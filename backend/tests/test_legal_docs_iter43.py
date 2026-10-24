# Legal documents: public merged list, admin CRUD with built-in overrides, aliases, auth
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN = {"email": "admin@lovreski.ru", "password": "LovreskiAdmin2026!"}
USER = {"email": "testuser1@lovreski.ru", "password": "password123"}
BUILTINS = ["terms-of-service", "privacy-policy", "payment-rules", "refund-policy", "community-guidelines", "security-tips"]


@pytest.fixture(scope="module")
def admin_h():
    r = requests.post(f"{API}/admin/login", json=ADMIN)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def user_h():
    r = requests.post(f"{API}/auth/login", json=USER)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module", autouse=True)
def cleanup(admin_h):
    yield
    for s in ["terms-of-service", "privacy-policy", "cookie-policy", "test_cookie"]:
        requests.delete(f"{API}/admin/legal/{s}", headers=admin_h)


# Public list
def test_public_list_builtins():
    r = requests.get(f"{API}/legal")
    assert r.status_code == 200
    assert "no-store" in r.headers.get("cache-control", "")
    d = r.json()
    assert [x["slug"] for x in d[:6]] == BUILTINS
    assert all(x["source"] == "builtin" for x in d[:6])
    assert all("body" not in x for x in d)


def test_public_get_alias_builtin():
    for a, c in [("terms", "terms-of-service"), ("privacy", "privacy-policy"), ("payment", "payment-rules"),
                 ("refund", "refund-policy"), ("security", "security-tips"), ("guidelines", "community-guidelines"),
                 ("community", "community-guidelines")]:
        r = requests.get(f"{API}/legal/{a}")
        assert r.status_code == 200
        j = r.json()
        assert j["slug"] == c and j["source"] == "builtin" and len(j["body"]) > 50
        assert "no-store" in r.headers.get("cache-control", "")


def test_public_get_unknown_404():
    assert requests.get(f"{API}/legal/no-such-doc-xyz").status_code == 404


# Auth
def test_admin_endpoints_require_admin(user_h):
    assert requests.get(f"{API}/admin/legal", headers=user_h).status_code == 401
    assert requests.post(f"{API}/admin/legal", headers=user_h, json={"slug": "x", "title": "x", "body": "x"}).status_code == 401
    assert requests.put(f"{API}/admin/legal/privacy-policy", headers=user_h, json={"slug": "privacy-policy", "title": "x", "body": "x"}).status_code == 401
    assert requests.delete(f"{API}/admin/legal/privacy-policy", headers=user_h).status_code == 401
    assert requests.get(f"{API}/admin/legal").status_code == 401


def test_admin_list_has_body(admin_h):
    r = requests.get(f"{API}/admin/legal", headers=admin_h)
    assert r.status_code == 200
    d = r.json()
    assert [x["slug"] for x in d[:6]] == BUILTINS
    assert all(x.get("body") for x in d)


# Override via alias
def test_create_override_alias_terms(admin_h):
    r = requests.post(f"{API}/admin/legal", headers=admin_h,
                      json={"slug": "terms", "title": "TEST_Terms Title", "body": "# TEST Heading\n\n**bold** text\n\n- a\n- b"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["slug"] == "terms-of-service" and j["overrides_builtin"] is True
    lst = requests.get(f"{API}/legal").json()
    t = next(x for x in lst if x["slug"] == "terms-of-service")
    assert t["source"] == "custom" and t["title"] == "TEST_Terms Title"
    assert len([x for x in lst if x["slug"] in ("terms", "terms-of-service")]) == 1
    for s in ["terms", "terms-of-service"]:
        g = requests.get(f"{API}/legal/{s}").json()
        assert g["source"] == "custom" and "TEST Heading" in g["body"] and g["slug"] == "terms-of-service"


def test_create_duplicate_409(admin_h):
    for s in ["terms", "terms-of-service"]:
        r = requests.post(f"{API}/admin/legal", headers=admin_h, json={"slug": s, "title": "dup", "body": "dup"})
        assert r.status_code == 409


def test_put_builtin_creates_override(admin_h):
    r = requests.put(f"{API}/admin/legal/privacy-policy", headers=admin_h,
                     json={"slug": "privacy-policy", "title": "TEST_Privacy", "body": "## TEST priv"})
    assert r.status_code == 200, r.text
    g = requests.get(f"{API}/legal/privacy").json()
    assert g["source"] == "custom" and g["title"] == "TEST_Privacy"


def test_put_slug_mismatch_400(admin_h):
    r = requests.put(f"{API}/admin/legal/privacy-policy", headers=admin_h,
                     json={"slug": "terms", "title": "x", "body": "x"})
    assert r.status_code == 400


def test_put_unknown_404(admin_h):
    r = requests.put(f"{API}/admin/legal/nope-doc", headers=admin_h, json={"slug": "nope-doc", "title": "x", "body": "x"})
    assert r.status_code == 404


def test_delete_custom_reverts(admin_h):
    r = requests.delete(f"{API}/admin/legal/privacy-policy", headers=admin_h)
    assert r.status_code == 200 and r.json()["reverted_to_builtin"] is True
    g = requests.get(f"{API}/legal/privacy-policy").json()
    assert g["source"] == "builtin" and g["title"] == "🛡 Privacy Policy"
    r = requests.delete(f"{API}/admin/legal/terms", headers=admin_h)
    assert r.status_code == 200 and r.json()["reverted_to_builtin"] is True
    assert requests.get(f"{API}/legal/terms").json()["source"] == "builtin"


def test_delete_builtin_without_custom_400(admin_h):
    assert requests.delete(f"{API}/admin/legal/security-tips", headers=admin_h).status_code == 400


def test_new_slug_lifecycle(admin_h):
    r = requests.post(f"{API}/admin/legal", headers=admin_h,
                      json={"slug": "cookie-policy", "title": "TEST_Cookie", "body": "Cookies **here**"})
    assert r.status_code == 200 and r.json()["overrides_builtin"] is False
    lst = requests.get(f"{API}/legal").json()
    assert [x["slug"] for x in lst[:6]] == BUILTINS
    c = lst[6]
    assert c["slug"] == "cookie-policy" and c["source"] == "custom"
    assert requests.get(f"{API}/legal/cookie-policy").json()["title"] == "TEST_Cookie"
    r = requests.delete(f"{API}/admin/legal/cookie-policy", headers=admin_h)
    assert r.status_code == 200 and r.json()["reverted_to_builtin"] is False
    assert requests.get(f"{API}/legal/cookie-policy").status_code == 404
    assert requests.delete(f"{API}/admin/legal/cookie-policy", headers=admin_h).status_code == 404


def test_validation_bad_slug_422(admin_h):
    r = requests.post(f"{API}/admin/legal", headers=admin_h, json={"slug": "Bad Slug!", "title": "x", "body": "x"})
    assert r.status_code == 422
    r = requests.post(f"{API}/admin/legal", headers=admin_h, json={"slug": "ok-slug", "title": "", "body": "x"})
    assert r.status_code == 422
