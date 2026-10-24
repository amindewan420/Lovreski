# Seed helper for iter48 UI test: fresh user with pending/verified/rejected receipts
import os, json, uuid
import requests
from test_hide_submission_iter48 import _png, BASE_URL, ADMIN, H

email = f"test_ui_hide_{uuid.uuid4().hex[:6]}@lovreski.ru"
t = requests.post(f"{BASE_URL}/api/auth/register", json={"email": email, "password": "password123", "name": "TEST UI Hide", "gender": "male", "dob": "1995-01-01"}).json()["token"]
adm = requests.post(f"{BASE_URL}/api/admin/login", json=ADMIN).json()["token"]
subs = [requests.post(f"{BASE_URL}/api/support/receipt", headers=H(t), json={"receipt_data_url": _png(), "message": f"TEST_ui_{i}"}).json()["submission_id"] for i in range(4)]
requests.post(f"{BASE_URL}/api/admin/support/{subs[0]}/approve", headers=H(adm), json={"coins": 10, "reason": "TEST"})
requests.post(f"{BASE_URL}/api/admin/support/{subs[1]}/reject", headers=H(adm), json={"reason": "TEST ui reject"})
print(json.dumps({"email": email, "token": t, "verified": subs[0], "rejected": subs[1], "pending": subs[2], "pending2": subs[3]}))
