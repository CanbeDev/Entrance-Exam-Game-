import { soundUrl } from './assets.ts';
import type { SoundEvent } from './assets.ts';
import { defaults, volumeBound } from './preferences.ts';
import type { SoundPreferences } from './preferences.ts';
export interface Voice { volume: number; currentTime: number; readonly paused?: boolean; readonly readyState?: number; readonly ended?: boolean; play: () => Promise<void>; pause: () => void; onerror: HTMLMediaElement['onerror']; onended?: HTMLMediaElement['onended'] }
export type PlaybackPhase = 'idle' | 'muted' | 'activation-required' | 'throttled' | 'loading' | 'playing' | 'ended' | 'stopped' | 'blocked' | 'failed';
export interface PlaybackStatus { phase: PlaybackPhase; event: SoundEvent | null; message: string; currentTime: number; readyState: number; paused: boolean; volume: number; enabled: boolean; activated: boolean }
export class SoundService {
  private preferences = { ...defaults };
  private unlocked = false;
  private voice: Voice | null = null;
  private lastAt = -Infinity;
  private sequence = 0;
  private diceId: string | null = null;
  private after: SoundEvent | undefined;
  private phase: PlaybackPhase = 'idle';
  private event: SoundEvent | null = null;
  private message = '';
  private listeners = new Set<() => void>();
  private createVoice: (url: string) => Voice;
  private clock: () => number;
  private unavailable: () => void;
  constructor(createVoice: (url: string) => Voice = url => new Audio(url), clock = () => Date.now(), unavailable: () => void = () => {}) {
    this.createVoice = createVoice; this.clock = clock; this.unavailable = unavailable;
  }
  configure(preferences: SoundPreferences): void {
    this.preferences = { enabled: preferences.enabled, volume: volumeBound(preferences.volume) };
    if (!preferences.enabled || this.preferences.volume === 0) this.stop();
    if (this.voice) this.voice.volume = this.preferences.volume;
    this.notify();
  }
  activate(): void { this.unlocked = true; this.notify(); }
  get active() { return this.unlocked && this.preferences.enabled; }
  subscribe = (listener: () => void): (() => void) => { this.listeners.add(listener); return () => this.listeners.delete(listener); };
  inspect = (): PlaybackStatus => ({ phase: this.phase, event: this.event, message: this.message,
    currentTime: this.voice?.currentTime ?? 0, readyState: this.voice?.readyState ?? 0,
    paused: this.voice?.paused ?? true, volume: this.preferences.volume,
    enabled: this.preferences.enabled, activated: this.unlocked });
  private notify(): void { for (const listener of this.listeners) { try { listener(); } catch { /* Optional observers cannot break playback/gameplay. */ } } }
  private status(phase: PlaybackPhase, message = ''): void { this.phase = phase; this.message = message; this.notify(); }
  stop(): void {
    this.sequence++; this.diceId = null; this.after = undefined;
    try { this.voice?.pause(); } catch { /* Media is optional. */ }
    this.voice = null;
    this.status('stopped');
  }
  play(event: SoundEvent, { rapid = false, important = false }: { rapid?: boolean; important?: boolean } = {}): boolean {
    if (!this.preferences.enabled || this.preferences.volume === 0) { this.event = event; this.status('muted', 'Sound is off or volume is zero.'); return false; }
    if (!this.unlocked) { this.event = event; this.status('activation-required', 'Enable playback using a user action in this tab.'); return false; }
    const now = this.clock();
    if (!important && now - this.lastAt < (rapid ? 1200 : 160)) return false;
    this.stop(); this.lastAt = now;
    this.event = event; this.status('loading');
    const sequence = this.sequence;
    try {
      const voice = this.createVoice(soundUrl(event)); this.voice = voice; voice.volume = this.preferences.volume;
      const fail = (error?: unknown) => { if (sequence === this.sequence) {
        this.stop(); const blocked = error instanceof Error && error.name === 'NotAllowedError';
        this.status(blocked ? 'blocked' : 'failed', blocked ? 'The browser blocked playback. Enable sound with a user action.' : 'The audio asset could not be loaded or played.');
        try { this.unavailable(); } catch { /* Optional status UI is isolated. */ }
      } };
      voice.onerror = () => fail();
      voice.onended = () => {
        if (sequence !== this.sequence) return;
        const after = this.after; this.diceId = null; this.after = undefined;
        this.status('ended');
        if (after) this.play(after, { important: true });
      };
      void Promise.resolve(voice.play()).then(() => {
        if (sequence === this.sequence && !voice.ended) this.status('playing');
      }).catch(fail);
      return true;
    } catch { this.stop(); this.status('failed', 'The audio asset could not be loaded or played.'); try { this.unavailable(); } catch { /* Optional status UI. */ } return false; }
  }
  exchange(id: string, after: SoundEvent | undefined, rapid: boolean, reduced: boolean): void {
    if (!this.play('dice', { rapid })) return;
    this.diceId = id; this.after = rapid || reduced ? undefined : after;
    // Let the real clip play. One optional follow-up may run on natural media
    // completion, never on the animation deadline. Rapid/reduced playback omits
    // that follow-up. Any new cue/mute/Pause cancels it; gameplay never waits.
  }
  finishDice(id: string): void {
    if (this.diceId !== id) return;
    // Skip settles the visual only. It must not cut an unplayed/playing clip to
    // zero length, and must not schedule an extra sound for skipped animation.
    this.after = undefined;
  }
}
