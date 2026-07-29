import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { MobileShell } from "@/components/lovreski/Shell";
import { Crown, Coins, Check, X, Clock } from "lucide-react";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";

export default function PremiumPage() {
  const { user, refresh } = useAuth();
  const [packages, setPackages] = useState([]);
  const [sbpPhone, setSbpPhone] = useState("");
  const [phone, setPhone] = useState("");
  const [txs, setTxs] = useState([]);
  const [selected, setSelected] = useState(null);
  const nav = useNavigate();

  const load = async () => {
    const [pkg, t] = await Promise.all([api.get("/coins/packages"), api.get("/coins/transactions")]);
    setPackages(pkg.data.packages); setSbpPhone(pkg.data.sbp_phone); setTxs(t.data);
  };
  useEffect(() => { load(); }, []);

  const buy = async () => {
    if (!selected || !phone) return toast.error("Укажите телефон и пакет");
    try {
      await api.post("/coins/purchase", { package_id: selected.id, phone });
      toast.success("Запрос отправлен! Ожидайте подтверждение администратора.");
      setSelected(null); setPhone(""); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Ошибка"); }
  };

  return (
    <MobileShell>
      <header className="sticky top-0 z-40 bg-background/85 backdrop-blur-xl px-4 pt-4 pb-3 border-b border-border/50 flex items-center gap-2">
        <button onClick={() => nav(-1)} className="text-sm text-muted-foreground">← Назад</button>
        <h1 className="font-display font-black text-xl flex items-center gap-2"><Crown className="w-6 h-6 text-accent" /> Premium & Монеты</h1>
      </header>

      <div className="p-4 space-y-4">
        <div className="p-5 rounded-2xl bg-gradient-to-br from-primary via-primary to-rose-700 text-primary-foreground relative overflow-hidden grain">
          <p className="text-xs uppercase tracking-widest opacity-80">Ваш баланс</p>
          <p className="font-display font-black text-4xl mt-1">{user?.coins || 0} 💰</p>
          <p className="text-sm mt-2 opacity-90">{user?.is_premium ? "✨ Premium активен" : "Активируйте Premium для всех функций"}</p>
        </div>

        <div className="grid grid-cols-2 gap-3">
          {packages.map((p) => (
            <button
              key={p.id}
              data-testid={`pkg-${p.id}`}
              onClick={() => setSelected(p)}
              className={`p-4 rounded-2xl text-left border-2 transition-all duration-200 ${selected?.id === p.id ? "border-primary bg-primary/5 scale-[1.02]" : "border-border bg-card hover:border-primary/50"}`}
            >
              <div className="flex items-baseline gap-1">
                <span className="font-display font-black text-2xl">{p.coins}</span>
                <Coins className="w-4 h-4 text-accent" />
              </div>
              <p className="text-lg font-bold text-primary mt-1">{p.price} ₽</p>
              <p className="text-[10px] text-muted-foreground">{(p.price / p.coins).toFixed(0)} ₽/монета</p>
            </button>
          ))}
        </div>

        {selected && (
          <div className="p-4 rounded-2xl bg-card border border-border space-y-3">
            <div className="text-sm">
              <p className="font-semibold">Оплата через СБП (Сбербанк)</p>
              <p className="text-xs text-muted-foreground mt-1">Переведите {selected.price} ₽ на номер:</p>
              <p className="font-display font-black text-lg text-primary mt-1">{sbpPhone}</p>
            </div>
            <input
              data-testid="input-phone"
              placeholder="Ваш номер (СБП)"
              value={phone} onChange={(e) => setPhone(e.target.value)}
              className="w-full px-3 py-2 rounded-xl bg-muted outline-none"
            />
            <button data-testid="btn-buy" onClick={buy} className="w-full btn-pill bg-primary text-primary-foreground">Отправить запрос</button>
            <p className="text-[11px] text-muted-foreground">После подтверждения администратором монеты и Premium активируются автоматически.</p>
          </div>
        )}

        <div>
          <h3 className="font-display font-bold mb-2">История</h3>
          <div className="space-y-2">
            {txs.length === 0 && <p className="text-sm text-muted-foreground">Транзакций пока нет</p>}
            {txs.map((t) => (
              <div key={t.tx_id} data-testid={`tx-${t.tx_id}`} className="p-3 rounded-xl bg-card border border-border flex items-center justify-between">
                <div>
                  <p className="font-semibold text-sm">{t.coins} монет · {t.amount_rub} ₽</p>
                  <p className="text-[11px] text-muted-foreground">{new Date(t.created_at).toLocaleString("ru")}</p>
                </div>
                <span className={`text-xs font-bold px-2 py-1 rounded-full flex items-center gap-1 ${t.status === "approved" ? "bg-emerald-500/15 text-emerald-500" : t.status === "rejected" ? "bg-rose-500/15 text-rose-500" : "bg-amber-500/15 text-amber-500"}`}>
                  {t.status === "approved" ? <Check className="w-3 h-3" /> : t.status === "rejected" ? <X className="w-3 h-3" /> : <Clock className="w-3 h-3" />}
                  {t.status === "approved" ? "Одобрено" : t.status === "rejected" ? "Отклонено" : "Ожидание"}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </MobileShell>
  );
}
