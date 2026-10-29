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
import hmac
import re
import hashlib
from cryptography.fernet import Fernet, InvalidToken
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing import List, Optional, Literal
from datetime import datetime, timezone, timedelta

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# FCM Push Notifications module (fails-safe if Firebase env vars are missing)
import push as fcm

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

JWT_SECRET = os.environ['JWT_SECRET']
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

ADMIN_EMAIL = os.environ['ADMIN_EMAIL'].strip()
ADMIN_PASSWORD = os.environ['ADMIN_PASSWORD']

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

# ── Signed file URLs (short-lived, HMAC-based) ──
FILE_URL_TTL_SECONDS = int(os.environ.get('FILE_URL_TTL_SECONDS', '600'))
_FILE_SIGN_SECRET = (os.environ.get('FILE_SIGN_SECRET') or JWT_SECRET).encode()
_FILE_URL_RE = re.compile(r"/api/files/([0-9a-f]{24})")

def sign_file_url(url: Optional[str], ttl: int = FILE_URL_TTL_SECONDS) -> Optional[str]:
    """Turn a plain /api/files/<id> URL into a short-lived signed URL.
    Non-file URLs are returned unchanged."""
    if not url:
        return url
    m = _FILE_URL_RE.search(url)
    if not m:
        return url
    exp = int(datetime.now(timezone.utc).timestamp()) + ttl
    sig = hmac.new(_FILE_SIGN_SECRET, f"{m.group(1)}.{exp}".encode(), hashlib.sha256).hexdigest()[:32]
    return f"{url}?exp={exp}&sig={sig}"

def verify_file_sig(file_id: str, exp: Optional[int], sig: Optional[str]) -> bool:
    if not exp or not sig:
        return False
    try:
        if int(exp) < int(datetime.now(timezone.utc).timestamp()):
            return False
    except (TypeError, ValueError):
        return False
    good = hmac.new(_FILE_SIGN_SECRET, f"{file_id}.{exp}".encode(), hashlib.sha256).hexdigest()[:32]
    return hmac.compare_digest(good, sig)

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

# ── Admin Panel auth (separate from user auth; credentials only from env) ──
def admin_fingerprint() -> str:
    """Changes whenever ADMIN_EMAIL/ADMIN_PASSWORD change in .env → old admin tokens become invalid."""
    return hashlib.sha256(f"{ADMIN_EMAIL.lower()}:{ADMIN_PASSWORD}".encode()).hexdigest()[:24]

def make_admin_jwt(jti: str) -> str:
    # No `exp`: admin stays logged in until manual logout (server-side revocation via admin_sessions).
    payload = {"type": "admin", "sub": ADMIN_EMAIL.lower(), "jti": jti, "fp": admin_fingerprint(), "iat": int(now_utc().timestamp())}
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

