import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { api, setToken } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

// REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
export default function AuthCallback() {
  const nav = useNavigate();
  const { setUser } = useAuth();

  useEffect(() => {
    const hash = window.location.hash || "";
    const match = hash.match(/session_id=([^&]+)/);
    if (!match) { nav("/"); return; }
    const sid = match[1];
    (async () => {
      try {
        const { data } = await api.post("/auth/session", { session_id: sid });
        if (data.token) setToken(data.token);
        setUser(data.user);
        toast.success(`Добро пожаловать, ${data.user.name}!`);
        nav("/home", { replace: true, state: { user: data.user } });
      } catch (e) {
        toast.error("Не удалось войти через Google");
        nav("/", { replace: true });
      }
    })();
  }, [nav, setUser]);

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="animate-pulse text-muted-foreground">Вход...</div>
    </div>
  );
}
