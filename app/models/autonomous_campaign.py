import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime,
    Text, JSON, Enum as SAEnum,
)

from app.database import Base


def _uuid():
    return str(uuid.uuid4())


def _now():
    return datetime.utcnow()


class AutonomousCampaign(Base):
    __tablename__ = "autonomous_campaigns"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False, default="100k-1M Creators Autonomous Batch")
    description = Column(Text, default="Automated outreach targeting top creators with 100k-1M followers, high engagement rates, and automatic 7-day follow-up.")
    
    # Target Criteria Filters
    target_weekly_limit = Column(Integer, default=50)      # Max creators reached per week
    min_followers = Column(Integer, default=100000)        # Default 100k
    max_followers = Column(Integer, default=1000000)       # Default 1M
    min_engagement_rate = Column(Float, default=2.0)       # Default 2.0%
    niches = Column(JSON, default=lambda: ["Tech", "Software", "SaaS", "Creator Economy", "Gaming"])  # Target niches

    # Template Settings (outreach message)
    template_subject = Column(String, default="Co-founder partnership inquiry for {{display_name}}")
    template_body = Column(
        Text,
        default=(
            "Hi {{first_name}},\n\n"
            "I've been following your {{niche}} content on {{platform}} and love how engaged your community is.\n\n"
            "We're building {{product_name}} — a high-growth product tailored for creators in {{niche}}. "
            "Given your audience scale ({{follower_count}} followers) and strong engagement, we'd love to discuss a "
            "co-founder partnership with a 50/50 revenue split.\n\n"
            "Are you open to a quick 15-minute sync this week?\n\n"
            "Best,\n"
            "Creator Forge Team"
        ),
    )

    # Follow-up Template Settings (1-week follow-up if no response)
    followup_template_subject = Column(String, default="Re: Co-founder partnership inquiry for {{display_name}}")
    followup_template_body = Column(
        Text,
        default=(
            "Hi {{first_name}},\n\n"
            "Following up on my note last week regarding the {{product_name}} co-founder partnership.\n\n"
            "Totally understand if your inbox is slammed! If you're open to exploring a custom digital product for your "
            "{{follower_count}} followers, let me know if Thursday or Friday works for a brief chat.\n\n"
            "Best,\n"
            "Creator Forge Team"
        ),
    )
    followup_delay_days = Column(Integer, default=7)        # Default 1 week gap

    # Operational Controls
    status = Column(
        SAEnum("active", "paused", "completed", name="autonomous_campaign_status_enum"),
        default="active",
        index=True,
    )
    auto_send = Column(Boolean, default=True)               # Fully autonomous send vs draft review
    
    # Analytics / Tracking
    total_sent = Column(Integer, default=0)
    total_replied = Column(Integer, default=0)
    total_followups_sent = Column(Integer, default=0)
    last_run_at = Column(DateTime)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)