async def verify_admin(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.lower().startswith('bearer '):
        raise HTTPException(status_code=401, detail="Admin authentication required")
    try:
        payload = pyjwt.decode(authorization.split(' ', 1)[1], JWT_SECRET, algorithms=[JWT_ALG])
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid admin token")
    if (payload.get("type") != "admin" or payload.get("fp") != admin_fingerprint()
            or payload.get("sub") != ADMIN_EMAIL.lower()):
        raise HTTPException(status_code=401, detail="Invalid admin token")
    sess = await db.admin_sessions.find_one({"jti": payload.get("jti"), "revoked": False}, {"_id": 0})
    if not sess:
        raise HTTPException(status_code=401, detail="Admin session ended")
    doc = await db.users.find_one({"email": ADMIN_EMAIL.lower()}, {"_id": 0, "password_hash": 0})
    ident = doc or {"user_id": "admin", "email": ADMIN_EMAIL.lower(), "name": "Admin"}
    ident["is_admin"] = True
    ident["admin_jti"] = payload["jti"]
    return ident

require_admin = verify_admin

# ── Generic brute-force lockout (login_attempts collection) ──
async def lockout_remaining(key: str) -> int:
    rec = await db.login_attempts.find_one({"key": key}, {"_id": 0}) or {}
    lu = rec.get("locked_until")
    if lu:
        left = (datetime.fromisoformat(lu) - now_utc()).total_seconds()
        if left > 0:
            return int(left)
    return 0

async def register_failed_login(key: str, max_fails: int, lock_minutes: int = 15) -> None:
    rec = await db.login_attempts.find_one({"key": key}, {"_id": 0}) or {}
    fails = (0 if rec.get("locked_until") else int(rec.get("fails", 0))) + 1
    upd = {"key": key, "fails": fails, "last_fail": iso(now_utc()), "locked_until": None}
    if fails >= max_fails:
        upd.update({"fails": 0, "locked_until": iso(now_utc() + timedelta(minutes=lock_minutes))})
    await db.login_attempts.update_one({"key": key}, {"$set": upd}, upsert=True)

async def clear_failed_logins(*keys: str) -> None:
    await db.login_attempts.delete_many({"key": {"$in": list(keys)}})

def client_ip(request: Request) -> str:
    """Rightmost X-Forwarded-For hop = address seen by our own ingress (not client-spoofable)."""
    fwd = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
    return fwd[-1] if fwd else (request.client.host if request.client else "unknown")

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
    notif_push: Optional[dict[str, bool]] = None

class MessageBody(BaseModel):
    text: Optional[str] = None
    kind: Literal['text', 'emoji', 'image', 'file', 'gift', 'voice', 'video', 'location'] = 'text'
    media_url: Optional[str] = None
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lng: Optional[float] = Field(default=None, ge=-180, le=180)
    place: Optional[str] = Field(default=None, max_length=200)
    live: bool = False
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
MSG_COST = {"text": 1, "emoji": 2, "image": 5, "file": 5, "voice": 5, "video": 10, "location": 2}
LOCATION_TTL_MINUTES = 5  # shared location links expire 5 min after sharing
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

    async def broadcast_event(self, participants: list, type_: str, data: dict):
        for uid in participants:
            await self.send_to(uid, {"type": type_, "data": data})

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

# ────────────────────────────── GridFS Object Storage ──────────────────────────────
# Files live in the same MongoDB via GridFS (fs.files + fs.chunks). No external
# service, no keys. Files served through /api/files/{file_id} with proper MIME.
from motor.motor_asyncio import AsyncIOMotorGridFSBucket  # noqa: E402
from bson import ObjectId as _ObjectId  # noqa: E402
gridfs_bucket = AsyncIOMotorGridFSBucket(db)

async def gridfs_put(content: bytes, filename: str, content_type: str, metadata: Optional[dict] = None) -> str:
    """Store raw bytes in GridFS and return the file_id as a hex string."""
    meta = {"content_type": content_type, **(metadata or {})}
    file_id = await gridfs_bucket.upload_from_stream(filename, content, metadata=meta)
    return str(file_id)

def gridfs_url(file_id: str) -> str:
    """Client-facing URL for a stored file."""
    return f"/api/files/{file_id}"

# ── Unified storage: Timeweb S3 when configured, GridFS fallback ──
import storage as _cloud  # noqa: E402

async def storage_put(content: bytes, filename: str, content_type: str, metadata: Optional[dict] = None) -> dict:
    """Store raw bytes in the active storage backend.
    Returns {"url": <client-facing URL>, "file_id": <internal id>}.
    S3 configured  → url is the direct public Timeweb URL.
    GridFS fallback → url is /api/files/<id> (streams/redirects through the API).
    On any S3 failure we fall back to GridFS so uploads never break."""
    meta = metadata or {}
    kind = meta.get("kind") or "other"
    if _cloud.is_configured():
        try:
            up = await _cloud.upload_bytes(content, filename, content_type, meta.get("owner_id"), kind)
            file_id = uuid.uuid4().hex[:24]  # 24-hex keeps our signed-URL regexes happy
            await db.s3_files.insert_one({
                "_id": file_id,
                "s3_key": up["public_id"],
                "public_url": up["public_url"],
                "bytes": up["bytes"],
                "content_type": up["content_type"],
                "filename": filename,
                "kind": kind,
                "owner_id": meta.get("owner_id"),
                "created_at": iso(now_utc()),
            })
            return {"url": up["public_url"], "file_id": file_id}
        except Exception as e:
            logger.warning(f"[storage] S3 upload failed, falling back to GridFS: {e}")
    fid = await gridfs_put(content, filename, content_type, metadata)
    return {"url": gridfs_url(fid), "file_id": fid}

def _guess_ext(content_type: str) -> str:
    return {
        "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif",
        "audio/webm": ".webm", "audio/mp4": ".m4a", "audio/mpeg": ".mp3", "audio/wav": ".wav",
        "video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov",
        "application/pdf": ".pdf",
    }.get(content_type, "")

RECEIPT_MIMES = {"image/jpeg", "image/jpg", "image/png", "image/webp", "application/pdf"}
RECEIPT_MAX_BYTES = 10 * 1024 * 1024

def validate_receipt_data_url(data_url: str) -> None:
    """Receipts: JPG/PNG/WEBP/PDF only, ≤10 MB, content must match the declared type."""
    if not isinstance(data_url, str) or not data_url.startswith("data:") or "," not in data_url:
        raise HTTPException(status_code=400, detail="Неверный формат файла")
    header, b64 = data_url.split(",", 1)
    mime = header[5:].split(";")[0].lower()
    if mime not in RECEIPT_MIMES:
        raise HTTPException(status_code=400, detail="Поддерживаются только JPG, PNG или PDF")
    if len(b64) * 3 // 4 > RECEIPT_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Файл больше 10 МБ")
    try:
        head = base64.b64decode(b64[:64] + "=" * (-len(b64[:64]) % 4))
    except Exception:
        raise HTTPException(status_code=400, detail="Файл повреждён")
    if mime == "application/pdf" and not head.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="Файл не является корректным PDF")

