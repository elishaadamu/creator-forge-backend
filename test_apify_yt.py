import httpx, time, os

# Load env
for line in open(".env").readlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

API_KEY = os.environ["APIFY_API_KEY"]
base = "https://api.apify.com/v2"
headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

# Try YouTube channel scraper actor
r = httpx.post(
    f"{base}/acts/streamers~youtube-channel-scraper/runs",
    json={"startUrls": [{"url": "https://www.youtube.com/@mkbhd"}], "maxResults": 1},
    headers=headers, timeout=20
)
print("Status:", r.status_code, r.text[:300])
