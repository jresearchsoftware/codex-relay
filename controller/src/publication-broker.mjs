import { CONSUMER, CONSUMER_DIGEST } from '../../consumer/consumer.mjs';
import { PROGRESS_BOUNDED_EXECUTION } from '../../runtime/src/execution-policy.mjs';
import { REPOSITORY, VERSION, WRITER, OWNER, digest, exactSha, fail, positive, validateEnvelope } from './execution-contract.mjs';
import { canonicalAuthorityJson, validateAuthorityRecord, renderAuthorityRecord, sha256Body } from '../../contracts/src/github-authority.mjs';
import { admitEnvelope, revalidateReadyEvent, revalidateAuthority, revalidateIntegrationBase, assertPr, linkedIssue } from './live-authority.mjs';
import { secretFree } from './trusted-git.mjs';
import { failureDiagnosticFromDetails } from './diagnostics.mjs';
import { admissionWarningSummary, executionWarningSummary, terminalOutcomeBody, workerOutcomeClaims, usageOutcomeSummary, boundOutcomeBody } from './outcome.mjs';
import { boundedThreadCorrelationIdentity, threadCorrelationIdentity } from './run-name.mjs';
import { recoverPublication, recoveryAuthorization, recoveryAuthorizationBody } from './publication-recovery.mjs';
import { assertStep, assertPrStepTitle, projectedRequestTitle, labelNames, stepLike } from './step-metadata.mjs';
import { findCurrentIssuePullRequest } from './publication-target.mjs';
import { prReadiness, readinessOutcomeLines } from './pr-readiness.mjs';
import { nonClosingTaskBody } from './task-relationship.mjs';
import { transitionPr, beginRemediation } from './pr-lifecycle.mjs';

