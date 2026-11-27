import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { canonicalAuthorityJson, extractAuthorityRecord, renderAuthorityRecord, sha256Body, validateAdmissionSnapshot } from '../../contracts/src/github-authority.mjs';

test('Writer binds App Server execution to the selected repository and original attempt', async t => {
  const root = await mkdtemp(join(tmpdir(), 'relay-app-server-admission-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const config = JSON.parse(await readFile(new URL('../../consumer/fixtures/example.json', import.meta.url), 'utf8'));
  const first = config.repository;
  const selected = 'second-org/second-project';
  const target = { socketPath: '/run/test-relay/selected.sock', workspaceRoot: '/srv/test-relay/selected' };
  config.repositories = [first, selected];
  config.repositoryAppServerTargets = {
    [first]: { socketPath: '/run/test-relay/first.sock', workspaceRoot: '/srv/test-relay/first' },
    [selected]: target
  };
  delete config.repository;
  const configPath = join(root, 'consumer.json');
  await writeFile(configPath, JSON.stringify(config), { mode: 0o600 });
  process.env.RELAY_CONSUMER_CONFIG = configPath;
  process.env.RELAY_REPOSITORY = selected;
  const { fixture } = await import('./fixture.mjs');
  const { validateEnvelope } = await import('../src/execution-contract.mjs');

  const admissionCalls = [];
  const f = await fixture(t, { route: 'app-server', remediation: true, labelLaunch: true, streamlinedAdmission: true,
    beforeAdmission: ({ issue, review }) => {
      issue.labels.push({ name: 'step-1' });
      review.body = renderAuthorityRecord({ ...extractAuthorityRecord(review.body),
        overrides: { model: 'gpt-5.6-luna', effort: 'high', subagents: false, validation: ['diff-check'] } });
    },
    createAdmission: () => ({
      assertOpen: async () => admissionCalls.push('open'),
      assertSlotComplete: async slot => admissionCalls.push(slot),
      assertAppServerAttemptsComplete: async task => admissionCalls.push(task),
      reserve: async () => ({ version: 1, status: 'active' })
    }) });
  const e = f.envelope;
  assert.deepEqual(admissionCalls, ['open', 'primary', 42]);
  assert.equal(e.repository, selected);
  assert.equal(e.backend, 'app-server');
  assert.deepEqual(e.appServerTarget, target);
  assert.equal(e.route, 'auto');
  assert.equal(e.readyLabel, 'codex-ready-app-server');
  assert.deepEqual(e.profile, { cliModelId: 'gpt-5.6-luna', effort: 'high' });
  assert.equal(e.subagentsAllowed, false);
  assert.match(e.thread, /^Task 42 — Step 2 — CR-42-001/);
  assert.equal(e.request.backend, 'app-server');
  assert.equal(e.request.app_server_target_sha256, sha256Body(canonicalAuthorityJson(target)));
  assert.ok(!JSON.stringify(e.request).includes(target.socketPath));
  assert.ok(!JSON.stringify(e.request).includes(target.workspaceRoot));
  assert.equal(validateEnvelope(e), e);
  assert.throws(() => validateAdmissionSnapshot({ ...e.request, route: 'manual' }), { code: 'AUTHORITY_ADMISSION_INVALID' });
  assert.throws(() => validateEnvelope({ ...e, appServerTarget: config.repositoryAppServerTargets[first] }),
    { code: 'APP_SERVER_TARGET_BINDING_CHANGED' });
  assert.throws(() => validateEnvelope({ ...e, readyLabel: 'codex-ready-auto' }), { code: 'APP_SERVER_TARGET_BINDING_CHANGED' });
  assert.equal((await f.store.get(e.runId)).readyConsumed, true);
  assert.deepEqual(f.pr.labels, [{ name: 'step-2' }]);

  await assert.rejects(f.broker.invoke({ ...f.admissionRequest, route: 'auto' }), { code: 'RUN_BINDING_CHANGED' });
  await assert.rejects(f.broker.invoke(f.admissionRequest), { code: 'PREDISPATCH_ATTEMPT_FINALIZED' });
  const journal = { version: e.version, envelope: e, execution: { reserved: true, returned: false } };
  await f.journal.put(e.runId, { ...journal, envelope: { ...e, backend: undefined } });
  await assert.rejects(f.broker.invoke(f.admissionRequest), { code: 'PREDISPATCH_ATTEMPT_FINALIZED' });
  await f.journal.put(e.runId, journal);
  const replay = await f.broker.invoke(f.admissionRequest);
  assert.equal(replay.resumed, true);
  assert.equal(replay.admissionUnstarted, undefined);
  assert.equal(replay.envelope.step, e.step);
  assert.deepEqual(admissionCalls, ['open', 'primary', 42]);

  await t.test('a disconnect preserves the original turn and checkout until Writer can finish and release the attempt', async t => {
    const { createAdmissionControl } = await import('../src/admission-control.mjs');
    const { runAttempt } = await import('../src/attempt.mjs');
    const { CONSUMER_DIGEST } = await import('../../consumer/consumer.mjs');
    const f = await fixture(t, { route: 'app-server', labelLaunch: true, writerCollect: true,
      createAdmission: async ({ root, store, journal }) => {
        const gateRoot = join(root, 'claims');
        await mkdir(gateRoot, { mode: 0o700 });
        const admission = createAdmissionControl({ root: gateRoot, consumerDigest: CONSUMER_DIGEST, store, journal, protectedRoot: false });
        await admission.initialize();
        return admission;
      }
    });
    const { envelope, admissionControl, journal, broker } = f;
    const { attemptId, runId, issueNumber } = envelope;
    const attempt = { runId, attemptId };
    const checkpoint = { attemptId, socketPath: envelope.appServerTarget.socketPath,
      cwd: join(envelope.appServerTarget.workspaceRoot, attemptId),
      threadId: '12345678-1234-1234-1234-123456789abc', turnId: '12345678-1234-1234-1234-123456789abd',
      phase: 'turn-started' };
    const terminal = { ...checkpoint, phase: 'terminal', status: 'completed', containment: 'turn_completed' };
    const collectRequest = { operation: 'collect-progress', ...attempt };
    const request = { ...f, collect: () => broker.invoke(collectRequest) };
    let prepared = 0;
    let starts = 0;
    let reconciliations = 0;
    let sourceHead;
    const interrupted = Object.assign(new Error('Synthetic transport loss'), { code: 'APP_SERVER_CONNECTION_LOST' });
    await assert.rejects(runAttempt({ ...request,
      prepare: async e => { prepared++; await f.prepare(e); },
      execute: async (e, options) => {
        assert.equal(options.mode, undefined);
        starts++;
        await options.saveCheckpoint(checkpoint);
        sourceHead = await f.commit('docs/work.md', 'Useful source from the App Server turn.\n');
        throw interrupted;
      }
    }), { code: 'APP_SERVER_CONNECTION_LOST' });
    assert.equal((await journal.get(runId)).execution.returned, false);
    assert.deepEqual((await journal.get(runId)).execution.appServer, checkpoint);
    assert.equal((await f.store.get(runId)).outcome, null);
    assert.equal(f.comments.length, 0);
    assert.equal(f.pushes(), 0);
    await assert.rejects(broker.invoke(collectRequest), { code: 'COLLECTION_NOT_ADMITTED' });
    await assert.rejects(admissionControl.assertAppServerAttemptsComplete(issueNumber), { code: 'PRIOR_EXECUTION_UNRESOLVED' });

    const operationId = '12345678-1234-1234-1234-123456789abc';
    await admissionControl.quiesce({ operationId, target: 'a'.repeat(40) });
    const active = await admissionControl.drained({ operationId });
    assert.equal(active.drained, false);
    assert.deepEqual(active.active, [runId]);
    await assert.rejects(admissionControl.complete(attempt), { code: 'ADMISSION_COMPLETION_UNKNOWN' });

    const pending = await journal.get(runId);
    await journal.put(runId, { ...pending, execution: { ...pending.execution, returned: true, child: 'started', containment: 'reaped' } });
    await assert.rejects(broker.invoke(collectRequest), { code: 'COLLECTION_NOT_ADMITTED' });
    await assert.rejects(admissionControl.complete(attempt), { code: 'ADMISSION_COMPLETION_UNKNOWN' });
    await journal.put(runId, pending);

    const replay = await broker.invoke(f.admissionRequest);
    assert.equal(replay.resumed, true);
    const result = await runAttempt({ ...request, envelope: replay.envelope, admissionResumed: true,
      prepare: async () => { assert.fail('A reconciled turn must reuse its original checkout.'); },
      execute: async (e, options) => {
        assert.equal(options.mode, 'reconcile');
        assert.deepEqual(options.checkpoint, checkpoint);
        reconciliations++;
        await options.saveCheckpoint(terminal);
        return { version: e.version, attemptId, child: 'started', containment: 'turn_completed',
          result: { status: 'success', summary: 'App Server source complete.', validation: ['fixture check'] } };
      }
    });
    assert.equal(prepared, 1);
    assert.equal(starts, 1);
    assert.equal(reconciliations, 1);
    assert.equal(result.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
    assert.equal(result.head, sourceHead);
    assert.equal(result.prNumber, 43);
    assert.equal((await f.api.get('/pulls/43')).draft, false);
    assert.equal(f.comments.filter(comment => comment.body.startsWith('## Codex Outcome')).length, 1);
    assert.equal(f.pushes(), 1);
    const finalReplay = await runAttempt({ ...request, admissionResumed: true,
      execute: async () => { assert.fail('A published turn must not execute again.'); } });
    assert.equal(finalReplay.outcomeId, result.outcomeId);
    assert.equal(f.pushes(), 1);
    assert.equal(f.comments.filter(comment => comment.body.startsWith('## Codex Outcome')).length, 1);
    assert.deepEqual(await admissionControl.complete(attempt), { complete: true });
    const lifecycle = (await f.store.get(runId)).controllerLifecycle;
    assert.equal(lifecycle.containment, 'turn_completed');
    for (const [key, value] of Object.entries(terminal)) assert.equal(lifecycle.appServer[key], value);
    assert.equal((await admissionControl.drained({ operationId })).drained, true);

    const cli = await fixture(t, { writerCollect: true });
    const cliRun = cli.envelope.runId;
    await cli.journal.put(cliRun, { version: cli.envelope.version, envelope: cli.envelope,
      execution: { reserved: true, returned: true, child: 'started', containment: 'turn_completed', appServer: terminal } });
    await assert.rejects(cli.broker.invoke({ operation: 'collect-progress', runId: cliRun, attemptId: cli.envelope.attemptId }),
      { code: 'COLLECTION_NOT_ADMITTED' });
  });
});
