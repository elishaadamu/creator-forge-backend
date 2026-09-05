import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime,
    ForeignKey, Text, JSON
)
from sqlalchemy.orm import relationship

from app.database import Base


def _uuid():
    return str(uuid.uuid4())


def _now():
    return datetime.utcnow()


class CoLaunchProject(Base):
    """
    Core Co-Launch Project entity representing the 50/50 partnership between
    the platform and the acquired creator across Phase 1 (Validate), Phase 2 (Build MVP),
    and Phase 3 (Launch).
    """
    __tablename__ = "co_launch_projects"

    id = Column(String, primary_key=True, default=_uuid)
    creator_id = Column(String, ForeignKey("creators.id", ondelete="SET NULL"), nullable=True, index=True)
    creator_handle = Column(String, nullable=True)
    creator_name = Column(String, nullable=True)
    creator_avatar = Column(String, nullable=True)
    creator_email = Column(String, nullable=True)
    niche = Column(String, nullable=True)
    followers = Column(String, nullable=True)

    product_name = Column(String, nullable=False, default="New Product OS")
    product_tagline = Column(String, nullable=True)
    target_audience = Column(Text, nullable=True)
    pricing = Column(String, nullable=True, default="$29/mo Starter • $79/mo Pro")
    revenue_model = Column(String, nullable=True)

    current_phase = Column(Integer, default=1, index=True)  # 1 = Validate, 2 = Build MVP, 3 = Launch
    current_step = Column(String, default="plan")           # 'plan', 'assets', 'campaign', 'optimize', 'gate'
    status = Column(String, default="validating", index=True) # 'validating', 'building', 'launched', 'paused', 'killed'

    presale_target = Column(Float, default=5000.0)
    current_presales = Column(Float, default=0.0)
    visitors = Column(Integer, default=0)
    conversion_rate = Column(Float, default=0.0)

    portal_token = Column(String, default="cf_sec_live")
    portal_link_sent = Column(Boolean, default=False)
    portal_link_sent_to = Column(String, nullable=True)
    portal_link_sent_at = Column(DateTime, nullable=True)

    selected_concept = Column(JSON, default=dict)
    metadata_info = Column(JSON, default=dict)

    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    # Relationships
    validation_plan = relationship("ValidationPlan", back_populates="project", uselist=False, cascade="all, delete-orphan")
    validation_campaign = relationship("ValidationCampaign", back_populates="project", uselist=False, cascade="all, delete-orphan")
    creator_tasks = relationship("CreatorCampaignTask", back_populates="project", cascade="all, delete-orphan", order_by="CreatorCampaignTask.day_number")
    telemetry = relationship("ValidationTelemetry", back_populates="project", uselist=False, cascade="all, delete-orphan")
    gate_decisions = relationship("ValidationGateDecision", back_populates="project", cascade="all, delete-orphan", order_by="desc(ValidationGateDecision.decided_at)")


class ValidationPlan(Base):
    """
    Step 1: Validation Plan Specification.
    AI defines customer, problem, offer, pricing, test method, validation period + success threshold.
    """
    __tablename__ = "validation_plans"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("co_launch_projects.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)

    customer = Column(Text, nullable=True)
    problem = Column(Text, nullable=True)
    offer = Column(Text, nullable=True)
    pricing = Column(String, nullable=True)
    test_method = Column(Text, nullable=True)
    period = Column(String, default="14 days")
    threshold = Column(Text, default="$5,000 in presales within 14 days")
    target_revenue = Column(Float, default=5000.0)
    status = Column(String, default="ready") # 'draft', 'ready', 'locked'

    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    project = relationship("CoLaunchProject", back_populates="validation_plan")


class ValidationCampaign(Base):
    """
    Step 2: Build Validation Campaign.
    Product assets (name, branding, positioning, copy, mockups, pricing),
    infrastructure (landing page, checkout, waitlist, analytics),
    research (survey questions & feedback), and human review status.
    """
    __tablename__ = "validation_campaigns"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("co_launch_projects.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)

    product_assets = Column(JSON, default=dict)
    infrastructure = Column(JSON, default=dict)
    research_survey = Column(JSON, default=dict)
    campaign_kit = Column(JSON, default=dict)

    review_status = Column(String, default="draft", index=True) # 'draft', 'pending_approval', 'approved', 'launched'
    approved_by = Column(String, nullable=True)
    approved_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    project = relationship("CoLaunchProject", back_populates="validation_campaign")


class CreatorCampaignTask(Base):
    """
    Step 3: Creator Campaign Daily Checklist.
    Posting schedule, social posts, stories, newsletter, video scripts, polls, CTAs, tracking links.
    """
    __tablename__ = "creator_campaign_tasks"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("co_launch_projects.id", ondelete="CASCADE"), nullable=False, index=True)

    day_number = Column(Integer, default=1, index=True)
    channel = Column(String, default="instagram") # 'instagram', 'youtube', 'newsletter', 'twitter', 'tiktok'
    task_title = Column(String, nullable=False)   # e.g. "Post Instagram Story #2"
    content_draft = Column(Text, nullable=True)
    cta_text = Column(String, nullable=True)
    tracking_link = Column(String, nullable=True)
    media_prompt = Column(String, nullable=True)
    status = Column(String, default="pending", index=True) # 'pending', 'today', 'completed', 'skipped'
    completed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    project = relationship("CoLaunchProject", back_populates="creator_tasks")


class ValidationTelemetry(Base):
    """
    Step 4: Run + Optimize Validation.
    Live traffic, CTR, signups, presales, revenue, conversion, attribution, preorder reservations,
    and AI-generated experiments.
    """
    __tablename__ = "validation_telemetry"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("co_launch_projects.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)

    visitors = Column(Integer, default=0)
    views = Column(Integer, default=0)
    ctr = Column(Float, default=0.0)
    signups = Column(Integer, default=0)
    presales_count = Column(Integer, default=0)
    presales_revenue = Column(Float, default=0.0)
    conversion_rate = Column(Float, default=0.0)

    reservations = Column(JSON, default=list)
    channel_attribution = Column(JSON, default=dict)
    experiments = Column(JSON, default=list)
    feedback_clusters = Column(JSON, default=list)

    updated_at = Column(DateTime, default=_now, onupdate=_now)

    project = relationship("CoLaunchProject", back_populates="telemetry")


class ValidationGateDecision(Base):
    """
    Step 5: Validation Gate Checkpoint.
    Records the executive pass/test-again/fail decision, compares against the Step 1 threshold,
    and documents milestone outcomes.
    """
    __tablename__ = "validation_gate_decisions"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("co_launch_projects.id", ondelete="CASCADE"), nullable=False, index=True)

    decision = Column(String, nullable=False) # 'pass_to_phase2', 'iterate_validation', 'kill_project'
    target_revenue = Column(Float, default=5000.0)
    achieved_revenue = Column(Float, default=0.0)
    backers_count = Column(Integer, default=0)
    conversion_rate = Column(Float, default=0.0)
    gate_status = Column(String, default="passed") # 'passed', 'iterating', 'failed'
    gate_notes = Column(Text, nullable=True)

    decided_at = Column(DateTime, default=_now)

    project = relationship("CoLaunchProject", back_populates="gate_decisions")
