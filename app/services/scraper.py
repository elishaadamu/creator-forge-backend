"""
Public profile scraper — YouTube, Instagram, TikTok.
Only reads publicly visible page data. No login, no private info.
"""
import json
import re
import httpx
import logging

logger = logging.getLogger(__name__)

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
    s = s.strip().replace(",", "").replace(" subscribers", "").replace(" subscriber", "").replace(" followers", "").replace(" follower", "")
    try:
        if s.endswith("M") or s.endswith("m"):
            return int(float(s[:-1]) * 1_000_000)
        if s.endswith("K") or s.endswith("k"):
            return int(float(s[:-1]) * 1_000)
        if s.endswith("B") or s.endswith("b"):
            return int(float(s[:-1]) * 1_000_000_000)
        return int(float(s))
    except Exception:
        return 0


def _follower_count(value) -> int:
    """Normalize platform follower fields that may be numbers or abbreviated strings."""
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, (int, float)):
        return max(0, int(value))
    return _num(str(value))


def _first_value(data: dict, *keys):
    """Return the first populated value from a provider response."""
    for key in keys:
        value = data.get(key)
        if value is not None and value != "":
            return value
    return 0


def _apify_run(actor_id: str, run_input: dict, api_key: str, timeout_secs: int = 150) -> list:
    """
    Run an Apify actor and return dataset items.
    Uses POST /runs with waitForFinish and dataset items extraction,
    with run-sync fallback.
    """
    import urllib.parse
    import time
    if not api_key:
        return []
    safe_actor = actor_id.replace("/", "~")
    token_str = api_key.strip()

    # 1. Start run with waitForFinish parameter (official Apify pattern)
    try:
        run_url = f"https://api.apify.com/v2/acts/{urllib.parse.quote(safe_actor)}/runs?token={token_str}&waitForFinish={int(timeout_secs)}"
        r = httpx.post(run_url, json=run_input, timeout=float(timeout_secs + 20))
        if r.status_code in (200, 201):
            run_data = r.json().get("data", {})
            status = run_data.get("status")
            dataset_id = run_data.get("defaultDatasetId")
            run_id = run_data.get("id")

            if status == "SUCCEEDED" and dataset_id:
                items_url = f"https://api.apify.com/v2/datasets/{dataset_id}/items?token={token_str}"
                ir = httpx.get(items_url, timeout=30.0)
                if ir.status_code == 200:
                    items = ir.json()
                    if isinstance(items, list) and len(items) > 0:
                        return items

            # If still running asynchronously, poll until completion
            if run_id and dataset_id and status not in ("FAILED", "ABORTED", "TIMED-OUT"):
                start_t = time.time()
                while time.time() - start_t < timeout_secs:
                    time.sleep(3.0)
                    poll_url = f"https://api.apify.com/v2/actor-runs/{run_id}?token={token_str}"
                    pr = httpx.get(poll_url, timeout=15.0)
                    if pr.status_code == 200:
                        p_status = pr.json().get("data", {}).get("status")
                        if p_status == "SUCCEEDED":
                            items_url = f"https://api.apify.com/v2/datasets/{dataset_id}/items?token={token_str}"
                            ir = httpx.get(items_url, timeout=30.0)
                            if ir.status_code == 200:
                                items = ir.json()
                                if isinstance(items, list) and len(items) > 0:
                                    return items
                        elif p_status in ("FAILED", "ABORTED", "TIMED-OUT"):
                            break
    except Exception as e:
        logger.warning(f"[Apify Run] Notice for {actor_id}: {e}")

    # 2. Fallback: Direct run-sync-get-dataset-items
    try:
        sync_url = f"https://api.apify.com/v2/acts/{urllib.parse.quote(safe_actor)}/run-sync-get-dataset-items?token={token_str}&timeout={int(timeout_secs)}"
        r = httpx.post(sync_url, json=run_input, timeout=float(timeout_secs + 20))
        if r.status_code in (200, 201):
            data = r.json()
            if isinstance(data, list) and len(data) > 0:
                return data
            elif isinstance(data, dict) and "items" in data:
                return data["items"]
    except Exception as e:
        logger.debug(f"[Apify Fallback] Sync notice: {e}")

    return []


