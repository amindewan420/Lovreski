import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { MobileShell } from "@/components/lovreski/Shell";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ChevronRight, User, Search, Crown, Bell, Languages, FileText, Download, Shield, LogOut } from "lucide-react";
import { useI18n, getLangMeta } from "@/lib/i18n";
import LanguageSheet from "@/components/lovreski/LanguageSheet";

const LEGAL = {
  terms: {
    title: "User Agreement — Lovreski Platform",
    body: `USER AGREEMENT OF THE LOVRESKI INTERNET PLATFORM\n\nBy this User Agreement, the Administration of the Lovreski Platform invites any person (the "User") to use the services provided by the Platform.\n\nThe Platform Administration offers the User the opportunity to use the Platform's features under the terms specified in this Agreement.\n\nUsing the Platform means the User accepts and agrees to comply with all terms of this Agreement.\n\nTERMS AND DEFINITIONS:\n\nPlatform — A set of software and hardware tools providing public access to information through the Internet.\n\nPlatform Administration — Representatives of the Lovreski Platform authorized by owner Al Amin Dewan to manage and control the Platform's operation.\n\nPlatform User — A person who uses the Lovreski Platform in accordance with these Terms.\n\nPersonal Account — A set of protected pages created during User registration, accessed via login and password.\n\nAccount/Profile — A unique name (login) and password for accessing the User's personal pages within the Platform.\n\nServices — Paid and Free services provided by the Platform Administration to the User.\n\nContent — Text, graphics, audio, and any other materials posted on the Platform.\n\nFree Services — Services provided to Platform Users at no cost.\n\nPaid Services — Services provided after they are ordered and payment is confirmed.\n\n1. GENERAL PROVISIONS\n\nThis Agreement governs the relationship between the Platform Administration and Users when using the Platform's features.\n\nThe Platform is an online platform where the Administration provides information services to introduce Users to each other, strictly in accordance with this Agreement.\n\nThe current version of this Agreement is available at: https://lovreski.com.ru\n\nThe Platform Administration reserves the right to make changes to this Agreement by publishing the new version online. Users are required to regularly monitor changes to the Agreement.\n\nThe domain name lovreski.com.ru is owned by the Platform Administration.\n\n2. ACCEPTANCE OF THE AGREEMENT\n\nTo fully use the Platform's functionality, the User must accept this Agreement.\n\nAcceptance means the User's full agreement with all terms of this Agreement.\n\nFrom a legal point of view, acceptance includes registering on the Platform or starting to use its functionality.\n\nThe User is prohibited from using the Platform without fully agreeing to the terms of this Agreement.\n\nThe period for accepting this Agreement is unlimited.\n\n3. REGISTRATION\n\nThe Platform Administration invites Users to register on the Platform to gain access to its features.\n\nRegistration is carried out by filling out a registration form and confirming via a code value, or through social network authorization.\n\nAfter completing registration, Users can pay for paid services and start using the Platform's features.\n\n4. ADMINISTRATION STATUS\n\nThe Platform Administration monitors the Platform's functionality and User actions.\n\nThe Administration reserves the right to:\n— Change the Platform's design, content, and service list at any time.\n— Send messages to Users via email or other available means.\n— Modify or delete any Content that violates the Agreement or applicable laws.\n— Restrict or terminate User access to the Platform with or without prior notice.\n— Set additional restrictions on the use of the Platform at any time.\n\nThe Administration undertakes to:\n— Provide User data to third parties only in accordance with this Agreement and applicable law.\n— Ensure proper provision of services in accordance with the terms of this Agreement.\n— Provide consultations to Users on additional issues arising from this Agreement.\n\n5. USER'S LEGAL STATUS\n\nThe User has the right to:\n— Use the Platform's full functionality.\n— Require the Platform Administration to comply with the terms of this Agreement.\n— Submit requests to the Administration regarding the Platform's functioning.\n\nThe User undertakes to:\n— Comply with all terms of this Agreement.\n— Provide only true personal data.\n— Not use Platform services for illegal purposes or in ways that may harm the Platform or third parties.\n— Not disclose confidential information.\n— Not perform actions prohibited by this Agreement.\n\nWhen using the Platform, the User is prohibited from:\n— Using the Platform in any way that interferes with its normal functioning.\n— Downloading, storing, or distributing viruses or malicious programs.\n— Collecting or storing Users' personal data for commercial purposes.\n— Posting pornographic materials or links to such content.\n— Posting any information considered undesirable by the Platform Administration.\n\n6. PARTNER SELECTION SERVICES & PRICING\n\nBasic services for searching and selecting potential partners are provided free of charge. Registered users become a "Platform User."\n\nTo become a User, you must create an account with a valid email address, password, and other required information.\n\nYou are prohibited from using another person's name, a name owned by someone else, or any offensive/obscene name as your username.\n\nB. Premium Services:\n\n💳 How to Activate Premium?\n\nTo get Premium, copy the SBP phone number given in the Premium & Coins section.\nOpen your bank app and paste the copied number in the recipient field.\nChoose your favourite Premium package and pay the exact amount.\nAfter payment, take a screenshot or save your payment receipt.\nGo to the Support section inside the app and send your payment receipt to the admin.\nThe admin will verify your payment and add the coins to your account.\nOnce verified, your Premium will be activated successfully! 🎉\n\n7. VALIDITY PERIOD\n\nThis User Agreement becomes effective upon acceptance by the User and remains in effect throughout the User's use of the Platform.\n\nEarly termination is carried out by sending a relevant notification to the Platform Administration.\n\nThis Agreement becomes effective from the moment it is published on the Platform's pages and remains in effect for an unlimited period of time.`,
  },
  payment: {
    title: "💳 Payment Rules",
    body: `The Platform provides limited functionality completely free of charge. The free version allows the User to send no more than one message to the same chat.\n\nTo use the full functionality — including sending more than one message — the User must purchase Coins.\n\nThe number of Coins ranges from 1 to 500. There is no limit to the number of Coin purchases a user can make.\n\nCOIN PRICING:\n\n1 Coin        —  5 ₽\n100 Coins     —  500 ₽  (5.0 ₽/coin)\n200 Coins     —  900 ₽  (4.5 ₽/coin)\n300 Coins     — 1,200 ₽ (4.0 ₽/coin)\n500 Coins     — 1,900 ₽ (3.8 ₽/coin)\n\nEach time 1 message is sent, 1 Coin is deducted from the User's account balance.\n\n💳 How to Activate Premium?\n\nTo get Premium, copy the SBP phone number given in the Premium & Coins section.\nOpen your bank app and paste the copied number in the recipient field.\nChoose your favourite Premium package and pay the exact amount.\nAfter payment, take a screenshot or save your payment receipt file.\nGo to the Support section inside the app and send your payment receipt to the admin.\nThe admin will verify your payment and add the coins to your account.\nOnce verified, your Premium will be activated successfully! 🎉`,
  },
  security: {
    title: "🔒 Security Tips",
    body: `We strive to make online dating easier and safer. Every new profile is checked at registration. All data is encrypted to prevent fraud and bank card theft. Suspicious profiles are actively blocked.\n\n💬 Communication on the Site:\n\nDo not share your contact information until you have gotten to know the person properly. Attackers often try to get your social media or phone number immediately.\n\nDo not transfer money at the request of another person, even if they claim to be in trouble.\n\nDo not disclose your bank card details or share your SMS passwords.\n\nDo not click on questionable links.\n\nRemember to delete any information that attackers may find and use against you.\n\n🤝 Real-Life Communication:\n\nGet to know the person well before meeting in real life. Do not agree to meet after just a few messages.\n\nHold your first meetings in public places that you are familiar with.\n\nKeep your family or friends informed about when and where you plan to meet someone new.\n\nCharge your phone and keep it with you at all times.\n\nIf you feel uncomfortable, leave the meeting under any pretext.`,
  },
  refund: { title: "💰 Refund Request", body: "" },
};
const LEGAL_ORDER = ["terms", "payment", "security", "refund"];

