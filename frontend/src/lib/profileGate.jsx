// Blocks likes / new chats until the user's own profile has a photo + the 5 "About me" choices.
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { UserRoundPen } from "lucide-react";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { useAuth } from "@/context/AuthContext";
import { useI18n } from "@/lib/i18n";

export const REQUIRED_FIELDS = ["photos", "goal", "relationship", "kids", "smoking", "alcohol"];
const EVENT = "lovreski:profile-incomplete";

export const missingFields = (u) => REQUIRED_FIELDS.filter((f) => (f === "photos" ? !(u?.photos || []).length : !u?.[f]));
export const emitProfileGate = (missing) => window.dispatchEvent(new CustomEvent(EVENT, { detail: missing }));

// Returns guard(): true when the action may proceed; otherwise opens the gate and returns false.
export function useProfileGate() {
  const { user } = useAuth();
  return useCallback(() => {
    const missing = missingFields(user);
    if (!missing.length) return true;
    emitProfileGate(missing);
    return false;
  }, [user]);
}

export const ProfileGate = () => {
  const { t } = useI18n();
  const nav = useNavigate();
  const [missing, setMissing] = useState(null);
  useEffect(() => {
    const on = (e) => {
      setMissing(e.detail || []);
      nav("/profile?complete=1");
    };
    window.addEventListener(EVENT, on);
    return () => window.removeEventListener(EVENT, on);
  }, [nav]);

  return (
    <Dialog open={!!missing} onOpenChange={(o) => !o && setMissing(null)}>
      <DialogContent data-testid="profile-gate-dialog" className="max-w-sm rounded-3xl">
        <div className="w-12 h-12 rounded-2xl bg-primary/10 text-primary flex items-center justify-center">
          <UserRoundPen className="w-6 h-6" />
        </div>
        <DialogTitle className="font-display text-xl">{t("gate.title")}</DialogTitle>
        <DialogDescription data-testid="profile-gate-message">{t("gate.message")}</DialogDescription>
        {!!missing?.length && (
          <div>
            <p className="text-xs font-semibold text-muted-foreground mb-2">{t("gate.missing")}</p>
            <div className="flex flex-wrap gap-1.5" data-testid="profile-gate-missing">
              {missing.map((f) => (
                <span key={f} data-testid={`gate-missing-${f}`} className="px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-500/10 text-rose-600">
                  {t(`gate.field.${f}`)}
                </span>
              ))}
            </div>
          </div>
        )}
        <button data-testid="profile-gate-ok" onClick={() => setMissing(null)} className="btn-pill bg-primary text-primary-foreground w-full">
          {t("gate.button")}
        </button>
      </DialogContent>
    </Dialog>
  );
};
