import { useEffect, useRef, useState } from 'react';
import type { AppState } from '../game/controller.ts';
import { SoundService } from './service.ts';
import { SoundLedger } from './events.ts';
import { defaults, loadPreferences, savePreferences } from './preferences.ts';
import type { SoundEvent } from './assets.ts';
import './sound.css';
// One service/ledger for this page, not per board/revision/Chronicle component.
export const pageSound = new SoundService(undefined, undefined, () => {
  for (const notify of listeners) notify();
});
const ledger = new SoundLedger(), listeners = new Set<() => void>();
export const uiSound = (event: SoundEvent) => { pageSound.play(event, { important: event === 'pause' }); };
export function SoundSettings() {
  const [preferences, setPreferences] = useState({ ...defaults });
  const [activated, setActivated] = useState(false), [message, setMessage] = useState('');
  useEffect(() => {
    const loaded = loadPreferences(); setPreferences(loaded); pageSound.configure(loaded);
    setActivated(pageSound.inspect().activated);
    const unsubscribe = pageSound.subscribe(() => setActivated(pageSound.inspect().activated));
    const notify = () => setMessage('Sound could not play. Gameplay is unaffected.');
    listeners.add(notify); return () => { unsubscribe(); listeners.delete(notify); pageSound.stop(); };
  }, []);
  function enable() { pageSound.activate(); setActivated(true); setMessage(''); }
  return <details className="geo-sound" id="sound-settings"><summary>Sound {preferences.enabled ? 'on' : 'off'}</summary>
    <fieldset><legend>Sound effects</legend>
      <label><input type="checkbox" checked={preferences.enabled} onChange={event => {
        const next = { ...preferences, enabled: event.currentTarget.checked };
        if (next.enabled) enable(); setPreferences(next); savePreferences(next); pageSound.configure(next);
        if (next.enabled) uiSound('select');
      }} /> Sound on</label>
      <label>Effects volume <input type="range" min={0} max={100} step={1} value={Math.round(preferences.volume * 100)} onChange={event => {
        const next = { ...preferences, volume: Number(event.target.value) / 100 };
        setPreferences(next); savePreferences(next); pageSound.configure(next);
      }} /></label>
      {preferences.enabled && !activated && <button type="button" onClick={() => { enable(); uiSound('select'); }}>Enable playback in this tab</button>}
      <p className="geo-help">Optional effects. Sound starts only after you enable playback in this tab.</p>
      {message && <p role="status">{message}</p>}
    </fieldset>
  </details>;
}
export function GameplaySound({ state }: { state: AppState }) {
  const lastError = useRef<string | null>(null);
  const mounted = useRef(false);
  useEffect(() => {
    if (!mounted.current) { ledger.baseline(state); lastError.current = state.error; mounted.current = true; }
    const reduced = typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    for (const cue of ledger.observe(state)) {
      if (cue.event === 'dice' && cue.id) pageSound.exchange(cue.id, cue.after, !!cue.rapid, reduced);
      else pageSound.play(cue.event, { rapid: cue.rapid, important: cue.important });
    }
    if (state.error && state.error !== lastError.current) pageSound.play('error');
    lastError.current = state.error;
  }, [state]);
  return null;
}
