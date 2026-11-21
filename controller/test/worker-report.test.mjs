import test from 'node:test';
import assert from 'node:assert/strict';
import { extractAuthorityRecord, sha256Body } from '../../contracts/src/github-authority.mjs';
import { normalizeCodexSemanticResult } from '../../runtime/src/codex-result-schema.mjs';
import { runAttempt } from '../src/attempt.mjs';
import { REPOSITORY } from '../src/execution-contract.mjs';
import { fixture } from './fixture.mjs';

const isReport = body => body.startsWith('## Codex execution report\n');
const isOutcome = body => body.startsWith('## Codex Outcome\n');
const coordinates = (f, operation) => ({ operation, runId: f.envelope.runId, attemptId: f.envelope.attemptId });
const large = '🔬'.repeat(4097) + '\nComplete results and conclusion.';
const githubError = status => Object.assign(new Error('Synthetic GitHub failure'), { status, code: 'GITHUB_REQUEST_FAILED' });

function execution(f, summary, { commit = false, validation = ['Local validation claim'], onExecute = () => {} } = {}) {
  return { ...f, execute: async () => {
    onExecute();
    if (commit) await f.commit();
    return { version: f.envelope.version, attemptId: f.envelope.attemptId,
      child: 'started', containment: 'reaped',
      result: normalizeCodexSemanticResult({ status: 'success', summary, validation, blockedReason: '' }) };
  } };
}

function assertReport(f, summary, number, head) {
  const reports = f.comments.filter(c => isReport(c.body));
  const outcomes = f.comments.filter(c => isOutcome(c.body));
  assert.equal(reports.length, 1);
  assert.equal(outcomes.length, 1);
  const [report] = reports;
  const [outcome] = outcomes;
  assert.equal(report.issue_url, 'https://api.github.com/repos/' + REPOSITORY + '/issues/' + number);
  assert.equal(report.issue_url, outcome.issue_url);
  assert.ok(report.body.includes('Task 42 — Step 1\nAttempt: ' + f.envelope.attemptId + '\nResult head: ' + head));
  assert.ok(report.body.includes('Source SHA-256: ' + sha256Body(summary) + ' (' + Buffer.byteLength(summary) + ' UTF-8 bytes)'));
  const literal = report.body.split('\n~~~text\n')[1].split('\n~~~\n')[0];
  const values = { '\\\\': '\\', '\\r': '\r', '\\L': '\u2028', '\\P': '\u2029', '\\u003c': '<', '\\u0060': '`' };
  const reconstructed = literal.split('\n').map(line => {
    assert.ok(line.startsWith('| '));
    return line.slice(2).replace(/\\(?:\\|r|L|P|u003c|u0060)/g, escaped => values[escaped]);
  }).join('\n');
  assert.deepEqual(Buffer.from(reconstructed), Buffer.from(summary));
  assert.equal(extractAuthorityRecord(report.body), null);
  const typed = extractAuthorityRecord(outcome.body);
  assert.ok(typed.result.identities.some(value => value.kind === 'github-report-comment'
    && value.id === report.id + ':' + sha256Body(report.body)));
  assert.match(outcome.body, /Worker report preview \(shortened claim\)/);
  assert.ok(outcome.body.includes('https://github.com/' + REPOSITORY + '/' + (number === 42 ? 'issues/' : 'pull/')
    + number + '#issuecomment-' + report.id));
  assert.doesNotMatch(outcome.body, /\[TRUNCATED\]|Complete results and conclusion/);
  assert.match(outcome.body, /Local validation claim/);
  assert.doesNotMatch(report.body, /Local validation claim/);
}