async def store_data_url_in_gridfs(data_url: str, owner_id: Optional[str], kind: str) -> str:
    """Decode a data:URL and store it (Timeweb S3 when configured, else GridFS).
    Returns the client-facing URL."""
    if not data_url.startswith("data:"):
        raise ValueError("Not a data URL")
    header, b64 = data_url.split(",", 1)
    # header = "data:<mime>;base64"
    content_type = header[5:].split(";")[0] or "application/octet-stream"
    raw = base64.b64decode(b64)
    filename = f"{kind}_{uuid.uuid4().hex[:12]}{_guess_ext(content_type)}"
    return (await storage_put(raw, filename, content_type, {"owner_id": owner_id, "kind": kind}))["url"]

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

async def _base_candidates(user: dict, pool_limit: int = 500, exclude: tuple = ("like", "pass")) -> list[dict]:
    """Common candidate pool: gender + age-range filter, no blocked/self, no admins.
    `exclude` controls which swipe types drop a profile from the pool:
      Discover → ("like",)   liked users are permanently hidden; skips cycle back
      Home     → ("pass",)   only passes hidden; liked stay visible (flagged liked)
    """
    show_me = user.get('show_me', 'both')
    gender_q: dict = {"gender": show_me} if show_me in ('male', 'female') else {}
    blocked = user.get('blocked', []) + [user['user_id']]
    swipes = await db.likes.find({"from_user": user['user_id']}, {"_id": 0, "to_user": 1, "type": 1}).to_list(2000)
    already = {s['to_user'] for s in swipes if s.get('type') in exclude}
    already.update(blocked)
    q = {"user_id": {"$nin": list(already)}, "is_admin": {"$ne": True}, "deactivated": {"$ne": True}, **gender_q}
    pool = await db.users.find(q, {"_id": 0, "password_hash": 0}).limit(pool_limit).to_list(pool_limit)
    # Age-range filter (from Settings → Поиск → Возраст)
    amin = user.get('age_min') or 18
    amax = user.get('age_max') or 85
    if amin != 18 or amax != 85:
        pool = [u for u in pool if amin <= calc_age(u.get('dob', '')) <= amax]
    return pool
def chat_id(a: str, b: str) -> str:
    return "chat_" + "_".join(sorted([a, b]))

def expire_location(m: dict) -> dict:
    """Strip coordinates from location messages once they expire (5 min). Expiry is exposed for countdowns."""
    if m.get('kind') != 'location' or not m.get('location'):
        return m
    exp = m.get('location_expires_at')
    try:
        exp_dt = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
        if exp_dt.tzinfo is None:
            exp_dt = exp_dt.replace(tzinfo=timezone.utc)
    except Exception:
        exp_dt = None
    if exp_dt is None or now_utc() >= exp_dt:
        m['location'] = None
        m['location_expired'] = True
    else:
        m['location_expired'] = False
    return m

