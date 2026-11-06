import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile, writeFile, mkdtemp, rm, rmdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { createElement, isValidElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { buildMap } from '../scripts/build-map-data.mjs';
import { parseMapSvg } from '../scripts/map-source.mjs';
import { bounds, contains, edgeDistance, interiorAnchor, parsePath } from '../src/map/geometry.ts';
import { project } from '../src/map/projection.ts';
import { factionMap, formatMapCount, overlaps, segmentCrossesBox, tokenLayout, validateAtlas } from '../src/map/layout.ts';

const root = new URL('../', import.meta.url);
const text = path => readFile(new URL(path, root), 'utf8');
const json = async path => JSON.parse(await text(path));
let data, source, input, module, vite;
before(async () => {
  source = await text('public/assets/world-map.svg');
  input = { svg: source, catalogText: await text('../backend/app/data/countries.json'),
    aliases: await json('src/map/country-aliases.json'), fallbacks: await json('src/map/fallback-anchors.json'),
    reference: await json('src/map/reference-points.json') };
  data = await json('src/map/mapData.generated.json');
  vite = await createServer({ configFile: false, root: fileURLToPath(root),
    server: { middlewareMode: true, hmr: false, ws: false }, optimizeDeps: { noDiscovery: true, include: [] }, logLevel: 'silent' });
  module = await vite.ssrLoadModule('/src/map/AtlasMap.tsx');
});
after(async () => { await vite?.close(); });
const worldIds = ['brazil', 'canada', 'uk', 'norway', 'australia', 'angola', 'czechia', 'state-of-palestine', 'bahrain', 'seychelles'];
const smallIds = ['andorra', 'holy-see', 'kiribati', 'liechtenstein', 'monaco', 'san-marino', 'singapore', 'luxembourg', 'malta', 'switzerland'];
function props(ids = worldIds) {
  return { countries: ids.map((id, i) => ({ id, name: data.countries.find(c => c.id === id).name, soldiers: 10 + i, owner_id: `p${i}` })),
    players: ids.map((id, i) => ({ id: `p${i}`, kind: i ? 'npc' : 'human', starting_country_id: id })),
    turnOrder: ids.map((_, i) => `p${i}`), onSelect() {} };
}
function* nodes(element) {
  if (Array.isArray(element)) { for (const e of element) yield* nodes(e); }
  else if (isValidElement(element)) { yield element; yield* nodes(element.props.children); }
}
const render = p => renderToStaticMarkup(createElement(module.AtlasMap, p));

test('map-only extreme counts are compact while ordinary counts stay exact', () => {
  for (const n of [0, 9, 10, 999, 123456, 999999]) assert.equal(formatMapCount(n), String(n));
  assert.equal(formatMapCount(1234567), '≈1.2M');
  assert.equal(formatMapCount(1234567890), '≈1.2B');
  assert.equal(formatMapCount(Number.MAX_SAFE_INTEGER), '≈9007.2T');
  const p = props(); p.selectedId = p.countries[0].id; p.countries[0].soldiers = 1234567;
  const tree = [...nodes(module.AtlasContent(p))];
  const marker = tree.find(e => e.props['data-map-country'] === p.selectedId);
  assert.equal([...nodes(marker)].find(e => e.props.className === 'geo-atlas__number').props.children, '≈1.2M');
  assert.match(marker.props['aria-label'], /1234567 soldiers/);
  const roster = tree.find(e => e.props['data-roster-country'] === p.selectedId);
  assert.equal(roster.props['data-selected'], true);
  assert.equal([...nodes(roster)].find(e => e.props.onSelect).props.soldiers, 1234567);
  assert.match(render(p), /role="status">Selected: Brazil, 1234567/);
});

test('leader crossing detection includes text boxes and handles parallel or zero-length segments', () => {
  const box = { x: 40, y: 40, width: 20, height: 20 };
  assert.equal(segmentCrossesBox({x:0,y:50}, {x:100,y:50}, box), true);
  assert.equal(segmentCrossesBox({x:0,y:0}, {x:100,y:0}, box), false);
  assert.equal(segmentCrossesBox({x:50,y:50}, {x:50,y:50}, box), true);
  assert.equal(segmentCrossesBox({x:0,y:0}, {x:0,y:0}, box), false);
});

test('compact marker geometry does not jump when authoritative counts change', () => {
  for (const viewport of [375, 768, 1440]) {
    const p = props(smallIds), initial = tokenLayout(p.countries, data, viewport);
    p.countries.forEach(c => c.soldiers = Number.MAX_SAFE_INTEGER);
    assert.deepEqual(tokenLayout(p.countries, data, viewport), initial);
    assert.ok(initial.placements.every(t => t.width === 128 && t.height === 112));
    assert.ok(initial.placements.some(t => t.leader));
  }
});

test('dense microstate layout limits displacement and leader obstruction without dropping countries', () => {
  for (const viewport of [375, 768, 1440]) {
    const layout = tokenLayout(props(smallIds).countries, data, viewport);
    assert.equal(layout.packed, false);
    assert.equal(layout.placements.length, 10);
    const crossings = layout.placements.reduce((n, marker) => n + layout.placements.filter(other =>
      other.id !== marker.id && segmentCrossesBox(marker.anchor, marker.pin, other)).length, 0);
    assert.ok(crossings <= 5, `dense fixture has ${crossings} obstructed leaders`);
    assert.ok(layout.placements.every(t => Math.hypot(t.pin.x - t.anchor.x, t.pin.y - t.anchor.y) <= 260));
  }
});

test('selection and keyboard focus use one number ring without a selected geography rectangle', async () => {
  const css = await text('src/map/atlas.css');
  assert.match(css, /aria-pressed="true"\] \.geo-atlas__number \{ outline: 3px solid var\(--geo-forest\)/);
  assert.doesNotMatch(css, /\.geo-atlas__token\[aria-pressed="true"\] \{/);
  assert.match(css, /:focus-visible \.geo-atlas__number \{ outline: 3px solid var\(--geo-ink\); outline-offset: 2px/);
  assert.match(css, /data-selected="true"\] \.geo-token \{ border: 2px solid var\(--geo-forest\)/);
});

test('revalidated source audit and deterministic generated output match the current catalog', async () => {
  const generated = buildMap(input);
  assert.equal(JSON.stringify(generated, null, 2) + '\n', await text('src/map/mapData.generated.json'));
  assert.deepEqual(buildMap(input), generated);
  assert.deepEqual(data.metadata.audit, { paths: 470, groups: 221, countries: 195, geometryCountries: 188,
    fallbackCountries: 7, aliases: 17, neutralGroups: 33, neutralPaths: 92 });
  const catalog = JSON.parse(input.catalogText);
  assert.deepEqual(data.countries.map(c => c.id), catalog.countries.map(c => c.id));
  assert.equal(new Set(data.countries.map(c => c.id)).size, catalog.countries.length);
  assert.deepEqual(data.viewBox, [0, 0, 2000, 857]);
});

test('actual CLI --check succeeds and detects corrupt output without overwriting it', async (t) => {
  const directory = await mkdtemp(join(tmpdir(), 'geo-atlas-drift-'));
  t.after(async () => { await rm(join(directory, 'map.json'), { force: true }); await rmdir(directory); });
  const output = join(directory, 'map.json');
  await writeFile(output, 'drift\n');
  const run = args => spawnSync(process.execPath, ['scripts/build-map-data.mjs', '--check', ...args], { cwd: fileURLToPath(root), encoding: 'utf8' });
  assert.equal(run([]).status, 0);
  const failed = run(['--output', output]);
  assert.equal(failed.status, 1);
  assert.match(failed.stderr, /drift/);
  assert.equal(await readFile(output, 'utf8'), 'drift\n');
});

test('every path/subpath is preserved and all computed anchors are finite, bounded and interior', () => {
  const parsed = parseMapSvg(source);
  assert.deepEqual(data.paths.map(p => p.d), parsed.paths.map(p => p.d));
  assert.deepEqual(data.groups.flatMap(g => g.pathIndices).sort((a, b) => a - b), Array.from({ length: 470 }, (_, i) => i));
  for (const entry of data.countries) {
    assert.ok(entry.anchor.x > 0 && entry.anchor.x < 2000 && entry.anchor.y > 0 && entry.anchor.y < 857, entry.id);
    if (entry.groupKey) {
      const group = data.groups.find(g => g.key === entry.groupKey);
      const rings = group.pathIndices.flatMap(i => parsePath(data.paths[i].d));
      assert.ok(contains(entry.anchor, rings), entry.id);
      assert.ok(edgeDistance(entry.anchor, rings) > 0, entry.id);
    }
  }
});

test('concave, hole and multipart geometry chooses real interior points instead of bbox centres', () => {
  for (const d of ['M0 0L10 0L10 2L2 2L2 10L0 10Z',
    'M0 0L10 0L10 10L0 10Z M2 2L2 8L8 8L8 2Z',
    'M0 0L2 0L2 2L0 2Z M20 20L40 20L40 40L20 40Z']) {
    const rings = parsePath(d), anchor = interiorAnchor(rings);
    assert.ok(contains(anchor, rings));
    assert.ok(edgeDistance(anchor, rings) > 0);
  }
  const anchor = interiorAnchor(parsePath('M0 0L2 0L2 2L0 2Z M20 20L40 20L40 40L20 40Z'));
  assert.ok(anchor.x > 20 && anchor.y > 20, 'largest landmass selected');
  assert.throws(() => parsePath('M0 0 C1 1 2 2 3 3Z'));
  assert.throws(() => parsePath('M0 0L1 1'));
});

test('all explicit aliases resolve, and Netherlands/BQBO, Congos and Koreas remain distinct', () => {
  for (const [id, alias] of Object.entries(input.aliases)) assert.equal(data.countries.find(c => c.id === id).groupKey, alias.svgKey);
  assert.equal(data.countries.find(c => c.id === 'netherlands').groupKey, 'NL');
  assert.equal(data.groups.find(g => g.key === 'BQBO').canonicalId, null);
  assert.equal(data.countries.find(c => c.id === 'congo').groupKey, 'CG');
  assert.equal(data.countries.find(c => c.id === 'democratic-republic-of-the-congo').groupKey, 'CD');
  assert.equal(data.countries.find(c => c.id === 'north-korea').groupKey, 'KP');
  assert.equal(data.countries.find(c => c.id === 'south-korea').groupKey, 'KR');
  const aliases = structuredClone(input.aliases);
  aliases.czechia.svgKey = aliases.congo.svgKey;
  assert.throws(() => buildMap({ ...input, aliases }), /Duplicate alias/);
  const catalog = JSON.parse(input.catalogText); catalog.countries.push(catalog.countries[0]);
  assert.throws(() => buildMap({ ...input, catalogText: JSON.stringify(catalog) }), /Duplicate canonical/);
});

test('seven missing-shape anchors carry pinned geographic provenance and verified Robinson calibration', () => {
  assert.deepEqual(data.countries.filter(c => c.missingShape).map(c => c.id).sort(), Object.keys(input.fallbacks).sort());
  assert.equal(input.reference.projection, 'Robinson');
  assert.equal(data.metadata.sourceSha256, createHash('sha256').update(source).digest('hex'));
  assert.equal(data.metadata.sourceSha256, input.reference.svgSha256);
  for (const entry of data.countries.filter(c => c.missingShape)) {
    assert.equal(entry.provenance.sourceSha256, input.reference.sourceSha256);
    assert.match(entry.provenance.source, /natural-earth-vector/);
    assert.ok(entry.provenance.referenceCode && entry.provenance.method);
    const p = project(entry.provenance.coordinates, data.metadata.calibration);
    assert.ok(Math.hypot(p.x - entry.anchor.x, p.y - entry.anchor.y) < .000002);
  }
  assert.ok(data.metadata.controlResiduals.every(c => c.residual < input.reference.controlTolerance));
  assert.ok(data.metadata.validation.every(c => c.residual < input.reference.validationTolerance));
  assert.throws(() => buildMap({ ...input, fallbacks: {} }), /fallback coverage/);
});

test('licence notices are retained and unsafe/unsupported XML or attributes are rejected', () => {
  assert.equal(data.metadata.licenseNotice, parseMapSvg(source).licenseNotice);
  assert.match(data.metadata.licenseNotice, /Copyright \(c\) 2020 Pareto Softare/);
  assert.match(data.metadata.licenseNotice, /permission notice shall be included/);
  assert.match(data.metadata.reference.projectionLicense, /Copyright 2013-2021 Mike Bostock/);
  for (const svg of [
    '<!DOCTYPE svg [<!ENTITY x SYSTEM "file:///private">]>' + source,
    source.replace('<svg ', '<svg onload="bad()" '), source.replace('</svg>', '<script>bad()</script></svg>'),
    source.replace('<path ', '<path href="https://untrusted.invalid" '),
    source.replace('<path ', '<path transform="scale(2)" '), source.replace('id="AF"', 'id="AL"'),
    source.replace('fill="#ececec"', 'fill="url(https://untrusted.invalid)"'), source.replace('0 0 2000 857', '0 0 0 0'),
  ]) assert.throws(() => parseMapSvg(svg));
});

test('collision placement is deterministic, disjoint and bounded at 375/768/1440, including extreme counts', () => {
  for (const viewport of [375, 768, 1440]) for (const ids of [worldIds, smallIds]) {
    const p = props(ids); p.countries.forEach(c => { c.soldiers = Number.MAX_SAFE_INTEGER; });
    const layout = tokenLayout(p.countries, data, viewport);
    assert.equal(layout.placements.length, 10);
    assert.deepEqual(layout, tokenLayout([...p.countries].reverse(), data, viewport));
    layout.placements.forEach((a, i) => {
      assert.ok(a.x >= 0 && a.y >= 0 && a.x + a.width <= layout.width && a.y + a.height <= layout.height);
      for (const b of layout.placements.slice(i + 1)) assert.equal(overlaps(a, b), false);
    });
    assert.ok(layout.placements.some(c => c.leader));
    assert.ok(layout.width >= viewport);
  }
});

test('ownership/selection changes cannot reorder faction colours or geographic placements', () => {
  const p = props(), before = tokenLayout(p.countries, data, 768), factions = factionMap(p);
  p.countries[1].owner_id = p.players[0].id;
  p.selectedId = p.countries[1].id;
  p.playingId = p.countries[3].id;
  assert.deepEqual(factionMap(p), factions);
  assert.deepEqual(tokenLayout(p.countries, data, 768), before);
  assert.equal(factions.get('p0'), 0);
  assert.equal(new Set(factions.values()).size, 10);
});

test('multipart ownership colour updates every fragment while nonparticipants and territories stay neutral', () => {
  const p = props(); p.countries.find(c => c.id === 'australia').owner_id = 'p0';
  const tree = [...nodes(module.AtlasContent(p))];
  const pieces = tree.filter(e => e.type === 'path' && e.props['data-map-group'] === 'Australia');
  assert.equal(pieces.length, 2);
  assert.ok(pieces.every(e => e.props.fill === 'var(--geo-forest)' && e.props.fillOpacity === .42));
  const neutral = tree.filter(e => e.type === 'path' && ['BQBO', 'GL', 'TW', 'NL'].includes(e.props['data-map-group']));
  assert.ok(neutral.length >= 4);
  assert.ok(neutral.every(e => e.props.fill === 'var(--geo-land)' && !e.props.onClick));
});

test('map paths, native token buttons and roster share exactly the same one-ID selection callback', () => {
  const p = props(), calls = []; p.onSelect = id => calls.push(id);
  const tree = [...nodes(module.AtlasContent(p))];
  for (const country of p.countries) {
    const token = tree.find(e => e.props['data-map-country'] === country.id);
    const row = tree.find(e => e.props['data-roster-country'] === country.id);
    const soldier = [...nodes(row.props.children)].find(e => e.props.onSelect);
    const path = tree.find(e => e.type === 'path' && e.props['data-country'] === country.id);
    assert.equal(token.type, 'button'); assert.equal(token.props.type, 'button');
    assert.equal(token.props.onClick, soldier.props.onSelect);
    assert.equal(token.props.onClick, path.props.onClick);
    const count = calls.length; token.props.onClick(); assert.deepEqual(calls.slice(count), [country.id]);
    soldier.props.onSelect(); assert.equal(calls.at(-1), country.id);
  }
  assert.equal(calls.length, 20);
});

test('roster preserves all ten names/owners/large counts and native keyboard/focus semantics', () => {
  const p = props(smallIds); p.countries[0].soldiers = 1234567; p.selectedId = p.countries[0].id;
  const html = render(p);
  assert.equal((html.match(/data-map-country=/g) ?? []).length, 10);
  assert.equal((html.match(/data-roster-country=/g) ?? []).length, 10);
  assert.match(html, /1234567 soldiers/);
  assert.match(html, /role="region"[^>]*aria-label="Scrollable world map"[^>]*tabindex="0"/);
  assert.match(html, /aria-pressed="true"/);
  assert.match(html, /location marker: no source border/);
  assert.doesNotMatch(html, /<svg[^>]*>\s*<button|<img|dangerouslySetInnerHTML/);
});

test('FROM/TARGET/PLAYING and battle relationships are explicit and no battle line is invented', () => {
  const p = props(); p.fromId = 'brazil'; p.targetId = 'uk'; p.playingId = 'norway';
  let html = render(p);
  assert.match(html, /data-state="from"/); assert.match(html, /data-state="target"/); assert.match(html, /data-state="playing"/);
  assert.doesNotMatch(html, /<line class="geo-atlas__battle"/);
  p.battle = { source_id: 'brazil', target_id: 'uk', preview: true };
  html = render(p); assert.match(html, /Preview: Brazil → United Kingdom/);
  assert.match(html, /<line class="geo-atlas__battle"/);
  p.battle.preview = false; assert.match(render(p), /Attack: Brazil → United Kingdom/);
  p.battle.target_id = 'not-in-game'; assert.throws(() => render(p));
});

test('canvas/leader coordinates share one transform and CSS supports scroll, focus and reduced motion', async () => {
  for (const viewport of [375, 768, 1440]) {
    const layout = tokenLayout(props(smallIds).countries, data, viewport);
    assert.equal(layout.height / layout.width, 857 / 2000);
    for (const token of layout.placements) {
      const anchor = data.countries.find(c => c.id === token.id).anchor;
      assert.ok(Math.abs(token.anchor.x / layout.scale - anchor.x) < 1e-9);
      assert.ok(token.pin.x >= 0 && token.pin.x <= layout.width);
    }
  }
  const css = await text('src/map/atlas.css');
  assert.match(css, /overflow-x: auto/); assert.match(css, /prefers-reduced-motion/);
  assert.match(await text('src/ui/components.css'), /:focus-visible/);
});

test('invalid identities/counts fail closed; render does not mutate input or create service activity', async () => {
  const p = props(), before = JSON.stringify(p);
  const original = globalThis.fetch;
  let requests = 0;
  globalThis.fetch = () => { requests++; throw new Error('Atlas rendering must be offline'); };
  try { render(p); assert.equal(requests, 0); } finally { globalThis.fetch = original; }
  assert.equal(JSON.stringify(p), before);
  p.countries[0].owner_id = 'unknown'; assert.throws(() => validateAtlas(p, data));
  p.countries[0].owner_id = 'p0'; p.countries[0].soldiers = NaN; assert.throws(() => render(p));
  const src = await text('src/map/AtlasMap.tsx');
  assert.doesNotMatch(src, /\b(?:fetch|XMLHttpRequest|WebSocket|EventSource|axios)\b|dangerouslySetInnerHTML|\.innerHTML|controller/);
  assert.doesNotMatch(await text('src/main.tsx'), /AtlasMap|AtlasPreview/);
});
