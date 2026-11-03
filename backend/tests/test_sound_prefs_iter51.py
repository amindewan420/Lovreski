# Sound & Audio preferences: PATCH /api/user/preferences + /api/auth/me
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
DEFAULTS = {"soundEnabled": False, "soundVolume": 50, "micEnabled": False}


def _login(email):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "password123"})
    if r.status_code != 200:
        pytest.skip(f"login failed {email}")
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return s


@pytest.fixture(scope="module")
def client():
    s = _login("testuser1@lovreski.ru")
    yield s
    s.patch(f"{BASE_URL}/api/user/preferences", json=DEFAULTS)


class TestPrefs:
    def test_unauth_401(self):
        r = requests.patch(f"{BASE_URL}/api/user/preferences", json={"soundEnabled": True})
        assert r.status_code == 401

    def test_reset_defaults(self, client):
        r = client.patch(f"{BASE_URL}/api/user/preferences", json=DEFAULTS)
        assert r.status_code == 200
        assert r.json() == DEFAULTS

    def test_empty_body_returns_merged(self, client):
        r = client.patch(f"{BASE_URL}/api/user/preferences", json={})
        assert r.status_code == 200
        d = r.json()
        for k in DEFAULTS:
            assert k in d

    def test_partial_sound_enabled(self, client):
        r = client.patch(f"{BASE_URL}/api/user/preferences", json={"soundEnabled": True})
        assert r.status_code == 200
        assert r.json() == {"soundEnabled": True, "soundVolume": 50, "micEnabled": False}
        me = client.get(f"{BASE_URL}/api/auth/me").json()
        assert me["preferences"]["soundEnabled"] is True

    def test_partial_volume(self, client):
        r = client.patch(f"{BASE_URL}/api/user/preferences", json={"soundVolume": 80})
        assert r.status_code == 200
        d = r.json()
        assert d["soundVolume"] == 80 and d["soundEnabled"] is True
        me = client.get(f"{BASE_URL}/api/auth/me").json()
        assert me["preferences"]["soundVolume"] == 80
        assert me["preferences"]["soundEnabled"] is True

    def test_mic(self, client):
        r = client.patch(f"{BASE_URL}/api/user/preferences", json={"micEnabled": True})
        assert r.status_code == 200 and r.json()["micEnabled"] is True
        assert client.get(f"{BASE_URL}/api/auth/me").json()["preferences"]["micEnabled"] is True

    @pytest.mark.parametrize("vol", [-1, 101, 1000])
    def test_volume_out_of_range(self, client, vol):
        r = client.patch(f"{BASE_URL}/api/user/preferences", json={"soundVolume": vol})
        assert r.status_code == 422

    @pytest.mark.parametrize("vol", [0, 100])
    def test_volume_bounds_ok(self, client, vol):
        r = client.patch(f"{BASE_URL}/api/user/preferences", json={"soundVolume": vol})
        assert r.status_code == 200 and r.json()["soundVolume"] == vol

    def test_wrong_type(self, client):
        r = client.patch(f"{BASE_URL}/api/user/preferences", json={"soundEnabled": "notabool"})
        assert r.status_code == 422

    def test_unknown_field_ignored(self, client):
        r = client.patch(f"{BASE_URL}/api/user/preferences", json={"evil": 1})
        assert r.status_code == 200
        assert "evil" not in r.json()
        me = client.get(f"{BASE_URL}/api/auth/me").json()
        assert "evil" not in (me.get("preferences") or {})

    def test_null_does_not_overwrite(self, client):
        client.patch(f"{BASE_URL}/api/user/preferences", json={"soundEnabled": True})
        r = client.patch(f"{BASE_URL}/api/user/preferences", json={"soundEnabled": None})
        assert r.status_code == 200 and r.json()["soundEnabled"] is True

    def test_final_reset(self, client):
        r = client.patch(f"{BASE_URL}/api/user/preferences", json=DEFAULTS)
        assert r.json() == DEFAULTS
        assert client.get(f"{BASE_URL}/api/auth/me").json()["preferences"] == DEFAULTS
