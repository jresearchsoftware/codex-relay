#!/usr/bin/env python3
"""Relay's owner-operated Debian deployment entrypoint (backend is private)."""
import argparse
from contextlib import ExitStack
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import shlex
import stat
import subprocess
import sys
import tempfile
import time
import uuid

sys.dont_write_bytecode = True
from config import load, compile_inputs, require, selector

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'deploy/ansible'
PHASES = {'check': 'site.yml', 'apply': 'site.yml', 'upgrade': 'site.yml', 'post-check': 'site.yml',
          'inventory': None, 'bootstrap': 'site.yml', 'reinstall': 'site.yml',
          'reinstall-recover': None,
          'workflow-project': None, 'workflow-verify': None,
          'runner-register': None, 'general-runner-register': None,
          'diagnose': 'relay-production-diagnostic.yml', 'activate': 'relay-reviewer-activation.yml',
          'runner-enable': 'relay-production-runner-enable.yml',
          'general-runner-enable': 'relay-general-runner.yml',
          'stale-dispose': 'relay-production-operation-stale-disposition.yml',
          'tls-check': 'relay-tls-preparation.yml',
          'tls-prepare': 'relay-tls-preparation.yml',
          'tls-dry-run': 'relay-tls-preparation.yml',
          'tls-issue': 'relay-tls-preparation.yml',
          'reviewer-credentials': 'relay-reviewer-credentials.yml',
          'writer-credentials': 'relay-writer-credentials.yml',
          'codex-credentials': 'relay-codex-credentials.yml',
          'ingress': 'relay-docker-nginx.yml'}
BOOTSTRAP_MUTATIONS = ['tls-prepare', 'tls-dry-run', 'tls-issue', 'reviewer-credentials',
                       'writer-credentials', 'codex-credentials', 'ingress']


def command(argv, **kwargs):
    return subprocess.run([str(a) for a in argv], check=True, text=True, capture_output=True, **kwargs).stdout.strip()


def git(root, *args):
    return command(['git', '-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false', '-C', root, *args])


def clean_git(root):
    require(Path(git(root, 'rev-parse', '--show-toplevel')).resolve() == root.resolve(), 'source-root')
    require(not git(root, 'status', '--porcelain', '--untracked-files=all'), 'clean-source')
    revision = git(root, 'rev-parse', 'HEAD^{commit}')
    require(re.fullmatch('[0-9a-f]{40}', revision), 'source-revision')
    return revision


def committed_projection(config, revision, source_root, consumer_root, consumer_revision):
    """Bind derived workflow bytes to the frozen consumer Git commit as well.

    A clean status excludes ignored files; ignored/untracked projections are
    proposals and cannot establish the reviewed consumer installation binding.
    """
    from workflow_projection import MANIFEST, render, verify
    manifest = verify(config, revision, source_root, consumer_root)
    files = {**render(config, revision, source_root),
             MANIFEST: json.dumps(manifest, sort_keys=True, indent=2).encode() + b'\n'}
    for path, expected in files.items():
        entry = git(consumer_root, 'ls-tree', consumer_revision, '--', path)
        require(entry.startswith('100644 blob ') and entry.endswith('\t' + path),
                'workflow-projection-not-in-consumer-commit:' + path)
        raw = subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false',
                              '-C', str(consumer_root), 'cat-file', 'blob', consumer_revision + ':' + path],
                             capture_output=True, check=True).stdout
        require(raw == expected, 'workflow-projection-commit-mismatch:' + path)


def source_identity(root):
    revision = clean_git(root)
    tree = git(root, 'rev-parse', revision + '^{tree}')
    # git archive below exports only this exact object, never working files.
    entries = git(root, 'ls-tree', '-r', revision).splitlines()
    require(all(row.split()[0] in ['100644', '100755'] for row in entries), 'regular-source-files')
    def digest(*paths):
        listing = git(root, 'ls-tree', '-r', revision, '--', *paths)
        require(listing, 'source-paths')
        return hashlib.sha256(listing.encode()).hexdigest()
    return {'revision': revision, 'tree': tree,
            'sourceTreeSha256': digest('controller', 'runtime', 'consumer', 'contracts', 'reviewer', 'deploy'),
            'controllerSourceTreeSha256': digest('consumer/consumer.mjs', 'consumer/consumer-config.mjs',
                'controller/src', 'runtime/src', 'runtime/config', 'contracts/src', 'reviewer/src/executable-cr-v2.json'),
            'codexLauncherSourceTreeSha256': digest('deploy/ansible/roles/relay_codex_runtime/templates/relay-codex-launcher.mjs.j2',
                'deploy/ansible/roles/relay_codex_runtime/templates/relay-codex-cleanup.py.j2'),
            'reviewerSourceTreeSha256': digest('reviewer'),
            'reviewerBuildInputsTreeSha256': digest('deploy/ansible/group_vars/all.yml', 'deploy/ansible/site.yml',
                'deploy/ansible/roles/relay_base', 'deploy/ansible/roles/relay_preflight',
                'deploy/ansible/roles/relay_artifacts', 'deploy/ansible/roles/relay_runtime',
                'deploy/ansible/roles/relay_nginx', 'deploy/ansible/roles/relay_docker_nginx')}


def root_owned(path):
    for entry in [path, *path.parents]:
        metadata = entry.lstat()
        require(metadata.st_uid == 0 and not stat.S_ISLNK(metadata.st_mode)
                and not metadata.st_mode & 0o022, 'protected-local-input')


