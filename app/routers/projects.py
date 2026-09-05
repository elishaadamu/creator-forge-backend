# -*- coding: utf-8 -*-
import logging
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

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
    niche: Optional[Any] = None
    followers: Optional[Any] = None
    productName: Optional[str] = "New Co-Launch Venture"
    productTagline: Optional[str] = None
    targetAudience: Optional[str] = None
    customer: Optional[str] = None
    problem: Optional[str] = None
    keyFeatures: Optional[List[str]] = None
    pricing: Optional[str] = None
    revenueModel: Optional[str] = None
    presaleTarget: Optional[float] = 12500.0
    selectedConcept: Optional[Dict[str, Any]] = None
    mockup: Optional[Dict[str, Any]] = None
    campaign_kit: Optional[Dict[str, Any]] = None
    campaignKit: Optional[Dict[str, Any]] = None


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
    productAssets: Optional[Dict[str, Any]] = None
    infrastructure: Optional[Dict[str, Any]] = None
    research_survey: Optional[Dict[str, Any]] = None
    researchSurvey: Optional[Dict[str, Any]] = None
    review_status: Optional[str] = None # 'draft', 'approved', 'launched'
    reviewStatus: Optional[str] = None
    campaign_kit: Optional[Dict[str, Any]] = None
    campaignKit: Optional[Dict[str, Any]] = None
    creator_tasks: Optional[List[Dict[str, Any]]] = None
    creatorTasks: Optional[List[Dict[str, Any]]] = None
    campaign_launched: Optional[bool] = None
    campaignLaunched: Optional[bool] = None



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
    clientId: Optional[str] = None
    fingerprint: Optional[str] = None
    channel: Optional[str] = "Direct / Other"
    ref: Optional[str] = None
    path: Optional[str] = None
    isNewVisitor: Optional[bool] = None


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
        "mvpBuildPlan": (proj.metadata_info or {}).get("mvp_build_plan") or (proj.metadata_info or {}).get("mvpBuildPlan"),
        "engineeringTasks": (proj.metadata_info or {}).get("engineering_tasks") or (proj.metadata_info or {}).get("engineeringTasks", []),
        "qaResults": (proj.metadata_info or {}).get("qa_results") or (proj.metadata_info or {}).get("qaResults"),
        "betaFeedback": (proj.metadata_info or {}).get("beta_feedback") or (proj.metadata_info or {}).get("betaFeedback", []),
        "feedbackClusters": (proj.metadata_info or {}).get("feedback_clusters") or (proj.metadata_info or {}).get("feedbackClusters") or (telemetry.feedback_clusters if telemetry else []) or [],
        "readinessReport": (proj.metadata_info or {}).get("readiness_report") or (proj.metadata_info or {}).get("readinessReport"),
        "appliedPatches": (proj.metadata_info or {}).get("applied_patches") or (proj.metadata_info or {}).get("appliedPatches", []),
        "mvpVersion": (proj.metadata_info or {}).get("mvp_version") or (proj.metadata_info or {}).get("mvpVersion", "v1.0.0-MVP"),
        "launchStrategy": (proj.metadata_info or {}).get("launch_strategy") or (proj.metadata_info or {}).get("launchStrategy"),
        "creatorAssets": (proj.metadata_info or {}).get("creator_assets") or (proj.metadata_info or {}).get("creatorAssets"),
        "launchTelemetry": (proj.metadata_info or {}).get("launch_telemetry") or (proj.metadata_info or {}).get("launchTelemetry"),
        "channelStats": (proj.metadata_info or {}).get("channel_stats") or (proj.metadata_info or {}).get("channelStats", []),
        "launchManagerData": (proj.metadata_info or {}).get("launch_manager_data") or (proj.metadata_info or {}).get("launchManagerData"),
        "dispatchedActions": (proj.metadata_info or {}).get("dispatched_actions") or (proj.metadata_info or {}).get("dispatchedActions", []),
        "launchReport": (proj.metadata_info or {}).get("launch_report") or (proj.metadata_info or {}).get("launchReport"),
        "launchStatus": (proj.metadata_info or {}).get("launch_status") or (proj.metadata_info or {}).get("launchStatus", "PREP"),
        "productInfrastructure": (proj.metadata_info or {}).get("product_infrastructure") or (proj.metadata_info or {}).get("productInfrastructure"),
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
            "campaignKit": (
                (campaign.campaign_kit if campaign and getattr(campaign, "campaign_kit", None) else None) or
                (proj.metadata_info or {}).get("campaign_kit") or
                (proj.metadata_info or {}).get("campaignKit") or
                (campaign.product_assets.get("campaign_kit") if campaign and isinstance(campaign.product_assets, dict) else None)
            ),
            "reviewStatus": campaign.review_status,
            "approvedAt": campaign.approved_at.isoformat() if campaign.approved_at else None,
        } if campaign else None,
        "campaignKit": (
            (campaign.campaign_kit if campaign and getattr(campaign, "campaign_kit", None) else None) or
            (proj.metadata_info or {}).get("campaign_kit") or
            (proj.metadata_info or {}).get("campaignKit") or
            (campaign.product_assets.get("campaign_kit") if campaign and isinstance(campaign.product_assets, dict) else None) or
            (campaign.product_assets.get("campaignKit") if campaign and isinstance(campaign.product_assets, dict) else None) or
            (campaign.product_assets if campaign and isinstance(campaign.product_assets, dict) and campaign.product_assets.get("postingSchedule") else None)
        ),
        "campaignLaunched": bool(
            (campaign and campaign.campaign_kit and isinstance(campaign.campaign_kit, dict) and bool(
                campaign.campaign_kit.get("postingSchedule") or
                campaign.campaign_kit.get("announcementPost") or
                campaign.campaign_kit.get("storySequence") or
                campaign.campaign_kit.get("videoScript") or
                campaign.campaign_kit.get("newsletterDraft")
            )) or
            (proj.metadata_info and isinstance(proj.metadata_info, dict) and bool(
                (proj.metadata_info.get("campaign_kit") or {}).get("postingSchedule") or
                (proj.metadata_info.get("campaign_kit") or {}).get("announcementPost")
            ))
        ),
        "campaignAssetsGenerated": bool(
            (campaign and campaign.campaign_kit and isinstance(campaign.campaign_kit, dict) and bool(
                campaign.campaign_kit.get("postingSchedule") or
                campaign.campaign_kit.get("announcementPost") or
                campaign.campaign_kit.get("storySequence") or
                campaign.campaign_kit.get("videoScript") or
                campaign.campaign_kit.get("newsletterDraft")
            )) or
            (proj.metadata_info and isinstance(proj.metadata_info, dict) and bool(
                (proj.metadata_info.get("campaign_kit") or {}).get("postingSchedule") or
                (proj.metadata_info.get("campaign_kit") or {}).get("announcementPost")
            ))
        ),
        "surveyData": campaign.research_survey if campaign else None,
        "surveyResponses": (
            (campaign.research_survey.get("responses") if campaign and isinstance(campaign.research_survey, dict) else None) or
            (proj.metadata_info or {}).get("survey_responses") or
            (proj.metadata_info or {}).get("surveyResponses") or
            []
        ),
        "surveyAnalysis": (
            (campaign.research_survey.get("analysis") if campaign and isinstance(campaign.research_survey, dict) else None) or
            (proj.metadata_info or {}).get("survey_analysis") or
            (proj.metadata_info or {}).get("surveyAnalysis") or
            None
        ),
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
            "feedbackClusters": (proj.metadata_info or {}).get("feedback_clusters") or (telemetry.feedback_clusters if telemetry else []) or [],
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


