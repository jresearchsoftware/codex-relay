import test from 'node:test';
import assert from 'node:assert/strict';
import { admissionBinding, authoritySourceDigest, canonicalAuthorityJson, createAdmissionSnapshot, extractAuthorityRecord, nativeReference,
  resolveTaskAuthority, sha256Body } from '../src/github-authority.mjs';
import { continueAfterApproval } from '../src/post-review-continuation.mjs';

const repository = 'example-org/sample-project';
const reviewer = { login: 'reviewer-app[bot]', id: 7, type: 'Bot' };
const writer = { login: 'writer-app[bot]', id: 8, type: 'Bot' };
const owner = { login: 'owner', id: 9, type: 'User' };
const head = 'a'.repeat(40);
const base = 'b'.repeat(40);
const sourceMarker = '<!-- jresearchsoftware-reviewer-source-pr:v1 -->';
const render = record => '```relay-authority\n' + canonicalAuthorityJson(record) + '\n```\n';

function fixture({ retained = false, policy = 'keep-open', next = false } = {}) {
  const task = retained ? 99 : 106;
  const parent = { kind: 'issue', number: task };
  const branch = `codex/task-${task}`;
  const charter = `Authority model: github-native-v1\nIssue closure policy: ${policy}\n`
    + 'Goal: Permit owner-authorized standalone manual source PR implementation and independent review.\n';
  const common = kind => ({ schema_version: '4.0', kind, repository, task, parent, charter_sha256: sha256Body(charter) });
  const native = (record, id, author = reviewer) => ({ kind: 'issue-comment', repository, id,
    parent: record.parent, author, body: render(record) });
  const records = [{ kind: 'issue-body', repository, id: 1000, parent, author: owner, body: charter }];
  const request = { ...common('task-request'), schema_version: '3.0', step: 1, route: 'manual',
    purpose: 'Owner-authorized standalone source implementation', scope: ['Implement the authorized source change.'],
    model: 'test-model', effort: 'xhigh', subagents: true, validation: ['diff-check'],
    boundaries: ['Direct standalone launch and ordinary owner-channel publication are authorized. Do not route through Relay.', 'No deployment.'],
    decisions: [], context: [], supersedes: null, branch, base_sha: base, starting_head: head,
    existing_pr: 42, issue_closure_policy: policy, continuation: { hold: false, task_complete: false, next: null } };
  if (retained) records.push(native(request, 100));
  const direction = native({ ...common('decision'), purpose: 'Next authorized scope',
    amendments: { scope: ['Next authorized bounded phase'] }, supersedes: null, context: [] }, 200);
  if (next) {
    records.push(direction, native({ ...common('decision'), purpose: 'Authorized next execution',
      amendments: { continuation: { hold: false, next: { task, direction: nativeReference(direction) } } },
      supersedes: null, context: [] }, 201));
  }
  // Reproduces the ordinary owner result from the PR #105 scenario: never a typed
  // Writer Outcome or a second authority source.
  records.push({ kind: 'issue-comment', repository, id: 300, parent, author: owner,
    body: 'Implementation complete through standalone manual Codex. Validation and exact source head are recorded on the PR.' });
  const binding = { repository, task, charterBody: charter, trustedAuthor: reviewer, trustedWriter: writer,
    trustedOwner: owner, route: 'manual', pullRequest: 42,
    startingState: { branch, base_sha: base, starting_head: head, existing_pr: 42 } };
  const resolved = resolveTaskAuthority(records, { ...binding, compatibility: retained });
  const approved = { kind: 'review', repository, id: 501, parent: { kind: 'pull_request', number: 42 },
    author: reviewer, state: 'APPROVED', commit_id: head,
    body: `Independent review accepts the exact source head.\n<!-- jresearchsoftware-reviewer-acceptance:v1 authority_sha256=${resolved.authority.sha256} -->\n${sourceMarker}` };
  records.push(approved);
  const receipt = { publication_status: 'verified', repository, task, charter_sha256: sha256Body(charter),
    authority: resolved.authority, approval: nativeReference(approved), reviewed_head_sha: head, reviewed_base_sha: base,
    source_pr: { repository, number: 42, head_sha: head, branch, author: { ...owner } } };
  const state = { binding, nativeRecords: records, currentApproval: receipt.approval,
    standaloneAuthorization: { authority_sha256: resolved.authority.sha256, pullRequest: 42, headSha: head,
      authorized: true, admittedExecution: false, warningsDispositioned: true },
    task: { number: task, step: 1, complete: false, remainingWork: true, protectedBoundary: false, hold: false, closed: false },
    pr: { number: 42, taskNumber: task, step: 1, author: { ...owner }, branch, headRepository: repository,
      body: `Related to #${task}\nStandalone source implementation.`, headSha: head, baseSha: base, exactBaseRequired: true,
      closesTask: false, state: 'open', merged: false, readiness: 'ready', mergeability: 'clean',
      requiredChecksComplete: true, requiredChecks: [{ headSha: head, status: 'completed', conclusion: 'success' }] } };
  const mutations = [];
  const completed = new Map();
  const ports = {
    readCanonicalState: async () => state,
    reserveAction: async ({ operationId }) => completed.get(operationId) ?? { status: 'reserved', operationId },
    recordActionResult: async ({ operationId, result }) => {
      if (result.status === 'verified') completed.set(operationId, { status: 'completed', operationId, result });
    },
    mergeSquash: async action => {
      assert.equal(action.expectedHeadSha, head);
      assert.equal(action.expectedBaseSha, base);
      assert.equal(action.commitTitle, `Task ${task} implementation`);
      assert.doesNotMatch(action.commitTitle + action.commitBody, /\b(?:closes|fixes|resolves)\b/i);
      mutations.push('merge'); state.pr.merged = true; state.pr.state = 'closed'; state.pr.mergeCommitSha = 'c'.repeat(40);
      return { status: 'verified', mergeCommitSha: state.pr.mergeCommitSha };
    },
    closeIssue: async () => { mutations.push('close'); state.task.closed = true; return { status: 'verified' }; },
    readNextAuthority: async () => ({ binding, nativeRecords: records, protectedBoundary: false }),
    manualHandoff: async action => {
      assert.equal(Object.hasOwn(action, 'step'), false);
      assert.equal(Object.hasOwn(action, 'nextRequest'), false);
      mutations.push('handoff'); return { status: 'verified' };
    }
  };
  const rewriteReview = body => { approved.body = body; receipt.approval = nativeReference(approved); state.currentApproval = receipt.approval; };
  const refreshAuthority = () => {
    const previous = receipt.authority.sha256;
    receipt.authority = resolveTaskAuthority(records, { ...binding, compatibility: retained }).authority;
    state.standaloneAuthorization.authority_sha256 = receipt.authority.sha256;
    rewriteReview(approved.body.replace(previous, receipt.authority.sha256));
  };
  const addOutcome = ({ pr = 42, revision = head, outcomeRequest, typed = true } = {}) => {
    if (!typed) {
      records.push({ kind: 'issue-comment', repository, id: 600, parent: { kind: 'pull_request', number: pr },
        author: writer, body: `## Codex Outcome\nDurable/published head: ${revision}\n<!-- relay:run-123:outcome -->` });
      return;
    }
    const admission = admissionBinding(createAdmissionSnapshot(resolved, { step: 1, attempt: '123', runId: '123' }));
    records.push(native({ ...common('outcome'), parent: pr ? { kind: 'pull_request', number: pr } : parent,
      authority: resolved.authority, admission, step: 1, attempt: '123', status: 'implemented',
      result: { kind: 'git', revision, identities: [] }, warnings: [], limitations: [], summary: 'Admitted execution result.' }, 600, writer));
    if (outcomeRequest) {
      const record = { ...request, kind: 'outcome', step: 1, attempt: '123', status: 'implemented',
        request: outcomeRequest, result: { kind: 'git', revision, identities: [] }, warnings: [], limitations: [], summary: 'Historical admitted result.' };
      for (const key of ['route', 'purpose', 'scope', 'model', 'effort', 'subagents', 'validation', 'boundaries', 'decisions', 'context',
        'supersedes', 'branch', 'base_sha', 'starting_head', 'existing_pr', 'issue_closure_policy', 'continuation']) delete record[key];
      records.at(-1).body = render(record);
    }
  };
  return { receipt, state, records, resolved, approved, ports, mutations, rewriteReview, refreshAuthority, addOutcome, request };
}

