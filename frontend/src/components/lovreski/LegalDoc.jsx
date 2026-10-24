import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Loader2, AlertTriangle, Globe } from "lucide-react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

// Live list of legal docs (admin custom versions override built-ins), titles in app language.
export function useLegalDocs() {
  const { lang } = useI18n();
  const [docs, setDocs] = useState([]);
  const [error, setError] = useState(false);
  useEffect(() => {
    const plain = () => api.get("/legal", { params: { t: Date.now() } });
    api.get("/legal", { params: { lang, t: Date.now() }, timeout: 30000 })
      .catch(plain)
      .then((r) => { setDocs(r.data || []); setError(false); })
      .catch(() => setError(true));
  }, [lang]);
  return { docs, error };
}

const md = {
  h1: (p) => <h2 className="font-display font-black text-lg mt-5 mb-2" {...p} />,
  h2: (p) => <h3 className="font-display font-bold text-base mt-4 mb-1.5" {...p} />,
  h3: (p) => <h4 className="font-semibold mt-3 mb-1" {...p} />,
  p: (p) => <p className="mb-3 whitespace-pre-wrap" {...p} />,
  ul: (p) => <ul className="list-disc pl-5 mb-3 space-y-1" {...p} />,
  ol: (p) => <ol className="list-decimal pl-5 mb-3 space-y-1" {...p} />,
  a: (p) => <a className="text-primary underline" target="_blank" rel="noreferrer" {...p} />,
  strong: (p) => <strong className="font-bold" {...p} />,
};

export const LegalDocView = ({ slug }) => {
  const { lang, t } = useI18n();
  const [doc, setDoc] = useState(null);
  const [error, setError] = useState("");
  const [orig, setOrig] = useState(false);
  useEffect(() => {
    setDoc(null); setError(""); setOrig(false);
    const get = (params, timeout) => api.get(`/legal/${slug}`, { params: { ...params, t: Date.now() }, timeout });
    // Translated version first; on any failure fall back to the original text.
    get({ lang }, 90000)
      .catch((e) => (e.response?.status === 404 ? Promise.reject(e) : get({}, 20000)))
      .then((r) => setDoc(r.data))
      .catch((e) => setError(e.response?.status === 404 ? "Документ не найден" : "Не удалось загрузить документ"));
  }, [slug, lang]);
  if (error) return <div data-testid="legal-error" className="p-8 flex flex-col items-center gap-2 text-muted-foreground"><AlertTriangle className="w-6 h-6" />{error}</div>;
  if (!doc) return <div data-testid="legal-loading" className="p-10 flex flex-col items-center gap-2 text-muted-foreground text-sm"><Loader2 className="w-6 h-6 animate-spin" />{t("legal.translating")}</div>;
  const body = orig && doc.original_body ? doc.original_body : doc.body;
  return (
    <article data-testid={`legal-doc-${slug}`} className="p-4 text-sm leading-relaxed no-translate">
      {doc.translated && (
        <button data-testid="legal-toggle-orig" onClick={() => setOrig((v) => !v)} className="mb-3 text-xs text-primary flex items-center gap-1">
          <Globe className="w-3.5 h-3.5" /> {t("legal.translated")} · {orig ? t("chat.show_translation") : t("chat.show_original")}
        </button>
      )}
      <ReactMarkdown components={md}>{body}</ReactMarkdown>
      {doc.updated_at && <p className="mt-6 text-[11px] text-muted-foreground">{new Date(doc.updated_at).toLocaleDateString(lang || "ru")}</p>}
    </article>
  );
};
