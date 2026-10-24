# Iter38: Admin-panel Firebase push config, announcements, push tokens, notif_push prefs, visits, chat location pins
import os, uuid, json
import pytest, requests
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient
from dotenv import dotenv_values

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL') or dotenv_values('/app/frontend/.env')['REACT_APP_BACKEND_URL']
BASE_URL = BASE_URL.rstrip('/')
API = f"{BASE_URL}/api"
BENV = dotenv_values('/app/backend/.env')
mdb = MongoClient(BENV['MONGO_URL'])[BENV['DB_NAME']]
FAKE_SA = open('/tmp/fake_sa.json').read()


def login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    d = r.json()
    return {"Authorization": f"Bearer {d['token']}"}, d.get('user', {})


def register():
    email = f"test_{uuid.uuid4().hex[:8]}@lovreski.ru"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "password123", "name": "TEST_U", "gender": "male", "dob": "1995-01-01"})
    assert r.status_code in (200, 201), r.text
    d = r.json()
    return {"Authorization": f"Bearer {d['token']}"}, d['user']['user_id']


@pytest.fixture(scope="module")
def admin():
    return login("admin@lovreski.ru", "LovreskiAdmin2026!")[0]


@pytest.fixture(scope="module")
def ua():
    h, u = login("match_a@lovreski.ru", "password123")
    me = requests.get(f"{API}/auth/me", headers=h).json()
    return h, me.get('user_id') or u.get('user_id')


@pytest.fixture(scope="module")
def ub():
    h, u = login("match_b@lovreski.ru", "password123")
    me = requests.get(f"{API}/auth/me", headers=h).json()
    return h, me.get('user_id') or u.get('user_id')


@pytest.fixture(scope="module", autouse=True)
def cleanup_firebase():
    backup = mdb.settings.find_one({"key": "firebase"})  # preserve real admin config if present
    mdb.settings.delete_one({"key": "firebase"})
    yield
    mdb.settings.delete_one({"key": "firebase"})
    if backup:
        mdb.settings.insert_one(backup)
    mdb.push_tokens.delete_many({"token": {"$regex": "^TEST_"}})


# ---- Push config (public/admin) ----
class TestPushConfig:
    def test_public_unconfigured(self):
        r = requests.get(f"{API}/push/config")
        assert r.status_code == 200 and r.json() == {"configured": False}

    def test_admin_config_forbidden_for_user(self, ua):
        assert requests.get(f"{API}/admin/push/config", headers=ua[0]).status_code == 403
        assert requests.put(f"{API}/admin/push/config", headers=ua[0], json={"api_key": "x"}).status_code == 403

    def test_admin_config_get(self, admin):
        r = requests.get(f"{API}/admin/push/config", headers=admin)
        assert r.status_code == 200
        d = r.json()
        for k in ("project_id", "api_key", "app_id", "sender_id", "vapid_key", "auth_domain", "has_service_account", "client_email", "ready", "devices", "subscribed_users"):
            assert k in d
        assert d["has_service_account"] is False and d["ready"] is False

    def test_invalid_json_rejected(self, admin):
        r = requests.put(f"{API}/admin/push/config", headers=admin, json={"service_account_json": "{not json"})
        assert r.status_code == 400 and "JSON" in r.json()["detail"]

    def test_wrong_type_rejected(self, admin):
        r = requests.put(f"{API}/admin/push/config", headers=admin, json={"service_account_json": json.dumps({"type": "user"})})
        assert r.status_code == 400 and "service_account" in r.json()["detail"]

    def test_missing_field_rejected(self, admin):
        r = requests.put(f"{API}/admin/push/config", headers=admin, json={"service_account_json": json.dumps({"type": "service_account", "project_id": "x"})})
        assert r.status_code == 400 and "отсутствует" in r.json()["detail"]

    def test_upload_fake_sa(self, admin):
        r = requests.put(f"{API}/admin/push/config", headers=admin, json={"service_account_json": FAKE_SA})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["has_service_account"] is True
        assert d["project_id"] == "lovreski-test"
        assert d["client_email"].startswith("firebase-adminsdk@")
        assert d["ready"] is False
        assert "private_key" not in json.dumps(d) and "service_account_enc" not in d
        assert requests.get(f"{API}/push/config").json() == {"configured": False}

    def test_save_web_fields_ready(self, admin):
        r = requests.put(f"{API}/admin/push/config", headers=admin, json={"api_key": "AIzaTEST", "app_id": "1:123:web:abc", "sender_id": "123", "vapid_key": "BTESTVAPID"})
        assert r.status_code == 200
        d = r.json()
        assert d["ready"] is True and d["api_key"] == "AIzaTEST" and d["has_service_account"] is True
        g = requests.get(f"{API}/admin/push/config", headers=admin).json()
        assert g["ready"] is True and "private_key" not in json.dumps(g)
        p = requests.get(f"{API}/push/config").json()
        assert p["configured"] is True and p["vapidKey"] == "BTESTVAPID" and p["projectId"] == "lovreski-test"
        assert p["authDomain"] == "lovreski-test.firebaseapp.com"

    def test_push_token_and_test(self, ua):
        h = ua[0]
        tok = "TEST_" + uuid.uuid4().hex * 2
        assert requests.post(f"{API}/push/token", headers=h, json={"token": tok}).status_code == 200
        assert mdb.push_tokens.find_one({"token": tok})["user_id"] == ua[1]
        r = requests.post(f"{API}/push/test", headers=h)
        assert r.status_code == 200
        d = r.json()
        assert d["sent"] == 0  # fake key -> graceful
        print("push/test with token:", d)
        r = requests.delete(f"{API}/push/token", headers=h, json={"token": tok})
        assert r.status_code == 200 and mdb.push_tokens.find_one({"token": tok}) is None
        r = requests.post(f"{API}/push/test", headers=h)
        assert r.status_code == 200 and r.json().get("reason") in ("no-tokens", "not-configured")

    def test_delete_sa(self, admin):
        r = requests.delete(f"{API}/admin/push/service-account", headers=admin)
        assert r.status_code == 200
        d = r.json()
        assert d["has_service_account"] is False and d["ready"] is False
        assert requests.get(f"{API}/push/config").json() == {"configured": False}

    def test_push_test_not_configured(self, ua):
        r = requests.post(f"{API}/push/test", headers=ua[0])
        assert r.status_code == 200 and r.json().get("reason") in ("no-tokens", "not-configured")


