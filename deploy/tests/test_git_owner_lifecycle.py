"""Git owner route uses frozen desired data and the selected target parser."""
from contextlib import contextmanager, redirect_stdout, redirect_stderr
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
sys.path.insert(0, str(Path(__file__).parent))
import owner_lifecycle as owner
from git_intent import GitIntentError
from test_lifecycle import Gate, HEAD, OLD, OPERATION

REAL_TEMPORARY = tempfile.TemporaryDirectory
REAL_RUN = owner.subprocess.run
CONFIG_SHA = 'c' * 40
TOKEN = 'synthetic_ephemeral_workflow_token'


class GitOwnerLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = REAL_TEMPORARY(prefix='relay-git-owner-', dir='/tmp')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.install = self.root / 'fixture'
        self.binding = {'repository': 'example/private-config', 'configPath': 'deploy/production.json',
                        'owner': 'Owner', 'productRepository': 'example/product'}
        self.desired = {'source': {'repository': 'https://github.com/example/product'},
            'consumer': {'owner': 'owner', 'repository': 'example/product', 'desiredValue': 'new'},
            'environment': {'namespace': 'fixture', 'localApply': {'source': 'git',
                'repository': self.binding['repository'], 'configPath': self.binding['configPath']}}}
        self.raw = json.dumps(self.desired).encode()
        self.receipt = {'config_repository': self.binding['repository'], 'config_repository_id': 17,
            'config_path': self.binding['configPath'], 'config_sha': CONFIG_SHA,
            'config_blob_sha': 'd' * 40, 'config_sha256': hashlib.sha256(self.raw).hexdigest(),
            'product_repository': 'example/product', 'product_repository_id': 18,
            'product_sha': HEAD, 'source_policy': 'accepted-main', 'workflow_run_id': 31, 'action': 'apply'}
        self.previous_manifest = {'gitConfigReceipt': copy.deepcopy(self.receipt)}
        self.source = self.root / 'accepted-source'
        self.source.mkdir()
        (self.source / 'deploy').mkdir()
        shutil.copyfile(ROOT / 'deploy/installation-contract.json', self.source / 'deploy/installation-contract.json')
        self.values = {'relay_install_root': str(self.install)}
        self.gate = Gate()
        self.primitive = []
        self.parser_inputs = []
        self.readbacks = []
        self.locks = []

        @contextmanager
        def lock(path):
            self.locks.append(path)
            try:
                yield 77
            finally:
                self.locks.remove(path)

        def parse(source, raw):
            self.parser_inputs.append((source, raw))
            return copy.deepcopy(self.desired), dict(self.values)

        @contextmanager
        def consumer_access(config, repository):
            yield SimpleNamespace(head=self.receipt['product_sha'], token=None)

        def backend(argv, **kwargs):
            if argv[0].endswith('relay-admission'):
                return SimpleNamespace(stdout=json.dumps(self.gate(*argv[1:])), returncode=0)
            self.primitive.append((argv, kwargs))
            config_path = Path(argv[argv.index('--config') + 1])
            self.assertEqual(config_path.read_bytes(), self.raw)
            self.assertNotIn(TOKEN, str(argv))
            self.assertNotIn(TOKEN, str(kwargs))
            if '--git-config-receipt' in argv:
                path = Path(argv[argv.index('--git-config-receipt') + 1])
                self.assertEqual(json.loads(path.read_bytes()), self.receipt)
                self.assertEqual(self.locks, [])
            return SimpleNamespace(stdout='', returncode=0)

        for name, value in [('git_anchor', lambda revision: (self.install, dict(self.binding), self.previous_manifest)),
            ('protected_parents', lambda path: None), ('selected_config', parse),
            ('acquire_source', lambda directory, repository, revision, **kwargs: self.source),
            ('public_main', lambda repository: self.receipt['product_sha']), ('acquire', lock),
            ('git_result', lambda *args: self.readbacks.append(args))]:
            mocked = patch.object(owner, name, value); mocked.start(); self.addCleanup(mocked.stop)
        mocked = patch.object(owner.repository_source, 'consumer_access', consumer_access)
        mocked.start(); self.addCleanup(mocked.stop)
        for mocked in [patch.object(owner.os, 'geteuid', return_value=0),
                       patch.object(owner.subprocess, 'run', side_effect=backend),
                       patch('git_intent.resolve_pair', side_effect=lambda *args: {'config_bytes': self.raw, 'receipt': self.receipt}),
                       patch.object(owner.tempfile, 'TemporaryDirectory',
                                    side_effect=lambda **kwargs: REAL_TEMPORARY(prefix='inner-', dir=self.root))]:
            mocked.start(); self.addCleanup(mocked.stop)

    def invoke(self, action='apply'):
        self.receipt['action'] = action
        with redirect_stdout(io.StringIO()) as output:
            owner.run_git(f'git:{action}:{OLD}:{CONFIG_SHA}:31', TOKEN)
        self.assertNotIn(TOKEN, output.getvalue())
        return output.getvalue()

    def test_config_only_apply_uses_new_git_bytes_and_ordinary_install_once_without_outer_lock(self):
        self.receipt['product_sha'] = OLD
        output = self.invoke()
        self.assertEqual(len(self.primitive), 1)
        argv, options = self.primitive[0]
        self.assertEqual(argv[argv.index('--phase') + 1], 'install')
        self.assertEqual(argv[argv.index('--resolved-revision') + 1], OLD)
        self.assertNotIn('--expected-installed-head', argv)
        self.assertFalse(self.gate.calls)
        self.assertEqual(self.parser_inputs, [(self.source, self.raw)])
        self.assertEqual(self.readbacks[0][2], self.receipt)
        self.assertIn('RELAY_GIT_APPLY_VERIFIED=' + OLD, output)

    def test_wrong_source_namespace_owner_or_install_root_stop_before_primitive(self):
        for modify in [lambda: self.desired['environment'].update(namespace='foreign'),
                       lambda: self.values.update(relay_install_root='/opt/foreign'),
                       lambda: self.desired['consumer'].update(owner='attacker'),
                       lambda: self.desired['source'].update(repository='https://github.com/other/product'),
                       lambda: self.desired['environment']['localApply'].update(configPath='other.json'),
                       lambda: self.desired['environment']['localApply'].update(qualificationProductSha=HEAD)]:
            desired, values = copy.deepcopy(self.desired), dict(self.values)
            modify()
            with self.assertRaises(ValueError):
                self.invoke()
            self.assertEqual(self.primitive, [])
            self.assertEqual(self.gate.calls, [])
            self.desired, self.values = desired, values

    def test_historical_target_without_git_capability_stops_before_private_config_parse(self):
        contract = self.source / 'deploy/installation-contract.json'
        contract.write_text(json.dumps({'schemaVersion': 1, 'epoch': 1, 'capabilities': ['lifecycle-v1']}))
        with self.assertRaisesRegex(ValueError, '^git-target-installation-contract-unsupported$'):
            self.invoke()
        self.assertEqual(self.parser_inputs, [])
        self.assertEqual(self.primitive, [])
        self.assertEqual(self.gate.calls, [])

    def test_missing_or_invalid_contract_has_a_precise_fixed_diagnostic_before_parse(self):
        contract = self.source / 'deploy/installation-contract.json'
        contract.unlink()
        with self.assertRaisesRegex(ValueError, '^git-target-installation-contract-missing$'):
            self.invoke()
        for raw in [b'{bad json', b'{"schemaVersion":1,"epoch":0,"capabilities":["git-desired-v1"]}',
                    b'{"schemaVersion":1,"epoch":1,"capabilities":"git-desired-v1"}',
                    b'{"schemaVersion":1,"epoch":1,"epoch":2,"capabilities":["git-desired-v1"]}']:
            contract.write_bytes(raw)
            with self.assertRaisesRegex(ValueError, '^git-target-installation-contract-invalid$'):
                self.invoke()
        contract.unlink()
        contract.symlink_to(ROOT / 'deploy/installation-contract.json')
        with self.assertRaisesRegex(ValueError, '^git-target-installation-contract-invalid$'):
            self.invoke()
        self.assertEqual(self.parser_inputs, [])
        self.assertEqual(self.primitive, [])
        self.assertEqual(self.gate.calls, [])

    def test_future_target_metadata_can_retain_git_capability_without_installed_schema_parsing(self):
        (self.source / 'deploy/installation-contract.json').write_text(json.dumps({
            'schemaVersion': 2, 'epoch': 2, 'capabilities': ['git-desired-v1', 'future-feature-v2'],
            'futureTargetMetadata': {'supportedByTarget': True}}))
        self.invoke()
        self.assertEqual(len(self.parser_inputs), 1)
        self.assertEqual(len(self.primitive), 1)

    def test_stop_closes_gate_and_resume_requires_exact_qualified_pair_then_readback(self):
        self.receipt['product_sha'] = OLD
        self.previous_manifest['gitConfigReceipt'] = copy.deepcopy(self.receipt)
        self.invoke('stop')
        self.assertEqual(self.gate.phase, 'drained')
        self.assertEqual(self.primitive, [])
        self.invoke('resume')
        self.assertEqual(self.gate.phase, 'open')
        self.assertEqual(self.primitive[0][0][self.primitive[0][0].index('--phase') + 1], 'post-check')
        self.assertEqual(len(self.readbacks), 1)

    def test_resume_rejects_changed_repository_identity_or_config_pair_before_reopening(self):
        self.gate = Gate(phase='drained', target=OLD)
        self.previous_manifest['gitConfigReceipt']['product_sha'] = OLD
        for change in [('product_repository_id', 99), ('config_repository_id', 99), ('config_sha', 'e' * 40)]:
            receipt = dict(self.receipt); self.receipt['product_sha'] = OLD
            self.receipt[change[0]] = change[1]
            with self.assertRaisesRegex(ValueError, '^resume-git-apply-required$'):
                self.invoke('resume')
            self.assertEqual(self.gate.phase, 'drained')
            self.assertEqual(self.primitive, [])
            self.receipt = receipt

    def test_resume_restores_original_qualified_product_when_public_main_moves(self):
        self.gate = Gate(phase='drained', target=OLD)
        self.previous_manifest['gitConfigReceipt']['product_sha'] = OLD
        self.receipt['product_sha'] = HEAD
        output = self.invoke('resume')
        self.assertEqual(self.gate.phase, 'open')
        argv = self.primitive[0][0]
        self.assertEqual(argv[argv.index('--resolved-revision') + 1], OLD)
        self.assertEqual(self.readbacks[0][2]['product_sha'], OLD)
        self.assertIn('RELAY_GIT_DISPATCH_PAIR=', output)
        self.assertIn('RELAY_GIT_RESUME_QUALIFIED_PAIR=', output)

    def test_main_preserves_git_error_code_and_never_logs_secret_exception_details(self):
        error_output = io.StringIO()
        with patch.object(owner, 'run_git', side_effect=GitIntentError('GIT_INTENT_WORKFLOW_MISMATCH')):
            with redirect_stderr(error_output):
                status = owner.main([f'git:apply:{OLD}:{CONFIG_SHA}:31'], io.BytesIO(TOKEN.encode()))
        self.assertEqual(status, 1)
        self.assertIn('GIT_INTENT_WORKFLOW_MISMATCH', error_output.getvalue())
        self.assertNotIn(TOKEN, error_output.getvalue())
        error_output = io.StringIO()
        with patch.object(owner, 'run_git', side_effect=OSError(TOKEN)):
            with redirect_stderr(error_output):
                self.assertEqual(owner.main([f'git:apply:{OLD}:{CONFIG_SHA}:31'], io.BytesIO(TOKEN.encode())), 1)
        self.assertNotIn(TOKEN, error_output.getvalue())

    def test_legacy_main_route_does_not_read_git_token_or_change_legacy_request(self):
        request = f'stop:{OLD}:{HEAD}'
        with patch.object(owner, 'run') as legacy, patch('git_intent.read_token') as token_reader:
            self.assertEqual(owner.main([request], io.BytesIO(b'')), 0)
        legacy.assert_called_once_with(request)
        token_reader.assert_not_called()

    def test_private_consumer_clone_uses_distinct_writer_read_token_and_revokes_before_install(self):
        private_token = 'synthetic_writer_read_token'
        self.desired['consumer']['repository'] = 'example/private-consumer'
        revoked = []
        fetches = []

        @contextmanager
        def private_access(config, repository):
            self.assertEqual(repository, 'example/private-consumer')
            try:
                yield SimpleNamespace(head=HEAD, token=private_token)
            finally:
                revoked.append(True)

        def acquire(directory, repository, head, **kwargs):
            fetches.append((repository, head, kwargs))
            return self.source

        with patch.object(owner.repository_source, 'consumer_access', private_access), \
             patch.object(owner, 'acquire_source', side_effect=acquire):
            self.invoke()
        self.assertEqual(fetches[-1], ('example/private-consumer', HEAD, {'read_token': private_token}))
        self.assertNotEqual(private_token, TOKEN)
        self.assertTrue(revoked)
        self.assertEqual(len(self.primitive), 1)
        self.assertNotIn(private_token, str(self.primitive))


