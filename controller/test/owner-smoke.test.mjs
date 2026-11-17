import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn, spawnSync } from 'node:child_process';
import { CONSUMER, CONSUMER_DIGEST } from '../../consumer/consumer.mjs';
import { validateEnvelope } from '../src/execution-contract.mjs';
import { assertOwnerSmokeCaller, executeOwnerSmoke, OWNER_SMOKE_INPUT, OWNER_SMOKE_PROFILE, validateOwnerSmokeRequest } from '../src/owner-smoke.mjs';
import { createOnDemandDispatchAdapter, createOwnerSmokeDispatchAdapter } from '../src/github.mjs';

const request = () => ({ version: 2, kind: 'owner-smoke', repository: CONSUMER.repository,
  consumerDigest: CONSUMER_DIGEST, attemptId: 'event-1234567890123', approvedHead: 'c'.repeat(40) });

test('owner smoke cannot be mistaken for a native admission or supply executable Task fields', async () => {
  assert.equal(validateOwnerSmokeRequest(request()).kind, 'owner-smoke');
  assert.throws(() => validateEnvelope(request()), { code: 'EXECUTION_ENVELOPE_INVALID' });
  await assert.rejects(createOnDemandDispatchAdapter().dispatch(request()), { code: 'EXECUTION_ENVELOPE_INVALID' });
  for (const delta of [{ input: 'arbitrary work' }, { profile: { cliModelId: 'other' } }, { step: 1 },
    { issueNumber: 263 }, { route: 'auto' }, { executionSlot: 'foreign' }, { attemptId: 'run-1' },
    { approvedHead: 'main' }, { repository: 'foreign/repository' }]) {
    assert.throws(() => validateOwnerSmokeRequest({ ...request(), ...delta }), { code: 'OWNER_SMOKE_REQUEST_INVALID' });
  }
});

test('owner smoke execution uses fixed prompt/profile and no synthetic Issue, Task, Step or admission', async () => {
  const actual = await executeOwnerSmoke(request(), { runTask: async value => {
    assert.equal(value.inputText, OWNER_SMOKE_INPUT); assert.deepEqual(value.profile, OWNER_SMOKE_PROFILE);
    assert.equal(value.operation, 'owner-smoke'); assert.equal(value.existingFallback, true);
    assert.equal(value.targetNumber, undefined);
    const args = value.buildArgs({ inputPath: '/scratch/input', cwd: '/scratch', profile: value.profile });
    assert.equal(args.at(-1), '--owner-smoke');
    assert.ok(!args.includes('--issue') && !args.includes('--pull-request'));
    value.evidence.codexContainment = 'reaped';
    return { status: 'success', summary: 'general-runner-smoke-child-started' };
  } });
  assert.equal(actual.child, 'started'); assert.equal(actual.containment, 'reaped');
});

function callerFixture(delta = {}) {
  const head = request().approvedHead, reviewed = `/opt/relay/releases/${head}/reviewed-source`;
  const producer = `${reviewed}/consumer-general-runner-smoke.mjs`;
  const files = { '/proc/20/cmdline': `/usr/bin/node\0${producer}\0--approved-head\0${head}\0`,
    '/proc/20/status': 'Name: node\nPPid:\t10\n', '/proc/10/comm': 'runuser\n',
    '/proc/10/cmdline': `/usr/sbin/runuser\0-u\0example-runner\0--\0/usr/bin/node\0${producer}\0--approved-head\0${head}\0`,
    [`/opt/relay/releases/${head}/artifact-manifest.json`]: JSON.stringify({ commit: head }), ...delta.files };
  return { parentPid: 20, uid: 1001, modulePath: `${reviewed}/controller/src/owner-smoke.mjs`,
    read: async path => files[path], metadata: async path => ({ uid: path === '/proc/20' ? 1001 : 0, isDirectory: () => true }),
    canonical: async path => path === '/opt/relay/current' ? `/opt/relay/releases/${head}` : path,
    load: async () => ({ OWNER_SMOKE_RUNNER_USER: 'example-runner', OWNER_SMOKE_CURRENT: '/opt/relay/current', OWNER_SMOKE_RELEASE_ROOT: '/opt/relay/releases' }), ...delta };
}
test('owner smoke verifies exact installed caller, current head, root runuser and event scratch', async () => {
  assert.equal(await assertOwnerSmokeCaller(request(), callerFixture()), `${CONSUMER.paths.workRoot}/${request().attemptId}`);
  for (const delta of [
    { read: async path => path.endsWith('/cmdline') ? '/usr/bin/node\0foreign.mjs\0' : '' },
    { metadata: async () => ({ uid: 1001, isDirectory: () => true }) },
    { canonical: async path => path === '/opt/relay/current' ? '/opt/relay/releases/' + 'd'.repeat(40) : path },
    { canonical: async path => path.includes('/event-') ? '/foreign/scratch' : callerFixture().canonical(path) },
    { read: async path => path.endsWith('/comm') ? 'node\n' : callerFixture().read(path) }
  ]) await assert.rejects(assertOwnerSmokeCaller(request(), callerFixture(delta)));
});

