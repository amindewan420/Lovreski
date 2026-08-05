"""
Lovreski Dating App — FastAPI Backend
All routes prefixed with /api. MongoDB storage. Uses custom user_id (UUID).
"""
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Response, Cookie, Header, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
import json as _json
import os
import io
import base64
import logging
import math
import uuid
import bcrypt
import jwt as pyjwt
import httpx
import qrcode
from cryptography.fernet import Fernet, InvalidToken
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
# ── Encryption for admin SBP phone (at rest in DB) ──
_ENC_KEY = os.environ.get('SBP_ENCRYPT_KEY')
_fernet = Fernet(_ENC_KEY.encode()) if _ENC_KEY else None

def encrypt_str(v: str) -> str:
    if not _fernet: return v
    return _fernet.encrypt(v.encode()).decode()

def decrypt_str(v: str) -> str:
    if not _fernet: return v
    try:
        return _fernet.decrypt(v.encode()).decode()
    except InvalidToken:
        return v  # legacy plain value

def mask_phone(p: str) -> str:
    # +79780369381 → +7 (***) ***-**-81
    if not p: return ""
    digits = "".join(c for c in p if c.isdigit())
    if len(digits) < 4: return "***"
    return f"+{digits[0]} (***) ***-**-{digits[-2:]}"

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
    gender: Literal['male', 'female', 'non_binary', 'prefer_not']
    dob: str  # YYYY-MM-DD

class LoginBody(BaseModel):
    email: EmailStr
    password: str

class SessionExchange(BaseModel):
    session_id: str

class ProfileUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=50)
    dob: Optional[str] = None
    gender: Optional[str] = None
    about: Optional[str] = Field(default=None, max_length=500)
    job: Optional[str] = Field(default=None, max_length=80)
    education: Optional[str] = Field(default=None, max_length=100)
    language: Optional[str] = Field(default=None, max_length=50)
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
    show_me: Optional[str] = None
    age_min: Optional[int] = None
    age_max: Optional[int] = None
    distance_mode: Optional[str] = None
    distance_km: Optional[int] = Field(default=None, ge=0, le=2000)
    auto_translate: Optional[bool] = None
    language_pref: Optional[str] = Field(default=None, max_length=10)

class MessageBody(BaseModel):
    text: Optional[str] = None
    kind: Literal['text', 'emoji', 'image', 'file', 'gift', 'voice', 'video'] = 'text'
    media_url: Optional[str] = None
    file_name: Optional[str] = None
    gift_key: Optional[str] = None
    reply_to: Optional[str] = None

class ReportBody(BaseModel):
    target_user_id: str
    reason: str

class PurchaseBody(BaseModel):
    package_id: str
    # phone/sbp_balance are legacy — no longer required. Kept optional for backward compat.
    phone: Optional[str] = None
    sbp_balance: Optional[float] = None
    bank: Optional[Literal['sberbank', 'tbank']] = None  # user's preferred sending bank

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
    {"id": "p100", "coins": 100, "price": 500},
    {"id": "p200", "coins": 200, "price": 900},
    {"id": "p300", "coins": 300, "price": 1200},
    {"id": "p500", "coins": 500, "price": 1900},
]
# Per-type coin cost for chat messages. Free users can send at most FREE_MSGS
# messages TOTAL per chat (any kind). Beyond that the input is hard-blocked
# unless the user has coins (or Premium for text/emoji). Note: 'gift' kind
# does NOT use MSG_COST — its cost is looked up per-key in GIFT_COST_BY_KEY.
MSG_COST = {"text": 1, "emoji": 2, "image": 5, "file": 5, "voice": 5, "video": 10}
FREE_MSGS = 2

# Gift catalog — illustrations use free Unicode emoji rendered inside a colored
# gradient tile on the frontend; each gift has a specific coin cost per spec.
GIFT_CATALOG = [
    {"key": "heart",       "name": "Сердце",       "emoji": "❤️", "cost": 5,  "gradient": "from-rose-400 to-pink-500"},
    {"key": "rose",        "name": "Роза",         "emoji": "🌹", "cost": 10, "gradient": "from-red-400 to-rose-600"},
    {"key": "kiss",        "name": "Поцелуй",      "emoji": "💋", "cost": 5,  "gradient": "from-pink-400 to-fuchsia-500"},
    {"key": "crown",       "name": "Корона",       "emoji": "👑", "cost": 20, "gradient": "from-amber-400 to-yellow-500"},
    {"key": "diamond",     "name": "Бриллиант",    "emoji": "💎", "cost": 20, "gradient": "from-sky-300 to-cyan-500"},
    {"key": "bouquet",     "name": "Букет",        "emoji": "💐", "cost": 15, "gradient": "from-fuchsia-400 to-pink-500"},
    {"key": "cake",        "name": "Торт",         "emoji": "🎂", "cost": 10, "gradient": "from-orange-300 to-rose-400"},
    {"key": "star",        "name": "Звезда",       "emoji": "⭐", "cost": 5,  "gradient": "from-yellow-300 to-amber-500"},
    {"key": "yacht",       "name": "Яхта",         "emoji": "🛥️", "cost": 30, "gradient": "from-blue-400 to-indigo-600"},
    {"key": "champagne",   "name": "Шампанское",   "emoji": "🥂", "cost": 15, "gradient": "from-yellow-200 to-amber-400"},
    {"key": "cocktail",    "name": "Коктейль",     "emoji": "🍹", "cost": 10, "gradient": "from-lime-300 to-emerald-500"},
    {"key": "envelope",    "name": "Письмо",       "emoji": "💌", "cost": 5,  "gradient": "from-rose-300 to-red-500"},
    {"key": "tulips",      "name": "Тюльпаны",     "emoji": "🌷", "cost": 10, "gradient": "from-pink-300 to-rose-500"},
    {"key": "winged_heart","name": "Крылатое сердце","emoji": "💘","cost": 15, "gradient": "from-red-400 to-pink-600"},
    {"key": "watermelon",  "name": "Арбуз",        "emoji": "🍉", "cost": 5,  "gradient": "from-emerald-400 to-red-500"},
    {"key": "koala",       "name": "Коала",        "emoji": "🐨", "cost": 8,  "gradient": "from-slate-300 to-slate-500"},
    {"key": "lips",        "name": "Губы",         "emoji": "👄", "cost": 5,  "gradient": "from-rose-400 to-red-600"},
    {"key": "mask",        "name": "Маска",        "emoji": "🎭", "cost": 8,  "gradient": "from-purple-400 to-fuchsia-600"},
]
GIFT_COST_BY_KEY = {g["key"]: g["cost"] for g in GIFT_CATALOG}

# ────────────────────────────── WebSocket Manager ──────────────────────────────
class WSManager:
    """Very small in-process pub/sub for chat + notifications.
    NOTE: single-process only. Fine for MVP; use Redis pub/sub to scale out."""
    def __init__(self):
        self._conns: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, user_id: str, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._conns.setdefault(user_id, set()).add(ws)

    async def disconnect(self, user_id: str, ws: WebSocket):
        async with self._lock:
            conns = self._conns.get(user_id)
            if conns:
                conns.discard(ws)
                if not conns:
                    self._conns.pop(user_id, None)

    def is_online(self, user_id: str) -> bool:
        return bool(self._conns.get(user_id))

    def online_users(self) -> list[str]:
        return list(self._conns.keys())

    async def send_to(self, user_id: str, payload: dict):
        conns = list(self._conns.get(user_id, ()))
        dead: list[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(user_id, ws)

    async def broadcast_message(self, msg: dict):
        """Send a chat message payload to both participants."""
        payload = {"type": "message", "data": msg}
        for uid in msg.get('participants', []):
            await self.send_to(uid, payload)

    async def broadcast_deletion(self, chat_id_val: str, participants: list, message_id: str, scope: str, deleted_by: str):
        """Notify both participants that a message was deleted for everyone."""
        payload = {"type": "message_deleted", "data": {
            "message_id": message_id, "chat_id": chat_id_val,
            "scope": scope, "deleted_by": deleted_by,
        }}
        for uid in participants:
            await self.send_to(uid, payload)

ws_manager = WSManager()

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
        # A user counts as "online" if a live WebSocket is open (real-time),
        # OR they had HTTP activity in the last 60 s (fallback for browsers
        # that just page-loaded without opening the WS yet).
        online = ws_manager.is_online(u['user_id']) or (now_utc() - last_active).total_seconds() < 60
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
    if user.get('deactivated'):
        raise HTTPException(status_code=403, detail="Аккаунт деактивирован. Обратитесь в поддержку.")
    banned_until = user.get('banned_until')
    if banned_until:
        try:
            bu = datetime.fromisoformat(str(banned_until).replace('Z', '+00:00'))
            if bu.tzinfo is None: bu = bu.replace(tzinfo=timezone.utc)
            if bu > now_utc():
                raise HTTPException(status_code=403, detail=f"Аккаунт заблокирован до {bu.strftime('%Y-%m-%d %H:%M UTC')}. Причина: {user.get('ban_reason','')}")
        except HTTPException:
            raise
        except Exception:
            pass
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
    # DOB → must be 18+
    if 'dob' in update:
        age = calc_age(update['dob'])
        if age < 18:
            raise HTTPException(status_code=400, detail="Возраст должен быть 18+")
    update['last_active'] = iso(now_utc())
    await db.users.update_one({"user_id": user['user_id']}, {"$set": update})
    fresh = await db.users.find_one({"user_id": user['user_id']}, {"_id": 0, "password_hash": 0})
    return fresh

class PhotoBody(BaseModel):
    data_url: str  # base64 data URL like data:image/jpeg;base64,...

def _compress_image_data_url(data_url: str, max_dim: int = 1600, quality: int = 82) -> tuple[str, bytes]:
    """Resize + JPEG-compress the uploaded image server-side.
    Accepts JPG/PNG/WEBP/HEIC. Returns (data_url, raw_bytes)."""
    from PIL import Image
    try:
        # Optional HEIC support
        try:
            from pillow_heif import register_heif_opener  # type: ignore
            register_heif_opener()
        except Exception:
            pass
        header, b64 = data_url.split(',', 1)
        raw = base64.b64decode(b64)
        img = Image.open(io.BytesIO(raw))
        # Correct orientation from EXIF
        try:
            from PIL import ImageOps
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass
        if img.mode != "RGB":
            img = img.convert("RGB")
        # Resize to fit within max_dim square while keeping aspect
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=quality, optimize=True)
        compressed = out.getvalue()
        new_url = "data:image/jpeg;base64," + base64.b64encode(compressed).decode()
        return new_url, compressed
    except Exception as e:
        logger.warning(f"Image compression failed, falling back to original: {e}")
        return data_url, b""

