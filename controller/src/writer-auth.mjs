import { CONSUMER } from '../../consumer/consumer.mjs';
import { createSign } from "node:crypto";
import { readFile, stat } from "node:fs/promises";
const API_ROOT = "https://api.github.com";
const APP_ID = CONSUMER.writerApp.appId;
const INSTALLATION_ID = CONSUMER.writerApp.installationId;
const blocked = (code) => Object.assign(new Error(code), { code });
const CREDENTIAL_ENV = CONSUMER.paths.credentialEnv;
const CREDENTIAL_KEY_FILE = CONSUMER.paths.credentialKeyFile;
export const WRITER_TOKEN_PERMISSIONS = Object.freeze({
  metadata: "read",
  contents: "write",
  issues: "write",
  pull_requests: "write",
  workflows: "write"
});
export function parseEnv(text, expectedKeyFile) {
  const values = {};
  for (const line of text.split(/\r?\n/)) {
    if (!line || line.startsWith("#")) continue;
    const match = line.match(/^([A-Z0-9_]+)=(.*)$/);
    if (!match || Object.hasOwn(values, match[1])) throw blocked("WRITER_IDENTITY_INVALID");
    values[match[1]] = match[2];
  }
  if (values.GITHUB_APP_ID !== APP_ID || values.GITHUB_APP_INSTALLATION_ID !== INSTALLATION_ID || values.GITHUB_APP_PRIVATE_KEY_FILE !== expectedKeyFile) {
    throw blocked("WRITER_IDENTITY_INVALID", "The root-owned Writer identity contract is not the admitted App/installation/path");
  }
  return values;
}

async function credentials() {
  const env = parseEnv(await readFile(CREDENTIAL_ENV, "utf8"), CREDENTIAL_KEY_FILE);
  const envStat = await stat(CREDENTIAL_ENV);
  const keyStat = await stat(CREDENTIAL_KEY_FILE);
  if (envStat.uid !== 0 || keyStat.uid !== 0 || (envStat.mode & 0o077) !== 0 || (keyStat.mode & 0o077) !== 0) throw blocked("WRITER_CREDENTIAL_BOUNDARY_INVALID", "Writer credential files must remain root-only");
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
  const text = await response.text();
  let value;
  try { value = text ? JSON.parse(text) : {}; } catch { value = {}; }
  if (!response.ok) throw blocked("GITHUB_MUTATION_FAILED", `GitHub ${method} ${path} returned ${response.status}`);
  return value;
}

export async function token() {
  const payload = await http(`/app/installations/${INSTALLATION_ID}/access_tokens`, {
    method: "POST",
    jwt: await appJwt(),
    body: { repositories: [CONSUMER.repository.split('/')[1]], permissions: WRITER_TOKEN_PERMISSIONS }
  });
  if (typeof payload.token !== "string" || !payload.token || typeof payload.expires_at !== "string") throw blocked("WRITER_TOKEN_INVALID", "GitHub did not return a bounded installation token");
  const expiry = Date.parse(payload.expires_at);
  if (!Number.isFinite(expiry) || expiry <= Date.now() || expiry > Date.now() + 70 * 60 * 1000) throw blocked("WRITER_TOKEN_INVALID", "Writer installation token lifetime is outside the bounded contract");
  return payload.token;
}