# ---- Announcements ----
class TestAnnounce:
    def test_forbidden(self, ua):
        assert requests.post(f"{API}/admin/push/announce", headers=ua[0], json={"title": "x", "body": "y"}).status_code == 403

    def test_announce(self, admin, ua):
        t = f"TEST_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/admin/push/announce", headers=admin, json={"title": t, "body": "Привет всем"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True and d["in_app"] > 0
        notes = requests.get(f"{API}/notifications", headers=ua[0]).json()
        assert any(t in n.get("message", "") and n.get("kind") == "announcement" for n in notes)
        mdb.notifications.delete_many({"message": {"$regex": t}})

    def test_announce_validation(self, admin):
        assert requests.post(f"{API}/admin/push/announce", headers=admin, json={"title": "", "body": "y"}).status_code == 422


# ---- Profile prefs + visits + like ----
class TestPrefsVisits:
    def test_notif_push_persist(self, ua):
        h = ua[0]
        prefs = {"messages": True, "likes": False, "matches": True, "visits": False, "announcements": True}
        r = requests.put(f"{API}/profile", headers=h, json={"notif_push": prefs})
        assert r.status_code == 200, r.text
        me = requests.get(f"{API}/auth/me", headers=h).json()
        assert me.get("notif_push") == prefs, me.get("notif_push")
        requests.put(f"{API}/profile", headers=h, json={"notif_push": {k: True for k in prefs}})

    def test_visit_recorded(self, ua, ub):
        r = requests.get(f"{API}/profile/{ub[1]}", headers=ua[0])
        assert r.status_code == 200
        v = mdb.profile_visits.find_one({"viewer": ua[1], "target": ub[1]})
        assert v is not None and v.get("count", 0) >= 1

    def test_like_works(self):
        h1, u1 = register()
        h2, u2 = register()
        r = requests.post(f"{API}/like/{u2}", headers=h1)
        assert r.status_code == 200, r.text
        r = requests.post(f"{API}/like/{u1}", headers=h2)
        assert r.status_code == 200, r.text
        print("mutual like:", r.json())


# ---- Chat location pins ----
class TestLocation:
    def test_send_text_regression(self, ua, ub):
        r = requests.post(f"{API}/chats/{ub[1]}/send", headers=ua[0], json={"kind": "text", "text": "TEST_hi"})
        assert r.status_code in (200, 402), r.text

    def test_location_requires_coords(self, ua, ub):
        r = requests.post(f"{API}/chats/{ub[1]}/send", headers=ua[0], json={"kind": "location"})
        assert r.status_code == 400

    def test_location_send_and_expire(self):
        h1, u1 = register()
        h2, u2 = register()
        r = requests.post(f"{API}/chats/{u2}/send", headers=h1, json={"kind": "location", "lat": 55.75, "lng": 37.61, "place": "Кафе TEST"})
        assert r.status_code == 200, r.text
        m = r.json()
        mid = m["message_id"]
        assert m["location"] == {"lat": 55.75, "lng": 37.61, "place": "Кафе TEST"}
        exp = datetime.fromisoformat(m["location_expires_at"].replace("Z", "+00:00"))
        assert timedelta(hours=23, minutes=55) < exp - datetime.now(timezone.utc) <= timedelta(hours=24, minutes=1)
        msgs = requests.get(f"{API}/chats/{u1}/messages", headers=h2).json()
        lm = [x for x in msgs if x["message_id"] == mid][0]
        assert lm["location"]["lat"] == 55.75 and not lm.get("location_expired")
        # expire via DB
        mdb.messages.update_one({"message_id": mid}, {"$set": {"location_expires_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()}})
        msgs = requests.get(f"{API}/chats/{u1}/messages", headers=h2).json()
        lm = [x for x in msgs if x["message_id"] == mid][0]
        assert lm["location"] is None and lm["location_expired"] is True
        # chat list
        chats = requests.get(f"{API}/chats", headers=h2).json()
        c = [c for c in chats if c["user"]["user_id"] == u1][0]
        print("chat list last_message location:", c["last_message"].get("location"), c["last_message"].get("location_expired"))

    def test_block_expires_pins(self):
        h1, u1 = register()
        h2, u2 = register()
        r = requests.post(f"{API}/chats/{u2}/send", headers=h1, json={"kind": "location", "lat": 59.93, "lng": 30.33})
        assert r.status_code == 200
        mid = r.json()["message_id"]
        assert requests.post(f"{API}/block/{u1}", headers=h2).status_code == 200
        msgs = requests.get(f"{API}/chats/{u2}/messages", headers=h1).json()
        lm = [x for x in msgs if x["message_id"] == mid][0]
        assert lm["location"] is None and lm["location_expired"] is True
