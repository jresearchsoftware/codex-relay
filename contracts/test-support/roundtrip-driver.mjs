import { CONSUMER } from '../../consumer/consumer.mjs';
// Called with the actual intercepted GitHub POST payload by Rust HTTP tests.
// Kept outside test/ so Node's default discovery never runs this stdin driver.
import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
import { extractRemediationContract, validateRemediationContract } from '../src/contracts.mjs';
import { admitEnvelope, readAuthority, revalidateAuthority } from '../../controller/src/live-authority.mjs';
import { dispatchRunName } from '../../controller/src/launch-metadata.mjs';
import { REPOSITORY, REVIEWER, OWNER, NATIVE_VALIDATIONS, validateEnvelope } from '../../controller/src/execution-contract.mjs';
import { prepareReviewStep, synchronizeReviewStep } from '../src/step-synchronization.mjs';

export async function admitPublished(arguments_, publication) {
  assert.equal(publication.event, 'REQUEST_CHANGES');
  assert.equal(publication.commit_id, arguments_.expected_head_sha);
  const contract = validateRemediationContract(extractRemediationContract(publication.body),
    { pullRequest: arguments_.pr_number, reviewedHeadSha: publication.commit_id });
  const input = arguments_.change_request;
  assert.equal(contract.change_request_id, input.change_request_id);
  assert.equal(contract.step, input.step);
  assert.deepEqual(contract.finding_ids, input.findings.map(f => f.id));
  assert.equal(contract.codex_model, input.codex_model);
  assert.equal(contract.codex_effort, input.codex_effort);
  assert.equal(contract.subagents_allowed, input.subagents_allowed ?? false);
  assert.equal(contract.success_token, input.success_token);
  assert.equal(contract.blocked_token, input.blocked_token);
  assert.ok(!('allowed_paths' in contract));
  assert.ok(!('review_model' in contract));
  assert.ok(!('review_effort' in contract));
  assert.ok(contract.required_validation.every(v => NATIVE_VALIDATIONS.has(v)));
  assert.deepEqual(contract.required_validation, [...input.required_validation].sort());
  const labels = [{ name: `step-${input.step > 1 ? input.step - 1 : input.step}` }];
  const issue = { number: 24, labels: structuredClone(labels), state: 'open', user: { login: OWNER }, body: '# Task 24\nImplement the admitted serialization change.' };
  const pr = { number: arguments_.pr_number, state: 'open', merged: false, draft: false, body: 'Related to #24',
    labels: structuredClone(labels), title: 'Task 24 serialization', base: { ref: CONSUMER.baseBranch, sha: publication.commit_id, repo: { full_name: REPOSITORY } },
    head: { ref: `${CONSUMER.taskBranchPrefix}task-24`, sha: publication.commit_id, repo: { full_name: REPOSITORY } } };
  const review = { id: 17, state: 'CHANGES_REQUESTED', commit_id: publication.commit_id,
    user: { login: REVIEWER }, body: publication.body };
  // The historical Step-1 fixture remains parseable. A new CR advances from
  // current labels through owner orchestration; retries retain its exact Step.
  for (const step of [input.step, input.step]) {
    const launch = { runId: 99, route: 'auto', target: 'pull_request', number: pr.number, issueNumber: issue.number, step };
    const api = {
      viewer: async () => ({ login: OWNER, type: 'User' }),
      ensureStepLabel: async value => assert.equal(value, input.step),
      patch: async (path, body) => {
        const subject = path === '/issues/24' ? issue : [`/issues/${pr.number}`, `/pulls/${pr.number}`].includes(path) ? pr : assert.fail(path);
        if (body.labels) subject.labels = body.labels.map(name => ({ name }));
        if (body.title) subject.title = body.title;
      },
      getRun: async () => ({ id: 99, repository: { full_name: REPOSITORY }, actor: { login: OWNER },
        status: 'in_progress', path: CONSUMER.routingWorkflow, event: 'workflow_dispatch',
        head_branch: CONSUMER.baseBranch, run_attempt: 1, display_title: dispatchRunName(launch) }),
      get: async path => {
        if (path === `/pulls/${pr.number}`) return structuredClone(pr);
        if (path === '/issues/24') return structuredClone(issue);
        if (path === `/git/ref/heads/${CONSUMER.baseBranch}`) return { object: { sha: publication.commit_id } };
        throw new Error(`Unexpected authority request: ${path}`);
      },
      list: async path => {
        assert.equal(path, `/pulls/${pr.number}/reviews`);
        return [structuredClone(review)];
      }
    };
    if (input.step > 1) {
      if (issue.labels[0].name !== `step-${input.step}`) assert.equal((await prepareReviewStep(api, pr.number)).step, input.step);
      assert.equal((await synchronizeReviewStep(api, pr.number, review.id)).step, input.step);
    }
    const envelope = await admitEnvelope(api, launch);
    assert.ok(!envelope.blocked, JSON.stringify(envelope.block));
    assert.equal(envelope.step, step);
    assert.equal(envelope.profile.cliModelId, input.codex_model);
    assert.deepEqual(envelope.validation, contract.required_validation);
    assert.throws(() => validateEnvelope({ ...envelope, validation: ['undeclared-check'] }), { code: 'REQUIRED_VALIDATION_UNSUPPORTED' });
    assert.equal(envelope.closure, 'Related to #24');
    assert.equal((await readAuthority(api, 'pull_request', pr.number, { step })).contract.step, input.step);
    await revalidateAuthority(api, envelope);
    await assert.rejects(readAuthority(api, 'pull_request', pr.number, { step: step === 1 ? 2 : step - 1 }), { code: 'STEP_LABEL_MISMATCH' });
  }
  return contract;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  let input = '';
  for await (const chunk of process.stdin) input += chunk;
  const { arguments: arguments_, publication } = JSON.parse(input);
  await admitPublished(arguments_, publication);
  process.stdout.write('REVIEWER_PUBLICATION_REMEDIATION_ROUNDTRIP_PASS\n');
}
