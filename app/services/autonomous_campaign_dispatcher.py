# -*- coding: utf-8 -*-
"""
Autonomous Campaign Post Dispatcher Service
Enables zero-effort creator publishing:
- Automatically formats daily post kits (formatted caption, embedded visual preview, direct download links for high-res images and videos).
- Delivers post kits directly to creator/founder inboxes based on their campaign schedule day.
- Supports both autonomous cron dispatch and 1-click on-demand test delivery.
"""

import os
import re
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.config import settings
from app.models.project import CoLaunchProject, ValidationCampaign
from app.integrations.email_provider import EmailProvider

logger = logging.getLogger(__name__)


def format_daily_post_kit_email_html(
    creator_name: str,
    creator_handle: str,
    product_name: str,
    product_tagline: str,
    milestone_num: int,
    day_num: int,
    channel: str,
    title: str,
    description: str,
    caption_text: str,
    image_url: Optional[str] = None,
    video_url: Optional[str] = None,
    preorder_url: Optional[str] = None,
    recommended_time: Optional[str] = None
) -> str:
    """
    Renders an executive, ready-to-publish Daily Post Kit HTML email.
    Designed for 1-tap mobile/desktop copying and direct asset downloading.
    """
    c_name = creator_name or "Creator"
    handle = f"@{creator_handle.lstrip('@')}" if creator_handle else ""
    p_name = product_name or "Software Platform"
    ch = (channel or "Social Media").upper()
    rec_time = recommended_time or "12:00 AM (Midnight) in creator's local timezone"
    target_link = preorder_url or "https://creatorforge.app/preorder"

    # Clean caption for copy block
    clean_caption = (caption_text or description or "").strip()

    # Asset download buttons
    asset_buttons_html = ""
    asset_preview_html = ""

    if image_url:
        full_img_url = image_url
        if not full_img_url.startswith("http"):
            base_domain = getattr(settings, "BACKEND_URL", "https://creator-forge-backend.onrender.com")
            full_img_url = f"{base_domain.rstrip('/')}/{image_url.lstrip('/')}"

        asset_preview_html += f"""
        <div style="margin: 20px 0; text-align: center; background: #070a12; border: 1px solid #1e293b; border-radius: 12px; padding: 12px; overflow: hidden;">
          <p style="font-size: 11px; text-transform: uppercase; letter-spacing: 1px; color: #94a3b8; margin: 0 0 10px 0; font-family: monospace;">📸 Visual Post Graphic Preview</p>
          <img src="{full_img_url}" alt="Campaign Post Graphic" style="max-width: 100%; height: auto; border-radius: 8px; border: 1px solid #334155; display: inline-block;" />
        </div>
        """
        asset_buttons_html += f"""
        <a href="{full_img_url}" download="post_graphic_{day_num}.png" target="_blank" style="display: inline-block; background: #2563eb; color: #ffffff; text-decoration: none; padding: 12px 22px; font-weight: 700; font-size: 13px; border-radius: 8px; margin: 6px 4px; box-shadow: 0 2px 4px rgba(0,0,0,0.2);">
          📥 Download Image (PNG)
        </a>
        """

    if video_url:
        full_vid_url = video_url
        if not full_vid_url.startswith("http"):
            base_domain = getattr(settings, "BACKEND_URL", "https://creator-forge-backend.onrender.com")
            full_vid_url = f"{base_domain.rstrip('/')}/{video_url.lstrip('/')}"

        asset_buttons_html += f"""
        <a href="{full_vid_url}" download="campaign_video_day_{day_num}.mp4" target="_blank" style="display: inline-block; background: #059669; color: #ffffff; text-decoration: none; padding: 12px 22px; font-weight: 700; font-size: 13px; border-radius: 8px; margin: 6px 4px; box-shadow: 0 2px 4px rgba(0,0,0,0.2);">
          🎬 Download Video Teaser (MP4)
        </a>
        """

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Day {day_num} Post Kit: {title}</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0b0f19; color: #f1f5f9; margin: 0; padding: 24px 12px;">
  <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 600px; margin: 0 auto; background-color: #111827; border-radius: 16px; border: 1px solid #1f2937; overflow: hidden;">
    
    <!-- Top Header Banner -->
    <tr>
      <td style="padding: 24px 28px; background: linear-gradient(135deg, #1e1b4b 0%, #0f172a 100%); border-bottom: 1px solid #1f2937;">
        <table width="100%" border="0" cellspacing="0" cellpadding="0">
          <tr>
            <td>
              <span style="display: inline-block; background-color: #10b981; color: #ffffff; font-size: 10px; font-weight: 800; text-transform: uppercase; letter-spacing: 1px; padding: 4px 10px; border-radius: 20px; font-family: monospace;">
                🚀 DAY {day_num} POST KIT • MILESTONE {milestone_num}
              </span>
              <h1 style="color: #ffffff; font-size: 20px; font-weight: 800; margin: 10px 0 4px 0; line-height: 1.3;">
                {title}
              </h1>
              <p style="color: #94a3b8; font-size: 12px; margin: 0;">
                Co-Launch Venture: <strong style="color: #38bdf8;">{p_name}</strong> with {c_name} {handle}
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>

    <!-- Main Content -->
    <tr>
      <td style="padding: 24px 28px;">
        
        <!-- Quick Guidance Box -->
        <div style="background-color: #1e293b; border-radius: 10px; padding: 14px 18px; margin-bottom: 20px; border-left: 4px solid #38bdf8;">
          <table width="100%" border="0" cellspacing="0" cellpadding="0">
            <tr>
              <td style="font-size: 12px; color: #cbd5e1; line-height: 1.5;">
                <strong style="color: #ffffff;">Target Platform:</strong> {ch}<br>
                <strong style="color: #ffffff;">Recommended Post Time:</strong> {rec_time}<br>
                <strong style="color: #ffffff;">Action:</strong> Copy caption below, download attached visual asset, and publish!
              </td>
            </tr>
          </table>
        </div>

        <!-- Visual Asset Preview & Downloads -->
        {asset_preview_html}

        {f'<div style="text-align: center; margin: 16px 0;">{asset_buttons_html}</div>' if asset_buttons_html else ''}

        <!-- Ready to Copy Caption Block -->
        <div style="margin-top: 24px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <span style="font-size: 12px; font-weight: 700; color: #fde047; text-transform: uppercase; letter-spacing: 0.5px; font-family: monospace;">
              📋 READY-TO-PUBLISH CAPTION
            </span>
            <span style="font-size: 11px; color: #94a3b8;">(Tap & select all to copy)</span>
          </div>
          <div style="background-color: #070a12; border: 1px solid #334155; border-radius: 12px; padding: 18px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 14px; line-height: 1.6; color: #f1f5f9; white-space: pre-wrap; word-break: break-word; user-select: all;">
{clean_caption}
          </div>
        </div>

        <!-- Launch Link Reminder -->
        <div style="margin-top: 20px; padding: 12px 16px; background-color: #070a12; border: 1px solid #1e293b; border-radius: 10px; font-size: 12px; color: #94a3b8;">
          🔗 <strong style="color: #cbd5e1;">Your Pre-Order Page:</strong> <a href="{target_link}" style="color: #38bdf8; text-decoration: underline;" target="_blank">{target_link}</a>
        </div>

        <!-- 3-Step Simple Publishing Flow -->
        <div style="margin-top: 24px; padding-top: 20px; border-top: 1px solid #1f2937;">
          <p style="font-size: 11px; font-weight: 700; color: #94a3b8; text-transform: uppercase; margin: 0 0 10px 0; letter-spacing: 0.5px;">
            HOW TO POST IN 30 SECONDS:
          </p>
          <ol style="margin: 0; padding-left: 20px; font-size: 12px; color: #cbd5e1; line-height: 1.8;">
            <li>Copy the caption block above.</li>
            <li>Click download for the image or video on this email.</li>
            <li>Open {ch} on your phone or computer, paste the caption, attach the asset, and tap Post!</li>
          </ol>
        </div>

      </td>
    </tr>

    <!-- Footer -->
    <tr>
      <td style="padding: 20px 28px; background-color: #070a12; border-top: 1px solid #1f2937; text-align: center;">
        <p style="font-size: 11px; color: #64748b; margin: 0 0 6px 0;">
          Sent autonomously by <strong>Creator Forge Co-Launch Studio</strong> for {c_name} {handle}.
        </p>
        <p style="font-size: 10px; color: #475569; margin: 0;">
          Zero app logins required. Post kits are automatically delivered on your scheduled milestone days.
        </p>
      </td>
    </tr>

  </table>
