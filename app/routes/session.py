import asyncio
import httpx
import uuid
import logging
import pydantic
from datetime import datetime
from fastapi import APIRouter, HTTPException, Body
from app.config import settings
from app.database import get_database

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory session store: local_session_id -> session metadata
sessions = {}


class SessionStartRequest(pydantic.BaseModel):
    user_id: str = None

@router.post("/session/start")
async def start_web_session(body: SessionStartRequest = Body(default_factory=SessionStartRequest)):
    """
    Creates a Lyzr LiveKit session and returns LiveKit credentials to the frontend.
    The frontend uses these directly with the livekit-client SDK.
    """
    local_session_id = f"web_{uuid.uuid4().hex[:12]}"
    agent_id = settings.LYZR_AGENT_ID
    user_id = body.user_id

    if not agent_id:
        raise HTTPException(status_code=500, detail="LYZR_Managerial_Agent_ID is not set in .env")
    if not settings.LYZR_API_KEY:
        raise HTTPException(status_code=500, detail="LYZR_API_KEY is not set in .env")

    # Only send agentId + userIdentity — let Lyzr generate sessionId (must be UUID)
    payload = {
        "agentId": agent_id,
        "userIdentity": local_session_id,
    }

    print(f"\033[94m\033[1m🔗 [LYZR]\033[0m Starting session → POST {settings.LYZR_VOICE_BASE}/sessions/start | agentId={agent_id}")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.LYZR_VOICE_BASE}/sessions/start",
            headers={"x-api-key": settings.LYZR_API_KEY, "Content-Type": "application/json"},
            json=payload,
            timeout=20.0
        )

    if response.status_code != 200:
        error_detail = response.text
        try:
            error_json = response.json()
            error_detail = error_json.get("error") or error_json.get("detail") or response.text
        except Exception:
            pass
        logger.error(f"Lyzr session start failed ({response.status_code}): {response.text}")
        raise HTTPException(
            status_code=502,
            detail=f"Lyzr API error ({response.status_code}): {error_detail}"
        )

    lyzr_data = response.json()
    user_token   = lyzr_data.get("userToken")
    room_name    = lyzr_data.get("roomName")
    lyzr_sid     = lyzr_data.get("sessionId")
    livekit_url  = lyzr_data.get("livekitUrl")

    # Store in memory for session/end + transcript polling
    sessions[local_session_id] = {
        "lyzrSessionId": lyzr_sid,
        "roomName": room_name,
        "agentId": agent_id,
        "userId": user_id,
        "startTime": datetime.now().isoformat(),
    }
    print(f"\033[92m\033[1m✅ [SESSION]\033[0m Started | local={local_session_id} | lyzr={lyzr_sid} | user={user_id}")

    # Persist session metadata to MongoDB
    try:
        db = get_database()
        await db["sessions"].insert_one({
            "session_id": local_session_id,
            "lyzr_session_id": lyzr_sid,
            "agent_id": agent_id,
            "user_id": user_id,
            "room_name": room_name,
            "start_time": datetime.now().isoformat(),
            "status": "active",
            "type": "web",
        })
        print(f"\033[96m\033[1m🍃 [MONGODB]\033[0m Session persisted: {local_session_id}")
    except Exception as e:
        logger.error(f"Failed to persist session: {e}")

    return {
        "sessionId": local_session_id,
        "lyzrSessionId": lyzr_sid,
        "userToken": user_token,
        "roomName": room_name,
        "livekitUrl": livekit_url,
    }


class SessionEndRequest(pydantic.BaseModel):
    transcript: list = []


