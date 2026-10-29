import assert from 'node:assert/strict';

export const id = '0123456789abcdef01234567';
export const user = { id: 'user-offline', username: 'offline_user' };
export const csrf = 'x'.repeat(43);
export const credentials = { username: user.username, password: 'Offline fixture password 12345' };
export const json = (body, status = 200, headers = {}) => new Response(JSON.stringify(body), {
  status, headers: { 'Content-Type': 'application/json', ...headers },
});
export const failure = (status, code, headers) => json({ detail: { code } }, status, headers);
export const login = () => json({ user, expires_at: '2027-01-01T12:00:00Z' });
export const token = () => json({ csrf_token: csrf });
export const game = (revision = 0) => ({
  _id: id, game_name: 'Offline game', status: 'active', schema_version: 3,
  revision, round: 1, current_turn: 0, turn_sequence: 1, phase: 'deciding',
  countries: [], players: [], turn_order: [], pending_reinforcements: 0, attack_used: false,
});
export const result = (revision = 1) => {
  const state = game(revision);
  delete state._id; // Actual action results can omit route identity.
  return { state, events: [], npc_decision: null };
};
export function queue(...steps) {
  const calls = [];
  const fetch = async (url, init) => {
    calls.push({ url, ...init });
    assert.ok(steps.length, `Unexpected offline request: ${url}`);
    const step = steps.shift();
    return typeof step === 'function' ? step(url, init) : step;
  };
  return { fetch, calls, done: () => assert.equal(steps.length, 0, 'Unused mock responses') };
}
export const body = (call) => call.body === undefined ? undefined : JSON.parse(call.body);
