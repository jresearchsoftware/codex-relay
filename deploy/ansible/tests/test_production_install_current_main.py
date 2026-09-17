"""Step 2: execute real Ansible scope, package and lifecycle decisions locally.

The runner fixture uses only temporary paths, a synthetic runner distribution,
and a recording systemctl substitute. It never contacts Debian or registers a
runner. Native privilege/systemd tests remain separate exact-head checks.
"""
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tarfile
import tempfile
import unittest

import yaml



ROOT = Path(__file__).resolve().parents[1]
ANSIBLE = os.name != 'nt' and shutil.which('ansible-playbook') is not None
HEAD = 'a' * 40


def write_yaml(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding='utf-8')


def run_play(directory, tasks, values, extra=None, check=False):
    play = directory / 'test.yml'
    defaults = yaml.safe_load((ROOT / 'group_vars/all.yml').read_text())
    write_yaml(play, [{'hosts': 'localhost', 'connection': 'local', 'gather_facts': False,
                      'vars': {**defaults, **values}, 'tasks': tasks}])
    env = {**os.environ, 'ANSIBLE_NOCOLOR': '1', 'ANSIBLE_LOCALHOST_WARNING': 'False',
           'ANSIBLE_ROLES_PATH': str(directory / 'roles'), 'ANSIBLE_CONFIG': str(ROOT / 'ansible.cfg')}
    command = ['ansible-playbook', '-i', 'localhost,', str(play)]
    if check:
        command.append('--check')
    if extra:
        write_yaml(directory / 'extra.yml', extra)
        command += ['--extra-vars', '@' + str(directory / 'extra.yml')]
    return subprocess.run(command, env=env, capture_output=True, text=True, timeout=120)


