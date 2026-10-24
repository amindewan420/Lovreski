import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Loader2, AlertTriangle } from "lucide-react";
import { api } from "@/lib/api";

// Live list of legal docs (admin custom versions override built-ins).
export function useLegalDocs() {
  const [docs, setDocs] = useState([]);
  const [error, setError] = useState(false);
  useEffect(() => {
    api.get("/legal", { params: { t: Date.now() } }).then((r) => setDocs(r.data || [])).catch(() => setError(true));
  }, []);
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

export const LegalDocView = ({ slug, onLoaded }) => {
  const [doc, setDoc] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    setDoc(null); setError("");
    api.get(`/legal/${slug}`, { params: { t: Date.now() } })
      .then((r) => { setDoc(r.data); onLoaded?.(r.data); })
      .catch((e) => setError(e.response?.status === 404 ? "Документ не найден" : "Не удалось загрузить документ"));
    // eslint-disable-next-line
  }, [slug]);
  if (error) return <div data-testid="legal-error" className="p-8 flex flex-col items-center gap-2 text-muted-foreground"><AlertTriangle className="w-6 h-6" />{error}</div>;
  if (!doc) return <div data-testid="legal-loading" className="p-10 flex justify-center"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>;
  return (
    <article data-testid={`legal-doc-${slug}`} className="p-4 text-sm leading-relaxed">
      <ReactMarkdown components={md}>{doc.body}</ReactMarkdown>
      {doc.updated_at && <p className="mt-6 text-[11px] text-muted-foreground">Обновлено: {new Date(doc.updated_at).toLocaleDateString("ru")}</p>}
    </article>
  );
};
