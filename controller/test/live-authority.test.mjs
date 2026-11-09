import test from 'node:test';
import assert from 'node:assert/strict';
import { OWNER, REVIEWER } from '../src/execution-contract.mjs';
import { revalidateAuthority } from '../src/live-authority.mjs';
import { fixture } from './fixture.mjs';

for (const remediation of [false, true]) {
  test(`current ${remediation ? 'CR' : 'Issue'} authority binds exact literal native bytes`, async t => {
    const f = await fixture(t, { remediation, instruction: 'Preserve *.md, a*b, a—b, and `a  b` exactly.' });
    const source = remediation ? f.review : f.issue;
    const original = source.body;
    for (const [before, after] of [['*.md', '.md'], ['a*b', 'ab'], ['a—b', 'a-b'], ['a  b', 'a b']]) {
      source.body = original.replace(before, after);
      await assert.rejects(revalidateAuthority(f.api, f.envelope), { code: 'AUTHORITY_SOURCE_MISMATCH' });
    }
    source.body = original;
    await revalidateAuthority(f.api, f.envelope);
    assert.equal(f.pushes(), 0); assert.equal(f.comments.length, 0);
  });
}

test('current native target, reviewed head and trusted Reviewer checks remain fail-closed', async t => {
  for (const [mutate, codes] of [
    [f => { f.pr.body = 'Related to #42\nRelated to #44'; }, ['CANONICAL_ISSUE_AMBIGUOUS', 'AUTHORITY_SOURCE_TARGET_MISMATCH']],
    [f => { f.pr.head.ref = 'codex/other'; }, ['STARTING_STATE_MISMATCH']],
    [f => { f.pr.base.ref = 'other'; }, ['PR_NOT_ADMITTED']],
    [f => { f.pr.head.repo.full_name = 'other/repo'; }, ['PR_NOT_ADMITTED']],
    [f => { f.review.commit_id = 'b'.repeat(40); }, ['AUTHORITY_NATIVE_KIND_MISMATCH']],
    [f => { f.review.id++; }, ['AUTHORITY_SOURCE_MISSING', 'AUTHORITY_SOURCE_MISMATCH']],
    [f => { f.review.user.login = OWNER; }, ['AUTHORITY_SOURCE_MISMATCH', 'AUTHORITY_SOURCE_UNTRUSTED', 'AUTHORITY_SOURCE_MISSING']],
    [f => { f.issue.user.login = REVIEWER; }, ['ISSUE_NOT_ADMITTED']]
  ]) {
    const f = await fixture(t, { remediation: true });
    mutate(f);
    await assert.rejects(revalidateAuthority(f.api, f.envelope), error => codes.includes(error.code), codes.join('/'));
    assert.equal(f.pushes(), 0); assert.equal(f.comments.length, 0);
  }
});
