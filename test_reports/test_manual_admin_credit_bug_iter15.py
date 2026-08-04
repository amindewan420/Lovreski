#!/usr/bin/env python3
"""Focused regression test for Iteration-14 manual-only coin credit contract.

Verifies legacy /api/admin/payments/{tx_id} approve/reject no longer credits
coins/premium, while the two allowed manual credit paths still work.
"""
import base64
import json
import os
import time
from pathlib import Path

import requests


ROOT = Path("/app")
REPORT_DIR = ROOT / "test_reports"
RESULT_PATH = REPORT_DIR / "manual_credit_backend_results_iter15.json"


def read_env(path: Path) -> dict:
    env = {}
    if not path.exists():
        return env
    for raw in path.read_text().splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        k, v = raw.split("=", 1)
        env[k] = v.strip().strip('"').strip("'")
    return env


frontend_env = read_env(ROOT / "frontend" / ".env")
backend_env = read_env(ROOT / "backend" / ".env")
BASE = os.environ.get("BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL") or "http://localhost:8001"
API = BASE.rstrip("/") + "/api"
ADMIN_EMAIL = backend_env.get("ADMIN_EMAIL", "admin@lovreski.ru")
ADMIN_PASSWORD = backend_env.get("ADMIN_PASSWORD", "LovreskiAdmin2026!")
WEBHOOK_SECRET = backend_env.get("SBP_WEBHOOK_SECRET", "")


class TestFailure(AssertionError):
    pass


