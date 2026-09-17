import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { after } from 'node:test';

export async function loadTemplate(name, variables = {}) {
  const root = await mkdtemp(join(tmpdir(), 'relay-template-test-'));
  after(() => rm(root, { recursive: true, force: true }));
  const values = { relay_install_root: '/opt/relay-test', relay_config_root: '/etc/relay-test',
    relay_state_root: '/var/lib/relay-test', ...variables };
  const source = await readFile(new URL('../roles/relay_controller/templates/' + name + '.j2', import.meta.url), 'utf8');
  const rendered = source.replace(/{{\s*(\w+)\s*}}/g, (_, key) => {
    if (!(key in values)) throw new Error('missing template test input: ' + key);
    return values[key];
  });
  const path = join(root, name);
  await writeFile(path, rendered);
  return import(pathToFileURL(path).href);
}
