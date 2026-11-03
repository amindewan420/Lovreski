// App sounds (incoming / outgoing / match), synthesized with Web Audio — nothing loads until sound is enabled.
const SINK_KEY = "lovreski_sink";
export const DEFAULT_PREFS = { soundEnabled: false, soundVolume: 50, micEnabled: false };

let prefs = { ...DEFAULT_PREFS };
let ctx = null;

export const setSoundPrefs = (p) => { prefs = { ...DEFAULT_PREFS, ...(p || {}) }; };
export const getSinkId = () => localStorage.getItem(SINK_KEY) || "";
export const canPickOutput = () => typeof window.AudioContext !== "undefined" && "setSinkId" in AudioContext.prototype;

const getCtx = async () => {
  if (!ctx) {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    ctx = new AC();
    const sink = getSinkId();
    if (sink && ctx.setSinkId) { try { await ctx.setSinkId(sink); } catch { /* device gone → default */ } }
  }
  if (ctx.state === "suspended") { try { await ctx.resume(); } catch { /* needs a user gesture */ } }
  return ctx;
};

export const setOutputDevice = async (deviceId) => {
  localStorage.setItem(SINK_KEY, deviceId || "");
  if (ctx?.setSinkId) { try { await ctx.setSinkId(deviceId || ""); } catch { /* unsupported */ } }
};

export const listOutputDevices = async () => {
  try {
    const all = await navigator.mediaDevices.enumerateDevices();
    return all.filter((d) => d.kind === "audiooutput");
  } catch { return []; }
};

const TONES = {
  incoming: [[660, 0, 0.12], [880, 0.12, 0.18]],
  outgoing: [[520, 0, 0.08]],
  match: [[523, 0, 0.12], [659, 0.1, 0.12], [784, 0.2, 0.12], [1047, 0.3, 0.3]],
};

// `force` plays regardless of the toggle (used by the "Test sound" button).
export async function playSound(kind, { force = false, volume } = {}) {
  if (!force && !prefs.soundEnabled) return;
  const vol = (volume ?? prefs.soundVolume) / 100;
  if (vol <= 0) return;
  const ac = await getCtx();
  if (!ac) return;
  const t0 = ac.currentTime + 0.01;
  for (const [freq, at, dur] of TONES[kind] || TONES.incoming) {
    const osc = ac.createOscillator();
    const gain = ac.createGain();
    osc.type = "sine";
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0, t0 + at);
    gain.gain.linearRampToValueAtTime(0.35 * vol, t0 + at + 0.015);
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + at + dur);
    osc.connect(gain).connect(ac.destination);
    osc.start(t0 + at);
    osc.stop(t0 + at + dur + 0.02);
  }
}
