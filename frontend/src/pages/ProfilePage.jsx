import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { MobileShell } from "@/components/lovreski/Shell";
import { Settings, Coins, Crown, Pencil, LogOut, Shield, Camera, Sun, Moon } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useTheme } from "@/context/ThemeContext";
import { toast } from "sonner";

const INTERESTS_POOL = {
  "Романтика": ["Поцелуи","Объятия","Флирт","Ужин","Комплименты","Массаж","Романтические фильмы","Танцы"],
  "Общение": ["Путешествия","Шоппинг","Кемпинг","Музеи","Клубы","Друзья","Караоке","Искусство"],
  "Творчество": ["Фотография","Музыка","Дизайн","Макияж","Блог","Живопись"],
  "Активность": ["Бег","Йога","Фитнес","Прогулки","Альпинизм","Плавание","Верховая езда"],
  "Еда и напитки": ["Здоровое питание","Кофе","Чай","Вино","Острая еда"],
  "Спорт": ["Футбол","Баскетбол","Хоккей","Теннис"],
  "Дом": ["Кулинария","Настольные игры","Книги","Кино"],
  "Развитие": ["Онлайн-курсы","Психология","Медитация","IT","Языки"],
};

export default function ProfilePage() {
  const { user, refresh, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const nav = useNavigate();
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({});

  useEffect(() => { if (user) setForm({ ...user }); }, [user]);

  const save = async () => {
    const payload = {
      name: form.name, about: form.about, job: form.job, education: form.education,
      language: form.language, height: form.height, goal: form.goal, relationship: form.relationship,
      kids: form.kids, smoking: form.smoking, alcohol: form.alcohol, interests: form.interests, photos: form.photos,
    };
    try { await api.put("/profile", payload); await refresh(); setEditing(false); toast.success("Профиль обновлён"); }
    catch (e) { toast.error(e.response?.data?.detail || "Ошибка"); }
  };

  const addPhoto = async () => {
    const url = window.prompt("Вставьте URL фотографии:");
    if (!url) return;
    const next = [...(form.photos || []), url].slice(0, 4);
    setForm({ ...form, photos: next });
    await api.put("/profile", { photos: next });
    await refresh();
  };

  const toggleInterest = (i) => {
    const cur = form.interests || [];
    if (cur.includes(i)) setForm({ ...form, interests: cur.filter((x) => x !== i) });
    else if (cur.length < 10) setForm({ ...form, interests: [...cur, i] });
    else toast.error("Максимум 10");
  };

  if (!user) return null;
  const popularity = user.popularity || "medium";

  return (
    <MobileShell>
      <header className="sticky top-0 z-40 bg-background/85 backdrop-blur-xl px-4 pt-4 pb-3 flex justify-between items-center border-b border-border/50">
        <h1 className="font-display font-black text-2xl tracking-tight">Профиль</h1>
        <div className="flex gap-2">
          <button onClick={toggle} className="p-2 rounded-full bg-muted hover:bg-muted/70">{theme === "dark" ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}</button>
          <button data-testid="btn-settings" onClick={() => nav("/settings")} className="p-2 rounded-full bg-muted hover:bg-muted/70"><Settings className="w-5 h-5" /></button>
        </div>
      </header>

      <div className="px-4 pt-6 pb-6 text-center relative">
        <div className="relative w-32 h-32 mx-auto">
          <img
            src={form.photos?.[0] || `https://api.dicebear.com/9.x/avataaars/svg?seed=${user.user_id}`}
            className="w-full h-full rounded-full object-cover border-4 border-primary/30 shadow-xl shadow-primary/20"
            alt=""
          />
          <button data-testid="btn-add-photo" onClick={addPhoto} className="absolute bottom-0 right-0 w-10 h-10 rounded-full bg-primary text-primary-foreground flex items-center justify-center shadow-lg hover:scale-105 transition-transform duration-200">
            <Camera className="w-5 h-5" />
          </button>
        </div>
        <h2 className="mt-4 font-display font-black text-2xl">{user.name}, {new Date().getFullYear() - parseInt((user.dob || "2000-01-01").split("-")[0])}</h2>
        {user.city && <p className="text-sm text-muted-foreground">{user.city}</p>}
      </div>

      <div className="px-4 grid grid-cols-2 gap-3">
        <div className="p-4 rounded-2xl bg-card border border-border">
          <p className="text-xs text-muted-foreground uppercase tracking-wider mb-2">Популярность</p>
          <p className={`font-display font-black text-xl ${popularity === "high" ? "text-emerald-500" : popularity === "low" ? "text-amber-500" : "text-primary"}`}>
            {popularity === "high" ? "Высокая" : popularity === "low" ? "Низкая" : "Средняя"}
          </p>
        </div>
        <button data-testid="coin-card" onClick={() => nav("/premium")} className="p-4 rounded-2xl bg-gradient-to-br from-primary to-primary/70 text-primary-foreground text-left hover:scale-[1.02] transition-transform duration-200">
          <p className="text-xs uppercase tracking-wider opacity-80 flex items-center gap-1"><Coins className="w-3 h-3" /> Баланс</p>
          <p className="font-display font-black text-2xl mt-1">{user.coins || 0} 💰</p>
          <p className="text-xs mt-1 opacity-90">Пополнить →</p>
        </button>
      </div>

      {!user.is_premium && (
        <button data-testid="premium-cta" onClick={() => nav("/premium")} className="mx-4 mt-3 w-[calc(100%-2rem)] p-4 rounded-2xl bg-gradient-to-r from-accent to-amber-500 text-accent-foreground font-bold flex items-center justify-between hover:scale-[1.01] transition-transform duration-200">
          <span className="flex items-center gap-2"><Crown className="w-5 h-5" /> Активировать Premium</span>
          <span>→</span>
        </button>
      )}

      <div className="px-4 mt-6">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-display font-bold text-lg">О себе</h3>
          <button data-testid="btn-edit-profile" onClick={() => setEditing((v) => !v)} className="flex items-center gap-1 text-sm text-primary font-semibold">
            <Pencil className="w-4 h-4" /> {editing ? "Готово" : "Редактировать"}
          </button>
        </div>
        {editing ? (
          <div className="space-y-2 bg-card p-4 rounded-2xl border border-border">
            <input data-testid="edit-name" placeholder="Имя" value={form.name || ""} onChange={(e) => setForm({ ...form, name: e.target.value })} className="w-full px-3 py-2 rounded-lg bg-muted outline-none" />
            <textarea data-testid="edit-about" maxLength={500} placeholder="О себе (макс 500)" value={form.about || ""} onChange={(e) => setForm({ ...form, about: e.target.value })} rows={3} className="w-full px-3 py-2 rounded-lg bg-muted outline-none" />
            <input maxLength={80} placeholder="Работа" value={form.job || ""} onChange={(e) => setForm({ ...form, job: e.target.value })} className="w-full px-3 py-2 rounded-lg bg-muted outline-none" />
            <input maxLength={100} placeholder="Образование" value={form.education || ""} onChange={(e) => setForm({ ...form, education: e.target.value })} className="w-full px-3 py-2 rounded-lg bg-muted outline-none" />
            <input maxLength={50} placeholder="Языки" value={form.language || ""} onChange={(e) => setForm({ ...form, language: e.target.value })} className="w-full px-3 py-2 rounded-lg bg-muted outline-none" />
            <div>
              <label className="text-xs text-muted-foreground">Рост: {form.height || 170} см</label>
              <input type="range" min={60} max={250} value={form.height || 170} onChange={(e) => setForm({ ...form, height: parseInt(e.target.value) })} className="w-full accent-primary" />
            </div>
            <select value={form.goal || ""} onChange={(e) => setForm({ ...form, goal: e.target.value })} className="w-full px-3 py-2 rounded-lg bg-muted">
              <option value="">Цель</option>
              <option>Долгосрочные отношения</option><option>Общение и новые знакомства</option>
              <option>Дружба</option><option>Новый опыт</option>
            </select>
            <select value={form.relationship || ""} onChange={(e) => setForm({ ...form, relationship: e.target.value })} className="w-full px-3 py-2 rounded-lg bg-muted">
              <option value="">Статус</option><option>Single</option><option>Multiple</option><option>Complicated</option><option>Taken</option><option>Not to answer</option>
            </select>
            <div className="grid grid-cols-3 gap-2">
              <select value={form.kids || ""} onChange={(e) => setForm({ ...form, kids: e.target.value })} className="px-2 py-2 rounded-lg bg-muted text-sm">
                <option value="">Дети</option><option>No kids</option><option>I have kids</option><option>No answer</option>
              </select>
              <select value={form.smoking || ""} onChange={(e) => setForm({ ...form, smoking: e.target.value })} className="px-2 py-2 rounded-lg bg-muted text-sm">
                <option value="">Курение</option><option>Don't smoke</option><option>Rarely</option><option>Smoke</option>
              </select>
              <select value={form.alcohol || ""} onChange={(e) => setForm({ ...form, alcohol: e.target.value })} className="px-2 py-2 rounded-lg bg-muted text-sm">
                <option value="">Алкоголь</option><option>Don't drink</option><option>Rarely</option><option>Drink</option>
              </select>
            </div>
            <div>
              <p className="text-xs text-muted-foreground mb-2">Интересы: {form.interests?.length || 0}/10</p>
              <div className="space-y-2 max-h-60 overflow-y-auto">
                {Object.entries(INTERESTS_POOL).map(([cat, items]) => (
                  <div key={cat}>
                    <p className="text-[10px] uppercase font-bold text-primary tracking-wider">{cat}</p>
                    <div className="flex gap-1 flex-wrap mt-1">
                      {items.map((i) => (
                        <button key={i} data-testid={`interest-${i}`} onClick={() => toggleInterest(i)} type="button" className={`px-2 py-1 rounded-full text-xs font-medium transition-colors duration-200 ${form.interests?.includes(i) ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-muted/70"}`}>{i}</button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <button data-testid="btn-save-profile" onClick={save} className="w-full btn-pill bg-primary text-primary-foreground mt-2">Сохранить</button>
          </div>
        ) : (
          <div className="space-y-2 text-sm">
            {user.about && <p className="p-3 bg-muted rounded-xl">{user.about}</p>}
            {user.job && <p><b>Работа:</b> {user.job}</p>}
            {user.education && <p><b>Образование:</b> {user.education}</p>}
            {user.height && <p><b>Рост:</b> {user.height} см</p>}
            {user.goal && <p><b>Цель:</b> {user.goal}</p>}
            {user.interests?.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-2">
                {user.interests.map((i) => <span key={i} className="px-2 py-1 text-xs bg-secondary text-secondary-foreground rounded-full font-medium">{i}</span>)}
              </div>
            )}
          </div>
        )}
      </div>

      {user.is_admin && (
        <button data-testid="btn-admin" onClick={() => nav("/admin")} className="mx-4 mt-6 w-[calc(100%-2rem)] btn-pill bg-foreground text-background">
          <Shield className="w-4 h-4 mr-2" /> Админ панель
        </button>
      )}
      <button data-testid="btn-logout" onClick={async () => { await logout(); nav("/"); }} className="mx-4 mt-3 w-[calc(100%-2rem)] btn-pill bg-muted hover:bg-muted/70">
        <LogOut className="w-4 h-4 mr-2" /> Выйти
      </button>
    </MobileShell>
  );
}
