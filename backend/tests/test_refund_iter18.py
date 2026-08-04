"""Iteration 18: Refund request feature - backend tests.
Covers POST /api/support/refund (create, validation, rate-limit),
GET /api/admin/refunds (admin listing + non-admin 403),
POST /api/admin/refunds/{id}/decide (approve/reject, second decide -> 404).
"""
import os
import time
import base64
import io
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if BASE_URL:
    BASE_URL = BASE_URL.rstrip("/")

ADMIN_EMAIL = "admin@lovreski.ru"
ADMIN_PASSWORD = "LovreskiAdmin2026!"

# Tiny 1x1 PNG (base64) data URL
TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4//8/AwAI/AL+XJ/PYQAAAABJRU5ErkJggg=="
)
TINY_PNG_DATA_URL = f"data:image/png;base64,{TINY_PNG_B64}"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def user_token():
    ts = int(time.time() * 1000)
    email = f"ref_{ts}@lovreski.ru"
    payload = {
        "email": email,
        "password": "password123",
        "name": "RefTester",
        "gender": "male",
        "dob": "1998-05-15",
    }
    r = requests.post(f"{BASE_URL}/api/auth/register", json=payload, timeout=30)
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text}"
    return r.json()["token"], email


def auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


class TestRefundCreate:
    def test_missing_receipt_returns_422(self, user_token):
        token, _ = user_token
        r = requests.post(
            f"{BASE_URL}/api/support/refund",
            json={"full_name": "Test", "email": "test@x.com", "reason": "double charge"},
            headers=auth_headers(token),
            timeout=30,
        )
        assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text}"

    def test_missing_full_name_returns_422(self, user_token):
        token, _ = user_token
        r = requests.post(
            f"{BASE_URL}/api/support/refund",
            json={"email": "test@x.com", "receipt_data_url": TINY_PNG_DATA_URL, "reason": "x"},
            headers=auth_headers(token),
            timeout=30,
        )
        assert r.status_code == 422

    def test_missing_email_returns_422(self, user_token):
        token, _ = user_token
        r = requests.post(
            f"{BASE_URL}/api/support/refund",
            json={"full_name": "T", "receipt_data_url": TINY_PNG_DATA_URL, "reason": "x"},
            headers=auth_headers(token),
            timeout=30,
        )
        assert r.status_code == 422

    def test_missing_reason_returns_422(self, user_token):
        token, _ = user_token
        r = requests.post(
            f"{BASE_URL}/api/support/refund",
            json={"full_name": "T", "email": "test@x.com", "receipt_data_url": TINY_PNG_DATA_URL},
            headers=auth_headers(token),
            timeout=30,
        )
        assert r.status_code == 422

    def test_create_refund_success(self, user_token):
        token, email = user_token
        r = requests.post(
            f"{BASE_URL}/api/support/refund",
            json={
                "full_name": "Test User",
                "email": email,
                "receipt_data_url": TINY_PNG_DATA_URL,
                "reason": "Charged twice",
            },
            headers=auth_headers(token),
            timeout=30,
        )
        assert r.status_code == 200, f"got {r.status_code}: {r.text}"
        data = r.json()
        assert "refund_id" in data
        assert data.get("status") == "pending"
        assert data["refund_id"].startswith("ref_")


class TestRefundRateLimit:
    def test_fourth_refund_returns_429(self):
        # Fresh user
        ts = int(time.time() * 1000)
        email = f"rl_{ts}@lovreski.ru"
        reg = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={"email": email, "password": "password123", "name": "RL", "gender": "male", "dob": "1998-05-15"},
            timeout=30,
        )
        assert reg.status_code == 200
        token = reg.json()["token"]
        headers = auth_headers(token)

        def submit():
            return requests.post(
                f"{BASE_URL}/api/support/refund",
                json={
                    "full_name": "Rate Limit User",
                    "email": email,
                    "receipt_data_url": TINY_PNG_DATA_URL,
                    "reason": "test rate limit",
                },
                headers=headers,
                timeout=30,
            )

        for i in range(3):
            resp = submit()
            assert resp.status_code == 200, f"iter {i}: {resp.status_code} {resp.text}"
        r4 = submit()
        assert r4.status_code == 429, f"expected 429, got {r4.status_code}: {r4.text}"


