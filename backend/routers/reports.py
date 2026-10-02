"""Report + Block routes."""
import uuid
from fastapi import Depends
from server import (
    api, db, logger, now_utc, iso, fcm,
    get_current_user, ReportBody,
)

@api.post("/report")
async def report_user(body: ReportBody, user: dict = Depends(get_current_user)):
    await db.reports.insert_one({
        "report_id": f"rep_{uuid.uuid4().hex[:12]}",
        "from_user": user['user_id'],
        "target_user": body.target_user_id,
        "reason": body.reason,
        "status": "open",
        "created_at": iso(now_utc()),
    })
    try:
        await fcm.notify_admin_new_submission(db, "report", user.get("name") or user.get("email") or "user")
    except Exception as e:
        logger.warning(f"[push] admin report notify failed: {e}")
    return {"ok": True}

@api.post("/block/{target_id}")
async def block(target_id: str, user: dict = Depends(get_current_user)):
    await db.users.update_one({"user_id": user['user_id']}, {"$addToSet": {"blocked": target_id}})
    return {"ok": True}
