#!/usr/bin/env python3
"""Credential-free native Skill discovery; never starts a thread or model turn."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time


VERSION = "codex-cli 0.162.1"
NAME = "codex-relay"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def isolated_environment(root):
    env = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "WINDIR", "COMSPEC")
           if key in os.environ}
    for key, directory in {"HOME": "home", "USERPROFILE": "home", "CODEX_HOME": "codex",
                           "XDG_CONFIG_HOME": "config", "XDG_CACHE_HOME": "cache",
                           "XDG_DATA_HOME": "data", "XDG_STATE_HOME": "state",
                           "TMPDIR": "tmp", "TMP": "tmp", "TEMP": "tmp"}.items():
        path = root / directory
        path.mkdir(exist_ok=True)
        env[key] = str(path)
    # No caller API keys, auth, inherited Codex settings, or credential helpers.
    env.update({"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "NO_COLOR": "1",
                "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": str(root / "gitconfig"),
                "HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9",
                "ALL_PROXY": "http://127.0.0.1:9", "RUST_LOG": "error"})
    (root / "codex/config.toml").write_text(
        "[analytics]\nenabled = false\n[feedback]\nenabled = false\n", encoding="utf-8")
    return env


def run(binary, arguments, root, env):
    result = subprocess.run([str(binary), *arguments], cwd=root, env=env,
                            text=True, capture_output=True, timeout=30)
    require(result.returncode == 0, f"Codex {arguments[0]} failed: {result.stderr[-4000:]}")
    return result


def source_description(skill):
    """The shipped artifact uses a single-line YAML description, not a YAML parser."""
    lines = (skill / "SKILL.md").read_text(encoding="utf-8").splitlines()
    require(lines and lines[0] == "---", "Skill needs YAML frontmatter")
    end = lines.index("---", 1)
    fields = dict(line.split(":", 1) for line in lines[1:end] if ":" in line)
    require(fields.get("name", "").strip().strip("\"'") == NAME,
            "Expected the codex-relay Skill")
    description = fields.get("description", "").strip()
    if description.startswith('"'):
        description = json.loads(description)
    elif description.startswith("'") and description.endswith("'"):
        description = description[1:-1].replace("''", "'")
    require(description and description not in {">", "|", ">-", "|-"},
            "Qualification expects the shipped single-line description")
    return description


class Discovery:
    def __init__(self, binary, cwd, env):
        self.process = subprocess.Popen([str(binary), "app-server"], cwd=cwd, env=env,
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, text=True, encoding="utf-8")
        self.messages = queue.Queue()
        self.diagnostics = []
        self.warnings = []
        self.methods = []
        self.counter = 0
        self.readers = [threading.Thread(target=self.read_stdout, daemon=True),
                        threading.Thread(target=self.read_stderr, daemon=True)]
        for reader in self.readers:
            reader.start()

    def read_stdout(self):
        for line in self.process.stdout:
            try:
                self.messages.put(json.loads(line))
            except ValueError:
                self.messages.put({"invalid_json": True})
        self.messages.put({"eof": True})

    def read_stderr(self):
        for line in self.process.stderr:
            if len(self.diagnostics) < 100:
                self.diagnostics.append(line.rstrip())

    def send(self, method, params, request=True):
        require(method in {"initialize", "initialized", "skills/list"},
                "Only discovery protocol methods are allowed")
        self.methods.append(method)
        message = {"method": method, "params": params}
        if request:
            self.counter += 1
            message["id"] = self.counter
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()
        if not request:
            return None
        deadline = time.monotonic() + 30
        while True:
            remaining = deadline - time.monotonic()
            require(remaining > 0, f"Timed out waiting for {method}")
            try:
                response = self.messages.get(timeout=remaining)
            except queue.Empty as error:
                raise RuntimeError(f"Timed out waiting for {method}") from error
            require(not response.get("eof"), f"App-server exited before {method}")
            require(not response.get("invalid_json"), "Invalid app-server JSON output")
            if response.get("method") == "configWarning":
                self.warnings.append(response.get("params", {}).get("summary", "configWarning"))
            require("method" not in response or "id" not in response,
                    "Unexpected server request during discovery")
            if response.get("id") == message["id"]:
                require("error" not in response, f"{method}: {response.get('error')}")
                return response["result"]

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        for reader in self.readers:
            reader.join(timeout=2)


def entry(result, cwd):
    rows = [row for row in result.get("data", []) if Path(row["cwd"]).resolve() == cwd]
    require(len(rows) == 1, "Native skills/list did not return exactly the requested cwd")
    return rows[0]


def assert_discovered(row, target, description):
    matches = [item for item in row["skills"] if item["name"] == NAME]
    require(len(matches) == 1, "Expected exactly one native codex-relay discovery")
    skill = matches[0]
    require(Path(skill["path"]).resolve() == target / "SKILL.md", "Wrong native Skill path")
    require(skill["description"] == description, "Native description differs from artifact")
    require(skill["enabled"] is True and skill["scope"] == "repo",
            "Skill must be enabled in repository scope")
    return {key: skill[key] for key in ("name", "description", "scope", "enabled")}


def qualify(binary, skill):
    description = source_description(skill)
    files = list(skill.rglob("*"))
    require(all(not path.is_symlink() and (path.is_file() or path.is_dir()) for path in files),
            "Artifact must contain only ordinary files and directories")
    inventory = "".join(path.relative_to(skill).as_posix() + "\0" +
                        hashlib.sha256(path.read_bytes()).hexdigest() + "\n"
                        for path in sorted(files, key=lambda item: item.relative_to(skill).as_posix())
                        if path.is_file())
    artifact_sha256 = hashlib.sha256(inventory.encode("utf-8")).hexdigest()
    # TemporaryDirectory's root stays outside the source checkout on both platforms.
    with tempfile.TemporaryDirectory(prefix="relay-skill-client-") as temporary:
        root = Path(temporary).resolve()
        env = isolated_environment(root)
        version = run(binary, ["--version"], root, env)
        require(version.stdout.strip() == VERSION, "Expected exactly " + VERSION)
        schema = root / "schema"
        generated = run(binary, ["app-server", "generate-json-schema", "--out", str(schema)], root, env)
        params = json.loads((schema / "v2/SkillsListParams.json").read_text(encoding="utf-8"))
        response = json.loads((schema / "v2/SkillsListResponse.json").read_text(encoding="utf-8"))
        require({"cwds", "forceReload"} <= params["properties"].keys(),
                "Pinned native schema lacks the required discovery parameters")
        require({"name", "description", "path", "scope", "enabled"} <= set(
            response["definitions"]["SkillMetadata"]["required"]),
            "Pinned native schema lacks required Skill metadata")
        project = root / "project"
        project.mkdir()
        git = shutil.which("git", path=env.get("PATH"))
        require(git, "Git is required to create the disposable discovery repository")
        subprocess.run([git, "-c", "init.templateDir=", "init", "--quiet", str(project)],
                       cwd=root, env=env, check=True, capture_output=True, timeout=15)
        target = project / ".agents/skills" / NAME
        shutil.copytree(skill, target)
        nested = project / "src/nested"
        nested.mkdir(parents=True)
        outside = root / "unrelated"
        outside.mkdir()
        client = Discovery(binary, project, env)
        try:
            initialized = client.send("initialize", {"clientInfo": {
                "name": "relay_skill_qualification", "version": "0.1.0"}})
            require(Path(initialized["codexHome"]).resolve() == root / "codex",
                    "App-server did not use the isolated CODEX_HOME")
            client.send("initialized", {}, request=False)
            observed = client.send("skills/list", {"cwds": [str(project), str(nested), str(outside)],
                                                     "forceReload": True})
            found = []
            for cwd in (project, nested):
                row = entry(observed, cwd)
                require(not row["errors"], "Native Skill parse errors: " + str(row["errors"]))
                found.append(assert_discovered(row, target, description))
            foreign = entry(observed, outside)
            require(not foreign["errors"] and not any(s["name"] == NAME for s in foreign["skills"]),
                    "Repository Skill leaked into an unrelated cwd")
            # Exercise the real parser's error surface instead of assuming silence means parsing.
            malformed = project / ".agents/skills/invalid-probe/SKILL.md"
            malformed.parent.mkdir()
            malformed.write_text("---\nname: [invalid\n---\ninvalid fixture\n", encoding="utf-8")
            bad = entry(client.send("skills/list", {"cwds": [str(project)], "forceReload": True}), project)
            require(any(Path(error["path"]).resolve() == malformed for error in bad["errors"]),
                    "Native parser did not expose the malformed Skill")
            assert_discovered(bad, target, description)
        finally:
            client.close()
        require(client.process.returncode == 0, "App-server did not close cleanly")
        require(not (root / "codex/auth.json").exists(), "Discovery unexpectedly created auth state")
        require(not list((root / "codex").glob("sessions/**/*.jsonl")),
                "Discovery unexpectedly created a model session")
        return {"ok": True, "codex_version": version.stdout.strip(),
                "codex_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
                "artifact_sha256": artifact_sha256,
                "platform": initialized["platformOs"], "artifact_files": sum(p.is_file() for p in files),
                "discovery": found, "nested_cwd": "passed", "unrelated_cwd": "excluded",
                "malformed_skill": "reported", "methods_sent": client.methods,
                "model_calls": 0, "model_behavior": "UNVERIFIED",
                "warnings": list(dict.fromkeys(client.warnings)),
                "diagnostics": list(dict.fromkeys(
                    [line for line in (version.stderr + generated.stderr).splitlines() if line]
                    + client.diagnostics))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", required=True, type=Path, help="native Codex 0.162.1 executable")
    parser.add_argument("--skill", required=True, type=Path, help="standalone codex-relay artifact directory")
    args = parser.parse_args()
    try:
        result = qualify(args.codex.resolve(strict=True), args.skill.resolve(strict=True))
    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as error:
        print(json.dumps({"ok": False, "error": str(error), "model_calls": 0}))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
