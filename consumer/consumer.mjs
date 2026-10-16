import { loadConsumer, consumerDigest, selectRepositoryConsumer, resolveExecutionConsumer, selectExecutionSlot } from './consumer-config.mjs';
import { execFileSync } from 'node:child_process';

// One immutable deployment snapshot per process. No repository-local search,
// implicit consumer, hot reload, or moving model-landscape lookup.
export const INSTALLATION_CONSUMER = loadConsumer(process.env.RELAY_CONSUMER_CONFIG);
export const CONSUMER_DIGEST = consumerDigest(INSTALLATION_CONSUMER);
export const CONSUMER = selectRepositoryConsumer(INSTALLATION_CONSUMER,
  process.env.RELAY_REPOSITORY ?? (INSTALLATION_CONSUMER.repositories ? process.env.GITHUB_REPOSITORY : undefined));
// Fixed installed wrappers pin the slot. The native routing runner supplies its
// configured name; actual UID is checked before admission. Root Writer uses the
// immutable stored envelope instead of this process-local resource view.
export const EXECUTION_SLOT = process.env.RELAY_EXECUTION_SLOT
  ?? CONSUMER.executionSlots?.find(slot => slot.runnerName === process.env.RUNNER_NAME)?.id;
export const executionConsumer = slotId => resolveExecutionConsumer(CONSUMER, slotId);
export const EXECUTION_CONSUMER = executionConsumer(EXECUTION_SLOT);
export function unixUserId(user) {
  const value = execFileSync('/usr/bin/id', ['-u', user], { encoding: 'utf8', env: { PATH: '/usr/bin:/bin', LANG: 'C', LC_ALL: 'C' }, timeout: 5000 }).trim();
  if (!/^[1-9][0-9]{0,9}$/.test(value) || !Number.isSafeInteger(Number(value))) throw Object.assign(new Error('EXECUTION_SLOT_IDENTITY_INVALID'), { code: 'EXECUTION_SLOT_IDENTITY_INVALID' });
  return Number(value);
}
export function runnerExecutionSlot({ runnerName = process.env.RUNNER_NAME, uid = process.getuid?.(), uidForUser = unixUserId } = {}) {
  return selectExecutionSlot(CONSUMER, { runnerName, uid, uidForUser });
}
