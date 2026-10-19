import test from 'node:test';
import assert from 'node:assert/strict';
import { harness } from './independent-admission-fixture.mjs';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { promisify } from 'node:util';
import { execFile } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { CONSUMER } from '../../consumer/consumer.mjs';
import { EXECUTION_PATH_NAMES } from '../../consumer/consumer-config.mjs';
import { REPOSITORY, REVIEWER } from '../src/execution-contract.mjs';
import { canonicalAuthorityJson, sha256Body } from '../../contracts/src/github-authority.mjs';
import { revalidateAuthority } from '../src/live-authority.mjs';

const copy = value => structuredClone(value);

test('Task 85 pattern: withdraw a Step 2 manual handoff, then admit isolated Step 3 without inventing cancellation', async t => {
  const f = await harness(t, { tasks: [85] });
  await f.broker.dispatch(f.ready(98, 85, 'manual'));
  const step2 = await f.broker.dispatch(f.ready(99, 85, 'manual'));
  await f.broker.dispatch({ operation: 'handoff', runId: 99, attemptId: 'run-99' });
  const original = copy(await f.store.get(99));
  const handoff = f.comments[0].body;
  const decision = { schema_version: '4.0', kind: 'decision', repository: REPOSITORY, task: 85,
    parent: { kind: 'issue', number: 85 }, charter_sha256: sha256Body(f.issues.get(85).body),
    purpose: 'Withdraw the old manual handoff and authorize a fresh independent source attempt.',
    amendments: { purpose: 'Continue independent source work after withdrawal',
      boundaries: ['Do not execute withdrawn run-99; only newly admitted independent work is authorized.'],
      scope: ['The prior manual handoff is withdrawn; only the new isolated attempt may perform this source work.'] },
    supersedes: null, context: [] };
  f.comments.push({ id: 6000, number: 85, user: { login: REVIEWER, id: 701, type: 'Bot' },
    issue_url: `https://api.github.com/repos/${REPOSITORY}/issues/85`,
    body: '```relay-authority\n' + canonicalAuthorityJson(decision) + '\n```\n' });
  const step3 = await f.broker.dispatch(f.ready(100, 85, 'manual'));
  assert.equal(step2.envelope.step, 2); assert.equal(step3.envelope.step, 3);
  assert.equal(step3.envelope.request.lineage.attempt, 'run-99');
  assert.equal(step3.envelope.request.authority.decisions[0].id, 6000);
  await assert.rejects(revalidateAuthority(f.api, step2.envelope), { code: 'AUTHORITY_CHANGED' });
  await revalidateAuthority(f.api, step2.envelope, { reporting: true });
  assert.deepEqual(await f.store.get(99), original);
  assert.equal(original.outcome, null);
  assert.equal(f.comments[0].body, handoff);
  assert.deepEqual(f.issues.get(85).labels, [{ name: 'step-3' }]);
});

for (const routes of [['manual', 'manual'], ['auto', 'manual'], ['manual', 'auto']]) {
  test(`same Task admits ${routes.join('/')} independent commands while prior work has no Outcome`, async t => {
    const f = await harness(t);
    const firstRequest = f.ready(99, 42, routes[0]);
    const first = await f.broker.dispatch(firstRequest);
    if (routes[0] === 'manual') {
      await f.broker.dispatch({ operation: 'handoff', runId: 99, attemptId: 'run-99' });
      assert.match(f.comments[0].body, /independent checkout\/worktree and execution resources for run-99/);
    }
    const original = copy(await f.store.get(99));
    const secondRequest = f.ready(100, 42, routes[1]);
    const second = await f.broker.dispatch(secondRequest);
    assert.equal(first.envelope.step, 1); assert.equal(second.envelope.step, 2);
    assert.equal(second.envelope.request.lineage.attempt, 'run-99');
    assert.equal(original.outcome, null);
    assert.equal(f.runs.get(99).status, 'in_progress');
    assert.deepEqual((await f.store.get(99)).envelope, original.envelope);
    for (const [request, result] of [[firstRequest, first], [secondRequest, second]])
      assert.deepEqual((await f.broker.dispatch(request)).envelope, result.envelope);
    assert.deepEqual(f.issues.get(42).labels, [{ name: 'step-2' }]);
    assert.equal(f.deletes(), 2);
    for (const runId of [99, 100]) {
      const record = await f.store.get(runId);
      assert.equal(Boolean(record.controllerLifecycle), record.envelope.route === 'auto');
    }
  });
}

test('independent Tasks keep their admission, projection and manual resources separate during overlap', async t => {
  const f = await harness(t);
  const firstRequest = f.ready(99, 42, 'auto');
  const first = await f.broker.dispatch(firstRequest);
  const secondRequest = f.ready(100, 44, 'manual');
  const second = await f.broker.dispatch(secondRequest);
  assert.equal(first.envelope.step, 1); assert.equal(second.envelope.step, 1);
  assert.notEqual(first.envelope.branch, second.envelope.branch);
  assert.equal((await f.store.get(99)).outcome, null);
  assert.equal((await f.store.get(100)).controllerLifecycle, undefined);
  await f.broker.dispatch(firstRequest); await f.broker.dispatch(secondRequest);
  for (const issue of f.issues.values()) assert.deepEqual(issue.labels, [{ name: 'step-1' }]);
});

