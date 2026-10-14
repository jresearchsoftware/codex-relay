#!/usr/bin/env python3
"""Fixed protected owner apply/stop/resume composition; no caller-selected paths."""
import http.client
import json
import os
from pathlib import Path
import re
import ssl
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
from config import compile_inputs
from deployment_lock import acquire
from installed_config import verify as installed_config
from lifecycle import execute, require

ROOT = Path(__file__).resolve().parents[1]


def public_main(repository):
    require(re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository), 'product-repository')
    connection = http.client.HTTPSConnection('api.github.com', timeout=15,
                                              context=ssl.create_default_context())
    try:
        connection.request('GET', '/repos/' + repository + '/git/ref/heads/main', headers={
            'Accept': 'application/vnd.github+json', 'User-Agent': 'codex-relay-owner-lifecycle',
            'Cache-Control': 'no-cache'})
        response = connection.getresponse()
        require(response.status == 200, 'accepted-main-unavailable')
        raw = response.read(8193)
        require(len(raw) <= 8192, 'accepted-main-unavailable')
        value = json.loads(raw)
        require(value.get('ref') == 'refs/heads/main'
                and value.get('object', {}).get('type') == 'commit', 'accepted-main-unavailable')
        head = value['object']['sha']
        require(re.fullmatch('[0-9a-f]{40}', head), 'accepted-main-unavailable')
        return head
    finally:
        connection.close()


def clean_environment():
    return {'HOME': '/root', 'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8',
            'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
            'GIT_TERMINAL_PROMPT': '0', 'PYTHONDONTWRITEBYTECODE': '1'}


def git(root, *arguments):
    return subprocess.check_output(['/usr/bin/git', '-c', 'core.hooksPath=/dev/null',
        '-c', 'core.fsmonitor=false', '-c', 'core.attributesfile=/dev/null',
        '-C', str(root), *arguments], env=clean_environment(), text=True,
        stderr=subprocess.DEVNULL, timeout=120).strip()


def acquire_source(directory, repository, head):
    """Fresh protected Git only; never consume the runner's checkout/metadata."""
    require(re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository)
            and re.fullmatch('[0-9a-f]{40}', head), 'source-binding')
    directory.mkdir(mode=0o700)
    git(directory, 'init', '--quiet', '--template=')
    git(directory, 'fetch', '--quiet', '--no-tags', '--depth=1',
        'https://github.com/' + repository + '.git', head)
    require(git(directory, 'rev-parse', 'FETCH_HEAD^{commit}') == head, 'source-head-mismatch')
    entries = git(directory, 'ls-tree', '-r', '--name-only', head).splitlines()
    require(entries and all(not p.startswith('/') and '..' not in p.split('/')
                           and not any(x.lower() == '.git' for x in p.split('/')) for p in entries),
            'source-path-unsafe')
    require(all(row.split()[0] in ['100644', '100755']
                for row in git(directory, 'ls-tree', '-r', head).splitlines()), 'source-mode-unsafe')
    git(directory, 'checkout', '--quiet', '--detach', head)
    require(not git(directory, 'status', '--porcelain', '--untracked-files=all'), 'source-dirty')
    return directory


def installed_proof(config, head):
    install = Path(compile_inputs(config)['relay_install_root'])
    # Full config/manifest/current identity read belongs to this same call.
    installed_config(install / 'releases' / head / 'reviewed-source', head)
    return True


