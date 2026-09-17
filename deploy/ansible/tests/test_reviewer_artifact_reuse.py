"""Static and contract-level tests for verified Reviewer artifact reuse."""

from pathlib import Path
import base64
import json
import unittest


ROOT = Path(__file__).resolve().parents[1]


def reuse_allowed(current_manifest, expected, observed_digest):
    """Mirror the fail-closed evidence contract without touching a host."""
    return (
        current_manifest.get("schemaVersion") == "1.0"
        and current_manifest.get("commit") == expected["commit"]
        and current_manifest.get("releaseSourceTreeSha256", "") == expected["release"]
        and current_manifest.get("controllerSourceTreeSha256", "") == expected["controller"]
        and current_manifest.get("reviewerSourceTreeSha256") == expected["source"]
        and current_manifest.get("reviewerBuildInputsTreeSha256") == expected["inputs"]
        and current_manifest.get("reviewerBuildContractSha256") == expected["contract"]
        and current_manifest.get("reviewerBuildToolchain", {}).get("archiveSha256") == expected["toolchain"]
        and current_manifest.get("reviewerBuildToolchain", {}).get("cargoVersion", "").startswith("cargo " + expected["rust"])
        and current_manifest.get("reviewerBinarySha256") == observed_digest
        and current_manifest.get("reviewerArtifactProvenance") in {"built", "verified-reuse"}
    )


def parse_manifest_for_reuse(raw_result):
    """Mirror the Ansible content-presence guard for skipped slurp results."""
    if "content" not in raw_result:
        return None
    return json.loads(base64.b64decode(raw_result["content"]))


