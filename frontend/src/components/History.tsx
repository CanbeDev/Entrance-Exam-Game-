import type { GameApi, PublicActionResult, PublicCommittedAction, PublicGame, PublicGameEvent } from '../api/index.ts';
import { useEffect, useRef, useState } from 'react';
import { participantName } from '../game/view.ts';
import { BattleCommentaryPanel } from './BattleCommentary.tsx';
import { NewBattleCommentary } from '../api/live-commentary.ts';
import type { LiveCommentaryUpdate } from '../api/live-commentary.ts';
import { BattleExchange } from './BattleExchange.tsx';
import { createExchangeLedger } from './battle-view.ts';
import { chronicleEntries, chronicleWindow, receiptRound, receiptTime } from './chronicle-view.ts';
import './chronicle.css';
import { participantCountryName } from './refresh-view.ts';
import { actionSummary } from './gameplay-view.ts';

const names: Record<PublicGameEvent['type'], string> = {
  attack_started: 'Attack started', dice_exchange: 'Dice exchange', conquered: 'Country conquered',
  eliminated: 'Participant eliminated', victory: 'Victory', transferred: 'Soldiers transferred',
  allocated: 'Reinforcements allocated', attack_stopped: 'Attack stopped', attack_failed: 'Attack ended',
  turn_ended: 'Turn ended', turn_started: 'Turn started',
};
function Event({ event, game }: { event: PublicGameEvent; game: PublicGame }) {
  const country = (id: string | null | undefined) => game.countries?.find((c) => c.id === id)?.name ?? id;
  return <li>
    <strong>{names[event.type]}</strong> — {participantName(game, event.actor_id)}
    {event.source_id && <span> · {country(event.source_id)}{event.target_id && ` → ${country(event.target_id)}`}</span>}
    {event.amount != null && <span> · {event.amount} soldiers</span>}
    {event.type === 'dice_exchange' && <>
      <p>Attacker dice: {event.attacker_dice?.join(', ') || '—'}. Defender dice: {event.defender_dice?.join(', ') || '—'}.</p>
      <p>Attacker losses: {event.attacker_losses ?? 'not recorded'}. Defender losses: {event.defender_losses ?? 'not recorded'}.</p>
    </>}
    {!!event.allocations?.length && <ul>{event.allocations.map((allocation) => <li key={allocation.country_id}>
      {country(allocation.country_id)}: {allocation.amount}
    </li>)}</ul>}
  </li>;
}
export function History({ game, events, latest, more, disabled, loadMore, api, gameId, canGenerateCommentary,
  commentaryAccountId, liveCommentaryAllowed, canStartCommentary }: {
  game: PublicGame; events: readonly PublicCommittedAction[]; latest: PublicActionResult | null;
  more: boolean; disabled: boolean; loadMore: () => void;
  api: GameApi; gameId: string; canGenerateCommentary: boolean;
  commentaryAccountId: string | null; liveCommentaryAllowed: boolean;
  canStartCommentary: () => boolean;
}) {
  const [automatic, setAutomatic] = useState(true);
  const [battleLedger] = useState(() => createExchangeLedger(game.revision));
  const previousGame = useRef<PublicGame | null>(null);
  useEffect(() => { previousGame.current = game; }, [game]);
  const permission = useRef(canStartCommentary);
  permission.current = canStartCommentary;
  const [liveResults, setLiveResults] = useState<ReadonlyMap<number, LiveCommentaryUpdate>>(() => new Map());
  const [live] = useState(() => new NewBattleCommentary(
    (id, revision, permitted) => api.generateBattleCommentary(id, revision, permitted),
    (revision, display) => setLiveResults((previous) => {
      const results = new Map(previous); results.delete(revision); results.set(revision, display);
      if (results.size > 64) results.delete(results.keys().next().value!);
      return results;
    }),
    (id, after) => api.events(id, { after_revision: after, limit: 100 }), game.revision ?? 0,
    () => permission.current(),
  ));
  useEffect(() => {
    live.contextChanged(gameId, commentaryAccountId, liveCommentaryAllowed);
    if (!live.active) setAutomatic(false);
    live.observe(game.revision ?? 0);
  }, [live, gameId, commentaryAccountId, liveCommentaryAllowed, game, automatic]);
  useEffect(() => () => live.dispose(), [live]);
  const [collapsed, setCollapsed] = useState(false);
  const [page, setPage] = useState(0);
  const entries = chronicleEntries(events, [...liveResults.values()].flatMap(display => display.entry ? [display.entry] : []));
  const window = chronicleWindow(entries, page);
  const latestRecorded = latest && entries.some(entry => entry.revision === latest.state.revision);
  return <section className="geo-chronicle" aria-labelledby="history-title">
    <header className="geo-chronicle__header"><div><span className="geo-label">Campaign record</span>
      <h2 id="history-title">Chronicle</h2></div>
      <button aria-expanded={!collapsed} aria-controls="chronicle-content" onClick={() => setCollapsed(value => !value)}>{collapsed ? 'Expand Chronicle' : 'Collapse Chronicle'}</button>
    </header>
    <p className="geo-help">Committed history · Latest moves first. {entries.length} loaded {entries.length === 1 ? 'move' : 'moves'}{more ? '; earlier records available' : ''}.</p>
    <div id="chronicle-content" hidden={collapsed}>
    {commentaryAccountId && (canGenerateCommentary || automatic) && <details className="geo-chronicle__settings">
      <summary>Commentary settings</summary>
      <label><input type="checkbox" checked={automatic} disabled={!automatic && !liveCommentaryAllowed}
        onChange={(event) => {
          if (event.currentTarget.checked) {
            live.contextChanged(gameId, commentaryAccountId, liveCommentaryAllowed);
            setAutomatic(live.enable(game.revision ?? 0));
          } else { live.disable(); setAutomatic(false); }
        }} /> Commentary for new battles</label>
      <p>New exchanges are narrated when commentary is available. Gameplay continues while it is prepared.
        Turning it off stops queued narration; a request already sent may finish.</p>
      {liveResults.get(0)?.error && <p role="status">Commentary is unavailable. Gameplay can continue.</p>}
    </details>}
    {latest && !latestRecorded && <section className="geo-chronicle__latest" aria-label="Latest submitted move">
      <h3>Latest move</h3>
      <ul>{latest.events.map((event, i) => <Event event={event} game={game} key={i} />)}</ul>
      {latest.npc_decision && <aside className="geo-chronicle__reason"><h4>{participantCountryName(game, latest.events[0]?.actor_id)}’s Strategy</h4><p>{latest.npc_decision.explanation}</p></aside>}
    </section>}
    {entries.length === 0 && <p>No committed moves yet.</p>}
    <ol className="geo-chronicle__entries" aria-label="Committed moves, latest first">
      {window.entries.map((entry, index) => <ChronicleEntry key={`${gameId}:${entry.revision}:${entry.action_id}`} entry={entry}
        initiallyOpen={index === 0 && window.page === 0} game={game} gameId={gameId} api={api}
        ledger={battleLedger} previous={previousGame.current} canGenerate={canGenerateCommentary}
        automatic={liveResults.get(entry.revision)} permitted={() => permission.current()} />)}
    </ol>
    <nav className="geo-chronicle__pages" aria-label="Chronicle pages">
      {window.page > 0 && <button onClick={() => setPage(0)}>Latest moves</button>}
      {window.page > 1 && <button onClick={() => setPage(window.page - 1)}>Newer loaded moves</button>}
      {window.page < window.last && <button onClick={() => setPage(window.page + 1)}>Earlier loaded moves</button>}
      {more && window.page === window.last && <button disabled={disabled} onClick={loadMore}>Load more history</button>}
    </nav>
    </div>
  </section>;
}

