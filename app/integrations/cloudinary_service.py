import os
import logging
import re
from app.config import settings

logger = logging.getLogger("creator_forge.cloudinary")

try:
    import cloudinary
    import cloudinary.uploader
    from cloudinary.utils import cloudinary_url
    HAS_CLOUDINARY = True
except ImportError:
    HAS_CLOUDINARY = False
    logger.warning("[Cloudinary] cloudinary package not installed in environment, fallback active.")

def init_cloudinary():
    """Initializes Cloudinary configuration with environment credentials."""
    if not HAS_CLOUDINARY:
        return
    try:
        if settings.CLOUDINARY_URL:
            cloudinary.config(cloudinary_url=settings.CLOUDINARY_URL)
        elif settings.CLOUDINARY_CLOUD_NAME and settings.CLOUDINARY_API_KEY:
            cloudinary.config(
                cloud_name=settings.CLOUDINARY_CLOUD_NAME,
                api_key=settings.CLOUDINARY_API_KEY,
                api_secret=settings.CLOUDINARY_API_SECRET or None,
                secure=True
            )
    except Exception as e:
        logger.warning(f"[Cloudinary] Init warning: {e}")

# Call on import
init_cloudinary()

def extract_public_id_from_url(url: str) -> str:
    """Extracts Cloudinary public ID from a delivery URL."""
    if not url or "cloudinary.com" not in url:
        return ""
    try:
        # e.g., https://res.cloudinary.com/axk6onmw/image/upload/v12345/creator_forge/sample.jpg
        # Extract everything after /upload/(v\d+/)?
        match = re.search(r"/upload/(?:v\d+/)?(.+?)(?:\.[a-zA-Z0-9]+)?$", url)
        if match:
            return match.group(1)
    except Exception:
        pass
    return ""

def upload_media_to_cloudinary(file_data, public_id=None, resource_type="auto", folder="creator_forge"):
    """
    Uploads an image, video, PDF, or document to Cloudinary CDN.
    """
    if not HAS_CLOUDINARY:
        return {
            "success": False,
            "error": "Cloudinary package not available",
            "secure_url": file_data if isinstance(file_data, str) and (file_data.startswith("http") or file_data.startswith("data:")) else None
        }

    try:
        init_cloudinary()

        # Detect raw resource type for code and text files
        actual_resource_type = resource_type
        if public_id and (resource_type == "auto" or not resource_type):
            lower_name = public_id.lower()
            if any(lower_name.endswith(ext) for ext in [".js", ".jsx", ".ts", ".tsx", ".py", ".md", ".sql", ".json", ".csv", ".txt", ".env", ".yaml", ".yml", ".html", ".css", ".dart"]):
                actual_resource_type = "raw"

        upload_params = {
            "resource_type": actual_resource_type,
            "folder": folder,
            "overwrite": True
        }
        if public_id:
            clean_id = public_id.replace(" ", "_")
            upload_params["public_id"] = clean_id

        result = cloudinary.uploader.upload(file_data, **upload_params)
        
        secure_url = result.get("secure_url")
        pub_id = result.get("public_id")
        
        optimize_url = secure_url
        auto_crop_thumbnail = secure_url

        if result.get("resource_type") == "image":
            try:
                opt_url, _ = cloudinary_url(pub_id, fetch_format="auto", quality="auto", secure=True)
                crop_url, _ = cloudinary_url(pub_id, width=500, height=500, crop="auto", gravity="auto", secure=True)
                optimize_url = opt_url or secure_url
                auto_crop_thumbnail = crop_url or secure_url
            except Exception:
                pass

        return {
            "success": True,
            "secure_url": secure_url,
            "optimize_url": optimize_url,
            "thumbnail_url": auto_crop_thumbnail,
            "public_id": pub_id,
            "resource_type": result.get("resource_type", "image"),
            "format": result.get("format"),
            "bytes": result.get("bytes", 0),
            "width": result.get("width"),
            "height": result.get("height"),
            "created_at": result.get("created_at")
        }
    except Exception as e:
        logger.warning(f"[Cloudinary] Upload failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "secure_url": file_data if isinstance(file_data, str) and (file_data.startswith("http") or file_data.startswith("data:")) else None
        }

def delete_media_from_cloudinary(public_id: str = None, url: str = None, resource_type: str = "image"):
    """
    Deletes an asset from Cloudinary by public ID or Cloudinary URL.
    """
    if not HAS_CLOUDINARY:
        return {"success": False, "error": "Cloudinary package not available"}

    target_id = public_id or extract_public_id_from_url(url)
    if not target_id:
        return {"success": False, "error": "No valid public_id or Cloudinary URL provided"}

    try:
        init_cloudinary()
        
        # Try deleting with given resource_type, fallback to raw/video if not found
        res_types_to_try = [resource_type]
        if resource_type == "image":
            res_types_to_try.extend(["raw", "video"])
        elif resource_type == "raw":
            res_types_to_try.extend(["image", "video"])
        elif resource_type == "video":
            res_types_to_try.extend(["image", "raw"])

        last_result = None
        for r_type in res_types_to_try:
            try:
                res = cloudinary.uploader.destroy(target_id, resource_type=r_type, invalidate=True)
                last_result = res
                if res.get("result") == "ok":
                    logger.info(f"[Cloudinary] Successfully deleted '{target_id}' as {r_type}")
                    return {"success": True, "result": res, "deleted_id": target_id}
            except Exception as inner_e:
                logger.debug(f"[Cloudinary] Destroy attempt as {r_type} error: {inner_e}")

        logger.info(f"[Cloudinary] Destroy completed for '{target_id}': {last_result}")
        return {"success": True, "result": last_result, "deleted_id": target_id}
    except Exception as e:
        logger.warning(f"[Cloudinary] Delete error for '{target_id}': {e}")
        return {"success": False, "error": str(e)}

def delete_all_files_for_project(proj):
    """
    Deletes all Cloudinary assets associated with a project:
    - Files in metadata_info["project_files"]
    - Selected concept assets / mockups
    - Campaign assets
    """
    if not proj or not HAS_CLOUDINARY:
        return
    try:
        meta = proj.metadata_info or {}
        files = meta.get("project_files", [])
        if isinstance(files, list):
            for f in files:
                if isinstance(f, dict):
                    pub_id = f.get("public_id")
                    url = f.get("url") or f.get("content")
                    cat = f.get("category", "image")
                    r_type = "video" if cat == "video" else "raw" if cat == "code" else "image"
                    delete_media_from_cloudinary(public_id=pub_id, url=url, resource_type=r_type)

        # Also check mockup / concept assets
        concept = proj.selected_concept or {}
        if isinstance(concept, dict):
            for k, val in concept.items():
                if isinstance(val, str) and "cloudinary.com" in val:
                    delete_media_from_cloudinary(url=val)

        # Also check campaign assets
        if hasattr(proj, "validation_campaign") and proj.validation_campaign and proj.validation_campaign.product_assets:
            assets = proj.validation_campaign.product_assets
            if isinstance(assets, dict):
                for k, val in assets.items():
                    if isinstance(val, str) and "cloudinary.com" in val:
                        delete_media_from_cloudinary(url=val)
    except Exception as e:
        logger.warning(f"[Cloudinary] Error purging assets for project {getattr(proj, 'id', 'unknown')}: {e}")