class ReviewerArtifactReuseTests(unittest.TestCase):
    def setUp(self):
        artifact_tasks = ROOT / "roles" / "relay_artifacts" / "tasks"
        self.artifacts = "\n".join(
            (artifact_tasks / name).read_text(encoding="utf-8")
            for name in ("main.yml", "resolve-identities.yml", "verify-reviewer-reuse.yml")
        )
        self.manifest = (ROOT / "roles" / "relay_artifacts" / "templates" / "artifact-manifest.json.j2").read_text(encoding="utf-8")
        self.probe = (ROOT / "roles" / "relay_controller" / "templates" / "relay-qualification-codex-probe.mjs.j2").read_text(encoding="utf-8")
        self.expected = {
            "commit": "a" * 40,
            "release": "r" * 64,
            "controller": "c" * 64,
            "source": "source",
            "inputs": "inputs",
            "contract": "contract",
            "toolchain": "toolchain",
            "rust": "1.90.0",
        }

    def test_reuse_requires_verified_content_build_and_digest_identity(self):
        for marker in (
            "relay_reviewer_build_inputs_tree_sha256",
            "relay_reviewer_build_contract_sha256",
            "reviewerArtifactProvenance",
            "reviewerReuseSourceRelease",
            "reviewerReuseSourceBinarySha256",
            "relay_reviewer_reuse_verified",
            "reviewerBuildToolchain.archiveSha256",
            "reviewerBuildToolchain.cargoVersion",
            "relay_current_release.stat.lnk_source",
            "islnk",
            "Re-use the verified Reviewer executable".replace("Re-use", "Reuse"),
            "not relay_reviewer_reuse_verified | bool",
            "sha256sum",
        ):
            self.assertIn(marker, self.artifacts + self.manifest)

    def test_reuse_provenance_is_rendered_after_the_eligibility_fact(self):
        eligibility = self.artifacts.index("relay_reviewer_reuse_verified:")
        provenance = self.artifacts.index("Record verified Reviewer reuse provenance")
        self.assertLess(eligibility, provenance)
        self.assertIn('"reviewerArtifactProvenance": "{{ relay_reviewer_artifact_provenance }}"', self.manifest)
        self.assertIn('"reviewerReuseSourceRelease": "{{ relay_reviewer_reuse_source_release }}"', self.manifest)

    def test_unchanged_verified_artifact_is_reusable(self):
        current = {
            "schemaVersion": "1.0",
            "commit": "a" * 40,
            "releaseSourceTreeSha256": "r" * 64,
            "controllerSourceTreeSha256": "c" * 64,
            "reviewerSourceTreeSha256": "source",
            "reviewerBuildInputsTreeSha256": "inputs",
            "reviewerBuildContractSha256": "contract",
            "reviewerBuildToolchain": {"archiveSha256": "toolchain", "cargoVersion": "cargo 1.90.0 (stable)"},
            "reviewerBinarySha256": "digest",
            "reviewerArtifactProvenance": "built",
        }
        self.assertTrue(reuse_allowed(current, self.expected, "digest"))

    def test_missing_current_manifest_skipped_slurp_keeps_no_reuse_default(self):
        self.assertIsNone(parse_manifest_for_reuse({"skipped": True}))
        self.assertIn("relay_current_reviewer_manifest_raw.content is defined", self.artifacts)

    def test_present_valid_current_manifest_is_parsed_for_reuse_evaluation(self):
        raw = {"content": base64.b64encode(json.dumps({"schemaVersion": "1.0"}).encode()).decode()}
        self.assertEqual(parse_manifest_for_reuse(raw), {"schemaVersion": "1.0"})
        self.assertIn("relay_current_reviewer_manifest_raw.content | b64decode | from_json", self.artifacts)

    def test_present_malformed_current_manifest_fails_closed(self):
        raw = {"content": base64.b64encode(b"not-json").decode()}
        with self.assertRaises(json.JSONDecodeError):
            parse_manifest_for_reuse(raw)
        self.assertIn("from_json", self.artifacts)

    def test_changed_or_unverified_evidence_rebuilds(self):
        current = {
            "schemaVersion": "1.0",
            "commit": "a" * 40,
            "releaseSourceTreeSha256": "r" * 64,
            "controllerSourceTreeSha256": "c" * 64,
            "reviewerSourceTreeSha256": "source",
            "reviewerBuildInputsTreeSha256": "inputs",
            "reviewerBuildContractSha256": "contract",
            "reviewerBuildToolchain": {"archiveSha256": "toolchain", "cargoVersion": "cargo 1.90.0 (stable)"},
            "reviewerBinarySha256": "digest",
            "reviewerArtifactProvenance": "built",
        }
        for field, value in (
            ("reviewerSourceTreeSha256", "changed"),
            ("reviewerBuildInputsTreeSha256", "changed"),
            ("reviewerBuildContractSha256", "changed"),
            ("reviewerArtifactProvenance", "unknown"),
        ):
            candidate = {**current, field: value}
            self.assertFalse(reuse_allowed(candidate, self.expected, "digest"), field)
        self.assertFalse(reuse_allowed(current, self.expected, "wrong-digest"))
        for field, value in (
            ("commit", "b" * 40),
            ("releaseSourceTreeSha256", "changed"),
            ("controllerSourceTreeSha256", "changed"),
        ):
            candidate = {**current, field: value}
            self.assertFalse(reuse_allowed(candidate, self.expected, "digest"), field)
        for field, value in (
            ("archiveSha256", "changed"),
            ("cargoVersion", "cargo 1.89.0 (stable)"),
        ):
            candidate = {**current, "reviewerBuildToolchain": {**current["reviewerBuildToolchain"], field: value}}
            self.assertFalse(reuse_allowed(candidate, self.expected, "digest"), field)

    def test_non_routing_probe_uses_the_runner_owned_real_codex_path(self):
        for marker in (
            "runCodex",
            "gpt-5.6-luna",
            'effort: "high"',
            'WORK_ROOT = "{{ relay_state_root }}/dispatch-work"',
            "await chmod(cwd, 0o2770)",
            "CODEX_RUNTIME_TIMEOUT_MS: \"600000\"",
            "childStarted",
            "diagnosticStore",
            "Do not access GitHub",
        ):
            self.assertIn(marker, self.probe)
        self.assertNotIn("CODEX_ACCESS_TOKEN", self.probe)


if __name__ == "__main__":
    unittest.main()
