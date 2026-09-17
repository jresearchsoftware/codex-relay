import { createHash } from 'node:crypto';
import { readFileSync, lstatSync } from 'node:fs';
import { dirname, isAbsolute } from 'node:path';

const reject = () => { throw Object.assign(new Error('CONSUMER_CONFIG_INVALID'), { code: 'CONSUMER_CONFIG_INVALID' }); };
const text = (v, re) => typeof v === 'string' && re.test(v);
const login = v => text(v, /^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$/) && !v.includes('--');
export const safeBranch = v => text(v, /^[A-Za-z0-9][A-Za-z0-9._/-]{0,239}$/)
  && v.split('/').every(p => p && !p.startsWith('.') && !p.endsWith('.lock')) && !v.includes('..') && !v.endsWith('.');
const path = v => text(v, /^\/[A-Za-z0-9_./-]+$/) && v.split('/').slice(1).every(p => p && p !== '.' && p !== '..');
const keys = (v, names) => v && typeof v === 'object' && !Array.isArray(v)
  && Object.keys(v).length === names.length && names.every(k => Object.hasOwn(v, k));
function freeze(v) { if (v && typeof v === 'object') { Object.values(v).forEach(freeze); Object.freeze(v); } return v; }

export function validateConsumer(c) {
  const { validationNames, ...required } = c ?? {};
  if (!keys(required, ['version', 'repository', 'owner', 'baseBranch', 'taskBranchPrefix', 'routingWorkflow', 'recoveryWorkflow', 'validationWorkflow',
    'writerApp', 'reviewerApp', 'writerIdentity', 'remediationIdentity', 'defaultProfile', 'paths', 'runtimeUser'])) reject();
  if (Object.hasOwn(c, 'validationNames') && (!Array.isArray(validationNames) || validationNames.length > 32
    || new Set(validationNames).size !== validationNames.length
    || validationNames.some(name => !text(name, /^[a-z][a-z0-9-]{0,63}$/)))) reject();
  const repo = typeof c.repository === 'string' ? c.repository.split('/') : [];
  if (c.version !== 1 || repo.length !== 2 || !login(repo[0]) || !text(repo[1], /^[A-Za-z0-9_.-]{1,100}$/)
    || ['.', '..'].includes(repo[1]) || !login(c.owner) || !safeBranch(c.baseBranch)
    || !text(c.taskBranchPrefix, /^[A-Za-z0-9][A-Za-z0-9_/-]*\/$/) || !safeBranch(c.taskBranchPrefix + 'task-1')
    || c.baseBranch.startsWith(c.taskBranchPrefix) || (!text(c.runtimeUser, /^[a-z_][a-z0-9_-]{0,31}$/) || c.runtimeUser === 'root')) reject();
  for (const workflow of [c.routingWorkflow, c.recoveryWorkflow, c.validationWorkflow]) {
    if (!text(workflow, /^\.github\/workflows\/[A-Za-z0-9_-]+\.ya?ml$/)) reject();
  }
  if (new Set([c.routingWorkflow, c.recoveryWorkflow, c.validationWorkflow]).size !== 3) reject();
  for (const app of [c.writerApp, c.reviewerApp]) {
    if (!keys(app, ['slug', 'appId', 'installationId', 'expectedActor']) || !text(app.slug, /^[a-z0-9][a-z0-9-]{0,99}$/)
      || !text(app.appId, /^[1-9][0-9]{0,15}$/) || !text(app.installationId, /^[1-9][0-9]{0,15}$/)
      || app.expectedActor !== `${app.slug}[bot]`) reject();
  }
  for (const field of ['slug', 'appId', 'installationId', 'expectedActor']) if (c.writerApp[field] === c.reviewerApp[field]) reject();
  for (const identity of [c.writerIdentity, c.remediationIdentity]) {
    if (!keys(identity, ['name', 'email']) || !text(identity.name, /^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$/)
      || !text(identity.email, /^[A-Za-z0-9+_.\[\]-]+@[A-Za-z0-9.-]+$/)
      || identity.name === c.reviewerApp.slug || identity.email.includes(c.reviewerApp.expectedActor)) reject();
  }
  if (!keys(c.defaultProfile, ['cliModelId', 'effort'])
    || !text(c.defaultProfile.cliModelId, /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/)
    || !text(c.defaultProfile.effort, /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/)) reject();
  if (!keys(c.paths, ['workRoot', 'attemptRoot', 'dispatch', 'writerHelper', 'launcher', 'diagnosticsConfig',
    'diagnosticsStore', 'diagnosticsRoot', 'credentialEnv', 'credentialKeyFile', 'claimRoot'])
    || Object.values(c.paths).some(v => !path(v)) || new Set(Object.values(c.paths)).size !== Object.keys(c.paths).length) reject();
  if (/(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]{20,}|PRIVATE KEY/.test(JSON.stringify(c))) reject();
  return freeze(structuredClone(c));
}

export function loadConsumer(pathname) {
  if (!pathname || !isAbsolute(pathname)) reject();
  try {
    const stat = lstatSync(pathname);
    if (!stat.isFile() || stat.isSymbolicLink() || stat.size > 16384 || (stat.mode & 0o022)) reject();
    return validateConsumer(parseConsumerJson(readFileSync(pathname, 'utf8')));
  } catch { reject(); }
}

export function parseConsumerJson(source) {
  const value = JSON.parse(source);
  // JSON.parse establishes syntax; inspect object-key tokens before accepting
  // its last-key-wins result. Escaped spellings of the same key also conflict.
  const tokens = source.match(/"(?:[^"\\]|\\.)*"|[{}\[\]:,]/g) ?? [];
  const stack = [];
  for (let i = 0; i < tokens.length; i++) {
    const token = tokens[i];
    if (token === '{' || token === '[') stack.push(token === '{' ? new Set() : null);
    else if (token === '}' || token === ']') stack.pop();
    else if (token.startsWith('"') && tokens[i + 1] === ':') {
      const key = JSON.parse(token); const keys = stack.at(-1);
      if (!keys || keys.has(key)) reject();
      keys.add(key);
    }
  }
  return value;
}

// The privileged entrypoint additionally proves every parent is root-owned.
// The root-owned env-i wrapper supplies this path, never request JSON or a PR.
export function assertRootConsumer(pathname) {
  if (!pathname || !isAbsolute(pathname)) reject();
  for (let at = pathname; ; at = dirname(at)) {
    const stat = lstatSync(at);
    if (stat.uid !== 0 || stat.isSymbolicLink() || (stat.mode & 0o022)) reject();
    if (at === '/') break;
  }
}
export const consumerDigest = c => createHash('sha256').update(JSON.stringify(c)).digest('hex');
