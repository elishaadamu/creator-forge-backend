# -*- coding: utf-8 -*-
"""
Campaign AI Media Generator Service
Exclusively powered by OpenAI with Creator Channel & Social Post Alignment:
- Image Generation: OpenAI Image Models (gpt-image-1, gpt-image-1-mini, chatgpt-image-latest, dall-e-3)
  with tailored channel niche aesthetics, authentic social copy integration, and creator branding.
- Video Generation: OpenAI Video Models (sora-2, sora-2-pro) with graceful fallback to
  high-impact cinematic MP4 teaser video compilation (imageio/H.264) when Sora endpoint is restricted (404).
"""

import os
import time
import base64
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from app.config import settings

logger = logging.getLogger(__name__)

# Ensure media directory exists
BASE_STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"
GENERATED_MEDIA_DIR = BASE_STATIC_DIR / "generated"
GENERATED_MEDIA_DIR.mkdir(parents=True, exist_ok=True)


def _get_live_env_openai_key() -> str:
    key = os.getenv("OPENAI_API_KEY") or getattr(settings, "OPENAI_API_KEY", "")
    if key and not (key.endswith("WOYA") or key.endswith("jwwA")):
        return key.strip().strip('"\'')
    # Read dynamically from .env
    env_file = BASE_STATIC_DIR.parent / ".env"
    if env_file.exists():
        try:
            for line in env_file.read_text(encoding="utf-8-sig").splitlines():
                line = line.strip()
                if line.startswith("OPENAI_API_KEY="):
                    val = line.split("=", 1)[1].strip().strip('"\'')
                    if val and not (val.endswith("WOYA") or val.endswith("jwwA")):
                        return val
        except Exception:
            pass
    return ""


def _get_openai_client(api_key: Optional[str] = None):
    from openai import OpenAI
    candidate = (api_key or "").strip().strip('"\'')
    if candidate and not (candidate.endswith("WOYA") or candidate.endswith("jwwA")):
        resolved_key = candidate
    else:
        resolved_key = _get_live_env_openai_key()

    if not resolved_key:
        raise ValueError("No valid OpenAI API key found in request or backend/.env (OPENAI_API_KEY)")
    return OpenAI(api_key=resolved_key)


def build_creator_channel_image_prompt(
    creator_name: str,
    creator_handle: str,
    niche: str,
    product_name: str,
    product_tagline: str,
    target_audience: str,
    announcement_post: str,
    user_prompt: Optional[str] = None
) -> str:
    """
    Constructs an authentic, high-converting social media announcement graphic prompt
    that strictly respects the creator's channel theme, niche aesthetic, audience, and the actual social post copy.
    """
    post_snippet = (announcement_post or "").strip()
    post_context = ""
    if post_snippet:
        lines = [l.strip() for l in post_snippet.split("\n") if l.strip() and not l.startswith("http")]
        key_snippet = " ".join(lines[:3])[:220]
        if key_snippet:
            post_context = f"The official social announcement hook is: \"{key_snippet}\"."

    niche_lower = (niche or "Tech").lower()
    if any(k in niche_lower for k in ["code", "developer", "software", "tech", "saas", "ai", "hardware", "engineering"]):
        channel_style = "Sleek dark-mode developer & tech aesthetic with elegant terminal accents, glowing glassmorphic IDE/dashboard UI card, neon cyan and emerald indicators, futuristic minimalism, and authentic workstation studio lighting."
    elif any(k in niche_lower for k in ["design", "art", "creative", "video", "photo", "film", "motion"]):
        channel_style = "High-aesthetic creator studio design with Swiss typography hierarchy, cinematic lens flares, premium monochrome contrast, subtle color gradients, and museum-grade visual layout."
    elif any(k in niche_lower for k in ["business", "finance", "money", "invest", "wealth", "crypto", "growth", "marketing"]):
        channel_style = "Modern executive fintech aesthetic with bold analytical charts, clean metrics HUD, dark sapphire and gold accents, and authoritative creator brand elevation."
    elif any(k in niche_lower for k in ["fitness", "health", "wellness", "biohack", "sport", "physique"]):
        channel_style = "High-energy athletic performance aesthetic with high-contrast dramatic studio lighting, biometric telemetry charts, bold modern typography, and clean vitality accents."
    elif any(k in niche_lower for k in ["gaming", "streamer", "esports", "entertainment"]):
        channel_style = "Vibrant immersive creator studio aesthetic with ambient RGB room glows, sleek holographic product HUD badge, and high-impact streamer brand styling."
    else:
        channel_style = "Modern creator studio aesthetic with clean typography, premium glassmorphic UI card, vibrant brand lighting, and sleek commercial showcase styling."

    c_name = creator_name or "Creator"
    handle = f" (@{creator_handle.lstrip('@')})" if creator_handle else ""
    p_name = product_name or "Exclusive Tool OS"
    tagline = f" — {product_tagline}" if product_tagline else ""
    audience = f" tailored for an audience of {target_audience}" if target_audience else ""

    parts = [
        f"A professional, visually arresting social media announcement post graphic designed specifically for the official channel of {c_name}{handle} in the {niche} space.",
        f"Announcing their co-founded software venture: '{p_name}'{tagline}{audience}.",
        f"Channel Aesthetic: {channel_style}",
    ]

    if post_context:
        parts.append(f"Post Context: {post_context}")

    if user_prompt and user_prompt.strip() and not user_prompt.startswith("Announcement graphic for:"):
        parts.append(f"Specific creator notes: {user_prompt.strip()}")

    parts.append(
        "Visual Layout: Centered around a premium 3D floating product dashboard showcase card with sleek UI elements, illuminated badge signifying 'Official Co-Launch' and 'Founding Cohort Access', and subtle creator channel visual motifs. 4K resolution, photo-realistic studio lighting, ultra-sharp detail, crisp modern graphic design for Twitter/X and LinkedIn. No distorted text, no random watermarks, high commercial quality."
    )

    return " ".join(parts)


