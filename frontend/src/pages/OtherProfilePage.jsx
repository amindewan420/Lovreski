import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { ArrowLeft, Heart, MessageCircle, Flag, Ban, MapPin, Briefcase, GraduationCap, Languages, Ruler, ShieldCheck, Crown } from "lucide-react";
import { toast } from "sonner";

export default function OtherProfilePage() {
  const { id } = useParams();
  const nav = useNavigate();
  const [p, setP] = useState(null);
  const [photoIdx, setPhotoIdx] = useState(0);

  useEffect(() => { (async () => {
    try { const { data } = await api.get(`/profile/${id}`); setP(data); }
    catch { toast.error("Профиль не найден"); nav(-1); }
  })(); }, [id, nav]);

  if (!p) return <div className="min-h-screen flex items-center justify-center">Загрузка...</div>;

  const doLike = async () => {
    try { const { data } = await api.post(`/like/${id}`); toast.success(data.match ? `Взаимная симпатия!` : "Симпатия отправлена"); }
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

  return (
    <div className="min-h-screen bg-background flex justify-center">
      <div className="w-full max-w-md bg-background pb-24">
        <div className="relative aspect-[3/4] bg-muted">
          <img src={photos[photoIdx]} alt="" className="w-full h-full object-cover" />
          <div className="absolute inset-x-0 top-2 flex gap-1 px-2">
            {photos.map((_, i) => (
              <div key={i} className={`flex-1 h-1 rounded-full ${i === photoIdx ? "bg-white" : "bg-white/40"}`} />
            ))}
          </div>
          <div className="absolute inset-0 flex">
            <button className="flex-1" onClick={() => setPhotoIdx((i) => Math.max(0, i - 1))} />
            <button className="flex-1" onClick={() => setPhotoIdx((i) => Math.min(photos.length - 1, i + 1))} />
          </div>
          <button onClick={() => nav(-1)} className="absolute top-4 left-4 w-10 h-10 rounded-full bg-black/40 backdrop-blur text-white flex items-center justify-center"><ArrowLeft className="w-5 h-5" /></button>
          <div className="absolute inset-x-0 bottom-0 h-1/2 bg-gradient-to-t from-black/85 to-transparent pointer-events-none" />
          <div className="absolute inset-x-0 bottom-0 p-4 text-white">
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="font-display font-black text-3xl">{p.name}, {p.age}</h1>
              {p.verified && <ShieldCheck className="w-6 h-6 text-sky-400" />}
              {p.is_premium && <Crown className="w-5 h-5 text-accent" />}
              {p.online && <span className="text-xs bg-emerald-500 px-2 py-0.5 rounded-full">онлайн</span>}
            </div>
            {p.city && <p className="text-sm mt-1 flex items-center gap-1"><MapPin className="w-4 h-4" /> {p.city}{p.distance_km != null ? ` · ${p.distance_km} км` : ""}</p>}
          </div>
        </div>

        <div className="px-4 py-5 space-y-4">
          {p.about && <p className="text-sm leading-relaxed p-4 bg-muted rounded-2xl">{p.about}</p>}
          <div className="grid grid-cols-2 gap-2 text-sm">
            {p.job && <div className="flex items-center gap-2 p-3 bg-card border border-border rounded-xl"><Briefcase className="w-4 h-4 text-primary" /> {p.job}</div>}
            {p.education && <div className="flex items-center gap-2 p-3 bg-card border border-border rounded-xl"><GraduationCap className="w-4 h-4 text-primary" /> {p.education}</div>}
            {p.language && <div className="flex items-center gap-2 p-3 bg-card border border-border rounded-xl"><Languages className="w-4 h-4 text-primary" /> {p.language}</div>}
            {p.height && <div className="flex items-center gap-2 p-3 bg-card border border-border rounded-xl"><Ruler className="w-4 h-4 text-primary" /> {p.height} см</div>}
          </div>
          {p.goal && <p className="text-sm"><b>Цель:</b> {p.goal}</p>}
          {p.interests?.length > 0 && (
            <div>
              <h3 className="font-display font-bold mb-2">Интересы</h3>
              <div className="flex flex-wrap gap-1.5">
                {p.interests.map((i) => <span key={i} className="px-3 py-1.5 bg-secondary text-secondary-foreground rounded-full text-xs font-semibold">{i}</span>)}
              </div>
            </div>
          )}
        </div>

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
