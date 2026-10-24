import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { MobileShell } from "@/components/lovreski/Shell";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ChevronRight, User, Search, Crown, Bell, Languages, FileText, Download, Shield, LogOut, BellRing, BellOff } from "lucide-react";
import { useI18n, getLangMeta } from "@/lib/i18n";
import LanguageSheet from "@/components/lovreski/LanguageSheet";
import { Slider } from "@/components/ui/slider";
import { usePushNotifications } from "@/hooks/usePushNotifications";
import { RECEIPT_ACCEPT, receiptFileError, readReceipt } from "@/lib/receiptFile";
import { FILTER_SIG_KEY } from "@/lib/filterSync";
import { useLegalDocs, LegalDocView } from "@/components/lovreski/LegalDoc";


export default function SettingsPage() {
  const { user, refresh, logout } = useAuth();
  const nav = useNavigate();
  const { t, lang, setLang } = useI18n();
  const langMeta = getLangMeta(lang);
  const [section, setSection] = useState(null);
  const { docs: legalDocs, error: legalError } = useLegalDocs();
  const [form, setForm] = useState({});
  const [installed, setInstalled] = useState(false);
  const [showLang, setShowLang] = useState(false);

  useEffect(() => { if (user) setForm({ ...user }); }, [user]);
  const push = usePushNotifications(user);
  useEffect(() => {
    setInstalled(window.matchMedia("(display-mode: standalone)").matches);
  }, []);

  const save = async (payload) => {
    try {
      await api.put("/profile", payload);
      await refresh();
      // Stamp the filter signature so Discover auto-refreshes when filters change
      const f = { ...form, ...payload };
      localStorage.setItem(FILTER_SIG_KEY, JSON.stringify({
        age_min: f.age_min ?? 18, age_max: f.age_max ?? 85,
        distance_mode: f.distance_mode || "unlimited", distance_km: f.distance_km ?? 50,
      }));
      toast.success("Сохранено");
    } catch { toast.error("Ошибка"); }
  };

  const install = () => {
    if (installed) return toast.info("Приложение уже установлено");
    toast.info("Используйте меню браузера → «Установить приложение»");
  };

  if (section) {
    const l = legalDocs.find((d) => d.slug === section) || { title: "" };
    return (
      <MobileShell>
        <header className="sticky top-0 z-40 bg-background/85 backdrop-blur-xl px-4 pt-4 pb-3 border-b border-border/50 flex items-center gap-2">
          <button data-testid="legal-back" onClick={() => setSection(null)} className="text-sm text-muted-foreground shrink-0 whitespace-nowrap">← Назад</button>
          <h1 className="font-display font-black text-xl truncate min-w-0">{l.title}</h1>
        </header>
        <LegalDocView slug={section} />
        {section === "refund-policy" && <RefundForm />}
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
          <div className="px-4 py-3" data-testid="age-range-block">
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm text-slate-700">Возраст</span>
              <span data-testid="age-range-label" className="text-sm font-semibold text-primary">
                {form.age_min || 18}–{form.age_max || 85}
              </span>
            </div>
            <Slider
              min={18}
              max={85}
              step={1}
              minStepsBetweenThumbs={1}
              value={[form.age_min || 18, form.age_max || 85]}
              onValueChange={([a, b]) => setForm({ ...form, age_min: a, age_max: b })}
              onValueCommit={([a, b]) => save({ age_min: a, age_max: b })}
              data-testid="age-range-slider"
              aria-label="Возраст"
            />
            <div className="flex justify-between text-[10px] text-slate-400 mt-1.5">
              <span>18</span><span>85</span>
            </div>
          </div>
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
          {["messages","likes","matches","visits","announcements"].map((k) => (
            <Row key={k} label={t(`settings.notif.${k}`)}>
              <input type="checkbox" data-testid={`notif-toggle-${k}`} checked={form.notif_push?.[k] ?? true} onChange={(e) => { const np = { ...(form.notif_push||{}), [k]: e.target.checked }; setForm({ ...form, notif_push: np }); save({ notif_push: np }); }} className="accent-primary" />
            </Row>
          ))}
        </Section>

        <Section title={t("settings.section.push")} icon={BellRing}>
          {!push.serverConfigured ? (
            <p className="text-xs text-slate-500 py-2 px-1">{t("settings.push_pending")}</p>
          ) : !push.supported ? (
            <p className="text-xs text-slate-500 py-2 px-1">{t("settings.push_unsupported")}</p>
          ) : push.subscribedToken ? (
            <>
              <div className="flex items-center gap-2 py-1.5 text-sm text-emerald-600">
                <BellRing className="w-4 h-4" /> <span>{t("settings.push_on")}</span>
              </div>
              <button
                data-testid="btn-push-test"
                disabled={push.subscribing}
                onClick={async () => {
                  try {
                    const r = await push.sendTest();
                    toast.success(t("settings.push_test_sent") + (r?.sent ? ` (${r.sent})` : ""));
                  } catch (e) { toast.error(e?.response?.data?.detail || t("common.error")); }
                }}
                className="w-full text-left text-sm py-2 text-primary"
              >
                {t("settings.push_test")}
              </button>
              <button
                data-testid="btn-push-off"
                disabled={push.subscribing}
                onClick={async () => {
                  try { await push.unsubscribe(); toast.success(t("settings.push_off_done")); } catch { toast.error(t("common.error")); }
                }}
                className="w-full text-left text-sm py-2 text-red-500 flex items-center gap-2"
              >
                <BellOff className="w-4 h-4" /> {t("settings.push_disable")}
              </button>
            </>
          ) : (
            <button
              data-testid="btn-push-on"
              disabled={push.subscribing}
              onClick={async () => {
                try { await push.subscribe(); toast.success(t("settings.push_on_done")); }
                catch (e) { toast.error(e?.message || t("common.error")); }
              }}
              className="w-full btn-pill bg-primary text-primary-foreground disabled:opacity-60"
            >
              <BellRing className="w-4 h-4 mr-2" /> {push.subscribing ? "..." : t("settings.push_enable")}
            </button>
          )}
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
          {legalDocs.map((d) => (
            <button key={d.slug} data-testid={`legal-${d.slug}`} onClick={() => setSection(d.slug)} className="w-full flex justify-between items-center py-2 text-sm text-left">
              <span>{d.title}</span><ChevronRight className="w-4 h-4 shrink-0" />
            </button>
          ))}
          {legalError && <p className="text-xs text-muted-foreground py-2">Не удалось загрузить документы</p>}
        </Section>

        <button data-testid="btn-install" onClick={install} className="w-full btn-pill bg-primary text-primary-foreground"><Download className="w-4 h-4 mr-2" /> {installed ? t("settings.installed") : t("settings.install")}</button>

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
    const err = receiptFileError(file);
    if (err) { toast.error(err); return; }
    setFileName(file.name);
    readReceipt(file).then(setReceipt).catch(() => toast.error("Не удалось прочитать файл"));
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
      <input ref={ref} type="file" accept={RECEIPT_ACCEPT} className="hidden" onChange={(e) => { pick(e.target.files?.[0]); e.target.value = ""; }} data-testid="refund-file-input" />
      <button data-testid="refund-upload-btn" onClick={() => ref.current?.click()} className={`w-full p-3 rounded-xl border-2 border-dashed ${receipt ? "border-emerald-500 bg-emerald-500/5" : "border-border"}`}>📎 Upload Receipt {fileName && `· ${fileName}`}</button>
      <label className="text-xs font-semibold">Reason for Refund *</label>
      <textarea data-testid="refund-reason" rows={4} maxLength={1000} placeholder="Please explain why you are requesting a refund..." value={f.reason} onChange={(e) => setF({...f, reason: e.target.value})} className="w-full px-3 py-2 rounded-xl bg-muted outline-none" />
      <button data-testid="refund-submit" onClick={submit} disabled={!valid || busy} className="w-full btn-pill bg-primary text-primary-foreground disabled:opacity-50">{busy ? "..." : "📩 Submit Refund Request"}</button>
      <p className="text-[11px] text-amber-600 dark:text-amber-400 border-l-2 border-amber-500 pl-2 mt-2">⚠️ Note: Refund requests are reviewed manually by the admin. Please allow 24-48 hours for processing. Incomplete requests will not be considered.</p>
    </div>
  );
}
