import asyncio
import random
from datetime import datetime, timedelta
from app.database import get_database, connect_to_mongo

# Fixed customer data — must stay in sync with the Customer Registry in
# agent_prompts/GARD_Manager_Agent.md
CUSTOMERS = [
    {"user_id": "user_000", "name": "James Wilson",      "company": "Hospital Central",  "products_owned": ["sp50", "v3"],       "experience": "experienced"},
    {"user_id": "user_001", "name": "Mary Chen",          "company": "Global Logistics",  "products_owned": ["w3"],               "experience": "intermediate"},
    {"user_id": "user_002", "name": "Robert Miller",      "company": "Elite Security",    "products_owned": ["k5"],               "experience": "experienced"},
    {"user_id": "user_003", "name": "Patricia Garcia",    "company": "Metro Retail",      "products_owned": ["sp50"],             "experience": "intermediate"},
    {"user_id": "user_004", "name": "Michael Brown",      "company": "Tech Campus",       "products_owned": ["v3", "w3"],         "experience": "new"},
    {"user_id": "user_005", "name": "Jennifer Davis",     "company": "Hospital Central",  "products_owned": ["sp50", "k5"],       "experience": "intermediate"},
    {"user_id": "user_006", "name": "William Rodriguez",  "company": "Global Logistics",  "products_owned": ["yarbo"],            "experience": "new"},
    {"user_id": "user_007", "name": "Linda Martinez",     "company": "Elite Security",    "products_owned": ["sp50", "w3", "v3"], "experience": "experienced"},
    {"user_id": "user_008", "name": "David Hernandez",    "company": "Metro Retail",      "products_owned": ["k5"],               "experience": "new"},
    {"user_id": "user_009", "name": "Elizabeth Lopez",    "company": "Tech Campus",       "products_owned": ["sp50"],             "experience": "intermediate"},
    {"user_id": "user_010", "name": "Richard Gonzalez",   "company": "Hospital Central",  "products_owned": ["yarbo", "sp50"],    "experience": "experienced"},
    {"user_id": "user_011", "name": "Barbara Wilson",     "company": "Global Logistics",  "products_owned": ["v3"],               "experience": "new"},
]

# Experience level → approximate join date offset in days from today
EXPERIENCE_DAYS = {
    "new":          30,   # joined ~1 month ago
    "intermediate": 180,  # joined ~6 months ago
    "experienced":  400,  # joined ~13 months ago
}

EMAILS = {
    "James Wilson":     "james.wilson@hospitalcentral.com",
    "Mary Chen":        "mary.chen@globallogistics.com",
    "Robert Miller":    "robert.miller@elitesecurity.com",
    "Patricia Garcia":  "patricia.garcia@metroretail.com",
    "Michael Brown":    "michael.brown@techcampus.com",
    "Jennifer Davis":   "jennifer.davis@hospitalcentral.com",
    "William Rodriguez":"william.rodriguez@globallogistics.com",
    "Linda Martinez":   "linda.martinez@elitesecurity.com",
    "David Hernandez":  "david.hernandez@metroretail.com",
    "Elizabeth Lopez":  "elizabeth.lopez@techcampus.com",
    "Richard Gonzalez": "richard.gonzalez@hospitalcentral.com",
    "Barbara Wilson":   "barbara.wilson@globallogistics.com",
}

PHONES = {
    "James Wilson":     "+1 (555) 234-5678",
    "Mary Chen":        "+1 (555) 345-6789",
    "Robert Miller":    "+1 (555) 456-7890",
    "Patricia Garcia":  "+1 (555) 567-8901",
    "Michael Brown":    "+1 (555) 678-9012",
    "Jennifer Davis":   "+1 (555) 789-0123",
    "William Rodriguez":"+1 (555) 890-1234",
    "Linda Martinez":   "+1 (555) 901-2345",
    "David Hernandez":  "+1 (555) 012-3456",
    "Elizabeth Lopez":  "+1 (555) 123-4567",
    "Richard Gonzalez": "+1 (555) 234-5679",
    "Barbara Wilson":   "+1 (555) 345-6780",
}


async def populate_users():
    await connect_to_mongo()
    db = get_database()

    await db["users"].delete_many({})

    user_ids = []
    print("Creating user profiles...")
    now = datetime.now()

    for c in CUSTOMERS:
        days_ago = EXPERIENCE_DAYS[c["experience"]]
        joined_at = (now - timedelta(days=days_ago)).isoformat()

        user_doc = {
            "user_id":       c["user_id"],
            "name":          c["name"],
            "email":         EMAILS[c["name"]],
            "company":       c["company"],
            "joined_at":     joined_at,
            "last_active":   now.isoformat(),
            "products_owned": c["products_owned"],
            "phone":         PHONES[c["name"]],
        }
        await db["users"].insert_one(user_doc)
        user_ids.append(c["user_id"])

    print(f"Created {len(user_ids)} users. Mapping existing data...")

    # Map existing calls / tickets / leads to users with stable sequential IDs
    calls = await db["calls"].find({}).sort("processed_at", 1).to_list(None)
    for i, call in enumerate(calls):
        uid = user_ids[i % len(user_ids)]
        new_call_id = f"Call_ID{i}"
        await db["calls"].update_one(
            {"_id": call["_id"]},
            {"$set": {"user_id": uid, "call_id": new_call_id}}
        )

    tickets = await db["escalation_tickets"].find({}).sort("created_at", 1).to_list(None)
    for i, ticket in enumerate(tickets):
        uid = user_ids[i % len(user_ids)]
        new_ticket_id = f"Ticket_ID{i}"
        await db["escalation_tickets"].update_one(
            {"_id": ticket["_id"]},
            {"$set": {"user_id": uid, "ticket_id": new_ticket_id}}
        )

    leads = await db["sales_leads"].find({}).sort("detected_at", 1).to_list(None)
    for i, lead in enumerate(leads):
        uid = user_ids[i % len(user_ids)]
        new_lead_id = f"Sales_ID{i}"
        await db["sales_leads"].update_one(
            {"_id": lead["_id"]},
            {"$set": {"user_id": uid, "lead_id": new_lead_id}}
        )

    print("Mapping complete with human-readable IDs.")


if __name__ == "__main__":
    asyncio.run(populate_users())
