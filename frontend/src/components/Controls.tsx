import { useState } from 'react';
import type { ReactNode } from 'react';
import type { ActionCommand, PublicActionResult, PublicCountry, PublicGame } from '../api/index.ts';
import { activeParticipant, participantName, playable } from '../game/view.ts';
import { Button, NumericStepper, StatusIndicator } from '../ui/components.tsx';
import './controls.css';

type Action = ActionCommand['action'];
export interface ControlDraft {
  mode: 'attack' | 'transfer'; sourceId: string; targetId: string;
  transferSourceId: string; transferTargetId: string; amount: number;
  allocations: Readonly<Record<string, number>>;
}
export const emptyControlDraft = (): ControlDraft => ({ mode: 'attack', sourceId: '', targetId: '',
  transferSourceId: '', transferTargetId: '', amount: 1, allocations: {} });
interface HumanProps { game: PublicGame; disabled: boolean; act: (action: Action) => void;
  disabledReason?: string; latest?: PublicActionResult | null }

function CountrySummary({ country, label }: { country: PublicCountry; label: string }) {
  return <div className="geo-command__country"><span className="geo-label">{label}</span>
    <strong>{country.name}</strong><span>{country.soldiers} soldiers</span></div>;
}
function CommandHeader({ title, children }: { title: string; children?: ReactNode }) {
  return <header className="geo-command__header"><span className="geo-label">Your turn</span>
    <h2 id="moves-title">{title}</h2>{children}</header>;
}

export function HumanControls(props: HumanProps) {
  const [draft, onDraft] = useState(emptyControlDraft);
  return <HumanControlsView {...props} draft={draft} onDraft={onDraft} />;
}