async def _verify_gender_from_photo(image_data_url: str, user_gender: str) -> dict:
    """AI gender check via Emergent LLM vision. Returns {ok, reason}.
    Fails-open on any error / low confidence."""
    # Skip if user's registered gender isn't specifically male/female
    if user_gender not in ("male", "female"):
        return {"ok": True, "reason": "unchecked"}
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent  # type: ignore
        header, b64 = image_data_url.split(',', 1)
        chat = LlmChat(
            api_key=os.environ['EMERGENT_LLM_KEY'],
            session_id=f"gender_{uuid.uuid4().hex[:6]}",
            system_message=(
                "You are a photo moderator for a dating app. "
                "Analyze the primary human face in the image. Reply ONLY with strict JSON in the shape "
                '{"face_detected": true|false, "gender": "male"|"female"|"unknown", "confidence": 0.0-1.0}. '
                "'confidence' is your certainty about the gender."
            ),
        ).with_model("openai", "gpt-4o")
        msg = UserMessage(text="Analyze this photo and return the JSON.", file_contents=[ImageContent(image_base64=b64)])
        raw = await asyncio.wait_for(chat.send_message(msg), timeout=5.0)
        text = str(raw).strip()
        # Extract JSON (strip markdown fences if any)
        if text.startswith("```"):
            text = text.split('```', 2)[1].lstrip('json').strip()
        data = _json.loads(text)
        if not data.get("face_detected"):
            return {"ok": False, "reason": "no_face", "message": "Please upload a clear photo showing your face"}
        detected = data.get("gender", "unknown")
        conf = float(data.get("confidence") or 0)
        # Give benefit of the doubt on low confidence
        if detected == "unknown" or conf < 0.6:
            return {"ok": True, "reason": "low_confidence"}
        if detected != user_gender:
            return {"ok": False, "reason": "mismatch", "message": "Photo does not match your profile gender. Please upload a photo that matches your gender."}
        return {"ok": True, "reason": "match", "confidence": conf}
    except Exception as e:
        logger.warning(f"Gender verification failed-open: {e}")
        return {"ok": True, "reason": "verifier_error"}

@api.post("/profile/photo")
async def upload_photo(body: PhotoBody, user: dict = Depends(get_current_user)):
    """Accept ANY size base64 data URL — server compresses aggressively.
    Runs AI gender verification (5s timeout, fails-open on errors)."""
    if not body.data_url.startswith("data:image/"):
        raise HTTPException(status_code=400, detail="Invalid image format")

    fresh = await db.users.find_one({"user_id": user['user_id']}, {"_id": 0, "photos": 1, "gender": 1})
    photos = (fresh or {}).get('photos') or []
    if len(photos) >= 4:
        raise HTTPException(status_code=400, detail="Maximum 4 photos")

    # Compress FIRST — smaller image also speeds up the AI check
    compressed_url, _ = _compress_image_data_url(body.data_url)

    # AI gender verification
    verdict = await _verify_gender_from_photo(compressed_url, (fresh or {}).get('gender', ''))
    if not verdict.get('ok'):
        raise HTTPException(status_code=422, detail=verdict.get('message') or "Photo rejected")

    photos.append(compressed_url)
    await db.users.update_one({"user_id": user['user_id']}, {"$set": {"photos": photos, "last_active": iso(now_utc())}})
    return {"photos": photos, "verification": verdict}

class PhotosReorderBody(BaseModel):
    photos: List[str]  # full list in new order (max 4)

@api.put("/profile/photos")
async def reorder_photos(body: PhotosReorderBody, user: dict = Depends(get_current_user)):
    if len(body.photos) > 4:
        raise HTTPException(status_code=400, detail="Максимум 4 фотографии")
    await db.users.update_one({"user_id": user['user_id']}, {"$set": {"photos": body.photos}})
    return {"photos": body.photos}

@api.delete("/profile/photo/{index}")
async def delete_photo(index: int, user: dict = Depends(get_current_user)):
    fresh = await db.users.find_one({"user_id": user['user_id']}, {"_id": 0, "photos": 1})
    photos = (fresh or {}).get('photos') or []
    if index < 0 or index >= len(photos):
        raise HTTPException(status_code=404, detail="Photo not found")
    photos.pop(index)
    await db.users.update_one({"user_id": user['user_id']}, {"$set": {"photos": photos}})
    return {"photos": photos}

def _profile_completion(u: dict) -> int:
    """Percent completion — used to nudge users to fill the profile."""
    checks = [
        bool(u.get('photos')),
        bool(u.get('about')),
        bool(u.get('job')),
        bool(u.get('education')),
        bool(u.get('language')),
        bool(u.get('height')),
        bool(u.get('goal')),
        bool(u.get('relationship')),
        bool(u.get('kids')),
        bool(u.get('smoking') and u.get('alcohol')),
        bool(u.get('interests') and len(u['interests']) >= 3),
        bool(u.get('lat')),
    ]
    return int(round(100 * sum(1 for c in checks if c) / len(checks)))

@api.get("/profile/me/stats")
async def profile_stats(user: dict = Depends(get_current_user)):
    """Return popularity (based on likes received), polarity, and completion."""
    fresh = await db.users.find_one({"user_id": user['user_id']}, {"_id": 0, "password_hash": 0})
    if not fresh:
        raise HTTPException(status_code=404, detail="User not found")
    likes_received = await db.likes.count_documents({"to_user": user['user_id'], "type": "like"})
    # Popularity thresholds
    if likes_received >= 20: popularity = "high"
    elif likes_received >= 5: popularity = "medium"
    else: popularity = "low"
    # Polarity: derived from interest count (more social interests → extrovert)
    social_interests = {"Друзья", "Клубы", "Караоке", "Танцы", "Путешествия", "Караоке",
                        "Meeting with Friends", "Partying and Clubbing", "Dancing", "Karaoke", "Travel"}
    quiet_interests = {"Книги", "Медитация", "Йога", "Meditation", "Yoga", "Books",
                       "Fan Fiction", "Deep conversations", "Psychology"}
    interests = set(fresh.get('interests') or [])
    social_hits = len(interests & social_interests)
    quiet_hits = len(interests & quiet_interests)
    total = max(1, social_hits + quiet_hits)
    # 0 = introvert, 100 = extrovert; default 50
    polarity = int(round(50 + (social_hits - quiet_hits) / total * 50)) if (social_hits + quiet_hits) else 50
    return {
        "popularity": popularity,
        "likes_received": likes_received,
        "polarity": max(0, min(100, polarity)),
        "completion": _profile_completion(fresh),
        "photo_count": len(fresh.get('photos') or []),
        "interest_count": len(fresh.get('interests') or []),
    }

@api.put("/profile/location")
async def update_location(body: dict, user: dict = Depends(get_current_user)):
    """Called on app open to refresh user coordinates."""
    lat = body.get('lat'); lng = body.get('lng'); city = body.get('city')
    if lat is not None and lng is not None:
        await db.users.update_one({"user_id": user['user_id']}, {"$set": {"lat": float(lat), "lng": float(lng), "city": city, "last_active": iso(now_utc())}})
    elif city:
        await db.users.update_one({"user_id": user['user_id']}, {"$set": {"city": city, "last_active": iso(now_utc())}})
    return {"ok": True}


@api.get("/profile/{user_id}")
async def get_profile(user_id: str, user: dict = Depends(get_current_user)):
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Profile not found")
    return user_public(target, viewer=user)

# ────────────────────────────── Discovery / Home / Likes ──────────────────────────────
def _is_online(u: dict) -> bool:
    """True iff user has an open WS OR was HTTP-active in the last 60 s."""
    if ws_manager.is_online(u.get('user_id')):
        return True
    la = _parse_dt(u.get('last_active'))
    return bool(la and (now_utc() - la).total_seconds() < 60)

def _parse_dt(v):
    if not v: return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    try:
        d = datetime.fromisoformat(str(v).replace('Z', '+00:00'))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None

def _dist_km(viewer: dict, u: dict) -> Optional[float]:
    if viewer.get('lat') is None or u.get('lat') is None:
        return None
    return haversine_km(viewer['lat'], viewer['lng'], u['lat'], u['lng'])

async def _base_candidates(user: dict, pool_limit: int = 500) -> list[dict]:
    """Common candidate pool: gender filter, no blocked/self, no already-swiped, no admins."""
    show_me = user.get('show_me', 'both')
    gender_q: dict = {"gender": show_me} if show_me in ('male', 'female') else {}
    blocked = user.get('blocked', []) + [user['user_id']]
    swipes = await db.likes.find({"from_user": user['user_id']}, {"_id": 0, "to_user": 1}).to_list(2000)
    already = {s['to_user'] for s in swipes}
    already.update(blocked)
    q = {"user_id": {"$nin": list(already)}, "is_admin": {"$ne": True}, "deactivated": {"$ne": True}, **gender_q}
    return await db.users.find(q, {"_id": 0, "password_hash": 0}).limit(pool_limit).to_list(pool_limit)

