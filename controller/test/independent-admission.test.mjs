import { replacedReadyOutcome, interruptedAutomaticSuccessor, exerciseAutomaticRerun } from './independent-admission-scenario.mjs';
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
import { REPOSITORY, REVIEWER, WRITER } from '../src/execution-contract.mjs';
import { canonicalAuthorityJson, sha256Body } from '../../contracts/src/github-authority.mjs';
import { revalidateAuthority } from '../src/live-authority.mjs';
import { completedPredispatchRecovery } from '../src/predispatch-recovery.mjs';

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
    for (const [request, result] of [[firstRequest, first], [secondRequest, second]]) {
      if (request.route === 'auto') await assert.rejects(f.broker.dispatch(request), { code: 'PREDISPATCH_ATTEMPT_FINALIZED' });
      else assert.deepEqual((await f.broker.dispatch(request)).envelope, result.envelope);
    }
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
  await assert.rejects(f.broker.dispatch(firstRequest), { code: 'PREDISPATCH_ATTEMPT_FINALIZED' });
  await f.broker.dispatch(secondRequest);
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


test('prelaunch replacement Outcome is sealed and a later admitted Step retires it for drain and Apply', async t => {
  const f = await replacedReadyOutcome(t);
  await f.control.assertSlotComplete('primary');
  await assert.rejects(f.broker.dispatch(f.originalRequest), { code: 'READY_CONSUMPTION_UNCERTAIN' });
  assert.equal(f.deletes(), 1); assert.equal(f.comments.length, 1);
  assert.equal(f.comments[0].body, f.outcomeBytes);
  const nextRequest = f.ready(100, 42, 'manual');
  const damaged = copy(f.original);
  damaged.commentBodies.outcome.sha256 = 'f'.repeat(64);
  await f.store.put(99, damaged);
  await assert.rejects(f.broker.dispatch(nextRequest), { code: 'PREDISPATCH_EXECUTION_EVIDENCE_CONFLICT' });
  assert.equal(await f.store.get(100), null);
  await f.store.put(99, f.original);
  const next = await f.broker.dispatch(nextRequest);
  assert.equal(next.envelope.step, 2);
  const saved = await f.store.get(99), { predispatchRecovery, ...retired } = saved;
  assert.deepEqual(retired, f.original);
  assert.equal(predispatchRecovery.version, 4);
  assert.equal(predispatchRecovery.authorizationKind, 'owner-ready-event');
  assert.equal(predispatchRecovery.binding.replacementAttemptId, 'run-100');
  assert.ok(completedPredispatchRecovery(saved));
  for (const [field, value] of [['replacementReadyEventId', 71],
    ['outcomeCommentId', 0], ['replacementEnvelopeDigest', 'malformed']]) {
    const corrupt = copy(saved);
    corrupt.predispatchRecovery.binding[field] = value;
    assert.equal(completedPredispatchRecovery(corrupt), false);
    await f.store.put(99, corrupt);
    assert.deepEqual((await f.control.status()).unknown, [99]);
    await f.store.put(99, saved);
  }
  assert.equal(f.deletes(), 2); assert.equal(f.comments.length, 1);
  assert.equal(f.comments[0].body, f.outcomeBytes);
  await f.control.assertTaskComplete(42);
  const operationId = '12345678-1234-1234-1234-123456789abc';
  const target = 'b'.repeat(40);
  await f.control.quiesce({ operationId, target });
  const drained = await f.control.drained({ operationId });
  assert.equal(drained.drained, true);
  assert.deepEqual(drained.unknown, []);
  await f.control.checkConsumerTransition({ operationId, target });
});

