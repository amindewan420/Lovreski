"""
Lovreski Dating App — FastAPI Backend
All routes prefixed with /api. MongoDB storage. Uses custom user_id (UUID).
"""
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Response, Cookie, Header
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import math
import uuid
import bcrypt
import jwt as pyjwt
import httpx
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing import List, Optional, Literal
from datetime import datetime, timezone, timedelta

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

JWT_SECRET = os.environ.get('JWT_SECRET', 'change-me')
JWT_ALG = 'HS256'
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@lovreski.ru')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'ChangeMe!')

app = FastAPI(title="Lovreski API")
api = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ────────────────────────────── Helpers ──────────────────────────────
def now_utc():
    return datetime.now(timezone.utc)

def iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).isoformat()

def hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()

def check_pw(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except Exception:
        return False

def make_jwt(user_id: str, is_admin: bool = False) -> str:
    payload = {
        'user_id': user_id,
        'is_admin': is_admin,
        'exp': datetime.now(timezone.utc) + timedelta(days=30),
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

def decode_jwt(token: str) -> dict:
    return pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])

def haversine_km(lat1, lon1, lat2, lon2):
    if None in (lat1, lon1, lat2, lon2):
        return None
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

async def get_current_user(
    authorization: Optional[str] = Header(None),
    session_token: Optional[str] = Cookie(None),
) -> dict:
    token = None
    if authorization and authorization.lower().startswith('bearer '):
        token = authorization.split(' ', 1)[1]
    elif session_token:
        token = session_token
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    # Try session lookup first (Emergent OAuth or JWT)
    sess = await db.sessions.find_one({"session_token": token}, {"_id": 0})
    if sess:
        exp = sess.get('expires_at')
        if isinstance(exp, str):
            exp = datetime.fromisoformat(exp)
        if exp and exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp and exp < now_utc():
            raise HTTPException(status_code=401, detail="Session expired")
        user = await db.users.find_one({"user_id": sess['user_id']}, {"_id": 0, "password_hash": 0})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    # Try JWT
    try:
        payload = decode_jwt(token)
        user = await db.users.find_one({"user_id": payload['user_id']}, {"_id": 0, "password_hash": 0})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if not user.get('is_admin'):
        raise HTTPException(status_code=403, detail="Admin only")
    return user

# ────────────────────────────── Models ──────────────────────────────
class RegisterBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str
    gender: Literal['male', 'female']
    dob: str  # YYYY-MM-DD

class LoginBody(BaseModel):
    email: EmailStr
    password: str

class SessionExchange(BaseModel):
    session_id: str

class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    about: Optional[str] = None
    job: Optional[str] = None
    education: Optional[str] = None
    language: Optional[str] = None
    height: Optional[int] = None
    goal: Optional[str] = None
    relationship: Optional[str] = None
    kids: Optional[str] = None
    smoking: Optional[str] = None
    alcohol: Optional[str] = None
    interests: Optional[List[str]] = None
    photos: Optional[List[str]] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    city: Optional[str] = None
    show_me: Optional[str] = None  # 'male'|'female'|'both'
    age_min: Optional[int] = None
    age_max: Optional[int] = None
    distance_mode: Optional[str] = None  # 'limited'|'unlimited'
    auto_translate: Optional[bool] = None

class MessageBody(BaseModel):
    text: Optional[str] = None
    kind: Literal['text', 'emoji', 'image', 'gift', 'voice', 'video'] = 'text'
    media_url: Optional[str] = None
    gift_key: Optional[str] = None
    reply_to: Optional[str] = None

class ReportBody(BaseModel):
    target_user_id: str
    reason: str

class PurchaseBody(BaseModel):
    package_id: str
    phone: str
    sbp_balance: Optional[float] = None  # client-declared SBP balance for the mock balance check

class AdminPaymentAction(BaseModel):
    action: Literal['approve', 'reject']
    reason: Optional[str] = None

class TranslateBody(BaseModel):
    text: str
    target: str = 'ru'

class ForgotBody(BaseModel):
    email: EmailStr

class ResetBody(BaseModel):
    email: EmailStr
    otp: str
    new_password: str = Field(min_length=6)

# ────────────────────────────── Constants ──────────────────────────────
COIN_PACKAGES = [
    {"id": "p10", "coins": 10, "price": 300},
    {"id": "p25", "coins": 25, "price": 700},
    {"id": "p50", "coins": 50, "price": 1200},
    {"id": "p100", "coins": 100, "price": 2000},
]
MSG_COST = {"text": 1, "emoji": 1, "image": 5, "gift": 10, "voice": 10, "video": 10}
FREE_MSGS = 2

