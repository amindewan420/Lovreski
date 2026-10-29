# Iter49: display-time translation of profile fields (/api/translate/batch name mode) + i18n bundles
import os
import re
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
CYR = re.compile(r"[\u0400-\u04FF]")
BENG = re.compile(r"[\u0980-\u09FF]")
DEVA = re.compile(r"[\u0900-\u097F]")


def _login(email):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "password123"}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"login failed {email}: {r.status_code}")
    return r.json()["token"]


@pytest.fixture(scope="module")
def h():
    return {"Authorization": f"Bearer {_login('testuser1@lovreski.ru')}"}


def _batch(h, target, texts, mode=None):
    body = {"target": target, "texts": texts}
    if mode:
        body["mode"] = mode
    return requests.post(f"{BASE_URL}/api/translate/batch", json=body, headers=h, timeout=90)


# Name transliteration mode
class TestNameMode:
    def test_maria_en(self, h):
        r = _batch(h, "en", ["Мария"], "name")
        assert r.status_code == 200
        v = r.json()["translations"]["Мария"]
        print("Мария->en:", v)
        assert not CYR.search(v) and "mari" in v.lower()

    def test_maria_bn(self, h):
        r = _batch(h, "bn", ["Мария"], "name")
        assert r.status_code == 200
        v = r.json()["translations"]["Мария"]
        print("Мария->bn:", v)
        assert BENG.search(v)

    def test_alex_ru(self, h):
        r = _batch(h, "ru", ["Alex"], "name")
        v = r.json()["translations"]["Alex"]
        print("Alex->ru:", v)
        assert v == "Алекс"

    def test_name_hi_as(self, h):
        v = _batch(h, "hi", ["Мария"], "name").json()["translations"]["Мария"]
        print("hi:", v)
        assert DEVA.search(v)
        v = _batch(h, "as", ["Мария"], "name").json()["translations"]["Мария"]
        print("as:", v)
        assert BENG.search(v)

    def test_name_not_translated_by_meaning(self, h):
        # 'Любовь' as a name should be transliterated (Lyubov), not 'Love'
        v = _batch(h, "en", ["Любовь"], "name").json()["translations"]["Любовь"]
        print("Любовь->en name:", v)
        assert "love" != v.strip().lower()

    def test_default_text_mode(self, h):
        r = _batch(h, "en", ["Программист", "Люблю путешествия, кофе и долгие прогулки"])
        assert r.status_code == 200
        tr = r.json()["translations"]
        print(tr)
        assert "programmer" in tr["Программист"].lower() or "developer" in tr["Программист"].lower()
        assert not CYR.search(tr["Люблю путешествия, кофе и долгие прогулки"])

    def test_text_mode_separate_cache(self, h):
        # same string in text vs name mode should be cached separately
        t = _batch(h, "en", ["Любовь"], "text").json()["translations"]["Любовь"]
        n = _batch(h, "en", ["Любовь"], "name").json()["translations"]["Любовь"]
        print("text:", t, "name:", n)
        assert t.lower() != n.lower()

    def test_invalid_mode_422(self, h):
        r = _batch(h, "en", ["Мария"], "bogus")
        assert r.status_code == 422

    def test_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/translate/batch", json={"target": "en", "texts": ["x"], "mode": "name"}, timeout=30)
        assert r.status_code in (401, 403)


# i18n full bundles
@pytest.mark.parametrize("lang", ["bn", "as", "hi"])
def test_i18n_bundle(lang):
    t0 = time.time()
    r = requests.get(f"{BASE_URL}/api/i18n/{lang}", timeout=120)
    dt = time.time() - t0
    assert r.status_code == 200
    d = r.json()
    print(lang, "time", round(dt, 1), "cached", d.get("cached"), "err", d.get("error"))
    assert d["lang"] == lang
    assert "error" not in d
    assert dt < 25
    s = d["strings"]
    script = DEVA if lang == "hi" else BENG
    n = sum(1 for v in s.values() if isinstance(v, str) and script.search(v))
    print(lang, "native-script strings", n, "/", len(s))
    assert n > len(s) * 0.5


# Premium keys translated
@pytest.mark.parametrize("lang", ["en"])
def test_premium_keys_en(lang):
    s = requests.get(f"{BASE_URL}/api/i18n/{lang}", timeout=120).json()["strings"]
    pk = {k: v for k, v in s.items() if k.startswith("premium.")}
    print("premium keys", len(pk))
    assert len(pk) > 0
    cyr = [k for k, v in pk.items() if CYR.search(v) and k != "premium.recipient_name"]
    print("cyrillic premium.* in en:", cyr[:10])
    assert not cyr


# Regression: chat message translation
def test_chat_translate_regression():
    hb = {"Authorization": f"Bearer {_login('match_b@lovreski.ru')}"}
    r = _batch(hb, "en", ["Привет! Как дела? Пойдём завтра в кино?"])
    v = r.json()["translations"]["Привет! Как дела? Пойдём завтра в кино?"]
    print(v)
    assert not CYR.search(v)
    r = requests.post(f"{BASE_URL}/api/translate", json={"text": "Good morning, my friend", "target": "ru"}, headers=hb, timeout=60)
    assert r.status_code == 200
    print(r.json())
    assert CYR.search(r.json()["translated"])


# Stored profile values unchanged
def test_me_unchanged(h):
    me = requests.get(f"{BASE_URL}/api/auth/me", headers=h, timeout=30).json()
    u = me.get("user", me)
    print({k: u.get(k) for k in ["name", "about", "job", "education", "language", "language_pref"]})
    assert u["name"] == "Мария"
    assert u["job"] == "Программист"
