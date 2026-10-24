import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { BellRing, Upload, CheckCircle2, AlertCircle, Trash2, Send, KeyRound } from "lucide-react";

const FIELDS = [
  { k: "project_id", label: "Project ID", ph: "Firebase Console → ⚙ Project settings → General → Project ID (заполняется из JSON автоматически)" },
  { k: "api_key", label: "Web API Key", ph: "Project settings → General → Your apps → Web app → SDK setup → apiKey" },
  { k: "app_id", label: "App ID", ph: "Project settings → General → Your apps → Web app → appId (1:123…:web:abc…)" },
  { k: "sender_id", label: "Sender ID", ph: "Project settings → Cloud Messaging → Sender ID (messagingSenderId)" },
  { k: "vapid_key", label: "VAPID key (Web Push certificate)", ph: "Project settings → Cloud Messaging → Web configuration → Web Push certificates → Key pair" },
  { k: "auth_domain", label: "Auth domain (необязательно)", ph: "<project-id>.firebaseapp.com — по умолчанию подставляется автоматически" },
];

const errMsg = (e) => e?.response?.data?.detail || e.message || "Ошибка";

const StatusPill = ({ ok, children, testid }) => (
  <span data-testid={testid} className={`inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full ${ok ? "bg-emerald-500/15 text-emerald-600" : "bg-amber-500/15 text-amber-600"}`}>
    {ok ? <CheckCircle2 className="w-3.5 h-3.5" /> : <AlertCircle className="w-3.5 h-3.5" />}{children}
  </span>
);

const ServiceAccountCard = ({ cfg, onSaved }) => {
  const fileRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const onFile = async (e) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    setBusy(true);
    try {
      const text = await f.text();
      const { data } = await api.put("/admin/push/config", { service_account_json: text });
      onSaved(data);
      toast.success("Service account загружен и проверен");
    } catch (err) { toast.error(errMsg(err)); } finally { setBusy(false); }
  };
  const remove = async () => {
    if (!window.confirm("Удалить service account? Push-уведомления перестанут отправляться.")) return;
    const { data } = await api.delete("/admin/push/service-account");
    onSaved(data);
    toast.success("Service account удалён");
  };
  return (
    <div className="p-5 rounded-2xl bg-card border border-border">
      <div className="flex items-center gap-2 mb-1"><KeyRound className="w-4 h-4 text-primary" /><h3 className="font-display font-bold">Service account (.json)</h3></div>
      <p className="text-xs text-muted-foreground mb-3">Firebase Console → ⚙ Project settings → <b>Service accounts</b> → «Generate new private key». Файл шифруется в базе данных и никогда не возвращается в браузер.</p>
      {cfg.has_service_account ? (
        <div data-testid="push-sa-info" className="p-3 rounded-xl bg-muted text-sm flex items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="font-semibold truncate">{cfg.client_email}</p>
            <p className="text-xs text-muted-foreground">project: {cfg.sa_project_id}</p>
          </div>
          <button data-testid="push-sa-remove" onClick={remove} className="p-2 rounded-full hover:bg-background text-rose-500"><Trash2 className="w-4 h-4" /></button>
        </div>
      ) : (
        <p data-testid="push-sa-empty" className="text-sm text-muted-foreground p-3 rounded-xl bg-muted">Файл ещё не загружен</p>
      )}
      <input ref={fileRef} type="file" accept="application/json,.json" className="hidden" onChange={onFile} data-testid="push-sa-file" />
      <button data-testid="push-sa-upload" disabled={busy} onClick={() => fileRef.current?.click()} className="mt-3 w-full py-2.5 rounded-full bg-primary text-primary-foreground font-semibold text-sm flex items-center justify-center gap-2 disabled:opacity-60">
        <Upload className="w-4 h-4" /> {busy ? "Проверяем..." : cfg.has_service_account ? "Заменить файл" : "Загрузить JSON файл"}
      </button>
    </div>
  );
};