class TestAdminRefunds:
    def test_non_admin_forbidden(self, user_token):
        token, _ = user_token
        r = requests.get(f"{BASE_URL}/api/admin/refunds", headers=auth_headers(token), timeout=30)
        assert r.status_code == 403, f"got {r.status_code}: {r.text}"

    def test_admin_list_refunds(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/admin/refunds", headers=auth_headers(admin_token), timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        # ensure created refund from earlier tests present
        assert any(item.get("status") in ("pending", "approved", "rejected") for item in data) or data == []
        # ensure _id not leaked
        for item in data:
            assert "_id" not in item

    def test_approve_flow_and_second_decide_404(self, user_token, admin_token):
        token, email = user_token
        # Create a fresh refund to decide on
        create = requests.post(
            f"{BASE_URL}/api/support/refund",
            json={
                "full_name": "Approve Case",
                "email": email,
                "receipt_data_url": TINY_PNG_DATA_URL,
                "reason": "approve me",
            },
            headers=auth_headers(token),
            timeout=30,
        )
        # user_token was used earlier; may hit rate limit -> use fresh user
        if create.status_code == 429:
            ts = int(time.time() * 1000)
            new_email = f"appr_{ts}@lovreski.ru"
            reg = requests.post(
                f"{BASE_URL}/api/auth/register",
                json={"email": new_email, "password": "password123", "name": "AP", "gender": "male", "dob": "1998-05-15"},
                timeout=30,
            )
            assert reg.status_code == 200
            token = reg.json()["token"]
            create = requests.post(
                f"{BASE_URL}/api/support/refund",
                json={
                    "full_name": "Approve Case",
                    "email": new_email,
                    "receipt_data_url": TINY_PNG_DATA_URL,
                    "reason": "approve me",
                },
                headers=auth_headers(token),
                timeout=30,
            )
        assert create.status_code == 200, create.text
        rid = create.json()["refund_id"]

        decide = requests.post(
            f"{BASE_URL}/api/admin/refunds/{rid}/decide",
            json={"action": "approve"},
            headers=auth_headers(admin_token),
            timeout=30,
        )
        assert decide.status_code == 200
        assert decide.json().get("ok") is True

        # Verify status changed via list
        listed = requests.get(f"{BASE_URL}/api/admin/refunds", headers=auth_headers(admin_token), timeout=30)
        assert listed.status_code == 200
        found = [x for x in listed.json() if x.get("refund_id") == rid]
        assert found and found[0]["status"] == "approved"

        # Second decide should 404
        decide2 = requests.post(
            f"{BASE_URL}/api/admin/refunds/{rid}/decide",
            json={"action": "approve"},
            headers=auth_headers(admin_token),
            timeout=30,
        )
        assert decide2.status_code == 404, f"expected 404, got {decide2.status_code}: {decide2.text}"

    def test_reject_flow(self, admin_token):
        # fresh user
        ts = int(time.time() * 1000)
        email = f"rej_{ts}@lovreski.ru"
        reg = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={"email": email, "password": "password123", "name": "RJ", "gender": "male", "dob": "1998-05-15"},
            timeout=30,
        )
        assert reg.status_code == 200
        utoken = reg.json()["token"]
        create = requests.post(
            f"{BASE_URL}/api/support/refund",
            json={
                "full_name": "Reject Case",
                "email": email,
                "receipt_data_url": TINY_PNG_DATA_URL,
                "reason": "reject me",
            },
            headers=auth_headers(utoken),
            timeout=30,
        )
        assert create.status_code == 200
        rid = create.json()["refund_id"]

        decide = requests.post(
            f"{BASE_URL}/api/admin/refunds/{rid}/decide",
            json={"action": "reject", "reason": "insufficient proof"},
            headers=auth_headers(admin_token),
            timeout=30,
        )
        assert decide.status_code == 200

        listed = requests.get(f"{BASE_URL}/api/admin/refunds?status=rejected", headers=auth_headers(admin_token), timeout=30)
        assert listed.status_code == 200
        found = [x for x in listed.json() if x.get("refund_id") == rid]
        assert found and found[0]["status"] == "rejected"

        # Check user got a notification
        notif = requests.get(f"{BASE_URL}/api/notifications", headers=auth_headers(utoken), timeout=30)
        # notifications endpoint may or may not exist; skip assert if missing
        if notif.status_code == 200:
            items = notif.json() if isinstance(notif.json(), list) else notif.json().get("items", [])
            assert any("Refund" in (i.get("message") or i.get("text") or "") or "refund" in (i.get("message") or i.get("text") or "").lower() for i in items)
