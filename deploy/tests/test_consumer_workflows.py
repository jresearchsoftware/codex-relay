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
from workflow_projection import render, general_pool_label


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
                group = ('codex-relay-control-${{ github.run_id }}' if value is self.routing
                         else 'codex-relay-recovery-${{ inputs.run_id }}')
                self.assertEqual(value['concurrency'], {
                    'group': group, 'cancel-in-progress': False, 'queue': 'max'})
                job, step = control_step(value)
                self.assertEqual(job['runs-on'], {'group': 'relay-general',
                    'labels': ['self-hosted', 'Linux', 'X64', general_pool_label(self_config())]})
                self.assertNotIn('permissions', job)
                self.assertNotIn('uses', step)
                self.assertEqual(step['shell'], 'bash --noprofile --norc -euo pipefail {0}')
                self.assertEqual(step['env']['GITHUB_TOKEN'], '${{ github.token }}')
                self.assertEqual(step['env']['RELAY_CONSUMER_CONFIG'], '/etc/codex-relay/consumer.json')
                self.assertEqual(step['env']['EXPECTED_WORKFLOW_CONTRACT'], 'relay-workflows-v4')
                self.assertEqual(step['env']['NODE_OPTIONS'], '')
                self.assertEqual(step['env']['NODE_PATH'], '')
                self.assertIn('codex-relay-general-runner:codex-relay-general-runner) export RELAY_EXECUTION_SLOT=primary', step['run'])
                self.assertIn('case "$RUNNER_NAME:$(/usr/bin/id -un)" in', step['run'])
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

    def test_guidance_publisher_uses_accepted_upstream_and_exact_producer(self):
        publication = workflow('publish-guidance.yml')
        self.assertEqual(publication['on']['workflow_run'], {
            'workflows': ['Public CI'], 'types': ['completed'], 'branches': ['main']})
        self.assertEqual(set(publication['on']), {'workflow_run', 'workflow_dispatch'})
        self.assertEqual(set(publication['on']['workflow_dispatch']['inputs']), {'source_sha'})
        self.assertIs(publication['on']['workflow_dispatch']['inputs']['source_sha']['required'], False)
        self.assertEqual(publication['permissions'], {'contents': 'read', 'actions': 'read'})
        self.assertNotIn('concurrency', publication)
        resolver = publication['jobs']['resolve-source']
        self.assertEqual(resolver['runs-on'], 'ubuntu-24.04')
        self.assertEqual(resolver['outputs'], {'source_sha': '${{ steps.source.outputs.source_sha }}'})
        step, = resolver['steps']
        self.assertEqual(step['id'], 'source')
        self.assertEqual(step['env'], {'MANUAL_SOURCE_SHA': '${{ inputs.source_sha }}'})
        self.assertNotIn('${{', step['run'])
        self.assertNotIn('secrets.', json.dumps(resolver))
        job = publication['jobs']['publish']
        self.assertEqual(job['needs'], 'resolve-source')
        self.assertEqual(job['if'], "needs.resolve-source.outputs.source_sha != ''")
        self.assertEqual(job['concurrency'], {
            'group': 'relay-guidance-publication-${{ needs.resolve-source.outputs.source_sha }}',
            'cancel-in-progress': False})
        self.assertEqual(job['uses'],
                         'jresearchsoftware/shared-governance/.github/workflows/vibe-publisher.yml@main')
        self.assertEqual(job['with'], {
            'mode': 'publish',
            'source_sha': '${{ needs.resolve-source.outputs.source_sha }}',
            'binding': 'vibe-publisher.json', 'package': 'org.jresearch.ai/codex-relay'})
        self.assertEqual(job['secrets'], {
            'DEVELOPMENT_GOVERNANCE_PUBLISH_TOKEN': '${{ secrets.DEVELOPMENT_GOVERNANCE_PUBLISH_TOKEN }}'})

        steps = self.validation['jobs']['publisher-readiness']['steps']
        publisher = next(step for step in steps if step.get('id') == 'publisher')
        self.assertEqual(publisher['with'], {
            'repository': 'jresearchsoftware/shared-governance', 'ref': 'main',
            'path': '.publisher', 'persist-credentials': False})
        integration = next(step for step in steps if 'scripts/test-relay-publisher.py' in step.get('run', ''))
        self.assertEqual(integration['env'], {
            'PUBLISHER_SHA': '${{ steps.publisher.outputs.commit }}',
            'SOURCE_SHA': '${{ github.event.pull_request.head.sha || github.sha }}'})
        self.assertIn('--publisher-sha "$PUBLISHER_SHA" --source-sha "$SOURCE_SHA"', integration['run'])
        self.assertIn('GITHUB_STEP_SUMMARY', integration['run'])
        check = next(step for step in steps if 'publisher.py check' in step.get('run', ''))
        self.assertEqual(check['env']['SOURCE_SHA'], integration['env']['SOURCE_SHA'])
        self.assertIn('--source . --source-sha "$SOURCE_SHA" --base "$BASE_SHA" --main "$BASE_SHA"', check['run'])
        self.assertIn('.publisher/tooling/vibe-publisher/publisher.py', check['run'])
        for step in (integration, check):
            self.assertNotIn('continue-on-error', step)
            self.assertNotIn('if', step)
            self.assertNotIn('secrets.', json.dumps(step))

    @unittest.skipUnless(NODE, 'Node is required to exercise the publication event filter')
    def test_guidance_publisher_accepts_only_bound_main_push_or_main_retry(self):
        job = workflow('publish-guidance.yml')['jobs']['resolve-source']
        script = r"""
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
const job = JSON.parse(readFileSync(0, 'utf8'));
const evaluate = (source, github, inputs) =>
  Function('github', 'inputs', `return (${source.replace(/^\$\{\{/, '').replace(/\}\}$/, '')});`)(github, inputs);
const source = 'a'.repeat(40), retry = 'b'.repeat(40);
const original = { repository: 'jresearchsoftware/codex-relay', ref: 'refs/heads/main',
  event_name: 'workflow_run', event: { workflow_run: { conclusion: 'success', event: 'push',
  head_branch: 'main', head_sha: source, head_repository: { full_name: 'jresearchsoftware/codex-relay' } } } };
const cases = [
  [g => {}, true],
  [g => { g.repository = 'foreign/repo'; }, false],
  [g => { g.event.workflow_run.conclusion = 'failure'; }, false],
  [g => { g.event.workflow_run.event = 'pull_request'; }, false],
  [g => { g.event.workflow_run.head_branch = 'topic'; }, false],
  [g => { g.event.workflow_run.head_repository.full_name = 'foreign/repo'; }, false],
  [g => { g.event_name = 'push'; }, false],
  [g => { g.event_name = 'workflow_dispatch'; g.event.workflow_run = {}; }, true],
  [g => { g.event_name = 'workflow_dispatch'; g.ref = 'refs/heads/topic'; }, false],
];
for (const [change, expected] of cases) {
  const github = structuredClone(original); change(github);
  assert.equal(evaluate(job.if, github, {source_sha: retry}), expected);
}
"""
        checked = subprocess.run([NODE, '--input-type=module', '-e', script], cwd=ROOT,
                                 input=json.dumps(job), text=True, capture_output=True)
        self.assertEqual(checked.returncode, 0, checked.stderr)

    @unittest.skipUnless(shutil.which('bash'), 'Bash is required to execute source resolution')
    def test_guidance_source_resolution_uses_exact_event_identity(self):
        # Exercise the actual workflow code without checkout, credentials or API
        # transport. Accepted-main membership and exact successful source CI are
        # separate Shared Publisher checks in scripts/test-relay-publisher.py.
        resolver = workflow('publish-guidance.yml')['jobs']['resolve-source']
        step, = resolver['steps']
        dispatch_sha, explicit_sha, automatic_sha = ('a' * 40, 'b' * 40, 'c' * 40)
        run = {'conclusion': 'success', 'event': 'push', 'head_branch': 'main',
               'head_sha': automatic_sha,
               'head_repository': {'full_name': 'jresearchsoftware/codex-relay'}}

        def resolve(event_name='workflow_dispatch', supplied='', event=None, changes=None):
            with tempfile.TemporaryDirectory(prefix='relay-source-resolution-') as directory:
                root = Path(directory)
                event_path, output, summary = (root / name for name in ('event.json', 'output', 'summary'))
                event_path.write_text(json.dumps({'workflow_run': run} if event is None else event))
                environment = {key: os.environ[key] for key in ('PATH', 'SYSTEMROOT', 'LANG', 'LC_ALL')
                               if key in os.environ}
                environment.update(GITHUB_REPOSITORY='jresearchsoftware/codex-relay',
                                   GITHUB_REF='refs/heads/main', GITHUB_EVENT_NAME=event_name,
                                   GITHUB_SHA=dispatch_sha, GITHUB_EVENT_PATH=str(event_path),
                                   GITHUB_OUTPUT=str(output), GITHUB_STEP_SUMMARY=str(summary))
                if supplied is not None:
                    environment['MANUAL_SOURCE_SHA'] = supplied
                for key, value in (changes or {}).items():
                    if value is None:
                        environment.pop(key, None)
                    else:
                        environment[key] = value
                checked = subprocess.run(['bash', '--noprofile', '--norc', '-euo', 'pipefail', '-c', step['run']],
                                         cwd=root, env=environment, text=True, capture_output=True)
                return (checked, output.read_text() if output.exists() else '',
                        summary.read_text() if summary.exists() else '')

        for supplied, event, expected in (
            (None, {}, dispatch_sha), ('', {}, dispatch_sha),
            (None, {'workflow_run': run, 'inputs': {'source_sha': explicit_sha}}, dispatch_sha),
            ('', {'workflow_run': run, 'inputs': {'source_sha': explicit_sha}}, dispatch_sha),
            (explicit_sha, {'workflow_run': run}, explicit_sha),
        ):
            with self.subTest(supplied=supplied, event=event):
                checked, output, summary = resolve(supplied=supplied, event=event)
                self.assertEqual(checked.returncode, 0, checked.stderr)
                self.assertEqual(output, f'source_sha={expected}\n')
                self.assertIn(expected, summary)
                self.assertIn('Shared Publisher must qualify', summary)
        checked, output, summary = resolve(event_name='workflow_run', supplied=explicit_sha)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertEqual(output, f'source_sha={automatic_sha}\n')
        self.assertIn('workflow_run.head_sha', summary)

        rejected = [
            {'supplied': value} for value in
            ('main', 'abc123', 'B' * 40, 'g' * 40, ' ' + explicit_sha, explicit_sha + '\n')
        ]
        rejected += [
            {'changes': {'GITHUB_SHA': value}} for value in ('', 'main', None)
        ]
        rejected += [
            {'changes': {'GITHUB_REF': ref}} for ref in ('refs/heads/topic', 'refs/tags/main')
        ]
        rejected += [{'changes': {'GITHUB_REPOSITORY': 'foreign/repo'}}, {'event_name': 'push'}]
        for field, value in (
            ('head_sha', ''), ('head_sha', 'main'), ('head_sha', 'D' * 40),
            ('head_branch', 'topic'), ('conclusion', 'failure'), ('conclusion', 'cancelled'),
            ('event', 'pull_request'), ('head_repository', {'full_name': 'foreign/repo'}),
        ):
            rejected.append({'event_name': 'workflow_run', 'event': {'workflow_run': {**run, field: value}}})
        rejected += [
            {'event_name': 'workflow_run', 'event': {}},
            {'event_name': 'workflow_run',
             'event': {'workflow_run': {key: value for key, value in run.items() if key != 'head_sha'}}},
        ]
        for case in rejected:
            with self.subTest(rejected=case):
                checked, output, _ = resolve(**case)
                self.assertNotEqual(checked.returncode, 0, checked.stdout)
                self.assertEqual(output, '', 'Rejected events must not produce a publishable source')

    @unittest.skipUnless(NODE, 'Node is required to compare native launch metadata')
    def test_native_names_and_owner_event_conditions(self):
        # Evaluate the small GitHub expression subset actually used by these
        # workflows, then compare native names to the real controller contract.
        # No repository execution or GitHub calls are performed.
        script = r"""
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dispatchRunName, labelRunName } from './controller/src/launch-metadata.mjs';
import { authorityMode } from './contracts/src/github-authority.mjs';
const [routing, recovery] = JSON.parse(readFileSync(0, 'utf8'));
const evaluate = (source, github, inputs = {}) => {
  const expression = source.trim().replace(/^\$\{\{/, '').replace(/\}\}$/, '')
    // GitHub strings escape apostrophes by doubling them; backslashes stay
    // literal until fromJSON explicitly decodes a JSON value.
    .replace(/'(?:[^']|'')*'/g, token => JSON.stringify(token.slice(1, -1).replace(/''/g, "'")))
    .replace(/\.labels\.\*\.name/g, '.labels.map(label => label.name)');
  const format = (template, ...values) => template.replace(/\{([0-9]+)\}/g, (_, index) => values[Number(index)]);
  return Function('github', 'inputs', 'format', 'join', 'contains', 'fromJSON', `return (${expression});`)
    (github, inputs, format, (values, separator) => values.join(separator),
      (value, part) => String(value ?? '').toLowerCase().includes(String(part).toLowerCase()), JSON.parse);
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
    if (target === 'issue') {
      assert.equal(evaluate(routing['run-name'], github),
        `${route === 'manual' ? 'Manual handoff' : 'Auto implementation'} · Task 27 · codex-ready-${route}`);
      const marker = 'Authority model: github-native-v1';
      for (const body of [`Example migration marker: \`${marker}\``, `Quoted marker: "${marker}"`,
        `Before ${marker}`, `> ${marker}`, `\\n${marker}\\n`,
        JSON.stringify(`\n${marker}\n`), `example authority model: GITHUB-NATIVE-V1`]) {
        const unmarked = { ...subject, body };
        assert.equal(authorityMode(body), 'legacy');
        assert.equal(evaluate(routing['run-name'], { ...github, event: { ...github.event, issue: unmarked } }), labelRunName(launch, unmarked), body);
      }
      for (const body of [marker, `${marker}\nCharter`, `Charter\n${marker}\nScope`, `Charter\n${marker}`,
        `${marker}\r\nCharter`, `Charter\r\n${marker}\r\nScope`, `Charter\r\n${marker}`, `\`\`\`\n${marker}\n\`\`\``]) {
        const native = { ...subject, body, labels: [{ name: 'step-900' }, { name: `codex-ready-${route}` }] };
        assert.equal(authorityMode(body), 'github-native-v1');
        assert.equal(evaluate(routing['run-name'], { ...github, event: { ...github.event, issue: native } }), labelRunName(launch, native), body);
        assert.equal(evaluate(routing['run-name'], { ...github, event: { ...github.event, issue: native } }),
          `${route === 'manual' ? 'Manual handoff' : 'Auto implementation'} · Task 27 · codex-ready-${route}`);
      }
      for (const body of ['authority model: github-native-v1', ` ${marker}`, `${marker} `, `${marker} after`, `- ${marker}`, `${marker}\n${marker}`]) {
        assert.throws(() => authorityMode(body), { code: 'AUTHORITY_MODEL_INVALID' });
      }
      const newInputs = { ...inputs, step: '' };
      assert.equal(evaluate(routing['run-name'], base, newInputs), dispatchRunName({ ...launch, step: null }));
    }
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
                    self.assertIn('RELAY_REPOSITORY_INTEGRATION_OUTDATED', blocked.stderr)
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
            for operation in ['inspect-prepublication', 'recover-prepublication']:
                inputs = {'RECOVERY_OPERATION': operation, 'RECOVERY_HEAD': HEAD}
                if operation == 'recover-prepublication':
                    inputs['RECOVERY_AUTHORIZATION_ID'] = '123'
                retained = execute(self.recovery, inputs)
                self.assertEqual(retained.returncode, 0, retained.stderr)
                expected = {'operation': operation, 'runId': 99, 'attemptId': 'run-99', 'head': HEAD}
                if operation == 'recover-prepublication':
                    expected['authorizationId'] = 123
                self.assertEqual(json.loads(retained.stdout.splitlines()[-1])['fixtureRequest'], expected)
            for invalid in ({'RECOVERY_RUN_ID': '1; touch bad'}, {'RECOVERY_RUN_ID': '0'},
                            {'RECOVERY_RUN_ID': '99999999999999999999'}, {'RECOVERY_ATTEMPT_ID': '../run-99'},
                            {'RECOVERY_OPERATION': 'launch'}, {'RECOVERY_OPERATION': 'recover'},
                            {'RECOVERY_AUTHORIZATION_ID': '123'}, {'RECOVERY_HEAD': HEAD},
                            {'RECOVERY_OPERATION': 'inspect-prepublication'},
                            {'RECOVERY_OPERATION': 'recover-prepublication', 'RECOVERY_HEAD': HEAD},
                            {'RECOVERY_OPERATION': 'inspect-prepublication', 'RECOVERY_HEAD': '../candidate'},
                            {'RECOVERY_OPERATION': 'inspect-prepublication', 'RECOVERY_HEAD': HEAD,
                             'RECOVERY_AUTHORIZATION_ID': '123'}):
                blocked = execute(self.recovery, invalid)
                self.assertNotEqual(blocked.returncode, 0)
                self.assertIn('RECOVERY_REQUEST_INVALID', blocked.stderr)
                self.assertNotIn('fixtureRequest', blocked.stdout)

            compatibility.write_text(json.dumps({'workflowContract': 'relay-workflows-v3'}))
            for value in (self.routing, self.recovery):
                blocked = execute(value)
                self.assertNotEqual(blocked.returncode, 0)
                self.assertIn('RELAY_REPOSITORY_INTEGRATION_OUTDATED', blocked.stderr)
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