test('a later automatic Step retires the prior replacement while retaining its own active lifecycle', async t => {
  const f = await replacedReadyOutcome(t);
  const next = await f.broker.dispatch(f.ready(100, 42, 'auto'));
  assert.equal(next.envelope.step, 2);
  assert.ok(completedPredispatchRecovery(await f.store.get(99)));
  const status = await f.control.status();
  assert.deepEqual(status.active, [100]);
  assert.deepEqual(status.unknown, []);
  const operationId = '12345678-1234-1234-1234-123456789abc';
  const target = 'c'.repeat(40);
  await f.control.quiesce({ operationId, target });
  const drained = await f.control.drained({ operationId });
  assert.equal(drained.drained, false);
  assert.deepEqual(drained.active, [100]);
  assert.deepEqual(drained.unknown, []);
});

test('replacement retirement resumes after an interrupted durable admission without a new owner event or extra launch', async t => {
  const f = await replacedReadyOutcome(t);
  const nextRequest = f.ready(100, 42, 'manual');
  const put = f.store.put.bind(f.store);
  let interrupt = true;
  f.store.put = async (id, record) => {
    await put(id, record);
    if (interrupt && id === 100) {
      interrupt = false;
      throw new Error('synthetic interruption after durable admission');
    }
  };
  await assert.rejects(f.broker.dispatch(nextRequest), /synthetic interruption/);
  assert.ok(await f.store.get(100));
  assert.equal((await f.store.get(99)).predispatchRecovery, undefined);
  assert.equal(f.deletes(), 1);

  // Actions reruns preserve run_id but increment run_attempt. The owner event
  // and durable admission, rather than a second owner command, bind recovery.
  f.runs.get(100).run_attempt = 2;
  f.runs.get(100).status = 'in_progress';
  f.runs.get(100).conclusion = null;
  f.runs.get(100).updated_at = '2026-09-04T12:00:08Z';
  const resumed = await f.broker.dispatch(nextRequest);
  assert.equal(resumed.envelope.step, 2);
  assert.ok(completedPredispatchRecovery(await f.store.get(99)));
  assert.equal(f.deletes(), 2);
  assert.equal(f.comments.length, 1);
});


test('same-run automatic replay rechecks admission and starts only its first journal reservation', async t => {
  const { f, nextRequest } = await interruptedAutomaticSuccessor(t);
  const resumed = await f.broker.dispatch(nextRequest);
  assert.equal(resumed.resumed, true);
  assert.equal(resumed.admissionUnstarted, true);
  assert.equal(resumed.envelope.step, 2);
  assert.ok(completedPredispatchRecovery(await f.store.get(99)));
  assert.equal(f.deletes(), 2);
  assert.equal(f.comments.length, 1);
});

test('Actions attempt 2 recovers through the routing entrypoint, completes once, and drains both records', async t => {
  await exerciseAutomaticRerun(t);
});

test('Actions attempt 3 recovers a durable predecessor receipt before successor consumption without another worker', async t => {
  await exerciseAutomaticRerun(t, { interruptAfterReceipt: true });
});

test('a fresh Actions rerun without a durable native admission cannot launch', async t => {
  const f = await harness(t);
  const request = f.ready(100, 42, 'auto');
  f.runs.get(100).run_attempt = 2;
  await assert.rejects(f.broker.dispatch(request), { code: 'OWNER_RUN_NOT_ADMITTED' });
  assert.equal(await f.store.get(100), null);
  assert.equal(f.deletes(), 0);
});

test('a corrupt retired predecessor receipt cannot authorize successor replay', async t => {
  const { f, nextRequest } = await interruptedAutomaticSuccessor(t);
  const put = f.store.put.bind(f.store);
  let interrupt = true;
  f.store.put = async (id, record) => {
    await put(id, record);
    if (interrupt && id === 99 && completedPredispatchRecovery(record)) {
      interrupt = false;
      throw new Error('synthetic interruption after durable receipt');
    }
  };
  await assert.rejects(f.broker.dispatch(nextRequest), /synthetic interruption/);
  const retired = await f.store.get(99);
  retired.predispatchRecovery.binding.replacementEnvelopeDigest = '0'.repeat(64);
  await put(99, retired);
  f.runs.get(100).run_attempt = 3;
  await assert.rejects(f.broker.dispatch(nextRequest), { code: 'PREDISPATCH_ATTEMPT_FINALIZED' });
  assert.equal(await f.journal.get(100), null);
  assert.equal(f.deletes(), 1);
});

