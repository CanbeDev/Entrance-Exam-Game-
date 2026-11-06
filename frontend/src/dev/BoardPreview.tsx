import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import type { GameController } from '../game/controller.ts';
import { AppView } from '../App.tsx';
import { boardFixture, boardModes, fixtureNarration } from './board-fixtures.ts';
import type { BoardMode } from './board-fixtures.ts';
import { battleFixture, battleModes, advanceBattleFixture } from './battle-fixtures.ts';
import type { BattleMode } from './battle-fixtures.ts';
import { chronicleFixture, chronicleModes } from './chronicle-fixtures.ts';
import type { ChronicleMode } from './chronicle-fixtures.ts';
import { NpcAcceptanceTools } from './NpcAcceptanceTools.tsx';
import { SoundTestPanel } from './SoundTestPanel.tsx';

const previewModes = [...boardModes, ...battleModes, ...chronicleModes];
type PreviewMode = BoardMode | BattleMode | ChronicleMode;

function BoardPreview() {
  const [mode, setMode] = useState<PreviewMode>(() => {
    const requested = new URLSearchParams(window.location.search).get('fixture');
    return previewModes.includes(requested as PreviewMode) ? requested as PreviewMode : 'human';
  });
  const [exchangeAdvanced, setExchangeAdvanced] = useState(false);
  const [notice, setNotice] = useState('All gameplay buttons are inert offline callbacks. Use the fixture selector to change state.');
  const [forward, setForward] = useState<boolean | null>(null);
  const [transition, setTransition] = useState<'none' | 'complete' | 'capture'>('none');
  const [limit, setLimit] = useState<number | null>(null);
  const base = chronicleModes.includes(mode as ChronicleMode) ? chronicleFixture(mode as ChronicleMode)
    : battleModes.includes(mode as BattleMode) ? battleFixture(mode as BattleMode) : boardFixture(mode as BoardMode);
  const fixture = transition !== 'none' ? boardFixture(transition === 'complete' ? 'completed' : 'conquest') : exchangeAdvanced ? advanceBattleFixture(base) : base;
  if (transition !== 'none' && fixture.game) {
    fixture.game = { ...fixture.game, revision: 13 };
    const events = transition === 'complete'
      ? [{ type: 'victory' as const, actor_id: fixture.game.winner!, round: fixture.game.round!, turn_sequence: fixture.game.turn_sequence! }]
      : [{ type: 'conquered' as const, actor_id: 'player-0', source_id: 'brazil', target_id: 'canada', amount: 2, round: fixture.game.round!, turn_sequence: fixture.game.turn_sequence! }];
    fixture.events = [...base.events, { revision: 13, action_id: `offline-preview-${transition}-13`,
      actor: { player_id: 'player-0', kind: 'human' }, committed_at: '2026-11-03T00:00:00Z', events }];
    fixture.lastResult = { state: fixture.game, events };
  }
  const state = { ...fixture, fastForward: forward ?? fixture.fastForward, npcAttemptBudget: limit ?? fixture.npcAttemptBudget };
  // Match the controller's synchronous snapshot update for local playback cues.
  let currentForward = state.fastForward;
  const record = () => { setNotice('Offline callback observed. No gameplay or network operation was submitted.'); };
  const controller = {
    getSnapshot: () => ({ ...state, fastForward: currentForward }),
    api: { battleCommentary: async (_id: string, revision: number) => ({...fixtureNarration(),revision,action_id:state.events.find(e=>e.revision===revision)?.action_id ?? 'offline-dice-exchange'}), generateBattleCommentary: async () => fixtureNarration(),
      events: async () => ({ events: [], after_revision: 12, next_after_revision: null, has_more: false }) },
    act: record, stepNpc: record, fastForward: () => { currentForward = true; setForward(true); record(); }, pause: () => { currentForward = false; setForward(false); record(); },
    refresh: record, checkPendingNpc: record, retryPending: record, configureNpcBudget: (value: number) => { if (Number.isSafeInteger(value) && value >= 0) setLimit(value); record(); }, authenticate: record,
    initialize: record, logout: record, moreHistory: record, openGame: record,
  } as unknown as GameController;
  return <>
    <div className="geo-ui" style={{ padding: 16 }}>
      <p><strong>Stage 7 · isolated development fixtures only</strong></p>
      <label>Fixture state <select value={mode} onChange={event => { setMode(event.target.value as PreviewMode); setForward(null); setLimit(null); setTransition('none'); setExchangeAdvanced(false); }}>
        {previewModes.map(value => <option key={value} value={value}>{value}</option>)}
      </select></label>
      <p role="status">{notice}</p>
      <NpcAcceptanceTools state={state} controller={controller} />
      <SoundTestPanel />
      {battleModes.includes(mode as BattleMode) && !exchangeAdvanced && state.game?.battle && !state.pending && <button onClick={()=>setExchangeAdvanced(true)}>Preview one newly committed exchange</button>}
      {mode === 'human' && transition === 'none' && <div><button onClick={() => setTransition('complete')}>Preview confirmed victory transition</button>
        <button onClick={() => setTransition('capture')}>Preview confirmed conquest transition</button></div>}
      <p>In human, choose Attack from, then Attack target to review each local selection state. In conquest, select Transfer soldiers.
        In npc-fast-forward or npc-in-flight, test Pause. These controls submit no requests.</p>
    </div>
    <AppView key={mode} state={state} controller={controller} now={0} origin="http://127.0.0.1:5175" />
  </>;
}
if (!import.meta.env.DEV) throw new Error('The board preview is development-only.');
createRoot(document.getElementById('root')!).render(<BoardPreview />);