def apify_scrape_tiktok_profiles(handles: list, apify_token: str = None, timeout_secs: int = 90) -> list:
    """
    Run Apify TikTok Profile Scraper (clockworks/tiktok-profile-scraper / 0FXVyOXXEmdGcV88a).
    """
    from app.config import settings
    token = apify_token or settings.APIFY_API_KEY
    if not token or not handles:
        return []

    actor_id = getattr(settings, "APIFY_TIKTOK_ACTOR", "0FXVyOXXEmdGcV88a")
    cleaned_profiles = [str(h).lstrip("@").strip() for h in handles if str(h).strip()]
    if not cleaned_profiles:
        return []

    run_input = {
        "profiles": cleaned_profiles,
        "profileScrapeSections": ["videos"],
        "profileSorting": "latest",
        "resultsPerPage": 10,
        "excludePinnedPosts": False,
        "shouldDownloadVideos": False,
        "shouldDownloadCovers": False,
        "shouldDownloadAvatars": False,
    }

    raw_items = _apify_run(actor_id, run_input, token, timeout_secs=timeout_secs)
    results = []
    seen = set()

    for item in raw_items:
        if not isinstance(item, dict):
            continue

        meta = item.get("authorMeta") or item
        raw_h = meta.get("name") or meta.get("username") or item.get("name") or ""
        clean_h = str(raw_h).lstrip("@").strip()
        if not clean_h or clean_h in seen:
            continue
        seen.add(clean_h)

        display_name = meta.get("nickName") or meta.get("nickname") or item.get("nickname") or clean_h
        fans = int(meta.get("fans") or meta.get("followerCount") or item.get("followerCount") or 0)
        bio = meta.get("signature") or item.get("signature") or meta.get("bio") or ""
        avatar = meta.get("avatar") or meta.get("avatarLarger") or meta.get("avatarMedium") or ""

        # Extract public email from bio or meta
        contacts = _extract_contacts_from_text(bio)
        email = meta.get("email") or meta.get("publicEmail") or (contacts["emails"][0] if contacts["emails"] else "")

        digg_count = int(meta.get("digg") or meta.get("heart") or item.get("heart") or 0)
        video_count = int(meta.get("video") or item.get("videoCount") or 0)

        results.append({
            "handle": clean_h,
            "platform": "tiktok",
            "display_name": display_name,
            "follower_count": fans,
            "followerStr": f"{fans/1_000_000:.1f}M" if fans >= 1_000_000 else f"{fans/1_000:.0f}K" if fans >= 1000 else str(fans),
            "bio": bio,
            "avatar_url": avatar or f"https://ui-avatars.com/api/?name={clean_h}&background=06b6d4&color=fff",
            "email_public": email,
            "email": email,
            "profile_url": f"https://www.tiktok.com/@{clean_h}",
            "video_count": video_count,
            "raw_apify_data": item,
        })

    return results


def apify_scrape_instagram_profiles(handles: list, apify_token: str = None, timeout_secs: int = 90) -> list:
    """
    Run Apify Instagram Profile Scraper (apify/instagram-profile-scraper / dSCLg0C3YEZ83HzYX).
    """
    from app.config import settings
    token = apify_token or settings.APIFY_API_KEY
    if not token or not handles:
        return []

    actor_id = getattr(settings, "APIFY_INSTAGRAM_ACTOR", "dSCLg0C3YEZ83HzYX")
    cleaned_handles = [str(h).lstrip("@").strip() for h in handles if str(h).strip()]
    if not cleaned_handles:
        return []

    run_input = {
        "usernames": cleaned_handles,
        "includeAboutSection": False,
    }

    raw_items = _apify_run(actor_id, run_input, token, timeout_secs=timeout_secs)
    results = []
    seen = set()

    for item in raw_items:
        if not isinstance(item, dict):
            continue

        raw_h = item.get("username") or item.get("name") or ""
        clean_h = str(raw_h).lstrip("@").strip()
        if not clean_h or clean_h in seen:
            continue
        seen.add(clean_h)

        display_name = item.get("fullName") or item.get("name") or clean_h
        bio = item.get("biography") or item.get("bio") or ""
        followers = int(item.get("followersCount") or item.get("followers") or 0)
        avatar = item.get("profilePicUrlHD") or item.get("profilePicUrl") or ""

        # Extract email
        contacts = _extract_contacts_from_text(bio)
        email = (
            item.get("businessEmail")
            or item.get("publicEmail")
            or item.get("externalEmail")
            or (contacts["emails"][0] if contacts["emails"] else "")
        )

        posts_count = int(item.get("postsCount") or item.get("mediaCount") or 0)

        results.append({
            "handle": clean_h,
            "platform": "instagram",
            "display_name": display_name,
            "follower_count": followers,
            "followerStr": f"{followers/1_000_000:.1f}M" if followers >= 1_000_000 else f"{followers/1_000:.0f}K" if followers >= 1000 else str(followers),
            "bio": bio,
            "avatar_url": avatar or f"https://ui-avatars.com/api/?name={clean_h}&background=ec4899&color=fff",
            "email_public": email,
            "email": email,
            "profile_url": f"https://www.instagram.com/{clean_h}",
            "video_count": posts_count,
            "raw_apify_data": item,
        })

    return results


