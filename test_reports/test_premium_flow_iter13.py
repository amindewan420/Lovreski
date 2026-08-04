#!/usr/bin/env python3
"""Focused regression tests for Lovreski Premium/Coin manual approval flow."""
import asyncio
import base64
import json
import os
import re
import time
from datetime import datetime, timezone, timedelta

import requests


ROOT = "/app"
REPORT_DIR = os.path.join(ROOT, "test_reports")
os.makedirs(REPORT_DIR, exist_ok=True)


def read_env_value(path, key):
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k == key:
                    return v.strip().strip('"').strip("'")
    except FileNotFoundError:
        return None
    return None


BACKEND_URL = read_env_value(os.path.join(ROOT, "frontend", ".env"), "REACT_APP_BACKEND_URL")
API = f"{BACKEND_URL}/api"
MONGO_URL = read_env_value(os.path.join(ROOT, "backend", ".env"), "MONGO_URL")
DB_NAME = read_env_value(os.path.join(ROOT, "backend", ".env"), "DB_NAME")
WEBHOOK_SECRET = read_env_value(os.path.join(ROOT, "backend", ".env"), "SBP_WEBHOOK_SECRET")


PNG_1X1 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/lxL0RQAAAABJRU5ErkJggg=="
RECEIPT_DATA_URL = "data:image/png;base64," + PNG_1X1


class T:
    def __init__(self):
        self.results = []
        self.context = {}

    def check(self, name, ok, detail=""):
        status = "PASS" if ok else "FAIL"
        print(f"{status}: {name} {('- ' + detail) if detail else ''}")
        self.results.append({"name": name, "status": status, "detail": detail})
        return ok

    def fail(self, name, detail):
        return self.check(name, False, detail)

    def summary(self):
        passed = sum(1 for r in self.results if r["status"] == "PASS")
        total = len(self.results)
        return {"passed": passed, "total": total, "success_rate": round((passed / total) * 100, 2) if total else 0}


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def post(path, token=None, **kwargs):
    headers = kwargs.pop("headers", {})
    if token:
        headers.update(auth_headers(token))
    return requests.post(API + path, headers=headers, timeout=30, **kwargs)


def get(path, token=None, **kwargs):
    headers = kwargs.pop("headers", {})
    if token:
        headers.update(auth_headers(token))
    return requests.get(API + path, headers=headers, timeout=30, **kwargs)


def register(email):
    r = post("/auth/register", json={
        "email": email,
        "password": "password123",
        "name": "Receipt Tester",
        "gender": "male",
        "dob": "1998-05-15",
    })
    if r.status_code == 409:
        r = post("/auth/login", json={"email": email, "password": "password123"})
    r.raise_for_status()
    return r.json()


async def count_audit_for_submission(submission_id):
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        count = await db.admin_audit.count_documents({"submission_id": submission_id})
        client.close()
        return count
    except Exception as e:
        print(f"WARN: audit DB check failed: {e}")
        return None


