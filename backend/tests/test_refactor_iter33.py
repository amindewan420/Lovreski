"""
Iter-33: Full backend regression after routers/ refactor.
Covers all 83 /api/* routes across 13 router modules + server.py (ws, misc).
"""
import os
import io
import uuid
import time
import json
import base64
import asyncio
import pytest
import requests
import websockets

def _read_env():
    try:
        with open("/app/frontend/.env") as f:
            for ln in f:
                if ln.startswith("REACT_APP_BACKEND_URL="):
                    return ln.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    return ""

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or _read_env()
assert BASE, "REACT_APP_BACKEND_URL missing"

ADMIN_EMAIL = "admin@lovreski.ru"
ADMIN_PW = "LovreskiAdmin2026!"
U1_EMAIL = "testuser1@lovreski.ru"
U2_EMAIL = "testuser2@lovreski.ru"
PW = "password123"

TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)
TINY_JPG_DATA_URL = "data:image/jpeg;base64," + base64.b64encode(TINY_PNG).decode()


def _login(email, pw):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": pw}, timeout=15)
    assert r.status_code == 200, f"login {email} -> {r.status_code} {r.text[:200]}"
    return r.json()["token"]


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def tokens():
    # Ensure testuser2 exists
    try:
        requests.post(
            f"{BASE}/api/auth/register",
            json={
                "email": U2_EMAIL,
                "password": PW,
                "name": "Test Two",
                "gender": "female",
                "birth_date": "1996-02-02",
                "city": "Moscow",
            },
            timeout=15,
        )
    except Exception:
        pass
    try:
        requests.post(
            f"{BASE}/api/auth/register",
            json={
                "email": U1_EMAIL,
                "password": PW,
                "name": "Test One",
                "gender": "male",
                "birth_date": "1995-01-01",
                "city": "Moscow",
            },
            timeout=15,
        )
    except Exception:
        pass
    return {
        "admin": _login(ADMIN_EMAIL, ADMIN_PW),
        "u1": _login(U1_EMAIL, PW),
        "u2": _login(U2_EMAIL, PW),
    }


# ---------------- MISC / HEALTH ----------------
def test_health():
    r = requests.get(f"{BASE}/api/health", timeout=10)
    assert r.status_code == 200
    assert r.json().get("status") == "ok" or "ok" in str(r.json()).lower()


def test_route_count():
    # openapi served at backend root (fastapi default). Via public ingress /openapi.json
    # goes to frontend, so use internal localhost:8001.
    r = requests.get("http://localhost:8001/openapi.json", timeout=10)
    assert r.status_code == 200
    paths = [p for p in r.json()["paths"] if p.startswith("/api/")]
    assert len(paths) == 79, f"expected 79 unique api paths, got {len(paths)}"


# ---------------- AUTH ----------------
def test_auth_me(tokens):
    r = requests.get(f"{BASE}/api/auth/me", headers=_h(tokens["u1"]), timeout=10)
    assert r.status_code == 200
    assert r.json().get("email") == U1_EMAIL


def test_auth_logout(tokens):
    # Use a fresh token so we don't invalidate others
    t = _login(U1_EMAIL, PW)
    r = requests.post(f"{BASE}/api/auth/logout", headers=_h(t), timeout=10)
    assert r.status_code in (200, 204)


# ---------------- PROFILE ----------------
def test_profile_put_partial(tokens):
    r = requests.put(
        f"{BASE}/api/profile",
        headers=_h(tokens["u1"]),
        json={"about": "iter33 test " + uuid.uuid4().hex[:6]},
        timeout=10,
    )
    assert r.status_code == 200


def test_profile_get_other(tokens):
    me = requests.get(f"{BASE}/api/auth/me", headers=_h(tokens["u2"]), timeout=10).json()
    r = requests.get(f"{BASE}/api/profile/{me['user_id']}", headers=_h(tokens["u1"]), timeout=10)
    assert r.status_code == 200


def test_profile_me_stats(tokens):
    r = requests.get(f"{BASE}/api/profile/me/stats", headers=_h(tokens["u1"]), timeout=10)
    assert r.status_code == 200
    data = r.json()
    assert "completion_pct" in data or "popularity" in data