def apify_scrape_youtube_channels(channels: list, apify_token: str = None, timeout_secs: int = 90) -> list:
    """
    Run Apify YouTube Channel Scraper (streamers/youtube-channel-scraper / 67Q6fmd8iedTVcCwY).
    """
    from app.config import settings
    token = apify_token or settings.APIFY_API_KEY
    if not token or not channels:
        return []

    actor_id = getattr(settings, "APIFY_YOUTUBE_ACTOR", "67Q6fmd8iedTVcCwY")
    start_urls = []
    for ch in channels:
        if not ch:
            continue
        c_str = str(ch).strip()
        if c_str.startswith("http"):
            start_urls.append({"url": c_str})
        else:
            clean_h = c_str.lstrip("@").strip()
            start_urls.append({"url": f"https://www.youtube.com/@{clean_h}"})

    if not start_urls:
        return []

    run_input = {
        "startUrls": start_urls,
        "maxResults": 10,
        "maxResultsShorts": 5,
        "maxResultStreams": 0,
        "sortVideosBy": "NEWEST",
    }

    raw_items = _apify_run(actor_id, run_input, token, timeout_secs=timeout_secs)
    results = []
    seen = set()

    for item in raw_items:
        if not isinstance(item, dict):
            continue

        raw_url = item.get("channelUrl") or item.get("url") or ""
        clean_h = ""
        if "/@" in raw_url:
            clean_h = raw_url.split("/@")[-1].split("/")[0].split("?")[0].strip()
        elif raw_url:
            clean_h = raw_url.split("/")[-1].split("?")[0].lstrip("@").strip()

        if not clean_h:
            clean_h = str(item.get("channelName") or item.get("name") or "").replace(" ", "").lower()

        if not clean_h or clean_h in seen:
            continue
        seen.add(clean_h)

        display_name = item.get("channelName") or item.get("name") or clean_h
        bio = item.get("channelDescription") or item.get("description") or ""
        subs = _follower_count(item.get("numberOfSubscribers") or item.get("subscribers") or item.get("subscriberCount") or 0)
        avatar = item.get("channelAvatarUrl") or item.get("avatarUrl") or ""
        total_views = int(item.get("channelTotalViews") or 0)
        total_videos = int(item.get("channelTotalVideos") or 0)

        contacts = _extract_contacts_from_text(bio)
        email = item.get("email") or (contacts["emails"][0] if contacts["emails"] else "")

        results.append({
            "handle": clean_h,
            "platform": "youtube",
            "display_name": display_name,
            "follower_count": subs,
            "followerStr": f"{subs/1_000_000:.1f}M" if subs >= 1_000_000 else f"{subs/1_000:.0f}K" if subs >= 1000 else str(subs),
            "bio": bio,
            "avatar_url": avatar or f"https://ui-avatars.com/api/?name={clean_h}&background=ef4444&color=fff",
            "email_public": email,
            "email": email,
            "profile_url": f"https://www.youtube.com/@{clean_h}",
            "total_views": total_views,
            "video_count": total_videos,
            "raw_apify_data": item,
        })

    return results


def innertube_fetch_channel(handle_or_query: str) -> dict:
    """Fetch live YouTube channel profile data directly using YouTube's Innertube API."""
    clean = handle_or_query.lstrip("@").strip()
    url = "https://www.youtube.com/youtubei/v1/search?prettyPrint=false"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
    }
    payload = {
        "context": {
            "client": {
                "hl": "en",
                "gl": "US",
                "clientName": "WEB",
                "clientVersion": "2.20240401.01.00",
            }
        },
        "query": clean,
        "params": "EgIQAg%3D%3D",
    }
    try:
        r = httpx.post(url, json=payload, headers=headers, timeout=15)
        if r.status_code == 200:
            data = r.json()
            items = (
                data.get("contents", {})
                .get("twoColumnSearchResultsRenderer", {})
                .get("primaryContents", {})
                .get("sectionListRenderer", {})
                .get("contents", [])
            )
            for section in items:
                renderers = section.get("itemSectionRenderer", {}).get("contents", [])
                for item in renderers:
                    ch = item.get("channelRenderer")
                    if ch:
                        title = ch.get("title", {}).get("simpleText") or "".join(r.get("text", "") for r in ch.get("title", {}).get("runs", []))
                        canonical = ch.get("canonicalBaseUrl", "").lstrip("/").lstrip("@")
                        handle_tag = ch.get("subscriberCountText", {}).get("simpleText") or ""
                        
                        sub_text = ch.get("videoCountText", {}).get("simpleText") or ""
                        if "subscriber" not in sub_text.lower():
                            sub_text = ch.get("subscriberCountText", {}).get("simpleText") or ""
                            
                        clean_handle = canonical
                        if not clean_handle and handle_tag.startswith("@"):
                            clean_handle = handle_tag.lstrip("@")
                        if not clean_handle:
                            clean_handle = clean
                            
                        thumbs = ch.get("thumbnail", {}).get("thumbnails", [])
                        avatar = thumbs[-1].get("url") if thumbs else ""
                        if avatar.startswith("//"):
                            avatar = "https:" + avatar
                            
                        desc = "".join(r.get("text", "") for r in ch.get("descriptionSnippet", {}).get("runs", []))
                        emails = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", desc)
                        
                        return {
                            "handle": clean_handle,
                            "platform": "youtube",
                            "display_name": title or clean_handle,
                            "bio": desc,
                            "follower_count": _num(sub_text),
                            "avatar_url": avatar,
                            "email_public": emails[0] if emails else "",
                            "profile_url": f"https://www.youtube.com/@{clean_handle}",
                            "niche": ["Tech"],
                            "website": "",
                            "social_links": [],
                        }
    except Exception as e:
        print(f"[YouTube Innertube] Error: {e}")
    return {}


