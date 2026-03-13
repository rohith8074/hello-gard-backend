import asyncio
import httpx
import os
import certifi
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()
api_key = os.getenv("LYZR_API_KEY")
mongo_uri = os.getenv("MONGODB_URI")
db_name = os.getenv("MONGODB_DATABASE", "hellogard_db")
base_url = "https://voice-livekit.studio.lyzr.ai/v1"

# Setup MotorClient adding tlsCAFile=certifi.where() because certs sometimes cause AsyncIoMotor failures hanging locally
async def test():
    client = AsyncIOMotorClient(mongo_uri, tlsCAFile=certifi.where())
    db = client[db_name]

    doc = await db["sessions"].find_one({"session_id": "web_a3e73b7a1aa6"})
    if not doc:
        print("Session doc not found.")
        return
    lyzr_sid = doc.get("lyzr_session_id")
    print(f"Mapped local session 'web_a3e73b7a1aa6' to Lyzr ID: {lyzr_sid}")

    audio_url = f"{base_url}/transcripts/{lyzr_sid}/audio"
    print(f"Fetching from: {audio_url}")
    async with httpx.AsyncClient() as c2:
        resp = await c2.get(audio_url, headers={"x-api-key": api_key}, timeout=15.0)
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            print("Audio fetch returned 200 SUCCESS.")
        else:
            print(resp.text)

asyncio.run(test())
