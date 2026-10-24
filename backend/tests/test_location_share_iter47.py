# Iter47: Location sharing — 2-coin cost (always), unique 5-min link token, public /loc/{token}, live update/stop + WS
import os, re, uuid, json, time, threading
import pytest, requests, websocket
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient
from dotenv import dotenv_values

BASE_URL = (os.environ.get('REACT_APP_BACKEND_URL') or dotenv_values('/app/frontend/.env')['REACT_APP_BACKEND_URL']).rstrip('/')
API = f"{BASE_URL}/api"
BENV = dotenv_values('/app/backend/.env')
mdb = MongoClient(BENV['MONGO_URL'])[BENV['DB_NAME']]


def login(email, pw="password123"):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    tok = r.json()['token']
    h = {"Authorization": f"Bearer {tok}"}
    me = requests.get(f"{API}/auth/me", headers=h).json()
    return h, me['user_id'], tok


def coins(h):
    return int(requests.get(f"{API}/auth/me", headers=h).json().get('coins') or 0)


def send_loc(h, other, lat=55.75, lng=37.61, live=False, place="TEST_place"):
    return requests.post(f"{API}/chats/{other}/send", headers=h, json={"kind": "location", "lat": lat, "lng": lng, "place": place, "live": live})


@pytest.fixture(scope="module")
def A():
    return login("match_a@lovreski.ru")


@pytest.fixture(scope="module")
def B():
    return login("match_b@lovreski.ru")


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    mdb.messages.delete_many({"kind": "location", "location.place": {"$regex": "^TEST_"}})


# ── Cost / deduction ──
def test_location_deducts_2_and_shape(A, B):
    h, _, _ = A
    before = coins(h)
    r = send_loc(h, B[1], live=True)
    assert r.status_code == 200, r.text
    d = r.json()
    assert coins(h) == before - 2
    assert re.fullmatch(r"[0-9a-f]{32}", d['location']['token'])
    assert d['location']['live'] is True
    assert d['cost_paid'] == 2
    created = datetime.fromisoformat(d['created_at'].replace("Z", "+00:00"))
    exp = datetime.fromisoformat(d['location_expires_at'].replace("Z", "+00:00"))
    assert abs((exp - created).total_seconds() - 300) < 2


def test_tokens_unique(A, B):
    h = A[0]
    t1 = send_loc(h, B[1]).json()['location']['token']
    t2 = send_loc(h, B[1]).json()['location']['token']
    assert t1 != t2


def test_new_user_within_free_quota_still_pays(A):
    email = f"test_loc_{uuid.uuid4().hex[:8]}@lovreski.ru"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "password123", "name": "TEST_Loc", "gender": "male", "dob": "1995-01-01"})
    assert r.status_code in (200, 201), r.text
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    uid = r.json()['user']['user_id']
    try:
        mdb.users.update_one({"user_id": uid}, {"$set": {"coins": 5}})
        r = send_loc(h, A[1])
        assert r.status_code == 200, r.text
        assert coins(h) == 3
        # free text still free
        rt = requests.post(f"{API}/chats/{A[1]}/send", headers=h, json={"kind": "text", "text": "TEST hi"})
        assert rt.status_code == 200 and coins(h) == 3
        # 3 → 1 → then blocked
        assert send_loc(h, A[1]).status_code == 200 and coins(h) == 1
        cnt = mdb.messages.count_documents({"from_user": uid})
        rb = send_loc(h, A[1])
        assert rb.status_code == 402
        det = rb.json()['detail']
        assert det['blocked'] is True and det['required'] == 2
        assert "Недостаточно монет" in det['message']
        assert coins(h) == 1
        assert mdb.messages.count_documents({"from_user": uid}) == cnt
    finally:
        mdb.messages.delete_many({"from_user": uid})
        mdb.users.delete_one({"user_id": uid})


def test_missing_latlng_400(A, B):
    h = A[0]
    before = coins(h)
    r = requests.post(f"{API}/chats/{B[1]}/send", headers=h, json={"kind": "location", "lat": 55.0})
    assert r.status_code == 400
    assert coins(h) == before


def test_parallel_double_spend(A):
    email = f"test_loc_{uuid.uuid4().hex[:8]}@lovreski.ru"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "password123", "name": "TEST_Loc", "gender": "male", "dob": "1995-01-01"})
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    uid = r.json()['user']['user_id']
    mdb.users.update_one({"user_id": uid}, {"$set": {"coins": 2}})
    res = []
    ts = [threading.Thread(target=lambda: res.append(send_loc(h, A[1]).status_code)) for _ in range(4)]
    [t.start() for t in ts]; [t.join() for t in ts]
    try:
        assert res.count(200) == 1, res
        assert coins(h) == 0
    finally:
        mdb.messages.delete_many({"from_user": uid})
        mdb.users.delete_one({"user_id": uid})


