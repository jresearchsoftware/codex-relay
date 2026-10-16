import { createHash } from 'node:crypto';
import { readFileSync, lstatSync } from 'node:fs';
import { dirname, isAbsolute } from 'node:path';
import { resolveExecutionDefaults } from '../contracts/src/execution-defaults.mjs';

const reject = () => { throw Object.assign(new Error('CONSUMER_CONFIG_INVALID'), { code: 'CONSUMER_CONFIG_INVALID' }); };
const text = (v, re) => typeof v === 'string' && re.test(v);
const login = v => text(v, /^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$/) && !v.includes('--');
export const safeBranch = v => text(v, /^[A-Za-z0-9][A-Za-z0-9._/-]{0,239}$/)
  && v.split('/').every(p => p && !p.startsWith('.') && !p.endsWith('.lock')) && !v.includes('..') && !v.endsWith('.');
const path = v => text(v, /^\/[A-Za-z0-9_./-]+$/) && v.split('/').slice(1).every(p => p && p !== '.' && p !== '..');
const unixIdentity = v => text(v, /^[a-z_][a-z0-9_-]{0,31}$/) && v !== 'root';
export const EXECUTION_PATH_NAMES = Object.freeze(['workRoot', 'attemptRoot', 'dispatch', 'launcher', 'diagnosticsConfig', 'diagnosticsStore', 'diagnosticsRoot']);
const overlaps = (a, b) => a === b || a.startsWith(`${b}/`) || b.startsWith(`${a}/`);
const keys = (v, names) => v && typeof v === 'object' && !Array.isArray(v)
  && Object.keys(v).length === names.length && names.every(k => Object.hasOwn(v, k));
function freeze(v) { if (v && typeof v === 'object') { Object.values(v).forEach(freeze); Object.freeze(v); } return v; }

