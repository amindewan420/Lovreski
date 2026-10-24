"""Firebase Cloud Messaging (Web Push) for Lovreski.

Configuration is stored in MongoDB (`settings` collection, key="firebase") and
managed from the Admin Panel — no .env variables required. The service-account
JSON is encrypted at rest. All functions no-op gracefully when not configured.
"""
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger("lovreski.push")

PRESENCE_TTL = timedelta(seconds=60)
APP_NAME = "lovreski-fcm"
WEB_FIELDS = ("project_id", "api_key", "app_id", "sender_id", "auth_domain", "vapid_key")

_app = None
_app_sig: Optional[str] = None


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ─── Config storage ─────────────────────────────────────────────────────────
async def get_config(db) -> dict:
    return await db.settings.find_one({"key": "firebase"}, {"_id": 0}) or {}


async def save_config(db, fields: dict, service_account: Optional[dict] = None) -> dict:
    from server import encrypt_str
    upd = {k: (fields.get(k) or "").strip() for k in WEB_FIELDS if k in fields and fields.get(k) is not None}
    if service_account is not None:
        upd["service_account_enc"] = encrypt_str(json.dumps(service_account))
        upd["client_email"] = service_account.get("client_email", "")
        upd["sa_project_id"] = service_account.get("project_id", "")
        if not upd.get("project_id") and not (await get_config(db)).get("project_id"):
            upd["project_id"] = service_account.get("project_id", "")
    upd.update({"key": "firebase", "updated_at": _iso(_now())})
    await db.settings.update_one({"key": "firebase"}, {"$set": upd}, upsert=True)
    return await get_config(db)


async def clear_service_account(db) -> None:
    await db.settings.update_one({"key": "firebase"}, {"$unset": {"service_account_enc": "", "client_email": "", "sa_project_id": ""}})


def public_web_config(cfg: dict) -> dict:
    """Web-SDK config (all public by design) — only exposed when complete."""
    ok = all(cfg.get(k) for k in ("project_id", "api_key", "app_id", "sender_id", "vapid_key"))
    if not ok or not cfg.get("service_account_enc"):
        return {"configured": False}
    return {
        "configured": True,
        "apiKey": cfg["api_key"],
        "authDomain": cfg.get("auth_domain") or f"{cfg['project_id']}.firebaseapp.com",
        "projectId": cfg["project_id"],
        "messagingSenderId": cfg["sender_id"],
        "appId": cfg["app_id"],
        "vapidKey": cfg["vapid_key"],
    }


async def is_configured(db) -> bool:
    return bool((await get_config(db)).get("service_account_enc"))


async def get_app(db):
    """Initialize (or re-initialize on config change) a named firebase_admin app."""
    global _app, _app_sig
    cfg = await get_config(db)
    enc = cfg.get("service_account_enc")
    if not enc:
        return None
    if _app is not None and _app_sig == enc:
        return _app
    try:
        import firebase_admin
        from firebase_admin import credentials
        from server import decrypt_str
        if _app is not None:
            try:
                firebase_admin.delete_app(_app)
            except Exception:
                pass
        svc = json.loads(decrypt_str(enc))
        _app = firebase_admin.initialize_app(credentials.Certificate(svc), name=APP_NAME)
        _app_sig = enc
        logger.info("[push] Firebase Admin initialized (project=%s)", svc.get("project_id"))
        return _app
    except Exception as e:
        _app, _app_sig = None, None
        logger.warning("[push] Firebase init failed: %s", e)
        return None


def validate_service_account(svc: dict) -> Optional[str]:
    if not isinstance(svc, dict) or svc.get("type") != "service_account":
        return "Файл не является service account JSON (type != service_account)"
    for k in ("project_id", "private_key", "client_email"):
        if not svc.get(k):
            return f"В файле отсутствует поле {k}"
    try:
        from firebase_admin import credentials
        credentials.Certificate(svc)
    except Exception as e:
        return f"Некорректный ключ: {e}"
    return None


