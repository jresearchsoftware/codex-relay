import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

const exec = promisify(execFile);
const targets = ['example-org/project-a', 'example-org/project-b'];
const source = name => new URL(`../src/${name}.mjs`, import.meta.url).href;
const consumerSource = new URL('../../consumer/consumer.mjs', import.meta.url).href;
const linux = { skip: process.platform !== 'linux' };
async function fixture(t, { repositories = targets, pool = false } = {}) {
  const root = await mkdtemp(join(tmpdir(), 'relay-multi-writer-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const configuration = JSON.parse(await readFile(new URL('../../consumer/fixtures/example.json', import.meta.url), 'utf8'));
  delete configuration.repository;
  configuration.repositories = repositories;
  configuration.paths.workRoot = join(root, 'work');
  configuration.paths.attemptRoot = join(root, 'journals');
  configuration.paths.claimRoot = join(root, 'claims');
  configuration.paths.diagnosticsRoot = join(root, 'diagnostics');
  if (pool) {
    const { EXECUTION_PATH_NAMES } = await import('../../consumer/consumer-config.mjs');
    configuration.generalRunnerPool = { desiredCapacity: 2 };
    configuration.executionSlots = ['primary', 'pool-2'].map(id => ({
      id, runnerName: `test-${id}`, runnerUser: 'relay-runner', runtimeUser: configuration.runtimeUser,
      workGroup: 'relay-work', paths: Object.fromEntries(EXECUTION_PATH_NAMES.map(name => [name,
        id === 'primary' ? configuration.paths[name] : join(root, id, name)]))
    }));
  }
  const pathname = join(root, 'consumer.json');
  await writeFile(pathname, JSON.stringify(configuration), { mode: 0o600 });
  const env = { ...process.env, RELAY_CONSUMER_CONFIG: pathname };
  for (const name of ['RELAY_REPOSITORY', 'GITHUB_REPOSITORY', 'RELAY_EXECUTION_SLOT', 'RUNNER_NAME']) delete env[name];
  async function run(repository, program) {
    const bootstrap = `import assert from 'node:assert/strict';
      const root = ${JSON.stringify(root)};
      const targets = ${JSON.stringify(repositories)};
      const repository = process.env.RELAY_REPOSITORY;
      ${program}`;
    const result = await exec(process.execPath, ['--input-type=module', '-e', bootstrap], {
      env: { ...env, RELAY_REPOSITORY: repository }, timeout: 60000, maxBuffer: 1024 * 1024 });
    return result.stdout.trim() ? JSON.parse(result.stdout) : null;
  }
  return { root, run };
}

test('installed pool admission classifies a foreign pending checkout without transferring Task authority', linux, async t => {
  const relay = 'example-org/codex-relay';
  const docReview = 'example-org/docs-evolution-review';
  const f = await fixture(t, { repositories: [relay, docReview], pool: true });
  const setup = program => `
    const { mkdir, readFile, rmdir, writeFile, unlink } = await import('node:fs/promises');
    const { CONSUMER, INSTALLATION_CONSUMER, executionConsumer } = await import(${JSON.stringify(consumerSource)});
    const { resolveExecutionConsumer, selectRepositoryConsumer } = await import(${JSON.stringify(new URL('../../consumer/consumer-config.mjs', import.meta.url).href)});
    const { createAttemptStore, createPublicationStore } = await import(${JSON.stringify(source('attempt-store'))});
    const { installedAdmissionControl } = await import(${JSON.stringify(source('admission-cli'))});
    const { createPublicationBroker } = await import(${JSON.stringify(source('publication-broker'))});
    const { createSlotJournal } = await import(${JSON.stringify(source('slot-journal'))});
    const { pendingPredispatchRecord } = await import(${JSON.stringify(source('predispatch-recovery'))});
    const { validateEnvelope } = await import(${JSON.stringify(source('execution-contract'))});
    const { harness } = await import(${JSON.stringify(new URL('./independent-admission-fixture.mjs', import.meta.url).href)});
    const cleanups = [];
    const slot = 'pool-2';
    const storeRoot = CONSUMER.paths.claimRoot + '/publication-v2';
    const docReview = targets[1];
    const paths = resolveExecutionConsumer(selectRepositoryConsumer(INSTALLATION_CONSUMER, docReview), slot).paths;
    const journal = createAttemptStore(paths.attemptRoot, { repository: docReview });
    const store = createPublicationStore(storeRoot);
    const runId = 80;
    const localRunId = 81;
    const task = 42;
    const local = await harness({ after: cleanup => cleanups.push(cleanup) }, {
      store, journal: createSlotJournal(store), executionSlot: slot });
    try {
      ${program}
    } finally { for (const cleanup of cleanups.reverse()) await cleanup(); }`;
  await f.run(docReview, setup(`
    const failure = Object.assign(new Error('Synthetic Step projection failure'), { code: 'EIO' });
    local.api.ensureStepLabel = async () => { throw failure; };
    await assert.rejects(local.broker.dispatch(local.ready(runId, task, 'auto')), { code: 'EIO' });
    const retained = await store.get(runId);
    assert.equal(retained.envelope.repository, docReview);
    assert.equal(retained.envelope.executionSlot, slot);
    assert.equal(pendingPredispatchRecord(retained), true);
    assert.equal(await journal.get(runId), null);
    await mkdir(paths.workRoot, { recursive: true });`));

  await f.run(relay, setup(`
    const gate = installedAdmissionControl();
    const admission = { assertOpen: () => local.control.assertOpen(), reserve: () => local.control.reserve(),
      assertSlotComplete: slot => gate.assertSlotComplete(slot) };
    const broker = createPublicationBroker({ api: local.api, store, publisher: {}, admission, journal: createSlotJournal(store) });
    const request = local.ready(localRunId, task, 'auto');
    const foreignStore = createAttemptStore(storeRoot, { repository: docReview, repositories: targets, namespace: true });
    const retained = await foreignStore.get(runId);
    const foreignPath = storeRoot + '/repositories/' + docReview + '/' + runId + '.json';
    const foreignBytes = await readFile(foreignPath);
    const checkout = paths.workRoot + '/run-' + runId;
    assert.throws(() => validateEnvelope(retained.envelope), { code: 'EXECUTION_ENVELOPE_INVALID' });
    await assert.rejects(broker.dispatch({ ...request, repository: docReview }), { code: 'ATTEMPT_REPOSITORY_MISMATCH' });
    assert.equal(await store.get(runId), null);

    async function unavailable(state) {
      await assert.rejects(broker.dispatch(request), error => {
        assert.equal(error.code, 'EXECUTION_SLOT_UNAVAILABLE');
        assert.equal(error.details.resource, slot);
        assert.deepEqual(error.details.active, state === 'active' ? [runId] : []);
        assert.deepEqual(error.details.unknown, state === 'unknown' ? [runId] : []);
        assert.ok(error.details.pending.some(item => item.runId === runId && item.repository === docReview));
        assert.deepEqual(error.details.slotConflict, { slot, runId, repository: docReview, state });
        return true;
      });
      assert.equal(await store.get(localRunId), null);
      assert.equal(local.deletes(), 0);
    }
    await mkdir(checkout);
    await unavailable('unknown');
    await rmdir(checkout);
    await journal.put(runId, { version: 2, envelope: retained.envelope });
    await unavailable('unknown');
    await unlink(paths.attemptRoot + '/' + runId + '.json');

    const consumed = { ...retained, stepProjected: true, readyConsumed: true,
      readyConsumption: { status: 'consumed', eventId: retained.envelope.readyEventId,
        label: retained.envelope.readyLabel, removalEventId: retained.envelope.readyEventId + 1 } };
    delete consumed.stepProjectionFrom;
    await foreignStore.put(runId, consumed);
    await unavailable('active');
    await writeFile(foreignPath, foreignBytes);

    await rmdir(paths.workRoot);
    await writeFile(paths.workRoot, 'Synthetic non-directory');
    await assert.rejects(broker.dispatch(request), { code: 'ADMISSION_RESOURCE_EVIDENCE_UNREADABLE' });
    assert.equal(await store.get(localRunId), null);
    await unlink(paths.workRoot);
    await mkdir(paths.workRoot);

    const malformed = { ...retained, envelope: { ...retained.envelope, attemptId: 'run-0' } };
    await foreignStore.put(runId, malformed);
    await assert.rejects(broker.dispatch(request), { code: 'EXECUTION_SLOT_UNAVAILABLE' });
    assert.equal(await store.get(localRunId), null);
    await writeFile(foreignPath, foreignBytes);

    await foreignStore.put(runId, { ...retained, envelope: { ...retained.envelope, runId: runId + 2 } });
    await assert.rejects(broker.dispatch(request), { code: 'ADMISSION_ATTEMPT_INVALID' });
    assert.equal(await store.get(localRunId), null);
    await writeFile(foreignPath, foreignBytes);
    await assert.rejects(foreignStore.put(runId, { ...retained, envelope: { ...retained.envelope, repository } }),
      { code: 'ATTEMPT_REPOSITORY_MISMATCH' });

    await foreignStore.put(runId, { ...retained, envelope: { ...retained.envelope, executionSlot: 'pool-unknown' } });
    await assert.rejects(broker.dispatch(request), error => {
      assert.equal(error.code, 'ADMISSION_ATTEMPT_INVALID');
      assert.equal(error.details.conflictingRunId, runId);
      assert.equal(error.details.repository, docReview);
      assert.equal(error.details.cause, 'ADMISSION_RESOURCE_IDENTITY_INVALID');
      return true;
    });
    assert.equal(await store.get(localRunId), null);
    await writeFile(foreignPath, foreignBytes);

    await gate.assertTaskComplete(task);
    await mkdir(executionConsumer(slot).paths.workRoot + '/run-' + runId, { recursive: true });
    await gate.assertSlotComplete(slot);
    const admitted = await broker.dispatch(request);
    assert.equal(admitted.envelope.repository, repository);
    assert.equal(admitted.envelope.runId, localRunId);
    assert.equal(admitted.envelope.executionSlot, slot);
    assert.equal(admitted.envelope.step, 1);
    assert.equal(local.deletes(), 1);
    assert.deepEqual(await readFile(foreignPath), foreignBytes);
    assert.equal(await journal.get(runId), null);`));
});

test('same run and Task numbers retain separate records, journals and Step lineage while sharing slot admission', linux, async t => {
  const f = await fixture(t);
  const setup = `
    const { CONSUMER, CONSUMER_DIGEST } = await import(${JSON.stringify(consumerSource)});
    const { createAttemptStore, createPublicationStore } = await import(${JSON.stringify(source('attempt-store'))});
    const { createAdmissionControl } = await import(${JSON.stringify(source('admission-control'))});
    const { createSlotJournal } = await import(${JSON.stringify(source('slot-journal'))});
    const { nextAdmissionStep } = await import(${JSON.stringify(source('admission-step'))});
    const store = createPublicationStore(root + '/publication');
    const journal = createAttemptStore(CONSUMER.paths.attemptRoot);
    const gate = createAdmissionControl({ root, consumerDigest: CONSUMER_DIGEST, store,
      journal: createSlotJournal(store), protectedRoot: false });
    await gate.initialize();`;
  for (const [index, repository] of targets.entries()) {
    await f.run(repository, setup + `
      await gate.assertTaskComplete(42);
      assert.equal(nextAdmissionStep(await store.all(), 42).step, 1);
      ${index === 1 ? "await assert.rejects(gate.assertSlotComplete('primary'), { code: 'EXECUTION_SLOT_UNAVAILABLE' });" : "await gate.assertSlotComplete('primary');"}
      const record = { envelope: { version: 2, repository, consumerDigest: CONSUMER_DIGEST,
        runId: 99, attemptId: 'run-99', issueNumber: 42, step: ${index === 0 ? 7 : 3}, route: 'auto' },
        controllerLifecycle: { version: 1, status: 'active' } };
      assert.equal(await store.reserve(99, record), true);
      assert.equal(await store.reserve(99, record), false);
      await journal.put(99, { ...record, marker: repository });
      assert.equal((await createSlotJournal(store).get(99)).marker, repository);
      await assert.rejects(gate.assertTaskComplete(42), { code: 'PRIOR_EXECUTION_UNRESOLVED' });`);
  }
  for (const [index, repository] of targets.entries()) {
    await f.run(repository, setup + `
      const rows = await store.all();
      assert.equal(rows.length, 2);
      assert.deepEqual(rows.map(row => row.envelope.repository).sort(), targets);
      for (const target of targets) assert.equal((await createSlotJournal(store).get(99, target)).marker, target);
      const record = await store.get(99);
      assert.equal(record.envelope.repository, repository);
      assert.equal(record.envelope.step, ${index === 0 ? 7 : 3});
      record.outcome = { status: 'BLOCKED', head: null, prNumber: null, outcomeId: 1 };
      record.controllerLifecycle = { version: 1, status: 'complete', child: 'not_started', containment: 'not_required' };
      await store.put(99, record);
      const next = nextAdmissionStep(await store.all(), 42);
      assert.equal(next.step, ${index === 0 ? 8 : 4});
      assert.equal(next.lineage.step, record.envelope.step);
      await assert.rejects(store.put(99, { envelope: { repository: targets.find(target => target !== repository) } }),
        { code: 'ATTEMPT_REPOSITORY_MISMATCH' });`);
  }
  await f.run(targets[0], setup + `await gate.assertSlotComplete('primary'); assert.deepEqual((await gate.status()).active, []);`);
});

test('request bootstrap rejects an unconfigured target before any Writer credential or network operation', linux, async t => {
  const f = await fixture(t);
  await f.run(targets[0], `
    const { Readable } = await import('node:stream');
    const { readRepositoryRequest } = await import(${JSON.stringify(source('repository-entrypoint'))});
    const env = { ...process.env };
    let credentialsReached = false;
    const guardedWriter = async request => {
      await readRepositoryRequest({ env, input: Readable.from([JSON.stringify(request)]), limit: 1024 });
      credentialsReached = true;
    };
    for (const repository of ['foreign/project', '../project', undefined]) {
      await assert.rejects(guardedWriter({ repository, operation: 'publication-state', runId: 99 }),
        { code: 'CONSUMER_CONFIG_INVALID' });
      assert.equal(credentialsReached, false);
      assert.equal(env.RELAY_REPOSITORY, targets[0]);
    }
    await guardedWriter({ repository: targets[1], operation: 'publication-state', runId: 99 });
    assert.equal(credentialsReached, true);
    assert.equal(env.RELAY_REPOSITORY, targets[1]);`);
});

test('one configured Writer identity targets each repository for publication and recovery and rejects foreign receipts', linux, async t => {
  const f = await fixture(t);
  const identities = [];
  for (const repository of targets) identities.push(await f.run(repository, `
    const { EventEmitter } = await import('node:events');
    const { PassThrough } = await import('node:stream');
    const { CONSUMER } = await import(${JSON.stringify(consumerSource)});
    const { createLocalWriterAdapter } = await import(${JSON.stringify(source('local-writer'))});
    const { createGithubApi } = await import(${JSON.stringify(source('github-api'))});
    const credentialEnv = 'GITHUB_APP_ID=' + CONSUMER.writerApp.appId + '\\nGITHUB_APP_INSTALLATION_ID='
      + CONSUMER.writerApp.installationId + '\\nGITHUB_APP_PRIVATE_KEY_FILE=' + CONSUMER.paths.credentialKeyFile,
      { default: filesystem } = await import('node:fs/promises');
    const { syncBuiltinESMExports } = await import('node:module');
    const { generateKeyPairSync } = await import('node:crypto');
    const { privateKey } = generateKeyPairSync('rsa', { modulusLength: 2048,
      privateKeyEncoding: { type: 'pkcs8', format: 'pem' }, publicKeyEncoding: { type: 'spki', format: 'pem' } });
    const originalRead = filesystem.readFile, originalStat = filesystem.stat, originalFetch = globalThis.fetch;
    let tokenRequest;
    try {
      // Synthetic credentials only: unexpected filesystem/network access fails
      // before a real credential or network transport can be consulted.
      filesystem.readFile = async path => {
        if (path === CONSUMER.paths.credentialEnv) return credentialEnv;
        if (path === CONSUMER.paths.credentialKeyFile) return privateKey;
        assert.fail('Unexpected credential read');
      };
      filesystem.stat = async path => {
        assert.ok([CONSUMER.paths.credentialEnv, CONSUMER.paths.credentialKeyFile].includes(path));
        return { uid: 0, mode: 0o600 };
      };
      syncBuiltinESMExports();
      globalThis.fetch = async (url, options) => {
        tokenRequest = { url, options };
        return { ok: true, text: async () => JSON.stringify({ token: 'synthetic-issued-token',
          expires_at: new Date(Date.now() + 3600000).toISOString() }) };
      };
      const { token, WRITER_TOKEN_PERMISSIONS } = await import(${JSON.stringify(source('writer-auth'))});
      assert.equal(await token(), 'synthetic-issued-token');
      assert.equal(tokenRequest.url, 'https://api.github.com/app/installations/' + CONSUMER.writerApp.installationId + '/access_tokens');
      assert.deepEqual(JSON.parse(tokenRequest.options.body), { repositories: [repository.split('/')[1]], permissions: WRITER_TOKEN_PERMISSIONS });
      const jwt = tokenRequest.options.headers.authorization.slice('Bearer '.length);
      assert.equal(JSON.parse(Buffer.from(jwt.split('.')[1], 'base64url')).iss, CONSUMER.writerApp.appId);
    } finally {
      filesystem.readFile = originalRead; filesystem.stat = originalStat; globalThis.fetch = originalFetch;
      syncBuiltinESMExports();
    }
    const requests = []; let wrongReceipt = false;
    const adapter = createLocalWriterAdapter({ spawnImpl: (command, args, options) => {
      assert.equal(args.at(-1), CONSUMER.paths.writerHelper);
      assert.equal(options.env.RELAY_REPOSITORY, undefined);
      const child = new EventEmitter();
      child.stdout = new PassThrough(); child.stderr = new PassThrough(); child.stdin = new PassThrough();
      child.stdin.on('data', bytes => {
        const request = JSON.parse(bytes); requests.push(request);
        process.nextTick(() => {
          child.stdout.write(JSON.stringify({ repository: wrongReceipt ? targets.find(value => value !== repository) : repository }));
          child.emit('close', 0);
        });
      });
      return child;
    } });
    for (const operation of ['admit', 'publish-progress', 'publication-state', 'recover-publication', 'complete-handoff']) {
      await adapter.invoke({ operation, runId: 99, attemptId: 'run-99' });
      assert.equal(requests.at(-1).repository, repository);
    }
    const count = requests.length;
    await assert.rejects(adapter.invoke({ operation: 'publication-state', repository: 'foreign/project', runId: 99 }),
      { code: 'WRITER_REPOSITORY_INVALID' });
    assert.equal(requests.length, count);
    wrongReceipt = true;
    await assert.rejects(adapter.invoke({ operation: 'recover-publication', runId: 99 }), { code: 'WRITER_RECEIPT_INVALID' });
    const paths = [];
    const api = createGithubApi({ token: 'synthetic-writer-token', runToken: 'synthetic-run-token', fetchImpl: async (url, options) => {
      paths.push({ url, authorization: options.headers.authorization });
      return { ok: true, status: 200, json: async () => ({}) };
    } });
    await api.post('/issues/42/comments', { body: 'Synthetic canonical Outcome.' });
    await api.get('/pulls/43'); await api.getRun(99);
    assert.ok(paths.every(value => value.url.startsWith('https://api.github.com/repos/' + repository + '/')));
    assert.equal(paths[0].authorization, 'Bearer synthetic-writer-token');
    assert.equal(paths[2].authorization, 'Bearer synthetic-run-token');
    console.log(JSON.stringify({ app: CONSUMER.writerApp, identity: CONSUMER.writerIdentity,
      helper: CONSUMER.paths.writerHelper, credentials: CONSUMER.paths.credentialEnv }));`));
  assert.deepEqual(identities[0], identities[1]);
});

test('canonical no-change publication and recovery-state inspection keep the selected repository identity', linux, async t => {
  const f = await fixture(t);
  for (const repository of targets) await f.run(repository, `
    const cleanups = [];
    const { fixture } = await import(${JSON.stringify(new URL('./fixture.mjs', import.meta.url).href)});
    const { runAttempt } = await import(${JSON.stringify(source('attempt'))});
    const { extractAuthorityRecord } = await import(${JSON.stringify(new URL('../../contracts/src/github-authority.mjs', import.meta.url).href)});
    try {
      const f = await fixture({ after: action => cleanups.push(action) }, { route: 'auto',
        issueBody: 'Authority model: github-native-v1\\nIssue closure policy: keep-open\\nVerify that no source change is required.',
        labelLaunch: true, streamlinedAdmission: true });
      const result = await runAttempt({ ...f, execute: async () => ({ version: 2, attemptId: f.envelope.attemptId,
        child: 'started', containment: 'reaped', result: { status: 'success', summary: 'No source change was required.', validation: [] } }) });
      assert.equal(result.repository, repository);
      assert.equal(result.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
      assert.equal(f.pushes(), 0);
      assert.equal(f.comments.length, 1);
      const record = extractAuthorityRecord(f.comments[0].body);
      assert.equal(record.repository, repository);
      assert.equal(record.task, 42);
      const state = await f.broker.invoke({ operation: 'publication-state', runId: 99, attemptId: f.envelope.attemptId });
      assert.equal(state.repository, repository);
      await runAttempt({ ...f, admissionResumed: true, execute: () => assert.fail('publication replay launched execution') });
      assert.equal(f.comments.length, 1);
    } finally { for (const cleanup of cleanups.reverse()) await cleanup(); }`);
});

test('legacy direct numeric state stays visible across every namespaced read and mutation boundary', linux, async t => {
  const f = await fixture(t);
  // Materialize both current namespaces before old direct numeric state appears;
  // a store object created earlier must recheck the boundary on every operation.
  for (const repository of targets) await f.run(repository, `
    const { createPublicationStore } = await import(${JSON.stringify(source('attempt-store'))});
    const store = createPublicationStore(root + '/mixed');
    assert.equal(await store.reserve(99, { envelope: { repository, runId: 99 }, marker: repository }), true);`);
  await f.run(targets[0], `
    const { readFile, readdir } = await import('node:fs/promises');
    const { createAttemptStore, createPublicationStore } = await import(${JSON.stringify(source('attempt-store'))});
    const store = createPublicationStore(root + '/mixed');
    assert.equal((await store.all()).length, 2);
    const retained = { envelope: { repository, runId: 99 }, marker: 'retained-singleton-history' };
    await createAttemptStore(root + '/mixed').put(99, retained);
    const paths = [root + '/mixed/99.json', ...targets.map(target => root + '/mixed/repositories/' + target + '/99.json')];
    const original = await Promise.all(paths.map(path => readFile(path, 'utf8')));
    for (const action of [
      () => store.get(99), () => store.get(100), () => store.get(99, targets[1]),
      () => store.put(99, { envelope: { repository, runId: 99 }, marker: 'overwrite' }),
      () => store.put(100, { envelope: { repository, runId: 100 } }),
      () => store.reserve(99, { envelope: { repository, runId: 99 } }),
      () => store.reserve(100, { envelope: { repository, runId: 100 } }),
      () => store.all(), () => store.withLock(100, () => assert.fail('legacy state must block before entering the lock'))
    ]) await assert.rejects(action(), { code: 'CONSUMER_CONFIG_CHANGED' });
    assert.deepEqual(await Promise.all(paths.map(path => readFile(path, 'utf8'))), original);
    for (const target of targets) assert.deepEqual(await readdir(root + '/mixed/repositories/' + target), ['99.json']);
    assert.deepEqual(await createAttemptStore(root + '/mixed').get(99), retained);`);
  // A second process/selected repository must observe the same retained stop,
  // rather than creating an independent successful namespace beside history.
  await f.run(targets[1], `
    const { createPublicationStore } = await import(${JSON.stringify(source('attempt-store'))});
    const store = createPublicationStore(root + '/mixed');
    for (const action of [() => store.get(99), () => store.all(),
      () => store.put(100, { envelope: { repository, runId: 100 } }),
      () => store.reserve(100, { envelope: { repository, runId: 100 } })])
      await assert.rejects(action(), { code: 'CONSUMER_CONFIG_CHANGED' });`);
});

test('diagnostic transport preserves the selected target, isolates equal execution IDs and rejects an unconfigured sink target', linux, async t => {
  const f = await fixture(t);
  for (const repository of targets) await f.run(repository, `
    const { EventEmitter } = await import('node:events');
    const { PassThrough, Readable } = await import('node:stream');
    const { readFile } = await import('node:fs/promises');
    const { CONSUMER } = await import(${JSON.stringify(consumerSource)});
    const { persistExecutionDiagnostic } = await import(${JSON.stringify(source('diagnostics'))});
    const { readRepositoryRequest } = await import(${JSON.stringify(source('repository-entrypoint'))});
    const { writeDiagnosticBundle } = await import(${JSON.stringify(source('diagnostic-store'))});
    const env = { ...process.env };
    let stored = 0;
    async function sink(bytes) {
      const selected = await readRepositoryRequest({ env, input: Readable.from([bytes]), limit: 16 * 1024 * 1024 });
      assert.equal(selected.repository, repository);
      const result = await writeDiagnosticBundle(selected);
      stored++;
      return result;
    }
    const diagnostic = { schemaVersion: '1.0', executionId: 'run-99', mode: 'normal',
      marker: repository, repository: 'foreign/project' };
    const before = structuredClone(diagnostic);
    await persistExecutionDiagnostic(diagnostic, { spawnImpl: (command, args, options) => {
      assert.equal(command, '/usr/bin/sudo');
      assert.deepEqual(args, ['-n', CONSUMER.paths.diagnosticsStore]);
      assert.equal(options.env.RELAY_REPOSITORY, undefined);
      const child = new EventEmitter();
      child.stdout = new PassThrough(); child.stderr = new PassThrough(); child.stdin = new PassThrough();
      child.stdin.on('data', bytes => process.nextTick(async () => {
        try { child.stdout.write(JSON.stringify(await sink(bytes))); child.emit('close', 0); }
        catch (error) { child.stderr.write(JSON.stringify({ code: error.code })); child.emit('close', 1); }
      }));
      return child;
    } });
    assert.equal(stored, 1);
    assert.deepEqual(diagnostic, before);
    const bytes = await readFile(CONSUMER.paths.diagnosticsRoot + '/run-99.json', 'utf8');
    const record = JSON.parse(bytes);
    assert.equal(record.repository, repository);
    assert.equal(record.marker, repository);
    await assert.rejects(sink(JSON.stringify({ ...diagnostic, repository: 'foreign/project' })),
      { code: 'CONSUMER_CONFIG_INVALID' });
    assert.equal(stored, 1);
    assert.equal(await readFile(CONSUMER.paths.diagnosticsRoot + '/run-99.json', 'utf8'), bytes);`);
  // Read both durable results after the second write to detect a hidden
  // last-writer-wins collision at the shared installation's sink path.
  await f.run(targets[0], `
    const { readFile } = await import('node:fs/promises');
    for (const target of targets) {
      const record = JSON.parse(await readFile(root + '/diagnostics/repositories/' + target + '/run-99.json', 'utf8'));
      assert.equal(record.repository, target); assert.equal(record.marker, target);
    }`);
});
