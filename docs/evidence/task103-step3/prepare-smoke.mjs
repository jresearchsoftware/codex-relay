// Offline preparation only. Never creates admissions, journals, native events or runs.
import assert from 'node:assert/strict';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { sha256Body, authorityMode, stableClosurePolicy, validateAuthorityRecord,
  renderAuthorityRecord } from '../../../contracts/src/github-authority.mjs';

export const TEST_REPOSITORIES = Object.freeze({
  'jresearchsoftware/codex-relay-testbed': 1407614568,
  'jresearchsoftware/codex-relay-testbed-2': 1409883950,
});
export const VARIANTS = Object.freeze({
  'same-a': 'jresearchsoftware/codex-relay-testbed',
  'same-b': 'jresearchsoftware/codex-relay-testbed',
  'cross-a': 'jresearchsoftware/codex-relay-testbed',
  'cross-b': 'jresearchsoftware/codex-relay-testbed-2',
});
const outputFile = variant => `qualification/task103-parallel/${variant}.txt`;
const purpose = variant => `Parallel qualification smoke ${variant} for product Task 103`;
export function charter(variant, holdSeconds = 120) {
  assert(Object.hasOwn(VARIANTS, variant), 'unknown variant');
  assert(Number.isInteger(holdSeconds) && holdSeconds >= 60 && holdSeconds <= 180 && holdSeconds % 30 === 0,
    'hold must be 60..180 seconds in 30-second chunks');
  return `Authority model: github-native-v1

## Goal

Execute one genuine, bounded automatic Codex workload for ${purpose(variant)} in ${VARIANTS[variant]}.
This independent disposable TEST Task contributes evidence to product Task 103; it is not a product implementation or a governance prerequisite.

## Scope

1. From the Writer-admitted checkout, wait ${holdSeconds} seconds as ${holdSeconds / 30} sequential foreground commands of exactly 30 seconds each. Use python3 -c 'import time; time.sleep(30)'. Do not background the wait or launch another model. This keeps the real automatic Codex invocation alive for observable overlap with another independently admitted Task.
2. Create only ${outputFile(variant)} with exactly these UTF-8 bytes: task103-${variant}: bounded automatic smoke completed followed by one LF. Keep the content constant; runtime timestamps belong to protected/native evidence.
3. Check the exact bytes with Python, run git diff --check, and inspect git status for unrelated work. Commit only that file on the admitted fixture branch and return the normal structured automatic result. Writer owns trusted import, push, PR and Outcome publication.

## Boundaries

No other source/workflow/configuration change, credentials, protected-state editing, nested Relay/model call, subagents, external publication by the worker, acceptance, merge, closure, deployment or service/runner/App mutation. Preserve unrelated fixtures. Do not fabricate Task/Step admission, run IDs, ready events or protected intervals. Stop at a concrete boundary; do not retry inference.

## Validation

Exact file bytes and path; git diff --check; ordinary trusted introduced-blob secret scan. Product candidate tests remain product Task 103's responsibility. This fixture is intentionally a one-file smoke workload.

Issue closure policy: keep-open
Keep this fixture open until its native Writer Outcome and overlap evidence are reconciled. Independent acceptance and owner disposition are still required before any cleanup or closure.

## Recommended model budget

Model: gpt-6.1-sol. Effort: medium. Subagents: Off.
Rationale: a mechanical one-file smoke with explicit commands; substantive concurrency judgment stays in product Task 103. Do not escalate, substitute profiles or add helpers inside this fixture.
`;
}

export function prepareDecision({ variant, issue, repository, main, holdSeconds = 120 }) {
  assert.equal(repository.full_name, VARIANTS[variant], 'TEST repository binding');
  assert.equal(repository.id, TEST_REPOSITORIES[repository.full_name], 'TEST repository native ID');
  assert.equal(issue.repository_url, `https://api.github.com/repos/${repository.full_name}`);
  assert(Number.isSafeInteger(issue.id) && issue.id > 0 && Number.isSafeInteger(issue.number) && issue.number > 0);
  assert.equal(issue.state, 'open');
  assert(!issue.pull_request && !issue.labels.some(label => label.name.startsWith('codex-ready-')),
    'new fixture only, before any ready command');
  assert.equal(issue.title, purpose(variant));
  assert.equal(issue.body, charter(variant, holdSeconds), 'full native charter bytes');
  assert.equal(authorityMode(issue.body), 'github-native-v1');
  assert.deepEqual(stableClosurePolicy(issue.body), { policy: 'keep-open', warnings: [] });
  assert(/^[a-f0-9]{40}$/.test(main.sha), 'live TEST main SHA');
  const record = { schema_version: '4.0', kind: 'decision', repository: repository.full_name,
    task: issue.number, parent: { kind: 'issue', number: issue.number }, charter_sha256: sha256Body(issue.body),
    purpose: `Bind the short automatic TEST smoke profile and independent branch for ${variant}`,
    amendments: { purpose: purpose(variant), model: 'gpt-6.1-sol', effort: 'medium', subagents: false,
      scope: [`Execute the complete one-file ${variant} workload in the stable charter, including the bounded foreground wait.`],
      validation: ['diff-check', 'secret-scan'], issue_closure_policy: 'keep-open',
      branch: `codex/task-${issue.number}-task103-${variant}`, base_sha: main.sha, starting_head: main.sha, existing_pr: null },
    supersedes: null, context: [] };
  validateAuthorityRecord(record, { repository: repository.full_name, task: issue.number, charterBody: issue.body });
  assert(!Object.hasOwn(record, 'step') && !Object.hasOwn(record.amendments, 'step'));
  return { repository: repository.full_name, record };
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const [mode, input, output, seconds] = process.argv.slice(2);
  if (mode === 'charters') {
    const holdSeconds = Number(output ?? 120);
    await mkdir(input, { recursive: true });
    for (const variant of Object.keys(VARIANTS)) {
      await writeFile(join(input, `${variant}.charter.md`), charter(variant, holdSeconds));
      await writeFile(join(input, `${variant}.issue.json`), JSON.stringify({ title: purpose(variant),
        body: charter(variant, holdSeconds) }, null, 2) + '\n');
    }
    console.log(JSON.stringify({ preparedOnly: true, realAdmission: false, holdSeconds, variants: VARIANTS }));
  } else if (mode === 'decision') {
    const observed = JSON.parse(await readFile(input, 'utf8'));
    const prepared = prepareDecision({ ...observed, holdSeconds: Number(seconds ?? 120) });
    await mkdir(output, { recursive: true });
    await writeFile(join(output, `${observed.variant}.decision.json`), JSON.stringify(prepared, null, 2) + '\n');
    await writeFile(join(output, `${observed.variant}.decision-preview.md`), renderAuthorityRecord(prepared.record));
    console.log(JSON.stringify({ preparedOnly: true, realAdmission: false, repository: prepared.repository,
      task: prepared.record.task, branch: prepared.record.amendments.branch, charterSha256: prepared.record.charter_sha256 }));
  } else throw Error('usage: prepare-smoke.mjs charters OUTPUT [SECONDS] | decision OBSERVATIONS.json OUTPUT [SECONDS]');
}
