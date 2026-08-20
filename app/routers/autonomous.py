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
