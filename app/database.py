from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings, BASE_DIR

fallback_sqlite_url = "sqlite:///:memory:"

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
    if ":memory:" in url:
        return create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=False,
        )
    return create_engine(
        url,
        connect_args={"check_same_thread": False},
        echo=False,
    )


def get_working_engine():
    db_url = settings.DATABASE_URL
    if db_url and ("postgres" in db_url or "postgresql" in db_url):
        try:
            eng = create_configured_engine(db_url)
            from sqlalchemy import text
            with eng.connect() as conn:
                conn.execute(text("SELECT 1"))
            return eng
        except Exception as _e:
            print(f"[DB INIT] PostgreSQL connection failed ({_e}). Falling back to in-memory database.")
            return create_configured_engine(fallback_sqlite_url)
    return create_configured_engine(db_url or fallback_sqlite_url)

engine = get_working_engine()


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
    from app.models import creator, campaign, outreach, audit, project, niche, workflow_state  # noqa: F401 — registers models
    from sqlalchemy import text
    try:
        # Always run create_all to ensure all registered tables exist (idempotent)
        Base.metadata.create_all(bind=engine)

        # Migration: ensure campaign_kit column exists on validation_campaigns
        try:
            with engine.connect() as conn:
                is_pg = "postgresql" in str(engine.url) or "postgres" in str(engine.url)
                if is_pg:
                    conn.execute(text("ALTER TABLE validation_campaigns ADD COLUMN IF NOT EXISTS campaign_kit JSONB DEFAULT '{}'::jsonb"))
                else:
                    # SQLite: check if column exists
                    col_info = conn.execute(text("PRAGMA table_info(validation_campaigns)")).fetchall()
                    col_names = [c[1] for c in col_info]
                    if "campaign_kit" not in col_names:
                        conn.execute(text("ALTER TABLE validation_campaigns ADD COLUMN campaign_kit JSON DEFAULT '{}'"))
                conn.commit()
        except Exception as _mig_err:
            print(f"[DB INIT] Column migration notice: {_mig_err}")
    except Exception as e:
        print(f"[DB INIT] Database connection failed: {e}.")
        print("[DB INIT] Gracefully falling back to in-memory database to keep service online.")
        engine = create_configured_engine(fallback_sqlite_url)
        SessionLocal.configure(bind=engine)
        Base.metadata.create_all(bind=engine)
        try:
            with engine.connect() as conn:
                col_info = conn.execute(text("PRAGMA table_info(validation_campaigns)")).fetchall()
                col_names = [c[1] for c in col_info]
                if "campaign_kit" not in col_names:
                    conn.execute(text("ALTER TABLE validation_campaigns ADD COLUMN campaign_kit JSON DEFAULT '{}'"))
                conn.commit()
        except Exception:
            pass
    
    # Auto-seed the 'default' campaign if missing
    from app.models.campaign import Campaign
    from app.models.niche import TargetNiche
    from app.models.creator import Creator
    from app.models.project import CoLaunchProject
    from app.models.workflow_state import WorkflowState
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
        
        # Auto-seed default target niches if missing
        niche_count = db.query(TargetNiche).count()
        if niche_count == 0:
            print("[DB INIT] Seeding default target niches in database...")
            DEFAULT_NICHES = [
                # Active defaults
                ("Tech", "tech", True, "14.2k"),
                ("Software", "tech", True, "9.8k"),
                ("SaaS", "tech", True, "6.4k"),
                ("Fintech", "business", True, "5.1k"),
                ("Productivity", "business", True, "11.3k"),
                # Available defaults
                ("AI Tools", "tech", False, "8.7k"),
                ("Creator Economy", "creative", False, "7.5k"),
                ("Gaming", "creative", False, "22.1k"),
                ("Fitness & Health", "lifestyle", False, "13.9k"),
                ("E-Commerce", "business", False, "8.2k"),
                ("Finance", "business", False, "6.9k"),
                ("Crypto & Web3", "business", False, "4.8k"),
                ("Design & Creative", "creative", False, "9.1k"),
                ("Education", "lifestyle", False, "10.5k"),
                ("Beauty & Lifestyle", "lifestyle", False, "16.7k"),
                ("Marketing", "business", False, "8.4k"),
            ]
            for name, cat, active, cnt in DEFAULT_NICHES:
                slug_id = name.lower().replace(" & ", "-").replace(" ", "-")
                db.add(TargetNiche(
                    id=slug_id,
                    name=name,
                    category=cat,
                    is_active=active,
                    count=cnt,
                ))
            db.commit()
            print("[DB INIT] Seeding default target niches completed.")

        # Sync creators from MongoDB Atlas into memory if present
        if db.query(Creator).count() == 0:
            try:
                from app.mongodb import get_collection
                coll = get_collection("creators")
                if coll is not None:
                    mongo_creators = list(coll.find({}))
                    if mongo_creators:
                        import json
                        from datetime import datetime
                        creator_cols = {c.name for c in Creator.__table__.columns}
                        for doc in mongo_creators:
                            r = dict(doc)
                            r.pop("_id", None)
                            if isinstance(r.get("niche"), str):
                                try:
                                    r["niche"] = json.loads(r["niche"])
                                except Exception:
                                    r["niche"] = [r["niche"]]
                            for dt_field in ["created_at", "updated_at"]:
                                if r.get(dt_field) and isinstance(r[dt_field], str):
                                    try:
                                        r[dt_field] = datetime.fromisoformat(r[dt_field])
                                    except Exception:
                                        r[dt_field] = datetime.utcnow()
                            filtered = {k: v for k, v in r.items() if k in creator_cols}
                            db.add(Creator(**filtered))
                        db.commit()
                        print(f"[DB INIT] Synced {len(mongo_creators)} creators from MongoDB into memory.")
            except Exception as m_err:
                print(f"[DB INIT] MongoDB creator sync notice: {m_err}")
                db.rollback()

        # Seed from data_backup.json as fail-safe fallback
        backup_file = BASE_DIR / "data_backup.json"
        if backup_file.exists():
            try:
                import json
                from datetime import datetime
                with open(backup_file, "r", encoding="utf-8") as bf:
                    bdata = json.load(bf)

                # 1. Creators
                if db.query(Creator).count() == 0:
                    b_creators = bdata.get("creators", [])
                    creator_cols = {c.name for c in Creator.__table__.columns}
                    for doc in b_creators:
                        r = dict(doc)
                        r.pop("_id", None)
                        if isinstance(r.get("niche"), str):
                            try: r["niche"] = json.loads(r["niche"])
                            except Exception: r["niche"] = [r["niche"]]
                        for dt_field in ["created_at", "updated_at"]:
                            if r.get(dt_field) and isinstance(r[dt_field], str):
                                try: r[dt_field] = datetime.fromisoformat(r[dt_field])
                                except Exception: r[dt_field] = datetime.utcnow()
                        filtered = {k: v for k, v in r.items() if k in creator_cols}
                        db.add(Creator(**filtered))
                    db.commit()
                    print(f"[DB INIT] Seeded {len(b_creators)} creators from data_backup.json.")

                # 2. Projects
                if db.query(CoLaunchProject).count() == 0:
                    b_projects = bdata.get("co_launch_projects", [])
                    proj_cols = {c.name for c in CoLaunchProject.__table__.columns}
                    for pdoc in b_projects:
                        pr = dict(pdoc)
                        pr.pop("_id", None)
                        if "creatorHandle" in pr and "creator_handle" not in pr: pr["creator_handle"] = pr["creatorHandle"]
                        if "creatorName" in pr and "creator_name" not in pr: pr["creator_name"] = pr["creatorName"]
                        if "creatorEmail" in pr and "creator_email" not in pr: pr["creator_email"] = pr["creatorEmail"]
                        if "creatorId" in pr and "creator_id" not in pr: pr["creator_id"] = pr["creatorId"]
                        if "productName" in pr and "product_name" not in pr: pr["product_name"] = pr["productName"]
                        if "productTagline" in pr and "product_tagline" not in pr: pr["product_tagline"] = pr["productTagline"]
                        if "selectedConcept" in pr and "selected_concept" not in pr: pr["selected_concept"] = pr["selectedConcept"]
                        if "metadataInfo" in pr and "metadata_info" not in pr: pr["metadata_info"] = pr["metadataInfo"]
                        if "presaleTarget" in pr and "presale_target" not in pr: pr["presale_target"] = pr["presaleTarget"]
                        for dt_field in ["created_at", "updated_at", "portal_link_sent_at"]:
                            if pr.get(dt_field) and isinstance(pr[dt_field], str):
                                try: pr[dt_field] = datetime.fromisoformat(pr[dt_field])
                                except Exception: pr[dt_field] = datetime.utcnow()
                        filtered_p = {k: v for k, v in pr.items() if k in proj_cols}
                        db.add(CoLaunchProject(**filtered_p))
                    db.commit()
                    print(f"[DB INIT] Seeded {len(b_projects)} projects from data_backup.json.")

                # 3. Workflow State
                ws_row = db.query(WorkflowState).filter(WorkflowState.id == "default").first()
                if not ws_row:
                    ws_row = WorkflowState(
                        id="default",
                        active_section="section1",
                        active_step=6,
                        default_pass_price=199.0,
                        cobuilder_pass_price=199.0,
                        extra_state={"default_pass_price": 199.0, "cobuilder_pass_price": 199.0}
                    )
                    db.add(ws_row)
                    db.commit()
                    print("[DB INIT] Seeded default workflow state with 199.0 pass fee.")
                else:
                    cur_extra = dict(ws_row.extra_state or {})
                    cur_extra["default_pass_price"] = 199.0
                    cur_extra["cobuilder_pass_price"] = 199.0
                    ws_row.extra_state = cur_extra
                    ws_row.default_pass_price = 199.0
                    ws_row.cobuilder_pass_price = 199.0
                    db.commit()
            except Exception as b_err:
                print(f"[DB INIT] Fail-safe backup seed notice: {b_err}")
                db.rollback()
    except Exception as e:
        print(f"[DB INIT] Warning: Failed to seed defaults: {e}")
        db.rollback()
    finally:
        db.close()

