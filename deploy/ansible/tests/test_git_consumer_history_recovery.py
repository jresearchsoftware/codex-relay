"""Disposable root/Linux qualification of real consumer publication and history.

The synthetic receipts model accepted historical Writer formats. No installed
consumer, native GitHub record, credential or model execution is used.
"""
import fcntl
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
BASELINE = 'b6edaaf4982df5b7dd6d56fd68b7ce7e34ccd7a9'
REVISION = 'a' * 40  # Synthetic installed-source receipt, not release authority.
OP = '12345678-1234-1234-1234-123456789abc'
COMPONENTS = ('consumer', 'controller', 'contracts', 'runtime', 'reviewer')
NODE = '/usr/bin/node'
spec = importlib.util.spec_from_file_location('history_consumer_publication',
    ROOT / 'deploy/ansible/scripts/publish_git_consumer.py')
publication = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publication)


HISTORY = r"""
import {join} from 'node:path';
import {CONSUMER,CONSUMER_DIGEST} from './consumer/consumer.mjs';
import {createPublicationStore,createAttemptStore} from './controller/src/attempt-store.mjs';
import {VERSION} from './controller/src/execution-contract.mjs';
import {completedAdmissionRecord} from './controller/src/admission-control.mjs';
import {canonicalAuthorityJson,renderAuthorityRecord,sha256Body,validateAuthorityRecord}
  from './contracts/src/github-authority.mjs';
const store=createPublicationStore(join(CONSUMER.paths.claimRoot,'publication-v2'));
const journal=createAttemptStore(CONSUMER.paths.attemptRoot);
const operation=process.argv[1], mode=process.argv[2];
const head='b'.repeat(40), repository=CONSUMER.repository;
const charter='Authority model: github-native-v1\nIssue closure policy: keep-open';
function request(task,route) {
  const value={schema_version:'3.0',kind:'task-request',repository,task,
    parent:{kind:'issue',number:task},charter_sha256:sha256Body(charter),step:1,route,
    purpose:'Synthetic isolated history qualification',scope:['Preserve original attempt evidence.'],
    model:'gpt-6.1-sol',effort:'xhigh',subagents:false,validation:['diff-check'],
    boundaries:['No external mutation.'],decisions:[],context:[],supersedes:null,
    branch:route==='auto'?`codex/task-${task}`:null,
    base_sha:route==='auto'?head:null,starting_head:route==='auto'?head:null,
    existing_pr:null,issue_closure_policy:'keep-open'};
  validateAuthorityRecord(value,{repository,task}); return value;
}
function envelope(runId,route='manual') {
  const task=runId+1000, selected=request(task,route);
  return {version:VERSION,repository,consumerDigest:CONSUMER_DIGEST,runId,attemptId:`run-${runId}`,
    route,target:'issue',number:task,issueNumber:task,step:1,
    branch:selected.branch,startHead:selected.starting_head,
    request:selected,requestReference:{kind:'issue-comment',id:runId+2000,
      parent:selected.parent,sha256:sha256Body(renderAuthorityRecord(selected))}};
}
function outcome(runId) {
  return {status:'BLOCKED',head:null,prNumber:null,outcomeId:runId+3000,
    bodySha256:sha256Body(`Synthetic native terminal body ${runId}`)};
}
function manualResult(e,parent) {
  const result={schema_version:'3.0',kind:'outcome',repository,task:e.issueNumber,parent,
    charter_sha256:e.request.charter_sha256,request:e.requestReference,attempt:e.attemptId,
    status:'implemented',result:{kind:parent.kind==='pull_request'?'git':'qualification',
      revision:head,identities:[{kind:'github-actions-run',id:String(e.runId)}]},
    warnings:[],limitations:['Synthetic receipt; no external operation performed.'],
    summary:'Preserved historical manual result.'};
  validateAuthorityRecord(result,{repository,task:e.issueNumber}); return result;
}
if(operation==='seed') {
  // 140 completed automatic records exercise real original-envelope journals.
  for(let id=1;id<=140;id++) {
    const e=envelope(id,'auto'), terminal=outcome(id);
    await store.put(id,{envelope:e,outcome:terminal,controllerLifecycle:{version:1,
      status:'complete',child:'not_started',containment:'not_required'}});
    await journal.put(id,{version:VERSION,envelope:e,outcome:terminal,execution:null});
  }
  // Seven current hashed refusals and one earlier sealed, unhashed refusal.
  for(let id=201;id<=208;id++) {
    const e=envelope(id), block={code:'AUTHORITY_ROUTE_MISMATCH'};
    delete e.request; delete e.requestReference;
    Object.assign(e,{admissionBlock:block,authorityDigest:null});
    const terminal=outcome(id), record={envelope:e,admissionBlock:block,outcome:terminal};
    if(id===208) {
      record.commentBodies={outcome:{number:e.issueNumber,sha256:terminal.bodySha256,
        rendererVersion:'human-v1'}}; delete terminal.bodySha256;
    }
    await store.put(id,record);
  }
  // The original v3 owner transport predates body hashes and body seals.
  for(const id of [301,302]) {
    const e=envelope(id), parent={kind:id===302?'pull_request':'issue',number:id===302?902:e.issueNumber};
    const result=manualResult(e,parent), record={envelope:e,publicationIntent:null,commentIntent:null,
      outcome:{status:'IMPLEMENTED_PENDING_FRESH_REVIEW',head,prNumber:id===302?902:null,
        outcomeId:id+3000,manual:true},
      manualResultAuthorization:{id:id+4000,
        sha256:sha256Body('```relay-manual-result\n'+canonicalAuthorityJson(result)+'\n```\n')}};
    if(id===302) record.prNumber=902;
    await store.put(id,record);
  }
  // Early direct-v3 saved exact submission/body digests, without publishedResult.
  const e=envelope(303), result=manualResult(e,{kind:'issue',number:e.issueNumber});
  const body=renderAuthorityRecord(result)+'\n\n<!-- relay:run-303:outcome -->';
  await store.put(303,{envelope:e,manualSubmission:{sha256:sha256Body(canonicalAuthorityJson(result)),
    parent:result.parent,rendererVersion:'human-v1'},
    commentBodies:{outcome:{number:e.issueNumber,sha256:sha256Body(body),rendererVersion:'human-v1'}},
    outcome:{status:'IMPLEMENTED_PENDING_FRESH_REVIEW',head,prNumber:null,outcomeId:3303,
      bodySha256:sha256Body(body),manual:true}});
  if(mode==='full') for(let id=401;id<=410;id++) {
    const e=envelope(id), record={envelope:e,outcome:null};
    // Issued, unissued and withdrawn-in-prose handoffs all lack completion proof.
    if(id<=405) record.commentBodies={handoff:{number:e.issueNumber,
      sha256:sha256Body(`Synthetic handoff ${id}`),rendererVersion:'human-v1'}};
    if(id===401) e.input='Owner withdrew future permission; prior execution remains unknown.';
    await store.put(id,record);
  }
}
const rows=await store.all(), unknown=[];
for(const row of rows) if(!await completedAdmissionRecord(row,journal)) unknown.push(row.envelope.runId);
console.log(JSON.stringify({records:rows.length,journals:(await journal.all()).length,
  unknown:unknown.sort((a,b)=>a-b),consumerDigest:CONSUMER_DIGEST}));
"""


