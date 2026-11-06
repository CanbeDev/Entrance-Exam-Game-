import type { PublicCommittedAction } from '../api/index.ts';

export const CHRONICLE_PAGE_SIZE = 20;
/** Server receipts win over a matching independently observed live receipt. */
export function chronicleEntries(events: readonly PublicCommittedAction[], live: readonly PublicCommittedAction[]) {
  const byRevision = new Map<number, PublicCommittedAction>();
  for (const entry of [...live, ...events]) byRevision.set(entry.revision, entry);
  return [...byRevision.values()].sort((a, b) => b.revision - a.revision);
}
export function chronicleWindow(entries: readonly PublicCommittedAction[], page: number) {
  const last = Math.max(0, Math.ceil(entries.length / CHRONICLE_PAGE_SIZE) - 1);
  const current = Math.max(0, Math.min(page, last));
  return { page: current, last, entries: entries.slice(current * CHRONICLE_PAGE_SIZE, (current + 1) * CHRONICLE_PAGE_SIZE) };
}
export function receiptRound(entry: Pick<PublicCommittedAction, 'events'>): number | null {
  const round = entry.events[0]?.round;
  return typeof round === 'number' && Number.isSafeInteger(round) && round >= 1 ? round : null;
}
export function receiptTime(value: string): string | null {
  // Missing/invalid historical fields are omitted, never replaced with today's date.
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(value) && Number.isFinite(Date.parse(value))
    ? new Date(value).toISOString().replace('T', ' ').replace('.000Z', ' UTC').replace('Z', ' UTC') : null;
}
