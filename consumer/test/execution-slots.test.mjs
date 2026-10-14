import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { promisify } from 'node:util';
import { execFile } from 'node:child_process';
import { validateConsumer, consumerDigest, resolveExecutionConsumer, selectExecutionSlot, EXECUTION_PATH_NAMES } from '../consumer-config.mjs';
import { isolatedCodexProcess } from '../../deploy/ansible/roles/relay_codex_runtime/files/relay-codex-isolation.mjs';
import { CONSUMER } from '../consumer.mjs';
import { main } from '../../controller/src/entrypoint.mjs';
import { fixture } from '../../controller/test/fixture.mjs';

function pool() {
  const c = structuredClone(CONSUMER);
  delete c.executionSlots;
  const paths = Object.fromEntries(EXECUTION_PATH_NAMES.map(name => [name, c.paths[name]]));
  c.executionSlots = [
    { id: 'primary', runnerName: 'sample-primary', runnerUser: 'relay-runner', runtimeUser: c.runtimeUser, workGroup: 'relay-work', paths },
    { id: 'second', runnerName: 'sample-second', runnerUser: 'relay-runner-two', runtimeUser: 'relay-worker-two', workGroup: 'relay-work-two',
      paths: Object.fromEntries(EXECUTION_PATH_NAMES.map(name => [name, `/var/lib/relay-example-slot-two/${name}`])) }
  ];
  return c;
}

test('finite slots preserve one full config digest and explicit primary legacy paths', () => {
  const c = validateConsumer(pool()); const digest = consumerDigest(c);
  const second = resolveExecutionConsumer(c, 'second');
  assert.equal(second.runtimeUser, 'relay-worker-two');
  assert.equal(second.paths.writerHelper, c.paths.writerHelper);
  assert.equal(second.paths.claimRoot, c.paths.claimRoot);
  assert.equal(second.paths.workRoot, c.executionSlots[1].paths.workRoot);
  assert.equal(consumerDigest(c), digest);
  assert.notEqual(consumerDigest(second), digest);
  assert.equal(resolveExecutionConsumer(c).paths.workRoot, c.paths.workRoot);
  assert.ok(Object.isFrozen(second.paths));
  assert.throws(() => resolveExecutionConsumer(c, 'foreign'));
});

test('slot admission requires both configured runner name and actual UID', () => {
  const c = validateConsumer(pool());
  const uidForUser = name => name === 'relay-runner' ? 1201 : 1202;
  assert.equal(selectExecutionSlot(c, { runnerName: 'sample-second', uid: 1202, uidForUser }), 'second');
  assert.throws(() => selectExecutionSlot(c, { runnerName: 'sample-second', uid: 1201, uidForUser }));
  assert.throws(() => selectExecutionSlot(c, { runnerName: 'foreign', uid: 1202, uidForUser }));
  assert.throws(() => selectExecutionSlot(c, { runnerName: 'sample-primary', uid: 0, uidForUser }));
});

test('slots reject overlapping work/evidence/helper roots and reused Unix identities', () => {
  for (const mutate of [
    c => { c.executionSlots[1].runnerUser = c.executionSlots[0].runnerUser; },
    c => { c.executionSlots[1].runtimeUser = c.executionSlots[0].runnerUser; },
    c => { c.executionSlots[1].workGroup = c.executionSlots[0].workGroup; },
    c => { c.executionSlots[1].paths.workRoot = c.paths.workRoot + '/foreign'; },
    c => { c.executionSlots[1].paths.attemptRoot = c.paths.claimRoot; },
    c => { c.executionSlots[1].paths.dispatch = c.executionSlots[1].paths.workRoot + '/dispatch'; },
    c => { c.executionSlots[1].paths.attemptRoot = c.executionSlots[1].paths.workRoot + '/journal'; },
    c => { c.executionSlots[0].runtimeUser = 'foreign-runtime'; },
    c => { c.executionSlots.shift(); },
    c => { c.executionSlots.push(structuredClone(c.executionSlots[1])); },
    c => { c.executionSlots = []; }
  ]) { const c = pool(); mutate(c); assert.throws(() => validateConsumer(c)); }
});

test('isolated child sees only installed readonly code and its admitted checkout', () => {
  const spec = isolatedCodexProcess({ binary: '/opt/sample/codex-runtime/bin/codex', resolvedBinary: '/var/lib/sample/packages/bin/codex',
    cwd: '/var/lib/sample/slot-two/work/run-103', toolchainRoot: '/opt/sample/rust', args: ['exec', '--json'] });
  assert.equal(spec.command, '/usr/bin/bwrap');
  for (const flag of ['--unshare-user', '--unshare-pid', '--unshare-ipc', '--unshare-uts', '--die-with-parent', '--new-session']) assert.ok(spec.args.includes(flag));
  assert.equal(spec.args.filter(value => value === '--bind').length, 1);
  assert.equal(spec.args[spec.args.indexOf('--bind') + 1], '/var/lib/sample/slot-two/work/run-103');
  assert.ok(spec.args.includes('/var/lib/sample/packages/bin'));
  assert.ok(!spec.args.includes('/etc'));
  assert.ok(!spec.args.includes('/var/lib'));
  assert.ok(!spec.args.includes('/opt/sample'));
  assert.ok(!spec.args.includes('/opt/sample/runner'));
  assert.ok(!spec.args.includes('--unshare-net'));
  assert.deepEqual(spec.args.slice(-4), ['--', '/opt/sample/codex-runtime/bin/codex', 'exec', '--json']);
});

