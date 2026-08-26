import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy.orm import Session
from app.database import SessionLocal

from app.models.autonomous_campaign import AutonomousCampaign
from app.models.creator import Creator, Contact, ProductRecommendation, MetricsSnapshot
from app.models.outreach import OutreachMessage, Thread, FollowUp, Reply
from app.services import audit as audit_svc
from app.services.suppression import is_suppressed
from app.integrations.email_provider import email_provider

logger = logging.getLogger(__name__)
_SCHEDULER_RUNNING = False


EMAIL_REGEX = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+')


def is_real_valid_email(email_str: Optional[str]) -> bool:
    """Validate that email is not empty, missing @/., or a dummy @example.com domain."""
    if not email_str or not isinstance(email_str, str):
        return False
    email_clean = email_str.strip().lower()
    if "@" not in email_clean or "." not in email_clean:
        return False
    invalid_domains = ["example.com", "example.org", "example.net", "test.com", "placeholder.com"]
    if any(domain in email_clean for domain in invalid_domains):
        return False
    return True


def extract_email_from_text(text: Optional[str]) -> Optional[str]:
    """Extract first valid public email address found in bio, website, notes, etc."""
    if not text or not isinstance(text, str):
        return None
    matches = EMAIL_REGEX.findall(text)
    for m in matches:
        m_clean = m.strip().rstrip('.')
        if is_real_valid_email(m_clean):
            return m_clean
    return None


def format_follower_count(count: int) -> str:
    """Format follower count as 150K, 1.2M, etc."""
    if not count:
        return "10K+"
    if count >= 1_000_000:
        val = count / 1_000_000
        return f"{val:.1f}M".replace(".0M", "M")
    if count >= 1_000:
        val = count / 1_000
        return f"{int(val)}K"
    return str(count)


def render_template(template_str: str, creator: Creator, product_name: str = "Creator Academy") -> str:
    """Render template placeholders like {{display_name}}, {{niche}}, {{platform}}, etc."""
    if not template_str:
        return ""

    display_name = creator.display_name or creator.handle
    first_name = display_name.split()[0] if display_name else creator.handle

    niche_str = "content creation"
    if creator.niche and isinstance(creator.niche, list) and len(creator.niche) > 0:
        niche_str = creator.niche[0]
    elif isinstance(creator.niche, str) and creator.niche:
        niche_str = creator.niche

    platform_str = (creator.platform or "social media").title()
    follower_str = format_follower_count(creator.follower_count or 0)
    handle_str = f"@{creator.handle.lstrip('@')}"

    replacements = {
        "{{display_name}}": display_name,
        "{{first_name}}": first_name,
        "{{handle}}": handle_str,
        "{{platform}}": platform_str,
        "{{niche}}": niche_str,
        "{{follower_count}}": follower_str,
        "{{product_name}}": product_name,
    }

    result = template_str
    for key, val in replacements.items():
        result = result.replace(key, str(val))

    return result