class RecordSurveyResponseRequest(BaseModel):
    projectId: Optional[str] = None
    slug: Optional[str] = None
    creatorHandle: Optional[str] = None
    name: Optional[str] = None
    respondentName: Optional[str] = None
    email: Optional[str] = None
    respondentEmail: Optional[str] = None
    rating: Optional[int] = None
    intentScore: Optional[int] = None
    answers: Optional[Dict[str, Any]] = None
    submittedAt: Optional[str] = None



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
    clean_handle = (body.creatorHandle or "").lstrip("@").strip().lower()
    if not existing_creator_proj and clean_handle:
        existing_creator_proj = db.query(CoLaunchProject).filter(
            CoLaunchProject.creator_handle.ilike(f"%{clean_handle}%")
        ).first()
    if not existing_creator_proj and body.creatorName:
        clean_name = body.creatorName.strip().lower()
        if clean_name and len(clean_name) >= 3:
            existing_creator_proj = db.query(CoLaunchProject).filter(
                CoLaunchProject.creator_name.ilike(f"%{clean_name}%")
            ).first()

    if existing_creator_proj:
        updated = False
        concept_data = body.selectedConcept or {}
        new_name = body.productName or concept_data.get("name")
        new_tagline = body.productTagline or concept_data.get("tagline")
        new_pricing = body.pricing or concept_data.get("pricing")

        if new_name and new_name != existing_creator_proj.product_name:
            existing_creator_proj.product_name = new_name
            updated = True
        if new_tagline and new_tagline != existing_creator_proj.product_tagline:
            existing_creator_proj.product_tagline = new_tagline
            updated = True
        if new_pricing and new_pricing != existing_creator_proj.pricing:
            existing_creator_proj.pricing = new_pricing
            updated = True
        if concept_data and concept_data != existing_creator_proj.selected_concept:
            existing_creator_proj.selected_concept = concept_data
            updated = True

        if updated:
            db.commit()
            db.refresh(existing_creator_proj)

        logger.info(f"[execute_create_co_launch_project] Project {existing_creator_proj.id} matched for creator. Returning project.")
        return _format_project_response(existing_creator_proj)

    proj_id = body.id or f"proj_{int(datetime.utcnow().timestamp()*1000)}"

    # Clean existing if exact ID exists
    existing = db.get(CoLaunchProject, proj_id)
    if existing:
        db.delete(existing)
        db.commit()

    concept_data = body.selectedConcept or {}
    product_name = body.productName or concept_data.get("name") or "New Co-Launch Venture"
    product_tagline = body.productTagline or concept_data.get("tagline") or ""
    pricing_str = body.pricing or concept_data.get("pricing") or "$29/mo Starter • $79/mo Pro"
    presale_target_val = float(body.presaleTarget or concept_data.get("presaleTarget") or 12500.0)

    niche_str = ", ".join(str(x) for x in body.niche) if isinstance(body.niche, list) else (str(body.niche) if body.niche else None)
    followers_str = str(body.followers) if body.followers is not None else None

    valid_creator_id = None
    if body.creatorId:
        c_row = db.get(Creator, body.creatorId)
        if c_row:
            valid_creator_id = c_row.id
        else:
            c_by_handle = db.query(Creator).filter(
                (Creator.handle.ilike(body.creatorId.lstrip("@"))) |
                (Creator.handle.ilike(f"@{body.creatorId.lstrip('@')}"))
            ).first()
            if c_by_handle:
                valid_creator_id = c_by_handle.id

    proj = CoLaunchProject(
        id=proj_id,
        creator_id=valid_creator_id,
        creator_handle=body.creatorHandle,
        creator_name=body.creatorName or body.creatorHandle,
        creator_avatar=body.creatorAvatar,
        creator_email=body.creatorEmail,
        niche=niche_str,
        followers=followers_str,
        product_name=product_name,
        product_tagline=product_tagline,
        target_audience=body.customer or body.targetAudience or concept_data.get("customer") or "",
        pricing=pricing_str,
        revenue_model=body.revenueModel or concept_data.get("revenueModel") or "SaaS Subscription",
        current_phase=1,
        current_step="plan",
        status="validating",
        presale_target=presale_target_val,
        current_presales=0.0,
        visitors=0,
        conversion_rate=0.0,
        portal_token="cf_sec_live",
        selected_concept=concept_data,
        created_at=datetime.utcnow()
    )
    db.add(proj)
    db.commit()
    db.refresh(proj)

    # Dynamic pricing extraction from concept / payload
    import re
    raw_pricing = pricing_str or "$29/mo Starter • $79/mo Pro"
    price_matches = [int(p) for p in re.findall(r'\$(\d+)', raw_pricing)]
    if len(price_matches) >= 2:
        starter_price = price_matches[0]
        pro_price = price_matches[1]
        founding_price = price_matches[2] if len(price_matches) > 2 else max(starter_price * 3, 89)
    elif len(price_matches) == 1:
        founding_price = price_matches[0]
        starter_price = max(9, int(round(founding_price * 0.3)))
        pro_price = max(starter_price * 2, int(round(founding_price * 0.7)))
    else:
        starter_price = 29
        pro_price = 79
        founding_price = 99
    
    deposit_price = max(9, int(round(founding_price * 0.2)))

    # 1. Step 1: Create Validation Plan
    customer_desc = body.customer or body.targetAudience or f"{body.niche or 'Creator'} audience and builders"
    problem_desc = body.problem or f"Manual workflows and lack of specialized tooling in {body.niche or 'this space'}"
    offer_desc = f"{body.productName} Founding Co-Launch Access: {body.productTagline or ''}"
    plan = ValidationPlan(
        project_id=proj.id,
        customer=customer_desc,
        problem=problem_desc,
        offer=offer_desc,
        pricing=raw_pricing,
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
            "pricingConfig": {
                "foundingPrice": founding_price,
                "depositPrice": deposit_price,
                "perks": f"50% Lifetime Price Lock & VIP Alpha Perks for {proj.creator_name or 'Founding'} Backers"
            },
            "pricingTiers": [
                {"name": "Founding Member", "price": founding_price, "period": "lifetime", "perks": "Lifetime core access, private Discord, roadmap voting"},
                {"name": "Starter Plan", "price": starter_price, "period": "month", "perks": "Full template library, monthly updates, standard support"},
                {"name": "Pro Builder", "price": pro_price, "period": "month", "perks": "Unlimited syncs, 1-on-1 onboarding, priority feature access"},
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
                {"id": "q2", "question": f"Would you pay ${starter_price}–${pro_price}/month for a tool that automates this completely?", "type": "multiple_choice", "options": ["Definitely yes", "Maybe", "No"]},
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
        (5, "newsletter", "Newsletter Broadcast: Founding Cohort Announcement", f"Subject: Building something new with you.\n\nOver the past 6 months, the #1 request I received was a dedicated solution for {body.niche or 'creators'}. Today we're opening presales for {body.productName}.", f"Reserve Founding Access (${founding_price})", f"https://launch.app/p/{slug}?utm=newsletter"),
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
                "hypothesis": f"Offering a ${founding_price} lifetime founding pass accelerates initial presale velocity towards the ${int(body.presaleTarget or 5000):,} threshold",
                "variant": f"${founding_price} Lifetime Founding Access (Limited to first 50 builders)",
                "status": "ready"
            }
        ],
        feedback_clusters=[]
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

    return _format_project_response(proj)


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
    cur_meta = dict(proj.metadata_info or {})
    if meta is not None:
        cur_meta.update(meta)

    if "projectFiles" in body or "project_files" in body:
        cur_meta["project_files"] = body.get("projectFiles") or body.get("project_files")

    if "messages" in body:
        cur_meta["messages"] = body["messages"]

    if "mvpBuildPlan" in body or "mvp_build_plan" in body:
        cur_meta["mvp_build_plan"] = body.get("mvpBuildPlan") or body.get("mvp_build_plan")

    if "engineeringTasks" in body or "engineering_tasks" in body:
        cur_meta["engineering_tasks"] = body.get("engineeringTasks") or body.get("engineering_tasks")

    if "qaResults" in body or "qa_results" in body:
        cur_meta["qa_results"] = body.get("qaResults") or body.get("qa_results")

    if "betaFeedback" in body or "beta_feedback" in body:
        cur_meta["beta_feedback"] = body.get("betaFeedback") or body.get("beta_feedback")

    if "feedbackClusters" in body or "feedback_clusters" in body:
        clusters = body.get("feedbackClusters") or body.get("feedback_clusters")
        cur_meta["feedback_clusters"] = clusters
        if proj.telemetry:
            proj.telemetry.feedback_clusters = clusters

    if "readinessReport" in body or "readiness_report" in body:
        cur_meta["readiness_report"] = body.get("readinessReport") or body.get("readiness_report")

    if "appliedPatches" in body or "applied_patches" in body:
        cur_meta["applied_patches"] = body.get("appliedPatches") or body.get("applied_patches")

    if "mvpVersion" in body or "mvp_version" in body:
        cur_meta["mvp_version"] = body.get("mvpVersion") or body.get("mvp_version")

    if "launchStrategy" in body or "launch_strategy" in body:
        cur_meta["launch_strategy"] = body.get("launchStrategy") or body.get("launch_strategy")

    if "creatorAssets" in body or "creator_assets" in body:
        cur_meta["creator_assets"] = body.get("creatorAssets") or body.get("creator_assets")

    if "launchTelemetry" in body or "launch_telemetry" in body:
        cur_meta["launch_telemetry"] = body.get("launchTelemetry") or body.get("launch_telemetry")

    if "channelStats" in body or "channel_stats" in body:
        cur_meta["channel_stats"] = body.get("channelStats") or body.get("channel_stats")

    if "launchManagerData" in body or "launch_manager_data" in body:
        cur_meta["launch_manager_data"] = body.get("launchManagerData") or body.get("launch_manager_data")

    if "dispatchedActions" in body or "dispatched_actions" in body:
        cur_meta["dispatched_actions"] = body.get("dispatchedActions") or body.get("dispatched_actions")

    if "launchReport" in body or "launch_report" in body:
        cur_meta["launch_report"] = body.get("launchReport") or body.get("launch_report")

    if "launchStatus" in body or "launch_status" in body:
        cur_meta["launch_status"] = body.get("launchStatus") or body.get("launch_status")

    if "productInfrastructure" in body or "product_infrastructure" in body:
        cur_meta["product_infrastructure"] = body.get("productInfrastructure") or body.get("product_infrastructure")

    if "campaignKit" in body or "campaign_kit" in body:
        ck = body.get("campaignKit") or body.get("campaign_kit")
        if ck and isinstance(ck, dict):
            cur_meta["campaign_kit"] = ck
            cur_meta["campaign_launched"] = True
            if proj.validation_campaign:
                proj.validation_campaign.campaign_kit = ck
                flag_modified(proj.validation_campaign, "campaign_kit")

    if "campaignLaunched" in body or "campaign_launched" in body:
        cl = body.get("campaignLaunched") if body.get("campaignLaunched") is not None else body.get("campaign_launched")
        cur_meta["campaign_launched"] = bool(cl)

    proj.metadata_info = cur_meta
    flag_modified(proj, "metadata_info")

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
    """Save or update Step 2 Campaign Assets, Infrastructure, Step 3 Campaign Kit, and Creator Tasks."""
    proj = db.get(CoLaunchProject, project_id)
    if not proj:
        raise HTTPException(404, f"Project '{project_id}' not found")

    campaign = proj.validation_campaign
    if not campaign:
        campaign = ValidationCampaign(project_id=proj.id)
        db.add(campaign)

    prod_assets = body.product_assets if body.product_assets is not None else body.productAssets
    if prod_assets is not None:
        campaign.product_assets = prod_assets
        flag_modified(campaign, "product_assets")
    if body.infrastructure is not None:
        campaign.infrastructure = body.infrastructure
        flag_modified(campaign, "infrastructure")
    res_survey = body.research_survey if body.research_survey is not None else body.researchSurvey
    if res_survey is not None:
        campaign.research_survey = res_survey
        flag_modified(campaign, "research_survey")
    rev_status = body.review_status if body.review_status is not None else body.reviewStatus
    if rev_status is not None:
        campaign.review_status = rev_status
        if rev_status in ("approved", "launched"):
            campaign.approved_at = datetime.utcnow()
            campaign.approved_by = "Lead Founder"

    # Step 3: Campaign Kit & Launch State Persistence
    kit = body.campaign_kit if body.campaign_kit is not None else body.campaignKit
    if kit is None and prod_assets and isinstance(prod_assets, dict):
        if "campaign_kit" in prod_assets:
            kit = prod_assets["campaign_kit"]
        elif "campaignKit" in prod_assets:
            kit = prod_assets["campaignKit"]

    meta = dict(proj.metadata_info or {})
    if kit is not None:
        campaign.campaign_kit = kit
        meta["campaign_kit"] = kit
        meta["campaign_launched"] = True
        flag_modified(campaign, "campaign_kit")

    camp_launched = body.campaign_launched if body.campaign_launched is not None else body.campaignLaunched
    if camp_launched is not None:
        meta["campaign_launched"] = camp_launched
        if camp_launched:
            campaign.review_status = "approved"

    proj.metadata_info = meta
    flag_modified(proj, "metadata_info")

    # Step 3: Creator Campaign Tasks in PostgreSQL
    creator_tasks = body.creator_tasks if body.creator_tasks is not None else body.creatorTasks
    if creator_tasks is not None and isinstance(creator_tasks, list) and len(creator_tasks) > 0:
        db.query(CreatorCampaignTask).filter(CreatorCampaignTask.project_id == proj.id).delete()
        for idx, t in enumerate(creator_tasks):
            t_day = t.get("dayNumber") or t.get("day_number") or t.get("day") or (idx + 1)
            t_status = "completed" if (t.get("done") or t.get("status") == "completed") else (t.get("status") or "pending")
            
            # Smart draft extraction if draft is empty but draftKey or channel exists
            raw_draft = str(t.get("content") or t.get("content_draft") or t.get("draft") or "").strip()
            draft_key = t.get("draftKey") or t.get("draft_key")
            if not raw_draft and kit and isinstance(kit, dict):
                if draft_key and kit.get(draft_key):
                    raw_draft = str(kit.get(draft_key))
                elif t.get("channel") in ("Twitter / X", "twitter", "All Social Channels") and kit.get("announcementPost"):
                    raw_draft = str(kit.get("announcementPost"))
                elif "Story" in str(t.get("title", "")) and kit.get("storySequence"):
                    raw_draft = str(kit.get("storySequence"))
                elif "Video" in str(t.get("title", "")) and kit.get("videoScript"):
                    raw_draft = str(kit.get("videoScript"))
                elif "Newsletter" in str(t.get("title", "")) and kit.get("newsletterDraft"):
                    raw_draft = str(kit.get("newsletterDraft"))
                elif "DM" in str(t.get("title", "")) and kit.get("directMessageScript"):
                    raw_draft = str(kit.get("directMessageScript"))

            task_obj = CreatorCampaignTask(
                project_id=proj.id,
                day_number=int(t_day),
                channel=str(t.get("channel") or "instagram"),
                task_title=str(t.get("title") or t.get("task_title") or f"Day {t_day} Campaign Post"),
                content_draft=raw_draft,
                cta_text=str(t.get("cta") or t.get("cta_text") or ""),
                tracking_link=str(t.get("trackingLink") or t.get("tracking_link") or ""),
                media_prompt=str(t.get("mediaPrompt") or t.get("media_prompt") or ""),
                status=t_status,
                completed_at=datetime.utcnow() if t_status == "completed" else None
            )
            db.add(task_obj)

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


