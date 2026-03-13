import json
import httpx
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException
from app.config import settings
from app.database import get_database

logger = logging.getLogger(__name__)
router = APIRouter()

# ANSI Colors for Terminal
CYAN = "\033[96m"
GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"

@router.get("/transcripts")
async def get_all_transcripts():
    """
    Fetches ALL transcripts (both local web sessions and synced Lyzr phone calls).
    Merges them and sorts by newest first.
    """
    try:
        db = get_database()
        all_transcripts = []
        
        # 1. Fetch local web transcripts (from VoiceAgentInterface)
        transcripts_collection = db["transcripts"]
        cursor = transcripts_collection.find({}, {"_id": 0})
        local_transcripts = await cursor.to_list(length=None)
        
        # Transform local transcripts to unified format
        for item in local_transcripts:
            all_transcripts.append({
                "sessionId": item.get("sessionId"),
                "lyzrSessionId": item.get("lyzrSessionId"),
                "timestamp": item.get("timestamp"),
                "createdAt": item.get("timestamp"),
                "history": item.get("history", []),
                "type": item.get("type", "web"),
                "source": "local"  # Mark as local web call
            })
        
        # 2. Fetch synced Lyzr transcripts (from phone calls)
        lyzr_transcripts_collection = db["lyzr_transcripts"]
        lyzr_cursor = lyzr_transcripts_collection.find({}, {"_id": 0})
        lyzr_transcripts = await lyzr_cursor.to_list(length=None)
        
        # Transform Lyzr transcripts to unified format
        for item in lyzr_transcripts:
            # Convert Lyzr transcript format to our format
            history = []
            for t in item.get("transcripts", []):
                history.append({
                    "role": t.get("role", "user"),
                    "content": t.get("transcript", ""),
                    "timestamp": t.get("transcriptTimestamp", "")
                })
            
            all_transcripts.append({
                "sessionId": item.get("sessionId") or item.get("callSid"),
                "lyzrSessionId": item.get("sessionId"),
                "timestamp": item.get("createdAt"),
                "createdAt": item.get("createdAt"),
                "history": history,
                "type": "phone" if item.get("from") or item.get("to") else "web",
                "source": "lyzr",  # Mark as Lyzr phone call
                "callSid": item.get("callSid"),
                "from": item.get("from"),
                "to": item.get("to"),
                "agent_name": item.get("agent_name")
            })
        
        # 3. Sort all transcripts by timestamp (newest first)
        all_transcripts.sort(key=lambda x: x.get("timestamp") or x.get("createdAt") or "", reverse=True)
        
        return {
            "success": True,
            "count": len(all_transcripts),
            "local_count": len(local_transcripts),
            "lyzr_count": len(lyzr_transcripts),
            "transcripts": all_transcripts
        }
    except Exception as e:
        logger.error(f"Failed to fetch transcripts: {e}")
        return {
            "success": False,
            "count": 0,
            "local_count": 0,
            "lyzr_count": 0,
            "transcripts": []
        }

@router.post("/transcripts/sync")
async def sync_transcripts_from_lyzr():
    """
    Fetches transcripts from Lyzr API and syncs to MongoDB.
    Only stores new transcripts (no duplicates based on _id).
    """
    try:
        db = get_database()
        lyzr_transcripts_collection = db["lyzr_transcripts"]
        
        # Fetch from Lyzr LiveKit API — correct endpoint per API docs
        url = f"{settings.LYZR_VOICE_BASE}/transcripts/agent/{settings.LYZR_AGENT_ID}"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers={"x-api-key": settings.LYZR_API_KEY},
                timeout=30.0
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Lyzr API Error: {response.text}"
                )
            
            data = response.json()
            # Lyzr LiveKit API returns { items: [...], total, limit, offset }
            lyzr_transcripts = data.get("items", data.get("transcripts", []))
            
            if not lyzr_transcripts:
                return {
                    "success": True,
                    "message": "No transcripts found from Lyzr",
                    "new_count": 0,
                    "total_count": 0
                }
            
            # Check for existing IDs in MongoDB
            existing_ids = set()
            cursor = lyzr_transcripts_collection.find({}, {"_id": 1})
            async for doc in cursor:
                existing_ids.add(doc["_id"])
            
            # Filter out duplicates
            new_transcripts = []
            for transcript in lyzr_transcripts:
                transcript_id = transcript.get("_id")
                if transcript_id and transcript_id not in existing_ids:
                    # Add sync metadata
                    transcript["syncedAt"] = datetime.now().isoformat()
                    new_transcripts.append(transcript)
            
            # Insert new transcripts
            if new_transcripts:
                result = await lyzr_transcripts_collection.insert_many(new_transcripts)
                inserted_count = len(result.inserted_ids)
                print(f"{CYAN}{BOLD}🔄 [SYNC]{RESET} Synced {inserted_count} new transcripts from Lyzr")
            else:
                inserted_count = 0
                print(f"{GREEN}{BOLD}✓ [SYNC]{RESET} No new transcripts to sync")
            
            return {
                "success": True,
                "message": f"Synced {inserted_count} new transcripts",
                "new_count": inserted_count,
                "total_count": len(lyzr_transcripts),
                "skipped_duplicates": len(lyzr_transcripts) - inserted_count
            }
            
    except httpx.TimeoutException:
        logger.error("Lyzr API timeout")
        raise HTTPException(status_code=504, detail="Lyzr API timeout")
    except Exception as e:
        logger.error(f"Sync error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")

@router.get("/transcripts/lyzr")
async def get_lyzr_transcripts(limit: int = 50, skip: int = 0):
    """
    Fetches synced Lyzr transcripts from MongoDB.
    Supports pagination.
    """
    try:
        db = get_database()
        lyzr_transcripts_collection = db["lyzr_transcripts"]
        
        # Get total count
        total = await lyzr_transcripts_collection.count_documents({})
        
        # Fetch paginated results sorted by creation date (newest first)
        cursor = lyzr_transcripts_collection.find(
            {},
            {"_id": 1, "callSid": 1, "sessionId": 1, "agentId": 1, 
             "from": 1, "to": 1, "createdAt": 1, "transcripts": 1, 
             "updatedAt": 1, "agent_name": 1, "syncedAt": 1}
        ).sort("createdAt", -1).skip(skip).limit(limit)
        
        transcripts = await cursor.to_list(length=limit)
        
        return {
            "success": True,
            "transcripts": transcripts,
            "pagination": {
                "total": total,
                "limit": limit,
                "skip": skip,
                "hasMore": (skip + len(transcripts)) < total
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to fetch Lyzr transcripts: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health/mongodb")
async def check_mongodb():
    """Check MongoDB connection status"""
    try:
        db = get_database()
        await db.client.admin.command('ping')
        
        # Get collection stats
        transcripts_count = await db["transcripts"].count_documents({})
        lyzr_transcripts_count = await db["lyzr_transcripts"].count_documents({})
        
        return {
            "status": "healthy",
            "database": settings.DATABASE_NAME,
            "collections": {
                "transcripts": transcripts_count,
                "lyzr_transcripts": lyzr_transcripts_count
            }
        }
    except Exception as e:
        logger.error(f"MongoDB health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"MongoDB unavailable: {str(e)}")
