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
    out["devices"] = await db.push_tokens.count_documents({"user_id": {"$ne": fcm.ADMIN_UID}})
    out["subscribed_users"] = len([i for i in await db.push_tokens.distinct("user_id") if i != fcm.ADMIN_UID])
    out["admin_devices"] = await db.push_tokens.count_documents({"user_id": fcm.ADMIN_UID})
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


# ─── Admin-Panel devices (admin alerts) ────────────────────────────────────
@api.post("/admin/push/token")
async def admin_push_save_token(body: PushTokenBody, request: Request, admin: dict = Depends(require_admin)):
    await fcm.save_token(db, fcm.ADMIN_UID, body.token, "admin-web", request.headers.get("user-agent", ""))
    return {"ok": True, "devices": await db.push_tokens.count_documents({"user_id": fcm.ADMIN_UID})}


@api.delete("/admin/push/token")
async def admin_push_delete_token(body: PushTokenBody, admin: dict = Depends(require_admin)):
    await fcm.remove_token(db, fcm.ADMIN_UID, body.token)
    return {"ok": True}


@api.post("/admin/push/test-self")
async def admin_push_test_self(admin: dict = Depends(require_admin)):
    return await fcm.broadcast_to_admins(db, title="🧪 Тест админ-уведомлений",
                                         body="Уведомления о чеках, возвратах, жалобах и входах работают.", kind="test")


async def _log_push(kind: str, title: str, body: str, target: str, **extra) -> str:
    pid = f"pl_{uuid.uuid4().hex[:12]}"
    await db.push_log.insert_one({"id": pid, "kind": kind, "title": title, "body": body, "target": target,
                                  "status": "sending", "sent": 0, "created_at": iso(now_utc()), **extra})
    return pid


@api.get("/admin/push/history")
async def admin_push_history(limit: int = 50, admin: dict = Depends(require_admin)):
    return await db.push_log.find({}, {"_id": 0}).sort("created_at", -1).to_list(min(max(limit, 1), 200))


class DirectPushBody(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1, max_length=300)


@api.post("/admin/push/user/{user_id}")
async def admin_push_user(user_id: str, body: DirectPushBody, admin: dict = Depends(require_admin)):
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0, "name": 1, "email": 1})
    if not target:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    await db.notifications.insert_one({
        "id": f"n_{uuid.uuid4().hex[:12]}", "user_id": user_id, "message": f"✉️ {body.title}: {body.body}",
        "kind": "admin_message", "read": False, "created_at": iso(now_utc()),
    })
    r = await fcm.send_to_user(db, user_id, title=f"✉️ {body.title}", body=body.body, url="/home", kind="admin_message")
    status = "sent" if r.get("sent") else (r.get("reason") or "failed")
    pid = await _log_push("direct", body.title, body.body, target.get("name") or target.get("email") or user_id,
                          target_user_id=user_id)
    await db.push_log.update_one({"id": pid}, {"$set": {"status": status, "sent": r.get("sent", 0)}})
    return {"ok": True, "in_app": True, "push": r}


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
    devices = await db.push_tokens.count_documents({"user_id": {"$ne": fcm.ADMIN_UID}})
    pid = await _log_push("announcement", body.title, body.body, "Все пользователи", in_app=len(users), devices=devices)

    async def _run():
        try:
            r = await fcm.broadcast_announcement(db, title=f"📣 {body.title}", body=body.body, url=url)
            await db.push_log.update_one({"id": pid}, {"$set": {"status": "sent", "sent": r.get("sent", 0), "users": r.get("users", 0)}})
            logger.info(f"[push] announcement by {admin['user_id']}: {r}")
        except Exception as e:
            await db.push_log.update_one({"id": pid}, {"$set": {"status": "failed"}})
            logger.warning(f"[push] announcement failed: {e}")
    asyncio.create_task(_run())
    return {"ok": True, "in_app": len(users), "queued_devices": devices}
