import asyncio
import email
from email.header import decode_header
import imaplib
import logging
from datetime import datetime
from email.utils import parseaddr

from app.config import settings
from app.database import SessionLocal
from app.models.creator import Contact, Creator
from app.models.outreach import Thread
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

def _find_thread_for_sender(db, from_email: str) -> str:
    """Attempt to find the most recent thread ID for the sender's email address."""
    # 1. Match against Contacts table
    contact = db.query(Contact).filter(Contact.value.ilike(f"%{from_email}%"), Contact.contact_type == "email").first()
    creator_id = contact.creator_id if contact else None
    
    # 2. Match against Creator table (public_email)
    if not creator_id:
        creator = db.query(Creator).filter(Creator.email_public.ilike(f"%{from_email}%")).first()
        if creator:
            creator_id = creator.id
            
    if not creator_id:
        return None
        
    # 3. Find latest thread
    thread = db.query(Thread).filter(Thread.creator_id == creator_id).order_by(Thread.created_at.desc()).first()
    return thread.id if thread else None

def poll_inbox_sync():
    """Synchronous function that connects to IMAP, fetches UNSEEN, and processes them."""
    if not settings.GOOGLE_EMAIL or not settings.GOOGLE_APP_PASSWORD:
        logger.warning("IMAP Poller: GOOGLE_EMAIL or GOOGLE_APP_PASSWORD not set. Skipping poll.")
        return

    mail = None
    db = SessionLocal()
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(settings.GOOGLE_EMAIL, settings.GOOGLE_APP_PASSWORD.replace(" ", ""))
        mail.select("INBOX")
        
        status, messages = mail.search(None, "UNSEEN")
        if status != "OK" or not messages[0]:
            return
            
        email_ids = messages[0].split()
        for e_id in email_ids:
            status, msg_data = mail.fetch(e_id, "(RFC822)")
            if status != "OK":
                continue
                
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    subject, from_email, body = _parse_email_message(msg)
                    
                    if not from_email:
                        continue
                        
                    thread_id = _find_thread_for_sender(db, from_email)
                    
                    if thread_id:
                        # We found a matching thread, record the reply!
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
                            logger.error(f"Failed to record reply from {from_email}: {e}")
                    else:
                        logger.info(f"Ignored UNSEEN email from {from_email} (No matching creator/thread found)")
                        
            # Mark as read
            # The act of fetching RFC822 typically marks as \Seen automatically in Gmail, 
            # but we can explicitly store the flag if needed.
            # mail.store(e_id, '+FLAGS', '\\Seen')
            
    except Exception as e:
        logger.error(f"IMAP Polling Error: {e}")
    finally:
        db.close()
        if mail:
            try:
                mail.logout()
            except:
                pass

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
