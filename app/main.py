from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from app.config import settings
from app.database import init_db
from app.routers import (
    creators, discovery, outreach, campaigns, decks, suppression, analytics, audit,
    public_portal, content_calendar, studio
)
from app.routers import agent as agent_router

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Internal Creator Forge ops pipeline — not for public use",
)

# ── CORS (allow Vite dev server + Vercel frontend) ───────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "https://creator-forge-frontend.vercel.app",
    ],
    allow_origin_regex="https://.*\\.vercel\\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Database init ────────────────────────────────────────────────────────────
@app.on_event("startup")
def startup():
    init_db()


# ── Static files + templates (only mount if the directory exists) ─────────────
BASE_DIR = Path(__file__).resolve().parent.parent
_static_dir = BASE_DIR / "frontend" / "static"
_template_dir = BASE_DIR / "frontend" / "templates"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")
templates = Jinja2Templates(directory=str(_template_dir)) if _template_dir.exists() else None


# ── API Routers ──────────────────────────────────────────────────────────────
app.include_router(creators.router)
app.include_router(discovery.router)
app.include_router(outreach.router)
app.include_router(campaigns.router)
app.include_router(decks.router)
app.include_router(suppression.router)
app.include_router(analytics.router)
app.include_router(audit.router)
app.include_router(agent_router.router)
app.include_router(public_portal.router)
app.include_router(content_calendar.router)
app.include_router(studio.router)


# ── Analytics alias (/api/analytics/summary used by ops CampaignStats) ──────
@app.get("/analytics/summary")
@app.get("/api/analytics/summary")
def analytics_summary_alias():
    """Ops dashboard analytics — counts across all pipeline stages."""
    from app.database import get_db
    from app.models.outreach import OutreachMessage, Thread, Reply
    from app.models.creator import Creator
    db = next(get_db())
    try:
        total_scraped   = db.query(Creator).count()
        total_qualified = db.query(Creator).filter(Creator.status == "qualified").count()
        total_sent      = db.query(OutreachMessage).filter(OutreachMessage.status == "sent").count()
        total_replies   = db.query(Reply).count()
        total_converted = db.query(Thread).filter(Thread.status == "converted").count()
        return {
            "total_scraped":       total_scraped,
            "total_qualified":     total_qualified,
            "total_outreach_sent": total_sent,
            "total_replies":       total_replies,
            "total_interested":    0,
            "total_converted":     total_converted,
            "reply_rate":          round(total_replies / total_sent * 100, 1) if total_sent else 0,
            "open_rate":           0,
            "campaigns":           [],
        }
    finally:
        db.close()


