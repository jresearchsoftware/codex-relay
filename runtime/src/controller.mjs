// Compatibility entrypoint for the separately authorized non-routing runtime probe.
// Ordinary Issue/remediation execution uses controller/src/attempt.mjs.
import { runGovernedCodexTask } from './codex-runtime.mjs';
export function runCodex({ profile, inputBytes, cwd, issueNumber, spawnImpl, env, appServer, taskTitle, evidence, executable }) {
  return runGovernedCodexTask({ operation: 'issue-implementation', profile, inputText: Buffer.from(inputBytes).toString('utf8'), cwd,
    targetNumber: issueNumber, spawnImpl, env, appServer, taskTitle, evidence, executable,
    buildArgs: ({ inputPath, cwd, profile }) => ['exec', '--json', '--model', profile.cliModelId, '--effort', profile.effort, '--input-file', inputPath, '--cwd', cwd, '--issue', String(issueNumber)] });
}
