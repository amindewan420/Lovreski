// Display-time translation of user-written profile text (name, about, job…). Stored data is never changed.
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

const HAS_LETTERS = /\p{L}/u;
const cache = new Map(); // `${lang}|${mode}|${text}` -> translated
const inflight = new Set();
const queued = new Map(); // `${lang}|${mode}` -> Set(text)
const subs = new Set();
let timer = null;

const flush = () => {
  timer = null;
  for (const [qk, set] of queued) {
    queued.delete(qk);
    const [lang, mode] = qk.split("|");
    const texts = [...set];
    for (let i = 0; i < texts.length; i += 100) {
      const chunk = texts.slice(i, i + 100);
      api.post("/translate/batch", { target: lang, texts: chunk, mode })
        .then(({ data }) => data?.translations || {})
        .catch(() => ({}))
        .then((tr) => {
          chunk.forEach((t) => { cache.set(`${qk}|${t}`, tr[t] ?? t); inflight.delete(`${qk}|${t}`); });
          subs.forEach((f) => f());
        });
    }
  }
};

export function useContentTx() {
  const { lang } = useI18n();
  const [, force] = useState(0);
  useEffect(() => {
    const f = () => force((x) => x + 1);
    subs.add(f);
    return () => subs.delete(f);
  }, []);
  return useCallback((text, mode = "text") => {
    if (!text || !lang || !HAS_LETTERS.test(text)) return text;
    const key = `${lang}|${mode}|${text}`;
    if (cache.has(key)) return cache.get(key);
    if (!inflight.has(key)) {
      inflight.add(key);
      const qk = `${lang}|${mode}`;
      if (!queued.has(qk)) queued.set(qk, new Set());
      queued.get(qk).add(text);
      if (!timer) timer = setTimeout(flush, 60);
    }
    return text;
  }, [lang]);
}

// Inline translated text; `no-translate` keeps the page-wide auto-translator from touching it twice.
export const Tx = ({ text, mode = "text", className = "", ...rest }) => {
  const tx = useContentTx();
  return <span className={`no-translate ${className}`} {...rest}>{tx(text, mode)}</span>;
};
