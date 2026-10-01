"""Run the ingress identity guard before its real Reviewer config render."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml


ANSIBLE = Path(__file__).resolve().parents[1]
PLAYBOOK = ANSIBLE / 'relay-docker-nginx.yml'


@unittest.skipUnless(os.name != 'nt' and os.geteuid() == 0,
                     'native root filesystem and Ansible execution required')
class DockerNginxInstanceGuardExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='relay-ingress-identity-', dir='/run')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.config_root = self.root / 'config'
        self.config_root.mkdir(mode=0o751)
        self.config = self.config_root / 'reviewer-mcp.json'
        self.fragment = self.root / 'existing-ingress.conf'
        self.fragment.write_text('preserve-existing-ingress\n')
        self.foreign = self.root / 'docreview.json'
        self.foreign.write_text('{"repository":"fixture/docreview"}\n')
        self.reload = self.root / 'reload-sentinel'
        (self.root / 'scripts').mkdir()
        shutil.copyfile(ANSIBLE / 'scripts/verify_instance_identity.py',
                        self.root / 'scripts/verify_instance_identity.py')
        (self.root / 'roles').symlink_to(ANSIBLE / 'roles', target_is_directory=True)

    def run_ingress_boundary(self, repository):
        self.config.write_text(json.dumps({'repository': repository, 'sentinel': 'existing-binding'}))
        self.config.chmod(0o640)
        before = self.config.read_bytes()
        before_stat = self.config.stat()
        variables = {
            **yaml.safe_load((ANSIBLE / 'group_vars/all.yml').read_text()),
            'ansible_connection': 'local', 'ansible_python_interpreter': '/usr/bin/python3',
            'relay_install_root': str(self.root / 'install'), 'relay_config_root': str(self.config_root),
            'relay_github_repository': 'fixture/public-relay',
            'relay_release_commit': 'a' * 40, 'relay_release_sha256': 'b' * 64,
            'relay_reviewer_user': self.root.name, 'relay_reviewer_group': 'root',
        }
        for name, suffix in {
            'relay_reviewer_service_name': 'reviewer.service',
            'relay_reviewer_recovery_service_name': 'recovery.service',
            'relay_reviewer_recovery_timer_name': 'recovery.timer',
            'relay_production_runner_service_name': 'runner.service',
            'relay_general_runner_service_name': 'general-runner.service',
            'relay_controller_service_name': 'controller.service',
            'relay_superseded_proxy_service_name': 'proxy.service',
        }.items():
            variables[name] = self.root.name + '-' + suffix
        preflight = yaml.safe_load((ANSIBLE / 'roles/relay_preflight/tasks/main.yml').read_text())
        binding = yaml.safe_load((ANSIBLE / 'roles/relay_reviewer_bind/tasks/main.yml').read_text())
        identity_guard = next(task for task in preflight if task.get('name') ==
                              "Refuse another consumer's repository or service identity before reconciliation")
        render = next(task for task in binding if task.get('name') ==
                      'Render the Reviewer config for the validated bind mode')
        # Keep the production role order and both real boundary tasks. Docker
        # discovery and later ingress work are replaced by local sentinels only;
        # no system service, Docker container or production path is mutated.
        tasks = []
        for role in yaml.safe_load(PLAYBOOK.read_text())[0]['roles']:
            if role['role'] == 'relay_preflight':
                tasks.append(copy.deepcopy(identity_guard))
            elif role['role'] == 'relay_reviewer_bind':
                tasks.append(copy.deepcopy(render))
            elif role['role'] == 'relay_docker_nginx':
                tasks.append({'name': 'Fixture ingress reconciliation sentinel',
                              'ansible.builtin.copy': {'dest': str(self.fragment), 'content': 'reconciled\n'}})
        fixture = self.root / 'ingress.yml'
        fixture.write_text(yaml.safe_dump([{
            'hosts': 'localhost', 'gather_facts': False, 'vars': variables, 'tasks': tasks,
            'handlers': [{'name': 'Try-restart Reviewer for validated bind mode',
                          'ansible.builtin.copy': {'dest': str(self.reload), 'content': 'reloaded\n'}}],
        }]))
        result = subprocess.run(
            [str(Path(sys.executable).with_name('ansible-playbook')), '-i', 'localhost,', str(fixture)],
            env={**os.environ, 'ANSIBLE_NOCOLOR': '1', 'ANSIBLE_CONFIG': str(ANSIBLE / 'ansible.cfg')},
            capture_output=True, text=True, timeout=60)
        return result, before, before_stat

    def test_foreign_repository_blocks_before_config_ingress_or_reload_mutation(self):
        result, before, before_stat = self.run_ingress_boundary('fixture/docreview')
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('RELAY_INSTANCE_IDENTITY_REJECTED', result.stdout + result.stderr)
        self.assertEqual(self.config.read_bytes(), before)
        after = self.config.stat()
        self.assertEqual((after.st_ino, after.st_mtime_ns, after.st_ctime_ns),
                         (before_stat.st_ino, before_stat.st_mtime_ns, before_stat.st_ctime_ns))
        self.assertEqual(self.fragment.read_text(), 'preserve-existing-ingress\n')
        self.assertEqual(self.foreign.read_text(), '{"repository":"fixture/docreview"}\n')
        self.assertFalse(self.reload.exists())

    def test_admitted_repository_reaches_the_real_config_render(self):
        result, _, _ = self.run_ingress_boundary('fixture/public-relay')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        rendered = json.loads(self.config.read_text())
        self.assertEqual(rendered['repository'], 'fixture/public-relay')
        self.assertEqual(rendered['artifact']['commit'], 'a' * 40)
        self.assertEqual(self.fragment.read_text(), 'reconciled\n')
        self.assertTrue(self.reload.exists())
        self.assertEqual(self.foreign.read_text(), '{"repository":"fixture/docreview"}\n')


if __name__ == '__main__':
    unittest.main()
