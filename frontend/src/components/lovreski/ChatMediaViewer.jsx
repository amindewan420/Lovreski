import { useEffect, useState } from "react";
import { TransformWrapper, TransformComponent } from "react-zoom-pan-pinch";
import { toast } from "sonner";
import { X, Download, Loader2, AlertTriangle, ZoomIn, ZoomOut, FileText } from "lucide-react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { PdfPages } from "@/components/lovreski/PdfPages";

const isMobile = () => /Android|iPhone|iPad|iPod/i.test(navigator.userAgent) || (navigator.maxTouchPoints > 1 && /Macintosh/.test(navigator.userAgent));

export const isPdfMsg = (m) => m.kind === "file" && /\.pdf$/i.test(m.file_name || m.media_url?.split("?")[0] || "");

const nameFor = (m, blob) => {
  if (m.file_name) return m.file_name;
  const ext = (blob?.type || "").split("/")[1]?.replace("jpeg", "jpg") || "jpg";
  return `lovreski_${m.message_id}.${ext}`;
};

// Bytes come through the same-origin API proxy (works for S3 + legacy files).
export async function fetchChatMedia(m, onProgress) {
  const { data } = await api.get(`/chat/media-file/${m.message_id}`, {
    responseType: "blob",
    onDownloadProgress: (e) => e.total && onProgress?.(Math.round((e.loaded / e.total) * 100)),
  });
  if (!data || data.size === 0) throw new Error("empty");
  return data;
}

const anchorSave = (blob, name) => {
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
};

// Images on phones → system share sheet ("Save Image" / "Save to Photos"); otherwise a normal download.
export async function saveChatMedia(m, blob, t) {
  const name = nameFor(m, blob);
  const isImage = (blob.type || "").startsWith("image/");
  if (isImage && isMobile() && navigator.canShare) {
    const file = new File([blob], name, { type: blob.type });
    if (navigator.canShare({ files: [file] })) {
      try {
        await navigator.share({ files: [file] });
        toast.success(t("media.saved_gallery"));
        return;
      } catch (e) {
        if (e?.name === "AbortError") return;
      }
    }
  }
  anchorSave(blob, name);
  toast.success(isImage ? t("media.saved_downloads_img") : t("media.saved_downloads_pdf"));
}

export async function downloadChatMedia(m, t) {
  const id = toast.loading(t("media.downloading"));
  try {
    const blob = await fetchChatMedia(m);
    toast.dismiss(id);
    await saveChatMedia(m, blob, t);
  } catch {
    toast.error(t("media.download_failed"), { id });
  }
}

const ImageZoom = ({ url, onError }) => (
  <TransformWrapper minScale={1} maxScale={6} doubleClick={{ mode: "toggle", step: 2.5 }} centerOnInit wheel={{ step: 0.2 }}>
    {({ zoomIn, zoomOut }) => (
      <>
        <TransformComponent wrapperClass="!w-full !h-full" contentClass="!w-full !h-full flex items-center justify-center">
          <img data-testid="media-viewer-img" src={url} alt="" onError={onError} className="max-w-full max-h-full object-contain select-none" draggable={false} />
        </TransformComponent>
        <div className="absolute bottom-6 left-1/2 -translate-x-1/2 flex gap-2 z-10">
          <button data-testid="media-zoom-out" onClick={() => zoomOut()} className="w-10 h-10 rounded-full bg-white/15 text-white flex items-center justify-center"><ZoomOut className="w-5 h-5" /></button>
          <button data-testid="media-zoom-in" onClick={() => zoomIn()} className="w-10 h-10 rounded-full bg-white/15 text-white flex items-center justify-center"><ZoomIn className="w-5 h-5" /></button>
        </div>
      </>
    )}
  </TransformWrapper>
);

export const ChatMediaViewer = ({ m, onClose }) => {
  const { t } = useI18n();
  const [st, setSt] = useState({ loading: true, progress: 0, blob: null, url: "", error: false });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!m) return;
    let alive = true; let objUrl = "";
    setSt({ loading: true, progress: 0, blob: null, url: "", error: false });
    fetchChatMedia(m, (p) => alive && setSt((s) => ({ ...s, progress: p })))
      .then((blob) => { if (!alive) return; objUrl = URL.createObjectURL(blob); setSt({ loading: false, progress: 100, blob, url: objUrl, error: false }); })
      .catch(() => alive && setSt({ loading: false, progress: 0, blob: null, url: "", error: true }));
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => { alive = false; window.removeEventListener("keydown", onKey); if (objUrl) URL.revokeObjectURL(objUrl); };
  }, [m, onClose]);

  if (!m) return null;
  const pdf = isPdfMsg(m) || st.blob?.type === "application/pdf";
  const save = async () => {
    if (!st.blob) return;
    setSaving(true);
    try { await saveChatMedia(m, st.blob, t); } catch { toast.error(t("media.download_failed")); } finally { setSaving(false); }
  };

  return (
    <div data-testid="media-viewer" className="fixed inset-0 z-[100] bg-black flex flex-col">
      <div className="flex items-center gap-2 px-3 py-3 text-white" style={{ paddingTop: "max(0.75rem, env(safe-area-inset-top))" }}>
        {pdf && <FileText className="w-5 h-5 opacity-70" />}
        <p className="text-sm font-semibold truncate mr-auto no-translate">{pdf ? m.file_name || "PDF" : ""}</p>
        <button data-testid="media-viewer-download" disabled={!st.blob || saving} onClick={save}
          className="h-9 px-4 rounded-full bg-white/15 text-sm font-semibold flex items-center gap-1.5 disabled:opacity-40">
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />} {t("media.download")}
        </button>
        <button data-testid="media-viewer-close" onClick={onClose} className="w-9 h-9 rounded-full bg-white/20 flex items-center justify-center"><X className="w-5 h-5" /></button>
      </div>
      <div className="relative flex-1 min-h-0 flex items-center justify-center overflow-hidden">
        {st.loading ? (
          <div data-testid="media-viewer-loading" className="flex flex-col items-center gap-3 text-white/80">
            <Loader2 className="w-8 h-8 animate-spin" />
            <p className="text-sm">{t("media.loading")}{st.progress ? ` · ${st.progress}%` : ""}</p>
          </div>
        ) : st.error ? (
          <div data-testid="media-viewer-error" className="flex flex-col items-center gap-3 text-white text-center px-6">
            <AlertTriangle className="w-10 h-10 text-amber-400" />
            <p className="font-semibold">{t("media.load_failed")}</p>
            <button onClick={() => downloadChatMedia(m, t)} className="px-4 py-2 rounded-full bg-white/15 text-sm">{t("media.try_download")}</button>
          </div>
        ) : pdf ? (
          <PdfPages blob={st.blob} onError={() => setSt((s) => ({ ...s, error: true }))} />
        ) : (
          <ImageZoom url={st.url} onError={() => setSt((s) => ({ ...s, error: true }))} />
        )}
      </div>
    </div>
  );
};
