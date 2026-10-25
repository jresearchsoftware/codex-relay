"""Real Linux file/lock and Node consumer-transition checks."""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest


spec = importlib.util.spec_from_file_location('publish_git_consumer',
    Path(__file__).parents[1] / 'scripts/publish_git_consumer.py')
publication = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publication)
OP = '12345678-1234-1234-1234-123456789abc'
REVISION = 'a' * 40
hash_bytes = lambda raw: hashlib.sha256(raw).hexdigest()
ROOT = Path(__file__).resolve().parents[3]


class PublishConsumerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='relay-consumer-publication-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / 'source'
        self.config = self.root / 'config'
        self.claims = self.root / 'claims'
        for directory in (self.source / 'controller/src', self.source / 'consumer', self.config, self.claims):
            directory.mkdir(parents=True, exist_ok=True)
        (self.source / 'controller/src/admission-cli.mjs').write_text('// fixture')
        (self.source / 'consumer/consumer-config.mjs').write_text('// fixture')
        (self.source / '.relay-source.json').write_text(json.dumps({'revision': REVISION}))
        self.old = b'{"accepted":"old"}'
        self.new = b'{"accepted":"new"}'
        self.consumer = self.config / 'consumer.json'
        self.consumer.write_bytes(self.old)
        self.desired = self.config / ('.consumer-' + OP + '.desired.json')
        self.desired.write_bytes(self.new)
        self.backup = self.config / ('consumer-before-' + OP + '.json')
        self.gate = {'operationId': OP, 'target': REVISION, 'phase': 'applying', 'consumerDigest': hash_bytes(self.old)}
        (self.claims / 'admission-v1.json').write_text(json.dumps(self.gate))
        (self.claims / 'admission-pool-v1.json').write_text(json.dumps(self.gate))
        self.calls = []
        self.fail_check = False
        self.fail_transition = False

    def execute(self, argv, env):
        self.calls.append(argv)
        self.assertEqual(env['RELAY_CONSUMER_CONFIG'], str(self.consumer))
        self.assertEqual(set(env), {'PATH', 'LANG', 'LC_ALL', 'RELAY_CONSUMER_CONFIG', 'RELAY_REPOSITORY'})
        # Every controller/validator operation observes one continuous lock.
        with (self.claims / 'publication-v2.lock').open('rb') as locked:
            with self.assertRaises(BlockingIOError):
                fcntl.flock(locked.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        if '--input-type=module' in argv:
            return {'digest': hash_bytes(Path(argv[-1]).read_bytes())}
        if 'consumer-transition-check' in argv:
            if self.fail_check:
                raise publication.ConsumerPublicationError('CONSUMER_PUBLICATION_CONTROLLER_FAILED')
            self.assertEqual(self.consumer.read_bytes(), self.old)
            return {'operationId': OP, 'target': REVISION, 'previousDigest': hash_bytes(self.old)}
        self.assertIn('consumer-transition', argv)
        self.assertEqual(argv[argv.index('--previous-digest') + 1], hash_bytes(self.old))
        self.assertEqual(self.consumer.read_bytes(), self.new)
        self.assertEqual(self.backup.read_bytes(), self.old)
        if self.fail_transition:
            raise publication.ConsumerPublicationError('CONSUMER_PUBLICATION_CONTROLLER_FAILED')
        self.gate['consumerDigest'] = hash_bytes(self.new)
        for name in ('admission-v1.json', 'admission-pool-v1.json'):
            (self.claims / name).write_text(json.dumps(self.gate))
        return {'operationId': OP, 'target': REVISION, 'phase': 'applying', 'consumerDigest': hash_bytes(self.new)}

    def publish(self, **changes):
        arguments = {'source': self.source, 'config_root': self.config, 'desired': self.desired,
            'claim_root': self.claims, 'repository': 'example/product', 'operation': OP,
            'revision': REVISION, 'owner_uid': os.geteuid(), 'boundary': self.root, 'execute': self.execute}
        arguments.update(changes)
        return publication.publish(**arguments)

    def test_atomic_publish_keeps_old_config_and_lock_across_both_controller_calls(self):
        result = self.publish()
        self.assertEqual(result['status'], 'PUBLISHED')
        self.assertEqual(self.consumer.read_bytes(), self.new)
        self.assertEqual(self.backup.read_bytes(), self.old)
        self.assertEqual(self.backup.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.consumer.stat().st_mode & 0o777, 0o644)
        self.assertEqual(len([call for call in self.calls if 'consumer-transition-check' in call]), 1)
        self.assertEqual(len([call for call in self.calls if 'consumer-transition' in call]), 1)

    @unittest.skipUnless(sys.platform == 'linux' and os.geteuid() == 0, 'root Linux identity transition required')
    def test_private_umask_keeps_public_consumer_and_serial_snapshot_readable_but_backup_private(self):
        # Only this disposable fixture is made traversable for an ordinary UID.
        self.root.chmod(0o755)
        self.config.chmod(0o755)
        (self.config / 'serial-pool-compat-v1.json').write_text(json.dumps({
            'target': {'consumerDigest': hash_bytes(self.old)}}))
        previous = os.umask(0o077)
        try:
            result = self.publish()
        finally:
            os.umask(previous)
        self.assertEqual(result['status'], 'PUBLISHED')
        snapshot = self.config / 'serial-pool-target-consumer-v1.json'
        program = ('from pathlib import Path;import sys;'
            'assert Path(sys.argv[1]).read_bytes()==b\'{"accepted":"new"}\';'
            'assert Path(sys.argv[2]).read_bytes()==b\'{"accepted":"old"}\';'
            '\ntry:Path(sys.argv[3]).read_bytes()'
            '\nexcept PermissionError:pass'
            '\nelse:raise AssertionError("private backup readable by runtime UID")')
        checked = subprocess.run(['/usr/bin/python3', '-I', '-c', program,
            str(self.consumer), str(snapshot), str(self.backup)], capture_output=True, text=True,
            user=65534, group=65534, extra_groups=[], timeout=30)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        for path, mode in [(self.consumer, 0o644), (snapshot, 0o644), (self.backup, 0o600)]:
            info = path.stat()
            self.assertEqual((info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode), info.st_nlink), (0, 0, mode, 1))

    @unittest.skipUnless(sys.platform == 'linux' and os.geteuid() == 0, 'root Linux identity transition required')
    def test_private_umask_actual_node_transition_publishes_a_runtime_readable_consumer(self):
        with tempfile.TemporaryDirectory(prefix='relay-consumer-native-', dir='/run') as temporary:
            root = Path(temporary)
            root.chmod(0o755)
            source, config, claims = root / 'source', root / 'config', root / 'claims'
            for component in ['consumer', 'controller', 'contracts', 'runtime', 'reviewer']:
                shutil.copytree(ROOT / component, source / component,
                    ignore=shutil.ignore_patterns('__pycache__', 'node_modules', 'target'))
            for path in [source, *source.rglob('*')]:
                path.chmod(0o755 if path.is_dir() else 0o644)
            (source / '.relay-source.json').write_text(json.dumps({'revision': REVISION}))
            config.mkdir(mode=0o755)
            claims.mkdir(mode=0o700)
            consumer = config / 'consumer.json'
            old = json.loads((ROOT / 'deploy/example.json').read_text())['consumer']
            old['paths']['claimRoot'] = str(claims)
            old['defaultProfile']['effort'] = 'xhigh'
            consumer.write_text(json.dumps(old))
            consumer.chmod(0o644)
            new = json.loads(json.dumps(old))
            new['defaultProfile']['effort'] = 'medium'
            desired = config / ('.consumer-' + OP + '.desired.json')
            desired.write_text(json.dumps(new))
            desired.chmod(0o600)
            lock = claims / 'publication-v2.lock'
            lock.write_bytes(b'')
            lock.chmod(0o600)
            cli = source / 'controller/src/admission-cli.mjs'
            repository = old.get('repository', old.get('repositories', [None])[0])
            env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'RELAY_CONSUMER_CONFIG': str(consumer),
                   'RELAY_REPOSITORY': repository}

            def admission(*arguments):
                result = subprocess.run(['/usr/bin/node', str(cli), *arguments], env=env,
                    capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                return json.loads(result.stdout)

            initialized = admission('initialize')
            admission('quiesce', '--operation', OP, '--target', REVISION)
            self.assertTrue(admission('drain-check', '--operation', OP)['drained'])
            admission('phase', '--operation', OP, '--phase', 'applying')

            def actual_locked_execute(argv, environment):
                with lock.open('rb') as stream:
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return publication._execute(argv, environment)

            previous = os.umask(0o077)
            try:
                result = publication.publish(source, config, desired, claims, repository, OP, REVISION,
                    execute=actual_locked_execute)
            finally:
                os.umask(previous)
            self.assertEqual(result['status'], 'PUBLISHED')
            observed = admission('status', '--operation', OP)
            self.assertEqual(observed['consumerDigest'], result['consumerDigest'])
            self.assertNotEqual(observed['consumerDigest'], initialized['consumerDigest'])
            self.assertEqual((observed['operationId'], observed['target'], observed['phase']), (OP, REVISION, 'applying'))
            self.assertEqual(observed['active'], [])
            self.assertEqual(observed['unknown'], [])
            backup = config / ('consumer-before-' + OP + '.json')
            self.assertEqual(json.loads(backup.read_bytes()), old)
            program = ('import{pathToFileURL}from"node:url";import{readFileSync}from"node:fs";'
                'const m=await import(pathToFileURL(process.argv[1]));'
                'const c=m.loadConsumer(process.argv[2]);let denied=false;'
                'try{readFileSync(process.argv[3])}catch(e){if(e.code==="EACCES")denied=true;else throw e}'
                'if(!denied)throw Error("private backup readable by runtime UID");'
                'console.log(JSON.stringify({effort:c.defaultProfile.effort,digest:m.consumerDigest(c)}));')
            runtime = subprocess.run(['/usr/bin/node', '--input-type=module', '-e', program,
                str(source / 'consumer/consumer-config.mjs'), str(consumer), str(backup)],
                capture_output=True, text=True, env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'},
                user=65534, group=65534, extra_groups=[], timeout=30)
            self.assertEqual(runtime.returncode, 0, runtime.stderr)
            self.assertEqual(json.loads(runtime.stdout), {'effort': 'medium', 'digest': observed['consumerDigest']})
            self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(consumer.stat().st_mode), 0o644)

    def test_failed_precheck_preserves_actual_config_and_does_not_create_backup(self):
        self.fail_check = True
        with self.assertRaises(publication.ConsumerPublicationError):
            self.publish()
        self.assertEqual(self.consumer.read_bytes(), self.old)
        self.assertFalse(self.backup.exists())
        self.assertFalse(any('consumer-transition' in call for call in self.calls))

    def test_same_consumer_digest_does_not_require_pending_manual_outcomes(self):
        self.fail_check = True
        self.desired.write_bytes(self.old)
        self.assertEqual(self.publish()['status'], 'UNCHANGED')
        self.assertFalse(any('consumer-transition-check' in call or 'consumer-transition' in call for call in self.calls))
        self.assertFalse(self.backup.exists())
        self.assertEqual(self.consumer.read_bytes(), self.old)

    def test_semantic_noop_with_different_json_bytes_preserves_original_binding(self):
        self.desired.write_bytes(b'{"accepted": "old"}\n')
        self.fail_check = True
        original_execute = self.execute

        def semantic_execute(argv, env):
            value = original_execute(argv, env)
            if '--input-type=module' in argv:
                normalized = json.dumps(json.loads(Path(argv[-1]).read_bytes()), sort_keys=True).encode()
                return {'digest': hash_bytes(normalized)}
            return value

        self.assertEqual(self.publish(execute=semantic_execute)['status'], 'UNCHANGED')
        self.assertEqual(self.consumer.read_bytes(), self.old)
        self.assertFalse(self.backup.exists())

    def test_failed_transition_keeps_known_config_and_original_backup_for_exact_recovery(self):
        self.fail_transition = True
        with self.assertRaisesRegex(publication.ConsumerPublicationError,
                                    '^CONSUMER_PUBLICATION_TRANSITION_REQUIRES_RECOVERY$'):
            self.publish()
        self.assertEqual(self.consumer.read_bytes(), self.new)
        self.assertEqual(self.backup.read_bytes(), self.old)
        self.fail_transition = False
        self.calls.clear()
        self.assertEqual(self.publish()['status'], 'PUBLISHED')
        self.assertFalse(any('consumer-transition-check' in call for call in self.calls))

    def test_serial_snapshot_is_frozen_at_original_receipt_target_and_never_overwritten(self):
        (self.config / 'serial-pool-compat-v1.json').write_text(json.dumps({
            'target': {'consumerDigest': hash_bytes(self.old)}}))
        self.publish()
        snapshot = self.config / 'serial-pool-target-consumer-v1.json'
        self.assertEqual(snapshot.read_bytes(), self.old)
        before = snapshot.stat().st_ino
        self.publish()
        self.assertEqual(snapshot.stat().st_ino, before)
        snapshot.write_bytes(b'{"tampered":true}')
        with self.assertRaisesRegex(publication.ConsumerPublicationError,
                                    '^CONSUMER_PUBLICATION_SERIAL_TARGET_CHANGED$'):
            self.publish()

    def test_symlinks_hardlinks_and_unprotected_parents_are_rejected_before_execution(self):
        for kind in ('symlink', 'hardlink', 'writable-parent'):
            with self.subTest(kind=kind):
                if kind == 'symlink':
                    self.desired.unlink(); self.desired.symlink_to(self.consumer)
                elif kind == 'hardlink':
                    self.desired.unlink(); os.link(self.consumer, self.desired)
                else:
                    self.desired.unlink(); self.desired.write_bytes(self.new)
                    self.config.chmod(0o777)
                with self.assertRaises(publication.ConsumerPublicationError):
                    self.publish()
                self.assertEqual(self.calls, [])
        self.config.chmod(0o755)

    def test_arbitrary_desired_path_and_wrong_source_revision_rejected(self):
        with self.assertRaisesRegex(publication.ConsumerPublicationError,
                                    '^CONSUMER_PUBLICATION_DESIRED_PATH_INVALID$'):
            self.publish(desired=self.root / 'outside.json')
        (self.source / '.relay-source.json').write_text(json.dumps({'revision': 'b' * 40}))
        with self.assertRaisesRegex(publication.ConsumerPublicationError,
                                    '^CONSUMER_PUBLICATION_SOURCE_MISMATCH$'):
            self.publish()


if __name__ == '__main__':
    unittest.main()
