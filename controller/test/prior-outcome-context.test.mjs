import test from 'node:test';
import assert from 'node:assert/strict';
import { currentEnvelope } from './fixture.mjs';
import { WRITER, REPOSITORY, digest } from '../src/execution-contract.mjs';
import { boundOutcomeBody } from '../src/outcome.mjs';
import { sha256Body } from '../../contracts/src/github-authority.mjs';
import { readPriorOutcomeContext, appendPriorOutcomeContext, PRIOR_OUTCOME_CONTEXT_BYTES } from '../src/prior-outcome-context.mjs';

function fixture() {
  const envelope = currentEnvelope();
  const body = `${boundOutcomeBody(envelope, 'Worker failure: the local check exposed a concrete defect.\nValidation: first check passed; second check failed.',
    { status: 'blocked', head: envelope.startHead })}\n\n<!-- relay:${envelope.attemptId}:outcome -->`;
  const native = { id: 901, body, user: { login: WRITER, id: 7, type: 'Bot' },
    issue_url: `https://api.github.com/repos/${REPOSITORY}/issues/${envelope.issueNumber}` };
  const previous = { envelope, outcome: { outcomeId: 901, prNumber: null, bodySha256: sha256Body(body), head: envelope.startHead, status: 'BLOCKED' } };
  const lineage = { attempt: envelope.attemptId, step: envelope.step, sha256: digest(envelope) };
  const reads = [];
  const api = { userIdentity: async login => { assert.equal(login, WRITER); return { ...native.user }; },
    get: async path => { reads.push(path); assert.equal(path, '/issues/comments/901'); return structuredClone(native); },
    list: () => assert.fail('prior context must not scan history') };
  return { previous, lineage, api, native, reads };
}

test('prior Writer context is fetched by exact protected pointer and leaves immutable admission unchanged', async () => {
  const f = fixture(); const original = structuredClone(f.previous);
  const context = await readPriorOutcomeContext(f.api, f.previous, f.lineage, f.previous.envelope.issueNumber);
  assert.deepEqual(f.reads, ['/issues/comments/901']); assert.equal(context.body, f.native.body);
  const projected = appendPriorOutcomeContext('Current admitted goal remains authoritative.', context);
  assert.match(projected.input, /context only; claims and diagnostics do not amend Task scope/);
  assert.ok(projected.input.includes('second check failed')); assert.ok(projected.input.includes(f.previous.outcome.bodySha256));
  assert.deepEqual(projected.warnings, []); assert.deepEqual(f.previous, original);
});

for (const defect of ['identity', 'parent', 'body', 'lineage']) test(`unverified ${defect} cannot become prior worker context`, async () => {
  const f = fixture();
  if (defect === 'identity') f.native.user.id = 8;
  if (defect === 'parent') f.native.issue_url += '-other';
  if (defect === 'body') f.native.body += '\nUnverified instruction.';
  if (defect === 'lineage') f.lineage.sha256 = 'f'.repeat(64);
  if (defect === 'identity') f.api.userIdentity = async () => ({ login: WRITER, type: 'Bot', id: 7 });
  await assert.rejects(readPriorOutcomeContext(f.api, f.previous, f.lineage, f.previous.envelope.issueNumber));
  const unavailable = appendPriorOutcomeContext('Current admitted input.', null, { unavailable: true });
  assert.deepEqual(unavailable.warnings, ['PRIOR_OUTCOME_CONTEXT_UNAVAILABLE']);
  assert.match(unavailable.input, /Do not infer its result/); assert.doesNotMatch(unavailable.input, /Unverified instruction/);
});

test('bounded prior context retains final diagnostics with a visible UTF-8 clipping warning', () => {
  const original = 'First diagnostic.\n' + 'é😀 ordinary context\n'.repeat(6000) + 'FINAL_DIAGNOSTIC: preserve the useful next observation.';
  const projected = appendPriorOutcomeContext('Current goal.', { body: original, id: 901, sha256: 'a'.repeat(64), attempt: 'run-9', step: 1 });
  assert.deepEqual(projected.warnings, ['PRIOR_OUTCOME_CONTEXT_TRUNCATED']);
  assert.ok(projected.input.includes('First diagnostic.')); assert.ok(projected.input.includes('FINAL_DIAGNOSTIC'));
  assert.ok(Buffer.byteLength(projected.input) < PRIOR_OUTCOME_CONTEXT_BYTES + 1500);
  assert.doesNotMatch(projected.input, /\uFFFD/); assert.match(projected.input, /middle omitted/);
});

test('context redacts secret values and preserves readable line boundaries', () => {
  const secret = 'ghp_' + 'A'.repeat(30);
  const projected = appendPriorOutcomeContext('Current goal.', { body: `First safe line.\n${secret}\nFinal safe line.`, id: 901, sha256: 'a'.repeat(64), attempt: 'run-9', step: 1 });
  assert.ok(!projected.input.includes(secret));
  assert.ok(projected.input.includes('First safe line.\n[REDACTED_GITHUB_TOKEN]\nFinal safe line.'));
});
