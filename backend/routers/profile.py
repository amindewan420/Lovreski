"""Profile routes — /profile/*"""
from fastapi import HTTPException, Depends
from typing import List
from pydantic import BaseModel
import uuid
from server import (
    api, db, logger, now_utc, iso,
    get_current_user, user_public, calc_age,
    _compress_image_data_url, storage_put, store_data_url_in_gridfs,
    _verify_gender_from_photo, _profile_completion,
    ProfileUpdate,
)

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
    compressed_url, compressed_bytes = _compress_image_data_url(body.data_url)

    # AI gender verification
    verdict = await _verify_gender_from_photo(compressed_url, (fresh or {}).get('gender', ''))
    if not verdict.get('ok'):
        raise HTTPException(status_code=422, detail=verdict.get('message') or "Photo rejected")

    # Persist to storage (Cloudinary when configured, else GridFS)
    if compressed_bytes:
        stored_url = await storage_put(compressed_bytes, f"photo_{uuid.uuid4().hex[:12]}.jpg", "image/jpeg",
                                       {"owner_id": user['user_id'], "kind": "profile_photo"})
    else:
        stored_url = await store_data_url_in_gridfs(compressed_url, user['user_id'], "profile_photo")
    photos.append(stored_url)
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

def _profile_completion_legacy_removed(u: dict) -> int:  # noqa: unused — kept for history
    return _profile_completion(u)

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

