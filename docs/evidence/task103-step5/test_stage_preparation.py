"""Preparation and disposable local identity tests; no remote/service/model operations."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import subprocess
import sys
import unittest

import yaml


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


stage = module(Path(__file__).with_name('stage-test-installation.py'), 'step5_stage')


def prepared_bundle(root):
    (root / 'ansible').mkdir()
    (root / 'source/deploy').mkdir(parents=True)
    (root / 'source/deploy/managed_pool.py').write_text('# deterministic unchanged helper\n')
    (root / 'ansible/stage.yml').write_text(yaml.safe_dump([{'name': 'old', 'become': False, 'post_tasks': [
        {'name': 'Create only dedicated TEST service tool overlay directories', 'loop': ['old.service']}]}]))
    (root / 'plan.json').write_text(json.dumps({'namespace': 'codex-relay-test', 'sourceRevision': 'a' * 40,
        'adaptations': [], 'limitations': [], 'prerequisites': []}))
    stage.patch_bundle(root, root / 'source', 2, 'prepared', 'guard')
    return yaml.safe_load((root / 'ansible/stage.yml').read_text())[0]


class PreparationTests(unittest.TestCase):
    def config(self, namespace='codex-relay-test-two'):
        return {'source': {'revision': 'b' * 40}, 'target': {'host': '195.201.83.241'},
                'consumer': {'repository': 'jresearchsoftware/codex-relay-testbed-2', 'runtimeUser': 'relay-test-two-codex',
                             'executionSlots': [{'id': 'primary'}, {'id': 'second'}]},
                'environment': {'namespace': namespace, 'generalRunner': {'name': 'old'}}}

    def test_config_preserves_namespace_runtime_and_uses_one_owner_pool(self):
        original = self.config()
        result = stage.prepared_config(original, 'a' * 40, '/mnt/c/private/test-admin.pem', '100', '200', 2)
        self.assertEqual(result['consumer']['runtimeUser'], 'relay-test-two-codex')
        self.assertEqual(result['environment']['generalRunner']['user'], 'relay-test-general-runner')
        self.assertEqual(result['environment']['generalRunner']['name'], 'relay-test-managed-pool')
        self.assertNotIn('executionSlots', result['consumer'])
        self.assertEqual(original['environment']['generalRunner']['name'], 'old')

    def test_exact_source_adaptation_keeps_original_guards_and_private_archives(self):
        previous = module(stage.PREVIOUS_PATH, 'original_test_stage')
        prepared, transformed, guard = stage.adapted_prepare(previous)
        self.assertTrue(callable(prepared))
        self.assertIn("range(2, 33)", transformed)
        self.assertIn("status['unknown']==[]", guard)
        self.assertIn("status['phase']=='open'", guard)
        self.assertIn("journal-", guard)
        self.assertIn('relay-test-managed-pool-pool-', guard)
        self.assertNotIn("task103-step3-retained-local-state", guard)
        with self.assertRaises(ValueError):
            stage.replace_once('changed source', 'expected invariant', 'new')

    def test_pool_overlay_targets_only_managed_service_dirs_and_never_creates_host_tool(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            play = prepared_bundle(root)
            self.assertIs(play['become'], True)
            for item in play['post_tasks']:
                if 'loop' in item:
                    self.assertEqual(item['loop'], ['relay-test-managed-pool-pool-1.service', 'relay-test-managed-pool-pool-2.service'])
                for module_name in ['ansible.builtin.copy', 'ansible.builtin.file']:
                    if module_name in item:
                        target = item[module_name].get('dest', item[module_name].get('path'))
                        self.assertTrue(target.startswith('/etc/systemd/system/'))
            wrapper = (root / 'run-stage.sh').read_text()
            self.assertLess(wrapper.index('os.lstat(p)'), wrapper.index('exec /usr/bin/systemd-run'))
            self.assertNotIn('touch ', wrapper)
            subprocess.run(['sh', '-n'], input=wrapper, text=True, check=True, capture_output=True)


    @unittest.skipUnless(sys.platform == 'linux' and os.geteuid() == 0
                         and shutil.which('ansible-playbook') and shutil.which('sudo'),
                         'native root, Ansible, sudo and existing nobody identity required')
    def test_native_staged_version_probe_uses_runner_uid_and_preserves_foreign_diagnostics(self):
        import pwd
        import stat
        account = pwd.getpwnam('nobody')
        source = Path(__file__).resolve().parents[3]
        tasks = yaml.safe_load((source / 'deploy/ansible/tasks/managed-pool-member.yml').read_text())
        probe = next(task for task in tasks if task['name'] == 'Verify the exact pinned physical runner version as its own identity')
        with tempfile.TemporaryDirectory(prefix='task103-stager-identity-', dir='/run') as value:
            root = Path(value)
            root.chmod(0o755)
            play = prepared_bundle(root)
            member = root / 'member'
            (member / 'bin').mkdir(parents=True)
            for path in [member, member / 'bin']:
                os.chown(path, account.pw_uid, account.pw_gid)
                path.chmod(0o750)
            listener = member / 'bin/Runner.Listener'
            listener.write_text('#!/usr/bin/python3\nfrom pathlib import Path\n'
                'root = Path(__file__).resolve().parent.parent\n'
                '(root / "_diag").mkdir(mode=0o700, exist_ok=True)\n'
                '(root / "_diag/Runner_fixture.log").write_text("synthetic version probe")\n'
                'print("2.336.0")\n')
            os.chown(listener, account.pw_uid, account.pw_gid)
            listener.chmod(0o750)
            play.pop('post_tasks')
            play.update(hosts='localhost', connection='local', gather_facts=False, tasks=[probe], vars={
                'relay_general_runner_pool': {'runnerUser': account.pw_name},
                'relay_pool_member': {'root': str(member)}, 'relay_runner_package_version': '2.336.0'})
            path = root / 'identity.yml'
            path.write_text(yaml.safe_dump([play]))
            environment = {**os.environ, 'HOME': str(root), 'ANSIBLE_LOCAL_TEMP': str(root / 'ansible-local'),
                           'ANSIBLE_REMOTE_TEMP': str(root / 'ansible-remote'), 'PYTHONDONTWRITEBYTECODE': '1'}
            argv = ['ansible-playbook', '-i', 'localhost,', '-e', 'ansible_python_interpreter=/usr/bin/python3', str(path)]
            result = subprocess.run(argv, env=environment, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            diagnostic, log = member / '_diag', member / '_diag/Runner_fixture.log'
            self.assertEqual((diagnostic.stat().st_uid, stat.S_IMODE(diagnostic.stat().st_mode)), (account.pw_uid, 0o700))
            self.assertEqual((log.stat().st_uid, stat.S_IMODE(log.stat().st_mode)), (account.pw_uid, 0o600))
            # Existing foreign diagnostics are never adopted or repaired by a
            # probe. This is a known disposable fixture, not a host path.
            os.chown(diagnostic, 0, 0)
            os.chown(log, 0, 0)

            def metadata(target):
                info = target.stat()
                return info.st_uid, info.st_gid, info.st_mode, info.st_mtime_ns, info.st_ctime_ns

            before = (metadata(diagnostic), metadata(log), log.read_bytes())
            result = subprocess.run(argv, env=environment, capture_output=True, text=True, timeout=60)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((metadata(diagnostic), metadata(log), log.read_bytes()), before)


if __name__ == '__main__':
    unittest.main()
