
// Immutable admissions select display metadata, never execution or acceptance.
export function latestProjection(records, envelope, { sameBranch = false } = {}) {
  return records.filter(r => !r.admissionBlock && r.envelope?.repository === envelope.repository
    && r.envelope.issueNumber === envelope.issueNumber && r.envelope.request?.kind === 'admission'
    && (!sameBranch || r.envelope.branch === envelope.branch))
    .map(r => r.envelope).reduce((latest, e) => e.step > latest.step ? e : latest, envelope);
}

// An unresolved external effect holds its exact target. An unrelated Outcome
// or a different ref cannot become a hidden installation-wide admission gate.
export function assertPublicationIsolation(records, envelope) {
  for (const record of records) {
    const other = record.envelope;
    if (!other || other.repository !== envelope.repository || other.attemptId === envelope.attemptId) continue;
    const sameRef = envelope.branch && other.branch === envelope.branch;
    const pr = envelope.target === 'pull_request' ? envelope.number : envelope.continuation?.pullRequest;
    const otherPr = record.prNumber ?? (other.target === 'pull_request' ? other.number : other.continuation?.pullRequest);
    if ((sameRef && (record.publicationIntent || record.prIntent && !record.prNumber))
      || ((sameRef || pr && pr === otherPr) && record.lifecycleIntent)) {
      throw Object.assign(new Error('PUBLICATION_TARGET_HELD'), { code: 'PUBLICATION_TARGET_HELD', details: { conflictingAttempt: other.attemptId,
        resource: sameRef ? `refs/heads/${envelope.branch}` : `pull_request/${pr}`,
        nextAction: 'recover-original-publication-operation' } });
    }
  }
}