def scrape_youtube(handle: str) -> dict:
    """
    Scrape a YouTube channel by @handle or URL.
    Uses Apify when key is configured, falls back to direct Innertube/HTML scrape.
    """
    from app.config import settings
    handle = handle.strip()
    clean_h = handle.lstrip("@").strip()
    if clean_h.startswith("UC") and len(clean_h) == 24:
        url = f"https://www.youtube.com/channel/{clean_h}"
    elif clean_h.startswith(("channel/", "c/", "user/", "@")):
        url = f"https://www.youtube.com/{clean_h}"
    else:
        url = f"https://www.youtube.com/@{clean_h}"

    result = {
        "handle": clean_h,
        "platform": "youtube",
        "profile_url": url,
        "display_name": clean_h,
        "bio": "",
        "avatar_url": "",
        "follower_count": 0,
        "banner_url": "",
        "niche": [],
        "email_public": "",
        "website": "",
        "social_links": [],
    }

    # Step 1: Live Profile Extraction via Innertube API (fast & accurate live stats/avatar)
    tube_res = innertube_fetch_channel(clean_h)
    if tube_res:
        result.update(tube_res)

    # Step 2: Direct scrape fallback if Innertube didn't return profile stats
    if not result.get("follower_count"):
        try:
            r = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
            html = r.text
            m = re.search(r"var ytInitialData\s*=\s*(\{.+?\});\s*(?:var|</script)", html, re.DOTALL)
            if m:
                data = json.loads(m.group(1))
                direct_res = _extract_channel_from_initial_data(data, clean_h)
                if direct_res:
                    result.update(direct_res)
        except Exception as e:
            print(f"[YouTube Scrape] Direct HTML fallback error: {e}")



    # Guess niche from bio keywords
    bio_lower = (result.get("bio") or "").lower()
    niche_map = {
        "fitness": ["fitness", "workout", "gym", "health", "exercise"],
        "cooking": ["cook", "recipe", "food", "kitchen", "chef"],
        "tech": ["tech", "software", "coding", "developer", "programming", "ai", "automation"],
        "finance": ["finance", "invest", "money", "wealth", "stock"],
        "gaming": ["gaming", "gamer", "twitch", "esport", "playthrough"],
        "beauty": ["beauty", "makeup", "skincare", "cosmetic"],
        "travel": ["travel", "explore", "adventure", "nomad"],
        "education": ["learn", "teach", "tutorial", "course", "education"],
        "lifestyle": ["lifestyle", "vlog", "daily", "routine"],
        "business": ["entrepreneur", "business", "startup", "founder"],
    }
    for tag, keywords in niche_map.items():
        if any(k in bio_lower for k in keywords) and tag not in result["niche"]:
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
            actor_id = getattr(
                settings,
                "APIFY_INSTAGRAM_EMAIL_ACTOR",
                "scrapers-hub~instagram-profile-email-scraper",
            )
            items = _apify_run(
                actor_id,
                {"usernames": [handle]},
                settings.APIFY_API_KEY,
            )
            if items:
                d = items[0]
                result["display_name"]  = d.get("fullName") or d.get("full_name") or d.get("username") or handle
                result["bio"]           = d.get("biography") or d.get("bio") or ""
                result["follower_count"] = _follower_count(
                    d.get("followersCount") or d.get("followers_count") or d.get("followedBy")
                )
                result["avatar_url"]    = d.get("profilePicUrlHD") or d.get("profilePicUrl") or d.get("profile_pic_url") or ""
                result["website"]       = d.get("externalUrl") or d.get("websiteUrl") or d.get("website") or ""
                result["email_public"] = (
                    d.get("email")
                    or d.get("publicEmail")
                    or d.get("businessEmail")
                    or d.get("contactEmail")
                    or d.get("externalEmail")
                    or d.get("email_public")
                    or ""
                )
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
                result["follower_count"] = _follower_count(
                    d.get("followerCount") or d.get("authorMeta", {}).get("fans")
                )
                raw_av = d.get("avatarLarger") or d.get("avatarMedium") or d.get("authorMeta", {}).get("avatar") or ""
                result["avatar_url"]    = _clean_url(raw_av)
                result["email_public"]  = (
                    d.get("email")
                    or d.get("publicEmail")
                    or d.get("authorMeta", {}).get("email")
                    or d.get("authorMeta", {}).get("publicEmail")
                    or ""
                )
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
                    result["follower_count"] = _follower_count(
                        user.get("followers") or user.get("followersCount")
                    )
                    avatar_raw = user.get("profilePicture") or user.get("profile_image_url_https") or user.get("avatarUrl") or ""
                    result["avatar_url"] = avatar_raw.replace("_normal", "_400x400") if avatar_raw else ""
            return result
        except Exception as e:
            result["error"] = f"Apify: {e}"
    return result


