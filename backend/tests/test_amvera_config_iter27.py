"""Iteration 27 — Amvera deploy config verification (config-only + API smoke).

Validates:
  1) /app/amvera.yaml YAML syntax + required schema keys per Amvera Docker docs.
  2) Dockerfile CMD is uvicorn (Python), NOT node — no scripts/start.js.
  3) Dockerfile EXPOSE 8000 matches amvera.yaml run.containerPort=8000.
  4) All secrets used at server startup are declared in amvera.yaml env list.
  5) backend/main.py imports cleanly and exposes /health.
  6) Regression smoke: /api/health, /api/coins/packages, /api/discover/feed.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest
import requests
import yaml

REPO = Path("/app")
AMVERA = REPO / "amvera.yaml"
DOCKERFILE = REPO / "Dockerfile"
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback to frontend .env
    for line in (REPO / "frontend" / ".env").read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
            break


# ── amvera.yaml schema ──────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def manifest() -> dict:
    return yaml.safe_load(AMVERA.read_text())


def test_amvera_yaml_parses(manifest):
    assert isinstance(manifest, dict)


def test_meta_toolchain_docker(manifest):
    meta = manifest.get("meta", {})
    assert meta.get("environment") == "docker"
    tc = meta.get("toolchain", {})
    assert tc.get("name") == "docker", "meta.toolchain.name must be 'docker' so Amvera does not auto-detect Node.js"
    assert tc.get("version") == "latest"


def test_build_dockerfile_reference(manifest):
    build = manifest.get("build", {})
    dockerfile_rel = build.get("dockerfile", "Dockerfile")
    assert (REPO / dockerfile_rel).is_file(), f"Dockerfile at {dockerfile_rel} missing"
    assert build.get("skip") is False


def test_run_container_port_matches_expose(manifest):
    port = str(manifest.get("run", {}).get("containerPort"))
    assert port == "8000"
    exposed = re.findall(r"^EXPOSE\s+(\d+)", DOCKERFILE.read_text(), re.M)
    assert "8000" in exposed, f"Dockerfile EXPOSE lines: {exposed}"


def test_required_env_secrets_declared(manifest):
    envs = {e["name"]: e for e in manifest.get("env", [])}
    for key in ("MONGO_URL", "DB_NAME", "JWT_SECRET", "ADMIN_EMAIL",
                "ADMIN_PASSWORD", "CORS_ORIGINS", "SBP_PHONE", "SBP_ENCRYPT_KEY"):
        assert key in envs, f"env var {key} missing from amvera.yaml"
        assert envs[key].get("required") is True, f"{key} should be required=true"


# ── Dockerfile coherence ────────────────────────────────────────────────────
def test_dockerfile_cmd_is_uvicorn_not_node():
    text = DOCKERFILE.read_text()
    cmd_lines = [l for l in text.splitlines() if l.startswith("CMD")]
    assert cmd_lines, "no CMD in Dockerfile"
    cmd = cmd_lines[-1]  # last (runtime) CMD
    assert "uvicorn" in cmd, f"runtime CMD must be uvicorn, got: {cmd}"
    assert "node" not in cmd and "npm" not in cmd, f"runtime CMD must not be node/npm: {cmd}"
    assert "scripts/start.js" not in text, "Dockerfile must not reference scripts/start.js"


def test_dockerfile_has_python_runtime_stage():
    text = DOCKERFILE.read_text()
    assert "python:3.11-slim" in text
    assert "AS runtime" in text


# ── main.py import sanity ───────────────────────────────────────────────────
def test_backend_main_imports_cleanly():
    result = subprocess.run(
        ["python", "-c", "import main; assert main.app is not None; print(len(main.app.routes))"],
        cwd=str(REPO / "backend"),
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, f"main.py import failed:\nSTDOUT={result.stdout}\nSTDERR={result.stderr}"
    assert int(result.stdout.strip()) > 10


# ── Regression smoke against running preview backend ────────────────────────
def test_api_health():
    r = requests.get(f"{BASE_URL}/api/health", timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("status") in ("ok", "healthy", "up") or body.get("ok") is True, body


def test_api_coins_packages():
    r = requests.get(f"{BASE_URL}/api/coins/packages", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    # accept either list or {packages: [...]}
    pkgs = data if isinstance(data, list) else data.get("packages", [])
    assert isinstance(pkgs, list) and len(pkgs) > 0


def _login(email: str, password: str) -> str | None:
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": password}, timeout=15)
    if r.status_code != 200:
        return None
    j = r.json()
    return j.get("access_token") or j.get("token")


def test_api_discover_feed_with_test_user():
    token = _login("testuser1@lovreski.ru", "password123")
    if not token:
        pytest.skip("test user login failed; not blocking config testing")
    r = requests.get(f"{BASE_URL}/api/discover/feed",
                     headers={"Authorization": f"Bearer {token}"}, timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, (list, dict))