@router.post("/{project_id}/remind-task/{task_id}")
def send_task_reminder(project_id: str, task_id: str, db: Session = Depends(get_db)):
    """
    Send an email reminder to the creator for a specific or overdue campaign post task.
    Includes the post draft, channel instructions, and tracking link.
    """
    proj = db.get(CoLaunchProject, project_id)
    if not proj:
        raise HTTPException(404, f"Project '{project_id}' not found")

    task = db.query(CreatorCampaignTask).filter(
        CreatorCampaignTask.project_id == project_id,
        CreatorCampaignTask.id == task_id
    ).first()
    if not task:
        raise HTTPException(404, f"Task '{task_id}' not found")

    from app.integrations.email_provider import email_provider
    from app.config import settings

    creator_email = (proj.creator_email or settings.RECIPIENT_EMAIL or "").strip()
    admin_email = (settings.ADMIN_EMAIL or "elishadamu97@gmail.com").strip()
    base_frontend = (settings.FRONTEND_URL or "https://creator-forge-frontend.vercel.app").rstrip("/")
    portal_slug = (proj.creator_handle or proj.creator_name or "creator").replace("@", "").replace(" ", "").strip().lower()
    portal_magic_link = f"{base_frontend}/portal/{portal_slug}?token={proj.portal_token}&project={proj.id}"

    subject = f"[LAUNCH MISSION] Day {task.day_number} Posting Reminder: {task.task_title}"
    body_text = f"""Hi {proj.creator_name or 'there'},

This is a quick reminder for your Day {task.day_number} co-launch milestone for {proj.product_name}!

Channel: {task.channel.upper()}
Mission: {task.task_title}

--- READY-TO-POST CONTENT DRAFT ---
{task.content_draft or 'See portal for draft details'}

Call to Action: {task.cta_text or 'Claim founding access'}
Your Tracking Link: {task.tracking_link or f'{base_frontend}/preorder/{portal_slug}'}

You can view the full draft, story sequences, and mark this task complete in your Creator Portal:
{portal_magic_link}

Best regards,
Creator Forge Studio Operations"""

    body_html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 24px; background: #0c0e14; color: #f1f5f9; border-radius: 16px; border: 1px solid rgba(255,255,255,0.08);">
        <div style="display: inline-block; padding: 4px 12px; background: rgba(168,85,247,0.15); border: 1px solid rgba(168,85,247,0.3); border-radius: 20px; font-size: 11px; font-weight: bold; color: #c084fc; margin-bottom: 12px;">
            DAY {task.day_number} LAUNCH MISSION REMINDER
        </div>
        <h2 style="color: #ffffff; margin-top: 0; font-size: 20px;">{task.task_title}</h2>
        <p style="color: #94a3b8; font-size: 14px; line-height: 1.6;">
            Hi {proj.creator_name or 'there'}, here is your scheduled launch post for <strong>{proj.product_name}</strong> on <strong>{task.channel.capitalize()}</strong>. Ready to copy and publish to your audience:
        </p>

        <div style="margin: 20px 0; padding: 18px; background: #161a24; border: 1px solid rgba(255,255,255,0.08); border-radius: 12px;">
            <p style="margin: 0 0 8px 0; font-size: 11px; font-weight: bold; color: #a855f7; text-transform: uppercase;">Ready-to-Post Copy Draft:</p>
            <p style="margin: 0; font-size: 13px; color: #e2e8f0; line-height: 1.7; white-space: pre-wrap;">{task.content_draft or ''}</p>
        </div>

        <div style="margin: 16px 0; padding: 14px; background: rgba(16,185,129,0.08); border: 1px solid rgba(16,185,129,0.25); border-radius: 12px;">
            <p style="margin: 0 0 6px 0; font-size: 11px; font-weight: bold; color: #34d399; text-transform: uppercase;">Your Unique Pre-Order Tracking Link:</p>
            <a href="{task.tracking_link or portal_magic_link}" style="color: #6ee7b7; font-size: 13px; font-weight: bold; word-break: break-all;">{task.tracking_link or portal_magic_link}</a>
        </div>

        <div style="margin: 24px 0 12px 0; text-align: center;">
            <a href="{portal_magic_link}" style="display: inline-block; padding: 12px 28px; background: #9333ea; color: #ffffff; text-decoration: none; font-weight: bold; font-size: 14px; border-radius: 10px; box-shadow: 0 4px 14px rgba(147, 51, 234, 0.4);">
                Open Creator Portal & Mark Done &rarr;
            </a>
        </div>
        <p style="color: #64748b; font-size: 11px; text-align: center; margin-top: 16px;">
            Co-Launch Partner Portal for {proj.product_name} &bull; 50/50 Revenue Share Active
        </p>
    </div>
    """

    sent_to = []
    if creator_email and "@" in creator_email:
        try:
            email_provider.send(
                to_email=creator_email,
                subject=subject,
                body_html=body_html,
                body_text=body_text
            )
            sent_to.append(creator_email)
        except Exception as e:
            logger.warning(f"Failed to send task reminder to creator {creator_email}: {e}")

    # Also notify admin
    if admin_email and "@" in admin_email and admin_email not in sent_to:
        try:
            email_provider.send(
                to_email=admin_email,
                subject=f"[ADMIN COPY] {subject}",
                body_html=body_html,
                body_text=body_text
            )
            sent_to.append(admin_email)
        except Exception as e:
            logger.warning(f"Failed to send task reminder admin copy: {e}")

    # Log in activity logs
    meta = dict(proj.metadata_info or {})
    logs = list(meta.get("activity_logs", []))
    logs.append({
        "id": str(uuid.uuid4()),
        "type": "campaign_reminder",
        "description": f"Dispatched reminder email for Day {task.day_number} ({task.channel}) to {', '.join(sent_to) if sent_to else 'Pending email'}",
        "timestamp": datetime.utcnow().isoformat()
    })
    meta["activity_logs"] = logs
    proj.metadata_info = meta
    db.commit()

    return {
        "status": "sent" if sent_to else "mocked",
        "sentTo": sent_to,
        "taskId": task.id,
        "taskTitle": task.task_title,
        "dayNumber": task.day_number,
        "channel": task.channel
    }


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
    Accurately tracks unique devices/visitors using client IDs and device fingerprints.
    Page reloads on the same device increment page views, NOT unique visitors.
    """
    # Exclude internal admin dashboard visits if accidentally sent
    if body.path and ("/dashboard" in body.path or "/admin" in body.path):
        return {"status": "ignored", "message": "Admin dashboard views are not tracked as customer visits"}

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

    # 1. Total page views always increments by 1
    telemetry.views = int(telemetry.views or 0) + 1

    # 2. Check if this client ID or device fingerprint has already been recorded
    meta = dict(proj.metadata_info or {})
    raw_tracked = meta.get("tracked_client_ids") or []
    tracked_clients = set(raw_tracked)

    client_key = (body.clientId or body.fingerprint or "").strip()

    is_truly_new = False
    if client_key:
        if client_key not in tracked_clients:
            tracked_clients.add(client_key)
            meta["tracked_client_ids"] = list(tracked_clients)[-5000:]
            proj.metadata_info = meta
            is_truly_new = True
    elif body.isNewVisitor is True:
        is_truly_new = True

    # 3. Only increment unique visitors if genuinely a new device/client, or if visitors count was 0
    if is_truly_new or not telemetry.visitors:
        telemetry.visitors = max(1, len(tracked_clients) if tracked_clients else (int(telemetry.visitors or 0) + 1))
        proj.visitors = telemetry.visitors

    # Map normalized channel
    chan = body.channel or "Direct / Other"
    cur_attr = dict(telemetry.channel_attribution or {})
    if is_truly_new or chan not in cur_attr:
        cur_attr[chan] = cur_attr.get(chan, 0) + 1
        telemetry.channel_attribution = cur_attr

    # Recalculate conversion rate
    res_count = len(telemetry.reservations or [])
    if telemetry.visitors and telemetry.visitors > 0:
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