for (const retained of [false, true]) {
  test(`${retained ? 'PR #105-style retained Request' : 'current v4 charter'} standalone source approval squashes once without fabricating execution`, async () => {
    const f = fixture({ retained });
    const original = structuredClone(f.receipt);
    assert.equal((await continueAfterApproval(f.receipt, f.ports)).status, 'complete');
    assert.equal((await continueAfterApproval(f.receipt, f.ports)).status, 'complete');
    assert.deepEqual(f.mutations, ['merge']);
    assert.deepEqual(f.receipt, original);
    assert.equal(Object.hasOwn(f.receipt, 'admission'), false);
    assert.equal(Object.hasOwn(f.receipt, 'outcome'), false);
  });
}

test('standalone acceptance retains authoritative closure and next-direction behavior', async () => {
  const closed = fixture({ policy: 'close-authorized' });
  closed.state.task.complete = true; closed.state.task.remainingWork = false;
  assert.equal((await continueAfterApproval(closed.receipt, closed.ports)).status, 'complete');
  assert.deepEqual(closed.mutations, ['merge', 'close']);
  const next = fixture({ next: true });
  assert.equal((await continueAfterApproval(next.receipt, next.ports)).status, 'complete');
  assert.equal((await continueAfterApproval(next.receipt, next.ports)).status, 'complete');
  assert.deepEqual(next.mutations, ['merge', 'handoff']);
});