/** Pure local-form presentation. Commands still go through the existing controller. */
export function HumanControlsView({ game, disabled, act, disabledReason, latest, draft, onDraft }: HumanProps & {
  draft: ControlDraft; onDraft: (draft: ControlDraft) => void;
}) {
  const actor = activeParticipant(game);
  if (!playable(game) || actor?.kind !== 'human' || !game.countries?.length) return <p>Current human-turn data is unavailable. Refresh the game before playing.</p>;
  const owned = game.countries.filter(c => c.owner_id === actor.id);
  const enemies = game.countries.filter(c => c.owner_id !== actor.id);
  const sources = owned.filter(c => c.soldiers > 1);
  const source = sources.find(c => c.id === draft.sourceId), target = enemies.find(c => c.id === draft.targetId);
  const update = (patch: Partial<ControlDraft>) => { if (!disabled) onDraft({ ...draft, ...patch }); };
  const submit = (action: Action) => { if (!disabled) act(action); };
  const reason = disabledReason ?? 'Wait for the current request or resolve the saved request above.';
  const recent = latest?.state.revision === game.revision ? latest?.events ?? [] : [];
  const conquest = recent.find(event => event.type === 'conquered');
  let content: ReactNode;

  if (game.phase === 'allocating') {
    const pool = game.pending_reinforcements;
    if (!Number.isSafeInteger(pool) || pool! <= 0 || game.round == null || game.round < 2 || !owned.length)
      return <section className="geo-command" aria-labelledby="moves-title"><CommandHeader title="Reinforcements unavailable" />
        <p>A valid round-two-or-later reinforcement budget is not available. Refresh before allocating.</p></section>;
    const amounts = owned.map(c => draft.allocations[c.id] ?? 0);
    const total = amounts.reduce((sum, amount) => sum + amount, 0);
    const valid = amounts.every(n => Number.isSafeInteger(n) && n >= 0 && n <= pool!) && total === pool;
    content = <><CommandHeader title="Place reinforcements"><p>Allocate {pool} reinforcements across the countries you hold.</p></CommandHeader>
      <p className="geo-command__budget" data-valid={valid}>{pool! - total} remaining · {total} of {pool} assigned</p>
      <form onSubmit={event => { event.preventDefault(); if (valid) submit({ type: 'allocate',
        allocations: owned.map((c, i) => ({ country_id: c.id, amount: amounts[i] })).filter(a => a.amount > 0) }); }}>
        <fieldset disabled={disabled}><legend>Reinforcement recipients</legend>
          {owned.map(c => <NumericStepper key={c.id} label={`${c.name} reinforcements`} min={0} max={pool!}
            value={Number.isSafeInteger(draft.allocations[c.id]) && draft.allocations[c.id]! >= 0 && draft.allocations[c.id]! <= pool! ? draft.allocations[c.id]! : 0}
            disabled={disabled} onChange={amount => update({ allocations: { ...draft.allocations, [c.id]: amount } })} />)}
        </fieldset>
        <Button type="submit" disabled={disabled || !valid} disabledReason={disabled ? reason : 'Allocate the full reinforcement budget before submitting.'}>Allocate reinforcements</Button>
      </form><p className="geo-help">The server supplies this pool. Reinforcements begin in round 2.</p></>;
  } else if (game.phase === 'attacking') {
    const attacker = owned.find(c => c.id === game.battle?.source_id), defender = enemies.find(c => c.id === game.battle?.target_id);
    const battleValid = !!attacker && !!defender && attacker.soldiers > 1 && defender.soldiers > 0;
    content = <><CommandHeader title="Attack in progress"><p>The countries stay locked for this attack.</p></CommandHeader>
      {attacker && defender ? <div className="geo-command__comparison" data-ready="true"><CountrySummary country={attacker} label="FROM" /><span className="geo-command__direction" aria-label="Attacking">↓</span><CountrySummary country={defender} label="TARGET" /></div>
        : <p>The current battle pair is unavailable. Refresh before continuing.</p>}
      {battleValid && <p>Next exchange: {Math.min(attacker!.soldiers - 1, defender!.soldiers)} dice each side. One soldier stays behind; tied pairs lose nothing.</p>}
      <h3 className="geo-heading-md">Keep attacking?</h3>
      <div className="geo-command__actions"><Button disabled={disabled || !battleValid} disabledReason={disabled ? reason : 'A valid active battle is required.'}
        onClick={() => { if (battleValid) submit({ type: 'roll' }); }}>Roll battle dice</Button>
        <Button variant="secondary" disabled={disabled || !battleValid} disabledReason={disabled ? reason : 'A valid active battle is required.'}
          onClick={() => { if (battleValid) submit({ type: 'stop_attack' }); }}>Stop attack and end turn</Button></div>
      <p className="geo-help">Transfers are unavailable during an attack. Committed dice, losses and narration remain in Moves and battles.</p></>;
  } else if (game.phase === 'deciding' || game.phase === 'post_attack') {
    const post = game.phase === 'post_attack';
    const transferSource = sources.find(c => c.id === draft.transferSourceId);
    const transferTarget = owned.find(c => c.id === draft.transferTargetId && c.id !== transferSource?.id);
    const transferValid = !!transferSource && !!transferTarget && Number.isSafeInteger(draft.amount)
      && draft.amount >= 1 && draft.amount <= transferSource.soldiers - 1;
    const attackValid = !!source && !!target;
    const attackReason = !sources.length ? 'An owned country needs at least two soldiers to attack.'
      : !enemies.length ? 'No rival target is available.' : !source ? 'Choose an attacking country.' : 'Choose a rival target.';
    content = <><CommandHeader title={post ? conquest ? 'Country conquered' : 'After the attack' : draft.mode === 'transfer' ? 'Transfer soldiers' : 'Plan your move'}>
      <p>{post ? 'You may transfer soldiers, then end your turn. A new attack starts on your next turn.' : 'One attack per turn, with as many dice exchanges as the battle permits. You may also transfer soldiers or skip.'}</p></CommandHeader>
      {conquest && <p>{game.countries.find(c => c.id === conquest.target_id)?.name ?? conquest.target_id} was conquered.
        {conquest.amount != null && ` Conquest reward: ${conquest.amount} soldiers added.`} This automatic reward is separate from any optional transfer.</p>}
      {draft.mode === 'transfer' ? <>
        <form onSubmit={event => { event.preventDefault(); if (transferValid) submit({ type: 'transfer', source_id: transferSource!.id,
          target_id: transferTarget!.id, amount: draft.amount }); }}>
          <fieldset disabled={disabled || owned.length < 2}><legend>Transfer between your countries</legend>
            <label>Transfer from <select required value={draft.transferSourceId} onChange={event => {
              const next = sources.find(c => c.id === event.target.value);
              update({ transferSourceId: event.target.value, transferTargetId: draft.transferTargetId === event.target.value ? '' : draft.transferTargetId,
                amount: Math.max(1, Math.min(draft.amount, next ? next.soldiers - 1 : 1)) });
            }}><option value="">Choose a source</option>{sources.map(c => <option value={c.id} key={c.id}>{c.name} ({c.soldiers} soldiers)</option>)}</select></label>
            <label>Transfer to <select required value={draft.transferTargetId} onChange={event => update({ transferTargetId: event.target.value })}>
              <option value="">Choose a destination</option>{owned.filter(c => c.id !== draft.transferSourceId).map(c => <option value={c.id} key={c.id}>{c.name} ({c.soldiers} soldiers)</option>)}</select></label>
            {transferSource && <NumericStepper label="Soldiers to transfer" min={1} max={transferSource.soldiers - 1}
              value={Math.max(1, Math.min(Number.isSafeInteger(draft.amount) ? draft.amount : 1, transferSource.soldiers - 1))}
              disabled={disabled} onChange={amount => update({ amount })} />}
          </fieldset>
          <p>Leave at least one soldier in the source country.</p>
          <Button type="submit" disabled={disabled || !transferValid} disabledReason={disabled ? reason : 'Choose two different owned countries and a valid positive amount.'}>Transfer soldiers</Button>
        </form>
        <Button variant="quiet" disabled={disabled} onClick={() => update({ mode: 'attack' })}>{post ? 'Back to end turn' : 'Back to attack'}</Button>
      </> : <>
        {!post && <form onSubmit={event => { event.preventDefault(); if (attackValid) submit({ type: 'start_attack', source_id: source!.id, target_id: target!.id }); }}>
          <fieldset disabled={disabled || !sources.length || !enemies.length}><legend>Start one attack</legend>
            <label>Attack from <select name="source" required value={draft.sourceId} onChange={event => update({ sourceId: event.target.value })}>
              <option value="">Choose an attacking country</option>{sources.map(c => <option key={c.id} value={c.id} aria-label={`${c.name}, ${c.soldiers} soldiers`}>{c.name}</option>)}</select></label>
            <label>Attack target <select name="target" required value={draft.targetId} onChange={event => update({ targetId: event.target.value })}>
              <option value="">Choose a rival target</option>{enemies.map(c => <option key={c.id} value={c.id} aria-label={`${c.name}, ${c.soldiers} soldiers`}>{c.name}</option>)}</select></label>
          </fieldset>
          {(source || target) && <div key={`${source?.id ?? ''}:${target?.id ?? ''}`} className="geo-command__comparison" data-ready={!!source && !!target}>
            {source && <CountrySummary country={source} label="FROM" />}{source && target && <span className="geo-command__direction" aria-label="Attacking">↓</span>}{target && <CountrySummary country={target} label="TARGET" />}</div>}
          <p className="geo-help">Any rival country can be attacked, regardless of distance. Selecting countries submits nothing.</p>
          <Button type="submit" className={attackValid ? 'geo-command__ready' : ''} disabled={disabled || !attackValid} disabledReason={disabled ? reason : attackReason}>Start attack</Button>
        </form>}
        <div className="geo-command__actions"><Button variant="secondary" disabled={disabled || owned.length < 2 || !sources.length}
          disabledReason={disabled ? reason : owned.length < 2 ? 'Hold at least two countries to transfer between them.' : 'An owned source needs at least two soldiers so one can stay behind.'} onClick={() => update({ mode: 'transfer' })}>Transfer soldiers</Button></div>
      </>}
      <div className="geo-command__footer">{post ? <Button variant={draft.mode === 'transfer' ? 'quiet' : 'primary'} disabled={disabled} disabledReason={reason}
        onClick={() => submit({ type: 'end_turn' })}>End turn</Button>
        : <Button variant="quiet" disabled={disabled} disabledReason={reason} onClick={() => submit({ type: 'skip' })}>Skip turn</Button>}</div>
    </>;
  } else content = <p>This turn phase is unavailable. Refresh before choosing a move.</p>;
  return <section className="geo-command" aria-labelledby="moves-title">{content}</section>;
}

