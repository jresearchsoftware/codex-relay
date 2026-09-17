"""Deterministic checks for the source-controlled qualification TLS gate."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class TlsPreparationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.group_vars = (ROOT / "group_vars" / "all.yml").read_text(encoding="utf-8")
        cls.playbook = (ROOT / "relay-tls-preparation.yml").read_text(encoding="utf-8")
        cls.tasks = (ROOT / "roles" / "relay_tls" / "tasks" / "main.yml").read_text(encoding="utf-8")

    def test_explicit_playbook_and_phase_gate_exist(self):
        self.assertIn("role: relay_preflight", self.playbook)
        self.assertIn("role: relay_apt_metadata", self.playbook)
        self.assertIn("role: relay_tls", self.playbook)
        self.assertIn("relay_tls_phase in ['prerequisites', 'dry_run', 'issue']", self.tasks)
        self.assertIn("TLS_PREPARATION_PREREQUISITES_READY", self.tasks)
        self.assertIn("TLS_ACME_OWNER_EMAIL_REQUIRED", self.tasks)


    def test_official_ca_identity_and_bundle_contract(self):
        for marker in (
            "https://developers.openai.com/plugins/mtls/openai-root-ca.pem",
            "https://developers.openai.com/plugins/mtls/openai-connectors-mtls-ca.pem",
            "49:3D:9A:1E:DC:48:D5:58:F5:A2:87:64:B2:06:05:20:5A:50:E1:DF:48:40:23:1E:34:2F:2E:0E:8C:DD:5B:E9",
            "DA:3D:8E:2E:32:EE:49:81:EA:11:52:C1:45:6F:86:6C:86:3D:BD:E2:FB:F4:F8:EB:A8:85:0D:F7:4B:65:68:16",
            "openssl verify -CAfile",
            "TLS_OPENAI_CA_BUNDLE_UPDATED",
            "TLS_OPENAI_CA_BUNDLE_UNCHANGED",
            "TLS_OPENAI_CA_BUNDLE_UNSAFE_PERMISSIONS",
            "fresh root-owned temporary directory",
            "remote_src: true",
        ):
            self.assertIn(marker, self.tasks + self.group_vars)
        self.assertIn("group: '{{ relay_reviewer_group }}'", self.tasks)
        self.assertIn("install -o root -g '{{ relay_reviewer_group }}' -m 0640", self.tasks)
        self.assertIn("root:' ~ relay_reviewer_group ~ ':640:regular file", self.tasks)

    def test_no_implicit_nginx_or_acme_issuance(self):
        self.assertIn("relay_tls_phase: prerequisites", self.group_vars)
        self.assertIn("relay_nginx_manage: false", self.group_vars)
        self.assertIn("TLS_PREPARATION_PREREQUISITES_READY", self.tasks)
        self.assertIn("relay_tls_phase == 'dry_run'", self.tasks)
        self.assertIn("relay_tls_phase == 'issue'", self.tasks)
        self.assertIn("TLS_ACME_EXACT_HEAD_REQUIRED", self.tasks)
        self.assertIn("relay_tls_qualified_manifest_file", self.tasks)
        self.assertIn("TLS_ACME_DRY_RUN_BINDING_INVALID_OR_STALE", self.tasks)
        self.assertIn("relay_nginx_server_certificate_file", self.tasks)
        self.assertIn("relay_nginx_server_private_key_file", self.tasks)
        self.assertIn("TLS_CERTIFICATE_KEY_VALIDATED", self.tasks)
        self.assertNotIn("ansible.builtin.systemd", self.tasks)
        self.assertNotIn("service:", self.tasks)

    def test_acme_and_qualification_preconditions_are_fail_closed(self):
        for marker in (
            "getent ahostsv4",
            "relay_tls_acme_admitted_ip",
            "ss -ltnpH",
            "TLS_ACME_PUBLIC_LISTENER_NOT_FREE",
            "TLS_ACME_PRECONDITIONS_RECHECK_PASS",
            "--standalone",
            "--dry-run",
            "TLS_ACME_DRY_RUN_BINDING_INVALID_OR_STALE",
            "TLS_PREPARATION_READY",
        ):
            self.assertIn(marker, self.tasks)
        self.assertIn("relay_tls_acme_hostname: relay.example.invalid", self.group_vars)
        self.assertIn("relay_tls_acme_admitted_ip: 192.0.2.10", self.group_vars)


if __name__ == "__main__":
    unittest.main()