@router.post("/record-survey-response")
@router.post("/{project_id}/survey-response")
def record_survey_response_universal(
    body: RecordSurveyResponseRequest,
    project_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Universal public survey response recorder called by /survey/:slug form or simulation.
    Persists respondent answers, increments question response counts, updates telemetry, and logs activity in DB.
    """
    proj = None
    target_id = project_id or body.projectId
    if target_id:
        proj = db.get(CoLaunchProject, target_id)
    
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
        raise HTTPException(404, "No active co-launch project found to record survey response")

    campaign = proj.validation_campaign
    if not campaign:
        campaign = ValidationCampaign(project_id=proj.id)
        db.add(campaign)

    res_survey = dict(campaign.research_survey or {})
    res_id = f"sr_{int(datetime.utcnow().timestamp()*1000)}"
    timestamp_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    res_name = (body.name or body.respondentName or "").strip() or "Community Member"
    res_email = (body.email or body.respondentEmail or "").strip() or f"respondent_{res_id[-4:]}@example.com"
    res_rating = int(body.rating if body.rating is not None else (body.intentScore if body.intentScore is not None else 8))

    response_item = {
        "id": res_id,
        "name": res_name,
        "email": res_email,
        "rating": res_rating,
        "answers": body.answers or {},
        "submittedAt": body.submittedAt or timestamp_str,
        "date": datetime.utcnow().strftime("%Y-%m-%d")
    }

    cur_responses = list(res_survey.get("responses") or [])
    cur_responses.insert(0, response_item)
    res_survey["responses"] = cur_responses

    # Update question response counts
    cur_questions = list(res_survey.get("questions") or [])
    if cur_questions:
        for q in cur_questions:
            qid = q.get("id")
            if body.answers and qid in body.answers and str(body.answers[qid]).strip():
                q["responseCount"] = int(q.get("responseCount") or 0) + 1
            elif not body.answers:
                q["responseCount"] = int(q.get("responseCount") or 0) + 1
        res_survey["questions"] = cur_questions

    campaign.research_survey = res_survey
    flag_modified(campaign, "research_survey")

    # Also keep in proj.metadata_info
    meta = dict(proj.metadata_info or {})
    meta["survey_responses"] = cur_responses
    
    # Telemetry signups
    telemetry = proj.telemetry
    if telemetry:
        telemetry.signups = max(int(telemetry.signups or 0), len(cur_responses))

    # Activity Log
    act_logs = list(meta.get("activity_logs") or [])
    act_item = {
        "id": f"act_{int(datetime.utcnow().timestamp()*1000)}",
        "action": "Audience Survey Response Recorded",
        "details": f"Survey feedback submitted by {res_name} ({res_email}) with intent score {res_rating}/10",
        "category": "research",
        "timestamp": timestamp_str
    }
    act_logs.insert(0, act_item)
    meta["activity_logs"] = act_logs[:50]
    proj.metadata_info = meta
    flag_modified(proj, "metadata_info")

    db.commit()
    db.refresh(proj)
    return _format_project_response(proj)


@router.delete("/{project_id}/survey-response/{response_id}")
def delete_survey_response(project_id: str, response_id: str, db: Session = Depends(get_db)):
    """Delete a single survey response and recalculate question response counts."""
    proj = db.get(CoLaunchProject, project_id)
    if not proj:
        raise HTTPException(404, f"Project '{project_id}' not found")
    
    campaign = proj.validation_campaign
    if not campaign:
        raise HTTPException(404, "No validation campaign found")

    res_survey = dict(campaign.research_survey or {})
    cur_responses = list(res_survey.get("responses") or [])
    
    new_responses = [r for r in cur_responses if r.get("id") != response_id]
    res_survey["responses"] = new_responses

    # Recalculate question response counts based on remaining responses
    cur_questions = list(res_survey.get("questions") or [])
    if cur_questions:
        for q in cur_questions:
            qid = q.get("id")
            count = 0
            for r in new_responses:
                ans = r.get("answers") or {}
                if qid in ans and str(ans[qid]).strip():
                    count += 1
                elif not ans:
                    count += 1
            q["responseCount"] = count
        res_survey["questions"] = cur_questions

    campaign.research_survey = res_survey
    flag_modified(campaign, "research_survey")

    meta = dict(proj.metadata_info or {})
    meta["survey_responses"] = new_responses
    proj.metadata_info = meta
    flag_modified(proj, "metadata_info")

    telemetry = proj.telemetry
    if telemetry:
        telemetry.signups = len(new_responses)

    db.commit()
    db.refresh(proj)
    return _format_project_response(proj)


@router.delete("/{project_id}/survey-responses")
def clear_all_survey_responses(project_id: str, db: Session = Depends(get_db)):
    """Clear all survey responses and reset question response counts to 0."""
    proj = db.get(CoLaunchProject, project_id)
    if not proj:
        raise HTTPException(404, f"Project '{project_id}' not found")
    
    campaign = proj.validation_campaign
    if not campaign:
        raise HTTPException(404, "No validation campaign found")

    res_survey = dict(campaign.research_survey or {})
    res_survey["responses"] = []
    res_survey["analysis"] = None

    cur_questions = list(res_survey.get("questions") or [])
    if cur_questions:
        for q in cur_questions:
            q["responseCount"] = 0
        res_survey["questions"] = cur_questions

    campaign.research_survey = res_survey
    flag_modified(campaign, "research_survey")

    meta = dict(proj.metadata_info or {})
    meta["survey_responses"] = []
    meta["survey_analysis"] = None
    proj.metadata_info = meta
    flag_modified(proj, "metadata_info")

    telemetry = proj.telemetry
    if telemetry:
        telemetry.signups = 0

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

