from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings, BASE_DIR

fallback_sqlite_url = f"sqlite:///{BASE_DIR}/creator_forge.db"

def create_configured_engine(url: str):
    if "postgresql" in url or "postgres" in url:
        return create_engine(
            url,
            pool_size=20,
            max_overflow=20,
            pool_timeout=30,
            pool_recycle=60,
            pool_pre_ping=True,
            connect_args={
                "connect_timeout": 10,
                "keepalives": 1,
                "keepalives_idle": 30,
                "keepalives_interval": 10,
                "keepalives_count": 5,
            },
            echo=False,
        )
    return create_engine(
        url,
        connect_args={"check_same_thread": False},
        echo=False,
    )


try:
    engine = create_configured_engine(settings.DATABASE_URL)
except Exception as _e:
    print(f"[DB INIT] PostgreSQL driver/connection error: {_e}. Falling back to local SQLite database.")
    engine = create_configured_engine(fallback_sqlite_url)


@event.listens_for(engine, "before_cursor_execute")
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    pass

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    global engine, SessionLocal
    from app.models import creator, campaign, outreach, audit, project  # noqa: F401 — registers models
    from sqlalchemy import text
    try:
        table_exists = False
        with engine.connect() as conn:
            try:
                conn.execute(text("SELECT 1 FROM creators LIMIT 1"))
                table_exists = True
            except Exception:
                pass

        if not table_exists:
            print("[DB INIT] Creating missing schema tables...")
            Base.metadata.create_all(bind=engine)
    except Exception as e:
        print(f"[DB INIT] Database connection failed: {e}.")
        print("[DB INIT] Gracefully falling back to local SQLite database to keep service online.")
        engine = create_configured_engine(fallback_sqlite_url)
        SessionLocal.configure(bind=engine)
        Base.metadata.create_all(bind=engine)
    
    # Auto-seed the 'default' campaign if missing
    from app.models.campaign import Campaign
    db = SessionLocal()
    try:
        default_campaign = db.query(Campaign).filter(Campaign.id == "default").first()
        if not default_campaign:
            print("[DB INIT] Seeding default campaign...")
            c = Campaign(
                id="default",
                name="Default Campaign",
                description="Default Creator Outreach Campaign",
                product_category="overall",
                status="active",
                daily_send_limit=10,
                require_human_approval=True,
                created_by="system"
            )
            db.add(c)
            db.commit()
            print("[DB INIT] Seeding default campaign completed.")
    except Exception as e:
        print(f"[DB INIT] Warning: Failed to seed default campaign: {e}")
        db.rollback()
    finally:
        db.close()
