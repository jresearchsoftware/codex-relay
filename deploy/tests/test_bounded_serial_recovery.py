"""Real composite admission/publisher proof in disposable Linux namespaces.

The migration receipt and native GitHub responses are explicit synthetic
fixtures. Retained source is the exact incident Git revision; its original
reader, current installed composite reader, signing, stores, locks and publisher
execute unchanged. This proves neither a real migration nor installed services.
"""
import copy
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys
import tempfile
import time

import pytest

from test_bounded_install_recovery import BASELINE, Incident, NODE, OPERATION, ROOT, write
sys.path.insert(0, str(ROOT / 'deploy/ansible/tests'))
from test_git_consumer_history_recovery import HISTORY


pytestmark = pytest.mark.skipif(sys.platform != 'linux' or os.geteuid() != 0,
    reason='real root mount/network/PID namespaces required')
MIGRATION = '22345678-1234-4234-8234-123456789abc'

# Only the GitHub HTTP boundary is synthetic. Native auth really parses the
# fixture env, signs with its ephemeral RSA key and requests read-only scope.
NATIVE = r"""
import {readFileSync,existsSync} from 'node:fs';
import {renderAuthorityRecord,sha256Body} from './contracts/src/github-authority.mjs';
const consumer=JSON.parse(readFileSync(process.env.RELAY_CONSUMER_CONFIG)),repository=consumer.repository;
const owner={login:consumer.owner,id:100,type:'User'};
const reviewer={login:consumer.reviewerApp.expectedActor,id:101,type:'Bot'};
const body='Authority model: github-native-v1\nIssue closure policy: keep-open';
const decision={schema_version:'4.0',kind:'decision',repository,task:1410,parent:{kind:'issue',number:1410},
 charter_sha256:sha256Body(body),purpose:'Withdraw this synthetic original route.',
 amendments:{boundaries:['No execution result or fresh admission is created.']},context:[],supersedes:null};
const comment={id:10410,issue_url:`https://api.github.com/repos/${repository}/issues/1410`,
 user:reviewer,body:renderAuthorityRecord(decision)};
globalThis.fetch=async(url,options={})=>{
 const path=new URL(url).pathname;let value;
 if(path===`/app/installations/${consumer.writerApp.installationId}/access_tokens`){
  const p=JSON.parse(options.body);
  if(options.method!=='POST'||JSON.stringify(p.permissions)!==JSON.stringify({metadata:'read',issues:'read',pull_requests:'read'}))
   throw Error('fixture rejected expanded App authority');
  value={token:'synthetic-read-only-fixture',expires_at:new Date(Date.now()+1800000).toISOString()};
 }else if(path===`/users/${encodeURIComponent(owner.login)}`)value=owner;
 else if(path===`/users/${encodeURIComponent(reviewer.login)}`)value=reviewer;
 else{
  const m=path.match(/\/issues\/(\d+)(?:\/(events|comments))?$/);
  if(!m)throw Error('fixture rejected unexpected native route');
  const task=Number(m[1]),route=task===1410,kind=m[2];
  const reopened=task===1401&&existsSync(new URL('./synthetic-reopened-task',import.meta.url));
  if(kind==='events')value=route?[]:[{id:task,event:'closed',actor:owner,created_at:'2026-11-03T10:00:00Z'},
   ...(reopened?[{id:task+1,event:'reopened',actor:owner,created_at:'2026-11-03T10:01:00Z'}]:[])];
  else if(kind==='comments')value=route?[comment]:[];
  else value={id:10000+task,number:task,body,state:route||reopened?'open':'closed',
   state_reason:reopened?'reopened':route?null:task===1409?'not_planned':'completed',closed_by:route||reopened?null:owner,
   url:`https://api.github.com/repos/${repository}/issues/${task}`};
 }
 return new Response(JSON.stringify(value));
};
"""


