# Iter39: Separate Admin Panel auth — /api/admin/login, verify-token, logout, rate limit, token isolation
import os, time, uuid
import jwt as pyjwt
import pytest, requests
from pymongo import MongoClient
from dotenv import dotenv_values

BASE_URL = (os.environ.get('REACT_APP_BACKEND_URL') or dotenv_values('/app/frontend/.env')['REACT_APP_BACKEND_URL']).rstrip('/')
API = f"{BASE_URL}/api"
BENV = dotenv_values('/app/backend/.env')
mdb = MongoClient(BENV['MONGO_URL'])[BENV['DB_NAME']]
AE, AP = BENV['ADMIN_EMAIL'], BENV['ADMIN_PASSWORD']


def admin_login():
    r = requests.post(f"{API}/admin/login", json={"email": AE, "password": AP})
    assert r.status_code == 200, r.text
    return r.json()


def H(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(autouse=True)
def reset_attempts():
    mdb.login_attempts.delete_many({})
    yield
    mdb.login_attempts.delete_many({})


@pytest.fixture(scope="module")
def atok():
    return admin_login()["token"]


def user_token(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return r.json()["token"]


# ---- Login ----
class TestAdminLogin:
    def test_login_success(self):
        d = admin_login()
        assert d["success"] is True and isinstance(d["token"], str) and len(d["token"]) > 20

    def test_login_email_case_insensitive(self):
        r = requests.post(f"{API}/admin/login", json={"email": AE.upper(), "password": AP})
        assert r.status_code == 200

    def test_wrong_password_401_delay(self):
        t = time.time()
        r = requests.post(f"{API}/admin/login", json={"email": AE, "password": "wrong"})
        assert r.status_code == 401 and r.json()["detail"] == "Invalid email or password"
        assert time.time() - t >= 0.9

    def test_wrong_email_401(self):
        r = requests.post(f"{API}/admin/login", json={"email": "x@lovreski.ru", "password": AP})
        assert r.status_code == 401 and r.json()["detail"] == "Invalid email or password"

    def test_empty_body_422(self):
        assert requests.post(f"{API}/admin/login", json={"email": "", "password": ""}).status_code == 422

    def test_rate_limit_lockout(self):
        for i in range(5):
            r = requests.post(f"{API}/admin/login", json={"email": AE, "password": f"bad{i}"})
            assert r.status_code == 401
        r = requests.post(f"{API}/admin/login", json={"email": AE, "password": AP})
        assert r.status_code == 429, r.text
        assert "Too many" in r.json()["detail"]

    def test_rate_limit_xff_spoof(self):
        """Security: can a spoofed X-Forwarded-For bypass the lockout?"""
        for i in range(5):
            requests.post(f"{API}/admin/login", json={"email": AE, "password": f"bad{i}"})
        r = requests.post(f"{API}/admin/login", json={"email": AE, "password": AP},
                          headers={"X-Forwarded-For": f"10.9.{uuid.uuid4().int % 250}.7"})
        print("XFF spoof status after lockout:", r.status_code)
        assert r.status_code == 429, "Lockout bypassed via spoofed X-Forwarded-For"


# ---- Token verification / isolation ----
class TestAdminToken:
    def test_verify_valid(self, atok):
        r = requests.get(f"{API}/admin/verify-token", headers=H(atok))
        assert r.status_code == 200 and r.json()["valid"] is True

    def test_no_exp_claim(self, atok):
        p = pyjwt.decode(atok, options={"verify_signature": False})
        assert "exp" not in p and p["type"] == "admin"

    def test_verify_missing_garbage(self):
        assert requests.get(f"{API}/admin/verify-token").status_code == 401
        assert requests.get(f"{API}/admin/verify-token", headers=H("garbage")).status_code == 401

    def test_forged_token_without_session(self, atok):
        p = pyjwt.decode(atok, options={"verify_signature": False})
        p["jti"] = uuid.uuid4().hex
        forged = pyjwt.encode(p, BENV['JWT_SECRET'], algorithm="HS256")
        assert requests.get(f"{API}/admin/verify-token", headers=H(forged)).status_code == 401

    @pytest.mark.parametrize("email,pw", [("admin@lovreski.ru", "LovreskiAdmin2026!"), ("testuser1@lovreski.ru", "password123")])
    def test_user_jwt_rejected_on_admin(self, email, pw):
        t = user_token(email, pw)
        for path in ["/admin/verify-token", "/admin/stats", "/admin/push/config", "/admin/users", "/admin/settings"]:
            r = requests.get(f"{API}{path}", headers=H(t))
            assert r.status_code == 401, f"{email} {path} -> {r.status_code}"

    def test_admin_token_rejected_on_user_endpoint(self, atok):
        assert requests.get(f"{API}/auth/me", headers=H(atok)).status_code == 401

    @pytest.mark.parametrize("path", ["/admin/stats", "/admin/payments", "/admin/users", "/admin/settings",
                                      "/admin/support/pending", "/admin/support/history", "/admin/support/pending-count",
                                      "/admin/push/config", "/admin/legal", "/admin/storage", "/admin/storage/cleanup-log",
                                      "/admin/refunds", "/admin/reports", "/admin/audit"])
    def test_admin_routes_work(self, atok, path):
        r = requests.get(f"{API}{path}", headers=H(atok))
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"

    def test_admin_routes_require_token(self):
        for path in ["/admin/stats", "/admin/users", "/admin/storage", "/admin/legal"]:
            assert requests.get(f"{API}{path}").status_code == 401, path


# ---- Logout ----
class TestAdminLogout:
    def test_logout_revokes(self):
        t = admin_login()["token"]
        assert requests.get(f"{API}/admin/verify-token", headers=H(t)).status_code == 200
        r = requests.post(f"{API}/admin/logout", headers=H(t))
        assert r.status_code == 200 and r.json()["success"] is True
        assert requests.get(f"{API}/admin/verify-token", headers=H(t)).status_code == 401
        assert requests.get(f"{API}/admin/stats", headers=H(t)).status_code == 401

    def test_other_sessions_survive_logout(self, atok):
        t2 = admin_login()["token"]
        requests.post(f"{API}/admin/logout", headers=H(t2))
        assert requests.get(f"{API}/admin/verify-token", headers=H(atok)).status_code == 200
