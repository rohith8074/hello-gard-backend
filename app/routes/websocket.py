import json
import ssl
import asyncio
import logging
import websockets
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.config import settings
from app.database import get_database

logger = logging.getLogger(__name__)
router = APIRouter()

# ANSI Colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RESET = "\033[0m"
BOLD = "\033[1m"

# Store active sessions
sessions = {}

async def log_interaction(session_id, role, content, agent_id=None):
    """Logs a single turn of conversation to MongoDB in real-time."""
    try:
        db = get_database()
        await db["interaction_logs"].insert_one({
            "session_id": session_id,
            "agent_id": agent_id,
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        print(f"\033[96m\033[1m🍃 [MONGODB]\033[0m Message turn captured in collection 'interaction_logs'")
    except Exception as e:
        logger.error(f"Real-time log failure: {e}")

async def save_transcript(history, sid, lyzr_sid=None):
    """Saves the conversation history to JSON file AND MongoDB."""
    if not history:
        return
    
    timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
    clean_sid = str(sid).replace(":", "_")
    
    data = {
        "sessionId": sid,
        "lyzrSessionId": lyzr_sid,
        "timestamp": datetime.now().isoformat(),
        "history": history,
        "type": "web" if str(sid).startswith("web") else "phone"
    }

    # 1. Save to JSON for local backup
    try:
        import os
        os.makedirs("transcripts", exist_ok=True)
        filename = f"transcripts/chat_{clean_sid}_{timestamp_str}.json"
        with open(filename, "w") as f:
            json.dump(data, f, indent=4)
        logger.info(f"Local backup saved: {filename}")
    except Exception as e:
        logger.error(f"Failed to save local JSON: {e}")

    # 2. Save to MongoDB
    try:
        db = get_database()
        transcripts_collection = db["transcripts"]
        await transcripts_collection.insert_one(data)
        print(f"\033[96m\033[1m🍃 [MONGODB]\033[0m Transcript archived to collection 'transcripts'")
    except Exception as e:
        logger.error(f"MongoDB Save Error: {e}")

async def trigger_post_call(session_id: str):
    """Fire-and-forget post-call processing."""
    try:
        from app.routes.post_call import process_post_call
        await process_post_call(session_id)
        print(f"\033[95m\033[1m📊 [POST-CALL]\033[0m Analysis complete for {session_id}")
    except Exception as e:
        logger.error(f"Post-call processing failed for {session_id}: {e}")

@router.websocket("/ws/web")
async def web_websocket_proxy(websocket: WebSocket, sessionId: str, lyzrWs: str):
    """
    A Transparent Proxy between the Browser and Lyzr.
    It captures transcripts for logging while piping audio at low latency.
    """
    await websocket.accept()
    stream_sid = f"WEB_{sessionId}"
    
    if sessionId not in sessions:
        sessions[sessionId] = {"history": [], "lyzrSid": None}
    lyzr_sid = sessions[sessionId].get("lyzrSid")
    print(f"\n{GREEN}{BOLD}🌐 [NATIVE WEB CALL]{RESET} Local ID: {sessionId} | Lyzr ID: {lyzr_sid}")
    
    try:
        # Connect to Lyzr's Voice WebSocket
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        async with websockets.connect(lyzrWs, ssl=ssl_context) as lyzr_socket:
            
            # Bridge Browser -> Lyzr
            async def browser_to_lyzr():
                try:
                    while True:
                        msg = await websocket.receive_text()
                        await lyzr_socket.send(msg)
                except Exception:
                    pass

            # Bridge Lyzr -> Browser (and capture transcripts)
            async def lyzr_to_browser():
                try:
                    while True:
                        msg = await lyzr_socket.recv()
                        data = json.loads(msg)
                        
                        # Intercept Transcripts for logging
                        if data.get("type") == "transcript":
                            role = data.get("role", "unknown")
                            text = data.get("text", "")
                            if text:
                                timestamp = datetime.now().isoformat()
                                sessions[sessionId]["history"].append({
                                    "role": role,
                                    "content": text,
                                    "timestamp": timestamp
                                })
                                # NEW: Real-time logging to MongoDB
                                agent_id = sessions[sessionId].get("agentId") # Trying to get agentId if available
                                asyncio.create_task(log_interaction(sessionId, role, text, agent_id=agent_id))
                                print(f"[{sessionId}] {YELLOW if role == 'agent' else GREEN}{BOLD}{role.upper()}:{RESET} {text}")
                        
                        # Pipe everything back to browser
                        await websocket.send_text(msg)
                except Exception:
                    pass

            # Run both bridges concurrently
            await asyncio.gather(browser_to_lyzr(), lyzr_to_browser())

    except Exception as e:
        logger.error(f"Proxy Error: {str(e)}")
    finally:
        lyzr_sid = sessions[sessionId].get("lyzrSid")
        await save_transcript(sessions[sessionId]["history"], sessionId, lyzr_sid=lyzr_sid)
        
        # NEW: Trigger post-call analysis (fire-and-forget)
        if sessions[sessionId]["history"]:  # Only if there was conversation
            asyncio.create_task(trigger_post_call(sessionId))
            
        # Update session status to completed
        try:
            db = get_database()
            await db["sessions"].update_one(
                {"session_id": sessionId},
                {"$set": {"status": "completed", "end_time": datetime.now().isoformat()}}
            )
            print(f"\033[96m\033[1m🍃 [MONGODB]\033[0m Session status marked 'completed' in collection 'sessions'")
        except Exception as e:
            logger.error(f"Failed to update session status: {e}")

        if sessionId in sessions:
            del sessions[sessionId]
        await websocket.close()