test('owner smoke transport retains the normal dispatcher lifetime and finalization boundary', async () => {
  let finalized, reserved;
  const adapter = createOwnerSmokeDispatchAdapter({
    reserveDiagnostic: async ({ executionId }) => { reserved = executionId; return { write: async () => {} }; },
    finalizeArtifacts: async value => { finalized = value; return { cleanup: 'complete', persistence: 'not_required' }; },
    spawnImpl(command, args, options) {
      assert.equal(command, CONSUMER.paths.dispatch); assert.deepEqual(args, ['--owner-smoke']);
      assert.equal(options.stdio.length, 4);
      return spawn(process.execPath, ['-e', `const fs=require('node:fs');const r=JSON.parse(fs.readFileSync(0,'utf8'));fs.writeSync(1,JSON.stringify({version:2,attemptId:r.attemptId,child:'started',containment:'reaped',result:{status:'success'}}));`], options);
    }
  });
  assert.equal((await adapter.dispatch(request())).containment, 'reaped');
  assert.equal(reserved, request().attemptId); assert.equal(finalized.containment, 'reaped');
});


test('real dispatcher owner mode refuses an unauthenticated caller before any child', () => {
  const entrypoint = new URL('../src/codex-dispatch-entrypoint.mjs', import.meta.url);
  const result = spawnSync(process.execPath, [entrypoint.pathname, '--owner-smoke'], {
    input: JSON.stringify(request()), env: { ...process.env }, encoding: 'utf8', timeout: 5000
  });
  assert.equal(result.status, 1, result.stderr);
  assert.equal(result.stdout, '');
  const failure = JSON.parse(result.stderr);
  assert.equal(failure.code, 'SMOKE_OWNER_TRANSITION_REQUIRED');
  assert.equal(failure.diagnostic.observed.child, 'not_started');
  assert.equal(failure.diagnostic.containment, 'not_required');
  const native = spawnSync(process.execPath, [entrypoint.pathname], {
    input: JSON.stringify(request()), env: { ...process.env }, encoding: 'utf8', timeout: 5000
  });
  assert.equal(native.status, 1);
  assert.equal(JSON.parse(native.stderr).code, 'EXECUTION_ENVELOPE_INVALID');
});


test('owner smoke reuses root helper manifest gate and reports exact failed authorization operation', async () => {
  const fixture = callerFixture();
  const read = async path => {
    if (path.endsWith('/artifact-manifest.json')) throw Object.assign(new Error('denied'), { code: 'EACCES' });
    return fixture.read(path);
  };
  assert.ok(await assertOwnerSmokeCaller(request(), { ...fixture, read }));
  await assert.rejects(assertOwnerSmokeCaller(request(), { ...fixture,
    read: async path => {
      if (path === '/proc/10/cmdline') throw Object.assign(new Error('denied'), { code: 'EACCES', syscall: 'open' });
      return fixture.read(path);
    }
  }), error => error.code === 'EACCES' && error.details.operation === 'owner-smoke-root-command');
});

test('owner smoke domain rejection retains safe observed binding without caller command text', async () => {
  await assert.rejects(assertOwnerSmokeCaller(request(), callerFixture({
    read: async path => path.endsWith('/cmdline') ? '/usr/bin/node\0private-caller-secret\0' : ''
  })), error => {
    assert.equal(error.code, 'SMOKE_OWNER_TRANSITION_REQUIRED');
    assert.equal(error.observation.check, 'owner-smoke-parent-command');
    assert.equal(error.observation.observed.producerMatches, false);
    assert.ok(!JSON.stringify(error).includes('private-caller-secret'));
    return true;
  });
});
