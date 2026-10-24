import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Shield, Mail, Lock, Eye, EyeOff, Loader2, AlertCircle } from "lucide-react";
import { adminApi, setAdminToken, verifyAdminToken } from "@/lib/adminApi";
import { AdminCheckingScreen } from "@/components/admin/AdminProtectedRoute";

const errorText = (e) => {
  const d = e?.response?.data?.detail;
  if (e?.response?.status === 401) return "Invalid email or password";
  if (typeof d === "string") return d;
  return "Не удалось войти. Попробуйте ещё раз.";
};

export default function AdminLogin() {
  const nav = useNavigate();
  const [checking, setChecking] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // Auto-login: valid stored token → straight to dashboard
  useEffect(() => {
    verifyAdminToken().then((ok) => (ok ? nav("/admin/dashboard", { replace: true }) : setChecking(false)));
  }, [nav]);

  const submit = async (e) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true); setError("");
    try {
      const { data } = await adminApi.post("/admin/login", { email: email.trim(), password });
      setAdminToken(data.token);
      nav("/admin/dashboard", { replace: true });
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  if (checking) return <AdminCheckingScreen />;
  return (
    <div className="min-h-screen bg-background flex items-center justify-center px-4">
      <form onSubmit={submit} data-testid="admin-login-form" className="w-full max-w-sm p-8 rounded-3xl bg-card border border-border shadow-xl">
        <div className="w-12 h-12 rounded-2xl bg-primary/15 text-primary flex items-center justify-center mb-5"><Shield className="w-6 h-6" /></div>
        <h1 className="font-display font-black text-2xl">Lovreski Admin</h1>
        <p className="text-sm text-muted-foreground mt-1 mb-6">Вход в панель администратора</p>

        <label className="block text-xs font-semibold text-muted-foreground mb-1">Email</label>
        <div className="relative mb-4">
          <Mail className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input data-testid="admin-login-email" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)}
            className="w-full pl-9 pr-3 py-2.5 rounded-xl bg-muted border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary/40" />
        </div>

        <label className="block text-xs font-semibold text-muted-foreground mb-1">Пароль</label>
        <div className="relative">
          <Lock className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input data-testid="admin-login-password" type={show ? "text" : "password"} autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)}
            className="w-full pl-9 pr-10 py-2.5 rounded-xl bg-muted border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary/40" />
          <button type="button" data-testid="admin-login-toggle-password" onClick={() => setShow((v) => !v)} className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 rounded-full hover:bg-background text-muted-foreground">
            {show ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          </button>
        </div>

        {error && (
          <div data-testid="admin-login-error" role="alert" className="mt-4 flex items-center gap-2 text-sm text-rose-600 bg-rose-500/10 border border-rose-500/20 rounded-xl px-3 py-2">
            <AlertCircle className="w-4 h-4 shrink-0" /> {error}
          </div>
        )}

        <button data-testid="admin-login-submit" type="submit" disabled={busy}
          className="mt-6 w-full py-3 rounded-full bg-primary text-primary-foreground font-semibold flex items-center justify-center gap-2 disabled:opacity-60 transition-opacity">
          {busy && <Loader2 className="w-4 h-4 animate-spin" />} Войти
        </button>
      </form>
    </div>
  );
}