// Caller serializes this broker across processes. Store contains immutable
// admission, trusted controller reservation/completion and mutation receipts.
// Runtime observations remain in the separate protected runner journal.
export function createPublicationBroker({ api, store, publisher, admission, journal, lifecycleStore }) {
  const receipt = value => ({ version: VERSION, repository: REPOSITORY, ...value });
  // The typed publisher projects the exact Request purpose, bounded by Unicode
  // characters. Do not normalize it through the legacy prose-title parser.
  const titleFor = e => secretFree(e.request
    ? projectedRequestTitle(e.request)
    : boundedThreadCorrelationIdentity(e.thread));
  async function prepareRemediation(e) {
    if (e.target !== 'pull_request') return;
    if (!lifecycleStore) fail('PR_LIFECYCLE_STORE_REQUIRED');
    // The current native CR supplies the same exact action as Reviewer
    // pr_lifecycle. Consume it before reserving a worker or emitting a handoff,
    // even when the owner launches through the ordinary routing entrypoint.
    await beginRemediation({ api, store: lifecycleStore, authorityDigest: e.authorityDigest,
      request: { operation: 'begin-remediation', prNumber: e.number, reviewId: e.reviewId, head: e.startHead } });
  }
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
      if (r.commentIntent?.key === key && r.commentIntent.number === number) {
        r.commentIntent = null; await store.put(r.envelope.runId, r);
      }
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
    const existing = await existingPullRequest(r, { allowStepMirror: true });
    if (existing) return mirrorStep(r, existing);
    if (r.prIntent) fail('PR_PUBLICATION_UNCERTAIN');
    r.prIntent = true; await store.put(e.runId, r);
    const pr = await api.post('/pulls', { title: titleFor(e), head: e.branch, base: CONSUMER.baseBranch, draft: true,
      body: `Implementation of https://github.com/${REPOSITORY}/issues/${e.issueNumber}\n\nThread: ${e.thread}\nCorrelation: ${threadCorrelationIdentity(e.thread)}\nAttempt: ${e.attemptId}\n${e.requestReference ? `Execution request native ID: ${e.requestReference.id}\nExecution request digest: ${e.requestReference.sha256}\n` : ''}Requested model: ${e.profile.cliModelId}; effort: ${e.profile.effort}\nStarting head: ${e.startHead}\n\n${e.closure}` });
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
      await api.patch(`/pulls/${pr.number}`, { body: secretFree(body) });
      const after = await api.get(`/pulls/${pr.number}`);
      assertPr(after, pr.number);
      if (after.head.sha !== pr.head.sha || after.body !== body
        || linkedIssue(after.body) !== r.envelope.issueNumber) fail('PR_AUTHORITY_CHANGED');
      pr = after;
    }
    if (r.relationshipIntent) { r.relationshipIntent = null; await store.put(r.envelope.runId, r); }
    return pr;
  }
  async function existingPullRequest(r, { allowStepMirror = false } = {}) {
    const e = r.envelope;
    if (e.target === 'pull_request') {
      const pr = await api.get(`/pulls/${e.number}`); assertPr(pr, e.number); return pr;
    }
    const pr = await findCurrentIssuePullRequest(api, e, r.prNumber ?? e.continuation?.pullRequest);
    if (!pr && r.prIntent) fail('PR_PUBLICATION_UNCERTAIN');
    if (e.continuation && !e.continuation.pullRequest && !r.publishedHead && pr) fail('PR_AUTHORITY_CHANGED');
    if (e.continuation && pr) {
      // Only our own newly created PR can finish a missing Step mirror.
      // Every observed conflicting Step/title must stop before another push.
      if (!allowStepMirror || e.continuation.pullRequest || labelNames(pr.labels).some(stepLike)) assertStep(pr.labels, e.step);
      assertPrStepTitle(pr, e.issueNumber, e.step);
    }
    if (pr) {
      // An uncertain POST has no number receipt yet. Reconcile its own native
      // attempt binding, not a different compatible PR created in the meantime.
      if (r.prIntent && !r.prNumber && !String(pr.body).split(/\r?\n/).includes(`Attempt: ${e.attemptId}`)) fail('PR_PUBLICATION_UNCERTAIN');
      await rememberPullRequest(r, pr);
      if (e.request && pr.title !== projectedRequestTitle(e.request)) fail('AUTHORITY_TITLE_PROJECTION_MISMATCH');
    }
    return pr;
  }

  async function observeReadiness(r, pr) {
    return { pr, readiness: prReadiness(pr, r.publishedHead) };
  }

  async function successfulOutcomeIntent(r, body, head, prNumber, metadata = {}) {
    if (r.successOutcomeIntent) {
      if (r.successOutcomeIntent.head !== head || r.successOutcomeIntent.prNumber !== prNumber) fail('OUTCOME_BINDING_CHANGED');
      return r.successOutcomeIntent.body;
    }
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
    return { observed: { child: 'not_started', exitCode: null }, executionState: 'known-not-executed', executionId: null,
      lastSuccessfulBoundary: 'admission', failureBoundary: 'authority', classification: { code: block.code, source: 'observed', stage: 'authority' },
      primaryCause: block.code, containment: 'not_required', terminal: 'blocked', durable: { publishedHead: null, diagnosticStore: null },
      nextAction: 'correct-authority-before-new-owner-attempt', orchestration: 'COMPLETED' };
  }

  async function terminalOutcome(r, { terminalCode, diagnostic, publishedHead } = {}) {
    if (r.outcome) return r.outcome;
    if (r.successOutcomeIntent) fail('SUCCESS_OUTCOME_PUBLICATION_UNCERTAIN');
    const e = r.envelope;
    let pr = null;
    if (!r.admissionBlock) {
      // Do not hide an unknown PR/readiness state behind an Issue fallback.
      pr = await existingPullRequest(r);
      if (pr) pr = await transitionPr({ api, store, key: e.runId, record: r, head: pr.head.sha, draft: true,
        readPr: () => existingPullRequest(r) });
    }
    const number = e.target === 'pull_request' ? e.number : pr?.number ?? e.issueNumber;
    const body = boundOutcomeBody(e, terminalOutcomeBody(e, { publishedHead: publishedHead ?? r.publishedHead, pr, terminalCode, diagnostic }),
      { pr, status: 'blocked', head: publishedHead ?? r.publishedHead });
    const outcome = await commentOnce(r, 'outcome', number, body);
    r.outcome = { status: 'BLOCKED', head: exactSha(publishedHead ?? r.publishedHead) ? (publishedHead ?? r.publishedHead) : null,
      prNumber: pr?.number ?? null, outcomeId: outcome.id };
    await store.put(e.runId, r);
    return r.outcome;
  }

  return {
    async dispatch(request) {
      if (request?.operation === 'begin-remediation') {
        if (!lifecycleStore) fail('PR_LIFECYCLE_STORE_REQUIRED');
        return receipt(await beginRemediation({ api, store: lifecycleStore, request }));
      }
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
        // Installed helpers hold the same root lock as lifecycle quiesce.
        // Reserve full controller ownership in this existing attempt before
        // the ready event is consumed or a child can be launched.
        if (request.route === 'auto') await admission?.assertOpen();
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
        }
        // Keep lifecycle failure before execution reservation and ready-command
        // consumption. The same CR/head can reconcile its pending Draft intent
        // without creating an unknown execution or publishing another review.
        if (!admitted.blocked) await prepareRemediation(envelope);
        if (envelope.transport === 'label') await revalidateReadyEvent(api, envelope);
        const r = { envelope, ...(admitted.blocked ? { admissionBlock: admitted.block } : {}),
          ...(!admitted.blocked && envelope.route === 'auto' && admission ? { controllerLifecycle: await admission.reserve() } : {}),
          ...(envelope.continuation?.pullRequest ? { prNumber: envelope.continuation.pullRequest } : {}),
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
        : ['publication-state', 'recover-publication', 'complete-handoff'].includes(request.operation) ? { revalidate: false } : {}); const e = r.envelope;
      if (request.operation === 'publication-state') {
        return receipt({ envelope: e, publicationIntent: r.publicationIntent, publishedHead: r.publishedHead,
          recovery: r.publicationRecoveries?.find(value => value.authorizationId === request.authorizationId) ?? null,
          authorizationBody: r.publicationIntent ? recoveryAuthorizationBody(recoveryAuthorization(e, r.publicationIntent,
            r.publicationRecoveries?.at(-1)?.authorizationId ?? null)) : null });
      }
      if (request.operation === 'recover-publication') {
        return receipt(await recoverPublication({ api, store, publisher, record: r, request }));
      }
      if (request.operation === 'complete-handoff') {
        if (r.handoffComplete) return receipt(r.outcome);
        const saved = await journal?.get(e.runId);
        if (e.route !== 'auto' || !saved || digest(saved.envelope) !== digest(e)
          || saved.version !== VERSION || saved.diagnostic
          || saved.execution?.reserved !== true || saved.execution.returned !== true
          || saved.execution.child !== 'started' || saved.execution.containment !== 'reaped'
          || saved.execution.result?.status !== 'success'
          || typeof saved.collection?.clean !== 'boolean' || saved.collection.head !== r.finalHead
          || r.outcome?.status !== 'IMPLEMENTED_PENDING_FRESH_REVIEW'
          || !['status', 'head', 'prNumber', 'outcomeId'].every(key => saved.outcome?.[key] === r.outcome[key])
          || r.publicationIntent || r.commentIntent) fail('EXECUTION_HANDOFF_NOT_PROVEN');
        // Full controller completion is recorded from the protected journal,
        // before any Ready mutation. No caller claims can replace this proof.
        await admission?.complete({ runId: e.runId, attemptId: e.attemptId });
        // admission.complete may have updated the same protected record.
        const completed = await store.get(e.runId);
        Object.assign(r, completed);
        if (!r.outcome.prNumber) {
          r.handoffComplete = true; await store.put(e.runId, r); return receipt(r.outcome);
        }
        const outcome = await api.get(`/issues/comments/${r.outcome.outcomeId}`);
        if (outcome.user?.login !== WRITER || !outcome.body?.endsWith(`<!-- relay:${e.attemptId}:outcome -->`)
          || !outcome.body.startsWith('## Codex Outcome\n\nStatus: IMPLEMENTED_PENDING_FRESH_REVIEW\n')
          || sha256Body(outcome.body) !== r.outcome.bodySha256) fail('COMMENT_CONTENT_CHANGED');
        const pr = await transitionPr({ api, store, key: e.runId, record: r, head: r.finalHead, draft: false,
          readPr: async () => {
            await revalidateAuthority(api, e);
            const current = await existingPullRequest(r);
            if (!current || current.number !== r.outcome.prNumber) fail('PR_AUTHORITY_CHANGED');
            return current;
          } });
        r.outcome.draft = pr.draft; r.handoffComplete = true;
        await store.put(e.runId, r);
        return receipt(r.outcome);
      }
      if (request.operation === 'preflight') {
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
        if (a.pr && !r.finalHead) a.pr = await projectTaskRelationship(r, a.pr);
        if (a.pr && !r.finalHead) {
          const title = titleFor(e);
          if (a.pr.title !== title) await api.patch(`/pulls/${a.pr.number}`, { title });
        }
        if (a.pr && !a.pr.draft && !r.finalHead) {
          await transitionPr({ api, store, key: e.runId, record: r, head: a.pr.head.sha, draft: true,
            readPr: () => existingPullRequest(r) });
        }
        return receipt({ envelope: e, publishedHead: r.publishedHead, finalHead: r.finalHead,
          ...(r.finalHead ? { outcome: receipt(r.outcome) } : {}) });
      }
      if (request.operation === 'publish-progress') {
        if (e.route !== 'auto' || r.finalHead) fail('PROGRESS_NOT_ADMITTED');
        return publisher.inspect(e, request.bundle, async g => {
          const previous = r.publishedHead ?? (e.target === 'pull_request' || e.continuation ? e.startHead : null);
          if (r.publicationIntent && r.publicationIntent.head !== g.head) fail('PUBLICATION_RECONCILIATION_REQUIRED');
          if (g.remoteHead === g.head) {
            if (!r.publicationIntent && r.publishedHead !== g.head) fail('UNATTRIBUTED_REMOTE_HEAD');
          } else {
            if (r.publicationIntent) fail('PUBLICATION_UNCERTAIN');
            if (g.remoteHead !== previous || !(await g.ancestor(e.startHead, g.head))
              || (previous && !(await g.ancestor(previous, g.head)))) fail('REMOTE_HEAD_CHANGED');
            if (!g.commits.length) fail('NO_PROGRESS');
            await revalidateAuthority(api, e);
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
          const pr = await pullRequest(r);
          // A lagging PR API cannot erase a successful Git ref observation.
          return receipt({ publishedHead: g.head, prNumber: pr.number, prObservedHead: pr.head.sha, ready: false });
        });
      }
      if (request.operation === 'manual-outcome') {
        // This publishes an owner-authored manual result, never Git objects,
        // execution, approval, merge, deployment or closure. A native owner
        // transport authorization is evidence, not a new execution request.
        if (e.route !== 'manual' || e.request?.kind !== 'task-request' || !positive(request.authorizationId)) fail('MANUAL_OUTCOME_NOT_ADMITTED');
        const source = await api.get(`/issues/comments/${request.authorizationId}`);
        const owner = await api.userIdentity(OWNER);
        if (source.id !== request.authorizationId || owner.login !== OWNER || owner.type !== 'User' || !positive(owner.id)
          || source.user?.login !== OWNER || source.user?.id !== owner.id || source.user?.type !== 'User'
          || source.issue_url !== `https://api.github.com/repos/${REPOSITORY}/issues/${e.issueNumber}`) fail('MANUAL_OUTCOME_AUTHORIZATION_INVALID');
        const match = /^```relay-manual-result\n([\s\S]*?)\n```\n?$/.exec(source.body ?? '');
        if (!match) fail('MANUAL_OUTCOME_AUTHORIZATION_INVALID');
        let result; try { result = JSON.parse(match[1]); } catch { fail('MANUAL_OUTCOME_AUTHORIZATION_INVALID'); }
        if (canonicalAuthorityJson(result) !== match[1]) fail('MANUAL_OUTCOME_AUTHORIZATION_INVALID');
        validateAuthorityRecord(result, { repository: REPOSITORY, task: e.issueNumber, charterBody: (await api.get(`/issues/${e.issueNumber}`)).body });
        if (result.kind !== 'outcome' || result.attempt !== e.attemptId
          || canonicalAuthorityJson(result.request) !== canonicalAuthorityJson(e.requestReference)) fail('MANUAL_OUTCOME_AUTHORIZATION_INVALID');
        if (r.manualResultAuthorization && (r.manualResultAuthorization.id !== source.id
          || r.manualResultAuthorization.sha256 !== sha256Body(source.body))) fail('MANUAL_OUTCOME_AUTHORIZATION_CHANGED');
        let pr = null;
        if (result.parent.kind === 'pull_request') {
          pr = await api.get(`/pulls/${result.parent.number}`);
          if (pr.number !== result.parent.number || pr.base?.repo?.full_name !== REPOSITORY || pr.head?.repo?.full_name !== REPOSITORY
            || linkedIssue(pr.body) !== e.issueNumber || (e.branch && pr.head.ref !== e.branch)
            || (result.result.kind === 'git' && result.result.revision !== pr.head.sha)
            || !pr.body?.split(/\r?\n/).includes(`Execution request digest: ${e.requestReference.sha256}`)) fail('PR_AUTHORITY_CHANGED');
          const artifacts = (await api.list(`/pulls?state=all&head=${REPOSITORY.split('/')[0]}:${encodeURIComponent(pr.head.ref)}`))
            .filter(candidate => candidate.body?.split(/\r?\n/).includes(`Execution request digest: ${e.requestReference.sha256}`));
          if (artifacts.length !== 1 || artifacts[0].number !== pr.number) fail('PR_AMBIGUOUS');
          await rememberPullRequest(r, pr);
        } else if (result.parent.number !== e.issueNumber || r.prNumber || r.prIntent || (e.branch && await existingPullRequest(r))) fail('PR_AUTHORITY_CHANGED');
        r.manualResultAuthorization = { id: source.id, sha256: sha256Body(source.body) }; await store.put(e.runId, r);
        const after = await api.get(`/issues/comments/${source.id}`);
        if (sha256Body(after.body) !== r.manualResultAuthorization.sha256 || after.user?.id !== owner.id) fail('MANUAL_OUTCOME_AUTHORIZATION_CHANGED');
        const transitionManual = async draft => {
          if (!pr || pr.state !== 'open' || pr.merged) return;
          if (!draft && (result.result.kind !== 'git' || result.result.revision !== pr.head.sha)) fail('PUBLISHED_HEAD_REQUIRED');
          pr = await transitionPr({ api, store, key: e.runId, record: r, head: pr.head.sha, draft,
            readPr: async () => {
              await revalidateAuthority(api, e);
              const current = await api.get(`/pulls/${pr.number}`); assertPr(current, pr.number);
              if (current.head.ref !== pr.head.ref || linkedIssue(current.body) !== e.issueNumber
                || !current.body?.split(/\r?\n/).includes(`Execution request digest: ${e.requestReference.sha256}`)) fail('PR_AUTHORITY_CHANGED');
              return current;
            } });
        };
        if (result.status !== 'implemented') await transitionManual(true);
        if (r.outcome) {
          if (result.status === 'implemented') {
            const durable = await api.get(`/issues/comments/${r.outcome.outcomeId}`);
            if (durable.user?.login !== WRITER || sha256Body(durable.body) !== r.outcome.bodySha256) fail('COMMENT_CONTENT_CHANGED');
            await transitionManual(false);
          }
          return receipt(r.outcome);
        }
        const body = `## Codex Outcome\n\nStatus: ${result.status === 'implemented' ? 'IMPLEMENTED_PENDING_FRESH_REVIEW' : 'BLOCKED'}\nAttempt: ${e.attemptId}\nManual result source: #${source.id}\n\n${renderAuthorityRecord(result)}`;
        let outcome = await commentOnce(r, 'outcome', pr?.number ?? e.issueNumber, body);
        const expectedBody = outcome.body;
        outcome = await api.get(`/issues/comments/${outcome.id}`);
        if (outcome.body !== expectedBody || outcome.user?.login !== WRITER) fail('COMMENT_CONTENT_CHANGED');
        r.outcome = { status: result.status === 'implemented' ? 'IMPLEMENTED_PENDING_FRESH_REVIEW' : 'BLOCKED',
          head: exactSha(result.result.revision) ? result.result.revision : null, prNumber: pr?.number ?? null,
          outcomeId: outcome.id, bodySha256: sha256Body(outcome.body), manual: true };
        await store.put(e.runId, r);
        if (result.status === 'implemented') await transitionManual(false);
        return receipt(r.outcome);
      }
      if (request.operation === 'finish-no-change') {
        if (r.outcome) return receipt(r.outcome);
        if (e.route !== 'auto' || e.request?.kind !== 'task-request'
          || e.target !== 'issue' || request.head !== e.startHead || r.publishedHead || r.publicationIntent) fail('NO_CHANGE_COMPLETION_INVALID');
        const pr = await existingPullRequest(r);
        if (pr && pr.head.sha !== e.startHead) fail('PR_HEAD_OBSERVATION_STALE');
        const number = pr?.number ?? e.issueNumber;
        const body = await successfulOutcomeIntent(r, boundOutcomeBody(e, `## Codex Outcome\n\nStatus: IMPLEMENTED_PENDING_FRESH_REVIEW\nThread: ${e.thread}\nAttempt: ${e.attemptId}\nSource/result head: ${e.startHead}\nArtifact: ${pr ? `PR #${pr.number}` : 'No PR; unchanged source'}\nCompletion: COMPLETED\n\n${workerOutcomeClaims(request.taskResult)}\n\nThe contained worker completed without source changes. No push or artificial PR was required. Independent Task review remains required.`, { pr, head: e.startHead }), e.startHead, pr?.number ?? null);
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
        // Manual routing skips worker preflight. Revalidate the native CR/head
        // and verified Draft state here, including admission/handoff replay.
        if (!r.outcome) await prepareRemediation(e);
        const url = e.reviewId ? `https://github.com/${REPOSITORY}/pull/${e.number}#pullrequestreview-${e.reviewId}` : `https://github.com/${REPOSITORY}/issues/${e.issueNumber}`;
        const requestBinding = e.requestReference ? `\nCurrent execution request: https://github.com/${REPOSITORY}/${e.requestReference.parent.kind === 'issue' ? 'issues' : 'pull'}/${e.requestReference.parent.number}#${e.requestReference.kind === 'review' ? 'pullrequestreview' : 'issuecomment'}-${e.requestReference.id}\nRequest SHA-256: ${e.requestReference.sha256}\nRead the stable Task charter plus this exact complete request and its selected source references. Verify it remains current; historical prose and ordinary comments grant no execution authority.\n` : '';
        const body = `MANUAL_CODEX_HANDOFF_READY\nThread: ${e.thread}\nAttempt: ${e.attemptId}\nModel: ${e.profile.cliModelId}; effort: ${e.profile.effort}\nSubagents: ${e.subagentsAllowed ? 'On' : 'Off'}\n\nCopyable prompt:\n\n\`\`\`text\nExecute the project-defined procedure for this canonical authority:\n${url}${requestBinding}\nThread: ${e.thread}\nCodex model: ${e.profile.cliModelId}\nCodex effort: ${e.profile.effort}\nSubagents: ${e.subagentsAllowed ? 'On' : 'Off'}\nFollow repository instructions and live authority. Commit and push safe task-owned work before handoff.\n\n${PROGRESS_BOUNDED_EXECUTION}\n\`\`\``;
        const comment = await commentOnce(r, 'handoff', e.number, body);
        return receipt({ status: 'handed-off', commentId: comment.id });
      }
      if (request.operation === 'terminal-outcome') {
        if (e.route !== 'auto' || request.status !== 'blocked') fail('TERMINAL_OUTCOME_NOT_ADMITTED');
        return receipt(await terminalOutcome(r, { publishedHead: request.publishedHead ?? r.publishedHead,
          terminalCode: request.terminalCode, diagnostic: request.diagnostic }));
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
        const executionWarnings = request.executionWarnings ?? [];
        if (!Array.isArray(executionWarnings) || executionWarnings.length > 1
          || executionWarnings.some(value => value !== 'UNCOMMITTED_WORK_REMAINS')) fail('EXECUTION_WARNING_INVALID');
        if (r.outcome?.status === 'BLOCKED') {
          const recovery = r.publicationRecoveries?.find(value => value.authorizationId === request.recoveryAuthorizationId);
          if (r.publicationIntent || recovery?.result?.status !== 'PUBLISHED'
            || recovery.result.publishedHead !== r.publishedHead) fail('RECOVERED_OUTCOME_REQUIRED');
        }
        await pullRequest(r);
        const drafted = await transitionPr({ api, store, key: e.runId, record: r, head: r.publishedHead, draft: true,
          readPr: () => existingPullRequest(r) });
        const { pr, readiness } = await observeReadiness(r, drafted);
        const warningSummary = [admissionWarningSummary(e.admission?.warnings ?? e.warnings),
          executionWarningSummary(executionWarnings)].filter(Boolean).join('; ');
        const body = await successfulOutcomeIntent(r, boundOutcomeBody(e, `## Codex Outcome\n\nStatus: IMPLEMENTED_PENDING_FRESH_REVIEW\nThread: ${e.thread}\nCorrelation: ${threadCorrelationIdentity(e.thread)}\nAttempt: ${e.attemptId}\nRequested model: ${e.profile.cliModelId}; effort: ${e.profile.effort}\nActual model/effort: UNAVAILABLE\n${usageOutcomeSummary(request.codexUsage)}\nHistorical reviewed/starting head: ${e.startHead}\nLatest durable candidate head: ${r.publishedHead}\n${readinessOutcomeLines(readiness)}\nCompletion: ${warningSummary ? 'COMPLETED_WITH_WARNINGS' : 'COMPLETED'}${warningSummary ? `\nWarning summary: ${warningSummary}` : ''}\n\n${workerOutcomeClaims(request.taskResult)}\n\nValidation: automatic worker reported bounded implementation and local validation success; Writer published and controller observed the exact PR head. Native candidate-head CI was not evaluated by automatic completion. Mergeability is a snapshot of the observed base; it does not establish independent acceptance or authorize base reconciliation.\nNative Ready means successful execution handoff only. Independent exact-head validation and review plus safe integration remain required before the authorized squash continuation.`, { pr, head: r.publishedHead, executionWarnings }), r.publishedHead, pr.number, { readiness });
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
  };
}
