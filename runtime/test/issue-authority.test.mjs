import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { parseIssueAuthority } from '../src/issue-authority.mjs';

const parse = body => parseIssueAuthority(body, { issueNumber: 42, step: 1, targetBaseSha: 'a'.repeat(40) });
const closureWarnings = authority => authority.warnings.filter(warning => warning.field === 'closure');

test('continuation is explicit and keeps its exact task head separate from the base', () => {
  const head = 'b'.repeat(40);
  const a = parse(`Implementation branch: codex/task-42\nImplementation continuation head: \`${head.toUpperCase()}\`\nImplementation pull request: #43`);
  assert.deepEqual(a.continuation, { head, pullRequest: 43 });
  assert.equal(a.baseSha, 'a'.repeat(40));
  assert.equal(a.admission.kind, 'issue-implementation-continuation');
  assert.equal(parse('Implement task.').continuation, undefined);
  assert.equal(parse(`Implementation branch: codex/task-42\nImplementation continuation head: ${head}`).continuation.pullRequest, null);
});

test('continuation never guesses a missing, malformed or conflicting branch/head/PR', () => {
  const head = 'b'.repeat(40);
  const fields = `Implementation branch: codex/task-42\nImplementation continuation head: ${head}`;
  for (const body of [
    `Implementation continuation head: ${head}`, fields.replace('codex/task-42', '../other'),
    fields.replace(head, 'short'), fields.replace(head, ''),
    `${fields}\nImplementation continuation head: ${head}`, `${fields}\nImplementation continuation head: ${'c'.repeat(40)}`,
    `${fields}\nImplementation branch: codex/other`, `${fields}\nImplementation pull request: #0`,
    `${fields}\nImplementation pull request: #43\nImplementation pull request: #43`,
    `${fields}\nImplementation pull request: #43\nImplementation pull request: #44`,
    `Implementation branch: codex/task-42\nImplementation pull request: #43`,
    `${fields}\nImplementation pull request: #9007199254740992`
  ]) assert.throws(() => parse(body), { code: 'ISSUE_CONTINUATION_INVALID' }, body);
});

test('canonical Task producer supplies an explicit valid closure decision', async () => {
  const template = await readFile(new URL('../../.github/ISSUE_TEMPLATE/codex-task.md', import.meta.url), 'utf8');
  const authority = parse(template);
  assert.equal(authority.closurePolicy, 'keep-open');
  assert.equal(authority.closingReference, 'Related to #42');
  assert.deepEqual(closureWarnings(authority), []);
  assert.equal(authority.resolutions.find(resolution => resolution.field === 'closure').source, 'authoring-normalized');
});

test('explicit Issue closure choices determine linkage without default warnings', () => {
  for (const [value, policy, reference] of [
    ['keep-open', 'keep-open', 'Related to #42'],
    ['close-authorized', 'close-authorized', 'Closes #42'],
    ['`CLOSE_AUTHORIZED`.', 'close-authorized', 'Closes #42']
  ]) {
    const authority = parse(`# Task 42\nIssue closure policy: ${value}`);
    assert.equal(authority.closurePolicy, policy);
    assert.equal(authority.closingReference, reference);
    assert.deepEqual(closureWarnings(authority), []);
  }
});

test('missing, malformed and conflicting Issue closure metadata keeps the Issue open visibly', () => {
  for (const metadata of [
    '',
    'Issue closure policy:',
    'Issue closure policy: close',
    'Issue closure policy: close-authorized\nIssue lifecycle: keep-open',
    'Issue closure policy: close-authorized\nIssue closure policy: invalid',
    'Issue closure policy: close-authorized\nIssue #42 remains open',
    'Issue closure policy: close-authorized\nIssue #43 remains open'
  ]) {
    const authority = parse(`# Task 42\n${metadata}`);
    assert.equal(authority.closurePolicy, 'keep-open', metadata);
    assert.equal(authority.closingReference, 'Related to #42', metadata);
    assert.deepEqual(closureWarnings(authority).map(warning => warning.code), ['ISSUE_CLOSURE_POLICY_DEFAULTED'], metadata);
    assert.equal(closureWarnings(authority)[0].resolved, 'keep-open');
  }
});

test('closure field limits cannot hide a conflicting value after an authorized prefix', () => {
  const prefix = Array(64).fill('Issue closure policy: close-authorized').join('\n');
  const bounded = parse(prefix);
  assert.equal(bounded.closurePolicy, 'close-authorized');
  assert.deepEqual(closureWarnings(bounded).map(warning => warning.code), ['ISSUE_CLOSURE_DUPLICATE_EQUIVALENT']);
  for (const tail of ['Issue lifecycle: keep-open', 'Issue closure policy: close-authorized']) {
    const authority = parse(`${prefix}\n${tail}`);
    assert.equal(authority.closurePolicy, 'keep-open');
    assert.equal(authority.closingReference, 'Related to #42');
    assert.deepEqual(closureWarnings(authority).map(warning => warning.code), ['ISSUE_CLOSURE_POLICY_DEFAULTED']);
  }
});
