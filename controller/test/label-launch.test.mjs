import test from 'node:test';
import assert from 'node:assert/strict';
import { currentStep } from '../src/step-metadata.mjs';
import { parseLabelLaunch, labelRunName } from '../src/launch-metadata.mjs';
import { admitEnvelope, readAuthority } from '../src/live-authority.mjs';
import { runAttempt } from '../src/attempt.mjs';
import { createPublicationBroker } from '../src/publication-broker.mjs';
import { fixture, memoryStore } from './fixture.mjs';
import { reportRoutingResult } from '../src/entrypoint.mjs';

const labels = (...names) => names.map(name => ({ name }));
const receipt = e => ({ version: 2, attemptId: e.attemptId, child: 'started', containment: 'reaped',
  result: { status: 'success', summary: 'Implemented authorized work.', validation: ['local checks passed'] } });

test('current metadata accepts fresh and arbitrary continued Steps without history or a counter', () => {
  for (const step of [1, 5, 937, Number.MAX_SAFE_INTEGER]) {
    assert.equal(currentStep(labels('enhancement', `step-${step}`)), step);
  }
  for (const [names, code] of [[[], 'STEP_LABEL_MISSING'], [['step-1', 'step-2'], 'STEP_LABEL_MULTIPLE'],
    [['step-1', 'step02'], 'STEP_LABEL_MULTIPLE']]) assert.throws(() => currentStep(labels(...names)), { code });
  for (const name of ['step', 'Step-1', 'step-0', 'step--1', 'step-01', 'step-1.5', 'step-1e3', 'step-2\n', 'step-9007199254740992', 'step_2']) {
    assert.throws(() => currentStep(labels(name)), { code: 'STEP_LABEL_INVALID' });
  }
});

