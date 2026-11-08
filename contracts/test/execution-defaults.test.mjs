import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { EXECUTION_DEFAULTS, resolveExecutionDefaults, resolveExecutionProfile } from '../src/execution-defaults.mjs';
import { validateConsumer, consumerDigest } from '../../consumer/consumer-config.mjs';
import { CONSUMER } from '../../consumer/consumer.mjs';
import { renderAuthorityRecord, sha256Body } from '../src/github-authority.mjs';
import { REPOSITORY, REVIEWER } from '../../controller/src/execution-contract.mjs';
import { executeCodex } from '../../controller/src/attempt-runtime.mjs';
import { fixture } from '../../controller/test/fixture.mjs';
import { PROGRESS_BOUNDED_EXECUTION } from '../../runtime/src/execution-policy.mjs';

test('ordinary project defaults match deployment authoring inputs and canonical policy', () => {
  assert.deepEqual(EXECUTION_DEFAULTS, { effort: 'xhigh', subagentsAllowed: true });
  const policy = readFileSync(new URL('../../AGENTS.md', import.meta.url), 'utf8');
  assert.match(policy, /default model is\s+`gpt-6\.1-sol`, the default reasoning effort is `xhigh` and the default Subagents\s+permission is `On`/);
  const example = JSON.parse(readFileSync(new URL('../../deploy/example.json', import.meta.url), 'utf8'));
  assert.deepEqual({ ...example.consumer.defaultProfile, effort: resolveExecutionDefaults(example.consumer.defaultProfile).effort }, { cliModelId: 'gpt-6.1-sol', effort: 'xhigh' });
  const backend = readFileSync(new URL('../../deploy/ansible/group_vars/all.yml', import.meta.url), 'utf8');
  assert.match(backend, /^relay_default_model: gpt-6\.1-sol$/m);
  assert.deepEqual(resolveExecutionDefaults({ effort: 'max', subagentsAllowed: false }),
    { effort: 'max', subagentsAllowed: false });
});

test('consumer model stays required and omitted effort resolves without altering explicit config digests', () => {
  const omitted = { ...CONSUMER, defaultProfile: { cliModelId: 'explicit-model' } };
  assert.deepEqual(validateConsumer(omitted).defaultProfile, { cliModelId: 'explicit-model', effort: 'xhigh' });
  for (const effort of ['medium', 'max', 'high', 'ultra', 'future-effort']) {
    const explicit = { ...omitted, defaultProfile: { cliModelId: 'explicit-model', effort } };
    assert.deepEqual(validateConsumer(explicit).defaultProfile, explicit.defaultProfile);
    assert.equal(consumerDigest(validateConsumer(explicit)), consumerDigest(explicit));
  }
  for (const defaultProfile of [{}, { effort: 'ultra' }, { cliModelId: 'm', effort: null },
    { cliModelId: 'm', effort: '' }, { cliModelId: 'm', review_model: 'm' }]) {
    assert.throws(() => validateConsumer({ ...CONSUMER, defaultProfile }), { code: 'CONSUMER_CONFIG_INVALID' });
  }
});

test('delegation guidance selects assignment profiles and bounds context and authority', () => {
  const policy = readFileSync(new URL('../../docs/execution-policy.md', import.meta.url), 'utf8');
  for (const guidance of [policy, PROGRESS_BOUNDED_EXECUTION]) {
    assert.match(guidance, /complexity and risk/);
    assert.match(guidance, /differ from the parent's/);
    assert.match(guidance, /separate self-contained assignment/);
    assert.match(guidance, /completion criteria/);
    assert.match(guidance, /only when materially necessary/);
    assert.match(guidance, /prohibitions and protected boundaries/);
    assert.match(guidance, /Delegation never expands/);
  }
});

test('current profile resolution preserves explicit permissions and rejects ambiguous values', () => {
  for (const allowed of [false, true]) assert.equal(resolveExecutionProfile({ decisions: { subagents: allowed } }).subagents, allowed);
  for (const subagents of ['Off', 'maybe', null, 1])
    assert.throws(() => resolveExecutionProfile({ decisions: { subagents } }), { code: 'AUTHORITY_PROFILE_INVALID' });
});

test('current admitted defaults and explicit Decision overrides reach the worker unchanged', async t => {
  for (const [effort, allowed] of [[CONSUMER.defaultProfile.effort, true], ['medium', true], ['max', false], ['high', true]]) {
    const f = await fixture(t, { profile: { cliModelId: 'explicit-model', effort }, beforeAdmission: ({ issue, api }) => {
      const source = { id: 920, user: { login: REVIEWER, id: 701, type: 'Bot' },
        issue_url: `https://api.github.com/repos/${REPOSITORY}/issues/42`,
        body: renderAuthorityRecord({ schema_version: '4.0', kind: 'decision', repository: REPOSITORY, task: 42,
          parent: { kind: 'issue', number: 42 }, charter_sha256: sha256Body(issue.body),
          purpose: 'Select the authorized execution profile', amendments: { model: 'explicit-model', effort, subagents: allowed },
          supersedes: null, context: [] }) };
      const list = api.list.bind(api);
      api.list = async path => path === '/issues/42/comments' ? [...await list(path), source] : list(path);
    } });
    assert.deepEqual(f.envelope.profile, { cliModelId: 'explicit-model', effort });
    assert.equal(f.envelope.subagentsAllowed, allowed);
    await executeCodex(f.envelope, { runTask: async request => {
      assert.deepEqual(request.profile, f.envelope.profile);
      assert.ok(request.inputText.includes(`Subagents: ${allowed ? 'On' : 'Off'}`));
      const args = request.buildArgs({ inputPath: '/fixture/input', cwd: '/fixture', profile: request.profile });
      assert.equal(args[args.indexOf('--effort') + 1], effort);
      return { status: 'success' };
    } });
  }
});
