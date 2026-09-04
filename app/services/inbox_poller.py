import asyncio
import email
from email.header import decode_header
import imaplib
import logging
import re
from datetime import datetime
from email.utils import parseaddr
from typing import Optional, List

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
    raw_body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            if content_type == "text/plain" and "attachment" not in content_disposition:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset()
                    raw_body = _decode_str(payload, charset)
                break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset()
            raw_body = _decode_str(payload, charset)
            
    cleaned_body = _clean_email_body(raw_body)
    return subject, from_email, cleaned_body, raw_body

def _find_thread_for_sender(db, from_email: str, subject: str = "", body: str = "", raw_body: str = "", all_creators: Optional[List[Creator]] = None) -> Optional[str]:
    """Attempt to find the thread ID for a creator using tracking tokens, handle, subject, or email."""
    if not from_email:
        return None
    from_email_clean = from_email.lower().strip()
    creator_id = None
    all_text = f"{subject} {body} {raw_body}".lower()

    # 1. Primary & 100% Reliable: Direct Creator Tracking Token
    # Matches [CF-CID:<creator_id>] embedded in the subject or quoted email body
    cid_match = re.search(r"cf-cid:([a-z0-9\-_]+)", all_text)
    if cid_match:
        cand_id = cid_match.group(1).strip()
        c = db.get(Creator, cand_id)
        if c:
            creator_id = c.id
        else:
            # Token belongs to an explicitly deleted creator — DO NOT match to other creators
            return None

    # 2. Handle token match: Handle:@<handle> or [#<handle>]
    if not creator_id:
        handle_match = re.search(r"handle:@([a-z0-9_.\-]+)", all_text) or re.search(r"\[#([a-z0-9_.\-]+)\]", all_text)
        if handle_match:
            cand_handle = handle_match.group(1).strip()
            c = db.query(Creator).filter(Creator.handle.ilike(f"%{cand_handle}%")).first()
            if c:
                creator_id = c.id
            else:
                # Handle token belongs to a deleted creator — DO NOT match to other creators
                return None

    if all_creators is None:
        all_creators = db.query(Creator).all()

    # 3. Match against Creator display_name or handle in subject line
    if not creator_id and subject:
        subj_lower = subject.lower()
        sorted_creators = sorted(all_creators, key=lambda x: len(x.display_name or ""), reverse=True)
        for c in sorted_creators:
            c_name = (c.display_name or "").lower().strip()
            c_handle = (c.handle or "").lower().lstrip("@").strip()
            if (c_name and len(c_name) >= 3 and c_name in subj_lower) or (c_handle and len(c_handle) >= 3 and c_handle in subj_lower):
                creator_id = c.id
                break

    # 4. Match against OutreachMessage subject
    if not creator_id and subject:
        clean_subj = subject.lower().replace("re:", "").replace("fwd:", "").replace("fw:", "").strip()
        if len(clean_subj) >= 6:
            msg = db.query(OutreachMessage).filter(OutreachMessage.subject.ilike(f"%{clean_subj[:35]}%")).order_by(OutreachMessage.created_at.desc()).first()
            if msg and msg.creator_id:
                creator_id = msg.creator_id

    admin_email = (settings.GOOGLE_EMAIL or settings.FROM_EMAIL or "elishadamu97@gmail.com").lower().strip()
    is_admin_email = from_email_clean == admin_email

    # 5. Match against Creator table (email_public) with multiple-creator disambiguation
    if not creator_id and not is_admin_email:
        matching_creators = [c for c in all_creators if (c.email_public or "").lower().strip() == from_email_clean]
        if len(matching_creators) == 1:
            creator_id = matching_creators[0].id
        elif len(matching_creators) > 1:
            # If multiple creators share this email (e.g. test environment or agency address):
            # Prefer the creator with the most recent open outreach thread
            recent_thread = db.query(Thread).filter(
                Thread.creator_id.in_([c.id for c in matching_creators])
            ).order_by(Thread.last_activity.desc()).first()
            if recent_thread:
                return recent_thread.id
            creator_id = matching_creators[0].id

    # 6. Match against Contacts table
    if not creator_id and not is_admin_email:
        contact = db.query(Contact).filter(Contact.value.ilike(f"%{from_email_clean}%"), Contact.contact_type == "email").first()
        if contact and contact.creator_id:
            creator_id = contact.creator_id

    # Strictly do NOT assign unrecognized/marketing emails to random creators
    if not creator_id:
        return None

    # Find or create latest thread for this specific creator
    thread = db.query(Thread).filter(Thread.creator_id == creator_id).order_by(Thread.created_at.desc()).first()
    if not thread:
        thread = Thread(creator_id=creator_id, status="open", created_at=datetime.utcnow(), last_activity=datetime.utcnow())
        db.add(thread)
        db.commit()
        db.refresh(thread)
    return thread.id


