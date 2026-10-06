import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdir, writeFile, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { fixture, memoryStore } from './fixture.mjs';
import { runAttempt } from '../src/attempt.mjs';
import { reportRoutingResult } from '../src/entrypoint.mjs';
import { safeDomainTerminal } from '../src/execution-contract.mjs';

const failure = (code, details) => Object.assign(new Error(code), { code, details });
const result = (e, status = 'blocked') => ({ version: e.version, attemptId: e.attemptId,
  child: 'started', containment: 'reaped', result: { status } });
const report = run => reportRoutingResult(run, { write() {}, writeError() {} });

for (const progress of [false, true]) {
  test(`safe worker BLOCKED ${progress ? 'with published progress' : 'without progress'} stays green on replay`, async t => {
    const f = await fixture(t); const journal = f.journal; let executions = 0;
    const args = { ...f, journal, execute: async () => { executions++; if (progress) await f.commit(); return result(f.envelope); } };
    assert.equal(await report(() => runAttempt(args)), 0);
    const saved = await journal.get(99);
    assert.equal(saved.diagnostic.orchestration, 'COMPLETED');
    if (progress) assert.equal((await f.api.get('/pulls/43')).draft, true);
    assert.equal(await report(() => runAttempt({ ...args,
      prepare: () => assert.fail('reprepare'), collect: () => assert.fail('recollect') })), 0);
    assert.equal(executions, 1); assert.equal(f.pushes(), progress ? 1 : 0); assert.equal(f.comments.length, 1);
  });
}

for (const code of ['CODEX_RESULT_MISSING', 'CODEX_RESULT_INVALID', 'CODEX_JSON_INVALID', 'CODEX_NONZERO_EXIT', 'CODEX_OUTPUT_TOO_LARGE', 'CODEX_RUNTIME_TIMEOUT']) {
  test(`known contained worker ${code} preserves progress once and terminalizes non-red`, async t => {
    const f = await fixture(t); const journal = f.journal;
    const args = { ...f, journal, execute: async () => {
      await f.commit(); throw failure(code, { childState: 'started', containment: 'reaped' });
    } };
    assert.equal(await report(() => runAttempt(args)), 0);
    assert.equal(await report(() => runAttempt(args)), 0);
    assert.equal((await journal.get(99)).outcome.status, 'BLOCKED');
    assert.equal(f.pushes(), 1); assert.equal(f.comments.length, 1);
    assert.equal((await f.api.get('/pulls/43')).draft, true);
  });
}

for (const code of ['INTERNAL_FAILURE', 'DISPATCH_NOT_STARTED', 'PROCESS_START_FAILED', 'WRITER_HELPER_TIMEOUT', 'TRUSTED_GIT_FAILED']) {
  test(`physical ${code} stays red even with known containment and a published Outcome`, async t => {
    const f = await fixture(t); const journal = f.journal;
    const args = { ...f, journal, execute: async () => { throw failure(code, { childState: 'not_started', containment: 'not_required' }); } };
    assert.equal(await report(() => runAttempt(args)), 1);
    assert.equal(await report(() => runAttempt(args)), 1);
    assert.equal(f.comments.length, 1);
  });
}

test('blocked remediation is draft, including a no-progress result', async t => {
  const f = await fixture(t, { remediation: true });
  assert.equal(await report(() => runAttempt({ ...f, journal: f.journal, execute: async () => result(f.envelope) })), 0);
  assert.equal((await f.api.get('/pulls/43')).draft, true);
});

for (const committed of [false, true]) {
  test(`uncommitted work remains a physical preservation failure with ${committed ? 'some' : 'no'} commits`, async t => {
    const f = await fixture(t);
    assert.equal(await report(() => runAttempt({ ...f, journal: f.journal, execute: async () => {
      if (committed) await f.commit();
      await writeFile(join(f.cwd, 'docs/work.md'), 'unsaved task work\n'); return result(f.envelope);
    } })), 1);
    assert.equal(await readFile(join(f.cwd, 'docs/work.md'), 'utf8'), 'unsaved task work\n');
    assert.equal(f.pushes(), committed ? 1 : 0);
  });
}