for (const [name, mutate, code] of [
  ['invalid attempt', f => { f.runs.get(100).run_attempt = 0; }, 'PREDISPATCH_REPLACEMENT_RUN_AMBIGUOUS'],
  ['foreign rerun actor', f => { f.runs.get(100).triggering_actor = { login: 'foreign' }; }, 'PREDISPATCH_REPLACEMENT_RUN_AMBIGUOUS'],
  ['wrong run', f => { f.runs.get(100).id = 101; }, 'PREDISPATCH_REPLACEMENT_RUN_AMBIGUOUS'],
  ['wrong workflow', f => { f.runs.get(100).path = '.github/workflows/foreign.yml'; }, 'PREDISPATCH_REPLACEMENT_RUN_AMBIGUOUS'],
  ['journal', async f => { await f.journal.put(100, { execution: null }); }, 'PREDISPATCH_EXECUTION_EVIDENCE_CONFLICT'],
  ['checkout', f => f.setCheckoutExists(true), 'PREDISPATCH_EXECUTION_EVIDENCE_CONFLICT'],
  ['publication effect', async f => { const r = await f.store.get(100); r.publicationIntent = { head: 'b'.repeat(40) }; await f.store.put(100, r); }, 'PREDISPATCH_EXECUTION_EVIDENCE_CONFLICT'],
  ['changed owner event', f => { f.events.get(42).at(-1).actor.login = 'foreign'; }, 'READY_EVENT_STALE']
]) {
  test('Actions rerun refuses unsafe successor continuation before any native mutation: ' + name, async t => {
    const { f, nextRequest } = await interruptedAutomaticSuccessor(t);
    await mutate(f);
    const old = copy(await f.store.get(99)), next = copy(await f.store.get(100));
    await assert.rejects(f.broker.dispatch(nextRequest), { code });
    assert.deepEqual(await f.store.get(99), old); assert.deepEqual(await f.store.get(100), next);
    assert.equal(f.deletes(), 1); assert.equal(f.comments.length, 1);
  });
}

test('same-run automatic replay leaves its owner command untouched when admission or the slot is unavailable', async t => {
  {
    const { f, nextRequest } = await interruptedAutomaticSuccessor(t);
    await f.control.quiesce({ operationId: '12345678-1234-1234-1234-123456789abc', target: 'b'.repeat(40) });
    await assert.rejects(f.broker.dispatch(nextRequest), { code: 'ADMISSION_QUIESCED' });
    assert.equal(f.deletes(), 1);
    assert.ok(f.issues.get(42).labels.some(label => label.name === 'codex-ready-auto'));
  }
  {
    const { f, nextRequest } = await interruptedAutomaticSuccessor(t);
    const occupying = structuredClone(await f.store.get(100));
    occupying.envelope = { ...occupying.envelope, runId: 101, attemptId: 'run-101', issueNumber: 44, number: 44 };
    occupying.controllerLifecycle = { version: 1, status: 'active' };
    delete occupying.predispatchPending;
    await f.store.put(101, occupying);
    await assert.rejects(f.broker.dispatch(nextRequest), { code: 'EXECUTION_SLOT_UNAVAILABLE' });
    assert.equal(f.deletes(), 1);
    assert.ok(f.issues.get(42).labels.some(label => label.name === 'codex-ready-auto'));
  }
});

