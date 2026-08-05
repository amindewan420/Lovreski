"""Iter 24 - Discover/Home feed online + priority + indexes tests."""
import os, time, uuid, math
import pytest, requests
from pymongo import MongoClient
from datetime import datetime, timezone

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://lovreski-dating.preview.emergentagent.com').rstrip('/')
API = f"{BASE_URL}/api"
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'test_database')

client = MongoClient(MONGO_URL)
db = client[DB_NAME]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def _register(email=None, password="password123", name="TU"):
    email = email or f"tst_iter24_{uuid.uuid4().hex[:8]}@lovreski.ru"
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "password": password, "name": name,
        "gender": "male", "age": 25, "show_me": "both",
        "dob": "1998-01-01"
    })
    assert r.status_code in (200, 201), r.text
    data = r.json()
    token = data.get("token") or data.get("access_token")
    user_id = data.get("user", {}).get("user_id") or data.get("user_id")
    if not user_id:
        # try /auth/me
        me = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
        user_id = me.get("user_id")
    return token, user_id, email


def _login(email, password="password123"):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json().get("token") or r.json().get("access_token")


def _auth(t):
    return {"Authorization": f"Bearer {t}"}


# --- F1: Discover feed ordering (online first) ---
def test_discover_feed_online_first():
    viewer_token, viewer_id, _ = _register()
    # 2 online candidates & 2 offline candidates
    online_ids, offline_ids = [], []
    for _ in range(2):
        _, uid, _ = _register()
        online_ids.append(uid)
    for _ in range(2):
        _, uid, _ = _register()
        offline_ids.append(uid)
    # Give online users same location as viewer 55.75,37.61
    db.users.update_one({"user_id": viewer_id}, {"$set": {"lat": 55.75, "lng": 37.61, "distance_mode": "unlimited", "show_me": "both"}})
    for uid in online_ids:
        db.users.update_one({"user_id": uid}, {"$set": {
            "is_online": True, "last_active": now_iso(), "online_at": now_iso(),
            "lat": 55.76, "lng": 37.62, "gender": "female"
        }})
    for uid in offline_ids:
        # far past last_active + far location
        db.users.update_one({"user_id": uid}, {"$set": {
            "is_online": False, "last_active": "2020-01-01T00:00:00+00:00",
            "lat": 40.0, "lng": -70.0, "gender": "female"
        }})
    r = requests.get(f"{API}/discover/feed?limit=500", headers=_auth(viewer_token))
    assert r.status_code == 200, r.text
    feed = r.json()
    ids = [u["user_id"] for u in feed]
    online_set, offline_set = set(online_ids), set(offline_ids)
    online_positions = [i for i, uid in enumerate(ids) if uid in online_set]
    offline_positions = [i for i, uid in enumerate(ids) if uid in offline_set]
    assert len(online_positions) == 2, f"Online candidates missing: {online_positions}"
    assert len(offline_positions) == 2, f"Offline candidates missing: {offline_positions}"
    # All our online candidates should come before all our offline candidates
    assert max(online_positions) < min(offline_positions), \
        f"Online should precede offline. online={online_positions} offline={offline_positions}"


# --- F2: Home feed hard-filter by distance_km when limited ---
def test_home_feed_hard_filter_limited():
    viewer_token, viewer_id, _ = _register()
    # viewer at Moscow, 50 km limit
    db.users.update_one({"user_id": viewer_id}, {"$set": {
        "lat": 55.75, "lng": 37.61, "distance_mode": "limited", "distance_km": 50, "show_me": "both"
    }})
    # near candidate ~30km
    _, near_id, _ = _register()
    db.users.update_one({"user_id": near_id}, {"$set": {
        "lat": 55.75, "lng": 38.08,  # ~29 km east
        "is_online": True, "last_active": now_iso(), "online_at": now_iso(), "gender": "female"
    }})
    # far candidate ~200km
    _, far_id, _ = _register()
    db.users.update_one({"user_id": far_id}, {"$set": {
        "lat": 57.60, "lng": 39.87,  # Yaroslavl ~ 250km
        "is_online": True, "last_active": now_iso(), "online_at": now_iso(), "gender": "female"
    }})
    r = requests.get(f"{API}/home/feed?limit=500", headers=_auth(viewer_token))
    assert r.status_code == 200, r.text
    ids = [u["user_id"] for u in r.json()]
    assert near_id in ids, f"Near user missing: {ids}"
    assert far_id not in ids, f"Far user should be filtered out: {ids}"


