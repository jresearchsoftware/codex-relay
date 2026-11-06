"""Native process/filesystem proof for the bounded retained-operation bridge.

The old source is archived from the exact incident revision. Current controller,
consumer validation, admission, publication stores and Writer flock execute as
real Linux processes/files. GitHub observations alone are synthetic; these tests
do not claim a live installation, service activation or native Task admission.
"""
import copy
import fcntl
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
import tempfile

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
from test_intent_install import invocation, observed, CONTRACT, TARGET
BASELINE = 'b6edaaf4982df5b7dd6d56fd68b7ce7e34ccd7a9'
OPERATION = '12345678-1234-4234-8234-123456789abc'
NODE = Path(os.environ.get('RELAY_QUALIFIED_NODE',
    '/home/hortonolite/.nvm/versions/node/v22.20.0/bin/node'))
pytestmark = pytest.mark.skipif(sys.platform != 'linux' or os.geteuid() != 0,
    reason='root/native Linux retained-operation process and filesystem qualification')


DRIVER = r"""
import {readFileSync} from 'node:fs';
import {CONSUMER,CONSUMER_DIGEST} from './consumer/consumer.mjs';
import {consumerDigest,validateConsumer} from './consumer/consumer-config.mjs';
import {createPublicationStore,createAttemptStore} from './controller/src/attempt-store.mjs';
import {createAdmissionControl,manualAdmissionComplete} from './controller/src/admission-control.mjs';
import {createInstalledTaskDisposition} from './controller/src/installed-task-disposition.mjs';
import {renderAuthorityRecord,sha256Body} from './contracts/src/github-authority.mjs';
const input=JSON.parse(readFileSync(0,'utf8')), repository=CONSUMER.repository;
const owner={login:CONSUMER.owner,id:100,type:'User'};
const reviewer={login:CONSUMER.reviewerApp.expectedActor,id:101,type:'Bot'};
const body='Authority model: github-native-v1\nIssue closure policy: keep-open';
const state=input.nativeState??{};
function comment(task) {
 const parent={kind:'issue',number:task};
 return {id:9000+task,issue_url:`https://api.github.com/repos/${repository}/issues/${task}`,
  user:reviewer,body:renderAuthorityRecord({schema_version:'4.0',kind:'decision',repository,
   task,parent,charter_sha256:sha256Body(body),purpose:'Withdraw the abandoned original route.',
   amendments:{boundaries:['No relaunch and no fabricated terminal receipt.']},context:[],supersedes:null})};
}
const disposition=createInstalledTaskDisposition({allowAcknowledgement:input.action==='acknowledge',
 tokenFor:async()=> 'synthetic-fixture-token',fetchImpl:async(url)=>{
  const path=new URL(url).pathname;
  if(state.unavailable) return {ok:false};
  let value;
  if(path===`/users/${encodeURIComponent(owner.login)}`) value=owner;
  else if(path===`/users/${encodeURIComponent(reviewer.login)}`) value=reviewer;
  else {
   const match=path.match(/\/issues\/(\d+)(?:\/(events|comments))?$/);
   if(!match) throw new Error('fixture-native-route');
   const task=Number(match[1]),kind=match[2],route=task===1410;
   const closed=!route&&!state.reopened;
   const issue={id:10000+task,number:task,body,state:closed?'closed':'open',
    state_reason:closed?(task===1409?'not_planned':'completed'):null,
    closed_by:closed?owner:null,url:`https://api.github.com/repos/${repository}/issues/${task}`};
   if(kind==='events') value=closed?[{id:task,event:'closed',actor:owner,
    created_at:'2026-11-03T10:00:00Z'}]:[];
   else if(kind==='comments') value=route?[comment(task)]:[];
   else value=issue;
  }
  return {ok:true,json:async()=>structuredClone(value)};
 }});
const store=createPublicationStore(`${CONSUMER.paths.claimRoot}/publication-v2`);
const journal=createAttemptStore(CONSUMER.paths.attemptRoot);
const control=createAdmissionControl({root:CONSUMER.paths.claimRoot,consumerDigest:CONSUMER_DIGEST,
 store,journal,manualAttemptDisposition:disposition.resolve});
let result;
if(input.action==='seed') {
 for(let runId=401;runId<=410;runId++) {
  const issueNumber=runId+1000;
  await store.put(runId,{envelope:{version:2,repository,consumerDigest:CONSUMER_DIGEST,
   runId,attemptId:`run-${runId}`,route:'manual',target:'issue',number:issueNumber,issueNumber,step:1},outcome:null});
 }
 result={records:(await store.all()).length};
} else if(input.action==='acknowledge') {
 const record=await store.get(410), source=comment(1410);
 result=await disposition.acknowledge(record,{reason:'route-switch',sources:[
  {kind:'issue-comment',id:source.id,parent:{kind:'issue',number:1410},sha256:sha256Body(source.body)}]});
} else if(input.action==='preflight') {
 result=await control.preflightConsumerTransition({desiredDigest:consumerDigest(validateConsumer(input.desired))});
} else if(input.action==='classify') {
 result=[];
 for(const record of await store.all()) result.push({runId:record.envelope.runId,
  complete:manualAdmissionComplete(record),reason:(await disposition.resolve(record))?.reason??null});
} else if(input.action==='transition-check') result=await control.checkConsumerTransition(input.options);
else if(input.action==='transition') result=await control.transitionConsumer(input.options);
else if(input.action==='recovery-target') result=await control.recoveryTarget(input.options);
else if(input.action==='phase') result=await control.phase(input.options);
else if(input.action==='status') result=await control.status();
else throw new Error('fixture-action');
console.log(JSON.stringify(result));
"""


