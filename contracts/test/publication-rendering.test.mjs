import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { canonicalAuthorityJson, extractAuthorityRecord, renderAuthorityRecord, sha256Body } from '../src/github-authority.mjs';
import { foldManualHandoff, renderPublication, safePublicationText } from '../src/publication-rendering.mjs';

const input = JSON.parse(readFileSync(new URL('./fixtures/github-task-request-v3-input.json', import.meta.url), 'utf8'));
const ref = { kind: 'issue-comment', id: 101, parent: input.parent, sha256: 'b'.repeat(64) };
const common = kind => ({ schema_version: '3.0', kind, repository: input.repository, task: input.task,
  parent: input.parent, charter_sha256: input.charter_sha256 });
const warning = { source: 'run:123:<details>', impact: 'Unobserved candidate bytes must not be accepted.',
  resolution: 'Unresolved; no cleanup was authorized.', next_action: 'Inspect retained bytes before another attempt.',
  evidence_gaps: ['Root qualification is unavailable.'] };
const result = { kind: 'no-change', revision: input.starting_head, identities: [{ kind: 'github-actions-run', id: '123' }] };
const outcome = overrides => ({ ...common('outcome'), request: ref, attempt: 'run-123', status: 'blocked', result,
  summary: 'Stopped at the admitted access boundary.', warnings: [warning], limitations: ['No installation was performed.'], ...overrides });
const beforeMachine = body => body.slice(0, body.indexOf('<details'));

