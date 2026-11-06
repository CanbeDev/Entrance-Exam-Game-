import { test } from 'node:test';
import assert from 'node:assert/strict';
import { GameApi } from '../src/api/index.ts';
import { id, csrf, json, login, token, credentials } from './helpers.mjs';

test('saved preference reads and explicit updates use authenticated exact routes with no generation requests', async () => {
  const calls = [];
  let version = 0, enabled = false;
  const api = new GameApi({ baseUrl: 'https://example.invalid/api', fetch: async (url, init) => {
    const path = new URL(url, 'https://example.invalid').pathname;
    const header = new Headers(init.headers);
    calls.push({ path, method: init.method ?? 'GET', body: init.body, csrf: header.get('X-CSRF-Token') });
    if (path.endsWith('/auth/login')) return login();
    if (path.endsWith('/auth/csrf')) return token();
    assert.equal(path, `/api/games/${id}/commentary-preference`);
    if (init.method === 'POST') {
      const request = JSON.parse(init.body);
      assert.deepEqual(request, { enabled: true, expected_version: version });
      assert.equal(header.get('X-CSRF-Token'), csrf);
      enabled = request.enabled; version++;
    }
    return json({ game_id: id, mode: 'worker', enabled, version, activation_revision: enabled ? 10 : null });
  } });
  await api.login(credentials);
  assert.equal((await api.commentaryPreference(id)).enabled, false);
  assert.equal((await api.setCommentaryPreference(id, true, 0)).version, 1);
  assert.equal((await api.commentaryPreference(id)).enabled, true);
  assert.equal(calls.filter(call => call.method === 'POST' && !call.path.endsWith('/auth/login')).length, 1);
  assert.ok(calls.every(call => !/commentary\/\d/.test(call.path)));
});
