"""Public installer orchestration with real retained-history readers and locks.

This composes the existing public-installer fixture with real Node subprocesses,
the byte-verified historical 0aff reader, protected on-disk records, flock and
the actual Writer lock lease. Host inventory, package staging and the Ansible
service/backend effects remain synthetic; this is not a live installation proof.
No network or credential is needed. Root/Linux fixtures live only under /run.
"""
import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import sys
import tempfile

import pytest

from test_install_preflight_ordering import invocation, backend, TARGET
from test_consumer_preflight_cli import protect_fixture_source
import install_preflight


ROOT = Path(__file__).resolve().parents[2]
HISTORICAL = '0aff32a6873262185f60364463f4e97ef330de89'
NODE = '/usr/bin/node'
SEED = r"""
import {currentEnvelope} from './controller/test/fixture.mjs';
import {createPublicationStore} from './controller/src/attempt-store.mjs';
import {predispatchBinding,completedPredispatchRecovery} from './controller/src/predispatch-recovery.mjs';
import {extractHistoricalRuntime} from './controller/test/historical-runtime.mjs';
import {CONSUMER} from './consumer/consumer.mjs';
const e=currentEnvelope({runId:99,step:2,transport:'label',readyEventId:71,
 readyLabel:'codex-ready-auto',readyEventAt:'2026-09-04T12:00:00Z'});
const r={envelope:e,nativeAdmission:true,stepProjectionFrom:['step-1'],
 controllerLifecycle:{version:1,status:'active'},publicationIntent:null,
 publishedHead:null,finalHead:null,outcome:null};
r.predispatchRecovery={version:1,status:'finalized',authorizationId:10000,
 binding:predispatchBinding(r),authorizedAt:'2026-09-04T12:02:00Z',
 completedAt:'2026-09-04T12:03:00Z'};
if(!completedPredispatchRecovery(r))throw Error('Invalid synthetic recovery fixture');
await createPublicationStore(CONSUMER.paths.claimRoot+'/publication-v2').put(99,r);
await extractHistoricalRuntime(process.argv[1],process.argv[2]);
console.log(JSON.stringify({digest:e.consumerDigest}));
"""


