"""Iter 46 — per-user 'delete for me' (sent+received), bulk delete, list_chats hidden behaviour."""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv('/app/backend/.env')
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
API = f"{BASE_URL}/api"
A = {"email": "match_a@lovreski.ru", "password": "password123"}
B = {"email": "match_b@lovreski.ru", "password": "password123"}
C = {"email": "testuser1@lovreski.ru", "password": "password123"}

mdb = MongoClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]


def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    mdb.users.update_one({"user_id": d['user']['user_id']}, {"$inc": {"coins": 50}})
    return d['token'], d['user']['user_id']


def H(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def ctx():
    ta, ua = _login(A)
    tb, ub = _login(B)
    tc, uc = _login(C)
    return dict(ta=ta, ua=ua, tb=tb, ub=ub, tc=tc, uc=uc)


def send(tok, other, text):
    r = requests.post(f"{API}/chats/{other}/send", json={"text": text, "kind": "text"}, headers=H(tok), timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    return d.get('message_id') or d.get('message', {}).get('message_id')


def ids_visible(tok, other):
    r = requests.get(f"{API}/chats/{other}/messages", headers=H(tok), timeout=15)
    assert r.status_code == 200
    return {m['message_id']: m for m in r.json()}


# --- single delete scope=me by receiver ---
def test_receiver_delete_for_me(ctx):
    mid = send(ctx['tb'], ctx['ua'], f"TEST_recv_{uuid.uuid4().hex[:5]}")
    assert mid
    r = requests.delete(f"{API}/messages/{mid}?scope=me", headers=H(ctx['ta']))
    assert r.status_code == 200, r.text
    assert mid not in ids_visible(ctx['ta'], ctx['ub'])
    assert mid in ids_visible(ctx['tb'], ctx['ua'])  # sender still sees it


def test_receiver_cannot_delete_everyone(ctx):
    mid = send(ctx['tb'], ctx['ua'], "TEST_recv_ev")
    r = requests.delete(f"{API}/messages/{mid}?scope=everyone", headers=H(ctx['ta']))
    assert r.status_code == 403


# --- bulk ---
def test_bulk_me_mixed(ctx):
    a1 = send(ctx['ta'], ctx['ub'], "TEST_bulk_a1")
    b1 = send(ctx['tb'], ctx['ua'], "TEST_bulk_b1")
    r = requests.post(f"{API}/messages/delete-bulk", json={"message_ids": [a1, b1], "scope": "me"}, headers=H(ctx['ta']))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d['ok'] is True and d['deleted'] == 2
    va = ids_visible(ctx['ta'], ctx['ub'])
    assert a1 not in va and b1 not in va
    vb = ids_visible(ctx['tb'], ctx['ua'])
    assert a1 in vb and b1 in vb


def test_bulk_everyone_own_fresh(ctx):
    a1 = send(ctx['ta'], ctx['ub'], "TEST_ev_a1")
    a2 = send(ctx['ta'], ctx['ub'], "TEST_ev_a2")
    r = requests.post(f"{API}/messages/delete-bulk", json={"message_ids": [a1, a2], "scope": "everyone"}, headers=H(ctx['ta']))
    assert r.status_code == 200, r.text
    assert r.json()['deleted'] == 2
    for tok, other in ((ctx['ta'], ctx['ub']), (ctx['tb'], ctx['ua'])):
        v = ids_visible(tok, other)
        assert v[a1]['deleted'] is True and v[a1]['text'] == ''
        assert v[a2]['deleted'] is True


def test_bulk_everyone_mixed_403_atomic(ctx):
    a1 = send(ctx['ta'], ctx['ub'], "TEST_atomic_a1")
    b1 = send(ctx['tb'], ctx['ua'], "TEST_atomic_b1")
    r = requests.post(f"{API}/messages/delete-bulk", json={"message_ids": [a1, b1], "scope": "everyone"}, headers=H(ctx['ta']))
    assert r.status_code == 403
    v = ids_visible(ctx['tb'], ctx['ua'])
    assert not v[a1].get('deleted') and v[a1]['text'] == "TEST_atomic_a1"


def test_bulk_everyone_too_old_403_atomic(ctx):
    a1 = send(ctx['ta'], ctx['ub'], "TEST_old_a1")
    a2 = send(ctx['ta'], ctx['ub'], "TEST_old_a2")
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    mdb.messages.update_one({"message_id": a2}, {"$set": {"created_at": old}})
    r = requests.post(f"{API}/messages/delete-bulk", json={"message_ids": [a1, a2], "scope": "everyone"}, headers=H(ctx['ta']))
    assert r.status_code == 403
    m = mdb.messages.find_one({"message_id": a1})
    assert not m.get('deleted')


def test_bulk_unknown_404(ctx):
    a1 = send(ctx['ta'], ctx['ub'], "TEST_unk")
    r = requests.post(f"{API}/messages/delete-bulk", json={"message_ids": [a1, "msg_nope_xyz"], "scope": "me"}, headers=H(ctx['ta']))
    assert r.status_code == 404
    assert ctx['ua'] not in (mdb.messages.find_one({"message_id": a1}).get('hidden_for') or [])


def test_bulk_non_participant_403(ctx):
    a1 = send(ctx['ta'], ctx['ub'], "TEST_np")
    r = requests.post(f"{API}/messages/delete-bulk", json={"message_ids": [a1], "scope": "me"}, headers=H(ctx['tc']))
    assert r.status_code == 403
    r = requests.delete(f"{API}/messages/{a1}?scope=me", headers=H(ctx['tc']))
    assert r.status_code == 403


def test_bulk_empty_and_too_many_422(ctx):
    r = requests.post(f"{API}/messages/delete-bulk", json={"message_ids": [], "scope": "me"}, headers=H(ctx['ta']))
    assert r.status_code == 422
    r = requests.post(f"{API}/messages/delete-bulk", json={"message_ids": [f"x{i}" for i in range(201)], "scope": "me"}, headers=H(ctx['ta']))
    assert r.status_code == 422
    r = requests.post(f"{API}/messages/delete-bulk", json={"message_ids": ["x"], "scope": "bogus"}, headers=H(ctx['ta']))
    assert r.status_code == 422


def test_bulk_unauth(ctx):
    r = requests.post(f"{API}/messages/delete-bulk", json={"message_ids": ["x"], "scope": "me"})
    assert r.status_code in (401, 403)


# --- list_chats ---
def test_list_chats_preview_skips_hidden(ctx):
    a1 = send(ctx['ta'], ctx['ub'], "TEST_prev_visible")
    a2 = send(ctx['ta'], ctx['ub'], "TEST_prev_hidden")
    requests.delete(f"{API}/messages/{a2}?scope=me", headers=H(ctx['ta']))
    r = requests.get(f"{API}/chats", headers=H(ctx['ta']))
    assert r.status_code == 200
    chat = [c for c in r.json() if c['user']['user_id'] == ctx['ub']][0]
    assert chat['last_message']['message_id'] == a1
    assert chat['last_message']['text'] == "TEST_prev_visible"
    # partner still sees latest
    rb = requests.get(f"{API}/chats", headers=H(ctx['tb'])).json()
    cb = [c for c in rb if c['user']['user_id'] == ctx['ua']][0]
    assert cb['last_message']['message_id'] == a2


def test_list_chats_all_hidden_stays_listed(ctx):
    # testuser1 <-> match_a chat: create one message from C to A? use a temp chat between C and A only if allowed
    cid_msgs = list(mdb.messages.find({"participants": {"$all": [ctx['uc'], ctx['ua']]}}, {"message_id": 1}))
    if not cid_msgs:
        pytest.skip("no C<->A chat to test all-hidden")
    ids = [m['message_id'] for m in cid_msgs]
    mdb.messages.update_many({"message_id": {"$in": ids}}, {"$addToSet": {"hidden_for": ctx['uc']}})
    try:
        r = requests.get(f"{API}/chats", headers=H(ctx['tc']))
        assert r.status_code == 200
        chat = [c for c in r.json() if c['user']['user_id'] == ctx['ua']]
        assert chat, "chat disappeared when all messages hidden"
        assert chat[0]['last_message']['text'] == ""
    finally:
        mdb.messages.update_many({"message_id": {"$in": ids}}, {"$pull": {"hidden_for": ctx['uc']}})
