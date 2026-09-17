// The model owns only decision-bearing task semantics. Git inventory,
// authority, execution profile, and publication metadata are derived by the
// trusted Writer/runtime after the native process has completed.
export const CODEX_RESULT_SCHEMA = Object.freeze({
  $schema: "http://json-schema.org/draft-07/schema#",
  title: "Unified governed Codex semantic result",
  type: "object",
  additionalProperties: false,
  required: ["status", "summary", "validation", "blockedReason"],
  properties: {
    status: { type: "string", enum: ["success", "blocked"] },
    summary: { type: "string", maxLength: 16 * 1024 },
    validation: {
      type: "array",
      maxItems: 64,
      items: { type: "string", maxLength: 512 }
    },
    blockedReason: { type: "string", maxLength: 2 * 1024 }
  }
});

const RESULT_KEYS = Object.freeze(["status", "summary", "validation", "blockedReason"]);
const MAX_SUMMARY_BYTES = 16 * 1024;
const MAX_BLOCKED_REASON_BYTES = 2 * 1024;
const MAX_VALIDATION_CLAIM_BYTES = 512;
const CODEX_RUNTIME_IDENTIFIER_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$/;

export function isBoundedCodexRuntimeIdentifier(value) {
  return typeof value === "string" && value !== "UNAVAILABLE" && CODEX_RUNTIME_IDENTIFIER_PATTERN.test(value);
}

function boundedString(value, field, maximumBytes, { allowEmpty = true } = {}) {
  if (typeof value !== "string" || (!allowEmpty && value.trim() === "")) {
    throw new Error(`CODEX_RESULT_${field.toUpperCase()}_INVALID`);
  }
  if (Buffer.byteLength(value, "utf8") > maximumBytes || /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(value)) {
    throw new Error(`CODEX_RESULT_${field.toUpperCase()}_INVALID`);
  }
  return value;
}

// JSON Schema validation is enforced by the governed launcher. This second
// bounded normalizer protects unit/integration seams that inject a fake child
// process and therefore bypass the launcher itself.
export function normalizeCodexSemanticResult(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("CODEX_RESULT_OBJECT_INVALID");
  const keys = Object.keys(value).sort().join("\0");
  if (keys !== [...RESULT_KEYS].sort().join("\0")) throw new Error("CODEX_RESULT_FIELDS_INVALID");
  if (value.status !== "success" && value.status !== "blocked") throw new Error("CODEX_RESULT_STATUS_INVALID");
  const summary = boundedString(value.summary, "summary", MAX_SUMMARY_BYTES, { allowEmpty: value.status === "blocked" });
  if (!Array.isArray(value.validation) || value.validation.length > 64 || value.validation.some(item => typeof item !== "string" || Buffer.byteLength(item, "utf8") > MAX_VALIDATION_CLAIM_BYTES || /[\u0000-\u001f\u007f]/.test(item))) {
    throw new Error("CODEX_RESULT_VALIDATION_INVALID");
  }
  const blockedReason = boundedString(value.blockedReason, "blockedReason", MAX_BLOCKED_REASON_BYTES);
  if (value.status === "success" && blockedReason.trim() !== "") throw new Error("CODEX_RESULT_BLOCKED_REASON_INVALID");
  if (value.status === "blocked" && blockedReason.trim() === "") throw new Error("CODEX_RESULT_BLOCKED_REASON_INVALID");
  return { status: value.status, summary, validation: [...value.validation], blockedReason };
}
