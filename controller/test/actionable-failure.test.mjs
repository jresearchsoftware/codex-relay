import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { fixture } from './fixture.mjs';
import { createGithubApi } from '../src/github-api.mjs';
import { createLocalWriterAdapter } from '../src/local-writer.mjs';
import { reportRoutingResult } from '../src/entrypoint.mjs';
import { admissionCliFailure, drainAdmission } from '../src/admission-cli.mjs';
import { runAttempt } from '../src/attempt.mjs';
import { causalEvidence, REPOSITORY } from '../src/execution-contract.mjs';
import { serializeWriterFailure } from '../src/privileged-writer-helper.mjs';
import { CONSUMER } from '../../consumer/consumer.mjs';

const canary = 'private-fixture-value-never-published';
const capture = async run => {
  let output = '';
  const write = text => { output += text; };
  return { status: await reportRoutingResult(run, { write, writeError: write, writeAnnotation: write }), output };
};

test('fresh admission reports the retained slot conflict without exposing private evidence', async () => {
  const cause = Object.assign(new Error(canary), {
    code: 'ADMISSION_RESOURCE_EVIDENCE_UNREADABLE',
    details: { resource: 'pool-2', conflictingRunId: 99, repository: 'example-org/docs-review', cause: canary }
  });
  const wire = serializeWriterFailure(cause);
  assert.deepEqual(wire.slotConflict, { slot: 'pool-2', runId: 99, repository: 'example-org/docs-review', state: 'unreadable' });
  const detail = { ...wire, runId: 100, childState: 'not_started' };
  const error = Object.assign(new Error(wire.code), { code: wire.code, details: detail });
  detail.diagnostic = causalEvidence(error, { stage: 'authority' });
  const { status, output } = await capture(async () => { throw error; });
  assert.equal(status, 1);
  assert.match(output, /Slot pool-2.*evidence for example-org\/docs-review run-99 is unreadable/);
  assert.match(output, /Codex child did not start/);
  assert.match(output, /verify the prior run’s retained Writer record, runner journal and checkout/);
  assert.doesNotMatch(output, new RegExp(canary));
});

// Use the real API client and Writer wire serializer in another process. The
// GitHub dependency and installed sudo entrypoint are synthetic in this test.
function preflightProcess(mode, healthyReceipt, tokenResponse) {
  const uri = path => JSON.stringify(new URL(path, import.meta.url).href);
  const script = `
    import { createGithubApi } from ${uri('../src/github-api.mjs')};
    import { http } from ${uri('../src/writer-auth.mjs')};
    import { serializeWriterFailure } from ${uri('../src/privileged-writer-helper.mjs')};
    import { readFileSync } from 'node:fs';
    const request = JSON.parse(readFileSync(0, 'utf8'));
    if (request.operation !== 'preflight') process.exit(21);
    let calls = 0;
    const tokenResponse = ${JSON.stringify(tokenResponse ?? null)};
    if (tokenResponse) globalThis.fetch = async (url, options) => {
      calls++;
      if (url !== 'https://api.github.com/app/installations/12345/access_tokens'
        || options.method !== 'POST' || options.headers.authorization !== 'Bearer ${canary}') process.exit(23);
      if (tokenResponse.network) throw Object.assign(new Error('private network message'), { code: 'ECONNRESET' });
      return new Response(tokenResponse.body ?? 'private native data token=${canary}', tokenResponse);
    };
    const api = createGithubApi({
      wait: async () => {}, random: () => 0,
      token: ${JSON.stringify(canary)},
      fetchImpl: async () => {
        calls++;
        if (${mode === 'recover'} && calls === 2) return Response.json(${JSON.stringify(healthyReceipt)});
        if (${mode === 'timeout'}) throw new DOMException('a private timeout detail', 'TimeoutError');
        if (${mode === 'invalid'}) return new Response('invalid JSON ${canary}', { status: 200 });
        return new Response('token=${canary}\u0020and\u0020private\u0020native\u0020data', { status: ${mode === 'forbidden' ? 403 : 504} });
      }
    });
    try {
      const value = tokenResponse
        ? await http('/app/installations/12345/access_tokens', { method: 'POST', jwt: '${canary}', body: {} })
        : await api.get('/issues/42?hidden=${canary}');
      if (calls !== 2) process.exit(22);
      process.stdout.write(JSON.stringify(value));
    } catch (error) {
      error.details.diagnosticStore = { status: 'stored', mode: 'normal', executionId: 'host-99-fixture' };
      const wire = JSON.stringify(serializeWriterFailure(error));
      if (tokenResponse && (calls !== 1 || wire.includes('${canary}')
        || /private |12345/.test(wire))) process.exit(24);
      process.stderr.write(wire);
      process.exitCode = 1;
    }
  `;
  return createLocalWriterAdapter({ spawnImpl: (_exe, _args, options) => spawn(process.execPath, ['--input-type=module', '-e', script], {
    ...options, env: { ...options.env, RELAY_CONSUMER_CONFIG: process.env.RELAY_CONSUMER_CONFIG }
  }) });
}

