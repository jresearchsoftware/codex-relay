"""Owner-only installed adapter for the bounded SERIAL/pool transition.

The deployment process holds the existing namespace and pool locks. Original
admission calls retain their publication lock and original module graph.
"""
import hashlib
import copy
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess

from managed_pool import Host, State, binding, pool_contract, require
from config import deployment_repository
from serial_pool_host import SerialPoolHost, SerialPoolGitHub
from serial_pool_transition import (MAX_SOURCE_FILES, ProtectedFiles, encoded, inspect,
                                    prepare, advance, write_new_gate)


def _node(source, consumer_path, code, payload=None, repository=None):
    environment = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C',
                   'RELAY_CONSUMER_CONFIG': consumer_path}
    if repository is not None:
        environment['RELAY_REPOSITORY'] = repository
    result = subprocess.run(['/usr/bin/node', '--input-type=module', '-e', code],
        input=None if payload is None else json.dumps(payload), text=True,
        env=environment, cwd=source,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60)
    require(result.returncode == 0, 'SERIAL_TRANSITION_ORIGINAL_READER_UNPROVEN')
    try:
        value = json.loads(result.stdout)
    except (ValueError, TypeError):
        require(False, 'SERIAL_TRANSITION_ORIGINAL_READER_UNPROVEN')
    return value


def consumer_digest(consumer, source):
    return _node(source, '/dev/null',
        'import {consumerDigest,validateConsumer} from "./consumer/consumer-config.mjs";'
        'let s="";for await(const b of process.stdin)s+=b;'
        'console.log(JSON.stringify(consumerDigest(validateConsumer(JSON.parse(s)))));', consumer)


def current_consumer_digest(config, source):
    """Read the installed prospective graph after its identity was verified.

    Historical callers keep consumer_digest and their original ordered bytes.
    """
    consumer_path = '/etc/' + config['environment']['namespace'] + '/consumer.json'
    ProtectedFiles().read(consumer_path, modes={0o644})
    return _node(source, consumer_path,
        'import {CONSUMER_DIGEST} from "./consumer/consumer.mjs";'
        'console.log(JSON.stringify(CONSUMER_DIGEST));', repository=deployment_repository(config))