def req(method, path, token=None, **kwargs):
    headers = kwargs.pop("headers", {}) or {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = requests.request(method, API + path, headers=headers, timeout=30, **kwargs)
    try:
        data = r.json()
    except Exception:
        data = r.text
    if r.status_code >= 400:
        raise TestFailure(f"{method} {path} failed {r.status_code}: {data}")
    return r.status_code, data


def assert_equal(actual, expected, message):
    if actual != expected:
        raise TestFailure(f"{message}: expected {expected!r}, got {actual!r}")


def assert_true(cond, message):
    if not cond:
        raise TestFailure(message)


def balance(user_token):
    _, data = req("GET", "/coins/balance", user_token)
    return {"coins": data.get("coins"), "is_premium": data.get("is_premium")}


def checkout(user_token, package_id="p100"):
    _, data = req("POST", "/coins/checkout", user_token, json={"package_id": package_id, "bank": "sberbank"})
    return data["tx_id"], data


def tx_status(user_token, tx_id):
    _, data = req("GET", f"/coins/status/{tx_id}", user_token)
    return data


def main():
    ts = int(time.time())
    email = f"leg_{ts}@lovreski.ru"
    password = "password123"
    results = {"base_url": BASE, "email": email, "steps": []}

    # Register fresh user and login admin.
    _, reg = req("POST", "/auth/register", json={
        "email": email,
        "password": password,
        "name": f"Legacy QA {ts}",
        "gender": "male",
        "dob": "1998-05-15",
    })
    user_token = reg["token"]
    user_id = reg["user"]["user_id"]
    _, admin_login = req("POST", "/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    admin_token = admin_login["token"]
    initial = balance(user_token)
    assert_equal(initial["coins"], 5, "Fresh test user starts with 5 coins")
    assert_equal(initial["is_premium"], False, "Fresh test user is not premium")
    results["steps"].append({"name": "fresh_user", "user_id": user_id, "balance": initial})

    # Exact bug: legacy admin payment approve should not mutate coins/premium.
    tx_approve, _ = checkout(user_token, "p100")
    before_approve = balance(user_token)
    code, approve_body = req("POST", f"/admin/payments/{tx_approve}", admin_token, json={"action": "approve"})
    after_approve = balance(user_token)
    approve_status = tx_status(user_token, tx_approve)["transaction"]["status"]
    assert_equal(code, 200, "Legacy admin payment approve returns 200")
    assert_equal(after_approve, before_approve, "Legacy admin payment approve must not alter coins/premium")
    note = approve_body.get("note", "") if isinstance(approve_body, dict) else ""
    assert_true("/admin/support/:id/approve" in note and "/admin/users/add-coins" in note,
                "Approve response note points to the two manual credit endpoints")
    results["steps"].append({
        "name": "legacy_admin_payment_approve_neutralized",
        "tx_id": tx_approve,
        "status_after": approve_status,
        "before": before_approve,
        "after": after_approve,
        "response": approve_body,
    })

    # Reject path should still mark rejected and not mutate coins/premium.
    tx_reject, _ = checkout(user_token, "p100")
    before_reject = balance(user_token)
    _, reject_body = req("POST", f"/admin/payments/{tx_reject}", admin_token, json={"action": "reject", "reason": "QA rejection"})
    after_reject = balance(user_token)
    reject_status = tx_status(user_token, tx_reject)["transaction"]["status"]
    assert_equal(reject_status, "rejected", "Legacy admin payment reject marks tx rejected")
    assert_equal(after_reject, before_reject, "Legacy admin payment reject must not alter coins/premium")
    results["steps"].append({
        "name": "legacy_admin_payment_reject_still_rejects",
        "tx_id": tx_reject,
        "status_after": reject_status,
        "before": before_reject,
        "after": after_reject,
        "response": reject_body,
    })

    # Checkout + status regression: polling should leave transaction pending and not credit.
    tx_pending, _ = checkout(user_token, "p100")
    before_status = balance(user_token)
    status_body = tx_status(user_token, tx_pending)
    after_status = balance(user_token)
    assert_equal(status_body["transaction"]["status"], "pending", "Checkout status remains pending")
    assert_equal(after_status, before_status, "Checkout status polling must not alter coins/premium")
    results["steps"].append({
        "name": "checkout_status_remains_pending_no_credit",
        "tx_id": tx_pending,
        "status_response": status_body,
        "before": before_status,
        "after": after_status,
    })

    # Webhook regression: success webhook queues a support item, does not credit.
    tx_webhook, checkout_body = checkout(user_token, "p100")
    before_webhook = balance(user_token)
    _, webhook_body = req(
        "POST",
        "/coins/webhook",
        json={"tx_id": tx_webhook, "status": "success", "amount_rub": checkout_body["amount_rub"], "bank": "Sberbank"},
        headers={"X-Webhook-Secret": WEBHOOK_SECRET},
    )
    after_webhook = balance(user_token)
    webhook_status = tx_status(user_token, tx_webhook)["transaction"]["status"]
    assert_equal(webhook_body.get("queued_for_admin"), True, "Webhook queues payment for admin approval")
    assert_equal(after_webhook, before_webhook, "Webhook success must not alter coins/premium")
    assert_equal(webhook_status, "awaiting_admin", "Webhook marks tx awaiting_admin, not success/credited")
    _, pending_subs = req("GET", "/admin/support/pending", admin_token)
    webhook_sub = next((s for s in pending_subs if s.get("user_id") == user_id and tx_webhook in (s.get("message") or "")), None)
    assert_true(webhook_sub is not None, "Webhook created a pending support submission")
    results["steps"].append({
        "name": "webhook_queues_no_credit",
        "tx_id": tx_webhook,
        "submission_id": webhook_sub["submission_id"],
        "status_after": webhook_status,
        "before": before_webhook,
        "after": after_webhook,
        "response": webhook_body,
    })

    # Allowed manual approval path: support approve credits and activates premium.
    approve_coins = 37
    before_support_approve = balance(user_token)
    _, support_approve_body = req(
        "POST",
        f"/admin/support/{webhook_sub['submission_id']}/approve",
        admin_token,
        json={"coins": approve_coins, "reason": "QA verified manual approval"},
    )
    after_support_approve = balance(user_token)
    assert_equal(after_support_approve["coins"], before_support_approve["coins"] + approve_coins,
                 "Support approve credits requested coins")
    assert_equal(after_support_approve["is_premium"], True, "Support approve activates premium")
    results["steps"].append({
        "name": "support_approve_allowed_credit_path",
        "submission_id": webhook_sub["submission_id"],
        "before": before_support_approve,
        "after": after_support_approve,
        "response": support_approve_body,
    })

    # Allowed custom add-coins path: still credits coins.
    add_coins = 11
    before_add = balance(user_token)
    _, add_body = req("POST", "/admin/users/add-coins", admin_token, json={
        "user_id": user_id,
        "coins": add_coins,
        "reason": "QA custom add-coins regression",
    })
    after_add = balance(user_token)
    assert_equal(after_add["coins"], before_add["coins"] + add_coins, "Admin add-coins credits requested amount")
    assert_equal(after_add["is_premium"], True, "Admin add-coins leaves/activates premium")
    results["steps"].append({
        "name": "admin_users_add_coins_allowed_credit_path",
        "before": before_add,
        "after": after_add,
        "response": add_body,
    })

    # Leave one pending submission for frontend admin pending badge verification.
    tiny_png = "data:image/png;base64," + base64.b64encode(b"qa-placeholder").decode()
    _, ui_sub = req("POST", "/support/receipt", user_token, json={
        "package_id": "p100",
        "receipt_data_url": tiny_png,
        "message": f"UI pending badge seed {ts}",
    })
    _, pending_count = req("GET", "/admin/support/pending-count", admin_token)
    assert_true(pending_count.get("count", 0) >= 1, "At least one pending support item exists for UI badge")
    results["steps"].append({"name": "ui_pending_seed", "submission_id": ui_sub["submission_id"], "pending_count": pending_count})

    results.update({
        "ok": True,
        "admin_email": ADMIN_EMAIL,
        "test_user_id": user_id,
        "final_balance": after_add,
        "ui_seed_submission_id": ui_sub["submission_id"],
    })
    RESULT_PATH.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        failure = {"ok": False, "error": str(e), "base_url": BASE}
        RESULT_PATH.write_text(json.dumps(failure, indent=2, ensure_ascii=False))
        print(json.dumps(failure, indent=2, ensure_ascii=False))
        raise