import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { MobileShell } from "@/components/lovreski/Shell";
import { Crown, Coins, Check, X, Clock, Sparkles, Building2 } from "lucide-react";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";

export default function PremiumPage() {
  const { user, refresh } = useAuth();
  const [packages, setPackages] = useState([]);
  const [sbpPhone, setSbpPhone] = useState("");
  const [phone, setPhone] = useState("");
  const [sbpBalance, setSbpBalance] = useState("");
  const [txs, setTxs] = useState([]);
  const [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState(false);
  const [celebrate, setCelebrate] = useState(false);
  const wasPremium = useRef(false);
  const nav = useNavigate();

  const load = async () => {
    const [pkg, t] = await Promise.all([api.get("/coins/packages"), api.get("/coins/transactions")]);
    setPackages(pkg.data.packages); setSbpPhone(pkg.data.sbp_phone); setTxs(t.data);
  };
  useEffect(() => { load(); }, []);

  // Real-time listener via polling: detect isPremium flip and trigger celebration
  useEffect(() => {
    wasPremium.current = !!user?.is_premium;
    const poll = setInterval(async () => {
      try {
        const { data } = await api.get("/coins/balance");
        if (data.is_premium && !wasPremium.current) {
          wasPremium.current = true;
          setCelebrate(true);
          setTimeout(() => setCelebrate(false), 4200);
          toast.success("🎉 Premium активирован!");
        }
        await refresh();
        // Keep tx list fresh so status transitions render instantly
        const tx = await api.get("/coins/transactions");
        setTxs(tx.data);
      } catch { /* ignore */ }
    }, 5000);
    return () => clearInterval(poll);
    // eslint-disable-next-line
  }, []);

  const buy = async () => {
    if (!selected) return toast.error("Выберите пакет");
    if (!phone) return toast.error("Укажите ваш номер СБП");
    setBusy(true);
    try {
      const payload = { package_id: selected.id, phone };
      // If user typed a balance amount, send it so backend can enforce the check
      if (sbpBalance !== "") payload.sbp_balance = parseFloat(sbpBalance);
      await api.post("/coins/purchase", payload);
      toast.success("Запрос отправлен! Администратор обработает платёж.");
      setSelected(null); setPhone(""); setSbpBalance(""); load();
    } catch (e) {
      const status = e.response?.status;
      const detail = e.response?.data?.detail || "Ошибка";
      if (status === 402) toast.error(detail);
      else toast.error(detail);
    } finally { setBusy(false); }
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
          <p data-testid="coin-balance" className="font-display font-black text-4xl mt-1">{user?.coins || 0} 💰</p>
          <p className="text-sm mt-2 opacity-90 flex items-center gap-2">
            {user?.is_premium ? <><Crown className="w-4 h-4" /> Premium активен</> : "Активируйте Premium для всех функций"}
          </p>
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
              {/* Bank badge — ONLY Sberbank ever shown */}
              <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-600 dark:text-emerald-400 font-semibold text-xs">
                <Building2 className="w-3.5 h-3.5" /> Сбербанк · СБП
              </div>
              <p className="text-xs text-muted-foreground mt-3">Переведите {selected.price} ₽ на номер:</p>
              <p data-testid="sbp-phone" className="font-display font-black text-xl text-primary mt-1 tracking-wide">{sbpPhone}</p>
              <p className="text-[10px] text-muted-foreground mt-1">Только Сбербанк принимает платежи. Другие банки — не подходят.</p>
            </div>
            <input
              data-testid="input-phone"
              placeholder="Ваш номер СБП (Сбербанк)"
              value={phone} onChange={(e) => setPhone(e.target.value)}
              className="w-full px-3 py-2 rounded-xl bg-muted outline-none"
            />
            <input
              data-testid="input-sbp-balance"
              placeholder="Баланс на счёте СБП (для проверки, необязательно)"
              type="number" min="0"
              value={sbpBalance} onChange={(e) => setSbpBalance(e.target.value)}
              className="w-full px-3 py-2 rounded-xl bg-muted outline-none"
            />
            <button data-testid="btn-buy" disabled={busy} onClick={buy} className="w-full btn-pill bg-primary text-primary-foreground disabled:opacity-60">
              {busy ? "..." : "Отправить запрос"}
            </button>
            <p className="text-[11px] text-muted-foreground">После подтверждения администратором монеты и Premium активируются автоматически — без перезапуска.</p>
          </div>
        )}

        <div>
          <h3 className="font-display font-bold mb-2">История транзакций</h3>
          <div className="space-y-2">
            {txs.length === 0 && <p className="text-sm text-muted-foreground">Транзакций пока нет</p>}
            {txs.map((t) => (
              <div key={t.tx_id} data-testid={`tx-${t.tx_id}`} className="p-3 rounded-xl bg-card border border-border">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-semibold text-sm">{t.coins} монет · {t.amount_rub} ₽</p>
                    <p className="text-[11px] text-muted-foreground">{new Date(t.created_at).toLocaleString("ru")}</p>
                    <p className="text-[11px] text-muted-foreground">{t.payment_method || "СБП (Сбербанк)"} · {t.phone}</p>
                  </div>
                  <span className={`text-xs font-bold px-2 py-1 rounded-full flex items-center gap-1 ${t.status === "approved" ? "bg-emerald-500/15 text-emerald-500" : t.status === "rejected" ? "bg-rose-500/15 text-rose-500" : "bg-amber-500/15 text-amber-500"}`}>
                    {t.status === "approved" ? <Check className="w-3 h-3" /> : t.status === "rejected" ? <X className="w-3 h-3" /> : <Clock className="w-3 h-3" />}
                    {t.status === "approved" ? "Одобрено" : t.status === "rejected" ? "Отклонено" : "Ожидание"}
                  </span>
                </div>
                {t.status === "rejected" && t.reject_reason && (
                  <p className="mt-2 text-xs text-rose-500 border-l-2 border-rose-500 pl-2">Причина: {t.reject_reason}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Real-time Premium activation celebration */}
      <AnimatePresence>
        {celebrate && (
          <motion.div
            data-testid="premium-celebration"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[80] flex items-center justify-center bg-black/70 backdrop-blur-md pointer-events-none"
          >
            <motion.div
              initial={{ scale: 0.5, rotate: -20 }}
              animate={{ scale: 1, rotate: 0 }}
              transition={{ type: "spring", damping: 12, stiffness: 200 }}
              className="text-center p-8 rounded-3xl bg-gradient-to-br from-accent via-amber-400 to-primary text-white shadow-2xl"
            >
              <motion.div
                animate={{ y: [-5, 5, -5] }}
                transition={{ duration: 2, repeat: Infinity }}
              >
                <Crown className="w-20 h-20 mx-auto mb-3" />
              </motion.div>
              <h2 className="font-display font-black text-3xl">🎉 Premium активирован!</h2>
              <p className="mt-2 opacity-95">Все функции разблокированы</p>
              <div className="flex justify-center gap-1 mt-3">
                {[...Array(5)].map((_, i) => (
                  <motion.div
                    key={i}
                    initial={{ y: -20, opacity: 0 }}
                    animate={{ y: [0, -30, 0], opacity: [1, 1, 0] }}
                    transition={{ duration: 1.5, delay: i * 0.15, repeat: Infinity }}
                  >
                    <Sparkles className="w-5 h-5" />
                  </motion.div>
                ))}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </MobileShell>
  );
}