export interface GameplayControlsProps {
  game: PublicGame; owner: boolean; disabled: boolean; fastForward: boolean;
  act: (action: Action) => void; step: () => void; fast: () => void; pause: () => void;
  busy?: boolean; pending?: boolean; disabledReason?: string; latest?: PublicActionResult | null; npcLimitReached?: boolean;
}
export function GameplayControls({ game, owner, disabled, fastForward, act, step, fast, pause,
  busy = false, pending = false, disabledReason, latest, npcLimitReached = false }: GameplayControlsProps) {
  const active = activeParticipant(game);
  if (!owner) return <section className="geo-command"><h2>Watching this game</h2>
    <p>Spectator view. Only this game's logged-in owner can play.</p><p>Follow the board, NPC explanations and saved commentary in the Chronicle.</p></section>;
  if (game.status === 'completed') return <section className="geo-command"><h2>Game complete</h2><p>This game is complete.</p>
    {game.winner && <p>Winner: {participantName(game, game.winner)}</p>}</section>;
  const complete = game.countries?.length === 10 && game.players?.length === 10 && game.turn_order?.length === 10
    && new Set(game.countries.map(c => c.id)).size === 10 && new Set(game.players.map(p => p.id)).size === 10
    && new Set(game.turn_order).size === 10 && game.turn_order.every(id => game.players!.some(p => p.id === id))
    && game.countries.every(c => Number.isSafeInteger(c.soldiers) && c.soldiers >= 1 && game.players!.some(p => p.id === c.owner_id));
  if (!playable(game) || !active || !complete || !game.countries?.some(c => c.owner_id === active.id))
    return <section className="geo-command"><h2>Read-only record</h2><p>This historical game is available for viewing only.</p>
      <p>Complete current-turn data is required before playing.</p></section>;
  const locked = disabled || pending || busy;
  const reason = pending ? 'Resolve the saved request above before starting another move.' : disabledReason ?? 'Wait until the current operation finishes.';
  const human = game.players?.find(p => p.kind === 'human');
  const eliminated = human && !game.countries!.some(c => c.owner_id === human.id);
  return <div className="geo-command-context">
    {pending && <p className="geo-command__recovery" role="status">{fastForward
      ? 'Confirming the submitted NPC move before continuing. Pause remains available.'
      : 'A submitted request remains saved. New moves are locked. Use the recovery controls above; do not submit a replacement move.'}</p>}
    {busy && <p role="status">An action is in progress. Keep this page open while its outcome is confirmed.</p>}
    {eliminated && <p>The human participant has been eliminated. The game is still active; you may continue the remaining NPC turns.</p>}
    {active.kind === 'human' ? <HumanControls game={game} disabled={locked} disabledReason={reason} latest={latest} act={act} />
      : <section className="geo-command geo-playback" aria-labelledby="npc-title"><header className="geo-command__header"><span className="geo-label">While rivals play</span>
        <h2 id="npc-title">{participantName(game, active.id)}</h2></header>
        <div className="geo-playback__state" role="status"><StatusIndicator>{pending && !busy ? 'Awaiting confirmation' : busy ? 'Advancing an NPC action' : fastForward ? 'Fast-forward is on' : 'Awaiting an NPC action · fast-forward is off'}</StatusIndicator>
          <p>{pending ? 'The submitted action must settle before another can begin.' : `Current phase: ${game.phase?.replaceAll('_', ' ') ?? 'not recorded'}.`}</p></div>
        <div className="geo-command__actions"><Button variant={fastForward ? 'secondary' : 'primary'} disabled={locked || fastForward || npcLimitReached} disabledReason={npcLimitReached ? 'The configured NPC limit is reached.' : reason}
          onClick={() => { if (!locked && !fastForward && !npcLimitReached) step(); }}>Advance one NPC action</Button>
          <Button variant="secondary" disabled={locked || fastForward || npcLimitReached} disabledReason={npcLimitReached ? 'The configured NPC limit is reached.' : reason}
            onClick={() => { if (!locked && !fastForward && !npcLimitReached) fast(); }}>Fast-forward NPCs</Button>
          {fastForward && <Button variant="primary" onClick={pause}>Pause NPC fast-forward</Button>}</div>
        {npcLimitReached && <p>The configured NPC limit is reached. Playback cannot start; saved outcomes can still be checked.</p>}
        <p>NPC actions and explanations remain visible. Fast-forward pauses at the human turn or game completion.</p>
        <p className="geo-help">Pause prevents another action from starting; an already submitted action may still finish.</p>
        <a href="#history-title">Follow committed moves in the Chronicle</a>
      </section>}
  </div>;
}
