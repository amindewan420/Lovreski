"""
Iteration 17 backend tests — AdminNotifier polling endpoint + full manual-approval regression.
Verifies:
  - /api/admin/support/pending-count returns 200 for admin, 403 for regular user
  - Fresh user can POST /api/support/receipt → pending count increments
  - Admin approve credits coins, activates Premium
  - SBP phone regression from iteration 16 still holds
"""
import os
import time
import base64
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://lovreski-dating.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@lovreski.ru"
ADMIN_PASS = "LovreskiAdmin2026!"

# 1x1 png data URL (transparent) — sufficient receipt payload
TINY_PNG = (
    "data:image/png;base64,"
    + base64.b64encode(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
            "0000000d49444154789c6300010000000500010d0a2db40000000049454e44ae426082"
        )
    ).decode()
)


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    tok = r.json().get("token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def user_token():
    ts = int(time.time())
    email = f"notif_{ts}@lovreski.ru"
    payload = {
        "email": email,
        "password": "password123",
        "name": "NotifTester",
        "gender": "male",
        "dob": "1998-05-15",
    }
    r = requests.post(f"{API}/auth/register", json=payload, timeout=15)
    assert r.status_code in (200, 201), f"register failed: {r.status_code} {r.text}"
    data = r.json()
    tok = data.get("token")
    uid = data.get("user", {}).get("user_id") or data.get("user", {}).get("id")
    assert tok
    return {"token": tok, "email": email, "user_id": uid}


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


def test_pending_count_admin_ok(admin_token):
    r = requests.get(f"{API}/admin/support/pending-count", headers=_h(admin_token), timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "count" in body and isinstance(body["count"], int)
    assert body["count"] >= 0


def test_pending_count_forbidden_for_regular_user(user_token):
    r = requests.get(f"{API}/admin/support/pending-count", headers=_h(user_token["token"]), timeout=15)
    assert r.status_code == 403, f"expected 403, got {r.status_code} {r.text}"


def test_pending_count_no_auth():
    r = requests.get(f"{API}/admin/support/pending-count", timeout=15)
    assert r.status_code in (401, 403)


def test_receipt_submission_increments_count(admin_token, user_token):
    # baseline
    b = requests.get(f"{API}/admin/support/pending-count", headers=_h(admin_token), timeout=15).json()["count"]

    r = requests.post(
        f"{API}/support/receipt",
        headers=_h(user_token["token"]),
        json={"package_id": "premium_month", "receipt_data_url": TINY_PNG, "message": "iter17 test"},
        timeout=20,
    )
    assert r.status_code == 200, r.text
    sub_id = r.json().get("submission_id")
    assert sub_id and sub_id.startswith("sub_")

    # allow eventual consistency
    time.sleep(1)
    a = requests.get(f"{API}/admin/support/pending-count", headers=_h(admin_token), timeout=15).json()["count"]
    assert a >= b + 1, f"count did not increment: before={b} after={a}"

    # pending list contains the new submission
    lst = requests.get(f"{API}/admin/support/pending", headers=_h(admin_token), timeout=15).json()
    ids = [s.get("submission_id") for s in lst]
    assert sub_id in ids

    # store on the fixture-shared user_token for regression test to reuse
    user_token["submission_id"] = sub_id


def test_admin_approve_credits_and_activates_premium(admin_token, user_token):
    sub_id = user_token.get("submission_id")
    if not sub_id:
        # create one if the previous test didn't run
        r = requests.post(
            f"{API}/support/receipt",
            headers=_h(user_token["token"]),
            json={"package_id": "premium_month", "receipt_data_url": TINY_PNG, "message": "iter17 approve"},
            timeout=20,
        )
        assert r.status_code == 200
        sub_id = r.json()["submission_id"]

    # Pre-check user coins
    me_before = requests.get(f"{API}/auth/me", headers=_h(user_token["token"]), timeout=15).json()
    coins_before = me_before.get("coins", 0)

    r = requests.post(
        f"{API}/admin/support/{sub_id}/approve",
        headers=_h(admin_token),
        json={"coins": 100, "reason": "iter17 approval"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    assert r.json().get("ok") is True

    # verify user premium + coins
    me_after = requests.get(f"{API}/auth/me", headers=_h(user_token["token"]), timeout=15).json()
    assert me_after.get("coins", 0) == coins_before + 100
    assert me_after.get("is_premium") is True

    # duplicate approve → 404 (idempotent CAS)
    r2 = requests.post(
        f"{API}/admin/support/{sub_id}/approve",
        headers=_h(admin_token),
        json={"coins": 100, "reason": "dup"},
        timeout=15,
    )
    assert r2.status_code == 404


def test_sbp_phone_regression_iter16(user_token):
    """Ensure the corrected +79780369381 is still what users see."""
    r = requests.get(f"{API}/coins/packages", headers=_h(user_token["token"]), timeout=15)
    assert r.status_code == 200
    txt = r.text
    assert "+79780369381" in txt, "corrected SBP phone missing from /packages"
    assert "+79783069381" not in txt, "old (wrong) SBP phone leaked into /packages"
