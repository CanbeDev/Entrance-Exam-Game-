import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile, readdir } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { soundAssets, soundUrl } from '../../src/sound/assets.ts';
import { verifyRuntimeSounds } from '../../scripts/verify-sound-assets.mjs';

const sources = new URL('../../public/assets/audio/', import.meta.url);
const alternate = 'Error_Gentle_two-ton_#4-1793669030910.mp3';
test('PRIVATE sources: all 19 originals exist; all 18 runtime copies equal original bytes', async () => {
  const rows = await verifyRuntimeSounds();
  assert.deepEqual((await readdir(sources)).sort(), [...Object.values(soundAssets), alternate].sort(),
    'Private source prerequisite: supply the exact original inventory; do not skip this profile');
  for (const row of rows) {
    const original = await readFile(new URL(encodeURIComponent(soundAssets[row.event]), sources));
    const runtime = await readFile(new URL('../../public' + soundUrl(row.event), import.meta.url));
    assert.deepEqual(runtime, original);
  }
  const unused = await readFile(new URL(encodeURIComponent(alternate), sources));
  assert.equal(createHash('sha256').update(unused).digest('hex'),
    '24524ee14c330a6b20eb11b4efb3fbf1b239e62928e692bf684b9439b8554d85');
});
