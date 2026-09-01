# -*- coding: utf-8 -*-
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.project import (
    CoLaunchProject, ValidationPlan, ValidationCampaign,
    CreatorCampaignTask, ValidationTelemetry, ValidationGateDecision
)
from app.models.creator import Creator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["projects"])


# Pydantic Schemas
class CreateProjectRequest(BaseModel):
    id: Optional[str] = None
    creatorId: Optional[str] = None
    creatorHandle: Optional[str] = None
    creatorName: Optional[str] = None
    creatorAvatar: Optional[str] = None
    creatorEmail: Optional[str] = None
    niche: Optional[str] = None
    followers: Optional[str] = None
    productName: str
    productTagline: Optional[str] = None
    targetAudience: Optional[str] = None
    customer: Optional[str] = None
    problem: Optional[str] = None
    keyFeatures: Optional[List[str]] = None
    pricing: Optional[str] = None
    revenueModel: Optional[str] = None
    presaleTarget: Optional[float] = 5000.0
    selectedConcept: Optional[Dict[str, Any]] = None
    mockup: Optional[Dict[str, Any]] = None


class UpdatePlanRequest(BaseModel):
    customer: Optional[str] = None
    problem: Optional[str] = None
    offer: Optional[str] = None
    pricing: Optional[str] = None
    test_method: Optional[str] = None
    period: Optional[str] = "14 days"
    threshold: Optional[str] = "$5,000 in presales within 14 days"
    target_revenue: Optional[float] = 5000.0
    status: Optional[str] = "ready"


class UpdateCampaignRequest(BaseModel):
    product_assets: Optional[Dict[str, Any]] = None
    infrastructure: Optional[Dict[str, Any]] = None
    research_survey: Optional[Dict[str, Any]] = None
    review_status: Optional[str] = None # 'draft', 'approved', 'launched'


class UpdateTaskRequest(BaseModel):
    status: Optional[str] = None # 'pending', 'today', 'completed', 'skipped'
    content_draft: Optional[str] = None
    cta_text: Optional[str] = None
    tracking_link: Optional[str] = None


class AddReservationRequest(BaseModel):
    name: str
    email: str
    amount: float
    tier: Optional[str] = "Founding Member"
    channel: Optional[str] = "instagram"


class GateDecisionRequest(BaseModel):
    decision: str # 'pass_to_phase2', 'iterate_validation', 'kill_project'
    notes: Optional[str] = None


class TrackVisitRequest(BaseModel):
    slug: Optional[str] = None
    projectId: Optional[str] = None
    channel: Optional[str] = "Direct / Other"
    ref: Optional[str] = None
    path: Optional[str] = None


def _format_project_response(proj: CoLaunchProject) -> Dict[str, Any]:
    plan = proj.validation_plan
    campaign = proj.validation_campaign
    telemetry = proj.telemetry
    tasks = [
        {
            "id": t.id,
            "dayNumber": t.day_number,
            "channel": t.channel,
            "title": t.task_title,
            "content": t.content_draft,
            "cta": t.cta_text,
            "trackingLink": t.tracking_link,
            "mediaPrompt": t.media_prompt,
            "status": t.status,
            "completedAt": t.completed_at.isoformat() if t.completed_at else None,
        }
        for t in (proj.creator_tasks or [])
    ]
    gate_decisions = [
        {
            "id": g.id,
            "decision": g.decision,
            "targetRevenue": g.target_revenue,
            "achievedRevenue": g.achieved_revenue,
            "backersCount": g.backers_count,
            "conversionRate": g.conversion_rate,
            "gateStatus": g.gate_status,
            "notes": g.gate_notes,
            "decidedAt": g.decided_at.isoformat() if g.decided_at else None,
        }
        for g in (proj.gate_decisions or [])
    ]

    return {
        "id": proj.id,
        "creatorId": proj.creator_id,
        "creatorHandle": proj.creator_handle,
        "creatorName": proj.creator_name,
        "creatorAvatar": proj.creator_avatar,
        "creatorEmail": proj.creator_email,
        "niche": proj.niche,
        "followers": proj.followers,
        "productName": proj.product_name,
        "productTagline": proj.product_tagline,
        "targetAudience": proj.target_audience,
        "pricing": proj.pricing,
        "revenueModel": proj.revenue_model,
        "currentPhase": proj.current_phase,
        "currentStep": proj.current_step,
        "status": proj.status,
        "presaleTarget": proj.presale_target,
        "currentPresales": proj.current_presales,
        "visitors": proj.visitors,
        "conversionRate": proj.conversion_rate,
        "portalToken": proj.portal_token,
        "portalLinkSent": proj.portal_link_sent,
        "portalLinkSentTo": proj.portal_link_sent_to,
        "portalLinkSentAt": proj.portal_link_sent_at.isoformat() if proj.portal_link_sent_at else None,
        "selectedConcept": proj.selected_concept,
        "metadataInfo": proj.metadata_info or {},
        "projectFiles": (proj.metadata_info or {}).get("project_files", []),
        "messages": (proj.metadata_info or {}).get("messages", []),
        "activityLogs": (proj.metadata_info or {}).get("activity_logs", []),
        "adminActivity": (proj.metadata_info or {}).get("activity_logs", []),
        "aiActivity": (proj.metadata_info or {}).get("activity_logs", []),
        "reservations": (telemetry.reservations if telemetry else []) or [],
        "currentPresales": float(proj.current_presales or 0.0),
        "visitors": int(proj.visitors or 0),
        "conversionRate": float(proj.conversion_rate or 0.0),
        "createdAt": proj.created_at.isoformat() if proj.created_at else None,
        "updatedAt": proj.updated_at.isoformat() if proj.updated_at else None,
        # Step 1
        "validationPlan": {
            "id": plan.id,
            "customer": plan.customer,
            "problem": plan.problem,
            "offer": plan.offer,
            "pricing": plan.pricing,
            "testMethod": plan.test_method,
            "period": plan.period,
            "threshold": plan.threshold,
            "targetRevenue": plan.target_revenue,
            "status": plan.status,
        } if plan else None,
        # Step 2
        "validationCampaign": {
            "id": campaign.id,
            "productAssets": campaign.product_assets,
            "infrastructure": campaign.infrastructure,
            "researchSurvey": campaign.research_survey,
            "reviewStatus": campaign.review_status,
            "approvedAt": campaign.approved_at.isoformat() if campaign.approved_at else None,
        } if campaign else None,
        "campaignKit": campaign.product_assets if campaign else None,
        "surveyData": campaign.research_survey if campaign else None,
        "infrastructure": campaign.infrastructure if campaign else None,
        # Step 3
        "creatorTasks": tasks,
        # Step 4
        "telemetry": {
            "id": telemetry.id,
            "visitors": telemetry.visitors,
            "views": telemetry.views,
            "ctr": telemetry.ctr,
            "signups": telemetry.signups,
            "presalesCount": telemetry.presales_count,
            "presalesRevenue": telemetry.presales_revenue,
            "conversionRate": telemetry.conversion_rate,
            "reservations": telemetry.reservations or [],
            "channelAttribution": telemetry.channel_attribution or {},
            "experiments": telemetry.experiments or [],
            "feedbackClusters": telemetry.feedback_clusters or [],
        } if telemetry else None,
        # Step 5
        "gateDecisions": gate_decisions,
    }


