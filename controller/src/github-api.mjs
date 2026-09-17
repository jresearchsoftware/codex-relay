import { CONSUMER } from '../../consumer/consumer.mjs';
import { REPOSITORY, fail } from './execution-contract.mjs';
export function createGithubApi({ token, runToken, fetchImpl = fetch } = {}) {
  async function request(path, method = 'GET', body, credential = token) {
    const response = await fetchImpl(`https://api.github.com/repos/${REPOSITORY}${path}`, {
      method, headers: { accept: 'application/vnd.github+json', authorization: `Bearer ${credential}`,
        'x-github-api-version': '2022-11-28', 'content-type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(15000) });
    if (!response.ok) throw Object.assign(new Error('GITHUB_REQUEST_FAILED'), { code: 'GITHUB_REQUEST_FAILED', status: response.status });
    return response.status === 204 ? null : response.json();
  }
  return {
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
      if (!response.ok) fail('OWNER_METADATA_ACTOR_REQUIRED');
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
      const result = await response.json();
      if (!response.ok || result.errors?.length) fail('READY_MUTATION_FAILED');
    },
    async draft(id) {
      const response = await fetchImpl('https://api.github.com/graphql', { method: 'POST',
        headers: { authorization: `Bearer ${token}`, 'content-type': 'application/json' },
        body: JSON.stringify({ query: 'mutation($id:ID!){convertPullRequestToDraft(input:{pullRequestId:$id}){pullRequest{id}}}', variables: { id } }),
        signal: AbortSignal.timeout(15000) });
      const result = await response.json();
      if (!response.ok || result.errors?.length) fail('DRAFT_MUTATION_FAILED');
    }
  };
}
