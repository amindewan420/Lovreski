# Iter40: Retest of security fixes — admin login XFF-spoof lockout, /auth/login lockout, no admin powers for admin@ user JWT
# Run serially: pytest tests/test_security_fixes_iter40.py -o addopts="" -v
import os, time, uuid
import pytest, requests
from pymongo import MongoClient
from dotenv import dotenv_values

BASE_URL = (os.environ.get('REACT_APP_BACKEND_URL') or dotenv_values('/app/frontend/.env')['REACT_APP_BACKEND_URL']).rstrip('/')
API = f"{BASE_URL}/api"
BENV = dotenv_values('/app/backend/.env')
mdb = MongoClient(BENV['MONGO_URL'])[BENV['DB_NAME']]
AE, AP = BENV['ADMIN_EMAIL'], BENV['ADMIN_PASSWORD']


def H(t):
    return {"Authorization": f"Bearer {t}"}


def ulogin(email, pw):
    return requests.post(f"{API}/auth/login", json={"email": email, "password": pw})


def register(prefix="TEST_iter40"):
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@lovreski.ru".lower()
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "password123", "name": "Tester",
                                                     "gender": "female", "dob": "1995-05-05"})
    assert r.status_code in (200, 201), r.text
    d = r.json()
    return email, d["token"], d["user"]["user_id"]


@pytest.fixture(autouse=True)
def reset_attempts():
    mdb.login_attempts.delete_many({})
    yield
    mdb.login_attempts.delete_many({})


@pytest.fixture(scope="module", autouse=True)
def cleanup_users():
    yield
    ids = [u["user_id"] for u in mdb.users.find({"email": {"$regex": "^test_iter40_"}}, {"user_id": 1})]
    mdb.messages.delete_many({"participants": {"$in": ids}})
    mdb.users.delete_many({"user_id": {"$in": ids}})


@pytest.fixture(scope="module")
def admin_user_token():
    r = ulogin(AE, AP)
    assert r.status_code == 200, r.text
    return r.json()["token"], r.json()["user"]["user_id"]


# ---- Fix 1: admin login lockout cannot be bypassed via X-Forwarded-For ----
class TestAdminXFF:
    def test_spoofed_xff_each_attempt_still_locks(self):
        for i in range(5):
            r = requests.post(f"{API}/admin/login", json={"email": AE, "password": f"bad{i}"},
                              headers={"X-Forwarded-For": f"10.{i}.{i}.{i}"})
            assert r.status_code == 401, (i, r.status_code)
        r = requests.post(f"{API}/admin/login", json={"email": AE, "password": AP},
                          headers={"X-Forwarded-For": "1.2.3.4"})
        assert r.status_code == 429, r.text

    def test_global_counter_recorded(self):
        for i in range(3):
            requests.post(f"{API}/admin/login", json={"email": AE, "password": f"bad{i}"},
                          headers={"X-Forwarded-For": f"172.16.{i}.1"})
        g = mdb.login_attempts.find_one({"key": "admin-global"})
        assert g and g["fails"] == 3
        ipkeys = [d["key"] for d in mdb.login_attempts.find({"key": {"$regex": "^admin-ip:"}})]
        assert len(ipkeys) == 1, f"spoofed XFF created separate IP buckets: {ipkeys}"
        assert not any(k.startswith("admin-ip:172.16.") for k in ipkeys)

    def test_global_lockout_at_20(self):
        # Simulate 19 global fails coming from other IPs, then one more → global lock
        mdb.login_attempts.update_one({"key": "admin-global"}, {"$set": {"key": "admin-global", "fails": 19, "locked_until": None}}, upsert=True)
        r = requests.post(f"{API}/admin/login", json={"email": AE, "password": "bad"})
        assert r.status_code == 401
        mdb.login_attempts.delete_many({"key": {"$regex": "^admin-ip:"}})  # only global lock remains
        r = requests.post(f"{API}/admin/login", json={"email": AE, "password": AP})
        assert r.status_code == 429, r.text

    def test_success_clears_and_returns_token(self):
        requests.post(f"{API}/admin/login", json={"email": AE, "password": "bad"})
        r = requests.post(f"{API}/admin/login", json={"email": AE, "password": AP})
        assert r.status_code == 200 and r.json()["success"] is True
        assert mdb.login_attempts.count_documents({"key": {"$regex": "^admin-"}}) == 0


