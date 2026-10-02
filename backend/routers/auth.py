"""Auth routes — /auth/*  (register, login, forgot, reset, session, me, logout)"""
from fastapi import HTTPException, Response, Cookie, Depends
from typing import Optional
from datetime import timedelta
import os, uuid, hashlib
import httpx
import jwt as pyjwt
from server import (
    api, db, logger, now_utc, iso,
    hash_pw, check_pw, make_jwt, decode_jwt,
    get_current_user,
    RegisterBody, LoginBody, SessionExchange, ForgotBody, ResetBody,
    user_public, calc_age,
    JWT_SECRET, JWT_ALG, ADMIN_EMAIL, ADMIN_PASSWORD,
)

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