export default function SettingsPage() {
  const { user, refresh, logout } = useAuth();
  const nav = useNavigate();
  const { t, lang, setLang } = useI18n();
  const langMeta = getLangMeta(lang);
  const [section, setSection] = useState(null);
  const [form, setForm] = useState({});
  const [installed, setInstalled] = useState(false);
  const [showLang, setShowLang] = useState(false);

  useEffect(() => { if (user) setForm({ ...user }); }, [user]);
  useEffect(() => {
    setInstalled(window.matchMedia("(display-mode: standalone)").matches);
  }, []);

  const save = async (payload) => { try { await api.put("/profile", payload); await refresh(); toast.success("Сохранено"); } catch { toast.error("Ошибка"); } };

  const install = () => {
    if (installed) return toast.info("Приложение уже установлено");
    toast.info("Используйте меню браузера → «Установить приложение»");
  };

  if (section && LEGAL[section]) {
    const l = LEGAL[section];
    return (
      <MobileShell>
        <header className="sticky top-0 z-40 bg-background/85 backdrop-blur-xl px-4 pt-4 pb-3 border-b border-border/50 flex items-center gap-2">
          <button onClick={() => setSection(null)} className="text-sm text-muted-foreground">← Назад</button>
          <h1 className="font-display font-black text-xl">{l.title}</h1>
        </header>
        {section === "refund" ? <RefundForm /> : (
          <div className="p-4 text-sm leading-relaxed whitespace-pre-wrap">{l.body}</div>
        )}
      </MobileShell>
    );
  }

  return (
    <MobileShell>
      <header className="sticky top-0 z-40 bg-background/85 backdrop-blur-xl px-4 pt-4 pb-3 border-b border-border/50 flex items-center gap-2">
        <button onClick={() => nav(-1)} className="text-sm text-muted-foreground">{t("settings.back")}</button>
        <h1 className="font-display font-black text-xl">{t("settings.title")}</h1>
      </header>

      <div className="p-4 space-y-6">
        <Section title={t("settings.section.personal")} icon={User}>
          <Row label={t("settings.name")}><input value={form.name || ""} onChange={(e) => setForm({ ...form, name: e.target.value })} onBlur={() => save({ name: form.name })} className="bg-transparent text-right outline-none" /></Row>
          <Row label={t("settings.gender")}>
            <select value={form.gender || "female"} onChange={(e) => { setForm({ ...form, gender: e.target.value }); save({ gender: e.target.value }); }} className="bg-transparent text-right outline-none">
              <option value="female">{t("settings.female")}</option><option value="male">{t("settings.male")}</option>
            </select>
          </Row>
          <Row label={t("settings.dob")}><input type="date" value={form.dob || ""} onChange={(e) => { setForm({ ...form, dob: e.target.value }); save({ dob: e.target.value }); }} className="bg-transparent text-right outline-none" /></Row>
        </Section>

        <Section title={t("settings.section.search")} icon={Search}>
          <Row label={t("settings.show_me")}>
            <select data-testid="show-me" value={form.show_me || "both"} onChange={(e) => { setForm({ ...form, show_me: e.target.value }); save({ show_me: e.target.value }); }} className="bg-transparent text-right outline-none">
              <option value="female">{t("settings.show_female")}</option><option value="male">{t("settings.show_male")}</option><option value="both">{t("settings.show_both")}</option>
            </select>
          </Row>
          <Row label={`Возраст: ${form.age_min || 18}–${form.age_max || 60}`}>
            <div className="flex gap-1">
              <input type="number" min={18} max={80} value={form.age_min || 18} onChange={(e) => setForm({ ...form, age_min: +e.target.value })} onBlur={() => save({ age_min: form.age_min })} className="w-14 bg-muted rounded px-1 text-right" />
              <input type="number" min={18} max={80} value={form.age_max || 60} onChange={(e) => setForm({ ...form, age_max: +e.target.value })} onBlur={() => save({ age_max: form.age_max })} className="w-14 bg-muted rounded px-1 text-right" />
            </div>
          </Row>
          <Row label={t("settings.distance")}>
            <select data-testid="distance-mode" value={form.distance_mode || "unlimited"} onChange={(e) => { setForm({ ...form, distance_mode: e.target.value }); save({ distance_mode: e.target.value }); }} className="bg-transparent text-right outline-none">
              <option value="limited">{t("settings.distance_near")}</option><option value="unlimited">{t("settings.distance_world")}</option>
            </select>
          </Row>
          {form.distance_mode === "limited" && (
            <div data-testid="distance-slider-row" className="px-4 py-3 border-t border-border">
              {!(form.lat && form.lng) && (
                <p className="text-xs text-amber-600 dark:text-amber-400 mb-2">📍 Разрешите доступ к геолокации для использования фильтра расстояния</p>
              )}
              <p data-testid="distance-label" className="text-sm font-semibold mb-1">В радиусе: {form.distance_km ?? 50} км</p>
              <input
                data-testid="distance-slider"
                type="range" min={0} max={2000} step={10}
                value={form.distance_km ?? 50}
                onChange={(e) => setForm({ ...form, distance_km: parseInt(e.target.value) })}
                onMouseUp={() => save({ distance_km: form.distance_km ?? 50 })}
                onTouchEnd={() => save({ distance_km: form.distance_km ?? 50 })}
                className="w-full accent-primary"
              />
              <div className="flex justify-between text-[10px] text-muted-foreground mt-1"><span>0 км</span><span>2000 км</span></div>
            </div>
          )}
        </Section>

        <Section title={t("settings.section.premium")} icon={Crown}>
          <button data-testid="link-premium" onClick={() => nav("/premium")} className="w-full flex justify-between items-center py-2 text-sm">
            <span>{t("settings.manage_premium")}</span><ChevronRight className="w-4 h-4" />
          </button>
        </Section>

        <Section title={t("settings.section.notifications")} icon={Bell}>
          {["messages","likes","matches","visits","who_liked"].map((k) => (
            <Row key={k} label={t(`settings.notif.${k}`)}>
              <input type="checkbox" checked={form.notif_push?.[k] || false} onChange={(e) => { const np = { ...(form.notif_push||{}), [k]: e.target.checked }; setForm({ ...form, notif_push: np }); save({ notif_push: np }); }} className="accent-primary" />
            </Row>
          ))}
        </Section>

        <Section title={t("settings.section.translate")} icon={Languages}>
          <Row label={t("settings.auto_translate")}>
            <input data-testid="toggle-translate" type="checkbox" checked={form.auto_translate || false} onChange={(e) => { setForm({ ...form, auto_translate: e.target.checked }); save({ auto_translate: e.target.checked }); }} className="accent-primary" />
          </Row>
          <button data-testid="settings-language-row" onClick={() => setShowLang(true)} className="w-full flex justify-between items-center px-4 py-3 text-sm">
            <span>{t("settings.language")}</span>
            <span className="flex items-center gap-2 text-muted-foreground">
              <span className="text-lg">{langMeta.flag}</span>
              <span>{langMeta.name}</span>
              <ChevronRight className="w-4 h-4" />
            </span>
          </button>
        </Section>

        <Section title={t("settings.section.legal")} icon={FileText}>
          {LEGAL_ORDER.map((k) => (
            <button key={k} data-testid={`legal-${k}`} onClick={() => setSection(k)} className="w-full flex justify-between items-center py-2 text-sm">
              <span>{LEGAL[k].title}</span><ChevronRight className="w-4 h-4" />
            </button>
          ))}
        </Section>

        <button data-testid="btn-install" onClick={install} className="w-full btn-pill bg-primary text-primary-foreground"><Download className="w-4 h-4 mr-2" /> {installed ? t("settings.installed") : t("settings.install")}</button>

        {user?.is_admin && (
          <button onClick={() => nav("/admin")} className="w-full btn-pill bg-foreground text-background"><Shield className="w-4 h-4 mr-2" /> {t("settings.admin")}</button>
        )}
        <button onClick={async () => { await logout(); nav("/"); }} className="w-full btn-pill bg-muted"><LogOut className="w-4 h-4 mr-2" /> {t("settings.logout")}</button>
      </div>
      <LanguageSheet open={showLang} onClose={() => setShowLang(false)} onSelect={async (l) => { const r = await setLang(l.code); setShowLang(false); if (r?.actualLang !== l.code) toast.error("Перевод недоступен, оставили русский"); else toast.success(`${l.flag} ${l.name}`); }} />
    </MobileShell>
  );
}

