import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { mkdtemp, writeFile, readFile, mkdir, symlink } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { runOwnerContinuation } from '../src/owner-continuation.mjs';
import { createOwnerGithub } from '../src/owner-native.mjs';
import { admissionBinding, canonicalAuthorityJson, createAdmissionSnapshot, nativeReference,
  extractAuthorityRecord, resolveTaskAuthority, sha256Body } from '../src/github-authority.mjs';

const repository = 'example-org/sample-project';
const head = 'a'.repeat(40), base = 'b'.repeat(40), merge = 'c'.repeat(40), operation = 'd'.repeat(64);
const owner = { login: 'example-owner', id: 1, type: 'User' };
const reviewer = { login: 'example-reviewer[bot]', id: 2, type: 'Bot' };
const writer = { login: 'example-writer[bot]', id: 3, type: 'Bot' };
const configPath = fileURLToPath(new URL('../../consumer/fixtures/example.json', import.meta.url));
const consumer = JSON.parse(await readFile(configPath, 'utf8'));
const render = value => `\`\`\`relay-authority\n${canonicalAuthorityJson(value)}\n\`\`\`\n`;

async function fixture(t, { hold = false } = {}) {
  const root = await mkdtemp(join(tmpdir(), 'relay-owner-native-'));
  const charter = 'Authority model: github-native-v1\nIssue closure policy: keep-open\nGoal: Bounded source integration; no Apply.';
  const issue = { id: 1000, number: 23, body: charter, user: owner, state: 'open' };
  const pr = { number: 25, body: 'Related to #23', user: writer, state: 'open', draft: false,
    merged: false, mergeable: true, mergeable_state: 'clean', merge_commit_sha: null,
    base: { ref: 'main', sha: base, repo: { full_name: repository } },
    head: { ref: 'codex/task-23', sha: head, repo: { full_name: repository } } };
  const records = [{ kind: 'issue-body', repository, id: issue.id, parent: { kind: 'issue', number: 23 }, body: charter, author: owner }];
  const decisions = [];
  if (hold) {
    const value = { schema_version: '4.0', kind: 'decision', repository, task: 23, parent: { kind: 'issue', number: 23 },
      charter_sha256: sha256Body(charter), purpose: 'Hold source integration', amendments: { continuation: { hold: true, next: null } }, supersedes: null, context: [] };
    decisions.push({ id: 200, user: reviewer, body: render(value), issue_url: `https://api.github.com/repos/${repository}/issues/23` });
    records.push({ ...decisions[0], author: reviewer, repository, kind: 'issue-comment', parent: value.parent });
  }
  const resolved = resolveTaskAuthority(records, { repository, task: 23, charterBody: charter, trustedAuthor: reviewer,
    route: 'manual', startingState: { branch: pr.head.ref, base_sha: base, starting_head: head, existing_pr: 25 } });
  const admission = admissionBinding(createAdmissionSnapshot(resolved, { step: 1, attempt: '123', runId: '123' }));
  const outcome = { schema_version: '4.0', kind: 'outcome', repository, task: 23, parent: { kind: 'pull_request', number: 25 },
    charter_sha256: sha256Body(charter), authority: resolved.authority, admission, step: 1, attempt: '123', status: 'implemented',
    result: { kind: 'git', revision: head, identities: [] }, warnings: [], limitations: [], summary: 'Bounded implementation.' };
  const outcomeNative = { id: 500, user: writer, body: render(outcome), issue_url: `https://api.github.com/repos/${repository}/issues/25` };
  const review = { id: 501, user: reviewer, state: 'APPROVED', commit_id: head,
    body: `Exact-head accepted.\n\n<!-- jresearchsoftware-reviewer-relay:v1 operation=${operation} -->\n<!-- jresearchsoftware-reviewer-acceptance:v1 authority_sha256=${resolved.authority.sha256} -->`,
    pull_request_url: `https://api.github.com/repos/${repository}/pulls/25` };
  const request = { repository, task: 23, pull_request: 25, expected_head_sha: head,
    authority_sha256: resolved.authority.sha256,
    approval: nativeReference({ ...review, repository, kind: 'review', parent: { kind: 'pull_request', number: 25 } }),
    owner_assessment: { hold: false, protected_boundary: false } };
  const checks = [
    { id: 600, name: 'review', app: { id: 102 }, external_id: operation, head_sha: head, status: 'completed', conclusion: 'success' },
    { id: 601, name: 'qualification', app: { id: 999 }, head_sha: head, status: 'completed', conclusion: 'success' }
  ];
  const state = { viewer: owner, issue, pr, review, outcomeNative, decisions, checks, puts: [], calls: [],
    rules: [{ type: 'required_status_checks', parameters: { required_status_checks: [{ context: 'qualification', integration_id: 999 }] } }],
    closing: [], statuses: [], extraTaskComments: [], extraPrComments: [], protected: false, protection: {}, loseMergeResponse: false, readbackUnavailable: false, rejectMerge: false };
  const server = createServer(async (req, res) => {
    const url = new URL(req.url, 'http://localhost');
    let raw = ''; for await (const part of req) raw += part;
    const payload = raw ? JSON.parse(raw) : undefined;
    const path = url.pathname.replace(/^\//, ''); state.calls.push([req.method, path]);
    let value;
    if (path === 'user') value = state.viewer;
    else if (path === `users/${owner.login}`) value = owner;
    else if (path === `users/${reviewer.login}`) value = reviewer;
    else if (path === `users/${writer.login}`) value = writer;
    else if (path === `repos/${repository}/issues/23`) value = issue;
    else if (path === `repos/${repository}/issues/23/comments`) value = [...decisions, ...state.extraTaskComments];
    else if (path === `repos/${repository}/issues/25/comments`) value = [outcomeNative, ...state.extraPrComments];
    else if (path === `repos/${repository}/pulls/25/reviews`) value = [review];
    else if (path === `repos/${repository}/pulls/25`) {
      if (pr.merged && state.readbackUnavailable) { res.writeHead(503); res.end('{}'); return; }
      value = pr;
    } else if (path === `repos/${repository}/branches/main`) value = { protected: state.protected };
    else if (path === `repos/${repository}/branches/main/protection`) value = state.protection;
    else if (path === `repos/${repository}/rules/branches/main`) value = state.rules;
    else if (path === `repos/${repository}/commits/${head}/check-runs`) value = { total_count: checks.length, check_runs: checks };
    else if (path === `repos/${repository}/commits/${head}/statuses`) value = state.statuses;
    else if (path === `repos/${repository}/commits/${merge}`) value = { sha: merge, parents: [{ sha: base }] };
    else if (path === 'graphql') value = { data: { repository: { pullRequest: { closingIssuesReferences: { nodes: state.closing, pageInfo: { hasNextPage: false } } } } } };
    else if (path === `repos/${repository}/pulls/25/merge` && req.method === 'PUT') {
      state.puts.push(payload);
      if (state.rejectMerge) { res.writeHead(503); res.end('{}'); return; }
      assert.equal(payload.merge_method, 'squash'); assert.equal(payload.sha, head);
      assert.ok(!/Closes|Fixes|Resolves|#23/i.test(payload.commit_title + payload.commit_message));
      pr.merged = true; pr.state = 'closed'; pr.merge_commit_sha = merge; pr.merged_by = owner;
      if (state.loseMergeResponse) { req.socket.destroy(); return; }
      value = { merged: true, sha: merge };
    } else { res.writeHead(404); res.end('{}'); return; }
    res.writeHead(200, { 'content-type': 'application/json' }); res.end(JSON.stringify(value));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise(resolve => { server.closeAllConnections(); server.close(resolve); }));
  const url = `http://127.0.0.1:${server.address().port}/`;
  const api = async (path, { method = 'GET', body } = {}) => {
    const response = await fetch(url + path, { method, body: body === undefined ? undefined : JSON.stringify(body) });
    if (!response.ok) throw Object.assign(new Error('OWNER_NATIVE_UNAVAILABLE'), { code: 'OWNER_NATIVE_UNAVAILABLE' });
    return response.json();
  };
  return { root, state, request, api, url, run: () => runOwnerContinuation(request, { consumer, api, storeRoot: root }) };
}

test('native owner adapter executes guarded squash and repeat reads without closure or relaunch', async t => {
  const f = await fixture(t);
  const result = await f.run();
  assert.equal(result.status, 'complete', JSON.stringify(result));
  assert.equal(result.scope, 'merge-only');
  assert.equal(result.task_continuation, 'OWNER_INTERPRETATION_CAPABILITY_REQUIRED');
  assert.equal((await f.run()).status, 'complete');
  assert.equal(f.state.puts.length, 1);
  assert.equal(f.state.issue.state, 'open');
  assert.equal(f.state.calls.some(([method, path]) => method !== 'GET' && path !== 'graphql' && !path.endsWith('/merge')), false);
});

test('lost merge response reconciles native owner squash without another PUT', async t => {
  const f = await fixture(t); f.state.loseMergeResponse = true;
  assert.equal((await f.run()).status, 'complete');
  assert.equal((await f.run()).status, 'complete');
  assert.equal(f.state.puts.length, 1);
});

test('uncertain merge stays reserved until exact native readback and never repeats mutation', async t => {
  const f = await fixture(t); f.state.readbackUnavailable = true;
  assert.equal((await f.run()).reason, 'CONTINUATION_ACTION_UNCERTAIN');
  f.state.readbackUnavailable = false;
  const recovered = await f.run();
  assert.equal(recovered.status, 'complete', JSON.stringify(recovered));
  assert.equal(recovered.actions[0].status, 'already-completed');
  assert.equal(f.state.puts.length, 1);
  const absent = await fixture(t); absent.state.rejectMerge = true;
  assert.equal((await absent.run()).reason, 'CONTINUATION_ACTION_UNCERTAIN');
  assert.equal((await absent.run()).reason, 'CONTINUATION_ACTION_UNCERTAIN');
  assert.equal(absent.state.puts.length, 1);
});

test('concurrent owner processes serialize one exact action and stale assessments are refused', async t => {
  const f = await fixture(t);
  const results = await Promise.allSettled([f.run(), f.run()]);
  assert.ok(results.some(result => result.status === 'fulfilled' && result.value.status === 'complete'));
  assert.equal(f.state.puts.length, 1);
  f.request.owner_assessment.hold = true;
  await assert.rejects(f.run(), { code: 'OWNER_ACTION_BINDING_CHANGED' });
});

test('native hold and interpreted protected boundary stop before merge', async t => {
  for (const change of [null, 'protected']) {
    const f = await fixture(t, { hold: change === null });
    if (change) f.request.owner_assessment.protected_boundary = true;
    assert.equal((await f.run()).reason, 'CONTINUATION_PROTECTED_BOUNDARY');
    assert.equal(f.state.puts.length, 0);
  }
});

test('native check changes after reservation cannot consume a stale owner assessment', async t => {
  const f = await fixture(t); let reads = 0;
  const api = async (path, options) => {
    if (path === `repos/${repository}/pulls/25` && ++reads === 3) f.state.checks[1].conclusion = 'failure';
    return f.api(path, options);
  };
  const result = await runOwnerContinuation(f.request, { consumer, api, storeRoot: f.root });
  assert.equal(result.reason, 'CONTINUATION_NOT_READY');
  assert.equal(f.state.puts.length, 0);
  f.state.checks[1].conclusion = 'success';
  f.request.owner_assessment.protected_boundary = true;
  assert.equal((await f.run()).reason, 'CONTINUATION_PROTECTED_BOUNDARY');
  f.request.owner_assessment.protected_boundary = false;
  assert.equal((await f.run()).status, 'complete');
  assert.equal(f.state.puts.length, 1);
});

test('legacy branch protection and classic status contexts use their authoritative native APIs', async t => {
  const f = await fixture(t); f.state.protected = true;
  f.state.protection = { required_status_checks: { contexts: ['legacy-status'] } };
  f.state.statuses.push({ id: 700, context: 'legacy-status', state: 'success' });
  assert.equal((await f.run()).status, 'complete');
  assert.ok(f.state.calls.some(([, path]) => path.endsWith('/branches/main/protection')));
});

test('required exact-base capability is refused before any read, reservation or merge', async t => {
  const f = await fixture(t); f.request.owner_assessment.exact_base_sha = merge;
  await assert.rejects(f.run(), { code: 'OWNER_EXACT_BASE_CAPABILITY_UNAVAILABLE' });
  assert.equal(f.state.calls.length, 0);
  assert.equal(f.state.puts.length, 0);
  await assert.rejects(readFile(join(f.root, 'repositories/example-org/sample-project/501.json')), { code: 'ENOENT' });
});

test('a missing owner assessment stops before mutation', async t => {
  const missing = await fixture(t); delete missing.request.owner_assessment.protected_boundary;
  await assert.rejects(missing.run(), { code: 'OWNER_INTERPRETATION_REQUIRED' });
});

test('clearing an unreserved transient hold or protected boundary needs no new handoff or approval', async t => {
  for (const field of ['hold', 'protected_boundary']) {
    const f = await fixture(t); f.request.owner_assessment[field] = true;
    assert.equal((await f.run()).reason, 'CONTINUATION_PROTECTED_BOUNDARY');
    assert.equal(f.state.puts.length, 0);
    await assert.rejects(readFile(join(f.root, 'repositories/example-org/sample-project/501.json')), { code: 'ENOENT' });
    f.request.owner_assessment[field] = false;
    assert.equal((await f.run()).status, 'complete');
    assert.equal((await f.run()).status, 'complete');
    assert.equal(f.state.puts.length, 1);
  }
});

function nextSameHeadOutcome(f, { amend = false } = {}) {
  const previous = extractAuthorityRecord(f.state.outcomeNative.body, { repository, task: 23 });
  const records = [{ kind: 'issue-body', id: f.state.issue.id, repository, parent: { kind: 'issue', number: 23 },
    author: owner, body: f.state.issue.body }];
  if (amend) {
    const value = { schema_version: '4.0', kind: 'decision', repository, task: 23, parent: { kind: 'issue', number: 23 },
      charter_sha256: sha256Body(f.state.issue.body), purpose: 'Authorize the bounded no-change continuation',
      amendments: { scope: ['Verify the existing same-head implementation under the accepted continuation.'] }, supersedes: null, context: [] };
    const native = { id: 200, user: reviewer, body: render(value), issue_url: `https://api.github.com/repos/${repository}/issues/23` };
    f.state.decisions.push(native);
    records.push({ ...native, kind: 'issue-comment', repository, author: reviewer, parent: value.parent });
  }
  const selected = resolveTaskAuthority(records, { repository, task: 23, charterBody: f.state.issue.body, trustedAuthor: reviewer,
    route: 'manual', startingState: { branch: 'codex/task-23', base_sha: base, starting_head: head, existing_pr: 25 } });
  const admission = admissionBinding(createAdmissionSnapshot(selected, { step: 2, attempt: '124', runId: '124' }));
  const current = { ...previous, authority: selected.authority, admission, step: 2, attempt: '124',
    result: { kind: 'no-change', revision: head, identities: [{ kind: 'qualification', id: 'run-124' }] } };
  f.state.outcomeNative.body = render(current);
  f.state.review.body = f.state.review.body.replace(f.request.authority_sha256, selected.authority.sha256);
  f.request.authority_sha256 = selected.authority.sha256;
  f.request.approval = nativeReference({ ...f.state.review, kind: 'review', repository, parent: { kind: 'pull_request', number: 25 } });
  return { id: 490, user: writer, body: render(previous), issue_url: `https://api.github.com/repos/${repository}/issues/25` };
}

test('a later same-head no-change result selects exact approved current authority without rejecting older Outcome history', async t => {
  const f = await fixture(t);
  f.state.extraPrComments.push(nextSameHeadOutcome(f, { amend: true }));
  assert.equal((await f.run()).status, 'complete');
  assert.equal(f.state.puts.length, 1);
});

test('a historical other-parent result does not compete with the reviewed PR result', async t => {
  const f = await fixture(t);
  const previous = nextSameHeadOutcome(f);
  const value = extractAuthorityRecord(previous.body, { repository, task: 23 });
  value.parent = { kind: 'issue', number: 23 };
  previous.body = render(value); previous.issue_url = `https://api.github.com/repos/${repository}/issues/23`;
  f.state.extraTaskComments.push(previous);
  assert.equal((await f.run()).status, 'complete');
  assert.equal(f.state.puts.length, 1);
});

test('same-authority same-head PR admissions remain ambiguous without native admission provenance', async t => {
  const f = await fixture(t);
  f.state.extraPrComments.push(nextSameHeadOutcome(f));
  await assert.rejects(f.run(), { code: 'OWNER_ADMITTED_OUTCOME_REQUIRED' });
  assert.equal(f.state.puts.length, 0);
});

test('native authority/head/publication/check/closure changes fail closed', async t => {
  for (const change of [
    f => { f.state.pr.head.sha = merge; },
    f => { f.state.review.body += '\nEdited review'; },
    f => { f.state.checks[0].external_id = 'e'.repeat(64); },
    f => { f.state.checks[1].status = 'in_progress'; },
    f => { f.state.checks[1].conclusion = 'failure'; },
    f => { f.state.pr.mergeable = null; },
    f => { f.state.pr.draft = true; },
    f => { f.state.viewer = writer; },
    f => { f.state.issue.body += '\nChanged charter.'; },
    f => { f.state.closing.push({ number: 23, repository: { nameWithOwner: repository } }); }
  ]) {
    const f = await fixture(t); change(f);
    const result = await f.run().catch(error => ({ status: 'stopped', reason: error.code }));
    assert.equal(result.status, 'stopped', JSON.stringify(result));
    assert.equal(f.state.puts.length, 0);
  }
});

test('unsafe and unreadable existing intent cannot be replaced', async t => {
  for (const malformed of [true, false]) {
    const f = await fixture(t);
    const directory = join(f.root, 'repositories', 'example-org', 'sample-project');
    await mkdir(directory, { recursive: true });
    if (malformed) await writeFile(join(directory, '501.json'), '{incomplete');
    else {
      const target = join(f.root, 'foreign.json'); await writeFile(target, '{}');
      try { await symlink(target, join(directory, '501.json')); }
      catch (error) { if (error.code === 'EPERM') { t.diagnostic('Native symlink case requires Linux permissions.'); continue; } throw error; }
    }
    await assert.rejects(f.run(), error => ['ATTEMPT_RECORD_UNREADABLE', 'OWNER_JOURNAL_UNSAFE'].includes(error.code));
    assert.equal(f.state.puts.length, 0);
  }
});

test('actual owner CLI uses gh transport against synthetic HTTP, with no live credentials', async t => {
  const f = await fixture(t);
  const syntheticConfig = join(f.root, 'consumer.json');
  await writeFile(syntheticConfig, JSON.stringify(consumer), { mode: 0o600 });
  const fakeGh = join(f.root, 'fake-gh.mjs');
  await writeFile(fakeGh, `const args=process.argv.slice(2);const endpoint=args[args.indexOf('--method')+2];const method=args[args.indexOf('--method')+1];let body='';for await(const p of process.stdin)body+=p;const r=await fetch(process.env.OWNER_FIXTURE_URL+endpoint,{method,body:body||undefined});process.stdout.write(await r.text());if(!r.ok)process.exitCode=1;`);
  const preload = join(f.root, 'preload.mjs');
  await writeFile(preload, `import cp from 'node:child_process';import {syncBuiltinESMExports} from 'node:module';const original=cp.spawn;cp.spawn=(command,args,options)=>command==='gh'?original(process.execPath,[${JSON.stringify(fakeGh)},...args],options):original(command,args,options);syncBuiltinESMExports();`);
  // This synthetic-only preload replaces gh; production CLI has no endpoint
  // override, certificate bypass or test fixture environment capability.
  const cli = fileURLToPath(new URL('../src/owner-continuation.mjs', import.meta.url));
  let cliHome = f.root;
  const runCli = () => new Promise((resolve, reject) => {
    const child = spawn(process.execPath, ['--import', preload, cli], { windowsHide: true,
      env: { ...process.env, HOME: cliHome, USERPROFILE: cliHome, RELAY_CONSUMER_CONFIG: syntheticConfig, OWNER_FIXTURE_URL: f.url,
        GH_TOKEN: '', GITHUB_TOKEN: '', NODE_OPTIONS: '' }, stdio: ['pipe', 'pipe', 'pipe'] });
    let out = '', err = ''; child.stdout.on('data', p => { out += p; }); child.stderr.on('data', p => { err += p; });
    child.on('error', reject); child.on('close', code => resolve({ code, out, err })); child.stdin.end(JSON.stringify(f.request));
  });
  const first = await runCli();
  assert.equal(first.code, 0, first.out + first.err);
  assert.equal(JSON.parse(first.out).status, 'complete', first.out);
  assert.equal((await runCli()).code, 0);
  assert.equal(f.state.puts.length, 1);
  // Stopped shared-helper results must also produce a failing process status.
  const stopped = await fixture(t, { hold: true });
  f.request = stopped.request;
  cliHome = stopped.root;
  const originalUrl = f.url; f.url = stopped.url;
  const stopResult = await runCli();
  assert.equal(stopResult.code, 1, stopResult.out + stopResult.err);
  assert.equal(JSON.parse(stopResult.out).reason, 'CONTINUATION_PROTECTED_BOUNDARY');
  f.url = originalUrl;
  // Also exercise the real bounded transport directly with its injectable spawn.
  const transport = createOwnerGithub({ spawnImpl: (_command, args, options) => spawn(process.execPath, [fakeGh, ...args], {
    ...options, env: { ...process.env, OWNER_FIXTURE_URL: f.url } }) });
  assert.equal((await transport('user')).login, owner.login);
});
