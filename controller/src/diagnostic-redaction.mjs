// Pure diagnostic text handling. No consumer, credential, store or runtime
// configuration is loaded, so fixed clients can use the same redactor at boot.
function replaceExact(text, value, replacement) {
  if (typeof value !== "string" || value.length === 0) return text;
  return text.split(value).join(replacement);
}

export function redactSecrets(value, { codexAccessToken = "", githubToken = "", knownSecrets = [], inputTruncated = false } = {}) {
  let text = String(value ?? "");
  if (inputTruncated) for (const secret of [codexAccessToken, githubToken, ...knownSecrets]) {
    if (typeof secret !== 'string' || !secret) continue;
    for (let length = Math.min(secret.length - 1, text.length); length > 0; length--) {
      if (text.endsWith(secret.slice(0, length))) { text = text.slice(0, -length) + '[REDACTED_PARTIAL_SECRET]'; break; }
    }
  }
  text = replaceExact(text, codexAccessToken, "[REDACTED_CODEX_ACCESS_TOKEN]");
  text = replaceExact(text, githubToken, "[REDACTED_GITHUB_TOKEN]");
  for (const secret of knownSecrets) text = replaceExact(text, secret, "[REDACTED_SECRET]");
  text = text.replace(/("(?:authorization|cookie|password|passwd|secret|token|api[_-]?key|access[_-]?token|private[_-]?key)"\s*:\s*)"(?:\\.|[^"\\])*(?:"|\\?$)/gi, '$1"[REDACTED_SECRET]"');
  text = text.replace(/-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?(?:-----END [^-]*PRIVATE KEY-----|$)/gi, "[REDACTED_PRIVATE_KEY]");
  text = text.replace(/\b(authorization\s*:\s*basic)\s+[^\s,;]+/gi, "$1 [REDACTED_BASIC_AUTH]");
  text = text.replace(/\b(?:authorization\s*:\s*bearer|bearer)\s+[^\s,;]+/gi, match => `${match.slice(0, match.toLowerCase().indexOf("bearer") + 6)} [REDACTED_BEARER]`);
  text = text.replace(/\b(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]+/g, "[REDACTED_GITHUB_TOKEN]");
  text = text.replace(/\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{12,}/g, "[REDACTED_API_KEY]");
  text = text.replace(/(https?:\/\/)[^\s/@:]+:[^\s/@]+@/gi, '$1[REDACTED_CREDENTIAL]@');
  text = text.replace(/\b(?:password|passwd|secret|token|api[_-]?key|access[_-]?token)\b\s*[:=]\s*[^\s,;"'\\}]+/gi, match => `${match.split(/[:=]/, 1)[0]}=[REDACTED_SECRET]`);
  return text;
}

export function redactDiagnosticText(value, { preserveNewlines = false, ...secrets } = {}) {
  return redactSecrets(value, secrets).replace(/[\u0000-\u001f\u007f-\u009f]/g, character => preserveNewlines && ["\n", "\r"].includes(character) ? character : " ");
}

export function boundedDiagnosticText(value, maxBytes, secrets = {}) {
  const redacted = redactDiagnosticText(value, secrets);
  const bytes = Buffer.byteLength(redacted, "utf8");
  const prefix = Buffer.from(redacted, "utf8").subarray(0, maxBytes);
  const fatal = new TextDecoder("utf-8", { fatal: true });
  let text;
  try { text = fatal.decode(prefix); }
  catch {
    text = "";
    for (let end = prefix.length - 1; end >= Math.max(0, prefix.length - 3); end -= 1) {
      try { text = fatal.decode(prefix.subarray(0, end)); break; } catch { /* Try the next safe prefix. */ }
    }
    if (text === "") text = new TextDecoder("utf-8").decode(prefix);
  }
  return { text, bytes, truncated: bytes > maxBytes };
}
