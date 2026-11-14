"""Bounded source-only promotion inside the ordinary guarded installer.

The sole private receipt lives in the existing operation stage. Desired bytes
come from canonical templates; observed host bytes never become desired state.
"""
import base64
import copy
import ctypes
import errno
import fcntl
import grp
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
import uuid

sys.dont_write_bytecode = True
# -B suppresses writes, but SourceLoader still reads a valid existing cache.
# A character-device prefix cannot contain any cached module path; standard
# import and spec loaders therefore compile the protected source bytes.
if __name__ == '__main__':
    _null = os.lstat('/dev/null')
    if not stat.S_ISCHR(_null.st_mode) or _null.st_uid != 0 or _null.st_rdev != os.makedev(1, 3):
        raise RuntimeError('SOURCE_UPGRADE_CACHE_PREFIX_UNSAFE')
    sys.pycache_prefix = '/dev/null'


MAX_INPUT = 64 * 1024 * 1024


def require(value, code='SOURCE_UPGRADE_UNPROVEN'):
    if not value:
        raise RuntimeError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def stage_helper(source):
    path = Path(source) / 'deploy/ansible/roles/relay_artifacts/files/relay-intent-stage.py'
    spec = importlib.util.spec_from_file_location('relay_source_stage', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_package_modes(receipt):
    """Keep installed reuse explicit; never impersonate an acquired package.

    Actual live-tree and recipe equivalence belongs to the source-upgrade
    verifier, under its original current binding. This validates only the
    sealed evidence shape, leaving existing staged receipts unchanged.
    """
    packages = receipt.get('packages')
    if not isinstance(packages, dict):
        require(False, 'SOURCE_UPGRADE_PACKAGE_RECEIPT_INVALID')
    reuse = any(isinstance(value, dict) and 'mode' in value for value in packages.values())
    require(reuse, 'SOURCE_UPGRADE_PACKAGE_RECEIPT_INVALID')
    require(set(packages) == {'runner', 'codex'}, 'SOURCE_UPGRADE_PACKAGE_RECEIPT_INVALID')
    previous = set()
    for kind, value in packages.items():
        require(isinstance(value, dict)
                and set(value) == {'mode', 'kind', 'sourceRevision', 'recipeSha256', 'treeSha256'}
                and value['mode'] == 'installed-reuse' and value['kind'] == kind
                and isinstance(value['sourceRevision'], str)
                and re.fullmatch('[a-f0-9]{40}', value['sourceRevision'])
                and all(isinstance(value[key], str) and re.fullmatch('[a-f0-9]{64}', value[key])
                        for key in ['recipeSha256', 'treeSha256']), 'SOURCE_UPGRADE_PACKAGE_RECEIPT_INVALID')
        previous.add(value['sourceRevision'])
    require(len(previous) == 1 and receipt['sourceIdentity']['revision'] not in previous,
            'SOURCE_UPGRADE_PACKAGE_RECEIPT_INVALID')
    require(not receipt['toolchain']['stagedPrefix'], 'SOURCE_UPGRADE_REUSE_TOOLCHAIN_INVALID')


def artifact_values(values, manifest):
    result = dict(values)
    result.update(relay_deployment_profile='production', relay_release_commit=manifest['commit'],
                  relay_release_sha256=manifest['releaseSourceTreeSha256'],
                  relay_release_path=values['relay_release_root'] + '/' + manifest['commit'],
                  relay_controller_source_tree_sha256=manifest['controllerSourceTreeSha256'],
                  relay_codex_launcher_source_tree_sha256=manifest['codexLauncherSourceTreeSha256'],
                  relay_consumer_revision=manifest['consumerRevision'],
                  relay_production_operation_target_head=manifest['commit'])
    result['relay_github_repositories'] = result['relay_writer_repositories']
    return result


def desired_manifest(values, identity, previous):
    manifest = copy.deepcopy(previous)
    revision = identity['revision']
    manifest.update(requestedRevision=values['relay_requested_revision'], resolvedRevision=revision,
                    installedRevision=revision, gitTree=identity['tree'], commit=revision,
                    previousRevision=previous['commit'], consumerRevision=values['relay_consumer_revision'],
                    releaseSourceTreeSha256=identity['sourceTreeSha256'],
                    deploymentConfigSha256=hashlib.sha256(values['relay_installed_deployment_config'].encode()).hexdigest(),
                    gitConfigReceipt=values['relay_git_config_receipt'],
                    deploymentContract=values['relay_deployment_contract'],
                    reviewerArtifactProvenance='verified-reuse',
                    reviewerReuseSourceRelease=values['relay_release_root'] + '/' + previous['commit'],
                    reviewerReuseSourceBinarySha256=previous['reviewerBinarySha256'])
    for key in ['controllerSourceTreeSha256', 'codexLauncherSourceTreeSha256',
                'reviewerSourceTreeSha256', 'reviewerBuildInputsTreeSha256']:
        manifest[key] = identity[key]
    # Ordinary upgrades do not invent a first-install readiness marker.
    manifest.pop('installationState', None)
    return manifest


def catalogue_transition(before, after, old_manifest, new_manifest, config_root, release_root):
    """Permit only canonical artifact provenance in the two owning JSON files."""
    from installed_state import NotEligible
    old, new = copy.deepcopy(before), copy.deepcopy(after)
    if set(old) != set(new):
        raise NotEligible('SOURCE_UPGRADE_CATALOGUE_CHANGED')
    old_entries, new_entries = old.pop('entries'), new.pop('entries')
    if old != new or len(old_entries) != len(new_entries):
        raise NotEligible('SOURCE_UPGRADE_CATALOGUE_CHANGED')
    changes = []
    for index, (left, right) in enumerate(zip(old_entries, new_entries)):
        if left == right:
            continue
        old_prefix = Path(release_root) / old_manifest['commit']
        new_prefix = Path(release_root) / new_manifest['commit']
        if Path(left['path']).is_relative_to(old_prefix) and Path(right['path']).is_relative_to(new_prefix):
            old_entry, new_entry = dict(left), dict(right)
            old_entry['path'] = str(Path(left['path']).relative_to(old_prefix))
            new_entry['path'] = str(Path(right['path']).relative_to(new_prefix))
            if old_entry != new_entry:
                raise NotEligible('SOURCE_UPGRADE_CATALOGUE_CHANGED')
            changes.append(right)
            continue
        left_meta, right_meta = dict(left), dict(right)
        for value in [left_meta, right_meta]:
            value.pop('contentBase64', None)
            value.pop('sha256', None)
        # This existing wrapper intentionally pins its absolute release. Its
        # sole allowed update follows the new source release; the fixed task
        # owner, all metadata and every other byte remain identical.
        owners = before.get('entryOwners', [[]] * len(old_entries))[index]
        diagnostics_owners = {'roles/relay_controller/tasks/runtime-entrypoints.yml:Install the fixed root-owned diagnostics store wrapper',
                              'tasks/execution-slot.yml:Install fixed credential-free slot dispatcher and diagnostic wrappers'}
        if (left_meta == right_meta and left.get('kind') == 'file' and bool(diagnostics_owners.intersection(owners))
                and Path(left['path']).name == 'relay-diagnostics-store'):
            old_raw = base64.b64decode(left['contentBase64'], validate=True)
            new_raw = base64.b64decode(right['contentBase64'], validate=True)
            old_path = str(old_prefix / 'bin/relay-diagnostics-store.mjs').encode()
            new_path = str(new_prefix / 'bin/relay-diagnostics-store.mjs').encode()
            if old_path in old_raw and old_raw.replace(old_path, new_path) == new_raw:
                changes.append(right)
                continue
        stale_owner = 'roles/relay_runtime/tasks/production-operation-stale-disposition.yml:Install the source-controlled stale-disposition helper'
        if left_meta == right_meta and left.get('kind') == 'file' and stale_owner in owners:
            old_raw = base64.b64decode(left['contentBase64'], validate=True)
            new_raw = base64.b64decode(right['contentBase64'], validate=True)
            old_line = ("superseding_head='" + old_manifest['commit'] + "'\n").encode()
            new_line = ("superseding_head='" + new_manifest['commit'] + "'\n").encode()
            bindings = [line for line in old_raw.splitlines(keepends=True)
                        if line.startswith(b'superseding_head=')]
            if (all(re.fullmatch('[a-f0-9]{40}', value) for value in
                    [old_manifest['commit'], new_manifest['commit']])
                    and bindings == [old_line] and old_raw.replace(old_line, new_line, 1) == new_raw):
                changes.append(right)
                continue
        if (left_meta != right_meta or left.get('kind') != 'file'
                or left['path'] not in [str(Path(config_root) / name) for name in ['reviewer-mcp.json', 'controller.json']]):
            raise NotEligible('SOURCE_UPGRADE_CATALOGUE_CHANGED')
        a, b = [json.loads(base64.b64decode(value['contentBase64'], validate=True)) for value in [left, right]]
        if (a.pop('artifact', None) != {'commit': old_manifest['commit'], 'sha256': old_manifest['releaseSourceTreeSha256']}
                or b.pop('artifact', None) != {'commit': new_manifest['commit'], 'sha256': new_manifest['releaseSourceTreeSha256']}
                or a != b):
            raise NotEligible('SOURCE_UPGRADE_CATALOGUE_CHANGED')
        changes.append(right)
    return changes


def guards(guard, pool_guard):
    require(guard is not None and guard.poll() is None, 'HOST_LOCK_LOST')
    require(pool_guard is not None and pool_guard.poll() is None, 'POOL_LOCK_LOST')


def invoke(preparation, action, **extra):
    return preparation.execute(['/usr/bin/python3', '-I', preparation.source + '/deploy/source_upgrade.py', action],
        payload={'values': preparation.values, 'identity': preparation.identity,
                 'operationId': preparation.operation, 'stage': preparation.stage,
                 'sourceRoot': preparation.source, **extra}, timeout=180)


def prepare(preparation, config, guard, pool_guard):
    from installed_state import NotEligible, build_catalogue
    from source_upgrade_proof import resolve_values
    guards(guard, pool_guard)
    try:
        preparation.values.update(resolve_values(preparation.values, Path(__file__).resolve().parents[1]))
    except NotEligible:
        return False
    preparation.values['relay_source_reuse_consumer_digest'] = preparation.desired_digest
    context = invoke(preparation, 'describe', config=config)
    guards(guard, pool_guard)
    if context.get('eligible') is False:
        return False
    preparation.values.update({key: value for key, value in context['oldValues'].items()
                               if key not in preparation.values})
    # These are validated host observations from the owning gateway predicate,
    # not desired configuration choices or unproved template register facts.
    for key in ['relay_reviewer_bind_address', 'relay_reviewer_bind_network',
                'relay_reviewer_gateway_validated', 'relay_docker_nginx_reviewer_upstream']:
        if key in context['oldValues']:
            preparation.values[key] = context['oldValues'][key]
    manifest = desired_manifest(preparation.values, preparation.identity, context['manifest'])
    source = Path(__file__).resolve().parents[1]
    try:
        before = build_catalogue(source, artifact_values(context['oldValues'], context['manifest']))
        after = build_catalogue(source, artifact_values(preparation.values, manifest))
        changes = catalogue_transition(before, after, context['manifest'], manifest, preparation.values['relay_config_root'], preparation.values['relay_release_root'])
    except NotEligible:
        return False
    result = invoke(preparation, 'prepare', config=config, context=context,
                    catalogueBefore=before, catalogueAfter=after, changes=changes, manifest=manifest)
    guards(guard, pool_guard)
    if result.get('eligible') is False:
        return False
    require(result.get('status') == 'SOURCE_STAGE_READY', 'SOURCE_UPGRADE_PREPARATION_UNPROVEN')
    preparation.host_observation = result['host']
    return True


def verify(preparation, *, final=False):
    result = invoke(preparation, 'verify', final=final)
    require(result.get('status') == 'SOURCE_STAGE_READY', 'SOURCE_UPGRADE_VERIFICATION_UNPROVEN')
    return result['receipt']


def promote(preparation, config, guard, pool_guard):
    guards(guard, pool_guard)
    result = guarded_promote(preparation, config, [guard, pool_guard, preparation.holder])
    guards(guard, pool_guard)
    require(result.get('status') == 'SOURCE_UPGRADE_READY'
            and result.get('revision') == preparation.identity['revision'], 'SOURCE_UPGRADE_PROMOTION_UNPROVEN')
    return result


def guarded_promote(preparation, config, holders):
    """Keep the ordinary backend's live holder monitoring during cutover."""
    from ansible_transport import TargetProcess
    process = TargetProcess(preparation.target, preparation.key,
        ['/usr/bin/python3', '-I', preparation.source + '/deploy/source_upgrade.py', 'promote'],
        local=preparation.local)
    payload = {'values': preparation.values, 'identity': preparation.identity,
        'operationId': preparation.operation, 'stage': preparation.stage, 'sourceRoot': preparation.source,
        'config': config, 'admissionPrefix': preparation.admission_prefix(), 'lease': preparation.lease_path}
    def alive():
        require(all(holder is not None and holder.poll() is None for holder in holders),
                'SOURCE_UPGRADE_OPERATION_GUARD_LOST')
    try:
        alive()
        process.start(json.dumps(payload))
        deadline = time.monotonic() + 180
        while process.poll() is None:
            alive()
            require(time.monotonic() < deadline, 'SOURCE_UPGRADE_OPERATION_TIMEOUT')
            time.sleep(0.05)
        alive()
        output, _errors = process.communicate(timeout=10)
        require(process.returncode == 0, 'SOURCE_UPGRADE_PROMOTION_UNPROVEN')
        return json.loads(output)
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def read_journal(data, helper):
    root = helper.stage_root(data['stage'], data['operationId'])
    value = json.loads(helper.read_regular(root / 'source-upgrade.json', limit=MAX_INPUT))
    require(value['operationId'] == data['operationId'] and value['identity'] == data['identity']
            and value['stage'] == data['stage'], 'SOURCE_UPGRADE_BINDING_CHANGED')
    return value


def candidate_checks(root, repository):
    source = root / 'release/reviewed-source'
    imports = ['entrypoint.mjs', 'recover-attempt-publication.mjs', 'admission-cli.mjs',
               'manual-outcome.mjs', 'privileged-writer-helper.mjs', 'trusted-git.mjs']
    command = ['/usr/bin/node', '--input-type=module', '-e',
        'import {pathToFileURL} from "node:url"; for(const path of process.argv.slice(2)) await import(pathToFileURL(path)); console.log("INTENT_STAGE_IMPORTS_READY");',
        'stage-import', *[str(source / 'controller/src' / name) for name in imports]]
    environment = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'HOME': str(root),
                   'RELAY_CONSUMER_CONFIG': str(root / 'consumer.json'), 'RELAY_REPOSITORY': repository}
    result = subprocess.run(command, env=environment, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60)
    require(result.returncode == 0 and result.stdout.strip() == b'INTENT_STAGE_IMPORTS_READY',
            'SOURCE_UPGRADE_CANDIDATE_IMPORTS_UNPROVEN')
    result = subprocess.run([str(root / 'release/bin/reviewer-mcp-http'), '--help'],
        env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'HOME': str(root)},
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=30)
    require(result.returncode == 0 and b'Usage:' in result.stdout, 'SOURCE_UPGRADE_REVIEWER_LOADER_UNPROVEN')


