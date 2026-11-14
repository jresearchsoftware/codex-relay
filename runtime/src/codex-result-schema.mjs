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
// JSON Schema maxLength counts Unicode codepoints, not UTF-8 bytes or UTF-16 units.
const MAX_SUMMARY_CHARACTERS = 16 * 1024;
const MAX_BLOCKED_REASON_CHARACTERS = 2 * 1024;
const MAX_VALIDATION_CLAIM_CHARACTERS = 512;
const CODEX_RUNTIME_IDENTIFIER_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$/;

export function isBoundedCodexRuntimeIdentifier(value) {
  return typeof value === "string" && value !== "UNAVAILABLE" && CODEX_RUNTIME_IDENTIFIER_PATTERN.test(value);
}

function boundedString(value, field, maximumCharacters, { allowEmpty = true } = {}) {
  if (typeof value !== "string" || (!allowEmpty && value.trim() === "")) {
    throw new Error(`CODEX_RESULT_${field.toUpperCase()}_INVALID`);
  }
  if ([...value].length > maximumCharacters || /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(value)) {
    throw new Error(`CODEX_RESULT_${field.toUpperCase()}_INVALID`);
  }
  return value;
}

// The governed launcher requests structured output from Codex. This bounded
// normalizer enforces the semantic contract locally; an upstream schema request
// alone does not prove that the returned text satisfies it.
export function normalizeCodexSemanticResult(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("CODEX_RESULT_OBJECT_INVALID");
  const keys = Object.keys(value).sort().join("\0");
  if (keys !== [...RESULT_KEYS].sort().join("\0")) throw new Error("CODEX_RESULT_FIELDS_INVALID");
  if (value.status !== "success" && value.status !== "blocked") throw new Error("CODEX_RESULT_STATUS_INVALID");
  const summary = boundedString(value.summary, "summary", MAX_SUMMARY_CHARACTERS, { allowEmpty: value.status === "blocked" });
  if (!Array.isArray(value.validation) || value.validation.length > 64 || value.validation.some(item => typeof item !== "string" || [...item].length > MAX_VALIDATION_CLAIM_CHARACTERS || /[\u0000-\u001f\u007f]/.test(item))) {
    throw new Error("CODEX_RESULT_VALIDATION_INVALID");
  }
  const blockedReason = boundedString(value.blockedReason, "blockedReason", MAX_BLOCKED_REASON_CHARACTERS);
  if (value.status === "success" && blockedReason.trim() !== "") throw new Error("CODEX_RESULT_BLOCKED_REASON_INVALID");
  if (value.status === "blocked" && blockedReason.trim() === "") throw new Error("CODEX_RESULT_BLOCKED_REASON_INVALID");
  return { status: value.status, summary, validation: [...value.validation], blockedReason };
}