def calc_age(dob: str) -> int:
    try:
        y, m, d = map(int, dob.split('-'))
        today = datetime.now(timezone.utc).date()
        return today.year - y - ((today.month, today.day) < (m, d))
    except Exception:
        return 25

def user_public(u: dict, viewer: Optional[dict] = None) -> dict:
    age = calc_age(u.get('dob', '2000-01-01'))
    lat, lng = u.get('lat'), u.get('lng')
    dist = None
    if viewer and viewer.get('lat') and lat:
        d = haversine_km(viewer['lat'], viewer['lng'], lat, lng)
        dist = round(d, 1) if d is not None else None
    last_active = u.get('last_active')
    if isinstance(last_active, str):
        try:
            last_active = datetime.fromisoformat(last_active)
        except Exception:
            last_active = None
    online = False
    if last_active:
        if last_active.tzinfo is None:
            last_active = last_active.replace(tzinfo=timezone.utc)
        online = (now_utc() - last_active).total_seconds() < 180
    return {
        "user_id": u['user_id'],
        "name": u.get('name', 'Пользователь'),
        "age": age,
        "gender": u.get('gender'),
        "photos": u.get('photos', []),
        "about": u.get('about', ''),
        "job": u.get('job', ''),
        "education": u.get('education', ''),
        "language": u.get('language', ''),
        "height": u.get('height'),
        "goal": u.get('goal', ''),
        "relationship": u.get('relationship', ''),
        "kids": u.get('kids', ''),
        "smoking": u.get('smoking', ''),
        "alcohol": u.get('alcohol', ''),
        "interests": u.get('interests', []),
        "city": u.get('city', ''),
        "distance_km": dist,
        "online": online,
        "last_active": iso(last_active) if last_active else None,
        "is_premium": bool(u.get('is_premium')),
        "verified": bool(u.get('verified')),
        "popularity": u.get('popularity', 'medium'),
    }

# ────────────────────────────── Auth ──────────────────────────────
@api.post("/auth/register")
async def register(body: RegisterBody):
    existing = await db.users.find_one({"email": body.email.lower()})
    if existing:
        raise HTTPException(status_code=409, detail="Email already exists")
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    doc = {
        "user_id": user_id,
        "email": body.email.lower(),
        "password_hash": hash_pw(body.password),
        "name": body.name,
        "gender": body.gender,
        "dob": body.dob,
        "photos": [],
        "interests": [],
        "coins": 5,
        "is_premium": False,
        "verified": False,
        "is_admin": False,
        "show_me": 'female' if body.gender == 'male' else 'male',
        "age_min": 18,
        "age_max": 60,
        "distance_mode": "unlimited",
        "auto_translate": False,
        "created_at": iso(now_utc()),
        "last_active": iso(now_utc()),
        "popularity": "medium",
        "notif_push": {"messages": True, "likes": True, "matches": True, "visits": False, "who_liked": False},
        "notif_email": {"messages": False, "likes": False, "matches": True},
    }
    await db.users.insert_one(doc)
    token = make_jwt(user_id)
    doc.pop('password_hash', None)
    doc.pop('_id', None)
    return {"token": token, "user": doc}

@api.post("/auth/login")
async def login(body: LoginBody):
    # Admin special login
    if body.email.lower() == ADMIN_EMAIL.lower() and body.password == ADMIN_PASSWORD:
        admin = await db.users.find_one({"email": ADMIN_EMAIL.lower()}, {"_id": 0})
        if not admin:
            admin_id = f"user_{uuid.uuid4().hex[:12]}"
            admin = {
                "user_id": admin_id, "email": ADMIN_EMAIL.lower(), "password_hash": hash_pw(ADMIN_PASSWORD),
                "name": "Admin", "gender": "male", "dob": "1990-01-01", "photos": [],
                "interests": [], "coins": 999999, "is_premium": True, "verified": True, "is_admin": True,
                "created_at": iso(now_utc()), "last_active": iso(now_utc()),
            }
            await db.users.insert_one(admin)
        token = make_jwt(admin['user_id'], is_admin=True)
        admin.pop('password_hash', None); admin.pop('_id', None)
        return {"token": token, "user": admin}
    user = await db.users.find_one({"email": body.email.lower()})
    if not user:
        raise HTTPException(status_code=404, detail="Account not found. Please sign up first.")
    if not check_pw(body.password, user.get('password_hash', '')):
        raise HTTPException(status_code=401, detail="Incorrect password")
    await db.users.update_one({"user_id": user['user_id']}, {"$set": {"last_active": iso(now_utc())}})
    token = make_jwt(user['user_id'], is_admin=user.get('is_admin', False))
    user.pop('password_hash', None); user.pop('_id', None)
    return {"token": token, "user": user}

