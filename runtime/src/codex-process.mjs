import { EXECUTION_CONSUMER as CONSUMER } from '../../consumer/consumer.mjs';

export const CODEX_SUDO_PATH = '/usr/bin/sudo';
export const CODEX_RUNTIME_USER = CONSUMER.runtimeUser;
export const CODEX_LAUNCHER_PATH = CONSUMER.paths.launcher;

// The installation selects the group, never Task input or worker metadata.
// A primary work GID also covers staged/renamed trees outside setgid parents.
// Retained serial configurations without workGroup keep their original ABI.
export function buildCodexProcessSpec({ args, executable = CODEX_LAUNCHER_PATH } = {}) {
  if (executable !== CODEX_LAUNCHER_PATH) throw new Error('Codex execution must use the fixed governed launcher');
  if (!Array.isArray(args)) throw new Error('Codex process arguments are required');
  return {
    command: CODEX_SUDO_PATH,
    args: ['-n', '-u', CODEX_RUNTIME_USER, ...(CONSUMER.workGroup ? ['-g', CONSUMER.workGroup] : []), executable, ...args]
  };
}
