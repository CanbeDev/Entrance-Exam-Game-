import type { PublicCommittedAction, PublicGame, PublicGameEvent } from '../api/index.ts';
export const validDie = (value: unknown): value is number => Number.isInteger(value) && Number(value) >= 1 && Number(value) <= 6;
const count = (value: unknown): number | null => Number.isSafeInteger(value) && Number(value) >= 0 ? Number(value) : null;
export const exchangeIdentity = (gameId: string, entry: PublicCommittedAction, index: number): string => JSON.stringify([gameId, entry.revision, entry.action_id, index]);
export const newlyObservedExchange = (revision: number, current: number | null | undefined, previous: number | null | undefined): boolean =>
  current != null && (revision === current || previous != null && revision > previous && revision <= current);
export function dicePairs(event: PublicGameEvent) {
  const a = event.attacker_dice ?? [], d = event.defender_dice ?? [];
  return Array.from({ length: Math.max(a.length, d.length) }, (_, index) => {
    const attacker = validDie(a[index]) ? a[index]! : null, defender = validDie(d[index]) ? d[index]! : null;
    return { index, attacker, defender, result: attacker === null || defender === null ? 'Result not recorded'
      : attacker === defender ? 'Tie — no loss' : attacker > defender ? 'Defender loses 1' : 'Attacker loses 1' };
  });
}
export interface BattleCounts { attackerBefore: number | null; attackerAfter: number | null; defenderBefore: number | null; defenderAfter: number | null; defenderCurrent: number | null }
export function exchangeCounts(entry: Pick<PublicCommittedAction, 'revision' | 'events'>, event: PublicGameEvent, game: PublicGame, previous?: PublicGame | null): BattleCounts {
  const single = entry.events.filter(e => e.type === 'dice_exchange').length === 1;
  const clean = single && !entry.events.some(e => e.type === 'allocated' || e.type === 'transferred');
  const prior = clean && previous?.revision === entry.revision - 1 ? previous : null;
  const current = clean && game.revision === entry.revision ? game : null;
  const country = (g: PublicGame | null, id: string | null | undefined) => g?.countries?.find(c => c.id === id);
  const conquered = clean && entry.events.some(e => e.type === 'conquered' && e.target_id === event.target_id);
  const aLoss = count(event.attacker_losses), dLoss = count(event.defender_losses);
  let attackerBefore = count(country(prior, event.source_id)?.soldiers), attackerAfter = count(country(current, event.source_id)?.soldiers);
  let defenderBefore = count(country(prior, event.target_id)?.soldiers), defenderAfter = conquered ? 0 : count(country(current, event.target_id)?.soldiers);
  const add = (a: number | null, b: number | null) => a !== null && b !== null ? count(a + b) : null;
  const subtract = (a: number | null, b: number | null) => a !== null && b !== null ? count(a - b) : null;
  attackerBefore ??= add(attackerAfter, aLoss); attackerAfter ??= subtract(attackerBefore, aLoss);
  defenderBefore ??= add(defenderAfter, dLoss); defenderAfter ??= subtract(defenderBefore, dLoss);
  return { attackerBefore, attackerAfter, defenderBefore, defenderAfter,
    defenderCurrent: conquered ? count(country(current, event.target_id)?.soldiers) : null };
}
export function mergeCounts(old: BattleCounts | undefined, next: BattleCounts): BattleCounts {
  return Object.fromEntries(Object.entries(next).map(([key, value]) => [key, old?.[key as keyof BattleCounts] ?? value])) as unknown as BattleCounts;
}
/** Per-History display ledger. It never allocates action IDs or sends a request. */
export function createExchangeLedger(initialRevision: number | null | undefined) {
  const seen = new Set<string>();
  return { counts: new Map<string, BattleCounts>(), claim(id: string, revision: number, motionAllowed: boolean) {
    if (seen.has(id)) return false;
    seen.add(id);
    return motionAllowed && initialRevision != null && revision > initialRevision;
  } };
}
