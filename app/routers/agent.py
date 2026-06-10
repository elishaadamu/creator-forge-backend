"""
Agent Router — batch pipeline endpoints.
These are called by Vercel Cron Jobs (daily at 9am UTC) or manually
from the Ops Dashboard. Each endpoint runs one phase of the pipeline.
"""
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional, List
import asyncio

from app.database import get_db
from app.config import settings
from app.models.creator import Creator
from app.services.scraper import scrape_profile
from app.services import analysis as analysis_svc
from app.services import product_recommendation as rec_svc
from app.services import outreach_generator as outreach_svc
from app.services import followup as followup_svc
from app.services import contact_discovery as contact_svc
from app.services import audit as audit_svc

router = APIRouter(prefix="/api/agent", tags=["agent"])


# ── Status ───────────────────────────────────────────────────────────────────

_agent_status = {"running": False, "last_run": None, "last_result": None}


@router.get("/status")
def agent_status():
    """Return current agent run status."""
    return {
        **_agent_status,
        "config": {
            "ai_configured":    bool(settings.ANTHROPIC_API_KEY),
            "apify_configured": bool(settings.APIFY_API_KEY),
            "email_configured": bool(settings.SENDGRID_API_KEY),
            "daily_send_limit": settings.DAILY_SEND_LIMIT_DEFAULT,
            "auto_send_enabled": settings.AUTO_SEND_ENABLED,
        }
    }


# ── Phase 1 — Scrape + store creator profiles ─────────────────────────────────

@router.post("/run-discovery")
def run_discovery(
    handles: List[str],
    platform: str = "youtube",
    db: Session = Depends(get_db),
):
    """
    Scrape a list of creator handles and save them to the database.
    Maximum 50 handles per call.
    """
    import uuid
    from datetime import datetime

    results = {"scraped": 0, "skipped": 0, "errors": []}
    for handle in handles[:50]:
        handle = handle.strip().lstrip("@")
        if not handle:
            continue
        # Check if already exists
        existing = db.query(Creator).filter(
            Creator.handle == handle,
            Creator.platform == platform,
        ).first()
        if existing:
            results["skipped"] += 1
            continue

        try:
            data = scrape_profile(platform, handle)
            if "error" in data and not data.get("follower_count"):
                results["errors"].append({"handle": handle, "error": data["error"]})
                continue

            creator = Creator(
                id=str(uuid.uuid4()),
                handle=data.get("handle", handle),
                platform=platform,
                display_name=data.get("display_name", handle),
                bio=data.get("bio", ""),
                profile_url=data.get("profile_url", ""),
                avatar_url=data.get("avatar_url", ""),
                follower_count=data.get("follower_count", 0),
                niche=data.get("niche", []),
                website=data.get("website", ""),
                email_public=data.get("email_public", ""),
                status="discovered",
                discovery_source="manual_scrape",
            )
            db.add(creator)
            db.commit()
            results["scraped"] += 1

            audit_svc.log(
                db, action="creator_scraped",
                entity_type="creator", entity_id=creator.id,
                actor="agent", details={"platform": platform, "handle": handle},
            )
        except Exception as e:
            results["errors"].append({"handle": handle, "error": str(e)})

    return results


# ── Phase 2 — AI analysis of all discovered creators ─────────────────────────

@router.post("/run-analysis")
def run_analysis(
    limit: int = 20,
    db: Session = Depends(get_db),
):
    """
    Run AI analysis on all 'discovered' creators above the follower threshold.
    Marks them as 'in_review' after analysis.
    """
    creators = (
        db.query(Creator)
        .filter(
            Creator.status == "discovered",
            Creator.follower_count >= settings.MIN_FOLLOWERS_THRESHOLD,
        )
        .limit(limit)
        .all()
    )

    results = {"analyzed": 0, "skipped": 0, "errors": []}
    for creator in creators:
        try:
            analysis_svc.run_ai_analysis(db, creator.id, actor="agent")
            creator.status = "in_review"
            db.commit()
            results["analyzed"] += 1
        except Exception as e:
            results["errors"].append({"creator_id": creator.id, "error": str(e)})

    return results


# ── Phase 3 — Generate outreach drafts for qualified creators ─────────────────

