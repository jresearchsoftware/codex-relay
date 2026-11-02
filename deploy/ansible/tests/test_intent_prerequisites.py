"""Execute fresh prerequisite composition with a recording APT action, never APT."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
ANSIBLE = os.name != 'nt' and os.geteuid() == 0 and shutil.which('ansible-playbook') is not None


@unittest.skipUnless(ANSIBLE, 'actual root Linux and Ansible required')
class IntentPrerequisitesTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='relay-prerequisite-test-', dir='/run')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        role = self.root / 'roles/relay_base/tasks'; role.mkdir(parents=True)
        # Substitute only the OS-package action; the real public composition and
        # owning task conditions still execute through Ansible.
        tasks = (ROOT / 'roles/relay_base/tasks/prerequisites.yml').read_text()
        (role / 'prerequisites.yml').write_text(tasks.replace('ansible.builtin.apt:', 'fixture_apt:'))
        plugins = self.root / 'action_plugins'; plugins.mkdir()
        (plugins / 'fixture_apt.py').write_text(
            'import json\nfrom pathlib import Path\nfrom ansible.plugins.action import ActionBase\n'
            'class ActionModule(ActionBase):\n'
            ' def run(self, tmp=None, task_vars=None):\n'
            '  result=super().run(tmp,task_vars)\n'
            '  path=Path(task_vars["fixture_apt_trace"])\n'
            '  with path.open("a") as output: output.write(json.dumps(self._task.args)+"\\n")\n'
            '  result.update(changed=True); return result\n')
        self.trace = self.root / 'apt-calls'
        self.install = self.root / 'new-install'
        self.install.mkdir(mode=0o755)
        self.claim = self.root / 'writer-claims'
        self.dispatch = self.root / 'dispatch'
        self.slot_attempts = self.root / 'slot-dispatch/attempts-v2'
        # An unrelated protected old installation is available throughout every
        # run; neither the fixture action nor the real tasks may mutate it.
        self.old = self.root / 'available-old'; self.old.mkdir(mode=0o755)
        (self.old / 'entrypoint').write_text('accepted protected old entrypoint\n')
        (self.old / 'entrypoint').chmod(0o750)
        self.old_before = self.snapshot()
        self.service_trace = self.root / 'systemctl-calls'
        self.service_states = self.root / 'service-states.json'
        self.systemctl = self.root / 'systemctl'
        self.systemctl.write_text('#!/usr/bin/python3\nimport json,sys\nfrom pathlib import Path\n'
            + 'states=json.loads(Path(' + repr(str(self.service_states)) + ').read_text())\n'
            + 'with Path(' + repr(str(self.service_trace)) + ').open("a") as out: out.write(sys.argv[2]+"\\n")\n'
            + 'value=states.get(sys.argv[2],"LoadState=not-found\\nActiveState=inactive\\nSubState=dead\\n")\n'
            + 'print(value);sys.exit(4 if "LoadState=not-found" in value else 0)\n')
        self.systemctl.chmod(0o755)

    def snapshot(self):
        return {str(path.relative_to(self.old)): (path.read_bytes() if path.is_file() else None,
                path.stat().st_ino, path.stat().st_uid, path.stat().st_gid, path.stat().st_mode)
                for path in [self.old, *self.old.rglob('*')]}

    def play(self, *, expected='none', manage=True, missing=None, states=None, pool=False, slots=False):
        plays = yaml.safe_load((ROOT / 'relay-intent-prerequisites.yml').read_text())
        play = plays[0]
        play.update(connection='local')
        play['vars'] = {'relay_install_root': str(self.install),
            'relay_intent_expected_installed_revision': expected, 'relay_manage_base_packages': manage,
            'relay_namespace': 'fixture', 'relay_reviewer_service_name': 'fixture-reviewer.service',
            'relay_production_runner_service_name': 'fixture-runner.service',
            'relay_controller_service_name': 'fixture-controller.service',
            'relay_reviewer_recovery_service_name': 'fixture-reviewer-recovery.service',
            'relay_reviewer_recovery_timer_name': 'fixture-reviewer-recovery.timer',
            'relay_general_runner_service_name': 'fixture-general.service',
            'relay_writer_claim_root': str(self.claim), 'relay_dispatch_state_root': str(self.dispatch),
            'relay_base_packages': yaml.safe_load((ROOT / 'group_vars/all.yml').read_text())['relay_base_packages'],
            'fixture_apt_trace': str(self.trace)}
        if pool:
            play['vars']['relay_general_runner_pool'] = {'name': 'shared-fixture'}
        if slots:
            play['vars']['relay_additional_execution_slots'] = [{'relay_runner_service_name': 'fixture-slot-second.service'}]
            play['vars']['relay_execution_slots'] = [{'paths': {'attemptRoot': str(self.slot_attempts)}}]
        self.service_states.write_text(json.dumps(states or {}))
        for task in play['pre_tasks']:
            command = task.get('ansible.builtin.command', {})
            if command.get('argv', [None])[0] == '/bin/systemctl':
                command['argv'][0] = str(self.systemctl)
        if missing:
            # Fixture-only dependency-path seam exercises the exact bounded
            # executable checker without changing host /usr or alternatives.
            command = play['tasks'][1]['ansible.builtin.command']['argv']
            index = 0 if missing == 'NODE' else 1
            present = '/usr/bin/node' if index == 0 else '/usr/bin/cc'
            command[-1] = command[-1].replace(present, str(self.root / ('missing-' + missing)))
        path = self.root / 'play.yml'; path.write_text(yaml.safe_dump(plays, sort_keys=False))
        inventory = self.root / 'inventory.json'
        inventory.write_text(json.dumps({'all': {'children': {'relay': {'hosts': {'localhost': {}}}}}}))
        result = subprocess.run(['ansible-playbook', '-i', str(inventory), str(path)], capture_output=True,
            text=True, timeout=45, env={**os.environ, 'ANSIBLE_NOCOLOR': '1',
                'ANSIBLE_ROLES_PATH': str(self.root / 'roles'),
                'ANSIBLE_ACTION_PLUGINS': str(self.root / 'action_plugins'),
                'ANSIBLE_LOCALHOST_WARNING': 'False'})
        self.assertEqual(self.snapshot(), self.old_before)
        return result

    def test_fresh_target_installs_exact_owning_prerequisite_list_without_accounts_or_helpers(self):
        result = self.play()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = [json.loads(line) for line in self.trace.read_text().splitlines()]
        self.assertEqual(calls, [{'name': yaml.safe_load((ROOT / 'group_vars/all.yml').read_text())['relay_base_packages'],
                                  'state': 'present', 'update_cache': True}])
        self.assertEqual(list(self.install.iterdir()), [])

    def test_existing_revision_and_forged_missing_pointer_proof_fail_before_package_action(self):
        for expected in ['a' * 40, 'none']:
            with self.subTest(expected=expected):
                if expected == 'none':
                    (self.install / 'current').symlink_to(self.old)
                result = self.play(expected=expected)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('INTENT_PREREQUISITES_FRESH_TARGET_REQUIRED', result.stdout)
                self.assertFalse(self.trace.exists())

    def test_disabled_package_management_preserves_external_prerequisite_route(self):
        result = self.play(manage=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.trace.exists())
        self.assertEqual(list(self.install.iterdir()), [])

    def test_disabled_package_management_reports_each_missing_staging_executable_without_apt(self):
        for missing in ['NODE', 'C_COMPILER']:
            with self.subTest(missing=missing):
                result = self.play(manage=False, missing=missing)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('INTENT_PREREQUISITES_' + missing + '_REQUIRED', result.stdout)
                self.assertFalse(self.trace.exists())

    def test_ordinary_base_uses_the_exact_same_first_prerequisite_task(self):
        tasks = yaml.safe_load((ROOT / 'roles/relay_base/tasks/main.yml').read_text())
        self.assertEqual(tasks[0]['ansible.builtin.include_tasks'], 'prerequisites.yml')
        prerequisite = yaml.safe_load((ROOT / 'roles/relay_base/tasks/prerequisites.yml').read_text())
        self.assertEqual(len(prerequisite), 1)
        self.assertEqual(prerequisite[0]['ansible.builtin.apt'], {
            'name': '{{ relay_base_packages }}', 'state': 'present',
            'update_cache': '{{ relay_manage_base_packages | bool }}'})
        self.assertEqual(prerequisite[0]['when'], 'relay_manage_base_packages | bool')

    def test_active_activating_or_unknown_namespace_orphans_fail_before_apt(self):
        for unit, state in [
            ('fixture-reviewer.service', 'ActiveState=active\nSubState=running\nMainPID=42\nControlPID=0'),
            ('fixture-controller.service', 'ActiveState=activating\nSubState=start\nMainPID=0\nControlPID=42'),
            ('fixture-runner.service', 'ActiveState=unknown\nSubState=unknown'),
            ('fixture-general.service', 'ActiveState=active\nSubState=running\nMainPID=43\nControlPID=0'),
            ('fixture-relay-manual-outcome.socket', 'ActiveState=active\nSubState=listening'),
            ('fixture-slot-second.service', 'ActiveState=active\nSubState=running\nMainPID=44\nControlPID=0'),
            ('fixture-reviewer-recovery.service', 'ActiveState=active\nSubState=running\nMainPID=45\nControlPID=0'),
            ('fixture-reviewer-recovery.timer', 'ActiveState=active\nSubState=waiting'),
        ]:
            with self.subTest(unit=unit):
                result = self.play(states={unit: 'LoadState=loaded\n' + state}, slots=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('INTENT_PREREQUISITES_NAMESPACE_ACTIVITY_UNPROVEN', result.stdout)
                self.assertFalse(self.trace.exists())
                self.assertEqual(list(self.install.iterdir()), [])

    def test_shared_general_pool_and_foreign_services_are_outside_fresh_namespace_stop_boundary(self):
        active = 'LoadState=loaded\nActiveState=active\nSubState=running\nMainPID=42\nControlPID=0'
        result = self.play(pool=True, states={name: active for name in [
            'fixture-general.service', 'docker.service', 'nginx.service', 'shared-fixture-pool-1.service']})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self.trace.exists())
        self.assertEqual(set(self.service_trace.read_text().splitlines()), {
            'fixture-reviewer.service', 'fixture-controller.service', 'fixture-runner.service',
            'fixture-relay-manual-outcome.socket', 'fixture-reviewer-recovery.service', 'fixture-reviewer-recovery.timer'})

    def test_retained_gates_and_configured_publication_or_execution_rows_are_preserved_before_apt(self):
        for path in [self.claim / 'admission-v1.json', self.claim / 'admission-pool-v1.json',
                     self.claim / 'publication-v2/repositories/example/sample/71.json',
                     self.claim / 'publication-pool-v1/72.json',
                     self.dispatch / 'attempts-v2/73.json', self.slot_attempts / '74.json']:
            with self.subTest(path=path.relative_to(self.root)):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'{"synthetic":"retained original operation"}\n'); path.chmod(0o600)
                before = path.read_bytes(), path.stat().st_ino
                result = self.play(slots=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('INTENT_PREREQUISITES_RETAINED_ADMISSION_REQUIRES_DIAGNOSIS', result.stdout)
                self.assertEqual((path.read_bytes(), path.stat().st_ino), before)
                self.assertFalse(self.trace.exists())
                self.assertFalse(self.service_trace.exists())
                path.unlink()

    def test_empty_provisioned_roots_and_keys_pass_with_known_inactive_recovery_timer(self):
        for path in [self.claim / 'publication-v2/repositories/example/sample',
                     self.claim / 'publication-pool-v1', self.dispatch / 'attempts-v2', self.slot_attempts]:
            path.mkdir(parents=True, mode=0o700)
        key = self.claim / 'publication-v2/.provisioned-key'
        key.write_bytes(b'synthetic provisioned key untouched'); key.chmod(0o600)
        before = key.read_bytes(), key.stat().st_ino
        result = self.play(slots=True, states={'fixture-reviewer-recovery.timer':
            'LoadState=loaded\nActiveState=inactive\nSubState=dead'})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self.trace.exists())
        self.assertEqual((key.read_bytes(), key.stat().st_ino), before)

    def test_aliased_or_unknown_journal_kind_is_unproven_without_content_read_or_apt(self):
        target = self.root / 'foreign-journal'; target.mkdir()
        self.dispatch.mkdir()
        (self.dispatch / 'attempts-v2').symlink_to(target)
        result = self.play()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('INTENT_PREREQUISITES_RETAINED_ADMISSION_REQUIRES_DIAGNOSIS', result.stdout)
        self.assertFalse(self.trace.exists())
        self.assertEqual(list(target.iterdir()), [])
        (self.dispatch / 'attempts-v2').unlink()
        os.mkfifo(self.dispatch / 'attempts-v2', 0o600)
        before = (self.dispatch / 'attempts-v2').lstat().st_ino
        result = self.play()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('INTENT_PREREQUISITES_RETAINED_ADMISSION_REQUIRES_DIAGNOSIS', result.stdout)
        self.assertFalse(self.trace.exists())
        self.assertEqual((self.dispatch / 'attempts-v2').lstat().st_ino, before)


if __name__ == '__main__':
    unittest.main()
