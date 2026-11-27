import { createHash, randomUUID } from 'node:crypto';
import { chmod, lstat, mkdir, readdir, realpath } from 'node:fs/promises';
import { basename, dirname, join, resolve } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { CODEX_RESULT_SCHEMA, normalizeCodexSemanticResult } from '../../runtime/src/codex-result-schema.mjs';
import { connectAppServer } from './app-server-connection.mjs';
import { normalizeCodexUsage } from './codex-usage.mjs';

const NATIVE_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const TERMINAL = new Set(['completed', 'interrupted', 'failed']);
const SAFE_MCP_NAME = /^[A-Za-z0-9_-]{1,100}$/;
const MAX_HISTORY_PAGES = 128;
const POLL_MS = 2000;
const RECOVERY_MS = 60_000;
const TURN_TIMEOUT_MS = 90 * 60 * 1000;
const hash = value => createHash('sha256').update(value).digest('hex');
const failure = (code, message = code) => Object.assign(new Error(message), { code });

async function helperReads(serverHome) {
  // Narrow read access to Codex's arg0 helper links and their binaries.
  // Never grant the sandbox access to the server HOME, sessions or auth files.
  const helperRoot = join(serverHome, 'tmp', 'arg0-linux');
  const root = await lstat(helperRoot);
  if (!root.isDirectory() || root.mode & 0o022 || await realpath(helperRoot) !== helperRoot) {
    throw failure('APP_SERVER_RUNTIME_UNQUALIFIED', 'App Server Linux sandbox helpers require a protected native runtime directory');
  }
  const entries = (await readdir(helperRoot)).filter(name => /^codex-arg0[A-Za-z0-9_-]+$/.test(name));
  if (!entries.length || entries.length > 16) throw failure('APP_SERVER_RUNTIME_UNQUALIFIED', 'App Server Linux sandbox helper inventory is missing or exceeds its bound');
  const readable = { [helperRoot]: 'read' };
  for (const name of entries) {
    const path = join(helperRoot, name, 'codex-linux-sandbox');
    const directory = await lstat(dirname(path));
    const binary = await realpath(path);
    const info = await lstat(binary);
    if (!directory.isDirectory() || directory.mode & 0o022 || !info.isFile() ||
        !['codex', 'codex-linux-sandbox'].includes(basename(binary)) ||
        !(info.mode & 0o111) || info.mode & 0o022) {
      throw failure('APP_SERVER_RUNTIME_UNQUALIFIED', 'App Server Linux sandbox helper executable is unqualified');
    }
    readable[binary] = 'read';
  }
  return readable;
}

