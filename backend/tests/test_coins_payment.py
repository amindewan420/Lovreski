"""Backend tests for Lovreski coin/premium payment rebuild.
Covers packages, checkout (SBP link + QR, no phone leak), status polling with mocked
auto-confirmation (~8s), atomic crediting, rate limiting (5/hour), admin settings
(masked/reveal/update), webhook secret auth, non-admin 403.
"""
import os
import re
import time
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://lovreski-dating.preview.emergentagent.com').rstrip('/')
API = f"{BASE_URL}/api"
ADMIN_PHONE = "+79780369381"
ADMIN_EMAIL = "admin@lovreski.ru"
ADMIN_PASS = "LovreskiAdmin2026!"


def _register_user():
    ts = int(time.time() * 1000)
    email = f"premtest_{ts}@lovreski.ru"
    payload = {
        "email": email, "password": "password123", "name": "PremTester",
        "gender": "male", "dob": "1998-05-15",
    }
    r = requests.post(f"{API}/auth/register", json=payload, timeout=15)
    assert r.status_code in (200, 201), f"register failed: {r.status_code} {r.text}"
    return r.json()["token"], email


def _login_admin():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def user_token():
    tok, _ = _register_user()
    return tok


@pytest.fixture(scope="module")
def admin_token():
    return _login_admin()


# ────────── packages ──────────
def test_packages_no_phone_leak_and_popular_flag():
    r = requests.get(f"{API}/coins/packages", timeout=10)
    assert r.status_code == 200
    body = r.json()
    text = r.text
    assert ADMIN_PHONE not in text
    assert "sbp_phone" not in text.lower() or "sbp_phone_masked" in text.lower()  # not raw
    # phone patterns
    assert not re.search(r"\+7\d{10}", text), f"Raw phone number leaked: {text}"
    pkgs = body["packages"]
    p50 = next((p for p in pkgs if p["id"] == "p50"), None)
    assert p50 and p50.get("popular") is True
    for pid in ("p10", "p25", "p100"):
        p = next((p for p in pkgs if p["id"] == pid), None)
        assert p and p.get("popular") is False


# ────────── checkout ──────────
def test_checkout_returns_link_no_phone(user_token):
    r = requests.post(f"{API}/coins/checkout", json={"package_id": "p10"},
                      headers={"Authorization": f"Bearer {user_token}"}, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    for k in ("tx_id", "amount_rub", "coins", "sbp_link", "qr_png", "expires_in"):
        assert k in body, f"missing {k}"
    assert body["amount_rub"] == 300
    assert body["coins"] == 10
    assert body["sbp_link"].startswith("https://qr.nspk.ru/pay")
    # amount pre-encoded (300 RUB → sum=30000 kopecks)
    assert "sum=30000" in body["sbp_link"]
    assert body["qr_png"].startswith("data:image/png;base64,")
    # No phone anywhere
    assert ADMIN_PHONE not in r.text
    assert not re.search(r"\+7\d{10}", r.text), f"Phone leaked: {r.text}"


def test_status_pending_then_success_and_no_double_credit(user_token):
    # Initial balance
    b0 = requests.get(f"{API}/coins/balance", headers={"Authorization": f"Bearer {user_token}"}).json()
    coins_before = b0["coins"]

    r = requests.post(f"{API}/coins/checkout", json={"package_id": "p25"},
                      headers={"Authorization": f"Bearer {user_token}"}, timeout=15)
    assert r.status_code == 200, r.text
    tx_id = r.json()["tx_id"]

    # Immediately: pending
    s = requests.get(f"{API}/coins/status/{tx_id}", headers={"Authorization": f"Bearer {user_token}"}).json()
    assert s["transaction"]["status"] == "pending"

    # Wait for mocked auto-confirm (~8s)
    time.sleep(11)
    s2 = requests.get(f"{API}/coins/status/{tx_id}", headers={"Authorization": f"Bearer {user_token}"}).json()
    assert s2["transaction"]["status"] == "success", f"unexpected: {s2}"
    assert s2["coins"] == coins_before + 25

    # Hit status 3 more times → coins must not double
    for _ in range(3):
        s3 = requests.get(f"{API}/coins/status/{tx_id}", headers={"Authorization": f"Bearer {user_token}"}).json()
    assert s3["coins"] == coins_before + 25, "double credit detected"

    # Also assert no phone in status response
    assert ADMIN_PHONE not in requests.get(f"{API}/coins/status/{tx_id}",
                                           headers={"Authorization": f"Bearer {user_token}"}).text


def test_rate_limit_5_per_hour():
    tok, _ = _register_user()  # fresh user
    codes = []
    for i in range(6):
        r = requests.post(f"{API}/coins/checkout", json={"package_id": "p10"},
                          headers={"Authorization": f"Bearer {tok}"}, timeout=15)
        codes.append(r.status_code)
    assert codes[:5].count(200) == 5, f"first 5 should be 200: {codes}"
    assert codes[5] == 429, f"6th should be 429: {codes}"


# ────────── admin settings ──────────
def test_admin_settings_masked(admin_token):
    r = requests.get(f"{API}/admin/settings", headers={"Authorization": f"Bearer {admin_token}"}, timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "sbp_phone_masked" in body
    assert "***" in body["sbp_phone_masked"]
    assert "sbp_phone_last4" in body
    # Raw phone NOT in response
    assert not re.search(r"\+7\d{10}", r.text), f"Raw phone in masked response: {r.text}"


def test_admin_settings_reveal(admin_token):
    r = requests.get(f"{API}/admin/settings/reveal", headers={"Authorization": f"Bearer {admin_token}"}, timeout=10)
    assert r.status_code == 200
    phone = r.json().get("sbp_phone")
    assert phone and phone.startswith("+7")


def test_admin_settings_update_and_link_updates(admin_token, user_token):
    # Read original
    original = requests.get(f"{API}/admin/settings/reveal",
                            headers={"Authorization": f"Bearer {admin_token}"}).json()["sbp_phone"]
    new_phone = "+79111234567"
    try:
        r = requests.put(f"{API}/admin/settings", json={"sbp_phone": new_phone},
                         headers={"Authorization": f"Bearer {admin_token}"}, timeout=10)
        assert r.status_code == 200, r.text
        # Verify persisted
        rev = requests.get(f"{API}/admin/settings/reveal",
                           headers={"Authorization": f"Bearer {admin_token}"}).json()
        assert rev["sbp_phone"] == new_phone

        # Fresh user checkout — SBP link should reference new phone via ref token but plaintext NOT in response
        tok, _ = _register_user()
        c = requests.post(f"{API}/coins/checkout", json={"package_id": "p10"},
                          headers={"Authorization": f"Bearer {tok}"}).json()
        assert new_phone not in c.get("sbp_link", "") + str(c)
    finally:
        # restore
        requests.put(f"{API}/admin/settings", json={"sbp_phone": original},
                     headers={"Authorization": f"Bearer {admin_token}"})


def test_non_admin_settings_forbidden(user_token):
    r = requests.get(f"{API}/admin/settings", headers={"Authorization": f"Bearer {user_token}"}, timeout=10)
    assert r.status_code == 403, r.status_code


# ────────── webhook ──────────
def test_webhook_requires_secret():
    r = requests.post(f"{API}/coins/webhook",
                      json={"tx_id": "fake", "status": "success", "amount_rub": 300, "bank": "Sberbank"},
                      timeout=10)
    assert r.status_code == 401
