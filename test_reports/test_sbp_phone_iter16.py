#!/usr/bin/env python3
"""Focused SBP recipient phone verification for bug-verification iteration 16."""
import json
import os
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests


ROOT = Path("/app")
REPORT_DIR = ROOT / "test_reports"
RESULT_PATH = REPORT_DIR / "sbp_phone_api_results_iter16.json"
CORRECT = "+79780369381"
WRONG = "+79783069381"


def read_env(path: Path) -> dict:
    env = {}
    if path.exists():
        for raw in path.read_text().splitlines():
            raw = raw.strip()
            if raw and not raw.startswith("#") and "=" in raw:
                k, v = raw.split("=", 1)
                env[k] = v.strip().strip('"').strip("'")
    return env


def req(method, url, **kwargs):
    r = requests.request(method, url, timeout=30, **kwargs)
    try:
        body = r.json()
    except Exception:
        body = r.text
    if r.status_code >= 400:
        raise AssertionError(f"{method} {url} failed {r.status_code}: {body}")
    return r, body


def assert_no_wrong_text(name: str, text: str):
    if WRONG in text:
        raise AssertionError(f"old wrong SBP phone {WRONG} still appears in {name}")


def main():
    frontend_env = read_env(ROOT / "frontend" / ".env")
    backend_env = read_env(ROOT / "backend" / ".env")
    base = os.environ.get("BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL") or "http://localhost:8001"
    base = base.rstrip("/")
    api = base + "/api"
    results = {"ok": False, "base_url": base, "checks": []}

    env_phone = backend_env.get("SBP_PHONE")
    assert env_phone == CORRECT, f"backend .env SBP_PHONE expected {CORRECT}, got {env_phone!r}"
    assert env_phone != WRONG, "backend .env still has old wrong phone"
    results["checks"].append({"name": "backend_env", "SBP_PHONE": env_phone})

    _, packages = req("GET", api + "/coins/packages")
    assert packages.get("sbp_phone") == CORRECT, f"/coins/packages returned {packages.get('sbp_phone')!r}"
    assert_no_wrong_text("/coins/packages JSON", json.dumps(packages, ensure_ascii=False))
    results["checks"].append({"name": "coins_packages", "sbp_phone": packages.get("sbp_phone")})

    _, login = req("POST", api + "/auth/login", json={
        "email": backend_env.get("ADMIN_EMAIL", "admin@lovreski.ru"),
        "password": backend_env.get("ADMIN_PASSWORD", "LovreskiAdmin2026!"),
    })
    token = login["token"]
    headers = {"Authorization": f"Bearer {token}"}
    results["checks"].append({"name": "admin_login", "is_admin": login.get("user", {}).get("is_admin")})

    _, settings = req("GET", api + "/admin/settings", headers=headers)
    assert settings.get("sbp_phone_last4") == "9381", f"admin last4 expected 9381, got {settings.get('sbp_phone_last4')!r}"
    masked = settings.get("sbp_phone_masked", "")
    assert masked.endswith("-81"), f"masked phone should expose corrected last two digits 81, got {masked!r}"
    assert_no_wrong_text("/admin/settings JSON", json.dumps(settings, ensure_ascii=False))
    results["checks"].append({"name": "admin_settings_masked", "sbp_phone_masked": masked, "last4": settings.get("sbp_phone_last4")})

    _, reveal = req("GET", api + "/admin/settings/reveal", headers=headers)
    assert reveal.get("sbp_phone") == CORRECT, f"admin reveal returned {reveal.get('sbp_phone')!r}"
    results["checks"].append({"name": "admin_settings_reveal", "sbp_phone": reveal.get("sbp_phone")})

    # Fetch frontend HTML and dev/compiled JS scripts exposed as /static/js/*.js.
    root_resp, root_html = req("GET", base + "/")
    assert_no_wrong_text("frontend index HTML", root_html if isinstance(root_html, str) else json.dumps(root_html))
    premium_resp, premium_html = req("GET", base + "/premium")
    premium_text = premium_html if isinstance(premium_html, str) else json.dumps(premium_html)
    assert_no_wrong_text("/premium route HTML", premium_text)
    script_paths = sorted(set(re.findall(r'<script[^>]+src=["\']([^"\']*?/static/js/[^"\']+\.js)["\']', root_resp.text)))
    js_checks = []
    for src in script_paths:
        script_url = urljoin(base + "/", src)
        _, js_text = req("GET", script_url)
        js_body = js_text if isinstance(js_text, str) else json.dumps(js_text)
        assert_no_wrong_text(f"JS bundle {urlparse(script_url).path}", js_body)
        js_checks.append({"path": urlparse(script_url).path, "contains_correct": CORRECT in js_body, "bytes": len(js_body)})
    results["checks"].append({"name": "frontend_static_html_and_js_no_old_phone", "script_count": len(script_paths), "scripts": js_checks})

    results["ok"] = True
    RESULT_PATH.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        failure = {"ok": False, "error": str(e), "correct": CORRECT, "wrong": WRONG}
        RESULT_PATH.write_text(json.dumps(failure, indent=2, ensure_ascii=False))
        print(json.dumps(failure, indent=2, ensure_ascii=False))
        raise