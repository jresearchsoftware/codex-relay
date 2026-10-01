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
import textwrap
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
    def test_tls_sources_and_public_identity_compile_without_ssh_fallback(self):
        c = json.loads((ROOT / 'deploy/example.json').read_text())
        original = config.compile_inputs(c)
        self.assertTrue(original['relay_tls_allow_legacy_lineage'])
        self.assertEqual(original['relay_tls_public_addresses'], [])
        self.assertEqual(original['relay_tls_acme_admitted_ip'], '')
        c['environment']['tls'] = {'source': {
            'certificateFile': '/etc/owner-tls/fullchain.pem',
            'privateKeyFile': '/etc/owner-tls/private.pem'}}
        c['environment']['reviewerCredential'] = {'sourceKeyFile': '/root/owner-reviewer.pem'}
        config.validate(c, ROOT)
        v = config.compile_inputs(c)
        self.assertFalse(v['relay_tls_allow_legacy_lineage'])
        self.assertEqual(v['relay_nginx_server_certificate_file'], '/etc/owner-tls/fullchain.pem')
        self.assertEqual(v['relay_reviewer_credential_source_file'], '/root/owner-reviewer.pem')
        c['environment']['tls'] = {'acme': {'email': 'owner@example.invalid',
            'challenge': 'webroot', 'webroot': '/srv/shared/web-root'}}
        c['environment']['ingress']['publicAddresses'] = ['198.51.100.20', '2001:db8::20']
        config.validate(c, ROOT)
        v = config.compile_inputs(c)
        self.assertEqual(v['relay_tls_public_addresses'], ['198.51.100.20', '2001:db8::20'])
        self.assertNotIn(c['target']['host'], v['relay_tls_public_addresses'])
        self.assertTrue(v['relay_tls_acme_configured'])
        self.assertTrue(v['relay_nginx_server_certificate_file'].endswith('/certs/server-fullchain.pem'))

    def test_ambiguous_bootstrap_configuration_is_rejected(self):
        c = json.loads((ROOT / 'deploy/example.json').read_text())
        c['environment']['tls'] = {'acme': {'email': 'owner@example.invalid',
            'challenge': 'webroot', 'webroot': '/srv/shared/web-root'}}
        c['environment']['ingress']['publicAddresses'] = ['198.51.100.20']
        for mutate in [lambda e: e['ingress'].pop('publicAddresses'),
                       lambda e: e['ingress'].update(publicAddresses=['ssh.example.invalid']),
                       lambda e: e['ingress'].update(publicAddresses=['198.51.100.20'] * 2),
                       lambda e: e['tls']['acme'].update(challenge='standalone'),
                       lambda e: e['tls']['acme'].update(webroot='/srv/foreign/web-root'),
                       lambda e: e['tls']['acme'].update(email='owner@example.invalid;command'),
                       lambda e: e['tls'].update(source={'certificateFile': '/etc/a.pem', 'privateKeyFile': '/etc/b.pem'}),
                       lambda e: e.update(reviewerCredential={'sourceKeyFile': '../private.pem'}),
                       lambda e: e['tls'].update(source={'certificateFile': '/etc/a.pem', 'privateKeyFile': '/etc/a.pem'})]:
            changed = copy.deepcopy(c)
            mutate(changed['environment'])
            with self.subTest(environment=changed['environment']), self.assertRaises(config.InvalidConfig):
                config.validate(changed, ROOT)

    def test_compiler_preserves_omitted_and_explicit_effort_for_runtime_resolution(self):
        for effort in [None, 'max', 'high', 'ultra']:
            c = json.loads((ROOT / 'deploy/example.json').read_text())
            if effort is not None:
                c['consumer']['defaultProfile']['effort'] = effort
            config.validate(c, ROOT)
            values = config.compile_inputs(c)
            if effort is None:
                self.assertNotIn('relay_default_effort', values)
            else:
                self.assertEqual(values['relay_default_effort'], effort)

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
        c['environment']['ingress']['publicAddresses'] = ['198.51.100.20', '2001:db8::20']
        c['environment']['tls'] = {'acme': {'email': 'owner@example.invalid',
            'challenge': 'webroot', 'webroot': '/srv/shared/web-root'}}
        c['environment']['reviewerCredential'] = {'sourceKeyFile': '/root/reviewer-input.pem'}
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
            'ssh': f'''import sys
from pathlib import Path
Path({str(cls.calls)!r}).write_text("strict-preflight")
if '--hold' in sys.argv[-1]:
    print('BOOTSTRAP_GUARD_READY', flush=True)
    sys.stdin.read()
    if Path({str(cls.base / 'guard-fail')!r}).exists(): sys.exit(1)
''',
            'ansible-playbook': f'''import json,sys
from pathlib import Path
a=sys.argv; inventory=json.loads(Path(a[a.index('-i')+1]).read_text())
hosts=inventory['all']['children']['relay']['hosts']; assert list(hosts)==['192.0.2.10']
v=hosts['192.0.2.10']; head=v['relay_source_identity']['revision']; consumer=v['relay_consumer_revision']
assert '--extra-vars' not in a # config permits scoped second-runner overrides
v['_test_playbook']=Path(a[a.index('-i')+2]).name
v['_test_check_mode']='--check' in a
Path({str(cls.capture)!r}).write_text(json.dumps(v))
print('192.0.2.10 : ok=1 changed=0 unreachable=0 failed=0')
print('PRODUCTION_APPLY_VALIDATED='+head)
print('PRODUCTION_CHECK_VALIDATED='+head+';state=stable-no-op;recovery=none')
print('RELAY_INSTALLED_REVISION='+head+';consumer='+consumer+';previous=none')
print('TLS_BOOTSTRAP_CHECK=PASS;head='+head)
print('TLS_BOOTSTRAP_RESULT=PASS;phase='+v['relay_tls_phase']+';head='+head)
print('REVIEWER_CREDENTIAL_STAGE=PASS;head='+head)
if a[a.index('-i')+2].endswith('relay-production-bootstrap-disposition.yml'):
    print('PRODUCTION_BOOTSTRAP_DISPOSITION_PASS='+head)
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

    def test_ingress_final_host_guard_failure_cannot_report_success(self):
        marker = self.base / 'guard-fail'
        marker.touch()
        try:
            result = self.invoke('--phase', 'ingress', '--authorize-ingress')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('ingress-operation-guard-final-check', result.stderr)
            self.assertNotIn('RELAY_DEPLOYMENT_RESULT=PASS', result.stdout)
        finally:
            marker.unlink()

    def test_bootstrap_phases_are_public_explicit_and_keep_other_lifecycles_off(self):
        for phase, playbook in [('tls-prepare', 'relay-tls-preparation.yml'),
                                ('tls-dry-run', 'relay-tls-preparation.yml'),
                                ('tls-issue', 'relay-tls-preparation.yml'),
                                ('reviewer-credentials', 'relay-reviewer-credentials.yml'),
                                ('ingress', 'relay-docker-nginx.yml')]:
            with self.subTest(phase=phase):
                denied = self.invoke('--phase', phase)
                self.assertNotEqual(denied.returncode, 0)
                self.assertFalse(self.capture.exists())
                result = self.invoke('--phase', phase, '--authorize-' + phase)
                self.assertEqual(result.returncode, 0, result.stderr)
                values = json.loads(self.capture.read_text())
                self.assertEqual(values['_test_playbook'], playbook)
                self.assertEqual(values['relay_bootstrap_exact_head'], self.revision)
                self.assertEqual(values['relay_runner_service_state_management'], 'preserve')
                self.assertFalse(values['relay_runner_registration_authorized'])
                self.assertFalse(values['relay_service_activation_authorized'])
                self.assertEqual(values['relay_tls_public_addresses'], ['198.51.100.20', '2001:db8::20'])
                self.assertEqual(values['relay_tls_acme_admitted_ip'], '')
                wrong = self.invoke('--phase', 'check', '--authorize-' + phase)
                self.assertNotEqual(wrong.returncode, 0)
                self.assertFalse(self.capture.exists())

    def bootstrap_fixture(self, module_name, class_name):
        if os.geteuid() != 0 or not shutil.which('openssl'):
            self.skipTest('native root filesystem and OpenSSL required')
        spec = importlib.util.spec_from_file_location('public_' + module_name,
            self.product / 'deploy/ansible/tests' / (module_name + '.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        fixture_type = getattr(module, class_name)
        fixture_type.setUpClass()
        fixture = fixture_type()
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        # The real bootstrap guard must see the CLI's exact installed revision.
        current = fixture.root / 'install/current'
        release = current.parent / 'releases' / self.revision
        current.resolve().rename(release)
        current.unlink()
        current.symlink_to(release)
        manifest = release / 'artifact-manifest.json'
        value = json.loads(manifest.read_text())
        value.update(commit=self.revision, installedRevision=self.revision)
        manifest.write_text(json.dumps(value))
        return fixture

    def recovery_backend(self, phase, request, destination, trust_store=None):
        # Only SSH/Ansible transport and remote path mapping are synthetic. The
        # public CLI, Git identities, guard, publication and retry are real.
        backend = self.bin / 'ansible-playbook'
        self.addCleanup(backend.write_text, backend.read_text())
        interrupted = destination.parent / 'fixture-crash-injected'
        helper = 'tls-webroot-bootstrap.py' if phase == 'tls-issue' else 'reviewer-credential-stage.py'
        backend.write_text('#!/usr/bin/python3\n' + textwrap.dedent(f'''\
            import importlib.util, json, os, stat, sys
            from pathlib import Path
            from types import SimpleNamespace
            a = sys.argv
            hosts = json.loads(Path(a[a.index('-i') + 1]).read_text())['all']['children']['relay']['hosts']
            assert list(hosts) == ['192.0.2.10']
            v = hosts['192.0.2.10']
            Path({str(self.capture)!r}).write_text(json.dumps(v))
            head = v['relay_bootstrap_exact_head']
            assert v['relay_production_operation_phase'] == {phase!r}
            assert not v['relay_service_activation_authorized']
            assert not v['relay_runner_registration_authorized']
            assert v['relay_runner_service_state_management'] == 'preserve'
            expected = 'relay-tls-preparation.yml' if {phase!r} == 'tls-issue' else 'relay-reviewer-credentials.yml'
            assert Path(a[a.index('-i') + 2]).name == expected
            tools = Path({str(self.product / 'deploy/ansible/tools')!r})
            sys.path.insert(0, str(tools))
            spec = importlib.util.spec_from_file_location('public_bootstrap', tools / {helper!r})
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            request = {request!r}
            destination, interrupted = Path({str(destination)!r}), Path({str(interrupted)!r})
            fsync = os.fsync
            def crash_after_publication(fd):
                fsync(fd)
                if stat.S_ISDIR(os.fstat(fd).st_mode) and destination.exists() and not interrupted.exists():
                    interrupted.touch()
                    os._exit(73)
            os.fsync = crash_after_publication
            if {phase!r} == 'tls-issue':
                assert request['hostname'] == v['relay_tls_acme_hostname']
                request.update(phase=v['relay_tls_phase'], head=head)
                validator = module.validator_module()
                module.validator_module = lambda: SimpleNamespace(validate_sources=lambda *args, **kwargs:
                    validator.validate_sources(*args, **kwargs, trust_store={str(trust_store)!r}))
                module.prepare_ca = lambda _: None
                def no_external_operation(*_):
                    raise AssertionError('validated lineage reuse needs no external operation')
                module.execute = no_external_operation
                result = module.run(request)
                assert result['status'] == 'TLS_EXISTING_CERTIFICATE_REUSED'
                print('TLS_BOOTSTRAP_RESULT=PASS;phase=issue;head=' + head)
            else:
                assert request['app_id'] == str(v['relay_reviewer_app_id'])
                assert request['installation_id'] == str(v['relay_reviewer_app_installation_id'])
                request['exact_head'] = head
                result = module.stage(SimpleNamespace(**request))
                assert result['status'] == 'REVIEWER_CREDENTIAL_UNCHANGED'
                print(result['proof'])
            print('192.0.2.10 : ok=1 changed=0 unreachable=0 failed=0')
            '''))
        return interrupted

    def assert_public_recovery(self, phase, destination, interrupted):
        command = ('--phase', phase, '--authorize-' + phase)
        failed = self.invoke(*command)
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn('BACKEND_FAILED;phase=' + phase, failed.stderr)
        self.assertTrue(interrupted.exists(), 'must reach actual durable publication')
        self.assertEqual(destination.stat().st_nlink, 1)
        identity = destination.stat().st_ino
        if phase == 'tls-issue':
            self.assertFalse((destination.parent / 'server-fullchain.pem').exists())
        recovered = self.invoke(*command)
        self.assertEqual(recovered.returncode, 0, recovered.stderr)
        self.assertIn('RELAY_DEPLOYMENT_RESULT=PASS;phase=' + phase, recovered.stdout)
        self.assertIn('resolved_revision=' + self.revision, recovered.stdout)
        self.assertEqual(destination.stat().st_ino, identity)
        self.assertEqual(destination.stat().st_nlink, 1)

    def test_public_tls_issue_retries_its_interrupted_publication_without_cleanup(self):
        fixture = self.bootstrap_fixture('test_tls_bootstrap_execution', 'BootstrapExecutionTests')
        fixture.config['hostname'] = json.loads(self.config.read_text())['environment']['ingress']['serverName']
        archive, _, _ = fixture.make_server_lineage()
        destination = Path(fixture.config['private_key'])
        interrupted = self.recovery_backend('tls-issue', fixture.config, destination,
                                            fixture.root / 'ca-fixture/root.pem')
        self.assert_public_recovery('tls-issue', destination, interrupted)
        self.assertEqual(destination.read_bytes(), (archive / 'privkey1.pem').read_bytes())
        self.assertEqual(Path(fixture.config['certificate']).read_bytes(), (archive / 'fullchain1.pem').read_bytes())
        self.assertEqual(fixture.foreign.read_bytes(), fixture.foreign_original)

    def test_public_reviewer_credentials_retries_its_interrupted_publication_without_cleanup(self):
        fixture = self.bootstrap_fixture('test_reviewer_credential_staging', 'ReviewerCredentialStagingTests')
        app = json.loads(self.config.read_text())['consumer']['reviewerApp']
        fixture.args.app_id, fixture.args.installation_id = app['appId'], app['installationId']
        fixture.env.write_text('GITHUB_APP_PRIVATE_KEY_FILE=' + str(fixture.destination) + '\n'
            'GITHUB_APP_ID=' + app['appId'] + '\nGITHUB_APP_INSTALLATION_ID=' + app['installationId'] + '\n')
        interrupted = self.recovery_backend('reviewer-credentials', vars(fixture.args), fixture.destination)
        self.assert_public_recovery('reviewer-credentials', fixture.destination, interrupted)
        self.assertEqual(fixture.destination.read_bytes(), fixture.keys[0])
        self.assertEqual(fixture.source.read_bytes(), fixture.keys[0])
        self.assertFalse(list(fixture.credentials.glob('.reviewer-key-*')))

    def test_tls_check_is_read_only_and_ordinary_apply_does_not_enable_bootstrap(self):
        result = self.invoke('--phase', 'tls-check')
        self.assertEqual(result.returncode, 0, result.stderr)
        values = json.loads(self.capture.read_text())
        self.assertTrue(values['_test_check_mode'])
        self.assertFalse(values['relay_docker_nginx_manage'])
        self.assertFalse(values['relay_reviewer_credentials_authorized'])
        result = self.invoke('--phase', 'apply')
        self.assertEqual(result.returncode, 0, result.stderr)
        values = json.loads(self.capture.read_text())
        self.assertEqual(values['_test_playbook'], 'site.yml')
        self.assertFalse(values['relay_docker_nginx_manage'])
        self.assertFalse(values['relay_reviewer_credentials_authorized'])

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

    def test_bootstrap_disposition_has_a_distinct_explicit_evidence_shape(self):
        args = ['--phase', 'stale-dispose', '--authorize-stale-disposition',
                '--stale-phase', 'apply', '--stale-head', 'a' * 40,
                '--stale-apply-shape', 'bootstrap-only', '--stale-state-hash', 'b' * 64]
        result = self.invoke(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        values = json.loads(self.capture.read_text())
        self.assertEqual(values['relay_production_operation_stale_apply_shape'], 'bootstrap-only')
        self.assertEqual(values['relay_production_operation_stale_actual_completed_phase'], '')
        for invalid in (args + ['--stale-completed-phase', 'apply'], args[:-2],
                        ['--phase', 'apply', '--stale-apply-shape', 'bootstrap-only'],
                        [v if v != 'apply' else 'activate' for v in args]):
            result = self.invoke(*invalid)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(self.capture.exists())


if __name__ == '__main__':
    unittest.main()
