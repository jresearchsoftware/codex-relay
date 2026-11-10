import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';

const revisions = new Set(['3f4d4348cfb05866b2108eadcc35b7a17153ff14',
  'f6431d612d464c511fdda97e7dea64ace7f03ac7', '0aff32a6873262185f60364463f4e97ef330de89']);
const paths = ['consumer', 'controller/src', 'runtime/src', 'contracts/src', 'reviewer/src/executable-cr-v2.json'];
const selected = path => paths.some(p => path === p || path.startsWith(p + '/') || p.startsWith(path + '/'));
const objectId = (kind, bytes) => createHash('sha1').update(`${kind} ${bytes.length}\0`).update(bytes).digest('hex');

// Verify the raw Git commit and every selected tree/blob against the exact
// original commit ID. Unselected siblings need only their Git tree entries.
// This is test data, never an alternative installed-runtime source provider.
export function verifyHistoricalRuntime(fixture, revision) {
  assert.ok(revisions.has(revision), 'Unretained historical runtime');
  assert.equal(fixture.revision, revision);
  const commit = Buffer.from(fixture.commit, 'utf8');
  assert.equal(objectId('commit', commit), revision, 'Historical commit mismatch');
  const root = /^tree ([a-f0-9]{40})\n/.exec(fixture.commit)?.[1];
  assert.ok(root, 'Historical commit tree missing');
  const files = []; const trees = [];
  function visit(path, expected) {
    const bytes = Buffer.from(fixture.trees[path], 'base64');
    assert.equal(objectId('tree', bytes), expected, `Historical tree mismatch: ${path}`);
    trees.push(path);
    let offset = 0;
    while (offset < bytes.length) {
      const space = bytes.indexOf(32, offset); const zero = bytes.indexOf(0, space + 1);
      assert.ok(space > offset && zero > space && zero + 21 <= bytes.length, 'Invalid historical tree');
      const mode = bytes.toString('ascii', offset, space);
      const name = bytes.toString('utf8', space + 1, zero);
      assert.ok(name && !['.', '..'].includes(name) && !/[\\/]/.test(name), 'Unsafe historical path');
      const child = path ? path + '/' + name : name;
      const oid = bytes.subarray(zero + 1, zero + 21).toString('hex');
      offset = zero + 21;
      if (!selected(child)) continue;
      if (mode === '40000') visit(child, oid);
      else {
        assert.ok(['100644', '100755'].includes(mode), 'Unsupported historical file mode');
        assert.ok(Object.hasOwn(fixture.files, child), `Missing historical blob: ${child}`);
        const content = Buffer.from(fixture.files[child], 'utf8');
        assert.equal(objectId('blob', content), oid, `Historical blob mismatch: ${child}`);
        files.push({ path: child, content, mode: parseInt(mode, 8) & 0o777 });
      }
    }
  }
  visit('', root);
  assert.deepEqual(Object.keys(fixture.files).sort(), files.map(file => file.path).sort(), 'Historical file set mismatch');
  assert.deepEqual(Object.keys(fixture.trees).sort(), trees.sort(), 'Historical proof set mismatch');
  return files;
}

export async function extractHistoricalRuntime(destination, revision) {
  assert.ok(revisions.has(revision), 'Unretained historical runtime');
  const fixture = JSON.parse(await readFile(new URL(`./fixtures/historical-runtime/${revision}.json`, import.meta.url), 'utf8'));
  const files = verifyHistoricalRuntime(fixture, revision);
  // Finish verification before materializing any executable source.
  for (const file of files) {
    const target = join(destination, file.path);
    await mkdir(dirname(target), { recursive: true, mode: 0o755 });
    await writeFile(target, file.content, { mode: file.mode });
  }
}