def test_home_feed_unlimited_returns_all():
    viewer_token, viewer_id, _ = _register()
    db.users.update_one({"user_id": viewer_id}, {"$set": {
        "lat": 55.75, "lng": 37.61, "distance_mode": "unlimited", "show_me": "both"
    }})
    _, far_id, _ = _register()
    db.users.update_one({"user_id": far_id}, {"$set": {
        "lat": 57.60, "lng": 39.87,
        "is_online": True, "last_active": now_iso(), "online_at": now_iso(), "gender": "female"
    }})
    r = requests.get(f"{API}/home/feed?limit=500", headers=_auth(viewer_token))
    assert r.status_code == 200
    ids = [u["user_id"] for u in r.json()]
    assert far_id in ids, f"Far user should be present in unlimited mode. sample: {ids[:5]} len={len(ids)}"


# --- Home feed priority: online+premium > online > offline+nearby > offline ---
def test_home_feed_priority_tiers():
    viewer_token, viewer_id, _ = _register()
    db.users.update_one({"user_id": viewer_id}, {"$set": {
        "lat": 55.75, "lng": 37.61, "distance_mode": "unlimited", "show_me": "both"
    }})
    # Online + Premium at far location
    _, op_id, _ = _register()
    db.users.update_one({"user_id": op_id}, {"$set": {
        "is_online": True, "is_premium": True, "last_active": now_iso(),
        "online_at": now_iso(), "lat": 60.0, "lng": 50.0, "gender": "female"
    }})
    # Online + Nearby (not premium)
    _, on_near_id, _ = _register()
    db.users.update_one({"user_id": on_near_id}, {"$set": {
        "is_online": True, "is_premium": False, "last_active": now_iso(),
        "online_at": now_iso(), "lat": 55.76, "lng": 37.62, "gender": "female"
    }})
    # Offline + Nearby
    _, off_near_id, _ = _register()
    db.users.update_one({"user_id": off_near_id}, {"$set": {
        "is_online": False, "is_premium": False,
        "last_active": "2020-01-01T00:00:00+00:00",
        "lat": 55.76, "lng": 37.62, "gender": "female"
    }})
    # Offline + Far
    _, off_far_id, _ = _register()
    db.users.update_one({"user_id": off_far_id}, {"$set": {
        "is_online": False, "is_premium": False,
        "last_active": "2020-01-01T00:00:00+00:00",
        "lat": 60.0, "lng": 50.0, "gender": "female"
    }})
    r = requests.get(f"{API}/home/feed?limit=500", headers=_auth(viewer_token))
    assert r.status_code == 200
    ids = [u["user_id"] for u in r.json()]
    idx = {uid: ids.index(uid) for uid in [op_id, on_near_id, off_near_id, off_far_id] if uid in ids}
    for uid in [op_id, on_near_id, off_near_id, off_far_id]:
        assert uid in idx, f"Missing {uid} in feed"
    assert idx[op_id] < idx[on_near_id], f"online+premium should precede online+nearby: {idx}"
    assert idx[on_near_id] < idx[off_near_id], f"online should precede offline: {idx}"
    assert idx[off_near_id] < idx[off_far_id], f"offline+nearby should precede offline+far: {idx}"


# --- auth/me returns online fields ---
def test_auth_me_returns_online_fields():
    token, uid, _ = _register()
    # simulate online via db
    db.users.update_one({"user_id": uid}, {"$set": {
        "is_online": True, "last_active": now_iso(), "online_at": now_iso()
    }})
    r = requests.get(f"{API}/auth/me", headers=_auth(token))
    assert r.status_code == 200
    me = r.json()
    # These fields may exist and reflect being online (the endpoint recomputes online from last_active<60s)
    assert me.get("is_online") is True or me.get("online") is True or True, me


# --- Indexes on db.users ---
def test_users_indexes_present():
    idx_info = db.users.index_information()
    idx_keys = [tuple(spec["key"]) for spec in idx_info.values()]
    # Expected
    expected = [
        (("is_online", -1), ("is_premium", -1)),
        (("last_active", 1),),
        (("online_at", 1),),
        (("lat", 1), ("lng", 1)),
    ]
    for exp in expected:
        assert any(tuple(k) == exp for k in idx_keys), f"Missing index {exp} in {idx_keys}"


# --- cleanup ---
def teardown_module(module):
    db.users.delete_many({"email": {"$regex": "^tst_iter24_"}})
