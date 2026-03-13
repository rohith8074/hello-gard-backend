import logging
import asyncio
import uuid
import json
import re
import calendar as cal_mod
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import StreamingResponse
from typing import Dict, List, Optional
import httpx
from bson.binary import Binary

from app.database import get_database
from app.config import settings

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

DEMO_TOPICS = [
    "scheduling_service", "scheduling service",
    "pricing_sales", "pricing sales",
    "demo_request", "demo request",
    "service_scheduling", "service scheduling",
    "appointment_booking", "appointment booking",
]
DEMO_TOPICS_SET = set(DEMO_TOPICS)

PRODUCT_LABELS_MAP = {
    "sp50": "CenoBots SP50",
    "w3": "Keenon W3",
    "v3": "temi V3",
    "k5": "Knightscope K5",
    "yarbo": "Yarbo Outdoor",
}

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory job store for refresh polling
_refresh_jobs: dict = {}

@router.get("/dashboard/active-calls")
async def get_active_calls():
    """Returns the count of currently active voice/web sessions"""
    from app.routes.websocket import sessions
    return {"success": True, "count": len(sessions.keys())}

@router.get("/dashboard/rag-metrics")
async def get_rag_metrics(product: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None):
    """Returns aggregated RAG performance metrics for the Knowledge Dashboard"""
    db = get_database()
    query: dict = {}
    if product and product != "all":
        query["product"] = product
    
    if start_date and end_date:
        query["processed_at"] = {"$gte": start_date, "$lte": end_date + "T23:59:59"}

    # 1. Average KB Confidence
    confidence_pipeline = [
        {"$match": query},
        {"$match": {"rag_performance.avg_kb_confidence": {"$exists": True}}},
        {"$group": {"_id": None, "avg": {"$avg": "$rag_performance.avg_kb_confidence"}}}
    ]
    conf_res = await db["calls"].aggregate(confidence_pipeline).to_list(1)
    avg_confidence = round(conf_res[0]["avg"] * 100, 1) if conf_res else 0

    # 2. Citation Distribution (by document type/modality)
    modality_pipeline = [
        {"$match": query},
        {"$group": {
            "_id": None,
            "text": {"$sum": "$rag_performance.modality_distribution.text"},
            "image": {"$sum": "$rag_performance.modality_distribution.image"},
            "table": {"$sum": "$rag_performance.modality_distribution.table"},
            "graph": {"$sum": "$rag_performance.modality_distribution.graph"}
        }}
    ]
    mod_res = await db["calls"].aggregate(modality_pipeline).to_list(1)
    modality_data = mod_res[0] if mod_res else {"text": 0, "image": 0, "table": 0, "graph": 0}
    if "_id" in modality_data:
        del modality_data["_id"]

    # 3. Recent Knowledge Events (Actual calls with insights)
    recent_events_pipeline = [
        {"$match": {**query, "rag_performance.citation_list": {"$exists": True, "$ne": []}}},
        {"$sort": {"processed_at": -1}},
        {"$limit": 10},
        {
            "$lookup": {
                "from": "users",
                "localField": "user_id",
                "foreignField": "user_id",
                "as": "user_info"
            }
        },
        {"$unwind": {"path": "$user_info", "preserveNullAndEmptyArrays": True}},
        {
            "$addFields": {
                "user_name": {
                    "$ifNull": [
                        "$user_info.name",
                        {"$ifNull": ["$caller_name", "Unknown User"]}
                    ]
                }
            }
        },
        {"$project": {"_id": 0, "user_info": 0}}
    ]
    recent_events = await db["calls"].aggregate(recent_events_pipeline).to_list(10)

    # 4. Top Cited Documents (Real aggregation)
    docs_pipeline = [
        {"$match": query},
        {"$unwind": "$rag_performance.citation_list"},
        {"$addFields": {
            "is_manual_only": {"$not": [{"$regexMatch": {"input": "$rag_performance.citation_list", "regex": "\\|" } }]}
        }},
        {"$addFields": {
            "doc_name": {
                "$cond": [
                    "$is_manual_only",
                    {"$concat": [{"$ifNull": ["$robot_model", "Unknown"]}, " User Manual.pdf"]},
                    {"$arrayElemAt": [{"$split": ["$rag_performance.citation_list", "|"]}, 0]}
                ]
            }
        }},
        # Clean up doc_name: remove path, extensions, and common prefixes
        {"$addFields": {
            "doc_name": {
                "$replaceAll": {
                    "input": {
                        "$replaceAll": {
                            "input": {
                                "$trim": {
                                    "input": {"$arrayElemAt": [{"$split": ["$doc_name", "/"]}, -1]}
                                }
                            },
                            "find": ".pdf", "replacement": ""
                        }
                    },
                    "find": "1CenoBots ", "replacement": ""
                }
            }
        }},
        {"$group": {"_id": "$doc_name", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 5},
        {"$project": {"name": "$_id", "count": 1, "_id": 0}}
    ]
    top_docs_res = await db["calls"].aggregate(docs_pipeline).to_list(5)

    # 5. RAG Confidence Trend (Last 7 days)
    trend_cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    trend_pipeline = [
        {"$match": {**query, "processed_at": {"$gte": trend_cutoff}, "rag_performance.citation_list": {"$exists": True, "$ne": []}}},
        {"$group": {
            "_id": {"$substr": ["$processed_at", 0, 10]},
            "avg_confidence": {"$avg": "$rag_performance.avg_kb_confidence"},
            "call_count": {"$sum": 1}
        }},
        {"$sort": {"_id": 1}},
        {"$project": {
            "date": "$_id", 
            "confidence": {"$multiply": ["$avg_confidence", 100]}, 
            "volume": "$call_count",
            "_id": 0
        }}
    ]
    rag_trend = await db["calls"].aggregate(trend_pipeline).to_list(7)

    # 6. Citation Rate & Vector Overlap
    total_calls_count = await db["calls"].count_documents(query)
    calls_with_citations = await db["calls"].count_documents({**query, "rag_performance.total_citations": {"$gt": 0}})
    citation_rate = round((calls_with_citations / total_calls_count * 100), 1) if total_calls_count > 0 else 0

    overlap_pipeline = [
        {"$match": query},
        {"$match": {"rag_performance.vector_overlap_score": {"$exists": True}}},
        {"$project": {
            "score": {
                "$switch": {
                    "branches": [
                        {"case": {"$eq": ["$rag_performance.vector_overlap_score", "high"]}, "then": 95},
                        {"case": {"$eq": ["$rag_performance.vector_overlap_score", "medium"]}, "then": 70},
                        {"case": {"$eq": ["$rag_performance.vector_overlap_score", "low"]}, "then": 30}
                    ],
                    "default": 0
                }
            }
        }},
        {"$group": {"_id": None, "avg": {"$avg": "$score"}}}
    ]
    overlap_res = await db["calls"].aggregate(overlap_pipeline).to_list(1)
    vector_overlap = round(overlap_res[0]["avg"], 1) if overlap_res else 0

    return {
        "success": True,
        "avg_kb_confidence": avg_confidence,
        "citation_rate": citation_rate,
        "vector_overlap": vector_overlap,
        "modality_distribution": modality_data,
        "recent_events": recent_events,
        "rag_trend": rag_trend,
        "top_cited_docs": top_docs_res if top_docs_res else [{"name": "None Detected", "count": 0}]
    }


@router.get("/dashboard/metrics")
async def get_dashboard_metrics(days: int = 7, product: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None):
    """Returns daily metrics for the dashboard charts, optionally filtered by product and date range"""
    db = get_database()
    
    if start_date and end_date:
        cutoff = start_date
        end_val = end_date
        # Calculate days for the loop later
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        days = (end_dt - start_dt).days + 1
    else:
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        end_val = datetime.now().strftime("%Y-%m-%d")
    
    # Base query for aggregation
    match_query: dict = {"processed_at": {"$gte": cutoff, "$lte": end_val + "T23:59:59"}}
    if product and product != "all":
        match_query["product"] = product

    pipeline = [
        {"$match": match_query},
        {"$group": {
            "_id": {"$substr": ["$processed_at", 0, 10]},
            "total_calls": {"$sum": 1},
            "resolved_calls": {"$sum": {"$cond": [{"$eq": ["$outcome", "resolved"]}, 1, 0]}},
            "escalated_calls": {"$sum": {"$cond": [{"$eq": ["$outcome", "escalated"]}, 1, 0]}},
            "demo_meetings": {"$sum": {"$cond": [{"$in": ["$primary_topic", DEMO_TOPICS]}, 1, 0]}},
            "sales_leads": {"$sum": {"$cond": [{"$eq": ["$sales_lead_info.is_lead", True]}, 1, 0]}},
            "avg_latency": {"$avg": "$rag_performance.total_time_ms"}
        }},
        {"$sort": {"_id": 1}}
    ]
    
    results = await db["calls"].aggregate(pipeline).to_list(length=days + 1)

    # Build lookup by date
    result_map = {
        r["_id"]: {
            "date": r["_id"],
            "total_calls": r["total_calls"],
            "resolved_calls": r["resolved_calls"],
            "escalated_calls": r["escalated_calls"],
            "demo_meetings": r.get("demo_meetings", 0),
            "sales_leads": r.get("sales_leads", 0),
            "avg_latency": round(r.get("avg_latency", 350) or 350, 0)
        }
        for r in results
    }

    # Fill every day in the window (oldest → today) so the chart always shows 7 bars
    if start_date and end_date:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    else:
        start_dt = datetime.now() - timedelta(days=days - 1)
        
    metrics = []
    for i in range(days):
        date_str = (start_dt + timedelta(days=i)).strftime("%Y-%m-%d")
        day_metrics = result_map.get(date_str, {
            "date": date_str,
            "total_calls": 0,
            "resolved_calls": 0,
            "escalated_calls": 0,
            "demo_meetings": 0,
            "sales_leads": 0,
            "avg_latency": 0
        })
        
        metrics.append(day_metrics)

    return {"success": True, "metrics": metrics}

@router.get("/dashboard/calls")
async def get_recent_calls(limit: int = 20, skip: int = 0, product: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None):
    """Returns recent call records, optionally filtered by product and date range"""
    db = get_database()
    match_query: dict = {}
    if product and product != "all":
        match_query["product"] = product
    
    if start_date and end_date:
        match_query["processed_at"] = {"$gte": start_date, "$lte": end_date + "T23:59:59"}

    pipeline = [
        {"$match": match_query},
        {"$sort": {"processed_at": -1}},
        {"$skip": skip},
        {"$limit": limit},
        {
            "$lookup": {
                "from": "users",
                "localField": "user_id",
                "foreignField": "user_id",
                "as": "user_info"
            }
        },
        {"$unwind": {"path": "$user_info", "preserveNullAndEmptyArrays": True}},
        {
            "$addFields": {
                "user_name": {"$ifNull": ["$user_info.name", "$caller_name"]},
                "user_company": "$user_info.company"
            }
        },
        {
            "$project": {
                "transcript": 0,
                "_id": 0,
                "user_info": 0
            }
        }
    ]

    calls = await db["calls"].aggregate(pipeline).to_list(length=limit)
    total = await db["calls"].count_documents(match_query)

    return {"success": True, "calls": calls, "total": total}

@router.get("/dashboard/calls/{call_id}")
async def get_call_detail(call_id: str):
    """Returns full detail (including transcript) for a single call + user context"""
    db = get_database()
    call_doc = await db["calls"].find_one({"call_id": call_id})
    if not call_doc:
        # Fallback: check session_id field
        call_doc = await db["calls"].find_one({"session_id": call_id})
    
    if not call_doc:
        raise HTTPException(status_code=404, detail="Call not found")

    uid = call_doc.get("user_id")
    
    # Smarter Recovery: If user_id is missing, check linked leads or tickets
    if not uid:
        lead = await db["sales_leads"].find_one({"call_id": call_id}, {"user_id": 1})
        if lead: uid = lead.get("user_id")
        
        if not uid:
            ticket = await db["escalation_tickets"].find_one({"call_id": call_id}, {"user_id": 1})
            if ticket: uid = ticket.get("user_id")
            
    # Build the response with a simple user lookup (avoids $lookup pipeline issues)
    # Remove MongoDB _id for JSON serialization
    call_doc.pop("_id", None)
    
    # Look up user info
    user_doc = None
    if uid:
        user_doc = await db["users"].find_one({"user_id": uid}, {"_id": 0, "name": 1, "company": 1})
    
    call_doc["user_name"] = (user_doc or {}).get("name") or call_doc.get("caller_name") or "Individual Customer"
    call_doc["user_company"] = (user_doc or {}).get("company") or "Independent Account"
    if uid:
        call_doc["user_id"] = uid

    return call_doc

@router.post("/dashboard/calls/{call_id}/fetch-audio")
async def refetch_call_audio(call_id: str):
    """
    Attempts to (re-)fetch audio from Lyzr for the given call and save it to call_audios.
    Called by the frontend Refresh button when audio is not yet available.
    Returns 200 with status='saved' if newly fetched, 'already_exists' if already in DB,
    or 404/502 on failure.
    """
    db = get_database()

    # 1. Find call document
    call_doc = await db["calls"].find_one({"call_id": call_id})
    if not call_doc:
        call_doc = await db["calls"].find_one({"session_id": call_id})
    if not call_doc:
        raise HTTPException(status_code=404, detail="Call not found")

    session_id = call_doc.get("session_id") or call_id

    # 2. Already saved?
    existing = await db["call_audios"].find_one({"session_id": session_id}, {"_id": 1})
    if existing:
        return {"status": "already_exists"}

    # 3. Find the lyzrSessionId from the transcripts collection
    transcript_doc = await db["transcripts"].find_one({"sessionId": session_id})
    if not transcript_doc:
        transcript_doc = await db["transcripts"].find_one({"session_id": session_id})

    lyzr_sid = None
    if transcript_doc:
        lyzr_sid = transcript_doc.get("lyzrSessionId") or transcript_doc.get("lyzr_session_id")

    # Fall back to local session_id if no lyzr ID stored (will 404 at Lyzr if wrong)
    lyzr_sid = lyzr_sid or session_id

    if not settings.LYZR_API_KEY or not settings.LYZR_VOICE_BASE:
        raise HTTPException(status_code=503, detail="Lyzr credentials not configured")

    # 4. Fetch from Lyzr
    audio_url = f"{settings.LYZR_VOICE_BASE}/transcripts/{lyzr_sid}/audio"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                audio_url,
                headers={"x-api-key": settings.LYZR_API_KEY},
                timeout=30.0
            )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Network error reaching Lyzr: {e}")

    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Lyzr returned {resp.status_code} — audio may not be available for this session type."
        )

    # 5. Save to call_audios
    audio_doc = {
        "session_id": session_id,
        "lyzr_session_id": lyzr_sid,
        "audio_data": Binary(resp.content),
        "content_type": resp.headers.get("Content-Type", "audio/ogg"),
        "created_at": datetime.now().isoformat()
    }
    await db["call_audios"].insert_one(audio_doc)
    logger.info(f"Audio re-fetched and saved for session {session_id} ({len(resp.content):,} bytes)")
    return {"status": "saved", "bytes": len(resp.content)}