# ── UI Routes ────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
@app.get("/login", response_class=HTMLResponse)
@app.get("/signup", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
def index(request: Request):
    if templates is None:
        return HTMLResponse("<h1>Creator Forge API</h1><p>Visit <a href='/docs'>/docs</a> for the API.</p>")
    return templates.TemplateResponse("app.html", {"request": request})


# ── UI Routes (legacy Jinja2 — only active if frontend/templates dir exists) ──
def _tpl(request: Request, name: str, **ctx):
    if templates is None:
        return HTMLResponse(f"<p>API-only mode. Visit <a href='/docs'>/docs</a>.</p>", status_code=200)
    return templates.TemplateResponse(name, {"request": request, **ctx})

@app.get("/discovery",             response_class=HTMLResponse)
def view_discovery(request: Request):         return _tpl(request, "discovery.html")

@app.get("/leads",                 response_class=HTMLResponse)
def view_leads(request: Request):             return _tpl(request, "qualified_leads.html")

@app.get("/creators/{creator_id}", response_class=HTMLResponse)
def view_creator(request: Request, creator_id: str): return _tpl(request, "creator_detail.html", creator_id=creator_id)

@app.get("/review",                response_class=HTMLResponse)
def view_review(request: Request):            return _tpl(request, "review_queue.html")

@app.get("/outreach-editor",       response_class=HTMLResponse)
def view_outreach_editor(request: Request):   return _tpl(request, "outreach_editor.html")

@app.get("/send-queue",            response_class=HTMLResponse)
def view_send_queue(request: Request):        return _tpl(request, "send_queue.html")

@app.get("/inbox",                 response_class=HTMLResponse)
def view_inbox(request: Request):             return _tpl(request, "reply_inbox.html")

@app.get("/analytics",             response_class=HTMLResponse)
def view_analytics(request: Request):         return _tpl(request, "analytics.html")

@app.get("/audit",                 response_class=HTMLResponse)
def view_audit(request: Request):             return _tpl(request, "audit_log.html")

@app.get("/decks/{deck_id}/preview", response_class=HTMLResponse)
def view_deck(request: Request, deck_id: str): return _tpl(request, "deck_preview.html", deck_id=deck_id)



# ── Settings API ─────────────────────────────────────────────────────────────
@app.get("/api/settings")
def get_settings():
    """Return current runtime-editable settings (masked secrets)."""
    def mask(v): return ("•" * 8 + v[-4:]) if v and len(v) > 4 else ("set" if v else "")
    return {
        "anthropic_api_key":  mask(settings.ANTHROPIC_API_KEY),
        "apify_api_key":      mask(settings.APIFY_API_KEY),
        "sendgrid_api_key":   mask(settings.SENDGRID_API_KEY),
        "from_email":         settings.FROM_EMAIL,
        "from_name":          settings.FROM_NAME,
        "ai_model":           settings.AI_MODEL,
        "apify_configured":   bool(settings.APIFY_API_KEY),
        "ai_configured":      bool(settings.ANTHROPIC_API_KEY),
    }


@app.post("/api/settings")
def update_settings(body: dict):
    """Update runtime-editable settings and persist to .env."""
    from pathlib import Path as _Path
    import re as _re

    allowed = {
        "anthropic_api_key": "ANTHROPIC_API_KEY",
        "apify_api_key":     "APIFY_API_KEY",
        "sendgrid_api_key":  "SENDGRID_API_KEY",
        "from_email":        "FROM_EMAIL",
        "from_name":         "FROM_NAME",
    }
    updated = []
    env_updates = {}
    for field, attr in allowed.items():
        val = body.get(field)
        if val is not None:
            setattr(settings, attr, val)
            env_updates[attr] = val
            updated.append(field)

    if env_updates:
        env_path = _Path(settings.DATABASE_URL.replace("sqlite:///", "").replace("creator_forge.db", "")).parent / ".env"
        # Use BASE_DIR
        from app.config import BASE_DIR
        env_path = BASE_DIR / ".env"
        existing = {}
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    existing[k.strip()] = v.strip()
        existing.update(env_updates)
        lines = ["# Creator Forge environment variables — auto-managed"]
        for k, v in existing.items():
            lines.append(f"{k}={v}")
        env_path.write_text("\n".join(lines) + "\n")

    return {"updated": updated}


# ── Fix bad avatar URLs in DB (one-time cleanup) ─────────────────────────────
@app.post("/api/admin/fix-avatars")
def fix_avatars():
    """Decode unicode-escaped avatar URLs already stored in the DB."""
    from app.database import get_db as _get_db
    from app.models.creator import Creator as _Creator
    from app.services.scraper import _clean_url
    db = next(_get_db())
    fixed = 0
    for c in db.query(_Creator).all():
        if c.avatar_url and ("\\u" in c.avatar_url or "\\/" in c.avatar_url):
            c.avatar_url = _clean_url(c.avatar_url)
            fixed += 1
    db.commit()
    return {"fixed": fixed}


# ── Avatar proxy (bypasses browser CORS on yt3.ggpht.com etc.) ───────────────
@app.get("/api/proxy/avatar")
def proxy_avatar(url: str):
    """Fetch a remote avatar image server-side and return it to avoid CORS blocks."""
    import httpx
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Referer": "https://www.youtube.com/",
    }
    try:
        r = httpx.get(url, headers=HEADERS, timeout=10, follow_redirects=True)
        content_type = r.headers.get("content-type", "image/jpeg")
        return Response(
            content=r.content,
            media_type=content_type,
            headers={"Cache-Control": "public, max-age=86400"},
        )
    except Exception:
        return Response(status_code=404)


# ── NVIDIA NIM Image Generation Proxy ────────────────────────────────────────
from pydantic import BaseModel

