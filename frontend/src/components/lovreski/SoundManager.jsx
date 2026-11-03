// Keeps sound prefs in sync with the user and plays the incoming-message sound app-wide.
import { useCallback, useEffect } from "react";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { createChatSocket } from "@/lib/ws";
import { DEFAULT_PREFS, playSound, setSoundPrefs } from "@/lib/sound";

export function useSoundPrefs() {
  const { user, refresh } = useAuth();
  const prefs = { ...DEFAULT_PREFS, ...(user?.preferences || {}) };
  const update = useCallback(async (patch) => {
    setSoundPrefs({ ...prefs, ...patch });
    await api.patch("/user/preferences", patch);
    await refresh();
  }, [prefs, refresh]); // eslint-disable-line react-hooks/exhaustive-deps
  return [prefs, update];
}

export const SoundManager = () => {
  const { user } = useAuth();
  const prefs = user?.preferences;
  const enabled = !!prefs?.soundEnabled;
  useEffect(() => { setSoundPrefs(prefs); }, [prefs]);
  useEffect(() => {
    if (!user?.user_id || !enabled) return;
    const sock = createChatSocket({
      onMessage: (m) => { if (m.from_user && m.from_user !== user.user_id) playSound("incoming"); },
    });
    return () => sock.close();
  }, [user?.user_id, enabled]);
  return null;
};