test('root journal routing and global admission drain read each immutable stored slot', async t => {
  const root = await mkdtemp(join(tmpdir(), 'relay-slots-')); t.after(() => rm(root, { recursive: true, force: true }));
  const config = join(root, 'consumer.json'); await writeFile(config, JSON.stringify(pool()), { mode: 0o644 });
  const exec = promisify(execFile);
  const source = `
    import assert from 'node:assert/strict';
    import { createSlotJournal } from './controller/src/slot-journal.mjs';
    import { callerExecutionSlot, assertWriterSlot } from './controller/src/privileged-writer-helper.mjs';
    import { CONSUMER, CONSUMER_DIGEST } from './consumer/consumer.mjs';
    import { createAdmissionControl } from './controller/src/admission-control.mjs';
    const make = (runId, executionSlot, issueNumber) => ({envelope:{version:2,runId,attemptId:'run-'+runId,route:'auto',consumerDigest:CONSUMER_DIGEST,executionSlot,issueNumber}, controllerLifecycle:{version:1,status:'active'}});
    const records = [make(1,'primary',10),make(2,'second',11)];
    const store = {get:async id=>records.find(r=>r.envelope.runId===id),all:async()=>records};
    const observed=[];
    const journal=createSlotJournal(store,{createStore:root=>({get:async id=>{observed.push([root,id]);return null;}})});
    await journal.get(1);await journal.get(2);
    assert.equal(observed[0][0],CONSUMER.paths.attemptRoot);
    assert.equal(observed[1][0],CONSUMER.executionSlots[1].paths.attemptRoot);
    const gate=createAdmissionControl({root:${JSON.stringify(root)},consumerDigest:CONSUMER_DIGEST,store,journal,protectedRoot:false});
    await gate.initialize(); assert.deepEqual((await gate.status()).active,[1,2]);
    await assert.rejects(gate.assertSlotComplete('second'),e=>e.code==='EXECUTION_SLOT_UNAVAILABLE');
    await assert.rejects(gate.assertTaskComplete(10),e=>e.code==='PRIOR_EXECUTION_UNRESOLVED');
    const uidForUser=user=>user==='relay-runner'?1201:1202;
    assert.equal(callerExecutionSlot({uid:1202,uidForUser}),'second');
    assert.throws(()=>callerExecutionSlot({uid:1400,uidForUser}));
    await assertWriterSlot({operation:'admit',executionSlot:'second'}, {callerUid:'1202',resolveSlot:()=> 'second'});
    await assert.rejects(assertWriterSlot({operation:'admit',executionSlot:'primary'}, {callerUid:'1202',resolveSlot:()=> 'second'}));
    await assert.rejects(assertWriterSlot({operation:'finish',runId:1,executionSlot:'second'}, {callerUid:'1202',resolveSlot:()=> 'second',store}),e=>e.code==='EXECUTION_SLOT_BINDING_CHANGED');
  `;
  await exec(process.execPath, ['--input-type=module', '-e', source], { env: { ...process.env, RELAY_CONSUMER_CONFIG: config, RELAY_EXECUTION_SLOT: 'second' } });
});

test('a duplicate controller never persists failure or completes the active owner reservation', async t => {
  const f = await fixture(t);
  const operations = [];
  const event = { repository: { full_name: CONSUMER.repository }, sender: { login: CONSUMER.owner },
    inputs: { route: 'auto', task: '42', step: '1' } };
  await assert.rejects(main({
    env: { GITHUB_EVENT_PATH: '/unused', GITHUB_EVENT_NAME: 'workflow_dispatch', GITHUB_REF: `refs/heads/${CONSUMER.baseBranch}`, GITHUB_RUN_ID: '99' },
    readEvent: async () => JSON.stringify(event), resolveSlot: () => undefined,
    createWriter: () => ({ invoke: async request => { operations.push(request.operation); return { envelope: f.envelope }; } }),
    createDispatcher: () => ({ dispatch: () => assert.fail('duplicate worker started') }),
    createJournal: () => ({ withLock: async () => { throw Object.assign(new Error('busy'), { code: 'ATTEMPT_CONTROLLER_BUSY' }); } }),
    persistFailure: () => assert.fail('duplicate modified diagnostics')
  }), error => error.code === 'ATTEMPT_CONTROLLER_BUSY');
  assert.deepEqual(operations, ['admit']);
});
