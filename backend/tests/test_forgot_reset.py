"""Backend tests for forgot-password OTP flow."""
import os
import time
import requests
import pytest

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://lovreski-dating.preview.emergentagent.com').rstrip('/')
API = f"{BASE_URL}/api"


def _register(email, pw="password123"):
    return requests.post(f"{API}/auth/register", json={
        "email": email, "password": pw, "name": "Tester",
        "gender": "male", "dob": "1998-05-15",
    })


def _login(email, pw):
    return requests.post(f"{API}/auth/login", json={"email": email, "password": pw})


@pytest.fixture(scope="module")
def fresh_user():
    ts = int(time.time() * 1000)
    email = f"reset_{ts}@lovreski.ru"
    r = _register(email)
    assert r.status_code == 200, r.text
    return {"email": email, "password": "password123"}


class TestForgotFlow:
    def test_forgot_known_email_returns_dev_otp(self, fresh_user):
        r = requests.post(f"{API}/auth/forgot", json={"email": fresh_user["email"]})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert data.get("dev_otp") and len(data["dev_otp"]) == 6 and data["dev_otp"].isdigit()
        fresh_user["otp"] = data["dev_otp"]

    def test_forgot_unknown_email_dev_otp_null(self):
        ts = int(time.time() * 1000)
        r = requests.post(f"{API}/auth/forgot", json={"email": f"nobody_{ts}@lovreski.ru"})
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") is True
        assert data.get("dev_otp") is None

    def test_reset_invalid_otp(self, fresh_user):
        r = requests.post(f"{API}/auth/reset", json={
            "email": fresh_user["email"], "otp": "000000", "new_password": "newpass456",
        })
        assert r.status_code == 400
        assert "Invalid OTP" in r.json().get("detail", "")

    def test_reset_with_valid_otp_and_login_new(self, fresh_user):
        # request a fresh OTP (this is the 2nd request for this email, still under 3)
        r = requests.post(f"{API}/auth/forgot", json={"email": fresh_user["email"]})
        assert r.status_code == 200
        otp = r.json()["dev_otp"]
        new_pw = "newpass456"
        rr = requests.post(f"{API}/auth/reset", json={
            "email": fresh_user["email"], "otp": otp, "new_password": new_pw,
        })
        assert rr.status_code == 200, rr.text
        assert rr.json() == {"ok": True}
        # login with new password should succeed
        lr = _login(fresh_user["email"], new_pw)
        assert lr.status_code == 200, lr.text
        assert "token" in lr.json()
        # login with old password should fail 401
        old = _login(fresh_user["email"], fresh_user["password"])
        assert old.status_code == 401
        # save otp for one-time-use test
        fresh_user["used_otp"] = otp
        fresh_user["password"] = new_pw

    def test_otp_one_time_use(self, fresh_user):
        # reusing the OTP just consumed should fail
        r = requests.post(f"{API}/auth/reset", json={
            "email": fresh_user["email"], "otp": fresh_user["used_otp"], "new_password": "another123",
        })
        assert r.status_code == 400
        assert "Invalid OTP" in r.json().get("detail", "")


class TestRateLimit:
    def test_rate_limit_4th_request_429(self):
        ts = int(time.time() * 1000)
        email = f"rl_{ts}@lovreski.ru"
        assert _register(email).status_code == 200
        for i in range(3):
            r = requests.post(f"{API}/auth/forgot", json={"email": email})
            assert r.status_code == 200, f"req {i+1}: {r.text}"
        r4 = requests.post(f"{API}/auth/forgot", json={"email": email})
        assert r4.status_code == 429
        assert "Too many reset requests" in r4.json().get("detail", "")
