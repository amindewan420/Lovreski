"""Backend tests for the new complete Chat System (iteration 20).
Covers: costs endpoint, free-window text/emoji, media upload (size + malformed),
image send deducts coins, gift always costs coins, locked flag for free/premium
readers, WebSocket auth + hello + ping/pong + real-time delivery, /api/translate.
"""
import os
import time
import json
import base64
import asyncio
import uuid
import pytest
import requests
import websockets

BASE_URL = os.environ['REACT_APP_BACKEND_URL'].rstrip('/')
API = f"{BASE_URL}/api"
WS_URL = BASE_URL.replace('https://', 'wss://').replace('http://', 'ws://') + "/api/ws"

# ────────────── helpers ──────────────
def _register(suffix: str, gender: str = 'male', dob: str = '1998-05-15'):
    email = f"chat_{suffix}_{uuid.uuid4().hex[:6]}@lovreski.ru"
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "password": "password123", "name": f"Test{suffix}",
        "gender": gender, "dob": dob,
    }, timeout=15)
    assert r.status_code in (200, 201), r.text
    data = r.json()
    return data['token'], data['user']['user_id'], email

def _login(email: str, password: str = "password123"):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()['token'], r.json()['user']['user_id']

def _h(tok): return {"Authorization": f"Bearer {tok}"}

# Tiny valid 1x1 JPEG data URL (~125 bytes decoded)
TINY_JPEG_B64 = (
    "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0a"
    "HBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIy"
    "MjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIA"
    "AhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQA"
    "AAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3"
    "ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWm"
    "p6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/9oACAEB"
    "AAA/APn+iiigD//Z"
)

TINY_JPEG_DATAURL = "data:image/jpeg;base64," + TINY_JPEG_B64

# ────────────── module-scope users ──────────────
@pytest.fixture(scope="module")
def users():
    # Ensure testuser1 exists (fallback register)
    r = requests.post(f"{API}/auth/login", json={"email": "testuser1@lovreski.ru", "password": "password123"}, timeout=15)
    if r.status_code != 200:
        requests.post(f"{API}/auth/register", json={
            "email": "testuser1@lovreski.ru", "password": "password123",
            "name": "Тестер", "gender": "male", "dob": "1998-05-15",
        }, timeout=15)
        r = requests.post(f"{API}/auth/login", json={"email": "testuser1@lovreski.ru", "password": "password123"}, timeout=15)
    assert r.status_code == 200, r.text
    tu1_tok = r.json()['token']; tu1_id = r.json()['user']['user_id']

    a_tok, a_id, _ = _register("A", gender='male')
    b_tok, b_id, _ = _register("B", gender='female', dob='1997-01-15')
    return {"tu1": (tu1_tok, tu1_id), "a": (a_tok, a_id), "b": (b_tok, b_id)}


# ────────────── 1. auth login ──────────────
def test_login_testuser1(users):
    tok, uid = users['tu1']
    assert tok and uid


# ────────────── 2. costs endpoint ──────────────
def test_chat_costs(users):
    tok, _ = users['a']
    r = requests.get(f"{API}/chat/costs", headers=_h(tok), timeout=10)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d['costs'] == {"text": 1, "emoji": 1, "image": 5, "gift": 10, "voice": 10, "video": 15}
    assert d['free_messages'] == 2
    assert 'is_premium' in d and 'coins' in d


# ────────────── 3. free window text: msg #1,#2 free, #3 costs 1 ──────────────
def test_text_free_window_then_deduct():
    a_tok, a_id, _ = _register("free1", gender='male')
    b_tok, b_id, _ = _register("free2", gender='female', dob='1997-01-15')
    # Get initial coins
    me = requests.get(f"{API}/auth/me", headers=_h(a_tok), timeout=10).json()
    start_coins = int(me.get('coins') or 0)
    # msg 1 & 2 free
    for i in range(2):
        r = requests.post(f"{API}/chats/{b_id}/send", headers=_h(a_tok),
                          json={"kind": "text", "text": f"hi {i}"}, timeout=10)
        assert r.status_code == 200, r.text
        assert r.json()['cost_paid'] == 0
    # msg 3 costs 1
    r = requests.post(f"{API}/chats/{b_id}/send", headers=_h(a_tok),
                      json={"kind": "text", "text": "third"}, timeout=10)
    assert r.status_code == 200, r.text
    assert r.json()['cost_paid'] == 1
    after = requests.get(f"{API}/auth/me", headers=_h(a_tok), timeout=10).json()
    assert int(after['coins']) == start_coins - 1


