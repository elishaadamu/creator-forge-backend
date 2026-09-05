from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Header, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

import logging
from app.database import get_db, SessionLocal
from app.models.creator import Creator
from app.services import discovery, analysis as analysis_svc, product_recommendation, deck_generator
from app.services.contact_discovery import add_contact, get_contacts_for_creator, validate_contact
from app.services.scraper import scrape_profile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/creators", tags=["creators"])


class CreatorCreate(BaseModel):
    handle: str
    platform: str
    display_name: Optional[str] = None
    bio: Optional[str] = None
    profile_url: Optional[str] = None
    follower_count: int = 0
    niche: list[str] = []
    location: Optional[str] = None
    website: Optional[str] = None
    email_public: Optional[str] = None
    discovery_source: str = "manual"
    notes: Optional[str] = None


class ContactCreate(BaseModel):
    contact_type: str
    value: str
    source: str
    notes: Optional[str] = None


class ScrapeRequest(BaseModel):
    platform: str
    handle: str  # @handle, channel URL, or full URL
    save: bool = True  # auto-save to DB after scraping


class ApifyFindEmailRequest(BaseModel):
    handle: Optional[str] = None
    channel: Optional[str] = None
    url: Optional[str] = None
    api_key: Optional[str] = None


@router.post("/apify/find-email")
def apify_find_email_endpoint(body: ApifyFindEmailRequest):
    """Find public email via social media scraper & profile extraction."""
    from app.services.scraper import scrape_profile
    target = body.handle or body.channel or body.url
    if not target:
        raise HTTPException(400, "Handle, channel, or URL required")
    
    platform = (body.platform or "youtube").lower()
    res = scrape_profile(platform, target, apify_token=body.api_key)
    email = (res.get("email_public") or res.get("email") or "").strip()
    
    if not email:
        return {
            "success": False,
            "error": f"No public email found on {platform} profile for {target}",
            "data": res
        }
    
    return {
        "success": True,
        "email": email,
        "score": 100,
        "verification_status": "verified",
        "data": res
    }


class HunterFindEmailRequest(BaseModel):
    creator_id: Optional[str] = None
    domain: Optional[str] = None
    company: Optional[str] = None
    linkedin_handle: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    max_duration: Optional[int] = 10
    auto_save: Optional[bool] = True
    api_key: Optional[str] = None


class HunterVerifyEmailRequest(BaseModel):
    email: str
    creator_id: Optional[str] = None
    auto_save: Optional[bool] = True
    api_key: Optional[str] = None


@router.post("/hunter/find-email")
def hunter_find_email_endpoint(body: HunterFindEmailRequest, db: Session = Depends(get_db)):
    """
    Find high-probability corporate/business email via Hunter.io v2 API.
    Can accept explicit domain/company/names or resolve automatically for a creator_id.
    """
    from app.integrations.hunter import hunter
    
    creator = None
    if body.creator_id:
        creator = db.get(Creator, body.creator_id)
        if not creator:
            clean = body.creator_id.replace("@", "").lower().strip()
            creator = db.query(Creator).filter(
                (Creator.id == body.creator_id) |
                (Creator.handle.ilike(f"%{clean}%")) |
                (Creator.display_name.ilike(f"%{clean}%"))
            ).first()

    domain = body.domain
    company = body.company
    first_name = body.first_name
    last_name = body.last_name
    full_name = body.full_name

    # If creator found and missing fields, pull from creator profile
    # If creator found, use smart find with bio company extraction & platform fallback
    if creator:
        if not full_name and not (first_name and last_name):
            full_name = creator.display_name or creator.handle

        # Filter out social platform domains
        from app.integrations.hunter import clean_domain
        clean_d = clean_domain(domain)
        clean_c = company if company and company.lower() != (creator.handle or "").lower().replace("@", "") else None

        res = hunter.smart_find_for_creator(
            creator_name=full_name,
            handle=creator.handle,
            website_url=clean_d or getattr(creator, "website", None),
            bio=getattr(creator, "bio", None),
            company=clean_c,
            api_key=body.api_key
        )

        # If Hunter B2B finder didn't find an email, fall back to scraping platform profile (YouTube / Instagram / TikTok)
        if not res.get("success"):
            try:
                from app.services.scraper import scrape_profile
                p_slug = (creator.platform or "youtube").lower()
                clean_h = (creator.handle or "").lstrip("@")
                scraped = scrape_profile(p_slug, clean_h)
                scraped_email = (scraped.get("email_public") or scraped.get("email") or "").strip()
                if scraped_email and "@" in scraped_email:
                    # Immediately verify the scraped platform email with Hunter Email Verifier!
                    ver = hunter.verify_email(scraped_email, api_key=body.api_key)
                    res = {
                        "success": True,
                        "email": scraped_email,
                        "score": ver.get("score") or 85,
                        "verification_status": ver.get("status") or "valid",
                        "deliverable": ver.get("deliverable", True),
                        "source_type": f"{p_slug}_channel_contact",
                        "sources": [{"domain": f"{p_slug}.com", "uri": creator.profile_url or ""}],
                        "sources_count": 1,
                        "smtp_check": ver.get("smtp_check", True),
                        "mx_records": ver.get("mx_records", True),
                        "raw": ver.get("raw"),
                    }
            except Exception as scrap_err:
                logger.warning(f"Platform profile fallback notice for {creator.handle}: {scrap_err}")
    else:
        res = hunter.find_email(
            domain=domain,
            company=company,
            linkedin_handle=body.linkedin_handle,
            first_name=first_name,
            last_name=last_name,
            full_name=full_name,
            max_duration=body.max_duration or 10,
            api_key=body.api_key
        )

    if not res.get("success"):
        return res

    found_email = res.get("email")
    if found_email and creator and body.auto_save:
        creator.email_public = found_email
        db.commit()
        try:
            from app.services.contact_discovery import add_contact
            add_contact(
                db,
                creator.id,
                "email",
                found_email,
                "hunter_io",
                notes=f"Hunter.io Score: {res.get('score')} | Status: {res.get('verification_status')}",
                actor="hunter_api"
            )
        except Exception as e:
            pass

    return {
        **res,
        "creator_id": creator.id if creator else None,
        "saved": bool(creator and body.auto_save and found_email)
    }