# ─── Presence & preferences ─────────────────────────────────────────────────
async def should_push(db, user_id: str, ws_manager=None) -> bool:
    if ws_manager is not None and ws_manager.is_online(user_id):
        return False
    u = await db.users.find_one({"user_id": user_id}, {"_id": 0, "last_active": 1, "is_online": 1})
    if not u or u.get("is_online"):
        return False
    la = u.get("last_active")
    if not la:
        return True
    try:
        dt = datetime.fromisoformat(str(la).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (_now() - dt) > PRESENCE_TTL
    except Exception:
        return True


PREF_DEFAULTS = {"messages": True, "likes": True, "matches": True, "visits": True, "announcements": True}


async def pref_enabled(db, user_id: str, pref: str) -> bool:
    u = await db.users.find_one({"user_id": user_id}, {"_id": 0, "notif_push": 1}) or {}
    prefs = u.get("notif_push") or {}
    return bool(prefs.get(pref, PREF_DEFAULTS.get(pref, True)))


# ─── Token storage ──────────────────────────────────────────────────────────
async def save_token(db, user_id: str, token: str, platform: str = "web", user_agent: str = "") -> None:
    await db.push_tokens.update_one(
        {"token": token},
        {
            "$set": {"user_id": user_id, "token": token, "platform": platform,
                     "user_agent": user_agent[:200], "last_seen": _iso(_now())},
            "$setOnInsert": {"created_at": _iso(_now())},
        },
        upsert=True,
    )


async def remove_token(db, user_id: str, token: str) -> None:
    await db.push_tokens.delete_one({"user_id": user_id, "token": token})


async def _get_tokens(db, user_id: str) -> list[str]:
    docs = await db.push_tokens.find({"user_id": user_id}, {"_id": 0, "token": 1}).to_list(200)
    return [d["token"] for d in docs if d.get("token")]


# ─── Core send ──────────────────────────────────────────────────────────────
async def send_to_user(db, user_id: str, *, title: str, body: str, url: str = "/",
                       kind: str = "info", tag: Optional[str] = None,
                       extra_data: Optional[dict] = None, pref: Optional[str] = None) -> dict:
    """Send a Web Push to all of a user's tokens. Never raises."""
    if pref and not await pref_enabled(db, user_id, pref):
        return {"sent": 0, "reason": "pref-disabled"}
    app = await get_app(db)
    if app is None:
        return {"sent": 0, "reason": "not-configured"}
    tokens = await _get_tokens(db, user_id)
    if not tokens:
        return {"sent": 0, "reason": "no-tokens"}
    from firebase_admin import messaging
    data_payload = {"type": kind, "title": title[:200], "body": body[:200], "url": url, "tag": tag or kind}
    for k, v in (extra_data or {}).items():
        data_payload[str(k)] = str(v)
    sent, stale, last_err = 0, [], None
    for tk in tokens:
        try:
            # Data-only message: the service worker renders it and handles click-to-navigate.
            messaging.send(messaging.Message(
                token=tk, data=data_payload,
                webpush=messaging.WebpushConfig(headers={"Urgency": "high"}),
            ), app=app)
            sent += 1
        except Exception as e:
            err_name = type(e).__name__
            last_err = f"{err_name}: {e}"
            if "Unregistered" in err_name or "SenderIdMismatch" in err_name or "not a valid FCM registration token" in str(e):
                stale.append(tk)
            else:
                logger.warning("[push] send error for token %s...: %s", tk[:16], e)
    if stale:
        await db.push_tokens.delete_many({"user_id": user_id, "token": {"$in": stale}})
    out = {"sent": sent, "removed_stale": len(stale)}
    if not sent and last_err:
        out["error"] = last_err[:300]
    return out


async def broadcast_to_admins(db, *, title: str, body: str, url: str = "/admin", kind: str = "admin") -> dict:
    admins = await db.users.find({"is_admin": True}, {"_id": 0, "user_id": 1}).to_list(50)
    total = 0
    for a in admins:
        total += (await send_to_user(db, a["user_id"], title=title, body=body, url=url, kind=kind)).get("sent", 0)
    return {"sent": total, "admins": len(admins)}


async def broadcast_announcement(db, *, title: str, body: str, url: str = "/home") -> dict:
    ids = await db.push_tokens.distinct("user_id")
    sent = users = 0
    for uid in ids:
        r = await send_to_user(db, uid, title=title, body=body, url=url, kind="announcement", pref="announcements")
        if r.get("sent"):
            users += 1
            sent += r["sent"]
    return {"sent": sent, "users": users}


# ─── High-level event helpers ───────────────────────────────────────────────
async def notify_chat_message(db, ws_manager, recipient_id: str, sender_name: str,
                              preview: str, other_id: str) -> None:
    if not await should_push(db, recipient_id, ws_manager):
        return
    await send_to_user(
        db, recipient_id, title=f"💬 {sender_name}", body=preview or "Новое сообщение",
        url=f"/chats/{other_id}", kind="chat", tag=f"chat-{other_id}",
        extra_data={"other_id": other_id}, pref="messages",
    )


async def notify_like(db, user_id: str, liker_name: str, liker_id: str) -> None:
    await send_to_user(
        db, user_id, title="❤️ Новый лайк", body=f"{liker_name} лайкнул(а) вашу анкету",
        url="/likes", kind="like", tag=f"like-{liker_id}", pref="likes",
    )


async def notify_match(db, user_id: str, other_name: str, other_id: str) -> None:
    await send_to_user(
        db, user_id, title="💘 Взаимная симпатия!", body=f"Вы понравились {other_name}. Начните общение!",
        url=f"/chats/{other_id}", kind="match", tag=f"match-{other_id}",
        extra_data={"other_id": other_id}, pref="matches",
    )


async def notify_visit(db, user_id: str, visitor_name: str, visitor_id: str) -> None:
    await send_to_user(
        db, user_id, title="👀 Новый гость", body=f"{visitor_name} посетил(а) ваш профиль",
        url=f"/profile/{visitor_id}", kind="visit", tag=f"visit-{visitor_id}", pref="visits",
    )


async def notify_payment(db, user_id: str, message: str, success: bool = True) -> None:
    await send_to_user(
        db, user_id, title="✅ Платёж" if success else "❌ Платёж", body=message,
        url="/premium", kind="payment_success" if success else "payment_failed",
    )


async def notify_admin_new_submission(db, kind: str, from_user_name: str) -> None:
    labels = {
        "receipt": ("💰 Новый платёж на проверку", "/admin"),
        "report": ("⚠️ Новая жалоба на пользователя", "/admin"),
        "refund": ("💸 Новый запрос на возврат", "/admin"),
    }
    title, url = labels.get(kind, ("🔔 Новое событие", "/admin"))
    await broadcast_to_admins(db, title=title, body=f"От: {from_user_name}", url=url, kind="admin")
