import type { PublicActionResult, PublicCommittedAction, PublicGame, PublicGameEvent } from '../api/index.ts';
import { participantName } from '../game/view.ts';

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
export function History({ game, events, latest, more, disabled, loadMore }: {
  game: PublicGame; events: readonly PublicCommittedAction[]; latest: PublicActionResult | null;
  more: boolean; disabled: boolean; loadMore: () => void;
}) {
  return <section aria-labelledby="history-title">
    <h2 id="history-title">Moves and battles</h2>
    {latest && <section aria-label="Latest submitted move">
      <h3>Latest move</h3>
      <ul>{latest.events.map((event, i) => <Event event={event} game={game} key={i} />)}</ul>
      {latest.npc_decision && <p>NPC explanation: {latest.npc_decision.explanation}</p>}
    </section>}
    <h3>Committed history</h3>
    {events.length === 0 && <p>No committed moves yet.</p>}
    <ol>{events.map((entry) => <li key={entry.revision}>
      <h4>Move {entry.revision}: {participantName(game, entry.actor.player_id)}</h4>
      <ul>{entry.events.map((event, i) => <Event event={event} game={game} key={i} />)}</ul>
      {entry.npc_decision && <p>NPC explanation: {entry.npc_decision.explanation}</p>}
    </li>)}</ol>
    {more && <button disabled={disabled} onClick={loadMore}>Load more history</button>}
  </section>;
}
