"""Focused regressions for the production fixed-Writer release binding."""

from pathlib import Path
import re
import json
import os
import shutil
import shlex
import subprocess
import tempfile
import textwrap
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
INSTALL_ROOT = "/opt/codex-relay"
HELPER_SUFFIX = "/reviewed-source/controller/src/privileged-writer-helper.mjs"
WRITER_BINDING_VALIDATION = ROOT / "tasks" / "production-writer-binding-validation.yml"


def localhost_ansible_available():
    return os.name != "nt" and shutil.which("ansible-playbook") is not None


def render_writer_wrapper(template):
    values = {
        "relay_consumer_config_path": "/etc/codex-relay/consumer.json",
        "relay_writer_credential_env_file": "/etc/codex-relay/writer-credentials/github-app.env",
        "relay_writer_credential_key_file": "/etc/codex-relay/writer-credentials/github-app-private-key.pem",
        "relay_writer_claim_root": "/var/lib/codex-relay/writer-claims",
        "relay_writer_helper_release_path": f"{INSTALL_ROOT}/current{HELPER_SUFFIX}",
    }
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{{ " + key + " }}", value)
    return rendered


def wrapper_target(wrapper):
    match = re.search(r"/usr/bin/node '([^']+)'", wrapper)
    if match is None:
        raise AssertionError("fixed Writer wrapper has no node target")
    return match.group(1)


def resolve_current_target(wrapper, current_release):
    target = wrapper_target(wrapper)
    prefix = INSTALL_ROOT + "/current"
    if not target.startswith(prefix):
        return target
    return current_release + target[len(prefix) :]


def _writer_binding_facts(phase, writer_entrypoint):
    regular_stat = {"exists": True, "isreg": True, "islnk": False, "pw_name": "root", "gr_name": "root", "mode": "0750"}
    helper_stat = {"exists": True, "isreg": True, "islnk": False, "pw_name": "root", "gr_name": "relay", "mode": "0644"}
    return {
        "relay_deployment_profile": "production",
        "relay_production_operation_phase": phase,
        "relay_install_root": INSTALL_ROOT,
        "relay_release_root": f"{INSTALL_ROOT}/releases",
        "relay_production_final_paths": {"results": [{"stat": {}} for _ in range(8)] + [{"stat": regular_stat}, {"stat": helper_stat}]},
        "relay_production_final_writer_entrypoint": writer_entrypoint,
    }