def original_installation(target):
    """Read original protected bytes, including after current has moved."""
    namespace = target['environment']['namespace']
    require(re.fullmatch('[a-z][a-z0-9-]{0,30}', namespace), 'SERIAL_TRANSITION_NAMESPACE_INVALID')
    files = ProtectedFiles()
    consumer_path = '/etc/' + namespace + '/consumer.json'
    receipt_path = '/etc/' + namespace + '/serial-pool-compat-v1.json'
    receipt_raw = files.read(receipt_path, modes={0o644}, optional=True)
    if receipt_raw is None:
        install = Path('/opt') / namespace
        files.read('/etc/' + namespace + '/consumer.json', modes={0o644})
        current = install / 'current'
        info = current.lstat()
        require(info.st_uid == 0 and current.is_symlink(), 'SERIAL_TRANSITION_CURRENT_UNPROVEN')
        link = os.readlink(current)
        match = re.fullmatch('(?:/opt/' + re.escape(namespace) + '/)?releases/([0-9a-f]{40})', link)
        require(match is not None, 'SERIAL_TRANSITION_CURRENT_UNPROVEN')
        revision = match[1]
        release = '/opt/' + namespace + '/releases/' + revision
    else:
        receipt = json.loads(receipt_raw)
        require(receipt.get('namespace') == namespace and receipt.get('repository') == deployment_repository(target),
                'SERIAL_TRANSITION_RECEIPT_BINDING_INVALID')
        revision = receipt['original']['revision']
        require(re.fullmatch('[0-9a-f]{40}', revision), 'SERIAL_TRANSITION_CURRENT_UNPROVEN')
        consumer_path = '/etc/' + namespace + '/serial-consumer-v1.json'
        source_path = receipt['original'].get('sourceRoot')
        allowed = ['/opt/' + namespace + '/releases/' + revision,
                   '/opt/' + namespace + '/serial-compat-v1/' + revision]
        require(any(source_path == base + '/reviewed-source'
                    and receipt['original'].get('configPath') == base + '/deployment-config.json'
                    and receipt['original'].get('manifestPath') == base + '/artifact-manifest.json'
                    for base in allowed), 'SERIAL_TRANSITION_ORIGINAL_PATH_BINDING_INVALID')
        release = source_path.removesuffix('/reviewed-source')
    config_path = release + '/deployment-config.json'
    manifest_path = release + '/artifact-manifest.json'
    raw = files.read(config_path, modes={0o600})
    original = json.loads(raw)
    manifest_raw = files.read(manifest_path, modes={0o600, 0o640})
    manifest = json.loads(manifest_raw)
    identity = json.loads(files.read(release + '/reviewed-source/.relay-source.json', modes={0o600, 0o640, 0o644}))
    require(original['environment']['namespace'] == namespace
            and deployment_repository(original) == deployment_repository(target)
            and manifest.get('deploymentConfigSha256') == hashlib.sha256(raw).hexdigest()
            and all(manifest.get(key) == revision for key in ['commit', 'installedRevision', 'resolvedRevision'])
            and identity.get('revision') == revision and identity.get('tree') == manifest.get('gitTree')
            and re.fullmatch('[0-9a-f]{40}', identity.get('tree', '')),
            'SERIAL_TRANSITION_ORIGINAL_INSTALLATION_UNPROVEN')
    source = release + '/reviewed-source'
    source_sha256 = files.tree_sha256(source, source_links=original['environment'].get('compatibilityLinks', {}),
        original_source_root='/opt/' + namespace + '/releases/' + revision + '/reviewed-source')
    if receipt_raw is not None:
        # The retained original can predate the compatibility loader. Verify
        # its sealed bytes before executing any module from that old graph.
        retained = receipt['original']
        claim = original['consumer']['paths']['claimRoot']
        state = json.loads(files.read(claim + '/serial-pool-transition-v1.json', modes={0o600}))
        expected_receipt = {key: copy.deepcopy(state['plan'][key]) for key in
                            ['version', 'repository', 'namespace', 'original', 'target']}
        expected_receipt['operationId'] = state['operationId']
        gate_sha256 = hashlib.sha256(files.read(claim + '/admission-v1.json', modes={0o600})).hexdigest()
        expected_receipt['original']['gateSha256'] = gate_sha256
        receipt_sha256 = hashlib.sha256(receipt_raw).hexdigest()
        # Publishing the receipt can succeed just before the prepared-state
        # acknowledgement is lost. Its exact reserved plan is sufficient only
        # at that bounded frontier; the historical reader still runs last.
        require(encoded(expected_receipt) + b'\n' == receipt_raw
                and (state.get('receiptSha256') == receipt_sha256
                     or state.get('phase') == 'reserved' and 'receiptSha256' not in state)
                and retained.get('sourceTreeSha256') == source_sha256
                and retained.get('configSha256') == hashlib.sha256(raw).hexdigest()
                and retained.get('manifestSha256') == hashlib.sha256(manifest_raw).hexdigest()
                and retained.get('consumerSha256') == hashlib.sha256(files.read(consumer_path, modes={0o644})).hexdigest()
                and retained.get('gateSha256') == gate_sha256,
                'SERIAL_TRANSITION_ORIGINAL_CONTEXT_CHANGED')
    evidence = _node(source, consumer_path,
        'import {CONSUMER,CONSUMER_DIGEST} from "./consumer/consumer.mjs";'
        'import {validateEnvelope,digest} from "./controller/src/execution-contract.mjs";'
        'import {createAttemptStore} from "./controller/src/attempt-store.mjs";'
        'const records=await createAttemptStore(CONSUMER.paths.claimRoot+"/publication-v2").all();'
        'for(const r of records){if(!r.admissionBlock)validateEnvelope(r.envelope);'
        'if(r.envelope.consumerDigest!==CONSUMER_DIGEST)throw Error();}'
        'console.log(JSON.stringify({consumerDigest:CONSUMER_DIGEST,'
        'runs:records.map(r=>({runId:r.envelope.runId,attemptId:r.envelope.attemptId,'
        'envelopeSha256:digest(r.envelope)})).sort((a,b)=>a.runId-b.runId)}));',
        repository=deployment_repository(original))
    evidence.update(revision=revision, consumerPath=consumer_path, sourceRoot=source,
        manifestPath=manifest_path, configPath=config_path,
        runnerUid=pwd.getpwnam(original['environment']['generalRunner']['user']).pw_uid)
    return original, evidence