def write(path, value, mode=0o600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    raw = value if isinstance(value, bytes) else (json.dumps(value, sort_keys=True) + '\n').encode()
    path.write_bytes(raw)
    path.chmod(mode)
    return raw


def archive_old(destination):
    command = ['git', '-c', 'safe.directory=' + str(ROOT), '-C', str(ROOT)]
    available = subprocess.run([*command, 'cat-file', '-e', BASELINE + '^{commit}'], capture_output=True)
    if available.returncode:
        pytest.skip('exact retained incident Git object unavailable')
    raw = subprocess.check_output([*command, 'archive', BASELINE,
        'consumer', 'controller', 'contracts', 'runtime', 'reviewer'])
    tree = subprocess.check_output([*command, 'rev-parse', BASELINE + '^{tree}'], text=True).strip()
    destination.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            assert not path.is_absolute() and '..' not in path.parts
            if member.isdir():
                (destination / member.name).mkdir(parents=True, exist_ok=True, mode=0o755)
            else:
                assert member.isfile()
                write(destination / member.name, archive.extractfile(member).read(), member.mode & 0o755)
    return tree


class Incident:
    def __init__(self, root):
        self.root = root
        self.namespace = 'relay-bounded-recovery-fixture'
        self.install = root / 'opt' / self.namespace
        self.release = self.install / 'releases' / BASELINE
        tree = archive_old(self.release / 'reviewed-source')
        self.controller = root / 'separate-controller'
        self.revision = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
        for component in ('consumer', 'controller', 'contracts', 'runtime', 'reviewer', 'deploy'):
            shutil.copytree(ROOT / component, self.controller / component,
                ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache', 'target', 'node_modules'))
        for path in [self.controller, *self.controller.rglob('*')]:
            assert not path.is_symlink()
            path.chmod(0o755 if path.is_dir() or path.stat().st_mode & 0o111 else 0o644)
        write(self.controller / '.relay-source.json', {'revision': self.revision}, 0o644)
        write(self.controller / 'fixture-admission.mjs', DRIVER.encode(), 0o644)
        self.config = json.loads((ROOT / 'deploy/example.json').read_text())
        self.config['source']['revision'] = BASELINE
        self.config['environment']['namespace'] = self.namespace
        for name in self.config['consumer']['paths']:
            self.config['consumer']['paths'][name] = str(root / 'configured' / name)
        self.claims = root / 'var/lib' / self.namespace / 'writer-claims'
        self.journals = root / 'var/lib' / self.namespace / 'attempts'
        self.claims.mkdir(parents=True)
        self.journals.mkdir(parents=True)
        self.config['consumer']['paths'].update(claimRoot=str(self.claims), attemptRoot=str(self.journals))
        self.config['consumer']['defaultProfile']['effort'] = 'xhigh'
        self.original = copy.deepcopy(self.config)
        self.config_root = root / 'etc' / self.namespace
        self.consumer = self.config_root / 'consumer.json'
        write(self.consumer, self.config['consumer'], 0o644)
        old_raw = write(self.release / 'deployment-config.json', self.original)
        write(self.release / 'reviewed-source/.relay-source.json', {'revision': BASELINE, 'tree': tree}, 0o644)
        self.contract = {'schemaVersion': 1, 'epoch': 1,
            'capabilities': ['lifecycle-v1', 'git-desired-v1', 'integration-artifact-v1']}
        write(self.release / 'artifact-manifest.json', {'commit': BASELINE, 'installedRevision': BASELINE,
            'resolvedRevision': BASELINE, 'gitTree': tree, 'deploymentContract': self.contract,
            'gitConfigReceipt': {'product_sha': BASELINE, 'config_sha': 'a' * 40,
                'config_blob_sha': 'b' * 40, 'config_sha256': hashlib.sha256(old_raw).hexdigest()},
            'deploymentConfigSha256': hashlib.sha256(old_raw).hexdigest()})
        (self.install / 'current').symlink_to('releases/' + BASELINE)
        self.lock = self.claims / 'publication-v2.lock'
        write(self.lock, b'')
        self.native_state = {}
        self.digest = self.old_cli('initialize')['consumerDigest']
        self.old_cli('quiesce', '--operation', OPERATION, '--target', BASELINE)
        self.old_cli('drain-check', '--operation', OPERATION)
        self.old_cli('phase', '--operation', OPERATION, '--phase', 'applying')
        self.service_intent = {
            'reviewer': {'active': True, 'enabled': 'enabled', 'load': 'loaded'},
            'production': {'active': False, 'enabled': 'disabled', 'load': 'loaded'},
            'general': {'active': False, 'enabled': 'disabled', 'load': 'loaded'}}
        self.old_cli('snapshot', '--operation', OPERATION, payload=self.service_intent)
        self.old_cli('phase', '--operation', OPERATION, '--phase', 'recovery-required')
        self.gate = self.claims / 'admission-v1.json'
        self.backend = root / 'var/lib' / (self.namespace + '-production-operation.json')
        write(self.backend, {'schemaVersion': '1', 'state': 'RECOVERY_REQUIRED',
            'phase': 'apply', 'target_head': BASELINE})
        self.native('seed')
        self.native('acknowledge')
        self.config['source']['revision'] = self.revision
        self.config['consumer']['defaultProfile']['effort'] = 'medium'
        config_raw = (json.dumps(self.config, sort_keys=True) + '\n').encode()
        self.binding = {'operationId': OPERATION, 'retainedTarget': BASELINE, 'installedRevision': BASELINE,
            'controllerRevision': self.revision, 'desiredRevision': self.revision,
            'gitConfigReceipt': {'config_repository': 'example-org/test-config', 'config_path': 'relay.json',
                'config_sha': 'e' * 40, 'config_blob_sha': 'f' * 40,
                'config_sha256': hashlib.sha256(config_raw).hexdigest(), 'product_repository': 'example/product',
                'product_sha': self.revision, 'source_policy': 'test-qualified-exact'}}
        self.backup = self.config_root / ('consumer-before-' + OPERATION + '.json')
        self.receipt = self.backend.with_name(self.backend.stem + '.' + OPERATION + '.continuation.json')

    @property
    def env(self):
        return {'PATH': str(NODE.parent) + ':/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C',
            'RELAY_CONSUMER_CONFIG': str(self.consumer),
            'RELAY_REPOSITORY': self.original['consumer']['repository']}

    def old_cli(self, *arguments, payload=None):
        result = subprocess.run([str(NODE), str(self.release / 'reviewed-source/controller/src/admission-cli.mjs'),
            *arguments], input=None if payload is None else json.dumps(payload),
            env=self.env, text=True, capture_output=True, timeout=30)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    def native(self, action, *, environment=None, **values):
        result = subprocess.run([str(NODE), str(self.controller / 'fixture-admission.mjs')],
            input=json.dumps({'action': action, 'nativeState': self.native_state, **values}),
            env=environment or self.env, cwd=self.controller, text=True, capture_output=True, timeout=30)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    def probe(self, context):
        assert context['operationId'] == OPERATION
        assert context['target'] in (BASELINE, self.revision)
        with self.lock.open('rb') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                return self.native('preflight', desired=json.loads(json.dumps(self.config['consumer'], sort_keys=True)))
            except AssertionError:
                # The real native process's refusal cannot become eligibility.
                # Production transports expose their own bounded diagnostic.
                return {'eligible': False}

    def history(self):
        return {str(path.relative_to(self.root)): (path.read_bytes(), path.stat().st_ino)
            for directory in (self.claims / 'publication-v2', self.journals)
            for path in directory.rglob('*.json')}

    def snapshot(self):
        return {str(path.relative_to(self.root)): (path.read_bytes(), path.stat().st_ino)
            for path in (self.gate, self.backend, self.consumer,
                self.release / 'artifact-manifest.json', self.release / 'deployment-config.json') if path.exists()}

    def helper(self, action, *arguments, **options):
        import bounded_recovery
        return getattr(bounded_recovery, action)(self.config, self.binding, *arguments,
            root=self.root, admission_probe=self.probe, **options)

    def publish(self, *, interrupt=False):
        spec = importlib.util.spec_from_file_location('bounded_fixture_publisher',
            ROOT / 'deploy/ansible/scripts/publish_git_consumer.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        desired = self.config_root / ('.consumer-' + OPERATION + '.desired.json')
        write(desired, self.config['consumer'])

        def execute(argv, environment):
            with self.lock.open('rb') as handle:
                with pytest.raises(BlockingIOError):
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if argv[1] == '--input-type=module':
                return module._execute([str(NODE), *argv[1:]], environment)
            command = argv[2]
            assert command in ['consumer-transition-check', 'consumer-transition']
            options = {}
            for key, value in zip(argv[3::2], argv[4::2]):
                options[{'--operation': 'operationId', '--revision': 'target',
                    '--previous-digest': 'previousDigest'}[key]] = value
            if interrupt and command == 'consumer-transition':
                assert self.consumer.read_bytes() == desired.read_bytes() and self.backup.exists()
                raise module.ConsumerPublicationError('CONSUMER_PUBLICATION_CONTROLLER_FAILED')
            return self.native('transition-check' if command.endswith('-check') else 'transition',
                environment=environment, options=options)

        return module.publish(self.controller, self.config_root, desired, self.claims,
            self.original['consumer']['repository'], OPERATION, self.revision,
            boundary=self.root, execute=execute)

    def final_artifacts(self):
        release = self.install / 'releases' / self.revision
        source = release / 'reviewed-source'
        source.mkdir(parents=True)
        tree = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD^{tree}'], text=True).strip()
        write(source / '.relay-source.json', {'revision': self.revision, 'tree': tree}, 0o644)
        raw = write(release / 'deployment-config.json', self.config)
        write(release / 'artifact-manifest.json', {'commit': self.revision,
            'installedRevision': self.revision, 'resolvedRevision': self.revision, 'gitTree': tree,
            'deploymentContract': self.contract, 'deploymentConfigSha256': hashlib.sha256(raw).hexdigest(),
            'gitConfigReceipt': self.binding['gitConfigReceipt']})
        (self.install / 'current').unlink()
        (self.install / 'current').symlink_to('releases/' + self.revision)


@pytest.fixture
def incident():
    if not NODE.is_file():
        pytest.skip('set RELAY_QUALIFIED_NODE to a qualified Node 22 executable')
    assert subprocess.check_output([str(NODE), '--version'], text=True).startswith('v22.')
    with tempfile.TemporaryDirectory(prefix='relay-bounded-install-', dir='/run') as temporary:
        yield Incident(Path(temporary))


def test_incident_uses_exact_old_source_and_ten_current_dispositions_without_terminal_receipts(incident):
    before = incident.history()
    rows = incident.native('classify')
    assert [row['reason'] for row in rows] == ['task-completed'] * 8 + ['task-not-planned', 'route-switch']
    assert all(row['complete'] is False for row in rows)
    observed = incident.probe({'operationId': OPERATION, 'target': BASELINE})
    assert observed['eligible'] is True and observed['unknown'] == [] and observed['active'] == []
    assert observed['phase'] == 'recovery-required' and observed['currentDigest'] == incident.digest
    assert observed['desiredDigest'] != incident.digest
    assert incident.history() == before and not incident.backup.exists()
    assert json.loads(incident.backend.read_bytes())['target_head'] == BASELINE
    assert json.loads(incident.gate.read_bytes())['previousActive'] == incident.service_intent


def test_missing_original_activity_intent_is_refused_before_any_continuation_mutation(incident):
    gate = json.loads(incident.gate.read_bytes())
    gate['previousActive'] = None
    write(incident.gate, gate)
    before, history = incident.snapshot(), incident.history()
    with pytest.raises(ValueError, match='BOUNDED_RECOVERY_ORIGINAL_ACTIVITY_INTENT_UNPROVEN'):
        incident.helper('inspect')
    assert incident.snapshot() == before and incident.history() == history
    assert not incident.receipt.exists() and not incident.backup.exists()


def test_original_git_snapshot_does_not_replace_the_authentic_live_consumer_context(incident):
    # The original Apply may have published its intended snapshot before
    # consumer publication failed. The real gate still authenticates OLD bytes.
    original = copy.deepcopy(incident.original)
    original['consumer']['defaultProfile']['effort'] = 'high'
    snapshot = write(incident.release / 'deployment-config.json', original)
    manifest_path = incident.release / 'artifact-manifest.json'
    manifest = json.loads(manifest_path.read_bytes())
    manifest['deploymentConfigSha256'] = hashlib.sha256(snapshot).hexdigest()
    manifest['gitConfigReceipt']['config_sha256'] = hashlib.sha256(snapshot).hexdigest()
    write(manifest_path, manifest)
    before, history = incident.snapshot(), incident.history()
    proof = incident.helper('inspect')
    assert proof['original']['originalConsumer']['defaultProfile']['effort'] == 'high'
    assert proof['original']['consumer']['defaultProfile']['effort'] == 'xhigh'
    reserved = incident.helper('begin', proof)
    assert reserved['state'] == 'reserved'
    assert incident.snapshot() == before and incident.history() == history
    assert not incident.backup.exists()


@pytest.mark.parametrize('effect', ['journal', 'publication', 'submission'])
def test_real_preflight_rejects_conflicting_effects_even_with_native_closed_tasks(incident, effect):
    record_path = incident.claims / 'publication-v2/401.json'
    record = json.loads(record_path.read_bytes())
    if effect == 'journal':
        write(incident.journals / '401.json', {'version': 2, 'envelope': record['envelope'],
            'execution': {'reserved': True, 'returned': False, 'child': 'started', 'containment': 'unknown'}})
    else:
        record['commentIntent' if effect == 'publication' else 'manualSubmission'] = {'pending': True}
        write(record_path, record)
    before, history = incident.snapshot(), incident.history()
    observed = incident.probe({'operationId': OPERATION, 'target': BASELINE})
    assert observed['eligible'] is False and 401 in observed['unknown']
    assert incident.snapshot() == before and incident.history() == history
    assert not incident.backup.exists()


def test_native_reopen_and_unavailable_evidence_do_not_reuse_cached_route_disposition(incident):
    before, history = incident.snapshot(), incident.history()
    incident.native_state['reopened'] = True
    reopened = incident.probe({'operationId': OPERATION, 'target': BASELINE})
    assert reopened['eligible'] is False and reopened['unknown'] == list(range(401, 410))
    incident.native_state = {'unavailable': True}
    assert incident.probe({'operationId': OPERATION, 'target': BASELINE})['eligible'] is False
    assert incident.snapshot() == before and incident.history() == history


@pytest.mark.parametrize('maintenance', [False, True])
def test_bounded_bridge_keeps_original_operation_until_exact_final_pair_and_verified_gate(incident, maintenance):
    import bounded_recovery
    if maintenance:
        incident.binding['runnerMaintenance'] = {'operationId': OPERATION, 'retainedTarget': BASELINE,
            'runners': {'production': {'runnerId': 55, 'runnerName': 'sample-production-runner'}}}
    before, history = incident.snapshot(), incident.history()
    proof = incident.helper('inspect')
    assert incident.snapshot() == before and not incident.receipt.exists()
    reserved = incident.helper('begin', proof)
    assert reserved['state'] == 'reserved'
    assert incident.helper('revalidate', reserved) == reserved
    assert incident.snapshot() == before and incident.history() == history
    incident.native('recovery-target', options={'operationId': OPERATION, 'target': incident.revision})
    incident.native('phase', options={'operationId': OPERATION, 'phase': 'applying'})
    assert incident.helper('revalidate', reserved) == reserved
    assert bounded_recovery.backend_validate(incident.backend, incident.revision, OPERATION,
        root=incident.root)['originalTarget'] == BASELINE
    assert incident.publish()['status'] == 'PUBLISHED'
    assert incident.backup.read_bytes() == before[str(incident.consumer.relative_to(incident.root))][0]
    assert incident.history() == history and incident.backend.read_bytes() == before[
        str(incident.backend.relative_to(incident.root))][0]
    with pytest.raises(ValueError, match='FINAL_CURRENT_UNPROVEN'):
        bounded_recovery.backend_finalize(incident.backend, incident.revision, OPERATION, root=incident.root)
    incident.final_artifacts()
    bounded_recovery.backend_finalize(incident.backend, incident.revision, OPERATION, root=incident.root)
    assert not incident.backend.exists()
    assert json.loads(incident.receipt.read_bytes())['state'] == 'backend-complete'
    with pytest.raises(ValueError, match='FINAL_GATE_UNPROVEN'):
        incident.helper('finalize', reserved)
    incident.native('phase', options={'operationId': OPERATION, 'phase': 'verified', 'revision': incident.revision})
    completed = incident.helper('finalize', reserved)
    assert completed['state'] == 'complete' and incident.history() == history
    gate = json.loads(incident.gate.read_bytes())
    assert (gate['operationId'], gate['target'], gate['phase']) == (OPERATION, incident.revision, 'verified')
    assert completed['original'] == reserved['original']
    assert completed['binding'] == incident.binding


def test_gate_only_retained_operation_preserves_absence_and_completes_same_uuid(incident):
    import bounded_recovery
    incident.backend.unlink()
    incident.binding['runnerMaintenance'] = {'operationId': OPERATION, 'retainedTarget': BASELINE,
        'runners': {'production': {'runnerId': 55, 'runnerName': 'sample-production-runner'}}}
    before, history = incident.snapshot(), incident.history()
    proof = incident.helper('inspect')
    assert proof['original']['backendAbsent'] is True and proof['original']['backendBytes'] == ''
    reserved = incident.helper('begin', proof)
    assert incident.snapshot() == before and incident.history() == history
    incident.native('recovery-target', options={'operationId': OPERATION, 'target': incident.revision})
    incident.native('phase', options={'operationId': OPERATION, 'phase': 'applying'})
    assert incident.helper('revalidate', reserved) == reserved
    assert bounded_recovery.backend_validate(incident.backend, incident.revision, OPERATION,
        root=incident.root, require_applying=True)['operationId'] == OPERATION
    # Existing Ansible Begin creates this exact record under the existing locks.
    write(incident.backend, {'schemaVersion': '1', 'state': 'RECOVERY_REQUIRED',
                            'phase': 'apply', 'target_head': incident.revision})
    # APT may fail after Begin, before any desired artifact/consumer is installed.
    # The next read-only inspection must recognize only this derived backend.
    incident.native('phase', options={'operationId': OPERATION, 'phase': 'recovery-required'})
    interrupted, receipt_raw = incident.snapshot(), incident.receipt.read_bytes()
    assert incident.helper('inspect') == reserved
    assert incident.helper('begin', reserved) == reserved
    assert incident.helper('revalidate', reserved) == reserved
    assert incident.snapshot() == interrupted and incident.receipt.read_bytes() == receipt_raw
    assert incident.history() == history
    incident.native('phase', options={'operationId': OPERATION, 'phase': 'applying'})
    assert incident.helper('revalidate', reserved) == reserved
    assert incident.publish()['status'] == 'PUBLISHED'
    incident.final_artifacts()
    bounded_recovery.backend_finalize(incident.backend, incident.revision, OPERATION, root=incident.root)
    assert not incident.backend.exists()
    archive = incident.receipt.with_name(incident.receipt.name.removesuffix('.json') + '.original.json')
    assert not archive.exists(), 'no fabricated archive for an absent original backend'
    incident.native('phase', options={'operationId': OPERATION, 'phase': 'verified', 'revision': incident.revision})
    completed = incident.helper('finalize', reserved)
    assert completed['state'] == 'complete' and completed['original'] == proof['original']
    assert incident.history() == history


@pytest.mark.parametrize('damage', ['appeared', 'foreign-target', 'dangling-link'])
def test_gate_only_backend_cannot_be_replaced_or_reinterpreted(incident, damage):
    import bounded_recovery
    incident.backend.unlink()
    if damage == 'dangling-link':
        incident.backend.symlink_to(incident.root / 'missing')
        with pytest.raises(ValueError, match='PATH_UNSAFE'):
            incident.helper('inspect')
        return
    reserved = incident.helper('begin', incident.helper('inspect'))
    write(incident.backend, {'schemaVersion': '1', 'state': 'RECOVERY_REQUIRED',
                            'phase': 'apply', 'target_head': 'f' * 40})
    if damage == 'appeared':
        with pytest.raises(ValueError, match='BACKEND_BINDING_CHANGED'):
            incident.helper('revalidate', reserved)
    else:
        with pytest.raises(ValueError, match='BACKEND_BINDING_CHANGED'):
            bounded_recovery.backend_validate(incident.backend, incident.revision, OPERATION, root=incident.root)


@pytest.mark.parametrize('damage', ['unselected-target', 'foreign-target', 'extra-field', 'wrong-phase',
    'wrong-state', 'malformed', 'archive', 'receipt-next-link', 'changed-binding'])
def test_post_begin_continuation_refuses_ambiguous_backend_or_receipt(incident, damage):
    incident.backend.unlink()
    reserved = incident.helper('begin', incident.helper('inspect'))
    if damage != 'unselected-target':
        incident.native('recovery-target', options={'operationId': OPERATION, 'target': incident.revision})
    backend = {'schemaVersion': '1', 'state': 'RECOVERY_REQUIRED',
               'phase': 'apply', 'target_head': incident.revision}
    if damage == 'foreign-target':
        backend['target_head'] = 'f' * 40
    elif damage == 'extra-field':
        backend['operationId'] = OPERATION
    elif damage == 'wrong-phase':
        backend['phase'] = 'activate'
    elif damage == 'wrong-state':
        backend['state'] = 'STABLE'
    write(incident.backend, b'{' if damage == 'malformed' else backend)
    if damage == 'archive':
        write(incident.receipt.with_name(incident.receipt.name.removesuffix('.json') + '.original.json'), b'foreign')
    elif damage == 'receipt-next-link':
        incident.receipt.with_name(incident.receipt.name + '.next').symlink_to(incident.root / 'absent')
    elif damage == 'changed-binding':
        incident.binding['controllerRevision'] = incident.binding['desiredRevision'] = 'e' * 40
        incident.binding['gitConfigReceipt']['product_sha'] = 'e' * 40
    before, receipt_raw, history = incident.snapshot(), incident.receipt.read_bytes(), incident.history()
    for action, args in [('inspect', ()), ('revalidate', (reserved,))]:
        with pytest.raises(ValueError):
            incident.helper(action, *args)
    assert incident.snapshot() == before and incident.receipt.read_bytes() == receipt_raw
    assert incident.history() == history


def test_post_begin_revalidation_refuses_backend_change_during_live_probe(incident):
    import bounded_recovery
    incident.backend.unlink()
    reserved = incident.helper('begin', incident.helper('inspect'))
    incident.native('recovery-target', options={'operationId': OPERATION, 'target': incident.revision})
    write(incident.backend, {'schemaVersion': '1', 'state': 'RECOVERY_REQUIRED',
                           'phase': 'apply', 'target_head': incident.revision})
    def probe(context):
        result = incident.probe(context)
        write(incident.backend, {'schemaVersion': '1', 'state': 'RECOVERY_REQUIRED',
                               'phase': 'apply', 'target_head': 'f' * 40})
        return result
    with pytest.raises(ValueError, match='EVIDENCE_CHANGED'):
        bounded_recovery.revalidate(incident.config, incident.binding, reserved,
                                   root=incident.root, admission_probe=probe)


@pytest.mark.parametrize('evidence', ['manifest', 'source', 'source-blob', 'snapshot', 'consumer',
    'backend', 'receipt', 'gate', 'credential'])
def test_reserved_bridge_rejects_changed_protected_evidence_without_repair(incident, evidence):
    reserved = incident.helper('begin', incident.helper('inspect'))
    paths = {'manifest': incident.release / 'artifact-manifest.json',
        'source': incident.release / 'reviewed-source/.relay-source.json',
        'source-blob': incident.release / 'reviewed-source/controller/src/admission-cli.mjs',
        'credential': Path(incident.original['consumer']['paths']['credentialEnv']),
        'snapshot': incident.release / 'deployment-config.json', 'consumer': incident.consumer,
        'backend': incident.backend, 'receipt': incident.receipt, 'gate': incident.gate}
    path = paths[evidence]
    if evidence == 'source-blob':
        write(path, path.read_bytes() + b'\n// altered retained controller bytes\n', 0o644)
    elif evidence == 'credential':
        write(path, b'SYNTHETIC_FIXTURE_ONLY=changed\n')
    else:
        value = json.loads(path.read_bytes())
        if evidence == 'gate':
            value['operationId'] = '22345678-1234-4234-8234-123456789abc'
        else:
            value['unrelatedMutation'] = True
        write(path, value, path.stat().st_mode & 0o777)
    before, history, changed = incident.snapshot(), incident.history(), path.read_bytes()
    with pytest.raises(ValueError, match='BOUNDED_RECOVERY_'):
        incident.helper('revalidate', reserved)
    assert incident.snapshot() == before and incident.history() == history and path.read_bytes() == changed


@pytest.mark.parametrize('effect', ['journal', 'publication'])
def test_reserved_bridge_rechecks_live_effects_under_real_current_controller(incident, effect):
    reserved = incident.helper('begin', incident.helper('inspect'))
    path = incident.claims / 'publication-v2/401.json'
    record = json.loads(path.read_bytes())
    if effect == 'journal':
        write(incident.journals / '401.json', {'version': 2, 'envelope': record['envelope'],
            'execution': {'reserved': True, 'returned': False, 'containment': 'unknown'}})
    else:
        record['commentIntent'] = {'key': 'outcome'}
        write(path, record)
    before, history, receipt = incident.snapshot(), incident.history(), incident.receipt.read_bytes()
    with pytest.raises(ValueError, match='CURRENT_CONTROLLER_PROOF_UNPROVEN'):
        incident.helper('revalidate', reserved)
    assert incident.snapshot() == before and incident.history() == history
    assert incident.receipt.read_bytes() == receipt


def test_interrupted_consumer_rename_recovers_only_same_uuid_with_real_backup(incident):
    reserved = incident.helper('begin', incident.helper('inspect'))
    history, backend = incident.history(), incident.backend.read_bytes()
    incident.native('recovery-target', options={'operationId': OPERATION, 'target': incident.revision})
    incident.native('phase', options={'operationId': OPERATION, 'phase': 'applying'})
    incident.helper('revalidate', reserved)
    with pytest.raises(ValueError, match='CONSUMER_PUBLICATION_TRANSITION_REQUIRES_RECOVERY'):
        incident.publish(interrupt=True)
    backup, inode = incident.backup.read_bytes(), incident.backup.stat().st_ino
    assert json.loads(incident.gate.read_bytes())['consumerDigest'] == incident.digest
    assert incident.publish()['status'] == 'PUBLISHED'
    assert incident.publish()['status'] == 'UNCHANGED'
    assert (incident.backup.read_bytes(), incident.backup.stat().st_ino) == (backup, inode)
    assert incident.backend.read_bytes() == backend and incident.history() == history


def test_interrupted_receipt_reservation_remains_closed_and_cannot_be_replaced(incident, monkeypatch):
    import bounded_recovery
    proof = incident.helper('inspect')
    before, history = incident.snapshot(), incident.history()
    original_replace = bounded_recovery.os.replace

    def interrupt(source, target):
        if Path(target) == incident.receipt:
            raise OSError('synthetic interruption before durable receipt rename')
        return original_replace(source, target)

    with monkeypatch.context() as patch:
        patch.setattr(bounded_recovery.os, 'replace', interrupt)
        with pytest.raises(OSError, match='synthetic interruption'):
            incident.helper('begin', proof)
    pending = incident.receipt.with_name(incident.receipt.name + '.next')
    raw = pending.read_bytes()
    assert not incident.receipt.exists()
    with pytest.raises(ValueError, match='INTERRUPTED_RECEIPT'):
        incident.helper('begin', proof)
    assert pending.read_bytes() == raw and incident.snapshot() == before and incident.history() == history


def test_interrupted_backend_clear_keeps_original_journal_and_verified_recovery_boundary(incident, monkeypatch):
    import bounded_recovery
    reserved = incident.helper('begin', incident.helper('inspect'))
    backend, history = incident.backend.read_bytes(), incident.history()
    incident.native('recovery-target', options={'operationId': OPERATION, 'target': incident.revision})
    incident.native('phase', options={'operationId': OPERATION, 'phase': 'applying'})
    incident.publish()
    incident.final_artifacts()
    original_unlink = Path.unlink

    def interrupt(path, *arguments, **options):
        if path == incident.backend:
            raise OSError('synthetic interruption before original journal removal')
        return original_unlink(path, *arguments, **options)

    with monkeypatch.context() as patch:
        patch.setattr(Path, 'unlink', interrupt)
        with pytest.raises(OSError, match='synthetic interruption'):
            bounded_recovery.backend_finalize(incident.backend, incident.revision, OPERATION, root=incident.root)
    assert incident.backend.read_bytes() == backend and incident.history() == history
    assert json.loads(incident.receipt.read_bytes())['state'] == 'backend-complete'
    with pytest.raises(ValueError, match='FINAL_RECEIPT_UNPROVEN'):
        incident.helper('finalize', reserved)
    assert json.loads(incident.gate.read_bytes())['phase'] == 'applying'


def test_interrupted_backend_archive_stops_inspection_before_any_continuation_effect(incident, monkeypatch):
    import bounded_recovery
    reserved = incident.helper('begin', incident.helper('inspect'))
    backend = incident.backend.read_bytes()
    incident.native('recovery-target', options={'operationId': OPERATION, 'target': incident.revision})
    incident.native('phase', options={'operationId': OPERATION, 'phase': 'applying'})
    incident.publish()
    incident.final_artifacts()
    original_atomic = bounded_recovery.atomic

    def interrupt(path, value, *arguments, **options):
        if value.get('state') == 'backend-complete':
            raise OSError('synthetic interruption after original archive fsync')
        return original_atomic(path, value, *arguments, **options)

    with monkeypatch.context() as patch:
        patch.setattr(bounded_recovery, 'atomic', interrupt)
        with pytest.raises(OSError, match='synthetic interruption after original archive fsync'):
            bounded_recovery.backend_finalize(incident.backend, incident.revision, OPERATION, root=incident.root)
    archive = incident.receipt.with_name(incident.receipt.name.removesuffix('.json') + '.original.json')
    assert archive.read_bytes() == backend and incident.backend.read_bytes() == backend
    assert json.loads(incident.receipt.read_bytes()) == reserved
    before, history = incident.snapshot(), incident.history()
    archive_before = archive.read_bytes(), archive.stat().st_ino
    receipt_before = incident.receipt.read_bytes(), incident.receipt.stat().st_ino
    with pytest.raises(ValueError, match='^BOUNDED_RECOVERY_INTERRUPTED_ARCHIVE$'):
        bounded_recovery.inspect(incident.config, incident.binding, root=incident.root,
            admission_probe=lambda *_: pytest.fail('interrupted archive must stop before native effects'))
    assert incident.snapshot() == before and incident.history() == history
    assert (archive.read_bytes(), archive.stat().st_ino) == archive_before
    assert (incident.receipt.read_bytes(), incident.receipt.stat().st_ino) == receipt_before


@pytest.mark.parametrize('shape', ['file', 'dangling-symlink'])
def test_orphan_original_archive_stops_initial_inspection_without_mutation(incident, shape):
    import bounded_recovery
    archive = incident.receipt.with_name(incident.receipt.name.removesuffix('.json') + '.original.json')
    if shape == 'file':
        write(archive, incident.backend.read_bytes())
    else:
        archive.symlink_to('nonexistent-original-evidence.json')
    before, history, info = incident.snapshot(), incident.history(), archive.lstat()
    with pytest.raises(ValueError, match='^BOUNDED_RECOVERY_INTERRUPTED_ARCHIVE$'):
        bounded_recovery.inspect(incident.config, incident.binding, root=incident.root,
            admission_probe=lambda *_: pytest.fail('orphan archive must stop before native effects'))
    assert not incident.receipt.exists() and incident.snapshot() == before and incident.history() == history
    assert archive.lstat().st_ino == info.st_ino and archive.lstat().st_mode == info.st_mode
    if shape == 'dangling-symlink':
        assert os.readlink(archive) == 'nonexistent-original-evidence.json'
    else:
        assert archive.read_bytes() == incident.backend.read_bytes()


def test_reserved_continuation_cannot_be_rebound_to_another_git_pair_or_operation(incident):
    incident.helper('begin', incident.helper('inspect'))
    before, raw, history = incident.snapshot(), incident.receipt.read_bytes(), incident.history()
    incident.binding['gitConfigReceipt']['config_sha'] = 'f' * 40
    with pytest.raises(ValueError, match='BOUNDED_RECOVERY_'):
        incident.helper('inspect')
    assert incident.receipt.read_bytes() == raw and incident.snapshot() == before and incident.history() == history


@pytest.mark.parametrize('maintenance', [False, True])
def test_public_install_routes_explicit_recovery_with_original_uuid_and_frozen_git_pair(invocation, monkeypatch, maintenance):
    """Outer public orchestration proof; its host transport is explicitly stubbed."""
    import bounded_recovery
    import install_recovery
    import intent_install
    import inventory
    args, _, receipt, _ = invocation
    args.authorize_install_recovery = True
    args.install_recovery_operation = OPERATION
    args.install_recovery_target = BASELINE
    declaration = {'operationId': OPERATION, 'retainedTarget': BASELINE,
                   'runners': {'production': {'runnerId': 55, 'runnerName': 'sample-production-runner'}}}
    if maintenance:
        path = args.config.parent / 'owner-maintenance.json'
        path.write_text(json.dumps(declaration))
        args.retained_runner_maintenance = path
    before = observed(BASELINE, CONTRACT)
    before['blockers'] = [install_recovery.OPERATION_BLOCKER]
    after = observed(TARGET, CONTRACT)
    after['configuration']['status'] = 'equivalent'
    after['installed']['gitConfigReceipt'] = copy.deepcopy(receipt)
    calls, probes = [], []
    monkeypatch.setattr(inventory, 'remote_inventory', lambda *_a, **_k: after if calls else before)
    monkeypatch.setattr(install_recovery, 'remote_probe',
        lambda *_a, **_k: pytest.fail('explicit continuation must not execute the old installed reader'))
    proof = {'bounded': 'protected-target-proof'}

    def remote(_target, _key, _config, binding, guard, pool_guard):
        assert guard.poll() is None and pool_guard is None and not calls
        assert binding == {'operationId': OPERATION, 'retainedTarget': BASELINE,
            'installedRevision': BASELINE, 'controllerRevision': TARGET, 'desiredRevision': TARGET,
            'gitConfigReceipt': receipt, **({'runnerMaintenance': declaration} if maintenance else {})}
        probes.append(copy.deepcopy(binding))
        return proof

    monkeypatch.setattr(bounded_recovery, 'remote_probe', remote)
    intent_install.run(args, calls.append, ROOT, {'revision': TARGET})
    assert len(calls) == len(probes) == 1
    inner = calls[0]
    assert inner.phase == 'upgrade' and inner.lifecycle_recovery_operation == OPERATION
    assert inner.authorize_lifecycle_recovery is True
    assert inner._intent_bounded_recovery == probes[0] and inner._intent_bounded_recovery_proof == proof
    assert inner._intent_bounded_recovery is not probes[0]
    assert not hasattr(inner, '_intent_recovery_proof')
    assert all(guard.releases == 1 for guard in args._test_guards)
    assert before['blockers'] == [install_recovery.OPERATION_BLOCKER]


def test_public_install_without_new_flags_retains_original_same_target_recovery(invocation, monkeypatch):
    import bounded_recovery
    import install_recovery
    import intent_install
    import inventory
    args, _, receipt, _ = invocation
    before, after = observed(BASELINE, CONTRACT), observed(TARGET, CONTRACT)
    after['configuration']['status'] = 'equivalent'
    after['installed']['gitConfigReceipt'] = copy.deepcopy(receipt)
    calls, probes = [], []
    monkeypatch.setattr(inventory, 'remote_inventory', lambda *_a, **_k: after if calls else before)
    monkeypatch.setattr(bounded_recovery, 'remote_probe',
        lambda *_a, **_k: pytest.fail('ordinary install must not enable a cross-target continuation'))
    proof = {'operationId': OPERATION, 'target': TARGET, 'installedRevision': BASELINE}

    def remote(_target, _key, _config, target, installed, guard, pool_guard):
        assert target == TARGET and installed == BASELINE and guard.poll() is None and pool_guard is None
        probes.append(target)
        return proof

    monkeypatch.setattr(install_recovery, 'remote_probe', remote)
    intent_install.run(args, calls.append, ROOT, {'revision': TARGET})
    assert len(calls) == len(probes) == 1
    assert calls[0]._intent_recovery_proof == proof
    assert calls[0].lifecycle_recovery_operation == OPERATION
    assert not hasattr(calls[0], '_intent_bounded_recovery')


@pytest.mark.parametrize('authorized,operation,target', [
    (True, None, BASELINE), (True, OPERATION, None), (True, 'invalid', BASELINE),
    (True, OPERATION, 'main'), (False, OPERATION, BASELINE), (False, None, BASELINE)])
def test_public_install_rejects_incomplete_recovery_selection_before_host_access(
        invocation, monkeypatch, authorized, operation, target):
    import intent_install
    import inventory
    args, _, _, _ = invocation
    args.authorize_install_recovery = authorized
    args.install_recovery_operation, args.install_recovery_target = operation, target
    monkeypatch.setattr(inventory, 'remote_inventory', lambda *_a, **_k: pytest.fail('premature host access'))
    with pytest.raises(ValueError, match='RECOVERY_ARGUMENTS_INVALID'):
        intent_install.run(args, lambda *_a: pytest.fail('premature mutation'), ROOT, {'revision': TARGET})


@pytest.mark.parametrize('expert', ['authorize_upgrade', 'authorize_bootstrap', 'authorize_reinstall',
    'authorize_lifecycle_recovery', 'authorize_serial_to_pool'])
def test_public_install_rejects_mixed_expert_authority_before_host_access(invocation, monkeypatch, expert):
    import intent_install
    import inventory
    args, _, _, _ = invocation
    args.authorize_install_recovery = True
    args.install_recovery_operation, args.install_recovery_target = OPERATION, BASELINE
    setattr(args, expert, True)
    monkeypatch.setattr(inventory, 'remote_inventory', lambda *_a, **_k: pytest.fail('premature host access'))
    with pytest.raises(ValueError, match='EXPERT_AUTHORIZATION_FLAGS_INVALID'):
        intent_install.run(args, lambda *_a: pytest.fail('premature mutation'), ROOT, {'revision': TARGET})
