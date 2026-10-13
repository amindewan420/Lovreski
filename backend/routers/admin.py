"""Admin dashboard, payments, user management, settings routes."""
from fastapi import HTTPException, Depends, Request
from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from datetime import datetime, timedelta, timezone
import os, uuid
from server import (
    api, db, logger, now_utc, iso, fcm,
    get_current_user, require_admin, user_public,
    _push_notification, encrypt_str, decrypt_str, mask_phone,
    _get_admin_sbp_phone,
    _compress_image_data_url, gridfs_put, gridfs_url, store_data_url_in_gridfs, storage_put,
    gridfs_bucket,
    sign_file_url,
    AdminPaymentAction, COIN_PACKAGES,
)
import storage as _cloud

class AdminApproveBody(BaseModel):
    coins: int = Field(gt=0, le=100000)
    reason: str = Field(min_length=1, max_length=200)

class AdminRejectBody(BaseModel):
    reason: str = Field(min_length=1, max_length=200)

class CustomCoinAddBody(BaseModel):
    user_id: str
    coins: int = Field(gt=0, le=100000)
    reason: str = Field(min_length=1, max_length=200)

@api.get("/admin/support/pending-count")
async def admin_pending_count(_: dict = Depends(require_admin)):
    return {"count": await db.receipt_submissions.count_documents({"status": "pending"})}


@api.get("/admin/storage")
async def admin_storage(_: dict = Depends(require_admin)):
    """GridFS usage aggregated by `metadata.kind` (profile_photo | chat_image |
    chat_voice | chat_video | chat_file | support_receipt | refund_receipt | other).
    Falls back to content_type prefix when kind is absent.
    Returns: {total_files, total_bytes, by_kind: [{kind, files, bytes}], by_content_type: [...]}."""
    # $group on fs.files metadata.kind; sum file.length; count
    pipeline = [
        {"$group": {
            "_id": {"kind": "$metadata.kind", "content_type": "$metadata.content_type"},
            "files": {"$sum": 1},
            "bytes": {"$sum": "$length"},
        }},
        {"$sort": {"bytes": -1}},
    ]
    rows = await db["fs.files"].aggregate(pipeline).to_list(1000)
    by_kind: dict = {}
    by_ct: dict = {}
    total_files = 0
    total_bytes = 0
    for r in rows:
        kind = r["_id"].get("kind") or "other"
        ct = r["_id"].get("content_type") or "application/octet-stream"
        files = r["files"]
        size = int(r["bytes"] or 0)
        total_files += files
        total_bytes += size
        # aggregate by kind
        k = by_kind.setdefault(kind, {"kind": kind, "files": 0, "bytes": 0})
        k["files"] += files
        k["bytes"] += size
        # aggregate by content-type bucket
        ct_bucket = ct.split("/")[0] if "/" in ct else ct
        c = by_ct.setdefault(ct_bucket, {"content_type": ct_bucket, "files": 0, "bytes": 0})
        c["files"] += files
        c["bytes"] += size
    gridfs_files, gridfs_bytes = total_files, total_bytes
    # Merge S3-backed files (s3_files collection)
    c_rows = await db.s3_files.aggregate([
        {"$group": {"_id": "$kind", "files": {"$sum": 1}, "bytes": {"$sum": "$bytes"}}},
    ]).to_list(200)
    s3_files_n, s3_bytes_n = 0, 0
    for r in c_rows:
        kind = r["_id"] or "other"
        files = r["files"]
        size = int(r["bytes"] or 0)
        total_files += files
        total_bytes += size
        s3_files_n += files
        s3_bytes_n += size
        k = by_kind.setdefault(kind, {"kind": kind, "files": 0, "bytes": 0})
        k["files"] += files
        k["bytes"] += size
    return {
        "total_files": total_files,
        "total_bytes": total_bytes,
        "by_kind": sorted(by_kind.values(), key=lambda x: x["bytes"], reverse=True),
        "by_content_type": sorted(by_ct.values(), key=lambda x: x["bytes"], reverse=True),
        "stores": {
            "gridfs": {"files": gridfs_files, "bytes": gridfs_bytes},
            "s3": {"files": s3_files_n, "bytes": s3_bytes_n, "configured": _cloud.is_configured(),
                   "bucket": os.environ.get("S3_BUCKET", "") if _cloud.is_configured() else ""},
        },
    }


