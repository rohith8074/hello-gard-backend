from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import dashboard, agents, transcripts, session, websocket, post_call, auth, admin, kb_pages
from app.database import connect_to_mongo, close_mongo_connection, get_database
from app.config import settings
import logging

app = FastAPI(title="HelloGuard Voice AI API")

logger = logging.getLogger(__name__)


async def seed_default_admin():
    """Create the default admin account if it doesn't already exist."""
    import bcrypt
    from datetime import datetime, date
    db = get_database()
    existing = await db["login"].find_one({"username": settings.ADMIN_USERNAME})
    if not existing:
        # Direct bcrypt hashing
        salt = bcrypt.gensalt()
        pwd_bytes = settings.ADMIN_PASSWORD.encode('utf-8')
        hashed_password = bcrypt.hashpw(pwd_bytes, salt).decode('utf-8')

        await db["login"].insert_one({
            "username": settings.ADMIN_USERNAME,
            "name": settings.ADMIN_NAME,
            "password_hash": hashed_password,
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


from fastapi import Request
from fastapi.responses import JSONResponse

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception caught: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "error": str(exc)},
    )

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
app.include_router(kb_pages.router, prefix="/api/v1", tags=["KB Pages"])


@app.get("/")
async def root():
    return {"message": "HelloGuard Voice AI API is running"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
