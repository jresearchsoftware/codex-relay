import { main } from '../src/entrypoint.mjs';
import { CONSUMER } from '../../consumer/consumer.mjs';
import { VERSION, OWNER } from '../src/execution-contract.mjs';
import { completedPredispatchRecovery } from '../src/predispatch-recovery.mjs';
import assert from 'node:assert/strict';
import { harness } from './independent-admission-fixture.mjs';
import { REPOSITORY, WRITER } from '../src/execution-contract.mjs';
const copy = value => structuredClone(value);

export async function replacedReadyOutcome(t, options) {
  const f = await harness(t, options);
  const request = f.ready(99, 42, 'auto');
  const remove = f.api.delete;
  let replace = true;
  f.api.delete = async path => {
    if (replace && path.endsWith('/labels/codex-ready-auto')) {
      replace = false; f.replaceReady(42, 'auto');
    }
    return remove(path);
  };
  await assert.rejects(f.broker.dispatch(request), { code: 'READY_EVENT_REPLACED' });
  const original = await f.store.get(99);
  assert.deepEqual(original.controllerLifecycle, { version: 1, status: 'complete', child: 'not_started', containment: 'not_required' });
  assert.equal(original.outcome.status, 'BLOCKED');
  assert.equal(original.readyConsumed, undefined);
  assert.equal(original.readyConsumption.code, 'READY_EVENT_REPLACED');
  assert.equal(f.comments.length, 1);
  assert.match(f.comments[0].body, /Automatic worker launch authority was not returned/);
  f.runs.get(99).status = 'completed';
  f.runs.get(99).conclusion = 'failure';
  f.runs.get(99).updated_at = '2026-09-04T12:00:05.500Z';
  Object.assign(f.comments[0], {
    user: { login: WRITER, id: 701, type: 'Bot' },
    issue_url: 'https://api.github.com/repos/' + REPOSITORY + '/issues/42',
    created_at: '2026-09-04T12:00:05.000Z',
    updated_at: '2026-09-04T12:00:05.000Z'
  });
  const get = f.api.get.bind(f.api);
  f.api.get = async path => path.startsWith('/issues/comments/')
    ? copy(f.comments.find(comment => comment.id === Number(path.split('/').at(-1)))) : get(path);
  f.originalRequest = request;
  f.original = copy(original);
  f.outcomeBytes = f.comments[0].body;
  return f;
}

export async function interruptedAutomaticSuccessor(t, options) {
  const f = await replacedReadyOutcome(t, options);
  const nextRequest = f.ready(100, 42, 'auto');
  const put = f.store.put.bind(f.store);
  let interrupt = true;
  f.store.put = async (id, record) => {
    await put(id, record);
    if (interrupt && id === 100) {
      interrupt = false;
      throw new Error('synthetic interruption after durable automatic admission');
    }
  };
  await assert.rejects(f.broker.dispatch(nextRequest), /synthetic interruption/);
  assert.ok(await f.store.get(100));
  assert.equal(f.deletes(), 1);
  f.runs.get(100).status = 'completed';
  f.runs.get(100).conclusion = 'failure';
  f.runs.get(100).updated_at = '2026-09-04T12:00:07Z';
  f.runs.get(100).run_attempt = 2;
  f.runs.get(100).status = 'in_progress';
  f.runs.get(100).conclusion = null;
  f.runs.get(100).updated_at = '2026-09-04T12:00:08Z';
  return { f, nextRequest };
}

export async function exerciseAutomaticRerun(t, options = {}) {
  const { f, nextRequest } = await interruptedAutomaticSuccessor(t, options);
  const admitted = copy((await f.store.get(100)).envelope);
  const eventCount = f.events.get(42).length;
  let workers = 0;
  const routing = {
    env: { GITHUB_EVENT_PATH: 'synthetic.json', GITHUB_EVENT_NAME: 'issues',
      GITHUB_REF: `refs/heads/${CONSUMER.baseBranch}`, GITHUB_RUN_ID: '100', GITHUB_RUN_ATTEMPT: '2' },
    readEvent: async () => JSON.stringify({ repository: { full_name: REPOSITORY }, sender: { login: OWNER },
      action: 'labeled', label: { name: 'codex-ready-auto' }, issue: { number: 42 } }),
    resolveSlot: () => options.executionSlot,
    // The fixed privileged helper handles completion directly through its
    // admission capability after checking the caller's immutable slot.
    createWriter: () => ({ invoke: async ({ workflowReadToken, ...request }) => request.operation === 'complete-execution'
      ? { version: VERSION, repository: REPOSITORY, ...await f.control.complete(request) }
      : f.broker.dispatch(request) }),
    createJournal: () => f.journal,
    createDispatcher: () => ({ dispatch: async e => {
      workers++;
      return { version: VERSION, attemptId: e.attemptId, child: 'started', containment: 'reaped',
        result: { status: 'success', summary: 'Synthetic contained worker completed.', validation: [] } };
    } }),
    prepare: async () => {}, collect: async e => ({ head: e.startHead, clean: true }),
    persistFailure: async () => ({})
  };
  if (options.interruptAfterReceipt) {
    const put = f.store.put.bind(f.store);
    let interrupt = true;
    f.store.put = async (id, record) => {
      await put(id, record);
      if (interrupt && id === 99 && completedPredispatchRecovery(record)) {
        interrupt = false;
        throw new Error('synthetic interruption after durable predecessor retirement');
      }
    };
    await assert.rejects(main(routing), /synthetic interruption/);
    assert.equal(workers, 0);
    assert.equal(f.deletes(), 1);
    assert.ok(completedPredispatchRecovery(await f.store.get(99)));
    f.runs.get(100).status = 'completed';
    f.runs.get(100).conclusion = 'failure';
    f.runs.get(100).run_attempt = 3;
    f.runs.get(100).status = 'in_progress';
    f.runs.get(100).conclusion = null;
    routing.env.GITHUB_RUN_ATTEMPT = '3';
  }
  await main(routing);
  assert.equal(workers, 1);
  assert.deepEqual((await f.store.get(100)).envelope, admitted);
  assert.equal(f.events.get(42).length, eventCount + 1); // only the first successor DELETE
  assert.equal(f.deletes(), 2); // one original DELETE and one successor DELETE
  assert.equal(f.comments.length, 2); // original sealed Outcome plus successor's own Outcome
  assert.equal(f.comments[0].body, f.outcomeBytes);
  assert.ok(completedPredispatchRecovery(await f.store.get(99)));
  await f.broker.dispatch(nextRequest); // terminal journal replay, never a new worker
  f.runs.get(100).run_attempt = 3;
  await main(routing);
  assert.equal(workers, 1); assert.equal(f.deletes(), 2); assert.equal(f.comments.length, 2);
  const status = await f.control.status();
  assert.deepEqual(status.active, []); assert.deepEqual(status.unknown, []);
  if (options.quiesce === false) return { f, workers };
  const operationId = '12345678-1234-1234-1234-123456789abc';
  const target = 'b'.repeat(40);
  await f.control.quiesce({ operationId, target });
  assert.equal((await f.control.drained({ operationId })).drained, true);
  await f.control.checkConsumerTransition({ operationId, target });
  return { f, workers };
}
