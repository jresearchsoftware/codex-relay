import test from 'node:test';
import assert from 'node:assert/strict';
import { main } from '../src/entrypoint.mjs';
import { CONSUMER } from '../../consumer/consumer.mjs';
import { OWNER, REPOSITORY, REVIEWER } from '../src/execution-contract.mjs';
import { fixture } from './fixture.mjs';
import { spawn } from 'node:child_process';
import { createOnDemandDispatchAdapter } from '../src/github.mjs';
import { admissionBinding, canonicalAuthorityJson, extractAuthorityRecord, sha256Body } from '../../contracts/src/github-authority.mjs';

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
        const aborted = new Promise((resolve, reject) => {
          const onAbort = () => { clearTimeout(timer); resolve(); };
          const timer = setTimeout(() => {
            signal?.removeEventListener('abort', onAbort);
            reject(new Error('The routing controller did not receive native SIGTERM'));
          }, 1000);
          signal?.addEventListener('abort', onAbort, { once: true });
        });
        process.kill(process.pid, 'SIGTERM');
        await aborted;
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

for (const phase of ['before-launch', 'contained-child', 'unacknowledged-child']) {
  test(`native cancellation survives trusted Decision drift (${phase})`, async t => {
    const charter = 'Authority model: github-native-v1\nIssue closure policy: keep-open\nExercise native cancellation independently of Task requirements.';
    const decisions = [];
    const amend = amendments => decisions.push({ id: 900 + decisions.length,
      user: { login: REVIEWER, type: 'Bot', id: 701 },
      body: '```relay-authority\n' + canonicalAuthorityJson({ schema_version: '4.0', kind: 'decision',
        repository: REPOSITORY, task: 42, parent: { kind: 'issue', number: 42 },
        charter_sha256: sha256Body(charter), purpose: 'Clarify source requirements and acceptance.',
        amendments, supersedes: null, context: [] }) + '\n```\n' });
    amend({ scope: ['Original authorized source work'], boundaries: ['No deployment'], validation: ['diff-check'] });
    const f = await fixture(t, { issueBody: charter, labelLaunch: true,
      beforeAdmission: ({ api }) => {
        const list = api.list.bind(api);
        api.list = async path => path === '/issues/42/comments' ? [...decisions, ...await list(path)] : list(path);
      } });
    const original = structuredClone(f.envelope);
    let spawned = 0; let finalized; let collected = 0; let completed = 0;
    const before = ['SIGINT', 'SIGTERM'].map(name => process.listenerCount(name));
    const cancel = () => {
      amend({ boundaries: ['No deployment', 'Keep fixtures isolated'], validation: ['diff-check', 'secret-scan'] });
      process.kill(process.pid, 'SIGTERM');
    };
    // Exercise routing and the real dispatcher/process boundary. The child is
    // synthetic: its optional model-UID receipt distinguishes containment from
    // merely observing that the outer process exited after a signal.
    const options = {
      env: { GITHUB_EVENT_PATH: '/fixture/event', GITHUB_EVENT_NAME: 'workflow_dispatch',
        GITHUB_REF: `refs/heads/${CONSUMER.baseBranch}`, GITHUB_RUN_ID: String(f.envelope.runId) },
      readEvent: async () => JSON.stringify({ repository: { full_name: REPOSITORY }, sender: { login: OWNER },
        inputs: { task: String(f.envelope.issueNumber), step: String(f.envelope.step), route: 'auto' } }),
      resolveSlot: () => undefined, createJournal: () => f.journal,
      createWriter: () => ({ invoke: async request => {
        if (request.operation === 'admit') return { envelope: f.envelope };
        if (request.operation === 'complete-execution') { completed++; return { status: 'COMPLETED' }; }
        return f.broker.invoke(request);
      } }),
      createDispatcher: ({ signal }) => createOnDemandDispatchAdapter({ signal, timeoutMs: 5000,
        diagnosticStore: async value => ({ status: 'stored', executionId: value.executionId, mode: value.mode }),
        readDiagnosticConfig: async () => ({ mode: 'normal' }),
        reserveDiagnostic: async () => ({ write: async () => {} }),
        finalizeArtifacts: async value => { finalized = value;
          return { cleanup: 'complete', persistence: 'not_required', retention: 'none' }; },
        spawnImpl: (_command, _args, childOptions) => {
          spawned++;
          assert.notEqual(phase, 'before-launch');
          const code = `const { writeSync } = require('node:fs');
            process.stdin.resume(); const hold = setInterval(() => {}, 1000);
            ${phase === 'contained-child' ? `process.on('SIGTERM', () => {
              writeSync(2, JSON.stringify({ version: 2, status: 'blocked', code: 'EXECUTION_CANCELLED',
                diagnostic: { containment: 'reaped', observed: { child: 'started' } } }));
              clearInterval(hold); process.stdin.destroy(); process.exitCode = 1;
            });` : ''}
            writeSync(1, 'READY');`;
          const child = spawn(process.execPath, ['-e', code], childOptions);
          t.after(() => { if (child.exitCode === null && child.signalCode === null) child.kill('SIGKILL'); });
          child.stdout.once('data', cancel);
          return child;
        } }),
      prepare: async e => {
        await f.prepare(e);
        if (phase === 'before-launch') await new Promise((resolve, reject) => {
          const observed = () => { clearTimeout(timer); resolve(); };
          const timer = setTimeout(() => {
            process.removeListener('SIGTERM', observed); reject(new Error('Native SIGTERM was not delivered'));
          }, 1000);
          process.once('SIGTERM', observed); cancel();
        });
      },
      collect: async e => { collected++; return f.collect(e); }, persistFailure: f.persistFailure
    };
    const code = phase === 'unacknowledged-child' ? 'CONTAINMENT_NOT_PROVEN' : 'EXECUTION_CANCELLED';
    await assert.rejects(main(options), { code });
    const record = await f.journal.get(f.envelope.runId);
    assert.equal(record.execution.errorCode, code);
    assert.equal(record.execution.containment, phase === 'before-launch' ? 'not_required'
      : phase === 'contained-child' ? 'reaped' : 'unknown');
    assert.equal(record.execution.child, phase === 'before-launch' ? 'not_started'
      : phase === 'contained-child' ? 'started' : 'unknown');
    assert.equal(spawned, phase === 'before-launch' ? 0 : 1);
    assert.equal(collected, phase === 'unacknowledged-child' ? 0 : 1);
    if (phase !== 'before-launch') assert.equal(finalized.containment, record.execution.containment);
    assert.equal(f.pushes(), 0);
    assert.equal(completed, 1);
    const outcomes = f.comments.map(comment => extractAuthorityRecord(comment.body)).filter(value => value?.kind === 'outcome');
    assert.equal(outcomes.length, 1);
    assert.equal(outcomes[0].status, 'blocked');
    assert.deepEqual(outcomes[0].admission, admissionBinding(original.request));
    assert.deepEqual(outcomes[0].authority_drift.changed_fields, ['boundaries', 'validation']);
    assert.deepEqual((await f.store.get(f.envelope.runId)).envelope, original);
    assert.deepEqual(['SIGINT', 'SIGTERM'].map(name => process.listenerCount(name)), before);
  });
}