for (const [name, mutate] of [
  ['missing original transition', async f => {
    f.events.set(42, f.events.get(42).filter(event => event.id !== f.original.envelope.readyEventId));
  }],
  ['missing recorded replacement transition', async f => {
    const missing = f.original.readyConsumption.laterEvents[0];
    f.events.set(42, f.events.get(42).filter(event => event.id !== missing));
  }],
  ['missing Writer Outcome', async f => { f.comments.length = 0; }],
  ['duplicate Writer Outcome', async f => { f.comments.push({ ...copy(f.comments[0]), id: 9001 }); }],
  ['edited Writer Outcome', async f => { f.comments[0].body += '\nchanged'; }]
]) {
  test('independent owner admission continues when only predecessor retirement proof is unavailable: ' + name, async t => {
    const f = await replacedReadyOutcome(t);
    await mutate(f);
    const next = await f.broker.dispatch(f.ready(100, 42, 'manual'));
    assert.equal(next.envelope.step, 2);
    assert.ok(await f.store.get(100));
    assert.equal((await f.store.get(99)).predispatchRecovery, undefined);
    assert.deepEqual((await f.control.status()).unknown, [99]);
    assert.equal(f.deletes(), 2);
  });
}

for (const [name, mutate] of [
  ['duplicate recorded transition id', async f => {
    const record = copy(await f.store.get(99));
    record.readyConsumption.laterEvents.push(record.readyConsumption.laterEvents[0]);
    await f.store.put(99, record);
  }],
  ['conflicting duplicate transition', async f => {
    const original = f.events.get(42).find(event => event.id === f.original.envelope.readyEventId);
    f.events.get(42).push({ ...copy(original), actor: { login: 'foreign', type: 'User' } });
  }],
  ['original run rerun', async f => { f.runs.get(99).run_attempt = 2; }],
  ['contradictory worker journal', async f => { await f.journal.put(99, { execution: null }); }],
  ['existing checkout', async f => { f.setCheckoutExists(true); }]
]) {
  test('replacement retirement rejects ' + name + ' evidence before writing the new admission', async t => {
    const f = await replacedReadyOutcome(t);
    await mutate(f);
    const original = copy(await f.store.get(99));
    const nextRequest = f.ready(100, 42, 'manual');
    await assert.rejects(f.broker.dispatch(nextRequest));
    assert.equal(await f.store.get(100), null);
    assert.deepEqual(await f.store.get(99), original);
    assert.equal(f.deletes(), 1);
  });
}

test('managed-pool Actions reruns complete through the fixed helper admission intercept', async t => {
  const root = await mkdtemp(join(tmpdir(), 'relay-pool-rerun-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const pathname = join(root, 'consumer.json');
  await writeFile(pathname, JSON.stringify(copyConsumerPool()), { mode: 0o600 });
  const source = `
    import assert from 'node:assert/strict';
    import {exerciseAutomaticRerun} from './controller/test/independent-admission-scenario.mjs';
    import {completedAdmissionRecord} from './controller/src/admission-control.mjs';
    for (const interruptAfterReceipt of [false,true]) {
      const cleanups=[];
      try {
        const {f,workers}=await exerciseAutomaticRerun({after:cleanup=>cleanups.push(cleanup)},
          {executionSlot:'primary',interruptAfterReceipt});
        const completed=await f.store.get(100);
        assert.equal(workers,1);
        assert.equal(completed.envelope.executionSlot,'primary');
        assert.equal(completed.controllerLifecycle.status,'complete');
        assert.equal(completed.predispatchPending,undefined);
        assert.ok(await completedAdmissionRecord(completed,f.journal));
      } finally {for(const cleanup of cleanups.reverse()) await cleanup();}
    }
  `;
  await promisify(execFile)(process.execPath, ['--input-type=module', '-e', source], {
    cwd: fileURLToPath(new URL('../../', import.meta.url)),
    env: { ...process.env, RELAY_CONSUMER_CONFIG: pathname, RELAY_EXECUTION_SLOT: 'primary' }
  });
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
        await assert.rejects(f.broker.dispatch(a),e=>e.code==='PREDISPATCH_ATTEMPT_FINALIZED');
        await assert.rejects(f.broker.dispatch(b),e=>e.code==='PREDISPATCH_ATTEMPT_FINALIZED');
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
