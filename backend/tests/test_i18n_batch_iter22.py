"""Iter22: Test POST /api/i18n/translate-batch endpoint."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://lovreski-dating.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


def _post(lang, strings, timeout=60):
    return requests.post(f"{API}/i18n/translate-batch", json={"lang": lang, "strings": strings}, timeout=timeout)


def _has_cyrillic(s: str) -> bool:
    return any("\u0400" <= c <= "\u04FF" for c in s)


class TestI18nBatch:
    RU_STRINGS = ["Правовая информация", "Пользовательское соглашение", "Сохранить"]

    def test_1_translate_to_en(self):
        r = _post("en", self.RU_STRINGS)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "translations" in data
        t = data["translations"]
        assert len(t) == 3
        for src in self.RU_STRINGS:
            assert src in t
            val = t[src]
            assert isinstance(val, str) and val.strip()
            # English translation should not contain Cyrillic
            assert not _has_cyrillic(val), f"expected English translation for '{src}', got '{val}'"

    def test_2_idempotent_cache_hit(self):
        # Warm
        _post("en", self.RU_STRINGS)
        start = time.time()
        r = _post("en", self.RU_STRINGS)
        elapsed_ms = (time.time() - start) * 1000
        assert r.status_code == 200
        data = r.json()["translations"]
        assert len(data) == 3
        assert elapsed_ms < 1500, f"cache-hit latency too high: {elapsed_ms}ms"

    def test_3_ru_echoes_verbatim(self):
        r = _post("ru", self.RU_STRINGS)
        assert r.status_code == 200
        t = r.json()["translations"]
        for s in self.RU_STRINGS:
            assert t[s] == s

    def test_4_caps_at_200(self):
        # 250 unique strings
        strings = [f"Тест строка {i}" for i in range(250)]
        r = _post("en", strings, timeout=120)
        assert r.status_code == 200, r.text
        t = r.json()["translations"]
        assert len(t) <= 200

    def test_5_fail_open_no_500(self):
        # Even if LLM has issues, must never 500
        r = _post("en", ["Проверка отказоустойчивости уникальная строка XYZ"])
        assert r.status_code == 200
        assert "translations" in r.json()

    def test_6_empty_strings_handled(self):
        r = _post("en", [])
        assert r.status_code == 200
        assert r.json() == {"translations": {}}

    def test_7_persistence(self):
        unique = f"Уникальная строка теста {int(time.time())}"
        r1 = _post("en", [unique])
        assert r1.status_code == 200
        v1 = r1.json()["translations"].get(unique)
        assert v1 and isinstance(v1, str)
        # Second call - must be cached and fast
        start = time.time()
        r2 = _post("en", [unique])
        elapsed_ms = (time.time() - start) * 1000
        assert r2.status_code == 200
        v2 = r2.json()["translations"].get(unique)
        assert v2 == v1, f"persistence mismatch: {v1!r} != {v2!r}"
        assert elapsed_ms < 1500, f"cache-hit latency too high: {elapsed_ms}ms"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