const WebConfigCard = ({ cfg, onSaved }) => {
  const [form, setForm] = useState({});
  const [busy, setBusy] = useState(false);
  useEffect(() => { setForm(Object.fromEntries(FIELDS.map((f) => [f.k, cfg[f.k] || ""]))); }, [cfg]);
  const save = async () => {
    setBusy(true);
    try { const { data } = await api.put("/admin/push/config", form); onSaved(data); toast.success("Настройки сохранены"); }
    catch (err) { toast.error(errMsg(err)); } finally { setBusy(false); }
  };
  return (
    <div className="p-5 rounded-2xl bg-card border border-border">
      <h3 className="font-display font-bold mb-1">Web app config & VAPID</h3>
      <p className="text-xs text-muted-foreground mb-4">Если в проекте ещё нет Web-приложения: Project settings → General → «Add app» → Web (&lt;/&gt;).</p>
      <div className="space-y-3">
        {FIELDS.map((f) => (
          <label key={f.k} className="block">
            <span className="text-xs font-semibold text-muted-foreground">{f.label}</span>
            <input data-testid={`push-field-${f.k}`} value={form[f.k] || ""} placeholder={f.ph} onChange={(e) => setForm({ ...form, [f.k]: e.target.value })}
              className="mt-1 w-full px-3 py-2 rounded-xl bg-muted border border-border text-sm placeholder:text-[11px] placeholder:text-muted-foreground/70 focus:outline-none focus:ring-2 focus:ring-primary/40" />
          </label>
        ))}
      </div>
      <button data-testid="push-config-save" disabled={busy} onClick={save} className="mt-4 w-full py-2.5 rounded-full bg-foreground text-background font-semibold text-sm disabled:opacity-60">{busy ? "..." : "Сохранить"}</button>
    </div>
  );
};

const AnnounceCard = ({ ready }) => {
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const send = async () => {
    if (!title.trim() || !body.trim()) return toast.error("Заполните заголовок и текст");
    if (!window.confirm("Отправить объявление всем пользователям?")) return;
    setBusy(true);
    try {
      const { data } = await api.post("/admin/push/announce", { title, body, url: "/home" });
      toast.success(`Отправлено: в приложении ${data.in_app}, push ${data.sent} устройств`);
      setTitle(""); setBody("");
    } catch (err) { toast.error(errMsg(err)); } finally { setBusy(false); }
  };
  return (
    <div className="p-5 rounded-2xl bg-card border border-border">
      <h3 className="font-display font-bold mb-1">Объявление для всех</h3>
      <p className="text-xs text-muted-foreground mb-3">Появится в уведомлениях приложения{ready ? " и придёт push-уведомлением тем, кто их включил" : " (push не отправится, пока Firebase не настроен)"}.</p>
      <input data-testid="announce-title" value={title} maxLength={100} onChange={(e) => setTitle(e.target.value)} placeholder="Заголовок" className="w-full px-3 py-2 rounded-xl bg-muted border border-border text-sm mb-2" />
      <textarea data-testid="announce-body" value={body} maxLength={300} onChange={(e) => setBody(e.target.value)} placeholder="Текст объявления" rows={3} className="w-full px-3 py-2 rounded-xl bg-muted border border-border text-sm" />
      <button data-testid="announce-send" disabled={busy} onClick={send} className="mt-3 w-full py-2.5 rounded-full bg-primary text-primary-foreground font-semibold text-sm flex items-center justify-center gap-2 disabled:opacity-60"><Send className="w-4 h-4" /> {busy ? "..." : "Отправить"}</button>
    </div>
  );
};

export const PushConfigTab = () => {
  const [cfg, setCfg] = useState(null);
  const load = () => api.get("/admin/push/config").then((r) => setCfg(r.data)).catch(() => toast.error("Не удалось загрузить настройки"));
  useEffect(() => { load(); }, []);
  if (!cfg) return <p className="text-muted-foreground text-sm">Загрузка...</p>;
  const onSaved = (data) => setCfg((c) => ({ ...c, ...data }));
  return (
    <div data-testid="admin-push-tab" className="grid lg:grid-cols-2 gap-6 items-start">
      <div className="lg:col-span-2 p-5 rounded-2xl bg-card border border-border flex flex-wrap items-center gap-3">
        <BellRing className="w-5 h-5 text-primary" />
        <h3 className="font-display font-bold mr-auto">Push-уведомления (Firebase Cloud Messaging)</h3>
        <StatusPill ok={cfg.ready} testid="push-status-pill">{cfg.ready ? "Активны" : "Не настроены"}</StatusPill>
        <span data-testid="push-devices" className="text-xs text-muted-foreground">{cfg.subscribed_users ?? 0} польз. · {cfg.devices ?? 0} устройств</span>
      </div>
      <div className="space-y-6">
        <ServiceAccountCard cfg={cfg} onSaved={onSaved} />
        <AnnounceCard ready={cfg.ready} />
      </div>
      <WebConfigCard cfg={cfg} onSaved={onSaved} />
    </div>
  );
};