class SelectedTargetConfigTests(unittest.TestCase):
    def test_parser_executes_target_schema_in_isolated_process(self):
        with REAL_TEMPORARY(prefix='relay-selected-parser-', dir='/tmp') as directory:
            source = Path(directory)
            (source / 'deploy').mkdir()
            (source / 'deploy/config.py').write_text('import json\ndef loads(raw, root):\n return {"selectedTarget":json.loads(raw),"consumer":{}}\ndef compile_inputs(c):\n return {"schema":"target-only"}\n')
            with patch.object(owner, 'loads', side_effect=AssertionError('installed schema used')):
                config, values = owner.selected_config(source, b'{"newTargetField":true}')
            self.assertEqual(config, {'selectedTarget': {'newTargetField': True}, 'consumer': {}})
            self.assertEqual(values, {'schema': 'target-only'})

    def test_anchor_reads_source_locator_without_desired_snapshot_or_consumer_precondition(self):
        install = Path('/opt/fixture')
        release = install / 'releases' / OLD
        source = release / 'reviewed-source'
        binding = {'repository': 'example/private', 'configPath': 'deploy/config.json',
                   'owner': 'Owner', 'productRepository': 'example/product', 'qualificationProductSha': HEAD}
        records = {source / '.relay-source.json': {'revision': OLD, 'tree': 'f' * 40},
            release / 'artifact-manifest.json': {'commit': OLD, 'resolvedRevision': OLD, 'installedRevision': OLD, 'gitTree': 'f' * 40},
            Path('/etc/fixture/deployment-source.json'): binding}
        reads = []

        def read(path, *args, **kwargs):
            reads.append(path)
            return json.dumps(records[path]).encode(), None

        with patch.object(owner, 'ROOT', source), patch.object(owner, 'read_protected', side_effect=read), \
             patch.object(owner, 'protected_parents'), patch.object(Path, 'lstat', return_value=SimpleNamespace(st_mode=stat.S_IFLNK, st_uid=0)), \
             patch.object(owner.os, 'readlink', return_value=str(release)):
            actual_install, actual_binding, _ = owner.git_anchor(OLD)
        self.assertEqual(actual_install, install)
        self.assertEqual(actual_binding, binding)
        self.assertFalse(any(path.name in ('deployment-config.json', 'consumer.json') for path in reads))

    def test_readback_normalizes_with_target_consumer_schema_and_rejects_effective_drift(self):
        with REAL_TEMPORARY(prefix='relay-git-readback-', dir='/tmp') as directory:
            install = Path(directory) / 'fixture'
            release = install / 'releases' / HEAD
            source = release / 'reviewed-source'
            for name in ('consumer', 'contracts'):
                shutil.copytree(ROOT / name, source / name, copy_function=shutil.copyfile,
                                ignore=shutil.ignore_patterns('__pycache__'))
            (source / 'reviewer/src').mkdir(parents=True)
            shutil.copyfile(ROOT / 'reviewer/src/executable-cr-v2.json',
                            source / 'reviewer/src/executable-cr-v2.json')
            consumer = json.loads((ROOT / 'consumer/fixtures/example.json').read_bytes())
            consumer['defaultProfile'].pop('effort', None)
            actual = copy.deepcopy(consumer)
            actual['defaultProfile']['effort'] = 'xhigh'
            desired = {'consumer': consumer}
            raw = json.dumps(desired).encode()
            receipt = {'config_sha': CONFIG_SHA, 'product_sha': HEAD,
                'product_repository': 'example/product', 'product_repository_id': 1,
                'config_repository': 'example/private', 'config_repository_id': 2,
                'config_blob_sha': 'e' * 40, 'config_path': 'prod/relay.json',
                'config_sha256': hashlib.sha256(raw).hexdigest(), 'workflow_run_id': 31, 'action': 'apply'}
            manifest = {'commit': HEAD, 'resolvedRevision': HEAD, 'installedRevision': HEAD,
                'gitTree': 'f' * 40, 'gitConfigReceipt': copy.deepcopy(receipt),
                'deploymentConfigSha256': hashlib.sha256(raw).hexdigest()}
            records = {source / '.relay-source.json': {'revision': HEAD, 'tree': 'f' * 40},
                release / 'artifact-manifest.json': manifest, release / 'deployment-config.json': raw,
                Path('/etc/fixture/consumer.json'): actual}

            def read(path, *args, **kwargs):
                value = records[path]
                return value if isinstance(value, bytes) else json.dumps(value).encode(), None

            with patch.object(owner, 'read_protected', side_effect=read), patch.object(owner, 'protected_parents'), \
                 patch.object(Path, 'lstat', return_value=SimpleNamespace(st_mode=stat.S_IFLNK, st_uid=0)), \
                 patch.object(owner.os, 'readlink', return_value=str(release)), \
                 patch.object(owner, 'selected_config', return_value=(desired, {})):
                owner.git_result(install, HEAD, receipt, desired)
                owner.git_result(install, HEAD, {**receipt, 'workflow_run_id': 32}, desired)
                self.assertEqual(manifest['gitConfigReceipt']['workflow_run_id'], 31)
                actual['defaultProfile']['effort'] = 'low'
                with self.assertRaisesRegex(ValueError, '^git-consumer-readback-mismatch$'):
                    owner.git_result(install, HEAD, receipt, desired)
                actual['defaultProfile']['effort'] = 'xhigh'
                manifest['deploymentConfigSha256'] = '0' * 64
                with self.assertRaisesRegex(ValueError, '^git-pair-readback-mismatch$'):
                    owner.git_result(install, HEAD, receipt, desired)


if __name__ == '__main__':
    unittest.main()