def _extract_contacts_from_text(text: str) -> dict:
    """
    Extract Instagram handles from text. Emails must come directly from structured APIs.
    """
    contacts = {"emails": [], "instagram": None}
    if not text:
        return contacts

    # Extract Instagram handles
    ig_patterns = [
        r"instagram\.com/([a-zA-Z0-9_.]+)",
        r"(?:ig|insta|instagram)\s*[:\-]?\s*@?([a-zA-Z0-9_.]{2,30})",
    ]
    for pat in ig_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            contacts["instagram"] = m.group(1).strip().rstrip("/")
            break

    return contacts


def _direct_youtube_search(query: str, limit: int = 5) -> list[dict]:
    """
    Search YouTube directly via Innertube API or HTML scraping (no API key needed).
    Returns real channel titles, handles, actual subscriber counts, avatars, and bios.
    """
    # ── Try Innertube search first (fast, structured, 100% accurate subscriber counts) ──
    try:
        url = "https://www.youtube.com/youtubei/v1/search?prettyPrint=false"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Content-Type": "application/json",
        }
        payload = {
            "context": {
                "client": {
                    "hl": "en",
                    "gl": "US",
                    "clientName": "WEB",
                    "clientVersion": "2.20240401.01.00",
                }
            },
            "query": query,
            "params": "EgIQAg%3D%3D",
        }
        r = httpx.post(url, json=payload, headers=headers, timeout=15)
        if r.status_code == 200:
            data = r.json()
            items = (
                data.get("contents", {})
                .get("twoColumnSearchResultsRenderer", {})
                .get("primaryContents", {})
                .get("sectionListRenderer", {})
                .get("contents", [])
            )
            tube_results = []
            seen = set()
            for section in items:
                renderers = section.get("itemSectionRenderer", {}).get("contents", [])
                for item in renderers:
                    ch = item.get("channelRenderer")
                    if ch:
                        title = ch.get("title", {}).get("simpleText") or "".join(r.get("text", "") for r in ch.get("title", {}).get("runs", []))
                        canonical = ch.get("canonicalBaseUrl", "").lstrip("/").lstrip("@")
                        handle_tag = ch.get("subscriberCountText", {}).get("simpleText") or ""
                        
                        sub_text = ch.get("videoCountText", {}).get("simpleText") or ""
                        if "subscriber" not in sub_text.lower():
                            sub_text = ch.get("subscriberCountText", {}).get("simpleText") or ""
                            
                        clean_handle = canonical
                        if not clean_handle and handle_tag.startswith("@"):
                            clean_handle = handle_tag.lstrip("@")
                        if not clean_handle:
                            clean_handle = title.replace(" ", "").lower()
                            
                        if clean_handle in seen:
                            continue
                        seen.add(clean_handle)
                        
                        thumbs = ch.get("thumbnail", {}).get("thumbnails", [])
                        avatar = thumbs[-1].get("url") if thumbs else ""
                        if avatar.startswith("//"):
                            avatar = "https:" + avatar
                            
                        desc = "".join(r.get("text", "") for r in ch.get("descriptionSnippet", {}).get("runs", []))
                        contacts = _extract_contacts_from_text(desc)
                        
                        tube_results.append({
                            "handle": clean_handle,
                            "platform": "youtube",
                            "display_name": title or clean_handle,
                            "bio": desc,
                            "follower_count": _num(sub_text),
                            "avatar_url": avatar,
                            "email_public": contacts["emails"][0] if contacts["emails"] else "",
                            "instagram": contacts["instagram"] or "",
                            "profile_url": f"https://www.youtube.com/@{clean_handle}",
                        })
                        if len(tube_results) >= limit:
                            break
                if len(tube_results) >= limit:
                    break
            if tube_results:
                return tube_results
    except Exception as e:
        print(f"[YouTube Search] Innertube search error: {e}")

    import urllib.parse
    search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}&sp=EgIQAg%3D%3D"
    # sp=EgIQAg%3D%3D filters for "Channel" type results

    try:
        r = httpx.get(search_url, headers=HEADERS, timeout=15, follow_redirects=True)
        html = r.text
    except Exception as e:
        print(f"[YouTube Search] HTTP error: {e}")
        return []

    # Extract ytInitialData JSON blob
    m = re.search(r"var ytInitialData\s*=\s*(\{.+?\});\s*(?:var|</script)", html, re.DOTALL)
    if not m:
        print("[YouTube Search] Could not find ytInitialData in HTML")
        return []

    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        print("[YouTube Search] Failed to parse ytInitialData JSON")
        return []

    results = []
    seen_handles = set()

    # Navigate the nested YouTube data structure to find channel renderers
    try:
        contents = (
            data.get("contents", {})
            .get("twoColumnSearchResultsRenderer", {})
            .get("primaryContents", {})
            .get("sectionListRenderer", {})
            .get("contents", [])
        )
        for section in contents:
            items = (
                section.get("itemSectionRenderer", {})
                .get("contents", [])
            )
            for item in items:
                renderer = item.get("channelRenderer")
                if not renderer:
                    continue

                channel_id = renderer.get("channelId", "")
                # Extract handle from navigationEndpoint or canonicalBaseUrl
                handle = ""
                canonical = renderer.get("canonicalBaseUrl", "")
                if canonical:
                    handle = canonical.lstrip("/").lstrip("@")
                # Also try navigationEndpoint for custom URL
                if not handle:
                    try:
                        nav_url = renderer.get("navigationEndpoint", {}).get("browseEndpoint", {}).get("canonicalBaseUrl", "")
                        if nav_url:
                            handle = nav_url.lstrip("/").lstrip("@")
                    except Exception:
                        pass
                if not handle:
                    handle = channel_id

                if not handle or handle in seen_handles:
                    continue
                seen_handles.add(handle)

                display_name = ""
                title_obj = renderer.get("title", {})
                if isinstance(title_obj, dict):
                    display_name = title_obj.get("simpleText", "")
                    if not display_name:
                        runs = title_obj.get("runs", [])
                        display_name = "".join(r.get("text", "") for r in runs)
                display_name = display_name or handle

                # Subscriber count
                sub_text = ""
                sub_obj = renderer.get("subscriberCountText", {})
                if isinstance(sub_obj, dict):
                    sub_text = sub_obj.get("simpleText", "")
                    if not sub_text:
                        runs = sub_obj.get("runs", [])
                        sub_text = "".join(r.get("text", "") for r in runs)
                subs = _num(sub_text)

                # Description snippet
                desc_text = ""
                desc_obj = renderer.get("descriptionSnippet", {})
                if isinstance(desc_obj, dict):
                    runs = desc_obj.get("runs", [])
                    desc_text = "".join(r.get("text", "") for r in runs)

                # Avatar
                avatar_url = ""
                thumbs = renderer.get("thumbnail", {}).get("thumbnails", [])
                if thumbs:
                    avatar_url = thumbs[-1].get("url", "")
                    if avatar_url.startswith("//"):
                        avatar_url = "https:" + avatar_url

                # Video count text (for recency heuristic)
                video_count_text = ""
                vc_obj = renderer.get("videoCountText", {})
                if isinstance(vc_obj, dict):
                    video_count_text = vc_obj.get("simpleText", "")
                    if not video_count_text:
                        runs = vc_obj.get("runs", [])
                        video_count_text = "".join(r.get("text", "") for r in runs)

                # Extract contacts from description
                contacts = _extract_contacts_from_text(desc_text)
                email = contacts["emails"][0] if contacts["emails"] else ""

                results.append({
                    "handle": handle,
                    "channel_id": channel_id,
                    "platform": "youtube",
                    "display_name": display_name,
                    "bio": desc_text,
                    "follower_count": subs,
                    "avatar_url": avatar_url,
                    "email_public": email,
                    "instagram": contacts["instagram"] or "",
                    "profile_url": f"https://www.youtube.com/channel/{channel_id}" if handle.startswith("UC") else f"https://www.youtube.com/@{handle}",
                    "video_count_text": video_count_text,
                })

                if len(results) >= limit:
                    break
            if len(results) >= limit:
                break
    except Exception as e:
        print(f"[YouTube Search] Parse error: {e}")

    return results


