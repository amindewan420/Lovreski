import { useEffect, useState } from "react";
import { Copy, Reply, Trash2, CheckSquare, X } from "lucide-react";
import { toast } from "sonner";

export async function copyText(text, t) {
  try {
    if (navigator.clipboard?.writeText && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
    } else {
      const ta = Object.assign(document.createElement("textarea"), { value: text });
      ta.setAttribute("readonly", ""); ta.style.position = "fixed"; ta.style.opacity = "0";
      document.body.appendChild(ta); ta.select(); ta.setSelectionRange(0, text.length);
      const ok = document.execCommand("copy"); ta.remove();
      if (!ok) throw new Error("copy failed");
    }
    toast.success(t("chat.copied"));
  } catch {
    toast.error(t("chat.copy_failed"));
  }
}

const fmtN = (str, n) => (str.includes("{n}") ? str.replace("{n}", n) : `${str} (${n})`);

export const canDeleteForEveryone = (m, uid) => {
  if (!m || m.from_user !== uid || m.deleted) return false;
  return (Date.now() - new Date(m.created_at).getTime()) / 1000 <= 3600;
};

// Ignores taps for the first 400ms so the finger-lift after a long-press can't hit a button.
const Sheet = ({ testid, onClose, children }) => {
  const [armed, setArmed] = useState(false);
  useEffect(() => { const t = setTimeout(() => setArmed(true), 400); return () => clearTimeout(t); }, []);
  return (
    <div className={`fixed inset-0 z-[80] flex items-end sm:items-center sm:justify-center px-4 ${armed ? "" : "pointer-events-none"}`} data-testid={testid}>
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative bg-white rounded-t-3xl sm:rounded-3xl w-full sm:max-w-xs p-5 pb-[max(1.25rem,env(safe-area-inset-bottom))]" style={{ animation: "msgSheetIn 220ms cubic-bezier(0.2,0.9,0.3,1)" }}>
        <div className="mx-auto w-10 h-1 rounded-full bg-slate-200 mb-3 sm:hidden" />
        {children}
      </div>
    </div>
  );
};

const Row = ({ testid, onClick, icon: Icon, children, danger }) => (
  <button data-testid={testid} onClick={onClick}
    className={`w-full py-3 rounded-2xl font-semibold text-sm mb-2 flex items-center justify-center gap-2 ${danger ? "bg-red-500 text-white" : "bg-slate-100 text-slate-800"}`}>
    <Icon className="w-4 h-4" /> {children}
  </button>
);

// Long-press menu: [Copy] [Reply] [Select] [Delete for me] [Delete for everyone]
export const MessageActionSheet = ({ m, uid, t, copyValue, onClose, onReply, onSelect, onDelete }) => {
  if (!m) return null;
  const isText = (m.kind === "text" || m.kind === "emoji") && !m.deleted && !m.locked && !!m.text;
  return (
    <Sheet testid="action-sheet" onClose={onClose}>
      <div className="grid grid-cols-3 gap-2 mb-3">
        {isText && (
          <button data-testid="action-copy-btn" onClick={() => { onClose(); copyText(copyValue, t); }} className="flex flex-col items-center gap-1 py-3 rounded-2xl bg-sky-50 text-sky-700 text-xs font-semibold"><Copy className="w-5 h-5" />{t("chat.copy")}</button>
        )}
        {!m.deleted && (
          <button data-testid="action-reply-btn" onClick={() => { onClose(); onReply(m); }} className="flex flex-col items-center gap-1 py-3 rounded-2xl bg-primary/10 text-primary text-xs font-semibold"><Reply className="w-5 h-5" />{t("chat.reply")}</button>
        )}
        <button data-testid="action-select-btn" onClick={() => { onClose(); onSelect(m); }} className="flex flex-col items-center gap-1 py-3 rounded-2xl bg-slate-100 text-slate-700 text-xs font-semibold"><CheckSquare className="w-5 h-5" />{t("chat.select")}</button>
      </div>
      <Row testid="delete-me-btn" icon={Trash2} onClick={() => { onClose(); onDelete([m], "me"); }}>{t("chat.delete_me")}</Row>
      {canDeleteForEveryone(m, uid) && (
        <Row testid="delete-everyone-btn" icon={Trash2} danger onClick={() => { onClose(); onDelete([m], "everyone"); }}>{t("chat.delete_everyone")}</Row>
      )}
      <button data-testid="action-cancel" onClick={onClose} className="w-full py-2 text-sm text-slate-500">{t("chat.cancel")}</button>
    </Sheet>
  );
};

export const SelectionBar = ({ count, t, onCancel, onDelete }) => (
  <div data-testid="selection-bar" className="absolute inset-0 z-40 bg-white flex items-center gap-3 px-3">
    <button data-testid="selection-cancel" onClick={onCancel} className="p-2 -ml-2 rounded-full hover:bg-slate-100 flex items-center gap-1 text-sm text-slate-700">
      <X className="w-5 h-5" /> <span className="hidden min-[360px]:inline">{t("chat.cancel")}</span>
    </button>
    <p data-testid="selection-count" className="flex-1 font-semibold text-slate-900">{fmtN(t("chat.n_selected"), count)}</p>
    <button data-testid="selection-delete" disabled={!count} onClick={onDelete} className="p-2.5 rounded-full bg-red-50 text-red-600 disabled:opacity-30">
      <Trash2 className="w-5 h-5" />
    </button>
  </div>
);

export const BulkDeleteDialog = ({ msgs, uid, t, onClose, onDelete }) => {
  if (!msgs) return null;
  const everyone = msgs.length > 0 && msgs.every((m) => canDeleteForEveryone(m, uid));
  return (
    <Sheet testid="bulk-delete-dialog" onClose={onClose}>
      <p data-testid="bulk-delete-title" className="text-center font-display font-bold text-slate-900 mb-4">{fmtN(t("chat.delete_n_confirm"), msgs.length)}</p>
      <Row testid="bulk-delete-me" icon={Trash2} onClick={() => onDelete(msgs, "me")}>{t("chat.delete_me")}</Row>
      {everyone && <Row testid="bulk-delete-everyone" icon={Trash2} danger onClick={() => onDelete(msgs, "everyone")}>{t("chat.delete_everyone")}</Row>}
      <button data-testid="bulk-delete-cancel" onClick={onClose} className="w-full py-2 text-sm text-slate-500">{t("chat.cancel")}</button>
    </Sheet>
  );
};
