from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import bcrypt
from datetime import datetime, date
from app.database import get_database
from app.middleware.auth_deps import create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["Auth"])


class RegisterRequest(BaseModel):
    username: str
    name: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/register")
async def register(body: RegisterRequest):
    db = get_database()

    if len(body.username.strip()) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    existing = await db["login"].find_one({"username": body.username.lower().strip()})
    if existing:
        raise HTTPException(status_code=409, detail="Username already taken")

    # Direct bcrypt hashing
    salt = bcrypt.gensalt()
    pwd_bytes = body.password.encode('utf-8')
    hashed_password = bcrypt.hashpw(pwd_bytes, salt).decode('utf-8')

    user = {
        "username": body.username.lower().strip(),
        "name": body.name.strip(),
        "password_hash": hashed_password,
        "status": "pending",          # waits for admin approval
        "role": "operator",           # default role
        "created_at": datetime.utcnow(),
        "approved_by": None,
        "approved_at": None,
        "role_changed_by": None,
        "role_changed_at": None,
        "daily_sessions_used": 0,
        "quota_reset_date": str(date.today()),
        "daily_session_limit": 5,
    }
    await db["login"].insert_one(user)
    return {"message": "Registration successful. Waiting for admin approval."}


@router.post("/login")
async def login(body: LoginRequest):
    db = get_database()
    user = await db["login"].find_one({"username": body.username.lower().strip()})

    # Direct bcrypt verification
    if user:
        pwd_bytes = body.password.encode('utf-8')
        hash_bytes = user["password_hash"].encode('utf-8')
        is_valid = bcrypt.checkpw(pwd_bytes, hash_bytes)
    else:
        is_valid = False

    if not user or not is_valid:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_access_token({"sub": user["username"]})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": str(user["_id"]),
            "username": user["username"],
            "name": user["name"],
            "role": user["role"],
            "status": user["status"],
        }
    }


@router.get("/me")
async def me(current_user: dict = Depends(get_current_user)):
    return {
        "id": current_user["_id"],
        "username": current_user["username"],
        "name": current_user["name"],
        "role": current_user["role"],
        "status": current_user["status"],
        "daily_sessions_used": current_user.get("daily_sessions_used", 0),
        "daily_session_limit": current_user.get("daily_session_limit", 5),
    }
