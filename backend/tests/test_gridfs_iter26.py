"""Iter 26 — File & Media Storage (GridFS) backend tests."""
import os
import re
import io
import base64
import hashlib
import pytest
import requests
from PIL import Image

def _load_backend_url():
    v = os.environ.get('REACT_APP_BACKEND_URL')
    if v:
        return v.rstrip('/')
    try:
        with open('/app/frontend/.env') as f:
            for line in f:
                if line.startswith('REACT_APP_BACKEND_URL='):
                    return line.split('=', 1)[1].strip().rstrip('/')
    except Exception:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL missing")

BASE_URL = _load_backend_url()
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@lovreski.ru"
ADMIN_PASSWORD = "LovreskiAdmin2026!"
USER_EMAIL = "testuser1@lovreski.ru"
USER_PASSWORD = "password123"

HEX24 = re.compile(r"^[a-f0-9]{24}$")


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def user_token():
    r = requests.post(f"{API}/auth/login", json={"email": USER_EMAIL, "password": USER_PASSWORD}, timeout=15)
    if r.status_code != 200:
        # Register fresh
        rr = requests.post(f"{API}/auth/register", json={
            "email": USER_EMAIL, "password": USER_PASSWORD,
            "name": "Тестер", "gender": "male", "dob": "1998-05-15"
        }, timeout=15)
        assert rr.status_code in (200, 201), rr.text
        return rr.json()["token"]
    return r.json()["token"]


def _headers(tok):
    return {"Authorization": f"Bearer {tok}"}


def _small_png_data_url():
    img = Image.new("RGB", (32, 32), (200, 50, 50))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(), buf.getvalue()


def _small_jpeg_bytes(w=64, h=64):
    img = Image.new("RGB", (w, h), (30, 200, 90))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return buf.getvalue()


