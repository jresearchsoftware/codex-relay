import { createHash } from 'node:crypto';
import { readFileSync, lstatSync } from 'node:fs';
import { dirname, isAbsolute } from 'node:path';
import { resolveExecutionDefaults } from '../contracts/src/execution-defaults.mjs';

// These observations are safe even during an uncaught module-import failure.
// Never attach a raw configuration value or parser excerpt to enumerable fields.
const observedValue = value => value === null ? { type: 'null' }
  : typeof value === 'string' ? { type: 'string', characters: value.length }
    : Array.isArray(value) ? { type: 'array', length: value.length }
      : typeof value === 'object' ? { type: 'object', keys: Object.keys(value).length }
        : ['number', 'boolean'].includes(typeof value) && (typeof value !== 'number' || Number.isFinite(value))
          ? { type: typeof value, value } : { type: typeof value };
const reject = (field, check, expected, observed, cause) => {
  const error = Object.assign(new Error('CONSUMER_CONFIG_INVALID'), { code: 'CONSUMER_CONFIG_INVALID',
    observation: { field, check, expected, observed: observedValue(observed) } });
  // Existing protected causal capture follows runtimeCause. Unlike Error.cause,
  // this non-enumerable property is omitted by Node's default uncaught inspect,
  // which could otherwise disclose JSON.parse's original source excerpt.
  if (cause !== undefined) Object.defineProperty(error, 'runtimeCause', { value: cause });
  throw error;
};
const requireConfig = (valid, field, check, expected, observed) => {
  if (!valid) reject(field, check, expected, observed);
};
const text = (v, re) => typeof v === 'string' && re.test(v);
const login = v => text(v, /^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$/) && !v.includes('--');
export const safeBranch = v => text(v, /^[A-Za-z0-9][A-Za-z0-9._/-]{0,239}$/)
  && v.split('/').every(p => p && !p.startsWith('.') && !p.endsWith('.lock')) && !v.includes('..') && !v.endsWith('.');
const path = v => text(v, /^\/[A-Za-z0-9_./-]+$/) && v.split('/').slice(1).every(p => p && p !== '.' && p !== '..');
const unixIdentity = v => text(v, /^[a-z_][a-z0-9_-]{0,31}$/) && v !== 'root';
const repositoryName = value => {
  const parts = typeof value === 'string' ? value.split('/') : [];
  return parts.length === 2 && login(parts[0]) && text(parts[1], /^[A-Za-z0-9_.-]{1,100}$/)
    && !['.', '..'].includes(parts[1]);
};
export const EXECUTION_PATH_NAMES = Object.freeze(['workRoot', 'attemptRoot', 'dispatch', 'launcher', 'diagnosticsConfig', 'diagnosticsStore', 'diagnosticsRoot']);
const REPOSITORY_PATH_NAMES = Object.freeze(['workRoot', 'attemptRoot', 'diagnosticsRoot']);
const overlaps = (a, b) => a === b || a.startsWith(`${b}/`) || b.startsWith(`${a}/`);
const keys = (v, names) => v && typeof v === 'object' && !Array.isArray(v)
  && Object.keys(v).length === names.length && names.every(k => Object.hasOwn(v, k));
function freeze(v) { if (v && typeof v === 'object') { Object.values(v).forEach(freeze); Object.freeze(v); } return v; }

