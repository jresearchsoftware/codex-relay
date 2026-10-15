import test from 'node:test';
import assert from 'node:assert/strict';
import { main } from '../src/entrypoint.mjs';
import { CONSUMER } from '../../consumer/consumer.mjs';
import { OWNER, REPOSITORY } from '../src/execution-contract.mjs';
import { fixture } from './fixture.mjs';

test('routing holds a real late termination signal through the terminal Writer receipt', async t => {
  const f = await fixture(t); let executed = 0; let completed = 0; let signal;
  const before = ['SIGINT', 'SIGTERM'].map(name => process.listenerCount(name));
  const result = await main({
    env: { GITHUB_EVENT_PATH: '/fixture/event', GITHUB_EVENT_NAME: 'workflow_dispatch',
      GITHUB_REF: `refs/heads/${CONSUMER.baseBranch}`, GITHUB_RUN_ID: String(f.envelope.runId) },
    readEvent: async () => JSON.stringify({ repository: { full_name: REPOSITORY }, sender: { login: OWNER },
      inputs: { task: String(f.envelope.issueNumber), step: String(f.envelope.step), route: 'auto' } }),
    resolveSlot: () => undefined, createJournal: () => f.journal,
    createWriter: () => ({ invoke: async request => {
      if (request.operation === 'admit') return { envelope: f.envelope };
      if (request.operation === 'complete-execution') {
        assert.equal((await f.journal.get(f.envelope.runId)).outcome.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
        process.kill(process.pid, 'SIGTERM');
        await new Promise(resolve => setImmediate(resolve));
        assert.equal(signal.aborted, true); completed++;
        return { status: 'COMPLETED' };
      }
      return f.broker.invoke(request);
    } }),
    createDispatcher: (options = {}) => { signal = options.signal; return { dispatch: async () => {
      executed++; await f.commit();
      return { version: 2, attemptId: f.envelope.attemptId, child: 'started', containment: 'reaped',
        result: { status: 'success', summary: 'done', validation: [] } };
    } }; },
    prepare: f.prepare, collect: f.collect, persistFailure: f.persistFailure
  });
  assert.equal(result.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
  assert.equal(executed, 1); assert.equal(completed, 1); assert.equal(f.pushes(), 1);
  assert.deepEqual(['SIGINT', 'SIGTERM'].map(name => process.listenerCount(name)), before);
});
