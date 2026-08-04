"""Iteration 19 - Distance filter tests"""
import os
import time
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://lovreski-dating.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

TS = int(time.time())


def _register(email_prefix, lat=None, lng=None, gender="female"):
    email = f"{email_prefix}_{TS}_{os.urandom(2).hex()}@lovreski.ru"
    payload = {"email": email, "password": "password123", "name": f"U{email_prefix}",
               "gender": gender, "dob": "1998-05-15"}
    r = requests.post(f"{API}/auth/register", json=payload, timeout=15)
    assert r.status_code == 200, f"register failed {r.status_code} {r.text}"
    token = r.json()["token"]
    # If lat/lng provided, update profile
    if lat is not None:
        h = {"Authorization": f"Bearer {token}"}
        pr = requests.put(f"{API}/profile", json={"lat": lat, "lng": lng}, headers=h, timeout=15)
        assert pr.status_code == 200, pr.text
    return token, email


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ────────── ProfileUpdate validation ──────────
def test_profile_put_distance_km_valid():
    token, _ = _register("dv")
    r = requests.put(f"{API}/profile", json={"distance_mode": "limited", "distance_km": 150}, headers=_auth(token), timeout=15)
    assert r.status_code == 200, r.text
    me = requests.get(f"{API}/auth/me", headers=_auth(token), timeout=15).json()
    assert me.get("distance_mode") == "limited"
    assert me.get("distance_km") == 150


def test_profile_put_distance_km_too_large_422():
    token, _ = _register("dv2")
    r = requests.put(f"{API}/profile", json={"distance_km": 2500}, headers=_auth(token), timeout=15)
    assert r.status_code == 422, f"expected 422 got {r.status_code}: {r.text}"


def test_profile_put_distance_km_negative_422():
    token, _ = _register("dv3")
    r = requests.put(f"{API}/profile", json={"distance_km": -5}, headers=_auth(token), timeout=15)
    assert r.status_code == 422, f"expected 422 got {r.status_code}: {r.text}"


def test_profile_put_distance_km_boundary_0_and_2000():
    token, _ = _register("dv4")
    r = requests.put(f"{API}/profile", json={"distance_km": 0}, headers=_auth(token), timeout=15)
    assert r.status_code == 200
    r = requests.put(f"{API}/profile", json={"distance_km": 2000}, headers=_auth(token), timeout=15)
    assert r.status_code == 200


# ────────── Feed radius filter ──────────
# Moscow origin
MOSCOW = (55.7558, 37.6173)
# ~10 km away in Moscow (slight lat delta)
NEAR = (55.8458, 37.6173)  # ~10 km north
# ~500 km away (Nizhny Novgorod area)
FAR = (56.3269, 44.0075)


def test_feed_limited_filters_by_radius_and_unlimited_shows_all():
    # Create viewer (male) with location in Moscow, show_me=female
    viewer_token, viewer_email = _register("view", lat=MOSCOW[0], lng=MOSCOW[1], gender="male")
    # Create 2 female users near & far
    near_token, near_email = _register("near", lat=NEAR[0], lng=NEAR[1], gender="female")
    far_token, far_email = _register("far", lat=FAR[0], lng=FAR[1], gender="female")

    # Set viewer to limited 50km + show_me=female
    r = requests.put(f"{API}/profile", json={
        "distance_mode": "limited", "distance_km": 50, "show_me": "female"
    }, headers=_auth(viewer_token), timeout=15)
    assert r.status_code == 200, r.text

    # Fetch feed with large limit
    r = requests.get(f"{API}/home/feed?limit=200", headers=_auth(viewer_token), timeout=15)
    assert r.status_code == 200
    feed = r.json()
    emails_in_feed = {u.get("email") for u in feed}
    # Emails may not be exposed in user_public; fall back to name matching
    names_in_feed = {u.get("name") for u in feed}
    ids_in_feed = {u.get("user_id") or u.get("id") for u in feed}

    # We need to identify near vs far - get their user_ids via their own /profile/me
    near_me = requests.get(f"{API}/auth/me", headers=_auth(near_token), timeout=15).json()
    far_me = requests.get(f"{API}/auth/me", headers=_auth(far_token), timeout=15).json()
    near_id = near_me.get("user_id")
    far_id = far_me.get("user_id")
    assert near_id and far_id

    assert near_id in ids_in_feed, f"NEAR user (10km) missing from limited feed. feed size={len(feed)}"
    assert far_id not in ids_in_feed, f"FAR user (500km) should be excluded from limited feed"

    # Switch to unlimited
    r = requests.put(f"{API}/profile", json={"distance_mode": "unlimited"}, headers=_auth(viewer_token), timeout=15)
    assert r.status_code == 200
    r = requests.get(f"{API}/home/feed?limit=200", headers=_auth(viewer_token), timeout=15)
    assert r.status_code == 200
    feed2 = r.json()
    ids2 = {u.get("user_id") or u.get("id") for u in feed2}
    assert near_id in ids2, "NEAR user missing in unlimited"
    assert far_id in ids2, "FAR user missing in unlimited"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
