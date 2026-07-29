#!/usr/bin/env python3
"""Focused backend verification for Lovreski auth bug."""
import json
import os
import random
import re
import sys
import time
from pathlib import Path

import requests
from pymongo import MongoClient


ROOT = Path("/app")


def parse_env(path: Path):
    data = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        data[k] = v.strip().strip('"').strip("'")
    return data


def expect(condition, message, details=None):
    if not condition:
        raise AssertionError(f"{message}: {details}")


def main():
    frontend_env = parse_env(ROOT / "frontend" / ".env")
    backend_env = parse_env(ROOT / "backend" / ".env")
    base = frontend_env["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
    mongo_url = backend_env["MONGO_URL"]
    db_name = backend_env["DB_NAME"]
    stamp = f"{int(time.time())}_{random.randint(1000,9999)}"
    email = f"bugtest_{stamp}@lovreski.ru"
    unknown_email = f"unknown_{stamp}@lovreski.ru"
    password = "password123"
    wrong_password = "wrongpass123"
    register_payload = {
        "email": email,
        "password": password,
        "name": "Bug Test User",
        "gender": "female",
        "dob": "1998-05-15",
    }
    session = requests.Session()
    results = {
        "api_base": base,
        "email": email,
        "checks": [],
    }

    # Clean just in case a random collision occurred.
    mongo = MongoClient(mongo_url)
    db = mongo[db_name]
    db.users.delete_many({"email": {"$in": [email.lower(), unknown_email.lower()]}})

    # New registration succeeds and returns token + user.
    r = session.post(f"{base}/auth/register", json=register_payload, timeout=20)
    results["checks"].append({"name": "new_registration", "status": r.status_code, "body": r.json() if r.content else None})
    expect(r.status_code == 200, "new registration should return HTTP 200", r.text)
    body = r.json()
    expect(bool(body.get("token")), "registration response should include token", body)
    expect(body.get("user", {}).get("email") == email.lower(), "registration response should include user email", body)
    expect("password_hash" not in body.get("user", {}), "registration response should not expose password_hash", body)

    # User is persisted with password hash and expected user_id.
    persisted = db.users.find_one({"email": email.lower()}, {"_id": 0})
    safe_persisted = dict(persisted or {})
    if "password_hash" in safe_persisted:
        safe_persisted["password_hash"] = "<present>"
    results["checks"].append({"name": "mongo_persistence", "found": bool(persisted), "doc": safe_persisted})
    expect(persisted is not None, "registered user should be persisted in MongoDB", None)
    expect(persisted.get("user_id") == body["user"]["user_id"], "Mongo user_id should match response user_id", safe_persisted)
    expect(bool(persisted.get("password_hash")) and persisted.get("password_hash") != password, "Mongo should store password hash, not plaintext", safe_persisted)

    # Duplicate registration returns exact English detail.
    r_dup = session.post(f"{base}/auth/register", json=register_payload, timeout=20)
    dup_body = r_dup.json() if r_dup.content else {}
    results["checks"].append({"name": "duplicate_registration", "status": r_dup.status_code, "body": dup_body})
    expect(r_dup.status_code == 409, "duplicate registration should return HTTP 409", r_dup.text)
    expect(dup_body.get("detail") == "Email already exists", "duplicate detail should be exact English string", dup_body)
    expect("wrong email or password" not in json.dumps(dup_body).lower(), "duplicate should not show generic wrong email/password", dup_body)

    # Correct login succeeds with token + user.
    r_login = session.post(f"{base}/auth/login", json={"email": email, "password": password}, timeout=20)
    login_body = r_login.json() if r_login.content else {}
    results["checks"].append({"name": "correct_login", "status": r_login.status_code, "body": login_body})
    expect(r_login.status_code == 200, "correct login should return HTTP 200", r_login.text)
    expect(bool(login_body.get("token")), "login response should include token", login_body)
    expect(login_body.get("user", {}).get("email") == email.lower(), "login response should include user email", login_body)

    # Wrong password returns exact English detail.
    r_wrong = session.post(f"{base}/auth/login", json={"email": email, "password": wrong_password}, timeout=20)
    wrong_body = r_wrong.json() if r_wrong.content else {}
    results["checks"].append({"name": "wrong_password", "status": r_wrong.status_code, "body": wrong_body})
    expect(r_wrong.status_code == 401, "wrong password should return HTTP 401", r_wrong.text)
    expect(wrong_body.get("detail") == "Incorrect password", "wrong password detail should be exact English string", wrong_body)
    expect("wrong email or password" not in json.dumps(wrong_body).lower(), "wrong password should not show generic wrong email/password", wrong_body)

    # Unknown email returns friendly not-found detail, not generic.
    r_unknown = session.post(f"{base}/auth/login", json={"email": unknown_email, "password": password}, timeout=20)
    unknown_body = r_unknown.json() if r_unknown.content else {}
    results["checks"].append({"name": "unknown_email", "status": r_unknown.status_code, "body": unknown_body})
    expect(r_unknown.status_code == 404, "unknown email should return HTTP 404", r_unknown.text)
    expect(unknown_body.get("detail") == "Account not found. Please sign up first.", "unknown email detail should be friendly string", unknown_body)
    expect("wrong email or password" not in json.dumps(unknown_body).lower(), "unknown email should not show generic wrong email/password", unknown_body)

    out_path = ROOT / "test_reports" / "auth_backend_results.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(json.dumps({"ok": True, "results_path": str(out_path), "email": email}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise