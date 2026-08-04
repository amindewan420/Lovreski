#!/usr/bin/env python3
"""Focused bug verification for Iteration-13 critical webhook auto-credit regression.

Contract under test:
- POST /api/coins/webhook must not credit coins or activate Premium unless AUTO_CREDIT_ENABLED=1.
- Successful signed webhook should queue a pending receipt submission for admin review.
- Coins/Premium may be changed only by /admin/support/{id}/approve or /admin/users/add-coins.
"""

import json
import os
import time
import uuid
from pathlib import Path

import requests


ROOT = Path("/app")
REPORT_DIR = ROOT / "test_reports"
RESULTS_PATH = REPORT_DIR / "webhook_manual_approval_bug_iter14_results.json"


def parse_env(path: Path) -> dict:
    data = {}
    if not path.exists():
        return data
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        data[k.strip()] = v.strip().strip('"').strip("'")
    return data


front_env = parse_env(ROOT / "frontend" / ".env")
back_env = parse_env(ROOT / "backend" / ".env")

BASE_URL = front_env.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
WEBHOOK_SECRET = back_env.get("SBP_WEBHOOK_SECRET")
ADMIN_EMAIL = back_env.get("ADMIN_EMAIL", "admin@lovreski.ru")
ADMIN_PASSWORD = back_env.get("ADMIN_PASSWORD", "LovreskiAdmin2026!")

results = []
context = {
    "base_url": BASE_URL,
    "auto_credit_enabled_env": back_env.get("AUTO_CREDIT_ENABLED", "<unset/default false>"),
}


