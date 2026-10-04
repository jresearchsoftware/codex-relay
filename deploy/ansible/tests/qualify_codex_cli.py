#!/usr/bin/env python3
"""Credential-free qualification of the exact official release in temporary homes.

Only a loopback deterministic Responses service is used; no model is called. The
separate installed_runtime_proof.py exercises real launcher/users/sudo with a
deterministic child; this probe exercises the official release itself.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import shutil
import stat
from pathlib import Path
import subprocess
import tempfile
import threading
import uuid

import yaml

REPO = Path(__file__).resolve().parents[3]
USAGE = {"input_tokens": 100, "cached_input_tokens": 25, "cache_write_input_tokens": 10,
         "output_tokens": 30, "reasoning_output_tokens": 20}
RESULT = {"status": "success", "summary": "Deterministic CLI qualification",
          "validation": ["loopback response"], "blockedReason": ""}


def isolated_environment(root):
    """Match the launcher's task-local locations, with no inherited credentials."""
    root.mkdir(parents=True)
    for name in ("home", "config", "cache", "data", "state", "tmp"):
        (root / name).mkdir()
    env = {"PATH": "/usr/bin:/bin", "HOME": str(root / "home"), "USERPROFILE": str(root / "home"),
           "CODEX_HOME": str(root / "home"), "LANG": "C", "LC_ALL": "C", "TZ": "UTC",
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
           "GIT_CONFIG_SYSTEM": "/dev/null", "GIT_TERMINAL_PROMPT": "0", "GIT_SSH_COMMAND": "false"}
    for name in ("CONFIG", "CACHE", "DATA", "STATE"):
        env[f"XDG_{name}_HOME"] = str(root / name.lower())
    for name in ("TMP", "TEMP", "TMPDIR"):
        env[name] = str(root / "tmp")
    return env


def nested_objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from nested_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from nested_objects(child)