@pytest.fixture
def real_gate(invocation, monkeypatch):
    if sys.platform != 'linux' or os.geteuid() != 0 or not Path(NODE).exists():
        pytest.skip('root Linux with Node required for protected installer integration')
    args, events, projected_gate, state, records = invocation
    with tempfile.TemporaryDirectory(prefix='relay-predispatch-public-', dir='/run') as temporary:
        root = Path(temporary)
        source, historical = root / 'candidate', root / 'historical'
        for component in ['consumer', 'controller', 'runtime', 'contracts', 'reviewer/src']:
            shutil.copytree(ROOT / component, source / component,
                ignore=shutil.ignore_patterns('target', 'node_modules', '__pycache__'))
        (source / 'deploy').mkdir()
        for name in ['installation-contract.json', 'writer_lock_lease.py']:
            shutil.copyfile(ROOT / 'deploy' / name, source / 'deploy' / name)
        (source / '.relay-source.json').write_text(json.dumps({'revision': TARGET}))
        consumer = json.loads((ROOT / 'consumer/fixtures/example.json').read_text())
        for key in consumer['paths']:
            consumer['paths'][key] = str(root / 'state' / key)
        config = root / 'consumer.json'
        config.write_text(json.dumps(consumer))
        claim = Path(consumer['paths']['claimRoot'])
        claim.mkdir(parents=True)
        lock = claim / 'publication-v2.lock'
        lock.touch()
        environment = {'PATH': '/usr/bin:/bin', 'HOME': str(root), 'LANG': 'C', 'LC_ALL': 'C',
                       'RELAY_CONSUMER_CONFIG': str(config)}

        def node(argv, *, cwd=source, locked=True, timeout=15):
            command = [NODE, *map(str, argv)]
            if locked:
                command = ['/usr/bin/flock', '-w', '5', str(lock), *command]
            result = subprocess.run(command, cwd=cwd, env=environment, text=True,
                                    capture_output=True, timeout=timeout)
            if result.returncode:
                raise RuntimeError(result.stderr)
            return json.loads(result.stdout)

        digest = node(['--input-type=module', '-e', SEED, historical, HISTORICAL])['digest']
        protect_fixture_source(source)
        protect_fixture_source(historical)
        # Compute artifact tree identity with independent Git, whose metadata
        # remains outside the staged regular-file archive.
        proof = root / 'proof.git'
        subprocess.run(['/usr/bin/git', 'init', '--bare', str(proof)], check=True,
                       capture_output=True, env=environment)
        git = ['/usr/bin/git', '--git-dir=' + str(proof), '--work-tree=' + str(source)]
        subprocess.run([*git, 'add', 'consumer', 'controller', 'runtime', 'contracts', 'reviewer', 'deploy'],
                       check=True, capture_output=True, env=environment)
        tree = subprocess.check_output([*git, 'write-tree'], env=environment, text=True).strip()
        (source / '.relay-source.json').write_text(json.dumps({'revision': TARGET, 'tree': tree}))
        record = claim / 'publication-v2/99.json'
        before = record.read_bytes()
        original_gate = state['preparation']
        base = install_preflight.PreparedInstall  # injected orchestration adapter
        # Load the production class separately so drain/lease behavior stays
        # real even while the orchestration fixture patches its module.
        import importlib.util
        spec = importlib.util.spec_from_file_location('predispatch_real_preflight', ROOT / 'deploy/install_preflight.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        real = module.PreparedInstall

        def admission(command, *options, old=False):
            selected = historical if old else source
            value = node([selected / 'controller/src/admission-cli.mjs', command, *options],
                         locked=command != 'drain')
            if not old and isinstance(value, dict) and 'phase' in value:
                projected_gate.update(phase=value['phase'], operation=value.get('operationId'))
            return value

        class Preparation(base):
            def __init__(self, *arguments, **options):
                super().__init__(*arguments, **options)
                self.source = str(source)
                self.stage = str(root)
                self.lease_path = str(root / 'writer-lock.json')
                self.values = {'relay_consumer_config_path': str(config),
                               'relay_github_repository': consumer['repository']}

            def consumer(self, **options):
                super().consumer(**options)
                self.initial['baselineDigest'] = digest

            def drain_staged(self):
                events.append('real-drain')
                return real.drain_staged(self)

            def execute(self, argv, **options):
                if 'drain-check' in argv:
                    events.append('real-drain-check')
                result = subprocess.run(argv, env=environment, text=True, capture_output=True,
                                        timeout=options.get('timeout', 15))
                if result.returncode:
                    raise RuntimeError(result.stderr)
                value = json.loads(result.stdout)
                if isinstance(value, dict) and 'phase' in value:
                    projected_gate.update(phase=value['phase'], operation=value.get('operationId'))
                return value

            def lock_writer(self):
                events.append('real-writer-lock')
                self.holder = subprocess.Popen(['/usr/bin/python3', '-I',
                    str(source / 'deploy/writer_lock_lease.py'), '--hold', str(lock),
                    self.lease_path, self.operation, TARGET, digest], env=environment,
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                with selectors.DefaultSelector() as selector:
                    selector.register(self.holder.stdout, selectors.EVENT_READ)
                    assert selector.select(10), 'Writer lease did not become ready'
                    assert self.holder.stdout.readline() == 'WRITER_LOCK_READY\n'

            def admission_prefix(self):
                return real.admission_prefix(self)

            def release_writer(self):
                if self.holder is not None:
                    events.append('real-writer-release')
                    self.holder.stdin.close()
                    assert self.holder.wait(timeout=10) == 0
                    self.holder.stdout.close()
                    self.holder.stderr.close()
                    self.holder = None

        monkeypatch.setattr(install_preflight, 'PreparedInstall', Preparation)

        def remote_admission(_target, _key, _namespace, command, *options, **kwargs):
            events.append('real:' + command)
            return admission(command, *options)

        monkeypatch.setattr(backend, 'remote_admission', remote_admission)
        admission('initialize')
        yield args, events, projected_gate, state, admission, record, before, node, source, historical
        prepared = state.get('preparation')
        if prepared is not None and prepared is not original_gate:
            prepared.release_writer()


def test_public_upgrade_drains_with_real_candidate_reader_and_retains_original_record(real_gate):
    args, events, gate, state, admission, record, before, *_ = real_gate
    old = admission('status', old=True)
    assert old['active'] == [99] and old['unknown'] == []
    assert admission('status')['active'] == []
    backend.run(args)
    after = admission('status')
    assert after['phase'] == 'open' and after['active'] == after['unknown'] == []
    assert record.read_bytes() == before
    assert events.index('real-drain') < events.index('real-writer-lock')
    assert events.index('real-writer-lock') < events.index('real-drain-check') < events.index('backend')
    assert events.index('backend') < events.index('real-writer-release') < events.index('real:resume')


def test_public_rollback_to_old_runtime_stops_before_gate_or_backend_mutation(real_gate, monkeypatch):
    args, events, gate, state, admission, record, before, node, source, historical = real_gate
    backend.run(args)
    state['installed'] = TARGET
    args.resolved_revision = HISTORICAL
    args.intent_expected_installed_revision = TARGET
    args.git_intent['product_sha'] = HISTORICAL
    monkeypatch.setattr(backend, 'source_identity', lambda _: {'revision': HISTORICAL, 'tree': 'f' * 40})
    start = len(events)
    gate_before = admission('status')
    with pytest.raises(RuntimeError, match='PREDISPATCH_TARGET_INCOMPATIBLE'):
        backend.run(args)
    assert admission('status') == gate_before
    assert record.read_bytes() == before
    assert 'backend' not in events[start:]
    assert 'real:resume' not in events[start:]
