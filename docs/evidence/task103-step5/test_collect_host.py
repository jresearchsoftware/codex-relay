"""Pure path-export checks; never native execution evidence."""
import importlib.util
from pathlib import Path
import copy
import stat
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('step5_collector', Path(__file__).with_name('collect-host.py'))
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


class PathExportTests(unittest.TestCase):
    def environment(self):
        return b'\0'.join(f'{key}=/var/lib/codex-relay-test/work/run-123/.codex-sandbox/{suffix}'.encode()
                          for key, suffix in collector.PATHS.items()) + b'\0'

    def test_exports_only_explicit_paths(self):
        raw = self.environment() + b'CODEX_ACCESS_TOKEN=deterministic-private-sentinel\0UNRELATED=\xff\0'
        result = collector.path_environment(raw, '/var/lib/codex-relay-test/work/run-123')
        self.assertEqual(set(result), set(collector.PATHS))
        self.assertNotIn('deterministic-private-sentinel', repr(result))

    def test_refuses_duplicate_missing_and_foreign_path(self):
        raw = self.environment()
        for invalid in [raw + b'HOME=/home/shared\0', raw.replace(b'CODEX_HOME=', b'UNKNOWN='),
                        raw.replace(b'/.codex-sandbox/cache', b'/.codex-sandbox/../shared')]:
            with self.assertRaises(ValueError):
                collector.path_environment(invalid, '/var/lib/codex-relay-test/work/run-123')


class InstalledPoolTests(unittest.TestCase):
    """Model root/native observations explicitly; no real privileged filesystem."""
    def fixture(self):
        candidate, name = 'a' * 40, 'relay-test-pool'
        native = {'native_reads_complete': True, 'group': {'id': 6, 'name': 'test-control', 'visibility': 'selected',
                  'restricted_to_workflows': True}, 'runners': [{'id': 51, 'name': name, 'status': 'online'},
                  {'id': 52, 'name': name + '-2', 'status': 'online'}]}
        files = {}
        for ns, (repository, _) in collector.base.TARGETS.items():
            slots = [{'id': 'primary' if n == 1 else f'pool-{n}', 'runnerName': name if n == 1 else f'{name}-{n}',
                      'runnerUser': 'test-runner', 'runtimeUser': 'test-codex',
                      'paths': {'workRoot': f'/var/lib/{ns}/slots/{n}/work', 'attemptRoot': f'/var/lib/{ns}/slots/{n}/dispatch/attempts-v2'}}
                     for n in range(1, 33)]
            config = {'repository': repository, 'runtimeUser': 'test-codex', 'generalRunnerPool': {'desiredCapacity': 2},
                      'executionSlots': slots, 'paths': {'claimRoot': f'/var/lib/{ns}/writer-claims'}}
            deployment = {'consumer': config, 'environment': {'generalRunner': {'name': name, 'user': 'test-runner',
                          'scope': 'organization', 'group': 'test-control'}}}
            files[f'/etc/{ns}/consumer.json'] = config
            files[f'/opt/{ns}/releases/{candidate}/deployment-config.json'] = deployment
        manifest = {'version': 1, 'desiredCapacity': 2, 'ownerRepository': next(iter(collector.base.TARGETS.values()))[0],
                    'consumers': {repo: {'namespace': ns, 'admission': f'/opt/{ns}/relay-admission'}
                                  for ns, (repo, _) in collector.base.TARGETS.items()},
                    'members': {'primary': {'phase': 'ready', 'runnerId': 51}, 'pool-2': {'phase': 'ready', 'runnerId': 52}},
                    'binding': {'name': name, 'runnerUser': 'test-runner', 'group': 'test-control',
                                'members': [{'id': 'primary', 'name': name, 'service': name + '-pool-1.service'},
                                            {'id': 'pool-2', 'name': name + '-2', 'service': name + '-pool-2.service'}]}}
        files[f'/var/lib/codex-relay-pools/{name}/pool.json'] = manifest
        return candidate, native, files

    def load(self, candidate, native, files):
        def source(path, owners, limit=0):
            return copy.deepcopy(files[str(path)]), {'path': str(path), 'sha256': 'c' * 64}
        def release(path, strict=False):
            return path.parent / 'releases' / candidate
        with patch.object(collector.base, 'safe_path', side_effect=lambda path, root: Path(path)), \
             patch.object(collector.base, 'json_source', side_effect=source), \
             patch.object(collector.base, 'unit_binding', side_effect=lambda unit, user: {'ControlGroup': '/system.slice/' + unit, 'FragmentPath': '/etc/systemd/system/' + unit}), \
             patch.object(collector.pwd, 'getpwnam', side_effect=lambda user: SimpleNamespace(pw_uid=900 if user == 'test-runner' else 300)), \
             patch.object(Path, 'lstat', return_value=SimpleNamespace(st_mode=stat.S_IFLNK | 0o777, st_uid=0)), \
             patch.object(Path, 'resolve', release):
            return collector.load_installation(candidate, native)

    def test_one_physical_pool_binds_two_repository_inventories(self):
        candidate, native, files = self.fixture()
        slots, _, installed = self.load(candidate, native, files)
        self.assertEqual(len(slots), 64)
        self.assertEqual(len(installed['pool']['members']), 2)
        self.assertEqual({slot['uid'] for slot in slots}, {300})

    def test_refuses_uncertain_manifest_and_repository_pool_multiplication(self):
        for mutate in [lambda f: f['/var/lib/codex-relay-pools/relay-test-pool/pool.json']['members']['pool-2'].update(phase='draining'),
                       lambda f: f['/var/lib/codex-relay-pools/relay-test-pool/pool.json']['members']['primary'].update(runnerId=99),
                       lambda f: f['/etc/codex-relay-test-two/consumer.json']['executionSlots'][0].update(runnerName='other')]:
            candidate, native, files = self.fixture()
            mutate(files)
            with self.assertRaises(ValueError):
                self.load(candidate, native, files)


if __name__ == '__main__':
    unittest.main()
