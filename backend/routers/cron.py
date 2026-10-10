"""Platform cron endpoints + storage cleanup job.

Registered via `.emergent/crons.yml`. Each cron endpoint must ack 2xx
immediately and enqueue the real work asynchronously.
"""
import asyncio
import hmac
import os
import re
import uuid
from datetime import timedelta
from typing import Optional

from bson import ObjectId
from fastapi import Depends, HTTPException, Request

from server import api, db, logger, now_utc, iso, require_admin

FILE_URL_RE = re.compile(r"/api/files/([0-9a-f]{24})")
S3_KEY_RE = re.compile(r"(lovreski/[A-Za-z0-9_\-./]+)")
DEFAULT_RETENTION_DAYS = int(os.environ.get("STORAGE_RETENTION_DAYS", "7"))


def _extract_file_ids(urls) -> set:
    """Pull GridFS ObjectIds out of /api/files/<hex> URLs."""
    out = set()
    for u in urls:
        if not isinstance(u, str):
            continue
        for m in FILE_URL_RE.findall(u):
            try:
                out.add(ObjectId(m))
            except Exception:
                continue
    return out


def _extract_s3_keys(urls) -> set:
    """Pull S3 object keys (lovreski/...) out of direct Timeweb URLs."""
    out = set()
    for u in urls:
        if not isinstance(u, str):
            continue
        for m in S3_KEY_RE.findall(u):
            out.add(m.rstrip("?#"))
    return out


async def collect_referenced_file_ids() -> tuple:
    """Scan every collection that may reference a stored file.
    Returns (referenced_object_ids, referenced_s3_keys)."""
    referenced: set = set()
    s3_keys: set = set()

    def _collect(urls):
        referenced.update(_extract_file_ids(urls))
        s3_keys.update(_extract_s3_keys(urls))

    async for u in db.users.find({}, {"_id": 0, "photos": 1}):
        _collect(u.get("photos") or [])
    async for m in db.messages.find({"media_url": {"$ne": None}}, {"_id": 0, "media_url": 1}):
        _collect([m.get("media_url")])
    async for r in db.receipt_submissions.find({"receipt_data_url": {"$ne": None}}, {"_id": 0, "receipt_data_url": 1}):
        _collect([r.get("receipt_data_url")])
    async for r in db.refund_requests.find({"receipt_data_url": {"$ne": None}}, {"_id": 0, "receipt_data_url": 1}):
        _collect([r.get("receipt_data_url")])
    return referenced, s3_keys


async def run_storage_cleanup(retention_days: Optional[int] = None) -> dict:
    """Delete orphaned files older than `retention_days` days from BOTH stores.

    Orphan = not referenced by any user photo, message media, receipt, or
    refund attachment. Deleted-message media becomes orphaned because the
    tombstone flow nulls `media_url`. S3 assets are destroyed via the
    API (then the s3_files doc is removed); GridFS files are deleted from
    fs.files + fs.chunks.
    """
    days = retention_days or DEFAULT_RETENTION_DAYS
    cutoff = now_utc() - timedelta(days=days)
    referenced, referenced_s3_keys = await collect_referenced_file_ids()
    referenced_strs = {str(x) for x in referenced}

    deleted_files = 0
    freed_bytes = 0
    # ── GridFS orphans ──
    async for f in db["fs.files"].find({"uploadDate": {"$lt": cutoff}}, {"_id": 1, "length": 1, "metadata": 1}):
        fid = f["_id"]
        if fid in referenced:
            continue
        size = int(f.get("length") or 0)
        try:
            await db["fs.chunks"].delete_many({"files_id": fid})
            await db["fs.files"].delete_one({"_id": fid})
            deleted_files += 1
            freed_bytes += size
        except Exception as e:
            logger.warning(f"[storage-cleanup] failed deleting gridfs {fid}: {e}")

    # ── S3 orphans ──
    import storage as _cloud
    async for c in db.s3_files.find({"created_at": {"$lt": iso(cutoff)}}, {"_id": 1, "bytes": 1, "s3_key": 1}):
        cid = c["_id"]
        # Referenced via stable /api/files/<id> URL OR direct S3 URL (by key)
        if cid in referenced_strs or c.get("s3_key") in referenced_s3_keys:
            continue
        ok = await _cloud.destroy(c["s3_key"])
        if ok:
            await db.s3_files.delete_one({"_id": cid})
            deleted_files += 1
            freed_bytes += int(c.get("bytes") or 0)
        else:
            logger.warning(f"[storage-cleanup] s3 destroy failed for {cid}, doc kept")

    report = {
        "run_id": f"clean_{uuid.uuid4().hex[:12]}",
        "started_at": iso(now_utc()),
        "retention_days": days,
        "referenced_files": len(referenced),
        "deleted_files": deleted_files,
        "freed_bytes": freed_bytes,
    }
    await db.storage_cleanup_runs.insert_one(report)
    report.pop("_id", None)
    logger.info(f"[storage-cleanup] done: {deleted_files} files, {freed_bytes} bytes freed (retention {days}d)")
    return report


def _check_cron_secret(request: Request) -> None:
    """Constant-time Bearer check against WEBHOOK_CRON_SECRET."""
    expected = os.environ.get("WEBHOOK_CRON_SECRET")
    auth = request.headers.get("authorization", "")
    token = auth.split(" ", 1)[1] if auth.lower().startswith("bearer ") else ""
    if not expected or not token or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="Invalid cron secret")


@api.post("/cron/storage-cleanup")
async def cron_storage_cleanup(request: Request):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    _check_cron_secret(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    run_id = (body or {}).get("run_id") or request.headers.get("x-webhook-id") or f"manual_{uuid.uuid4().hex[:8]}"

    # Idempotency: same run_id → don't execute twice
    if await db.cron_runs.find_one({"run_id": run_id}):
        return {"ok": True, "duplicate": True, "run_id": run_id}
    await db.cron_runs.insert_one({"run_id": run_id, "job": "storage-cleanup", "queued_at": iso(now_utc())})

    asyncio.create_task(run_storage_cleanup())
    return {"ok": True, "queued": True, "run_id": run_id}


# ─── Admin manual triggers ────────────────────────────────────────────────
@api.post("/admin/storage/cleanup")
async def admin_storage_cleanup(_: dict = Depends(require_admin)):
    """Admin-triggered immediate cleanup (runs synchronously, returns report)."""
    report = await run_storage_cleanup()
    return report


@api.get("/admin/storage/cleanup-log")
async def admin_storage_cleanup_log(_: dict = Depends(require_admin), limit: int = 10):
    runs = await db.storage_cleanup_runs.find({}, {"_id": 0}).sort("started_at", -1).to_list(limit)
    return runs
