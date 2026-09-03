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
    delay_hours_override: Optional[int] = None,
) -> Dict:
    """
    Autonomous follow-up engine — runs on schedule.

    Sends follow-up emails for threads that:
      1. Are OPEN (no reply at all) and the delay window has passed.
      2. Have a NOT_INTERESTED reply — one polite re-engagement attempt is made.

    delay_hours_override: if set, overrides the campaign's followup_delay_days for testing.
                          When None, the campaign's followup_delay_days (default 7) is used.
    """
    from app.config import settings

    campaign_query = db.query(AutonomousCampaign)
    if campaign_id:
        campaign_query = campaign_query.filter(AutonomousCampaign.id == campaign_id)

    campaigns = campaign_query.filter(AutonomousCampaign.status == "active").all()
    if not campaigns:
        return {"processed": 0, "sent": 0, "message": "No active autonomous campaigns found"}

    # Resolve delay — use override (hours) or fall back to settings then campaign days
    effective_delay_hours = (
        delay_hours_override
        if delay_hours_override is not None
        else settings.FOLLOWUP_DELAY_HOURS
    )

    results = {"processed": 0, "sent": 0, "queued": 0, "skipped_already_sent": 0, "errors": []}

    for campaign in campaigns:
        # Convert to hours — honour override, else use campaign days setting
        if effective_delay_hours is not None:
            delay_h = effective_delay_hours
        else:
            delay_h = (campaign.followup_delay_days or 7) * 24

        cutoff = datetime.utcnow() - timedelta(hours=delay_h)

        logger.info(
            f"[FollowUp] Campaign={campaign.id} | delay={delay_h}h | cutoff={cutoff.isoformat()} | "
            f"checking open + not_interested threads"
        )

        # ── 1. Open threads (no reply at all) past the delay window ──────────────
        open_threads = (
            db.query(Thread)
            .join(OutreachMessage, Thread.outreach_message_id == OutreachMessage.id)
            .filter(
                OutreachMessage.campaign_id == campaign.id,
                Thread.status == "open",
                Thread.created_at <= cutoff,
            )
            .all()
        )

        # ── 2. Threads with a not_interested reply (one re-engagement attempt) ───
        not_interested_threads = (
            db.query(Thread)
            .join(OutreachMessage, Thread.outreach_message_id == OutreachMessage.id)
            .join(Reply, Reply.thread_id == Thread.id)
            .filter(
                OutreachMessage.campaign_id == campaign.id,
                Thread.status == "replied",
                Reply.classification == "not_interested",
            )
            .all()
        )

        eligible_threads = open_threads + not_interested_threads
        logger.info(
            f"[FollowUp] Campaign={campaign.id} | open={len(open_threads)} | "
            f"not_interested={len(not_interested_threads)} | total eligible={len(eligible_threads)}"
        )

        for thread in eligible_threads:
            # Skip if a non-skipped follow-up already exists for this thread
            existing_fu = db.query(FollowUp).filter(
                FollowUp.thread_id == thread.id,
                FollowUp.status != "skipped",
            ).first()
            if existing_fu:
                results["skipped_already_sent"] += 1
                continue

            creator = db.get(Creator, thread.creator_id)
            if not creator:
                continue

            # Determine if this is a re-engagement or a standard follow-up
            is_not_interested = thread.status == "replied"

            try:
                rec = db.query(ProductRecommendation).filter(
                    ProductRecommendation.creator_id == creator.id
                ).first()
                product_name = rec.product_name if rec else "Creator Academy"

                if is_not_interested:
                    # Softer re-engagement subject/body for not_interested threads
                    fu_subject = render_template(
                        campaign.followup_template_subject or "Re: {{display_name}} — one last thought",
                        creator, product_name
                    )
                    re_engage_body = (
                        campaign.followup_template_body
                        + "\n\nP.S. Completely understand if this isn't for you — just wanted to share "
                        "one last thought before closing off. No pressure at all."
                    )
                    fu_body = render_template(re_engage_body, creator, product_name)
                else:
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

                # Resolve contact email
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
                        logger.info(
                            f"[FollowUp] Sent follow-up to @{creator.handle} <{contact.value}> "
                            f"({'re-engage' if is_not_interested else 'no-reply'})"
                        )
                    except Exception as fu_err:
                        logger.error(f"[FollowUp] Send error for @{creator.handle}: {fu_err}")
                        results["errors"].append({"thread_id": thread.id, "error": f"Send error: {fu_err}"})
                else:
                    results["queued"] += 1

                audit_svc.log(
                    db,
                    action="autonomous_followup_generated",
                    entity_type="follow_up",
                    entity_id=fu.id,
                    actor=actor,
                    details={
                        "thread_id": thread.id,
                        "creator_handle": creator.handle,
                        "followup_type": "re_engage" if is_not_interested else "no_reply",
                        "delay_hours": delay_h,
                    },
                )

            except Exception as e:
                logger.error(f"[FollowUp] Error processing thread {thread.id}: {e}")
                results["errors"].append({"thread_id": thread.id, "error": str(e)})

    logger.info(f"[FollowUp] Run complete: {results}")
    return results


