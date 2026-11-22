import { setTimeout as sleep } from 'node:timers/promises';
import { performance } from 'node:perf_hooks';
import { ambiguousGithubWrite, attachWriteReadback, githubEndpoint, networkCode } from './failure-report.mjs';
import { CONSUMER } from '../../consumer/consumer.mjs';
import { redactDiagnosticText } from './diagnostics.mjs';
import { REPOSITORY, fail } from './execution-contract.mjs';

async function captureResponseFailure(response, { code, operation, method, path, knownSecrets = [] }) {
  const capture = { availability: 'unavailable', bytes: 0, truncated: false };
  try {
    const reader = response.body?.getReader?.();
    if (reader) {
      const chunks = []; let bytes = 0;
      try {
        while (bytes <= 8192) {
          const value = await reader.read();
          if (value.done) break;
          bytes += value.value.byteLength;
          chunks.push(Buffer.from(value.value).subarray(0, Math.max(0, 8192 - (bytes - value.value.byteLength))));
          if (bytes > 8192) { capture.truncated = true; break; }
        }
      } finally {
        Object.assign(capture, { availability: 'available', bytes, text: redactDiagnosticText(Buffer.concat(chunks).toString('utf8'), { knownSecrets, inputTruncated: capture.truncated }) });
        try { await reader.cancel(); } catch (error) { capture.cancelFailure = { code: error?.code, message: error?.message }; }
      }
    }
  } catch (error) { capture.unavailableReason = error?.code ?? error?.name ?? 'RESPONSE_READ_FAILED';
    capture.readFailure = { code: error?.code, message: error?.message }; capture.truncated = capture.bytes > 0; }
  const error = Object.assign(new Error(code), { code, status: response.status });
  error.native = { operation, method, path, status: response.status, response: capture };
  return error;
}
function isRateLimited(response, error) {
  return response.status === 429 || response.status === 403 && (response.headers?.has('retry-after')
    || response.headers?.get('x-ratelimit-remaining') === '0'
    || /"message"\s*:\s*"(?:You have exceeded a secondary rate limit|API rate limit exceeded)\b/i.test(error.native.response.text ?? ''));
}

export async function responseFailure(response, options) {
  const error = await captureResponseFailure(response, options);
  const rateLimited = isRateLimited(response, error);
  error.details = { githubFailure: { method: options.method, endpoint: githubEndpoint(options.path),
    status: response.status, reason: rateLimited ? 'rate-limit' : 'http',
    ...(rateLimited ? { retryDelaySeconds: Math.max(1, Math.ceil(retryDelay(response.headers, true, Date.now()) / 1000)) } : {}),
    attempts: 1, stopped: options.method === 'GET' ? 'non-transient' : 'mutation' } };
  throw error;
}

const MAX_READ_ATTEMPTS = 3;
const READ_DEADLINE_MS = 48_000;
const READ_TIMEOUT_MS = 15_000;
const WRITE_TIMEOUT_MS = 15_000;
const transientStatuses = new Set([408, 500, 502, 503, 504]);

function retryDelay(headers, rateLimited, now) {
  const after = headers?.get('retry-after');
  let delay;
  if (/^[0-9]+$/.test(after ?? '')) delay = Number(after) * 1000;
  else if (after) {
    const date = Date.parse(after);
    if (Number.isFinite(date)) delay = Math.max(0, date - now);
  }
  const reset = headers?.get('x-ratelimit-reset');
  if (rateLimited && headers?.get('x-ratelimit-remaining') === '0' && /^[0-9]+$/.test(reset ?? '')) {
    delay = Math.max(delay ?? 0, Number(reset) * 1000 - now);
  }
  // GitHub's minimum for secondary limits without a usable provider delay.
  return delay ?? (rateLimited ? 60_000 : 0);
}

export function createGithubApi({ token, runToken, fetchImpl = fetch, signal,
  monotonic = () => performance.now(), wallTime = Date.now, wait = sleep, random = Math.random } = {}) {
  async function request(path, method = 'GET', body, credential = token, {
    absolute = false, operation = 'github-request', code = 'GITHUB_REQUEST_FAILED', graphql = false
  } = {}) {
    const read = method === 'GET';
    const timeout = read ? READ_TIMEOUT_MS : WRITE_TIMEOUT_MS;
    const deadline = monotonic() + (read ? READ_DEADLINE_MS : WRITE_TIMEOUT_MS);
    const overall = AbortSignal.timeout(read ? READ_DEADLINE_MS : WRITE_TIMEOUT_MS);
    const cancellation = signal ? AbortSignal.any([signal, overall]) : overall;
    const url = `https://api.github.com${absolute ? '' : `/repos/${REPOSITORY}`}${path}`;
    const payload = body === undefined ? undefined : JSON.stringify(body);
    let attempts = 0;
    let error;
    let reason;
    let status;
    let osCode;
    const observations = [];
    let stopped;
    for (;;) {
      if (signal?.aborted) { stopped = 'cancelled'; break; }
      const remaining = deadline - monotonic();
      if (remaining <= 0 || overall.aborted) { stopped = 'deadline'; break; }
      const timer = AbortSignal.timeout(Math.max(1, Math.ceil(Math.min(timeout, remaining))));
      const attemptSignal = AbortSignal.any([timer, cancellation]);
      let response;
      let retryMs = 0;
      status = undefined;
      osCode = undefined;
      reason = undefined;
      attempts++;
      try {
        response = await fetchImpl(url, {
          method, headers: { accept: 'application/vnd.github+json', authorization: `Bearer ${credential}`,
            'x-github-api-version': '2022-11-28', 'content-type': 'application/json' },
          body: payload, signal: attemptSignal, redirect: 'manual'
        });
        status = response.status;
        if (!response.ok) {
          error = await captureResponseFailure(response, { code, operation, method, path, knownSecrets: [credential].filter(Boolean) });
          const rateLimited = isRateLimited(response, error);
          reason = rateLimited ? 'rate-limit' : 'http';
          retryMs = retryDelay(response.headers, rateLimited, wallTime());
        } else {
          const decoded = status === 204 ? null : await response.json();
          if (!graphql || decoded?.data && !decoded.errors?.length) return decoded;
          reason = 'graphql-error';
          error = Object.assign(new Error(code), { code, native: { errors: decoded?.errors } });
        }
      } catch (cause) {
        osCode = networkCode(cause?.cause?.code ?? cause?.code);
        reason = signal?.aborted ? 'cancelled' : timer.aborted || overall.aborted || cause?.name === 'TimeoutError' || osCode === 'ETIMEDOUT'
          ? 'timeout' : cause instanceof SyntaxError ? 'invalid-response' : osCode ? 'network' : 'transport-unknown';
        error = new Error(code, { cause });
      }
      observations.push({ status, reason, osCode });
      const transient = reason === 'rate-limit' || transientStatuses.has(status) && reason === 'http'
        || reason === 'timeout' || reason === 'network' && !['ENOTFOUND', 'CERT_HAS_EXPIRED', 'UNABLE_TO_VERIFY_LEAF_SIGNATURE', 'SELF_SIGNED_CERT_IN_CHAIN'].includes(osCode);
      if (signal?.aborted) { stopped = 'cancelled'; break; }
      if (!read) { stopped = 'mutation'; break; }
      if (!transient) { stopped = 'non-transient'; break; }
      if (attempts === MAX_READ_ATTEMPTS) { stopped = 'attempt-limit'; break; }
      const jitter = Math.floor(250 * (1 + random()) * 2 ** (attempts - 1));
      const delay = retryMs + jitter;
      if (delay >= deadline - monotonic() || overall.aborted) {
        stopped = retryMs ? 'provider-delay' : 'deadline';
        break;
      }
      try { await wait(delay, undefined, { signal: cancellation }); }
      catch (cause) {
        if (!cancellation.aborted) throw cause;
        stopped = signal?.aborted ? 'cancelled' : 'deadline';
        break;
      }
    }
    error ??= new Error(code);
    error.code = code;
    error.status = status;
    error.native = { operation, method, path, ...error.native, observations };
    error.details = { ...error.details, githubFailure: { method, endpoint: githubEndpoint(path), status, osCode,
      reason: reason ?? (stopped === 'cancelled' ? 'cancelled' : 'timeout'), attempts, stopped } };
    throw error;
  }
  return {
    userIdentity(login) {
      // Callers select the configured publisher, never a worker-supplied actor.
      return request(`/users/${encodeURIComponent(login)}`, 'GET', undefined, token,
        { absolute: true, operation: 'publisher-identity', code: 'AUTHORITY_PUBLISHER_UNAVAILABLE' });
    },
    async ensureStepLabel(step) {
      if (!Number.isSafeInteger(step) || step < 1) fail('STEP_LABEL_INVALID');
      const name = `step-${step}`;
      try { await request(`/labels/${name}`); }
      catch (error) {
        if (error.status !== 404) throw error;
        try {
          await request('/labels', 'POST', { name, color: 'ededed',
            description: `Current logical Step ${step}; correlation only, never a launch command.` });
        } catch (writeError) {
          if (!ambiguousGithubWrite(writeError)) throw writeError;
          let label;
          try { label = await request(`/labels/${name}`); }
          catch (cause) { attachWriteReadback(writeError, cause.status === 404 ? 'not-observed' : 'unavailable', cause); throw writeError; }
          if (label?.name !== name) { attachWriteReadback(writeError, 'unavailable'); throw writeError; }
        }
      }
    },
    viewer() {
      return request('/user', 'GET', undefined, token,
        { absolute: true, operation: 'viewer-identity', code: 'OWNER_METADATA_ACTOR_REQUIRED' });
    },
    get: path => request(path), post: (path, body) => request(path, 'POST', body),
    patch: (path, body) => request(path, 'PATCH', body),
    delete: path => request(path, 'DELETE'),
    getRun: id => { if (!runToken) fail('WORKFLOW_READ_TOKEN_REQUIRED'); return request(`/actions/runs/${id}`, 'GET', undefined, runToken); },
    async list(path) {
      const result = [];
      for (let page = 1; page <= 100; page++) {
        const rows = await request(`${path}${path.includes('?') ? '&' : '?'}per_page=100&page=${page}`);
        if (!Array.isArray(rows)) fail('GITHUB_LIST_INVALID'); result.push(...rows);
        if (rows.length < 100) return result;
      }
      fail('GITHUB_PAGINATION_LIMIT');
    },
    async validations(head) {
      if (!runToken) fail('WORKFLOW_READ_TOKEN_REQUIRED');
      const result = [];
      for (let page = 1; page <= 20; page++) {
        const data = await request(`/actions/workflows/${encodeURIComponent(CONSUMER.validationWorkflow.split('/').at(-1))}/runs?head_sha=${head}&event=pull_request&per_page=100&page=${page}`, 'GET', undefined, runToken);
        if (!Array.isArray(data?.workflow_runs)) fail('GITHUB_VALIDATION_RUNS_INVALID'); result.push(...data.workflow_runs);
        if (data.workflow_runs.length < 100) return result;
      }
      fail('GITHUB_PAGINATION_LIMIT');
    },
    async ready(id) {
      await request('/graphql', 'POST', {
        query: 'mutation($id:ID!){markPullRequestReadyForReview(input:{pullRequestId:$id}){pullRequest{id}}}', variables: { id }
      }, token, { absolute: true, graphql: true, operation: 'mark-ready', code: 'READY_MUTATION_FAILED' });
    },
    async draft(id) {
      await request('/graphql', 'POST', {
        query: 'mutation($id:ID!){convertPullRequestToDraft(input:{pullRequestId:$id}){pullRequest{id}}}', variables: { id }
      }, token, { absolute: true, graphql: true, operation: 'mark-draft', code: 'DRAFT_MUTATION_FAILED' });
    }
  };
}
