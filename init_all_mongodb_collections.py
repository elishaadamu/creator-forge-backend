import os
import json
import sys
from pathlib import Path
from pymongo import MongoClient, ReplaceOne

BASE_DIR = Path(__file__).resolve().parent

# Load .env file
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

MONGODB_URI = os.getenv("MONGODB_URI", os.getenv("MONGO_URL", "")).strip()
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "creator_forge").strip()

if not MONGODB_URI:
    print("[ERROR] MONGODB_URI is not set in backend/.env!")
    sys.exit(1)

print(f"Connecting to MongoDB database '{MONGODB_DB_NAME}'...")
try:
    client = MongoClient(
        MONGODB_URI,
        serverSelectionTimeoutMS=8000,
        connectTimeoutMS=10000,
        retryWrites=True,
    )
    client.admin.command('ping')
    print("✓ Successfully authenticated and connected to MongoDB cluster!")
except Exception as e:
    print(f"[CONNECTION ERROR] Could not connect to MongoDB: {e}")
    sys.exit(1)

db = client[MONGODB_DB_NAME]

# The complete list of 28 schema tables/collections
SCHEMA_COLLECTIONS = [
    "analyses",
    "audit_logs",
    "autonomous_campaigns",
    "campaigns",
    "co_launch_projects",
    "contacts",
    "content_samples",
    "creator_campaign_tasks",
    "creators",
    "decks",
    "follow_ups",
    "media_images",
    "metrics_snapshots",
    "outreach_messages",
    "partnerships",
    "post_suggestions",
    "product_recommendations",
    "replies",
    "reviews",
    "suppression_list",
    "target_niches",
    "threads",
    "user_profiles",
    "validation_campaigns",
    "validation_gate_decisions",
    "validation_plans",
    "validation_telemetry",
    "workflow_states",
]

existing_collections = set(db.list_collection_names())
print(f"\nChecking all 28 collections in '{MONGODB_DB_NAME}'...")

# 1. Ensure all 28 collections are explicitly created
created_count = 0
for col_name in SCHEMA_COLLECTIONS:
    if col_name not in existing_collections:
        try:
            db.create_collection(col_name)
            created_count += 1
            print(f"  + Created collection: '{col_name}'")
        except Exception as e:
            print(f"  - Notice for '{col_name}': {e}")
    else:
        print(f"  ✓ Collection exists: '{col_name}'")

# 2. Collections ready in MongoDB Atlas
print("  ✓ All collections verified in MongoDB Atlas.")

# 3. Seed default target niches if empty
target_niches_coll = db["target_niches"]
if target_niches_coll.count_documents({}) == 0:
    DEFAULT_NICHES = [
        ("Tech", "tech", True, "14.2k"),
        ("Software", "tech", True, "9.8k"),
        ("SaaS", "tech", True, "6.4k"),
        ("Fintech", "business", True, "5.1k"),
        ("Productivity", "business", True, "11.3k"),
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
    niche_docs = []
    for name, cat, active, cnt in DEFAULT_NICHES:
        slug_id = name.lower().replace(" & ", "-").replace(" ", "-")
        niche_docs.append({
            "_id": slug_id,
            "id": slug_id,
            "name": name,
            "category": cat,
            "is_active": active,
            "count": cnt,
        })
    target_niches_coll.insert_many(niche_docs, ordered=False)
    print(f"  ✓ Seeded {len(niche_docs)} default niches in 'target_niches'")

# 4. Create useful indexes for fast lookups
db.creators.create_index("handle", unique=True, sparse=True)
db.creators.create_index("status")
db.creators.create_index("platform")
db.contacts.create_index("creator_id")
db.outreach_messages.create_index("creator_id")
db.threads.create_index("creator_id")
db.replies.create_index("thread_id")
db.audit_logs.create_index("created_at")

# 5. Summary of all 28 collections and their document counts
all_current = sorted(db.list_collection_names())
print("\n========================================================")
print(f" All 28 MongoDB Collections in '{MONGODB_DB_NAME}':")
print("========================================================")
for idx, cname in enumerate(SCHEMA_COLLECTIONS, 1):
    doc_count = db[cname].count_documents({})
    status_icon = "🟢" if doc_count > 0 else "⚪"
    print(f"  {idx:2d}. {status_icon} {cname:28s} : {doc_count:4d} docs")
print("========================================================\n")