test('contained successful handoff with generated residue stays green with a durable actionable warning on replay', async t => {
  const f = await fixture(t); const journal = f.journal; let executions = 0; let returned;
  const residue = join(f.cwd, '__pycache__/generated.pyc');
  const stdout = []; const warnings = [];
  const reporting = { write: text => stdout.push(text), writeError: text => warnings.push(text) };
  const args = { ...f, journal, execute: async () => {
    executions++; await f.commit();
    await mkdir(join(f.cwd, '__pycache__'));
    await writeFile(residue, 'generated local validation cache\n');
    return result(f.envelope, 'success');
  } };
  assert.equal(await reportRoutingResult(async () => { returned = await runAttempt(args); return returned; }, reporting), 0);
  assert.equal(returned.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
  assert.deepEqual(returned.executionWarnings, ['UNCOMMITTED_WORK_REMAINS']);
  assert.deepEqual((await journal.get(99)).outcome, { ...returned, draft: true });
  assert.deepEqual((await f.store.get(99)).outcome.executionWarnings, ['UNCOMMITTED_WORK_REMAINS']);
  assert.equal((await journal.get(99)).collection.clean, false);
  assert.equal((await f.api.get('/pulls/43')).draft, false);
  assert.match(f.comments[0].body, /Completion: COMPLETED_WITH_WARNINGS/);
  assert.match(f.comments[0].body, /UNCOMMITTED_WORK_REMAINS/);
  assert.match(f.comments[0].body, /owner.*reviewer must reconcile.*before acceptance/i);
  assert.equal(await reportRoutingResult(() => runAttempt({ ...args,
    prepare: () => assert.fail('replay prepared the checkout'),
    execute: () => assert.fail('replay executed the worker'),
    collect: () => assert.fail('replay recollected residue') }), reporting), 0);
  assert.deepEqual(JSON.parse(stdout[1]), JSON.parse(stdout[0]));
  assert.equal(warnings.filter(text => text.startsWith('::warning') && text.includes('UNCOMMITTED_WORK_REMAINS')).length, 2);
  assert.equal(await readFile(residue, 'utf8'), 'generated local validation cache\n');
  assert.equal(await f.command(f.cwd, ['status', '--porcelain']), '?? __pycache__/');
  assert.equal(await f.command(f.cwd, ['rev-list', '--count', `${f.envelope.startHead}..HEAD`]), '1');
  assert.equal(await f.command(f.cwd, ['ls-tree', '--name-only', 'HEAD', '__pycache__']), '');
  assert.equal(executions, 1); assert.equal(f.pushes(), 1); assert.equal(f.comments.length, 1);
});

test('replay restores the Writer warning receipt when completion preceded the runner terminal journal write', async t => {
  const f = await fixture(t); const journal = f.journal;
  const residue = join(f.cwd, 'validation-cache.tmp');
  const completed = await runAttempt({ ...f, journal, execute: async () => {
    await f.commit(); await writeFile(residue, 'generated validation residue\n');
    return result(f.envelope, 'success');
  } });
  // Model the crash window after Writer persisted finish but before the runner
  // persisted the returned receipt. Execution and publication are already known.
  const interrupted = await journal.get(99); interrupted.outcome = null;
  await journal.put(99, interrupted);
  assert.deepEqual(completed.executionWarnings, ['UNCOMMITTED_WORK_REMAINS']);
  assert.deepEqual((await f.store.get(99)).outcome.executionWarnings, completed.executionWarnings);
  const operations = []; const warnings = []; let restored;
  const args = { ...f, journal,
    prepare: () => assert.fail('receipt restoration prepared the checkout'),
    execute: () => assert.fail('receipt restoration executed the worker'),
    collect: () => assert.fail('receipt restoration recollected residue'),
    broker: { invoke: request => { operations.push(request.operation); return f.broker.invoke(request); } } };
  assert.equal(await reportRoutingResult(async () => { restored = await runAttempt(args); return restored; },
    { write() {}, writeError: text => warnings.push(text) }), 0);
  assert.deepEqual(restored, completed);
  assert.deepEqual(operations, ['preflight', 'complete-handoff']);
  assert.deepEqual((await journal.get(99)).outcome, completed);
  assert.equal(warnings.filter(text => text.startsWith('::warning') && text.includes('UNCOMMITTED_WORK_REMAINS')).length, 1);
  assert.deepEqual(await runAttempt({ ...args, broker: { invoke: request => { assert.equal(request.operation, 'complete-handoff'); return f.broker.invoke(request); } } }), completed);
  assert.equal(await readFile(residue, 'utf8'), 'generated validation residue\n');
  assert.equal(f.pushes(), 1); assert.equal(f.comments.length, 1);
});

test('a failed terminal journal write remains red on replay even after Writer persisted successful handoff with a warning', async t => {
  const f = await fixture(t); const journal = f.journal; const put = journal.put;
  let writeFailed = false;
  journal.put = async (id, record) => {
    if (record.outcome?.status === 'IMPLEMENTED_PENDING_FRESH_REVIEW' && !writeFailed) {
      writeFailed = true; throw failure('JOURNAL_WRITE_FAILED');
    }
    return put(id, record);
  };
  assert.equal(await report(() => runAttempt({ ...f, journal, execute: async () => {
    await f.commit(); await writeFile(join(f.cwd, 'validation-cache.tmp'), 'generated validation residue\n');
    return result(f.envelope, 'success');
  } })), 1);
  const failed = await journal.get(99);
  assert.equal(failed.outcome.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
  assert.deepEqual(failed.outcome.executionWarnings, ['UNCOMMITTED_WORK_REMAINS']);
  assert.equal((await f.api.get('/pulls/43')).draft, true);
  assert.equal(failed.diagnostic.orchestration, 'FAILED');
  assert.equal(failed.diagnostic.classification.code, 'JOURNAL_WRITE_FAILED');
  assert.equal(await report(() => runAttempt({ ...f, journal,
    broker: { invoke: () => assert.fail('failed terminal replay contacted Writer') },
    prepare: () => assert.fail('failed terminal replay prepared the checkout'),
    execute: () => assert.fail('failed terminal replay executed the worker'),
    collect: () => assert.fail('failed terminal replay recollected residue') })), 1);
  assert.deepEqual(await journal.get(99), failed);
  assert.equal(f.pushes(), 1); assert.equal(f.comments.length, 1);
});

for (const boundary of ['collection', 'clean-observation', 'publication', 'authority', 'containment', 'outcome', 'journal']) {
  test(`successful worker with generated residue stays red when ${boundary} is uncertain or failed`, async t => {
    const f = await fixture(t); const journal = f.journal;
    const residue = join(f.cwd, 'validation-cache.tmp');
    const broker = { invoke: async request => {
      if (boundary === 'publication' && request.operation === 'publish-progress') throw failure('PUBLICATION_UNCERTAIN');
      if (boundary === 'outcome' && request.operation === 'finish') throw failure('COMMENT_PUBLICATION_UNCERTAIN');
      return f.broker.invoke(request);
    } };
    const put = journal.put;
    if (boundary === 'journal') journal.put = async (id, row) => { if (row.outcome) throw failure('JOURNAL_WRITE_FAILED'); return put(id, row); };
    assert.equal(await report(() => runAttempt({ ...f, broker, journal,
      collect: async e => {
        if (boundary === 'collection') throw failure('OBJECT_IMPORT_FAILED');
        const progress = await f.collect(e);
        return boundary === 'clean-observation' ? { ...progress, clean: undefined } : progress;
      },
      execute: async () => {
        await f.commit(); await writeFile(residue, 'generated validation residue\n');
        if (boundary === 'authority') f.issue.body += '\nChanged owner requirement.';
        const returned = result(f.envelope, 'success');
        if (boundary === 'containment') returned.containment = 'unknown';
        return returned;
      } })), 1);
    assert.equal(await readFile(residue, 'utf8'), 'generated validation residue\n');
    if (boundary !== 'journal') assert.equal((await journal.get(99)).diagnostic.orchestration, 'FAILED');
  });
}

test('known success without changes is a normal incomplete result, never ready', async t => {
  const f = await fixture(t); const journal = f.journal;
  assert.equal(await report(() => runAttempt({ ...f, journal, execute: async () => result(f.envelope, 'success') })), 0);
  assert.equal((await journal.get(99)).outcome.status, 'BLOCKED'); assert.equal(f.pushes(), 0);
});

test('a domain-looking code cannot hide unknown execution, containment or publication', () => {
  const e = { startHead: 'a'.repeat(40) };
  const r = { envelope: e, execution: { reserved: true, returned: true, child: 'started', containment: 'reaped' }, collection: { head: e.startHead, clean: true } };
  assert.equal(safeDomainTerminal(failure('SEMANTIC_RESULT_BLOCKED'), r, 'readiness'), true);
  for (const changed of [
    { execution: { ...r.execution, reserved: false } },
    { execution: { ...r.execution, returned: false } },
    { execution: { ...r.execution, child: 'unknown' } },
    { execution: { ...r.execution, containment: 'unknown' } },
    { collection: { head: 'b'.repeat(40), clean: true } },
    { collection: { head: e.startHead, clean: false } },
  ]) assert.equal(safeDomainTerminal(failure('SEMANTIC_RESULT_BLOCKED'), { ...r, ...changed }, 'readiness'), false);
  assert.equal(safeDomainTerminal(Object.assign(failure('UNKNOWN_INTERNAL'), { name: 'IssueAuthorityError' }), r, 'preflight'), false);
});

test('loss of scope with an unknown reserved execution remains red', async t => {
  const f = await fixture(t); const journal = f.journal;
  await journal.put(99, { version: f.envelope.version, envelope: f.envelope, execution: { reserved: true, returned: false } });
  f.issue.body = '# lost scope';
  assert.equal(await report(() => runAttempt({ ...f, journal, execute: () => assert.fail('duplicate') })), 1);
});

for (const boundary of ['collection', 'publication', 'outcome', 'journal', 'draft']) {
  test(`failure at ${boundary} cannot turn a worker domain result green`, async t => {
    const f = await fixture(t, { remediation: boundary === 'draft' }); const journal = f.journal;
    const broker = { invoke: async request => {
      if (boundary === 'publication' && request.operation === 'publish-progress') throw failure('PUBLICATION_UNCERTAIN');
      if (boundary === 'outcome' && request.operation === 'terminal-outcome') throw failure('COMMENT_PUBLICATION_UNCERTAIN');
      return f.broker.invoke(request);
    } };
    const put = journal.put;
    if (boundary === 'journal') journal.put = async (id, row) => { if (row.outcome) throw failure('JOURNAL_WRITE_FAILED'); return put(id, row); };
    if (boundary === 'draft') {
      // Admission already verified Draft. Exercise a failed preflight repair
      // when native state changes after that boundary.
      f.pr.draft = false;
      f.api.draft = async () => { throw failure('DRAFT_MUTATION_FAILED'); };
    }
    assert.equal(await report(() => runAttempt({ ...f, broker, journal,
      collect: boundary === 'collection' ? () => { throw failure('OBJECT_IMPORT_FAILED'); } : f.collect,
      execute: async () => { await f.commit(); return result(f.envelope); } })), 1);
  });
}

test('defaulted base remains immutable when live main advances after admission', async t => {
  const f = await fixture(t, { issueBody: '# Task 42\nRequired branch: codex/test-42\nComplete the task-required repository changes.' });
  assert.equal(await report(() => runAttempt({ ...f, journal: f.journal, execute: async () => {
    await writeFile(join(f.source, 'unrelated.md'), 'main advance\n');
    await f.command(f.source, ['add', '.']); await f.command(f.source, ['commit', '-m', 'main advance']); await f.command(f.source, ['push', f.remote, 'main']);
    await f.commit(); return result(f.envelope, 'success');
  } })), 0);
  assert.equal(f.pushes(), 1);
  assert.match(f.comments[0].body, /Completion: COMPLETED_WITH_WARNINGS/);
});

test('resumed admission revalidates authority within the normal terminal boundary', async t => {
  const f = await fixture(t); const journal = f.journal;
  await journal.put(99, { version: f.envelope.version, envelope: f.envelope, execution: null });
  f.issue.body = '# lost scope';
  const admitted = await f.broker.invoke(f.admissionRequest);
  assert.equal(await report(() => runAttempt({ ...f, envelope: admitted.envelope, admissionResumed: true, journal, execute: () => assert.fail('scope') })), 0);
  assert.equal(f.comments.length, 1);
});

test('CLI reporting emits one warning for a domain block and returns a real nonzero exit for internal failure', async () => {
  const output = []; const options = { write: x => output.push(x), writeError: x => output.push(x) };
  assert.equal(await reportRoutingResult(async () => ({ status: 'BLOCKED' }), options), 0);
  assert.equal(output.filter(x => x.startsWith('::warning')).length, 1);
  assert.equal(await reportRoutingResult(async () => { throw new Error('private internal text'); }, options), 1);
  assert.ok(!output.join('').includes('private internal text'));
});

test('a worker capability blocker reaches the Outcome as a bounded redacted claim', async t => {
  const f = await fixture(t);
  const value = result(f.envelope);
  value.result.summary = 'Applicable local checks passed';
  value.result.blockedReason = 'Capability unavailable; password=synthetic-private-value';
  assert.equal(await report(() => runAttempt({ ...f, journal: f.journal, execute: async () => value })), 0);
  assert.match(f.comments[0].body, /Worker summary \(claim\): Applicable local checks passed/);
  assert.match(f.comments[0].body, /Worker blocker \(claim\): Capability unavailable/);
  assert.doesNotMatch(f.comments[0].body, /synthetic-private-value/);
});
