"""Intent-driven composition over Relay's existing protected install primitives.

Git inputs select desired configuration. Inventory selects a safe strategy and
supplies readback evidence; it never supplies replacement configuration values.
The ordinary command does not create another deployment journal.
"""
import argparse
from contextlib import ExitStack
import copy
import hashlib
import http.client
import inspect
import json
import os
from pathlib import Path
import re
import ssl
import stat
import subprocess
import tempfile

from ansible_transport import qualify_target
from config import loads, unique_object


REVISION = re.compile(r'[0-9a-f]{40}')
DIGEST = re.compile(r'[0-9a-f]{64}')
REPOSITORY = re.compile(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+')
CAPABILITIES = {'lifecycle-v1', 'git-desired-v1', 'integration-artifact-v1'}
# Task 25's accepted and live-qualified admission/lifecycle rollout. One lineage
# boundary classifies all pre-metadata revisions; this is not a transition table.
LEGACY_LIFECYCLE_BOUNDARY = 'e1f00e828242c794c013ce8f555578d03564a441'


def require(value, code):
    if not value:
        raise ValueError('RELAY_INSTALL_' + code)


def contract(value):
    require(isinstance(value, dict) and value.keys() == {'schemaVersion', 'epoch', 'capabilities'}
            and type(value['schemaVersion']) is int and value['schemaVersion'] == 1
            and type(value['epoch']) is int and value['epoch'] > 0
            and isinstance(value['capabilities'], list)
            and all(isinstance(item, str) and item in CAPABILITIES for item in value['capabilities'])
            and len(value['capabilities']) == len(set(value['capabilities'])),
            'COMPATIBILITY_METADATA_INVALID')
    return value


def source_repository(config):
    value = config['source']['repository'].removeprefix('https://github.com/').removeprefix(
        'git@github.com:').removesuffix('.git')
    require(REPOSITORY.fullmatch(value), 'PRODUCT_REPOSITORY_INVALID')
    return value


def _git(root, *arguments):
    result = subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false',
        '-C', str(root), *arguments], text=True, capture_output=True, timeout=120)
    require(result.returncode == 0, 'GIT_SOURCE_UNAVAILABLE')
    return result.stdout.strip()


def qualify_identity(target, key):
    """Retain the existing owner SSH key and configured host identity checks."""
    if target.get('connection', 'ssh') == 'ssh':
        require(key.is_file() and not key.is_symlink(), 'OPERATOR_KEY_INVALID')
        identity = subprocess.run(['ssh-keygen', '-lf', str(key)], capture_output=True,
                                  check=True, text=True, timeout=30).stdout.split()
        require(len(identity) > 1 and identity[1] == target.get('identityFingerprint'),
                'OPERATOR_KEY_IDENTITY_INVALID')
        known = subprocess.run(['ssh-keygen', '-F', target['host']], capture_output=True,
                               check=True, text=True, timeout=30).stdout
        fingerprints = subprocess.run(['ssh-keygen', '-lf', '-'], input=known,
                                     capture_output=True, check=True, text=True, timeout=30).stdout
        require(any(len(row.split()) > 1 and row.split()[1] == target['hostFingerprint']
                    for row in fingerprints.splitlines()), 'HOST_IDENTITY_INVALID')
    qualify_target(target, key)


def prepare_target(target, key, config, revision, guard):
    """Reprove actual resource identity and perform bounded legacy hardening."""
    require(guard is not None and guard.poll() is None, 'HOST_LOCK_LOST')
    from clean_reinstall import remote_action
    result = remote_action(target, key, config, revision, action='prepare',
                           guard=guard, git_desired=True)
    require(guard.poll() is None, 'HOST_LOCK_LOST')
    require(isinstance(result, dict) and result.keys() == {'state', 'namespace', 'hardened'}
            and result['state'] == 'PREPARED' and result['namespace'] == config['environment']['namespace']
            and type(result['hardened']) is bool,
            'OPERATION_DIRECTORY_UNSAFE')
    return result['hardened']