def _decorate_msg(m: dict, viewer_id: str, viewer_is_premium: bool) -> dict:
    """Apply locked flag: incoming messages from partner beyond the 2 free window
    are hidden unless the viewer has Premium. Free users see the message exists
    but content is masked with an upgrade prompt."""
    m = {k: v for k, v in m.items() if k != '_id'}
    # Media is served via short-lived signed URLs (files router enforces access).
    if m.get('media_url'):
        m['media_url'] = sign_file_url(m['media_url'])
    if m.get('from_user') != viewer_id and not viewer_is_premium:
        # Count position of this message among partner's messages in the chat
        pass  # handled in bulk below for efficiency
    return m

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
    if body.kind == 'location' and (body.lat is None or body.lng is None):
        raise HTTPException(status_code=400, detail="Location requires lat/lng")
    cid = chat_id(sender['user_id'], other_id)
    sent_count = await db.messages.count_documents({"chat_id": cid, "from_user": sender['user_id']})
    is_admin_sender = False

    # Refresh coin/premium status from DB
    fresh = await db.users.find_one({"user_id": sender['user_id']}, {"_id": 0, "coins": 1, "is_premium": 1})
    coins = int((fresh or {}).get('coins') or 0)
    is_premium = bool((fresh or {}).get('is_premium'))

    within_free = sent_count < FREE_MSGS
    # First 2 messages are ALWAYS free (any kind). After that:
    #   - If user has enough coins → deduct
    #   - Otherwise → 402 with `blocked=True` in body so client shows purchase popup
    # Location sharing is ALWAYS paid (2 coins), even inside the free-message quota.
    if (within_free or is_admin_sender) and body.kind != 'location':
        cost_paid = 0
    else:
        if coins < cost:
            raise HTTPException(status_code=402, detail={
                "message": "Недостаточно монет. Купите монеты, чтобы продолжить." if body.kind == 'location' else "Купите монеты, чтобы продолжить общение",
                "blocked": True,
                "required": cost,
                "have": coins,
                "kind": body.kind,
            })
        # Atomic check-and-deduct (prevents double-spend from parallel requests)
        res = await db.users.update_one({"user_id": sender['user_id'], "coins": {"$gte": cost}}, {"$inc": {"coins": -cost}})
        if res.modified_count == 0:
            raise HTTPException(status_code=402, detail={"message": "Недостаточно монет. Купите монеты, чтобы продолжить.",
                                                         "blocked": True, "required": cost, "have": 0, "kind": body.kind})
        cost_paid = cost
    msg = {
        "message_id": f"msg_{uuid.uuid4().hex[:12]}",
        "chat_id": cid,
        "participants": sorted([sender['user_id'], other_id]),
        "from_user": sender['user_id'],
        "to_user": other_id,
        "kind": body.kind,
        "text": "" if body.kind == 'location' else (body.text or ""),
        "media_url": body.media_url,
        "file_name": body.file_name,
        "gift_key": body.gift_key,
        "reply_to": body.reply_to,
        **({"location": {"lat": body.lat, "lng": body.lng, "place": body.place or "", "live": bool(body.live),
                         "token": uuid.uuid4().hex, "updated_at": iso(now_utc())},
            "location_expires_at": iso(now_utc() + timedelta(minutes=LOCATION_TTL_MINUTES))} if body.kind == 'location' else {}),
        "read": False,
        "cost_paid": cost_paid,
        "created_at": iso(now_utc()),
    }
    await db.messages.insert_one(msg)
    msg.pop('_id', None)
    # Sign media_url copies for transport (DB keeps the plain URL).
    if msg.get('media_url'):
        msg['media_url'] = sign_file_url(msg['media_url'])
    # Broadcast to both participants via WS (fire-and-forget)
    try:
        await ws_manager.broadcast_message(msg)
    except Exception as e:
        logger.warning(f"ws broadcast failed: {e}")
    # FCM push to recipient — only if they are not actively connected.
    try:
        preview_map = {
            "text": body.text or "",
            "emoji": body.text or "",
            "image": "🖼 Фото",
            "video": "🎬 Видео",
            "voice": "🎤 Голосовое сообщение",
            "file": f"📎 {body.file_name or 'Файл'}",
            "gift": "🎁 Подарок",
            "location": "📍 Местоположение",
        }
        preview = preview_map.get(body.kind, body.text or "Новое сообщение")
        await fcm.notify_chat_message(
            db, ws_manager,
            recipient_id=other_id,
            sender_name=sender.get("name") or "Lovreski",
            preview=preview,
            other_id=sender['user_id'],
        )
    except Exception as e:
        logger.warning(f"[push] chat notify failed: {e}")
    return msg
