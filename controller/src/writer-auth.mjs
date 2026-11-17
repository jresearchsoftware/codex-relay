import { CONSUMER } from '../../consumer/consumer.mjs';
import { createSign } from "node:crypto";
import { readFile, stat } from "node:fs/promises";
import { boundedDiagnosticText } from './diagnostic-redaction.mjs';
import { responseFailure } from './github-api.mjs';
const API_ROOT = "https://api.github.com";
const APP_ID = CONSUMER.writerApp.appId;
const INSTALLATION_ID = CONSUMER.writerApp.installationId;
const blocked = (code, message = code, observation) => Object.assign(new Error(message), { code,
  ...(observation ? { observation } : {}) });
const CREDENTIAL_ENV = CONSUMER.paths.credentialEnv;
const CREDENTIAL_KEY_FILE = CONSUMER.paths.credentialKeyFile;
export const WRITER_TOKEN_PERMISSIONS = Object.freeze({
  metadata: "read",
  contents: "write",
  issues: "write",
  pull_requests: "write",
  workflows: "write"
});
export const TASK_READ_TOKEN_PERMISSIONS = Object.freeze({
  metadata: 'read', issues: 'read', pull_requests: 'read'
});
export function parseEnv(text, expectedKeyFile) {
  const values = {};
  for (const [index, line] of text.split(/\r?\n/).entries()) {
    if (!line || line.startsWith("#")) continue;
    const match = line.match(/^([A-Z0-9_]+)=(.*)$/);
    if (!match || Object.hasOwn(values, match[1])) throw blocked('WRITER_IDENTITY_INVALID', 'Writer credential environment syntax is invalid',
      { check: 'writer-credential-env.syntax', expected: 'unique KEY=value records', observed: { line: index + 1, duplicate: Boolean(match) } });
    values[match[1]] = match[2];
  }
  if (values.GITHUB_APP_ID !== APP_ID || values.GITHUB_APP_INSTALLATION_ID !== INSTALLATION_ID || values.GITHUB_APP_PRIVATE_KEY_FILE !== expectedKeyFile) {
    throw blocked("WRITER_IDENTITY_INVALID", "The root-owned Writer identity contract is not the admitted App/installation/path", { check: 'writer-credential-env.binding',
      expected: { appId: APP_ID, installationId: INSTALLATION_ID, keyFile: expectedKeyFile },
      observed: { appId: values.GITHUB_APP_ID ?? null, installationId: values.GITHUB_APP_INSTALLATION_ID ?? null, keyFile: values.GITHUB_APP_PRIVATE_KEY_FILE ?? null } });
  }
  return values;
}

async function credentials() {
  const env = parseEnv(await readFile(CREDENTIAL_ENV, "utf8"), CREDENTIAL_KEY_FILE);
  const envStat = await stat(CREDENTIAL_ENV);
  const keyStat = await stat(CREDENTIAL_KEY_FILE);
  if (envStat.uid !== 0 || keyStat.uid !== 0 || (envStat.mode & 0o077) !== 0 || (keyStat.mode & 0o077) !== 0) throw blocked("WRITER_CREDENTIAL_BOUNDARY_INVALID", "Writer credential files must remain root-only", { check: 'writer-credentials.metadata', expected: { uid: 0, privateBits: 0 },
    observed: { envUid: envStat.uid, keyUid: keyStat.uid, envPrivateBits: envStat.mode & 0o077, keyPrivateBits: keyStat.mode & 0o077 } });
  return { key: await readFile(CREDENTIAL_KEY_FILE, "utf8") };
}

function b64url(value) { return Buffer.from(value).toString("base64").replaceAll("+", "-").replaceAll("/", "_").replaceAll(/=+$/g, ""); }

async function appJwt() {
  const { key } = await credentials();
  const now = Math.floor(Date.now() / 1000);
  const header = b64url(JSON.stringify({ alg: "RS256", typ: "JWT" }));
  const payload = b64url(JSON.stringify({ iat: now - 60, exp: now + 540, iss: APP_ID }));
  const signer = createSign("RSA-SHA256");
  signer.update(`${header}.${payload}`);
  return `${header}.${payload}.${b64url(signer.sign(key))}`;
}

export async function http(path, { method = "GET", token, jwt, body } = {}) {
  const headers = { accept: "application/vnd.github+json", "x-github-api-version": "2022-11-28", "user-agent": "codex-relay-writer" };
  if (token) headers.authorization = `Bearer ${token}`;
  if (jwt) headers.authorization = `Bearer ${jwt}`;
  if (body !== undefined) headers["content-type"] = "application/json";
  const response = await fetch(`${API_ROOT}${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  if (!response.ok) return responseFailure(response, { code: 'GITHUB_MUTATION_FAILED', operation: 'writer-authentication', method, path,
    knownSecrets: [token, jwt].filter(Boolean) });
  const text = await response.text();
  let value;
  try { value = text ? JSON.parse(text) : {}; }
  catch (cause) {
    const error = blocked('WRITER_TOKEN_INVALID', 'GitHub installation-token response is not valid JSON', {
      check: 'writer-token.response-json', expected: 'JSON object',
      observed: { status: response.status, body: boundedDiagnosticText(text, 4096, { knownSecrets: [token, jwt].filter(Boolean) }) } });
    Object.defineProperty(error, 'runtimeCause', { value: cause });
    throw error;
  }

  return value;
}

export async function taskReadToken(repository) {
  // The root lifecycle adapter selects this identity from the protected current
  // configuration or authenticated retained compatibility configuration. Never
  // accept a repository selector from worker or admission command arguments.
  if (typeof repository !== 'string' || !/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repository)
    || repository.split('/').some(part => part === '.' || part === '..')) throw blocked('WRITER_IDENTITY_INVALID');
  return installationToken(repository, TASK_READ_TOKEN_PERMISSIONS);
}

async function installationToken(repository, permissions) {
  const payload = await http(`/app/installations/${INSTALLATION_ID}/access_tokens`, {
    method: "POST",
    jwt: await appJwt(),
    body: { repositories: [repository.split('/')[1]], permissions }
  });
  if (typeof payload?.token !== "string" || !payload.token || typeof payload.expires_at !== "string") throw blocked("WRITER_TOKEN_INVALID", "GitHub did not return a bounded installation token", { check: 'writer-token.fields', expected: 'nonempty token and expiry string',
    observed: { token: typeof payload?.token === 'string' && payload.token.length > 0 ? 'present_redacted' : 'unavailable', expiryType: typeof payload?.expires_at } });
  const expiry = Date.parse(payload.expires_at);
  if (!Number.isFinite(expiry) || expiry <= Date.now() || expiry > Date.now() + 70 * 60 * 1000) throw blocked("WRITER_TOKEN_INVALID", "Writer installation token lifetime is outside the bounded contract", { check: 'writer-token.expiry',
    expected: 'future expiry within 70 minutes', observed: payload.expires_at });
  return payload.token;
}

export async function token() {
  return installationToken(CONSUMER.repository, WRITER_TOKEN_PERMISSIONS);
}