def ingress_guard(target, key, values, revision):
    """Hold the installed host operation lock across the private adapter play.

    The remote helper is from the exact accepted installation, not transferred
    candidate code. EOF releases the kernel lock; no daemon or new ledger.
    """
    remote = ['/usr/bin/python3', values['relay_install_root'] +
              '/current/reviewed-source/deploy/ansible/tools/bootstrap_guard.py', '--hold',
              '--lock-file', values['relay_runtime_root'] + '/production-operation.lock',
              '--operation-record', values['relay_production_operation_record_path'],
              '--manifest', values['relay_install_root'] + '/current/artifact-manifest.json',
              '--exact-head', revision]
    process = subprocess.Popen(['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
        '-o', 'IdentitiesOnly=yes', '-i', str(key), target['user'] + '@' + target['host'], shlex.join(remote)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    with selectors.DefaultSelector() as ready:
        ready.register(process.stdout, selectors.EVENT_READ)
        acquired = bool(ready.select(timeout=30)) and process.stdout.readline().strip() == 'BOOTSTRAP_GUARD_READY'
    if not acquired:
        process.stdin.close()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        raise RuntimeError('ingress-operation-guard-unavailable')
    return process


def apply_guard(target, key, namespace):
    # The same reviewed stdlib-only lock implementation runs on the target for
    # an owner apply and locally for the installed helper. No credential or
    # user-selected command is passed to the holder.
    source = (ROOT / 'deploy/deployment_lock.py').read_text()
    remote = ['/usr/bin/python3', '-I', '-c', source,
              '/var/lib/' + namespace + '-deployment.lock']
    process = subprocess.Popen(['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
        '-o', 'IdentitiesOnly=yes', '-i', str(key), target['user'] + '@' + target['host'], shlex.join(remote)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    with selectors.DefaultSelector() as ready:
        ready.register(process.stdout, selectors.EVENT_READ)
        acquired = bool(ready.select(timeout=30)) and process.stdout.readline().strip() == 'DEPLOYMENT_LOCK_READY'
    if not acquired:
        process.stdin.close()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        raise RuntimeError('host-apply-lock-unavailable')
    return process


def remote_admission(target, key, namespace, *arguments):
    remote = ['/opt/' + namespace + '/relay-admission', *arguments]
    result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
        '-o', 'IdentitiesOnly=yes', '-i', str(key), target['user'] + '@' + target['host'],
        shlex.join(remote)], text=True, capture_output=True, timeout=1860)
    require(result.returncode == 0, 'trusted-admission-operation-failed;inspect-before-recovery')
    return json.loads(result.stdout)


def run_backend(argv, cwd, env, log, guard=None):
    process = subprocess.Popen(argv, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT)
    started = time.monotonic()
    next_progress = started + 30
    try:
        while process.poll() is None:
            if time.monotonic() >= next_progress:
                print(f'RELAY_DEPLOYMENT_PROGRESS=backend-running;elapsed_seconds={int(time.monotonic()-started)}', flush=True)
                next_progress = time.monotonic() + 30
            if guard is not None and guard.poll() is not None:
                raise RuntimeError('host-operation-guard-lost;inspect-before-retry')
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
        if guard is not None and guard.poll() is not None:
            raise RuntimeError('host-operation-guard-lost;inspect-before-retry')
        return process.returncode
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def arguments():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', required=True, type=Path)
    p.add_argument('--phase', choices=[*PHASES, 'validate'], required=True)
    p.add_argument('--requested-revision', help='selector already resolved by the trusted acquisition/bootstrap')
    p.add_argument('--resolved-revision', help='exact acquisition result; must equal this clean checkout')
    p.add_argument('--consumer-root', type=Path, help='consumer Git checkout when durable config is stored separately')
    p.add_argument('--authorize-upgrade', action='store_true')
    p.add_argument('--authorize-workflow-projection', action='store_true')
    p.add_argument('--authorize-bootstrap', action='store_true', help='install after inventory and consumer workflow review')
    p.add_argument('--authorize-reinstall', action='store_true', help='retire proven managed runtime and install the exact target')
    p.add_argument('--authorize-reinstall-recovery', action='store_true',
                   help='Safely archive a diagnosed failed reinstall without retargeting its journal')
    p.add_argument('--reinstall-recovery-target', help='Exact target of the retained failed reinstall')
    p.add_argument('--projection-output', type=Path, help='optional directory for derived workflow review files')
    p.add_argument('--authorize-runner-register', action='store_true')
    p.add_argument('--authorize-general-runner-register', action='store_true')
    p.add_argument('--runner-registration-token', help='ephemeral bootstrap input for this registration only')
    p.add_argument('--general-runner-registration-token', help='ephemeral bootstrap input for this registration only')
    p.add_argument('--log-root', type=Path, default=Path('/tmp/relay-deployment'))
    p.add_argument('--local-reconcile', action='store_true', help=argparse.SUPPRESS)
    p.add_argument('--local-lifecycle', action='store_true', help=argparse.SUPPRESS)
    p.add_argument('--lifecycle-operation', help=argparse.SUPPRESS)
    p.add_argument('--lifecycle-lock-fd', type=int, help=argparse.SUPPRESS)
    p.add_argument('--authorize-lifecycle-recovery', action='store_true',
                   help='After diagnosis/disposition, recover or roll back a retained quiesced operation')
    p.add_argument('--lifecycle-recovery-operation', help='Exact retained admission operation UUID')
    p.add_argument('--consumer-revision', help=argparse.SUPPRESS)
    p.add_argument('--expected-installed-head', help=argparse.SUPPRESS)
    p.add_argument('--workflow-consumer-revision', help=argparse.SUPPRESS)
    p.add_argument('--authorize-apply-recovery', action='store_true',
                   help='Owner-authorized matching installed-config apply recovery after diagnosis')
    p.add_argument('--authorize-reviewer-activation', action='store_true')
    p.add_argument('--authorize-runner-enable', action='store_true')
    p.add_argument('--authorize-general-runner-enable', action='store_true')
    p.add_argument('--authorize-stale-disposition', action='store_true')
    for phase in BOOTSTRAP_MUTATIONS:
        p.add_argument('--authorize-' + phase, action='store_true')
    p.add_argument('--stale-phase', choices=['apply', 'activate', 'runner-enable'])
    p.add_argument('--stale-head')
    p.add_argument('--stale-completed-phase', choices=['apply'])
    p.add_argument('--stale-apply-shape', choices=['bootstrap-only'])
    p.add_argument('--stale-state-hash')
    p.add_argument('--issue-number', type=int)
    p.add_argument('--issue-body-sha256', default='')
    p.add_argument('--pull-request', type=int)
    p.add_argument('--review-id', type=int)
    p.add_argument('--reviewed-head', help='diagnostic PR identity only; never deployment approval')
    p.add_argument('--change-request-id')
    p.add_argument('--branch')
    p.add_argument('--base-branch-sha')
    return p.parse_args()


def run(args):
    os.umask(0o077)
    require(args.authorize_upgrade == (args.phase == 'upgrade'), 'explicit-upgrade')
    require(args.authorize_workflow_projection == (args.phase == 'workflow-project'), 'explicit-workflow-projection')
    require(not args.authorize_bootstrap or args.phase == 'bootstrap', 'explicit-bootstrap')
    require(args.authorize_reinstall == (args.phase == 'reinstall'), 'explicit-reinstall')
    require(args.authorize_reinstall_recovery == (args.phase == 'reinstall-recover')
            and (bool(re.fullmatch('[0-9a-f]{40}', args.reinstall_recovery_target or ''))
                 if args.authorize_reinstall_recovery else args.reinstall_recovery_target is None)
            and not (args.authorize_reinstall_recovery and args.local_reconcile), 'explicit-reinstall-recovery')
    require(args.projection_output is None or args.phase in ['bootstrap', 'reinstall'], 'projection-output-phase')
    require(args.authorize_runner_register == (args.phase == 'runner-register'), 'explicit-runner-registration')
    require(args.authorize_general_runner_register == (args.phase == 'general-runner-register'),
            'explicit-general-runner-registration')
    require(args.runner_registration_token is None or args.phase == 'runner-register', 'runner-token-phase')
    require(args.general_runner_registration_token is None or args.phase == 'general-runner-register',
            'general-runner-token-phase')
    require(not args.local_reconcile or args.consumer_root is None, 'local-consumer-root-forbidden')
    require(not args.local_lifecycle or (os.geteuid() == 0 and not args.local_reconcile
            and args.phase in ['apply', 'upgrade', 'post-check']
            and re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', args.lifecycle_operation or '')
            and args.lifecycle_lock_fd is not None), 'protected-local-lifecycle')
    require(args.local_lifecycle or (args.lifecycle_operation is None and args.lifecycle_lock_fd is None),
            'lifecycle-internal-options')
    require(args.authorize_lifecycle_recovery == bool(args.lifecycle_recovery_operation)
            and (not args.authorize_lifecycle_recovery or (args.phase == 'upgrade' and not args.local_lifecycle
                 and re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', args.lifecycle_recovery_operation))),
            'explicit-lifecycle-recovery')
    require((bool(re.fullmatch('[0-9a-f]{40}', args.workflow_consumer_revision or ''))
             if args.expected_installed_head else args.workflow_consumer_revision is None),
            'installed-workflow-consumer-revision')
    config_path = args.config.absolute()
    installed_digest = ''
    installed_consumer_revision = None
    if args.expected_installed_head:
        require(args.local_reconcile and args.phase == 'apply' and args.consumer_revision is None
                and config_path == ROOT.parent / 'deployment-config.json', 'installed-reconcile-interface')
        from installed_config import verify
        config, installed_digest, installed_consumer_revision = verify(ROOT, args.expected_installed_head)
    else:
        config = load(config_path, ROOT)
    values = compile_inputs(config)
    if args.local_lifecycle:
        root_owned(ROOT)
        root_owned(config_path)
        lock_path = Path('/var/lib/' + values['relay_namespace'] + '-deployment.lock')
        lock_info = os.fstat(args.lifecycle_lock_fd)
        current_lock = lock_path.lstat()
        require(stat.S_ISREG(lock_info.st_mode) and lock_info.st_uid == lock_info.st_gid == 0
                and stat.S_IMODE(lock_info.st_mode) == 0o600 and lock_info.st_nlink == 1
                and (lock_info.st_dev, lock_info.st_ino) == (current_lock.st_dev, current_lock.st_ino),
                'lifecycle-host-lock-binding')
        fcntl.flock(args.lifecycle_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        gate_result = command([values['relay_install_root'] + '/relay-admission', 'status',
                               '--operation', args.lifecycle_operation])
        gate_state = json.loads(gate_result)
        require(gate_state['phase'] == 'applying' and gate_state['target'] == args.resolved_revision,
                'lifecycle-admission-binding')
    require(not args.authorize_apply_recovery or
            (args.phase == 'apply' and not args.local_reconcile and values['relay_local_apply_source'] == 'installed'),
            'explicit-installed-apply-recovery')
    if args.phase == 'validate':
        print('RELAY_DEPLOYMENT_CONFIG=PASS;schemaVersion=1')
        return
    require(sys.platform == 'linux', 'linux-controller')
    if args.local_reconcile:
        # An unprivileged runner can reach only the installed fixed sudo helper,
        # which stages the admitted consumer commit and calls this exact source.
        require(os.geteuid() == 0 and args.phase == 'apply', 'local-reconcile-root-apply')
        root_owned(ROOT)
        root_owned(config_path)
        identity = json.loads((ROOT / '.relay-source.json').read_text())
        require(ROOT == Path(values['relay_release_root']) / identity['revision'] / 'reviewed-source', 'installed-product-path')
        require(config['environment']['localApply'].get('source') != 'installed'
                or bool(args.expected_installed_head), 'installed-reconcile-interface')
        consumer_revision = installed_consumer_revision or args.consumer_revision
        requested = identity['revision']  # explicit installed version, never pretend to resolve remote main
    else:
        require(args.consumer_revision is None, 'consumer-revision-from-git-only')
        identity = source_identity(ROOT)
        requested = args.requested_revision or identity['revision']
        if args.phase == 'inventory':
            consumer_revision = None
        else:
            consumer_root = (args.consumer_root.absolute() if args.consumer_root else
                             Path(git(config_path.parent, 'rev-parse', '--show-toplevel')))
            consumer_revision = clean_git(consumer_root)
    require(selector(requested), 'requested-revision')
    require(args.resolved_revision is None or args.resolved_revision == identity['revision'], 'resolved-revision-mismatch')
    require(args.phase == 'inventory' or re.fullmatch('[0-9a-f]{40}', consumer_revision or ''), 'consumer-revision')
    revision = identity['revision']
    if args.phase in ['upgrade', 'workflow-project', 'workflow-verify', 'inventory', 'bootstrap', 'reinstall', 'reinstall-recover']:
        require(args.resolved_revision == revision and not args.local_reconcile, 'explicit-exact-product-target')
    require(not re.fullmatch('[0-9a-f]{40}', requested) or requested == revision, 'selected-commit-mismatch')
    require(args.authorize_reviewer_activation == (args.phase == 'activate'), 'explicit-activation')
    require(args.authorize_runner_enable == (args.phase == 'runner-enable'), 'explicit-runner-enablement')
    require(args.authorize_general_runner_enable == (args.phase == 'general-runner-enable'), 'explicit-general-runner-enablement')
    require(args.authorize_stale_disposition == (args.phase == 'stale-dispose'), 'explicit-stale-disposition')
    for phase in BOOTSTRAP_MUTATIONS:
        require(getattr(args, 'authorize_' + phase.replace('-', '_')) == (args.phase == phase),
                'explicit-' + phase)
    if args.phase in ['tls-dry-run', 'tls-issue']:
        require(values['relay_tls_acme_configured'], 'tls.acme-required')
    for role in ['reviewer', 'writer', 'codex']:
        if args.phase == role + '-credentials':
            require(bool(values['relay_' + role + '_credential_source_file']), role + 'Credential-required')
    if args.phase == 'stale-dispose':
        require(args.stale_phase and re.fullmatch('[0-9a-f]{40}', args.stale_head or '') and args.stale_head != revision, 'stale-identity')
        if args.stale_phase == 'apply':
            require(re.fullmatch('[0-9a-f]{64}', args.stale_state_hash or '') and
                    ((args.stale_apply_shape == 'bootstrap-only' and not args.stale_completed_phase) or
                     (not args.stale_apply_shape and args.stale_completed_phase == 'apply')), 'stale-apply-evidence')
        else:
            require(not any([args.stale_apply_shape, args.stale_completed_phase, args.stale_state_hash]), 'stale-flags')
    else:
        require(not any([args.stale_phase, args.stale_head, args.stale_completed_phase, args.stale_state_hash, args.stale_apply_shape]), 'stale-flags')
    if args.phase == 'diagnose':
        if args.issue_number:
            require(args.issue_number > 0 and not any([args.pull_request, args.review_id, args.reviewed_head,
                args.change_request_id, args.branch, args.base_branch_sha]), 'diagnostic-target')
            require(not args.issue_body_sha256 or re.fullmatch('[0-9a-f]{64}', args.issue_body_sha256), 'issue-digest')
        else:
            require(args.pull_request and args.pull_request > 0 and args.review_id and args.review_id > 0
                and re.fullmatch('[0-9a-f]{40}', args.reviewed_head or '')
                and re.fullmatch('CR-[A-Za-z0-9-]{1,96}', args.change_request_id or '')
                and selector(args.branch) and re.fullmatch('[0-9a-f]{40}', args.base_branch_sha or ''), 'diagnostic-pr')
    else:
        require(not any([args.issue_number, args.issue_body_sha256, args.pull_request, args.review_id,
            args.reviewed_head, args.change_request_id, args.branch, args.base_branch_sha]), 'diagnostic-flags')
    if args.phase in ['workflow-project', 'workflow-verify', 'upgrade'] or args.local_lifecycle or (args.phase == 'apply' and not args.local_reconcile):
        from workflow_projection import project, verify
        if args.phase == 'workflow-project':
            project(config, revision, ROOT, consumer_root)
        else:
            committed_projection(config, revision, ROOT, consumer_root, consumer_revision)
        print(f'RELAY_WORKFLOW_PROJECTION=PASS;revision={revision};consumer={consumer_revision}', flush=True)
        if args.phase in ['workflow-project', 'workflow-verify']:
            print(f'RELAY_DEPLOYMENT_RESULT=PASS;phase={args.phase}')
            return
    if args.local_lifecycle and args.phase == 'post-check':
        # A later graceful resume observes current consumer projection bytes,
        # but does not rewrite the installed manifest's original provenance.
        from installed_config import verify
        _, _, consumer_revision = verify(Path(values['relay_install_root']) / 'releases' /
                                         revision / 'reviewed-source', revision)
    target = config['target']
    key = Path(target['identityFile']).expanduser()
    if not args.local_reconcile and not args.local_lifecycle:
        require(key.is_file() and not key.is_symlink(), 'operator-key')
        require(command(['ssh-keygen', '-lf', key]).split()[1] == target['identityFingerprint'], 'operator-key-identity')
        known = command(['ssh-keygen', '-F', target['host']])
        fingerprints = command(['ssh-keygen', '-lf', '-'], input=known).splitlines()
        require(any(row.split()[1] == target['hostFingerprint'] for row in fingerprints), 'host-identity')
        command(['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'IdentitiesOnly=yes',
                 '-i', key, target['user'] + '@' + target['host'], 'true'])
    install_flow = args.phase in ['bootstrap', 'reinstall']
    if args.phase == 'inventory' or install_flow:
        from inventory import remote_inventory
        observed = remote_inventory(target, key, config)
        print('RELAY_INVENTORY=' + json.dumps(observed, sort_keys=True), flush=True)
        if args.phase == 'inventory':
            print('RELAY_DEPLOYMENT_RESULT=PASS;phase=inventory;authority=read-only', flush=True)
            return
        require(not observed['blockers'], 'inventory-blocked;inspect-reported-prerequisites')
        from workflow_projection import prepare, render
        proposal_key = hashlib.sha256(b''.join(path.encode() + b'\0' + content
            for path, content in render(config, revision, ROOT).items())).hexdigest()[:16]
        output = args.projection_output or (args.log_root / ('workflows-' + revision + '-' +
                  config['consumer']['repository'].replace('/', '-') + '-' + proposal_key))
        proposal = prepare(config, revision, ROOT, consumer_root, output)
        print('RELAY_BOOTSTRAP_PROJECTION=' + json.dumps(proposal, sort_keys=True), flush=True)
        if proposal['state'] != 'ready':
            print('RELAY_DEPLOYMENT_PENDING=WORKFLOW_REVIEW_REQUIRED;target_unchanged=true', flush=True)
            return
        committed_projection(config, revision, ROOT, consumer_root, consumer_revision)
        if args.phase == 'bootstrap' and not args.authorize_bootstrap:
            print('RELAY_DEPLOYMENT_PENDING=INSTALL_AUTHORIZATION_REQUIRED;flag=--authorize-bootstrap;target_unchanged=true')
            return
    admission_operation_id = (args.lifecycle_operation if args.local_lifecycle else
        (args.lifecycle_recovery_operation or str(uuid.uuid4()) if args.phase == 'upgrade' else ''))
    values.update({
        'relay_review_root': str(ROOT), 'relay_source_identity': identity,
        'relay_requested_revision': requested, 'relay_consumer_revision': consumer_revision,
        'relay_deployment_profile': 'production',
        'relay_production_operation_phase': 'apply' if args.phase == 'upgrade' or install_flow else args.phase,
        'relay_upgrade_requested': args.phase == 'upgrade',
        'relay_upgrade_lifecycle_managed': args.phase == 'upgrade' or (args.local_lifecycle and args.phase == 'apply'),
        'relay_admission_operation_id': admission_operation_id,
        'relay_admission_recovery_authorized': args.authorize_lifecycle_recovery,
        'relay_owner_apply_requested': (args.phase == 'apply' or install_flow) and not args.local_reconcile,
        'relay_production_operation_target_head': revision,
        'relay_production_exact_head': revision, 'relay_reviewer_activation_exact_head': revision,
        'relay_installed_config_reconcile': bool(args.expected_installed_head),
        'relay_installed_config_expected_sha256': installed_digest,
        'relay_workflow_consumer_revision': args.workflow_consumer_revision or '',
        'relay_installed_config_recovery_authorized': args.authorize_apply_recovery or args.phase == 'reinstall',
        'relay_clean_reinstall_journal_sha256': '',
        'relay_production_runner_enable_exact_head': revision,
        'relay_service_state_management': 'preserve',
        'relay_service_activation_authorized': args.authorize_reviewer_activation,
        'relay_service_enabled': args.authorize_reviewer_activation,
        'relay_runner_service_state_management': 'enforce' if args.phase == 'runner-enable' else 'preserve',
        'relay_runner_registration_enabled': args.authorize_runner_enable,
        'relay_runner_registration_authorized': args.authorize_runner_enable,
        'relay_runner_registration_completed': args.authorize_runner_enable,
        'relay_runner_service_enabled': args.authorize_runner_enable,
        'relay_production_runner_enable_authorized': args.authorize_runner_enable,
        'relay_production_defer_lifecycle': args.local_reconcile,
        'relay_production_operation_stale_phase': args.stale_phase or '',
        'relay_production_operation_stale_target_head': args.stale_head or '',
        'relay_production_operation_stale_authorized': args.authorize_stale_disposition,
        'relay_production_operation_stale_actual_completed_phase': args.stale_completed_phase or '',
        'relay_production_operation_stale_expected_state_hash': args.stale_state_hash or '',
        'relay_production_operation_stale_apply_shape': args.stale_apply_shape or '',
        'relay_production_diagnostic_target': 'issue' if args.issue_number else 'pull_request',
        'relay_production_diagnostic_issue_number': args.issue_number,
        'relay_production_diagnostic_issue_body_sha256': args.issue_body_sha256,
        'relay_production_diagnostic_pull_request': args.pull_request,
        'relay_production_diagnostic_review_id': args.review_id,
        'relay_production_diagnostic_reviewed_head': args.reviewed_head or '',
        'relay_production_diagnostic_change_request_id': args.change_request_id or '',
        'relay_production_diagnostic_branch': args.branch or '',
        'relay_production_diagnostic_base_branch_sha': args.base_branch_sha or '',
        'relay_bootstrap_public_entrypoint': True,
        'relay_bootstrap_exact_head': revision,
        'relay_reviewer_credentials_authorized': args.authorize_reviewer_credentials,
        'relay_writer_credentials_authorized': args.authorize_writer_credentials,
        'relay_codex_credentials_authorized': args.authorize_codex_credentials,
        'relay_tls_exact_head': revision,
        'relay_tls_phase': {'tls-check': 'prerequisites', 'tls-prepare': 'prerequisites',
                           'tls-dry-run': 'dry_run', 'tls-issue': 'issue'}.get(args.phase, 'prerequisites'),
    })
    # Preserve complete owner intent for upgrades for every consumer. These
    # literal references never contain credential bytes or bootstrap tokens.
    snapshot = json.dumps(config, sort_keys=True, separators=(',', ':'), ensure_ascii=False) + '\n'
    values['relay_installed_deployment_config'] = snapshot
    values['relay_installed_deployment_config_sha256'] = hashlib.sha256(snapshot.encode('utf-8')).hexdigest()
    require(not installed_digest or installed_digest == values['relay_installed_deployment_config_sha256'],
            'installed-config-canonical')
    if args.phase == 'ingress':
        values.update(relay_docker_nginx_manage=True, relay_docker_nginx_service_enabled=True,
                      relay_docker_nginx_validation_mode='active')
    if args.phase in ['general-runner-enable', 'general-runner-register']:
        import yaml  # part of the private Ansible backend dependency set
        values.update(yaml.safe_load((BACKEND / 'vars/general-runner.yml').read_text()))
        values['relay_general_runner_authorized'] = args.phase == 'general-runner-enable'
    if args.phase in ['runner-register', 'general-runner-register']:
        from runner_registration import register_runner
        token = (args.runner_registration_token if args.phase == 'runner-register'
                 else args.general_runner_registration_token)
        guard = ingress_guard(target, key, values, revision)
        try:
            proof = register_runner(target, key, values, revision, token, guard)
        finally:
            guard.stdin.close()
            require(guard.wait(timeout=30) == 0, 'host-operation-guard-final-check;inspect-before-retry')
        print(proof)
        print(f'RELAY_DEPLOYMENT_RESULT=PASS;phase={args.phase}')
        return
    args.log_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    log_fd, log_name = tempfile.mkstemp(prefix=f'relay-{revision[:12]}-{args.phase}-', suffix='.log', dir=args.log_root)
    print(f'requested_revision={requested}\nresolved_revision={revision}\nconsumer_revision={consumer_revision}', flush=True)
    lock_name = hashlib.sha256((target['host'] + values['relay_install_root']).encode()).hexdigest()[:24]
    lock_path = (Path(values['relay_state_root']) if args.local_reconcile else Path(tempfile.gettempdir())) / ('relay-deploy-' + lock_name + '.lock')
    with os.fdopen(log_fd, 'w') as log, tempfile.TemporaryDirectory(prefix='relay-deploy-') as temporary:
        work = Path(temporary)
        lock = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            require(os.fstat(lock).st_uid == os.getuid() and not os.fstat(lock).st_mode & 0o077, 'invocation-lock')
            if args.phase in ['apply', 'upgrade', 'bootstrap', 'reinstall', 'reinstall-recover', 'activate', 'runner-enable', 'general-runner-enable', 'stale-dispose', *BOOTSTRAP_MUTATIONS]:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # A normal source archive is only an internal transport detail.
            # No consumer lock, helper hash, distribution bundle or host cache.
            if args.phase == 'reinstall-recover':
                from clean_reinstall import remote_action
                guard = apply_guard(target, key, values['relay_namespace'])
                try:
                    recovered = remote_action(target, key, config, args.reinstall_recovery_target,
                                              action='recover', guard=guard)
                    log.write(json.dumps(recovered, sort_keys=True) + '\n')
                    log.flush()
                finally:
                    guard.stdin.close()
                    require(guard.wait(timeout=30) == 0, 'host-operation-guard-final-check;inspect-before-retry')
                print('RELAY_REINSTALL_RECOVERY=' + json.dumps(recovered, sort_keys=True), flush=True)
                print(f'RELAY_DEPLOYMENT_RESULT=PASS;phase=reinstall-recover;controller_revision={revision};log={log_name}', flush=True)
                return
            if args.phase in ['apply', 'upgrade', 'bootstrap', 'reinstall'] and not args.local_reconcile:
                archive = work / 'source.tar'
                git(ROOT, 'archive', '--format=tar', '--output=' + str(archive), revision)
                values['relay_source_archive'] = str(archive)
            inventory = {'all': {'children': {'relay': {'hosts': {target['host']: {**values,
                'ansible_user': target['user'], 'ansible_connection': 'local' if args.local_reconcile or args.local_lifecycle else 'ssh',
                'ansible_become': not (args.local_reconcile or args.local_lifecycle)}}}}}}
            (work / 'inventory.json').write_text(json.dumps(inventory))
            env = {k: os.environ[k] for k in ['HOME', 'PATH', 'USER', 'LANG', 'LC_ALL', 'SSH_AUTH_SOCK'] if k in os.environ}
            env.update({'ANSIBLE_CONFIG': str(BACKEND / 'ansible.cfg'), 'ANSIBLE_ROLES_PATH': str(BACKEND / 'roles'),
                'ANSIBLE_SSH_COMMON_ARGS': '-o BatchMode=yes -o StrictHostKeyChecking=yes -o IdentitiesOnly=yes',
                'ANSIBLE_PRIVATE_KEY_FILE': str(key), 'PYTHONDONTWRITEBYTECODE': '1'})
            playbook = ('relay-production-bootstrap-disposition.yml' if args.stale_apply_shape else PHASES[args.phase])
            argv = ['ansible-playbook', '-i', str(work / 'inventory.json'), str(BACKEND / playbook),
                    '--limit', target['host']]
            if args.phase in ['check', 'post-check', 'tls-check']:
                argv += ['--check']
            started = time.monotonic()
            log.write(f'requested_revision={requested};resolved_revision={revision};consumer_revision={consumer_revision}\n')
            log.flush()
            with ExitStack() as host_locks:
                guard = None
                if args.phase in ['apply', 'upgrade', 'bootstrap', 'reinstall']:
                    if args.local_lifecycle:
                        pass  # inherited, validated host lock covers the complete lifecycle
                    elif args.local_reconcile:
                        from deployment_lock import acquire
                        host_locks.enter_context(acquire('/var/lib/' + values['relay_namespace'] + '-deployment.lock'))
                    else:
                        guard = apply_guard(target, key, values['relay_namespace'])
                elif args.phase == 'ingress':
                    guard = ingress_guard(target, key, values, revision)
                try:
                    lifecycle_operation = None
                    if args.phase == 'upgrade' and not args.local_lifecycle:
                        from lifecycle import progress
                        lifecycle_operation = admission_operation_id
                        if not args.authorize_lifecycle_recovery:
                            progress('QUIESCE', revision)
                            remote_admission(target, key, values['relay_namespace'], 'quiesce',
                                             '--operation', lifecycle_operation, '--target', revision)
                        progress('DRAIN', revision)
                        if args.authorize_lifecycle_recovery:
                            state = remote_admission(target, key, values['relay_namespace'], 'status',
                                                     '--operation', lifecycle_operation)
                            require(state['phase'] == 'recovery-required' and not state['active']
                                    and not state['unknown'], 'lifecycle-recovery-drain-unproven')
                            remote_admission(target, key, values['relay_namespace'], 'recovery-target',
                                             '--operation', lifecycle_operation, '--target', revision)
                        else:
                            remote_admission(target, key, values['relay_namespace'], 'drain',
                                             '--operation', lifecycle_operation, '--timeout', '1800')
                        remote_admission(target, key, values['relay_namespace'], 'phase',
                                         '--operation', lifecycle_operation, '--phase', 'applying')
                        progress('APPLY', revision)
                    if install_flow:
                        # Re-observe under the host mutex; a read-only report is
                        # never itself a destructive or installation capability.
                        observed = remote_inventory(target, key, config)
                        require(not observed['blockers'], 'inventory-changed-before-install')
                        if args.phase == 'reinstall':
                            from clean_reinstall import remote_action
                            retired = remote_action(target, key, config, revision, observed,
                                                    action='decommission', guard=guard)
                            values['relay_clean_reinstall_journal_sha256'] = retired['journalSha256']
                            inventory['all']['children']['relay']['hosts'][target['host']].update(values)
                            (work / 'inventory.json').write_text(json.dumps(inventory))
                    returncode = run_backend(argv, BACKEND, env, log, guard)
                    if args.phase == 'upgrade' or install_flow:
                        log.flush()
                        apply_evidence = Path(log_name).read_text()
                        require(returncode == 0 and 'failed=0' in apply_evidence,
                                f'{args.phase}-apply-failed;log={log_name};next=diagnose-operation-before-retry')
                        require(f'PRODUCTION_APPLY_VALIDATED={revision}' in apply_evidence,
                                args.phase + '-final-runtime-proof')
                        require(f'RELAY_INSTALLED_REVISION={revision};consumer={consumer_revision};' in apply_evidence,
                                args.phase + '-installed-identity-proof')
                        if args.phase == 'upgrade':
                            require(f'RELAY_UPGRADE_ACTIVATION_VALIDATED={revision}' in apply_evidence,
                                    'upgrade-same-operation-activation-proof')
                        # Bootstrap/reinstall keep their independent qualification
                        # check; ordinary upgrades already establish final proof.
                    if install_flow:
                        # Keep the existing host apply mutex held across the
                        # independent read-only check. No new recovery ledger:
                        # apply retains its normal durable operation semantics.
                        values['relay_production_operation_phase'] = 'post-check'
                        values['relay_upgrade_requested'] = False
                        inventory['all']['children']['relay']['hosts'][target['host']].update(values)
                        (work / 'inventory.json').write_text(json.dumps(inventory))
                        offset = len(apply_evidence)
                        returncode = run_backend([*argv, '--check'], BACKEND, env, log, guard)
                        log.flush()
                        checked = Path(log_name).read_text()[offset:]
                        require(returncode == 0 and 'failed=0' in checked,
                                f'{args.phase}-post-check-failed;log={log_name};next=diagnose-operation-before-retry')
                        require(not re.search(r'changed=[1-9][0-9]*', checked), args.phase + '-post-check-drift')
                        require(f'RELAY_INSTALLED_REVISION={revision};consumer={consumer_revision};' in checked,
                                args.phase + '-post-check-installed-identity-proof')
                        if args.phase == 'reinstall':
                            remote_action(target, key, config, revision, observed, action='complete', guard=guard)
                    if args.local_lifecycle and args.phase in ['apply', 'upgrade']:
                        log.flush()
                        require(returncode == 0
                                and f'RELAY_UPGRADE_ACTIVATION_VALIDATED={revision}' in Path(log_name).read_text(),
                                'lifecycle-same-operation-activation-proof')
                    if lifecycle_operation:
                        require(guard is not None and guard.poll() is None, 'lifecycle-host-lock-lost')
                        progress('ACTIVATE/VERIFY', revision)
                        remote_admission(target, key, values['relay_namespace'], 'phase',
                                         '--operation', lifecycle_operation, '--phase', 'verified', '--revision', revision)
                        progress('RESUME', revision)
                        remote_admission(target, key, values['relay_namespace'], 'resume', '--operation', lifecycle_operation)
                        progress('OPEN', revision)
                except Exception:
                    if lifecycle_operation:
                        try:
                            remote_admission(target, key, values['relay_namespace'], 'phase',
                                '--operation', lifecycle_operation, '--phase', 'recovery-required')
                        except Exception:
                            pass  # the last durable state remains closed
                    raise
                finally:
                    if guard is not None:
                        guard.stdin.close()
                        require(guard.wait(timeout=30) == 0, 'host-operation-guard-final-check;inspect-before-retry')
            log.flush()
            evidence = Path(log_name).read_text()
            if returncode:
                raise RuntimeError(f'BACKEND_FAILED;phase={args.phase};log={log_name};next=diagnose-operation-before-retry')
            require('failed=0' in evidence, 'backend-recap')
            if args.phase == 'tls-check':
                require(f'TLS_BOOTSTRAP_CHECK=PASS;head={revision}' in evidence, 'tls-check-proof')
            if args.phase in ['tls-prepare', 'tls-dry-run', 'tls-issue']:
                require(f'TLS_BOOTSTRAP_RESULT=PASS;phase={values["relay_tls_phase"]};head={revision}' in evidence,
                        'tls-bootstrap-proof')
            for role in ['reviewer', 'writer', 'codex']:
                if args.phase == role + '-credentials':
                    require(f'{role.upper()}_CREDENTIAL_STAGE=PASS;head={revision}' in evidence,
                            role + '-credential-proof')
            if args.phase == 'post-check':
                require(not re.search(r'changed=[1-9][0-9]*', evidence), 'post-check-drift')
            if args.phase == 'general-runner-enable':
                require(f'GENERAL_RUNNER_VALIDATED={revision};phase=general-runner-enable;' in evidence, 'general-runner-proof')
            if args.phase == 'check':
                if ('PRODUCTION_RECOVERY_CLASSIFICATION=' in evidence
                        or 'PRODUCTION_RECONCILIATION_STATE=RECOVERY_REQUIRED' in evidence):
                    raise RuntimeError(f'recovery-requires-disposition;log={log_name}')
                if not re.search(r'changed=[1-9][0-9]*', evidence):
                    require(f'PRODUCTION_CHECK_VALIDATED={revision};state=stable-no-op;recovery=none' in evidence, 'final-check-proof')
            if args.stale_apply_shape:
                require(f'PRODUCTION_BOOTSTRAP_DISPOSITION_PASS={revision}' in evidence, 'bootstrap-disposition-proof')
            if args.phase == 'apply':
                require(f'PRODUCTION_APPLY_VALIDATED={revision}' in evidence, 'final-runtime-proof')
            if args.phase in ['apply', 'upgrade', 'post-check', 'bootstrap', 'reinstall']:
                require(f'RELAY_INSTALLED_REVISION={revision};consumer={consumer_revision};' in evidence, 'installed-identity-proof')
                previous = re.search(r'RELAY_INSTALLED_REVISION=[0-9a-f]{40};consumer=[0-9a-f]{40};previous=([a-z0-9]+)', evidence)
                require(previous is not None, 'previous-revision-proof')
                print(f'installed_revision={revision}\nprevious_revision={previous[1]}\nRELAY_INSTALL_RESULT=PASS')
            if args.phase == 'upgrade':
                print(f'RELAY_UPGRADE_RESULT=PASS;installed={revision};projection={revision};verification=same-operation')
            if args.local_lifecycle:
                print(f'RELAY_LIFECYCLE_VERIFIED={revision}')
            if install_flow:
                print(f'RELAY_BOOTSTRAP_RESULT=PASS;phase={args.phase};installed={revision};post_check=clean;activation=owner-required')
            if args.local_reconcile:
                require(f'PRODUCTION_LIFECYCLE_PRESERVED={revision};activation=owner-after-job' in evidence, 'local-live-lifecycle')
                # Checkout mode retains the consumer workflow receipt ABI;
                # installed mode binds both revisions and reports the product SHA.
                receipt_head = revision if args.expected_installed_head else consumer_revision
                print(f'PRODUCTION_APPLY_VALIDATED={receipt_head}')
                print(f'PRODUCTION_LIFECYCLE_PRESERVED={receipt_head};activation=owner-after-job')
            print(f'RELAY_DEPLOYMENT_RESULT=PASS;phase={args.phase};elapsed_seconds={int(time.monotonic()-started)};log={log_name}')
        finally:
            os.close(lock)


if __name__ == '__main__':
    try:
        run(arguments())
    except (ValueError, OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, RuntimeError) as error:
        # Avoid dumping subprocess output or a full consumer/environment input.
        message = str(error) if isinstance(error, (ValueError, RuntimeError)) else type(error).__name__
        print('RELAY_DEPLOYMENT_BLOCKED=' + message, file=sys.stderr)
        sys.exit(1)
