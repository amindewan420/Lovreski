"""Focused verification for Iteration 9 profile bugfix.

Checks PUT /api/profile dob age gate and partial update behavior against the
preview backend URL configured for the frontend.
"""
import os
import time
import requests


BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://lovreski-dating.preview.emergentagent.com"
).rstrip("/")


def assert_status(resp, expected, label):
    if resp.status_code != expected:
        raise AssertionError(f"{label}: expected {expected}, got {resp.status_code}: {resp.text}")


def main():
    ts = int(time.time() * 1000)
    email = f"profiletest_bugfix_{ts}@lovreski.ru"
    password = "password123"
    reg = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={
            "email": email,
            "password": password,
            "name": "Bugfix QA",
            "gender": "female",
            "dob": "1998-05-15",
        },
        timeout=15,
    )
    assert_status(reg, 200, "register fresh valid user")
    token = reg.json()["token"]
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # 12-year-old must be rejected with the exact Russian detail.
    r = requests.put(f"{BASE_URL}/api/profile", headers=headers, json={"dob": "2015-01-01"}, timeout=15)
    assert_status(r, 400, "reject 2015-01-01 dob")
    assert r.json().get("detail") == "Возраст должен быть 18+", r.text

    # Valid DOB must still update.
    r = requests.put(f"{BASE_URL}/api/profile", headers=headers, json={"dob": "1998-05-15"}, timeout=15)
    assert_status(r, 200, "accept 1998-05-15 dob")
    assert r.json().get("dob") == "1998-05-15", r.text

    # A 17-year-old as of July 2026 must be rejected.
    r = requests.put(f"{BASE_URL}/api/profile", headers=headers, json={"dob": "2009-01-01"}, timeout=15)
    assert_status(r, 400, "reject 2009-01-01 dob")
    assert r.json().get("detail") == "Возраст должен быть 18+", r.text

    # Partial update without dob must not trigger the age gate.
    about = f"Partial update no dob {ts}"
    r = requests.put(f"{BASE_URL}/api/profile", headers=headers, json={"about": about}, timeout=15)
    assert_status(r, 200, "partial update without dob")
    body = r.json()
    assert body.get("about") == about, r.text
    assert body.get("dob") == "1998-05-15", r.text

    print("PASS", {"email": email, "age_gate": "verified", "partial_update": "verified"})


if __name__ == "__main__":
    main()