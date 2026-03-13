import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os
import json

load_dotenv('/Users/rohithp/Desktop/Hello_Guard_Voice_AI/gard-backend/.env')
uri = os.getenv('MONGODB_URI')
db_name = os.getenv('MONGODB_DATABASE', 'hellogard_db')

async def check():
    client = AsyncIOMotorClient(uri)
    db = client[db_name]
    # In dashboard.py and activity calendar, the API `getCalendarEvents` goes to /api/v1/dashboard/calendar?year=X&month=Y
    print("Test")
    
asyncio.run(check())
