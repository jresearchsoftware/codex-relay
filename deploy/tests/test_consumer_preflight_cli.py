"""Real root/private-namespace history observation with a drifted live consumer."""
import hashlib
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
CLI = 'controller/src/consumer-preflight-cli.mjs'
NODE = '/usr/bin/node'
TARGET = 'e' * 40
OP = '12345678-1234-1234-1234-123456789abc'


def protect_fixture_source(root):
    """Materialize the protected artifact contract, independent of checkout modes."""
    assert not root.is_symlink()
    for directory, dirs, files in os.walk(root, followlinks=False):
        Path(directory).chmod(0o755)
        dirs[:] = [name for name in dirs if not (Path(directory) / name).is_symlink()]
        for name in files:
            path = Path(directory) / name
            info = path.lstat()
            if stat.S_ISREG(info.st_mode):
                path.chmod(0o755 if info.st_mode & 0o111 else 0o644)

@unittest.skipUnless(sys.platform == 'linux', 'Linux file modes and symlinks required')
class FixtureArtifactProtectionTests(unittest.TestCase):
    def test_archive_modes_are_normalized_only_in_copied_artifact_without_following_links(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            checkout, external = root / 'checkout', root / 'external'
            checkout.mkdir(); checkout.chmod(0o775)
            external.mkdir(); external.chmod(0o775)
            for path, mode in [(checkout / 'module.mjs', 0o664), (checkout / 'entrypoint', 0o775),
                               (external / 'private-input', 0o664)]:
                path.write_text('synthetic mode fixture'); path.chmod(mode)
            (checkout / 'external-file').symlink_to(external / 'private-input')
            (checkout / 'external-directory').symlink_to(external, target_is_directory=True)
            original = {path: (path.lstat().st_mode, path.lstat().st_ino)
                        for path in [checkout, external, *checkout.iterdir(), external / 'private-input']}
            artifact = root / 'protected-copy'
            shutil.copytree(checkout, artifact, symlinks=True)
            protect_fixture_source(artifact)
            self.assertEqual(stat.S_IMODE(artifact.stat().st_mode), 0o755)
            self.assertEqual(stat.S_IMODE((artifact / 'module.mjs').stat().st_mode), 0o644)
            self.assertEqual(stat.S_IMODE((artifact / 'entrypoint').stat().st_mode), 0o755)
            self.assertTrue((artifact / 'external-file').is_symlink())
            self.assertTrue((artifact / 'external-directory').is_symlink())
            self.assertEqual({path: (path.lstat().st_mode, path.lstat().st_ino) for path in original}, original)


SEED = r"""
import {serialPoolFixture} from './controller/test/serial-pool-fixture.mjs';
import {consumerDigest} from './consumer/consumer-config.mjs';
process.umask(0o022);
const f=await serialPoolFixture({after:()=>{}});
await f.currentStore.put(201,{envelope:f.envelope(201,{route:'manual',consumerDigest:consumerDigest(f.installationConsumer),executionSlot:'primary',step:3})});
console.log(JSON.stringify({root:f.root,consumer:f.installationConsumer,currentDigest:consumerDigest(f.installationConsumer)}));
"""

PRIVATE = r"""import os,subprocess,sys
root,source,*args=sys.argv[1:]
for part,target in [('etc','/etc'),('opt','/opt'),('var/lib','/var/lib')]:
 subprocess.run(['/usr/bin/mount','--bind',root+'/'+part,target],check=True)
os.execve('/usr/bin/node',['/usr/bin/node',source+'/controller/src/consumer-preflight-cli.mjs',*args],
 {'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1'})
"""

PRIVATE_HOLDER = r"""import os,subprocess,sys
root,source,lock,receipt,operation,target,digest=sys.argv[1:]
for part,destination in [('etc','/etc'),('opt','/opt'),('var/lib','/var/lib')]:
 subprocess.run(['/usr/bin/mount','--bind',root+'/'+part,destination],check=True)
os.execve('/usr/bin/python3',['/usr/bin/python3','-I',source+'/deploy/writer_lock_lease.py',
 '--hold',lock,receipt,operation,target,digest],{'PATH':'/usr/bin:/bin'})
"""


@unittest.skipUnless(sys.platform == 'linux' and os.geteuid() == 0 and Path(NODE).exists(),
                     'actual root Linux, Node and private mount namespace required')
class ConsumerPreflightCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = subprocess.run(['/usr/bin/unshare', '--mount', '--propagation', 'private', '/usr/bin/true'],
                                capture_output=True)
        if result.returncode:
            raise unittest.SkipTest('private mount namespace unavailable')

    def setUp(self):
        process = subprocess.run([NODE, '--import', './consumer/test-support/consumer-env.mjs',
            '--input-type=module', '-e', SEED], cwd=ROOT,
            env={**os.environ, 'TMPDIR': '/run', 'TAR_OPTIONS': '--no-same-permissions'},
            text=True, capture_output=True, timeout=60)
        self.assertEqual(process.returncode, 0, process.stderr)
        seeded = json.loads(process.stdout)
        self.root = Path(seeded['root'])
        self.assertEqual(self.root.parent, Path('/run'))
        self.assertTrue(self.root.name.startswith('relay-serial-compat-'))
        self.addCleanup(shutil.rmtree, self.root)
        self.consumer, self.digest = seeded['consumer'], seeded['currentDigest']
        self.configuration = self.root / 'etc/relay-compat/consumer.json'
        self.actual = self.configuration.read_bytes()
        self.claims = self.root / self.consumer['paths']['claimRoot'].lstrip('/')
        self.lock = self.claims / 'publication-v2.lock'
        self.lock.write_bytes(b'')
        self.lock.chmod(0o644)
        self.stage = self.root / 'stage'
        self.stage.mkdir(mode=0o700)
        self.source = self.stage / 'source'
        for component in ['consumer', 'controller', 'runtime', 'contracts', 'reviewer/src']:
            shutil.copytree(ROOT / component, self.source / component,
                            symlinks=True, ignore=shutil.ignore_patterns('node_modules', 'target', '__pycache__'))
        (self.source / 'deploy').mkdir()
        shutil.copyfile(ROOT / 'deploy/writer_lock_lease.py', self.source / 'deploy/writer_lock_lease.py')
        (self.source / '.relay-source.json').write_text(json.dumps({'revision': TARGET}))
        protect_fixture_source(self.source)
        installed = self.root / ('opt/relay-compat/releases/' + 'd' * 40)
        (installed / 'reviewed-source').mkdir(parents=True)
        (installed / 'reviewed-source/.relay-source.json').write_text(json.dumps({'revision': 'd' * 40}))
        self.snapshot = installed / 'deployment-config.json'
        self.snapshot.write_text(json.dumps({'consumer': self.consumer, 'environment': {'namespace': 'relay-compat'}}))
        self.snapshot.chmod(0o600)
        self.manifest = installed / 'artifact-manifest.json'
        self.manifest.write_text(json.dumps({'commit': 'd' * 40, 'installedRevision': 'd' * 40,
            'resolvedRevision': 'd' * 40, 'deploymentConfigSha256': hashlib.sha256(self.snapshot.read_bytes()).hexdigest()}))
        self.manifest.chmod(0o640)
        (self.root / 'opt/relay-compat/current').symlink_to('releases/' + 'd' * 40)
        for name in ['passwd', 'group', 'nsswitch.conf']:
            shutil.copyfile(Path('/etc') / name, self.root / 'etc' / name)

    def protected_snapshot(self):
        result = {}
        for part in ['etc', 'opt', 'var/lib']:
            for path in (self.root / part).rglob('*'):
                info = path.lstat()
                if path.is_file() and not path.is_symlink():
                    result[str(path.relative_to(self.root))] = (hashlib.sha256(path.read_bytes()).hexdigest(),
                                                               info.st_ino, info.st_mode)
        return result

    def run_cli(self, *, desired=None, extra=()):
        arguments = ['--config', '/etc/relay-compat/consumer.json', '--install-root', '/opt/relay-compat',
            '--stage-root', str(self.stage), '--desired-digest', desired or 'f' * 64,
            '--repository', self.consumer['repository'], *extra]
        return subprocess.run(['/usr/bin/unshare', '--mount', '--propagation', 'private', '--',
            '/usr/bin/python3', '-I', '-c', PRIVATE, str(self.root), str(self.source), *arguments],
            text=True, capture_output=True, timeout=180)

    def test_valid_and_invalid_live_drift_still_observe_real_serial_and_current_pending_history(self):
        for drift in ['valid', 'invalid']:
            with self.subTest(drift=drift):
                if drift == 'valid':
                    value = json.loads(self.actual)
                    value['defaultProfile']['effort'] = 'medium'
                    self.configuration.write_text(json.dumps(value))
                else:
                    self.configuration.write_bytes(b'{ invalid live JSON')
                before = self.protected_snapshot()
                result = self.run_cli()
                # Required consumer rebinding cannot classify these original
                # and current handoffs without native Task authority. This
                # fixture deliberately supplies no App credentials or API.
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, '')
                self.assertEqual(json.loads(result.stderr)['code'], 'HISTORICAL_TASK_AUTHORITY_UNAVAILABLE')
                self.assertEqual(self.protected_snapshot(), before)

    def test_unchanged_digest_keeps_original_manual_bindings_and_matching_live_config_needs_no_snapshot(self):
        self.snapshot.unlink()
        before = self.protected_snapshot()
        result = self.run_cli(desired=self.digest)
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(result.stdout)
        self.assertTrue(receipt['eligible'])
        self.assertEqual(receipt['unknown'], [])
        self.assertEqual(receipt['active'], [200])
        self.assertFalse(receipt['consumerRestoreRequired'])
        self.assertEqual(receipt['effectiveConsumerPath'], '/etc/relay-compat/consumer.json')
        self.assertFalse(list(self.stage.glob('consumer-context-*')))
        self.assertEqual(self.protected_snapshot(), before)

    def test_proved_serial_migration_availability_option_retains_the_authenticated_current_digest(self):
        self.configuration.write_bytes(b'{ invalid live JSON')
        before = self.protected_snapshot()
        result = self.run_cli(extra=['--retain-current-digest'])
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertTrue(value['eligible'])
        self.assertTrue(value['retainedCurrentDigest'])
        self.assertEqual(value['requestedDesiredDigest'], 'f' * 64)
        self.assertEqual(value['desiredDigest'], self.digest)
        self.assertEqual(value['unknown'], [])
        self.assertEqual(self.protected_snapshot(), before)

    def test_missing_tampered_snapshot_or_gate_mismatch_never_changes_live_state(self):
        self.configuration.write_bytes(b'{ invalid live JSON')
        original = self.snapshot.read_bytes()
        gate = self.claims / 'admission-pool-v1.json'
        original_gate = gate.read_bytes()
        for failure in ['missing-snapshot', 'tampered-snapshot', 'gate-mismatch']:
            with self.subTest(failure=failure):
                self.snapshot.write_bytes(original)
                self.snapshot.chmod(0o600)
                gate.write_bytes(original_gate)
                if failure == 'missing-snapshot':
                    self.snapshot.unlink()
                elif failure == 'tampered-snapshot':
                    self.snapshot.write_bytes(original + b' ')
                else:
                    value = json.loads(original_gate)
                    value['consumerDigest'] = '0' * 64
                    gate.write_text(json.dumps(value))
                before = self.protected_snapshot()
                result = self.run_cli()
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, '')
                error = json.loads(result.stderr)
                self.assertRegex(error['code'], r'^[A-Z][A-Z0-9_]{0,79}$')
                self.assertTrue(error['next'])
                self.assertNotIn(str(self.root), result.stderr)
                self.assertFalse(list(self.stage.glob('consumer-context-*')))
                self.assertEqual(self.protected_snapshot(), before)

    def test_invalid_arguments_produce_only_a_bounded_error_and_next_action(self):
        result = self.run_cli(extra=['--unknown', 'private-value'])
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, '')
        error = json.loads(result.stderr)
        self.assertEqual(error['code'], 'CONSUMER_PREFLIGHT_ARGUMENTS_INVALID')
        self.assertNotIn('private-value', result.stderr)

    def test_legacy_current_consumer_without_snapshot_or_serial_receipt_has_no_new_prerequisite(self):
        original = self.root / 'etc/relay-compat/serial-consumer-v1.json'
        receipt = json.loads((self.root / 'etc/relay-compat/serial-pool-compat-v1.json').read_text())
        self.configuration.write_bytes(original.read_bytes())
        self.snapshot.unlink()
        (self.root / 'etc/relay-compat/serial-pool-compat-v1.json').unlink()
        before = self.protected_snapshot()
        result = self.run_cli(desired=receipt['original']['consumerDigest'])
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertTrue(value['eligible'])
        self.assertFalse(value['consumerRestoreRequired'])
        self.assertEqual(self.protected_snapshot(), before)

    def test_private_view_kernel_refuses_writing_the_consumer_while_original_preflight_remains_read_only(self):
        self.configuration.write_bytes(b'{ invalid live JSON')
        candidate = self.source / 'controller/src/admission-cli.mjs'
        candidate.write_text('import {writeFileSync as preflightWriteProbe} from "node:fs";'
            'try{preflightWriteProbe(process.env.RELAY_CONSUMER_CONFIG,"forbidden mutation");'
            'throw new Error("read-only private view missing");}'
            'catch(error){if(error.code!=="EROFS")throw error;}\n' + candidate.read_text())
        before = self.protected_snapshot()
        result = self.run_cli(desired=self.digest)
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertTrue(value['consumerRestoreRequired'])
        self.assertEqual(value['unknown'], [])
        self.assertEqual(value['active'], [200])
        self.assertTrue(value['eligible'])
        clone = Path(value['effectiveConsumerPath'])
        self.assertTrue(clone.is_relative_to(self.stage))
        self.assertEqual(clone.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(clone.stat().st_mode & 0o777, 0o644)
        self.assertEqual(json.loads(clone.read_bytes()), self.consumer)
        self.assertEqual(self.protected_snapshot(), before)

    def test_final_observation_reuses_verified_writer_holder_without_nested_flock(self):
        gate = self.claims / 'admission-pool-v1.json'
        state = json.loads(gate.read_bytes())
        state.update(phase='applying', operationId=OP, target=TARGET)
        gate.write_text(json.dumps(state))
        lease_path = self.stage / 'writer-lease.json'
        holder = subprocess.Popen(['/usr/bin/unshare', '--mount', '--propagation', 'private', '--',
            '/usr/bin/python3', '-I', '-c', PRIVATE_HOLDER, str(self.root), str(self.source),
            self.consumer['paths']['claimRoot'] + '/publication-v2.lock', str(lease_path), OP, TARGET, self.digest],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        def cleanup():
            if holder.poll() is None:
                holder.stdin.close()
                try:
                    holder.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    holder.kill(); holder.wait(timeout=5)
            holder.stdout.close(); holder.stderr.close()
        self.addCleanup(cleanup)
        with selectors.DefaultSelector() as events:
            events.register(holder.stdout, selectors.EVENT_READ)
            self.assertTrue(events.select(5))
            self.assertEqual(holder.stdout.readline(), 'WRITER_LOCK_READY\n')
        before = self.protected_snapshot()
        result = self.run_cli(desired=self.digest, extra=['--writer-lock-lease', str(lease_path)])
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertFalse(value['consumerRestoreRequired'])
        self.assertTrue(value['eligible'])
        self.assertEqual(value['operationId'], OP)
        self.assertEqual(self.protected_snapshot(), before)


if __name__ == '__main__':
    unittest.main()