@api.post("/admin/migrate/s3")
async def admin_migrate_s3(admin: dict = Depends(require_admin)):
    """One-time migration of all GridFS files to Timeweb S3.
    Keeps the SAME /api/files/<id> URL working by writing an s3_files doc
    keyed by the old GridFS id — no reference rewriting needed. On success the
    GridFS copy (fs.files + fs.chunks) is removed."""
    if not _cloud.is_configured():
        raise HTTPException(status_code=503, detail="S3 not configured — set S3_* env vars first")
    migrated = failed = skipped = 0
    cursor = db["fs.files"].find({}, {"metadata": 1, "filename": 1, "length": 1})
    async for f in cursor:
        fid = str(f["_id"])
        if await db.s3_files.find_one({"_id": fid}):
            skipped += 1
            continue
        meta = f.get("metadata") or {}
        kind = meta.get("kind") or "other"
        ct = meta.get("content_type") or "application/octet-stream"
        try:
            gout = await gridfs_bucket.open_download_stream(f["_id"])
            data = await gout.read()
            try:
                await gout.close()
            except Exception:
                pass
            up = await _cloud.upload_bytes(data, f.get("filename") or fid, ct, meta.get("owner_id"), kind)
            await db.s3_files.insert_one({
                "_id": fid,
                "s3_key": up["public_id"],
                "public_url": up["public_url"],
                "bytes": up["bytes"],
                "content_type": ct,
                "filename": f.get("filename"),
                "kind": kind,
                "owner_id": meta.get("owner_id"),
                "migrated_from": "gridfs",
                "created_at": iso(now_utc()),
            })
            await db["fs.chunks"].delete_many({"files_id": f["_id"]})
            await db["fs.files"].delete_one({"_id": f["_id"]})
            migrated += 1
        except Exception as e:
            logger.warning(f"[migrate-s3] {fid} failed: {e}")
            failed += 1
    await db.admin_audit.insert_one({
        "admin_id": admin['user_id'], "action": "s3_migrate",
        "migrated": migrated, "failed": failed, "skipped": skipped, "at": iso(now_utc()),
    })
    return {"ok": True, "migrated": migrated, "failed": failed, "skipped": skipped}


def _sign_receipt_urls(rows: list) -> list:
    """Pre-sign receipt_data_url on a list of admin-facing docs so the admin
    panel can render them without extra round-trips."""
    for r in rows:
        u = r.get("receipt_data_url")
        if isinstance(u, str) and u.startswith("/api/files/"):
            r["receipt_data_url"] = sign_file_url(u)
    return rows


