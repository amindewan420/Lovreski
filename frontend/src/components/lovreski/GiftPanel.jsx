import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export default function GiftPanel({ open, onClose, onSend, coins = 0 }) {
  const { t } = useI18n();
  const [gifts, setGifts] = useState([]);
  const [confirming, setConfirming] = useState(null);

  useEffect(() => {
    if (!open) return;
    (async () => {
      try { const { data } = await api.get('/gifts'); setGifts(data || []); }
      catch { /* noop */ }
    })();
  }, [open]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[60] flex items-end" data-testid="gift-sheet">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative w-full max-w-md mx-auto bg-white rounded-t-3xl flex flex-col" style={{ maxHeight: "70vh", height: "70vh" }}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
          <p className="text-sm font-semibold text-slate-700">{t("chat.send_gift")}</p>
          <div className="flex items-center gap-3">
            <span className="text-xs text-slate-500">💰 {coins}</span>
            <button data-testid="gift-close" onClick={onClose} className="p-1 rounded-full hover:bg-slate-100"><X className="w-4 h-4 text-slate-500" /></button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-3">
          <div className="grid grid-cols-3 gap-3">
            {gifts.map((g) => (
              <button key={g.key} data-testid={`gift-${g.key}`} onClick={() => setConfirming(g)}
                className="flex flex-col items-center gap-1.5 p-3 rounded-2xl hover:shadow-md active:scale-95 transition">
                <div className={`w-16 h-16 rounded-2xl bg-gradient-to-br ${g.gradient} flex items-center justify-center shadow-sm`}>
                  <span className="text-3xl">{g.emoji}</span>
                </div>
                <span className="text-[11px] font-medium text-slate-700 leading-tight text-center">{g.name}</span>
                <span className="text-[11px] text-primary font-bold">{g.cost} 💰</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {confirming && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center px-4" data-testid="gift-confirm">
          <div className="absolute inset-0 bg-black/60" onClick={() => setConfirming(null)} />
          <div className="relative bg-white rounded-3xl w-full max-w-xs p-6 text-center">
            <div className={`w-20 h-20 mx-auto rounded-2xl bg-gradient-to-br ${confirming.gradient} flex items-center justify-center mb-3`}>
              <span className="text-4xl">{confirming.emoji}</span>
            </div>
            <p className="font-semibold text-slate-900">{confirming.name}</p>
            <p className="text-xs text-slate-500 mt-1">{t("chat.confirm_gift", { cost: confirming.cost })}</p>
            <div className="flex gap-2 mt-4">
              <button data-testid="gift-cancel" onClick={() => setConfirming(null)} className="flex-1 py-2.5 rounded-full bg-slate-100 text-slate-700 text-sm font-medium">{t("chat.cancel")}</button>
              <button data-testid="gift-confirm-send" onClick={() => { onSend?.(confirming); setConfirming(null); }} className="flex-1 py-2.5 rounded-full bg-primary text-primary-foreground text-sm font-semibold">{t("chat.confirm")}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
