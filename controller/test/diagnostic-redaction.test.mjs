import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import * as pure from '../src/diagnostic-redaction.mjs';
import * as compatible from '../src/diagnostics.mjs';

test('diagnostic exports share the pure implementation and work without consumer configuration', () => {
  assert.equal(compatible.redactDiagnosticText, pure.redactDiagnosticText);
  assert.equal(compatible.boundedDiagnosticText, pure.boundedDiagnosticText);
  const module = new URL('../src/diagnostic-redaction.mjs', import.meta.url).href;
  const result = spawnSync(process.execPath, ['--input-type=module', '-e', `
    const { boundedDiagnosticText } = await import(${JSON.stringify(module)});
    process.stdout.write(JSON.stringify(boundedDiagnosticText('native EACCES token=fixture-secret', 256)));
  `], { env: { PATH: '/usr/bin:/bin' }, encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr);
  assert.match(JSON.parse(result.stdout).text, /native EACCES/);
  assert.ok(!result.stdout.includes('fixture-secret'));
});

test('shared redaction covers a captured prefix inside a JSON credential without losing the native cause', () => {
  const raw = '{"message":"native invalid receipt ENOSPC","token":"' + 'private-credential'.repeat(300);
  const result = pure.boundedDiagnosticText(raw.slice(0, 4096), 2048, { inputTruncated: true });
  assert.match(result.text, /native invalid receipt ENOSPC/);
  assert.ok(!result.text.includes('private-credential'));
  assert.ok(Buffer.byteLength(result.text) <= 2048);
  assert.equal(pure.boundedDiagnosticText('é'.repeat(10), 3).text, 'é');
  const danglingEscape = pure.boundedDiagnosticText(raw.slice(0, 4095) + '\\', 2048, { inputTruncated: true });
  assert.match(danglingEscape.text, /native invalid receipt ENOSPC/);
  assert.ok(!danglingEscape.text.includes('private-credential'));
});
