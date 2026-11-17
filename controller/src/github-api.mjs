import { CONSUMER } from '../../consumer/consumer.mjs';
import { redactDiagnosticText } from './diagnostics.mjs';
import { REPOSITORY, fail } from './execution-contract.mjs';

export async function responseFailure(response, { code, operation, method, path, knownSecrets = [] }) {
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
  throw error;
}
export function createGithubApi({ token, runToken, fetchImpl = fetch } = {}) {
  async function request(path, method = 'GET', body, credential = token) {
    let response;
    try { response = await fetchImpl(`https://api.github.com/repos/${REPOSITORY}${path}`, {
      method, headers: { accept: 'application/vnd.github+json', authorization: `Bearer ${credential}`,
        'x-github-api-version': '2022-11-28', 'content-type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(15000) }); }
    catch (cause) { throw Object.assign(new Error('GITHUB_REQUEST_FAILED', { cause }), {
      code: 'GITHUB_REQUEST_FAILED', native: { operation: 'github-request', method, path } }); }
    if (!response.ok) return responseFailure(response, { code: 'GITHUB_REQUEST_FAILED', operation: 'github-request', method, path, knownSecrets: [credential].filter(Boolean) });
    return response.status === 204 ? null : response.json();
  }
  return {
    async userIdentity(login) {
      // Callers select the configured publisher, never a worker-supplied actor.
      const response = await fetchImpl(`https://api.github.com/users/${encodeURIComponent(login)}`, {
        headers: { accept: 'application/vnd.github+json', authorization: `Bearer ${token}`,
          'x-github-api-version': '2022-11-28' }, signal: AbortSignal.timeout(15000) });
      if (!response.ok) return responseFailure(response, { code: 'AUTHORITY_PUBLISHER_UNAVAILABLE', operation: 'publisher-identity', method: 'GET', path: '/users/configured-publisher' });
      return response.json();
    },
    async ensureStepLabel(step) {
      if (!Number.isSafeInteger(step) || step < 1) fail('STEP_LABEL_INVALID');
      const name = `step-${step}`;
      try { await request(`/labels/${name}`); }
      catch (error) {
        if (error.status !== 404) throw error;
        await request('/labels', 'POST', { name, color: 'ededed', description: `Current logical Step ${step}; correlation only, never a launch command.` });
      }
    },
    async viewer() {
      const response = await fetchImpl('https://api.github.com/user', {
        headers: { accept: 'application/vnd.github+json', authorization: `Bearer ${token}`, 'x-github-api-version': '2022-11-28' },
        signal: AbortSignal.timeout(15000) });
      if (!response.ok) return responseFailure(response, { code: 'OWNER_METADATA_ACTOR_REQUIRED', operation: 'viewer-identity', method: 'GET', path: '/user' });
      return response.json();
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
        if (!Array.isArray(data.workflow_runs)) fail('GITHUB_VALIDATION_RUNS_INVALID'); result.push(...data.workflow_runs);
        if (data.workflow_runs.length < 100) return result;
      }
      fail('GITHUB_PAGINATION_LIMIT');
    },
    async ready(id) {
      const response = await fetchImpl('https://api.github.com/graphql', { method: 'POST',
        headers: { authorization: `Bearer ${token}`, 'content-type': 'application/json' },
        body: JSON.stringify({ query: 'mutation($id:ID!){markPullRequestReadyForReview(input:{pullRequestId:$id}){pullRequest{id}}}', variables: { id } }),
        signal: AbortSignal.timeout(15000) });
      if (!response.ok) return responseFailure(response, { code: 'READY_MUTATION_FAILED', operation: 'mark-ready', method: 'POST', path: '/graphql' });
      const result = await response.json();
      if (result.errors?.length) throw Object.assign(new Error('READY_MUTATION_FAILED'), { code: 'READY_MUTATION_FAILED',
        native: { operation: 'mark-ready', status: response.status, errors: result.errors } });
    },
    async draft(id) {
      const response = await fetchImpl('https://api.github.com/graphql', { method: 'POST',
        headers: { authorization: `Bearer ${token}`, 'content-type': 'application/json' },
        body: JSON.stringify({ query: 'mutation($id:ID!){convertPullRequestToDraft(input:{pullRequestId:$id}){pullRequest{id}}}', variables: { id } }),
        signal: AbortSignal.timeout(15000) });
      if (!response.ok) return responseFailure(response, { code: 'DRAFT_MUTATION_FAILED', operation: 'mark-draft', method: 'POST', path: '/graphql' });
      const result = await response.json();
      if (result.errors?.length) throw Object.assign(new Error('DRAFT_MUTATION_FAILED'), { code: 'DRAFT_MUTATION_FAILED',
        native: { operation: 'mark-draft', status: response.status, errors: result.errors } });
    }
  };
}
