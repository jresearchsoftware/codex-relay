import { CONSUMER, CONSUMER_DIGEST } from '../../consumer/consumer.mjs';
import { PROGRESS_BOUNDED_EXECUTION } from '../../runtime/src/execution-policy.mjs';
import { REPOSITORY, VERSION, WRITER, exactSha, fail, positive, validateEnvelope } from './execution-contract.mjs';
import { admitEnvelope, revalidateReadyEvent, revalidateAuthority, revalidateIntegrationBase, assertPr, linkedIssue } from './live-authority.mjs';
import { secretFree } from './trusted-git.mjs';
import { failureDiagnosticFromDetails } from './diagnostics.mjs';
import { admissionWarningSummary, terminalOutcomeBody, workerOutcomeClaims } from './outcome.mjs';
import { boundedThreadCorrelationIdentity, threadCorrelationIdentity } from './run-name.mjs';
import { recoverPublication, recoveryAuthorization, recoveryAuthorizationBody } from './publication-recovery.mjs';
import { assertStep, labelNames, stepLike } from './step-metadata.mjs';

// Caller serializes this broker across processes. Store contains only immutable
// admission and mutation intents/receipts, never child, retry or lifecycle state.
export function createPublicationBroker({ api, store, publisher }) {
  const receipt = value => ({ version: VERSION, repository: REPOSITORY, ...value });
  async function mirrorStep(r, pr) {
    const e = r.envelope;
    assertStep((await api.get(`/issues/${e.issueNumber}`)).labels, e.step);
    const labels = (await api.get(`/issues/${pr.number}`)).labels;
    // Creation/recovery may finish a missing mirror, but never overwrite a
    // conflicting Step. The Issue remains the durable anchor.
    if (labelNames(labels).some(stepLike)) assertStep(labels, e.step);
    else {
      if (e.target !== 'issue') fail('STEP_LABEL_MISSING');
      await api.post(`/issues/${pr.number}/labels`, { labels: [`step-${e.step}`] });
    }
    assertStep((await api.get(`/issues/${pr.number}`)).labels, e.step);
    return pr;
  }
  function publicationFailure(code, { cause, diagnostic = {} } = {}) {
    const source = {
      ...(cause?.details ?? {}),
      failureDiagnostic: { ...(cause?.details?.failureDiagnostic ?? {}), ...diagnostic }
    };
    const failureDiagnostic = failureDiagnosticFromDetails(source, {
      fallbackCode: code, fallbackStage: 'writer-publication', fallbackBoundary: 'writer-publication'
    });
    const error = new Error(code); error.code = code; error.details = { failureDiagnostic }; throw error;
  }
  async function bound(request, { revalidate = true, allowAdmissionBlock = false } = {}) {
    if (!positive(request.runId)) fail('RUN_ID_INVALID');
    const record = await store.get(request.runId);
    if (!record || request.attemptId !== record.envelope.attemptId) fail('ATTEMPT_NOT_ADMITTED');
    if (record.envelope.consumerDigest !== CONSUMER_DIGEST) fail('CONSUMER_CONFIG_CHANGED');
    if (record.admissionBlock) {
      if (!allowAdmissionBlock) fail('ADMISSION_ALREADY_BLOCKED');
      return record;
    }
    validateEnvelope(record.envelope);
    if (revalidate) await revalidateAuthority(api, record.envelope);
    return record;
  }
  async function commentOnce(r, key, number, body) {
    secretFree(body);
    const marker = `<!-- relay:${r.envelope.attemptId}:${key} -->`;
    const matches = (await api.list(`/issues/${number}/comments`)).filter(c => c.user?.login === WRITER && c.body?.includes(marker));
    if (matches.length > 1) fail('COMMENT_AMBIGUOUS');
    if (matches.length === 1) {
      if (matches[0].body !== `${body}\n\n${marker}`) fail('COMMENT_CONTENT_CHANGED');
      return matches[0];
    }
    // An ambiguous POST must never be blindly repeated after a failed GET.
    if (r.commentIntent?.key === key) fail('COMMENT_PUBLICATION_UNCERTAIN');
    r.commentIntent = { key, number }; await store.put(r.envelope.runId, r);
    const comment = await api.post(`/issues/${number}/comments`, { body: `${body}\n\n${marker}` });
    r.commentIntent = null; await store.put(r.envelope.runId, r);
    return comment;
  }
  async function pullRequest(r) {
    const e = r.envelope;
    if (e.target === 'pull_request') {
      const pr = await api.get(`/pulls/${e.number}`); assertPr(pr, e.number); return mirrorStep(r, pr);
    }
    const matches = await api.list(`/pulls?state=all&head=${CONSUMER.repository.split('/')[0]}:${encodeURIComponent(e.branch)}&base=${encodeURIComponent(CONSUMER.baseBranch)}`);
    if (matches.length > 1) fail('PR_AMBIGUOUS');
    if (matches.length === 1) {
      const pr = matches[0]; assertPr(pr, pr.number);
      if (pr.head.ref !== e.branch || linkedIssue(pr.body) !== e.issueNumber) fail('PR_AUTHORITY_CHANGED');
      return mirrorStep(r, pr);
    }
    if (r.prIntent) fail('PR_PUBLICATION_UNCERTAIN');
    r.prIntent = true; await store.put(e.runId, r);
    const pr = await api.post('/pulls', { title: secretFree(boundedThreadCorrelationIdentity(e.thread)), head: e.branch, base: CONSUMER.baseBranch, draft: true,
      body: `Implementation of https://github.com/${REPOSITORY}/issues/${e.issueNumber}\n\nThread: ${e.thread}\nCorrelation: ${threadCorrelationIdentity(e.thread)}\nAttempt: ${e.attemptId}\nRequested model: ${e.profile.cliModelId}; effort: ${e.profile.effort}\nStarting head: ${e.startHead}\n\n${e.closure}` });
    assertPr(pr, pr.number); return mirrorStep(r, pr);
  }
  async function existingPullRequest(r) {
    const e = r.envelope;
    if (e.target === 'pull_request') {
      const pr = await api.get(`/pulls/${e.number}`); assertPr(pr, e.number); return pr;
    }
    const matches = await api.list(`/pulls?state=all&head=${CONSUMER.repository.split('/')[0]}:${encodeURIComponent(e.branch)}&base=${encodeURIComponent(CONSUMER.baseBranch)}`);
    if (matches.length > 1) fail('PR_AMBIGUOUS');
    if (matches.length === 0) return null;
    const pr = matches[0]; assertPr(pr, pr.number);
    if (pr.head.ref !== e.branch || linkedIssue(pr.body) !== e.issueNumber) fail('PR_AUTHORITY_CHANGED');
    return pr;
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
    return { observed: { child: 'not_started', exitCode: null }, executionState: 'known-not-executed', executionId: null,
      lastSuccessfulBoundary: 'admission', failureBoundary: 'authority', classification: { code: block.code, source: 'observed', stage: 'authority' },
      primaryCause: block.code, containment: 'not_required', terminal: 'blocked', durable: { publishedHead: null, diagnosticStore: null },
      nextAction: 'correct-authority-before-new-owner-attempt', orchestration: 'COMPLETED' };
  }

  async function terminalOutcome(r, { terminalCode, diagnostic, publishedHead } = {}) {
    if (r.outcome) return r.outcome;
    const e = r.envelope;
    let pr = null;
    if (!r.admissionBlock) {
      // Do not hide an unknown PR/readiness state behind an Issue fallback.
      pr = await existingPullRequest(r);
      if (pr && !pr.draft) {
        await api.draft(pr.node_id);
        pr = await api.get(`/pulls/${pr.number}`);
        assertPr(pr, pr.number);
        if (!pr.draft) fail('DRAFT_OBSERVATION_CHANGED');
      }
    }
    const number = e.target === 'pull_request' ? e.number : pr?.number ?? e.issueNumber;
    const body = terminalOutcomeBody(e, { publishedHead: publishedHead ?? r.publishedHead, pr, terminalCode, diagnostic });
    const outcome = await commentOnce(r, 'outcome', number, body);
    r.outcome = { status: 'BLOCKED', head: exactSha(publishedHead ?? r.publishedHead) ? (publishedHead ?? r.publishedHead) : null,
      prNumber: pr?.number ?? null, outcomeId: outcome.id };
    await store.put(e.runId, r);
    return r.outcome;
  }

  return {
    async dispatch(request) {
      if (!request || !positive(request.runId)) fail('BROKER_REQUEST_INVALID');
      if (request.operation === 'admit') {
        const existing = await store.get(request.runId);
        if (existing && existing.envelope.consumerDigest !== CONSUMER_DIGEST) fail('CONSUMER_CONFIG_CHANGED');
        if (existing) {
          const e = existing.envelope;
          if (e.target !== request.target || e.number !== request.number || e.route !== request.route
            || e.step !== request.step || (e.transport !== 'label' && e.issueNumber !== request.issueNumber)
            || e.transport !== request.transport) fail('RUN_BINDING_CHANGED');
          if (e.transport === 'label' && !existing.readyConsumed) fail('READY_CONSUMPTION_UNCERTAIN');
          if (existing.admissionBlock) {
            if (!existing.outcome) await terminalOutcome(existing, { terminalCode: existing.admissionBlock.code, diagnostic: admissionBlockDiagnostic(existing.admissionBlock) });
            return receipt({ envelope: e, resumed: true, status: 'BLOCKED', outcome: existing.outcome });
          }
          // The attempt's preflight revalidates live authority inside its
          // terminal boundary; admission replay must not bypass that path.
          return receipt({ envelope: e, resumed: true });
        }
        const admitted = await admitEnvelope(api, request);
        const envelope = admitted.blocked ? blockedAdmissionEnvelope(admitted) : validateEnvelope(admitted);
        // Reserve the native event in the existing attempt record, under the
        // Writer lock. This is replay protection, never a Step ledger.
        if (envelope.transport === 'label') {
          for (const previous of await store.all()) {
            const prior = previous.envelope;
            if (prior.readyEventId === envelope.readyEventId) fail('READY_EVENT_ALREADY_CONSUMED');
            if (!(prior.target === envelope.target && prior.number === envelope.number)
              && !(positive(envelope.issueNumber) && prior.issueNumber === envelope.issueNumber)) continue;
            const run = await api.getRun(prior.runId);
            if (run.status !== 'completed' || !Number.isFinite(Date.parse(run.updated_at))
              || Date.parse(envelope.readyEventAt) <= Date.parse(run.updated_at)) fail('READY_EVENT_QUEUED');
          }
          await revalidateReadyEvent(api, envelope);
        }
        const r = { envelope, ...(admitted.blocked ? { admissionBlock: admitted.block } : {}),
          publicationIntent: null, publishedHead: null, finalHead: null, outcome: null };
        await store.put(request.runId, r);
        if (envelope.transport === 'label') {
          await api.delete(`/issues/${envelope.number}/labels/${envelope.readyLabel}`);
          if (labelNames((await api.get(`/issues/${envelope.number}`)).labels).includes(envelope.readyLabel)) fail('READY_CONSUMPTION_UNCERTAIN');
          r.readyConsumed = true; await store.put(request.runId, r);
        }
        if (admitted.blocked) {
          await terminalOutcome(r, { terminalCode: admitted.block.code, diagnostic: admissionBlockDiagnostic(admitted.block) });
          return receipt({ envelope, status: 'BLOCKED', outcome: r.outcome });
        }
        return receipt({ envelope });
      }
      const r = await bound(request, request.operation === 'terminal-outcome' ? { revalidate: false, allowAdmissionBlock: true }
        : ['publication-state', 'recover-publication'].includes(request.operation) ? { revalidate: false } : {}); const e = r.envelope;
      if (request.operation === 'publication-state') {
        return receipt({ envelope: e, publicationIntent: r.publicationIntent, publishedHead: r.publishedHead,
          recovery: r.publicationRecoveries?.find(value => value.authorizationId === request.authorizationId) ?? null,
          authorizationBody: r.publicationIntent ? recoveryAuthorizationBody(recoveryAuthorization(e, r.publicationIntent,
            r.publicationRecoveries?.at(-1)?.authorizationId ?? null)) : null });
      }
      if (request.operation === 'recover-publication') {
        return receipt(await recoverPublication({ api, store, publisher, record: r, request }));
      }
      if (request.operation === 'preflight') {
        const a = await revalidateAuthority(api, e);
        if (a.pr && a.pr.head.sha !== (r.publishedHead ?? e.startHead)) fail('REMOTE_HEAD_CHANGED');
        // A reviewed dirty PR is the resolver's input. Bind the observed main,
        // then let trusted checkout/publication validate its Git ancestry.
        if (a.pr) await revalidateIntegrationBase(api, e);
        if (a.pr && !r.finalHead) {
          const title = secretFree(boundedThreadCorrelationIdentity(e.thread));
          if (a.pr.title !== title) await api.patch(`/pulls/${a.pr.number}`, { title });
        }
        if (a.pr && !a.pr.draft && !r.finalHead) {
          await api.draft(a.pr.node_id);
          const after = await api.get(`/pulls/${a.pr.number}`);
          assertPr(after, a.pr.number);
          if (!after.draft || after.head.sha !== a.pr.head.sha) fail('DRAFT_OBSERVATION_CHANGED');
        }
        return receipt({ envelope: e, publishedHead: r.publishedHead, finalHead: r.finalHead });
      }
      if (request.operation === 'publish-progress') {
        if (e.route !== 'auto' || r.finalHead) fail('PROGRESS_NOT_ADMITTED');
        return publisher.inspect(e, request.bundle, async g => {
          const previous = r.publishedHead ?? (e.target === 'pull_request' ? e.startHead : null);
          if (r.publicationIntent && r.publicationIntent.head !== g.head) fail('PUBLICATION_RECONCILIATION_REQUIRED');
          if (g.remoteHead === g.head) {
            if (!r.publicationIntent && r.publishedHead !== g.head) fail('UNATTRIBUTED_REMOTE_HEAD');
          } else {
            if (r.publicationIntent) fail('PUBLICATION_UNCERTAIN');
            if (g.remoteHead !== previous || !(await g.ancestor(e.startHead, g.head))
              || (previous && !(await g.ancestor(previous, g.head)))) fail('REMOTE_HEAD_CHANGED');
            if (!g.commits.length) fail('NO_PROGRESS');
            await revalidateAuthority(api, e);
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
          const pr = await pullRequest(r);
          // A lagging PR API cannot erase a successful Git ref observation.
          return receipt({ publishedHead: g.head, prNumber: pr.number, prObservedHead: pr.head.sha, ready: false });
        });
      }
      if (request.operation === 'handoff') {
        if (e.route !== 'manual') fail('MANUAL_ROUTE_REQUIRED');
        const url = e.reviewId ? `https://github.com/${REPOSITORY}/pull/${e.number}#pullrequestreview-${e.reviewId}` : `https://github.com/${REPOSITORY}/issues/${e.issueNumber}`;
        const body = `MANUAL_CODEX_HANDOFF_READY\nThread: ${e.thread}\nAttempt: ${e.attemptId}\nModel: ${e.profile.cliModelId}; effort: ${e.profile.effort}\n\nCopyable prompt:\n\n\`\`\`text\nExecute the project-defined procedure for this canonical authority:\n${url}\nThread: ${e.thread}\nFollow repository instructions and live authority. Commit and push safe task-owned work before handoff.\n\n${PROGRESS_BOUNDED_EXECUTION}\n\`\`\``;
        const comment = await commentOnce(r, 'handoff', e.number, body);
        return receipt({ status: 'handed-off', commentId: comment.id });
      }
      if (request.operation === 'terminal-outcome') {
        if (e.route !== 'auto' || request.status !== 'blocked') fail('TERMINAL_OUTCOME_NOT_ADMITTED');
        return receipt(await terminalOutcome(r, { publishedHead: request.publishedHead ?? r.publishedHead,
          terminalCode: request.terminalCode, diagnostic: request.diagnostic }));
      }
      if (request.operation === 'finish') {
        if (r.outcome && r.outcome.status !== 'BLOCKED') return receipt(r.outcome);
        if (!r.publishedHead || request.head !== r.publishedHead) fail('PUBLISHED_HEAD_REQUIRED');
        if (r.outcome?.status === 'BLOCKED') {
          const recovery = r.publicationRecoveries?.find(value => value.authorizationId === request.recoveryAuthorizationId);
          if (r.publicationIntent || recovery?.result?.status !== 'PUBLISHED'
            || recovery.result.publishedHead !== r.publishedHead) fail('RECOVERED_OUTCOME_REQUIRED');
        }
        const pr = await pullRequest(r);
        if (pr.head.sha !== r.publishedHead) fail('PR_HEAD_OBSERVATION_STALE');
        const warningSummary = admissionWarningSummary(e.admission?.warnings ?? e.warnings);
        const body = `## Codex Outcome\n\nStatus: IMPLEMENTED_PENDING_FRESH_REVIEW\nThread: ${e.thread}\nCorrelation: ${threadCorrelationIdentity(e.thread)}\nAttempt: ${e.attemptId}\nRequested model: ${e.profile.cliModelId}; effort: ${e.profile.effort}\nActual model/effort: UNAVAILABLE\nHistorical reviewed/starting head: ${e.startHead}\nLatest durable and ready head: ${r.publishedHead}\nObserved integration base: ${pr.base.sha}\nCompletion: ${warningSummary ? 'COMPLETED_WITH_WARNINGS' : 'COMPLETED'}${warningSummary ? `\nWarning summary: ${warningSummary}` : ''}\n\n${workerOutcomeClaims(request.taskResult)}\n\nValidation: automatic worker reported bounded implementation and local validation success; Writer published and controller observed the exact PR head. Native exact-head CI and GitHub mergeability were not evaluated by automatic completion.\nIndependent exact-head validation and review, integration/mergeability, and human merge remain required.`;
        if (pr.draft) await api.ready(pr.node_id);
        const after = await api.get(`/pulls/${pr.number}`);
        assertPr(after, pr.number);
        if (after.draft || after.head.sha !== r.publishedHead) fail('READY_OBSERVATION_CHANGED');
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
        r.finalHead = r.publishedHead;
        r.outcome = { status: 'IMPLEMENTED_PENDING_FRESH_REVIEW', head: r.finalHead, prNumber: pr.number, outcomeId: outcome.id };
        await store.put(e.runId, r);
        return receipt({ status: 'IMPLEMENTED_PENDING_FRESH_REVIEW', head: r.finalHead, prNumber: pr.number, outcomeId: outcome.id });
      }
      fail('BROKER_OPERATION_NOT_ALLOWED');
    }
  };
}