</body>
</html>
"""


def dispatch_campaign_post_email(
    db: Session,
    project_id: str,
    task_id: Optional[str] = None,
    day: Optional[int] = None,
    recipient_email: Optional[str] = None,
    caller: Optional[str] = "admin"
) -> Dict[str, Any]:
    """
    Locates the scheduled post for the given project, constructs the daily post kit email,
    and dispatches it to the creator/founder's inbox.
    """
    proj = db.get(CoLaunchProject, project_id)
    if not proj:
        raise ValueError(f"Project '{project_id}' not found")

    campaign = proj.validation_campaign
    if not campaign or not campaign.campaign_kit:
        raise ValueError("Campaign Kit has not been generated for this project yet")

    kit = dict(campaign.campaign_kit)
    schedule: List[Dict[str, Any]] = list(kit.get("postingSchedule") or [])

    if not schedule:
        raise ValueError("No posting schedule found in campaign kit")

    # Select target task
    selected_task = None
    if task_id:
        for t in schedule:
            if str(t.get("id")) == str(task_id):
                selected_task = t
                break
    elif day is not None:
        for t in schedule:
            if t.get("day") == day:
                selected_task = t
                break

    if not selected_task:
        # Default to the active 'today' task or the first uncompleted task
        for t in schedule:
            if t.get("isToday") and not t.get("done"):
                selected_task = t
                break
        if not selected_task:
            for t in schedule:
                if not t.get("done"):
                    selected_task = t
                    break
        if not selected_task:
            selected_task = schedule[0]

    # Resolve recipient email address
    auto_config = kit.get("autonomousEmailDelivery") or {}
    target_email = (
        recipient_email
        or auto_config.get("recipientEmail")
        or getattr(proj, "creator_email", None)
        or getattr(proj, "email", None)
        or getattr(settings, "ADMIN_EMAIL", None)
        or getattr(settings, "GOOGLE_EMAIL", None)
    )

    if not target_email or "@" not in target_email:
        raise ValueError(
            "No valid recipient email address found. Please provide an email address or configure Autonomous Email Delivery."
        )

    target_email = target_email.strip()

    # Determine post copy based on channel
    channel = (selected_task.get("channel") or "Social Media").lower()
    task_title = selected_task.get("title") or "Campaign Post"
    task_desc = selected_task.get("description") or ""

    if "video" in channel or "youtube" in channel or "reel" in channel or "short" in channel:
        caption = kit.get("videoScript") or selected_task.get("draft") or task_desc
    elif "story" in channel:
        caption = kit.get("storySequence") or selected_task.get("draft") or task_desc
    elif "newsletter" in channel or "email" in channel:
        caption = kit.get("newsletterDraft") or selected_task.get("draft") or task_desc
    else:
        caption = kit.get("announcementPost") or selected_task.get("draft") or task_desc

    # Visual assets
    image_url = kit.get("cloudinaryImageUrl") or kit.get("postImageUrl")
    video_url = kit.get("cloudinaryVideoUrl") or kit.get("videoUrl")

    # Format HTML
    subject = f"🚀 [Day {selected_task.get('day', 1)} Post Kit] {task_title} • {proj.product_name}"
    tz_label = kit.get("creatorTimezone") or auto_config.get("timezone") or "local timezone"
    html_content = format_daily_post_kit_email_html(
        creator_name=proj.creator_name,
        creator_handle=proj.creator_handle,
        product_name=proj.product_name,
        product_tagline=proj.product_tagline,
        milestone_num=selected_task.get("milestoneNumber", selected_task.get("day", 1)),
        day_num=selected_task.get("day", 1),
        channel=selected_task.get("channel", "Social Media"),
        title=task_title,
        description=task_desc,
        caption_text=caption,
        image_url=image_url,
        video_url=video_url,
        preorder_url=f"https://creatorforge.app/preorder/{(proj.product_name or 'launch').lower().replace(' ', '-')}",
        recommended_time=f"12:00 AM (Midnight) · {tz_label}"
    )

    plain_text = f"""