export function validateConsumer(c) {
  const { validationNames, executionSlots, generalRunnerPool, repositories, repositoryRuntimeUsers, workGroup, ...required } = c ?? {};
  const multiple = Object.hasOwn(c ?? {}, 'repositories');
  if (!keys(required, ['version', ...(multiple ? [] : ['repository']), 'owner', 'baseBranch', 'taskBranchPrefix', 'routingWorkflow', 'recoveryWorkflow', 'validationWorkflow',
    'writerApp', 'reviewerApp', 'writerIdentity', 'remediationIdentity', 'defaultProfile', 'paths', 'runtimeUser'])) reject('configuration', 'exact-fields', 'required consumer fields with only declared optional fields', c);
  if (multiple) {
    requireConfig(Array.isArray(repositories) && repositories.length > 0, 'repositories', 'repository-list', 'nonempty owner/name list', repositories);
    for (const [index, value] of repositories.entries()) requireConfig(repositoryName(value), `repositories[${index}]`, 'repository-name', 'one valid owner/name', value);
    requireConfig(new Set(repositories.map(value => value.toLowerCase())).size === repositories.length, 'repositories', 'unique-repositories', 'case-insensitively unique repositories', new Set(repositories.map(value => value.toLowerCase())).size);
  }
  if (!multiple && !repositoryName(c.repository)) reject('repository', 'repository-name', 'one valid owner/name', c.repository);
  if (Object.hasOwn(c, 'workGroup') && !unixIdentity(workGroup)) reject('workGroup', 'non-root-unix-identity', 'valid non-root Unix group', workGroup);
  if (Object.hasOwn(c, 'repositoryRuntimeUsers') && (!multiple || !repositoryRuntimeUsers
    || typeof repositoryRuntimeUsers !== 'object' || Array.isArray(repositoryRuntimeUsers)
    || Object.entries(repositoryRuntimeUsers).some(([repository, user]) => !repositories.includes(repository) || !unixIdentity(user)))) reject('repositoryRuntimeUsers', 'configured-repository-identities', 'plural configured repository keys and non-root Unix users', repositoryRuntimeUsers);
  if (Object.hasOwn(c, 'validationNames')) {
    requireConfig(Array.isArray(validationNames) && validationNames.length <= 32, 'validationNames', 'bounded-validation-list', 'array of at most 32 check names', validationNames);
    requireConfig(new Set(validationNames).size === validationNames.length, 'validationNames', 'unique-validation-names', 'unique check names', new Set(validationNames).size);
    for (const [index, name] of validationNames.entries()) requireConfig(text(name, /^[a-z][a-z0-9-]{0,63}$/), `validationNames[${index}]`, 'validation-name', 'bounded lowercase check name', name);
  }
  if (Object.hasOwn(c, 'generalRunnerPool') && (!keys(generalRunnerPool, ['desiredCapacity'])
    || !Number.isInteger(generalRunnerPool.desiredCapacity) || generalRunnerPool.desiredCapacity < 1
    || generalRunnerPool.desiredCapacity > 32 || !Object.hasOwn(c, 'executionSlots'))) reject('generalRunnerPool', 'managed-capacity', 'exact desiredCapacity integer 1–32 with executionSlots', generalRunnerPool);
  requireConfig(c.version === 1, 'version', 'supported-version', '1', c.version);
  requireConfig(login(c.owner), 'owner', 'github-login', 'valid bounded GitHub owner login', c.owner);
  requireConfig(safeBranch(c.baseBranch), 'baseBranch', 'safe-git-branch', 'safe bounded branch name', c.baseBranch);
  requireConfig(text(c.taskBranchPrefix, /^[A-Za-z0-9][A-Za-z0-9_/-]*\/$/) && safeBranch(c.taskBranchPrefix + 'task-1'),
    'taskBranchPrefix', 'safe-task-prefix', 'safe task branch prefix ending in slash', c.taskBranchPrefix);
  requireConfig(!c.baseBranch.startsWith(c.taskBranchPrefix), 'baseBranch', 'outside-task-prefix', 'base outside task branch prefix', c.baseBranch);
  requireConfig(unixIdentity(c.runtimeUser), 'runtimeUser', 'non-root-unix-identity', 'valid non-root Unix user', c.runtimeUser);
  for (const field of ['routingWorkflow', 'recoveryWorkflow', 'validationWorkflow']) {
    if (!text(c[field], /^\.github\/workflows\/[A-Za-z0-9_-]+\.ya?ml$/)) reject(field, 'workflow-path', '.github/workflows/<name>.yml or .yaml', c[field]);
  }
  if (new Set([c.routingWorkflow, c.recoveryWorkflow, c.validationWorkflow]).size !== 3) reject('workflows', 'distinct-workflows', 'three distinct workflow paths', new Set([c.routingWorkflow, c.recoveryWorkflow, c.validationWorkflow]).size);
  for (const field of ['writerApp', 'reviewerApp']) {
    const app = c[field];
    requireConfig(keys(app, ['slug', 'appId', 'installationId', 'expectedActor']), field, 'exact-app-fields', 'slug/appId/installationId/expectedActor', app);
    requireConfig(text(app.slug, /^[a-z0-9][a-z0-9-]{0,99}$/), `${field}.slug`, 'app-slug', 'bounded lowercase App slug', app.slug);
    for (const id of ['appId', 'installationId']) requireConfig(text(app[id], /^[1-9][0-9]{0,15}$/), `${field}.${id}`, 'native-app-id', 'positive decimal string of at most 16 digits', app[id]);
    requireConfig(app.expectedActor === `${app.slug}[bot]`, `${field}.expectedActor`, 'app-actor-binding', 'actor equal to configured slug plus [bot]', app.expectedActor);
  }
  for (const field of ['slug', 'appId', 'installationId', 'expectedActor']) if (c.writerApp[field] === c.reviewerApp[field]) reject(`reviewerApp.${field}`, 'separate-writer-reviewer', 'distinct Writer and Reviewer identity', c.reviewerApp[field]);
  for (const field of ['writerIdentity', 'remediationIdentity']) {
    const identity = c[field];
    requireConfig(keys(identity, ['name', 'email']), field, 'exact-commit-identity', 'name/email fields', identity);
    requireConfig(text(identity.name, /^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$/), `${field}.name`, 'commit-name', 'bounded commit identity name', identity.name);
    requireConfig(text(identity.email, /^[A-Za-z0-9+_.\[\]-]+@[A-Za-z0-9.-]+$/), `${field}.email`, 'commit-email', 'bounded commit identity email', identity.email);
    requireConfig(identity.name !== c.reviewerApp.slug && !identity.email.includes(c.reviewerApp.expectedActor), field, 'separate-reviewer-commit-identity', 'commit identity distinct from Reviewer actor', true);
  }
  const profile = c.defaultProfile;
  if (!profile || !keys(profile, Object.hasOwn(profile, 'effort') ? ['cliModelId', 'effort'] : ['cliModelId'])
    || !text(c.defaultProfile.cliModelId, /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/)
    || (Object.hasOwn(profile, 'effort') && !text(profile.effort, /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/))) reject('defaultProfile', 'execution-profile', 'exact cliModelId with optional bounded effort', profile);
  if (!keys(c.paths, ['workRoot', 'attemptRoot', 'dispatch', 'writerHelper', 'launcher', 'diagnosticsConfig',
    'diagnosticsStore', 'diagnosticsRoot', 'credentialEnv', 'credentialKeyFile', 'claimRoot'])
    ) reject('paths', 'exact-path-fields', 'complete declared installed path fields', c.paths);
  for (const [field, value] of Object.entries(c.paths)) requireConfig(path(value), `paths.${field}`, 'safe-absolute-path', 'absolute path with safe nonempty components', value);
  requireConfig(new Set(Object.values(c.paths)).size === Object.keys(c.paths).length, 'paths', 'distinct-installed-paths', 'distinct values for all installed paths', new Set(Object.values(c.paths)).size);
  if (Object.hasOwn(c, 'executionSlots')) {
    // One installation snapshot with bounded resources and separate attempt roots.
    // Managed pool instances may share trusted runner and non-root worker UIDs.
    // The primary slot retains all legacy locations for old attempt recovery.
    if (!Array.isArray(executionSlots) || executionSlots.length < 1 || executionSlots.length > 32) reject('executionSlots', 'bounded-slots', 'array of 1–32 execution slots', executionSlots);
    for (const [index, slot] of executionSlots.entries()) {
      const field = `executionSlots[${index}]`;
      requireConfig(keys(slot, ['id', 'runnerName', 'runnerUser', 'runtimeUser', 'workGroup', 'paths']), field, 'exact-slot-fields', 'id/runnerName/runnerUser/runtimeUser/workGroup/paths', slot);
      requireConfig(text(slot.id, /^[a-z][a-z0-9-]{0,31}$/), `${field}.id`, 'slot-id', 'bounded lowercase slot ID', slot.id);
      requireConfig(text(slot.runnerName, /^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$/), `${field}.runnerName`, 'runner-name', 'bounded runner name', slot.runnerName);
      for (const identity of ['runnerUser', 'runtimeUser', 'workGroup']) requireConfig(unixIdentity(slot[identity]), `${field}.${identity}`, 'non-root-unix-identity', 'valid non-root Unix identity', slot[identity]);
      requireConfig(slot.runnerUser !== slot.runtimeUser, field, 'separate-runner-runtime', 'different runner and runtime users', slot.runnerUser === slot.runtimeUser);
      requireConfig(keys(slot.paths, EXECUTION_PATH_NAMES), `${field}.paths`, 'exact-slot-path-fields', 'complete execution path fields', slot.paths);
      for (const name of EXECUTION_PATH_NAMES) requireConfig(path(slot.paths[name]), `${field}.paths.${name}`, 'safe-absolute-path', 'absolute path with safe nonempty components', slot.paths[name]);
      requireConfig(new Set(Object.values(slot.paths)).size === EXECUTION_PATH_NAMES.length, `${field}.paths`, 'distinct-slot-paths', 'distinct slot paths', new Set(Object.values(slot.paths)).size);
    }
    const distinctFields = generalRunnerPool ? ['id', 'runnerName']
      : ['id', 'runnerName', 'runnerUser', 'runtimeUser', 'workGroup'];
    for (const field of distinctFields) {
      if (new Set(executionSlots.map(slot => slot[field])).size !== executionSlots.length) reject(`executionSlots.${field}`, 'distinct-slot-bindings', 'one distinct value per slot', new Set(executionSlots.map(slot => slot[field])).size);
    }
    const runnerUsers = new Set(executionSlots.map(slot => slot.runnerUser));
    if (executionSlots.some(slot => runnerUsers.has(slot.runtimeUser))) reject('executionSlots.runtimeUser', 'outside-runner-identities', 'runtime user distinct from every runner user', true);
    const primary = executionSlots.find(slot => slot.id === 'primary');
    requireConfig(Boolean(primary), 'executionSlots.primary', 'primary-slot', 'one preserved primary slot', Boolean(primary));
    requireConfig(primary.runtimeUser === c.runtimeUser, 'executionSlots.primary.runtimeUser', 'primary-runtime-binding', 'equal to top-level runtimeUser', primary.runtimeUser);
    requireConfig(workGroup === undefined || primary.workGroup === workGroup, 'executionSlots.primary.workGroup', 'primary-group-binding', 'equal to optional top-level workGroup', primary.workGroup);
    for (const name of EXECUTION_PATH_NAMES) requireConfig(primary.paths[name] === c.paths[name], `executionSlots.primary.paths.${name}`, 'primary-path-binding', `equal to top-level paths.${name}`, primary.paths[name]);
    for (let i = 0; i < executionSlots.length; i++) {
      const slotPaths = Object.values(executionSlots[i].paths);
      for (const protectedName of ['writerHelper', 'credentialEnv', 'credentialKeyFile', 'claimRoot']) {
        if (slotPaths.some(value => overlaps(value, c.paths[protectedName]))) reject(`executionSlots[${i}].paths`, 'outside-protected-path', `no overlap with paths.${protectedName}`, true);
      }
      for (const other of executionSlots.slice(i + 1)) {
        if (slotPaths.some(value => Object.values(other.paths).some(candidate => overlaps(value, candidate)))) reject(`executionSlots[${i}].paths`, 'nonoverlapping-slot-paths', 'no overlap with any other slot path', true);
      }
      // A worker-writable root cannot contain an installed helper/config.
      const writableRoots = ['workRoot', 'attemptRoot', 'diagnosticsRoot'].map(name => executionSlots[i].paths[name]);
      if (writableRoots.some((value, index) => writableRoots.slice(index + 1).some(other => overlaps(value, other)))) reject(`executionSlots[${i}].paths`, 'nonoverlapping-writable-roots', 'independent work/attempt/diagnostics roots', true);
      for (const writable of ['workRoot', 'attemptRoot', 'diagnosticsRoot']) {
        for (const readonly of ['dispatch', 'launcher', 'diagnosticsConfig', 'diagnosticsStore']) {
          if (overlaps(executionSlots[i].paths[writable], executionSlots[i].paths[readonly])) reject(`executionSlots[${i}].paths.${writable}`, 'outside-readonly-path', `no overlap with slot paths.${readonly}`, true);
        }
      }
    }
  }
  if (/(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]{20,}|PRIVATE KEY/.test(JSON.stringify(c))) reject('configuration', 'secret-free-input', 'no credential markers', true);
  const resolved = structuredClone(c);
  resolved.defaultProfile.effort = resolveExecutionDefaults(profile).effort;
  if (multiple) for (const repository of repositories) validateConsumer(selectRepositoryConsumer(resolved, repository));
  return freeze(resolved);
}

