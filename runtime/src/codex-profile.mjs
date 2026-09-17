import { CONSUMER } from '../../consumer/consumer.mjs';
// Project defaults and bounded argument syntax only. Codex/backend owns
// executable capability truth; a new model or effort needs no project update.
export const CANONICAL_CODEX_DEFAULT_PROFILE = CONSUMER.defaultProfile;
const secretLike = value => /(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]{20,}/.test(value);
export const safeModel = value => typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(value) && !/[\r\n]/.test(value) && !secretLike(value);
export const safeEffort = value => typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(value) && !/[\r\n]/.test(value) && !secretLike(value);

export function resolveCodexProfile({ cliModelId, effort } = {}) {
  const profile = {
    cliModelId: cliModelId === undefined ? CANONICAL_CODEX_DEFAULT_PROFILE.cliModelId : cliModelId,
    effort: effort === undefined ? CANONICAL_CODEX_DEFAULT_PROFILE.effort : effort
  };
  if (!safeModel(profile.cliModelId) || !safeEffort(profile.effort)) {
    throw Object.assign(new Error('Model and effort must be bounded argument identifiers'), { code: 'MODEL_PROFILE_INVALID' });
  }
  return profile;
}
