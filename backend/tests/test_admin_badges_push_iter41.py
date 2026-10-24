# Iter41: Admin unread badges (refunds/complaints), admin push device/test-self/direct push/history/announce, Russian result notifications
# Run: pytest tests/test_admin_badges_push_iter41.py -o addopts="" -v
import os, time, uuid, base64, io
import pytest, requests
from pymongo import MongoClient
from dotenv import dotenv_values

BASE_URL = (os.environ.get('REACT_APP_BACKEND_URL') or dotenv_values('/app/frontend/.env')['REACT_APP_BACKEND_URL']).rstrip('/')
API = f"{BASE_URL}/api"
BENV = dotenv_values('/app/backend/.env')
mdb = MongoClient(BENV['MONGO_URL'])[BENV['DB_NAME']]
AE, AP = BENV['ADMIN_EMAIL'], BENV['ADMIN_PASSWORD']


def _png():
    try:
        from PIL import Image
        b = io.BytesIO(); Image.new("RGB", (40, 40), (200, 30, 30)).save(b, "PNG")
        return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
    except Exception:
        return "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


IMG = _png()


def H(t):
    return {"Authorization": f"Bearer {t}"}


def register():
    email = f"test_iter41_{uuid.uuid4().hex[:8]}@lovreski.ru"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "password123", "name": "TEST_iter41",
                                                     "gender": "female", "dob": "1995-05-05"})
    assert r.status_code in (200, 201), r.text
    d = r.json()
    return email, d["token"], d["user"]["user_id"]


@pytest.fixture(scope="module")
def admin():
    mdb.login_attempts.delete_many({})
    r = requests.post(f"{API}/admin/login", json={"email": AE, "password": AP})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def user():
    return register()


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    ids = [u["user_id"] for u in mdb.users.find({"email": {"$regex": "^test_iter41_"}}, {"user_id": 1})]
    mdb.refund_requests.delete_many({"user_id": {"$in": ids}})
    mdb.reports.delete_many({"from_user": {"$in": ids}})
    mdb.receipt_submissions.delete_many({"user_id": {"$in": ids}})
    mdb.notifications.delete_many({"user_id": {"$in": ids}})
    mdb.push_log.delete_many({"title": {"$regex": "^TEST_iter41"}})
    mdb.notifications.delete_many({"message": {"$regex": "TEST_iter41"}})
    mdb.push_tokens.delete_many({"token": {"$regex": "^TEST_iter41"}})
    mdb.users.delete_many({"user_id": {"$in": ids}})
    mdb.login_attempts.delete_many({})


# ---- Badges: refunds ----
class TestRefundBadge:
    def test_refund_unread_flow(self, admin, user):
        _, tok, uid = user
        requests.post(f"{API}/admin/refund-requests/mark-read", headers=H(admin))
        assert requests.get(f"{API}/admin/refund-requests/unread-count", headers=H(admin)).json()["count"] == 0
        r = requests.post(f"{API}/support/refund", headers=H(tok), json={
            "full_name": "TEST_iter41 User", "email": "x@lovreski.ru", "receipt_data_url": IMG, "reason": "test"})
        assert r.status_code == 200, r.text
        rid = r.json()["refund_id"]
        doc = mdb.refund_requests.find_one({"refund_id": rid})
        assert doc["is_read"] is False
        c = requests.get(f"{API}/admin/refund-requests/unread-count", headers=H(admin)).json()["count"]
        assert c == 1
        m = requests.post(f"{API}/admin/refund-requests/mark-read", headers=H(admin))
        assert m.status_code == 200 and m.json()["marked"] >= 1
        assert requests.get(f"{API}/admin/refund-requests/unread-count", headers=H(admin)).json()["count"] == 0

    def test_refund_decide_russian_notification(self, admin, user):
        _, tok, uid = user
        r = requests.post(f"{API}/support/refund", headers=H(tok), json={
            "full_name": "TEST_iter41 User", "email": "x@lovreski.ru", "receipt_data_url": IMG, "reason": "test2"})
        assert r.status_code == 200, r.text
        rid = r.json()["refund_id"]
        d = requests.post(f"{API}/admin/refunds/{rid}/decide", headers=H(admin), json={"action": "approve", "reason": "ок"})
        assert d.status_code == 200, d.text
        notes = requests.get(f"{API}/notifications", headers=H(tok)).json()
        assert any("Возврат одобрен" in n["message"] for n in notes), notes


# ---- Badges: complaints ----
class TestComplaintBadge:
    def test_report_unread_flow(self, admin, user):
        _, tok, uid = user
        requests.post(f"{API}/admin/complaints/mark-read", headers=H(admin))
        assert requests.get(f"{API}/admin/complaints/unread-count", headers=H(admin)).json()["count"] == 0
        r = requests.post(f"{API}/report", headers=H(tok), json={"target_user_id": "u_nonexistent", "reason": "TEST_iter41 spam"})
        assert r.status_code == 200, r.text
        assert requests.get(f"{API}/admin/complaints/unread-count", headers=H(admin)).json()["count"] == 1
        m = requests.post(f"{API}/admin/complaints/mark-read", headers=H(admin))
        assert m.status_code == 200 and m.json()["marked"] >= 1
        assert requests.get(f"{API}/admin/complaints/unread-count", headers=H(admin)).json()["count"] == 0


