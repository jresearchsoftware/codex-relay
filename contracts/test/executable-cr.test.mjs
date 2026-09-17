import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { CR_DEFINITION, canonicalJson, validateStructuredCr } from '../src/executable-cr.mjs';
import { extractRemediationContract, validateRemediationContract } from '../src/contracts.mjs';
import { admitPublished } from '../test-support/roundtrip-driver.mjs';

const fixture = name => readFileSync(new URL(`./fixtures/${name}`, import.meta.url), 'utf8');
const input = JSON.parse(fixture('executable-cr-v2-input.json'));
const body = fixture('executable-cr-v2.md').trimEnd();
const publication = { event: input.action, commit_id: input.expected_head_sha, body };
const context = { pullRequest: input.pr_number, reviewedHeadSha: input.expected_head_sha };
const parse = text => validateRemediationContract(extractRemediationContract(text), context);
const normalized = cr => ({ ...structuredClone(cr), subagents_allowed: cr.subagents_allowed ?? false,
  owner_policy_reconciliation: cr.owner_policy_reconciliation ?? [],
  findings: cr.findings.map(f => ({ ...f, evidence: f.evidence ?? [] })), required_validation: [...cr.required_validation].sort() });
const wire = (cr = input.change_request, delta = {}) => ({ schema_version: CR_DEFINITION.schema_version,
  repository: input.repository, pull_request: input.pr_number, reviewed_head_sha: input.expected_head_sha,
  change_request: normalized(cr), ...delta });
const block = data => '```reviewer-executable-cr\n' + canonicalJson(data) + '\n```';

test('Rust canonical fixture admits through current native controller with repeated matching Steps', async () => {
  const contract = await admitPublished(input, publication);
  assert.deepEqual(contract.finding_ids, ['CR12-F1', 'serialization_gap_2']);
  assert.ok(body.includes('### CR12-F1 — major'));
  assert.ok(body.includes('### serialization_gap_2 — major'));
  assert.ok(body.includes(block(wire())));
});

test('validation comes from the structured contract, independent of human heading spelling', async () => {
  const renamed = body.replace('## Required validation', '## Validation and compatibility expectations');
  await admitPublished(input, { ...publication, body: renamed });
  const missing = structuredClone(input.change_request); delete missing.required_validation;
  assert.throws(() => validateStructuredCr(missing), { code: 'EXECUTABLE_CR_INVALID' });
});

test('repeated compatibility prose cannot create duplicate executable values', async () => {
  assert.equal(input.change_request.owner_policy_reconciliation[0], input.change_request.owner_policy_reconciliation[1]);
  await admitPublished(input, { ...publication, body: 'Codex model: harmless prose\nCodex model: repeated harmless prose\n' + body });
  const duplicate = structuredClone(input.change_request); duplicate.required_validation.push('diff-check');
  assert.throws(() => validateStructuredCr(duplicate), { code: 'EXECUTABLE_CR_INVALID' });
});

for (const row of JSON.parse(fixture('executable-cr-v2-invalid.json'))) {
  test(`shared producer/consumer rejection: ${row.name}`, () => {
    const cr = structuredClone(input.change_request);
    const parent = row.path.slice(0, -1).reduce((v, key) => v[key], cr);
    if (row.delete) delete parent[row.path.at(-1)]; else parent[row.path.at(-1)] = row.value;
    assert.throws(() => validateStructuredCr(cr), { code: 'EXECUTABLE_CR_INVALID' });
  });
}

test('all declared native validation names and safe explicit profiles remain executable', async () => {
  for (const codex_effort of ['low', 'medium', 'high', 'xhigh', 'max', 'future-effort', 'unknown']) {
    for (const subagents_allowed of [false, true]) {
      const args = structuredClone(input);
      Object.assign(args.change_request, { codex_model: 'future-model', codex_effort, subagents_allowed,
        required_validation: [...CR_DEFINITION.input_schema.properties.required_validation.items.enum] });
      await admitPublished(args, { ...publication, body: block(wire(args.change_request)) });
    }
  }
});

test('wrong binding, malformed JSON, duplicate keys/contracts and unsupported versions fail closed', () => {
  for (const [delta, code] of [
    [{ repository: 'other/repo' }, 'CONTRACT_BINDING_INVALID'],
    [{ pull_request: 116 }, 'CONTRACT_BINDING_INVALID'],
    [{ reviewed_head_sha: 'b'.repeat(40) }, 'CONTRACT_HEAD_MISMATCH'],
    [{ schema_version: '3.0' }, 'EXECUTABLE_CR_INVALID'],
    [{ extra: true }, 'EXECUTABLE_CR_INVALID']
  ]) assert.throws(() => parse(block(wire(undefined, delta))), { code });
  for (const text of [body + '\n' + block(wire()), block(wire()).replace('"step": 2', '"step": 2, "step": 3'),
    block(wire()).replace('"step": 2', '"step":'), block(wire()).slice(0, -4),
    body + '\n```yaml\nschema_version: "1.0"\n```']) {
    assert.throws(() => parse(text), { code: 'EXECUTABLE_CR_INVALID' });
  }
});

test('safe quoted Unicode prose round-trips without YAML or Markdown interpretation', () => {
  const cr = structuredClone(input.change_request);
  cr.findings[0].problem = 'Preserve "quotes", commas, colon: [lists], `code`, \\paths & <tags> — café 🦀. The ```reviewer-executable-cr fence is Reviewer-owned.';
  const parsed = parse(block(wire(cr)));
  assert.equal(parsed.findings[0].problem, cr.findings[0].problem);
});

test('the shared definition uses only the bounded keywords and formats supported in both languages', () => {
  const keys = new Set(['type', 'required', 'properties', 'additionalProperties', 'enum', 'format',
    'minLength', 'maxLength', 'minItems', 'maxItems', 'items', 'uniqueItems', 'minimum', 'maximum', 'description', 'default']);
  const walk = spec => {
    assert.ok(Object.keys(spec).every(key => keys.has(key)));
    if (spec.type === 'object') {
      assert.equal(spec.additionalProperties, false);
      Object.values(spec.properties).forEach(walk);
    }
    if (spec.type === 'array') {
      if (spec.uniqueItems) assert.equal(spec.items.type, 'string');
      walk(spec.items);
    }
    if (spec.minLength !== undefined) assert.equal(spec.minLength, 1);
    if (spec.format) assert.ok(['stable-id', 'codex-argument', 'completion-token'].includes(spec.format));
  };
  walk(CR_DEFINITION.input_schema);
});