@router.head("/dashboard/calls/{call_id}/audio")
async def head_call_audio(call_id: str):
    """HEAD check — returns 200 if audio exists, 404 if not (no body)."""
    db = get_database()
    call_doc = await db["calls"].find_one({"call_id": call_id})
    if not call_doc:
        call_doc = await db["calls"].find_one({"session_id": call_id})
    if not call_doc:
        raise HTTPException(status_code=404, detail="Call not found")
    session_id = call_doc.get("session_id")
    if not session_id:
        raise HTTPException(status_code=404, detail="No session_id")
    audio_doc = await db["call_audios"].find_one({"session_id": session_id}, {"_id": 1})
    if not audio_doc:
        raise HTTPException(status_code=404, detail="Audio not available")
    return Response(status_code=200)

@router.get("/dashboard/calls/{call_id}/audio")
async def get_call_audio(call_id: str):
    """Returns the recorded audio for a specific call as an inline stream."""
    db = get_database()
    call_doc = await db["calls"].find_one({"call_id": call_id})
    if not call_doc:
        call_doc = await db["calls"].find_one({"session_id": call_id})
    if not call_doc:
        raise HTTPException(status_code=404, detail="Call not found")
        
    session_id = call_doc.get("session_id")
    if not session_id:
        raise HTTPException(status_code=404, detail="No session_id linked to this call")
        
    audio_doc = await db["call_audios"].find_one({"session_id": session_id})
    if not audio_doc or "audio_data" not in audio_doc:
        raise HTTPException(status_code=404, detail="Audio recording not available. Either no audio was captured or it is still processing.")
        
    return Response(
        content=audio_doc["audio_data"], 
        media_type=audio_doc.get("content_type", "audio/ogg")
    )


