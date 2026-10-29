"""Translation & app-wide i18n routes."""
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from translation import translate_texts

# Exact English wording for profile options (source of truth for stored values)
I18N_EN_OVERRIDES = {"profile.interests.romance": "Romance & Passion", "profile.interests.romance.kisses": "Kisses", "profile.interests.romance.hugs": "Hugs", "profile.interests.romance.flirt": "Flirt", "profile.interests.romance.romantic_dinners": "Romantic dinners", "profile.interests.romance.compliments": "Compliments", "profile.interests.romance.massage": "Massage", "profile.interests.romance.touching": "Touching", "profile.interests.romance.watch_romantic_movies": "Watch romantic movies", "profile.interests.romance.underwear": "Underwear", "profile.interests.romance.deep_conversations": "Deep conversations", "profile.interests.romance.dramas": "Dramas", "profile.interests.romance.spontaneous_surprises": "Spontaneous surprises", "profile.interests.romance.video_games": "Video Games", "profile.interests.romance.fashion_and_beauty": "Fashion and Beauty", "profile.interests.romance.cars": "Cars", "profile.interests.romance.it_and_tech": "IT and Tech", "profile.interests.romance.psychology": "Psychology", "profile.interests.romance.meditation": "Meditation", "profile.interests.romance.language_learning": "Language Learning", "profile.interests.romance.dancing": "Dancing", "profile.interests.romance.make_love": "Make Love", "profile.interests.romance.fan_fiction": "Fan Fiction", "profile.interests.social": "Social Life", "profile.interests.social.travel": "Travel", "profile.interests.social.shopping": "Shopping", "profile.interests.social.camping": "Camping", "profile.interests.social.museums_and_galleries": "Museums and Galleries", "profile.interests.social.partying_and_clubbing": "Partying and Clubbing", "profile.interests.social.meeting_with_friends": "Meeting with Friends", "profile.interests.social.active_recreation": "Active Recreation", "profile.interests.social.karaoke": "Karaoke", "profile.interests.social.art": "Art", "profile.interests.creative": "Quizzes & Creativity", "profile.interests.creative.photography": "Photography", "profile.interests.creative.music": "Music", "profile.interests.creative.design": "Design", "profile.interests.creative.makeup": "Makeup", "profile.interests.creative.blogging": "Blogging", "profile.interests.creative.painting": "Painting", "profile.interests.active": "Active Lifestyle", "profile.interests.active.running": "Running", "profile.interests.active.yoga": "Yoga", "profile.interests.active.fitness": "Fitness", "profile.interests.active.walks": "Walks", "profile.interests.active.mountain_climbing": "Mountain Climbing", "profile.interests.active.swimming": "Swimming", "profile.interests.active.horseback_riding": "Horseback Riding", "profile.interests.food": "Food & Drinks", "profile.interests.food.healthy_eating": "Healthy Eating", "profile.interests.food.coffee_and_tea": "Coffee and Tea", "profile.interests.food.drink_with_friends": "Drink with Friends", "profile.interests.food.spicy_food": "Spicy Food", "profile.interests.sports": "Sports", "profile.interests.sports.football": "Football", "profile.interests.sports.basketball": "Basketball", "profile.interests.sports.hockey": "Hockey", "profile.interests.sports.swimming": "Swimming", "profile.interests.home": "Home Time", "profile.interests.home.cooking": "Cooking", "profile.interests.home.board_games": "Board Games", "profile.interests.home.books": "Books", "profile.interests.personal": "Personal Development", "profile.interests.personal.online_learning": "Online Learning", "profile.interests.personal.travel": "Travel", "profile.interests.personal.cartoons": "Cartoons", "profile.goal.long_term": "Long-term commitment", "profile.goal.chat": "To chat and meet new people", "profile.goal.friendship": "Friendship", "profile.goal.experience": "New Experience", "profile.relationship.single": "Single", "profile.relationship.multiple": "Multiple", "profile.relationship.complicated": "Complicated", "profile.relationship.taken": "Taken", "profile.relationship.not_to_answer": "Not to answer", "profile.kids.no_kids": "No kids", "profile.kids.i_have_kids": "I have kids", "profile.kids.no_answer": "No answer", "profile.smoking.dont_smoke": "Don't smoke", "profile.smoking.rarely": "Rarely", "profile.smoking.smoke": "Smoke", "profile.smoking.not_to_answer": "Not to answer", "profile.alcohol.dont_drink": "Don't drink", "profile.alcohol.rarely": "Rarely", "profile.alcohol.drink": "Drink", "profile.alcohol.not_to_answer": "Not to answer"}


def _apply_overrides(lang: str, strings: dict) -> dict:
    return {**strings, **I18N_EN_OVERRIDES} if (lang or "").lower().startswith("en") else strings

from typing import List
import asyncio, hashlib, json as _json
import os
from server import (
    api, db, logger, now_utc, iso,
    get_current_user, TranslateBody,
    I18N_BASE_RU, I18N_VERSION,
)

@api.post("/translate")
async def translate(body: TranslateBody, user: dict = Depends(get_current_user)):
    """Single text → same shared engine as chat batches & legal docs (cached, fail-open)."""
    tr = await translate_texts(db, [body.text], body.target)
    return {"translated": tr.get(body.text, body.text), "target": body.target}


class ContentBatchBody(BaseModel):
    target: str = Field(min_length=2, max_length=10)
    texts: List[str] = Field(max_length=300)


@api.post("/translate/batch")
async def translate_batch(body: ContentBatchBody, user: dict = Depends(get_current_user)):
    """Translate many chat texts in one consistent pass. Returns {translations: {original: translated}}."""
    texts = [t[:4000] for t in body.texts if isinstance(t, str)]
    return {"target": body.target, "translations": await translate_texts(db, texts, body.target)}

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
        return {"lang": lang, "strings": _apply_overrides(lang, cached['strings']), "cached": True, "version": I18N_VERSION}
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
        return {"lang": lang, "strings": _apply_overrides(lang, translated), "cached": False, "version": I18N_VERSION}
    except Exception as e:
        logger.exception("i18n translate failed")
        # Fail-open: return Russian so UI is at least legible
        return {"lang": "ru", "strings": I18N_BASE_RU, "cached": False, "error": str(e), "version": I18N_VERSION}
