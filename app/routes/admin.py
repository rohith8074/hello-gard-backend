from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from datetime import datetime, date
from bson import ObjectId
from app.database import get_database
from app.middleware.auth_deps import require_admin

router = APIRouter(prefix="/admin", tags=["Admin"])


def _serialize_user(u: dict) -> dict:
    return {
        "id": str(u["_id"]),
        "username": u["username"],
        "name": u["name"],
        "role": u["role"],
        "status": u["status"],
        "created_at": u.get("created_at", "").isoformat() if u.get("created_at") else None,
        "approved_by": u.get("approved_by"),
        "approved_at": u.get("approved_at", "").isoformat() if u.get("approved_at") else None,
        "daily_sessions_used": u.get("daily_sessions_used", 0),
        "daily_session_limit": u.get("daily_session_limit", 5),
        "quota_reset_date": u.get("quota_reset_date"),
    }


@router.get("/users")
async def list_users(admin: dict = Depends(require_admin)):
    db = get_database()
    users = await db["login"].find({}).sort("created_at", -1).to_list(200)
    return {"users": [_serialize_user(u) for u in users]}


@router.patch("/users/{user_id}/approve")
async def approve_user(user_id: str, admin: dict = Depends(require_admin)):
    db = get_database()
    user = await db["login"].find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user["status"] == "active":
        raise HTTPException(status_code=400, detail="User already active")

    await db["login"].update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {
            "status": "active",
            "approved_by": admin["username"],
            "approved_at": datetime.utcnow(),
        }}
    )
    return {"message": f"User {user['username']} approved"}


@router.patch("/users/{user_id}/role")
async def toggle_role(user_id: str, admin: dict = Depends(require_admin)):
    db = get_database()
    user = await db["login"].find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent removing the last admin
    if user["role"] == "admin":
        admin_count = await db["login"].count_documents({"role": "admin", "status": "active"})
        if admin_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot remove the last admin")

    new_role = "admin" if user["role"] == "operator" else "operator"
    await db["login"].update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {
            "role": new_role,
            "role_changed_by": admin["username"],
            "role_changed_at": datetime.utcnow(),
        }}
    )
    return {"message": f"Role updated to {new_role}", "new_role": new_role}


@router.delete("/users/{user_id}/reject")
async def reject_user(user_id: str, admin: dict = Depends(require_admin)):
    """Permanently delete a pending user registration (rejection)."""
    db = get_database()
    user = await db["login"].find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user["status"] != "pending":
        raise HTTPException(status_code=400, detail="Only pending users can be rejected")
    await db["login"].delete_one({"_id": ObjectId(user_id)})
    return {"message": f"User {user['username']} rejected and removed"}


@router.patch("/users/{user_id}/suspend")
async def toggle_suspend(user_id: str, admin: dict = Depends(require_admin)):
    db = get_database()
    user = await db["login"].find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Cannot suspend yourself
    if str(user["_id"]) == admin["_id"]:
        raise HTTPException(status_code=400, detail="Cannot suspend your own account")

    new_status = "suspended" if user["status"] == "active" else "active"
    await db["login"].update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"status": new_status}}
    )
    return {"message": f"User {user['username']} is now {new_status}", "new_status": new_status}
