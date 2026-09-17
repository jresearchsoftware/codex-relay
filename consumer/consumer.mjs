import { loadConsumer, consumerDigest } from './consumer-config.mjs';

// One immutable deployment snapshot per process. No repository-local search,
// implicit consumer, hot reload, or moving model-landscape lookup.
export const CONSUMER = loadConsumer(process.env.RELAY_CONSUMER_CONFIG);
export const CONSUMER_DIGEST = consumerDigest(CONSUMER);
