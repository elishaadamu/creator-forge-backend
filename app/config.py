import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file if present (no external deps needed)
_env_path = BASE_DIR / ".env"
if _env_path.exists():
    try:
        _content = _env_path.read_text(encoding="utf-8-sig")
    except Exception:
        _content = _env_path.read_text()
    for _line in _content.splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ[_k.strip()] = _v.strip()

class Settings:
    APP_NAME: str = "Creator Forge Internal Ops"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"

    # Database
    _db_url = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR}/creator_forge.db")
    if _db_url.startswith("postgres://"):
        _db_url = _db_url.replace("postgres://", "postgresql://", 1)
    if _db_url.startswith("postgresql://") and not _db_url.startswith("postgresql+"):
        try:
            import psycopg2  # noqa: F401
        except ImportError:
            try:
                import pg8000  # noqa: F401
                _db_url = _db_url.replace("postgresql://", "postgresql+pg8000://", 1)
            except ImportError:
                print("[CONFIG] Neither psycopg2 nor pg8000 installed. Falling back to local SQLite.")
                _db_url = f"sqlite:///{BASE_DIR}/creator_forge.db"
    DATABASE_URL: str = _db_url



    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-this-in-production-internal-ops-only")

    # Safety Controls
    DAILY_SEND_LIMIT_DEFAULT: int = int(os.getenv("DAILY_SEND_LIMIT", "10"))
    AUTO_SEND_ENABLED: bool = False   # Never auto-send; always require human approval
    MIN_FOLLOWERS_THRESHOLD: int = 100_000
    MIN_ENGAGEMENT_SCORE: float = 3.0  # minimum quality score (0-10)

    # AI
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    TOGETHER_API_KEY: str = os.getenv("TOGETHER_API_KEY", "")
    APIFY_API_KEY: str = os.getenv("APIFY_API_KEY", "")
    APIFY_YOUTUBE_EMAIL_ACTOR: str = os.getenv(
        "APIFY_YOUTUBE_EMAIL_ACTOR",
        "dataovercoffee~youtube-channel-business-email-scraper",
    )
    APIFY_INSTAGRAM_EMAIL_ACTOR: str = os.getenv(
        "APIFY_INSTAGRAM_EMAIL_ACTOR",
        "scrapers-hub~instagram-profile-email-scraper",
    )
    ACTIVE_AI_PROVIDER: str = os.getenv("ACTIVE_AI_PROVIDER", "openai")
    AI_MODEL: str = "gpt-4o"

    # Email / Outreach (stubs — real keys go in .env)
    SENDGRID_API_KEY: str = os.getenv("SENDGRID_API_KEY", "")
    FROM_EMAIL: str = os.getenv("FROM_EMAIL", "partnerships@yourcompany.com")
    FROM_NAME: str = os.getenv("FROM_NAME", "Creator Partnerships Team")
    GOOGLE_EMAIL: str = os.getenv("GOOGLE_EMAIL", "")
    GOOGLE_APP_PASSWORD: str = os.getenv("GOOGLE_APP_PASSWORD", "")
    ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "elishadamu97@gmail.com")

    # Integration stubs
    YOUTUBE_API_KEY: str = os.getenv("YOUTUBE_API_KEY", "")
    INSTAGRAM_ACCESS_TOKEN: str = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
    TIKTOK_API_KEY: str = os.getenv("TIKTOK_API_KEY", "")
    
    # Meta (Instagram) OAuth
    META_CLIENT_ID: str = os.getenv("META_CLIENT_ID", "YOUR_META_APP_ID_HERE")
    FRONTEND_URL: str = (os.getenv("FRONTEND_URL") or "https://creator-forge-frontend.vercel.app").rstrip("/")
    REDIRECT_URI: str = os.getenv("REDIRECT_URI", "")

settings = Settings()

