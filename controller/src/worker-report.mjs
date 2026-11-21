import { sha256Body } from '../../contracts/src/github-authority.mjs';
import { safePublicationText } from '../../contracts/src/publication-rendering.mjs';
import { MAX_SUMMARY_CHARACTERS } from '../../runtime/src/codex-result-schema.mjs';
import { redactDiagnosticText, redactSecrets } from './diagnostic-redaction.mjs';
import { fail, positive, WRITER } from './execution-contract.mjs';
import { secretFree } from './trusted-git.mjs';

export const SUMMARY_DISPLAY_BYTES = 16 * 1024;
const reportMarker = e => `<!-- relay:${e.attemptId}:report -->`;
const parentUrl = (e, number) => `https://api.github.com/repos/${e.repository}/issues/${number}`;
const literals = { '\\': '\\\\', '\r': '\\r', '\u2028': '\\L', '\u2029': '\\P',
  '<!--': '\\u003c!--', '```': '\\u0060``' };

export const isReportFailure = code => ['WORKER_REPORT_UNSAFE', 'WORKER_REPORT_UNAVAILABLE', 'WORKER_REPORT_CHANGED'].includes(code);

export function needsWorkerReport(summary, secrets) {
  return typeof summary === 'string' && (Buffer.byteLength(summary) > SUMMARY_DISPLAY_BYTES
    || Buffer.byteLength(safePublicationText(redactDiagnosticText(summary, secrets))) > SUMMARY_DISPLAY_BYTES);
}

function reportBody(e, head, summary, secrets) {
  // Publish only the report field, never diagnostics, token counters or
  // validation claims. Redaction of a report would change the deliverable.
  if (!summary.trim() || [...summary].length > MAX_SUMMARY_CHARACTERS || !summary.isWellFormed()
    || /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(summary)
    || redactSecrets(summary, secrets) !== summary) fail('WORKER_REPORT_UNSAFE');
  try { secretFree(summary); }
  catch (cause) { throw reportError('WORKER_REPORT_UNSAFE', cause); }
  // A fixed fenced block displays the report as inert text. The prefix keeps
  // every worker line out of authority parsers and prevents fence breakout.
  // Escape carriage returns, other JS line terminators and HTML comment starts
  // reversibly so neither native normalization nor marker search can alter it.
  const literal = summary.replace(/[\\\r\u2028\u2029]|<!--|```/g, value => literals[value])
    .split('\n').map(line => `| ${line}`).join('\n');
  return [
    '## Codex execution report', '',
    `Task ${e.issueNumber} — Step ${e.step}`,
    `Attempt: ${e.attemptId}`,
    `Result head: ${head}`,
    `Source SHA-256: ${sha256Body(summary)} (${Buffer.byteLength(summary)} UTF-8 bytes)`,
    '', 'The block contains the complete summary accepted from the launcher. Remove each line’s `| ` prefix and decode `\\\\`, `\\r`, `\\L` (U+2028), `\\P` (U+2029), `\\u003c` and `\\u0060` in a single pass to recover the original UTF-8 text.',
    '', '~~~text', literal, '~~~', '', reportMarker(e)
  ].join('\n');
}

function reportError(code, cause) {
  return Object.assign(new Error(code, { cause }), { code });
}

export async function verifyWorkerReport(api, e, report) {
  if (!report) return;
  let comment;
  try { comment = await api.get(`/issues/comments/${report.commentId}`); }
  catch (cause) { throw reportError('WORKER_REPORT_UNAVAILABLE', cause); }
  if (comment?.id !== report.commentId || comment.user?.login !== WRITER || comment.user?.type !== 'Bot'
    || comment.issue_url !== parentUrl(e, report.number) || typeof comment.body !== 'string'
    || sha256Body(comment.body) !== report.bodySha256) fail('WORKER_REPORT_CHANGED');
}

export async function publishWorkerReport({ api, store, record, number, head, summary, secrets }) {
  const e = record.envelope;
  const body = reportBody(e, head, summary, secrets);
  const bodySha256 = sha256Body(body);
  let intent = record.workerReport;
  if (intent && (intent.number !== number || intent.head !== head || intent.bodySha256 !== bodySha256))
    fail('WORKER_REPORT_CHANGED');
  if (intent?.commentId) {
    await verifyWorkerReport(api, e, intent);
    return intent;
  }
  let commentId;
  let postFailure;
  if (!intent) {
    intent = { number, head, bodySha256 };
    record.workerReport = intent;
    try { await store.put(e.runId, record); }
    catch (cause) { throw reportError('WORKER_REPORT_UNAVAILABLE', cause); }
    try { commentId = (await api.post(`/issues/${number}/comments`, { body })).id; }
    catch (cause) { postFailure = cause; }
  }
  // Recover an ambiguous POST only by observing its reserved exact bytes.
  // Absence does not authorize posting again, even after a process restart.
  if (!positive(commentId)) {
    let comments;
    try { comments = await api.list(`/issues/${number}/comments`); }
    catch (cause) { throw reportError('WORKER_REPORT_UNAVAILABLE', cause); }
    const matches = comments.filter(c => c.user?.login === WRITER && c.body?.endsWith(reportMarker(e)));
    if (!matches.length) throw reportError('WORKER_REPORT_UNAVAILABLE', postFailure);
    if (matches.length !== 1 || !positive(matches[0].id)) fail('WORKER_REPORT_CHANGED');
    commentId = matches[0].id;
  }
  const report = { ...intent, commentId };
  await verifyWorkerReport(api, e, report);
  record.workerReport = report;
  try { await store.put(e.runId, record); }
  catch (cause) { throw reportError('WORKER_REPORT_UNAVAILABLE', cause); }
  return report;
}

export function workerReportLink(e, report) {
  const path = report.number === e.issueNumber ? 'issues' : 'pull';
  return `https://github.com/${e.repository}/${path}/${report.number}#issuecomment-${report.commentId}`;
}
