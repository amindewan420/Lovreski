# Iteration 45: chat media-file proxy endpoint (view/download attachments)
import base64, io, os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    with open('/app/frontend/.env') as f:
        for line in f:
            if line.startswith('REACT_APP_BACKEND_URL='):
                BASE_URL = line.split('=', 1)[1].strip().rstrip('/')
API = f"{BASE_URL}/api"
PDF_MSG = "msg_7c6cdc9ca60c"
MATCH_B = "user_3e49e86330a7"


def login(email, pw="password123"):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def H(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def tok_a():
    return login("match_a@lovreski.ru")


@pytest.fixture(scope="module")
def tok_b():
    return login("match_b@lovreski.ru")


@pytest.fixture(scope="module")
def tok_other():
    return login("testuser1@lovreski.ru")


def _png_bytes():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (200, 30, 90)).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture(scope="module")
def image_msg(tok_a):
    me = requests.get(f"{API}/auth/me", headers=H(tok_a)).json()
    uid = me.get("user_id") or me.get("user", {}).get("user_id")
    if (me.get("coins") or me.get("user", {}).get("coins") or 0) < 50:
        at = requests.post(f"{API}/admin/login", json={"email": "admin@lovreski.ru", "password": "LovreskiAdmin2026!"}).json()["token"]
        requests.post(f"{API}/admin/users/add-coins", headers=H(at), json={"user_id": uid, "coins": 200, "reason": "TEST iter45"})
    du = "data:image/png;base64," + base64.b64encode(_png_bytes()).decode()
    r = requests.post(f"{API}/chat/media", headers=H(tok_a), json={"data_url": du, "kind": "image", "file_name": "x.png"})
    assert r.status_code == 200, r.text
    media_url = r.json().get("media_url") or r.json().get("url") or r.json().get("data_url")
    r = requests.post(f"{API}/chats/{MATCH_B}/send", headers=H(tok_a), json={"kind": "image", "media_url": media_url, "text": ""})
    assert r.status_code == 200, r.text
    d = r.json()
    msg = d.get("message") or d
    assert msg.get("message_id"), d
    return msg["message_id"]


class TestPdf:
    def test_pdf_inline_sender(self, tok_a):
        r = requests.get(f"{API}/chat/media-file/{PDF_MSG}", headers=H(tok_a))
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("application/pdf")
        assert r.headers["content-disposition"].startswith("inline")
        assert "ticket.pdf" in r.headers["content-disposition"]
        assert r.content[:4] == b"%PDF"

    def test_pdf_attachment_receiver(self, tok_b):
        r = requests.get(f"{API}/chat/media-file/{PDF_MSG}?download=1", headers=H(tok_b))
        assert r.status_code == 200
        assert r.headers["content-disposition"].startswith("attachment")
        assert "filename*=UTF-8''ticket.pdf" in r.headers["content-disposition"]

    def test_non_participant_404(self, tok_other):
        r = requests.get(f"{API}/chat/media-file/{PDF_MSG}", headers=H(tok_other))
        assert r.status_code == 404
        assert r.json()["detail"] == "File not found"

    def test_unknown_id_404(self, tok_a):
        r = requests.get(f"{API}/chat/media-file/msg_doesnotexist", headers=H(tok_a))
        assert r.status_code == 404

    def test_no_auth_401(self):
        r = requests.get(f"{API}/chat/media-file/{PDF_MSG}")
        assert r.status_code == 401


class TestImage:
    def test_image_stream(self, tok_a, tok_b, image_msg):
        for t in (tok_a, tok_b):
            r = requests.get(f"{API}/chat/media-file/{image_msg}", headers=H(t))
            assert r.status_code == 200, r.text
            assert r.headers["content-type"].startswith("image/")
            assert len(r.content) > 50

    def test_image_download_header(self, tok_b, image_msg):
        r = requests.get(f"{API}/chat/media-file/{image_msg}?download=1", headers=H(tok_b))
        assert r.headers["content-disposition"].startswith("attachment")

    def test_text_message_404(self, tok_a):
        r = requests.get(f"{API}/chats/{MATCH_B}/messages", headers=H(tok_a))
        if r.status_code != 200:
            pytest.skip("messages endpoint differs")
        d = r.json()
        msgs = d if isinstance(d, list) else d.get("messages", [])
        txt = next((m for m in msgs if not m.get("media_url") and not m.get("deleted")), None)
        if not txt:
            pytest.skip("no text msg")
        r = requests.get(f"{API}/chat/media-file/{txt['message_id']}", headers=H(tok_a))
        assert r.status_code == 404

    def test_deleted_message_404(self, tok_a):
        du = "data:image/png;base64," + base64.b64encode(_png_bytes()).decode()
        r = requests.post(f"{API}/chat/media", headers=H(tok_a), json={"data_url": du, "kind": "image", "file_name": "del.png"})
        mu = r.json().get("media_url") or r.json().get("url")
        r = requests.post(f"{API}/chats/{MATCH_B}/send", headers=H(tok_a), json={"kind": "image", "media_url": mu, "text": ""})
        mid = (r.json().get("message") or r.json())["message_id"]
        dr = requests.delete(f"{API}/messages/{mid}?scope=everyone", headers=H(tok_a))
        if dr.status_code not in (200, 204):
            pytest.skip(f"delete route unknown {dr.status_code}")
        r = requests.get(f"{API}/chat/media-file/{mid}", headers=H(tok_a))
        assert r.status_code == 404
