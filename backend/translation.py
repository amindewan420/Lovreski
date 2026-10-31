"""Shared content-translation engine (chat messages + legal documents).

Same Emergent-LLM model for everything, cached per (lang, sha(text)) in
`content_translations`, batched, and fail-open (returns the original text)."""
from __future__ import annotations
import asyncio
import hashlib
import json
import logging
import os
import uuid

logger = logging.getLogger("lovreski.translation")

MODEL = ("openai", "gpt-4.1-mini")
CHUNK = 40
MAX_ITEM_CHARS = 6000


def _key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


# ISO-639-1 codes (+ common regional variants) accepted for translation; anything else → no translation.
SUPPORTED_LANGS = set("""af am ar az be bg bn bs ca cs cy da de el en es et eu fa fi fil fr ga gl gu he hi hr hu hy id
is it ja ka kk km kn ko ky lo lt lv mk ml mn mr ms my ne nl no pa pl ps pt ro ru si sk sl sq sr sv sw ta te tg th
tk tl tr uk ur uz vi zh zh-cn zh-tw pt-br as en-us fr-ca es-419 en-gb""".split())


LANG_NAMES = {'af': 'Afrikaans', 'am': 'Amharic', 'ar': 'Arabic', 'az': 'Azerbaijani', 'be': 'Belarusian', 'bg': 'Bulgarian', 'bn': 'Bengali (Bengali script)', 'bs': 'Bosnian', 'ca': 'Catalan', 'cs': 'Czech', 'cy': 'Welsh', 'da': 'Danish', 'de': 'German', 'el': 'Greek', 'en': 'English', 'es': 'Spanish', 'et': 'Estonian', 'eu': 'Basque', 'fa': 'Persian', 'fi': 'Finnish', 'fil': 'Filipino', 'fr': 'French', 'ga': 'Irish', 'gl': 'Galician', 'gu': 'Gujarati', 'he': 'Hebrew', 'hi': 'Hindi (Devanagari script)', 'hr': 'Croatian', 'hu': 'Hungarian', 'hy': 'Armenian', 'id': 'Indonesian', 'is': 'Icelandic', 'it': 'Italian', 'ja': 'Japanese', 'ka': 'Georgian', 'kk': 'Kazakh', 'km': 'Khmer', 'kn': 'Kannada', 'ko': 'Korean', 'ky': 'Kyrgyz', 'lo': 'Lao', 'lt': 'Lithuanian', 'lv': 'Latvian', 'mk': 'Macedonian', 'ml': 'Malayalam', 'mn': 'Mongolian', 'mr': 'Marathi', 'ms': 'Malay', 'my': 'Burmese', 'ne': 'Nepali', 'nl': 'Dutch', 'no': 'Norwegian', 'pa': 'Punjabi', 'pl': 'Polish', 'ps': 'Pashto', 'pt': 'Portuguese', 'ro': 'Romanian', 'ru': 'Russian', 'si': 'Sinhala', 'sk': 'Slovak', 'sl': 'Slovenian', 'sq': 'Albanian', 'sr': 'Serbian', 'sv': 'Swedish', 'sw': 'Swahili', 'ta': 'Tamil', 'te': 'Telugu', 'tg': 'Tajik', 'th': 'Thai', 'tk': 'Turkmen', 'tl': 'Filipino', 'tr': 'Turkish', 'uk': 'Ukrainian', 'ur': 'Urdu', 'uz': 'Uzbek', 'vi': 'Vietnamese', 'zh': 'Chinese (Simplified)', 'zh-cn': 'Chinese (Simplified)', 'zh-tw': 'Chinese (Traditional)', 'pt-br': 'Brazilian Portuguese', 'as': 'Assamese (Bengali-Assamese script, NOT Kazakh)', 'en-us': 'English', 'fr-ca': 'Canadian French', 'es-419': 'Latin American Spanish', 'en-gb': 'British English'}


def lang_label(code: str) -> str:
    return f"{LANG_NAMES.get(code, code)} [code '{code}']"


def norm_lang(lang: str) -> str:
    code = (lang or "").strip().lower()[:10]
    return code if code in SUPPORTED_LANGS else ""


def _system_prompt(lang: str, mode: str) -> str:
    if mode == "name":
        return (
            "You transliterate people's first names for a dating app. You receive a JSON array of names in any script. "
            f"Write EVERY name in the native script of {lang_label(lang)}, keeping its pronunciation "
            "(e.g. 'Мария' -> 'Maria' for en, 'Alex' -> 'অ্যালেক্স' for bn, 'Alex' -> 'Алекс' for ru). Always convert names "
            "written in a different script (Latin, Cyrillic, etc.). Never translate the meaning. Only if a name is already "
            "in the target script, return it unchanged. Keep emojis and numbers. Return ONLY a JSON array of the same length "
            "and order, no code fences, no comments."
        )
    return (
        "You are a professional translator for a dating app. You receive a JSON array of texts in any language. "
        f"Translate EVERY element into {lang_label(lang)}. "
        "If an element is already in that language, return it unchanged. Keep the casual tone, emojis, numbers, "
        "URLs, names, {placeholders}, line breaks and Markdown formatting. Acronyms written in another script "
        "must be transliterated into the target script. Return ONLY a JSON array of the same length and order, "
        "no code fences, no comments."
    )


async def _llm_translate(items: list[str], lang: str, mode: str = "text") -> list[str]:
    from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore
    chat = LlmChat(
        api_key=os.environ["EMERGENT_LLM_KEY"],
        session_id=f"content_tr_{mode}_{lang}_{uuid.uuid4().hex}",
        system_message=_system_prompt(lang, mode),
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

async def translate_texts(db, texts: list[str], lang: str, mode: str = "text") -> dict[str, str]:
    # Backend translation disabled; browser will handle translation.
    uniq = [t for t in dict.fromkeys(texts) if isinstance(t, str) and t.strip()]
    return {t: t for t in uniq}

def split_blocks(body: str) -> list[str]:
    """Paragraph blocks of a Markdown doc — small units give a granular cache."""
    return body.split("\n\n")

async def translate_markdown(db, body: str, lang: str) -> str:
    # Backend translation disabled; return original text.
    return body or ""
