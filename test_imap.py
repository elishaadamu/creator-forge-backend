import os
import imaplib

# Load environment variables
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ[key.strip()] = val.strip()

from app.config import settings

def test_imap():
    email = settings.GOOGLE_EMAIL
    password = settings.GOOGLE_APP_PASSWORD

    print(f"Testing IMAP connection for: {email}")
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(email, password)
        print("✅ Login successful!")
        
        mail.select("INBOX")
        status, messages = mail.search(None, "UNSEEN")
        if status == "OK":
            unseen_count = len(messages[0].split())
            print(f"✅ Selected INBOX. Found {unseen_count} UNSEEN messages.")
        else:
            print("❌ Failed to select INBOX.")
            
        mail.logout()
    except Exception as e:
        print(f"❌ IMAP Test Failed: {e}")

if __name__ == "__main__":
    test_imap()
