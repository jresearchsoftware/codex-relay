import { CONSUMER } from '../../consumer/consumer.mjs';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { promisify } from 'node:util';
import { execFile } from 'node:child_process';
import { createPublicationBroker } from '../src/publication-broker.mjs';
import { createGitPublisher, collectProgress, gitEnvironment } from '../src/trusted-git.mjs';
import { prepareCheckout } from '../src/attempt-runtime.mjs';
import { dispatchRunName, labelRunName } from '../src/launch-metadata.mjs';
import { REPOSITORY, WRITER, REVIEWER } from '../src/execution-contract.mjs';

const exec = promisify(execFile);
const copy = v => structuredClone(v);
const installedFixtureEventBase = Number.parseInt(process.env.INSTALLED_FIXTURE_EVENT_BASE ?? '1000', 10);
let nextInstalledFixtureEventOffset = 0;
export function memoryStore() {
  const rows = new Map();
  return { get: async id => copy(rows.get(id) ?? null), put: async (id, r) => { rows.set(id, copy(r)); }, all: async () => copy([...rows.values()]) };
}
export async function fixture(t, { remediation = false, instruction = '', installed = false, issueBody, reviewBody, step = remediation ? 2 : 1, labelLaunch = false, route = 'auto',
  mainAdvance = false, unrelatedMain = false, nativeReview = false, beforeAdmission = () => {}, profile = { cliModelId: 'gpt-5.6-luna', effort: 'high' } } = {}) {
  // The installed proof runs real code against the governed dispatch-work
  // root. Give each fixture its own admitted event namespace so a concurrent
  // test or a later proof subprocess cannot prepare, collect, or clean up
  // another checkout.
  const fixtureRunId = installed ? installedFixtureEventBase + nextInstalledFixtureEventOffset++ : 99;
  const root = await mkdtemp(join(tmpdir(), 'relay-core-test-')); t.after(() => rm(root, { recursive: true, force: true }));
  const remote = join(root, 'remote.git'); const source = join(root, 'source');
  const env = { ...gitEnvironment(), GIT_AUTHOR_NAME: 'owner', GIT_AUTHOR_EMAIL: 'owner@example.test', GIT_COMMITTER_NAME: 'owner', GIT_COMMITTER_EMAIL: 'owner@example.test' };
  const command = async (cwd, args, override = {}) => (await exec('git', args, { cwd, env: { ...env, ...override } })).stdout.trim();
  await mkdir(source); await command(root, ['init', '--bare', remote]); await command(source, ['init', '-b', CONSUMER.baseBranch]);
  await mkdir(join(source, 'docs')); await writeFile(join(source, 'docs/work.md'), 'baseline\n');
  await command(source, ['add', '.']);
  // Independent fixtures intentionally share one baseline SHA, even when
  // construction crosses a second boundary. Keep task-progress dates separate.
  await command(source, ['commit', '-m', 'baseline'], {
    GIT_AUTHOR_DATE: '2000-01-01T00:00:00Z', GIT_COMMITTER_DATE: '2000-01-01T00:00:00Z',
  });
  await command(source, ['push', remote, CONSUMER.baseBranch]); const base = await command(source, ['rev-parse', 'HEAD']);
  const issue = { number: 42, labels: [{ name: `step-${step}` }], state: 'open', user: { login: CONSUMER.owner }, body: [
    '# Task 42 test', `- Required starting base: \`${base}\``, `- Required branch: ${CONSUMER.taskBranchPrefix}test-42`,
    '- Exact implementation thread: `Task 42 - Step 1 - core`', '- Issue closure policy: `close-authorized`',
    '## Execution profile', `- Codex model: \`${profile.cliModelId}\``, `- Codex reasoning effort: \`${profile.effort}\``,
    '## Validation', '- git diff --check' ].join('\n') };
  if (issueBody !== undefined) issue.body = issueBody;
  let pr = null; let nextComment = 1; const comments = []; let taskBranch = `${CONSUMER.taskBranchPrefix}test-42`;
  let review;
  if (remediation) {
    await command(source, ['push', remote, `${CONSUMER.baseBranch}:refs/heads/${CONSUMER.taskBranchPrefix}test-42`]);
    pr = { number: 43, title: `Task 42 · Step ${step} · core`, labels: [{ name: `step-${step}` }], node_id: 'PR_node', state: 'open', merged: false, draft: false, body: 'Closes #42',
      base: { ref: CONSUMER.baseBranch, sha: base, repo: { full_name: REPOSITORY } },
      head: { ref: `${CONSUMER.taskBranchPrefix}test-42`, sha: base, repo: { full_name: REPOSITORY } }, mergeable: true };
    review = { id: 17, user: { login: REVIEWER }, state: 'CHANGES_REQUESTED', commit_id: base, body: [
      'F1: correct the documentation.', '```yaml', 'schema_version: "1.0"', 'change_request_id: CR-42-001',
      `repository: ${REPOSITORY}`, 'pull_request: 43', `reviewed_head_sha: ${base}`, `required_starting_head: ${base}`,
      `remediation_thread_title: Task 42 - Step ${step} - CR-42-001 core`, `codex_model: ${profile.cliModelId}`, `codex_effort: ${profile.effort}`,
      'subagents_allowed: false', 'finding_ids: [F1]', 'required_validation: [diff-check]',
      'success_token: READY', 'blocked_token: BLOCKED', '```' ].join('\n') };
  }
  if (nativeReview && review) review.body = [
    '## Change Request metadata', '- Change Request ID: CR-42-003', `- Target repository: ${REPOSITORY}`,
    '- Target pull request: #43', `- Reviewed head SHA: ${base}`, '## Required remediation launch profile',
    `- Thread name: Task 42 — Step ${step} — Integration reconciliation`, `- Codex model: ${profile.cliModelId}`,
    `- Codex reasoning effort: ${profile.effort}`, `- Required starting head: ${base}`, '- Subagents: Off',
    '## Findings', '### CR42-F1 — major — Reconcile current main',
    '## Validation', 'Run routing, remediation, launcher, Ansible, Reviewer, workflow/static, git diff and secret checks.',
    '## Outcome', 'Expected successful remediation outcome: `CR_42_003_REMEDIATED_PENDING_REVIEW`.'
  ].join('\n');
  if (reviewBody !== undefined && review) review.body = reviewBody;
  if (instruction) (remediation ? review : issue).body += `\n${instruction}`;
  if (mainAdvance || unrelatedMain) {
    if (remediation) {
      await command(source, ['switch', '-c', taskBranch]);
      await writeFile(join(source, 'docs/work.md'), 'reviewed task behavior\n');
      await command(source, ['commit', '-am', 'reviewed task']);
      await command(source, ['push', remote, taskBranch]);
      review.commit_id = await command(source, ['rev-parse', 'HEAD']);
      review.body = review.body.replaceAll(base, review.commit_id);
      await command(source, ['switch', CONSUMER.baseBranch]);
      pr.mergeable = false;
    }
    await writeFile(join(source, 'docs/work.md'), 'advanced main behavior\n');
    await writeFile(join(source, 'main-feature.md'), 'preserve main feature\n');
    await command(source, ['add', '.']);
    if (unrelatedMain) {
      const tree = await command(source, ['write-tree']);
      const rootCommit = await command(source, ['commit-tree', tree, '-m', 'unrelated root']);
      // A local synthetic remote with unrelated history, never a production push.
      await command(source, ['push', remote, `${rootCommit}:refs/heads/unrelated`]);
      await command(root, ['--git-dir=' + remote, 'update-ref', `refs/heads/${CONSUMER.baseBranch}`, rootCommit]);
    } else {
      await command(source, ['commit', '-m', 'advance main']);
      await command(source, ['push', remote, CONSUMER.baseBranch]);
    }
  }
  let checksReady = false; let pushes = 0; let staleObservation = false; let observedHead; let pushFailure = false;
  let observationFailure = null; const publicationOperations = [];
  const launch = { target: remediation ? 'pull_request' : 'issue', number: remediation ? 43 : 42, issueNumber: 42, step, route, ...(labelLaunch ? { transport: 'label' } : {}) };
  const events = labelLaunch ? [{ id: 71, event: 'labeled', actor: { login: CONSUMER.owner, type: 'User' },
    label: { name: `codex-ready-${route}` }, created_at: '2026-09-04T12:00:00Z' }] : [];
  if (labelLaunch) (pr ?? issue).labels.push({ name: `codex-ready-${route}` });
  const admissionRequest = { operation: 'admit', runId: fixtureRunId, ...launch };
  const run = { id: fixtureRunId, repository: { full_name: REPOSITORY }, actor: { login: CONSUMER.owner }, status: 'in_progress',
    event: labelLaunch ? remediation ? 'pull_request_target' : 'issues' : 'workflow_dispatch', head_branch: CONSUMER.baseBranch,
    display_title: labelLaunch ? labelRunName(launch, pr ?? issue) : dispatchRunName(launch), path: CONSUMER.routingWorkflow, run_attempt: 1, created_at: '2026-09-04T12:00:01Z' };
  const remoteHead = async () => (await command(root, ['ls-remote', remote, `refs/heads/${taskBranch}`])).split(/\s+/)[0] || null;
  const api = {
    getRun: async () => copy(run),
    async get(path) {
      if (/^\/issues\/comments\/[1-9][0-9]*$/.test(path)) {
        const comment = comments.find(c => c.id === Number(path.split('/').at(-1)));
        if (comment) return copy(comment);
      }
      if (path === '/issues/42') return copy(issue);
      if (path === '/issues/43') return copy(pr);
      if (path.startsWith('/git/matching-refs/')) return [];
      if (path === `/git/ref/heads/${CONSUMER.baseBranch}`) return { object: { sha: await command(root, ['--git-dir='+remote, 'rev-parse', CONSUMER.baseBranch]) } };
      if (path === '/pulls/43' && pr) return { ...copy(pr), head: { ...pr.head, sha: await remoteHead() } };
      throw new Error(`Unexpected GET ${path}`);
    },
    async list(path) {
      if (path.endsWith('/events')) return copy(events);
      if (path === '/pulls/43/reviews') return [copy(review)];
      if (path.startsWith('/pulls?')) return pr ? [await this.get('/pulls/43')] : [];
      if (path.endsWith('/comments')) return copy(comments);
      throw new Error(`Unexpected list ${path}`);
    },
    async post(path, body) {
      if (path === '/pulls') {
        pr = { number: 43, labels: [], title: body.title, node_id: 'PR_node', state: 'open', merged: false, draft: body.draft, body: body.body,
          base: { ref: CONSUMER.baseBranch, sha: base, repo: { full_name: REPOSITORY } },
          head: { ref: body.head, sha: await remoteHead(), repo: { full_name: REPOSITORY } }, mergeable: true };
        return copy(pr);
      }
      if (path === '/issues/43/labels') {
        pr.labels.push(...body.labels.map(name => ({ name }))); return copy(pr.labels);
      }
      if (path.endsWith('/comments')) { const c = { id: nextComment++, user: { login: WRITER }, body: body.body }; comments.push(c); return copy(c); }
      throw new Error(`Unexpected POST ${path}`);
    },
    async delete(path) {
      assertLabelPath(path);
      const subject = remediation ? pr : issue;
      subject.labels = subject.labels.filter(l => l.name !== path.split('/').at(-1));
    },
    async patch(path, body) {
      if (path === '/pulls/43' && Object.keys(body).join() === 'title') {
        pr.title = body.title; return copy(pr);
      }
      const comment = comments.find(c => path === `/issues/comments/${c.id}`);
      if (!comment) throw new Error('Unexpected comment PATCH');
      comment.body = body.body; return copy(comment);
    },
    async validations(head) { return checksReady ? [{ id: 10, path: '.github/workflows/relay-exact-head-validation.yml', event: 'pull_request', head_sha: head, status: 'completed', conclusion: 'success' }] : []; },
    async ready() { pr.draft = false; },
    async draft() { pr.draft = true; }
  };
  function assertLabelPath(path) {
    if (!labelLaunch || path !== `/issues/${launch.number}/labels/codex-ready-${route}`) throw new Error('Unexpected label mutation');
  }
  const store = memoryStore(); const realPublisher = createGitPublisher({ remote, root });
  const publisher = { inspect: (e, bundle, fn) => realPublisher.inspect(e, bundle, g => fn({ ...g,
    push: async () => {
      publicationOperations.push('push');
      pushes++;
      if (pushFailure) {
        if (pushFailure.afterPush) await g.push();
        throw pushFailure.error ?? pushFailure;
      }
      await g.push();
    },
    observe: async () => {
      publicationOperations.push('observe');
      if (observationFailure) throw observationFailure;
      return staleObservation ? null : observedHead ?? g.observe();
    } })) };
  const brokerImpl = createPublicationBroker({ api, store, publisher });
  const broker = { invoke: r => brokerImpl.dispatch(r) };
  await beforeAdmission({ issue, pr, review, run, events, api, store, admissionRequest });
  const admission = await broker.invoke(admissionRequest);
  const { envelope } = admission;
  taskBranch = envelope.branch ?? taskBranch;
  const workRoot = installed ? CONSUMER.paths.workRoot : join(root, 'work'); await mkdir(workRoot, { recursive: true });
  const cwd = join(workRoot, envelope.attemptId);
  // The installed test may invoke this same cleanup while another fixture is
  // collecting progress; it must therefore own a distinct checkout path.
  const removeCheckout = () => rm(cwd, { recursive: true, force: true });
  if (installed) t.after(removeCheckout);
  const { name, email } = remediation ? CONSUMER.remediationIdentity : CONSUMER.writerIdentity;
  const identity = { GIT_AUTHOR_NAME: name, GIT_COMMITTER_NAME: name, GIT_AUTHOR_EMAIL: email, GIT_COMMITTER_EMAIL: email };
  const commit = async (path = 'docs/work.md', text = 'changed\n') => { await writeFile(join(cwd, path), text); await command(cwd, ['add', path]); await command(cwd, ['commit', '-m', 'task progress'], identity); return command(cwd, ['rev-parse', 'HEAD']); };
  return { root, remote, source, command, api, issue, pr, run, events, admissionRequest, admission, review, store, broker, publisher, identity, envelope, cwd, commit, comments, remoteHead, removeCheckout,
    prepare: e => prepareCheckout(e, { root: workRoot, remote, token: null }),
    collect: e => collectProgress(cwd, e, { root, remote }),
    checksReady: () => { checksReady = true; }, pushes: () => pushes,
    publicationOperations, failObserve: v => { observationFailure = v; },
    stale: v => { staleObservation = v; }, observeAs: v => { observedHead = v; },
    failPush: v => { pushFailure = v === true ? Object.assign(new Error('transport failed'), { code: 'EIO' }) : v; } };
}
