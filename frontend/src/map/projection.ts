import type { Point } from './geometry.ts';

// Robinson interpolation adapted from d3-geo-projection; ISC notice is preserved
// in reference-points.json and the generated metadata. No runtime dependency.
const table = [[.9986, -.062], [1, 0], [.9986, .062], [.9954, .124], [.9900, .186], [.9822, .248],
  [.9730, .310], [.9600, .372], [.9427, .434], [.9216, .4958], [.8962, .5571], [.8679, .6176],
  [.8350, .6769], [.7986, .7346], [.7597, .7903], [.7186, .8435], [.6732, .8936], [.6213, .9394], [.5722, .9761], [.5322, 1]];
export function robinson(longitude: number, latitude: number): Point {
  if (!Number.isFinite(longitude) || !Number.isFinite(latitude) || Math.abs(longitude) > 180 || Math.abs(latitude) > 90) throw new Error('Invalid geodetic reference');
  const n = Math.min(18, Math.abs(latitude) / 5), i = Math.floor(n), f = n - i;
  const a = table[i], b = table[i + 1], c = table[Math.min(19, i + 2)];
  const interpolate = (axis: number) => b[axis] + f * (c[axis] - a[axis]) / 2 + f * f * (c[axis] - 2 * b[axis] + a[axis]) / 2;
  return { x: longitude * Math.PI / 180 * interpolate(0), y: Math.sign(latitude) * interpolate(1) * 1.593415793900743 };
}
export interface Calibration { xScale: number; xOffset: number; yScale: number; yOffset: number }
export function calibrate(pairs: { geographic: readonly number[]; svg: Point }[]): Calibration {
  if (pairs.length < 4) throw new Error('Insufficient projection controls');
  function fit(axis: 'x' | 'y') {
    const values = pairs.map(p => ({ raw: robinson(p.geographic[0], p.geographic[1])[axis], svg: p.svg[axis] }));
    const mean = values.reduce((a, p) => a + p.raw, 0) / values.length;
    const target = values.reduce((a, p) => a + p.svg, 0) / values.length;
    const denominator = values.reduce((a, p) => a + (p.raw - mean) ** 2, 0);
    if (!denominator) throw new Error('Degenerate projection controls');
    const scale = values.reduce((a, p) => a + (p.raw - mean) * (p.svg - target), 0) / denominator;
    return [scale, target - scale * mean];
  }
  const [xScale, xOffset] = fit('x'), [yScale, yOffset] = fit('y');
  return { xScale, xOffset, yScale, yOffset };
}
export function project(coordinates: readonly number[], calibration: Calibration): Point {
  const raw = robinson(coordinates[0], coordinates[1]);
  return { x: calibration.xOffset + raw.x * calibration.xScale, y: calibration.yOffset + raw.y * calibration.yScale };
}
