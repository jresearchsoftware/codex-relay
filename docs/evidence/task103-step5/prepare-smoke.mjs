// Pure preparation. Native Issue creation, trusted publication and owner-ready
// commands remain separate operations owned by the admitted manual execution.
import assert from 'node:assert/strict';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { charter as previousCharter, TEST_REPOSITORIES, VARIANTS } from '../task103-step3/prepare-smoke.mjs';
import { sha256Body, validateAuthorityRecord } from '../../../contracts/src/github-authority.mjs';
export { TEST_REPOSITORIES, VARIANTS };
export const purpose = variant => `Managed pool qualification smoke ${variant} for product Task 103 Step 5`;
export function charter(variant, holdSeconds = 120) {
  return previousCharter(variant, holdSeconds)
    .replaceAll(`Parallel qualification smoke ${variant} for product Task 103`, purpose(variant))
    .replaceAll('qualification/task103-parallel/', 'qualification/task103-managed-pool/')
    .replaceAll(`task103-${variant}:`, `task103-step5-${variant}:`);
}
export function prepareDecision({ variant, issue, repository, main, holdSeconds = 120 }) {
  assert.equal(repository.full_name, VARIANTS[variant]);
  assert.equal(repository.id, TEST_REPOSITORIES[repository.full_name]);
  assert.equal(issue.repository_url, `https://api.github.com/repos/${repository.full_name}`);
  assert(Number.isSafeInteger(issue.id) && issue.id > 0 && Number.isSafeInteger(issue.number) && issue.number > 0);
  assert.equal(issue.state, 'open');
  assert(!issue.pull_request && !issue.labels.some(label => label.name.startsWith('codex-ready-')));
  assert.equal(issue.title, purpose(variant)); assert.equal(issue.body, charter(variant, holdSeconds));
  assert.match(main.sha, /^[a-f0-9]{40}$/);
  const record = { schema_version: '4.0', kind: 'decision', repository: repository.full_name, task: issue.number,
    parent: { kind: 'issue', number: issue.number }, charter_sha256: sha256Body(issue.body),
    purpose: `Bind the independent bounded managed-pool fixture ${variant}`,
    amendments: { purpose: purpose(variant), model: 'gpt-6.1-sol', effort: 'medium', subagents: false,
      scope: ['Execute the complete stable one-file charter with its bounded foreground waits.'],
      validation: ['diff-check', 'secret-scan'], issue_closure_policy: 'keep-open',
      branch: `codex/task-${issue.number}-task103-pool-${variant}`, base_sha: main.sha,
      starting_head: main.sha, existing_pr: null }, supersedes: null, context: [] };
  validateAuthorityRecord(record, { repository: repository.full_name, task: issue.number, charterBody: issue.body });
  return { repository: repository.full_name, record };
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const [mode, input, output, seconds] = process.argv.slice(2);
  if (mode === 'charters') {
    await mkdir(input, { recursive: false });
    const holdSeconds = Number(output ?? 120);
    for (const variant of Object.keys(VARIANTS)) {
      await writeFile(join(input, `${variant}.issue.json`), JSON.stringify({ title: purpose(variant), body: charter(variant, holdSeconds) }, null, 2) + '\n', { flag: 'wx' });
    }
    console.log(JSON.stringify({ preparedOnly: true, realAdmission: false, holdSeconds }));
  } else if (mode === 'decision') {
    assert(output, 'usage: prepare-smoke.mjs decision OBSERVED.json OUTPUT.json [HOLD_SECONDS]');
    const prepared = prepareDecision({ ...JSON.parse(await readFile(input, 'utf8')), holdSeconds: Number(seconds ?? 120) });
    await writeFile(output, JSON.stringify(prepared, null, 2) + '\n', { flag: 'wx' });
    console.log(JSON.stringify({ preparedOnly: true, realAdmission: false, repository: prepared.repository, task: prepared.record.task }));
  } else throw new Error('usage: prepare-smoke.mjs charters NEW_OUTPUT_DIR [HOLD_SECONDS] | decision OBSERVED.json OUTPUT.json [HOLD_SECONDS]');
}
