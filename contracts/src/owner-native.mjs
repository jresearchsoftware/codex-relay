import { spawn } from 'node:child_process';
import { canonicalAuthorityJson, extractAuthorityRecord, nativeReference, referenceKey,
  resolveOutcomeAuthority, sha256Body } from './github-authority.mjs';
import { taskReferences } from '../../controller/src/task-relationship.mjs';

export const reject = code => { throw Object.assign(new Error(code), { code }); };
const positive = n => Number.isSafeInteger(n) && n > 0;
const same = (a, b) => canonicalAuthorityJson(a) === canonicalAuthorityJson(b);
const digest = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const sha = value => typeof value === 'string' && /^[a-f0-9]{40}$/.test(value);
const identity = value => ({ login: value?.login, id: value?.id, type: value?.type });
const trusted = (value, expected) => same(identity(value), identity(expected));
const native = (value, repository, kind, parent) => ({ kind, repository, id: value.id,
  parent, author: identity(value.user), body: value.body, state: value.state, commit_id: value.commit_id });

// The production transport uses only the caller's existing gh authentication.
// No token extraction, shell interpolation, caller URL or credential selection.
export function createOwnerGithub({ spawnImpl = spawn } = {}) {
  return async (endpoint, { method = 'GET', body } = {}) => {
    const args = ['api', '--hostname', 'github.com', '--method', method, endpoint];
    if (body !== undefined) args.push('--input', '-');
    return new Promise((resolve, rejectPromise) => {
      const child = spawnImpl('gh', args, { stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true });
      const chunks = []; let length = 0; let failed = false;
      const timeout = setTimeout(() => { failed = true; child.kill(); }, 30000);
      child.stdout.on('data', value => {
        length += value.length;
        if (length > 8 * 1024 * 1024) { failed = true; child.kill(); }
        else chunks.push(value);
      });
      // stderr may contain private transport details; retain no caller bytes.
      child.stderr.resume();
      child.stdin.on('error', () => {});
      child.once('error', () => { clearTimeout(timeout); rejectPromise(Object.assign(new Error('OWNER_NATIVE_UNAVAILABLE'), { code: 'OWNER_NATIVE_UNAVAILABLE' })); });
      child.once('close', code => {
        clearTimeout(timeout);
        if (failed || code !== 0) {
          let status;
          try { status = Number(JSON.parse(Buffer.concat(chunks).toString('utf8')).status); } catch { /* bounded public status only */ }
          return rejectPromise(Object.assign(new Error('OWNER_NATIVE_UNAVAILABLE'), { code: 'OWNER_NATIVE_UNAVAILABLE',
            ...(Number.isInteger(status) && status >= 400 && status <= 599 ? { status } : {}) }));
        }
        try { resolve(JSON.parse(Buffer.concat(chunks).toString('utf8'))); }
        catch { rejectPromise(Object.assign(new Error('OWNER_NATIVE_INVALID'), { code: 'OWNER_NATIVE_INVALID' })); }
      });
      child.stdin.end(body === undefined ? undefined : JSON.stringify(body));
    });
  };
}

export function validateOwnerRequest(request) {
  const fields = ['repository', 'task', 'pull_request', 'expected_head_sha', 'authority_sha256', 'approval', 'owner_assessment'];
  if (!request || Object.keys(request).length !== fields.length || fields.some(key => !Object.hasOwn(request, key))
    || !/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(request.repository)
    || request.repository.split('/').some(part => ['.', '..'].includes(part))
    || !positive(request.task) || !positive(request.pull_request) || !sha(request.expected_head_sha)
    || !digest(request.authority_sha256)) reject('OWNER_CONTINUATION_INPUT_INVALID');
  const approval = request.approval;
  if (!approval || Object.keys(approval).length !== 4 || approval.kind !== 'review' || !positive(approval.id)
    || !digest(approval.sha256) || !same(approval.parent, { kind: 'pull_request', number: request.pull_request })) reject('OWNER_CONTINUATION_INPUT_INVALID');
  const assessment = request.owner_assessment;
  if (!assessment || Object.keys(assessment).some(key => !['hold', 'protected_boundary', 'exact_base_sha'].includes(key))
    || typeof assessment.hold !== 'boolean' || typeof assessment.protected_boundary !== 'boolean'
    || Object.hasOwn(assessment, 'exact_base_sha') && !sha(assessment.exact_base_sha)) reject('OWNER_INTERPRETATION_REQUIRED');
}

