import test from 'node:test';
import assert from 'node:assert/strict';
import { chmod, chown, lstat, mkdir, readFile, symlink, link, writeFile } from 'node:fs/promises';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { join } from 'node:path';
import { fixture } from './fixture.mjs';
import { createPublicationBroker } from '../src/publication-broker.mjs';
import { runAttempt } from '../src/attempt.mjs';
import { VERSION, OWNER, REPOSITORY } from '../src/execution-contract.mjs';
import { recoveryAuthorization, recoveryAuthorizationBody } from '../src/publication-recovery.mjs';
import { recoverAttemptPublication } from '../src/recover-attempt-publication.mjs';

const exec = promisify(execFile);
const contained = e => ({ version: VERSION, envelope: structuredClone(e),
  execution: { reserved: true, returned: true, child: 'started', containment: 'reaped', result: { status: 'success' } },
  outcome: null, diagnostic: null });
function collector(f, collectRetained) {
  const broker = createPublicationBroker({ api: f.api, store: f.store, journal: f.journal,
    publisher: f.publisher, lifecycleStore: f.lifecycleStore, collectRetained });
  return { invoke: request => broker.dispatch(request) };
}

test('protected collection requires exact nonterminal contained admission and rejects caller paths', async t => {
  const f = await fixture(t); const e = f.envelope;
  let calls = 0;
  const broker = collector(f, async bound => { assert.deepEqual(bound, e); calls++; return { head: e.startHead, clean: true, bundle: null }; });
  const request = { operation: 'collect-progress', runId: e.runId, attemptId: e.attemptId };
  await assert.rejects(broker.invoke(request), { code: 'COLLECTION_NOT_ADMITTED' });
  for (const mutate of [
    r => { r.execution.returned = false; }, r => { r.execution.containment = 'unknown'; },
    r => { r.envelope.attemptId = 'run-100'; }, r => { r.outcome = {}; }, r => { r.diagnostic = {}; }
  ]) {
    const r = contained(e); mutate(r); await f.journal.put(e.runId, r);
    await assert.rejects(broker.invoke(request), { code: 'COLLECTION_NOT_ADMITTED' });
  }
  await f.journal.put(e.runId, contained(e));
  await assert.rejects(broker.invoke({ ...request, checkout: '/etc' }), { code: 'COLLECTION_REQUEST_INVALID' });
  assert.equal(calls, 0);
  assert.equal((await broker.invoke(request)).head, e.startHead); assert.equal(calls, 1);
  const record = await f.store.get(e.runId);
  record.publicationIntent = { previous: null, head: e.startHead }; await f.store.put(e.runId, record);
  assert.equal((await broker.invoke(request)).head, e.startHead); assert.equal(calls, 2);
  assert.equal(f.pushes(), 0);
});