# ---- Auth guard ----
class TestAuthGuard:
    @pytest.mark.parametrize("method,path,body", [
        ("get", "/admin/refund-requests/unread-count", None),
        ("post", "/admin/refund-requests/mark-read", None),
        ("get", "/admin/complaints/unread-count", None),
        ("post", "/admin/complaints/mark-read", None),
        ("post", "/admin/push/token", {"token": "TEST_iter41_tok_aaaaaaaaaaaaaaaa"}),
        ("delete", "/admin/push/token", {"token": "TEST_iter41_tok_aaaaaaaaaaaaaaaa"}),
        ("post", "/admin/push/test-self", None),
        ("post", "/admin/push/user/u_x", {"title": "TEST_iter41", "body": "b"}),
        ("get", "/admin/push/history", None),
        ("post", "/admin/push/announce", {"title": "TEST_iter41", "body": "b"}),
    ])
    def test_user_token_401(self, user, method, path, body):
        _, tok, _ = user
        r = getattr(requests, method)(f"{API}{path}", headers=H(tok), json=body)
        assert r.status_code == 401, (path, r.status_code, r.text)
        r2 = getattr(requests, method)(f"{API}{path}", json=body)
        assert r2.status_code == 401, (path, r2.status_code)


# ---- Admin push ----
class TestAdminPush:
    def test_admin_device_register_delete(self, admin):
        tk = "TEST_iter41_tok_" + uuid.uuid4().hex
        r = requests.post(f"{API}/admin/push/token", headers=H(admin), json={"token": tk})
        assert r.status_code == 200 and r.json()["devices"] >= 1
        cfg = requests.get(f"{API}/admin/push/config", headers=H(admin)).json()
        assert cfg["admin_devices"] >= 1
        d = requests.request("DELETE", f"{API}/admin/push/token", headers=H(admin), json={"token": tk})
        assert d.status_code == 200
        assert mdb.push_tokens.count_documents({"token": tk}) == 0

    def test_test_self(self, admin):
        r = requests.post(f"{API}/admin/push/test-self", headers=H(admin))
        assert r.status_code == 200, r.text
        assert r.json().get("sent") == 0 and r.json().get("reason") in ("not-configured", "no-tokens")

    def test_direct_push_user(self, admin, user):
        _, tok, uid = user
        title = f"TEST_iter41_direct_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/admin/push/user/{uid}", headers=H(admin), json={"title": title, "body": "Привет"})
        assert r.status_code == 200, r.text
        assert r.json()["in_app"] is True
        notes = requests.get(f"{API}/notifications", headers=H(tok)).json()
        assert any(title in n["message"] and n.get("kind") == "admin_message" for n in notes)
        hist = requests.get(f"{API}/admin/push/history", headers=H(admin)).json()
        assert hist[0]["title"] == title, hist[:2]
        assert hist[0]["kind"] == "direct" and hist[0]["target_user_id"] == uid
        assert hist[0]["status"] in ("not-configured", "no-tokens")
        assert "_id" not in hist[0]

    def test_direct_push_unknown_404(self, admin):
        r = requests.post(f"{API}/admin/push/user/u_doesnotexist_zz", headers=H(admin), json={"title": "TEST_iter41", "body": "b"})
        assert r.status_code == 404

    def test_direct_push_validation(self, admin, user):
        r = requests.post(f"{API}/admin/push/user/{user[2]}", headers=H(admin), json={"title": "", "body": "b"})
        assert r.status_code == 422

    def test_announce_log(self, admin):
        title = f"TEST_iter41_ann_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/admin/push/announce", headers=H(admin), json={"title": title, "body": "b"})
        assert r.status_code == 200, r.text
        time.sleep(3)
        doc = mdb.push_log.find_one({"title": title})
        assert doc and doc["kind"] == "announcement"
        assert doc["status"] == "sent", doc["status"]
        # cleanup mass in-app notifications
        mdb.notifications.delete_many({"message": {"$regex": title}})


# ---- Receipt approve/reject ----
class TestReceipts:
    def _submit(self, tok):
        r = requests.post(f"{API}/support/receipt", headers=H(tok), json={"receipt_data_url": IMG, "message": "TEST_iter41"})
        assert r.status_code == 200, r.text
        return r.json().get("submission_id")

    def test_pending_count_and_approve(self, admin):
        _, tok, uid = register()
        before = requests.get(f"{API}/admin/support/pending-count", headers=H(admin)).json()["count"]
        sid = self._submit(tok)
        assert requests.get(f"{API}/admin/support/pending-count", headers=H(admin)).json()["count"] == before + 1
        r = requests.post(f"{API}/admin/support/{sid}/approve", headers=H(admin), json={"coins": 10, "reason": "TEST"})
        assert r.status_code == 200, r.text
        notes = requests.get(f"{API}/notifications", headers=H(tok)).json()
        assert any("Платёж подтверждён" in n["message"] for n in notes)

    def test_reject(self, admin):
        _, tok, uid = register()
        sid = self._submit(tok)
        r = requests.post(f"{API}/admin/support/{sid}/reject", headers=H(admin), json={"reason": "TEST плохо"})
        assert r.status_code == 200, r.text
        notes = requests.get(f"{API}/notifications", headers=H(tok)).json()
        assert any("Чек отклонён" in n["message"] for n in notes)


# ---- Admin login still works with fire-and-forget alerts ----
class TestAdminLogin:
    def test_login_fail_and_success(self):
        mdb.login_attempts.delete_many({})
        r = requests.post(f"{API}/admin/login", json={"email": AE, "password": "wrong"})
        assert r.status_code == 401
        r = requests.post(f"{API}/admin/login", json={"email": AE, "password": AP})
        assert r.status_code == 200 and r.json().get("token")
        mdb.login_attempts.delete_many({})