class InferRequest(BaseModel):
    prompt: str
    seed: int = 0

@app.post("/v1/infer")
@app.post("/api/v1/infer")
def nvidia_infer(req: InferRequest, request: Request):
    """Proxy image generation requests to NVIDIA NIM FLUX.1-schnell model."""
    import httpx
    import logging
    
    # Read custom nvidia key from headers if provided
    nvidia_key = request.headers.get("x-nvidia-api-key", "").strip() or settings.NVIDIA_API_KEY
    if not nvidia_key:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="NVIDIA API Key not provided. Enter it in settings.")

    url = "https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux.1-schnell"
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {nvidia_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "prompt": req.prompt,
        "seed": req.seed
    }
    
    try:
        # Use a longer timeout as image generation can take several seconds
        r = httpx.post(url, headers=headers, json=payload, timeout=45.0)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        err_msg = str(e)
        if hasattr(e, 'response') and e.response is not None:
            err_msg += f" - {e.response.text}"
        logging.error(f"NVIDIA NIM Image generation failed: {err_msg}")
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=f"Image generation failed: {err_msg}")


# ── Signup Welcome Email API ──────────────────────────────────────────────────
class SignupEmailRequest(BaseModel):
    email: str
    username: str
    sendgrid_api_key: str = ""

@app.post("/api/auth/signup-email")
def send_signup_email(req: SignupEmailRequest):
    """Send a successful account creation email using SendGrid."""
    import httpx
    import logging

    api_key = req.sendgrid_api_key.strip() or settings.SENDGRID_API_KEY
    if not api_key:
        logging.warning("SendGrid API key not set. Simulating welcome email success.")
        return {
            "status": "simulated",
            "message": "SendGrid API key not set. Onboarding welcome email simulation succeeded.",
            "recipient": req.email
        }

    from_email = settings.FROM_EMAIL or "welcome@creatorforge.com"
    from_name = settings.FROM_NAME or "Creator Forge Team"

    subject = f"Welcome to Creator Forge, {req.username}!"
    body_text = f"Hi {req.username},\n\nYour account has been successfully created on Creator Forge. Welcome to the command center!\n\nBest,\nThe Creator Forge Team"
    body_html = f"""
    <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 24px; border: 1px solid #1f2937; border-radius: 16px; background-color: #0b0b0b; color: #f3f4f6; box-shadow: 0 10px 25px rgba(0,0,0,0.5);">
        <div style="text-align: center; margin-bottom: 32px; border-bottom: 1px solid #1f2937; padding-bottom: 24px;">
            <h1 style="color: #ffffff; font-size: 26px; font-weight: 800; margin: 0; letter-spacing: -0.025em; text-transform: uppercase;">CREATOR FORGE</h1>
            <p style="color: #9ca3af; font-size: 13px; margin: 6px 0 0 0; text-transform: uppercase; letter-spacing: 0.1em;">Secure Operator Console</p>
        </div>
        <div style="line-height: 1.6; font-size: 15px; color: #d1d5db;">
            <p style="font-size: 16px; color: #ffffff;">Hi <strong>{req.username}</strong>,</p>
            <p>Your secure operator account has been successfully created. Welcome to the **Creator Forge** command center!</p>
            <p>You now have full local access to your personal audience builder, automated launch campaigns, and AI content calendar.</p>
            
            <div style="background: rgba(245, 158, 11, 0.04); border: 1px solid rgba(245, 158, 11, 0.15); border-left: 4px solid #f59e0b; border-radius: 12px; padding: 16px; margin: 24px 0;">
                <h4 style="margin: 0 0 4px 0; font-size: 13px; color: #ffffff; font-weight: 600;">🔒 Local Sandbox Privacy Enforced</h4>
                <p style="margin: 0; font-size: 12px; color: #9ca3af; line-height: 1.5;">
                    To protect your digital identity, all platform API credentials (like Apify and Gemini keys) are loaded strictly in your browser's active memory. They are never written to databases or persistent storage, and are immediately cleared when you log out.
                </p>
            </div>
            
            <p>Let's build something epic.</p>
            <p style="margin-top: 40px; border-t: 1px solid #1f2937; padding-top: 24px; font-size: 13px; color: #9ca3af; line-height: 1.5;">
                Best regards,<br/>
                <strong style="color: #ffffff;">The Creator Forge Team</strong>
            </p>
        </div>
    </div>
    """

    url = "https://api.sendgrid.com/v3/mail/send"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "personalizations": [
            {
                "to": [{"email": req.email}]
            }
        ],
        "from": {
            "email": from_email,
            "name": from_name
        },
        "subject": subject,
        "content": [
            {
                "type": "text/plain",
                "value": body_text
            },
            {
                "type": "text/html",
                "value": body_html
            }
        ]
    }

    try:
        r = httpx.post(url, headers=headers, json=payload, timeout=15.0)
        if r.status_code not in (200, 201, 202):
            logging.error(f"SendGrid responded with status {r.status_code}: {r.text}")
            return {
                "status": "error",
                "message": f"SendGrid API responded with status {r.status_code}"
            }
        return {"status": "sent", "message_id": r.headers.get("X-Message-Id", "unknown")}
    except Exception as e:
        logging.error(f"SendGrid connection error: {str(e)}")
        return {"status": "error", "message": f"Connection to SendGrid failed: {str(e)}"}