@api.get("/admin/support/pending")
async def admin_pending(_: dict = Depends(require_admin)):
    subs = await db.receipt_submissions.find({"status": "pending"}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return _sign_receipt_urls(subs)

@api.get("/admin/support/history")
async def admin_history(_: dict = Depends(require_admin)):
    subs = await db.receipt_submissions.find({"status": {"$ne": "pending"}}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return _sign_receipt_urls(subs)

@api.post("/admin/support/{submission_id}/approve")
async def admin_approve_receipt(submission_id: str, body: AdminApproveBody, admin: dict = Depends(require_admin)):
    """Admin approves a receipt: atomically credits coins + activates Premium.
    Idempotent via CAS on status:pending → verified."""
    res = await db.receipt_submissions.find_one_and_update(
        {"submission_id": submission_id, "status": "pending"},
        {"$set": {
            "status": "verified",
            "coins_added": body.coins,
            "reason": body.reason,
            "admin_id": admin['user_id'],
            "verified_at": iso(now_utc()),
        }},
        return_document=True,
    )
    if not res:
        raise HTTPException(status_code=404, detail="Submission not found or already processed")
    # Credit coins + activate premium
    await db.users.update_one(
        {"user_id": res['user_id']},
        {"$inc": {"coins": body.coins},
         "$set": {"is_premium": True, "premium_until": iso(now_utc() + timedelta(days=30))}},
    )
    # Audit log
    await db.admin_audit.insert_one({
        "admin_id": admin['user_id'], "action": "receipt_approve",
        "target_user": res['user_id'], "submission_id": submission_id,
        "coins": body.coins, "reason": body.reason, "at": iso(now_utc()),
    })
    await _push_notification(res['user_id'], f"🎉 Payment verified! {body.coins} coins added. Your Premium is now ACTIVE! 👑", "success")
    return {"ok": True, "coins_added": body.coins}

@api.post("/admin/support/{submission_id}/reject")
async def admin_reject_receipt(submission_id: str, body: AdminRejectBody, admin: dict = Depends(require_admin)):
    res = await db.receipt_submissions.find_one_and_update(
        {"submission_id": submission_id, "status": "pending"},
        {"$set": {
            "status": "rejected",
            "reject_reason": body.reason,
            "admin_id": admin['user_id'],
            "rejected_at": iso(now_utc()),
        }},
        return_document=True,
    )
    if not res:
        raise HTTPException(status_code=404, detail="Submission not found or already processed")
    await db.admin_audit.insert_one({
        "admin_id": admin['user_id'], "action": "receipt_reject",
        "target_user": res['user_id'], "submission_id": submission_id,
        "reason": body.reason, "at": iso(now_utc()),
    })
    await _push_notification(res['user_id'], f"❌ Receipt rejected. Reason: {body.reason}. Please contact support.", "error")
    return {"ok": True}

@api.post("/admin/users/add-coins")
async def admin_add_coins(body: CustomCoinAddBody, admin: dict = Depends(require_admin)):
    target = await db.users.find_one({"user_id": body.user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    new_balance = (target.get('coins', 0) or 0) + body.coins
    await db.users.update_one(
        {"user_id": body.user_id},
        {"$inc": {"coins": body.coins},
         "$set": {"is_premium": True, "premium_until": iso(now_utc() + timedelta(days=30))}},
    )
    await db.admin_audit.insert_one({
        "admin_id": admin['user_id'], "action": "custom_coin_add",
        "target_user": body.user_id, "coins": body.coins,
        "reason": body.reason, "at": iso(now_utc()),
    })
    await _push_notification(body.user_id, f"🎉 {body.coins} coins added by admin. Premium is ACTIVE! 👑", "success")
    return {"ok": True, "new_balance": new_balance}
class RefundBody(BaseModel):
    full_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    receipt_data_url: str
    reason: str = Field(min_length=1, max_length=1000)

@api.post("/support/refund")
async def submit_refund(body: RefundBody, request: Request, user: dict = Depends(get_current_user)):
    if not body.receipt_data_url.startswith("data:"):
        raise HTTPException(status_code=400, detail="Invalid receipt format")
    # Rate limit 3 refund requests per user per day
    since = now_utc() - timedelta(days=1)
    recent = await db.refund_requests.count_documents({"user_id": user['user_id'], "created_at": {"$gte": iso(since)}})
    if recent >= 3:
        raise HTTPException(status_code=429, detail="Too many refund requests. Try again tomorrow.")
    receipt = body.receipt_data_url
    if receipt.startswith("data:image/"):
        try:
            _, compressed_bytes = _compress_image_data_url(receipt, max_dim=1800, quality=85)
            if compressed_bytes:
                receipt_url = (await storage_put(compressed_bytes, f"refund_{uuid.uuid4().hex[:10]}.jpg", "image/jpeg",
                                                 {"owner_id": user['user_id'], "kind": "refund_receipt"}))["url"]
            else:
                receipt_url = await store_data_url_in_gridfs(receipt, user['user_id'], "refund_receipt")
        except Exception:
            receipt_url = await store_data_url_in_gridfs(receipt, user['user_id'], "refund_receipt")
    else:
        receipt_url = await store_data_url_in_gridfs(receipt, user['user_id'], "refund_receipt")
    rid = f"ref_{uuid.uuid4().hex[:12]}"
    await db.refund_requests.insert_one({
        "refund_id": rid,
        "user_id": user['user_id'],
        "full_name": body.full_name,
        "email": body.email.lower(),
        "receipt_data_url": receipt_url,
        "reason": body.reason,
        "status": "pending",
        "created_at": iso(now_utc()),
    })
    return {"refund_id": rid, "status": "pending"}

@api.get("/admin/refunds")
async def admin_refunds(status: str = "all", _: dict = Depends(require_admin)):
    q = {} if status == "all" else {"status": status}
    r = await db.refund_requests.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
    return _sign_receipt_urls(r)

@api.post("/admin/refunds/{refund_id}/decide")
async def admin_refund_decide(refund_id: str, body: dict, admin: dict = Depends(require_admin)):
    action = body.get('action')
    if action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="Invalid action")
    reason = body.get('reason') or ""
    res = await db.refund_requests.find_one_and_update(
        {"refund_id": refund_id, "status": "pending"},
        {"$set": {"status": "approved" if action == "approve" else "rejected", "admin_reason": reason, "admin_id": admin['user_id'], "decided_at": iso(now_utc())}},
        return_document=True,
    )
    if not res:
        raise HTTPException(status_code=404, detail="Refund not found or already processed")
    await _push_notification(res['user_id'],
        f"{'✅' if action == 'approve' else '❌'} Refund {action}d." + (f" Note: {reason}" if reason else ""),
        "success" if action == "approve" else "error")
    return {"ok": True}

@api.get("/admin/stats")
async def admin_stats(_: dict = Depends(require_admin)):
    total_users = await db.users.count_documents({"is_admin": {"$ne": True}})
    premium_users = await db.users.count_documents({"is_premium": True, "is_admin": {"$ne": True}})
    pending = await db.transactions.count_documents({"status": "pending"})
    approved = await db.transactions.find({"status": "approved"}, {"_id": 0}).to_list(5000)
    revenue = sum(t.get('amount_rub', 0) for t in approved)
    month_start = now_utc().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    approved_month = sum(1 for t in approved if datetime.fromisoformat(t['created_at']) >= month_start)
    # Timeseries daily (last 24h buckets)
    daily = [0] * 24
    revenue_daily = [0] * 24
    today_start = now_utc().replace(hour=0, minute=0, second=0, microsecond=0)
    for t in approved:
        ts = datetime.fromisoformat(t['created_at'])
        if ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)
        if ts >= today_start:
            daily[ts.hour] += 1
            revenue_daily[ts.hour] += t.get('amount_rub', 0)
    # Monthly (last 30 days)
    monthly = [0] * 30
    revenue_monthly = [0] * 30
    for t in approved:
        ts = datetime.fromisoformat(t['created_at'])
        if ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)
        days_ago = (now_utc() - ts).days
        if 0 <= days_ago < 30:
            monthly[29 - days_ago] += 1
            revenue_monthly[29 - days_ago] += t.get('amount_rub', 0)
    # Yearly (12 months)
    yearly = [0] * 12
    revenue_yearly = [0] * 12
    for t in approved:
        ts = datetime.fromisoformat(t['created_at'])
        if ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)
        if ts.year == now_utc().year:
            yearly[ts.month - 1] += 1
            revenue_yearly[ts.month - 1] += t.get('amount_rub', 0)
    return {
        "total_users": total_users, "premium_users": premium_users,
        "pending": pending, "revenue": revenue, "approved_month": approved_month,
        "daily": daily, "revenue_daily": revenue_daily,
        "monthly": monthly, "revenue_monthly": revenue_monthly,
        "yearly": yearly, "revenue_yearly": revenue_yearly,
    }