export function validateConsumer(c) {
  const { validationNames, executionSlots, generalRunnerPool, ...required } = c ?? {};
  if (!keys(required, ['version', 'repository', 'owner', 'baseBranch', 'taskBranchPrefix', 'routingWorkflow', 'recoveryWorkflow', 'validationWorkflow',
    'writerApp', 'reviewerApp', 'writerIdentity', 'remediationIdentity', 'defaultProfile', 'paths', 'runtimeUser'])) reject();
  if (Object.hasOwn(c, 'validationNames') && (!Array.isArray(validationNames) || validationNames.length > 32
    || new Set(validationNames).size !== validationNames.length
    || validationNames.some(name => !text(name, /^[a-z][a-z0-9-]{0,63}$/)))) reject();
  if (Object.hasOwn(c, 'generalRunnerPool') && (!keys(generalRunnerPool, ['desiredCapacity'])
    || !Number.isInteger(generalRunnerPool.desiredCapacity) || generalRunnerPool.desiredCapacity < 1
    || generalRunnerPool.desiredCapacity > 32 || !Object.hasOwn(c, 'executionSlots'))) reject();
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
  const profile = c.defaultProfile;
  if (!profile || !keys(profile, Object.hasOwn(profile, 'effort') ? ['cliModelId', 'effort'] : ['cliModelId'])
    || !text(c.defaultProfile.cliModelId, /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/)
    || (Object.hasOwn(profile, 'effort') && !text(profile.effort, /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/))) reject();
  if (!keys(c.paths, ['workRoot', 'attemptRoot', 'dispatch', 'writerHelper', 'launcher', 'diagnosticsConfig',
    'diagnosticsStore', 'diagnosticsRoot', 'credentialEnv', 'credentialKeyFile', 'claimRoot'])
    || Object.values(c.paths).some(v => !path(v)) || new Set(Object.values(c.paths)).size !== Object.keys(c.paths).length) reject();
  if (Object.hasOwn(c, 'executionSlots')) {
    // One repository snapshot with bounded resources and separate attempt roots.
    // Managed pool instances may share trusted runner and non-root worker UIDs.
    // The primary slot retains all legacy locations for old attempt recovery.
    if (!Array.isArray(executionSlots) || executionSlots.length < 1 || executionSlots.length > 32) reject();
    for (const slot of executionSlots) {
      if (!keys(slot, ['id', 'runnerName', 'runnerUser', 'runtimeUser', 'workGroup', 'paths'])
        || !text(slot.id, /^[a-z][a-z0-9-]{0,31}$/)
        || !text(slot.runnerName, /^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$/)
        || ![slot.runnerUser, slot.runtimeUser, slot.workGroup].every(unixIdentity)
        || slot.runnerUser === slot.runtimeUser || !keys(slot.paths, EXECUTION_PATH_NAMES)
        || Object.values(slot.paths).some(v => !path(v))
        || new Set(Object.values(slot.paths)).size !== EXECUTION_PATH_NAMES.length) reject();
    }
    const distinctFields = generalRunnerPool ? ['id', 'runnerName']
      : ['id', 'runnerName', 'runnerUser', 'runtimeUser', 'workGroup'];
    for (const field of distinctFields) {
      if (new Set(executionSlots.map(slot => slot[field])).size !== executionSlots.length) reject();
    }
    const runnerUsers = new Set(executionSlots.map(slot => slot.runnerUser));
    if (executionSlots.some(slot => runnerUsers.has(slot.runtimeUser))) reject();
    const primary = executionSlots.find(slot => slot.id === 'primary');
    if (!primary || primary.runtimeUser !== c.runtimeUser || EXECUTION_PATH_NAMES.some(name => primary.paths[name] !== c.paths[name])) reject();
    for (let i = 0; i < executionSlots.length; i++) {
      const slotPaths = Object.values(executionSlots[i].paths);
      for (const protectedName of ['writerHelper', 'credentialEnv', 'credentialKeyFile', 'claimRoot']) {
        if (slotPaths.some(value => overlaps(value, c.paths[protectedName]))) reject();
      }
      for (const other of executionSlots.slice(i + 1)) {
        if (slotPaths.some(value => Object.values(other.paths).some(candidate => overlaps(value, candidate)))) reject();
      }
      // A worker-writable root cannot contain an installed helper/config.
      const writableRoots = ['workRoot', 'attemptRoot', 'diagnosticsRoot'].map(name => executionSlots[i].paths[name]);
      if (writableRoots.some((value, index) => writableRoots.slice(index + 1).some(other => overlaps(value, other)))) reject();
      for (const writable of ['workRoot', 'attemptRoot', 'diagnosticsRoot']) {
        for (const readonly of ['dispatch', 'launcher', 'diagnosticsConfig', 'diagnosticsStore']) {
          if (overlaps(executionSlots[i].paths[writable], executionSlots[i].paths[readonly])) reject();
        }
      }
    }
  }
  if (/(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]{20,}|PRIVATE KEY/.test(JSON.stringify(c))) reject();
  const resolved = structuredClone(c);
  resolved.defaultProfile.effort = resolveExecutionDefaults(profile).effort;
  return freeze(resolved);
}

export function loadConsumer(pathname) {
  if (!pathname || !isAbsolute(pathname)) reject();
  try {
    const stat = lstatSync(pathname);
    if (!stat.isFile() || stat.isSymbolicLink() || stat.size > 128 * 1024 || (stat.mode & 0o022)) reject();
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
// Desired pool capacity controls physical runner occupancy, not an admitted
// attempt's immutable identity. Managed configurations keep all resource-slot
// bindings stable so changing capacity cannot strand original-run recovery.
// Every runtime identity, helper, path and repository binding remains hashed.
export const consumerDigest = c => createHash('sha256').update(JSON.stringify(c.generalRunnerPool
  ? { ...c, generalRunnerPool: {} } : c)).digest('hex');

export function resolveExecutionConsumer(c, slotId) {
  if (!c.executionSlots) {
    if (slotId !== undefined && slotId !== null) reject();
    return c;
  }
  const slot = c.executionSlots.find(value => value.id === (slotId ?? 'primary'));
  if (!slot) reject();
  return freeze({ ...c, runtimeUser: slot.runtimeUser, paths: { ...c.paths, ...slot.paths } });
}

export function selectExecutionSlot(c, { runnerName, uid, uidForUser }) {
  if (!c.executionSlots) return undefined;
  const slot = c.executionSlots.find(value => value.runnerName === runnerName);
  if (!slot || !Number.isSafeInteger(uid) || uid < 1 || uidForUser(slot.runnerUser) !== uid) reject();
  return slot.id;
}
