"""Notifications + Push subscription routes."""
from fastapi import HTTPException, Depends, Request
from pydantic import BaseModel, Field
import os
from server import (
    api, db, logger, now_utc, iso, fcm,
    get_current_user, _push_notification,
)

@api.get("/notifications")
async def my_notifications(user: dict = Depends(get_current_user)):
    """Return the user's recent notifications and mark them as read."""
    notes = await db.notifications.find({"user_id": user['user_id']}, {"_id": 0}).sort("created_at", -1).to_list(50)
    await db.notifications.update_many({"user_id": user['user_id'], "read": False}, {"$set": {"read": True}})
    return notes
# ─── Push Notification Endpoints (FCM tokens) ─────────────────────────────
class PushTokenBody(BaseModel):
    token: str = Field(min_length=20, max_length=4096)
    platform: str = "web"


@api.get("/push/status")
async def push_status(user: dict = Depends(get_current_user)):
    """Reports whether FCM is configured on the server and if the caller has any tokens saved."""
    configured = fcm.is_configured()
    token_count = await db.push_tokens.count_documents({"user_id": user['user_id']})
    return {
        "configured": configured,
        "vapid_public_key": os.environ.get("FIREBASE_VAPID_PUBLIC_KEY", ""),
        "token_count": token_count,
    }


@api.post("/push/token")
async def push_save_token(body: PushTokenBody, request: Request, user: dict = Depends(get_current_user)):
    ua = request.headers.get("user-agent", "")
    await fcm.save_token(db, user['user_id'], body.token, body.platform, ua)
    return {"ok": True}


@api.delete("/push/token")
async def push_delete_token(body: PushTokenBody, user: dict = Depends(get_current_user)):
    await fcm.remove_token(db, user['user_id'], body.token)
    return {"ok": True}


@api.post("/push/test")
async def push_test(user: dict = Depends(get_current_user)):
    """Send a test push to the current user's registered devices."""
    r = await fcm.send_to_user(
        db, user['user_id'],
        title="🧪 Тестовое уведомление",
        body="Push-уведомления работают! Вы получите такие же сообщения о новых чатах и совпадениях.",
        url="/settings",
        kind="test",
    )
    return r