def legacy_strategy(root, repository, installed):
    """Prove a single known legacy lineage locally, then via public GitHub.

    Installed code does not interpret future target metadata. A shallow accepted
    source need not carry the full historical graph: the bounded compare read is
    a fallback for that proof, never an alternative product/config selector.
    """
    require(REVISION.fullmatch(installed or '') and REPOSITORY.fullmatch(repository or ''),
            'LEGACY_IDENTITY_INVALID')
    for ancestor, descendant, strategy in [
            (LEGACY_LIFECYCLE_BOUNDARY, installed, 'upgrade'),
            (installed, LEGACY_LIFECYCLE_BOUNDARY, 'reinstall')]:
        result = subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false',
            '-C', str(root), 'merge-base', '--is-ancestor', ancestor, descendant],
            text=True, capture_output=True, timeout=30)
        if result.returncode == 0:
            return strategy
    connection = http.client.HTTPSConnection('api.github.com', timeout=20,
                                              context=ssl.create_default_context())
    try:
        connection.request('GET', '/repos/' + repository + '/compare/' + LEGACY_LIFECYCLE_BOUNDARY
            + '...' + installed + '?per_page=1', headers={
                'Accept': 'application/vnd.github+json', 'User-Agent': 'codex-relay-install',
                'Cache-Control': 'no-cache'})
        response = connection.getresponse()
        require(response.status == 200, 'LEGACY_COMPATIBILITY_UNPROVEN')
        raw = response.read(1048577)
        require(len(raw) <= 1048576, 'LEGACY_COMPATIBILITY_UNPROVEN')
        value = json.loads(raw)
        require(value.get('base_commit', {}).get('sha') == LEGACY_LIFECYCLE_BOUNDARY,
                'LEGACY_COMPATIBILITY_UNPROVEN')
        merge_base = value.get('merge_base_commit', {}).get('sha')
        if value.get('status') in ['ahead', 'identical'] and merge_base == LEGACY_LIFECYCLE_BOUNDARY:
            return 'upgrade'
        if value.get('status') == 'behind' and merge_base == installed:
            return 'reinstall'
        raise ValueError('RELAY_INSTALL_LEGACY_TRANSITION_UNSUPPORTED')
    except (OSError, http.client.HTTPException, json.JSONDecodeError, UnicodeError):
        raise ValueError('RELAY_INSTALL_LEGACY_COMPATIBILITY_UNPROVEN') from None
    finally:
        connection.close()


