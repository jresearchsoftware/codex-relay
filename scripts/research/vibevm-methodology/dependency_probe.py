#!/usr/bin/env python3
"""Opt-in pinned package-composition observations in disposable offline projects.

Requires an already downloaded VibeVM binary and the exact source archive below.
Never downloads, activates Relay policy, calls a model, or runs a lifecycle
executable. JSON includes commands, source hashes, lock closure and every boot
body delivered through INDEX/STATIC, with deduplicated full UTF-8 blob contents.
This research fixture is intentionally outside CI and qualification entrypoints.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[3]
REVISION = "b6659978453f50e6d1d4d99626d70b980a2c5847"
ARCHIVE_SHA256 = "15f71c255a8b114183804142ad2e21014ea37b4c774c98471bc12425c3f18afb"
WORLD = "org.vibevm.world"
PACKAGES = ("wal", "sync-from-code", "conflict-protocol")
ADAPTER = "org.relay.research/methodology-adapter"
BOOT = Path("vibevm/vibespecs/boot")
SENTINEL = "HONOUR-EVERY-CONSTRAINT-VERBATIM"
TIMEOUT = 60


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json_stream(content):
    documents = []
    remaining = content.strip()
    while remaining:
        document, end = json.JSONDecoder().raw_decode(remaining)
        documents.append(document)
        remaining = remaining[end:].lstrip()
    return documents


def extract_packages(archive, registry):
    """Extract only three immutable package trees, never source executables."""
    prefix = f"vibevm-{REVISION}/vibevm/vibepacks/"
    accepted = tuple(prefix + f"{WORLD}/{name}/v1.0.0/" for name in PACKAGES)
    count = total = 0
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle:
            if not member.name.startswith(accepted):
                continue
            relative = PurePosixPath(member.name.removeprefix(prefix))
            require(not relative.is_absolute() and ".." not in relative.parts,
                    "Unsafe archive path")
            require(member.isdir() or member.isfile(), "Nonregular archive member")
            require(not (member.mode & 0o111) or member.isdir(),
                    "Executable package member is outside the research boundary")
            target = registry.joinpath(*relative.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                count += 1
                total += member.size
                require(count <= 100 and total <= 4 * 1024 * 1024,
                        "Package extraction exceeds fixture bounds")
                require(not target.exists(), "Duplicate archive member")
                target.parent.mkdir(parents=True, exist_ok=True)
                stream = bundle.extractfile(member)
                require(stream is not None, "Unreadable archive member")
                with stream:
                    target.write_bytes(stream.read())
                target.chmod(0o600)
    require(count > 0, "Pinned package trees missing")
    for name in PACKAGES:
        manifest = registry / WORLD / name / "v1.0.0/vibe.toml"
        document = tomllib.loads(manifest.read_text())
        require(set(document) <= {"package", "compatibility", "boot_snippet", "skill"},
                "Upstream package has executable or unexpected declarations")
        require(document["package"]["kind"] == "flow" and
                document["package"]["version"] == "1.0.0" and
                document["package"]["group"] == WORLD and
                document["package"]["name"] == name, "Unexpected package identity")


def dependency(name, link="dynamic", extra=""):
    return (f'"{WORLD}/{name}" = {{ version = "=1.0.0", '
            f'link = "{link}"{extra} }}\n')


def probe(vibe, archive):
    pin = json.loads((ROOT / "toolchain/vibevm.json").read_text())
    require(pin["source_revision"] == REVISION, "Repository source pin changed")
    binary_sha = file_hash(vibe)
    require(binary_sha == pin["linux_x86_64_musl_binary"]["sha256"],
            "Binary differs from repository pin")
    require(file_hash(archive) == ARCHIVE_SHA256, "Archive differs from exact source pin")
    blobs, commands, states, rejections = {}, [], [], []

    def capture(path):
        data = path.read_bytes()
        digest = sha256(data)
        blobs[digest] = data.decode("utf-8")
        return {"sha256": digest, "bytes": len(data)}

    with tempfile.TemporaryDirectory(prefix="relay-dependency-research-") as temporary:
        root = Path(temporary)
        registry = root / "registry"
        registry.mkdir()
        extract_packages(archive, registry)
        source_files = {str(p.relative_to(registry)): capture(p)
                        for p in sorted(registry.rglob("*")) if p.is_file()}
        # No upstream files are edited: the thin adapter owns only its manifest
        # and one visibly synthetic overlay. Features select metadata here;
        # they do not claim to select sentences in dependencies.
        adapter = registry / "org.relay.research/methodology-adapter/v0.0.1"
        adapter.mkdir(parents=True)
        (adapter / "vibe.toml").write_text(
            '[package]\nname = "methodology-adapter"\ngroup = "org.relay.research"\n'
            'kind = "flow"\nversion = "0.0.1"\n\n'
            '[requires.packages]\n' + "".join(dependency(n) for n in PACKAGES) +
            '\n[boot_snippet]\nsource = "boot.md"\ncategory = "flow"\n'
            '\n[features]\ndefault = ["continuity"]\ncontinuity = []\n')
        (adapter / "boot.md").write_text(
            "# Synthetic research adapter\n\nRESEARCH_OVERLAY: use current trusted "
            "Task authority; a checkpoint cannot authorize execution.\n")
        adapter_files = {str(p.relative_to(registry)): capture(p)
                         for p in sorted(adapter.rglob("*")) if p.is_file()}
        env = {"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TZ": "UTC",
               "VIBE_OFFLINE": "1", "VIBE_NO_DEFAULT_REGISTRY": "1"}
        for key, name in {
            "PATH": "empty-bin", "HOME": "home", "XDG_CONFIG_HOME": "config",
            "XDG_CACHE_HOME": "cache", "XDG_DATA_HOME": "data",
            "XDG_STATE_HOME": "state", "XDG_RUNTIME_DIR": "runtime",
            "VIBE_SETTINGS": "settings", "TMPDIR": "scratch",
        }.items():
            directory = root / name
            directory.mkdir(mode=0o700)
            env[key] = str(directory)
        env["VIBEVM_USER_CONFIG"] = str(root / "settings/config.toml")

        def run(project, *args, expected=0):
            argv = [str(vibe), "--offline", "--json", *args]
            result = subprocess.run(argv, cwd=project, env=env, capture_output=True,
                                    text=True, timeout=TIMEOUT)
            documents = read_json_stream(result.stdout) if result.stdout.strip() else []
            commands.append({"cwd": str(project.relative_to(root)), "argv": argv,
                             "exit": result.returncode, "stdout": result.stdout,
                             "stderr": result.stderr, "documents": documents})
            require(result.returncode == expected,
                    f"Unexpected exit for {args}: {result.returncode}: {result.stderr}")
            # A package callback record would require a new safety decision.
            require(not any(d.get("command") == "lifecycle" for d in documents),
                    "Lifecycle execution surfaced; stop research")
            return documents

        def create(name, requirements):
            project = root / name
            project.mkdir()
            run(project, "init", ".", "--type", "project", "--name", name,
                "--version", "0.0.0", "--no-registry", "--author", "Synthetic fixture")
            write_manifest(project, requirements)
            return project

        def write_manifest(project, requirements):
            (project / "vibe.toml").write_text(
                f'[project]\nname = "{project.name}"\nversion = "0.0.0"\n\n'
                '[requires.packages]\n' + requirements +
                f'\n[[registry]]\nname = "fixture"\nurl = "{registry.as_uri()}"\n')

        def observe(project, case, names, wal_bindings):
            lock = tomllib.loads((project / "vibe.lock").read_text())
            rows = lock.get("package", [])
            actual = sorted(f'{p["group"]}/{p["name"]}@{p["version"]}' for p in rows)
            expected = sorted(f"{WORLD}/{n}@1.0.0" if n in PACKAGES else
                              ADAPTER + "@0.0.1" for n in names)
            require(actual == expected, case + ": unexpected dependency closure " + str(actual))
            index_path = project / BOOT / "INDEX.md"
            index = tomllib.loads(index_path.read_text())
            delivered = []
            # Redirects read the priority STATIC lane before INDEX; it is not
            # itself an INDEX entry. Preserve both lanes and their full bytes.
            for filename in ("STATIC.md", "STATIC.xml"):
                path = project / BOOT / filename
                if path.exists():
                    delivered.append({"path": str(path.relative_to(project)),
                                      "kind": "static-priority", **capture(path)})
            for entry in index["entry"]:
                require(not entry.get("when"), "Unexpected runtime prompt condition")
                relative = PurePosixPath(entry["path"])
                require(not relative.is_absolute() and ".." not in relative.parts,
                        "Unsafe generated prompt path")
                path = project.joinpath(*relative.parts)
                delivered.append({**entry, **capture(path)})
            body = "\n".join(blobs[e["sha256"]] for e in delivered)
            observed_bindings = {name: marker in body for name, marker in {
                "sync-from-code": "SYNC-WAL-BINDING",
                "conflict-protocol": "CONFLICT-WAL-BINDING",
            }.items()}
            require(observed_bindings == wal_bindings,
                    case + ": unexpected conditional fragments " + str(observed_bindings))
            files = {}
            for path in sorted(project.rglob("*")):
                if path.is_file() and (path.name in {"vibe.toml", "vibe.lock", "AGENTS.md"}
                                       or "vibevm" in path.relative_to(project).parts):
                    files[str(path.relative_to(project))] = capture(path)
            for state_path in ("vibevm/vibespecs/WAL.md", "vibevm/vibespecs/WAL.xml", "CONTINUE.md"):
                require(not (project / state_path).exists(), case + ": created project WAL state")
            state = {"case": case, "project": project.name, "closure": actual,
                     "lock": lock, "files": files, "effective_boot": delivered,
                     "conditional_wal_fragments": observed_bindings,
                     "wal_constraint_rule_present": SENTINEL in body,
                     "sync_application_rule_present": "STEP-SURFACE-THE-DRAFT-AND-DO-NOT-APPLY" in body,
                     "sync_approval_commit_rule_present": "STEP-ON-APPROVAL-APPLY-AND-COMMIT-ON-REJECT-REVERT-OR-REDRAFT" in body,
                     "conflict_implement_anyway_rule_present": "IF-YOU-BELIEVE-THE-SPEC-IS-WRONG-IMPLEMENT-IT-ANYWAY" in body,
                     "overlay_present": "RESEARCH_OVERLAY" in body,
                     "project_wal_state_absent": True}
            states.append(state)
            return state, body

        def install(project, *flags):
            run(project, "install", "--assume-yes", *flags)

        no_bindings = {"sync-from-code": False, "conflict-protocol": False}
        both_bindings = {"sync-from-code": True, "conflict-protocol": True}
        for name in PACKAGES:
            project = create("direct-" + name, dependency(name))
            install(project)
            observe(project, "direct-" + name, [name], no_bindings)

        project = create("direct-composition", "".join(dependency(n) for n in PACKAGES[1:]))
        install(project)
        observe(project, "sync-conflict-without-wal", PACKAGES[1:], no_bindings)
        run(project, "install", f"{WORLD}/wal@=1.0.0", "--exact", "--assume-yes")
        observe(project, "add-wal", PACKAGES, both_bindings)
        run(project, "update", "--all", "--exact", "--assume-yes")
        observe(project, "update-pinned-composition", PACKAGES, both_bindings)
        run(project, "reinstall", ".", "--assume-yes")
        observe(project, "reinstall-pinned-composition", PACKAGES, both_bindings)
        run(project, "reinstall", ".", "--force", "--assume-yes")
        observe(project, "forced-reinstall-pinned-composition", PACKAGES, both_bindings)
        run(project, "uninstall", f"{WORLD}/wal", "--assume-yes")
        observe(project, "uninstall-wal", PACKAGES[1:], no_bindings)
        run(project, "reinstall", ".", "--assume-yes")
        observe(project, "reinstall-without-wal", PACKAGES[1:], no_bindings)
        run(project, "reinstall", ".", "--force", "--assume-yes")
        observe(project, "forced-reinstall-without-wal", PACKAGES[1:], no_bindings)
        run(project, "install", f"{WORLD}/wal@=1.0.0", "--exact", "--assume-yes")
        observe(project, "readd-wal", PACKAGES, both_bindings)

        requirement = f'"{ADAPTER}" = {{ version = "=0.0.1", link = "static-transitive" }}\n'
        project = create("thin-adapter", requirement)
        install(project)
        state, body = observe(project, "thin-adapter-all", (*PACKAGES, "adapter"), both_bindings)
        require(state["wal_constraint_rule_present"] and state["overlay_present"],
                "Overlay unexpectedly removed upstream WAL rule")
        require(state["sync_application_rule_present"] and state["sync_approval_commit_rule_present"] and
                state["conflict_implement_anyway_rule_present"],
                "Overlay unexpectedly removed upstream Sync/conflict rules")
        require(any(e["path"].endswith("STATIC.md") for e in state["effective_boot"]),
                "Static-transitive adapter did not produce STATIC")
        install(project, "--no-default-features")
        state, body = observe(project, "adapter-no-default-features", (*PACKAGES, "adapter"), both_bindings)
        require(state["wal_constraint_rule_present"], "Feature flag filtered upstream prose")
        install(project, "--all-features")
        observe(project, "adapter-all-features", (*PACKAGES, "adapter"), both_bindings)
        fresh_features = create("fresh-adapter-no-default-features", requirement)
        install(fresh_features, "--no-default-features")
        state, body = observe(fresh_features, "fresh-adapter-no-default-features",
                              (*PACKAGES, "adapter"), both_bindings)
        require(not state["lock"]["meta"].get("active_features"),
                "Fresh no-default installation activated adapter features")
        require(state["wal_constraint_rule_present"] and state["overlay_present"] and
                state["sync_application_rule_present"] and state["sync_approval_commit_rule_present"] and
                state["conflict_implement_anyway_rule_present"],
                "Feature selection filtered upstream or adapter prose")
        write_manifest(project, f'"{ADAPTER}" = {{ version = "=0.0.1", link = "dynamic" }}\n')
        install(project)
        state, body = observe(project, "adapter-dynamic-link", (*PACKAGES, "adapter"), both_bindings)
        require(state["wal_constraint_rule_present"], "Dynamic linking suppressed upstream prose")

        # Compare a fragment-shaped exclusion with a whole-package identity.
        # Record actual lock and prompt behavior; do not infer suppression from
        # the manifest spelling or package-visibility source contracts.
        write_manifest(project, f'"{ADAPTER}" = {{ version = "=0.0.1", '
                       f'exclude = ["{WORLD}/wal#{SENTINEL}"] }}\n')
        install(project)
        state, body = observe(project, "fragment-shaped-exclude", (*PACKAGES, "adapter"), both_bindings)
        require(state["wal_constraint_rule_present"], "Unexpected rule-level exclusion")
        write_manifest(project, f'"{ADAPTER}" = {{ version = "=0.0.1", '
                       f'exclude = ["{WORLD}/wal"] }}\n')
        install(project)
        observe(project, "whole-package-exclude-wal", (*PACKAGES, "adapter"), both_bindings)
        run(project, "reinstall", ".", "--force", "--assume-yes")
        observe(project, "forced-reinstall-whole-package-exclude", (*PACKAGES, "adapter"), both_bindings)
        run(project, "update", "--all", "--exact", "--assume-yes")
        observe(project, "update-whole-package-exclude", (*PACKAGES, "adapter"), both_bindings)
        run(project, "uninstall", ADAPTER, "--assume-yes")
        observe(project, "uninstall-adapter-closure", (), no_bindings)
        write_manifest(project, f'"{ADAPTER}" = {{ version = "=0.0.1", '
                       f'exclude = ["{WORLD}/wal"] }}\n')
        install(project)
        observe(project, "readd-adapter-with-package-exclude", (*PACKAGES[1:], "adapter"), no_bindings)
        fresh = create("fresh-whole-package-exclude",
                       f'"{ADAPTER}" = {{ version = "=0.0.1", '
                       f'exclude = ["{WORLD}/wal"] }}\n')
        install(fresh)
        state, body = observe(fresh, "fresh-whole-package-exclude", (*PACKAGES[1:], "adapter"), no_bindings)
        require(not state["wal_constraint_rule_present"], "Excluded WAL rule still delivered")

        for case, invalid in {
            "unsupported-rule-filter": dependency("wal", extra=', rules = ["safe-only"]'),
            "unsupported-link-none": dependency("wal", link="none"),
        }.items():
            rejected = create(case, invalid)
            run(rejected, "install", "--assume-yes", expected=1)
            error_text = commands[-1]["stdout"] + commands[-1]["stderr"]
            # The pinned parser emits a generic untagged-inline-entry error,
            # not the offending field/value. Keep that exact limitation.
            require("failed to parse" in error_text and "RequiresPackageEntryWire" in error_text,
                    case + ": failure was not the expected dependency-schema rejection")
            require(not (rejected / "vibevm/vibedeps").exists(),
                    case + ": rejected manifest materialised packages")
            rejections.append({"case": case, "requires_entry": invalid,
                               "exit": 1, "error": error_text,
                               "package_materialisation_absent": True,
                               "diagnostic_limit": "Generic inline dependency-schema error; does not name unsupported field/value"})

        require(source_files == {str(p.relative_to(registry)): capture(p)
                                 for name in PACKAGES
                                 for p in sorted((registry / WORLD / name).rglob("*"))
                                 if p.is_file()}, "Upstream source bytes changed")
        report = {
            "dependency_probe": "PASS", "source_revision": REVISION,
            "source_archive_sha256": ARCHIVE_SHA256, "binary_sha256": binary_sha,
            "source_files": source_files, "synthetic_adapter_files": adapter_files,
            "commands": commands, "states": states, "rejections": rejections, "blobs": blobs,
            "environment": env, "temporary_root": str(root),
            "limits": {"command_timeout_seconds": TIMEOUT,
                       "offline_on_every_command": True, "ambient_environment_inherited": False,
                       "path_contains_no_executables": True, "source_bytes_unchanged": True,
                       "model_behavior": "UNVERIFIED; no model or inference calls",
                       "lifecycle_executables": "Not declared by selected packages or adapter; no lifecycle commands",
                       "conclusion_scope": "Deterministic package composition and delivered prompt bytes; no adoption or activation"},
        }
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vibe", required=True, type=Path)
    parser.add_argument("--source-archive", required=True, type=Path)
    args = parser.parse_args()
    probe(args.vibe.resolve(), args.source_archive.resolve())