class RecordPreorderRequest(BaseModel):
    projectId: Optional[str] = None
    slug: Optional[str] = None
    creatorHandle: Optional[str] = None
    name: str
    email: str
    amount: float
    tier: Optional[str] = "Founding Pass"
    paymentMethod: Optional[str] = "Stripe"
    channel: Optional[str] = "direct"
    txId: Optional[str] = None


class LogActivityRequest(BaseModel):
    action: str
    details: Optional[str] = None
    category: Optional[str] = "admin_action"
    step: Optional[str] = "plan"
    phase: Optional[int] = 1


@router.get("")
def list_projects(db: Session = Depends(get_db)):
    """List all co-launch projects."""
    projects = db.query(CoLaunchProject).order_by(CoLaunchProject.created_at.desc()).all()
    return [_format_project_response(p) for p in projects]


def execute_create_co_launch_project(db: Session, body: CreateProjectRequest) -> dict:
    """
    Core implementation to initialize a new Co-Launch Project from concept.
    Initializes the 5-step validation architecture and sends dual notifications to Creator and Admin.
    Can be called directly by background autonomous pipeline without HTTP context.
    """
    # ── Strict Deduplication Guard: Check if project already exists for this creator ──
    existing_creator_proj = None
    if body.creatorId:
        existing_creator_proj = db.query(CoLaunchProject).filter(CoLaunchProject.creator_id == body.creatorId).first()
    if not existing_creator_proj and body.creatorEmail:
        existing_creator_proj = db.query(CoLaunchProject).filter(CoLaunchProject.creator_email == body.creatorEmail).first()

    if existing_creator_proj:
        logger.info(f"[execute_create_co_launch_project] Project {existing_creator_proj.id} already exists for creator {body.creatorId or body.creatorEmail}. Returning existing project to prevent duplicate emails.")
        return _format_project_response(existing_creator_proj)

    proj_id = body.id or f"proj_{int(datetime.utcnow().timestamp()*1000)}"

    # Clean existing if exact ID exists
    existing = db.get(CoLaunchProject, proj_id)
    if existing:
        db.delete(existing)
        db.commit()

    proj = CoLaunchProject(
        id=proj_id,
        creator_id=body.creatorId,
        creator_handle=body.creatorHandle,
        creator_name=body.creatorName or body.creatorHandle,
        creator_avatar=body.creatorAvatar,
        creator_email=body.creatorEmail,
        niche=body.niche,
        followers=body.followers,
        product_name=body.productName,
        product_tagline=body.productTagline or "",
        target_audience=body.customer or body.targetAudience or "",
        pricing=body.pricing or "$29/mo Starter • $79/mo Pro",
        revenue_model=body.revenueModel or "SaaS Subscription",
        current_phase=1,
        current_step="plan",
        status="validating",
        presale_target=body.presaleTarget or 5000.0,
        current_presales=0.0,
        visitors=0,
        conversion_rate=0.0,
        portal_token="cf_sec_live",
        selected_concept=body.selectedConcept or {},
        created_at=datetime.utcnow()
    )
    db.add(proj)
    db.commit()
    db.refresh(proj)

    # 1. Step 1: Create Validation Plan
    customer_desc = body.customer or body.targetAudience or f"{body.niche or 'Creator'} audience and builders"
    problem_desc = body.problem or f"Manual workflows and lack of specialized tooling in {body.niche or 'this space'}"
    offer_desc = f"{body.productName} Founding Co-Launch Access: {body.productTagline or ''}"
    plan = ValidationPlan(
        project_id=proj.id,
        customer=customer_desc,
        problem=problem_desc,
        offer=offer_desc,
        pricing=body.pricing or "$29/mo Starter • $79/mo Pro",
        test_method="1) Co-founder video announcement, 2) 10 user interviews, 3) 48-hour Founding Pre-Order sprint",
        period="14 days",
        threshold=f"${int(body.presaleTarget or 5000):,} in presales within 14 days",
        target_revenue=body.presaleTarget or 5000.0,
        status="ready"
    )
    db.add(plan)

    # 2. Step 2: Build Validation Campaign
    slug = body.productName.lower().replace(" ", "-").replace("'", "")
    campaign = ValidationCampaign(
        project_id=proj.id,
        product_assets={
            "productName": body.productName,
            "productTagline": body.productTagline or "",
            "positioning": f"The #1 automated platform built exclusively for {customer_desc}",
            "headline": f"Finally, an operating system tailored for {body.niche or 'your'} workflows",
            "mockup": body.mockup or {},
            "pricingTiers": [
                {"name": "Founding Member", "price": 99, "period": "lifetime", "perks": "Lifetime core access, private Discord, roadmap voting"},
                {"name": "Starter Plan", "price": 29, "period": "month", "perks": "Full template library, monthly updates, standard support"},
                {"name": "Pro Builder", "price": 79, "period": "month", "perks": "Unlimited syncs, 1-on-1 onboarding, priority feature access"},
            ]
        },
        infrastructure={
            "landingPageUrl": f"/p/{slug}",
            "checkoutUrl": f"/p/{slug}/checkout",
            "waitlistCount": 240,
            "attributionTracking": True,
            "utmSource": "creator_launch"
        },
        research_survey={
            "summary": f"Initial audience feedback survey identifying key pain points in {body.niche or 'niche'}.",
            "questions": [
                {"id": "q1", "question": f"What is your biggest daily roadblock when executing {body.niche or 'work'}?", "type": "text"},
                {"id": "q2", "question": f"Would you pay $29–$79/month for a tool that automates this completely?", "type": "multiple_choice", "options": ["Definitely yes", "Maybe", "No"]},
                {"id": "q3", "question": "What software do you currently stitch together to solve this?", "type": "text"},
            ],
            "responses": []
        },
        review_status="draft"
    )
    db.add(campaign)

    # 3. Step 3: Creator Campaign (14-day schedule)
    sample_tasks = [
        (1, "instagram", "Post Instagram Story #1: The Problem Teaser", f"Hey everyone! I've been noticing how frustrating {problem_desc.lower()} has been lately. Who else deals with this daily?", "Vote on poll + DM me", f"https://launch.app/p/{slug}?utm=ig_story1"),
        (2, "instagram", "Post Instagram Story #2: Behind-The-Scenes Co-Founding", f"Yesterday so many of you replied about this. That's why I'm co-founding {body.productName} to fix it once and for all! Link below to see the first preview.", "Tap link to view preview", f"https://launch.app/p/{slug}?utm=ig_story2"),
        (3, "youtube", "YouTube Video Integration Script (60s Mid-Roll)", f"Before we continue, a quick heads-up: my team and I are launching {body.productName}. If you're tired of {problem_desc.lower()}, we're opening 50 founding spots today at 50% off.", "Check link in top pinned comment", f"https://launch.app/p/{slug}?utm=yt_desc"),
        (5, "newsletter", "Newsletter Broadcast: Founding Cohort Announcement", f"Subject: Building something new with you.\n\nOver the past 6 months, the #1 request I received was a dedicated solution for {body.niche or 'creators'}. Today we're opening presales for {body.productName}.", "Reserve Founding Access ($99)", f"https://launch.app/p/{slug}?utm=newsletter"),
        (7, "twitter", "X / Twitter Breakdown Thread", f"1/5 Why existing tools fail for {customer_desc}.\n\n2/5 How we designed {body.productName} from scratch to cut setup time by 90%.\n\n3/5 Pre-order cohort open now (first 50 members get lifetime updates).", "Read thread & grab pass", f"https://launch.app/p/{slug}?utm=twitter"),
        (10, "instagram", "Post Instagram Story #3: Live Backer Progress", f"Update: We just crossed $3,000 in pre-orders in 48 hours! Only 18 founding member passes remain before prices increase.", "Claim remaining pass", f"https://launch.app/p/{slug}?utm=ig_story3"),
        (14, "youtube", "Community Post & Final Call", f"Closing the founding presale window for {body.productName} tonight at midnight. Huge thank you to the 40+ founding builders who joined!", "Final 6 hours to join", f"https://launch.app/p/{slug}?utm=yt_comm"),
    ]
    for day, chan, title, draft, cta, trk in sample_tasks:
        db.add(CreatorCampaignTask(
            project_id=proj.id,
            day_number=day,
            channel=chan,
            task_title=title,
            content_draft=draft,
            cta_text=cta,
            tracking_link=trk,
            status="today" if day == 1 else "pending"
        ))

    # 4. Step 4: Validation Telemetry
    telemetry = ValidationTelemetry(
        project_id=proj.id,
        visitors=0,
        views=0,
        ctr=0.0,
        signups=0,
        presales_count=0,
        presales_revenue=0.0,
        conversion_rate=0.0,
        reservations=[],
        channel_attribution={"instagram": 0, "youtube": 0, "newsletter": 0, "twitter": 0, "direct": 0},
        experiments=[
            {
                "id": "exp_msg_1",
                "category": "messaging",
                "title": "Pain-Point vs Outcome Headline",
                "hypothesis": "Focusing on hours saved will increase landing page conversion from 4% to 7%",
                "variant": f"Stop wasting 15+ hours a week on manual setups. {body.productName} automates your entire workflow in one click.",
                "status": "ready"
            },
            {
                "id": "exp_price_1",
                "category": "pricing",
                "title": "Lifetime Founding Pass vs Monthly",
                "hypothesis": "Offering a $99 lifetime founding pass accelerates initial presale velocity towards the $5K threshold",
                "variant": "$99 Lifetime Founding Access (Limited to first 50 builders)",
                "status": "ready"
            }
        ],
        feedback_clusters=[
            {"topic": "Setup Simplicity", "count": 28, "sentiment": "positive", "quote": "If this actually takes less than 5 minutes to connect, take my money."},
            {"topic": "Pricing Sensitivity", "count": 14, "sentiment": "neutral", "quote": "Is there an annual discount option?"}
        ]
    )
    db.add(telemetry)
    db.commit()
    db.refresh(proj)

    # ── Automated Dual Email Dispatch to Creator and Admin ────────────────────
    try:
        from app.integrations.email_provider import email_provider
        from app.config import settings

        creator_email = (body.creatorEmail or "").strip()
        admin_email = (settings.ADMIN_EMAIL or "elishadamu97@gmail.com").strip()
        base_frontend = (settings.FRONTEND_URL or "https://creator-forge-frontend.vercel.app").rstrip("/")
        portal_slug = (proj.creator_handle or proj.creator_name or "creator").replace("@", "").replace(" ", "").strip().lower()
        admin_project_link = f"{base_frontend}/launch?section=section2&project={proj.id}"
        portal_magic_link = f"{base_frontend}/portal/{portal_slug}?token={proj.portal_token}&project={proj.id}"

        email_subject = f"[PROJECT INITIALIZED] {proj.product_name} with {proj.creator_name or proj.creator_handle} (Section 2 Live)"
        admin_email_body = f"""Hello Admin,

A new Co-Launch Software Venture has been initialized into Section 2:

- Product Name: {proj.product_name}
- Tagline: {proj.product_tagline}
- Creator Partner: {proj.creator_name or proj.creator_handle} ({proj.niche or 'General'})
- Creator Email: {creator_email or 'Pending'}
- Target Presale Milestone: ${int(proj.presale_target):,}

- Admin Project OS Dashboard: {admin_project_link}
- Creator Portal Magic Link: {portal_magic_link}

Phase 1 (Validate) is now active and ready for execution.

Best regards,
Creator Forge Studio Operations"""

        admin_email_html = f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 24px; background: #0c0e14; color: #f1f5f9; border-radius: 16px; border: 1px solid rgba(255,255,255,0.08);">
            <h2 style="color: #a855f7; margin-top: 0;">Co-Launch Venture Initialized (Section 2 Live)</h2>
            <p style="color: #94a3b8; font-size: 14px;">A new Co-Launch Software Venture has moved into Section 2:</p>
            <ul style="line-height: 1.8; font-size: 14px; color: #cbd5e1;">
                <li><strong>Product:</strong> {proj.product_name}</li>
                <li><strong>Tagline:</strong> {proj.product_tagline}</li>
                <li><strong>Partner:</strong> {proj.creator_name or proj.creator_handle} ({proj.niche or 'General'})</li>
                <li><strong>Creator Email:</strong> {creator_email or 'Pending'}</li>
                <li><strong>Presale Milestone:</strong> ${int(proj.presale_target):,}</li>
            </ul>
            <div style="margin: 24px 0; padding: 16px; background: rgba(168,85,247,0.1); border: 1px solid rgba(168,85,247,0.3); border-radius: 12px;">
                <p style="margin: 0 0 8px 0; font-size: 13px; font-weight: bold; color: #c084fc;">[ADMIN DASHBOARD - PROJECT OS]:</p>
                <a href="{admin_project_link}" style="display: inline-block; padding: 10px 20px; background: #a855f7; color: #ffffff; text-decoration: none; font-weight: bold; font-size: 13px; border-radius: 8px;">Open Co-Launch Project OS -&gt;</a>
                <p style="margin: 8px 0 0 0; font-size: 11px; color: #94a3b8; word-break: break-all;">{admin_project_link}</p>
            </div>
            <div style="margin: 16px 0; padding: 14px; background: rgba(16,185,129,0.08); border: 1px solid rgba(16,185,129,0.25); border-radius: 12px;">
                <p style="margin: 0 0 6px 0; font-size: 12px; font-weight: bold; color: #34d399;">[CREATOR PORTAL MAGIC LINK]:</p>
                <a href="{portal_magic_link}" style="color: #6ee7b7; font-size: 12px; word-break: break-all;">{portal_magic_link}</a>
            </div>
            <p style="color: #64748b; font-size: 12px; margin-top: 24px;">Phase 1 (Validate) is active and ready for execution.</p>
        </div>
        """

        # 1. Dispatch Briefing to Admin (elishadamu97@gmail.com)
        if admin_email and "@" in admin_email:
            try:
                email_provider.send(
                    to_email=admin_email,
                    subject=f"[ADMIN BRIEFING] {email_subject}",
                    body_html=admin_email_html,
                    body_text=admin_email_body
                )
                logger.info(f"Dispatched Section 2 Admin Briefing to {admin_email}")
            except Exception as e:
                logger.warning(f"Failed to dispatch admin launch briefing: {e}")

        # 2. Dispatch Magic Portal Link to Creator
        if creator_email and "@" in creator_email:
            try:
                creator_email_body = f"""Hi {proj.creator_name or 'there'},

