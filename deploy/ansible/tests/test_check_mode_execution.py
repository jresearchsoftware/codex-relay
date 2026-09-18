"""Backend check-mode execution lessons extracted from the consumer workflow."""
import json, os, shutil, subprocess, tempfile, unittest
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[3]
HEAD='a'*40
def linux_ansible_available():
    return os.name != 'nt' and shutil.which('ansible-playbook') is not None
class DeploymentCheckTests(unittest.TestCase):
    @unittest.skipUnless(linux_ansible_available(), "Linux Ansible is required for restore-only check fixtures")
    def test_check_mode_covers_restore_only_runtime_and_reviewer_bind_surfaces(self):
        """Apply-only restore surfaces must contribute to the ordinary check plan."""
        runtime_include = (ROOT / "deploy" / "ansible" / "roles" / "relay_codex_runtime" / "tasks" / "runtime-namespace.yml").as_posix()
        bind_include = (ROOT / "deploy" / "ansible" / "tasks" / "production-reviewer-bind-state.yml").as_posix()
        source_templates = ROOT / "deploy" / "ansible" / "roles" / "relay_runtime" / "templates"

        def run_check(playbook_path):
            environment = os.environ.copy()
            environment.update({"ANSIBLE_NOCOLOR": "1", "ANSIBLE_LOCALHOST_WARNING": "False"})
            return subprocess.run(
                ["ansible-playbook", "-i", "localhost,", "-c", "local", "--check", str(playbook_path)],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )

        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture_root = Path(temporary_directory)

            runtime_home = fixture_root / "codex-home"
            runtime_playbook = fixture_root / "runtime-namespace-check.yml"
            runtime_vars = {
                "relay_codex_home": str(runtime_home),
                "relay_codex_user": "root",
                "relay_codex_group": "root",
            }
            runtime_rendered_vars = "\n".join(
                f"    {name}: {json.dumps(value)}" for name, value in runtime_vars.items()
            )
            runtime_playbook.write_text(
                "---\n"
                "- name: Check the source-controlled Codex namespace reconciliation\n"
                "  hosts: localhost\n"
                "  connection: local\n"
                "  gather_facts: false\n"
                "  vars:\n"
                f"{runtime_rendered_vars}\n"
                "  tasks:\n"
                f"    - ansible.builtin.include_tasks: {json.dumps(runtime_include)}\n"
                "    - name: Prove check-mode did not create the missing namespace\n"
                "      ansible.builtin.stat:\n"
                f"        path: {json.dumps(str(runtime_home / 'tmp'))}\n"
                "      register: runtime_tmp_after_check\n"
                "    - ansible.builtin.assert:\n"
                "        that: not runtime_tmp_after_check.stat.exists\n",
                encoding="utf-8",
            )
            runtime_result = run_check(runtime_playbook)
            runtime_output = runtime_result.stdout + runtime_result.stderr
            self.assertEqual(runtime_result.returncode, 0, runtime_output)
            self.assertRegex(runtime_output, r"changed=[1-9][0-9]*")
            self.assertFalse((runtime_home / "tmp").exists())

            template_root = fixture_root / "roles" / "relay_runtime" / "templates"
            template_root.mkdir(parents=True)
            for source in source_templates.iterdir():
                if source.is_file():
                    shutil.copy2(source, template_root / source.name)

            config_root = fixture_root / "config"
            install_root = fixture_root / "install"
            config_root.mkdir()
            install_root.mkdir()
            config_path = config_root / "reviewer-mcp.json"
            config_path.write_text(
                json.dumps(
                    {
                        "service": {
                            "bind_mode": "nexus_gateway",
                            "bind_address": "10.0.0.4",
                            "bind_network": "nexus",
                            "gateway_validated": True,
                        }
                    }
                ),
                encoding="utf-8",
            )
            config_before = config_path.read_bytes()
            bind_vars = {
                "relay_deployment_profile": "production",
                "relay_production_reviewer_bind_refresh": True,
                "relay_reviewer_bind_mode": "nexus_gateway",
                "relay_reviewer_gateway_validated": True,
                "relay_reviewer_bind_address": "10.0.0.5",
                "relay_reviewer_bind_port": 8787,
                "relay_reviewer_bind_network": "nexus", "relay_docker_network_name": "nexus",
                "relay_reviewer_group": "root",
                "relay_config_root": str(config_root),
                "relay_install_root": str(install_root),
                "relay_reviewer_readiness_path": str(install_root / "relay-reviewer-readiness"),
                "relay_evidence_root": str(fixture_root / "evidence"),
                "relay_github_repository": "example/relay-consumer",
                "relay_release_commit": "a" * 40,
                "relay_release_sha256": "b" * 64,
                "relay_reviewer_exec_start": "/bin/true",
                "relay_github_base_branch": "main",
                "relay_review_check_name": "chatgpt-review",
                "relay_writer_expected_actor": "writer[bot]",
                "relay_reviewer_app_slug": "reviewer",
                "relay_reviewer_app_id": "1",
                "relay_reviewer_app_installation_id": "2",
                "relay_reviewer_expected_actor": "actor",
                "relay_reviewer_service_name": "reviewer-mcp.service",
                "relay_reviewer_activation_marker": str(config_root / "activation"),
                "relay_reviewer_recovery_off_marker": str(config_root / "recovery-off"),
                "relay_production_operation_state_path": str(install_root / "operation-state"),
                "relay_production_operation_lock_path": str(fixture_root / "operation.lock"),
                "relay_runner_credentials_marker": str(fixture_root / "runner-credentials"),
                "relay_runner_registration_marker": str(fixture_root / "runner-registration"),
                "relay_runner_enable_start_path": str(install_root / "runner-enable"),
                "relay_production_operation_stale_disposition_path": str(install_root / "stale-disposition"),
                "relay_production_operation_record_path": str(fixture_root / "operation.json"),
                "relay_production_operation_schema_version": "1",
                "relay_production_operation_stale_phase": "",
                "relay_production_operation_stale_target_head": "c" * 40,
                "relay_production_operation_target_head": "a" * 40,
                "relay_production_operation_superseded_root": str(fixture_root / "superseded"),
                "relay_release_root": str(fixture_root / "releases"),
                "relay_runner_service_name": "relay-runner.service",
                "relay_production_runner_service_name": "relay-runner.service",
                "relay_runner_user": "runner",
                "relay_runner_group": "runner",
            }
            bind_rendered_vars = "\n".join(
                f"    {name}: {json.dumps(value)}" for name, value in bind_vars.items()
            )
            bind_playbook = fixture_root / "bind-state-check.yml"
            bind_playbook.write_text(
                "---\n"
                "- name: Check the source-controlled Reviewer bind refresh\n"
                "  hosts: localhost\n"
                "  connection: local\n"
                "  gather_facts: false\n"
                "  vars:\n"
                f"{bind_rendered_vars}\n"
                "  tasks:\n"
                f"    - ansible.builtin.include_tasks: {json.dumps(bind_include)}\n",
                encoding="utf-8",
            )
            bind_result = run_check(bind_playbook)
            bind_output = bind_result.stdout + bind_result.stderr
            self.assertEqual(bind_result.returncode, 0, bind_output)
            self.assertRegex(bind_output, r"changed=[1-9][0-9]*")
            self.assertEqual(config_path.read_bytes(), config_before)
            self.assertFalse((install_root / "relay-reviewer-readiness").exists())


    @unittest.skipUnless(linux_ansible_available(), "Linux Ansible is required for lifecycle check fixtures")
    def test_check_validation_fixture_emits_proof_only_for_exact_stable_state(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture_root = Path(temporary_directory)
            release_root = fixture_root / "releases"
            install_root = fixture_root / "install"
            release_path = release_root / HEAD
            release_path.mkdir(parents=True)
            install_root.mkdir()
            (install_root / "current").symlink_to(release_path, target_is_directory=True)
            (release_path / "artifact-manifest.json").write_text(
                json.dumps({"schemaVersion": "1.0", "commit": HEAD}),
                encoding="utf-8",
            )
            config_root = fixture_root / "config"
            config_root.mkdir()
            bind_address = "10.0.0.5"
            (config_root / "reviewer-mcp.json").write_text(
                json.dumps(
                    {
                        "service": {
                            "bind_mode": "nexus_gateway",
                            "bind_address": bind_address,
                            "bind_network": "nexus",
                            "gateway_validated": True,
                        }
                    }
                ),
                encoding="utf-8",
            )
            writer_entrypoint = (
                '#!/usr/bin/env bash\n'
                'test "$#" -eq 0\n'
                '/usr/bin/env -i RELAY_WRITER_CLAIM_ROOT=/var/lib/claims \\\n'
                f'  {install_root.as_posix()}/current/reviewed-source/controller/src/privileged-writer-helper.mjs\n'
            )
            writer_path = fixture_root / "writer-helper"
            launcher_path = fixture_root / "codex-launcher"
            writer_path.write_text(writer_entrypoint, encoding="utf-8")
            launcher_path.write_text("#!/usr/bin/env bash\n", encoding="utf-8")

            def regular(mode="0644"):
                return {
                    "exists": True,
                    "isreg": True,
                    "islnk": False,
                    "pw_name": "root",
                    "gr_name": "root",
                    "mode": mode,
                }

            final_paths = [
                {
                    "stat": {
                        "exists": True,
                        "isreg": False,
                        "islnk": True,
                        "lnk_source": release_path.as_posix(),
                        "pw_name": "root",
                    }
                },
                {"stat": regular("0640")},
                {"stat": regular("0750")},
                {"stat": regular("0640")},
                {"stat": regular()},
                {"stat": regular()},
                {"stat": {"exists": False}},
                {"stat": {"exists": False}},
                {"stat": regular("0750")},
                {"stat": regular("0750")},
                {"stat": regular("0755")},
            ]
            services = {
                "results": [
                    {"stdout": "active"},
                    {"stdout": "enabled"},
                    {"stdout": "inactive"},
                    {"stdout": "disabled"},
                ]
            }
            common_vars = {
                "relay_deployment_profile": "production",
                "relay_production_operation_phase": "check",
                "relay_production_operation_target_head": HEAD,
                "relay_production_operation_recovery_required": False,
                "relay_production_recovery_check_classified": False,
                "relay_reviewer_bind_mode": "nexus_gateway",
                "relay_reviewer_gateway_validated": True,
                "relay_reviewer_bind_network": "nexus", "relay_docker_network_name": "nexus",
                "relay_reviewer_bind_address": bind_address,
                "relay_reviewer_bind_port": 8787,
                "relay_release_root": release_root.as_posix(),
                "relay_install_root": install_root.as_posix(),
                "relay_config_root": config_root.as_posix(),
                "relay_production_final_paths": {"results": final_paths},
                "relay_production_final_manifest": {"schemaVersion": "1.0", "commit": HEAD},
                "relay_production_final_services": services,
                "relay_production_final_listener": {"stdout": f"LISTEN {bind_address}:8787"},
                "relay_production_final_writer_entrypoint": writer_entrypoint,
            }

            def run_fixture(recovery=False, manifest_head=HEAD):
                variables = dict(common_vars)
                variables["relay_production_operation_recovery_required"] = recovery
                variables["relay_production_recovery_check_classified"] = recovery
                variables["relay_production_final_manifest"] = {
                    "schemaVersion": "1.0",
                    "commit": manifest_head,
                }
                playbook_path = fixture_root / "check-validation.yml"
                rendered_vars = "\n".join(
                    f"    {name}: {json.dumps(value)}" for name, value in variables.items()
                )
                playbook_path.write_text(
                    "---\n"
                    "- name: Execute the check validation fixture\n"
                    "  hosts: localhost\n"
                    "  connection: local\n"
                    "  gather_facts: false\n"
                    "  vars:\n"
                    f"{rendered_vars}\n"
                    "  tasks:\n"
                    f"    - ansible.builtin.include_tasks: {str(ROOT / 'deploy' / 'ansible' / 'tasks' / 'production-check-final-validation.yml')}\n"
                    "    - ansible.builtin.debug:\n"
                    f"        msg: 'PRODUCTION_CHECK_VALIDATED={HEAD};state=stable-no-op;recovery=none'\n"
                    "      when: relay_production_check_stable | default(false) | bool\n",
                    encoding="utf-8",
                )
                return subprocess.run(
                    [
                        "ansible-playbook",
                        "-i",
                        "localhost,",
                        "-c",
                        "local",
                        "--check",
                        str(playbook_path),
                    ],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                )

            stable = run_fixture()
            self.assertEqual(stable.returncode, 0, stable.stderr or stable.stdout)
            self.assertIn(f"PRODUCTION_CHECK_VALIDATED={HEAD};state=stable-no-op;recovery=none", stable.stdout)

            recovery = run_fixture(recovery=True)
            self.assertEqual(recovery.returncode, 0, recovery.stderr or recovery.stdout)
            self.assertNotIn(f"PRODUCTION_CHECK_VALIDATED={HEAD};state=stable-no-op;recovery=none", recovery.stdout)

            wrong_head = run_fixture(manifest_head="b" * 40)
            self.assertEqual(wrong_head.returncode, 0, wrong_head.stderr or wrong_head.stdout)
            self.assertNotIn(f"PRODUCTION_CHECK_VALIDATED={HEAD};state=stable-no-op;recovery=none", wrong_head.stdout)
