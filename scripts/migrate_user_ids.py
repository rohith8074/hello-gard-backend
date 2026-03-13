"""
Migration: rename user_XXX → HG_XXX in all MongoDB collections.
Run from gard-backend/: python3 -m scripts.migrate_user_ids
"""
import asyncio
import re
from app.database import get_database, connect_to_mongo

# All fields across all collections that may hold a user_XXX id
FIELD_MAP = {
    "users":               ["user_id"],
    "calls":               ["user_id", "caller_id"],
    "transcripts":         ["user_id", "userId"],
    "escalation_tickets":  ["user_id"],
    "sales_leads":         ["user_id"],
    "security_events":     ["user_id"],
    "dashboard_metrics":   [],          # no user_id field
}

_PATTERN = re.compile(r"^user_(\d+)$")

def rename(val: str) -> str | None:
    m = _PATTERN.match(val or "")
    return f"HG_{m.group(1)}" if m else None


async def migrate():
    await connect_to_mongo()
    db = get_database()
    total = 0

    for collection, fields in FIELD_MAP.items():
        if not fields:
            continue
        docs = await db[collection].find({}).to_list(length=10_000)
        for doc in docs:
            updates = {}
            for field in fields:
                old_val = doc.get(field)
                if isinstance(old_val, str):
                    new_val = rename(old_val)
                    if new_val:
                        updates[field] = new_val
            if updates:
                await db[collection].update_one(
                    {"_id": doc["_id"]},
                    {"$set": updates}
                )
                total += 1
                print(f"  [{collection}] {doc['_id']} → {updates}")

    print(f"\n✅ Migration complete — {total} documents updated.")


if __name__ == "__main__":
    asyncio.run(migrate())