function ChronicleEntry({ entry, initiallyOpen, game, gameId, api, ledger, previous, canGenerate, automatic, permitted }: {
  entry: PublicCommittedAction; initiallyOpen: boolean; game: PublicGame; gameId: string; api: GameApi;
  ledger: ReturnType<typeof createExchangeLedger>; previous: PublicGame | null; canGenerate: boolean;
  automatic?: LiveCommentaryUpdate; permitted: () => boolean;
}) {
  const [open, setOpen] = useState(initiallyOpen);
  const [visited, setVisited] = useState(initiallyOpen);
  const round = receiptRound(entry), time = receiptTime(entry.committed_at);
  return <li className="geo-chronicle__entry" data-receipt={`${gameId}:${entry.revision}:${entry.action_id}`}>
    <details open={open} onToggle={event => {
      const expanded = event.currentTarget.open; setOpen(expanded); if (expanded) setVisited(true);
    }}>
      <summary><span className="geo-chronicle__meta">{round !== null ? `Round ${round} · ` : ''}Move {entry.revision}</span>
        <span className="geo-chronicle__actor">{participantName(game, entry.actor.player_id)}</span>
        <span className="geo-chronicle__summary">{entry.events.map(event => actionSummary(game, event)).join(' ') || 'Event details not recorded'}</span>
      </summary>
      {visited && <div className="geo-chronicle__body">
        {time && <time className="geo-help" dateTime={entry.committed_at}>{time}</time>}
        <ul className="geo-chronicle__events">{entry.events.map((event, i) => event.type === 'dice_exchange'
          ? <li key={i}><BattleExchange game={game} entry={entry} index={i} gameId={gameId} ledger={ledger} previous={previous} /></li>
          : <Event event={event} game={game} key={i} />)}</ul>
        {entry.npc_decision?.explanation && <aside className="geo-chronicle__reason" aria-label="Recorded strategic reasoning">
          <h4>{participantCountryName(game, entry.actor.player_id)}’s Strategy</h4><p className="geo-saved-justification">{entry.npc_decision.explanation}</p></aside>}
        {entry.events.some(event => event.type === 'dice_exchange') && <BattleCommentaryPanel
          api={api} gameId={gameId} game={game} entry={entry} canGenerate={canGenerate}
          automatic={automatic} permitted={permitted} />}
      </div>}
    </details>
  </li>;
}
