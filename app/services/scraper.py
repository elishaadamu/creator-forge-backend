"""
Public profile scraper — YouTube, Instagram, TikTok.
Only reads publicly visible page data. No login, no private info.
"""
import json
import re
import httpx

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Cookie": "CONSENT=YES+cb.20210328-17-p0.en+FX+433;",
}


def _num(s: str) -> int:
    """Parse '2.4M', '890K', '1,234' → int."""
    if not s:
        return 0
    s = s.strip().replace(",", "").replace(" subscribers", "").replace(" followers", "")
    try:
        if s.endswith("M"):
            return int(float(s[:-1]) * 1_000_000)
        if s.endswith("K"):
            return int(float(s[:-1]) * 1_000)
        return int(float(s))
    except Exception:
        return 0


def scrape_youtube(handle: str) -> dict:
    """
    Scrape a YouTube channel by @handle or URL.
    Uses Apify when key is configured, falls back to direct scrape.
    """
    from app.config import settings
    handle = handle.strip()
    if handle.startswith("UC") and len(handle) == 24:
        url = f"https://www.youtube.com/channel/{handle}"
    elif handle.startswith(("channel/", "c/", "user/", "@")):
        url = f"https://www.youtube.com/{handle}"
    else:
        url = f"https://www.youtube.com/@{handle}"

    result = {
        "handle": handle,
        "platform": "youtube",
        "profile_url": url,
        "display_name": handle,
        "bio": "",
        "avatar_url": "",
        "follower_count": 0,
        "banner_url": "",
        "niche": [],
        "email_public": "",
        "website": "",
        "social_links": [],
    }

    if settings.APIFY_API_KEY:
        try:
            items = _apify_run(
                "streamers/youtube-channel-scraper",
                {"startUrls": [{"url": url}], "maxResults": 10},
                settings.APIFY_API_KEY,
            )
            if items:
                d = items[0]
                result["display_name"] = d.get("channelName") or d.get("title") or handle
                result["bio"]           = d.get("channelDescription") or d.get("description") or d.get("about") or ""
                result["follower_count"]= d.get("numberOfSubscribers") or d.get("subscriberCount") or 0
                result["avatar_url"]    = d.get("channelAvatarUrl") or d.get("channelThumbnail") or d.get("avatarUrl") or ""
                result["banner_url"]    = d.get("channelBannerUrl") or ""
                
                # Extract videos
                recent = []
                for item in items:
                    if item.get("type") == "video" or item.get("type") == "short" or item.get("thumbnailUrl"):
                        recent.append({
                            "title": item.get("title") or "",
                            "thumbnail": item.get("thumbnailUrl") or "",
                            "videoId": item.get("id") or "",
                            "views": _num(str(item.get("viewCount", 0))),
                            "url": item.get("url") or ""
                        })
                result["recent_posts"] = recent[:6]
                
                # Check for website links
                links = d.get("channelDescriptionLinks", [])
                if links and isinstance(links, list) and len(links) > 0:
                    result["website"] = links[0].get("url", "")
                else:
                    result["website"] = d.get("links", [None])[0] if d.get("links") else ""
                # Extract emails from bio
                emails = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", result["bio"])
                if emails:
                    result["email_public"] = emails[0]
                # Guess niche
                bio_lower = (result["bio"] or "").lower()
                niche_map = {
                    "fitness": ["fitness", "workout", "gym", "health", "exercise"],
                    "cooking": ["cook", "recipe", "food", "kitchen", "chef"],
                    "tech": ["tech", "software", "coding", "developer", "programming", "gadget", "review", "electronics"],
                    "finance": ["finance", "invest", "money", "wealth", "stock"],
                    "gaming": ["gaming", "gamer", "twitch", "esport", "playthrough"],
                    "beauty": ["beauty", "makeup", "skincare", "cosmetic"],
                    "travel": ["travel", "explore", "adventure", "nomad"],
                    "education": ["learn", "teach", "tutorial", "course", "education"],
                    "lifestyle": ["lifestyle", "vlog", "daily", "routine"],
                    "business": ["entrepreneur", "business", "startup", "founder"],
                }
                for tag, keywords in niche_map.items():
                    if any(k in bio_lower for k in keywords):
                        result["niche"].append(tag)
                return result
        except Exception as e:
            result["error"] = f"Apify: {e}"

    # ── Direct scrape fallback ──────────────────────────────────────────────────
    try:
        r = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
        html = r.text
    except Exception as e:
        return {"error": str(e), "handle": handle, "platform": "youtube"}

    # ── Extract ytInitialData JSON ──
    m = re.search(r"var ytInitialData\s*=\s*(\{.+?\});\s*(?:var|</script)", html, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(1))

            # Channel name
            try:
                result["display_name"] = (
                    data["header"]["pageHeaderRenderer"]["pageTitle"]
                    or data["metadata"]["channelMetadataRenderer"]["title"]
                )
            except Exception:
                try:
                    result["display_name"] = data["metadata"]["channelMetadataRenderer"]["title"]
                except Exception:
                    pass

            # Description / bio
            try:
                result["bio"] = data["metadata"]["channelMetadataRenderer"]["description"]
            except Exception:
                pass

            # Avatar
            try:
                avatars = (
                    data["header"]["pageHeaderRenderer"]["content"]
                    ["pageHeaderViewModel"]["image"]["decoratedAvatarViewModel"]
                    ["avatar"]["avatarViewModel"]["image"]["sources"]
                )
                result["avatar_url"] = avatars[-1]["url"] if avatars else ""
            except Exception:
                try:
                    result["avatar_url"] = (
                        data["metadata"]["channelMetadataRenderer"]
                        ["avatar"]["thumbnails"][-1]["url"]
                    )
                except Exception:
                    pass

            # Subscriber count — try multiple paths
            sub_text = ""
            try:
                rows = (
                    data["header"]["pageHeaderRenderer"]["content"]
                    ["pageHeaderViewModel"]["metadata"]
                    ["contentMetadataViewModel"]["metadataRows"]
                )
                for row in rows:
                    for part in row.get("metadataParts", []):
                        txt = part.get("text", {}).get("content", "")
                        if "subscriber" in txt.lower() or any(c in txt for c in ["K", "M", "B"]):
                            sub_text = txt
                            break
            except Exception:
                pass

            if not sub_text:
                try:
                    sub_text = (
                        data["header"]["c4TabbedHeaderRenderer"]
                        ["subscriberCountText"]["simpleText"]
                    )
                except Exception:
                    pass

            if sub_text:
                result["follower_count"] = _num(sub_text)

            # Website / social links from channel
            try:
                links = (
                    data["header"]["pageHeaderRenderer"]["content"]
                    ["pageHeaderViewModel"]["metadata"]
                    ["contentMetadataViewModel"]["metadataRows"]
                )
                for row in links:
                    for part in row.get("metadataParts", []):
                        url_val = part.get("tapEndpoint", {}).get("urlEndpoint", {}).get("url", "")
                        if url_val and "youtube.com" not in url_val:
                            # Decode Google redirect URL
                            q = re.search(r"q=([^&]+)", url_val)
                            if q:
                                import urllib.parse
                                decoded = urllib.parse.unquote(q.group(1))
                                result["social_links"].append(decoded)
                                if not result["website"]:
                                    result["website"] = decoded
            except Exception:
                pass

        except json.JSONDecodeError:
            pass

    # ── Fallback: regex scan for YouTube avatar CDN URLs in raw HTML ──
    if not result["avatar_url"]:
        m = re.search(r'(https://yt3\.(?:ggpht|googleusercontent)\.com/[^"\s\\]{20,})', html)
        if m:
            raw_url = m.group(1).split('"')[0]
            result["avatar_url"] = raw_url

    # ── Fallback: oEmbed for display name ──
    if not result["display_name"] or result["display_name"] == handle:
        try:
            oe = httpx.get(
                f"https://www.youtube.com/oembed?url=https://www.youtube.com/@{handle}&format=json",
                headers=HEADERS, timeout=10,
            )
            if oe.status_code == 200:
                oe_data = oe.json()
                result["display_name"] = oe_data.get("author_name", handle)
        except Exception:
            pass

    # ── Extract emails from bio ──
    emails = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", result["bio"])
    if emails:
        result["email_public"] = emails[0]

    # ── Guess niche from bio keywords ──
    bio_lower = (result["bio"] or "").lower()
    niche_map = {
        "fitness": ["fitness", "workout", "gym", "health", "exercise"],
        "cooking": ["cook", "recipe", "food", "kitchen", "chef"],
        "tech": ["tech", "software", "coding", "developer", "programming"],
        "finance": ["finance", "invest", "money", "wealth", "stock"],
        "gaming": ["gaming", "gamer", "twitch", "esport", "playthrough"],
        "beauty": ["beauty", "makeup", "skincare", "cosmetic"],
        "travel": ["travel", "explore", "adventure", "nomad"],
        "education": ["learn", "teach", "tutorial", "course", "education"],
        "lifestyle": ["lifestyle", "vlog", "daily", "routine"],
        "business": ["entrepreneur", "business", "startup", "founder"],
    }
    for tag, keywords in niche_map.items():
        if any(k in bio_lower for k in keywords):
            result["niche"].append(tag)

    return result