@router.post("/hunter/verify-email")
def hunter_verify_email_endpoint(body: HunterVerifyEmailRequest, db: Session = Depends(get_db)):
    """
    Verify deliverability of an email using Hunter.io v2 Email Verifier.
    """
    from app.integrations.hunter import hunter
    res = hunter.verify_email(body.email, api_key=body.api_key)
    
    if res.get("success") and body.creator_id and body.auto_save:
        creator = db.get(Creator, body.creator_id)
        if creator and res.get("deliverable"):
            creator.email_public = body.email.strip()
            db.commit()

    return res


@router.post("/scrape")
def scrape_creator(request: Request, body: ScrapeRequest, actor: str = "internal"):
    """
    Scrape a public profile and optionally save it.
    Parses handle from full URLs automatically.
    """
    import re
    handle = body.handle.strip()
    platform = body.platform.lower().strip()

    # Parse handle from URL
    yt_patterns = [
        r"youtube\.com/(@[^/?&\s]+)",
        r"youtube\.com/(channel/[^/?&\s]+)",
        r"youtube\.com/(c/[^/?&\s]+)",
        r"youtube\.com/(user/[^/?&\s]+)",
    ]
    ig_patterns = [r"instagram\.com/([^/?&\s]+)"]
    tt_patterns = [r"tiktok\.com/(@?[^/?&\s]+)"]
    tw_patterns = [r"(?:twitter|x)\.com/([^/?&\s]+)"]

    if "youtube.com" in handle:
        platform = "youtube"
        for pat in yt_patterns:
            m = re.search(pat, handle)
            if m:
                handle = m.group(1)
                break
    elif "instagram.com" in handle:
        platform = "instagram"
        for pat in ig_patterns:
            m = re.search(pat, handle)
            if m:
                handle = m.group(1)
                break
    elif "tiktok.com" in handle:
        platform = "tiktok"
        for pat in tt_patterns:
            m = re.search(pat, handle)
            if m:
                handle = m.group(1)
                break
    elif "twitter.com" in handle or "x.com" in handle:
        platform = "twitter"
        for pat in tw_patterns:
            m = re.search(pat, handle)
            if m:
                handle = m.group(1)
                break

    if platform != "youtube":
        handle = handle.lstrip("@").strip("/")
    else:
        handle = handle.strip("/")

    apify_token = request.headers.get("X-Apify-Token")
    scraped = scrape_profile(platform, handle, apify_token=apify_token)
    if "error" in scraped and not scraped.get("display_name"):
        raise HTTPException(400, f"Scrape failed: {scraped['error']}")

    creator_data = None
    if body.save:
        try:
            with SessionLocal() as db:
                creator, created = discovery.create_or_get_creator(
                    db=db,
                    handle=scraped["handle"],
                    platform=scraped["platform"],
                    display_name=scraped.get("display_name"),
                    bio=scraped.get("bio"),
                    profile_url=scraped.get("profile_url"),
                    avatar_url=scraped.get("avatar_url"),
                    follower_count=scraped.get("follower_count", 0),
                    niche=scraped.get("niche", []),
                    website=scraped.get("website"),
                    email_public=scraped.get("email_public"),
                    discovery_source="scrape",
                    actor=actor,
                )
                # Auto-save any found email as a contact
                if scraped.get("email_public") and creator:
                    try:
                        add_contact(
                            db, creator.id, "email",
                            scraped["email_public"], "scraped_bio", actor=actor,
                        )
                    except Exception:
                        pass
                for link in scraped.get("social_links", [])[:3]:
                    try:
                        add_contact(
                            db, creator.id, "business_inquiry_form",
                            link, "scraped_profile", actor=actor,
                        )
                    except Exception:
                        pass
                creator_data = _creator_dict(creator) if creator else None
        except ValueError as e:
            raise HTTPException(400, str(e))

    return {
        "scraped": scraped,
        "creator": creator_data,
        "created": creator_data is not None,
    }


