import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { MobileShell } from "@/components/lovreski/Shell";
import {
  Coins, Crown, Copy, User, AlertTriangle, Phone, MessageSquare, Upload, X,
  Check, Clock, HeartHandshake, Building2,
} from "lucide-react";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";

export default function PremiumPage() {
  const { user, refresh } = useAuth();
  const nav = useNavigate();
  const [packages, setPackages] = useState([]);
  const [sbpPhone, setSbpPhone] = useState("");
  const [recipientName, setRecipientName] = useState("");
  const [selectedPkg, setSelectedPkg] = useState(null); // visual only
  const [supportOpen, setSupportOpen] = useState(false);
  const [receiptFile, setReceiptFile] = useState(null);
  const [receiptDataUrl, setReceiptDataUrl] = useState("");
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [mySubs, setMySubs] = useState([]);
  const fileRef = useRef(null);

  const load = async () => {
    const [pkgRes, mineRes] = await Promise.all([
      api.get("/coins/packages"),
      api.get("/support/my").catch(() => ({ data: [] })),
    ]);
    setPackages(pkgRes.data.packages);
    setSbpPhone(pkgRes.data.sbp_phone || "");
    setRecipientName(pkgRes.data.recipient_name || "");
    setMySubs(mineRes.data || []);
  };
  useEffect(() => { load(); }, []);

  const copyPhone = async () => {
    try { await navigator.clipboard.writeText(sbpPhone); toast.success("Номер скопирован ✓"); }
    catch { toast.error("Не удалось скопировать"); }
  };

  const onPickFile = (file) => {
    if (!file) return;
    const ok = ["image/jpeg", "image/jpg", "image/png", "application/pdf"].includes(file.type);
    if (!ok) return toast.error("Только JPG, PNG или PDF");
    setReceiptFile(file);
    const reader = new FileReader();
    reader.onload = () => setReceiptDataUrl(reader.result);
    reader.readAsDataURL(file);
  };

  const submitReceipt = async () => {
    if (!receiptDataUrl) return toast.error("Загрузите чек");
    setSubmitting(true);
    try {
      await api.post("/support/receipt", {
        package_id: selectedPkg?.id,
        receipt_data_url: receiptDataUrl,
        message: message || null,
      });
      toast.success("✅ Чек отправлен! Администратор проверит и активирует Premium.");
      setSupportOpen(false); setReceiptFile(null); setReceiptDataUrl(""); setMessage("");
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Ошибка отправки");
    } finally { setSubmitting(false); }
  };

  return (
    <MobileShell>
      <header className="sticky top-0 z-40 bg-background/85 backdrop-blur-xl px-4 pt-4 pb-3 border-b border-border/50 flex items-center gap-2">
        <button onClick={() => nav(-1)} className="text-sm text-muted-foreground">← Назад</button>
        <h1 className="font-display font-black text-xl flex items-center gap-2"><Crown className="w-6 h-6 text-accent" /> Premium & Монеты</h1>
      </header>

      <div className="p-4 space-y-5">
        {/* Live balance */}
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

        {/* Coin packages — visual selection ONLY (no auto-payment) */}
        <div>
          <h3 className="font-display font-bold text-lg mb-3">Выберите пакет</h3>
          <div className="grid grid-cols-2 gap-3">
            {packages.map((p) => (
              <button
                key={p.id}
                data-testid={`pkg-${p.id}`}
                onClick={() => setSelectedPkg(p)}
                className={`relative p-5 rounded-2xl text-left border-2 overflow-hidden transition-all duration-200 hover:scale-[1.02] active:scale-95 ${selectedPkg?.id === p.id ? "border-primary bg-primary/10 shadow-lg shadow-primary/20 scale-[1.02]" : p.popular ? "border-accent bg-gradient-to-br from-accent/10 to-primary/5" : "border-border bg-card hover:border-primary/60"}`}
              >
                {p.popular && (
                  <div className="absolute -top-2 -right-2 rotate-6 bg-accent text-accent-foreground text-[9px] font-black px-2 py-0.5 rounded-full uppercase tracking-widest shadow-md">
                    Popular
                  </div>
                )}
                {selectedPkg?.id === p.id && (
                  <div className="absolute top-1 right-1 w-6 h-6 rounded-full bg-primary text-primary-foreground flex items-center justify-center shadow-md">
                    <Check className="w-3.5 h-3.5" />
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
          <p className="text-[11px] text-muted-foreground mt-2 text-center">Выбор пакета не активирует оплату автоматически — оплатите вручную и отправьте чек ниже.</p>
        </div>

        {/* SBP payment info card */}
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
          <div className="mt-3 flex items-center gap-2 text-sm">
            <User className="w-4 h-4 text-primary" />
            <span className="text-muted-foreground">Получатель:</span>
            <span data-testid="sbp-recipient" className="font-semibold">{recipientName || "Al Amin Dewan"}</span>
          </div>
          <div data-testid="any-bank-note" className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
            <Building2 className="w-4 h-4" /> Any bank choose — оплатите из любого банка (Сбер, T-Bank, Альфа, ВТБ и др.)
          </div>
        </div>

        {/* Rules Box — amber border */}
        <div data-testid="rules-box" className="p-4 rounded-2xl border-2 border-amber-400 bg-amber-50 dark:bg-amber-950/30">
          <p className="font-display font-black text-sm flex items-center gap-1.5 text-amber-700 dark:text-amber-400 mb-2">
            <AlertTriangle className="w-4 h-4" /> PREMIUM ACTIVATION RULES
          </p>
          <ol className="space-y-1.5 text-[11px] leading-relaxed text-amber-900 dark:text-amber-100 list-decimal pl-4">
            <li data-testid="rule-1">Before making a premium payment, the user must verify that the recipient's banking name is <b>"Al Amin Dewan"</b>.</li>
            <li data-testid="rule-2">The user can select their preferred bank (e.g., Sberbank, T-Bank) before proceeding with payment.</li>
            <li data-testid="rule-3">After making the payment, you MUST send the payment receipt/screenshot to the Support Section.</li>
            <li data-testid="rule-4">Premium activation time is strictly: 🕗 <b>Moscow time 9 PM — 11:59 PM</b> (daily).</li>
            <li data-testid="rule-5">Admin will verify every receipt manually. ⚠️ If payment is NOT received in the account, premium will NOT be activated — even if a receipt is submitted.</li>
            <li data-testid="rule-6">💡 Admin advice: add new coins / renew your Premium BEFORE it expires to avoid interruption.</li>
          </ol>
        </div>

        {/* Premium Activation Support button */}
        <button
          data-testid="btn-open-support"
          onClick={() => setSupportOpen(true)}
          className="w-full btn-pill bg-primary text-primary-foreground shadow-lg shadow-primary/25"
        >
          <HeartHandshake className="w-4 h-4 mr-2" />
          📩 Premium Activation Support
        </button>

        {/* My previous submissions */}
        {mySubs.length > 0 && (
          <div>
            <h4 className="font-display font-bold text-sm mb-2">Мои заявки</h4>
            <div className="space-y-2">
              {mySubs.map((s) => (
                <div key={s.submission_id} data-testid={`sub-${s.submission_id}`} className="p-3 rounded-xl bg-card border border-border flex items-center justify-between">
                  <div>
                    <p className="text-xs text-muted-foreground">{new Date(s.created_at).toLocaleString("ru")}</p>
                    {s.message && <p className="text-xs mt-1">{s.message}</p>}
                    {s.status === "rejected" && s.reject_reason && <p className="text-[11px] text-rose-500 mt-1">Причина: {s.reject_reason}</p>}
                  </div>
                  <span className={`text-xs font-bold px-2 py-1 rounded-full flex items-center gap-1 ${s.status === "verified" ? "bg-emerald-500/15 text-emerald-500" : s.status === "rejected" ? "bg-rose-500/15 text-rose-500" : "bg-amber-500/15 text-amber-500"}`}>
                    {s.status === "verified" ? <Check className="w-3 h-3" /> : s.status === "rejected" ? <X className="w-3 h-3" /> : <Clock className="w-3 h-3" />}
                    {s.status === "verified" ? "Одобрено" : s.status === "rejected" ? "Отклонено" : "Ожидание"}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Support Submission Panel */}
      <AnimatePresence>
        {supportOpen && (
          <motion.div
            data-testid="support-panel"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-[70] flex items-end sm:items-center justify-center bg-black/70 backdrop-blur-sm p-0 sm:p-4"
            onClick={() => !submitting && setSupportOpen(false)}
          >
            <motion.div
              onClick={(e) => e.stopPropagation()}
              initial={{ y: 60, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 60, opacity: 0 }}
              className="w-full sm:max-w-md bg-card border-t sm:border sm:rounded-2xl border-border shadow-2xl p-6 rounded-t-3xl"
            >
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="font-display font-black text-lg">Premium Activation Support</h3>
                  <p className="text-xs text-muted-foreground">Загрузите чек для проверки администратором</p>
                </div>
                <button onClick={() => setSupportOpen(false)} className="p-1 rounded-full hover:bg-muted"><X className="w-5 h-5" /></button>
              </div>

              <input
                ref={fileRef}
                data-testid="receipt-file-input"
                type="file"
                accept="image/jpeg,image/jpg,image/png,application/pdf"
                className="hidden"
                onChange={(e) => onPickFile(e.target.files?.[0])}
              />
              <button
                data-testid="btn-pick-receipt"
                onClick={() => fileRef.current?.click()}
                className={`mt-4 w-full p-6 rounded-2xl border-2 border-dashed flex flex-col items-center justify-center transition-colors duration-200 ${receiptFile ? "border-emerald-500 bg-emerald-500/5" : "border-border hover:border-primary"}`}
              >
                <Upload className="w-8 h-8 text-primary mb-2" />
                <p className="text-sm font-semibold">{receiptFile ? `✓ ${receiptFile.name}` : "📎 Upload Receipt"}</p>
                <p className="text-[11px] text-muted-foreground mt-1">JPG · PNG · PDF</p>
              </button>

              {receiptDataUrl.startsWith("data:image/") && (
                <img src={receiptDataUrl} alt="preview" className="mt-3 w-full max-h-48 object-contain rounded-xl border border-border" />
              )}

              <div className="mt-4">
                <label className="text-xs font-semibold text-muted-foreground flex items-center gap-1"><MessageSquare className="w-3 h-3" /> Сообщение (необязательно)</label>
                <textarea
                  data-testid="receipt-message"
                  rows={2} maxLength={500}
                  placeholder="Короткое сообщение..."
                  value={message} onChange={(e) => setMessage(e.target.value)}
                  className="mt-1 w-full px-3 py-2 rounded-xl bg-muted outline-none text-sm"
                />
              </div>

              <button
                data-testid="btn-submit-receipt"
                onClick={submitReceipt}
                disabled={!receiptDataUrl || submitting}
                className="mt-4 w-full btn-pill bg-primary text-primary-foreground disabled:opacity-50"
              >
                {submitting ? "..." : "📤 Submit to Admin"}
              </button>
              <p className="text-[11px] text-muted-foreground mt-2 text-center">Файл обязателен. Сообщение — по желанию.</p>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </MobileShell>
  );
}
