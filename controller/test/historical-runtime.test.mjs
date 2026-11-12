import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { verifyHistoricalRuntime } from './historical-runtime.mjs';

for (const revision of ['3f4d4348cfb05866b2108eadcc35b7a17153ff14', 'f6431d612d464c511fdda97e7dea64ace7f03ac7',
  '0aff32a6873262185f60364463f4e97ef330de89']) {
  test(`retained runtime is complete and Git-authenticated offline: ${revision}`, async () => {
    const original = JSON.parse(await readFile(new URL(`./fixtures/historical-runtime/${revision}.json`, import.meta.url), 'utf8'));
    const files = verifyHistoricalRuntime(original, revision);
    assert.ok(files.some(file => file.path === 'controller/src/publication-broker.mjs'));
    assert.ok(files.some(file => file.path === 'reviewer/src/executable-cr-v2.json'));
    for (const corrupt of [
      fixture => { fixture.commit += '\n'; },
      fixture => { fixture.trees[''] = Buffer.from('invalid').toString('base64'); },
      fixture => { fixture.files['controller/src/publication-broker.mjs'] += '// changed\n'; },
      fixture => { delete fixture.files['controller/src/publication-broker.mjs']; },
      fixture => { fixture.files['controller/src/extra.mjs'] = ''; },
      fixture => { fixture.files['../escape.mjs'] = ''; },
      fixture => { fixture.revision = 'a'.repeat(40); },
    ]) {
      const fixture = structuredClone(original); corrupt(fixture);
      assert.throws(() => verifyHistoricalRuntime(fixture, revision));
    }
    assert.throws(() => verifyHistoricalRuntime(original, 'a'.repeat(40)), /Unretained/);
  });
}
