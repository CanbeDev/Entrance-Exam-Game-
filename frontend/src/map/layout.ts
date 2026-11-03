import type { Point } from './geometry.ts';
import type { AtlasProps, MapData } from './types.ts';
export const TOKEN_HEIGHT = 112;
const PIN_Y = 24;
/** Map-only approximation; authoritative and accessible counts remain exact. */
export function formatMapCount(count: number): string {
  if (count < 1_000_000) return String(count);
  const units = [[1e12, 'T'], [1e9, 'B'], [1e6, 'M']] as const;
  const [divisor, suffix] = units.find(([value]) => count >= value)!;
  return `≈${(count / divisor).toFixed(1).replace(/\.0$/, '')}${suffix}`;
}
/** Whether a leader passes through another marker's padded label box. */
export function segmentCrossesBox(a: Point, b: Point, box: Pick<TokenPlacement, 'x' | 'y' | 'width' | 'height'>): boolean {
  let start = 0, end = 1;
  for (const axis of ['x', 'y'] as const) {
    const low = box[axis] - 4, high = box[axis] + (axis === 'x' ? box.width : box.height) + 4;
    const delta = b[axis] - a[axis];
    if (delta === 0) { if (a[axis] < low || a[axis] > high) return false; }
    else {
      const t1 = (low - a[axis]) / delta, t2 = (high - a[axis]) / delta;
      start = Math.max(start, Math.min(t1, t2)); end = Math.min(end, Math.max(t1, t2));
      if (start > end) return false;
    }
  }
  return true;
}
export interface TokenPlacement {
  id: string; x: number; y: number; width: number; height: number; pin: Point; anchor: Point; leader: boolean;
}
export function overlaps(a: Pick<TokenPlacement, 'x' | 'y' | 'width' | 'height'>,
  b: Pick<TokenPlacement, 'x' | 'y' | 'width' | 'height'>, gap = 8): boolean {
  return a.x < b.x + b.width + gap && a.x + a.width + gap > b.x && a.y < b.y + b.height + gap && a.y + a.height + gap > b.y;
}
export function validateAtlas(props: AtlasProps, data: MapData): void {
  const known = new Set(data.countries.map(c => c.id));
  const owners = new Set(props.players.map(p => p.id)), ids = props.countries.map(c => c.id);
  if (props.countries.length > 10 || props.players.length > 10 || owners.size !== props.players.length
    || new Set(ids).size !== ids.length || props.turnOrder.length !== owners.size || new Set(props.turnOrder).size !== owners.size
    || props.turnOrder.some(id => !owners.has(id))) throw new Error('Invalid atlas identity/order');
  if (props.players.some(p => !known.has(p.starting_country_id) || !['human', 'npc'].includes(p.kind))) throw new Error('Invalid participant identity');
  if (props.countries.some(c => !known.has(c.id) || !owners.has(c.owner_id) || !c.name
    || !Number.isSafeInteger(c.soldiers) || c.soldiers < 0)) throw new Error('Invalid atlas country props');
  for (const id of [props.selectedId, props.fromId, props.targetId, props.playingId]) if (id && !ids.includes(id)) throw new Error('Unknown atlas selection');
  if (props.battle && (!ids.includes(props.battle.source_id) || !ids.includes(props.battle.target_id)
    || props.battle.source_id === props.battle.target_id)) throw new Error('Invalid battle relationship');
}
export function factionMap(props: Pick<AtlasProps, 'players' | 'turnOrder'>): Map<string, number> {
  let rival = 0;
  return new Map(props.turnOrder.map(id => [id, props.players.find(p => p.id === id)?.kind === 'human' ? 0 : ++rival]));
}
export function tokenLayout(countries: AtlasProps['countries'], data: MapData, viewportWidth: number) {
  if (!Number.isFinite(viewportWidth) || viewportWidth <= 0) throw new Error('Invalid map width');
  const width = Math.max(1000, viewportWidth), height = width * 857 / 2000, scale = width / 2000;
  const entries = [...countries].sort((a, b) => a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
  const models = entries.map(c => {
    const entry = data.countries.find(e => e.id === c.id);
    if (!entry) throw new Error('Unknown country anchor');
    return { id: c.id, width: 128, height: TOKEN_HEIGHT,
      anchor: { x: entry.anchor.x * scale, y: entry.anchor.y * scale } };
  });
  let placements: TokenPlacement[] = [];
  for (const model of models) {
    const candidates: { x: number; y: number; distance: number }[] = [];
    const desiredX = Math.max(0, Math.min(width - model.width, model.anchor.x - model.width / 2));
    const desiredY = Math.max(0, Math.min(height - model.height, model.anchor.y - PIN_Y));
    candidates.push({ x: desiredX, y: desiredY, distance: 0 });
    for (let y = 0; y <= height - model.height; y += 16) for (let x = 0; x <= width - model.width; x += 16) {
      candidates.push({ x, y, distance: Math.hypot(x + model.width / 2 - model.anchor.x, y + PIN_Y - model.anchor.y) });
    }
    const available = candidates.filter(p => !placements.some(other => overlaps({ ...model, ...p }, other)));
    const nearby = available.filter(p => p.distance <= 240);
    const ranked = (nearby.length ? nearby : available).map(p => {
      const pin = { x: p.x + model.width / 2, y: p.y + PIN_Y };
      const crossings = placements.filter(other => segmentCrossesBox(model.anchor, pin, other)
        || segmentCrossesBox(other.anchor, other.pin, { ...model, ...p })).length;
      const coveredAnchors = models.filter(other => other.id !== model.id
        && segmentCrossesBox(other.anchor, other.anchor, { ...model, ...p })).length;
      return { ...p, score: p.distance + (crossings + coveredAnchors) * 64 };
    });
    ranked.sort((a, b) => a.score - b.score || a.distance - b.distance || a.y - b.y || a.x - b.x);
    const position = ranked[0];
    if (!position) { placements = []; break; }
    const pin = { x: position.x + model.width / 2, y: position.y + PIN_Y };
    placements.push({ ...model, x: position.x, y: position.y, pin, leader: Math.hypot(pin.x - model.anchor.x, pin.y - model.anchor.y) > 1 });
  }
  // A deterministic packing fallback guarantees all ten tokens remain visible,
  // including extreme safe-integer counts. Leader lines retain geographic identity.
  const packed = placements.length !== models.length;
  if (packed) {
    const cellWidth = Math.max(144, ...models.map(m => m.width)) + 8, cellHeight = TOKEN_HEIGHT + 8;
    const columns = Math.floor(width / cellWidth), rows = Math.floor(height / cellHeight);
    if (columns * rows < models.length) throw new Error('Map cannot fit all tokens');
    placements = models.map((model, i) => {
      const x = i % columns * cellWidth, y = Math.floor(i / columns) * cellHeight;
      return { ...model, x, y, pin: { x: x + model.width / 2, y: y + PIN_Y }, leader: true };
    });
  }
  return { width, height, scale, placements, packed };
}
