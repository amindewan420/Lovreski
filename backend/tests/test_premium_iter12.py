"""Iteration 12 — Premium coin packages, SBP phone/recipient/banks, checkout bank field."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    with open('/app/frontend/.env') as f:
        for line in f:
            if line.startswith('REACT_APP_BACKEND_URL='):
                BASE_URL = line.split('=', 1)[1].strip().rstrip('/')

ADMIN = ("admin@lovreski.ru", "LovreskiAdmin2026!")


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _register():
    ts = int(time.time() * 1000)
    body = {"email": f"iter12_{ts}@lovreski.ru", "password": "password123",
            "name": "Iter12", "gender": "male", "dob": "1998-05-15"}
    r = requests.post(f"{BASE_URL}/api/auth/register", json=body, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def user_token():
    return _register()


@pytest.fixture(scope="module")
def admin_token():
    return _login(*ADMIN)


class TestPackagesResponse:
    def test_four_packages_ids_and_prices(self):
        r = requests.get(f"{BASE_URL}/api/coins/packages", timeout=15)
        assert r.status_code == 200
        data = r.json()
        pkgs = data["packages"]
        assert len(pkgs) == 4, f"expected 4 packages, got {len(pkgs)}"
        by_id = {p["id"]: p for p in pkgs}
        for pid in ("p100", "p200", "p300", "p500"):
            assert pid in by_id, f"missing {pid}"
        assert by_id["p100"]["coins"] == 100 and by_id["p100"]["price"] == 500
        assert by_id["p200"]["coins"] == 200 and by_id["p200"]["price"] == 900
        assert by_id["p300"]["coins"] == 300 and by_id["p300"]["price"] == 1200
        assert by_id["p500"]["coins"] == 500 and by_id["p500"]["price"] == 1900
        assert by_id["p300"].get("popular") is True
        # Others should not be popular
        for pid in ("p100", "p200", "p500"):
            assert by_id[pid].get("popular") is not True

    def test_sbp_phone_recipient_and_banks(self):
        data = requests.get(f"{BASE_URL}/api/coins/packages", timeout=15).json()
        assert data.get("sbp_phone") == "+79780369381", f"got {data.get('sbp_phone')}"
        assert data.get("recipient_name") == "Al Amin Dewan"
        banks = data.get("banks") or []
        ids = {b["id"] for b in banks}
        assert "sberbank" in ids and "tbank" in ids
        # names present
        by_id = {b["id"]: b["name"] for b in banks}
        assert "Сбер" in by_id["sberbank"] or "Sber" in by_id["sberbank"]
        assert "Bank" in by_id["tbank"] or "Тинь" in by_id["tbank"]


class TestCheckoutBankField:
    def test_checkout_with_tbank_stores_bank(self, user_token):
        h = {"Authorization": f"Bearer {user_token}"}
        r = requests.post(f"{BASE_URL}/api/coins/checkout",
                          json={"package_id": "p200", "bank": "tbank"},
                          headers=h, timeout=15)
        assert r.status_code == 200, r.text
        tx_id = r.json()["tx_id"]
        assert r.json()["amount_rub"] == 900
        assert r.json()["coins"] == 200
        # Verify persistence via /coins/status (immediately, before 8s auto-confirm)
        s = requests.get(f"{BASE_URL}/api/coins/status/{tx_id}", headers=h, timeout=15)
        assert s.status_code == 200
        tx = s.json()["transaction"]
        assert tx.get("bank") == "tbank", f"expected bank=tbank, got {tx.get('bank')}"
        # No raw phone leaked in checkout response
        assert "+7978" not in r.text, "raw admin phone leaked in checkout response"

    def test_checkout_with_sberbank(self, user_token):
        h = {"Authorization": f"Bearer {user_token}"}
        r = requests.post(f"{BASE_URL}/api/coins/checkout",
                          json={"package_id": "p100", "bank": "sberbank"},
                          headers=h, timeout=15)
        assert r.status_code == 200, r.text

    def test_checkout_invalid_bank_returns_422(self, user_token):
        h = {"Authorization": f"Bearer {user_token}"}
        r = requests.post(f"{BASE_URL}/api/coins/checkout",
                          json={"package_id": "p100", "bank": "raiffeisen"},
                          headers=h, timeout=15)
        assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text}"

    def test_checkout_no_bank_still_ok(self, user_token):
        h = {"Authorization": f"Bearer {user_token}"}
        r = requests.post(f"{BASE_URL}/api/coins/checkout",
                          json={"package_id": "p300"},
                          headers=h, timeout=15)
        assert r.status_code == 200, r.text


class TestAdminSettingsRegression:
    def test_admin_settings_masked_view(self, admin_token):
        h = {"Authorization": f"Bearer {admin_token}"}
        r = requests.get(f"{BASE_URL}/api/admin/settings", headers=h, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "sbp_phone_masked" in d
        assert "sbp_phone_last4" in d
        assert d["sbp_phone_last4"] == "9381"
        assert "*" in d["sbp_phone_masked"]
