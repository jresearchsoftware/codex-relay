#!/usr/bin/env python3
"""Opt-in Linux native VibeVM qualification of generated Relay guidance; never publish.

Creates only disposable /tmp fixtures and local fixture Git commits. Initial
anonymous acquisition of the pinned shared dependency requires network access;
ordinary projected-file use and subsequent native reinstall/projection are offline.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "guidance/artifacts/vpm"
# Accepted immutable consumer compatibility control, not a moving release lookup.
SHARED_FIVE = {
    "version": "5.0.0",
    "revision": "30a23f467c30c41fec918204cbbf2ecfffd7bef5",
    "tree_hash": "sha256:e686314f26c82f32f55958a242481d792e9fcd0d755a6eebf933431f3e0875d9",
}
SHARED_BELOW_FOUR = {"version": "3.0.0", "revision": "b6fefd51c2c34e4001e1709c9c157dfa2296ad60"}
SHARED_GIT = "https://github.com/jrs-vibevm/org.jresearch.ai.development-governance.git"
PROTOCOLS = ("context-loading", "task-handoff", "independent-review", "contract-and-decision-maintenance",
             "proportional-controls", "requirement-authority", "package-versioning", "self-adoption",
             "github-repository-governance")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def inventory(root):
    result = {}
    for path in sorted(root.rglob("*")):
        require(not path.is_symlink(), "Unexpected fixture/input symlink: " + str(path))
        if path.is_file():
            result[path.relative_to(root).as_posix()] = path.read_bytes()
    return result


def materialize(files, destination):
    for name, data in files.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(0o644)


def tree_hash(files):
    tree = hashlib.sha256()
    for name in sorted(files, key=lambda name: Path(name).parts):
        tree.update(name.encode() + b"\0" + files[name] + b"\0")
    return "sha256:" + tree.hexdigest()


def documents(data):
    result = []
    while data.strip():
        value, end = json.JSONDecoder().raw_decode(data.lstrip())
        result.append(value)
        data = data.lstrip()[end:]
    return result


def qualify(vibe):
    require(sys.platform.startswith("linux"), "Native filesystem qualification requires Linux")
    pin = json.loads((ROOT / "toolchain/vibevm.json").read_text())
    require(hashlib.sha256(vibe.read_bytes()).hexdigest() ==
            pin["linux_x86_64_musl_binary"]["sha256"], "VibeVM binary differs from pinned musl artifact")
    metadata = json.loads((ROOT / "guidance/source.json").read_text())
    candidate = inventory(ARTIFACT)
    require(candidate and "vibe.toml" in candidate, "Build generated VPM artifacts before qualification")
    manifest = tomllib.loads(candidate["vibe.toml"].decode())
    name, version = metadata["name"], metadata["version"]
    require(manifest["package"]["name"] == name and manifest["package"]["version"] == version,
            "Generated package identity differs from authoring metadata")
    requirement = metadata["shared_requirement"]
    lower_bound = re.fullmatch(r">=(\d+\.\d+\.\d+)", requirement)
    require(lower_bound, "Qualification expects the authored open-ended SemVer lower bound")
    require(manifest["requires"]["packages"][metadata["shared_coordinate"]] == requirement,
            "Generated package changes its declared shared compatibility requirement")
    shared_source = {"git": SHARED_GIT,
                     "rev": metadata["shared_distribution_revision"]}
    coordinate = manifest["package"]["group"] + "/" + name
    consumer_template = (ROOT / "guidance/artifacts/vpm-consumer.toml.in").read_text()
    declarations = tomllib.loads(consumer_template)["requires"]["packages"]
    require(set(declarations) == {coordinate, metadata["shared_coordinate"]},
            "Generated consumer adapter must declare exactly the two selected source roots")
    require(declarations[metadata["shared_coordinate"]] ==
            {"version": "=" + metadata["shared_version"], **shared_source, "auth": "none"},
            "Generated consumer adapter changes immutable shared source")
    require(declarations[coordinate] == {"version": "=" + version,
            "git": "REPLACE_WITH_SELECTED_RELAY_DISTRIBUTION_GIT_URL",
            "rev": "REPLACE_WITH_IMMUTABLE_RELAY_DISTRIBUTION_COMMIT", "auth": "none"},
            "Generated consumer adapter changes candidate identity or source placeholders")
    expected_skill = {key.removeprefix("skill/"): value for key, value in candidate.items()
                      if key.startswith("skill/")}
    standalone = inventory(ROOT / "guidance/artifacts/standalone" / name)
    require(not any(key.startswith("references/shared/") for key in expected_skill),
            "Native Skill must read the consumer's dependency, not a bundled shared snapshot")
    route = expected_skill["references/shared-protocols.md"].decode()
    require("vibe.lock" in route and "vibevm/vibedeps" in route and metadata["shared_coordinate"] in route,
            "Native shared route must resolve the consumer's reviewed lock and installed slot")
    require(all(topic + ".md" in route for topic in PROTOCOLS), "Native route omits an adopted protocol")
    require(any(key.startswith("references/shared/") for key in standalone),
            "Standalone Skill lost its offline immutable shared snapshot")
    require(expected_skill != standalone, "Delivery forms must retain their distinct shared-source packaging")
    lower_fixture = {"version": metadata["shared_version"], "revision": metadata["shared_distribution_revision"],
                     "tree_hash": metadata["shared_distribution_tree_hash"]}
    require(lower_fixture["version"] == lower_bound.group(1),
            "Select an immutable fixture for the authored minimum version before qualification")
    sandbox = Path(tempfile.mkdtemp(prefix="relay-guidance-vpm-", dir="/tmp"))
    env = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL") if key in os.environ}
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    for key, relative in {"HOME": "home", "XDG_CONFIG_HOME": "config", "XDG_CACHE_HOME": "cache",
                          "VIBE_SETTINGS": "settings"}.items():
        path = sandbox / relative
        path.mkdir()
        env[key] = str(path)
    env["VIBEVM_USER_CONFIG"] = str(sandbox / "settings/config.toml")
    reports = {}

    def run(label, cwd, arguments, native=False, refusal=False, offline=True, environment=None,
            expected_error=None):
        command = ([str(vibe), "--json", *( ["--offline"] if offline else [])] if native else []) + arguments
        result = subprocess.run(command, cwd=cwd, env=environment or env,
                                text=True, capture_output=True, timeout=120)
        (sandbox / (label + ".stdout")).write_text(result.stdout)
        (sandbox / (label + ".stderr")).write_text(result.stderr)
        reports[label] = {"exit": result.returncode, "command": command}
        if refusal:
            require(result.returncode != 0, label + " unexpectedly accepted unsafe state")
            expected = expected_error or ("tampered Vibe-owned skill file" if label == "managed-drift-refused"
                                          else "foreign pre-existing skill target")
            require(expected in result.stdout + result.stderr, label + " failed for an unrelated reason")
            return result
        require(result.returncode == 0, label + " failed: " + result.stdout + result.stderr)
        if native:
            require(not result.stderr.strip(), label + " emitted diagnostics: " + result.stderr)
            for value in documents(result.stdout):
                require(value.get("ok") is not False, label + " reported failure")
                if value.get("command") == "check":
                    require(value["summary"]["error"] == value["summary"]["warning"] == 0
                            and not value["findings"], label + " reported findings")
        return result

    tool_version = run("version", sandbox, [str(vibe), "--version"]).stdout.strip()
    require(tool_version == "vibe " + pin["version"], "Pinned tool version differs")
    package = sandbox / "package"
    package.mkdir()
    # Synthetic predecessor is a lifecycle fixture, never a published release.
    previous = dict(candidate)
    previous["vibe.toml"] = previous["vibe.toml"].replace(
        ('version = "' + version + '"').encode(), b'version = "0.0.0"', 1)
    previous["skill/SKILL.md"] += b"\nSynthetic predecessor qualification fixture.\n"
    old_provenance = json.loads(previous["skill/PROVENANCE.json"])
    old_provenance["version"] = "0.0.0"
    old_provenance["files"]["SKILL.md"] = hashlib.sha256(previous["skill/SKILL.md"]).hexdigest()
    previous["skill/PROVENANCE.json"] = (json.dumps(old_provenance, indent=2, sort_keys=True) + "\n").encode()
    materialize(previous, package)
    run("git-init", package, ["git", "init", "-q"])
    run("git-identity", package, ["git", "config", "user.name", "Synthetic Relay qualification"])
    run("git-email", package, ["git", "config", "user.email", "qualification@example.invalid"])
    run("git-maintenance", package, ["git", "config", "maintenance.auto", "false"])
    run("git-gc", package, ["git", "config", "gc.auto", "0"])
    # Local file transport uses upload-archive. Permit exact commit addressing in
    # this disposable fixture; public GitHub distribution uses its own transport.
    run("git-fixture-archive", package, ["git", "config", "uploadarchive.allowUnreachable", "true"])

    def commit(label):
        run(label + "-add", package, ["git", "add", "--all"])
        run(label + "-commit", package, ["git", "-c", "commit.gpgsign=false", "commit", "-qm", label])
        return run(label + "-head", package, ["git", "rev-parse", "HEAD"]).stdout.strip()

    old_revision = commit("synthetic-predecessor")
    materialize(candidate, package)
    revision = commit("actual-generated-candidate")
    consumer = sandbox / "consumer"
    consumer.mkdir()
    policy = b"# Local consumer policy\r\nKeep owner approval and existing overlays.\r\n"
    (consumer / "AGENTS.md").write_bytes(policy)
    neighbor = consumer / ".agents/skills/existing-local/SKILL.md"
    neighbor.parent.mkdir(parents=True)
    neighbor.write_bytes(b"Local unrelated Skill\n")

    def select(selected_version, selected_revision, shared_fixture=SHARED_FIVE, target=consumer):
        configured = consumer_template.replace("REPLACE_WITH_SELECTED_RELAY_DISTRIBUTION_GIT_URL", package.as_uri())
        configured = configured.replace("REPLACE_WITH_IMMUTABLE_RELAY_DISTRIBUTION_COMMIT", selected_revision)
        configured = configured.replace('version = "=' + version + '"',
                                        'version = "=' + selected_version + '"', 1)
        shared_declaration = '"' + metadata["shared_coordinate"] + '" = { version = "='
        configured = configured.replace(shared_declaration + metadata["shared_version"] + '"',
                                        shared_declaration + shared_fixture["version"] + '"')
        configured = configured.replace(metadata["shared_distribution_revision"], shared_fixture["revision"])
        (target / "vibe.toml").write_text(configured)

    def projection(label, refusal=False):
        return run(label, consumer, ["skill", "install", "--skill", name, "--agent", "codex",
                                    "--scope", "project", "--yes"], native=True, refusal=refusal)

    def local_content_preserved():
        require(policy in (consumer / "AGENTS.md").read_bytes(), "Native route replaced local policy")
        require(neighbor.read_bytes() == b"Local unrelated Skill\n", "Neighboring Skill changed")

    def installed_graph(target, shared_fixture, relay_revision):
        lock = tomllib.loads((target / "vibe.lock").read_text())
        require(lock["meta"]["schema_version"] == 7, "Expected the pinned native lock schema")
        packages = {entry["group"] + "/" + entry["name"]: entry for entry in lock["package"]}
        require(set(packages) == {coordinate, metadata["shared_coordinate"]}, "Expected exact two-package graph")
        require(packages[coordinate]["version"] == version and
                packages[coordinate]["source_ref"] == relay_revision and
                packages[coordinate]["content_hash"] == tree_hash(candidate), "Candidate lock identity differs")
        shared = packages[metadata["shared_coordinate"]]
        require(shared["version"] == shared_fixture["version"] and
                shared["source_ref"] == shared_fixture["revision"] and
                shared["content_hash"] == shared_fixture["tree_hash"], "Selected shared lock identity differs")
        shared_slot = target / "vibevm/vibedeps" / metadata["shared_coordinate"].replace("/", ".") / shared["version"]
        installed_shared = inventory(shared_slot)
        slot = tomllib.loads(installed_shared.pop(".vibe-slot.toml").decode())
        require(tree_hash(installed_shared) == shared["content_hash"], "Shared slot bytes differ from locked identity")
        require(slot["source_hash"] == shared["content_hash"] and
                {item["path"]: item["sha256"] for item in slot["file"]} ==
                {key: hashlib.sha256(value).hexdigest() for key, value in installed_shared.items()},
                "Shared slot receipt differs from locked dependency bytes")
        index = tomllib.loads((target / "vibevm/vibespecs/boot/INDEX.md").read_text())
        entries = [entry["path"] for entry in index["entry"]]
        expected_shared_boot = (shared_slot.relative_to(target) / "vibevm/vibespecs/boot/development-governance.md").as_posix()
        shared_routes = [entry for entry in entries if "development-governance" in entry]
        require(shared_routes == [expected_shared_boot], "Boot must route only to the consumer-selected shared slot")
        require(all((target / entry).is_file() for entry in entries), "Generated boot route is missing")
        for topic in PROTOCOLS:
            require((shared_slot / "vibevm/vibespecs/protocols" / (topic + ".md")).is_file(),
                    "Locked shared package is missing adopted protocol " + topic)
        require(inventory(target / ".agents/skills" / name) == expected_skill,
                "Native projection differs from native artifact")
        return packages

    select("0.0.0", old_revision)
    run("predecessor-install", consumer, ["install", "--no-default-registry", "--assume-yes"],
        native=True, offline=False)
    projection("predecessor-projection")
    select(version, revision)
    run("candidate-update", consumer, ["install", "--no-default-registry", "--assume-yes"],
        native=True, offline=False)
    projection("candidate-projection")
    destination = consumer / ".agents/skills" / name
    packages = installed_graph(consumer, SHARED_FIVE, revision)
    projection("repeat-projection")
    require(inventory(destination) == expected_skill, "Repeat projection changed bytes")
    select("0.0.0", old_revision)
    run("explicit-rollback", consumer, ["install", "--no-default-registry", "--assume-yes"], native=True)
    projection("rollback-projection")
    require((destination / "SKILL.md").read_bytes() == previous["skill/SKILL.md"],
            "Explicit rollback did not restore selected prior Skill")
    select(version, revision)
    run("restore-candidate", consumer, ["install", "--no-default-registry", "--assume-yes"], native=True)
    projection("restored-candidate-projection")
    require(inventory(destination) == expected_skill, "Candidate restoration after rollback differs")
    run("offline-reinstall", consumer, ["reinstall", ".", "--assume-yes"], native=True)
    projection("offline-projection")
    require(inventory(destination) == expected_skill, "Offline reinstall/projection changed bytes")
    run("native-check", consumer, ["check", "--path", "."], native=True)
    run("native-validate", consumer, ["validate", "--path", ".", "--no-default-registry"], native=True)
    local_content_preserved()
    fresh = sandbox / "fresh-clone"
    materialize({key: value for key, value in inventory(consumer).items()
                 if key.split("/")[0] not in {".git", ".vibe"}}, fresh)
    fresh_env = dict(env)
    for key in ("HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "VIBE_SETTINGS"):
        directory = sandbox / ("fresh-" + key.lower())
        directory.mkdir()
        fresh_env[key] = str(directory)
    fresh_env["VIBEVM_USER_CONFIG"] = str(sandbox / "fresh-vibe_settings/config.toml")
    run("fresh-clone-offline-reinstall", fresh, ["reinstall", ".", "--assume-yes"],
        native=True, environment=fresh_env)
    run("fresh-clone-offline-projection", fresh, ["skill", "install", "--skill", name,
        "--agent", "codex", "--scope", "project", "--yes"], native=True, environment=fresh_env)
    require(inventory(fresh / ".agents/skills" / name) == expected_skill,
            "Fresh clone with empty cache changed the offline projection")
    installed_graph(fresh, SHARED_FIVE, revision)
    lower_consumer = sandbox / "consumer-lower-bound"
    lower_consumer.mkdir()
    select(version, revision, shared_fixture=lower_fixture, target=lower_consumer)
    run("lower-bound-install", lower_consumer, ["install", "--no-default-registry", "--assume-yes"],
        native=True, offline=False)
    run("lower-bound-projection", lower_consumer, ["skill", "install", "--skill", name, "--agent", "codex",
        "--scope", "project", "--yes"], native=True)
    lower_packages = installed_graph(lower_consumer, lower_fixture, revision)
    lower_shared = inventory(lower_consumer / "vibevm/vibedeps" /
                             metadata["shared_coordinate"].replace("/", ".") / lower_fixture["version"])
    lower_shared.pop(".vibe-slot.toml")
    require(lower_shared == {key.removeprefix("references/shared/"): value for key, value in standalone.items()
                             if key.startswith("references/shared/")},
            "Standalone snapshot differs from the qualified immutable lower-bound package")
    run("lower-bound-check", lower_consumer, ["check", "--path", "."], native=True)
    run("lower-bound-validate", lower_consumer, ["validate", "--path", ".", "--no-default-registry"], native=True)
    # The pinned preceding release is genuinely outside the authored >=4.0.0
    # window. Let the native resolver prove refusal, rather than a local solver.
    require(lower_fixture["version"] == "4.0.0", "Select a preceding immutable negative fixture for the changed bound")
    below_consumer = sandbox / "consumer-below-bound"
    below_consumer.mkdir()
    (below_consumer / "AGENTS.md").write_bytes(policy)
    select(version, revision, shared_fixture=SHARED_BELOW_FOUR, target=below_consumer)
    run("below-bound-refused", below_consumer, ["install", "--no-default-registry", "--assume-yes"],
        native=True, offline=False, refusal=True, expected_error="unsatisfiable")
    require(not (below_consumer / "vibe.lock").exists() and
            not (below_consumer / ".agents/skills" / name).exists() and
            (below_consumer / "AGENTS.md").read_bytes() == policy,
            "Unsatisfiable dependency selection changed consumer policy, lock or Skill")
    # Native Skill receipt guards drift; lifecycle `package` is deliberately not used.
    skill_path = destination / "SKILL.md"
    altered = skill_path.read_bytes() + b"\nLocal edit to preserve.\n"
    skill_path.write_bytes(altered)
    before = inventory(destination)
    projection("managed-drift-refused", refusal=True)
    require(inventory(destination) == before, "Drift refusal modified local Skill bytes")
    skill_path.write_bytes(expected_skill["SKILL.md"])
    extra = destination / "local-addition.txt"
    extra.write_bytes(b"Local additional file\n")
    run("remove-projection", consumer, ["skill", "uninstall", "--skill", name, "--agent", "codex",
                                       "--scope", "project", "--yes"], native=True)
    require(inventory(destination) == {"local-addition.txt": b"Local additional file\n"},
            "Native uninstall removed foreign additions or retained owned files")
    local_content_preserved()
    projection("foreign-collision-refused", refusal=True)
    require(extra.read_bytes() == b"Local additional file\n", "Collision refusal lost local content")
    run("remove-relay-package", consumer, ["uninstall", coordinate, "--assume-yes"], native=True)
    remaining = tomllib.loads((consumer / "vibe.lock").read_text())["package"]
    require(len(remaining) == 1 and remaining[0]["name"] == "development-governance",
            "Removing Relay must preserve independently selected shared root")
    local_content_preserved()
    result = {"vpm_qualification": "PASS", "version": version, "tool": tool_version,
              "graph": {key: {field: value[field] for field in ("version", "content_hash", "source_ref")}
                        for key, value in packages.items()},
              "shared_requirement": requirement,
              "lower_bound_graph": {key: {field: value[field] for field in ("version", "content_hash", "source_ref")}
                                    for key, value in lower_packages.items()},
              "below_bound": {**SHARED_BELOW_FOUR, "result": "native resolver unsatisfiable"},
              "delivery_forms": "same Relay contract; native locked dependency and standalone immutable snapshot",
              "native_protocol_routing": "consumer lock/slot and sole selected shared boot route verified",
              "update_rollback_repeat_offline_drift_removal": "PASS",
              "candidate_source": "generated source proposal; local Git fixture, not external publication",
              "artifact_sha256": {key: hashlib.sha256(value).hexdigest() for key, value in candidate.items()},
              "consumer_adapter_sha256": hashlib.sha256(consumer_template.encode()).hexdigest(),
              "dependency_transport": "two explicit immutable consumer roots; VibeVM 1.0.7 omits transitive Git declarations",
              "model_behavior": "UNVERIFIED: native tool and file qualification only",
              "evidence_directory": str(sandbox), "commands": reports}
    (sandbox / "qualification.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vibe", required=True, type=Path, help="hash-pinned Linux musl VibeVM 1.0.7 binary")
    args = parser.parse_args()
    try:
        result = qualify(args.vibe.resolve())
        print(json.dumps({key: value for key, value in result.items()
                          if key not in {"commands", "artifact_sha256"}}, sort_keys=True))
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
