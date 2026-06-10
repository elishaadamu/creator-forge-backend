import httpx
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Cookie": "CONSENT=YES+cb.20210328-17-p0.en+FX+433;",
}
r = httpx.get("https://www.youtube.com/@mkbhd", headers=HEADERS, follow_redirects=True)
with open("yt_test.html", "w") as f:
    f.write(r.text)
import re
print("Title:", re.search(r'<title>(.*?)</title>', r.text).group(1))
