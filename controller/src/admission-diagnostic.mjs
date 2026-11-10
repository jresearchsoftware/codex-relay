import { boundedDiagnosticText } from './diagnostics.mjs';

const safeCode = value => /^[A-Z][A-Z0-9_]{0,79}$/.test(value ?? '') ? value : undefined;

// Private exception text stays in the protected Writer record. The helper wire
// carries only a fixed stage/operation and allowlisted classification, never the
// exception message, stack, request body, API URL or protected path.
export function admissionFailure(error, operation, executionId, knownSecrets = []) {
  const code = safeCode(error?.code) ?? 'ADMISSION_STEP_PROJECTION_FAILED';
  const name = ['Error', 'TypeError', 'RangeError', 'SyntaxError', 'ReferenceError', 'AbortError', 'TimeoutError']
    .includes(error?.name) ? error.name : 'Error';
  const status = Number.isInteger(error?.status) && error.status >= 100 && error.status <= 599 ? error.status : undefined;
  const diagnostic = { code, stage: 'authority', boundary: 'writer-publication', operation, executionId,
    preview: `Writer admission failed at ${operation} (${name}${status ? `; HTTP ${status}` : ''}). `
      + 'This admission call did not return launch authority. Protected admission and execution evidence remain authoritative.' };
  return { diagnostic, exception: { name, ...(status ? { status } : {}),
    ...boundedDiagnosticText(error?.stack ?? error?.message ?? name, 8192, { knownSecrets }) } };
}
