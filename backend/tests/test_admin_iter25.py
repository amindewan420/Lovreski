"""Iter 25 backend tests: admin coin-deduct, moderation (warn/ban7/deactivate),
legal docs CRUD, audit log, dashboard stats regression."""
import os, uuid, requests, pytest
from pathlib import Path

def _load_frontend_env():
    p = Path('/app/frontend/.env')
    if p.exists():
        for line in p.read_text().splitlines():
            if line.startswith('REACT_APP_BACKEND_URL='):
                return line.split('=', 1)[1].strip()
    return os.environ.get('REACT_APP_BACKEND_URL')

BASE_URL = (os.environ.get('REACT_APP_BACKEND_URL') or _load_frontend_env()).rstrip('/')
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@lovreski.ru"
ADMIN_PASS = "LovreskiAdmin2026!"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    return r


@pytest.fixture(scope="module")
def admin_token():
    r = _login(ADMIN_EMAIL, ADMIN_PASS)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_hdr(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


def _register(prefix="tst"):
    email = f"TEST_{prefix}_{uuid.uuid4().hex[:8]}@lovreski.ru"
    pw = "Passw0rd!"
    body = {"email": email, "password": pw, "name": "Тест", "gender": "male", "dob": "1998-05-15"}
    r = requests.post(f"{API}/auth/register", json=body, timeout=15)
    assert r.status_code in (200, 201), f"register failed: {r.status_code} {r.text}"
    j = r.json()
    return {"email": email, "password": pw, "token": j["token"], "user_id": j["user"]["user_id"]}


@pytest.fixture
def fresh_user():
    return _register()


@pytest.fixture(scope="module")
def user_token():
    r = _login("testuser1@lovreski.ru", "password123")
    if r.status_code != 200:
        u = _register("regularuser")
        return u["token"], u["user_id"]
    j = r.json()
    return j["token"], j["user"]["user_id"]


# ────────── Deduct coins ──────────
class TestDeductCoins:
    def test_deduct_success(self, admin_hdr, fresh_user):
        # add 20 coins first via admin
        r = requests.post(f"{API}/admin/users/add-coins", headers=admin_hdr,
                          json={"user_id": fresh_user["user_id"], "coins": 20, "reason": "seed"}, timeout=15)
        assert r.status_code == 200, r.text
        bal_before = r.json()["new_balance"]
        r = requests.post(f"{API}/admin/users/deduct-coins", headers=admin_hdr,
                          json={"user_id": fresh_user["user_id"], "coins": 5, "reason": "spam"}, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["ok"] is True
        assert j["deducted"] == 5
        assert j["new_balance"] == bal_before - 5

    def test_deduct_floors_at_zero(self, admin_hdr, fresh_user):
        r = requests.post(f"{API}/admin/users/deduct-coins", headers=admin_hdr,
                          json={"user_id": fresh_user["user_id"], "coins": 999, "reason": "over"}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["new_balance"] == 0

    def test_deduct_non_admin_forbidden(self, user_token, fresh_user):
        tok, _ = user_token
        r = requests.post(f"{API}/admin/users/deduct-coins",
                          headers={"Authorization": f"Bearer {tok}"},
                          json={"user_id": fresh_user["user_id"], "coins": 1, "reason": "x"}, timeout=15)
        assert r.status_code == 403

    def test_deduct_missing_reason_rejected(self, admin_hdr, fresh_user):
        r = requests.post(f"{API}/admin/users/deduct-coins", headers=admin_hdr,
                          json={"user_id": fresh_user["user_id"], "coins": 1, "reason": ""}, timeout=15)
        # Pydantic min_length=1 → 422; endpoint also raises 400 for whitespace-only. Accept 400 or 422.
        assert r.status_code in (400, 422), r.text

    def test_deduct_non_positive_rejected(self, admin_hdr, fresh_user):
        r = requests.post(f"{API}/admin/users/deduct-coins", headers=admin_hdr,
                          json={"user_id": fresh_user["user_id"], "coins": 0, "reason": "x"}, timeout=15)
        assert r.status_code in (400, 422), r.text


# ────────── Warn ──────────
class TestWarn:
    def test_warn_success(self, admin_hdr, fresh_user):
        r = requests.post(f"{API}/admin/users/{fresh_user['user_id']}/warn", headers=admin_hdr,
                          json={"reason": "тест"}, timeout=15)
        assert r.status_code == 200, r.text
        # verify audit contains warn
        aud = requests.get(f"{API}/admin/audit", headers=admin_hdr, timeout=15).json()
        assert any(a.get("action") == "warn" and a.get("target_user") == fresh_user["user_id"] for a in aud)

    def test_warn_forbidden_non_admin(self, user_token, fresh_user):
        tok, _ = user_token
        r = requests.post(f"{API}/admin/users/{fresh_user['user_id']}/warn",
                          headers={"Authorization": f"Bearer {tok}"}, json={"reason": "x"}, timeout=15)
        assert r.status_code == 403


# ────────── Ban7 ──────────
class TestBan7:
    def test_ban_and_login_blocked(self, admin_hdr, fresh_user):
        r = requests.post(f"{API}/admin/users/{fresh_user['user_id']}/ban7", headers=admin_hdr,
                          json={"reason": "spam", "days": 7}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("banned_until")
        # attempt login → 403 with Russian message
        lr = _login(fresh_user["email"], fresh_user["password"])
        assert lr.status_code == 403, lr.text
        assert "заблокирован" in lr.json().get("detail", "").lower() or "заблокирован" in lr.text.lower()


# ────────── Deactivate ──────────
class TestDeactivate:
    def test_deactivate_login_blocked_and_hidden(self, admin_hdr):
        u = _register("deact")
        r = requests.post(f"{API}/admin/users/{u['user_id']}/deactivate-permanent",
                          headers=admin_hdr, json={"reason": "abuse"}, timeout=15)
        assert r.status_code == 200, r.text
        lr = _login(u["email"], u["password"])
        assert lr.status_code == 403
        assert "деактивирован" in lr.text.lower()


# ────────── Audit list ──────────
class TestAudit:
    def test_audit_list_admin(self, admin_hdr):
        r = requests.get(f"{API}/admin/audit", headers=admin_hdr, timeout=15)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        # newest first
        if len(rows) >= 2:
            assert rows[0]["at"] >= rows[-1]["at"]

    def test_audit_forbidden_non_admin(self, user_token):
        tok, _ = user_token
        r = requests.get(f"{API}/admin/audit", headers={"Authorization": f"Bearer {tok}"}, timeout=15)
        assert r.status_code == 403


# ────────── Legal docs ──────────
SLUG = f"test-doc-{uuid.uuid4().hex[:6]}"


class TestLegal:
    def test_public_list_no_body(self):
        r = requests.get(f"{API}/legal", timeout=15)
        assert r.status_code == 200
        for d in r.json():
            assert "body" not in d

    def test_create_slug(self, admin_hdr):
        r = requests.post(f"{API}/admin/legal", headers=admin_hdr,
                          json={"slug": SLUG, "title": "Test Doc", "body": "content"}, timeout=15)
        assert r.status_code == 200, r.text

    def test_duplicate_slug_conflict(self, admin_hdr):
        r = requests.post(f"{API}/admin/legal", headers=admin_hdr,
                          json={"slug": SLUG, "title": "Dup", "body": "x"}, timeout=15)
        assert r.status_code == 409, r.text

    def test_slug_pattern_rejected(self, admin_hdr):
        r = requests.post(f"{API}/admin/legal", headers=admin_hdr,
                          json={"slug": "Bad Slug!", "title": "x", "body": "y"}, timeout=15)
        assert r.status_code in (400, 422), r.text

    def test_public_get_by_slug(self):
        r = requests.get(f"{API}/legal/{SLUG}", timeout=15)
        assert r.status_code == 200
        assert r.json()["body"] == "content"

    def test_unknown_slug_404(self):
        r = requests.get(f"{API}/legal/does-not-exist-xyz", timeout=15)
        assert r.status_code == 404

    def test_update(self, admin_hdr):
        r = requests.put(f"{API}/admin/legal/{SLUG}", headers=admin_hdr,
                         json={"slug": SLUG, "title": "Test Doc v2", "body": "updated"}, timeout=15)
        assert r.status_code == 200, r.text
        g = requests.get(f"{API}/legal/{SLUG}", timeout=15).json()
        assert g["title"] == "Test Doc v2"
        assert g["body"] == "updated"

    def test_delete(self, admin_hdr):
        r = requests.delete(f"{API}/admin/legal/{SLUG}", headers=admin_hdr, timeout=15)
        assert r.status_code == 200
        g = requests.get(f"{API}/legal/{SLUG}", timeout=15)
        assert g.status_code == 404

    def test_legal_forbidden_non_admin(self, user_token):
        tok, _ = user_token
        h = {"Authorization": f"Bearer {tok}"}
        r = requests.post(f"{API}/admin/legal", headers=h,
                         json={"slug": "x-y", "title": "t", "body": "b"}, timeout=15)
        assert r.status_code == 403
        r = requests.put(f"{API}/admin/legal/foo", headers=h,
                         json={"slug": "foo", "title": "t", "body": "b"}, timeout=15)
        assert r.status_code == 403
        r = requests.delete(f"{API}/admin/legal/foo", headers=h, timeout=15)
        assert r.status_code == 403


# ────────── Regression ──────────
class TestRegression:
    def test_stats_has_approved_month(self, admin_hdr):
        r = requests.get(f"{API}/admin/stats", headers=admin_hdr, timeout=15)
        assert r.status_code == 200
        assert "approved_month" in r.json()

    def test_payments_shape(self, admin_hdr):
        r = requests.get(f"{API}/admin/payments", headers=admin_hdr, timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_settings_update_audit(self, admin_hdr):
        r = requests.put(f"{API}/admin/settings", headers=admin_hdr,
                         json={"sbp_phone": "+79990000000"}, timeout=15)
        assert r.status_code == 200, r.text
        aud = requests.get(f"{API}/admin/audit", headers=admin_hdr, timeout=15).json()
        assert any(a.get("action") == "settings_update" for a in aud)