@api.get("/admin/payments")
async def admin_payments(status: str = "all", _: dict = Depends(require_admin)):
    q = {} if status == "all" else {"status": status}
    tx = await db.transactions.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return tx

@api.post("/admin/payments/{tx_id}")
async def admin_action_payment(tx_id: str, body: AdminPaymentAction, _: dict = Depends(require_admin)):
    """LEGACY endpoint. Under the manual-approval contract, this endpoint NO LONGER
    credits coins. It only updates the checkout tx status for record-keeping.
    Coin/Premium mutations must go through /admin/support/:id/approve or
    /admin/users/add-coins."""
    tx = await db.transactions.find_one({"tx_id": tx_id}, {"_id": 0})
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if body.action == "approve":
        # No coin/premium mutation here anymore — only mark the tx as reviewed.
        await db.transactions.update_one(
            {"tx_id": tx_id},
            {"$set": {"status": "awaiting_admin", "reviewed_at": iso(now_utc())}},
        )
        return {"ok": True, "note": "Use /admin/support/:id/approve or /admin/users/add-coins to credit coins."}
    else:
        await db.transactions.update_one(
            {"tx_id": tx_id},
            {"$set": {"status": "rejected", "reject_reason": body.reason or "Отклонено администратором"}},
        )
    return {"ok": True}