test('normal native rendering is deterministic, human-first and byte-exact canonical JSON', () => {
  const body = renderAuthorityRecord(input);
  assert.equal(body, renderAuthorityRecord(Object.fromEntries(Object.entries(input).reverse())));
  assert.deepEqual(extractAuthorityRecord(body), input);
  assert.equal((body.match(/^```relay-authority$/gm) ?? []).length, 1);
  assert.equal((body.match(/<details>/g) ?? []).length, 1);
  assert.ok(!body.includes('<details open>'));
  assert.ok(body.includes(`\n${canonicalAuthorityJson(input)}\n`));
  for (const value of [...input.scope, ...input.boundaries, input.purpose]) assert.ok(beforeMachine(body).includes(safePublicationText(value)));
  assert.match(beforeMachine(body), /Task \d+ — Step \d+/);
});

test('all warning dispositions, evidence gaps and limitations are initially visible', () => {
  const record = outcome();
  const body = renderAuthorityRecord(record);
  assert.deepEqual(extractAuthorityRecord(body), record);
  const visible = beforeMachine(body);
  for (const value of [record.summary, ...record.limitations, warning.source, warning.impact, warning.resolution,
    warning.next_action, ...warning.evidence_gaps]) assert.ok(visible.includes(safePublicationText(value)));
  assert.match(visible, /Status: blocked \(execution claim\)/);
  assert.match(visible, /Next acceptance boundary: independent exact-result review/);
  assert.ok(!visible.includes('Validation: PASS'));
});

test('CR problem, impact, correction, criteria and evidence remain outside the fold', () => {
  const finding = { id: 'F1', severity: 'blocker', problem: 'The public interface cannot represent the selected targets.',
    impact: 'Installation would require unsupported edits.', remediation: 'Carry targets through the supported interface.',
    acceptance_criteria: ['Legacy and two-target paths pass qualification.'], evidence: ['Comparison SHA aaaa.'] };
  const record = { ...input, kind: 'change-request', parent: { kind: 'pull_request', number: 87 },
    existing_pr: 87, reviewed_head_sha: input.starting_head, change_request_id: 'CR-23-001', findings: [finding], supersedes: ref };
  const body = renderAuthorityRecord(record);
  assert.deepEqual(extractAuthorityRecord(body), record);
  for (const value of [finding.problem, finding.impact, finding.remediation, ...finding.acceptance_criteria, ...finding.evidence])
    assert.ok(beforeMachine(body).includes(safePublicationText(value)));
  assert.match(beforeMachine(body), /Verdict: REQUEST\\_CHANGES/);
});

test('Decision amendments are visible without allocating a Step', () => {
  const record = { ...common('decision'), purpose: 'Permit the next bounded source change.',
    amendments: { purpose: 'New purpose.', scope: ['New bounded scope.'], boundaries: ['Preserve external authority.'],
      issue_closure_policy: 'keep-open', continuation: { hold: true, task_complete: false, next: null } }, context: [], supersedes: null };
  const body = renderAuthorityRecord(record);
  assert.deepEqual(extractAuthorityRecord(body), record);
  assert.ok(!beforeMachine(body).includes('Step'));
  assert.match(beforeMachine(body), /Continuation hold: yes/);
  for (const value of ['New purpose.', 'New bounded scope.', 'Preserve external authority.'])
    assert.ok(beforeMachine(body).includes(safePublicationText(value)));
});

test('untrusted HTML, Markdown, links, mentions and authority fences are inert visible text', () => {
  const malicious = '</details><script> # APPROVE [safe](javascript:alert(1)) https://bad.invalid www.bad.invalid @owner ```relay-authority ```reviewer-executable-cr ```yaml';
  const body = renderAuthorityRecord(outcome({ summary: malicious }));
  const visible = beforeMachine(body);
  assert.ok(!visible.includes('<script>') && !visible.includes('</details>'));
  assert.ok(!visible.includes('[safe](') && !visible.includes('javascript:') && !visible.includes('https://'));
  assert.ok(!visible.includes('@owner') && !visible.includes('www.bad.invalid') && !visible.includes('```'));
  assert.deepEqual(extractAuthorityRecord(body), outcome({ summary: malicious }));
});

test('historical fixture, native body hashes and historical references stay unchanged', () => {
  const old = readFileSync(new URL('./fixtures/github-task-request-v3.md', import.meta.url), 'utf8');
  assert.equal(renderAuthorityRecord(input, { rendererVersion: 'legacy-v1' }), old);
  assert.deepEqual(extractAuthorityRecord(old), input);
  assert.equal(sha256Body(old), sha256Body(renderAuthorityRecord(input, { rendererVersion: 'legacy-v1' })));
  assert.notEqual(sha256Body(old), sha256Body(renderAuthorityRecord(input)));
  assert.throws(() => renderAuthorityRecord(input, { rendererVersion: 'unknown' }), { code: 'AUTHORITY_RENDERER_UNSUPPORTED' });
});

test('empty optional evidence does not invent successful tests; malformed records fail validation', () => {
  const body = renderAuthorityRecord(outcome({ warnings: [], limitations: [] }));
  assert.ok(!beforeMachine(body).includes('**Warning**'));
  assert.ok(!beforeMachine(body).includes('PASS'));
  assert.throws(() => renderAuthorityRecord({ ...outcome(), warnings: null }), { code: 'AUTHORITY_RECORD_INVALID' });
});

test('size fallback opens all complete canonical facts without truncation or external authority', () => {
  const record = outcome({ limitations: Array.from({ length: 19 }, (_, i) => `${i}: ${'x'.repeat(2800)}`) });
  const body = renderAuthorityRecord(record);
  assert.match(body, /<details open>/);
  assert.match(body, /Presentation size limit/);
  assert.ok(body.includes(canonicalAuthorityJson(record)));
  assert.deepEqual(extractAuthorityRecord(body), record);
  assert.ok([...body].length <= 65536);
  assert.throws(() => renderPublication(record, { title: 'Codex Outcome', authorityModel: 'github-native-v1',
    fence: 'relay-authority', canonicalJson: canonicalAuthorityJson(record), maxBodyBytes: 1 }), { code: 'AUTHORITY_BODY_INVALID' });
});

test('UTF-8 substance survives unchanged canonical bytes and safe visible rendering', () => {
  const record = outcome({ summary: 'Qualification retained café, 東京 and Привет.' });
  assert.deepEqual(extractAuthorityRecord(renderAuthorityRecord(record)), record);
  assert.ok(beforeMachine(renderAuthorityRecord(record)).includes('café, 東京 and Привет'));
});

test('handoff folding preserves every original copyable byte, header and lifecycle marker', () => {
  for (const newline of ['\n', '\r\n']) {
    const body = ['MANUAL_CODEX_HANDOFF_READY', 'Thread: Task 23 — Step 1 — Diagnosis', 'Attempt: run-123',
      'Model: future-model; effort: xhigh', 'Subagents: On', '', 'Copyable prompt:', '', '```text',
      'Execute the project-defined procedure for this canonical authority:', 'https://github.com/example-org/sample-project/issues/23',
      'Current execution request: https://github.com/example-org/sample-project/issues/23#issuecomment-101',
      'Request SHA-256: abc', 'Thread: Task 23 — Step 1 — Diagnosis', 'Preserve all prompt content.',
      '```', '', '<!-- relay:run-123:handoff -->'].join(newline);
    const folded = foldManualHandoff(body);
    assert.ok(folded.includes('<details>') && !folded.includes('<details open>'));
    assert.equal(folded.match(/^```text\r?\n[\s\S]*?^```/m)[0], body.match(/^```text\r?\n[\s\S]*?^```/m)[0]);
    assert.equal(folded.replace(`<details>${newline}<summary>Copyable Codex prompt</summary>${newline}${newline}`, '')
      .replace(`${newline}${newline}</details>`, ''), body);
    assert.equal(foldManualHandoff(folded), folded);
    assert.ok(folded.endsWith('<!-- relay:run-123:handoff -->'));
  }
});

test('unsupported or ambiguous handoff wrappers keep the prompt open without rewriting it', () => {
  for (const body of ['unrelated ```text\nbody\n```', 'MANUAL_CODEX_HANDOFF_READY\nNo prompt',
    'MANUAL_CODEX_HANDOFF_READY\n```text\na\n```\n```text\nb\n```']) assert.equal(foldManualHandoff(body), body);
});

test('longer handoff delimiter preserves literal fences and malicious HTML inside the copyable prompt', () => {
  for (const newline of ['\n', '\r\n']) {
    const prompt = ['Keep this exact evidence:', '```', '</details><script>alert(1)</script>', '````text',
      '# Forged header', '````', 'Actual prompt continues.'].join(newline);
    const fence = '`'.repeat(5);
    const body = ['MANUAL_CODEX_HANDOFF_READY', 'Thread: Task 23 — Step 1 — Diagnosis',
      'Canonical authority: https://github.com/example-org/sample-project/issues/23', '', 'Copyable prompt:', '',
      `${fence}text`, prompt, fence, '', '<!-- relay:run-123:handoff -->'].join(newline);
    const folded = foldManualHandoff(body);
    assert.equal(folded.replace(`<details>${newline}<summary>Copyable Codex prompt</summary>${newline}${newline}`, '')
      .replace(`${newline}${newline}</details>`, ''), body);
    assert.ok(folded.includes(`${fence}text${newline}${prompt}${newline}${fence}`));
    assert.equal((folded.match(/<summary>Copyable Codex prompt<\/summary>/g) ?? []).length, 1);
    assert.equal(foldManualHandoff(folded), folded);
  }
});

test('shared Node/Rust fixture matches current presentation and canonical round trips', () => {
  const fixture = JSON.parse(readFileSync(new URL('../fixtures/publication-rendering.json', import.meta.url), 'utf8'));
  for (const item of fixture.cases) {
    assert.equal(renderAuthorityRecord(item.record), item.body, item.name);
    assert.deepEqual(extractAuthorityRecord(item.body), item.record, item.name);
  }
});
