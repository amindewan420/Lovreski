import { useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { toast } from "sonner";
import { Check, X, Clock, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

const STATUS = {
  verified: { label: "apps.status.verified", cls: "bg-emerald-500/15 text-emerald-500", Icon: Check },
  rejected: { label: "apps.status.rejected", cls: "bg-rose-500/15 text-rose-500", Icon: X },
  pending: { label: "apps.status.pending", cls: "bg-amber-500/15 text-amber-500", Icon: Clock },
};

const Overlay = ({ children, onClose, testid }) => (
  <motion.div data-testid={testid} className="fixed inset-0 z-[80] flex items-end sm:items-center justify-center bg-black/60 p-0 sm:p-4"
    initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
    <motion.div onClick={(e) => e.stopPropagation()} initial={{ y: 60 }} animate={{ y: 0 }} exit={{ y: 60 }} transition={{ type: "spring", damping: 26 }}
      className="w-full sm:max-w-sm bg-card rounded-t-3xl sm:rounded-3xl p-5 pb-[max(1.25rem,env(safe-area-inset-bottom))]">
      {children}
    </motion.div>
  </motion.div>
);

const AppCard = ({ s, onLongPress }) => {
  const { t } = useI18n();
  const timer = useRef(null);
  const st = STATUS[s.status] || STATUS.pending;
  const start = () => { clearTimeout(timer.current); timer.current = setTimeout(() => { navigator.vibrate?.(20); onLongPress(s); }, 550); };
  const cancel = () => clearTimeout(timer.current);
  return (
    <motion.div layout initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, x: -60, height: 0, marginTop: 0, paddingTop: 0, paddingBottom: 0 }}
      transition={{ duration: 0.25 }} data-testid={`sub-${s.submission_id}`}
      onTouchStart={start} onTouchEnd={cancel} onTouchMove={cancel} onTouchCancel={cancel}
      onMouseDown={start} onMouseUp={cancel} onMouseLeave={cancel}
      onContextMenu={(e) => { e.preventDefault(); onLongPress(s); }}
      className="p-3 rounded-xl bg-card border border-border flex items-center justify-between select-none overflow-hidden active:scale-[0.99] transition-transform"
      style={{ WebkitTouchCallout: "none" }}>
      <div>
        <p className="text-xs text-muted-foreground">{new Date(s.created_at).toLocaleString("ru")}</p>
        {s.message && <p className="text-xs mt-1">{s.message}</p>}
        {s.status === "rejected" && s.reject_reason && <p className="text-[11px] text-rose-500 mt-1">{t("apps.reason")} {s.reject_reason}</p>}
      </div>
      <span className={`text-xs font-bold px-2 py-1 rounded-full flex items-center gap-1 shrink-0 ${st.cls}`}>
        <st.Icon className="w-3 h-3" /> {t(st.label)}
      </span>
    </motion.div>
  );
};

// "Мои заявки" — long-press a card → Delete → confirm → hidden for this user only (soft delete).
export const MyApplications = ({ items, onRemoved }) => {
  const { t } = useI18n();
  const [menu, setMenu] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [busy, setBusy] = useState(false);
  const remove = async () => {
    setBusy(true);
    try {
      await api.patch(`/support/my/${confirm.submission_id}/hide`);
      onRemoved(confirm.submission_id);
      toast.success(t("apps.toast.removed"));
      setConfirm(null);
    } catch (e) {
      toast.error(e.response?.data?.detail || t("apps.toast.remove_failed"));
    } finally { setBusy(false); }
  };
  if (!items.length) return null;
  return (
    <div>
      <h4 className="font-display font-bold text-sm mb-1">{t("apps.title")}</h4>
      <p className="text-[11px] text-muted-foreground mb-2">{t("apps.hint")}</p>
      <div className="space-y-2">
        <AnimatePresence initial={false}>
          {items.map((s) => <AppCard key={s.submission_id} s={s} onLongPress={setMenu} />)}
        </AnimatePresence>
      </div>
      <AnimatePresence>
        {menu && (
          <Overlay testid="app-action-sheet" onClose={() => setMenu(null)}>
            <button data-testid="app-delete-option" onClick={() => { setConfirm(menu); setMenu(null); }}
              className="w-full py-3 rounded-2xl bg-red-500/10 text-red-600 font-semibold flex items-center justify-center gap-2">
              <Trash2 className="w-4 h-4" /> {t("apps.delete")}
            </button>
            <button data-testid="app-action-cancel" onClick={() => setMenu(null)} className="w-full py-2.5 mt-2 text-sm text-muted-foreground">{t("apps.cancel")}</button>
          </Overlay>
        )}
        {confirm && (
          <Overlay testid="app-delete-confirm" onClose={() => !busy && setConfirm(null)}>
            <p className="font-display font-bold text-center">{t("apps.confirm_title")}</p>
            <p className="text-xs text-muted-foreground text-center mt-1">{t("apps.confirm_body")}</p>
            <div className="grid grid-cols-2 gap-2 mt-5">
              <button data-testid="app-delete-cancel" disabled={busy} onClick={() => setConfirm(null)} className="py-3 rounded-full bg-muted font-semibold text-sm">{t("apps.cancel")}</button>
              <button data-testid="app-delete-confirm-btn" disabled={busy} onClick={remove} className="py-3 rounded-full bg-red-500 text-white font-semibold text-sm disabled:opacity-60">{busy ? "..." : t("apps.delete")}</button>
            </div>
          </Overlay>
        )}
      </AnimatePresence>
    </div>
  );
};
