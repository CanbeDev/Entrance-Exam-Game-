import { useEffect, useState } from 'react';
import type { PublicCommittedAction, PublicGame } from '../api/index.ts';
import { activeParticipant } from '../game/view.ts';
import { createExchangeLedger, dicePairs, exchangeCounts, exchangeIdentity, mergeCounts, newlyObservedExchange, validDie } from './battle-view.ts';
import type { BattleCounts } from './battle-view.ts';
import './battle.css';
import { pageSound } from '../sound/SoundSettings.tsx';
const number = (value: number) => value.toLocaleString('en-US');
const pips: Readonly<Record<number, readonly number[]>> = { 1:[4],2:[0,8],3:[0,4,8],4:[0,2,6,8],5:[0,2,4,6,8],6:[0,2,3,5,6,8] };
export function Die({ value, side }: { value: number | null; side: 'Attacker' | 'Defender' }) {
  return <span className={`geo-die geo-die--${side.toLowerCase()}`} role="img" aria-label={validDie(value) ? `${side} rolled ${value}` : `${side} die not recorded`} data-value={value ?? 'unknown'}>
    <span className="geo-die__pips" aria-hidden="true">{validDie(value) ? Array.from({length:9},(_,i)=><i key={i} data-pip={pips[value]!.includes(i)} />) : '?'}</span>
    <span className="geo-die__rolling" aria-hidden="true">···</span>
  </span>;
}
function Side({ name, side, before, after, loss, current, reward }: { name: string; side: 'Attacker' | 'Defender'; before: number | null; after: number | null; loss?: number; current?: number | null; reward?: number | null }) {
  return <aside className={`geo-battle__side geo-battle__side--${side.toLowerCase()}`}><span className="geo-label">{side === 'Attacker' ? 'Attacking forces' : 'Defending forces'}</span><h4>{name}</h4>
    {after !== null ? <><strong className="geo-battle__soldiers">{number(after)}</strong><p>soldiers after this exchange</p></> : <p>Soldier count not recorded for this exchange.</p>}
    {loss != null && <p className="geo-battle__loss">{number(loss)} {loss === 1 ? 'soldier' : 'soldiers'} lost</p>}
    {before !== null && <details className="geo-battle__before"><summary>Before exchange</summary><p>{number(before)} soldiers</p></details>}
    {reward != null && <p>Conquest reward: {number(reward)} soldiers added separately.</p>}
    {current != null && <p>After conquest reward: {number(current)} soldiers stationed here.</p>}
  </aside>;
}
export function BattleExchangeView({ game, entry, index, counts, rolling, skip, settled }: {
  game: PublicGame; entry: Pick<PublicCommittedAction, 'revision' | 'events'>; index: number; counts: BattleCounts; rolling: boolean; skip: () => void; settled: () => void;
}) {
  const event = entry.events[index]!;
  const pairs = dicePairs(event);
  const complete = pairs.length > 0 && pairs.every(p => p.attacker !== null && p.defender !== null);
  const ties = complete ? pairs.filter(p => p.attacker === p.defender).length : null;
  const country = (id: string | null | undefined) => game.countries?.find(c => c.id === id)?.name ?? id ?? 'Country not recorded';
  const conquest = entry.events.find(e => e.type === 'conquered' && e.target_id === event.target_id);
  return <section className="geo-battle" aria-label={`Committed dice exchange, move ${entry.revision}`}>
    <header className="geo-battle__heading"><h4>{country(event.source_id)} → {country(event.target_id)}</h4>
      <p>Confirmed exchange · Move {entry.revision}</p></header>
    <div className="geo-battle__summary" role="status"><span>Attacker losses: {event.attacker_losses ?? 'not recorded'}.</span>{' '}
      <span>Defender losses: {event.defender_losses ?? 'not recorded'}.</span>{' '}
      <span>{ties === null ? 'Ties not fully recorded.' : `${ties} ${ties === 1 ? 'tie' : 'ties'} — no loss.`}</span></div>
    <div className="geo-battle__layout"><Side name={country(event.source_id)} side="Attacker" before={counts.attackerBefore} after={counts.attackerAfter} loss={event.attacker_losses} />
      <Side name={country(event.target_id)} side="Defender" before={counts.defenderBefore} after={counts.defenderAfter} loss={event.defender_losses} current={counts.defenderCurrent} reward={conquest?.amount} />
      <div className="geo-battle__centre"><h4>Recorded dice · Move {entry.revision}</h4><p>{complete ? `${pairs.length} dice each side, paired in saved order.` : 'Some dice data is not recorded.'}</p>
        {rolling && <button type="button" onClick={skip}>Skip dice animation</button>}
        <div className="geo-battle__scroll" role="region" aria-label={`Dice pairs for move ${entry.revision}`} tabIndex={0}>
          <ol className="geo-battle__pairs" data-rolling={rolling} onAnimationEnd={e => { if (e.animationName === 'geo-die-roll') settled(); }}>
            {pairs.map(pair => <li key={pair.index} data-pair={pair.index + 1} data-outcome={pair.attacker === null || pair.defender === null ? 'unknown' : pair.attacker === pair.defender ? 'tie' : pair.attacker > pair.defender ? 'defender-loss' : 'attacker-loss'}><span className="geo-battle__pair-label">Pair {pair.index + 1}</span>
              <div className="geo-battle__dice"><Die value={pair.attacker} side="Attacker" /><span aria-hidden="true">vs</span><Die value={pair.defender} side="Defender" /></div>
              <span className="geo-battle__pair-result">{pair.result}</span></li>)}
          </ol>
        </div>
        {!pairs.length && <p>Dice values are unavailable for this exchange.</p>}
        <details><summary>Saved dice values</summary><p>Attacker dice: {event.attacker_dice?.join(', ') || 'not recorded'}. Defender dice: {event.defender_dice?.join(', ') || 'not recorded'}.</p></details>
      </div>
    </div>
  </section>;
}
export function BattleExchange({ game, entry, index, gameId, ledger, previous }: { game: PublicGame; entry: PublicCommittedAction; index: number; gameId: string;
  ledger: ReturnType<typeof createExchangeLedger>; previous?: PublicGame | null;
}) {
  const identity = exchangeIdentity(gameId, entry, index), event = entry.events[index]!;
  const counts = mergeCounts(ledger.counts.get(identity), exchangeCounts(entry, event, game, previous));
  const [rolling, setRolling] = useState(false);
  useEffect(() => { ledger.counts.set(identity, counts); }, [ledger, identity, counts.attackerBefore, counts.attackerAfter, counts.defenderBefore, counts.defenderAfter, counts.defenderCurrent]);
  useEffect(() => {
    const preference = typeof window.matchMedia === 'function' ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
    const hasDice = dicePairs(event).some(p => p.attacker !== null || p.defender !== null);
    setRolling(ledger.claim(identity, entry.revision, hasDice && newlyObservedExchange(entry.revision, game.revision, previous?.revision) && !preference?.matches));
    const change = () => { if (preference?.matches) setRolling(false); };
    preference?.addEventListener('change', change);
    return () => preference?.removeEventListener('change', change);
  }, [identity, ledger, entry.revision]);
  return <BattleExchangeView game={game} entry={entry} index={index} counts={counts} rolling={rolling}
    skip={() => { setRolling(false); pageSound.finishDice(`${gameId}:${entry.revision}:${entry.action_id}`); }} settled={() => setRolling(false)} />;
}
export function ActiveBattle({ game, pending = false }: { game: PublicGame; pending?: boolean }) {
  if (game.status !== 'active' || game.phase !== 'attacking' || !game.battle) return null;
  const a = game.countries?.find(c => c.id === game.battle!.source_id), d = game.countries?.find(c => c.id === game.battle!.target_id);
  return <section className="geo-battle geo-battle--active" aria-label="Current battle"><span className="geo-label">Battle underway</span><h3>{a?.name ?? game.battle.source_id} → {d?.name ?? game.battle.target_id}</h3>
    <p>{activeParticipant(game)?.kind === 'npc' ? 'Rival attack underway.' : 'Attack underway.'} {pending ? 'A battle action is awaiting confirmation. No new dice result is shown until it is committed.' : 'Use the existing battle actions to roll or stop.'}</p>
    <p>{a ? `${a.name}: ${number(a.soldiers)} soldiers. ` : ''}{d ? `${d.name}: ${number(d.soldiers)} soldiers.` : ''}</p>
    <a href="#history-title">View committed dice and commentary</a>
  </section>;
}
