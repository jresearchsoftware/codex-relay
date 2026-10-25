"""Real Linux file/lock checks; controller calls use a fixed fixture seam."""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest


spec = importlib.util.spec_from_file_location('publish_git_consumer',
    Path(__file__).parents[1] / 'scripts/publish_git_consumer.py')
publication = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publication)
OP = '12345678-1234-1234-1234-123456789abc'
REVISION = 'a' * 40
hash_bytes = lambda raw: hashlib.sha256(raw).hexdigest()


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
