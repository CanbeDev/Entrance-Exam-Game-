import type { PublicGame } from '../api/index.ts';
import { activeParticipant, participantName } from '../game/view.ts';

export function GameBoard({ game }: { game: PublicGame }) {
  const active = activeParticipant(game);
  return <section aria-labelledby="board-title">
    <h2 id="board-title">{game.game_name}</h2>
    <dl>
      <dt>Status</dt><dd>{game.status ?? 'waiting'}</dd>
      <dt>Round</dt><dd>{game.round ?? '—'}</dd>
      <dt>Current turn</dt><dd>{active ? participantName(game, active.id) : '—'}</dd>
      <dt>Turn phase</dt><dd>{game.phase?.replace('_', ' ') ?? 'Historical game'}</dd>
      <dt>Revision</dt><dd>{game.revision ?? '—'}</dd>
      {game.winner && <><dt>Winner</dt><dd>{participantName(game, game.winner)}</dd></>}
    </dl>
    <table>
      <caption>Countries and soldiers</caption>
      <thead><tr><th scope="col">Country</th><th scope="col">Controlled by</th><th scope="col">Soldiers</th></tr></thead>
      <tbody>{game.countries?.map((country) => <tr key={country.id}>
        <th scope="row">{country.name}</th><td>{participantName(game, country.owner_id)}</td><td>{country.soldiers}</td>
      </tr>)}</tbody>
    </table>
    {game.battle && <p>Battle in progress: {game.countries?.find((c) => c.id === game.battle!.source_id)?.name ?? game.battle.source_id}
      {' → '}{game.countries?.find((c) => c.id === game.battle!.target_id)?.name ?? game.battle.target_id}</p>}
    {game.players?.filter((p) => p.kind === 'human').some((p) => !game.countries?.some((c) => c.owner_id === p.id))
      && <p>The human participant has been eliminated. The remaining NPCs can finish the match.</p>}
  </section>;
}