def pair_digest(receipt):
    fields = ['product_repository', 'product_repository_id', 'product_sha', 'config_repository',
              'config_repository_id', 'config_sha', 'config_blob_sha', 'config_path', 'config_sha256']
    pair = {key: receipt[key] for key in fields if key in receipt}
    return hashlib.sha256(json.dumps(pair, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def installation_state(value, receipt=None):
    require(isinstance(value, dict) and value.keys() == {'schemaVersion', 'stage', 'pairSha256'}
            and type(value['schemaVersion']) is int and value['schemaVersion'] == 1
            and value['stage'] in ['fresh-incomplete', 'ready']
            and isinstance(value['pairSha256'], str) and DIGEST.fullmatch(value['pairSha256']),
            'INSTALLATION_STATE_UNPROVEN')
    if value['stage'] == 'fresh-incomplete':
        require(receipt is not None and value['pairSha256'] == pair_digest(receipt),
                'INCOMPLETE_FRESH_GIT_PAIR_CHANGED')
    return value


def plan(report, target, target_contract, *, root, repository, legacy=legacy_strategy, receipt=None):
    require(REVISION.fullmatch(target or ''), 'TARGET_INVALID')
    target_contract = contract(target_contract)
    require(target_contract['epoch'] == 1 and CAPABILITIES <= set(target_contract['capabilities']),
            'TARGET_CONTRACT_UNSUPPORTED')
    require(isinstance(report, dict) and isinstance(report.get('blockers'), list), 'INVENTORY_UNPROVEN')
    if report['blockers']:
        # A blocker string proves neither containment nor a safe recovery. Exact
        # existing classifiers must supply continuation proof before it can run.
        retained = any('recovery' in item for item in report['blockers'])
        raise ValueError('RELAY_INSTALL_' + ('RECOVERY_REQUIRES_DIAGNOSIS' if retained else 'TARGET_UNSAFE'))
    installed = report.get('installed', {})
    if installed.get('status') == 'missing':
        return {'strategy': 'fresh', 'phase': 'bootstrap', 'installed': 'none'}
    require(installed.get('status') == 'present' and REVISION.fullmatch(installed.get('revision', '')),
            'INSTALLED_IDENTITY_UNPROVEN')
    previous = installed['revision']
    metadata = installed.get('deploymentContract')
    if metadata is not None:
        metadata = contract(metadata)
        require(metadata['epoch'] <= target_contract['epoch'], 'TRANSITION_UNSUPPORTED')
    pending = installed.get('installationState')
    if pending is not None:
        pending = installation_state(pending, receipt)
        if pending['stage'] == 'fresh-incomplete':
            require(previous == target, 'INCOMPLETE_FRESH_PRODUCT_CHANGED')
            return {'strategy': 'fresh-continuation', 'phase': 'apply', 'installed': previous}
    if previous == target:
        return {'strategy': 'reconcile', 'phase': 'apply', 'installed': previous}
    if metadata is None:
        strategy = legacy(root, repository, previous)
    else:
        strategy = ('upgrade' if metadata['epoch'] == target_contract['epoch']
                    and 'lifecycle-v1' in metadata['capabilities'] else 'reinstall')
    require(strategy in ['upgrade', 'reinstall'], 'TRANSITION_UNSUPPORTED')
    return {'strategy': strategy, 'phase': strategy, 'installed': previous}


def _receipt(args, config, root, identity, config_raw):
    receipt = getattr(args, 'git_intent', None)
    path = getattr(args, 'git_config_receipt', None)
    if path is not None:
        require(receipt is None and os.geteuid() == 0, 'RECEIPT_INTERFACE_INVALID')
        from installed_config import read_protected
        raw, _ = read_protected(Path(path), {0o600}, group=0)
        receipt = json.loads(raw, object_pairs_hook=unique_object)
    raw = config_raw
    raw_digest = hashlib.sha256(raw).hexdigest()
    if receipt is None:
        # Ordinary consumers may still supply their existing owner-held file.
        # The private Git rule applies when that installation selected Git mode.
        if config['environment']['localApply'].get('source') != 'git':
            return {'source': 'owner-file', 'config_sha256': raw_digest,
                    'product_repository': source_repository(config), 'product_sha': identity['revision']}
        config_root = Path(_git(args.config.parent, 'rev-parse', '--show-toplevel')).resolve()
        require(not _git(config_root, 'status', '--porcelain', '--untracked-files=all'), 'CONFIG_CHECKOUT_DIRTY')
        config_head = _git(config_root, 'rev-parse', 'HEAD^{commit}')
        require(REVISION.fullmatch(config_head), 'CONFIG_COMMIT_INVALID')
        relative = args.config.resolve().relative_to(config_root).as_posix()
        policy = config['environment']['localApply']
        require(relative == policy['configPath'], 'CONFIG_PATH_MISMATCH')
        origin = _git(config_root, 'remote', 'get-url', 'origin')
        expected = policy['repository']
        require(origin in ['https://github.com/' + expected + '.git', 'https://github.com/' + expected,
                           'git@github.com:' + expected + '.git'], 'CONFIG_ORIGIN_MISMATCH')
        remote = _git(config_root, 'ls-remote', '--exit-code', 'origin', 'refs/heads/main').split()
        require(remote == [config_head, 'refs/heads/main'], 'CONFIG_ACCEPTED_MAIN_MISMATCH')
        product_main = _git(root, 'ls-remote', '--exit-code', config['source']['repository'], 'refs/heads/main').split()
        require(product_main == [identity['revision'], 'refs/heads/main'], 'PRODUCT_ACCEPTED_MAIN_MISMATCH')
        blob = _git(config_root, 'rev-parse', config_head + ':' + relative)
        committed = subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false',
            '-C', str(config_root), 'cat-file', 'blob', config_head + ':' + relative],
            capture_output=True, check=True, timeout=30).stdout
        require(committed == raw and REVISION.fullmatch(blob), 'CONFIG_COMMIT_BYTES_MISMATCH')
        receipt = {'source': 'owner-checkout', 'config_repository': expected, 'config_sha': config_head,
                   'config_blob_sha': blob, 'config_path': relative, 'config_sha256': raw_digest,
                   'product_repository': source_repository(config), 'product_sha': identity['revision'],
                   'source_policy': 'accepted-main'}
    fields = {'source', 'config_repository', 'config_repository_id', 'config_sha', 'config_blob_sha',
              'config_path', 'config_sha256', 'product_repository', 'product_repository_id',
              'product_sha', 'workflow_run_id', 'action', 'source_policy'}
    require(isinstance(receipt, dict) and set(receipt) <= fields
            and receipt.get('product_sha') == identity['revision']
            and receipt.get('product_repository') == source_repository(config)
            and receipt.get('config_sha256') == raw_digest
            and receipt.get('source_policy') in ['accepted-main', 'accepted-ancestor', 'test-qualified-exact']
            and REVISION.fullmatch(receipt.get('config_sha', ''))
            and REVISION.fullmatch(receipt.get('config_blob_sha', ''))
            and REPOSITORY.fullmatch(receipt.get('config_repository', ''))
            and isinstance(receipt.get('config_path'), str)
            and not receipt['config_path'].startswith('/')
            and all(part not in ['', '.', '..'] for part in receipt['config_path'].split('/')),
            'GIT_PAIR_BINDING_INVALID')
    policy = config['environment']['localApply']
    if policy.get('source') == 'git':
        require(receipt['config_repository'] == policy['repository']
                and receipt['config_path'] == policy['configPath'], 'GIT_POLICY_BINDING_INVALID')
    return receipt


