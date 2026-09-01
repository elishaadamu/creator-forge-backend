import logging
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.project import CoLaunchProject
from app.integrations.cloudinary_service import upload_media_to_cloudinary, delete_media_from_cloudinary

logger = logging.getLogger("creator_forge.upload")
router = APIRouter(prefix="/api/upload", tags=["Upload & Media CDN"])

class JsonUploadRequest(BaseModel):
    fileData: str # base64 data URL or remote URL
    fileName: Optional[str] = "media_asset"
    folder: Optional[str] = "creator_forge"
    projectId: Optional[str] = None

class DeleteMediaRequest(BaseModel):
    publicId: Optional[str] = None
    url: Optional[str] = None
    resourceType: Optional[str] = "image"
    projectId: Optional[str] = None
    fileId: Optional[str] = None

@router.post("")
async def upload_file_direct(body: JsonUploadRequest, db: Session = Depends(get_db)):
    """Uploads base64 or remote URL image/video/PDF to Cloudinary."""
    try:
        res = upload_media_to_cloudinary(
            file_data=body.fileData,
            public_id=body.fileName,
            folder=body.folder or "creator_forge"
        )
        
        # If projectId provided, append file metadata to project
        if body.projectId and res.get("success"):
            proj = db.get(CoLaunchProject, body.projectId)
            if proj:
                cur_meta = dict(proj.metadata_info or {})
                cur_files = cur_meta.get("project_files", [])
                new_item = {
                    "id": f"cld-{res.get('public_id')}",
                    "public_id": res.get("public_id"),
                    "name": body.fileName,
                    "url": res.get("secure_url"),
                    "optimizeUrl": res.get("optimize_url"),
                    "thumbnailUrl": res.get("thumbnail_url"),
                    "size": f"{(res.get('bytes', 0) / 1024):.1f} KB",
                    "type": res.get("format") or "media",
                    "category": res.get("resource_type") or "image",
                    "content": res.get("secure_url"),
                    "updatedAt": "Cloudinary CDN"
                }
                cur_files.append(new_item)
                cur_meta["project_files"] = cur_files
                proj.metadata_info = cur_meta
                db.commit()

        return res
    except Exception as e:
        logger.error(f"Direct upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/form")
async def upload_form_file(
    file: UploadFile = File(...),
    folder: Optional[str] = Form("creator_forge"),
    project_id: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """Uploads multipart form-data (image/video/PDF/raw code) directly to Cloudinary."""
    try:
        content_bytes = await file.read()
        import base64
        mime = file.content_type or "application/octet-stream"
        b64 = base64.b64encode(content_bytes).decode("utf-8")
        data_uri = f"data:{mime};base64,{b64}"

        res = upload_media_to_cloudinary(
            file_data=data_uri,
            public_id=file.filename,
            folder=folder or "creator_forge"
        )

        if project_id and res.get("success"):
            proj = db.get(CoLaunchProject, project_id)
            if proj:
                cur_meta = dict(proj.metadata_info or {})
                cur_files = cur_meta.get("project_files", [])
                new_item = {
                    "id": f"cld-{res.get('public_id')}",
                    "public_id": res.get("public_id"),
                    "name": file.filename,
                    "url": res.get("secure_url"),
                    "optimizeUrl": res.get("optimize_url"),
                    "thumbnailUrl": res.get("thumbnail_url"),
                    "size": f"{(res.get('bytes', len(content_bytes)) / 1024):.1f} KB",
                    "type": res.get("format") or file.filename.split('.')[-1],
                    "category": res.get("resource_type") or ("video" if "video" in mime else "image"),
                    "content": res.get("secure_url"),
                    "updatedAt": "Cloudinary CDN"
                }
                cur_files.append(new_item)
                cur_meta["project_files"] = cur_files
                proj.metadata_info = cur_meta
                db.commit()

        return res
    except Exception as e:
        logger.error(f"Form upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/delete")
@router.delete("")
def delete_file_from_cloud(payload: DeleteMediaRequest, db: Session = Depends(get_db)):
    """Deletes an asset from Cloudinary CDN and removes from project files."""
    try:
        public_id = payload.publicId
        url = payload.url
        resource_type = payload.resourceType or "image"
        
        cld_res = delete_media_from_cloudinary(
            public_id=public_id,
            url=url,
            resource_type=resource_type
        )

        # Also purge from PostgreSQL project metadata if project_id and file_id are provided
        if payload.projectId and payload.fileId:
            proj = db.get(CoLaunchProject, payload.projectId)
            if proj:
                cur_meta = dict(proj.metadata_info or {})
                cur_files = cur_meta.get("project_files", [])
                cur_files = [f for f in cur_files if f.get("id") != payload.fileId and f.get("url") != url]
                cur_meta["project_files"] = cur_files
                proj.metadata_info = cur_meta
                db.commit()

        return {
            "success": True,
            "cloudinary": cld_res
        }
    except Exception as e:
        logger.error(f"Delete file error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
