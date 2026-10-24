"""Notifications + Push (FCM) routes, incl. Admin-Panel Firebase configuration."""
from fastapi import HTTPException, Depends, Request
from pydantic import BaseModel, Field
from typing import Optional
import asyncio, json, uuid
from server import (
    api, db, logger, now_utc, iso, fcm,
    get_current_user, require_admin,
)

@api.get("/notifications")
async def my_notifications(user: dict = Depends(get_current_user)):
    """Return the user's recent notifications and mark them as read."""
    notes = await db.notifications.find({"user_id": user['user_id']}, {"_id": 0}).sort("created_at", -1).to_list(50)
    await db.notifications.update_many({"user_id": user['user_id'], "read": False}, {"$set": {"read": True}})
    return notes


class PushTokenBody(BaseModel):
    token: str = Field(min_length=20, max_length=4096)
    platform: str = "web"


@api.get("/push/config")
async def push_public_config():
    """Public Firebase Web-SDK config (apiKey/appId/VAPID are public by design)."""
    return fcm.public_web_config(await fcm.get_config(db))


@api.get("/push/status")
async def push_status(user: dict = Depends(get_current_user)):
    cfg = fcm.public_web_config(await fcm.get_config(db))
    token_count = await db.push_tokens.count_documents({"user_id": user['user_id']})
    return {"configured": cfg["configured"], "vapid_public_key": cfg.get("vapidKey", ""), "token_count": token_count}


@api.post("/push/token")
async def push_save_token(body: PushTokenBody, request: Request, user: dict = Depends(get_current_user)):
    await fcm.save_token(db, user['user_id'], body.token, body.platform, request.headers.get("user-agent", ""))
    return {"ok": True}


@api.delete("/push/token")
async def push_delete_token(body: PushTokenBody, user: dict = Depends(get_current_user)):
    await fcm.remove_token(db, user['user_id'], body.token)
    return {"ok": True}


@api.post("/push/test")
async def push_test(user: dict = Depends(get_current_user)):
    return await fcm.send_to_user(
        db, user['user_id'],
        title="🧪 Тестовое уведомление",
        body="Push-уведомления работают! Нажмите, чтобы открыть настройки.",
        url="/settings", kind="test",
    )


# ─── Admin: Firebase configuration ─────────────────────────────────────────
class FirebaseConfigBody(BaseModel):
    project_id: Optional[str] = Field(default=None, max_length=200)
    api_key: Optional[str] = Field(default=None, max_length=200)
    app_id: Optional[str] = Field(default=None, max_length=200)
    sender_id: Optional[str] = Field(default=None, max_length=100)
    auth_domain: Optional[str] = Field(default=None, max_length=200)
    vapid_key: Optional[str] = Field(default=None, max_length=300)
    service_account_json: Optional[str] = Field(default=None, max_length=20000)


def _admin_view(cfg: dict) -> dict:
    out = {k: cfg.get(k, "") for k in fcm.WEB_FIELDS}
    out.update({
        "has_service_account": bool(cfg.get("service_account_enc")),
        "client_email": cfg.get("client_email", ""),
        "sa_project_id": cfg.get("sa_project_id", ""),
        "updated_at": cfg.get("updated_at"),
        "ready": fcm.public_web_config(cfg)["configured"],
    })
    return out


@api.get("/admin/push/config")
async def admin_push_config(admin: dict = Depends(require_admin)):
    cfg = await fcm.get_config(db)
    out = _admin_view(cfg)
    out["devices"] = await db.push_tokens.count_documents({})
    out["subscribed_users"] = len(await db.push_tokens.distinct("user_id"))
    return out


@api.put("/admin/push/config")
async def admin_push_config_save(body: FirebaseConfigBody, admin: dict = Depends(require_admin)):
    svc = None
    if body.service_account_json:
        try:
            svc = json.loads(body.service_account_json)
        except Exception:
            raise HTTPException(status_code=400, detail="Файл не является корректным JSON")
        err = fcm.validate_service_account(svc)
        if err:
            raise HTTPException(status_code=400, detail=err)
    fields = body.model_dump(exclude={"service_account_json"}, exclude_none=True)
    cfg = await fcm.save_config(db, fields, svc)
    await db.admin_audit.insert_one({"id": f"au_{uuid.uuid4().hex[:10]}", "admin": admin['user_id'],
                                     "action": "firebase_config_update", "created_at": iso(now_utc())})
    return _admin_view(cfg)


@api.delete("/admin/push/service-account")
async def admin_push_sa_delete(admin: dict = Depends(require_admin)):
    await fcm.clear_service_account(db)
    return _admin_view(await fcm.get_config(db))


class AnnouncementBody(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1, max_length=300)
    url: Optional[str] = Field(default="/home", max_length=200)


@api.post("/admin/push/announce")
async def admin_push_announce(body: AnnouncementBody, admin: dict = Depends(require_admin)):
    url = body.url if (body.url or "").startswith("/") else "/home"
    users = await db.users.find({"is_admin": {"$ne": True}}, {"_id": 0, "user_id": 1}).to_list(100000)
    now = iso(now_utc())
    if users:
        await db.notifications.insert_many([{
            "id": f"n_{uuid.uuid4().hex[:12]}", "user_id": u['user_id'],
            "message": f"📣 {body.title}: {body.body}", "kind": "announcement",
            "read": False, "created_at": now,
        } for u in users])
    devices = await db.push_tokens.count_documents({})

    async def _run():
        try:
            r = await fcm.broadcast_announcement(db, title=f"📣 {body.title}", body=body.body, url=url)
            logger.info(f"[push] announcement by {admin['user_id']}: {r}")
        except Exception as e:
            logger.warning(f"[push] announcement failed: {e}")
    asyncio.create_task(_run())
    return {"ok": True, "in_app": len(users), "queued_devices": devices}
