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

# ── Unified storage: Cloudinary when configured, GridFS fallback ──
import storage as _cloud  # noqa: E402

async def storage_put(content: bytes, filename: str, content_type: str, metadata: Optional[dict] = None) -> str:
    """Store raw bytes in the active storage backend and return the
    client-facing URL (/api/files/<id>). Cloudinary when configured,
    otherwise GridFS. On any Cloudinary failure we fall back to GridFS so
    uploads never break."""
    meta = metadata or {}
    if _cloud.is_configured():
        try:
            up = await _cloud.upload_bytes(content, filename, content_type, meta.get("owner_id"), meta.get("kind") or "other")
            file_id = uuid.uuid4().hex[:24]  # 24-hex so signed-URL regexes keep working
            await db.cloud_files.insert_one({
                "_id": file_id,
                "cloudinary_public_id": up["public_id"],
                "resource_type": up["resource_type"],
                "access_type": up["type"],
                "bytes": up["bytes"],
                "format": up["format"],
                "content_type": content_type,
                "filename": filename,
                "kind": meta.get("kind") or "other",
                "owner_id": meta.get("owner_id"),
                "created_at": iso(now_utc()),
            })
            return gridfs_url(file_id)
        except Exception as e:
            logger.warning(f"[storage] Cloudinary upload failed, falling back to GridFS: {e}")
    return gridfs_url(await gridfs_put(content, filename, content_type, metadata))

def _guess_ext(content_type: str) -> str:
    return {
        "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif",
        "audio/webm": ".webm", "audio/mp4": ".m4a", "audio/mpeg": ".mp3", "audio/wav": ".wav",
        "video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov",
        "application/pdf": ".pdf",
    }.get(content_type, "")

async def store_data_url_in_gridfs(data_url: str, owner_id: Optional[str], kind: str) -> str:
    """Decode a data:URL and store it (Cloudinary when configured, else GridFS).
    Returns the client-facing URL."""
    if not data_url.startswith("data:"):
        raise ValueError("Not a data URL")
    header, b64 = data_url.split(",", 1)
    # header = "data:<mime>;base64"
    content_type = header[5:].split(";")[0] or "application/octet-stream"
    raw = base64.b64decode(b64)
    filename = f"{kind}_{uuid.uuid4().hex[:12]}{_guess_ext(content_type)}"
    return await storage_put(raw, filename, content_type, {"owner_id": owner_id, "kind": kind})

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
def chat_id(a: str, b: str) -> str:
    return "chat_" + "_".join(sorted([a, b]))

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
        url_map = {"success": "/premium", "warning": "/settings", "error": "/premium"}
        await fcm.send_to_user(
            db, user_id,
            title="Lovreski",
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
}

I18N_VERSION = hashlib.sha256(_json.dumps(I18N_BASE_RU, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]


# ────────────────────────────── Router Registration ──────────────────────────────
# Importing routers triggers their @api.X decorators to register routes on the shared api instance.
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
    await db.cloud_files.create_index("kind")
    await db.cloud_files.create_index("owner_id")
    # Initialize Firebase (safe no-op if env vars are missing)
    fcm.init_fcm()

@app.on_event("shutdown")
async def on_stop():
    client.close()
