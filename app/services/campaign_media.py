# -*- coding: utf-8 -*-
"""
Campaign AI Media Generator Service
Integrates:
- Primary: Google GenAI SDK (gemini-3.1-flash-image & veo-3.1-generate-preview)
- Fallback: OpenAI API (DALL-E 3 for image & OpenAI Videos for video)
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

DEFAULT_OPENAI_KEY = (
    os.getenv("OPENAI_API_KEY")
    or getattr(settings, "OPENAI_API_KEY", "")
)


def _get_genai_client(api_key: Optional[str] = None):
    from google import genai
    resolved_key = (
        api_key
        or getattr(settings, "GEMINI_API_KEY", None)
        or os.getenv("GEMINI_API_KEY", "")
    )
    if resolved_key:
        return genai.Client(api_key=resolved_key)
    return genai.Client()


def _get_openai_client(api_key: Optional[str] = None):
    from openai import OpenAI
    resolved_key = api_key or DEFAULT_OPENAI_KEY
    if not resolved_key:
        raise ValueError("No OpenAI API key provided or configured in environment")
    return OpenAI(api_key=resolved_key)


def generate_campaign_social_image(
    prompt: str,
    api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generates high-impact AI campaign graphic.
    1. Attempts Gemini (gemini-3.1-flash-image, fallback imagen-3.0-generate-002)
    2. If Gemini fails, automatically falls back to OpenAI DALL-E 3
    """
    image_bytes = None
    model_used = "gemini-3.1-flash-image"
    provider_used = "google"
    gemini_error = None

    logger.info(f"🎨 [AI IMAGE GEN] Requesting primary Gemini with prompt: {prompt[:120]}...")

    # Step 1: Attempt Gemini
    try:
        client = _get_genai_client(api_key)
        try:
            interaction = client.interactions.create(
                model="gemini-3.1-flash-image",
                input=prompt,
            )
            if hasattr(interaction, "output_image") and getattr(interaction.output_image, "data", None):
                image_bytes = base64.b64decode(interaction.output_image.data)
            elif hasattr(interaction, "output") and getattr(interaction.output, "data", None):
                image_bytes = base64.b64decode(interaction.output.data)
        except Exception as e_interact:
            logger.warning(f"⚠️ interactions.create(gemini-3.1-flash-image) warning: {e_interact}. Trying imagen fallback...")
            res = client.models.generate_images(
                model="imagen-3.0-generate-002",
                prompt=prompt,
            )
            if res.generated_images:
                image_bytes = res.generated_images[0].image.image_bytes
                model_used = "imagen-3.0-generate-002"
    except Exception as g_err:
        gemini_error = str(g_err)
        logger.warning(f"⚠️ Gemini image generation failed ({gemini_error}). Falling back to OpenAI DALL-E 3...")

    # Step 2: Fallback to OpenAI DALL-E 3 if Gemini failed
    if not image_bytes:
        try:
            oai_client = _get_openai_client(openai_api_key)
            logger.info("🎨 [AI IMAGE GEN] Generating image via OpenAI DALL-E 3 fallback...")
            # DALL-E 3 supports high quality prompts
            oai_res = oai_client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size="1024x1024",
                quality="standard",
                response_format="b64_json",
                n=1,
            )
            if oai_res.data and getattr(oai_res.data[0], "b64_json", None):
                image_bytes = base64.b64decode(oai_res.data[0].b64_json)
                model_used = "dall-e-3 (OpenAI Fallback)"
                provider_used = "openai"
            elif oai_res.data and getattr(oai_res.data[0], "url", None):
                import httpx
                img_resp = httpx.get(oai_res.data[0].url, timeout=30.0)
                img_resp.raise_for_status()
                image_bytes = img_resp.content
                model_used = "dall-e-3 (OpenAI Fallback)"
                provider_used = "openai"
        except Exception as oai_err:
            logger.error(f"❌ OpenAI DALL-E 3 fallback also failed: {oai_err}")
            raise RuntimeError(
                f"Gemini image generation failed ({gemini_error or 'unknown'}). OpenAI fallback also failed: {oai_err}"
            )

    if not image_bytes:
        raise ValueError(
            f"No image data returned from image generation (Gemini error: {gemini_error})"
        )

    filename = f"campaign_post_{int(time.time())}_{os.urandom(4).hex()}.png"
    filepath = GENERATED_MEDIA_DIR / filename

    with open(filepath, "wb") as f:
        f.write(image_bytes)

    b64_data = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:image/png;base64,{b64_data}"

    logger.info(f"✅ Generated campaign image saved to {filepath} using {model_used}")

    return {
        "url": f"/static/generated/{filename}",
        "filename": filename,
        "data_url": data_url,
        "prompt": prompt,
        "model": model_used,
        "provider": provider_used,
        "fallback_used": (provider_used == "openai")
    }


