"""
One-shot script: fetch audio for the latest conversation from Lyzr and save to call_audios.
Run from gard-backend/: python3 -m scripts.fetch_latest_audio
"""
import asyncio
import httpx
from bson.binary import Binary
from datetime import datetime
from app.database import get_database, connect_to_mongo
from app.config import settings


async def fetch_latest_audio():
    await connect_to_mongo()
    db = get_database()

    # 1. Find the latest transcript that has a lyzrSessionId
    transcript = await db["transcripts"].find_one(
        {"lyzrSessionId": {"$exists": True, "$ne": None}},
        sort=[("timestamp", -1)]
    )

    if not transcript:
        print("❌ No transcript with a lyzrSessionId found.")
        return

    local_sid  = transcript.get("sessionId") or transcript.get("session_id")
    lyzr_sid   = transcript.get("lyzrSessionId") or transcript.get("lyzr_session_id")

    print(f"📋 Latest transcript found")
    print(f"   local_session_id : {local_sid}")
    print(f"   lyzr_session_id  : {lyzr_sid}")

    if not lyzr_sid:
        print("❌ lyzrSessionId is empty — cannot fetch audio.")
        return

    # 2. Check if audio already exists
    existing = await db["call_audios"].find_one({"session_id": local_sid})
    if existing:
        print(f"✅ Audio already saved for session {local_sid}. Nothing to do.")
        return

    # 3. Fetch audio from Lyzr
    audio_url = f"{settings.LYZR_VOICE_BASE}/transcripts/{lyzr_sid}/audio"
    print(f"\n🎵 Fetching audio from: {audio_url}")

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            audio_url,
            headers={"x-api-key": settings.LYZR_API_KEY},
            timeout=30.0
        )

    print(f"   HTTP status : {resp.status_code}")
    print(f"   Content-Type: {resp.headers.get('Content-Type', 'unknown')}")
    print(f"   Size        : {len(resp.content)} bytes")

    if resp.status_code != 200:
        print(f"\n❌ Lyzr returned {resp.status_code}.")
        print(f"   Response body: {resp.text[:300]}")
        print("\n💡 Possible reasons:")
        print("   - Audio storage is not enabled for web/LiveKit sessions in your Lyzr plan")
        print("   - The session has expired and audio was purged")
        print("   - The lyzrSessionId doesn't match an audio recording")
        return

    # 4. Save to call_audios
    audio_doc = {
        "session_id":      local_sid,
        "lyzr_session_id": lyzr_sid,
        "audio_data":      Binary(resp.content),
        "content_type":    resp.headers.get("Content-Type", "audio/ogg"),
        "created_at":      datetime.now().isoformat()
    }
    await db["call_audios"].insert_one(audio_doc)
    print(f"\n✅ Audio saved to 'call_audios' for session {local_sid}")
    print(f"   {len(resp.content):,} bytes stored as Binary")


if __name__ == "__main__":
    asyncio.run(fetch_latest_audio())
