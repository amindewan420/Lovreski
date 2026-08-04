"""Iteration 21 – Telegram-style chat redesign backend tests.
Covers: /api/gifts (18 gifts), /api/i18n/{base,en,fr,de,xx}, /api/chat/status/{other_id},
per-gift-cost sends, free-user hard-block (402 blocked=true), /api/chat/media file kind,
PUT /api/profile language_pref, WebSocket regression.
"""
import os
import time
import json
import asyncio
import uuid
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL')
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"
BASE_URL = BASE_URL.rstrip('/')
API = f"{BASE_URL}/api"


def _rand():
    return uuid.uuid4().hex[:8]


def _register(coins_needed=None):
    email = f"iter21_{_rand()}@lovreski.ru"
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "password": "password123", "name": "Iter21",
        "gender": "male", "dob": "1998-05-15",
    }, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"], r.json()["user"]["user_id"], email


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def user_a():
    tok, uid, email = _register()
    return {"token": tok, "user_id": uid, "email": email}


@pytest.fixture(scope="module")
def user_b():
    tok, uid, email = _register()
    return {"token": tok, "user_id": uid, "email": email}


# ─── Gifts catalog ──────────────────────────────────────────────────────────
class TestGifts:
    def test_gifts_18_with_required_fields(self):
        r = requests.get(f"{API}/gifts", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) == 18, f"expected 18 gifts, got {len(data)}"
        required = {"key", "name", "emoji", "cost", "gradient"}
        for g in data:
            assert required <= set(g.keys()), f"gift missing keys: {g}"
            assert isinstance(g["cost"], int)
            assert 5 <= g["cost"] <= 30

    def test_gifts_specific_costs(self):
        r = requests.get(f"{API}/gifts", timeout=15).json()
        costs = {g["key"]: g["cost"] for g in r}
        assert costs["heart"] == 5
        assert costs["diamond"] == 20
        assert costs["yacht"] == 30


