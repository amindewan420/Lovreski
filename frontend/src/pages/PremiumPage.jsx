import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { MobileShell } from "@/components/lovreski/Shell";
import {
  Coins, Sparkles, Crown, Building2, Check, Clock, X, Copy, ExternalLink,
  ShieldCheck, AlertTriangle, Phone, User,
} from "lucide-react";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import confetti from "canvas-confetti";

export default function PremiumPage() {
  const { user, refresh } = useAuth();
  const nav = useNavigate();
  const [packages, setPackages] = useState([]);
  const [sbpPhone, setSbpPhone] = useState("");
  const [recipientName, setRecipientName] = useState("");
  const [banks, setBanks] = useState([]);
  const [selectedBank, setSelectedBank] = useState("sberbank");
  const [checkout, setCheckout] = useState(null);
  const [status, setStatus] = useState("pending");
  const [busy, setBusy] = useState(false);
  const [success, setSuccess] = useState(null);
  const pollTimer = useRef(null);

  const load = async () => {
    const { data } = await api.get("/coins/packages");
    setPackages(data.packages);
    setSbpPhone(data.sbp_phone || "");
    setRecipientName(data.recipient_name || "");
    setBanks(data.banks || []);
  };
  useEffect(() => { load(); }, []);
  useEffect(() => () => { if (pollTimer.current) clearInterval(pollTimer.current); }, []);

  const copyPhone = async () => {
    try {
      await navigator.clipboard.writeText(sbpPhone);
      toast.success("Номер скопирован ✓");
    } catch { toast.error("Не удалось скопировать"); }
  };

  const startCheckout = async (pkg) => {
    setBusy(true);
    try {
      const { data } = await api.post("/coins/checkout", { package_id: pkg.id, bank: selectedBank });
      setCheckout(data); setStatus("pending");
      pollTimer.current = setInterval(async () => {
        try {
          const r = await api.get(`/coins/status/${data.tx_id}`);
          const tx = r.data.transaction;
          if (tx.status === "success") {
            clearInterval(pollTimer.current); pollTimer.current = null;
            setStatus("success");
            setSuccess({ coinsAdded: tx.coins, newBalance: r.data.coins, bank: tx.bank });
            setCheckout(null);
            await refresh();
            confetti({ particleCount: 120, spread: 90, origin: { y: 0.6 } });
            setTimeout(() => confetti({ particleCount: 80, spread: 100, angle: 60, origin: { x: 0 } }), 250);
            setTimeout(() => confetti({ particleCount: 80, spread: 100, angle: 120, origin: { x: 1 } }), 400);
          } else if (tx.status === "failed") {
            clearInterval(pollTimer.current); pollTimer.current = null;
            setStatus("failed");
            toast.error("❌ Insufficient balance! Please top up your bank account and try again.");
          }
        } catch { /* keep polling */ }
      }, 3000);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Ошибка");
    } finally { setBusy(false); }
  };

  const closeCheckout = () => {
    if (pollTimer.current) { clearInterval(pollTimer.current); pollTimer.current = null; }
    setCheckout(null); setStatus("pending");
  };

  const copyLink = async () => {
    if (!checkout?.sbp_link) return;
    await navigator.clipboard.writeText(checkout.sbp_link);
    toast.success("Ссылка скопирована");
  };

  return (
    <MobileShell>
      <header className="sticky top-0 z-40 bg-background/85 backdrop-blur-xl px-4 pt-4 pb-3 border-b border-border/50 flex items-center gap-2">
        <button onClick={() => nav(-1)} className="text-sm text-muted-foreground">← Назад</button>
        <h1 className="font-display font-black text-xl flex items-center gap-2"><Crown className="w-6 h-6 text-accent" /> Premium & Монеты</h1>
      </header>

      <div className="p-4 space-y-5">
        {/* Live balance card */}
        <div className="p-5 rounded-2xl bg-gradient-to-br from-primary via-primary to-rose-700 text-primary-foreground relative overflow-hidden grain">
          <p className="text-xs uppercase tracking-widest opacity-80">Ваш баланс</p>
          <p data-testid="coin-balance" className="font-display font-black text-4xl mt-1">{user?.coins || 0} 🪙</p>
          <p className="text-sm mt-2 opacity-90 flex items-center gap-2">
            {user?.is_premium ? <><Crown className="w-4 h-4" /> Premium активен</> : "Активируйте Premium для всех функций"}
          </p>
          <button
            onClick={() => nav("/purchase-history")}
            data-testid="link-purchase-history"
            className="mt-3 text-xs bg-white/15 backdrop-blur px-3 py-1.5 rounded-full font-semibold hover:bg-white/25"
          >
            История покупок →
          </button>
        </div>

        {/* Coin packages */}
        <div>
          <h3 className="font-display font-bold text-lg mb-3">Выберите пакет</h3>
          <div className="grid grid-cols-2 gap-3">
            {packages.map((p) => (
              <button
                key={p.id}
                data-testid={`pkg-${p.id}`}
                disabled={busy}
                onClick={() => startCheckout(p)}
                className={`relative p-5 rounded-2xl text-left border-2 overflow-hidden transition-all duration-200 group ${p.popular ? "border-accent bg-gradient-to-br from-accent/10 to-primary/5 shadow-lg shadow-accent/20" : "border-border bg-card hover:border-primary/60"} disabled:opacity-60 hover:scale-[1.02] active:scale-95`}
              >
                {p.popular && (
                  <div className="absolute -top-2 -right-2 rotate-6 bg-accent text-accent-foreground text-[9px] font-black px-2 py-0.5 rounded-full uppercase tracking-widest shadow-md">
                    Popular
                  </div>
                )}
                <div className="text-4xl">🪙</div>
                <div className="flex items-baseline gap-1 mt-2">
                  <span className="font-display font-black text-3xl">{p.coins}</span>
                  <span className="text-xs text-muted-foreground">монет</span>
                </div>
                <p className="text-lg font-bold text-primary mt-1">{p.price.toLocaleString("ru")} ₽</p>
                <p className="text-[10px] text-muted-foreground mt-1">{(p.price / p.coins).toFixed(1)} ₽ / монета</p>
              </button>
            ))}
          </div>
        </div>

        {/* SBP payment phone number — copyable */}
        <div className="p-4 rounded-2xl bg-card border border-border" data-testid="sbp-info-card">
          <p className="text-xs uppercase tracking-widest text-muted-foreground flex items-center gap-1">
            <Phone className="w-3.5 h-3.5" /> Номер СБП для оплаты
          </p>
          <div className="mt-2 flex items-center gap-2">
            <p data-testid="sbp-phone" className="flex-1 font-display font-semibold text-xl tracking-wide select-all">{sbpPhone || "—"}</p>
            <button
              data-testid="btn-copy-phone"
              onClick={copyPhone}
              className="inline-flex items-center gap-1 px-3 py-2 rounded-full bg-primary text-primary-foreground text-xs font-bold hover:opacity-90"
            >
              <Copy className="w-3.5 h-3.5" /> Копировать
            </button>
          </div>
          {recipientName && (
            <div className="mt-3 flex items-center gap-2 text-sm">
              <User className="w-4 h-4 text-primary" />
              <span className="text-muted-foreground">Получатель:</span>
              <span data-testid="sbp-recipient" className="font-semibold">{recipientName}</span>
            </div>
          )}
        </div>

        {/* Bank selector — user's preferred bank */}
        {banks.length > 0 && (
          <div className="p-4 rounded-2xl bg-card border border-border" data-testid="bank-selector">
            <p className="text-xs uppercase tracking-widest text-muted-foreground mb-2 flex items-center gap-1">
              <Building2 className="w-3.5 h-3.5" /> Ваш банк-отправитель
            </p>
            <div className="grid grid-cols-2 gap-2">
              {banks.map((b) => (
                <button
                  key={b.id}
                  data-testid={`bank-${b.id}`}
                  onClick={() => setSelectedBank(b.id)}
                  className={`p-3 rounded-xl border-2 text-sm font-semibold transition-all duration-200 ${selectedBank === b.id ? "border-primary bg-primary/5 text-primary" : "border-border hover:border-primary/50"}`}
                >
                  {selectedBank === b.id && <Check className="w-4 h-4 mr-1 inline" />}
                  {b.name}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Rules Box — yellow/orange border */}
        <div
          data-testid="rules-box"
          className="p-4 rounded-2xl border-2 border-amber-400 bg-amber-50 dark:bg-amber-950/30"
        >
          <p className="font-display font-black text-sm flex items-center gap-1.5 text-amber-700 dark:text-amber-400">
            <AlertTriangle className="w-4 h-4" /> ПРАВИЛА АКТИВАЦИИ PREMIUM
          </p>
          <ol className="mt-3 space-y-2 text-sm text-amber-900 dark:text-amber-100 list-decimal pl-5">
            <li data-testid="rule-1">
              Перед оплатой Premium убедитесь, что <b>имя получателя</b> в вашем банке — <b>"{recipientName || 'Al Amin Dewan'}"</b>.
            </li>
            <li data-testid="rule-2">
              Вы можете выбрать <b>предпочитаемый банк</b> (например, Сбербанк, T-Bank) для оплаты.
            </li>
          </ol>
        </div>
      </div>

      {/* One-click Payment Popup */}
      <AnimatePresence>
        {checkout && (
          <motion.div
            data-testid="pay-modal"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-[70] flex items-end sm:items-center justify-center bg-black/70 backdrop-blur-sm p-0 sm:p-4"
            onClick={closeCheckout}
          >
            <motion.div
              onClick={(e) => e.stopPropagation()}
              initial={{ y: 40, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 40, opacity: 0 }}
              className="w-full sm:max-w-md bg-card border-t sm:border sm:rounded-2xl border-border shadow-2xl p-6 rounded-t-3xl"
            >
              <div className="flex justify-between items-start mb-1">
                <div>
                  <h3 className="font-display font-black text-xl">Оплата {checkout.amount_rub.toLocaleString("ru")} ₽</h3>
                  <p className="text-xs text-muted-foreground">Получите {checkout.coins} монет 🪙 · через {banks.find(b => b.id === selectedBank)?.name}</p>
                </div>
                <button data-testid="pay-close" onClick={closeCheckout} className="p-1 rounded-full hover:bg-muted"><X className="w-5 h-5" /></button>
              </div>

              <div className="mt-4 flex flex-col items-center">
                <div className="p-3 bg-white rounded-2xl shadow-lg border border-border">
                  <img data-testid="pay-qr" src={checkout.qr_png} alt="Отсканируйте QR" className="w-52 h-52" />
                </div>
                <p className="mt-3 text-xs text-center text-muted-foreground max-w-xs">
                  Отсканируйте QR или переведите на <b>{sbpPhone}</b> ({recipientName}) вручную через ваш банк
                </p>
              </div>

              <div className="mt-4 grid grid-cols-2 gap-2">
                <a
                  data-testid="pay-open-bank"
                  href={checkout.sbp_link}
                  target="_blank" rel="noopener noreferrer"
                  className="btn-pill bg-primary text-primary-foreground text-sm !py-2.5"
                >
                  <ExternalLink className="w-4 h-4 mr-1" /> Открыть в банке
                </a>
                <button
                  data-testid="pay-copy-link"
                  onClick={copyLink}
                  className="btn-pill bg-muted text-foreground text-sm !py-2.5"
                >
                  <Copy className="w-4 h-4 mr-1" /> Копировать
                </button>
              </div>

              <div className="mt-5 p-3 rounded-xl bg-muted flex items-center gap-3">
                {status === "pending" && (
                  <>
                    <div className="relative">
                      <div className="w-3 h-3 rounded-full bg-amber-500 animate-pulse" />
                      <div className="absolute inset-0 w-3 h-3 rounded-full bg-amber-500 animate-ping" />
                    </div>
                    <div className="flex-1">
                      <p data-testid="pay-status" className="text-sm font-semibold">Ожидание оплаты...</p>
                      <p className="text-[11px] text-muted-foreground">Проверяем каждые 3 сек.</p>
                    </div>
                  </>
                )}
                {status === "failed" && (
                  <>
                    <X className="w-5 h-5 text-rose-500" />
                    <div className="flex-1">
                      <p data-testid="pay-status" className="text-sm font-semibold text-rose-500">Платёж не прошёл</p>
                      <p className="text-[11px] text-muted-foreground">Проверьте баланс и попробуйте снова.</p>
                    </div>
                  </>
                )}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Success screen with confetti */}
      <AnimatePresence>
        {success && (
          <motion.div
            data-testid="pay-success"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-[80] flex items-center justify-center bg-black/80 backdrop-blur-md p-4"
          >
            <motion.div
              initial={{ scale: 0.5 }} animate={{ scale: 1 }}
              transition={{ type: "spring", damping: 12 }}
              className="w-full max-w-sm text-center p-8 rounded-3xl bg-gradient-to-br from-emerald-500 via-emerald-400 to-primary text-white shadow-2xl"
            >
              <motion.div animate={{ y: [-5, 5, -5], rotate: [0, 5, -5, 0] }} transition={{ duration: 2, repeat: Infinity }} className="text-7xl mb-3">🎊</motion.div>
              <h2 className="font-display font-black text-3xl">Payment Successful!</h2>
              <p className="mt-3 text-2xl">+{success.coinsAdded} 🪙 монет</p>
              <p className="mt-1 opacity-90 text-sm">Новый баланс: <b>{success.newBalance}</b> монет</p>
              <div className="mt-6 flex flex-col gap-2">
                <button
                  data-testid="success-explore"
                  onClick={() => { setSuccess(null); nav("/home"); }}
                  className="w-full btn-pill bg-white text-emerald-600 font-black"
                >
                  Start Exploring →
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </MobileShell>
  );
}
