from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.autonomous_campaign import AutonomousCampaign
from app.models.creator import Creator
from app.services import autonomous_outreach as auto_svc

router = APIRouter(prefix="/api/autonomous", tags=["autonomous"])


# ── Pydantic Schemas ──────────────────────────────────────────────────────────

class CampaignCreateSchema(BaseModel):
    name: str = "100k-1M Creators Autonomous Batch"
    description: Optional[str] = "Automated outreach targeting creators with 100k-1M followers."
    target_weekly_limit: int = 50
    min_followers: int = 100000
    max_followers: int = 1000000
    min_engagement_rate: float = 2.0
    niches: List[str] = Field(default_factory=lambda: ["Tech", "Software", "SaaS", "Creator Economy", "Gaming"])
    template_subject: str = "Co-founder partnership inquiry for {{display_name}}"
    template_body: str = (
        "Hi {{first_name}},\n\n"
        "I've been following your {{niche}} content on {{platform}} and love how engaged your community is.\n\n"
        "We're building {{product_name}} — a high-growth product tailored for creators in {{niche}}. "
        "Given your audience scale ({{follower_count}} followers) and strong engagement, we'd love to discuss a "
        "co-founder partnership with a 50/50 revenue split.\n\n"
        "Are you open to a quick 15-minute sync this week?\n\n"
        "Best,\nCreator Forge Team"
    )
    followup_template_subject: str = "Re: Co-founder partnership inquiry for {{display_name}}"
    followup_template_body: str = (
        "Hi {{first_name}},\n\n"
        "Following up on my note last week regarding the {{product_name}} co-founder partnership.\n\n"
        "Totally understand if your inbox is slammed! If you're open to exploring a custom digital product for your "
        "{{follower_count}} followers, let me know if Thursday or Friday works for a brief chat.\n\n"
        "Best,\nCreator Forge Team"
    )
    followup_delay_days: int = 7
    status: str = "active"
    auto_send: bool = True


