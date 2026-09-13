"""Tests for FCM Web Push scaffold (iteration 32).

Firebase creds are intentionally empty; the module must no-op safely.
Covers: /api/push/status, /api/push/token (POST+DELETE), /api/push/test,
and regressions on chat send, like (match), and receipt submission.
"""
import os
import base64
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://lovreski-dating.preview.emergentagent.com").rstrip("/")

ADMIN_EMAIL = "admin@lovreski.ru"
ADMIN_PASS = "LovreskiAdmin2026!"
USER1_EMAIL = "testuser1@lovreski.ru"
USER1_PASS = "password123"


def _login_or_register(email, password, name="Тестер", gender="male", dob="1998-05-15"):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    if r.status_code == 200:
        return r.json()["token"], r.json().get("user", {}).get("user_id")
    r = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": password, "name": name, "gender": gender, "dob": dob},
        timeout=15,
    )
    assert r.status_code in (200, 201), f"register failed: {r.status_code} {r.text}"
    j = r.json()
    return j["token"], j.get("user", {}).get("user_id")


@pytest.fixture(scope="module")
def user1():
    tok, uid = _login_or_register(USER1_EMAIL, USER1_PASS)
    return {"token": tok, "user_id": uid, "headers": {"Authorization": f"Bearer {tok}"}}


@pytest.fixture(scope="module")
def user2():
    email = f"testuser2@lovreski.ru"
    tok, uid = _login_or_register(email, "password123", name="Тестер2", gender="female")
    return {"token": tok, "user_id": uid, "headers": {"Authorization": f"Bearer {tok}"}}


@pytest.fixture(scope="module")
def admin():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.text}"
    tok = r.json()["token"]
    return {"token": tok, "headers": {"Authorization": f"Bearer {tok}"}}


# ─── Health ─────────────────────────────────────────────────────────────
def test_health():
    r = requests.get(f"{BASE_URL}/api/health", timeout=10)
    assert r.status_code == 200


# ─── Push status (unconfigured) ─────────────────────────────────────────
def test_push_status_unconfigured(user1):
    r = requests.get(f"{BASE_URL}/api/push/status", headers=user1["headers"], timeout=10)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("configured") is False
    assert j.get("vapid_public_key", "") == ""
    assert "token_count" in j
    assert isinstance(j["token_count"], int)


def test_push_status_requires_auth():
    r = requests.get(f"{BASE_URL}/api/push/status", timeout=10)
    assert r.status_code in (401, 403)


# ─── Token registration ─────────────────────────────────────────────────
DUMMY_TOKEN = "dummy_test_token_abcdef12345678901234"


def test_push_token_post_and_upsert(user1):
    # get baseline token_count
    r0 = requests.get(f"{BASE_URL}/api/push/status", headers=user1["headers"], timeout=10)
    base_count = r0.json().get("token_count", 0)

    # First POST
    r = requests.post(
        f"{BASE_URL}/api/push/token",
        headers=user1["headers"],
        json={"token": DUMMY_TOKEN, "platform": "web"},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    assert r.json().get("ok") is True

    r1 = requests.get(f"{BASE_URL}/api/push/status", headers=user1["headers"], timeout=10)
    c1 = r1.json().get("token_count", 0)
    assert c1 >= 1

    # Second POST with same token → upsert (no duplicate)
    r2 = requests.post(
        f"{BASE_URL}/api/push/token",
        headers=user1["headers"],
        json={"token": DUMMY_TOKEN, "platform": "web"},
        timeout=10,
    )
    assert r2.status_code == 200
    r3 = requests.get(f"{BASE_URL}/api/push/status", headers=user1["headers"], timeout=10)
    c2 = r3.json().get("token_count", 0)
    assert c2 == c1, f"expected upsert, count changed {c1}->{c2}"


def test_push_token_delete(user1):
    # ensure exists
    requests.post(f"{BASE_URL}/api/push/token", headers=user1["headers"],
                  json={"token": DUMMY_TOKEN, "platform": "web"}, timeout=10)
    r_before = requests.get(f"{BASE_URL}/api/push/status", headers=user1["headers"], timeout=10)
    before = r_before.json().get("token_count", 0)

    r = requests.delete(
        f"{BASE_URL}/api/push/token",
        headers=user1["headers"],
        json={"token": DUMMY_TOKEN},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    assert r.json().get("ok") is True

    r_after = requests.get(f"{BASE_URL}/api/push/status", headers=user1["headers"], timeout=10)
    after = r_after.json().get("token_count", 0)
    assert after == before - 1, f"count did not decrement: {before}->{after}"


# ─── Test push in unconfigured state ────────────────────────────────────
def test_push_test_not_configured(user1):
    r = requests.post(f"{BASE_URL}/api/push/test", headers=user1["headers"], timeout=10)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("sent") == 0
    assert j.get("reason") == "not-configured"


# ─── Regressions: chat send, like/match, receipt ────────────────────────
def test_chat_send_regression(user1, user2):
    payload = {"text": "hello from push test"}
    r = requests.post(
        f"{BASE_URL}/api/chats/{user2['user_id']}/send",
        headers=user1["headers"], json=payload, timeout=15,
    )
    assert r.status_code in (200, 201), f"chat send failed: {r.status_code} {r.text}"
    j = r.json()
    # response should contain a message-like object; don't over-assert schema
    assert isinstance(j, dict)


def test_like_and_match_regression(user1, user2):
    # user1 likes user2
    r1 = requests.post(f"{BASE_URL}/api/like/{user2['user_id']}", headers=user1["headers"], timeout=15)
    assert r1.status_code in (200, 201), r1.text
    # user2 likes user1 back → mutual match
    r2 = requests.post(f"{BASE_URL}/api/like/{user1['user_id']}", headers=user2["headers"], timeout=15)
    assert r2.status_code in (200, 201), r2.text
    # response should indicate match=True or contain match_id (best-effort)
    j = r2.json()
    assert isinstance(j, dict)


def test_receipt_submission_regression(user1):
    # 1x1 transparent PNG
    tiny_png = base64.b64encode(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
            "890000000d49444154789c6360000000000200015e9e9d4a0000000049454e44ae426082"
        )
    ).decode()
    data_url = f"data:image/png;base64,{tiny_png}"
    payload = {"amount": 599, "plan": "1m", "receipt_data_url": data_url}
    r = requests.post(f"{BASE_URL}/api/support/receipt", headers=user1["headers"], json=payload, timeout=20)
    assert r.status_code in (200, 201), f"receipt failed: {r.status_code} {r.text}"
    j = r.json()
    assert "submission_id" in j or "id" in j
    assert j.get("status", "pending") == "pending"
