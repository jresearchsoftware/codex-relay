import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { parseIssueAuthority } from '../src/issue-authority.mjs';

const parse = body => parseIssueAuthority(body, { issueNumber: 42, step: 1, targetBaseSha: 'a'.repeat(40) });
const closureWarnings = authority => authority.warnings.filter(warning => warning.field === 'closure');

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
