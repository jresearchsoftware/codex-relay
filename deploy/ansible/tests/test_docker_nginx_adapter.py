"""Deterministic safety checks for the pinned Docker-nginx adapter."""

import unittest


MARKER = "# managed-by: codex-relay-docker-nginx"
ALLOWED_PROJECTION_FILES = {"fullchain.pem", "privkey.pem", "openai-client-ca.pem"}


def fragment_is_relay_owned(content):
    return content.startswith(MARKER + "\n")


def projection_entries_are_safe(entries):
    return all(entry in ALLOWED_PROJECTION_FILES for entry in entries)


def docker_control_plane_is_admitted(inspect, expected_image="nginx:latest", ownership_root="/srv/nexus"):
    mounts = inspect.get("Mounts", [])
    return (
        inspect.get("Name") == "/nginx"
        and inspect.get("Config", {}).get("Image") == expected_image
        and inspect.get("State", {}).get("Running") is True
        and any(m.get("Source") == f"{ownership_root}/nginx-conf" and m.get("Destination") == "/etc/nginx/conf.d" for m in mounts)
        and any(m.get("Source") == f"{ownership_root}/letsencrypt" and m.get("Destination") == "/etc/letsencrypt" for m in mounts)
    )


def virtual_hosts_are_distinct(relay_host, nexus_host, nexus_aliases):
    return relay_host != nexus_host and relay_host not in set(nexus_aliases)


def foreign_config_claims_host(server_name_lines, relay_host):
    return any(
        relay_host in {token.rstrip(";") for token in line.split()[1:]}
        for line in server_name_lines
    )


class DockerNginxAdapterTests(unittest.TestCase):
    def test_only_marked_fragment_is_relay_owned(self):
        self.assertTrue(fragment_is_relay_owned(MARKER + "\nserver {}"))
        self.assertFalse(fragment_is_relay_owned("# managed-by: foreign\nserver {}"))

    def test_projection_namespace_rejects_foreign_entries(self):
        self.assertTrue(projection_entries_are_safe(sorted(ALLOWED_PROJECTION_FILES)))
        self.assertFalse(projection_entries_are_safe(["fullchain.pem", "foreign.pem"]))

    def test_pinned_container_identity_and_mounts_are_required(self):
        admitted = {
            "Name": "/nginx",
            "Config": {"Image": "nginx:latest"},
            "State": {"Running": True},
            "Mounts": [
                {"Source": "/srv/nexus/nginx-conf", "Destination": "/etc/nginx/conf.d"},
                {"Source": "/srv/nexus/letsencrypt", "Destination": "/etc/letsencrypt"},
            ],
        }
        self.assertTrue(docker_control_plane_is_admitted(admitted))
        admitted["Mounts"][0]["Source"] = "/srv/shared/nginx-conf"
        admitted["Mounts"][1]["Source"] = "/srv/shared/letsencrypt"
        self.assertTrue(docker_control_plane_is_admitted(admitted, ownership_root="/srv/shared"))
        admitted["Mounts"][1]["Source"] = "/srv/nexus/letsencrypt"
        self.assertFalse(docker_control_plane_is_admitted(admitted, ownership_root="/srv/shared"))
        admitted["Name"] = "/foreign-nginx"
        self.assertFalse(docker_control_plane_is_admitted(admitted))

    def test_adapter_does_not_admit_host_nginx_as_reload_control_plane(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        role = (root / "roles" / "relay_docker_nginx" / "tasks" / "main.yml").read_text(encoding="utf-8")
        handler = (root / "roles" / "relay_docker_nginx" / "handlers" / "main.yml").read_text(encoding="utf-8")
        self.assertNotIn("ansible.builtin.systemd", handler)
        self.assertIn("docker", role + handler)
        self.assertIn("docker exec", role + handler)

    def test_relay_and_nexus_virtual_hosts_are_distinct(self):
        self.assertTrue(virtual_hosts_are_distinct(
            "relay.example.invalid", "other.example.invalid", []
        ))
        self.assertFalse(virtual_hosts_are_distinct(
            "relay.example.invalid", "relay.example.invalid", []
        ))
        self.assertFalse(virtual_hosts_are_distinct(
            "relay.example.invalid", "other.example.invalid",
            ["relay.example.invalid"]
        ))

    def test_foreign_relay_hostname_claim_blocks_activation(self):
        self.assertFalse(foreign_config_claims_host(
            ["server_name other.example.invalid;"],
            "relay.example.invalid"
        ))
        self.assertTrue(foreign_config_claims_host(
            ["server_name other.example.invalid relay.example.invalid;"],
            "relay.example.invalid"
        ))

    def test_conflicting_server_name_warning_is_explicitly_rejected(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        role = (root / "roles" / "relay_docker_nginx" / "tasks" / "main.yml").read_text(encoding="utf-8")
        self.assertIn("conflicting server name", role)
        self.assertIn("exit 23", role)

    def test_prospective_mode_allows_stopped_pinned_container_identity(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        role = (root / "roles" / "relay_docker_nginx" / "tasks" / "main.yml").read_text(encoding="utf-8")
        self.assertIn("relay_docker_nginx_validation_mode == 'prospective'", role)
        self.assertIn("DOCKER_NGINX_PROSPECTIVE_CHECK_MODE_PLAN", role)
        self.assertIn("check_mode: false", role)
        self.assertIn("      - --network", role)
        self.assertIn("      - nexus", role)
        self.assertIn("relay_docker_nginx_dhparam_file", role)
        self.assertIn("/etc/ssl/certs/dhparam-2048.pem", role)
        self.assertIn("ansible.builtin.command", role)
        self.assertIn("failed_when", role)

    def test_parameterized_root_is_source_controlled_and_mixed_roots_fail_closed(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        group_vars = (root / "group_vars" / "all.yml").read_text(encoding="utf-8")
        role = (root / "roles" / "relay_docker_nginx" / "tasks" / "main.yml").read_text(encoding="utf-8")
        fragment = (root / "roles" / "relay_docker_nginx" / "templates" / "codex-relay-docker.conf.j2").read_text(encoding="utf-8")
        self.assertIn("relay_nexus_ownership_root: /srv/nexus", group_vars)
        self.assertIn("relay_docker_nginx_conf_root: '{{ relay_nexus_ownership_root }}/nginx-conf'", group_vars)
        self.assertIn("NEXUS_OWNERSHIP_ROOT_CONTRACT_INVALID_OR_MIXED", role)
        self.assertIn("NEXUS_OWNERSHIP_ROOT_SYSTEMD_COMPOSE_MISMATCH", role)
        self.assertIn("relay_docker_nginx_letsencrypt_root", fragment)
        self.assertNotIn("/srv/nexus/letsencrypt", fragment)


if __name__ == "__main__":
    unittest.main()
