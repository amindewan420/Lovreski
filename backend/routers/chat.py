"""Chat routes — /chats/*, /messages/*, /chat/*, /gifts"""
from fastapi import HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime, timezone
import io, base64, uuid
from server import (
    api, db, logger, now_utc, iso, fcm, ws_manager,
    get_current_user, user_public,
    chat_id, _decorate_msg, _do_send_message, _compress_image_data_url,
    gridfs_put, gridfs_url, store_data_url_in_gridfs, sign_file_url, storage_put,
    MessageBody, GIFT_CATALOG, MSG_COST, FREE_MSGS,
)

@api.get("/chats")
async def list_chats(user: dict = Depends(get_current_user)):
    uid = user['user_id']
    # 1) Latest message per chat (single query, dedup client-side).
    msgs = await db.messages.find({"participants": uid}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    chats: dict[str, dict] = {}
    for m in msgs:
        cid = m['chat_id']
        if cid not in chats:
            chats[cid] = m
    if not chats:
        return []
    # 2) Batch-fetch every partner user in ONE query (fixes N+1).
    other_ids = list({[p for p in last['participants'] if p != uid][0] for last in chats.values()})
    others = await db.users.find(
        {"user_id": {"$in": other_ids}},
        {"_id": 0, "password_hash": 0},
    ).to_list(len(other_ids) + 10)
    others_by_id = {o['user_id']: o for o in others}
    # 3) Batch-count unread per chat via aggregation (one query total).
    pipeline = [
        {"$match": {"to_user": uid, "read": False, "chat_id": {"$in": list(chats.keys())}}},
        {"$group": {"_id": "$chat_id", "n": {"$sum": 1}}},
    ]
    unread_by_chat = {row["_id"]: row["n"] async for row in db.messages.aggregate(pipeline)}
    # 4) Assemble result
    result = []
    for cid, last in chats.items():
        other_id = [p for p in last['participants'] if p != uid][0]
        other = others_by_id.get(other_id)
        if not other:
            continue
        result.append({
            "chat_id": cid,
            "user": user_public(other, viewer=user),
            "last_message": last,
            "unread": unread_by_chat.get(cid, 0),
        })
    result.sort(key=lambda x: x['last_message']['created_at'], reverse=True)
    return result
@api.get("/chats/{other_id}/messages")
async def get_messages(other_id: str, user: dict = Depends(get_current_user), limit: int = 200):
    cid = chat_id(user['user_id'], other_id)
    uid = user['user_id']
    msgs = await db.messages.find(
        {"chat_id": cid, "hidden_for": {"$ne": uid}},
        {"_id": 0}
    ).sort("created_at", 1).to_list(limit)
    await db.messages.update_many({"chat_id": cid, "to_user": uid, "deleted": {"$ne": True}}, {"$set": {"read": True}})
    is_premium = bool(user.get('is_premium'))
    partner_seen = 0
    for m in msgs:
        m.pop('_id', None)
        # Normalize deleted-for-everyone messages so the client can render a placeholder
        if m.get('deleted'):
            m['text'] = ''
            m['media_url'] = None
            m['file_name'] = None
            m['gift_key'] = None
            m['locked'] = False
            continue
        if m.get('from_user') != uid:
            partner_seen += 1
            if not is_premium and partner_seen > FREE_MSGS:
                m['locked'] = True
                m['text'] = ''
                m['media_url'] = None
            else:
                m['locked'] = False
        else:
            m['locked'] = False
        # Media is served via short-lived signed URLs (files router enforces access)
        if m.get('media_url'):
            m['media_url'] = sign_file_url(m['media_url'])
    return msgs

@api.delete("/messages/{message_id}")
async def delete_message(message_id: str, scope: str = "me", user: dict = Depends(get_current_user)):
    """Delete a message.

    - scope='me'       → hide only for the current user (any message the user can see).
    - scope='everyone' → tombstone the message for both participants. Allowed only
                          within 1 hour of send and only by the sender (or an admin).
                          Broadcasts a WS `message_deleted` event.
    """
    if scope not in {"me", "everyone"}:
        raise HTTPException(status_code=400, detail="Invalid scope")
    m = await db.messages.find_one({"message_id": message_id}, {"_id": 0})
    if not m:
        raise HTTPException(status_code=404, detail="Message not found")
    uid = user['user_id']
    is_admin = bool(user.get('is_admin'))
    if uid not in (m.get('participants') or []) and not is_admin:
        raise HTTPException(status_code=403, detail="Not your chat")

    if scope == "me":
        await db.messages.update_one({"message_id": message_id}, {"$addToSet": {"hidden_for": uid}})
        return {"ok": True, "scope": "me", "message_id": message_id}

    # scope == "everyone"
    if m.get('deleted'):
        return {"ok": True, "scope": "everyone", "message_id": message_id, "already": True}
    if m.get('from_user') != uid and not is_admin:
        raise HTTPException(status_code=403, detail="Only the sender can delete for everyone")
    # 1-hour window (admins bypass)
    try:
        created = datetime.fromisoformat(m['created_at'].replace('Z', '+00:00'))
    except Exception:
        created = now_utc()
    if not is_admin and (now_utc() - created).total_seconds() > 3600:
        raise HTTPException(status_code=403, detail="Прошло больше часа — нельзя удалить у всех")

    await db.messages.update_one(
        {"message_id": message_id},
        {"$set": {
            "deleted": True,
            "deleted_at": iso(now_utc()),
            "deleted_by": uid,
            "text": "",
            "media_url": None,
            "file_name": None,
            "gift_key": None,
        }},
    )
    try:
        await ws_manager.broadcast_deletion(m['chat_id'], m.get('participants') or [], message_id, "everyone", uid)
    except Exception as e:
        logger.warning(f"ws deletion broadcast failed: {e}")
    return {"ok": True, "scope": "everyone", "message_id": message_id}

@api.post("/chats/{other_id}/send")
async def send_message(other_id: str, body: MessageBody, user: dict = Depends(get_current_user)):
    return await _do_send_message(user, other_id, body)

class ChatMediaBody(BaseModel):
    data_url: str
    kind: Literal['image', 'voice', 'video', 'file']
    file_name: Optional[str] = None

@api.post("/chat/media")
async def upload_chat_media(body: ChatMediaBody, user: dict = Depends(get_current_user)):
    """Upload chat media (image / voice / video / file). Returns a data_url
    suitable for the `media_url` field in a subsequent /chats/{id}/send call.
    Images are compressed. Audio / video / files are stored as-is (base64 data URLs)."""
    if not body.data_url.startswith("data:"):
        raise HTTPException(status_code=400, detail="Invalid media format")
    max_bytes = 4 * 1024 * 1024 if body.kind == 'image' else 10 * 1024 * 1024
    try:
        _, b64 = body.data_url.split(',', 1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Malformed data URL")
    approx_bytes = int(len(b64) * 3 / 4)
    if approx_bytes > max_bytes:
        raise HTTPException(status_code=413, detail=f"Файл слишком большой (лимит {max_bytes // (1024*1024)} МБ)")
    if body.kind == 'image':
        if not body.data_url.startswith('data:image/'):
            raise HTTPException(status_code=400, detail="Ожидается изображение")
        _, compressed_bytes = _compress_image_data_url(body.data_url, max_dim=1200, quality=78)
        if compressed_bytes:
            media_url = await storage_put(compressed_bytes, f"chat_image_{uuid.uuid4().hex[:10]}.jpg", "image/jpeg",
                                          {"owner_id": user['user_id'], "kind": "chat_image"})
        else:
            media_url = await store_data_url_in_gridfs(body.data_url, user['user_id'], f"chat_{body.kind}")
    else:
        media_url = await store_data_url_in_gridfs(body.data_url, user['user_id'], f"chat_{body.kind}")
    return {"media_url": media_url, "kind": body.kind, "size_bytes": approx_bytes, "file_name": body.file_name}

@api.get("/chat/status/{other_id}")
async def chat_status(other_id: str, user: dict = Depends(get_current_user)):
    """Per-chat state for the current viewer.
    Returns free-message counter and whether the input is hard-blocked."""
    cid = chat_id(user['user_id'], other_id)
    sent = await db.messages.count_documents({"chat_id": cid, "from_user": user['user_id']})
    fresh = await db.users.find_one({"user_id": user['user_id']}, {"_id": 0, "coins": 1, "is_premium": 1})
    coins = int((fresh or {}).get('coins') or 0)
    is_premium = bool((fresh or {}).get('is_premium'))
    # Free-message limit reached AND no coins → blocked
    is_blocked = (sent >= FREE_MSGS) and coins < MSG_COST['text'] and not is_premium and not user.get('is_admin')
    return {
        "chat_id": cid,
        "sent_count": sent,
        "free_used": min(sent, FREE_MSGS),
        "free_limit": FREE_MSGS,
        "coins": coins,
        "is_premium": is_premium,
        "is_blocked": is_blocked,
    }

@api.get("/gifts")
async def gifts_list():
    """Public gift catalog: key, name, emoji, cost, tailwind gradient."""
    return GIFT_CATALOG

