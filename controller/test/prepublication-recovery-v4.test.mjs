import test from 'node:test';
import assert from 'node:assert/strict';
import { CONSUMER, CONSUMER_DIGEST } from '../../consumer/consumer.mjs';
import { readAuthority } from '../src/live-authority.mjs';
import { prepublicationState, recoverPrepublication } from '../src/prepublication-recovery.mjs';
import { dispatchRunName } from '../src/launch-metadata.mjs';
import { REPOSITORY, OWNER, WRITER, REVIEWER, VERSION, digest } from '../src/execution-contract.mjs';
import { admissionBinding, authoritySourceDigest, canonicalAuthorityJson, renderAuthorityRecord, sha256Body } from '../../contracts/src/github-authority.mjs';

const copy = value => structuredClone(value);
const base = 'a'.repeat(40), head = 'b'.repeat(40);
async function fixture() {
  const issue = { number: 42, title: 'Task 42 — bounded work', state: 'open', user: { login: OWNER }, labels: [],
    body: 'Authority model: github-native-v1\nIssue closure policy: keep-open\n\nImplement bounded work.' };
  const writer = { login: WRITER, id: 57, type: 'Bot' };
  const reviewer = { login: REVIEWER, id: 58, type: 'Bot' };
  let outcome;
  const reads = [];
  const api = {
    userIdentity: async login => { assert.ok([WRITER, REVIEWER].includes(login)); return copy(login === WRITER ? writer : reviewer); },
    get: async path => {
      reads.push(path);
      if (path === '/issues/42') return copy(issue);
      if (path === '/issues/comments/701') return copy(outcome);
      assert.fail(`Unexpected GET ${path}`);
    },
    list: async path => {
      if (path === '/issues/42/comments' || path.startsWith('/pulls?')) return [];
      assert.fail(`Unexpected list ${path}`);
    }
  };
  const admitted = await readAuthority(api, 'issue', 42, { streamlined: true, route: 'auto', runId: 99, step: 2, targetBase: base });
  const e = { ...admitted, repository: REPOSITORY, version: VERSION, target: 'issue', number: 42, route: 'auto',
    runId: 99, attemptId: 'run-99', step: 2, reviewId: null, targetBase: base, consumerDigest: CONSUMER_DIGEST };
  const run = { id: 99, event: 'workflow_dispatch', head_branch: CONSUMER.baseBranch, display_title: dispatchRunName(e),
    repository: { full_name: REPOSITORY }, actor: { login: OWNER }, status: 'completed', path: CONSUMER.routingWorkflow,
    run_attempt: 1, updated_at: '2026-09-04T12:02:00Z' };
  api.getRun = async () => copy(run);
  const typed = { schema_version: '4.0', kind: 'outcome', repository: REPOSITORY, task: 42,
    parent: { kind: 'issue', number: 42 }, charter_sha256: e.request.charter_sha256, step: 2,
    authority: e.request.authority, admission: admissionBinding(e.request), attempt: 'run-99', status: 'blocked',
    result: { kind: 'no-change', revision: base, identities: [{ kind: 'github-actions-run', id: '99' }] },
    summary: 'Collection stopped before publication.', warnings: [], limitations: ['No candidate publication occurred.'] };
  const body = value => `${renderAuthorityRecord(value)}\n\n<!-- relay:run-99:outcome -->`;
  outcome = { id: 701, body: body(typed), user: copy(writer),
    issue_url: `https://api.github.com/repos/${REPOSITORY}/issues/42`,
    created_at: '2026-09-04T12:01:30Z', updated_at: '2026-09-04T12:01:30Z' };
  const r = { envelope: e, outcome: { status: 'BLOCKED', head: null, prNumber: null, outcomeId: 701, bodySha256: sha256Body(outcome.body) },
    controllerLifecycle: { version: 1, status: 'complete', child: 'started', containment: 'reaped' } };
  const saved = { version: VERSION, envelope: copy(e), execution: { reserved: true, returned: true, child: 'started',
    containment: 'reaped', result: { status: 'success' } }, outcome: copy(r.outcome),
    diagnostic: { classification: { stage: 'progress' }, lastSuccessfulBoundary: 'contained-execution',
      observed: { child: 'started' }, containment: 'reaped', orchestration: 'FAILED', durable: { publishedHead: null } } };
  const journal = { get: async id => { assert.equal(id, 99); return copy(saved); } };
  const state = () => prepublicationState({ api, journal, record: r, head });
  const rebindBody = () => { r.outcome.bodySha256 = sha256Body(outcome.body); saved.outcome = copy(r.outcome); };
  return { api, journal, r, saved, outcome, typed, body, state, rebindBody, issue, run, reads };
}

