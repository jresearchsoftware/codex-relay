import assert from 'node:assert/strict';
import { mkdtemp, mkdir, rm, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { executeAppServer } from '../src/app-server.mjs';

const THREAD = '01a21300-1234-7000-8000-123456789abc';
const TURN = '01a21300-1234-7000-8000-123456789abd';
const OTHER_TURN = '01a21300-1234-7000-8000-123456789abe';
const SEMANTIC = { status: 'success', summary: 'Completed fixture', validation: ['fixture-only'], blockedReason: '' };
const page = (data = []) => ({ data, nextCursor: null });

async function fixture(t, options = {}) {
  const root = await mkdtemp(join(tmpdir(), 'relay-app-server-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const serverHome = join(root, 'server');
  const cwd = join(root, 'work', 'run-901');
  const helperRoot = join(serverHome, 'tmp', 'arg0-linux', 'codex-arg0Test');
  await mkdir(helperRoot, { recursive: true, mode: 0o700 });
  await mkdir(join(cwd, '.git'), { recursive: true, mode: 0o700 });
  const binary = join(root, 'codex');
  await writeFile(binary, '', { mode: 0o755 });
  await symlink(binary, join(helperRoot, 'codex-linux-sandbox'));

  let state, name = null, turn, input, pendingTerminals = options.pendingTerminals ?? false;
  let connections = 0;
  const checkpoints = [];
  const requests = [];
  const args = {
    attemptId: 'run-901', target: { socketPath: join(root, 'app.sock'), workspaceRoot: join(root, 'work') },
    cwd, taskTitle: 'Task 901 — Step 3 — Isolated fixture',
    profile: { cliModelId: 'gpt-6.2-sol', effort: 'medium' }, subagentsAllowed: false, inputText: 'Admitted assignment'
  };
  const startThread = () => ({
    id: THREAD, sessionId: THREAD, parentThreadId: null, cwd, ephemeral: false, historyMode: 'paginated', name, preview: '',
    status: { type: turn?.status === 'inProgress' ? 'active' : 'idle' },
    environments: [{ environmentId: 'local', cwd, runtimeWorkspaceRoots: [cwd] }]
  });
  const connect = async path => {
    assert.equal(path, args.target.socketPath);
    connections++;
    return {
      codexHome: serverHome,
      close() {},
      async request(method, params) {
        requests.push([method, params]);
        switch (method) {
          case 'config/read':
            return { config: { mcp_servers: { fixture_mcp: {} } } };
          case 'thread/start':
            assert.equal(state.phase, 'thread-starting');
            if (options.disconnectThread) throw Object.assign(new Error('connection lost'), { reconnectable: true });
            return {
              cwd, model: params.model, reasoningEffort: params.config.model_reasoning_effort,
              approvalPolicy: params.approvalPolicy, activePermissionProfile: { id: params.permissions, extends: null },
              sandbox: { type: 'workspaceWrite', writableRoots: [join(cwd, '.git')], networkAccess: options.networkAllowed ?? false,
                excludeSlashTmp: true, excludeTmpdirEnvVar: true },
              runtimeWorkspaceRoots: [cwd], thread: startThread()
            };
          case 'mcpServerStatus/list': return page([{ runtimeStatus: options.mcpActive ? 'ready' : 'disabled' }]);
          case 'thread/read': return { thread: startThread() };
          case 'thread/name/set':
            assert.equal(state.threadId, THREAD);
            name = params.name;
            return {};
          case 'thread/turns/list':
            assert.equal(params.threadId, THREAD);
            return page(turn ? [turn, ...(options.extraTurn ? [{ id: OTHER_TURN, status: 'completed' }] : [])] : []);
          case 'turn/start':
            assert.equal(state.phase, 'turn-starting');
            assert.equal(name, args.taskTitle);
            assert.equal(params.clientUserMessageId, state.messageId);
            input = params.input;
            turn = { id: TURN, status: options.active ? 'inProgress' : 'completed' };
            if (options.disconnectTurn) throw Object.assign(new Error('connection lost'), { reconnectable: true });
            return { turn };
          case 'thread/items/list':
            assert.equal(params.threadId, THREAD);
            assert.equal(params.turnId, TURN);
            return page([
              { turnId: TURN, item: { type: 'userMessage', clientId: options.foreignInput ? OTHER_TURN : state.messageId, content: input } },
              { turnId: TURN, item: { type: 'agentMessage', phase: 'final_answer', text: JSON.stringify(SEMANTIC) } }
            ]);
          case 'thread/list':
            assert.equal(params.ancestorThreadId, THREAD);
            return page();
          case 'thread/backgroundTerminals/list':
            assert.equal(params.threadId, THREAD);
            return page(pendingTerminals ? [{ processId: 'fixture' }] : []);
          case 'thread/backgroundTerminals/clean':
            assert.equal(params.threadId, THREAD);
            pendingTerminals = false;
            return {};
          case 'turn/interrupt':
            assert.deepEqual(params, { threadId: THREAD, turnId: TURN });
            turn = { id: TURN, status: 'interrupted' };
            return {};
          default:
            assert.fail(method);
        }
      }
    };
  };
  const count = method => requests.filter(([actual]) => actual === method).length;
  return {
    args, checkpoints, requests, count,
    get connections() { return connections; },
    run: (more = {}) => executeAppServer(args, {
      connect, pollMs: 0,
      saveCheckpoint: async checkpoint => {
        state = structuredClone(checkpoint);
        checkpoints.push(state);
      },
      ...more
    })
  };
}

test('App Server sends the admitted profile and scoped tools in one named Developer turn', async t => {
  const f = await fixture(t, { pendingTerminals: true });
  const receipt = await f.run();
  const [, start] = f.requests.find(([method]) => method === 'thread/start');
  const [, turn] = f.requests.find(([method]) => method === 'turn/start');
  assert.equal(f.count('turn/start'), 1);
  assert.equal(f.count('thread/backgroundTerminals/clean'), 1);
  assert.equal(f.count('turn/interrupt'), 0);
  assert.equal(start.config.agents.enabled, false);
  assert.equal(start.config.features.multi_agent_v2, false);
  assert.equal(start.config['mcp_servers.fixture_mcp.enabled'], false);
  assert.equal(start.config.features.apps, false);
  assert.equal(start.config.features.plugins, false);
  assert.equal(start.config.shell_environment_policy.inherit, 'none');
  assert.equal(start.config.permissions[start.permissions].filesystem[f.args.target.socketPath], 'none');
  assert.equal(start.config.permissions[start.permissions].network.enabled, false);
  assert.equal(turn.model, f.args.profile.cliModelId);
  assert.equal(turn.effort, f.args.profile.effort);
  assert.equal(turn.cwd, f.args.cwd);
  assert.equal(turn.outputSchema.properties.status.type, 'string');
  assert.deepEqual(receipt.result, { ...SEMANTIC, threadId: THREAD, sessionId: THREAD });
  assert.equal(receipt.appServer.subagentsUsed, false);
  assert.equal(receipt.containment, 'turn_completed');
  const reads = f.requests.length;
  assert.deepEqual(await f.run({ mode: 'reconcile', checkpoint: receipt.appServer }), receipt);
  assert.equal(f.requests.length, reads);
});

test('lost turn-start response reconciles original user input and never resubmits a turn', async t => {
  const f = await fixture(t, { disconnectTurn: true });
  const receipt = await f.run();
  assert.equal(f.connections, 2);
  assert.equal(f.count('thread/start'), 1);
  assert.equal(f.count('turn/start'), 1);
  assert.equal(receipt.appServer.turnId, TURN);
  assert.equal(receipt.appServer.status, 'completed');
});

test('reconciliation refuses a foreign turn even when it has a successful result', async t => {
  const f = await fixture(t, { disconnectTurn: true, foreignInput: true });
  await assert.rejects(f.run(), error => {
    assert.equal(error.code, 'APP_SERVER_TURN_BINDING_INVALID');
    assert.equal(error.details.containment, 'unknown');
    assert.equal(error.details.appServer.phase, 'turn-starting');
    return true;
  });
  assert.equal(f.count('turn/start'), 1);
  assert.equal(f.count('turn/interrupt'), 0);
  assert.equal(f.count('thread/backgroundTerminals/clean'), 0);
});

test('reconciliation rejects another turn and does not issue a broad stop', async t => {
  const f = await fixture(t, { extraTurn: true });
  await assert.rejects(f.run(), { code: 'APP_SERVER_TURN_BINDING_INVALID' });
  assert.equal(f.count('turn/interrupt'), 0);
});

test('a persisted active turn can be interrupted through its original binding', async t => {
  const f = await fixture(t, { active: true });
  const signal = new AbortController();
  const run = f.run({ signal: signal.signal });
  const wait = async () => {
    while (!f.checkpoints.some(checkpoint => checkpoint.phase === 'turn-started')) {
      await new Promise(resolve => setImmediate(resolve));
    }
  };
  await wait();
  signal.abort();
  await assert.rejects(run, error => {
    assert.equal(error.code, 'APP_SERVER_TURN_INTERRUPTED');
    assert.equal(error.details.containment, 'turn_interrupted');
    assert.equal(error.details.appServer.status, 'interrupted');
    return true;
  });
  assert.equal(f.count('turn/start'), 1);
  assert.equal(f.count('turn/interrupt'), 1);
});

test('a lost thread start keeps its no-turn checkpoint and never starts a second thread', async t => {
  const f = await fixture(t, { disconnectThread: true });
  await assert.rejects(f.run(), error => error.details.containment === 'not_required');
  await assert.rejects(f.run({ mode: 'reconcile', checkpoint: f.checkpoints.at(-1) }), { code: 'APP_SERVER_THREAD_START_UNCERTAIN' });
  assert.equal(f.count('thread/start'), 1);
  assert.equal(f.count('turn/start'), 0);
});

test('App Server refuses inference on an unexpected permission or active inherited MCP server', async t => {
  for (const [options, code] of [
    [{ networkAllowed: true }, 'APP_SERVER_THREAD_POLICY_UNVERIFIED'],
    [{ mcpActive: true }, 'APP_SERVER_MCP_UNVERIFIED']
  ]) {
    const f = await fixture(t, options);
    await assert.rejects(f.run(), error => error.code === code && error.details.containment === 'not_required');
    assert.equal(f.count('turn/start'), 0);
  }
});

test('a terminal checkpoint from another assignment cannot authorize collection', async t => {
  const f = await fixture(t);
  const receipt = await f.run();
  const reads = f.requests.length;
  f.args.inputText = 'Different assignment';
  await assert.rejects(f.run({ mode: 'reconcile', checkpoint: receipt.appServer }), error => {
    assert.equal(error.code, 'APP_SERVER_CHECKPOINT_INVALID');
    assert.equal(error.details.containment, 'unknown');
    return true;
  });
  assert.equal(f.requests.length, reads);
});