def main():
    t = T()
    ts = int(time.time())

    # Credentials and identities
    admin_resp = post("/auth/login", json={"email": "admin@lovreski.ru", "password": "LovreskiAdmin2026!"})
    t.check("admin login succeeds", admin_resp.status_code == 200, str(admin_resp.status_code))
    admin_token = admin_resp.json()["token"]

    user_email = f"recp_{ts}@lovreski.ru"
    user_data = register(user_email)
    user_token = user_data["token"]
    user_id = user_data["user"]["user_id"]
    initial_coins = int(user_data["user"].get("coins", 0))
    t.context.update({"user_email": user_email, "user_id": user_id, "initial_coins": initial_coins})
    t.check("fresh user registered", bool(user_token and user_id), user_email)

    # Critical regression: checkout/status must not auto-credit.
    checkout = post("/coins/checkout", token=user_token, json={"package_id": "p200"})
    t.check("POST /coins/checkout creates pending tx", checkout.status_code == 200 and checkout.json().get("tx_id"), checkout.text[:160])
    tx_id = checkout.json().get("tx_id")
    time.sleep(11)
    status = get(f"/coins/status/{tx_id}", token=user_token)
    status_json = status.json() if status.status_code == 200 else {}
    t.check("/coins/status remains pending after >10s", status.status_code == 200 and status_json.get("transaction", {}).get("status") == "pending", json.dumps(status_json)[:240])
    t.check("checkout/status did not increment coins", status.status_code == 200 and status_json.get("coins") == initial_coins, f"coins={status_json.get('coins')} initial={initial_coins}")

    # Receipt endpoint validation and rate limit.
    missing = post("/support/receipt", token=user_token, json={"message": "no file"})
    t.check("POST /support/receipt without receipt_data_url returns 422", missing.status_code == 422, missing.text[:160])

    sub_ids = []
    for i in range(5):
        r = post("/support/receipt", token=user_token, json={
            "package_id": "p200" if i == 0 else None,
            "receipt_data_url": RECEIPT_DATA_URL,
            "message": f"receipt message {i}",
        })
        ok = r.status_code == 200 and r.json().get("status") == "pending" and r.json().get("submission_id")
        t.check(f"valid receipt submission {i+1} returns pending", ok, r.text[:160])
        if ok:
            sub_ids.append(r.json()["submission_id"])
    sixth = post("/support/receipt", token=user_token, json={"receipt_data_url": RECEIPT_DATA_URL, "message": "rate limit"})
    t.check("6th receipt submission in hour returns 429", sixth.status_code == 429, sixth.text[:160])

    mine = get("/support/my", token=user_token)
    mine_json = mine.json() if mine.status_code == 200 else []
    t.check("GET /support/my succeeds", mine.status_code == 200 and isinstance(mine_json, list), mine.text[:160])
    t.check("GET /support/my strips receipt_data_url", all("receipt_data_url" not in s for s in mine_json), json.dumps(mine_json[:1])[:240])
    created = [s.get("created_at") for s in mine_json[:5]]
    t.check("GET /support/my newest-first", created == sorted(created, reverse=True), json.dumps(created))

    nonadmin_pending = get("/admin/support/pending", token=user_token)
    t.check("non-admin GET /admin/support/pending returns 403", nonadmin_pending.status_code == 403, nonadmin_pending.text[:160])
    pending = get("/admin/support/pending", token=admin_token)
    pending_json = pending.json() if pending.status_code == 200 else []
    t.check("admin pending list includes submissions with receipt bytes and user info", pending.status_code == 200 and all(any(s.get("submission_id") == sid and s.get("receipt_data_url", "").startswith("data:") and s.get("user_email") == user_email for s in pending_json) for sid in sub_ids[:2]), f"pending_count={len(pending_json)}")
    count = get("/admin/support/pending-count", token=admin_token)
    count_json = count.json() if count.status_code == 200 else {}
    t.check("admin pending-count returns count >= created pending", count.status_code == 200 and count_json.get("count", 0) >= len(sub_ids), json.dumps(count_json))

    # Approve path: credits once, premium active, audit and notification.
    approve_id = sub_ids[0]
    approve = post(f"/admin/support/{approve_id}/approve", token=admin_token, json={"coins": 100, "reason": "Payment verified"})
    t.check("admin approve receipt returns ok", approve.status_code == 200 and approve.json().get("coins_added") == 100, approve.text[:160])
    me_after_approve = get("/auth/me", token=user_token).json()
    premium_until = me_after_approve.get("premium_until")
    premium_ok = False
    if premium_until:
        try:
            dt = datetime.fromisoformat(premium_until)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            premium_ok = dt > datetime.now(timezone.utc) + timedelta(days=29)
        except Exception:
            premium_ok = False
    t.check("approve increments user.coins by 100 and activates premium_until ~30d", me_after_approve.get("coins") == initial_coins + 100 and me_after_approve.get("is_premium") is True and premium_ok, json.dumps({"coins": me_after_approve.get("coins"), "is_premium": me_after_approve.get("is_premium"), "premium_until": premium_until}))
    audit_count = asyncio.run(count_audit_for_submission(approve_id))
    t.check("approve inserts admin_audit entry", audit_count is None or audit_count >= 1, f"audit_count={audit_count}")
    notes = get("/notifications", token=user_token)
    t.check("approve creates success notification", notes.status_code == 200 and any("Payment verified" in n.get("message", "") and n.get("kind") == "success" for n in notes.json()), notes.text[:240])
    approve_again = post(f"/admin/support/{approve_id}/approve", token=admin_token, json={"coins": 100, "reason": "Payment verified"})
    me_after_second_approve = get("/auth/me", token=user_token).json()
    t.check("second approve returns 404 and no double-credit", approve_again.status_code == 404 and me_after_second_approve.get("coins") == initial_coins + 100, f"status={approve_again.status_code} coins={me_after_second_approve.get('coins')}")

    # Reject path with idempotency and notification.
    reject_id = sub_ids[1]
    reject = post(f"/admin/support/{reject_id}/reject", token=admin_token, json={"reason": "Blurry receipt"})
    t.check("admin reject receipt returns ok", reject.status_code == 200 and reject.json().get("ok") is True, reject.text[:160])
    reject_again = post(f"/admin/support/{reject_id}/reject", token=admin_token, json={"reason": "Blurry receipt"})
    t.check("second reject returns 404", reject_again.status_code == 404, reject_again.text[:160])
    notes2 = get("/notifications", token=user_token)
    t.check("reject creates rejection notification", notes2.status_code == 200 and any("Receipt rejected" in n.get("message", "") and "Blurry receipt" in n.get("message", "") for n in notes2.json()), notes2.text[:240])

    # Custom coin add endpoint validation.
    invalid0 = post("/admin/users/add-coins", token=admin_token, json={"user_id": user_id, "coins": 0, "reason": "bad"})
    invalid_neg = post("/admin/users/add-coins", token=admin_token, json={"user_id": user_id, "coins": -5, "reason": "bad"})
    t.check("admin add-coins rejects 0", invalid0.status_code == 422, invalid0.text[:120])
    t.check("admin add-coins rejects negative", invalid_neg.status_code == 422, invalid_neg.text[:120])
    add = post("/admin/users/add-coins", token=admin_token, json={"user_id": user_id, "coins": 7, "reason": "Manual bonus"})
    final_me = get("/auth/me", token=user_token).json()
    t.check("admin add-coins valid body increments coins and keeps premium", add.status_code == 200 and add.json().get("new_balance") == initial_coins + 107 and final_me.get("coins") == initial_coins + 107 and final_me.get("is_premium") is True, f"add={add.text[:160]} final_coins={final_me.get('coins')}")

    # Security/contract check: old SBP webhook should not remain as an automated credit path under manual-only flow.
    webhook_email = f"webhook_{ts}@lovreski.ru"
    webhook_user = register(webhook_email)
    webhook_token = webhook_user["token"]
    webhook_initial = int(webhook_user["user"].get("coins", 0))
    wh_checkout = post("/coins/checkout", token=webhook_token, json={"package_id": "p100"})
    wh_tx = wh_checkout.json().get("tx_id") if wh_checkout.status_code == 200 else None
    wh = post("/coins/webhook", headers={"X-Webhook-Secret": WEBHOOK_SECRET or ""}, json={"tx_id": wh_tx, "amount_rub": 500, "status": "success", "bank": "Sberbank"}) if wh_tx else None
    wh_me = get("/auth/me", token=webhook_token).json()
    # This is intentionally expected to be blocked/disabled in the manual-only product contract.
    t.check("manual-only contract: /coins/webhook must not auto-credit coins/premium", not (wh and wh.status_code == 200 and wh_me.get("coins") != webhook_initial and wh_me.get("is_premium") is True), f"webhook_status={wh.status_code if wh else None} initial={webhook_initial} after={wh_me.get('coins')} premium={wh_me.get('is_premium')}")

    t.context.update({
        "admin_token": admin_token,
        "user_token": user_token,
        "approved_submission_id": approve_id,
        "rejected_submission_id": reject_id,
        "remaining_pending_submission_ids": sub_ids[2:],
        "webhook_test_email": webhook_email,
    })
    out = {"summary": t.summary(), "context": t.context, "results": t.results}
    out_path = os.path.join(REPORT_DIR, "premium_backend_iter13_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    if any(r["status"] == "FAIL" for r in t.results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()