"""Lovreski backend API tests."""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://lovreski-dating.preview.emergentagent.com').rstrip('/')
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@lovreski.ru"
ADMIN_PASSWORD = "LovreskiAdmin2026!"


@pytest.fixture(scope="session")
def s():
    return requests.Session()


@pytest.fixture(scope="session")
def seeded(s):
    r = s.post(f"{API}/demo/seed", timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="session")
def user_a(s):
    email = f"test_{uuid.uuid4().hex[:8]}@lovreski.ru"
    body = {"email": email, "password": "password123", "name": "TestA",
            "gender": "male", "dob": "1995-05-15"}
    r = s.post(f"{API}/auth/register", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    return {"email": email, "token": data["token"], "user": data["user"]}


@pytest.fixture(scope="session")
def user_b(s):
    email = f"test_{uuid.uuid4().hex[:8]}@lovreski.ru"
    body = {"email": email, "password": "password123", "name": "TestB",
            "gender": "female", "dob": "1996-06-16"}
    r = s.post(f"{API}/auth/register", json=body)
    assert r.status_code == 200
    data = r.json()
    return {"email": email, "token": data["token"], "user": data["user"]}


def H(token):
    return {"Authorization": f"Bearer {token}"}


# ────────── Health & Seed ──────────
def test_health(s):
    r = s.get(f"{API}/health")
    assert r.status_code == 200
    assert r.json().get("ok") is True


def test_seed(seeded):
    assert seeded.get("ok") is True


def test_seed_idempotent(s, seeded):
    r = s.post(f"{API}/demo/seed")
    assert r.status_code == 200
    # second call should either say already or seed count
    j = r.json()
    assert "already" in j or j.get("seeded") == 16


# ────────── Auth ──────────
def test_register_duplicate(s, user_a):
    r = s.post(f"{API}/auth/register", json={
        "email": user_a["email"], "password": "password123", "name": "Dup",
        "gender": "male", "dob": "1995-05-15"})
    assert r.status_code == 400


def test_login_success(s, user_a):
    r = s.post(f"{API}/auth/login", json={"email": user_a["email"], "password": "password123"})
    assert r.status_code == 200
    assert "token" in r.json()


def test_login_wrong_password(s, user_a):
    r = s.post(f"{API}/auth/login", json={"email": user_a["email"], "password": "WRONG"})
    assert r.status_code == 401


def test_admin_login(s):
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200
    data = r.json()
    assert data["user"].get("is_admin") is True


def test_me(s, user_a):
    r = s.get(f"{API}/auth/me", headers=H(user_a["token"]))
    assert r.status_code == 200
    assert r.json()["email"] == user_a["email"]


def test_me_no_token(s):
    r = s.get(f"{API}/auth/me")
    assert r.status_code == 401


# ────────── Profile ──────────
def test_profile_update(s, user_a):
    r = s.put(f"{API}/profile", headers=H(user_a["token"]),
              json={"about": "Люблю кофе", "interests": ["Кофе", "Йога"], "height": 180})
    assert r.status_code == 200
    d = r.json()
    assert d["about"] == "Люблю кофе"
    assert d["height"] == 180


def test_profile_too_many_interests(s, user_a):
    r = s.put(f"{API}/profile", headers=H(user_a["token"]),
              json={"interests": [f"i{i}" for i in range(11)]})
    assert r.status_code == 400


def test_profile_too_many_photos(s, user_a):
    r = s.put(f"{API}/profile", headers=H(user_a["token"]),
              json={"photos": [f"http://p/{i}" for i in range(5)]})
    assert r.status_code == 400


# ────────── Feed ──────────
def test_home_feed(s, user_a, seeded):
    r = s.get(f"{API}/home/feed?limit=6", headers=H(user_a["token"]))
    assert r.status_code == 200
    feed = r.json()
    assert isinstance(feed, list)
    assert len(feed) <= 6
    # user_a is male, show_me=female, all profiles should be female
    for u in feed:
        assert u["gender"] == "female", f"non-female in male's feed: {u}"


def test_discover_feed(s, user_a):
    r = s.get(f"{API}/discover/feed", headers=H(user_a["token"]))
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ────────── Likes / Match ──────────
def test_like_and_match(s, user_a, user_b):
    # A likes B
    r1 = s.post(f"{API}/like/{user_b['user']['user_id']}", headers=H(user_a["token"]))
    assert r1.status_code == 200
    assert r1.json()["match"] is False
    # B likes A → match
    r2 = s.post(f"{API}/like/{user_a['user']['user_id']}", headers=H(user_b["token"]))
    assert r2.status_code == 200
    assert r2.json()["match"] is True


def test_pass(s, user_a, seeded):
    feed = s.get(f"{API}/discover/feed", headers=H(user_a["token"])).json()
    if feed:
        r = s.post(f"{API}/pass/{feed[0]['user_id']}", headers=H(user_a["token"]))
        assert r.status_code == 200


def test_likes_lists(s, user_a):
    for path in ("received", "sent", "matches"):
        r = s.get(f"{API}/likes/{path}", headers=H(user_a["token"]))
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ────────── Chat ──────────
def test_chat_free_and_paid(s, user_a, user_b):
    other = user_b["user"]["user_id"]
    # Ensure fresh user_a has coins=5. First 2 msgs free
    for i in range(2):
        r = s.post(f"{API}/chats/{other}/send", headers=H(user_a["token"]),
                   json={"text": f"hi {i}", "kind": "text"})
        assert r.status_code == 200, r.text
    # Check balance still 5
    bal = s.get(f"{API}/coins/balance", headers=H(user_a["token"])).json()
    assert bal["coins"] == 5
    # 3rd message → cost 1
    r = s.post(f"{API}/chats/{other}/send", headers=H(user_a["token"]),
               json={"text": "hi 3", "kind": "text"})
    assert r.status_code == 200
    bal2 = s.get(f"{API}/coins/balance", headers=H(user_a["token"])).json()
    assert bal2["coins"] == 4


def test_chat_messages_and_list(s, user_a, user_b):
    other = user_b["user"]["user_id"]
    r = s.get(f"{API}/chats/{other}/messages", headers=H(user_a["token"]))
    assert r.status_code == 200
    msgs = r.json()
    assert len(msgs) >= 3
    r2 = s.get(f"{API}/chats", headers=H(user_a["token"]))
    assert r2.status_code == 200
    chats = r2.json()
    assert any(c["user"]["user_id"] == other for c in chats)


# ────────── Coins ──────────
def test_coin_packages(s):
    r = s.get(f"{API}/coins/packages")
    assert r.status_code == 200
    pkgs = r.json()["packages"]
    assert len(pkgs) == 4
    coins = sorted(p["coins"] for p in pkgs)
    assert coins == [10, 25, 50, 100]


def test_coin_purchase(s, user_a):
    r = s.post(f"{API}/coins/purchase", headers=H(user_a["token"]),
               json={"package_id": "p10", "phone": "+79000000000"})
    assert r.status_code == 200
    tx = r.json()
    assert tx["status"] == "pending"
    assert tx["coins"] == 10


# ────────── Admin ──────────
@pytest.fixture(scope="session")
def admin_token(s):
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200
    return r.json()["token"]


def test_admin_stats(s, admin_token):
    r = s.get(f"{API}/admin/stats", headers=H(admin_token))
    assert r.status_code == 200
    d = r.json()
    for k in ("total_users", "premium_users", "pending", "revenue",
              "daily", "monthly", "yearly", "revenue_daily", "revenue_monthly", "revenue_yearly"):
        assert k in d
    assert len(d["daily"]) == 24
    assert len(d["monthly"]) == 30
    assert len(d["yearly"]) == 12


def test_admin_payments_and_approve(s, admin_token, user_a):
    # create a purchase for user_a
    pr = s.post(f"{API}/coins/purchase", headers=H(user_a["token"]),
                json={"package_id": "p25", "phone": "+79000000001"}).json()
    tx_id = pr["tx_id"]
    # List
    r = s.get(f"{API}/admin/payments", headers=H(admin_token))
    assert r.status_code == 200
    assert any(t["tx_id"] == tx_id for t in r.json())
    # Approve
    ap = s.post(f"{API}/admin/payments/{tx_id}", headers=H(admin_token),
                json={"action": "approve"})
    assert ap.status_code == 200
    # verify coins incremented on user_a
    bal = s.get(f"{API}/coins/balance", headers=H(user_a["token"])).json()
    assert bal["coins"] >= 25
    assert bal["is_premium"] is True


def test_admin_payments_reject(s, admin_token, user_b):
    pr = s.post(f"{API}/coins/purchase", headers=H(user_b["token"]),
                json={"package_id": "p10", "phone": "+79000000002"}).json()
    tx_id = pr["tx_id"]
    r = s.post(f"{API}/admin/payments/{tx_id}", headers=H(admin_token),
               json={"action": "reject", "reason": "bad"})
    assert r.status_code == 200
    # Fetch and verify status
    lst = s.get(f"{API}/admin/payments?status=rejected", headers=H(admin_token)).json()
    assert any(t["tx_id"] == tx_id and t["status"] == "rejected" for t in lst)


def test_report_and_admin_reports(s, user_a, user_b, admin_token):
    r = s.post(f"{API}/report", headers=H(user_a["token"]),
               json={"target_user_id": user_b["user"]["user_id"], "reason": "spam"})
    assert r.status_code == 200
    r2 = s.get(f"{API}/admin/reports", headers=H(admin_token))
    assert r2.status_code == 200
    assert isinstance(r2.json(), list)


def test_admin_forbidden_for_user(s, user_a):
    r = s.get(f"{API}/admin/stats", headers=H(user_a["token"]))
    assert r.status_code == 403


def test_protected_no_token(s):
    for path in ("/home/feed", "/discover/feed", "/chats", "/coins/balance"):
        r = s.get(f"{API}{path}")
        assert r.status_code == 401, path


# ────────── Translate (best-effort) ──────────
def test_translate(s, user_a):
    r = s.post(f"{API}/translate", headers=H(user_a["token"]),
               json={"text": "Hello, how are you?", "target": "ru"})
    if r.status_code != 200:
        pytest.skip(f"translate unavailable: {r.status_code} {r.text[:100]}")
    d = r.json()
    assert "translated" in d
    assert len(d["translated"]) > 0
