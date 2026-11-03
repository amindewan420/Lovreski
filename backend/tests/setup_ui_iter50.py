# Creates TEST_ users for profile-gate UI test (iter50); prints JSON with tokens/ids
import os, uuid, json, requests
BASE = os.environ['REACT_APP_BACKEND_URL'].rstrip('/')
def reg(g, name):
    e = f"test_gateui_{uuid.uuid4().hex[:8]}@lovreski.ru"
    r = requests.post(f"{BASE}/api/auth/register", json={"email": e, "password": "password123", "name": name, "gender": g, "dob": "1996-03-03"}).json()
    return {"email": e, "token": r["token"], "id": r["user"]["user_id"]}
u = reg("female", "TEST_Incomplete")
t = reg("male", "TEST_Target")
h = {"Authorization": f"Bearer {t['token']}"}
requests.put(f"{BASE}/api/profile", headers=h, json={"photos": ["https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=400"], "goal": "relationship", "relationship": "single", "kids": "no", "smoking": "no", "alcohol": "no"})
print(json.dumps({"u": u, "t": t}))
