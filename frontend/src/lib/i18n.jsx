// App-wide i18n. Loads Russian base + on-demand translated bundles from backend.
// Persists selected language in localStorage AND on the user profile (language_pref).
import { createContext, useContext, useEffect, useState, useCallback, useMemo } from "react";
import { api } from "./api";
import { useAuth } from "@/context/AuthContext";

const LS_KEY = "lovreski_lang";

export const LANGUAGES = {
  // Global
  global: [
    { code: "en",     flag: "🇺🇸", name: "English" },
  ],
  // Europe
  europe: [
    { code: "ru",     flag: "🇷🇺", name: "Русский" },
    { code: "uk",     flag: "🇺🇦", name: "Українська" },
    { code: "de",     flag: "🇩🇪", name: "Deutsch" },
    { code: "fr",     flag: "🇫🇷", name: "Français" },
    { code: "es",     flag: "🇪🇸", name: "Español" },
    { code: "it",     flag: "🇮🇹", name: "Italiano" },
    { code: "pt",     flag: "🇵🇹", name: "Português" },
    { code: "nl",     flag: "🇳🇱", name: "Nederlands" },
    { code: "pl",     flag: "🇵🇱", name: "Polski" },
    { code: "cs",     flag: "🇨🇿", name: "Čeština" },
    { code: "sk",     flag: "🇸🇰", name: "Slovenčina" },
    { code: "hu",     flag: "🇭🇺", name: "Magyar" },
    { code: "ro",     flag: "🇷🇴", name: "Română" },
    { code: "bg",     flag: "🇧🇬", name: "Български" },
    { code: "hr",     flag: "🇭🇷", name: "Hrvatski" },
    { code: "sr",     flag: "🇷🇸", name: "Српски" },
    { code: "sl",     flag: "🇸🇮", name: "Slovenščina" },
    { code: "et",     flag: "🇪🇪", name: "Eesti" },
    { code: "lv",     flag: "🇱🇻", name: "Latviešu" },
    { code: "lt",     flag: "🇱🇹", name: "Lietuvių" },
    { code: "fi",     flag: "🇫🇮", name: "Suomi" },
    { code: "sv",     flag: "🇸🇪", name: "Svenska" },
    { code: "no",     flag: "🇳🇴", name: "Norsk" },
    { code: "da",     flag: "🇩🇰", name: "Dansk" },
    { code: "el",     flag: "🇬🇷", name: "Ελληνικά" },
    { code: "is",     flag: "🇮🇸", name: "Íslenska" },
    { code: "ga",     flag: "🇮🇪", name: "Gaeilge" },
  ],
  asia: [
    { code: "hi",     flag: "🇮🇳", name: "हिन्दी" },
    { code: "as",     flag: "🇮🇳", name: "অসমীয়া" },
    { code: "bn",     flag: "🇧🇩", name: "বাংলা" },
    { code: "ur",     flag: "🇵🇰", name: "اردو" },
    { code: "ta",     flag: "🇮🇳", name: "தமிழ்" },
    { code: "te",     flag: "🇮🇳", name: "తెలుగు" },
    { code: "ml",     flag: "🇮🇳", name: "മലയാളം" },
    { code: "kn",     flag: "🇮🇳", name: "ಕನ್ನಡ" },
    { code: "mr",     flag: "🇮🇳", name: "मराठी" },
    { code: "gu",     flag: "🇮🇳", name: "ગુજરાતી" },
    { code: "pa",     flag: "🇮🇳", name: "ਪੰਜਾਬੀ" },
    { code: "ne",     flag: "🇳🇵", name: "नेपाली" },
    { code: "si",     flag: "🇱🇰", name: "සිංහල" },
    { code: "zh",     flag: "🇨🇳", name: "中文(简体)" },
    { code: "zh-TW",  flag: "🇹🇼", name: "中文(繁體)" },
    { code: "ja",     flag: "🇯🇵", name: "日本語" },
    { code: "ko",     flag: "🇰🇷", name: "한국어" },
    { code: "th",     flag: "🇹🇭", name: "ไทย" },
    { code: "vi",     flag: "🇻🇳", name: "Tiếng Việt" },
    { code: "id",     flag: "🇮🇩", name: "Bahasa Indonesia" },
    { code: "ms",     flag: "🇲🇾", name: "Bahasa Melayu" },
    { code: "tl",     flag: "🇵🇭", name: "Filipino" },
    { code: "km",     flag: "🇰🇭", name: "ខ្មែរ" },
    { code: "lo",     flag: "🇱🇦", name: "ລາວ" },
    { code: "my",     flag: "🇲🇲", name: "မြန်မာ" },
    { code: "mn",     flag: "🇲🇳", name: "Монгол" },
    { code: "kk",     flag: "🇰🇿", name: "Қазақша" },
    { code: "uz",     flag: "🇺🇿", name: "Oʻzbekcha" },
    { code: "ky",     flag: "🇰🇬", name: "Кыргызча" },
    { code: "tg",     flag: "🇹🇯", name: "Тоҷикӣ" },
    { code: "tr",     flag: "🇹🇷", name: "Türkçe" },
    { code: "fa",     flag: "🇮🇷", name: "فارسی" },
    { code: "ar",     flag: "🇸🇦", name: "العربية" },
    { code: "he",     flag: "🇮🇱", name: "עברית" },
  ],
  americas: [
    { code: "en-US",  flag: "🇺🇸", name: "English (US)" },
    { code: "fr-CA",  flag: "🇨🇦", name: "Français (Canada)" },
    { code: "pt-BR",  flag: "🇧🇷", name: "Português (Brasil)" },
    { code: "es-419", flag: "🌎", name: "Español (Latinoamérica)" },
  ],
};

