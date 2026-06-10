import re
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.creator import Creator, Analysis, ProductRecommendation, Deck
from app.services.scraper import scrape_profile
from app.services import discovery
from app.services import analysis as analysis_svc
from app.services import product_recommendation as rec_svc
from app.services import deck_generator


router = APIRouter(prefix="/api/public", tags=["public"])


class ApplyRequest(BaseModel):
    handle: str
    platform: str = "youtube"


@router.post("/apply")
def public_apply(body: ApplyRequest, db: Session = Depends(get_db)):
    """
    Public Endpoint: A creator enters their handle to see what product fits their audience.
    Runs automated scraper, AI analysis, recommendations, and generates a pitch deck.
    Returns a teaser results payload (with gated content) to maximize sign-up conversion.
    """
    handle = body.handle.strip()
    platform = body.platform.strip().lower()

    # Basic sanitization of handle (match what creators.py does)
    if platform == "youtube":
        handle = handle.replace("https://www.youtube.com/", "").replace("youtube.com/", "")
        if handle.startswith("@"):
            pass
    elif platform == "instagram":
        handle = handle.replace("https://www.instagram.com/", "").replace("instagram.com/", "").strip("/")
    elif platform == "tiktok":
        handle = handle.replace("https://www.tiktok.com/", "").replace("tiktok.com/", "").strip("/")

    # Check if already exists in DB
    creator = db.query(Creator).filter(
        Creator.handle == handle,
        Creator.platform == platform
    ).first()

    created_new = False
    if not creator:
        # 1. Scrape profile
        try:
            scraped = scrape_profile(platform, handle)
            if "error" in scraped and not scraped.get("display_name"):
                raise HTTPException(400, f"Could not scrape creator profile: {scraped['error']}")
        except Exception as e:
            raise HTTPException(400, f"Scrape failed: {str(e)}")

        # 2. Save Creator
        try:
            creator, created_new = discovery.create_or_get_creator(
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
                discovery_source="public_portal_apply",
                actor="public_user",
            )
        except ValueError as e:
            raise HTTPException(400, str(e))

    # Get or run Analysis
    analysis = db.query(Analysis).filter(Analysis.creator_id == creator.id).order_by(Analysis.analyzed_at.desc()).first()
    if not analysis:
        try:
            analysis = analysis_svc.run_ai_analysis(db, creator.id, actor="public_user")
        except Exception as e:
            # Create a basic placeholder analysis if AI fails
            analysis = Analysis(
                creator_id=creator.id,
                engagement_quality_score=5.0,
                summary="Analysis pending review.",
                model_used="none"
            )
            db.add(analysis)
            db.commit()
            db.refresh(analysis)

    # Get or run Recommendations
    recs = db.query(ProductRecommendation).filter(ProductRecommendation.creator_id == creator.id).all()
    if not recs:
        try:
            recs = rec_svc.generate_recommendations(db, creator.id, actor="public_user")
        except Exception as e:
            raise HTTPException(500, f"Failed to generate product recommendations: {str(e)}")

    # Get top recommendation and auto-approve it so it's ready for deck generation
    top_rec = sorted(recs, key=lambda r: r.confidence_score or 0, reverse=True)[0] if recs else None
    if top_rec and top_rec.status == "draft":
        top_rec.status = "approved"
        db.commit()
        db.refresh(top_rec)

    # Get or run Deck
    deck = None
    if top_rec:
        deck = db.query(Deck).filter(
            Deck.creator_id == creator.id,
            Deck.product_recommendation_id == top_rec.id
        ).first()
        if not deck:
            try:
                deck = deck_generator.generate_deck(db, creator.id, top_rec.id, actor="public_user")
            except Exception:
                pass

    # Build the Teaser Response (Gating detailed info)
    gated_recs = []
    for r in recs:
        is_top = (top_rec and r.id == top_rec.id)
        gated_recs.append({
            "id": r.id,
            "product_name": r.product_name if is_top else "[Locked - Sign Up to Unlock]",
            "product_category": r.product_category,
            "tagline": r.tagline if is_top else "Sign up to view this idea's details",
            "revenue_potential": r.revenue_potential if is_top else "[Locked]",
            "description": r.description if is_top else "",
            "confidence_score": r.confidence_score,
            "is_top_recommendation": is_top
        })

    slide_teasers = []
    if deck and deck.slides:
        # Only expose titles to public
        for slide in deck.slides:
            slide_teasers.append({
                "title": slide.get("title", "Slide"),
                "type": slide.get("type", "content"),
                "body": "[Locked - Sign up to unlock full pitch deck]"
            })

    return {
        "creator": {
            "display_name": creator.display_name,
            "handle": creator.handle,
            "platform": creator.platform,
            "follower_count": creator.follower_count,
            "avatar_url": creator.avatar_url,
            "niche": creator.niche
        },
        "analysis_teaser": {
            "score": analysis.engagement_quality_score,
            "summary": analysis.summary,
            "brand_safety": analysis.brand_safety_score
        },
        "product_ideas_teaser": gated_recs,
        "pitch_deck_teaser": {
            "title": deck.title if deck else "Launch Presentation",
            "slides": slide_teasers,
            "gated": True
        },
        "signup_required": True,
        "message": "Verify your email to unlock all 3 product ideas, the full pitch deck, and your automated venture launch!"
    }
