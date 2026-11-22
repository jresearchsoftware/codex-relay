import { CONSUMER, CONSUMER_DIGEST } from '../../consumer/consumer.mjs';
import { PROGRESS_BOUNDED_EXECUTION } from '../../runtime/src/execution-policy.mjs';
import { REPOSITORY, VERSION, WRITER, digest, exactSha, fail, positive, validateEnvelope } from './execution-contract.mjs';
import { canonicalAuthorityJson, sha256Body, authorityMode, admissionBinding } from '../../contracts/src/github-authority.mjs';
import { admitEnvelope, revalidateReadyEvent, readyTransitions, revalidateAuthority, revalidateIntegrationBase, assertPr, linkedIssue } from './live-authority.mjs';
import { secretFree } from './trusted-git.mjs';
import { failureDiagnosticFromDetails } from './diagnostics.mjs';
import { admissionWarningSummary, executionWarningSummary, terminalOutcomeBody, automaticOutcomeBody, usageOutcomeSummary, safeOutcomePublication } from './outcome.mjs';
import { threadCorrelationIdentity } from './run-name.mjs';
import { recoverPublication, recoveryAuthorization, recoveryAuthorizationBody, authorizeRecoveryCollection, authorizeRecovery } from './publication-recovery.mjs';
import { assertStep, currentStep, assertPrStepTitle, projectedRequestTitle, labelNames, stepLike } from './step-metadata.mjs';
import { findCurrentIssuePullRequest } from './publication-target.mjs';
import { prReadiness, readinessOutcomeLines } from './pr-readiness.mjs';
import { nonClosingTaskBody } from './task-relationship.mjs';
import { transitionPr, beginRemediation } from './pr-lifecycle.mjs';
import { prepublicationState, recoverPrepublication } from './prepublication-recovery.mjs';
import { publishManualOutcome, assertManualPullRequestBinding } from './manual-outcome.mjs';
import { nextAdmissionStep, latestAdmissionRecord } from './admission-step.mjs';
import { PUBLICATION_RENDERER_VERSION } from '../../contracts/src/publication-rendering.mjs';
import { executionConsumer } from '../../consumer/consumer.mjs';
import { renderManualHandoff } from './manual-handoff.mjs';
import { latestProjection, assertPublicationIsolation } from './publication-isolation.mjs';
import { ambiguousGithubWrite, attachWriteReadback, failureFacts, safeFailureFacts } from './failure-report.mjs';
import { admissionFailure } from './admission-diagnostic.mjs';
import { predispatchState, finalizePredispatch, predispatchReplacementState, finalizePredispatchReplacement,
  completedPredispatchRecovery, pendingPredispatchRecord, consumedPredispatchRecord, consumedPredispatchMarker,
  predispatchReadyReplacementReported, revalidateUnreturnedAdmission } from './predispatch-recovery.mjs';