class ExternalPrerequisite(ValueError):
    def __init__(self, code, next_action):
        super().__init__('RELAY_INSTALL_EXTERNAL_' + code)
        self.next_action = next_action


def automatic_requested(config):
    environment = config['environment']
    return (environment.get('instance', {}).get('publicationEnabled', True)
            or environment['codexTokenRequired'] or bool(environment.get('codexCredential')))


def fresh_completion(config, report, args):
    """Compose existing expert phases from observed prerequisites, not secrets."""
    state = {item['name']: item['status'] for item in report.get('protectedState', [])}
    environment = config['environment']
    phases = []
    for name in ['runner_registration_token', 'general_runner_registration_token']:
        token = getattr(args, name, None)
        require(token is None or (isinstance(token, str) and 0 < len(token) <= 4096
                and all(33 <= ord(character) <= 126 for character in token)), 'REGISTRATION_TOKEN_INVALID')
    publication = environment.get('instance', {}).get('publicationEnabled', True)
    automatic = automatic_requested(config)
    # The existing automatic-runner readiness contract requires a Codex token
    # even when codexTokenRequired=false permits an inactive initial bootstrap.
    for role, required in [('reviewer', True), ('writer', publication), ('codex', automatic)]:
        if not required:
            continue
        installed = role + ('-installed-token' if role == 'codex' else '-installed-key')
        if state.get(installed) == 'reusable-metadata':
            continue
        reference = environment.get(role + 'Credential')
        if reference and state.get(role + '-source') == 'reusable-metadata':
            phases.append((role + '-credentials', 'primary'))
        elif required or reference:
            raise ExternalPrerequisite(role.upper() + '_CREDENTIAL_REQUIRED',
                'Provide the configured protected ' + role + ' credential source or a qualified installed credential, '
                'then use the same ordinary install command.')
    ca_ready = state.get('openai-client-ca') == 'reusable-metadata'
    tls_ready = all(state.get('tls-' + key) == 'reusable-metadata'
                    for key in ['certificateFile', 'privateKeyFile'])
    acme = bool(environment.get('tls', {}).get('acme'))
    if not tls_ready and not acme:
        raise ExternalPrerequisite('TLS_CERTIFICATE_REQUIRED',
            'Provide the configured protected TLS certificate and key, or configure the supported ACME prerequisites; '
            'then use the same ordinary install command.')
    if not ca_ready:
        phases.append(('tls-prepare', 'primary'))
    if not tls_ready and acme:
        phases.extend([('tls-dry-run', 'primary'), ('tls-issue', 'primary')])
    phases.append(('tls-check', 'primary'))
    if environment['reviewerBind']['mode'] == 'docker_gateway':
        phases.append(('ingress', 'primary'))
    phases.append(('activate', 'primary'))
    runners = report.get('runners', {})
    specifications = [('production', 'runner-register', 'runner_registration_token', 'primary')] if automatic else []
    if automatic and 'generalRunnerPool' not in config['consumer']:
        specifications += [('general', 'general-runner-register', 'general_runner_registration_token', 'primary')]
        specifications += [('slot-' + slot['id'], 'general-runner-register',
                            'general_runner_registration_token', slot['id'])
                           for slot in config['consumer'].get('executionSlots', [])[1:]]
    for name, phase, token, slot in specifications:
        row = runners.get(name, {})
        require(row.get('status') in ['missing', 'reusable'], 'RUNNER_REGISTRATION_STATE_UNPROVEN')
        if row.get('status') != 'reusable' and not getattr(args, token, None):
            raise ExternalPrerequisite(name.upper().replace('-', '_') + '_RUNNER_REGISTRATION_REQUIRED',
                'Provide the matching optional ephemeral runner registration token with qualified repository/group '
                'access, or restore the intended reusable registration; then use the same ordinary install command.')
        phases.append((phase, slot))
        if name == 'production':
            phases.append(('runner-enable', slot))
        else:
            phases.append(('general-runner-enable', slot))
    return phases


