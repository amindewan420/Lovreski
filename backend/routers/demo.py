"""Demo profile seed route — /demo/seed"""
import uuid
from server import (
    api, db, logger, now_utc, iso,
    hash_pw,
)

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