test('duplicate delivery of the reserved native command cannot allocate a sibling Step or another DELETE', async t => {
  const f = await harness(t);
  const request = f.ready(99, 42, 'manual');
  await f.broker.dispatch(request);
  const original = await f.store.get(99);
  // The same delivered event is explicitly exposed as current again; it still
  // cannot bypass the durable native event reservation under another run ID.
  f.events.set(42, [f.events.get(42)[0]]);
  f.issues.get(42).labels.push({ name: 'codex-ready-manual' });
  f.runs.set(100, { ...copy(f.runs.get(99)), id: 100 });
  await assert.rejects(f.broker.dispatch({ ...request, runId: 100 }), { code: 'READY_EVENT_ALREADY_CONSUMED' });
  assert.equal(await f.store.get(100), null);
  assert.deepEqual(await f.store.get(99), original);
  assert.equal(f.deletes(), 1);
});

test('prelaunch ready race releases only its unused automatic resource and reports the original attempt once', async t => {
  const f = await harness(t);
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
  const outcomeBytes = f.comments[0].body;
  await f.control.assertSlotComplete('primary');
  await assert.rejects(f.broker.dispatch(request), { code: 'READY_CONSUMPTION_UNCERTAIN' });
  assert.equal(f.deletes(), 1); assert.equal(f.comments.length, 1);
  assert.equal(f.comments[0].body, outcomeBytes);
  const next = await f.broker.dispatch(f.ready(100, 42, 'auto'));
  assert.equal(next.envelope.step, 2);
  assert.deepEqual((await f.store.get(99)).outcome, original.outcome);
  assert.deepEqual((await f.store.get(99)).envelope, original.envelope);
});

test('two automatic same-UID attempts overlap on distinct slots for the same Task and independent Tasks', async t => {
  const root = await mkdtemp(join(tmpdir(), 'relay-two-auto-admission-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const config = copyConsumerPool(); const pathname = join(root, 'consumer.json');
  await writeFile(pathname, JSON.stringify(config), { mode: 0o600 });
  const source = `
    import assert from 'node:assert/strict';
    import {harness} from './controller/test/independent-admission-fixture.mjs';
    import {CONSUMER} from './consumer/consumer.mjs';
    assert.equal(CONSUMER.executionSlots[0].runtimeUser,CONSUMER.executionSlots[1].runtimeUser);
    for(const secondTask of [42,44]) {
      const cleanups=[];const f=await harness({after:cleanup=>cleanups.push(cleanup)});
      try {
        const a={...f.ready(99,42,'auto'),executionSlot:'primary'};
        const first=await f.broker.dispatch(a);
        const b={...f.ready(100,secondTask,'auto'),executionSlot:'second'};
        const second=await f.broker.dispatch(b);
        assert.equal(first.envelope.step,1);assert.equal(second.envelope.step,secondTask===42?2:1);
        assert.notEqual(first.envelope.attemptId,second.envelope.attemptId);
        assert.equal((await f.store.get(99)).controllerLifecycle.status,'active');
        assert.equal((await f.store.get(100)).controllerLifecycle.status,'active');
        assert.equal((await f.store.get(99)).outcome,null);assert.equal((await f.store.get(100)).outcome,null);
        assert.deepEqual((await f.control.status()).active,[99,100]);
        assert.deepEqual((await f.broker.dispatch(a)).envelope,first.envelope);
        assert.deepEqual((await f.broker.dispatch(b)).envelope,second.envelope);
        assert.deepEqual(f.issues.get(secondTask).labels,[{name:'step-'+(secondTask===42?2:1)}]);
        const blocked={...f.ready(101,44,'auto'),executionSlot:'primary'};
        await assert.rejects(f.broker.dispatch(blocked),e=>e.code==='EXECUTION_SLOT_UNAVAILABLE'&&e.details.active.includes(99));
        assert.equal(await f.store.get(101),null);
        assert.equal(f.deletes(),2);
      } finally {for(const cleanup of cleanups) await cleanup();}
    }
  `;
  await promisify(execFile)(process.execPath, ['--input-type=module', '-e', source], {
    cwd: fileURLToPath(new URL('../../', import.meta.url)),
    env: { ...process.env, RELAY_CONSUMER_CONFIG: pathname, RELAY_EXECUTION_SLOT: 'primary' }
  });
});

function copyConsumerPool() {
  const config = structuredClone(CONSUMER);
  config.generalRunnerPool = { desiredCapacity: 2 };
  const identity = { runnerUser: 'relay-runner', runtimeUser: config.runtimeUser, workGroup: 'relay-work' };
  config.executionSlots = [
    { id: 'primary', runnerName: 'fixture-primary', ...identity,
      paths: Object.fromEntries(EXECUTION_PATH_NAMES.map(name => [name, config.paths[name]])) },
    { id: 'second', runnerName: 'fixture-second', ...identity,
      paths: Object.fromEntries(EXECUTION_PATH_NAMES.map(name => [name, `/var/lib/relay-fixture-second/${name}`])) }
  ];
  return config;
}