def run(request):
    require(os.geteuid() == 0, 'root-required')
    match = re.fullmatch(r'(apply|stop|resume):([0-9a-f]{40}):([0-9a-f]{40})', request)
    require(match is not None, 'argument-contract')
    action, installed, consumer_head = match.groups()
    config, _, _ = installed_config(ROOT, installed)
    values = compile_inputs(config)
    repository = config['consumer']['repository']
    source_repository = config['source']['repository'].removeprefix('https://github.com/').removeprefix(
        'git@github.com:').removesuffix('.git')
    gate_path = values['relay_install_root'] + '/relay-admission'

    def gate(*arguments):
        result = subprocess.run([gate_path, *arguments], env=clean_environment(),
                                text=True, stdout=subprocess.PIPE, check=True, timeout=1860)
        return json.loads(result.stdout)

    with acquire('/var/lib/' + values['relay_namespace'] + '-deployment.lock') as lock_fd:
        # Revalidate the protected installation under the mutex before any state
        # change. Bind public main ONCE. Later movement cannot retarget this call.
        installed_config(ROOT, installed)
        selected = public_main(source_repository)
        if source_repository == repository:
            require(selected == consumer_head, 'consumer-dispatch-stale')
        else:
            require(public_main(repository) == consumer_head, 'consumer-dispatch-stale')
        target = selected if action == 'apply' else installed
        print(f'RELAY_LIFECYCLE_SELECTED={target};installed={installed};consumer={consumer_head}', flush=True)
        if action == 'stop':
            execute(gate, target, None, None, stop=True)
            return
        state = gate('status') if action == 'resume' else None
        if state:
            # Uncertain apply/recovery is not an ordinary graceful resume.
            require(state['phase'] in ['quiesced', 'drained'], 'resume-recovery-requires-diagnosis')
            require(state['target'] == installed, 'resume-installed-target-mismatch')
        with tempfile.TemporaryDirectory(prefix='owner-lifecycle-',
                                         dir=values['relay_production_local_apply_stage_root']) as temporary:
            work = Path(temporary)
            source = acquire_source(work / 'product', source_repository, target)
            consumer = source if repository == source_repository and target == consumer_head else acquire_source(
                work / 'consumer', repository, consumer_head)
            from workflow_projection import verify
            try:
                verify(config, target, source, consumer)
            except ValueError:
                raise ValueError('WORKFLOW_REVIEW_REQUIRED;consumer-projection-must-match-selected-target') from None
            # Freeze source and consumer before quiesce. The existing public API
            # performs committed projection checks again at its mutation boundary.
            phase = 'post-check' if action == 'resume' else ('apply' if target == installed else 'upgrade')
            operation = state['operationId'] if state else None

            def apply():
                nonlocal operation
                current = gate('status')
                operation = current['operationId']
                argv = ['/usr/bin/python3', str(source / 'deploy/relay-deploy.py'),
                    '--config', str(ROOT.parent / 'deployment-config.json'), '--consumer-root', str(consumer),
                    '--phase', phase, '--requested-revision', target, '--resolved-revision', target,
                    '--local-lifecycle', '--lifecycle-operation', operation,
                    '--lifecycle-lock-fd', str(lock_fd)]
                if phase == 'upgrade':
                    argv.append('--authorize-upgrade')
                process = subprocess.Popen(argv, env=clean_environment(), pass_fds=(lock_fd,),
                                           text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                evidence = []
                try:
                    for line in process.stdout:
                        print(line, end='', flush=True)
                        evidence.append(line)
                    require(process.wait() == 0, 'lifecycle-public-primitive-failed')
                finally:
                    process.stdout.close()
                    if process.poll() is None:
                        process.terminate()
                        process.wait(timeout=30)
                return ''.join(evidence)

            def verify_result(evidence, revision):
                require(f'RELAY_LIFECYCLE_VERIFIED={revision}' in evidence
                        and f'installed_revision={revision}' in evidence
                        and f'RELAY_WORKFLOW_PROJECTION=PASS;revision={revision};consumer={consumer_head}' in evidence,
                        'lifecycle-same-operation-proof-missing')
                return installed_proof(config, revision)

            execute(gate, target, apply, verify_result, operation=operation,
                    already_quiesced=state is not None)


if __name__ == '__main__':
    try:
        require(len(sys.argv) == 2, 'argument-contract')
        run(sys.argv[1])
    except (ValueError, OSError, subprocess.SubprocessError, KeyError, TypeError,
            http.client.HTTPException) as error:
        # Protected logs retain backend evidence; no private config or transport
        # stderr is copied into public errors. Admission is never reopened here.
        code = str(error).split(';')[0] if type(error) is ValueError else 'input-or-io'
        if not re.fullmatch(r'[A-Za-z][A-Za-z-]{0,79}|WORKFLOW_REVIEW_REQUIRED', code):
            code = 'input-or-io'
        print(f'RELAY_OWNER_LIFECYCLE_BLOCKED={code};inspect-state-and-protected-deployment-log', file=sys.stderr)
        raise SystemExit(1)
