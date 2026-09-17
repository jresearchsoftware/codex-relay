import test from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { mkdtemp, mkdir, writeFile, readFile, rm } from 'node:fs/promises';
import { PassThrough } from 'node:stream';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { promisify } from 'node:util';
import { execFile } from 'node:child_process';
import { createAttemptStore } from '../src/attempt-store.mjs';
import { createPublicationBroker } from '../src/publication-broker.mjs';
import { classifyGitFailure, createGitPublisher, collectProgress, git, gitEnvironment } from '../src/trusted-git.mjs';
import { prepareCheckout } from '../src/attempt-runtime.mjs';
import { runAttempt } from '../src/attempt.mjs';
import { REPOSITORY, VERSION, WRITER, REVIEWER, causalEvidence } from '../src/execution-contract.mjs';
import { currentReview } from '../src/live-authority.mjs';
import { failureDiagnosticFromDetails, redactDiagnosticText } from '../src/diagnostics.mjs';
import { createLocalWriterAdapter } from '../src/local-writer.mjs';
import { serializeWriterFailure } from '../src/privileged-writer-helper.mjs';
import { admissionWarningSummary, emitAdmissionWarnings, terminalOutcomeBody, workerOutcomeClaims } from '../src/outcome.mjs';

import { fixture, memoryStore } from './fixture.mjs';
const exec = promisify(execFile);

test('new Issue admission safely defaults recoverable metadata and publishes warning-ready authority', async t => {
  const f = await fixture(t, { issueBody: [
    '# Task 42 defaulted admission',
    'Implement the admitted goal.'
  ].join('\n') });
  assert.equal(f.envelope.startHead, f.envelope.targetBase);
  assert.equal(f.envelope.branch, 'codex/task-42');
  assert.equal(f.envelope.thread, 'Task 42 — Step 1 — defaulted admission');
  assert.equal(f.envelope.closure, 'Related to #42');
  assert.deepEqual(f.envelope.profile, { cliModelId: 'example-model', effort: 'max' });
  assert.equal(f.envelope.subagentsAllowed, false);
  assert.ok(!('allowedPaths' in f.envelope));
  assert.ok(f.envelope.admission.warnings.some(warning => warning.code === 'CODEX_MODEL_DEFAULTED'));
  assert.ok(f.envelope.admission.warnings.some(warning => warning.code === 'CODEX_EFFORT_DEFAULTED'));
  assert.ok(!f.envelope.admission.warnings.some(warning => ['accepted starting base', 'branch'].includes(warning.field)));
  assert.ok(f.envelope.admission.warnings.some(warning => warning.code === 'ISSUE_CLOSURE_POLICY_DEFAULTED'));
  const emitted = [];
  assert.equal(emitAdmissionWarnings(f.envelope.admission.warnings, value => emitted.push(value)), f.envelope.admission.warnings.length);
  assert.ok(emitted.every(value => value.startsWith('::warning title=Codex admission::')));
  const body = terminalOutcomeBody(f.envelope, { terminalCode: 'SEMANTIC_RESULT_BLOCKED' });
  assert.match(body, /Admission status: COMPLETED_WITH_WARNINGS/);
  assert.ok(body.includes(`Warning summary: ${admissionWarningSummary(f.envelope.admission.warnings)}`));
});

test('safe admission blockers publish exactly one truthful terminal Outcome without worker authority', async t => {
  const f = await fixture(t, { issueBody: [
    '# Task 42 malformed starting head',
    'Accepted starting main: not-a-sha'
  ].join('\n') });
  assert.equal(f.envelope.admissionBlock.code, 'ISSUE_STARTING_HEAD_INVALID');
  assert.equal(f.comments.filter(comment => comment.body.includes('## Codex Outcome')).length, 1);
  assert.match(f.comments[0].body, /Status: BLOCKED/);
  assert.match(f.comments[0].body, /Token: IMPLEMENTATION_BLOCKED/);
  assert.match(f.comments[0].body, /Admission status: BLOCKED_BEFORE_WORKER/);
  assert.match(f.comments[0].body, /Requested model: UNAVAILABLE; effort: UNAVAILABLE/);
  assert.match(f.comments[0].body, /Historical reviewed\/starting head: UNAVAILABLE/);
  const resumed = await f.broker.invoke(f.admissionRequest);
  assert.equal(resumed.status, 'BLOCKED');
  assert.equal(f.comments.filter(comment => comment.body.includes('## Codex Outcome')).length, 1);
});

test('a live malformed starting head terminalizes as a normal blocked Outcome', async t => {
  const f = await fixture(t); const journal = memoryStore();
  f.issue.body += '\nAccepted starting main: malformed';
  const result = await runAttempt({ ...f, journal, execute: () => assert.fail('head blocker must not launch the worker') });
  assert.equal(result.status, 'BLOCKED');
  assert.equal(f.comments.filter(comment => comment.body.includes('## Codex Outcome')).length, 1);
  assert.match(f.comments[0].body, /Terminal code: ISSUE_STARTING_HEAD_INVALID/);
  assert.match(f.comments[0].body, /Admission status: COMPLETED/);
});