export function createOwnerNativeReader({ api, consumer, request }) {
  const repository = request.repository;
  const prefix = `repos/${repository}`;
  const checkTarget = pr => {
    if (pr.number !== request.pull_request || pr.base?.repo?.full_name !== repository || pr.head?.repo?.full_name !== repository
      || pr.base?.ref !== consumer.baseBranch || !sha(pr.base?.sha) || pr.head?.sha !== request.expected_head_sha
      || !same(taskReferences(pr.body, repository), [request.task])) reject('OWNER_PR_BINDING_CHANGED');
  };
  async function list(path, field) {
    const values = [];
    for (let page = 1; page <= 6; page++) {
      const data = await api(`${prefix}/${path}${path.includes('?') ? '&' : '?'}per_page=100&page=${page}`);
      const rows = field ? data[field] : data;
      if (!Array.isArray(rows)) reject('OWNER_NATIVE_INVALID');
      if (rows.length > 100 || values.length + rows.length > 500) reject('OWNER_NATIVE_TRUNCATED');
      values.push(...rows);
      if (rows.length < 100) {
        if (field && data.total_count !== undefined && data.total_count !== values.length) reject('OWNER_NATIVE_TRUNCATED');
        return values;
      }
    }
    reject('OWNER_NATIVE_TRUNCATED');
  }
  async function read() {
    const [viewer, owner, reviewer, writer, issue, pr, taskComments, prComments, reviews] = await Promise.all([
      api('user'), api(`users/${consumer.owner}`), api(`users/${consumer.reviewerApp.expectedActor}`),
      api(`users/${consumer.writerApp.expectedActor}`), api(`${prefix}/issues/${request.task}`),
      api(`${prefix}/pulls/${request.pull_request}`), list(`issues/${request.task}/comments`),
      list(`issues/${request.pull_request}/comments`), list(`pulls/${request.pull_request}/reviews`)
    ]);
    if (owner.login !== consumer.owner || owner.type !== 'User' || !positive(owner.id) || !trusted(viewer, owner)) reject('OWNER_IDENTITY_REQUIRED');
    if (reviewer.login !== consumer.reviewerApp.expectedActor || reviewer.type !== 'Bot' || !positive(reviewer.id)
      || writer.login !== consumer.writerApp.expectedActor || writer.type !== 'Bot' || !positive(writer.id)
      || reviewer.id === writer.id) reject('OWNER_NATIVE_IDENTITY_INVALID');
    if (issue.number !== request.task || !positive(issue.id) || issue.pull_request || typeof issue.body !== 'string'
      || !trusted(issue.user, owner) || !['open', 'closed'].includes(issue.state)) reject('OWNER_TASK_BINDING_CHANGED');
    checkTarget(pr);
    const records = new Map();
    const add = value => {
      if (!positive(value.id) || typeof value.body !== 'string') reject('OWNER_NATIVE_INVALID');
      const key = referenceKey(value);
      if (records.has(key) && !same(records.get(key), value)) reject('OWNER_NATIVE_INVALID');
      records.set(key, value);
      if (records.size > 500) reject('OWNER_NATIVE_TRUNCATED');
    };
    add(native(issue, repository, 'issue-body', { kind: 'issue', number: request.task }));
    for (const [comments, parent] of [[taskComments, { kind: 'issue', number: request.task }],
      [prComments, { kind: 'pull_request', number: request.pull_request }]]) {
      for (const value of comments) {
        if (value.issue_url !== `https://api.github.com/${prefix}/issues/${parent.number}`) reject('OWNER_NATIVE_PARENT_INVALID');
        if ((trusted(value.user, reviewer) || trusted(value.user, writer)) && /^```relay-authority/m.test(value.body ?? '')) {
          add(native(value, repository, 'issue-comment', parent));
        }
      }
    }
    for (const value of reviews) {
      if (value.pull_request_url !== `https://api.github.com/${prefix}/pulls/${request.pull_request}`) reject('OWNER_NATIVE_PARENT_INVALID');
      if (trusted(value.user, reviewer)) add(native(value, repository, 'review', { kind: 'pull_request', number: request.pull_request }));
    }
    const matchingOutcomes = [...records.values()].filter(value => value.kind === 'issue-comment' && trusted(value.author, writer))
      .map(record => ({ record, value: extractAuthorityRecord(record.body, { repository, task: request.task }) }))
      .filter(({ record, value }) => value?.kind === 'outcome' && value.schema_version === '4.0' && value.status === 'implemented'
        && value.repository === repository && value.task === request.task && same(value.parent, record.parent)
        && value.parent.kind === 'pull_request' && value.parent.number === request.pull_request
        && value.result.revision === request.expected_head_sha && ['git', 'no-change'].includes(value.result.kind));
    // A same-head historical result with older Task sources is not the result
    // accepted under the native review's exact current-authority marker. Prefer
    // that precise binding, without guessing between same-authority admissions.
    const exactOutcomes = matchingOutcomes.filter(({ value }) => value.authority?.sha256 === request.authority_sha256);
    const outcomes = exactOutcomes.length ? exactOutcomes : matchingOutcomes;
    if (outcomes.length !== 1 || !outcomes[0].value.admission) reject('OWNER_ADMITTED_OUTCOME_REQUIRED');
    const outcome = outcomes[0].value;
    async function source(ref) {
      if (ref.parent.kind === 'issue' && ref.parent.number !== request.task) reject('OWNER_NATIVE_PARENT_INVALID');
      if (ref.parent.kind === 'pull_request') {
        const target = await api(`${prefix}/pulls/${ref.parent.number}`);
        if (target.number !== ref.parent.number || target.base?.repo?.full_name !== repository
          || target.head?.repo?.full_name !== repository || !same(taskReferences(target.body, repository), [request.task])) reject('OWNER_NATIVE_PARENT_INVALID');
      }
      let value;
      if (ref.kind === 'issue-comment') {
        value = await api(`${prefix}/issues/comments/${ref.id}`);
        if (value.issue_url !== `https://api.github.com/${prefix}/issues/${ref.parent.number}`) reject('OWNER_NATIVE_PARENT_INVALID');
      } else if (ref.kind === 'review' && ref.parent.kind === 'pull_request') {
        value = await api(`${prefix}/pulls/${ref.parent.number}/reviews/${ref.id}`);
        if (value.pull_request_url !== `https://api.github.com/${prefix}/pulls/${ref.parent.number}`) reject('OWNER_NATIVE_PARENT_INVALID');
      } else if (ref.kind === 'review-comment' && ref.parent.kind === 'pull_request') {
        value = await api(`${prefix}/pulls/comments/${ref.id}`);
        if (value.pull_request_url !== `https://api.github.com/${prefix}/pulls/${ref.parent.number}`) reject('OWNER_NATIVE_PARENT_INVALID');
      } else reject('OWNER_SOURCE_CAPABILITY_UNAVAILABLE');
      if (value.id !== ref.id) reject('OWNER_NATIVE_PARENT_INVALID');
      const record = native(value, repository, ref.kind, ref.parent);
      if (!same(nativeReference(record), ref)) reject('OWNER_NATIVE_SOURCE_CHANGED');
      add(record);
    }
    // Follow exact typed provenance/context through the existing SourceRef
    // model, including linked same-Task PRs; never follow caller URLs.
    for (const record of records.values()) {
      if (!trusted(record.author, reviewer) && !trusted(record.author, writer)) continue;
      const value = extractAuthorityRecord(record.body, { repository, task: request.task });
      if (!value) continue;
      if (value.kind === 'outcome' && record.id !== outcomes[0].record.id) continue;
      const refs = [value.supersedes, value.outcome, ...(value.context ?? []), ...(value.decisions ?? []),
        value.authority?.charter, value.authority?.change_request, value.authority?.compatibility_request,
        ...(value.authority?.decisions ?? [])].filter(Boolean);
      for (const ref of refs) {
        if (!records.has(referenceKey(ref))) await source(ref);
      }
    }
    const decisive = [...records.values()].filter(value => value.kind === 'review' && value.parent.number === request.pull_request && trusted(value.author, reviewer)
      && ['APPROVED', 'CHANGES_REQUESTED', 'DISMISSED'].includes(value.state)).sort((a, b) => a.id - b.id).at(-1);
    if (!decisive || decisive.state !== 'APPROVED' || decisive.commit_id !== request.expected_head_sha
      || !same(nativeReference(decisive), request.approval)) reject('OWNER_APPROVAL_CHANGED');
    const markers = decisive.body.split(/\r?\n/).filter(line => line.startsWith('<!-- jresearchsoftware-reviewer-relay:'));
    const marker = /^<!-- jresearchsoftware-reviewer-relay:v1 operation=([a-f0-9]{64}) -->$/.exec(markers[0] ?? '');
    if (markers.length !== 1 || !marker) reject('OWNER_PUBLICATION_UNVERIFIED');
    const acceptanceMarker = `<!-- jresearchsoftware-reviewer-acceptance:v1 authority_sha256=${request.authority_sha256} -->`;
    if (decisive.body.split(/\r?\n/).filter(line => line.startsWith('<!-- jresearchsoftware-reviewer-acceptance:')).length !== 1
      || !decisive.body.split(/\r?\n/).includes(acceptanceMarker)) reject('OWNER_PUBLICATION_UNVERIFIED');
    const binding = { repository, task: request.task, charterId: issue.id, charterBody: issue.body,
      trustedAuthor: identity(reviewer), trustedWriter: identity(writer), trustedOwner: identity(owner),
      pullRequest: request.pull_request, ...(outcome.authority_resolution ? { authorityResolution: outcome.authority_resolution } : {}) };
    const resolved = resolveOutcomeAuthority(outcome.authority, [...records.values()], binding);
    if (resolved.authority.sha256 !== request.authority_sha256) reject('OWNER_AUTHORITY_CHANGED');
    // Existing helper additionally verifies accepted current authority against
    // original Writer result. This adapter never fabricates a replacement result.
    const receipt = { publication_status: 'verified', repository, task: request.task,
      charter_sha256: sha256Body(issue.body), authority: resolved.authority, admission: outcome.admission,
      approval: request.approval, reviewed_head_sha: request.expected_head_sha,
      ...(request.owner_assessment.exact_base_sha ? { reviewed_base_sha: request.owner_assessment.exact_base_sha } : {}) };
    const [branch, rules, runs, statuses, closing] = await Promise.all([
      api(`${prefix}/branches/${encodeURIComponent(consumer.baseBranch)}`),
      api(`${prefix}/rules/branches/${encodeURIComponent(consumer.baseBranch)}`),
      list(`commits/${request.expected_head_sha}/check-runs?filter=all`, 'check_runs'),
      list(`commits/${request.expected_head_sha}/statuses`),
      api('graphql', { method: 'POST', body: { query: 'query($owner:String!,$name:String!,$number:Int!){repository(owner:$owner,name:$name){pullRequest(number:$number){closingIssuesReferences(first:100){nodes{number repository{nameWithOwner}} pageInfo{hasNextPage}}}}}',
        variables: { owner: repository.split('/')[0], name: repository.split('/')[1], number: request.pull_request } } })
    ]);
    const links = closing.data?.repository?.pullRequest?.closingIssuesReferences;
    if (closing.errors?.length || !links || !Array.isArray(links.nodes) || links.pageInfo?.hasNextPage !== false) reject('OWNER_CLOSING_LINKS_UNAVAILABLE');
    const closesTask = links.nodes.some(value => value.number === request.task && value.repository?.nameWithOwner === repository);
    if (!Array.isArray(rules) || typeof branch.protected !== 'boolean') reject('OWNER_REQUIRED_CHECKS_UNAVAILABLE');
    if (rules.some(rule => rule.type === 'workflows')) reject('OWNER_REQUIRED_CHECKS_CAPABILITY_UNAVAILABLE');
    const requirements = [];
    const addRequirements = items => {
      if (!Array.isArray(items)) reject('OWNER_REQUIRED_CHECKS_UNAVAILABLE');
      for (const item of items) {
        if (typeof item.context !== 'string' || !item.context) reject('OWNER_REQUIRED_CHECKS_UNAVAILABLE');
        requirements.push({ name: item.context, app: item.integration_id ?? item.app_id ?? null });
      }
    };
    for (const rule of rules) if (rule.type === 'required_status_checks') addRequirements(rule.parameters?.required_status_checks);
    if (branch.protected) {
      let protection;
      try { protection = await api(`${prefix}/branches/${encodeURIComponent(consumer.baseBranch)}/protection`); }
      catch (error) {
        // A ruleset-protected branch can have no legacy branch protection.
        // A 403 or an otherwise unproved absence remains a real evidence gap.
        if (error.status !== 404 || rules.length === 0) throw error;
        protection = {};
      }
      const required = protection.required_status_checks;
      if (required != null) addRequirements(required.checks ?? required.contexts?.map(context => ({ context })));
    }
    const publicationCheck = runs.filter(run => run.external_id === marker[1] && String(run.app?.id) === consumer.reviewerApp.appId)
      .sort((a, b) => b.id - a.id)[0];
    if (!publicationCheck || publicationCheck.head_sha !== request.expected_head_sha
      || publicationCheck.status !== 'completed' || publicationCheck.conclusion !== 'success') reject('OWNER_PUBLICATION_CHECK_UNVERIFIED');
    const requiredChecks = [publicationCheck];
    for (const requirement of requirements) {
      const candidates = runs.filter(run => run.name === requirement.name
        && (requirement.app == null || requirement.app === -1 || run.app?.id === requirement.app)).sort((a, b) => b.id - a.id);
      const run = candidates[0];
      const status = statuses.filter(value => value.context === requirement.name).sort((a, b) => b.id - a.id)[0];
      if (run) {
        requiredChecks.push(run);
        // GitHub requires both when a classic status and a check share an
        // unpinned required context. Do not hide a red status behind a green run.
        if ((requirement.app == null || requirement.app === -1) && status) {
          if (status.state !== 'success' || status.sha !== undefined && status.sha !== request.expected_head_sha) reject('OWNER_REQUIRED_CHECKS_UNVERIFIED');
          requiredChecks.push({ head_sha: request.expected_head_sha, status: 'completed', conclusion: 'success' });
        }
      }
      else if ((requirement.app == null || requirement.app === -1) && status?.state === 'success'
        && (status.sha === undefined || status.sha === request.expected_head_sha)) {
        // Commit statuses commonly omit sha; this complete collection was
        // acquired from the exact native commits/<approved-sha>/statuses path.
        requiredChecks.push({ head_sha: request.expected_head_sha, status: 'completed', conclusion: 'success' });
      } else reject('OWNER_REQUIRED_CHECKS_UNVERIFIED');
    }
    return { receipt, state: { binding, nativeRecords: [...records.values()], currentApproval: request.approval,
      task: { number: request.task, hold: request.owner_assessment.hold,
        protectedBoundary: request.owner_assessment.protected_boundary, closed: issue.state === 'closed' },
      pr: { number: pr.number, taskNumber: request.task, headSha: pr.head.sha, baseSha: pr.base.sha,
        merged: pr.merged, mergeCommitSha: pr.merge_commit_sha, state: pr.state, closesTask,
        exactBaseRequired: Boolean(request.owner_assessment.exact_base_sha),
        readiness: pr.draft === false ? 'ready' : 'unknown', mergeability: pr.mergeable === true && pr.mergeable_state === 'clean' ? 'clean' : 'unknown',
        requiredChecksComplete: true, requiredChecks: requiredChecks.map(run => ({ headSha: run.head_sha, status: run.status, conclusion: run.conclusion })) } } };
  }
  return { read, checkTarget, prefix };
}
