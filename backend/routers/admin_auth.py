"""Admin Panel login — credentials come ONLY from ADMIN_EMAIL / ADMIN_PASSWORD env vars."""
import asyncio
import hmac
import uuid
from datetime import timedelta
from fastapi import HTTPException, Depends, Request
from pydantic import BaseModel, Field
from server import (
    api, db, logger, now_utc, iso,
    ADMIN_EMAIL, ADMIN_PASSWORD, make_admin_jwt, verify_admin,
)

MAX_FAILS = 5
LOCKOUT = timedelta(minutes=15)
FAIL_DELAY_SECONDS = 1.0


class AdminLoginBody(BaseModel):
    email: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=200)


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return (fwd.split(",")[0].strip() if fwd else "") or (request.client.host if request.client else "unknown")


def _parse(ts):
    from datetime import datetime
    return datetime.fromisoformat(ts) if ts else None


@api.post("/admin/login")
async def admin_login(body: AdminLoginBody, request: Request):
    ip = _client_ip(request)
    rec = await db.admin_login_attempts.find_one({"ip": ip}, {"_id": 0}) or {}
    locked_until = _parse(rec.get("locked_until"))
    if locked_until and locked_until > now_utc():
        mins = max(1, int((locked_until - now_utc()).total_seconds() // 60) + 1)
        raise HTTPException(status_code=429, detail=f"Too many failed attempts. Try again in {mins} min.")

    email_ok = hmac.compare_digest(body.email.strip().lower().encode(), ADMIN_EMAIL.lower().encode())
    pass_ok = hmac.compare_digest(body.password.encode(), ADMIN_PASSWORD.encode())
    if not (email_ok and pass_ok):
        prev = 0 if locked_until else int(rec.get("fails", 0))
        fails = prev + 1
        upd = {"ip": ip, "fails": fails, "last_fail": iso(now_utc())}
        if fails >= MAX_FAILS:
            upd.update({"locked_until": iso(now_utc() + LOCKOUT), "fails": 0})
        await db.admin_login_attempts.update_one({"ip": ip}, {"$set": upd}, upsert=True)
        logger.warning(f"[admin-auth] failed login from {ip} ({fails}/{MAX_FAILS})")
        await asyncio.sleep(FAIL_DELAY_SECONDS)
        raise HTTPException(status_code=401, detail="Invalid email or password")

    await db.admin_login_attempts.delete_one({"ip": ip})
    jti = uuid.uuid4().hex
    await db.admin_sessions.insert_one({
        "jti": jti, "revoked": False, "ip": ip,
        "user_agent": request.headers.get("user-agent", "")[:200], "created_at": iso(now_utc()),
    })
    logger.info(f"[admin-auth] admin login from {ip}")
    return {"success": True, "token": make_admin_jwt(jti)}


@api.get("/admin/verify-token")
async def admin_verify_token(admin: dict = Depends(verify_admin)):
    return {"valid": True, "email": admin["email"]}


@api.post("/admin/logout")
async def admin_logout(admin: dict = Depends(verify_admin)):
    await db.admin_sessions.update_one({"jti": admin["admin_jti"]}, {"$set": {"revoked": True, "revoked_at": iso(now_utc())}})
    return {"success": True}
