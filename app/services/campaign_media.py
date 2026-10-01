# -*- coding: utf-8 -*-
"""
Campaign AI Media Generator Service
Integrates Google GenAI SDK for:
- Video Generation via Veo 3.1 (veo-3.1-generate-preview)
- Image Generation via Gemini 3.1 Flash Image (gemini-3.1-flash-image)
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


def _get_client(api_key: Optional[str] = None):
    from google import genai
    resolved_key = (
        api_key
        or settings.GEMINI_API_KEY
        or os.getenv("GEMINI_API_KEY", "")
    )
    if resolved_key:
        return genai.Client(api_key=resolved_key)
    return genai.Client()


def generate_campaign_social_image(prompt: str, api_key: Optional[str] = None) -> Dict[str, Any]:
    """
    Generates high-impact AI campaign graphic using gemini-3.1-flash-image.
    """
    client = _get_client(api_key)
    image_bytes = None

    logger.info(f"🎨 [AI IMAGE GEN] Requesting gemini-3.1-flash-image with prompt: {prompt[:120]}...")

    # Primary user-specified pattern:
    try:
        interaction = client.interactions.create(
            model="gemini-3.1-flash-image",
            input=prompt,
        )
        if hasattr(interaction, "output_image") and getattr(interaction.output_image, "data", None):
            image_bytes = base64.b64decode(interaction.output_image.data)
        elif hasattr(interaction, "output") and getattr(interaction.output, "data", None):
            image_bytes = base64.b64decode(interaction.output.data)
    except Exception as e:
        logger.warning(f"⚠️ interactions.create(gemini-3.1-flash-image) error: {e}. Attempting fallback...")
        try:
            # Fallback to models.generate_images if interactions API is not available
            res = client.models.generate_images(
                model="imagen-3.0-generate-002",
                prompt=prompt,
            )
            if res.generated_images:
                image_bytes = res.generated_images[0].image.image_bytes
        except Exception as fallback_e:
            logger.error(f"❌ Image generation fallback failed: {fallback_e}")
            raise e

    if not image_bytes:
        raise ValueError("No image data returned from image generation API")

    filename = f"campaign_post_{int(time.time())}_{os.urandom(4).hex()}.png"
    filepath = GENERATED_MEDIA_DIR / filename

    with open(filepath, "wb") as f:
        f.write(image_bytes)

    b64_data = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:image/png;base64,{b64_data}"

    logger.info(f"✅ Generated campaign image saved to {filepath}")

    return {
        "url": f"/static/generated/{filename}",
        "filename": filename,
        "data_url": data_url,
        "prompt": prompt,
        "model": "gemini-3.1-flash-image"
    }


def generate_campaign_video(
    prompt: str,
    api_key: Optional[str] = None,
    max_wait_seconds: int = 360
) -> Dict[str, Any]:
    """
    Generates video teaser/ad using Veo 3.1 (veo-3.1-generate-preview).
    Polls operation status until ready and downloads to destination.
    """
    from google.genai import types

    client = _get_client(api_key)

    logger.info(f"🎬 [AI VIDEO GEN] Initiating Veo 3.1 video generation with prompt: {prompt[:120]}...")

    operation = client.models.generate_videos(
        model="veo-3.1-generate-preview",
        prompt=prompt,
    )

    start_time = time.time()
    # Poll operation status until the video is ready
    while not operation.done:
        elapsed = time.time() - start_time
        if elapsed > max_wait_seconds:
            raise TimeoutError(f"Video generation timed out after {int(elapsed)}s")
        print("Waiting for video generation to complete...")
        time.sleep(10)
        operation = client.operations.get(operation)

    # Download generated video
    if not operation.response or not operation.response.generated_videos:
        raise ValueError("No video was generated in Veo 3.1 response")

    generated_video = operation.response.generated_videos[0]
    filename = f"campaign_video_{int(time.time())}_{os.urandom(4).hex()}.mp4"
    filepath = GENERATED_MEDIA_DIR / filename

    client.files.download(file=generated_video.video, destination=str(filepath))
    print(f"Generated video saved to {filepath}")
    logger.info(f"✅ Generated video saved to {filepath}")

    return {
        "url": f"/static/generated/{filename}",
        "filename": filename,
        "prompt": prompt,
        "model": "veo-3.1-generate-preview"
    }
