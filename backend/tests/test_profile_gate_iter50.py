# Profile-completion gate (iter50): like + first message require photos/goal/relationship/kids/smoking/alcohol
import os
import uuid
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
REQUIRED = ["photos", "goal", "relationship", "kids", "smoking", "alcohol"]
COMPLETE = {"photos": ["https://example.com/TEST_p.jpg"], "goal": "relationship", "relationship": "single",
            "kids": "no", "smoking": "no", "alcohol": "no"}

CREATED = []


def _register(gender):
    email = f"TEST_gate_{uuid.uuid4().hex[:8]}@lovreski.ru".lower()
    r = requests.post(f"{BASE_URL}/api/auth/register", json={
        "email": email, "password": "password123", "name": "TEST_Gate", "gender": gender, "dob": "1995-05-05"})
    assert r.status_code == 200, r.text
    d = r.json()
    tok = d.get("token")
    uid = (d.get("user") or {}).get("user_id")
    assert tok and uid
    CREATED.append(uid)
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s, uid


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    env = {}
    for line in open('/app/backend/.env'):
        if '=' in line:
            k, v = line.strip().split('=', 1)
            env[k] = v.strip('"')
    db = MongoClient(env['MONGO_URL'])[env['DB_NAME']]
    for uid in CREATED:
        db.users.delete_one({"user_id": uid})
        db.likes.delete_many({"$or": [{"from_user": uid}, {"to_user": uid}]})
        db.matches.delete_many({"pair": uid})
        db.messages.delete_many({"participants": uid})
        db.messages.delete_many({"from_user": uid})
        db.sessions.delete_many({"user_id": uid})


@pytest.fixture(scope="module")
def pair():
    a, a_id = _register("male")
    b, b_id = _register("female")
    return a, a_id, b, b_id


class TestLikeGate:
    def test_like_blocked_when_incomplete(self, pair):
        a, _, _, b_id = pair
        r = a.post(f"{BASE_URL}/api/like/{b_id}")
        assert r.status_code == 403
        d = r.json()["detail"]
        assert d["code"] == "profile_incomplete"
        assert sorted(d["missing"]) == sorted(REQUIRED)
        assert "message" in d

    def test_partial_profile_lists_only_missing(self, pair):
        a, _, _, b_id = pair
        r = a.put(f"{BASE_URL}/api/profile", json={"goal": "relationship", "kids": "no"})
        assert r.status_code == 200
        r = a.post(f"{BASE_URL}/api/like/{b_id}")
        assert r.status_code == 403
        assert sorted(r.json()["detail"]["missing"]) == sorted(["photos", "relationship", "smoking", "alcohol"])

    def test_pass_not_gated(self, pair):
        a, _, _, b_id = pair
        r = a.post(f"{BASE_URL}/api/pass/{b_id}")
        assert r.status_code == 200, r.text

    def test_home_feed_not_gated(self, pair):
        a = pair[0]
        r = a.get(f"{BASE_URL}/api/home/feed")
        assert r.status_code == 200

    def test_like_self_still_400(self, pair):
        a, a_id, _, _ = pair
        assert a.post(f"{BASE_URL}/api/like/{a_id}").status_code == 400

    def test_like_allowed_when_complete(self, pair):
        a, _, _, b_id = pair
        assert a.put(f"{BASE_URL}/api/profile", json=COMPLETE).status_code == 200
        r = a.post(f"{BASE_URL}/api/like/{b_id}")
        assert r.status_code == 200, r.text

    def test_like_nonexistent_target_404_when_complete(self, pair):
        a = pair[0]
        assert a.post(f"{BASE_URL}/api/like/TEST_nouser_xyz").status_code == 404


class TestMessageGate:
    def test_first_message_blocked_when_incomplete(self, pair):
        _, a_id, b, _ = pair
        r = b.post(f"{BASE_URL}/api/chats/{a_id}/send", json={"text": "hi", "kind": "text"})
        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "profile_incomplete"

    def test_first_message_allowed_when_complete_and_reply_allowed_incomplete(self, pair):
        a, a_id, b, b_id = pair
        # a is complete (from like test) -> starts chat
        r = a.post(f"{BASE_URL}/api/chats/{b_id}/send", json={"text": "TEST_hello", "kind": "text"})
        assert r.status_code == 200, r.text
        # b still incomplete -> reply allowed in existing chat
        r = b.post(f"{BASE_URL}/api/chats/{a_id}/send", json={"text": "TEST_reply", "kind": "text"})
        assert r.status_code == 200, r.text
