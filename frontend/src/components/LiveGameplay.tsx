import type { PublicActionResult, PublicCommittedAction, PublicGame } from '../api/index.ts';
import { ActiveBattle, BattleExchangeView } from './BattleExchange.tsx';
import { exchangeCounts } from './battle-view.ts';
import { actionSummary, committedDisplays } from './gameplay-view.ts';
import { participantCountryName } from './refresh-view.ts';
import { receiptRound } from './chronicle-view.ts';

export function SavedNpcDecision({ game, latest, committed }: {
  game: PublicGame; latest?: PublicActionResult | null; committed: readonly PublicCommittedAction[];
}) {
  const npc = committedDisplays(game, latest, committed).npc;
  return npc?.decision ? <aside className="geo-live__perspective" aria-label="Latest saved commander decision">
    <p className="geo-label">Commander’s decision · Move {npc.revision}</p>
    <h3>{participantCountryName(game, npc.actorId)}’s Strategy</h3>
    <ul>{npc.events.map((event, index) => <li key={index}>{actionSummary(game, event)}</li>)}</ul>
    <p className="geo-saved-justification">{npc.decision.explanation}</p>
  </aside> : null;
}

/** Read-only snapshot view. No effect, ledger, audio, commentary consumer or API. */
export function LiveGameplay({ game, latest, committed, pending }: {
  game: PublicGame; latest?: PublicActionResult | null; committed: readonly PublicCommittedAction[]; pending?: boolean;
}) {
  const display = committedDisplays(game, latest, committed), record = display.latest;
  const exchange = display.exchange;
  return <section className="geo-live" id="live-action" tabIndex={-1} aria-label="Live gameplay and saved decisions">
    <ActiveBattle game={game} pending={pending} />
    {record && <div className="geo-live__committed" data-confirmed-revision={record.revision}>
      <p className="geo-label">Latest confirmed action · {receiptRound(record) != null ? `Round ${receiptRound(record)} · ` : ''}Move {record.revision}</p>
      {pending && <p className="geo-help">Previous confirmed result. The outstanding action is not confirmed.</p>}
      <ul className="geo-live__summary">{record.events.filter(event => event.type !== 'dice_exchange').map((event, index) =>
        <li key={index}>{actionSummary(game, event)}</li>)}</ul>
    </div>}
    {exchange && <div className="geo-live__committed">
      {exchange !== record && <p className="geo-help">Most recent saved exchange · Move {exchange.revision}. Current turn and soldier totals are shown separately.</p>}
      {exchange.events.map((event, index) => event.type === 'dice_exchange'
        ? <div className="geo-live__exchange" key={index}><p className="geo-label">Latest confirmed exchange</p>
          <BattleExchangeView game={game} entry={exchange} index={index} counts={exchangeCounts(exchange, event, game)}
            rolling={false} skip={() => {}} settled={() => {}} /></div> : null)}
    </div>}
    {!record && game.phase !== 'attacking' && <p className="geo-help">Confirmed moves will appear here as they are received.</p>}
    {record && <nav aria-label="Confirmed action navigation"><a href="#game-actions">Back to actions</a><a href="#history-title">Complete records and Battle Commentary in the Chronicle</a></nav>}
  </section>;
}
