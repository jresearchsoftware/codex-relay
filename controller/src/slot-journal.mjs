import { INSTALLATION_CONSUMER } from '../../consumer/consumer.mjs';
import { selectRepositoryConsumer, resolveExecutionConsumer } from '../../consumer/consumer-config.mjs';
import { createAttemptStore } from './attempt-store.mjs';

// Root always selects retained runner evidence through its own immutable
// publication record. Request JSON cannot supply a journal path or slot.
export function createSlotJournal(store, { createStore = createAttemptStore } = {}) {
  return {
    async get(runId, repository) {
      const record = await store.get(runId, repository);
      if (!record?.envelope) return null;
      const consumer = resolveExecutionConsumer(selectRepositoryConsumer(INSTALLATION_CONSUMER,
        record.envelope.repository), record.envelope.executionSlot);
      return createStore(consumer.paths.attemptRoot, { repository: record.envelope.repository }).get(runId);
    }
  };
}