def original_gate(original, evidence):
    def gate(*args, services=None):
        # Each call uses the original parser/ABI, never current or the new
        # /etc consumer. The original source has no migration interpretation.
        command = ['/usr/bin/node', evidence['sourceRoot'] + '/controller/src/admission-cli.mjs', *args]
        if args[0] != 'drain':
            command = ['/usr/bin/flock', '-w', '180',
                original['consumer']['paths']['claimRoot'] + '/publication-v2.lock', *command]
        result = subprocess.run(command, input=None if services is None else json.dumps(services),
            text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=1860,
            env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C',
                 'RELAY_CONSUMER_CONFIG': evidence['consumerPath']})
        require(result.returncode == 0, 'SERIAL_TRANSITION_ORIGINAL_ADMISSION_UNPROVEN')
        return json.loads(result.stdout)
    return gate


def services(config):
    from config import compile_inputs
    values = compile_inputs(config)
    units = {'reviewer': values.get('relay_reviewer_service_name', 'reviewer-mcp.service'),
        'production': values.get('relay_production_runner_service_name', 'relay-runner.service'),
        'general': values.get('relay_general_runner_service_name', 'relay-general-runner.service'),
        'manualOutcome': values['relay_namespace'] + '-relay-manual-outcome.socket'}
    units.update({'slot-' + slot['relay_execution_slot']: slot['relay_runner_service_name']
                  for slot in values.get('relay_additional_execution_slots', [])})
    result = {}
    for name, unit in units.items():
        process = subprocess.run(['/usr/bin/systemctl', 'show', unit,
            '--property=LoadState,ActiveState,SubState,UnitFileState,MainPID,ExecMainStartTimestampMonotonic'],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=30)
        rows = dict(row.split('=', 1) for row in process.stdout.splitlines() if '=' in row)
        require(rows.get('LoadState') in ['loaded', 'not-found']
                and rows.get('ActiveState') in ['active', 'inactive', 'failed'],
                'SERIAL_TRANSITION_SERVICE_ACTIVITY_UNPROVEN')
        absent = rows['LoadState'] == 'not-found'
        active = rows['ActiveState'] == 'active'
        enabled = rows.get('UnitFileState', 'disabled')
        if absent:
            require(not active and rows.get('SubState') == 'dead'
                    and enabled in ['', 'not-found', 'disabled'], 'SERIAL_TRANSITION_SERVICE_ACTIVITY_UNPROVEN')
            enabled = 'disabled'
        require(enabled in ['enabled', 'enabled-runtime', 'disabled'], 'SERIAL_TRANSITION_SERVICE_ACTIVITY_UNPROVEN')
        if active:
            require(process.returncode == 0 and enabled in ['enabled', 'enabled-runtime']
                    and (rows.get('SubState') == 'listening' if name == 'manualOutcome' else
                         rows.get('SubState') == 'running'
                         and re.fullmatch('[1-9][0-9]*', rows.get('MainPID', ''))
                         and re.fullmatch('[1-9][0-9]*', rows.get('ExecMainStartTimestampMonotonic', ''))),
                    'SERIAL_TRANSITION_SERVICE_ACTIVITY_UNPROVEN')
        result[name] = {'active': active, 'enabled': enabled, 'load': rows['LoadState']}
    # Preserve the installed pre-manual-capability snapshot ABI when absent.
    if result['manualOutcome'] == {'active': False, 'enabled': 'disabled', 'load': 'not-found'}:
        result.pop('manualOutcome')
    return result


