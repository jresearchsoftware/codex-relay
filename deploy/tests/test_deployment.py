"""Execute the public CLI with a recorded backend; no target or credentials used."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
import config


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def commit(root):
    git(root, 'init', '--quiet', '--template=', '--initial-branch=main')
    git(root, 'add', '.')
    git(root, '-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '--quiet', '-m', 'fixture')
    return git(root, 'rev-parse', 'HEAD')


class ConfigurationTests(unittest.TestCase):
    def test_alternate_consumer_passes_the_actual_codex_runtime_contract(self):
        import yaml
        from ansible.parsing.dataloader import DataLoader
        from ansible.template import Templar
        from jinja2 import Environment, StrictUndefined
        c = json.loads((ROOT / 'deploy/example.json').read_text())
        c['environment'].update(namespace='canary-relay', serviceUser='canary-service',
            reviewerUser='canary-reviewer', codexWorkGroup='canary-work')
        c['environment']['runner']['user'] = 'canary-runner'
        c['environment']['generalRunner']['user'] = 'canary-general'
        c['consumer']['runtimeUser'] = 'canary-codex'
        c['consumer']['paths'] = {k: v.replace('codex-relay', 'canary-relay') for k, v in c['consumer']['paths'].items()}
        config.validate(c, ROOT)
        backend = ROOT / 'deploy/ansible'
        values = {**yaml.safe_load((backend / 'group_vars/all.yml').read_text()), **config.compile_inputs(c)}
        templar = Templar(loader=DataLoader(), variables=values)
        keys = ['relay_codex_cli_version', 'relay_codex_installer_url', 'relay_codex_user', 'relay_codex_group',
                'relay_codex_launcher_path', 'relay_install_root', 'relay_codex_binary_path',
                'relay_codex_access_token_file', 'relay_config_root', 'relay_codex_work_group']
        resolved = {k: templar.template(values[k]) for k in keys}
        contract = yaml.safe_load((backend / 'roles/relay_codex_runtime/tasks/main.yml').read_text())[0]
        environment = Environment(undefined=StrictUndefined)
        for expression in contract['ansible.builtin.assert']['that']:
            self.assertTrue(environment.compile_expression(expression)(**resolved), expression)

    def test_example_is_valid_and_compiles_consumer_properties(self):
        c = config.load(ROOT / 'deploy/example.json', ROOT)
        result = config.compile_inputs(c)
        self.assertEqual(result['relay_github_repository'], c['consumer']['repository'])
        self.assertEqual(result['relay_production_runner_user'], c['environment']['runner']['user'])
        self.assertNotEqual(result['relay_production_runner_user'], result['relay_general_runner_user'])
        self.assertFalse(result['relay_docker_nginx_manage'])

    def test_rejects_unknown_backend_inputs_credential_material_and_shared_identities(self):
        c = json.loads((ROOT / 'deploy/example.json').read_text())
        for mutate in [lambda v: v.update(ansible_playbook='caller.yml'),
                       lambda v: v['environment']['runner'].update(user=v['environment']['reviewerUser']),
                       lambda v: v['environment']['compatibilityLinks'].update({'../escape':'controller'}),
                       lambda v: v['environment']['ingress'].update(ownershipRoot='/opt'),
                       lambda v: v['target'].update(host='host; command'),
                       lambda v: v['source'].update(revision='--upload-pack=command')]:
            changed = copy.deepcopy(c)
            mutate(changed)
            with self.assertRaises(config.InvalidConfig):
                config.validate(changed, ROOT)

    def test_ambiguous_json_and_template_execution_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'config.json'
            for value in ['{"schemaVersion":1,"schemaVersion":2}', '{"input":"{{ lookup(\"pipe\",\"command\") }}"}']:
                path.write_text(value)
                with self.assertRaises(ValueError):
                    config.load(path, ROOT)


@unittest.skipUnless(sys.platform == 'linux', 'Linux product entrypoint')
class EntrypointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='relay-deploy-test-')
        cls.base = Path(cls.temporary.name)
        cls.product = cls.base / 'product'
        cls.product.mkdir()
        for name in ['deploy', 'consumer', 'controller', 'runtime', 'contracts', 'reviewer']:
            shutil.copytree(ROOT / name, cls.product / name,
                            ignore=shutil.ignore_patterns('__pycache__', 'target', '.pytest_cache'))
        cls.revision = commit(cls.product)
        cls.consumer = cls.base / 'consumer'
        cls.consumer.mkdir()
        c = json.loads((ROOT / 'deploy/example.json').read_text())
        cls.key = cls.base / 'key-reference'
        cls.key.write_text('fixture-only-not-a-key')
        c['target']['identityFile'] = str(cls.key)
        cls.config = cls.consumer / 'relay.json'
        cls.config.write_text(json.dumps(c))
        cls.consumer_revision = commit(cls.consumer)
        cls.bin = cls.base / 'bin'
        cls.bin.mkdir()
        cls.capture = cls.base / 'capture.json'
        cls.calls = cls.base / 'ssh-calls'
        stubs = {
            'ssh-keygen': '''import sys
if '-F' in sys.argv: print('fixture-known-host')
else: print('256 SHA256:' + ('B' if sys.argv[-1]=='-' else 'A')*43 + ' fixture')
''',
            'ssh': f'from pathlib import Path\nPath({str(cls.calls)!r}).write_text("strict-preflight")\n',
            'ansible-playbook': f'''import json,sys
from pathlib import Path
a=sys.argv; inventory=json.loads(Path(a[a.index('-i')+1]).read_text())
hosts=inventory['all']['children']['relay']['hosts']; assert list(hosts)==['192.0.2.10']
v=hosts['192.0.2.10']; head=v['relay_source_identity']['revision']; consumer=v['relay_consumer_revision']
assert '--extra-vars' not in a # config permits scoped second-runner overrides
Path({str(cls.capture)!r}).write_text(json.dumps(v))
print('192.0.2.10 : ok=1 changed=0 unreachable=0 failed=0')
print('PRODUCTION_APPLY_VALIDATED='+head)
print('PRODUCTION_CHECK_VALIDATED='+head+';state=stable-no-op;recovery=none')
print('RELAY_INSTALLED_REVISION='+head+';consumer='+consumer+';previous=none')
''',
        }
        for name, source in stubs.items():
            path = cls.bin / name
            path.write_text('#!/usr/bin/python3\n' + source)
            path.chmod(0o755)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def invoke(self, *args):
        self.capture.unlink(missing_ok=True)
        return subprocess.run([sys.executable, str(self.product / 'deploy/relay-deploy.py'),
            '--config', str(self.config), '--log-root', str(self.base / 'logs'), *args],
            env={**os.environ, 'PATH': str(self.bin) + ':' + os.environ['PATH'],
                 'TMPDIR': str(self.base),
                 'ANSIBLE_CONFIG':'/untrusted/caller.cfg', 'PYTHONDONTWRITEBYTECODE':'1'},
            capture_output=True, text=True)

    def test_apply_reports_exact_product_and_consumer_without_review_gate(self):
        result = self.invoke('--phase','apply','--requested-revision','main','--resolved-revision',self.revision)
        self.assertEqual(result.returncode, 0, result.stderr)
        for line in ['requested_revision=main', 'resolved_revision='+self.revision,
                     'installed_revision='+self.revision, 'consumer_revision='+self.consumer_revision, 'RELAY_INSTALL_RESULT=PASS']:
            self.assertIn(line, result.stdout)
        values = json.loads(self.capture.read_text())
        self.assertEqual(values['relay_production_operation_target_head'], self.revision)
        self.assertEqual(values['relay_runner_service_state_management'], 'preserve')
        self.assertFalse(values['relay_service_activation_authorized'])
        self.assertFalse(Path(values['relay_source_archive']).exists(), 'temporary transport must be removed')

    def test_explicit_sha_and_normal_post_check_bind_the_same_identity(self):
        result = self.invoke('--phase','post-check','--requested-revision',self.revision)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('installed_revision='+self.revision,result.stdout)

    def test_mismatched_or_dirty_source_fails_before_backend(self):
        result = self.invoke('--phase','apply','--resolved-revision','a'*40)
        self.assertNotEqual(result.returncode,0)
        self.assertFalse(self.capture.exists())
        dirty = self.product / 'uncommitted'
        dirty.write_text('uncommitted source')
        try:
            result = self.invoke('--phase','apply')
            self.assertNotEqual(result.returncode,0)
            self.assertFalse(self.capture.exists())
        finally:
            dirty.unlink()

    def test_post_check_rejects_config_drift_even_with_valid_identity_receipt(self):
        backend = self.bin / 'ansible-playbook'
        original = backend.read_text()
        try:
            backend.write_text(original.replace('changed=0', 'changed=1'))
            result = self.invoke('--phase', 'post-check', '--requested-revision', self.revision)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('post-check-drift', result.stderr)
            self.assertNotIn('RELAY_INSTALL_RESULT=PASS', result.stdout)
        finally:
            backend.write_text(original)

    def test_lifecycle_flags_are_separate_from_version_selection(self):
        for args in [('--phase','activate'), ('--phase','general-runner-enable'), ('--phase','apply','--authorize-runner-enable'),
                     ('--phase','apply','--reviewed-head',self.revision),
                     ('--phase','stale-dispose','--authorize-stale-disposition')]:
            result=self.invoke(*args)
            self.assertNotEqual(result.returncode,0)
            self.assertFalse(self.capture.exists())


if __name__ == '__main__':
    unittest.main()
