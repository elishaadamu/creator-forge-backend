# -*- coding: utf-8 -*-
"""
Hunter.io Integration Module
Provides Email Finder and Email Verifier services using Hunter.io v2 API.
API Documentation:
- Email Finder: https://hunter.io/api-documentation/v2#email-finder
- Email Verifier: https://hunter.io/api-documentation/v2#email-verifier
"""

import logging
import re
import time
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

HUNTER_API_BASE = "https://api.hunter.io/v2"

# Social platforms, stores, and link aggregators that should NOT be used as corporate domain
IGNORED_DOMAINS = {
    "youtube.com", "youtu.be", "instagram.com", "tiktok.com",
    "twitter.com", "x.com", "linktr.ee", "bio.link", "beacons.ai",
    "facebook.com", "threads.net", "linkedin.com", "gmail.com",
    "yahoo.com", "hotmail.com", "outlook.com", "icloud.com",
    "patreon.com", "discord.gg", "discord.com", "twitch.tv",
    "spotify.com", "apple.com", "steampowered.com", "amazon.com",
    "github.com", "reddit.com", "medium.com", "substack.com"
}


def clean_domain(url_or_domain: Optional[str]) -> Optional[str]:
    """Extract and sanitize a clean domain from a URL or raw domain string."""
    if not url_or_domain:
        return None
    val = url_or_domain.strip().lower()
    if "://" in val:
        try:
            parsed = urlparse(val)
            val = parsed.netloc or parsed.path
        except Exception:
            pass
    # Strip port if present
    val = val.split(":")[0]
    # Remove leading www.
    if val.startswith("www."):
        val = val[4:]
    # Remove paths
    val = val.split("/")[0].strip()

    # Reject if it's a known generic platform or invalid domain structure
    if any(val == ig or val.endswith("." + ig) for ig in IGNORED_DOMAINS) or "." not in val or len(val) < 4:
        return None
    return val


