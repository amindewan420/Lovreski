"""Firebase Cloud Messaging (Web Push) integration for Lovreski.

Design goals:
- Fail-safe: if Firebase is not configured (env vars missing), all functions
  no-op gracefully so the rest of the app keeps working. This lets us ship
  the scaffold before the user pastes their Firebase credentials.
- Presence-aware: only send FCM when the recipient's WebSocket has been idle
  > PRESENCE_TTL. Foreground users already get real-time WS updates.
- Multi-device: each user can register multiple browser tokens; stale ones
  are pruned when FCM reports UnregisteredError.

Env vars (in /app/backend/.env):
  FIREBASE_PROJECT_ID              - your Firebase project id (also enables FCM)
  FIREBASE_SERVICE_ACCOUNT_JSON    - the ENTIRE service-account JSON (inline)
                                     OR
  GOOGLE_APPLICATION_CREDENTIALS   - absolute path to the service-account file
"""
from __future__ import annotations
import os
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger("lovreski.push")

# Presence: skip FCM if the user has an active WS or pinged within this window.
PRESENCE_TTL = timedelta(seconds=60)

_fcm_ready = False


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def is_configured() -> bool:
    """Return True if Firebase credentials are present in the environment."""
    if not os.environ.get("FIREBASE_PROJECT_ID"):
        return False
    return bool(
        os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
        or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    )


def init_fcm() -> bool:
    """Initialize firebase-admin once. Safe to call multiple times."""
    global _fcm_ready
    if _fcm_ready:
        return True
    if not is_configured():
        logger.info("[push] Firebase not configured — FCM disabled (in-app notifications still work)")
        return False
    try:
        import firebase_admin
        from firebase_admin import credentials
        if firebase_admin._apps:
            _fcm_ready = True
            return True
        inline_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
        if inline_json:
            svc = json.loads(inline_json)
            firebase_admin.initialize_app(credentials.Certificate(svc))
        else:
            # GOOGLE_APPLICATION_CREDENTIALS path — firebase_admin picks it up automatically.
            firebase_admin.initialize_app()
        _fcm_ready = True
        logger.info("[push] Firebase Admin initialized (project=%s)", os.environ.get("FIREBASE_PROJECT_ID"))
        return True
    except Exception as e:
        logger.warning("[push] Firebase init failed: %s", e)
        return False


# ─── Presence check (called before every FCM send) ─────────────────────────
async def should_push(db, user_id: str, ws_manager=None) -> bool:
    """Return True when the user is not actively connected AND has been idle
    more than PRESENCE_TTL. `ws_manager` is the in-process WSManager singleton."""
    if ws_manager is not None and ws_manager.is_online(user_id):
        return False
    u = await db.users.find_one({"user_id": user_id}, {"_id": 0, "last_active": 1, "is_online": 1})
    if not u:
        return False
    if u.get("is_online"):
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


# ─── Token storage ──────────────────────────────────────────────────────────
async def save_token(db, user_id: str, token: str, platform: str = "web", user_agent: str = "") -> None:
    await db.push_tokens.update_one(
        {"token": token},
        {
            "$set": {
                "user_id": user_id,
                "token": token,
                "platform": platform,
                "user_agent": user_agent[:200],
                "last_seen": _iso(_now()),
            },
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
async def send_to_user(
    db,
    user_id: str,
    *,
    title: str,
    body: str,
    url: str = "/",
    kind: str = "info",
    tag: Optional[str] = None,
    extra_data: Optional[dict] = None,
) -> dict:
    """Send a Web Push to all of a user's registered tokens.
    Returns {sent, removed_stale, reason}.  Never raises."""
    if not init_fcm():
        return {"sent": 0, "reason": "not-configured"}
    tokens = await _get_tokens(db, user_id)
    if not tokens:
        return {"sent": 0, "reason": "no-tokens"}
    try:
        from firebase_admin import messaging
    except Exception as e:
        logger.warning("[push] messaging import failed: %s", e)
        return {"sent": 0, "reason": "sdk-error"}
    sent = 0
    stale: list[str] = []
    data_payload = {
        "type": kind,
        "title": title[:200],
        "body": body[:200],
        "url": url,
    }
    if extra_data:
        # FCM data payload values MUST be strings.
        for k, v in extra_data.items():
            data_payload[str(k)] = str(v)
    for tk in tokens:
        try:
            msg = messaging.Message(
                token=tk,
                notification=messaging.Notification(title=title[:200], body=body[:400]),
                data=data_payload,
                webpush=messaging.WebpushConfig(
                    fcm_options=messaging.WebpushFCMOptions(link=url),
                    notification=messaging.WebpushNotification(
                        title=title[:200], body=body[:400], tag=tag or kind, icon="/logo192.png"
                    ),
                ),
            )
            messaging.send(msg)
            sent += 1
        except Exception as e:
            # UnregisteredError / invalid tokens → prune
            err_name = type(e).__name__
            if "Unregistered" in err_name or "InvalidArgumentError" in err_name or "invalid" in str(e).lower():
                stale.append(tk)
            else:
                logger.warning("[push] send error for token %s...: %s", tk[:16], e)
    if stale:
        await db.push_tokens.delete_many({"user_id": user_id, "token": {"$in": stale}})
    return {"sent": sent, "removed_stale": len(stale)}


async def broadcast_to_admins(db, *, title: str, body: str, url: str = "/admin", kind: str = "admin") -> dict:
    admins = await db.users.find({"is_admin": True}, {"_id": 0, "user_id": 1}).to_list(50)
    total_sent = 0
    for a in admins:
        r = await send_to_user(db, a["user_id"], title=title, body=body, url=url, kind=kind)
        total_sent += r.get("sent", 0)
    return {"sent": total_sent, "admins": len(admins)}


# ─── High-level event helpers (used by the app code) ────────────────────────
async def notify_chat_message(db, ws_manager, recipient_id: str, sender_name: str,
                              preview: str, other_id: str) -> None:
    """Recipient gets a push only if not actively connected."""
    if not await should_push(db, recipient_id, ws_manager):
        return
    await send_to_user(
        db, recipient_id,
        title=f"💬 {sender_name}",
        body=preview or "Новое сообщение",
        url=f"/chats/{other_id}",
        kind="chat",
        tag=f"chat-{other_id}",
        extra_data={"other_id": other_id, "sender_name": sender_name},
    )


async def notify_match(db, user_id: str, other_name: str, other_id: str) -> None:
    await send_to_user(
        db, user_id,
        title="💘 Взаимная симпатия!",
        body=f"Вы понравились {other_name}. Начните общение!",
        url=f"/profile/{other_id}",
        kind="match",
        tag=f"match-{other_id}",
        extra_data={"other_id": other_id},
    )


async def notify_payment(db, user_id: str, message: str, success: bool = True) -> None:
    await send_to_user(
        db, user_id,
        title="✅ Платёж" if success else "❌ Платёж",
        body=message,
        url="/premium",
        kind="payment_success" if success else "payment_failed",
    )


async def notify_admin_new_submission(db, kind: str, from_user_name: str) -> None:
    """Alert admins about new admin-actionable events (payments, reports)."""
    labels = {
        "receipt": ("💰 Новый платёж на проверку", "/admin"),
        "report": ("⚠️ Новая жалоба на пользователя", "/admin"),
        "refund": ("💸 Новый запрос на возврат", "/admin"),
    }
    title, url = labels.get(kind, ("🔔 Новое событие", "/admin"))
    await broadcast_to_admins(db, title=title, body=f"От: {from_user_name}", url=url, kind="admin")