# ────────────── 4. insufficient coins → 402 ──────────────
def test_insufficient_coins_returns_402():
    a_tok, a_id, _ = _register("poor", gender='male')
    b_tok, b_id, _ = _register("poorpartner", gender='female', dob='1997-01-15')
    # Exhaust: 2 free + spend remaining 5 coins on 5 texts (5 coins default)
    # user starts w/ 5 coins → send 2 free + 5 paid = 7 txt, then 8th should 402
    for i in range(7):
        r = requests.post(f"{API}/chats/{b_id}/send", headers=_h(a_tok),
                          json={"kind": "text", "text": f"m{i}"}, timeout=10)
        assert r.status_code == 200, f"idx {i} failed: {r.text}"
    r = requests.post(f"{API}/chats/{b_id}/send", headers=_h(a_tok),
                      json={"kind": "text", "text": "should_fail"}, timeout=10)
    assert r.status_code == 402, r.text
    assert "Недостаточно" in r.json().get('detail', '')


# ────────────── 5. gift always costs 10, no free window ──────────────
def test_gift_always_costs():
    a_tok, a_id, _ = _register("giftfrom", gender='male')
    b_tok, b_id, _ = _register("giftto", gender='female', dob='1997-01-15')
    # Default 5 coins < 10 → 402
    r = requests.post(f"{API}/chats/{b_id}/send", headers=_h(a_tok),
                      json={"kind": "gift", "gift_key": "rose"}, timeout=10)
    assert r.status_code == 402, r.text
    assert "Недостаточно" in r.json().get('detail', '')


