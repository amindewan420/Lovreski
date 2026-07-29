import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { Heart, Sparkles, Eye, EyeOff } from "lucide-react";

export default function Landing() {
  const nav = useNavigate();
  const { login, register } = useAuth();
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({
    email: "", password: "", name: "", gender: "female", dob: "1998-01-01",
  });
  const [submitting, setSubmitting] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const doGoogle = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + "/home";
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  const submit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      if (mode === "login") {
        const u = await login(form.email, form.password);
        toast.success(`С возвращением, ${u.name}!`);
        nav(u.is_admin ? "/admin" : "/home");
      } else {
        const u = await register(form);
        toast.success("Добро пожаловать в Lovreski!");
        nav("/home");
      }
    } catch (err) {
      const status = err.response?.status;
      const detail = err.response?.data?.detail;
      let msg = detail || "Ошибка";
      // Map to specific, user-friendly messages
      if (mode === "register" && status === 409) msg = "Email already exists";
      else if (mode === "login" && status === 401) msg = "Incorrect password";
      else if (mode === "login" && status === 404) {
        // Auto-switch to Register tab and preserve the email so the user can sign up in one click
        msg = "Account not found — переключаем на регистрацию";
        setMode("register");
      }
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex justify-center">
      <div className="w-full max-w-md relative overflow-hidden">
        <div className="absolute -top-32 -right-24 w-80 h-80 rounded-full bg-primary/25 blur-3xl" />
        <div className="absolute top-40 -left-32 w-72 h-72 rounded-full bg-accent/20 blur-3xl" />
        <div className="relative px-6 pt-16 pb-8 grain">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-11 h-11 rounded-2xl bg-primary flex items-center justify-center shadow-lg shadow-primary/30">
              <Heart className="w-6 h-6 text-primary-foreground fill-current" />
            </div>
            <span className="font-display font-black text-2xl tracking-tight">Lovreski</span>
          </div>
          <h1 className="font-display text-6xl sm:text-7xl font-black leading-[1.05] tracking-tight mt-8">
            <span className="text-primary">Lovreski</span>
          </h1>
        </div>

        <div className="relative bg-card rounded-t-[2rem] p-6 border-t border-border shadow-2xl">
          <div className="flex bg-muted rounded-full p-1 mb-6">
            <button
              data-testid="mode-login"
              onClick={() => setMode("login")}
              className={`flex-1 py-2 rounded-full text-sm font-semibold transition-colors duration-200 ${mode === "login" ? "bg-card text-foreground shadow" : "text-muted-foreground"}`}
            >
              Войти
            </button>
            <button
              data-testid="mode-register"
              onClick={() => setMode("register")}
              className={`flex-1 py-2 rounded-full text-sm font-semibold transition-colors duration-200 ${mode === "register" ? "bg-card text-foreground shadow" : "text-muted-foreground"}`}
            >
              Регистрация
            </button>
          </div>

          <form onSubmit={submit} className="space-y-3">
            {mode === "register" && (
              <>
                <input
                  data-testid="input-name"
                  required placeholder="Ваше имя"
                  value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="w-full px-4 py-3 rounded-xl bg-muted border border-transparent focus:border-primary focus:bg-card outline-none transition-colors duration-200"
                />
                <div className="grid grid-cols-2 gap-2">
                  <select
                    data-testid="input-gender"
                    value={form.gender} onChange={(e) => setForm({ ...form, gender: e.target.value })}
                    className="px-4 py-3 rounded-xl bg-muted border border-transparent focus:border-primary outline-none"
                  >
                    <option value="female">Женский</option>
                    <option value="male">Мужской</option>
                  </select>
                  <input
                    data-testid="input-dob"
                    type="date" value={form.dob}
                    onChange={(e) => setForm({ ...form, dob: e.target.value })}
                    className="px-4 py-3 rounded-xl bg-muted border border-transparent focus:border-primary outline-none"
                  />
                </div>
              </>
            )}
            <input
              data-testid="input-email"
              type="email" required placeholder="Email"
              value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })}
              className="w-full px-4 py-3 rounded-xl bg-muted border border-transparent focus:border-primary focus:bg-card outline-none transition-colors duration-200"
            />
            <div className="relative">
              <input
                data-testid="input-password"
                type={showPassword ? "text" : "password"} required placeholder="Пароль (мин. 6 символов)"
                value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })}
                className="w-full px-4 py-3 pr-12 rounded-xl bg-muted border border-transparent focus:border-primary focus:bg-card outline-none transition-colors duration-200"
              />
              <button
                type="button"
                data-testid="toggle-password"
                onClick={() => setShowPassword((v) => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-muted-foreground hover:text-foreground transition-colors duration-200"
                aria-label={showPassword ? "Скрыть пароль" : "Показать пароль"}
              >
                {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
              </button>
            </div>
            <button
              data-testid="submit-auth"
              disabled={submitting} type="submit"
              className="w-full btn-pill bg-primary text-primary-foreground shadow-lg shadow-primary/25 disabled:opacity-60"
            >
              {submitting ? "..." : mode === "login" ? "Войти" : "Создать аккаунт"}
            </button>
          </form>

          <div className="flex items-center gap-3 my-5">
            <div className="flex-1 h-px bg-border" />
            <span className="text-xs text-muted-foreground uppercase tracking-widest">или</span>
            <div className="flex-1 h-px bg-border" />
          </div>

          <button
            data-testid="google-auth"
            onClick={doGoogle}
            className="w-full btn-pill bg-card border border-border hover:bg-muted"
          >
            <Sparkles className="w-4 h-4 mr-2" />
            Продолжить с Google
          </button>

          <p className="text-xs text-muted-foreground mt-6 text-center leading-relaxed">
            Продолжая, вы соглашаетесь с Правилами и Политикой конфиденциальности.
          </p>
        </div>
      </div>
    </div>
  );
}