def record(name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {name}: {detail}")
    results.append({"name": name, "status": status, "detail": str(detail)[:1500]})


def request(method, path, **kwargs):
    kwargs.setdefault("timeout", 25)
    return requests.request(method, f"{BASE_URL}/api{path}", **kwargs)


def safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return {"raw": resp.text[:1000]}


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def balance(user_token):
    resp = request("GET", "/coins/balance", headers=auth_header(user_token))
    return resp.status_code, safe_json(resp)


def checkout(user_token, package_id):
    return request("POST", "/coins/checkout", headers=auth_header(user_token), json={"package_id": package_id})


def find_pending_submission(admin_token, user_id, tx_id=None, submission_id=None):
    resp = request("GET", "/admin/support/pending", headers=auth_header(admin_token))
    data = safe_json(resp)
    if resp.status_code != 200 or not isinstance(data, list):
        return resp.status_code, data, None
    for sub in data:
        if sub.get("user_id") != user_id:
            continue
        if submission_id and sub.get("submission_id") == submission_id:
            return resp.status_code, data, sub
        if tx_id and tx_id in (sub.get("message") or ""):
            return resp.status_code, data, sub
    return resp.status_code, data, None


def main():
    if not WEBHOOK_SECRET:
        record("SBP_WEBHOOK_SECRET present", False, "Missing in /app/backend/.env")
        return
    record("SBP_WEBHOOK_SECRET present", True, "using configured secret (not printed)")

    admin_resp = request("POST", "/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    admin_data = safe_json(admin_resp)
    admin_token = admin_data.get("token")
    record("admin login succeeds", admin_resp.status_code == 200 and bool(admin_token), admin_resp.status_code)
    if not admin_token:
        return

    email = f"whk_{int(time.time())}_{uuid.uuid4().hex[:6]}@lovreski.ru"
    reg_body = {
        "email": email,
        "password": "password123",
        "name": "Webhook Bug Tester",
        "gender": "male",
        "dob": "1998-05-15",
    }
    reg_resp = request("POST", "/auth/register", json=reg_body)
    reg_data = safe_json(reg_resp)
    user_token = reg_data.get("token")
    user = reg_data.get("user", {})
    user_id = user.get("user_id")
    context.update({"user_email": email, "user_id": user_id})
    record("fresh webhook test user registered", reg_resp.status_code == 200 and bool(user_token), reg_resp.status_code)
    if not user_token:
        return

    b_status, initial_balance = balance(user_token)
    initial_coins = initial_balance.get("coins")
    initial_premium = initial_balance.get("is_premium")
    context.update({"initial_coins": initial_coins, "initial_premium": initial_premium})
    record("initial user balance is non-premium", b_status == 200 and initial_coins == 5 and initial_premium is False, initial_balance)

    # 1) Invalid secret must stay unauthorized.
    c1 = checkout(user_token, "p100")
    tx1 = safe_json(c1)
    tx1_id = tx1.get("tx_id")
    context["valid_webhook_tx_id"] = tx1_id
    record("checkout for valid webhook test creates pending tx", c1.status_code == 200 and bool(tx1_id), tx1)
    if not tx1_id:
        return

    invalid_resp = request(
        "POST",
        "/coins/webhook",
        headers={"X-Webhook-Secret": "definitely-invalid-secret"},
        json={"tx_id": tx1_id, "status": "success", "amount_rub": tx1.get("amount_rub"), "bank": "sberbank"},
    )
    record("POST /coins/webhook with invalid secret returns 401", invalid_resp.status_code == 401, f"{invalid_resp.status_code} {safe_json(invalid_resp)}")

    # 2) Valid success webhook must queue for admin without changing balance/premium.
    success_resp = request(
        "POST",
        "/coins/webhook",
        headers={"X-Webhook-Secret": WEBHOOK_SECRET},
        json={"tx_id": tx1_id, "status": "success", "amount_rub": tx1.get("amount_rub"), "bank": "sberbank"},
    )
    success_data = safe_json(success_resp)
    record(
        "valid success webhook returns ok true + queued_for_admin true",
        success_resp.status_code == 200 and success_data.get("ok") is True and success_data.get("queued_for_admin") is True,
        f"{success_resp.status_code} {success_data}",
    )

    after_status, after_webhook_balance = balance(user_token)
    no_auto_credit = (
        after_status == 200
        and after_webhook_balance.get("coins") == initial_coins
        and after_webhook_balance.get("is_premium") == initial_premium
    )
    record("valid success webhook does NOT increment coins or activate Premium", no_auto_credit, after_webhook_balance)

    status_resp = request("GET", f"/coins/status/{tx1_id}", headers=auth_header(user_token))
    status_data = safe_json(status_resp)
    record(
        "webhook-updated tx is awaiting_admin and not credited in status response",
        status_resp.status_code == 200
        and status_data.get("transaction", {}).get("status") == "awaiting_admin"
        and status_data.get("transaction", {}).get("credited") is False,
        status_data,
    )

    pending_status, pending_list, webhook_sub = find_pending_submission(admin_token, user_id, tx_id=tx1_id)
    context["webhook_submission_id"] = webhook_sub.get("submission_id") if webhook_sub else None
    record(
        "webhook creates a pending receipt_submission visible in admin pending",
        pending_status == 200 and webhook_sub is not None and webhook_sub.get("status") == "pending" and webhook_sub.get("receipt_data_url") is None,
        webhook_sub or f"pending_status={pending_status}, pending_count={len(pending_list) if isinstance(pending_list, list) else 'n/a'}",
    )

    # 3) Amount mismatch must fail the transaction and not credit.
    c2 = checkout(user_token, "p200")
    tx2 = safe_json(c2)
    tx2_id = tx2.get("tx_id")
    context["mismatch_tx_id"] = tx2_id
    record("checkout for mismatch test creates pending tx", c2.status_code == 200 and bool(tx2_id), tx2)
    if tx2_id:
        mismatch_resp = request(
            "POST",
            "/coins/webhook",
            headers={"X-Webhook-Secret": WEBHOOK_SECRET},
            json={"tx_id": tx2_id, "status": "success", "amount_rub": tx2.get("amount_rub", 0) + 1, "bank": "tbank"},
        )
        mismatch_data = safe_json(mismatch_resp)
        record("amount mismatch webhook returns ok false", mismatch_resp.status_code == 200 and mismatch_data.get("ok") is False, f"{mismatch_resp.status_code} {mismatch_data}")
        mismatch_status_resp = request("GET", f"/coins/status/{tx2_id}", headers=auth_header(user_token))
        mismatch_status = safe_json(mismatch_status_resp)
        record("amount mismatch marks tx.status failed", mismatch_status_resp.status_code == 200 and mismatch_status.get("transaction", {}).get("status") == "failed", mismatch_status)
        _, after_mismatch_balance = balance(user_token)
        record("amount mismatch does not credit coins/premium", after_mismatch_balance.get("coins") == initial_coins and after_mismatch_balance.get("is_premium") == initial_premium, after_mismatch_balance)

    # 4) /coins/status regression: auto-confirm remains off for ordinary checkout.
    c3 = checkout(user_token, "p300")
    tx3 = safe_json(c3)
    tx3_id = tx3.get("tx_id")
    context["pending_status_tx_id"] = tx3_id
    record("checkout for status-pending regression creates tx", c3.status_code == 200 and bool(tx3_id), tx3)
    if tx3_id:
        time.sleep(9.5)
        pending_resp = request("GET", f"/coins/status/{tx3_id}", headers=auth_header(user_token))
        pending_data = safe_json(pending_resp)
        record(
            "/coins/status remains pending after auto-confirm delay when AUTO_CREDIT_ENABLED is off",
            pending_resp.status_code == 200
            and pending_data.get("transaction", {}).get("status") == "pending"
            and pending_data.get("coins") == initial_coins
            and pending_data.get("is_premium") == initial_premium,
            pending_data,
        )

    # 5) Admin approve of webhook-created pending item is the manual crediting path.
    if webhook_sub:
        approve_resp = request(
            "POST",
            f"/admin/support/{webhook_sub['submission_id']}/approve",
            headers=auth_header(admin_token),
            json={"coins": tx1.get("coins"), "reason": "Verified queued webhook payment"},
        )
        approve_data = safe_json(approve_resp)
        record("admin can approve webhook-created pending submission", approve_resp.status_code == 200 and approve_data.get("ok") is True, f"{approve_resp.status_code} {approve_data}")
        _, after_approval_balance = balance(user_token)
        expected_after_approval = initial_coins + tx1.get("coins", 0)
        record(
            "admin support approval increments coins and activates Premium",
            after_approval_balance.get("coins") == expected_after_approval and after_approval_balance.get("is_premium") is True,
            {"expected_coins": expected_after_approval, "actual": after_approval_balance},
        )
        second_approve_resp = request(
            "POST",
            f"/admin/support/{webhook_sub['submission_id']}/approve",
            headers=auth_header(admin_token),
            json={"coins": tx1.get("coins"), "reason": "Duplicate approval attempt"},
        )
        _, after_second_approval_balance = balance(user_token)
        record(
            "second approve returns 404 and does not double-credit",
            second_approve_resp.status_code == 404 and after_second_approval_balance.get("coins") == expected_after_approval,
            {"status": second_approve_resp.status_code, "balance": after_second_approval_balance},
        )

    # 6) Manual receipt submit/reject regression.
    missing_receipt_resp = request("POST", "/support/receipt", headers=auth_header(user_token), json={"message": "no file"})
    record("/support/receipt without file returns 422", missing_receipt_resp.status_code == 422, f"{missing_receipt_resp.status_code} {safe_json(missing_receipt_resp)}")

    receipt_resp = request(
        "POST",
        "/support/receipt",
        headers=auth_header(user_token),
        json={"package_id": "p100", "receipt_data_url": "data:image/png;base64,iVBORw0KGgo=", "message": "manual reject regression receipt"},
    )
    receipt_data = safe_json(receipt_resp)
    manual_sub_id = receipt_data.get("submission_id")
    context["manual_receipt_submission_id"] = manual_sub_id
    record("/support/receipt valid upload returns pending", receipt_resp.status_code == 200 and receipt_data.get("status") == "pending" and bool(manual_sub_id), f"{receipt_resp.status_code} {receipt_data}")
    if manual_sub_id:
        _, _, manual_sub = find_pending_submission(admin_token, user_id, submission_id=manual_sub_id)
        record("manual receipt is visible in admin pending", manual_sub is not None and manual_sub.get("receipt_data_url"), manual_sub)
        reject_resp = request("POST", f"/admin/support/{manual_sub_id}/reject", headers=auth_header(admin_token), json={"reason": "Blurry receipt"})
        record("admin reject receipt returns ok", reject_resp.status_code == 200 and safe_json(reject_resp).get("ok") is True, f"{reject_resp.status_code} {safe_json(reject_resp)}")
        second_reject_resp = request("POST", f"/admin/support/{manual_sub_id}/reject", headers=auth_header(admin_token), json={"reason": "Duplicate reject"})
        record("second reject returns 404", second_reject_resp.status_code == 404, f"{second_reject_resp.status_code} {safe_json(second_reject_resp)}")

    # 7) Admin add-coins regression.
    zero_resp = request("POST", "/admin/users/add-coins", headers=auth_header(admin_token), json={"user_id": user_id, "coins": 0, "reason": "invalid zero"})
    neg_resp = request("POST", "/admin/users/add-coins", headers=auth_header(admin_token), json={"user_id": user_id, "coins": -5, "reason": "invalid negative"})
    record("admin add-coins rejects zero", zero_resp.status_code == 422, f"{zero_resp.status_code} {safe_json(zero_resp)}")
    record("admin add-coins rejects negative", neg_resp.status_code == 422, f"{neg_resp.status_code} {safe_json(neg_resp)}")

    _, before_add_balance = balance(user_token)
    add_resp = request("POST", "/admin/users/add-coins", headers=auth_header(admin_token), json={"user_id": user_id, "coins": 7, "reason": "Bug verification custom add"})
    add_data = safe_json(add_resp)
    _, after_add_balance = balance(user_token)
    record(
        "admin add-coins valid body increments coins and keeps Premium active",
        add_resp.status_code == 200
        and add_data.get("ok") is True
        and after_add_balance.get("coins") == before_add_balance.get("coins", 0) + 7
        and after_add_balance.get("is_premium") is True,
        {"response": add_data, "before": before_add_balance, "after": after_add_balance},
    )

    # 8) Forbidden legacy credit path check: contract says only support approve or add-coins may credit.
    legacy_checkout = checkout(user_token, "p100")
    legacy_tx = safe_json(legacy_checkout)
    legacy_tx_id = legacy_tx.get("tx_id")
    context["legacy_admin_payments_tx_id"] = legacy_tx_id
    record("checkout for forbidden legacy admin payments path creates tx", legacy_checkout.status_code == 200 and bool(legacy_tx_id), legacy_tx)
    if legacy_tx_id:
        _, before_legacy_balance = balance(user_token)
        legacy_approve = request(
            "POST",
            f"/admin/payments/{legacy_tx_id}",
            headers=auth_header(admin_token),
            json={"action": "approve"},
        )
        legacy_approve_data = safe_json(legacy_approve)
        _, after_legacy_balance = balance(user_token)
        record(
            "FORBIDDEN: /admin/payments/{tx_id} approve must not be a coin-credit path",
            legacy_approve.status_code >= 400 or after_legacy_balance.get("coins") == before_legacy_balance.get("coins"),
            {"response_status": legacy_approve.status_code, "response": legacy_approve_data, "before": before_legacy_balance, "after": after_legacy_balance},
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        record("test script crashed", False, repr(exc))
    passed = sum(1 for r in results if r["status"] == "PASS")
    total = len(results)
    out = {
        "summary": {"passed": passed, "total": total, "success_rate": round((passed / total) * 100, 2) if total else 0},
        "context": context,
        "results": results,
    }
    RESULTS_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(json.dumps(out["summary"], indent=2))