# ── Public link ──
def test_loc_link_valid_then_expired(A, B):
    d = send_loc(A[0], B[1], lat=55.7, lng=37.6).json()
    tok = d['location']['token']
    r = requests.get(f"{API}/loc/{tok}")
    assert r.status_code == 200
    j = r.json()
    assert j['valid'] is True and j['lat'] == 55.7 and j['lng'] == 37.6 and j['place'] == "TEST_place"
    assert 290 <= j['seconds_left'] <= 300
    mdb.messages.update_one({"message_id": d['message_id']}, {"$set": {"location_expires_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()}})
    r = requests.get(f"{API}/loc/{tok}")
    assert r.status_code == 410 and r.json()['detail'] == "This location link has expired"
    # messages list hides coords
    msgs = requests.get(f"{API}/chats/{A[1]}/messages", headers=B[0]).json()
    msgs = msgs.get('messages', msgs) if isinstance(msgs, dict) else msgs
    m = [x for x in msgs if x['message_id'] == d['message_id']]
    assert m and m[0]['location'] is None and m[0]['location_expired'] is True


def test_loc_link_unknown_malformed():
    assert requests.get(f"{API}/loc/{uuid.uuid4().hex}").status_code == 404
    assert requests.get(f"{API}/loc/not-a-token").status_code == 404


# ── Live update / stop ──
def test_live_update_ws_and_stop(A, B):
    d = send_loc(A[0], B[1], live=True).json()
    mid = d['message_id']
    ws_url = BASE_URL.replace("https://", "wss://").replace("http://", "ws://") + f"/api/ws?token={B[2]}"
    ws = websocket.create_connection(ws_url, timeout=10)
    time.sleep(1)
    try:
        r = requests.post(f"{API}/location/{mid}/update", headers=A[0], json={"lat": 55.8, "lng": 37.7})
        assert r.status_code == 200
        got = None
        end = time.time() + 8
        while time.time() < end:
            ev = json.loads(ws.recv())
            if ev.get('type') == 'location_update' and ev['data'].get('message_id') == mid:
                got = ev['data']; break
        assert got and got['lat'] == 55.8 and got['lng'] == 37.7
        j = requests.get(f"{API}/loc/{d['location']['token']}").json()
        assert j['lat'] == 55.8 and j['lng'] == 37.7
        # non-sender → 404
        assert requests.post(f"{API}/location/{mid}/update", headers=B[0], json={"lat": 1, "lng": 1}).status_code == 404
        assert requests.post(f"{API}/location/{mid}/stop", headers=B[0]).status_code == 404
        # stop → expired
        assert requests.post(f"{API}/location/{mid}/stop", headers=A[0]).status_code == 200
        got2 = None
        end = time.time() + 8
        while time.time() < end:
            ev = json.loads(ws.recv())
            if ev.get('type') == 'location_update' and ev['data'].get('message_id') == mid:
                got2 = ev['data']; break
        assert got2 and got2.get('expired') is True
        assert requests.get(f"{API}/loc/{d['location']['token']}").status_code == 410
        assert requests.post(f"{API}/location/{mid}/update", headers=A[0], json={"lat": 1, "lng": 1}).status_code == 410
    finally:
        ws.close()


def test_update_non_live_404(A, B):
    d = send_loc(A[0], B[1], live=False).json()
    assert requests.post(f"{API}/location/{d['message_id']}/update", headers=A[0], json={"lat": 1, "lng": 1}).status_code == 404


def test_update_invalid_coords_422(A, B):
    d = send_loc(A[0], B[1], live=True).json()
    assert requests.post(f"{API}/location/{d['message_id']}/update", headers=A[0], json={"lat": 999, "lng": 1}).status_code == 422
    requests.post(f"{API}/location/{d['message_id']}/stop", headers=A[0])


def test_regression_text_send(A, B):
    r = requests.post(f"{API}/chats/{B[1]}/send", headers=A[0], json={"kind": "text", "text": "TEST_regression"})
    assert r.status_code == 200 and r.json()['text'] == "TEST_regression"
    mdb.messages.delete_one({"message_id": r.json()['message_id']})
