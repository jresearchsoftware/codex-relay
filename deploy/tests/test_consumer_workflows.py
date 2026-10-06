"""Public consumer wiring; no installed runner or GitHub qualification is implied."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / '.github/workflows'
NODE = shutil.which('node')
HEAD = 'a' * 40
sys.path.insert(0, str(ROOT / 'deploy'))
from workflow_projection import render


def self_config():
    """Synthetic inputs with the public consumer's non-secret workflow wiring."""
    config = json.loads((ROOT / 'deploy/example.json').read_text())
    config['source']['repository'] = 'https://github.com/jresearchsoftware/codex-relay.git'
    config['consumer']['repository'] = 'jresearchsoftware/codex-relay'
    config['consumer']['owner'] = 'foal'
    config['environment']['runner'].update(user='codex-relay-runner', name='codex-relay-runner',
                                            group='codex-relay-runner', labels=['codex-relay'])
    config['environment']['generalRunner'].update(user='codex-relay-general-runner', name='codex-relay-general-runner')
    config['environment']['localApply'] = {'source': 'installed'}
    return config


def workflow(name):
    # Managed workflows are tested from canonical source at a synthetic pinned
    # product revision. The repository projection remains the installed owner
    # version until an accepted release is explicitly projected and reviewed.
    sources = render(self_config(), HEAD, ROOT)
    raw = sources.get('.github/workflows/' + name)
    value = yaml.safe_load(raw if raw is not None else (WORKFLOWS / name).read_bytes())
    # PyYAML's YAML 1.1 boolean resolver recognizes GitHub's unquoted `on` key.
    if True in value:
        value['on'] = value.pop(True)
    return value


def control_step(value):
    job, = value['jobs'].values()
    step, = job['steps']
    return job, step


def javascript(step):
    script = step['run'].split("<<'NODE'\n", 1)[1]
    return script.rsplit('\nNODE', 1)[0]


class ConsumerWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.routing = workflow('codex-relay-routing.yml')
        self.recovery = workflow('manual-writer-publication-recovery.yml')
        self.validation = workflow('relay-exact-head-validation.yml')

    def test_events_permissions_and_runner_boundaries(self):
        self.assertEqual(set(self.routing['on']), {'issues', 'pull_request_target', 'workflow_dispatch'})
        self.assertEqual(self.routing['on']['issues'], {'types': ['labeled']})
        self.assertEqual(self.routing['on']['pull_request_target'], {'types': ['labeled'], 'branches': ['main']})
        self.assertEqual(set(self.recovery['on']), {'workflow_dispatch'})
        permissions = {'actions': 'read', 'contents': 'read', 'issues': 'read', 'pull-requests': 'read'}
        for value in (self.routing, self.recovery):
            with self.subTest(workflow=value['name']):
                self.assertEqual(value['permissions'], permissions)
                self.assertEqual(value['concurrency'], {'group': 'codex-relay-control', 'cancel-in-progress': False})
                job, step = control_step(value)
                self.assertEqual(job['runs-on'], ['self-hosted', 'Linux', 'X64', 'codex-relay'])
                self.assertNotIn('permissions', job)
                self.assertNotIn('uses', step)
                self.assertEqual(step['shell'], 'bash --noprofile --norc -euo pipefail {0}')
                self.assertEqual(step['env']['GITHUB_TOKEN'], '${{ github.token }}')
                self.assertEqual(step['env']['RELAY_CONSUMER_CONFIG'], '/etc/codex-relay/consumer.json')
                self.assertEqual(step['env']['EXPECTED_WORKFLOW_CONTRACT'], 'relay-workflows-v2')
                self.assertEqual(step['env']['NODE_OPTIONS'], '')
                self.assertEqual(step['env']['NODE_PATH'], '')
                self.assertIn('test "$RUNNER_NAME" = codex-relay-general-runner', step['run'])
                self.assertIn('test "$(/usr/bin/id -un)" = codex-relay-general-runner', step['run'])
                self.assertNotIn('${{', step['run'], 'Event/input values must not be interpolated into shell source')
                self.assertNotIn('checkout', step['run'])
                self.assertNotIn('sudo', step['run'], 'Only installed Relay helpers own privileged invocation')
                self.assertNotIn('artifact-manifest.json', step['run'], 'The general runner cannot read the restricted manifest')
                if shutil.which('bash') and os.name != 'nt':
                    checked = subprocess.run(['bash', '-n'], input=step['run'], text=True, capture_output=True)
                    self.assertEqual(checked.returncode, 0, checked.stderr)

    def test_candidate_keeps_disposable_exact_head_validation(self):
        self.assertEqual(set(self.validation['on']), {'pull_request', 'push'})
        self.assertEqual(self.validation['permissions'], {'contents': 'read'})
        self.assertEqual(self.validation['jobs']['candidate']['name'], 'Candidate checks')
        for job in self.validation['jobs'].values():
            self.assertEqual(job['runs-on'], 'ubuntu-24.04')
            self.assertNotIn('permissions', job)
            checkout = job['steps'][0]
            self.assertEqual(checkout['with']['ref'], '${{ github.event.pull_request.head.sha || github.sha }}')
            self.assertIs(checkout['with']['persist-credentials'], False)
            self.assertEqual(checkout['with']['fetch-depth'], 0)
            for step in job['steps']:
                if 'uses' in step:
                    self.assertRegex(step['uses'], r'^[A-Za-z0-9_/-]+@[0-9a-f]{40}$')
        self.assertFalse((WORKFLOWS / 'ci.yml').exists(), 'Avoid duplicate candidate check producers')

    def test_cli_compatibility_keeps_targeted_unprivileged_qualification(self):
        steps = self.validation['jobs']['runtime']['steps']
        contracts = next(step for step in steps if '-m unittest' in step.get('run', ''))
        self.assertNotIn('sudo', contracts['run'])
        for suite in ('deploy.tests.test_consumer_workflows',
                      'deploy.ansible.tests.test_codex_runtime_contract',
                      'deploy.ansible.tests.test_production_codex_launcher_binding',
                      'deploy.ansible.tests.test_production_diagnostic'):
            self.assertIn(suite, contracts['run'])
        for suite in ('codex-launcher-*.test.mjs', 'diagnostics-*.test.mjs', 'diagnostic-snapshot.test.mjs'):
            self.assertIn('deploy/ansible/tests/' + suite, contracts['run'])
        release = next(step for step in steps if 'qualify_codex_cli.py' in step.get('run', ''))
        self.assertEqual(release['run'], 'python3 deploy/ansible/tests/qualify_codex_cli.py')
        self.assertLess(steps.index(release), steps.index(contracts))
        for step in (contracts, release):
            self.assertNotIn('if', step)
            self.assertNotIn('continue-on-error', step)
            self.assertNotIn('||', step['run'])
        for step in steps:
            command = step.get('run', '')
            self.assertNotIn('sudo', command)
            self.assertNotIn('installed_runtime_proof.py', command)
            self.assertNotIn('-m pytest', command)
            self.assertNotIn('unittest discover', command)
            if command and shutil.which('bash') and os.name != 'nt':
                checked = subprocess.run(['bash', '-n'], input=command, text=True, capture_output=True)
                self.assertEqual(checked.returncode, 0, checked.stderr)

    @unittest.skipUnless(NODE, 'Node is required to compare native launch metadata')
    def test_native_names_and_owner_event_conditions(self):
        # Evaluate the small GitHub expression subset actually used by these
        # workflows, then compare native names to the real controller contract.
        # No repository execution or GitHub calls are performed.
        script = r"""
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dispatchRunName, labelRunName } from './controller/src/launch-metadata.mjs';
const [routing, recovery] = JSON.parse(readFileSync(0, 'utf8'));
const evaluate = (source, github, inputs = {}) => {
  const expression = source.trim().replace(/^\$\{\{/, '').replace(/\}\}$/, '')
    .replace(/\.labels\.\*\.name/g, '.labels.map(label => label.name)');
  const format = (template, ...values) => template.replace(/\{([0-9]+)\}/g, (_, index) => values[Number(index)]);
  return Function('github', 'inputs', 'format', 'join', `return (${expression});`)
    (github, inputs, format, (values, separator) => values.join(separator));
};
const base = { repository: 'jresearchsoftware/codex-relay', actor: 'foal', triggering_actor: 'foal',
  ref: 'refs/heads/main', event_name: 'workflow_dispatch', event: {} };
const condition = routing.jobs.route.if;
for (const route of ['auto', 'manual']) {
  for (const target of ['issue', 'pull_request']) {
    const launch = { route, issueNumber: 27, step: 3, target, number: target === 'issue' ? 27 : 28 };
    const inputs = { route, task: '27', step: '3', pull_request: target === 'issue' ? '' : '28' };
    assert.equal(evaluate(routing['run-name'], base, inputs), dispatchRunName(launch));
    assert.equal(evaluate(condition, base, inputs), true);
    const subject = { number: launch.number, title: 'Task 27 · Step 3 · CR purpose',
      labels: ['bug', 'step-3', `codex-ready-${route}`].map(name => ({ name })),
      head: { repo: { full_name: base.repository } } };
    const github = { ...base, event_name: target === 'issue' ? 'issues' : 'pull_request_target',
      event: { action: 'labeled', label: { name: `codex-ready-${route}` },
        [target === 'issue' ? 'issue' : 'pull_request']: subject } };
    assert.equal(evaluate(routing['run-name'], github), labelRunName(launch, subject));
    assert.equal(evaluate(condition, github), true);
    assert.equal(evaluate(condition, { ...github, event: { ...github.event, label: { name: 'step-3' } } }), false);
    assert.equal(evaluate(condition, { ...github, event: { ...github.event, action: 'unlabeled' } }), false);
    if (target === 'pull_request') {
      assert.equal(evaluate(condition, { ...github, event: { ...github.event,
        pull_request: { ...subject, head: { repo: { full_name: 'fork/relay' } } } } }), false);
    }
  }
}
for (const value of [condition, recovery.jobs.recover.if]) {
  assert.equal(evaluate(value, base), true);
  for (const changed of [{ actor: 'other' }, { triggering_actor: 'other' },
    { repository: 'other/relay' }, { ref: 'refs/heads/candidate' }, { ref: 'refs/tags/main' }]) {
    assert.equal(evaluate(value, { ...base, ...changed }), false);
  }
}
"""
        with tempfile.TemporaryDirectory(prefix='relay-workflow-consumer-') as temporary:
            config = Path(temporary) / 'consumer.json'
            shutil.copyfile(ROOT / 'consumer/fixtures/example.json', config)
            config.chmod(0o600)
            result = subprocess.run([NODE, '--import', './consumer/test-support/consumer-env.mjs',
                                     '--input-type=module', '-e', script], cwd=ROOT,
                                    env={**os.environ, 'RELAY_CONSUMER_CONFIG': str(config)},
                                    input=json.dumps([self.routing, self.recovery]), text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(NODE and os.name != 'nt', 'Installed-release fixtures require native Linux paths')
    def test_actual_workflow_scripts_fail_before_unaccepted_runtime_and_preserve_recovery_inputs(self):
        with tempfile.TemporaryDirectory(prefix='relay-workflows-') as temporary:
            install = Path(temporary)
            release = install / 'releases' / HEAD
            source = release / 'reviewed-source/controller/src'
            source.mkdir(parents=True)
            (release / 'bin').mkdir()
            for directory in [install, install / 'releases', release, release / 'bin', release / 'reviewed-source']:
                directory.chmod(0o751)
            (install / 'current').symlink_to(release, target_is_directory=True)
            manifest = release / 'artifact-manifest.json'
            manifest.write_text(json.dumps({'commit': HEAD}))
            manifest.chmod(0o640)
            identity = release / 'reviewed-source/.relay-source.json'
            identity.write_text(json.dumps({'revision': HEAD}))
            compatibility = release / 'reviewed-source/deploy/workflows/contract.json'
            compatibility.parent.mkdir(parents=True)
            compatibility.write_text(json.dumps({'workflowContract': 'relay-workflows-v1'}))
            identity.chmod(0o644)
            (source / 'entrypoint.mjs').write_text(
                'export async function main() { console.log("FIXTURE_ROUTING_STARTED"); }\n'
                'export async function reportRoutingResult(run) { await run(); return 0; }\n')
            (source / 'recover-attempt-publication.mjs').write_text(
                'import { readFileSync } from "node:fs";\n'
                'console.log(JSON.stringify({fixtureRequest: JSON.parse(readFileSync(0, "utf8"))}));\n')
            (release / 'bin/relay-routing.mjs').symlink_to(source / 'entrypoint.mjs')
            (release / 'bin/relay-publication-recovery.mjs').symlink_to(source / 'recover-attempt-publication.mjs')

            # A root-run qualification repeats the scripts under an unrelated
            # unprivileged identity, with the real installed 0751/0644/0640 modes.
            # Ordinary non-root suite runs still exercise the script contract.
            def drop_privileges():
                os.setgroups([])
                os.setgid(65534)
                os.setuid(65534)

            child_options = {'preexec_fn': drop_privileges} if os.geteuid() == 0 else {}
            node = NODE
            if child_options:
                # The selected toolchain may live below a private owner home.
                # Stage its executable in this fixture without widening host
                # permissions, so denial proves the manifest boundary itself.
                node = str(install / 'node')
                shutil.copyfile(NODE, node)
                Path(node).chmod(0o755)
                unreadable = subprocess.run([node, '-e', 'require("node:fs").readFileSync(process.argv[1])', str(manifest)],
                                            text=True, capture_output=True, **child_options)
                self.assertNotEqual(unreadable.returncode, 0, 'Fixture must deny the restricted manifest')
                self.assertIn('EACCES', unreadable.stderr)

            def execute(value, overrides=None):
                _, step = control_step(value)
                code = javascript(step).replace('/opt/codex-relay', install.as_posix()).replace('/usr/bin/node', node)
                environment = {**os.environ, 'EXPECTED_WORKFLOW_CONTRACT': 'relay-workflows-v1', 'GITHUB_SHA': HEAD,
                               'RECOVERY_OPERATION': 'inspect', 'RECOVERY_RUN_ID': '99',
                               'RECOVERY_ATTEMPT_ID': 'run-99', 'RECOVERY_AUTHORIZATION_ID': '',
                               **(overrides or {})}
                return subprocess.run([node, '--input-type=module', '-e', code],
                                      env=environment, text=True, capture_output=True, **child_options)

            started = execute(self.routing)
            self.assertEqual(started.returncode, 0, started.stderr)
            self.assertIn('FIXTURE_ROUTING_STARTED', started.stdout)
            for value in (self.routing, self.recovery):
                for invalid in ({'EXPECTED_WORKFLOW_CONTRACT': 'b' * 40}, {'EXPECTED_WORKFLOW_CONTRACT': '../../candidate'}):
                    blocked = execute(value, invalid)
                    self.assertNotEqual(blocked.returncode, 0)
                    self.assertIn('INSTALLED_RELAY_IDENTITY_MISMATCH', blocked.stderr)
                    self.assertNotIn('FIXTURE_ROUTING_STARTED', blocked.stdout)
                    self.assertNotIn('fixtureRequest', blocked.stdout)
                identity.write_text(json.dumps({'revision': 'b' * 40}))
                blocked = execute(value)
                self.assertNotEqual(blocked.returncode, 0)
                self.assertIn('INSTALLED_RELAY_IDENTITY_MISMATCH', blocked.stderr)
                identity.write_text(json.dumps({'revision': HEAD}))

            # A consumer commit, newer Relay main or unavailable latest-version
            # information never changes the installed runtime selection.
            for value in (self.routing, self.recovery):
                continued = execute(value, {'GITHUB_SHA': 'c' * 40, 'LATEST_RELAY_HEAD': 'd' * 40})
                self.assertEqual(continued.returncode, 0, continued.stderr)
                self.assertNotIn('warning', continued.stdout.lower())
                self.assertEqual(continued.stderr, '')
                logged = json.loads(continued.stdout.splitlines()[0])
                self.assertEqual(logged, {'installedRelayHead': HEAD, 'workflowHead': 'c' * 40})

            inspected = execute(self.recovery)
            self.assertEqual(inspected.returncode, 0, inspected.stderr)
            self.assertEqual(json.loads(inspected.stdout.splitlines()[-1])['fixtureRequest'],
                             {'operation': 'inspect', 'runId': 99, 'attemptId': 'run-99'})
            recovered = execute(self.recovery, {'RECOVERY_OPERATION': 'recover', 'RECOVERY_AUTHORIZATION_ID': '123'})
            self.assertEqual(recovered.returncode, 0, recovered.stderr)
            self.assertEqual(json.loads(recovered.stdout.splitlines()[-1])['fixtureRequest'],
                             {'runId': 99, 'attemptId': 'run-99', 'authorizationId': 123})
            for invalid in ({'RECOVERY_RUN_ID': '1; touch bad'}, {'RECOVERY_RUN_ID': '0'},
                            {'RECOVERY_RUN_ID': '99999999999999999999'}, {'RECOVERY_ATTEMPT_ID': '../run-99'},
                            {'RECOVERY_OPERATION': 'launch'}, {'RECOVERY_OPERATION': 'recover'},
                            {'RECOVERY_AUTHORIZATION_ID': '123'}):
                blocked = execute(self.recovery, invalid)
                self.assertNotEqual(blocked.returncode, 0)
                self.assertIn('RECOVERY_REQUEST_INVALID', blocked.stderr)
                self.assertNotIn('fixtureRequest', blocked.stdout)

            compatibility.write_text(json.dumps({'workflowContract': 'relay-workflows-v2'}))
            for value in (self.routing, self.recovery):
                blocked = execute(value)
                self.assertNotEqual(blocked.returncode, 0)
                self.assertIn('INSTALLED_RELAY_IDENTITY_MISMATCH', blocked.stderr)
            compatibility.unlink()
            self.assertNotEqual(execute(self.routing).returncode, 0)
            compatibility.write_text(json.dumps({'workflowContract': 'relay-workflows-v1'}))

            # An owner-installed compatible product can change without another
            # workflow projection. The resolved revision remains observable.
            next_head = 'd' * 40
            next_release = install / 'releases' / next_head
            shutil.copytree(release, next_release)
            (next_release / 'reviewed-source/.relay-source.json').write_text(json.dumps({'revision': next_head}))
            (install / 'current').unlink()
            (install / 'current').symlink_to(next_release)
            for value in (self.routing, self.recovery):
                continued = execute(value)
                self.assertEqual(continued.returncode, 0, continued.stderr)
                self.assertEqual(json.loads(continued.stdout.splitlines()[0])['installedRelayHead'], next_head)


if __name__ == '__main__':
    unittest.main()
