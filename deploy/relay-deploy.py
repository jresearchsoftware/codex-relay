#!/usr/bin/env python3
"""Relay's owner-operated Debian deployment entrypoint (backend is private)."""
import argparse
from contextlib import ExitStack
from types import SimpleNamespace
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import time
import uuid

sys.dont_write_bytecode = True
from config import load, loads, compile_inputs, require, selector, deployment_repository, unique_object
from git_source_locator import expected_locator, resume_receipt

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'deploy/ansible'
from ansible_transport import connection_vars, backend_environment, hold_target, run_target
PHASES = {'check': 'site.yml', 'apply': 'site.yml', 'upgrade': 'site.yml', 'post-check': 'site.yml',
          'inventory': None, 'bootstrap': 'site.yml', 'reinstall': 'site.yml',
          'reinstall-recover': None,
          'workflow-project': None, 'workflow-verify': None,
          'runner-register': None,
          'diagnose': 'relay-production-diagnostic.yml', 'activate': 'relay-reviewer-activation.yml',
          'runner-enable': 'relay-production-runner-enable.yml',
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


def committed_projection(config, revision, source_root, consumer_root, consumer_revision, repository=None):
    """Bind derived workflow bytes to the frozen consumer Git commit as well.

    A clean status excludes ignored files; ignored/untracked projections are
    proposals and cannot establish the reviewed consumer installation binding.
    """
    from workflow_projection import MANIFEST, render, verify
    manifest = verify(config, revision, source_root, consumer_root, repository)
    files = {**render(config, revision, source_root, repository),
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
            'reviewerSourceTreeSha256': digest('reviewer', 'contracts/src/github-authority-v1.json', 'contracts/src/github-authority-v4.json'),
            'reviewerBuildInputsTreeSha256': digest('deploy/ansible/group_vars/all.yml', 'deploy/ansible/site.yml',
                'deploy/ansible/roles/relay_base', 'deploy/ansible/roles/relay_preflight',
                'deploy/ansible/roles/relay_artifacts', 'deploy/ansible/roles/relay_runtime',
                'deploy/ansible/roles/relay_nginx', 'deploy/ansible/roles/relay_docker_nginx')}


def root_owned(path):
    for entry in [path, *path.parents]:
        metadata = entry.lstat()
        require(metadata.st_uid == 0 and not stat.S_ISLNK(metadata.st_mode)
                and not metadata.st_mode & 0o022, 'protected-local-input')


def resume_configuration(config, config_raw, revision, install_root):
    """Verify installed provenance before retaining its original Git evidence."""
    from installed_config import verify, read_protected
    source = Path(install_root) / 'releases' / revision / 'reviewed-source'
    git_mode = config['environment']['localApply'].get('source') == 'git'
    installed, digest, consumer_revision = verify(
        source, revision, **({'require_local_apply': False} if git_mode else {}))
    receipt = None
    if git_mode:
        require(installed == config, 'git-resume-installed-config-binding')
        manifest = json.loads(read_protected(source.parent / 'artifact-manifest.json', {0o640, 0o600})[0],
                              object_pairs_hook=unique_object)
        receipt = resume_receipt(config, revision, manifest, digest, config_raw)
    return consumer_revision, receipt


def readonly_consumer_revision(report, config, revision, receipt, guard, pool_guard):
    """Retain protected target provenance only for an unchanged Git installation.

    The existing inventory transport reads the configured target, including SSH
    targets. No controller-local installed path or caller-selected SHA is used.
    """
    require(guard is not None and guard.poll() is None
            and ('generalRunnerPool' not in config['consumer']
                 or pool_guard is not None and pool_guard.poll() is None),
            'intent-readonly-host-lock-unproven')
    installed = report.get('installed', {})
    require(config['environment']['localApply'].get('source') == 'git'
            and not report.get('blockers') and installed.get('status') == 'present'
            and installed.get('revision') == revision and receipt.get('product_sha') == revision
            and installed.get('gitConfigReceipt') == receipt
            and report.get('configuration', {}).get('status') == 'equivalent',
            'intent-readonly-installed-binding-unproven')
    consumer_revision = installed.get('consumerRevision')
    require(isinstance(consumer_revision, str) and re.fullmatch('[0-9a-f]{40}', consumer_revision),
            'intent-readonly-consumer-provenance-unproven')
    return consumer_revision


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
    return hold_target(target, key, remote, 'BOOTSTRAP_GUARD_READY')


def apply_guard(target, key, namespace):
    # The same reviewed stdlib-only lock implementation runs on the target for
    # an owner apply and locally for the installed helper. No credential or
    # user-selected command is passed to the holder.
    source = (ROOT / 'deploy/deployment_lock.py').read_text()
    remote = ['/usr/bin/python3', '-I', '-c', source,
              '/var/lib/' + namespace + '-deployment.lock']
    return hold_target(target, key, remote, 'DEPLOYMENT_LOCK_READY')


def remote_admission(target, key, namespace, *arguments):
    remote = ['/opt/' + namespace + '/relay-admission', *arguments]
    result = run_target(target, key, remote, timeout=1860)
    require(result.returncode == 0, 'trusted-admission-operation-failed;inspect-before-recovery')
    return json.loads(result.stdout)


def run_backend(argv, cwd, env, log, guard=None, extra_guard=None):
    process = subprocess.Popen(argv, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT)
    started = time.monotonic()
    next_progress = started + 30
    try:
        while process.poll() is None:
            if time.monotonic() >= next_progress:
                print(f'RELAY_DEPLOYMENT_PROGRESS=backend-running;elapsed_seconds={int(time.monotonic()-started)}', flush=True)
                next_progress = time.monotonic() + 30
            if any(holder is not None and holder.poll() is not None for holder in [guard, extra_guard]):
                raise RuntimeError('host-operation-guard-lost;inspect-before-retry')
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
        if any(holder is not None and holder.poll() is not None for holder in [guard, extra_guard]):
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
    # Reject the retired credential-bearing interface without argparse echoing
    # a supplied ephemeral token as part of an unknown-argument diagnostic.
    require(not any(value.split('=', 1)[0] == '--general-runner-registration-token'
                    for value in sys.argv[1:]), 'retired-general-runner-interface')
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', required=True, type=Path)
    p.add_argument('--connection', choices=['ssh', 'local'],
                   help='Ansible connection override; preserves the exact deployment configuration binding')
    p.add_argument('--phase', choices=[*PHASES, 'validate', 'install', 'owner-lifecycle-bootstrap'], required=True)
    p.add_argument('--authorize-owner-lifecycle-bootstrap', action='store_true',
                   help='Refresh only the fixed Git recovery transport from accepted source; local root only')
    p.add_argument('--requested-revision', help='selector already resolved by the trusted acquisition/bootstrap')
    p.add_argument('--resolved-revision', help='exact acquisition result; must equal this clean checkout')
    p.add_argument('--consumer-root', type=Path, help='consumer Git checkout when durable config is stored separately')
    p.add_argument('--repository', help='explicit configured target for workflow-project or workflow-verify')
    p.add_argument('--authorize-upgrade', action='store_true')
    p.add_argument('--authorize-workflow-projection', action='store_true')
    p.add_argument('--authorize-bootstrap', action='store_true', help='install after inventory and consumer workflow review')
    p.add_argument('--authorize-reinstall', action='store_true', help='retire proven managed runtime and install the exact target')
    p.add_argument('--authorize-reinstall-recovery', action='store_true',
                   help='Safely archive a diagnosed failed reinstall without retargeting its journal')
    p.add_argument('--reinstall-recovery-target', help='Exact target of the retained failed reinstall')
    p.add_argument('--projection-output', type=Path, help='optional directory for derived workflow review files')
    p.add_argument('--authorize-runner-register', action='store_true')
    p.add_argument('--runner-registration-token', help='ephemeral bootstrap input for this registration only')
    p.add_argument('--log-root', type=Path, default=Path('/tmp/relay-deployment'))
    p.add_argument('--local-reconcile', action='store_true', help=argparse.SUPPRESS)
    p.add_argument('--local-lifecycle', action='store_true', help=argparse.SUPPRESS)
    p.add_argument('--lifecycle-operation', help=argparse.SUPPRESS)
    p.add_argument('--lifecycle-lock-fd', type=int, help=argparse.SUPPRESS)
    p.add_argument('--authorize-lifecycle-recovery', action='store_true',
                   help='After diagnosis/disposition, recover or roll back a retained quiesced operation')
    p.add_argument('--lifecycle-recovery-operation', help='Exact retained admission operation UUID')
    p.add_argument('--predispatch-recovery-request', type=Path,
                   help='Root-private exact pre-dispatch finalization request; use the crash-safe same-install Writer bridge')
    p.add_argument('--authorize-install-recovery', action='store_true',
                   help='Continue one diagnosed operation using this independently accepted controller and Git pair')
    p.add_argument('--install-recovery-operation', help='Exact original operation UUID; install recovery only')
    p.add_argument('--install-recovery-target', help='Immutable original product target; install recovery only')
    p.add_argument('--retained-runner-maintenance', type=Path,
                   help='Owner declaration of exact existing Runner identities for bounded install recovery')
    p.add_argument('--continue-install-recovery', action='store_true',
                   help='Continue a proved reserved Begin or consumer-publication frontier with its frozen Git pair')
    p.add_argument('--consumer-revision', help=argparse.SUPPRESS)
    p.add_argument('--expected-installed-head', help=argparse.SUPPRESS)
    p.add_argument('--git-config-receipt', type=Path, help=argparse.SUPPRESS)
    p.add_argument('--workflow-consumer-revision', help=argparse.SUPPRESS)
    p.add_argument('--authorize-apply-recovery', action='store_true',
                   help='Owner-authorized matching installed-config apply recovery after diagnosis')
    p.add_argument('--authorize-reviewer-activation', action='store_true')
    p.add_argument('--authorize-runner-enable', action='store_true')
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
    if args.phase == 'owner-lifecycle-bootstrap':
        require(args.authorize_owner_lifecycle_bootstrap and args.connection == 'local',
                'explicit-local-owner-lifecycle-bootstrap-required')
        require(not any(value for key, value in vars(args).items()
                        if key.startswith('authorize_') and key != 'authorize_owner_lifecycle_bootstrap'),
                'bootstrap-authorization-flags-invalid')
        identity = source_identity(ROOT)
        require(args.resolved_revision == identity['revision'], 'bootstrap-exact-source-required')
        from owner_lifecycle_bootstrap import bootstrap
        result = bootstrap(load(args.config, ROOT), identity['revision'])
        print('RELAY_OWNER_LIFECYCLE_BOOTSTRAPPED=' + result + ';services=unchanged;admission=unchanged')
        return
    require(not getattr(args, 'authorize_owner_lifecycle_bootstrap', False), 'bootstrap-interface-only')
    if args.phase == 'install':
        from intent_install import run as install
        return install(args, run, ROOT, source_identity(ROOT), guard_factory=apply_guard)
    require(not getattr(args, 'continue_install_recovery', False), 'install-continuation-interface-only')
    require(getattr(args, 'retained_runner_maintenance', None) is None or getattr(args, 'intent_install', False),
            'runner-maintenance-install-only')
    intent_install = getattr(args, 'intent_install', False)
    require(getattr(args, 'predispatch_recovery_request', None) is None
            or intent_install and args.phase in ['apply', 'upgrade'] and os.geteuid() == 0,
            'predispatch-recovery-install-root-only')
    bounded_binding = getattr(args, '_intent_bounded_recovery', None)
    require(bounded_binding is None or intent_install and args.authorize_lifecycle_recovery,
            'bounded-recovery-interface-only')
    require(not getattr(args, 'authorize_install_recovery', False)
            and getattr(args, 'install_recovery_operation', None) is None
            and getattr(args, 'install_recovery_target', None) is None, 'install-recovery-interface-only')
    inherited_guard = getattr(args, '_intent_host_guard', None)
    inherited_pool_guard = getattr(args, '_intent_pool_guard', None)
    require(inherited_guard is None or (intent_install and inherited_guard.poll() is None
            and not args.local_reconcile and not args.local_lifecycle), 'intent-host-lock-unproven')
    require(inherited_pool_guard is None or (inherited_guard is not None
            and inherited_pool_guard.poll() is None), 'intent-pool-lock-unproven')
    require(getattr(args, 'git_config_receipt', None) is None, 'git-receipt-install-only')
    require(getattr(args, 'repository', None) is None or args.phase in ['workflow-project', 'workflow-verify'],
            'repository-projection-only')
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
    require(args.runner_registration_token is None or args.phase == 'runner-register', 'runner-token-phase')
    require(not args.local_reconcile or args.consumer_root is None, 'local-consumer-root-forbidden')
    require(not args.local_lifecycle or (os.geteuid() == 0 and not args.local_reconcile
            and args.phase in ['apply', 'upgrade', 'post-check']
            and re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', args.lifecycle_operation or '')
            and args.lifecycle_lock_fd is not None), 'protected-local-lifecycle')
    require(args.local_lifecycle or (args.lifecycle_operation is None and args.lifecycle_lock_fd is None),
            'lifecycle-internal-options')
    require(args.authorize_lifecycle_recovery == bool(args.lifecycle_recovery_operation)
            and (not args.authorize_lifecycle_recovery or (args.phase in ['upgrade', 'reinstall'] and not args.local_lifecycle
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
        if intent_install:
            raw = config_path.read_bytes()
            require(hashlib.sha256(raw).hexdigest() == args.git_intent['config_sha256'], 'frozen-git-config-changed')
            config = loads(raw.decode('utf-8'), ROOT)
        else:
            config = load(config_path, ROOT)
    if 'generalRunnerPool' in config['consumer']:
        # Bind new managed target policy in the same order that the protected
        # canonical snapshot and installed reader produce, including derived slots.
        config = loads(json.dumps(config, sort_keys=True, separators=(',', ':'), ensure_ascii=False), ROOT)
    pool_reinstall = args.phase == 'reinstall' and 'generalRunnerPool' in config['consumer']
    require(not (args.phase == 'reinstall' and args.authorize_lifecycle_recovery) or pool_reinstall,
            'pool-reinstall-recovery-only')
    values = compile_inputs(config)
    deployment_contract = {}
    contract_path = ROOT / 'deploy/installation-contract.json'
    if contract_path.exists():
        from intent_install import contract
        deployment_contract = contract(json.loads(contract_path.read_text()))
    require(not intent_install or deployment_contract, 'intent-deployment-contract-required')
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
    # Git resume proves the installed pair below. Receiving-repository workflow
    # publication is independent of restoring that qualified host installation.
    git_resume = (args.local_lifecycle and args.phase == 'post-check'
                  and values['relay_local_apply_source'] == 'git')
    git_readonly = (intent_install and args.phase == 'post-check'
                    and values['relay_local_apply_source'] == 'git')
    if not intent_install and not git_resume and (args.phase in ['workflow-project', 'workflow-verify', 'upgrade'] or args.local_lifecycle or (args.phase == 'apply' and not args.local_reconcile)):
        from workflow_projection import project, verify
        if args.phase == 'workflow-project':
            project(config, revision, ROOT, consumer_root, getattr(args, 'repository', None))
        else:
            committed_projection(config, revision, ROOT, consumer_root, consumer_revision,
                                 getattr(args, 'repository', None))
        print(f'RELAY_WORKFLOW_PROJECTION=PASS;revision={revision};consumer={consumer_revision}', flush=True)
        if args.phase in ['workflow-project', 'workflow-verify']:
            print(f'RELAY_DEPLOYMENT_RESULT=PASS;phase={args.phase}')
            return
    if args.local_lifecycle and args.phase == 'post-check':
        # A later graceful resume verifies installed configuration and keeps
        # the installed manifest's original provenance.
        consumer_revision, original_receipt = resume_configuration(
            config, config_path.read_bytes(), revision, values['relay_install_root'])
        if original_receipt is not None:
            args.git_intent = original_receipt
    values['relay_deployment_source'] = expected_locator(
        config, revision, getattr(args, 'git_intent', None),
        config_path.read_bytes() if getattr(args, 'git_intent', None) else None)
    target = dict(config['target'])
    if getattr(args, 'connection', None) is not None:
        target['connection'] = args.connection
    key = Path(target.get('identityFile', '/unused-local-identity')).expanduser()
    if not args.local_reconcile and not args.local_lifecycle and target.get('connection', 'ssh') == 'ssh':
        require(isinstance(target.get('identityFile'), str)
                and isinstance(target.get('identityFingerprint'), str), 'ssh-identity-required')
        require(key.is_file() and not key.is_symlink(), 'operator-key')
        require(command(['ssh-keygen', '-lf', key]).split()[1] == target['identityFingerprint'], 'operator-key-identity')
        known = command(['ssh-keygen', '-F', target['host']])
        fingerprints = command(['ssh-keygen', '-lf', '-'], input=known).splitlines()
        require(any(row.split()[1] == target['hostFingerprint'] for row in fingerprints), 'host-identity')
    if not args.local_reconcile and not args.local_lifecycle:
        from ansible_transport import qualify_target
        qualify_target(target, key)
    install_flow = args.phase in ['bootstrap', 'reinstall']
    pool_reinstall_proof = None
    if args.phase == 'inventory' or install_flow:
        from inventory import remote_inventory
        observed = remote_inventory(target, key, config, **({'git_desired': True} if intent_install else {}))
        print('RELAY_INVENTORY=' + json.dumps(observed, sort_keys=True), flush=True)
        if args.phase == 'inventory':
            print('RELAY_DEPLOYMENT_RESULT=PASS;phase=inventory;authority=read-only', flush=True)
            return
        if pool_reinstall and args.authorize_lifecycle_recovery:
            from clean_reinstall import remote_action, continuation_inventory
            pool_reinstall_proof = remote_action(target, key, config, revision, action='continuation',
                                                operation_id=args.lifecycle_recovery_operation)
            observed = continuation_inventory(observed, pool_reinstall_proof)
        if intent_install:
            from intent_install import strategy_inventory
            observed = strategy_inventory(observed)
        require(not observed['blockers'], 'inventory-blocked;inspect-reported-prerequisites')
        if not intent_install:
            from workflow_projection import _manifest, prepare, render
            target_manifest = _manifest(config, ROOT, render(config, revision, ROOT))
            proposal_key = hashlib.sha256(json.dumps(
                target_manifest, sort_keys=True).encode()).hexdigest()[:16]
            output = args.projection_output or (args.log_root / ('workflows-' + revision + '-' +
                      deployment_repository(config).replace('/', '-') + '-' + proposal_key))
            proposal = prepare(config, revision, ROOT, consumer_root, output)
            print('RELAY_BOOTSTRAP_PROJECTION=' + json.dumps(proposal, sort_keys=True), flush=True)
            if proposal['state'] != 'ready':
                print('RELAY_DEPLOYMENT_PENDING=WORKFLOW_REVIEW_REQUIRED;target_unchanged=true', flush=True)
                return
            committed_projection(config, revision, ROOT, consumer_root, consumer_revision)
        if args.phase == 'bootstrap' and not args.authorize_bootstrap:
            print('RELAY_DEPLOYMENT_PENDING=INSTALL_AUTHORIZATION_REQUIRED;flag=--authorize-bootstrap;target_unchanged=true')
            return
    lifecycle_required = (args.phase == 'upgrade' or (intent_install and args.phase == 'apply'
                          and args.intent_expected_installed_revision != 'none'))
    admission_operation_id = (args.lifecycle_operation if args.local_lifecycle else
        (args.lifecycle_recovery_operation or str(uuid.uuid4()) if lifecycle_required or pool_reinstall else ''))
    values.update({
        'relay_review_root': str(ROOT), 'relay_source_identity': identity,
        'relay_requested_revision': requested, 'relay_consumer_revision': consumer_revision,
        'relay_deployment_profile': 'production',
        'relay_production_operation_phase': 'apply' if args.phase == 'upgrade' or install_flow else args.phase,
        'relay_upgrade_requested': args.phase == 'upgrade',
        'relay_upgrade_lifecycle_managed': lifecycle_required or (args.local_lifecycle and args.phase == 'apply'),
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
        'relay_git_desired_state': intent_install,
        # Reinstall independently proves the old identity under the host mutex,
        # then retires current before the fresh backend starts.
        'relay_intent_expected_installed_revision': ('none' if intent_install and args.phase == 'reinstall'
            else getattr(args, 'intent_expected_installed_revision', '')),
        'relay_git_config_receipt': getattr(args, 'git_intent', {}),
        'relay_bounded_recovery_binding': bounded_binding or {},
        'relay_retained_reviewer_config_adoption': bool((bounded_binding or {}).get('runnerMaintenance')),
        'relay_deployment_contract': deployment_contract,
        'relay_installation_state': getattr(args, '_intent_installation_state', {}),
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
    if intent_install:
        values['relay_consumer_config_path'] = values['relay_config_root'] + '/consumer.json'
        if pool_reinstall_proof is not None and not pool_reinstall_proof['completed']:
            values['relay_clean_reinstall_journal_sha256'] = pool_reinstall_proof['journalSha256']
    if getattr(args, '_intent_fresh_bootstrap', False):
        require(intent_install and args.phase == 'bootstrap'
                and args.intent_expected_installed_revision == 'none' and inherited_guard is not None,
                'intent-fresh-bootstrap-unproven')
        # Install inactive runtime first, then the existing bounded credential
        # phases. The same frozen config is enforced by the following apply.
        values['relay_codex_token_required'] = False
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
    if args.phase == 'runner-register':
        from runner_registration import register_runner
        token = args.runner_registration_token
        guard = ingress_guard(target, key, values, revision)
        try:
            def registration_poll():
                for holder in [guard, inherited_guard, inherited_pool_guard]:
                    if holder is not None and holder.poll() is not None:
                        return holder.poll()
                return None
            proof = register_runner(target, key, values, revision, token,
                                    SimpleNamespace(poll=registration_poll))
        finally:
            guard.stdin.close()
            require(guard.wait(timeout=30) == 0, 'host-operation-guard-final-check;inspect-before-retry')
        print(proof)
        print(f'RELAY_DEPLOYMENT_RESULT=PASS;phase={args.phase}')
        return
    args.log_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    log_fd, log_name = tempfile.mkstemp(prefix=f'relay-{revision[:12]}-{args.phase}-', suffix='.log', dir=args.log_root)
    if intent_install:
        args._intent_log_path = log_name
    consumer_label = 'receiving_revision' if git_readonly else 'consumer_revision'
    print(f'requested_revision={requested}\nresolved_revision={revision}\n{consumer_label}={consumer_revision}', flush=True)
    lock_name = hashlib.sha256((target['host'] + values['relay_install_root']).encode()).hexdigest()[:24]
    lock_path = (Path(values['relay_state_root']) if args.local_reconcile else Path(tempfile.gettempdir())) / ('relay-deploy-' + lock_name + '.lock')
    with os.fdopen(log_fd, 'w') as log, tempfile.TemporaryDirectory(prefix='relay-deploy-') as temporary:
        work = Path(temporary)
        lock = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            require(os.fstat(lock).st_uid == os.getuid() and not os.fstat(lock).st_mode & 0o077, 'invocation-lock')
            if args.phase in ['apply', 'upgrade', 'bootstrap', 'reinstall', 'reinstall-recover', 'activate', 'runner-enable', 'stale-dispose', *BOOTSTRAP_MUTATIONS]:
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
                **connection_vars(target, key, local=args.local_reconcile or args.local_lifecycle)}}}}}}
            (work / 'inventory.json').write_text(json.dumps(inventory))
            env = backend_environment()
            playbook = ('relay-production-bootstrap-disposition.yml' if args.stale_apply_shape else PHASES[args.phase])
            argv = ['ansible-playbook', '-i', str(work / 'inventory.json'), str(BACKEND / playbook),
                    '--limit', target['host']]
            if args.phase in ['check', 'post-check', 'tls-check']:
                argv += ['--check']
            started = time.monotonic()
            log.write(f'requested_revision={requested};resolved_revision={revision};{consumer_label}={consumer_revision}\n')
            log.flush()
            with ExitStack() as host_locks:
                guard = inherited_guard
                pool_guard = inherited_pool_guard
                owns_guard = False
                if args.phase in ['apply', 'upgrade', 'bootstrap', 'reinstall']:
                    if args.local_lifecycle:
                        pass  # inherited, validated host lock covers the complete lifecycle
                    elif args.local_reconcile:
                        from deployment_lock import acquire
                        host_locks.enter_context(acquire('/var/lib/' + values['relay_namespace'] + '-deployment.lock'))
                    elif guard is None:
                        guard = apply_guard(target, key, values['relay_namespace'])
                        owns_guard = True
                elif args.phase == 'ingress':
                    if inherited_guard is None:
                        guard = ingress_guard(target, key, values, revision)
                        owns_guard = True
                    else:
                        ingress_holder = ingress_guard(target, key, values, revision)
                        host_locks.callback(lambda: (ingress_holder.stdin.close(),
                            require(ingress_holder.wait(timeout=30) == 0, 'ingress-operation-guard-final-check')))
                        # Ingress has no pool operation; retain both its own
                        # installed operation lock and the inherited host lock.
                        def ingress_poll():
                            for holder in [ingress_holder, inherited_pool_guard]:
                                if holder is not None and holder.poll() is not None:
                                    return holder.poll()
                            return None
                        pool_guard = SimpleNamespace(poll=ingress_poll)
                if ('generalRunnerPool' in config['consumer']
                        and args.phase in ['apply', 'upgrade', 'bootstrap', 'reinstall']):
                    pool_lock_namespace = 'codex-relay-pool-' + config['environment']['generalRunner']['name']
                    if args.local_reconcile or args.local_lifecycle:
                        from deployment_lock import acquire
                        host_locks.enter_context(acquire('/var/lib/' + pool_lock_namespace + '-deployment.lock'))
                    elif pool_guard is None:
                        pool_guard = apply_guard(target, key, pool_lock_namespace)
                        def release_pool_guard():
                            pool_guard.stdin.close()
                            require(pool_guard.wait(timeout=30) == 0, 'pool-host-lock-final-check;inspect-before-retry')
                        host_locks.callback(release_pool_guard)
                try:
                    lifecycle_operation = None
                    preparation = None
                    pool_preflight_proof = None
                    def clear_preparation_inventory():
                        for name in ['relay_intent_writer_lock_lease', 'relay_intent_admission_prefix',
                                     'relay_intent_staged_release', 'relay_intent_stage_root',
                                     'relay_intent_stage_operation', 'relay_intent_stage_source_only',
                                     'relay_intent_stage_reinstall', 'relay_intent_preflight_consumer_path',
                                     'relay_intent_preflight_baseline_digest', 'relay_intent_preflight_claim_root',
                                     'relay_intent_preflight_installed_revision']:
                            values.pop(name, None)
                            inventory['all']['children']['relay']['hosts'][target['host']].pop(name, None)
                        (work / 'inventory.json').write_text(json.dumps(inventory))
                    if intent_install:
                        # The first observation chose a strategy. Revalidate its
                        # installation under the same host mutex before even a
                        # quiesce/reservation may change protected state.
                        from inventory import remote_inventory
                        locked_inventory = remote_inventory(target, key, config, git_desired=True)
                        locked_installed = locked_inventory['installed']
                        locked_revision = (locked_installed.get('revision')
                            if locked_installed.get('status') == 'present' else 'none'
                            if locked_installed.get('status') == 'missing' else 'invalid')
                        from intent_install import strategy_inventory
                        intent_recovery = getattr(args, '_intent_recovery_proof', None)
                        if bounded_binding is not None:
                            from bounded_recovery import remote_probe as bounded_probe
                            from install_recovery import provisional_inventory
                            bounded = bounded_probe(target, key, config, bounded_binding, guard, pool_guard)
                            require(bounded == args._intent_bounded_recovery_proof,
                                    'bounded-recovery-evidence-changed')
                            locked_inventory = provisional_inventory(locked_inventory)
                        elif intent_recovery is not None:
                            from install_recovery import revalidate as revalidate_recovery, proved_inventory
                            require(args.authorize_lifecycle_recovery
                                    and args.lifecycle_recovery_operation == intent_recovery['operationId'],
                                    'intent-recovery-arguments-changed')
                            repeated = revalidate_recovery(intent_recovery, target, key, config, revision,
                                args.intent_expected_installed_revision, guard, pool_guard)
                            locked_inventory = proved_inventory(locked_inventory, repeated, revision,
                                args.intent_expected_installed_revision)
                        require(not strategy_inventory(locked_inventory)['blockers']
                                and locked_revision == args.intent_expected_installed_revision,
                                'intent-installation-changed-before-reservation')
                    if ('generalRunnerPool' in config['consumer']
                            and args.phase in ['apply', 'upgrade', 'bootstrap', 'reinstall']):
                        from managed_pool_transport import preflight_pool
                        pool_preflight_proof = preflight_pool(target, key, config, guard,
                            local=args.local_reconcile or args.local_lifecycle, extra_guard=pool_guard)
                    if intent_install and args.phase in ['apply', 'upgrade', 'bootstrap', 'reinstall']:
                        from install_preflight import PreparedInstall
                        stage_operation = admission_operation_id or str(uuid.uuid4())
                        preparation = PreparedInstall(target, key, values, identity, stage_operation,
                            local=args.local_reconcile or args.local_lifecycle, reinstall=args.phase == 'reinstall')
                        created_stage = preparation.create()
                        if isinstance(created_stage, dict) and created_stage.get('preservedPrevious') is True:
                            print('RELAY_INSTALL_PREPARATION=previous-stage-preserved;operation=' + stage_operation, flush=True)
                        args._intent_failure_stage = 'preflight-source'
                        values.update(relay_intent_stage_root=preparation.stage,
                            relay_intent_stage_operation=stage_operation, relay_intent_stage_source_only=True,
                            relay_intent_stage_reinstall=args.phase == 'reinstall',
                            relay_intent_preflight_installed_revision=args.intent_expected_installed_revision)
                        def preflight_play(name):
                            inventory['all']['children']['relay']['hosts'][target['host']].update(values)
                            (work / 'inventory.json').write_text(json.dumps(inventory))
                            offset = len(Path(log_name).read_text())
                            code = run_backend([*argv[:3], str(BACKEND / name), *argv[4:]],
                                BACKEND, env, log, guard, pool_guard)
                            log.flush()
                            proof = Path(log_name).read_text()[offset:]
                            if code != 0 or 'failed=0' not in proof:
                                codes = re.findall(r'\b(?:BOUNDED_RECOVERY|INTENT|HOST|RELAY|PRODUCTION)_[A-Z_]{2,100}\b', proof)
                                error = RuntimeError(codes[-1] if codes else 'INSTALL_PREFLIGHT_' +
                                    ('STAGING_FAILED' if name == 'relay-intent-stage.yml' else 'COMPATIBILITY_FAILED'))
                                error.next_action = ('Inspect the named preflight prerequisite in the private installer log; '
                                    'correct it through the existing version or owner-supported package/credential procedure '
                                    'while the old entrypoint remains available. Retry the same frozen Git pair.')
                                raise error
                        if args.intent_expected_installed_revision == 'none':
                            args._intent_failure_stage = 'fresh-product-prerequisites'
                            args._intent_product_prerequisites = True
                            preflight_play('relay-intent-prerequisites.yml')
                            args._intent_failure_stage = 'preflight-source'
                        preflight_play('relay-intent-stage.yml')
                        preparation.desired()
                        args._intent_failure_stage = 'preflight-history'
                        if pool_reinstall_proof is not None and not pool_reinstall_proof['completed']:
                            preparation.consumer_retained(pool_reinstall_proof)
                        elif args.intent_expected_installed_revision != 'none':
                            preparation.consumer()
                        if preparation.initial is not None:
                            if args.phase == 'reinstall' and preparation.initial['consumerChange']:
                                error = RuntimeError('INSTALL_PREFLIGHT_REINSTALL_CONSUMER_REBIND_UNSUPPORTED')
                                error.next_action = ('Keep the installed entrypoint available. This protected replacement '
                                    'cannot rebind retained admission history through the fresh-install consumer path. '
                                    'Use a compatible installed lifecycle transition when its contract permits it, '
                                    'or obtain a separately qualified replacement preserving the original gate and history; '
                                    'do not edit protected attempts or clear admission state.')
                                raise error
                        if bounded_binding is not None:
                            # The original gate is already closed. Reprove all
                            # manual/live effects with the qualified controller,
                            # preserve original evidence, then explicitly bind
                            # the SAME operation to its owner-selected final pair.
                            preparation.lock_writer()
                            args._intent_mutation_started = True
                            args._intent_bounded_recovery_proof = preparation.bounded_recovery(
                                config, bounded_binding, args._intent_bounded_recovery_proof)
                            gate = preparation.execute([*preparation.admission_prefix(), 'recovery-target',
                                '--operation', admission_operation_id, '--target', revision])
                            require(gate['operationId'] == admission_operation_id and gate['target'] == revision
                                    and gate['phase'] == 'recovery-required', 'bounded-recovery-target-unproven')
                            preparation.release_writer()
                        # The owning read-only checks and real staging run before
                        # quiesce; a dry run cannot replace build/load proof.
                        args._intent_failure_stage = 'preflight-host-policy'
                        backend_expected = values['relay_intent_expected_installed_revision']
                        values['relay_intent_expected_installed_revision'] = args.intent_expected_installed_revision
                        if preparation.initial is not None and preparation.initial['consumerRestoreRequired']:
                            values['relay_intent_preflight_consumer_path'] = preparation.initial['effectiveConsumerPath']
                            values['relay_intent_preflight_baseline_digest'] = preparation.initial['baselineDigest']
                            values['relay_intent_preflight_claim_root'] = preparation.initial['claimRoot']
                        preflight_play('relay-intent-preflight.yml')
                        for name in ['relay_intent_preflight_consumer_path', 'relay_intent_preflight_baseline_digest',
                                     'relay_intent_preflight_claim_root']:
                            values.pop(name, None)
                            inventory['all']['children']['relay']['hosts'][target['host']].pop(name, None)
                        values['relay_intent_expected_installed_revision'] = backend_expected
                        inventory['all']['children']['relay']['hosts'][target['host']]['relay_intent_expected_installed_revision'] = backend_expected
                        preparation.host()
                        # A transient signed-repository/hash failure must be
                        # discovered while the known-good runtime and its gate
                        # still retain their original state. No package installs
                        # or live APT-list changes occur in this acquisition proof.
                        args._intent_failure_stage = 'prerequisite-acquisition'
                        preflight_play('relay-intent-apt-preflight.yml')
                        if preparation.initial is not None and not args.authorize_lifecycle_recovery:
                            preparation.capture()
                        values['relay_intent_stage_source_only'] = False
                        args._intent_failure_stage = 'candidate-stage'
                        preflight_play('relay-intent-stage.yml')
                        preparation.verify_stage()
                        values['relay_intent_staged_release'] = preparation.stage + '/release'
                        inventory['all']['children']['relay']['hosts'][target['host']].update(values)
                        (work / 'inventory.json').write_text(json.dumps(inventory))
                        print('RELAY_INSTALL_PREFLIGHT=prepared;operation=' + stage_operation, flush=True)
                    if (intent_install and (lifecycle_required or pool_reinstall)
                            and not args.authorize_lifecycle_recovery):
                        from consumer_drift import prepare as restore_consumer_drift
                        previous_mutation = getattr(args, '_intent_mutation_started', False)
                        args._intent_mutation_started = True
                        # The helper may quiesce before a transport failure. Keep
                        # that SAME UUID for diagnosis and normal continuation.
                        lifecycle_operation = admission_operation_id
                        restored = restore_consumer_drift(target, key, config, revision,
                            admission_operation_id, guard, pool_guard)
                        if restored['status'] == 'restored':
                            require(restored['operationId'] == admission_operation_id,
                                    'consumer-drift-operation-mismatch')
                            print('RELAY_INSTALL_CONSUMER_DRIFT=restored;operation=' + admission_operation_id,
                                  flush=True)
                        else:
                            args._intent_mutation_started = previous_mutation
                            lifecycle_operation = None
                    if intent_install:
                        # An invalid effective consumer was provisional strategy
                        # input only. The target proof must restore/authenticate it
                        # before the ordinary resource/preflight/backend checks.
                        allowed_stage_operation = None
                        if preparation is not None and not preparation.reinstall:
                            allowed_stage_operation = preparation.operation
                        strict_inventory = remote_inventory(target, key, config, git_desired=True,
                            allowed_stage_operation=allowed_stage_operation)
                        strict_installed = strict_inventory['installed']
                        strict_revision = (strict_installed.get('revision')
                            if strict_installed.get('status') == 'present' else 'none'
                            if strict_installed.get('status') == 'missing' else 'invalid')
                        if bounded_binding is not None:
                            strict_inventory = provisional_inventory(strict_inventory)
                        elif getattr(args, '_intent_recovery_proof', None) is not None:
                            strict_inventory = proved_inventory(strict_inventory, repeated, revision,
                                args.intent_expected_installed_revision)
                        require(not strict_inventory['blockers']
                                and strict_revision == args.intent_expected_installed_revision,
                                'intent-installation-changed-before-reservation')
                        if git_readonly:
                            original_consumer = readonly_consumer_revision(locked_inventory, config, revision,
                                args.git_intent, guard, pool_guard)
                            repeated_consumer = readonly_consumer_revision(strict_inventory, config, revision,
                                args.git_intent, guard, pool_guard)
                            require(original_consumer == repeated_consumer,
                                    'intent-readonly-consumer-provenance-changed')
                            print('RELAY_INSTALL_CONSUMER_PROVENANCE=installed:' + original_consumer
                                  + ';receiving:' + consumer_revision, flush=True)
                            log.write('consumer_revision=' + original_consumer
                                      + ';receiving_revision=' + consumer_revision + '\n')
                            consumer_revision = original_consumer
                            values['relay_consumer_revision'] = consumer_revision
                            inventory['all']['children']['relay']['hosts'][target['host']].update(values)
                            (work / 'inventory.json').write_text(json.dumps(inventory))
                    completed_pool_reinstall = False
                    retirement_report = None
                    if lifecycle_required and not args.local_lifecycle:
                        from lifecycle import progress
                        lifecycle_operation = admission_operation_id
                        if intent_install:
                            args._intent_mutation_started = True
                        if not args.authorize_lifecycle_recovery:
                            progress('QUIESCE', revision)
                            target_source_arguments = (['--target-source', preparation.source]
                                if preparation is not None and 'predispatch-retention-v1' in
                                locked_inventory.get('installed', {}).get('deploymentContract', {}).get('capabilities', []) else [])
                            remote_admission(target, key, values['relay_namespace'], 'quiesce',
                                             '--operation', lifecycle_operation, '--target', revision, *target_source_arguments)
                        progress('DRAIN', revision)
                        if args.authorize_lifecycle_recovery:
                            if bounded_binding is not None:
                                preparation.lock_writer()
                                preparation.bounded_recovery(config, bounded_binding,
                                    args._intent_bounded_recovery_proof, action='revalidate')
                                def recovery_admission(*arguments):
                                    return preparation.execute([*preparation.admission_prefix(), *arguments])
                            else:
                                def recovery_admission(*arguments):
                                    return remote_admission(target, key, values['relay_namespace'], *arguments)
                            state = recovery_admission('status', '--operation', lifecycle_operation)
                            require(state['phase'] == 'recovery-required' and not state['active']
                                    and not state['unknown'], 'lifecycle-recovery-drain-unproven')
                            recovery_admission('recovery-target', '--operation', lifecycle_operation, '--target', revision)
                        else:
                            if preparation is not None:
                                bridge_request_path = getattr(args, 'predispatch_recovery_request', None)
                                if bridge_request_path is not None:
                                    from installed_config import read_protected
                                    raw, _ = read_protected(bridge_request_path, {0o600}, group=0)
                                    require(len(raw) <= 4096, 'predispatch-recovery-request-size')
                                    recovery_request = json.loads(raw)
                                    values['relay_intent_admission_prefix'] = preparation.admission_prefix()
                                    proof = preparation.bridge_predispatch(recovery_request,
                                        lambda: preflight_play('relay-predispatch-bridge-snapshot.yml'))
                                    require(proof['operationId'] == lifecycle_operation and proof['target'] == revision,
                                            'predispatch-bridge-install-binding')
                                    values['relay_intent_expected_installed_revision'] = revision
                                    args.intent_expected_installed_revision = revision
                                    inventory['all']['children']['relay']['hosts'][target['host']].update(values)
                                    (work / 'inventory.json').write_text(json.dumps(inventory))
                                else:
                                    preparation.drain_staged()
                                # Recheck under the same lock and retain it until
                                # cutover; the old reader may not understand a
                                # valid candidate administrative receipt.
                                if preparation.holder is None:
                                    preparation.lock_writer()
                                if bridge_request_path is None:
                                    locked_drain = preparation.execute([*preparation.admission_prefix(), 'drain-check',
                                        '--operation', lifecycle_operation])
                                    require(locked_drain.get('drained') is True, 'staged-drain-changed-before-cutover')
                            else:
                                remote_admission(target, key, values['relay_namespace'], 'drain',
                                                 '--operation', lifecycle_operation, '--timeout', '1800')
                        if bounded_binding is not None or (preparation is not None and preparation.holder is not None):
                            if bounded_binding is None:
                                def recovery_admission(*arguments):
                                    return preparation.execute([*preparation.admission_prefix(), *arguments])
                            recovery_admission('phase', '--operation', lifecycle_operation, '--phase', 'applying')
                        else:
                            remote_admission(target, key, values['relay_namespace'], 'phase',
                                             '--operation', lifecycle_operation, '--phase', 'applying')
                        progress('APPLY', revision)
                    elif pool_reinstall:
                        from lifecycle import progress
                        from clean_reinstall import remote_action, continuation_inventory
                        lifecycle_operation = admission_operation_id
                        if intent_install:
                            args._intent_mutation_started = True
                        if args.authorize_lifecycle_recovery:
                            pool_reinstall_proof = remote_action(target, key, config, revision, action='continue',
                                guard=guard, operation_id=lifecycle_operation)
                            completed_pool_reinstall = pool_reinstall_proof['completed']
                            values['relay_clean_reinstall_journal_sha256'] = pool_reinstall_proof['journalSha256']
                        else:
                            progress('QUIESCE', revision)
                            remote_admission(target, key, values['relay_namespace'], 'quiesce',
                                             '--operation', lifecycle_operation, '--target', revision)
                            progress('DRAIN', revision)
                            remote_admission(target, key, values['relay_namespace'], 'drain',
                                             '--operation', lifecycle_operation, '--timeout', '1800')
                            remote_admission(target, key, values['relay_namespace'], 'phase',
                                             '--operation', lifecycle_operation, '--phase', 'applying')
                        progress('APPLY' if not completed_pool_reinstall else 'VERIFY-RETAINED-REINSTALL', revision)
                    if install_flow:
                        # Re-observe under the host mutex; a read-only report is
                        # never itself a destructive or installation capability.
                        if intent_install:
                            observed = remote_inventory(target, key, config, git_desired=True,
                                allowed_stage_operation=allowed_stage_operation)
                        else:
                            observed = remote_inventory(target, key, config)
                        if pool_reinstall_proof is not None:
                            observed = continuation_inventory(observed, pool_reinstall_proof)
                        require(not observed['blockers'], 'inventory-changed-before-install')
                    if preparation is not None:
                        args._intent_failure_stage = 'final-revalidation'
                        fresh_preparation = preparation.initial is None
                        if preparation.retained_proof is not None:
                            repeated_retirement = remote_action(target, key, config, revision,
                                action='continuation', guard=guard, operation_id=lifecycle_operation)
                            require(repeated_retirement == preparation.retained_proof,
                                    'INSTALL_PREFLIGHT_RETAINED_REPLACEMENT_CHANGED')
                        if pool_preflight_proof is not None:
                            repeated_pool = preflight_pool(target, key, config, guard,
                                local=args.local_reconcile or args.local_lifecycle, extra_guard=pool_guard)
                            require(str(repeated_pool) == str(pool_preflight_proof),
                                    'INSTALL_PREFLIGHT_POOL_POLICY_CHANGED')
                        if not fresh_preparation and preparation.holder is None:
                            preparation.lock_writer()
                        preparation.final(fresh=fresh_preparation)
                        require(hashlib.sha256(config_path.read_bytes()).hexdigest() == args.git_intent['config_sha256']
                                and source_identity(ROOT) == identity, 'frozen-git-inputs-changed-before-cutover')
                        # Keep the existing Writer kernel lock across the final
                        # evidence check and every active installation effect.
                        if not fresh_preparation:
                            values.update(relay_intent_writer_lock_lease=preparation.lease_path,
                                relay_intent_admission_prefix=preparation.admission_prefix())
                        inventory['all']['children']['relay']['hosts'][target['host']].update(values)
                        (work / 'inventory.json').write_text(json.dumps(inventory))
                        preparation.cutover_started = True
                        args._intent_failure_stage = 'controlled-cutover'
                    if intent_install and args.phase in ['apply', 'upgrade', 'bootstrap', 'reinstall']:
                        args._intent_mutation_started = True
                        from intent_install import prepare_target
                        if prepare_target(target, key, config, revision, guard):
                            print('RELAY_INSTALL_HARDENING=legacy-operation-directory;mode=0750', flush=True)
                    if install_flow:
                        if args.phase == 'reinstall':
                            from clean_reinstall import remote_action
                            if pool_reinstall_proof is None:
                                # Protected replacement retains the same consumer
                                # digest (proved above). Its owning retirement
                                # helper takes its original publication lock for
                                # pool admission observations. Release this lease
                                # for that bounded operation, then reacquire before
                                # installing any candidate helpers/configuration.
                                if preparation is not None:
                                    preparation.release_writer()
                                retired = remote_action(target, key, config, revision, observed,
                                    action='decommission', guard=guard,
                                    **({'git_desired': True} if intent_install else {}),
                                    **({'operation_id': lifecycle_operation} if pool_reinstall else {}))
                                values['relay_clean_reinstall_journal_sha256'] = retired['journalSha256']
                                retirement_report = observed
                                if preparation is not None and preparation.initial is not None:
                                    preparation.lock_writer()
                                    preparation.after_retirement()
                                    require(hashlib.sha256(config_path.read_bytes()).hexdigest() == args.git_intent['config_sha256']
                                            and source_identity(ROOT) == identity, 'frozen-git-inputs-changed-after-retirement')
                            else:
                                retirement_report = {**observed, 'installed': {'status': 'present',
                                    'revision': pool_reinstall_proof['sourceRevision']}}
                            inventory['all']['children']['relay']['hosts'][target['host']].update(values)
                            (work / 'inventory.json').write_text(json.dumps(inventory))
                    def cutover_poll():
                        for holder in [pool_guard, preparation.holder if preparation is not None else None]:
                            if holder is not None and holder.poll() is not None:
                                return holder.poll()
                        return None
                    if preparation is not None and preparation.holder is not None:
                        returncode = None if completed_pool_reinstall else run_backend(argv, BACKEND, env, log, guard,
                            SimpleNamespace(poll=cutover_poll))
                    else:
                        returncode = None if completed_pool_reinstall else run_backend(argv, BACKEND, env, log, guard, pool_guard)
                    if preparation is not None:
                        preparation.release_writer()
                        args._intent_failure_stage = 'activation-verification'
                        # Subsequent native postchecks use the ordinary fixed
                        # installed helper after the publication mutex releases.
                        clear_preparation_inventory()
                    if (returncode == 0 and 'generalRunnerPool' in config['consumer']
                            and args.phase in ['apply', 'upgrade', 'bootstrap', 'reinstall']
                            and not completed_pool_reinstall and not getattr(args, '_intent_defer_pool_reconcile', False)):
                        from managed_pool_transport import reconcile_pool
                        proof = reconcile_pool(target, key, config, revision, guard,
                                               local=args.local_reconcile or args.local_lifecycle,
                                               extra_guard=pool_guard)
                        log.write(proof + '\n')
                        log.flush()
                        print(proof, flush=True)
                    if (lifecycle_required or install_flow) and not completed_pool_reinstall:
                        log.flush()
                        apply_evidence = Path(log_name).read_text()
                        require(returncode == 0 and 'failed=0' in apply_evidence,
                                f'{args.phase}-apply-failed;log={log_name};next=diagnose-operation-before-retry')
                        require(f'PRODUCTION_APPLY_VALIDATED={revision}' in apply_evidence,
                                args.phase + '-final-runtime-proof')
                        require(f'RELAY_INSTALLED_REVISION={revision};consumer={consumer_revision};' in apply_evidence,
                                args.phase + '-installed-identity-proof')
                        if lifecycle_required:
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
                        if intent_install:
                            values['relay_intent_expected_installed_revision'] = revision
                        inventory['all']['children']['relay']['hosts'][target['host']].update(values)
                        (work / 'inventory.json').write_text(json.dumps(inventory))
                        offset = len(Path(log_name).read_text())
                        returncode = run_backend([*argv, '--check'], BACKEND, env, log, guard, pool_guard)
                        log.flush()
                        checked = Path(log_name).read_text()[offset:]
                        require(returncode == 0 and 'failed=0' in checked,
                                f'{args.phase}-post-check-failed;log={log_name};next=diagnose-operation-before-retry')
                        require(not re.search(r'changed=[1-9][0-9]*', checked), args.phase + '-post-check-drift')
                        require(f'RELAY_INSTALLED_REVISION={revision};consumer={consumer_revision};' in checked,
                                args.phase + '-post-check-installed-identity-proof')
                        if args.phase == 'reinstall' and not pool_reinstall:
                            remote_action(target, key, config, revision, observed, action='complete', guard=guard)
                    if args.local_lifecycle and args.phase in ['apply', 'upgrade']:
                        log.flush()
                        require(returncode == 0
                                and f'RELAY_UPGRADE_ACTIVATION_VALIDATED={revision}' in Path(log_name).read_text(),
                                'lifecycle-same-operation-activation-proof')
                    if lifecycle_operation:
                        require(guard is not None and guard.poll() is None, 'lifecycle-host-lock-lost')
                        if bounded_binding is not None:
                            from intent_install import readback
                            final_inventory = remote_inventory(target, key, config, git_desired=True)
                            readback(final_inventory, revision, args.git_intent)
                        progress('ACTIVATE/VERIFY', revision)
                        remote_admission(target, key, values['relay_namespace'], 'phase',
                                         '--operation', lifecycle_operation, '--phase', 'verified', '--revision', revision)
                        if bounded_binding is not None:
                            preparation.lock_writer()
                            try:
                                preparation.bounded_recovery(config, bounded_binding,
                                    args._intent_bounded_recovery_proof, action='finalize')
                            finally:
                                preparation.release_writer()
                        if pool_reinstall and not completed_pool_reinstall:
                            remote_action(target, key, config, revision, retirement_report, action='complete',
                                          guard=guard, operation_id=lifecycle_operation)
                        progress('RESUME', revision)
                        remote_admission(target, key, values['relay_namespace'], 'resume', '--operation', lifecycle_operation)
                        progress('OPEN', revision)
                except Exception:
                    restored_old = False
                    if (preparation is not None and preparation.captured and not preparation.cutover_started
                            and lifecycle_operation and not args.authorize_lifecycle_recovery):
                        try:
                            aborted = preparation.abort()
                            require(aborted['status'] == 'old-open-restored', 'INSTALL_PREFLIGHT_ABORT_UNPROVEN')
                            args._intent_mutation_started = False
                            args._intent_old_availability_restored = True
                            restored_old = True
                            print('RELAY_INSTALL_PREFLIGHT=aborted;old-availability=verified;operation=' + lifecycle_operation,
                                  flush=True)
                        except Exception:
                            print('RELAY_INSTALL_PREFLIGHT_ABORT=unproven;retain-original-operation;inspect-before-recovery',
                                  flush=True)
                    if preparation is not None:
                        preparation.release_writer()
                    if lifecycle_operation and not restored_old:
                        try:
                            remote_admission(target, key, values['relay_namespace'], 'phase',
                                '--operation', lifecycle_operation, '--phase', 'recovery-required')
                        except Exception:
                            pass  # the last durable state remains closed
                    raise
                finally:
                    if guard is not None and owns_guard:
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
