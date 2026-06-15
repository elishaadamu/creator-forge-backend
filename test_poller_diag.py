"""Quick diagnostic: check what the poller would do with UNSEEN emails."""
import os, sys, imaplib, email
from email.header import decode_header
from email.utils import parseaddr

env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ[key.strip()] = val.strip()

from app.config import settings
from app.database import SessionLocal
from app.models.creator import Contact, Creator
from app.models.outreach import Thread

def decode_str(val, charset=None):
    if isinstance(val, bytes):
        try:
            return val.decode(charset or 'utf-8', errors='replace')
        except LookupError:
            return val.decode('utf-8', errors='replace')
    return val

db = SessionLocal()

# Show all contacts in DB
contacts = db.query(Contact).filter(Contact.contact_type == "email").all()
print(f"=== {len(contacts)} email contacts in DB ===")
for c in contacts:
    print(f"  creator_id={c.creator_id[:8]}  email={c.value}")

# Show creators with public email
creators = db.query(Creator).filter(Creator.email_public.isnot(None), Creator.email_public != "").all()
print(f"\n=== {len(creators)} creators with email_public ===")
for cr in creators:
    print(f"  id={cr.id[:8]}  email_public={cr.email_public}")

# Show threads
threads = db.query(Thread).all()
print(f"\n=== {len(threads)} threads in DB ===")
for t in threads:
    print(f"  thread_id={t.id[:8]}  creator_id={t.creator_id[:8]}  status={t.status}")

# Now check UNSEEN emails
print("\n=== Checking UNSEEN emails in Gmail ===")
mail = imaplib.IMAP4_SSL("imap.gmail.com")
mail.login(settings.GOOGLE_EMAIL, settings.GOOGLE_APP_PASSWORD.replace(" ", ""))
mail.select("INBOX")

status, messages = mail.search(None, "UNSEEN")
if status == "OK" and messages[0]:
    email_ids = messages[0].split()
    for e_id in email_ids:
        status, msg_data = mail.fetch(e_id, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
        if status == "OK":
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    header_data = response_part[1].decode('utf-8', errors='replace')
                    msg = email.message_from_string(header_data)
                    _, from_email = parseaddr(msg.get("From", ""))
                    subject_parts = decode_header(msg.get("Subject", ""))
                    subject = "".join([decode_str(v, c) for v, c in subject_parts])
                    print(f"  From: {from_email}  Subject: {subject[:60]}")
                    
                    # Check if this matches any contact
                    contact = db.query(Contact).filter(
                        Contact.value.ilike(f"%{from_email}%"),
                        Contact.contact_type == "email"
                    ).first()
                    creator = db.query(Creator).filter(
                        Creator.email_public.ilike(f"%{from_email}%")
                    ).first() if not contact else None
                    
                    if contact:
                        print(f"    → MATCH via Contact (creator_id={contact.creator_id[:8]})")
                    elif creator:
                        print(f"    → MATCH via Creator.email_public (id={creator.id[:8]})")
                    else:
                        print(f"    → NO MATCH (will be ignored)")
else:
    print("  No UNSEEN messages.")

mail.logout()
db.close()
print("\nDone.")
