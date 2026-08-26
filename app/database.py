from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings, BASE_DIR

try:
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
        echo=False,
    )
except Exception as _e:
    print(f"[DB INIT] PostgreSQL driver/connection error: {_e}. Falling back to local SQLite database.")
    fallback_url = f"sqlite:///{BASE_DIR}/creator_forge.db"
    engine = create_engine(fallback_url, connect_args={"check_same_thread": False}, echo=False)



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
    from app.models import creator, campaign, outreach, audit  # noqa: F401 — registers models
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