NICHE_SEARCH_EXPANSIONS = {
    "tech": [
        "Software Engineering", "Full Stack Developer", "Python AI Apps", "SaaS Founder Build", 
        "Web Development Nextjs", "Indie Hacker Software", "DevOps Cloud", "Coding Tutorial", 
        "Tech Reviews Setup", "AI Tools Workflow", "Productivity Software", "Frontend React", 
        "Data Science Machine Learning", "Mobile App Flutter", "Cybersecurity Tools", "Linux System Architecture"
    ],
    "fitness": [
        "Fitness Coach Workout", "Bodybuilding Science", "Nutrition Diet Meal Prep", 
        "Calisthenics Training", "Home Gym Routines", "Strength Conditioning", "Mobility Rehab", "Hypertrophy Training"
    ],
    "finance": [
        "Personal Finance Investing", "SaaS Business Revenue", "Stock Market Trading", 
        "Real Estate Investing", "Crypto Blockchain", "E-commerce Amazon FBA", "Financial Independence FIRE", "Dividend Investing"
    ],
    "business": [
        "Startup Founder Journey", "Solo Founder SaaS", "Marketing Growth Hacks", 
        "Sales Funnels B2B", "Digital Agency Scaling", "NoCode Automation", "Product Management", "Micro SaaS"
    ],
    "creator": [
        "Content Creation Workflow", "Video Editing Premiere DaVinci", "Podcast Production", 
        "YouTube Growth Strategy", "Camera Gear Studio", "Graphic Design Brand", "Storytelling Filmmaking"
    ],
    "gaming": [
        "Game Development Unity Unreal", "Indie Game Studio", "Gaming Hardware Setup", 
        "Game Design Mechanics", "Pixel Art Animation", "Esports Analytics", "Godot Engine Devlog"
    ],
    "design": [
        "UI UX Design Figma", "Webflow Website Design", "Product Design Systems", 
        "3D Motion Blender", "Brand Identity Typography", "Design Freelancing", "Motion Graphics After Effects"
    ],
}


