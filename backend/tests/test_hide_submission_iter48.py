# Iter48: soft-delete (hide) of user's own receipt submissions — "Мои заявки"
import os, uuid, base64, io
import pytest, requests
from PIL import Image

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN = {"email": "admin@lovreski.ru", "password": "LovreskiAdmin2026!"}


def _png():
    buf = io.BytesIO()
    Image.new("RGB", (20, 20), (200, 50, 50)).save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _register():
    email = f"test_hide_{uuid.uuid4().hex[:8]}@lovreski.ru"
    r = requests.post(f"{BASE_URL}/api/auth/register", json={
        "email": email, "password": "password123", "name": "TEST Hide",
        "gender": "male", "dob": "1995-01-01"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def H(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def admin():
    r = requests.post(f"{BASE_URL}/api/admin/login", json=ADMIN)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def ctx(admin):
    a, b = _register(), _register()
    subs = []
    for i in range(4):
        r = requests.post(f"{BASE_URL}/api/support/receipt", headers=H(a),
                          json={"receipt_data_url": _png(), "message": f"TEST_hide_{i}"})
        assert r.status_code == 200, r.text
        subs.append(r.json()["submission_id"])
    yield {"a": a, "b": b, "subs": subs, "admin": admin}
    for s in subs:  # cleanup leftover pending
        requests.post(f"{BASE_URL}/api/admin/support/{s}/reject", headers=H(admin), json={"reason": "TEST cleanup"})


def _my(t):
    r = requests.get(f"{BASE_URL}/api/support/my", headers=H(t))
    assert r.status_code == 200
    return [x["submission_id"] for x in r.json()]


def _me(t):
    r = requests.get(f"{BASE_URL}/api/auth/me", headers=H(t))
    assert r.status_code == 200
    d = r.json()
    d = d.get("user", d)
    return d.get("coins", 0), d.get("is_premium", False)


def test_list_contains_all(ctx):
    mine = _my(ctx["a"])
    assert all(s in mine for s in ctx["subs"])


def test_hide_requires_auth(ctx):
    r = requests.patch(f"{BASE_URL}/api/support/my/{ctx['subs'][0]}/hide")
    assert r.status_code in (401, 403)


def test_hide_other_users_404(ctx):
    r = requests.patch(f"{BASE_URL}/api/support/my/{ctx['subs'][0]}/hide", headers=H(ctx["b"]))
    assert r.status_code == 404
    assert ctx["subs"][0] in _my(ctx["a"])


def test_hide_unknown_404(ctx):
    r = requests.patch(f"{BASE_URL}/api/support/my/sub_doesnotexist/hide", headers=H(ctx["a"]))
    assert r.status_code == 404


def test_hide_pending_then_approve_credits(ctx):
    s = ctx["subs"][0]
    r = requests.patch(f"{BASE_URL}/api/support/my/{s}/hide", headers=H(ctx["a"]))
    assert r.status_code == 200 and r.json()["ok"] is True
    mine = _my(ctx["a"])
    assert s not in mine and ctx["subs"][1] in mine
    pend = requests.get(f"{BASE_URL}/api/admin/support/pending", headers=H(ctx["admin"])).json()
    p = [x for x in pend if x["submission_id"] == s]
    assert p and p[0]["is_deleted_by_user"] is True
    c0, _ = _me(ctx["a"])
    r = requests.post(f"{BASE_URL}/api/admin/support/{s}/approve", headers=H(ctx["admin"]), json={"coins": 50, "reason": "TEST"})
    assert r.status_code == 200, r.text
    c1, prem = _me(ctx["a"])
    assert c1 == c0 + 50 and prem is True
    hist = requests.get(f"{BASE_URL}/api/admin/support/history", headers=H(ctx["admin"])).json()
    h = [x for x in hist if x["submission_id"] == s]
    assert h and h[0]["is_deleted_by_user"] is True and h[0]["status"] == "verified"
    assert s not in _my(ctx["a"])


def test_hide_verified_keeps_premium_coins(ctx):
    s = ctx["subs"][1]
    r = requests.post(f"{BASE_URL}/api/admin/support/{s}/approve", headers=H(ctx["admin"]), json={"coins": 30, "reason": "TEST"})
    assert r.status_code == 200
    before = _me(ctx["a"])
    r = requests.patch(f"{BASE_URL}/api/support/my/{s}/hide", headers=H(ctx["a"]))
    assert r.status_code == 200
    assert _me(ctx["a"]) == before
    assert s not in _my(ctx["a"])


def test_hide_rejected(ctx):
    s = ctx["subs"][2]
    requests.post(f"{BASE_URL}/api/admin/support/{s}/reject", headers=H(ctx["admin"]), json={"reason": "TEST rej"})
    r = requests.patch(f"{BASE_URL}/api/support/my/{s}/hide", headers=H(ctx["a"]))
    assert r.status_code == 200
    assert s not in _my(ctx["a"])
    assert ctx["subs"][3] in _my(ctx["a"])


def test_hide_idempotent(ctx):
    s = ctx["subs"][2]
    r = requests.patch(f"{BASE_URL}/api/support/my/{s}/hide", headers=H(ctx["a"]))
    assert r.status_code == 200
