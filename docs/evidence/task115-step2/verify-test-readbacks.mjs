// Read-only verification of installed source bytes and synthetic native results.
// Usage: node verify-test-readbacks.mjs ISSUE_COMMENTS PR_COMMENTS INSTALLED_HASHES OUTPUT
// Comments must be complete `gh api --paginate --slurp` JSON readbacks.
import {readFileSync, writeFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {resolve, join} from 'node:path';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {extractAuthorityRecord, canonicalAuthorityJson, sha256Body, admissionBinding} from '../../../contracts/src/github-authority.mjs';

const [issueComments, prComments, installedHashes, output] = process.argv.slice(2);
assert(output, 'four input/output paths required');
const here = fileURLToPath(new URL('.', import.meta.url));
const root = resolve(here, '../../..');
const native = [issueComments, prComments].flatMap(p => JSON.parse(readFileSync(p, 'utf8')).flat());
const source = '3fff4140c57b993b9f006159529d9459ec9ace13';
const installed = JSON.parse(readFileSync(installedHashes, 'utf8'));
const paths = execFileSync('git', ['ls-tree', '-r', '--name-only', source], {cwd: root, encoding: 'utf8'}).trim().split('\n');
assert.deepEqual(Object.keys(installed).sort(), paths.sort());
for (const path of paths) {
  const bytes = execFileSync('git', ['show', `${source}:${path}`], {cwd: root, maxBuffer: 16 * 1024 * 1024});
  assert.equal(createHash('sha256').update(bytes).digest('hex'), installed[path], path);
}
const expected = [
  {run: 9007115000401, id: 6120882274, sha256: 'ee11bd9b2aa016210ff44a6e71e98c7070f206d654f3bbaefa3708913cf40ba5', parent: {kind: 'issue', number: 6}},
  {run: 9007115000402, id: 6120948158, sha256: 'b1a6388c6915f41c705e56f9833da2e9d9d9166d16213ae02204be14b61a9412', parent: {kind: 'pull_request', number: 7}},
  {run: 9007115000403, id: 6121034785, sha256: '1a2d562dbf31bf57a43bfaee4fc8449438abd0edb017418d6a2f0d9a22db4a0d', parent: {kind: 'issue', number: 6}},
  {run: 9007115000404, id: 6121131253, sha256: 'cdbd4b447fa9f033082fcf4879b3a2880933d831365df791fb3068c9126f991b', parent: {kind: 'pull_request', number: 7}},
];
const results = expected.map(e => {
  const comments = native.filter(v => v.body?.includes(`<!-- relay:run-${e.run}:outcome -->`));
  assert.equal(comments.length, 1, `one native Outcome per run ${e.run}`);
  const comment = comments[0];
  assert.equal(comment.id, e.id);
  assert.equal(comment.user.login, 'jresearch-relay-test-writer[bot]');
  assert.equal(comment.user.id, 338711029);
  assert.equal(comment.user.type, 'Bot');
  assert.equal(sha256Body(comment.body), e.sha256);
  const record = extractAuthorityRecord(comment.body);
  const claim = JSON.parse(readFileSync(join(here, `synthetic-inputs/${e.run}.claim.json`), 'utf8'));
  const admission = claim.envelope.request;
  assert.equal(canonicalAuthorityJson(record.authority), canonicalAuthorityJson(admission.authority));
  assert.equal(canonicalAuthorityJson(record.admission), canonicalAuthorityJson(admissionBinding(admission)));
  assert.equal(canonicalAuthorityJson(record.authority_resolution), canonicalAuthorityJson(admission.authority_resolution));
  assert.deepEqual(record.parent, e.parent);
  assert.deepEqual(record.authority_drift.changed_fields, ['scope']);
  assert.equal(record.authority_drift.review_required, true);
  assert.equal(record.authority_drift.current_authority.decisions.length, 1);
  assert.equal(record.authority_drift.current_authority.decisions[0].id, 6120864980);
  assert.equal(record.authority_drift.current_authority.decisions[0].sha256, 'd19567904224987f68aa9844b89b3a91efde7cdc002f1874e557b037fc7622c0');
  assert.equal(record.authority_drift.current_authority.sha256, 'b60350f300d2f48bd896b2c8bf6125a77342ce730718489262cc8ec1dd4b55f4');
  assert(comment.body.indexOf('Changed Task fields: scope.') < comment.body.indexOf('<details>'));
  return {...e, url: comment.html_url, actor: {id: comment.user.id, login: comment.user.login, type: comment.user.type}, admission: record.admission,
    admitted_authority: record.authority.sha256, current_authority: record.authority_drift.current_authority.sha256,
    changed_fields: record.authority_drift.changed_fields, review_required: true, immutable_admission_unchanged: true,
    captured_resolution_unchanged: true, exact_native_body_verified: true, single_native_outcome: true,
    synthetic: true, real_admission: false, real_worker_model_execution: false};
});
const receipt = {observed_at: new Date().toISOString(), status: 'PASS', source_revision: source,
  installed_files: paths.length, installed_bytes_equal_exact_git_tree: true,
  installed_hash_map_sha256: createHash('sha256').update(readFileSync(installedHashes)).digest('hex'), outcomes: results};
writeFileSync(output, JSON.stringify(receipt, null, 2) + '\n');
console.log(JSON.stringify(receipt));
