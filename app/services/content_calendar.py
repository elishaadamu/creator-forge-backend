import json
import re
from datetime import datetime, timedelta
from typing import Optional, List

from sqlalchemy.orm import Session

from app.config import settings
from app.models.creator import Creator, ProductRecommendation, PostSuggestion
from app.services import audit as audit_svc


def _build_calendar_prompt(creator: Creator, rec: ProductRecommendation) -> str:
    return f"""You are a social media growth strategist helping a creator launch their new product.

Creator Profile:
- Name: {creator.display_name} (@{creator.handle}) on {creator.platform}
- Niche: {', '.join(creator.niche or []) or 'unknown'}
- Followers: {creator.follower_count:,}
- Bio: {creator.bio or 'N/A'}

Product Launching:
- Product Name: {rec.product_name}
- Product Category: {rec.product_category}
- Tagline: {rec.tagline}
- Description: {rec.description}
- Target Audience: {rec.target_audience}

Generate a 7-day content launch calendar to promote this product. The calendar should have exactly 5 high-impact post suggestions tailored to their platform and audience.
Each suggestion must include:
1. platform: the channel (e.g. tiktok, youtube, instagram, twitter, linkedin)
2. hook: a viral click-worthy hook or title (less than 15 words)
3. body: the script (for video) or caption text (for posts) explaining the concept, highlighting value, and ending with a Call-to-Action to check out the product.
4. scheduled_days_offset: how many days from now to post this (integer 1 to 7)

Return a JSON array with exactly 5 objects:
[
  {{
    "platform": "<tiktok|youtube|instagram|twitter|linkedin>",
    "hook": "<viral hook>",
    "body": "<script/caption with \\n for line breaks>",
    "scheduled_days_offset": <int 1-7>
  }}
]

Return ONLY valid JSON. No conversational filler, no markdown block wrappers."""


def generate_calendar(
    db: Session,
    creator_id: str,
    product_rec_id: str,
    actor: str = "system",
) -> List[PostSuggestion]:
    creator = db.get(Creator, creator_id)
    rec = db.get(ProductRecommendation, product_rec_id)
    if not creator or not rec:
        raise ValueError("Creator or ProductRecommendation not found")

    prompt = _build_calendar_prompt(creator, rec)
    raw = None

    if settings.ANTHROPIC_API_KEY:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
            message = client.messages.create(
                model=settings.AI_MODEL,
                max_tokens=2500,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text.strip()
        except Exception as e:
            print(f"Anthropic calendar generation failed: {e}")
            raw = None

    if not raw and settings.GEMINI_API_KEY:
        try:
            from google import genai
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
            )
            raw = response.text.strip()
        except Exception as e:
            print(f"Gemini calendar generation failed: {e}")
            raw = None

    # Parse JSON list
    items = []
    if raw:
        try:
            items = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if match:
                try:
                    items = json.loads(match.group())
                except json.JSONDecodeError:
                    pass

    # If parsing failed or empty, provide static fallback calendar
    if not items:
        items = [
            {
                "platform": creator.platform or "youtube",
                "hook": f"Why I'm launching {rec.product_name} today",
                "body": f"Hey guys, today is a massive day. I'm finally launching {rec.product_name} — {rec.tagline}.\n\nThis is designed specifically to help you guys with the issues we talk about all the time in the comments. Go click the link in bio to check it out!",
                "scheduled_days_offset": 1
            },
            {
                "platform": "tiktok" if creator.platform != "tiktok" else "instagram",
                "hook": "The biggest mistake I see people make in my space",
                "body": f"We constantly see this problem, and it's why I built {rec.product_name}. Check out how it works and how you can save hours of time today.",
                "scheduled_days_offset": 3
            }
        ]

    suggestions = []
    now_time = datetime.utcnow()
    for item in items:
        offset = int(item.get("scheduled_days_offset", 1))
        scheduled_for = now_time + timedelta(days=offset)
        
        sug = PostSuggestion(
            creator_id=creator_id,
            product_recommendation_id=product_rec_id,
            hook=item.get("hook", "Untitled Suggestion"),
            body=item.get("body", ""),
            platform=item.get("platform", "youtube"),
            status="draft",
            scheduled_for=scheduled_for
        )
        db.add(sug)
        suggestions.append(sug)

    db.commit()
    for s in suggestions:
        db.refresh(s)

    audit_svc.log(
        db, action="calendar_generated", entity_type="creator",
        entity_id=creator_id, actor=actor,
        details={"post_count": len(suggestions), "product_id": product_rec_id},
    )
    return suggestions
