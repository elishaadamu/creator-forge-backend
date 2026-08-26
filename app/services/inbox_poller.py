import asyncio
import email
from email.header import decode_header
import imaplib
import logging
from datetime import datetime
from email.utils import parseaddr
from typing import Optional

from app.config import settings
from app.database import SessionLocal
from app.models.creator import Contact, Creator
from app.models.outreach import OutreachMessage, Thread, Reply
from app.services.reply_classifier import record_reply

logger = logging.getLogger(__name__)

# Control flag for the async loop
_RUNNING = False

def _decode_str(val, charset=None):
    if isinstance(val, bytes):
        try:
            return val.decode(charset or 'utf-8', errors='replace')
        except LookupError:
            return val.decode('utf-8', errors='replace')
    return val

def _clean_email_body(body: str) -> str:
    """Strip quoted text from email replies."""
    if not body: return body
    import re
    
    # Replace \r\n with \n
    body = body.replace('\r\n', '\n')
    
    # Look for multi-line Gmail "On ... wrote:" pattern
    pattern = re.compile(r'\nOn\s+.*wrote:\s*', re.IGNORECASE | re.DOTALL)
    match = pattern.search(body)
    if match:
        body = body[:match.start()]
        
    lines = body.split('\n')
    cleaned = []
    
    quote_patterns = [
        re.compile(r'^_{3,}\s*$'),
        re.compile(r'^-{3,}\s*Original Message\s*-{3,}$', re.IGNORECASE),
        re.compile(r'^From:\s+.*$', re.IGNORECASE),
    ]
    
    for line in lines:
        stripped = line.strip()
        is_quote = False
        
        if stripped.startswith('>'):
            is_quote = True
            
        for p in quote_patterns:
            if p.match(stripped):
                is_quote = True
                break
                
        if is_quote:
            break
            
        cleaned.append(line)
        
    return '\n'.join(cleaned).strip()

def _parse_email_message(msg):
    # Parse Subject
    subject = ""
    if msg["Subject"]:
        headers = decode_header(msg["Subject"])
        subject = "".join([_decode_str(val, charset) for val, charset in headers])
        
    # Parse From
    from_raw = msg.get("From", "")
    _, from_email = parseaddr(from_raw)
    from_email = from_email.lower().strip()
    
    # Parse Body
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            if content_type == "text/plain" and "attachment" not in content_disposition:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset()
                    body = _decode_str(payload, charset)
                break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset()
            body = _decode_str(payload, charset)
            
    body = _clean_email_body(body)
    return subject, from_email, body

def _find_thread_for_sender(db, from_email: str, subject: str = "") -> Optional[str]:
    """Attempt to find the most recent thread ID for the sender's email address or subject line."""
    if not from_email:
        return None
    from_email_clean = from_email.lower().strip()
    creator_id = None

    all_creators = db.query(Creator).all()

    # 1. Match against Creator name or handle in subject line
    if subject:
        subj_lower = subject.lower()
        for c in all_creators:
            c_name = (c.display_name or "").lower().strip()
            c_handle = (c.handle or "").lower().lstrip("@").strip()
            if (c_name and len(c_name) >= 3 and c_name in subj_lower) or (c_handle and len(c_handle) >= 3 and c_handle in subj_lower):
                creator_id = c.id
                break

    # 2. Match against OutreachMessage subject
    if not creator_id and subject:
        clean_subj = subject.lower().replace("re:", "").replace("fwd:", "").strip()
        if clean_subj:
            msg = db.query(OutreachMessage).filter(OutreachMessage.subject.ilike(f"%{clean_subj[:30]}%")).order_by(OutreachMessage.created_at.desc()).first()
            if msg and msg.creator_id:
                creator_id = msg.creator_id

    # 3. Match against Creator table (email_public)
    if not creator_id:
        for c in all_creators:
            c_email = (c.email_public or "").lower().strip()
            if c_email and c_email == from_email_clean:
                creator_id = c.id
                break

    # 4. Match against Contacts table
    if not creator_id:
        contact = db.query(Contact).filter(Contact.value.ilike(f"%{from_email_clean}%"), Contact.contact_type == "email").first()
        if contact:
            creator_id = contact.creator_id

    # 5. If still not matched, find the most recently pitched creator
    if not creator_id and all_creators:
        recent_msg = db.query(OutreachMessage).order_by(OutreachMessage.created_at.desc()).first()
        if recent_msg and recent_msg.creator_id:
            creator_id = recent_msg.creator_id

    if not creator_id:
        return None

    # Find or create latest thread for this creator
    thread = db.query(Thread).filter(Thread.creator_id == creator_id).order_by(Thread.created_at.desc()).first()
    if not thread:
        thread = Thread(creator_id=creator_id, status="open")
        db.add(thread)
        db.commit()
        db.refresh(thread)
    return thread.id


