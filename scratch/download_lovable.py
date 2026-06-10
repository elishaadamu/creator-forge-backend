import urllib.request
import re
import json

url = "https://creatorcofounder.lovable.app/assets/index-DJEXPdYt.js"
req = urllib.request.Request(
    url, 
    headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
)

try:
    with urllib.request.urlopen(req) as response:
        content = response.read().decode('utf-8')
    
    # Let's find some key components or strings in the JS
    print(f"Downloaded {len(content)} bytes of JS")
    
    # Find all strings matching "something"
    # We can write a file of all strings or text blocks
    # To understand the app flow, let's extract strings of length 15-500 that look like UI text
    strings = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', content)
    single_strings = re.findall(r"'([^'\\]*(?:\\.[^'\\]*)*)'", content)
    
    all_str = strings + single_strings
    filtered_str = []
    for s in all_str:
        s_clean = s.strip()
        # filter out css classes, tailwind utility classes, svg path data, etc.
        if len(s_clean) > 20 and not s_clean.startswith("M") and not s_clean.startswith("m") and " " in s_clean:
            if not any(c in s_clean for c in ["{", "}", ";", "px", "rem", "hover:", "focus:", "active:"]):
                filtered_str.append(s_clean)
                
    filtered_str = list(set(filtered_str))
    print(f"Found {len(filtered_str)} unique UI-like strings")
    
    # Save the strings to a scratch file so we can view them
    with open("scratch/lovable_strings.txt", "w") as f:
        for s in sorted(filtered_str, key=len):
            f.write(s + "\n")
            
    print("Saved to scratch/lovable_strings.txt")

except Exception as e:
    print(f"Error: {e}")
