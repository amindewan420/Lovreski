#!/usr/bin/env python3
"""Focused backend verification for Lovreski profile bug fixes."""
import base64
import io
import json
import os
import random
import string
import time
from pathlib import Path

import requests
from PIL import Image

BASE_URL = os.environ.get("BACKEND_URL", "http://localhost:8001/api")
OUT = Path("/app/test_reports/profile_bug_backend_results.json")
PASSWORD = "password123"

results = []

def record(name, passed, details="", status=None):
    item = {"name": name, "passed": bool(passed), "status": status, "details": details}
    results.append(item)
    print(("PASS" if passed else "FAIL"), name, status if status is not None else "", details[:300])


def post(path, token=None, **kwargs):
    headers = kwargs.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return requests.post(BASE_URL + path, headers=headers, timeout=60, **kwargs)


def put(path, token=None, **kwargs):
    headers = kwargs.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return requests.put(BASE_URL + path, headers=headers, timeout=60, **kwargs)


def register(gender="female", name=None):
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
    email = f"profilebug_{gender}_{suffix}@lovreski.ru"
    payload = {
        "email": email,
        "password": PASSWORD,
        "name": name or f"QA {gender} {suffix}",
        "gender": gender,
        "dob": "1998-05-15",
    }
    r = post("/auth/register", json=payload)
    if r.status_code != 200:
        raise RuntimeError(f"register failed {r.status_code}: {r.text}")
    data = r.json()
    return data["token"], data["user"]


def data_url_from_image(img: Image.Image, fmt="JPEG", quality=95):
    buf = io.BytesIO()
    save_kwargs = {"format": fmt}
    if fmt.upper() in {"JPEG", "WEBP"}:
        save_kwargs["quality"] = quality
    if fmt.upper() == "JPEG" and img.mode != "RGB":
        img = img.convert("RGB")
    img.save(buf, **save_kwargs)
    raw = buf.getvalue()
    mime = "jpeg" if fmt.upper() == "JPEG" else fmt.lower()
    return f"data:image/{mime};base64," + base64.b64encode(raw).decode(), len(raw)


def solid_color_data_url(size=(1200, 1200), color=(240, 20, 140)):
    return data_url_from_image(Image.new("RGB", size, color), "JPEG", quality=95)


def fetch_face_data_url(url, min_bytes=None, upscale=False):
    r = requests.get(url, timeout=30, headers={"User-Agent": "Lovreski-QA/1.0"})
    r.raise_for_status()
    img = Image.open(io.BytesIO(r.content)).convert("RGB")
    if upscale:
        # Build a high-entropy >5MB image while keeping a clear central face.
        noise = Image.effect_noise((4000, 5000), 80).convert("RGB")
        face = img.copy()
        face.thumbnail((1600, 1600), Image.LANCZOS)
        x = (noise.width - face.width) // 2
        y = (noise.height - face.height) // 2
        noise.paste(face, (x, y))
        img = noise
    return data_url_from_image(img, "JPEG", quality=95)


def upload_photo(token, data_url):
    return post("/profile/photo", token=token, json={"data_url": data_url})


def clear_photos(token):
    r = put("/profile", token=token, json={"photos": []})
    if r.status_code != 200:
        print("WARN could not clear photos", r.status_code, r.text[:100])


