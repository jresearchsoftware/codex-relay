import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { CONSUMER, CONSUMER_DIGEST } from '../../consumer/consumer.mjs';
import { REPOSITORY, WRITER } from '../src/execution-contract.mjs';
import { createAdmissionControl } from '../src/admission-control.mjs';
import { createPublicationBroker } from '../src/publication-broker.mjs';
import { labelRunName } from '../src/launch-metadata.mjs';
import { memoryStore } from './fixture.mjs';

const charter = 'Authority model: github-native-v1\nIssue closure policy: keep-open\nImplement independent source/research work.';
const copy = value => structuredClone(value);

export async function harness(t) {
  const root = await mkdtemp(join(tmpdir(), 'relay-independent-admission-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const store = memoryStore(); const journal = memoryStore();
  const control = createAdmissionControl({ root, consumerDigest: CONSUMER_DIGEST, store, journal, protectedRoot: false });
  await control.initialize();
  const issues = new Map([42, 44].map(number => [number, { id: number + 1000, number, title: `Task ${number} — Source work`,
    state: 'open', user: { login: CONSUMER.owner }, body: charter, labels: [] }]));
  const runs = new Map(); const events = new Map(); const comments = [];
  let eventId = 1000; let command = 0; let deletes = 0;
  const api = {
    getRun: async id => copy(runs.get(id)),
    userIdentity: async login => ({ login, id: 701, type: 'Bot' }),
    async get(path) {
      if (/^\/issues\/(42|44)$/.test(path)) return copy(issues.get(Number(path.split('/')[2])));
      if (path.startsWith('/git/ref/heads/')) return { object: { sha: 'a'.repeat(40) } };
      if (path.startsWith('/git/matching-refs/heads/')) return [];
      throw new Error(`Unexpected GET ${path}`);
    },
    async list(path) {
      if (path.endsWith('/events')) return copy(events.get(Number(path.split('/')[2])) ?? []);
      if (path.endsWith('/comments')) return copy(comments.filter(comment => comment.number === Number(path.split('/')[2])));
      if (path.startsWith('/pulls?')) return [];
      throw new Error(`Unexpected LIST ${path}`);
    },
    ensureStepLabel: async () => {},
    async post(path, data) {
      const number = Number(path.split('/')[2]);
      if (path.endsWith('/labels')) {
        const issue = issues.get(number);
        for (const name of data.labels) if (!issue.labels.some(label => label.name === name)) issue.labels.push({ name });
        return copy(issue.labels);
      }
      if (path.endsWith('/comments')) {
        const comment = { id: comments.length + 5000, number, user: { login: WRITER }, body: data.body };
        comments.push(comment); return copy(comment);
      }
      throw new Error(`Unexpected POST ${path}`);
    },
    async delete(path) {
      const number = Number(path.split('/')[2]); const name = decodeURIComponent(path.split('/').at(-1));
      issues.get(number).labels = issues.get(number).labels.filter(label => label.name !== name);
      if (name.startsWith('codex-ready-')) {
        deletes++;
        events.get(number).push({ id: ++eventId, event: 'unlabeled', label: { name },
          actor: { login: WRITER, type: 'Bot' }, created_at: new Date(Date.UTC(2026, 8, 4, 12, 0, command * 3 + 1)).toISOString() });
      }
    }
  };
  const broker = createPublicationBroker({ api, store, journal, admission: control, publisher: {} });
  function ready(runId, number, route) {
    command++;
    const issue = issues.get(number); const launch = { target: 'issue', number, route };
    const at = Date.UTC(2026, 8, 4, 12, 0, command * 3);
    issue.labels.push({ name: `codex-ready-${route}` });
    const history = events.get(number) ?? [];
    history.push({ id: ++eventId, event: 'labeled', label: { name: `codex-ready-${route}` },
      actor: { login: CONSUMER.owner, type: 'User' }, created_at: new Date(at).toISOString() });
    events.set(number, history);
    runs.set(runId, { id: runId, repository: { full_name: REPOSITORY }, actor: { login: CONSUMER.owner },
      status: 'in_progress', event: 'issues', head_branch: CONSUMER.baseBranch,
      display_title: labelRunName(launch, issue), path: CONSUMER.routingWorkflow, run_attempt: 1,
      created_at: new Date(at + 1000).toISOString() });
    return { operation: 'admit', runId, ...launch, transport: 'label', step: null };
  }
  function replaceReady(number, route) {
    const at = new Date(Date.UTC(2026, 8, 4, 12, 0, command * 3 + 1)).toISOString();
    const issue = issues.get(number);
    for (const label of issue.labels.filter(label => label.name.startsWith('codex-ready-')))
      events.get(number).push({ id: ++eventId, event: 'unlabeled', label: copy(label),
        actor: { login: CONSUMER.owner, type: 'User' }, created_at: at });
    issue.labels = issue.labels.filter(label => !label.name.startsWith('codex-ready-'));
    issue.labels.push({ name: `codex-ready-${route}` });
    events.get(number).push({ id: ++eventId, event: 'labeled', label: { name: `codex-ready-${route}` },
      actor: { login: CONSUMER.owner, type: 'User' }, created_at: at });
  }
  return { broker, api, control, store, journal, issues, runs, events, comments, ready, replaceReady, deletes: () => deletes };
}
