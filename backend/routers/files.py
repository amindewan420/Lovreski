"""File endpoints — /files/* with signed-URL access control.

Access model:
- profile_photo            → public (needed for feed/profile rendering)
- chat_* / receipts / other → require EITHER a valid short-lived signed URL
  (?exp&sig, minted by /files/{id}/signed or server-side serialization)
  OR an authenticated session where the caller is the file owner, an admin,
  or (for chat media) a participant of a message referencing the file.
"""
from fastapi import HTTPException, Depends, Header, Cookie
from fastapi import UploadFile
from fastapi import File as UploadFileParam
from fastapi.responses import StreamingResponse
from bson import ObjectId as _ObjectId
from typing import Optional
import io
import uuid
import base64
from server import (
    api, db, logger, now_utc, iso,
    get_current_user, gridfs_bucket, gridfs_put, gridfs_url,
    sign_file_url, verify_file_sig,
    _compress_image_data_url,
)

PUBLIC_KINDS = {"profile_photo"}


async def _load_meta(oid: _ObjectId) -> Optional[dict]:
    return await db["fs.files"].find_one({"_id": oid}, {"metadata": 1, "length": 1, "filename": 1})


async def _try_auth(authorization: Optional[str], session_token: Optional[str]) -> Optional[dict]:
    try:
        return await get_current_user(authorization=authorization, session_token=session_token)
    except Exception:
        return None


async def _is_chat_participant(user_id: str, file_id: str) -> bool:
    msg = await db.messages.find_one({"media_url": f"/api/files/{file_id}"}, {"_id": 0, "participants": 1})
    return bool(msg and user_id in (msg.get("participants") or []))


@api.get("/files/{file_id}")
async def get_file(
    file_id: str,
    exp: Optional[int] = None,
    sig: Optional[str] = None,
    authorization: Optional[str] = Header(None),
    session_token: Optional[str] = Cookie(None),
):
    """Stream a file from GridFS with its stored MIME type.
    Public kinds (profile photos) are open; everything else needs a valid
    signed URL or an authorized session (owner / admin / chat participant)."""
    try:
        oid = _ObjectId(file_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Bad file id")
    doc = await _load_meta(oid)
    if not doc:
        raise HTTPException(status_code=404, detail="File not found")
    meta = doc.get("metadata") or {}
    kind = meta.get("kind") or ""
    owner = meta.get("owner_id")

    allowed = kind in PUBLIC_KINDS or verify_file_sig(file_id, exp, sig)
    if not allowed:
        user = await _try_auth(authorization, session_token)
        if user:
            if user.get("is_admin") or (owner and owner == user["user_id"]):
                allowed = True
            elif kind.startswith("chat_") and await _is_chat_participant(user["user_id"], file_id):
                allowed = True
    if not allowed:
        raise HTTPException(status_code=403, detail="Access denied")

    content_type = meta.get("content_type") or "application/octet-stream"
    gout = await gridfs_bucket.open_download_stream(oid)

    async def iter_chunks():
        try:
            while True:
                chunk = await gout.readchunk()
                if not chunk:
                    break
                yield chunk
        finally:
            try:
                await gout.close()
            except Exception:
                pass

    cache = "public, max-age=31536000, immutable" if kind in PUBLIC_KINDS else "private, max-age=600"
    headers = {
        "Content-Length": str(doc.get("length") or gout.length),
        "Cache-Control": cache,
    }
    return StreamingResponse(iter_chunks(), media_type=content_type, headers=headers)


@api.get("/files/{file_id}/signed")
async def get_signed_file_url(file_id: str, user: dict = Depends(get_current_user)):
    """Mint a short-lived signed URL for a file.
    profile_photo → returns the plain URL (public anyway).
    chat_*        → participants of a message referencing the file, or admin.
    receipts/other → owner or admin only."""
    try:
        oid = _ObjectId(file_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Bad file id")
    doc = await _load_meta(oid)
    if not doc:
        raise HTTPException(status_code=404, detail="File not found")
    meta = doc.get("metadata") or {}
    kind = meta.get("kind") or ""
    owner = meta.get("owner_id")
    plain = f"/api/files/{file_id}"

    if kind in PUBLIC_KINDS:
        return {"url": plain, "public": True}
    allowed = user.get("is_admin") or (owner and owner == user["user_id"])
    if not allowed and kind.startswith("chat_"):
        allowed = await _is_chat_participant(user["user_id"], file_id)
    if not allowed:
        raise HTTPException(status_code=403, detail="Access denied")
    return {"url": sign_file_url(plain)}


@api.post("/files/upload")
async def upload_file(file: UploadFile = UploadFileParam(...), user: dict = Depends(get_current_user)):
    """Generic authenticated file upload. Used by the frontend when uploading
    via <input type=file>. Images are auto-compressed; other kinds stored
    as-is. Returns {file_id, url, content_type, size}."""
    content_type = file.content_type or "application/octet-stream"
    raw = await file.read()
    max_bytes = 4 * 1024 * 1024 if content_type.startswith("image/") else 10 * 1024 * 1024
    if len(raw) > max_bytes:
        raise HTTPException(status_code=413, detail=f"File too large (max {max_bytes // (1024 * 1024)} MB)")
    if content_type.startswith("image/"):
        # Compress to JPEG before storing
        try:
            data_url = "data:" + content_type + ";base64," + base64.b64encode(raw).decode()
            _, raw = _compress_image_data_url(data_url, max_dim=1200, quality=78)
            content_type = "image/jpeg"
        except Exception:
            pass  # store original on failure
    filename = f"{file.filename or 'file'}_{uuid.uuid4().hex[:8]}"
    file_id = await gridfs_put(raw, filename, content_type, {"owner_id": user['user_id'], "orig_name": file.filename})
    return {"file_id": file_id, "url": gridfs_url(file_id), "content_type": content_type, "size": len(raw)}
