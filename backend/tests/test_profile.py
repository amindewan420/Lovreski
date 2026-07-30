"""Profile endpoints tests — Iteration 9.
Covers /profile/me/stats, photo upload/reorder/delete, location, age gate,
interests cap, new gender values (non_binary, prefer_not)."""
import os, base64, time, io, uuid, requests, pytest

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://lovreski-dating.preview.emergentagent.com').rstrip('/')

def _tiny_png_data_url() -> str:
    # 1x1 red PNG
    b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
    return "data:image/png;base64," + b64

def _register(gender="female", dob="1998-05-15"):
    ts = uuid.uuid4().hex[:12]
    email = f"profiletest_{ts}_{gender}@lovreski.ru"
    r = requests.post(f"{BASE_URL}/api/auth/register", json={
        "email": email, "password": "password123", "name": "TEST_Profile",
        "gender": gender, "dob": dob,
    })
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text}"
    j = r.json()
    return j["token"], j["user"], email

@pytest.fixture(scope="module")
def auth():
    token, user, email = _register()
    return {"token": token, "user": user, "email": email,
            "h": {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}}


class TestProfileStats:
    def test_stats_endpoint_shape(self, auth):
        r = requests.get(f"{BASE_URL}/api/profile/me/stats", headers=auth["h"])
        assert r.status_code == 200
        d = r.json()
        for k in ("popularity", "likes_received", "polarity", "completion", "photo_count", "interest_count"):
            assert k in d, f"missing {k}"
        assert d["popularity"] in ("low", "medium", "high")
        assert 0 <= d["polarity"] <= 100
        assert 0 <= d["completion"] <= 100


class TestPhotoOps:
    def test_upload_photo(self, auth):
        r = requests.post(f"{BASE_URL}/api/profile/photo", headers=auth["h"], json={"data_url": _tiny_png_data_url()})
        assert r.status_code == 200, r.text
        assert len(r.json()["photos"]) >= 1

    def test_upload_non_image_rejected(self, auth):
        r = requests.post(f"{BASE_URL}/api/profile/photo", headers=auth["h"], json={"data_url": "data:text/plain;base64,aGVsbG8="})
        assert r.status_code == 400

    def test_upload_oversize_rejected(self, auth):
        big = "data:image/png;base64," + ("A" * 2_100_000)
        r = requests.post(f"{BASE_URL}/api/profile/photo", headers=auth["h"], json={"data_url": big})
        assert r.status_code == 413

    def test_max_4_photos(self, auth):
        # Get current count via stats
        for _ in range(4):
            requests.post(f"{BASE_URL}/api/profile/photo", headers=auth["h"], json={"data_url": _tiny_png_data_url()})
        # This 5th should fail (either 400 max limit)
        r = requests.post(f"{BASE_URL}/api/profile/photo", headers=auth["h"], json={"data_url": _tiny_png_data_url()})
        assert r.status_code == 400
        assert "4" in r.json().get("detail", "")

    def test_reorder_photos(self, auth):
        # Get current photos
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=auth["h"]).json()
        photos = me.get("photos", [])
        if len(photos) < 2:
            pytest.skip("need 2 photos to reorder")
        new_order = list(reversed(photos))
        r = requests.put(f"{BASE_URL}/api/profile/photos", headers=auth["h"], json={"photos": new_order})
        assert r.status_code == 200
        assert r.json()["photos"] == new_order

    def test_delete_photo_out_of_range(self, auth):
        r = requests.delete(f"{BASE_URL}/api/profile/photo/99", headers=auth["h"])
        assert r.status_code == 404

    def test_delete_photo_valid(self, auth):
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=auth["h"]).json()
        before = len(me.get("photos", []))
        if before == 0:
            pytest.skip("no photos to delete")
        r = requests.delete(f"{BASE_URL}/api/profile/photo/0", headers=auth["h"])
        assert r.status_code == 200
        assert len(r.json()["photos"]) == before - 1


class TestLocation:
    def test_update_location(self, auth):
        r = requests.put(f"{BASE_URL}/api/profile/location", headers=auth["h"],
                         json={"lat": 44.9521, "lng": 34.1024, "city": "Симферополь"})
        assert r.status_code == 200
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=auth["h"]).json()
        assert abs(me.get("lat", 0) - 44.9521) < 0.01
        assert abs(me.get("lng", 0) - 34.1024) < 0.01


class TestProfileValidation:
    def test_age_gate_under_18(self, auth):
        r = requests.put(f"{BASE_URL}/api/profile", headers=auth["h"], json={"dob": "2015-01-01"})
        assert r.status_code == 400
        assert "18" in r.json().get("detail", "")

    def test_interests_cap_11(self, auth):
        interests = [f"i{i}" for i in range(11)]
        r = requests.put(f"{BASE_URL}/api/profile", headers=auth["h"], json={"interests": interests})
        assert r.status_code == 400
        assert "10" in r.json().get("detail", "") or "Максимум" in r.json().get("detail", "")

    def test_interests_cap_10_ok(self, auth):
        interests = [f"i{i}" for i in range(10)]
        r = requests.put(f"{BASE_URL}/api/profile", headers=auth["h"], json={"interests": interests})
        assert r.status_code == 200


class TestNewGenderValues:
    def test_register_non_binary(self):
        token, user, _ = _register(gender="non_binary")
        assert user["gender"] == "non_binary"

    def test_register_prefer_not(self):
        token, user, _ = _register(gender="prefer_not")
        assert user["gender"] == "prefer_not"

    def test_register_invalid_gender(self):
        ts = uuid.uuid4().hex[:12]
        r = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": f"bad_{ts}@lovreski.ru", "password": "password123",
            "name": "TEST", "gender": "banana", "dob": "1998-05-15",
        })
        assert r.status_code == 422  # Pydantic Literal rejection