@router.post("/run-outreach")
def run_outreach(
    campaign_id: str,
    limit: int = 10,
    tone: str = "professional_friendly",
    db: Session = Depends(get_db),
):
    """
    Generate AI outreach drafts for all 'qualified' creators in a campaign.
    All drafts start in 'draft' status and require human review before sending.
    NEVER auto-sends.
    """
    from app.models.creator import ProductRecommendation
    from app.models.outreach import OutreachMessage

    creators = (
        db.query(Creator)
        .filter(Creator.status == "qualified")
        .limit(limit)
        .all()
    )

    results = {"drafted": 0, "skipped": 0, "errors": []}
    for creator in creators:
        # Skip if already has a pending/sent message in this campaign
        existing = (
            db.query(OutreachMessage)
            .filter(
                OutreachMessage.creator_id == creator.id,
                OutreachMessage.campaign_id == campaign_id,
            )
            .first()
        )
        if existing:
            results["skipped"] += 1
            continue

        # Get best product recommendation, or generate one if not exists
        rec = (
            db.query(ProductRecommendation)
            .filter(ProductRecommendation.creator_id == creator.id)
            .order_by(ProductRecommendation.confidence_score.desc())
            .first()
        )
        if not rec:
            try:
                from app.services import product_recommendation as rec_svc
                recs = rec_svc.generate_recommendations(db, creator.id, actor="agent")
                if recs:
                    rec = recs[0]
            except Exception as e:
                results["errors"].append({"creator_id": creator.id, "error": f"Failed to generate product recommendation: {e}"})
                continue

        if not rec:
            results["skipped"] += 1
            continue

        # Auto-approve recommendation for agent pipeline if it's in draft
        if rec.status == "draft":
            try:
                from app.services import product_recommendation as rec_svc
                rec_svc.approve_recommendation(db, rec.id, reviewer="agent", notes="Auto-approved by agent pipeline")
            except Exception as e:
                results["errors"].append({"creator_id": creator.id, "error": f"Failed to approve product recommendation: {e}"})
                continue

        try:
            msg = outreach_svc.generate_outreach_draft(
                db=db,
                creator_id=creator.id,
                campaign_id=campaign_id,
                contact_id=None,
                product_recommendation_id=rec.id,
                tone=tone,
                actor="agent",
            )
            # Submit for review so it shows up in "Needs Review" in the Ops Dashboard
            outreach_svc.submit_for_review(db, msg.id, actor="agent")
            results["drafted"] += 1
        except Exception as e:
            results["errors"].append({"creator_id": creator.id, "error": str(e)})

    return results


# ── Phase 4 — Generate follow-ups for eligible threads ────────────────────────

@router.post("/run-followups")
def run_followups(
    limit: int = 20,
    db: Session = Depends(get_db),
):
    """
    Generate AI follow-up drafts for eligible open threads.
    Rules enforced: max 2 follow-ups, 7-day minimum gap, no follow-up if already replied.
    All follow-ups require human review before send.
    """
    from app.models.outreach import Thread

    threads = (
        db.query(Thread)
        .filter(Thread.status == "open")
        .limit(limit)
        .all()
    )

    results = {"generated": 0, "skipped": 0, "errors": []}
    for thread in threads:
        can_do, reason = followup_svc.can_follow_up(db, thread.id)
        if not can_do:
            results["skipped"] += 1
            continue
        try:
            followup_svc.generate_followup(db, thread.id, actor="agent")
            results["generated"] += 1
        except Exception as e:
            results["errors"].append({"thread_id": thread.id, "error": str(e)})

    return results


# ── Full pipeline run (convenience — calls all phases) ────────────────────────

@router.post("/run-full-pipeline")
def run_full_pipeline(
    campaign_id: str,
    db: Session = Depends(get_db),
):
    """
    Run all pipeline phases in sequence. Called by Vercel Cron at 9am UTC daily.
    Returns a summary of each phase.
    """
    import datetime

    _agent_status["running"] = True
    _agent_status["last_run"] = datetime.datetime.utcnow().isoformat()

    summary = {}

    try:
        analysis_result = run_analysis(limit=50, db=db)
        summary["analysis"] = analysis_result

        outreach_result = run_outreach(campaign_id=campaign_id, limit=10, db=db)
        summary["outreach"] = outreach_result

        followup_result = run_followups(limit=20, db=db)
        summary["followups"] = followup_result

    except Exception as e:
        summary["error"] = str(e)

    _agent_status["running"] = False
    _agent_status["last_result"] = summary
    return summary


# ── Analytics summary ─────────────────────────────────────────────────────────

@router.get("/analytics-summary")
def analytics_summary(db: Session = Depends(get_db)):
    """Pipeline analytics for the ops dashboard."""
    from app.models.outreach import OutreachMessage, Thread, Reply
    from app.models.creator import Campaign

    total_scraped   = db.query(Creator).count()
    total_qualified = db.query(Creator).filter(Creator.status == "qualified").count()
    total_sent      = db.query(OutreachMessage).filter(OutreachMessage.status == "sent").count()
    total_replies   = db.query(Reply).count()
    total_threads   = db.query(Thread).count()

    return {
        "total_scraped":       total_scraped,
        "total_qualified":     total_qualified,
        "total_outreach_sent": total_sent,
        "total_replies":       total_replies,
        "total_interested":    0,  # TODO: query by classification
        "total_converted":     db.query(Thread).filter(Thread.status == "converted").count(),
        "reply_rate":          round(total_replies / total_sent * 100, 1) if total_sent else 0,
        "open_rate":           0,  # Requires SendGrid tracking webhooks
        "campaigns":           [],
    }