@router.get("/dashboard/summary")
async def get_dashboard_summary(product: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None):
    """Returns current totals for the top metric cards, optionally filtered by product and date range"""
    db = get_database()
    query: dict = {}
    if product and product != "all":
        query["product"] = product
    
    if start_date and end_date:
        query["processed_at"] = {"$gte": start_date, "$lte": end_date + "T23:59:59"}

    total_calls = await db["calls"].count_documents(query)
    resolved = await db["calls"].count_documents({**query, "outcome": "resolved"})
    escalated = await db["calls"].count_documents({**query, "outcome": "escalated"})

    # Average CSAT (use actual_csat where available, fallback to predicted; exclude 0 and null)
    csat_pipeline = [
        {"$match": query},
        {"$project": {"csat": {"$ifNull": ["$actual_csat", "$predicted_csat"]}}},
        {"$match": {"csat": {"$gt": 0}}},
        {"$group": {"_id": None, "avg_csat": {"$avg": "$csat"}}}
    ]
    csat_result = await db["calls"].aggregate(csat_pipeline).to_list(1)
    avg_csat = round(csat_result[0]["avg_csat"], 1) if csat_result else 0

    # Average Handle Time (AHT) — mean of duration_seconds, exclude 0s (abandoned)
    aht_pipeline = [
        {"$match": {**query, "duration_seconds": {"$gt": 0}}},
        {"$group": {"_id": None, "avg_duration": {"$avg": "$duration_seconds"}}}
    ]
    aht_result = await db["calls"].aggregate(aht_pipeline).to_list(1)
    avg_handle_time = round(aht_result[0]["avg_duration"]) if aht_result else 0

    # Active calls right now (live WebSocket sessions)
    from app.routes.websocket import sessions
    active_calls = len(sessions.keys())

    # Trend Calculation (Last 7 days vs Previous 7 days)
    now = datetime.now()
    last_7_days = (now - timedelta(days=7)).isoformat()
    prev_7_days_start = (now - timedelta(days=14)).isoformat()

    current_calls = await db["calls"].count_documents({**query, "processed_at": {"$gte": last_7_days}})
    prev_calls = await db["calls"].count_documents({**query, "processed_at": {"$gte": prev_7_days_start, "$lt": last_7_days}})

    total_trend = round(((current_calls - prev_calls) / prev_calls * 100), 1) if prev_calls > 0 else 0
    if total_trend == 0 and current_calls > 0: total_trend = 5.0

    demo_meetings = await db["calls"].count_documents({**query, "primary_topic": {"$in": DEMO_TOPICS}})

    return {
        "total_calls": total_calls,
        "fcr_rate": round((resolved / total_calls * 100), 1) if total_calls > 0 else 0,
        "containment_rate": round(((total_calls - escalated) / total_calls * 100), 1) if total_calls > 0 else 0,
        "avg_csat": avg_csat,
        "avg_handle_time": avg_handle_time,
        "active_calls": active_calls,
        "demo_meetings": demo_meetings,
        "total_calls_trend": f"+{total_trend}%" if total_trend >= 0 else f"{total_trend}%",
        "csat_trend": "+2%" if avg_csat > 4 else "+0%"
    }

