"""Discovery, Home feed, Likes & Matches routes."""
from fastapi import HTTPException, Depends
from server import (
    api, db, logger, now_utc, iso, fcm,
    get_current_user, user_public,
    _is_online, _parse_dt, _dist_km, _base_candidates,
)

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
        # FCM push to both users on match creation
        try:
            await fcm.notify_match(db, target_id, user.get("name") or "Someone", user['user_id'])
            await fcm.notify_match(db, user['user_id'], target.get("name") or "Someone", target_id)
        except Exception as e:
            logger.warning(f"[push] match notify failed: {e}")
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