for (const observation of ['uncertain-response', 'missing-readback', 'missing-merge-sha']) {
  test(`standalone squash retains ${observation} without retrying the merge or closing the Task`, async () => {
    const f = fixture({ policy: 'close-authorized' });
    f.state.task.complete = true;
    f.state.task.remainingWork = false;
    const record = f.ports.recordActionResult;
    f.ports.recordActionResult = async receipt => {
      if (receipt.result.status === 'uncertain') {
        // The trusted adapter retains its original uncertain mutation intent.
        f.ports.reserveAction = async ({ operationId }) => ({ operationId, status: 'uncertain' });
      }
      return record(receipt);
    };
    f.ports.mergeSquash = async () => {
      f.mutations.push('merge');
      if (observation === 'uncertain-response') throw new Error('Native response lost');
      if (observation === 'missing-merge-sha') f.state.pr.merged = true;
      return { status: 'verified', mergeCommitSha: 'c'.repeat(40) };
    };
    const reason = observation === 'uncertain-response' ? 'CONTINUATION_ACTION_UNCERTAIN' : 'CONTINUATION_MERGE_UNVERIFIED';
    assert.equal((await continueAfterApproval(f.receipt, f.ports)).reason, reason);
    assert.equal((await continueAfterApproval(f.receipt, f.ports)).reason, reason);
    assert.deepEqual(f.mutations, ['merge']);
  });
}

test('retained initial manual Request may precede creation of its exact source PR', async () => {
  const f = fixture({ retained: true });
  f.request.existing_pr = null;
  f.records.find(record => record.id === 100).body = render(f.request);
  f.refreshAuthority();
  assert.equal((await continueAfterApproval(f.receipt, f.ports)).status, 'complete');
  assert.deepEqual(f.mutations, ['merge']);
});

