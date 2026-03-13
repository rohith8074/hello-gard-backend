import os
import json
import logging
import asyncio
import httpx
from typing import Dict, Any, List
from datetime import datetime
from fastapi import APIRouter, HTTPException
from bson.binary import Binary

from app.config import settings
from app.database import get_database
from app.lib.agents import lyzr_manager

router = APIRouter()
logger = logging.getLogger(__name__)

# OpenAI dependencies removed in favor of Lyzr Agent API integration.

PROMPT_FILE_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), 
    "../../../../agent_prompts/Post_Call_Intelligence_Agent.md"
))

if not os.path.exists(PROMPT_FILE_PATH):
    PROMPT_FILE_PATH = os.path.abspath(os.path.join(
        os.path.dirname(__file__), 
        "../../../agent_prompts/Post_Call_Intelligence_Agent.md"
    ))

def get_agent_instructions_and_schema():
    """Reads System Prompt and JSON schema dynamically from the MD file."""
    try:
        with open(PROMPT_FILE_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        # Extract everything before ```json as the system prompt
        part1, sep, part2 = content.partition("```json")
        if not sep:
            logger.error("Could not find ```json in Post_Call_Intelligence_Agent.md")
            return content, None
            
        system_prompt = part1.strip()
        
        # Extract the JSON payload
        schema_str, sep2, _ = part2.partition("```")
        json_schema = json.loads(schema_str.strip())
        
        return system_prompt, json_schema
    except Exception as e:
        logger.error(f"Failed to read agent prompt file: {e}")
        return "", None

def format_transcript_for_agent(history: List[Dict[str, Any]]) -> str:
    """Format dictionary history objects into a readable string."""
    lines = []
    for item in history:
        role = item.get("role", "unknown").upper()
        content = item.get("content", "")
        lines.append(f"{role}: {content}")
    return "\n".join(lines)

def calculate_duration(history: List[Dict[str, Any]]) -> int:
    """Calculate call duration in seconds based on transcript timestamps."""
    if len(history) < 2:
        return 0
    try:
        # isoformat strings logic:
        start_ts = history[0].get("timestamp")
        end_ts = history[-1].get("timestamp")
        
        if not start_ts or not end_ts:
            return 0
            
        start = datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
        end = datetime.fromisoformat(end_ts.replace("Z", "+00:00"))
        return int((end - start).total_seconds())
    except Exception as e:
        logger.warning(f"Failed to calculate duration: {e}")
        return 0

def parse_agent_json(response_str: str) -> Dict[str, Any]:
    """Robustly parse JSON output from the LLM."""
    try:
        clean_str = response_str.strip()
        if clean_str.startswith("```json"):
            clean_str = clean_str[7:]
        elif clean_str.startswith("```"):
            clean_str = clean_str[3:]
            
        if clean_str.endswith("```"):
            clean_str = clean_str[:-3]
            
        return json.loads(clean_str.strip())
    except Exception as e:
        logger.error(f"Failed to parse agent JSON: {e}. Raw response: {response_str}")
        return {
            "outcome": "other",
            "primary_topic": "unknown",
            "issue_resolved": False,
            "summary": "Agent returned unparseable text or failed.",
            "raw_response": response_str
        }

async def log_security_event(db, event_type: str, title: str, origin: str, level: str = "info", meta: dict = None):
    """Write a structured event to the security_events collection for the Priority Event Feed."""
    doc = {
        "event_type": event_type,
        "title": title,
        "origin": origin,
        "level": level,                          # info | warning | critical
        "timestamp": datetime.utcnow().isoformat() + "Z",
        **(meta or {}),
    }
    await db["security_events"].insert_one(doc)


async def update_daily_metrics(db, call_analysis: Dict[str, Any]):
    """Upsert daily performance metrics based on the current call analysis."""
    today = datetime.now().strftime("%Y-%m-%d")

    update = {
        "$inc": {
            "total_calls": 1,
        },
        "$set": {
            "updated_at": datetime.now().isoformat()
        },
        "$setOnInsert": {
            "date": today,
            "fcr_rate": 0,
            "containment_rate": 0,
            "avg_csat": 0,
        }
    }

    # Increment Topic Counters
    topic = call_analysis.get("primary_topic")
    if topic:
        update["$inc"][f"topic_counts.{topic}"] = 1

    # Increment Outcome Counters
    outcome = call_analysis.get("outcome", "other")
    update["$inc"][f"{outcome}_calls"] = 1

    # Increment Sentiment Shifts
    shift = call_analysis.get("sentiment", {}).get("shift", "stable")
    if shift:
        update["$inc"][f"sentiment_shifts.{shift}"] = 1

    # Increment sub-agent counters if any
    for agent in call_analysis.get("agents_activated", []):
        update["$inc"][f"agent_counts.{agent}"] = 1
    
    # Track KB Performance for rolling avg
    rag = call_analysis.get("rag_performance", {})
    if rag.get("avg_kb_confidence") is not None:
        update["$inc"]["kb_confidence_sum"] = rag["avg_kb_confidence"]
        update["$inc"]["kb_call_count"] = 1

    await db["dashboard_metrics"].update_one(
        {"date": today},
        update,
        upsert=True
    )
    print(f"\033[96m\033[1m🍃 [MONGODB]\033[0m Daily metrics updated in collection 'dashboard_metrics'")
    
    # Ideally, recalculate strictly computed rates (FCR, CSAT) after upserting
    # We do a basic approximation here, and do real recalculation in the GET method

@router.post("/post-call/{session_id}")
async def process_post_call(session_id: str):
    """
    Main route to process a transcript immediately after call completion.
    It passes the transcript to the Lyzr Post-Call Agent for JSON analysis.
    """
    db = get_database()
    transcript_doc = await db["transcripts"].find_one({"sessionId": session_id})

    if not transcript_doc:
        raise HTTPException(status_code=404, detail="Transcript not found")

    # 2. Check if already processed
    existing = await db["calls"].find_one({"session_id": session_id})
    if existing:
        existing.pop("_id", None)
        return {"status": "already_processed", "call_analysis": existing}

    history = transcript_doc.get("history", [])
    session_user_id = transcript_doc.get("user_id") or transcript_doc.get("userId")
    caller_id = transcript_doc.get("caller_id") or transcript_doc.get("callerId")
    
    if not history:
        print(f"Skipping empty call analytics for {session_id}")
        return {"status": "skipped_empty_call"}

    # 3. Build input for Post_Call_Intelligence_Agent
    transcript_text = format_transcript_for_agent(history)
    
    agent_input = json.dumps({
        "call_id": session_id,
        "timestamp": transcript_doc.get("timestamp", datetime.now().isoformat()),
        "duration_seconds": calculate_duration(history),
        "transcript_text": transcript_text,
    })
    
    logger.info(f"Triggering Post-Call Analysis for {session_id}...")
    logger.debug(f"Post-Call Input Payload for {session_id}: {agent_input}")

    # 4. Run Analysis via Lyzr Post-Call Agent
    try:
        # Use the Lyzr Agent ID from settings
        agent_id = settings.POST_CALL_AGENT_ID
        
        if not agent_id:
            logger.warning("LYZR_POST_CALL_AGENT_ID legacy config missing. Writing fallback state.")
            call_analysis = parse_agent_json('{"outcome": "unprocessed", "primary_topic": "other", "summary": "Skipped because LYZR_POST_CALL_AGENT_ID is missing."}')
        else:
            # Call the Lyzr Agent
            response_text = await lyzr_manager.chat_with_agent(
                agent_id=agent_id,
                message=agent_input
            )
            
            logger.debug(f"Raw Lyzr Analysis Response for {session_id}: {response_text}")
            # The Lyzr agent is prompted to return structured JSON
            call_analysis = parse_agent_json(response_text)
            logger.info(f"Lyzr AI Analysis Successful for {session_id} | Outcome: {call_analysis.get('outcome')}")
    except Exception as e:
        logger.error(f"Lyzr integration failed for {session_id}: {str(e)}")
        call_analysis = parse_agent_json(f'{{"outcome": "other", "primary_topic": "other", "summary": "Lyzr Analysis failed: {str(e)}"}}')

    # 5. Enrich Analysis dict
    call_analysis["call_id"] = session_id
    call_analysis["session_id"] = session_id
    call_analysis["processed_at"] = datetime.now().isoformat()
    if caller_id: call_analysis["caller_id"] = caller_id

    # Prefer the user_id extracted from the transcript by the agent (e.g. "user_000")
    # over the session's user_id which may be the operator's MongoDB ObjectId
    agent_user_id = call_analysis.get("user_id")
    user_id = agent_user_id or session_user_id
    
    # Normalize ID: Change HG004 -> HG_004 to match system consistency
    if isinstance(user_id, str) and user_id.startswith("HG") and "_" not in user_id:
        if len(user_id) > 2 and user_id[2:].isdigit():
            user_id = f"HG_{user_id[2:]}"
            logger.info(f"Normalized user_id: {agent_user_id} -> {user_id}")
            
    if user_id:
        call_analysis["user_id"] = user_id
    # Adding raw transcript for display rendering
    call_analysis["transcript"] = history

    # 6. Save to DB — upsert on session_id prevents duplicates if endpoint is triggered twice
    await db["calls"].update_one(
        {"session_id": session_id},
        {"$setOnInsert": call_analysis},
        upsert=True
    )
    print(f"\033[96m\033[1m🍃 [MONGODB]\033[0m Call analysis saved to collection 'calls'")
    
    # Needs a copy without MongoDB ObjectID for return/update methods
    try:
        if settings.LYZR_API_KEY and settings.LYZR_VOICE_BASE:
            # Lyzr's audio endpoint requires its own session ID, not the local UUID.
            # The transcript doc stores it as lyzrSessionId (web) or lyzr_session_id (phone).
            lyzr_sid = (
                transcript_doc.get("lyzrSessionId")
                or transcript_doc.get("lyzr_session_id")
                or session_id  # fallback — will 404 if Lyzr ID differs from local ID
            )
            async with httpx.AsyncClient() as client:
                audio_url = f"{settings.LYZR_VOICE_BASE}/transcripts/{lyzr_sid}/audio"
                print(f"\033[94m\033[1m🎵 [AUDIO]\033[0m Fetching audio for lyzr_sid={lyzr_sid} from {audio_url}")
                audio_resp = await client.get(
                    audio_url,
                    headers={"x-api-key": settings.LYZR_API_KEY},
                    timeout=15.0
                )
                if audio_resp.status_code == 200:
                    audio_doc = {
                        "session_id": session_id,
                        "lyzr_session_id": lyzr_sid,
                        "audio_data": Binary(audio_resp.content),
                        "content_type": audio_resp.headers.get("Content-Type", "audio/ogg"),
                        "created_at": datetime.now().isoformat()
                    }
                    await db["call_audios"].insert_one(audio_doc)
                    print(f"\033[96m\033[1m🍃 [MONGODB]\033[0m Audio saved to collection 'call_audios' for {session_id}")
                else:
                    logger.warning(f"Audio fetch returned {audio_resp.status_code} for lyzr_sid={lyzr_sid} — audio may not be available for this session type.")
    except Exception as e:
        logger.error(f"Failed to fetch/save audio for {session_id}: {str(e)}")

    clean_analysis = dict(call_analysis)
    clean_analysis.pop("_id", None)

    # 7. Update Daily Rolling Metrics
    await update_daily_metrics(db, clean_analysis)

    # 7b. Log call-analyzed event
    outcome = clean_analysis.get("outcome", "other")
    product = clean_analysis.get("product", "unknown")
    sentiment_end = clean_analysis.get("sentiment", {}).get("end", "neutral")
    event_level = "warning" if outcome in ("escalated", "abandoned") else "info"
    topic = clean_analysis.get("primary_topic", "other")
    await log_security_event(
        db,
        event_type="call_analyzed",
        title=f"Call analyzed [{outcome.upper()}] — {product.upper()} | Sentiment: {sentiment_end}",
        origin=session_id[:12],
        level=event_level,
        meta={"call_id": session_id, "product": product, "outcome": outcome, "primary_topic": topic, "user_id": user_id},
    )

    # 8. Auto-create escalation ticket if call was escalated
    if outcome == "escalated":
        t_info = clean_analysis.get("ticket_info", {})
        ticket_doc = {
            "ticket_id": f"ESC-{session_id[:8].upper()}",
            "call_id": session_id,
            "user_id": user_id,
            "reason": clean_analysis.get("escalation_reason") or t_info.get("recap") or "Unresolved by AI",
            "product": product,
            "status": "open",
            "priority": t_info.get("priority", "high"),
            "category": t_info.get("category", "hardware"),
            "created_at": datetime.now().isoformat(),
            "summary": t_info.get("recap") or clean_analysis.get("summary", "Escalated call — see transcript for details"),
            "tags": clean_analysis.get("tags", []),
        }
        await db["escalation_tickets"].insert_one(ticket_doc)
        print(f"\033[96m\033[1m🍃 [MONGODB]\033[0m Escalation ticket persisted to collection 'escalation_tickets'")
        logger.info(f"Auto-created escalation ticket {ticket_doc['ticket_id']} for {session_id}")

        await log_security_event(
            db,
            event_type="escalation_created",
            title=f"Escalation ticket {ticket_doc['ticket_id']} opened — {ticket_doc['reason']}",
            origin=session_id[:12],
            level="critical" if ticket_doc["priority"] == "critical" else "warning",
            meta={"ticket_id": ticket_doc["ticket_id"], "priority": ticket_doc["priority"], "product": product, "user_id": user_id},
        )

    # 9. Auto-detect sales leads from transcript signals
    s_info = clean_analysis.get("sales_lead_info", {})
    if s_info.get("is_lead"):
        lead_doc = {
            "lead_id": f"SALES-{session_id[:8].upper()}",
            "call_id": session_id,
            "user_id": user_id,
            "product": product,
            "opportunity": s_info.get("opportunity_type") or clean_analysis.get("primary_topic", "").replace("_", " ").title(),
            "estimated_revenue": s_info.get("estimated_revenue", 0),
            "confidence": s_info.get("confidence_score", "medium"),
            "justification": s_info.get("justification", ""),
            "detected_at": datetime.now().isoformat(),
            "source": "post_call_analysis",
        }
        await db["sales_leads"].insert_one(lead_doc)
        print(f"\033[96m\033[1m🍃 [MONGODB]\033[0m Sales lead captured in collection 'sales_leads'")
        logger.info(f"Auto-created sales lead {lead_doc['lead_id']} for {session_id}")

        await log_security_event(
            db,
            event_type="sales_lead_detected",
            title=f"Sales lead detected — {lead_doc['opportunity']} (${lead_doc['estimated_revenue']}, {lead_doc['confidence']} confidence)",
            origin=session_id[:12],
            level="info",
            meta={"lead_id": lead_doc["lead_id"], "product": product, "estimated_revenue": lead_doc["estimated_revenue"], "user_id": user_id},
        )

    return {"status": "success", "call_analysis": clean_analysis}
