import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtemp, mkdir, readFile, rm, stat, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { runGovernedCodexTask } from '../src/codex-runtime.mjs';
import { finalizeRuntimeArtifacts } from '../src/runtime-finalization.mjs';
import { reserveRuntimeDiagnostic } from '../../controller/src/diagnostic-fallback.mjs';
import { writeDiagnosticBundle } from '../../controller/src/diagnostic-store.mjs';

async function readWhenReady(pathname) {
  const deadline = Date.now() + 5000;
  while (Date.now() < deadline) {
    try { return JSON.parse(await readFile(pathname, 'utf8')); }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
    await new Promise(resolve => setTimeout(resolve, 10));
  }
  throw new Error('Synthetic child did not become ready');
}

// Actual same-UID Linux processes exercise the runtime's separate state and
// lifetime pipes. The synthetic launcher is deliberate: this is not evidence
// of installed sudo/Bubblewrap, GitHub scheduling or real model execution.
test('same-UID overlapping runtimes isolate state and cancellation/finalization to their own attempt',
  { skip: process.platform !== 'linux' }, async t => {
    const root = await mkdtemp(join(tmpdir(), 'relay-shared-uid-'));
    const children = [];
    t.after(async () => {
      for (const child of children) if (child.exitCode === null) child.kill('SIGKILL');
      await rm(root, { recursive: true, force: true });
    });
    const workRoot = join(root, 'work');
    const fallbackRoot = join(root, 'fallback');
    const diagnosticRoot = join(root, 'diagnostics');
    const script = join(root, 'synthetic-launcher.mjs');
    await writeFile(script, `
      import { readFileSync, writeFileSync, writeSync } from 'node:fs';
      import { join } from 'node:path';
      const id = readFileSync(process.env.CODEX_ALLOWED_INPUT_ROOT + '/task-input.md', 'utf8').split('\\n')[0];
      const names = ['HOME','CODEX_HOME','XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_DATA_HOME','XDG_STATE_HOME','TMPDIR'];
      const roots = Object.fromEntries(names.map(name => [name, process.env[name]]));
      for (const path of new Set(Object.values(roots))) writeFileSync(join(path, 'same-name-state'), id);
      process.stdin.resume();
      let stopped = false;
      const hold = setInterval(() => {
        try { readFileSync(join(process.env.TMPDIR, 'complete')); stop(false); } catch {}
      }, 10);
      function stop(cancelled) {
        if (stopped) return; stopped = true; clearInterval(hold);
        const result = {status:'success',summary:id,validation:[],blockedReason:''};
        if (!cancelled) writeSync(1, JSON.stringify({type:'task_result',result})+'\\n');
        writeSync(2, JSON.stringify({source:'relay-codex-launcher',schemaVersion:1,
          code:cancelled?'EXECUTION_CANCELLED':'CODEX_EXIT_OK',bytes:0,preview:'',
          childStarted:true,childExitCode:cancelled?1:0,containment:'reaped'})+'\\n');
        process.stdin.destroy(); process.exitCode = cancelled ? 1 : 0;
      }
      process.stdin.on('end', () => stop(true));
      process.on('SIGTERM', () => stop(true));
      writeFileSync(join(process.env.TMPDIR, 'ready'), JSON.stringify({id,pid:process.pid,uid:process.getuid(),roots,
        githubToken:process.env.GITHUB_TOKEN??null,sshAgent:process.env.SSH_AUTH_SOCK??null}));
    `);
    const diagnosticStore = value => writeDiagnosticBundle(value, { root: diagnosticRoot });
    const make = async runId => {
      const attemptId = `run-${runId}`;
      const cwd = join(workRoot, attemptId); await mkdir(cwd, { recursive: true });
      const capsule = await reserveRuntimeDiagnostic({ executionId: attemptId, root: fallbackRoot });
      const cancellation = new AbortController(); const evidence = {};
      const promise = runGovernedCodexTask({ attemptId, cwd, inputText: attemptId,
        buildArgs: () => [], existingFallback: true, openFallback: async () => capsule,
        readDiagnosticConfig: async () => ({ mode: 'normal' }), diagnosticStore,
        env: { PATH: process.env.PATH, GITHUB_TOKEN: 'synthetic-excluded', SSH_AUTH_SOCK: '/synthetic-excluded' },
        signal: cancellation.signal, evidence, spawnImpl(command, args, options) {
          assert.equal(command, '/usr/bin/sudo');
          const child = spawn(process.execPath, [script], options); children.push(child); return child;
        } });
      // Install rejection handling immediately, before waiting for either child.
      const result = promise.then(value => ({ value }), error => ({ error }));
      return { attemptId, cwd, capsule, cancellation, evidence, result,
        readyPath: join(cwd, '.codex-sandbox/tmp/ready') };
    };
    const [left, right] = await Promise.all([make(101), make(102)]);
    const [a, b] = await Promise.all([readWhenReady(left.readyPath), readWhenReady(right.readyPath)]);
    assert.equal(a.uid, b.uid); assert.equal(a.uid, process.getuid()); assert.notEqual(a.pid, b.pid);
    process.kill(a.pid, 0); process.kill(b.pid, 0);
    for (const key of Object.keys(a.roots)) {
      assert.notEqual(a.roots[key], b.roots[key]);
      assert.equal(await readFile(join(a.roots[key], 'same-name-state'), 'utf8'), left.attemptId);
      assert.equal(await readFile(join(b.roots[key], 'same-name-state'), 'utf8'), right.attemptId);
    }
    assert.equal(a.githubToken, null); assert.equal(b.githubToken, null);
    assert.equal(a.sshAgent, null); assert.equal(b.sshAgent, null);
    left.cancellation.abort();
    assert.equal((await left.result).error.code, 'EXECUTION_CANCELLED');
    assert.equal(left.evidence.codexContainment, 'reaped');
    assert.throws(() => process.kill(a.pid, 0), { code: 'ESRCH' });
    process.kill(b.pid, 0);
    assert.equal((await right.capsule.read()).operation, 'launcher-spawn');
    const leftDiagnostic = JSON.parse(await readFile(join(diagnosticRoot, `${left.attemptId}.json`), 'utf8'));
    assert.equal(leftDiagnostic.executionId, left.attemptId);
    await finalizeRuntimeArtifacts({ executionId: left.attemptId, containment: 'reaped',
      fallbackStore: left.capsule, workRoot, diagnosticStore, failure: { code: 'EXECUTION_CANCELLED' },
      cleanupSandbox: async ({ cwd }) => { assert.equal(cwd, left.cwd); await rm(join(cwd, '.codex-sandbox'), { recursive: true }); } });
    assert.ok((await stat(join(right.cwd, '.codex-sandbox'))).isDirectory());
    process.kill(b.pid, 0);
    await writeFile(join(b.roots.TMPDIR, 'complete'), 'done');
    const finished = await right.result;
    assert.equal(finished.error, undefined); assert.equal(finished.value.summary, right.attemptId);
    assert.equal(right.evidence.codexContainment, 'reaped');
    assert.equal((await left.capsule.read()).executionId, left.attemptId);
    assert.equal((await right.capsule.read()).executionId, right.attemptId);
  });
