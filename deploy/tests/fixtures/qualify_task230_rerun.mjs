// Isolated TEST evidence only: synthetic GitHub/worker, real installed stores and gate.
import assert from 'node:assert/strict';
import { readFile, writeFile, readdir } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
import { CONSUMER, EXECUTION_CONSUMER } from '../../../consumer/consumer.mjs';
import { createAttemptStore, createPublicationStore } from '../../../controller/src/attempt-store.mjs';
import { installedAdmissionControl } from '../../../controller/src/admission-cli.mjs';
import { completedAdmissionRecord } from '../../../controller/src/admission-control.mjs';
import { completedPredispatchRecovery } from '../../../controller/src/predispatch-recovery.mjs';
import { exerciseAutomaticRerun } from '../../../controller/test/independent-admission-scenario.mjs';

assert.equal(process.getuid(), 0);
assert.ok(process.argv.includes('--isolated-disposable-container'));
await readFile('/.dockerenv');
assert.deepEqual(await readdir('/sys/class/net'), ['lo']);
assert.ok(process.env.RELAY_CONSUMER_CONFIG?.startsWith('/etc/'));
const expectedRevision = process.argv[process.argv.indexOf('--expected-revision') + 1];
assert.match(expectedRevision ?? '', /^[a-f0-9]{40}$/);
const sourceRevision = execFileSync('git', ['-C', fileURLToPath(new URL('../../../', import.meta.url)),
  'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
assert.equal(sourceRevision, expectedRevision);
const reportPath = '/qualification/task230-rerun-evidence.json';
if (!process.argv.includes('--under-writer-lock')) {
  const output = execFileSync('/usr/bin/flock', ['-w', '10', `${CONSUMER.paths.claimRoot}/publication-v2.lock`,
    process.execPath, fileURLToPath(import.meta.url), ...process.argv.slice(2), '--under-writer-lock'],
  { encoding: 'utf8', env: process.env });
  process.stdout.write(output);
} else {
  const hash = bytes => createHash('sha256').update(bytes).digest('hex');
  if (process.argv.includes('--verify-preserved')) {
    const report = JSON.parse(await readFile(reportPath, 'utf8'));
    for (const item of report.files) assert.equal(hash(await readFile(item.path)), item.sha256, item.path);
    console.log('TASK230_RERUN_HISTORY_PRESERVED=PASS');
  } else {
    const store = createPublicationStore(`${CONSUMER.paths.claimRoot}/publication-v2`);
    const journal = createAttemptStore(EXECUTION_CONSUMER.paths.attemptRoot);
    for (const id of [99, 100]) {
      assert.equal(await store.get(id), null, 'Never replace retained publication history');
      assert.equal(await journal.get(id), null, 'Never replace retained execution history');
    }
    const cleanup = [];
    let result;
    try {
      result = await exerciseAutomaticRerun({ after: action => cleanup.push(action) }, {
        store, journal, admission: installedAdmissionControl(),
        executionSlot: CONSUMER.executionSlots ? 'primary' : undefined, quiesce: false
      });
      assert.ok(completedPredispatchRecovery(await store.get(99)));
      assert.ok(await completedAdmissionRecord(await store.get(100), journal));
      const status = await installedAdmissionControl().status();
      assert.deepEqual(status.active, []);
      assert.deepEqual(status.unknown, []);
      const files = [];
      async function collect(root) {
        for (const entry of await readdir(root, { withFileTypes: true })) {
          const path = join(root, entry.name);
          if (entry.isDirectory()) await collect(path);
          else if (/^(99|100)\.json$/.test(entry.name)) files.push({ path, sha256: hash(await readFile(path)) });
        }
      }
      await collect(`${CONSUMER.paths.claimRoot}/publication-v2`);
      await collect(EXECUTION_CONSUMER.paths.attemptRoot);
      assert.equal(files.length, 3);
      await writeFile(reportPath, JSON.stringify({ sourceRevision, files, workers: result.workers, network: 'none',
        substitutions: ['GitHub API observations', 'contained worker result'], status }, null, 2) + '\n');
      console.log('TASK230_INSTALLED_RERUN_PAIR=PASS;workers=1;records=2;journals=1;network=none');
    } finally {
      for (const action of cleanup.reverse()) await action();
    }
  }
}
