#!/usr/bin/env python3
"""Focused backend auth regression checks for iteration 3."""

import json
import os
import random
import time
from pathlib import Path

import requests


BASE_URL = os.environ.get("BACKEND_BASE_URL", "https://lovreski-dating.preview.emergentagent.com/api").rstrip("/")
RESULT_PATH = Path("/app/test_reports/auth_backend_reverify_iteration3_results.json")


def post(path, payload):
    return requests.post(f"{BASE_URL}{path}", json=payload, timeout=20)


def main():
    stamp = int(time.time())
    email = f"bugretest_{stamp}_{random.randint(1000, 9999)}@lovreski.ru"
    password = "password123"
    register_payload = {
        "email": email,
        "password": password,
        "name": "Bug Retest",
        "gender": "male",
        "dob": "1998-05-15",
    }
    unknown_email = f"unknown_{stamp}_{random.randint(1000, 9999)}@lovreski.ru"

    checks = []

    def record(name, response, expected_status, expected_detail=None, expect_token=False):
        try:
            body = response.json()
        except Exception:
            body = {"raw": response.text}
        ok = response.status_code == expected_status
        if expected_detail is not None:
            ok = ok and body.get("detail") == expected_detail
        if expect_token:
            ok = ok and bool(body.get("token")) and body.get("user", {}).get("email") == email
        checks.append({
            "name": name,
            "status": response.status_code,
            "expected_status": expected_status,
            "body": body,
            "expected_detail": expected_detail,
            "passed": ok,
        })
        if not ok:
            raise AssertionError(f"{name} failed: status={response.status_code}, body={body}")
        return body

    reg_body = record("register_new_user", post("/auth/register", register_payload), 200, expect_token=True)
    record("duplicate_register", post("/auth/register", register_payload), 409, "Email already exists")
    login_body = record("login_correct_password", post("/auth/login", {"email": email, "password": password}), 200, expect_token=True)
    record("login_wrong_password", post("/auth/login", {"email": email, "password": "wrongpass123"}), 401, "Incorrect password")
    record("login_unknown_email", post("/auth/login", {"email": unknown_email, "password": password}), 404, "Account not found. Please sign up first.")

    # Extra user-outcome proof: token from correct login can authenticate /auth/me.
    me_resp = requests.get(
        f"{BASE_URL}/auth/me",
        headers={"Authorization": f"Bearer {login_body['token']}"},
        timeout=20,
    )
    try:
        me_body = me_resp.json()
    except Exception:
        me_body = {"raw": me_resp.text}
    me_ok = me_resp.status_code == 200 and me_body.get("email") == email and me_body.get("user_id") == reg_body["user"]["user_id"]
    checks.append({
        "name": "auth_me_with_login_token",
        "status": me_resp.status_code,
        "expected_status": 200,
        "body": me_body,
        "passed": me_ok,
    })
    if not me_ok:
        raise AssertionError(f"auth_me_with_login_token failed: status={me_resp.status_code}, body={me_body}")

    result = {"base_url": BASE_URL, "created_email": email, "checks": checks, "all_passed": all(c["passed"] for c in checks)}
    RESULT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()