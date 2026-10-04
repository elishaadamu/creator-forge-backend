import os
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.collection import Collection

logger = logging.getLogger("creator_forge.mongodb")

BASE_DIR = Path(__file__).resolve().parent.parent

def get_mongo_uri() -> str:
    uri = os.getenv("MONGODB_URI", os.getenv("MONGO_URL", "")).strip()
    if not uri:
        try:
            from app.config import settings
            uri = getattr(settings, "MONGODB_URI", "").strip()
        except Exception:
            pass
    return uri


_client: Optional[MongoClient] = None
_db: Optional[Database] = None

def get_mongo_client() -> Optional[MongoClient]:
    global _client
    if _client is not None:
        return _client

    uri = get_mongo_uri()
    if not uri:
        logger.warning("[MongoDB] MONGODB_URI not configured in .env.")
        return None

    try:
        _client = MongoClient(
            uri,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=10000,
            socketTimeoutMS=30000,
            maxPoolSize=50,
            minPoolSize=5,
            retryWrites=True
        )
        # Test connection with ping
        _client.admin.command('ping')
        logger.info("[MongoDB] Connected successfully to MongoDB cluster!")
        return _client
    except Exception as e:
        logger.error(f"[MongoDB] Failed to connect to MongoDB ({e}).")
        _client = None
        return None


def get_mongo_db() -> Optional[Database]:
    global _db
    if _db is not None:
        return _db

    client = get_mongo_client()
    if client is None:
        return None

    db_name = os.getenv("MONGODB_DB_NAME", "creator_forge").strip()
    _db = client[db_name]
    return _db


def get_collection(name: str) -> Optional[Collection]:
    db = get_mongo_db()
    if db is None:
        return None
    return db[name]


def check_mongo_connection() -> Dict[str, Any]:
    uri = get_mongo_uri()
    if not uri:
        return {
            "status": "not_configured",
            "message": "MONGODB_URI is not set in backend/.env. Please provide your MongoDB Atlas connection string."
        }
    try:
        client = get_mongo_client()
        if client:
            client.admin.command('ping')
            db = get_mongo_db()
            collections = db.list_collection_names() if db is not None else []
            return {
                "status": "connected",
                "database": os.getenv("MONGODB_DB_NAME", "creator_forge"),
                "collections": collections
            }
        return {"status": "disconnected", "message": "Could not connect to MongoDB."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


SCHEMA_COLLECTIONS = [
    "analyses", "audit_logs", "autonomous_campaigns", "campaigns",
    "co_launch_projects", "contacts", "content_samples", "creator_campaign_tasks",
    "creators", "decks", "follow_ups", "media_images", "metrics_snapshots",
    "outreach_messages", "partnerships", "post_suggestions", "product_recommendations",
    "replies", "reviews", "suppression_list", "target_niches", "threads",
    "user_profiles", "validation_campaigns", "validation_gate_decisions",
    "validation_plans", "validation_telemetry", "workflow_states",
]


def seed_from_backup_if_empty():
    """Seeds collections from backend/data_backup.json and ensures all 28 schema collections exist."""
    db = get_mongo_db()
    if db is None:
        return

    # 1. Ensure all 28 collections are explicitly present
    existing_colls = set(db.list_collection_names())
    for col_name in SCHEMA_COLLECTIONS:
        if col_name not in existing_colls:
            try:
                db.create_collection(col_name)
            except Exception:
                pass

    backup_file = BASE_DIR / "data_backup.json"
    if not backup_file.exists():
        return

    try:
        with open(backup_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        for table_name, rows in data.items():
            if not rows or not isinstance(rows, list):
                continue
            coll = db[table_name]
            if coll.count_documents({}) == 0:
                logger.info(f"[MongoDB] Seeding {len(rows)} records into collection '{table_name}'...")
                # Normalize documents (ensure 'id' is unique or mapped)
                docs = []
                for r in rows:
                    doc = dict(r)
                    if "id" in doc and "_id" not in doc:
                        doc["_id"] = doc["id"]
                    docs.append(doc)
                if docs:
                    coll.insert_many(docs, ordered=False)
                    logger.info(f"[MongoDB] Successfully seeded '{table_name}' ({len(docs)} documents).")
    except Exception as e:
        logger.warning(f"[MongoDB] Backup seed error: {e}")
