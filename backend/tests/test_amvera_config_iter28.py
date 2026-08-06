"""Iteration 28 — Amvera Docker build fix: yarn.lock is now OPTIONAL.

Fixes the user's Amvera error:
    lstat /workspace/frontend/yarn.lock: no such file or directory

Root cause: Dockerfile did `COPY frontend/package.json frontend/yarn.lock ./`
(hard-required lockfile). User's Git initial commit did not include yarn.lock.

Fix under test:
  - `COPY frontend/yarn.lock* ./` (wildcard — file optional).
  - `RUN yarn install` (no --frozen-lockfile — resolves fine with or without).

Also (regression) re-checks iter 27's meta.toolchain block and main.py import.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import requests
import yaml

REPO = Path("/app")
DOCKERFILE = REPO / "Dockerfile"
AMVERA = REPO / "amvera.yaml"
FE = REPO / "frontend"


# ── Dockerfile: lockfile-less friendliness ──────────────────────────────────
@pytest.fixture(scope="module")
def dockerfile_text() -> str:
    return DOCKERFILE.read_text()


def test_dockerfile_copies_yarn_lock_with_wildcard(dockerfile_text: str):
    """The wildcard makes yarn.lock optional. Without it, the exact error the
    user hit ('lstat .../yarn.lock: no such file or directory') would return."""
    # Must NOT have a bare `COPY frontend/yarn.lock ./` line (hard-required).
    hard_required = re.search(r"^\s*COPY\s+frontend/yarn\.lock\s+", dockerfile_text, re.M)
    assert hard_required is None, "Dockerfile still hard-requires yarn.lock (no wildcard)"
    # Must have the wildcard form.
    wildcard = re.search(r"^\s*COPY\s+frontend/yarn\.lock\*\s+\./", dockerfile_text, re.M)
    assert wildcard is not None, "Dockerfile missing `COPY frontend/yarn.lock* ./` wildcard line"


def test_dockerfile_yarn_install_not_frozen(dockerfile_text: str):
    """--frozen-lockfile would abort the build if no lockfile is present."""
    install_lines = [l for l in dockerfile_text.splitlines()
                     if re.search(r"\byarn\s+install\b", l)]
    assert install_lines, "no `yarn install` line found in Dockerfile"
    for line in install_lines:
        assert "--frozen-lockfile" not in line, (
            f"`--frozen-lockfile` present in `{line.strip()}` — would fail without yarn.lock"
        )


def test_dockerfile_copies_package_json_before_source(dockerfile_text: str):
    """package.json must be copied BEFORE `COPY frontend/ ./` so layer cache works."""
    idx_pkg = dockerfile_text.find("COPY frontend/package.json")
    idx_src = dockerfile_text.find("COPY frontend/ ./")
    assert idx_pkg != -1
    assert idx_src != -1
    assert idx_pkg < idx_src


# ── Regression: iter 27 config still intact ─────────────────────────────────
def test_amvera_meta_toolchain_still_docker():
    manifest = yaml.safe_load(AMVERA.read_text())
    meta = manifest.get("meta", {})
    assert meta.get("environment") == "docker"
    assert meta.get("toolchain", {}).get("name") == "docker"
    assert meta.get("toolchain", {}).get("version") == "latest"


def test_backend_main_still_imports():
    r = subprocess.run(
        ["python", "-c", "import main; assert main.app; print(len(main.app.routes))"],
        cwd=str(REPO / "backend"), capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, f"stdout={r.stdout}\nstderr={r.stderr}"
    assert int(r.stdout.strip()) > 10


# ── Simulated Amvera clone WITHOUT yarn.lock ────────────────────────────────
def _run_yarn_install(workdir: Path, timeout: int = 480) -> subprocess.CompletedProcess:
    """Mirror the Dockerfile's `yarn install --network-timeout 600000` but with
    --ignore-scripts (skip postinstall for speed) and offline preference (cache
    is populated from the app's own install — same registry the Dockerfile hits)."""
    env = os.environ.copy()
    env["CI"] = "false"
    return subprocess.run(
        ["yarn", "install", "--ignore-scripts", "--network-timeout", "600000",
         "--prefer-offline", "--no-progress", "--non-interactive"],
        cwd=str(workdir), capture_output=True, text=True, timeout=timeout, env=env,
    )


@pytest.fixture(scope="module")
def scratch_no_lockfile(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("fe_no_lock")
    shutil.copy(FE / "package.json", d / "package.json")
    assert not (d / "yarn.lock").exists()
    return d


@pytest.fixture(scope="module")
def scratch_with_lockfile(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("fe_with_lock")
    shutil.copy(FE / "package.json", d / "package.json")
    shutil.copy(FE / "yarn.lock", d / "yarn.lock")
    return d


def test_yarn_install_without_lockfile_succeeds(scratch_no_lockfile: Path):
    """Simulates Amvera cloning the repo WITHOUT yarn.lock (user's actual case)."""
    result = _run_yarn_install(scratch_no_lockfile)
    if result.returncode != 0:
        # Show tail of stderr for diagnostics
        tail = "\n".join((result.stderr or "").splitlines()[-40:])
        pytest.fail(f"yarn install (no lockfile) failed rc={result.returncode}\n{tail}")
    assert (scratch_no_lockfile / "node_modules").is_dir(), "node_modules not created"
    assert (scratch_no_lockfile / "yarn.lock").is_file(), (
        "yarn should generate yarn.lock after resolving from package.json"
    )


def test_yarn_install_with_lockfile_succeeds(scratch_with_lockfile: Path):
    """Simulates the alternative — user commits the lockfile."""
    result = _run_yarn_install(scratch_with_lockfile)
    if result.returncode != 0:
        tail = "\n".join((result.stderr or "").splitlines()[-40:])
        pytest.fail(f"yarn install (with lockfile) failed rc={result.returncode}\n{tail}")
    assert (scratch_with_lockfile / "node_modules").is_dir()


# ── Regression: preview backend /api/health ─────────────────────────────────
def test_api_health_regression():
    base = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
    if not base:
        env_file = (REPO / "frontend" / ".env").read_text()
        for line in env_file.splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                base = line.split("=", 1)[1].strip().rstrip("/")
                break
    r = requests.get(f"{base}/api/health", timeout=15)
    assert r.status_code == 200, r.text
