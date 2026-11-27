import { join } from 'node:path';

const nativeId = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

// A native turn receipt and a reaped CLI process prove different lifecycles.
// Only the backend selected by this admission may establish execution completion.
export function executionEnded(envelope, execution) {
  if (execution?.child === 'not_started') {
    if (envelope?.backend !== 'app-server') return ['reaped', 'not_required'].includes(execution.containment);
    return execution.containment === 'not_required' && (!execution.appServer
      || ['thread-starting', 'thread-created'].includes(execution.appServer.phase));
  }
  if (execution?.child !== 'started') return false;
  if (envelope?.backend !== 'app-server') return execution.containment === 'reaped';
  const native = execution.appServer;
  return native?.phase === 'terminal' && native.attemptId === envelope.attemptId
    && nativeId.test(native.threadId) && nativeId.test(native.turnId)
    && typeof envelope.appServerTarget?.workspaceRoot === 'string'
    && native.socketPath === envelope.appServerTarget.socketPath
    && native.cwd === join(envelope.appServerTarget.workspaceRoot, envelope.attemptId)
    && native.containment === execution.containment
    && ['completed', 'interrupted', 'failed'].includes(native.status)
    && execution.containment === `turn_${native.status}`;
}

export function terminalObservation(envelope, execution) {
  const { child, containment } = execution;
  if (envelope.backend !== 'app-server' || child === 'not_started') return { child, containment };
  const { phase, attemptId, threadId, turnId, status, socketPath, cwd } = execution.appServer;
  return { child, containment, appServer: { phase, attemptId, threadId, turnId, status, socketPath, cwd, containment } };
}
