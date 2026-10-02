import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { EXECUTION_DEFAULTS, resolveExecutionDefaults } from '../src/execution-defaults.mjs';
import { validateConsumer, consumerDigest } from '../../consumer/consumer-config.mjs';
import { CONSUMER } from '../../consumer/consumer.mjs';
import { parseIssueAuthority } from '../../runtime/src/issue-authority.mjs';
import { executeCodex } from '../../controller/src/attempt-runtime.mjs';
import { fixture } from '../../controller/test/fixture.mjs';
import { PROGRESS_BOUNDED_EXECUTION } from '../../runtime/src/execution-policy.mjs';

test('ordinary project defaults match schema, deployment inputs and canonical policy', () => {
  assert.deepEqual(EXECUTION_DEFAULTS, { effort: 'medium', subagentsAllowed: true });
  const policy = readFileSync(new URL('../../AGENTS.md', import.meta.url), 'utf8');
  assert.match(policy, /default model is\s+`gpt-6\.1-sol`, the default reasoning effort is `medium` and the default Subagents\s+permission is `On`/);
  const example = JSON.parse(readFileSync(new URL('../../deploy/example.json', import.meta.url), 'utf8'));
  assert.deepEqual(validateConsumer(example.consumer).defaultProfile, { cliModelId: 'gpt-6.1-sol', effort: 'medium' });
  const backend = readFileSync(new URL('../../deploy/ansible/group_vars/all.yml', import.meta.url), 'utf8');
  assert.match(backend, /^relay_default_model: gpt-6\.1-sol$/m);
  assert.deepEqual(resolveExecutionDefaults({ effort: 'max', subagentsAllowed: false }),
    { effort: 'max', subagentsAllowed: false });
});

test('consumer model stays required and omitted effort resolves without altering explicit config digests', () => {
  const omitted = { ...CONSUMER, defaultProfile: { cliModelId: 'explicit-model' } };
  assert.deepEqual(validateConsumer(omitted).defaultProfile, { cliModelId: 'explicit-model', effort: 'medium' });
  for (const effort of ['max', 'high', 'ultra', 'future-effort']) {
    const explicit = { ...omitted, defaultProfile: { cliModelId: 'explicit-model', effort } };
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

test('Issue authority preserves explicit permissions and blocks ambiguous permissions', () => {
  const parse = body => parseIssueAuthority(body, { issueNumber: 42, step: 1, targetBaseSha: 'a'.repeat(40) });
  assert.equal(parse('# Task\nDo the work.').subagentsAllowed, true);
  for (const [text, expected] of [['Off', false], ['On', true]]) {
    assert.equal(parse(`# Task\nSubagents: ${text}`).subagentsAllowed, expected);
  }
  for (const text of ['Subagents: maybe', 'Subagents: Off\nSubagents: On', 'Subagents:']) {
    assert.throws(() => parse(`# Task\n${text}`), { code: 'SUBAGENTS_PERMISSION_INVALID' });
  }
});

test('Issue defaults and explicit overrides reach the worker unchanged', async t => {
  for (const [fields, effort, allowed] of [
    ['', CONSUMER.defaultProfile.effort, true],
    ['Codex effort: max\nSubagents: Off', 'max', false],
    ['Codex effort: high\nSubagents: On', 'high', true]
  ]) {
    const f = await fixture(t, { issueBody: `# Task 42\nImplement the goal.\nCodex model: explicit-model\n${fields}` });
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
