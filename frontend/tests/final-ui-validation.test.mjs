import { test } from 'node:test';
import assert from 'node:assert/strict';
import { accountErrors } from '../src/components/auth-validation.ts';

test('inline account validation blocks missing/invalid credentials and preserves legacy login passwords', () => {
  assert.ok(accountErrors('', '', false).username);
  assert.ok(accountErrors('ab', 'x', false).username);
  assert.ok(accountErrors('bad name', 'x', false).username);
  assert.equal(accountErrors('existing_user', 'x', false).password, '');
  assert.ok(accountErrors('new_user', 'short', true).password);
  assert.equal(accountErrors('new_user', 'long secure password', true).password, '');
  assert.ok(accountErrors('new_user', 'x'.repeat(129), true).password);
  assert.ok(accountErrors('new_user', 'valid length but\0invalid', true).password);
});
