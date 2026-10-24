# Iter42: Receipt upload (JPG/PNG/PDF) validation + admin receipt-file proxy + refunds
# NOTE: run with `-n 0` (module-level shared STATE; xdist parallelism breaks ordering)
import base64
import io
import os
import uuid

import pytest
import requests
from PIL import Image

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN = {"email": "admin@lovreski.ru", "password": "LovreskiAdmin2026!"}
PUB = "https://s3.twcstorage.ru/600faa0a-6355-47f3-8485-fb1ee59ea330"
STATE = {}


def _pdf_url(path="/tmp/receipt.pdf"):
    with open(path, "rb") as f:
        return "data:application/pdf;base64," + base64.b64encode(f.read()).decode()


def _png_url():
    buf = io.BytesIO()
    Image.new("RGB", (120, 80), (200, 30, 30)).save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _register():
    email = f"test_rcpt_{uuid.uuid4().hex[:8]}@lovreski.ru"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "password123", "name": "TEST Rcpt",
                                                   "gender": "male", "dob": "1995-05-05"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def user_h():
    return _register()


@pytest.fixture(scope="module")
def admin_h():
    r = requests.post(f"{API}/admin/login", json=ADMIN)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


# --- Upload validation ---
class TestReceiptValidation:
    def test_reject_txt_mime(self, user_h):
        r = requests.post(f"{API}/support/receipt", headers=user_h,
                          json={"receipt_data_url": "data:text/plain;base64,aGVsbG8="})
        assert r.status_code == 400
        assert "JPG, PNG или PDF" in r.json()["detail"]

    def test_reject_fake_pdf(self, user_h):
        fake = "data:application/pdf;base64," + base64.b64encode(b"not a pdf at all, just text" * 5).decode()
        r = requests.post(f"{API}/support/receipt", headers=user_h, json={"receipt_data_url": fake})
        assert r.status_code == 400
        assert "PDF" in r.json()["detail"]

    def test_reject_over_10mb(self, user_h):
        big = "data:application/pdf;base64," + base64.b64encode(b"%PDF-1.4\n" + b"0" * (11 * 1024 * 1024)).decode()
        r = requests.post(f"{API}/support/receipt", headers=user_h, json={"receipt_data_url": big})
        assert r.status_code == 413

    def test_refund_reject_txt(self, user_h):
        r = requests.post(f"{API}/support/refund", headers=user_h, json={
            "full_name": "TEST", "email": "t@lovreski.ru", "reason": "x",
            "receipt_data_url": "data:text/plain;base64,aGVsbG8="})
        assert r.status_code == 400


# --- Successful uploads ---
class TestReceiptUploads:
    def test_pdf_receipt_upload(self, user_h, admin_h):
        r = requests.post(f"{API}/support/receipt", headers=user_h, json={"receipt_data_url": _pdf_url(), "message": "TEST pdf"})
        assert r.status_code == 200, r.text
        sid = r.json()["submission_id"]
        pend = requests.get(f"{API}/admin/support/pending", headers=admin_h).json()
        doc = next(s for s in pend if s["submission_id"] == sid)
        assert doc["receipt_data_url"].endswith(".pdf")
        STATE["pdf_sub"] = sid
        STATE["pdf_url"] = doc["receipt_data_url"]

    def test_png_receipt_upload(self, user_h, admin_h):
        r = requests.post(f"{API}/support/receipt", headers=user_h, json={"receipt_data_url": _png_url()})
        assert r.status_code == 200, r.text
        sid = r.json()["submission_id"]
        pend = requests.get(f"{API}/admin/support/pending", headers=admin_h).json()
        doc = next(s for s in pend if s["submission_id"] == sid)
        STATE["img_sub"] = sid
        STATE["img_url"] = doc["receipt_data_url"]

    def test_big_pdf_upload(self, user_h, admin_h):
        r = requests.post(f"{API}/support/receipt", headers=user_h, json={"receipt_data_url": _pdf_url("/tmp/big.pdf")}, timeout=120)
        assert r.status_code == 200, r.text
        sid = r.json()["submission_id"]
        pend = requests.get(f"{API}/admin/support/pending", headers=admin_h).json()
        STATE["big_url"] = next(s for s in pend if s["submission_id"] == sid)["receipt_data_url"]
        STATE["big_sub"] = sid

    def test_refund_pdf_and_image(self, user_h, admin_h):
        ids = []
        for url in (_pdf_url(), _png_url()):
            r = requests.post(f"{API}/support/refund", headers=user_h, json={
                "full_name": "TEST Refund", "email": "t@lovreski.ru", "reason": "TEST", "receipt_data_url": url})
            assert r.status_code == 200, r.text
            ids.append(r.json()["refund_id"])
        refs = requests.get(f"{API}/admin/refunds", headers=admin_h).json()
        m = {x["refund_id"]: x for x in refs}
        assert m[ids[0]]["receipt_data_url"].endswith(".pdf")
        STATE["ref_pdf"], STATE["ref_img"] = ids
        STATE["ref_pdf_url"] = m[ids[0]]["receipt_data_url"]


