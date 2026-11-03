// Settings → Sound & Audio: master toggle, volume, output device (🎧), test sound, mic preference.
import { useEffect, useState } from "react";
import { Headphones, Volume2, Mic, Play, Music } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import { useI18n } from "@/lib/i18n";
import { useSoundPrefs } from "@/components/lovreski/SoundManager";
import { RINGTONES, canPickOutput, getSinkId, listOutputDevices, playSound, setOutputDevice } from "@/lib/sound";

export const SoundSettings = () => {
  const { t } = useI18n();
  const [prefs, update] = useSoundPrefs();
  const [vol, setVol] = useState(prefs.soundVolume);
  const [devices, setDevices] = useState([]);
  const [showDevices, setShowDevices] = useState(false);
  const [sink, setSink] = useState(getSinkId());
  useEffect(() => setVol(prefs.soundVolume), [prefs.soundVolume]);

  const openDevices = async () => {
    if (!showDevices) setDevices(await listOutputDevices());
    setShowDevices((s) => !s);
  };
  const pick = async (id) => { setSink(id); await setOutputDevice(id); };
  const off = !prefs.soundEnabled;

  return (
    <div data-testid="sound-settings">
      <div className="flex justify-between items-center px-4 py-3 text-sm">
        <span className="flex items-center gap-2"><Volume2 className="w-4 h-4" /> {t("sound.enable")}</span>
        <Switch data-testid="sound-toggle" checked={prefs.soundEnabled} onCheckedChange={(v) => update({ soundEnabled: v })} />
      </div>
      <div className={`px-4 py-3 text-sm ${off ? "opacity-50" : ""}`}>
        <div className="flex justify-between mb-2">
          <span>{t("sound.volume")}</span>
          <span data-testid="sound-volume-value" className="font-semibold">{vol}%</span>
        </div>
        <Slider data-testid="sound-volume-slider" disabled={off} min={0} max={100} step={5} value={[vol]}
          onValueChange={([v]) => setVol(v)} onValueCommit={([v]) => update({ soundVolume: v })} />
      </div>
      <div className={`flex justify-between items-center gap-2 px-4 py-3 text-sm ${off ? "opacity-50" : ""}`}>
        <button data-testid="sound-output-btn" disabled={off} onClick={openDevices} className="flex items-center gap-2 disabled:cursor-not-allowed">
          <Headphones className="w-4 h-4" /> {t("sound.output")}
        </button>
        <button data-testid="sound-test-btn" disabled={off} onClick={() => playSound("incoming", { force: true, volume: vol })}
          className="btn-pill bg-muted text-xs !py-1.5 flex items-center gap-1 disabled:cursor-not-allowed">
          <Play className="w-3 h-3" /> {t("sound.test")}
        </button>
      </div>
      {showDevices && !off && (
        <div data-testid="sound-device-list" className="px-4 pb-3 space-y-1 text-sm">
          {!canPickOutput() || devices.length < 2 ? (
            <p data-testid="sound-device-unsupported" className="text-xs text-muted-foreground">{t("sound.output_default")}</p>
          ) : devices.map((d, i) => (
            <label key={d.deviceId || i} className="flex items-center gap-2 py-1 cursor-pointer">
              <input type="radio" name="sink" data-testid={`sound-device-${i}`} className="accent-primary"
                checked={(sink || "default") === d.deviceId || (!sink && i === 0)} onChange={() => pick(d.deviceId === "default" ? "" : d.deviceId)} />
              <span className="truncate">{d.label || `${t("sound.device")} ${i + 1}`}</span>
            </label>
          ))}
        </div>
      )}
      <div className={`px-4 py-3 text-sm ${off ? "opacity-50" : ""}`}>
        <p className="flex items-center gap-2 mb-2"><Music className="w-4 h-4" /> {t("sound.ringtone")}</p>
        <div className="grid grid-cols-3 sm:grid-cols-5 gap-1.5" data-testid="ringtone-list">
          {Object.keys(RINGTONES).map((k) => {
            const active = prefs.ringtone === k;
            return (
              <button key={k} data-testid={`ringtone-${k}`} disabled={off} aria-pressed={active}
                onClick={() => { playSound("incoming", { force: true, volume: vol, ringtone: k }); if (!active) update({ ringtone: k }); }}
                className={`py-2 px-1 truncate rounded-xl text-xs font-semibold border transition-colors duration-200 disabled:cursor-not-allowed ${active ? "bg-primary text-primary-foreground border-primary" : "bg-muted border-transparent hover:border-primary/40"}`}>
                {t(`sound.tone.${k}`)}
              </button>
            );
          })}
        </div>
      </div>
      <div className="flex justify-between items-center px-4 py-3 text-sm">
        <span className="flex items-center gap-2"><Mic className="w-4 h-4" /> {t("sound.mic")}</span>
        <Switch data-testid="mic-toggle" checked={prefs.micEnabled} onCheckedChange={(v) => update({ micEnabled: v })} />
      </div>
    </div>
  );
};