@api.get("/admin/reports")
async def admin_reports(_: dict = Depends(require_admin)):
    reports = await db.reports.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    # Aggregate reports per target
    agg: dict = {}
    for r in reports:
        t = r['target_user']
        agg.setdefault(t, {"target_user": t, "count": 0, "reasons": [], "last": r['created_at']})
        agg[t]['count'] += 1
        agg[t]['reasons'].append(r['reason'])
    out = []
    for uid, data in agg.items():
        u = await db.users.find_one({"user_id": uid}, {"_id": 0, "password_hash": 0})
        if u:
            data['user'] = user_public(u)
            out.append(data)
    return out

@api.get("/admin/users")
async def admin_users(_: dict = Depends(require_admin), limit: int = 100):
    users = await db.users.find({"is_admin": {"$ne": True}}, {"_id": 0, "password_hash": 0}).limit(limit).to_list(limit)
    return [user_public(u) for u in users]

@api.post("/admin/users/{user_id}/deactivate")
async def admin_deactivate(user_id: str, _: dict = Depends(require_admin)):
    await db.users.delete_one({"user_id": user_id})
    await db.sessions.delete_many({"user_id": user_id})
    await db.messages.delete_many({"$or": [{"from_user": user_id}, {"to_user": user_id}]})
    await db.likes.delete_many({"$or": [{"from_user": user_id}, {"to_user": user_id}]})
    return {"ok": True}

@api.post("/admin/users/{user_id}/ban")
async def admin_ban(user_id: str, days: int = 7, _: dict = Depends(require_admin)):
    await db.users.update_one({"user_id": user_id}, {"$set": {"banned_until": iso(now_utc() + timedelta(days=days))}})
    return {"ok": True}

@api.put("/admin/settings")
async def admin_settings_update(data: dict, admin: dict = Depends(require_admin)):
    """Admin can only update whitelisted keys. `sbp_phone` is encrypted before storage."""
    updates: dict = {}
    if 'sbp_phone' in data:
        phone = str(data['sbp_phone']).strip()
        # Basic validation — must look like a Russian phone (E.164, 11 digits after +)
        digits = ''.join(c for c in phone if c.isdigit())
        if len(digits) < 10 or len(digits) > 15:
            raise HTTPException(status_code=400, detail="Invalid SBP phone format")
        updates['sbp_phone_enc'] = encrypt_str(phone)
    if 'packages' in data and isinstance(data['packages'], list):
        # Validate each package
        for p in data['packages']:
            if not isinstance(p.get('coins'), int) or p['coins'] <= 0:
                raise HTTPException(status_code=400, detail="Invalid coins amount")
            if not isinstance(p.get('price'), (int, float)) or p['price'] <= 0:
                raise HTTPException(status_code=400, detail="Invalid price")
        updates['packages'] = data['packages']
    if not updates:
        raise HTTPException(status_code=400, detail="No valid settings keys provided")
    updates['updated_at'] = iso(now_utc())
    await db.settings.update_one({"key": "app"}, {"$set": {"key": "app", **updates}}, upsert=True)
    await db.admin_audit.insert_one({
        "admin_id": admin['user_id'],
        "action": "settings_update",
        "keys": list(updates.keys()),
        "at": iso(now_utc()),
    })
    return {"ok": True}