async function threadConfiguration(connection, cwd, profile, subagentsAllowed, permissionId, socketPath) {
  const effective = (await connection.request('config/read', { cwd, includeLayers: false }))?.config;
  if (!effective || typeof effective !== 'object' || Array.isArray(effective) ||
      Object.keys(effective.shell_environment_policy?.set ?? {}).length) {
    throw failure('APP_SERVER_CONFIG_UNQUALIFIED', 'App Server must support effective config readback and have no inherited shell environment overrides for this workspace');
  }
  const mcpNames = Object.keys(effective.mcp_servers ?? {});
  if (mcpNames.length > 100 || mcpNames.some(name => !SAFE_MCP_NAME.test(name))) {
    throw failure('APP_SERVER_MCP_UNQUALIFIED', 'App Server MCP configurations must have bounded overrideable names');
  }
  const filesystem = await helperReads(connection.codexHome).catch(error => {
    if (error.code === 'APP_SERVER_RUNTIME_UNQUALIFIED') throw error;
    throw failure('APP_SERVER_RUNTIME_UNQUALIFIED', 'Relay cannot read the protected App Server Linux sandbox helper paths');
  });
  const scratch = join(cwd, '.git', 'relay-runtime');
  // The controller may run with umask 077. The admitted model identity needs
  // the inherited checkout group to create its own sandbox runtime files.
  await mkdir(scratch, { mode: 0o700 });
  await chmod(scratch, 0o2770);
  return {
    ...Object.fromEntries(mcpNames.map(name => [`mcp_servers.${name}.enabled`, false])),
    permissions: {
      [permissionId]: {
        filesystem: {
          ':minimal': 'read', '/etc': 'none',
          ':workspace_roots': { '.': 'write', '.git': 'write' },
          ...filesystem, [socketPath]: 'none'
        },
        network: { enabled: false }
      }
    },
    default_permissions: permissionId,
    model_reasoning_effort: profile.effort,
    allow_login_shell: false,
    web_search: 'disabled',
    features: {
      apps: false, plugins: false, hooks: false, remote_plugin: false,
      browser_use: false, browser_use_external: false, browser_use_full_cdp_access: false,
      computer_use: false, image_generation: false, goals: false,
      code_mode: false, code_mode_only: false, shell_snapshot: false,
      skill_mcp_dependency_install: false, memories: false, agent_message_board_mcp: false,
      multi_agent: subagentsAllowed, multi_agent_v2: subagentsAllowed,
      subagent_thread_environments: false, use_legacy_landlock: false
    },
    // Model-selected Code Mode delegates the same sandboxed turn tools. Do
    // not select it on behalf of other models or fall back on host failure.
    code_mode: { disable_in_process_fallback: true },
    agents: { enabled: subagentsAllowed },
    shell_environment_policy: {
      inherit: 'none', set: {
        PATH: '/usr/bin:/bin', HOME: scratch, CODEX_HOME: scratch, TMPDIR: scratch, LANG: 'C.UTF-8',
        GIT_CONFIG_NOSYSTEM: '1', GIT_CONFIG_SYSTEM: '/dev/null', GIT_CONFIG_GLOBAL: '/dev/null',
        GIT_CONFIG_COUNT: '1', GIT_CONFIG_KEY_0: 'safe.directory', GIT_CONFIG_VALUE_0: cwd,
        GIT_TERMINAL_PROMPT: '0', GIT_SSH_COMMAND: 'false'
      }
    }
  };
}

function verifyStart(started, cwd, profile, permissionId) {
  const t = started?.thread;
  const s = started?.sandbox;
  const [environment, other] = t?.environments ?? [];
  if (!NATIVE_ID.test(t?.id ?? '') || t.ephemeral !== false || t.historyMode !== 'paginated' ||
      t.parentThreadId !== null || t.sessionId !== t.id || t.status?.type !== 'idle' || t.cwd !== cwd ||
      started.cwd !== cwd || started.runtimeWorkspaceRoots?.join('\0') !== cwd ||
      environment?.environmentId !== 'local' || environment.cwd !== cwd || other ||
      environment.runtimeWorkspaceRoots?.join('\0') !== cwd ||
      started.model !== profile.cliModelId || started.reasoningEffort !== profile.effort ||
      started.approvalPolicy !== 'never' || started.activePermissionProfile?.id !== permissionId ||
      started.activePermissionProfile?.extends !== null ||
      s?.type !== 'workspaceWrite' || s.networkAccess !== false || s.excludeSlashTmp !== true ||
      s.excludeTmpdirEnvVar !== true || !Array.isArray(s.writableRoots) ||
      !s.writableRoots.includes(join(cwd, '.git')) || s.writableRoots.some(path => path !== cwd && path !== join(cwd, '.git'))) {
    throw failure('APP_SERVER_THREAD_POLICY_UNVERIFIED', 'App Server did not confirm the admitted local workspace, profile and permissions');
  }
}

function checkedPage(response, code) {
  if (!Array.isArray(response?.data) ||
      !(response.nextCursor === null || (typeof response.nextCursor === 'string' && response.nextCursor.length <= 4096))) throw failure(code);
  return response;
}

async function verifyNoMcp(connection, threadId) {
  const page = checkedPage(await connection.request('mcpServerStatus/list', {
    threadId, limit: 100, detail: 'toolsAndAuthOnly'
  }), 'APP_SERVER_MCP_UNVERIFIED');
  if (page.nextCursor || page.data.some(server => server.runtimeStatus !== 'disabled')) {
    throw failure('APP_SERVER_MCP_UNVERIFIED', 'App Server did not confirm that inherited MCP tools were disabled for this thread');
  }
}

