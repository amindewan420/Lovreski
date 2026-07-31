import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import {
  ArrowLeft, Heart, MessageCircle, Flag, Ban, MapPin, Briefcase, GraduationCap,
  Languages, Ruler, ShieldCheck, Crown, Circle, Cigarette, Wine, Baby, Target, Users2,
} from "lucide-react";
import { toast } from "sonner";
import { INTEREST_CATEGORIES, GENDER_OPTIONS } from "@/lib/profileConstants";

const cmToFtIn = (cm) => {
  const totalIn = cm / 2.54;
  const ft = Math.floor(totalIn / 12);
  const inch = Math.round(totalIn - ft * 12);
  return `${ft}'${inch}"`;
};

// Group user's chosen interests by category for the public view.
const groupInterests = (chosen = []) => {
  const groups = [];
  for (const cat of INTEREST_CATEGORIES) {
    const items = cat.items.filter((i) => chosen.includes(i));
    if (items.length) groups.push({ ...cat, items });
  }
  // Also include any items that don't map to a category
  const flat = INTEREST_CATEGORIES.flatMap((c) => c.items);
  const extras = chosen.filter((i) => !flat.includes(i));
  if (extras.length) groups.push({ key: "other", label: "Другое", emoji: "✨", items: extras });
  return groups;
};