import threading
import socket

_POLL_LOCK = threading.Lock()

def poll_inbox_sync():
    """Synchronous function that connects to IMAP, fetches recent messages, and processes incoming creator replies."""
    if not settings.GOOGLE_EMAIL or not settings.GOOGLE_APP_PASSWORD:
        logger.warning("IMAP Poller: GOOGLE_EMAIL or GOOGLE_APP_PASSWORD not set. Skipping poll.")
        return

    # Non-blocking lock: if another sync is currently running, skip to prevent stalling
    if not _POLL_LOCK.acquire(blocking=False):
        logger.debug("IMAP Poller already running in another thread. Skipping concurrent invocation.")
        return

    admin_email = (settings.GOOGLE_EMAIL or "").lower().strip()
    mail = None
    db = SessionLocal()
    prev_timeout = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(8)  # 8s fast socket timeout to prevent hang
        mail = imaplib.IMAP4_SSL("imap.gmail.com", timeout=8)
        mail.login(settings.GOOGLE_EMAIL, settings.GOOGLE_APP_PASSWORD.replace(" ", ""))
        mail.select("INBOX")
        
        # Search recent messages (fetch last 10 message IDs for instant response)
        status, messages = mail.search(None, "ALL")
        if status != "OK" or not messages[0]:
            return
            
        all_ids = messages[0].split()
        email_ids = all_ids[-25:]  # Check last 25 emails for instant responsive sync
        for e_id in email_ids:
            try:
                status, msg_data = mail.fetch(e_id, "(RFC822)")
                if status != "OK":
                    continue
                    
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        subject, from_email, body = _parse_email_message(msg)
                        
                        if not from_email:
                            continue

                        # Ignore outgoing emails sent by admin, system, or automated notifications.
                        # A self-reply is useful in local/testing workflows, so let messages
                        # with reply-style subjects reach the subject/thread matcher.
                        from_lower = from_email.lower().strip()
                        is_reply_subject = subject.lower().lstrip().startswith(("re:", "fwd:", "fw:"))
                        if ((from_lower == admin_email and not is_reply_subject)
                            or "mailer-daemon" in from_lower
                            or "no-reply" in from_lower
                            or "noreply" in from_lower
                            or "accounts.google.com" in from_lower):
                            continue
                            
                        thread_id = _find_thread_for_sender(db, from_email, subject)
                        
                        if thread_id:
                            # Check if reply already exists in DB to prevent duplicates
                            existing_reply = db.query(Reply).filter(
                                Reply.thread_id == thread_id,
                                Reply.from_address == from_email,
                                Reply.body == body,
                            ).first()

                            if not existing_reply:
                                try:
                                    record_reply(
                                        db=db,
                                        thread_id=thread_id,
                                        from_address=from_email,
                                        subject=subject,
                                        body=body,
                                        actor="imap_poller"
                                    )
                                    logger.info(f"Recorded IMAP reply from {from_email} to thread {thread_id}")
                                except Exception as e:
                                    safe_err = str(e).encode("ascii", "ignore").decode("ascii")
                                    logger.error(f"Failed to record reply from {from_email}: {safe_err}")
                            else:
                                pass
            except Exception as item_err:
                logger.debug(f"IMAP item fetch error: {item_err}")
                continue
    except Exception as e:
        safe_err = str(e).encode("ascii", "ignore").decode("ascii")
        logger.warning(f"IMAP Polling transient warning: {safe_err}")
    finally:
        try:
            socket.setdefaulttimeout(prev_timeout)
        except:
            pass
        db.close()
        if mail:
            try:
                mail.close()
            except:
                pass
            try:
                mail.logout()
            except:
                pass
        _POLL_LOCK.release()

async def start_poller_loop(interval_seconds: int = 60):
    global _RUNNING
    _RUNNING = True
    logger.info("Starting IMAP Inbox Poller loop...")
    while _RUNNING:
        try:
            # Run the synchronous IMAP polling in a threadpool to avoid blocking the async loop
            await asyncio.to_thread(poll_inbox_sync)
        except Exception as e:
            logger.error(f"Error in poller loop: {e}")
        
        await asyncio.sleep(interval_seconds)

def stop_poller_loop():
    global _RUNNING
    _RUNNING = False
    logger.info("Stopping IMAP Inbox Poller loop...")
