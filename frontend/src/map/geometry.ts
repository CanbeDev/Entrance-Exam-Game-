export type Point = { x: number; y: number };
export type Ring = Point[];
export type Bounds = { minX: number; minY: number; maxX: number; maxY: number };

/** The pinned source has only M/m, implicit line pairs, l and Z/z. Fail on drift. */
export function parsePath(d: string): Ring[] {
  const tokens = d.match(/[MmLlZz]|[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?/g) ?? [];
  if (d.replace(/[MmLlZz]|[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?|[\s,]+/g, '')) throw new Error('Unsupported path syntax');
  const rings: Ring[] = [];
  let ring: Ring = [], point = { x: 0, y: 0 }, command = '', index = 0;
  while (index < tokens.length) {
    if (/^[A-Za-z]$/.test(tokens[index])) command = tokens[index++];
    if (/^[Zz]$/.test(command)) {
      if (ring.length < 3 || Math.abs(signedArea(ring)) < 1e-10) throw new Error('Degenerate path');
      rings.push(ring); point = ring[0]; ring = []; command = ''; continue;
    }
    if (!/^[MmLl]$/.test(command) || index + 1 >= tokens.length) throw new Error('Malformed path');
    const x = Number(tokens[index++]), y = Number(tokens[index++]);
    if (!Number.isFinite(x) || !Number.isFinite(y)) throw new Error('Nonfinite path');
    const next = { x: x + (command === command.toLowerCase() ? point.x : 0), y: y + (command === command.toLowerCase() ? point.y : 0) };
    if (/^[Mm]$/.test(command)) {
      if (ring.length) throw new Error('Unclosed subpath');
      command = command === 'M' ? 'L' : 'l';
    } else if (!ring.length) throw new Error('Line without move');
    point = next; ring.push(point);
  }
  if (ring.length || !rings.length) throw new Error('Unclosed path');
  return rings;
}

export function signedArea(ring: Ring): number {
  return ring.reduce((sum, p, i) => { const q = ring[(i + 1) % ring.length]; return sum + p.x * q.y - q.x * p.y; }, 0) / 2;
}
export function bounds(rings: Ring[]): Bounds {
  const points = rings.flat();
  if (!points.length) throw new Error('Missing geometry');
  return { minX: Math.min(...points.map(p => p.x)), minY: Math.min(...points.map(p => p.y)),
    maxX: Math.max(...points.map(p => p.x)), maxY: Math.max(...points.map(p => p.y)) };
}
export function centroid(ring: Ring): Point {
  let x = 0, y = 0;
  ring.forEach((p, i) => { const q = ring[(i + 1) % ring.length], cross = p.x * q.y - q.x * p.y;
    x += (p.x + q.x) * cross; y += (p.y + q.y) * cross; });
  const divisor = 6 * signedArea(ring);
  if (!divisor) throw new Error('Zero-area polygon');
  return { x: x / divisor, y: y / divisor };
}
export function contains(point: Point, rings: Ring[]): boolean {
  let winding = 0;
  for (const ring of rings) ring.forEach((a, i) => {
    const b = ring[(i + 1) % ring.length], cross = (b.x - a.x) * (point.y - a.y) - (point.x - a.x) * (b.y - a.y);
    if (a.y <= point.y && b.y > point.y && cross > 0) winding++;
    if (a.y > point.y && b.y <= point.y && cross < 0) winding--;
  });
  return winding !== 0;
}
export function edgeDistance(point: Point, rings: Ring[]): number {
  let minimum = Infinity;
  for (const ring of rings) ring.forEach((a, i) => {
    const b = ring[(i + 1) % ring.length], dx = b.x - a.x, dy = b.y - a.y;
    const t = dx || dy ? Math.max(0, Math.min(1, ((point.x - a.x) * dx + (point.y - a.y) * dy) / (dx * dx + dy * dy))) : 0;
    minimum = Math.min(minimum, Math.hypot(point.x - a.x - t * dx, point.y - a.y - t * dy));
  });
  return minimum;
}

/** Area centroid when interior; deterministic branch-and-bound interior search otherwise. */
export function interiorAnchor(rings: Ring[]): Point {
  const largest = [...rings].sort((a, b) => Math.abs(signedArea(b)) - Math.abs(signedArea(a)))[0];
  const center = centroid(largest);
  if (contains(center, rings) && contains(center, [largest]) && edgeDistance(center, rings) > 1e-8) return center;
  const box = bounds([largest]), size = Math.min(box.maxX - box.minX, box.maxY - box.minY);
  const tolerance = Math.max(0.00001, Math.min(0.25, size / 100));
  const distance = (p: Point) => edgeDistance(p, rings) * (contains(p, rings) && contains(p, [largest]) ? 1 : -1);
  const cell = (x: number, y: number, h: number) => { const d = distance({ x, y }); return { x, y, h, d, max: d + h * Math.SQRT2 }; };
  const queue: (Point & { h: number; d: number; max: number })[] = [];
  for (let x = box.minX; x < box.maxX; x += size) for (let y = box.minY; y < box.maxY; y += size) queue.push(cell(x + size / 2, y + size / 2, size / 2));
  let best = cell(center.x, center.y, 0), iterations = 0;
  while (queue.length) {
    queue.sort((a, b) => b.max - a.max || a.x - b.x || a.y - b.y);
    const current = queue.shift()!;
    if (current.d > best.d) best = current;
    if (current.max - best.d <= tolerance) continue;
    const h = current.h / 2;
    for (const dx of [-h, h]) for (const dy of [-h, h]) queue.push(cell(current.x + dx, current.y + dy, h));
    if (++iterations > 100000) throw new Error('Interior search did not converge');
  }
  if (best.d <= 0 || !contains(best, rings)) throw new Error('No verified interior anchor');
  return { x: best.x, y: best.y };
}
