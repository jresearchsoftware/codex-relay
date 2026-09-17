import test from 'node:test';
import assert from 'node:assert/strict';
import { writeFile, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { fixture } from './fixture.mjs';
import { establishCanonicalCheckout } from '../src/canonical-checkout.mjs';

const establish = f => establishCanonicalCheckout(f.source, f.envelope, { remote: f.remote });
async function otherBranch(f, publish = true) {
  await f.command(f.source, ['switch', '-c', 'codex/unrelated']);
  await writeFile(join(f.source, 'unrelated.md'), 'unrelated work\n');
  await f.command(f.source, ['add', '.']); await f.command(f.source, ['commit', '-m', 'unrelated']);
  if (publish) await f.command(f.source, ['push', f.remote, 'codex/unrelated']);
  return f.command(f.source, ['rev-parse', 'HEAD']);
}
test('fetch/switch existing canonical remote precedes the exact-head gate despite a different initial branch/head', async t => {
  const f = await fixture(t, { remediation: true }); const initial = await otherBranch(f);
  assert.notEqual(initial, f.envelope.startHead);
  assert.equal(await establish(f), f.envelope.startHead);
  assert.equal(await f.command(f.source, ['branch', '--show-current']), f.envelope.branch);
  assert.equal(await f.command(f.source, ['rev-parse', 'codex/unrelated']), initial);
});
test('refreshed canonical mismatch blocks on the canonical branch without resetting it', async t => {
  const f = await fixture(t, { remediation: true }); const initial = await otherBranch(f);
  await f.command(f.source, ['push', f.remote, `HEAD:refs/heads/${f.envelope.branch}`]);
  await assert.rejects(establish(f), { code: 'STARTING_STATE_MISMATCH' });
  assert.equal(await f.command(f.source, ['branch', '--show-current']), f.envelope.branch);
  assert.equal(await f.command(f.source, ['rev-parse', 'HEAD']), initial);
});
test('dirty initial state is preserved without switching', async t => {
  const f = await fixture(t, { remediation: true }); await otherBranch(f);
  await writeFile(join(f.source, 'docs/work.md'), 'dirty\n');
  await assert.rejects(establish(f), { code: 'CHECKOUT_DIRTY' });
  assert.equal(await f.command(f.source, ['branch', '--show-current']), 'codex/unrelated');
  assert.equal(await readFile(join(f.source, 'docs/work.md'), 'utf8'), 'dirty\n');
});
test('unpublished unrelated commits remain intact without switching', async t => {
  const f = await fixture(t, { remediation: true }); const head = await otherBranch(f, false);
  await assert.rejects(establish(f), { code: 'CHECKOUT_UNPUBLISHED' });
  assert.equal(await f.command(f.source, ['rev-parse', 'HEAD']), head);
});
test('unpublished canonical work is preserved instead of replaced by its remote', async t => {
  const f = await fixture(t, { remediation: true }); const head = await otherBranch(f);
  await f.command(f.source, ['branch', f.envelope.branch, head]);
  await assert.rejects(establish(f), { code: 'CHECKOUT_UNPUBLISHED' });
  assert.equal(await f.command(f.source, ['rev-parse', f.envelope.branch]), head);
});
test('missing canonical remote blocks without a replacement branch', async t => {
  const f = await fixture(t); const head = await f.command(f.source, ['rev-parse', 'HEAD']);
  await assert.rejects(establish(f), { code: 'CANONICAL_BRANCH_MISSING' });
  assert.equal(await f.command(f.source, ['rev-parse', 'HEAD']), head);
  assert.equal(await f.command(f.source, ['branch', '--list', f.envelope.branch]), '');
});

test('a published local canonical branch behind the admitted remote advances only by fast-forward', async t => {
  const f = await fixture(t, { remediation: true });
  await f.command(f.source, ['branch', f.envelope.branch, f.envelope.startHead]);
  const head = await otherBranch(f);
  await f.command(f.source, ['push', f.remote, `HEAD:refs/heads/${f.envelope.branch}`]);
  assert.equal(await establishCanonicalCheckout(f.source, { ...f.envelope, startHead: head }, { remote: f.remote }), head);
  assert.equal(await f.command(f.source, ['branch', '--show-current']), f.envelope.branch);
  assert.equal(await f.command(f.source, ['rev-parse', 'HEAD']), head);
});

test('automatic prepare refuses to reuse a worker checkout and preserves its bytes', async t => {
  const f = await fixture(t); await f.prepare(f.envelope);
  await writeFile(join(f.cwd, 'docs/work.md'), 'worker evidence\n');
  await assert.rejects(f.prepare(f.envelope), { code: 'CHECKOUT_ALREADY_EXISTS' });
  assert.equal(await readFile(join(f.cwd, 'docs/work.md'), 'utf8'), 'worker evidence\n');
});