const Section = ({ title, icon: Icon, children }) => (
  <div>
    <h3 className="font-display font-bold text-sm text-muted-foreground uppercase tracking-widest mb-2 flex items-center gap-2"><Icon className="w-4 h-4" /> {title}</h3>
    <div className="bg-card rounded-2xl border border-border divide-y divide-border">{children}</div>
  </div>
);
const Row = ({ label, children }) => (
  <div className="flex justify-between items-center px-4 py-3 text-sm">
    <span>{label}</span>
    <div>{children}</div>
  </div>
);

function RefundForm() {
  const [f, setF] = useState({ full_name: "", email: "", reason: "" });
  const [receipt, setReceipt] = useState("");
  const [fileName, setFileName] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const ref = useRef(null);
  const pick = (file) => {
    if (!file) return;
    setFileName(file.name);
    const r = new FileReader(); r.onload = () => setReceipt(r.result); r.readAsDataURL(file);
  };
  const valid = f.full_name.trim() && f.email.trim() && f.reason.trim() && receipt;
  const submit = async () => {
    if (!valid) return toast.error("Заполните все поля и приложите чек");
    setBusy(true);
    try {
      await api.post("/support/refund", { ...f, receipt_data_url: receipt });
      setDone(true);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Ошибка");
    } finally { setBusy(false); }
  };
  if (done) return (
    <div className="p-6 text-center">
      <p className="text-4xl">✅</p>
      <p className="mt-3 font-display font-bold text-lg">Your refund request has been submitted successfully!</p>
      <p className="mt-2 text-sm text-muted-foreground">Admin will review within 24-48 hours.</p>
    </div>
  );
  return (
    <div className="p-4 space-y-3" data-testid="refund-form">
      <p className="text-sm text-muted-foreground">To request a coin refund, please fill in the form below completely. Your request will be reviewed by the admin and processed accordingly.</p>
      <label className="text-xs font-semibold">Full Name *</label>
      <input data-testid="refund-name" placeholder="Enter your full name" value={f.full_name} onChange={(e) => setF({...f, full_name: e.target.value})} className="w-full px-3 py-2 rounded-xl bg-muted outline-none" />
      <label className="text-xs font-semibold">Email Address *</label>
      <input data-testid="refund-email" type="email" placeholder="Enter your email address" value={f.email} onChange={(e) => setF({...f, email: e.target.value})} className="w-full px-3 py-2 rounded-xl bg-muted outline-none" />
      <label className="text-xs font-semibold">Payment Receipt *</label>
      <input ref={ref} type="file" accept="image/*" className="hidden" onChange={(e) => pick(e.target.files?.[0])} data-testid="refund-file-input" />
      <button data-testid="refund-upload-btn" onClick={() => ref.current?.click()} className={`w-full p-3 rounded-xl border-2 border-dashed ${receipt ? "border-emerald-500 bg-emerald-500/5" : "border-border"}`}>📎 Upload Receipt {fileName && `· ${fileName}`}</button>
      <label className="text-xs font-semibold">Reason for Refund *</label>
      <textarea data-testid="refund-reason" rows={4} maxLength={1000} placeholder="Please explain why you are requesting a refund..." value={f.reason} onChange={(e) => setF({...f, reason: e.target.value})} className="w-full px-3 py-2 rounded-xl bg-muted outline-none" />
      <button data-testid="refund-submit" onClick={submit} disabled={!valid || busy} className="w-full btn-pill bg-primary text-primary-foreground disabled:opacity-50">{busy ? "..." : "📩 Submit Refund Request"}</button>
      <p className="text-[11px] text-amber-600 dark:text-amber-400 border-l-2 border-amber-500 pl-2 mt-2">⚠️ Note: Refund requests are reviewed manually by the admin. Please allow 24-48 hours for processing. Incomplete requests will not be considered.</p>
    </div>
  );
}