export function loadConsumer(pathname) {
  if (typeof pathname !== 'string' || !pathname || !isAbsolute(pathname)) reject('configurationPath', 'absolute-config-path', 'explicit absolute consumer path', pathname);
  let phase = 'lstat';
  try {
    const stat = lstatSync(pathname);
    requireConfig(stat.isFile() && !stat.isSymbolicLink(), 'configurationPath', 'regular-config-file', 'regular nonsymlink file', stat.isFile() && !stat.isSymbolicLink());
    requireConfig(stat.size <= 128 * 1024, 'configurationPath', 'bounded-config-file', 'at most 131072 bytes', stat.size);
    requireConfig(!(stat.mode & 0o022), 'configurationPath', 'protected-config-mode', 'no group/other write bits', stat.mode & 0o022);
    phase = 'read'; const source = readFileSync(pathname, 'utf8');
    phase = 'parse'; const parsed = parseConsumerJson(source);
    phase = 'validate'; return validateConsumer(parsed);
  } catch (error) {
    if (error?.code === 'CONSUMER_CONFIG_INVALID') throw error;
    reject('configurationPath', `config-${phase}`, 'readable valid consumer JSON', undefined, error);
  }
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
      if (!keys || keys.has(key)) reject('json.object.keys', 'unique-json-keys', 'unique keys including escaped equivalents', true);
      keys.add(key);
    }
  }
  return value;
}