class ProductionWriterReleaseBindingTests(unittest.TestCase):
    def setUp(self):
        self.site = (ROOT / "site.yml").read_text(encoding="utf-8")
        self.final_validation = (ROOT / "tasks" / "production-final-validation.yml").read_text(encoding="utf-8")
        self.writer_binding_validation = WRITER_BINDING_VALIDATION.read_text(encoding="utf-8")
        self.template = (ROOT / "roles" / "relay_controller" / "templates" / "relay-writer-controller.j2").read_text(encoding="utf-8")
        self.writer_tasks = (ROOT / "roles" / "relay_controller" / "tasks" / "writer-entrypoint.yml").read_text(encoding="utf-8")
        self.controller_tasks = (ROOT / "roles" / "relay_controller" / "tasks" / "main.yml").read_text(encoding="utf-8")
        self.sudoers = (ROOT / "roles" / "relay_controller" / "templates" / "relay-writer-controller.sudoers.j2").read_text(encoding="utf-8")
        self.group_vars = (ROOT / "group_vars" / "all.yml").read_text(encoding="utf-8")

    def test_current_bound_wrapper_follows_restore_only_release_transition(self):
        release_n = f"{INSTALL_ROOT}/releases/{'a' * 40}"
        release_n_plus_one = f"{INSTALL_ROOT}/releases/{'b' * 40}"
        wrapper = render_writer_wrapper(self.template)

        self.assertNotIn(release_n, wrapper)
        self.assertNotIn(release_n_plus_one, wrapper)
        self.assertEqual(resolve_current_target(wrapper, release_n), release_n + HELPER_SUFFIX)
        self.assertEqual(resolve_current_target(wrapper, release_n_plus_one), release_n_plus_one + HELPER_SUFFIX)
        self.assertIn("relay_writer_helper_release_path: '{{ relay_install_root }}/current" + HELPER_SUFFIX + "'", self.group_vars)

    def test_ordinary_apply_reconciles_the_full_writer_and_diagnostics_role(self):
        role = next(entry for entry in yaml.safe_load(self.site)[1]['roles']
                    if entry['role'] == 'relay_controller')
        self.assertNotIn('when', role)
        self.assertIn('include_tasks: writer-entrypoint.yml', self.controller_tasks)
        self.assertIn('relay_diagnostics_root', self.controller_tasks)
        self.assertIn('state: absent', self.controller_tasks)
        self.assertNotIn('remediation-state.yml', self.writer_tasks)

    def test_publication_lock_is_os_owned_and_waits_for_short_lifecycle_snapshots(self):
        self.assertIn('/usr/bin/flock -w 5', self.template)
        self.assertIn('publication-v2.lock', self.template)
        self.assertNotIn('remediation-state.json', self.writer_tasks)

    def test_lifecycle_admission_helper_is_root_only_credential_free_and_shares_writer_lock(self):
        template = (ROOT / 'roles/relay_controller/templates/relay-admission.j2').read_text(encoding='utf-8')
        self.assertIn('publication-v2.lock', template)
        self.assertIn('/usr/bin/env -i', template)
        self.assertIn('current/reviewed-source/controller/src/admission-cli.mjs', template)
        self.assertNotIn('CREDENTIAL', template)
        self.assertNotIn('relay-admission', self.sudoers)
        tasks = yaml.safe_load(self.writer_tasks)
        install = next(task['ansible.builtin.template'] for task in tasks
                       if task.get('ansible.builtin.template', {}).get('src') == 'relay-admission.j2')
        self.assertEqual((install['owner'], install['group'], install['mode']), ('root', 'root', '0750'))
        initialize = next(task for task in tasks if task.get('ansible.builtin.command', {}).get('argv', [])[-1:] == ['initialize'])
        self.assertIn('not ansible_check_mode | bool', initialize['when'])
        self.assertIn('not relay_upgrade_lifecycle_managed | default(false) | bool', initialize['when'])
        preserve = next(task for task in tasks if task.get('register') == 'relay_admission_preserved')
        self.assertEqual(preserve['ansible.builtin.command']['argv'][-1], 'status')
        self.assertIn('relay_upgrade_lifecycle_managed | default(false) | bool', preserve['when'])

    @unittest.skipUnless(localhost_ansible_available(), 'native Ansible is required for admission preservation regression')
    def test_managed_install_requires_existing_gate_without_reinitializing_it(self):
        tasks = [task for task in yaml.safe_load(self.writer_tasks)
                 if task.get('register') in ['relay_admission_initialized', 'relay_admission_preserved']]
        with tempfile.TemporaryDirectory(prefix='relay-gate-install-') as temporary:
            root = Path(temporary)
            gate = root / 'admission-v1.json'
            calls = root / 'calls'
            helper = root / 'relay-admission'
            helper.write_text('#!/bin/sh\nset -eu\n'
                + "printf '%s\\n' \"$1\" >> " + shlex.quote(str(calls)) + '\n'
                + 'case "$1" in\n'
                + 'status) test -f ' + shlex.quote(str(gate)) + ' ;;\n'
                + 'initialize) test -f ' + shlex.quote(str(gate)) + ' || printf open > '
                + shlex.quote(str(gate)) + ' ;;\n'
                + '*) exit 41 ;;\nesac\n', encoding='utf-8')
            helper.chmod(0o700)
            playbook = root / 'playbook.yml'
            playbook.write_text(yaml.safe_dump([{'hosts': 'localhost', 'gather_facts': False,
                'vars': {'relay_install_root': str(root), 'relay_upgrade_lifecycle_managed': True},
                'tasks': tasks}], sort_keys=False), encoding='utf-8')
            command = ['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(playbook)]
            environment = {**os.environ, 'ANSIBLE_REMOTE_TEMP': str(root / 'ansible-remote'),
                           'ANSIBLE_LOCAL_TEMP': str(root / 'ansible-local')}
            missing = subprocess.run(command, env=environment, text=True, capture_output=True, timeout=30)
            self.assertNotEqual(missing.returncode, 0, missing.stdout + missing.stderr)
            self.assertFalse(gate.exists())
            self.assertTrue(calls.exists(), missing.stdout + missing.stderr)
            self.assertEqual(calls.read_text(encoding='utf-8'), 'status\n')
            calls.unlink()
            gate.write_text('retained-applying-state', encoding='utf-8')
            existing = subprocess.run(command, env=environment, text=True, capture_output=True, timeout=30)
            self.assertEqual(existing.returncode, 0, existing.stdout + existing.stderr)
            self.assertEqual(gate.read_text(encoding='utf-8'), 'retained-applying-state')
            self.assertEqual(calls.read_text(encoding='utf-8'), 'status\n')

    def test_final_validation_rejects_concrete_old_release_binding(self):
        self.assertIn("production-writer-binding-validation.yml", self.final_validation)
        self.assertIn("relay_production_final_writer_binding_valid", self.writer_binding_validation)
        self.assertIn("relay_install_root ~ '/current" + HELPER_SUFFIX, self.writer_binding_validation)
        self.assertIn("relay_release_root | regex_escape", self.writer_binding_validation)
        self.assertIn("relay_production_final_paths.results[8]", self.writer_binding_validation)
        self.assertIn("relay_production_final_paths.results[9]", self.writer_binding_validation)
        self.assertIn("current/reviewed-source/controller/src/privileged-writer-helper.mjs", self.site)

    def test_post_check_uses_shared_writer_validation_without_check_mode_blocker(self):
        plays = yaml.safe_load(self.site)
        namespaced_play = next(
            play for play in plays if play.get("name") == "Install namespaced relay prerequisites and runtime state"
        )
        validation_task = next(
            task
            for task in namespaced_play["post_tasks"]
            if isinstance(task, dict)
            and task.get("ansible.builtin.include_tasks") == "tasks/production-writer-binding-validation.yml"
        )
        self.assertEqual(
            validation_task["when"],
            [
                "relay_deployment_profile == 'production'",
                "relay_production_operation_phase | default('') == 'post-check'",
            ],
        )
        self.assertIn("relay_production_writer_binding_failure_message", validation_task["vars"])
        self.assertIn("relay_production_operation_phase | default('') in ['apply', 'post-check']", self.writer_binding_validation)
        self.assertIn("relay_production_operation_phase | default('') == 'post-check'", self.writer_binding_validation)
        self.assertIn("not ansible_check_mode | bool", self.writer_binding_validation)

    @unittest.skipUnless(localhost_ansible_available(), "native Ansible is required for the post-check binding regression")
    def test_post_check_rejects_stale_wrapper_and_accepts_current_bound_wrapper(self):
        stale_wrapper = (
            "#!/bin/sh\n"
            "set -eu\n"
            'test "$#" -eq 0 || exit 40\n'
            "/usr/bin/env -i PATH=/usr/bin:/bin\n"
            "RELAY_WRITER_CLAIM_ROOT=/var/lib/codex-relay/writer-claims\n"
            f"/usr/bin/node '{INSTALL_ROOT}/releases/{'a' * 40}{HELPER_SUFFIX}'\n"
        )
        current_wrapper = render_writer_wrapper(self.template)

        self._run_writer_binding_validation("post-check", stale_wrapper, expect_success=False, check_mode=True)
        self._run_writer_binding_validation("post-check", current_wrapper, expect_success=True, check_mode=True)
        self._run_writer_binding_validation("check", stale_wrapper, expect_success=True, check_mode=True)

    @unittest.skipUnless(localhost_ansible_available(), "native Ansible is required for the apply binding regression")
    def test_apply_keeps_strict_writer_binding_validation(self):
        stale_wrapper = (
            "/usr/bin/node "
            f"'{INSTALL_ROOT}/releases/{'a' * 40}{HELPER_SUFFIX}'\n"
        )
        self._run_writer_binding_validation("apply", stale_wrapper, expect_success=False, check_mode=False)

    def _run_writer_binding_validation(self, phase, writer_entrypoint, *, expect_success, check_mode):
        facts = _writer_binding_facts(phase, writer_entrypoint)
        with tempfile.TemporaryDirectory() as temporary_directory:
            playbook_path = Path(temporary_directory) / "writer-binding-validation.yml"
            include_path = WRITER_BINDING_VALIDATION.as_posix()
            variables = textwrap.indent(json.dumps(facts, indent=2), "    ")
            playbook_path.write_text(
                "---\n"
                "- name: Execute the source-controlled Writer binding validation\n"
                "  hosts: localhost\n"
                "  connection: local\n"
                "  gather_facts: false\n"
                "  vars:\n"
                f"{variables}\n"
                "  tasks:\n"
                f"    - ansible.builtin.include_tasks: '{include_path}'\n"
                "      vars:\n"
                "        relay_production_writer_binding_failure_message: PRODUCTION_WRITER_RUNTIME_BINDING_INVALID\n",
                encoding="utf-8",
            )
            command = ["ansible-playbook", "-i", "localhost,", "-c", "local", str(playbook_path)]
            if check_mode:
                command.append("--check")
            result = subprocess.run(
                command,
                cwd=ROOT,
                env={**os.environ, "ANSIBLE_NOCOLOR": "1", "ANSIBLE_LOCALHOST_WARNING": "False"},
                capture_output=True,
                text=True,
                check=False,
            )
            if expect_success:
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            else:
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("PRODUCTION_WRITER_RUNTIME_BINDING_INVALID", result.stdout + result.stderr)

    def test_writer_privilege_path_and_environment_restrictions_remain_fixed(self):
        for marker in (
            'test "$#" -eq 0',
            "/usr/bin/env -i",
            "PATH=/usr/bin:/bin",
            "HOME=/root",
            "RELAY_WRITER_CREDENTIAL_ENV=",
            "RELAY_WRITER_CREDENTIAL_KEY_FILE=",
            "RELAY_WRITER_CLAIM_ROOT=",
            "/usr/bin/node",
        ):
            self.assertIn(marker, self.template)
        self.assertIn("!setenv", self.sudoers)
        self.assertIn("{{ relay_runner_user }} ALL=(root) NOPASSWD: {{ relay_writer_helper_path }}", self.sudoers)
        self.assertIn("owner: root", self.writer_tasks)
        self.assertIn("group: root", self.writer_tasks)
        self.assertIn("mode: '0750'", self.writer_tasks)
        self.assertIn("mode: '0700'", self.writer_tasks)
        self.assertIn("mode: '0440'", self.writer_tasks)


if __name__ == "__main__":
    unittest.main()
