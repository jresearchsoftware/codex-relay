import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { CONSUMER } from '../../consumer/consumer.mjs';
import { EXECUTION_PATH_NAMES } from '../../consumer/consumer-config.mjs';

test('execution and cleanup select only the frozen installation work group, including secondary slots', async t => {
  const root = await mkdtemp(join(tmpdir(), 'relay-launch-group-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const original = structuredClone(CONSUMER);
  delete original.executionSlots; delete original.generalRunnerPool; delete original.workGroup;
  const serial = { ...original, workGroup: 'shared-work' };
  const slotted = { ...serial, executionSlots: [
    { id: 'primary', runnerName: 'sample-primary', runnerUser: 'sample-runner', runtimeUser: serial.runtimeUser,
      workGroup: serial.workGroup, paths: Object.fromEntries(EXECUTION_PATH_NAMES.map(name => [name, serial.paths[name]])) },
    { id: 'second', runnerName: 'sample-second', runnerUser: 'second-runner', runtimeUser: 'second-worker', workGroup: 'second-work',
      paths: Object.fromEntries(EXECUTION_PATH_NAMES.map(name => [name, `/var/lib/second-slot/${name}`])) }
  ] };
  const script = `import { EventEmitter } from 'node:events';
import { PassThrough } from 'node:stream';
import { buildCodexProcessSpec } from ${JSON.stringify(new URL('../src/codex-process.mjs', import.meta.url).href)};
import { cleanupCodexSandbox } from ${JSON.stringify(new URL('../src/sandbox-cleanup.mjs', import.meta.url).href)};
let cleanup;
await cleanupCodexSandbox({ cwd: '/synthetic/run-171', sandboxIdentity: { device: '1', inode: '2' }, spawnImpl(command,args) {
  cleanup={command,args}; const child=new EventEmitter(); child.stdout=new PassThrough(); child.stderr=new PassThrough();
  setImmediate(()=>{ child.stdout.end('{"schemaVersion":1,"status":"removed"}'); child.emit('close',0); }); return child;
} });
console.log(JSON.stringify({ exec: buildCodexProcessSpec({args:['exec']}), cleanup }));`;
  for (const [consumer, slot, group, user] of [
    [original, undefined, undefined, original.runtimeUser],
    [serial, undefined, 'shared-work', serial.runtimeUser],
    [slotted, 'second', 'second-work', 'second-worker']
  ]) {
    const config = join(root, 'consumer.json'); await writeFile(config, JSON.stringify(consumer), { mode: 0o600 });
    const env = { ...process.env, RELAY_CONSUMER_CONFIG: config };
    delete env.RELAY_EXECUTION_SLOT; delete env.RUNNER_NAME;
    if (slot) env.RELAY_EXECUTION_SLOT = slot;
    const child = spawnSync(process.execPath, ['--input-type=module', '-e', script], { env, encoding: 'utf8' });
    assert.equal(child.status, 0, child.stderr);
    const result = JSON.parse(child.stdout);
    for (const spec of [result.exec, result.cleanup]) {
      assert.equal(spec.command, '/usr/bin/sudo'); assert.deepEqual(spec.args.slice(0, 3), ['-n', '-u', user]);
      if (group) assert.deepEqual(spec.args.slice(3, 5), ['-g', group]);
      else assert.ok(!spec.args.includes('-g'));
    }
    assert.equal(result.cleanup.args.at(-5), 'cleanup');
  }
});
