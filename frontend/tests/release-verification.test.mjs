import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile, writeFile, copyFile, mkdtemp, readdir, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve, sep } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';
import { textChecksum } from '../scripts/text-checksum.mjs';
import { validateSoundManifest, verifyRuntimeSounds } from '../scripts/verify-sound-assets.mjs';

const runtime = new URL('../public/assets/sounds/', import.meta.url);
test('text checksums preserve the existing identifiers across LF, CRLF and mixed endings', () => {
  const lf = '{\n  "name": "country"\n}\n';
  const crlf = lf.replaceAll('\n', '\r\n');
  assert.equal(textChecksum(lf), createHash('sha256').update(crlf).digest('hex'));
  assert.equal(textChecksum(crlf), textChecksum(lf));
  assert.equal(textChecksum(lf.replace('\n', '\r\n')), textChecksum(lf));
  assert.equal(textChecksum(lf.replaceAll('\n', '\r')), textChecksum(lf));
  assert.notEqual(textChecksum(lf.replace('country', 'different')), textChecksum(lf));
});

test('contract, map and capital metadata keep their original reviewed checksums without regeneration', async () => {
  const read = path => readFile(new URL(path, import.meta.url), 'utf8');
  const generated = await read('../src/api/generated.ts');
  assert.ok(generated.includes(textChecksum(await read('../../docs/openapi.json'))));
  const map = JSON.parse(await read('../src/map/mapData.generated.json'));
  const reference = JSON.parse(await read('../src/country/reference.generated.json'));
  const catalog = textChecksum(await read('../../backend/app/data/countries.json'));
  assert.equal(map.metadata.datasetSha256, catalog);
  assert.equal(reference.catalogSha256, catalog);
  assert.equal(reference.capitalSha256, textChecksum(await read('../data/geonames-countryInfo.txt')));
});

test('public sound manifest rejects missing, duplicate, unexpected and inconsistent mappings', async () => {
  const manifest = JSON.parse(await readFile(new URL('manifest.json', runtime), 'utf8'));
  assert.equal(validateSoundManifest(manifest).length, 18);
  for (const tamper of [
    m => m.files.pop(),
    m => { m.files[1] = structuredClone(m.files[0]); },
    m => { m.files[0].event = 'unexpected'; },
    m => { m.files[0].original = 'wrong-original.mp3'; },
    m => { m.files[0].runtime = '/assets/audio/private.mp3'; },
    m => { m.files[0].sha256 = 'invalid'; },
    m => { m.files[0].bytes = -1; },
    m => { m.files[0].extra = true; },
  ]) {
    const changed = structuredClone(manifest); tamper(changed);
    assert.throws(() => validateSoundManifest(changed));
  }
});

for (const defect of ['missing', 'bytes', 'size', 'extra']) {
  test(`public runtime validation fails on ${defect} assets without requiring private originals`, async t => {
    const parent = resolve(tmpdir());
    const directory = await mkdtemp(join(parent, 'geo-public-audio-'));
    t.after(async () => {
      assert.ok(resolve(directory).startsWith(parent + sep));
      await rm(directory, { recursive: true });
    });
    const copied = pathToFileURL(directory + sep);
    for (const name of await readdir(runtime)) {
      if (defect === 'missing' && name === 'dice.mp3') continue;
      await copyFile(new URL(name, runtime), new URL(name, copied));
    }
    if (defect === 'bytes') {
      const file = new URL('dice.mp3', copied), bytes = await readFile(file);
      bytes[0] ^= 1; await writeFile(file, bytes);
    }
    if (defect === 'size') {
      const file = new URL('manifest.json', copied), value = JSON.parse(await readFile(file, 'utf8'));
      value.files[0].bytes++; await writeFile(file, JSON.stringify(value));
    }
    if (defect === 'extra') await writeFile(new URL('unexpected.mp3', copied), 'unexpected');
    await assert.rejects(verifyRuntimeSounds(copied));
    assert.equal((await verifyRuntimeSounds()).length, 18);
  });
}
