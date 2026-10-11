"""Source-only qualification of the separated, rendered manual Writer boundary."""
import json
import os
from pathlib import Path
import subprocess
import sys

from jinja2 import Environment, StrictUndefined, UndefinedError, TemplateAssertionError
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
TEMPLATES = ROOT / "roles/relay_controller/templates"
ENV = Environment(undefined=StrictUndefined)
ENV.filters["bool"] = lambda value: value is True or str(value).lower() in ("true", "1", "yes")
ENV.filters["to_json"] = json.dumps


def context(namespace):
    values = yaml.safe_load((ROOT / "group_vars/all.yml").read_text())
    values.update(relay_namespace=namespace, relay_install_root=f"/opt/{namespace}",
                  relay_config_root=f"/etc/{namespace}", relay_state_root=f"/var/lib/{namespace}",
                  relay_log_root=f"/var/log/{namespace}", relay_runtime_root=f"/run/{namespace}",
                  relay_reviewer_user=f"{namespace}-reviewer", relay_reviewer_group=f"{namespace}-reviewer",
                  relay_reviewer_proxy_group="www-data", relay_deployment_profile="production")
    for _ in range(12):
        for key, value in values.items():
            if isinstance(value, str) and "{{" in value:
                try:
                    values[key] = ENV.from_string(value).render(values)
                except (UndefinedError, TemplateAssertionError):
                    pass
    return values


def render(name, values):
    return ENV.from_string((TEMPLATES / name).read_text()).render(values)


def sections(text):
    result = {}; section = None
    for line in text.splitlines():
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]; result[section] = {}
        elif section and "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1); result[section][key] = value
    return result


@pytest.mark.parametrize("namespace", ["codex-relay", "second-relay"])
def test_rendered_socket_uses_the_matching_factory_service_and_reviewer_only_group(namespace):
    values = context(namespace)
    socket = sections(render("relay-manual-outcome.socket.j2", values))
    service = sections(render("relay-manual-outcome@.service.j2", values))
    assert socket["Socket"] == {"ListenStream": f"/run/{namespace}-manual-outcome.sock",
                                 "SocketUser": "root", "SocketGroup": f"{namespace}-reviewer",
                                 "SocketMode": "0660", "Accept": "yes", "MaxConnections": "4",
                                 "RemoveOnStop": "yes"}
    assert service["Service"]["User"] == service["Service"]["Group"] == "root"
    # The lifecycle detector must also find retained children after MainPID exits.
    # systemd's default per-template slice would break its qualified cgroup path.
    assert service["Service"]["Slice"] == "system.slice"
    assert service["Service"]["ExecStart"] == f"/opt/{namespace}/relay-manual-outcome-writer"
    assert service["Service"]["NoNewPrivileges"] == "true"
    assert service["Service"]["StandardInput"] == service["Service"]["StandardOutput"] == "socket"
    assert service["Service"]["StandardError"] == "null"
    assert service["Service"]["UMask"] == "0077"
    assert service["Service"]["RuntimeMaxSec"] == service["Service"]["TimeoutStartSec"] == "60"
    assert service["Service"]["ReadWritePaths"] == f"/var/lib/{namespace}/writer-claims"
    tasks = yaml.safe_load((ROOT / "roles/relay_controller/tasks/writer-entrypoint.yml").read_text())
    units = next(task for task in tasks if "relay-manual-outcome.socket" in task.get("loop", []))
    installed = [ENV.from_string(units["ansible.builtin.template"]["dest"]).render(values, item=item)
                 for item in units["loop"]]
    assert installed == [f"/etc/systemd/system/{namespace}-relay-manual-outcome.socket",
                         f"/etc/systemd/system/{namespace}-relay-manual-outcome@.service"]
    # With Accept=yes, these matching names select the per-connection service.
    assert installed[0].removesuffix(".socket") + "@.service" == installed[1]


def test_installed_clients_cannot_select_credentials_command_or_operation_and_preserve_nnp():
    values = context("second-relay")
    client = render("relay-manual-outcome.j2", values)
    writer = render("relay-manual-outcome-writer.j2", values)
    for wrapper in [client, writer]:
        assert 'test "$#" -eq 0 || exit 40' in wrapper
        assert "/usr/bin/env -i" in wrapper
        assert "PATH=/usr/bin:/bin" in wrapper
        assert "/usr/bin/node '/opt/second-relay/current/reviewed-source/controller/src/manual-outcome-" in wrapper
        assert "sudo" not in wrapper
    assert "RELAY_MANUAL_OUTCOME_SOCKET='/run/second-relay-manual-outcome.sock'" in client
    assert "RELAY_CONSUMER_CONFIG" not in client and "WRITER_CREDENTIAL" not in client
    assert "RELAY_CONSUMER_CONFIG='/etc/second-relay/consumer.json'" in writer
    assert "/usr/bin/flock -w 5 '/var/lib/second-relay/writer-claims/publication-v2.lock'" in writer
    reviewer = ENV.from_string((ROOT / "roles/relay_runtime/templates/reviewer-mcp.service.j2").read_text()).render(values)
    assert f"User={values['relay_reviewer_user']}" in reviewer
    assert "NoNewPrivileges=true" in reviewer
    assert f"SupplementaryGroups={values['relay_reviewer_group']}" in reviewer
    assert "writer-claims" not in reviewer and "writer-credentials" not in reviewer


def test_installation_protects_wrapper_ownership_and_has_no_generic_sudo_grant():
    tasks = yaml.safe_load((ROOT / "roles/relay_controller/tasks/writer-entrypoint.yml").read_text())
    for name, expected in [("relay-manual-outcome.j2", {"owner": "root", "group": "{{ relay_reviewer_group }}", "mode": "0750"}),
                           ("relay-manual-outcome-writer.j2", {"owner": "root", "group": "root", "mode": "0700"})]:
        template = next(task["ansible.builtin.template"] for task in tasks
                        if task.get("ansible.builtin.template", {}).get("src") == name)
        assert {key: template[key] for key in expected} == expected
    for path in ROOT.rglob("*.sudoers.j2"):
        assert "relay-manual-outcome" not in path.read_text()


@pytest.mark.skipif(os.name == "nt", reason="Native Linux shell boundary")
def test_rendered_fixed_wrappers_reject_arguments_before_starting_any_service(tmp_path):
    for name in ["relay-manual-outcome.j2", "relay-manual-outcome-writer.j2"]:
        wrapper = tmp_path / name
        wrapper.write_text(render(name, context("second-relay")))
        assert subprocess.run(["/bin/sh", "-n", str(wrapper)], capture_output=True).returncode == 0
        result = subprocess.run(["/bin/sh", str(wrapper), "operation=arbitrary"], input=b"private-input", capture_output=True)
        assert result.returncode == 40 and result.stdout == result.stderr == b""


@pytest.mark.skipif(os.name == "nt", reason="Native Linux lifecycle inventory")
@pytest.mark.parametrize("isolated", [False, True])
def test_supported_reinstall_inventory_includes_both_manual_capability_units(isolated):
    sys.path.insert(0, str(REPO / "deploy"))
    import clean_reinstall
    config = json.loads((REPO / "deploy/example.json").read_text())
    if isolated:
        config["environment"]["instance"] = {"reviewerPort": 18787, "publicationEnabled": False}
    namespace = config["environment"]["namespace"]
    units = clean_reinstall.unit_names(config)
    assert f"{namespace}-relay-manual-outcome.socket" in units
    assert f"{namespace}-relay-manual-outcome@.service" in units
