"""Execute the production workflow gate with synthetic installed state only."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_consumer_workflows import HEAD, NODE, control_step, javascript, workflow


class ProductionWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.workflow = workflow('manual-main-production-deploy.yml')
        self.job, self.step = control_step(self.workflow)

    def test_only_manual_owner_main_can_schedule_in_explicit_production_group(self):
        self.assertEqual(self.workflow['on'], {'workflow_dispatch': None})
        self.assertEqual(self.workflow['permissions'], {'contents': 'read'})
        self.assertEqual(self.workflow['concurrency'], {'group': 'codex-relay-production', 'cancel-in-progress': False})
        self.assertEqual(self.job['runs-on'], {
            'group': 'codex-relay-runner', 'labels': ['self-hosted', 'Linux', 'X64', 'codex-relay']})
        self.assertNotIn('uses', self.step)
        self.assertEqual(self.step['shell'], 'bash --noprofile --norc -euo pipefail {0}')
        self.assertEqual(self.step['env'], {'EXPECTED_WORKFLOW_CONTRACT': 'relay-workflows-v1', 'NODE_OPTIONS': '', 'NODE_PATH': ''})
        self.assertNotIn('${{', self.step['run'])
        self.assertIn('test "$RUNNER_NAME" = codex-relay-runner', self.step['run'])
        self.assertIn('test "$(/usr/bin/id -un)" = codex-relay-runner', self.step['run'])
        for forbidden in ['checkout', 'ansible', 'ssh ', 'inputs.', 'GITHUB_TOKEN']:
            self.assertNotIn(forbidden, self.step['run'])
        if shutil.which('bash') and os.name != 'nt':
            checked = subprocess.run(['bash', '-n'], input=self.step['run'], text=True, capture_output=True)
            self.assertEqual(checked.returncode, 0, checked.stderr)

    @unittest.skipUnless(NODE, 'Node is required to evaluate native owner conditions')
    def test_native_conditions_reject_fork_candidate_event_and_nonowner_rerun(self):
        code = r'''
        import assert from 'node:assert/strict';
        import { readFileSync } from 'node:fs';
        const expression = JSON.parse(readFileSync(0, 'utf8')).trim().slice(3, -2);
        const evaluate = Function('github', `return (${expression});`);
        const base = { repository: 'jresearchsoftware/codex-relay', event_name: 'workflow_dispatch',
          actor: 'foal', triggering_actor: 'foal', ref: 'refs/heads/main' };
        assert.equal(evaluate(base), true);
        for (const changed of [{repository:'fork/relay'}, {event_name:'pull_request'},
          {event_name:'pull_request_target'}, {event_name:'push'}, {actor:'other'},
          {triggering_actor:'other'}, {ref:'refs/heads/candidate'}, {ref:'refs/tags/main'}]) {
          assert.equal(evaluate({...base, ...changed}), false);
        }
        '''
        checked = subprocess.run([NODE, '--input-type=module', '-e', code],
                                 input=json.dumps(self.job['if']), text=True, capture_output=True)
        self.assertEqual(checked.returncode, 0, checked.stderr)

    @unittest.skipUnless(NODE and os.name != 'nt', 'Installed-state execution requires Linux')
    def test_single_typed_argument_binds_pinned_product_and_distinct_consumer(self):
        with tempfile.TemporaryDirectory(prefix='relay-production-workflow-') as temporary:
            install = Path(temporary)
            release = install / 'releases' / HEAD
            (release / 'reviewed-source').mkdir(parents=True)
            (install / 'current').symlink_to(release, target_is_directory=True)
            identity = release / 'reviewed-source/.relay-source.json'
            identity.write_text(json.dumps({'revision': HEAD}))
            compatibility = release / 'reviewed-source/deploy/workflows/contract.json'
            compatibility.parent.mkdir(parents=True)
            compatibility.write_text(json.dumps({'workflowContract': 'relay-workflows-v1'}))
            # Replace only the fixed executable/path in the real workflow script.
            # The fixture records invocation; it never invokes sudo or deploys.
            stub = install / 'sudo-fixture'
            stub.write_text('#!/usr/bin/python3\nimport json,os,sys\n'
                            'print("FIXTURE_HELPER="+json.dumps(sys.argv[1:]))\n'
                            'sys.exit(int(os.environ.get("FIXTURE_EXIT","0")))\n')
            stub.chmod(0o755)
            code = javascript(self.step).replace('/opt/codex-relay', str(install)).replace('/usr/bin/sudo', str(stub))

            def run(**overrides):
                return subprocess.run([NODE, '--input-type=module', '-e', code], text=True, capture_output=True,
                    env={**os.environ, 'EXPECTED_WORKFLOW_CONTRACT': 'relay-workflows-v1', 'GITHUB_SHA': 'c' * 40, **overrides})

            good = run()
            self.assertEqual(good.returncode, 0, good.stderr)
            line = next(line for line in good.stdout.splitlines() if line.startswith('FIXTURE_HELPER='))
            self.assertEqual(json.loads(line.split('=', 1)[1]),
                             ['-n', str(install / 'relay-production-local-apply'), HEAD + ':' + 'c' * 40])
            for invalid in [{'EXPECTED_WORKFLOW_CONTRACT': 'b' * 40}, {'EXPECTED_WORKFLOW_CONTRACT': '../../candidate'},
                            {'EXPECTED_WORKFLOW_CONTRACT': ''}, {'GITHUB_SHA': 'main'}, {'GITHUB_SHA': ''},
                            {'GITHUB_SHA': HEAD + ':' + HEAD}, {'EXPECTED_WORKFLOW_CONTRACT': 'relay-workflows-v1' + ':' + HEAD}]:
                blocked = run(**invalid)
                self.assertNotEqual(blocked.returncode, 0)
                self.assertNotIn('FIXTURE_HELPER=', blocked.stdout)
            identity.write_text(json.dumps({'revision': 'b' * 40}))
            blocked = run()
            self.assertNotEqual(blocked.returncode, 0)
            self.assertNotIn('FIXTURE_HELPER=', blocked.stdout)
            identity.write_text(json.dumps({'revision': HEAD}))
            self.assertEqual(run(FIXTURE_EXIT='64').returncode, 64)
            compatibility.write_text(json.dumps({'workflowContract': 'relay-workflows-v2'}))
            self.assertNotEqual(run().returncode, 0)
            compatibility.write_text(json.dumps({'workflowContract': 'relay-workflows-v1'}))
            next_head = 'd' * 40
            next_release = install / 'releases' / next_head
            shutil.copytree(release, next_release)
            (next_release / 'reviewed-source/.relay-source.json').write_text(json.dumps({'revision': next_head}))
            (install / 'current').unlink()
            (install / 'current').symlink_to(next_release)
            compatible = run()
            self.assertEqual(compatible.returncode, 0, compatible.stderr)
            line = next(line for line in compatible.stdout.splitlines() if line.startswith('FIXTURE_HELPER='))
            self.assertEqual(json.loads(line.split('=', 1)[1])[-1], next_head + ':' + 'c' * 40)
            stub.unlink()
            self.assertNotEqual(run().returncode, 0)