def node(source, consumer, program, *arguments, preload=None):
    command = ['/usr/bin/node']
    if preload:
        command += ['--import', str(preload)]
    result = subprocess.run([*command, '--input-type=module', '-e', program, '--', *map(str, arguments)],
        cwd=source, env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C',
            'RELAY_CONSUMER_CONFIG': str(consumer)}, text=True, capture_output=True, timeout=180)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def harness(root, *, mixed=False):
    """Child-only mount changes disappear when this network-isolated process exits."""
    run = subprocess.run
    run(['mount', '--make-rprivate', '/'], check=True)
    incident = Incident(root)
    for relative in ('etc', 'opt', 'var/lib'):
        (root / relative).mkdir(parents=True, exist_ok=True)
    for name in ('passwd', 'group', 'nsswitch.conf', 'ld.so.cache'):
        path = Path('/etc') / name
        if path.is_file():
            shutil.copyfile(path, root / 'etc' / name)
    for relative in ('etc', 'opt', 'var/lib'):
        run(['mount', '--bind', str(root / relative), '/' + relative], check=True)
    run(['mount', '--bind', str(NODE), '/usr/bin/node'], check=True)
    assert all(line.split()[0] in ('Iface', 'lo') for line in Path('/proc/net/route').read_text().splitlines())
    namespace = incident.namespace
    consumer = Path('/etc') / namespace / 'consumer.json'
    install = Path('/opt') / namespace
    release = install / 'releases' / BASELINE
    retained = install / 'serial-compat-v1' / BASELINE
    shutil.copytree(release, retained)
    serial = consumer.with_name('serial-consumer-v1.json')
    original_bytes = consumer.read_bytes()
    write(serial, original_bytes, 0o644)
    original = json.loads(original_bytes)
    old_gate = incident.claims / 'admission-v1.json'
    gate = json.loads(old_gate.read_bytes())
    gate.update(operationId=MIGRATION, phase='applying')
    write(old_gate, gate)
    old_digest = gate['consumerDigest']
    original_history = HISTORY.replace('route,target:',
        "profile:CONSUMER.defaultProfile,subagentsAllowed:false,validation:['diff-check'],"
        "targetBase:head,authorityDigest:'a'.repeat(64),historicalBase:selected.base_sha,route,target:")
    seeded = node(retained / 'reviewed-source', serial, original_history, 'seed', 'full')
    assert seeded['records'] == 161 and seeded['journals'] == 140
    current_manual = []
    if mixed:
        for run_id in range(401, 411):
            path = incident.claims / 'publication-v2' / (str(run_id) + '.json')
            current_manual.append(json.loads(path.read_bytes()))
            path.unlink()
    current = copy.deepcopy(original)
    current['generalRunnerPool'] = {'desiredCapacity': 1}
    names = ['workRoot', 'attemptRoot', 'dispatch', 'launcher', 'diagnosticsConfig', 'diagnosticsStore', 'diagnosticsRoot']
    current['executionSlots'] = [{'id': 'primary', 'runnerName': 'synthetic-pool', 'runnerUser': 'nobody',
        'runtimeUser': current['runtimeUser'], 'workGroup': 'relay-work',
        'paths': {name: current['paths'][name] for name in names}}]
    write(consumer, current, 0o644)
    pool_bytes = consumer.read_bytes()
    digest_program = "import{CONSUMER_DIGEST}from'./consumer/consumer.mjs';console.log(JSON.stringify(CONSUMER_DIGEST));"
    current_digest = node(incident.controller, consumer, digest_program)
    if mixed:
        for record in current_manual:
            record['envelope']['consumerDigest'] = current_digest
            write(incident.claims / 'publication-pool-v1' / (str(record['envelope']['runId']) + '.json'), record)
    pool_gate = incident.claims / 'admission-pool-v1.json'
    write(pool_gate, {**gate, 'operationId': OPERATION, 'phase': 'recovery-required', 'consumerDigest': current_digest})
    # This explicitly synthetic receipt seals the actual original source graph,
    # consumer, envelopes, snapshot, manifest and original immutable gate bytes.
    seal = r"""
import{protectedSourceTreeSha256}from'./controller/src/serial-pool-compatibility.mjs';
import{digest}from'./controller/src/execution-contract.mjs';
import{readFileSync}from'node:fs';
const [source,records]=process.argv.slice(1);
console.log(JSON.stringify({source:await protectedSourceTreeSha256(source),
 runs:JSON.parse(readFileSync(records)).map(r=>({runId:r.envelope.runId,attemptId:r.envelope.attemptId,envelopeSha256:digest(r.envelope)}))}));
"""
    records = [json.loads(path.read_bytes()) for path in sorted((incident.claims / 'publication-v2').glob('*.json'))]
    record_list = root / 'synthetic-record-list.json'
    write(record_list, json.dumps(records).encode())
    hashes = node(incident.controller, consumer, seal, retained / 'reviewed-source', record_list)
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    receipt_path = consumer.with_name('serial-pool-compat-v1.json')
    write(receipt_path, {'version': 1, 'repository': original['repository'], 'namespace': namespace,
        'operationId': MIGRATION, 'original': {'revision': BASELINE, 'consumerPath': str(serial),
            'consumerSha256': sha(serial), 'consumerDigest': old_digest,
            'sourceRoot': str(retained / 'reviewed-source'), 'sourceTreeSha256': hashes['source'],
            'manifestPath': str(retained / 'artifact-manifest.json'),
            'manifestSha256': sha(retained / 'artifact-manifest.json'),
            'configPath': str(retained / 'deployment-config.json'),
            'configSha256': sha(retained / 'deployment-config.json'), 'gateSha256': sha(old_gate),
            'runs': hashes['runs'], 'runnerUser': 'nobody', 'runnerUid': pwd.getpwnam('nobody').pw_uid},
        'target': {'consumerDigest': current_digest}}, 0o644)
    # The retained snapshot binds the actual historical runner identity.
    retained_config = json.loads((retained / 'deployment-config.json').read_bytes())
    retained_config['environment']['generalRunner']['user'] = 'nobody'
    retained_raw = write(retained / 'deployment-config.json', retained_config)
    manifest = json.loads((retained / 'artifact-manifest.json').read_bytes())
    manifest['deploymentConfigSha256'] = hashlib.sha256(retained_raw).hexdigest()
    write(retained / 'artifact-manifest.json', manifest)
    receipt = json.loads(receipt_path.read_bytes())
    receipt['original'].update(configSha256=sha(retained / 'deployment-config.json'),
        manifestSha256=sha(retained / 'artifact-manifest.json'))
    write(receipt_path, receipt, 0o644)
    config = copy.deepcopy(incident.original)
    config['consumer'] = current
    raw = write(release / 'deployment-config.json', config)
    manifest = json.loads((release / 'artifact-manifest.json').read_bytes())
    manifest['deploymentConfigSha256'] = hashlib.sha256(raw).hexdigest()
    write(release / 'artifact-manifest.json', manifest)
    config['source']['revision'] = incident.revision
    config['consumer']['defaultProfile']['effort'] = 'medium'
    # Real native App auth uses only this ephemeral synthetic key; bytes never
    # enter repository files, output or receipts.
    key_path = Path(current['paths']['credentialKeyFile'])
    generated = run(['openssl', 'genpkey', '-algorithm', 'RSA', '-pkeyopt', 'rsa_keygen_bits:2048'],
        capture_output=True, check=True)
    write(key_path, generated.stdout)
    write(Path(current['paths']['credentialEnv']), ('GITHUB_APP_ID=' + current['writerApp']['appId'] + '\n'
        'GITHUB_APP_INSTALLATION_ID=' + current['writerApp']['installationId'] + '\n'
        'GITHUB_APP_PRIVATE_KEY_FILE=' + str(key_path) + '\n').encode())
    preload = incident.controller / 'synthetic-native-preload.mjs'
    native = NATIVE
    if mixed:
        native = native.replace("const path=new URL(url).pathname;let value;",
            "const path=new URL(url).pathname;let value;"
            "if(!path.includes('access_tokens'))await new Promise(r=>setTimeout(r,400));")
    write(preload, native.encode(), 0o644)
    acknowledge = r"""
import{createInstalledTaskDisposition}from'./controller/src/installed-task-disposition.mjs';
import{loadSerialPoolCompatibility,createCompatibilityStore}from'./controller/src/serial-pool-compatibility.mjs';
import{CONSUMER}from'./consumer/consumer.mjs';
import{createAttemptStore,createPublicationStore}from'./controller/src/attempt-store.mjs';
const c=await loadSerialPoolCompatibility({consumer:CONSUMER});
const s=createCompatibilityStore({compatibility:c,currentStore:createPublicationStore(c.current.storeRoot),
 originalStore:createAttemptStore(c.original.storeRoot)}),r=await s.get(410);
const d=createInstalledTaskDisposition({historicalConsumer:c.originalConsumer,allowAcknowledgement:true});
const source=await fetch(`https://api.github.com/repos/${CONSUMER.repository}/issues/1410/comments`).then(r=>r.json());
const{sha256Body}=await import('./contracts/src/github-authority.mjs');
console.log(JSON.stringify(await d.acknowledge(r,{reason:'route-switch',sources:[{kind:'issue-comment',id:10410,
 parent:{kind:'issue',number:1410},sha256:sha256Body(source[0].body)}]})));
"""
    node(incident.controller, consumer, acknowledge, preload=preload)
    import bounded_recovery
    binding = {**incident.binding, 'gitConfigReceipt': {**incident.binding['gitConfigReceipt']}}
    desired_config = write(root / 'synthetic-desired-deployment.json', config)
    binding['gitConfigReceipt']['config_sha256'] = hashlib.sha256(desired_config).hexdigest()
    binding['gitConfigReceipt']['config_blob_sha'] = hashlib.sha1(
        b'blob ' + str(len(desired_config)).encode() + b'\0' + desired_config).hexdigest()
    cli = incident.controller / 'controller/src/admission-cli.mjs'
    desired = consumer.with_name('.consumer-' + OPERATION + '.desired.json')
    write(desired, config['consumer'])
    desired_digest = node(incident.controller, desired, digest_program)

    def command(arguments):
        result = run(['/usr/bin/node', '--import', str(preload), str(cli), *arguments],
            env={'PATH': '/usr/bin:/bin', 'RELAY_CONSUMER_CONFIG': str(consumer)},
            capture_output=True, text=True, timeout=180)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    def probe(_context):
        with incident.lock.open('rb') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return command(['consumer-transition-preflight', '--desired-digest', desired_digest])

    historical = incident.history()
    originals = {str(path): (path.read_bytes(), path.stat().st_ino)
        for path in [old_gate, serial, receipt_path, retained / 'deployment-config.json', retained / 'artifact-manifest.json']}
    target_snapshot = consumer.with_name('serial-pool-target-consumer-v1.json')
    backup = consumer.with_name('consumer-before-' + OPERATION + '.json')
    assert not target_snapshot.exists() and not backup.exists()
    observed = probe({})
    assert observed['eligible'] and observed['active'] == observed['unknown'] == []
    assert [row['reason'] for row in observed['manualAttempts']['historical']] == ['task-completed'] * 8 + ['task-not-planned', 'route-switch']
    proof = bounded_recovery.inspect(config, binding)
    bounded = bounded_recovery.begin(config, binding, proof, admission_probe=probe)
    command(['recovery-target', '--operation', OPERATION, '--target', incident.revision])
    command(['phase', '--operation', OPERATION, '--phase', 'applying'])
    bounded_recovery.revalidate(config, binding, bounded, admission_probe=probe)
    spec = importlib.util.spec_from_file_location('serial_bounded_publication', ROOT / 'deploy/ansible/scripts/publish_git_consumer.py')
    publisher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(publisher)

    timings = []
    def execute(argv, environment):
        with incident.lock.open('rb') as handle:
            with pytest.raises(BlockingIOError):
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        actual = [argv[0], '--import', str(preload), *argv[1:]] if argv[1] != '--input-type=module' else argv
        start = time.monotonic()
        result = None
        try:
            result = publisher._execute(actual, environment)
            return result
        finally:
            timings.append({'action': argv[2] if argv[1] != '--input-type=module' else 'digest',
                'seconds': round(time.monotonic() - start, 3),
                **({'trace': result['_transitionTiming']} if result and '_transitionTiming' in result else {})})

    if mixed:
        def interrupted(argv, environment):
            if 'consumer-transition' in argv:
                return publisher._execute([argv[0], '--import', str(preload), *argv[1:]], environment, timeout=0.1)
            return execute(argv, environment)
        with pytest.raises(publisher.ConsumerPublicationError, match='TRANSITION_REQUIRES_RECOVERY'):
            publisher.publish(incident.controller, consumer.parent, desired, incident.claims,
                original['repository'], OPERATION, incident.revision, execute=interrupted)
        assert consumer.read_bytes() == desired.read_bytes()
        assert json.loads(pool_gate.read_bytes())['consumerDigest'] == current_digest
        assert incident.history() == historical
        reopened = incident.controller / 'synthetic-reopened-task'
        write(reopened, b'explicit native-reopen fixture', 0o644)
        with pytest.raises(publisher.ConsumerPublicationError, match='TRANSITION_REQUIRES_RECOVERY'):
            publisher.publish(incident.controller, consumer.parent, desired, incident.claims,
                original['repository'], OPERATION, incident.revision, execute=execute)
        assert json.loads(pool_gate.read_bytes())['consumerDigest'] == current_digest
        assert incident.history() == historical
        reopened.unlink()

    result = publisher.publish(incident.controller, consumer.parent, desired, incident.claims,
        original['repository'], OPERATION, incident.revision, execute=execute)
    assert result['status'] == 'PUBLISHED' and result['consumerDigest'] == desired_digest
    assert backup.read_bytes() == target_snapshot.read_bytes() == pool_bytes
    assert node(incident.controller, target_snapshot, digest_program) == current_digest
    after = command(['consumer-transition-preflight', '--desired-digest', desired_digest])
    assert after['eligible'] and after['active'] == after['unknown'] == []
    assert command(['status'])['manualAttempts']['historical'] == observed['manualAttempts']['historical']
    manual_store = 'publication-pool-v1' if mixed else 'publication-v2'
    assert all(json.loads((incident.claims / manual_store / (str(run_id) + '.json')).read_bytes()).get('outcome') is None
        for run_id in range(401, 411))
    assert incident.history() == historical
    assert all((Path(path).read_bytes(), Path(path).stat().st_ino) == value for path, value in originals.items())
    gate = json.loads(pool_gate.read_bytes())
    assert (gate['phase'], gate['operationId'], gate['target'], gate['consumerDigest']) == (
        'applying', OPERATION, incident.revision, desired_digest)
    assert json.loads(incident.backend.read_bytes()) == {'schemaVersion': '1', 'state': 'RECOVERY_REQUIRED',
        'phase': 'apply', 'target_head': BASELINE}
    print(json.dumps({'composite': True, 'mixed': mixed, 'records': 161, 'historical': 10, 'timings': timings, 'targetSnapshotCreated': True,
        'originalHistoryUnchanged': True, 'admission': 'applying'}))


