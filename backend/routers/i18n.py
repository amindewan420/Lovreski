"""Translation & app-wide i18n routes."""
from fastapi import Depends, HTTPException
from pydantic import BaseModel
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
