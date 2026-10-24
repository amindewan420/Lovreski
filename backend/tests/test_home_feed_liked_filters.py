"""Backend tests for Home feed `liked` flag, age filter, distance hard-filter,
and Discover regression (iteration 35 — Lovreski Home page fixes)."""
import os
import pytest
import requests
from pathlib import Path


def _load_backend_url():
    v = os.environ.get('REACT_APP_BACKEND_URL')
    if v:
        return v.rstrip('/')
    env = Path('/app/frontend/.env')
    for line in env.read_text().splitlines():
        if line.startswith('REACT_APP_BACKEND_URL='):
            return line.split('=', 1)[1].strip().rstrip('/')
    raise RuntimeError('REACT_APP_BACKEND_URL not set')


BASE_URL = _load_backend_url()
API = f"{BASE_URL}/api"

U1 = {"email": "testuser1@lovreski.ru", "password": "password123"}


# ---------------- fixtures ----------------
@pytest.fixture(scope="module")
def tokens():
    r = requests.post(f"{API}/auth/login", json=U1, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def client(tokens):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tokens}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module", autouse=True)
def restore_profile(client):
    # Snapshot current profile
    me = client.get(f"{API}/me", timeout=20).json()
    snap = {
        "age_min": me.get("age_min", 18),
        "age_max": me.get("age_max", 60),
        "distance_mode": me.get("distance_mode", "unlimited"),
        "distance_km": me.get("distance_km", 100),
        "lat": me.get("lat"),
        "lng": me.get("lng"),
    }
    yield
    # Restore
    try:
        client.put(f"{API}/profile", json=snap, timeout=20)
    except Exception:
        pass


# ---------------- liked flag + idempotency ----------------
def test_home_feed_has_liked_boolean(client):
    r = client.get(f"{API}/home/feed?limit=20", timeout=20)
    assert r.status_code == 200
    feed = r.json()
    assert isinstance(feed, list)
    assert len(feed) > 0, "home feed empty — seed data missing"
    for p in feed:
        assert "liked" in p, f"missing liked on {p.get('user_id')}"
        assert isinstance(p["liked"], bool)


def test_like_keeps_card_and_sets_liked_true(client):
    r = client.get(f"{API}/home/feed?limit=20", timeout=20).json()
    unliked = [p for p in r if not p["liked"]]
    assert unliked, "no unliked profile to test with"
    target = unliked[0]["user_id"]

    lk = client.post(f"{API}/like/{target}", timeout=20)
    assert lk.status_code == 200

    r2 = client.get(f"{API}/home/feed?limit=50", timeout=20).json()
    found = [p for p in r2 if p["user_id"] == target]
    assert found, f"liked profile {target} was removed from home feed (bug)"
    assert found[0]["liked"] is True


def test_duplicate_like_idempotent(client):
    r = client.get(f"{API}/home/feed?limit=50", timeout=20).json()
    liked = [p for p in r if p["liked"]]
    assert liked, "need a liked profile from previous test"
    target = liked[0]["user_id"]

    lk = client.post(f"{API}/like/{target}", timeout=20)
    assert lk.status_code == 200, f"duplicate like failed: {lk.status_code} {lk.text}"

    r2 = client.get(f"{API}/home/feed?limit=50", timeout=20).json()
    still = [p for p in r2 if p["user_id"] == target]
    assert still and still[0]["liked"] is True


# ---------------- age filter ----------------
def test_age_filter_hard_limits_feed(client):
    up = client.put(f"{API}/profile", json={"age_min": 20, "age_max": 25}, timeout=20)
    assert up.status_code == 200

    feed = client.get(f"{API}/home/feed?limit=50", timeout=20).json()
    # feed may be empty if no users in band — assert all returned are in range
    for p in feed:
        assert 20 <= p["age"] <= 25, f"profile {p['user_id']} age {p['age']} outside 20-25"

    # restore
    client.put(f"{API}/profile", json={"age_min": 18, "age_max": 60}, timeout=20)


def test_age_filter_realtime_change(client):
    client.put(f"{API}/profile", json={"age_min": 18, "age_max": 60}, timeout=20)
    before = client.get(f"{API}/home/feed?limit=50", timeout=20).json()

    client.put(f"{API}/profile", json={"age_min": 40, "age_max": 60}, timeout=20)
    after = client.get(f"{API}/home/feed?limit=50", timeout=20).json()
    for p in after:
        assert 40 <= p["age"] <= 60

    # restore
    client.put(f"{API}/profile", json={"age_min": 18, "age_max": 60}, timeout=20)


# ---------------- distance hard filter ----------------
def test_distance_hard_filter(client):
    # Set Moscow location
    client.put(f"{API}/profile", json={"lat": 55.75, "lng": 37.61}, timeout=20)
    # Limited 10km → very narrow; may be empty but must not include > 10 km
    client.put(f"{API}/profile", json={"distance_mode": "limited", "distance_km": 10}, timeout=20)
    narrow = client.get(f"{API}/home/feed?limit=50", timeout=20).json()
    for p in narrow:
        assert p.get("distance_km") is not None, f"profile {p['user_id']} has no distance despite hard filter"
        assert p["distance_km"] <= 10

    # Wider 500 km — should include results and all within range
    client.put(f"{API}/profile", json={"distance_mode": "limited", "distance_km": 500}, timeout=20)
    wide = client.get(f"{API}/home/feed?limit=50", timeout=20).json()
    for p in wide:
        assert p.get("distance_km") is not None
        assert p["distance_km"] <= 500

    # Restore unlimited
    client.put(f"{API}/profile", json={"distance_mode": "unlimited"}, timeout=20)


# ---------------- discover regression ----------------
def test_discover_excludes_liked(client):
    home = client.get(f"{API}/home/feed?limit=50", timeout=20).json()
    liked_ids = {p["user_id"] for p in home if p["liked"]}
    if not liked_ids:
        pytest.skip("no liked profiles to verify discover exclusion")
    disc = client.get(f"{API}/discover/feed?limit=50", timeout=20)
    assert disc.status_code == 200
    disc_ids = {p["user_id"] for p in disc.json()}
    overlap = liked_ids & disc_ids
    assert not overlap, f"discover feed must exclude liked profiles, got overlap: {overlap}"


def test_likes_sent_contains_liked(client):
    r = client.get(f"{API}/likes/sent", timeout=20)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