def _clean_url(url: str) -> str:
    """Decode JSON/unicode escapes in URLs (e.g. \\u002F → /)."""
    if not url:
        return url
    try:
        import json as _json
        return _json.loads(f'"{url}"')
    except Exception:
        return url.replace("\\u002F", "/").replace("\\u0026", "&").replace("\\/", "/")


def _apify_run(actor_id: str, run_input: dict, api_key: str) -> list:
    """
    Run an Apify actor synchronously and return the dataset items.
    Polls until finished (max 60s).
    """
    import time
    base = "https://api.apify.com/v2"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    # Apify uses ~ not / in URL paths for actor IDs
    actor_url_id = actor_id.replace("/", "~")
    # Start run
    r = httpx.post(
        f"{base}/acts/{actor_url_id}/runs",
        json=run_input, headers=headers, timeout=20,
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Apify run failed: {r.status_code} {r.text[:200]}")
    run_id = r.json()["data"]["id"]

    # Poll for completion
    for _ in range(24):  # 24 × 2.5s = 60s max
        time.sleep(2.5)
        status_r = httpx.get(f"{base}/actor-runs/{run_id}", headers=headers, timeout=10)
        status = status_r.json()["data"]["status"]
        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            break

    if status != "SUCCEEDED":
        raise RuntimeError(f"Apify actor {actor_id} ended with status: {status}")

    # Fetch results
    dataset_id = status_r.json()["data"]["defaultDatasetId"]
    items_r = httpx.get(f"{base}/datasets/{dataset_id}/items", headers=headers, timeout=15)
    return items_r.json() if isinstance(items_r.json(), list) else []


def scrape_instagram(handle: str) -> dict:
    """Instagram scrape — uses Apify when key is configured, falls back to direct."""
    from app.config import settings
    handle = handle.lstrip("@").strip()
    url = f"https://www.instagram.com/{handle}/"
    result = {
        "handle": handle, "platform": "instagram", "profile_url": url,
        "display_name": handle, "bio": "", "avatar_url": "",
        "follower_count": 0, "niche": [], "email_public": "",
        "website": "", "social_links": [],
    }

    if settings.APIFY_API_KEY:
        try:
            items = _apify_run(
                "apify/instagram-profile-scraper",
                {"usernames": [handle]},
                settings.APIFY_API_KEY,
            )
            if items:
                d = items[0]
                result["display_name"]  = d.get("fullName") or d.get("username") or handle
                result["bio"]           = d.get("biography") or ""
                result["follower_count"]= d.get("followersCount") or d.get("followedBy") or 0
                result["avatar_url"]    = d.get("profilePicUrlHD") or d.get("profilePicUrl") or ""
                result["website"]       = d.get("externalUrl") or d.get("websiteUrl") or ""
                emails = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", result["bio"])
                if emails:
                    result["email_public"] = emails[0]
            return result
        except Exception as e:
            result["error"] = f"Apify: {e}"

    # Direct fallback (limited — Instagram blocks most requests)
    try:
        r = httpx.get(url, headers=HEADERS, timeout=12, follow_redirects=True)
        html = r.text
        for pat, key in [
            (r'"edge_followed_by":\{"count":(\d+)\}', "follower_count"),
            (r'"biography":"([^"]*)"', "bio"),
            (r'"full_name":"([^"]*)"', "display_name"),
            (r'"profile_pic_url":"([^"]*)"', "avatar_url"),
            (r'"external_url":"([^"]*)"', "website"),
        ]:
            m = re.search(pat, html)
            if m:
                val = m.group(1).replace("\\/", "/")
                if key == "follower_count":
                    result[key] = int(val)
                else:
                    result[key] = val
        emails = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", result["bio"])
        if emails:
            result["email_public"] = emails[0]
    except Exception as e:
        result["error"] = str(e)
    return result


def scrape_tiktok(handle: str) -> dict:
    """TikTok scrape — uses Apify when key is configured, falls back to direct."""
    from app.config import settings
    handle = handle.lstrip("@").strip()
    url = f"https://www.tiktok.com/@{handle}"
    result = {
        "handle": handle, "platform": "tiktok", "profile_url": url,
        "display_name": handle, "bio": "", "avatar_url": "",
        "follower_count": 0, "niche": [], "email_public": "",
        "website": "", "social_links": [],
    }

    if settings.APIFY_API_KEY:
        try:
            items = _apify_run(
                "clockworks/tiktok-profile-scraper",
                {"profiles": [f"https://www.tiktok.com/@{handle}"], "resultsPerPage": 1},
                settings.APIFY_API_KEY,
            )
            if items:
                d = items[0]
                result["display_name"]  = d.get("nickname") or d.get("authorMeta", {}).get("name") or handle
                result["bio"]           = d.get("signature") or d.get("authorMeta", {}).get("signature") or ""
                result["follower_count"]= d.get("followerCount") or d.get("authorMeta", {}).get("fans") or 0
                raw_av = d.get("avatarLarger") or d.get("avatarMedium") or d.get("authorMeta", {}).get("avatar") or ""
                result["avatar_url"]    = _clean_url(raw_av)
                emails = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", result["bio"])
                if emails:
                    result["email_public"] = emails[0]
            return result
        except Exception as e:
            result["error"] = f"Apify: {e}"

    # Direct fallback
    try:
        r = httpx.get(url, headers=HEADERS, timeout=12, follow_redirects=True)
        html = r.text
        for pat, key in [
            (r'"followerCount":(\d+)', "follower_count"),
            (r'"desc":"([^"]*)"', "bio"),
            (r'"nickname":"([^"]*)"', "display_name"),
            (r'"avatarLarger":"([^"]*)"', "avatar_url"),
        ]:
            m = re.search(pat, html)
            if m:
                val = m.group(1).replace("\\/", "/")
                if key == "follower_count":
                    result[key] = int(val)
                elif key == "avatar_url":
                    result[key] = _clean_url(val)
                else:
                    result[key] = val
        emails = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", result["bio"])
        if emails:
            result["email_public"] = emails[0]
    except Exception as e:
        result["error"] = str(e)
    return result


def scrape_twitter(handle: str) -> dict:
    """Twitter/X scrape — uses Apify when key is configured."""
    from app.config import settings
    handle = handle.lstrip("@").strip()
    url = f"https://x.com/{handle}"
    result = {
        "handle": handle, "platform": "twitter", "profile_url": url,
        "display_name": handle, "bio": "", "avatar_url": "",
        "follower_count": 0, "niche": [], "email_public": "",
        "website": "", "social_links": [],
    }

    if settings.APIFY_API_KEY:
        try:
            items = _apify_run(
                "apify/twitter-scraper",
                {
                    "twitterHandles": [handle],
                    "maxItems": 20,
                    "addUserInfo": True,
                    "includeUserData": True
                },
                settings.APIFY_API_KEY,
            )
            if items:
                item = items[0]
                user = item.get("author") or item.get("user") or (item if item.get("userName") else None)
                if user:
                    username = user.get("userName") or user.get("screen_name") or handle
                    result["display_name"] = user.get("name") or user.get("displayName") or username
                    result["bio"] = user.get("description") or user.get("bio") or ""
                    result["follower_count"] = user.get("followers") or user.get("followersCount") or 0
                    avatar_raw = user.get("profilePicture") or user.get("profile_image_url_https") or user.get("avatarUrl") or ""
                    result["avatar_url"] = avatar_raw.replace("_normal", "_400x400") if avatar_raw else ""
            return result
        except Exception as e:
            result["error"] = f"Apify: {e}"
    return result


def scrape_profile(platform: str, handle: str) -> dict:
    """Dispatch to correct scraper."""
    if platform == "youtube":
        return scrape_youtube(handle)
    elif platform == "instagram":
        return scrape_instagram(handle)
    elif platform == "tiktok":
        return scrape_tiktok(handle)
    elif platform == "twitter":
        return scrape_twitter(handle)
    else:
        return {"error": f"No scraper for platform: {platform}", "handle": handle, "platform": platform}