def generate_campaign_video(
    prompt: str,
    api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    max_wait_seconds: int = 360
) -> Dict[str, Any]:
    """
    Generates video teaser/ad.
    1. Attempts Veo 3.1 (veo-3.1-generate-preview) with operation polling
    2. If Veo fails, falls back to OpenAI Video API
    """
    gemini_error = None
    logger.info(f"🎬 [AI VIDEO GEN] Initiating Veo 3.1 video generation with prompt: {prompt[:120]}...")

    # Step 1: Attempt Gemini Veo 3.1
    try:
        client = _get_genai_client(api_key)
        operation = client.models.generate_videos(
            model="veo-3.1-generate-preview",
            prompt=prompt,
        )

        start_time = time.time()
        while not operation.done:
            elapsed = time.time() - start_time
            if elapsed > max_wait_seconds:
                raise TimeoutError(f"Veo 3.1 generation timed out after {int(elapsed)}s")
            logger.info(f"Waiting for Veo 3.1 video generation ({int(elapsed)}s elapsed)...")
            time.sleep(10)
            operation = client.operations.get(operation)

        if not operation.response or not operation.response.generated_videos:
            raise ValueError("No video was generated in Veo 3.1 response")

        generated_video = operation.response.generated_videos[0]
        filename = f"campaign_video_{int(time.time())}_{os.urandom(4).hex()}.mp4"
        filepath = GENERATED_MEDIA_DIR / filename

        client.files.download(file=generated_video.video, destination=str(filepath))
        logger.info(f"✅ Generated Veo 3.1 video saved to {filepath}")

        return {
            "url": f"/static/generated/{filename}",
            "filename": filename,
            "prompt": prompt,
            "model": "veo-3.1-generate-preview",
            "provider": "google",
            "fallback_used": False
        }
    except Exception as g_err:
        gemini_error = str(g_err)
        logger.warning(f"⚠️ Veo 3.1 video generation failed ({gemini_error}). Falling back to OpenAI Video...")

    # Step 2: Fallback to OpenAI Video
    try:
        oai_client = _get_openai_client(openai_api_key)
        logger.info("🎬 [AI VIDEO GEN] Polling OpenAI Video API fallback...")
        
        # Check if videos client is available on openai
        if hasattr(oai_client, "videos") and callable(getattr(oai_client.videos, "create_and_poll", None)):
            video_op = oai_client.videos.create_and_poll(
                prompt=prompt,
                model="sora-1",
                seconds=8,
            )
            content = oai_client.videos.download_content(video_op.id)
            filename = f"campaign_video_oai_{int(time.time())}_{os.urandom(4).hex()}.mp4"
            filepath = GENERATED_MEDIA_DIR / filename
            with open(filepath, "wb") as f:
                f.write(content.read() if hasattr(content, "read") else content)

            logger.info(f"✅ Generated OpenAI video saved to {filepath}")
            return {
                "url": f"/static/generated/{filename}",
                "filename": filename,
                "prompt": prompt,
                "model": "sora-1 (OpenAI Fallback)",
                "provider": "openai",
                "fallback_used": True
            }
        else:
            raise NotImplementedError("OpenAI client does not expose videos.create_and_poll on this environment")
    except Exception as oai_err:
        logger.error(f"❌ OpenAI Video fallback also failed: {oai_err}")
        raise RuntimeError(
            f"Veo 3.1 video generation failed ({gemini_error or 'unknown'}). OpenAI video fallback also failed: {oai_err}"
        )
