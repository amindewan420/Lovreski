"""Coins & Premium routes — /coins/*, /support/receipt, /support/my"""
from fastapi import HTTPException, Depends, Request
from pydantic import BaseModel, Field
from typing import Optional
from datetime import timedelta
import io, uuid, base64, os
from server import (
    api, db, logger, now_utc, iso, fcm,
    get_current_user,
    _get_admin_sbp_phone, _build_sbp_link, _qr_png_base64, _try_auto_confirm,
    _compress_image_data_url, gridfs_put, gridfs_url, store_data_url_in_gridfs, storage_put,
    COIN_PACKAGES, AUTO_CREDIT_ENABLED, MOCK_CONFIRM_DELAY_SECONDS,
    PurchaseBody,
)

@api.get("/coins/packages")
async def coin_packages():
    """Public packages + admin SBP phone (per updated spec, users need to see the
    payment recipient number and copy it into their bank app)."""
    s = await db.settings.find_one({"key": "app"}, {"_id": 0}) or {}
    packages = s.get('packages') or COIN_PACKAGES
    for p in packages:
        p['popular'] = (p['id'] == 'p300')  # 300 coins = best value (4 ₽/coin)
    # Fetch the admin SBP phone (encrypted at rest) so users can copy it
    sbp_phone = await _get_admin_sbp_phone()
    return {
        "packages": packages,
        "currency": "RUB",
        "sbp_phone": sbp_phone,
        "recipient_name": os.environ.get('SBP_RECIPIENT_NAME', 'Al Amin Dewan'),
        "banks": [
            {"id": "sberbank", "name": "Сбербанк"},
            {"id": "tbank", "name": "T-Bank (Тинькофф)"},
        ],
    }

@api.post("/coins/checkout")
async def coins_checkout(body: PurchaseBody, request: Request, user: dict = Depends(get_current_user)):
    """Create a payment transaction and return SBP link + QR (server-side only knows the phone)."""
    # Rate limit: 5 payment attempts per user per hour
    since = now_utc() - timedelta(hours=1)
    recent = await db.transactions.count_documents({"user_id": user['user_id'], "created_at": {"$gte": iso(since)}})
    if recent >= 5:
        raise HTTPException(status_code=429, detail="Too many payment attempts. Please try again later.")

    s = await db.settings.find_one({"key": "app"}, {"_id": 0}) or {}
    packages = s.get('packages') or COIN_PACKAGES
    pkg = next((p for p in packages if p['id'] == body.package_id), None)
    if not pkg:
        raise HTTPException(status_code=400, detail="Package not found")

    admin_phone = await _get_admin_sbp_phone()
    if not admin_phone:
        raise HTTPException(status_code=500, detail="Payment provider not configured")

    tx_id = f"tx_{uuid.uuid4().hex[:12]}"
    sbp_link = _build_sbp_link(admin_phone, pkg['price'], tx_id)
    ip = request.client.host if request.client else None

    tx = {
        "tx_id": tx_id,
        "user_id": user['user_id'],
        "user_email": user.get('email'),
        "user_name": user.get('name'),
        "package_id": pkg['id'],
        "coins": pkg['coins'],
        "amount_rub": pkg['price'],
        "payment_method": "SBP",
        "bank": body.bank,  # sender's chosen bank (sberbank | tbank | None)
        "status": "pending",  # pending → success | failed
        "credited": False,
        "ip": ip,
        "sbp_link_hash": hash(sbp_link),
        "created_at": iso(now_utc()),
        "auto_confirm_at": iso(now_utc() + timedelta(seconds=MOCK_CONFIRM_DELAY_SECONDS)),
    }
    await db.transactions.insert_one(tx)
    tx.pop('_id', None)
    return {
        "tx_id": tx_id,
        "amount_rub": pkg['price'],
        "coins": pkg['coins'],
        "sbp_link": sbp_link,
        "qr_png": _qr_png_base64(sbp_link),
        "expires_in": 600,  # 10 minutes
        # Deliberately NOT returning the admin phone number.
    }

@api.get("/coins/status/{tx_id}")
async def coins_status(tx_id: str, user: dict = Depends(get_current_user)):
    """Polled every 3s by the payment popup. Returns tx status + fresh user balance."""
    # Fetch WITH auto_confirm_at so _try_auto_confirm can respect the delay,
    # then strip sensitive fields before returning to the client.
    tx = await db.transactions.find_one({"tx_id": tx_id, "user_id": user['user_id']}, {"_id": 0, "sbp_link_hash": 0, "ip": 0})
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    tx = await _try_auto_confirm(tx)
    tx.pop('auto_confirm_at', None)
    fresh = await db.users.find_one({"user_id": user['user_id']}, {"_id": 0})
    return {"transaction": tx, "coins": fresh.get('coins', 0), "is_premium": fresh.get('is_premium', False)}

