import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useNavigate } from "react-router-dom";
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { Shield, Users, Crown, Clock, TrendingUp, Check, X, Flag, LogOut, Search as SearchIcon, MinusCircle, AlertTriangle, Ban, UserX, FileText, Trash2, Plus, Pencil, Database } from "lucide-react";
import { toast } from "sonner";

// Format bytes for human readability
const fmtBytes = (b) => {
  if (!b && b !== 0) return "—";
  if (b < 1024) return `${b} Б`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} КБ`;
  if (b < 1024 * 1024 * 1024) return `${(b / 1024 / 1024).toFixed(2)} МБ`;
  return `${(b / 1024 / 1024 / 1024).toFixed(2)} ГБ`;
};

const KIND_LABELS = {
  profile_photo: "Фото профиля",
  chat_image: "Чат — фото",
  chat_voice: "Чат — голосовые",
  chat_video: "Чат — видео",
  chat_file: "Чат — файлы",
  support_receipt: "Чеки оплаты",
  refund_receipt: "Чеки возврата",
  other: "Прочее",
};

const KIND_COLORS = {
  profile_photo: "bg-rose-500",
  chat_image: "bg-sky-500",
  chat_voice: "bg-emerald-500",
  chat_video: "bg-purple-500",
  chat_file: "bg-slate-500",
  support_receipt: "bg-amber-500",
  refund_receipt: "bg-orange-500",
  other: "bg-slate-400",
};

export default function AdminPage() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const [tab, setTab] = useState("dashboard");
  const [stats, setStats] = useState(null);
  const [payments, setPayments] = useState([]);
  const [reports, setReports] = useState([]);
  const [users, setUsers] = useState([]);
  const [period, setPeriod] = useState("daily");
  const [mode, setMode] = useState("revenue");
  const [sbpPhoneInput, setSbpPhoneInput] = useState("");
  const [sbpMasked, setSbpMasked] = useState("");
  const [sbpRevealed, setSbpRevealed] = useState(null);
  const [pendingSubs, setPendingSubs] = useState([]);
  const [supportHistory, setSupportHistory] = useState([]);
  const [pendingCount, setPendingCount] = useState(0);
  const [modal, setModal] = useState(null); // {kind:'approve'|'reject', submission}
  const [coinAmt, setCoinAmt] = useState("");
  const [modalReason, setModalReason] = useState("");
  const [viewImg, setViewImg] = useState(null);
  // NEW: search / filter for payments
  const [payQ, setPayQ] = useState("");
  const [payStatus, setPayStatus] = useState("all");
  // NEW: deduct-coins + moderation actions
  const [deductTarget, setDeductTarget] = useState(null);
  const [deductAmt, setDeductAmt] = useState("");
  const [deductReason, setDeductReason] = useState("");
  const [modAction, setModAction] = useState(null); // { kind:'warn'|'ban'|'deactivate', user_id, user_name }
  const [modReason, setModReason] = useState("");
  const [modDays, setModDays] = useState(7);
  // NEW: legal docs
  const [legal, setLegal] = useState([]);
  const [legalEdit, setLegalEdit] = useState(null); // {slug,title,body,isNew}
  // NEW: GridFS storage widget
  const [storage, setStorage] = useState(null);
  const [cleanupLog, setCleanupLog] = useState([]);
  const [cleaning, setCleaning] = useState(false);

  useEffect(() => {
    if (!user) return;
    if (!user.is_admin) { nav("/home"); return; }
    load();
    // Auto-refresh admin data every 10s so new pending receipts appear live
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, [user, nav]);

  const load = async () => {
    try {
      const [s, p, r, u, cfg, pend, hist, cnt] = await Promise.all([
        api.get("/admin/stats"),
        api.get("/admin/payments"),
        api.get("/admin/reports"),
        api.get("/admin/users"),
        api.get("/admin/settings"),
        api.get("/admin/support/pending"),
        api.get("/admin/support/history"),
        api.get("/admin/support/pending-count"),
      ]);
      setStats(s.data); setPayments(p.data); setReports(r.data); setUsers(u.data);
      setSbpMasked(cfg.data?.sbp_phone_masked || "");
      setSbpPhoneInput(""); setSbpRevealed(null);
      setPendingSubs(pend.data); setSupportHistory(hist.data);
      setPendingCount(cnt.data?.count || 0);
      // Legal docs — best-effort, don't fail whole load if endpoint absent
      try { const l = await api.get("/admin/legal"); setLegal(l.data || []); } catch { /* noop */ }
      // Storage usage — best-effort
      try { const st = await api.get("/admin/storage"); setStorage(st.data || null); } catch { /* noop */ }
      try { const cl = await api.get("/admin/storage/cleanup-log"); setCleanupLog(cl.data || []); } catch { /* noop */ }
    } catch (e) { toast.error("Требуются права администратора"); nav("/home"); }
  };

  // ─── Storage cleanup (manual trigger) ───────────────────────────────
  const runCleanup = async () => {
    if (!window.confirm("Удалить осиротевшие файлы старше 7 дней?")) return;
    setCleaning(true);
    try {
      const { data } = await api.post("/admin/storage/cleanup");
      toast.success(`Очистка завершена: удалено ${data.deleted_files} файлов, освобождено ${fmtBytes(data.freed_bytes)}`);
      const [st, cl] = await Promise.all([api.get("/admin/storage"), api.get("/admin/storage/cleanup-log")]);
      setStorage(st.data); setCleanupLog(cl.data || []);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Ошибка очистки");
    } finally { setCleaning(false); }
  };

  // ─── Deduct coins ───────────────────────────────────────────────────
  const submitDeduct = async () => {
    const coins = parseInt(deductAmt, 10);
    if (!coins || coins <= 0) return toast.error("Введите положительное число монет");
    if (!deductReason.trim()) return toast.error("Причина обязательна");
    if (!window.confirm(`Списать ${coins} монет у ${deductTarget.name}?`)) return;
    try {
      const { data } = await api.post("/admin/users/deduct-coins", { user_id: deductTarget.user_id, coins, reason: deductReason.trim() });
      toast.success(`✅ Списано ${data.deducted} · Баланс: ${data.new_balance}`);
      setDeductTarget(null); setDeductAmt(""); setDeductReason(""); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Ошибка"); }
  };

  // ─── Moderation (warn / ban7 / deactivate) ──────────────────────────
  const submitModAction = async () => {
    if (!modAction) return;
    if (!modReason.trim()) return toast.error("Причина обязательна");
    const { kind, user_id } = modAction;
    const url = kind === "warn" ? `/admin/users/${user_id}/warn`
      : kind === "ban" ? `/admin/users/${user_id}/ban7`
      : `/admin/users/${user_id}/deactivate-permanent`;
    const body = { reason: modReason.trim(), days: modDays };
    if (kind === "deactivate" && !window.confirm(`Навсегда деактивировать ${modAction.user_name}? Пользователь потеряет доступ.`)) return;
    try {
      await api.post(url, body);
      toast.success(kind === "warn" ? "⚠️ Предупреждение отправлено" : kind === "ban" ? `🚫 Заблокирован на ${modDays} дн.` : "🛑 Аккаунт деактивирован");
      setModAction(null); setModReason(""); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Ошибка"); }
  };

  // ─── Legal docs ─────────────────────────────────────────────────────
  const saveLegal = async () => {
    if (!legalEdit) return;
    const { slug, title, body, isNew } = legalEdit;
    if (!/^[a-z0-9_-]+$/.test(slug)) return toast.error("Slug: a-z 0-9 - _");
    if (!title.trim() || !body.trim()) return toast.error("Заполните все поля");
    try {
      if (isNew) await api.post("/admin/legal", { slug, title, body });
      else await api.put(`/admin/legal/${slug}`, { slug, title, body });
      toast.success("Сохранено"); setLegalEdit(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Ошибка"); }
  };
  const removeLegal = async (slug) => {
    if (!window.confirm(`Удалить документ "${slug}"?`)) return;
    try { await api.delete(`/admin/legal/${slug}`); toast.success("Удалено"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Ошибка"); }
  };

  const openApprove = (s) => { setModal({ kind: "approve", submission: s }); setCoinAmt(""); setModalReason(""); };
  const openReject = (s) => { setModal({ kind: "reject", submission: s }); setModalReason(""); };

  const doApprove = async () => {
    const coins = parseInt(coinAmt, 10);
    if (!coins || coins <= 0) return toast.error("Введите положительное число монет");
    if (!modalReason.trim()) return toast.error("Причина обязательна");
    if (!window.confirm(`Начислить ${coins} монет пользователю ${modal.submission.user_name}?`)) return;
    try {
      await api.post(`/admin/support/${modal.submission.submission_id}/approve`, { coins, reason: modalReason });
      toast.success(`✅ ${coins} монет начислено · Premium активирован`);
      setModal(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Ошибка"); }
  };

  const doReject = async () => {
    if (!modalReason.trim()) return toast.error("Причина обязательна");
    try {
      await api.post(`/admin/support/${modal.submission.submission_id}/reject`, { reason: modalReason });
      toast.success("Чек отклонён");
      setModal(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Ошибка"); }
  };

  const revealSbp = async () => {
    if (!window.confirm("Показать полный SBP номер? Это действие будет зарегистрировано в логах аудита.")) return;
    try {
      const { data } = await api.get("/admin/settings/reveal");
      setSbpRevealed(data.sbp_phone);
      // Auto-hide after 15 seconds for shoulder-surfing protection
      setTimeout(() => setSbpRevealed(null), 15000);
    } catch { toast.error("Не удалось получить номер"); }
  };

  const saveSbpPhone = async () => {
    if (!/^\+?\d{10,15}$/.test(sbpPhoneInput.replace(/[\s()-]/g, ""))) return toast.error("Неверный формат телефона");
    await api.put("/admin/settings", { sbp_phone: sbpPhoneInput.trim() });
    toast.success("SBP номер обновлён — изменения применятся ко всем будущим платежам");
    setSbpPhoneInput("");
    load();
  };

  const act = async (tx_id, action) => {
    const reason = action === "reject" ? window.prompt("Причина отказа:", "Платёж не найден") : null;
    if (action === "reject" && !reason) return;
    await api.post(`/admin/payments/${tx_id}`, { action, reason });
    toast.success(action === "approve" ? "Одобрено" : "Отклонено"); load();
  };
  const deactivate = async (uid) => {
    if (!window.confirm("Удалить пользователя навсегда?")) return;
    await api.post(`/admin/users/${uid}/deactivate`); toast.success("Пользователь удалён"); load();
  };

  const chartData = () => {
    if (!stats) return [];
    if (period === "daily") return stats.daily.map((c, i) => ({ label: `${i}:00`, count: c, revenue: stats.revenue_daily[i] }));
    if (period === "monthly") return stats.monthly.map((c, i) => ({ label: `-${29-i}д`, count: c, revenue: stats.revenue_monthly[i] }));
    return stats.yearly.map((c, i) => ({ label: ["Янв","Фев","Мар","Апр","Май","Июн","Июл","Авг","Сен","Окт","Ноя","Дек"][i], count: c, revenue: stats.revenue_yearly[i] }));
  };

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border bg-card/50 backdrop-blur px-6 py-4 flex items-center gap-3">
        <Shield className="w-6 h-6 text-primary" />
        <h1 className="font-display font-black text-2xl">Lovreski Admin</h1>
        <div className="ml-auto flex gap-2">
          <button onClick={() => nav("/home")} className="text-sm px-3 py-1.5 rounded-full bg-muted">← В приложение</button>
          <button onClick={async () => { await logout(); nav("/"); }} className="text-sm px-3 py-1.5 rounded-full bg-muted"><LogOut className="w-4 h-4 inline" /> Выход</button>
        </div>
      </header>

      <div className="max-w-6xl mx-auto p-6">
        <div className="flex gap-2 mb-6 bg-muted p-1 rounded-full w-fit">
          {[{k:"dashboard",l:"Дашборд"},{k:"support",l:"Verification",badge:pendingCount},{k:"payments",l:"Платежи"},{k:"refunds",l:"Refund Requests"},{k:"reports",l:"Жалобы"},{k:"users",l:"Пользователи"},{k:"legal",l:"Правовые"},{k:"settings",l:"Настройки"}].map(t => (
            <button key={t.k} data-testid={`admin-tab-${t.k}`} onClick={() => setTab(t.k)} className={`relative px-5 py-2 rounded-full font-semibold text-sm ${tab === t.k ? "bg-card shadow" : "text-muted-foreground"}`}>
              {t.l}
              {t.badge > 0 && (
                <span data-testid="pending-badge" className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 rounded-full bg-rose-500 text-white text-[10px] font-bold flex items-center justify-center">
                  {t.badge}
                </span>
              )}
            </button>
          ))}
        </div>

        {tab === "dashboard" && stats && (
          <div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
              <Stat title="Всего пользователей" value={stats.total_users} icon={Users} />
              <Stat title="Premium" value={stats.premium_users} icon={Crown} accent />
              <Stat title="Выручка" value={`${stats.revenue.toLocaleString("ru")} ₽`} icon={TrendingUp} />
              <Stat title="Ожидают" value={stats.pending} icon={Clock} />
              <Stat title="Одобрено в этом месяце" value={stats.approved_month} icon={Check} />
            </div>

            {/* GridFS Storage widget */}
            {storage && (
              <div className="bg-card border border-border rounded-2xl p-5 mb-6" data-testid="admin-storage-widget">
                <div className="flex flex-wrap items-center justify-between mb-3">
                  <h3 className="font-display font-bold text-lg flex items-center gap-2">
                    <Database className="w-5 h-5" /> Хранилище (GridFS)
                  </h3>
                  <span className="text-sm text-muted-foreground" data-testid="admin-storage-total">
                    Всего: <strong>{fmtBytes(storage.total_bytes)}</strong> · {storage.total_files} файлов
                  </span>
                </div>
                {/* Stacked bar */}
                <div className="flex h-3 w-full rounded-full overflow-hidden mb-4" aria-hidden="true">
                  {storage.by_kind.map((k) => (
                    <div
                      key={k.kind}
                      title={`${KIND_LABELS[k.kind] || k.kind} — ${fmtBytes(k.bytes)}`}
                      style={{ width: storage.total_bytes ? `${(k.bytes / storage.total_bytes) * 100}%` : 0 }}
                      className={`${KIND_COLORS[k.kind] || KIND_COLORS.other} transition-all`}
                    />
                  ))}
                </div>
                {/* Per-kind table */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-2 text-sm">
                  {storage.by_kind.map((k) => (
                    <div key={k.kind} data-testid={`storage-row-${k.kind}`} className="flex items-center justify-between py-1 border-b border-border/50">
                      <span className="flex items-center gap-2 text-muted-foreground">
                        <span className={`w-2 h-2 rounded-full ${KIND_COLORS[k.kind] || KIND_COLORS.other}`} />
                        {KIND_LABELS[k.kind] || k.kind}
                      </span>
                      <span className="text-foreground">
                        <span className="text-muted-foreground">{k.files}</span>
                        <span className="mx-1.5 text-muted-foreground">·</span>
                        <span className="font-medium">{fmtBytes(k.bytes)}</span>
                      </span>
                    </div>
                  ))}
                </div>
                {storage.by_kind.length === 0 && (
                  <p className="text-sm text-muted-foreground text-center py-4">Файлов пока нет.</p>
                )}

                {/* Cleanup controls + last run */}
                <div className="mt-4 pt-3 border-t border-border/60 flex flex-wrap items-center justify-between gap-3">
                  <div className="text-xs text-muted-foreground" data-testid="storage-last-run">
                    {cleanupLog.length > 0 ? (() => {
                      const r = cleanupLog[0];
                      const dt = new Date(r.started_at);
                      return <>Последняя очистка: {dt.toLocaleDateString("ru")} {dt.toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit" })} · удалено {r.deleted_files} · освобождено {fmtBytes(r.freed_bytes)}</>;
                    })() : "Автоочистка: ежедневно в 03:00 UTC (файлы старше 7 дней)"}
                  </div>
                  <button
                    data-testid="btn-storage-cleanup"
                    onClick={runCleanup}
                    disabled={cleaning}
                    className="px-4 py-1.5 rounded-full text-xs font-semibold bg-muted hover:bg-muted/70 text-foreground disabled:opacity-50 flex items-center gap-1.5"
                  >
                    <Trash2 className="w-3.5 h-3.5" /> {cleaning ? "Очистка..." : "Очистить сейчас"}
                  </button>
                </div>
              </div>
            )}

            <div className="bg-card border border-border rounded-2xl p-5">
              <div className="flex flex-wrap gap-3 items-center justify-between mb-4">
                <h3 className="font-display font-bold text-lg">Аналитика</h3>
                <div className="flex gap-2">
                  <div className="flex bg-muted rounded-full p-1">
                    {["daily","monthly","yearly"].map(p => (
                      <button key={p} onClick={() => setPeriod(p)} className={`px-3 py-1 text-xs font-semibold rounded-full ${period === p ? "bg-card shadow" : "text-muted-foreground"}`}>{{daily:"День",monthly:"Месяц",yearly:"Год"}[p]}</button>
                    ))}
                  </div>
                  <div className="flex bg-muted rounded-full p-1">
                    <button onClick={() => setMode("revenue")} className={`px-3 py-1 text-xs font-semibold rounded-full ${mode === "revenue" ? "bg-card shadow" : "text-muted-foreground"}`}>💰 Выручка</button>
                    <button onClick={() => setMode("count")} className={`px-3 py-1 text-xs font-semibold rounded-full ${mode === "count" ? "bg-card shadow" : "text-muted-foreground"}`}>👥 Кол-во</button>
                  </div>
                </div>
              </div>
              <ResponsiveContainer width="100%" height={280}>
                {period === "monthly" ? (
                  <LineChart data={chartData()}>
                    <CartesianGrid strokeOpacity={0.15} />
                    <XAxis dataKey="label" fontSize={11} />
                    <YAxis fontSize={11} />
                    <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))" }} />
                    <Line dataKey={mode} stroke="hsl(var(--primary))" strokeWidth={3} dot={{ r: 4 }} />
                  </LineChart>
                ) : (
                  <BarChart data={chartData()}>
                    <CartesianGrid strokeOpacity={0.15} />
                    <XAxis dataKey="label" fontSize={11} />
                    <YAxis fontSize={11} />
                    <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))" }} />
                    <Bar dataKey={mode} fill="hsl(var(--primary))" radius={[8,8,0,0]} />
                  </BarChart>
                )}
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {tab === "payments" && (
          <div>
            <div className="flex flex-wrap gap-2 mb-4 items-center">
              <div className="flex bg-muted rounded-full p-1">
                {[{k:"all",l:"Все"},{k:"pending",l:"Ожидают"},{k:"approved",l:"Одобрены"},{k:"rejected",l:"Отклонены"}].map((s) => (
                  <button key={s.k} data-testid={`pay-filter-${s.k}`} onClick={() => setPayStatus(s.k)}
                    className={`px-4 py-1.5 rounded-full text-xs font-semibold ${payStatus === s.k ? "bg-card shadow" : "text-muted-foreground"}`}>
                    {s.l}
                  </button>
                ))}
              </div>
              <div className="flex items-center gap-2 bg-muted rounded-full px-3 py-1.5 flex-1 max-w-xs">
                <SearchIcon className="w-4 h-4 text-muted-foreground" />
                <input data-testid="pay-search" value={payQ} onChange={(e) => setPayQ(e.target.value)} placeholder="Имя или email…"
                  className="flex-1 bg-transparent outline-none text-sm" />
              </div>
            </div>
            <div className="bg-card border border-border rounded-2xl overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-muted text-left">
                  <tr><th className="p-3">Пользователь</th><th className="p-3">Пакет</th><th className="p-3">Сумма</th><th className="p-3">Дата</th><th className="p-3">Статус</th><th className="p-3">Действие</th></tr>
                </thead>
                <tbody>
                  {payments
                    .filter((t) => payStatus === "all" || t.status === payStatus)
                    .filter((t) => {
                      const q = payQ.trim().toLowerCase();
                      if (!q) return true;
                      return (t.user_name || "").toLowerCase().includes(q) || (t.user_email || "").toLowerCase().includes(q);
                    })
                    .map((t) => (
                    <tr key={t.tx_id} data-testid={`payment-${t.tx_id}`} className="border-t border-border">
                      <td className="p-3 flex items-center gap-2">
                        {t.user_photo && <img src={t.user_photo} alt="" className="w-8 h-8 rounded-full object-cover" />}
                        <span>{t.user_name}<br /><span className="text-xs text-muted-foreground">{t.user_email}</span></span>
                      </td>
                      <td className="p-3">{t.coins} 💰</td>
                      <td className="p-3 font-bold">{t.amount_rub} ₽</td>
                      <td className="p-3 text-xs">{new Date(t.created_at).toLocaleDateString("ru")}</td>
                      <td className="p-3"><span className={`text-xs px-2 py-1 rounded-full ${t.status === "approved" ? "bg-emerald-500/15 text-emerald-500" : t.status === "rejected" ? "bg-rose-500/15 text-rose-500" : "bg-amber-500/15 text-amber-500"}`}>{t.status}</span></td>
                      <td className="p-3">
                        {t.status === "pending" && (
                          <div className="flex gap-1">
                            <button data-testid={`approve-${t.tx_id}`} onClick={() => act(t.tx_id, "approve")} className="p-1.5 rounded bg-emerald-500 text-white"><Check className="w-4 h-4" /></button>
                            <button data-testid={`reject-${t.tx_id}`} onClick={() => act(t.tx_id, "reject")} className="p-1.5 rounded bg-rose-500 text-white"><X className="w-4 h-4" /></button>
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                  {payments.length === 0 && <tr><td colSpan={6} className="p-8 text-center text-muted-foreground">Нет платежей</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {tab === "reports" && (
          <div className="grid gap-3">
            {reports.map(r => (
              <div key={r.target_user} data-testid={`report-${r.target_user}`} className="p-4 bg-card border border-border rounded-2xl">
                <div className="flex items-center gap-4">
                  <img src={r.user?.photos?.[0]} alt="" className="w-16 h-16 rounded-full object-cover" />
                  <div className="flex-1 min-w-0">
                    <p className="font-bold">{r.user?.name}, {r.user?.age}</p>
                    <p className="text-xs text-muted-foreground truncate">{r.user?.email || r.target_user}</p>
                    <p className="text-xs mt-0.5"><b>Жалоб: {r.count}</b> · {new Date(r.last).toLocaleDateString("ru")}</p>
                    <p className="text-xs mt-1 italic line-clamp-2">{r.reasons.slice(0, 3).join(" · ")}</p>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button data-testid={`report-view-${r.target_user}`} onClick={() => nav(`/u/${r.target_user}`)} className="btn-pill bg-muted text-xs !py-1.5 !px-3">👁 Профиль</button>
                  <button data-testid={`report-warn-${r.target_user}`} onClick={() => { setModAction({ kind: "warn", user_id: r.target_user, user_name: r.user?.name }); setModReason(r.reasons?.[0] || ""); }} className="btn-pill bg-amber-500 text-white text-xs !py-1.5 !px-3"><AlertTriangle className="w-3.5 h-3.5 mr-1" /> Предупредить</button>
                  <button data-testid={`report-ban-${r.target_user}`} onClick={() => { setModAction({ kind: "ban", user_id: r.target_user, user_name: r.user?.name }); setModDays(7); setModReason(r.reasons?.[0] || ""); }} className="btn-pill bg-orange-500 text-white text-xs !py-1.5 !px-3"><Ban className="w-3.5 h-3.5 mr-1" /> Бан 7 дн.</button>
                  <button data-testid={`report-deactivate-${r.target_user}`} onClick={() => { setModAction({ kind: "deactivate", user_id: r.target_user, user_name: r.user?.name }); setModReason(r.reasons?.[0] || ""); }} className="btn-pill bg-rose-500 text-white text-xs !py-1.5 !px-3"><UserX className="w-3.5 h-3.5 mr-1" /> Навсегда</button>
                </div>
              </div>
            ))}
            {reports.length === 0 && <p className="text-center text-muted-foreground py-10">Нет жалоб</p>}
          </div>
        )}

        {tab === "users" && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {users.map(u => (
              <div key={u.user_id} data-testid={`user-card-${u.user_id}`} className="p-3 bg-card border border-border rounded-2xl">
                <img src={u.photos?.[0]} className="w-full aspect-square rounded-xl object-cover" alt="" />
                <p className="font-bold text-sm mt-2">{u.name}, {u.age}</p>
                <p className="text-xs text-muted-foreground">{u.city} · 💰 {u.coins ?? 0}</p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  <button data-testid={`deduct-${u.user_id}`} onClick={() => { setDeductTarget(u); setDeductAmt(""); setDeductReason(""); }} className="text-[10px] px-2 py-1 rounded-full bg-amber-500/15 text-amber-500 font-semibold"><MinusCircle className="w-3 h-3 inline mr-0.5" /> Списать</button>
                  <button onClick={() => { setModAction({ kind: "ban", user_id: u.user_id, user_name: u.name }); setModDays(7); setModReason(""); }} className="text-[10px] px-2 py-1 rounded-full bg-orange-500/15 text-orange-500 font-semibold">Бан</button>
                  <button onClick={() => { setModAction({ kind: "deactivate", user_id: u.user_id, user_name: u.name }); setModReason(""); }} className="text-[10px] px-2 py-1 rounded-full bg-rose-500/15 text-rose-500 font-semibold">Удалить</button>
                </div>
              </div>
            ))}
          </div>
        )}

        {tab === "legal" && (
          <div className="max-w-3xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-display font-bold text-lg">Правовые документы</h3>
              <button data-testid="legal-new" onClick={() => setLegalEdit({ slug: "", title: "", body: "", isNew: true })} className="btn-pill bg-primary text-primary-foreground text-sm !py-2"><Plus className="w-4 h-4 mr-1" /> Новый</button>
            </div>
            <div className="grid gap-2">
              {legal.length === 0 && <p className="text-sm text-muted-foreground text-center py-8">Документов пока нет</p>}
              {legal.map((d) => (
                <div key={d.slug} data-testid={`legal-${d.slug}`} className="p-3 rounded-xl bg-card border border-border flex items-center gap-3">
                  <FileText className="w-5 h-5 text-muted-foreground" />
                  <div className="flex-1 min-w-0">
                    <p className="font-semibold text-sm truncate">{d.title}</p>
                    <p className="text-[11px] text-muted-foreground">/{d.slug} · {new Date(d.updated_at).toLocaleDateString("ru")}</p>
                  </div>
                  <button data-testid={`legal-edit-${d.slug}`} onClick={() => setLegalEdit({ slug: d.slug, title: d.title, body: d.body, isNew: false })} className="p-2 rounded-full hover:bg-muted"><Pencil className="w-4 h-4" /></button>
                  <button data-testid={`legal-delete-${d.slug}`} onClick={() => removeLegal(d.slug)} className="p-2 rounded-full hover:bg-rose-500/10 text-rose-500"><Trash2 className="w-4 h-4" /></button>
                </div>
              ))}
            </div>
          </div>
        )}

        {tab === "support" && (
          <div className="space-y-3">
            <h3 className="font-display font-bold text-lg">Проверка чеков</h3>
            {pendingSubs.length === 0 && supportHistory.length === 0 && (
              <p className="text-center text-muted-foreground py-10">Нет заявок</p>
            )}
            {pendingSubs.map((s) => (
              <div key={s.submission_id} data-testid={`pending-${s.submission_id}`} className="p-4 rounded-2xl bg-card border border-border">
                <div className="flex gap-4">
                  <button onClick={() => setViewImg(s.receipt_data_url)} className="w-24 h-24 rounded-xl overflow-hidden bg-muted flex-shrink-0">
                    {s.receipt_data_url?.startsWith("data:image/") ? (
                      <img src={s.receipt_data_url} alt="receipt" className="w-full h-full object-cover" data-testid={`receipt-img-${s.submission_id}`} />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-xs text-muted-foreground">PDF</div>
                    )}
                  </button>
                  <div className="flex-1 min-w-0">
                    <p className="font-bold">{s.user_name} <span className="text-xs text-muted-foreground">({s.user_email})</span></p>
                    <p className="text-[11px] text-muted-foreground">ID: {s.user_id}</p>
                    <p className="text-[11px] text-muted-foreground">{new Date(s.created_at).toLocaleString("ru")}</p>
                    {s.message && <p className="text-xs mt-1 italic">"{s.message}"</p>}
                    {s.package_id && <p className="text-xs mt-1">Пакет: <b>{s.package_id}</b></p>}
                  </div>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <button data-testid={`btn-approve-${s.submission_id}`} onClick={() => openApprove(s)} className="btn-pill bg-emerald-500 text-white text-sm !py-2"><Check className="w-4 h-4 mr-1" /> Custom Coin Add</button>
                  <button data-testid={`btn-reject-${s.submission_id}`} onClick={() => openReject(s)} className="btn-pill bg-rose-500 text-white text-sm !py-2"><X className="w-4 h-4 mr-1" /> Отклонить</button>
                </div>
              </div>
            ))}
            {supportHistory.length > 0 && (
              <details className="mt-4">
                <summary className="text-sm font-semibold text-muted-foreground cursor-pointer">История ({supportHistory.length})</summary>
                <div className="mt-2 space-y-2">
                  {supportHistory.map((s) => (
                    <div key={s.submission_id} className="p-3 rounded-xl bg-muted/40 border border-border text-xs">
                      <div className="flex justify-between">
                        <span><b>{s.user_name}</b> · {new Date(s.created_at).toLocaleDateString("ru")}</span>
                        <span className={s.status === "verified" ? "text-emerald-500" : "text-rose-500"}>
                          {s.status === "verified" ? `✓ ${s.coins_added} 🪙` : `✗ ${s.reject_reason}`}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </details>
            )}
          </div>
        )}

        {tab === "refunds" && <RefundsTab />}

        {tab === "settings" && (
          <div className="max-w-lg space-y-6">
            <div className="p-5 rounded-2xl bg-card border border-border">
              <h3 className="font-display font-bold mb-1">SBP номер (Сбербанк)</h3>
              <p className="text-xs text-muted-foreground mb-3">
                Этот номер используется для приёма платежей через СБП. Он <b>зашифрован в базе данных</b> и никогда не отображается пользователям — ни на странице оплаты, ни в исходном коде.
                Пользователи оплачивают из <b>любого банка</b>, а деньги приходят только на Сбербанк по этому номеру.
              </p>

              {/* Current — masked, with explicit reveal */}
              <div className="p-3 rounded-xl bg-muted flex items-center justify-between">
                <div>
                  <p className="text-[10px] uppercase tracking-widest text-muted-foreground">Текущий номер</p>
                  <p data-testid="admin-sbp-current" className="font-display font-bold text-lg mt-1">
                    {sbpRevealed || sbpMasked || "—"}
                  </p>
                </div>
                <button
                  data-testid="admin-sbp-reveal"
                  onClick={revealSbp}
                  className="text-xs px-3 py-1.5 rounded-full bg-background border border-border hover:bg-muted"
                >
                  {sbpRevealed ? "Скрыть" : "👁 Показать"}
                </button>
              </div>

              {/* Update form */}
              <div className="mt-4">
                <label className="text-xs font-semibold text-muted-foreground">Новый номер</label>
                <div className="flex gap-2 mt-1">
                  <input
                    data-testid="admin-sbp-phone"
                    value={sbpPhoneInput}
                    onChange={(e) => setSbpPhoneInput(e.target.value)}
                    placeholder="+7XXXXXXXXXX"
                    className="flex-1 px-3 py-2 rounded-xl bg-muted outline-none border border-transparent focus:border-primary"
                  />
                  <button data-testid="admin-save-sbp" onClick={saveSbpPhone} disabled={!sbpPhoneInput.trim()} className="btn-pill bg-primary text-primary-foreground disabled:opacity-50">Сохранить</button>
                </div>
                <p className="text-[11px] text-muted-foreground mt-2">
                  ✅ Изменение применяется мгновенно ко всем будущим платежам. Перезапуск не требуется.
                </p>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Approve / Reject modal */}
      {modal && (
        <div data-testid="admin-modal" className="fixed inset-0 z-[80] flex items-center justify-center bg-black/70 backdrop-blur-sm p-4" onClick={() => setModal(null)}>
          <div onClick={(e) => e.stopPropagation()} className="w-full max-w-md bg-card border border-border rounded-2xl shadow-2xl p-6">
            {modal.kind === "approve" ? (
              <>
                <h3 className="font-display font-black text-lg">💰 Custom Coin Add</h3>
                <p className="text-xs text-muted-foreground mt-1">Пользователь: <b>{modal.submission.user_name}</b> ({modal.submission.user_email})</p>
                <p className="text-xs text-muted-foreground">Текущий баланс: <b>{modal.submission._currentBalance ?? "—"}</b> 🪙</p>
                <div className="mt-4 space-y-3">
                  <div>
                    <label className="text-xs font-semibold">Сумма монет (число):</label>
                    <input
                      data-testid="modal-coin-amount"
                      type="number" min="1" step="1"
                      value={coinAmt} onChange={(e) => setCoinAmt(e.target.value.replace(/[^\d]/g, ""))}
                      className="mt-1 w-full px-3 py-2 rounded-xl bg-muted outline-none border border-transparent focus:border-primary text-lg font-bold"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-semibold">Причина (обязательно):</label>
                    <input
                      data-testid="modal-reason"
                      value={modalReason} onChange={(e) => setModalReason(e.target.value)}
                      placeholder="e.g. Payment verified"
                      className="mt-1 w-full px-3 py-2 rounded-xl bg-muted outline-none border border-transparent focus:border-primary"
                    />
                  </div>
                  {coinAmt > 0 && (
                    <div data-testid="modal-preview" className="p-3 rounded-xl bg-primary/10 border border-primary/30 text-sm">
                      Предпросмотр: <b>+ {coinAmt}</b> 🪙 · Premium будет активирован
                    </div>
                  )}
                </div>
                <div className="mt-5 flex gap-2">
                  <button onClick={() => setModal(null)} className="flex-1 btn-pill bg-muted">Отмена</button>
                  <button data-testid="modal-confirm-approve" onClick={doApprove} className="flex-1 btn-pill bg-emerald-500 text-white">✅ Confirm & Add Coins</button>
                </div>
              </>
            ) : (
              <>
                <h3 className="font-display font-black text-lg text-rose-500">❌ Отклонить чек</h3>
                <p className="text-xs text-muted-foreground mt-1">Пользователь: <b>{modal.submission.user_name}</b></p>
                <div className="mt-4 space-y-2">
                  {["Blurry/unclear receipt","Wrong amount transferred","Fake/edited receipt","Payment not received in account"].map((r) => (
                    <button key={r} data-testid={`reject-reason-${r.replace(/[^a-z]/gi,'_')}`} onClick={() => setModalReason(r)} className={`w-full text-left px-3 py-2 rounded-xl border ${modalReason === r ? "border-rose-500 bg-rose-500/10" : "border-border"}`}>
                      {r}
                    </button>
                  ))}
                  <input
                    data-testid="modal-reject-other"
                    placeholder="Другое..."
                    value={modalReason.startsWith("Other:") ? modalReason.slice(6) : (["Blurry/unclear receipt","Wrong amount transferred","Fake/edited receipt","Payment not received in account"].includes(modalReason) ? "" : modalReason)}
                    onChange={(e) => setModalReason("Other: " + e.target.value)}
                    className="w-full px-3 py-2 rounded-xl bg-muted outline-none border border-transparent focus:border-primary"
                  />
                </div>
                <div className="mt-5 flex gap-2">
                  <button onClick={() => setModal(null)} className="flex-1 btn-pill bg-muted">Отмена</button>
                  <button data-testid="modal-confirm-reject" onClick={doReject} className="flex-1 btn-pill bg-rose-500 text-white">Reject</button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* Fullscreen receipt viewer */}
      {viewImg && (
        <div className="fixed inset-0 z-[90] bg-black/95 flex items-center justify-center p-4" onClick={() => setViewImg(null)}>
          <img src={viewImg} alt="receipt" className="max-w-full max-h-full object-contain" />
          <button className="absolute top-4 right-4 w-10 h-10 rounded-full bg-white/20 text-white flex items-center justify-center">✕</button>
        </div>
      )}

      {/* Deduct-coins modal */}
      {deductTarget && (
        <div data-testid="deduct-modal" className="fixed inset-0 z-[80] flex items-center justify-center bg-black/70 backdrop-blur-sm p-4" onClick={() => setDeductTarget(null)}>
          <div onClick={(e) => e.stopPropagation()} className="w-full max-w-md bg-card border border-border rounded-2xl shadow-2xl p-6">
            <h3 className="font-display font-black text-lg flex items-center gap-2"><MinusCircle className="w-5 h-5 text-amber-500" /> Списать монеты</h3>
            <p className="text-xs text-muted-foreground mt-1">Пользователь: <b>{deductTarget.name}</b> · Баланс: <b>{deductTarget.coins ?? 0}</b> 🪙</p>
            <div className="mt-4 space-y-3">
              <input data-testid="deduct-amount" type="number" min="1" step="1" value={deductAmt} onChange={(e) => setDeductAmt(e.target.value.replace(/[^\d]/g, ""))} placeholder="Сумма монет" className="w-full px-3 py-2 rounded-xl bg-muted outline-none border border-transparent focus:border-primary text-lg font-bold" />
              <textarea data-testid="deduct-reason" rows={3} value={deductReason} onChange={(e) => setDeductReason(e.target.value)} placeholder="Причина (обязательно)" className="w-full px-3 py-2 rounded-xl bg-muted outline-none border border-transparent focus:border-primary text-sm resize-none" />
            </div>
            <div className="mt-5 flex gap-2">
              <button data-testid="deduct-cancel" onClick={() => setDeductTarget(null)} className="flex-1 btn-pill bg-muted">Отмена</button>
              <button data-testid="deduct-submit" onClick={submitDeduct} className="flex-1 btn-pill bg-amber-500 text-white font-bold">Списать</button>
            </div>
          </div>
        </div>
      )}

      {/* Moderation-action modal (warn / ban / deactivate) */}
      {modAction && (
        <div data-testid="mod-modal" className="fixed inset-0 z-[80] flex items-center justify-center bg-black/70 backdrop-blur-sm p-4" onClick={() => setModAction(null)}>
          <div onClick={(e) => e.stopPropagation()} className="w-full max-w-md bg-card border border-border rounded-2xl shadow-2xl p-6">
            <h3 className="font-display font-black text-lg flex items-center gap-2">
              {modAction.kind === "warn" && <><AlertTriangle className="w-5 h-5 text-amber-500" /> Предупреждение</>}
              {modAction.kind === "ban" && <><Ban className="w-5 h-5 text-orange-500" /> Временный бан</>}
              {modAction.kind === "deactivate" && <><UserX className="w-5 h-5 text-rose-500" /> Деактивация навсегда</>}
            </h3>
            <p className="text-xs text-muted-foreground mt-1">Пользователь: <b>{modAction.user_name}</b></p>
            <div className="mt-4 space-y-3">
              {modAction.kind === "ban" && (
                <div>
                  <label className="text-xs font-semibold">Длительность (дней):</label>
                  <input data-testid="mod-days" type="number" min="1" max="365" value={modDays} onChange={(e) => setModDays(parseInt(e.target.value || "7", 10))} className="mt-1 w-full px-3 py-2 rounded-xl bg-muted outline-none border border-transparent focus:border-primary" />
                </div>
              )}
              <div>
                <label className="text-xs font-semibold">Причина (обязательно):</label>
                <textarea data-testid="mod-reason" rows={3} value={modReason} onChange={(e) => setModReason(e.target.value)} className="mt-1 w-full px-3 py-2 rounded-xl bg-muted outline-none border border-transparent focus:border-primary text-sm resize-none" />
              </div>
            </div>
            <div className="mt-5 flex gap-2">
              <button data-testid="mod-cancel" onClick={() => setModAction(null)} className="flex-1 btn-pill bg-muted">Отмена</button>
              <button
                data-testid="mod-submit"
                onClick={submitModAction}
                className={`flex-1 btn-pill text-white font-bold ${modAction.kind === "warn" ? "bg-amber-500" : modAction.kind === "ban" ? "bg-orange-500" : "bg-rose-500"}`}
              >
                Подтвердить
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Legal editor modal */}
      {legalEdit && (
        <div data-testid="legal-modal" className="fixed inset-0 z-[80] flex items-center justify-center bg-black/70 backdrop-blur-sm p-4" onClick={() => setLegalEdit(null)}>
          <div onClick={(e) => e.stopPropagation()} className="w-full max-w-2xl bg-card border border-border rounded-2xl shadow-2xl p-6 flex flex-col max-h-[85vh]">
            <h3 className="font-display font-black text-lg flex items-center gap-2"><FileText className="w-5 h-5" /> {legalEdit.isNew ? "Новый документ" : "Редактировать"}</h3>
            <div className="mt-4 space-y-3 flex-1 overflow-y-auto">
              <div>
                <label className="text-xs font-semibold">Slug (URL, латиница):</label>
                <input data-testid="legal-slug" value={legalEdit.slug} onChange={(e) => setLegalEdit({ ...legalEdit, slug: e.target.value.toLowerCase() })} disabled={!legalEdit.isNew} placeholder="terms" className="mt-1 w-full px-3 py-2 rounded-xl bg-muted outline-none border border-transparent focus:border-primary disabled:opacity-60" />
              </div>
              <div>
                <label className="text-xs font-semibold">Название:</label>
                <input data-testid="legal-title" value={legalEdit.title} onChange={(e) => setLegalEdit({ ...legalEdit, title: e.target.value })} placeholder="Пользовательское соглашение" className="mt-1 w-full px-3 py-2 rounded-xl bg-muted outline-none border border-transparent focus:border-primary" />
              </div>
              <div>
                <label className="text-xs font-semibold">Текст (Markdown):</label>
                <textarea data-testid="legal-body" rows={14} value={legalEdit.body} onChange={(e) => setLegalEdit({ ...legalEdit, body: e.target.value })} className="mt-1 w-full px-3 py-2 rounded-xl bg-muted outline-none border border-transparent focus:border-primary text-sm resize-none font-mono" />
              </div>
            </div>
            <div className="mt-4 flex gap-2 shrink-0">
              <button data-testid="legal-cancel" onClick={() => setLegalEdit(null)} className="flex-1 btn-pill bg-muted">Отмена</button>
              <button data-testid="legal-save" onClick={saveLegal} className="flex-1 btn-pill bg-primary text-primary-foreground font-bold">Сохранить</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const Stat = ({ title, value, icon: Icon, accent }) => (
  <div className={`p-5 rounded-2xl border border-border ${accent ? "bg-gradient-to-br from-primary to-primary/70 text-primary-foreground" : "bg-card"}`}>
    <div className="flex items-center justify-between">
      <p className={`text-xs uppercase tracking-widest ${accent ? "opacity-80" : "text-muted-foreground"}`}>{title}</p>
      <Icon className="w-5 h-5 opacity-70" />
    </div>
    <p className="font-display font-black text-2xl mt-2">{value}</p>
  </div>
);

function RefundsTab() {
  const [items, setItems] = useState([]);
  const [viewImg, setViewImg] = useState(null);
  const load = async () => {
    try { const { data } = await api.get("/admin/refunds"); setItems(data); } catch { toast.error("Ошибка"); }
  };
  useEffect(() => { load(); }, []);
  const decide = async (id, action) => {
    const reason = action === "reject" ? window.prompt("Причина отказа:", "") : (window.prompt("Комментарий (необязательно):") || "");
    if (action === "reject" && !reason) return;
    try { await api.post(`/admin/refunds/${id}/decide`, { action, reason }); toast.success("Обновлено"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Ошибка"); }
  };
  return (
    <div className="space-y-3">
      <h3 className="font-display font-bold text-lg">Refund Requests</h3>
      {items.length === 0 && <p className="text-center text-muted-foreground py-10">Нет заявок</p>}
      {items.map((r) => (
        <div key={r.refund_id} data-testid={`refund-${r.refund_id}`} className="p-4 rounded-2xl bg-card border border-border">
          <div className="flex gap-4">
            {r.receipt_data_url && (
              <button onClick={() => setViewImg(r.receipt_data_url)} className="w-24 h-24 rounded-xl overflow-hidden bg-muted flex-shrink-0">
                <img src={r.receipt_data_url} alt="" className="w-full h-full object-cover" />
              </button>
            )}
            <div className="flex-1 min-w-0">
              <p className="font-bold">{r.full_name}</p>
              <p className="text-xs text-muted-foreground">{r.email}</p>
              <p className="text-xs mt-1">{r.reason}</p>
              <p className="text-[11px] text-muted-foreground mt-1">{new Date(r.created_at).toLocaleString("ru")}</p>
            </div>
            <span className={`text-xs font-bold px-2 py-1 rounded-full h-fit ${r.status === "approved" ? "bg-emerald-500/15 text-emerald-500" : r.status === "rejected" ? "bg-rose-500/15 text-rose-500" : "bg-amber-500/15 text-amber-500"}`}>{r.status}</span>
          </div>
          {r.status === "pending" && (
            <div className="mt-3 grid grid-cols-2 gap-2">
              <button onClick={() => decide(r.refund_id, "approve")} className="btn-pill bg-emerald-500 text-white text-sm !py-2">✅ Approve</button>
              <button onClick={() => decide(r.refund_id, "reject")} className="btn-pill bg-rose-500 text-white text-sm !py-2">❌ Reject</button>
            </div>
          )}
        </div>
      ))}
      {viewImg && (
        <div className="fixed inset-0 z-[90] bg-black/95 flex items-center justify-center p-4" onClick={() => setViewImg(null)}>
          <img src={viewImg} alt="" className="max-w-full max-h-full object-contain" />
        </div>
      )}
    </div>
  );
}
