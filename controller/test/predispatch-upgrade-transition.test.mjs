import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { fixture, memoryStore } from './fixture.mjs';
import { createPublicationBroker } from '../src/publication-broker.mjs';
import { createAdmissionControl } from '../src/admission-control.mjs';
import { REPOSITORY } from '../src/execution-contract.mjs';
import { nextAdmissionStep } from '../src/admission-step.mjs';
import { extractHistoricalRuntime } from './historical-runtime.mjs';

test('installed 0aff reader blocks finalized receipt while staged candidate drains and advances', async t => {
  const oldRoot = await mkdtemp(join(tmpdir(), 'relay-230-old-runtime-'));
  t.after(() => rm(oldRoot, { recursive: true, force: true }));
  await extractHistoricalRuntime(oldRoot, '0aff32a6873262185f60364463f4e97ef330de89');
  const { createAdmissionControl: oldControl } = await import(pathToFileURL(join(oldRoot, 'controller/src/admission-control.mjs')));
  let f; const journal = memoryStore();
  journal.withLock = async (_id, action) => action();
  await assert.rejects(fixture(t, {labelLaunch:true, continuation:true, createJournal:()=>journal,
    createAdmission:async()=>({assertOpen:async()=>{},assertSlotComplete:async()=>{},reserve:async()=>({version:1,status:'active'})}),
    beforeAdmission(value) { f=value; value.issue.labels=[{name:'step-1'},{name:'codex-ready-auto'}];
      value.api.ensureStepLabel=async()=>{throw new TypeError('projection failure');}; }}),
    {code:'ADMISSION_STEP_PROJECTION_FAILED'});
  // Model the exact old source shape even when the candidate adds new
  // pre-dispatch markers to newly reserved attempts.
  const oldRecord = await f.store.get(99);
  delete oldRecord.predispatchPending;
  await f.store.put(99, oldRecord);
  f.run.status='completed'; f.run.conclusion='failure'; f.run.run_attempt=1;
  f.run.updated_at='2026-09-04T12:01:00Z';
  const original=await f.store.get(99), get=f.api.get; const comments=[];
  f.api.get=async path=>path===`/git/ref/heads/${original.envelope.branch}` ? {object:{sha:original.envelope.startHead}}
    : path.startsWith('/issues/comments/') ? comments.find(c=>c.id===Number(path.split('/').at(-1))) : get(path);
  // The historical-runtime fixture models the compatibility boundary below;
  // it deliberately has no live installed Writer or deployment wrapper.
  const broker=createPublicationBroker({api:f.api,store:f.store,publisher:{},journal,checkoutAbsent:async()=>true,
    assertPredispatchFence:async()=>{}});
  const inspect={operation:'predispatch-state',runId:99,attemptId:'run-99'};
  const state=await broker.dispatch(inspect), created_at='2026-09-04T12:02:00Z';
  comments.push({id:10000,user:{login:'example-owner',type:'User'},issue_url:`https://api.github.com/repos/${REPOSITORY}/issues/42`,created_at,updated_at:created_at,body:state.authorizationBody});
  await broker.dispatch({...inspect,operation:'finalize-predispatch',authorizationId:10000});
  const record=await f.store.get(99);
  const gateRoot=await mkdtemp(join(tmpdir(),'relay-230-transition-')); t.after(()=>rm(gateRoot,{recursive:true,force:true}));
  const params={root:gateRoot,consumerDigest:record.envelope.consumerDigest,store:f.store,journal,protectedRoot:false};
  const old=oldControl(params), candidate=createAdmissionControl(params);
  const operationId='12345678-1234-4234-8234-123456789abc', target='b'.repeat(40);
  await old.initialize(); await old.quiesce({operationId,target});
  assert.equal((await old.drained({operationId})).drained,false);
  assert.deepEqual((await old.status()).active,[99]);
  assert.equal((await candidate.drained({operationId})).drained,true);
  assert.equal((await candidate.drained({operationId})).drained,true);
  assert.equal((await candidate.phase({operationId,phase:'applying'})).phase,'applying');
  await candidate.phase({operationId,phase:'verified',revision:target});
  await candidate.resume({operationId});
  assert.equal((await candidate.status()).phase,'open');
  assert.equal(nextAdmissionStep([record],42,[{name:'step-1'}]).step,3);
  await assert.rejects(broker.dispatch(f.admissionRequest),{code:'PREDISPATCH_ATTEMPT_FINALIZED'});
  await journal.put(99,{unexpected:true});
  assert.deepEqual((await candidate.status()).unknown,[99]);
});