@api.get("/admin/settings")
async def admin_settings_get(_: dict = Depends(require_admin)):
    """Admin sees the SBP phone MASKED by default. Full number requires explicit ?reveal=true.
    Never expose the raw phone anywhere else."""
    s = await db.settings.find_one({"key": "app"}, {"_id": 0}) or {}
    enc = s.get('sbp_phone_enc')
    if not enc:
        # Bootstrap from env
        env_phone = os.environ.get('SBP_PHONE', '')
        if env_phone:
            await db.settings.update_one({"key": "app"}, {"$set": {"key": "app", "sbp_phone_enc": encrypt_str(env_phone), "updated_at": iso(now_utc())}}, upsert=True)
            enc = encrypt_str(env_phone)
    phone = decrypt_str(enc) if enc else ""
    return {
        "sbp_phone_masked": mask_phone(phone),
        "sbp_phone_last4": phone[-4:] if phone else "",
        "packages": s.get('packages') or COIN_PACKAGES,
    }

@api.get("/admin/settings/reveal")
async def admin_settings_reveal(admin: dict = Depends(require_admin)):
    """Explicit reveal — returns the raw admin SBP phone. Requires admin role.
    Rate-limited implicitly by admin session. Every reveal is audit-logged."""
    s = await db.settings.find_one({"key": "app"}, {"_id": 0}) or {}
    enc = s.get('sbp_phone_enc')
    phone = decrypt_str(enc) if enc else os.environ.get('SBP_PHONE', '')
    await db.admin_audit.insert_one({
        "admin_id": admin['user_id'], "action": "sbp_reveal", "at": iso(now_utc()),
    })
    return {"sbp_phone": phone}

@api.post("/admin/users/deduct-coins")
async def admin_deduct_coins(body: CustomCoinAddBody, admin: dict = Depends(require_admin)):
    """Deduct coins from a user's balance. Requires a reason.
    Balance floored at 0. Audit-logged."""
    if body.coins <= 0:
        raise HTTPException(status_code=400, detail="Coins must be positive")
    if not (body.reason or "").strip():
        raise HTTPException(status_code=400, detail="Reason is required")
    target = await db.users.find_one({"user_id": body.user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    current = int(target.get('coins') or 0)
    deduct = min(body.coins, current)
    new_balance = current - deduct
    await db.users.update_one({"user_id": body.user_id}, {"$set": {"coins": new_balance}})
    await db.admin_audit.insert_one({
        "admin_id": admin['user_id'], "action": "custom_coin_deduct",
        "target_user": body.user_id, "coins": -deduct, "requested": body.coins,
        "reason": body.reason, "at": iso(now_utc()),
    })
    await _push_notification(body.user_id, f"⚠️ {deduct} монет удержано администратором. Причина: {body.reason}", "warning")
    return {"ok": True, "new_balance": new_balance, "deducted": deduct}
class UserActionBody(BaseModel):
    reason: Optional[str] = None
    days: Optional[int] = 7

@api.post("/admin/users/{user_id}/warn")
async def admin_warn(user_id: str, body: UserActionBody, admin: dict = Depends(require_admin)):
    """Send a warning notification to the user and mark on their record."""
    reason = (body.reason or "").strip() or "Нарушение правил"
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0, "user_id": 1})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    await db.users.update_one({"user_id": user_id}, {"$inc": {"warn_count": 1}, "$set": {"last_warn_at": iso(now_utc()), "last_warn_reason": reason}})
    await db.admin_audit.insert_one({"admin_id": admin['user_id'], "action": "warn", "target_user": user_id, "reason": reason, "at": iso(now_utc())})
    await _push_notification(user_id, f"⚠️ Предупреждение от администрации: {reason}", "warning")
    return {"ok": True}

