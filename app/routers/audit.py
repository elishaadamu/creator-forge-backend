from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.audit import AuditLog, Review

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("/logs")
def list_logs(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    action: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    q = db.query(AuditLog)
    if entity_type:
        q = q.filter(AuditLog.entity_type == entity_type)
    if entity_id:
        q = q.filter(AuditLog.entity_id == entity_id)
    if action:
        q = q.filter(AuditLog.action == action)
    logs = q.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit).all()
    return [
        {
            "id": l.id, "entity_type": l.entity_type, "entity_id": l.entity_id,
            "action": l.action, "actor": l.actor, "details": l.details,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        for l in logs
    ]


@router.get("/reviews")
def list_reviews(
    entity_type: Optional[str] = None,
    decision: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    q = db.query(Review)
    if entity_type:
        q = q.filter(Review.entity_type == entity_type)
    if decision:
        q = q.filter(Review.decision == decision)
    reviews = q.order_by(Review.reviewed_at.desc()).offset(skip).limit(limit).all()
    return [
        {
            "id": r.id, "entity_type": r.entity_type, "entity_id": r.entity_id,
            "reviewer": r.reviewer, "decision": r.decision, "notes": r.notes,
            "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
        }
        for r in reviews
    ]


@router.get("/logs/{log_id}/inspect")
def inspect_log(
    log_id: str,
    db: Session = Depends(get_db),
):
    log = db.get(AuditLog, log_id)
    if not log:
        return {"status": "error", "message": "Log not found"}
    
    res = {
        "id": log.id,
        "entity_type": log.entity_type,
        "entity_id": log.entity_id,
        "action": log.action,
        "actor": log.actor,
        "details": log.details or {},
        "created_at": log.created_at.isoformat() if log.created_at else None,
        "ip_address": log.ip_address,
        "entity_details": None
    }
    
    try:
        from app.models.creator import Creator
        from app.models.campaign import Campaign
        from app.models.outreach import OutreachMessage
        
        # Check by entity_type or from details dictionary
        creator_id = log.entity_id if log.entity_type == "creator" else log.details.get("creator_id") if isinstance(log.details, dict) else None
        campaign_id = log.entity_id if log.entity_type == "campaign" else log.details.get("campaign_id") if isinstance(log.details, dict) else None
        message_id = log.entity_id if log.entity_type == "outreach_message" else log.details.get("message_id") if isinstance(log.details, dict) else None
        
        if creator_id:
            creator = db.get(Creator, creator_id)
            if creator:
                res["entity_details"] = {
                    "type": "creator",
                    "id": creator.id,
                    "handle": creator.handle,
                    "platform": creator.platform,
                    "name": creator.display_name,
                    "follower_count": creator.follower_count,
                    "profile_pic": creator.avatar_url,
                    "status": creator.status,
                    "ai_status": "analyzed" if creator.analyses else "unprocessed",
                }
        elif campaign_id:
            campaign = db.get(Campaign, campaign_id)
            if campaign:
                res["entity_details"] = {
                    "type": "campaign",
                    "id": campaign.id,
                    "name": campaign.name,
                    "status": campaign.status,
                    "daily_send_limit": campaign.daily_send_limit,
                    "total_sent": campaign.total_sent,
                }
        elif message_id:
            msg = db.get(OutreachMessage, message_id)
            if msg:
                creator_handle = None
                if msg.creator_id:
                    creator = db.get(Creator, msg.creator_id)
                    if creator:
                        creator_handle = f"@{creator.handle} ({creator.platform})"
                
                res["entity_details"] = {
                    "type": "outreach_message",
                    "id": msg.id,
                    "subject": msg.subject,
                    "body": msg.body,
                    "status": msg.status,
                    "sent_at": msg.sent_at.isoformat() if msg.sent_at else None,
                    "send_method": msg.send_method,
                    "creator_handle": creator_handle,
                }
    except Exception as e:
        res["entity_details_error"] = str(e)
        
    return res