@unittest.skipUnless(sys.platform == 'linux' and os.geteuid() == 0 and Path(NODE).exists(),
                     'real root Linux filesystem and Node required')
class GitConsumerHistoryRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='relay-history-recovery-', dir='/run')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.root.chmod(0o755)
        self.source = self.root / 'source'
        for component in COMPONENTS:
            shutil.copytree(ROOT / component, self.source / component,
                ignore=shutil.ignore_patterns('__pycache__', 'node_modules', 'target'))
        self.protect_source(self.source, REVISION)
        self.config, self.claims, self.journals = (self.root / name for name in ('config', 'claims', 'journals'))
        for path in (self.config, self.claims, self.journals):
            path.mkdir(mode=0o700)
        self.consumer = self.config / 'consumer.json'
        old = json.loads((ROOT / 'deploy/example.json').read_text())['consumer']
        for name in old['paths']:
            old['paths'][name] = str(self.root / 'configured' / name)
        old['paths'].update(claimRoot=str(self.claims), attemptRoot=str(self.journals))
        old['defaultProfile']['effort'] = 'xhigh'
        self.old = json.dumps(old).encode()
        self.consumer.write_bytes(self.old)
        self.consumer.chmod(0o644)
        new = json.loads(self.old)
        new['defaultProfile']['effort'] = 'medium'
        self.new = json.dumps(new).encode()
        self.desired = self.config / ('.consumer-' + OP + '.desired.json')
        self.desired.write_bytes(self.new)
        self.desired.chmod(0o600)
        self.backup = self.config / ('consumer-before-' + OP + '.json')
        self.gate = self.claims / 'admission-v1.json'
        self.lock = self.claims / 'publication-v2.lock'
        self.lock.write_bytes(b'')
        self.lock.chmod(0o600)
        self.repository = old['repository']
        self.env = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C',
            'RELAY_CONSUMER_CONFIG': str(self.consumer), 'RELAY_REPOSITORY': self.repository}
        self.calls = []
        self.initial = self.admission('initialize')
        self.expected_new_digest = self.node(
            "import{loadConsumer,consumerDigest}from'./consumer/consumer-config.mjs';"
            "console.log(JSON.stringify({digest:consumerDigest(loadConsumer(process.argv[1]))}));",
            str(self.desired))['digest']
        self.assertNotEqual(self.expected_new_digest, self.initial['consumerDigest'])

    @staticmethod
    def protect_source(source, revision):
        for path in [source, *source.rglob('*')]:
            path.chmod(0o755 if path.is_dir() else 0o644)
        (source / '.relay-source.json').write_text(json.dumps({'revision': revision}))

    def node(self, program, *arguments, source=None):
        result = subprocess.run([NODE, '--input-type=module', '-e', program, '--', *arguments],
            cwd=source or self.source, env=self.env, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def admission(self, *arguments, source=None):
        cli = (source or self.source) / 'controller/src/admission-cli.mjs'
        result = subprocess.run(['/usr/bin/flock', '-w', '5', str(self.lock), NODE, str(cli), *arguments],
            env=self.env, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def seed(self, mode='completed'):
        report = self.node(HISTORY, 'seed', mode)
        self.assertEqual(report['records'], 161 if mode == 'full' else 151)
        self.assertEqual(report['journals'], 140)
        self.assertEqual(report['consumerDigest'], self.initial['consumerDigest'])
        self.assertEqual(report['unknown'], list(range(401, 411)) if mode == 'full' else [])
        self.admission('quiesce', '--operation', OP, '--target', REVISION)
        self.assertTrue(self.admission('drain-check', '--operation', OP)['drained'])
        self.admission('phase', '--operation', OP, '--phase', 'applying')

    def history_snapshot(self):
        values = {}
        for root in (self.claims / 'publication-v2', self.journals):
            for path in root.rglob('*.json'):
                info = path.stat()
                self.assertEqual((info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode), info.st_nlink),
                                 (0, 0, 0o600, 1))
                values[str(path.relative_to(self.root))] = (path.read_bytes(), info.st_ino)
        return values

    def execute(self, argv, environment):
        # This is observation around the real subprocess, never a controller stub.
        with self.lock.open('rb') as stream:
            with self.assertRaises(BlockingIOError):
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.assertEqual(environment['RELAY_CONSUMER_CONFIG'], str(self.consumer))
        self.calls.append(argv)
        return publication._execute(argv, environment)

    def publish(self, execute=None):
        return publication.publish(self.source, self.config, self.desired, self.claims,
            self.repository, OP, REVISION, execute=execute or self.execute)

    def test_accepted_baseline_rejects_the_eleven_completed_manual_receipts(self):
        self.seed()
        baseline = self.root / 'accepted-baseline'
        baseline.mkdir()
        frozen_source = os.environ.get('RELAY_HISTORY_BASELINE_SOURCE')
        if frozen_source:
            frozen_source = Path(frozen_source)
            self.assertEqual(json.loads((frozen_source / '.relay-source.json').read_text())['revision'], BASELINE)
            for component in COMPONENTS:
                shutil.copytree(frozen_source / component, baseline / component)
        else:
            if shutil.which('git') is None:
                self.skipTest('historical accepted-source comparison requires frozen source or local Git objects')
            repository = Path(os.environ.get('RELAY_HISTORY_BASELINE_REPOSITORY', ROOT)).resolve()
            git = ['git', '-c', 'safe.directory=' + str(repository)]
            available = subprocess.run([*git, 'cat-file', '-e', BASELINE + '^{commit}'],
                cwd=repository, capture_output=True, timeout=60)
            if available.returncode and b'Not a valid object name' in available.stderr:
                self.skipTest('exact accepted baseline object unavailable in this source checkout')
            self.assertEqual(available.returncode, 0, 'accepted baseline Git object read failed')
            archived = subprocess.run([*git, 'archive', BASELINE, *COMPONENTS],
                cwd=repository, capture_output=True, timeout=60)
            self.assertEqual(archived.returncode, 0, 'accepted baseline Git archive read failed')
            with tarfile.open(fileobj=io.BytesIO(archived.stdout)) as archive:
                for member in archive.getmembers():
                    target = baseline / member.name
                    self.assertTrue(target.resolve().is_relative_to(baseline))
                    self.assertFalse(member.issym() or member.islnk())
                archive.extractall(baseline)
        self.protect_source(baseline, BASELINE)
        before, gate = self.history_snapshot(), self.gate.read_bytes()
        report = self.node(HISTORY, 'inventory', source=baseline)
        self.assertEqual(report['unknown'], [*range(201, 209), 301, 302, 303])
        with self.assertRaises(publication.ConsumerPublicationError) as caught:
            publication._execute([NODE, str(baseline / 'controller/src/admission-cli.mjs'),
                'consumer-transition-check', '--operation', OP, '--revision', REVISION], self.env)
        self.assertEqual(caught.exception.controller_diagnostic['code'], 'ADMISSION_NOT_DRAINED')
        self.assertEqual(self.gate.read_bytes(), gate)
        self.assertEqual(self.consumer.read_bytes(), self.old)
        self.assertFalse(self.backup.exists())
        self.assertEqual(self.history_snapshot(), before)

    def test_candidate_publishes_completed_history_without_rebinding_attempts_or_journals(self):
        self.seed()
        before = self.history_snapshot()
        previous = os.umask(0o077)
        try:
            published = self.publish()
        finally:
            os.umask(previous)
        self.assertEqual(published['status'], 'PUBLISHED')
        self.assertEqual(published['consumerDigest'], self.expected_new_digest)
        self.assertNotEqual(published['consumerDigest'], self.initial['consumerDigest'])
        self.assertEqual(self.consumer.read_bytes(), self.new)
        self.assertEqual(self.backup.read_bytes(), self.old)
        self.assertEqual(stat.S_IMODE(self.consumer.stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE(self.backup.stat().st_mode), 0o600)
        state = self.admission('status')
        self.assertEqual((state['operationId'], state['target'], state['phase']), (OP, REVISION, 'applying'))
        self.assertEqual(state['consumerDigest'], published['consumerDigest'])
        self.assertEqual((state['active'], state['unknown']), ([], []))
        report = self.node(HISTORY, 'inventory')
        self.assertEqual(report['unknown'], [])
        self.assertEqual(report['consumerDigest'], self.expected_new_digest)
        self.assertEqual(self.history_snapshot(), before)

    def test_full_history_blocks_ten_unknown_handoffs_but_code_only_apply_preserves_them(self):
        self.seed('full')
        before, gate = self.history_snapshot(), self.gate.read_bytes()
        with self.assertRaises(publication.ConsumerPublicationError) as caught:
            self.publish()
        self.assertEqual(str(caught.exception), 'CONSUMER_PUBLICATION_CONTROLLER_FAILED')
        self.assertEqual(caught.exception.controller_diagnostic, {'action': 'consumer-transition-check',
            'failure': 'nonzero_exit', 'exit_code': 1, 'code': 'HISTORICAL_TASK_AUTHORITY_UNAVAILABLE'})
        self.assertEqual(self.consumer.read_bytes(), self.old)
        self.assertFalse(self.backup.exists())
        self.assertEqual(self.gate.read_bytes(), gate)
        self.assertFalse(any('consumer-transition' in call for call in self.calls))
        self.desired.write_bytes(json.dumps(json.loads(self.old), indent=2).encode() + b'\n')
        self.calls.clear()
        result = self.publish()
        self.assertEqual(result['status'], 'UNCHANGED')
        self.assertEqual(result['consumerDigest'], self.initial['consumerDigest'])
        self.assertFalse(any('consumer-transition-check' in call or 'consumer-transition' in call
                             for call in self.calls))
        self.assertEqual(self.consumer.read_bytes(), self.old)
        self.assertFalse(self.backup.exists())
        self.assertEqual(self.gate.read_bytes(), gate)
        self.assertEqual(self.node(HISTORY, 'inventory')['unknown'], list(range(401, 411)))
        self.assertEqual(self.history_snapshot(), before)

    def test_real_same_uuid_recovery_after_rename_preserves_backup_and_original_history(self):
        self.seed()
        before, gate_before = self.history_snapshot(), self.gate.read_bytes()

        def stop_after_consumer_rename(argv, environment):
            if 'consumer-transition' in argv:
                self.assertEqual(self.consumer.read_bytes(), self.new)
                self.assertEqual(self.backup.read_bytes(), self.old)
                self.assertEqual(self.gate.read_bytes(), gate_before)
                # The one controlled fault is before the real gate operation.
                # Recovery below invokes the unmodified controller subprocess.
                with self.lock.open('rb') as stream:
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                raise publication.ConsumerPublicationError('CONSUMER_PUBLICATION_CONTROLLER_FAILED', {
                    'action': 'consumer-transition', 'failure': 'execution_failed'})
            return self.execute(argv, environment)

        with self.assertRaisesRegex(publication.ConsumerPublicationError,
            '^CONSUMER_PUBLICATION_TRANSITION_REQUIRES_RECOVERY$'):
            self.publish(execute=stop_after_consumer_rename)
        backup_inode = self.backup.stat().st_ino
        self.assertEqual(self.history_snapshot(), before)
        self.calls.clear()
        recovered = self.publish()
        self.assertEqual(recovered['status'], 'PUBLISHED')
        self.assertEqual(recovered['consumerDigest'], self.expected_new_digest)
        self.assertFalse(any('consumer-transition-check' in call for call in self.calls))
        self.assertEqual(sum('consumer-transition' in call for call in self.calls), 1)
        self.assertEqual(self.backup.stat().st_ino, backup_inode)
        self.assertEqual(self.backup.read_bytes(), self.old)
        state = self.admission('status')
        self.assertEqual(state['consumerDigest'], recovered['consumerDigest'])
        self.assertNotEqual(state['consumerDigest'], self.initial['consumerDigest'])
        self.assertEqual((state['operationId'], state['target'], state['phase']), (OP, REVISION, 'applying'))
        self.assertEqual((state['active'], state['unknown']), ([], []))
        self.assertEqual(self.history_snapshot(), before)
        gate_after = self.gate.read_bytes()
        self.calls.clear()
        replay = self.publish()
        self.assertEqual((replay['status'], replay['consumerDigest']), ('UNCHANGED', recovered['consumerDigest']))
        self.assertFalse(any('consumer-transition-check' in call or 'consumer-transition' in call
                             for call in self.calls))
        self.assertEqual(self.gate.read_bytes(), gate_after)
        self.assertEqual(self.consumer.read_bytes(), self.new)
        self.assertEqual(self.backup.stat().st_ino, backup_inode)
        self.assertEqual(self.backup.read_bytes(), self.old)
        self.assertEqual(self.history_snapshot(), before)