class ChatMediaBody(BaseModel):
    data_url: str
    kind: Literal['image', 'voice', 'video', 'file']
    file_name: Optional[str] = None

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

class ReceiptBody(BaseModel):
    package_id: Optional[str] = None
    receipt_data_url: str  # base64 data URL (JPG/PNG/PDF)
    message: Optional[str] = Field(default=None, max_length=500)

async def _push_notification(user_id: str, message: str, kind: str = "info"):
    await db.notifications.insert_one({
        "id": f"n_{uuid.uuid4().hex[:12]}",
        "user_id": user_id, "message": message, "kind": kind, "read": False,
        "created_at": iso(now_utc()),
    })
    # Also fire a browser Web Push (no-op if Firebase not configured / user offline / no token)
    try:
        url_map = {"success": "/premium", "warning": "/settings", "error": "/premium", "admin_message": "/home"}
        await fcm.send_to_user(
            db, user_id,
            title={"success": "✅ Lovreski", "error": "❌ Lovreski", "warning": "⚠️ Lovreski"}.get(kind, "Lovreski"),
            body=message,
            url=url_map.get(kind, "/"),
            kind=kind,
        )
    except Exception as e:
        logger.warning(f"[push] _push_notification FCM failed: {e}")

class PushTokenBody(BaseModel):
    token: str = Field(min_length=20, max_length=4096)
    platform: str = "web"

class AdminApproveBody(BaseModel):
    coins: int = Field(gt=0, le=100000)
    reason: str = Field(min_length=1, max_length=200)

class AdminRejectBody(BaseModel):
    reason: str = Field(min_length=1, max_length=200)

class CustomCoinAddBody(BaseModel):
    user_id: str
    coins: int = Field(gt=0, le=100000)
    reason: str = Field(min_length=1, max_length=200)
class RefundBody(BaseModel):
    full_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    receipt_data_url: str
    reason: str = Field(min_length=1, max_length=1000)

class UserActionBody(BaseModel):
    reason: Optional[str] = None
    days: Optional[int] = 7

class LegalDocBody(BaseModel):
    slug: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1)

