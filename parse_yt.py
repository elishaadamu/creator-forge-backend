import re
with open("yt_test.html") as f:
    html = f.read()
print("Title:", re.search(r'<title>(.*?)</title>', html).group(1))
m = re.search(r'var ytInitialData\s*=\s*(.*?);</script>', html)
if m:
    print("Found ytInitialData")
else:
    print("ytInitialData not found!")
    # Check for window["ytInitialData"]
    m2 = re.search(r'window\["ytInitialData"\]\s*=\s*(.*?);', html)
    if m2:
        print("Found window['ytInitialData']")
    else:
        print("Not found either.")