@router.post("")
def create_creator(body: CreatorCreate, actor: str = "internal", db: Session = Depends(get_db)):
    try:
        creator, created = discovery.create_or_get_creator(
            db=db, actor=actor, **body.model_dump()
        )
        return {"created": created, "creator": _creator_dict(creator)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("")
def list_creators(
    status: Optional[str] = None,
    platform: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    q = db.query(Creator)
    if status:
        q = q.filter(Creator.status == status)
    if platform:
        q = q.filter(Creator.platform == platform)
    creators = q.order_by(Creator.created_at.desc()).offset(skip).limit(limit).all()
    return [_creator_dict(c) for c in creators]


@router.get("/{creator_id}")
def get_creator(creator_id: str, db: Session = Depends(get_db)):
    c = db.get(Creator, creator_id)
    if not c:
        raise HTTPException(404, "Creator not found")
    return _creator_dict(c)


class CreatorUpdate(BaseModel):
    display_name: Optional[str] = None
    bio: Optional[str] = None
    profile_url: Optional[str] = None
    follower_count: Optional[int] = None
    niche: Optional[list[str]] = None
    location: Optional[str] = None
    website: Optional[str] = None
    email_public: Optional[str] = None
    email: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    selected_concept_id: Optional[str] = None
    selectedConceptId: Optional[str] = None
    selected_concept: Optional[Dict[str, Any]] = None
    selectedConcept: Optional[Dict[str, Any]] = None


@router.patch("/{creator_id}")
@router.put("/{creator_id}")
def update_creator_details(
    creator_id: str,
    body: CreatorUpdate,
    actor: str = "user",
    db: Session = Depends(get_db)
):
    c = db.get(Creator, creator_id)
    if not c:
        clean_handle = creator_id.lstrip("@").strip().lower()
        c = db.query(Creator).filter(
            (Creator.handle.ilike(clean_handle)) |
            (Creator.handle.ilike(f"@{clean_handle}")) |
            (Creator.email_public.ilike(creator_id.strip())) |
            (Creator.display_name.ilike(creator_id.strip()))
        ).first()

    if not c:
        raise HTTPException(404, f"Creator {creator_id} not found")
    
    data = body.model_dump(exclude_unset=True)
    target_email = (body.email_public or body.email or "").strip()
    if target_email:
        c.email_public = target_email

    for field, val in data.items():
        if field not in ("email", "email_public", "selected_concept_id", "selectedConceptId", "selected_concept", "selectedConcept") and hasattr(c, field):
            setattr(c, field, val)

    # Persist selected_concept_id and selected_concept to discovery_notes JSON
    if any(k in data for k in ("selected_concept_id", "selectedConceptId", "selected_concept", "selectedConcept")):
        import json
        notes = {}
        if c.discovery_notes and c.discovery_notes.startswith("{"):
            try:
                notes = json.loads(c.discovery_notes)
            except Exception:
                notes = {}
        sel_id = data.get("selected_concept_id") or data.get("selectedConceptId")
        if sel_id:
            notes["selected_concept_id"] = sel_id
        sel_concept = data.get("selected_concept") or data.get("selectedConcept")
        if sel_concept:
            notes["selected_concept"] = sel_concept
        c.discovery_notes = json.dumps(notes)
    
    if target_email:
        try:
            from app.models.creator import Contact
            contact = db.query(Contact).filter(Contact.creator_id == c.id, Contact.contact_type == "email").first()
            if contact:
                contact.value = target_email
            else:
                contact = Contact(creator_id=c.id, contact_type="email", value=target_email, source="manual_edit")
                db.add(contact)
        except Exception:
            pass
            
    db.commit()
    db.refresh(c)
    return {"status": "success", "creator": _creator_dict(c)}


@router.patch("/{creator_id}/status")
def update_status(
    creator_id: str, status: str, notes: Optional[str] = None,
    actor: str = "internal", db: Session = Depends(get_db)
):
    try:
        c = discovery.update_creator_status(db, creator_id, status, actor, notes)
        return _creator_dict(c)
    except ValueError as e:
        raise HTTPException(400, str(e))


class QualifyBody(BaseModel):
    status: str  # qualified | disqualified | in_review | approved
    notes: Optional[str] = None


@router.post("/{creator_id}/qualify")
def qualify_creator(
    creator_id: str, body: QualifyBody,
    actor: str = "ops_dashboard", db: Session = Depends(get_db)
):
    """Ops dashboard shortcut — mark a creator as qualified/disqualified."""
    try:
        c = discovery.update_creator_status(db, creator_id, body.status, actor, body.notes)
        return _creator_dict(c)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{creator_id}/analyze")
def run_analysis(
    creator_id: str,
    actor: str = "internal",
    x_gemini_key: Optional[str] = Header(None),
    x_openai_key: Optional[str] = Header(None),
    x_anthropic_key: Optional[str] = Header(None),
    x_together_key: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    from app.services.scraper import scrape_profile

    creator = db.get(Creator, creator_id)
    if not creator:
        raise HTTPException(404, "Creator not found")

    # Auto re-scrape if we are missing critical data
    if not creator.follower_count or not creator.bio or not creator.niche:
        try:
            scraped = scrape_profile(creator.platform, creator.handle)
            if scraped.get("follower_count"):
                creator.follower_count = scraped["follower_count"]
            if scraped.get("bio") and not creator.bio:
                creator.bio = scraped["bio"]
            if scraped.get("display_name") and scraped["display_name"] != creator.handle:
                creator.display_name = scraped["display_name"]
            if scraped.get("avatar_url") and not creator.avatar_url:
                creator.avatar_url = scraped["avatar_url"]
            if scraped.get("niche") and not creator.niche:
                creator.niche = scraped["niche"]
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(creator, "niche")
            if scraped.get("email_public") and not creator.email_public:
                creator.email_public = scraped["email_public"]
            db.commit()
        except Exception:
            pass  # continue with whatever data we have

    custom_keys = {}
    if x_gemini_key:
        custom_keys["geminiKey"] = x_gemini_key
    if x_openai_key:
        custom_keys["openaiKey"] = x_openai_key
    if x_anthropic_key:
        custom_keys["anthropicKey"] = x_anthropic_key
    if x_together_key:
        custom_keys["togetherKey"] = x_together_key

    try:
        result = analysis_svc.run_ai_analysis(db, creator_id, actor=actor, custom_keys=custom_keys or None)
        return {"analysis_id": result.id, "summary": result.summary, "score": result.engagement_quality_score}
    except ValueError as e:
        status_code = 404 if "not found" in str(e).lower() else 400
        raise HTTPException(status_code, str(e))


class SuppressBody(BaseModel):
    reason: str = "do_not_contact"
    notes: Optional[str] = None


@router.post("/{creator_id}/suppress")
def suppress_creator(
    creator_id: str, body: SuppressBody = SuppressBody(),
    actor: str = "ops_dashboard", db: Session = Depends(get_db)
):
    """Ops dashboard — suppress a creator (add to do-not-contact list)."""
    from app.services.suppression import add_suppression
    creator = db.get(Creator, creator_id)
    if not creator:
        raise HTTPException(404, "Creator not found")
    add_suppression(
        db, reason=body.reason, creator_id=creator_id,
        email=creator.email_public or None,
        suppressed_by=actor, notes=body.notes, actor=actor,
    )
    return {"suppressed": True, "creator_id": creator_id}


@router.delete("/all")
def delete_all_creators(db: Session = Depends(get_db)):
    """Delete all creators and all associated contacts, outreach messages, threads, and replies."""
    from sqlalchemy import text
    try:
        bind_url = str(db.bind.url) if db.bind else ""
        if "postgresql" in bind_url or "postgres" in bind_url:
            db.execute(text("""
                TRUNCATE TABLE 
                    validation_gate_decisions, validation_telemetry, creator_campaign_tasks,
                    validation_campaigns, validation_plans, co_launch_projects,
                    replies, follow_ups, threads, outreach_messages, suppression_list,
                    contacts, analyses, content_samples, decks, metrics_snapshots,
                    partnerships, post_suggestions, product_recommendations, creators
                CASCADE;
            """))
            # Reset global workflow state to prevent orphan choices or pitch history from resurfacing
            try:
                from app.models.workflow_state import WorkflowState
                state = db.get(WorkflowState, "default")
                if state:
                    state.active_section = "section1"
                    state.active_step = 1
                    state.selected_creator_id = None
                    state.active_project_id = None
                    state.pitch_sent_map = {}
                    state.ai_choice_map = {}
                    state.answer_sent_map = {}
                    state.persuasion_sent_map = {}
                    state.creator_stage_map = {}
                    state.extra_state = {}
                    state.updated_at = datetime.utcnow()
            except Exception as ws_err:
                logger.warning(f"Failed to reset workflow state during delete_all: {ws_err}")

            db.commit()
            return {"success": True, "deleted_count": 0, "message": "Successfully wiped all creators, projects, and workflow states"}
        else:
            from app.models.outreach import OutreachMessage, Thread, Reply, FollowUp, SuppressionList
            from app.models.creator import (
                Contact, Analysis, ContentSample, Deck,
                MetricsSnapshot, Partnership, PostSuggestion, ProductRecommendation
            )
            from app.models.project import (
                CoLaunchProject, ValidationPlan, ValidationCampaign,
                CreatorCampaignTask, ValidationTelemetry, ValidationGateDecision
            )
            db.query(Reply).delete(synchronize_session=False)
            db.query(FollowUp).delete(synchronize_session=False)
            db.query(Thread).delete(synchronize_session=False)
            db.query(OutreachMessage).delete(synchronize_session=False)
            db.query(SuppressionList).delete(synchronize_session=False)
            db.query(Contact).delete(synchronize_session=False)
            db.query(Analysis).delete(synchronize_session=False)
            db.query(ContentSample).delete(synchronize_session=False)
            db.query(Deck).delete(synchronize_session=False)
            db.query(MetricsSnapshot).delete(synchronize_session=False)
            db.query(Partnership).delete(synchronize_session=False)
            db.query(PostSuggestion).delete(synchronize_session=False)
            db.query(ProductRecommendation).delete(synchronize_session=False)
            db.query(ValidationGateDecision).delete(synchronize_session=False)
            db.query(ValidationTelemetry).delete(synchronize_session=False)
            db.query(CreatorCampaignTask).delete(synchronize_session=False)
            db.query(ValidationCampaign).delete(synchronize_session=False)
            db.query(ValidationPlan).delete(synchronize_session=False)
            db.query(CoLaunchProject).delete(synchronize_session=False)
            deleted_count = db.query(Creator).delete(synchronize_session=False)

            # Reset global workflow state
            try:
                from app.models.workflow_state import WorkflowState
                state = db.get(WorkflowState, "default")
                if state:
                    state.active_section = "section1"
                    state.active_step = 1
                    state.selected_creator_id = None
                    state.active_project_id = None
                    state.pitch_sent_map = {}
                    state.ai_choice_map = {}
                    state.answer_sent_map = {}
                    state.persuasion_sent_map = {}
                    state.creator_stage_map = {}
                    state.extra_state = {}
                    state.updated_at = datetime.utcnow()
            except Exception as ws_err:
                logger.warning(f"Failed to reset workflow state during delete_all: {ws_err}")

            db.commit()
            return {"success": True, "deleted_count": deleted_count, "message": f"Successfully deleted {deleted_count} creators and reset workflow states"}
    except Exception as e:
        db.rollback()
        try:
            from app.models.outreach import OutreachMessage, Thread, Reply, FollowUp, SuppressionList
            from app.models.creator import (
                Contact, Analysis, ContentSample, Deck,
                MetricsSnapshot, Partnership, PostSuggestion, ProductRecommendation
            )
            from app.models.project import (
                CoLaunchProject, ValidationPlan, ValidationCampaign,
                CreatorCampaignTask, ValidationTelemetry, ValidationGateDecision
            )
            # Purge all Cloudinary assets for all ventures
            try:
                from app.integrations.cloudinary_service import delete_all_files_for_project
                all_projs = db.query(CoLaunchProject).all()
                for p in all_projs:
                    delete_all_files_for_project(p)
            except Exception as cld_err:
                logger.warning(f"[DeleteAllCreators] Cloudinary purge error: {cld_err}")

            db.query(Reply).delete(synchronize_session=False)
            db.query(FollowUp).delete(synchronize_session=False)
            db.query(Thread).delete(synchronize_session=False)
            db.query(OutreachMessage).delete(synchronize_session=False)
            db.query(SuppressionList).delete(synchronize_session=False)
            db.query(Contact).delete(synchronize_session=False)
            db.query(Analysis).delete(synchronize_session=False)
            db.query(ContentSample).delete(synchronize_session=False)
            db.query(Deck).delete(synchronize_session=False)
            db.query(MetricsSnapshot).delete(synchronize_session=False)
            db.query(Partnership).delete(synchronize_session=False)
            db.query(PostSuggestion).delete(synchronize_session=False)
            db.query(ProductRecommendation).delete(synchronize_session=False)
            db.query(ValidationGateDecision).delete(synchronize_session=False)
            db.query(ValidationTelemetry).delete(synchronize_session=False)
            db.query(CreatorCampaignTask).delete(synchronize_session=False)
            db.query(ValidationCampaign).delete(synchronize_session=False)
            db.query(ValidationPlan).delete(synchronize_session=False)
            db.query(CoLaunchProject).delete(synchronize_session=False)
            deleted_count = db.query(Creator).delete(synchronize_session=False)
            db.commit()
            return {"success": True, "deleted_count": deleted_count, "message": f"Successfully deleted {deleted_count} creators and all venture files from Cloudinary & DB"}
        except Exception as e2:
            db.rollback()
            raise HTTPException(500, f"Failed to delete all creators: {str(e2)}")


@router.delete("/{creator_id}")
def delete_creator(
    creator_id: str, actor: str = "ops_dashboard", db: Session = Depends(get_db)
):
    """Ops dashboard — delete a creator entirely with all chats, threads, and dependencies cascaded."""
    if creator_id == "all":
        return delete_all_creators(db=db)

    creator = db.get(Creator, creator_id)
    if not creator:
        clean_handle = creator_id.lstrip("@").strip().lower()
        creator = db.query(Creator).filter(
            (Creator.handle.ilike(clean_handle)) |
            (Creator.handle.ilike(f"@{clean_handle}")) |
            (Creator.email_public.ilike(creator_id.strip())) |
            (Creator.display_name.ilike(creator_id.strip()))
        ).first()

    if not creator:
        raise HTTPException(404, "Creator not found")

    real_id = creator.id

    from app.models.outreach import OutreachMessage, Thread, Reply, FollowUp, SuppressionList
    from app.models.creator import (
        Contact, Analysis, ContentSample, Deck,
        MetricsSnapshot, Partnership, PostSuggestion, ProductRecommendation
    )
    from app.models.project import CoLaunchProject

    try:
        thread_ids = [t.id for t in db.query(Thread.id).filter(Thread.creator_id == real_id).all()]
        if thread_ids:
            db.query(Reply).filter(Reply.thread_id.in_(thread_ids)).delete(synchronize_session=False)
            db.query(FollowUp).filter(FollowUp.thread_id.in_(thread_ids)).delete(synchronize_session=False)
        db.query(Thread).filter(Thread.creator_id == real_id).delete(synchronize_session=False)
        db.query(OutreachMessage).filter(OutreachMessage.creator_id == real_id).delete(synchronize_session=False)
        db.query(SuppressionList).filter(SuppressionList.creator_id == real_id).delete(synchronize_session=False)
        db.query(Contact).filter(Contact.creator_id == real_id).delete(synchronize_session=False)
        db.query(Analysis).filter(Analysis.creator_id == real_id).delete(synchronize_session=False)
        db.query(ContentSample).filter(ContentSample.creator_id == real_id).delete(synchronize_session=False)
        db.query(Deck).filter(Deck.creator_id == real_id).delete(synchronize_session=False)
        db.query(MetricsSnapshot).filter(MetricsSnapshot.creator_id == real_id).delete(synchronize_session=False)
        db.query(Partnership).filter(Partnership.creator_id == real_id).delete(synchronize_session=False)
        db.query(PostSuggestion).filter(PostSuggestion.creator_id == real_id).delete(synchronize_session=False)
        db.query(ProductRecommendation).filter(ProductRecommendation.creator_id == real_id).delete(synchronize_session=False)

        # Purge all Cloudinary assets and co-launch projects associated with this creator
        try:
            from app.integrations.cloudinary_service import delete_all_files_for_project, delete_media_from_cloudinary
            creator_projs = db.query(CoLaunchProject).filter(
                (CoLaunchProject.creator_id == real_id) |
                (CoLaunchProject.creator_handle.ilike(f"%{creator.handle or ''}%"))
            ).all()
            for p in creator_projs:
                delete_all_files_for_project(p)
                db.delete(p)

            if creator.avatar_url and "cloudinary.com" in creator.avatar_url:
                delete_media_from_cloudinary(url=creator.avatar_url)
        except Exception as cld_err:
            logger.warning(f"[DeleteCreator] Cloudinary purge error: {cld_err}")

        db.delete(creator)

        # Purge creator from global workflow state maps
        try:
            from app.models.workflow_state import WorkflowState
            state = db.get(WorkflowState, "default")
            if state:
                dirty = False
                for map_name in ("pitch_sent_map", "ai_choice_map", "answer_sent_map", "persuasion_sent_map", "creator_stage_map"):
                    curr = dict(getattr(state, map_name) or {})
                    keys_to_remove = [k for k in curr if k in (real_id, clean_handle, f"@{clean_handle}")]
                    if keys_to_remove:
                        for k in keys_to_remove:
                            curr.pop(k, None)
                        setattr(state, map_name, curr)
                        dirty = True
                if state.selected_creator_id in (real_id, clean_handle, f"@{clean_handle}"):
                    state.selected_creator_id = None
                    dirty = True
                if dirty:
                    state.updated_at = datetime.utcnow()
        except Exception as ws_err:
            logger.warning(f"Failed to purge creator from workflow state: {ws_err}")

        db.commit()
        return {"deleted": True, "creator_id": real_id}
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Failed to delete creator: {str(e)}")


class CreatorPatchBody(BaseModel):
    display_name: Optional[str] = None
    email_public: Optional[str] = None
    status: Optional[str] = None
    reply_classification: Optional[str] = None
    reply_text: Optional[str] = None
    discovery_notes: Optional[str] = None
    niche: Optional[list] = None


@router.patch("/{creator_id}")
def update_creator(
    creator_id: str, body: CreatorPatchBody, actor: str = "ops_dashboard", db: Session = Depends(get_db)
):
    """Update creator attributes, including email, status, and reply classification."""
    creator = db.get(Creator, creator_id)
    if not creator:
        clean_handle = creator_id.lstrip("@").strip().lower()
        creator = db.query(Creator).filter(
            (Creator.handle.ilike(clean_handle)) |
            (Creator.handle.ilike(f"@{clean_handle}")) |
            (Creator.email_public.ilike(creator_id.strip())) |
            (Creator.display_name.ilike(creator_id.strip()))
        ).first()

    if not creator:
        raise HTTPException(404, f"Creator {creator_id} not found")

    if body.display_name is not None:
        creator.display_name = body.display_name
    if body.email_public is not None:
        creator.email_public = body.email_public
    if body.status is not None:
        creator.status = body.status
    if body.discovery_notes is not None:
        creator.discovery_notes = body.discovery_notes
    if body.niche is not None:
        creator.niche = body.niche
    
    if body.reply_classification is not None or body.reply_text is not None:
        import json
        notes_data = {}
        try:
            if creator.discovery_notes and creator.discovery_notes.startswith("{"):
                notes_data = json.loads(creator.discovery_notes)
        except Exception:
            notes_data = {}
        if body.reply_classification is not None:
            notes_data["reply_classification"] = body.reply_classification
        if body.reply_text is not None:
            notes_data["reply_text"] = body.reply_text
        creator.discovery_notes = json.dumps(notes_data)

    creator.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(creator)
    return _creator_dict(creator)


@router.post("/{creator_id}/recommend")
def generate_products(
    creator_id: str,
    actor: str = "internal",
    x_gemini_key: Optional[str] = Header(None),
    x_openai_key: Optional[str] = Header(None),
    x_anthropic_key: Optional[str] = Header(None),
    x_together_key: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    custom_keys = {}
    if x_gemini_key:
        custom_keys["geminiKey"] = x_gemini_key
    if x_openai_key:
        custom_keys["openaiKey"] = x_openai_key
    if x_anthropic_key:
        custom_keys["anthropicKey"] = x_anthropic_key
    if x_together_key:
        custom_keys["togetherKey"] = x_together_key

    try:
        recs = product_recommendation.generate_recommendations(
            db, creator_id, actor=actor, custom_keys=custom_keys or None
        )
        return [_rec_dict(r) for r in recs]
    except ValueError as e:
        status_code = 404 if "not found" in str(e).lower() else 400
        raise HTTPException(status_code, str(e))


@router.post("/{creator_id}/pitch-package")
def generate_pitch_package(creator_id: str, actor: str = "internal", db: Session = Depends(get_db)):
    """
    One-click: generates product recommendation + pitch deck + outreach email.
    Returns everything needed to pitch this creator.
    """
    from app.models.creator import ProductRecommendation, Deck
    from app.services.outreach_generator import generate_outreach_draft
    from app.models.outreach import OutreachMessage

    creator = db.get(Creator, creator_id)
    if not creator:
        raise HTTPException(404, "Creator not found")

    # 1. Get or generate product recommendation
    rec = (
        db.query(ProductRecommendation)
        .filter(ProductRecommendation.creator_id == creator_id)
        .order_by(ProductRecommendation.created_at.desc())
        .first()
    )
    if not rec:
        recs = product_recommendation.generate_recommendations(db, creator_id, actor=actor)
        rec = recs[0] if recs else None
    if not rec:
        raise HTTPException(500, "Could not generate product recommendation")

    # 2. Get or generate deck
    existing_deck = (
        db.query(Deck)
        .filter(Deck.creator_id == creator_id, Deck.product_recommendation_id == rec.id)
        .order_by(Deck.version.desc())
        .first()
    )
    deck = existing_deck or deck_generator.generate_deck(db, creator_id, rec.id, actor=actor)

    # 3. Generate outreach email (no campaign/contact required — draft only)
    # Build a temp structure
    from app.config import settings
    import json, re

    email_draft = _generate_email_draft(creator, rec, settings)

    # 4. Gather contacts
    contacts = get_contacts_for_creator(db, creator_id)

    return {
        "creator": _creator_dict(creator),
        "recommendation": _rec_dict(rec),
        "deck": {"id": deck.id, "title": deck.title, "slides": deck.slides, "version": deck.version},
        "email_draft": email_draft,
        "contacts": [_contact_dict(c) for c in contacts],
    }


def _generate_email_draft(creator, rec, settings) -> dict:
    """Generate email subject + body for pitch. Uses AI when configured, else rich template."""
    name       = creator.display_name or f"@{creator.handle}"
    handle     = creator.handle
    platform   = creator.platform.capitalize()
    niche_str  = ', '.join(creator.niche or [])
    followers  = creator.follower_count or 0
    bio        = (creator.bio or '').strip()

    def _fmt(n):
        if n >= 1_000_000: return f"{n/1_000_000:.1f}M".replace('.0M', 'M')
        if n >= 1_000: return f"{n//1_000}K"
        return str(n)

    prompt = (
        f"Write a short, highly personalized cold outreach email for a creator partnership.\n\n"
        f"Creator: {name} (@{handle}) on {platform}\n"
        f"Followers: {_fmt(followers)}\n"
        f"Niche: {niche_str or 'general'}\n"
        f"Bio: {bio or 'N/A'}\n\n"
        f"Product pitch: {rec.product_name} — {rec.tagline}\n"
        f"Description: {rec.description}\n"
        f"Revenue potential: {rec.revenue_potential}\n\n"
        f"Rules:\n"
        f"- Max 200 words total\n"
        f"- Open with something SPECIFIC from their bio or content (not generic)\n"
        f"- Conversational, human tone — not corporate\n"
        f"- Lead with value to them, not what we want\n"
        f"- One CTA: 20-min call\n"
        f"- End with: 'Reply STOP anytime to opt out.'\n\n"
        f'Return JSON only: {{"subject": "...", "body": "..."}}'
    )

    raw = None
    try:
        from app.services.llm import call_llm
        raw = call_llm(prompt=prompt, max_tokens=800)
        if raw:
            print(f"\n🚀 [PITCH PACK OUTREACH SUCCESS] Generated successfully using LLM raw payload.")
        else:
            print(f"\n⚠️ [PITCH PACK OUTREACH WARNING] LLM returned empty response. Falling back to default template.")
    except Exception as e:
        print(f"\n❌ [PITCH PACK OUTREACH ERROR] LLM generation failed: {e}. Falling back to default template.")
        raw = None

    import json, re
    if raw:
        try:
            data = json.loads(raw)
        except Exception:
            m = re.search(r'\{.*\}', raw, re.DOTALL)
            data = json.loads(m.group()) if m else {"subject": f"Partnership idea for {name}", "body": raw}
        return data
    else:
        # Rich template fallback if LLM failed
        bio_line = f"Your channel — \"{bio[:120]}{'...' if len(bio)>120 else ''}\" — " if bio else f"Your {platform} channel "
        niche_line = f"in the {niche_str} space" if niche_str else "in your space"
        subject = f"Partnership idea for {name}"
        body = (
            f"Hi {name},\n\n"
            f"{bio_line}caught my attention. {_fmt(followers)} followers {niche_line} — "
            f"and I think your audience is exactly who we've been trying to reach.\n\n"
            f"We're looking to build **{rec.product_name}** with the right creator — {rec.tagline}\n\n"
            f"{rec.description}\n\n"
            f"Revenue potential: {rec.revenue_potential}. "
            f"You'd bring the audience and trust; we handle the product and operations.\n\n"
            f"Would you be open to a quick 20-minute call this week to explore it?\n\n"
            f"Best,\n[Your Name]\n\n"
            f"P.S. Reply STOP anytime and I won't reach out again."
        )
        return {"subject": subject, "body": body}


class SendRequest(BaseModel):
    subject: str
    body: str


@router.post("/{creator_id}/send")
def send_outreach(
    creator_id: str, body: SendRequest,
    actor: str = "internal", db: Session = Depends(get_db)
):
    """
    Human-approved send: user has reviewed and edited the email, now queues it.
    Creates the outreach message already marked approved so it goes straight to queue.
    """
    from app.models.outreach import OutreachMessage
    import uuid as _uuid_mod
    from datetime import datetime

    creator = db.get(Creator, creator_id)
    if not creator:
        raise HTTPException(404, "Creator not found")

    # Safety: check suppression
    if creator.status == "suppressed":
        raise HTTPException(400, "Creator is on suppression list")

    # Find best contact (email preferred)
    contacts = get_contacts_for_creator(db, creator_id)
    email_contacts = [c for c in contacts if c.contact_type == "email" and not c.is_suppressed]
    target_contact_id = email_contacts[0].id if email_contacts else None

    msg = OutreachMessage(
        id=str(_uuid_mod.uuid4()),
        creator_id=creator_id,
        contact_id=target_contact_id,
        subject=body.subject,
        body=body.body,
        status="approved",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(msg)

    # Mark creator as in_review (outreach sent, awaiting reply)
    if creator.status in ("discovered", "qualified"):
        creator.status = "in_review"
    creator.updated_at = datetime.utcnow()

    # Audit log
    from app.models.audit import AuditLog
    db.add(AuditLog(
        id=str(_uuid_mod.uuid4()),
        entity_type="outreach_message", entity_id=msg.id,
        action="human_approved_send", actor=actor,
        details={"subject": body.subject, "creator_id": creator_id},
        created_at=datetime.utcnow(),
    ))
    db.commit()

    return {
        "message_id": msg.id,
        "status": "approved",
        "contact_id": target_contact_id,
        "note": "Queued for send. Review in Dashboard → Outreach Queue.",
    }


@router.post("/{creator_id}/contacts")
def add_creator_contact(
    creator_id: str, body: ContactCreate,
    actor: str = "internal", db: Session = Depends(get_db)
):
    try:
        contact = add_contact(db, creator_id, body.contact_type, body.value, body.source, body.notes, actor)
        return _contact_dict(contact)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{creator_id}/contacts")
def list_contacts(creator_id: str, db: Session = Depends(get_db)):
    return [_contact_dict(c) for c in get_contacts_for_creator(db, creator_id)]


@router.patch("/contacts/{contact_id}/validate")
def validate(
    contact_id: str, is_valid: bool, notes: Optional[str] = None,
    reviewer: str = "internal", db: Session = Depends(get_db)
):
    try:
        c = validate_contact(db, contact_id, is_valid, notes, reviewer)
        return _contact_dict(c)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/{creator_id}/analysis")
def get_creator_analysis(creator_id: str, db: Session = Depends(get_db)):
    from app.models.creator import Analysis
    analysis = (
        db.query(Analysis)
        .filter(Analysis.creator_id == creator_id)
        .order_by(Analysis.analyzed_at.desc())
        .first()
    )
    if not analysis:
        raise HTTPException(404, "No analysis found for this creator")
    return {
        "id": analysis.id,
        "creator_id": analysis.creator_id,
        "analysis_type": analysis.analysis_type,
        "engagement_quality_score": analysis.engagement_quality_score,
        "audience_demand_signals": analysis.audience_demand_signals or {},
        "content_themes": analysis.content_themes or [],
        "brand_safety_score": analysis.brand_safety_score,
        "recommended_niches": analysis.recommended_niches or [],
        "audience_pain_points": analysis.audience_pain_points or [],
        "summary": analysis.summary,
        "raw_output": analysis.raw_output,
        "model_used": analysis.model_used,
        "analyzed_at": analysis.analyzed_at.isoformat() if analysis.analyzed_at else None,
    }


def _creator_dict(c: Creator) -> dict:
    reply_classification = None
    reply_text = None
    product_concepts = []
    selected_concept_id = None
    selected_concept = None
    try:
        if c.discovery_notes and c.discovery_notes.startswith("{"):
            import json
            parsed = json.loads(c.discovery_notes)
            reply_classification = parsed.get("reply_classification")
            reply_text = parsed.get("reply_text")
            product_concepts = parsed.get("product_concepts") or []
            selected_concept_id = parsed.get("selected_concept_id") or parsed.get("selectedConceptId")
            selected_concept = parsed.get("selected_concept") or parsed.get("selectedConcept")
    except Exception:
        pass

    return {
        "id": c.id, "handle": c.handle, "platform": c.platform,
        "display_name": c.display_name, "bio": c.bio,
        "profile_url": c.profile_url, "avatar_url": c.avatar_url,
        "follower_count": c.follower_count, "niche": c.niche or [],
        "location": c.location, "website": c.website,
        "email_public": c.email_public, "status": c.status,
        "reply_classification": reply_classification,
        "reply_text": reply_text,
        "product_concepts": product_concepts,
        "productConcepts": product_concepts,
        "selected_concept_id": selected_concept_id,
        "selectedConceptId": selected_concept_id,
        "selected_concept": selected_concept,
        "selectedConcept": selected_concept,
        "discovery_source": c.discovery_source,
        "engagement_score": c.engagement_score,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def _rec_dict(r) -> dict:
    return {
        "id": r.id, "product_name": r.product_name, "product_category": r.product_category,
        "tagline": r.tagline, "description": r.description,
        "revenue_potential": r.revenue_potential, "confidence_score": r.confidence_score,
        "status": r.status,
    }


def _contact_dict(c) -> dict:
    return {
        "id": c.id, "contact_type": c.contact_type, "value": c.value,
        "source": c.source, "is_verified": c.is_verified, "is_valid": c.is_valid,
        "is_suppressed": c.is_suppressed, "notes": c.notes,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }



