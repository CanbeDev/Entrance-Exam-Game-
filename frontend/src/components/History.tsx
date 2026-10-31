import type { GameApi, PublicActionResult, PublicCommittedAction, PublicGame, PublicGameEvent } from '../api/index.ts';
import { useEffect, useRef, useState } from 'react';
import { participantName } from '../game/view.ts';
import { BattleCommentaryPanel } from './BattleCommentary.tsx';
import { NewBattleCommentary } from '../api/live-commentary.ts';
import type { LiveCommentaryUpdate } from '../api/live-commentary.ts';

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
      <p>Attacker losses: {event.attacker_losses ?? 0}. Defender losses: {event.defender_losses ?? 0}.</p>
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
  return <section aria-labelledby="history-title">
    <h2 id="history-title">Moves and battles</h2>
    {commentaryAccountId && (canGenerateCommentary || automatic) && <div>
      <label><input type="checkbox" checked={automatic} disabled={!automatic && !liveCommentaryAllowed}
        onChange={(event) => {
          if (event.currentTarget.checked) {
            live.contextChanged(gameId, commentaryAccountId, liveCommentaryAllowed);
            setAutomatic(live.enable(game.revision ?? 0));
          } else { live.disable(); setAutomatic(false); }
        }} /> AI commentary for new battles</label>
      <p>New committed exchanges are narrated automatically within the server's cost limits. Saved history is not generated again.
        Gameplay continues while narration is prepared. Turning it off cancels queued narration; a submitted request may finish.</p>
      {liveResults.get(0)?.error && <p role="status">{liveResults.get(0)?.error}</p>}
    </div>}
    {latest && <section aria-label="Latest submitted move">
      <h3>Latest move</h3>
      <ul>{latest.events.map((event, i) => <Event event={event} game={game} key={i} />)}</ul>
      {latest.npc_decision && <p>NPC explanation: {latest.npc_decision.explanation}</p>}
    </section>}
    {[...liveResults.values()].some((display) => display.entry && !events.some((entry) => entry.revision === display.entry!.revision)) && <section aria-label="Recent live battle exchanges">
      <h3>Recent live battle exchanges</h3>
      {[...liveResults.values()].filter((display) => display.entry && !events.some((entry) => entry.revision === display.entry!.revision))
        .map((display) => <div key={display.entry!.revision}>
          <h4>Move {display.entry!.revision}</h4>
          <ul>{display.entry!.events.map((event, i) => <Event event={event} game={game} key={i} />)}</ul>
          {display.entry!.npc_decision && <p>NPC explanation: {display.entry!.npc_decision.explanation}</p>}
          <BattleCommentaryPanel api={api} gameId={gameId} game={game} entry={display.entry!}
            canGenerate={canGenerateCommentary} automatic={display} permitted={() => permission.current()} />
        </div>)}
    </section>}
    <h3>Committed history</h3>
    {events.length === 0 && <p>No committed moves yet.</p>}
    <ol>{events.map((entry) => <li key={entry.revision}>
      <h4>Move {entry.revision}: {participantName(game, entry.actor.player_id)}</h4>
      <ul>{entry.events.map((event, i) => <Event event={event} game={game} key={i} />)}</ul>
      {entry.npc_decision && <p>NPC explanation: {entry.npc_decision.explanation}</p>}
      {entry.events.some((event) => event.type === 'dice_exchange') && <BattleCommentaryPanel
        key={`${gameId}:${entry.revision}:${entry.action_id}`}
        api={api} gameId={gameId} game={game} entry={entry} canGenerate={canGenerateCommentary}
        automatic={liveResults.get(entry.revision)} permitted={() => permission.current()} />}
    </li>)}</ol>
    {more && <button disabled={disabled} onClick={loadMore}>Load more history</button>}
  </section>;
}
