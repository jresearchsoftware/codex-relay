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
import signal
import stat
import subprocess
import sys
import tempfile
import time
import threading
import uuid

sys.dont_write_bytecode = True
from config import load, loads, compile_inputs, require, selector, deployment_repository, unique_object, InvalidConfig
from git_source_locator import expected_locator, resume_receipt
from lifecycle import (progress, report_failure, public_log_reference, start_failure_observation,
                       stop_failure_observation, print_terminal_failure, observe_failure_state,
                       observe_admission_call, observe_admission_result, observe_backend_start,
                       observe_target_mutation, admission_failure_receipt, LifecycleCheckError)

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'deploy/ansible'
from ansible_transport import connection_vars, backend_environment, hold_target, run_target
from timing import public_ansible_timing
PHASES = {'check': 'site.yml', 'apply': 'site.yml', 'upgrade': 'site.yml', 'post-check': 'site.yml',
          'inventory': None, 'bootstrap': 'site.yml', 'reinstall': 'site.yml',
          'reinstall-recover': None,
          'workflow-project': None, 'workflow-verify': None, 'workflow-deployment-project': None,
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
    from lifecycle import failure_reporting_source
    source = failure_reporting_source() + (ROOT / 'deploy/deployment_lock.py').read_text()
    remote = ['/usr/bin/python3', '-I', '-c', source,
              '/var/lib/' + namespace + '-deployment.lock']
    return hold_target(target, key, remote, 'DEPLOYMENT_LOCK_READY')


def remote_admission(target, key, namespace, *arguments):
    remote = ['/opt/' + namespace + '/relay-admission', *arguments]
    observe_admission_call(arguments[0])
    result = run_target(target, key, remote, timeout=1860,
                        **({'progress': True} if arguments[0] == 'drain' else {}))
    if result.returncode:
        receipt = admission_failure_receipt(result.stderr)
        code = receipt.get('code', 'trusted-admission-operation-failed')
        raise LifecycleCheckError(code + ';inspect-before-recovery') from subprocess.CalledProcessError(
            result.returncode, 'fixed-admission-operation', output=result.stdout, stderr=result.stderr)
    decoded = json.loads(result.stdout)
    action = arguments[0]
    phase = arguments[arguments.index('--phase') + 1] if '--phase' in arguments else None
    if isinstance(decoded, dict) and (action != 'drain' or decoded.get('drained') is True):
        observe_admission_result(action, phase)
    return decoded


def release_guard(guard):
    """Retain the primary operation failure if releasing its holder also fails."""
    failing = sys.exc_info()[0] is not None
    try:
        guard.stdin.close()
        require(guard.wait(timeout=30) == 0, 'host-operation-guard-final-check;inspect-before-retry')
    except Exception as error:
        report_failure(error, 'guard-release')
        if not failing:
            raise
        print('RELAY_DEPLOYMENT_WARNING=host-operation-guard-final-check-unproven;primary-failure-preserved;inspect-before-retry',
              file=sys.stderr, flush=True)


def run_backend(argv, cwd, env, log, guard=None, extra_guard=None):
    log.flush()
    offset = os.fstat(log.fileno()).st_size
    if '--check' not in argv:
        observe_target_mutation()
    env = os.environ.copy() if env is None else dict(env)
    env['ANSIBLE_CALLBACK_PLUGINS'] = str(BACKEND / 'callback_plugins')
    env['ANSIBLE_CALLBACKS_ENABLED'] = 'relay_timing'
    # The lifecycle UUID is shared across backend invocations; a standalone
    # invocation receives one correlation ID without creating lifecycle authority.
    operation = env.get('RELAY_TIMING_OPERATION', '')
    if not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', operation):
        operation = str(uuid.uuid4())
    env['RELAY_TIMING_OPERATION'] = operation
    invocation = str(uuid.uuid4())
    env['RELAY_TIMING_INVOCATION'] = invocation
    process = subprocess.Popen(argv, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    observe_backend_start()
    started = time.monotonic()
    next_progress = started + 30
    # The existing private Ansible log remains the primary diagnostic source.
    # Only fixed source-owned phase names are projected into the Actions log.
    pending = b''
    dependency = 'ansible-playbook'
    dependencies = {
        'relay_apt_metadata': 'apt-package-metadata', 'relay_artifacts': 'release-artifacts',
        'relay_codex_runtime': 'codex-package-and-runtime', 'relay_runtime': 'reviewer-build-and-runtime',
        'relay_runner': 'production-runner-package', 'relay_general_runner': 'general-runner-package',
        'relay_controller': 'controller-entrypoints',
        'Try-restart the previously active Reviewer and production dependency': 'reviewer-activation',
        'Wait for the previously active Reviewer listener after activation': 'reviewer-listener',
        'Require previously active services to become healthy in the same operation': 'service-health',
        'Prove active Reviewer and production processes adopted the installed transition': 'runtime-verification',
        'Require preserved activation intent and healthy previously active components': 'runtime-verification',
    }
    print('RELAY_DEPLOYMENT_PROGRESS=backend;dependency=ansible-playbook;state=started', flush=True)
    def observe():
        nonlocal offset, pending, dependency, next_progress
        log.flush()
        # Read through a separate descriptor: the backend's shared write offset
        # must never move while observing progress. Bound each observation.
        with open(log.name if isinstance(log.name, str) else '/proc/self/fd/' + str(log.fileno()), 'rb') as reader:
            reader.seek(offset)
            chunk = reader.read(65536)
        offset += len(chunk)
        pending += chunk
        while b'\n' in pending:
            raw, pending = pending.split(b'\n', 1)
            if len(raw) > 4096:
                continue
            line = raw.decode('utf-8', errors='replace')
            if public_ansible_timing(line, operation, invocation):
                print(line, flush=True)
            match = re.fullmatch(r'TASK \[([^\]]+)\] \*+', line)
            if match:
                name = match[1].split(' : ', 1)[0]
                current = dependencies.get(name)
                if current and current != dependency:
                    dependency = current
                    print(f'RELAY_DEPLOYMENT_PROGRESS=backend;dependency={dependency};state=running;elapsed_seconds={int(time.monotonic()-started)}', flush=True)
                    next_progress = time.monotonic() + 30
        if len(pending) > 4096:
            pending = b'oversized:'
    try:
        while process.poll() is None:
            observe()
            if time.monotonic() >= next_progress:
                print(f'RELAY_DEPLOYMENT_PROGRESS=backend-running;dependency={dependency};elapsed_seconds={int(time.monotonic()-started)}', flush=True)
                next_progress = time.monotonic() + 30
            if any(holder is not None and holder.poll() is not None for holder in [guard, extra_guard]):
                raise RuntimeError('host-operation-guard-lost;inspect-before-retry')
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
        if any(holder is not None and holder.poll() is not None for holder in [guard, extra_guard]):
            raise RuntimeError('host-operation-guard-lost;inspect-before-retry')
        observe()
        observe_failure_state(boundary='backend-returned', backend=dependency, backend_exit=process.returncode)
        print(f'RELAY_ANSIBLE_TIMING=operation={operation};invocation={invocation};kind=backend;wall_ms={int((time.monotonic()-started)*1000)}', flush=True)
        print(f'RELAY_DEPLOYMENT_PROGRESS=backend;dependency={dependency};state={"completed" if process.returncode == 0 else "failed"};exit={process.returncode};elapsed_seconds={int(time.monotonic()-started)}', flush=True)
        return process.returncode
    finally:
        primary = sys.exc_info()[1]
        if primary is not None:
            observe_failure_state(backend=dependency, backend_exit=process.returncode)
        try:
            if process.poll() is None or primary is not None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=10)
                # Parent exit alone does not stop an ignoring descendant in
                # this invocation's own controller group. Remote effects remain
                # uncertain and are reconciled through the original operation.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        except Exception as secondary:
            report_failure(secondary, 'backend-cleanup', private_log=log.name if isinstance(log.name, str) else None)
            if primary is None:
                raise
            print('RELAY_DEPLOYMENT_WARNING=backend-cleanup-unproven;primary-failure-preserved;inspect-before-retry',
                  file=sys.stderr, flush=True)


def arguments():
    # Reject the retired credential-bearing interface without argparse echoing
    # a supplied ephemeral token as part of an unknown-argument diagnostic.
    require(not any(value.split('=', 1)[0] == '--general-runner-registration-token'
                    for value in sys.argv[1:]), 'retired-general-runner-interface')
    class DiagnosticParser(argparse.ArgumentParser):
        def error(self, message):
            report_failure(ValueError(message), 'deployment-arguments')
            # argparse messages can contain raw argument values. Only the class
            # of parse failure reaches the ordinary command output.
            category = 'invalid choice' if 'invalid choice:' in message else (
                'unrecognized arguments' if message.startswith('unrecognized arguments:') else 'invalid or missing arguments')
            super().error(category + '. Check the selected operation and deployment options with --help.')

    p = DiagnosticParser(description=__doc__)
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
    p.add_argument('--projection-output', type=Path,
                   help='review directory; required for workflow-deployment-project, optional for bootstrap/reinstall')
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
    p.add_argument('--native-reservation-attempt', type=int, help=argparse.SUPPRESS)
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


def run(args, *, reservation_token=None):
    if not hasattr(args, '_apply_preparation_started'):
        args._apply_preparation_started = time.monotonic()
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
        config = load(args.config, ROOT)
        observe_target_mutation()
        result = bootstrap(config, identity['revision'])
        print('RELAY_OWNER_LIFECYCLE_BOOTSTRAPPED=' + result + ';services=unchanged;admission=unchanged')
        return
    require(not getattr(args, 'authorize_owner_lifecycle_bootstrap', False), 'bootstrap-interface-only')
    if args.phase == 'install':
        from intent_install import run as install
        attempt = getattr(args, 'native_reservation_attempt', None)
        if attempt is not None:
            require(os.geteuid() == 0 and args.connection == 'local'
                    and getattr(args, 'git_config_receipt', None) is not None
                    and not args.authorize_install_recovery and 0 < attempt <= 9007199254740991,
                    'native-runner-reservation-interface-unproven')
            from git_intent import read_token
            reservation_token = read_token(sys.stdin.buffer)
            def run_install_phase(inner):
                return run(inner, reservation_token=reservation_token)
        else:
            run_install_phase = run
        return install(args, run_install_phase, ROOT, source_identity(ROOT), guard_factory=apply_guard)
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
    require(args.authorize_workflow_projection == (args.phase in ['workflow-project', 'workflow-deployment-project']),
            'explicit-workflow-projection')
    require(not args.authorize_bootstrap or args.phase == 'bootstrap', 'explicit-bootstrap')
    require(args.authorize_reinstall == (args.phase == 'reinstall'), 'explicit-reinstall')
    require(args.authorize_reinstall_recovery == (args.phase == 'reinstall-recover')
            and (bool(re.fullmatch('[0-9a-f]{40}', args.reinstall_recovery_target or ''))
                 if args.authorize_reinstall_recovery else args.reinstall_recovery_target is None)
            and not (args.authorize_reinstall_recovery and args.local_reconcile), 'explicit-reinstall-recovery')
    require(args.projection_output is None or args.phase in ['bootstrap', 'reinstall', 'workflow-deployment-project'],
            'projection-output-phase')
    require(args.phase != 'workflow-deployment-project'
            or args.projection_output is not None and args.consumer_root is None,
            'deployment-projection-output-required;omit-consumer-root')
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
            if args.phase in ['workflow-project', 'workflow-deployment-project']:
                # Hash precisely the bytes validated and used, not a later read
                # or a normalized serialization. Callers correlate this with
                # their successful Apply's immutable desired-config snapshot.
                projection_config_raw = config_path.read_bytes()
                config = loads(projection_config_raw.decode('utf-8'), ROOT)
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
        if args.phase in ['inventory', 'workflow-deployment-project']:
            consumer_revision = None
        else:
            consumer_root = (args.consumer_root.absolute() if args.consumer_root else
                             Path(git(config_path.parent, 'rev-parse', '--show-toplevel')))
            consumer_revision = clean_git(consumer_root)
    require(selector(requested), 'requested-revision')
    require(args.resolved_revision is None or args.resolved_revision == identity['revision'], 'resolved-revision-mismatch')
    require(args.phase in ['inventory', 'workflow-deployment-project']
            or re.fullmatch('[0-9a-f]{40}', consumer_revision or ''), 'consumer-revision')
    revision = identity['revision']
    if args.phase in ['upgrade', 'workflow-project', 'workflow-verify', 'workflow-deployment-project',
                      'inventory', 'bootstrap', 'reinstall', 'reinstall-recover']:
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
    if args.phase == 'workflow-deployment-project':
        from workflow_projection import project_deployment
        result = project_deployment(config, revision, ROOT, args.projection_output)
        result.update(schemaVersion=1, kind='deployment',
                      repository=config['environment']['localApply']['repository'],
                      productRevision=revision, sourceRepository=config['source']['repository'],
                      configSha256=hashlib.sha256(projection_config_raw).hexdigest())
        print('RELAY_WORKFLOW_PROJECTION_RESULT=' + json.dumps(result, sort_keys=True), flush=True)
        print(f'RELAY_DEPLOYMENT_RESULT=PASS;phase={args.phase}')
        return
    if not intent_install and not git_resume and (args.phase in ['workflow-project', 'workflow-verify', 'upgrade'] or args.local_lifecycle or (args.phase == 'apply' and not args.local_reconcile)):
        from workflow_projection import project_result, verify
        if args.phase == 'workflow-project':
            result = project_result(config, revision, ROOT, consumer_root, getattr(args, 'repository', None))
            result.pop('manifest')
            result.update(schemaVersion=1, kind='consumer',
                          repository=deployment_repository(config, getattr(args, 'repository', None)),
                          productRevision=revision, sourceRepository=config['source']['repository'],
                          configSha256=hashlib.sha256(projection_config_raw).hexdigest(),
                          consumerRevision=consumer_revision)
            print('RELAY_WORKFLOW_PROJECTION_RESULT=' + json.dumps(result, sort_keys=True), flush=True)
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
    observe_failure_state(boundary='configuration', requested=revision)
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
    observe_failure_state(boundary='host-preflight')
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
    planned_pool_maintenance = (lifecycle_required and not args.local_lifecycle
                                and 'generalRunnerPool' in config['consumer']
                                and not args.authorize_lifecycle_recovery)
    reserved_pool = (config['environment']['localApply'].get('poolReservation') == 'same-run-v1'
                     and planned_pool_maintenance)
    workflow_run = None
    if reserved_pool:
        receipt = getattr(args, 'git_intent', None)
        attempt = getattr(args, 'native_reservation_attempt', None)
        require(intent_install and args.connection == 'local' and os.geteuid() == 0
                and reservation_token is not None and type(attempt) is int and attempt > 0
                and isinstance(receipt, dict) and receipt.get('action') == 'apply',
                'native-runner-reservation-required')
        workflow_run = {key: receipt[key] for key in ('config_repository', 'config_sha', 'workflow_run_id')}
        workflow_run['workflow_run_attempt'] = attempt
    admission_operation_id = (args.lifecycle_operation if args.local_lifecycle else
        (args.lifecycle_recovery_operation or str(uuid.uuid4()) if lifecycle_required or pool_reinstall else ''))
    observe_failure_state(operation_id=admission_operation_id, config=consumer_revision if not git_readonly else None)

    def apply_timing(phase, started):
        elapsed_ms = int((time.monotonic() - started) * 1000)
        owner_run = (getattr(args, 'git_intent', None) or {}).get('workflow_run_id') if intent_install else None
        correlation = f';owner_run={owner_run}' if type(owner_run) is int and owner_run > 0 else ''
        print(f'RELAY_APPLY_TIMING=operation={admission_operation_id};phase={phase};wall_ms={elapsed_ms}{correlation}',
              flush=True)
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
            observe_target_mutation()
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
    log_ref = public_log_reference(log_name)
    observe_failure_state(log=log_ref)
    if intent_install:
        args._intent_log_path = log_name
    consumer_label = 'receiving_revision' if git_readonly else 'consumer_revision'
    print(f'requested_revision={requested}\nresolved_revision={revision}\n{consumer_label}={consumer_revision}', flush=True)
    print(f'RELAY_DEPLOYMENT_LOG={log_ref};access=protected;phase={args.phase}', flush=True)
    lock_name = hashlib.sha256((target['host'] + values['relay_install_root']).encode()).hexdigest()[:24]
    lock_path = (Path(values['relay_state_root']) if args.local_reconcile else Path(tempfile.gettempdir())) / ('relay-deploy-' + lock_name + '.lock')
    with os.fdopen(log_fd, 'w') as log, tempfile.TemporaryDirectory(prefix='relay-deploy-') as temporary:
        log.write('protected_log=' + log_name + '\n')
        log.flush()
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
                    observe_target_mutation()
                    recovered = remote_action(target, key, config, args.reinstall_recovery_target,
                                              action='recover', guard=guard)
                    log.write(json.dumps(recovered, sort_keys=True) + '\n')
                    log.flush()
                finally:
                    release_guard(guard)
                print('RELAY_REINSTALL_RECOVERY=' + json.dumps(recovered, sort_keys=True), flush=True)
                print(f'RELAY_DEPLOYMENT_RESULT=PASS;phase=reinstall-recover;controller_revision={revision};log={log_ref}', flush=True)
                return
            if args.phase in ['apply', 'upgrade', 'bootstrap', 'reinstall'] and not args.local_reconcile:
                archive = work / 'source.tar'
                git(ROOT, 'archive', '--format=tar', '--output=' + str(archive), revision)
                values['relay_source_archive'] = str(archive)
            inventory = {'all': {'children': {'relay': {'hosts': {target['host']: {**values,
                **connection_vars(target, key, local=args.local_reconcile or args.local_lifecycle)}}}}}}
            (work / 'inventory.json').write_text(json.dumps(inventory))
            env = backend_environment()
            env['RELAY_TIMING_OPERATION'] = admission_operation_id or str(uuid.uuid4())
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
                    pool_maintenance_started = False
                    pool_drain_completed = False
                    reviewer_pause_pending = False
                    gate_reopened = False
                    preparation = None
                    qualified_local = args.local_reconcile or args.local_lifecycle

                    def pool_maintenance(action):
                        if reserved_pool:
                            from managed_pool_transport import maintain_reserved_pool
                            result = maintain_reserved_pool(config, admission_operation_id, action, guard,
                                                            pool_guard, ROOT, workflow_run, reservation_token)
                        else:
                            from managed_pool_transport import maintain_pool
                            result = maintain_pool(target, key, config, admission_operation_id, action, guard,
                                                   local=qualified_local, extra_guard=pool_guard)
                        for key_name in ['paused', 'stopped', 'preserved', 'ready', 'busy']:
                            require(isinstance(result.get(key_name), list)
                                    and len(result[key_name]) <= 32
                                    and all(re.fullmatch(r'[a-z][a-z0-9-]{0,31}', member)
                                            for member in result[key_name]),
                                    'pool-maintenance-result-unproven')
                        counts = ';'.join(f'{name}={len(result[name])}'
                                          for name in ['paused', 'stopped', 'preserved', 'ready', 'busy'])
                        print(f'RELAY_POOL_MAINTENANCE={action};operation={admission_operation_id};{counts}',
                              flush=True)
                        return result

                    def reviewer_maintenance(*arguments):
                        helper = values['relay_install_root'] + '/relay-reviewer-maintenance'
                        result = run_target(target, key, [helper, *arguments], timeout=330, local=qualified_local)
                        if result.returncode:
                            raise LifecycleCheckError('reviewer-maintenance-unproven') from subprocess.CalledProcessError(
                                result.returncode, 'reviewer-maintenance', output=result.stdout, stderr=result.stderr)
                        status = json.loads(result.stdout)
                        require(isinstance(status, dict) and type(status.get('pid')) is int and status['pid'] > 0,
                                'reviewer-maintenance-status-unproven')
                        return status

                    def resume_reviewer(timeout, *, previous_pid=None):
                        require(guard is not None and guard.poll() is None, 'lifecycle-host-lock-lost')
                        ready = reviewer_maintenance('ready', '--timeout', str(timeout))
                        require(ready.get('ready') is True and (previous_pid is None or ready['pid'] == previous_pid),
                                'reviewer-resume-readiness-unproven')
                        require('operation' in ready and ready['operation'] in (None, admission_operation_id),
                                'reviewer-resume-operation-mismatch')
                        if ready['operation'] is not None or ready.get('writerAccepting') is not True:
                            ready = reviewer_maintenance('resume', '--operation', admission_operation_id)
                        require(ready.get('ready') is True and 'operation' in ready and ready['operation'] is None
                                and ready.get('writerAccepting') is True, 'reviewer-resume-readback-unproven')
                    fast_source = False
                    source_proof = None
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
                    pool_preflight_needed = ('generalRunnerPool' in config['consumer']
                        and args.phase in ['apply', 'upgrade', 'bootstrap', 'reinstall'])
                    defer_pool_preflight = (pool_preflight_needed and intent_install
                        and args.phase == 'upgrade' and not args.authorize_lifecycle_recovery
                        and bounded_binding is None
                        and getattr(args, 'predispatch_recovery_request', None) is None)
                    def check_pool_preflight():
                        from managed_pool_transport import preflight_pool
                        return preflight_pool(target, key, config, guard,
                            local=args.local_reconcile or args.local_lifecycle, extra_guard=pool_guard)
                    if pool_preflight_needed and not defer_pool_preflight:
                        pool_preflight_proof = check_pool_preflight()
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
                        from source_stage import prepare as prepare_source_only
                        if not prepare_source_only(preparation, guard, pool_guard):
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
                        source_reuse = False
                        # The native proof requires the same online listeners
                        # and routing labels before and after promotion.
                        if (args.phase == 'upgrade' and not args.authorize_lifecycle_recovery
                                and not planned_pool_maintenance
                                and bounded_binding is None and preparation.initial is not None
                                and not preparation.initial['consumerChange']
                                and not preparation.initial['consumerRestoreRequired']
                                and getattr(args, 'predispatch_recovery_request', None) is None):
                            args._intent_failure_stage = 'source-reuse-preparation'
                            source_reuse = preparation.prepare_source_reuse(config, guard, pool_guard)
                        if source_reuse:
                            # Retain the same original-operation rollback proof;
                            # nomination and stage writes have not changed live state.
                            preparation.capture()
                        else:
                            # Native nomination already proves the identical pool
                            # predicates in its initial/final/post-effect proofs.
                            # Every ordinary fallback retains both owning checks.
                            if defer_pool_preflight:
                                pool_preflight_proof = check_pool_preflight()
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
                    reviewer_pid = None
                    if lifecycle_required and not args.local_lifecycle and args.authorize_lifecycle_recovery:
                        # An interrupted Apply can leave the component paused while
                        # the service is down. The normal activation proof comes
                        # first; then the authenticated control checks marker ownership.
                        marker = values['relay_config_root'] + '/reviewer-maintenance.json'
                        probe = run_target(target, key, ['/usr/bin/test', '-e', marker, '-o', '-L', marker],
                                           timeout=30, local=qualified_local)
                        require(probe.returncode in (0, 1), 'reviewer-maintenance-record-unproven')
                        reviewer_pause_pending = probe.returncode == 0
                    elif lifecycle_required and not args.local_lifecycle:
                        service = run_target(target, key, ['/usr/bin/systemctl', 'show',
                            values['relay_reviewer_service_name'], '--property=ActiveState', '--value'],
                            timeout=30, local=qualified_local)
                        require(service.returncode == 0 and service.stdout.strip() in {'active', 'inactive'},
                                'reviewer-service-state-unproven')
                        reviewer_active = service.stdout.strip() == 'active'
                        if reviewer_active:
                            probe = run_target(target, key, ['/usr/bin/test', '-x',
                                values['relay_install_root'] + '/relay-reviewer-maintenance'],
                                timeout=30, local=qualified_local)
                            if probe.returncode == 1:
                                socket = run_target(target, key, ['/usr/bin/systemctl', 'show',
                                    values['relay_reviewer_socket_service_name'], '--property=LoadState', '--value'],
                                    timeout=30, local=qualified_local)
                                legacy = run_target(target, key, ['/usr/bin/systemctl', 'show',
                                    values['relay_reviewer_service_name'], '--property=MainPID', '--value'],
                                    timeout=30, local=qualified_local)
                                require(socket.returncode == 0 and socket.stdout.strip() == 'not-found'
                                        and legacy.returncode == 0 and re.fullmatch(r'[1-9][0-9]*', legacy.stdout.strip()),
                                        'reviewer-legacy-identity-unproven')
                                values['relay_reviewer_legacy_pid'] = legacy.stdout.strip()
                                inventory['all']['children']['relay']['hosts'][target['host']].update(values)
                                (work / 'inventory.json').write_text(json.dumps(inventory))
                            else:
                                require(probe.returncode == 0, 'reviewer-maintenance-capability-unproven')
                                reviewer_status = reviewer_maintenance('status')
                                require(reviewer_status.get('ready') is True
                                        and 'operation' in reviewer_status
                                        and reviewer_status['operation'] in (None, admission_operation_id),
                                        'reviewer-activity-boundary-unproven')
                                reviewer_pid = reviewer_status['pid']
                    # Preparation is read-only with respect to serving execution. A
                    # Quickstrike that arrives there still admits and publishes normally.
                    # Withhold native eligibility and finish accepted General jobs before
                    # closing admission, including jobs that already reached their runner.
                    if planned_pool_maintenance:
                        apply_timing('preparation', args._apply_preparation_started)
                        args._intent_failure_stage = 'general-runner-intake'
                        pause_started = time.monotonic()
                        pool_maintenance_started = True
                        observe_target_mutation()
                        if intent_install:
                            args._intent_mutation_started = True
                        pool_maintenance('pause')
                        apply_timing('intake-pause', pause_started)
                        args._intent_failure_stage = 'general-runner-drain'
                        drain_started = time.monotonic()
                        drained = pool_maintenance('drain')
                        if preparation is not None:
                            preparation.stopped_pool_members = frozenset(drained['stopped'])
                        pool_drain_completed = True
                        apply_timing('runner-drain', drain_started)
                    if reviewer_pid is not None:
                        args._intent_failure_stage = 'reviewer-writer-drain'
                        # A failed acknowledgement may follow a durable marker write.
                        reviewer_pause_pending = True
                        observe_target_mutation()
                        if intent_install:
                            args._intent_mutation_started = True
                        reviewer_maintenance('pause-writer', '--operation', admission_operation_id)
                        reviewer_maintenance('wait', '--scope', 'writer', '--timeout', '300')
                    if (intent_install and (lifecycle_required or pool_reinstall)
                            and not args.authorize_lifecycle_recovery):
                        from consumer_drift import prepare as restore_consumer_drift
                        if reserved_pool:
                            pool_maintenance('verify')
                        previous_mutation = getattr(args, '_intent_mutation_started', False)
                        observe_target_mutation()
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
                        if reserved_pool:
                            pool_maintenance('verify')
                        lifecycle_operation = admission_operation_id
                        if not pool_maintenance_started:
                            apply_timing('preparation', args._apply_preparation_started)
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
                    elif pool_reinstall:
                        from clean_reinstall import remote_action, continuation_inventory
                        lifecycle_operation = admission_operation_id
                        if intent_install:
                            args._intent_mutation_started = True
                        if args.authorize_lifecycle_recovery:
                            observe_target_mutation()
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
                            repeated_pool = check_pool_preflight()
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
                    if (intent_install and args.phase in ['apply', 'upgrade', 'bootstrap', 'reinstall']
                            and not (preparation is not None and getattr(preparation, 'source_reuse', False))):
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
                                observe_target_mutation()
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
                    fast_source = preparation is not None and getattr(preparation, 'source_reuse', False)
                    if args.phase in ['apply', 'upgrade', 'bootstrap', 'reinstall'] and not completed_pool_reinstall:
                        observe_target_mutation()
                        progress('APPLY', revision)
                    if fast_source:
                        args._intent_mutation_started = True
                        source_proof = preparation.promote_source_reuse(config, guard, pool_guard)
                        returncode = 0
                        print('RELAY_SOURCE_UPGRADE_VALIDATED=' + revision, flush=True)
                    elif preparation is not None and preparation.holder is not None:
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
                    if returncode == 0 and args.phase in ['apply', 'upgrade', 'bootstrap', 'reinstall']:
                        progress('ACTIVATE/VERIFY', revision)
                    # Expert bootstrap/reinstall materializes an inactive
                    # installation. Pool registration/start belongs to Apply
                    # after the owner's separate Reviewer activation.
                    if (returncode == 0 and 'generalRunnerPool' in config['consumer']
                            and args.phase in ['apply', 'upgrade', 'bootstrap', 'reinstall']
                            and not (install_flow and not intent_install)
                            and not completed_pool_reinstall and not fast_source
                            and not getattr(args, '_intent_defer_pool_reconcile', False)):
                        from managed_pool_transport import reconcile_pool
                        proof = reconcile_pool(target, key, config, revision, guard,
                                               local=args.local_reconcile or args.local_lifecycle,
                                               extra_guard=pool_guard)
                        log.write(proof + '\n')
                        log.flush()
                        print(proof, flush=True)
                    if (lifecycle_required or install_flow) and not completed_pool_reinstall and not fast_source:
                        log.flush()
                        apply_evidence = Path(log_name).read_text()
                        require(returncode == 0 and 'failed=0' in apply_evidence,
                                f'{args.phase}-apply-failed;log={log_ref};next=diagnose-operation-before-retry')
                        require(f'PRODUCTION_APPLY_VALIDATED={revision}' in apply_evidence,
                                args.phase + '-final-runtime-proof')
                        require(f'RELAY_INSTALLED_REVISION={revision};consumer={consumer_revision};' in apply_evidence,
                                args.phase + '-installed-identity-proof')
                        if lifecycle_required:
                            require(f'RELAY_UPGRADE_ACTIVATION_VALIDATED={revision}' in apply_evidence,
                                    'upgrade-same-operation-activation-proof')
                            observe_failure_state(boundary='activation', installed=revision, activation='verified')
                        else:
                            observe_failure_state(boundary='installed', installed=revision)
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
                                f'{args.phase}-post-check-failed;log={log_ref};next=diagnose-operation-before-retry')
                        require(not re.search(r'changed=[1-9][0-9]*', checked), args.phase + '-post-check-drift')
                        require(f'RELAY_INSTALLED_REVISION={revision};consumer={consumer_revision};' in checked,
                                args.phase + '-post-check-installed-identity-proof')
                        if args.phase == 'reinstall' and not pool_reinstall:
                            remote_action(target, key, config, revision, observed, action='complete', guard=guard)
                    if args.local_lifecycle and args.phase in ['apply', 'upgrade'] and not fast_source:
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
                        if pool_maintenance_started:
                            pool_maintenance('restart')
                        if reviewer_pause_pending:
                            resume_reviewer(300)
                            reviewer_pause_pending = False
                        progress('RESUME', revision)
                        remote_admission(target, key, values['relay_namespace'], 'resume', '--operation', lifecycle_operation)
                        gate_reopened = True
                        if pool_maintenance_started:
                            pool_maintenance('resume')
                        progress('OPEN', revision)
                except Exception as error:
                    report_failure(error, 'installer', private_log=log_name)
                    progress('RECOVERY', revision)
                    pool_restored = False
                    restored_old_gate = False
                    if (preparation is not None and preparation.captured
                            and (not preparation.cutover_started or preparation.predispatch_bridge_attempted)
                            and lifecycle_operation and not gate_reopened
                            and (not args.authorize_lifecycle_recovery or preparation.predispatch_bridge_attempted)):
                        try:
                            aborted = preparation.abort()
                            require(aborted['status'] == 'old-open-restored', 'INSTALL_PREFLIGHT_ABORT_UNPROVEN')
                            restored_old_gate = True
                            observe_failure_state(boundary='original-open', admission='open', installed=args.intent_expected_installed_revision)
                            if reviewer_pause_pending:
                                resume_reviewer(30, previous_pid=reviewer_pid)
                                reviewer_pause_pending = False
                            if pool_drain_completed:
                                pool_maintenance('restart')
                                pool_maintenance('resume')
                                pool_restored = True
                            args._intent_mutation_started = False
                            args._intent_old_availability_restored = True
                            print('RELAY_INSTALL_PREFLIGHT=aborted;old-availability=verified;operation=' + lifecycle_operation,
                                  flush=True)
                        except Exception as recovery_error:
                            report_failure(recovery_error, 'install-preflight-abort', private_log=log_name)
                            print('RELAY_INSTALL_PREFLIGHT_ABORT=unproven;retain-original-operation;inspect-before-recovery',
                                  flush=True)
                    if (reviewer_pause_pending and lifecycle_operation is None
                            and not args.authorize_lifecycle_recovery):
                        try:
                            resume_reviewer(30, previous_pid=reviewer_pid)
                            reviewer_pause_pending = False
                        except Exception as recovery_error:
                            report_failure(recovery_error, 'reviewer-resume-old', private_log=log_name)
                    if (reserved_pool and pool_maintenance_started and not pool_restored
                            and not reviewer_pause_pending and (lifecycle_operation is None or gate_reopened)):
                        # Reconcile the exact paused labels while the original
                        # reservation is still live and the bound gates are open.
                        try:
                            pool_maintenance('resume' if gate_reopened else 'rollback')
                            pool_restored = True
                            if lifecycle_operation is None:
                                args._intent_old_availability_restored = True
                                observe_failure_state(boundary='original-open', admission='open',
                                                      installed=args.intent_expected_installed_revision)
                        except Exception as recovery_error:
                            report_failure(recovery_error, 'pool-resume-open', private_log=log_name)
                    if not reserved_pool and pool_drain_completed and lifecycle_operation is None:
                        # Only the pool was stopped. Its original operation can
                        # verify runner and admission readiness before restoring labels.
                        try:
                            pool_maintenance('restart')
                            pool_maintenance('resume')
                            pool_restored = True
                        except Exception as recovery_error:
                            report_failure(recovery_error, 'pool-resume-old', private_log=log_name)
                    if pool_maintenance_started and not pool_restored and (lifecycle_operation is None or gate_reopened):
                        phase = 'verified-admission-open' if gate_reopened else 'before-quiesce'
                        print(f'RELAY_POOL_RECOVERY_REQUIRED=operation={admission_operation_id};phase={phase};'
                              'next=inspect-original-pool-operation-before-retry', flush=True)
                    if reviewer_pause_pending:
                        phase = ('old-admission-open' if restored_old_gate else 'admission-closed-or-unproven'
                                 if lifecycle_operation or args.authorize_lifecycle_recovery else 'before-quiesce')
                        print(f'RELAY_REVIEWER_RECOVERY_REQUIRED=operation={admission_operation_id};phase={phase};'
                              'next=inspect-original-reviewer-operation-before-retry', flush=True)
                    if preparation is not None:
                        preparation.release_writer()
                    if lifecycle_operation and not gate_reopened and not restored_old_gate:
                        try:
                            remote_admission(target, key, values['relay_namespace'], 'phase',
                                '--operation', lifecycle_operation, '--phase', 'recovery-required')
                        except Exception as recovery_error:
                            report_failure(recovery_error, 'recovery-state-write', private_log=log_name)
                            print('RELAY_DEPLOYMENT_WARNING=recovery-state-write-unproven;primary-failure-preserved',
                                  file=sys.stderr, flush=True)  # the last durable state remains closed
                    raise
                finally:
                    if guard is not None and owns_guard:
                        release_guard(guard)
            log.flush()
            evidence = Path(log_name).read_text()
            if returncode:
                raise RuntimeError(f'BACKEND_FAILED;phase={args.phase};log={log_ref};next=diagnose-operation-before-retry')
            if not fast_source:
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
                    raise RuntimeError(f'recovery-requires-disposition;log={log_ref}')
                if not re.search(r'changed=[1-9][0-9]*', evidence):
                    require(f'PRODUCTION_CHECK_VALIDATED={revision};state=stable-no-op;recovery=none' in evidence, 'final-check-proof')
            if args.stale_apply_shape:
                require(f'PRODUCTION_BOOTSTRAP_DISPOSITION_PASS={revision}' in evidence, 'bootstrap-disposition-proof')
            if args.phase == 'apply':
                require(f'PRODUCTION_APPLY_VALIDATED={revision}' in evidence, 'final-runtime-proof')
            if args.phase in ['apply', 'upgrade', 'post-check', 'bootstrap', 'reinstall']:
                if fast_source:
                    require(source_proof['status'] == 'SOURCE_UPGRADE_READY'
                            and source_proof['revision'] == revision
                            and source_proof['consumerRevision'] == consumer_revision
                            and source_proof['previousRevision'] == args.intent_expected_installed_revision,
                            'source-upgrade-final-proof')
                    previous_revision = source_proof['previousRevision']
                else:
                    require(f'RELAY_INSTALLED_REVISION={revision};consumer={consumer_revision};' in evidence, 'installed-identity-proof')
                    previous = re.search(r'RELAY_INSTALLED_REVISION=[0-9a-f]{40};consumer=[0-9a-f]{40};previous=([a-z0-9]+)', evidence)
                    require(previous is not None, 'previous-revision-proof')
                    previous_revision = previous[1]
                observe_failure_state(installed=revision, **({'boundary': 'installed'} if not lifecycle_operation else {}))
                print(f'installed_revision={revision}\nprevious_revision={previous_revision}\nRELAY_INSTALL_RESULT=PASS')
            if args.phase == 'upgrade':
                print(f'RELAY_UPGRADE_RESULT=PASS;installed={revision};projection={revision};verification=same-operation')
            if args.local_lifecycle:
                print(f'RELAY_LIFECYCLE_VERIFIED={revision}')
            if install_flow:
                print(f'RELAY_BOOTSTRAP_RESULT=PASS;phase={args.phase};installed={revision};post_check=clean;activation=owner-required')
                if not intent_install and 'generalRunnerPool' in config['consumer']:
                    print('RELAY_DEPLOYMENT_PENDING=ACTIVATION_AND_POOL_RECONCILIATION_REQUIRED;next=activate-then-apply')
            if args.local_reconcile:
                require(f'PRODUCTION_LIFECYCLE_PRESERVED={revision};activation=owner-after-job' in evidence, 'local-live-lifecycle')
                # Checkout mode retains the consumer workflow receipt ABI;
                # installed mode binds both revisions and reports the product SHA.
                receipt_head = revision if args.expected_installed_head else consumer_revision
                print(f'PRODUCTION_APPLY_VALIDATED={receipt_head}')
                print(f'PRODUCTION_LIFECYCLE_PRESERVED={receipt_head};activation=owner-after-job')
            print(f'RELAY_DEPLOYMENT_RESULT=PASS;phase={args.phase};elapsed_seconds={int(time.monotonic()-started)};log={log_ref}')
        finally:
            os.close(lock)