def build_creator_channel_video_prompt(
    creator_name: str,
    creator_handle: str,
    niche: str,
    product_name: str,
    product_tagline: str,
    video_script: str,
    user_prompt: Optional[str] = None
) -> str:
    """
    Constructs a cinematic launch video teaser prompt aligned with the creator's channel and script.
    """
    script_snippet = (video_script or "").strip()[:180]
    c_name = creator_name or "Creator"
    p_name = product_name or "Software Venture"
    niche_name = niche or "Tech"

    prompt_parts = [
        f"A dynamic, cinematic 60-second video teaser announcing {p_name} co-founded with creator {c_name} in the {niche_name} space.",
        f"Channel Theme: High-tech creator studio lighting, futuristic screen interfaces, dramatic camera dolly zoom, ultra-sharp commercial quality."
    ]
    if script_snippet:
        prompt_parts.append(f"Script theme: {script_snippet}")
    if user_prompt and user_prompt.strip():
        prompt_parts.append(f"Additional direction: {user_prompt.strip()}")

    return " ".join(prompt_parts)


def _create_cinematic_mp4_teaser(
    creator_name: Optional[str] = None,
    creator_handle: Optional[str] = None,
    product_name: Optional[str] = None,
    niche: Optional[str] = None,
    base_image_url: Optional[str] = None,
    duration_sec: int = 5,
    fps: int = 24
) -> bytes:
    """
    Compiles a real, high-impact cinematic MP4 launch teaser video using imageio and PIL.
    Animates the creator post graphic or branded canvas with smooth Ken Burns zoom,
    studio ambient glow, and crisp launch title card overlays.
    """
    import numpy as np
    from PIL import Image, ImageDraw
    import imageio.v3 as iio

    w, h = 640, 368  # 16:9 divisible by 16 for optimal H.264 encoding
    n_frames = fps * duration_sec
    c_name = creator_name or "Official Creator"
    handle = f"@{creator_handle.lstrip('@')}" if creator_handle else ""
    p_name = product_name or "New Venture OS"
    n_tag = (niche or "Tech Architecture").upper()

    base_img = None
    if base_image_url:
        try:
            rel = base_image_url.replace("/static/", "").lstrip("/")
            local_path = BASE_STATIC_DIR / rel
            if local_path.exists():
                loaded = Image.open(local_path).convert("RGB")
                base_img = loaded.resize((w, h), Image.Resampling.BILINEAR)
        except Exception as e_img:
            logger.warning(f"Could not load base image for teaser video: {e_img}")

    if not base_img:
        base_img = Image.new("RGB", (w, h), color=(10, 16, 28))
        d_base = ImageDraw.Draw(base_img)
        for r in range(160, 0, -10):
            d_base.ellipse(
                [(w // 2 - r, h // 2 - r), (w // 2 + r, h // 2 + r)],
                fill=(12 + r // 4, 18 + r // 3, 40 + r // 2)
            )

    frames = []
    for f in range(n_frames):
        t = f / float(n_frames)
        # Smooth cinematic scale 1.0 -> 1.05
        scale = 1.0 + 0.05 * t
        nw, nh = int(w * scale), int(h * scale)
        scaled = base_img.resize((nw, nh), Image.Resampling.BILINEAR)
        left = (nw - w) // 2
        top = (nh - h) // 2
        frame = scaled.crop((left, top, left + w, top + h))

        d = ImageDraw.Draw(frame, "RGBA")
        # Top gradient banner
        d.rectangle([(0, 0), (w, 46)], fill=(5, 8, 18, 210))
        # Bottom gradient banner
        d.rectangle([(0, h - 68), (w, h)], fill=(3, 6, 15, 230))

        # Accent border lines
        d.line([(0, 46), (w, 46)], fill=(245, 158, 11, 160), width=1)
        d.line([(0, h - 68), (w, h - 68)], fill=(56, 189, 248, 160), width=1)

        # Text overlays
        d.text((16, 14), f"OFFICIAL CO-LAUNCH • {n_tag}", fill=(245, 158, 11, 255))
        d.text((16, h - 56), p_name, fill=(255, 255, 255, 255))
        d.text((16, h - 34), f"{c_name} {handle} — Founding Cohort Access Open", fill=(203, 213, 225, 240))

        frames.append(np.array(frame))

    temp_filename = f"temp_teaser_{int(time.time())}_{os.urandom(4).hex()}.mp4"
    temp_path = GENERATED_MEDIA_DIR / temp_filename
    iio.imwrite(temp_path, frames, fps=fps)
    data = temp_path.read_bytes()
    try:
        temp_path.unlink(missing_ok=True)
    except Exception:
        pass
    return data


def generate_campaign_social_image(
    prompt: str,
    api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    creator_name: Optional[str] = None,
    creator_handle: Optional[str] = None,
    creator_id: Optional[str] = None,
    niche: Optional[str] = None,
    product_name: Optional[str] = None,
    project_id: Optional[str] = None,
    generated_by: Optional[str] = "admin",
) -> Dict[str, Any]:
    """
    Generates high-impact AI campaign graphic using OpenAI Image API.
    Saves image to Cloudinary partitioned strictly under the creator's profile
    (folder: creator_forge/creators/{creator_slug}/campaigns) with local disk caching fallback.
    """
    import re
    resolved_key = openai_api_key or api_key
    oai_client = _get_openai_client(resolved_key)

    logger.info(f"🎨 [IMAGE GEN] Requesting image with prompt: {prompt[:120]}...")

    candidate_models = [
        "gpt-image-1",
        "gpt-image-1-mini",
        "chatgpt-image-latest",
        "dall-e-3",
        "dall-e-2",
    ]

    image_bytes = None
    model_used = None
    last_error = None

    import httpx

    for m in candidate_models:
        try:
            logger.info(f"🎨 Trying image model: {m}...")
            res = oai_client.images.generate(
                model=m,
                prompt=prompt,
                n=1,
            )
            if res.data and getattr(res.data[0], "b64_json", None):
                image_bytes = base64.b64decode(res.data[0].b64_json)
                model_used = m
                break
            elif res.data and getattr(res.data[0], "url", None):
                img_resp = httpx.get(res.data[0].url, timeout=30.0)
                img_resp.raise_for_status()
                image_bytes = img_resp.content
                model_used = m
                break
        except Exception as err:
            last_error = err
            logger.warning(f"⚠️ Model {m} generation failed: {err}. Trying next candidate...")
            continue

    if not image_bytes:
        raise RuntimeError(f"Image generation failed: {last_error}")

    filename = f"campaign_post_{int(time.time())}_{os.urandom(4).hex()}.png"
    filepath = GENERATED_MEDIA_DIR / filename

    with open(filepath, "wb") as f:
        f.write(image_bytes)

    b64_data = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:image/png;base64,{b64_data}"

    logger.info(f"✅ Generated campaign image saved locally to {filepath}")

    # Build creator-profile partitioned Cloudinary folder and public ID
    clean_handle = (creator_handle or "").replace("@", "").strip()
    creator_identifier = clean_handle or (creator_name or "").strip().replace(" ", "_") or (creator_id or "creator")
    creator_slug = re.sub(r'[^a-zA-Z0-9_-]', '_', creator_identifier).strip('_').lower() or "creator"
    clean_product = re.sub(r'[^a-zA-Z0-9_-]', '_', (product_name or "launch")).strip('_').lower() or "launch"
    timestamp = int(time.time())

    # Specific folder based on creator's profile, not generic
    cld_folder = f"creator_forge/creators/{creator_slug}/campaigns"
    cld_public_id = f"{creator_slug}_{clean_product}_post_{timestamp}"

    tags = [
        f"creator:{creator_slug}",
        "campaign_announcement_graphic",
        f"project:{project_id or 'general'}",
        f"generator:{generated_by or 'admin'}"
    ]
    if niche:
        tags.append(f"niche:{re.sub(r'[^a-zA-Z0-9_-]', '_', niche).lower()}")

    context = {
        "creator_name": creator_name or "Creator",
        "creator_handle": creator_handle or "",
        "creator_id": creator_id or "",
        "product_name": product_name or "Launch Venture",
        "project_id": project_id or "",
        "generated_by": generated_by or "admin"
    }

    final_url = f"/static/generated/{filename}"
    is_cloudinary = False
    cld_public_id_saved = None
    optimize_url = None
    thumbnail_url = None

    try:
        from app.integrations.cloudinary_service import upload_media_to_cloudinary
        cld_res = upload_media_to_cloudinary(
            file_data=str(filepath),
            public_id=cld_public_id,
            folder=cld_folder,
            resource_type="image",
            tags=tags,
            context=context
        )
        if cld_res.get("success") and cld_res.get("secure_url"):
            final_url = cld_res.get("secure_url")
            is_cloudinary = True
            cld_public_id_saved = cld_res.get("public_id")
            optimize_url = cld_res.get("optimize_url")
            thumbnail_url = cld_res.get("thumbnail_url")
            logger.info(f"☁️ Successfully uploaded campaign image to Cloudinary under creator folder '{cld_folder}': {final_url}")
        else:
            logger.warning(f"⚠️ Cloudinary upload returned error: {cld_res.get('error')}. Using local delivery.")
    except Exception as cld_err:
        logger.warning(f"⚠️ Cloudinary upload exception: {cld_err}. Using local delivery.")

    return {
        "url": final_url,
        "secure_url": final_url,
        "cloudinary_url": final_url if is_cloudinary else None,
        "cloudinary_public_id": cld_public_id_saved,
        "optimize_url": optimize_url or final_url,
        "thumbnail_url": thumbnail_url or final_url,
        "creator_folder": cld_folder,
        "creator_slug": creator_slug,
        "is_cloudinary": is_cloudinary,
        "filename": filename,
        "data_url": data_url,
        "prompt": prompt,
        "model": "announcement-graphic",
        "provider": "ai"
    }


def generate_campaign_video(
    prompt: str,
    api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    creator_name: Optional[str] = None,
    creator_handle: Optional[str] = None,
    product_name: Optional[str] = None,
    niche: Optional[str] = None,
    post_image_url: Optional[str] = None,
    max_wait_seconds: int = 360
) -> Dict[str, Any]:
    """
    Generates video teaser/ad using OpenAI Video (Sora) API.
    If OpenAI Video endpoint is unavailable/restricted (HTTP 404),
    gracefully compiles a high-fidelity cinematic MP4 campaign video teaser.
    """
    resolved_key = openai_api_key or api_key
    oai_client = _get_openai_client(resolved_key)

    logger.info(f"🎬 [OPENAI VIDEO GEN] Initiating video generation with prompt: {prompt[:120]}...")

    candidate_models = ["sora-2", "sora-2-pro", None]
    video_bytes = None
    model_used = "sora-2"
    sora_attempted = False

    if hasattr(oai_client, "videos") and callable(getattr(oai_client.videos, "create_and_poll", None)):
        for vm in candidate_models:
            try:
                sora_attempted = True
                logger.info(f"🎬 Trying OpenAI video model: {vm or 'default'}...")
                kwargs = {"prompt": prompt, "seconds": 8}
                if vm:
                    kwargs["model"] = vm
                video_op = oai_client.videos.create_and_poll(**kwargs)
                content = oai_client.videos.download_content(video_op.id)
                raw = content.read() if hasattr(content, "read") else content
                if raw:
                    video_bytes = raw
                    model_used = vm or "sora-2"
                    break
            except Exception as v_err:
                logger.warning(f"⚠️ OpenAI video model {vm} attempt: {v_err}")
                continue

    # Graceful fallback: If Sora is restricted (404) or failed, compile genuine cinematic MP4 teaser
    if not video_bytes:
        logger.info("🎬 Rendering cinematic MP4 campaign video teaser (Ken Burns studio zoom & brand overlays)...")
        video_bytes = _create_cinematic_mp4_teaser(
            creator_name=creator_name,
            creator_handle=creator_handle,
            product_name=product_name,
            niche=niche,
            base_image_url=post_image_url,
            duration_sec=5,
            fps=24
        )
        model_used = "launch-teaser"

    filename = f"campaign_video_{int(time.time())}_{os.urandom(4).hex()}.mp4"
    filepath = GENERATED_MEDIA_DIR / filename

    with open(filepath, "wb") as f:
        f.write(video_bytes)

    logger.info(f"✅ Generated campaign video saved locally to {filepath}")

    # Build creator-specific folder for video
    clean_handle = (creator_handle or "").replace("@", "").strip()
    creator_identifier = clean_handle or (creator_name or "").strip().replace(" ", "_") or "creator"
    creator_slug = re.sub(r'[^a-zA-Z0-9_-]', '_', creator_identifier).strip('_').lower() or "creator"
    clean_product = re.sub(r'[^a-zA-Z0-9_-]', '_', (product_name or "launch")).strip('_').lower() or "launch"
    cld_folder = f"creator_forge/creators/{creator_slug}/campaigns"
    cld_video_id = f"{creator_slug}_{clean_product}_video_{int(time.time())}"

    final_video_url = f"/static/generated/{filename}"
    is_cloudinary = False
    cld_public_id_saved = None

    try:
        from app.integrations.cloudinary_service import upload_media_to_cloudinary
        cld_res = upload_media_to_cloudinary(
            file_data=str(filepath),
            public_id=cld_video_id,
            folder=cld_folder,
            resource_type="video",
            tags=[f"creator:{creator_slug}", "campaign_teaser_video"]
        )
        if cld_res.get("success") and cld_res.get("secure_url"):
            final_video_url = cld_res.get("secure_url")
            is_cloudinary = True
            cld_public_id_saved = cld_res.get("public_id")
            logger.info(f"☁️ Successfully uploaded campaign video to Cloudinary under creator folder '{cld_folder}': {final_video_url}")
    except Exception as cld_err:
        logger.warning(f"⚠️ Cloudinary video upload skipped/failed: {cld_err}")

    return {
        "url": final_video_url,
        "secure_url": final_video_url,
        "cloudinary_url": final_video_url if is_cloudinary else None,
        "cloudinary_public_id": cld_public_id_saved,
        "creator_folder": cld_folder,
        "creator_slug": creator_slug,
        "is_cloudinary": is_cloudinary,
        "filename": filename,
        "prompt": prompt,
        "model": model_used,
        "provider": "ai"
    }
