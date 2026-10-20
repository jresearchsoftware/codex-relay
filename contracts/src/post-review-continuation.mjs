import {
  authorityMode, canonicalAuthorityJson, extractAuthorityRecord, nativeReference, referenceKey,
  selectCurrentRequest, sha256Body, stableClosurePolicy, validateTaskApproval, resolveTaskAuthority, resolveOutcomeAuthority
} from './github-authority.mjs';

const sha = value => typeof value === 'string' && /^[a-f0-9]{40}$/.test(value);
const same = (left, right) => canonicalAuthorityJson(left) === canonicalAuthorityJson(right);
const stop = code => { throw Object.assign(new Error(code), { code }); };
const trusted = (native, identity) => identity && typeof identity.login === 'string' && identity.login.length > 0
  && Number.isSafeInteger(identity.id) && identity.id > 0 && identity.type === 'Bot'
  && native.author?.login === identity.login && native.author?.id === identity.id && native.author?.type === 'Bot';
const defaults = { hold: false, task_complete: false, next: null };
const requiredPorts = ['readCanonicalState', 'reserveAction', 'recordActionResult'];
const sourcePrMarker = '<!-- jresearchsoftware-reviewer-source-pr:v1 -->';

function standaloneSourcePr(receipt, state, binding, current, native) {
  const source = receipt.source_pr;
  const pr = state.pr;
  const owner = binding.trustedOwner;
  const identity = value => owner && typeof owner.login === 'string' && owner.login.length > 0
    && Number.isSafeInteger(owner.id) && owner.id > 0 && owner.type === 'User'
    && value?.login === owner.login && value?.id === owner.id && value?.type === 'User';
  const authorization = state.standaloneAuthorization;
  // These semantic facts come from the existing trusted owner adapter, not
  // receipt assertions, PR authorship or an ordinary result comment.
  if (!source || receipt.admission != null || receipt.outcome != null || native.kind !== 'review'
    || !trusted({ author: binding.trustedWriter }, binding.trustedWriter)
    || !identity(source.author) || !identity(pr?.author) || source.repository !== receipt.repository
    || pr.headRepository !== receipt.repository || source.number !== pr.number
    || source.head_sha !== receipt.reviewed_head_sha || source.head_sha !== pr.headSha
    || !sha(source.head_sha) || typeof source.branch !== 'string' || source.branch.length === 0
    || source.branch !== pr.branch || current.request.route === 'auto'
    || authorization?.authority_sha256 !== receipt.authority.sha256
    || authorization.pullRequest !== source.number || authorization.headSha !== source.head_sha
    || authorization.authorized !== true || authorization.admittedExecution !== false
    || authorization.warningsDispositioned !== true) stop('CONTINUATION_STANDALONE_UNVERIFIED');
  const retained = current.compatibilityRequest;
  if (receipt.authority.compatibility_request !== null) {
    if (!retained || !same(retained.reference, receipt.authority.compatibility_request)
      || retained.request.route !== 'manual' || retained.request.branch !== source.branch
      || retained.request.existing_pr !== null && retained.request.existing_pr !== source.number
      || retained.request.step !== state.task.step
      || retained.request.step !== pr.step) stop('CONTINUATION_STANDALONE_UNVERIFIED');
  }
  if (current.request.existing_pr !== null && current.request.existing_pr !== source.number
    || current.request.branch !== null && current.request.branch !== source.branch) stop('CONTINUATION_STANDALONE_UNVERIFIED');
  if (typeof pr.body !== 'string' || pr.body.split(/\r?\n/).some(line =>
    /^(?:Attempt:|Execution admission digest:|Execution request digest:)/.test(line.trim()))
    || pr.body.includes('<!-- relay:')) stop('CONTINUATION_STANDALONE_UNVERIFIED');
  for (const record of state.nativeRecords) {
    if (record.kind !== 'issue-comment' || !trusted(record, binding.trustedWriter)) continue;
    if (record.parent.kind === 'pull_request' && record.parent.number === source.number
      && (/^## Codex Outcome\b/m.test(record.body) || record.body.includes('<!-- relay:'))) stop('CONTINUATION_STANDALONE_UNVERIFIED');
    const outcome = extractAuthorityRecord(record.body, { repository: receipt.repository });
    if (outcome?.kind !== 'outcome') continue;
    if (record.parent.kind === 'pull_request' && record.parent.number === source.number
      || outcome.authority?.change_request?.parent.number === source.number
      || outcome.task === receipt.task && (outcome.result.revision === source.head_sha
        || retained && (same(outcome.request, retained.reference)
          || same(outcome.authority?.compatibility_request, retained.reference)))) stop('CONTINUATION_STANDALONE_UNVERIFIED');
  }
}

function acceptedState(receipt, state, transition = null) {
  const binding = state?.binding;
  if (!binding || binding.repository !== receipt.repository || binding.task !== receipt.task
    || sha256Body(binding.charterBody) !== receipt.charter_sha256 || !Array.isArray(state.nativeRecords)
    || !same(state.currentApproval, receipt.approval)
    || state.task?.number !== receipt.task || typeof state.task.remainingWork !== 'boolean'
    || typeof state.task.protectedBoundary !== 'boolean' || typeof state.task.hold !== 'boolean'
    || typeof state.task.closed !== 'boolean') stop('CONTINUATION_AUTHORITY_CHANGED');
  const native = state.nativeRecords.find(record => referenceKey(record) === referenceKey(receipt.approval));
  if (!native || native.repository !== receipt.repository || !same(nativeReference(native), receipt.approval)
    || !trusted(native, binding.trustedAuthor)) stop('CONTINUATION_APPROVAL_UNVERIFIED');
  if (!receipt.authority && native.body.split(/\r?\n/).some(line =>
    line.startsWith('<!-- jresearchsoftware-reviewer-source-pr:')
      || line.startsWith('<!-- jresearchsoftware-reviewer-acceptance:'))) stop('CONTINUATION_APPROVAL_UNVERIFIED');
  let current;
  if (authorityMode(binding.charterBody) === 'github-native-v1') {
    if (receipt.authority) {
      current = resolveOutcomeAuthority(receipt.authority, state.nativeRecords, binding);
      // Receipt authority is the independently accepted current Task, rather
      // than the immutable authority of the execution's historical Outcome.
      if (!same(current.authority, receipt.authority)) stop('AUTHORITY_APPROVAL_STALE_REQUEST');
      if (Object.hasOwn(receipt, 'source_pr')) standaloneSourcePr(receipt, state, binding, current, native);
      else if (!receipt.admission || receipt.admission.step < 1 || !Number.isSafeInteger(receipt.admission.step)
        || !/^[a-f0-9]{64}$/.test(receipt.admission.sha256)) stop('CONTINUATION_AUTHORITY_CHANGED');
      if (typeof state.task.complete !== 'boolean') stop('CONTINUATION_COMPLETION_UNVERIFIED');
    } else {
      current = selectCurrentRequest(state.nativeRecords, binding);
      if (!same(current.reference, transition?.reference ?? receipt.request)) stop('CONTINUATION_REQUEST_CHANGED');
      if (transition) preparedRequest(current, transition.source, transition.target, receipt);
    }
  } else if (receipt.request !== null || typeof receipt.authority_digest !== 'string'
    || !/^[a-f0-9]{64}$/.test(receipt.authority_digest) || state.authorityDigest !== receipt.authority_digest) {
    stop('CONTINUATION_AUTHORITY_CHANGED');
  }
  if (Object.hasOwn(receipt, 'source_pr') && !receipt.authority) stop('CONTINUATION_STANDALONE_UNVERIFIED');
  let continuation = current?.request.continuation ?? state.legacyContinuation ?? defaults;
  const retainedContinuation = Object.hasOwn(receipt, 'source_pr') ? current?.compatibilityRequest?.request.continuation : null;
  if (retainedContinuation?.next?.request && !retainedContinuation.next.direction
    && !current.decisions.some(selected => Object.hasOwn(selected.decision.amendments, 'continuation'))) {
    // Preserve the visible pending direction. A retained Request reference
    // cannot launch fresh v3 work through a v4 source acceptance receipt.
    continuation = { ...continuation, next: retainedContinuation.next };
  }
  if (!continuation || typeof continuation.hold !== 'boolean' || !receipt.authority && typeof continuation.task_complete !== 'boolean'
    || !Object.hasOwn(continuation, 'next')) stop('CONTINUATION_AUTHORITY_CHANGED');
  if (continuation.hold || state.task.hold || state.task.protectedBoundary) stop('CONTINUATION_PROTECTED_BOUNDARY');
  if (native.kind === 'review') {
    if (receipt.authority) {
      const markers = native.body.split(/\r?\n/).filter(line => line.startsWith('<!-- jresearchsoftware-reviewer-acceptance:v1 '));
      if (markers.length > 1 || markers.length === 1
        && markers[0] !== `<!-- jresearchsoftware-reviewer-acceptance:v1 authority_sha256=${receipt.authority.sha256} -->`) stop('CONTINUATION_APPROVAL_UNVERIFIED');
      const sourceMarkers = native.body.split(/\r?\n/).filter(line => line.startsWith('<!-- jresearchsoftware-reviewer-source-pr:'));
      if (Object.hasOwn(receipt, 'source_pr')) {
        if (markers.length !== 1 || sourceMarkers.length !== 1 || sourceMarkers[0] !== sourcePrMarker) stop('CONTINUATION_APPROVAL_UNVERIFIED');
      } else {
        if (sourceMarkers.length) stop('CONTINUATION_APPROVAL_UNVERIFIED');
        // Historical v4 approvals carried no authority marker. They can retain
        // unchanged original-Outcome acceptance, never acquire new Task semantics
        // from a caller-carried receipt after the native approval.
        const outcomes = state.nativeRecords.filter(record => record.kind === 'issue-comment' && trusted(record, binding.trustedWriter))
          .map(native => ({ native, outcome: extractAuthorityRecord(native.body, binding) }))
          .filter(({ outcome }) => outcome?.kind === 'outcome' && outcome.schema_version === '4.0'
            && same(outcome.admission, receipt.admission));
        if (outcomes.some(({ native, outcome }) => !same(native.parent, outcome.parent)
          || outcome.parent.kind === 'pull_request' && outcome.parent.number !== state.pr?.number
          || outcome.parent.kind === 'issue' && outcome.parent.number !== receipt.task
          || outcome.status !== 'implemented' || !['git', 'no-change'].includes(outcome.result.kind)
          || outcome.result.revision !== receipt.reviewed_head_sha)) stop('CONTINUATION_APPROVAL_UNVERIFIED');
        const deliveredOutcome = outcomes[0]?.outcome;
        if (outcomes.length !== 1 || !markers.length && !same(deliveredOutcome.authority, receipt.authority)) stop('CONTINUATION_APPROVAL_UNVERIFIED');
        const delivered = resolveOutcomeAuthority(deliveredOutcome.authority, state.nativeRecords,
          { ...binding, ...(deliveredOutcome.authority_resolution ? { authorityResolution: deliveredOutcome.authority_resolution } : {}) });
        if (!same(delivered.authority, receipt.authority)) stop('AUTHORITY_APPROVAL_STALE_REQUEST');
      }
    }
    if (native.state !== 'APPROVED' || !sha(receipt.reviewed_head_sha) || native.commit_id !== receipt.reviewed_head_sha
      || !state.pr || native.parent.kind !== 'pull_request' || native.parent.number !== state.pr.number
      || state.pr.taskNumber !== receipt.task
      || state.pr.headSha !== receipt.reviewed_head_sha) stop('CONTINUATION_HEAD_CHANGED');
    if (state.pr.exactBaseRequired === true && (!sha(receipt.reviewed_base_sha) || state.pr.baseSha !== receipt.reviewed_base_sha)) stop('CONTINUATION_BASE_CHANGED');
  } else if (native.kind === 'issue-comment') {
    const approval = extractAuthorityRecord(native.body, binding);
    if (approval?.kind !== 'task-approval') stop('CONTINUATION_APPROVAL_UNVERIFIED');
    if (transition) {
      const previous = transition.acceptance;
      const outcomeNative = state.nativeRecords.find(record => same(nativeReference(record), nativeReference(previous.outcomeRecord)));
      if (!same(approval, previous.approval) || !outcomeNative || !trusted(outcomeNative, binding.trustedWriter)
        || !state.nativeRecords.some(record => same(nativeReference(record), receipt.request))) stop('CONTINUATION_APPROVAL_UNVERIFIED');
    } else {
      if (receipt.authority && (!same(approval.authority, receipt.authority) || !same(approval.admission, receipt.admission))) stop('CONTINUATION_APPROVAL_UNVERIFIED');
      current.approvalValidation = validateTaskApproval(approval, state.nativeRecords, binding);
    }
    // A Task Approval accepts its immutable Task result; it is not a PR review
    // and does not supply permission to merge a disposable artifact PR.
  } else stop('CONTINUATION_APPROVAL_UNVERIFIED');
  return { binding, native, current, continuation, state };
}

function readyToMerge(accepted) {
  const pr = accepted.state.pr;
  if (accepted.current && pr.closesTask !== false) stop('CONTINUATION_IMPLICIT_CLOSURE');
  if (pr.state !== 'open' || pr.merged !== false || !sha(pr.baseSha) || pr.readiness !== 'ready'
    || pr.mergeability !== 'clean' || pr.requiredChecksComplete !== true || !Array.isArray(pr.requiredChecks)
    || pr.requiredChecks.some(check => check.headSha !== accepted.native.commit_id || check.status !== 'completed'
      || !['success', 'neutral', 'skipped'].includes(check.conclusion))) stop('CONTINUATION_NOT_READY');
}

const reusedFields = ['repository', 'task', 'charter_sha256', 'route', 'purpose', 'scope', 'model', 'effort', 'subagents',
  'validation', 'boundaries', 'issue_closure_policy', 'branch'];
function preparationSnapshot(source, target, receipt) {
  if (target.task !== receipt.task || !Number.isSafeInteger(target.step)
    || target.step < source.request.step || target.step > source.request.step + 1) stop('CONTINUATION_DIRECTION_INVALID');
  const direction = source.decisions.find(selected => same(selected.reference, target.direction));
  if (!direction || direction.decision.parent.kind !== 'issue' || direction.decision.parent.number !== receipt.task) stop('CONTINUATION_DIRECTION_INVALID');
  if (source.decisions.some(selected => selected.decision.parent.kind === 'issue'
    && selected.decision.amendments.continuation !== undefined && !same(selected.decision.amendments.continuation, defaults))) stop('CONTINUATION_DIRECTION_INCOMPLETE');
  const scopedDecisions = source.decisions.filter(selected => selected.decision.parent.kind === 'pull_request');
  for (const selected of scopedDecisions) {
    for (const field of Object.keys(selected.decision.amendments)) {
      if (!same(direction.decision.amendments[field], source.request[field])) stop('CONTINUATION_DIRECTION_INCOMPLETE');
    }
  }
  const decisions = source.request.decisions.filter(reference => reference.parent.kind === 'issue');
  const context = [...source.request.context, ...scopedDecisions.map(selected => selected.reference), receipt.approval]
    .filter((reference, index, references) => references.findIndex(other => same(other, reference)) === index);
  return { ...Object.fromEntries(reusedFields.map(field => [field, source.request[field]])), schema_version: '3.0', kind: 'task-request',
    parent: { kind: 'issue', number: receipt.task }, step: target.step, decisions, context, supersedes: source.reference,
    base_sha: source.request.base_sha, starting_head: source.request.starting_head, existing_pr: null, continuation: { ...defaults } };
}
function preparedRequest(selected, source, target, receipt) {
  const request = selected.request;
  const expected = preparationSnapshot(source, target, receipt);
  if (request.kind !== 'task-request' || !same(request.parent, { kind: 'issue', number: receipt.task })
    || reusedFields.some(field => !same(request[field], source.request[field])) || request.step !== target.step
    || !same(request.supersedes, source.reference) || request.existing_pr !== null
    || !same(request.context, expected.context) || !same(request.decisions, expected.decisions)
    || !same(request.continuation ?? defaults, defaults)) stop('CONTINUATION_PREPARED_REQUEST_INVALID');
}

// Owner-channel adapter only. These ports wrap the existing trusted native
// publication journal/API; the worker must never receive them. The helper
// neither loads credentials nor authors new scope, Requests or owner decisions.
export async function continueAfterApproval(receipt, ports) {
  const actions = [];
  if (!receipt || receipt.publication_status !== 'verified' || !receipt.approval
    || !Number.isSafeInteger(receipt.approval.id) || receipt.approval.id < 1) {
    return { status: 'stopped', reason: 'CONTINUATION_PUBLICATION_UNVERIFIED', actions };
  }
  if (!ports || requiredPorts.some(name => typeof ports[name] !== 'function')) {
    return { status: 'stopped', reason: 'CONTINUATION_ADAPTER_UNAVAILABLE', actions };
  }
  let preparedTransition = null;
  const read = async () => acceptedState(receipt, await ports.readCanonicalState({ repository: receipt.repository, task: receipt.task,
    approval: receipt.approval, request: preparedTransition?.reference ?? receipt.request }), preparedTransition);
  const act = async (kind, target, mutation, guard) => {
    if (typeof mutation !== 'function') stop('CONTINUATION_ADAPTER_UNAVAILABLE');
    const action = { kind, repository: receipt.repository, task: receipt.task, approval: receipt.approval, ...target };
    const operationId = sha256Body(canonicalAuthorityJson(action));
    const reserved = await ports.reserveAction({ operationId, action });
    if (reserved?.status === 'completed') {
      if (reserved.operationId !== operationId || reserved.result?.status !== 'verified') stop('CONTINUATION_ACTION_UNCERTAIN');
      actions.push({ kind, operationId, status: 'already-completed', result: reserved.result });
      return reserved.result;
    }
    if (reserved?.status !== 'reserved' || reserved.operationId !== operationId) stop('CONTINUATION_ACTION_UNCERTAIN');
    // A reservation is not permission to mutate after authority changed.
    try {
      const fresh = await read();
      if (guard) await guard(fresh, action);
    } catch (error) {
      await ports.recordActionResult({ operationId, action, result: { status: 'not-started', reason: error?.code ?? 'CONTINUATION_EVIDENCE_UNAVAILABLE' } });
      throw error;
    }
    let result;
    try { result = await mutation({ operationId, ...action }); }
    catch (error) {
      await ports.recordActionResult({ operationId, action, result: { status: 'uncertain' } });
      stop('CONTINUATION_ACTION_UNCERTAIN');
    }
    actions.push({ kind, operationId, status: result?.status ?? 'uncertain', result });
    try { await ports.recordActionResult({ operationId, action, result }); }
    catch { stop('CONTINUATION_RECEIPT_UNCERTAIN'); }
    if (result?.status !== 'verified') stop('CONTINUATION_ACTION_UNCERTAIN');
    return result;
  };
  try {
    let accepted = await read();
    if (accepted.native.kind === 'review') {
      if (accepted.state.pr.merged === true) {
        if (!sha(accepted.state.pr.mergeCommitSha)) stop('CONTINUATION_MERGE_UNVERIFIED');
      } else {
        readyToMerge(accepted);
        const neutralMessage = accepted.current ? { commitTitle: `Task ${receipt.task} implementation`,
          commitBody: `Pull request: ${accepted.state.pr.number}\nApproved head: ${receipt.reviewed_head_sha}\nNative approval: ${receipt.approval.id}\n` } : {};
        const result = await act('squash-merge', { pullRequest: accepted.state.pr.number,
          expectedHeadSha: receipt.reviewed_head_sha, expectedBaseSha: accepted.state.pr.baseSha, ...neutralMessage }, ports.mergeSquash, (fresh, action) => {
          readyToMerge(fresh);
          if (fresh.state.pr.baseSha !== action.expectedBaseSha) stop('CONTINUATION_BASE_CHANGED');
        });
        accepted = await read();
        if (!accepted.state.pr.merged || !sha(result.mergeCommitSha)
          || accepted.state.pr.mergeCommitSha !== result.mergeCommitSha) stop('CONTINUATION_MERGE_UNVERIFIED');
      }
    }
    accepted = await read();
    const closure = receipt.authority ? { policy: accepted.current.request.issue_closure_policy, warnings: accepted.current.warnings }
      : stableClosurePolicy(accepted.binding.charterBody);
    const taskComplete = receipt.authority ? accepted.state.task.complete : accepted.continuation.task_complete;
    if (closure.policy === 'close-authorized' && taskComplete && !accepted.state.task.remainingWork
      && accepted.continuation.next?.task !== receipt.task
      && !accepted.state.task.closed) {
      await act('close-issue', { issueNumber: receipt.task }, ports.closeIssue, fresh => {
        const effective = receipt.authority ? fresh.current.request.issue_closure_policy : stableClosurePolicy(fresh.binding.charterBody).policy;
        const complete = receipt.authority ? fresh.state.task.complete : fresh.continuation.task_complete;
        if (effective !== 'close-authorized' || !complete
          || fresh.state.task.remainingWork || fresh.state.task.closed) stop('CONTINUATION_CLOSURE_CHANGED');
      });
      accepted = await read();
      if (!accepted.state.task.closed) stop('CONTINUATION_CLOSURE_UNVERIFIED');
    }
    if (receipt.authority && closure.policy === 'keep-open' && taskComplete && !accepted.state.task.remainingWork
      && accepted.continuation.next === null && !accepted.state.task.closed) stop('CONTINUATION_CLOSURE_POLICY_RECONCILIATION_REQUIRED');
    let next = accepted.continuation.next;
    if (next !== null) {
      if (receipt.authority) {
        if (!Number.isSafeInteger(next.task) || next.task < 1 || !next.direction
          || typeof ports.readNextAuthority !== 'function') stop('CONTINUATION_NEXT_AUTHORITY_INVALID');
        const readNext = async () => {
          const state = await ports.readNextAuthority({ repository: receipt.repository, task: next.task, direction: next.direction });
          if (state?.binding?.repository !== receipt.repository || state.binding.task !== next.task) stop('CONTINUATION_NEXT_AUTHORITY_INVALID');
          const resolved = resolveTaskAuthority(state.nativeRecords, { ...state.binding, compatibility: false });
          if (!resolved || !resolved.decisions.some(item => same(item.reference, next.direction))) stop('CONTINUATION_NEXT_REQUEST_CHANGED');
          if (resolved.request.continuation.hold || state.protectedBoundary !== false) stop('CONTINUATION_PROTECTED_BOUNDARY');
          if (!['auto', 'manual'].includes(resolved.request.route)) stop('CONTINUATION_NEXT_AUTHORITY_INVALID');
          return resolved;
        };
        const selected = await readNext();
        const kind = selected.request.route === 'auto' ? 'launch-authority' : 'manual-handoff';
        const mutation = selected.request.route === 'auto' ? ports.launchAuthority ?? ports.launchRequest : ports.manualHandoff;
        await act(kind, { nextTask: next.task, nextAuthority: selected.authority, direction: next.direction,
          route: selected.request.route }, mutation, async () => {
          const fresh = await readNext();
          if (!same(fresh.authority, selected.authority) || fresh.request.route !== selected.request.route) stop('CONTINUATION_NEXT_REQUEST_CHANGED');
        });
        return { status: 'complete', actions, warnings: closure.warnings };
      }
      if (!next || !Number.isSafeInteger(next.task) || next.task < 1 || (!next.request && !next.direction)
        || typeof ports.readNextAuthority !== 'function') stop('CONTINUATION_NEXT_AUTHORITY_INVALID');
      if (next.direction) {
        if (!accepted.current || typeof ports.prepareNextAuthority !== 'function') stop('CONTINUATION_ADAPTER_UNAVAILABLE');
        const source = accepted.current;
        const target = next;
        const snapshot = preparationSnapshot(source, target, receipt);
        const result = await act('prepare-next-authority', { nextTask: target.task, direction: target.direction,
          step: target.step, acceptedRequest: source.reference }, action => ports.prepareNextAuthority({ ...action, snapshot }), fresh => {
          if (!same(fresh.continuation.next, target) || !same(fresh.current.reference, source.reference)) stop('CONTINUATION_REQUEST_CHANGED');
          preparationSnapshot(fresh.current, target, receipt);
        });
        if (!result.request || same(result.request, source.reference)) stop('CONTINUATION_PREPARED_REQUEST_INVALID');
        const prepared = await ports.readNextAuthority({ repository: receipt.repository, task: target.task, request: result.request });
        if (prepared?.binding?.repository !== receipt.repository || prepared.binding.task !== target.task) stop('CONTINUATION_NEXT_AUTHORITY_INVALID');
        const selected = selectCurrentRequest(prepared.nativeRecords, prepared.binding);
        if (!selected || !same(selected.reference, result.request)) stop('CONTINUATION_NEXT_REQUEST_CHANGED');
        preparedRequest(selected, source, target, receipt);
        preparedTransition = { reference: selected.reference, source, target, acceptance: source.approvalValidation };
        accepted = await read();
        next = { task: target.task, request: selected.reference };
      }
      const nextState = await ports.readNextAuthority({ repository: receipt.repository, task: next.task, request: next.request });
      const nextBinding = nextState?.binding;
      if (!nextBinding || nextBinding.repository !== receipt.repository || nextBinding.task !== next.task) stop('CONTINUATION_NEXT_AUTHORITY_INVALID');
      const selected = selectCurrentRequest(nextState.nativeRecords, nextBinding);
      if (!selected || !same(selected.reference, next.request)) stop('CONTINUATION_NEXT_REQUEST_CHANGED');
      const nextContinuation = selected.request.continuation ?? defaults;
      if (nextContinuation.hold || nextState.protectedBoundary !== false) stop('CONTINUATION_PROTECTED_BOUNDARY');
      if (next.task === receipt.task && same(next.request, receipt.request)) stop('CONTINUATION_NEXT_REPLAY');
      const kind = selected.request.route === 'auto' ? 'launch-request' : 'manual-handoff';
      const mutation = selected.request.route === 'auto' ? ports.launchRequest : ports.manualHandoff;
      await act(kind, { nextTask: next.task, nextRequest: next.request, route: selected.request.route }, mutation, async () => {
        // A delayed reservation must not launch an edited or superseded Request.
        const fresh = await ports.readNextAuthority({ repository: receipt.repository, task: next.task, request: next.request });
        if (fresh?.binding?.repository !== receipt.repository || fresh.binding.task !== next.task) stop('CONTINUATION_NEXT_AUTHORITY_INVALID');
        const current = selectCurrentRequest(fresh.nativeRecords, fresh.binding);
        if (!current || !same(current.reference, next.request)) stop('CONTINUATION_NEXT_REQUEST_CHANGED');
        if ((current.request.continuation ?? defaults).hold || fresh.protectedBoundary !== false) stop('CONTINUATION_PROTECTED_BOUNDARY');
      });
    }
    return { status: 'complete', actions, warnings: closure.warnings };
  } catch (error) {
    return { status: 'stopped', reason: typeof error?.code === 'string' ? error.code : 'CONTINUATION_EVIDENCE_UNAVAILABLE', actions };
  }
}
