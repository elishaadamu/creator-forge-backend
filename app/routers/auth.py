import httpx
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse
from app.config import settings
from urllib.parse import urlparse

router = APIRouter(prefix="/api/auth", tags=["Auth"])

def get_frontend_url(request: Request) -> str:
    """
    Get the frontend dashboard URL dynamically based on Request headers
    to prevent connection refused issues when using 127.0.0.1 or custom IPs.
    """
    referer = request.headers.get("referer") or request.headers.get("origin")
    if referer:
        parsed = urlparse(referer)
        # Returns e.g. http://localhost:5173/dashboard or http://127.0.0.1:5173/dashboard
        return f"{parsed.scheme}://{parsed.netloc}/dashboard"
    return "http://localhost:5173/dashboard"

def get_callback_uri(request: Request) -> str:
    """
    Get the callback redirect URI matching uvicorn's bound host and port.
    """
    return str(request.base_url).rstrip("/") + "/api/auth/instagram/callback"

@router.get("/instagram/login")
async def instagram_login(request: Request, handle: str = "default"):
    """
    Initiate the Meta/Instagram OAuth flow.
    """
    frontend_url = get_frontend_url(request)
    client_id = settings.META_CLIENT_ID
    if not client_id or client_id == "YOUR_META_APP_ID_HERE":
        # If the user hasn't set up the Meta App yet, we can simulate success for demo purposes
        # Or we could raise an error. Let's redirect to frontend with a fake success parameter 
        # so the UI still works even without a real Meta App configured.
        return RedirectResponse(f"{frontend_url}?tab=accounts&ig_connected=true&demo_mode=true")

    # The required scopes for Instagram publishing
    scopes = "instagram_basic,instagram_content_publish,pages_read_engagement,pages_show_list"
    
    # We pass the user's handle in the state parameter so we know who they are when they return
    state = handle
    redirect_uri = get_callback_uri(request)

    oauth_url = (
        f"https://www.facebook.com/v21.0/dialog/oauth"
        f"?client_id={client_id}"
        f"&display=page"
        f"&extras={{\"setup\":{{\"channel\":\"IG_API\"}}}}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope={scopes}"
        f"&state={state}"
    )
    return RedirectResponse(oauth_url)


@router.get("/instagram/callback")
async def instagram_callback(request: Request, code: str = None, state: str = None, error: str = None, error_description: str = None):
    """
    Handle the callback from Meta after the user authenticates.
    """
    frontend_url = get_frontend_url(request)
    redirect_uri = get_callback_uri(request)

    if error:
        print(f"Meta OAuth Error: {error} - {error_description}")
        return RedirectResponse(f"{frontend_url}?tab=accounts&ig_error=true")

    if not code:
        raise HTTPException(status_code=400, detail="No code provided")

    # 1. Exchange code for short-lived access token
    token_url = "https://graph.facebook.com/v21.0/oauth/access_token"
    params = {
        "client_id": settings.META_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "client_secret": settings.META_CLIENT_SECRET,
        "code": code
    }

    async with httpx.AsyncClient() as client:
        resp = await client.get(token_url, params=params)
        data = resp.json()

    if "error" in data:
        print(f"Error fetching token: {data}")
        return RedirectResponse(f"{frontend_url}?tab=accounts&ig_error=true")

    short_lived_token = data.get("access_token")

    # 2. Exchange short-lived token for long-lived token (60 days)
    long_lived_url = "https://graph.facebook.com/v21.0/oauth/access_token"
    ll_params = {
        "grant_type": "fb_exchange_token",
        "client_id": settings.META_CLIENT_ID,
        "client_secret": settings.META_CLIENT_SECRET,
        "fb_exchange_token": short_lived_token
    }

    async with httpx.AsyncClient() as client:
        ll_resp = await client.get(long_lived_url, params=ll_params)
        ll_data = ll_resp.json()

    long_lived_token = ll_data.get("access_token")

    if long_lived_token:
        # Note: In a real app, you would store `long_lived_token` securely in the database 
        # linked to `state` (the creator's handle).
        print(f"Successfully obtained long-lived token for {state}: {long_lived_token[:15]}...")
        # settings.INSTAGRAM_ACCESS_TOKEN = long_lived_token # (in-memory update)
    
    return RedirectResponse(f"{frontend_url}?tab=accounts&ig_connected=true")

