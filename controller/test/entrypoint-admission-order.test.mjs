import test from 'node:test';
import assert from 'node:assert/strict';
import { CONSUMER, EXECUTION_SLOT } from '../../consumer/consumer.mjs';
import { OWNER, REPOSITORY } from '../src/execution-contract.mjs';
import { main } from '../src/entrypoint.mjs';

const event = { repository: { full_name: REPOSITORY }, sender: { login: OWNER },
  inputs: { route: 'auto', task: '42' } };
const env = { GITHUB_EVENT_PATH: 'synthetic-event.json', GITHUB_EVENT_NAME: 'workflow_dispatch',
  GITHUB_REF: `refs/heads/${CONSUMER.baseBranch}`, GITHUB_RUN_ID: '99', GITHUB_TOKEN: 'synthetic-test-token' };

function options(overrides = {}) {
  let admissions = 0;
  return {
    env, readEvent: async () => JSON.stringify(event), resolveSlot: () => CONSUMER.executionSlots ? EXECUTION_SLOT : undefined,
    createWriter: () => ({ invoke: async () => { admissions++; return { status: 'BLOCKED', envelope: {} }; } }),
    admissions: () => admissions, ...overrides
  };
}

test('dispatcher construction failure precedes automatic admission', async () => {
  const f = options({ createDispatcher: () => { throw new Error('synthetic dispatcher setup failure'); } });
  await assert.rejects(main(f), /synthetic dispatcher setup failure/);
  assert.equal(f.admissions(), 0);
});

test('journal construction failure precedes automatic admission', async () => {
  const f = options({ createDispatcher: () => ({ dispatch: async () => assert.fail('worker must not start') }),
    createJournal: () => { throw new Error('synthetic journal setup failure'); } });
  await assert.rejects(main(f), /synthetic journal setup failure/);
  assert.equal(f.admissions(), 0);
});
