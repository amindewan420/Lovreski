import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { MobileShell } from "@/components/lovreski/Shell";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ChevronRight, User, Search, Crown, Bell, Languages, FileText, Download, Shield, LogOut } from "lucide-react";

const LEGAL = {
  payment: { title: "Правила оплаты", body: "Все платежи осуществляются через СБП (Сбербанк). После оплаты запрос обрабатывается администратором в течение 24 часов. При успешном подтверждении монеты и Premium активируются автоматически." },
  support: { title: "Поддержка", body: "Свяжитесь с нами: support@lovreski.ru. Время ответа: 24 часа. Работаем ежедневно 09:00–21:00 МСК." },
  security: { title: "Безопасность", body: "Все переписки защищены сквозным шифрованием. Мы никогда не передаём ваши данные третьим лицам. Не сообщайте свои данные незнакомцам." },
  refund: { title: "Возврат средств", body: "Возврат возможен в течение 14 дней с момента покупки, если монеты не были использованы. Обратитесь в поддержку с чеком СБП." },
};

export default function SettingsPage() {
  const { user, refresh, logout } = useAuth();
  const nav = useNavigate();
  const [section, setSection] = useState(null);
  const [form, setForm] = useState({});
  const [installed, setInstalled] = useState(false);

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
        <div className="p-4 text-sm leading-relaxed whitespace-pre-wrap">{l.body}</div>
      </MobileShell>
    );
  }

  return (
    <MobileShell>
      <header className="sticky top-0 z-40 bg-background/85 backdrop-blur-xl px-4 pt-4 pb-3 border-b border-border/50 flex items-center gap-2">
        <button onClick={() => nav(-1)} className="text-sm text-muted-foreground">← Назад</button>
        <h1 className="font-display font-black text-xl">Настройки</h1>
      </header>

      <div className="p-4 space-y-6">
        <Section title="Личная информация" icon={User}>
          <Row label="Имя"><input value={form.name || ""} onChange={(e) => setForm({ ...form, name: e.target.value })} onBlur={() => save({ name: form.name })} className="bg-transparent text-right outline-none" /></Row>
          <Row label="Пол">
            <select value={form.gender || "female"} onChange={(e) => { setForm({ ...form, gender: e.target.value }); save({ gender: e.target.value }); }} className="bg-transparent text-right outline-none">
              <option value="female">Женский</option><option value="male">Мужской</option>
            </select>
          </Row>
          <Row label="Дата рождения"><input type="date" value={form.dob || ""} onChange={(e) => { setForm({ ...form, dob: e.target.value }); save({ dob: e.target.value }); }} className="bg-transparent text-right outline-none" /></Row>
        </Section>

        <Section title="Поиск" icon={Search}>
          <Row label="Показывать">
            <select data-testid="show-me" value={form.show_me || "both"} onChange={(e) => { setForm({ ...form, show_me: e.target.value }); save({ show_me: e.target.value }); }} className="bg-transparent text-right outline-none">
              <option value="female">Девушек</option><option value="male">Парней</option><option value="both">Всех</option>
            </select>
          </Row>
          <Row label={`Возраст: ${form.age_min || 18}–${form.age_max || 60}`}>
            <div className="flex gap-1">
              <input type="number" min={18} max={80} value={form.age_min || 18} onChange={(e) => setForm({ ...form, age_min: +e.target.value })} onBlur={() => save({ age_min: form.age_min })} className="w-14 bg-muted rounded px-1 text-right" />
              <input type="number" min={18} max={80} value={form.age_max || 60} onChange={(e) => setForm({ ...form, age_max: +e.target.value })} onBlur={() => save({ age_max: form.age_max })} className="w-14 bg-muted rounded px-1 text-right" />
            </div>
          </Row>
          <Row label="Расстояние">
            <select value={form.distance_mode || "unlimited"} onChange={(e) => { setForm({ ...form, distance_mode: e.target.value }); save({ distance_mode: e.target.value }); }} className="bg-transparent text-right outline-none">
              <option value="limited">🏘️ Рядом</option><option value="unlimited">🌍 Весь мир</option>
            </select>
          </Row>
        </Section>

        <Section title="Premium & Монеты" icon={Crown}>
          <button data-testid="link-premium" onClick={() => nav("/premium")} className="w-full flex justify-between items-center py-2 text-sm">
            <span>Управление Premium</span><ChevronRight className="w-4 h-4" />
          </button>
        </Section>

        <Section title="Уведомления" icon={Bell}>
          {["messages","likes","matches","visits","who_liked"].map((k) => (
            <Row key={k} label={{messages:"Сообщения",likes:"Лайки",matches:"Матчи",visits:"Посещения",who_liked:"Кто лайкнул"}[k]}>
              <input type="checkbox" checked={form.notif_push?.[k] || false} onChange={(e) => { const np = { ...(form.notif_push||{}), [k]: e.target.checked }; setForm({ ...form, notif_push: np }); save({ notif_push: np }); }} className="accent-primary" />
            </Row>
          ))}
        </Section>

        <Section title="AI Перевод" icon={Languages}>
          <Row label="Авто-перевод в чате">
            <input data-testid="toggle-translate" type="checkbox" checked={form.auto_translate || false} onChange={(e) => { setForm({ ...form, auto_translate: e.target.checked }); save({ auto_translate: e.target.checked }); }} className="accent-primary" />
          </Row>
        </Section>

        <Section title="Правовая информация" icon={FileText}>
          {Object.entries(LEGAL).map(([k, v]) => (
            <button key={k} onClick={() => setSection(k)} className="w-full flex justify-between items-center py-2 text-sm">
              <span>{v.title}</span><ChevronRight className="w-4 h-4" />
            </button>
          ))}
        </Section>

        <button data-testid="btn-install" onClick={install} className="w-full btn-pill bg-primary text-primary-foreground"><Download className="w-4 h-4 mr-2" /> {installed ? "Установлено" : "Установить приложение"}</button>

        {user?.is_admin && (
          <button onClick={() => nav("/admin")} className="w-full btn-pill bg-foreground text-background"><Shield className="w-4 h-4 mr-2" /> Админ панель</button>
        )}
        <button onClick={async () => { await logout(); nav("/"); }} className="w-full btn-pill bg-muted"><LogOut className="w-4 h-4 mr-2" /> Выйти</button>
      </div>
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
