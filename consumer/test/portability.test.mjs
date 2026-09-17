import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import { CONSUMER, CONSUMER_DIGEST } from '../consumer.mjs';
import { loadConsumer, validateConsumer, parseConsumerJson } from '../consumer-config.mjs';
import { fixture, memoryStore } from '../../controller/test/fixture.mjs';
import { runAttempt } from '../../controller/src/attempt.mjs';
import { assertPr, currentReview } from '../../controller/src/live-authority.mjs';
import { validateEnvelope } from '../../controller/src/execution-contract.mjs';
import { createGithubApi } from '../../controller/src/github-api.mjs';
import { validateRemediationContract } from '../../contracts/src/contracts.mjs';
import { parseEnv } from '../../controller/src/writer-auth.mjs';
import { readDiagnosticsConfig } from '../../controller/src/diagnostics.mjs';

test(`same modules: ${CONSUMER.repository} Issue and remediation publication and replay`, async t => {
  for (const remediation of [false, true]) {
    const f = await fixture(t, { remediation, labelLaunch: true });
    assert.equal(f.envelope.repository, CONSUMER.repository);
    assert.equal(f.envelope.consumerDigest, CONSUMER_DIGEST);
    assert.ok(f.envelope.branch.startsWith(CONSUMER.taskBranchPrefix));
    const journal = memoryStore(); let calls = 0;
    const execute = async () => {
      calls++; await f.commit();
      return { version: 2, attemptId: f.envelope.attemptId, child: 'started', containment: 'reaped',
        result: { status: 'success', summary: 'isolated fixture', validation: ['local fixture'] } };
    };
    const result = await runAttempt({ ...f, journal, execute });
    assert.equal(result.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW', JSON.stringify(result));
    await runAttempt({ ...f, journal, execute });
    assert.equal(calls, 1); assert.equal(f.pushes(), 1);
    assert.equal(f.comments.filter(c => c.body.includes('## Codex Outcome')).length, 1);
    assert.equal(await f.remoteHead(), result.head);
    assert.throws(() => validateEnvelope({ ...f.envelope, repository: 'foreign/repository' }));
    assert.throws(() => validateEnvelope({ ...f.envelope, consumerDigest: '0'.repeat(64) }));
    if (remediation) {
      assert.throws(() => assertPr({ ...f.pr, base: { ...f.pr.base, ref: 'foreign-base' } }, f.pr.number));
      assert.throws(() => assertPr({ ...f.pr, head: { ...f.pr.head, repo: { full_name: 'foreign/fork' } } }, f.pr.number));
      assert.throws(() => currentReview([{ ...f.review, user: { login: CONSUMER.writerApp.expectedActor } }]));
    }
  }
});

test('consumer profile is resolved once; repository API and credentials use only the configured identity', async t => {
  const f = await fixture(t, { issueBody: '# Fixture task\nImplement the admitted goal.' });
  assert.deepEqual(f.envelope.profile, CONSUMER.defaultProfile);
  assert.equal(f.envelope.branch, `${CONSUMER.taskBranchPrefix}task-42`);
  const requests = [];
  const api = createGithubApi({ token: 'fixture', fetchImpl: async url => {
    requests.push(url); return { ok: true, status: 200, json: async () => ({}) };
  } });
  await api.get('/issues/1');
  assert.equal(requests[0], `https://api.github.com/repos/${CONSUMER.repository}/issues/1`);
  const env = `GITHUB_APP_ID=${CONSUMER.writerApp.appId}\nGITHUB_APP_INSTALLATION_ID=${CONSUMER.writerApp.installationId}\nGITHUB_APP_PRIVATE_KEY_FILE=${CONSUMER.paths.credentialKeyFile}`;
  assert.ok(parseEnv(env, CONSUMER.paths.credentialKeyFile));
  assert.throws(() => parseEnv(env.replace(CONSUMER.writerApp.appId, CONSUMER.reviewerApp.appId), CONSUMER.paths.credentialKeyFile));
  assert.throws(() => parseEnv(env + '\nGITHUB_APP_ID=1', CONSUMER.paths.credentialKeyFile));
  assert.throws(() => validateRemediationContract({ schema_version: '1.0', repository: 'foreign/repository', pull_request: 1 }, { pullRequest: 1 }));
});

test('missing, malformed, unsafe and overlapping consumer configuration fails closed', () => {
  for (const value of [undefined, {}, { ...CONSUMER, repository: 'wrong/owner/repo' },
    { ...CONSUMER, baseBranch: '../main' }, { ...CONSUMER, writerApp: CONSUMER.reviewerApp },
    { ...CONSUMER, defaultProfile: null }, { ...CONSUMER, runtimeUser: 'root;id' },
    { ...CONSUMER, routingWorkflow: '../workflow.yml' }, { ...CONSUMER, unknown: 'ignored' }]) {
    assert.throws(() => validateConsumer(value), { code: 'CONSUMER_CONFIG_INVALID' });
  }
  assert.throws(() => parseConsumerJson('{"a":1,"a":2}'));
  assert.throws(() => parseConsumerJson('{"a":1,"nested":{"b":1,"b":2}}'));
  assert.throws(() => loadConsumer('/nonexistent/relay-consumer.json'));
  const env = { ...process.env }; delete env.RELAY_CONSUMER_CONFIG;
  const result = spawnSync(process.execPath, [new URL('../consumer.mjs', import.meta.url).pathname], { env, encoding: 'utf8' });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /CONSUMER_CONFIG_INVALID/);
});

test('consumer validation declarations are optional, bounded names rather than commands', () => {
  for (const validationNames of [null, 'pytest', ['pytest', 'pytest'], ['pytest;id'], ['UPPER'],
    ['a'.repeat(65)], Array.from({ length: 33 }, (_, i) => `check-${i}`)]) {
    assert.throws(() => validateConsumer({ ...CONSUMER, validationNames }), { code: 'CONSUMER_CONFIG_INVALID' });
  }
  assert.deepEqual(validateConsumer({ ...CONSUMER, validationNames: ['pytest-inventory'] }).validationNames, ['pytest-inventory']);
});

test('plain synthetic consumer and diagnostics examples pass the actual validators', async () => {
  for (const name of ['example', 'canary', 'inventory']) {
    const value = parseConsumerJson(await readFile(new URL(`../fixtures/${name}.json`, import.meta.url), 'utf8'));
    assert.equal(validateConsumer(value).repository, value.repository);
  }
  const example = await readFile(new URL('../../examples/diagnostics.json', import.meta.url), 'utf8');
  assert.deepEqual(await readDiagnosticsConfig({ readFileImpl: async () => example }), { mode: 'normal' });
});
