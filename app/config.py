import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # Lyzr Configuration
    LYZR_API_KEY: str = os.getenv("LYZR_API_KEY", "")
    LYZR_AGENT_ID: str = os.getenv("LYZR_Managerial_Agent_ID", "")
    POST_CALL_AGENT_ID: str = os.getenv("LYZR_POST_CALL_AGENT_ID", "")

    # Specific API Bases
    # Voice (LiveKit sessions + transcripts)
    LYZR_VOICE_BASE: str = os.getenv("LYZR_VOICE_BASE", "https://voice-livekit.studio.lyzr.ai/v1")
    # Chat (post-call analysis, sub-agents) — full URL including path
    LYZR_CHAT_BASE: str = os.getenv("LYZR_CHAT_BASE", "https://agent-prod.studio.lyzr.ai")
    LYZR_AGENT_URL: str = os.getenv("LYZR_AGENT_URL", "https://agent-prod.studio.lyzr.ai/v3/inference/chat/")

    # Aliases for backwards compatibility
    LYZR_API_BASE: str = LYZR_VOICE_BASE
    LYZR_CHAT_API_BASE: str = LYZR_CHAT_BASE

    # MongoDB Configuration
    MONGODB_URI: str = os.getenv("Mongodb_URI", "")
    DATABASE_NAME: str = os.getenv("Databse_name", "HelloGard").strip()

    # Security
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "hellguard-rbac-secret-2024-change-in-prod")

    # Server Configuration
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # CORS — comma-separated list of allowed origins, e.g. "https://app.hellaguard.com,http://localhost:3000"
    CORS_ORIGINS: list = [
        o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()
    ]

    # Default admin seed (override via env in production)
    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "rohith")
    ADMIN_NAME: str = os.getenv("ADMIN_NAME", "Rohith")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "Password@123")

settings = Settings()
