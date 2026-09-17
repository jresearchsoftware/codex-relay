"""Run copied release modules without workspace config or Unix privilege.

Only the diagnostic's runuser boundary is substituted here. Native exact-head
CI owns the proof of real users, root-owned configuration and sudo isolation.
"""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar
import yaml

ROOT = Path(__file__).resolve().parents[3]
ANSIBLE = ROOT / 'deploy/ansible'
SPEC = importlib.util.spec_from_file_location('installed_consumer_diagnostic', ANSIBLE / 'tools/production-diagnostic.py')
DIAGNOSTIC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DIAGNOSTIC)
RUN = subprocess.run
CLEAN_ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'}


class InstalledConsumerBindingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='installed-consumer-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.install = self.root / 'opt'
        self.release = self.install / 'release'
        self.source = self.release / 'reviewed-source'
        self.source.mkdir(parents=True)
        (self.release / 'bin').mkdir()
        (self.install / 'current').symlink_to(self.release, target_is_directory=True)
        self.values = {
            **yaml.safe_load((ANSIBLE / 'group_vars/all.yml').read_text()),
            'relay_install_root': str(self.install), 'relay_release_path': str(self.release),
        }
        artifacts = yaml.safe_load((ANSIBLE / 'roles/relay_artifacts/tasks/main.yml').read_text())
        # The product Git object supplies the complete unchanged module tree.
        for name in ['controller', 'runtime', 'consumer', 'contracts', 'reviewer']:
            shutil.copytree(ROOT / name, self.source / name,
                            ignore=shutil.ignore_patterns('target', '__pycache__'))
        for name in ['Stage the exact reviewed on-demand Codex dispatch artifact',
                     'Stage the exact reviewed diagnostics store artifact']:
            link = self.render(next(t for t in artifacts if t.get('name') == name)['ansible.builtin.file'])
            Path(link['dest']).symlink_to(link['src'])
        validation = yaml.safe_load((ANSIBLE / 'roles/relay_codex_runtime/tasks/production-launcher-validation.yml').read_text())
        self.diagnostic_task = next(t for t in validation if t.get('register') == 'relay_production_diagnostics_closure')
        self.configs = {}
        for consumer in ['example', 'canary']:
            directory = self.root / consumer
            directory.mkdir()
            config = json.loads((ROOT / f'consumer/fixtures/{consumer}.json').read_text())
            config['paths']['diagnosticsRoot'] = str(directory / 'bundles')
            config['paths']['diagnosticsConfig'] = str(directory / 'diagnostics.json')
            (directory / 'diagnostics.json').write_text('{"schemaVersion":"1.0","mode":"normal","retentionCount":8}')
            path = directory / 'consumer.json'
            path.write_text(json.dumps(config))
            path.chmod(0o644)
            self.configs[consumer] = path

    def render(self, source, config=None):
        variables = dict(self.values)
        if config is not None:
            variables['relay_consumer_config_path'] = str(config)
        return Templar(loader=DataLoader(), variables=variables).template(source, convert_data=False)

    def run_module(self, args, env, **kwargs):
        return RUN(args, cwd=self.root, env=env, capture_output=True, text=True, timeout=20, **kwargs)

    def diagnostic_probe(self, config, ambient=None):
        task = self.render(self.diagnostic_task, config)
        return self.run_module(task['ansible.builtin.command']['argv'],
                               {**CLEAN_ENV, **(ambient or {}), **task.get('environment', {})})

    def wrapper(self, name, config):
        path = self.install / name
        template = (ANSIBLE / f'roles/relay_controller/templates/{name}.j2').read_text()
        path.write_text(self.render(template, config))
        path.chmod(0o755)
        return str(path)

    def test_diagnostic_import_uses_deployed_config_without_workspace_or_ambient_fallback(self):
        self.assertTrue((self.source / 'consumer/fixtures').exists())  # packaged examples must never become a fallback
        direct = ['/usr/bin/node', str(self.release / 'bin/relay-diagnostics-store.mjs'), '--check-runtime']
        unbound = self.run_module(direct, CLEAN_ENV)
        self.assertNotEqual(unbound.returncode, 0)
        self.assertIn('CONSUMER_CONFIG_INVALID', unbound.stderr)
        for config in self.configs.values():
            for ambient in [None, {'RELAY_CONSUMER_CONFIG': '/missing/workspace/consumer.json'}]:
                with self.subTest(config=config, ambient=ambient):
                    result = self.diagnostic_probe(config, ambient)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout, 'DIAGNOSTICS_RUNTIME_READY\n')
                    self.assertFalse((config.parent / 'bundles').exists())

    def test_worker_diagnostic_passes_deployed_config_in_its_cleared_runner_environment(self):
        def as_runner(args, **kwargs):
            self.assertEqual(args[:4], ['/usr/sbin/runuser', '-u', 'relay-runner', '--'])
            self.assertEqual(set(kwargs['env']), {*CLEAN_ENV, 'RELAY_CONSUMER_CONFIG'})
            return RUN(args[4:], **kwargs)

        with mock.patch.dict(os.environ, {'RELAY_CONSUMER_CONFIG': '/missing/workspace/consumer.json'}), \
                mock.patch.object(DIAGNOSTIC.subprocess, 'run', side_effect=as_runner):
            for config in self.configs.values():
                result = DIAGNOSTIC.worker_preflight(self.release, consumer_config=config)
                self.assertEqual(result['status'], 'passed', result)
            result = DIAGNOSTIC.worker_preflight(self.release, consumer_config=self.root / 'missing.json')
            self.assertEqual(result['status'], 'blocked', result)

    def test_wrappers_override_caller_config_and_store_only_in_the_bound_consumer(self):
        for name, config in self.configs.items():
            other = self.configs['canary' if name == 'example' else 'example']
            env = {**CLEAN_ENV, 'RELAY_CONSUMER_CONFIG': str(other)}
            dispatch = self.wrapper('relay-codex-dispatch', config)
            ready = self.run_module([dispatch, '--check-runtime'], env)
            self.assertEqual(ready.returncode, 0, ready.stderr)
            self.assertEqual(json.loads(ready.stdout)['status'], 'RUNTIME_READY')
            store = self.wrapper('relay-diagnostics-store', config)
            request = {'schemaVersion': '1.0', 'mode': 'normal', 'executionId': name}
            result = self.run_module([store], env, input=json.dumps(request))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['status'], 'stored')
            self.assertTrue((config.parent / f'bundles/{name}.json').is_file())
            self.assertFalse((other.parent / f'bundles/{name}.json').exists())
            forbidden = self.run_module([store, '--check-runtime'], env)
            self.assertEqual(forbidden.returncode, 40)

    def test_installed_probes_and_wrappers_fail_closed_on_invalid_deployed_config(self):
        config = self.root / 'invalid.json'
        valid = self.configs['example'].read_text()
        ambient = {'RELAY_CONSUMER_CONFIG': str(self.configs['canary'])}
        for mode in ['missing', 'malformed', 'duplicate-key', 'writable', 'symlink']:
            with self.subTest(mode=mode):
                config.unlink(missing_ok=True)
                if mode == 'symlink':
                    config.symlink_to(self.configs['example'])
                elif mode != 'missing':
                    config.write_text({'malformed': '{', 'duplicate-key': valid.replace('"version": 1', '"version": 1, "version": 1')}.get(mode, valid))
                    config.chmod(0o666 if mode == 'writable' else 0o644)
                results = [self.diagnostic_probe(config, ambient)]
                for wrapper, arguments in [('relay-codex-dispatch', ['--check-runtime']), ('relay-diagnostics-store', [])]:
                    results.append(self.run_module([self.wrapper(wrapper, config), *arguments], {**CLEAN_ENV, **ambient}, input='{}'))
                for result in results:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(result.stdout, '')
                    self.assertIn('CONSUMER_CONFIG_INVALID', result.stderr)

    def test_installed_dispatch_rejects_cross_consumer_and_stale_digest_before_execution(self):
        consumer_module = (self.source / 'consumer/consumer.mjs').as_uri()
        contract_module = (self.source / 'controller/src/execution-contract.mjs').as_uri()
        admission = f"""
          import {{ CONSUMER, CONSUMER_DIGEST }} from {json.dumps(consumer_module)};
          import {{ validateEnvelope }} from {json.dumps(contract_module)};
          const e = {{version: 2, repository: CONSUMER.repository, consumerDigest: CONSUMER_DIGEST,
            profile: CONSUMER.defaultProfile, runId: 7, step: 1, attemptId: 'run-7', target: 'issue',
            number: 1, issueNumber: 1, route: 'auto', startHead: 'a'.repeat(40), historicalBase: 'a'.repeat(40),
            targetBase: 'a'.repeat(40), authorityDigest: 'b'.repeat(64),
            branch: CONSUMER.taskBranchPrefix + 'task-1', validation: ['routing-tests']}};
          process.stdout.write(JSON.stringify(validateEnvelope(e)));
        """
        for name, config in self.configs.items():
            env = {**CLEAN_ENV, 'RELAY_CONSUMER_CONFIG': str(config)}
            admitted = self.run_module(['/usr/bin/node', '--input-type=module', '-e', admission], env)
            self.assertEqual(admitted.returncode, 0, admitted.stderr)
            envelope = json.loads(admitted.stdout)
            for mutation in ['repository', 'missing-digest', 'changed-digest', 'changed-config', 'other-consumer']:
                with self.subTest(consumer=name, mutation=mutation):
                    payload = dict(envelope)
                    original = config.read_text()
                    bound = config
                    if mutation == 'repository':
                        payload['repository'] = 'foreign/repository'
                    elif mutation == 'missing-digest':
                        del payload['consumerDigest']
                    elif mutation == 'changed-digest':
                        payload['consumerDigest'] = '0' * 64
                    elif mutation == 'other-consumer':
                        bound = self.configs['canary' if name == 'example' else 'example']
                    else:
                        changed = json.loads(original)
                        changed['owner'] = 'different-owner'
                        config.write_text(json.dumps(changed))
                    try:
                        dispatch = self.wrapper('relay-codex-dispatch', bound)
                        result = self.run_module([dispatch], env, input=json.dumps(payload))
                        self.assertNotEqual(result.returncode, 0)
                        self.assertEqual(result.stdout, '')
                        self.assertEqual(json.loads(result.stderr)['code'], 'EXECUTION_ENVELOPE_INVALID')
                    finally:
                        config.write_text(original)


if __name__ == '__main__':
    unittest.main()
