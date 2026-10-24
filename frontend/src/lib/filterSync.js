// Filter-change sync between Settings and Discover.
// SettingsPage stamps a signature on every save; DiscoverPage compares it on
// mount + window focus and auto-refreshes the pool when it changed.
export const FILTER_SIG_KEY = "lovreski_filters_sig";

export const currentFilterSig = (user) => JSON.stringify({
  age_min: user?.age_min ?? 18,
  age_max: user?.age_max ?? 85,
  distance_mode: user?.distance_mode || "unlimited",
  distance_km: user?.distance_km ?? 50,
});