def run_autonomous_batch(
    db: Session,
    campaign_id: str,
    limit: Optional[int] = None,
    creator_ids: Optional[List[str]] = None,
    creators_data: Optional[List[dict]] = None,
    template_subject: Optional[str] = None,
    template_body: Optional[str] = None,
    actor: str = "autonomous_engine",
) -> Dict:
    """
    Run an autonomous batch outreach execution for a given campaign.
    Supports explicitly passed creators/creators_data with user-modified emails,
    or falls back to eligible filtered creators in database.
    """
    campaign = db.get(AutonomousCampaign, campaign_id)
    if not campaign:
        raise ValueError(f"Autonomous campaign {campaign_id} not found")

    if campaign.status == "paused":
        return {"status": "paused", "sent": 0, "queued": 0, "message": "Campaign is currently paused."}

    if actor == "autonomous_scheduler" and campaign.last_run_at:
        next_run_at = campaign.last_run_at + timedelta(days=7)
        if datetime.utcnow() < next_run_at:
            return {
                "status": "throttled",
                "sent": 0,
                "queued": 0,
                "message": f"Automatic outreach is paused until {next_run_at.isoformat()}.",
            }

    max_batch = limit or campaign.target_weekly_limit or 50
    eligible_creators = []

    # 1. If explicit creators_data provided (e.g. from Acquisition Engine active batch)
    if creators_data and isinstance(creators_data, list) and len(creators_data) > 0:
        for c_data in creators_data:
            c_handle = str(c_data.get("handle") or "").lstrip("@").strip()
            c_id = str(c_data.get("id") or "")
            c_email = str(c_data.get("email") or c_data.get("email_public") or "").strip()

            creator = None
            if c_id and not c_id.startswith("auto_"):
                creator = db.get(Creator, c_id)
            if not creator and c_handle:
                creator = db.query(Creator).filter(Creator.handle == c_handle).first()

            if not creator and c_handle:
                # Create creator on the fly if not in DB yet
                try:
                    from app.services.discovery import create_or_get_creator
                    creator, _ = create_or_get_creator(
                        db=db,
                        handle=c_handle,
                        platform=str(c_data.get("platform", "youtube")).lower(),
                        display_name=str(c_data.get("display_name") or c_data.get("name") or c_handle),
                        follower_count=int(c_data.get("follower_count") or 100000),
                        niche=c_data.get("niche") or ["Tech"],
                        email_public=c_email,
                        actor=actor
                    )
                except Exception as e:
                    logger.warn(f"[Autonomous Batch] Failed to create creator @{c_handle}: {e}")

            if creator:
                if actor == "autonomous_scheduler":
                    already_contacted = db.query(OutreachMessage).filter(
                        OutreachMessage.creator_id == creator.id,
                        OutreachMessage.status.in_(["queued", "sent"]),
                    ).first()
                    if already_contacted:
                        continue
                if c_email:
                    creator.email_public = c_email
                    db.commit()
                eligible_creators.append(creator)

    # 2. If explicit creator_ids provided
    elif creator_ids and isinstance(creator_ids, list) and len(creator_ids) > 0:
        for cid in creator_ids:
            c = db.get(Creator, cid)
            if c:
                eligible_creators.append(c)

    # 3. Fallback: Query eligible creators from DB
    else:
        query = db.query(Creator).filter(
            Creator.follower_count >= campaign.min_followers,
            Creator.follower_count <= campaign.max_followers,
            Creator.status.in_(["discovered", "qualified", "in_review", "approved"]),
        )

        all_creators = query.all()

        for creator in all_creators:
            # Check suppression
            if is_suppressed(db, creator_id=creator.id, email=creator.email_public):
                continue

            # Check if already outreach sent for this campaign
            if actor == "autonomous_scheduler":
                already_sent = db.query(OutreachMessage).filter(
                    OutreachMessage.creator_id == creator.id,
                    OutreachMessage.status.in_(["queued", "sent"]),
                ).first()
                if already_sent:
                    continue

            # Niche matching if campaign specifies target niches
            if campaign.niches and isinstance(campaign.niches, list) and len(campaign.niches) > 0:
                creator_niches = creator.niche if isinstance(creator.niche, list) else []
                if creator.bio:
                    bio_lower = creator.bio.lower()
                    niche_match = any(n.lower() in bio_lower for n in campaign.niches)
                else:
                    niche_match = False

                if not niche_match:
                    niche_match = any(
                        any(n.lower() in str(cn).lower() for n in campaign.niches)
                        for cn in creator_niches
                    )
                # If no niche matched, skip (unless creator niche list is empty, then allow)
                if creator_niches and not niche_match:
                    continue

            # Engagement rate check (metrics snapshot or creator.engagement_score)
            eng_rate = creator.engagement_score or 0.0
            snapshot = db.query(MetricsSnapshot).filter(
                MetricsSnapshot.creator_id == creator.id
            ).order_by(MetricsSnapshot.snapshot_date.desc()).first()
            if snapshot and snapshot.engagement_rate:
                eng_rate = max(eng_rate, snapshot.engagement_rate)

            # Minimum engagement rate check (default threshold 2.0%)
            if campaign.min_engagement_rate and eng_rate < campaign.min_engagement_rate and eng_rate > 0:
                continue

            eligible_creators.append(creator)
            if len(eligible_creators) >= max_batch:
                break

    results = {"total_eligible": len(eligible_creators), "sent": 0, "queued": 0, "errors": [], "processed_creators": []}

    for creator in eligible_creators:
        try:
            # Find product recommendation or fallback
            rec = db.query(ProductRecommendation).filter(
                ProductRecommendation.creator_id == creator.id
            ).first()
            product_name = rec.product_name if rec else f"{creator.niche[0] if creator.niche and isinstance(creator.niche, list) else 'Creator'} Product"

            tmpl_s = template_subject or campaign.template_subject
            tmpl_b = template_body or campaign.template_body
            subject = render_template(tmpl_s, creator, product_name)
            body = render_template(tmpl_b, creator, product_name)

            # Determine real public email address
            target_email = None
            if is_real_valid_email(creator.email_public):
                target_email = creator.email_public.strip()

            contact = db.query(Contact).filter(Contact.creator_id == creator.id, Contact.contact_type == "email").first()
            if contact and is_real_valid_email(contact.value):
                if not target_email:
                    target_email = contact.value.strip()

            # Fallback: Extract email from bio, website, or discovery notes
            if not target_email:
                extracted = extract_email_from_text(creator.bio) or extract_email_from_text(creator.website) or extract_email_from_text(creator.discovery_notes)
                if extracted:
                    target_email = extracted
                    creator.email_public = extracted
                    db.commit()

            print(f"\n[AUTONOMOUS BATCH CREATOR] ID='{creator.id}' | Handle='{creator.handle}' | Name='{creator.display_name}' | email_public='{creator.email_public}' | target_email='{target_email}'")
            logger.info(f"[AUTONOMOUS BATCH] Creator ID={creator.id} Handle={creator.handle} Name={creator.display_name} PublicEmail={creator.email_public} TargetEmail={target_email}")

            # Ensure contact record exists with valid email
            if target_email:
                if not contact:
                    contact = Contact(
                        creator_id=creator.id,
                        contact_type="email",
                        value=target_email,
                        source="public_profile",
                    )
                    db.add(contact)
                    db.commit()
                    db.refresh(contact)
                elif not is_real_valid_email(contact.value):
                    contact.value = target_email
                    db.commit()

            if target_email and is_real_valid_email(target_email):
                msg_status = "queued" if campaign.auto_send else "draft"
                outreach_msg = OutreachMessage(
                    creator_id=creator.id,
                    campaign_id="default",
                    contact_id=contact.id if contact else None,
                    subject=subject,
                    body=body,
                    send_method="email",
                    status=msg_status,
                    queued_at=datetime.utcnow(),
                )
                db.add(outreach_msg)
                db.commit()
                db.refresh(outreach_msg)

                # Create thread for tracking
                thread = Thread(
                    creator_id=creator.id,
                    outreach_message_id=outreach_msg.id,
                    status="open",
                    created_at=datetime.utcnow(),
                )
                db.add(thread)
                db.commit()

                # Dispatch email via Google SMTP
                if campaign.auto_send:
                    try:
                        email_provider.send(
                            to_email=target_email,
                            subject=subject,
                            body_html=body.replace("\n", "<br>"),
                            body_text=body,
                        )
                        outreach_msg.status = "sent"
                        outreach_msg.sent_at = datetime.utcnow()
                        db.commit()
                        results["sent"] += 1
                    except Exception as send_err:
                        outreach_msg.status = "failed"
                        outreach_msg.send_error = str(send_err)
                        db.commit()
                        results["errors"].append({"creator_id": creator.id, "error": f"Send error: {send_err}"})
                else:
                    results["queued"] += 1

                final_status = outreach_msg.status
                send_err_val = outreach_msg.send_error
            else:
                # Creator has no public email address — skip outreach dispatch
                final_status = "skipped_no_email"
                send_err_val = "No valid email address found"
                results["skipped_no_email"] = results.get("skipped_no_email", 0) + 1

            results["processed_creators"].append({
                "id": creator.id,
                "handle": creator.handle,
                "display_name": creator.display_name,
                "email_public": creator.email_public,
                "target_email": target_email,
                "status": final_status,
                "send_error": send_err_val,
            })

            campaign.total_sent = (campaign.total_sent or 0) + 1
            audit_svc.log(
                db,
                action="autonomous_outreach_generated",
                entity_type="outreach_message",
                entity_id=outreach_msg.id,
                actor=actor,
                details={"campaign_id": campaign_id, "creator_handle": creator.handle},
            )
        except Exception as e:
            results["errors"].append({"creator_id": creator.id, "error": str(e)})

    campaign.last_run_at = datetime.utcnow()
    db.commit()

    return results


