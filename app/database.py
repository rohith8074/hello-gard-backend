from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings
import logging

logger = logging.getLogger(__name__)

class Database:
    client: AsyncIOMotorClient = None
    
db = Database()

async def connect_to_mongo():
    """Connect to MongoDB"""
    if not settings.MONGODB_URI:
        logger.error("❌ MONGODB_URI is not set in environment variables.")
        raise ValueError("MONGODB_URI environment variable is required")

    try:
        db.client = AsyncIOMotorClient(settings.MONGODB_URI)
        # Test connection
        await db.client.admin.command('ping')
        logger.info(f"✅ Connected to MongoDB: {settings.DATABASE_NAME}")
    except Exception as e:
        logger.error(f"❌ Could not connect to MongoDB: {e}")
        raise

async def close_mongo_connection():
    """Close MongoDB connection"""
    if db.client:
        db.client.close()
        logger.info("MongoDB connection closed")

def get_database():
    """Get database instance"""
    return db.client[settings.DATABASE_NAME]
