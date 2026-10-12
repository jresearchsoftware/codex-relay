// Presentation only: callers validate authority before rendering. This module
// never resolves scope, accepts claims, allocates a Step or changes JSON bytes.
export const PUBLICATION_RENDERER_VERSION = 'human-v1';
export const LEGACY_PUBLICATION_RENDERER_VERSION = 'legacy-v1';

export function safePublicationText(value) {
  return String(value).replace(/[\u0000-\u001f\u007f]/g, ' ')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/[\\`*_{}\[\]()#+.!|~-]/g, '\\$&')
    .replace(/:/g, '&#58;').replace(/@/g, '&#64;');
}

const text = safePublicationText;
function section(lines, title, values) {
  if (!Array.isArray(values) || !values.length) return;
  lines.push('', `**${title}**`, '', ...values.map(value => `- ${text(value)}`));
}
function continuation(lines, value) {
  if (!value) return;
  lines.push('', `Continuation hold: ${value.hold ? 'yes' : 'no'}.`);
  if (value.task_complete !== undefined) lines.push(`Task completion claim: ${value.task_complete ? 'complete' : 'incomplete'}.`);
  if (value.next) lines.push(`Authorized next direction: Task ${value.next.task}${value.next.step ? `, Step ${value.next.step}` : ''}; native reference ${value.next.direction?.id ?? value.next.request?.id ?? 'UNAVAILABLE'}.`);
}
function identity(record) {
  return `Task ${record.task}${record.step ?? record.admission?.step ? ` — Step ${record.step ?? record.admission.step}` : ''}${record.change_request_id ? ` — ${text(record.change_request_id)}` : ''}`;
}
function core(record, title, authorityModel) {
  const lines = [`## Relay ${title}`, '', identity(record), '', `Authority model: ${authorityModel}`];
  if (record.purpose) lines.push('', `Purpose: ${text(record.purpose)}`);
  if (record.status) lines.push('', `Status: ${text(record.status)}${record.kind === 'outcome' ? ' (execution claim)' : ''}`);
  if (record.verdict || record.kind === 'change-request') lines.push('', `Verdict: ${text(record.verdict ?? 'REQUEST_CHANGES')}`);
  if (record.summary) lines.push('', text(record.summary));
  return lines;
}
function visible(record, title, authorityModel) {
  const lines = core(record, title, authorityModel);
  if (record.attempt ?? record.admission?.attempt) lines.push('', `Attempt: ${text(record.attempt ?? record.admission.attempt)}`);
  if (record.reviewed_head_sha) lines.push('', `Reviewed head: ${text(record.reviewed_head_sha)}`);
  if (record.result) {
    lines.push('', `Result: ${text(record.result.kind)}; revision: ${record.result.revision === null ? 'UNAVAILABLE' : text(record.result.revision)}.`);
    section(lines, 'Immutable result identities', record.result.identities.map(value => `${value.kind}: ${value.id}`));
  }
  if (record.outcome) lines.push('', `Accepted Outcome native ID: ${record.outcome.id}; digest: ${record.outcome.sha256}.`);
  if (record.authority_drift) {
    const drift = record.authority_drift;
    lines.push('', `Admitted authority digest: ${record.authority.sha256}.`,
      `Current trusted authority digest: ${drift.current_authority.sha256}.`,
      `Changed Task fields: ${drift.changed_fields.map(text).join(', ') || 'none (source provenance changed)'}.`,
      `Current-requirement review required: ${drift.review_required ? 'yes' : 'no additional semantic delta'}. The admission remains unchanged; permission changes grant no new execution authority.`);
    section(lines, 'Authority comparison gaps', drift.comparison_gaps);
  }
  section(lines, 'Scope', record.scope);
  section(lines, 'Boundaries', record.boundaries);
  section(lines, 'Required validation', record.validation);
  if (record.issue_closure_policy) lines.push('', `Issue closure policy: ${text(record.issue_closure_policy)}; closure still requires the applicable completion and independent acceptance conditions.`);
  if (record.route) lines.push('', `Execution route: ${text(record.route)}.`);
  if (record.model || record.effort || record.subagents !== undefined) lines.push('', `Requested profile: model ${text(record.model ?? 'project default')}; effort ${text(record.effort ?? 'project default')}; Subagents ${record.subagents === undefined ? 'project default' : record.subagents ? 'On' : 'Off'}. Actual runtime profile is not inferred.`);
  continuation(lines, record.continuation);
  if (record.amendments) {
    lines.push('', '**Decision amendments**');
    for (const key of Object.keys(record.amendments).sort()) {
      const value = record.amendments[key];
      if (key === 'continuation') continuation(lines, value);
      else if (Array.isArray(value)) section(lines, key.replace(/_/g, ' '), value);
      else lines.push('', `${key.replace(/_/g, ' ')}: ${text(value)}.`);
    }
  }
  if (record.overrides && Object.keys(record.overrides).length) {
    lines.push('', '**Remediation execution overrides**');
    for (const key of Object.keys(record.overrides).sort()) {
      const value = record.overrides[key];
      if (Array.isArray(value)) section(lines, key.replace(/_/g, ' '), value);
      else lines.push('', `${key.replace(/_/g, ' ')}: ${text(value)}.`);
    }
    lines.push('', 'Overrides apply within Task authority; they do not grant unrelated scope or Task closure.');
  }
  for (const finding of record.findings ?? []) {
    lines.push('', `**Finding ${text(finding.id)} (${text(finding.severity)})**`, '',
      `Problem: ${text(finding.problem)}`, '', `Impact: ${text(finding.impact)}`, '', `Required correction: ${text(finding.remediation)}`);
    section(lines, 'Acceptance criteria', finding.acceptance_criteria);
    section(lines, 'Finding evidence', finding.evidence);
  }
  for (const warning of record.warnings ?? []) {
    lines.push('', '**Warning**', '', `Source: ${text(warning.source)}`, '', `Impact: ${text(warning.impact)}`, '',
      `Disposition: ${text(warning.resolution)}`, '', `Next action: ${text(warning.next_action)}`);
    section(lines, 'Evidence gaps', warning.evidence_gaps);
  }
  section(lines, 'Limitations', record.limitations);
  if (record.kind === 'outcome') lines.push('', 'Next acceptance boundary: independent exact-result review; execution claims do not establish independent acceptance.');
  if (record.kind === 'change-request' || record.kind === 'task-review') lines.push('', 'Next acceptance boundary: correct the findings within authorized scope, then obtain fresh independent review of the exact result.');
  return lines;
}

export function renderPublication(record, { title, authorityModel, fence, canonicalJson,
  rendererVersion = PUBLICATION_RENDERER_VERSION, maxBodyBytes = 100000, maxBodyChars = 65536 }) {
  const machine = `\`\`\`${fence}\n${canonicalJson}\n\`\`\``;
  if (rendererVersion === LEGACY_PUBLICATION_RENDERER_VERSION) return `## Relay ${title}\n\nAuthority model: ${authorityModel}\n\n${machine}\n`;
  if (rendererVersion !== PUBLICATION_RENDERER_VERSION) throw Object.assign(new Error('Unsupported publication renderer'), { code: 'AUTHORITY_RENDERER_UNSUPPORTED' });
  const wrap = (lines, open = false) => `${lines.join('\n')}\n\n<details${open ? ' open' : ''}>\n<summary>Machine-readable authority (JSON)</summary>\n\n${machine}\n\n</details>\n`;
  const body = wrap(visible(record, title, authorityModel));
  if (Buffer.byteLength(body, 'utf8') <= maxBodyBytes && [...body].length <= maxBodyChars) return body;
  // A native-body size limit is a demonstrated integrity constraint. Keep the
  // complete canonical facts visible, instead of truncating material evidence.
  const fallback = wrap([...core(record, title, authorityModel), '',
    'Presentation size limit: canonical JSON is open below so all scope, findings, warnings and limitations remain visible.'], true);
  if (Buffer.byteLength(fallback, 'utf8') > maxBodyBytes || [...fallback].length > maxBodyChars)
    throw Object.assign(new Error('Publication exceeds native body limits'), { code: 'AUTHORITY_BODY_INVALID' });
  return fallback;
}

// Only the already-existing copyable fence is wrapped. Its contents, headers,
// references and lifecycle markers remain byte-exact, including CRLF inputs.
export function foldManualHandoff(body) {
  if (typeof body !== 'string' || !body.startsWith('MANUAL_CODEX_HANDOFF_READY\n') && !body.startsWith('MANUAL_CODEX_HANDOFF_READY\r\n')) return body;
  if (body.includes('<summary>Copyable Codex prompt</summary>')) return body;
  const blocks = [...body.matchAll(/^(`{3,})text\r?\n[\s\S]*?^\1(?=\r?\n|$)/gm)];
  if (blocks.length !== 1) return body;
  const block = blocks[0];
  const newline = body.includes('\r\n') ? '\r\n' : '\n';
  return `${body.slice(0, block.index)}<details>${newline}<summary>Copyable Codex prompt</summary>${newline}${newline}${block[0]}${newline}${newline}</details>${body.slice(block.index + block[0].length)}`;
}
