"""Portable, offline checks for the public subagent flow (Python 3.11+)."""

from pathlib import Path
import re
import tomllib
import unittest
from urllib.parse import unquote, urlsplit


PACKAGE = Path(__file__).resolve().parents[1]
POLICY = "vibevm/vibespecs/protocols/subagents.md"
RUNTIME = "vibevm/vibespecs/guides/runtime-evidence.md"
BOOT = "vibevm/vibespecs/boot/landscape-subagents.md"


class PackageChecks(unittest.TestCase):
    def test_manifest_contract(self):
        manifest = tomllib.loads((PACKAGE / "vibe.toml").read_text(encoding="utf-8"))
        self.assertEqual(set(manifest), {"package", "boot_snippet"})
        self.assertEqual(
            manifest["package"],
            {
                "group": "org.jresearch.ai", "name": "landscape-subagents",
                "version": "1.0.2", "kind": "flow", "format": "simple",
                "epoch": 1, "publish": False, "frozen": True, "license": "MIT",
                "description": "Passive, explicitly adopted subagent workflow and child-profile guidance.",
            },
        )
        self.assertEqual(
            manifest["boot_snippet"],
            {"source": BOOT, "category": "flow", "link": "dynamic"},
        )

    def test_mit_license(self):
        notice = (PACKAGE / "LICENSE").read_text(encoding="utf-8")
        self.assertTrue(notice.startswith(
            "MIT License\n\nCopyright (c) 2026 Codex Model Landscape contributors\n"
        ))
        self.assertIn("Permission is hereby granted, free of charge", notice)

    def test_policy_and_profile_contract(self):
        policy = (PACKAGE / POLICY).read_text(encoding="utf-8")
        for fragment in (
            "Reviewed: **October 9, 2026**", "no minimum subagent",
            "strongly prefer delegating them in parallel", "Subagents Off",
            "consumer's allowed choices", "Keep the parent's selected model and effort unchanged",
            "Preserve explicit child profiles and effort ceilings",
            "use supported\ninheritance and disclose that limitation",
            "it gains no model-routing role",
        ):
            # Authority and assignment invariants, not a replacement for the
            # producer's full canonical-projection comparison.
            self.assertIn(fragment, policy)
        rows = [line for line in policy.splitlines()
                if line.startswith("| ") and "`gpt-" in line]
        self.assertEqual(len(rows), 6)
        profiles = ("gpt-6-luna / high", "gpt-6-luna / high", "gpt-6.1-sol / medium",
                    "gpt-6.1-sol / high", "gpt-6.1-sol / xhigh", "gpt-6.1-sol / max")
        for row, profile in zip(rows, profiles, strict=True):
            self.assertIn(f"`{profile}`", row)
        self.assertIn("`gpt-6-astra / max`", rows[-1])

    def test_dated_runtime_scope(self):
        runtime = (PACKAGE / RUNTIME).read_text(encoding="utf-8")
        for fragment in ("October 9, 2026", "Codex CLI 0.160.0",
                         "These source tests were inspected, not executed",
                         "not a `proactive = true` setting", "adoption.md"):
            self.assertIn(fragment, runtime)

    def test_public_references_and_no_private_source_identities(self):
        # Only provider citations already used by this dated package are exported.
        # A public provider revision is allowed as provenance for that public source;
        # unrelated source-object identities are rejected, even outside Markdown.
        provider_revisions = set()
        texts = [(path, path.read_text(encoding="utf-8"))
                 for path in PACKAGE.rglob("*")
                 if path.is_file() and "__pycache__" not in path.parts]
        for path, content in texts:
            url_pattern = r"https?:" + "/" + r"/[^\s)\]\"'<>]+"
            for raw in re.findall(url_pattern, content):
                parsed = urlsplit(raw.rstrip(".,;:"))
                self.assertEqual(parsed.scheme, "https", (path, raw))
                self.assertIn(parsed.hostname, {
                    "learn.chatgpt.com", "developers.openai.com", "github.com",
                }, (path, raw))
                if parsed.hostname == "github.com":
                    self.assertTrue(parsed.path.startswith("/openai/codex/"), (path, raw))
                    revision = re.match(r"/openai/codex/blob/([0-9a-f]{40})/", parsed.path)
                    if revision:
                        provider_revisions.add(revision.group(1))
        self.assertTrue(provider_revisions)
        for path, content in texts:
            for identity in re.findall(r"(?<![0-9a-f])[0-9a-f]{40}(?![0-9a-f])", content):
                self.assertIn(identity, provider_revisions, (path, identity))

    def test_boot_is_conditional_and_small(self):
        boot = (PACKAGE / BOOT).read_text(encoding="utf-8")
        self.assertLess(len(boot.encode("utf-8")), 1600)
        self.assertLess(boot.index("explicitly adopt"), boot.index("[subagent policy]"))
        for fragment in (
            "does not\nadopt", "Subagents On", "no helper quota", "Subagents Off",
            "task and runtime", "parent's profile", "stable throughout an admitted task",
        ):
            self.assertIn(fragment, boot)

    def test_markdown_links_are_portable(self):
        count = 0
        for path in PACKAGE.rglob("*.md"):
            text = path.read_text(encoding="utf-8")
            for target in re.findall(r"\[[^\]]*\]\(([^\s)]+)\)", text):
                parsed = urlsplit(target)
                if parsed.scheme:
                    self.assertEqual(parsed.scheme, "https", (path, target))
                    self.assertTrue(parsed.netloc, (path, target))
                    continue
                resolved = (path.parent / unquote(parsed.path)).resolve()
                self.assertTrue(resolved.is_relative_to(PACKAGE), (path, target))
                self.assertTrue(resolved.is_file(), (path, target))
                count += 1
        self.assertGreaterEqual(count, 10)

    def test_passive_payload_inventory(self):
        allowed = {
            ".gitattributes", "vibe.toml", "README.md", "QUALIFICATION.md", "LICENSE",
            BOOT, POLICY, RUNTIME, "vibevm/vibespecs/guides/adoption.md",
            "tests/check_package.py", "tests/qualify_local.py",
        }
        actual = {
            p.relative_to(PACKAGE).as_posix() for p in PACKAGE.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts
        }
        self.assertEqual(actual, allowed)
        # No lifecycle, executable install contributions, Skill, MCP or client config.
        # The exact manifest and file allowlist bound this check to this candidate.
        self.assertFalse(any(p.endswith((".sh", ".ps1", ".exe")) for p in actual))


if __name__ == "__main__":
    unittest.main(verbosity=2)
