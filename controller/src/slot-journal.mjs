import { INSTALLATION_CONSUMER } from '../../consumer/consumer.mjs';
import { selectRepositoryConsumer, resolveExecutionConsumer } from '../../consumer/consumer-config.mjs';
import { createAttemptStore } from './attempt-store.mjs';

// Root always selects retained runner evidence through its own immutable
// publication record. Request JSON cannot supply a journal path or slot.
export function createSlotJournal(store, { createStore = createAttemptStore } = {}) {
  async function originalStore(runId) {
    const record = await store.get(runId);
    if (!record?.envelope) throw new Error('ATTEMPT_NOT_ADMITTED');
    const consumer = resolveExecutionConsumer(selectRepositoryConsumer(INSTALLATION_CONSUMER,
      record.envelope.repository), record.envelope.executionSlot);
    return createStore(consumer.paths.attemptRoot, { repository: record.envelope.repository });
  }
  return {
    async withLock(runId, action) { return (await originalStore(runId)).withLock(runId, action); },
    async get(runId, repository) {
      const record = await store.get(runId, repository);
      if (!record?.envelope) return null;
      const consumer = resolveExecutionConsumer(selectRepositoryConsumer(INSTALLATION_CONSUMER,
        record.envelope.repository), record.envelope.executionSlot);
      return createStore(consumer.paths.attemptRoot, { repository: record.envelope.repository }).get(runId);
    }
  };
}
