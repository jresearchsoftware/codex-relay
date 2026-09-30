import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { EXECUTION_DEFAULTS, resolveExecutionDefaults } from '../src/execution-defaults.mjs';
import { validateConsumer, consumerDigest } from '../../consumer/consumer-config.mjs';
import { CONSUMER } from '../../consumer/consumer.mjs';
import { parseIssueAuthority } from '../../runtime/src/issue-authority.mjs';
import { executeCodex } from '../../controller/src/attempt-runtime.mjs';
import { fixture } from '../../controller/test/fixture.mjs';

test('shared machine defaults match canonical policy without a model default', () => {
  assert.deepEqual(EXECUTION_DEFAULTS, { effort: 'ultra', subagentsAllowed: true });
  const policy = readFileSync(new URL('../../AGENTS.md', import.meta.url), 'utf8');
  assert.match(policy, /default reasoning effort is\s+`ultra` and the default Subagents permission is `On`/);
  assert.deepEqual(resolveExecutionDefaults({ effort: 'max', subagentsAllowed: false }),
    { effort: 'max', subagentsAllowed: false });
});

test('consumer model stays required and omitted effort resolves without altering explicit config digests', () => {
  const omitted = { ...CONSUMER, defaultProfile: { cliModelId: 'explicit-model' } };
  assert.deepEqual(validateConsumer(omitted).defaultProfile, { cliModelId: 'explicit-model', effort: 'ultra' });
  for (const effort of ['max', 'high', 'ultra', 'future-effort']) {
    const explicit = { ...omitted, defaultProfile: { cliModelId: 'explicit-model', effort } };
    assert.equal(consumerDigest(validateConsumer(explicit)), consumerDigest(explicit));
  }
  for (const defaultProfile of [{}, { effort: 'ultra' }, { cliModelId: 'm', effort: null },
    { cliModelId: 'm', effort: '' }, { cliModelId: 'm', review_model: 'm' }]) {
    assert.throws(() => validateConsumer({ ...CONSUMER, defaultProfile }), { code: 'CONSUMER_CONFIG_INVALID' });
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