def normalize_release(destination, values):
    """The fixed metadata assignments owned by artifact intent-consume.yml."""
    destination = Path(destination)
    relay_gid = grp.getgrnam(values.get('relay_group', values['relay_user'])).gr_gid
    reviewer_gid = grp.getgrnam(values.get('relay_reviewer_group', values['relay_reviewer_user'])).gr_gid
    runner_gid = grp.getgrnam(values.get('relay_runner_group', values['relay_runner_user'])).gr_gid
    for relative in ['', 'bin', 'reviewed-source']:
        path = destination / relative
        os.chown(path, 0, relay_gid)
        path.chmod(0o751)
    os.chown(destination / 'bin/reviewer-mcp-http', 0, reviewer_gid)
    (destination / 'bin/reviewer-mcp-http').chmod(0o750)
    for relative in ['reviewer-source', 'contracts']:
        for path in [destination / relative, *(destination / relative).rglob('*')]:
            os.chown(path, 0, relay_gid, follow_symlinks=False)
    os.chown(destination / 'artifact-manifest.json', 0, relay_gid)
    os.chown(destination / 'bin/relay-codex-dispatch.mjs', 0, runner_gid, follow_symlinks=False)


def release_move_plan(source, destination, helper):
    """Qualify no-replace rename before any live installation mutation.

    A disposable directory in the existing private stage tests filesystem/kernel
    support. Unsupported filesystems retain the frozen consumer; no rename
    failure after the original operation record ever retries another writer.
    """
    source, destination = Path(source), Path(destination)
    if sys.platform != 'linux' or os.path.lexists(destination):
        return None
    source_info = helper.protected(source, directory=True)
    parent_info = helper.protected(destination.parent, directory=True)
    if source_info.st_dev != parent_info.st_dev:
        return None
    try:
        rename = ctypes.CDLL(None, use_errno=True).renameat2
    except AttributeError:
        return None
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int

    def no_replace(left, right):
        if rename(-100, os.fsencode(left), -100, os.fsencode(right), 1) != 0:
            number = ctypes.get_errno()
            raise OSError(number, os.strerror(number))

    probe = source.parent / ('.rename-probe-' + str(uuid.uuid4()))
    moved = probe.with_name(probe.name + '-moved')
    probe.mkdir(mode=0o700)
    probe_identity = probe.stat()
    try:
        try:
            no_replace(probe, moved)
        except OSError as error:
            if error.errno in [errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP, errno.EXDEV]:
                return None
            raise
    finally:
        for path in [probe, moved]:
            if os.path.lexists(path):
                info = path.lstat()
                require(stat.S_ISDIR(info.st_mode) and (info.st_dev, info.st_ino)
                        == (probe_identity.st_dev, probe_identity.st_ino), 'SOURCE_UPGRADE_MOVE_PROBE_CHANGED')
                path.rmdir()

    def move():
        current = helper.protected(source, directory=True)
        parent = helper.protected(destination.parent, directory=True)
        require(helper.stamp(current) == helper.stamp(source_info)
                and (parent.st_dev, parent.st_ino) == (parent_info.st_dev, parent_info.st_ino)
                and not os.path.lexists(destination), 'SOURCE_UPGRADE_MOVE_BINDING_CHANGED')
        no_replace(source, destination)
        # The payload and reference receipts were already fsynced by their
        # owning writers. Commit removal and publication of the directory name.
        for path in [source.parent, destination.parent]:
            descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        observed = helper.protected(destination, directory=True)
        require((observed.st_dev, observed.st_ino) == (source_info.st_dev, source_info.st_ino),
                'SOURCE_UPGRADE_MOVE_BINDING_CHANGED')
    return move