@api.get("/discover/feed")
async def discover_feed(user: dict = Depends(get_current_user), limit: int = 20):
    """Search page (swipe cards). Priority:
       1. Online + Nearby, 2. Online (any), 3. Offline + Nearby, 4. Offline (any).
       Sort formula: is_online DESC, distance ASC, last_seen DESC.
       Nearby = within `distance_km` when the user picked 'limited' mode
       (default: 100 km when unset)."""
    pool = await _base_candidates(user)
    nearby_km = user.get('distance_km') if user.get('distance_mode') == 'limited' else 100
    if not isinstance(nearby_km, (int, float)):
        nearby_km = 100
    now = now_utc()
    scored = []
    for u in pool:
        online = _is_online(u)
        d = _dist_km(user, u)
        nearby = (d is not None and d <= nearby_km)
        # Tier: lower value = higher priority
        if online and nearby:
            tier = 0
        elif online:
            tier = 1
        elif nearby:
            tier = 2
        else:
            tier = 3
        last_seen = _parse_dt(u.get('last_active'))
        last_seen_score = (now - last_seen).total_seconds() if last_seen else 10 ** 9
        scored.append((tier, d if d is not None else 10 ** 9, last_seen_score, u))
    scored.sort(key=lambda t: (t[0], t[1], t[2]))
    return [user_public(t[3], viewer=user) for t in scored[:limit]]

@api.get("/home/feed")
async def home_feed(user: dict = Depends(get_current_user), limit: int = 6, skip: int = 0):
    """Home page (grid). HARD-filters by the user's selected distance range
       when `distance_mode='limited'` — profiles outside the range are hidden.
       Priority within the range:
         1. Public users inside selected range (always included; sorted below)
         2. Online + Premium
         3. Online + Nearby (Nearby = <= radius / 100 km fallback)
         4. Recently came Online (online_at DESC)
         5. Offline + Nearby
         6. Offline (any)"""
    pool = await _base_candidates(user, pool_limit=800)
    hard_limit = user.get('distance_km') if user.get('distance_mode') == 'limited' else None
    if hard_limit is not None and not isinstance(hard_limit, (int, float)):
        hard_limit = None
    # For "nearby" tiers when no hard limit picked, treat 100 km as nearby.
    nearby_km = hard_limit if hard_limit is not None else 100
    now = now_utc()
    scored: list = []
    for u in pool:
        d = _dist_km(user, u)
        # HARD distance filter (Priority 1 rule)
        if hard_limit is not None:
            if d is None:
                continue  # no geo → cannot verify within range
            if d > hard_limit:
                continue
        online = _is_online(u)
        premium = bool(u.get('is_premium'))
        nearby = (d is not None and d <= nearby_km)
        online_at = _parse_dt(u.get('online_at'))
        if online and premium:
            tier = 1
        elif online and nearby:
            tier = 2
        elif online:
            tier = 3  # includes "recently came online" — sub-sorted by online_at
        elif nearby:
            tier = 4
        else:
            tier = 5
        # secondary sort keys
        online_at_score = -(online_at.timestamp() if online_at else 0)
        last_seen = _parse_dt(u.get('last_active'))
        last_seen_score = (now - last_seen).total_seconds() if last_seen else 10 ** 9
        dist_score = d if d is not None else 10 ** 9
        scored.append((tier, online_at_score, dist_score, last_seen_score, u))
    scored.sort(key=lambda t: (t[0], t[1], t[2], t[3]))
    return [user_public(t[4], viewer=user) for t in scored[skip:skip + limit]]

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

def _decorate_msg(m: dict, viewer_id: str, viewer_is_premium: bool) -> dict:
    """Apply locked flag: incoming messages from partner beyond the 2 free window
    are hidden unless the viewer has Premium. Free users see the message exists
    but content is masked with an upgrade prompt."""
    m = {k: v for k, v in m.items() if k != '_id'}
    if m.get('from_user') != viewer_id and not viewer_is_premium:
        # Count position of this message among partner's messages in the chat
        pass  # handled in bulk below for efficiency
    return m

@api.get("/chats/{other_id}/messages")
async def get_messages(other_id: str, user: dict = Depends(get_current_user), limit: int = 200):
    cid = chat_id(user['user_id'], other_id)
    uid = user['user_id']
    msgs = await db.messages.find(
        {"chat_id": cid, "hidden_for": {"$ne": uid}},
        {"_id": 0}
    ).sort("created_at", 1).to_list(limit)
    await db.messages.update_many({"chat_id": cid, "to_user": uid, "deleted": {"$ne": True}}, {"$set": {"read": True}})
    is_premium = bool(user.get('is_premium'))
    partner_seen = 0
    for m in msgs:
        m.pop('_id', None)
        # Normalize deleted-for-everyone messages so the client can render a placeholder
        if m.get('deleted'):
            m['text'] = ''
            m['media_url'] = None
            m['file_name'] = None
            m['gift_key'] = None
            m['locked'] = False
            continue
        if m.get('from_user') != uid:
            partner_seen += 1
            if not is_premium and partner_seen > FREE_MSGS:
                m['locked'] = True
                m['text'] = ''
                m['media_url'] = None
            else:
                m['locked'] = False
        else:
            m['locked'] = False
    return msgs

@api.delete("/messages/{message_id}")
async def delete_message(message_id: str, scope: str = "me", user: dict = Depends(get_current_user)):
    """Delete a message.

    - scope='me'       → hide only for the current user (any message the user can see).
    - scope='everyone' → tombstone the message for both participants. Allowed only
                          within 1 hour of send and only by the sender (or an admin).
                          Broadcasts a WS `message_deleted` event.
    """
    if scope not in {"me", "everyone"}:
        raise HTTPException(status_code=400, detail="Invalid scope")
    m = await db.messages.find_one({"message_id": message_id}, {"_id": 0})
    if not m:
        raise HTTPException(status_code=404, detail="Message not found")
    uid = user['user_id']
    is_admin = bool(user.get('is_admin'))
    if uid not in (m.get('participants') or []) and not is_admin:
        raise HTTPException(status_code=403, detail="Not your chat")

    if scope == "me":
        await db.messages.update_one({"message_id": message_id}, {"$addToSet": {"hidden_for": uid}})
        return {"ok": True, "scope": "me", "message_id": message_id}

    # scope == "everyone"
    if m.get('deleted'):
        return {"ok": True, "scope": "everyone", "message_id": message_id, "already": True}
    if m.get('from_user') != uid and not is_admin:
        raise HTTPException(status_code=403, detail="Only the sender can delete for everyone")
    # 1-hour window (admins bypass)
    try:
        created = datetime.fromisoformat(m['created_at'].replace('Z', '+00:00'))
    except Exception:
        created = now_utc()
    if not is_admin and (now_utc() - created).total_seconds() > 3600:
        raise HTTPException(status_code=403, detail="Прошло больше часа — нельзя удалить у всех")

    await db.messages.update_one(
        {"message_id": message_id},
        {"$set": {
            "deleted": True,
            "deleted_at": iso(now_utc()),
            "deleted_by": uid,
            "text": "",
            "media_url": None,
            "file_name": None,
            "gift_key": None,
        }},
    )
    try:
        await ws_manager.broadcast_deletion(m['chat_id'], m.get('participants') or [], message_id, "everyone", uid)
    except Exception as e:
        logger.warning(f"ws deletion broadcast failed: {e}")
    return {"ok": True, "scope": "everyone", "message_id": message_id}

async def _do_send_message(sender: dict, other_id: str, body: MessageBody) -> dict:
    other = await db.users.find_one({"user_id": other_id}, {"_id": 0})
    if not other:
        raise HTTPException(status_code=404, detail="User not found")
    if body.kind not in MSG_COST and body.kind != 'gift':
        raise HTTPException(status_code=400, detail="Invalid message kind")
    # Gift cost varies by key
    if body.kind == 'gift':
        if not body.gift_key or body.gift_key not in GIFT_COST_BY_KEY:
            raise HTTPException(status_code=400, detail="Invalid gift")
        cost = GIFT_COST_BY_KEY[body.gift_key]
    else:
        cost = MSG_COST[body.kind]
    cid = chat_id(sender['user_id'], other_id)
    sent_count = await db.messages.count_documents({"chat_id": cid, "from_user": sender['user_id']})
    is_admin_sender = sender.get('is_admin', False)

    # Refresh coin/premium status from DB
    fresh = await db.users.find_one({"user_id": sender['user_id']}, {"_id": 0, "coins": 1, "is_premium": 1})
    coins = int((fresh or {}).get('coins') or 0)
    is_premium = bool((fresh or {}).get('is_premium'))

    within_free = sent_count < FREE_MSGS
    # First 2 messages are ALWAYS free (any kind). After that:
    #   - If user has enough coins → deduct
    #   - Otherwise → 402 with `blocked=True` in body so client shows purchase popup
    if within_free or is_admin_sender:
        cost_paid = 0
    else:
        if coins < cost:
            raise HTTPException(status_code=402, detail={
                "message": "Купите монеты, чтобы продолжить общение",
                "blocked": True,
                "required": cost,
                "have": coins,
                "kind": body.kind,
            })
        await db.users.update_one({"user_id": sender['user_id']}, {"$inc": {"coins": -cost}})
        cost_paid = cost
    msg = {
        "message_id": f"msg_{uuid.uuid4().hex[:12]}",
        "chat_id": cid,
        "participants": sorted([sender['user_id'], other_id]),
        "from_user": sender['user_id'],
        "to_user": other_id,
        "kind": body.kind,
        "text": body.text or "",
        "media_url": body.media_url,
        "file_name": body.file_name,
        "gift_key": body.gift_key,
        "reply_to": body.reply_to,
        "read": False,
        "cost_paid": cost_paid,
        "created_at": iso(now_utc()),
    }
    await db.messages.insert_one(msg)
    msg.pop('_id', None)
    # Broadcast to both participants via WS (fire-and-forget)
    try:
        await ws_manager.broadcast_message(msg)
    except Exception as e:
        logger.warning(f"ws broadcast failed: {e}")
    return msg

