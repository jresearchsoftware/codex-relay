import { CONSUMER_DIGEST } from '../../consumer/consumer.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createOnDemandDispatchAdapter } from '../src/github.mjs';
import { REPOSITORY } from '../src/execution-contract.mjs';
const envelope = { version: 2, consumerDigest: CONSUMER_DIGEST, repository: REPOSITORY, attemptId: 'run-9', step: 2, runId: 9,
  target: 'issue', number: 42, issueNumber: 42, route: 'auto', branch: 'codex/test',
  startHead: 'a'.repeat(40), historicalBase: 'a'.repeat(40), targetBase: 'b'.repeat(40), authorityDigest: 'c'.repeat(64), profile: { cliModelId: 'fixture-model', effort: 'high' }, validation: ['diff-check'] };
function launch(code) {
  return (command, args, options) => {
    assert.equal(command, '/opt/relay-example/relay-codex-dispatch'); assert.deepEqual(args, []);
    assert.equal(options.env.GITHUB_TOKEN, undefined); assert.equal(options.env.workflowReadToken, undefined);
    // Emit deterministic fixture bytes through the actual descriptors. This
    // also works when a sandbox restricts Node's socket-backed stdio wrappers.
    return spawn(process.execPath, ['-e', `const { writeSync } = require('node:fs'); ${code}`], options);
  };
}
test('real bounded dispatcher process returns the same attempt envelope without publication credentials', async () => {
  const dispatcher = createOnDemandDispatchAdapter({ spawnImpl: launch(`const e=JSON.parse(require('node:fs').readFileSync(0,'utf8'));writeSync(1, JSON.stringify({version:e.version,attemptId:e.attemptId,child:'started',result:{status:'blocked'}}));`) });
  const value = await dispatcher.dispatch(envelope);
  assert.equal(value.attemptId, envelope.attemptId); assert.equal(value.containment, 'reaped');
});
test('a failed process with unparseable stderr retains unknown child evidence', async () => {
  const dispatcher = createOnDemandDispatchAdapter({ spawnImpl: launch("process.stdin.resume(); process.stdin.on('end',()=>{writeSync(2, 'non-diagnostic failure');process.exitCode=1;});") });
  await assert.rejects(dispatcher.dispatch(envelope), error => {
    assert.equal(error.details.childState, 'unknown'); assert.equal(error.details.containment, 'reaped'); return true;
  });
});
test('native process timeout is bounded and cannot be relabeled not_started', async () => {
  const dispatcher = createOnDemandDispatchAdapter({ timeoutMs: 100, spawnImpl: launch('process.stdin.resume(); setInterval(()=>{},1000);') });
  await assert.rejects(dispatcher.dispatch(envelope), error => {
    assert.equal(error.code, 'EXECUTION_TIMEOUT'); assert.equal(error.details.childState, 'unknown'); return true;
  });
});
test('an unsupported required validation stops before the process boundary', async () => {
  const dispatcher = createOnDemandDispatchAdapter({ spawnImpl: () => assert.fail('must not start') });
  await assert.rejects(dispatcher.dispatch({ ...envelope, validation: ['custom-unknown-check'] }), { code: 'REQUIRED_VALIDATION_UNSUPPORTED' });
});
test('specific safe worker failure and known cause survive the dispatcher', async () => {
  const dispatcher = createOnDemandDispatchAdapter({ spawnImpl: launch(`process.stdin.resume(); process.stdin.on('end',()=>{writeSync(2, JSON.stringify({version:2,status:'blocked',code:'CODEX_RESULT_MISSING',diagnostic:{observed:{child:'started'},primaryCause:'CODEX_RESULT_MISSING'}}));process.exitCode=1;});`) });
  await assert.rejects(dispatcher.dispatch(envelope), error => {
    assert.equal(error.code, 'CODEX_RESULT_MISSING'); assert.equal(error.details.primaryCause, 'CODEX_RESULT_MISSING');
    assert.equal(error.details.childState, 'started'); assert.equal(error.details.containment, 'reaped'); return true;
  });
});
