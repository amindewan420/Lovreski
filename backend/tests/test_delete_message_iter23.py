"""Iter 23 — Delete Message backend tests."""
import os
import asyncio
import json
import uuid
import time
from datetime import datetime, timedelta, timezone

import pytest
import requests
import websockets

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
API = f"{BASE_URL}/api"
WS_URL = BASE_URL.replace('https://', 'wss://').replace('http://', 'ws://') + '/api/ws'

# Credentials
U1 = {"email": "testuser1@lovreski.ru", "password": "password123"}
ADMIN = {"email": "admin@lovreski.ru", "password": "LovreskiAdmin2026!"}
U2_EMAIL = f"deltest2_{uuid.uuid4().hex[:6]}@lovreski.ru"
U2 = {"email": U2_EMAIL, "password": "password123", "name": "DelTest2",
      "gender": "male", "dob": "1996-06-06"}


# ────── Fixtures ──────
@pytest.fixture(scope="module")
def s():
    return requests.Session()


def _login(s, creds):
    r = s.post(f"{API}/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()


def _register(s, body):
    r = s.post(f"{API}/auth/register", json=body, timeout=15)
    assert r.status_code in (200, 201), f"register failed: {r.status_code} {r.text}"
    return r.json()


@pytest.fixture(scope="module")
def u1(s):
    data = _login(s, U1)
    # Grant coins to u1 for sending
    try:
        from pymongo import MongoClient
        mc = MongoClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017'))
        db = mc[os.environ.get('DB_NAME', 'test_database')]
        db.users.update_one({"user_id": data['user']['user_id']}, {"$set": {"coins": 500, "is_premium": True}})
    except Exception as e:
        print(f"coin grant failed: {e}")
    return data


@pytest.fixture(scope="module")
def u2(s):
    data = _register(s, U2)
    try:
        from pymongo import MongoClient
        mc = MongoClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017'))
        db = mc[os.environ.get('DB_NAME', 'test_database')]
        db.users.update_one({"user_id": data['user']['user_id']}, {"$set": {"coins": 500, "is_premium": True}})
    except Exception:
        pass
    return data


@pytest.fixture(scope="module")
def admin(s):
    return _login(s, ADMIN)


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


def _send(s, tok, other_id, text="hi", kind="text", **extra):
    body = {"text": text, "kind": kind, **extra}
    r = s.post(f"{API}/chats/{other_id}/send", json=body, headers=_h(tok), timeout=15)
    assert r.status_code == 200, f"send failed: {r.status_code} {r.text}"
    return r.json()


def _list(s, tok, other_id):
    r = s.get(f"{API}/chats/{other_id}/messages", headers=_h(tok), timeout=15)
    assert r.status_code == 200
    return r.json()


# ────── scope=me ──────
def test_delete_me_hides_only_for_caller(s, u1, u2):
    msg = _send(s, u1['token'], u2['user']['user_id'], text=f"TEST_me_{uuid.uuid4().hex[:6]}")
    mid = msg['message_id']
    r = s.delete(f"{API}/messages/{mid}?scope=me", headers=_h(u1['token']))
    assert r.status_code == 200
    body = r.json()
    assert body['ok'] is True and body['scope'] == 'me'
    # u1 no longer sees it
    ids1 = [m['message_id'] for m in _list(s, u1['token'], u2['user']['user_id'])]
    assert mid not in ids1
    # u2 still sees it
    ids2 = [m['message_id'] for m in _list(s, u2['token'], u1['user']['user_id'])]
    assert mid in ids2


def test_delete_me_idempotent(s, u1, u2):
    msg = _send(s, u1['token'], u2['user']['user_id'], text="TEST_idem")
    mid = msg['message_id']
    r1 = s.delete(f"{API}/messages/{mid}?scope=me", headers=_h(u1['token']))
    r2 = s.delete(f"{API}/messages/{mid}?scope=me", headers=_h(u1['token']))
    assert r1.status_code == 200 and r2.status_code == 200


def test_delete_me_partner_message_allowed(s, u1, u2):
    # u2 sends, u1 hides for himself
    msg = _send(s, u2['token'], u1['user']['user_id'], text="TEST_partner")
    mid = msg['message_id']
    r = s.delete(f"{API}/messages/{mid}?scope=me", headers=_h(u1['token']))
    assert r.status_code == 200


# ────── scope=everyone ──────
def test_delete_everyone_tombstones_for_both(s, u1, u2):
    msg = _send(s, u1['token'], u2['user']['user_id'], text=f"TEST_everyone_{uuid.uuid4().hex[:6]}")
    mid = msg['message_id']
    r = s.delete(f"{API}/messages/{mid}?scope=everyone", headers=_h(u1['token']))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {"ok": True, "scope": "everyone", "message_id": mid} or body.get("ok") is True
    # both viewers see deleted=true with cleared fields
    for tok, other in [(u1['token'], u2['user']['user_id']), (u2['token'], u1['user']['user_id'])]:
        msgs = _list(s, tok, other)
        found = [m for m in msgs if m['message_id'] == mid]
        assert found, f"deleted message missing for viewer"
        m = found[0]
        assert m['deleted'] is True
        assert m.get('text', '') == ''
        assert m.get('media_url') in (None, '')


def test_delete_everyone_sender_only(s, u1, u2):
    msg = _send(s, u1['token'], u2['user']['user_id'], text="TEST_sender")
    mid = msg['message_id']
    # u2 tries to delete u1's message
    r = s.delete(f"{API}/messages/{mid}?scope=everyone", headers=_h(u2['token']))
    assert r.status_code == 403


def test_delete_everyone_1hr_window(s, u1, u2, admin):
    # Fabricate old message directly via API then patch created_at via mongo? We don't have mongo here.
    # Alternate: send normally, then via admin, override created_at using debug endpoint if exists.
    # Fall back to direct mongo via pymongo.
    from pymongo import MongoClient
    mc = MongoClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017'))
    db = mc[os.environ.get('DB_NAME', 'test_database')]

    msg = _send(s, u1['token'], u2['user']['user_id'], text="TEST_old")
    mid = msg['message_id']
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat().replace('+00:00', 'Z')
    db.messages.update_one({"message_id": mid}, {"$set": {"created_at": old}})

    # Sender (non-admin) forbidden
    r = s.delete(f"{API}/messages/{mid}?scope=everyone", headers=_h(u1['token']))
    assert r.status_code == 403

    # Admin bypasses
    r2 = s.delete(f"{API}/messages/{mid}?scope=everyone", headers=_h(admin['token']))
    assert r2.status_code == 200, r2.text


def test_delete_media_url_cleared(s, u1, u2):
    msg = _send(s, u1['token'], u2['user']['user_id'], text="", kind="image",
                media_url="https://example.com/img.png")
    mid = msg['message_id']
    r = s.delete(f"{API}/messages/{mid}?scope=everyone", headers=_h(u1['token']))
    assert r.status_code == 200
    msgs = _list(s, u2['token'], u1['user']['user_id'])
    m = [x for x in msgs if x['message_id'] == mid][0]
    assert m['deleted'] is True
    assert m.get('media_url') in (None, '')


def test_bogus_id_returns_404(s, u1):
    r = s.delete(f"{API}/messages/bogus-{uuid.uuid4().hex}?scope=me", headers=_h(u1['token']))
    assert r.status_code == 404


def test_invalid_scope_returns_400(s, u1, u2):
    msg = _send(s, u1['token'], u2['user']['user_id'], text="TEST_scope")
    mid = msg['message_id']
    r = s.delete(f"{API}/messages/{mid}?scope=nuke", headers=_h(u1['token']))
    assert r.status_code == 400


def test_reply_to_deleted(s, u1, u2):
    a = _send(s, u1['token'], u2['user']['user_id'], text="TEST_reply_parent")
    b = _send(s, u1['token'], u2['user']['user_id'], text="TEST_reply_child", reply_to=a['message_id'])
    r = s.delete(f"{API}/messages/{a['message_id']}?scope=everyone", headers=_h(u1['token']))
    assert r.status_code == 200
    msgs = _list(s, u2['token'], u1['user']['user_id'])
    parent = [m for m in msgs if m['message_id'] == a['message_id']][0]
    assert parent['deleted'] is True and parent.get('text', '') == ''


# ────── WebSocket ──────
def test_ws_broadcast_deletion(s, u1, u2):
    """u2's ws should receive message_deleted when u1 deletes everyone."""

    async def run():
        u2_tok = u2['token']
        received = []
        async with websockets.connect(f"{WS_URL}?token={u2_tok}", open_timeout=10) as ws:
            # consume hello
            hello = await asyncio.wait_for(ws.recv(), timeout=5)
            assert 'hello' in hello

            # u1 sends message
            msg = _send(s, u1['token'], u2['user']['user_id'], text=f"TEST_ws_{uuid.uuid4().hex[:6]}")
            mid = msg['message_id']

            # Delete for everyone
            r = s.delete(f"{API}/messages/{mid}?scope=everyone", headers=_h(u1['token']))
            assert r.status_code == 200

            # Poll ws for up to 3s
            deadline = time.time() + 4
            while time.time() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.5)
                    data = json.loads(raw)
                    received.append(data)
                    if data.get('type') == 'message_deleted' and data.get('data', {}).get('message_id') == mid:
                        return data
                except asyncio.TimeoutError:
                    continue
        return None

    result = asyncio.run(run())
    assert result is not None, "no message_deleted WS frame received"
    assert result['data']['scope'] == 'everyone'
