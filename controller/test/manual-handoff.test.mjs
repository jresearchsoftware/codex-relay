import test from 'node:test';
import assert from 'node:assert/strict';
import { canonicalAuthorityJson } from '../../contracts/src/github-authority.mjs';
import { compactManualPrompt, renderManualHandoff } from '../src/manual-handoff.mjs';

const repository = 'example-org/sample-project';
const authorityUrl = `https://github.com/${repository}/issues/42`;
const startHead = 'a'.repeat(40);
function envelope(overrides = {}) {
  return { repository, issueNumber: 42, step: 7,
    thread: 'Task 42 — Step 7 — Implement the admitted goal',
    profile: { cliModelId: 'future-model', effort: 'xhigh' }, subagentsAllowed: true,
    branch: 'codex/task-42', startHead, historicalBase: 'b'.repeat(40),
    request: { kind: 'admission', charter_sha256: 'b'.repeat(64),
      authority: { decisions: [{ id: 900, sha256: 'c'.repeat(64), parent: { kind: 'issue', number: 42 } }] } },
    ...overrides };
}
function assertCompact(prompt) {
  assert.ok(prompt.split('\n').length >= 10 && prompt.split('\n').length <= 15, prompt);
  assert.ok(prompt.length < 1700, `${prompt.length} characters`);
  assert.doesNotMatch(prompt, /SHA-256|sha256|Selected trusted Decisions|Progress-bounded|Issue closure policy|Scope:/);
  assert.match(prompt, /Read AGENTS\.md, the current canonical authority and its referenced accepted governance/);
  assert.match(prompt, /Stop on .*mismatch.*protected boundary/);
  assert.match(prompt, /canonical Outcome/);
}

test('fresh v4 handoff keeps launch identity and profile in a compact prompt without authority boilerplate', () => {
  const e = envelope();
  const before = structuredClone(e);
  const prompt = compactManualPrompt(e, authorityUrl);
  assertCompact(prompt);
  assert.ok(prompt.includes('Task: #42; Step: 7'));
  for (const line of [`Repository: ${repository}`, `Canonical authority: ${authorityUrl}`, `Thread: ${e.thread}`,
    'Codex model: future-model', 'Codex effort: xhigh', 'Subagents: On',
    `Admitted branch: codex/task-42; base SHA: ${e.historicalBase}; source PR: none (new source work)`, `Required starting head: ${startHead}`]) assert.ok(prompt.split('\n').includes(line), line);
  assert.match(prompt, /normalize.*before applying the starting-head gate; preserve local work/);
  assert.match(prompt, /submit_manual_outcome/);
  assert.ok(!prompt.includes('#issuecomment-900'));
  assert.deepEqual(e, before);
  assert.equal(compactManualPrompt(e, authorityUrl), prompt);
});

test('CR continuation uses the admitted starting head while the original reviewed head remains outside the copyable prompt', () => {
  const reviewedHead = 'f'.repeat(40);
  const e = envelope({ thread: 'Task 42 — Step 7 — CR-42-001 — Correct the finding',
    request: { kind: 'admission', reviewed_head_sha: reviewedHead } });
  const reviewUrl = `https://github.com/${repository}/pull/43#pullrequestreview-789`;
  const prompt = compactManualPrompt(e, reviewUrl);
  assertCompact(prompt);
  assert.ok(prompt.includes(`Canonical authority: ${reviewUrl}`));
  assert.ok(prompt.includes(e.thread));
  assert.ok(prompt.includes(`Required starting head: ${startHead}`));
  assert.ok(!prompt.includes(reviewedHead));
});

test('non-source manual admission remains compact without inventing a branch or required Git head', () => {
  const e = envelope({ branch: null, startHead: null, historicalBase: null, targetBase: null });
  const prompt = compactManualPrompt(e, authorityUrl);
  assertCompact(prompt);
  assert.doesNotMatch(prompt, /Admitted branch:|Required starting head:|normalize the canonical checkout|null|undefined/);
  assert.ok(prompt.includes(`Repository: ${repository}`));
  assert.match(prompt, /Admitted Git start: none \(source-free manual work\)/);
  assert.match(prompt, /submit_manual_outcome/);
});

test('the complete prompt is open and the complete canonical JSON is folded', () => {
  const hostileText = '東京 <img src=x onerror=alert(1)> `````';
  const e = envelope({ attemptId: 'run-47', thread: `Task 42 — Step 7 — ${hostileText}` });
  const binding = { result: { evidence: Array.from({ length: 100 }, () => hostileText) } };
  const { body, previousBody } = renderManualHandoff(e, authorityUrl, binding);
  const prompt = /^(`{6})text\n([\s\S]+?)\n\1$/m.exec(body);
  const fold = '\n<details>\n<summary>Manual Outcome binding (JSON)</summary>\n\n';
  assert.equal(prompt[2], compactManualPrompt(e, authorityUrl));
  const beforePrompt = body.slice(0, prompt.index);
  assert.ok(beforePrompt.includes('Attempt: run-47'));
  assert.ok(beforePrompt.includes(authorityUrl));
  assert.doesNotMatch(beforePrompt, /<details|<img/);
  const json = body.split(fold)[1].match(/^```json\n([\s\S]+?)\n```\n\n<\/details>$/)[1];
  assert.equal(json, canonicalAuthorityJson(binding));
  assert.deepEqual(JSON.parse(json), binding);
  assert.ok(previousBody.includes('<summary>Copyable Codex prompt</summary>'));
  assert.ok(previousBody.endsWith(`\n\n\`\`\`json\n${json}\n\`\`\``));
});
