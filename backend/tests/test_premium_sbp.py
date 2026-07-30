"""Tests for the Lovreski Premium / SBP purchase flow (iteration 6)."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    # Fallback to reading frontend/.env
    try:
        with open('/app/frontend/.env') as f:
            for line in f:
                if line.startswith('REACT_APP_BACKEND_URL='):
                    BASE_URL = line.split('=', 1)[1].strip().rstrip('/')
                    break
    except Exception:
        pass

ADMIN_EMAIL = "admin@lovreski.ru"
ADMIN_PASSWORD = "LovreskiAdmin2026!"


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed {r.status_code} {r.text}"
    return r.json()["token"]


def _register_user():
    ts = int(time.time() * 1000)
    email = f"premtest_{ts}@lovreski.ru"
    body = {
        "email": email,
        "password": "password123",
        "name": "Prem Tester",
        "gender": "male",
        "dob": "1998-05-15",
    }
    r = requests.post(f"{BASE_URL}/api/auth/register", json=body, timeout=15)
    assert r.status_code == 200, f"register failed {r.status_code} {r.text}"
    return email, r.json()["token"]


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def user_creds():
    email, token = _register_user()
    return {"email": email, "token": token}


# ─── /coins/packages returns configured phone + Sberbank ─────────────────────
class TestPackages:
    def test_packages_shape_and_phone(self):
        r = requests.get(f"{BASE_URL}/api/coins/packages", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "packages" in data and isinstance(data["packages"], list) and len(data["packages"]) > 0
        assert data.get("bank") == "Sberbank"
        # Either env value or admin override; must be a non-empty string starting with +7
        assert isinstance(data.get("sbp_phone"), str) and data["sbp_phone"].startswith("+7")


# ─── /coins/purchase: insufficient balance is blocked ───────────────────────
class TestPurchase:
    def test_purchase_insufficient_balance_returns_402(self, user_creds):
        headers = {"Authorization": f"Bearer {user_creds['token']}"}
        pkgs = requests.get(f"{BASE_URL}/api/coins/packages", timeout=15).json()["packages"]
        pkg = pkgs[0]
        body = {"package_id": pkg["id"], "phone": "+79001112233", "sbp_balance": 1.0}
        r = requests.post(f"{BASE_URL}/api/coins/purchase", json=body, headers=headers, timeout=15)
        assert r.status_code == 402, f"expected 402, got {r.status_code}: {r.text}"
        detail = r.json().get("detail", "")
        assert "Insufficient Balance" in detail, f"detail missing message: {detail}"

    def test_purchase_sufficient_balance_succeeds(self, user_creds):
        headers = {"Authorization": f"Bearer {user_creds['token']}"}
        pkgs = requests.get(f"{BASE_URL}/api/coins/packages", timeout=15).json()["packages"]
        pkg = pkgs[0]
        body = {"package_id": pkg["id"], "phone": "+79001112233", "sbp_balance": pkg["price"] + 5000}
        r = requests.post(f"{BASE_URL}/api/coins/purchase", json=body, headers=headers, timeout=15)
        assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text}"
        tx = r.json()
        assert tx["status"] == "pending"
        assert tx["payment_method"] == "SBP (Sberbank)"
        assert tx["amount_rub"] == pkg["price"]
        assert "tx_id" in tx

    def test_purchase_without_balance_field_succeeds(self, user_creds):
        headers = {"Authorization": f"Bearer {user_creds['token']}"}
        pkgs = requests.get(f"{BASE_URL}/api/coins/packages", timeout=15).json()["packages"]
        pkg = pkgs[0]
        body = {"package_id": pkg["id"], "phone": "+79001112233"}
        r = requests.post(f"{BASE_URL}/api/coins/purchase", json=body, headers=headers, timeout=15)
        assert r.status_code == 200
        assert r.json()["status"] == "pending"


# ─── admin settings override ─────────────────────────────────────────────────
class TestAdminSettings:
    def test_admin_can_override_sbp_phone(self, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        new_phone = "+79001112233"
        # Save current value first, restore in teardown
        cur = requests.get(f"{BASE_URL}/api/admin/settings", headers=headers, timeout=15).json()
        orig_phone = cur.get("sbp_phone")
        try:
            r = requests.put(f"{BASE_URL}/api/admin/settings", json={"sbp_phone": new_phone}, headers=headers, timeout=15)
            assert r.status_code == 200
            pkgs = requests.get(f"{BASE_URL}/api/coins/packages", timeout=15).json()
            assert pkgs["sbp_phone"] == new_phone, f"expected override to win: {pkgs['sbp_phone']}"
        finally:
            # restore
            restore = orig_phone if orig_phone else "+79780369381"
            requests.put(f"{BASE_URL}/api/admin/settings", json={"sbp_phone": restore}, headers=headers, timeout=15)

    def test_default_sbp_phone_after_restore(self):
        # After the previous test restores, the packages endpoint should return +79780369381
        pkgs = requests.get(f"{BASE_URL}/api/coins/packages", timeout=15).json()
        assert pkgs["sbp_phone"] == "+79780369381", f"expected default env phone, got {pkgs['sbp_phone']}"


# ─── admin approval flips is_premium and increments coins ────────────────────
class TestApprovalFlow:
    def test_end_to_end_approval(self, admin_token):
        # fresh user
        email, token = _register_user()
        u_headers = {"Authorization": f"Bearer {token}"}
        a_headers = {"Authorization": f"Bearer {admin_token}"}

        # balance before
        bal_before = requests.get(f"{BASE_URL}/api/coins/balance", headers=u_headers, timeout=15).json()
        assert bal_before.get("is_premium") is False

        pkgs = requests.get(f"{BASE_URL}/api/coins/packages", timeout=15).json()["packages"]
        pkg = pkgs[0]
        pr = requests.post(
            f"{BASE_URL}/api/coins/purchase",
            json={"package_id": pkg["id"], "phone": "+79001112233", "sbp_balance": pkg["price"] + 1000},
            headers=u_headers, timeout=15,
        )
        assert pr.status_code == 200
        tx_id = pr.json()["tx_id"]

        # admin approves
        ar = requests.post(
            f"{BASE_URL}/api/admin/payments/{tx_id}",
            json={"action": "approve"},
            headers=a_headers, timeout=15,
        )
        assert ar.status_code == 200, ar.text

        # user balance should reflect
        bal_after = requests.get(f"{BASE_URL}/api/coins/balance", headers=u_headers, timeout=15).json()
        assert bal_after.get("is_premium") is True, f"is_premium not flipped: {bal_after}"
        assert bal_after.get("coins", 0) >= pkg["coins"], f"coins not incremented: {bal_after}"

        # tx list should show approved
        txs = requests.get(f"{BASE_URL}/api/coins/transactions", headers=u_headers, timeout=15).json()
        target = next((t for t in txs if t["tx_id"] == tx_id), None)
        assert target and target["status"] == "approved"
        assert target.get("payment_method") == "SBP (Sberbank)"

    def test_reject_flow_sets_reason(self, admin_token):
        email, token = _register_user()
        u_headers = {"Authorization": f"Bearer {token}"}
        a_headers = {"Authorization": f"Bearer {admin_token}"}
        pkgs = requests.get(f"{BASE_URL}/api/coins/packages", timeout=15).json()["packages"]
        pkg = pkgs[0]
        pr = requests.post(
            f"{BASE_URL}/api/coins/purchase",
            json={"package_id": pkg["id"], "phone": "+79001112233"},
            headers=u_headers, timeout=15,
        )
        tx_id = pr.json()["tx_id"]
        rej = requests.post(
            f"{BASE_URL}/api/admin/payments/{tx_id}",
            json={"action": "reject", "reason": "Test reject reason"},
            headers=a_headers, timeout=15,
        )
        assert rej.status_code == 200
        txs = requests.get(f"{BASE_URL}/api/coins/transactions", headers=u_headers, timeout=15).json()
        target = next((t for t in txs if t["tx_id"] == tx_id), None)
        assert target["status"] == "rejected"
        assert target.get("reject_reason") == "Test reject reason"
