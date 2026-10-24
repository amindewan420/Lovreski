import { useEffect, useState } from "react";
import { PdfPages } from "@/components/lovreski/PdfPages";
import axios from "axios";
import { toast } from "sonner";
import { X, Download, ExternalLink, Loader2, FileText, AlertTriangle } from "lucide-react";
import { adminApi } from "@/lib/adminApi";
import { API_BASE } from "@/lib/api";


export const receiptKind = (src) => {
  if (!src || typeof src !== "string") return "unknown";
  if (src.startsWith("data:")) return src.startsWith("data:application/pdf") ? "pdf" : "image";
  const path = src.split("?")[0].toLowerCase();
  if (path.endsWith(".pdf")) return "pdf";
  if (/\.(jpe?g|png|webp|gif)$/.test(path)) return "image";
  return "unknown";
};

const fileName = (src, type) => {
  const base = (src.startsWith("data:") ? "receipt" : src.split("?")[0].split("/").pop()) || "receipt";
  return base.includes(".") ? `receipt_${base}` : `${base}.${type === "application/pdf" ? "pdf" : "jpg"}`;
};

// Fetches receipt bytes as a Blob (S3 via same-origin admin proxy; signed /api/files directly).
export async function fetchReceiptBlob(src, onProgress) {
  if (src.startsWith("data:")) return (await fetch(src)).blob();
  const cfg = { responseType: "blob", onDownloadProgress: (e) => e.total && onProgress?.(Math.round((e.loaded / e.total) * 100)) };
  if (src.startsWith("/api/")) return (await axios.get(API_BASE.replace(/\/api$/, "") + src, cfg)).data;
  return (await adminApi.get("/admin/receipt-file", { ...cfg, params: { src } })).data;
}

const errorText = async (e) => {
  const st = e?.response?.status;
  if (st === 404) return "File not found";
  try { const d = JSON.parse(await e.response.data.text()); if (d?.detail) return d.detail; } catch { /* noop */ }
  return "Unable to load receipt";
};

const saveBlob = (blob, name) => {
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
};

export async function downloadReceipt(src) {
  const id = toast.loading("Скачивание чека...");
  try {
    const blob = await fetchReceiptBlob(src);
    saveBlob(blob, fileName(src, blob.type));
    toast.success("Чек скачан", { id });
  } catch (e) {
    toast.error(await errorText(e), { id });
  }
}

export const ReceiptViewer = ({ src, onClose }) => {
  const [state, setState] = useState({ loading: true, progress: 0, error: "", blob: null, url: "" });
  useEffect(() => {
    if (!src) return;
    let alive = true; let objUrl = "";
    setState({ loading: true, progress: 0, error: "", blob: null, url: "" });
    fetchReceiptBlob(src, (p) => alive && setState((s) => ({ ...s, progress: p })))
      .then((blob) => {
        if (!alive) return;
        if (!blob || blob.size === 0) throw Object.assign(new Error("empty"), { response: { status: 404 } });
        objUrl = URL.createObjectURL(blob);
        setState({ loading: false, progress: 100, error: "", blob, url: objUrl });
      })
      .catch(async (e) => alive && setState({ loading: false, progress: 0, error: await errorText(e), blob: null, url: "" }));
    return () => { alive = false; if (objUrl) URL.revokeObjectURL(objUrl); };
  }, [src]);

  if (!src) return null;
  const isPdf = state.blob ? state.blob.type === "application/pdf" || receiptKind(src) === "pdf" : receiptKind(src) === "pdf";
  const fail = (msg = "Unable to load receipt") => setState((s) => ({ ...s, error: msg }));

  return (
    <div data-testid="receipt-viewer" className="fixed inset-0 z-[95] bg-black flex flex-col">
      <div className="flex items-center gap-2 px-3 sm:px-5 py-3 border-b border-white/10 text-white">
        <FileText className="w-5 h-5 opacity-70" />
        <p className="text-sm font-semibold mr-auto">{isPdf ? "PDF чек" : "Чек"}</p>
        {state.url && (
          <>
            <button data-testid="receipt-open-tab" onClick={() => window.open(state.url, "_blank", "noopener")} className="px-3 py-1.5 rounded-full bg-white/15 text-xs font-semibold flex items-center gap-1"><ExternalLink className="w-3.5 h-3.5" /><span className="hidden sm:inline">Новая вкладка</span></button>
            <button data-testid="receipt-download" onClick={() => saveBlob(state.blob, fileName(src, state.blob.type))} className="px-3 py-1.5 rounded-full bg-white/15 text-xs font-semibold flex items-center gap-1"><Download className="w-3.5 h-3.5" /><span className="hidden sm:inline">Скачать</span></button>
          </>
        )}
        <button data-testid="receipt-viewer-close" onClick={onClose} className="w-9 h-9 rounded-full bg-white/20 flex items-center justify-center"><X className="w-5 h-5" /></button>
      </div>
      <div className="flex-1 min-h-0 flex items-center justify-center">
        {state.loading ? (
          <div data-testid="receipt-loading" className="flex flex-col items-center gap-3 text-white/80">
            <Loader2 className="w-8 h-8 animate-spin" />
            <p className="text-sm">Загрузка чека{state.progress ? ` · ${state.progress}%` : "..."}</p>
          </div>
        ) : state.error ? (
          <div data-testid="receipt-error" className="flex flex-col items-center gap-3 text-center px-6 text-white">
            <AlertTriangle className="w-10 h-10 text-amber-400" />
            <p className="font-semibold">{state.error}</p>
            {state.blob && <button onClick={() => saveBlob(state.blob, fileName(src, state.blob.type))} className="px-4 py-2 rounded-full bg-white/15 text-sm">Скачать файл</button>}
            {!state.blob && <button onClick={() => downloadReceipt(src)} className="px-4 py-2 rounded-full bg-white/15 text-sm">Попробовать скачать</button>}
          </div>
        ) : isPdf ? (
          <PdfPages blob={state.blob} onError={() => fail()} />
        ) : (
          <img data-testid="receipt-image" src={state.url} alt="receipt" onError={() => fail()} className="max-w-full max-h-full object-contain p-3" />
        )}
      </div>
    </div>
  );
};

export const ReceiptThumb = ({ src, onOpen, testid }) => {
  const [broken, setBroken] = useState(false);
  const kind = broken ? "unknown" : receiptKind(src);
  if (!src) {
    return (
      <div data-testid={testid ? `${testid}-missing` : undefined} className="w-24 h-24 flex-shrink-0 rounded-xl bg-muted flex flex-col items-center justify-center text-muted-foreground">
        <AlertTriangle className="w-6 h-6" /><span className="text-[10px] font-semibold mt-1 text-center px-1">Файл не приложен</span>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-1.5 flex-shrink-0">
      <button data-testid={testid} onClick={onOpen} className="w-24 h-24 rounded-xl overflow-hidden bg-muted flex items-center justify-center">
        {kind === "image" ? (
          <img src={src} alt="receipt" onError={() => setBroken(true)} className="w-full h-full object-cover" />
        ) : (
          <div className="flex flex-col items-center text-rose-500"><FileText className="w-8 h-8" /><span className="text-[10px] font-bold mt-1">{kind === "pdf" ? "PDF" : "ФАЙЛ"}</span></div>
        )}
      </button>
      <button data-testid={testid ? `${testid}-download` : undefined} onClick={() => downloadReceipt(src)} className="text-[11px] font-semibold text-primary flex items-center justify-center gap-1">
        <Download className="w-3 h-3" /> Скачать
      </button>
    </div>
  );
};
