import { readFileSync } from 'node:fs';
import { CONSUMER } from '../../consumer/consumer.mjs';
import { safeModel, safeEffort } from '../../runtime/src/codex-profile.mjs';

// Included by the Rust binary and retained in reviewed-source at runtime. No
// network lookup, capability inventory or separate CR authority store.
export const CR_DEFINITION = JSON.parse(readFileSync(new URL(
  '../../reviewer/src/executable-cr-v2.json',
  import.meta.url), 'utf8'));
const validationItems = CR_DEFINITION.input_schema.properties.required_validation.items;
// Names are trusted consumer policy, never commands or caller-supplied schema.
validationItems.enum = [...new Set([...validationItems.enum, ...(CONSUMER.validationNames ?? [])])];
export const NATIVE_CR_VALIDATIONS = Object.freeze(validationItems.enum);
const invalid = () => { throw Object.assign(new Error('Invalid Reviewer execution contract'), { code: 'EXECUTABLE_CR_INVALID' }); };
const safeText = s => s.trim().length > 0 && s.normalize('NFC') === s && !/filecite/i.test(s)
  && !/[\p{Cc}\uFFFD\u200B-\u200F\u2028-\u202E\u2060-\u2069\uFEFF\uD800-\uDFFF]/u.test(s)
  && !/^(?:todo|tbd|unknown|pending|n\/a)$/i.test(s.trim()) && !(s.startsWith('<') && s.endsWith('>'));
const formatMatches = (s, format) => ({
  'stable-id': () => /^[A-Za-z][A-Za-z0-9_-]*$/.test(s),
  'codex-argument': () => safeModel(s),
  'completion-token': () => /^[A-Z][A-Z0-9_]*$/.test(s)
}[format]?.() ?? false);

// Only the bounded keywords used by our checked-in definition are supported;
// callers never supply schemas. String bounds match Rust's UTF-8 byte limits.
function conforms(value, spec) {
  if (spec.enum && !spec.enum.includes(value)) return false;
  switch (spec.type) {
    case 'object': return value !== null && typeof value === 'object' && !Array.isArray(value)
      && spec.required.every(key => Object.hasOwn(value, key))
      && Object.entries(value).every(([key, v]) => Object.hasOwn(spec.properties, key) && conforms(v, spec.properties[key]));
    case 'array': return Array.isArray(value) && value.length >= spec.minItems && value.length <= spec.maxItems
      && value.every(v => conforms(v, spec.items)) && (!spec.uniqueItems || new Set(value).size === value.length);
    case 'string': return typeof value === 'string' && (spec.enum || spec.format === 'codex-argument' || safeText(value))
      && Buffer.byteLength(value) <= (spec.maxLength ?? 1000) && (!spec.format || formatMatches(value, spec.format));
    case 'integer': return Number.isSafeInteger(value) && value >= spec.minimum && value <= spec.maximum;
    case 'boolean': return typeof value === 'boolean';
    default: return false;
  }
}

export function validateStructuredCr(cr) {
  if (!conforms(cr, CR_DEFINITION.input_schema) || !safeEffort(cr.codex_effort)
    || new Set(cr.findings.map(f => f.id)).size !== cr.findings.length
    || cr.success_token === cr.blocked_token || cr.success_outcome === cr.blocked_outcome) invalid();
  return cr;
}

export function canonicalJson(value) {
  const ordered = v => Array.isArray(v) ? v.map(ordered) : v !== null && typeof v === 'object'
    ? Object.fromEntries(Object.keys(v).sort().map(k => [k, ordered(v[k])])) : v;
  return JSON.stringify(ordered(value), null, 2);
}

export function extractExecutableCr(body) {
  const fence = CR_DEFINITION.fence;
  const starts = [...body.matchAll(new RegExp('^```' + fence + '[^\\n]*', 'gm'))];
  if (!starts.length) return null;
  const blocks = [...body.matchAll(new RegExp('^```' + fence + '\\n([\\s\\S]*?)\\n```(?=\\n|$)', 'gm'))];
  if (blocks.length !== 1 || starts.length !== 1
    || /```ya?ml\s*\n[\s\S]*?\bschema_version\s*:/i.test(body)) invalid();
  let wire;
  try { wire = JSON.parse(blocks[0][1]); } catch { invalid(); }
  // The producer owns quoting/order/escaping. This also rejects duplicate JSON
  // keys instead of allowing JSON.parse's last value to become authority.
  if (canonicalJson(wire) !== blocks[0][1] || !wire || Array.isArray(wire)
    || Object.keys(wire).sort().join(',') !== 'change_request,pull_request,repository,reviewed_head_sha,schema_version'
    || wire.schema_version !== CR_DEFINITION.schema_version) invalid();
  const cr = validateStructuredCr(wire.change_request);
  return { ...cr, schema_version: wire.schema_version, repository: wire.repository,
    pull_request: wire.pull_request, reviewed_head_sha: wire.reviewed_head_sha,
    required_starting_head: wire.reviewed_head_sha, finding_ids: cr.findings.map(f => f.id),
    subagents_allowed: cr.subagents_allowed ?? false };
}
