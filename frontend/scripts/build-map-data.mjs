import { readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { textChecksum } from './text-checksum.mjs';
import { parseMapSvg } from './map-source.mjs';
import { bounds, centroid, contains, edgeDistance, interiorAnchor, parsePath, signedArea } from '../src/map/geometry.ts';
import { calibrate, project } from '../src/map/projection.ts';

const hash = text => createHash('sha256').update(text).digest('hex');
const normalize = name => name.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]/g, '');
const round = n => Math.round(n * 1e6) / 1e6;
export function buildMap({ svg, catalogText, aliases, fallbacks, reference }) {
  const source = parseMapSvg(svg), catalog = JSON.parse(catalogText);
  if (hash(svg) !== reference.svgSha256) throw new Error('SVG identity changed: review projection/reference calibration');
  const names = new Map(), ids = new Set();
  for (const c of catalog.countries) {
    if (ids.has(c.id) || names.has(normalize(c.name))) throw new Error('Duplicate canonical country');
    ids.add(c.id); names.set(normalize(c.name), c.id);
  }
  for (const id of Object.keys(aliases)) if (!ids.has(id)) throw new Error('Alias has unknown canonical ID');
  const aliasKeys = Object.values(aliases).map(a => a.svgKey);
  if (new Set(aliasKeys).size !== aliasKeys.length) throw new Error('Duplicate alias group');
  const grouped = new Map();
  source.paths.forEach((p, index) => {
    if (!grouped.has(p.key)) grouped.set(p.key, { key: p.key, name: p.name, pathIndices: [], rings: [] });
    const group = grouped.get(p.key);
    if (group.name !== p.name) throw new Error('Ambiguous SVG group name');
    group.pathIndices.push(index); group.rings.push(...parsePath(p.d));
  });
  const controlPairs = reference.controls.map(c => {
    const group = grouped.get(c.key);
    if (!group) throw new Error('Missing projection control geometry');
    const largest = [...group.rings].sort((a, b) => Math.abs(signedArea(b)) - Math.abs(signedArea(a)))[0];
    return { geographic: c.coordinates, svg: centroid(largest), key: c.key };
  });
  const calibration = calibrate(controlPairs);
  const controlResiduals = controlPairs.map(c => ({ key: c.key, residual: Math.hypot(...['x', 'y'].map(axis => project(c.geographic, calibration)[axis] - c.svg[axis])) }));
  if (controlResiduals.some(c => c.residual > reference.controlTolerance)) throw new Error('Projection calibration did not match source geometry');
  const validation = reference.validation.map(c => {
    const p = project(c.coordinates, calibration), group = grouped.get(c.key);
    if (!group) throw new Error('Missing projection validation geometry');
    return { key: c.key, x: p.x, y: p.y, residual: contains(p, group.rings) ? 0 : edgeDistance(p, group.rings) };
  });
  if (validation.some(v => v.residual > reference.validationTolerance)) throw new Error('Independent projection validation failed: ' + JSON.stringify(validation.filter(v => v.residual > reference.validationTolerance)));
  const matched = new Map();
  const groups = [...grouped.values()].map(group => {
    const aliasEntry = Object.entries(aliases).find(([, a]) => a.svgKey === group.key);
    if (aliasEntry && aliasEntry[1].svgName !== group.name) throw new Error('Alias source label changed');
    // BQBO repeats the Netherlands label; it is deliberately NOT canonical NL.
    const canonicalId = group.key === 'BQBO' ? null : aliasEntry?.[0] ?? names.get(normalize(group.name)) ?? null;
    if (canonicalId && matched.has(canonicalId)) throw new Error('Ambiguous many-to-one country mapping');
    const box = bounds(group.rings);
    if (box.minX < -1e-6 || box.minY < -1e-6 || box.maxX > 2000.000001 || box.maxY > 857.000001) throw new Error('Geometry outside viewport');
    if (canonicalId) matched.set(canonicalId, group);
    return { key: group.key, name: group.name, canonicalId, pathIndices: group.pathIndices, bounds: box };
  });
  for (const alias of Object.values(aliases)) if (!grouped.has(alias.svgKey)) throw new Error('Unused alias');
  const missing = catalog.countries.filter(c => !matched.has(c.id)).map(c => c.id).sort();
  if (JSON.stringify(missing) !== JSON.stringify(Object.keys(fallbacks).sort())) throw new Error('Missing/unreviewed fallback coverage: ' + missing.join(', '));
  const countries = catalog.countries.map(c => {
    const group = matched.get(c.id), fallback = fallbacks[c.id];
    if (fallback && (fallback.source !== reference.source || fallback.sourceSha256 !== reference.sourceSha256
      || !fallback.method || !fallback.referenceCode)) throw new Error('Missing fallback provenance');
    const anchor = group ? interiorAnchor(group.rings) : project(fallback.coordinates, calibration);
    // Round then re-check containment; a tiny island must not be rounded out of existence.
    const point = { x: round(anchor.x), y: round(anchor.y) };
    if (![point.x, point.y].every(Number.isFinite) || point.x <= 0 || point.y <= 0 || point.x >= 2000 || point.y >= 857
      || group && !contains(point, group.rings)) throw new Error('Invalid country anchor: ' + c.id);
    return { id: c.id, name: c.name, groupKey: group?.key ?? null, anchor: point, missingShape: !group,
      anchorMethod: group ? 'Largest-landmass area centroid, containment checked; interior search when necessary' : fallback.method,
      ...(fallback ? { provenance: fallback } : {}) };
  });
  return { schemaVersion: 1, metadata: { sourceSha256: hash(svg), datasetSha256: textChecksum(catalogText), datasetId: catalog.dataset_id,
    sourceUrl: reference.svgSource, licenseNotice: source.licenseNotice,
    reference, calibration, controlResiduals, validation, ignoredZeroRadiusCircles: source.circles,
    audit: { paths: source.paths.length, groups: groups.length, countries: countries.length, geometryCountries: matched.size,
      fallbackCountries: missing.length, aliases: Object.keys(aliases).length, neutralGroups: groups.filter(g => !g.canonicalId).length,
      neutralPaths: groups.filter(g => !g.canonicalId).reduce((s, g) => s + g.pathIndices.length, 0) } },
    viewBox: source.viewBox, paths: source.paths.map(p => ({ d: p.d, groupKey: p.key })), groups, countries };
}
export function assertCurrent(expected, actual) { if (expected !== actual) throw new Error('Generated map data drift: run node scripts/build-map-data.mjs and review'); }
export async function generate({ check = false, output = new URL('../src/map/mapData.generated.json', import.meta.url) } = {}) {
  const root = new URL('../', import.meta.url), json = async path => JSON.parse(await readFile(new URL(path, root), 'utf8'));
  const [svg, catalogText, aliases, fallbacks, reference] = await Promise.all([
    readFile(new URL('public/assets/world-map.svg', root), 'utf8'),
    readFile(new URL('../backend/app/data/countries.json', root), 'utf8'),
    json('src/map/country-aliases.json'), json('src/map/fallback-anchors.json'), json('src/map/reference-points.json'),
  ]);
  const text = JSON.stringify(buildMap({ svg, catalogText, aliases, fallbacks, reference }), null, 2) + '\n';
  if (check) assertCurrent(text, await readFile(output, 'utf8')); else await writeFile(output, text);
  return JSON.parse(text).metadata.audit;
}
if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const at = process.argv.indexOf('--output');
  try { console.log(JSON.stringify(await generate({ check: process.argv.includes('--check'),
    ...(at >= 0 ? { output: resolve(process.argv[at + 1]) } : {}) }))); }
  catch (error) { console.error(error.message); process.exitCode = 1; }
}
