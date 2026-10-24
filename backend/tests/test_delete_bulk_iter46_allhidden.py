"""Iter 46 — chat stays in /api/chats when every message is hidden for the viewer (A<->B, reverted after)."""
from test_delete_bulk_iter46 import API, A, B, H, _login, mdb, requests


def test_all_hidden_chat_listed():
    ta, ua = _login(A)
    tb, ub = _login(B)
    to_hide = [m['message_id'] for m in mdb.messages.find(
        {"participants": {"$all": [ua, ub]}, "hidden_for": {"$ne": ua}}, {"message_id": 1})]
    mdb.messages.update_many({"message_id": {"$in": to_hide}}, {"$addToSet": {"hidden_for": ua}})
    try:
        r = requests.get(f"{API}/chats", headers=H(ta))
        assert r.status_code == 200
        chat = [c for c in r.json() if c['user']['user_id'] == ub]
        assert chat, "chat disappeared when all messages hidden"
        assert chat[0]['last_message']['text'] == ""
        assert chat[0]['last_message'].get('media_url') is None
        rm = requests.get(f"{API}/chats/{ub}/messages", headers=H(ta))
        assert rm.json() == []
    finally:
        mdb.messages.update_many({"message_id": {"$in": to_hide}}, {"$pull": {"hidden_for": ua}})