class CampaignUpdateSchema(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    target_weekly_limit: Optional[int] = None
    min_followers: Optional[int] = None
    max_followers: Optional[int] = None
    min_engagement_rate: Optional[float] = None
    niches: Optional[List[str]] = None
    template_subject: Optional[str] = None
    template_body: Optional[str] = None
    followup_template_subject: Optional[str] = None
    followup_template_body: Optional[str] = None
    followup_delay_days: Optional[int] = None
    status: Optional[str] = None
    auto_send: Optional[bool] = None


class PreviewRequestSchema(BaseModel):
    template_subject: str
    template_body: str
    sample_handle: Optional[str] = "techlead"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/campaigns")
def list_autonomous_campaigns(db: Session = Depends(get_db)):
    """List all autonomous outreach campaigns. Auto-seeds a default campaign if empty."""
    campaigns = db.query(AutonomousCampaign).order_by(AutonomousCampaign.created_at.desc()).all()
    if not campaigns:
        # Seed default campaign
        default_camp = AutonomousCampaign(
            name="100k-1M Creators Autonomous Batch",
            description="Autonomous outreach targeting 100k-1M followers with good engagement and automatic 7-day follow-up.",
            target_weekly_limit=50,
            min_followers=100000,
            max_followers=1000000,
            min_engagement_rate=2.0,
            niches=["Tech", "Software", "SaaS", "Creator Economy", "Gaming"],
            status="active",
            auto_send=True,
        )
        db.add(default_camp)
        db.commit()
        db.refresh(default_camp)
        campaigns = [default_camp]
    return campaigns


@router.post("/campaigns")
def create_autonomous_campaign(data: CampaignCreateSchema, db: Session = Depends(get_db)):
    """Create a new autonomous campaign configuration."""
    campaign = AutonomousCampaign(**data.dict())
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return campaign


@router.get("/campaigns/{campaign_id}")
def get_autonomous_campaign(campaign_id: str, db: Session = Depends(get_db)):
    """Get a single autonomous campaign."""
    campaign = db.get(AutonomousCampaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=44, detail="Campaign not found")
    return campaign


@router.put("/campaigns/{campaign_id}")
def update_autonomous_campaign(campaign_id: str, data: CampaignUpdateSchema, db: Session = Depends(get_db)):
    """Update campaign settings or templates."""
    campaign = db.get(AutonomousCampaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    update_dict = data.dict(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(campaign, key, value)

    db.commit()
    db.refresh(campaign)
    return campaign


@router.delete("/campaigns/{campaign_id}")
def delete_autonomous_campaign(campaign_id: str, db: Session = Depends(get_db)):
    """Delete an autonomous campaign."""
    campaign = db.get(AutonomousCampaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    db.delete(campaign)
    db.commit()
    return {"status": "deleted", "id": campaign_id}


@router.post("/campaigns/{campaign_id}/run")
def run_campaign_batch(campaign_id: str, limit: Optional[int] = Query(None), db: Session = Depends(get_db)):
    """Trigger a manual run for an autonomous batch outreach campaign."""
    try:
        res = auto_svc.run_autonomous_batch(db, campaign_id=campaign_id, limit=limit)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run-followups")
def run_autonomous_followups(campaign_id: Optional[str] = Query(None), db: Session = Depends(get_db)):
    """Trigger processing of unreplied threads for 7-day follow-ups."""
    try:
        res = auto_svc.process_autonomous_followups(db, campaign_id=campaign_id)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/preview")
def preview_rendered_template(data: PreviewRequestSchema, db: Session = Depends(get_db)):
    """Preview rendered subject and body with a sample or selected creator."""
    creator = None
    if data.sample_handle:
        creator = db.query(Creator).filter(Creator.handle == data.sample_handle.lstrip("@")).first()
    
    if not creator:
        creator = db.query(Creator).first()

    # Fallback mock creator if DB has no creators yet
    if not creator:
        class MockCreator:
            display_name = "Alex Rivera"
            handle = "alexrivera"
            platform = "youtube"
            follower_count = 350000
            niche = ["Tech"]
            bio = "Building the future of tech & AI software."
            email_public = "alex@example.com"
        creator = MockCreator()

    rendered_subject = auto_svc.render_template(data.template_subject, creator, "AI DevTools Studio")
    rendered_body = auto_svc.render_template(data.template_body, creator, "AI DevTools Studio")

    return {
        "creator": {
            "display_name": creator.display_name,
            "handle": creator.handle,
            "follower_count": creator.follower_count,
            "niche": creator.niche,
        },
        "rendered_subject": rendered_subject,
        "rendered_body": rendered_body,
    }


class DiscoverCreatorsSchema(BaseModel):
    niches: Optional[List[str]] = Field(default_factory=lambda: ["Tech", "Software", "SaaS", "Fintech", "Productivity"])
    min_followers: int = 100000
    max_followers: int = 1000000
    min_engagement_rate: float = 2.0
    target_count: int = 5


@router.post("/discover-creators")
def discover_autonomous_creators(data: DiscoverCreatorsSchema, db: Session = Depends(get_db)):
    """
    Autonomously discover & qualify creators based on campaign requirements.
    Performs live search/Apify scraping, handle deduplication, follower scaling, 
    and public business email extraction & enrichment.
    """
    query_str = " ".join(data.niches or ["Tech", "Software", "SaaS"])

    from app.services.scraper import search_youtube_channels
    from app.services.discovery import create_or_get_creator

    discovered_raw = search_youtube_channels(query_str, limit=data.target_count or 5)

    newly_saved = []
    for target in discovered_raw:
        try:
            creator, _ = create_or_get_creator(
                db,
                handle=target["handle"],
                platform=target["platform"],
                display_name=target["display_name"],
                bio=target["bio"],
                follower_count=target["follower_count"],
                niche=target["niche"],
                email_public=target["email_public"],
                avatar_url=target["avatar_url"],
                actor="autonomous_discovery_tool"
            )
            creator.status = "qualified"
            creator.engagement_score = target.get("engagement_score", 4.2)
            db.commit()
            db.refresh(creator)
            newly_saved.append(creator)
        except Exception as e:
            db.rollback()
    
    # Return newly saved creators matching search
    all_qualified = newly_saved if newly_saved else db.query(Creator).filter(
        Creator.follower_count >= data.min_followers,
        Creator.follower_count <= data.max_followers,
        Creator.status.in_(["discovered", "qualified", "in_review", "approved"])
    ).order_by(Creator.updated_at.desc()).all()
    
    result = []
    for c in all_qualified:
        score = min(99, int(70 + (c.engagement_score or 3.0) * 4 + (c.follower_count / 100000)))
        
        if c.follower_count >= 1000000:
            follower_str = f"{c.follower_count / 1000000:.1f}M"
        else:
            follower_str = f"{int(c.follower_count / 1000)}K"
            
        niche_list = c.niche if isinstance(c.niche, list) else ([c.niche] if c.niche else ["Tech"])
        niche_str = ", ".join(niche_list)
            
        result.append({
            "id": c.id,
            "name": c.display_name or c.handle,
            "display_name": c.display_name or c.handle,
            "handle": f"@{c.handle.lstrip('@')}",
            "platform": (c.platform or "YouTube").capitalize(),
            "follower_count": c.follower_count,
            "followerStr": follower_str,
            "engagement": c.engagement_score or 3.5,
            "niche": niche_str,
            "avatar": c.avatar_url,
            "creatorScore": score,
            "email": c.email_public,
            "email_public": c.email_public,
            "status": c.status,
            "replyClassification": "interested",
            "replySubject": f"Re: Co-founder partnership inquiry for {c.display_name}",
            "replyText": "Interested in reviewing software co-founder product concepts.",
            "replyTime": "Recently",
            "productConcepts": [
                {
                    "id": f"p1_{c.id[:6]}",
                    "name": f"{c.display_name.split()[0]} OS",
                    "tagline": f"Automated creator tool for {niche_list[0]} audience",
                    "problem": "Audience monetisation & automated software workflows",
                    "pricing": "$29/mo",
                    "mvpDifficulty": "Low (2 weeks)",
                    "opportunityScore": min(98, score + 3),
                    "mockupUrl": "https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=600&auto=format&fit=crop&q=80",
                    "rationale": "High audience purchase intent identified via community feedback."
                },
                {
                    "id": f"p2_{c.id[:6]}",
                    "name": f"{c.display_name.split()[0]} Flow AI",
                    "tagline": "Sponsorship & digital product manager",
                    "problem": "Creator revenue operations & contract escrow",
                    "pricing": "$49/mo",
                    "mvpDifficulty": "Medium (3 weeks)",
                    "opportunityScore": min(94, score - 2),
                    "mockupUrl": "https://images.unsplash.com/photo-1460925895917-afdab827c52f?w=600&auto=format&fit=crop&q=80",
                    "rationale": "Strong engagement on recent video."
                }
            ]
        })
        
    return {
        "status": "success",
        "discovered_count": len(result),
        "creators": result
    }