# ─────────── Password reset (OTP) ───────────
# NOTE: No email service is configured — the OTP is returned in the response as
# `dev_otp` so the frontend can auto-fill it (MOCKED delivery). Swap to Resend/
# SendGrid when a mail API key is provided.
import secrets

@api.post("/auth/forgot")
async def forgot_password(body: ForgotBody):
    email = body.email.lower()
    user = await db.users.find_one({"email": email}, {"_id": 0, "user_id": 1})
    # Rate limit: max 3 OTP requests per email per 15 minutes
    since = now_utc() - timedelta(minutes=15)
    recent = await db.password_reset_otps.count_documents({
        "email": email, "created_at": {"$gte": iso(since)},
    })
    if recent >= 3:
        raise HTTPException(status_code=429, detail="Too many reset requests. Try again in 15 minutes.")
    # Always generate an OTP even if user is missing to avoid email enumeration,
    # but only persist when the user exists.
    otp = f"{secrets.randbelow(1000000):06d}"
    if user:
        await db.password_reset_otps.insert_one({
            "email": email,
            "otp": otp,
            "used": False,
            "created_at": iso(now_utc()),
            "expires_at": iso(now_utc() + timedelta(minutes=10)),
        })
    # MOCKED: no email sending — return OTP directly so the UI can auto-fill it.
    return {"ok": True, "dev_otp": otp if user else None, "message": "OTP отправлен (в этой сборке возвращается в ответе для авто-заполнения)"}

