import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file if present (no external deps needed)
_env_path = BASE_DIR / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

class Settings:
    APP_NAME: str = "Creator Forge Internal Ops"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"

    # Database
    _db_url = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR}/creator_forge.db")
    if _db_url.startswith("postgres://"):
        _db_url = _db_url.replace("postgres://", "postgresql://", 1)
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
    NVIDIA_API_KEY: str = os.getenv("NVIDIA_API_KEY", "")
    AI_MODEL: str = "claude-sonnet-4-6"

    # Email / Outreach (stubs — real keys go in .env)
    SENDGRID_API_KEY: str = os.getenv("SENDGRID_API_KEY", "")
    FROM_EMAIL: str = os.getenv("FROM_EMAIL", "partnerships@yourcompany.com")
    FROM_NAME: str = os.getenv("FROM_NAME", "Creator Partnerships Team")

    # Integration stubs
    YOUTUBE_API_KEY: str = os.getenv("YOUTUBE_API_KEY", "")
    INSTAGRAM_ACCESS_TOKEN: str = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
    TIKTOK_API_KEY: str = os.getenv("TIKTOK_API_KEY", "")

    # Apify — enables accurate scraping for Instagram & TikTok
    APIFY_API_KEY: str = os.getenv("APIFY_API_KEY", "")


settings = Settings()