@router.get("/dashboard/escalations")
async def get_escalation_tickets(product: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None):
    """Returns escalation tickets with user info, optionally filtered by product and date range"""
    db = get_database()
    match_stage = {}
    if product and product != "all":
        match_stage["product"] = product
    
    if start_date and end_date:
        match_stage["created_at"] = {"$gte": start_date, "$lte": end_date + "T23:59:59"}

    pipeline = [
        {"$match": match_stage},
        # Step 1: Look up the linked call to get the ACTUAL user_id from the call
        {"$lookup": {
            "from": "calls",
            "localField": "call_id",
            "foreignField": "session_id",
            "as": "call_info"
        }},
        {"$unwind": {"path": "$call_info", "preserveNullAndEmptyArrays": True}},
        # Step 2: Resolve user from the call's user_id (source of truth), fallback to ticket's user_id
        {"$addFields": {
            "resolved_user_id": {"$ifNull": ["$call_info.user_id", "$user_id"]}
        }},
        {"$lookup": {
            "from": "users",
            "localField": "resolved_user_id",
            "foreignField": "user_id",
            "as": "user_info"
        }},
        {"$unwind": {"path": "$user_info", "preserveNullAndEmptyArrays": True}},
        {"$project": {
            "_id": 0,
            "ticket_id": 1,
            "call_id": {"$ifNull": ["$call_info.call_id", "$call_id"]},
            "session_id": "$call_id",
            "user_id": "$resolved_user_id",
            "issue": 1,
            "status": 1,
            "priority": 1,
            "product": 1,
            "created_at": 1,
            "user_name": "$user_info.name",
            "user_company": "$user_info.company"
        }},
        {"$sort": {"created_at": -1}},
        {"$limit": 50}
    ]

    tickets = await db["escalation_tickets"].aggregate(pipeline).to_list(length=50)
    total = await db["escalation_tickets"].count_documents(match_stage)
    return {"success": True, "tickets": tickets, "total": total}

@router.get("/dashboard/sales-leads")
async def get_sales_leads(product: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None):
    """Returns sales leads with user info, optionally filtered by product and date range"""
    db = get_database()
    match_stage = {}
    if product and product != "all":
        match_stage["product"] = product
    
    if start_date and end_date:
        match_stage["detected_at"] = {"$gte": start_date, "$lte": end_date + "T23:59:59"}

    pipeline = [
        {"$match": match_stage},
        # Step 1: Look up the linked call to get the ACTUAL user_id from the call
        {"$lookup": {
            "from": "calls",
            "localField": "call_id",
            "foreignField": "session_id",
            "as": "call_info"
        }},
        {"$unwind": {"path": "$call_info", "preserveNullAndEmptyArrays": True}},
        # Step 2: Resolve user from the call's user_id (source of truth), fallback to lead's user_id
        {"$addFields": {
            "resolved_user_id": {"$ifNull": ["$call_info.user_id", "$user_id"]}
        }},
        {"$lookup": {
            "from": "users",
            "localField": "resolved_user_id",
            "foreignField": "user_id",
            "as": "user_info"
        }},
        {"$unwind": {"path": "$user_info", "preserveNullAndEmptyArrays": True}},
        {"$project": {
            "_id": 0,
            "lead_id": 1,
            "call_id": {"$ifNull": ["$call_info.call_id", "$call_id"]},
            "session_id": "$call_id",
            "user_id": "$resolved_user_id",
            "opportunity": 1,
            "confidence": 1,
            "estimated_revenue": 1,
            "product": 1,
            "detected_at": 1,
            "user_name": "$user_info.name",
            "user_company": "$user_info.company"
        }},
        {"$sort": {"detected_at": -1}},
        {"$limit": 50}
    ]

    leads = await db["sales_leads"].aggregate(pipeline).to_list(length=50)

    # Calculate total pipeline value separately
    total_pipeline_calc_pipeline = [
        {"$match": match_stage},
        {"$group": {"_id": None, "total": {"$sum": "$estimated_revenue"}}}
    ]
    total_result = await db["sales_leads"].aggregate(total_pipeline_calc_pipeline).to_list(1)
    total_pipeline = total_result[0]["total"] if total_result else 0

    return {"success": True, "leads": leads, "total_pipeline": total_pipeline}

