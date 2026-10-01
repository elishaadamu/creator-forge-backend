# -*- coding: utf-8 -*-
"""
Campaign AI Media Generator Service
Exclusively powered by OpenAI:
- Image Generation: OpenAI Image Models (gpt-image-1, gpt-image-1-mini, chatgpt-image-latest, dall-e-3)
- Video Generation: OpenAI Video Models (sora-2, sora-2-pro)
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


def generate_campaign_social_image(
    prompt: str,
    api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generates high-impact AI campaign graphic using OpenAI Image API.
    Tries active OpenAI image models in order: gpt-image-1, gpt-image-1-mini, chatgpt-image-latest, dall-e-3.
    """
    resolved_key = openai_api_key or api_key
    oai_client = _get_openai_client(resolved_key)

    logger.info(f"🎨 [OPENAI IMAGE GEN] Requesting image with prompt: {prompt[:120]}...")

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
            logger.info(f"🎨 Trying OpenAI model: {m}...")
            # For gpt-image and chatgpt-image models, call images.generate
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
        raise RuntimeError(f"OpenAI image generation failed across available models: {last_error}")

    filename = f"campaign_post_{int(time.time())}_{os.urandom(4).hex()}.png"
    filepath = GENERATED_MEDIA_DIR / filename

    with open(filepath, "wb") as f:
        f.write(image_bytes)

    b64_data = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:image/png;base64,{b64_data}"

    logger.info(f"✅ Generated campaign image saved to {filepath} using OpenAI ({model_used})")

    return {
        "url": f"/static/generated/{filename}",
        "filename": filename,
        "data_url": data_url,
        "prompt": prompt,
        "model": model_used,
        "provider": "openai"
    }


def generate_campaign_video(
    prompt: str,
    api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    max_wait_seconds: int = 360
) -> Dict[str, Any]:
    """
    Generates video teaser/ad using OpenAI Video (Sora) API.
    Tries sora-2, sora-2-pro, or default model.
    """
    resolved_key = openai_api_key or api_key
    oai_client = _get_openai_client(resolved_key)

    logger.info(f"🎬 [OPENAI VIDEO GEN] Initiating OpenAI video generation with prompt: {prompt[:120]}...")

    if not hasattr(oai_client, "videos") or not callable(getattr(oai_client.videos, "create_and_poll", None)):
        raise RuntimeError("OpenAI client does not expose video generation methods on this version")

    candidate_models = ["sora-2", "sora-2-pro", None]
    video_bytes = None
    model_used = "sora-2"
    last_error = None

    for vm in candidate_models:
        try:
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
            last_error = v_err
            logger.warning(f"⚠️ OpenAI video model {vm} failed: {v_err}. Trying next...")
            continue

    if not video_bytes:
        raise RuntimeError(f"OpenAI video generation failed: {last_error}")

    filename = f"campaign_video_{int(time.time())}_{os.urandom(4).hex()}.mp4"
    filepath = GENERATED_MEDIA_DIR / filename

    with open(filepath, "wb") as f:
        f.write(video_bytes)

    logger.info(f"✅ Generated OpenAI video saved to {filepath} using {model_used}")

    return {
        "url": f"/static/generated/{filename}",
        "filename": filename,
        "prompt": prompt,
        "model": model_used,
        "provider": "openai"
    }