def search_youtube_channels(query: str, limit: int = 5, min_followers: int = 0, max_followers: int = 0) -> list[dict]:
    """
    Search YouTube for creators matching niche keywords with dynamic query expansion & randomized sampling.
    """
    import random
    from app.config import settings

    raw_channels = []
    q_lower = query.lower().strip()

    # Identify matching niche categories
    matched_expansions = []
    for cat, terms in NICHE_SEARCH_EXPANSIONS.items():
        if cat in q_lower:
            matched_expansions.extend(terms)
    
    if not matched_expansions:
        # Default to splitting query or fallback to tech/business
        matched_expansions = [kw.strip() for kw in query.replace(",", " ").split() if kw.strip()] or NICHE_SEARCH_EXPANSIONS["tech"]

    # Expand search terms pool
    all_terms = list(matched_expansions)
    random.shuffle(all_terms)
    # Add variations to ensure deep candidate pool
    if len(all_terms) < 12:
        all_terms.extend([f"{t} expert" for t in matched_expansions[:4]])
        all_terms.extend([f"{t} pro" for t in matched_expansions[:4]])
        all_terms.extend([f"{t} setup" for t in matched_expansions[:4]])

    modifiers = ["channel", "creator", "tutorials", "review", "build", "vlog", "guide", "software"]

    # ── Step 1: Fast direct YouTube search with dynamic query loops ───────────
    seen = set()
    filtered = []

    for term in all_terms:
        mod = random.choice(modifiers)
        search_query = f"{term} {mod}"
        found = _direct_youtube_search(search_query, limit=30)
        
        for ch in found:
            key = ch["handle"].lower()
            if key in seen:
                continue
            seen.add(key)
            
            subs = ch.get("follower_count", 0)
            # Strict follower tier filtering (100k - 1M)
            if min_followers and subs < min_followers:
                continue
            if max_followers and subs > max_followers:
                continue
            
            ch["niche"] = [term]
            filtered.append(ch)
            
        if len(filtered) >= limit * 3:
            break

    # If still need more candidates and strict filter returned few, run broader search queries
    if len(filtered) < limit:
        for extra_q in [f"{query} creator channel", f"{query} full tutorial", f"{query} podcast"]:
            found = _direct_youtube_search(extra_q, limit=30)
            for ch in found:
                key = ch["handle"].lower()
                if key in seen:
                    continue
                seen.add(key)
                subs = ch.get("follower_count", 0)
                if min_followers and subs < min_followers:
                    continue
                if max_followers and subs > max_followers:
                    continue
                ch["niche"] = [query]
                filtered.append(ch)
            if len(filtered) >= limit * 2:
                break

    if not filtered:
        return []

    # ── Step 2: Randomize candidate order for variety ────────────────────────
    random.shuffle(filtered)

    # ── Step 4: Enrich channels via individual channel page scrape ────────
    for ch in filtered[:limit]:
        needs_enrichment = (
            not ch.get("email_public")
            or not ch.get("follower_count")
            or ch.get("handle", "").startswith("UC")
        )
        if needs_enrichment and ch.get("handle"):
            try:
                # Use channel_id path for UC handles, @handle for others
                lookup = ch.get("channel_id") or ch["handle"] if ch["handle"].startswith("UC") else ch["handle"]
                profile = scrape_youtube(lookup)
                if profile and "error" not in profile:
                    # Enrich bio & contacts
                    if profile.get("bio"):
                        contacts = _extract_contacts_from_text(profile["bio"])
                        if contacts["emails"] and not ch.get("email_public"):
                            ch["email_public"] = contacts["emails"][0]
                        if contacts["instagram"] and not ch.get("instagram"):
                            ch["instagram"] = contacts["instagram"]
                        if not ch.get("bio"):
                            ch["bio"] = profile["bio"]
                    # Enrich avatar
                    if not ch.get("avatar_url") and profile.get("avatar_url"):
                        ch["avatar_url"] = profile["avatar_url"]
                    # Enrich subscriber count
                    if profile.get("follower_count") and (not ch.get("follower_count") or ch["follower_count"] == 0):
                        ch["follower_count"] = profile["follower_count"]
                    # Derive better handle from display name if still UC-style
                    if ch["handle"].startswith("UC") and profile.get("display_name"):
                        clean = profile["display_name"].strip().replace(" ", "").lower()
                        clean = re.sub(r"[^a-z0-9_]", "", clean)
                        if clean and len(clean) >= 3:
                            ch["handle"] = clean
                            ch["profile_url"] = f"https://www.youtube.com/@{clean}"
            except Exception:
                pass

    # ── Step 5: Build final results ─────────────────────────────────────────
    results = []
    niche_label = matched_expansions[0] if matched_expansions else query
    for ch in filtered[:limit]:
        results.append({
            "handle": ch["handle"],
            "platform": "youtube",
            "display_name": ch.get("display_name") or ch["handle"],
            "bio": ch.get("bio", ""),
            "follower_count": ch.get("follower_count", 0),
            "avatar_url": ch.get("avatar_url", ""),
            "email_public": ch.get("email_public", ""),
            "instagram": ch.get("instagram", ""),
            "profile_url": ch.get("profile_url", f"https://www.youtube.com/@{ch['handle']}"),
            "niche": ch.get("niche", [niche_label]),
        })

    print(f"[YouTube Search] Final qualified creators ({len(results)}):")
    for r in results:
        subs = r["follower_count"]
        subs_str = f"{subs/1_000_000:.1f}M" if subs >= 1_000_000 else f"{subs/1_000:.0f}K" if subs >= 1_000 else str(subs)
        safe_name = r["display_name"].encode("ascii", "ignore").decode("ascii")
        print(f"  - @{r['handle']} ({safe_name}) | {subs_str} subs | email: {r['email_public'] or 'none'}")

    return results


