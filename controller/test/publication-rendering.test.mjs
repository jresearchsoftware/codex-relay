import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { boundOutcomeBody, workerOutcomeClaims } from '../src/outcome.mjs';
import { admissionBinding, authoritySourceDigest, createAdmissionSnapshot, extractAuthorityRecord, sha256Body } from '../../contracts/src/github-authority.mjs';

const request = JSON.parse(readFileSync(new URL('../../contracts/test/fixtures/github-task-request-v3-input.json', import.meta.url), 'utf8'));
test('new admission Outcome binds protected snapshot instead of manufacturing a public Request', () => {
  const source = { charter: { kind: 'issue-body', id: request.task, parent: request.parent, sha256: request.charter_sha256 },
    decisions: [], change_request: null, compatibility_request: null };
  const authority = { ...source, sha256: authoritySourceDigest(source) };
  const snapshot = createAdmissionSnapshot({ request: { ...request, continuation: { hold: false, next: null } }, authority },
    { step: 2, attempt: 'run-456', runId: '456' });
  const e = { request: snapshot, requestReference: source.charter, step: 2, repository: request.repository,
    issueNumber: request.task, attemptId: snapshot.attempt, runId: 456, startHead: request.starting_head, admission: { warnings: [] } };
  const record = extractAuthorityRecord(boundOutcomeBody(e, 'Recorded worker validation claims.', { head: e.startHead }));
  assert.equal(record.schema_version, '4.0');
  assert.deepEqual(record.authority, authority);
  assert.deepEqual(record.admission, admissionBinding(snapshot));
  assert.equal(record.step, 2);
  assert.ok(!Object.hasOwn(record, 'request'));
});
test('automatic Outcome keeps one canonical machine block and initially visible warnings', () => {
  const e = { request, requestReference: { kind: 'issue-comment', id: 101, parent: request.parent, sha256: 'c'.repeat(64) },
    repository: request.repository, issueNumber: request.task, attemptId: 'run-123', runId: 123,
    startHead: request.starting_head, admission: { warnings: [{ code: 'ISSUE_CLOSURE_POLICY_INVALID' }] } };
  const body = boundOutcomeBody(e, '## Codex Outcome\n\nWorker summary (claim): No source change.',
    { head: e.startHead, status: 'blocked', executionWarnings: ['UNCOMMITTED_WORK_REMAINS'] });
  const record = extractAuthorityRecord(body);
  assert.equal(record.kind, 'outcome');
  assert.equal(record.request.sha256, e.requestReference.sha256);
  assert.equal((body.match(/^```relay-authority$/gm) ?? []).length, 1);
  const visible = body.slice(0, body.indexOf('<details>'));
  assert.match(visible, /Uncommitted checkout work requires reconciliation before acceptance/);
  assert.match(visible, /Unresolved at execution handoff/);
  assert.match(visible, /Native exact\\-head checks and independent acceptance remain separate/);
  assert.equal(sha256Body(body), sha256Body(boundOutcomeBody(e, '## Codex Outcome\n\nWorker summary (claim): No source change.',
    { head: e.startHead, status: 'blocked', executionWarnings: ['UNCOMMITTED_WORK_REMAINS'] })));
});

test('worker claims cannot inject human-facing headings, folded HTML, links or authority fences', () => {
  const claims = workerOutcomeClaims({ summary: 'Claim\n# APPROVED\n</details><script>[safe](javascript:alert(1)) @owner ```relay-authority',
    validation: ['https://bad.invalid www.bad.invalid\n```yaml', 'UNAVAILABLE'] });
  assert.ok(!claims.includes('\n# APPROVED') && !claims.includes('</details>') && !claims.includes('<script>'));
  assert.ok(!claims.includes('[safe](') && !claims.includes('javascript:') && !claims.includes('@owner'));
  assert.ok(!claims.includes('https://bad.invalid') && !claims.includes('www.bad.invalid') && !claims.includes('```'));
  assert.match(claims, /Worker summary \(claim\)/);
  assert.match(claims, /UNAVAILABLE/);
});