const negatives = [
  ['missing owner authorization', f => { delete f.state.standaloneAuthorization; }],
  ['ordinary owner comment is no authority', f => { f.state.standaloneAuthorization.authorized = false; }],
  ['unknown admitted execution', f => { delete f.state.standaloneAuthorization.admittedExecution; }],
  ['admitted manual execution', f => { f.state.standaloneAuthorization.admittedExecution = true; }],
  ['automatic route', f => { f.state.binding.route = 'auto'; }],
  ['undispositioned warnings', f => { f.state.standaloneAuthorization.warningsDispositioned = false; }],
  ['wrong authorized authority', f => { f.state.standaloneAuthorization.authority_sha256 = 'f'.repeat(64); }],
  ['wrong authorized PR', f => { f.state.standaloneAuthorization.pullRequest++; }],
  ['wrong authorized head', f => { f.state.standaloneAuthorization.headSha = 'f'.repeat(40); }],
  ['receipt admission', f => { f.receipt.admission = { step: 1, attempt: '123', sha256: 'f'.repeat(64) }; }],
  ['receipt Outcome', f => { f.receipt.outcome = f.receipt.approval; }],
  ['untrusted owner ID', f => { f.state.binding.trustedOwner = { ...owner, id: 99 }; }],
  ['unknown trusted Writer identity', f => { delete f.state.binding.trustedWriter; }],
  ['Bot source author', f => { f.receipt.source_pr.author.type = 'Bot'; }],
  ['different PR author', f => { f.state.pr.author.id++; }],
  ['foreign receipt repository', f => { f.receipt.source_pr.repository = 'foreign/project'; }],
  ['fork head', f => { f.state.pr.headRepository = 'foreign/project'; }],
  ['wrong source PR', f => { f.receipt.source_pr.number++; }],
  ['wrong source branch', f => { f.receipt.source_pr.branch += '-other'; }],
  ['wrong canonical source branch', f => { f.state.pr.branch += '-other'; }],
  ['changed head', f => { f.state.pr.headSha = 'f'.repeat(40); }],
  ['changed exact base', f => { f.state.pr.baseSha = 'f'.repeat(40); }],
  ['implicit Task closure', f => { f.state.pr.closesTask = true; }],
  ['pending checks', f => { f.state.pr.requiredChecksComplete = false; }],
  ['wrong check head', f => { f.state.pr.requiredChecks[0].headSha = 'f'.repeat(40); }],
  ['failed checks', f => { f.state.pr.requiredChecks[0].conclusion = 'failure'; }],
  ['canonical hold', f => { f.state.task.hold = true; }],
  ['protected boundary', f => { f.state.task.protectedBoundary = true; }],
  ['unknown completion', f => { delete f.state.task.complete; }],
  ['wrong native reviewer', f => { f.approved.author = { ...reviewer, id: 99 }; }],
  ['dismissed native approval', f => { f.approved.state = 'DISMISSED'; }],
  ['wrong native review head', f => { f.approved.commit_id = 'f'.repeat(40); }],
  ['changed current approval', f => { f.state.currentApproval = { ...f.receipt.approval, id: 502 }; }],
  ['changed authority source', f => { f.records[0].body += 'Changed scope.\n'; }],
  ['no source marker', f => { f.rewriteReview(f.approved.body.replace(sourceMarker, '')); }],
  ['duplicate source marker', f => { f.rewriteReview(f.approved.body + '\n' + sourceMarker); }],
  ['malformed source marker', f => { f.rewriteReview(f.approved.body.replace(sourceMarker, '<!-- jresearchsoftware-reviewer-source-pr:v2 -->')); }],
  ['no authority marker', f => { f.rewriteReview(sourceMarker); }],
  ['duplicate authority marker', f => { f.rewriteReview(f.approved.body + '\n' + f.approved.body.split('\n')[1]); }],
  ['wrong authority marker', f => { f.rewriteReview(f.approved.body.replace(f.receipt.authority.sha256, 'f'.repeat(64))); }],
  ['PR admission marker', f => { f.state.pr.body += '\nExecution admission digest: ' + 'f'.repeat(64); }],
  ['missing PR body evidence', f => { delete f.state.pr.body; }],
  ['indented PR admission marker', f => { f.state.pr.body += '\n  Execution admission digest: ' + 'f'.repeat(64); }],
  ['PR legacy request marker', f => { f.state.pr.body += '\nExecution request digest: ' + 'f'.repeat(64); }],
  ['PR attempt marker', f => { f.state.pr.body += '\nAttempt: run-123'; }],
  ['PR native execution marker', f => { f.state.pr.body += '\n<!-- relay:run-123:pr -->'; }],
  ['typed same-PR Writer Outcome', f => { f.addOutcome(); }],
  ['historical same-PR Writer Outcome', f => { f.addOutcome({ typed: false }); }],
  ['exact-head Issue Writer Outcome', f => { f.addOutcome({ pr: null }); }],
  ['ordinary no-PR owner result', f => { f.receipt.approval = nativeReference(f.records.find(record => record.id === 300));
    f.state.currentApproval = f.receipt.approval; f.state.pr = null; }]
];
for (const [name, mutate] of negatives) {
  test(`standalone continuation stops before mutation: ${name}`, async () => {
    const f = fixture(); mutate(f);
    assert.equal((await continueAfterApproval(f.receipt, f.ports)).status, 'stopped');
    assert.deepEqual(f.mutations, []);
  });
}

test('retained Request acceptance rejects automatic, branch, PR and Step mismatches', async () => {
  for (const mutate of [f => { f.request.route = 'auto'; }, f => { f.request.branch += '-other'; },
    f => { f.request.existing_pr = 43; }, f => { f.state.task.step = 2; }, f => { f.state.pr.step = 2; }]) {
    const f = fixture({ retained: true }); mutate(f);
    f.records.find(record => record.id === 100).body = render(f.request);
    f.refreshAuthority();
    assert.equal((await continueAfterApproval(f.receipt, f.ports)).status, 'stopped');
    assert.deepEqual(f.mutations, []);
  }
});