@api.post("/coins/webhook")
async def coins_webhook(payload: dict, request: Request):
    """SBP webhook. Under the manual-approval flow, this endpoint NO LONGER
    credits coins directly — it only records the incoming payment claim as a
    pending 'receipt submission' that the admin must approve just like a
    user-uploaded screenshot. To re-enable direct crediting (real Sberbank
    signed webhook in production), set AUTO_CREDIT_ENABLED=1."""
    secret = request.headers.get('X-Webhook-Secret')
    expected = os.environ.get('SBP_WEBHOOK_SECRET')
    if not expected:
        raise HTTPException(status_code=503, detail="Webhook secret not configured")
    if secret != expected:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")
    tx_id = payload.get('tx_id')
    tx = await db.transactions.find_one({"tx_id": tx_id}, {"_id": 0})
    if not tx: raise HTTPException(status_code=404, detail="tx not found")
    if payload.get('status') != 'success' or payload.get('amount_rub') != tx['amount_rub']:
        await db.transactions.update_one({"tx_id": tx_id, "credited": False}, {"$set": {"status": "failed", "fail_reason": "Amount mismatch or bank error"}})
        return {"ok": False}
    if not AUTO_CREDIT_ENABLED:
        # Manual-approval flow: record as a pending receipt submission for the admin
        # instead of crediting the user directly.
        await db.transactions.update_one({"tx_id": tx_id}, {"$set": {"status": "awaiting_admin", "bank": payload.get('bank') or tx.get('bank')}})
        sub_id = f"sub_{uuid.uuid4().hex[:12]}"
        await db.receipt_submissions.insert_one({
            "submission_id": sub_id,
            "user_id": tx['user_id'],
            "user_email": tx.get('user_email'),
            "user_name": tx.get('user_name'),
            "package_id": tx.get('package_id'),
            "receipt_data_url": None,
            "message": f"[SBP webhook] tx {tx_id} · {payload.get('bank') or 'bank'} · {tx['amount_rub']} ₽",
            "status": "pending",
            "created_at": iso(now_utc()),
        })
        return {"ok": True, "queued_for_admin": True}
    # Legacy direct-credit path (only when explicitly enabled)
    res = await db.transactions.find_one_and_update(
        {"tx_id": tx_id, "credited": False, "status": "pending"},
        {"$set": {"status": "success", "credited": True, "bank": payload.get('bank') or "Sberbank", "confirmed_at": iso(now_utc())}},
    )
    if res:
        await db.users.update_one(
            {"user_id": tx['user_id']},
            {"$inc": {"coins": tx['coins']}, "$set": {"is_premium": True, "premium_until": iso(now_utc() + timedelta(days=30))}},
        )
    return {"ok": True}

@api.get("/coins/transactions")
async def user_transactions(user: dict = Depends(get_current_user)):
    tx = await db.transactions.find(
        {"user_id": user['user_id']},
        {"_id": 0, "sbp_link_hash": 0, "auto_confirm_at": 0, "ip": 0},
    ).sort("created_at", -1).to_list(200)
    return tx

@api.get("/coins/balance")
async def coin_balance(user: dict = Depends(get_current_user)):
    fresh = await db.users.find_one({"user_id": user['user_id']}, {"_id": 0})
    return {"coins": fresh.get('coins', 0), "is_premium": fresh.get('is_premium', False)}
class ReceiptBody(BaseModel):
    package_id: Optional[str] = None
    receipt_data_url: str  # base64 data URL (JPG/PNG/PDF)
    message: Optional[str] = Field(default=None, max_length=500)

@api.post("/support/receipt")
async def submit_receipt(body: ReceiptBody, user: dict = Depends(get_current_user)):
    """User uploads a payment receipt image/PDF for admin verification.
    Coins are NOT credited here — only after admin approval."""
    if not body.receipt_data_url.startswith("data:"):
        raise HTTPException(status_code=400, detail="Invalid receipt format")
    # Rate-limit 5 receipts per hour
    since = now_utc() - timedelta(hours=1)
    recent = await db.receipt_submissions.count_documents({"user_id": user['user_id'], "created_at": {"$gte": iso(since)}})
    if recent >= 5:
        raise HTTPException(status_code=429, detail="Too many submissions. Try again later.")
    # Store receipt in GridFS (was base64 in Mongo doc)
    receipt = body.receipt_data_url
    if receipt.startswith("data:image/"):
        try:
            _, compressed_bytes = _compress_image_data_url(receipt, max_dim=1800, quality=85)
            if compressed_bytes:
                receipt_url = (await storage_put(compressed_bytes, f"receipt_{uuid.uuid4().hex[:10]}.jpg", "image/jpeg",
                                                 {"owner_id": user['user_id'], "kind": "support_receipt"}))["url"]
            else:
                receipt_url = await store_data_url_in_gridfs(receipt, user['user_id'], "support_receipt")
        except Exception:
            receipt_url = await store_data_url_in_gridfs(receipt, user['user_id'], "support_receipt")
    else:
        receipt_url = await store_data_url_in_gridfs(receipt, user['user_id'], "support_receipt")
    sub_id = f"sub_{uuid.uuid4().hex[:12]}"
    await db.receipt_submissions.insert_one({
        "submission_id": sub_id,
        "user_id": user['user_id'],
        "user_email": user.get('email'),
        "user_name": user.get('name'),
        "package_id": body.package_id,
        "receipt_data_url": receipt_url,
        "message": body.message,
        "status": "pending",  # pending → verified | rejected
        "created_at": iso(now_utc()),
    })
    # Alert all admins of the new receipt
    try:
        await fcm.notify_admin_new_submission(db, "receipt", user.get("name") or user.get("email") or "user")
    except Exception as e:
        logger.warning(f"[push] admin receipt notify failed: {e}")
    return {"submission_id": sub_id, "status": "pending"}

@api.get("/support/my")
async def my_submissions(user: dict = Depends(get_current_user)):
    subs = await db.receipt_submissions.find(
        {"user_id": user['user_id']},
        {"_id": 0, "receipt_data_url": 0},
    ).sort("created_at", -1).to_list(50)
    return subs
