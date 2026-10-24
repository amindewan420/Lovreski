import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Smartphone, History, Send } from "lucide-react";
import { adminApi } from "@/lib/adminApi";
import { pushSupported, isIOSNonStandalone, registerAndSyncToken, ADMIN_TOKEN_KEY } from "@/hooks/usePushNotifications";
import { BottomSheet } from "@/components/lovreski/BottomSheet";

const errMsg = (e) => e?.response?.data?.detail || e?.message || "Ошибка";

export const AdminDeviceCard = ({ ready, devices, onChange }) => {
  const [on, setOn] = useState(() => !!localStorage.getItem(ADMIN_TOKEN_KEY) && typeof Notification !== "undefined" && Notification.permission === "granted");
  const [busy, setBusy] = useState(false);
  const enable = async () => {
    if (!pushSupported()) return toast.error("Браузер не поддерживает Web Push");
    if (isIOSNonStandalone()) return toast.error("На iPhone сначала добавьте сайт на главный экран");
    setBusy(true);
    try {
      if ((await Notification.requestPermission()) !== "granted") throw new Error("Разрешение на уведомления отклонено");
      await registerAndSyncToken({ admin: true });
      setOn(true); onChange?.();
      toast.success("Админ-уведомления включены на этом устройстве");
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  const disable = async () => {
    const token = localStorage.getItem(ADMIN_TOKEN_KEY);
    try { if (token) await adminApi.delete("/admin/push/token", { data: { token } }); } catch { /* noop */ }
    localStorage.removeItem(ADMIN_TOKEN_KEY);
    setOn(false); onChange?.();
    toast.success("Отключено");
  };
  const test = async () => {
    try { const { data } = await adminApi.post("/admin/push/test-self"); toast.success(`Отправлено на ${data.sent || 0} устр.`); }
    catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div className="p-5 rounded-2xl bg-card border border-border" data-testid="admin-device-card">
      <div className="flex items-center gap-2 mb-1"><Smartphone className="w-4 h-4 text-primary" /><h3 className="font-display font-bold">Уведомления администратора</h3></div>
      <p className="text-xs text-muted-foreground mb-3">Новые чеки, запросы на возврат, жалобы, а также входы и блокировки админ-панели. Подключено устройств: <b data-testid="admin-devices-count">{devices ?? 0}</b></p>
      {!ready ? (
        <p className="text-xs p-3 rounded-xl bg-muted text-muted-foreground">Сначала настройте Firebase в карточках «Service account» и «Web app config».</p>
      ) : on ? (
        <div className="grid grid-cols-2 gap-2">
          <button data-testid="admin-device-test" onClick={test} className="py-2.5 rounded-full bg-muted font-semibold text-sm">🧪 Тест</button>
          <button data-testid="admin-device-disable" onClick={disable} className="py-2.5 rounded-full bg-muted font-semibold text-sm">Отключить</button>
        </div>
      ) : (
        <button data-testid="admin-device-enable" disabled={busy} onClick={enable} className="w-full py-2.5 rounded-full bg-primary text-primary-foreground font-semibold text-sm disabled:opacity-60">
          {busy ? "..." : "Включить на этом устройстве"}
        </button>
      )}
    </div>
  );
};

const STATUS = { sent: "✓ доставлено", sending: "⏳ отправка", "no-tokens": "нет устройств", "not-configured": "push не настроен", "pref-disabled": "отключено пользователем", failed: "ошибка" };

export const PushHistoryCard = ({ refreshKey }) => {
  const [items, setItems] = useState([]);
  useEffect(() => { adminApi.get("/admin/push/history").then((r) => setItems(r.data || [])).catch(() => {}); }, [refreshKey]);
  return (
    <div className="p-5 rounded-2xl bg-card border border-border" data-testid="push-history">
      <div className="flex items-center gap-2 mb-3"><History className="w-4 h-4 text-primary" /><h3 className="font-display font-bold">История отправок</h3></div>
      {items.length === 0 && <p className="text-sm text-muted-foreground">Пока ничего не отправлялось</p>}
      <div className="space-y-2 max-h-96 overflow-y-auto">
        {items.map((h) => (
          <div key={h.id} data-testid={`push-history-${h.id}`} className="p-3 rounded-xl bg-muted text-sm">
            <div className="flex justify-between gap-2">
              <p className="font-semibold truncate">{h.kind === "announcement" ? "📣" : "✉️"} {h.title}</p>
              <span className="text-[11px] text-muted-foreground shrink-0">{new Date(h.created_at).toLocaleString("ru", { dateStyle: "short", timeStyle: "short" })}</span>
            </div>
            <p className="text-xs text-muted-foreground line-clamp-2">{h.body}</p>
            <p className="text-[11px] mt-1">
              <b>{h.target}</b> · {STATUS[h.status] || h.status} · push: {h.sent || 0} устр.{h.in_app != null ? ` · в приложении: ${h.in_app}` : ""}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
};

export const DirectPushSheet = ({ target, onClose }) => {
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { setTitle(""); setBody(""); }, [target]);
  const send = async () => {
    if (!title.trim() || !body.trim()) return toast.error("Заполните заголовок и текст");
    setBusy(true);
    try {
      const { data } = await adminApi.post(`/admin/push/user/${target.user_id}`, { title, body });
      toast.success(data.push?.sent ? `Push доставлен на ${data.push.sent} устр.` : "Сохранено в уведомлениях (push-устройств нет)");
      onClose();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  return (
    <BottomSheet open={!!target} onClose={onClose} title={`Push · ${target?.name || ""}`} testId="direct-push-sheet">
      <input data-testid="direct-push-title" value={title} maxLength={100} onChange={(e) => setTitle(e.target.value)} placeholder="Заголовок" className="w-full px-3 py-2.5 rounded-xl bg-muted border border-border text-sm mb-2" />
      <textarea data-testid="direct-push-body" value={body} maxLength={300} rows={4} onChange={(e) => setBody(e.target.value)} placeholder="Текст сообщения" className="w-full px-3 py-2.5 rounded-xl bg-muted border border-border text-sm" />
      <button data-testid="direct-push-send" disabled={busy} onClick={send} className="mt-3 w-full py-3 rounded-full bg-primary text-primary-foreground font-semibold flex items-center justify-center gap-2 disabled:opacity-60">
        <Send className="w-4 h-4" /> {busy ? "..." : "Отправить"}
      </button>
    </BottomSheet>
  );
};
