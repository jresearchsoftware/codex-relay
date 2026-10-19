import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { runAttempt } from '../src/attempt.mjs';
import { fixture } from './fixture.mjs';

const failure = code => Object.assign(new Error(code), { code });
const result = e => ({ version: e.version, attemptId: e.attemptId,
  child: 'started', containment: 'reaped', result: { status: 'success' } });

for (const clean of [true, false]) {
  test(`contained ${clean ? 'clean' : 'retained dirty'} checkout proof survives uncertain publication before an Outcome`, async t => {
    const f = await fixture(t);
    let executions = 0; let savedAtPublication;
    const broker = { async invoke(request) {
      if (request.operation === 'publish-progress') {
        savedAtPublication = await f.journal.get(f.envelope.runId);
        assert.equal(savedAtPublication.execution.containment, 'reaped');
        assert.equal(savedAtPublication.execution.returned, true);
        assert.deepEqual(savedAtPublication.collection,
          { head: request.bundle ? await f.command(f.cwd, ['rev-parse', 'HEAD']) : null, clean, preserved: true });
        assert.equal(savedAtPublication.progress, null);
        assert.equal(savedAtPublication.outcome, null);
        throw failure('PUBLICATION_UNCERTAIN');
      }
      if (request.operation === 'terminal-outcome') throw failure('OUTCOME_PUBLICATION_UNCERTAIN');
      return f.broker.invoke(request);
    } };
    const options = { ...f, broker, execute: async () => {
      executions++; await f.commit();
      if (!clean) await writeFile(join(f.cwd, 'retained-work.md'), 'preserved uncommitted work\n');
      return result(f.envelope);
    } };
    await assert.rejects(runAttempt(options), { code: 'PUBLICATION_UNCERTAIN' });
    const saved = await f.journal.get(f.envelope.runId);
    assert.deepEqual(saved.collection, savedAtPublication.collection);
    assert.equal(saved.outcome, null); assert.equal(f.pushes(), 0);
    assert.equal(await readFile(join(f.cwd, 'docs/work.md'), 'utf8'), 'changed\n');
    if (!clean) assert.equal(await readFile(join(f.cwd, 'retained-work.md'), 'utf8'), 'preserved uncommitted work\n');
    // A fresh resource can be available without retrying the original model.
    await assert.rejects(runAttempt({ ...options,
      prepare: () => assert.fail('reserved execution must not be prepared again') }), { code: 'PUBLICATION_UNCERTAIN' });
    assert.equal(executions, 1);
  });
}

test('a failed collection receipt write cannot start publication', async t => {
  const f = await fixture(t); let failed = false; const publications = [];
  const journal = { get: f.journal.get, async put(id, record) {
    if (!failed && record.collection?.preserved) { failed = true; throw failure('ENOSPC'); }
    return f.journal.put(id, record);
  } };
  const broker = { async invoke(request) {
    if (request.operation === 'publish-progress') publications.push(request);
    return f.broker.invoke(request);
  } };
  await assert.rejects(runAttempt({ ...f, journal, broker,
    execute: async () => { await f.commit(); return result(f.envelope); } }), { code: 'ENOSPC' });
  assert.deepEqual(publications, []); assert.equal(f.pushes(), 0);
});

test('unknown child containment cannot claim a preserved collection receipt', async t => {
  const f = await fixture(t);
  await assert.rejects(runAttempt({ ...f,
    execute: async () => ({ ...result(f.envelope), containment: 'unknown' }),
    collect: () => assert.fail('unknown child must retain its checkout resource') }), { code: 'CONTAINMENT_NOT_PROVEN' });
  assert.equal((await f.journal.get(f.envelope.runId)).collection, undefined);
  assert.equal(f.pushes(), 0);
});

test('two controllers cannot initialize the same checkout path concurrently', async t => {
  const f = await fixture(t);
  const attempts = await Promise.allSettled([f.prepare(f.envelope), f.prepare(f.envelope)]);
  assert.equal(attempts.filter(value => value.status === 'fulfilled').length, 1);
  const rejected = attempts.find(value => value.status === 'rejected');
  assert.equal(rejected.reason.code, 'CHECKOUT_ALREADY_EXISTS');
  assert.equal(await readFile(join(f.cwd, 'docs/work.md'), 'utf8'), 'baseline\n');
});

test('independent same-Task attempts initialize distinct retained checkouts concurrently', async t => {
  const f = await fixture(t);
  const sibling = { ...f.envelope, runId: 100, attemptId: 'run-100', step: f.envelope.step + 1 };
  const [left, right] = await Promise.all([f.prepare(f.envelope), f.prepare(sibling)]);
  assert.notEqual(left, right); assert.equal(f.envelope.issueNumber, sibling.issueNumber);
  await writeFile(join(left, 'docs/work.md'), 'first attempt retained work\n');
  assert.equal(await readFile(join(right, 'docs/work.md'), 'utf8'), 'baseline\n');
  await writeFile(join(right, 'docs/work.md'), 'second attempt retained work\n');
  assert.equal(await readFile(join(left, 'docs/work.md'), 'utf8'), 'first attempt retained work\n');
});