// The privileged entrypoint additionally proves every parent is root-owned.
// The root-owned env-i wrapper supplies this path, never request JSON or a PR.
export function assertRootConsumer(pathname) {
  if (typeof pathname !== 'string' || !pathname || !isAbsolute(pathname)) reject('configurationPath', 'absolute-config-path', 'explicit absolute consumer path', pathname);
  for (let at = pathname; ; at = dirname(at)) {
    const stat = lstatSync(at);
    if (stat.uid !== 0 || stat.isSymbolicLink() || (stat.mode & 0o022)) reject('configurationPath.ancestors', 'root-owned-config-path', 'root-owned nonsymlink path without group/other write', stat.uid !== 0 ? stat.uid : stat.mode & 0o022);
    if (at === '/') break;
  }
}
// Desired pool capacity controls physical runner occupancy, not an admitted
// attempt's immutable identity. Managed configurations keep all resource-slot
// bindings stable so changing capacity cannot strand original-run recovery.
// Every runtime identity, helper, path and repository binding remains hashed.
export const consumerDigest = c => createHash('sha256').update(JSON.stringify(c.generalRunnerPool
  ? { ...c, generalRunnerPool: {} } : c)).digest('hex');

export const configuredRepositories = c => c.repositories ?? [c.repository];

// Repository selection changes only the process-local resource view. The
// complete installation remains the immutable digest and shared lock boundary.
export function selectRepositoryConsumer(c, repository) {
  if (!c.repositories) {
    if (repository !== undefined && repository !== c.repository) reject('repositorySelection', 'configured-repository', 'selected repository equals configured repository', repository);
    return c;
  }
  if (!c.repositories.includes(repository)) reject('repositorySelection', 'configured-repository', 'explicit member of configured repositories', repository);
  const { repositories, repositoryRuntimeUsers, ...shared } = c;
  const runtimeUser = repositoryRuntimeUsers?.[repository] ?? c.runtimeUser;
  const pathsForRepository = paths => ({ ...paths, ...Object.fromEntries(REPOSITORY_PATH_NAMES
    .map(name => [name, `${paths[name]}/repositories/${repository}`])) });
  const selected = { ...shared, repository, runtimeUser, paths: pathsForRepository(c.paths) };
  if (c.executionSlots) selected.executionSlots = c.executionSlots.map(slot => ({ ...slot,
    runtimeUser: repositoryRuntimeUsers?.[repository] !== undefined && slot.runtimeUser === c.runtimeUser
      ? runtimeUser : slot.runtimeUser,
    paths: pathsForRepository(slot.paths) }));
  return freeze(selected);
}

export function resolveExecutionConsumer(c, slotId) {
  if (!c.executionSlots) {
    if (slotId !== undefined && slotId !== null) reject('executionSlotSelection', 'configured-slot', 'no slot selection for a serial configuration', slotId);
    return c;
  }
  const slot = c.executionSlots.find(value => value.id === (slotId ?? 'primary'));
  if (!slot) reject('executionSlotSelection', 'configured-slot', 'explicit configured slot or preserved primary', slotId);
  return freeze({ ...c, runtimeUser: slot.runtimeUser, workGroup: slot.workGroup, paths: { ...c.paths, ...slot.paths } });
}

export function selectExecutionSlot(c, { runnerName, uid, uidForUser }) {
  if (!c.executionSlots) return undefined;
  const slot = c.executionSlots.find(value => value.runnerName === runnerName);
  if (!slot) reject('runnerName', 'configured-runner', 'runner bound to a configured execution slot', runnerName);
  if (!Number.isSafeInteger(uid) || uid < 1) reject('runnerUid', 'positive-native-uid', 'positive safe integer runner UID', uid);
  if (uidForUser(slot.runnerUser) !== uid) reject('runnerUid', 'configured-runner-uid', 'actual UID equals configured runner user UID', uid);
  return slot.id;
}
