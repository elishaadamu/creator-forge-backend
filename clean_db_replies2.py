import os
import re

env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ[key.strip()] = val.strip()

from app.database import SessionLocal
from app.models.outreach import Reply

def _clean_email_body(body: str) -> str:
    """Strip quoted text from email replies."""
    if not body: return body
    
    # Handle the specific Gmail multi-line "On ... wrote:" pattern
    # It often looks like: "On Mon, Jun 15, 2026, 2:57 PM Person <email> wrote:"
    # which can be wrapped across multiple lines.
    
    # Let's just find the first occurrence of "On " followed by "wrote:" within a few lines.
    # A simpler way is to use regex with DOTALL to match the block, or just split by a relaxed pattern.
    
    # Replace \r\n with \n
    body = body.replace('\r\n', '\n')
    
    # Look for "On [Date], [Name] <[Email]> wrote:" and strip it and everything after
    pattern = re.compile(r'\nOn\s+.*wrote:\s*', re.IGNORECASE | re.DOTALL)
    match = pattern.search(body)
    if match:
        body = body[:match.start()]
        
    # Also handle '> ' quoting lines if they appear early
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

def run():
    db = SessionLocal()
    replies = db.query(Reply).all()
    updated = 0
    for r in replies:
        if r.body:
            cleaned = _clean_email_body(r.body)
            if cleaned != r.body:
                r.body = cleaned
                updated += 1
    
    if updated > 0:
        db.commit()
    print(f"Cleaned {updated} existing replies.")
    db.close()

if __name__ == "__main__":
    run()
