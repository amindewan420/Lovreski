// Auto-translates every chat text into the app language in one consistent pass.
// Results are cached per language (memory here + server-side DB cache).
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

const memo = new Map(); // lang -> Map(original -> translated)
const HAS_LETTERS = /\p{L}/u;

const cacheFor = (lang) => {
  if (!memo.has(lang)) memo.set(lang, new Map());
  return memo.get(lang);
};

export const translatableTexts = (msgs) => {
  const out = [];
  for (const m of msgs) {
    if (m.deleted || m.locked) continue;
    if ((m.kind === "text" || m.kind === "emoji") && m.text && HAS_LETTERS.test(m.text)) out.push(m.text);
    if (m.kind === "location" && m.location?.place && HAS_LETTERS.test(m.location.place)) out.push(m.location.place);
  }
  return out;
};

export function useChatTranslation(msgs, lang) {
  const [, force] = useState(0);
  const [pending, setPending] = useState(() => new Set());
  const inflight = useRef(new Set());

  useEffect(() => {
    if (!lang) return;
    const cache = cacheFor(lang);
    const missing = [...new Set(translatableTexts(msgs))].filter((t) => !cache.has(t) && !inflight.current.has(`${lang}|${t}`));
    if (!missing.length) return;
    missing.forEach((t) => inflight.current.add(`${lang}|${t}`));
    setPending((p) => new Set([...p, ...missing]));
    // Chunked requests, but results are applied together in one pass.
    const chunks = [];
    for (let i = 0; i < missing.length; i += 100) chunks.push(missing.slice(i, i + 100));
    Promise.all(chunks.map((c) => api.post("/translate/batch", { target: lang, texts: c })
      .then(({ data }) => data?.translations || {})
      .catch(() => ({})))) // fail-open: keep original
      .then((parts) => { const all = Object.assign({}, ...parts); for (const t of missing) cache.set(t, all[t] ?? t); })
      .finally(() => {
        missing.forEach((t) => inflight.current.delete(`${lang}|${t}`));
        setPending((p) => { const n = new Set(p); missing.forEach((t) => n.delete(t)); return n; });
        force((x) => x + 1);
      });
  }, [msgs, lang]);

  const tx = useCallback((text) => (text && lang ? cacheFor(lang).get(text) ?? text : text), [lang]);
  const isTranslated = useCallback((text) => !!text && tx(text) !== text, [tx]);
  const isPending = useCallback((text) => !!text && pending.has(text), [pending]);

  return { tx, isTranslated, isPending, busy: pending.size > 0 };
}
