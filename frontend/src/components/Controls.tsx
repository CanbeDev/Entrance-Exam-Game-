import { useState } from 'react';
import type { SubmitEvent } from 'react';
import type { ActionCommand, PublicCountry, PublicGame } from '../api/index.ts';
import { activeParticipant, playable } from '../game/view.ts';

export function HumanControls({ game, disabled, act }: {
  game: PublicGame; disabled: boolean; act: (action: ActionCommand['action']) => void;
}) {
  const actor = activeParticipant(game);
  const owned = game.countries?.filter((country) => country.owner_id === actor?.id) ?? [];
  const enemies = game.countries?.filter((country) => country.owner_id !== actor?.id) ?? [];
  const sources = owned.filter((country) => country.soldiers > 1);
  const [allocationError, setAllocationError] = useState('');
  function attack(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    act({ type: 'start_attack', source_id: String(data.get('source')), target_id: String(data.get('target')) });
  }
  function allocate(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const allocations = owned.map((country) => ({ country_id: country.id, amount: Number(data.get(country.id)) }))
      .filter((entry) => entry.amount > 0);
    if (allocations.reduce((sum, entry) => sum + entry.amount, 0) !== game.pending_reinforcements) {
      setAllocationError('Allocate the full reinforcement budget before submitting.');
      return;
    }
    setAllocationError('');
    act({ type: 'allocate', allocations });
  }
  return <section aria-labelledby="moves-title">
    <h2 id="moves-title">Your turn</h2>
    {game.phase === 'allocating' && <form onSubmit={allocate}><fieldset disabled={disabled}>
      <legend>Allocate {game.pending_reinforcements} reinforcements</legend>
      {owned.map((country) => <label key={country.id}>{country.name} reinforcements
        <input name={country.id} type="number" min={0} max={game.pending_reinforcements ?? 0} step={1} required defaultValue={0} />
      </label>)}
      {allocationError && <p role="alert">{allocationError}</p>}
      <button type="submit">Allocate reinforcements</button>
    </fieldset></form>}
    {game.phase === 'deciding' && <>
      <form onSubmit={attack}><fieldset disabled={disabled || sources.length === 0 || enemies.length === 0}>
        <legend>Start one attack</legend>
        <label>Attack from <select name="source" required defaultValue={sources[0]?.id ?? ''}>
          {sources.map((country) => <option key={country.id} value={country.id}>{country.name} ({country.soldiers} soldiers)</option>)}
        </select></label>
        <label>Attack target <select name="target" required defaultValue={enemies[0]?.id ?? ''}>
          {enemies.map((country) => <option key={country.id} value={country.id}>{country.name} ({country.soldiers} soldiers)</option>)}
        </select></label>
        <button type="submit">Start attack</button>
      </fieldset></form>
      <button disabled={disabled} onClick={() => act({ type: 'skip' })}>Skip turn</button>
    </>}
    {game.phase === 'attacking' && <fieldset disabled={disabled}>
      <legend>Continue or stop the current battle</legend>
      <button onClick={() => act({ type: 'roll' })}>Roll battle dice</button>
      <button onClick={() => act({ type: 'stop_attack' })}>Stop attack and end turn</button>
    </fieldset>}
    {(game.phase === 'deciding' || game.phase === 'post_attack') && <TransferForm owned={owned} disabled={disabled} act={act} />}
    {game.phase === 'post_attack' && <button disabled={disabled} onClick={() => act({ type: 'end_turn' })}>End turn</button>}
  </section>;
}

function TransferForm({ owned, disabled, act }: {
  owned: readonly PublicCountry[]; disabled: boolean; act: (action: ActionCommand['action']) => void;
}) {
  const sources = owned.filter((country) => country.soldiers > 1);
  const [sourceId, setSourceId] = useState(sources[0]?.id ?? '');
  const source = sources.find((country) => country.id === sourceId);
  const targets = owned.filter((country) => country.id !== sourceId);
  function transfer(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    act({ type: 'transfer', source_id: sourceId, target_id: String(data.get('transfer_target')), amount: Number(data.get('amount')) });
  }
  return <form onSubmit={transfer}><fieldset disabled={disabled || owned.length < 2 || !source || targets.length === 0}>
    <legend>Transfer between your countries</legend>
    <label>Transfer from <select value={sourceId} onChange={(event) => setSourceId(event.target.value)} required>
      {sources.map((country) => <option key={country.id} value={country.id}>{country.name}</option>)}
    </select></label>
    <label>Transfer to <select name="transfer_target" key={sourceId} defaultValue={targets[0]?.id ?? ''} required>
      {targets.map((country) => <option key={country.id} value={country.id}>{country.name}</option>)}
    </select></label>
    <label>Soldiers to transfer <input name="amount" type="number" min={1} max={source ? source.soldiers - 1 : 1} step={1} required defaultValue={1} /></label>
    <p>Leave at least one soldier in the source country.</p>
    <button type="submit">Transfer soldiers</button>
  </fieldset></form>;
}

export function GameplayControls({ game, owner, disabled, fastForward, act, step, fast, pause }: {
  game: PublicGame; owner: boolean; disabled: boolean; fastForward: boolean;
  act: (action: ActionCommand['action']) => void; step: () => void; fast: () => void; pause: () => void;
}) {
  if (!owner) return <p>Spectator view. Only this game's logged-in owner can play.</p>;
  if (game.status === 'completed') return <p>This game is complete.</p>;
  if (!playable(game)) return <p>This historical game is available for viewing only.</p>;
  if (activeParticipant(game)?.kind === 'human') return <HumanControls game={game} disabled={disabled} act={act} />;
  return <section aria-labelledby="npc-title"><h2 id="npc-title">NPC turn</h2>
    <button disabled={disabled || fastForward} onClick={step}>Advance one NPC action</button>
    <button disabled={disabled || fastForward} onClick={fast}>Fast-forward NPCs</button>
    {fastForward && <button onClick={pause}>Pause NPC fast-forward</button>}
    <p>NPC actions and explanations remain visible. Fast-forward pauses at the human turn or game completion.</p>
  </section>;
}