@api.post("/auth/reset")
async def reset_password(body: ResetBody):
    email = body.email.lower()
    rec = await db.password_reset_otps.find_one(
        {"email": email, "otp": body.otp, "used": False},
        sort=[("created_at", -1)],
    )
    if not rec:
        raise HTTPException(status_code=400, detail="Invalid OTP")
    exp = rec.get('expires_at')
    if isinstance(exp, str):
        try:
            exp_dt = datetime.fromisoformat(exp)
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            if exp_dt < now_utc():
                raise HTTPException(status_code=400, detail="OTP expired. Request a new one.")
        except ValueError:
            raise HTTPException(status_code=400, detail="OTP expired. Request a new one.")
    # Update password and invalidate OTP (one-time-use)
    new_hash = hash_pw(body.new_password)
    result = await db.users.update_one({"email": email}, {"$set": {"password_hash": new_hash}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Account not found")
    await db.password_reset_otps.update_one({"_id": rec['_id']}, {"$set": {"used": True, "used_at": iso(now_utc())}})
    return {"ok": True}

@api.post("/auth/session")
async def exchange_session(body: SessionExchange, response: Response):
    # REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    async with httpx.AsyncClient(timeout=15) as h:
        r = await h.get(
            "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
            headers={"X-Session-ID": body.session_id},
        )
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="OAuth session invalid")
    data = r.json()
    email = data['email'].lower()
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        user = {
            "user_id": user_id, "email": email, "name": data.get('name', email.split('@')[0]),
            "gender": "female", "dob": "1998-01-01",
            "photos": [data['picture']] if data.get('picture') else [],
            "interests": [], "coins": 5, "is_premium": False, "verified": True,
            "is_admin": False, "show_me": "male", "age_min": 18, "age_max": 60,
            "distance_mode": "unlimited", "auto_translate": False,
            "created_at": iso(now_utc()), "last_active": iso(now_utc()),
            "popularity": "medium",
            "notif_push": {"messages": True, "likes": True, "matches": True, "visits": False, "who_liked": False},
            "notif_email": {"messages": False, "likes": False, "matches": True},
        }
        await db.users.insert_one(user)
    session_token = data['session_token']
    expires_at = now_utc() + timedelta(days=7)
    await db.sessions.insert_one({
        "user_id": user['user_id'], "session_token": session_token,
        "expires_at": iso(expires_at), "created_at": iso(now_utc()),
    })
    response.set_cookie("session_token", session_token, httponly=True, secure=True, samesite="none", path="/", max_age=7*24*3600)
    user.pop('password_hash', None); user.pop('_id', None)
    return {"user": user, "token": session_token}

@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return user

@api.post("/auth/logout")
async def logout(response: Response, session_token: Optional[str] = Cookie(None)):
    if session_token:
        await db.sessions.delete_one({"session_token": session_token})
    response.delete_cookie("session_token", path="/")
    return {"ok": True}

# ────────────────────────────── Profile ──────────────────────────────
@api.put("/profile")
async def update_profile(body: ProfileUpdate, user: dict = Depends(get_current_user)):
    update = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if 'interests' in update and len(update['interests']) > 10:
        raise HTTPException(status_code=400, detail="Максимум 10 интересов")
    if 'photos' in update and len(update['photos']) > 4:
        raise HTTPException(status_code=400, detail="Максимум 4 фотографии")
    update['last_active'] = iso(now_utc())
    await db.users.update_one({"user_id": user['user_id']}, {"$set": update})
    fresh = await db.users.find_one({"user_id": user['user_id']}, {"_id": 0, "password_hash": 0})
    return fresh

@api.get("/profile/{user_id}")
async def get_profile(user_id: str, user: dict = Depends(get_current_user)):
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Profile not found")
    return user_public(target, viewer=user)

# ────────────────────────────── Discovery / Home / Likes ──────────────────────────────
async def _filter_feed(user: dict, limit: int, skip: int = 0):
    show_me = user.get('show_me', 'both')
    gender_q: dict = {}
    if show_me in ('male', 'female'):
        gender_q = {"gender": show_me}
    blocked = user.get('blocked', []) + [user['user_id']]
    # Get already-liked/passed
    swipes = await db.likes.find({"from_user": user['user_id']}, {"_id": 0, "to_user": 1}).to_list(2000)
    already = {s['to_user'] for s in swipes}
    already.update(blocked)
    q = {"user_id": {"$nin": list(already)}, "is_admin": {"$ne": True}, **gender_q}
    users = await db.users.find(q, {"_id": 0, "password_hash": 0}).skip(skip).limit(limit * 3).to_list(limit * 3)
    # Priority sort
    def score(u):
        la = u.get('last_active')
        if isinstance(la, str):
            try: la = datetime.fromisoformat(la)
            except Exception: la = None
        if la and la.tzinfo is None: la = la.replace(tzinfo=timezone.utc)
        online_bonus = 0
        if la:
            secs = (now_utc() - la).total_seconds()
            if secs < 180: online_bonus = 1000
            elif secs < 3600: online_bonus = 500
            elif secs < 86400: online_bonus = 200
        dist = 0
        if user.get('lat') and u.get('lat'):
            d = haversine_km(user['lat'], user['lng'], u['lat'], u['lng']) or 9999
            dist = -d
        return online_bonus + dist
    users.sort(key=score, reverse=True)
    return [user_public(u, viewer=user) for u in users[:limit]]

@api.get("/home/feed")
async def home_feed(user: dict = Depends(get_current_user), limit: int = 6, skip: int = 0):
    return await _filter_feed(user, limit, skip)

@api.get("/discover/feed")
async def discover_feed(user: dict = Depends(get_current_user), limit: int = 20):
    return await _filter_feed(user, limit)

@api.post("/like/{target_id}")
async def like_user(target_id: str, user: dict = Depends(get_current_user)):
    if target_id == user['user_id']:
        raise HTTPException(status_code=400, detail="Нельзя лайкнуть себя")
    target = await db.users.find_one({"user_id": target_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    await db.likes.update_one(
        {"from_user": user['user_id'], "to_user": target_id},
        {"$set": {"from_user": user['user_id'], "to_user": target_id, "type": "like", "created_at": iso(now_utc())}},
        upsert=True,
    )
    reverse = await db.likes.find_one({"from_user": target_id, "to_user": user['user_id'], "type": "like"})
    is_match = bool(reverse)
    if is_match:
        pair = sorted([user['user_id'], target_id])
        await db.matches.update_one(
            {"pair": pair},
            {"$set": {"pair": pair, "users": pair, "created_at": iso(now_utc())}},
            upsert=True,
        )
    return {"ok": True, "match": is_match, "target": user_public(target, viewer=user)}

@api.post("/pass/{target_id}")
async def pass_user(target_id: str, user: dict = Depends(get_current_user)):
    await db.likes.update_one(
        {"from_user": user['user_id'], "to_user": target_id},
        {"$set": {"from_user": user['user_id'], "to_user": target_id, "type": "pass", "created_at": iso(now_utc())}},
        upsert=True,
    )
    return {"ok": True}

@api.get("/likes/received")
async def likes_received(user: dict = Depends(get_current_user)):
    likes = await db.likes.find({"to_user": user['user_id'], "type": "like"}, {"_id": 0}).to_list(500)
    ids = [l['from_user'] for l in likes]
    users = await db.users.find({"user_id": {"$in": ids}}, {"_id": 0, "password_hash": 0}).to_list(500)
    return [user_public(u, viewer=user) for u in users]

@api.get("/likes/sent")
async def likes_sent(user: dict = Depends(get_current_user)):
    likes = await db.likes.find({"from_user": user['user_id'], "type": "like"}, {"_id": 0}).to_list(500)
    ids = [l['to_user'] for l in likes]
    users = await db.users.find({"user_id": {"$in": ids}}, {"_id": 0, "password_hash": 0}).to_list(500)
    return [user_public(u, viewer=user) for u in users]

@api.get("/likes/matches")
async def likes_matches(user: dict = Depends(get_current_user)):
    matches = await db.matches.find({"users": user['user_id']}, {"_id": 0}).to_list(500)
    ids = []
    for m in matches:
        for uid in m['users']:
            if uid != user['user_id']:
                ids.append(uid)
    users = await db.users.find({"user_id": {"$in": ids}}, {"_id": 0, "password_hash": 0}).to_list(500)
    return [user_public(u, viewer=user) for u in users]

# ────────────────────────────── Chat ──────────────────────────────
def chat_id(a: str, b: str) -> str:
    return "chat_" + "_".join(sorted([a, b]))

@api.get("/chats")
async def list_chats(user: dict = Depends(get_current_user)):
    msgs = await db.messages.find({"participants": user['user_id']}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    chats: dict = {}
    for m in msgs:
        cid = m['chat_id']
        if cid not in chats:
            chats[cid] = m
    result = []
    for cid, last in chats.items():
        other_id = [p for p in last['participants'] if p != user['user_id']][0]
        other = await db.users.find_one({"user_id": other_id}, {"_id": 0, "password_hash": 0})
        if not other: continue
        unread = await db.messages.count_documents({"chat_id": cid, "to_user": user['user_id'], "read": False})
        result.append({
            "chat_id": cid,
            "user": user_public(other, viewer=user),
            "last_message": last,
            "unread": unread,
        })
    result.sort(key=lambda x: x['last_message']['created_at'], reverse=True)
    return result

@api.get("/chats/{other_id}/messages")
async def get_messages(other_id: str, user: dict = Depends(get_current_user), limit: int = 100):
    cid = chat_id(user['user_id'], other_id)
    msgs = await db.messages.find({"chat_id": cid}, {"_id": 0}).sort("created_at", 1).to_list(limit)
    await db.messages.update_many({"chat_id": cid, "to_user": user['user_id']}, {"$set": {"read": True}})
    # Add locked flag: if user has no premium & no coins & msg is beyond free window from partner → unlock via premium
    return msgs

@api.post("/chats/{other_id}/send")
async def send_message(other_id: str, body: MessageBody, user: dict = Depends(get_current_user)):
    other = await db.users.find_one({"user_id": other_id}, {"_id": 0})
    if not other:
        raise HTTPException(status_code=404, detail="User not found")
    cost = MSG_COST.get(body.kind, 1)
    cid = chat_id(user['user_id'], other_id)
    # Count sent messages by user in this chat
    sent_count = await db.messages.count_documents({"chat_id": cid, "from_user": user['user_id']})
    is_admin_sender = user.get('is_admin', False)
    needs_pay = sent_count >= FREE_MSGS and not is_admin_sender
    if needs_pay:
        if not user.get('is_premium') and user.get('coins', 0) < cost:
            raise HTTPException(status_code=402, detail=f"Недостаточно монет. Требуется {cost}, а у вас {user.get('coins', 0)}. Оформите Premium.")
        # deduct coins (even if premium, we still deduct — matches problem statement)
        if user.get('coins', 0) >= cost:
            await db.users.update_one({"user_id": user['user_id']}, {"$inc": {"coins": -cost}})
        elif not user.get('is_premium'):
            raise HTTPException(status_code=402, detail="Недостаточно монет")
    msg = {
        "message_id": f"msg_{uuid.uuid4().hex[:12]}",
        "chat_id": cid,
        "participants": sorted([user['user_id'], other_id]),
        "from_user": user['user_id'],
        "to_user": other_id,
        "kind": body.kind,
        "text": body.text or "",
        "media_url": body.media_url,
        "gift_key": body.gift_key,
        "reply_to": body.reply_to,
        "read": False,
        "created_at": iso(now_utc()),
    }
    await db.messages.insert_one(msg)
    msg.pop('_id', None)
    return msg

@api.delete("/messages/{message_id}")
async def delete_message(message_id: str, user: dict = Depends(get_current_user)):
    # Deletion costs 1 coin per problem statement
    m = await db.messages.find_one({"message_id": message_id, "from_user": user['user_id']}, {"_id": 0})
    if not m:
        raise HTTPException(status_code=404, detail="Message not found")
    if user.get('coins', 0) < 1 and not user.get('is_admin'):
        raise HTTPException(status_code=402, detail="Недостаточно монет для удаления")
    if not user.get('is_admin'):
        await db.users.update_one({"user_id": user['user_id']}, {"$inc": {"coins": -1}})
    await db.messages.delete_one({"message_id": message_id})
    return {"ok": True}

# ────────────────────────────── Premium & Coins ──────────────────────────────
@api.get("/coins/packages")
async def coin_packages():
    # Allow admin to override packages + SBP phone via settings
    s = await db.settings.find_one({"key": "app"}, {"_id": 0}) or {}
    packages = s.get('packages') or COIN_PACKAGES
    sbp_phone = s.get('sbp_phone') or os.environ.get('SBP_PHONE', '')
    return {"packages": packages, "sbp_phone": sbp_phone, "bank": "Sberbank"}

@api.post("/coins/purchase")
async def purchase(body: PurchaseBody, user: dict = Depends(get_current_user)):
    s = await db.settings.find_one({"key": "app"}, {"_id": 0}) or {}
    packages = s.get('packages') or COIN_PACKAGES
    pkg = next((p for p in packages if p['id'] == body.package_id), None)
    if not pkg:
        raise HTTPException(status_code=400, detail="Пакет не найден")
    # Mock SBP balance check: if the client reports a numeric balance, enforce it
    if body.sbp_balance is not None and body.sbp_balance < pkg['price']:
        raise HTTPException(status_code=402, detail=f"Insufficient Balance! Please top up your SBP account first. Требуется {pkg['price']} ₽")
    tx = {
        "tx_id": f"tx_{uuid.uuid4().hex[:12]}",
        "user_id": user['user_id'],
        "user_email": user.get('email'),
        "user_name": user.get('name'),
        "package_id": pkg['id'],
        "coins": pkg['coins'],
        "amount_rub": pkg['price'],
        "phone": body.phone,
        "payment_method": "SBP (Sberbank)",
        "status": "pending",
        "created_at": iso(now_utc()),
    }
    await db.transactions.insert_one(tx)
    tx.pop('_id', None)
    return tx

@api.get("/coins/transactions")
async def user_transactions(user: dict = Depends(get_current_user)):
    tx = await db.transactions.find({"user_id": user['user_id']}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return tx

@api.get("/coins/balance")
async def coin_balance(user: dict = Depends(get_current_user)):
    fresh = await db.users.find_one({"user_id": user['user_id']}, {"_id": 0})
    return {"coins": fresh.get('coins', 0), "is_premium": fresh.get('is_premium', False)}

# ────────────────────────────── Reports ──────────────────────────────
@api.post("/report")
async def report_user(body: ReportBody, user: dict = Depends(get_current_user)):
    await db.reports.insert_one({
        "report_id": f"rep_{uuid.uuid4().hex[:12]}",
        "from_user": user['user_id'],
        "target_user": body.target_user_id,
        "reason": body.reason,
        "status": "open",
        "created_at": iso(now_utc()),
    })
    return {"ok": True}

@api.post("/block/{target_id}")
async def block(target_id: str, user: dict = Depends(get_current_user)):
    await db.users.update_one({"user_id": user['user_id']}, {"$addToSet": {"blocked": target_id}})
    return {"ok": True}

# ────────────────────────────── Admin ──────────────────────────────
@api.get("/admin/stats")
async def admin_stats(_: dict = Depends(require_admin)):
    total_users = await db.users.count_documents({"is_admin": {"$ne": True}})
    premium_users = await db.users.count_documents({"is_premium": True, "is_admin": {"$ne": True}})
    pending = await db.transactions.count_documents({"status": "pending"})
    approved = await db.transactions.find({"status": "approved"}, {"_id": 0}).to_list(5000)
    revenue = sum(t.get('amount_rub', 0) for t in approved)
    month_start = now_utc().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    approved_month = sum(1 for t in approved if datetime.fromisoformat(t['created_at']) >= month_start)
    # Timeseries daily (last 24h buckets)
    daily = [0] * 24
    revenue_daily = [0] * 24
    today_start = now_utc().replace(hour=0, minute=0, second=0, microsecond=0)
    for t in approved:
        ts = datetime.fromisoformat(t['created_at'])
        if ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)
        if ts >= today_start:
            daily[ts.hour] += 1
            revenue_daily[ts.hour] += t.get('amount_rub', 0)
    # Monthly (last 30 days)
    monthly = [0] * 30
    revenue_monthly = [0] * 30
    for t in approved:
        ts = datetime.fromisoformat(t['created_at'])
        if ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)
        days_ago = (now_utc() - ts).days
        if 0 <= days_ago < 30:
            monthly[29 - days_ago] += 1
            revenue_monthly[29 - days_ago] += t.get('amount_rub', 0)
    # Yearly (12 months)
    yearly = [0] * 12
    revenue_yearly = [0] * 12
    for t in approved:
        ts = datetime.fromisoformat(t['created_at'])
        if ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)
        if ts.year == now_utc().year:
            yearly[ts.month - 1] += 1
            revenue_yearly[ts.month - 1] += t.get('amount_rub', 0)
    return {
        "total_users": total_users, "premium_users": premium_users,
        "pending": pending, "revenue": revenue, "approved_month": approved_month,
        "daily": daily, "revenue_daily": revenue_daily,
        "monthly": monthly, "revenue_monthly": revenue_monthly,
        "yearly": yearly, "revenue_yearly": revenue_yearly,
    }

@api.get("/admin/payments")
async def admin_payments(status: str = "all", _: dict = Depends(require_admin)):
    q = {} if status == "all" else {"status": status}
    tx = await db.transactions.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return tx

@api.post("/admin/payments/{tx_id}")
async def admin_action_payment(tx_id: str, body: AdminPaymentAction, _: dict = Depends(require_admin)):
    tx = await db.transactions.find_one({"tx_id": tx_id}, {"_id": 0})
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if body.action == "approve":
        await db.transactions.update_one({"tx_id": tx_id}, {"$set": {"status": "approved", "approved_at": iso(now_utc())}})
        await db.users.update_one(
            {"user_id": tx['user_id']},
            {"$inc": {"coins": tx['coins']}, "$set": {"is_premium": True, "premium_until": iso(now_utc() + timedelta(days=30))}},
        )
    else:
        await db.transactions.update_one({"tx_id": tx_id}, {"$set": {"status": "rejected", "reject_reason": body.reason or "Отклонено администратором"}})
    return {"ok": True}

@api.get("/admin/reports")
async def admin_reports(_: dict = Depends(require_admin)):
    reports = await db.reports.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    # Aggregate reports per target
    agg: dict = {}
    for r in reports:
        t = r['target_user']
        agg.setdefault(t, {"target_user": t, "count": 0, "reasons": [], "last": r['created_at']})
        agg[t]['count'] += 1
        agg[t]['reasons'].append(r['reason'])
    out = []
    for uid, data in agg.items():
        u = await db.users.find_one({"user_id": uid}, {"_id": 0, "password_hash": 0})
        if u:
            data['user'] = user_public(u)
            out.append(data)
    return out

@api.get("/admin/users")
async def admin_users(_: dict = Depends(require_admin), limit: int = 100):
    users = await db.users.find({"is_admin": {"$ne": True}}, {"_id": 0, "password_hash": 0}).limit(limit).to_list(limit)
    return [user_public(u) for u in users]

@api.post("/admin/users/{user_id}/deactivate")
async def admin_deactivate(user_id: str, _: dict = Depends(require_admin)):
    await db.users.delete_one({"user_id": user_id})
    await db.sessions.delete_many({"user_id": user_id})
    await db.messages.delete_many({"$or": [{"from_user": user_id}, {"to_user": user_id}]})
    await db.likes.delete_many({"$or": [{"from_user": user_id}, {"to_user": user_id}]})
    return {"ok": True}

@api.post("/admin/users/{user_id}/ban")
async def admin_ban(user_id: str, days: int = 7, _: dict = Depends(require_admin)):
    await db.users.update_one({"user_id": user_id}, {"$set": {"banned_until": iso(now_utc() + timedelta(days=days))}})
    return {"ok": True}

@api.put("/admin/settings")
async def admin_settings_update(data: dict, _: dict = Depends(require_admin)):
    await db.settings.update_one({"key": "app"}, {"$set": {"key": "app", **data, "updated_at": iso(now_utc())}}, upsert=True)
    return {"ok": True}

@api.get("/admin/settings")
async def admin_settings_get(_: dict = Depends(require_admin)):
    s = await db.settings.find_one({"key": "app"}, {"_id": 0}) or {}
    return s

# ────────────────────────────── Translation ──────────────────────────────
@api.post("/translate")
async def translate(body: TranslateBody, user: dict = Depends(get_current_user)):
    """Auto-translate text using Emergent LLM key."""
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore
        chat = LlmChat(
            api_key=os.environ['EMERGENT_LLM_KEY'],
            session_id=f"trans_{user['user_id']}",
            system_message=f"You are a professional translator. Detect the source language and translate the user text to {body.target}. Respond ONLY with the translated text, no explanations, no quotes.",
        ).with_model("openai", "gpt-4o-mini")
        resp = await chat.send_message(UserMessage(text=body.text))
        return {"translated": str(resp).strip(), "target": body.target}
    except Exception as e:
        logger.exception("translate failed")
        raise HTTPException(status_code=500, detail=str(e))

# ────────────────────────────── Demo seed ──────────────────────────────
@api.post("/demo/seed")
async def seed_demo():
    existing = await db.users.count_documents({"is_demo": True})
    if existing >= 15:
        return {"ok": True, "already": existing}
    demo_photos_f = [
        "https://images.unsplash.com/photo-1489278353717-f64c6ee8a4d2?w=600",
        "https://images.unsplash.com/photo-1662850886700-4ec19bd30d11?w=600",
        "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=600",
        "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=600",
        "https://images.unsplash.com/photo-1508214751196-bcfd4ca60f91?w=600",
        "https://images.unsplash.com/photo-1517841905240-472988babdf9?w=600",
        "https://images.unsplash.com/photo-1524504388940-b1c1722653e1?w=600",
        "https://images.unsplash.com/photo-1531123897727-8f129e1688ce?w=600",
    ]
    demo_photos_m = [
        "https://images.unsplash.com/photo-1623366302587-b38b1ddaefd9?w=600",
        "https://images.unsplash.com/photo-1568602471122-7832951cc4c5?w=600",
        "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=600",
        "https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?w=600",
        "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=600",
        "https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?w=600",
        "https://images.unsplash.com/photo-1552058544-f2b08422138a?w=600",
        "https://images.unsplash.com/photo-1522075469751-3a6694fb2f61?w=600",
    ]
    female_names = ["Анна", "Мария", "Елена", "Ольга", "Наталья", "Ирина", "Екатерина", "Юлия"]
    male_names = ["Алексей", "Дмитрий", "Иван", "Максим", "Сергей", "Артём", "Никита", "Роман"]
    cities = [
        ("Симферополь", 44.9521, 34.1024),
        ("Санкт-Петербург", 59.9343, 30.3351),
        ("Казань", 55.7887, 49.1221),
        ("Новосибирск", 55.0084, 82.9357),
        ("Сочи", 43.5855, 39.7231),
        ("Москва", 55.7558, 37.6173),
    ]
    interests_pool = ["Путешествия", "Кофе", "Йога", "Фитнес", "Фотография", "Музыка",
                       "Живопись", "Кулинария", "Книги", "Кино", "Танцы", "Плавание",
                       "Медитация", "Языки", "IT", "Психология", "Мода", "Дизайн"]
    goals = ["Долгосрочные отношения", "Общение и новые знакомства", "Дружба", "Новый опыт"]
    import random
    for i in range(16):
        is_female = i < 8
        name = (female_names if is_female else male_names)[i % 8]
        photo = (demo_photos_f if is_female else demo_photos_m)[i % 8]
        city = random.choice(cities)
        age = random.randint(21, 38)
        year = now_utc().year - age
        uid = f"demo_{uuid.uuid4().hex[:10]}"
        doc = {
            "user_id": uid,
            "email": f"demo{i}@lovreski.ru",
            "name": name,
            "gender": "female" if is_female else "male",
            "dob": f"{year}-06-15",
            "photos": [photo],
            "about": random.choice([
                "Люблю путешествия и хорошие книги. Ищу интересного собеседника.",
                "Творческая натура, обожаю кофе по утрам и вечерние прогулки.",
                "Активный образ жизни, спорт, музыка. Открыт(а) для новых знакомств.",
                "Простая девушка/парень с добрым сердцем. Ценю искренность.",
            ]),
            "job": random.choice(["Дизайнер", "Разработчик", "Маркетолог", "Врач", "Фотограф", "Учитель"]),
            "education": random.choice(["Высшее", "МГУ", "СПбГУ", "КФУ"]),
            "language": random.choice(["Русский, English", "Русский", "Русский, Español"]),
            "height": random.randint(160, 190),
            "goal": random.choice(goals),
            "relationship": "Single",
            "kids": random.choice(["No kids", "I have kids", "No answer"]),
            "smoking": random.choice(["Don't smoke", "Rarely", "Not to answer"]),
            "alcohol": random.choice(["Don't drink", "Rarely", "Drink"]),
            "interests": random.sample(interests_pool, k=5),
            "city": city[0],
            "lat": city[1] + random.uniform(-0.1, 0.1),
            "lng": city[2] + random.uniform(-0.1, 0.1),
            "coins": random.randint(0, 50),
            "is_premium": random.random() < 0.3,
            "verified": random.random() < 0.5,
            "is_admin": False,
            "is_demo": True,
            "popularity": random.choice(["low", "medium", "high"]),
            "show_me": "male" if is_female else "female",
            "age_min": 18, "age_max": 60, "distance_mode": "unlimited",
            "created_at": iso(now_utc()),
            "last_active": iso(now_utc() - timedelta(minutes=random.randint(0, 4000))),
        }
        await db.users.insert_one(doc)
    return {"ok": True, "seeded": 16}

@api.get("/health")
async def health():
    return {"ok": True}

# ────────────────────────────── App wiring ──────────────────────────────
app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def on_start():
    await db.users.create_index("user_id", unique=True)
    await db.users.create_index("email")
    await db.sessions.create_index("session_token", unique=True)
    await db.likes.create_index([("from_user", 1), ("to_user", 1)], unique=True)
    await db.messages.create_index("chat_id")

@app.on_event("shutdown")
async def on_stop():
    client.close()