def qualify_execution(binary, root):
    """Exercise the production argv, changing only the provider to a local fake.

    The fake supplies responses, never executes model-selected tools and never
    invokes a child agent. Rollouts verify effective policy, not OS enforcement;
    privileged containment and cleanup retain their separate qualification.
    """
    node = shutil.which("node")
    assert node, "Node is required for the actual Relay schema/parser"
    schema_module = (REPO / "runtime/src/codex-result-schema.mjs").as_uri()
    schema = json.loads(subprocess.run(
        [node, "--input-type=module", "-e",
         "const m = await import(process.argv[1]); console.log(JSON.stringify(m.CODEX_RESULT_SCHEMA));",
         schema_module], check=True, capture_output=True, text=True, timeout=30,
        env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"}).stdout)
    consumer = root / "fixture-consumer.json"
    consumer.write_bytes((REPO / "consumer/fixtures/example.json").read_bytes())
    consumer.chmod(0o600)
    requests = []
    response_events = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            # A bound local provider requires neither OpenAI auth nor a login.
            assert self.path == "/v1/responses", self.path
            assert self.headers.get("Authorization") is None
            assert self.headers.get("Content-Encoding") is None
            requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            body = "".join(f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"
                           for event in response_events).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    identifiers = set()
    try:
        # Off remains a task instruction, as in the governed launcher; it is not
        # a native feature toggle. No subagent is spawned in this qualification.
        for index, (permission, effort, mode) in enumerate([
            ("On", "xhigh", "success"), ("Off", "ultra", "missing-usage"),
            ("On", "xhigh", "invalid-result"), ("Off", "xhigh", "failure")
        ]):
            work = root / f"work-{index}"
            work.mkdir()
            sandbox = work / ".codex-sandbox"
            env = isolated_environment(sandbox)
            subprocess.run(["git", "init", "-q", str(work)], env=env, check=True)
            schema_path = sandbox / "codex-result-schema.json"
            schema_path.write_text(json.dumps(schema))
            prompt = f"Synthetic task input: Unicode \u041c\u0430\u0440\u043a\u0435\u0440, literal $() and `quotes`.\nSubagents: {permission}\n"
            input_path = sandbox / "task-input.md"
            input_path.write_text(prompt)
            requests.clear()
            response_events.clear()
            if mode == "failure":
                response_events.append({"type": "response.failed", "response": {
                    "id": "resp-fixture", "error": {"code": "insufficient_quota",
                    "message": "Synthetic provider refusal"}}})
            else:
                final_text = "not valid semantic JSON" if mode == "invalid-result" else json.dumps(RESULT)
                response = {"id": "resp-fixture"}
                if mode != "missing-usage":
                    response["usage"] = {"input_tokens": 100, "output_tokens": 30, "total_tokens": 130,
                        "input_tokens_details": {"cached_tokens": 25, "cache_write_tokens": 10},
                        "output_tokens_details": {"reasoning_tokens": 20}}
                response_events.extend([
                    {"type": "response.created", "response": {"id": "resp-fixture"}},
                    {"type": "response.output_item.done", "item": {"type": "message", "role": "assistant",
                        "id": "msg-fixture", "content": [{"type": "output_text", "text": final_text}]}},
                    {"type": "response.completed", "response": response}])

            # These production flags intentionally remain explicit. --ephemeral,
            # --worktree, resume, and config/rule suppression are not adopted.
            argv = [str(binary), "exec", "--json", "--sandbox", "workspace-write",
                    "--add-dir", str(work / ".git"), "--output-schema", str(schema_path),
                    "--model", "gpt-6-astra", "-c", f"model_reasoning_effort={effort}",
                    "-c", "sandbox_workspace_write.network_access=true", "--cd", str(work),
                    "-c", 'model_provider="qualification"', "-c",
                    f'model_providers.qualification={{name="qualification",base_url="http://127.0.0.1:{server.server_port}/v1",'
                    'wire_api="responses",requires_openai_auth=false,supports_websockets=false}',
                    "-c", "features.enable_request_compression=false", "-"]
            child = subprocess.run(argv, cwd=work, env=env, input=input_path.read_text(),
                                   capture_output=True, text=True, timeout=45)
            assert len(requests) == 1, len(requests)
            request = requests[0]
            assert request["model"] == "gpt-6-astra"
            # In this release's bundled catalog Ultra resolves to xhigh for
            # this synthetic provider. Relay passes the admitted string intact;
            # this observation is not proof of a live provider's model support.
            assert request["reasoning"]["effort"] == "xhigh", (effort, request["reasoning"])
            assert request["text"]["format"] == {
                "name": "codex_output_schema", "type": "json_schema", "strict": True, "schema": schema}
            assert any(item.get("role") == "user" and item.get("content") == [
                {"type": "input_text", "text": prompt}] for item in request["input"])
            # Native multi_agent defaults to enabled, including with Off in the
            # prompt. Relay's resolved permission is enforced by instructions.
            assert any(item.get("name") == "spawn_agent" for item in nested_objects(request))
            events = [json.loads(line) for line in child.stdout.splitlines()]
            assert events[0]["type"] == "thread.started"
            identifier = events[0]["thread_id"]
            uuid.UUID(identifier)
            assert identifier not in identifiers
            identifiers.add(identifier)
            assert sum(event["type"] == "thread.started" for event in events) == 1
            assert sum(event["type"] == "turn.started" for event in events) == 1
            assert not any("model" in event or "effort" in event for event in events)
            if mode == "failure":
                assert child.returncode == 1, child.stderr
                assert any(event["type"] == "turn.failed" for event in events)
                assert not any(event["type"] == "turn.completed" for event in events)
            else:
                assert child.returncode == 0, child.stderr
                assert events[-1] == {"type": "turn.completed", "usage": {
                    key: 0 for key in USAGE} if mode == "missing-usage" else USAGE}
                assert sum(event["type"] == "turn.completed" for event in events) == 1
                messages = [event["item"]["text"] for event in events if event["type"] == "item.completed"
                            and event["item"]["type"] == "agent_message"]
                assert messages == [final_text]
                # Schema is an upstream request, not local validation: exercise
                # Relay's actual semantic parser against the real JSONL stream.
                parsed = subprocess.run([node, "--input-type=module", "-e", """
import { readFileSync } from 'node:fs';
const { parseCodexJsonLines } = await import(process.argv[1]);
try { console.log(JSON.stringify(parseCodexJsonLines(readFileSync(0, 'utf8')))); }
catch { process.exitCode = 2; }
""", (REPO / "runtime/src/codex-runtime.mjs").as_uri()], input=child.stdout,
                    capture_output=True, text=True, timeout=30,
                    env={**env, "RELAY_CONSUMER_CONFIG": str(consumer)})
                if mode == "invalid-result":
                    assert parsed.returncode == 2
                else:
                    assert parsed.returncode == 0, parsed.stderr
                    assert json.loads(parsed.stdout) == {**RESULT, "threadId": identifier, "sessionId": identifier}

            rollouts = list((sandbox / "home/sessions").rglob("*.jsonl"))
            assert len(rollouts) == 1
            records = [json.loads(line) for line in rollouts[0].read_text().splitlines()]
            metadata = next(record["payload"] for record in records if record["type"] == "session_meta")
            context = next(record["payload"] for record in records if record["type"] == "turn_context")
            assert metadata["id"] == identifier and metadata["cli_version"] == "0.160.0"
            assert context["cwd"] == str(work)
            assert context["model"] == "gpt-6-astra" and context["effort"] == effort
            assert context["approval_policy"] == "never"
            assert context["sandbox_policy"]["type"] == "workspace-write"
            assert context["sandbox_policy"]["network_access"] is True
            assert context["sandbox_policy"]["writable_roots"] == [str(work / ".git")]
            assert work.joinpath(".git").is_dir()  # no native worktree adoption
            assert not (work / ".codex").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def qualify():
    variables = yaml.safe_load((REPO / "deploy/ansible/group_vars/all.yml").read_text())
    version = variables["relay_codex_cli_version"]
    assert version == "0.160.0"
    # Use native Linux /tmp, not a caller TMPDIR that may inherit a checkout's
    # setgid bit/default ACL and invalidate the production umask probe.
    with tempfile.TemporaryDirectory(prefix="codex-cli-qualification-", dir="/tmp") as temporary:
        root = Path(temporary)
        home = root / "home"
        home.mkdir()
        install = root / "bin"
        # An allowlist, never the runner's credential-bearing environment.
        env = {"PATH": "/usr/bin:/bin", "HOME": str(home), "CODEX_HOME": str(home),
               "CODEX_INSTALL_DIR": str(install), "CODEX_NON_INTERACTIVE": "1",
               "LANG": "C", "LC_ALL": "C"}
        for name in ("CONFIG", "CACHE", "DATA", "STATE"):
            directory = root / name.lower()
            directory.mkdir()
            env[f"XDG_{name}_HOME"] = str(directory)
        installer = root / "install.sh"
        subprocess.run(["/usr/bin/curl", "--fail", "--silent", "--show-error", "--location", "--max-time", "60",
                        variables["relay_codex_installer_url"], "--output", str(installer)], env=env, check=True, timeout=65)
        # The production deploy inherits the runner service's restrictive mask.
        # Keep the offline distribution fixture honest against the real public
        # installer: these mkdir ancestors (unlike archived files) become 0700.
        subprocess.run(["/bin/sh", str(installer), "--release", version], cwd=root, env=env, check=True, timeout=300, umask=0o077)
        binary = install / "codex"
        assert binary.is_symlink()
        releases = home / "packages/standalone/releases"
        assert binary.resolve().is_relative_to(releases)
        assert binary.resolve().relative_to(releases).parts[0].startswith(version + "-")
        for path in [home / 'packages', home / 'packages/standalone', releases,
                     releases / binary.resolve().relative_to(releases).parts[0]]:
            assert stat.S_IMODE(path.stat().st_mode) == 0o700, path

        def run(*args):
            return subprocess.run([str(binary), *args], cwd=root, env=env, input="",
                                  text=True, capture_output=True, check=True, timeout=30).stdout

        assert run("--version").strip() == f"codex-cli {version}"
        help_text = run("exec", "--help")
        for flag in ("--strict-config", "--color", "--thread-source", "--worktree", "--ephemeral",
                     "--ignore-user-config", "--ignore-rules", "--approve-for-me"):
            assert flag in help_text, flag
        run("exec", "fork", "--help")
        run("exec", "resume", "--help")
        # Parser examples only. Codex/backend owns capability truth; this
        # qualification neither mirrors a catalog nor proves model support.
        for model, effort in [("gpt-6-astra", "max"), ("future-model", "future-effort"),
                              ("gpt-6-astra", "xhigh"), ("gpt-6-astra", "ultra")]:
            # --help terminates before config/auth/session startup.
            run("exec", "--json", "--sandbox", "workspace-write", "--add-dir", str(root / ".git"),
                "--output-schema", str(root / "schema.json"), "--model", model,
                "-c", f"model_reasoning_effort={effort}", "-c", "sandbox_workspace_write.network_access=true",
                "--cd", str(root), "-", "--help")
        # A poisonous installed-user config must not enter the task's new home.
        # No existing user configuration or credentials are read or modified.
        (home / "config.toml").write_text("invalid = [\n")
        qualify_execution(binary, root)
        assert (home / "config.toml").read_text() == "invalid = [\n"
        assert not (home / "sessions").exists()
        print(f"CODEX_CLI_QUALIFICATION_PASS=version={version}; official-installer; release-symlink; deploy-umask=0077; package-roots=0700; real-jsonl; schema-request-and-semantic-parser; thread-id; native-usage-and-zero-default; model-effort-request; stdin; isolated-home; sandbox-policy; subagents=prompt-permission; nonzero-exit; model-call=none")


if __name__ == "__main__":
    qualify()
