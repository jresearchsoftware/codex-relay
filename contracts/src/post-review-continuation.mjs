import {
  authorityMode, canonicalAuthorityJson, extractAuthorityRecord, nativeReference, referenceKey,
  selectCurrentRequest, sha256Body, stableClosurePolicy, validateTaskApproval
} from './github-authority.mjs';

const sha = value => typeof value === 'string' && /^[a-f0-9]{40}$/.test(value);
const same = (left, right) => canonicalAuthorityJson(left) === canonicalAuthorityJson(right);
const stop = code => { throw Object.assign(new Error(code), { code }); };
const trusted = (native, identity) => identity && typeof identity.login === 'string' && identity.login.length > 0
  && Number.isSafeInteger(identity.id) && identity.id > 0 && identity.type === 'Bot'
  && native.author?.login === identity.login && native.author?.id === identity.id && native.author?.type === 'Bot';
const defaults = { hold: false, task_complete: false, next: null };
const requiredPorts = ['readCanonicalState', 'reserveAction', 'recordActionResult'];

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
  let current;
  if (authorityMode(binding.charterBody) === 'github-native-v1') {
    current = selectCurrentRequest(state.nativeRecords, binding);
    if (!same(current.reference, transition?.reference ?? receipt.request)) stop('CONTINUATION_REQUEST_CHANGED');
    if (transition) preparedRequest(current, transition.source, transition.target, receipt);
  } else if (receipt.request !== null || typeof receipt.authority_digest !== 'string'
    || !/^[a-f0-9]{64}$/.test(receipt.authority_digest) || state.authorityDigest !== receipt.authority_digest) {
    stop('CONTINUATION_AUTHORITY_CHANGED');
  }
  const continuation = current?.request.continuation ?? state.legacyContinuation ?? defaults;
  if (!continuation || typeof continuation.hold !== 'boolean' || typeof continuation.task_complete !== 'boolean'
    || !Object.hasOwn(continuation, 'next')) stop('CONTINUATION_AUTHORITY_CHANGED');
  if (continuation.hold || state.task.hold || state.task.protectedBoundary) stop('CONTINUATION_PROTECTED_BOUNDARY');
  if (native.kind === 'review') {
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
    } else current.approvalValidation = validateTaskApproval(approval, state.nativeRecords, binding);
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
    const closure = stableClosurePolicy(accepted.binding.charterBody);
    if (closure.policy === 'close-authorized' && accepted.continuation.task_complete && !accepted.state.task.remainingWork
      && accepted.continuation.next?.task !== receipt.task
      && !accepted.state.task.closed) {
      await act('close-issue', { issueNumber: receipt.task }, ports.closeIssue, fresh => {
        if (stableClosurePolicy(fresh.binding.charterBody).policy !== 'close-authorized' || !fresh.continuation.task_complete
          || fresh.state.task.remainingWork || fresh.state.task.closed) stop('CONTINUATION_CLOSURE_CHANGED');
      });
      accepted = await read();
      if (!accepted.state.task.closed) stop('CONTINUATION_CLOSURE_UNVERIFIED');
    }
    let next = accepted.continuation.next;
    if (next !== null) {
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