def pool_ready(config, github):
    contract = pool_contract(config)
    state = State('/var/lib/codex-relay-pools/' + contract['name']).read()
    require(state is not None and state.get('binding') == binding(contract), 'SERIAL_TRANSITION_POOL_BINDING_UNPROVEN')
    host = Host(contract)
    remote = github.runners()
    for member in contract['members'][:contract['desiredCapacity']]:
        matches = [runner for runner in remote if runner.get('name') == member['name']]
        require(len(matches) == 1 and matches[0].get('id') == host.registration(member)
                and matches[0].get('status') == 'online' and host.ready(member),
                'SERIAL_TRANSITION_POOL_READINESS_UNPROVEN')
    return True


def _current_source_links(files, source):
    """Observe only protected aliases to this release's canonical components.

    A later Git Apply must not need the mutable deployment snapshot to select
    the installed reader. The complete tree walk below still revalidates every
    alias, directory and file before any installed code executes.
    """
    components = {'controller', 'consumer', 'contracts', 'runtime', 'reviewer'}
    links = {}
    count = 0

    def visit(directory, prefix=''):
        nonlocal count
        with files.parent(directory + '/.source-links') as (descriptor, _):
            for name in os.listdir(descriptor):
                count += 1
                require(count <= MAX_SOURCE_FILES, 'SERIAL_TRANSITION_SOURCE_LIMIT')
                info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                relative = prefix + name
                if stat.S_ISLNK(info.st_mode):
                    target = os.readlink(name, dir_fd=descriptor)
                    component = target.removeprefix(source + '/')
                    require(component in components and target == source + '/' + component
                            and len(links) < 8, 'SERIAL_TRANSITION_SOURCE_LINK_UNPROVEN')
                    links[relative] = component
                elif stat.S_ISDIR(info.st_mode):
                    visit(directory + '/' + name, relative + '/')

    visit(source)
    return links


def current_source(config, *, git_desired=False):
    """Select a protected canonical installed graph before invoking its code."""
    namespace = config['environment']['namespace']
    install = '/opt/' + namespace
    files = ProtectedFiles()
    with files.parent(install + '/current') as (parent, name):
        metadata = os.stat(name, dir_fd=parent, follow_symlinks=False)
        require(metadata.st_uid == 0 and stat.S_ISLNK(metadata.st_mode),
                'SERIAL_TRANSITION_CURRENT_UNPROVEN')
        link = os.readlink(name, dir_fd=parent)
    matched = re.fullmatch('(?:' + re.escape(install) + '/)?releases/([0-9a-f]{40})', link)
    require(matched is not None, 'SERIAL_TRANSITION_CURRENT_UNPROVEN')
    revision = matched[1]
    release = install + '/releases/' + revision
    manifest = json.loads(files.read(release + '/artifact-manifest.json', modes={0o600, 0o640}))
    source = release + '/reviewed-source'
    identity = json.loads(files.read(source + '/.relay-source.json', modes={0o600, 0o640, 0o644}))
    require(all(manifest.get(key) == revision for key in ['commit', 'installedRevision', 'resolvedRevision'])
            and identity.get('revision') == revision and identity.get('tree') == manifest.get('gitTree')
            and re.fullmatch('[0-9a-f]{40}', identity.get('tree', '')),
            'SERIAL_TRANSITION_CURRENT_UNPROVEN')
    if git_desired:
        links = _current_source_links(files, source)
    else:
        raw = files.read(release + '/deployment-config.json', modes={0o600})
        installed = json.loads(raw)
        require(installed['environment']['namespace'] == namespace
                and deployment_repository(installed) == deployment_repository(config)
                and manifest.get('deploymentConfigSha256') == hashlib.sha256(raw).hexdigest(),
                'SERIAL_TRANSITION_CURRENT_UNPROVEN')
        links = installed['environment'].get('compatibilityLinks', {})
    files.tree_sha256(source, source_links=links, original_source_root=source)
    return source