def parse_names(
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    full_name: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Ensure first_name, last_name, and full_name are populated cleanly."""
    f = (first_name or "").strip() or None
    l = (last_name or "").strip() or None
    full = (full_name or "").strip() or None

    if full and (not f or not l):
        parts = full.split()
        if len(parts) >= 2:
            if not f:
                f = parts[0]
            if not l:
                l = " ".join(parts[1:])
        elif len(parts) == 1 and not f:
            f = parts[0]

    if f and l and not full:
        full = f"{f} {l}"

    return f, l, full


class HunterClient:
    """Client for interacting with the Hunter.io v2 API."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or getattr(settings, "HUNTER_API_KEY", "") or ""

    def is_configured(self) -> bool:
        return bool(self.api_key and len(self.api_key.strip()) >= 10)

    def find_email(
        self,
        domain: Optional[str] = None,
        company: Optional[str] = None,
        linkedin_handle: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        full_name: Optional[str] = None,
        max_duration: int = 10,
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Finds the most likely email address for a person and company/domain.
        Requires at least (domain OR company OR linkedin_handle)
        AND (first_name+last_name OR full_name OR linkedin_handle).
        """
        key = api_key or self.api_key
        if not key:
            return {
                "success": False,
                "error": "Hunter.io API key is not configured.",
                "data": None,
            }

        sanitized_domain = clean_domain(domain)
        f_name, l_name, full = parse_names(first_name, last_name, full_name)

        params: Dict[str, Any] = {
            "api_key": key,
            "max_duration": max(3, min(20, int(max_duration or 10))),
        }

        if sanitized_domain:
            params["domain"] = sanitized_domain
        elif company:
            params["company"] = company.strip()
        elif linkedin_handle:
            params["linkedin_handle"] = linkedin_handle.strip().lstrip("@")

        if not any(k in params for k in ["domain", "company", "linkedin_handle"]):
            return {
                "success": False,
                "error": "At least one of domain, company, or linkedin_handle is required.",
                "data": None,
            }

        if linkedin_handle and "linkedin_handle" in params:
            pass  # linkedin_handle does not strictly require names
        else:
            if f_name and l_name:
                params["first_name"] = f_name
                params["last_name"] = l_name
            elif full and len(full.strip().split()) >= 2:
                params["full_name"] = full.strip()
            else:
                return {
                    "success": False,
                    "error": "First and last name are required by Hunter.io email-finder.",
                    "data": None,
                }

        url = f"{HUNTER_API_BASE}/email-finder"
        try:
            with httpx.Client(timeout=25.0) as client:
                res = client.get(url, params=params)

            if res.status_code == 200:
                body = res.json()
                data = body.get("data") or {}
                found_email = data.get("email")
                verification = data.get("verification") or {}

                return {
                    "success": bool(found_email),
                    "email": found_email,
                    "score": data.get("score"),
                    "verification_status": verification.get("status"),  # 'valid', 'accept_all', 'unknown'
                    "accept_all": data.get("accept_all"),
                    "position": data.get("position"),
                    "company": data.get("company"),
                    "domain": data.get("domain"),
                    "first_name": data.get("first_name") or f_name,
                    "last_name": data.get("last_name") or l_name,
                    "sources_count": len(data.get("sources") or []),
                    "sources": data.get("sources") or [],
                    "raw": data,
                }

            # Handle specific Hunter errors
            error_data = {}
            try:
                error_data = res.json()
            except Exception:
                pass

            error_msg = (
                error_data.get("errors", [{}])[0].get("details")
                or error_data.get("message")
                or f"Hunter API error (HTTP {res.status_code})"
            )
            logger.warning(f"[Hunter.io Email Finder] Error {res.status_code}: {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "status_code": res.status_code,
                "data": error_data,
            }

        except Exception as exc:
            logger.error(f"[Hunter.io Email Finder] Exception: {exc}", exc_info=True)
            return {
                "success": False,
                "error": f"Failed to connect to Hunter.io: {str(exc)}",
                "data": None,
            }

    def domain_search(
        self,
        domain: str,
        limit: int = 5,
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Searches for email addresses associated with a corporate or company domain.
        API: GET https://api.hunter.io/v2/domain-search?domain={domain}&limit={limit}&api_key={api_key}
        """
        key = api_key or self.api_key
        if not key:
            return {"success": False, "error": "Hunter.io API key is not configured.", "emails": []}
        sanitized_domain = clean_domain(domain)
        if not sanitized_domain:
            return {"success": False, "error": "Invalid domain", "emails": []}

        url = f"{HUNTER_API_BASE}/domain-search"
        params = {"domain": sanitized_domain, "limit": max(1, min(15, limit)), "api_key": key}
        try:
            res = httpx.get(url, params=params, timeout=10)
            if res.status_code == 200:
                payload = res.json().get("data", {})
                emails = payload.get("emails", [])
                return {
                    "success": True,
                    "domain": sanitized_domain,
                    "organization": payload.get("organization"),
                    "emails": emails,
                    "raw": payload,
                }
            return {"success": False, "error": f"HTTP {res.status_code}", "emails": []}
        except Exception as exc:
            logger.warning(f"[Hunter.io Domain Search] Error: {exc}")
            return {"success": False, "error": str(exc), "emails": []}

    def verify_email(
        self,
        email: str,
        api_key: Optional[str] = None,
        max_retries: int = 1,
    ) -> Dict[str, Any]:
        """
        Verifies the deliverability of an email address.
        Status: 'valid', 'invalid', 'accept_all', 'webmail', 'disposable', 'unknown'
        Result: 'deliverable', 'undeliverable', 'risky'
        """
        key = api_key or self.api_key
        if not key:
            return {
                "success": False,
                "error": "Hunter.io API key is not configured.",
                "data": None,
            }

        clean_email = (email or "").strip().lower()
        if not clean_email or "@" not in clean_email:
            return {
                "success": False,
                "error": f"Invalid email format: '{email}'",
                "data": None,
            }

        url = f"{HUNTER_API_BASE}/email-verifier"
        params = {"email": clean_email, "api_key": key}

        for attempt in range(max_retries + 1):
            try:
                with httpx.Client(timeout=25.0) as client:
                    res = client.get(url, params=params)

                # HTTP 202: Verification still in progress, poll if attempts remain
                if res.status_code == 202 and attempt < max_retries:
                    time.sleep(2.0)
                    continue

                if res.status_code == 200:
                    body = res.json()
                    data = body.get("data") or {}
                    status = data.get("status")
                    result = data.get("result")
                    score = data.get("score", 0)

                    is_deliverable = (
                        status in ["valid", "webmail"]
                        or result == "deliverable"
                        or (status == "accept_all" and (score or 0) >= 70)
                    )

                    return {
                        "success": True,
                        "email": clean_email,
                        "status": status,  # valid, invalid, accept_all, webmail, disposable, unknown
                        "result": result,  # deliverable, undeliverable, risky
                        "score": score,
                        "deliverable": is_deliverable,
                        "regexp": data.get("regexp", True),
                        "gibberish": data.get("gibberish", False),
                        "disposable": data.get("disposable", False),
                        "webmail": data.get("webmail", False),
                        "mx_records": data.get("mx_records", True),
                        "smtp_server": data.get("smtp_server", True),
                        "smtp_check": data.get("smtp_check", True),
                        "accept_all": data.get("accept_all", False),
                        "block": data.get("block", False),
                        "sources_count": len(data.get("sources") or []),
                        "sources": data.get("sources") or [],
                        "raw": data,
                    }

                error_data = {}
                try:
                    error_data = res.json()
                except Exception:
                    pass

                error_msg = (
                    error_data.get("errors", [{}])[0].get("details")
                    or error_data.get("message")
                    or f"Hunter API verifier error (HTTP {res.status_code})"
                )
                return {
                    "success": False,
                    "error": error_msg,
                    "status_code": res.status_code,
                    "data": error_data,
                }

            except Exception as exc:
                if attempt < max_retries:
                    time.sleep(1.0)
                    continue
                logger.error(f"[Hunter.io Email Verifier] Exception: {exc}", exc_info=True)
                return {
                    "success": False,
                    "error": f"Failed to connect to Hunter.io: {str(exc)}",
                    "data": None,
                }

        return {
            "success": False,
            "error": "Hunter email verification timed out.",
            "data": None,
        }

    def smart_find_for_creator(
        self,
        creator_name: str,
        handle: Optional[str] = None,
        website_url: Optional[str] = None,
        bio: Optional[str] = None,
        company: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Intelligently resolves creator name, website links, bio company mentions,
        or handles to find and verify their highest probability business email.
        """
        first_name, last_name, full_name = parse_names(full_name=creator_name)

        # 0. Check if an email is already present directly in bio or description
        if bio:
            emails_in_bio = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", bio)
            if emails_in_bio:
                extracted_email = emails_in_bio[0].strip()
                v_res = self.verify_email(extracted_email, api_key=api_key)
                if v_res.get("success"):
                    v_res["email"] = extracted_email
                    v_res["source_type"] = "bio_extracted"
                    v_res["sources_count"] = 1
                    return v_res

        # 1. Candidate domains from website_url or bio links
        candidate_domains = []
        clean_web = clean_domain(website_url)
        if clean_web:
            candidate_domains.append(clean_web)

        if bio:
            matches = re.findall(r"(?:https?://)?(?:www\.)?([a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})", bio)
            for m in matches:
                dom = clean_domain(m)
                if dom and dom not in candidate_domains:
                    candidate_domains.append(dom)

        # 2. Extract company / organization names from bio (e.g., "At Datalumina, I lead...")
        candidate_companies = []
        if company and company.strip():
            candidate_companies.append(company.strip())

        if bio:
            bio_companies = re.findall(
                r'\b(?:at|@|founder(?:\s+of|\s+at)?|ceo(?:\s+of|\s+at)?|building|running|leads?|co-founder(?:\s+of|\s+at)?)\s+([A-Z][a-zA-Z0-9_\-]+)',
                bio,
                re.IGNORECASE
            )
            for bc in bio_companies:
                clean_bc = bc.strip()
                if clean_bc.lower() not in {"the", "a", "an", "our", "my", "this", "their", "all"} and len(clean_bc) >= 3:
                    if clean_bc not in candidate_companies:
                        candidate_companies.append(clean_bc)

        # Handle as fallback company name
        clean_h = (handle or "").lstrip("@").strip()
        if clean_h and not clean_h.isdigit() and len(clean_h) >= 3:
            if clean_h not in candidate_companies:
                candidate_companies.append(clean_h)

        # Attempt A: Search via Candidate Domains
        for dom in candidate_domains:
            res = self.find_email(
                domain=dom,
                first_name=first_name,
                last_name=last_name,
                full_name=full_name,
                api_key=api_key,
            )
            if res.get("success") and res.get("email"):
                res["searched_domain"] = dom
                return res

            # Fallback A2: Domain Search on candidate domain
            ds_res = self.domain_search(domain=dom, limit=5, api_key=api_key)
            if ds_res.get("success") and ds_res.get("emails"):
                emails_list = ds_res["emails"]
                chosen = None
                if first_name:
                    fn_lower = first_name.lower()
                    for em_obj in emails_list:
                        val = em_obj.get("value", "")
                        if fn_lower in val.lower() or (em_obj.get("first_name") and fn_lower in em_obj["first_name"].lower()):
                            chosen = em_obj
                            break
                if not chosen and emails_list:
                    chosen = max(emails_list, key=lambda x: x.get("confidence", 0))

                if chosen and chosen.get("value"):
                    return {
                        "success": True,
                        "email": chosen["value"],
                        "score": chosen.get("confidence", 80),
                        "verification_status": "valid",
                        "position": chosen.get("position"),
                        "company": ds_res.get("organization") or dom,
                        "domain": dom,
                        "first_name": chosen.get("first_name") or first_name,
                        "last_name": chosen.get("last_name") or last_name,
                        "sources_count": len(chosen.get("sources", [])),
                        "sources": chosen.get("sources", []),
                        "source_type": "domain_search",
                        "searched_domain": dom,
                    }

        # Attempt B: Search via Candidate Companies (e.g. Datalumina)
        for comp in candidate_companies:
            res = self.find_email(
                company=comp,
                first_name=first_name,
                last_name=last_name,
                full_name=full_name,
                api_key=api_key,
            )
            if res.get("success") and res.get("email"):
                res["searched_company"] = comp
                return res

        return {
            "success": False,
            "error": f"No email found on Hunter.io for {creator_name} ({', '.join(candidate_companies) or 'no registered company'}).",
            "candidate_domains": candidate_domains,
            "candidate_companies": candidate_companies,
        }


# Global singleton instance
hunter = HunterClient()
