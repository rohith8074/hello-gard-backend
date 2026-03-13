import asyncio
import logging
import httpx
from dotenv import load_dotenv

load_dotenv()

from app.config import settings

logger = logging.getLogger(__name__)


class LyzrAgentManager:
    def __init__(self):
        self.api_key = settings.LYZR_API_KEY
        # Direct chat endpoint from .env: https://agent-prod.studio.lyzr.ai/v3/inference/chat/
        self.chat_url = settings.LYZR_AGENT_URL

    async def chat_with_agent(self, agent_id: str, message: str) -> str:
        """
        Call the Lyzr Chat API directly via httpx.
        The lyzr_agent_api SDK hardcodes /v2/chat/ which returns 405 —
        the correct endpoint is /v3/inference/chat/ per LYZR_AGENT_URL in .env.
        """
        if not self.api_key:
            logger.warning("Lyzr API client not initialized — LYZR_API_KEY missing?")
            return "API Key not configured"

        payload = {
            "agent_id": agent_id,
            "user_id": "hellgard_system",
            "session_id": f"post_call_{agent_id}",
            "message": message,
        }

        print(f"\033[95m[POST-CALL AGENT]\033[0m → POST {self.chat_url} | agent_id={agent_id}")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.chat_url,
                headers={
                    "x-api-key": self.api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=60.0,
            )

        print(f"\033[95m[POST-CALL AGENT]\033[0m ← status={response.status_code}")

        if response.status_code != 200:
            raise Exception(f"Lyzr Chat API error ({response.status_code}): {response.text[:300]}")

        result = response.json()
        print(f"\033[95m[POST-CALL AGENT]\033[0m response keys={list(result.keys()) if isinstance(result, dict) else type(result)}")

        # Lyzr v3 returns {"response": "...", ...} or {"message": "..."}
        if isinstance(result, dict):
            text = result.get("response") or result.get("message") or result.get("text") or str(result)
            return text

        return str(result)


lyzr_manager = LyzrAgentManager()