import threading
import socket

_POLL_LOCK = threading.Lock()

def poll_inbox_sync(wait_timeout: float = 0.0) -> dict:
    """Synchronous function that connects to IMAP, fetches recent messages, and processes incoming creator replies."""
    if not settings.GOOGLE_EMAIL or not settings.GOOGLE_APP_PASSWORD:
        logger.warning("IMAP Poller: GOOGLE_EMAIL or GOOGLE_APP_PASSWORD not set. Skipping poll.")
        return {"status": "skipped", "reason": "no_credentials", "new_replies": 0}

    # Non-blocking or bounded lock acquisition
    acquired = _POLL_LOCK.acquire(timeout=wait_timeout) if wait_timeout > 0 else _POLL_LOCK.acquire(blocking=False)
    if not acquired:
        logger.debug("IMAP Poller already running in another thread. Skipping concurrent invocation.")
        return {"status": "busy", "reason": "already_running", "new_replies": 0}

    admin_email = (settings.GOOGLE_EMAIL or "").lower().strip()
    mail = None
    prev_timeout = socket.getdefaulttimeout()
    new_replies_count = 0
    candidate_messages = []
    try:
        socket.setdefaulttimeout(8)  # 8s socket timeout to prevent hang
        mail = imaplib.IMAP4_SSL("imap.gmail.com", timeout=8)
        mail.login(settings.GOOGLE_EMAIL, settings.GOOGLE_APP_PASSWORD.replace(" ", ""))
        mail.select("INBOX")
        
        # Search recent messages (fetch last 20 message IDs for instant response)
        status, messages = mail.search(None, "ALL")
        if status != "OK" or not messages[0]:
            return {"status": "success", "new_replies": 0, "processed": 0}
            
        all_ids = messages[0].split()
        email_ids = all_ids[-15:]  # Check last 15 emails for responsive sync
        status, msg_data = mail.fetch(b",".join(email_ids), "(RFC822)")
        if status == "OK" and msg_data:
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    try:
                        msg = email.message_from_bytes(response_part[1])
                        subject, from_email, body, raw_body = _parse_email_message(msg)
                        
                        if not from_email:
                            continue

                        from_lower = from_email.lower().strip()
                        is_reply_subject = subject.lower().lstrip().startswith(("re:", "fwd:", "fw:"))

                        # Filter out automated marketing, system alerts, and notification bots
                        ignore_patterns = (
                            "mailer-daemon", "no-reply", "noreply", "accounts.google.com",
                            "googleaistudio", "prisma.io", "openai.com", "twilio.com",
                            "qualtrics", "apify.com", "github.com", "notifications@",
                            "security-noreply"
                        )
                        if any(pat in from_lower for pat in ignore_patterns):
                            continue

                        # Ignore outgoing messages from admin unless it's a self-test reply
                        if from_lower == admin_email and not is_reply_subject:
                            continue

                        candidate_messages.append((from_email, subject, body, raw_body))
                    except Exception as item_err:
                        logger.debug(f"IMAP item parse error: {item_err}")
                        continue

        # If candidate messages were found, open a dedicated short-lived DB session to process them
        if candidate_messages:
            db = SessionLocal()
            try:
                all_creators = db.query(Creator).all()
                for from_email, subject, body, raw_body in candidate_messages:
                    thread_id = _find_thread_for_sender(db, from_email, subject, body, raw_body, all_creators=all_creators)
                    if thread_id:
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
                                new_replies_count += 1
                                logger.info(f"Recorded IMAP reply from {from_email} to thread {thread_id}")
                            except Exception as e:
                                safe_err = str(e).encode("ascii", "ignore").decode("ascii")
                                logger.error(f"Failed to record reply from {from_email}: {safe_err}")
            finally:
                db.close()
        return {"status": "success", "new_replies": new_replies_count, "processed": len(candidate_messages)}
    except Exception as e:
        safe_err = str(e).encode("ascii", "ignore").decode("ascii")
        logger.warning(f"IMAP Polling transient warning: {safe_err}")
        return {"status": "error", "error": safe_err, "new_replies": 0}
    finally:
        try:
            socket.setdefaulttimeout(prev_timeout)
        except Exception:
            pass
        if mail:
            try:
                mail.close()
            except Exception:
                pass
            try:
                mail.logout()
            except Exception:
                pass
        if _POLL_LOCK.locked():
            try:
                _POLL_LOCK.release()
            except Exception:
                pass

async def start_poller_loop(interval_seconds: int = 60):
    global _RUNNING
    _RUNNING = True
    logger.info("Starting IMAP Inbox Poller loop...")
    await asyncio.sleep(5)  # Let server complete startup and bind to port
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
