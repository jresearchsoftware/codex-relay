#!/usr/bin/env python3
"""Credential-free release/installer/parser qualification in a temporary CI home.

This does not call a model or mutate the governed production runtime. The
separate installed_runtime_proof.py exercises real launcher/users/sudo with a
deterministic child; this probe exercises the official release itself.
"""
import stat
from pathlib import Path
import subprocess
import tempfile

import yaml

REPO = Path(__file__).resolve().parents[3]


def qualify():
    variables = yaml.safe_load((REPO / "deploy/ansible/group_vars/all.yml").read_text())
    version = variables["relay_codex_cli_version"]
    assert version == "0.154.0"
    with tempfile.TemporaryDirectory(prefix="codex-cli-qualification-") as temporary:
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
        print(f"CODEX_CLI_QUALIFICATION_PASS=version={version}; official-installer; release-symlink; deploy-umask=0077; package-roots=0700; explicit-argv; syntax-only; model-call=none")


if __name__ == "__main__":
    qualify()
