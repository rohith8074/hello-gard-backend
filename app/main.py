from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import dashboard, agents, transcripts, session, websocket, post_call, auth, admin
from app.database import connect_to_mongo, close_mongo_connection, get_database
from app.config import settings
import logging

app = FastAPI(title="HelloGuard Voice AI API")

logger = logging.getLogger(__name__)


async def seed_default_admin():
    """Create the default admin account if it doesn't already exist."""
    from passlib.context import CryptContext
    from datetime import datetime, date
    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    db = get_database()
    existing = await db["login"].find_one({"username": settings.ADMIN_USERNAME})
    if not existing:
        await db["login"].insert_one({
            "username": settings.ADMIN_USERNAME,
            "name": settings.ADMIN_NAME,
            "password_hash": pwd_ctx.hash(settings.ADMIN_PASSWORD),
            "status": "active",
            "role": "admin",
            "created_at": datetime.utcnow(),
            "approved_by": "system",
            "approved_at": datetime.utcnow(),
            "role_changed_by": None,
            "role_changed_at": None,
            "daily_sessions_used": 0,
            "quota_reset_date": str(date.today()),
            "daily_session_limit": 999,
        })
        logger.info("Default admin '%s' created", settings.ADMIN_USERNAME)
    else:
        logger.info("Default admin '%s' already exists", settings.ADMIN_USERNAME)


@app.on_event("startup")
async def startup_event():
    await connect_to_mongo()
    await seed_default_admin()
    logger.info("Voice AI API started")


@app.on_event("shutdown")
async def shutdown_event():
    await close_mongo_connection()
    logger.info("Voice AI API shutting down")


# Enable CORS — origins controlled via CORS_ORIGINS env var
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(post_call.router, prefix="/api/v1", tags=["Post-Call"])
app.include_router(agents.router, prefix="/api/v1")
app.include_router(transcripts.router, prefix="/api/v1", tags=["Transcripts"])
app.include_router(session.router, prefix="/api/v1", tags=["Session"])
app.include_router(websocket.router, tags=["WebSocket"])


@app.get("/")
async def root():
    return {"message": "HelloGuard Voice AI API is running"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
