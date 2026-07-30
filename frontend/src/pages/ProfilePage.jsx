import { useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { MobileShell } from "@/components/lovreski/Shell";
import { BottomSheet } from "@/components/lovreski/BottomSheet";
import { useNavigate } from "react-router-dom";
import { useTheme } from "@/context/ThemeContext";
import { toast } from "sonner";
import {
  INTEREST_CATEGORIES, GOAL_OPTIONS, RELATIONSHIP_OPTIONS, KIDS_OPTIONS,
  SMOKING_OPTIONS, ALCOHOL_OPTIONS, GENDER_OPTIONS,
} from "@/lib/profileConstants";
import {
  Settings, Coins, Crown, Pencil, Eye, LogOut, Camera, Sun, Moon, Trash2,
  ChevronRight, Check, Plus, Info, ShieldCheck, MapPin, Circle,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

// Convert cm → ft/in (approximate).
const cmToFtIn = (cm) => {
  const totalIn = cm / 2.54;
  const ft = Math.floor(totalIn / 12);
  const inch = Math.round(totalIn - ft * 12);
  return `${ft}'${inch}"`;
};

export default function ProfilePage() {
  const { user, refresh, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const nav = useNavigate();
  const [mode, setMode] = useState("edit"); // 'edit' | 'view'
  const [form, setForm] = useState({});
  const [stats, setStats] = useState({ popularity: "medium", polarity: 50, completion: 0, likes_received: 0 });
  const [savedField, setSavedField] = useState(null); // shows the "Saved ✓" tick
  const [sheet, setSheet] = useState(null); // active bottom sheet: 'height'|'goal'|'relationship'|'kids'|'smoking'|'alcohol'|'gender'|'interests'|'gallery'
  const [heightDraft, setHeightDraft] = useState(170);
  const [galleryIdx, setGalleryIdx] = useState(0);
  const [dragging, setDragging] = useState(null); // photo idx being dragged
  const fileRef = useRef(null);

  useEffect(() => { if (user) setForm({ ...user }); }, [user]);
  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get("/profile/me/stats");
        setStats(data);
      } catch {}
    })();
  }, [user?.user_id]);

  // Auto-save a single field (called on blur / dropdown-select)
  const saveField = async (patch) => {
    try {
      await api.put("/profile", patch);
      const firstKey = Object.keys(patch)[0];
      setSavedField(firstKey);
      setTimeout(() => setSavedField(null), 1500);
      await refresh();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Не удалось сохранить");
    }
  };

  // Full save via bottom button
  const saveAll = async () => {
    try {
      const payload = { ...form };
      delete payload.email; delete payload.user_id;
      await api.put("/profile", payload);
      await refresh();
      toast.success("✅ Профиль обновлён!");
    } catch (e) { toast.error(e.response?.data?.detail || "Ошибка"); }
  };

  // File → base64 upload
  const handleUpload = async (file) => {
    if (!file) return;
    if (!file.type.startsWith("image/")) return toast.error("Только изображения");
    if (file.size > 1_500_000) return toast.error("Максимум 1.5 МБ");
    const reader = new FileReader();
    reader.onload = async () => {
      try {
        await api.post("/profile/photo", { data_url: reader.result });
        await refresh();
        toast.success("Фото загружено ✓");
      } catch (e) { toast.error(e.response?.data?.detail || "Ошибка загрузки"); }
    };
    reader.readAsDataURL(file);
  };

  const deletePhoto = async (idx) => {
    try { await api.delete(`/profile/photo/${idx}`); await refresh(); toast.success("Фото удалено"); }
    catch { toast.error("Ошибка"); }
  };

  const reorderPhotos = async (from, to) => {
    if (from === to) return;
    const next = [...(form.photos || [])];
    const [moved] = next.splice(from, 1);
    next.splice(to, 0, moved);
    setForm((f) => ({ ...f, photos: next }));
    try { await api.put("/profile/photos", { photos: next }); await refresh(); }
    catch { toast.error("Ошибка"); }
  };

  const toggleInterest = async (i) => {
    const cur = form.interests || [];
    let next;
    if (cur.includes(i)) next = cur.filter((x) => x !== i);
    else if (cur.length < 10) next = [...cur, i];
    else { toast.error("Максимум 10 интересов"); return; }
    setForm((f) => ({ ...f, interests: next }));
    await saveField({ interests: next });
  };

  if (!user) return null;
  const photos = form.photos || [];
  const age = new Date().getFullYear() - parseInt((user.dob || "2000-01-01").split("-")[0]);
  const popColor = stats.popularity === "high" ? "bg-emerald-500" : stats.popularity === "low" ? "bg-rose-500" : "bg-amber-500";
  const popLabel = stats.popularity === "high" ? "Высокая" : stats.popularity === "low" ? "Низкая" : "Средняя";
  const popPct = stats.popularity === "high" ? 90 : stats.popularity === "low" ? 25 : 60;

  // ────────── VIEW mode ──────────
  if (mode === "view") {
    return (
      <MobileShell>
        <header className="sticky top-0 z-40 bg-background/85 backdrop-blur-xl px-4 pt-4 pb-3 flex justify-between items-center border-b border-border/50">
          <h1 className="font-display font-black text-2xl">Предпросмотр</h1>
          <button data-testid="btn-back-to-edit" onClick={() => setMode("edit")} className="btn-pill bg-primary text-primary-foreground text-xs !py-2">
            <Pencil className="w-3 h-3 mr-1" /> Редактировать
          </button>
        </header>
        <div className="p-4">
          <div className="relative aspect-[3/4] rounded-3xl overflow-hidden bg-muted shadow-xl">
            <img
              data-testid="view-main-photo"
              src={photos[galleryIdx] || `https://api.dicebear.com/9.x/avataaars/svg?seed=${user.user_id}`}
              alt=""
              className="w-full h-full object-cover"
            />
            <div className="absolute inset-x-0 top-2 flex gap-1 px-3">
              {(photos.length ? photos : [1]).map((_, i) => (
                <div key={i} className={`flex-1 h-1 rounded-full ${i === galleryIdx ? "bg-white" : "bg-white/40"}`} />
              ))}
            </div>
            <div className="absolute inset-0 flex">
              <button className="flex-1" onClick={() => setGalleryIdx((i) => Math.max(0, i - 1))} />
              <button className="flex-1" onClick={() => setGalleryIdx((i) => Math.min(photos.length - 1, i + 1))} />
            </div>
            <div className="absolute inset-x-0 bottom-0 h-1/2 bg-gradient-to-t from-black/85 to-transparent pointer-events-none" />
            <div className="absolute inset-x-0 bottom-0 p-5 text-white">
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="font-display font-black text-3xl">{user.name}, {age}</h2>
                {user.verified && <ShieldCheck className="w-6 h-6 text-sky-400" />}
                {user.is_premium && <Crown className="w-5 h-5 text-accent" />}
              </div>
              {user.city && <p className="text-sm mt-1 flex items-center gap-1"><MapPin className="w-4 h-4" /> {user.city}</p>}
            </div>
          </div>
          {user.about && <p className="mt-4 p-4 bg-muted rounded-2xl text-sm">{user.about}</p>}
          {user.interests?.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {user.interests.map((i) => <span key={i} className="px-3 py-1.5 bg-primary text-primary-foreground rounded-full text-xs font-semibold">{i}</span>)}
            </div>
          )}
        </div>
      </MobileShell>
    );
  }

  // ────────── EDIT mode ──────────
  return (
    <MobileShell>
      {/* Sticky header — always shows photo + name */}
      <header className="sticky top-0 z-40 bg-background/90 backdrop-blur-xl border-b border-border/50">
        <div className="flex justify-between items-center px-4 pt-3 pb-2">
          <div className="flex items-center gap-2 min-w-0">
            <img
              src={photos[0] || `https://api.dicebear.com/9.x/avataaars/svg?seed=${user.user_id}`}
              alt="" className="w-9 h-9 rounded-full object-cover"
            />
            <div className="min-w-0">
              <p className="font-display font-black text-sm leading-none truncate">{user.name}, {age}</p>
              <p className="text-[10px] text-muted-foreground flex items-center gap-1">
                <Circle className="w-2 h-2 text-emerald-500 fill-current" /> Онлайн
              </p>
            </div>
          </div>
          <div className="flex gap-2">
            <button data-testid="btn-view-mode" onClick={() => setMode("view")} className="p-2 rounded-full bg-muted hover:bg-muted/70" aria-label="Preview">
              <Eye className="w-5 h-5" />
            </button>
            <button onClick={toggle} className="p-2 rounded-full bg-muted hover:bg-muted/70">
              {theme === "dark" ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
            </button>
            <button data-testid="btn-settings" onClick={() => nav("/settings")} className="p-2 rounded-full bg-muted hover:bg-muted/70">
              <Settings className="w-5 h-5" />
            </button>
          </div>
        </div>
        {/* Profile completion bar */}
        <div className="px-4 pb-2">
          <div className="flex items-center justify-between mb-1">
            <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-widest">Профиль заполнен</span>
            <span data-testid="completion-pct" className="text-[11px] font-bold text-primary">{stats.completion}%</span>
          </div>
          <div className="h-1.5 rounded-full bg-muted overflow-hidden">
            <motion.div
              className="h-full bg-gradient-to-r from-primary to-rose-400"
              initial={{ width: 0 }} animate={{ width: `${stats.completion}%` }}
              transition={{ duration: 0.6 }}
            />
          </div>
          {stats.completion < 100 && (
            <p className="text-[10px] text-muted-foreground mt-1">Заполните профиль, чтобы получать больше симпатий</p>
          )}
        </div>
      </header>

      <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={(e) => handleUpload(e.target.files?.[0])} data-testid="photo-file-input" />

      {/* Big circular photo header */}
      <section className="px-4 pt-6 pb-3 text-center">
        <div className="relative w-32 h-32 mx-auto">
          <img
            data-testid="main-avatar"
            src={photos[0] || `https://api.dicebear.com/9.x/avataaars/svg?seed=${user.user_id}`}
            alt="" className="w-full h-full rounded-full object-cover border-4 border-primary/30 shadow-xl shadow-primary/20"
          />
          <button
            data-testid="btn-upload-photo"
            onClick={() => fileRef.current?.click()}
            className="absolute bottom-0 right-0 w-10 h-10 rounded-full bg-primary text-primary-foreground flex items-center justify-center shadow-lg hover:scale-105 transition-transform duration-200"
            aria-label="Загрузить фото"
          >
            <Plus className="w-5 h-5" />
          </button>
        </div>
        <div className="mt-3 flex items-center justify-center gap-2">
          <h2 className="font-display font-black text-xl">{user.name}, {age}</h2>
          <Circle className="w-2.5 h-2.5 text-emerald-500 fill-current" />
        </div>
        {user.city && <p className="text-xs text-muted-foreground">{user.city}</p>}
        <button
          data-testid="btn-toggle-view"
          onClick={() => setMode("view")}
          className="mt-3 inline-flex items-center gap-1 text-sm text-primary font-semibold hover:underline"
        >
          <Pencil className="w-4 h-4" /> Редактировать · Предпросмотр
        </button>
      </section>

      {/* Photo gallery — up to 4, drag-reorder + delete */}
      <section className="px-4 pb-4">
        <div className="grid grid-cols-4 gap-2">
          {[0,1,2,3].map((i) => {
            const p = photos[i];
            return (
              <div
                key={i}
                data-testid={`photo-slot-${i}`}
                draggable={!!p}
                onDragStart={() => setDragging(i)}
                onDragOver={(e) => e.preventDefault()}
                onDrop={() => { if (dragging !== null) reorderPhotos(dragging, i); setDragging(null); }}
                className="relative aspect-square rounded-xl overflow-hidden bg-muted border border-border group"
              >
                {p ? (
                  <>
                    <img src={p} alt="" className="w-full h-full object-cover" onClick={() => { setGalleryIdx(i); setSheet("gallery"); }} />
                    {i === 0 && <span className="absolute top-1 left-1 text-[9px] font-black bg-primary text-primary-foreground px-1.5 py-0.5 rounded-full">MAIN</span>}
                    <button
                      data-testid={`btn-delete-photo-${i}`}
                      onClick={(e) => { e.stopPropagation(); deletePhoto(i); }}
                      className="absolute top-1 right-1 w-6 h-6 rounded-full bg-black/70 text-white flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-200"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </>
                ) : (
                  <button data-testid={`btn-add-photo-${i}`} onClick={() => fileRef.current?.click()} className="w-full h-full flex items-center justify-center text-muted-foreground hover:bg-muted/70">
                    <Plus className="w-6 h-6" />
                  </button>
                )}
              </div>
            );
          })}
        </div>
        <p className="text-[10px] text-muted-foreground mt-1.5 text-center">Перетащите для изменения порядка · до 4 фото</p>
      </section>

      {/* Popularity + coin balance + polarity cards */}
      <section className="px-4 grid grid-cols-2 gap-3">
        <div data-testid="popularity-card" className="p-4 rounded-2xl bg-card border border-border relative group">
          <div className="flex items-center justify-between">
            <p className="text-[10px] uppercase tracking-widest text-muted-foreground">Популярность</p>
            <button className="text-muted-foreground opacity-70 hover:opacity-100" aria-label="info">
              <Info className="w-3.5 h-3.5" />
            </button>
          </div>
          <p className={`font-display font-black text-xl mt-1 ${stats.popularity === "high" ? "text-emerald-500" : stats.popularity === "low" ? "text-rose-500" : "text-amber-500"}`}>{popLabel}</p>
          <div className="h-2 rounded-full bg-muted mt-2 overflow-hidden">
            <motion.div className={`h-full ${popColor}`} initial={{ width: 0 }} animate={{ width: `${popPct}%` }} />
          </div>
          <p className="text-[10px] text-muted-foreground mt-1">{stats.likes_received} симпатий получено</p>
          <div className="absolute top-full left-0 mt-1 hidden group-hover:block bg-foreground text-background text-[10px] px-2 py-1 rounded-md z-10 max-w-[200px]">
            Считается по количеству симпатий за последние 30 дней
          </div>
        </div>
        <button data-testid="coin-card" onClick={() => nav("/premium")} className="p-4 rounded-2xl bg-gradient-to-br from-primary to-primary/70 text-primary-foreground text-left hover:scale-[1.02] transition-transform duration-200">
          <p className="text-[10px] uppercase tracking-widest opacity-80 flex items-center gap-1"><Coins className="w-3 h-3" /> Баланс</p>
          <p className="font-display font-black text-2xl mt-1">{user.coins || 0} 🪙</p>
          <p className="text-[11px] mt-1 opacity-90 font-semibold">Пополнить →</p>
        </button>
      </section>

      {/* Polarity graph + Premium display */}
      <section className="px-4 mt-3 grid grid-cols-2 gap-3">
        <div data-testid="polarity-card" className="p-4 rounded-2xl bg-card border border-border">
          <p className="text-[10px] uppercase tracking-widest text-muted-foreground">Полярность</p>
          <p className="text-xs mt-1 font-semibold">{stats.polarity < 40 ? "Интроверт" : stats.polarity > 60 ? "Экстраверт" : "Амбиверт"}</p>
          <div className="relative h-2 rounded-full bg-muted mt-2 overflow-hidden">
            <div className="absolute inset-0 bg-gradient-to-r from-sky-400 via-primary to-amber-400 opacity-30" />
            <motion.div
              initial={{ x: 0 }}
              animate={{ x: `${stats.polarity}%` }}
              className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-primary shadow-md ring-2 ring-background"
              style={{ left: 0, transform: `translate(${stats.polarity}%, -50%) translateX(-50%)` }}
            />
          </div>
          <div className="flex justify-between text-[9px] text-muted-foreground mt-1">
            <span>🧘 тихий</span><span>🎉 общительный</span>
          </div>
        </div>
        <div data-testid="premium-card" className={`p-4 rounded-2xl border ${user.is_premium ? "bg-gradient-to-br from-accent/20 to-amber-400/10 border-accent/40" : "bg-card border-border"}`}>
          <p className="text-[10px] uppercase tracking-widest text-muted-foreground flex items-center gap-1"><Crown className="w-3 h-3" /> Premium</p>
          {user.is_premium ? (
            <>
              <p className="font-display font-black text-lg mt-1 text-accent">Активен</p>
              <p className="text-[10px] text-muted-foreground">Все функции разблокированы</p>
            </>
          ) : (
            <>
              <p className="font-display font-black text-lg mt-1">Не активен</p>
              <button onClick={() => nav("/premium")} className="text-[10px] text-primary font-bold hover:underline">Активировать →</button>
            </>
          )}
        </div>
      </section>

      {/* Personal Info fields */}
      <section className="px-4 mt-5 space-y-3">
        <SectionTitle>Основная информация</SectionTitle>

        <FieldRow
          label="Имя" testid="field-name" saved={savedField === "name"}
          input={
            <input
              value={form.name || ""} maxLength={50}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              onBlur={() => form.name !== user.name && saveField({ name: form.name })}
              className="flex-1 bg-transparent outline-none text-right"
            />
          }
          counter={`${(form.name || "").length}/50`}
        />

        <FieldRow
          label="Пол" testid="field-gender" saved={savedField === "gender"}
          input={<span className="text-right">{GENDER_OPTIONS.find((g) => g.value === form.gender)?.label || "—"}</span>}
          rightArrow onClick={() => setSheet("gender")}
        />

        <FieldRow
          label="Дата рождения" testid="field-dob" saved={savedField === "dob"}
          input={
            <input
              type="date"
              value={form.dob || ""}
              onChange={(e) => setForm({ ...form, dob: e.target.value })}
              onBlur={() => form.dob !== user.dob && saveField({ dob: form.dob })}
              className="flex-1 bg-transparent outline-none text-right"
            />
          }
        />

        <div data-testid="field-about" className="p-3 bg-card border border-border rounded-2xl">
          <div className="flex justify-between items-center mb-1">
            <p className="text-xs font-semibold text-muted-foreground">О себе</p>
            <div className="flex items-center gap-2">
              {savedField === "about" && <SavedTick />}
              <span className="text-[10px] text-muted-foreground">{(form.about || "").length}/500</span>
            </div>
          </div>
          <textarea
            data-testid="input-about"
            maxLength={500} rows={3}
            placeholder="Расскажите о себе..."
            value={form.about || ""}
            onChange={(e) => setForm({ ...form, about: e.target.value })}
            onBlur={() => form.about !== user.about && saveField({ about: form.about })}
            className="w-full bg-transparent outline-none text-sm resize-none"
          />
        </div>

        <FieldRow
          label="Работа" testid="field-job" saved={savedField === "job"}
          input={
            <input
              maxLength={80} placeholder="Ваша профессия..."
              value={form.job || ""}
              onChange={(e) => setForm({ ...form, job: e.target.value })}
              onBlur={() => form.job !== user.job && saveField({ job: form.job })}
              className="flex-1 bg-transparent outline-none text-right"
            />
          }
          counter={`${(form.job || "").length}/80`}
        />

        <FieldRow
          label="Образование" testid="field-education" saved={savedField === "education"}
          input={
            <input
              maxLength={100} placeholder="Ваше образование..."
              value={form.education || ""}
              onChange={(e) => setForm({ ...form, education: e.target.value })}
              onBlur={() => form.education !== user.education && saveField({ education: form.education })}
              className="flex-1 bg-transparent outline-none text-right"
            />
          }
          counter={`${(form.education || "").length}/100`}
        />

        <FieldRow
          label="Языки" testid="field-language" saved={savedField === "language"}
          input={
            <input
              maxLength={50} placeholder="English, Russian..."
              value={form.language || ""}
              onChange={(e) => setForm({ ...form, language: e.target.value })}
              onBlur={() => form.language !== user.language && saveField({ language: form.language })}
              className="flex-1 bg-transparent outline-none text-right"
            />
          }
          counter={`${(form.language || "").length}/50`}
        />

        <FieldRow
          label="Рост" testid="field-height" saved={savedField === "height"}
          input={<span className="text-right">{form.height ? `${form.height} см · ${cmToFtIn(form.height)}` : "—"}</span>}
          rightArrow onClick={() => { setHeightDraft(form.height || 170); setSheet("height"); }}
        />
      </section>

      {/* Dropdown fields */}
      <section className="px-4 mt-5 space-y-3">
        <SectionTitle>Обо мне</SectionTitle>

        <FieldRow
          label="Цель" testid="field-goal" saved={savedField === "goal"}
          input={<span className="text-right">{GOAL_OPTIONS.find((g) => g.value === form.goal || g.label === form.goal)?.emoji || ""} {form.goal || "—"}</span>}
          rightArrow onClick={() => setSheet("goal")}
        />
        <FieldRow label="Отношения" testid="field-relationship" saved={savedField === "relationship"} input={<span>{form.relationship || "—"}</span>} rightArrow onClick={() => setSheet("relationship")} />
        <FieldRow label="Дети" testid="field-kids" saved={savedField === "kids"} input={<span>{form.kids || "—"}</span>} rightArrow onClick={() => setSheet("kids")} />
        <FieldRow label="Курение" testid="field-smoking" saved={savedField === "smoking"} input={<span>{form.smoking || "—"}</span>} rightArrow onClick={() => setSheet("smoking")} />
        <FieldRow label="Алкоголь" testid="field-alcohol" saved={savedField === "alcohol"} input={<span>{form.alcohol || "—"}</span>} rightArrow onClick={() => setSheet("alcohol")} />
      </section>

      {/* Interests */}
      <section className="px-4 mt-5">
        <div className="flex justify-between items-center mb-2">
          <SectionTitle>Интересы</SectionTitle>
          <span data-testid="interests-counter" className="text-xs font-semibold text-primary">{(form.interests || []).length}/10 выбрано</span>
        </div>
        <button
          data-testid="btn-open-interests"
          onClick={() => setSheet("interests")}
          className="w-full p-3 bg-card border border-border rounded-2xl text-left"
        >
          {form.interests?.length ? (
            <div className="flex flex-wrap gap-1.5">
              {form.interests.map((i) => (
                <span key={i} className="px-3 py-1 text-xs font-semibold bg-primary text-primary-foreground rounded-full">{i}</span>
              ))}
              <span className="px-3 py-1 text-xs font-semibold border-2 border-dashed border-border text-muted-foreground rounded-full">+ добавить</span>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Нажмите, чтобы выбрать интересы</p>
          )}
        </button>
      </section>

      {/* Save all button */}
      <section className="px-4 mt-6">
        <button data-testid="btn-save-all" onClick={saveAll} className="w-full btn-pill bg-primary text-primary-foreground shadow-lg shadow-primary/25">
          Сохранить профиль
        </button>
      </section>

      {/* Admin + logout */}
      <section className="px-4 mt-3 space-y-2 pb-6">
        {user.is_admin && (
          <button onClick={() => nav("/admin")} className="w-full btn-pill bg-foreground text-background">
            🛡 Админ панель
          </button>
        )}
        <button data-testid="btn-logout" onClick={async () => { await logout(); nav("/"); }} className="w-full btn-pill bg-muted hover:bg-muted/70">
          <LogOut className="w-4 h-4 mr-2" /> Выйти
        </button>
      </section>

      {/* ────────── BOTTOM SHEETS ────────── */}
      <BottomSheet open={sheet === "gender"} onClose={() => setSheet(null)} title="Пол" testId="sheet-gender">
        {GENDER_OPTIONS.map((g) => (
          <button key={g.value} data-testid={`opt-gender-${g.value}`} onClick={async () => { setForm((f) => ({ ...f, gender: g.value })); await saveField({ gender: g.value }); setSheet(null); }} className="w-full flex justify-between items-center px-4 py-3 rounded-xl hover:bg-muted">
            <span>{g.label}</span>
            {form.gender === g.value && <Check className="w-5 h-5 text-primary" />}
          </button>
        ))}
      </BottomSheet>

      <BottomSheet open={sheet === "goal"} onClose={() => setSheet(null)} title="Ваша цель" testId="sheet-goal">
        {GOAL_OPTIONS.map((g) => (
          <button key={g.value} data-testid={`opt-goal-${g.value}`} onClick={async () => { setForm((f) => ({ ...f, goal: g.label })); await saveField({ goal: g.label }); setSheet(null); }} className="w-full flex justify-between items-center px-4 py-3 rounded-xl hover:bg-muted">
            <span>{g.emoji} {g.label}</span>
            {form.goal === g.label && <Check className="w-5 h-5 text-primary" />}
          </button>
        ))}
      </BottomSheet>

      {[
        { key: "relationship", title: "Отношения", opts: RELATIONSHIP_OPTIONS },
        { key: "kids", title: "Дети", opts: KIDS_OPTIONS },
        { key: "smoking", title: "Курение", opts: SMOKING_OPTIONS },
        { key: "alcohol", title: "Алкоголь", opts: ALCOHOL_OPTIONS },
      ].map(({ key, title, opts }) => (
        <BottomSheet key={key} open={sheet === key} onClose={() => setSheet(null)} title={title} testId={`sheet-${key}`}>
          {opts.map((o) => (
            <button key={o} data-testid={`opt-${key}-${o.replace(/\s/g, "_")}`} onClick={async () => { setForm((f) => ({ ...f, [key]: o })); await saveField({ [key]: o }); setSheet(null); }} className="w-full flex justify-between items-center px-4 py-3 rounded-xl hover:bg-muted">
              <span>{o}</span>
              {form[key] === o && <Check className="w-5 h-5 text-primary" />}
            </button>
          ))}
        </BottomSheet>
      ))}

      <BottomSheet open={sheet === "height"} onClose={() => setSheet(null)} title="Рост" testId="sheet-height">
        <div className="text-center py-4">
          <p data-testid="height-display" className="font-display font-black text-5xl text-primary">{heightDraft} см</p>
          <p className="text-sm text-muted-foreground mt-1">{cmToFtIn(heightDraft)}</p>
        </div>
        <input
          data-testid="height-slider"
          type="range" min={60} max={250} value={heightDraft}
          onChange={(e) => setHeightDraft(parseInt(e.target.value))}
          className="w-full accent-primary"
        />
        <div className="flex justify-between text-xs text-muted-foreground mt-2">
          <span>60 см</span><span>250 см</span>
        </div>
        <div className="grid grid-cols-2 gap-2 mt-5">
          <button data-testid="height-skip" onClick={async () => { await saveField({ height: null }); setSheet(null); }} className="btn-pill bg-muted">Не указывать</button>
          <button data-testid="height-save" onClick={async () => { setForm((f) => ({ ...f, height: heightDraft })); await saveField({ height: heightDraft }); setSheet(null); }} className="btn-pill bg-primary text-primary-foreground">Сохранить</button>
        </div>
      </BottomSheet>

      <BottomSheet open={sheet === "interests"} onClose={() => setSheet(null)} title={`Интересы (${(form.interests || []).length}/10)`} testId="sheet-interests">
        <div className="space-y-4">
          {INTEREST_CATEGORIES.map((cat) => (
            <div key={cat.key}>
              <h4 className="font-display font-bold text-sm mb-2 flex items-center gap-1">
                <span>{cat.emoji}</span> {cat.label}
              </h4>
              <div className="flex flex-wrap gap-1.5">
                {cat.items.map((i) => {
                  const active = (form.interests || []).includes(i);
                  const disabled = !active && (form.interests || []).length >= 10;
                  return (
                    <button
                      key={i}
                      data-testid={`interest-${i.replace(/\s/g, "_")}`}
                      disabled={disabled}
                      onClick={() => toggleInterest(i)}
                      className={`px-3 py-1.5 rounded-full text-xs font-semibold transition-colors duration-200 ${
                        active
                          ? "bg-primary text-primary-foreground border-2 border-primary"
                          : disabled
                          ? "border-2 border-border text-muted-foreground opacity-40 cursor-not-allowed"
                          : "border-2 border-border text-foreground hover:border-primary"
                      }`}
                    >
                      {i}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </BottomSheet>

      {/* Fullscreen swipeable gallery */}
      <AnimatePresence>
        {sheet === "gallery" && photos.length > 0 && (
          <motion.div
            data-testid="fullscreen-gallery"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-[80] bg-black flex items-center justify-center"
            onClick={() => setSheet(null)}
          >
            <img src={photos[galleryIdx]} alt="" className="max-w-full max-h-full object-contain" />
            <button onClick={() => setSheet(null)} className="absolute top-4 right-4 w-10 h-10 rounded-full bg-white/20 text-white flex items-center justify-center">✕</button>
            <div className="absolute inset-x-0 top-4 flex gap-1 px-4">
              {photos.map((_, i) => <div key={i} className={`flex-1 h-1 rounded-full ${i === galleryIdx ? "bg-white" : "bg-white/30"}`} />)}
            </div>
            <button className="absolute left-0 top-0 bottom-0 w-1/3" onClick={(e) => { e.stopPropagation(); setGalleryIdx((i) => Math.max(0, i - 1)); }} />
            <button className="absolute right-0 top-0 bottom-0 w-1/3" onClick={(e) => { e.stopPropagation(); setGalleryIdx((i) => Math.min(photos.length - 1, i + 1)); }} />
          </motion.div>
        )}
      </AnimatePresence>
    </MobileShell>
  );
}

// ────────── Reusable pieces ──────────
const SectionTitle = ({ children }) => (
  <h3 className="font-display font-bold text-xs uppercase tracking-widest text-muted-foreground">{children}</h3>
);

const FieldRow = ({ label, input, counter, saved, rightArrow, onClick, testid }) => (
  <div data-testid={testid} onClick={onClick} className={`p-3 bg-card border border-border rounded-2xl flex items-center gap-3 ${onClick ? "cursor-pointer hover:bg-muted/40" : ""}`}>
    <span className="text-sm font-semibold text-muted-foreground w-24 flex-shrink-0">{label}</span>
    <div className="flex-1 text-sm text-right truncate">{input}</div>
    <div className="flex items-center gap-1">
      {saved && <SavedTick />}
      {counter && <span className="text-[10px] text-muted-foreground">{counter}</span>}
      {rightArrow && <ChevronRight className="w-4 h-4 text-muted-foreground" />}
    </div>
  </div>
);

const SavedTick = () => (
  <motion.span
    initial={{ opacity: 0, scale: 0.5 }}
    animate={{ opacity: 1, scale: 1 }}
    exit={{ opacity: 0 }}
    className="inline-flex items-center gap-0.5 text-emerald-500 text-[10px] font-bold"
  >
    <Check className="w-3 h-3" /> Saved
  </motion.span>
);