def process_autonomous_followups(
    db: Session,
    campaign_id: Optional[str] = None,
    actor: str = "autonomous_engine",
) -> Dict:
    """
    Process 1-week (7-day) follow-ups for open threads with no reply.
    """
    campaign_query = db.query(AutonomousCampaign)
    if campaign_id:
        campaign_query = campaign_query.filter(AutonomousCampaign.id == campaign_id)
    
    campaigns = campaign_query.filter(AutonomousCampaign.status == "active").all()
    if not campaigns:
        return {"processed": 0, "sent": 0, "message": "No active autonomous campaigns found"}

    results = {"processed": 0, "sent": 0, "queued": 0, "errors": []}

    for campaign in campaigns:
        delay_days = campaign.followup_delay_days or 7
        cutoff_date = datetime.utcnow() - timedelta(days=delay_days)

        # Query open threads for messages in this campaign created before cutoff_date
        threads = (
            db.query(Thread)
            .join(OutreachMessage, Thread.outreach_message_id == OutreachMessage.id)
            .filter(
                OutreachMessage.campaign_id == campaign.id,
                Thread.status == "open",
                Thread.created_at <= cutoff_date,
            )
            .all()
        )

        for thread in threads:
            # Check if creator already replied
            has_reply = db.query(Reply).filter(Reply.thread_id == thread.id).first()
            if has_reply:
                thread.status = "replied"
                db.commit()
                continue

            # Check if a follow-up already exists
            existing_fu = db.query(FollowUp).filter(
                FollowUp.thread_id == thread.id,
                FollowUp.status != "skipped",
            ).first()
            if existing_fu:
                continue

            creator = db.get(Creator, thread.creator_id)
            if not creator:
                continue

            try:
                rec = db.query(ProductRecommendation).filter(
                    ProductRecommendation.creator_id == creator.id
                ).first()
                product_name = rec.product_name if rec else "Creator Academy"

                fu_subject = render_template(campaign.followup_template_subject, creator, product_name)
                fu_body = render_template(campaign.followup_template_body, creator, product_name)
                full_draft = f"Subject: {fu_subject}\n\n{fu_body}"

                fu_status = "approved" if campaign.auto_send else "draft"
                fu = FollowUp(
                    thread_id=thread.id,
                    draft=full_draft,
                    status=fu_status,
                    scheduled_for=datetime.utcnow(),
                )
                db.add(fu)
                db.commit()
                db.refresh(fu)

                results["processed"] += 1

                # If auto-send enabled, attempt sending email
                original_msg = db.get(OutreachMessage, thread.outreach_message_id)
                contact = db.get(Contact, original_msg.contact_id) if (original_msg and original_msg.contact_id) else None
                if not contact and creator.email_public:
                    contact = db.query(Contact).filter(Contact.creator_id == creator.id).first()

                if campaign.auto_send and contact and contact.value and not is_suppressed(db, email=contact.value):
                    try:
                        email_provider.send(
                            to_email=contact.value,
                            subject=fu_subject,
                            body_html=fu_body.replace("\n", "<br>"),
                            body_text=fu_body,
                        )
                        fu.status = "sent"
                        fu.sent_at = datetime.utcnow()
                        thread.last_activity = datetime.utcnow()
                        campaign.total_followups_sent = (campaign.total_followups_sent or 0) + 1
                        db.commit()
                        results["sent"] += 1
                    except Exception as fu_err:
                        results["errors"].append({"thread_id": thread.id, "error": f"Followup send error: {fu_err}"})
                else:
                    results["queued"] += 1

                audit_svc.log(
                    db,
                    action="autonomous_followup_generated",
                    entity_type="follow_up",
                    entity_id=fu.id,
                    actor=actor,
                    details={"thread_id": thread.id, "creator_handle": creator.handle},
                )

            except Exception as e:
                results["errors"].append({"thread_id": thread.id, "error": str(e)})

    return results


async def start_autonomous_scheduler_loop(interval_hours: int = 24):
    """
    Background scheduler loop:
    Runs active autonomous batch outreach campaigns and 7-day follow-ups automatically.
    """
    global _SCHEDULER_RUNNING
    _SCHEDULER_RUNNING = True
    logger.info("Starting Autonomous Outreach Scheduler loop...")
    while _SCHEDULER_RUNNING:
        try:
            db = SessionLocal()
            try:
                active_camps = db.query(AutonomousCampaign).filter(AutonomousCampaign.status == "active").all()
                for camp in active_camps:
                    run_autonomous_batch(db, campaign_id=camp.id, actor="autonomous_scheduler")
                process_autonomous_followups(db, actor="autonomous_scheduler")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error in autonomous scheduler loop: {e}")

        await asyncio.sleep(interval_hours * 3600)


def stop_autonomous_scheduler_loop():
    global _SCHEDULER_RUNNING
    _SCHEDULER_RUNNING = False
    logger.info("Stopping Autonomous Outreach Scheduler loop...")