async function readThread(connection, state) {
  const t = (await connection.request('thread/read', { threadId: state.threadId, includeTurns: false }))?.thread;
  if (t?.id !== state.threadId || t.cwd !== state.cwd || t.ephemeral !== false || t.historyMode !== 'paginated') {
    throw failure('APP_SERVER_THREAD_BINDING_INVALID');
  }
  return t;
}

async function onlyTurn(connection, state) {
  const turns = checkedPage(await connection.request('thread/turns/list', {
    threadId: state.threadId, limit: 2, itemsView: 'notLoaded'
  }), 'APP_SERVER_HISTORY_UNVERIFIED');
  if (turns.nextCursor || turns.data.length > 1 ||
      turns.data.some(turn => !NATIVE_ID.test(turn.id ?? '') || (state.turnId && turn.id !== state.turnId) ||
      !(turn.status === 'inProgress' || TERMINAL.has(turn.status)))) {
    throw failure('APP_SERVER_TURN_BINDING_INVALID', 'App Server thread has unexpected turn history; retain the original attempt for reconciliation');
  }
  return turns.data[0];
}

async function inspectTurn(connection, state, turnId, terminal) {
  let cursor, semanticMessage, markerVerified = false, firstUser = false, usedSubagents = false;
  for (let count = 0; count < MAX_HISTORY_PAGES; count++) {
    const page = checkedPage(await connection.request('thread/items/list', {
      threadId: state.threadId, turnId, sortDirection: 'asc', limit: 25, cursor,
      deferOutput: { commandExecution: true, mcpToolCall: true }
    }), 'APP_SERVER_HISTORY_UNVERIFIED');
    for (const row of page.data) {
      const item = row?.item;
      if (row?.turnId !== turnId || !item || typeof item.type !== 'string') throw failure('APP_SERVER_HISTORY_UNVERIFIED');
      if (item.type === 'userMessage' && !firstUser) {
        firstUser = true;
        const [content, other] = item.content ?? [];
        if (item.clientId !== state.messageId || content?.type !== 'text' || other ||
            typeof content.text !== 'string' || hash(content.text) !== state.inputSha256) {
          throw failure('APP_SERVER_TURN_BINDING_INVALID', 'App Server did not return the original Relay assignment as the first turn input');
        }
        markerVerified = true;
        if (!terminal) return { markerVerified };
      }
      if (item.type === 'agentMessage' && (item.phase === 'final_answer' || item.phase == null)) semanticMessage = item.text;
      if (item.type === 'subAgentActivity' || item.type === 'collabAgentToolCall') usedSubagents = true;
    }
    if (!page.nextCursor) return { markerVerified, semanticMessage, usedSubagents };
    if (page.nextCursor === cursor) throw failure('APP_SERVER_HISTORY_UNVERIFIED');
    cursor = page.nextCursor;
  }
  throw failure('APP_SERVER_HISTORY_UNVERIFIED', 'App Server history exceeds the bounded reconciliation window');
}

