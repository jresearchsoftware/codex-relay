"""Generated recovery code parses and routes protected receipts to their slot."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
import clean_reinstall
from config import load


def inputs():
    return load(ROOT / 'deploy/example.json', ROOT)


@pytest.mark.skipif(not shutil.which('node'), reason='Node required')
def test_generated_candidate_admission_has_one_consumer_binding_and_valid_module_syntax():
    source = clean_reinstall.recovery_admission_program(inputs())
    parsed = subprocess.run(['node', '--check', '--input-type=module'], input=source,
                            text=True, capture_output=True)
    assert parsed.returncode == 0, parsed.stderr
    assert source.count('import { CONSUMER, CONSUMER_DIGEST, CONSUMER as INSTALLATION_CONSUMER }') == 1
    assert 'configuredRepositories' not in source
    assert '../../consumer/' not in source


@pytest.mark.skipif(not shutil.which('node'), reason='Node required')
def test_generated_recovery_module_links_all_dependencies_from_retained_source(tmp_path):
    source = clean_reinstall.recovery_admission_program(inputs(), source_base=ROOT.as_uri() + '/')
    # Link and evaluate the real generated module outside the source checkout.
    # Stop before the privileged state reader: this needs no root, gate or API.
    source = source.split('assertRootConsumer(process.env.RELAY_CONSUMER_CONFIG);', 1)[0]
    source += '\nconsole.log("REINSTALL_ADMISSION_MODULE_LINKED");\n'
    environment = {key: value for key, value in os.environ.items() if not key.startswith('RELAY_')}
    environment['RELAY_CONSUMER_CONFIG'] = str(ROOT / 'consumer/fixtures/example.json')
    result = subprocess.run(['node', '--input-type=module'], input=source, cwd=tmp_path,
                            env=environment, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'REINSTALL_ADMISSION_MODULE_LINKED'


@pytest.mark.parametrize('slot, expected', [('primary', '/var/lib/codex-relay/dispatch/attempts-v2'),
                                          ('pool-2', '/var/lib/codex-relay/slots/pool-2/dispatch/attempts-v2'),
                                          ('foreign', None)])
def test_candidate_recovery_journal_reads_only_the_original_protected_configured_slot(slot, expected):
    source = clean_reinstall.recovery_admission_program(inputs())
    # Execute the actual generated adapter with a protected-store fixture; no
    # caller path is accepted, and no installed or credential bytes are read.
    adapter = source.split('const store = createAttemptStore(', 1)[1].split('const admission = ', 1)[0]
    adapter = 'const store = createAttemptStore(' + adapter
    program = 'const CONSUMER=' + json.dumps(inputs()['consumer']) + ';\n'
    program += 'const fail=code=>{throw Error(code)};const paths=[];\n'
    program += 'const createAttemptStore=path=>({get:async runId=>{paths.push(path); return path.endsWith("/publication-v2") ? {envelope:{executionSlot:' + json.dumps(slot) + '}} : {runId,path}}});\n'
    program += adapter + '\ntry { console.log(JSON.stringify(await journal.get("101"))) } catch(e){console.error(e.message);process.exitCode=1;}\n'
    result = subprocess.run(['node', '--input-type=module', '-e', program], text=True, capture_output=True)
    if expected is None:
        assert result.returncode != 0 and 'EXECUTION_SLOT_INVALID' in result.stderr
    else:
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == {'runId': '101', 'path': expected}



@pytest.mark.skipif(not shutil.which('node'), reason='Node required')
def test_generated_singleton_recovery_uses_retained_metadata_without_new_retained_exports(tmp_path):
    # Older accepted singleton runtimes expose CONSUMER/digest and the parser,
    # without the new installation-level/progress helper exports. Link the
    # actual generated module against that historical dependency surface.
    retained = tmp_path / 'retained'
    consumer = inputs()['consumer']
    modules = {
        'consumer/consumer.mjs': 'export const CONSUMER=' + json.dumps(consumer) + ';export const CONSUMER_DIGEST="' + 'a' * 64 + '";',
        'consumer/consumer-config.mjs': 'export const parseConsumerJson=JSON.parse;export const assertRootConsumer=()=>{};',
        'controller/src/execution-contract.mjs': 'export const digest=()=>"";export const exactSha=()=>true;export const fail=code=>{throw Error(code)};export const positive=Number.isSafeInteger;export const VERSION=2;export const REPOSITORY=' + json.dumps(consumer['repository']) + ';',
        'contracts/src/github-authority.mjs': 'export const admissionBinding=()=>{};export const canonicalAuthorityJson=JSON.stringify;export const validateAuthorityRecord=()=>{};',
        'controller/src/predispatch-recovery.mjs': 'export const completedPredispatchRecovery=()=>false;export const pendingPredispatchRecord=()=>false;export const predispatchNoWorkerRecord=()=>false;export const consumedPredispatchMarker=()=>false;',
        'controller/src/execution-effects.mjs': 'export const manualAttemptHasConflictingActivity=()=>false;export const attemptHasPendingPublicationEffects=()=>false;',
        'controller/src/attempt-store.mjs': 'export const createAttemptStore=()=>{};',
    }
    for name, content in modules.items():
        path = retained / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    source = clean_reinstall.recovery_admission_program(inputs(), source_base=retained.as_uri() + '/')
    source = source.split('assertRootConsumer(process.env.RELAY_CONSUMER_CONFIG);', 1)[0]
    slot = consumer['executionSlots'][-1]['id']
    source += '\nconsole.log(JSON.stringify(verifiedPendingLocation({repository:CONSUMER.repository,executionSlot:' + json.dumps(slot) + '})));'
    result = subprocess.run(['node', '--input-type=module'], input=source, cwd=tmp_path,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {'repository': consumer['repository'], 'executionSlot': slot}


@pytest.mark.skipif(not shutil.which('node'), reason='Node required')
def test_generated_singleton_recovery_does_not_invent_missing_or_foreign_location(tmp_path):
    source = clean_reinstall.recovery_admission_program(inputs(), source_base=ROOT.as_uri() + '/')
    source = source.split('assertRootConsumer(process.env.RELAY_CONSUMER_CONFIG);', 1)[0]
    source += '\nconsole.log(JSON.stringify([verifiedPendingLocation({repository:CONSUMER.repository}),verifiedPendingLocation({repository:"foreign/private",executionSlot:"primary"})]));'
    environment = {key: value for key, value in os.environ.items() if not key.startswith('RELAY_')}
    environment['RELAY_CONSUMER_CONFIG'] = str(ROOT / 'consumer/fixtures/example.json')
    result = subprocess.run(['node', '--input-type=module'], input=source, cwd=tmp_path,
                            env=environment, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [{'repository': 'example-org/sample-project'}, {}]
