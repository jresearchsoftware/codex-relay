import test from 'node:test';
import assert from 'node:assert/strict';
import { REPOSITORY, OWNER, REVIEWER } from '../src/execution-contract.mjs';
import { authorityFingerprint, readAuthority, revalidateAuthority } from '../src/live-authority.mjs';

const head = 'a'.repeat(40);
const issueBody = [
  '# Task 42 test', `Accepted starting \`main\`: \`${head}\``, 'Required branch: `codex/test-42`',
  'Exact implementation thread: `Task 42 - Step 1 - core`', 'Issue closure policy: `close-authorized`',
  'Codex model: `gpt-5.6-luna`', 'Codex reasoning effort: `high`',
  '## Notes', 'Keep this bounded — preserve API.'
].join('\n');
const nativeBody = [
  '## Metadata', 'Change Request ID: CR-42-001', `Target repository: ${REPOSITORY}`,
  'Target pull request: #43', `Reviewed head SHA: ${head}`, `Required starting head: ${head}`,
  'Thread name: Task 42 - Step 2 - CR-42-001 core', 'Codex model: gpt-5.6-luna',
  'Codex reasoning effort: high', 'Subagents: Off',
  '## Required validation', '- git diff --check', '### F1 — Fix substantive content',
  '## Completion outcome', 'Allowed success token: `READY`', 'Allowed blocked token: `BLOCKED`'
].join('\n');
const contract = {
  schema_version: '1.0', change_request_id: 'CR-42-001', repository: REPOSITORY, pull_request: 43,
  reviewed_head_sha: head, required_starting_head: head, remediation_thread_title: 'Task 42 - Step 2 - CR-42-001 core',
  codex_model: 'gpt-5.6-luna', codex_effort: 'high', subagents_allowed: false,
  finding_ids: ['F1', 'F2'], required_validation: ['diff-check', 'secret-scan'],
  success_token: 'READY', blocked_token: 'BLOCKED'
};
const yamlBody = c => ['### F1 — Fix content', '### F2 — Preserve API', '```yaml',
  ...Object.entries(c).map(([k, v]) => `${k}: ${JSON.stringify(v)}`), '```'].join('\n');

async function fixture(kind = 'issue') {
  const issue = { number: 42, labels: [{ name: 'step-2' }], body: issueBody, state: 'open', user: { login: OWNER } };
  const pr = { number: 43, labels: [{ name: 'step-2' }], state: 'open', merged: false, body: 'Closes #42',
    base: { ref: 'main', sha: head, repo: { full_name: REPOSITORY } },
    head: { ref: 'codex/test-42', sha: head, repo: { full_name: REPOSITORY } } };
  const review = { id: 17, commit_id: head, user: { login: REVIEWER }, state: 'CHANGES_REQUESTED',
    body: kind === 'yaml' ? yamlBody(contract) : nativeBody };
  const api = {
    get: async path => structuredClone(path === '/pulls/43' ? pr : issue),
    list: async () => [structuredClone(review)]
  };
  const target = kind === 'issue' ? 'issue' : 'pull_request'; const number = target === 'issue' ? 42 : 43;
  const a = await readAuthority(api, target, number, { step: 2 });
  const envelope = { ...a, target, number, step: 2, reviewId: a.review?.id ?? null };
  return { issue, pr, review, api, envelope, revalidate: () => revalidateAuthority(api, envelope) };
}

test('Issue parsed profile, closure and starting bindings cannot remain stale', async () => {
  const f = await fixture();
  for (const [before, after] of [
    ['`gpt-5.6-luna`', '`gpt-5.6-sol`'],
    ['`high`', '`max`'], ['`close-authorized`', '`keep-open`'], ['`codex/test-42`', '`codex/other`'],
    [head, 'b'.repeat(40)]
  ]) {
    f.issue.body = issueBody.replace(before, after);
    await assert.rejects(f.revalidate(), { code: 'AUTHORITY_CHANGED' }, `${before} -> ${after}`);
  }
});

test('parsed execution is fingerprinted even when cosmetic prose would collide', async () => {
  const { envelope } = await fixture();
  const fingerprint = execution => authorityFingerprint({ issue: { body: '' }, execution });
  for (const delta of [
    { profile: { cliModelId: 'gpt-5.6-sol', effort: 'high' } },
    { profile: { cliModelId: 'gpt-5.6-luna', effort: 'max' } }, { closure: 'Related to #42' },
    { issueNumber: 44 }, { branch: 'codex/other' }, { startHead: 'b'.repeat(40) }, { validation: ['diff-check'] }
  ]) assert.notEqual(fingerprint({ ...envelope, ...delta }), fingerprint(envelope));
  assert.equal(fingerprint({ ...envelope, validation: [...envelope.validation].reverse(), profile: { effort: 'high', cliModelId: 'gpt-5.6-luna' } }), fingerprint(envelope));
});

test('literal instructions preserve stars, backticks, Unicode and whitespace inside code', async () => {
  for (const [before, after] of [['docs/', 'docs/*'], ['a*b', 'ab'], ['a—b', 'a-b'],
    ['a  b', 'a b'], ['e\u0301', 'é'], ['a`*b', 'a`b']]) {
    const f = await fixture();
    f.issue.body += `\nPreserve \`\`${before}\`\` exactly.`;
    const a = await readAuthority(f.api, 'issue', 42, { step: 2 }); Object.assign(f.envelope, a);
    f.issue.body = f.issue.body.replace(`\`\`${before}\`\``, `\`\`${after}\`\``);
    await assert.rejects(f.revalidate(), { code: 'AUTHORITY_CHANGED' });
  }
});