# ── Dedicated Follow-up Scheduler Loop ───────────────────────────────────────

_FOLLOWUP_SCHEDULER_RUNNING = False


async def start_followup_scheduler_loop():
    """
    Dedicated background loop for autonomous follow-ups.

    Interval and delay are read from settings on every tick so you can change
    them in .env and restart without touching code:

      FOLLOWUP_CHECK_INTERVAL_HOURS=1   # how often this loop fires (testing: 1h)
      FOLLOWUP_DELAY_HOURS=1            # min hours after outreach before follow-up fires
                                         # Production: set to 168 (7 days)
    """
    global _FOLLOWUP_SCHEDULER_RUNNING
    _FOLLOWUP_SCHEDULER_RUNNING = True
    from app.config import settings

    logger.info(
        f"[FollowUp Scheduler] Started — "
        f"check every {settings.FOLLOWUP_CHECK_INTERVAL_HOURS}h, "
        f"delay {settings.FOLLOWUP_DELAY_HOURS}h before follow-up fires"
    )

    await asyncio.sleep(10)  # Let server complete startup and bind to port
    while _FOLLOWUP_SCHEDULER_RUNNING:
        try:
            db = SessionLocal()
            try:
                result = process_autonomous_followups(
                    db,
                    actor="followup_scheduler",
                    delay_hours_override=settings.FOLLOWUP_DELAY_HOURS,
                )
                logger.info(f"[FollowUp Scheduler] Tick complete: {result}")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"[FollowUp Scheduler] Unhandled error: {e}")

        await asyncio.sleep(settings.FOLLOWUP_CHECK_INTERVAL_HOURS * 3600)


def stop_followup_scheduler_loop():
    global _FOLLOWUP_SCHEDULER_RUNNING
    _FOLLOWUP_SCHEDULER_RUNNING = False
    logger.info("[FollowUp Scheduler] Stopped.")


# ── Main Outreach Scheduler Loop (batch sending) ─────────────────────────────

async def start_autonomous_scheduler_loop(interval_hours: int = 24):
    """
    Background scheduler loop for autonomous batch OUTREACH (new emails).
    Follow-ups are handled separately by start_followup_scheduler_loop.
    """
    global _SCHEDULER_RUNNING
    _SCHEDULER_RUNNING = True
    logger.info("[Outreach Scheduler] Started — batch outreach loop running...")
    await asyncio.sleep(15)  # Let server complete startup and bind to port
    while _SCHEDULER_RUNNING:
        try:
            db = SessionLocal()
            try:
                active_camps = db.query(AutonomousCampaign).filter(AutonomousCampaign.status == "active").all()
                for camp in active_camps:
                    run_autonomous_batch(db, campaign_id=camp.id, actor="autonomous_scheduler")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"[Outreach Scheduler] Error: {e}")

        await asyncio.sleep(interval_hours * 3600)


def stop_autonomous_scheduler_loop():
    global _SCHEDULER_RUNNING
    _SCHEDULER_RUNNING = False
    logger.info("[Outreach Scheduler] Stopped.")