def target_installed(config, revision, target_digest):
    """An exact completed backend identity permits forward repair, not Apply."""
    namespace = config['environment']['namespace']
    current = Path('/opt') / namespace / 'current'
    expected = '/opt/' + namespace + '/releases/' + revision
    info = current.lstat()
    require(info.st_uid == 0 and current.is_symlink(), 'SERIAL_TRANSITION_CURRENT_UNPROVEN')
    if os.readlink(current) not in [expected, 'releases/' + revision]:
        return False
    files = ProtectedFiles()
    pending_raw = files.read('/var/lib/' + namespace + '-production-operation.json', modes={0o600}, optional=True)
    if pending_raw is not None:
        pending = json.loads(pending_raw)
        require(pending.get('state') == 'RECOVERY_REQUIRED' and pending.get('phase') == 'apply'
                and pending.get('target_head') == revision, 'SERIAL_TRANSITION_BACKEND_OPERATION_UNPROVEN')
        return False
    raw = files.read(expected + '/deployment-config.json', modes={0o600})
    if json.loads(raw) != config:
        return False
    manifest = json.loads(files.read(expected + '/artifact-manifest.json', modes={0o600, 0o640}))
    identity = json.loads(files.read(expected + '/reviewed-source/.relay-source.json', modes={0o644, 0o640, 0o600}))
    require(all(manifest.get(key) == revision for key in ['commit', 'installedRevision', 'resolvedRevision'])
            and manifest.get('deploymentConfigSha256') == hashlib.sha256(raw).hexdigest()
            and identity.get('revision') == revision and manifest.get('gitTree') == identity.get('tree'),
            'SERIAL_TRANSITION_TARGET_INSTALLATION_UNPROVEN')
    observed = _node(expected + '/reviewed-source', '/etc/' + namespace + '/consumer.json',
        'import {CONSUMER_DIGEST} from "./consumer/consumer.mjs";'
        'import {installedAdmissionControl} from "./controller/src/admission-cli.mjs";'
        'console.log(JSON.stringify({digest:CONSUMER_DIGEST,gate:await installedAdmissionControl().read()}));',
        repository=deployment_repository(config))
    require(observed['digest'] == target_digest, 'SERIAL_TRANSITION_TARGET_INSTALLATION_UNPROVEN')
    return True


def _current_admission(config, *, git_desired=False):
    """Use the protected installed validator and gate, independently of intent."""
    namespace = config['environment']['namespace']
    consumer_path = '/etc/' + namespace + '/consumer.json'
    ProtectedFiles().read(consumer_path, modes={0o644})
    source = current_source(config, git_desired=git_desired)
    return _node(source, consumer_path,
        'import {CONSUMER_DIGEST,INSTALLATION_CONSUMER} from "./consumer/consumer.mjs";'
        'import {installedAdmissionControl} from "./controller/src/admission-cli.mjs";'
        'console.log(JSON.stringify({gate:await installedAdmissionControl().read(),digest:CONSUMER_DIGEST,'
        'managed:Boolean(INSTALLATION_CONSUMER.generalRunnerPool)}));',
        repository=deployment_repository(config))