test('v4 prepublication inspection binds exact authority/admission and leaves all terminal evidence unchanged', async () => {
  const f = await fixture(); const prior = copy({ r: f.r, saved: f.saved, outcome: f.outcome });
  const value = await f.state();
  assert.deepEqual(value.binding.authority, f.r.envelope.request.authority);
  assert.deepEqual(value.binding.admission, admissionBinding(f.r.envelope.request));
  assert.equal(Object.hasOwn(value.binding, 'request'), false);
  assert.equal(value.binding.terminal.bodySha256, sha256Body(f.outcome.body));
  assert.equal(value.binding.terminal.journalDigest, digest(f.saved));
  assert.deepEqual({ r: f.r, saved: f.saved, outcome: f.outcome }, prior);
  assert.ok(f.reads.includes('/issues/42'));
});

test('human renderer header cannot bypass terminal digest, Writer identity or canonical target binding', async () => {
  for (const mutate of [
    f => { f.outcome.body = f.outcome.body.replace('Collection stopped', 'Collection allegedly passed'); },
    f => { f.outcome.user.id++; },
    f => { f.outcome.user.type = 'User'; },
    f => { f.outcome.issue_url = `https://api.github.com/repos/${REPOSITORY}/issues/43`; },
    f => { delete f.r.outcome.bodySha256; },
    f => { f.outcome.body = f.outcome.body.replace('relay:run-99:outcome', 'relay:run-100:outcome'); }
  ]) {
    const f = await fixture(); mutate(f);
    await assert.rejects(f.state(), { code: 'RECOVERY_TERMINAL_OUTCOME_CHANGED' });
  }
});

test('even a body with matching protected digest must bind the admitted v4 Step, attempt and authority', async () => {
  for (const mutate of [
    value => { value.authority.charter.id = 43; value.authority.sha256 = authoritySourceDigest(value.authority); },
    value => { value.admission.sha256 = 'c'.repeat(64); },
    value => { value.parent.number = 43; },
    value => { value.step = 3; value.admission.step = 3; },
    value => { value.attempt = 'run-100'; value.admission.attempt = 'run-100'; }
  ]) {
    const f = await fixture(); const value = copy(f.typed); mutate(value);
    // Serialize without producer validation so the parser sees hostile native bytes.
    f.outcome.body = f.body(f.typed).replace(/```relay-authority\n[\s\S]*?\n```/, `\`\`\`relay-authority\n${canonicalAuthorityJson(value)}\n\`\`\``);
    f.rebindBody();
    await assert.rejects(f.state(), { code: 'RECOVERY_TERMINAL_OUTCOME_CHANGED' });
  }
});

test('changed original run, source authority or retained journal stops v4 inspection before recovery mutation', async () => {
  for (const [mutate, code] of [
    [f => { f.run.run_attempt = 2; }, 'RECOVERY_ORIGINAL_RUN_NOT_COMPLETED'],
    [f => { f.issue.body += '\nChanged live authority.'; }, 'AUTHORITY_CHANGED'],
    [f => { f.saved.execution.containment = 'unknown'; }, 'RECOVERY_EXECUTION_NOT_PROVEN'],
    [f => { f.saved.collection = { head }; }, 'RECOVERY_TERMINAL_STATE_NOT_PROVEN']
  ]) {
    const f = await fixture(); mutate(f);
    await assert.rejects(f.state(), { code });
  }
});

test('v4 inspection alone never authorizes collection or publication', async () => {
  const f = await fixture();
  await assert.rejects(recoverPrepublication({ api: f.api, journal: f.journal, record: f.r,
    request: { head }, collect: () => assert.fail('No owner authorization'),
    publisher: { inspect: () => assert.fail('No owner authorization') },
    store: { put: () => assert.fail('No owner authorization') } }), { code: 'RECOVERY_OWNER_AUTHORIZATION_REQUIRED' });
  assert.equal(f.r.prepublicationRecovery, undefined);
});