// Caller serializes this broker across processes. Store contains immutable
// admission, trusted controller reservation/completion and mutation receipts.
// Runtime observations remain in the separate protected runner journal.
export function createPublicationBroker({ api, store, publisher, admission, journal, lifecycleStore, admissionLifecycleStore, collectRetained, allowManualOutcome = false, diagnosticSecrets = [], checkoutAbsent,
  recordFailure = async () => undefined,
  assertPredispatchFence = async () => fail('PREDISPATCH_COMPATIBLE_WRITER_REQUIRED') }) {
  const secrets = { knownSecrets: diagnosticSecrets };
  const receipt = value => ({ version: VERSION, repository: REPOSITORY, ...value });
  const bindingLines = e => `Execution admission digest: ${admissionBinding(e.request).sha256}\nEffective authority digest: ${e.authorityDigest}\n`;
  const titleFor = e => secretFree(projectedRequestTitle(e.request));
  const stepLabels = subject => labelNames(subject.labels).filter(stepLike).sort();
  const replacementRetirementCanDefer = error =>
    ['PREDISPATCH_OUTCOME_RECONCILIATION_UNPROVEN', 'PREDISPATCH_REPLACEMENT_RECONCILIATION_UNPROVEN']
      .includes(error?.code);
  async function publicationRecords(e) {
    if (!store.scan) return store.all();
    const rows = (await store.scan()).filter(row => row.repository === e.repository);
    const independent = row => {
      // A sealed original journal can prove ownership of a damaged publication
      // record, but cannot establish successful admission or terminal status.
      const identity = row.envelope ?? row.record?.envelope;
      return identity?.repository === row.repository && identity.runId === row.runId
        && identity.attemptId === `run-${row.runId}` && positive(identity.issueNumber)
        && identity.issueNumber !== e.issueNumber
        && (!e.branch || identity.branch !== e.branch)
        && !(e.target === 'pull_request' && identity.target === 'pull_request' && identity.number === e.number);
    };
    const unknown = rows.find(row => (row.error || !row.record?.envelope) && !independent(row));
    if (unknown) throw Object.assign(new Error('PUBLICATION_INVENTORY_UNRESOLVED', { cause: unknown.cause }), {
      code: 'PUBLICATION_INVENTORY_UNRESOLVED', details: { conflictingAttempt: `run-${unknown.runId}`,
        resource: `repository/${e.repository}`, nextAction: 'inspect-original-unreadable-publication-record' } });
    return rows.filter(row => !row.error && row.record?.envelope).map(row => row.record);
  }
  const projectionFor = async (e, options) => latestProjection(await publicationRecords(e), e, options);
  const isCurrentProjection = async e => (await projectionFor(e)).step === e.step;
  const guardPublication = async e => assertPublicationIsolation(await publicationRecords(e), e);
  async function projectAdmittedStep(r) {
    let operation = 'step-inventory';
    try { return await projectStep(r, value => { operation = value; }); }
    catch (cause) {
      const failure = admissionFailure(cause, operation, r.envelope.attemptId, diagnosticSecrets);
      r.admissionFailure = failure;
      try { await store.put(r.envelope.runId, r); }
      catch (error) {
        failure.recorderFailure = admissionFailure(error, 'admission-diagnostic-write', r.envelope.attemptId, diagnosticSecrets).exception;
        await recordFailure({ error: Object.assign(new Error('ADMISSION_DIAGNOSTIC_WRITE_FAILED', { cause }), {
          code: 'ADMISSION_DIAGNOSTIC_WRITE_FAILED', native: { recorderFailure: error } }), operation, phase: 'authority', runId: r.envelope.runId,
          secrets: { knownSecrets: diagnosticSecrets } });
        // Keep the original failure even when diagnostic retention also fails.
        failure.diagnostic.preview += ' The protected diagnostic write also failed; retention is unverified.';
      }
      throw Object.assign(new Error(failure.diagnostic.code, { cause }), { code: failure.diagnostic.code,
        details: { childState: 'not_started', failureDiagnostic: { ...failure.diagnostic, childState: 'not_started' },
          admissionEffect: { step: r.envelope.step, projection: 'unknown', ready: 'not-attempted' } } });
    }
  }
  // Step labels and PR titles have a bounded, exact readback. Only a
  // verified result reconciles a lost acknowledgement in this invocation.
  async function projectPresentation(mutate, readback) {
    try { await mutate(); }
    catch (error) {
      if (!ambiguousGithubWrite(error)) throw error;
      try {
        if (await readback()) return;
        attachWriteReadback(error, 'not-observed');
      } catch (cause) { attachWriteReadback(error, 'unavailable', cause); }
      throw error;
    }
  }
  async function projectStep(r, at) {
    const e = r.envelope;
    const latest = latestAdmissionRecord(await publicationRecords(e), e.issueNumber);
    if (latest?.envelope.attemptId !== e.attemptId) {
      r.stepProjectionSupersededBy = latest?.envelope.attemptId ?? null;
      await store.put(e.runId, r); return;
    }
    at('step-authority'); await revalidateAuthority(api, e);
    at('step-issue-read');
    const subject = await api.get(`/issues/${e.issueNumber}`);
    if (r.stepProjectionFrom
      && canonicalAuthorityJson(stepLabels(subject)) !== canonicalAuthorityJson(r.stepProjectionFrom)
      && canonicalAuthorityJson(stepLabels(subject)) !== canonicalAuthorityJson([`step-${e.step}`]))
      fail('STEP_LABEL_POSITION_CHANGED');
    at('step-label-ensure'); await api.ensureStepLabel(e.step);
    // Individual label operations preserve a ready command (or unrelated
    // owner label) added after this read. A labels-array PATCH can erase it.
    at('step-label-remove');
    const labelPresent = async name => {
      const state = await api.get(`/issues/${e.issueNumber}`);
      if (state?.number !== subject.number || state?.state !== subject.state || state?.body !== subject.body
        || !Array.isArray(state.labels)) fail('AUTHORITY_CHANGED');
      return labelNames(state.labels).includes(name);
    };
    for (const label of labelNames(subject.labels).filter(name => stepLike(name) && name !== `step-${e.step}`))
      await projectPresentation(() => api.delete(`/issues/${e.issueNumber}/labels/${encodeURIComponent(label)}`),
        async () => !await labelPresent(label));
    at('step-label-add');
    if (!labelNames(subject.labels).includes(`step-${e.step}`))
      await projectPresentation(() => api.post(`/issues/${e.issueNumber}/labels`, { labels: [`step-${e.step}`] }),
        () => labelPresent(`step-${e.step}`));
    at('step-issue-readback'); assertStep((await api.get(`/issues/${e.issueNumber}`)).labels, e.step);
    if (e.target === 'pull_request' || e.continuation?.pullRequest) {
      const number = e.target === 'pull_request' ? e.number : e.continuation.pullRequest;
      at('step-pr-read'); const pr = await api.get(`/pulls/${number}`);
      at('step-pr-projection'); await mirrorStep(r, pr, { advance: true });
    }
    at('step-receipt'); r.stepProjected = true; delete r.stepProjectionFrom; await store.put(e.runId, r);
  }
  async function readyConsumptionFailure(r, code, { cause, transitions = [] } = {}) {
    const e = r.envelope;
    if (cause) {
      // A later journal/Outcome failure must not erase the original DELETE or
      // revalidation error. This evidence write authorizes no native retry.
      try {
        await recordFailure({ error: cause, operation: 'ready-command-consumption',
          phase: 'authority', runId: e.runId, workerStarted: false, secrets: { knownSecrets: diagnosticSecrets } });
      } catch { cause.details = { ...cause.details, diagnosticRecorderFailed: true }; }
    }
    const later = transitions.length ? transitions.filter(event => event.id > e.readyEventId).map(event => event.id)
      : r.readyConsumption?.laterEvents ?? [];
    const originalCode = r.readyConsumption?.code ?? code;
    const admissionEffect = { step: e.step, projection: r.stepProjected ? 'projected' : 'unknown', ready: 'uncertain' };
    const preview = `Ready consumption for ${e.attemptId} on #${e.number}, original event ${e.readyEventId}, stopped: ${code}.`
      + (later.length ? ` Later transition IDs: ${later.join(', ')}.` : '')
      + (e.route === 'auto' ? ' Automatic worker launch authority was not returned.' : ' No manual handoff was emitted; this does not establish the state of independent offline work.')
      + ' This DELETE will not be retried. Inspect the target; remove any remaining ready label and apply the intended command again in a later second for a fresh independent attempt.';
    r.readyConsumption = { ...r.readyConsumption, status: 'uncertain', code: originalCode, laterEvents: later, diagnostic: preview };
    // This broker has not returned a launchable envelope. The new automatic
    // reservation has no worker child; this is not a historical cancellation
    // or a negative manual-start receipt. Its label effect remains uncertain.
    if (e.route === 'auto' && !r.readyConsumed && r.controllerLifecycle?.status === 'active')
      r.controllerLifecycle = { version: 1, status: 'complete', child: 'not_started', containment: 'not_required' };
    await store.put(e.runId, r);
    try {
      await terminalOutcome(r, { terminalCode: originalCode, diagnostic: { ...admissionBlockDiagnostic({ code: originalCode }),
        ...failureFacts(cause), ...(cause?.details?.diagnosticRecorderFailed ? { diagnosticRecorderFailed: true } : {}),
        admissionEffect, admissionSummary: preview, nextAction: 'inspect-ready-target-and-apply-fresh-owner-command' } });
    } catch (error) {
      const original = cause ?? Object.assign(new Error(originalCode), { code: originalCode });
      original.details = { ...original.details, outcomePublication: safeOutcomePublication(error) };
      original.native = { ...original.native, outcomePublicationFailure: error };
      publicationFailure(originalCode, { cause: original,
        diagnostic: { stage: 'authority', boundary: 'writer-publication', workerStarted: false, childState: 'not_started', preview }, admissionEffect });
    }
    publicationFailure(code, { cause, diagnostic: { stage: 'authority', boundary: 'authority', workerStarted: false,
      childState: 'not_started', preview }, admissionEffect });
  }
  async function consumeReadyCommand(r) {
    const e = r.envelope;
    if (r.readyConsumed) return;
    if (r.readyConsumption) return readyConsumptionFailure(r, 'READY_CONSUMPTION_UNCERTAIN');
    // Projection and other native reads may have allowed a replacement. Check
    // again at the mutation boundary and reserve the single DELETE first.
    try { await revalidateReadyEvent(api, e); }
    catch (cause) { return readyConsumptionFailure(r, 'READY_EVENT_REPLACED', { cause }); }
    r.readyConsumption = { status: 'deleting', eventId: e.readyEventId, label: e.readyLabel };
    await store.put(e.runId, r);
    let subject, transitions, mutationError;
    try { await api.delete(`/issues/${e.number}/labels/${e.readyLabel}`); }
    catch (cause) {
      if (!ambiguousGithubWrite(cause)) return readyConsumptionFailure(r, 'READY_CONSUMPTION_UNCERTAIN', { cause });
      mutationError = cause;
    }
    try {
      subject = await api.get(`/issues/${e.number}`);
      transitions = await readyTransitions(api, e.number);
    } catch (cause) {
      if (mutationError) attachWriteReadback(mutationError, 'unavailable', cause);
      return readyConsumptionFailure(r, 'READY_CONSUMPTION_UNCERTAIN', { cause: mutationError ?? cause });
    }
    const later = transitions.filter(event => event.id > e.readyEventId);
    const ownRemoval = event => event.event === 'unlabeled' && event.label.name === e.readyLabel
      && event.actor?.login === WRITER && event.actor?.type === 'Bot';
    // GitHub DELETE has no compare-and-delete event precondition. Detect a
    // replacement even if DELETE erased it before the label read-back. Never
    // consume a later command or mistake a same-second transition for our own.
    if (later.some(event => !ownRemoval(event))) {
      if (mutationError) attachWriteReadback(mutationError, 'unavailable');
      return readyConsumptionFailure(r, 'READY_EVENT_REPLACED', { transitions, cause: mutationError });
    }
    if (later.length !== 1 || !ownRemoval(later[0]) || labelNames(subject.labels).includes(e.readyLabel)) {
      if (mutationError) attachWriteReadback(mutationError, 'not-observed');
      return readyConsumptionFailure(r, 'READY_CONSUMPTION_UNCERTAIN', { transitions, cause: mutationError });
    }
    r.readyConsumption = { ...r.readyConsumption, status: 'consumed', removalEventId: later[0].id };
    // Keep the reservation through controller startup. A consumed command may
    // have returned an envelope even when the caller never receives the reply;
    // only terminal controller evidence or the locked original-run finalizer
    // can retire this marker.
    r.readyConsumed = true; await store.put(e.runId, r);
  }
  async function prepareRemediation(e) {
    if (e.target !== 'pull_request') return;
    if (!lifecycleStore) fail('PR_LIFECYCLE_STORE_REQUIRED');
    // The current native CR supplies the same exact action as Reviewer
    // pr_lifecycle. Consume it before reserving a worker or emitting a handoff,
    // even when the owner launches through the ordinary routing entrypoint.
    await beginRemediation({ api, store: lifecycleStore, admissionStore: admissionLifecycleStore,
      authorityDigest: e.authorityDigest, admittedEnvelope: e,
      request: { operation: 'begin-remediation', prNumber: e.number, reviewId: e.reviewId, head: e.startHead } });
  }
  async function mirrorStep(r, pr, { advance = false, publishedTransition } = {}) {
    const e = await projectionFor(r.envelope);
    if (e.branch !== r.envelope.branch) return pr;
    // Only the immediate metadata read after this Writer's verified non-force
    // push may lag at either endpoint. This never authorizes Ready or a new head.
    const ownTransition = publishedTransition && r.publishedHead === publishedTransition.head
      && !r.publicationIntent && [publishedTransition.previous, publishedTransition.head].every(exactSha)
      && [publishedTransition.previous, publishedTransition.head].includes(pr.head.sha);
    const heads = ownTransition ? [publishedTransition.previous, publishedTransition.head] : [pr.head.sha];
    const read = async () => {
      const current = await api.get(`/pulls/${pr.number}`);
      assertPr(current, pr.number);
      if (current.head.ref !== e.branch || !heads.includes(current.head.sha)
        || current.base.ref !== pr.base.ref || linkedIssue(current.body) !== e.issueNumber) fail('PR_AUTHORITY_CHANGED');
      return current;
    };
    const observed = await read();
    try {
      const labels = (await api.get(`/issues/${pr.number}`)).labels;
      for (const label of labelNames(labels).filter(name => stepLike(name) && name !== `step-${e.step}`))
        await api.delete(`/issues/${pr.number}/labels/${encodeURIComponent(label)}`);
      if (!labelNames(labels).includes(`step-${e.step}`)) {
        await api.ensureStepLabel(e.step);
        await api.post(`/issues/${pr.number}/labels`, { labels: [`step-${e.step}`] });
      }
      assertStep((await api.get(`/issues/${pr.number}`)).labels, e.step);
      if (observed.title !== titleFor(e))
        await projectPresentation(() => api.patch(`/pulls/${pr.number}`, { title: titleFor(e) }), async () => (await read()).title === titleFor(e));
      if ((await read()).title !== titleFor(e)) fail('AUTHORITY_TITLE_PROJECTION_MISMATCH');
    } catch (error) {
      if (error.code === 'PR_AUTHORITY_CHANGED') throw error;
      r.presentationWarnings = ['PRESENTATION_REPAIR_UNAVAILABLE'];
      r.presentationFailure = admissionFailure(error, 'pr-presentation-repair', e.attemptId, diagnosticSecrets);
      await recordFailure({ error, operation: 'pr-presentation-repair', phase: 'writer-publication', runId: e.runId, secrets: { knownSecrets: diagnosticSecrets } });
      await store.put(r.envelope.runId, r);
    }
    // Canonical Issue numbering is owner-maintained input for the next launch.
    // A presentation repair of this result never rewinds that position.
    const current = await read();
    return current;
  }
  function publicationFailure(code, { cause, diagnostic = {}, admissionEffect } = {}) {
    const source = {
      ...(cause?.details ?? {}),
      failureDiagnostic: { ...(cause?.details?.failureDiagnostic ?? {}), ...diagnostic }
    };
    const failureDiagnostic = failureDiagnosticFromDetails(source, {
      fallbackCode: code, fallbackStage: 'writer-publication', fallbackBoundary: 'writer-publication'
    });
    const error = new Error(code, { cause }); error.code = code; error.details = { failureDiagnostic, admissionEffect, outcomePublication: cause?.details?.outcomePublication,
      diagnosticRecorderFailed: cause?.details?.diagnosticRecorderFailed };
    throw error;
  }
  async function bound(request, { revalidate = true, allowAdmissionBlock = false, reporting = false, verifyStartingBase = false } = {}) {
    if (!positive(request.runId)) fail('RUN_ID_INVALID');
    const record = await store.get(request.runId);
    if (!record || request.attemptId !== record.envelope.attemptId) fail('ATTEMPT_NOT_ADMITTED');
    if (record.envelope.consumerDigest !== CONSUMER_DIGEST) fail('CONSUMER_CONFIG_CHANGED');
    if (record.admissionBlock) {
      if (!allowAdmissionBlock) fail('ADMISSION_ALREADY_BLOCKED');
      return record;
    }
    validateEnvelope(record.envelope);
    if (revalidate) record.authorityDrift = (await revalidateAuthority(api, record.envelope, { reporting, verifyStartingBase })).authorityDrift;
    return record;
  }
  async function commentOnce(r, key, number, body, { legacyBodies = [] } = {}) {
    secretFree(body);
    const marker = `<!-- relay:${r.envelope.attemptId}:${key} -->`;
    const intent = r.commentIntent?.key === key && r.commentIntent.number === number ? r.commentIntent : null;
    const exactBody = intent?.body ?? `${body}\n\n${marker}`;
    const readMatches = async () => (await api.list(`/issues/${number}/comments`))
      .filter(c => c.user?.login === WRITER && c.body?.includes(marker));
    const matches = await readMatches();
    if (matches.length > 1) fail('COMMENT_AMBIGUOUS');
    if (matches.length === 1) {
      const saved = r.commentBodies?.[key];
      const savedOutcome = key === 'outcome' ? r.outcome?.bodySha256 : null;
      if (saved ? saved.number !== number || sha256Body(matches[0].body) !== saved.sha256
        : savedOutcome ? sha256Body(matches[0].body) !== savedOutcome
        : matches[0].body !== exactBody && !legacyBodies.some(previous => matches[0].body === `${previous}\n\n${marker}`)) fail('COMMENT_CONTENT_CHANGED');
      if (r.commentIntent?.key === key && r.commentIntent.number === number) {
        r.commentIntent = null; await store.put(r.envelope.runId, r);
      }
      return matches[0];
    }
    // An ambiguous POST must never be blindly repeated after a failed GET.
    if (r.commentIntent?.key === key) fail('COMMENT_PUBLICATION_UNCERTAIN');
    r.commentIntent = { key, number, body: exactBody, rendererVersion: PUBLICATION_RENDERER_VERSION }; await store.put(r.envelope.runId, r);
    let comment;
    try { comment = await api.post(`/issues/${number}/comments`, { body: exactBody }); }
    catch (error) {
      if (!ambiguousGithubWrite(error)) throw error;
      let observed;
      try { observed = await readMatches(); }
      catch (cause) { attachWriteReadback(error, 'unavailable', cause); throw error; }
      if (observed.length !== 1 || !positive(observed[0].id) || observed[0].body !== exactBody) {
        attachWriteReadback(error, observed.length === 0 ? 'not-observed' : 'unavailable');
        throw error;
      }
      comment = observed[0];
    }
    if (comment?.body !== exactBody) fail('COMMENT_CONTENT_CHANGED');
    r.commentBodies = { ...r.commentBodies, [key]: { number, sha256: sha256Body(exactBody), rendererVersion: PUBLICATION_RENDERER_VERSION } };
    r.commentIntent = null; await store.put(r.envelope.runId, r);
    return comment;
  }
  async function pullRequest(r, publishedTransition = null) {
    const e = r.envelope;
    const existing = await existingPullRequest(r, { allowStepMirror: true, publishedTransition });
    if (existing) {
      const current = !r.finalHead && await isCurrentProjection(e)
        ? await projectTaskRelationship(r, existing) : existing;
      return mirrorStep(r, current, { publishedTransition });
    }
    if (r.prIntent) fail('PR_PUBLICATION_UNCERTAIN');
    r.prIntent = true; await store.put(e.runId, r);
    const intent = { title: titleFor(await projectionFor(e, { sameBranch: true })), head: e.branch, base: CONSUMER.baseBranch, draft: true,
      body: `Implementation of https://github.com/${REPOSITORY}/issues/${e.issueNumber}\n\nThread: ${e.thread}\nCorrelation: ${threadCorrelationIdentity(e.thread)}\nAttempt: ${e.attemptId}\n${bindingLines(e)}Requested model: ${e.profile.cliModelId}; effort: ${e.profile.effort}\nStarting head: ${e.startHead}\n\n${e.closure}` };
    let pr;
    try { pr = await api.post('/pulls', intent); }
    catch (error) {
      if (!ambiguousGithubWrite(error)) throw error;
      try {
        const observed = await findCurrentIssuePullRequest(api, e, null, publishedTransition);
        if (observed?.body === intent.body && observed.title === intent.title && observed.draft === true
          && observed.head.sha === r.publishedHead && observed.user?.login === WRITER) pr = observed;
        else attachWriteReadback(error, observed ? 'unavailable' : 'not-observed');
      } catch (cause) { attachWriteReadback(error, 'unavailable', cause); }
      if (!pr) throw error;
    }
    assertPr(pr, pr.number);
    if (pr.head.ref !== e.branch || linkedIssue(pr.body) !== e.issueNumber) fail('PR_AUTHORITY_CHANGED');
    await rememberPullRequest(r, pr);
    return mirrorStep(r, pr);
  }
  async function rememberPullRequest(r, pr) {
    // Preserve the first observed target before any label/readiness mutation.
    // Closing or replacing it cannot authorize another PR in this attempt.
    if (r.prNumber && r.prNumber !== pr.number) fail('PR_AUTHORITY_CHANGED');
    if (!r.prNumber) {
      r.prNumber = pr.number;
      await store.put(r.envelope.runId, r);
    }
  }
  async function projectTaskRelationship(r, pr) {
    if (!r.envelope.request) return pr;
    const body = nonClosingTaskBody(pr.body, REPOSITORY, r.envelope.issueNumber);
    const prior = r.relationshipIntent;
    if (prior && (prior.number !== pr.number || prior.head !== pr.head.sha
      || ![prior.before, prior.body].includes(pr.body))) fail('PR_AUTHORITY_CHANGED');
    if (body !== pr.body) {
      r.relationshipIntent = { number: pr.number, head: pr.head.sha, before: pr.body, body };
      await store.put(r.envelope.runId, r);
      // Re-admission retires an earlier final designation before new work.
      // Reserve and re-read first: an owner edit or moved head must not be
      // overwritten by a stale preflight/publication observation.
      const before = await api.get(`/pulls/${pr.number}`);
      assertPr(before, pr.number);
      if (before.head.sha !== pr.head.sha || before.head.ref !== pr.head.ref
        || ![pr.body, body].includes(before.body)
        || linkedIssue(before.body) !== r.envelope.issueNumber) fail('PR_AUTHORITY_CHANGED');
      if (before.body !== body) await api.patch(`/pulls/${pr.number}`, { body: secretFree(body) });
      const after = await api.get(`/pulls/${pr.number}`);
      assertPr(after, pr.number);
      if (after.head.sha !== pr.head.sha || after.head.ref !== pr.head.ref || after.body !== body
        || linkedIssue(after.body) !== r.envelope.issueNumber) fail('PR_AUTHORITY_CHANGED');
      pr = after;
    }
    if (r.relationshipIntent) { r.relationshipIntent = null; await store.put(r.envelope.runId, r); }
    return pr;
  }
  async function historicalManualPullRequest(r) {
    const e = r.envelope;
    // An Issue report cannot replace an original PR target or escape an
    // unresolved effect. Only its own exact Issue Outcome POST may recover.
    if (e.target === 'pull_request' || e.continuation?.pullRequest || e.request.existing_pr
      || r.outcome?.prNumber) fail('PR_AUTHORITY_CHANGED');
    const effect = ['publicationIntent', 'publishedHead', 'lifecycleIntent', 'relationshipIntent',
      'readinessIntent', 'successOutcomeIntent'].find(key => r[key])
      ?? (r.prepublicationRecovery?.publication ? 'prepublicationRecovery' : null)
      ?? (r.commentIntent && (r.commentIntent.key !== 'outcome' || r.commentIntent.number !== e.issueNumber)
        ? 'commentIntent' : null);
    if (effect) throw Object.assign(new Error('MANUAL_OUTCOME_PUBLICATION_UNRESOLVED'), {
      code: 'MANUAL_OUTCOME_PUBLICATION_UNRESOLVED', details: { conflictingAttempt: e.attemptId,
        resource: effect, nextAction: 'inspect-original-manual-publication' } });
    if (!e.branch) return null;
    const artifacts = await api.list(`/pulls?state=all&head=${REPOSITORY.split('/')[0]}:${encodeURIComponent(e.branch)}`);
    const owns = (pr, owner) => pr.body?.split(/\r?\n/).includes(`Execution admission digest: ${admissionBinding(owner.request).sha256}`);
    const original = artifacts.filter(pr => owns(pr, e)
      || pr.body?.split(/\r?\n/).includes(`Attempt: ${e.attemptId}`));
    if (original.length > 1) fail('PR_AMBIGUOUS');
    if (original.length) return original[0];
    const open = artifacts.filter(pr => pr.state === 'open');
    if (open.length > 1) fail('PR_AMBIGUOUS');
    if (open.length) {
      const records = await publicationRecords(e);
      for (const pr of open) {
        assertPr(pr, pr.number);
        const owners = records.filter(other => !other.admissionBlock
          && other.envelope?.repository === e.repository && other.envelope.issueNumber === e.issueNumber
          && other.envelope.branch === e.branch && other.envelope.step > e.step
          && other.envelope.request?.kind === 'admission' && owns(pr, other.envelope)
          && (!other.prNumber || other.prNumber === pr.number)
          && (other.envelope.target !== 'pull_request' || other.envelope.number === pr.number)
          && (!other.envelope.continuation?.pullRequest || other.envelope.continuation.pullRequest === pr.number)
          && (!other.envelope.request.existing_pr || other.envelope.request.existing_pr === pr.number));
        if (pr.head.ref !== e.branch || linkedIssue(pr.body) !== e.issueNumber || owners.length !== 1)
          fail('PR_AUTHORITY_CHANGED');
      }
    }
    // Discovery here is read-only: a sibling's PR is never remembered as ours,
    // and its current title, Step labels, ref and readiness remain untouched.
    return null;
  }
  async function existingPullRequest(r, { allowStepMirror = false, attemptOnly = false, publishedTransition = null } = {}) {
    if (attemptOnly) return historicalManualPullRequest(r);
    const e = r.envelope;
    const projection = await projectionFor(e, { sameBranch: true });
    if (e.target === 'pull_request') {
      const pr = await api.get(`/pulls/${e.number}`); assertPr(pr, e.number); return pr;
    }
    const pr = await findCurrentIssuePullRequest(api, e, r.prNumber ?? e.continuation?.pullRequest, publishedTransition);
    if (!pr && r.prIntent) fail('PR_PUBLICATION_UNCERTAIN');
    if (!pr && (await publicationRecords(e)).some(other => other.envelope?.attemptId !== e.attemptId
      && other.envelope?.repository === e.repository && other.envelope?.branch === e.branch
      && other.prIntent && !other.prNumber)) fail('PR_PUBLICATION_UNCERTAIN');
    if (e.continuation && !e.continuation.pullRequest && !r.publishedHead
      && !r.prepublicationRecovery?.publication?.publishedHead && pr) fail('PR_AUTHORITY_CHANGED');
    // Native admission and exact Task/PR/head relationships bind this result.
    // Step/title drift is presentation; admission/handoff projection repairs it
    // without inventing a different execution or overwriting a later attempt.
    if (pr) {
      // An uncertain POST has no number receipt yet. Reconcile its own native
      // attempt binding, not a different compatible PR created in the meantime.
      if (r.prIntent && !r.prNumber && !String(pr.body).split(/\r?\n/).includes(`Attempt: ${e.attemptId}`)) fail('PR_PUBLICATION_UNCERTAIN');
      await rememberPullRequest(r, pr);
    }
    return pr;
  }

  async function observeReadiness(r, pr) {
    return { pr, readiness: prReadiness(pr, r.publishedHead) };
  }

  async function successfulOutcomeIntent(r, renderBody, head, prNumber, metadata = {}) {
    if (r.successOutcomeIntent) {
      if (r.successOutcomeIntent.head !== head || r.successOutcomeIntent.prNumber !== prNumber) fail('OUTCOME_BINDING_CHANGED');
      return r.successOutcomeIntent.body;
    }
    const body = renderBody();
    r.successOutcomeIntent = { body: secretFree(body), head, prNumber, ...metadata };
    await store.put(r.envelope.runId, r);
    return body;
  }

  async function reconcileReadinessOutcome(r) {
    const intent = r.readinessIntent;
    if (!intent) return;
    const e = r.envelope;
    const path = `/issues/comments/${r.outcome.outcomeId}`;
    const marker = `<!-- relay:${e.attemptId}:outcome -->`;
    const outcome = await api.get(path);
    if (outcome.user?.login !== WRITER || !outcome.body?.endsWith(marker)
      || !outcome.body.startsWith('## Codex Outcome\n\nStatus: IMPLEMENTED_PENDING_FRESH_REVIEW\n')) fail('COMMENT_CONTENT_CHANGED');
    const anchor = `Latest durable candidate head: ${r.publishedHead}\n`;
    const previous = anchor + readinessOutcomeLines(r.outcome.readiness, r.outcome.draft);
    const desired = anchor + readinessOutcomeLines(intent.readiness, intent.draft);
    if (!outcome.body.includes(previous) && !outcome.body.includes(desired)) fail('COMMENT_CONTENT_CHANGED');
    const body = outcome.body.includes(desired) ? outcome.body : outcome.body.replace(previous, desired);
    if (body !== outcome.body) {
      await api.patch(path, { body: secretFree(body) });
      const observed = await api.get(path);
      if (observed.body !== body || observed.user?.login !== WRITER) fail('COMMENT_CONTENT_CHANGED');
    }
    r.outcome = { ...r.outcome, readiness: intent.readiness, draft: intent.draft, bodySha256: sha256Body(body) };
    if (r.commentBodies?.outcome) r.commentBodies.outcome.sha256 = r.outcome.bodySha256;
    r.readinessIntent = null;
    await store.put(e.runId, r);
  }

  function blockedAdmissionEnvelope(admitted) {
    return { version: VERSION, repository: REPOSITORY, consumerDigest: CONSUMER_DIGEST, attemptId: admitted.attemptId, runId: admitted.runId,
      target: admitted.target, number: admitted.number, issueNumber: admitted.issueNumber, route: admitted.route, step: admitted.step,
      ...(admitted.transport ? { transport: admitted.transport, readyEventId: admitted.readyEventId,
        readyEventAt: admitted.readyEventAt, readyLabel: admitted.readyLabel, runName: admitted.runName } : {}),
      branch: null, startHead: null, historicalBase: null,
      targetBase: exactSha(admitted.targetBase) ? admitted.targetBase : null, reviewId: null,
      authorityDigest: null, profile: { cliModelId: 'UNAVAILABLE', effort: 'UNAVAILABLE' },
      thread: 'UNAVAILABLE', title: 'UNAVAILABLE', closure: null, input: '', validation: [], admissionBlock: admitted.block };
  }

  function admissionBlockDiagnostic(block) {
    return { ...safeFailureFacts(block), ...(block.diagnosticRecorderFailed ? { diagnosticRecorderFailed: true } : {}), observed: { child: 'not_started', exitCode: null }, executionState: 'known-not-executed', executionId: null,
      lastSuccessfulBoundary: 'admission', failureBoundary: 'authority', classification: { code: block.code, source: 'observed', stage: 'authority' },
      primaryCause: block.code, containment: 'not_required', terminal: 'blocked', durable: { publishedHead: null, diagnosticStore: block.diagnosticStore ?? null },
      nextAction: 'correct-authority-before-new-owner-attempt', orchestration: 'COMPLETED' };
  }

  async function terminalOutcome(r, { terminalCode, diagnostic, publishedHead, executionWarnings = [] } = {}) {
    if (r.outcome) return r.outcome;
    if (r.successOutcomeIntent) fail('SUCCESS_OUTCOME_PUBLICATION_UNCERTAIN');
    const e = r.envelope;
    const authorityDrift = !r.admissionBlock && e.request?.kind === 'admission'
      ? (await revalidateAuthority(api, e, { reporting: true })).authorityDrift : undefined;
    let pr = null;
    if (!r.admissionBlock) {
      // Do not hide an unknown PR/readiness state behind an Issue fallback.
      pr = await existingPullRequest(r);
      if (pr && await isCurrentProjection(e)) {
        await guardPublication(e);
        pr = await transitionPr({ api, store, key: e.runId, record: r, head: pr.head.sha, draft: true,
          readPr: () => existingPullRequest(r) });
      }
    }
    const number = e.target === 'pull_request' ? e.number : pr?.number ?? e.issueNumber;
    const body = terminalOutcomeBody(e, { publishedHead: publishedHead ?? r.publishedHead, pr, terminalCode,
      diagnostic, executionWarnings, authorityDrift, secrets });
    const outcome = await commentOnce(r, 'outcome', number, body);
    r.outcome = { status: 'BLOCKED', head: exactSha(publishedHead ?? r.publishedHead) ? (publishedHead ?? r.publishedHead) : null,
      prNumber: pr?.number ?? null, outcomeId: outcome.id, bodySha256: sha256Body(outcome.body) };
    await store.put(e.runId, r);
    return r.outcome;
  }

  return {
    async dispatch(request) {
      try {
        const result = await dispatch(request);
        if (result?.status === 'BLOCKED' && request?.operation === 'admit') {
          const error = Object.assign(new Error(result.envelope?.admissionBlock?.code ?? 'ADMISSION_BLOCKED'), {
            code: result.envelope?.admissionBlock?.code ?? 'ADMISSION_BLOCKED' });
          const diagnosticStore = result.envelope?.admissionBlock?.diagnosticStore ?? await recordFailure({ error, operation: request?.operation, phase: 'authority',
            runId: request?.runId, workerStarted: result.envelope?.admissionBlock ? false : undefined, secrets: { knownSecrets: diagnosticSecrets } });
          return { ...result, diagnosticStore };
        }
        return result;
      } catch (error) {
        try {
          const diagnosticStore = await recordFailure({ error, operation: request?.operation, phase: request?.operation === 'admit' ? 'authority' : 'writer-publication',
            runId: request?.runId, workerStarted: request?.operation === 'admit' && ['OWNER_RUN_NOT_ADMITTED', 'ADMISSION_QUIESCED'].includes(error.code) ? false : undefined, secrets: { knownSecrets: diagnosticSecrets } });
          if (diagnosticStore) error.details = { ...error.details, diagnosticStore };
        } catch { error.details = { ...error.details, diagnosticRecorderFailed: true }; }
        throw error;
      }
    }
  };
  async function dispatch(request) {
      if (request?.repository !== undefined) {
        if (request.repository !== REPOSITORY) fail('ATTEMPT_REPOSITORY_MISMATCH');
        const { repository, ...operationRequest } = request;
        request = operationRequest;
      }
      if (request?.operation === 'manual-outcome-direct' && !allowManualOutcome) fail('MANUAL_CAPABILITY_REQUIRED');
      if (request?.operation === 'begin-remediation') {
        if (!lifecycleStore) fail('PR_LIFECYCLE_STORE_REQUIRED');
        return receipt(await beginRemediation({ api, store: lifecycleStore, request }));
      }
      if (!request || !positive(request.runId)) fail('BROKER_REQUEST_INVALID');
      if (request.operation === 'admit') {
        if (CONSUMER.executionSlots && request.route === 'auto') executionConsumer(request.executionSlot);
        if (!CONSUMER.executionSlots && Object.hasOwn(request, 'executionSlot')) fail('EXECUTION_SLOT_INVALID');
        const existing = await store.get(request.runId);
        if (existing && existing.envelope.consumerDigest !== CONSUMER_DIGEST) fail('CONSUMER_CONFIG_CHANGED');
        if (existing) {
          const e = existing.envelope;
          const mayRecoverUnreturnedAdmission = existing.nativeAdmission === true && e.transport === 'label'
            && existing.readyConsumed !== true && existing.readyConsumption === undefined
            && !existing.admissionBlock && !existing.outcome;
          if (existing.predispatchRecovery) fail('PREDISPATCH_ATTEMPT_FINALIZED');
          if (e.target !== request.target || e.number !== request.number || e.route !== request.route
            || (e.transport !== 'label' && e.issueNumber !== request.issueNumber)
            || e.transport !== request.transport
            || (e.executionSlot ?? null) !== (request.executionSlot ?? null)) fail('RUN_BINDING_CHANGED');
          const replacementPredecessorReplayCandidates = mayRecoverUnreturnedAdmission
            ? (await publicationRecords({ repository: e.repository, issueNumber: e.issueNumber }))
              .filter(record => record.envelope?.issueNumber === e.issueNumber
                && record.envelope?.runId !== e.runId && record.predispatchPending
                && (predispatchReadyReplacementReported(record)
                  || record.predispatchRecovery?.version === 4 && completedPredispatchRecovery(record)
                    && record.predispatchRecovery.binding.replacementEnvelopeDigest === digest(e)))
            : [];
          const recoverUnreturnedAdmission = mayRecoverUnreturnedAdmission
            && replacementPredecessorReplayCandidates.length > 0;
          let admissionUnstarted = false;
          // A pending boundary may already have released its resource under the
          // Writer lock. Never resume its command deletion or issue launch
          // authority, even if a later journal appears or DELETE was in flight.
          if (existing.predispatchPending) {
            if (existing.readyConsumption?.status === 'deleting') {
              if (!pendingPredispatchRecord(existing)) fail('READY_CONSUMPTION_UNCERTAIN');
              fail('PREDISPATCH_ATTEMPT_FINALIZED');
            }
            if (existing.readyConsumption && !consumedPredispatchMarker(existing)) fail('READY_CONSUMPTION_UNCERTAIN');
            if (!recoverUnreturnedAdmission) fail('PREDISPATCH_ATTEMPT_FINALIZED');
          }
          if (recoverUnreturnedAdmission) {
            await revalidateUnreturnedAdmission({ api, journal, record: existing, checkoutAbsent });
            if (e.route === 'auto') {
              if (!admission?.assertOpen || !admission?.assertSlotComplete)
                fail('PREDISPATCH_EXECUTION_EVIDENCE_CONFLICT');
              await admission.assertOpen();
              await admission.assertSlotComplete(e.executionSlot ?? 'primary');
              admissionUnstarted = true;
            }
            await revalidateReadyEvent(api, e);
            for (const previous of replacementPredecessorReplayCandidates) {
              if (previous.predispatchRecovery) {
                if (!completedPredispatchRecovery(previous) || await journal.get(previous.envelope.runId, previous.envelope.repository)
                  || !await checkoutAbsent(previous.envelope)) fail('PREDISPATCH_EXECUTION_EVIDENCE_CONFLICT');
                continue;
              }
              if (await journal.get(previous.envelope.runId, previous.envelope.repository)
                || !await checkoutAbsent(previous.envelope)) fail('PREDISPATCH_EXECUTION_EVIDENCE_CONFLICT');
              try {
                const state = await predispatchReplacementState({ api, journal, record: previous,
                  replacement: e, replacementRecord: existing, checkoutAbsent });
                await finalizePredispatchReplacement({ api, store, journal, record: previous,
                  replacementRecord: existing, checkoutAbsent, expectedBinding: state.binding });
              } catch (error) {
                if (!replacementRetirementCanDefer(error)) throw error;
                await recordFailure({ error, operation: 'predispatch-retirement-deferred', phase: 'authority', runId: request.runId, secrets: { knownSecrets: diagnosticSecrets } });
              }
            }
          }
          if (e.transport === 'label' && !existing.readyConsumed) {
            if (existing.readyConsumption) await consumeReadyCommand(existing);
            if (e.route === 'auto' && !existing.admissionBlock && !recoverUnreturnedAdmission) {
              // runAttempt already refuses an absent/mismatched replay journal.
              // Enforce that same invariant BEFORE changing any native metadata
              // or deleting the original owner command during admit replay.
              const saved = await journal?.get(e.runId);
              if (!saved || saved.version !== VERSION || !Object.hasOwn(saved, 'execution'))
                fail('JOURNAL_MISSING_EXECUTION_UNKNOWN');
              if (digest(saved.envelope) !== digest(e)) fail('JOURNAL_BINDING_CHANGED');
            }
            await revalidateReadyEvent(api, e);
            if (!existing.admissionBlock) await projectAdmittedStep(existing);
            await consumeReadyCommand(existing);
          }
          if (existing.admissionBlock) {
            if (!existing.outcome) await terminalOutcome(existing, { terminalCode: existing.admissionBlock.code, diagnostic: admissionBlockDiagnostic(existing.admissionBlock) });
            return receipt({ envelope: e, resumed: true, status: 'BLOCKED', outcome: existing.outcome });
          }
          // The attempt's preflight revalidates live authority inside its
          // terminal boundary; admission replay must not bypass that path.
          return receipt({ envelope: e, resumed: true,
            ...(admissionUnstarted ? { admissionUnstarted: true } : {}) });
        }
        // Installed helpers hold the same root lock as lifecycle quiesce.
        // Reserve full controller ownership in this existing attempt before
        // the ready event is consumed or a child can be launched.
        if (request.route === 'auto') await admission?.assertOpen();
        if (request.route === 'auto' && CONSUMER.executionSlots) {
          if (!request.executionSlot || !admission?.assertSlotComplete) fail('EXECUTION_SLOT_INVALID');
          await admission.assertSlotComplete(request.executionSlot);
        }
        if (request.route === 'auto' && !CONSUMER.executionSlots) await admission?.assertSlotComplete?.('primary');
        const subject = await api.get(request.target === 'issue' ? `/issues/${request.number}` : `/pulls/${request.number}`);
        let task = request.target === 'issue' ? request.number : null;
        if (request.target === 'pull_request') {
          try { task = linkedIssue(subject.body); } catch (error) { if (error.code !== 'CANONICAL_ISSUE_AMBIGUOUS') throw error; }
        }
        const charter = request.target === 'issue' ? subject : task ? await api.get(`/issues/${task}`) : null;
        const nativeAdmission = charter !== null && authorityMode(charter.body) === 'github-native-v1';
        const priorRecords = nativeAdmission ? (await publicationRecords({ repository: REPOSITORY, issueNumber: task }))
          .filter(record => record.envelope?.repository === REPOSITORY) : [];
        const replacementPredecessors = [];
        for (const previous of priorRecords.filter(record => record.envelope?.issueNumber === task && record.predispatchPending)) {
          const original = previous.envelope;
          if (previous.predispatchRecovery) {
            if (!completedPredispatchRecovery(previous) || !journal || await journal.get(original.runId, original.repository)
              || !checkoutAbsent || !await checkoutAbsent(original)) fail('PREDISPATCH_EXECUTION_EVIDENCE_CONFLICT');
            continue;
          }
          if (consumedPredispatchMarker(previous)) {
            if (request.route === 'auto' && (original.executionSlot ?? 'primary') === (request.executionSlot ?? 'primary')) {
              if (!admission?.assertSlotComplete) fail('PREDISPATCH_EXECUTION_EVIDENCE_CONFLICT');
              await admission.assertSlotComplete(original.executionSlot ?? 'primary');
            }
            continue;
          }
          const replacementReported = predispatchReadyReplacementReported(previous);
          if (!(pendingPredispatchRecord(previous) || replacementReported)
            || !journal || await journal.get(original.runId, original.repository)
            || !checkoutAbsent || !await checkoutAbsent(original)) fail('PREDISPATCH_EXECUTION_EVIDENCE_CONFLICT');
          if (previous.readyConsumption && !replacementReported) fail('READY_CONSUMPTION_UNCERTAIN');
          if (replacementReported) replacementPredecessors.push(previous);
        }
        // Physical slot/process and attempt-checkout guards prove execution
        // isolation. An older Task Outcome is not a resource reservation.
        const allocation = nativeAdmission ? nextAdmissionStep(priorRecords, task, charter.labels) : {};
        const previousRecord = allocation.lineage ? priorRecords.find(record => record.envelope?.attemptId === allocation.lineage.attempt) : undefined;
        const admitted = await admitEnvelope(api, request, { nextStep: allocation.step, lineage: allocation.lineage, previousRecord,
          recordFailure: input => recordFailure({ ...input, secrets: { knownSecrets: diagnosticSecrets } }) });
        const slotBound = { ...admitted, ...(request.executionSlot ? { executionSlot: request.executionSlot } : {}) };
        const envelope = admitted.blocked ? { ...blockedAdmissionEnvelope(admitted), ...(request.executionSlot ? { executionSlot: request.executionSlot } : {}) }
          : validateEnvelope(slotBound);
        // Reserve the native event in the existing attempt record, under the
        // Writer lock. This is replay protection, never a Step ledger.
        if (envelope.transport === 'label') {
          for (const previous of await publicationRecords(envelope)) {
            const prior = previous.envelope;
            if (prior?.repository !== REPOSITORY) continue;
            if (prior.readyEventId === envelope.readyEventId) fail('READY_EVENT_ALREADY_CONSUMED');

          }
        }
        if (envelope.transport === 'label') await revalidateReadyEvent(api, envelope);
        if (!admitted.blocked && nativeAdmission) {
          const current = await api.get(`/issues/${task}`);
          if (envelope.issueNumber !== task || current.number !== task
            || (charter.id !== undefined && current.id !== charter.id)
            || canonicalAuthorityJson(stepLabels(current)) !== canonicalAuthorityJson(stepLabels(charter)))
            fail('STEP_LABEL_POSITION_CHANGED');
        }
        const replacementStates = [];
        if (!admitted.blocked) {
          for (const previous of replacementPredecessors) {
            try {
              const state = await predispatchReplacementState({ api, journal, record: previous,
                replacement: envelope, checkoutAbsent });
              replacementStates.push({ record: previous, binding: state.binding });
            } catch (error) {
              if (!replacementRetirementCanDefer(error)) throw error;
                await recordFailure({ error, operation: 'predispatch-retirement-deferred', phase: 'authority', runId: request.runId, secrets: { knownSecrets: diagnosticSecrets } });
            }
          }
        }
        // Keep lifecycle failure before execution reservation and ready-command
        // consumption. The same CR/head can reconcile its pending Draft intent
        // without creating an unknown execution or publishing another review.
        if (!admitted.blocked) await prepareRemediation(envelope);
        const r = { envelope, ...(nativeAdmission ? { nativeAdmission: true } : {}), ...(admitted.blocked ? { admissionBlock: admitted.block } : {}),
          ...(!admitted.blocked && nativeAdmission ? { stepProjectionFrom: stepLabels(charter) } : {}),
          ...(!admitted.blocked && nativeAdmission && envelope.route === 'auto' && envelope.transport === 'label'
            ? { predispatchPending: { version: 1, projectionFrom: stepLabels(charter) } } : {}),
          ...(!admitted.blocked && envelope.route === 'auto' && admission ? { controllerLifecycle: await admission.reserve() } : {}),
          ...(envelope.continuation?.pullRequest ? { prNumber: envelope.continuation.pullRequest } : {}),
          publicationIntent: null, publishedHead: null, finalHead: null, outcome: null };
        await store.put(request.runId, r);
        for (const state of replacementStates) {
          try {
            await finalizePredispatchReplacement({ api, store, journal, record: state.record,
              replacementRecord: r, checkoutAbsent, expectedBinding: state.binding });
          } catch (error) {
            if (!replacementRetirementCanDefer(error)) throw error;
                await recordFailure({ error, operation: 'predispatch-retirement-deferred', phase: 'authority', runId: request.runId, secrets: { knownSecrets: diagnosticSecrets } });
          }
        }
        if (!admitted.blocked && nativeAdmission) {
          await projectAdmittedStep(r);
        }
        if (envelope.transport === 'label') {
          await consumeReadyCommand(r);
        }
        if (admitted.blocked) {
          const block = admitted.block;
          try { await terminalOutcome(r, { terminalCode: block.code, diagnostic: admissionBlockDiagnostic(block) }); }
          catch (cause) {
            const error = Object.assign(new Error(block.code), { code: block.code, details: {
              ...safeFailureFacts(block), childState: 'not_started', diagnosticStore: block.diagnosticStore,
              diagnosticRecorderFailed: block.diagnosticRecorderFailed, outcomePublication: safeOutcomePublication(cause)
            }, native: { outcomePublicationFailure: cause } });
            throw error;
          }
          return receipt({ envelope, status: 'BLOCKED', outcome: r.outcome });
        }
        return receipt({ envelope });
      }
      const r = await bound(request, request.operation === 'manual-outcome-direct' ? { revalidate: false }
        : request.operation === 'terminal-outcome' ? { revalidate: false, allowAdmissionBlock: true }
        : ['publication-state', 'recover-publication', 'complete-handoff', 'complete-execution', 'prepublication-state', 'recover-prepublication', 'predispatch-state', 'predispatch-authorization', 'finalize-predispatch'].includes(request.operation) ? { revalidate: false }
          : { reporting: ['collect-progress', 'finish', 'finish-no-change'].includes(request.operation),
            verifyStartingBase: ['preflight', 'publish-progress'].includes(request.operation) }); const e = r.envelope;
      if (r.predispatchRecovery && !['publication-state', 'predispatch-state', 'predispatch-authorization', 'finalize-predispatch'].includes(request.operation)) fail('PREDISPATCH_ATTEMPT_FINALIZED');
      if (['predispatch-state', 'predispatch-authorization', 'finalize-predispatch'].includes(request.operation)) {
        if (Object.keys(request).some(key => !['operation', 'runId', 'attemptId', 'authorizationId', 'workflowReadToken', 'executionSlot'].includes(key))) fail('RECOVERY_REQUEST_INVALID');
        if (!journal?.withLock) fail('PREDISPATCH_CONTROLLER_LOCK_REQUIRED');
        return journal.withLock(e.runId, async () => {
          if (request.operation === 'predispatch-authorization') {
            if (r.predispatchRecovery) {
              if (!completedPredispatchRecovery(r) || r.predispatchRecovery.authorizationId !== request.authorizationId)
                fail('PREDISPATCH_RECOVERY_BINDING_CHANGED');
              return receipt({ binding: r.predispatchRecovery.binding,
                authorization: { id: request.authorizationId, authorizedAt: r.predispatchRecovery.authorizedAt } });
            }
            const state = await predispatchState({ api, journal, record: r, checkoutAbsent });
            const authorizedAt = await authorizeRecovery(api, e, request.authorizationId, state.binding);
            return receipt({ ...state, authorization: { id: request.authorizationId, authorizedAt } });
          }
          if (request.operation === 'predispatch-state') {
            if (r.predispatchRecovery) {
              if (!completedPredispatchRecovery(r)) fail('PREDISPATCH_RECOVERY_BINDING_CHANGED');
              return receipt({ recovery: r.predispatchRecovery });
            }
            return receipt(await predispatchState({ api, journal, record: r, checkoutAbsent }));
          }
          if (!r.predispatchRecovery) await assertPredispatchFence(e);
          return receipt({ recovery: await finalizePredispatch({ api, store, journal, record: r, request, checkoutAbsent }) });
        });
      }
      if (r.prepublicationRecovery && !['prepublication-state', 'recover-prepublication'].includes(request.operation)) fail('PREPUBLICATION_RECOVERY_RESERVED');
      if (['prepublication-state', 'recover-prepublication'].includes(request.operation)
        && Object.keys(request).some(key => !['operation', 'runId', 'attemptId', 'head', 'authorizationId', 'workflowReadToken', 'executionSlot'].includes(key))) fail('RECOVERY_REQUEST_INVALID');
      if (request.operation === 'prepublication-state') {
        const { binding, authorizationBody, recovery } = await prepublicationState({ api, journal, record: r, head: request.head });
        return receipt({ binding, authorizationBody, recovery });
      }
      if (request.operation === 'recover-prepublication') {
        await guardPublication(e);
        return receipt(await recoverPrepublication({ api, store, publisher, journal, record: r, request,
          collect: async envelope => {
            if (!collectRetained) fail('RETAINED_COLLECTOR_UNAVAILABLE');
            return collectRetained(envelope);
          },
          checkPullRequest: async previous => {
            const pr = await findCurrentIssuePullRequest(api, e, r.prNumber ?? e.continuation?.pullRequest);
            // This route is restricted to prepublication, with no original PR.
            if (pr || e.continuation?.pullRequest || previous !== (e.continuation ? e.startHead : null)) fail('PR_AUTHORITY_CHANGED');
          },
          finish: async recovery => {
            const head = recovery.publication.publishedHead;
            const readPr = async () => {
              await revalidateAuthority(api, e);
              const pr = await existingPullRequest(r);
              if (!pr || pr.head.sha !== head || (recovery.outcome && pr.number !== recovery.outcome.prNumber)
                || pr.user?.login !== WRITER || pr.user?.type !== 'Bot'
                || pr.user?.id !== recovery.binding.writer.id
                || !pr.body?.split(/\r?\n/).includes(`Attempt: ${e.attemptId}`)
                || !pr.body?.split(/\r?\n/).includes(`Execution admission digest: ${admissionBinding(e.request).sha256}`)) fail('PR_AUTHORITY_CHANGED');
              return pr;
            };
            if (!recovery.outcome) {
              await pullRequest(r);
              await readPr();
              // This intent was created after the recovery reservation. Exact
              // native attempt/Request/head observation resolves it.
              if (r.prIntent) { r.prIntent = null; await store.put(e.runId, r); }
              const drafted = await transitionPr({ api, store, key: e.runId, record: r, head, draft: true, readPr });
              const readiness = prReadiness(drafted, head);
              if (!recovery.outcomeIntent) {
                const saved = await journal.get(e.runId);
                const body = automaticOutcomeBody(e, `## Codex Outcome\n\nStatus: IMPLEMENTED_PENDING_FRESH_REVIEW\nThread: ${e.thread}\nAttempt: ${e.attemptId}\nRequested model: ${e.profile.cliModelId}; effort: ${e.profile.effort}\nActual model/effort: UNAVAILABLE\n${usageOutcomeSummary(saved.execution.codexUsage)}\nHistorical reviewed/starting head: ${e.startHead}\nLatest durable candidate head: ${head}\n${readinessOutcomeLines(readiness)}\nCompletion: COMPLETED\nRecovery authorization: #${recovery.authorizationId}\nHistorical BLOCKED Outcome: https://github.com/${REPOSITORY}/issues/${e.issueNumber}#issuecomment-${r.outcome.outcomeId}\n\n`, `\n\nTrusted Writer recovered independently verified retained object bytes from the original contained successful execution. The original blocked Outcome, journal and collection failure remain unchanged. Recovery does not rerun Codex or establish native exact-head validation, independent acceptance, merge or deployment.`, { pr: drafted, head, taskResult: saved.execution.result, secrets,
                  markerKey: `prepublication-${recovery.authorizationId}` });
                recovery.outcomeIntent = { body: secretFree(body), readiness };
                await store.put(e.runId, r);
              }
              const key = `prepublication-${recovery.authorizationId}`;
              const outcome = await commentOnce(r, key, drafted.number, recovery.outcomeIntent.body);
              const observed = await api.get(`/issues/comments/${outcome.id}`);
              if (observed.id !== outcome.id || observed.user?.login !== WRITER
                || observed.user?.id !== recovery.binding.writer.id || observed.user?.type !== 'Bot'
                || observed.issue_url !== `https://api.github.com/repos/${REPOSITORY}/issues/${drafted.number}`
                || observed.body !== outcome.body) fail('COMMENT_CONTENT_CHANGED');
              recovery.outcome = { status: 'IMPLEMENTED_PENDING_FRESH_REVIEW', head, prNumber: drafted.number,
                outcomeId: observed.id, bodySha256: sha256Body(observed.body), readiness: recovery.outcomeIntent.readiness,
                draft: drafted.draft, recoveryAuthorizationId: recovery.authorizationId };
              await store.put(e.runId, r);
            }
            // This is a new handoff proof, not admission.complete's old BLOCKED
            // shortcut. Reread original evidence before granting native Ready.
            await prepublicationState({ api, journal, record: r, head });
            if (r.prIntent || r.commentIntent || recovery.collection.clean !== true
              || recovery.collection.head !== head) fail('EXECUTION_HANDOFF_NOT_PROVEN');
            const outcome = await api.get(`/issues/comments/${recovery.outcome.outcomeId}`);
            if (outcome.id !== recovery.outcome.outcomeId || outcome.user?.login !== WRITER
              || outcome.user?.id !== recovery.binding.writer.id || outcome.user?.type !== 'Bot'
              || outcome.issue_url !== `https://api.github.com/repos/${REPOSITORY}/issues/${recovery.outcome.prNumber}`
              || sha256Body(outcome.body) !== recovery.outcome.bodySha256
              || !outcome.body?.endsWith(`<!-- relay:${e.attemptId}:prepublication-${recovery.authorizationId} -->`)) fail('COMMENT_CONTENT_CHANGED');
            recovery.handoffProven = true;
            await store.put(e.runId, r);
            const pr = await transitionPr({ api, store, key: e.runId, record: r, head, draft: false, readPr });
            recovery.outcome.draft = pr.draft; recovery.complete = true;
            await store.put(e.runId, r);
            return recovery.outcome;
          } }));
      }
      if (request.operation === 'publication-state') {
        return receipt({ envelope: e, publicationIntent: r.publicationIntent, publishedHead: r.publishedHead,
          admissionState: { predispatchRecovery: r.predispatchRecovery ?? null, step: e.step, stepProjected: r.stepProjected ?? null,
            stepProjectionFrom: r.stepProjectionFrom ?? null, readyEventId: e.readyEventId ?? null,
            readyConsumption: r.readyConsumption?.status ?? null, readyConsumed: r.readyConsumed ?? null,
            controllerLifecycle: r.controllerLifecycle ? {
              version: r.controllerLifecycle.version, status: r.controllerLifecycle.status,
              ...(r.controllerLifecycle.child ? { child: r.controllerLifecycle.child } : {}),
              ...(r.controllerLifecycle.containment ? { containment: r.controllerLifecycle.containment } : {}) } : null,
            failureDiagnostic: failureDiagnosticFromDetails({ failureDiagnostic: r.admissionFailure?.diagnostic }) ?? null },
          recovery: r.publicationRecoveries?.find(value => value.authorizationId === request.authorizationId) ?? null,
          authorizationBody: r.publicationIntent ? recoveryAuthorizationBody(recoveryAuthorization(e, r.publicationIntent,
            r.publicationRecoveries?.at(-1)?.authorizationId ?? null)) : null });
      }
      if (request.operation === 'recover-publication') {
        await guardPublication(e);
        return receipt(await recoverPublication({ api, store, publisher, record: r, request }));
      }
      if (request.operation === 'complete-execution') {
        if (Object.keys(request).sort().join(',') !== 'attemptId,operation,runId'
          || e.route !== 'auto') fail('RECOVERY_REQUEST_INVALID');
        const saved = await journal?.get(e.runId);
        if (!saved || saved.version !== VERSION || digest(saved.envelope) !== digest(e)
          || !saved.outcome || !r.outcome
          || !['BLOCKED', 'IMPLEMENTED_PENDING_FRESH_REVIEW'].includes(saved.outcome.status)
          || !['status', 'head', 'prNumber', 'outcomeId'].every(key => saved.outcome[key] === r.outcome[key])
          || saved.diagnostic?.orchestration === 'FAILED' || r.publicationIntent || r.commentIntent
          || saved.execution !== null && (saved.execution?.reserved !== true || saved.execution.returned !== true
            || !['started', 'not_started'].includes(saved.execution.child)
            || !(saved.execution.containment === 'reaped'
              || (saved.execution.child === 'not_started' && saved.execution.containment === 'not_required'))))
          fail('ADMISSION_COMPLETION_UNKNOWN');
        await admission?.complete({ runId: e.runId, attemptId: e.attemptId });
        if (!admission && r.predispatchPending) {
          if (!consumedPredispatchMarker(r)) fail('ADMISSION_COMPLETION_UNKNOWN');
          delete r.predispatchPending;
          await store.put(e.runId, r);
        }
        const completed = await store.get(e.runId);
        if (!Object.hasOwn(completed, 'predispatchPending')) delete r.predispatchPending;
        Object.assign(r, completed);
        return receipt({ complete: true });
      }
      if (request.operation === 'complete-handoff') {
        if (r.handoffComplete) return receipt(r.outcome);
        const saved = await journal?.get(e.runId);
        if (e.route !== 'auto' || !saved || digest(saved.envelope) !== digest(e)
          || saved.version !== VERSION || saved.diagnostic
          || saved.execution?.reserved !== true || saved.execution.returned !== true
          || saved.execution.child !== 'started' || saved.execution.containment !== 'reaped'
          || saved.execution.result?.status !== 'success'
          || !(typeof saved.collection?.clean === 'boolean' || saved.collection?.clean === null && saved.collection?.preserved === true && saved.collection?.worktreeObservation?.status === 'unknown') || saved.collection.head !== r.finalHead
          || r.outcome?.status !== 'IMPLEMENTED_PENDING_FRESH_REVIEW'
          || !['status', 'head', 'prNumber', 'outcomeId'].every(key => saved.outcome?.[key] === r.outcome[key])
          || r.publicationIntent || r.commentIntent) fail('EXECUTION_HANDOFF_NOT_PROVEN');
        // Full controller completion is recorded from the protected journal,
        // before any Ready mutation. No caller claims can replace this proof.
        await admission?.complete({ runId: e.runId, attemptId: e.attemptId });
        if (!admission && r.predispatchPending) {
          if (!consumedPredispatchMarker(r)) fail('EXECUTION_HANDOFF_NOT_PROVEN');
          delete r.predispatchPending;
          await store.put(e.runId, r);
        }
        // admission.complete may have updated the same protected record.
        const completed = await store.get(e.runId);
        if (!Object.hasOwn(completed, 'predispatchPending')) delete r.predispatchPending;
        Object.assign(r, completed);
        if (!r.outcome.prNumber || !await isCurrentProjection(e)) {
          r.handoffComplete = true; await store.put(e.runId, r); return receipt(r.outcome);
        }
        await guardPublication(e);
        const outcome = await api.get(`/issues/comments/${r.outcome.outcomeId}`);
        if (outcome.user?.login !== WRITER || !outcome.body?.endsWith(`<!-- relay:${e.attemptId}:outcome -->`)
          || !outcome.body.startsWith('## Codex Outcome\n\nStatus: IMPLEMENTED_PENDING_FRESH_REVIEW\n')
          || sha256Body(outcome.body) !== r.outcome.bodySha256) fail('COMMENT_CONTENT_CHANGED');
        const pr = await transitionPr({ api, store, key: e.runId, record: r, head: r.finalHead, draft: false,
          readPr: async () => {
            await revalidateAuthority(api, e, { handoff: true });
            const current = await existingPullRequest(r);
            if (!current || current.number !== r.outcome.prNumber) fail('PR_AUTHORITY_CHANGED');
            return current;
          } });
        r.outcome.draft = pr.draft; r.handoffComplete = true;
        await store.put(e.runId, r);
        return receipt(r.outcome);
      }
      if (request.operation === 'preflight') {
        if (r.predispatchPending) {
          const saved = await journal?.get(e.runId, e.repository);
          if (!consumedPredispatchRecord(r) || !saved || saved.version !== VERSION
            || digest(saved.envelope) !== digest(e) || !Object.hasOwn(saved, 'execution')
            || saved.execution !== null && (saved.execution?.reserved !== true || saved.execution.returned !== true))
            fail('PREDISPATCH_CONTROLLER_JOURNAL_REQUIRED');
        }
        const a = await revalidateAuthority(api, e);
        if (a.pr && a.pr.head.sha !== (r.publishedHead ?? e.startHead)) fail('REMOTE_HEAD_CHANGED');
        if (e.continuation) {
          const refs = await api.get(`/git/matching-refs/heads/${e.branch}`);
          const exact = Array.isArray(refs) ? refs.filter(ref => ref.ref === `refs/heads/${e.branch}`) : [];
          if (exact.length !== 1 || exact[0].object?.sha !== (r.publishedHead ?? e.startHead)) fail('REMOTE_HEAD_CHANGED');
          await existingPullRequest(r);
        }
        // A reviewed dirty PR is the resolver's input. Bind the observed main,
        // then let trusted checkout/publication validate its Git ancestry.
        if (e.target === 'pull_request') await revalidateIntegrationBase(api, e);
        if (a.pr && !r.finalHead && await isCurrentProjection(e)) {
          await guardPublication(e);
          a.pr = await projectTaskRelationship(r, a.pr);
        }
        if (a.pr && !r.finalHead && await isCurrentProjection(e)) {
          const title = titleFor(e);
          if (a.pr.title !== title) await api.patch(`/pulls/${a.pr.number}`, { title });
        }
        if (a.pr && !a.pr.draft && !r.finalHead && await isCurrentProjection(e)) {
          await transitionPr({ api, store, key: e.runId, record: r, head: a.pr.head.sha, draft: true,
            readPr: () => existingPullRequest(r) });
        }
        return receipt({ envelope: e, publishedHead: r.publishedHead, finalHead: r.finalHead,
          ...(r.finalHead ? { outcome: receipt(r.outcome) } : {}) });
      }
      if (request.operation === 'collect-progress') {
        // The fixed root Writer derives both checkout and journal from its
        // immutable admission. Caller JSON cannot select a path or assert that
        // the worker is contained. Reuse the bounded retained-source reader;
        // private worker modes are not a reason to alter source permissions.
        if (Object.keys(request).some(key => !['operation', 'runId', 'attemptId', 'workflowReadToken', 'executionSlot', 'authorizationId'].includes(key))) fail('COLLECTION_REQUEST_INVALID');
        const recovery = Object.hasOwn(request, 'authorizationId');
        const saved = await journal?.get(e.runId);
        if (e.route !== 'auto' || !recovery && (r.finalHead || r.outcome)
          || !saved || saved.version !== VERSION || digest(saved.envelope) !== digest(e)
          || !recovery && (saved.outcome || saved.diagnostic)
          || saved.execution?.reserved !== true || saved.execution.returned !== true
          || !['started', 'not_started'].includes(saved.execution.child)
          || !(saved.execution.containment === 'reaped'
            || saved.execution.child === 'not_started' && saved.execution.containment === 'not_required')) fail('COLLECTION_NOT_ADMITTED');
        await guardPublication(e);
        const expected = recovery ? await authorizeRecoveryCollection({ api, record: r, authorizationId: request.authorizationId }) : null;
        if (recovery && (saved.execution.child !== 'started' || saved.execution.result?.status !== 'success'
          || saved.collection?.head !== expected)) fail('RECOVERY_EXECUTION_NOT_PROVEN');
        if (!collectRetained) fail('RETAINED_COLLECTOR_UNAVAILABLE');
        const progress = await collectRetained(e);
        if (expected && progress.head !== expected) fail('RECOVERY_CANDIDATE_CHANGED');
        return receipt(progress);
      }
      if (request.operation === 'publish-progress') {
        if (e.route !== 'auto' || r.finalHead) fail('PROGRESS_NOT_ADMITTED');
        await guardPublication(e);
        return publisher.inspect(e, request.bundle, async g => {
          if (e.request?.kind === 'admission' && e.target === 'issue' && !e.continuation
            && !await g.ancestor(e.startHead, 'refs/remotes/main')) fail('STARTING_STATE_MISMATCH');
          const previous = r.publishedHead ?? (e.target === 'pull_request' || e.continuation ? e.startHead : null);
          if (r.publicationIntent && r.publicationIntent.head !== g.head) fail('PUBLICATION_RECONCILIATION_REQUIRED');
          if (g.remoteHead === g.head) {
            if (!r.publicationIntent && r.publishedHead !== g.head) fail('UNATTRIBUTED_REMOTE_HEAD');
          } else {
            if (r.publicationIntent) fail('PUBLICATION_UNCERTAIN');
            if (g.remoteHead !== previous || !(await g.ancestor(e.startHead, g.head))
              || (previous && !(await g.ancestor(previous, g.head)))) fail('REMOTE_HEAD_CHANGED');
            if (!g.commits.length) fail('NO_PROGRESS');
            await revalidateAuthority(api, e, { verifyStartingBase: true });
            if (e.continuation) {
              const pr = await existingPullRequest(r);
              if (pr && pr.head.sha !== previous) fail('REMOTE_HEAD_CHANGED');
              if (await g.observe() !== previous) fail('REMOTE_HEAD_CHANGED');
            }
            if (g.integrationBase) await revalidateIntegrationBase(api, e);
            r.publicationIntent = { previous, head: g.head }; await store.put(e.runId, r);
            // No force, lease, reset or rewrite. Any push error is followed
            // only by exact observation, never by a second push.
            let pushFailure = null;
            try { await g.push(); } catch (error) { pushFailure = error; }
            let observed;
            try { observed = await g.observe(); }
            catch (error) {
              const observationDiagnostic = failureDiagnosticFromDetails(error?.details);
              publicationFailure('PUBLICATION_UNCERTAIN', { cause: error, diagnostic: {
                classification: observationDiagnostic?.classification ?? observationDiagnostic?.primaryCause ?? 'GIT_OBSERVATION_UNAVAILABLE',
                primaryCause: observationDiagnostic?.primaryCause ?? observationDiagnostic?.classification ?? 'GIT_OBSERVATION_UNAVAILABLE', operation: 'observe',
                ...(pushFailure ? { priorCause: pushFailure.details?.failureDiagnostic?.primaryCause ?? 'GIT_UNKNOWN_FAILURE' } : {})
              } });
            }
            if (observed !== g.head) {
              const observationCause = observed === null ? 'GIT_OBSERVATION_UNCERTAIN' : 'GIT_REMOTE_HEAD_CONFLICT';
              const unchangedAfterFailedPush = pushFailure && observed === previous;
              publicationFailure('PUBLICATION_UNCERTAIN', {
                // Push details belong to the primary cause only when observation
                // confirms the previous head. A conflict has only prior push context.
                cause: unchangedAfterFailedPush ? pushFailure : undefined,
                diagnostic: {
                  classification: unchangedAfterFailedPush ? pushFailure.details?.failureDiagnostic?.classification ?? 'GIT_UNKNOWN_FAILURE' : observationCause,
                  primaryCause: unchangedAfterFailedPush ? pushFailure.details?.failureDiagnostic?.primaryCause ?? 'GIT_UNKNOWN_FAILURE' : observationCause,
                  operation: unchangedAfterFailedPush ? 'push' : 'observe', ...(pushFailure && !unchangedAfterFailedPush ? { priorCause: pushFailure.details?.failureDiagnostic?.primaryCause ?? 'GIT_UNKNOWN_FAILURE' } : {})
                }
              });
            }
          }
          r.publishedHead = g.head; r.publicationIntent = null; await store.put(e.runId, r);
          const pr = await pullRequest(r, { previous, head: g.head });
          // A lagging PR API cannot erase a successful Git ref observation.
          return receipt({ publishedHead: g.head, prNumber: pr.number, prObservedHead: pr.head.sha, ready: false });
        });
      }
      if (request.operation === 'manual-outcome-direct') {
        return receipt(await publishManualOutcome({ api, store, record: r, submission: request.submission,
          checkPublication: (envelope, pr) => guardPublication(pr
            ? { ...envelope, target: 'pull_request', number: pr.number } : envelope),
          commentOnce, rememberPullRequest, existingPullRequest, revalidate: envelope => revalidateAuthority(api, envelope,
            { reporting: true, publicationTarget: request.submission.result.parent.kind === 'pull_request' ? request.submission.result.parent.number : undefined }),
          historical: async envelope => !await isCurrentProjection(envelope),
          projectPullRequest: async (record, pr) => {
            // A recovered exact Outcome may already have an independently
            // accepted final designation. Replaying it changes no closure link.
            const current = !record.outcome && pr.state === 'open' && !pr.merged
              ? await projectTaskRelationship(record, pr) : pr;
            return mirrorStep(record, current);
          },
          transitionManual: async (record, pr, result, draft) => {
            if (!pr || pr.state !== 'open' || pr.merged) return;
            if (!await isCurrentProjection(e)) return;
            await guardPublication(e);
            if (!draft && (!['git', 'no-change'].includes(result.result.kind) || result.result.revision !== pr.head.sha)) fail('PUBLISHED_HEAD_REQUIRED');
            await transitionPr({ api, store, key: e.runId, record, head: pr.head.sha, draft,
              readPr: async () => { await revalidateAuthority(api, e, { handoff: true, publicationTarget: pr.number }); const current = await api.get(`/pulls/${pr.number}`);
                assertPr(current, pr.number); if (current.head.ref !== pr.head.ref || linkedIssue(current.body) !== e.issueNumber) fail('PR_AUTHORITY_CHANGED');
                await assertManualPullRequestBinding(api, e, current, { unique: false }); return current; } });
          } }));
      }
      if (request.operation === 'finish-no-change') {
        if (r.outcome) return receipt(r.outcome);
        if (e.route !== 'auto' || e.request?.kind !== 'admission'
          || request.head !== e.startHead || r.publishedHead || r.publicationIntent) fail('NO_CHANGE_COMPLETION_INVALID');
        if (request.executionWarnings !== undefined && !Array.isArray(request.executionWarnings)) fail('EXECUTION_WARNING_INVALID');
        const executionWarnings = [...new Set([...(request.executionWarnings ?? []), ...(r.presentationWarnings ?? [])])];
        if (!Array.isArray(executionWarnings) || executionWarnings.some(code => !['RUNTIME_CLEANUP_FAILED', 'PRESENTATION_REPAIR_UNAVAILABLE', 'WORKTREE_OBSERVATION_INCOMPLETE'].includes(code)) || executionWarnings.length > 3) fail('EXECUTION_WARNING_INVALID');
        const pr = await existingPullRequest(r);
        if (pr && pr.head.sha !== e.startHead) fail('PR_HEAD_OBSERVATION_STALE');
        const number = pr?.number ?? e.issueNumber;
        const body = await successfulOutcomeIntent(r, () => automaticOutcomeBody(e, `## Codex Outcome\n\nStatus: IMPLEMENTED_PENDING_FRESH_REVIEW\nThread: ${e.thread}\nAttempt: ${e.attemptId}\nSource/result head: ${e.startHead}\nArtifact: ${pr ? `PR #${pr.number}` : 'No PR; unchanged source'}\nCompletion: COMPLETED\n\n`, `\n\nThe contained worker completed without source changes. No push or artificial PR was required. Independent exact-result review remains required.`, { pr, head: e.startHead, executionWarnings, authorityDrift: r.authorityDrift, taskResult: request.taskResult ?? {}, secrets }), e.startHead, pr?.number ?? null);
        let outcome = await commentOnce(r, 'outcome', number, body);
        const expectedBody = outcome.body;
        outcome = await api.get(`/issues/comments/${outcome.id}`);
        if (outcome.body !== expectedBody || outcome.user?.login !== WRITER) fail('COMMENT_CONTENT_CHANGED');
        r.finalHead = e.startHead; r.handoffComplete = false; r.successOutcomeIntent = null;
        r.outcome = { status: 'IMPLEMENTED_PENDING_FRESH_REVIEW', head: e.startHead, prNumber: pr?.number ?? null,
          outcomeId: outcome.id, bodySha256: sha256Body(outcome.body), ...(pr ? { draft: pr.draft } : {}), noChange: true };
        await store.put(e.runId, r);
        return receipt(r.outcome);
      }
      if (request.operation === 'handoff') {
        if (e.route !== 'manual') fail('MANUAL_ROUTE_REQUIRED');
        // Manual routing skips worker preflight. Both CR remediation and Issue
        // continuation must verify Draft before exposing an executable handoff.
        if (!r.outcome) {
          await prepareRemediation(e);
          if ((e.target === 'pull_request' || e.continuation?.pullRequest) && await isCurrentProjection(e)) {
            const pr = await existingPullRequest(r);
            if (pr) {
              await guardPublication(e);
              await projectTaskRelationship(r, pr);
            }
          }
          if (e.target === 'issue' && e.continuation?.pullRequest && await isCurrentProjection(e)) {
            await guardPublication(e);
            await transitionPr({ api, store, key: e.runId, record: r, head: e.startHead, draft: true,
              readPr: async () => {
                await revalidateAuthority(api, e);
                const pr = await existingPullRequest(r);
                if (!pr || pr.number !== e.continuation.pullRequest) fail('PR_AUTHORITY_CHANGED');
                return pr;
              } });
          }
        }
        const url = e.reviewId ? `https://github.com/${REPOSITORY}/pull/${e.number}#pullrequestreview-${e.reviewId}` : `https://github.com/${REPOSITORY}/issues/${e.issueNumber}`;
        const continuationBinding = e.reviewId && e.startHead !== e.request.reviewed_head_sha
          ? `Admitted source PR: https://github.com/${REPOSITORY}/pull/${e.number}\nAdmitted branch: ${e.branch}\nRequired starting head: ${e.startHead}\nOriginal CR reviewed head (finding provenance): ${e.request.reviewed_head_sha}\nUse the admitted starting head above; the original CR reviewed head remains finding provenance.\n` : '';
        const requestBinding = `\nStable Task charter SHA-256: ${e.request.charter_sha256}\nEffective authority SHA-256: ${e.authorityDigest}\nExecution admission SHA-256: ${admissionBinding(e.request).sha256}\n${continuationBinding}Selected trusted Decisions: ${e.request.authority.decisions.map(ref => `https://github.com/${REPOSITORY}/issues/${ref.parent.number}#issuecomment-${ref.id} (SHA-256 ${ref.sha256})`).join('; ') || 'none'}\nRead the stable Task charter and these exact selected trusted sources. Verify currentness; historical prose and ordinary comments grant no execution authority.\n`;
        const body = `MANUAL_CODEX_HANDOFF_READY\nThread: ${e.thread}\nAttempt: ${e.attemptId}\nModel: ${e.profile.cliModelId}; effort: ${e.profile.effort}\nSubagents: ${e.subagentsAllowed ? 'On' : 'Off'}\n\nCopyable prompt:\n\n\`\`\`text\nExecute the project-defined procedure for this canonical authority:\n${url}${requestBinding}\nThread: ${e.thread}\nCodex model: ${e.profile.cliModelId}\nCodex effort: ${e.profile.effort}\nSubagents: ${e.subagentsAllowed ? 'On' : 'Off'}\nFollow repository instructions and live authority. Commit and push safe task-owned work before handoff.\n\n${PROGRESS_BOUNDED_EXECUTION}\n\`\`\``;
        const outcomeBinding = {
          repository: REPOSITORY, task: e.issueNumber, run_id: e.runId,
          result: { schema_version: '4.0', kind: 'outcome', repository: REPOSITORY, task: e.issueNumber,
            parent: { kind: e.target === 'pull_request' ? 'pull_request' : 'issue', number: e.number },
            charter_sha256: e.request.charter_sha256, step: e.step, authority: e.request.authority,
            admission: admissionBinding(e.request), attempt: e.attemptId }
        };
        const handoff = renderManualHandoff(e, url, outcomeBinding);
        const comment = await commentOnce(r, 'handoff', e.number, handoff.body, { legacyBodies: [handoff.previousBody, body] });
        return receipt({ status: 'handed-off', commentId: comment.id });
      }
      if (request.operation === 'terminal-outcome') {
        if (e.route !== 'auto' || request.status !== 'blocked') fail('TERMINAL_OUTCOME_NOT_ADMITTED');
        const executionWarnings = request.executionWarnings ?? [];
        if (!Array.isArray(executionWarnings) || executionWarnings.length > 4
          || executionWarnings.some(code => !['UNCOMMITTED_WORK_REMAINS', 'WORKTREE_OBSERVATION_INCOMPLETE', 'RUNTIME_CLEANUP_FAILED', 'PRESENTATION_REPAIR_UNAVAILABLE'].includes(code))) fail('EXECUTION_WARNING_INVALID');
        return receipt(await terminalOutcome(r, { publishedHead: request.publishedHead ?? r.publishedHead,
          terminalCode: request.terminalCode, diagnostic: request.diagnostic, executionWarnings }));
      }
      if (request.operation === 'observe-readiness') {
        if (r.outcome?.status !== 'IMPLEMENTED_PENDING_FRESH_REVIEW' || !r.finalHead
          || request.head !== r.finalHead || r.publishedHead !== r.finalHead) fail('COMPLETED_PUBLICATION_REQUIRED');
        if (!r.outcome.readiness) fail('READINESS_OBSERVATION_UNAVAILABLE');
        const current = await existingPullRequest(r);
        if (!current || current.number !== r.outcome.prNumber) fail('PR_AUTHORITY_CHANGED');
        const { pr, readiness } = await observeReadiness(r, current);
        // Reconcile an accepted PATCH with a lost response/state receipt before
        // recording a new snapshot. PATCH is repeated only after a native GET
        // proves the old section is still present; publication is never retried.
        await reconcileReadinessOutcome(r);
        r.readinessIntent = { readiness, draft: pr.draft };
        await store.put(e.runId, r);
        await reconcileReadinessOutcome(r);
        return receipt(r.outcome);
      }
      if (request.operation === 'finish') {
        if (r.outcome && r.outcome.status !== 'BLOCKED') return receipt(r.outcome);
        if (!r.publishedHead || request.head !== r.publishedHead) fail('PUBLISHED_HEAD_REQUIRED');
        if (request.executionWarnings !== undefined && !Array.isArray(request.executionWarnings)) fail('EXECUTION_WARNING_INVALID');
        const executionWarnings = [...new Set([...(request.executionWarnings ?? []), ...(r.presentationWarnings ?? [])])];
        if (!Array.isArray(executionWarnings) || executionWarnings.length > 4
          || executionWarnings.some(value => !['UNCOMMITTED_WORK_REMAINS', 'WORKTREE_OBSERVATION_INCOMPLETE', 'RUNTIME_CLEANUP_FAILED', 'PRESENTATION_REPAIR_UNAVAILABLE'].includes(value))) fail('EXECUTION_WARNING_INVALID');
        if (r.outcome?.status === 'BLOCKED') {
          const recovery = r.publicationRecoveries?.find(value => value.authorizationId === request.recoveryAuthorizationId);
          if (r.publicationIntent || recovery?.result?.status !== 'PUBLISHED'
            || recovery.result.publishedHead !== r.publishedHead) fail('RECOVERED_OUTCOME_REQUIRED');
        }
        await pullRequest(r);
        if (await isCurrentProjection(e)) await guardPublication(e);
        const drafted = await isCurrentProjection(e)
          ? await transitionPr({ api, store, key: e.runId, record: r, head: r.publishedHead, draft: true,
            readPr: () => existingPullRequest(r) }) : await existingPullRequest(r);
        const { pr, readiness } = await observeReadiness(r, drafted);
        const warningSummary = [admissionWarningSummary(e.admission?.warnings ?? e.warnings),
          executionWarningSummary(executionWarnings)].filter(Boolean).join('; ');
        const body = await successfulOutcomeIntent(r, () => automaticOutcomeBody(e, `## Codex Outcome\n\nStatus: IMPLEMENTED_PENDING_FRESH_REVIEW\nThread: ${e.thread}\nCorrelation: ${threadCorrelationIdentity(e.thread)}\nAttempt: ${e.attemptId}\nRequested model: ${e.profile.cliModelId}; effort: ${e.profile.effort}\nActual model/effort: UNAVAILABLE\n${usageOutcomeSummary(request.codexUsage)}\nHistorical reviewed/starting head: ${e.startHead}\nLatest durable candidate head: ${r.publishedHead}\n${readinessOutcomeLines(readiness)}\nCompletion: ${warningSummary ? 'COMPLETED_WITH_WARNINGS' : 'COMPLETED'}${warningSummary ? `\nWarning summary: ${warningSummary}` : ''}\n\n`, `\n\nValidation: automatic worker reported bounded implementation and local validation success; Writer published and controller observed the exact PR head. Native candidate-head CI was not evaluated by automatic completion. Mergeability is a snapshot of the observed base; it does not establish independent acceptance or authorize base reconciliation.\nNative Ready means successful execution handoff only. Independent exact-head validation and review plus safe integration remain required before the authorized squash continuation.`, { pr, head: r.publishedHead, executionWarnings, authorityDrift: r.authorityDrift, taskResult: request.taskResult ?? {}, secrets }), r.publishedHead, pr.number, { readiness });
        const outcomeReadiness = r.successOutcomeIntent.readiness;
        let outcome;
        if (r.outcome?.status === 'BLOCKED') {
          const path = `/issues/comments/${r.outcome.outcomeId}`;
          const marker = `<!-- relay:${e.attemptId}:outcome -->`;
          const desired = `${body}\n\n${marker}`;
          outcome = await api.get(path);
          if (outcome.id !== r.outcome.outcomeId || outcome.user?.login !== WRITER || !outcome.body?.endsWith(marker)) fail('COMMENT_CONTENT_CHANGED');
          if (outcome.body !== desired) {
            if (!outcome.body.startsWith('## Codex Outcome\n\nStatus: BLOCKED\n')) fail('COMMENT_CONTENT_CHANGED');
            await api.patch(path, { body: secretFree(desired) });
            outcome = await api.get(path);
            if (outcome.body !== desired || outcome.user?.login !== WRITER) fail('COMMENT_CONTENT_CHANGED');
          }
        } else outcome = await commentOnce(r, 'outcome', pr.number, body);
        const expectedBody = outcome.body;
        outcome = await api.get(`/issues/comments/${outcome.id}`);
        if (outcome.body !== expectedBody || outcome.user?.login !== WRITER) fail('COMMENT_CONTENT_CHANGED');
        r.finalHead = r.publishedHead; r.handoffComplete = false; r.successOutcomeIntent = null;
        r.outcome = { status: 'IMPLEMENTED_PENDING_FRESH_REVIEW', head: r.finalHead, prNumber: pr.number, outcomeId: outcome.id,
          bodySha256: sha256Body(outcome.body), readiness: outcomeReadiness, draft: pr.draft,
          ...(executionWarnings.length ? { executionWarnings } : {}) };
        await store.put(e.runId, r);
        return receipt(r.outcome);
      }
      fail('BROKER_OPERATION_NOT_ALLOWED');
    }
}
