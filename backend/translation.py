"""Shared content-translation engine (chat messages + legal documents).

Same Emergent-LLM model for everything, cached per (lang, sha(text)) in
`content_translations`, batched, and fail-open (returns the original text)."""
from __future__ import annotations
import asyncio
import hashlib
import json
import logging
import os

logger = logging.getLogger("lovreski.translation")

MODEL = ("openai", "gpt-4o-mini")
CHUNK = 40
MAX_ITEM_CHARS = 6000


def _key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


# ISO-639-1 codes (+ common regional variants) accepted for translation; anything else → no translation.
SUPPORTED_LANGS = set("""af am ar az be bg bn bs ca cs cy da de el en es et eu fa fi fil fr ga gl gu he hi hr hu hy id
is it ja ka kk km kn ko ky lo lt lv mk ml mn mr ms my ne nl no pa pl ps pt ro ru si sk sl sq sr sv sw ta te tg th
tk tl tr uk ur uz vi zh zh-cn zh-tw pt-br as en-us fr-ca es-419 en-gb""".split())


def norm_lang(lang: str) -> str:
    code = (lang or "").strip().lower()[:10]
    return code if code in SUPPORTED_LANGS else ""


async def _llm_translate(items: list[str], lang: str) -> list[str]:
    from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore
    chat = LlmChat(
        api_key=os.environ["EMERGENT_LLM_KEY"],
        session_id=f"content_tr_{lang}_{_key(items[0])}",
        system_message=(
            "You are a professional translator for a dating app. You receive a JSON array of texts in any language. "
            f"Translate EVERY element into the language with code '{lang}'. "
            "If an element is already in that language, return it unchanged. Keep the casual tone, emojis, numbers, "
            "URLs, names, line breaks and Markdown formatting. Return ONLY a JSON array of the same length and order, "
            "no code fences, no comments."
        ),
    ).with_model(*MODEL)
    raw = await asyncio.wait_for(chat.send_message(UserMessage(text=json.dumps(items, ensure_ascii=False))), timeout=45.0)
    txt = str(raw).strip()
    if txt.startswith("```"):
        txt = txt.strip("`")
        if txt.lower().startswith("json"):
            txt = txt[4:].lstrip()
    out = json.loads(txt)
    if not isinstance(out, list) or len(out) != len(items):
        raise ValueError("bad shape")
    return [o if isinstance(o, str) and o.strip() else src for o, src in zip(out, items)]


async def translate_texts(db, texts: list[str], lang: str) -> dict[str, str]:
    """Return {original: translated} for every text. Never raises; failures map to the original."""
    lang = norm_lang(lang)
    uniq = [t for t in dict.fromkeys(texts) if isinstance(t, str) and t.strip()]
    if not uniq or not lang:
        return {t: t for t in uniq}
    keys = {t: _key(t) for t in uniq}
    docs = await db.content_translations.find(
        {"lang": lang, "key": {"$in": list(keys.values())}}, {"_id": 0, "key": 1, "value": 1}
    ).to_list(len(keys) + 10)
    cached = {d["key"]: d["value"] for d in docs}
    result = {t: cached[k] for t, k in keys.items() if k in cached}
    missing = [t for t in uniq if t not in result]

    async def run(chunk: list[str]):
        try:
            translated = await _llm_translate([t[:MAX_ITEM_CHARS] for t in chunk], lang)
        except Exception as e:
            logger.warning(f"[translate] {lang} chunk of {len(chunk)} failed: {e}")
            for t in chunk:
                result[t] = t
            return
        for src, dst in zip(chunk, translated):
            result[src] = dst
            await db.content_translations.update_one(
                {"lang": lang, "key": keys[src]},
                {"$set": {"lang": lang, "key": keys[src], "value": dst}}, upsert=True,
            )

    await asyncio.gather(*[run(missing[i:i + CHUNK]) for i in range(0, len(missing), CHUNK)])
    return {t: result.get(t, t) for t in uniq}


def split_blocks(body: str) -> list[str]:
    """Paragraph blocks of a Markdown doc — small units give a granular cache."""
    return body.split("\n\n")


async def translate_markdown(db, body: str, lang: str) -> str:
    blocks = split_blocks(body or "")
    tr = await translate_texts(db, [b for b in blocks if b.strip()], lang)
    return "\n\n".join(tr.get(b, b) if b.strip() else b for b in blocks)
