"""Deterministic non-secret checks for the qualification two-PEM credential gate."""

from pathlib import Path
import unittest


ANSIBLE_ROOT = Path(__file__).resolve().parents[1]


def text(relative_path):
    return (ANSIBLE_ROOT / relative_path).read_text(encoding="utf-8")


class CredentialProvisioningTests(unittest.TestCase):
    def test_non_secret_reviewer_and_writer_defaults_are_complete(self):
        group_vars = text("group_vars/all.yml")
        reviewer = text("roles/relay_runtime/templates/relay-reviewer-github-app.env.j2")
        writer = text("roles/relay_runtime/templates/relay-writer-github-app.env.j2")
        for marker in (
            "relay_reviewer_app_slug: example-reviewer",
            "relay_reviewer_app_id: '1001'",
            "relay_reviewer_app_installation_id: '2001'",
            "relay_reviewer_expected_actor: example-reviewer[bot]",
            "relay_writer_app_slug: example-writer",
            "relay_writer_app_id: '1002'",
            "relay_writer_app_installation_id: '2002'",
            "relay_writer_expected_actor: example-writer[bot]",
            "relay_github_repository: example/relay-consumer",
        ):
            self.assertIn(marker, group_vars)
        self.assertIn("GITHUB_APP_ID={{ relay_reviewer_app_id }}", reviewer)
        self.assertIn("GITHUB_APP_INSTALLATION_ID={{ relay_reviewer_app_installation_id }}", reviewer)
        self.assertIn("GITHUB_APP_ID={{ relay_writer_app_id }}", writer)
        self.assertIn("GITHUB_APP_INSTALLATION_ID={{ relay_writer_app_installation_id }}", writer)
        helper = text("roles/relay_runtime/templates/relay-credential-provision.j2")
        self.assertIn('grep -Fx "$key_var=$key_file"', helper)
        self.assertIn('grep -Fx "$app_id_var=$app_id"', helper)
        self.assertIn('grep -Fx "$installation_id_var=$installation_id"', helper)
        self.assertNotIn("wc -l", helper)

    def test_missing_or_non_pem_private_keys_fail_closed(self):
        helper = text("roles/relay_runtime/templates/relay-credential-provision.j2")
        self.assertIn("test ! -L \"$path\" && test -f \"$path\"", helper)
        self.assertIn("stat -c '%U:%G:%a'", helper)
        self.assertNotIn("$mode:regular file", helper)
        self.assertIn("validate_pem_file", helper)
        self.assertIn("test -s \"$key_file\" || exit 47", helper)
        self.assertIn("BEGIN .*PRIVATE KEY", helper)
        self.assertIn("END .*PRIVATE KEY", helper)

    def test_reviewer_and_writer_file_modes_remain_separate(self):
        runtime = text("roles/relay_runtime/tasks/main.yml")
        helper = text("roles/relay_runtime/templates/relay-credential-provision.j2")
        self.assertIn("{path: '{{ relay_config_root }}', owner: root, group: root, mode: '0751'}", runtime)
        self.assertIn("{path: '{{ relay_config_root }}/certs', group: '{{ relay_reviewer_group }}', mode: '0750'}", runtime)
        self.assertIn("path: '{{ relay_tls_client_ca_file }}'", runtime)
        self.assertIn("Enforce Reviewer-readable client CA bundle permissions", runtime)
        self.assertIn("{path: '{{ relay_state_root }}', owner: root, mode: '0755'}", runtime)
        self.assertIn("{path: '{{ relay_evidence_root }}', mode: '0751'}", runtime)
        self.assertIn("dest: '{{ relay_config_root }}/reviewer-mcp.json'", runtime)
        self.assertIn("dest: '{{ relay_config_root }}/relay.env'", runtime)
        self.assertIn("{path: '{{ relay_log_root }}', owner: '{{ relay_user }}', group: '{{ relay_reviewer_group }}', mode: '0770'}", runtime)
        self.assertIn("{path: '{{ relay_runtime_root }}', owner: root, group: '{{ relay_reviewer_group }}', mode: '0770'}", runtime)
        self.assertIn("group: '{{ relay_reviewer_group }}'", runtime)
        self.assertIn("mode: '0640'", runtime)
        self.assertIn("group: root", runtime)
        self.assertIn("mode: '0600'", runtime)
        self.assertIn("Provide only the two temporary private-key PEM files", helper)
        self.assertNotIn("GITHUB_APP_ID=", helper)
        self.assertNotIn("GITHUB_APP_INSTALLATION_ID=", helper)