[CREATOR FORGE DAILY POST KIT • DAY {selected_task.get('day', 1)}]
Venture: {proj.product_name}
Milestone: {task_title}
Channel: {selected_task.get('channel', 'Social Media')}

CAPTION TO COPY:
{caption}

ASSETS:
- Image: {image_url or 'None'}
- Video: {video_url or 'None'}

Pre-Order URL: https://creatorforge.app/preorder
"""

    # Dispatch email
    provider = EmailProvider()
    send_result = provider.send(
        to_email=target_email,
        subject=subject,
        body_html=html_content,
        body_text=plain_text,
        from_name=f"{proj.product_name} Launch Studio"
    )

    # Mark task as emailed
    selected_task["emailed"] = True
    selected_task["lastEmailedAt"] = datetime.utcnow().isoformat()
    selected_task["lastEmailedTo"] = target_email

    # Update database
    kit["postingSchedule"] = schedule
    campaign.campaign_kit = kit
    flag_modified(campaign, "campaign_kit")
    db.commit()

    logger.info(f"✅ Dispatched Day {selected_task.get('day')} Post Kit to {target_email} (MessageID: {send_result.get('message_id')})")

    return {
        "success": True,
        "recipient": target_email,
        "taskId": selected_task.get("id"),
        "day": selected_task.get("day"),
        "title": task_title,
        "channel": selected_task.get("channel"),
        "messageId": send_result.get("message_id"),
        "hasImage": bool(image_url),
        "hasVideo": bool(video_url),
        "message": f"Day {selected_task.get('day')} Post Kit successfully delivered to {target_email}!"
    }