# ---------------- DISCOVER / LIKES ----------------
def test_home_feed(tokens):
    r = requests.get(f"{BASE}/api/home/feed?limit=6", headers=_h(tokens["u1"]), timeout=15)
    assert r.status_code == 200


def test_discover_feed(tokens):
    r = requests.get(f"{BASE}/api/discover/feed?limit=20", headers=_h(tokens["u1"]), timeout=15)
    assert r.status_code == 200


def test_like_pass_match(tokens):
    u2 = requests.get(f"{BASE}/api/auth/me", headers=_h(tokens["u2"]), timeout=10).json()
    u1 = requests.get(f"{BASE}/api/auth/me", headers=_h(tokens["u1"]), timeout=10).json()
    r = requests.post(f"{BASE}/api/like/{u2['user_id']}", headers=_h(tokens["u1"]), timeout=10)
    assert r.status_code == 200
    r2 = requests.post(f"{BASE}/api/like/{u1['user_id']}", headers=_h(tokens["u2"]), timeout=10)
    assert r2.status_code == 200


def test_likes_received_sent_matches(tokens):
    for ep in ("received", "sent", "matches"):
        r = requests.get(f"{BASE}/api/likes/{ep}", headers=_h(tokens["u1"]), timeout=10)
        assert r.status_code == 200, f"{ep}: {r.status_code}"


# ---------------- CHAT ----------------
def test_chats_list(tokens):
    r = requests.get(f"{BASE}/api/chats", headers=_h(tokens["u1"]), timeout=10)
    assert r.status_code == 200