# ---- Fix 2: /auth/login normal bcrypt + per-email lockout ----
class TestUserLoginLockout:
    def test_10_fails_then_429(self):
        email, _, _ = register()
        for i in range(10):
            r = ulogin(email, f"wrong{i}")
            assert r.status_code == 401, (i, r.status_code, r.text)
        r = ulogin(email, "password123")
        assert r.status_code == 429, r.text

    def test_success_clears_counter(self):
        email, _, _ = register()
        for i in range(9):
            assert ulogin(email, f"wrong{i}").status_code == 401
        assert ulogin(email, "password123").status_code == 200
        assert mdb.login_attempts.count_documents({"key": f"user:{email}"}) == 0
        for i in range(9):
            assert ulogin(email, f"wrong{i}").status_code == 401
        assert ulogin(email, "password123").status_code == 200

    def test_lockout_is_per_email(self):
        email, _, _ = register()
        for i in range(10):
            ulogin(email, "x")
        assert ulogin(email, "password123").status_code == 429
        assert ulogin("testuser1@lovreski.ru", "password123").status_code == 200

    def test_admin_email_wrong_pw_counts(self):
        r = ulogin(AE, "wrong")
        assert r.status_code == 401
        assert mdb.login_attempts.find_one({"key": f"user:{AE.lower()}"})["fails"] == 1

    @pytest.mark.parametrize("email", ["testuser1@lovreski.ru", "match_a@lovreski.ru", "match_b@lovreski.ru"])
    def test_regular_users_login(self, email):
        r = ulogin(email, "password123")
        assert r.status_code == 200 and r.json()["user"]["email"] == email


# ---- Fix 3: admin@ user JWT has no admin powers ----
class TestNoAdminPowersForUserJWT:
    def test_admin_routes_401(self, admin_user_token):
        t, _ = admin_user_token
        for p in ["/admin/verify-token", "/admin/stats", "/admin/users", "/admin/payments", "/admin/storage"]:
            assert requests.get(f"{API}{p}", headers=H(t)).status_code == 401, p

    def test_demo_seed_user_401_admin_200(self, admin_user_token):
        t, _ = admin_user_token
        assert requests.post(f"{API}/demo/seed", headers=H(t)).status_code == 401
        at = requests.post(f"{API}/admin/login", json={"email": AE, "password": AP}).json()["token"]
        r = requests.post(f"{API}/demo/seed", headers=H(at))
        assert r.status_code == 200, r.text

    def test_cannot_delete_others_message(self, admin_user_token):
        t, auid = admin_user_token
        m = mdb.messages.find_one({"participants": {"$nin": [auid]}, "deleted": {"$ne": True}}, {"_id": 0, "message_id": 1})
        assert m, "no foreign message to test"
        r = requests.delete(f"{API}/messages/{m['message_id']}?scope=everyone", headers=H(t))
        assert r.status_code == 403, r.text
        assert not mdb.messages.find_one({"message_id": m["message_id"]}).get("deleted")

    def test_cannot_bypass_1h_window(self, admin_user_token):
        t, auid = admin_user_token
        _, _, other = register()
        r = requests.post(f"{API}/chats/{other}/send", headers=H(t), json={"kind": "text", "text": "TEST_old"})
        assert r.status_code == 200, r.text
        mid = r.json().get("message_id") or r.json().get("message", {}).get("message_id")
        assert mid, r.text
        mdb.messages.update_one({"message_id": mid}, {"$set": {"created_at": "2020-01-01T00:00:00+00:00"}})
        r = requests.delete(f"{API}/messages/{mid}?scope=everyone", headers=H(t))
        assert r.status_code == 403, r.text

    def test_cannot_read_foreign_receipts(self, admin_user_token):
        t, auid = admin_user_token
        docs = list(mdb.s3_files.find({"kind": {"$in": ["support_receipt", "refund_receipt", "other"]},
                                       "owner_id": {"$ne": auid}}, {"_id": 1}).limit(3))
        assert docs
        for d in docs:
            fid = d["_id"]
            r1 = requests.get(f"{API}/files/{fid}/signed", headers=H(t))
            r2 = requests.get(f"{API}/files/{fid}", headers=H(t), allow_redirects=False)
            assert r1.status_code == 403, (fid, r1.status_code)
            assert r2.status_code == 403, (fid, r2.status_code)

    def test_admin_token_can_sign_receipts(self):
        at = requests.post(f"{API}/admin/login", json={"email": AE, "password": AP}).json()["token"]
        r = requests.get(f"{API}/admin/support/history", headers=H(at))
        assert r.status_code == 200
        txt = r.text
        assert "sig=" in txt or "/api/files/" not in txt, "receipt urls not signed"

    def test_paywall_applies(self, admin_user_token):
        t, auid = admin_user_token
        _, _, other = register()
        before = mdb.users.find_one({"user_id": auid})["coins"]
        for i in range(3):
            r = requests.post(f"{API}/chats/{other}/send", headers=H(t), json={"kind": "text", "text": f"TEST_{i}"})
            assert r.status_code == 200, r.text
        after = mdb.users.find_one({"user_id": auid})["coins"]
        assert after < before, f"3rd message was free for admin@ user (coins {before}->{after})"