Welcome to your software co-launch portal!

We have officially initialized {proj.product_name} into Phase 1 (Validation). You can access your dedicated Creator Portal and track live progress here:

Access Portal: {portal_magic_link}

Best,
Creator Forge Studio Team"""
                email_provider.send(
                    to_email=creator_email,
                    subject=f"Access Your Co-Founder Portal: {proj.product_name}",
                    body_html=creator_email_body.replace("\n", "<br>"),
                    body_text=creator_email_body
                )
                proj.portal_link_sent = True
                proj.portal_link_sent_to = creator_email
                proj.portal_link_sent_at = datetime.utcnow()
                db.commit()
                logger.info(f"Dispatched Portal Magic Link to Creator {creator_email}")
            except Exception as e:
                logger.warning(f"Failed to dispatch creator portal link: {e}")
    except Exception as dispatch_err:
        logger.warning(f"Project dispatch notification exception: {dispatch_err}")

    return _format_project_response(proj)


@router.post("", status_code=201)
def create_project(body: CreateProjectRequest, db: Session = Depends(get_db)):
    """Initialize a new Co-Launch Project from Section 1 concept."""
    return execute_create_co_launch_project(db, body)


@router.get("/{project_id}")
def get_project(project_id: str, db: Session = Depends(get_db)):
    """Fetch complete co-launch project with all 5 validation steps."""
    proj = db.get(CoLaunchProject, project_id)
    if not proj:
        # Also resolve by creator_id, creator_handle, or clean slug (e.g. 'codanics')
        clean_target = project_id.replace("@", "").lower().strip()
        proj = db.query(CoLaunchProject).filter(
            (CoLaunchProject.creator_id == project_id) |
            (CoLaunchProject.creator_handle.ilike(f"%{clean_target}%")) |
            (CoLaunchProject.creator_name.ilike(f"%{clean_target}%")) |
            (CoLaunchProject.creator_email.ilike(f"%{clean_target}%"))
        ).first()
    if not proj:
        raise HTTPException(404, f"Project '{project_id}' not found")
@router.patch("/{project_id}")
@router.put("/{project_id}")
def update_project_general(project_id: str, body: Dict[str, Any], db: Session = Depends(get_db)):
    """Update co-launch project phase, step, status, or metadata attributes."""
    proj = db.get(CoLaunchProject, project_id)
    if not proj:
        clean_target = project_id.replace("@", "").lower().strip()
        proj = db.query(CoLaunchProject).filter(
            (CoLaunchProject.creator_id == project_id) |
            (CoLaunchProject.creator_handle.ilike(f"%{clean_target}%")) |
            (CoLaunchProject.creator_name.ilike(f"%{clean_target}%")) |
            (CoLaunchProject.creator_email.ilike(f"%{clean_target}%"))
        ).first()

    if not proj:
        raise HTTPException(404, f"Project '{project_id}' not found")

    phase = body.get("currentPhase") if body.get("currentPhase") is not None else body.get("current_phase")
    if phase is not None:
        proj.current_phase = int(phase)
        if int(phase) == 2 and proj.status == "validating":
            proj.status = "building"
        elif int(phase) == 3:
            proj.status = "launched"

    step = body.get("currentStep") or body.get("current_step")
    if step is not None:
        proj.current_step = str(step)

    status = body.get("status")
    if status is not None:
        proj.status = str(status)

    if "productName" in body or "product_name" in body:
        proj.product_name = str(body.get("productName") or body.get("product_name"))

    if "productTagline" in body or "product_tagline" in body:
        proj.product_tagline = str(body.get("productTagline") or body.get("product_tagline"))

    if "pricing" in body:
        proj.pricing = str(body.get("pricing"))

    target = body.get("presaleTarget") if body.get("presaleTarget") is not None else body.get("presale_target")
    if target is not None:
        proj.presale_target = float(target)

    meta = body.get("metadataInfo") or body.get("metadata_info")
    if meta is not None:
        cur_meta = dict(proj.metadata_info or {})
        cur_meta.update(meta)
        proj.metadata_info = cur_meta

    if "projectFiles" in body:
        cur_meta = dict(proj.metadata_info or {})
        cur_meta["project_files"] = body["projectFiles"]
        proj.metadata_info = cur_meta

    if "messages" in body:
        cur_meta = dict(proj.metadata_info or {})
        cur_meta["messages"] = body["messages"]
        proj.metadata_info = cur_meta

    proj.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(proj)
    return _format_project_response(proj)


@router.put("/{project_id}/plan")
def update_validation_plan(project_id: str, body: UpdatePlanRequest, db: Session = Depends(get_db)):
    """Save or update Step 1 Validation Plan."""
    proj = db.get(CoLaunchProject, project_id)
    if not proj:
        raise HTTPException(404, f"Project '{project_id}' not found")

    plan = proj.validation_plan
    if not plan:
        plan = ValidationPlan(project_id=proj.id)
        db.add(plan)

    if body.customer is not None: plan.customer = body.customer
    if body.problem is not None: plan.problem = body.problem
    if body.offer is not None: plan.offer = body.offer
    if body.pricing is not None: plan.pricing = body.pricing
    if body.test_method is not None: plan.test_method = body.test_method
    if body.period is not None: plan.period = body.period
    if body.threshold is not None: plan.threshold = body.threshold
    if body.target_revenue is not None:
        plan.target_revenue = body.target_revenue
        proj.presale_target = body.target_revenue
    if body.status is not None: plan.status = body.status

    db.commit()
    db.refresh(proj)
    return _format_project_response(proj)


@router.put("/{project_id}/campaign")
def update_validation_campaign(project_id: str, body: UpdateCampaignRequest, db: Session = Depends(get_db)):
    """Save or update Step 2 Campaign Assets, Infrastructure, and Approve & Launch status."""
    proj = db.get(CoLaunchProject, project_id)
    if not proj:
        raise HTTPException(404, f"Project '{project_id}' not found")

    campaign = proj.validation_campaign
    if not campaign:
        campaign = ValidationCampaign(project_id=proj.id)
        db.add(campaign)

    if body.product_assets is not None: campaign.product_assets = body.product_assets
    if body.infrastructure is not None: campaign.infrastructure = body.infrastructure
    if body.research_survey is not None: campaign.research_survey = body.research_survey
    if body.review_status is not None:
        campaign.review_status = body.review_status
        if body.review_status in ("approved", "launched"):
            campaign.approved_at = datetime.utcnow()
            campaign.approved_by = "Lead Founder"

    db.commit()
    db.refresh(proj)
    return _format_project_response(proj)


@router.get("/{project_id}/creator-tasks")
def get_creator_tasks(project_id: str, db: Session = Depends(get_db)):
    """Fetch Step 3 Creator Campaign Tasks."""
    tasks = db.query(CreatorCampaignTask).filter(CreatorCampaignTask.project_id == project_id).order_by(CreatorCampaignTask.day_number).all()
    return [
        {
            "id": t.id,
            "dayNumber": t.day_number,
            "channel": t.channel,
            "title": t.task_title,
            "content": t.content_draft,
            "cta": t.cta_text,
            "trackingLink": t.tracking_link,
            "mediaPrompt": t.media_prompt,
            "status": t.status,
            "completedAt": t.completed_at.isoformat() if t.completed_at else None,
        }
        for t in tasks
    ]


@router.patch("/{project_id}/creator-tasks/{task_id}")
def update_creator_task(project_id: str, task_id: str, body: UpdateTaskRequest, db: Session = Depends(get_db)):
    """Update a Step 3 creator campaign checklist task."""
    task = db.query(CreatorCampaignTask).filter(
        CreatorCampaignTask.project_id == project_id,
        CreatorCampaignTask.id == task_id
    ).first()
    if not task:
        raise HTTPException(404, f"Task '{task_id}' not found")

    if body.status is not None:
        task.status = body.status
        if body.status == "completed":
            task.completed_at = datetime.utcnow()
    if body.content_draft is not None: task.content_draft = body.content_draft
    if body.cta_text is not None: task.cta_text = body.cta_text
    if body.tracking_link is not None: task.tracking_link = body.tracking_link

    db.commit()
    return {"status": "success", "taskId": task.id, "newStatus": task.status}


@router.post("/{project_id}/reservations")
def add_reservation(project_id: str, body: AddReservationRequest, db: Session = Depends(get_db)):
    """Record a verified buyer pre-order / reservation in Step 4 Telemetry."""
    proj = db.get(CoLaunchProject, project_id)
    if not proj:
        raise HTTPException(404, f"Project '{project_id}' not found")

    telemetry = proj.telemetry
    if not telemetry:
        telemetry = ValidationTelemetry(project_id=proj.id)
        db.add(telemetry)

    reservation_item = {
        "id": f"res_{int(datetime.utcnow().timestamp()*1000)}",
        "name": body.name,
        "email": body.email,
        "amount": float(body.amount),
        "tier": body.tier,
        "channel": body.channel,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
        "status": "paid"
    }

    cur_res = list(telemetry.reservations or [])
    cur_res.insert(0, reservation_item)
    telemetry.reservations = cur_res

    # Increment telemetry metrics
    telemetry.presales_count = len(cur_res)
    new_revenue = sum(r.get("amount", 0) for r in cur_res)
    telemetry.presales_revenue = new_revenue
    proj.current_presales = new_revenue

    # Update visitors and conversion rate
    cur_visitors = max(telemetry.visitors, len(cur_res) * 6)
    telemetry.visitors = cur_visitors
    proj.visitors = cur_visitors
    conv = round((len(cur_res) / cur_visitors) * 100, 1) if cur_visitors > 0 else 0.0
    telemetry.conversion_rate = conv
    proj.conversion_rate = conv

    # Attribution
    cur_attr = dict(telemetry.channel_attribution or {})
    chan = body.channel or "direct"
    cur_attr[chan] = cur_attr.get(chan, 0) + 1
    telemetry.channel_attribution = cur_attr

    db.commit()
    db.refresh(proj)
    return _format_project_response(proj)


@router.post("/{project_id}/gate-decision")
def record_gate_decision(project_id: str, body: GateDecisionRequest, db: Session = Depends(get_db)):
    """Record Step 5 Executive Validation Gate decision."""
    proj = db.get(CoLaunchProject, project_id)
    if not proj:
        raise HTTPException(404, f"Project '{project_id}' not found")

    target = proj.presale_target or 5000.0
    achieved = proj.current_presales or 0.0
    is_passed = achieved >= target

    if body.decision == "pass_to_phase2":
        proj.current_phase = 2
        proj.current_step = "specs"
        proj.status = "building"
        gate_status = "passed"
    elif body.decision == "iterate_validation":
        proj.current_phase = 1
        proj.current_step = "optimize"
        proj.status = "validating"
        gate_status = "iterating"
    else: # 'kill_project'
        proj.status = "killed"
        gate_status = "failed"

    decision = ValidationGateDecision(
        project_id=proj.id,
        decision=body.decision,
        target_revenue=target,
        achieved_revenue=achieved,
        backers_count=proj.telemetry.presales_count if proj.telemetry else 0,
        conversion_rate=proj.conversion_rate or 0.0,
        gate_status=gate_status,
        gate_notes=body.notes or f"Executive gate decision: {body.decision}"
    )
    db.add(decision)
    db.commit()
    db.refresh(proj)

    return _format_project_response(proj)


@router.post("/record-visit")
def record_visit_universal(body: TrackVisitRequest, db: Session = Depends(get_db)):
    """
    Universal public page/preorder visit recorder.
    Increments unique visitors, channel attribution count in DB, and updates live telemetry.
    """
    proj = None
    if body.projectId:
        proj = db.get(CoLaunchProject, body.projectId)
    
    if not proj and body.slug:
        clean_slug = body.slug.lower().strip()
        projects = db.query(CoLaunchProject).all()
        for p in projects:
            p_slug = (p.product_name or "").lower().replace(" ", "-").replace("'", "")
            c_slug = (p.creator_handle or "").lower().replace("@", "")
            if clean_slug in p_slug or p_slug in clean_slug or clean_slug == c_slug or clean_slug == p.id:
                proj = p
                break
    
    if not proj:
        proj = db.query(CoLaunchProject).order_by(CoLaunchProject.created_at.desc()).first()

    if not proj:
        return {"status": "ok", "message": "No active project"}

    telemetry = proj.telemetry
    if not telemetry:
        telemetry = ValidationTelemetry(project_id=proj.id)
        db.add(telemetry)

    # Increment visitors & page views
    telemetry.visitors = int(telemetry.visitors or 0) + 1
    telemetry.views = int(telemetry.views or 0) + 1
    proj.visitors = telemetry.visitors

    # Map normalized channel
    chan = body.channel or "Direct / Other"
    cur_attr = dict(telemetry.channel_attribution or {})
    cur_attr[chan] = cur_attr.get(chan, 0) + 1
    telemetry.channel_attribution = cur_attr

    # Recalculate conversion rate
    res_count = len(telemetry.reservations or [])
    if telemetry.visitors > 0:
        telemetry.conversion_rate = round((res_count / telemetry.visitors) * 100, 1)
        proj.conversion_rate = telemetry.conversion_rate

    db.commit()
    db.refresh(proj)
    return _format_project_response(proj)


@router.post("/{project_id}/track-visit")
def track_project_visit(project_id: str, body: TrackVisitRequest, db: Session = Depends(get_db)):
    """Track a visit for a specific project ID."""
    body.projectId = project_id
    return record_visit_universal(body, db)


@router.post("/record-preorder")
def record_preorder_universal(body: RecordPreorderRequest, db: Session = Depends(get_db)):
    """
    Universal public pre-order recorder called by /preorder/:slug checkout.
    Persists reservation, updates presales revenue, unique visitors, and logs activity in DB.
    """
    proj = None
    if body.projectId:
        proj = db.get(CoLaunchProject, body.projectId)
    
    if not proj and body.slug:
        clean_slug = body.slug.lower().strip()
        projects = db.query(CoLaunchProject).all()
        for p in projects:
            p_slug = (p.product_name or "").lower().replace(" ", "-").replace("'", "")
            c_slug = (p.creator_handle or "").lower().replace("@", "")
            if clean_slug in p_slug or p_slug in clean_slug or clean_slug == c_slug or clean_slug == p.id:
                proj = p
                break
    
    if not proj:
        # Fallback to the latest active project
        proj = db.query(CoLaunchProject).order_by(CoLaunchProject.created_at.desc()).first()

    if not proj:
        raise HTTPException(404, "No active co-launch project found to record reservation")

    telemetry = proj.telemetry
    if not telemetry:
        telemetry = ValidationTelemetry(project_id=proj.id)
        db.add(telemetry)

    res_id = f"res_{int(datetime.utcnow().timestamp()*1000)}"
    timestamp_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    reservation_item = {
        "id": res_id,
        "name": body.name,
        "email": body.email,
        "amount": float(body.amount),
        "tier": body.tier or "Founding Pass",
        "paymentMethod": body.paymentMethod or "Stripe",
        "channel": body.channel or "Direct / Other",
        "txId": body.txId or f"tx_{res_id}",
        "timestamp": timestamp_str,
        "status": "Paid"
    }

    cur_res = list(telemetry.reservations or [])
    cur_res.insert(0, reservation_item)
    telemetry.reservations = cur_res

    # Increment telemetry metrics
    telemetry.presales_count = len(cur_res)
    new_revenue = sum(float(r.get("amount", 0)) for r in cur_res)
    telemetry.presales_revenue = new_revenue
    proj.current_presales = new_revenue

    # Update visitors and conversion rate
    cur_visitors = max(int(telemetry.visitors or 0), len(cur_res) * 5, 1)
    telemetry.visitors = cur_visitors
    proj.visitors = cur_visitors
    conv = round((len(cur_res) / cur_visitors) * 100, 1) if cur_visitors > 0 else 0.0
    telemetry.conversion_rate = conv
    proj.conversion_rate = conv

    # Attribution
    cur_attr = dict(telemetry.channel_attribution or {})
    chan = body.channel or "Direct / Other"
    cur_attr[chan] = cur_attr.get(chan, 0) + 1
    telemetry.channel_attribution = cur_attr

    # Activity Log
    meta = dict(proj.metadata_info or {})
    act_logs = list(meta.get("activity_logs") or [])
    act_item = {
        "id": f"act_{int(datetime.utcnow().timestamp()*1000)}",
        "action": "Customer Pre-Order Received",
        "details": f"${body.amount:.0f} {body.tier} reserved by {body.name} ({body.email}) via {body.paymentMethod or 'Stripe'}",
        "category": "revenue",
        "timestamp": timestamp_str
    }
    act_logs.insert(0, act_item)
    meta["activity_logs"] = act_logs[:50]
    proj.metadata_info = meta

    db.commit()
    db.refresh(proj)
    return _format_project_response(proj)


@router.post("/{project_id}/log-activity")
def log_admin_activity(project_id: str, body: LogActivityRequest, db: Session = Depends(get_db)):
    """Record an audit trail action conducted by the admin or AI agent."""
    proj = db.get(CoLaunchProject, project_id)
    if not proj:
        raise HTTPException(404, f"Project '{project_id}' not found")

    meta = dict(proj.metadata_info or {})
    act_logs = list(meta.get("activity_logs") or [])
    timestamp_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    act_item = {
        "id": f"act_{int(datetime.utcnow().timestamp()*1000)}",
        "action": body.action,
        "details": body.details or body.action,
        "category": body.category or "admin_action",
        "step": body.step or "plan",
        "phase": body.phase or 1,
        "timestamp": timestamp_str
    }
    act_logs.insert(0, act_item)
    meta["activity_logs"] = act_logs[:50]
    proj.metadata_info = meta

    db.commit()
    db.refresh(proj)
    return {"status": "success", "activity": act_item, "activityLogs": meta["activity_logs"]}


@router.get("/by-slug/{slug}")
def get_project_by_slug(slug: str, db: Session = Depends(get_db)):
    """Lookup active co-launch project by slug or creator handle."""
    clean_slug = slug.lower().strip()
    projects = db.query(CoLaunchProject).order_by(CoLaunchProject.created_at.desc()).all()
    for p in projects:
        p_slug = (p.product_name or "").lower().replace(" ", "-").replace("'", "")
        c_slug = (p.creator_handle or "").lower().replace("@", "")
        if clean_slug in p_slug or p_slug in clean_slug or clean_slug == c_slug or clean_slug == p.id:
            return _format_project_response(p)
    
    if projects:
        return _format_project_response(projects[0])
    raise HTTPException(404, f"No project found matching slug '{slug}'")


@router.delete("/{project_id}")
def delete_project(project_id: str, db: Session = Depends(get_db)):
    """Delete a co-launch project, all validation records, and all uploaded Cloudinary files."""
    proj = db.get(CoLaunchProject, project_id)
    if not proj:
        raise HTTPException(404, f"Project '{project_id}' not found")
    
    try:
        from app.integrations.cloudinary_service import delete_all_files_for_project
        delete_all_files_for_project(proj)
    except Exception as e:
        logger.warning(f"[DeleteProject] Cloudinary purge error: {e}")

    db.delete(proj)
    db.commit()
    return {"status": "success", "message": f"Project '{project_id}' and all associated Cloudinary files deleted."}

