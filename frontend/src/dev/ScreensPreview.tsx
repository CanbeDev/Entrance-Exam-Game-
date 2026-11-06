import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import type { GameController } from '../game/controller.ts';
import { AppView } from '../App.tsx';
import { screenFixture, screenModes } from './screen-fixtures.ts';
import type { ScreenMode } from './screen-fixtures.ts';
import { fixtureNarration } from './board-fixtures.ts';

function ScreensPreview() {
  const [mode, setMode] = useState<ScreenMode>(() => {
    const value = new URLSearchParams(window.location.search).get('fixture');
    return screenModes.includes(value as ScreenMode) ? value as ScreenMode : 'landing';
  });
  const [notice, setNotice] = useState('Presentation fixtures only. No authentication, gameplay or provider is connected.');
  const { state, screen } = screenFixture(mode);
  const record = (message: string) => { setNotice(`Offline callback: ${message}. No request was sent.`); };
  const controller = { getSnapshot: () => state,
    api: { battleCommentary: async (_game: string, revision: number) => ({ ...fixtureNarration(), revision,
      action_id: state.events.find(entry => entry.revision === revision)?.action_id ?? 'offline-unrecorded' }),
      generateBattleCommentary: async () => { record('commentary generation'); return fixtureNarration(); },
      commentaryPreference: async (gameId: string) => ({ game_id: gameId, mode: 'browser', enabled: false, version: 0, activation_revision: null }),
      events: async () => ({ events: [], after_revision: state.game?.revision ?? 0, next_after_revision: state.game?.revision ?? 0, has_more: false }) },
    authenticate: (_credentials: unknown, register: boolean) => record(register ? 'register and log in' : 'log in'),
    logout: () => record('logout'), create: () => record('create game'), dashboard: () => record('search games'),
    page: () => record('change page'), openGame: () => record('open public game'), initialize: () => record('reconnect'),
    refresh: () => record('check game status'), act: () => record('game action'), stepNpc: () => record('NPC step'),
    fastForward: () => record('fast-forward'), pause: () => record('Pause'), checkPendingNpc: () => record('read-only confirmation'),
    retryPending: () => record('explicit saved retry'), moreHistory: () => record('read history'),
  } as unknown as GameController;
  return <><aside className="geo-ui" style={{ padding: 16 }} aria-label="Isolated developer preview">
    <strong>Stage 8 · isolated development fixtures only</strong>
    <label>Fixture state <select data-fixture value={mode} onChange={event => { setMode(event.target.value as ScreenMode); setNotice('Presentation fixture changed. No request was sent.'); }}>
      {screenModes.map(value => <option key={value} value={value}>{value}</option>)}
    </select></label><p data-preview-callback role="status">{notice}</p>
  </aside><AppView key={mode} state={state} controller={controller} now={0} origin={window.location.origin} screen={screen} /></>;
}
if (!import.meta.env.DEV) throw new Error('The screens preview is development-only.');
createRoot(document.getElementById('root')!).render(<ScreensPreview />);