@pytest.mark.parametrize('mixed', [False, True])
def test_real_serial_composite_bounded_recovery_creates_missing_target_snapshot_before_consumer_change(mixed):
    if not NODE.is_file():
        pytest.skip('qualified Node 22 executable unavailable')
    probe = subprocess.run(['unshare', '--mount', '--net', '--pid', '--fork', '--kill-child', 'true'], capture_output=True)
    if probe.returncode:
        pytest.skip('private mount/network/PID namespaces unavailable')
    with tempfile.TemporaryDirectory(prefix='relay-bounded-serial-', dir='/run') as directory:
        result = subprocess.run(['unshare', '--mount', '--net', '--pid', '--fork', '--kill-child', '--mount-proc',
            sys.executable, str(Path(__file__).resolve()), '--mixed-harness' if mixed else '--composite-harness', directory],
            text=True, capture_output=True, timeout=360)
        assert result.returncode == 0, result.stdout + result.stderr
        assert json.loads(result.stdout)['originalHistoryUnchanged'] is True
        print(result.stdout.strip())


if __name__ == '__main__':
    assert len(sys.argv) == 3 and sys.argv[1] in ['--composite-harness', '--mixed-harness']
    harness(Path(sys.argv[2]), mixed=sys.argv[1] == '--mixed-harness')
