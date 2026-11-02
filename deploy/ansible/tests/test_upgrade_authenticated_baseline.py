"""Read-only upgrade proof using the actual protected baseline and Node digest."""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
ANSIBLE = ROOT / 'deploy/ansible'
OP = '12345678-1234-1234-1234-123456789abc'
PREVIOUS, TARGET = 'a' * 40, 'b' * 40
spec = importlib.util.spec_from_file_location('upgrade_baseline', ANSIBLE / 'scripts/verify_upgrade.py')
upgrade = importlib.util.module_from_spec(spec)
spec.loader.exec_module(upgrade)
NATIVE = sys.platform == 'linux' and os.geteuid() == 0 and Path('/usr/bin/node').exists()


@unittest.skipUnless(NATIVE, 'actual root Linux and Node required')
class UpgradeAuthenticatedBaselineTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='relay-upgrade-baseline-', dir='/run')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = json.loads((ROOT / 'deploy/example.json').read_bytes())
        self.install, self.config_root = self.root / 'opt/codex-relay', self.root / 'etc/codex-relay'
        self.release = self.install / 'releases' / PREVIOUS
        (self.release / 'reviewed-source').mkdir(parents=True)
        (self.release / 'reviewed-source/.relay-source.json').write_text(json.dumps({'revision': PREVIOUS, 'tree': 'c' * 40}))
        (self.release / 'artifact-manifest.json').write_text(json.dumps({
            'commit': PREVIOUS, 'installedRevision': PREVIOUS, 'resolvedRevision': PREVIOUS, 'gitTree': 'c' * 40}))
        (self.install / 'current').symlink_to('releases/' + PREVIOUS)
        self.config_root.mkdir(parents=True)
        self.canonical = self.config_root / 'consumer.json'
        self.canonical.write_bytes(b'{ invalid original live consumer')
        self.canonical.chmod(0o600)
        self.stage = self.install / 'releases' / ('.stage-' + OP)
        self.stage.mkdir(mode=0o700)
        source = self.stage / 'release/reviewed-source'
        source.mkdir(parents=True)
        for name in ('consumer', 'contracts'):
            shutil.copytree(ROOT / name, source / name,
                ignore=shutil.ignore_patterns('node_modules', 'target', '__pycache__'))
        (source / 'reviewer/src').mkdir(parents=True)
        shutil.copyfile(ROOT / 'reviewer/src/executable-cr-v2.json', source / 'reviewer/src/executable-cr-v2.json')
        (source / '.relay-source.json').write_text(json.dumps({'revision': TARGET}))
        context = self.stage / 'consumer-context-abc123'
        context.mkdir(mode=0o700)
        self.baseline = context / 'consumer.json'
        self.baseline.write_text(json.dumps(self.config['consumer']) + '\n')
        self.baseline.chmod(0o644)
        script = ('import{readFileSync}from"node:fs";import{pathToFileURL}from"node:url";'
                  'const m=await import(pathToFileURL(process.argv[1]));'
                  'console.log(m.consumerDigest(m.validateConsumer(m.parseConsumerJson(readFileSync(process.argv[2],"utf8")))));')
        self.digest = subprocess.check_output(['/usr/bin/node', '--input-type=module', '-e', script,
            str(source / 'consumer/consumer-config.mjs'), str(self.baseline)], text=True, timeout=30).strip()
        claims = self.root / self.config['consumer']['paths']['claimRoot'].lstrip('/')
        claims.mkdir(parents=True)
        self.gate = claims / 'admission-v1.json'
        self.gate.write_text(json.dumps({'version': 1, 'consumerDigest': self.digest, 'phase': 'open',
            'operationId': None, 'target': None, 'previousActive': None, 'verifiedRevision': None}))
        self.gate.chmod(0o600)
        self.context = {'stageRoot': str(self.stage), 'consumerPath': str(self.baseline),
            'baselineDigest': self.digest, 'claimRoot': self.config['consumer']['paths']['claimRoot']}
        resource_spec = importlib.util.spec_from_file_location('upgrade_selected_resources', ROOT / 'deploy/clean_reinstall.py')
        self.resources = importlib.util.module_from_spec(resource_spec)
        resource_spec.loader.exec_module(self.resources)
        units = self.root / 'etc/systemd/system'
        units.mkdir(parents=True)
        identities = {self.resources.unit_names(self.config)[2]: self.config['environment']['reviewerUser'],
            **{unit: identity for _, identity, unit in self.resources.runner_specs(self.config)}}
        for name, identity in identities.items():
            (units / name).write_text('[Service]\nUser=' + identity + '\n')

    def verify(self, *, config=None, context=True, serial=False):
        return upgrade.verify_desired(self.install, self.config_root, TARGET, PREVIOUS,
            boundary=self.root, expected_config=config or self.config,
            resource_probe=self.resources.prove_git_resource_boundary,
            consumer_resource_probe=self.resources.prove_consumer_resources,
            consumer_baseline=self.context if context else None, qualified_serial_preflight=serial)

    def test_invalid_canonical_bytes_use_only_gate_authenticated_baseline_without_writes(self):
        original, gate, link = self.canonical.read_bytes(), self.gate.read_bytes(), os.readlink(self.install / 'current')
        with self.assertRaises(ValueError):
            self.verify(context=False)
        self.assertEqual(self.verify(), PREVIOUS)
        self.assertEqual(self.canonical.read_bytes(), original)
        self.assertEqual(self.gate.read_bytes(), gate)
        self.assertEqual(os.readlink(self.install / 'current'), link)

    def test_baseline_does_not_bypass_retained_resource_identity_proof(self):
        wanted = deepcopy(self.config)
        wanted['consumer']['runtimeUser'] = 'foreign-runtime'
        with self.assertRaisesRegex(ValueError, 'RESOURCE_MIGRATION_UNSUPPORTED'):
            self.verify(config=wanted)
        unit = self.root / 'etc/systemd/system' / self.resources.unit_names(self.config)[2]
        unit.write_text('[Service]\nUser=foreign-reviewer\n')
        with self.assertRaisesRegex(ValueError, 'RESOURCE_MIGRATION_UNSUPPORTED'):
            self.verify()

    def test_changed_clone_claim_digest_or_gate_cannot_supply_baseline(self):
        original = self.baseline.read_bytes()
        value = json.loads(original)
        value['defaultProfile']['effort'] = 'medium'
        self.baseline.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'BASELINE_BINDING_UNPROVEN'):
            self.verify()
        self.baseline.write_bytes(original)
        self.context['claimRoot'] = '/var/lib/foreign/claims'
        with self.assertRaisesRegex(ValueError, 'BASELINE_BINDING_UNPROVEN'):
            self.verify()
        self.context['claimRoot'] = self.config['consumer']['paths']['claimRoot']
        value = json.loads(self.gate.read_bytes())
        value['consumerDigest'] = 'f' * 64
        self.gate.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'BASELINE_GATE_UNPROVEN'):
            self.verify()

    def test_unsafe_or_unbound_clone_and_canonical_alias_are_rejected(self):
        self.context['consumerPath'] = str(self.canonical)
        with self.assertRaisesRegex(ValueError, 'BASELINE_BINDING_UNPROVEN'):
            self.verify()
        self.context['consumerPath'] = str(self.baseline)
        self.stage.chmod(0o755)
        with self.assertRaisesRegex(ValueError, 'BASELINE_BINDING_UNPROVEN'):
            self.verify()
        self.stage.chmod(0o700)
        self.canonical.unlink()
        self.canonical.symlink_to(self.baseline)
        with self.assertRaisesRegex(ValueError, 'UNSAFE_PATH'):
            self.verify()

    def test_serial_owning_preflight_is_explicit_stage_bound_and_keeps_identity_checks(self):
        self.canonical.write_text(json.dumps(self.config['consumer']))
        wanted = deepcopy(self.config)
        wanted['consumer']['generalRunnerPool'] = {'desiredCapacity': 2}
        with self.assertRaisesRegex(ValueError, 'RESOURCE_MIGRATION_UNSUPPORTED'):
            self.verify(config=wanted, context=False)
        self.assertEqual(self.verify(config=wanted, context=False, serial=str(self.stage)), PREVIOUS)
        with self.assertRaisesRegex(ValueError, 'SERIAL_PREFLIGHT_UNPROVEN'):
            self.verify(config=self.config, context=False, serial=str(self.stage))
        with self.assertRaisesRegex(ValueError, 'SERIAL_PREFLIGHT_UNPROVEN'):
            self.verify(config=wanted, context=False, serial=str(self.root))

    def test_actual_ansible_rendered_private_baseline_command_executes_without_live_mutation(self):
        try:
            from ansible.parsing.dataloader import DataLoader
            from ansible.template import Templar
        except ImportError:
            self.skipTest('actual Ansible renderer required')
        available = subprocess.run(['/usr/bin/unshare', '--mount', '/usr/bin/true'], capture_output=True)
        if available.returncode:
            self.skipTest('private root mount namespace required')
        loader = DataLoader()
        loader.set_basedir(str(ANSIBLE))
        task = loader.load_from_file(str(ANSIBLE / 'tasks/upgrade-preflight.yml'))[0]
        logical = lambda path: '/' + str(path.relative_to(self.root))
        values = {'playbook_dir': str(ANSIBLE), 'relay_git_desired_state': True,
            'relay_install_root': logical(self.install), 'relay_config_root': logical(self.config_root),
            'relay_production_operation_target_head': TARGET, 'relay_intent_expected_installed_revision': PREVIOUS,
            'relay_owner_apply_requested': True, 'relay_serial_pool_transition': False,
            'relay_installed_deployment_config': json.dumps(self.config),
            'relay_intent_preflight_consumer_path': logical(self.baseline),
            'relay_intent_preflight_baseline_digest': self.digest,
            'relay_intent_preflight_claim_root': self.context['claimRoot'], 'relay_intent_stage_root': logical(self.stage)}
        templar = Templar(loader=loader, variables=values)
        argv = templar.template(task['ansible.builtin.command']['argv'])
        original = self.canonical.read_bytes()
        program = ('import json,subprocess,sys;root=sys.argv[1];'
                   '[subprocess.run(["/usr/bin/mount","--bind",root+"/"+part,"/"+part],check=True)'
                   ' for part in ("opt","etc","var/lib")];'
                   'raise SystemExit(subprocess.run(json.loads(sys.argv[2]),input=sys.stdin.buffer.read()).returncode)')
        result = subprocess.run(['/usr/bin/unshare', '--mount', '--propagation', 'private', '--',
            '/usr/bin/python3', '-I', '-c', program, str(self.root), json.dumps(argv)],
            input=json.dumps(self.config), text=True, capture_output=True, timeout=45,
            env={'PATH': '/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1'})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'RELAY_UPGRADE_SOURCE_VALIDATED=' + PREVIOUS + '\n')
        self.assertEqual(self.canonical.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