def phase_arguments(args, phase, receipt, consumer, expected, guard, pool_guard, *, fresh=False, slot='primary'):
    inner = argparse.Namespace(**vars(args))
    for key in list(vars(inner)):
        if key.startswith('authorize_'):
            setattr(inner, key, False)
    authorizations = {'bootstrap': 'bootstrap', 'reinstall': 'reinstall', 'upgrade': 'upgrade',
        'activate': 'reviewer_activation', 'runner-register': 'runner_register',
        'general-runner-register': 'general_runner_register', 'runner-enable': 'runner_enable',
        'general-runner-enable': 'general_runner_enable', **{name: name.replace('-', '_') for name in [
            'reviewer-credentials', 'writer-credentials', 'codex-credentials',
            'tls-prepare', 'tls-dry-run', 'tls-issue', 'ingress']}}
    for name in set(authorizations.values()):
        setattr(inner, 'authorize_' + name, False)
    if phase in authorizations:
        setattr(inner, 'authorize_' + authorizations[phase], True)
    inner.phase, inner.intent_install = phase, True
    inner.intent_expected_installed_revision = expected
    inner.git_intent, inner.git_config_receipt = copy.deepcopy(receipt), None
    inner.consumer_root, inner.projection_output = Path(consumer), None
    inner.execution_slot = slot
    inner.runner_registration_token = inner.general_runner_registration_token = None
    inner._intent_host_guard, inner._intent_pool_guard = guard, pool_guard
    inner._intent_fresh_bootstrap = fresh and phase == 'bootstrap'
    inner._intent_defer_pool_reconcile = fresh and 'generalRunnerPool' in getattr(args, '_intent_consumer', {})
    return inner


def hold_install_guard(target, key, namespace, root):
    """Use the same existing kernel mutex as the expert apply primitive."""
    from ansible_transport import hold_target
    source = (Path(root) / 'deploy/deployment_lock.py').read_text()
    return hold_target(target, key, ['/usr/bin/python3', '-I', '-c', source,
                                   '/var/lib/' + namespace + '-deployment.lock'], 'DEPLOYMENT_LOCK_READY')


def release_guard(guard):
    guard.stdin.close()
    require(guard.wait(timeout=30) == 0, 'HOST_LOCK_RELEASE_UNPROVEN')


def readback(report, revision, receipt, *, same_pair_only=False):
    installed = report['installed']
    require(not report.get('blockers') and installed.get('status') == 'present'
            and installed.get('revision') == revision
            and (same_pair_only or report['configuration'].get('status') == 'equivalent'), 'READBACK_UNPROVEN')
    actual = installed.get('gitConfigReceipt')
    require((isinstance(actual, dict) and pair_digest(actual) == pair_digest(receipt))
            if same_pair_only else actual == receipt, 'GIT_PAIR_READBACK_UNPROVEN')