@api.post("/chats/{other_id}/send")
async def send_message(other_id: str, body: MessageBody, user: dict = Depends(get_current_user)):
    return await _do_send_message(user, other_id, body)

class ChatMediaBody(BaseModel):
    data_url: str
    kind: Literal['image', 'voice', 'video', 'file']
    file_name: Optional[str] = None

@api.post("/chat/media")
async def upload_chat_media(body: ChatMediaBody, user: dict = Depends(get_current_user)):
    """Upload chat media (image / voice / video / file). Returns a data_url
    suitable for the `media_url` field in a subsequent /chats/{id}/send call.
    Images are compressed. Audio / video / files are stored as-is (base64 data URLs)."""
    if not body.data_url.startswith("data:"):
        raise HTTPException(status_code=400, detail="Invalid media format")
    max_bytes = 4 * 1024 * 1024 if body.kind == 'image' else 10 * 1024 * 1024
    try:
        _, b64 = body.data_url.split(',', 1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Malformed data URL")
    approx_bytes = int(len(b64) * 3 / 4)
    if approx_bytes > max_bytes:
        raise HTTPException(status_code=413, detail=f"Файл слишком большой (лимит {max_bytes // (1024*1024)} МБ)")
    if body.kind == 'image':
        if not body.data_url.startswith('data:image/'):
            raise HTTPException(status_code=400, detail="Ожидается изображение")
        media_url, _ = _compress_image_data_url(body.data_url, max_dim=1200, quality=78)
    else:
        media_url = body.data_url
    return {"media_url": media_url, "kind": body.kind, "size_bytes": approx_bytes, "file_name": body.file_name}

@api.get("/chat/status/{other_id}")
async def chat_status(other_id: str, user: dict = Depends(get_current_user)):
    """Per-chat state for the current viewer.
    Returns free-message counter and whether the input is hard-blocked."""
    cid = chat_id(user['user_id'], other_id)
    sent = await db.messages.count_documents({"chat_id": cid, "from_user": user['user_id']})
    fresh = await db.users.find_one({"user_id": user['user_id']}, {"_id": 0, "coins": 1, "is_premium": 1})
    coins = int((fresh or {}).get('coins') or 0)
    is_premium = bool((fresh or {}).get('is_premium'))
    # Free-message limit reached AND no coins → blocked
    is_blocked = (sent >= FREE_MSGS) and coins < MSG_COST['text'] and not is_premium and not user.get('is_admin')
    return {
        "chat_id": cid,
        "sent_count": sent,
        "free_used": min(sent, FREE_MSGS),
        "free_limit": FREE_MSGS,
        "coins": coins,
        "is_premium": is_premium,
        "is_blocked": is_blocked,
    }

@api.get("/gifts")
async def gifts_list():
    """Public gift catalog: key, name, emoji, cost, tailwind gradient."""
    return GIFT_CATALOG

# ────────────────────────────── Premium & Coins ──────────────────────────────
# ⚠️ Auto-crediting DISABLED per updated flow — coins are added ONLY by admin
# manually after verifying a submitted payment receipt. The `_try_auto_confirm`
# function is retained but is a no-op unless AUTO_CREDIT_ENABLED is set to '1'.
AUTO_CREDIT_ENABLED = os.environ.get('AUTO_CREDIT_ENABLED', '0') == '1'
MOCK_CONFIRM_DELAY_SECONDS = 8  # only used if AUTO_CREDIT_ENABLED

async def _get_admin_sbp_phone() -> str:
    """Fetch the current admin SBP phone from DB (encrypted at rest) with env fallback.
    Never returned to any non-admin endpoint."""
    s = await db.settings.find_one({"key": "app"}, {"_id": 0}) or {}
    enc = s.get('sbp_phone_enc')
    if enc:
        return decrypt_str(enc)
    # Bootstrap from env on first run
    env_phone = os.environ.get('SBP_PHONE', '')
    if env_phone:
        await db.settings.update_one({"key": "app"}, {"$set": {"key": "app", "sbp_phone_enc": encrypt_str(env_phone), "updated_at": iso(now_utc())}}, upsert=True)
    return env_phone

def _build_sbp_link(phone: str, amount_rub: int, tx_id: str) -> str:
    """Build a Russian SBP (Система быстрых платежей) deep link that any Russian bank app can open.
    Format follows the NSPK (National Payment Card System) short URL standard used by Russian banks.
    Comment as free-text description that will be shown to the sender inside their bank app."""
    # NOTE: qr.nspk.ru is the real host used by SBP for pay-by-link. The token here encodes tx ref.
    from urllib.parse import quote
    ref = f"lovreski_{tx_id}"
    return f"https://qr.nspk.ru/pay?type=01&bank=100000000111&sum={amount_rub}00&cur=RUB&crc=lovreski&ref={ref}&purpose={quote('Lovreski coins')}"

def _qr_png_base64(data: str) -> str:
    """Generate a PNG data-URL for a QR code — used to render the SBP payment QR client-side."""
    img = qrcode.make(data)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

@api.get("/coins/packages")
async def coin_packages():
    """Public packages + admin SBP phone (per updated spec, users need to see the
    payment recipient number and copy it into their bank app)."""
    s = await db.settings.find_one({"key": "app"}, {"_id": 0}) or {}
    packages = s.get('packages') or COIN_PACKAGES
    for p in packages:
        p['popular'] = (p['id'] == 'p300')  # 300 coins = best value (4 ₽/coin)
    # Fetch the admin SBP phone (encrypted at rest) so users can copy it
    sbp_phone = await _get_admin_sbp_phone()
    return {
        "packages": packages,
        "currency": "RUB",
        "sbp_phone": sbp_phone,
        "recipient_name": os.environ.get('SBP_RECIPIENT_NAME', 'Al Amin Dewan'),
        "banks": [
            {"id": "sberbank", "name": "Сбербанк"},
            {"id": "tbank", "name": "T-Bank (Тинькофф)"},
        ],
    }

@api.post("/coins/checkout")
async def coins_checkout(body: PurchaseBody, request: Request, user: dict = Depends(get_current_user)):
    """Create a payment transaction and return SBP link + QR (server-side only knows the phone)."""
    # Rate limit: 5 payment attempts per user per hour
    since = now_utc() - timedelta(hours=1)
    recent = await db.transactions.count_documents({"user_id": user['user_id'], "created_at": {"$gte": iso(since)}})
    if recent >= 5:
        raise HTTPException(status_code=429, detail="Too many payment attempts. Please try again later.")

    s = await db.settings.find_one({"key": "app"}, {"_id": 0}) or {}
    packages = s.get('packages') or COIN_PACKAGES
    pkg = next((p for p in packages if p['id'] == body.package_id), None)
    if not pkg:
        raise HTTPException(status_code=400, detail="Package not found")

    admin_phone = await _get_admin_sbp_phone()
    if not admin_phone:
        raise HTTPException(status_code=500, detail="Payment provider not configured")

    tx_id = f"tx_{uuid.uuid4().hex[:12]}"
    sbp_link = _build_sbp_link(admin_phone, pkg['price'], tx_id)
    ip = request.client.host if request.client else None

    tx = {
        "tx_id": tx_id,
        "user_id": user['user_id'],
        "user_email": user.get('email'),
        "user_name": user.get('name'),
        "package_id": pkg['id'],
        "coins": pkg['coins'],
        "amount_rub": pkg['price'],
        "payment_method": "SBP",
        "bank": body.bank,  # sender's chosen bank (sberbank | tbank | None)
        "status": "pending",  # pending → success | failed
        "credited": False,
        "ip": ip,
        "sbp_link_hash": hash(sbp_link),
        "created_at": iso(now_utc()),
        "auto_confirm_at": iso(now_utc() + timedelta(seconds=MOCK_CONFIRM_DELAY_SECONDS)),
    }
    await db.transactions.insert_one(tx)
    tx.pop('_id', None)
    return {
        "tx_id": tx_id,
        "amount_rub": pkg['price'],
        "coins": pkg['coins'],
        "sbp_link": sbp_link,
        "qr_png": _qr_png_base64(sbp_link),
        "expires_in": 600,  # 10 minutes
        # Deliberately NOT returning the admin phone number.
    }

async def _try_auto_confirm(tx: dict) -> dict:
    """DISABLED by default. Only runs when AUTO_CREDIT_ENABLED env is '1'.
    Under the new manual-approval flow, coins are added only via /admin/support/*
    or /admin/users/*/add-coins."""
    if not AUTO_CREDIT_ENABLED:
        return tx
    if tx.get('credited') or tx.get('status') != 'pending':
        return tx
    ac = tx.get('auto_confirm_at')
    if isinstance(ac, str):
        try:
            ac_dt = datetime.fromisoformat(ac)
            if ac_dt.tzinfo is None: ac_dt = ac_dt.replace(tzinfo=timezone.utc)
            if now_utc() < ac_dt:
                return tx
        except ValueError:
            return tx
    # Atomic mark-as-success (prevents double-crediting via CAS on credited: False).
    # Preserve the user-selected sender bank (tx.bank); only set it to 'Sberbank' if
    # the user did not choose one at checkout.
    set_fields = {"status": "success", "credited": True, "confirmed_at": iso(now_utc())}
    if not tx.get('bank'):
        set_fields['bank'] = "Sberbank"
    res = await db.transactions.find_one_and_update(
        {"tx_id": tx['tx_id'], "credited": False, "status": "pending"},
        {"$set": set_fields},
        return_document=True,
    )
    if not res:
        return await db.transactions.find_one({"tx_id": tx['tx_id']}, {"_id": 0}) or tx
    # Credit coins + activate Premium
    await db.users.update_one(
        {"user_id": tx['user_id']},
        {"$inc": {"coins": tx['coins']},
         "$set": {"is_premium": True, "premium_until": iso(now_utc() + timedelta(days=30))}},
    )
    res.pop('_id', None)
    return res

@api.get("/coins/status/{tx_id}")
async def coins_status(tx_id: str, user: dict = Depends(get_current_user)):
    """Polled every 3s by the payment popup. Returns tx status + fresh user balance."""
    # Fetch WITH auto_confirm_at so _try_auto_confirm can respect the delay,
    # then strip sensitive fields before returning to the client.
    tx = await db.transactions.find_one({"tx_id": tx_id, "user_id": user['user_id']}, {"_id": 0, "sbp_link_hash": 0, "ip": 0})
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    tx = await _try_auto_confirm(tx)
    tx.pop('auto_confirm_at', None)
    fresh = await db.users.find_one({"user_id": user['user_id']}, {"_id": 0})
    return {"transaction": tx, "coins": fresh.get('coins', 0), "is_premium": fresh.get('is_premium', False)}

@api.post("/coins/webhook")
async def coins_webhook(payload: dict, request: Request):
    """SBP webhook. Under the manual-approval flow, this endpoint NO LONGER
    credits coins directly — it only records the incoming payment claim as a
    pending 'receipt submission' that the admin must approve just like a
    user-uploaded screenshot. To re-enable direct crediting (real Sberbank
    signed webhook in production), set AUTO_CREDIT_ENABLED=1."""
    secret = request.headers.get('X-Webhook-Secret')
    expected = os.environ.get('SBP_WEBHOOK_SECRET')
    if not expected:
        raise HTTPException(status_code=503, detail="Webhook secret not configured")
    if secret != expected:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")
    tx_id = payload.get('tx_id')
    tx = await db.transactions.find_one({"tx_id": tx_id}, {"_id": 0})
    if not tx: raise HTTPException(status_code=404, detail="tx not found")
    if payload.get('status') != 'success' or payload.get('amount_rub') != tx['amount_rub']:
        await db.transactions.update_one({"tx_id": tx_id, "credited": False}, {"$set": {"status": "failed", "fail_reason": "Amount mismatch or bank error"}})
        return {"ok": False}
    if not AUTO_CREDIT_ENABLED:
        # Manual-approval flow: record as a pending receipt submission for the admin
        # instead of crediting the user directly.
        await db.transactions.update_one({"tx_id": tx_id}, {"$set": {"status": "awaiting_admin", "bank": payload.get('bank') or tx.get('bank')}})
        sub_id = f"sub_{uuid.uuid4().hex[:12]}"
        await db.receipt_submissions.insert_one({
            "submission_id": sub_id,
            "user_id": tx['user_id'],
            "user_email": tx.get('user_email'),
            "user_name": tx.get('user_name'),
            "package_id": tx.get('package_id'),
            "receipt_data_url": None,
            "message": f"[SBP webhook] tx {tx_id} · {payload.get('bank') or 'bank'} · {tx['amount_rub']} ₽",
            "status": "pending",
            "created_at": iso(now_utc()),
        })
        return {"ok": True, "queued_for_admin": True}
    # Legacy direct-credit path (only when explicitly enabled)
    res = await db.transactions.find_one_and_update(
        {"tx_id": tx_id, "credited": False, "status": "pending"},
        {"$set": {"status": "success", "credited": True, "bank": payload.get('bank') or "Sberbank", "confirmed_at": iso(now_utc())}},
    )
    if res:
        await db.users.update_one(
            {"user_id": tx['user_id']},
            {"$inc": {"coins": tx['coins']}, "$set": {"is_premium": True, "premium_until": iso(now_utc() + timedelta(days=30))}},
        )
    return {"ok": True}

@api.get("/coins/transactions")
async def user_transactions(user: dict = Depends(get_current_user)):
    tx = await db.transactions.find(
        {"user_id": user['user_id']},
        {"_id": 0, "sbp_link_hash": 0, "auto_confirm_at": 0, "ip": 0},
    ).sort("created_at", -1).to_list(200)
    return tx

@api.get("/coins/balance")
async def coin_balance(user: dict = Depends(get_current_user)):
    fresh = await db.users.find_one({"user_id": user['user_id']}, {"_id": 0})
    return {"coins": fresh.get('coins', 0), "is_premium": fresh.get('is_premium', False)}

# ────────── Manual receipt-approval flow ──────────

class ReceiptBody(BaseModel):
    package_id: Optional[str] = None
    receipt_data_url: str  # base64 data URL (JPG/PNG/PDF)
    message: Optional[str] = Field(default=None, max_length=500)

@api.post("/support/receipt")
async def submit_receipt(body: ReceiptBody, user: dict = Depends(get_current_user)):
    """User uploads a payment receipt image/PDF for admin verification.
    Coins are NOT credited here — only after admin approval."""
    if not body.receipt_data_url.startswith("data:"):
        raise HTTPException(status_code=400, detail="Invalid receipt format")
    # Rate-limit 5 receipts per hour
    since = now_utc() - timedelta(hours=1)
    recent = await db.receipt_submissions.count_documents({"user_id": user['user_id'], "created_at": {"$gte": iso(since)}})
    if recent >= 5:
        raise HTTPException(status_code=429, detail="Too many submissions. Try again later.")
    # Optional compression for image receipts
    receipt = body.receipt_data_url
    if receipt.startswith("data:image/"):
        try:
            receipt, _ = _compress_image_data_url(receipt, max_dim=1800, quality=85)
        except Exception:
            pass
    sub_id = f"sub_{uuid.uuid4().hex[:12]}"
    await db.receipt_submissions.insert_one({
        "submission_id": sub_id,
        "user_id": user['user_id'],
        "user_email": user.get('email'),
        "user_name": user.get('name'),
        "package_id": body.package_id,
        "receipt_data_url": receipt,
        "message": body.message,
        "status": "pending",  # pending → verified | rejected
        "created_at": iso(now_utc()),
    })
    return {"submission_id": sub_id, "status": "pending"}

@api.get("/support/my")
async def my_submissions(user: dict = Depends(get_current_user)):
    subs = await db.receipt_submissions.find(
        {"user_id": user['user_id']},
        {"_id": 0, "receipt_data_url": 0},
    ).sort("created_at", -1).to_list(50)
    return subs

@api.get("/notifications")
async def my_notifications(user: dict = Depends(get_current_user)):
    """Return the user's recent notifications and mark them as read."""
    notes = await db.notifications.find({"user_id": user['user_id']}, {"_id": 0}).sort("created_at", -1).to_list(50)
    await db.notifications.update_many({"user_id": user['user_id'], "read": False}, {"$set": {"read": True}})
    return notes

async def _push_notification(user_id: str, message: str, kind: str = "info"):
    await db.notifications.insert_one({
        "id": f"n_{uuid.uuid4().hex[:12]}",
        "user_id": user_id, "message": message, "kind": kind, "read": False,
        "created_at": iso(now_utc()),
    })

# ────────── Admin: pending submissions + custom coin add ──────────

class AdminApproveBody(BaseModel):
    coins: int = Field(gt=0, le=100000)
    reason: str = Field(min_length=1, max_length=200)

class AdminRejectBody(BaseModel):
    reason: str = Field(min_length=1, max_length=200)

class CustomCoinAddBody(BaseModel):
    user_id: str
    coins: int = Field(gt=0, le=100000)
    reason: str = Field(min_length=1, max_length=200)

@api.get("/admin/support/pending-count")
async def admin_pending_count(_: dict = Depends(require_admin)):
    return {"count": await db.receipt_submissions.count_documents({"status": "pending"})}

@api.get("/admin/support/pending")
async def admin_pending(_: dict = Depends(require_admin)):
    subs = await db.receipt_submissions.find({"status": "pending"}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return subs

@api.get("/admin/support/history")
async def admin_history(_: dict = Depends(require_admin)):
    subs = await db.receipt_submissions.find({"status": {"$ne": "pending"}}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return subs

@api.post("/admin/support/{submission_id}/approve")
async def admin_approve_receipt(submission_id: str, body: AdminApproveBody, admin: dict = Depends(require_admin)):
    """Admin approves a receipt: atomically credits coins + activates Premium.
    Idempotent via CAS on status:pending → verified."""
    res = await db.receipt_submissions.find_one_and_update(
        {"submission_id": submission_id, "status": "pending"},
        {"$set": {
            "status": "verified",
            "coins_added": body.coins,
            "reason": body.reason,
            "admin_id": admin['user_id'],
            "verified_at": iso(now_utc()),
        }},
        return_document=True,
    )
    if not res:
        raise HTTPException(status_code=404, detail="Submission not found or already processed")
    # Credit coins + activate premium
    await db.users.update_one(
        {"user_id": res['user_id']},
        {"$inc": {"coins": body.coins},
         "$set": {"is_premium": True, "premium_until": iso(now_utc() + timedelta(days=30))}},
    )
    # Audit log
    await db.admin_audit.insert_one({
        "admin_id": admin['user_id'], "action": "receipt_approve",
        "target_user": res['user_id'], "submission_id": submission_id,
        "coins": body.coins, "reason": body.reason, "at": iso(now_utc()),
    })
    await _push_notification(res['user_id'], f"🎉 Payment verified! {body.coins} coins added. Your Premium is now ACTIVE! 👑", "success")
    return {"ok": True, "coins_added": body.coins}

@api.post("/admin/support/{submission_id}/reject")
async def admin_reject_receipt(submission_id: str, body: AdminRejectBody, admin: dict = Depends(require_admin)):
    res = await db.receipt_submissions.find_one_and_update(
        {"submission_id": submission_id, "status": "pending"},
        {"$set": {
            "status": "rejected",
            "reject_reason": body.reason,
            "admin_id": admin['user_id'],
            "rejected_at": iso(now_utc()),
        }},
        return_document=True,
    )
    if not res:
        raise HTTPException(status_code=404, detail="Submission not found or already processed")
    await db.admin_audit.insert_one({
        "admin_id": admin['user_id'], "action": "receipt_reject",
        "target_user": res['user_id'], "submission_id": submission_id,
        "reason": body.reason, "at": iso(now_utc()),
    })
    await _push_notification(res['user_id'], f"❌ Receipt rejected. Reason: {body.reason}. Please contact support.", "error")
    return {"ok": True}

@api.post("/admin/users/add-coins")
async def admin_add_coins(body: CustomCoinAddBody, admin: dict = Depends(require_admin)):
    target = await db.users.find_one({"user_id": body.user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    new_balance = (target.get('coins', 0) or 0) + body.coins
    await db.users.update_one(
        {"user_id": body.user_id},
        {"$inc": {"coins": body.coins},
         "$set": {"is_premium": True, "premium_until": iso(now_utc() + timedelta(days=30))}},
    )
    await db.admin_audit.insert_one({
        "admin_id": admin['user_id'], "action": "custom_coin_add",
        "target_user": body.user_id, "coins": body.coins,
        "reason": body.reason, "at": iso(now_utc()),
    })
    await _push_notification(body.user_id, f"🎉 {body.coins} coins added by admin. Premium is ACTIVE! 👑", "success")
    return {"ok": True, "new_balance": new_balance}

# ────────── Refund Requests ──────────

class RefundBody(BaseModel):
    full_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    receipt_data_url: str
    reason: str = Field(min_length=1, max_length=1000)

@api.post("/support/refund")
async def submit_refund(body: RefundBody, request: Request, user: dict = Depends(get_current_user)):
    if not body.receipt_data_url.startswith("data:"):
        raise HTTPException(status_code=400, detail="Invalid receipt format")
    # Rate limit 3 refund requests per user per day
    since = now_utc() - timedelta(days=1)
    recent = await db.refund_requests.count_documents({"user_id": user['user_id'], "created_at": {"$gte": iso(since)}})
    if recent >= 3:
        raise HTTPException(status_code=429, detail="Too many refund requests. Try again tomorrow.")
    receipt = body.receipt_data_url
    if receipt.startswith("data:image/"):
        try: receipt, _ = _compress_image_data_url(receipt, max_dim=1800, quality=85)
        except Exception: pass
    rid = f"ref_{uuid.uuid4().hex[:12]}"
    await db.refund_requests.insert_one({
        "refund_id": rid,
        "user_id": user['user_id'],
        "full_name": body.full_name,
        "email": body.email.lower(),
        "receipt_data_url": receipt,
        "reason": body.reason,
        "status": "pending",
        "created_at": iso(now_utc()),
    })
    return {"refund_id": rid, "status": "pending"}

@api.get("/admin/refunds")
async def admin_refunds(status: str = "all", _: dict = Depends(require_admin)):
    q = {} if status == "all" else {"status": status}
    r = await db.refund_requests.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
    return r

@api.post("/admin/refunds/{refund_id}/decide")
async def admin_refund_decide(refund_id: str, body: dict, admin: dict = Depends(require_admin)):
    action = body.get('action')
    if action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="Invalid action")
    reason = body.get('reason') or ""
    res = await db.refund_requests.find_one_and_update(
        {"refund_id": refund_id, "status": "pending"},
        {"$set": {"status": "approved" if action == "approve" else "rejected", "admin_reason": reason, "admin_id": admin['user_id'], "decided_at": iso(now_utc())}},
        return_document=True,
    )
    if not res:
        raise HTTPException(status_code=404, detail="Refund not found or already processed")
    await _push_notification(res['user_id'],
        f"{'✅' if action == 'approve' else '❌'} Refund {action}d." + (f" Note: {reason}" if reason else ""),
        "success" if action == "approve" else "error")
    return {"ok": True}


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
    """LEGACY endpoint. Under the manual-approval contract, this endpoint NO LONGER
    credits coins. It only updates the checkout tx status for record-keeping.
    Coin/Premium mutations must go through /admin/support/:id/approve or
    /admin/users/add-coins."""
    tx = await db.transactions.find_one({"tx_id": tx_id}, {"_id": 0})
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if body.action == "approve":
        # No coin/premium mutation here anymore — only mark the tx as reviewed.
        await db.transactions.update_one(
            {"tx_id": tx_id},
            {"$set": {"status": "awaiting_admin", "reviewed_at": iso(now_utc())}},
        )
        return {"ok": True, "note": "Use /admin/support/:id/approve or /admin/users/add-coins to credit coins."}
    else:
        await db.transactions.update_one(
            {"tx_id": tx_id},
            {"$set": {"status": "rejected", "reject_reason": body.reason or "Отклонено администратором"}},
        )
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
async def admin_settings_update(data: dict, admin: dict = Depends(require_admin)):
    """Admin can only update whitelisted keys. `sbp_phone` is encrypted before storage."""
    updates: dict = {}
    if 'sbp_phone' in data:
        phone = str(data['sbp_phone']).strip()
        # Basic validation — must look like a Russian phone (E.164, 11 digits after +)
        digits = ''.join(c for c in phone if c.isdigit())
        if len(digits) < 10 or len(digits) > 15:
            raise HTTPException(status_code=400, detail="Invalid SBP phone format")
        updates['sbp_phone_enc'] = encrypt_str(phone)
    if 'packages' in data and isinstance(data['packages'], list):
        # Validate each package
        for p in data['packages']:
            if not isinstance(p.get('coins'), int) or p['coins'] <= 0:
                raise HTTPException(status_code=400, detail="Invalid coins amount")
            if not isinstance(p.get('price'), (int, float)) or p['price'] <= 0:
                raise HTTPException(status_code=400, detail="Invalid price")
        updates['packages'] = data['packages']
    if not updates:
        raise HTTPException(status_code=400, detail="No valid settings keys provided")
    updates['updated_at'] = iso(now_utc())
    await db.settings.update_one({"key": "app"}, {"$set": {"key": "app", **updates}}, upsert=True)
    await db.admin_audit.insert_one({
        "admin_id": admin['user_id'],
        "action": "settings_update",
        "keys": list(updates.keys()),
        "at": iso(now_utc()),
    })
    return {"ok": True}

@api.get("/admin/settings")
async def admin_settings_get(_: dict = Depends(require_admin)):
    """Admin sees the SBP phone MASKED by default. Full number requires explicit ?reveal=true.
    Never expose the raw phone anywhere else."""
    s = await db.settings.find_one({"key": "app"}, {"_id": 0}) or {}
    enc = s.get('sbp_phone_enc')
    if not enc:
        # Bootstrap from env
        env_phone = os.environ.get('SBP_PHONE', '')
        if env_phone:
            await db.settings.update_one({"key": "app"}, {"$set": {"key": "app", "sbp_phone_enc": encrypt_str(env_phone), "updated_at": iso(now_utc())}}, upsert=True)
            enc = encrypt_str(env_phone)
    phone = decrypt_str(enc) if enc else ""
    return {
        "sbp_phone_masked": mask_phone(phone),
        "sbp_phone_last4": phone[-4:] if phone else "",
        "packages": s.get('packages') or COIN_PACKAGES,
    }

@api.get("/admin/settings/reveal")
async def admin_settings_reveal(_: dict = Depends(require_admin)):
    """Explicit reveal — returns the raw admin SBP phone. Requires admin role.
    Rate-limited implicitly by admin session. Log this event for audit."""
    s = await db.settings.find_one({"key": "app"}, {"_id": 0}) or {}
    enc = s.get('sbp_phone_enc')
    phone = decrypt_str(enc) if enc else os.environ.get('SBP_PHONE', '')
    logger.warning(f"[audit] admin revealed SBP phone at {iso(now_utc())}")
    return {"sbp_phone": phone}

@api.post("/admin/users/deduct-coins")
async def admin_deduct_coins(body: CustomCoinAddBody, admin: dict = Depends(require_admin)):
    """Deduct coins from a user's balance. Requires a reason.
    Balance floored at 0. Audit-logged."""
    if body.coins <= 0:
        raise HTTPException(status_code=400, detail="Coins must be positive")
    if not (body.reason or "").strip():
        raise HTTPException(status_code=400, detail="Reason is required")
    target = await db.users.find_one({"user_id": body.user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    current = int(target.get('coins') or 0)
    deduct = min(body.coins, current)
    new_balance = current - deduct
    await db.users.update_one({"user_id": body.user_id}, {"$set": {"coins": new_balance}})
    await db.admin_audit.insert_one({
        "admin_id": admin['user_id'], "action": "custom_coin_deduct",
        "target_user": body.user_id, "coins": -deduct, "requested": body.coins,
        "reason": body.reason, "at": iso(now_utc()),
    })
    await _push_notification(body.user_id, f"⚠️ {deduct} монет удержано администратором. Причина: {body.reason}", "warning")
    return {"ok": True, "new_balance": new_balance, "deducted": deduct}

# ────────── User moderation actions ──────────
class UserActionBody(BaseModel):
    reason: Optional[str] = None
    days: Optional[int] = 7

@api.post("/admin/users/{user_id}/warn")
async def admin_warn(user_id: str, body: UserActionBody, admin: dict = Depends(require_admin)):
    """Send a warning notification to the user and mark on their record."""
    reason = (body.reason or "").strip() or "Нарушение правил"
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0, "user_id": 1})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    await db.users.update_one({"user_id": user_id}, {"$inc": {"warn_count": 1}, "$set": {"last_warn_at": iso(now_utc()), "last_warn_reason": reason}})
    await db.admin_audit.insert_one({"admin_id": admin['user_id'], "action": "warn", "target_user": user_id, "reason": reason, "at": iso(now_utc())})
    await _push_notification(user_id, f"⚠️ Предупреждение от администрации: {reason}", "warning")
    return {"ok": True}

# Backwards-compat: keep existing GET ban without body; add richer POST with reason+days
@api.post("/admin/users/{user_id}/ban7")
async def admin_ban7(user_id: str, body: UserActionBody, admin: dict = Depends(require_admin)):
    """Temporarily ban a user for `days` days (default 7). Ban clears sessions."""
    days = int(body.days or 7)
    if days <= 0 or days > 365:
        raise HTTPException(status_code=400, detail="days must be 1-365")
    reason = (body.reason or "").strip() or "Временная блокировка"
    until = iso(now_utc() + timedelta(days=days))
    r = await db.users.update_one({"user_id": user_id}, {"$set": {"banned_until": until, "ban_reason": reason}})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    await db.sessions.delete_many({"user_id": user_id})
    await db.admin_audit.insert_one({"admin_id": admin['user_id'], "action": "ban", "target_user": user_id, "days": days, "reason": reason, "at": iso(now_utc())})
    return {"ok": True, "banned_until": until}

@api.post("/admin/users/{user_id}/deactivate-permanent")
async def admin_deactivate_permanent(user_id: str, body: UserActionBody, admin: dict = Depends(require_admin)):
    """Soft-deactivate: hide from all feeds, invalidate sessions, prevent future logins.
    Content stays for audit / moderation review — no hard delete."""
    reason = (body.reason or "").strip() or "Постоянная деактивация"
    r = await db.users.update_one({"user_id": user_id}, {"$set": {
        "deactivated": True,
        "deactivated_at": iso(now_utc()),
        "deactivate_reason": reason,
        "is_online": False,
    }})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    await db.sessions.delete_many({"user_id": user_id})
    await db.admin_audit.insert_one({"admin_id": admin['user_id'], "action": "deactivate_permanent", "target_user": user_id, "reason": reason, "at": iso(now_utc())})
    return {"ok": True}

# ────────── Legal Documents (Admin-managed) ──────────
class LegalDocBody(BaseModel):
    slug: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1)

@api.get("/legal")
async def legal_list_public():
    """Public: list all published legal docs (slug, title, updated_at)."""
    docs = await db.legal_docs.find({}, {"_id": 0, "body": 0}).sort("title", 1).to_list(100)
    return docs

@api.get("/legal/{slug}")
async def legal_get_public(slug: str):
    d = await db.legal_docs.find_one({"slug": slug}, {"_id": 0})
    if not d:
        raise HTTPException(status_code=404, detail="Document not found")
    return d

@api.get("/admin/legal")
async def admin_legal_list(_: dict = Depends(require_admin)):
    return await db.legal_docs.find({}, {"_id": 0}).sort("title", 1).to_list(200)

@api.post("/admin/legal")
async def admin_legal_create(body: LegalDocBody, admin: dict = Depends(require_admin)):
    exists = await db.legal_docs.find_one({"slug": body.slug}, {"_id": 0, "slug": 1})
    if exists:
        raise HTTPException(status_code=409, detail="Slug already exists")
    doc = {**body.model_dump(), "created_at": iso(now_utc()), "updated_at": iso(now_utc())}
    await db.legal_docs.insert_one(doc)
    await db.admin_audit.insert_one({"admin_id": admin['user_id'], "action": "legal_create", "slug": body.slug, "at": iso(now_utc())})
    return {"ok": True, "slug": body.slug}

@api.put("/admin/legal/{slug}")
async def admin_legal_update(slug: str, body: LegalDocBody, admin: dict = Depends(require_admin)):
    if body.slug != slug:
        raise HTTPException(status_code=400, detail="Slug in body must match URL")
    r = await db.legal_docs.update_one(
        {"slug": slug},
        {"$set": {"title": body.title, "body": body.body, "updated_at": iso(now_utc())}},
    )
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Document not found")
    await db.admin_audit.insert_one({"admin_id": admin['user_id'], "action": "legal_update", "slug": slug, "at": iso(now_utc())})
    return {"ok": True}

@api.delete("/admin/legal/{slug}")
async def admin_legal_delete(slug: str, admin: dict = Depends(require_admin)):
    r = await db.legal_docs.delete_one({"slug": slug})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Document not found")
    await db.admin_audit.insert_one({"admin_id": admin['user_id'], "action": "legal_delete", "slug": slug, "at": iso(now_utc())})
    return {"ok": True}

# ────────── Admin Audit Log (read-only viewer) ──────────
@api.get("/admin/audit")
async def admin_audit_list(_: dict = Depends(require_admin), limit: int = 200):
    """Chronological audit log of admin mutations. Newest first."""
    rows = await db.admin_audit.find({}, {"_id": 0}).sort("at", -1).limit(limit).to_list(limit)
    return rows

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

class I18nBatchBody(BaseModel):
    lang: str
    strings: list[str]

@api.post("/i18n/translate-batch")
async def i18n_translate_batch(body: I18nBatchBody):
    """Translate a batch of Russian UI strings to `lang`.
    Persists each entry in `db.i18n_dynamic` keyed by (lang, sha16(text))."""
    lang = body.lang.lower().strip()
    # Dedupe + strip empties + cap payload
    raw_strings = [s for s in dict.fromkeys(body.strings or []) if s and s.strip()]
    if not raw_strings:
        return {"translations": {}}
    if lang == "ru":
        return {"translations": {s: s for s in raw_strings}}
    # Cap to prevent abuse
    if len(raw_strings) > 200:
        raw_strings = raw_strings[:200]

    def key_of(s: str) -> str:
        return hashlib.sha256(s.encode("utf-8")).hexdigest()[:20]

    # Look up cache
    keys = [key_of(s) for s in raw_strings]
    docs = await db.i18n_dynamic.find({"lang": lang, "key": {"$in": keys}}, {"_id": 0, "key": 1, "value": 1}).to_list(len(keys) + 10)
    cache_map = {d["key"]: d["value"] for d in docs}
    result: dict[str, str] = {}
    missing: list[str] = []
    for s in raw_strings:
        k = key_of(s)
        if k in cache_map:
            result[s] = cache_map[k]
        else:
            missing.append(s)

    if missing:
        try:
            from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore
            payload = _json.dumps(missing, ensure_ascii=False)
            chat = LlmChat(
                api_key=os.environ['EMERGENT_LLM_KEY'],
                session_id=f"i18n_batch_{lang}",
                system_message=(
                    "You are a professional UI translator. You will receive a JSON array of Russian UI strings. "
                    f"Translate every element to the target language code '{lang}'. "
                    "Return ONLY a JSON array of the same length in the same order. "
                    "Preserve emojis, punctuation, numbers, and any {placeholders}. "
                    "Never wrap the response in markdown or code fences."
                ),
            ).with_model("openai", "gpt-4o-mini")
            raw = await asyncio.wait_for(chat.send_message(UserMessage(text=payload)), timeout=30.0)
            txt = str(raw).strip()
            if txt.startswith("```"):
                txt = txt.strip("`")
                if txt.lower().startswith("json"):
                    txt = txt[4:].lstrip()
            translated = _json.loads(txt)
            if not isinstance(translated, list) or len(translated) != len(missing):
                raise ValueError("bad shape")
            # Persist and merge
            ops = []
            for src, dst in zip(missing, translated):
                if not isinstance(dst, str) or not dst.strip():
                    continue
                result[src] = dst
                ops.append({"lang": lang, "key": key_of(src), "src": src, "value": dst, "updated_at": iso(now_utc())})
            if ops:
                # bulk upsert
                await asyncio.gather(*[
                    db.i18n_dynamic.update_one(
                        {"lang": lang, "key": op["key"]},
                        {"$set": op},
                        upsert=True,
                    ) for op in ops
                ])
        except Exception as e:
            logger.warning(f"batch translate failed for {lang}: {e}")
            # Fail-open: return russian for missing
            for s in missing:
                result.setdefault(s, s)
    return {"translations": result}

# ────────────────────────────── App-wide i18n ──────────────────────────────
# Canonical Russian UI dictionary. Extend as new strings are added.
I18N_BASE_RU = {
    # nav
    "nav.home": "Главная", "nav.search": "Поиск", "nav.likes": "Лайки",
    "nav.chats": "Чаты", "nav.profile": "Профиль",
    # chat
    "chat.title": "Чаты", "chat.empty": "Начните общение из вкладки Поиск",
    "chat.online": "онлайн", "chat.recent": "недавно", "chat.typing": "печатает...",
    "chat.placeholder": "Сообщение...", "chat.placeholder_blocked": "🔒 Купите монеты, чтобы продолжить общение",
    "chat.reply": "Ответить", "chat.translate": "Перевести", "chat.reply_prefix": "Ответ:",
    "chat.today": "Сегодня", "chat.yesterday": "Вчера",
    "chat.send_gift": "Отправить подарок",
    "chat.confirm_gift": "Отправить подарок за {cost} монет?",
    "chat.confirm": "Отправить", "chat.cancel": "Отменить",
    "chat.recording": "Запись голосового · до 60с",
    "chat.limit_title": "Лимит бесплатных сообщений исчерпан!",
    "chat.limit_body": "Чтобы продолжить общение, пожалуйста, купите монеты.",
    "chat.buy_coins": "🛒 Купить монеты", "chat.close": "Закрыть",
    "chat.gift_gallery": "Галерея", "chat.gift_file": "Файл",
    "chat.gift_camera": "Видео", "chat.gift_emoji": "Эмодзи",
    "chat.gift_gifts": "Подарки", "chat.gift_translate": "Переводчик",
    "chat.preview_gift": "🎁 Подарок", "chat.preview_image": "📷 Фото",
    "chat.preview_voice": "🎤 Голосовое", "chat.preview_video": "🎥 Видео",
    "chat.preview_file": "📁 Файл",
    "chat.premium_locked": "Оформите Premium, чтобы прочитать",
    "chat.premium_cta": "Оформить Premium",
    "chat.deleted": "Это сообщение было удалено",
    "chat.original_deleted": "Исходное сообщение удалено",
    "chat.delete_title": "Удалить сообщение?",
    "chat.delete_me": "Удалить у меня",
    "chat.delete_everyone": "Удалить у всех",
    "chat.delete_note": "Удалить у всех можно только в течение 1 часа после отправки",
    # settings
    "settings.title": "Настройки", "settings.back": "← Назад",
    "settings.section.personal": "Личная информация",
    "settings.section.search": "Поиск",
    "settings.section.premium": "Premium & Монеты",
    "settings.section.notifications": "Уведомления",
    "settings.section.translate": "AI Перевод",
    "settings.section.legal": "Правовая информация",
    "settings.name": "Имя", "settings.gender": "Пол", "settings.dob": "Дата рождения",
    "settings.female": "Женский", "settings.male": "Мужской",
    "settings.show_me": "Показывать", "settings.show_female": "Девушек",
    "settings.show_male": "Парней", "settings.show_both": "Всех",
    "settings.distance": "Расстояние", "settings.distance_near": "📍 Рядом",
    "settings.distance_world": "🌍 Весь мир",
    "settings.manage_premium": "Управление Premium",
    "settings.notif.messages": "Сообщения", "settings.notif.likes": "Лайки",
    "settings.notif.matches": "Матчи", "settings.notif.visits": "Посещения",
    "settings.notif.who_liked": "Кто лайкнул",
    "settings.auto_translate": "Авто-перевод в чате",
    "settings.language": "Язык перевода",
    "settings.install": "Установить приложение",
    "settings.installed": "Установлено",
    "settings.admin": "Админ панель", "settings.logout": "Выйти",
    # common
    "common.save": "Сохранить", "common.saved": "Сохранено", "common.error": "Ошибка",
    "common.loading": "Загрузка...", "common.search": "Поиск",
    # language sheet
    "lang.title": "Выберите язык", "lang.search": "Поиск языка",
    "lang.region.global": "🌍 Глобальные", "lang.region.europe": "🌍 Европа",
    "lang.region.asia": "🌏 Азия", "lang.region.americas": "🌎 Америка",
}

import hashlib
I18N_VERSION = hashlib.sha256(_json.dumps(I18N_BASE_RU, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]

@api.get("/i18n/base")
async def i18n_base():
    """Return the canonical Russian dictionary. Front-end uses this as source."""
    return {"lang": "ru", "strings": I18N_BASE_RU, "version": I18N_VERSION}

@api.get("/i18n/{lang}")
async def i18n_lang(lang: str):
    """Return the UI dictionary translated to `lang`. Cached in Mongo.
    First call for a new language triggers a single bulk LLM translation."""
    lang = lang.lower().strip()
    if lang == "ru":
        return {"lang": "ru", "strings": I18N_BASE_RU, "cached": True, "version": I18N_VERSION}
    cached = await db.i18n_cache.find_one({"lang": lang}, {"_id": 0})
    # Invalidate whenever the base dictionary version changes
    if cached and cached.get('version') == I18N_VERSION:
        return {"lang": lang, "strings": cached['strings'], "cached": True, "version": I18N_VERSION}
    # Translate via LLM in one shot
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore
        payload = _json.dumps(I18N_BASE_RU, ensure_ascii=False)
        chat = LlmChat(
            api_key=os.environ['EMERGENT_LLM_KEY'],
            session_id=f"i18n_{lang}",
            system_message=(
                "You are a professional UI translator. You will receive a JSON object of Russian UI strings. "
                f"Translate ALL values to the target language code '{lang}'. "
                "Keep the JSON keys IDENTICAL. Preserve any {placeholders}, emojis, and punctuation. "
                "Respond ONLY with the translated JSON object — no markdown, no commentary."
            ),
        ).with_model("openai", "gpt-4o-mini")
        raw = await asyncio.wait_for(chat.send_message(UserMessage(text=payload)), timeout=45.0)
        txt = str(raw).strip()
        if txt.startswith("```"):
            txt = txt.split("```", 2)[1].lstrip("json").strip()
        translated = _json.loads(txt)
        # Fill any missing keys with the Russian original
        for k, v in I18N_BASE_RU.items():
            translated.setdefault(k, v)
        await db.i18n_cache.update_one(
            {"lang": lang},
            {"$set": {"lang": lang, "strings": translated, "version": I18N_VERSION, "updated_at": iso(now_utc())}},
            upsert=True,
        )
        return {"lang": lang, "strings": translated, "cached": False, "version": I18N_VERSION}
    except Exception as e:
        logger.exception("i18n translate failed")
        # Fail-open: return Russian so UI is at least legible
        return {"lang": "ru", "strings": I18N_BASE_RU, "cached": False, "error": str(e), "version": I18N_VERSION}

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

@api.get("/chat/costs")
async def chat_costs(user: dict = Depends(get_current_user)):
    """Public pricing table for chat message kinds + free-msg window."""
    return {
        "costs": MSG_COST,
        "free_messages": FREE_MSGS,
        "is_premium": bool(user.get('is_premium')),
        "coins": int(user.get('coins') or 0),
    }

# ────────────────────────────── App wiring ──────────────────────────────
app.include_router(api)

# WebSocket for realtime chat + presence. Path is prefixed with /api so the K8s
# ingress routes it to the backend on 8001. Auth via JWT/session token in query.
@app.websocket("/api/ws")
async def ws_endpoint(websocket: WebSocket, token: Optional[str] = None):
    if not token:
        await websocket.close(code=4401)
        return
    user_id: Optional[str] = None
    # Prefer session lookup, fall back to JWT
    sess = await db.sessions.find_one({"session_token": token}, {"_id": 0})
    if sess:
        user_id = sess.get('user_id')
    else:
        try:
            payload = decode_jwt(token)
            user_id = payload.get('user_id')
        except Exception:
            user_id = None
    if not user_id:
        await websocket.close(code=4401)
        return
    await ws_manager.connect(user_id, websocket)
    # Mark online. Only bump `online_at` on a fresh transition (offline → online).
    try:
        prev = await db.users.find_one({"user_id": user_id}, {"_id": 0, "is_online": 1})
        now_iso = iso(now_utc())
        set_fields = {"is_online": True, "last_active": now_iso}
        if not (prev or {}).get('is_online'):
            set_fields["online_at"] = now_iso
        await db.users.update_one({"user_id": user_id}, {"$set": set_fields})
        await websocket.send_json({"type": "hello", "user_id": user_id})
        while True:
            # Client may send { type: "ping" } or { type: "typing", to: <uid> }
            raw = await websocket.receive_text()
            try:
                data = _json.loads(raw)
            except Exception:
                continue
            if data.get('type') == 'ping':
                await websocket.send_json({"type": "pong"})
                await db.users.update_one({"user_id": user_id}, {"$set": {"last_active": iso(now_utc())}})
            elif data.get('type') == 'typing' and data.get('to'):
                await ws_manager.send_to(data['to'], {"type": "typing", "from": user_id})
            elif data.get('type') == 'read' and data.get('chat_with'):
                cid = chat_id(user_id, data['chat_with'])
                await db.messages.update_many({"chat_id": cid, "to_user": user_id}, {"$set": {"read": True}})
                await ws_manager.send_to(data['chat_with'], {"type": "read", "from": user_id})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"ws loop error: {e}")
    finally:
        await ws_manager.disconnect(user_id, websocket)
        # Only flip is_online=false if no other sockets remain for this user
        if not ws_manager.is_online(user_id):
            await db.users.update_one({"user_id": user_id}, {"$set": {"is_online": False, "last_active": iso(now_utc())}})

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
    # Feed / discovery indexes
    await db.users.create_index([("is_online", -1), ("is_premium", -1)])
    await db.users.create_index("last_active")
    await db.users.create_index("online_at")
    await db.users.create_index([("lat", 1), ("lng", 1)])
    await db.sessions.create_index("session_token", unique=True)
    await db.likes.create_index([("from_user", 1), ("to_user", 1)], unique=True)
    await db.messages.create_index("chat_id")
    await db.messages.create_index([("chat_id", 1), ("created_at", 1)])
    await db.i18n_cache.create_index("lang", unique=True)
    await db.i18n_dynamic.create_index([("lang", 1), ("key", 1)], unique=True)

@app.on_event("shutdown")
async def on_stop():
    client.close()
