import { MapPin, Circle, Crown, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";

export const ProfileCard = ({ user, testid, onLike, onPass, compact = false }) => {
  const photo = user.photos?.[0] || `https://api.dicebear.com/9.x/avataaars/svg?seed=${user.user_id}`;
  return (
    <div
      data-testid={testid || `profile-card-${user.user_id}`}
      className="relative overflow-hidden rounded-2xl bg-card shadow-sm border border-border/60 group"
    >
      <Link to={`/profile/${user.user_id}`}>
        <div className="aspect-[3/4] w-full overflow-hidden bg-muted">
          <img
            src={photo}
            alt={user.name}
            className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
          />
          <div className="absolute inset-x-0 bottom-0 h-1/2 bg-gradient-to-t from-black/85 via-black/40 to-transparent pointer-events-none" />
        </div>
        <div className="absolute top-2 left-2 right-2 flex justify-between items-start">
          <div className="flex gap-1">
            {user.online && (
              <span className="inline-flex items-center gap-1 bg-emerald-500 text-white text-[10px] font-semibold px-2 py-0.5 rounded-full">
                <Circle className="w-2 h-2 fill-current" /> онлайн
              </span>
            )}
            {user.verified && (
              <span className="inline-flex items-center gap-1 bg-sky-500/90 text-white text-[10px] font-semibold px-2 py-0.5 rounded-full">
                <ShieldCheck className="w-3 h-3" />
              </span>
            )}
          </div>
          {user.is_premium && (
            <span className="inline-flex items-center gap-1 bg-accent text-accent-foreground text-[10px] font-bold px-2 py-0.5 rounded-full">
              <Crown className="w-3 h-3" /> PREMIUM
            </span>
          )}
        </div>
        <div className="absolute inset-x-0 bottom-0 p-3 text-white">
          <h3 className="font-display font-bold text-lg leading-tight">
            {user.name}, {user.age}
          </h3>
          {user.distance_km != null && (
            <p className="flex items-center gap-1 text-xs opacity-90 mt-0.5">
              <MapPin className="w-3 h-3" /> {user.distance_km} км
            </p>
          )}
        </div>
      </Link>
      {!compact && (onLike || onPass) && (
        <div className="flex gap-2 p-2 bg-card">
          <button
            data-testid={`pass-btn-${user.user_id}`}
            onClick={() => onPass?.(user)}
            className="flex-1 py-2 rounded-full bg-muted text-muted-foreground font-semibold text-sm hover:bg-muted/70 transition-colors duration-200"
          >
            ✖
          </button>
          <button
            data-testid={`like-btn-${user.user_id}`}
            onClick={() => onLike?.(user)}
            className="flex-1 py-2 rounded-full bg-primary text-primary-foreground font-semibold text-sm hover:opacity-90 transition-opacity duration-200"
          >
            ❤
          </button>
        </div>
      )}
    </div>
  );
};
