from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime

from app.database import get_db
from app.models.creator import Creator, ProductRecommendation, PostSuggestion
from app.services import content_calendar as calendar_svc


router = APIRouter(prefix="/api/calendar", tags=["calendar"])


class GenerateCalendarRequest(BaseModel):
    creator_id: str
    product_recommendation_id: str


class SuggestionResponse(BaseModel):
    id: str
    creator_id: str
    product_recommendation_id: str
    hook: str
    body: str
    platform: str
    status: str
    scheduled_for: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("/{creator_id}", response_model=List[SuggestionResponse])
def get_creator_calendar(creator_id: str, db: Session = Depends(get_db)):
    """Retrieve all content suggestions (calendar posts) for a creator."""
    posts = (
        db.query(PostSuggestion)
        .filter(PostSuggestion.creator_id == creator_id)
        .order_by(PostSuggestion.scheduled_for.asc())
        .all()
    )
    return posts


@router.post("/generate", response_model=List[SuggestionResponse])
def generate_creator_calendar(body: GenerateCalendarRequest, db: Session = Depends(get_db)):
    """Generate 5 fresh AI post suggestions to promote a product idea."""
    try:
        posts = calendar_svc.generate_calendar(
            db=db,
            creator_id=body.creator_id,
            product_rec_id=body.product_recommendation_id,
            actor="ops_dashboard"
        )
        return posts
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Error generating calendar: {str(e)}")


@router.post("/{post_id}/approve", response_model=SuggestionResponse)
def approve_calendar_post(post_id: str, db: Session = Depends(get_db)):
    """Approve a post draft to move it to 'approved' status."""
    post = db.get(PostSuggestion, post_id)
    if not post:
        raise HTTPException(404, "Post suggestion not found")
    post.status = "approved"
    db.commit()
    db.refresh(post)
    return post


@router.post("/{post_id}/queue", response_model=SuggestionResponse)
def queue_calendar_post(post_id: str, db: Session = Depends(get_db)):
    """Queue an approved post suggestion for automatic publishing."""
    post = db.get(PostSuggestion, post_id)
    if not post:
        raise HTTPException(404, "Post suggestion not found")
    if post.status != "approved":
        post.status = "approved"  # Auto approve if not already
    post.status = "queued"
    db.commit()
    db.refresh(post)
    return post


@router.post("/{post_id}/post", response_model=SuggestionResponse)
def publish_calendar_post(post_id: str, db: Session = Depends(get_db)):
    """Simulate publishing the post to the social platform (sets status to 'posted')."""
    post = db.get(PostSuggestion, post_id)
    if not post:
        raise HTTPException(404, "Post suggestion not found")
    post.status = "posted"
    db.commit()
    db.refresh(post)
    return post