test('root Writer collects worker-private atomic replacements without changing modes, then publishes and readies', {
  skip: process.platform !== 'linux' || process.getuid?.() !== 0 ? 'requires native Linux root and distinct numeric worker/collector identities' : false
}, async t => {
  const f = await fixture(t); const e = f.envelope;
  const broker = collector(f, f.collect);
  let head; let before;
  const result = await runAttempt({ envelope: e, broker, journal: f.journal, prepare: f.prepare,
    execute: async () => {
      const nested = join(f.cwd, 'docs/nested'); await mkdir(nested);
      head = await f.commit('docs/nested/private.md', 'private-mode source\n');
      head = await f.commit('docs/acl.md', 'ACL-restricted task source\n');
      for (const path of [f.root, join(f.root, 'work'), f.cwd, join(f.cwd, 'docs')]) await chmod(path, 0o755);
      await chown(nested, 983, 980); await chmod(nested, 0o700);
      const aclFile = join(f.cwd, 'docs/acl.md'); await chown(aclFile, 983, 980);
      // A named-user deny takes precedence over group/other permissions.
      // Use Linux's native POSIX ACL xattr; no optional setfacl binary needed.
      await exec('/usr/bin/python3', ['-c',
        "import os,struct,sys; entries=[(1,6,0xffffffff),(2,0,985),(4,4,0xffffffff),(16,4,0xffffffff),(32,4,0xffffffff)]; os.setxattr(sys.argv[1], 'system.posix_acl_access', struct.pack('<I',2)+b''.join(struct.pack('<HHI',*e) for e in entries))", aclFile]);
      await assert.rejects(exec('setpriv', ['--reuid', '985', '--regid', '982', '--clear-groups', '/usr/bin/cat', aclFile]));
      // The producer really creates and atomically replaces the source as its
      // own UID/GID. Neither the runner nor Writer repairs the file afterward.
      await exec('setpriv', ['--reuid', '983', '--regid', '980', '--clear-groups', process.execPath, '--input-type=module', '-e',
        `import {writeFile,rename} from 'node:fs/promises'; await writeFile(${JSON.stringify(join(nested, 'next'))}, 'private-mode source\\n', {mode:0o600}); await rename(${JSON.stringify(join(nested, 'next'))}, ${JSON.stringify(join(nested, 'private.md'))});`]);
      before = await lstat(join(nested, 'private.md'));
      await assert.rejects(exec('setpriv', ['--reuid', '985', '--regid', '982', '--clear-groups', '/usr/bin/cat', join(nested, 'private.md')]));
      return { version: VERSION, attemptId: e.attemptId, child: 'started', containment: 'reaped',
        result: { status: 'success', summary: 'Synthetic restrictive source', validation: [], blockedReason: null } };
    }, collect: () => broker.invoke({ operation: 'collect-progress', runId: e.runId, attemptId: e.attemptId }) });
  assert.equal(result.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW'); assert.equal(result.head, head);
  assert.equal(f.pushes(), 1); assert.equal((await f.api.get(`/pulls/${result.prNumber}`)).draft, false);
  const after = await lstat(join(f.cwd, 'docs/nested/private.md'));
  for (const key of ['uid', 'gid', 'mode', 'ino', 'dev', 'size', 'ctimeMs', 'mtimeMs']) assert.equal(after[key], before[key]);
  assert.equal(after.mode & 0o777, 0o600);
  // Task-owned symlinks are observed as links, never dereferenced, including
  // a protected outside target. Hard links cannot smuggle host source bytes.
  const outside = join(f.root, 'outside-secret'); await writeFile(outside, 'outside sentinel', { mode: 0o600 });
  await symlink(outside, join(f.cwd, 'outside-link'));
  assert.equal((await f.collect(e)).clean, false);
  await link(outside, join(f.cwd, 'outside-hardlink'));
  await assert.rejects(f.collect(e), { code: 'UNTRUSTED_GIT_FILE_INVALID' });
  assert.equal(await readFile(outside, 'utf8'), 'outside sentinel');
});

test('private-mode source survives failed publication and explicit same-attempt recovery without worker replay', {
  skip: process.platform !== 'linux' || process.getuid?.() !== 0 ? 'requires native Linux root' : false
}, async t => {
  const f = await fixture(t); const e = f.envelope; const broker = collector(f, f.collect);
  let head; let executions = 0;
  f.failPush(true);
  await assert.rejects(runAttempt({ envelope: e, broker, journal: f.journal, prepare: f.prepare,
    execute: async () => {
      executions++; head = await f.commit('docs/private.md', 'restrictive recovery source\n');
      await chown(join(f.cwd, 'docs/private.md'), 983, 980); await chmod(join(f.cwd, 'docs/private.md'), 0o600);
      await chown(join(f.cwd, 'docs'), 983, 980); await chmod(join(f.cwd, 'docs'), 0o700);
      return { version: VERSION, attemptId: e.attemptId, child: 'started', containment: 'reaped',
        result: { status: 'success', summary: 'Restrictive recovery source', validation: [], blockedReason: null } };
    }, collect: () => broker.invoke({ operation: 'collect-progress', runId: e.runId, attemptId: e.attemptId })
  }), { code: 'PUBLICATION_UNCERTAIN' });
  f.failPush(false); assert.equal(f.pushes(), 1);
  f.run.status = 'completed'; f.run.updated_at = '2026-09-04T12:01:00Z';
  const record = await f.store.get(e.runId);
  const binding = recoveryAuthorization(e, record.publicationIntent);
  f.comments.push({ id: 10000, user: { login: OWNER, type: 'User' },
    issue_url: `https://api.github.com/repos/${REPOSITORY}/issues/${e.number}`,
    created_at: '2026-09-04T12:02:00Z', updated_at: '2026-09-04T12:02:00Z', body: recoveryAuthorizationBody(binding) });
  const options = { runId: e.runId, attemptId: e.attemptId, authorizationId: 10000, broker, journal: f.journal,
    collect: () => broker.invoke({ operation: 'collect-progress', runId: e.runId, attemptId: e.attemptId, authorizationId: 10000 }) };
  const recovered = await recoverAttemptPublication(options);
  assert.equal(recovered.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW'); assert.equal(recovered.head, head);
  assert.equal((await f.api.get(`/pulls/${recovered.prNumber}`)).draft, false);
  assert.deepEqual(await recoverAttemptPublication(options), recovered);
  assert.equal(executions, 1); assert.equal(f.pushes(), 2);
  assert.equal((await lstat(join(f.cwd, 'docs/private.md'))).mode & 0o777, 0o600);
});