for (const [mode, cause, attempts] of [
  ['gateway', /HTTP 504 Gateway Timeout/, 3],
  ['timeout', /GitHub GET \(Issues\) timed out/, 3],
  ['forbidden', /HTTP 403 Forbidden/, 1],
  ['invalid', /HTTP 200 and returned a response that could not be decoded/, 1],
  ['recover', null, 2]
]) test(`ordinary Actions and Outcome after Writer preflight ${mode}`, async t => {
  const f = await fixture(t);
  const healthy = await f.broker.invoke({ operation: 'preflight', runId: f.envelope.runId, attemptId: f.envelope.attemptId });
  const worker = preflightProcess(mode, { repository: REPOSITORY, ...healthy });
  let executions = 0;
  let preflights = 0;
  const run = () => runAttempt({ ...f, broker: { invoke(request) {
    if (request.operation !== 'preflight') return f.broker.invoke(request);
    preflights++;
    return worker.invoke(request);
  } }, execute: async e => {
    executions++;
    return { version: e.version, attemptId: e.attemptId, child: 'started', containment: 'reaped',
      result: { status: 'success', summary: 'Synthetic success', validation: [] } };
  } });
  const { status, output } = await capture(run);
  assert.equal(preflights, 1);
  assert.equal((await f.store.all()).length, 1);
  assert.equal((await f.store.get(f.envelope.runId)).envelope.step, f.envelope.step);
  assert.equal(f.comments.length, 1);
  assert.equal(f.pushes(), 0);
  if (mode === 'recover') {
    assert.equal(status, 0);
    assert.equal(executions, 1);
    assert.match(f.comments[0].body, /IMPLEMENTED_PENDING_FRESH_REVIEW/);
    assert.doesNotMatch(output + f.comments[0].body, /::error|GITHUB_REQUEST_FAILED|HTTP 504/);
    return;
  }
  assert.equal(status, 1);
  assert.equal(executions, 0);
  for (const surface of [output, f.comments[0].body]) {
    assert.match(surface, /Writer preflight.*run-99.*GITHUB_REQUEST_FAILED/);
    assert.match(surface, /GitHub GET \(Issues\)/);
    assert.match(surface, cause);
    assert.match(surface, new RegExp(`${attempts} request attempt`));
    assert.match(surface, /Codex child did not start/);
    assert.match(surface, /Next action: (?:Have the host operator|Verify that the configured GitHub credential)/);
    assert.doesNotMatch(surface, new RegExp(`${canary}|private (?:native|timeout) detail`));
  }
});

