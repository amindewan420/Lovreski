"""Admin Panel login — credentials come ONLY from ADMIN_EMAIL / ADMIN_PASSWORD env vars."""
import asyncio
import hmac
import uuid
from fastapi import HTTPException, Depends, Request
from pydantic import BaseModel, Field
from server import (
    api, db, logger, now_utc, iso, fcm,
    ADMIN_EMAIL, ADMIN_PASSWORD, make_admin_jwt, verify_admin,
    client_ip, lockout_remaining, register_failed_login, clear_failed_logins,
)

MAX_FAILS_PER_IP = 5
MAX_FAILS_GLOBAL = 20
FAIL_DELAY_SECONDS = 1.0


class AdminLoginBody(BaseModel):
    email: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=200)


@api.post("/admin/login")
async def admin_login(body: AdminLoginBody, request: Request):
    ip = client_ip(request)
    ip_key, global_key = f"admin-ip:{ip}", "admin-global"
    left = max(await lockout_remaining(ip_key), await lockout_remaining(global_key))
    if left:
        raise HTTPException(status_code=429, detail=f"Too many failed attempts. Try again in {left // 60 + 1} min.")

    email_ok = hmac.compare_digest(body.email.strip().lower().encode(), ADMIN_EMAIL.lower().encode())
    pass_ok = hmac.compare_digest(body.password.encode(), ADMIN_PASSWORD.encode())
    if not (email_ok and pass_ok):
        await register_failed_login(ip_key, MAX_FAILS_PER_IP)
        await register_failed_login(global_key, MAX_FAILS_GLOBAL)
        if await lockout_remaining(ip_key) or await lockout_remaining(global_key):
            asyncio.create_task(fcm.notify_admin_security(db, "🚨 Вход в админ-панель заблокирован",
                                                          f"Слишком много неверных попыток · IP {ip}"))
        logger.warning(f"[admin-auth] failed admin login from {ip}")
        await asyncio.sleep(FAIL_DELAY_SECONDS)
        raise HTTPException(status_code=401, detail="Invalid email or password")

    await clear_failed_logins(ip_key, global_key)
    jti = uuid.uuid4().hex
    await db.admin_sessions.insert_one({
        "jti": jti, "revoked": False, "ip": ip,
        "user_agent": request.headers.get("user-agent", "")[:200], "created_at": iso(now_utc()),
    })
    logger.info(f"[admin-auth] admin login from {ip}")
    ua = request.headers.get("user-agent", "")[:60]
    asyncio.create_task(fcm.notify_admin_security(db, "🔐 Вход в админ-панель", f"IP {ip} · {ua}"))
    return {"success": True, "token": make_admin_jwt(jti)}


@api.get("/admin/verify-token")
async def admin_verify_token(admin: dict = Depends(verify_admin)):
    return {"valid": True, "email": admin["email"]}


@api.post("/admin/logout")
async def admin_logout(admin: dict = Depends(verify_admin)):
    await db.admin_sessions.update_one({"jti": admin["admin_jti"]}, {"$set": {"revoked": True, "revoked_at": iso(now_utc())}})
    return {"success": True}