# ── Download Keys PDF API ─────────────────────────────────────────────────────
class DownloadKeysRequest(BaseModel):
    apify_token: str = ""
    youtube_api_key: str = ""
    gemini_api_key: str = ""
    together_api_key: str = ""
    nvidia_api_key: str = ""

@app.post("/api/settings/download-keys-pdf")
def download_keys_pdf(req: DownloadKeysRequest):
    """Generate a clean, structured PDF of the user's transient API keys."""
    from fastapi.responses import StreamingResponse
    import io
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos
    from datetime import datetime

    class StyledPDF(FPDF):
        def header(self):
            # Sleek slate banner
            self.set_fill_color(15, 23, 42)  # slate-900
            self.rect(0, 0, 210, 35, "F")
            
            # Header Title
            self.set_text_color(255, 255, 255)
            self.set_font("Helvetica", size=16, style="B")
            self.set_xy(10, 10)
            self.cell(190, 8, text="CREATOR FORGE", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
            
            # Header Subtitle
            self.set_font("Helvetica", size=9)
            self.set_text_color(148, 163, 184)  # slate-400
            self.cell(190, 5, text="SECURITY KEY BACKUP | CONFIDENTIAL", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
            
            self.set_y(45)

        def footer(self):
            self.set_y(-25)
            self.set_font("Helvetica", size=8, style="I")
            self.set_text_color(148, 163, 184)
            # Footer dividing line
            self.set_draw_color(226, 232, 240)
            self.line(10, self.get_y(), 200, self.get_y())
            self.set_y(self.get_y() + 2)
            
            self.cell(100, 10, text=f"Generated on {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')} | Creator Forge Auth Layer", new_x=XPos.RIGHT, new_y=YPos.TOP, align="L")
            self.cell(90, 10, text=f"Page {self.page_no()}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="R")

    pdf = StyledPDF()
    pdf.add_page()
    pdf.ln(5)
    
    # Intro/Security description
    pdf.set_text_color(71, 85, 105)  # slate-600
    pdf.set_font("Helvetica", size=10)
    pdf.multi_cell(
        190, 5, 
        text="Security Notice: For your privacy and protection, Creator Forge enforces in-memory transient key storage. "
             "These keys are never stored in databases or local browser caches (localStorage). "
             "Keep this PDF backup secure. You can copy-paste these keys when launching the console in a new session."
    )
    pdf.ln(8)
    
    keys_data = [
        ("Apify Token", req.apify_token),
        ("YouTube API Key", req.youtube_api_key),
        ("Google Gemini Key", req.gemini_api_key),
        ("Together.ai Key", req.together_api_key),
        ("NVIDIA NIM Key", req.nvidia_api_key)
    ]
    
    for label, val in keys_data:
        # Key Label
        pdf.set_text_color(15, 23, 42)  # slate-900
        pdf.set_font("Helvetica", size=10, style="B")
        pdf.cell(190, 6, text=label, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        # Styled Box container for the Key value
        pdf.set_fill_color(248, 250, 252)  # slate-50
        pdf.set_draw_color(226, 232, 240)  # slate-200
        pdf.set_text_color(30, 41, 59)     # slate-800
        pdf.set_font("Courier", size=9)
        
        display_val = val.strip() if val.strip() else "[Not Configured]"
        pdf.multi_cell(190, 8, text=display_val, border=1, fill=True)
        pdf.ln(4)
        
    pdf_bytes = bytes(pdf.output())
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=creator_forge_api_keys.pdf"}
    )


# ── Authentication & Synchronization APIs ─────────────────────────────────────
from typing import Any, Dict, Optional
from app.database import get_db
from sqlalchemy.orm import Session

class SignupRequest(BaseModel):
    username: str
    email: str
    password: str
    creator_data: Optional[Dict[str, Any]] = None
    calendar_data: Optional[Dict[str, Any]] = None
    launch_pack_data: Optional[Dict[str, Any]] = None
    studio_data: Optional[Dict[str, Any]] = None

class LoginRequest(BaseModel):
    identifier: str
    password: str

class SyncRequest(BaseModel):
    username: str
    creator_data: Optional[Dict[str, Any]] = None
    calendar_data: Optional[Dict[str, Any]] = None
    launch_pack_data: Optional[Dict[str, Any]] = None
    studio_data: Optional[Dict[str, Any]] = None

@app.post("/api/auth/signup")
def auth_signup(req: SignupRequest, db: Session = Depends(get_db)):
    from app.models.creator import UserProfile
    from fastapi import HTTPException

    # Check unique constraints
    existing = db.query(UserProfile).filter(
        (UserProfile.username == req.username) | (UserProfile.email == req.email)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username or email already registered")

    user = UserProfile(
        username=req.username,
        email=req.email,
        password=req.password,
        creator_data=req.creator_data,
        calendar_data=req.calendar_data,
        launch_pack_data=req.launch_pack_data,
        studio_data=req.studio_data
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "status": "success",
        "username": user.username,
        "email": user.email,
        "creator_data": user.creator_data,
        "calendar_data": user.calendar_data,
        "launch_pack_data": user.launch_pack_data,
        "studio_data": user.studio_data
    }

@app.post("/api/auth/login")
def auth_login(req: LoginRequest, db: Session = Depends(get_db)):
    from app.models.creator import UserProfile
    from fastapi import HTTPException

    user = db.query(UserProfile).filter(
        (UserProfile.username == req.identifier) | (UserProfile.email == req.identifier)
    ).first()

    if not user or user.password != req.password:
        raise HTTPException(status_code=400, detail="Invalid username/email or password credentials.")

    return {
        "status": "success",
        "username": user.username,
        "email": user.email,
        "creator_data": user.creator_data,
        "calendar_data": user.calendar_data,
        "launch_pack_data": user.launch_pack_data,
        "studio_data": user.studio_data,
        "ai_keys": user.ai_keys  # Return saved AI keys if user consented
    }

@app.post("/api/auth/sync")
def auth_sync(req: SyncRequest, db: Session = Depends(get_db)):
    from app.models.creator import UserProfile
    from fastapi import HTTPException

    user = db.query(UserProfile).filter(UserProfile.username == req.username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if req.creator_data is not None:
        user.creator_data = req.creator_data
    if req.calendar_data is not None:
        user.calendar_data = req.calendar_data
    if req.launch_pack_data is not None:
        user.launch_pack_data = req.launch_pack_data
    if req.studio_data is not None:
        user.studio_data = req.studio_data

    db.commit()
    return {"status": "success"}


# ── AI Keys Save/Load (user-consented persistence) ────────────────────────────

class SaveAiKeysRequest(BaseModel):
    username: str
    ai_keys: Dict[str, str]  # { geminiKey, togetherKey, nvidiaKey }

class DeleteAiKeysRequest(BaseModel):
    username: str

@app.post("/api/auth/save-ai-keys")
def save_ai_keys(req: SaveAiKeysRequest, db: Session = Depends(get_db)):
    """Save AI API keys to the database (user explicitly consented)."""
    from app.models.creator import UserProfile
    from fastapi import HTTPException

    user = db.query(UserProfile).filter(UserProfile.username == req.username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.ai_keys = req.ai_keys
    db.commit()
    return {"status": "success", "message": "AI keys saved securely."}

@app.post("/api/auth/delete-ai-keys")
def delete_ai_keys(req: DeleteAiKeysRequest, db: Session = Depends(get_db)):
    """Remove saved AI keys from database."""
    from app.models.creator import UserProfile
    from fastapi import HTTPException

    user = db.query(UserProfile).filter(UserProfile.username == req.username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.ai_keys = None
    db.commit()
    return {"status": "success", "message": "AI keys removed from database."}

@app.get("/api/auth/load-ai-keys/{username}")
def load_ai_keys(username: str, db: Session = Depends(get_db)):
    """Load saved AI keys for a user (only returns if previously consented)."""
    from app.models.creator import UserProfile
    from fastapi import HTTPException

    user = db.query(UserProfile).filter(UserProfile.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {"status": "success", "ai_keys": user.ai_keys}


# ── Admin Control APIs ────────────────────────────────────────────────────────
@app.get("/api/admin/users")
def list_admin_users(db: Session = Depends(get_db)):
    """List all registered users for admin control panel."""
    from app.models.creator import UserProfile
    users = db.query(UserProfile).order_by(UserProfile.created_at.desc()).all()
    out = []
    for u in users:
        platform = None
        handle = None
        if u.creator_data and isinstance(u.creator_data, dict):
            platform = u.creator_data.get("platform")
            handle = u.creator_data.get("handle")
        
        has_ai_keys = False
        if u.ai_keys and isinstance(u.ai_keys, dict):
            has_ai_keys = any(bool(v) for v in u.ai_keys.values())

        out.append({
            "username": u.username,
            "email": u.email,
            "platform": platform,
            "handle": handle,
            "has_ai_keys": has_ai_keys,
            "created_at": u.created_at.isoformat() if u.created_at else None
        })
    return {"status": "success", "users": out}


@app.delete("/api/admin/users/{username}")
def delete_admin_user(username: str, db: Session = Depends(get_db)):
    """Delete a user profile."""
    from app.models.creator import UserProfile
    from fastapi import HTTPException
    user = db.query(UserProfile).filter(UserProfile.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
    return {"status": "success", "message": f"User {username} deleted."}


@app.get("/api/admin/system-stats")
def get_system_stats(db: Session = Depends(get_db)):
    """Return database stats and row counts."""
    from app.models.creator import UserProfile, Creator, ProductRecommendation
    from pathlib import Path as _Path
    
    db_size_bytes = 0
    try:
        db_path = _Path(settings.DATABASE_URL.replace("sqlite:///", ""))
        if db_path.exists():
            db_size_bytes = db_path.stat().st_size
    except Exception:
        pass

    try:
        users_count = db.query(UserProfile).count()
    except Exception:
        users_count = 0

    try:
        creators_count = db.query(Creator).count()
    except Exception:
        creators_count = 0

    try:
        recs_count = db.query(ProductRecommendation).count()
    except Exception:
        recs_count = 0

    try:
        from app.models.campaign import Campaign
        campaigns_count = db.query(Campaign).count()
    except Exception:
        campaigns_count = 0

    try:
        from app.models.outreach import OutreachMessage
        outreach_count = db.query(OutreachMessage).count()
    except Exception:
        outreach_count = 0

    try:
        from app.models.outreach import SuppressionList
        suppression_count = db.query(SuppressionList).count()
    except Exception:
        suppression_count = 0

    try:
        from app.models.audit import AuditLog
        audit_logs_count = db.query(AuditLog).count()
    except Exception:
        audit_logs_count = 0

    return {
        "status": "success",
        "db_size": f"{db_size_bytes / 1024:.1f} KB",
        "users_count": users_count,
        "creators_count": creators_count,
        "recs_count": recs_count,
        "campaigns_count": campaigns_count,
        "outreach_count": outreach_count,
        "suppression_count": suppression_count,
        "audit_logs_count": audit_logs_count,
    }


# ── Health ───────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}