class I18nBatchBody(BaseModel):
    lang: str
    strings: list[str]

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
    "chat.you": "Вы",
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
    "settings.notif.announcements": "Новости от Lovreski",
    "push.prompt_title": "Включить уведомления?",
    "push.prompt_body": "Узнавайте о новых лайках, матчах и сообщениях сразу.",
    "push.enable": "Включить", "push.later": "Позже", "push.open": "Открыть",
    "push.denied": "Уведомления запрещены в настройках браузера",
    "chat.location": "Локация", "chat.preview_locked": "Новое сообщение",
    "chat.show_original": "Показать оригинал", "chat.show_translation": "Показать перевод",
    "chat.translating": "Переводим…",
    # Profile options (values stored in English, labels via t())
    "profile.interests.romance": "Романтика и страсть",
    "profile.interests.romance.kisses": "Поцелуи",
    "profile.interests.romance.hugs": "Объятия",
    "profile.interests.romance.flirt": "Флирт",
    "profile.interests.romance.romantic_dinners": "Романтические ужины",
    "profile.interests.romance.compliments": "Комплименты",
    "profile.interests.romance.massage": "Массаж",
    "profile.interests.romance.touching": "Прикосновения",
    "profile.interests.romance.watch_romantic_movies": "Романтические фильмы",
    "profile.interests.romance.underwear": "Нижнее бельё",
    "profile.interests.romance.deep_conversations": "Глубокие разговоры",
    "profile.interests.romance.dramas": "Драмы",
    "profile.interests.romance.spontaneous_surprises": "Спонтанные сюрпризы",
    "profile.interests.romance.video_games": "Видеоигры",
    "profile.interests.romance.fashion_and_beauty": "Мода и красота",
    "profile.interests.romance.cars": "Автомобили",
    "profile.interests.romance.it_and_tech": "IT и технологии",
    "profile.interests.romance.psychology": "Психология",
    "profile.interests.romance.meditation": "Медитация",
    "profile.interests.romance.language_learning": "Изучение языков",
    "profile.interests.romance.dancing": "Танцы",
    "profile.interests.romance.make_love": "Заниматься любовью",
    "profile.interests.romance.fan_fiction": "Фанфики",
    "profile.interests.social": "Светская жизнь",
    "profile.interests.social.travel": "Путешествия",
    "profile.interests.social.shopping": "Шопинг",
    "profile.interests.social.camping": "Кемпинг",
    "profile.interests.social.museums_and_galleries": "Музеи и галереи",
    "profile.interests.social.partying_and_clubbing": "Вечеринки и клубы",
    "profile.interests.social.meeting_with_friends": "Встречи с друзьями",
    "profile.interests.social.active_recreation": "Активный отдых",
    "profile.interests.social.karaoke": "Караоке",
    "profile.interests.social.art": "Искусство",
    "profile.interests.creative": "Викторины и творчество",
    "profile.interests.creative.photography": "Фотография",
    "profile.interests.creative.music": "Музыка",
    "profile.interests.creative.design": "Дизайн",
    "profile.interests.creative.makeup": "Макияж",
    "profile.interests.creative.blogging": "Блогинг",
    "profile.interests.creative.painting": "Живопись",
    "profile.interests.active": "Активный образ жизни",
    "profile.interests.active.running": "Бег",
    "profile.interests.active.yoga": "Йога",
    "profile.interests.active.fitness": "Фитнес",
    "profile.interests.active.walks": "Прогулки",
    "profile.interests.active.mountain_climbing": "Альпинизм",
    "profile.interests.active.swimming": "Плавание",
    "profile.interests.active.horseback_riding": "Верховая езда",
    "profile.interests.food": "Еда и напитки",
    "profile.interests.food.healthy_eating": "Здоровое питание",
    "profile.interests.food.coffee_and_tea": "Кофе и чай",
    "profile.interests.food.drink_with_friends": "Выпить с друзьями",
    "profile.interests.food.spicy_food": "Острая еда",
    "profile.interests.sports": "Спорт",
    "profile.interests.sports.football": "Футбол",
    "profile.interests.sports.basketball": "Баскетбол",
    "profile.interests.sports.hockey": "Хоккей",
    "profile.interests.sports.swimming": "Плавание",
    "profile.interests.home": "Время дома",
    "profile.interests.home.cooking": "Кулинария",
    "profile.interests.home.board_games": "Настольные игры",
    "profile.interests.home.books": "Книги",
    "profile.interests.personal": "Личностное развитие",
    "profile.interests.personal.online_learning": "Онлайн-обучение",
    "profile.interests.personal.travel": "Путешествия",
    "profile.interests.personal.cartoons": "Мультфильмы",
    "profile.goal.long_term": "Серьёзные отношения",
    "profile.goal.chat": "Общение и новые знакомства",
    "profile.goal.friendship": "Дружба",
    "profile.goal.experience": "Новый опыт",
    "profile.relationship.single": "Свободен(на)",
    "profile.relationship.multiple": "Несколько отношений",
    "profile.relationship.complicated": "Всё сложно",
    "profile.relationship.taken": "Занят(а)",
    "profile.relationship.not_to_answer": "Не хочу отвечать",
    "profile.kids.no_kids": "Нет детей",
    "profile.kids.i_have_kids": "Есть дети",
    "profile.kids.no_answer": "Без ответа",
    "profile.smoking.dont_smoke": "Не курю",
    "profile.smoking.rarely": "Редко",
    "profile.smoking.smoke": "Курю",
    "profile.smoking.not_to_answer": "Не хочу отвечать",
    "profile.alcohol.dont_drink": "Не пью",
    "profile.alcohol.rarely": "Редко",
    "profile.alcohol.drink": "Пью",
    "profile.alcohol.not_to_answer": "Не хочу отвечать",
    "chat.loc_cost": "Отправка локации стоит {n} монеты", "chat.loc_share_live": "Транслировать моё местоположение (5 мин)",
    "chat.loc_no_coins": "Недостаточно монет. Купите монеты, чтобы продолжить.",
    "chat.loc_sent": "Локация отправлена · списано {n} монеты",
    "chat.loc_link_expired": "Срок действия ссылки на локацию истёк", "chat.loc_link_missing": "Ссылка не найдена",
    "chat.loc_distance": "Расстояние до вас: {d}", "chat.loc_copy_link": "Ссылка", "chat.loc_stop_live": "Остановить трансляцию",
    "chat.loc_geo_denied": "Нет доступа к геолокации — разрешите её в настройках браузера",
    "chat.loc_geo_unsupported": "Геолокация не поддерживается этим устройством",
    "chat.copy": "Копировать", "chat.copied": "Сообщение скопировано", "chat.copy_failed": "Не удалось скопировать",
    "chat.select": "Выбрать", "chat.n_selected": "Выбрано: {n}",
    "chat.delete_n_confirm": "Удалить выбранные сообщения ({n})?", "chat.deleted_toast": "Сообщения удалены",
    "media.download": "Скачать", "media.downloading": "Скачивание…", "media.loading": "Загрузка",
    "media.saved_gallery": "Изображение сохранено в галерею",
    "media.saved_downloads_img": "Изображение сохранено в «Загрузки»",
    "media.saved_downloads_pdf": "PDF сохранён в «Загрузки»",
    "media.download_failed": "Не удалось скачать, попробуйте ещё раз",
    "media.load_failed": "Не удалось загрузить файл", "media.retry": "Повторить", "media.try_download": "Попробовать скачать",
    "legal.translated": "Переведено автоматически", "legal.translating": "Переводим документ…", "chat.location_title": "Отправить место встречи",
    "chat.location_hint": "Перетащите метку или нажмите на карту, чтобы выбрать место.",
    "chat.location_safety": "Ради вашей безопасности всегда встречайтесь в людных общественных местах и сообщите друзьям, куда идёте.",
    "chat.location_send": "Отправить локацию", "chat.location_mine": "Моё местоположение",
    "chat.location_expires": "Ссылка на локацию действует 5 минут",
    "chat.location_expired": "Срок действия метки истёк",
    "chat.location_open": "Открыть в Google Картах",
    "chat.location_place_ph": "Название места (необязательно), напр. «Кафе на Тверской»",
    "settings.section.push": "Push-уведомления",
    "settings.push_enable": "Включить push-уведомления",
    "settings.push_disable": "Отключить push-уведомления",
    "settings.push_on": "Push-уведомления включены",
    "settings.push_on_done": "Push-уведомления включены",
    "settings.push_off_done": "Push-уведомления отключены",
    "settings.push_test": "🧪 Отправить тестовое уведомление",
    "settings.push_test_sent": "Тестовое уведомление отправлено",
    "settings.push_pending": "Push-уведомления пока не настроены администратором (нужны ключи Firebase).",
    "settings.push_unsupported": "Ваш браузер не поддерживает Web Push. Установите приложение как PWA.",
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
    # premium & coins page
    "premium.back": "← Назад", "premium.title": "Premium & Монеты",
    "premium.balance": "Ваш баланс", "premium.active": "Premium активен",
    "premium.activate_hint": "Активируйте Premium для всех функций",
    "premium.purchase_history": "История покупок →", "premium.choose_package": "Выберите пакет",
    "premium.popular": "Популярный", "premium.coins_unit": "монет", "premium.per_coin": "₽ / монета",
    "premium.package_note": "Выбор пакета не активирует оплату автоматически — оплатите вручную и отправьте чек ниже.",
    "premium.sbp_label": "Номер СБП для оплаты", "premium.copy": "Копировать",
    "premium.recipient_label": "Получатель:", "premium.recipient_name": "Ал Амин Д.",
    "premium.any_bank": "Оплатите из любого банка (Сбер, T-Bank, Альфа, ВТБ и др.)",
    "premium.rules_title": "ПРАВИЛА АКТИВАЦИИ PREMIUM",
    "premium.rule_1": "Сначала скопируйте номер телефона СБП. Откройте приложение банка, вставьте скопированный номер, выберите понравившийся пакет Premium и оплатите точную сумму.",
    "premium.rule_2": "После оплаты вы ОБЯЗАТЕЛЬНО должны отправить чек/скриншот оплаты в раздел поддержки.",
    "premium.rule_3": "Администратор проверяет каждый чек вручную. Если оплата НЕ поступила на счёт, Premium НЕ будет активирован — даже если чек отправлен.",
    "premium.rule_4": "Время активации Premium строго: по московскому времени с 21:00 до 23:59 (ежедневно).",
    "premium.rule_5": "Перед оплатой Premium пользователь должен убедиться, что имя получателя в банке — «{name}».",
    "premium.rule_6": "Пользователь может выбрать удобный банк (например, Сбербанк, ВТБ и др.) перед оплатой.",
    "premium.rule_7": "Совет администратора: пополняйте монеты / продлевайте Premium ДО окончания срока, чтобы избежать перерыва.",
    "premium.support_button": "Поддержка активации Premium",
    "premium.support_subtitle": "Загрузите чек для проверки администратором",
    "premium.upload_receipt": "Загрузить чек", "premium.message_label": "Сообщение (необязательно)",
    "premium.message_placeholder": "Короткое сообщение...", "premium.submit_button": "Отправить администратору",
    "premium.file_required_note": "Файл обязателен. Сообщение — по желанию.",
    "premium.toast.copied": "Номер скопирован ✓", "premium.toast.copy_failed": "Не удалось скопировать",
    "premium.toast.read_failed": "Не удалось прочитать файл", "premium.toast.need_receipt": "Загрузите чек",
    "premium.toast.sent": "✅ Чек отправлен! Администратор проверит и активирует Premium.",
    "premium.toast.send_error": "Ошибка отправки",
    "receipt.err.type": "Только JPG, PNG или PDF", "receipt.err.size": "Файл больше {mb} МБ",
    "receipt.err.empty": "Файл пустой",
    "apps.title": "Мои заявки", "apps.hint": "Удерживайте заявку, чтобы удалить её из истории",
    "apps.status.verified": "Одобрено", "apps.status.rejected": "Отклонено", "apps.status.pending": "Ожидание",
    "apps.reason": "Причина:", "apps.delete": "Удалить", "apps.cancel": "Отмена",
    "apps.confirm_title": "Удалить эту заявку из истории?",
    "apps.confirm_body": "Это действие нельзя отменить. Ваш Premium и монеты не изменятся.",
    "apps.toast.removed": "Запись удалена из истории", "apps.toast.remove_failed": "Не удалось удалить",
}