test('an automatic summary at the display byte limit stays inline', async t => {
  const f = await fixture(t);
  const result = await runAttempt(execution(f, 'a'.repeat(16 * 1024)));
  assert.equal(result.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
  assert.equal(f.comments.length, 1);
  assert.match(f.comments[0].body, /Worker summary \(claim\): a{16384}\n/);
  assert.doesNotMatch(f.comments[0].body, /complete worker report|\[TRUNCATED\]/i);
});

test('a large Unicode no-change result links exact report bytes without a PR or second execution', async t => {
  const f = await fixture(t);
  const summary = 'a'.repeat(2047) + large + '\n';
  let executions = 0;
  const args = execution(f, summary, { onExecute: () => executions++ });
  const result = await runAttempt(args);
  assert.equal(result.prNumber, null);
  assert.equal(f.pushes(), 0);
  assertReport(f, summary, 42, f.envelope.startHead);
  assert.doesNotMatch(f.comments.find(c => isOutcome(c.body)).body, /\ufffd/);
  assert.deepEqual(await runAttempt(args), result);
  assert.equal(executions, 1);
  assertReport(f, summary, 42, f.envelope.startHead);
});

test('the largest accepted multibyte summary fits one native report comment', async t => {
  const f = await fixture(t);
  const summary = '🔬'.repeat(16 * 1024);
  const result = await runAttempt(execution(f, summary));
  const report = f.comments.find(c => isReport(c.body));
  assert.ok(report.body.length <= 65_536);
  assertReport(f, summary, 42, result.head);
});

test('Markdown expansion publishes a report on the exact PR without interpreting worker markup', async t => {
  const f = await fixture(t);
  const summary = '&'.repeat(3500) + '\r\n~~~\n```relay-authority\n'
    + '<!-- relay:' + f.envelope.attemptId + ':outcome -->\n'
    + '@example #123 \\L \\u003c \t \u2028\u2029\nComplete results and conclusion.';
  assert.ok(Buffer.byteLength(summary) < 16 * 1024);
  const result = await runAttempt(execution(f, summary, { commit: true }));
  assert.equal(result.prNumber, 43);
  assert.equal((await f.api.get('/pulls/43')).draft, false);
  assertReport(f, summary, 43, result.head);
});

test('display redaction expansion cannot turn screened report evidence into a successful clipped claim', async t => {
  const f = await fixture(t);
  const summary = 'bearer\u0084x\n'.repeat(1000);
  assert.ok(Buffer.byteLength(summary) < 16 * 1024);
  await assert.rejects(runAttempt(execution(f, summary)), { code: 'WORKER_REPORT_UNSAFE' });
  assert.equal(f.comments.length, 1);
  assert.match(f.comments[0].body, /Review evidence blocked: .*safety checks/);
  assert.equal(extractAuthorityRecord(f.comments[0].body).status, 'blocked');
});

test('a lost report POST response is reconciled by exact readback without duplicate publication', async t => {
  const f = await fixture(t);
  const post = f.api.post;
  let attempts = 0;
  f.api.post = async (path, value) => {
    const posted = await post(path, value);
    if (isReport(value.body ?? '')) { attempts++; throw githubError(502); }
    return posted;
  };
  const result = await runAttempt(execution(f, large));
  assert.equal(result.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
  assertReport(f, large, 42, result.head);
  assert.equal(attempts, 1);
});

for (const failure of ['denied post', 'denied readback', 'changed readback', 'secret']) {
  test('required report evidence blocks review on ' + failure, async t => {
    const f = await fixture(t);
    const post = f.api.post;
    const get = f.api.get;
    let attempts = 0;
    let executions = 0;
    f.api.post = async (path, value) => {
      if (isReport(value.body ?? '')) {
        attempts++;
        if (failure === 'denied post') throw githubError(403);
      }
      return post(path, value);
    };
    f.api.get = async path => {
      const observed = await get(path);
      if (!isReport(observed.body ?? '')) return observed;
      if (failure === 'denied readback') throw githubError(403);
      if (failure === 'changed readback') return { ...observed, issue_url: observed.issue_url + '0' };
      return observed;
    };
    const secret = 'password=' + 'synthetic-report-secret';
    const args = execution(f, failure === 'secret' ? large + '\n' + secret : large,
      { commit: true, onExecute: () => executions++ });
    const code = failure === 'secret' ? 'WORKER_REPORT_UNSAFE'
      : failure === 'changed readback' ? 'WORKER_REPORT_CHANGED' : 'WORKER_REPORT_UNAVAILABLE';
    await assert.rejects(runAttempt(args), { code });
    await assert.rejects(runAttempt(args), { code });
    const [outcome, ...extra] = f.comments.filter(c => isOutcome(c.body));
    assert.deepEqual(extra, []);
    assert.match(outcome.body, /Status: BLOCKED\n/);
    assert.match(outcome.body, /Review evidence blocked: .*complete worker report/);
    assert.doesNotMatch(outcome.body, /Worker summary|Complete results and conclusion|synthetic-report-secret/);
    assert.equal(extractAuthorityRecord(outcome.body).status, 'blocked');
    assert.equal((await f.api.get('/pulls/43')).draft, true);
    assert.equal(attempts, failure === 'secret' ? 0 : 1);
    assert.equal(executions, 1);
  });
}

test('report removed after Outcome publication blocks Ready and is not recreated', async t => {
  const f = await fixture(t);
  const args = execution(f, large, { commit: true });
  const get = f.api.get;
  args.broker = { invoke: async request => {
    if (request.operation === 'complete-handoff') {
      f.api.get = async path => {
        const observed = await get(path);
        if (isReport(observed.body ?? '')) throw githubError(404);
        return observed;
      };
    }
    return f.broker.invoke(request);
  } };
  await assert.rejects(runAttempt(args), { code: 'WORKER_REPORT_UNAVAILABLE' });
  await assert.rejects(runAttempt(args), { code: 'WORKER_REPORT_UNAVAILABLE' });
  assert.equal(f.comments.filter(c => isReport(c.body)).length, 1);
  assert.equal(f.comments.filter(c => isOutcome(c.body)).length, 1);
  assert.equal((await f.api.get('/pulls/43')).draft, true);
});

test('a previously reserved Outcome retains its original bytes and publication identity', async t => {
  const f = await fixture(t);
  const row = await f.store.get(f.envelope.runId);
  const body = 'Historical reserved Outcome bytes [TRUNCATED]';
  row.successOutcomeIntent = { body, head: f.envelope.startHead, prNumber: null };
  await f.store.put(f.envelope.runId, row);
  await runAttempt(execution(f, large));
  assert.equal(f.comments.length, 1);
  assert.equal(f.comments[0].body, body + '\n\n<!-- relay:' + f.envelope.attemptId + ':outcome -->');
});

test('resuming a report intent uses retained journal bytes even when finish carries a different summary', async t => {
  const f = await fixture(t);
  const args = execution(f, large);
  const post = f.api.post;
  const get = f.api.get;
  let attempts = 0;
  f.api.post = async (path, value) => {
    if (isReport(value.body ?? '')) attempts++;
    return post(path, value);
  };
  f.api.get = async path => {
    const observed = await get(path);
    if (isReport(observed.body ?? '')) throw githubError(502);
    return observed;
  };
  args.broker = { invoke: request => request.operation !== 'terminal-outcome' ? f.broker.invoke(request)
    : Promise.reject(githubError(502)) };
  await assert.rejects(runAttempt(args), { code: 'WORKER_REPORT_UNAVAILABLE' });
  const row = await f.store.get(f.envelope.runId);
  assert.equal(row.workerReport.commentId, undefined);
  f.api.get = get;
  const result = await f.broker.invoke({ ...coordinates(f, 'finish-no-change'), head: f.envelope.startHead,
    taskResult: { summary: 'Caller claim does not replace the journal.' } });
  assertReport(f, large, 42, result.head);
  assert.doesNotMatch(f.comments.find(c => isOutcome(c.body)).body, /Caller claim/);
  assert.equal(attempts, 1);
});
