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

function pool({ shared = false } = {}) {
  const c = structuredClone(CONSUMER);
  delete c.executionSlots;
  const paths = Object.fromEntries(EXECUTION_PATH_NAMES.map(name => [name, c.paths[name]]));
  c.executionSlots = [
    { id: 'primary', runnerName: 'sample-primary', runnerUser: 'relay-runner', runtimeUser: c.runtimeUser, workGroup: 'relay-work', paths },
    { id: 'second', runnerName: 'sample-second', runnerUser: 'relay-runner-two', runtimeUser: 'relay-worker-two', workGroup: 'relay-work-two',
      paths: Object.fromEntries(EXECUTION_PATH_NAMES.map(name => [name, `/var/lib/relay-example-slot-two/${name}`])) }
  ];
  if (shared) {
    c.generalRunnerPool = { desiredCapacity: 2 };
    Object.assign(c.executionSlots[1], { runnerUser: c.executionSlots[0].runnerUser,
      runtimeUser: c.runtimeUser, workGroup: c.executionSlots[0].workGroup });
  }
  return c;
}

test('finite slots preserve one full config digest and explicit primary legacy paths', () => {
  const c = validateConsumer(pool()); const digest = consumerDigest(c);
  const second = resolveExecutionConsumer(c, 'second');
  assert.equal(second.runtimeUser, 'relay-worker-two');
  assert.equal(second.workGroup, 'relay-work-two');
  assert.equal(resolveExecutionConsumer(c).workGroup, 'relay-work');
  assert.equal(second.paths.writerHelper, c.paths.writerHelper);
  assert.equal(second.paths.claimRoot, c.paths.claimRoot);
  assert.equal(second.paths.workRoot, c.executionSlots[1].paths.workRoot);
  assert.equal(consumerDigest(c), digest);
  assert.notEqual(consumerDigest(second), digest);
  assert.equal(resolveExecutionConsumer(c).paths.workRoot, c.paths.workRoot);
  assert.ok(Object.isFrozen(second.paths));
  assert.throws(() => resolveExecutionConsumer(c, 'foreign'));
});

test('serial workGroup is optional, explicit and bound to the installation digest', () => {
  const original = structuredClone(CONSUMER); delete original.executionSlots; delete original.workGroup;
  const fixed = validateConsumer({ ...original, workGroup: 'relay-work' });
  assert.equal(resolveExecutionConsumer(fixed).workGroup, 'relay-work');
  assert.equal(resolveExecutionConsumer(original).workGroup, undefined);
  assert.notEqual(consumerDigest(fixed), consumerDigest(original));
  for (const workGroup of [null, '', 'root', 'shared;id', 979]) {
    assert.throws(() => validateConsumer({ ...original, workGroup }), { code: 'CONSUMER_CONFIG_INVALID' });
  }
  assert.throws(() => validateConsumer({ ...pool(), workGroup: 'foreign-group' }), { code: 'CONSUMER_CONFIG_INVALID' });
});

test('slot admission requires both configured runner name and actual UID', () => {
  const c = validateConsumer(pool());
  const uidForUser = name => name === 'relay-runner' ? 1201 : 1202;
  assert.equal(selectExecutionSlot(c, { runnerName: 'sample-second', uid: 1202, uidForUser }), 'second');
  assert.throws(() => selectExecutionSlot(c, { runnerName: 'sample-second', uid: 1201, uidForUser }));
  assert.throws(() => selectExecutionSlot(c, { runnerName: 'foreign', uid: 1202, uidForUser }));
  assert.throws(() => selectExecutionSlot(c, { runnerName: 'sample-primary', uid: 0, uidForUser }));
});