# Backwards-compat: keep existing GET ban without body; add richer POST with reason+days
@api.post("/admin/users/{user_id}/ban7")
async def admin_ban7(user_id: str, body: UserActionBody, admin: dict = Depends(require_admin)):
    """Temporarily ban a user for `days` days (default 7). Ban clears sessions."""
    days = int(body.days or 7)
    if days <= 0 or days > 365:
        raise HTTPException(status_code=400, detail="days must be 1-365")
    reason = (body.reason or "").strip() or "Временная блокировка"
    until = iso(now_utc() + timedelta(days=days))
    r = await db.users.update_one({"user_id": user_id}, {"$set": {"banned_until": until, "ban_reason": reason}})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    await db.sessions.delete_many({"user_id": user_id})
    await db.admin_audit.insert_one({"admin_id": admin['user_id'], "action": "ban", "target_user": user_id, "days": days, "reason": reason, "at": iso(now_utc())})
    return {"ok": True, "banned_until": until}

@api.post("/admin/users/{user_id}/deactivate-permanent")
async def admin_deactivate_permanent(user_id: str, body: UserActionBody, admin: dict = Depends(require_admin)):
    """Soft-deactivate: hide from all feeds, invalidate sessions, prevent future logins.
    Content stays for audit / moderation review — no hard delete."""
    reason = (body.reason or "").strip() or "Постоянная деактивация"
    r = await db.users.update_one({"user_id": user_id}, {"$set": {
        "deactivated": True,
        "deactivated_at": iso(now_utc()),
        "deactivate_reason": reason,
        "is_online": False,
    }})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    await db.sessions.delete_many({"user_id": user_id})
    await db.admin_audit.insert_one({"admin_id": admin['user_id'], "action": "deactivate_permanent", "target_user": user_id, "reason": reason, "at": iso(now_utc())})
    return {"ok": True}
class LegalDocBody(BaseModel):
    slug: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1)

@api.get("/legal")
async def legal_list_public():
    """Public: list all published legal docs (slug, title, updated_at)."""
    docs = await db.legal_docs.find({}, {"_id": 0, "body": 0}).sort("title", 1).to_list(100)
    return docs

@api.get("/legal/{slug}")
async def legal_get_public(slug: str):
    d = await db.legal_docs.find_one({"slug": slug}, {"_id": 0})
    if not d:
        raise HTTPException(status_code=404, detail="Document not found")
    return d

@api.get("/admin/legal")
async def admin_legal_list(_: dict = Depends(require_admin)):
    return await db.legal_docs.find({}, {"_id": 0}).sort("title", 1).to_list(200)

@api.post("/admin/legal")
async def admin_legal_create(body: LegalDocBody, admin: dict = Depends(require_admin)):
    exists = await db.legal_docs.find_one({"slug": body.slug}, {"_id": 0, "slug": 1})
    if exists:
        raise HTTPException(status_code=409, detail="Slug already exists")
    doc = {**body.model_dump(), "created_at": iso(now_utc()), "updated_at": iso(now_utc())}
    await db.legal_docs.insert_one(doc)
    await db.admin_audit.insert_one({"admin_id": admin['user_id'], "action": "legal_create", "slug": body.slug, "at": iso(now_utc())})
    return {"ok": True, "slug": body.slug}

@api.put("/admin/legal/{slug}")
async def admin_legal_update(slug: str, body: LegalDocBody, admin: dict = Depends(require_admin)):
    if body.slug != slug:
        raise HTTPException(status_code=400, detail="Slug in body must match URL")
    r = await db.legal_docs.update_one(
        {"slug": slug},
        {"$set": {"title": body.title, "body": body.body, "updated_at": iso(now_utc())}},
    )
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Document not found")
    await db.admin_audit.insert_one({"admin_id": admin['user_id'], "action": "legal_update", "slug": slug, "at": iso(now_utc())})
    return {"ok": True}

