import test from 'node:test';
import assert from 'node:assert/strict';
import { fixture } from './fixture.mjs';
import { REPOSITORY } from '../src/execution-contract.mjs';

const charter = 'Authority model: github-native-v1\nIssue closure policy: keep-open\nIndependent source research.';
const ownership = { repository: REPOSITORY, runId: 98, attemptId: 'run-98',
  issueNumber: 85, branch: 'codex/task-85', target: 'issue', number: 85 };

for (const damaged of ['missing', 'corrupt', 'incompatible']) {
  test(`sealed unrelated ${damaged} record does not block a fresh independent manual admission`, async t => {
    const f = await fixture(t, { issueBody: charter, route: 'manual', labelLaunch: true, streamlinedAdmission: true,
      beforeAdmission: ({ store }) => {
        const all = store.all.bind(store);
        store.scan = async () => [...(await all()).map(record => ({ runId: record.envelope.runId,
          repository: REPOSITORY, record })), { repository: REPOSITORY, runId: 98,
          record: damaged === 'incompatible' ? { envelope: ownership } : null,
          envelope: ownership, error: `FIXTURE_${damaged.toUpperCase()}` }];
      } });
    assert.equal(f.envelope.step, 1);
    assert.equal(await f.store.get(98), null);
    assert.equal(f.comments.length, 0);
  });
}

for (const identity of [null, { ...ownership, issueNumber: 42 }]) {
  test(`damaged publication with ${identity ? 'same Task' : 'unproven'} ownership identifies its exact conflict`, async t => {
    await assert.rejects(fixture(t, { issueBody: charter, route: 'manual', labelLaunch: true, streamlinedAdmission: true,
      beforeAdmission: ({ store }) => {
        store.scan = async () => [{ repository: REPOSITORY, runId: 98, record: null,
          envelope: identity, error: 'ATTEMPT_RECORD_UNREADABLE' }];
      } }), error => {
      assert.equal(error.code, 'PUBLICATION_INVENTORY_UNRESOLVED');
      assert.equal(error.details.conflictingAttempt, 'run-98'); return true;
    });
  });
}
