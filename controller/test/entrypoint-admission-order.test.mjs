import test from 'node:test';
import assert from 'node:assert/strict';
import { CONSUMER, EXECUTION_SLOT } from '../../consumer/consumer.mjs';
import { OWNER, REPOSITORY, VERSION } from '../src/execution-contract.mjs';
import { main } from '../src/entrypoint.mjs';
import { currentEnvelope, memoryStore } from './fixture.mjs';

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

function unstartedReplayOptions(admissionUnstarted) {
  const envelope = currentEnvelope({ runId: 99 });
  const journal = memoryStore();
  const calls = [];
  let dispatches = 0;
  const outcome = { status: 'IMPLEMENTED_PENDING_FRESH_REVIEW', head: envelope.startHead, prNumber: 43, outcomeId: 57 };
  return { envelope, journal, calls, dispatches: () => dispatches, outcome,
    options: options({
      createWriter: () => ({ invoke: async request => {
        calls.push(request.operation);
        if (request.operation === 'admit') return { envelope, resumed: true, admissionUnstarted };
        if (request.operation === 'preflight') return {};
        if (request.operation === 'finish-no-change') return outcome;
        if (request.operation === 'complete-handoff') return { status: 'READY' };
        if (request.operation === 'complete-execution') return { complete: true };
        assert.fail(`unexpected Writer operation ${request.operation}`);
      } }),
      createDispatcher: () => ({ dispatch: async e => {
        dispatches++;
        return { version: VERSION, attemptId: e.attemptId, child: 'not_started', containment: 'not_required',
          result: { status: 'success', summary: 'No source changes were needed.', validation: [] } };
      } }),
      createJournal: () => journal,
      prepare: async () => {},
      collect: async e => ({ head: e.startHead, clean: true }),
      persistFailure: async () => ({})
    }) };
}

test('the exact unstarted automatic replay receipt permits its first journal and worker reservation', async () => {
  const f = unstartedReplayOptions(true);
  assert.deepEqual(await main(f.options), { status: 'READY' });
  assert.equal(f.dispatches(), 1);
  assert.deepEqual(f.calls, ['admit', 'preflight', 'finish-no-change', 'complete-handoff', 'complete-execution']);
  assert.equal((await f.journal.get(99)).execution.returned, true);
});

test('a resumed automatic attempt without the unstarted replay receipt still requires its journal', async () => {
  const f = unstartedReplayOptions(false);
  await assert.rejects(main(f.options), { code: 'JOURNAL_MISSING_EXECUTION_UNKNOWN' });
  assert.equal(f.dispatches(), 0);
  assert.equal(await f.journal.get(99), null);
  assert.deepEqual(f.calls, ['admit', 'complete-execution']);
});

test('the unstarted replay receipt cannot override a journal that appeared before worker reservation', async () => {
  const f = unstartedReplayOptions(true);
  await f.journal.put(99, { version: VERSION, envelope: f.envelope, execution: null });
  await assert.rejects(main(f.options), { code: 'JOURNAL_MISSING_EXECUTION_UNKNOWN' });
  assert.equal(f.dispatches(), 0);
  assert.deepEqual(f.calls, ['admit', 'complete-execution']);
});
