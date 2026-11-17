"""Execute both generated owner workflows against local receipt-only helpers."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
from workflow_projection import PRODUCTION, render, render_deployment
from test_consumer_workflows import javascript, self_config

REQUESTED = 'a' * 40
INSTALLED = 'b' * 40
CONFIG = 'c' * 40
RETAINED_CONFIG = 'd' * 40
NODE = shutil.which('node')


@pytest.fixture(params=['git', 'installed'])
def workflow_fixture(request, tmp_path):
    config = self_config()
    if request.param == 'git':
        config['environment']['localApply'] = {'source': 'git', 'repository': 'example/private', 'configPath': 'prod.json'}
        rendered = render_deployment(config, REQUESTED, ROOT)
        assert rendered == render_deployment(config, INSTALLED, ROOT)
    else:
        rendered = render(config, REQUESTED, ROOT)
        assert rendered == render(config, INSTALLED, ROOT)
    workflow = yaml.safe_load(rendered[PRODUCTION])
    assert '${{ github.run_number }}.${{ github.run_attempt }}' in workflow['run-name']
    job, = workflow['jobs'].values()
    step, = job['steps']
    install = tmp_path / 'install'
    release = install / 'releases' / INSTALLED
    source = release / 'reviewed-source'
    (source / 'deploy/workflows').mkdir(parents=True)
    (source / '.relay-source.json').write_text(json.dumps({'revision': INSTALLED}))
    (source / 'deploy/workflows/contract.json').write_text(json.dumps({
        'workflowContract': 'relay-workflows-v3', 'parallelWorkflowContract': 'relay-workflows-v4'}))
    (install / 'current').symlink_to(release)
    helper = tmp_path / 'sudo-fixture'
    summary = tmp_path / 'summary'
    code = javascript(step).replace('/opt/codex-relay', str(install)).replace('/usr/bin/sudo', str(helper))

    def run(lines, exit_code=0, sha=CONFIG, output_error=False):
        helper.write_text('#!' + sys.executable + '\nimport sys\n'
                          + 'print(' + repr('\n'.join(lines)) + ')\nsys.exit(' + str(exit_code) + ')\n')
        helper.chmod(0o755)
        summary.write_text('')
        program = code
        if output_error:
            program = program.replace('await new Promise(resolve => {',
                'setImmediate(() => child.stdout.emit("error",Object.assign(new Error("private-output-error"),{code:"EIO"})));\nawait new Promise(resolve => {')
        result = subprocess.run([NODE, '--input-type=module', '-e', program], text=True, capture_output=True,
            env={**os.environ, 'GITHUB_SHA': sha, 'GITHUB_RUN_ID': '123',
                 'EXPECTED_WORKFLOW_CONTRACT': 'relay-workflows-v4', 'RELAY_LIFECYCLE_ACTION': 'apply',
                 'GITHUB_STEP_SUMMARY': str(summary)})
        return result, summary.read_text()
    return run, request.param


@pytest.mark.skipif(not NODE, reason='Node required for projected workflow fixtures')
def test_summary_distinguishes_requested_pair_from_verified_retained_installation(workflow_fixture):
    run, kind = workflow_fixture
    receipt = (f'RELAY_OWNER_LIFECYCLE_RESULT=OPEN;requested={REQUESTED};config={CONFIG};'
               f'installed={INSTALLED};installed_config={RETAINED_CONFIG}')
    pair = 'RELAY_GIT_PAIR=' + json.dumps({'product_sha': REQUESTED, 'config_sha': CONFIG})
    result, summary = run([pair, receipt])
    assert result.returncode == 0, result.stderr
    assert f'| Requested product | {REQUESTED} |' in summary
    assert f'| Requested configuration/workflow | {CONFIG} |' in summary
    assert f'| Verified installed product | {INSTALLED} |' in summary
    assert f'| Verified installed configuration | {RETAINED_CONFIG} |' in summary
    assert '| Lifecycle outcome | OPEN |' in summary


@pytest.mark.skipif(not NODE, reason='Node required for projected workflow fixtures')
@pytest.mark.parametrize('failure', ['child-failed', 'missing-receipt', 'invalid-receipt', 'invalid-dispatch'])
def test_failure_or_unknown_proof_never_reports_installed_success(workflow_fixture, failure):
    run, _kind = workflow_fixture
    receipt = (f'RELAY_OWNER_LIFECYCLE_RESULT=OPEN;requested={REQUESTED};config={CONFIG};'
               f'installed={INSTALLED};installed_config={RETAINED_CONFIG}')
    lines = [receipt] if failure == 'child-failed' else (
        ['RELAY_GIT_PAIR={"product_sha":"private-config-value"}', receipt + ';private=private-config-value']
        if failure == 'invalid-receipt' else [])
    result, summary = run(lines, 7 if failure == 'child-failed' else 0,
                          sha='main' if failure == 'invalid-dispatch' else CONFIG)
    assert f'| Verified installed product | unknown |' in summary
    assert '| Lifecycle outcome | OPEN |' not in summary
    assert 'private-config-value' not in summary
    assert result.returncode != 0 if failure in ['child-failed', 'invalid-dispatch'] else result.returncode == 0


@pytest.mark.skipif(not NODE, reason='Node required for projected workflow fixtures')
def test_generated_workflow_handles_output_error_and_awaits_failed_close(workflow_fixture):
    run, _kind = workflow_fixture
    receipt = (f'RELAY_OWNER_LIFECYCLE_RESULT=OPEN;requested={REQUESTED};config={CONFIG};'
               f'installed={INSTALLED};installed_config={RETAINED_CONFIG}')
    result, summary = run([receipt], output_error=True)
    assert result.returncode != 0
    assert 'helper-output-failed;code=EIO' in result.stderr
    assert 'private-output-error' not in result.stderr
    assert '| Verified installed product | unknown |' in summary
    assert '| Lifecycle outcome | OPEN |' not in summary


@pytest.mark.parametrize('git_mode', [False, True])
def test_runner_guard_refusal_still_leaves_an_explicit_unknown_summary(tmp_path, git_mode):
    config = self_config()
    if git_mode:
        config['environment']['localApply'] = {'source': 'git', 'repository': 'example/private', 'configPath': 'prod.json'}
    workflow = yaml.safe_load((render_deployment if git_mode else render)(config, REQUESTED, ROOT)[PRODUCTION])
    job, = workflow['jobs'].values()
    step, = job['steps']
    summary = tmp_path / 'guard-summary'
    result = subprocess.run(['bash', '--noprofile', '--norc', '-euo', 'pipefail'], input=step['run'], text=True,
        capture_output=True, env={**os.environ, 'RUNNER_NAME': 'foreign-unregistered-runner',
            'RELAY_LIFECYCLE_ACTION': 'apply', 'GITHUB_STEP_SUMMARY': str(summary)})
    assert result.returncode != 0
    assert 'RELAY_RUNNER_SLOT_IDENTITY_MISMATCH' in result.stderr
    assert 'installed revisions unknown' in summary.read_text()


@pytest.mark.skipif(not NODE, reason='Node required for projected workflow fixtures')
def test_input_transport_failure_cannot_be_replaced_by_successful_close(tmp_path):
    """Replay the event ordering that previously replaced EPIPE with exit zero."""
    observer = (ROOT / 'deploy/workflows/lifecycle-observer.js.in').read_text()
    receipt = (f'RELAY_OWNER_LIFECYCLE_RESULT=OPEN;requested={REQUESTED};config={CONFIG};'
               f'installed={INSTALLED};installed_config={RETAINED_CONFIG}')
    summary = tmp_path / 'summary'
    code = ('import {appendFile} from "node:fs/promises";\n' + observer
        + '\nreport.observe(Buffer.from(' + json.dumps(receipt + '\n') + '));'
        + '\nreport.transportFailed({code:"EPIPE",message:"private-token"},"helper-input");'
        + '\nreport.finish(0);await report.write();')
    result = subprocess.run([NODE, '--input-type=module', '-e', code], capture_output=True, text=True,
        env={**os.environ, 'GITHUB_SHA': CONFIG, 'GITHUB_STEP_SUMMARY': str(summary)})
    assert result.returncode == 0, result.stderr
    assert 'helper-input-failed;code=EPIPE' in result.stderr and 'private-token' not in result.stderr
    assert '| Verified installed product | unknown |' in summary.read_text()
    assert '| Lifecycle outcome | OPEN |' not in summary.read_text()
