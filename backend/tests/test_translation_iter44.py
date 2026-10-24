# Iteration 44: content translation (chat batch + legal docs) regression tests
import os, time, pytest, requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
S = requests.Session()


def _login(email, pw="password123"):
    r = S.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def tok_a():
    return _login("match_a@lovreski.ru")


@pytest.fixture(scope="module")
def admin_tok():
    r = S.post(f"{BASE_URL}/api/admin/login", json={"email": "admin@lovreski.ru", "password": "LovreskiAdmin2026!"}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def H(t):
    return {"Authorization": f"Bearer {t}"}


# --- /api/translate/batch ---
class TestBatch:
    def test_no_auth_401(self):
        r = requests.post(f"{BASE_URL}/api/translate/batch", json={"target": "en", "texts": ["Привет"]}, timeout=30)
        assert r.status_code == 401

    def test_empty_list(self, tok_a):
        r = S.post(f"{BASE_URL}/api/translate/batch", json={"target": "en", "texts": []}, headers=H(tok_a), timeout=30)
        assert r.status_code == 200
        assert r.json()["translations"] == {}

    def test_batch_translate_and_cache(self, tok_a):
        texts = [f"Привет, как дела? TEST{int(time.time())}", "Я люблю кофе по утрам", "Hello my friend"]
        t0 = time.time()
        r = S.post(f"{BASE_URL}/api/translate/batch", json={"target": "en", "texts": texts}, headers=H(tok_a), timeout=90)
        first = time.time() - t0
        assert r.status_code == 200, r.text
        tr = r.json()["translations"]
        assert set(tr.keys()) == set(texts)
        assert tr["Hello my friend"] == "Hello my friend"
        assert tr["Я люблю кофе по утрам"] != "Я люблю кофе по утрам"
        assert "coffee" in tr["Я люблю кофе по утрам"].lower()
        t0 = time.time()
        r2 = S.post(f"{BASE_URL}/api/translate/batch", json={"target": "en", "texts": texts}, headers=H(tok_a), timeout=90)
        second = time.time() - t0
        assert r2.json()["translations"] == tr
        print(f"first={first:.2f}s second={second:.2f}s")
        assert second < 1.5

    def test_invalid_target_fail_open(self, tok_a):
        r = S.post(f"{BASE_URL}/api/translate/batch", json={"target": "zz-invalid", "texts": ["Добрый вечер"]}, headers=H(tok_a), timeout=90)
        assert r.status_code == 200, r.text
        assert isinstance(r.json()["translations"]["Добрый вечер"], str)
        assert r.json()["translations"]["Добрый вечер"].strip()

    def test_single_translate(self, tok_a):
        r = S.post(f"{BASE_URL}/api/translate", json={"text": "Я люблю кофе по утрам", "target": "en"}, headers=H(tok_a), timeout=60)
        assert r.status_code == 200
        assert "coffee" in r.json()["translated"].lower()


# --- /api/legal?lang ---
class TestLegal:
    def test_list_en(self):
        # built-in docs are authored in English -> en is unchanged, ru must differ
        docs = S.get(f"{BASE_URL}/api/legal?lang=en", timeout=120).json()
        assert all(d["title"] == d["original_title"] for d in docs)
        r = S.get(f"{BASE_URL}/api/legal?lang=ru", timeout=120)
        assert r.status_code == 200
        docs = r.json()
        assert len(docs) > 0
        assert all(d["title"] != d["original_title"] for d in docs)

    def test_list_no_lang(self):
        docs = S.get(f"{BASE_URL}/api/legal", timeout=30).json()
        assert all("original_title" not in d for d in docs)

    def test_doc_de(self):
        r = S.get(f"{BASE_URL}/api/legal/terms-of-service?lang=de", timeout=180)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["translated"] is True
        assert d["original_body"] and d["body"] != d["original_body"]
        assert d["lang"] == "de"

    def test_doc_original(self):
        d = S.get(f"{BASE_URL}/api/legal/terms-of-service", timeout=30).json()
        assert "original_body" not in d and "translated" not in d

    def test_unknown_404(self):
        assert S.get(f"{BASE_URL}/api/legal/no-such-doc-xyz?lang=en", timeout=30).status_code == 404

    def test_admin_save_prewarms(self, admin_tok, tok_a):
        # make sure 'en' is among chosen languages
        S.put(f"{BASE_URL}/api/profile", json={"language_pref": "en"}, headers=H(tok_a), timeout=30)
        slug = "test-iter44-doc"
        S.delete(f"{BASE_URL}/api/admin/legal/{slug}", headers=H(admin_tok), timeout=30)
        body = f"# Тестовый документ\n\nЭто тестовый абзац номер {int(time.time())}.\n\nВторой абзац о правилах."
        r = S.post(f"{BASE_URL}/api/admin/legal", json={"slug": slug, "title": "Тестовые правила", "body": body}, headers=H(admin_tok), timeout=30)
        assert r.status_code == 200, r.text
        try:
            time.sleep(15)
            t0 = time.time()
            d = S.get(f"{BASE_URL}/api/legal/{slug}?lang=en", timeout=60).json()
            el = time.time() - t0
            print(f"prewarmed GET took {el:.2f}s")
            assert d["translated"] is True
            assert el < 2.0
            # PUT update also works
            r = S.put(f"{BASE_URL}/api/admin/legal/{slug}", json={"slug": slug, "title": "Тестовые правила 2", "body": body + "\n\nТретий абзац."}, headers=H(admin_tok), timeout=30)
            assert r.status_code == 200
        finally:
            assert S.delete(f"{BASE_URL}/api/admin/legal/{slug}", headers=H(admin_tok), timeout=30).status_code == 200