test('ambiguous remediation authority publishes one blocked Outcome on the fixed PR without guessing its head', async t => {
  const f = await fixture(t, { remediation: true, reviewBody: 'The reviewed identity is not present.' });
  assert.equal(f.envelope.admissionBlock.code, 'CURRENT_METADATA_MISSING');
  assert.equal(f.comments.filter(comment => comment.body.includes('## Codex Outcome')).length, 1);
  assert.match(f.comments[0].body, /Token: REMEDIATION_BLOCKED/);
  assert.match(f.comments[0].body, /Admission status: BLOCKED_BEFORE_WORKER/);
  assert.match(f.comments[0].body, /Historical reviewed\/starting head: UNAVAILABLE/);
  assert.doesNotMatch(f.comments[0].body, /Starting head: [a-f0-9]{40}/);
});

function helperFailureSpawn(payload) {
  return () => {
    const child = new EventEmitter();
    child.stdout = new PassThrough();
    child.stderr = new PassThrough();
    child.stdin = new PassThrough();
    queueMicrotask(() => {
      child.stdout.end();
      child.stderr.end(`${JSON.stringify(payload)}\n`);
      child.emit('close', 1, null);
    });
    return child;
  };
}

test('composed owner path finishes once with exact-head CI pending and mergeability unknown', async t => {
  const f = await fixture(t); const journal = createAttemptStore(join(f.root, 'journal')); let executions = 0;
  const get = f.api.get.bind(f.api);
  f.api.get = async path => {
    const value = await get(path);
    return path === '/pulls/43' ? { ...value, mergeable: null } : value;
  };
  f.api.validations = async () => assert.fail('automatic finish must not query native CI');
  const args = { ...f, journal, execute: async () => { executions++; await f.commit(); return { version: VERSION, attemptId: f.envelope.attemptId, child: 'started', containment: 'reaped', result: { status: 'success' } }; } };
  const result = await runAttempt(args);
  const saved = await journal.get(99);
  assert.equal(saved.progress.head, await f.remoteHead()); assert.equal(f.pushes(), 1);
  assert.equal(result.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW'); assert.equal(executions, 1); assert.equal(f.pushes(), 1);
  assert.equal(f.comments.filter(c => c.body.includes('## Codex Outcome')).length, 1);
  assert.match(f.comments[0].body, /Native exact-head CI and GitHub mergeability were not evaluated/);
  assert.doesNotMatch(f.comments[0].body, /check \d+ passed|GitHub reports mergeable/);
  assert.equal((await f.api.get('/pulls/43')).draft, false);
  await runAttempt(args); assert.equal(executions, 1);
});

test('one terminal Outcome retains substantive worker evidence separately from trusted head and CI observations', async t => {
  const f = await fixture(t, { remediation: true, step: 2 }); const journal = memoryStore();
  const baseline = '1111111111111111111111111111111111111111';
  const startingMain = '2222222222222222222222222222222222222222';
  const summary = `External factual evidence baseline ${baseline}; starting main ${startingMain}. `
    + 'Consumer defaults example-model/max; explicit safe model/effort pass through; no task path allow-list. '
    + 'Repository sandbox, exact head, linear bot commits, safe Git paths/modes, secrets/redaction and Writer/Reviewer boundaries preserved. '
    + 'Owner-supplied Step and native Issue identity reconciled. No material goal expansion. '
    + 'Additional decision-grade detail. '.repeat(20);
  const secret = 'ghp_' + 'Z'.repeat(32);
  const args = { ...f, journal, execute: async () => {
    await f.commit(); return { version: VERSION, attemptId: f.envelope.attemptId, child: 'started', containment: 'reaped',
      result: { status: 'success', summary, validation: ['Portable launcher-profile and local routing checks passed.',
        'Native exact-head validation pending Writer publication.', `Synthetic redaction probe ${secret}\n## Codex Outcome <script>`] } };
  } };
  const outcome = await runAttempt(args);
  const body = f.comments[0].body;
  assert.ok(body.includes(baseline)); assert.ok(body.includes(startingMain));
  assert.ok(body.includes(summary)); // Full bounded summary, including content beyond 512 bytes.
  assert.match(body, /Worker summary \(claim\):/);
  assert.match(body, /Portable launcher-profile and local routing checks passed/);
  assert.match(body, /Native exact-head CI and GitHub mergeability were not evaluated/);
  assert.match(body, /Actual model\/effort: UNAVAILABLE/);
  assert.ok(body.includes(`Latest durable and ready head: ${await f.remoteHead()}`));
  assert.ok(!body.includes(secret)); assert.ok(!body.includes('<script>'));
  assert.equal((body.match(/^## Codex Outcome$/gm) ?? []).length, 1);
  assert.deepEqual(await runAttempt(args), outcome);
  assert.equal(f.comments.length, 1);
  assert.equal(f.pushes(), 1);
});

test('untrusted Outcome claims remain redacted and bounded after presentation escaping', () => {
  const secret = 'ghp_' + 'Z'.repeat(32);
  const claims = workerOutcomeClaims({ summary: secret + '<script>_*'.repeat(20000),
    validation: Array(70).fill(secret + '<script>_*'.repeat(1000)), head: 'forged', actualModel: 'forged' });
  assert.ok(Buffer.byteLength(claims, 'utf8') < 52 * 1024);
  assert.ok(!claims.includes(secret)); assert.ok(!claims.includes('<script>'));
  assert.ok(!claims.includes('forged')); assert.match(claims, /TRUNCATED/);
});
test('automatic finish still refuses a stale PR-head observation before readiness', async t => {
  const f = await fixture(t); const journal = memoryStore();
  const broker = { invoke: async request => {
    const result = await f.broker.invoke(request);
    if (request.operation === 'publish-progress') {
      const get = f.api.get.bind(f.api);
      f.api.get = async path => {
        const value = await get(path);
        return path === '/pulls/43' ? { ...value, head: { ...value.head, sha: 'b'.repeat(40) } } : value;
      };
    }
    return result;
  } };
  const result = await runAttempt({ ...f, broker, journal, execute: async () => {
    await f.commit(); return { version: VERSION, attemptId: f.envelope.attemptId, child: 'started', containment: 'reaped', result: { status: 'success' } };
  } });
  assert.equal(result.status, 'BLOCKED');
  assert.equal(f.comments.filter(c => c.body.includes('## Codex Outcome')).length, 1);
  assert.match(f.comments[0].body, /Status: BLOCKED/);
  assert.match(f.comments[0].body, /Durable\/published head: [a-f0-9]{40}/);
});
test('manual routing remains a handoff and does not enter automatic completion', async t => {
  const f = await fixture(t); const envelope = { ...f.envelope, route: 'manual' };
  let observed;
  const result = await runAttempt({ envelope, broker: { invoke: async request => {
    observed = request; return { status: 'handed-off' };
  } }, journal: null, prepare: () => assert.fail('manual preparation'), execute: () => assert.fail('manual execution'), collect: () => assert.fail('manual collection') });
  assert.equal(result.status, 'handed-off');
  assert.equal(observed.operation, 'handoff');
  assert.equal(observed.attemptId, envelope.attemptId);
});

for (const remediation of [false, true]) test(`one ${remediation ? 'remediation' : 'implementation'} worker preserves multiple corrections without relaunch`, async t => {
  const f = await fixture(t, { remediation }); const journal = memoryStore();
  let executions = 0; let finalHead;
  const args = { ...f, journal, execute: async () => {
    executions++;
    for (const correction of ['initial implementation', 'correct diagnosed failure', 'correct new validation finding']) {
      finalHead = await f.commit('docs/work.md', `${correction}\n`);
    }
    return { version: VERSION, attemptId: f.envelope.attemptId, child: 'started', containment: 'reaped',
      result: { status: 'success', summary: 'Three evidence-based corrections', validation: [], blockedReason: '' } };
  } };
  const completed = await runAttempt(args);
  assert.match(completed.status, /PENDING_FRESH_REVIEW/);
  assert.equal(await f.remoteHead(), finalHead);
  assert.equal(await f.command(f.cwd, ['rev-list', '--count', `${f.envelope.startHead}..HEAD`]), '3');
  await runAttempt(args);
  assert.equal(executions, 1); assert.equal(f.pushes(), 1);
  assert.equal(f.comments.filter(c => c.body.includes('## Codex Outcome')).length, 1);
});
test('blocked model commits are durable and never asserted ready', async t => {
  const f = await fixture(t); const journal = memoryStore();
  const result = await runAttempt({ ...f, journal, execute: async () => { await f.commit(); return { version: VERSION, attemptId: f.envelope.attemptId, child: 'started', containment: 'reaped', result: { status: 'blocked' } }; } });
  assert.equal(result.status, 'BLOCKED');
  assert.equal((await journal.get(99)).progress.head, await f.remoteHead());
  assert.equal(f.comments.filter(c => c.body.includes('## Codex Outcome')).length, 1);
  assert.match(f.comments[0].body, new RegExp(`Durable/published head: ${await f.remoteHead()}`));
  assert.match(f.comments[0].body, /Cause summary: UNAVAILABLE/);
});
test('a failed ready transition cannot publish a completion Outcome', async t => {
  const f = await fixture(t); const journal = memoryStore();
  f.api.ready = async () => { throw Object.assign(new Error('READY_FAILED'), { code: 'READY_FAILED' }); };
  await assert.rejects(runAttempt({ ...f, journal, execute: async () => {
    await f.commit(); return { version: VERSION, attemptId: f.envelope.attemptId, child: 'started', containment: 'reaped', result: { status: 'success' } };
  } }), { code: 'READY_FAILED' });
  assert.equal(f.comments.filter(c => c.body.includes('## Codex Outcome')).length, 1);
  assert.match(f.comments[0].body, /Terminal code: READY_FAILED/);
  assert.equal((await journal.get(99)).progress.head, await f.remoteHead());
});

test('automatic failure before durable publication publishes one blocked Issue Outcome', async t => {
  const f = await fixture(t); const journal = memoryStore();
  await assert.rejects(runAttempt({ ...f, journal, execute: async () => {
    throw Object.assign(new Error('worker unavailable'), { code: 'CODEX_RESULT_MISSING' });
  } }), { code: 'CONTAINMENT_NOT_PROVEN' });
  assert.equal(f.comments.filter(c => c.body.includes('## Codex Outcome')).length, 1);
  assert.match(f.comments[0].body, /Durable\/published head: NONE PUBLISHED/);
  assert.match(f.comments[0].body, /Failure boundary: result-parse/);
  assert.match(f.comments[0].body, /Cause summary: CODEX_RESULT_MISSING/);
  assert.equal(f.comments[0].body.includes('Durable/published head: ' + await f.remoteHead()), false);
});

test('blocked remediation publishes its terminal Outcome on the existing PR', async t => {
  const f = await fixture(t, { remediation: true }); const journal = memoryStore();
  const result = await runAttempt({ ...f, journal, execute: async () => {
    return { version: VERSION, attemptId: f.envelope.attemptId, child: 'started', containment: 'reaped', result: { status: 'blocked' } };
  } });
  assert.equal(result.status, 'BLOCKED');
  assert.equal(f.comments.filter(c => c.body.includes('## Codex Outcome')).length, 1);
  assert.match(f.comments[0].body, /Token: REMEDIATION_BLOCKED/);
  assert.match(f.comments[0].body, /Historical reviewed\/starting head:/);
});

test('blocked Outcome uses structured route state instead of Issue\/CR token prose', () => {
  const body = terminalOutcomeBody({
    target: 'pull_request',
    input: 'Allowed blocked token: TASK_18_BLOCKED\nNative Change Request blocked_token: CR_18_002_BLOCKED',
    thread: 'Task 18 — Step 3 — Outcome Scope and Run-Name Gate Remediation',
    attemptId: 'event-18-step-3',
    profile: { cliModelId: 'gpt-5.6-luna', effort: 'high' },
    startHead: 'a'.repeat(40)
  }, { terminalCode: 'SEMANTIC_RESULT_BLOCKED' });
  assert.match(body, /Token: REMEDIATION_BLOCKED/);
  assert.doesNotMatch(body, /TASK_18_BLOCKED|CR_18_002_BLOCKED/);
});

test('Outcome publication failure is explicit in terminal execution evidence', async t => {
  const f = await fixture(t); const journal = memoryStore();
  const post = f.api.post.bind(f.api);
  f.api.post = async (path, body) => path.endsWith('/comments')
    ? Promise.reject(Object.assign(new Error('comment unavailable'), { code: 'GITHUB_REQUEST_FAILED' }))
    : post(path, body);
  await assert.rejects(runAttempt({ ...f, journal, execute: async () => {
    throw Object.assign(new Error('worker unavailable'), { code: 'CODEX_RESULT_MISSING' });
  } }), error => {
    assert.equal(error.code, 'CONTAINMENT_NOT_PROVEN');
    assert.deepEqual(error.details.outcomePublication, { status: 'failed', code: 'GITHUB_REQUEST_FAILED' });
    assert.deepEqual(error.details.diagnostic.outcomePublication, { status: 'failed', code: 'GITHUB_REQUEST_FAILED' });
    return true;
  });
  assert.equal(f.comments.filter(c => c.body.includes('## Codex Outcome')).length, 0);
});
test('successful push plus stale observation reconciles without repeating the push', async t => {
  const f = await fixture(t); await f.prepare(f.envelope); await f.commit(); const progress = await f.collect(f.envelope);
  const request = { operation: 'publish-progress', runId: 99, attemptId: f.envelope.attemptId, bundle: progress.bundle };
  f.stale(true); await assert.rejects(f.broker.invoke(request), error => {
    assert.equal(error.code, 'PUBLICATION_UNCERTAIN');
    assert.equal(error.details.failureDiagnostic.primaryCause, 'GIT_OBSERVATION_UNCERTAIN'); return true;
  });
  assert.equal(await f.remoteHead(), progress.head);
  f.stale(false); const result = await f.broker.invoke(request);
  assert.equal(result.publishedHead, progress.head); assert.equal(f.pushes(), 1);
});
test('uncertain failed push is not automatically repeated', async t => {
  const f = await fixture(t); await f.prepare(f.envelope); await f.commit(); const progress = await f.collect(f.envelope);
  const request = { operation: 'publish-progress', runId: 99, attemptId: f.envelope.attemptId, bundle: progress.bundle };
  f.failPush(true); await assert.rejects(f.broker.invoke(request), { code: 'PUBLICATION_UNCERTAIN' });
  f.failPush(false); await assert.rejects(f.broker.invoke(request), { code: 'PUBLICATION_UNCERTAIN' }); assert.equal(f.pushes(), 1);
});
test('failed push retains an observed authorization cause and blocks future mutation', async t => {
  const f = await fixture(t); await f.prepare(f.envelope); await f.commit(); const progress = await f.collect(f.envelope);
  const request = { operation: 'publish-progress', runId: 99, attemptId: f.envelope.attemptId, bundle: progress.bundle };
  const cause = Object.assign(new Error('remote authentication failed: token=private'), {
    details: { failureDiagnostic: { classification: 'GIT_AUTHORIZATION_REJECTED', primaryCause: 'GIT_AUTHORIZATION_REJECTED', operation: 'push', preview: 'remote authentication failed: token=[REDACTED_SECRET]' } }
  });
  f.failPush(cause); await assert.rejects(f.broker.invoke(request), error => {
    assert.equal(error.code, 'PUBLICATION_UNCERTAIN');
    assert.equal(error.details.failureDiagnostic.primaryCause, 'GIT_AUTHORIZATION_REJECTED');
    assert.equal(error.details.failureDiagnostic.operation, 'push'); return true;
  });
  f.failPush(false); await assert.rejects(f.broker.invoke(request), { code: 'PUBLICATION_UNCERTAIN' });
  assert.equal(f.pushes(), 1);
});
test('failed push plus exact remote observation succeeds without a second push', async t => {
  const f = await fixture(t); await f.prepare(f.envelope); await f.commit(); const progress = await f.collect(f.envelope);
  const request = { operation: 'publish-progress', runId: 99, attemptId: f.envelope.attemptId, bundle: progress.bundle };
  const cause = Object.assign(new Error('response lost after remote accepted the push'), { code: 'ETIMEDOUT' });
  f.failPush({ afterPush: true, error: cause });
  const result = await f.broker.invoke(request); assert.equal(result.publishedHead, progress.head); assert.equal(f.pushes(), 1);
  const resumed = await f.broker.invoke(request); assert.equal(resumed.publishedHead, progress.head); assert.equal(f.pushes(), 1);
});
test('remote head conflict remains distinct from transport uncertainty', async t => {
  const f = await fixture(t); await f.prepare(f.envelope); await f.commit(); const progress = await f.collect(f.envelope);
  f.observeAs('b'.repeat(40));
  await assert.rejects(f.broker.invoke({ operation: 'publish-progress', runId: 99, attemptId: f.envelope.attemptId, bundle: progress.bundle }), error => {
    assert.equal(error.code, 'PUBLICATION_UNCERTAIN');
    assert.equal(error.details.failureDiagnostic.primaryCause, 'GIT_REMOTE_HEAD_CONFLICT'); return true;
  });
  assert.equal(f.pushes(), 1);
});
test('trusted Git failure classifies and bounds safe causal evidence', async () => {
  assert.equal(classifyGitFailure({ code: 128, stderr: 'remote: Authentication failed' }), 'GIT_AUTHORIZATION_REJECTED');
  assert.equal(classifyGitFailure({ code: 1, stderr: 'non-fast-forward' }), 'GIT_REF_CONFLICT');
  assert.equal(classifyGitFailure({ code: 'ECONNRESET', stderr: 'connection reset by peer' }), 'GIT_TRANSPORT_FAILED');
  assert.equal(classifyGitFailure({ code: 'ETIMEDOUT', stderr: 'operation timed out' }), 'GIT_TIMEOUT');
  assert.equal(classifyGitFailure({ code: 1, stderr: 'something unexpected' }), 'GIT_UNKNOWN_FAILURE');
  await assert.rejects(git(tmpdir(), ['rev-parse', 'HEAD']), error => {
    assert.equal(error.code, 'TRUSTED_GIT_FAILED');
    assert.equal(error.details.failureDiagnostic.classification, 'GIT_LOCAL_FAILURE');
    assert.equal(error.details.failureDiagnostic.operation, 'rev-parse');
    assert.ok(error.details.failureDiagnostic.preview.length <= 1024);
    assert.ok(!JSON.stringify(error.details).includes('Authorization:'));
    return true;
  });
  const redacted = failureDiagnosticFromDetails({ failureDiagnostic: {
    code: 'TRUSTED_GIT_FAILED', preview: `authorization: ghp_${'A'.repeat(24)}`
  } });
  assert.ok(!JSON.stringify(redacted).includes(`ghp_${'A'.repeat(24)}`));
});
test('local process permission failures take precedence over authorization text', () => {
  for (const code of ['EACCES', 'EPERM', 'ENOENT', 'EINVAL', 'ENOTDIR']) {
    assert.equal(classifyGitFailure({ code, stderr: 'Permission denied' }), 'GIT_LOCAL_FAILURE');
  }
  for (const stderr of [
    "fatal: Authentication failed for 'https://github.com/example/repo.git/'",
    'remote: Write access to repository not granted.',
    'git@github.com: Permission denied (publickey).'
  ]) {
    assert.equal(classifyGitFailure({ code: 128, stderr }), 'GIT_AUTHORIZATION_REJECTED');
  }
});
test('Basic Authorization values are redacted case-insensitively before persistence', () => {
  const headerValue = Buffer.from('x-access-token:synthetic-not-secret').toString('base64');
  const raw = `authorization: basic ${headerValue}`;
  const redacted = redactDiagnosticText(raw);
  assert.ok(!redacted.includes(headerValue));
  assert.match(redacted, /authorization: basic \[REDACTED_BASIC_AUTH\]/i);
  const diagnostic = failureDiagnosticFromDetails({ failureDiagnostic: { preview: `Authorization: Basic ${headerValue}` } });
  assert.ok(!JSON.stringify(diagnostic).includes(headerValue));
});
test('publication process exit stays separate from Codex child exit in causal evidence', () => {
  const publicationError = Object.assign(new Error('publication failed'), {
    code: 'PUBLICATION_UNCERTAIN',
    details: { failureDiagnostic: {
      code: 'PUBLICATION_UNCERTAIN', classification: 'GIT_REF_CONFLICT', primaryCause: 'GIT_REF_CONFLICT',
      operation: 'observe', priorCause: 'GIT_AUTHORIZATION_REJECTED', gitExitCode: 128
    } }
  });
  const publication = causalEvidence(publicationError, { child: 'started', stage: 'progress' });
  assert.equal(publication.observed.exitCode, null);
  assert.deepEqual(publication.publication, { operation: 'observe', priorCause: 'GIT_AUTHORIZATION_REJECTED', gitExitCode: 128 });

  const childError = Object.assign(new Error('child failed'), {
    code: 'CODEX_NONZERO_EXIT',
    details: { failureDiagnostic: { code: 'CODEX_NONZERO_EXIT', childState: 'started', childExitCode: 7, primaryCause: 'CODEX_RESULT_MISSING' } }
  });
  const child = causalEvidence(childError, { child: 'started', stage: 'execution' });
  assert.equal(child.observed.exitCode, 7);
  assert.equal(child.publication, undefined);
});
test('publication cause survives broker, privileged helper, local adapter, and terminal diagnostics', async t => {
  const f = await fixture(t); const journal = memoryStore();
  const headerValue = Buffer.from('x-access-token:synthetic-not-secret').toString('base64');
  const pushCause = Object.assign(new Error('remote authentication failed'), {
    code: 128,
    details: { failureDiagnostic: {
      code: 'TRUSTED_GIT_FAILED', classification: 'GIT_AUTHORIZATION_REJECTED', primaryCause: 'GIT_AUTHORIZATION_REJECTED',
      operation: 'push', gitExitCode: 128, preview: `Authorization: Basic ${headerValue}`
    } }
  });
  f.failPush(pushCause); f.observeAs('b'.repeat(40));
  const boundaryBroker = {
    invoke: request => request.operation === 'publish-progress'
      ? f.broker.invoke(request).catch(async error => {
        const payload = serializeWriterFailure(error);
        assert.ok(!JSON.stringify(payload).includes(headerValue));
        const local = createLocalWriterAdapter({ spawnImpl: helperFailureSpawn(payload) });
        return local.invoke(request);
      })
      : f.broker.invoke(request)
  };

  await assert.rejects(runAttempt({ ...f, broker: boundaryBroker, journal, execute: async () => {
    await f.commit();
    return { version: VERSION, attemptId: f.envelope.attemptId, child: 'started', containment: 'reaped', result: { status: 'success' } };
  } }), error => {
    assert.equal(error.code, 'PUBLICATION_UNCERTAIN');
    assert.equal(error.details.failureDiagnostic.primaryCause, 'GIT_REMOTE_HEAD_CONFLICT');
    assert.equal(error.details.diagnostic.observed.exitCode, null);
    assert.deepEqual(error.details.diagnostic.publication, {
      operation: 'observe', priorCause: 'GIT_AUTHORIZATION_REJECTED'
    });
    assert.equal(error.details.failureDiagnostic.gitExitCode, undefined);
    assert.equal(error.details.failureDiagnostic.preview, undefined);
    return true;
  });
  const terminal = (await journal.get(99)).diagnostic;
  assert.equal(terminal.primaryCause, 'GIT_REMOTE_HEAD_CONFLICT');
  assert.deepEqual(terminal.publication, { operation: 'observe', priorCause: 'GIT_AUTHORIZATION_REJECTED' });
  assert.equal(f.pushes(), 1);
});

for (const observationCause of ['GIT_TIMEOUT', 'GIT_AUTHORIZATION_REJECTED', 'GIT_TRANSPORT_FAILED', 'GIT_LOCAL_FAILURE', 'GIT_UNKNOWN_FAILURE', null]) {
  for (const failedPush of [false, true]) {
    test(`terminal observation cause ${observationCause ?? 'unavailable'} after ${failedPush ? 'failed' : 'successful'} push stays attributable without retry`, async t => {
      const f = await fixture(t); const journal = memoryStore();
      if (failedPush) f.failPush({ details: { failureDiagnostic: {
        classification: 'GIT_REF_CONFLICT', primaryCause: 'GIT_REF_CONFLICT', operation: 'push', gitExitCode: 1, preview: 'push rejected'
      } } });
      f.failObserve(Object.assign(new Error('observation failed'), observationCause ? { details: { failureDiagnostic: {
        code: 'TRUSTED_GIT_FAILED', classification: observationCause, primaryCause: observationCause,
        operation: 'ls-remote', gitExitCode: 128, preview: 'observation failed'
      } } } : {}));
      const publication = { operation: 'observe', ...(failedPush ? { priorCause: 'GIT_REF_CONFLICT' } : {}),
        ...(observationCause ? { gitExitCode: 128 } : {}) };
      const broker = { invoke: request => request.operation === 'publish-progress'
        ? f.broker.invoke(request).catch(error => createLocalWriterAdapter({
          spawnImpl: helperFailureSpawn(serializeWriterFailure(error))
        }).invoke(request))
        : f.broker.invoke(request) };
      await assert.rejects(runAttempt({ ...f, broker, journal, execute: async () => {
        await f.commit();
        return { version: VERSION, attemptId: f.envelope.attemptId, child: 'started', containment: 'reaped', result: { status: 'success' } };
      } }), error => {
        assert.equal(error.code, 'PUBLICATION_UNCERTAIN');
        const diagnostic = error.details.failureDiagnostic;
        assert.equal(diagnostic.primaryCause, observationCause ?? 'GIT_OBSERVATION_UNAVAILABLE');
        assert.equal(diagnostic.classification, observationCause ?? 'GIT_OBSERVATION_UNAVAILABLE');
        assert.equal(diagnostic.preview, observationCause ? 'observation failed' : undefined);
        assert.equal(diagnostic.operation, 'observe');
        return true;
      });
      const terminal = (await journal.get(99)).diagnostic;
      assert.equal(terminal.primaryCause, observationCause ?? 'GIT_OBSERVATION_UNAVAILABLE');
      assert.deepEqual(terminal.publication, publication);
      assert.equal(terminal.observed.exitCode, null);
      assert.deepEqual(f.publicationOperations, ['push', 'observe']);
      const progress = await f.collect(f.envelope);
      f.failPush(false); f.failObserve(null);
      const request = { operation: 'publish-progress', runId: 99, attemptId: f.envelope.attemptId, bundle: progress.bundle };
      if (failedPush) await assert.rejects(broker.invoke(request), { code: 'PUBLICATION_UNCERTAIN' });
      else assert.equal((await broker.invoke(request)).publishedHead, progress.head);
      assert.equal(f.pushes(), 1);
      assert.deepEqual(f.publicationOperations, ['push', 'observe']);
    });
  }
}

test('failed push with confirmed unchanged existing head retains push cause in terminal diagnostics', async t => {
  const f = await fixture(t, { remediation: true }); const journal = memoryStore();
  f.failPush({ details: { failureDiagnostic: {
    classification: 'GIT_AUTHORIZATION_REJECTED', primaryCause: 'GIT_AUTHORIZATION_REJECTED',
    operation: 'push', gitExitCode: 128, preview: 'remote authentication failed'
  } } });
  const broker = { invoke: request => request.operation === 'publish-progress'
    ? f.broker.invoke(request).catch(error => createLocalWriterAdapter({
      spawnImpl: helperFailureSpawn(serializeWriterFailure(error))
    }).invoke(request))
    : f.broker.invoke(request) };
  await assert.rejects(runAttempt({ ...f, broker, journal, execute: async () => {
    await f.commit();
    return { version: VERSION, attemptId: f.envelope.attemptId, child: 'started', containment: 'reaped', result: { status: 'success' } };
  } }), error => {
    assert.equal(error.code, 'PUBLICATION_UNCERTAIN');
    assert.equal(error.details.failureDiagnostic.preview, 'remote authentication failed');
    return true;
  });
  const terminal = (await journal.get(99)).diagnostic;
  assert.equal(terminal.primaryCause, 'GIT_AUTHORIZATION_REJECTED');
  assert.deepEqual(terminal.publication, { operation: 'push', gitExitCode: 128 });
  assert.equal(terminal.observed.exitCode, null);
  assert.equal(await f.remoteHead(), f.envelope.startHead);
  f.failPush(false); const progress = await f.collect(f.envelope);
  await assert.rejects(broker.invoke({ operation: 'publish-progress', runId: 99, attemptId: f.envelope.attemptId, bundle: progress.bundle }), { code: 'PUBLICATION_UNCERTAIN' });
  assert.deepEqual(f.publicationOperations, ['push', 'observe']);
  assert.equal(f.pushes(), 1);
});
test('unknown execution reservation cannot be relaunched', async t => {
  const f = await fixture(t); const journal = memoryStore();
  await journal.put(99, { version: VERSION, envelope: f.envelope, execution: { reserved: true, returned: false } });
  await assert.rejects(runAttempt({ ...f, journal, execute: () => assert.fail('duplicate child') }), { code: 'EXECUTION_UNKNOWN_NO_RETRY' });
  assert.equal((await journal.get(99)).diagnostic.observed.child, 'unknown');
});
test('missing journal after admission remains unknown and cannot launch a child', async t => {
  const f = await fixture(t);
  await assert.rejects(runAttempt({ ...f, admissionResumed: true, journal: memoryStore(), execute: () => assert.fail('duplicate') }), { code: 'JOURNAL_MISSING_EXECUTION_UNKNOWN' });
});
test('a journal without execution evidence cannot be treated as a new attempt', async t => {
  const f = await fixture(t); const journal = memoryStore();
  await journal.put(99, { version: VERSION, envelope: f.envelope });
  await assert.rejects(runAttempt({ ...f, journal, execute: () => assert.fail('duplicate') }), { code: 'JOURNAL_MISSING_EXECUTION_UNKNOWN' });
});
for (const remediation of [false, true]) test(`trusted publication accepts task-required repository files, remediation=${remediation}`, async t => {
  const f = await fixture(t, { remediation }); await f.prepare(f.envelope);
  await f.command(f.cwd, ['config', 'core.fsmonitor', 'echo HOSTILE_CONFIG_EXECUTED']);
  for (const path of ['new-policy.md', 'automation/new-worker.mjs', '.github/ISSUE_TEMPLATE/new.md', 'admin/example.md']) {
    await mkdir(join(f.cwd, path, '..'), { recursive: true });
    await f.commit(path, 'task-required change\n');
  }
  const p = await f.collect(f.envelope);
  const result = await f.broker.invoke({ operation: 'publish-progress', runId: 99, attemptId: f.envelope.attemptId, bundle: p.bundle });
  assert.equal(result.publishedHead, p.head);
  assert.equal(f.pushes(), 1);
  assert.equal(await f.command(f.root, ['--git-dir=' + f.remote, 'rev-parse', 'main']), f.envelope.startHead);
});
test('unrelated main advancement does not gate safe progress publication', async t => {
  const f = await fixture(t); await f.prepare(f.envelope); await f.commit();
  await writeFile(join(f.source, 'unrelated.md'), 'main advanced\n'); await f.command(f.source, ['add', '.']); await f.command(f.source, ['commit', '-m', 'unrelated']); await f.command(f.source, ['push', f.remote, 'main']);
  const p = await f.collect(f.envelope);
  const r = await f.broker.invoke({ operation: 'publish-progress', runId: 99, attemptId: f.envelope.attemptId, bundle: p.bundle });
  assert.equal(r.publishedHead, p.head);
});
test('one native dispatch cannot be presented as another run', async t => {
  const f = await fixture(t);
  await assert.rejects(f.broker.invoke({ ...f.admissionRequest, runId: 100 }), { code: 'OWNER_RUN_NOT_ADMITTED' });
});
test('authority mutation blocks publication before mutation', async t => {
  const f = await fixture(t); await f.prepare(f.envelope); await f.commit(); const p = await f.collect(f.envelope);
  f.issue.body += '\nOwner changed the goal.';
  await assert.rejects(f.broker.invoke({ operation: 'publish-progress', runId: 99, attemptId: f.envelope.attemptId, bundle: p.bundle }), { code: 'AUTHORITY_CHANGED' }); assert.equal(f.pushes(), 0);
});

test('live goal edit rejects stale admitted progress before any publication mutation', async t => {
  const f = await fixture(t); await f.prepare(f.envelope); await f.commit(); const p = await f.collect(f.envelope);
  const before = await f.remoteHead(); const record = await f.store.get(99);
  f.issue.body += '\nNew required behavior.';
  f.api.post = f.api.delete = f.api.ready = async () => assert.fail('publication mutation');
  await assert.rejects(f.broker.invoke({ operation: 'publish-progress', runId: 99, attemptId: f.envelope.attemptId, bundle: p.bundle }), { code: 'AUTHORITY_CHANGED' });
  assert.equal(f.pushes(), 0); assert.equal(await f.remoteHead(), before);
  assert.deepEqual(await f.store.get(99), record);
});

test('a live PR closure edit rejects stale remediation progress before publication', async t => {
  const f = await fixture(t, { remediation: true }); await f.prepare(f.envelope); await f.commit(); const p = await f.collect(f.envelope);
  const get = f.api.get.bind(f.api);
  f.api.get = async path => { const value = await get(path); return path === '/pulls/43' ? { ...value, body: 'Related to #42' } : value; };
  f.api.post = f.api.delete = f.api.ready = async () => assert.fail('publication mutation');
  await assert.rejects(f.broker.invoke({ operation: 'publish-progress', runId: 99, attemptId: f.envelope.attemptId, bundle: p.bundle }), { code: 'AUTHORITY_CHANGED' });
  assert.equal(f.pushes(), 0); assert.equal(await f.remoteHead(), f.envelope.startHead);
});

for (const remediation of [false, true]) {
  test(`ordinary ${remediation ? 'native CR' : 'Issue'} glob edit blocks all publication mutation`, async t => {
    const f = await fixture(t, { remediation, instruction: 'Process *.md files.' });
    await f.prepare(f.envelope); await f.commit(); const p = await f.collect(f.envelope);
    const before = await f.remoteHead(); const record = await f.store.get(99);
    const source = remediation ? f.review : f.issue;
    source.body = source.body.replace('Process *.md files.', 'Process .md files.');
    f.api.post = f.api.delete = f.api.ready = async () => assert.fail('publication mutation');
    await assert.rejects(f.broker.invoke({ operation: 'publish-progress', runId: 99,
      attemptId: f.envelope.attemptId, bundle: p.bundle }), { code: 'AUTHORITY_CHANGED' });
    assert.equal(f.pushes(), 0); assert.equal(await f.remoteHead(), before);
    assert.deepEqual(await f.store.get(99), record);
  });
}

test('cosmetic Issue formatting still permits durable publication', async t => {
  const f = await fixture(t); await f.prepare(f.envelope); await f.commit(); const p = await f.collect(f.envelope);
  f.issue.body = f.issue.body.replace('## Execution profile', '### **Execution profile**')
    .replace('## Validation', '### **Validation**').replace('- git diff --check', '* **git diff --check**');
  const r = await f.broker.invoke({ operation: 'publish-progress', runId: 99, attemptId: f.envelope.attemptId, bundle: p.bundle });
  assert.equal(r.publishedHead, p.head); assert.equal(await f.remoteHead(), p.head); assert.equal(f.pushes(), 1);
});
test('a secret introduced and then removed still blocks all publication', async t => {
  const f = await fixture(t); await f.prepare(f.envelope);
  const synthetic = ['gh', 'p_', 'A'.repeat(24)].join('');
  await f.commit('docs/work.md', synthetic); await f.commit('docs/work.md', 'removed\n');
  const p = await f.collect(f.envelope);
  await assert.rejects(f.broker.invoke({ operation: 'publish-progress', runId: 99, attemptId: f.envelope.attemptId, bundle: p.bundle }), { code: 'SECRET_PUBLICATION_SCAN_FAILED' });
  assert.equal(f.pushes(), 0);
});
test('current native review selection is deterministic and a later approval supersedes CR', () => {
  const review = id => ({ id, user: { login: REVIEWER }, state: 'CHANGES_REQUESTED', commit_id: 'a'.repeat(40) });
  assert.equal(currentReview([review(5), review(8), review(4)]).id, 8);
  assert.throws(() => currentReview([review(8), { ...review(9), state: 'APPROVED' }]), { code: 'CURRENT_CHANGE_REQUEST_MISSING' });
  assert.throws(() => currentReview([{ ...review(9), user: { login: WRITER } }]), { code: 'CURRENT_CHANGE_REQUEST_MISSING' });
});
test('missing runtime evidence preserves unknown primary cause and execution', () => {
  const d = causalEvidence(new Error('raw private output'));
  assert.equal(d.observed.child, 'unknown'); assert.equal(d.primaryCause, null); assert.equal(d.classification.source, 'fallback');
  assert.ok(!JSON.stringify(d).includes('raw private'));
});
test('composed remediation preserves historical reviewed head and publishes a new ready head', async t => {
  const f = await fixture(t, { remediation: true });
  const result = await runAttempt({ ...f, journal: memoryStore(), execute: async () => {
    await f.commit(); return { version: VERSION, attemptId: f.envelope.attemptId, child: 'started', containment: 'reaped', result: { status: 'success' } };
  } });
  assert.equal(result.head, await f.remoteHead()); assert.notEqual(result.head, f.review.commit_id);
  assert.equal(f.envelope.startHead, f.review.commit_id); assert.equal(f.comments.length, 1);
});
