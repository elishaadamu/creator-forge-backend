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
    # Ping to verify authentication and connectivity
    client.admin.command('ping')
    print("✓ Successfully authenticated and connected to MongoDB cluster!")
except Exception as e:
    print(f"[CONNECTION ERROR] Could not connect to MongoDB: {e}")
    sys.exit(1)

db = client[MONGODB_DB_NAME]
backup_file = BASE_DIR / "data_backup.json"

if not backup_file.exists():
    print(f"[ERROR] Backup file not found at {backup_file}")
    sys.exit(1)

with open(backup_file, "r", encoding="utf-8") as f:
    backup_data = json.load(f)

total_tables = len(backup_data)
print(f"\nFound {total_tables} tables in backup. Pushing to MongoDB collections...")

pushed_summary = {}

for table_name, records in backup_data.items():
    if not records or not isinstance(records, list):
        continue

    coll = db[table_name]
    operations = []

    for item in records:
        doc = dict(item)
        
        # Ensure _id is present
        if "id" in doc:
            doc["_id"] = doc["id"]
        
        # Parse JSON string fields to native MongoDB types
        for key in ["niche", "tags", "metadata", "extra_data", "details"]:
            if key in doc and isinstance(doc[key], str):
                try:
                    doc[key] = json.loads(doc[key])
                except Exception:
                    pass

        # Upsert document by _id
        if "_id" in doc:
            operations.append(ReplaceOne({"_id": doc["_id"]}, doc, upsert=True))

    if operations:
        res = coll.bulk_write(operations, ordered=False)
        count = (res.upserted_count or 0) + (res.modified_count or 0) + (res.matched_count or 0)
        pushed_summary[table_name] = len(operations)
        print(f"  ✓ [{table_name}] Pushed {len(operations)} documents (Upserted: {res.upserted_count}, Modified: {res.modified_count})")
    else:
        print(f"  - [{table_name}] 0 records to push.")

print("\n==========================================")
print(" MongoDB Push Complete!")
print(f" Total collections updated: {len(pushed_summary)}")
for coll_name, count in pushed_summary.items():
    print(f"   • {coll_name}: {count} documents")
print("==========================================\n")