test('current v4 standalone needs no invented execution route or historical Request fallback', async () => {
  const f = fixture();
  delete f.state.binding.route;
  f.records.push({ kind: 'issue-comment', repository, id: 100, parent: { kind: 'issue', number: f.receipt.task }, author: reviewer,
    body: render({ ...f.request, route: 'auto', branch: 'codex/historical', existing_pr: 99 }) });
  assert.equal((await continueAfterApproval(f.receipt, f.ports)).status, 'complete');
  assert.equal(f.receipt.authority.compatibility_request, null);
  assert.deepEqual(f.mutations, ['merge']);
});

test('new trusted Task semantics require fresh native standalone acceptance', async () => {
  const f = fixture();
  f.records.push({ kind: 'issue-comment', repository, id: 502, parent: { kind: 'issue', number: f.receipt.task }, author: reviewer,
    body: render({ schema_version: '4.0', kind: 'decision', repository, task: f.receipt.task,
      parent: { kind: 'issue', number: f.receipt.task }, charter_sha256: f.receipt.charter_sha256,
      purpose: 'Current requirement amendment', amendments: { scope: ['Additional current requirement'] }, supersedes: null, context: [] }) });
  assert.equal((await continueAfterApproval(f.receipt, f.ports)).reason, 'AUTHORITY_APPROVAL_STALE_REQUEST');
  f.receipt.authority = resolveTaskAuthority(f.records, { ...f.state.binding, compatibility: false }).authority;
  f.state.standaloneAuthorization.authority_sha256 = f.receipt.authority.sha256;
  assert.equal((await continueAfterApproval(f.receipt, f.ports)).reason, 'CONTINUATION_APPROVAL_UNVERIFIED');
  assert.deepEqual(f.mutations, []);
});

test('same retained Request Writer result cannot be bypassed as standalone', async () => {
  for (const v4 of [false, true]) {
    const f = fixture({ retained: true });
    f.addOutcome({ pr: null, revision: 'd'.repeat(40), ...(v4 ? {} : { outcomeRequest: f.receipt.authority.compatibility_request }) });
    assert.equal((await continueAfterApproval(f.receipt, f.ports)).status, 'stopped');
    assert.deepEqual(f.mutations, []);
  }
});

test('unrelated historical Writer result does not block current standalone source acceptance', async () => {
  const f = fixture();
  f.addOutcome({ pr: 99, revision: 'd'.repeat(40) });
  const previous = extractAuthorityRecord(f.records.at(-1).body);
  previous.authority.charter.sha256 = 'e'.repeat(64);
  previous.authority.sha256 = authoritySourceDigest(previous.authority);
  f.records.at(-1).body = render({ ...previous, charter_sha256: 'e'.repeat(64) });
  assert.equal((await continueAfterApproval(f.receipt, f.ports)).status, 'complete');
  assert.deepEqual(f.mutations, ['merge']);
});

test('standalone authorization is re-read after reservation before every effect', async () => {
  const f = fixture();
  f.ports.reserveAction = async ({ operationId }) => {
    f.state.standaloneAuthorization.authorized = false;
    return { status: 'reserved', operationId };
  };
  assert.equal((await continueAfterApproval(f.receipt, f.ports)).reason, 'CONTINUATION_STANDALONE_UNVERIFIED');
  assert.deepEqual(f.mutations, []);
});

test('an admitted receipt cannot lose its admission and become a standalone native review', async () => {
  const f = fixture();
  f.rewriteReview(f.approved.body.replace(sourceMarker, ''));
  assert.equal((await continueAfterApproval(f.receipt, f.ports)).reason, 'CONTINUATION_APPROVAL_UNVERIFIED');
  assert.deepEqual(f.mutations, []);
  delete f.receipt.source_pr;
  assert.equal((await continueAfterApproval(f.receipt, f.ports)).reason, 'CONTINUATION_AUTHORITY_CHANGED');
});

test('a standalone native review cannot bypass its authorization through a retained receipt', async () => {
  const f = fixture({ retained: true });
  f.receipt.request = f.receipt.authority.compatibility_request;
  delete f.receipt.authority;
  delete f.receipt.source_pr;
  delete f.state.standaloneAuthorization;
  assert.equal((await continueAfterApproval(f.receipt, f.ports)).reason, 'CONTINUATION_APPROVAL_UNVERIFIED');
  assert.deepEqual(f.mutations, []);
});

