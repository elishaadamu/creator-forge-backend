"""Check if replies exist in the DB."""
import os
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ[key.strip()] = val.strip()

from app.database import SessionLocal
from app.models.outreach import Thread, Reply

db = SessionLocal()
threads = db.query(Thread).all()
print(f"=== {len(threads)} threads ===")
for t in threads:
    replies = db.query(Reply).filter(Reply.thread_id == t.id).all()
    creator_name = t.creator.display_name if t.creator else "?"
    print(f"  Thread {t.id[:8]} | Creator: {creator_name} | Status: {t.status} | Replies: {len(replies)}")
    for r in replies:
        print(f"    Reply from {r.from_address} | Classification: {r.classification} | Body: {(r.body or '')[:80]}")

db.close()
