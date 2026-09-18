#!/usr/bin/env python3
"""Relay's owner-operated Debian deployment entrypoint (backend is private)."""
import argparse
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

sys.dont_write_bytecode = True
from config import load, compile_inputs, require, selector

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'deploy/ansible'
PHASES = {'check': 'site.yml', 'apply': 'site.yml', 'post-check': 'site.yml',
          'diagnose': 'relay-production-diagnostic.yml', 'activate': 'relay-reviewer-activation.yml',
          'runner-enable': 'relay-production-runner-enable.yml',
          'general-runner-enable': 'relay-general-runner.yml',
          'stale-dispose': 'relay-production-operation-stale-disposition.yml'}


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
            'codexLauncherSourceTreeSha256': digest('deploy/ansible/roles/relay_codex_runtime/templates/relay-codex-launcher.mjs.j2'),
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


def arguments():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', required=True, type=Path)
    p.add_argument('--phase', choices=[*PHASES, 'validate'], required=True)
    p.add_argument('--requested-revision', help='selector already resolved by the trusted acquisition/bootstrap')
    p.add_argument('--resolved-revision', help='exact acquisition result; must equal this clean checkout')
    p.add_argument('--log-root', type=Path, default=Path('/tmp/relay-deployment'))
    p.add_argument('--local-reconcile', action='store_true', help=argparse.SUPPRESS)
    p.add_argument('--consumer-revision', help=argparse.SUPPRESS)
    p.add_argument('--authorize-reviewer-activation', action='store_true')
    p.add_argument('--authorize-runner-enable', action='store_true')
    p.add_argument('--authorize-general-runner-enable', action='store_true')
    p.add_argument('--authorize-stale-disposition', action='store_true')
    p.add_argument('--stale-phase', choices=['apply', 'activate', 'runner-enable'])
    p.add_argument('--stale-head')
    p.add_argument('--stale-completed-phase', choices=['apply'])
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
    config_path = args.config.absolute()
    config = load(config_path, ROOT)
    values = compile_inputs(config)
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
        consumer_revision = args.consumer_revision
        requested = identity['revision']  # explicit installed version, never pretend to resolve remote main
    else:
        require(args.consumer_revision is None, 'consumer-revision-from-git-only')
        identity = source_identity(ROOT)
        requested = args.requested_revision or identity['revision']
        consumer_root = Path(git(config_path.parent, 'rev-parse', '--show-toplevel'))
        consumer_revision = clean_git(consumer_root)
    require(selector(requested), 'requested-revision')
    require(args.resolved_revision is None or args.resolved_revision == identity['revision'], 'resolved-revision-mismatch')
    require(re.fullmatch('[0-9a-f]{40}', consumer_revision or ''), 'consumer-revision')
    revision = identity['revision']
    require(not re.fullmatch('[0-9a-f]{40}', requested) or requested == revision, 'selected-commit-mismatch')
    require(args.authorize_reviewer_activation == (args.phase == 'activate'), 'explicit-activation')
    require(args.authorize_runner_enable == (args.phase == 'runner-enable'), 'explicit-runner-enablement')
    require(args.authorize_general_runner_enable == (args.phase == 'general-runner-enable'), 'explicit-general-runner-enablement')
    require(args.authorize_stale_disposition == (args.phase == 'stale-dispose'), 'explicit-stale-disposition')
    if args.phase == 'stale-dispose':
        require(args.stale_phase and re.fullmatch('[0-9a-f]{40}', args.stale_head or '') and args.stale_head != revision, 'stale-identity')
        if args.stale_phase == 'apply':
            require(args.stale_completed_phase == 'apply' and re.fullmatch('[0-9a-f]{64}', args.stale_state_hash or ''), 'stale-apply-evidence')
    else:
        require(not any([args.stale_phase, args.stale_head, args.stale_completed_phase, args.stale_state_hash]), 'stale-flags')
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
    target = config['target']
    key = Path(target['identityFile']).expanduser()
    if not args.local_reconcile:
        require(key.is_file() and not key.is_symlink(), 'operator-key')
        require(command(['ssh-keygen', '-lf', key]).split()[1] == target['identityFingerprint'], 'operator-key-identity')
        known = command(['ssh-keygen', '-F', target['host']])
        fingerprints = command(['ssh-keygen', '-lf', '-'], input=known).splitlines()
        require(any(row.split()[1] == target['hostFingerprint'] for row in fingerprints), 'host-identity')
        command(['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'IdentitiesOnly=yes',
                 '-i', key, target['user'] + '@' + target['host'], 'true'])
    values.update({
        'relay_review_root': str(ROOT), 'relay_source_identity': identity,
        'relay_requested_revision': requested, 'relay_consumer_revision': consumer_revision,
        'relay_deployment_profile': 'production',
        'relay_production_operation_phase': args.phase, 'relay_production_operation_target_head': revision,
        'relay_production_exact_head': revision, 'relay_reviewer_activation_exact_head': revision,
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
        'relay_production_diagnostic_target': 'issue' if args.issue_number else 'pull_request',
        'relay_production_diagnostic_issue_number': args.issue_number,
        'relay_production_diagnostic_issue_body_sha256': args.issue_body_sha256,
        'relay_production_diagnostic_pull_request': args.pull_request,
        'relay_production_diagnostic_review_id': args.review_id,
        'relay_production_diagnostic_reviewed_head': args.reviewed_head or '',
        'relay_production_diagnostic_change_request_id': args.change_request_id or '',
        'relay_production_diagnostic_branch': args.branch or '',
        'relay_production_diagnostic_base_branch_sha': args.base_branch_sha or '',
    })
    if args.phase == 'general-runner-enable':
        import yaml  # part of the private Ansible backend dependency set
        values.update(yaml.safe_load((BACKEND / 'vars/general-runner.yml').read_text()))
        values['relay_general_runner_authorized'] = True
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
            if args.phase in ['apply', 'activate', 'runner-enable', 'general-runner-enable', 'stale-dispose']:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # A normal source archive is only an internal transport detail.
            # No consumer lock, helper hash, distribution bundle or host cache.
            if args.phase == 'apply' and not args.local_reconcile:
                archive = work / 'source.tar'
                git(ROOT, 'archive', '--format=tar', '--output=' + str(archive), revision)
                values['relay_source_archive'] = str(archive)
            inventory = {'all': {'children': {'relay': {'hosts': {target['host']: {**values,
                'ansible_user': target['user'], 'ansible_connection': 'local' if args.local_reconcile else 'ssh',
                'ansible_become': not args.local_reconcile}}}}}}
            (work / 'inventory.json').write_text(json.dumps(inventory))
            env = {k: os.environ[k] for k in ['HOME', 'PATH', 'USER', 'LANG', 'LC_ALL', 'SSH_AUTH_SOCK'] if k in os.environ}
            env.update({'ANSIBLE_CONFIG': str(BACKEND / 'ansible.cfg'), 'ANSIBLE_ROLES_PATH': str(BACKEND / 'roles'),
                'ANSIBLE_SSH_COMMON_ARGS': '-o BatchMode=yes -o StrictHostKeyChecking=yes -o IdentitiesOnly=yes',
                'ANSIBLE_PRIVATE_KEY_FILE': str(key), 'PYTHONDONTWRITEBYTECODE': '1'})
            argv = ['ansible-playbook', '-i', str(work / 'inventory.json'), str(BACKEND / PHASES[args.phase]),
                    '--limit', target['host']]
            if args.phase in ['check', 'post-check']:
                argv += ['--check']
            started = time.monotonic()
            log.write(f'requested_revision={requested};resolved_revision={revision};consumer_revision={consumer_revision}\n')
            log.flush()
            completed = subprocess.run(argv, cwd=BACKEND, env=env, stdout=log, stderr=subprocess.STDOUT)
            log.flush()
            evidence = Path(log_name).read_text()
            if completed.returncode:
                raise RuntimeError(f'BACKEND_FAILED;phase={args.phase};log={log_name};next=diagnose-operation-before-retry')
            require('failed=0' in evidence, 'backend-recap')
            if args.phase == 'post-check':
                require(not re.search(r'changed=[1-9][0-9]*', evidence), 'post-check-drift')
            if args.phase == 'general-runner-enable':
                require(f'GENERAL_RUNNER_VALIDATED={revision};phase=general-runner-enable;' in evidence, 'general-runner-proof')
            if args.phase == 'check':
                require('PRODUCTION_RECOVERY_CLASSIFICATION=' not in evidence
                        and 'PRODUCTION_RECONCILIATION_STATE=RECOVERY_REQUIRED' not in evidence, 'recovery-requires-disposition')
                if not re.search(r'changed=[1-9][0-9]*', evidence):
                    require(f'PRODUCTION_CHECK_VALIDATED={revision};state=stable-no-op;recovery=none' in evidence, 'final-check-proof')
            if args.phase == 'apply':
                require(f'PRODUCTION_APPLY_VALIDATED={revision}' in evidence, 'final-runtime-proof')
            if args.phase in ['apply', 'post-check']:
                require(f'RELAY_INSTALLED_REVISION={revision};consumer={consumer_revision};' in evidence, 'installed-identity-proof')
                previous = re.search(r'RELAY_INSTALLED_REVISION=[0-9a-f]{40};consumer=[0-9a-f]{40};previous=([a-z0-9]+)', evidence)
                require(previous is not None, 'previous-revision-proof')
                print(f'installed_revision={revision}\nprevious_revision={previous[1]}\nRELAY_INSTALL_RESULT=PASS')
            if args.local_reconcile:
                require(f'PRODUCTION_LIFECYCLE_PRESERVED={revision};activation=owner-after-job' in evidence, 'local-live-lifecycle')
                # Keep the existing trusted consumer workflow's receipt ABI.
                print(f'PRODUCTION_APPLY_VALIDATED={consumer_revision}')
                print(f'PRODUCTION_LIFECYCLE_PRESERVED={consumer_revision};activation=owner-after-job')
            print(f'RELAY_DEPLOYMENT_RESULT=PASS;phase={args.phase};elapsed_seconds={int(time.monotonic()-started)};log={log_name}')
        finally:
            os.close(lock)


if __name__ == '__main__':
    try:
        run(arguments())
    except (ValueError, OSError, subprocess.CalledProcessError, RuntimeError) as error:
        # Avoid dumping subprocess output or a full consumer/environment input.
        message = str(error) if isinstance(error, (ValueError, RuntimeError)) else type(error).__name__
        print('RELAY_DEPLOYMENT_BLOCKED=' + message, file=sys.stderr)
        sys.exit(1)