def main():
    health = requests.get(BASE_URL + "/health", timeout=10)
    record("backend health", health.status_code == 200, health.text, health.status_code)

    token, user = register("female")

    validation_cases = [
        ("about > 500 returns 422", {"about": "a" * 501}),
        ("job > 80 returns 422", {"job": "j" * 81}),
        ("education > 100 returns 422", {"education": "e" * 101}),
        ("language > 50 returns 422", {"language": "l" * 51}),
    ]
    for name, payload in validation_cases:
        r = put("/profile", token=token, json=payload)
        record(name, r.status_code == 422, r.text[:250], r.status_code)

    within_payload = {
        "about": "a" * 500,
        "job": "j" * 80,
        "education": "e" * 100,
        "language": "l" * 50,
        "height": 170,
        "goal": "Long-term commitment",
        "relationship": "Single",
        "kids": "No kids",
        "smoking": "Don't smoke",
        "alcohol": "Rarely",
        "interests": ["Travel", "Yoga", "Coffee and Tea"],
        "city": "QA City",
        "lat": 44.95,
        "lng": 34.10,
    }
    r = put("/profile", token=token, json=within_payload)
    ok_persist = r.status_code == 200 and all(r.json().get(k) == v for k, v in within_payload.items() if k != "interests") and r.json().get("interests") == within_payload["interests"]
    record("within-limit profile returns 200 and persists", ok_persist, r.text[:300], r.status_code)

    # Photo tests: use separate users to avoid four-photo cap interactions.
    female_token, _ = register("female")
    male_token, _ = register("male")

    # Large >5MB real female face image should be accepted, compressed to JPEG, and significantly smaller.
    try:
        large_face_url, input_bytes = fetch_face_data_url("https://images.unsplash.com/photo-1508214751196-bcfd4ca60f91?w=1600", upscale=True)
        record("generated large face image >5MB", input_bytes > 5 * 1024 * 1024, f"input_bytes={input_bytes}")
        t0 = time.time()
        r = upload_photo(female_token, large_face_url)
        elapsed = time.time() - t0
        if r.status_code == 200:
            data = r.json()
            first = data.get("photos", [None])[0]
            compressed_bytes = int(len(first.split(",", 1)[1]) * 3 / 4) if first and "," in first else None
            passed = bool(first and first.startswith("data:image/jpeg;base64,") and compressed_bytes and compressed_bytes < input_bytes * 0.7)
            details = f"elapsed={elapsed:.1f}s input_bytes={input_bytes} compressed_est={compressed_bytes} verification={data.get('verification')}"
        else:
            passed = False
            details = f"elapsed={elapsed:.1f}s body={r.text[:500]} input_bytes={input_bytes}"
        record("photo upload accepts >5MB and stores compressed JPEG", passed, details, r.status_code)
    except Exception as e:
        record("photo upload accepts >5MB and stores compressed JPEG", False, repr(e))

    # Solid color no-face must be rejected with exact message.
    noface_token, _ = register("female")
    solid_url, solid_bytes = solid_color_data_url()
    t0 = time.time()
    r = upload_photo(noface_token, solid_url)
    elapsed = time.time() - t0
    expected_msg = "Please upload a clear photo showing your face"
    passed = r.status_code == 422 and (r.json().get("detail") if r.headers.get("content-type", "").startswith("application/json") else "") == expected_msg
    record("solid color no-face photo rejected with exact message", passed, f"elapsed={elapsed:.1f}s body={r.text[:500]} input_bytes={solid_bytes}", r.status_code)

    # Female portrait against male profile must be rejected with exact mismatch message.
    try:
        female_face_url, female_bytes = fetch_face_data_url("https://images.unsplash.com/photo-1508214751196-bcfd4ca60f91?w=1200")
        t0 = time.time()
        r = upload_photo(male_token, female_face_url)
        elapsed = time.time() - t0
        expected = "Photo does not match your profile gender. Please upload a photo that matches your gender."
        detail = r.json().get("detail") if r.headers.get("content-type", "").startswith("application/json") else ""
        record("male user + clearly female face rejected with exact mismatch", r.status_code == 422 and detail == expected, f"elapsed={elapsed:.1f}s body={r.text[:500]} input_bytes={female_bytes}", r.status_code)
    except Exception as e:
        record("male user + clearly female face rejected with exact mismatch", False, repr(e))

    # Male face against male profile should be accepted.
    try:
        clear_photos(male_token)
        male_face_url, male_bytes = fetch_face_data_url("https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=1200")
        t0 = time.time()
        r = upload_photo(male_token, male_face_url)
        elapsed = time.time() - t0
        details = f"elapsed={elapsed:.1f}s body={r.text[:500]} input_bytes={male_bytes}"
        record("male user + clearly male face accepted", r.status_code == 200, details, r.status_code)
    except Exception as e:
        record("male user + clearly male face accepted", False, repr(e))

    OUT.write_text(json.dumps({"base_url": BASE_URL, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    failed = [r for r in results if not r["passed"]]
    print(f"Wrote {OUT}; {len(results)-len(failed)}/{len(results)} passed")
    return 1 if failed else 0

if __name__ == "__main__":
    raise SystemExit(main())
