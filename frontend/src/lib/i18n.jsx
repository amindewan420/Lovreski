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

  const t = useCallback((key, vars) => {
    let v = strings[key] ?? key;
    if (vars) for (const [k, val] of Object.entries(vars)) v = v.replace(`{${k}}`, val);
    return v;
  }, [strings]);

  const value = useMemo(() => ({ lang, strings, t, setLang, loading }), [lang, strings, t, setLang, loading]);
  return <I18nCtx.Provider value={value}>{children}</I18nCtx.Provider>;
}

export function useI18n() { return useContext(I18nCtx); }
