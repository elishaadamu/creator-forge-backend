"""
Hunter.io Email Discovery & Verification Service
Enables finding verified business emails for creators using their name and website domain.
"""
import re
import logging
import httpx
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

def extract_domain(url_or_text: str) -> str:
    """Extract clean domain from a URL or email address."""
    if not url_or_text:
        return ""
    text = str(url_or_text).strip()
    if "@" in text and not text.startswith("http"):
        return text.split("@")[-1].lower()
    
    if not text.startswith(("http://", "https://")):
        text = "https://" + text
    try:
        parsed = urlparse(text)
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        # Exclude social media root domains from Hunter.io corporate email search
        excluded_domains = [
            "youtube.com", "instagram.com", "tiktok.com", "twitter.com",
            "x.com", "facebook.com", "linkedin.com", "linktr.ee",
            "beacons.ai", "stan.store", "hoo.be", "snipfeed.co"
        ]
        if any(netloc == exc or netloc.endswith(f".{exc}") for exc in excluded_domains):
            return ""
        return netloc
    except Exception:
        return ""


def hunter_find_email(
    full_name: str = None,
    domain: str = None,
    hunter_api_key: str = None,
    timeout_secs: int = 15
) -> str:
    """
    Query Hunter.io Email Finder API (https://api.hunter.io/v2/email-finder).
    Finds the verified email of a creator given their name and personal domain.
    """
    from app.config import settings
    api_key = hunter_api_key or getattr(settings, "HUNTER_API_KEY", "")
    if not api_key:
        return ""

    clean_domain = extract_domain(domain)
    if not clean_domain:
        return ""

    first_name = ""
    last_name = ""
    if full_name:
        parts = full_name.strip().split()
        if len(parts) == 1:
            first_name = parts[0]
        elif len(parts) >= 2:
            first_name = parts[0]
            last_name = " ".join(parts[1:])

    url = "https://api.hunter.io/v2/email-finder"
    params = {
        "domain": clean_domain,
        "api_key": api_key,
    }
    if full_name:
        params["full_name"] = full_name
    elif first_name and last_name:
        params["first_name"] = first_name
        params["last_name"] = last_name

    try:
        r = httpx.get(url, params=params, timeout=timeout_secs)
        if r.status_code == 200:
            data = r.json().get("data", {})
            email = data.get("email") or ""
            score = data.get("score", 0)
            print(f"[Hunter.io] Found email: {email} (confidence: {score}%) for domain={clean_domain}")
            return email
        elif r.status_code == 404:
            # Fallback to domain search to see all emails associated with this domain
            ds_url = "https://api.hunter.io/v2/domain-search"
            ds_r = httpx.get(ds_url, params={"domain": clean_domain, "api_key": api_key, "limit": 3}, timeout=timeout_secs)
            if ds_r.status_code == 200:
                emails = ds_r.json().get("data", {}).get("emails", [])
                if emails:
                    top_email = emails[0].get("value") or ""
                    print(f"[Hunter.io Domain Search] Found email: {top_email} for domain={clean_domain}")
                    return top_email
    except Exception as e:
        logger.warning(f"[Hunter.io] Email Finder error for domain={clean_domain}: {e}")

    return ""


def hunter_verify_email(email: str, hunter_api_key: str = None, timeout_secs: int = 15) -> dict:
    """
    Verify an email address via Hunter.io Email Verifier API (https://api.hunter.io/v2/email-verifier).
    """
    from app.config import settings
    api_key = hunter_api_key or getattr(settings, "HUNTER_API_KEY", "")
    if not api_key or not email:
        return {"email": email, "status": "unknown", "score": 0}

    url = "https://api.hunter.io/v2/email-verifier"
    try:
        r = httpx.get(url, params={"email": email, "api_key": api_key}, timeout=timeout_secs)
        if r.status_code == 200:
            data = r.json().get("data", {})
            status = data.get("status") or "unknown"
            score = data.get("score") or 0
            return {
                "email": email,
                "status": status,
                "score": score,
                "is_deliverable": status in ("valid", "accept_all"),
                "regexp": data.get("regexp", True),
                "gibberish": data.get("gibberish", False),
                "disposable": data.get("disposable", False),
                "webmail": data.get("webmail", False),
                "mx_records": data.get("mx_records", True),
                "smtp_check": data.get("smtp_check", True),
            }
    except Exception as e:
        logger.warning(f"[Hunter.io] Email Verifier error for {email}: {e}")

    return {"email": email, "status": "unknown", "score": 0}
