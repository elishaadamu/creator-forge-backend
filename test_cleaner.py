import re

def clean_email_body(body: str) -> str:
    """Strip quoted text from email replies."""
    lines = body.split('\n')
    cleaned = []
    
    # Common quote headers
    quote_patterns = [
        re.compile(r'^On\s+.*wrote:\s*$'),
        re.compile(r'^_{3,}\s*$'), # _________
        re.compile(r'^-{3,}\s*Original Message\s*-{3,}$', re.IGNORECASE),
        re.compile(r'^>'),
        re.compile(r'^From:\s+.*$', re.IGNORECASE),
    ]
    
    for line in lines:
        stripped = line.strip()
        
        # If we hit a quote line, we stop parsing and assume the rest is history
        is_quote = False
        for p in quote_patterns:
            if p.match(stripped):
                is_quote = True
                break
                
        if is_quote:
            break
            
        cleaned.append(line)
        
    return '\n'.join(cleaned).strip()

def test():
    body = """Yes, I would be interested.

On Mon, Jun 15, 2026, 3:47 PM Creator Forge <creatorforgeweb@gmail.com> wrote:
> Hi Whitney...
"""
    print("--- Before ---")
    print(body)
    print("--- After ---")
    print(clean_email_body(body))

if __name__ == "__main__":
    test()