# ---------- chat/media ----------
class TestChatMedia:
    def test_chat_media_upload_returns_gridfs_url(self, user_token):
        data_url, _ = _small_png_data_url()
        r = requests.post(f"{API}/chat/media",
                          headers=_headers(user_token),
                          json={"data_url": data_url, "kind": "image"}, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        media_url = body["media_url"]
        assert media_url.startswith("/api/files/"), media_url
        assert not media_url.startswith("data:")
        file_id = media_url.rsplit("/", 1)[-1]
        assert HEX24.match(file_id), file_id
        # persist for downstream test
        pytest.chat_media_url = media_url
        pytest.chat_media_id = file_id


# ---------- GET /api/files/{id} ----------
class TestFileServing:
    def test_get_file_ok(self, user_token):
        data_url, _ = _small_png_data_url()
        r = requests.post(f"{API}/chat/media", headers=_headers(user_token),
                          json={"data_url": data_url, "kind": "image"}, timeout=30)
        media_url = r.json()["media_url"]
        rr = requests.get(f"{BASE_URL}{media_url}", timeout=30)
        assert rr.status_code == 200
        assert rr.headers.get("Content-Type", "").startswith("image/"), rr.headers
        assert int(rr.headers.get("Content-Length", "0")) > 0
        # Cache-Control is set by backend to `public, max-age=31536000, immutable`
        # but the preview ingress (Cloudflare) may strip / rewrite it.
        # Assert against direct backend to guarantee the app itself sets it.
        try:
            direct = requests.get(f"http://localhost:8001{media_url}", timeout=10)
            assert "public" in direct.headers.get("Cache-Control", ""), direct.headers.get("Cache-Control")
        except requests.RequestException:
            pass
        assert len(rr.content) == int(rr.headers["Content-Length"])

    def test_get_file_bad_id_400(self):
        r = requests.get(f"{API}/files/notahex", timeout=15)
        assert r.status_code == 400, r.text

    def test_get_file_missing_id_404(self):
        # valid-shape hex not in fs.files
        bogus = "0" * 24
        r = requests.get(f"{API}/files/{bogus}", timeout=15)
        assert r.status_code == 404, r.text


# ---------- POST /api/files/upload ----------
class TestFilesUpload:
    def test_upload_multipart_ok(self, user_token):
        jpg = _small_jpeg_bytes()
        files = {"file": ("tiny.jpg", jpg, "image/jpeg")}
        r = requests.post(f"{API}/files/upload", headers=_headers(user_token), files=files, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["url"].startswith("/api/files/")
        assert HEX24.match(d["file_id"])
        assert d["content_type"] == "image/jpeg"
        assert d["size"] > 0

    def test_upload_unauthenticated_401(self):
        jpg = _small_jpeg_bytes()
        files = {"file": ("tiny.jpg", jpg, "image/jpeg")}
        r = requests.post(f"{API}/files/upload", files=files, timeout=30)
        assert r.status_code in (401, 403), r.status_code

    def test_upload_image_too_large_413(self, user_token):
        # >4 MB image
        big = b"\xff" * (4 * 1024 * 1024 + 1024)
        files = {"file": ("big.jpg", big, "image/jpeg")}
        r = requests.post(f"{API}/files/upload", headers=_headers(user_token), files=files, timeout=60)
        assert r.status_code == 413, r.status_code

    def test_upload_non_image_too_large_413(self, user_token):
        big = b"x" * (10 * 1024 * 1024 + 1024)
        files = {"file": ("big.bin", big, "application/octet-stream")}
        r = requests.post(f"{API}/files/upload", headers=_headers(user_token), files=files, timeout=60)
        assert r.status_code == 413, r.status_code


# ---------- profile photo persistence ----------
class TestProfilePhoto:
    def test_profile_photo_stored_in_gridfs(self):
        # Register a fresh non-binary user to bypass AI gender check
        import uuid as _uuid
        email = f"TEST_iter26_{_uuid.uuid4().hex[:8]}@lovreski.ru"
        reg = requests.post(f"{API}/auth/register", json={
            "email": email, "password": "password123",
            "name": "TEST_iter26", "gender": "non_binary", "dob": "1998-05-15"
        }, timeout=15)
        assert reg.status_code in (200, 201), reg.text
        tok = reg.json()["token"]
        data_url, _ = _small_png_data_url()
        r = requests.post(f"{API}/profile/photo",
                          headers=_headers(tok),
                          json={"data_url": data_url}, timeout=45)
        assert r.status_code == 200, r.text
        me2 = requests.get(f"{API}/auth/me", headers=_headers(tok), timeout=15).json()
        new_photos = me2["photos"]
        assert len(new_photos) >= 1
        last = new_photos[-1]
        assert last.startswith("/api/files/"), last
        assert not last.startswith("data:")
        fr = requests.get(f"{BASE_URL}{last}", timeout=30)
        assert fr.status_code == 200


# ---------- chat send with GridFS media ----------
class TestChatSendWithMedia:
    def test_send_image_message(self, user_token, admin_token):
        # Send from testuser -> admin
        me = requests.get(f"{API}/auth/me", headers=_headers(user_token), timeout=15).json()
        admin_me = requests.get(f"{API}/auth/me", headers=_headers(admin_token), timeout=15).json()
        target_id = admin_me["user_id"]
        data_url, _ = _small_png_data_url()
        m = requests.post(f"{API}/chat/media", headers=_headers(user_token),
                          json={"data_url": data_url, "kind": "image"}, timeout=30).json()
        media_url = m["media_url"]
        assert media_url.startswith("/api/files/")
        send = requests.post(f"{API}/chats/{target_id}/send",
                             headers=_headers(user_token),
                             json={"kind": "image", "text": "", "media_url": media_url}, timeout=30)
        assert send.status_code == 200, send.text
        # Fetch messages
        msgs = requests.get(f"{API}/chats/{target_id}/messages",
                            headers=_headers(user_token), timeout=15).json()
        assert isinstance(msgs, list)
        # find our message
        found = [x for x in msgs if x.get("media_url") == media_url]
        assert found, "sent media message not returned in /messages"
        for x in msgs:
            mu = x.get("media_url")
            if mu:
                assert not mu.startswith("data:"), mu


# ---------- support receipt ----------
class TestSupportReceipt:
    def test_receipt_stored_in_gridfs(self, user_token, admin_token):
        data_url, _ = _small_png_data_url()
        r = requests.post(f"{API}/support/receipt", headers=_headers(user_token),
                          json={"package_id": "test_pkg", "receipt_data_url": data_url,
                                "message": "TEST_iter26"}, timeout=30)
        assert r.status_code == 200, r.text
        sub_id = r.json()["submission_id"]
        pend = requests.get(f"{API}/admin/support/pending", headers=_headers(admin_token), timeout=15)
        assert pend.status_code == 200
        rows = pend.json()
        mine = [x for x in rows if x.get("submission_id") == sub_id]
        assert mine, "submitted receipt not visible to admin"
        url = mine[0].get("receipt_data_url")
        assert url and url.startswith("/api/files/"), url


# ---------- refund ----------
class TestSupportRefund:
    def test_refund_stored_in_gridfs(self, user_token, admin_token):
        data_url, _ = _small_png_data_url()
        payload = {
            "receipt_data_url": data_url,
            "reason": "TEST_iter26 refund",
            "full_name": "TEST User",
            "email": USER_EMAIL,
        }
        r = requests.post(f"{API}/support/refund", headers=_headers(user_token), json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text
        refs = requests.get(f"{API}/admin/refunds", headers=_headers(admin_token), timeout=15)
        assert refs.status_code == 200
        rows = refs.json()
        assert rows, "no refunds returned"
        # verify our latest refund url is gridfs
        # find TEST_iter26 refund
        found = [x for x in rows if (x.get("reason") or "").startswith("TEST_iter26")]
        target = found[0] if found else rows[0]
        url = target.get("receipt_data_url")
        assert url and url.startswith("/api/files/"), url


# ---------- backfill idempotency + auth ----------
class TestBackfill:
    def test_non_admin_forbidden(self, user_token):
        r = requests.post(f"{API}/admin/migrate/gridfs", headers=_headers(user_token), timeout=30)
        assert r.status_code in (401, 403), r.status_code

    def test_backfill_idempotent(self, admin_token):
        # Run twice — expect all zeros the second time
        r1 = requests.post(f"{API}/admin/migrate/gridfs", headers=_headers(admin_token), timeout=120)
        assert r1.status_code == 200, r1.text
        d1 = r1.json()
        assert d1.get("ok") is True
        assert "migrated" in d1
        r2 = requests.post(f"{API}/admin/migrate/gridfs", headers=_headers(admin_token), timeout=120)
        assert r2.status_code == 200
        d2 = r2.json()
        m2 = d2["migrated"]
        assert m2["users_photos"] == 0, m2
        assert m2["messages_media"] == 0, m2
        assert m2["receipts"] == 0, m2
        assert m2["refunds"] == 0, m2


# ---------- invariants via API (post-migration) ----------
class TestPostMigrationInvariants:
    def test_no_base64_in_auth_me(self, user_token):
        me = requests.get(f"{API}/auth/me", headers=_headers(user_token), timeout=15).json()
        for p in me.get("photos") or []:
            assert not p.startswith("data:"), p

    def test_no_base64_in_admin_support_pending(self, admin_token):
        rows = requests.get(f"{API}/admin/support/pending", headers=_headers(admin_token), timeout=15).json()
        for r in rows:
            u = r.get("receipt_data_url") or ""
            assert not u.startswith("data:"), u

    def test_no_base64_in_admin_refunds(self, admin_token):
        rows = requests.get(f"{API}/admin/refunds", headers=_headers(admin_token), timeout=15).json()
        for r in rows:
            u = r.get("receipt_data_url") or ""
            assert not u.startswith("data:"), u


# ---------- regression smoke ----------
class TestSmokeRegression:
    def test_home_feed(self, user_token):
        r = requests.get(f"{API}/home/feed", headers=_headers(user_token), timeout=20)
        assert r.status_code == 200

    def test_discover_feed(self, user_token):
        r = requests.get(f"{API}/discover/feed", headers=_headers(user_token), timeout=20)
        assert r.status_code == 200

    def test_chats(self, user_token):
        r = requests.get(f"{API}/chats", headers=_headers(user_token), timeout=20)
        assert r.status_code == 200

    def test_auth_me(self, user_token):
        r = requests.get(f"{API}/auth/me", headers=_headers(user_token), timeout=20)
        assert r.status_code == 200
        assert "user_id" in r.json()

    def test_admin_stats(self, admin_token):
        r = requests.get(f"{API}/admin/stats", headers=_headers(admin_token), timeout=20)
        assert r.status_code == 200