def main():
    previous = signal.getsignal(signal.SIGTERM)
    installed_handler = (threading.current_thread() is threading.main_thread() and previous == signal.SIG_DFL)
    if installed_handler:
        def interrupted(_signum, _frame):
            raise InterruptedError('deployment-interrupted')
        signal.signal(signal.SIGTERM, interrupted)
    observation = start_failure_observation('deployment')
    try:
        args = arguments()
        observe_failure_state(phase=getattr(args, 'phase', None))
        run(args)
        return 0
    except (Exception, KeyboardInterrupt) as error:
        print_terminal_failure(error, 'deployment-entrypoint', report_failure)
        # Avoid dumping subprocess output or a full consumer/environment input.
        candidate = str(error) if isinstance(error, (ValueError, RuntimeError)) else ''
        field = (re.fullmatch(r'INVALID_DEPLOYMENT_CONFIG:([A-Za-z][A-Za-z0-9_.-]{0,159})(?:([:;]).*)?', candidate)
                 if isinstance(error, InvalidConfig) else None)
        if field:
            # Keep the supported field/check identity; values and host paths
            # after it stay behind the diagnostic reference printed above.
            message = 'INVALID_DEPLOYMENT_CONFIG:' + field[1]
            if field[2]:
                message += field[2] + 'protected-details'
            # Preserve source-owned inspection instructions independently of
            # private paths/observations in the same legacy diagnostic string.
            for action in ['inspect-file-type-and-access', 'diagnose-operation-before-retry']:
                if re.search(r'(?:;|;next=)' + action + r'(?:;|$)', candidate):
                    message += ';next=' + action
        else:
            code = candidate.split(';', 1)[0]
            known = code in {'BACKEND_FAILED', 'RELAY_INSTALL_FAILED', 'recovery-requires-disposition',
                             'host-operation-guard-lost'}
            if isinstance(error, LifecycleCheckError):
                known = len(code) <= 110 and re.fullmatch(r'[a-z][a-z0-9]*(?:-[a-z0-9]+)+|ADMISSION_[A-Z_]{1,100}', code)
            elif type(error).__name__ == 'PoolError':
                known = re.fullmatch(r'MANAGED_POOL_[A-Z_]{1,100}', code)
            message = code if known else type(error).__name__
        print('RELAY_DEPLOYMENT_BLOCKED=' + message, file=sys.stderr)
        return 1
    finally:
        stop_failure_observation(observation)
        if installed_handler:
            signal.signal(signal.SIGTERM, previous)


if __name__ == '__main__':
    sys.exit(main())
