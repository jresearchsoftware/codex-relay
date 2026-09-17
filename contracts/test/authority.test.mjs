import test from 'node:test';
import assert from 'node:assert/strict';
import { CONSUMER } from '../../consumer/consumer.mjs';
import { extractRemediationContract, validateRemediationContract } from '../src/contracts.mjs';
const head = 'a'.repeat(40);
const fields = [
  'Change Request ID: CR-42-001', 'Target repository: example-org/sample-project',
  'Target pull request: #43', `Reviewed head SHA: ${head}`, `Required starting head: ${head}`,
  'Thread name: Task 42 - Step 2 - CR-42-001 simplify', 'Codex model: gpt-5.6-luna',
  'Codex reasoning effort: high', 'Subagents: Off'
];
const source = '# Task 42\nCorrect the documentation.';
test('remediation passes unknown safe profiles and effort independently of subagents', () => {
  const body = [...fields, '## Required validation', 'git diff', '### F1 content'].join('\n');
  const contract = extractRemediationContract(body, { canonicalIssueBody: source });
  for (const codex_effort of ['low', 'medium', 'high', 'xhigh', 'max', 'future-effort']) {
    for (const subagents_allowed of [false, true]) {
      const c = { ...contract, codex_model: 'future-model', codex_effort, subagents_allowed };
      const resolved = validateRemediationContract(c, { pullRequest: 43, reviewedHeadSha: head });
      assert.equal(resolved.codex_model, 'future-model');
      assert.equal(resolved.codex_effort, codex_effort);
      assert.equal(resolved.subagents_allowed, subagents_allowed);
      assert.ok(!('allowed_paths' in resolved));
    }
  }
  for (const delta of [{ codex_model: '../escape' }, { codex_effort: 'high;echo' }, { codex_model: '' }]) {
    assert.throws(() => validateRemediationContract({ ...contract, ...delta }, { pullRequest: 43, reviewedHeadSha: head }), { code: 'MODEL_PROFILE_INVALID' });
  }
});

test('native and YAML remediation default absent profile fields without path or review metadata', () => {
  const body = [...fields.filter(line => !/^(Codex|Subagents):?/.test(line)), '## Required validation', 'git diff', '### F1 content'].join('\n');
  const c = extractRemediationContract(body, { canonicalIssueBody: source });
  const context = { pullRequest: 43, reviewedHeadSha: head };
  for (const contract of [c, extractRemediationContract('```yaml\n' + Object.entries(c).filter(([, v]) => v !== undefined).map(([k,v]) => `${k}: ${JSON.stringify(v)}`).join('\n') + '\n```')]) {
    const resolved = validateRemediationContract(contract, context);
    assert.equal(resolved.codex_model, CONSUMER.defaultProfile.cliModelId);
    assert.equal(resolved.codex_effort, CONSUMER.defaultProfile.effort);
    assert.equal(resolved.subagents_allowed, false);
    assert.ok(!('allowed_paths' in resolved));
    assert.equal(validateRemediationContract({ ...contract, codex_model: 'future-model' }, context).codex_effort, CONSUMER.defaultProfile.effort);
    assert.equal(validateRemediationContract({ ...contract, codex_effort: 'future-effort' }, context).codex_model, CONSUMER.defaultProfile.cliModelId);
  }
});
test('native CR authority accepts reordered sections, bullets and dash variants without optional prose labels', () => {
  for (const dash of ['-', '—', '–']) {
    const body = ['### Required validation', '- git diff --check', '## Arbitrary launch heading',
      ...fields.slice().reverse().map(s => `* **${s.replaceAll(' - ', ` ${dash} `)}**`),
      '#### Findings', '### F1 — Fix substantive content'].join('\n');
    const c = extractRemediationContract(body, { canonicalIssueBody: source });
    assert.equal(validateRemediationContract(c, { pullRequest: 43, reviewedHeadSha: head }).required_starting_head, head);
  }
});
test('conflicting head metadata and substantive empty findings fail closed', () => {
  const body = [...fields, `Required starting head: ${'b'.repeat(40)}`, '## Required validation', 'git diff', '### F1 content'].join('\n');
  assert.throws(() => extractRemediationContract(body, { canonicalIssueBody: source }), { code: 'CONTRACT_VALUE_AMBIGUOUS' });
});

test('native integration CR headings retain task-qualified findings, validation and its exact Outcome token', () => {
  const body = ['## Change Request metadata', ...fields.map(s => `- ${s}`),
    '## Findings', '### CR42-F1 — major — Reconcile current main', '### CR42-F2 — major — Validate exact head',
    '## Validation', 'Run routing, remediation, launcher, Ansible, Reviewer, workflow/static, git diff and secret checks.',
    '## Outcome', 'Expected successful remediation outcome: `CR_42_003_REMEDIATED_PENDING_REVIEW`.'].join('\n');
  const context = { pullRequest: 43, reviewedHeadSha: head };
  const parse = text => validateRemediationContract(extractRemediationContract(text, { canonicalIssueBody: source }), context);
  const c = parse(body);
  assert.deepEqual(c.finding_ids, ['CR42-F1', 'CR42-F2']);
  assert.ok(c.required_validation.includes('routing-tests'));
  assert.ok(c.required_validation.includes('secret-scan'));
  assert.equal(c.success_token, 'CR_42_003_REMEDIATED_PENDING_REVIEW');
  assert.throws(() => parse(body.replace('## Validation', '## Unrecognized heading')), { code: 'CURRENT_VALIDATION_MISSING' });
  assert.throws(() => parse(body.replaceAll('CR42-F', 'unrecognized-')), { code: 'CONTRACT_SET_INVALID' });
  assert.throws(() => parse(`${body}\nRequired starting head: ${'b'.repeat(40)}`), { code: 'CONTRACT_VALUE_AMBIGUOUS' });
});