# --- Admin proxy ---
class TestReceiptProxy:
    def test_s3_object_headers_no_aws_chunked(self):
        if "pdf_url" not in STATE or not STATE["pdf_url"].startswith("http"):
            pytest.skip("no S3 url")
        r = requests.get(STATE["pdf_url"])
        assert r.status_code == 200
        assert r.headers.get("Content-Type") == "application/pdf"
        assert "aws-chunked" not in (r.headers.get("Content-Encoding") or "")
        assert r.content.startswith(b"%PDF")

    def test_proxy_pdf_inline(self, admin_h):
        r = requests.get(f"{API}/admin/receipt-file", headers=admin_h, params={"src": STATE["pdf_url"], "download": 0})
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/pdf")
        assert r.headers["content-disposition"].startswith("inline")
        assert r.content.startswith(b"%PDF")

    def test_proxy_pdf_attachment(self, admin_h):
        r = requests.get(f"{API}/admin/receipt-file", headers=admin_h, params={"src": STATE["pdf_url"], "download": 1})
        assert r.status_code == 200
        assert r.headers["content-disposition"].startswith("attachment")

    def test_proxy_image(self, admin_h):
        r = requests.get(f"{API}/admin/receipt-file", headers=admin_h, params={"src": STATE["img_url"]})
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("image/")

    def test_proxy_big_pdf(self, admin_h):
        r = requests.get(f"{API}/admin/receipt-file", headers=admin_h, params={"src": STATE["big_url"]}, timeout=120)
        assert r.status_code == 200
        assert len(r.content) > 9_000_000

    def test_proxy_refund_pdf(self, admin_h):
        r = requests.get(f"{API}/admin/receipt-file", headers=admin_h, params={"src": STATE["ref_pdf_url"]})
        assert r.status_code == 200
        assert r.content.startswith(b"%PDF")

    def test_proxy_user_token_401(self, user_h):
        r = requests.get(f"{API}/admin/receipt-file", headers=user_h, params={"src": STATE["pdf_url"]})
        assert r.status_code == 401

    def test_proxy_foreign_url_400(self, admin_h):
        r = requests.get(f"{API}/admin/receipt-file", headers=admin_h, params={"src": "https://evil.com/lovreski/support_receipt/a.pdf"})
        assert r.status_code == 400

    def test_proxy_non_receipt_kind_400(self, admin_h):
        r = requests.get(f"{API}/admin/receipt-file", headers=admin_h, params={"src": f"{PUB}/lovreski/profile_photo/x.jpg"})
        assert r.status_code == 400

    def test_proxy_traversal_400(self, admin_h):
        r = requests.get(f"{API}/admin/receipt-file", headers=admin_h, params={"src": f"{PUB}/lovreski/support_receipt/../profile_photo/x.jpg"})
        assert r.status_code == 400

    def test_proxy_missing_404(self, admin_h):
        r = requests.get(f"{API}/admin/receipt-file", headers=admin_h, params={"src": f"{PUB}/lovreski/support_receipt/doesnotexist.pdf"})
        assert r.status_code == 404
        assert r.json()["detail"] == "File not found"


# --- Rate limits ---
class TestRateLimits:
    def test_receipt_rate_limit_5_per_hour(self):
        h = _register()
        codes = [requests.post(f"{API}/support/receipt", headers=h, json={"receipt_data_url": _pdf_url()}).status_code for _ in range(6)]
        assert codes[:5] == [200] * 5 and codes[5] == 429, codes