export default function OtherProfilePage() {
  const { id } = useParams();
  const nav = useNavigate();
  const [p, setP] = useState(null);
  const [photoIdx, setPhotoIdx] = useState(0);

  useEffect(() => {
    (async () => {
      try { const { data } = await api.get(`/profile/${id}`); setP(data); }
      catch { toast.error("Профиль не найден"); nav(-1); }
    })();
  }, [id, nav]);

  if (!p) return <div className="min-h-screen flex items-center justify-center">Загрузка...</div>;

  const doLike = async () => {
    try { const { data } = await api.post(`/like/${id}`); toast.success(data.match ? "Взаимная симпатия!" : "Симпатия отправлена"); }
    catch { toast.error("Ошибка"); }
  };
  const doReport = async () => {
    const reason = window.prompt("Причина жалобы:", "Спам");
    if (!reason) return;
    await api.post("/report", { target_user_id: id, reason });
    toast.success("Жалоба отправлена");
  };
  const doBlock = async () => {
    await api.post(`/block/${id}`); toast.success("Пользователь заблокирован"); nav(-1);
  };

  const photos = p.photos?.length ? p.photos : [`https://api.dicebear.com/9.x/avataaars/svg?seed=${p.user_id}`];
  const genderLabel = GENDER_OPTIONS.find((g) => g.value === p.gender)?.label;
  const interestGroups = groupInterests(p.interests);

  return (
    <div className="min-h-screen bg-background flex justify-center">
      <div className="w-full max-w-md bg-background pb-24">
        {/* Photo gallery */}
        <div className="relative aspect-[3/4] bg-muted" data-testid="public-photo-gallery">
          <img src={photos[photoIdx]} alt="" className="w-full h-full object-cover" />
          <div className="absolute inset-x-0 top-2 flex gap-1 px-2">
            {photos.map((_, i) => (
              <div key={i} className={`flex-1 h-1 rounded-full ${i === photoIdx ? "bg-white" : "bg-white/40"}`} />
            ))}
          </div>
          <div className="absolute inset-0 flex">
            <button className="flex-1" aria-label="prev" onClick={() => setPhotoIdx((i) => Math.max(0, i - 1))} />
            <button className="flex-1" aria-label="next" onClick={() => setPhotoIdx((i) => Math.min(photos.length - 1, i + 1))} />
          </div>
          <button onClick={() => nav(-1)} className="absolute top-4 left-4 w-10 h-10 rounded-full bg-black/40 backdrop-blur text-white flex items-center justify-center">
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div className="absolute inset-x-0 bottom-0 h-1/2 bg-gradient-to-t from-black/85 to-transparent pointer-events-none" />
          <div className="absolute inset-x-0 bottom-0 p-4 text-white">
            <div className="flex items-center gap-2 flex-wrap">
              <h1 data-testid="public-name-age" className="font-display font-black text-3xl">{p.name}, {p.age}</h1>
              {p.verified && <ShieldCheck className="w-6 h-6 text-sky-400" />}
              {p.is_premium && <Crown className="w-5 h-5 text-accent" />}
              <span data-testid="public-online-status" className={`text-xs px-2 py-0.5 rounded-full inline-flex items-center gap-1 ${p.online ? "bg-emerald-500" : "bg-gray-500"}`}>
                <Circle className={`w-2 h-2 fill-current`} /> {p.online ? "онлайн" : "офлайн"}
              </span>
            </div>
            {(p.city || p.distance_km != null) && (
              <p data-testid="public-location" className="text-sm mt-1 flex items-center gap-1">
                <MapPin className="w-4 h-4" />
                {p.city}{p.distance_km != null ? ` · ${p.distance_km} км` : ""}
              </p>
            )}
          </div>
        </div>

        {/* Body content */}
        <div className="px-4 py-5 space-y-5">
          {/* Personal Information */}
          <Section title="Личная информация" testid="section-personal">
            {p.about && <p data-testid="public-about" className="text-sm leading-relaxed p-4 bg-muted rounded-2xl">{p.about}</p>}
            <div className="grid grid-cols-1 gap-2">
              {genderLabel && <PubRow icon={Users2} label="Пол" value={genderLabel} testid="public-gender" />}
              {p.age != null && <PubRow icon={Circle} label="Возраст" value={`${p.age} лет`} testid="public-age" />}
              {p.job && <PubRow icon={Briefcase} label="Работа" value={p.job} testid="public-job" />}
              {p.education && <PubRow icon={GraduationCap} label="Образование" value={p.education} testid="public-education" />}
              {p.language && <PubRow icon={Languages} label="Языки" value={p.language} testid="public-language" />}
              {p.height && <PubRow icon={Ruler} label="Рост" value={`${p.height} см · ${cmToFtIn(p.height)}`} testid="public-height" />}
            </div>
          </Section>

          {/* Lifestyle & Goals */}
          {(p.goal || p.relationship || p.kids || p.smoking || p.alcohol) && (
            <Section title="Образ жизни и цели" testid="section-lifestyle">
              <div className="grid grid-cols-1 gap-2">
                {p.goal && <PubRow icon={Target} label="Цель" value={p.goal} testid="public-goal" />}
                {p.relationship && <PubRow icon={Heart} label="Статус" value={p.relationship} testid="public-relationship" />}
                {p.kids && <PubRow icon={Baby} label="Дети" value={p.kids} testid="public-kids" />}
                {p.smoking && <PubRow icon={Cigarette} label="Курение" value={p.smoking} testid="public-smoking" />}
                {p.alcohol && <PubRow icon={Wine} label="Алкоголь" value={p.alcohol} testid="public-alcohol" />}
              </div>
            </Section>
          )}

          {/* Interests grouped by category */}
          {interestGroups.length > 0 && (
            <Section title="Интересы" testid="section-interests">
              <div className="space-y-3" data-testid="public-interests-list">
                {interestGroups.map((cat) => (
                  <div key={cat.key}>
                    <p className="text-[10px] font-black uppercase tracking-widest text-muted-foreground mb-1.5">
                      {cat.emoji} {cat.label}
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {cat.items.map((i) => (
                        <span key={i} data-testid={`public-interest-${i.replace(/\s/g, "_")}`} className="px-3 py-1.5 bg-primary text-primary-foreground rounded-full text-xs font-semibold">{i}</span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </Section>
          )}
        </div>

        {/* Bottom action bar */}
        <div className="fixed bottom-0 left-1/2 -translate-x-1/2 w-full max-w-md p-3 bg-background/90 backdrop-blur border-t border-border flex gap-2">
          <button data-testid="pp-report" onClick={doReport} className="p-3 rounded-full bg-muted"><Flag className="w-5 h-5" /></button>
          <button data-testid="pp-block" onClick={doBlock} className="p-3 rounded-full bg-muted"><Ban className="w-5 h-5" /></button>
          <button data-testid="pp-like" onClick={doLike} className="flex-1 btn-pill bg-primary text-primary-foreground"><Heart className="w-4 h-4 mr-1" /> Нравится</button>
          <button data-testid="pp-msg" onClick={() => nav(`/chats/${id}`)} className="flex-1 btn-pill bg-foreground text-background"><MessageCircle className="w-4 h-4 mr-1" /> Написать</button>
        </div>
      </div>
    </div>
  );
}

const Section = ({ title, testid, children }) => (
  <section data-testid={testid}>
    <h2 className="font-display font-black text-lg mb-3">{title}</h2>
    <div className="space-y-2">{children}</div>
  </section>
);

const PubRow = ({ icon: Icon, label, value, testid }) => (
  <div data-testid={testid} className="flex items-center gap-3 p-3 bg-card border border-border rounded-xl">
    <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0">
      <Icon className="w-4 h-4 text-primary" />
    </div>
    <div className="flex-1 min-w-0">
      <p className="text-[10px] uppercase tracking-widest text-muted-foreground">{label}</p>
      <p className="font-semibold text-sm truncate">{value}</p>
    </div>
  </div>
);