test('an authority-bound admitted native review cannot downgrade to a retained receipt', async () => {
  const f = fixture({ retained: true });
  f.rewriteReview(f.approved.body.replace(sourceMarker, ''));
  f.receipt.request = f.receipt.authority.compatibility_request;
  delete f.receipt.authority;
  delete f.receipt.source_pr;
  delete f.state.standaloneAuthorization;
  assert.equal((await continueAfterApproval(f.receipt, f.ports)).reason, 'CONTINUATION_APPROVAL_UNVERIFIED');
  assert.deepEqual(f.mutations, []);
});

test('retained Request source acceptance also checks current Decision branch and PR identity', async () => {
  for (const amendments of [{ branch: 'codex/another-branch' }, { existing_pr: 43 }]) {
    const f = fixture({ retained: true });
    f.records.push({ kind: 'issue-comment', repository, id: 200, parent: { kind: 'issue', number: f.receipt.task }, author: reviewer,
      body: render({ schema_version: '4.0', kind: 'decision', repository, task: f.receipt.task,
        parent: { kind: 'issue', number: f.receipt.task }, charter_sha256: f.receipt.charter_sha256,
        purpose: 'Current source identity', amendments, supersedes: null, context: [] }) });
    f.refreshAuthority();
    assert.equal((await continueAfterApproval(f.receipt, f.ports)).reason, 'CONTINUATION_STANDALONE_UNVERIFIED');
    assert.deepEqual(f.mutations, []);
  }
});

test('retained request-only next stays visible after source squash without launching fresh v3 work', async () => {
  for (const overridden of [false, true]) {
    const f = fixture({ retained: true });
    f.request.continuation.next = { task: 107, request: { kind: 'issue-comment', id: 900,
      parent: { kind: 'issue', number: 107 }, sha256: 'f'.repeat(64) } };
    f.records.find(record => record.id === 100).body = render(f.request);
    if (overridden) f.records.push({ kind: 'issue-comment', repository, id: 200,
      parent: { kind: 'issue', number: f.receipt.task }, author: reviewer,
      body: render({ schema_version: '4.0', kind: 'decision', repository, task: f.receipt.task,
        parent: { kind: 'issue', number: f.receipt.task }, charter_sha256: f.receipt.charter_sha256,
        purpose: 'Supersede the old follow-up direction', amendments: { continuation: { hold: false, next: null } },
        supersedes: null, context: [] }) });
    f.refreshAuthority();
    for (let repeat = 0; repeat < 2; repeat++) {
      const result = await continueAfterApproval(f.receipt, f.ports);
      assert.equal(result.status, overridden ? 'complete' : 'stopped');
      if (!overridden) assert.equal(result.reason, 'CONTINUATION_NEXT_AUTHORITY_INVALID');
    }
    assert.deepEqual(f.mutations, ['merge']);
  }
});

test('no-PR automatic Task Approval still requires an authenticated Writer Outcome', async () => {
  const f = fixture();
  const admission = { step: 1, attempt: '123', sha256: 'd'.repeat(64) };
  const approval = { schema_version: '4.0', kind: 'task-approval', repository, task: f.receipt.task,
    parent: { kind: 'issue', number: f.receipt.task }, charter_sha256: f.receipt.charter_sha256,
    authority: f.receipt.authority, admission, outcome: { kind: 'issue-comment', id: 999,
      parent: { kind: 'issue', number: f.receipt.task }, sha256: 'e'.repeat(64) }, step: 1,
    result: { kind: 'no-change', revision: head, identities: [] }, warnings: [], limitations: [],
    summary: 'Automatic result approval without Writer evidence.', verdict: 'APPROVE' };
  f.approved.kind = 'issue-comment'; f.approved.parent = approval.parent; f.approved.body = render(approval);
  f.receipt.approval = nativeReference(f.approved); f.state.currentApproval = f.receipt.approval;
  f.receipt.admission = admission; delete f.receipt.source_pr; f.state.pr = null;
  f.state.binding.route = 'auto';
  assert.equal((await continueAfterApproval(f.receipt, f.ports)).status, 'stopped');
  assert.deepEqual(f.mutations, []);
});
