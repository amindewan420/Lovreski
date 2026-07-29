import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Heart, Sparkles, Eye, EyeOff, KeyRound, X } from "lucide-react";

export default function Landing() {
  const nav = useNavigate();
  const { login, register } = useAuth();
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({
    email: "", password: "", name: "", gender: "female", dob: "1998-01-01",
  });
  const [submitting, setSubmitting] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  // Forgot-password state
  const [forgotOpen, setForgotOpen] = useState(false);
  const [forgotStep, setForgotStep] = useState(1); // 1: enter email → 2: OTP + new password
  const [forgot, setForgot] = useState({ email: "", otp: "", newPassword: "" });
  const [forgotShowPw, setForgotShowPw] = useState(false);
  const [forgotBusy, setForgotBusy] = useState(false);

  const openForgot = () => {
    // Auto-fill the email that was already typed on the login form
    setForgot({ email: form.email || "", otp: "", newPassword: "" });
    setForgotStep(1);
    setForgotOpen(true);
  };

  const requestOtp = async () => {
    if (!forgot.email) return toast.error("Введите email");
    setForgotBusy(true);
    try {
      const { data } = await api.post("/auth/forgot", { email: forgot.email });
      // MOCKED delivery: dev_otp is returned so we auto-fill it
      if (data.dev_otp) {
        setForgot((f) => ({ ...f, otp: data.dev_otp }));
        toast.success(`Код отправлен и авто-заполнен: ${data.dev_otp}`);
      } else {
        toast.success("Если аккаунт существует, код отправлен");
      }
      setForgotStep(2);
    } catch (err) {
      const status = err.response?.status;
      if (status === 429) toast.error("Слишком много запросов. Попробуйте через 15 минут");
      else toast.error(err.response?.data?.detail || "Ошибка");
    } finally { setForgotBusy(false); }
  };

  const doReset = async () => {
    if (!forgot.otp || forgot.newPassword.length < 6) return toast.error("Введите код и новый пароль (мин. 6 символов)");
    setForgotBusy(true);
    try {
      await api.post("/auth/reset", { email: forgot.email, otp: forgot.otp, new_password: forgot.newPassword });
      toast.success("Пароль обновлён! Войдите с новым паролем.");
      // Auto-fill login form with the new credentials for one-tap sign-in
      setForm((f) => ({ ...f, email: forgot.email, password: forgot.newPassword }));
      setForgotOpen(false);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Ошибка сброса");
    } finally { setForgotBusy(false); }
  };

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
            {mode === "login" && (
              <div className="text-center pt-1">
                <button
                  type="button"
                  data-testid="forgot-password"
                  onClick={openForgot}
                  className="text-sm text-primary hover:underline font-semibold"
                >
                  Забыли пароль?
                </button>
              </div>
            )}
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

      {/* Forgot password modal */}
      {forgotOpen && (
        <div
          data-testid="forgot-modal"
          className="fixed inset-0 z-[60] flex items-end sm:items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={() => !forgotBusy && setForgotOpen(false)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="w-full sm:max-w-md bg-card border-t sm:border sm:rounded-2xl border-border shadow-2xl p-6 rounded-t-3xl animate-in slide-in-from-bottom duration-200"
          >
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <div className="w-10 h-10 rounded-full bg-primary/15 flex items-center justify-center">
                  <KeyRound className="w-5 h-5 text-primary" />
                </div>
                <div>
                  <h3 className="font-display font-black text-lg">Сброс пароля</h3>
                  <p className="text-xs text-muted-foreground">{forgotStep === 1 ? "Введите ваш email" : "Введите код и новый пароль"}</p>
                </div>
              </div>
              <button
                data-testid="forgot-close"
                onClick={() => !forgotBusy && setForgotOpen(false)}
                className="p-1 rounded-full hover:bg-muted"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {forgotStep === 1 ? (
              <div className="space-y-3">
                <input
                  data-testid="forgot-email"
                  type="email"
                  placeholder="Email"
                  value={forgot.email}
                  onChange={(e) => setForgot({ ...forgot, email: e.target.value })}
                  className="w-full px-4 py-3 rounded-xl bg-muted border border-transparent focus:border-primary focus:bg-background outline-none transition-colors duration-200"
                />
                <button
                  data-testid="forgot-request"
                  disabled={forgotBusy}
                  onClick={requestOtp}
                  className="w-full btn-pill bg-primary text-primary-foreground disabled:opacity-60"
                >
                  {forgotBusy ? "..." : "Отправить код"}
                </button>
                <p className="text-[11px] text-muted-foreground text-center">
                  Служба доставки email в этой сборке МОКИРОВАНА — код будет показан на экране и авто-заполнен.
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="text-xs px-3 py-2 rounded-lg bg-secondary text-secondary-foreground">
                  Код для <b>{forgot.email}</b>. Не пришёл?{" "}
                  <button onClick={() => setForgotStep(1)} className="underline font-semibold">Отправить снова</button>
                </div>
                <input
                  data-testid="forgot-otp"
                  inputMode="numeric"
                  pattern="\d*"
                  maxLength={6}
                  placeholder="Код из 6 цифр"
                  value={forgot.otp}
                  onChange={(e) => setForgot({ ...forgot, otp: e.target.value.replace(/\D/g, "") })}
                  className="w-full px-4 py-3 rounded-xl bg-muted border border-transparent focus:border-primary focus:bg-background outline-none text-center tracking-[0.5em] font-display font-bold text-lg transition-colors duration-200"
                />
                <div className="relative">
                  <input
                    data-testid="forgot-new-password"
                    type={forgotShowPw ? "text" : "password"}
                    placeholder="Новый пароль (мин. 6)"
                    value={forgot.newPassword}
                    onChange={(e) => setForgot({ ...forgot, newPassword: e.target.value })}
                    className="w-full px-4 py-3 pr-12 rounded-xl bg-muted border border-transparent focus:border-primary focus:bg-background outline-none transition-colors duration-200"
                  />
                  <button
                    type="button"
                    data-testid="forgot-toggle-password"
                    onClick={() => setForgotShowPw((v) => !v)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-muted-foreground hover:text-foreground"
                    aria-label={forgotShowPw ? "Скрыть пароль" : "Показать пароль"}
                  >
                    {forgotShowPw ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                  </button>
                </div>
                <button
                  data-testid="forgot-submit"
                  disabled={forgotBusy}
                  onClick={doReset}
                  className="w-full btn-pill bg-primary text-primary-foreground disabled:opacity-60"
                >
                  {forgotBusy ? "..." : "Установить новый пароль"}
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
