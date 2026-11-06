// Offline only. Preserve canonical IDs; never update gameplay or atlas data.
import { readFile, writeFile } from 'node:fs/promises';
import { textChecksum } from './text-checksum.mjs';
const read = path => readFile(new URL(path, import.meta.url), 'utf8');
const catalogText = await read('../../backend/app/data/countries.json');
const catalog = JSON.parse(catalogText), flags = JSON.parse(await read('../src/flags/countries.json'));
const ruleText = await read('../../backend/app/engine/population_rules.py');
const boundsText = /POPULATION_UPPER_BOUNDS = \(([\s\S]*?)\)/.exec(ruleText)?.[1];
if (!boundsText) throw Error('Population bounds unavailable');
const bounds = boundsText.split(',').map(s => s.trim()).filter(Boolean).map(s => Number(s.replaceAll('_','')));
if (bounds.length !== 8 || bounds.some(n => !Number.isSafeInteger(n))) throw Error('Unexpected population bounds');
const geoText = await read('../data/geonames-countryInfo.txt');
const capitals = new Map(geoText.split(/\r?\n/).filter(line => line && !line.startsWith('#')).map(line => {
  const fields = line.split('\t'); return [fields[0].toLowerCase(), fields[5].trim()];
}));
// Omit multi-seat, disputed, transitional or otherwise qualified entries rather
// than making the gazetteer's single capital column imply a complete account.
const qualified = new Set(['benin','bolivia','cote-d-ivoire','equatorial-guinea','indonesia','israel','malaysia','nauru','netherlands','south-africa','sri-lanka','state-of-palestine','swaziland','switzerland']);
const sha = textChecksum;
const output = { dataset: catalog.dataset_id, populationSource: catalog.source_url,
  catalogSha256: sha(catalogText), capitalSource: 'https://download.geonames.org/export/dump/countryInfo.txt',
  capitalLicense: 'https://creativecommons.org/licenses/by/4.0/', capitalSha256: sha(geoText),
  capitalCheckedOn: '2026-11-03', capitalNote: 'GeoNames reference; qualified or changing capital arrangements are omitted.',
  countries: catalog.countries.map(country => ({ ...country,
    startingSoldiers: bounds.filter(limit => country.population > limit).length + 1,
    capital: qualified.has(country.id) ? null : capitals.get(flags[country.id]) || null,
  })) };
const text = JSON.stringify(output, null, 2) + '\n';
const destination = new URL('../src/country/reference.generated.json', import.meta.url);
if (process.argv.includes('--check')) {
  if (await readFile(destination, 'utf8') !== text) throw Error('Country reference drift: rerun build-country-reference.mjs');
} else await writeFile(destination, text);
console.log(JSON.stringify({ countries: output.countries.length, capitals: output.countries.filter(c => c.capital).length }));