def sync_release_directories(source, helper):
    """Persist sealed topology once, including directory and symlink entries.

    Every regular source/generated/artifact byte in this native stage was
    written by the frozen helper's atomic writer (which fsyncs its file FD).
    Ancestor directory links and aliases need this bottom-up directory pass.
    """
    def unavailable(error):
        raise error
    for directory, _, _ in os.walk(source, topdown=False, followlinks=False, onerror=unavailable):
        path = Path(directory)
        before = helper.protected(path, directory=True)
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            require(helper.stamp(os.fstat(descriptor)) == helper.stamp(before),
                    'SOURCE_UPGRADE_MOVE_DIRECTORY_CHANGED')
            os.fsync(descriptor)
            require(helper.stamp(os.fstat(descriptor)) == helper.stamp(before)
                    == helper.stamp(path.lstat()), 'SOURCE_UPGRADE_MOVE_DIRECTORY_CHANGED')
        finally:
            os.close(descriptor)


def preserve_proof(before, after):
    # Full desired catalogue and host checks may intentionally change their
    # hashes at promotion. Component processes, payloads and pool must not.
    for key in ['loaded', 'packages', 'pool']:
        require(canonical(before[key]) == canonical(after[key]), 'SOURCE_UPGRADE_COMPONENT_CHANGED')


