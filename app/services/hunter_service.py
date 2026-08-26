"""
Hunter.io API Service — Email Finder, Domain Search & Email Verifier integration.
Pipeline: Apify / Discovery → Hunter.io (Finder, Domain Search & Verifier) → Outreach Sender.
"""
import logging
import urllib.parse
from typing import Optional, Dict, Any, List
import httpx

from app.config import settings

logger = logging.getLogger(__name__)

HUNTER_BASE_URL = "https://api.hunter.io/v2"
DELIVERABLE_STATUSES = {"valid", "accept_all", "webmail"}


def _get_api_key(api_key: Optional[str] = None) -> str:
    return (api_key or settings.HUNTER_API_KEY or "").strip()


def domain_search(
    domain: Optional[str] = None,
    company: Optional[str] = None,
    api_key: Optional[str] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    """
    Calls Hunter.io Domain Search API:
    GET https://api.hunter.io/v2/domain-search
    Returns public/business emails associated with a domain or company.
    """
    key = _get_api_key(api_key)
    if not key:
        return {"success": False, "error": "HUNTER_API_KEY is not configured", "emails": []}

    params = {"api_key": key, "limit": max(1, min(50, limit))}
    if domain:
        clean_dom = domain.strip().replace("http://", "").replace("https://", "").split("/")[0]
        params["domain"] = clean_dom
    elif company:
        params["company"] = company.strip()
    else:
        return {"success": False, "error": "Missing domain or company parameter", "emails": []}

    url = f"{HUNTER_BASE_URL}/domain-search"
    try:
        logger.info(f"[Hunter.io] Domain search for target='{params.get('domain') or params.get('company')}'")
        r = httpx.get(url, params=params, timeout=15.0)
        if r.status_code == 200:
            res_json = r.json()
            data = res_json.get("data") or {}
            raw_emails = data.get("emails") or []
            emails = []
            for em in raw_emails:
                emails.append({
                    "email": em.get("value"),
                    "type": em.get("type"),
                    "confidence": em.get("confidence", 0),
                    "first_name": em.get("first_name"),
                    "last_name": em.get("last_name"),
                    "position": em.get("position"),
                    "sources": em.get("sources", []),
                })
            return {
                "success": True,
                "domain": data.get("domain"),
                "organization": data.get("organization"),
                "pattern": data.get("pattern"),
                "emails": emails,
                "raw": data,
            }
        else:
            logger.warning(f"[Hunter.io] Domain search returned {r.status_code}: {r.text}")
            return {"success": False, "status_code": r.status_code, "error": r.text, "emails": []}
    except Exception as e:
        logger.error(f"[Hunter.io] Domain search exception: {e}")
        return {"success": False, "error": str(e), "emails": []}


def find_email(
    full_name: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    domain: Optional[str] = None,
    company: Optional[str] = None,
    linkedin_handle: Optional[str] = None,
    api_key: Optional[str] = None,
    max_duration: int = 10,
) -> Dict[str, Any]:
    """
    Calls Hunter.io Email Finder API:
    GET https://api.hunter.io/v2/email-finder
    Fallback to Domain Search if full_name cannot be split or if Email Finder returns 400.
    """
    key = _get_api_key(api_key)
    if not key:
        return {"success": False, "error": "HUNTER_API_KEY is not configured", "data": None}

    clean_domain = None
    if domain:
        clean_domain = domain.strip().replace("http://", "").replace("https://", "").split("/")[0]
        # Ignore generic social media or aggregators
        if any(d in clean_domain for d in ["youtube.com", "instagram.com", "tiktok.com", "twitter.com", "x.com", "linktr.ee", "twitch.tv"]):
            clean_domain = None

    clean_company = company.strip().lstrip("@") if company else None
    clean_full_name = full_name.strip() if full_name else None

    # Check if full_name looks like a person's first+last name (has space, 2-3 words, no special chars)
    is_person_name = False
    if clean_full_name:
        parts = [p for p in clean_full_name.split() if p]
        if 2 <= len(parts) <= 3 and not any(w.lower() in ["official", "channel", "tutorials", "media", "studios", "team", "inc", "ltd", "corp", "tv", "hq", "podcast", "code", "learn"] for w in parts):
            is_person_name = True
    elif first_name and last_name:
        is_person_name = True

    # 1. If we have a plausible person name, try Hunter Email Finder
    if is_person_name and (clean_domain or clean_company or linkedin_handle):
        params = {"api_key": key, "max_duration": max(3, min(20, max_duration))}
        if clean_domain:
            params["domain"] = clean_domain
        elif clean_company:
            params["company"] = clean_company
        elif linkedin_handle:
            params["linkedin_handle"] = linkedin_handle.strip().lstrip("@")

        if clean_full_name:
            params["full_name"] = clean_full_name
        else:
            if first_name: params["first_name"] = first_name.strip()
            if last_name: params["last_name"] = last_name.strip()

        url = f"{HUNTER_BASE_URL}/email-finder"
        try:
            logger.info(f"[Hunter.io] Searching email for name='{params.get('full_name') or params.get('first_name')}' target='{params.get('domain') or params.get('company')}'")
            r = httpx.get(url, params=params, timeout=float(max_duration + 5))
            if r.status_code == 200:
                res_json = r.json()
                data = res_json.get("data") or {}
                email = data.get("email")
                if email:
                    score = data.get("score", 0)
                    verification = data.get("verification") or {}
                    logger.info(f"[Hunter.io] Found email: {email} (Score: {score}, Status: {verification.get('status')})")
                    return {
                        "success": True,
                        "email": email,
                        "score": score,
                        "verification_status": verification.get("status"),
                        "deliverable": verification.get("status") in DELIVERABLE_STATUSES,
                        "first_name": data.get("first_name"),
                        "last_name": data.get("last_name"),
                        "position": data.get("position"),
                        "company": data.get("company"),
                        "raw": data,
                    }
        except Exception as e:
            logger.warning(f"[Hunter.io] Email Finder exception: {e}")

    # 2. Fallback to Domain Search if Email Finder yielded nothing or if target is brand/channel/company
    if clean_domain or clean_company:
        logger.info(f"[Hunter.io] Attempting Domain Search fallback for domain='{clean_domain}', company='{clean_company}'")
        ds_res = domain_search(domain=clean_domain, company=clean_company, api_key=key, limit=10)
        emails = ds_res.get("emails") or []
        if emails:
            # Score emails: prefer generic contact/support/business emails or highest confidence personal
            best = max(emails, key=lambda x: (15 if x.get("type") == "generic" else 0) + (x.get("confidence") or 0))
            best_email = best.get("email")
            if best_email:
                # Verify deliverability via Hunter Verifier
                v_res = verify_email(best_email, api_key=key)
                score = v_res.get("score") if v_res.get("success") else best.get("confidence", 80)
                status = v_res.get("status") if v_res.get("success") else "unknown"
                logger.info(f"[Hunter.io] Domain Search matched best email: {best_email} (Confidence/Score: {score}, Status: {status})")
                return {
                    "success": True,
                    "email": best_email,
                    "score": score,
                    "verification_status": status,
                    "deliverable": status in DELIVERABLE_STATUSES,
                    "first_name": best.get("first_name"),
                    "last_name": best.get("last_name"),
                    "position": best.get("position"),
                    "company": ds_res.get("organization") or clean_company,
                    "source": "domain_search",
                    "raw": best,
                }

    return {"success": False, "error": "No verified email found for this domain or company via Hunter.io", "data": None}


def verify_email(email: str, api_key: Optional[str] = None) -> Dict[str, Any]:
    """
    Calls Hunter.io Email Verifier API:
    GET https://api.hunter.io/v2/email-verifier
    """
    key = _get_api_key(api_key)
    if not key:
        return {"success": False, "error": "HUNTER_API_KEY is not configured", "data": None}

    clean_email = email.strip()
    if not clean_email or "@" not in clean_email:
        return {"success": False, "error": "Invalid email address", "data": None}

    url = f"{HUNTER_BASE_URL}/email-verifier"
    params = {"email": clean_email, "api_key": key}

    try:
        logger.info(f"[Hunter.io] Verifying email: {clean_email}")
        r = httpx.get(url, params=params, timeout=15.0)
        if r.status_code == 200:
            res_json = r.json()
            data = res_json.get("data") or {}
            status = data.get("status")
            score = data.get("score", 0)
            logger.info(f"[Hunter.io] Verification result for {clean_email}: status={status}, score={score}")
            return {
                "success": True,
                "email": clean_email,
                "status": status,
                "score": score,
                "deliverable": status in DELIVERABLE_STATUSES,
                "disposable": data.get("disposable", False),
                "webmail": data.get("webmail", False),
                "mx_records": data.get("mx_records", False),
                "smtp_check": data.get("smtp_check", False),
                "raw": data,
            }
        else:
            logger.warning(f"[Hunter.io] Email Verifier returned status {r.status_code}: {r.text}")
            return {"success": False, "status_code": r.status_code, "error": r.text}
    except Exception as e:
        logger.error(f"[Hunter.io] Email Verifier exception: {e}")
        return {"success": False, "error": str(e)}


def enrich_creator_with_hunter(creator_dict: dict, api_key: Optional[str] = None) -> dict:
    """
    Enriches creator profile using Hunter.io:
    1. If creator already has an email -> verifies deliverability via Hunter Verifier.
    2. If creator has NO email -> attempts to find verified email via Hunter Finder & Domain Search.
    """
    key = _get_api_key(api_key)
    if not key:
        return creator_dict

    email = (creator_dict.get("email_public") or creator_dict.get("email") or "").strip()
    name = creator_dict.get("display_name") or creator_dict.get("name") or ""
    website = creator_dict.get("website") or ""
    handle = (creator_dict.get("handle") or "").lstrip("@")

    # 1. Verify existing email if available
    if email and "@" in email:
        v_res = verify_email(email, api_key=key)
        if v_res.get("success"):
            creator_dict["hunter_verification"] = v_res.get("status")
            creator_dict["hunter_score"] = v_res.get("score")
            creator_dict["email_verified"] = v_res.get("deliverable", False)
        return creator_dict

    # 2. Extract potential domain or company candidates
    target_domain = None
    if website:
        target_domain = website.replace("http://", "").replace("https://", "").split("/")[0]
        if any(d in target_domain for d in ["youtube.com", "instagram.com", "tiktok.com", "twitter.com", "x.com", "linktr.ee"]):
            target_domain = None

    company_candidates = []
    if handle:
        import re
        company_candidates.append(handle)
        # Strip trailing digits (e.g. @CodeChef1 -> CodeChef)
        cleaned_handle = re.sub(r"\d+$", "", handle).strip()
        if cleaned_handle and cleaned_handle != handle:
            company_candidates.append(cleaned_handle)

    # Extract notable keywords/company names from name or bio
    if name:
        company_candidates.append(name)
        for word in name.split():
            if len(word) > 4 and word.lower() not in ["learn", "coding", "tutorial", "official", "channel", "gaming", "shorts", "daily"]:
                company_candidates.append(word)

    # 3. Search via Hunter Finder / Domain Search
    found = False
    for comp in company_candidates:
        if found:
            break
        f_res = find_email(
            full_name=name,
            domain=target_domain,
            company=comp,
            api_key=key,
        )
        if f_res.get("success") and f_res.get("email"):
            creator_dict["email_public"] = f_res["email"]
            creator_dict["email"] = f_res["email"]
            creator_dict["hunter_score"] = f_res.get("score")
            creator_dict["hunter_verification"] = f_res.get("verification_status")
            creator_dict["email_verified"] = f_res.get("deliverable", False)
            logger.info(f"[Hunter.io Pipeline] Successfully enriched verified email {f_res['email']} for creator @{handle} via company='{comp}'")
            found = True
            break

    return creator_dict