for (const [label, response, cause, action, uncertain] of [
  ['429 with provider guidance', { status: 429, headers: { 'retry-after': '120' } },
    /HTTP 429 Too Many Requests and was rate-limited/, /Wait at least 120 seconds/, false],
  ['429 with a delay outside the public range', { status: 429, headers: { 'retry-after': '99999999' } },
    /HTTP 429 Too Many Requests and was rate-limited/, /verify when the GitHub App rate limit lifts/, false],
  ['403 with provider guidance', { status: 403, headers: { 'retry-after': '120' } },
    /HTTP 403 Forbidden and was rate-limited/, /Wait at least 120 seconds/, false],
  ['403 with a secondary limit', { status: 403, body: '{"message":"You have exceeded a secondary rate limit. private native data"}' },
    /HTTP 403 Forbidden and was rate-limited/, /Wait at least 60 seconds/, false],
  ['401', { status: 401 }, /HTTP 401 Unauthorized/, /verify the configured Writer App installation/, false],
  ['403', { status: 403 }, /HTTP 403 Forbidden/, /verify the configured Writer App installation/, false],
  ['504', { status: 504 }, /HTTP 504 Gateway Timeout/, /check GitHub API availability/, true],
  ['network reset', { network: true }, /failed at the network boundary \(ECONNRESET\)/, /check GitHub API availability/, true]
]) test(`Writer token failure reaches Actions and Outcome after ${label}`, async t => {
  const f = await fixture(t);
  const writer = preflightProcess('token', null, response);
  const operations = [];
  const { status, output } = await capture(() => runAttempt({ ...f, broker: { invoke(request) {
    operations.push(request.operation);
    assert.equal(request.operation, 'preflight', 'Outcome delivery would repeat the installation-token POST');
    return writer.invoke(request);
  } }, execute: () => assert.fail('preflight blocked the worker') }));
  assert.equal(status, 1);
  assert.deepEqual(operations, ['preflight']);
  assert.equal((await f.store.all()).length, 1);
  assert.equal(f.pushes(), 0);
  assert.equal(f.comments.length, 0);
  assert.match(output, /deferred target-bound Outcome delivery because it requires another installation token request/);
  const saved = await f.journal.get(f.envelope.runId);
  assert.equal(saved.outcome, null);
  assert.deepEqual(saved.diagnostic.outcomePublication, { status: 'deferred' });
  const replay = await capture(() => runAttempt({ ...f, admissionResumed: true,
    broker: { invoke: () => assert.fail('deferred token failure must not start another Writer operation') },
    execute: () => assert.fail('deferred token failure must not start Codex') }));
  assert.equal(replay.status, 1);
  assert.match(replay.output, cause);
  assert.match(replay.output, /deferred target-bound Outcome delivery/);

  // Exercise Writer's real Outcome composition from the saved diagnostic
  // with the fake authorized GitHub client. The router did not dispatch this.
  await f.broker.invoke({ operation: 'terminal-outcome', runId: f.envelope.runId, attemptId: f.envelope.attemptId,
    status: 'blocked', terminalCode: saved.diagnostic.classification.code, diagnostic: saved.diagnostic });
  assert.equal(f.comments.length, 1);
  for (const surface of [output, f.comments[0].body]) {
    assert.match(surface, /Writer preflight.*run-99.*GITHUB_MUTATION_FAILED/);
    assert.match(surface, /GitHub POST \(Writer installation token\)/);
    assert.match(surface, cause);
    assert.match(surface, /1 request attempt \(0 retries\).*installation token requests are single-attempt/);
    assert.match(surface, /The Codex child did not start/);
    assert.match(surface, action);
    assert.equal(surface.includes('GitHub installation token issuance is unconfirmed.'), uncertain);
    assert.doesNotMatch(surface, new RegExp(`${canary}|private |12345|without a recognized transport cause|original Writer reservation`));
    if (response.headers || response.body) assert.doesNotMatch(surface, /verify the configured Writer App installation/);
  }
});

test('GitHub read honors provider delays, and cancellation during backoff preserves the last HTTP observation', async () => {
  let now = 0;
  const waits = [];
  let requests = 0;
  const api = createGithubApi({ monotonic: () => now, wallTime: () => 1_000_000, random: () => 0,
    wait: async ms => { waits.push(ms); now += ms; },
    fetchImpl: async () => ++requests === 1 ? new Response('', { status: 403, headers: {
      'retry-after': '1', 'x-ratelimit-remaining': '0', 'x-ratelimit-reset': '1002'
    } }) : Response.json({ ok: true }) });
  assert.deepEqual(await api.get('/issues/42'), { ok: true });
  assert.deepEqual(waits, [2250]);

  const long = createGithubApi({ wait: () => assert.fail('provider delay exceeds budget'),
    fetchImpl: async () => new Response('', { status: 429, headers: { 'retry-after': '120' } }) });
  const failed = await capture(() => long.get('/issues/42'));
  assert.equal(failed.status, 1);
  assert.match(failed.output, /HTTP 429.*1 request attempt.*provider-directed wait exceeded.*Check the rate-limit reset/);

  const cancelled = new AbortController();
  const cancel = createGithubApi({ signal: cancelled.signal,
    fetchImpl: async () => new Response('', { status: 504 }),
    wait: async (_ms, _value, { signal }) => { cancelled.abort(); signal.throwIfAborted(); } });
  const stopped = await capture(() => cancel.get('/issues/42'));
  assert.equal(stopped.status, 1);
  assert.match(stopped.output, /HTTP 504.*1 request attempt.*request was cancelled/);
});