def finalize_fresh_manifest(payload, *, root=Path('/'), owner_uid=0):
    """Mark only this exact pending pair ready after the final qualification.

    All other attestation fields and file ownership/mode are retained. Fixture
    roots/UIDs are Python-only seams; the target transport always uses root /.
    """
    def protect(path, directory=False):
        current, first = path, True
        while True:
            info = current.lstat()
            kind = stat.S_ISDIR if directory or not first else stat.S_ISREG
            require(current.is_relative_to(root) and info.st_uid == owner_uid
                    and kind(info.st_mode) and not info.st_mode & 0o022
                    and (not first or directory or info.st_nlink == 1), 'FINAL_MANIFEST_UNSAFE')
            if current == root:
                break
            current, first = current.parent, False
    def stamp(info):
        return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode,
                info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    def read(path, modes):
        protect(path)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            require(stat.S_IMODE(before.st_mode) in modes and before.st_size <= 65536,
                    'FINAL_MANIFEST_UNSAFE')
            raw = stream.read(65537)
            require(len(raw) <= 65536 and stamp(before) == stamp(os.fstat(stream.fileno()))
                    and stamp(before) == stamp(path.lstat()), 'FINAL_MANIFEST_CHANGED')
        return json.loads(raw, object_pairs_hook=unique_object), raw, before
    namespace, revision = payload['namespace'], payload['revision']
    require(re.fullmatch('[a-z][a-z0-9-]{0,30}', namespace)
            and REVISION.fullmatch(revision), 'FINAL_MANIFEST_BINDING_INVALID')
    install = root / 'opt' / namespace
    protect(install, True)
    current = install / 'current'
    link = current.lstat()
    require(stat.S_ISLNK(link.st_mode) and link.st_uid == owner_uid,
            'FINAL_MANIFEST_BINDING_INVALID')
    release = install / 'releases' / revision
    require(current.resolve(strict=True) == release, 'FINAL_MANIFEST_BINDING_INVALID')
    manifest, _, metadata = read(release / 'artifact-manifest.json', {0o600, 0o640, 0o644})
    source, _, _ = read(release / 'reviewed-source/.relay-source.json', {0o644, 0o640})
    _, snapshot, _ = read(release / 'deployment-config.json', {0o600})
    require(all(manifest.get(key) == revision for key in ['commit', 'installedRevision', 'resolvedRevision'])
            and source.get('revision') == revision and source.get('tree') == manifest.get('gitTree')
            and REVISION.fullmatch(manifest.get('gitTree', ''))
            and manifest.get('gitConfigReceipt') == payload['receipt']
            and manifest.get('deploymentConfigSha256') == hashlib.sha256(snapshot).hexdigest()
            == payload['deploymentConfigSha256'], 'FINAL_MANIFEST_BINDING_INVALID')
    state = installation_state(manifest.get('installationState'), payload['receipt'])
    require(state['pairSha256'] == pair_digest(payload['receipt']), 'FINAL_MANIFEST_BINDING_INVALID')
    if state['stage'] == 'ready':
        return state
    ready = {**state, 'stage': 'ready'}
    manifest['installationState'] = ready
    temporary = None
    directory = os.open(release, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        descriptor, temporary = tempfile.mkstemp(prefix='.fresh-ready-', dir=release)
        with os.fdopen(descriptor, 'w') as stream:
            os.fchown(stream.fileno(), metadata.st_uid, metadata.st_gid)
            os.fchmod(stream.fileno(), stat.S_IMODE(metadata.st_mode))
            json.dump(manifest, stream, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        require(stamp(os.stat('artifact-manifest.json', dir_fd=directory, follow_symlinks=False)) == stamp(metadata)
                and stamp(current.lstat()) == stamp(link) and current.resolve(strict=True) == release,
                'FINAL_MANIFEST_CHANGED')
        os.replace(Path(temporary).name, 'artifact-manifest.json', src_dir_fd=directory, dst_dir_fd=directory)
        temporary = None
        os.fsync(directory)
        return ready
    finally:
        if temporary is not None:
            Path(temporary).unlink()
        os.close(directory)


def complete_fresh(target, key, config, revision, receipt, guard, pool_guard):
    require(guard.poll() is None and (pool_guard is None or pool_guard.poll() is None), 'HOST_LOCK_LOST')
    from ansible_transport import run_target
    program = ('import hashlib,json,os,re,stat,sys,tempfile\nfrom pathlib import Path\n'
               'REVISION=re.compile(r"[0-9a-f]{40}");DIGEST=re.compile(r"[0-9a-f]{64}")\n')
    for helper in [require, unique_object, pair_digest, installation_state, finalize_fresh_manifest]:
        program += inspect.getsource(helper) + '\n'
    program += ('try:\n print(json.dumps(finalize_fresh_manifest(json.load(sys.stdin))))\n'
                'except Exception:\n print("RELAY_INSTALL_FINAL_MANIFEST_UNPROVEN",file=sys.stderr);sys.exit(1)\n')
    canonical = (json.dumps(config, sort_keys=True, separators=(',', ':'), ensure_ascii=False) + '\n').encode()
    payload = {'namespace': config['environment']['namespace'], 'revision': revision, 'receipt': receipt,
               'deploymentConfigSha256': hashlib.sha256(canonical).hexdigest()}
    result = run_target(target, key, ['/usr/bin/python3', '-I', '-c', program],
                        input=json.dumps(payload), timeout=60)
    require(result.returncode == 0 and guard.poll() is None
            and (pool_guard is None or pool_guard.poll() is None), 'FINAL_MANIFEST_UNPROVEN')
    ready = installation_state(json.loads(result.stdout), receipt)
    require(ready['stage'] == 'ready' and ready['pairSha256'] == pair_digest(receipt), 'FINAL_MANIFEST_UNPROVEN')
    return ready


def run(args, primitive, root, identity, *, guard_factory=None):
    require(os.sys.platform == 'linux', 'LINUX_CONTROLLER_REQUIRED')
    require(args.resolved_revision == identity['revision'], 'EXACT_PRODUCT_TARGET_REQUIRED')
    require(not any(getattr(args, key, False) for key in vars(args) if key.startswith('authorize_')),
            'EXPERT_AUTHORIZATION_FLAGS_INVALID')
    root = Path(root)
    args.config = args.config.absolute()
    stage, selected, mutation = 'desired-inputs', {'strategy': 'unresolved', 'installed': 'unavailable'}, False
    inner = None
    try:
        config_raw = args.config.read_bytes()
        config = loads(config_raw.decode('utf-8'), root)
        if 'generalRunnerPool' in config['consumer']:
            config = loads(json.dumps(config, sort_keys=True, separators=(',', ':'), ensure_ascii=False), root)
        receipt = _receipt(args, config, root, identity, config_raw)
        target_contract = contract(json.loads((root / 'deploy/installation-contract.json').read_text(),
                                             object_pairs_hook=unique_object))
        target = dict(config['target'])
        if getattr(args, 'connection', None) is not None:
            target['connection'] = args.connection
        key = Path(target.get('identityFile', '/unused-local-identity')).expanduser()
        stage = 'target-inventory'
        qualify_identity(target, key)
        from inventory import remote_inventory
        report = remote_inventory(target, key, config, git_desired=True)
        selected = plan(report, identity['revision'], target_contract, root=root,
                        repository=source_repository(config), receipt=receipt)
        fresh = selected['strategy'] in ['fresh', 'fresh-continuation']
        completion = fresh_completion(config, report, args) if fresh else []
        pending = {'schemaVersion': 1, 'stage': 'fresh-incomplete', 'pairSha256': pair_digest(receipt)}
        retained_state = report.get('installed', {}).get('installationState', {})
        if retained_state.get('stage') != 'ready' or retained_state.get('pairSha256') != pair_digest(receipt):
            retained_state = {}
        print('RELAY_INSTALL_PLAN=' + json.dumps({**selected, 'target': identity['revision'],
            'config': receipt.get('config_sha', receipt['config_sha256'])}, sort_keys=True), flush=True)
        stage = 'repository-integration'
        consumer = args.consumer_root or Path(_git(args.config.parent, 'rev-parse', '--show-toplevel'))
        from workflow_projection import integration
        output = args.projection_output or (args.log_root / ('integration-' + identity['revision'] + '-'
            + receipt['config_sha256'][:16]))
        artifact = integration(config, identity['revision'], root, consumer, output)
        factory = guard_factory or (lambda target, key, namespace: hold_install_guard(target, key, namespace, root))
        runner_token = getattr(args, 'runner_registration_token', None)
        general_token = getattr(args, 'general_runner_registration_token', None)
        args.runner_registration_token = args.general_runner_registration_token = None
        args._intent_consumer = config['consumer']
        with ExitStack() as locks:
            stage = 'host-lock'
            guard = factory(target, key, config['environment']['namespace'])
            locks.callback(release_guard, guard)
            pool_guard = None
            if 'generalRunnerPool' in config['consumer']:
                pool_guard = factory(target, key, 'codex-relay-pool-' + config['environment']['generalRunner']['name'])
                locks.callback(release_guard, pool_guard)
            expected = selected['installed']
            receipt_applied = selected['strategy'] != 'fresh-continuation'
            schedule = [(selected['phase'], 'primary')]
            if completion:
                # The inactive first pass installs the exact manifest needed by
                # bounded credential staging. The second pass enforces full
                # token/slot readiness without changing frozen desired bytes.
                credentials = [item for item in completion if item[0].endswith('-credentials')]
                schedule = ([('bootstrap', 'primary')] if selected['strategy'] == 'fresh' else [])
                schedule += credentials + [('apply', 'primary')]
                schedule += [item for item in completion if not item[0].endswith('-credentials')]
                if automatic_requested(config) and 'generalRunnerPool' in config['consumer']:
                    schedule.append(('managed-pool', 'primary'))
                schedule.append(('post-check', 'primary'))
            for phase, slot in schedule:
                stage = ('fresh-' if completion else '') + phase
                require(guard.poll() is None and (pool_guard is None or pool_guard.poll() is None), 'HOST_LOCK_LOST')
                require(args.config.read_bytes() == config_raw, 'CONFIG_BYTES_CHANGED')
                inner = phase_arguments(args, phase, receipt, consumer, expected, guard, pool_guard,
                                        fresh=bool(completion), slot=slot)
                inner._intent_installation_state = pending if fresh else retained_state
                if phase == 'runner-register' and report.get('runners', {}).get('production', {}).get('status') != 'reusable':
                    inner.runner_registration_token = runner_token
                if phase == 'general-runner-register':
                    name = 'general' if slot == 'primary' else 'slot-' + slot
                    if report.get('runners', {}).get(name, {}).get('status') != 'reusable':
                        inner.general_runner_registration_token = general_token
                try:
                    if phase == 'managed-pool':
                        from managed_pool_transport import reconcile_pool
                        mutation = True
                        proof = reconcile_pool(target, key, config, identity['revision'], guard,
                            local=target.get('connection') == 'local', extra_guard=pool_guard)
                        print(proof, flush=True)
                    else:
                        primitive(inner)
                finally:
                    mutation = mutation or getattr(inner, '_intent_mutation_started', False)
                    inner.runner_registration_token = inner.general_runner_registration_token = None
                require(guard.poll() is None and (pool_guard is None or pool_guard.poll() is None), 'HOST_LOCK_LOST')
                stage = 'installed-readback'
                observed = remote_inventory(target, key, config, git_desired=True)
                if phase in ['bootstrap', 'apply']:
                    receipt_applied = True
                readback(observed, identity['revision'], receipt, same_pair_only=not receipt_applied)
                if fresh:
                    require(observed['installed'].get('installationState') == pending,
                            'FRESH_PENDING_MARKER_UNPROVEN')
                expected = identity['revision']
            if fresh:
                stage = 'fresh-completion'
                ready = complete_fresh(target, key, config, identity['revision'], receipt, guard, pool_guard)
                observed = remote_inventory(target, key, config, git_desired=True)
                readback(observed, identity['revision'], receipt)
                require(observed['installed'].get('installationState') == ready, 'FRESH_READY_MARKER_UNPROVEN')
        print('RELAY_INSTALL_RESULT=' + json.dumps({'status': 'PASS', 'strategy': selected['strategy'],
            'product': identity['revision'], 'config': receipt.get('config_sha', receipt['config_sha256']),
            'readiness': ('reviewer-and-automatic' if automatic_requested(config) else 'reviewer-only')
                         if fresh else 'preserved-existing',
            'integration': artifact, 'next': 'Publish the generated directory contents through the consumer repository normal change process; no installer rerun is required.'},
            sort_keys=True), flush=True)
    except Exception as error:
        mutation = mutation or (inner is not None and getattr(inner, '_intent_mutation_started', False))
        code = str(error).split(';')[0] if isinstance(error, (ValueError, RuntimeError)) else type(error).__name__
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_:-]{0,160}', code):
            code = type(error).__name__
        failure = {'status': 'FAIL', 'target': identity['revision'], 'installed': selected['installed'],
            'strategy': selected['strategy'], 'stage': stage, 'cause': code,
            'hostMutation': 'unknown' if mutation else False,
            'recovery': 'retained-state-requires-diagnosis' if mutation else 'not-started',
            'automaticRetrySafe': False, 'next': getattr(error, 'next_action',
                'Inspect the reported prerequisite or retained operation evidence before retrying.')}
        if inner is not None and getattr(inner, '_intent_log_path', None):
            failure['log'] = inner._intent_log_path
        print('RELAY_INSTALL_FAILURE=' + json.dumps(failure, sort_keys=True), flush=True)
        raise RuntimeError('RELAY_INSTALL_FAILED;stage=' + stage + ';cause=' + code) from None