@router.post("/session/end")
async def end_web_session(session_id: str, body: SessionEndRequest = Body(default_factory=SessionEndRequest)):
    """
    Ends the Lyzr LiveKit session, saves the transcript collected by the frontend
    via LiveKit TranscriptionReceived, and triggers post-call analysis.
    """
    session_data = sessions.get(session_id)
    if not session_data:
        # Try to recover from DB
        try:
            db = get_database()
            doc = await db["sessions"].find_one({"session_id": session_id}, {"_id": 0})
            if doc:
                session_data = {
                    "lyzrSessionId": doc.get("lyzr_session_id"),
                    "roomName": doc.get("room_name"),
                    "agentId": doc.get("agent_id"),
                }
            else:
                raise HTTPException(status_code=404, detail="Session not found")
        except Exception:
            raise HTTPException(status_code=404, detail="Session not found")

    room_name = session_data.get("roomName")
    lyzr_sid  = session_data.get("lyzrSessionId")

    # 1. End the Lyzr LiveKit session
    try:
        async with httpx.AsyncClient() as client:
            end_resp = await client.post(
                f"{settings.LYZR_VOICE_BASE}/sessions/end",
                headers={"x-api-key": settings.LYZR_API_KEY, "Content-Type": "application/json"},
                json={"roomName": room_name},
                timeout=10.0
            )
        if end_resp.status_code not in (200, 204):
            logger.warning(f"Lyzr session end returned {end_resp.status_code}: {end_resp.text}")
    except Exception as e:
        logger.warning(f"Lyzr session end call failed: {e}")

    # 2. Use transcript sent from frontend (captured via LiveKit TranscriptionReceived).
    #    Lyzr REST /transcripts/{id} returns 404 during and immediately after calls.
    chat_history = []
    for turn in body.transcript:
        role = turn.get("role", "user") if isinstance(turn, dict) else getattr(turn, "role", "user")
        text = turn.get("text", "") if isinstance(turn, dict) else getattr(turn, "text", "")
        timestamp = turn.get("timestamp", datetime.now().isoformat()) if isinstance(turn, dict) else getattr(turn, "timestamp", datetime.now().isoformat())
        if text:
            chat_history.append({"role": role, "content": text, "timestamp": timestamp})
            label = "\033[92m[AI]\033[0m  " if role == "agent" else "\033[94m[USER]\033[0m"
            print(f"  {label} {text[:100]}")

    print(f"\033[96m\033[1m🍃 [SESSION END]\033[0m {len(chat_history)} transcript turns received from frontend for {session_id}")

    # 3. Save transcript to MongoDB
    if chat_history:
        try:
            db = get_database()
            await db["transcripts"].insert_one({
                "sessionId": session_id,
                "lyzrSessionId": lyzr_sid,
                "userId": session_data.get("userId"),
                "timestamp": datetime.now().isoformat(),
                "history": chat_history,
                "type": "web",
            })
            print(f"\033[96m\033[1m🍃 [MONGODB]\033[0m Transcript saved for session {session_id}")
        except Exception as e:
            logger.error(f"Failed to save transcript: {e}")

        # 4. Trigger post-call analysis (fire-and-forget with error logging)
        try:
            from app.routes.post_call import process_post_call

            async def _run_post_call(sid: str):
                try:
                    await process_post_call(sid)
                    print(f"\033[95m\033[1m📊 [POST-CALL]\033[0m Analysis complete for {sid}")
                except Exception as exc:
                    logger.error(f"Post-call analysis failed for {sid}: {exc}", exc_info=True)

            asyncio.create_task(_run_post_call(session_id))
            print(f"\033[95m\033[1m📊 [POST-CALL]\033[0m Analysis triggered for {session_id}")
        except Exception as e:
            logger.error(f"Failed to trigger post-call: {e}")

    # 5. Update session status in MongoDB
    try:
        db = get_database()
        await db["sessions"].update_one(
            {"session_id": session_id},
            {"$set": {"status": "completed", "end_time": datetime.now().isoformat()}}
        )
    except Exception as e:
        logger.error(f"Failed to update session status: {e}")

    # 6. Clean up memory
    sessions.pop(session_id, None)

    return {"status": "success", "turns": len(chat_history)}


@router.get("/session/active-count")
async def get_active_session_count():
    """Returns count of currently active LiveKit sessions."""
    return {"success": True, "count": len(sessions)}


@router.get("/session/transcript/{session_id}")
async def get_live_transcript(session_id: str):
    """
    Polls Lyzr for the latest transcript turns during a live call.
    Called by the frontend every 3 seconds to show live transcription.
    """
    session_data = sessions.get(session_id)
    if not session_data:
        return {"turns": [], "active": False}

    lyzr_sid = session_data.get("lyzrSessionId")
    if not lyzr_sid:
        return {"turns": [], "active": True}

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{settings.LYZR_VOICE_BASE}/transcripts/{lyzr_sid}",
                headers={"x-api-key": settings.LYZR_API_KEY},
                timeout=8.0
            )

        # Lyzr returns 404 during live calls — transcripts only finalize after session ends.
        # Live transcription is handled client-side via Web Speech API + LiveKit data channel.
        if resp.status_code != 200:
            return {"turns": [], "active": True}

        raw = resp.json()
        tx_data = raw.get("transcript", raw)
        chat_history_raw = tx_data.get("chatHistory", tx_data.get("messages", tx_data.get("turns", [])))

        turns = []
        for msg in chat_history_raw:
            raw_role = msg.get("role", msg.get("speaker", "user"))
            text = msg.get("content", msg.get("text", msg.get("message", "")))
            if not text:
                continue
            role = "agent" if str(raw_role).lower() in ("agent", "assistant") else "user"
            turns.append({"role": role, "text": text})

        return {"turns": turns, "active": True}

    except Exception as e:
        logger.warning(f"Live transcript poll failed for {session_id}: {e}")
        return {"turns": [], "active": True}