for (const accepted of [true, false]) {
  test(`terminal comment lost acknowledgement is ${accepted ? 'reconciled' : 'retained as uncertain'} without a second POST`, async t => {
    const f = await fixture(t);
    const post = f.api.post.bind(f.api);
    let posts = 0;
    let readbacks = 0;
    const list = f.api.list.bind(f.api);
    f.api.list = async path => {
      if (posts > 0 && path.endsWith('/comments')) readbacks++;
      return list(path);
    };
    f.api.post = async (path, body) => {
      const api = createGithubApi({ fetchImpl: async () => {
        posts++;
        if (accepted) await post(path, body);
        return new Response('private write response', { status: 504 });
      } });
      return api.post(path, body);
    };
    const failure = await capture(() => runAttempt({ ...f, execute: () => assert.fail('must stop before child'),
      prepare: async () => { throw Object.assign(new Error('private filesystem cause'), { code: 'CHECKOUT_DIRTY' }); },
      persistFailure: async () => { throw new Error('private recorder failure'); } }));
    assert.equal(failure.status, 1);
    assert.equal(posts, 1);
    assert.ok(readbacks >= 1);
    assert.match(failure.output, /CHECKOUT_DIRTY.*checkout has changes.*diagnostic recorder also failed/);
    assert.doesNotMatch(failure.output, /private (?:write|filesystem|recorder)/);
    if (accepted) {
      assert.equal(f.comments.length, 1);
      assert.match(f.comments[0].body, /CHECKOUT_DIRTY/);
      assert.doesNotMatch(failure.output, /Outcome delivery also failed/);
    } else {
      assert.equal(f.comments.length, 0);
      assert.ok((await f.store.get(99)).commentIntent);
      assert.match(failure.output, /Outcome delivery also failed.*GitHub POST \(Issue comments\).*HTTP 504/);
      assert.match(failure.output, /external effect may remain unverified.*Reconcile the original Writer reservation/);
    }
  });
}

test('accepted Step label and ready removal with lost responses keep one admission', async t => {
  const f = await fixture(t, { labelLaunch: true, deferAdmission: true });
  const post = f.api.post.bind(f.api);
  const remove = f.api.delete.bind(f.api);
  let stepWrites = 0;
  let readyDeletes = 0;
  f.api.post = (path, body) => createGithubApi({ fetchImpl: async () => {
    assert.equal(path, '/issues/42/labels');
    stepWrites++;
    await post(path, body);
    return new Response('', { status: 504 });
  } }).post(path, body);
  f.api.delete = path => createGithubApi({ fetchImpl: async () => {
    assert.equal(path, '/issues/42/labels/codex-ready-auto');
    readyDeletes++;
    await remove(path);
    return new Response('', { status: 504 });
  } }).delete(path);
  const admitted = await f.broker.invoke(f.admissionRequest);
  assert.equal(admitted.envelope.step, f.envelope.step);
  assert.equal(admitted.envelope.attemptId, f.envelope.attemptId);
  assert.equal(stepWrites, 1);
  assert.equal(readyDeletes, 1);
  const rows = await f.store.all();
  assert.equal(rows.length, 1);
  assert.equal(rows[0].stepProjected, true);
  assert.equal(rows[0].readyConsumed, true);
  assert.equal(f.comments.length, 0);
});

test('accepted PR creation reconciles its exact readback without a second POST', async t => {
  const f = await fixture(t);
  const post = f.api.post.bind(f.api);
  const get = f.api.get.bind(f.api);
  f.api.get = async path => {
    const data = await get(path);
    return path === '/pulls/43' ? { ...data, user: { login: CONSUMER.writerApp.expectedActor } } : data;
  };
  let prPosts = 0;
  f.api.post = (path, body) => path !== '/pulls' ? post(path, body)
    : createGithubApi({ fetchImpl: async () => {
      prPosts++;
      await post(path, body);
      return new Response('', { status: 504 });
    } }).post(path, body);
  let children = 0;
  const result = await capture(() => runAttempt({ ...f, execute: async e => {
    children++;
    await f.commit();
    return { version: e.version, attemptId: e.attemptId, child: 'started', containment: 'reaped',
      result: { status: 'success', summary: 'Synthetic success', validation: [] } };
  } }));
  assert.equal(result.status, 0, result.output);
  assert.doesNotMatch(result.output, /::error|GITHUB_REQUEST_FAILED/);
  assert.equal(prPosts, 1);
  assert.equal(children, 1);
  assert.equal(f.pushes(), 1);
  assert.equal(f.comments.length, 1);
  assert.equal((await f.store.get(99)).outcome.prNumber, 43);
});