def root_verify(journal, helper, *, final=False, full=False):
    import install_preflight
    import source_upgrade_proof as proof
    if full:
        before = proof.prove(journal['context']['oldValues'], journal['config'], journal['sourceRoot'],
                             journal['catalogueBefore'], expected_binding=journal['context']['binding'],
                             stage=journal['stage'], operation=journal['operationId'],
                             package_reference=journal['packageReference'])
        require(canonical(before) == canonical(journal['proof']), 'SOURCE_UPGRADE_LIVE_PROOF_CHANGED')
    else:
        binding = proof.read_binding(journal['context']['oldValues'])[0]
        require(canonical(binding) == canonical(journal['context']['binding']), 'SOURCE_UPGRADE_BINDING_CHANGED')
        from source_upgrade_packages import verify_reference
        reference = verify_reference(journal['stage'], journal['operationId'], journal['values'],
                                     journal['sourceRoot'], journal['packageReference'])
        require(reference['referenceTreeSha256'] == journal['packageReference']['payloadTreeSha256'],
                'SOURCE_UPGRADE_PACKAGE_CHANGED')
    receipt = helper.run('verify', journal['stage'],
                         {'operationId': journal['operationId'], 'sourceIdentity': journal['identity']})
    verify_package_modes(receipt)
    require(receipt == journal['receipt'], 'SOURCE_UPGRADE_STAGE_CHANGED')
    helper.run('check-destination', journal['stage'], {'operationId': journal['operationId'],
        'sourceIdentity': journal['identity'], 'releaseRoot': journal['values']['relay_release_root'], 'reinstall': False},
        journal['values']['relay_release_root'] + '/' + journal['identity']['revision'])
    if final:
        install_preflight.remote({'values': journal['values'], 'action': 'verify',
            'operation': journal['operationId'], 'target': journal['identity']['revision'],
            'stage': journal['stage'], 'reinstall': False})
    return receipt