export const ALL_LANGUAGES = [
  ...LANGUAGES.global,
  ...LANGUAGES.europe,
  ...LANGUAGES.asia,
  ...LANGUAGES.americas,
];

export const getLangMeta = (code) => ALL_LANGUAGES.find((l) => l.code === code) || LANGUAGES.europe[0];

const I18nCtx = createContext({
  lang: "ru",
  strings: {},
  t: (k, vars) => k,
  setLang: async () => {},
  loading: false,
});

export function I18nProvider({ children }) {
  const { user } = useAuth();
  const [lang, setLangState] = useState(() => localStorage.getItem(LS_KEY) || "ru");
  const [strings, setStrings] = useState({});
  const [loading, setLoading] = useState(false);

  const load = useCallback(async (code) => {
    setLoading(true);
    try {
      const { data } = await api.get(`/i18n/${code}`);
      setStrings(data.strings || {});
      setLangState(data.lang);
      localStorage.setItem(LS_KEY, data.lang);
      // If user asked for X but server returned Russian, translation failed.
      // Return that signal to callers so they can toast.
      return { requestedLang: code, actualLang: data.lang, error: data.error };
    } catch (e) {
      console.warn("i18n load failed:", e);
      return { requestedLang: code, actualLang: lang, error: String(e) };
    } finally { setLoading(false); }
  }, [lang]);

  // Initial load
  useEffect(() => { load(lang); }, [load, lang]);

  // Sync from user profile once logged in (server is source of truth)
  useEffect(() => {
    const pref = user?.language_pref;
    if (pref && pref !== lang) { load(pref); }
    // eslint-disable-next-line
  }, [user?.language_pref]);

  const setLang = useCallback(async (code) => {
    const result = await load(code);
    try { await api.put("/profile", { language_pref: code }); } catch { /* noop */ }
    return result;
  }, [load]);

  // ─── Auto DOM translator ─────────────────────────────────────────────
  // Walks visible text nodes + input/textarea placeholders + button titles /
  // aria-labels and translates Cyrillic content in the background via
  // `/api/i18n/translate-batch`. Skips anything inside `.no-translate` and
  // any elements marked `data-no-translate`. Uses a MutationObserver to
  // handle React re-renders.
  useEffect(() => {
    if (lang === "ru") return;
    const RU = /[\u0400-\u04FF]/;
    const seenTextNodes = new WeakSet();
    const seenAttrs = new WeakMap();          // element -> Set(attr-names seen)
    const originals = new WeakMap();          // element -> { attr: original }
    const map = new Map();                    // russian text -> translation
    const pending = new Map();                // text -> [{ kind, node, attr? }]
    let flushTimer = null;
    let disposed = false;

    const inSkipZone = (node) => {
      let el = node.nodeType === 3 ? node.parentElement : node;
      while (el) {
        if (el.dataset && (el.dataset.noTranslate !== undefined)) return true;
        if (el.classList && el.classList.contains("no-translate")) return true;
        // Never touch <script>/<style>/<code>/<pre>
        const tag = el.tagName;
        if (tag === "SCRIPT" || tag === "STYLE" || tag === "CODE" || tag === "PRE") return true;
        el = el.parentElement;
      }
      return false;
    };

    const enqueue = (text, node, attr) => {
      if (!pending.has(text)) pending.set(text, []);
      pending.get(text).push({ node, attr });
      if (flushTimer) return;
      flushTimer = setTimeout(flush, 220);
    };

    const applyTranslation = (text, translated) => {
      const targets = pending.get(text) || [];
      pending.delete(text);
      for (const { node, attr } of targets) {
        if (!node || !node.isConnected) continue;
        try {
          if (attr) {
            // Save original once for possible restore on lang="ru"
            if (!originals.has(node)) originals.set(node, {});
            const origs = originals.get(node);
            if (origs[attr] === undefined) origs[attr] = node.getAttribute(attr);
            node.setAttribute(attr, translated);
          } else {
            if (node.nodeType === 3) {
              // Preserve leading/trailing whitespace of original nodeValue
              const raw = node.nodeValue || "";
              const l = raw.match(/^\s*/)?.[0] || "";
              const r = raw.match(/\s*$/)?.[0] || "";
              node.nodeValue = `${l}${translated}${r}`;
            }
          }
        } catch { /* noop */ }
      }
    };

    const flush = async () => {
      flushTimer = null;
      if (pending.size === 0 || disposed) return;
      const batch = Array.from(pending.keys());
      // Apply already-known translations synchronously
      const missing = [];
      for (const t of batch) {
        if (map.has(t)) applyTranslation(t, map.get(t));
        else missing.push(t);
      }
      if (missing.length === 0) return;
      try {
        const { data } = await api.post("/i18n/translate-batch", { lang, strings: missing });
        if (disposed) return;
        const trans = data.translations || {};
        for (const t of missing) {
          const dst = trans[t] || t;
          map.set(t, dst);
          applyTranslation(t, dst);
        }
      } catch (e) {
        // clear pending to avoid infinite retry loop for this batch
        for (const t of missing) { map.set(t, t); pending.delete(t); }
      }
    };

    const scan = () => {
      if (disposed) return;
      // Text nodes
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
        acceptNode: (n) => (n.nodeValue && RU.test(n.nodeValue) && !seenTextNodes.has(n) && !inSkipZone(n))
          ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT,
      });
      let node;
      while ((node = walker.nextNode())) {
        seenTextNodes.add(node);
        const txt = node.nodeValue.trim();
        if (txt) enqueue(txt, node);
      }
      // Attributes: placeholder / title / aria-label / alt on inputs, buttons, images
      const attrTargets = document.querySelectorAll("[placeholder], [title], [aria-label], [alt]");
      attrTargets.forEach((el) => {
        if (inSkipZone(el)) return;
        const seen = seenAttrs.get(el) || new Set();
        for (const attr of ["placeholder", "title", "aria-label", "alt"]) {
          const v = el.getAttribute(attr);
          if (v && RU.test(v) && !seen.has(attr)) {
            seen.add(attr);
            enqueue(v.trim(), el, attr);
          }
        }
        seenAttrs.set(el, seen);
      });
    };

    scan();
    const observer = new MutationObserver(() => scan());
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: ["placeholder", "title", "aria-label", "alt"],
    });
    return () => {
      disposed = true;
      observer.disconnect();
      if (flushTimer) clearTimeout(flushTimer);
    };
  }, [lang]);

  const t = useCallback((key, vars) => {
    let v = strings[key] ?? key;
    if (vars) for (const [k, val] of Object.entries(vars)) v = v.replace(`{${k}}`, val);
    return v;
  }, [strings]);

  const value = useMemo(() => ({ lang, strings, t, setLang, loading }), [lang, strings, t, setLang, loading]);
  return <I18nCtx.Provider value={value}>{children}</I18nCtx.Provider>;
}

export function useI18n() { return useContext(I18nCtx); }