async function verifySettled(connection, state) {
  const descendants = checkedPage(await connection.request('thread/list', {
    ancestorThreadId: state.threadId, limit: 100,
    sourceKinds: ['subAgent', 'subAgentThreadSpawn', 'subAgentOther', 'subAgentCompact', 'subAgentReview']
  }), 'APP_SERVER_DESCENDANTS_UNVERIFIED');
  if (descendants.nextCursor || descendants.data.some(t => !NATIVE_ID.test(t.id ?? '') ||
      t.id === state.threadId || !['idle', 'notLoaded'].includes(t.status?.type))) {
    throw failure('APP_SERVER_DESCENDANTS_UNVERIFIED', 'App Server has active or unverified descendants of the admitted thread');
  }
  for (const threadId of [...descendants.data.map(thread => thread.id), state.threadId]) {
    const native = checkedPage(await connection.request('thread/backgroundTerminals/list', { threadId, limit: 1 }),
      'APP_SERVER_TERMINALS_UNVERIFIED');
    if (native.nextCursor || native.data.length) {
      await connection.request('thread/backgroundTerminals/clean', { threadId });
      const after = checkedPage(await connection.request('thread/backgroundTerminals/list', { threadId, limit: 1 }),
        'APP_SERVER_TERMINALS_UNVERIFIED');
      if (after.nextCursor || after.data.length) {
        throw failure('APP_SERVER_TERMINALS_UNVERIFIED', 'App Server still reports background terminals owned by the admitted task');
      }
    }
  }
  const t = await readThread(connection, state);
  if (!['idle', 'notLoaded'].includes(t.status?.type)) {
    throw failure('APP_SERVER_THREAD_NOT_SETTLED', 'App Server thread has not settled after its admitted turn');
  }
  const final = await onlyTurn(connection, state);
  if (final?.status !== state.status) throw failure('APP_SERVER_TURN_BINDING_INVALID');
  return descendants.data.length > 0;
}

function resultFromCheckpoint(state) {
  const appServer = state;
  const containment = `turn_${state.status}`;
  if (state.failureCode) throw failure(state.failureCode, 'App Server turn settled without a valid successful semantic response');
  return {
    result: { ...normalizeCodexSemanticResult(state.result), threadId: state.threadId, sessionId: state.threadId },
    containment, codexUsage: normalizeCodexUsage(), appServer
  };
}

