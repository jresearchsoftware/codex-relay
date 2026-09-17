// Shared runtime error; retired Issue lifecycle contracts are intentionally gone.
export class WriterBlockedError extends Error {
  constructor(code, message, details = {}) { super(message); this.name = 'WriterBlockedError'; this.code = code; this.details = details; }
}
