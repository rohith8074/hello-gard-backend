import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.lib.agents import lyzr_manager

router = APIRouter()
logger = logging.getLogger(__name__)

class ChatRequest(BaseModel):
    agent_id: str
    message: str

class ChatResponse(BaseModel):
    response: str

@router.post("/chat", response_model=ChatResponse)
async def chat_with_agent(request: ChatRequest):
    logger.info(f"Incoming Chat Request | Agent: {request.agent_id} | Message: {request.message}")
    try:
        response_text = await lyzr_manager.chat_with_agent(
            agent_id=request.agent_id,
            message=request.message
        )
        logger.info(f"Agent Response | Agent: {request.agent_id} | Response: {response_text[:100]}...")
        return {"response": response_text}
    except Exception as e:
        logger.error(f"Chat failed for agent {request.agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/telephony/webhook")
async def twilio_webhook():
    # Placeholder for Twilio voice interaction logic
    return {"message": "Webhook received"}