def scrape_profile(platform: str, handle: str, api_key: str = None, apify_token: str = None) -> dict:
    """
    Dispatch to the configured Apify scraper, with direct public-page fallback.
    """
    from app.config import settings
    token = apify_token or settings.APIFY_API_KEY
    clean_h = handle.lstrip("@").strip().strip("/")
    p = platform.lower().strip()

    # If full URL passed, extract handle & platform
    if "youtube.com/" in handle:
        p = "youtube"
        m = re.search(r"youtube\.com/(@?[^/?&\s]+)", handle)
        if m:
            clean_h = m.group(1).lstrip("@")
    elif "instagram.com/" in handle:
        p = "instagram"
        m = re.search(r"instagram\.com/([^/?&\s]+)", handle)
        if m:
            clean_h = m.group(1)
    elif "tiktok.com/" in handle:
        p = "tiktok"
        m = re.search(r"tiktok\.com/(@?[^/?&\s]+)", handle)
        if m:
            clean_h = m.group(1).lstrip("@")
    elif "twitter.com/" in handle or "x.com/" in handle:
        p = "twitter"
        m = re.search(r"(?:twitter|x)\.com/([^/?&\s]+)", handle)
        if m:
            clean_h = m.group(1)

    # 1. Primary: Apify Actors for Platform Scraping (TikTok, Instagram, YouTube)
    if token:
        try:
            if p == "youtube":
                res = apify_scrape_youtube_channels([clean_h], token, timeout_secs=60)
                if res:
                    return res[0]
            elif p == "instagram":
                res = apify_scrape_instagram_profiles([clean_h], token, timeout_secs=60)
                if res:
                    return res[0]
            elif p == "tiktok":
                res = apify_scrape_tiktok_profiles([clean_h], token, timeout_secs=60)
                if res:
                    return res[0]
            elif p == "twitter":
                res = _apify_run("apify~twitter-scraper", {"twitterHandles": [clean_h], "maxItems": 1}, token, timeout_secs=45)
                if res and len(res) > 0:
                    item = res[0]
                    user = item.get("author") or item.get("user") or item
                    bio = user.get("description") or user.get("bio") or ""
                    email_pub = (
                        user.get("email")
                        or user.get("publicEmail")
                        or item.get("email")
                        or ""
                    )
                    return {
                        "handle": clean_h,
                        "platform": "twitter",
                        "display_name": user.get("name") or clean_h,
                        "bio": bio,
                        "follower_count": _follower_count(_first_value(
                            user, "followers", "followersCount", "followerCount", "followers_count"
                        )),
                        "avatar_url": user.get("profilePicture") or user.get("profile_image_url_https") or "",
                        "email_public": email_pub,
                        "profile_url": f"https://x.com/{clean_h}",
                        "raw_apify_data": item,
                    }
        except Exception as e:
            logger.warning(f"[Apify Scraper] Fallback to direct scrapers for {p} @{clean_h}: {e}")

    # 2. Direct Fast Scrapers
    if p == "youtube":
        return scrape_youtube(clean_h)
    elif p == "instagram":
        return scrape_instagram(clean_h)
    elif p == "tiktok":
        return scrape_tiktok(clean_h)
    elif p == "twitter":
        return scrape_twitter(clean_h)
    else:
        return {"error": f"No scraper for platform: {p}", "handle": clean_h, "platform": p}