def preflight(config, github, target_digest):
    namespace = config['environment']['namespace']
    git_desired = config['environment']['localApply'].get('source') == 'git'
    receipt_path = '/etc/' + namespace + '/serial-pool-compat-v1.json'
    receipt_raw = ProtectedFiles().read(receipt_path, modes={0o644}, optional=True)
    current = Path('/opt') / namespace / 'current'
    if receipt_raw is None:
        if not current.exists() and not current.is_symlink():
            from pool_migration import reject_serial_transition
            reject_serial_transition(pool_contract(config))
            return None
        if git_desired:
            # The live protected consumer identifies an already-managed host.
            # Its mutable deployment snapshot is neither desired authority nor
            # sealed SERIAL history. A real SERIAL origin still takes the exact
            # original-installation path below before any migration is allowed.
            live = json.loads(ProtectedFiles().read('/etc/' + namespace + '/consumer.json', modes={0o644}))
            if isinstance(live, dict) and 'generalRunnerPool' in live:
                observed = _current_admission(config, git_desired=True)
                require(observed.get('managed') is True
                        and re.fullmatch('[0-9a-f]{64}', observed.get('digest', ''))
                        and observed.get('gate', {}).get('consumerDigest') == observed['digest'],
                        'SERIAL_TRANSITION_NEW_GATE_UNPROVEN')
                from pool_migration import reject_serial_transition
                reject_serial_transition(pool_contract(config))
                return None
        # An ordinary already-managed installation has no SERIAL transition.
        # Keep its existing complete protected peer/pool preflight unchanged.
        original, _ = original_installation(config)
        if 'generalRunnerPool' in original['consumer']:
            from pool_migration import reject_serial_transition
            reject_serial_transition(pool_contract(config))
            return None
    original, evidence = original_installation(config)
    adapter = SerialPoolGitHub(github)
    host = SerialPoolHost(adapter, pool_ready=lambda value: pool_ready(value, github))
    gate = original_gate(original, evidence)
    if receipt_raw is not None:
        receipt = json.loads(receipt_raw)
        state = json.loads(ProtectedFiles().read(
            original['consumer']['paths']['claimRoot'] + '/serial-pool-transition-v1.json', modes={0o600}))
        if state.get('phase') == 'retired':
            if not git_desired:
                from serial_pool_transition import validate_delta
                validate_delta(original, config)
            current_binding = host.inspect_legacy(original)
            require((git_desired or receipt['target']['consumerDigest'] == target_digest)
                    and hashlib.sha256(receipt_raw).hexdigest() == state.get('receiptSha256')
                    and receipt['original']['sourceTreeSha256'] == ProtectedFiles().tree_sha256(evidence['sourceRoot'],
                        source_links=original['environment'].get('compatibilityLinks', {}),
                        original_source_root='/opt/' + config['environment']['namespace']
                            + '/releases/' + evidence['revision'] + '/reviewed-source')
                    and receipt['original']['gateSha256'] == hashlib.sha256(ProtectedFiles().read(
                        original['consumer']['paths']['claimRoot'] + '/admission-v1.json', modes={0o600})).hexdigest()
                    and {key: value for key, value in current_binding.items() if key != 'ownWorker'} == state['plan']['binding']
                    and host.legacy_stopped(state['plan']['binding'])
                    and adapter.observe_legacy(state['plan']['binding']) is None,
                    'SERIAL_TRANSITION_RETIRED_BINDING_UNPROVEN')
            new_gate = json.loads(ProtectedFiles().read(
                original['consumer']['paths']['claimRoot'] + '/admission-pool-v1.json', modes={0o600}))
            observed = _current_admission(config, git_desired=git_desired)
            require(observed.get('gate') == new_gate
                    and new_gate.get('consumerDigest') == observed.get('digest')
                    and (git_desired or observed.get('digest') == target_digest),
                    'SERIAL_TRANSITION_NEW_GATE_UNPROVEN')
            # Later qualified lifecycle operations have their own UUID/target.
            # Only the original migration operation denotes unfinished cutover.
            completion = new_gate.get('phase') != 'open' and new_gate.get('operationId') == state['operationId']
            require(not completion or (new_gate.get('target') == state['targetRevision']
                    and receipt['target']['consumerDigest'] == target_digest
                    and state['plan']['targetConfigSha256'] == hashlib.sha256(encoded(config)).hexdigest()),
                    'SERIAL_TRANSITION_NEW_GATE_UNPROVEN')
            return {'phase': 'retired', 'operationId': state['operationId'], 'targetRevision': state['targetRevision'],
                    'completionRequired': completion}
    proof = inspect(original, config, evidence, target_consumer_digest=target_digest,
                    host=host, github=adapter, gate=gate)
    if receipt_raw is not None:
        proof['phase'] = state.get('phase')
    state_raw = ProtectedFiles().read(original['consumer']['paths']['claimRoot'] + '/serial-pool-transition-v1.json',
                                     modes={0o600}, optional=True)
    if state_raw is not None:
        state = json.loads(state_raw)
        require(state.get('version') == 1
                and state.get('plan', {}).get('targetConfigSha256') == hashlib.sha256(encoded(config)).hexdigest()
                and re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', state.get('operationId', '')),
                'SERIAL_TRANSITION_OPERATION_CONFLICT')
        proof['operationId'] = state['operationId']
    return proof