@unittest.skipUnless(ANSIBLE, 'Linux Ansible required')
class ProductionInstallCompositionTests(unittest.TestCase):


    def test_check_plans_general_software_before_identity_or_work_group_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / 'vars').mkdir()
            shutil.copy(ROOT / 'vars/general-runner.yml', directory / 'vars')
            for filename in ('main.yml', 'general-runtime.yml', 'general-validation.yml'):
                write_yaml(directory / 'roles/relay_runner/tasks' / filename,
                           [{'ansible.builtin.fail': {'msg': 'unmaterialized dependency was used'}}])
            tasks = [{'ansible.builtin.include_tasks': str(ROOT / 'tasks/production-general-runner.yml')}]
            for identity, group_planned in ((False, False), (True, True)):
                result = run_play(directory, tasks, {
                    'relay_deployment_profile': 'production', 'relay_production_exact_head': HEAD,
                    'relay_dispatch_identity_materialized': identity,
                    'relay_codex_work_group_planned': group_planned,
                }, check=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('GENERAL_RUNNER_CHECK_MODE_PLAN=', result.stdout)
                self.assertNotIn('GENERAL_RUNNER_INSTALLED_STATE=', result.stdout)

    def test_owner_lifecycle_paths_cannot_become_second_installers(self):
        runner_enable = (ROOT / 'relay-production-runner-enable.yml').read_text()
        general_enable = (ROOT / 'relay-general-runner.yml').read_text()
        activation = (ROOT / 'relay-reviewer-activation.yml').read_text()
        for source in (runner_enable, general_enable):
            self.assertIn('INSTALL_CURRENT_MAIN_FIRST', source)
            self.assertNotIn('ansible.builtin.unarchive', source)
            self.assertNotIn('ansible.builtin.get_url', source)
        production_roles = [task.get('ansible.builtin.include_role')
                            for task in yaml.safe_load(runner_enable)[0]['tasks']]
        self.assertNotIn({'name': 'relay_runner'}, production_roles)
        self.assertIn('relay_production_reviewer_bind_refresh: false', runner_enable)
        self.assertIn('relay_production_reviewer_bind_refresh: false', activation)

    def test_all_reviewer_restarts_and_codex_group_restart_defer_for_local_apply(self):
        for role in ('relay_runtime', 'relay_artifacts', 'relay_reviewer_bind'):
            for handler in yaml.safe_load((ROOT / 'roles' / role / 'handlers/main.yml').read_text()):
                if 'ansible.builtin.command' in handler:
                    self.assertIn('not relay_production_defer_lifecycle | default(false) | bool', handler['when'])
        codex = yaml.safe_load((ROOT / 'roles/relay_codex_runtime/tasks/main.yml').read_text())
        restart = next(task for task in codex if task.get('ansible.builtin.systemd', {}).get('state') == 'restarted')
        self.assertIn('not relay_production_defer_lifecycle | default(false) | bool', restart['when'])
        handlers = yaml.safe_load((ROOT / 'roles/relay_runner/handlers/main.yml').read_text())
        self.assertEqual([h['ansible.builtin.systemd'] for h in handlers], [{'daemon_reload': True}])

    def test_live_pid_or_enablement_change_prevents_final_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            stub = directory / 'systemctl'
            stub.write_text('#!/bin/sh\nprintf "MainPID=123\\nActiveState=active\\nSubState=running\\nUnitFileState=enabled\\n"\n')
            stub.chmod(0o755)
            source = (ROOT / 'tasks/production-live-lifecycle.yml').read_text().replace('/bin/systemctl', str(stub))
            path = directory / 'lifecycle.yml'
            path.write_text(source)
            include = {'ansible.builtin.include_tasks': str(path)}
            before = 'MainPID=123\nActiveState=active\nSubState=running\nUnitFileState=enabled'
            for changed in (None, 'MainPID=124', 'UnitFileState=disabled'):
                observed = before
                if changed:
                    key = changed.split('=')[0]
                    observed = '\n'.join(changed if line.startswith(key + '=') else line for line in before.splitlines())
                values = {'relay_production_exact_head': HEAD, 'relay_production_lifecycle_verify': True,
                          'relay_production_lifecycle_before': [observed, before]}
                result = run_play(directory, [include], values)
                self.assertEqual(result.returncode == 0, changed is None, result.stdout + result.stderr)
                self.assertEqual('PRODUCTION_LIFECYCLE_PRESERVED=' in result.stdout, changed is None)


class RunnerPackageFixture:
    """Real shared role, with only network and systemd I/O substituted.

    Defaults use temporary paths/root identity. The installed-runtime proof
    supplies real instance identities and canonical paths in its private mounts.
    """

    def __init__(self, directory, instance_values=None):
        self.directory = directory
        role = directory / 'roles/relay_runner'
        self.role = role
        shutil.copytree(ROOT / 'roles/relay_runner', role)
        trace = directory / 'systemctl.jsonl'
        service_state = directory / 'state'
        self.trace, self.service_state = trace, service_state
        service_state.write_text('inactive')
        stub = directory / 'systemctl'
        stub.write_text('#!/usr/bin/python3\nimport json, sys\nfrom pathlib import Path\n'
                        f'with open({str(trace)!r}, "a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\n'
                        f'active=Path({str(service_state)!r}).read_text()=="active"\n'
                        'if sys.argv[1]=="is-active":\n print("active" if active else "inactive"); sys.exit(0 if active else 3)\n'
                        'if sys.argv[1]=="is-enabled":\n print("enabled" if active else "disabled"); sys.exit(0 if active else 1)\n')
        stub.chmod(0o755)
        # Only I/O boundaries are substituted: no download, no real systemd.
        tasks = yaml.safe_load((role / 'tasks/main.yml').read_text())
        for task in tasks:
            if 'ansible.builtin.get_url' in task:
                task.pop('ansible.builtin.get_url')
                task['ansible.builtin.debug'] = {'msg': 'synthetic checksum-independent package fixture'}
            if 'ansible.builtin.systemd' in task:
                spec = task.pop('ansible.builtin.systemd')
                task['ansible.builtin.command'] = {'argv': [str(stub), 'lifecycle', str(spec)]}
            if task.get('ansible.builtin.command', {}).get('argv', [''])[0] == 'systemctl':
                task['ansible.builtin.command']['argv'][0] = str(stub)
        write_yaml(role / 'tasks/main.yml', tasks)
        write_yaml(role / 'handlers/main.yml', [{'name': 'Reload runner unit',
            'ansible.builtin.command': {'argv': [str(stub), 'daemon-reload']}}])
        cache = directory / 'cache'
        cache.mkdir()
        archive = cache / 'runner.tar.gz'
        with tarfile.open(archive, 'w:gz') as tar:
            # GNU tar restores this entry onto the destination itself.
            # Omitting it hid the fresh-install 0755 root regression.
            member = tarfile.TarInfo('./')
            member.type, member.mode = tarfile.DIRTYPE, 0o755
            tar.addfile(member)
            for name, content in {
                'config.sh': b'#!/bin/sh\nexit 99\n', 'run.sh': b'#!/bin/sh\nexit 99\n',
                'bin/Runner.Listener': b'#!/bin/sh\nprintf "2.336.0\\n"\n',
            }.items():
                member = tarfile.TarInfo(name)
                member.mode, member.size = 0o755, len(content)
                tar.addfile(member, io.BytesIO(content))
        (directory / 'install').mkdir()
        (directory / 'units').mkdir()
        runner = directory / 'runner'
        values = {
            'relay_runner_user': 'root', 'relay_runner_group': 'root',
            'relay_user': 'root', 'relay_group': 'root', 'relay_runner_root': str(runner),
            'relay_install_root': str(directory / 'install'), 'relay_state_root': str(directory / 'state-root'),
            'relay_runner_package_cache_root': str(cache), 'relay_runner_package_archive': str(archive),
            'relay_runner_work_root': str(directory / 'mutable/work'), 'relay_runner_home': str(directory / 'mutable/home'),
            'relay_runner_service_unit_path': str(directory / 'units/runner.service'),
            'relay_runner_service_state_management': 'preserve',
        }
        values.update(instance_values or {})
        self.values = values
        self.runner = Path(values['relay_runner_root'])
        self.include = [
            {'ansible.builtin.assert': {'that': [
                f'{key} == {values[key]!r}' for key in (
                    'relay_runner_root', 'relay_install_root', 'relay_state_root',
                    'relay_runner_package_cache_root', 'relay_runner_user',
                )
            ]}},
            {'ansible.builtin.include_role': {'name': 'relay_runner'}},
            {'ansible.builtin.debug': {'msg': 'FIXTURE_PACKAGE_INSTALL_NEEDED={{ relay_runner_package_install_needed }}'}},
        ]

    def run(self, check=False):
        return run_play(self.directory, self.include, self.values, check=check)


@unittest.skipUnless(ANSIBLE and getattr(os, 'geteuid', lambda: 1)() == 0, 'root for temporary file ownership only')
class RunnerInstalledStateExecutionTests(unittest.TestCase):
    def test_fresh_registered_repair_and_idempotent_reconciliation(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            fixture = RunnerPackageFixture(directory)
            runner, values = fixture.runner, fixture.values
            trace, service_state = fixture.trace, fixture.service_state
            result = fixture.run()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((runner / 'bin/Runner.Listener').is_file())
            self.assertEqual(stat.S_IMODE(runner.stat().st_mode), 0o750)
            self.assertFalse((runner / '.runner').exists())
            self.assertFalse((runner / '.credentials').exists())
            self.assertNotIn('lifecycle', trace.read_text())
            listener = runner / 'bin/Runner.Listener'
            before = listener.stat()
            runner.chmod(0o755)
            result = fixture.run(check=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(stat.S_IMODE(runner.stat().st_mode), 0o755)
            result = fixture.run()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(stat.S_IMODE(runner.stat().st_mode), 0o750)
            self.assertIn('FIXTURE_PACKAGE_INSTALL_NEEDED=False', result.stdout)
            self.assertEqual((listener.stat().st_ino, listener.stat().st_mtime_ns),
                             (before.st_ino, before.st_mtime_ns))
            self.assertFalse((runner / '.runner').exists())
            self.assertFalse((runner / '.credentials').exists())
            # Synthetic registration models existing state, without any real credential.
            marker = {'gitHubUrl': 'https://github.com/example/relay-consumer',
                      'agentName': 'relay-general', 'workFolder': values['relay_runner_work_root']}
            (runner / '.runner').write_text(json.dumps(marker))
            credential = runner / '.credentials'
            credential.write_bytes(b'synthetic-instance-state-not-a-credential\n')
            credential.chmod(0o600)
            identity = credential.stat().st_ino
            registration_before = (runner / '.runner').stat()
            service_state.write_text('active')
            (directory / 'units/runner.service').write_text('outdated unit fixture\n')
            result = fixture.run()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn('outdated unit', (directory / 'units/runner.service').read_text())
            self.assertNotIn('lifecycle', trace.read_text())
            # A version change cannot overwrite binaries of an executing runner.
            (runner / 'bin/Runner.Listener').write_text('#!/bin/sh\nprintf "2.335.0\\n"\n')
            result = fixture.run()
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('RUNNER_ACTIVE_PACKAGE_TRANSITION_REQUIRED', result.stdout)
            service_state.write_text('inactive')
            result = fixture.run()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('2.336.0', (runner / 'bin/Runner.Listener').read_text())
            self.assertEqual(stat.S_IMODE(runner.stat().st_mode), 0o750)
            self.assertEqual(credential.stat().st_ino, identity)
            self.assertEqual(stat.S_IMODE(credential.stat().st_mode), 0o600)
            self.assertEqual(credential.read_bytes(), b'synthetic-instance-state-not-a-credential\n')
            self.assertEqual(json.loads((runner / '.runner').read_text()), marker)
            self.assertEqual(((runner / '.runner').stat().st_ino, (runner / '.runner').stat().st_mode),
                             (registration_before.st_ino, registration_before.st_mode))
            result = fixture.run()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertRegex(result.stdout, r'changed=0\s+unreachable=0\s+failed=0')
            self.assertNotIn('lifecycle', trace.read_text())

    def test_unsafe_root_is_rejected_before_namespace_mutation(self):
        for kind in ('file', 'symlink', 'dangling-symlink'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                directory = Path(tmp)
                fixture = RunnerPackageFixture(directory)
                target = directory / 'outside'
                target.mkdir(mode=0o700)
                sentinel = target / 'preserved'
                sentinel.write_text('untouched')
                before = target.stat()
                if kind == 'file':
                    fixture.runner.write_text('not a directory')
                else:
                    fixture.runner.symlink_to(target if kind == 'symlink' else directory / 'missing')
                result = fixture.run()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('RUNNER_NAMESPACE_UNSAFE', result.stdout)
                # A root replaced after the initial guard is also refused by
                # the final non-recursive file operation, without following it.
                source = yaml.safe_load((ROOT / 'roles/relay_runner/tasks/main.yml').read_text())
                converge = next(task for task in source if task['name'] ==
                                'Converge runner root metadata after package reconciliation')
                result = run_play(directory, [converge], fixture.values)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual((target.stat().st_mode, target.stat().st_uid, target.stat().st_gid),
                                 (before.st_mode, before.st_uid, before.st_gid))
                self.assertEqual(sentinel.read_text(), 'untouched')
                self.assertFalse(fixture.trace.exists())

    def test_final_contract_observes_metadata_independently_of_convergence(self):
        source = yaml.safe_load((ROOT / 'roles/relay_runner/tasks/main.yml').read_text())
        first = next(i for i, task in enumerate(source)
                     if task['name'] == 'Inspect final runner root without following links')
        tasks = source[first:first + 2]
        for kind in ('valid', 'mode', 'owner', 'group', 'file', 'symlink', 'absent'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                directory = Path(tmp)
                runner = directory / 'runner'
                if kind == 'file':
                    runner.write_text('not a directory')
                elif kind == 'symlink':
                    runner.symlink_to(directory)
                elif kind != 'absent':
                    runner.mkdir(mode=0o755 if kind == 'mode' else 0o750)
                    # Numeric IDs intentionally need not have passwd/group entries.
                    os.chown(runner, 65534 if kind == 'owner' else 0, 65534 if kind == 'group' else 0)
                result = run_play(directory, tasks, {
                    'relay_runner_root': str(runner), 'relay_runner_user': 'root', 'relay_runner_group': 'root',
                })
                self.assertEqual(result.returncode == 0, kind == 'valid', result.stdout + result.stderr)
                if kind != 'valid':
                    self.assertIn('RUNNER_ROOT_OWNERSHIP_INVALID', result.stdout)

    def test_fresh_check_mode_does_not_claim_unmaterialized_root_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = RunnerPackageFixture(Path(tmp))
            Path(fixture.values['relay_runner_package_archive']).unlink()
            result = fixture.run(check=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse(fixture.runner.exists())

    def test_declared_retired_component_is_removed_by_the_ordinary_controller_role(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            unit = directory / 'relay-controller.service'
            unit.write_text('historical managed component\n')
            source = yaml.safe_load((ROOT / 'roles/relay_controller/tasks/main.yml').read_text())
            tasks = [task for task in source if 'historical Controller daemon' in task['name']]
            self.assertEqual(len(tasks), 3)
            for task in tasks:
                spec = task.get('ansible.builtin.stat') or task.get('ansible.builtin.file')
                if spec:
                    spec['path'] = str(unit)
                if 'ansible.builtin.systemd' in task:
                    self.assertEqual(task.pop('ansible.builtin.systemd')['state'], 'stopped')
                    task['ansible.builtin.debug'] = {'msg': 'fixture stop-and-disable before removal'}
                task.pop('notify', None)
            result = run_play(directory, tasks, {})
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse(unit.exists())
            result = run_play(directory, tasks, {})
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertRegex(result.stdout, r'changed=0\s+unreachable=0\s+failed=0')
