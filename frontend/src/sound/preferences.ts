export interface SoundPreferences { enabled: boolean; volume: number }
export const preferenceKey = 'geopolitics.sound.v1';
export const defaults: Readonly<SoundPreferences> = { enabled: false, volume: 0.35 };
export const volumeBound = (value: number) => Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : defaults.volume;
export function parsePreferences(raw: string | null): SoundPreferences {
  try {
    const value = JSON.parse(raw ?? 'null');
    if (!value || Object.keys(value).sort().join(',') !== 'enabled,volume'
      || typeof value.enabled !== 'boolean' || typeof value.volume !== 'number' || !Number.isFinite(value.volume)) return { ...defaults };
    return { enabled: value.enabled, volume: volumeBound(value.volume) };
  } catch { return { ...defaults }; }
}
/** Only this fixed, non-sensitive preference record may use browser storage. */
export function loadPreferences(): SoundPreferences {
  try { return parsePreferences(window.localStorage.getItem(preferenceKey)); } catch { return { ...defaults }; }
}
export function savePreferences(value: SoundPreferences): void {
  try { window.localStorage.setItem(preferenceKey, JSON.stringify({ enabled: value.enabled, volume: volumeBound(value.volume) })); } catch { /* Private mode/storage denial: keep in memory. */ }
}