test('native Issue/PR auto/manual label payloads expose Task and Step before execution; Step alone cannot launch', () => {
  for (const eventName of ['issues', 'pull_request_target']) for (const route of ['auto', 'manual']) {
    const isPr = eventName === 'pull_request_target';
    const subject = { number: isPr ? 13 : 12, labels: labels('step-5', `codex-ready-${route}`),
      title: isPr ? 'Task 12 · Step 5 · Restore launch UX' : 'An unrelated Issue title with old Step 80' };
    const event = { action: 'labeled', label: { name: `codex-ready-${route}` }, [isPr ? 'pull_request' : 'issue']: subject };
    const launch = parseLabelLaunch(event, eventName);
    assert.equal(launch.number, subject.number); assert.equal(launch.step, 5); assert.equal(launch.route, route);
    assert.equal(launch.issueNumber, undefined); // Writer resolves the linked Issue.
    const name = labelRunName(launch, subject);
    assert.match(name, /Task 12/); assert.match(name, /(?:step-5|Step 5)/);
    if (isPr) assert.match(name, /PR #13/);
    assert.ok(name.length <= 80, name);
    for (const label of ['step-5', 'enhancement', 'Codex-ready-auto']) {
      assert.throws(() => parseLabelLaunch({ ...event, label: { name: label } }, eventName), { code: 'READY_EVENT_REQUIRED' });
    }
    assert.throws(() => parseLabelLaunch({ ...event, action: 'unlabeled' }, eventName), { code: 'READY_EVENT_REQUIRED' });
  }
});

for (const remediation of [false, true]) test(`one fresh auto ready event runs bounded ${remediation ? 'remediation' : 'Issue implementation'} once`, async t => {
  const f = await fixture(t, { remediation, labelLaunch: true, step: 5 });
  assert.equal(f.envelope.step, 5); assert.equal(f.envelope.readyEventId, 71);
  assert.equal(f.envelope.attemptId, 'run-99');
  assert.equal(currentStep(f.issue.labels), 5);
  assert.ok(!(f.pr ?? f.issue).labels.some(l => l.name === 'codex-ready-auto'));
  const journal = memoryStore(); let calls = 0;
  const run = () => runAttempt({ ...f, journal, execute: async () => {
    calls++; await f.commit(); return receipt(f.envelope);
  } });
  assert.equal((await run()).status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
  assert.equal((await run()).status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
  assert.equal(calls, 1); assert.equal(f.pushes(), 1);
  assert.equal(currentStep((await f.api.get('/issues/43')).labels), 5);
  assert.equal(currentStep(f.issue.labels), 5);
  assert.equal((await f.broker.invoke(f.admissionRequest)).resumed, true);
});

for (const remediation of [false, true]) test(`manual ready label makes a copyable ${remediation ? 'CR' : 'Issue'} handoff without a worker`, async t => {
  const f = await fixture(t, { remediation, labelLaunch: true, route: 'manual', step: 5 });
  const run = () => runAttempt({ ...f, journal: memoryStore(), execute: async () => assert.fail('manual started Codex') });
  assert.equal((await run()).status, 'handed-off'); assert.equal((await run()).status, 'handed-off');
  assert.equal(f.comments.length, 1); assert.equal(f.pushes(), 0);
  assert.match(f.comments[0].body, /MANUAL_CODEX_HANDOFF_READY[\s\S]*```text/);
  assert.match(f.comments[0].body, /Task 42 — Step 5/);
  assert.match(f.comments[0].body, /```text[\s\S]*Progress-bounded execution[\s\S]*```/);
  assert.match(f.comments[0].body, /does not authorize blind Relay retries/);
  assert.match(f.comments[0].body, /Do not launch nested workers, subagents or fan-out unless separately authorized/);
  assert.equal(currentStep(f.issue.labels), 5);
});

test('new remediation admission rejects invalid Step and native CR authority even with a ready command', async t => {
  const f = await fixture(t, { remediation: true, step: 5, labelLaunch: true });
  const before = structuredClone({ pr: f.pr, issue: f.issue, review: f.review });
  for (const [mutate, code] of [
    [() => { f.issue.labels = []; }, 'STEP_LABEL_MISSING'],
    [() => { f.pr.labels = labels('step-5', 'step-6'); }, 'STEP_LABEL_MULTIPLE'],
    [() => { f.pr.labels = labels('step-05'); }, 'STEP_LABEL_INVALID'],
    [() => { f.pr.labels = labels('step-6'); }, 'STEP_LABEL_MISMATCH'],
    [() => { f.review.body = f.review.body.replace('Step 5', 'Step 6'); }, 'CHANGE_REQUEST_STEP_MISMATCH'],
    [() => { f.review.state = 'APPROVED'; }, 'CURRENT_CHANGE_REQUEST_MISSING'],
    [() => { f.review.user.login = 'example-owner'; }, 'CURRENT_CHANGE_REQUEST_MISSING'],
    [() => { f.review.commit_id = 'a'.repeat(40); }, 'CONTRACT_HEAD_MISMATCH']
  ]) {
    mutate(); await assert.rejects(readAuthority(f.api, 'pull_request', 43, { step: 5 }), { code });
    Object.assign(f.pr, structuredClone(before.pr)); Object.assign(f.issue, structuredClone(before.issue)); Object.assign(f.review, structuredClone(before.review));
  }
  assert.equal(f.pushes(), 0);
});

test('stale, removed, conflicting, unauthorized and rerun ready events fail closed', async t => {
  const f = await fixture(t, { labelLaunch: true });
  const subject = { ...f.issue, labels: labels('step-1', 'codex-ready-auto') };
  const fresh = { ...f.run, display_title: labelRunName(f.envelope, subject) };
  const event = structuredClone(f.events[0]);
  for (const [delta, expected] of [
    [{ event: { ...event, actor: { login: 'other', type: 'User' } } }, 'READY_EVENT_STALE'],
    [{ event: { ...event, actor: { login: 'example-owner', type: 'Bot' } } }, 'READY_EVENT_STALE'],
    [{ event: { ...event, event: 'unlabeled' } }, 'READY_EVENT_STALE'],
    [{ event: { ...event, created_at: '2026-09-04T11:00:00Z' } }, 'READY_EVENT_STALE'],
    [{ event: { ...event, created_at: '2026-09-04T12:01:00Z' } }, 'READY_EVENT_STALE'],
    [{ run: { ...fresh, run_attempt: 2 } }, 'OWNER_RUN_NOT_ADMITTED'],
    [{ run: { ...fresh, actor: { login: 'other' } } }, 'OWNER_RUN_NOT_ADMITTED'],
    [{ run: { ...fresh, triggering_actor: { login: 'other' } } }, 'OWNER_RUN_NOT_ADMITTED'],
    [{ run: { ...fresh, path: '.github/workflows/other.yml' } }, 'OWNER_RUN_NOT_ADMITTED'],
    [{ labels: labels('step-1', 'codex-ready-auto', 'codex-ready-manual') }, 'READY_LABEL_AMBIGUOUS']
  ]) {
    const api = { ...f.api, getRun: async () => delta.run ?? fresh,
      get: async path => path === '/issues/42' ? { ...subject, labels: delta.labels ?? subject.labels } : f.api.get(path),
      list: async path => path.endsWith('/events') ? [delta.event ?? event] : f.api.list(path) };
    try {
      const result = await admitEnvelope(api, f.admissionRequest);
      assert.equal(result.block?.code, expected);
    } catch (error) { assert.equal(error.code, expected); }
  }
});

test('a new run cannot reuse a consumed native event or queue a prewritten retry', async t => {
  const f = await fixture(t, { labelLaunch: true });
  const subject = { ...f.issue, labels: labels('step-1', 'codex-ready-auto') };
  const request = { ...f.admissionRequest, runId: 100 };
  const run = { ...f.run, id: 100, display_title: labelRunName(f.envelope, subject) };
  const api = { ...f.api, getRun: async id => id === 100 ? run : { ...f.run, status: 'completed', updated_at: '2026-09-04T12:01:00Z' },
    get: async path => path === '/issues/42' ? subject : f.api.get(path) };
  const broker = createPublicationBroker({ api, store: f.store, publisher: f.publisher });
  await assert.rejects(broker.dispatch(request), { code: 'READY_EVENT_ALREADY_CONSUMED' });
  f.events[0].id++;
  await assert.rejects(broker.dispatch(request), { code: 'READY_EVENT_QUEUED' });
  assert.equal(await f.store.get(100), null);
  assert.equal(f.pushes(), 0);
});

test('partial ready-label consumption reserves the event and never reexecutes on replay', async t => {
  const f = await fixture(t, { labelLaunch: true });
  const record = await f.store.get(99); record.readyConsumed = false; await f.store.put(99, record);
  await assert.rejects(f.broker.invoke(f.admissionRequest), { code: 'READY_CONSUMPTION_UNCERTAIN' });
  assert.equal(f.pushes(), 0);
});

test('a label run cannot target an unrelated invalid Issue even for a blocked Outcome', async t => {
  const f = await fixture(t, { labelLaunch: true });
  const api = { ...f.api, get: async path => path === '/issues/44'
    ? { ...f.issue, number: 44, labels: [] } : f.api.get(path) };
  const broker = createPublicationBroker({ api, store: memoryStore(), publisher: f.publisher });
  await assert.rejects(broker.dispatch({ ...f.admissionRequest, number: 44, issueNumber: 44 }), { code: 'OWNER_RUN_NOT_ADMITTED' });
  assert.equal(f.comments.length, 0); assert.equal(f.pushes(), 0);
});

test('native label ordering does not change launch authority', async t => {
  const f = await fixture(t, { labelLaunch: true });
  f.issue.labels = labels('codex-ready-auto', 'step-1');
  assert.equal((await admitEnvelope(f.api, f.admissionRequest)).step, 1);
});

function eventLaunch(f) {
  return parseLabelLaunch({ action: 'labeled', label: { name: `codex-ready-${f.admissionRequest.route}` },
    [f.pr ? 'pull_request' : 'issue']: f.pr ?? f.issue }, f.run.event);
}

for (const remediation of [false, true]) for (const route of ['auto', 'manual']) {
  test(`${route} ${remediation ? 'PR' : 'Issue'} invalid Step commands are consumed once with a bounded BLOCKED Outcome`, async t => {
    for (const [names, code] of [[[], 'STEP_LABEL_MISSING'], [['step-05'], 'STEP_LABEL_INVALID'],
      [['step-5', 'step-6'], 'STEP_LABEL_MULTIPLE']]) {
      const mutations = [];
      const f = await fixture(t, { remediation, route, step: 5, labelLaunch: true, beforeAdmission(f) {
        const subject = f.pr ?? f.issue;
        subject.labels = labels(...names, `codex-ready-${route}`);
        f.run.display_title = labelRunName(f.admissionRequest, subject);
        Object.assign(f.admissionRequest, eventLaunch(f)); // Includes the invalid event snapshot.
        assert.equal(f.admissionRequest.step, null);
        const remove = f.api.delete;
        f.api.delete = async path => { mutations.push(path); return remove(path); };
      } });
      assert.equal(f.admission.status, 'BLOCKED');
      assert.equal(f.envelope.admissionBlock.code, code);
      assert.equal(f.envelope.startHead, null); assert.equal(f.envelope.branch, null);
      assert.equal(f.envelope.readyEventId, 71);
      assert.deepEqual((f.pr ?? f.issue).labels, labels(...names));
      assert.equal((await f.store.get(99)).readyConsumed, true);
      assert.equal((await f.broker.invoke(f.admissionRequest)).status, 'BLOCKED');
      assert.deepEqual(mutations, [`/issues/${f.envelope.number}/labels/codex-ready-${route}`]);
      assert.equal(f.comments.length, 1); assert.equal(f.pushes(), 0);
      assert.match(f.comments[0].body, new RegExp(`Terminal code: ${code}`));
      assert.match(f.comments[0].body, /Admission status: BLOCKED_BEFORE_WORKER/);
      const output = [];
      assert.equal(await reportRoutingResult(() => f.broker.invoke(f.admissionRequest), {
        write: value => output.push(value), writeError: value => output.push(value)
      }), 0);
      assert.equal(output.filter(value => value.startsWith('::warning')).length, 1);
    }
  });
}

test('safe CR/Step/head/Issue authority rejection consumes the exact command and publishes only on its bound target', async t => {
  for (const [mutate, code] of [
    [f => { f.issue.labels = labels('step-6'); }, 'STEP_LABEL_MISMATCH'],
    [f => { f.pr.labels = labels('step-6', 'codex-ready-auto'); }, 'STEP_LABEL_MISMATCH'],
    [f => { f.pr.title = 'Task 42 · Step 6 · core'; }, 'STEP_DISPLAY_MISMATCH'],
    [f => { f.pr.body = 'Closes #42\nCloses #44'; }, 'CANONICAL_ISSUE_AMBIGUOUS'],
    [f => { f.review.state = 'APPROVED'; }, 'CURRENT_CHANGE_REQUEST_MISSING'],
    [f => { f.review.user.login = 'example-owner'; }, 'CURRENT_CHANGE_REQUEST_MISSING'],
    [f => { f.review.body = f.review.body.replace('Step 5', 'Step 6'); }, 'CHANGE_REQUEST_STEP_MISMATCH'],
    [f => { f.review.commit_id = 'b'.repeat(40); }, 'CONTRACT_HEAD_MISMATCH'],
    [f => { f.issue.state = 'closed'; }, 'ISSUE_NOT_ADMITTED'],
  ]) {
    const mutations = [];
    const f = await fixture(t, { remediation: true, step: 5, labelLaunch: true, beforeAdmission(f) {
      mutate(f);
      for (const method of ['post', 'delete']) {
        const operation = f.api[method];
        f.api[method] = async (path, body) => { mutations.push(path); return operation.call(f.api, path, body); };
      }
    } });
    assert.equal(f.admission.status, 'BLOCKED'); assert.equal(f.envelope.admissionBlock.code, code);
    assert.equal((await f.broker.invoke(f.admissionRequest)).status, 'BLOCKED');
    assert.deepEqual(mutations, ['/issues/43/labels/codex-ready-auto', '/issues/43/comments']);
    assert.equal(f.comments.length, 1); assert.equal(f.pushes(), 0);
  }
});

for (const remediation of [false, true]) test(`repairing invalid ${remediation ? 'PR' : 'Issue'} event metadata before admission cannot authorize that event`, async t => {
  const f = await fixture(t, { remediation, step: 5, labelLaunch: true, beforeAdmission(f) {
    const subject = f.pr ?? f.issue;
    subject.labels = labels('codex-ready-auto');
    f.run.display_title = labelRunName(f.admissionRequest, subject);
    Object.assign(f.admissionRequest, eventLaunch(f));
    subject.labels = labels('step-5', 'codex-ready-auto');
  } });
  assert.equal(f.admission.status, 'BLOCKED'); assert.equal(f.envelope.admissionBlock.code, 'LAUNCH_STEP_INVALID');
  assert.equal(f.envelope.step, null); assert.equal((await f.store.get(99)).readyConsumed, true);
  assert.equal(f.comments.length, 1); assert.equal(f.pushes(), 0);
});

test('repair and reapply creates a fresh same-Step attempt; a rejected event cannot be reused or queued', async t => {
  let deletes = 0;
  const f = await fixture(t, { step: 5, labelLaunch: true, beforeAdmission(f) {
    f.issue.labels = labels('step-05', 'codex-ready-auto');
    f.run.display_title = labelRunName(f.admissionRequest, f.issue);
    Object.assign(f.admissionRequest, eventLaunch(f));
    const remove = f.api.delete;
    f.api.delete = async path => { deletes++; return remove(path); };
  } });
  f.issue.labels = labels('step-5');
  assert.equal((await f.broker.invoke(f.admissionRequest)).status, 'BLOCKED');
  assert.equal(deletes, 1);
  const previousRun = { ...f.run, status: 'completed', updated_at: '2026-09-04T12:01:00Z' };
  f.run.id = 100;
  f.api.getRun = async id => structuredClone(id === 99 ? previousRun : f.run);
  f.issue.labels.push({ name: 'codex-ready-auto' });
  f.run.display_title = labelRunName(f.admissionRequest, f.issue);
  const request = { operation: 'admit', runId: 100, ...eventLaunch(f) };
  await assert.rejects(f.broker.invoke(request), { code: 'READY_EVENT_ALREADY_CONSUMED' });
  f.events[0].id++;
  await assert.rejects(f.broker.invoke(request), { code: 'READY_EVENT_QUEUED' });
  assert.equal(await f.store.get(100), null); assert.equal(deletes, 1); assert.equal(f.comments.length, 1);
  f.events[0].created_at = '2026-09-04T12:02:00Z';
  f.run.created_at = '2026-09-04T12:02:01Z';
  const fresh = await f.broker.invoke(request);
  assert.equal(fresh.envelope.step, 5); assert.equal(fresh.envelope.readyEventId, 72);
  assert.equal(fresh.envelope.attemptId, 'run-100'); assert.equal(fresh.envelope.admissionBlock, undefined);
  assert.equal(deletes, 2); assert.deepEqual(f.issue.labels, labels('step-5'));
  assert.equal((await f.broker.invoke(f.admissionRequest)).status, 'BLOCKED');
  assert.equal(deletes, 2); assert.equal(f.comments.length, 1);
});

for (const remediation of [false, true]) test(`unrelated ${remediation ? 'PR' : 'Issue'} label additions/removals/reordering preserve admission and display`, async t => {
  for (const current of [['step-5', 'codex-ready-auto', 'new-category'], ['codex-ready-auto', 'step-5'],
    ['category', 'codex-ready-auto', 'step-5', 'triage']]) {
    const f = await fixture(t, { remediation, labelLaunch: true, step: 5, beforeAdmission(f) {
      const subject = f.pr ?? f.issue;
      subject.labels = labels('triage', 'step-5', 'category', 'codex-ready-auto');
      f.run.display_title = labelRunName(f.admissionRequest, subject);
      Object.assign(f.admissionRequest, eventLaunch(f));
      subject.labels = labels(...current);
    } });
    assert.equal(f.envelope.step, 5); assert.equal(f.envelope.issueNumber, 42);
    assert.equal(f.envelope.admissionBlock, undefined);
    assert.match(f.run.display_title, /Task 42/); assert.match(f.run.display_title, /step-5|Step 5/);
    if (remediation) assert.match(f.run.display_title, /PR #43/);
    assert.deepEqual((f.pr ?? f.issue).labels, labels(...current.filter(name => name !== 'codex-ready-auto')));
  }
});

test('changing/removing/malforming Step after the event still blocks and consumes the bound command', async t => {
  for (const [names, code] of [[['step-6'], 'STEP_LABEL_MISMATCH'], [[], 'STEP_LABEL_MISSING'],
    [['step06'], 'STEP_LABEL_INVALID'], [['step-5', 'step-6'], 'STEP_LABEL_MULTIPLE']]) {
    const f = await fixture(t, { labelLaunch: true, step: 5, beforeAdmission(f) {
      f.issue.labels = labels('unrelated-new-label', ...names, 'codex-ready-auto');
    } });
    assert.equal(f.admission.status, 'BLOCKED'); assert.equal(f.envelope.admissionBlock.code, code);
    assert.equal((await f.store.get(99)).readyConsumed, true); assert.equal(f.comments.length, 1);
  }
});

test('unsafe event binding has no label mutation, attempt reservation or unrelated publication even with invalid Step', async t => {
  for (const remediation of [false, true]) for (const mutate of [
    f => { f.run.actor.login = 'other'; },
    f => { f.run.triggering_actor = { login: 'other' }; },
    f => { f.run.run_attempt = 2; },
    f => { f.run.path = '.github/workflows/other.yml'; },
    f => { f.run.repository.full_name = 'other/repo'; },
    f => { f.run.display_title = f.run.display_title.replace(/Task 42|PR #43/, 'Task 44'); },
    f => { f.run.display_title = f.run.display_title.replace(/Auto implementation|Auto remediation/, 'Manual handoff'); },
    f => { f.events[0].actor.login = 'other'; },
    f => { f.events[0].actor.type = 'Bot'; },
    f => { f.events[0].event = 'unlabeled'; },
    f => { f.events[0].label.name = 'codex-ready-manual'; },
    f => { f.events[0].created_at = '2026-09-04T11:00:00Z'; },
    f => { f.events[0].created_at = '2026-09-04T12:01:00Z'; },
    f => { (f.pr ?? f.issue).labels = labels('step-05'); },
    f => { (f.pr ?? f.issue).labels = labels('step-05', 'codex-ready-manual'); },
    f => { (f.pr ?? f.issue).labels.push({ name: 'codex-ready-manual' }); },
  ]) {
    let store;
    await assert.rejects(fixture(t, { remediation, labelLaunch: true, beforeAdmission(f) {
      store = f.store;
      (f.pr ?? f.issue).labels = labels('step-05', 'codex-ready-auto');
      mutate(f);
      f.api.delete = f.api.post = async () => assert.fail('unbound event mutated GitHub');
    } }), error => ['OWNER_RUN_NOT_ADMITTED', 'READY_EVENT_STALE', 'READY_LABEL_AMBIGUOUS'].includes(error.code));
    assert.deepEqual(await store.all(), []);
  }
});

test('replacement ready events discovered after authority reads are never consumed', async t => {
  await assert.rejects(fixture(t, { labelLaunch: true, beforeAdmission(f) {
    const get = f.api.get;
    f.api.get = async path => {
      if (path === '/git/ref/heads/main') f.events[0].id++;
      return get.call(f.api, path);
    };
    f.api.delete = f.api.post = async () => assert.fail('replacement command mutated');
  } }), { code: 'READY_EVENT_STALE' });
});

test('ambiguous blocked-command consumption reserves the event without retrying deletion or publication', async t => {
  const f = await fixture(t, { labelLaunch: true });
  const store = memoryStore(); let deletes = 0;
  f.issue.labels = labels('step-05', 'codex-ready-auto');
  const api = { ...f.api, delete: async () => { deletes++; throw Object.assign(new Error('transport'), { code: 'EIO' }); } };
  const broker = createPublicationBroker({ api, store, publisher: f.publisher });
  await assert.rejects(broker.dispatch(f.admissionRequest), { code: 'EIO' });
  assert.equal((await store.get(99)).envelope.readyEventId, 71);
  assert.equal((await store.get(99)).admissionBlock.code, 'STEP_LABEL_INVALID');
  await assert.rejects(broker.dispatch(f.admissionRequest), { code: 'READY_CONSUMPTION_UNCERTAIN' });
  assert.equal(deletes, 1); assert.equal(f.comments.length, 0);
});

test('an existing task branch rejects and consumes an Issue command once without launching work', async t => {
  const f = await fixture(t, { labelLaunch: true, beforeAdmission(f) {
    const get = f.api.get;
    f.api.get = path => path.startsWith('/git/matching-refs/') ? [{ ref: 'refs/heads/codex/test-42' }] : get.call(f.api, path);
  } });
  assert.equal(f.admission.status, 'BLOCKED');
  assert.equal(f.envelope.admissionBlock.code, 'TASK_BRANCH_ALREADY_EXISTS');
  assert.equal((await f.store.get(99)).readyConsumed, true);
  assert.equal((await f.broker.invoke(f.admissionRequest)).status, 'BLOCKED');
  assert.deepEqual(f.issue.labels, labels('step-1')); assert.equal(f.comments.length, 1); assert.equal(f.pushes(), 0);
});