def begin(config, github, target_digest, operation_id, target_revision):
    probe = preflight(config, github, target_digest)
    if probe is None:
        return probe
    if probe.get('phase') == 'retired':
        require(probe['operationId'] == operation_id and probe['targetRevision'] == target_revision,
                'SERIAL_TRANSITION_OPERATION_CONFLICT')
        return probe
    original, evidence = original_installation(config)
    adapter = SerialPoolGitHub(github)
    # Before the backend runs, no readiness claim permits removal.
    host = SerialPoolHost(adapter, pool_ready=lambda _value: False)
    gate = original_gate(original, evidence)
    state_path = original['consumer']['paths']['claimRoot'] + '/serial-pool-transition-v1.json'
    raw = ProtectedFiles().read(state_path, modes={0o600}, optional=True)
    observed = json.loads(raw)['services'] if raw is not None else services(original)
    state = prepare(original, config, evidence, operation_id=operation_id, target_revision=target_revision,
                    target_consumer_digest=target_digest, services=observed, host=host, github=adapter, gate=gate)
    # Fixed historical consumer copy is now published; future original calls
    # must not follow the consumer.json that the backend will replace.
    original, evidence = original_installation(config)
    gate = original_gate(original, evidence)
    if state['phase'] in ['prepared', 'stop-intent', 'stopped']:
        state = advance(original, config, evidence, host=host, github=adapter, gate=gate)
    else:
        bound = host.inspect_legacy(original)
        require({key: value for key, value in bound.items() if key != 'ownWorker'} == state['plan']['binding']
                and host.legacy_stopped(state['plan']['binding']), 'SERIAL_TRANSITION_STOP_UNPROVEN')
    if target_installed(config, target_revision, target_digest):
        # The new backend is already bound. Reapplying would reinterpret live
        # pool activity against the first absent-service snapshot. The owner
        # coordinator reconciles capacity, post-checks and finishes instead.
        return {'phase': 'installed', 'operationId': operation_id, 'targetRevision': target_revision}
    require(state['phase'] == 'stopped', 'SERIAL_TRANSITION_STOP_UNPROVEN')
    write_new_gate(original, config, evidence, operation_id=operation_id, target_revision=target_revision,
                   target_consumer_digest=target_digest, services=services(config))
    return state


def finish(config, github):
    original, evidence = original_installation(config)
    adapter = SerialPoolGitHub(github)
    host = SerialPoolHost(adapter, pool_ready=lambda value: pool_ready(value, github))
    result = advance(original, config, evidence, host=host, github=adapter,
                     gate=original_gate(original, evidence))
    require(result['phase'] == 'retired', 'SERIAL_TRANSITION_RETIREMENT_UNPROVEN')
    return result
