"""Pure preparation tests. No installer, SSH, API, service or model execution."""
import importlib.util
import json
from pathlib import Path
import tempfile
import subprocess
import unittest

import yaml


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


stage = module(Path(__file__).with_name('stage-test-installation.py'), 'step5_stage')


class PreparationTests(unittest.TestCase):
    def config(self, namespace='codex-relay-test-two'):
        return {'source': {'revision': 'b' * 40}, 'target': {'host': '195.201.83.241'},
                'consumer': {'repository': 'jresearchsoftware/codex-relay-testbed-2', 'runtimeUser': 'relay-test-two-codex',
                             'executionSlots': [{'id': 'primary'}, {'id': 'second'}]},
                'environment': {'namespace': namespace, 'generalRunner': {'name': 'old'}}}

    def test_config_preserves_namespace_runtime_and_uses_one_owner_pool(self):
        original = self.config()
        result = stage.prepared_config(original, 'a' * 40, '/mnt/c/private/test-admin.pem', '100', '200', 2)
        self.assertEqual(result['consumer']['runtimeUser'], 'relay-test-two-codex')
        self.assertEqual(result['environment']['generalRunner']['user'], 'relay-test-general-runner')
        self.assertEqual(result['environment']['generalRunner']['name'], 'relay-test-managed-pool')
        self.assertNotIn('executionSlots', result['consumer'])
        self.assertEqual(original['environment']['generalRunner']['name'], 'old')

    def test_exact_source_adaptation_keeps_original_guards_and_private_archives(self):
        previous = module(stage.PREVIOUS_PATH, 'original_test_stage')
        prepared, transformed, guard = stage.adapted_prepare(previous)
        self.assertTrue(callable(prepared))
        self.assertIn("range(2, 33)", transformed)
        self.assertIn("status['unknown']==[]", guard)
        self.assertIn("status['phase']=='open'", guard)
        self.assertIn("journal-", guard)
        self.assertIn('relay-test-managed-pool-pool-', guard)
        self.assertNotIn("task103-step3-retained-local-state", guard)
        with self.assertRaises(ValueError):
            stage.replace_once('changed source', 'expected invariant', 'new')

    def test_pool_overlay_targets_only_managed_service_dirs_and_never_creates_host_tool(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            (root / 'ansible').mkdir()
            (root / 'source/deploy').mkdir(parents=True)
            (root / 'source/deploy/managed_pool.py').write_text('# deterministic unchanged helper\n')
            (root / 'ansible/stage.yml').write_text(yaml.safe_dump([{'name': 'old', 'post_tasks': [
                {'name': 'Create only dedicated TEST service tool overlay directories', 'loop': ['old.service']}]}]))
            (root / 'plan.json').write_text(json.dumps({'namespace': 'codex-relay-test', 'sourceRevision': 'a' * 40,
                'adaptations': [], 'limitations': [], 'prerequisites': []}))
            stage.patch_bundle(root, root / 'source', 2, 'prepared', 'guard')
            play = yaml.safe_load((root / 'ansible/stage.yml').read_text())[0]
            for item in play['post_tasks']:
                if 'loop' in item:
                    self.assertEqual(item['loop'], ['relay-test-managed-pool-pool-1.service', 'relay-test-managed-pool-pool-2.service'])
                for module_name in ['ansible.builtin.copy', 'ansible.builtin.file']:
                    if module_name in item:
                        target = item[module_name].get('dest', item[module_name].get('path'))
                        self.assertTrue(target.startswith('/etc/systemd/system/'))
            wrapper = (root / 'run-stage.sh').read_text()
            self.assertLess(wrapper.index('os.lstat(p)'), wrapper.index('exec /usr/bin/systemd-run'))
            self.assertNotIn('touch ', wrapper)
            subprocess.run(['sh', '-n'], input=wrapper, text=True, check=True, capture_output=True)


if __name__ == '__main__':
    unittest.main()