I18N_VERSION = hashlib.sha256(_json.dumps(I18N_BASE_RU, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]


# ────────────────────────────── Router Registration ──────────────────────────────
# Importing routers triggers their @api.X decorators to register routes on the shared api instance.
from routers import admin_auth  # noqa: E402,F401
from routers import auth, profile, discover, chat, files, notifications, reports, admin, i18n, demo, misc, cron  # noqa: E402,F401
from routers import coins as _coins_router  # noqa: E402,F401 — aliased to avoid F811 with `coins` local in _do_send_message

app.include_router(api)

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
    await db.push_tokens.create_index("token", unique=True)
    await db.push_tokens.create_index([("user_id", 1), ("last_seen", -1)])
    await db.s3_files.create_index("kind")
    await db.admin_sessions.create_index("jti", unique=True)
    await db.login_attempts.create_index("key", unique=True)
    await db.content_translations.create_index([("lang", 1), ("key", 1)], unique=True)
    await db.messages.create_index("location.token", sparse=True)
    from routers.admin import prewarm_all_legal
    asyncio.create_task(prewarm_all_legal())
    await db.s3_files.create_index("owner_id")
    await db.profile_visits.create_index([("viewer", 1), ("target", 1)], unique=True)
    # Initialize Firebase from Admin-Panel config (no-op if not configured)
    await fcm.get_app(db)

@app.on_event("shutdown")
async def on_stop():
    client.close()