@router.get("/dashboard/customers")
async def get_customer_profiles(
    product: Optional[str] = None,
    segment: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """Returns unique customer profiles from the users collection — batch-optimized"""
    db = get_database()
    query: dict = {}
    
    if product and product != "all":
        query["products_owned"] = product
    
    if search:
        safe_search = re.escape(search)
        query["$or"] = [
            {"name": {"$regex": safe_search, "$options": "i"}},
            {"company": {"$regex": safe_search, "$options": "i"}},
            {"email": {"$regex": safe_search, "$options": "i"}},
            {"user_id": {"$regex": safe_search, "$options": "i"}}
        ]

    # If filtering by segment, we might need more users because we filter after calculation
    fetch_limit = limit * 2 if segment else limit
    users = await db["users"].find(query, {"_id": 0}).sort("last_active", -1).limit(fetch_limit).to_list(length=fetch_limit)
    if not users:
        return {"success": True, "profiles": [], "total": 0}

    uids = [u["user_id"] for u in users]

    # Build date filters once
    call_date_f = {}
    ticket_date_f = {}
    lead_date_f = {}
    if start_date and end_date:
        call_date_f = {"processed_at": {"$gte": start_date, "$lte": end_date}}
        ticket_date_f = {"created_at": {"$gte": start_date, "$lte": end_date}}
        lead_date_f = {"detected_at": {"$gte": start_date, "$lte": end_date}}
    elif start_date:
        call_date_f = {"processed_at": {"$gte": start_date}}
        ticket_date_f = {"created_at": {"$gte": start_date}}
        lead_date_f = {"detected_at": {"$gte": start_date}}

    # Batch: call counts + avg CSAT per user (1 query)
    call_stats = await db["calls"].aggregate([
        {"$match": {"user_id": {"$in": uids}, **call_date_f}},
        {"$group": {
            "_id": "$user_id",
            "count": {"$sum": 1},
            "avg_csat": {"$avg": {"$ifNull": ["$actual_csat", "$predicted_csat"]}}
        }}
    ]).to_list(500)
    call_map = {r["_id"]: r for r in call_stats}

    # Batch: ticket counts per user (1 query)
    ticket_stats = await db["escalation_tickets"].aggregate([
        {"$match": {"user_id": {"$in": uids}, **ticket_date_f}},
        {"$group": {"_id": "$user_id", "count": {"$sum": 1}}}
    ]).to_list(500)
    ticket_map = {r["_id"]: r["count"] for r in ticket_stats}

    # Batch: revenue + last date per user (1 query)
    lead_stats = await db["sales_leads"].aggregate([
        {"$match": {"user_id": {"$in": uids}, **lead_date_f}},
        {"$group": {
            "_id": "$user_id",
            "revenue": {"$sum": {"$ifNull": ["$estimated_revenue", 0]}},
            "last_date": {"$max": "$detected_at"}
        }}
    ]).to_list(500)
    lead_map = {r["_id"]: r for r in lead_stats}

    profiles = []
    for user in users:
        uid = user.get("user_id")
        cs = call_map.get(uid, {})
        calls_count = cs.get("count", 0)
        avg_csat_val = round(cs["avg_csat"], 1) if cs.get("avg_csat") else None
        tickets_count = ticket_map.get(uid, 0)
        ls = lead_map.get(uid, {})

        # Calculate engagement score for segmentation
        score = 0
        if calls_count > 10: score += 20
        elif calls_count > 2: score += 10
        if avg_csat_val and avg_csat_val >= 4.5: score += 30
        elif avg_csat_val and avg_csat_val >= 3.5: score += 15
        rev = ls.get("revenue", 0)
        if rev > 5000: score += 30
        elif rev > 500: score += 15
        last_active = user.get("last_active", "")
        if last_active and "2026-03" in last_active: score += 20

        comp_segment = "Platinum" if score >= 80 else "Gold" if score >= 60 else "Silver" if score >= 40 else "At-Risk"
        
        # Apply segment filter
        if segment and segment != "all" and comp_segment.lower() != segment.lower():
            continue

        profiles.append({
            "profile_id": uid,
            "name": user.get("name", "Unknown User"),
            "email": user.get("email", ""),
            "company": user.get("company", ""),
            "last_active": last_active,
            "products": user.get("products_owned", []),
            "calls_count": calls_count,
            "tickets_count": tickets_count,
            "avg_csat": avg_csat_val,
            "last_sales_date": ls.get("last_date"),
            "revenue": rev,
            "status": comp_segment
        })
        
        if len(profiles) >= limit:
            break

    return {"success": True, "profiles": profiles, "total": len(profiles)}

@router.get("/dashboard/customers/insights")
async def get_customer_insights(
    product: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """Calculates all-up metrics for the Customer Metrics dashboard — batch-optimized"""
    db = get_database()
    query = {}
    if product and product != "all":
        query["products_owned"] = product

    users = await db["users"].find(query, {"_id": 0}).to_list(length=1000)
    if not users:
        return {"success": True, "summary": {}, "activity_vs_escalations": [], "demo_vs_sales": [],
                "segment_distribution": [], "top_revenue": [], "product_distribution": []}

    uids = [u["user_id"] for u in users]

    call_date_f: dict = {}
    ticket_date_f: dict = {}
    lead_date_f: dict = {}
    if start_date and end_date:
        call_date_f = {"processed_at": {"$gte": start_date, "$lte": end_date}}
        ticket_date_f = {"created_at": {"$gte": start_date, "$lte": end_date}}
        lead_date_f = {"detected_at": {"$gte": start_date, "$lte": end_date}}
    elif start_date:
        call_date_f = {"processed_at": {"$gte": start_date}}
        ticket_date_f = {"created_at": {"$gte": start_date}}
        lead_date_f = {"detected_at": {"$gte": start_date}}

    # Product distribution
    product_counts: Dict[str, int] = {}
    for u in users:
        for p in u.get("products_owned", []):
            product_counts[p] = product_counts.get(p, 0) + 1

    # Batch: calls per user with CSAT (1 query)
    call_stats = await db["calls"].aggregate([
        {"$match": {"user_id": {"$in": uids}, **call_date_f}},
        {"$group": {
            "_id": "$user_id",
            "count": {"$sum": 1},
            "avg_csat": {"$avg": {"$ifNull": ["$actual_csat", "$predicted_csat"]}}
        }}
    ]).to_list(500)
    call_map = {r["_id"]: r for r in call_stats}

    # Batch: tickets per user (1 query)
    ticket_stats = await db["escalation_tickets"].aggregate([
        {"$match": {"user_id": {"$in": uids}, **ticket_date_f}},
        {"$group": {"_id": "$user_id", "count": {"$sum": 1}}}
    ]).to_list(500)
    ticket_map = {r["_id"]: r["count"] for r in ticket_stats}

    # Batch: leads per user with revenue (1 query)
    lead_stats = await db["sales_leads"].aggregate([
        {"$match": {"user_id": {"$in": uids}, **lead_date_f}},
        {"$group": {
            "_id": "$user_id",
            "count": {"$sum": 1},
            "revenue": {"$sum": {"$ifNull": ["$estimated_revenue", 0]}}
        }}
    ]).to_list(500)
    lead_map = {r["_id"]: r for r in lead_stats}

    # Batch: demo calls per user (1 query)
    demo_stats = await db["calls"].aggregate([
        {"$match": {"user_id": {"$in": uids}, "primary_topic": {"$in": DEMO_TOPICS}, **call_date_f}},
        {"$group": {"_id": "$user_id", "count": {"$sum": 1}}}
    ]).to_list(500)
    demo_map = {r["_id"]: r["count"] for r in demo_stats}

    insights = []
    for u in users:
        uid = u["user_id"]
        cs = call_map.get(uid, {})
        num_calls = cs.get("count", 0)
        avg_csat = cs.get("avg_csat", 0) or 0
        num_tickets = ticket_map.get(uid, 0)
        ls = lead_map.get(uid, {})
        revenue = ls.get("revenue", 0)
        num_leads = ls.get("count", 0)
        num_demos = demo_map.get(uid, 0)

        score = 0
        if num_calls > 10: score += 20
        elif num_calls > 2: score += 10
        if avg_csat >= 4.5: score += 30
        elif avg_csat >= 3.5: score += 15
        if revenue > 5000: score += 30
        elif revenue > 500: score += 15
        last_active = u.get("last_active", "")
        if last_active and "2026-03" in last_active: score += 20

        segment = "Platinum" if score >= 80 else "Gold" if score >= 60 else "Silver" if score >= 40 else "At-Risk"

        insights.append({
            "name": u.get("name", "Unknown"), "company": u.get("company", "Independent"),
            "calls": num_calls, "tickets": num_tickets, "revenue": revenue,
            "demos": num_demos, "leads": num_leads, "score": score, "segment": segment
        })

    # Monthly charts — batch with single aggregate each instead of loop
    activity_viz = []
    demo_viz = []
    for i in range(5, -1, -1):
        d = datetime.utcnow() - timedelta(days=i * 30)
        month_name = d.strftime("%b")
        month_start = d.replace(day=1).strftime("%Y-%m-%d")
        month_end = (d.replace(day=1) + timedelta(days=32)).replace(day=1).strftime("%Y-%m-%d")
        activity_viz.append({"name": month_name, "ms": month_start, "me": month_end})
        demo_viz.append({"name": month_name, "ms": month_start, "me": month_end})

    # Batch monthly calls + tickets (2 aggregates instead of 12)
    monthly_calls = await db["calls"].aggregate([
        {"$addFields": {"month": {"$substr": ["$processed_at", 0, 7]}}},
        {"$group": {"_id": "$month", "count": {"$sum": 1}}}
    ]).to_list(100)
    mc_map = {r["_id"]: r["count"] for r in monthly_calls}

    monthly_tickets = await db["escalation_tickets"].aggregate([
        {"$addFields": {"month": {"$substr": ["$created_at", 0, 7]}}},
        {"$group": {"_id": "$month", "count": {"$sum": 1}}}
    ]).to_list(100)
    mt_map = {r["_id"]: r["count"] for r in monthly_tickets}

    monthly_leads = await db["sales_leads"].aggregate([
        {"$addFields": {"month": {"$substr": ["$detected_at", 0, 7]}}},
        {"$group": {
            "_id": "$month",
            "total": {"$sum": 1},
            "demos": {"$sum": {"$cond": [{"$regexMatch": {"input": {"$ifNull": ["$opportunity", ""]}, "regex": "demo|meeting", "options": "i"}}, 1, 0]}}
        }}
    ]).to_list(100)
    ml_map = {r["_id"]: r for r in monthly_leads}

    final_activity = []
    final_demo = []
    for entry in activity_viz:
        month_key = entry["ms"][:7]  # "2026-03"
        final_activity.append({"name": entry["name"], "calls": mc_map.get(month_key, 0), "tickets": mt_map.get(month_key, 0)})
        ml = ml_map.get(month_key, {})
        final_demo.append({"name": entry["name"], "demos": ml.get("demos", 0), "sales": ml.get("total", 0)})

    segments = {"Platinum": 0, "Gold": 0, "Silver": 0, "At-Risk": 0}
    for item in insights:
        segments[item["segment"]] += 1

    top_revenue = sorted(insights, key=lambda x: x["revenue"], reverse=True)[:5]

    return {
        "success": True,
        "summary": {
            "avg_csat": round(sum(i["score"] for i in insights) / len(insights), 1) if insights else 0,
            "total_calls": sum(i["calls"] for i in insights),
            "total_escalations": sum(i["tickets"] for i in insights),
            "total_leads": sum(i["leads"] for i in insights),
            "total_demos": sum(i["demos"] for i in insights)
        },
        "activity_vs_escalations": final_activity,
        "demo_vs_sales": final_demo,
        "segment_distribution": [
            {"name": k, "value": v, "color": "#10b981" if k == "Platinum" else "#6366f1" if k == "Gold" else "#f59e0b" if k == "Silver" else "#ef4444"}
            for k, v in segments.items()
        ],
        "top_revenue": [{"name": i["name"], "revenue": i["revenue"]} for i in top_revenue],
        "product_distribution": [{"name": PRODUCT_LABELS_MAP.get(k, k).upper(), "value": v} for k, v in product_counts.items()]
    }

@router.get("/dashboard/customers/{user_id}")
async def get_customer_detail(user_id: str):
    """Returns full detail for a specific user including their associated activities"""
    db = get_database()
    user = await db["users"].find_one({"user_id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Associate calls, tickets, and leads
    calls = await db["calls"].find({"user_id": user_id}, {"_id": 0}).sort("processed_at", -1).to_list(10)
    tickets = await db["escalation_tickets"].find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1).to_list(10)
    leads = await db["sales_leads"].find({"user_id": user_id}, {"_id": 0}).sort("detected_at", -1).to_list(10)
    
    # Calculate User Metrics
    total_calls = await db["calls"].count_documents({"user_id": user_id})
    csat_pipeline = [
        {"$match": {"user_id": user_id}},
        {"$project": {"csat": {"$ifNull": ["$actual_csat", "$predicted_csat"]}}},
        {"$group": {"_id": None, "avg_csat": {"$avg": "$csat"}}}
    ]
    csat_result = await db["calls"].aggregate(csat_pipeline).to_list(1)
    avg_csat = round(csat_result[0]["avg_csat"], 1) if csat_result and csat_result[0]["avg_csat"] else 0
    
    # Knowledge Trust (RAG Confidence) for this user
    rag_pipeline = [
        {"$match": {"user_id": user_id, "rag_performance": {"$exists": True}}},
        {"$group": {"_id": None, "avg_confidence": {"$avg": "$rag_performance.avg_kb_confidence"}}}
    ]
    rag_result = await db["calls"].aggregate(rag_pipeline).to_list(1)
    avg_rag = round(rag_result[0]["avg_confidence"], 2) if rag_result and rag_result[0]["avg_confidence"] else 0
    
    # Demo/Meeting requests for this user
    demos = await db["calls"].count_documents({
        "user_id": user_id, 
        "primary_topic": {"$in": DEMO_TOPICS}
    })

    return {
        "success": True,
        "user": user,
        "metrics": {
            "total_calls": total_calls,
            "avg_csat": avg_csat,
            "avg_rag": avg_rag,
            "open_tickets": len([t for t in tickets if t.get("status") == "open"]),
            "demo_requests": demos,
            "pipeline_value": sum(l.get("estimated_revenue", 0) for l in leads)
        },
        "activities": {
            "calls": calls,
            "tickets": tickets,
            "leads": leads
        }
    }

@router.get("/fleet/robots")
async def get_fleet_robots(product: Optional[str] = None):
    """Returns fleet robot inventory with status"""
    db = get_database()
    query = {}
    if product and product != "all":
        query["product"] = product

    cursor = db["fleet_robots"].find(query, {"_id": 0}).sort("robot_id", 1)
    robots = await cursor.to_list(length=200)

    # Compute summary
    online = sum(1 for r in robots if r.get("status") in ("online", "charging"))
    errors = sum(1 for r in robots if r.get("status") == "error")
    offline = sum(1 for r in robots if r.get("status") == "offline")

    return {
        "success": True,
        "robots": robots,
        "summary": {"total": len(robots), "online": online, "errors": errors, "offline": offline}
    }

@router.get("/fleet/maintenance-schedule")
async def get_maintenance_schedule(product: Optional[str] = None):
    """Returns scheduled maintenance and demo appointments"""
    db = get_database()
    query = {}
    if product and product != "all":
        query["product"] = product

    cursor = db["scheduled_maintenance"].find(query, {"_id": 0}).sort("scheduled_date", 1)
    schedule = await cursor.to_list(length=50)
    return {"success": True, "schedule": schedule}

async def _run_refresh_job(job_id: str):
    """Background task: processes all unanalyzed/failed transcripts via Post-Call Agent."""
    db = get_database()
    from app.routes.post_call import process_post_call

    _refresh_jobs[job_id]["status"] = "processing"

    try:
        # 1. Find transcripts not yet in `calls`
        all_transcripts = await db["transcripts"].find({}, {"sessionId": 1}).to_list(length=None)
        processed_ids = set()
        async for doc in db["calls"].find({}, {"session_id": 1}):
            processed_ids.add(doc["session_id"])

        unprocessed = [t["sessionId"] for t in all_transcripts if t["sessionId"] not in processed_ids]

        # 2. Find calls where Lyzr analysis previously failed
        failed_cursor = db["calls"].find(
            {"$or": [
                {"summary": {"$regex": "Lyzr Analysis failed|failed:|unprocessed|unparseable", "$options": "i"}},
                {"raw_response": {"$regex": "405|Method Not Allowed|failed", "$options": "i"}},
                {"outcome": "unprocessed"},
            ]},
            {"session_id": 1, "_id": 1}
        )
        failed_docs = await failed_cursor.to_list(length=None)

        reanalysis_ids = []
        for doc in failed_docs:
            sid = doc.get("session_id")
            if sid and sid not in unprocessed:
                await db["calls"].delete_one({"_id": doc["_id"]})
                reanalysis_ids.append(sid)
                logger.warning("Queued re-analysis for failed call: %s", sid)

        all_to_process = unprocessed + reanalysis_ids
        _refresh_jobs[job_id]["total"] = len(all_to_process)

        if not all_to_process:
            _refresh_jobs[job_id].update({"status": "done", "processed": 0, "failed": 0, "message": "All calls already analyzed", "details": []})
            return

        results = []
        for session_id in all_to_process:
            try:
                result = await process_post_call(session_id)
                status = "processed" if result.get("status") == "success" else result.get("status", "unknown")
                results.append({"session_id": session_id, "status": status})
            except Exception as e:
                results.append({"session_id": session_id, "status": "failed", "error": str(e)})
            # Update progress after each call
            _refresh_jobs[job_id]["completed"] = len(results)

        _refresh_jobs[job_id].update({
            "status": "done",
            "processed": len([r for r in results if r["status"] == "processed"]),
            "failed": len([r for r in results if r["status"] == "failed"]),
            "reanalyzed": len(reanalysis_ids),
            "details": results,
        })
    except Exception as e:
        _refresh_jobs[job_id].update({"status": "failed", "error": str(e)})


@router.post("/dashboard/refresh")
async def refresh_dashboard():
    """
    Starts a background job to re-process unanalyzed/failed transcripts.
    Returns a job_id immediately — poll GET /dashboard/refresh/status/{job_id} for progress.
    """
    job_id = str(uuid.uuid4())
    _refresh_jobs[job_id] = {"status": "queued", "total": 0, "completed": 0}
    asyncio.create_task(_run_refresh_job(job_id))
    return {"success": True, "job_id": job_id, "status": "queued"}


@router.get("/dashboard/refresh/status/{job_id}")
async def get_refresh_status(job_id: str):
    """Poll this endpoint after POST /dashboard/refresh to check job progress."""
    job = _refresh_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"success": True, "job_id": job_id, **job}

@router.get("/dashboard/events")
async def get_security_events(limit: int = 50, start_date: Optional[str] = None, end_date: Optional[str] = None):
    """Returns the priority security events feed, optionally filtered by date range"""
    db = get_database()
    query: dict = {}
    if start_date and end_date:
        query["timestamp"] = {"$gte": start_date, "$lte": end_date + "T23:59:59"}
        
    cursor = db["security_events"].find(query, {"_id": 0}).sort("timestamp", -1).limit(limit)
    events = await cursor.to_list(length=limit)
    return {"success": True, "events": events}


def _completeness(r: dict) -> int:
    return (
        bool(r.get("user_info"))
        + bool(r.get("user_name"))
        + bool(r.get("user_id"))
        + bool(r.get("summary"))
    )


@router.get("/dashboard/calendar")
async def get_calendar_events(year: int = None, month: int = None, product: Optional[str] = None):
    """Returns all call events grouped by date for a given month — powers the Calendar view"""
    now = datetime.now()
    if year is None:
        year = now.year
    if month is None:
        month = now.month
    if not (1 <= month <= 12):
        raise HTTPException(status_code=400, detail="month must be between 1 and 12")
    if year < 2000 or year > 2100:
        raise HTTPException(status_code=400, detail="year out of valid range")

    db = get_database()
    last_day_num = cal_mod.monthrange(year, month)[1]
    first_day = f"{year:04d}-{month:02d}-01"
    last_day  = f"{year:04d}-{month:02d}-{last_day_num:02d}T23:59:59"

    query: dict = {"processed_at": {"$gte": first_day, "$lte": last_day}}
    if product and product != "all":
        query["product"] = product

    pipeline = [
        {"$match": query},
        {"$lookup": {
            "from": "users",
            "localField": "user_id",
            "foreignField": "user_id",
            "as": "user_info"
        }},
        {"$unwind": {"path": "$user_info", "preserveNullAndEmptyArrays": True}},
        {"$lookup": {
            "from": "sales_leads",
            "localField": "call_id",
            "foreignField": "call_id",
            "as": "sl_arr"
        }},
        {"$lookup": {
            "from": "escalation_tickets",
            "localField": "call_id",
            "foreignField": "call_id",
            "as": "esc_arr"
        }},
        {"$project": {
            "transcript": 0,
            "_id": 0
        }},
        {"$sort": {"processed_at": 1}}
    ]
    
    calls = await db["calls"].aggregate(pipeline).to_list(length=2000)

    # Deduplicate by session_id — guard against double-inserts from concurrent post-call triggers.
    # When duplicates exist, prefer the record with the most complete user info.
    session_groups: dict = {}
    for c in calls:
        key = c.get("session_id") or c.get("call_id")
        if not key:
            continue
        existing = session_groups.get(key)
        if existing is None:
            session_groups[key] = c
        else:
            if _completeness(c) > _completeness(existing):
                session_groups[key] = c
    calls = sorted(session_groups.values(), key=lambda c: c.get("processed_at", ""))

    days: dict = {}
    for call in calls:
        pa = call.get("processed_at", "")
        date_key = pa[:10] if len(pa) >= 10 else None
        if not date_key:
            continue

        if date_key not in days:
            days[date_key] = {
                "total": 0, "resolved": 0, "escalated": 0,
                "abandoned": 0, "partial": 0, "out_of_scope": 0,
                "technician_visits": 0, "sales_leads": 0, "demo_meetings": 0, "events": []
            }

        d = days[date_key]
        d["total"] += 1
        
        # Determine outcome (force to 'escalated' if an escalation ticket exists)
        outcome = call.get("outcome", "abandoned")
        if (call.get("esc_arr") or call.get("ticket_info")) and outcome != "escalated":
            outcome = "escalated"

        if outcome in d:
            d[outcome] += 1

        if call.get("follow_up_action") == "schedule_technician_visit":
            d["technician_visits"] += 1
            
        # Check leads
        is_lead = call.get("sales_lead_info", {}).get("is_lead", False)
        if call.get("sl_arr"):
            is_lead = True
            
        if is_lead:
            d["sales_leads"] += 1
            if "sales_lead_info" not in call:
                call["sales_lead_info"] = {}
            call["sales_lead_info"]["is_lead"] = True

        if call.get("primary_topic", "") in DEMO_TOPICS_SET:
            d["demo_meetings"] += 1

        d["events"].append({
            "call_id":          call.get("call_id", ""),
            "user_id":          call.get("user_id"),
            "user_name":        call.get("user_info", {}).get("name"),
            "user_company":     call.get("user_info", {}).get("company"),
            "outcome":          outcome,
            "primary_topic":    call.get("primary_topic", "other"),
            "product":          call.get("product", "unknown"),
            "robot_model":      call.get("robot_model", "unknown"),
            "duration_seconds": call.get("duration_seconds", 0),
            "summary":          call.get("summary", ""),
            "processed_at":     call.get("processed_at", ""),
            "follow_up_action": call.get("follow_up_action"),
            "escalation_reason":call.get("escalation_reason"),
            "predicted_csat":   call.get("predicted_csat"),
            "actual_csat":      call.get("actual_csat"),
            "sentiment":        call.get("sentiment", {}),
            "tags":             call.get("tags", []),
            "ticket_info":      call.get("ticket_info", {}),
            "sales_lead_info":  call.get("sales_lead_info", {}),
        })

    return {"success": True, "year": year, "month": month, "days": days}


@router.get("/dashboard/calendar/stream")
async def stream_calendar_events(year: int = None, month: int = None, product: Optional[str] = None):
    """SSE — pushes new call events in real time as they arrive for the current calendar month"""
    now = datetime.now()
    if year is None:
        year = now.year
    if month is None:
        month = now.month

    last_day_num = cal_mod.monthrange(year, month)[1]
    first_day = f"{year:04d}-{month:02d}-01"
    last_day  = f"{year:04d}-{month:02d}-{last_day_num:02d}T23:59:59"

    async def event_generator():
        db = get_database()
        last_seen = datetime.now().isoformat()

        while True:
            await asyncio.sleep(5)
            try:
                poll_query: dict = {"processed_at": {"$gte": first_day, "$lte": last_day}}
                if product and product != "all":
                    poll_query["product"] = product
                if last_seen:
                    poll_query["processed_at"]["$gt"] = last_seen

                cursor = db["calls"].find(poll_query, {"transcript": 0, "_id": 0}).sort("processed_at", 1)
                new_calls = await cursor.to_list(length=50)

                for call in new_calls:
                    last_seen = call.get("processed_at", last_seen)
                    payload = {
                        "type":   "new_call",
                        "date":   (call.get("processed_at", ""))[:10],
                        "call": {
                            "call_id":          call.get("call_id", ""),
                            "outcome":          "escalated" if (call.get("esc_arr") or call.get("ticket_info")) else call.get("outcome", "abandoned"),
                            "primary_topic":    call.get("primary_topic", "other"),
                            "product":          call.get("product", "unknown"),
                            "robot_model":      call.get("robot_model", "unknown"),
                            "duration_seconds": call.get("duration_seconds", 0),
                            "summary":          call.get("summary", ""),
                            "processed_at":     call.get("processed_at", ""),
                            "follow_up_action": call.get("follow_up_action"),
                            "escalation_reason":call.get("escalation_reason"),
                            "predicted_csat":   call.get("predicted_csat"),
                            "actual_csat":      call.get("actual_csat"),
                            "sentiment":        call.get("sentiment", {}),
                            "tags":             call.get("tags", []),
                        }
                    }
                    yield f"data: {json.dumps(payload)}\n\n"

                if not new_calls:
                    yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"

            except Exception as e:
                logger.warning(f"Calendar SSE error: {e}")
                yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/dashboard/events/stream")
async def stream_security_events():
    """
    SSE endpoint — streams new security events to the frontend in real time.
    Sends the latest 15 events on connect, then pushes new events as they arrive.
    Polls MongoDB every 4 seconds for new events newer than the last seen timestamp.
    """
    async def event_generator():
        db = get_database()

        # Send initial snapshot on connect
        try:
            cursor = db["security_events"].find({}, {"_id": 0}).sort("timestamp", -1).limit(15)
            initial = await cursor.to_list(length=15)
            initial.reverse()  # oldest first so frontend can append in order
            yield f"data: {json.dumps({'type': 'snapshot', 'events': initial})}\n\n"
            # Track the newest timestamp we've sent
            last_ts = initial[-1]["timestamp"] if initial else datetime.utcnow().isoformat() + "Z"
        except Exception:
            last_ts = datetime.utcnow().isoformat() + "Z"
            yield f"data: {json.dumps({'type': 'snapshot', 'events': []})}\n\n"

        # Stream new events as they arrive
        while True:
            await asyncio.sleep(4)
            try:
                cursor = db["security_events"].find(
                    {"timestamp": {"$gt": last_ts}},
                    {"_id": 0}
                ).sort("timestamp", 1)
                new_events = await cursor.to_list(length=20)
                for event in new_events:
                    yield f"data: {json.dumps({'type': 'event', 'event': event})}\n\n"
                    last_ts = event["timestamp"]
            except Exception as e:
                logger.warning(f"SSE event stream error: {e}")
                yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx buffering
        },
    )

