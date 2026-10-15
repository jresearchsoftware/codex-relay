import { executionConsumer } from '../../consumer/consumer.mjs';
import { createAttemptStore } from './attempt-store.mjs';

// Root always selects retained runner evidence through its own immutable
// publication record. Request JSON cannot supply a journal path or slot.
export function createSlotJournal(store, { createStore = createAttemptStore } = {}) {
  return {
    async get(runId) {
      const record = await store.get(runId);
      if (!record?.envelope) return null;
      return createStore(executionConsumer(record.envelope.executionSlot).paths.attemptRoot).get(runId);
    }
  };
}