# ─── i18n endpoints ─────────────────────────────────────────────────────────
class TestI18n:
    def test_base_ru(self):
        r = requests.get(f"{API}/i18n/base", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["lang"] == "ru"
        strings = data["strings"]
        assert len(strings) >= 80, f"only {len(strings)} keys"
        for k in ("nav.home", "chat.title", "settings.language"):
            assert k in strings

    def test_i18n_ru_alias(self):
        r = requests.get(f"{API}/i18n/ru", timeout=15)
        assert r.status_code == 200
        assert r.json()["lang"] == "ru"

    def test_i18n_en_translates_and_caches(self):
        # first call may be slow (LLM). allow up to 60s.
        r = requests.get(f"{API}/i18n/en", timeout=90)
        assert r.status_code == 200
        data = r.json()
        assert data.get("lang") == "en", f"got: {data.get('lang')} error={data.get('error')}"
        strings = data["strings"]
        assert "chat.title" in strings
        chat_title = strings["chat.title"]
        assert chat_title and chat_title[0].upper().startswith("C"), f"chat.title={chat_title}"
        # second call: cached quickly
        t0 = time.time()
        r2 = requests.get(f"{API}/i18n/en", timeout=15)
        elapsed = time.time() - t0
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2.get("cached") is True
        assert elapsed < 3.0, f"cached call took {elapsed:.2f}s"

    def test_i18n_fr_and_de(self):
        for lang in ("fr", "de"):
            r = requests.get(f"{API}/i18n/{lang}", timeout=90)
            assert r.status_code == 200
            data = r.json()
            # fail-open falls back to ru with error present. Accept either but
            # at least require 'strings' with the required keys.
            assert "strings" in data
            assert "chat.title" in data["strings"]

    def test_i18n_invalid_lang_no_500(self):
        r = requests.get(f"{API}/i18n/xx", timeout=90)
        assert r.status_code == 200, r.text
        data = r.json()
        # fallback path: lang may be 'ru' with error, or a best-effort 'xx'
        assert "strings" in data


# ─── /api/chat/status ───────────────────────────────────────────────────────
class TestChatStatus:
    def test_status_shape(self, user_a, user_b):
        r = requests.get(f"{API}/chat/status/{user_b['user_id']}", headers=_auth(user_a["token"]), timeout=15)
        assert r.status_code == 200
        data = r.json()
        for k in ("chat_id", "sent_count", "free_used", "free_limit", "coins", "is_premium", "is_blocked"):
            assert k in data
        assert data["free_limit"] == 2
        assert isinstance(data["is_blocked"], bool)


# ─── Send: free window + per-gift cost + block ──────────────────────────────
class TestSendCostsAndBlock:
    def test_free_then_gift_costs_by_key(self):
        # fresh user gets 5 default coins. Send: free msg1 text, free msg2 text,
        # then gift 'heart' (5 coins) should succeed and drop to 0. Then a
        # 'diamond' (20) should 402 blocked=true.
        tok_s, uid_s, _ = _register()
        tok_r, uid_r, _ = _register()
        # msg1 free (text)
        r1 = requests.post(f"{API}/chats/{uid_r}/send", headers=_auth(tok_s),
                           json={"kind": "text", "text": "hi 1"}, timeout=15)
        assert r1.status_code == 200
        assert r1.json()["cost_paid"] == 0
        # msg2 free (emoji, any kind counts)
        r2 = requests.post(f"{API}/chats/{uid_r}/send", headers=_auth(tok_s),
                           json={"kind": "emoji", "text": "😀"}, timeout=15)
        assert r2.status_code == 200
        assert r2.json()["cost_paid"] == 0
        # msg3 gift heart (5 coins deducted)
        r3 = requests.post(f"{API}/chats/{uid_r}/send", headers=_auth(tok_s),
                           json={"kind": "gift", "gift_key": "heart"}, timeout=15)
        assert r3.status_code == 200, r3.text
        assert r3.json()["cost_paid"] == 5
        # now coins should be 0. Diamond (20) → 402 blocked
        r4 = requests.post(f"{API}/chats/{uid_r}/send", headers=_auth(tok_s),
                           json={"kind": "gift", "gift_key": "diamond"}, timeout=15)
        assert r4.status_code == 402, r4.text
        detail = r4.json().get("detail")
        assert isinstance(detail, dict), f"detail must be dict, got: {detail!r}"
        assert detail.get("blocked") is True
        # text also blocked
        r5 = requests.post(f"{API}/chats/{uid_r}/send", headers=_auth(tok_s),
                           json={"kind": "text", "text": "please"}, timeout=15)
        assert r5.status_code == 402
        assert isinstance(r5.json().get("detail"), dict)

    def test_third_text_deducts_one(self):
        tok_s, uid_s, _ = _register()
        tok_r, uid_r, _ = _register()
        for i in range(2):
            requests.post(f"{API}/chats/{uid_r}/send", headers=_auth(tok_s),
                          json={"kind": "text", "text": f"free {i}"}, timeout=15)
        r = requests.post(f"{API}/chats/{uid_r}/send", headers=_auth(tok_s),
                          json={"kind": "text", "text": "paid"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["cost_paid"] == 1

    def test_emoji_after_free_costs_2(self):
        tok_s, uid_s, _ = _register()
        tok_r, uid_r, _ = _register()
        for i in range(2):
            requests.post(f"{API}/chats/{uid_r}/send", headers=_auth(tok_s),
                          json={"kind": "text", "text": f"free {i}"}, timeout=15)
        r = requests.post(f"{API}/chats/{uid_r}/send", headers=_auth(tok_s),
                          json={"kind": "emoji", "text": "😍"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["cost_paid"] == 2

    def test_gift_yacht_30_needs_topup(self):
        tok_s, uid_s, _ = _register()
        tok_r, uid_r, _ = _register()
        # consume free
        for i in range(2):
            requests.post(f"{API}/chats/{uid_r}/send", headers=_auth(tok_s),
                          json={"kind": "text", "text": f"free {i}"}, timeout=15)
        # yacht costs 30; user has 5 coins → 402
        r = requests.post(f"{API}/chats/{uid_r}/send", headers=_auth(tok_s),
                          json={"kind": "gift", "gift_key": "yacht"}, timeout=15)
        assert r.status_code == 402
        assert r.json()["detail"].get("required") == 30

    def test_invalid_gift_key_400(self):
        tok_s, uid_s, _ = _register()
        tok_r, uid_r, _ = _register()
        r = requests.post(f"{API}/chats/{uid_r}/send", headers=_auth(tok_s),
                          json={"kind": "gift", "gift_key": "nonsense_xyz"}, timeout=15)
        assert r.status_code == 400

    def test_file_kind_5_coins_after_free(self):
        tok_s, uid_s, _ = _register()
        tok_r, uid_r, _ = _register()
        for i in range(2):
            requests.post(f"{API}/chats/{uid_r}/send", headers=_auth(tok_s),
                          json={"kind": "text", "text": f"free {i}"}, timeout=15)
        # File kind: 5 coins. Fresh user has 5.
        r = requests.post(f"{API}/chats/{uid_r}/send", headers=_auth(tok_s),
                          json={"kind": "file", "media_url": "data:application/pdf;base64,AAAA", "file_name": "spec.pdf"}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["cost_paid"] == 5
        assert r.json().get("file_name") == "spec.pdf"


# ─── /api/chat/media file kind ──────────────────────────────────────────────
class TestChatMedia:
    def test_upload_file_kind(self, user_a):
        payload = {
            "data_url": "data:application/pdf;base64,SGVsbG8gV29ybGQ=",
            "kind": "file",
            "file_name": "hello.pdf",
        }
        r = requests.post(f"{API}/chat/media", headers=_auth(user_a["token"]), json=payload, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["kind"] == "file"
        assert data["media_url"].startswith("data:application/pdf")
        assert data.get("file_name") == "hello.pdf"

    def test_upload_voice_video_non_image(self, user_a):
        for kind, mime in (("voice", "audio/webm"), ("video", "video/mp4")):
            payload = {"data_url": f"data:{mime};base64,SGVsbG8=", "kind": kind}
            r = requests.post(f"{API}/chat/media", headers=_auth(user_a["token"]), json=payload, timeout=15)
            assert r.status_code == 200, r.text
            assert r.json()["kind"] == kind


# ─── PUT /api/profile language_pref ─────────────────────────────────────────
class TestProfileLanguage:
    def test_set_language_pref(self):
        tok, uid, _ = _register()
        r = requests.put(f"{API}/profile", headers=_auth(tok), json={"language_pref": "en"}, timeout=15)
        assert r.status_code == 200, r.text
        u = r.json()
        assert u.get("language_pref") == "en"
        # persistence via GET /auth/me
        r2 = requests.get(f"{API}/auth/me", headers=_auth(tok), timeout=15)
        assert r2.status_code == 200
        assert r2.json().get("language_pref") == "en"


# ─── WebSocket regression ───────────────────────────────────────────────────
class TestWebSocket:
    def test_ws_ping_pong_and_broadcast(self):
        import websockets
        tok_a, uid_a, _ = _register()
        tok_b, uid_b, _ = _register()
        ws_base = BASE_URL.replace("https://", "wss://").replace("http://", "ws://")

        async def run():
            async with websockets.connect(f"{ws_base}/api/ws?token={tok_b}", open_timeout=15, close_timeout=5) as ws:
                hello = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                assert hello.get("type") == "hello"
                await ws.send(json.dumps({"type": "ping"}))
                pong = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                assert pong.get("type") == "pong"
                # user A sends to B via REST
                requests.post(f"{API}/chats/{uid_b}/send", headers=_auth(tok_a),
                              json={"kind": "text", "text": "ws hello"}, timeout=15)
                deadline = time.time() + 8
                got_msg = False
                while time.time() < deadline:
                    try:
                        evt = json.loads(await asyncio.wait_for(ws.recv(), timeout=3))
                    except asyncio.TimeoutError:
                        break
                    if evt.get("type") == "message" and evt.get("data", {}).get("text") == "ws hello":
                        got_msg = True
                        break
                assert got_msg, "did not receive broadcast message on WS"

        asyncio.run(run())
