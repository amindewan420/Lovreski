#!/usr/bin/env python3
"""Focused verification for Lovreski coin/SBP payment leak regression.

Checks the previously reported frontend bundle leak plus payment API regressions.
Writes machine-readable evidence to iteration8_api_results.json.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests


ROOT = Path("/app")
OUT = ROOT / "test_reports" / "scripts" / "iteration8_api_results.json"
RAW = "+79780369381"
RAW_DIGITS = "79780369381"


def read_env(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for line in path.read_text().splitlines():
        if not line or line.strip().startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        data[k.strip()] = v.strip().strip('"').strip("'")
    return data


frontend_env = read_env(ROOT / "frontend" / ".env")
backend_env = read_env(ROOT / "backend" / ".env")
BASE = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL") or "https://lovreski-dating.preview.emergentagent.com"
BASE = BASE.rstrip("/")
API = f"{BASE}/api"


class CheckFailure(AssertionError):
    pass


results: dict[str, object] = {"base_url": BASE, "checks": []}


def record(name: str, ok: bool, detail: object = None):
    results["checks"].append({"name": name, "ok": ok, "detail": detail})
    print(("PASS" if ok else "FAIL") + f" {name}: {detail}")


def assert_no_raw(text: str, label: str, allow_phone_patterns: bool = False):
    if RAW in text or RAW_DIGITS in text:
        raise CheckFailure(f"{label} contains {RAW_DIGITS}")
    if not allow_phone_patterns and re.search(r"\+7\d{10}", text):
        raise CheckFailure(f"{label} contains a raw +7 phone pattern")


def req(method: str, path: str, token: str | None = None, **kwargs) -> requests.Response:
    headers = kwargs.pop("headers", {}) or {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = requests.request(method, f"{API}{path}", headers=headers, timeout=20, **kwargs)
    return r


def register(prefix: str = "leaktest") -> tuple[str, dict]:
    email = f"{prefix}_{int(time.time() * 1000)}_{os.getpid()}@lovreski.ru"
    payload = {
        "email": email,
        "password": "password123",
        "name": "Leak Tester",
        "gender": "male",
        "dob": "1998-05-15",
    }
    r = req("POST", "/auth/register", json=payload)
    if r.status_code not in (200, 201):
        raise CheckFailure(f"register failed {r.status_code}: {r.text}")
    return r.json()["token"], r.json()["user"]


def admin_login() -> str:
    r = req("POST", "/auth/login", json={"email": "admin@lovreski.ru", "password": "LovreskiAdmin2026!"})
    if r.status_code != 200:
        raise CheckFailure(f"admin login failed {r.status_code}: {r.text}")
    return r.json()["token"]


def check_static_js_bundle():
    root = requests.get(BASE + "/", timeout=20)
    if root.status_code != 200:
        raise CheckFailure(f"front page not reachable: {root.status_code}")
    script_paths = set(re.findall(r'<script[^>]+src=["\']([^"\']*/static/js/[^"\']+\.js(?:\?[^"\']*)?)["\']', root.text))
    # CRA dev server commonly exposes this even when the root HTML has minimal script tags.
    for fallback in ("/static/js/bundle.js", "/static/js/main.chunk.js", "/static/js/vendors~main.chunk.js"):
        script_paths.add(fallback)
    fetched = []
    for src in sorted(script_paths):
        url = urljoin(BASE + "/", src)
        resp = requests.get(url, timeout=30)
        if resp.status_code == 404:
            continue
        if resp.status_code != 200:
            raise CheckFailure(f"{url} returned {resp.status_code}")
        assert_no_raw(resp.text, url, allow_phone_patterns=True)
        fetched.append({"url": url, "bytes": len(resp.text)})
    if not fetched:
        raise CheckFailure("No /static/js/*.js assets could be fetched")
    return fetched


def check_api_flow():
    token, user = register("leaktest_api")
    admin = admin_login()

    packages = requests.get(f"{API}/coins/packages", timeout=20)
    if packages.status_code != 200:
        raise CheckFailure(f"packages status {packages.status_code}: {packages.text}")
    assert_no_raw(packages.text, "GET /coins/packages")
    pkgs = packages.json()["packages"]
    p50 = next((p for p in pkgs if p.get("id") == "p50"), None)
    if not p50 or p50.get("popular") is not True:
        raise CheckFailure("p50 popular badge flag missing")

    checkout = req("POST", "/coins/checkout", token, json={"package_id": "p10"})
    if checkout.status_code != 200:
        raise CheckFailure(f"checkout status {checkout.status_code}: {checkout.text}")
    assert_no_raw(checkout.text, "POST /coins/checkout")
    cbody = checkout.json()
    if not cbody.get("sbp_link", "").startswith("https://qr.nspk.ru/pay"):
        raise CheckFailure(f"bad sbp_link: {cbody.get('sbp_link')}")
    if "sum=30000" not in cbody["sbp_link"]:
        raise CheckFailure(f"amount missing from sbp_link: {cbody['sbp_link']}")
    if not cbody.get("qr_png", "").startswith("data:image/png;base64,"):
        raise CheckFailure("qr_png is not a base64 data URL")

    b0 = req("GET", "/coins/balance", token).json()["coins"]
    pay = req("POST", "/coins/checkout", token, json={"package_id": "p25"})
    if pay.status_code != 200:
        raise CheckFailure(f"second checkout failed: {pay.status_code} {pay.text}")
    tx_id = pay.json()["tx_id"]
    pending = req("GET", f"/coins/status/{tx_id}", token)
    if pending.status_code != 200 or pending.json()["transaction"]["status"] != "pending":
        raise CheckFailure(f"status did not start pending: {pending.status_code} {pending.text}")
    time.sleep(10)
    success = req("GET", f"/coins/status/{tx_id}", token)
    if success.status_code != 200:
        raise CheckFailure(f"success poll failed: {success.status_code} {success.text}")
    sbody = success.json()
    if sbody["transaction"]["status"] != "success" or sbody["coins"] != b0 + 25:
        raise CheckFailure(f"status did not auto-confirm and credit once: before={b0}, body={sbody}")
    balances = []
    for _ in range(3):
        again = req("GET", f"/coins/status/{tx_id}", token).json()
        balances.append(again["coins"])
    if any(v != b0 + 25 for v in balances):
        raise CheckFailure(f"double-credit/idempotence failure: {balances}")

    rate_token, _ = register("leaktest_rate")
    codes = [req("POST", "/coins/checkout", rate_token, json={"package_id": "p10"}).status_code for _ in range(6)]
    if codes[:5] != [200, 200, 200, 200, 200] or codes[5] != 429:
        raise CheckFailure(f"rate limit did not enforce 5/hour: {codes}")

    settings = req("GET", "/admin/settings", admin)
    if settings.status_code != 200:
        raise CheckFailure(f"admin settings failed: {settings.status_code} {settings.text}")
    assert_no_raw(settings.text, "GET /admin/settings")
    if "***" not in settings.json().get("sbp_phone_masked", ""):
        raise CheckFailure(f"masked admin phone missing: {settings.text}")

    reveal = req("GET", "/admin/settings/reveal", admin)
    if reveal.status_code != 200 or not reveal.json().get("sbp_phone", "").startswith("+7"):
        raise CheckFailure(f"admin reveal failed: {reveal.status_code} {reveal.text}")
    raw_phone = reveal.json()["sbp_phone"]

    non_admin_settings = req("GET", "/admin/settings", token)
    if non_admin_settings.status_code != 403:
        raise CheckFailure(f"non-admin settings expected 403, got {non_admin_settings.status_code}")

    webhook = requests.post(f"{API}/coins/webhook", json={"tx_id": "fake", "status": "success", "amount_rub": 300, "bank": "Sberbank"}, timeout=20)
    if webhook.status_code != 401:
        raise CheckFailure(f"webhook without secret expected 401, got {webhook.status_code}")

    db_detail = check_db_security(raw_phone=raw_phone, tx_id=cbody["tx_id"])
    return {"registered_user": user["email"], "status_tx_id": tx_id, "rate_limit_codes": codes, "db": db_detail}


def check_db_security(raw_phone: str, tx_id: str) -> dict:
    try:
        from pymongo import MongoClient  # type: ignore
    except Exception as exc:
        return {"skipped": f"pymongo unavailable: {exc}"}
    mongo_url = backend_env.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = backend_env.get("DB_NAME", "test_database")
    client = MongoClient(mongo_url, serverSelectionTimeoutMS=3000)
    db = client[db_name]
    setting = db.settings.find_one({"key": "app"}, {"_id": 0}) or {}
    enc = setting.get("sbp_phone_enc", "")
    if not enc or enc == raw_phone or raw_phone in enc:
        raise CheckFailure("SBP phone is not encrypted/masked in db.settings.sbp_phone_enc")
    tx = db.transactions.find_one({"tx_id": tx_id}, {"_id": 0}) or {}
    if "ip" not in tx or not tx.get("ip"):
        raise CheckFailure(f"transaction {tx_id} missing ip log")
    if raw_phone in json.dumps(tx, ensure_ascii=False):
        raise CheckFailure(f"raw SBP phone leaked in transaction {tx_id}")
    return {"settings_encrypted": True, "tx_ip_logged": True, "tx_id": tx_id}


def main() -> int:
    failures: list[str] = []
    for name, func in (("static_js_bundle_no_raw_phone", check_static_js_bundle), ("payment_api_regression", check_api_flow)):
        try:
            detail = func()
            record(name, True, detail)
        except Exception as exc:  # noqa: BLE001 - test harness wants all evidence
            failures.append(f"{name}: {exc}")
            record(name, False, str(exc))
    results["ok"] = not failures
    results["failures"] = failures
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())