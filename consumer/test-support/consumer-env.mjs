import { fileURLToPath } from 'node:url';

// Test harness only. Production has no default consumer.
process.env.RELAY_CONSUMER_CONFIG ??= fileURLToPath(new URL('../fixtures/example.json', import.meta.url));
