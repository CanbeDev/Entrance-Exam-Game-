import { readFile, readdir } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { soundAssets, soundUrl } from '../src/sound/assets.ts';

const defaultDirectory = new URL('../public/assets/sounds/', import.meta.url);
const sameKeys = (value, keys) => value && typeof value === 'object' && !Array.isArray(value)
  && Object.keys(value).sort().join(',') === keys.sort().join(',');

export function validateSoundManifest(manifest) {
  if (!sameKeys(manifest, ['provenance', 'method', 'files'])
      || typeof manifest.provenance !== 'string' || !manifest.provenance
      || manifest.method !== 'Byte-identical copies; originals unchanged'
      || !Array.isArray(manifest.files) || manifest.files.length !== 18
      || Object.keys(soundAssets).length !== 18) throw Error('Invalid sound manifest');
  const events = new Set(), originals = new Set(), paths = new Set();
  for (const row of manifest.files) {
    if (!sameKeys(row, ['event', 'original', 'runtime', 'bytes', 'sha256'])
        || !Object.hasOwn(soundAssets, row.event) || events.has(row.event)
        || row.original !== soundAssets[row.event] || originals.has(row.original)
        || row.runtime !== soundUrl(row.event) || paths.has(row.runtime)
        || !Number.isSafeInteger(row.bytes) || row.bytes <= 0
        || typeof row.sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(row.sha256)) {
      throw Error('Inconsistent sound manifest mapping');
    }
    events.add(row.event); originals.add(row.original); paths.add(row.runtime);
  }
  return manifest.files;
}

/** Public scope: integrity against reviewed manifest, not original-source equality. */
export async function verifyRuntimeSounds(directory = defaultDirectory) {
  const manifest = JSON.parse(await readFile(new URL('manifest.json', directory), 'utf8'));
  const rows = validateSoundManifest(manifest);
  const expected = ['manifest.json', ...rows.map(row => `${row.event}.mp3`)].sort();
  const entries = await readdir(directory, { withFileTypes: true });
  if (entries.some(entry => !entry.isFile())
      || entries.map(entry => entry.name).sort().join('\n') !== expected.join('\n')) {
    throw Error('Missing or unexpected runtime sound asset');
  }
  for (const row of rows) {
    const bytes = await readFile(new URL(`${row.event}.mp3`, directory));
    if (bytes.length !== row.bytes || createHash('sha256').update(bytes).digest('hex') !== row.sha256) {
      throw Error(`Runtime sound hash/size mismatch: ${row.event}`);
    }
  }
  return rows;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  await verifyRuntimeSounds();
  console.log('PUBLIC verification: 18 runtime sounds/mappings/hashes verified; original sources not checked.');
}