test('slots reject overlapping roots, root workers and runner/worker identity overlap', () => {
  for (const mutate of [
    c => { c.executionSlots[1].runtimeUser = c.executionSlots[0].runnerUser; },
    c => { c.executionSlots[1].runtimeUser = 'root'; },
    c => { c.executionSlots[1].runnerUser = 'root'; },
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

test('managed instances share runner/runtime identities while repository runtime selection remains protected configuration', () => {
  const c = validateConsumer(pool({ shared: true }));
  const uidForUser = user => user === 'relay-runner' ? 1201 : 1301;
  for (const slot of c.executionSlots) {
    assert.equal(selectExecutionSlot(c, { runnerName: slot.runnerName, uid: 1201, uidForUser }), slot.id);
    assert.equal(resolveExecutionConsumer(c, slot.id).runtimeUser, c.runtimeUser);
  }
  const other = pool({ shared: true });
  other.repository = 'synthetic-other/shared-pool';
  other.runtimeUser = 'other-runtime';
  for (const slot of other.executionSlots) slot.runtimeUser = other.runtimeUser;
  const selected = validateConsumer(other);
  assert.deepEqual(selected.executionSlots.map(slot => slot.runnerName), c.executionSlots.map(slot => slot.runnerName));
  assert.equal(resolveExecutionConsumer(selected, 'second').runtimeUser, 'other-runtime');
  assert.equal(resolveExecutionConsumer(c, 'second').runtimeUser, CONSUMER.runtimeUser);
  assert.notEqual(consumerDigest(selected), consumerDigest(c));
  for (const value of [null, {}, { desiredCapacity: 0 }, { desiredCapacity: 33 },
    { desiredCapacity: 1.5 }, { desiredCapacity: '2' }, { desiredCapacity: 2, runtimeUser: 'root' }]) {
    assert.throws(() => validateConsumer({ ...pool({ shared: true }), generalRunnerPool: value }));
  }
});

test('legacy execution slots retain distinct runner/runtime users and work groups', () => {
  for (const field of ['runnerUser', 'runtimeUser', 'workGroup']) {
    const legacy = pool(); legacy.executionSlots[1][field] = legacy.executionSlots[0][field];
    assert.throws(() => validateConsumer(legacy), { code: 'CONSUMER_CONFIG_INVALID' });
  }
  const managed = pool({ shared: true });
  assert.doesNotThrow(() => validateConsumer(managed));
  delete managed.generalRunnerPool;
  assert.throws(() => validateConsumer(managed), { code: 'CONSUMER_CONFIG_INVALID' });
});

test('pool capacity changes preserve admitted identity while runtime and repository bindings remain immutable', () => {
  const original = validateConsumer(pool({ shared: true }));
  const resized = structuredClone(original);
  resized.generalRunnerPool.desiredCapacity = 1;
  assert.equal(consumerDigest(validateConsumer(resized)), consumerDigest(original));
  for (const mutate of [
    c => { c.repository = 'another-owner/shared-pool'; },
    c => { c.executionSlots[1].paths.workRoot = '/var/lib/different-root/work'; },
    c => { c.executionSlots[1].runnerName = 'different-pool-member'; },
    c => { for (const slot of c.executionSlots) slot.runnerUser = 'different-runner'; },
    c => { c.runtimeUser = 'different-runtime'; for (const slot of c.executionSlots) slot.runtimeUser = c.runtimeUser; }
  ]) {
    const changed = structuredClone(original); mutate(changed);
    assert.notEqual(consumerDigest(validateConsumer(changed)), consumerDigest(original));
  }
  const legacy = pool();
  const resizedLegacy = structuredClone(legacy); resizedLegacy.executionSlots.pop();
  assert.notEqual(consumerDigest(validateConsumer(resizedLegacy)), consumerDigest(validateConsumer(legacy)));
});

test('isolated child sees the complete immutable package payload and its admitted checkout', () => {
  const spec = isolatedCodexProcess({ binary: '/opt/sample/codex-runtime/bin/codex', packageRoot: '/opt/sample/codex-runtime/package-home/packages',
    cwd: '/var/lib/sample/slot-two/work/run-103', toolchainRoot: '/opt/sample/rust', args: ['exec', '--json'] });
  assert.equal(spec.command, '/usr/bin/bwrap');
  for (const flag of ['--unshare-user', '--unshare-pid', '--unshare-ipc', '--unshare-uts', '--die-with-parent', '--new-session']) assert.ok(spec.args.includes(flag));
  assert.equal(spec.args.filter(value => value === '--bind').length, 1);
  assert.equal(spec.args[spec.args.indexOf('--bind') + 1], '/var/lib/sample/slot-two/work/run-103');
  assert.ok(spec.args.includes('/opt/sample/codex-runtime/package-home/packages'));
  assert.ok(!spec.args.includes('/opt/sample/codex-runtime/package-home'));
  assert.ok(!spec.args.includes('/var/lib/sample/codex-home'));
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
    await assert.rejects(assertWriterSlot({operation:'recover-publication',runId:1,executionSlot:'second'}, {callerUid:'1202',resolveSlot:()=> 'second',store}),e=>e.code==='EXECUTION_SLOT_BINDING_CHANGED');
    await assertWriterSlot({operation:'recover-publication',runId:2,executionSlot:'second'}, {callerUid:'1202',resolveSlot:()=> 'second',store});
    await assertWriterSlot({operation:'publication-state',runId:1,executionSlot:'second'}, {callerUid:'1202',resolveSlot:()=> 'second',store});
  `;
  await exec(process.execPath, ['--input-type=module', '-e', source], { env: { ...process.env, RELAY_CONSUMER_CONFIG: config, RELAY_EXECUTION_SLOT: 'second' } });
});

test('shared runner UID selects configured slots and recovers the original slot after capacity reduction', async t => {
  const root = await mkdtemp(join(tmpdir(), 'relay-shared-slots-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const config = join(root, 'consumer.json');
  const beforeResize = pool({ shared: true });
  const admittedDigest = consumerDigest(validateConsumer(beforeResize));
  beforeResize.generalRunnerPool.desiredCapacity = 1;
  await writeFile(config, JSON.stringify(beforeResize), { mode: 0o644 });
  const source = `
    import assert from 'node:assert/strict';
    import { callerExecutionSlot, assertWriterSlot } from './controller/src/privileged-writer-helper.mjs';
    import { CONSUMER, CONSUMER_DIGEST } from './consumer/consumer.mjs';
    import { publicationRecoveryJournal, recoverAttemptPublication } from './controller/src/recover-attempt-publication.mjs';
    const uidForUser = user => user === 'relay-runner' ? 1201 : 1301;
    const resolveSlot = options => callerExecutionSlot({ ...options, uidForUser });
    for (const slotId of ['primary', 'second']) {
      assert.equal(resolveSlot({ uid: 1201, slotId }), slotId);
      await assertWriterSlot({ operation: 'admit', executionSlot: slotId }, { callerUid: '1201', resolveSlot });
    }
    for (const options of [{ uid: 1201 }, { uid: 1201, slotId: 'foreign' },
      { uid: 0, slotId: 'primary' }, { uid: 1301, slotId: 'second' }]) {
      assert.throws(() => resolveSlot(options), { code: 'EXECUTION_SLOT_IDENTITY_INVALID' });
    }
    const store = { get: async () => ({ envelope: { executionSlot: 'primary' } }) };
    await assertWriterSlot({ operation: 'recover-publication', runId: 9, executionSlot: 'second' },
      { callerUid: '1201', resolveSlot, store });
    await assertWriterSlot({ operation: 'finish', runId: 9, executionSlot: 'second', recoveryAuthorizationId: 42 },
      { callerUid: '1201', resolveSlot, store });
    await assertWriterSlot({ operation: 'complete-handoff', runId: 9, executionSlot: 'second' },
      { callerUid: '1201', resolveSlot, store });
    for (const operation of ['preflight', 'finish', 'complete-execution']) {
      await assert.rejects(assertWriterSlot({ operation, runId: 9, executionSlot: 'second' },
        { callerUid: '1201', resolveSlot, store }), { code: 'EXECUTION_SLOT_BINDING_CHANGED' });
    }
    await assertWriterSlot({ operation: 'recover-publication', runId: 9, executionSlot: 'primary' },
      { callerUid: '1201', resolveSlot, store });
    await assertWriterSlot({ operation: 'publication-state', runId: 9, executionSlot: 'second' },
      { callerUid: '1201', resolveSlot, store });
    assert.equal(CONSUMER.generalRunnerPool.desiredCapacity,1);
    assert.equal(CONSUMER_DIGEST,${JSON.stringify(admittedDigest)});
    const envelope = {version:2,consumerDigest:${JSON.stringify(admittedDigest)},repository:CONSUMER.repository,
      executionSlot:'second',attemptId:'run-9',runId:9,step:1,target:'issue',number:42,issueNumber:42,
      route:'auto',branch:CONSUMER.taskBranchPrefix+'task-42',subagentsAllowed:true,
      startHead:'a'.repeat(40),historicalBase:'a'.repeat(40),targetBase:'b'.repeat(40),
      authorityDigest:'c'.repeat(64),profile:{cliModelId:'fixture-model',effort:'high'},validation:['diff-check']};
    const outcome={status:'IMPLEMENTED_PENDING_FRESH_REVIEW',head:'d'.repeat(40)};
    const record={version:2,envelope,execution:{reserved:true,returned:true,child:'started',containment:'reaped'},outcome};
    let locked=false; const journal={get:async()=>{assert.ok(locked);return record;},withLock:async(id,fn)=>{
      assert.equal(id,9);locked=true;try{return await fn();}finally{locked=false;}}};
    const request={runId:9,attemptId:'run-9',authorizationId:42};
    const broker={invoke:async value=>{
      assert.equal(value.runId,9);assert.equal(value.attemptId,'run-9');
      if(value.operation==='publication-state')return {envelope,recovery:{authorizationId:42}};
      if(value.operation==='recover-publication')return {publishedHead:outcome.head};
      if(value.operation==='complete-handoff')return outcome;
      assert.fail('Unexpected recovery operation');
    }};
    const selected=await publicationRecoveryJournal(request,broker,{createStore:root=>{
      assert.equal(root,CONSUMER.executionSlots[1].paths.attemptRoot);return journal;
    }});
    assert.equal(selected,journal);
    assert.deepEqual(await recoverAttemptPublication({...request,broker,journal:selected,
      collect:()=>assert.fail('Completed original result must not be recollected')}),outcome);
  `;
  await promisify(execFile)(process.execPath, ['--input-type=module', '-e', source],
    { env: { ...process.env, RELAY_CONSUMER_CONFIG: config, RELAY_EXECUTION_SLOT: 'primary' } });
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

for (const slotCount of [2, 32]) test(`lifecycle activity snapshot binds all ${slotCount} immutable configured slots and retains original recovery intent`, async t => {
  const root = await mkdtemp(join(tmpdir(), 'relay-slot-lifecycle-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const config = pool();
  if (slotCount === 32) {
    config.executionSlots.splice(1);
    for (let index = 1; index < slotCount; index++) {
      const id = `s${String(index).padStart(2, '0')}${'a'.repeat(29)}`;
      config.executionSlots.push({ id, runnerName: `sample-slot-${index}`, runnerUser: `relay-runner-${index}`,
        runtimeUser: `relay-worker-${index}`, workGroup: `relay-work-${index}`,
        paths: Object.fromEntries(EXECUTION_PATH_NAMES.map(name => [name, `/var/lib/relay-example-slot-${index}/${name}`])) });
    }
  }
  const pathname = join(root, 'consumer.json');
  await writeFile(pathname, JSON.stringify(validateConsumer(config)), { mode: 0o644 });
  const source = `
    import assert from 'node:assert/strict';
    import {readFile,writeFile} from 'node:fs/promises';
    import {CONSUMER,CONSUMER_DIGEST} from './consumer/consumer.mjs';
    import {createAdmissionControl,ADMISSION_STATE_BYTES} from './controller/src/admission-control.mjs';
    const root=${JSON.stringify(root)};
    const store={all:async()=>[]}; const journal={get:async()=>null};
    const options={root,consumerDigest:CONSUMER_DIGEST,store,journal,protectedRoot:false};
    const gate=createAdmissionControl(options);
    const operationId='12345678-1234-1234-1234-123456789abc'; const target='a'.repeat(40);
    const original={reviewer:{active:true,enabled:'disabled',load:'loaded'},
      production:{active:false,enabled:'enabled',load:'loaded'},
      general:{active:true,enabled:'enabled-runtime',load:'loaded'},
      manualOutcome:{active:false,enabled:'disabled',load:'not-found'}};
    const additional=CONSUMER.executionSlots.filter(slot=>slot.id!=='primary');
    for(const slot of additional) original['slot-'+slot.id]={active:false,enabled:'enabled-runtime',load:'loaded'};
    await gate.initialize(); await gate.quiesce({operationId,target}); await gate.drained({operationId});
    await gate.phase({operationId,phase:'applying'});
    const slotKey='slot-'+additional[0].id;
    for(const modify of [
      value=>{delete value[slotKey];},
      value=>{value['slot-foreign']={...value[slotKey]};},
      value=>{value['slot-primary']={...value.general};},
      value=>{value[slotKey].active='false';},
      value=>{value[slotKey].enabled='unknown';},
      value=>{value[slotKey].load='not-found';},
      value=>{value[slotKey].extra=true;}
    ]){
      const invalid=structuredClone(original);modify(invalid);
      await assert.rejects(gate.snapshot({operationId,services:invalid}),{code:'ADMISSION_SNAPSHOT_INVALID'});
      assert.equal((await gate.read()).previousActive,null);
    }
    assert.deepEqual((await gate.snapshot({operationId,services:original})).previousActive,original);
    const gatePath=root+'/admission-v1.json';
    const saved=await readFile(gatePath,'utf8'); assert.ok(Buffer.byteLength(saved)<=ADMISSION_STATE_BYTES);
    const changed=JSON.parse(saved); delete changed.previousActive[slotKey];
    await writeFile(gatePath,JSON.stringify(changed),{mode:0o600});
    await assert.rejects(gate.read(),{code:'ADMISSION_STATE_INVALID'});
    await writeFile(gatePath,saved,{mode:0o600});
    await assert.rejects(createAdmissionControl({...options,consumerDigest:'b'.repeat(64)}).read(),{code:'CONSUMER_CONFIG_CHANGED'});
    await gate.phase({operationId,phase:'recovery-required'});
    const reopened=createAdmissionControl(options);
    assert.deepEqual((await reopened.initialize()).previousActive,original);
    const failed=structuredClone(original);
    for(const component of Object.values(failed))component.active=false;
    assert.deepEqual((await reopened.snapshot({operationId,services:failed})).previousActive,original);
    await reopened.phase({operationId,phase:'applying'});
    assert.deepEqual((await reopened.snapshot({operationId,services:failed})).previousActive,original);
    await reopened.phase({operationId,phase:'verified',revision:target}); await reopened.resume({operationId});
    assert.equal((await reopened.read()).previousActive,null);
  `;
  await promisify(execFile)(process.execPath, ['--input-type=module', '-e', source],
    { env: { ...process.env, RELAY_CONSUMER_CONFIG: pathname, RELAY_EXECUTION_SLOT: 'primary' } });
});