test('literal stars in ordinary Issue and native CR prose invalidate admitted authority', async () => {
  for (const kind of ['issue', 'native', 'yaml']) {
    for (const instruction of ['Process *.md files.', 'Process *.md and *.txt files.',
      'Process docs/** files.', 'Preserve a*b exactly.', 'Use * literally.',
      'Compute 2 * 3 * 4.', 'Preserve ** literally.', 'Preserve **unclosed* text.',
      'Preserve \\*escaped text\\* exactly.']) {
      const f = await fixture(kind); const source = kind === 'issue' ? f.issue : f.review;
      source.body += `\n${instruction}`;
      Object.assign(f.envelope, await readAuthority(f.api, f.envelope.target, f.envelope.number, { step: 2 }));
      source.body = source.body.replace(instruction, instruction.replaceAll('*', ''));
      await assert.rejects(f.revalidate(), { code: 'AUTHORITY_CHANGED' }, `${kind}: ${instruction}`);
    }
  }
});

test('simple paired emphasis in Issue and native CR prose remains cosmetic', async () => {
  for (const kind of ['issue', 'native', 'yaml']) {
    for (const stars of ['*', '**', '***']) {
      const f = await fixture(kind); const source = kind === 'issue' ? f.issue : f.review;
      source.body += '\nPlease preserve API.';
      Object.assign(f.envelope, await readAuthority(f.api, f.envelope.target, f.envelope.number, { step: 2 }));
      source.body = source.body.replace('Please preserve API.', `Please ${stars}preserve API${stars}.`);
      await f.revalidate();
    }
  }
});

test('native CR profile, findings, validation and outcome contract edits invalidate admission', async () => {
  const f = await fixture('native');
  for (const [before, after] of [
    ['Codex model: gpt-5.6-luna', 'Codex model: gpt-5.6-sol'], ['effort: high', 'effort: max'],
    ['### F1', '### F2'], ['git diff --check', 'secret scan'], ['`READY`', '`READY*`'],
    ['`BLOCKED`', '`BLOCKED*`'], ['CR-42-001', 'CR-42-002']
  ]) {
    f.review.body = nativeBody.replaceAll(before, after);
    await assert.rejects(f.revalidate(), { code: 'AUTHORITY_CHANGED' });
  }
  f.review.body = nativeBody; f.issue.body = issueBody + '\nChanged required behavior.';
  await assert.rejects(f.revalidate(), { code: 'AUTHORITY_CHANGED' });
});

test('YAML CR binds the complete parsed execution contract, including previously excluded outcome tokens', async () => {
  const f = await fixture('yaml');
  for (const delta of [
    { codex_model: 'gpt-5.6-sol' }, { codex_effort: 'max' },
    { finding_ids: ['F2'] }, { required_validation: ['diff-check'] }, { success_token: 'READY*' },
    { blocked_token: 'BLOCKED*' }, { remediation_thread_title: 'Task 42 - Step 2 - revised instructions' },
    { change_request_id: 'CR-42-002' }
  ]) {
    f.review.body = yamlBody({ ...contract, ...delta });
    await assert.rejects(f.revalidate(), { code: 'AUTHORITY_CHANGED' });
  }
});

test('target, native head and Reviewer identity checks remain fail-closed', async () => {
  for (const [mutate, code] of [
    [f => { f.pr.body = 'Related to #42'; }, 'AUTHORITY_CHANGED'],
    [f => { f.pr.body = 'Closes #44'; }, 'AUTHORITY_CHANGED'],
    [f => { f.pr.head.ref = 'codex/other'; }, 'AUTHORITY_CHANGED'],
    [f => { f.pr.base.ref = 'other'; }, 'PR_NOT_ADMITTED'],
    [f => { f.pr.head.repo.full_name = 'other/repo'; }, 'PR_NOT_ADMITTED'],
    [f => { f.review.commit_id = 'b'.repeat(40); }, 'CONTRACT_HEAD_MISMATCH'],
    [f => { f.review.id++; }, 'AUTHORITY_CHANGED'],
    [f => { f.review.user.login = OWNER; }, 'CURRENT_CHANGE_REQUEST_MISSING'],
    [f => { f.issue.user.login = REVIEWER; }, 'ISSUE_NOT_ADMITTED']
  ]) {
    const f = await fixture('yaml'); mutate(f); await assert.rejects(f.revalidate(), { code });
  }
});

test('permitted emphasis, heading and prose dash changes preserve Issue and native CR authority', async () => {
  for (const kind of ['issue', 'native']) {
    const f = await fixture(kind);
    f.issue.body = issueBody.replace('## Notes', '### **Notes**').replace('Keep this bounded — preserve API.', '**Keep this bounded - preserve API.**');
    if (kind === 'native') f.review.body = nativeBody.replace('## Metadata', '### **Metadata**')
      .replace('Codex model: gpt-5.6-luna', '* **Codex model: gpt-5.6-luna**')
      .replaceAll(' - ', ' — ').replace('### F1 —', '#### **F1** –');
    await f.revalidate();
  }
});

test('YAML key/set ordering, quoting and display-title dash changes preserve executable authority', async () => {
  const f = await fixture('yaml');
  const cosmetic = Object.fromEntries(Object.entries({ ...contract,
    finding_ids: [...contract.finding_ids].reverse(),
    required_validation: [...contract.required_validation].reverse(),
    remediation_thread_title: contract.remediation_thread_title.replaceAll(' - ', ' — ')
  }).reverse());
  f.review.body = yamlBody(cosmetic).replace('codex_model: "gpt-5.6-luna"', 'codex_model: gpt-5.6-luna');
  await f.revalidate();
});
