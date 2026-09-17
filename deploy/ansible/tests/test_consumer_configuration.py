"""Render consumer inputs without installation, credentials or privilege."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar
import yaml

ROOT = Path(__file__).resolve().parents[3]
ANSIBLE = ROOT / 'deploy/ansible'


class ConsumerConfigurationTests(unittest.TestCase):
    def test_runtime_and_tls_config_root_satisfy_privileged_consumer_ownership(self):
        variables = yaml.safe_load((ANSIBLE / 'group_vars/all.yml').read_text())
        self.assertEqual(variables['relay_config_root'], '/etc/codex-relay')
        for role in ['relay_runtime', 'relay_tls']:
            tasks = yaml.safe_load((ANSIBLE / f'roles/{role}/tasks/main.yml').read_text())
            directories = next(t for t in tasks if any(
                isinstance(item, dict) and item.get('path') == '{{ relay_config_root }}'
                for item in t.get('loop', [])))
            item = next(item for item in directories['loop'] if item['path'] == '{{ relay_config_root }}')
            rendered = Templar(loader=DataLoader(), variables={**variables, 'item': item}).template(
                directories['ansible.builtin.file'])
            with self.subTest(role=role):
                self.assertEqual(rendered['path'], '/etc/codex-relay')
                self.assertEqual((rendered['owner'], rendered['group'], rendered['mode']), ('root', 'root', '0751'))
                self.assertFalse(rendered.get('recurse', False), 'child ownership must remain explicit')

    def test_rendered_snapshot_matches_each_qualified_consumer(self):
        source = (ANSIBLE / 'roles/relay_controller/templates/consumer.json.j2').read_text()
        for consumer in ['example', 'canary']:
            expected = json.loads((ROOT / f'consumer/fixtures/{consumer}.json').read_text())
            variables = yaml.safe_load((ANSIBLE / 'group_vars/all.yml').read_text())
            for key, variable in {
                'repository': 'relay_github_repository', 'owner': 'relay_owner_actor',
                'baseBranch': 'relay_github_base_branch', 'taskBranchPrefix': 'relay_task_branch_prefix',
                'routingWorkflow': 'relay_routing_workflow', 'recoveryWorkflow': 'relay_recovery_workflow',
                'validationWorkflow': 'relay_validation_workflow', 'runtimeUser': 'relay_codex_user',
            }.items():
                variables[variable] = expected[key]
            for role in ['writer', 'reviewer']:
                for key, variable in {'slug': f'relay_{role}_app_slug', 'appId': f'relay_{role}_app_id',
                                      'installationId': f'relay_{role}_app_installation_id',
                                      'expectedActor': f'relay_{role}_expected_actor'}.items():
                    variables[variable] = expected[role + 'App'][key]
            for role in ['writer', 'remediation']:
                for key in ['name', 'email']:
                    variables[f'relay_{role}_commit_{key}'] = expected[role + 'Identity'][key]
            variables['relay_default_model'] = expected['defaultProfile']['cliModelId']
            variables['relay_default_effort'] = expected['defaultProfile']['effort']
            for key, variable in {
                'workRoot': 'relay_dispatch_work_root', 'dispatch': 'relay_codex_dispatch_path',
                'writerHelper': 'relay_writer_helper_path', 'launcher': 'relay_codex_launcher_path',
                'diagnosticsConfig': 'relay_diagnostics_config_path', 'diagnosticsStore': 'relay_diagnostics_store_path',
                'diagnosticsRoot': 'relay_diagnostics_root', 'credentialEnv': 'relay_writer_credential_env_file',
                'credentialKeyFile': 'relay_writer_credential_key_file', 'claimRoot': 'relay_writer_claim_root',
            }.items():
                variables[variable] = expected['paths'][key]
            variables['relay_dispatch_state_root'] = str(Path(expected['paths']['attemptRoot']).parent)
            rendered = Templar(loader=DataLoader(), variables=variables).template(source, convert_data=False)
            self.assertEqual(json.loads(rendered), expected)
            with tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / 'consumer.json'
                path.write_text(rendered)
                path.chmod(0o644)
                probe = subprocess.run(['node', 'consumer/consumer.mjs'], cwd=ROOT,
                                       env={**os.environ, 'RELAY_CONSUMER_CONFIG': str(path)}, capture_output=True, text=True)
                self.assertEqual(probe.returncode, 0, probe.stderr)



if __name__ == '__main__':
    unittest.main()