@api.delete("/admin/legal/{slug}")
async def admin_legal_delete(slug: str, admin: dict = Depends(require_admin)):
    r = await db.legal_docs.delete_one({"slug": slug})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Document not found")
    await db.admin_audit.insert_one({"admin_id": admin['user_id'], "action": "legal_delete", "slug": slug, "at": iso(now_utc())})
    return {"ok": True}
# ────────── Admin Audit Log (read-only viewer) ──────────
@api.get("/admin/audit")
async def admin_audit_list(_: dict = Depends(require_admin), limit: int = 200):
    """Chronological audit log of admin mutations. Newest first."""
    rows = await db.admin_audit.find({}, {"_id": 0}).sort("at", -1).limit(limit).to_list(limit)
    return rows

# ────────── GridFS Backfill ──────────
@api.post("/admin/migrate/gridfs")
async def admin_backfill_gridfs(admin: dict = Depends(require_admin)):
    """One-shot: replace every base64 `data:` URL in users/messages/receipts/refunds
    with a GridFS-served /api/files/{id} URL. Idempotent — already-migrated URLs
    are left alone. Returns per-collection counts."""
    stats = {"users_photos": 0, "messages_media": 0, "receipts": 0, "refunds": 0, "errors": 0}

    async def migrate(data_url: str, kind: str, owner: Optional[str]) -> str:
        if not isinstance(data_url, str) or not data_url.startswith("data:"):
            return data_url
        try:
            return await store_data_url_in_gridfs(data_url, owner, kind)
        except Exception as e:
            stats["errors"] += 1
            logger.warning(f"backfill {kind} failed: {e}")
            return data_url

    # 1. User profile photos
    async for u in db.users.find({"photos": {"$elemMatch": {"$regex": "^data:"}}}, {"_id": 0, "user_id": 1, "photos": 1}):
        new_photos = []
        changed = False
        for p in u.get('photos') or []:
            if isinstance(p, str) and p.startswith("data:"):
                new_photos.append(await migrate(p, "profile_photo", u['user_id']))
                changed = True
                stats["users_photos"] += 1
            else:
                new_photos.append(p)
        if changed:
            await db.users.update_one({"user_id": u['user_id']}, {"$set": {"photos": new_photos}})

    # 2. Chat messages media_url
    async for m in db.messages.find({"media_url": {"$regex": "^data:"}}, {"_id": 0, "message_id": 1, "media_url": 1, "from_user": 1, "kind": 1}):
        new_url = await migrate(m['media_url'], f"chat_{m.get('kind', 'file')}", m.get('from_user'))
        if new_url != m['media_url']:
            await db.messages.update_one({"message_id": m['message_id']}, {"$set": {"media_url": new_url}})
            stats["messages_media"] += 1

    # 3. Receipt submissions
    async for r in db.receipt_submissions.find({"receipt_data_url": {"$regex": "^data:"}}, {"_id": 0, "submission_id": 1, "receipt_data_url": 1, "user_id": 1}):
        new_url = await migrate(r['receipt_data_url'], "support_receipt", r.get('user_id'))
        if new_url != r['receipt_data_url']:
            await db.receipt_submissions.update_one({"submission_id": r['submission_id']}, {"$set": {"receipt_data_url": new_url}})
            stats["receipts"] += 1

    # 4. Refund requests
    async for r in db.refund_requests.find({"receipt_data_url": {"$regex": "^data:"}}, {"_id": 0, "refund_id": 1, "receipt_data_url": 1, "user_id": 1}):
        new_url = await migrate(r['receipt_data_url'], "refund_receipt", r.get('user_id'))
        if new_url != r['receipt_data_url']:
            await db.refund_requests.update_one({"refund_id": r['refund_id']}, {"$set": {"receipt_data_url": new_url}})
            stats["refunds"] += 1

    total = sum(stats.values()) - stats["errors"]
    if total > 0 or stats["errors"] > 0:
        await db.admin_audit.insert_one({
            "admin_id": admin['user_id'], "action": "gridfs_backfill",
            "stats": stats, "at": iso(now_utc()),
        })
    return {"ok": True, "migrated": stats}