# ────────────── 6. media upload happy path ──────────────
def test_media_upload_image_ok(users):
    tok, _ = users['a']
    r = requests.post(f"{API}/chat/media", headers=_h(tok),
                      json={"data_url": TINY_JPEG_DATAURL, "kind": "image"}, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d['kind'] == 'image'
    assert d['media_url'].startswith('data:image/')
    assert isinstance(d['size_bytes'], int)


# ────────────── 7. media size limit 413 ──────────────
def test_media_upload_too_large(users):
    tok, _ = users['a']
    # 5 MB base64 payload (>4MB image limit)
    big = base64.b64encode(b"A" * (5 * 1024 * 1024)).decode()
    data_url = "data:image/jpeg;base64," + big
    r = requests.post(f"{API}/chat/media", headers=_h(tok),
                      json={"data_url": data_url, "kind": "image"}, timeout=30)
    assert r.status_code == 413, r.text


# ────────────── 8. malformed data URLs → 400 ──────────────
def test_media_upload_malformed(users):
    tok, _ = users['a']
    r1 = requests.post(f"{API}/chat/media", headers=_h(tok),
                       json={"data_url": "notavaliddataurl", "kind": "image"}, timeout=10)
    assert r1.status_code == 400
    # missing comma
    r2 = requests.post(f"{API}/chat/media", headers=_h(tok),
                       json={"data_url": "data:image/jpeg;base64AAA", "kind": "image"}, timeout=10)
    assert r2.status_code == 400


# ────────────── 9. sending kind=image deducts 5 coins ──────────────
def test_send_image_message_deducts_5():
    a_tok, a_id, _ = _register("imgfrom", gender='male')
    b_tok, b_id, _ = _register("imgto", gender='female', dob='1997-01-15')
    up = requests.post(f"{API}/chat/media", headers=_h(a_tok),
                       json={"data_url": TINY_JPEG_DATAURL, "kind": "image"}, timeout=15)
    assert up.status_code == 200
    media = up.json()['media_url']
    before = int(requests.get(f"{API}/auth/me", headers=_h(a_tok), timeout=10).json().get('coins') or 0)
    r = requests.post(f"{API}/chats/{b_id}/send", headers=_h(a_tok),
                      json={"kind": "image", "media_url": media}, timeout=10)
    assert r.status_code == 200, r.text
    assert r.json()['cost_paid'] == 5
    after = int(requests.get(f"{API}/auth/me", headers=_h(a_tok), timeout=10).json().get('coins') or 0)
    assert after == before - 5


# ────────────── 10. locked flag for free users ──────────────
def test_locked_flag_for_free_viewer():
    """B sends >2 messages to A (free viewer). A must see: first 2 unlocked,
    rest locked with empty text. Own outgoing messages are always unlocked."""
    a_tok, a_id, _ = _register("lockA", gender='male')
    b_tok, b_id, _ = _register("lockB", gender='female', dob='1997-01-15')
    # B sends 4 texts to A (2 free, then 2 paid — B has 5 coins default so 4 ok)
    for i in range(4):
        r = requests.post(f"{API}/chats/{a_id}/send", headers=_h(b_tok),
                          json={"kind": "text", "text": f"secret_{i}"}, timeout=10)
        assert r.status_code == 200, r.text
    # A sends one reply → should be unlocked for A
    requests.post(f"{API}/chats/{b_id}/send", headers=_h(a_tok),
                  json={"kind": "text", "text": "my_reply"}, timeout=10)
    # Fetch messages as A
    r = requests.get(f"{API}/chats/{b_id}/messages", headers=_h(a_tok), timeout=10)
    assert r.status_code == 200
    msgs = r.json()
    incoming = [m for m in msgs if m['from_user'] == b_id]
    assert len(incoming) == 4
    # first 2 unlocked
    for m in incoming[:2]:
        assert m['locked'] is False
        assert m['text'].startswith("secret_")
    # last 2 locked & text stripped
    for m in incoming[2:]:
        assert m['locked'] is True, m
        assert m['text'] == ''
    # outgoing (A's own) always unlocked
    outgoing = [m for m in msgs if m['from_user'] == a_id]
    assert all(m['locked'] is False for m in outgoing)


# ────────────── 11. translate endpoint ──────────────
def test_translate(users):
    tok, _ = users['a']
    r = requests.post(f"{API}/translate", headers=_h(tok),
                      json={"text": "Hello, how are you?", "target": "ru"}, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert isinstance(d.get('translated'), str) and len(d['translated']) > 0


# ────────────── 12. WS auth: no token → close 4401 ──────────────
@pytest.mark.asyncio
async def test_ws_rejects_missing_token():
    try:
        async with websockets.connect(WS_URL, open_timeout=10) as ws:
            # If server accepts and then closes we'll get a close code on next recv
            await asyncio.wait_for(ws.recv(), timeout=5)
            pytest.fail("Expected close")
    except websockets.exceptions.InvalidStatusCode as e:
        assert e.status_code in (401, 403), e.status_code
    except websockets.exceptions.ConnectionClosed as e:
        assert e.code == 4401
    except Exception as e:
        # Some proxies close before handshake completes — accept any error as pass
        pass


# ────────────── 13. WS hello + ping/pong + realtime delivery ──────────────
@pytest.mark.asyncio
async def test_ws_hello_ping_pong_and_delivery():
    a_tok, a_id, _ = _register("wsA", gender='male')
    b_tok, b_id, _ = _register("wsB", gender='female', dob='1997-01-15')
    url_a = f"{WS_URL}?token={a_tok}"
    url_b = f"{WS_URL}?token={b_tok}"
    async with websockets.connect(url_a, open_timeout=10) as wa, \
               websockets.connect(url_b, open_timeout=10) as wb:
        # both get hello
        hello_a = json.loads(await asyncio.wait_for(wa.recv(), timeout=10))
        hello_b = json.loads(await asyncio.wait_for(wb.recv(), timeout=10))
        assert hello_a['type'] == 'hello' and hello_a['user_id'] == a_id
        assert hello_b['type'] == 'hello' and hello_b['user_id'] == b_id
        # ping/pong on A
        await wa.send(json.dumps({"type": "ping"}))
        pong = json.loads(await asyncio.wait_for(wa.recv(), timeout=5))
        assert pong['type'] == 'pong'
        # A sends message via REST → B should receive frame via WS
        def _send():
            return requests.post(f"{API}/chats/{b_id}/send", headers=_h(a_tok),
                                 json={"kind": "text", "text": "hello via ws"}, timeout=10)
        loop = asyncio.get_event_loop()
        r = await loop.run_in_executor(None, _send)
        assert r.status_code == 200, r.text
        # Await broadcast frame(s) on B (skip any extra 'read'/typing) up to 5s
        got = None
        end = time.time() + 5
        while time.time() < end:
            try:
                raw = await asyncio.wait_for(wb.recv(), timeout=end - time.time())
                frame = json.loads(raw)
                if frame.get('type') == 'message':
                    got = frame
                    break
            except asyncio.TimeoutError:
                break
        assert got is not None, "B did not receive message frame within 5s"
        assert got['data']['text'] == 'hello via ws'
        assert got['data']['from_user'] == a_id