// The caller binds this operation to the protected attempt lock and synchronously
// persists every checkpoint before we send its corresponding write to the server.
export async function executeAppServer(
  { attemptId, target, cwd, taskTitle, profile, subagentsAllowed, inputText },
  { checkpoint, saveCheckpoint, signal, mode = 'execute', connect = connectAppServer, pollMs = POLL_MS } = {}
) {
  let state = checkpoint;
  let connection;
  const makeCheckpoint = async fields => {
    const next = { ...state, ...fields };
    await saveCheckpoint(next);
    state = next;
  };
  try {
    if (typeof saveCheckpoint !== 'function' || !['execute', 'reconcile', 'interrupt'].includes(mode) ||
        !/^(?:run|event)-[1-9][0-9]*$/.test(attemptId ?? '') ||
        typeof target?.workspaceRoot !== 'string' || !target.workspaceRoot.startsWith('/') ||
        typeof target?.socketPath !== 'string' || !target.socketPath.startsWith('/') ||
        cwd !== join(target.workspaceRoot, attemptId) || typeof inputText !== 'string' ||
        typeof taskTitle !== 'string' || !taskTitle.trim() || !profile?.cliModelId || !profile.effort ||
        typeof subagentsAllowed !== 'boolean') throw failure('APP_SERVER_EXECUTION_INVALID');
    if (state && (state.attemptId !== attemptId || state.cwd !== cwd || state.socketPath !== target.socketPath ||
        state.taskTitle !== taskTitle || state.model !== profile.cliModelId || state.effort !== profile.effort ||
        state.subagentsAllowed !== subagentsAllowed ||
        state.inputSha256 !== hash(inputText) || !NATIVE_ID.test(state.messageId ?? '') ||
        typeof state.serverHome !== 'string' || !state.serverHome.startsWith('/') ||
      (['turn-starting', 'turn-started'].includes(state.phase) && !Number.isSafeInteger(state.turnDeadline)) ||
        !['thread-starting', 'thread-created', 'turn-starting', 'turn-started', 'terminal'].includes(state.phase) ||
        (state.phase !== 'thread-starting' && !NATIVE_ID.test(state.threadId ?? '')) ||
        (['turn-started', 'terminal'].includes(state.phase) && !NATIVE_ID.test(state.turnId ?? '')))) {
      throw failure('APP_SERVER_CHECKPOINT_INVALID');
    }
    if (state?.phase === 'terminal') {
      if (!TERMINAL.has(state.status) || state.containment !== `turn_${state.status}`) throw failure('APP_SERVER_CHECKPOINT_INVALID');
      return resultFromCheckpoint(state);
    }
    if (state?.phase === 'thread-starting') {
      throw failure('APP_SERVER_THREAD_START_UNCERTAIN', 'App Server thread creation was not acknowledged; no turn was dispatched');
    }
    if (mode !== 'execute' && !['turn-starting', 'turn-started'].includes(state?.phase)) {
      throw failure('APP_SERVER_TURN_NOT_DISPATCHED', 'The protected checkpoint contains no App Server turn dispatch');
    }
    const open = async () => {
      const client = await connect(target.socketPath, {
        onNotification: () => {},
        ownsRequest: params => !!state?.threadId && params?.threadId === state.threadId
      });
      if (state && client.codexHome !== state.serverHome) {
        client.close();
        throw failure('APP_SERVER_INSTANCE_MISMATCH', 'App Server did not return the original protected server identity');
      }
      return client;
    };
    if (!state) {
      if (signal?.aborted) throw failure('APP_SERVER_TURN_NOT_DISPATCHED');
      if (await realpath(cwd) !== cwd || resolve(cwd) !== cwd) throw failure('APP_SERVER_WORKSPACE_UNQUALIFIED');
      connection = await open();
      const messageId = randomUUID();
      const permissionId = `relay_${messageId.replaceAll('-', '')}`;
      const config = await threadConfiguration(connection, cwd, profile, subagentsAllowed, permissionId, target.socketPath);
      await makeCheckpoint({ attemptId, socketPath: target.socketPath, serverHome: connection.codexHome, cwd,
        messageId, inputSha256: hash(inputText), phase: 'thread-starting', taskTitle,
        model: profile.cliModelId, effort: profile.effort, subagentsAllowed });
      const started = await connection.request('thread/start', {
        cwd, model: profile.cliModelId, allowProviderModelFallback: false, runtimeWorkspaceRoots: [cwd],
        environments: [{ environmentId: 'local', cwd, runtimeWorkspaceRoots: [cwd] }],
        permissions: permissionId, approvalPolicy: 'never', config, ephemeral: false, historyMode: 'paginated',
        daybreakEnabled: false, daybreakProgramPropagationEnrolled: false
      });
      if (NATIVE_ID.test(started?.thread?.id ?? '')) {
        await makeCheckpoint({ phase: 'thread-created', threadId: started.thread.id, permissionId });
      }
      verifyStart(started, cwd, profile, permissionId);
      await verifyNoMcp(connection, state.threadId);
      await makeCheckpoint({ policyVerified: true });
    }
    if (state.phase === 'thread-created') {
      if (state.policyVerified !== true) throw failure('APP_SERVER_THREAD_POLICY_UNVERIFIED');
      if (signal?.aborted) throw failure('APP_SERVER_TURN_NOT_DISPATCHED');
      connection ??= await open();
      const thread = await readThread(connection, state);
      if (thread.status?.type !== 'idle' || thread.preview !== '') throw failure('APP_SERVER_THREAD_NOT_FRESH');
      if (thread.name !== taskTitle) {
        await connection.request('thread/name/set', { threadId: state.threadId, name: taskTitle });
        if ((await readThread(connection, state)).name !== taskTitle) throw failure('APP_SERVER_THREAD_NAME_UNVERIFIED');
      }
      if (await onlyTurn(connection, state)) throw failure('APP_SERVER_THREAD_NOT_FRESH');
      if (signal?.aborted) throw failure('APP_SERVER_TURN_NOT_DISPATCHED');
      await makeCheckpoint({ phase: 'turn-starting', turnDeadline: Date.now() + TURN_TIMEOUT_MS });
      try {
        const started = (await connection.request('turn/start', {
          cwd, model: profile.cliModelId, effort: profile.effort, threadId: state.threadId,
          approvalPolicy: 'never', permissions: state.permissionId, clientUserMessageId: state.messageId,
          input: [{ type: 'text', text: inputText, text_elements: [] }], outputSchema: CODEX_RESULT_SCHEMA
        }))?.turn;
        if (!NATIVE_ID.test(started?.id ?? '')) throw failure('APP_SERVER_TURN_START_UNVERIFIED');
        await makeCheckpoint({ phase: 'turn-started', turnId: started.id });
      } catch (error) {
        if (!error.reconnectable && error.code !== 'APP_SERVER_REQUEST_REJECTED' && error.code !== 'APP_SERVER_TURN_START_UNVERIFIED') throw error;
        // The server can accept input even if the response did not arrive.
        // Preserve the write intent and recover only on the original thread.
        connection.close();
        connection = undefined;
      }
    }

    let unavailableUntil = Date.now() + RECOVERY_MS;
    let stopUntil;
    let interruptSent = false;
    for (;;) {
      if (mode === 'interrupt' || signal?.aborted || Date.now() >= state.turnDeadline) stopUntil ??= Date.now() + RECOVERY_MS;
      if (Date.now() > (stopUntil ?? unavailableUntil)) {
        throw failure('APP_SERVER_TURN_UNCERTAIN', 'App Server did not settle the original turn within the reconciliation window');
      }
      try {
        connection ??= await open();
        await readThread(connection, state);
        const turn = await onlyTurn(connection, state);
        if (turn) {
          const terminal = TERMINAL.has(turn.status);
          const inspected = await inspectTurn(connection, state, turn.id, terminal);
          if (inspected.markerVerified) {
            if (state.phase === 'turn-starting') await makeCheckpoint({ phase: 'turn-started', turnId: turn.id });
            if (terminal) {
              const descendantsUsed = await verifySettled(connection, { ...state, status: turn.status });
              const usedSubagents = descendantsUsed || inspected.usedSubagents;
              let result, failureCode;
              if (usedSubagents && !subagentsAllowed) failureCode = 'APP_SERVER_UNAUTHORIZED_SUBAGENTS';
              else if (turn.status !== 'completed') failureCode = `APP_SERVER_TURN_${turn.status.toUpperCase()}`;
              else {
                try { result = normalizeCodexSemanticResult(JSON.parse(inspected.semanticMessage)); }
                catch { failureCode = 'CODEX_RESULT_INVALID'; }
              }
              await makeCheckpoint({ phase: 'terminal', status: turn.status, containment: `turn_${turn.status}`,
                subagentsUsed: usedSubagents, ...(result ? { result } : { failureCode }) });
              return resultFromCheckpoint(state);
            }
            if (stopUntil && !interruptSent) {
              interruptSent = true;
              try { await connection.request('turn/interrupt', { threadId: state.threadId, turnId: state.turnId }); }
              catch (error) {
                if (!error.reconnectable && error.code !== 'APP_SERVER_REQUEST_REJECTED') throw error;
                connection.close();
                connection = undefined;
              }
            }
            if (mode === 'reconcile' && !stopUntil) {
              throw failure('APP_SERVER_TURN_ACTIVE', 'The original App Server turn is still active');
            }
            unavailableUntil = Date.now() + RECOVERY_MS;
          }
        }
      } catch (error) {
        if (!error.reconnectable && !['APP_SERVER_THREAD_NOT_SETTLED', 'APP_SERVER_DESCENDANTS_UNVERIFIED'].includes(error.code)) throw error;
        connection?.close();
        connection = undefined;
      }
      await delay(pollMs);
    }
  } catch (error) {
    let containment = 'not_required';
    if (error.code === 'APP_SERVER_CHECKPOINT_INVALID' || ['turn-starting', 'turn-started'].includes(state?.phase)) {
      containment = 'unknown';
    } else if (state?.phase === 'terminal' && TERMINAL.has(state.status) && state.containment === `turn_${state.status}`) {
      containment = state.containment;
    }
    error.details = {
      ...error.details,
      containment, childState: containment === 'not_required' ? 'not_started' : state?.turnId ? 'started' : 'unknown',
      executionId: attemptId, appServer: state
    };
    throw error;
  } finally {
    connection?.close();
  }
}