def admission(prefix, *arguments, payload=None):
    result = subprocess.run([*prefix, *arguments], input=None if payload is None else canonical(payload),
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60, check=False)
    require(result.returncode == 0 and len(result.stdout) <= 1024 * 1024, 'SOURCE_UPGRADE_ADMISSION_UNPROVEN')
    return json.loads(result.stdout)


def operation_record(values, revision):
    return {'schemaVersion': values['relay_production_operation_schema_version'],
            'state': 'RECOVERY_REQUIRED', 'phase': 'apply', 'target_head': revision}


def transition_lock(values, helper):
    from host_preflight import resolved
    values = resolved(values)
    path = Path(values['relay_production_operation_lock_path'])
    helper.protected(path.parent, directory=True)
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    info = os.fstat(descriptor)
    require(stat.S_ISREG(info.st_mode) and info.st_uid == info.st_gid == 0
            and not info.st_mode & 0o022 and info.st_nlink == 1, 'SOURCE_UPGRADE_TRANSITION_LOCK_UNSAFE')
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def promote_root(journal, data, helper):
    import install_preflight
    import source_upgrade_proof as proof
    from host_preflight import resolved
    values = resolved(journal['values'])
    prefix = data['admissionPrefix']
    require(prefix == ['/usr/bin/python3', '-I', journal['sourceRoot'] + '/deploy/writer_lock_lease.py',
        '--exec-admission', data['lease'], journal['sourceRoot'], values['relay_consumer_config_path'],
        values['relay_github_repository']], 'SOURCE_UPGRADE_ADMISSION_BINDING_CHANGED')
    require(data['lease'] == journal['stage'] + '/writer-lock.json', 'SOURCE_UPGRADE_LEASE_CHANGED')
    def gate_ready():
        gate = admission(prefix, 'status', '--operation', journal['operationId'])
        require(gate['phase'] == 'applying' and gate['operationId'] == journal['operationId']
                and gate['target'] == journal['identity']['revision']
                and not gate['active'] and not gate['unknown'], 'SOURCE_UPGRADE_GATE_CHANGED')
    gate_ready()
    activity = install_preflight.observe_predispatch_service_intent(values)
    retained = admission(prefix, 'snapshot', '--operation', journal['operationId'], payload=activity)
    require(retained['previousActive'] == activity, 'SOURCE_UPGRADE_SNAPSHOT_CHANGED')
    # The sole full final live proof follows drain under the retained Writer
    # lease, immediately before creating the original backend mutation record.
    root_verify(journal, helper, final=True, full=True)
    destination = values['relay_release_root'] + '/' + journal['identity']['revision']
    move_release = release_move_plan(Path(journal['stage']) / 'release', destination, helper)
    record = Path(values['relay_production_operation_record_path'])
    descriptor = transition_lock(values, helper)
    try:
        require(not os.path.lexists(record), 'SOURCE_UPGRADE_OPERATION_PENDING')
        helper.atomic(record, canonical(operation_record(values, journal['identity']['revision'])) + b'\n', 0o600)
    finally:
        os.close(descriptor)
    gate_ready()
    if move_release is None:
        helper.run('consume', journal['stage'], {'operationId': journal['operationId'],
            'sourceIdentity': journal['identity'], 'releaseRoot': values['relay_release_root'], 'reinstall': False}, destination)
    else:
        # Keep the frozen consumer's immediate sealed-tree revalidation. Only
        # its per-file copy/fsync loop is replaced by the qualified atomic move.
        receipt = helper.run('verify', journal['stage'],
            {'operationId': journal['operationId'], 'sourceIdentity': journal['identity']})
        verify_package_modes(receipt)
        require(receipt == journal['receipt'], 'SOURCE_UPGRADE_STAGE_CHANGED')
        helper.run('check-destination', journal['stage'], {'operationId': journal['operationId'],
            'sourceIdentity': journal['identity'], 'releaseRoot': values['relay_release_root'], 'reinstall': False}, destination)
        sync_release_directories(Path(journal['stage']) / 'release', helper)
        move_release()
        installed_source = str(Path(destination) / 'reviewed-source')
        prefix = [*prefix]
        prefix[2] = installed_source + '/deploy/writer_lock_lease.py'
        prefix[5] = installed_source
    normalize_release(destination, values)
    gate_ready()
    current = Path(values['relay_install_root']) / 'current'
    require(current.is_symlink() and current.resolve(strict=True)
            == Path(values['relay_release_root']) / journal['context']['manifest']['commit'],
            'SOURCE_UPGRADE_BINDING_CHANGED')
    temporary = current.with_name('.current-source-' + str(uuid.uuid4()))
    temporary.symlink_to(destination)
    try:
        os.replace(temporary, current)
        fd = os.open(current.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if os.path.lexists(temporary):
            temporary.unlink()
    # All mutable effects are now protected by the original record and snapshot.
    for entry in journal['changes']:
        path = Path(entry['path'])
        if path.is_relative_to(Path(destination)):
            continue
        gate_ready()
        previous = next(row for row in journal['catalogueBefore']['entries'] if row['path'] == entry['path'])
        require(hashlib.sha256(helper.read_regular(path)).hexdigest() == previous['sha256'],
                'SOURCE_UPGRADE_CONFIG_CHANGED')
        metadata = path.stat()
        helper.atomic(path, base64.b64decode(entry['contentBase64'], validate=True), entry['mode'])
        os.chown(path, metadata.st_uid, metadata.st_gid)
    after_source = str(Path(destination) / 'reviewed-source') if move_release is not None else journal['sourceRoot']
    original_path = sys.path[:]
    try:
        # Lazy imports use the same sealed bytes at their installed name. The
        # UUID journal, lease and package reference remain in the private stage.
        sys.path.insert(0, after_source + '/deploy')
        after = proof.prove(journal['values'], journal['config'], after_source, journal['catalogueAfter'],
                            stage=journal['stage'], operation=journal['operationId'],
                            package_reference=journal['packageReference'])
    finally:
        sys.path[:] = original_path
    preserve_proof(journal['proof'], after)
    require(install_preflight.observe_predispatch_service_intent(values) == activity, 'SOURCE_UPGRADE_ACTIVITY_CHANGED')
    gate_ready()
    descriptor = transition_lock(values, helper)
    try:
        require(json.loads(helper.read_regular(record)) == operation_record(values, journal['identity']['revision']),
                'SOURCE_UPGRADE_OPERATION_CHANGED')
        record.unlink()
        fd = os.open(record.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        os.close(descriptor)
    return {'status': 'SOURCE_UPGRADE_READY', 'revision': journal['identity']['revision'],
            'consumerRevision': journal['manifest']['consumerRevision'],
            'previousRevision': journal['manifest']['previousRevision']}


def remote(action, data):
    import source_upgrade_proof as proof
    from installed_state import NotEligible
    stage_path = Path(data['stage'])
    require(stage_path.is_absolute() and stage_path.parent == Path(data['values']['relay_release_root'])
            and data['sourceRoot'] == str(stage_path / 'release/reviewed-source'),
            'SOURCE_UPGRADE_SOURCE_BINDING_CHANGED')
    if action == 'describe':
        try:
            return proof.describe(data['values'], data['config'], data['identity'], data['sourceRoot'])
        except (NotEligible, ValueError, OSError, subprocess.SubprocessError):
            return {'eligible': False}
    helper = stage_helper(data['sourceRoot'])
    root = helper.stage_root(data['stage'], data['operationId'])
    if action == 'prepare':
        try:
            changes = catalogue_transition(data['catalogueBefore'], data['catalogueAfter'],
                                          data['context']['manifest'], data['manifest'], data['values']['relay_config_root'], data['values']['relay_release_root'])
            require(changes == data['changes'], 'SOURCE_UPGRADE_CATALOGUE_CHANGED')
            require(data['manifest'] == desired_manifest(data['values'], data['identity'], data['context']['manifest']),
                    'SOURCE_UPGRADE_MANIFEST_CHANGED')
            from source_upgrade_packages import prepare_reference
            package_reference = prepare_reference(data['stage'], data['operationId'], data['values'], data['sourceRoot'])
            before = proof.prove(data['context']['oldValues'], data['config'], data['sourceRoot'],
                data['catalogueBefore'], expected_binding=data['context']['binding'], stage=data['stage'],
                operation=data['operationId'], package_reference=package_reference)
        except (NotEligible, ValueError, OSError, subprocess.SubprocessError):
            return {'eligible': False}
        require(not os.path.lexists(root / 'source-upgrade.json'), 'SOURCE_UPGRADE_STAGE_ALREADY_PREPARED')
        expected = {'operationId': data['operationId'], 'sourceIdentity': data['identity']}
        acquisition = helper.run('extract', root, {**expected, 'compatibilityLinks': data['values'].get('relay_compatibility_links', [])}, root / 'source.tar')
        release = root / 'release'
        binary = release / 'bin/reviewer-mcp-http'
        binary.parent.mkdir(mode=0o751, exist_ok=True)
        helper.protected(binary.parent, directory=True)
        binary.parent.chmod(0o751)
        old_manifest = data['context']['manifest']
        old_release = Path(data['values']['relay_release_root']) / old_manifest['commit']
        raw = helper.read_regular(old_release / 'bin/reviewer-mcp-http')
        require(hashlib.sha256(raw).hexdigest() == old_manifest['reviewerBinarySha256'], 'SOURCE_UPGRADE_REVIEWER_CHANGED')
        helper.atomic(binary, raw, 0o750)
        for name, target in helper.BIN_LINKS.items():
            path = release / name
            require(not os.path.lexists(path), 'SOURCE_UPGRADE_STAGE_ALIAS_CHANGED')
            path.symlink_to(target)
        reviewer_source = release / 'reviewer-source'
        reviewer_source.mkdir(mode=0o750)
        helper.protected(reviewer_source, directory=True)
        reviewer_source.chmod(0o750)
        for name in ['Cargo.toml', 'Cargo.lock']:
            helper.atomic(reviewer_source / name, helper.read_regular(release / 'reviewed-source/reviewer' / name), 0o640)
        helper.copy_tree(release / 'reviewed-source/reviewer/src', reviewer_source / 'src')
        contracts = release / 'contracts'
        contracts.mkdir(mode=0o750)
        helper.protected(contracts, directory=True)
        contracts.chmod(0o750)
        (contracts / 'src').mkdir(mode=0o750)
        helper.protected(contracts / 'src', directory=True)
        (contracts / 'src').chmod(0o750)
        for name in ['github-authority-v1.json', 'github-authority-v4.json']:
            helper.atomic(contracts / 'src' / name, helper.read_regular(release / 'reviewed-source/contracts/src' / name), 0o640)
        helper.atomic(release / 'deployment-config.json', data['values']['relay_installed_deployment_config'].encode(), 0o600)
        helper.atomic(release / 'artifact-manifest.json', canonical(data['manifest']) + b'\n', 0o640)
        release.chmod(0o751)
        target_release = Path(data['values']['relay_release_root']) / data['identity']['revision']
        for entry in changes:
            path = Path(entry['path'])
            if path.is_relative_to(target_release):
                require(entry['kind'] == 'file', 'SOURCE_UPGRADE_GENERATED_ENTRY_UNSUPPORTED')
                target = release / path.relative_to(target_release)
                helper.atomic(target, base64.b64decode(entry['contentBase64'], validate=True), entry['mode'])
        candidate_checks(root, data['values']['relay_github_repository'])
        package_receipts = {kind: {'mode': 'installed-reuse', 'kind': kind,
            'sourceRevision': old_manifest['commit'], 'recipeSha256': before['packages'][kind]['recipeSha256'],
            'treeSha256': before['packages'][kind]['treeSha256']}
            for kind in ['runner', 'codex']}
        metadata = {**expected, 'sourceAcquisition': acquisition,
            'reviewer': {'binarySha256': old_manifest['reviewerBinarySha256'],
                'cargoVersion': old_manifest['reviewerBuildToolchain']['cargoVersion'],
                'artifactProvenance': 'verified-reuse', 'reuseSourceRelease': str(old_release),
                'reuseSourceBinarySha256': old_manifest['reviewerBinarySha256'],
                'buildContractSha256': old_manifest['reviewerBuildContractSha256'], 'previousRevision': old_manifest['commit']},
            'toolchain': {'livePrefix': data['values']['relay_rust_toolchain_root'], 'stagedPrefix': '',
                'version': data['values']['relay_rust_toolchain_version'],
                'archiveSha256': old_manifest['reviewerBuildToolchain']['archiveSha256']}, 'packages': package_receipts}
        verify_package_modes(metadata)
        receipt = helper.run('seal', root, metadata)
        journal = {**data, 'version': 1, 'proof': before, 'receipt': receipt, 'packageReference': package_reference}
        helper.atomic(root / 'source-upgrade.json', canonical(journal) + b'\n', 0o600)
        return {'status': 'SOURCE_STAGE_READY', 'host': before['host']}
    journal = read_journal(data, helper)
    if action == 'verify':
        return {'status': 'SOURCE_STAGE_READY', 'receipt': root_verify(journal, helper, final=data.get('final', False))}
    require(action == 'promote', 'SOURCE_UPGRADE_ACTION_INVALID')
    return promote_root(journal, data, helper)


if __name__ == '__main__':
    try:
        require(os.geteuid() == 0 and sys.argv[1:] in [['describe'], ['prepare'], ['verify'], ['promote']])
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        raw = sys.stdin.buffer.read(MAX_INPUT + 1)
        require(len(raw) <= MAX_INPUT)
        print(json.dumps(remote(sys.argv[1], json.loads(raw))))
    except Exception:
        # The private journal contains proof, environment and paths. Never
        # include it, the request, or child diagnostics in the public failure.
        print('SOURCE_UPGRADE_UNPROVEN', file=sys.stderr)
        raise SystemExit(40)
