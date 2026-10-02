"""File endpoints — /files/*"""
from fastapi import HTTPException, Depends
from fastapi import UploadFile
from fastapi import File as UploadFileParam
from fastapi.responses import StreamingResponse
from bson import ObjectId as _ObjectId
import io
from server import (
    api, db, logger, now_utc, iso,
    get_current_user, gridfs_bucket, gridfs_put, gridfs_url,
)

@api.get("/files/{file_id}")
async def get_file(file_id: str):
    """Stream a file from GridFS with its stored MIME type. Publicly reachable
    by URL — we intentionally don't require auth so <img>/<audio>/<video> in
    chat bubbles work without extra headers. File IDs are 24-hex opaque tokens
    so are not enumerable."""
    try:
        oid = _ObjectId(file_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Bad file id")
    try:
        gout = await gridfs_bucket.open_download_stream(oid)
    except Exception:
        raise HTTPException(status_code=404, detail="File not found")
    meta = gout.metadata or {}
    content_type = meta.get("content_type") or "application/octet-stream"

    async def iter_chunks():
        try:
            while True:
                chunk = await gout.readchunk()
                if not chunk:
                    break
                yield chunk
        finally:
            await gout.close()

    headers = {
        "Content-Length": str(gout.length),
        "Cache-Control": "public, max-age=31536000, immutable",
    }
    return StreamingResponse(iter_chunks(), media_type=content_type, headers=headers)

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
