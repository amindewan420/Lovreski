# Seed Russian chat messages between match_a and match_b for translation UI tests
import os, sys, json, requests
U = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
A_ID, B_ID = "user_4a6c98d1eb2b", "user_3e49e86330a7"


def login(e):
    return requests.post(f"{U}/api/auth/login", json={"email": e, "password": "password123"}).json()["token"]


ta, tb = login("match_a@lovreski.ru"), login("match_b@lovreski.ru")
adm = requests.post(f"{U}/api/admin/login", json={"email": "admin@lovreski.ru", "password": "LovreskiAdmin2026!"}).json()["token"]


def send(tok, other, payload):
    r = requests.post(f"{U}/api/chats/{other}/send", json=payload, headers={"Authorization": f"Bearer {tok}"})
    if r.status_code == 402:
        for uid in (A_ID, B_ID):
            x = requests.post(f"{U}/api/admin/users/add-coins", json={"user_id": uid, "coins": 200, "reason": "TEST iter44"}, headers={"Authorization": f"Bearer {adm}"})
            print("add-coins", x.status_code, x.text[:120])
        r = requests.post(f"{U}/api/chats/{other}/send", json=payload, headers={"Authorization": f"Bearer {tok}"})
    print(r.status_code, r.text[:160])
    return r.json() if r.ok else {}


if sys.argv[1:] == ["realtime"]:
    send(tb, A_ID, {"kind": "text", "text": "Привет, как твои дела сегодня?"})
    sys.exit()
m1 = send(tb, A_ID, {"kind": "text", "text": "Доброе утро! Как спалось?"})
send(tb, A_ID, {"kind": "text", "text": "Я сегодня иду гулять в парк с собакой"})
send(tb, A_ID, {"kind": "location", "lat": 55.76, "lng": 37.6, "place": "Кафе у Красной площади"})
mid = (m1.get("message") or m1).get("message_id")
send(ta, B_ID, {"kind": "text", "text": "Отлично, спасибо! Давай встретимся вечером", "reply_to": mid})
print("reply_to", mid)