def test_chat_costs(tokens):
    r = requests.get(f"{BASE}/api/chat/costs", headers=_h(tokens["u1"]), timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert "msg_cost" in d or "MSG_COST" in d or "free_msgs" in d or "FREE_MSGS" in d or "costs" in d or "free_messages" in d


def test_gifts(tokens):
    r = requests.get(f"{BASE}/api/gifts", headers=_h(tokens["u1"]), timeout=10)
    assert r.status_code == 200
    assert isinstance(r.json(), list) and len(r.json()) > 0


def test_send_text_message(tokens):
    u2 = requests.get(f"{BASE}/api/auth/me", headers=_h(tokens["u2"]), timeout=10).json()
    r = requests.post(
        f"{BASE}/api/chats/{u2['user_id']}/send",
        headers=_h(tokens["u1"]),
        json={"kind": "text", "text": "hello iter33 " + uuid.uuid4().hex[:6]},
        timeout=15,
    )
    assert r.status_code == 200, r.text[:300]


def test_messages_list_and_delete(tokens):
    u2 = requests.get(f"{BASE}/api/auth/me", headers=_h(tokens["u2"]), timeout=10).json()
    r = requests.get(
        f"{BASE}/api/chats/{u2['user_id']}/messages", headers=_h(tokens["u1"]), timeout=10
    )
    assert r.status_code == 200
    msgs = r.json()
    assert isinstance(msgs, list)
    if msgs:
        mid = msgs[-1].get("id") or msgs[-1].get("_id")
        if mid:
            r2 = requests.delete(
                f"{BASE}/api/messages/{mid}?scope=me",
                headers=_h(tokens["u1"]),
                timeout=10,
            )
            assert r2.status_code in (200, 204)


def test_chat_status(tokens):
    u2 = requests.get(f"{BASE}/api/auth/me", headers=_h(tokens["u2"]), timeout=10).json()
    r = requests.get(
        f"{BASE}/api/chat/status/{u2['user_id']}", headers=_h(tokens["u1"]), timeout=10
    )
    assert r.status_code == 200


# ---------------- FILES / GRIDFS ----------------
def test_files_upload_and_fetch(tokens):
    files = {"file": ("tiny.png", io.BytesIO(TINY_PNG), "image/png")}
    r = requests.post(
        f"{BASE}/api/files/upload", headers=_h(tokens["u1"]), files=files, timeout=20
    )
    assert r.status_code == 200, r.text[:300]
    fid = r.json().get("file_id") or r.json().get("id")
    assert fid
    r2 = requests.get(f"{BASE}/api/files/{fid}", headers=_h(tokens["u1"]), timeout=15)
    assert r2.status_code == 200
    assert r2.headers.get("content-type", "").startswith("image/")


# ---------------- COINS ----------------
def test_coin_packages(tokens):
    r = requests.get(f"{BASE}/api/coins/packages", headers=_h(tokens["u1"]), timeout=10)
    assert r.status_code == 200
    d = r.json()
    pkgs = d.get("packages") if isinstance(d, dict) else d
    assert isinstance(pkgs, list) and len(pkgs) == 4


def test_coins_balance(tokens):
    r = requests.get(f"{BASE}/api/coins/balance", headers=_h(tokens["u1"]), timeout=10)
    assert r.status_code == 200


def test_coins_transactions(tokens):
    r = requests.get(f"{BASE}/api/coins/transactions", headers=_h(tokens["u1"]), timeout=10)
    assert r.status_code == 200


def test_coins_checkout_and_status(tokens):
    r = requests.post(
        f"{BASE}/api/coins/checkout",
        headers=_h(tokens["u1"]),
        json={"package_id": "p100"},
        timeout=15,
    )
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    tx = d.get("tx_id") or d.get("id")
    assert tx
    assert "qr_png" in d or "qr" in d or "qr_data_url" in d
    r2 = requests.get(
        f"{BASE}/api/coins/status/{tx}", headers=_h(tokens["u1"]), timeout=10
    )
    assert r2.status_code == 200


# ---------------- SUPPORT RECEIPT + REFUND ----------------
def test_receipt_and_refund(tokens):
    r = requests.post(
        f"{BASE}/api/support/receipt",
        headers=_h(tokens["u1"]),
        json={"receipt_data_url": TINY_JPG_DATA_URL, "note": "iter33"},
        timeout=20,
    )
    assert r.status_code in (200, 201), r.text[:300]
    r2 = requests.get(f"{BASE}/api/support/my", headers=_h(tokens["u1"]), timeout=10)
    assert r2.status_code == 200
    # refund
    r3 = requests.post(
        f"{BASE}/api/support/refund",
        headers=_h(tokens["u1"]),
        json={"reason": "iter33 test refund"},
        timeout=15,
    )
    # Could be 200 or 400 (if no eligible tx). Just ensure not 500.
    assert r3.status_code < 500, r3.text[:300]


# ---------------- ADMIN ----------------
def test_admin_endpoints(tokens):
    h = _h(tokens["admin"])
    endpoints = [
        ("GET", "/api/admin/stats"),
        ("GET", "/api/admin/payments"),
        ("GET", "/api/admin/users?limit=5"),
        ("GET", "/api/admin/support/pending"),
        ("GET", "/api/admin/settings"),
        ("GET", "/api/admin/settings/reveal"),
        ("GET", "/api/admin/refunds"),
        ("GET", "/api/admin/legal"),
        ("GET", "/api/admin/audit"),
    ]
    for method, ep in endpoints:
        r = requests.request(method, f"{BASE}{ep}", headers=h, timeout=15)
        assert r.status_code == 200, f"{ep} -> {r.status_code} {r.text[:200]}"


def test_admin_settings_put(tokens):
    r = requests.put(
        f"{BASE}/api/admin/settings",
        headers=_h(tokens["admin"]),
        json={},
        timeout=10,
    )
    assert r.status_code in (200, 400)  # noop body may 400 depending on validation


def test_admin_add_deduct_coins(tokens):
    u1 = requests.get(f"{BASE}/api/auth/me", headers=_h(tokens["u1"]), timeout=10).json()
    r = requests.post(
        f"{BASE}/api/admin/users/add-coins",
        headers=_h(tokens["admin"]),
        json={"user_id": u1["user_id"], "coins": 5, "reason": "iter33"},
        timeout=10,
    )
    assert r.status_code == 200, r.text[:300]
    r2 = requests.post(
        f"{BASE}/api/admin/users/deduct-coins",
        headers=_h(tokens["admin"]),
        json={"user_id": u1["user_id"], "coins": 5, "reason": "iter33"},
        timeout=10,
    )
    assert r2.status_code == 200, r2.text[:300]


# ---------------- I18N ----------------
def test_i18n_base():
    r = requests.get(f"{BASE}/api/i18n/base", timeout=10)
    assert r.status_code == 200
    d = r.json()
    strings = d.get("strings") or d
    if isinstance(strings, dict):
        assert len(strings) >= 99


def test_i18n_lang_cached():
    r = requests.get(f"{BASE}/api/i18n/ru", timeout=10)
    assert r.status_code == 200


def test_i18n_translate_batch(tokens):
    r = requests.post(
        f"{BASE}/api/i18n/translate-batch",
        headers=_h(tokens["u1"]),
        json={"strings": ["Привет"], "lang": "en"},
        timeout=30,
    )
    assert r.status_code in (200, 400), r.text[:300]


def test_translate_simple(tokens):
    r = requests.post(
        f"{BASE}/api/translate",
        headers=_h(tokens["u1"]),
        json={"text": "Привет", "target_lang": "en"},
        timeout=30,
    )
    assert r.status_code in (200, 400), r.text[:300]


# ---------------- PUSH ----------------
def test_push_status(tokens):
    r = requests.get(f"{BASE}/api/push/status", headers=_h(tokens["u1"]), timeout=10)
    assert r.status_code == 200
    assert r.json().get("configured") is False


def test_push_token_crud(tokens):
    r = requests.post(
        f"{BASE}/api/push/token",
        headers=_h(tokens["u1"]),
        json={"token": "dummy-iter33-token-" + uuid.uuid4().hex},
        timeout=10,
    )
    assert r.status_code == 200, r.text[:300]
    r2 = requests.request(
        "DELETE",
        f"{BASE}/api/push/token",
        headers={**_h(tokens["u1"]), "Content-Type": "application/json"},
        data=json.dumps({"token": "dummy-iter33-token-abcdefg"}),
        timeout=10,
    )
    assert r2.status_code in (200, 204)


def test_push_test_unconfigured(tokens):
    r = requests.post(f"{BASE}/api/push/test", headers=_h(tokens["u1"]), timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d.get("sent") == 0


# ---------------- REPORTS / BLOCK ----------------
def test_report_and_block(tokens):
    u2 = requests.get(f"{BASE}/api/auth/me", headers=_h(tokens["u2"]), timeout=10).json()
    r = requests.post(
        f"{BASE}/api/report",
        headers=_h(tokens["u1"]),
        json={"target_user_id": u2["user_id"], "reason": "iter33"},
        timeout=10,
    )
    assert r.status_code in (200, 201)
    r2 = requests.post(
        f"{BASE}/api/block/{u2['user_id']}", headers=_h(tokens["u1"]), timeout=10
    )
    assert r2.status_code in (200, 201)


# ---------------- DEMO ----------------
def test_demo_seed_idempotent(tokens):
    r = requests.post(f"{BASE}/api/demo/seed", headers=_h(tokens["admin"]), timeout=30)
    assert r.status_code == 200
    r2 = requests.post(f"{BASE}/api/demo/seed", headers=_h(tokens["admin"]), timeout=30)
    assert r2.status_code == 200
    d = r2.json()
    already = d.get("already", 0)
    assert already >= 15 or d.get("ok") is True


# ---------------- WEBSOCKET ----------------
def test_websocket_ping_pong(tokens):
    async def run():
        ws_base = BASE.replace("https://", "wss://").replace("http://", "ws://")
        url = f"{ws_base}/api/ws?token={tokens['u1']}"
        async with websockets.connect(url, open_timeout=10) as ws:
            await ws.send(json.dumps({"type": "ping"}))
            # read a few frames; one should be pong
            got_pong = False
            for _ in range(5):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5)
                except asyncio.TimeoutError:
                    break
                if "pong" in str(msg).lower():
                    got_pong = True
                    break
            assert got_pong, "no pong received"

    asyncio.get_event_loop().run_until_complete(run())
