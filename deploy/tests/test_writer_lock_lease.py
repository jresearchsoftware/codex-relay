"""Root/Linux kernel proof for a bounded installer-held Writer flock."""
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import selectors
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / 'deploy/writer_lock_lease.py'
spec = importlib.util.spec_from_file_location('writer_lock_lease_test_module', MODULE)
lease = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lease)
OP = '12345678-1234-1234-1234-123456789abc'
TARGET, DIGEST = 'a' * 40, 'b' * 64


@unittest.skipUnless(sys.platform == 'linux' and os.geteuid() == 0,
                     'actual root Linux process and flock proof required')
class WriterLockLeaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='relay-writer-lease-', dir='/run')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.lock, self.receipt = self.root / 'publication-v2.lock', self.root / 'lease.json'
        self.lock.write_bytes(b'')
        self.lock.chmod(0o600)

    @staticmethod
    def stop(process):
        if process.poll() is None:
            process.stdin.close()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        for stream in [process.stdout, process.stderr]:
            stream.close()

    def holder(self, *, lock=None, receipt=None, operation=OP, target=TARGET, digest=DIGEST):
        process = subprocess.Popen([sys.executable, '-I', str(MODULE), '--hold',
            str(lock or self.lock), str(receipt or self.receipt), operation, target, digest],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.stop, process)
        with selectors.DefaultSelector() as events:
            events.register(process.stdout, selectors.EVENT_READ)
            self.assertTrue(events.select(5), 'holder readiness timed out')
            self.assertEqual(process.stdout.readline(), 'WRITER_LOCK_READY\n')
        return process

    def rewrite(self, mutate):
        value = json.loads(self.receipt.read_bytes())
        mutate(value)
        self.receipt.write_text(json.dumps(value))

    def test_live_kernel_holder_blocks_other_writers_and_releases_only_its_temporary_receipt(self):
        before = self.lock.stat()
        process = self.holder()
        value = lease.verify(self.receipt, self.lock, operation=OP, target=TARGET, consumer_digest=DIGEST)
        self.assertEqual(value['pid'], process.pid)
        self.assertEqual((value['lockDev'], value['lockIno']), (before.st_dev, before.st_ino))
        self.assertEqual(stat.S_IMODE(self.receipt.stat().st_mode), 0o600)
        with self.lock.open('rb') as stream:
            with self.assertRaises(BlockingIOError):
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        process.stdin.close()
        self.assertEqual(process.wait(timeout=5), 0)
        self.assertFalse(self.receipt.exists())
        self.assertEqual(self.lock.stat().st_ino, before.st_ino)
        with self.lock.open('rb') as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_foreign_binding_pid_start_and_forged_unlocked_descriptor_are_not_proof(self):
        self.holder()
        for kwargs in [{'operation': '22345678-1234-1234-1234-123456789abc'},
                       {'target': 'c' * 40}, {'consumer_digest': 'c' * 64}]:
            with self.assertRaises(ValueError):
                lease.verify(self.receipt, self.lock, **kwargs)
        original = self.receipt.read_bytes()
        self.rewrite(lambda value: value.update(startTicks=value['startTicks'] + 1))
        with self.assertRaises(ValueError):
            lease.verify(self.receipt, self.lock)
        self.receipt.write_bytes(original)
        # A root-written JSON record with a real descriptor still has no flock.
        with self.lock.open('rb') as stream:
            self.rewrite(lambda value: value.update(pid=os.getpid(), startTicks=lease._start(os.getpid()),
                                                   fd=stream.fileno()))
            with self.assertRaises(ValueError):
                lease.verify(self.receipt, self.lock)
        self.receipt.write_bytes(original)

    def test_ordinary_root_owned_readable_lock_needs_no_mode_or_group_tightening(self):
        self.lock.chmod(0o644)
        os.chown(self.lock, 0, 1)
        before = self.lock.stat()
        self.holder()
        value = lease.verify(self.receipt, self.lock)
        self.assertEqual((value['lockMode'], value['lockGid']), (0o644, 1))
        self.assertEqual((self.lock.stat().st_ino, self.lock.stat().st_mode, self.lock.stat().st_gid),
                         (before.st_ino, before.st_mode, before.st_gid))
        self.lock.chmod(0o600)
        with self.assertRaises(ValueError):
            lease.verify(self.receipt, self.lock)

    def test_group_or_other_writable_lock_is_rejected_without_repair(self):
        for mode in [0o620, 0o602, 0o666]:
            self.lock.chmod(mode)
            before = self.lock.stat()
            result = subprocess.run([sys.executable, '-I', str(MODULE), '--hold',
                str(self.lock), str(self.receipt), OP, TARGET, DIGEST], input='',
                capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 1)
            self.assertFalse(self.receipt.exists())
            self.assertEqual((self.lock.stat().st_ino, self.lock.stat().st_mode), (before.st_ino, before.st_mode))
    def test_replaced_lock_dead_holder_and_unsafe_receipt_fail_closed(self):
        process = self.holder()
        original = self.receipt.read_bytes()
        self.receipt.chmod(0o644)
        with self.assertRaises(ValueError):
            lease.verify(self.receipt, self.lock)
        self.receipt.chmod(0o600)
        self.lock.rename(self.root / 'original.lock')
        self.lock.write_bytes(b'')
        self.lock.chmod(0o600)
        with self.assertRaises(ValueError):
            lease.verify(self.receipt, self.lock)
        self.lock.unlink()
        (self.root / 'original.lock').rename(self.lock)
        process.kill()
        process.wait(timeout=5)
        with self.assertRaises((ValueError, OSError)):
            lease.verify(self.receipt, self.lock)
        self.assertEqual(self.receipt.read_bytes(), original)

    def test_duplicate_malformed_unreadable_or_aliased_receipts_and_writable_parents_are_rejected(self):
        self.holder()
        original = self.receipt.read_bytes()
        for raw in [b'{}', b'[]', b'not json', b'x' * 4097,
                    original.rstrip()[:-1] + b',"version":1}\n']:
            self.receipt.write_bytes(raw)
            with self.assertRaises(ValueError):
                lease.verify(self.receipt, self.lock)
        self.receipt.write_bytes(original)
        for field, value in [('pid', True), ('fd', -1), ('target', {}), ('consumerDigest', None)]:
            self.rewrite(lambda data: data.update({field: value}))
            with self.assertRaises(ValueError):
                lease.verify(self.receipt, self.lock)
            self.receipt.write_bytes(original)
        alias = self.root / 'alias.json'
        alias.symlink_to(self.receipt)
        with self.assertRaises(ValueError):
            lease.verify(alias, self.lock)
        alias.unlink()
        os.link(self.receipt, alias)
        with self.assertRaises(ValueError):
            lease.verify(self.receipt, self.lock)
        alias.unlink()
        self.root.chmod(0o777)
        try:
            with self.assertRaises(ValueError):
                lease.verify(self.receipt, self.lock)
        finally:
            self.root.chmod(0o700)
        missing = self.root / 'missing.json'
        with self.assertRaises(OSError):
            lease.verify(missing, self.lock)

    def test_existing_lock_is_required_and_busy_holder_never_creates_a_second_receipt(self):
        with self.assertRaises(OSError):
            lease.hold(self.root / 'missing.lock', self.receipt, OP, TARGET, DIGEST)
        self.holder()
        other = self.root / 'second.json'
        result = subprocess.run([sys.executable, '-I', str(MODULE), '--hold',
            str(self.lock), str(other), OP, TARGET, DIGEST], input='', capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, '')
        self.assertEqual(result.stderr, 'WRITER_LOCK_LEASE_UNPROVEN\n')
        self.assertFalse(other.exists())

    def test_holder_cleanup_does_not_unlink_a_replaced_lease(self):
        process = self.holder()
        self.receipt.rename(self.root / 'original-receipt.json')
        self.receipt.write_text('replacement')
        self.receipt.chmod(0o600)
        process.stdin.close()
        self.assertEqual(process.wait(timeout=5), 0)
        self.assertEqual(self.receipt.read_text(), 'replacement')

    def admission_source(self):
        source = self.root / 'candidate'
        (source / 'controller/src').mkdir(parents=True)
        (source / '.relay-source.json').write_text(json.dumps({'revision': TARGET}))
        (source / 'controller/src/admission-cli.mjs').write_text(
            'let input="";for await(const b of process.stdin)input+=b;'
            'console.log(JSON.stringify({args:process.argv.slice(2),input,'
            'consumer:process.env.RELAY_CONSUMER_CONFIG,repository:process.env.RELAY_REPOSITORY,'
            'privateEnvironmentPresent:process.env.PRIVATE_VALUE!==undefined}));')
        consumer = self.root / 'consumer.json'
        consumer.write_text(json.dumps({'repository': 'example/sample', 'paths': {'claimRoot': str(self.root)}}))
        return source, consumer

    def test_exec_admission_reuses_actual_flock_with_snapshot_stdin_and_clean_fixed_environment(self):
        self.holder()
        source, consumer = self.admission_source()
        result = subprocess.run([sys.executable, '-I', str(MODULE), '--exec-admission', str(self.receipt),
            str(source), str(consumer), 'example/sample', 'snapshot', '--operation', OP],
            input='{"services":"private synthetic input"}', text=True, capture_output=True, timeout=10,
            env={**os.environ, 'PRIVATE_VALUE': 'never copy this environment'})
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(value['args'], ['snapshot', '--operation', OP])
        self.assertEqual(value['input'], '{"services":"private synthetic input"}')
        self.assertFalse(value['privateEnvironmentPresent'])
        self.assertEqual(value['consumer'], str(consumer))
        self.assertEqual(value['repository'], 'example/sample')
        lease.verify(self.receipt, self.lock)

    def test_exec_admission_refuses_drain_unrelated_operations_and_foreign_source_boundaries(self):
        self.holder()
        source, consumer = self.admission_source()
        for args in [['drain'], ['unknown-command'], ['snapshot', '--operation',
                     '22345678-1234-1234-1234-123456789abc']]:
            result = subprocess.run([sys.executable, '-I', str(MODULE), '--exec-admission', str(self.receipt),
                str(source), str(consumer), 'example/sample', *args], input='', text=True,
                capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, '')
            self.assertEqual(result.stderr, 'WRITER_LOCK_LEASE_UNPROVEN\n')
        (source / '.relay-source.json').write_text(json.dumps({'revision': 'c' * 40}))
        result = subprocess.run([sys.executable, '-I', str(MODULE), '--exec-admission', str(self.receipt),
            str(source), str(consumer), 'example/sample', 'status'], input='', text=True,
            capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 1)
        (source / '.relay-source.json').write_text(json.dumps({'revision': TARGET}))
        source.chmod(0o777)
        result = subprocess.run([sys.executable, '-I', str(MODULE), '--exec-admission', str(self.receipt),
            str(source), str(consumer), 'example/sample', 'status'], input='', text=True,
            capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 1)

    def test_real_consumer_publication_retains_default_locking_and_reuses_only_verified_live_lease(self):
        history_path = ROOT / 'deploy/ansible/tests/test_git_consumer_history_recovery.py'
        history_spec = importlib.util.spec_from_file_location('lease_history_fixture', history_path)
        history = importlib.util.module_from_spec(history_spec)
        history_spec.loader.exec_module(history)
        for reuse in [False, True]:
            with self.subTest(reuse=reuse):
                fixture = history.GitConsumerHistoryRecoveryTests(
                    'test_candidate_publishes_completed_history_without_rebinding_attempts_or_journals')
                fixture.setUp()
                self.addCleanup(fixture.doCleanups)
                fixture.seed()
                before = fixture.history_snapshot()
                receipt = fixture.root / 'writer-lease.json'
                if reuse:
                    (fixture.source / 'deploy').mkdir()
                    shutil.copyfile(MODULE, fixture.source / 'deploy/writer_lock_lease.py')
                    self.holder(lock=fixture.lock, receipt=receipt, target=history.REVISION,
                                digest=fixture.initial['consumerDigest'])
                    original = receipt.read_bytes()
                    wrong = json.loads(original)
                    wrong['operationId'] = '22345678-1234-1234-1234-123456789abc'
                    receipt.write_text(json.dumps(wrong))
                    with self.assertRaisesRegex(history.publication.ConsumerPublicationError,
                                                '^CONSUMER_PUBLICATION_WRITER_LEASE_UNPROVEN$'):
                        history.publication.publish(fixture.source, fixture.config, fixture.desired,
                            fixture.claims, fixture.repository, history.OP, history.REVISION,
                            execute=fixture.execute, writer_lock_lease=receipt)
                    self.assertEqual(fixture.consumer.read_bytes(), fixture.old)
                    self.assertFalse(fixture.backup.exists())
                    receipt.write_bytes(original)
                result = history.publication.publish(fixture.source, fixture.config, fixture.desired,
                    fixture.claims, fixture.repository, history.OP, history.REVISION,
                    execute=fixture.execute, writer_lock_lease=receipt if reuse else None)
                self.assertEqual(result['status'], 'PUBLISHED')
                self.assertEqual(fixture.consumer.read_bytes(), fixture.new)
                self.assertEqual(fixture.history_snapshot(), before)
                if reuse:
                    lease.verify(receipt, fixture.lock)
                    with fixture.lock.open('rb') as stream:
                        with self.assertRaises(BlockingIOError):
                            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_same_uuid_postrename_recovery_authenticates_old_lease_backup_and_applying_gate(self):
        history_path = ROOT / 'deploy/ansible/tests/test_git_consumer_history_recovery.py'
        history_spec = importlib.util.spec_from_file_location('lease_postrename_fixture', history_path)
        history = importlib.util.module_from_spec(history_spec); history_spec.loader.exec_module(history)
        fixture = history.GitConsumerHistoryRecoveryTests(
            'test_real_same_uuid_recovery_after_rename_preserves_backup_and_original_history')
        fixture.setUp(); self.addCleanup(fixture.doCleanups)
        fixture.seed()
        (fixture.source / 'deploy').mkdir()
        shutil.copyfile(MODULE, fixture.source / 'deploy/writer_lock_lease.py')
        receipt = fixture.root / 'writer-lease.json'
        self.holder(lock=fixture.lock, receipt=receipt, target=history.REVISION,
                    digest=fixture.initial['consumerDigest'])
        before, gate_before = fixture.history_snapshot(), fixture.gate.read_bytes()

        def interrupted(argv, environment):
            if 'consumer-transition' in argv:
                self.assertEqual(fixture.consumer.read_bytes(), fixture.new)
                self.assertEqual(fixture.backup.read_bytes(), fixture.old)
                self.assertEqual(fixture.gate.read_bytes(), gate_before)
                raise history.publication.ConsumerPublicationError('CONSUMER_PUBLICATION_CONTROLLER_FAILED')
            return fixture.execute(argv, environment)

        def publish(execute=fixture.execute):
            return history.publication.publish(fixture.source, fixture.config, fixture.desired,
                fixture.claims, fixture.repository, history.OP, history.REVISION,
                execute=execute, writer_lock_lease=receipt)

        with self.assertRaisesRegex(history.publication.ConsumerPublicationError,
                                    '^CONSUMER_PUBLICATION_TRANSITION_REQUIRES_RECOVERY$'):
            publish(interrupted)
        backup_inode = fixture.backup.stat().st_ino
        drained = json.loads(gate_before); drained['phase'] = 'drained'
        fixture.gate.write_text(json.dumps(drained))
        with self.assertRaisesRegex(history.publication.ConsumerPublicationError,
                                    '^CONSUMER_PUBLICATION_WRITER_LEASE_DIGEST_CHANGED$'):
            publish()
        self.assertEqual(json.loads(fixture.gate.read_bytes()), drained)
        fixture.gate.write_bytes(gate_before)
        result = publish()
        self.assertEqual((result['status'], result['consumerDigest']), ('PUBLISHED', fixture.expected_new_digest))
        replay = publish()
        self.assertEqual((replay['status'], replay['consumerDigest']), ('UNCHANGED', fixture.expected_new_digest))
        self.assertEqual((fixture.backup.stat().st_ino, fixture.backup.read_bytes()), (backup_inode, fixture.old))
        self.assertEqual(fixture.history_snapshot(), before)
        lease.verify(receipt, fixture.lock, operation=history.OP, target=history.REVISION,
                     consumer_digest=fixture.initial['consumerDigest'])


if __name__ == '__main__':
    unittest.main()