test('late handoff failure reports the already published candidate and Outcome', async t => {
  const f = await fixture(t);
  const api = createGithubApi({ wait: async () => {}, fetchImpl: async () => new Response('', { status: 504 }) });
  const result = await capture(() => runAttempt({ ...f, broker: { invoke: request =>
    request.operation === 'complete-handoff' ? api.get('/pulls/43') : f.broker.invoke(request) },
    execute: async e => {
      await f.commit();
      return { version: e.version, attemptId: e.attemptId, child: 'started', containment: 'reaped',
        result: { status: 'success', summary: 'Synthetic success', validation: [] } };
    } }));
  assert.equal(result.status, 1);
  const committed = await f.store.get(f.envelope.runId);
  assert.match(result.output, /Writer complete-handoff.*HTTP 504/);
  assert.match(result.output, /The Codex child started/);
  assert.ok(result.output.includes(`Verified published head ${committed.publishedHead}`));
  assert.match(result.output, /Writer confirmed a target-bound Outcome/);
  assert.equal(f.comments.length, 1);
  assert.equal(f.pushes(), 1);
});

test('drain exhaustion yields an actionable protected-gate command result', async () => {
  const operationId = '11111111-1111-4111-8111-111111111111';
  let clock = 0;
  const input = { operationId, timeout: 1 };
  await assert.rejects(drainAdmission(input, {
    snapshot: async () => ({ drained: false, active: [99], unknown: [], private: canary }),
    now: () => clock, wait: async delay => { clock += delay; }, reportProgress() {}
  }), error => {
    const failure = admissionCliFailure(error, 'drain', { status: 'unavailable' });
    assert.match(failure.text, /Relay admission drain failed.*ADMISSION_DRAIN_TIMEOUT.*1 active and 0 unresolved/);
    assert.match(failure.text, /run relay-admission status for the retained operation/);
    assert.doesNotMatch(failure.text + JSON.stringify(failure.receipt), new RegExp(canary));
    assert.deepEqual(failure.receipt.drain, { seconds: 1, active: 1, unknown: 0 });
    return true;
  });
});

test('rate-limited Outcome write stops without an immediate native readback or second write', async t => {
  const f = await fixture(t);
  let writes = 0;
  let subsequentReads = 0;
  const list = f.api.list.bind(f.api);
  f.api.list = async path => {
    if (writes) subsequentReads++;
    return list(path);
  };
  f.api.post = (path, body) => createGithubApi({
    fetchImpl: async () => {
      writes++;
      return new Response('', { status: 429, headers: { 'retry-after': '120' } });
    }
  }).post(path, body);
  const result = await capture(() => runAttempt({ ...f,
    prepare: async () => { throw Object.assign(new Error('retained checkout'), { code: 'CHECKOUT_DIRTY' }); },
    execute: () => assert.fail('preflight blocked the worker') }));
  assert.equal(result.status, 1);
  assert.equal(writes, 1);
  assert.equal(subsequentReads, 0);
  assert.equal(f.comments.length, 0);
  assert.match(result.output, /CHECKOUT_DIRTY.*Outcome delivery also failed.*HTTP 429.*Check the rate-limit reset/);
  assert.doesNotMatch(result.output, /assert|read back the write/);
});

test('an unavailable recorder leaves an applicable action for an unknown startup cause', async () => {
  const error = Object.assign(new Error(canary), { details: {
    routingStage: 'authority', runId: 99, childState: 'not_started', diagnosticRecorderFailed: true
  } });
  const { status, output } = await capture(async () => { throw error; });
  assert.equal(status, 1);
  assert.match(output, /run-99.*The underlying cause was not established.*diagnostic recorder also failed/);
  assert.match(output, /Next action: Have the host operator verify the installed routing entrypoint and consumer configuration/);
  assert.doesNotMatch(output, new RegExp(canary));
});
