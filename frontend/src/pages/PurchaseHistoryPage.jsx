import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { MobileShell } from "@/components/lovreski/Shell";
import { useNavigate } from "react-router-dom";
import { Check, Clock, X, Coins } from "lucide-react";

export default function PurchaseHistoryPage() {
  const [txs, setTxs] = useState([]);
  const [loading, setLoading] = useState(true);
  const nav = useNavigate();

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get("/coins/transactions");
        setTxs(data);
      } finally { setLoading(false); }
    })();
  }, []);

  const totalCoins = txs.filter((t) => t.status === "success").reduce((s, t) => s + (t.coins || 0), 0);
  const totalSpent = txs.filter((t) => t.status === "success").reduce((s, t) => s + (t.amount_rub || 0), 0);

  return (
    <MobileShell>
      <header className="sticky top-0 z-40 bg-background/85 backdrop-blur-xl px-4 pt-4 pb-3 border-b border-border/50 flex items-center gap-2">
        <button onClick={() => nav(-1)} className="text-sm text-muted-foreground">← Назад</button>
        <h1 className="font-display font-black text-xl">История покупок</h1>
      </header>

      <div className="p-4 space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div className="p-4 rounded-2xl bg-gradient-to-br from-accent/15 to-primary/10 border border-accent/30">
            <p className="text-[10px] uppercase tracking-widest text-muted-foreground">Всего куплено</p>
            <p className="font-display font-black text-2xl mt-1 flex items-center gap-1">{totalCoins} <span className="text-lg">🪙</span></p>
          </div>
          <div className="p-4 rounded-2xl bg-card border border-border">
            <p className="text-[10px] uppercase tracking-widest text-muted-foreground">Всего потрачено</p>
            <p className="font-display font-black text-2xl mt-1">{totalSpent.toLocaleString("ru")} ₽</p>
          </div>
        </div>

        {loading ? (
          [...Array(3)].map((_, i) => <div key={i} className="h-16 bg-muted animate-pulse rounded-xl" />)
        ) : txs.length === 0 ? (
          <div className="text-center py-16">
            <Coins className="w-12 h-12 text-muted-foreground mx-auto mb-3" />
            <p className="text-muted-foreground">Покупок пока нет</p>
            <button onClick={() => nav("/premium")} className="mt-4 btn-pill bg-primary text-primary-foreground">Купить монеты</button>
          </div>
        ) : (
          <div className="space-y-2">
            {txs.map((t) => (
              <div key={t.tx_id} data-testid={`tx-${t.tx_id}`} className="p-4 rounded-2xl bg-card border border-border">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-bold text-lg flex items-center gap-1">+{t.coins} 🪙</p>
                    <p className="text-sm text-muted-foreground">{t.amount_rub?.toLocaleString("ru")} ₽</p>
                    <p className="text-[11px] text-muted-foreground mt-1">{new Date(t.created_at).toLocaleString("ru")}</p>
                    {t.bank && <p className="text-[11px] text-muted-foreground">Оплачено через {t.bank}</p>}
                  </div>
                  <span className={`text-xs font-bold px-3 py-1 rounded-full flex items-center gap-1 ${t.status === "success" || t.status === "approved" ? "bg-emerald-500/15 text-emerald-500" : t.status === "failed" || t.status === "rejected" ? "bg-rose-500/15 text-rose-500" : "bg-amber-500/15 text-amber-500"}`}>
                    {t.status === "success" || t.status === "approved" ? <Check className="w-3 h-3" /> : t.status === "failed" || t.status === "rejected" ? <X className="w-3 h-3" /> : <Clock className="w-3 h-3" />}
                    {t.status === "success" || t.status === "approved" ? "Успешно" : t.status === "failed" || t.status === "rejected" ? "Ошибка" : "Ожидание"}
                  </span>
                </div>
                {(t.status === "failed" || t.status === "rejected") && (t.reject_reason || t.fail_reason) && (
                  <p className="mt-2 text-xs text-rose-500 border-l-2 border-rose-500 pl-2">{t.reject_reason || t.fail_reason}</p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </MobileShell>
  );
}
