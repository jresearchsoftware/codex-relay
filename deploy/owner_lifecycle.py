#!/usr/bin/env python3
"""Fixed protected owner apply/stop/resume composition; no caller-selected paths."""
import http.client
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
from config import compile_inputs, deployment_repository, loads
from deployment_lock import acquire
from installed_config import verify as installed_config, read_protected, protected_parents
from lifecycle import execute, require

ROOT = Path(__file__).resolve().parents[1]


PROJECTION_PREFLIGHT_SCRIPT = '''import json, sys
from pathlib import Path
sys.dont_write_bytecode = True
source = Path(sys.argv[1])
sys.path.insert(0, str(source / 'deploy'))
try:
    raw = sys.stdin.buffer.read(262145)
    if len(raw) > 262144:
        raise ValueError()
    from config import loads
    from workflow_projection import verify
    config = loads(raw.decode('utf-8'), source)
    if 'generalRunnerPool' in config['consumer']:
        config = loads(json.dumps(config, sort_keys=True, separators=(',', ':'), ensure_ascii=False), source)
    verify(config, sys.argv[2], source, Path(sys.argv[3]))
    print('WORKFLOW_PREFLIGHT=PASS')
except Exception:
    print('WORKFLOW_REVIEW_REQUIRED', file=sys.stderr)
    sys.exit(1)
'''


def projection_preflight(source, target, consumer, config):
    """Validate with the frozen target's code, never the installed renderer."""
    result = subprocess.run(['/usr/bin/python3', '-I', '-c', PROJECTION_PREFLIGHT_SCRIPT,
                             str(source), target, str(consumer)],
        input=json.dumps(config), env=clean_environment(), text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=180)
    require(result.returncode == 0 and result.stdout == 'WORKFLOW_PREFLIGHT=PASS\n',
            'WORKFLOW_REVIEW_REQUIRED;consumer-projection-must-match-selected-target')


POOL_PREFLIGHT_SCRIPT = '''import json, re, sys
sys.dont_write_bytecode = True
sys.path.insert(0, sys.argv[1])
try:
    raw = sys.stdin.buffer.read(262145)
    if len(raw) > 262144:
        raise ValueError()
    from managed_pool_transport import preflight_pool
    preflight_pool(None, None, json.loads(raw), local=True)
    print('MANAGED_POOL_PREFLIGHT=PASS')
except Exception as error:
    code = str(error)
    print(code if re.fullmatch('MANAGED_POOL_[A-Z_]{1,100}', code) else
          'MANAGED_POOL_OWNER_PREFLIGHT_UNPROVEN', file=sys.stderr)
    sys.exit(1)
'''


def pool_preflight(source, config):
    """Use only the frozen protected target source before admission mutation."""
    if 'generalRunnerPool' not in config['consumer']:
        return
    name = config['environment']['generalRunner']['name']
    # The inner public primitive reacquires this same physical-pool lock. Keep
    # this read-only proof bounded rather than handing a new lock across APIs.
    with acquire('/var/lib/codex-relay-pool-' + name + '-deployment.lock'):
        result = subprocess.run(['/usr/bin/python3', '-I', '-c', POOL_PREFLIGHT_SCRIPT,
                                 str(source / 'deploy')],
            input=json.dumps(config), env=clean_environment(), text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=180)
    if result.returncode:
        codes = re.findall(r'^MANAGED_POOL_[A-Z_]{1,100}$', result.stderr, re.MULTILINE)
        raise ValueError(codes[-1] if codes else 'MANAGED_POOL_OWNER_PREFLIGHT_UNPROVEN')
    require(result.stdout == 'MANAGED_POOL_PREFLIGHT=PASS\n',
            'MANAGED_POOL_OWNER_PREFLIGHT_RESULT_UNPROVEN')


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


def git_anchor(installed):
    """Read only the protected source locator, never installed desired values."""
    import stat
    release = ROOT.parent
    install = release.parent.parent
    require(release.name == installed and release.parent.name == 'releases'
            and ROOT.name == 'reviewed-source', 'installed-release-path')
    current = install / 'current'
    protected_parents(current)
    metadata = current.lstat()
    require(stat.S_ISLNK(metadata.st_mode) and metadata.st_uid == 0
            and os.readlink(current) == str(release), 'installed-current-binding')
    identity = json.loads(read_protected(ROOT / '.relay-source.json', {0o644, 0o640, 0o600})[0])
    manifest = json.loads(read_protected(release / 'artifact-manifest.json', {0o640, 0o600})[0])
    require(isinstance(identity, dict) and isinstance(manifest, dict) and identity.get('revision') == installed
            and isinstance(identity.get('tree'), str) and re.fullmatch('[0-9a-f]{40}', identity['tree'])
            and all(manifest.get(key) == installed for key in ['commit', 'resolvedRevision', 'installedRevision'])
            and manifest.get('gitTree') == identity.get('tree'), 'installed-source-head')
    locator = Path('/etc') / install.name / 'deployment-source.json'
    binding = json.loads(read_protected(locator, {0o600}, group=0)[0])
    require(isinstance(binding, dict) and set(binding) in [
        {'repository', 'configPath', 'owner', 'productRepository'},
        {'repository', 'configPath', 'owner', 'productRepository', 'qualificationProductSha'}], 'git-source-locator')
    # An optional exact qualification pin is provisioned only by the root TEST
    # operator. Git configuration and workflow inputs cannot create this field.
    require('qualificationProductSha' not in binding
            or isinstance(binding['qualificationProductSha'], str)
            and re.fullmatch('[0-9a-f]{40}', binding['qualificationProductSha']), 'git-qualification-pin')
    return install, binding, manifest


def git_result(install, target, receipt, desired):
    """Verify the pair and effective configuration after the single Apply."""
    from config import unique_object
    import stat
    release = install / 'releases' / target
    current_link = install / 'current'
    protected_parents(current_link)
    info = current_link.lstat()
    require(stat.S_ISLNK(info.st_mode) and info.st_uid == 0 and os.readlink(current_link) == str(release),
            'git-current-readback-mismatch')
    source = release / 'reviewed-source'
    identity = json.loads(read_protected(source / '.relay-source.json', {0o644, 0o640, 0o600})[0])
    manifest = json.loads(read_protected(release / 'artifact-manifest.json', {0o640, 0o600})[0])
    raw = read_protected(release / 'deployment-config.json', {0o600}, group=0)[0]
    require(isinstance(identity, dict) and isinstance(manifest, dict) and manifest.get('gitConfigReceipt') == receipt
            and all(manifest.get(key) == target for key in ['commit', 'resolvedRevision', 'installedRevision'])
            and identity.get('revision') == target
            and isinstance(identity.get('tree'), str) and re.fullmatch('[0-9a-f]{40}', identity['tree'])
            and manifest.get('gitTree') == identity.get('tree')
            and manifest.get('deploymentConfigSha256') == hashlib.sha256(raw).hexdigest(),
            'git-pair-readback-mismatch')
    effective, _ = selected_config(source, raw)
    require(effective == desired,
            'git-effective-config-readback-mismatch')
    current = json.loads(read_protected(Path('/etc') / install.name / 'consumer.json',
                                      {0o600, 0o640, 0o644})[0], object_pairs_hook=unique_object)
    program = '''import {pathToFileURL} from 'node:url';
const {validateConsumer}=await import(pathToFileURL(process.argv[1]));
let raw=''; for await(const b of process.stdin){raw+=b; if(Buffer.byteLength(raw)>262144)process.exit(1)}
const input=JSON.parse(raw); const canonical=x=>JSON.stringify(x,(_k,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.keys(v).sort().map(k=>[k,v[k]])):v);
if(canonical(validateConsumer(input.current))!==canonical(validateConsumer(input.desired)))process.exit(1);
console.log('GIT_CONSUMER_READBACK=PASS');'''
    proof = subprocess.run(['/usr/bin/node', '--input-type=module', '-e', program,
                            str(source / 'consumer/consumer-config.mjs')],
        input=json.dumps({'current': current, 'desired': desired['consumer']}), text=True,
        env=clean_environment(), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False, timeout=60)
    require(proof.returncode == 0 and proof.stdout == 'GIT_CONSUMER_READBACK=PASS\n',
            'git-consumer-readback-mismatch')


def selected_config(source, raw):
    """The accepted target interprets its schema, including future additions."""
    program = '''import json, sys
sys.dont_write_bytecode = True
sys.path.insert(0, sys.argv[1])
from config import loads, compile_inputs
from pathlib import Path
raw = sys.stdin.buffer.read(65537)
if len(raw) > 65536: raise ValueError()
c = loads(raw.decode('utf-8'), Path(sys.argv[1]).parent)
if 'generalRunnerPool' in c['consumer']:
    c = loads(json.dumps(c, sort_keys=True, separators=(',', ':'), ensure_ascii=False), Path(sys.argv[1]).parent)
print(json.dumps({'config': c, 'values': compile_inputs(c)}))
'''
    result = subprocess.run(['/usr/bin/python3', '-I', '-c', program, str(source / 'deploy')],
        input=raw, env=clean_environment(), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        check=False, timeout=180)
    require(result.returncode == 0 and len(result.stdout) <= 524288, 'git-selected-config-invalid')
    parsed = json.loads(result.stdout)
    require(isinstance(parsed, dict) and isinstance(parsed.get('config'), dict)
            and isinstance(parsed.get('values'), dict), 'git-selected-config-invalid')
    return parsed['config'], parsed['values']


def git_target_capability(source):
    """Recognize the retained Git interface without parsing a future full schema."""
    from config import unique_object
    import stat
    source = Path(source)
    require(source.is_absolute() and source.is_dir() and not source.is_symlink()
            and (source / 'deploy').is_dir() and not (source / 'deploy').is_symlink(),
            'git-target-source-root-invalid')
    path = source / 'deploy/installation-contract.json'
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        raise ValueError('git-target-installation-contract-missing') from None
    except OSError:
        raise ValueError('git-target-installation-contract-invalid') from None
    try:
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
                    and 0 < before.st_size <= 65536, 'git-target-installation-contract-invalid')
            raw = stream.read(65537)
            stamp = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_nlink,
                value.st_uid, value.st_gid, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
            require(len(raw) == before.st_size and stamp(before) == stamp(os.fstat(stream.fileno()))
                    and stamp(before) == stamp(path.lstat()), 'git-target-installation-contract-invalid')
        metadata = json.loads(raw, object_pairs_hook=unique_object)
        capabilities = metadata.get('capabilities') if isinstance(metadata, dict) else None
        require(isinstance(metadata, dict) and type(metadata.get('schemaVersion')) is int
                and 0 < metadata['schemaVersion'] <= 9007199254740991
                and type(metadata.get('epoch')) is int and 0 < metadata['epoch'] <= 9007199254740991
                and isinstance(capabilities, list) and len(capabilities) <= 64
                and all(isinstance(value, str) and re.fullmatch('[A-Za-z0-9][A-Za-z0-9._-]{0,127}', value)
                        for value in capabilities)
                and len(capabilities) == len(set(capabilities)), 'git-target-installation-contract-invalid')
    except (OSError, UnicodeError, ValueError, TypeError):
        raise ValueError('git-target-installation-contract-invalid') from None
    require('git-desired-v1' in capabilities, 'git-target-installation-contract-unsupported')


def run_git(request, token):
    from git_intent import resolve_pair
    match = re.fullmatch(r'git:(apply|stop|resume):([0-9a-f]{40}):([0-9a-f]{40}):([1-9][0-9]{0,19})', request)
    require(os.geteuid() == 0 and match is not None, 'git-argument-contract')
    action, installed, config_sha, run_id = match.groups()
    install, binding, previous_manifest = git_anchor(installed)
    frozen = resolve_pair(binding, {'action': action, 'configSha': config_sha, 'runId': int(run_id)}, token)
    # The private native token is used only by resolve_pair; public Git is anonymous.
    token = None
    receipt = frozen['receipt']
    target = receipt['product_sha'] if action == 'apply' else installed
    print(('RELAY_GIT_PAIR=' if action == 'apply' else 'RELAY_GIT_DISPATCH_PAIR=')
          + json.dumps(receipt, sort_keys=True), flush=True)
    stage = Path('/var/lib') / install.name / 'production-apply'
    protected_parents(stage / 'entry')
    with tempfile.TemporaryDirectory(prefix='git-owner-lifecycle-', dir=stage) as temporary:
        work = Path(temporary)
        source = acquire_source(work / 'product', binding['productRepository'], target)
        git_target_capability(source)
        # Parse literal Git data using the selected accepted product's schema.
        desired, values = selected_config(source, frozen['config_bytes'])
        require(Path(values['relay_install_root']) == install
                and desired['environment']['namespace'] == install.name
                and desired['consumer']['owner'].casefold() == binding['owner'].casefold(),
                'git-config-target-mismatch')
        selected_repository = desired['source']['repository'].removeprefix('https://github.com/').removeprefix(
            'git@github.com:').removesuffix('.git')
        require(selected_repository == binding['productRepository'], 'git-product-repository-mismatch')
        require(desired['environment']['localApply'] == {
            'source': 'git', 'repository': binding['repository'], 'configPath': binding['configPath']},
            'git-config-source-mismatch')
        config_path = work / 'git-config.json'
        config_path.write_bytes(frozen['config_bytes'])
        config_path.chmod(0o600)
        receipt_path = work / 'git-receipt.json'
        receipt_path.write_text(json.dumps(receipt) + '\n')
        receipt_path.chmod(0o600)
        repository = deployment_repository(desired)
        consumer_head = public_main(repository)
        consumer = source if repository == binding['productRepository'] and consumer_head == target else acquire_source(
            work / 'consumer', repository, consumer_head)
        gate_path = str(install / 'relay-admission')

        def gate(*arguments):
            result = subprocess.run([gate_path, *arguments], env=clean_environment(),
                text=True, stdout=subprocess.PIPE, check=True, timeout=1860)
            return json.loads(result.stdout)

        if action == 'stop':
            with acquire('/var/lib/' + install.name + '-deployment.lock'):
                git_anchor(installed)
                execute(gate, installed, None, None, stop=True)
            return
        if action == 'resume':
            previous_pair = previous_manifest.get('gitConfigReceipt', {})
            require(all(previous_pair.get(key) == receipt.get(key) for key in [
                'config_repository', 'config_repository_id', 'config_sha', 'config_path', 'config_sha256',
                'product_repository', 'product_repository_id'])
                and previous_pair.get('product_sha') == installed, 'resume-git-apply-required')
            print('RELAY_GIT_RESUME_QUALIFIED_PAIR=' + json.dumps(previous_pair, sort_keys=True), flush=True)
            with acquire('/var/lib/' + install.name + '-deployment.lock') as lock_fd:
                git_anchor(installed)
                state = gate('status')
                require(state['phase'] in ['quiesced', 'drained'] and state['target'] == installed,
                        'resume-recovery-requires-diagnosis')

                def verify_resume():
                    argv = ['/usr/bin/python3', str(source / 'deploy/relay-deploy.py'), '--config', str(config_path),
                        '--consumer-root', str(consumer), '--phase', 'post-check', '--connection', 'local',
                        '--resolved-revision', installed, '--local-lifecycle',
                        '--lifecycle-operation', state['operationId'], '--lifecycle-lock-fd', str(lock_fd)]
                    subprocess.run(argv, env=clean_environment(), pass_fds=(lock_fd,), check=True)
                    git_result(install, installed, previous_pair, desired)
                    return True

                execute(gate, installed, verify_resume, lambda evidence, head: bool(evidence),
                        operation=state['operationId'], already_quiesced=True)
            return
        # The ordinary installer owns the single host lock and lifecycle gate.
        subprocess.run(['/usr/bin/python3', str(source / 'deploy/relay-deploy.py'),
            '--config', str(config_path), '--consumer-root', str(consumer), '--connection', 'local',
            '--phase', 'install', '--resolved-revision', target, '--git-config-receipt', str(receipt_path),
            '--log-root', '/var/log/' + install.name + '/owner-lifecycle'], env=clean_environment(), check=True)
        git_result(install, target, receipt, desired)
        print('RELAY_GIT_APPLY_VERIFIED=' + target + ';config=' + config_sha, flush=True)


def run(request):
    require(os.geteuid() == 0, 'root-required')
    match = re.fullmatch(r'(apply|stop|resume):([0-9a-f]{40}):([0-9a-f]{40})', request)
    require(match is not None, 'argument-contract')
    action, installed, consumer_head = match.groups()
    config, _, _ = installed_config(ROOT, installed)
    values = compile_inputs(config)
    repository = deployment_repository(config)
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
            projection_preflight(source, target, consumer, config)
            # Freeze source and consumer before quiesce. The existing public API
            # performs committed projection checks again at its mutation boundary.
            phase = 'post-check' if action == 'resume' else ('apply' if target == installed else 'upgrade')
            operation = state['operationId'] if state else None
            if action == 'apply':
                pool_preflight(source, config)

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


def main(arguments=None, token_stream=None):
    arguments = sys.argv[1:] if arguments is None else arguments
    try:
        require(len(arguments) == 1, 'argument-contract')
        if arguments[0].startswith('git:'):
            from git_intent import read_token
            run_git(arguments[0], read_token(sys.stdin.buffer if token_stream is None else token_stream))
        else:
            run(arguments[0])
        return 0
    except (ValueError, OSError, subprocess.SubprocessError, KeyError, TypeError,
            http.client.HTTPException) as error:
        # Protected logs retain backend evidence; no private config or transport
        # stderr is copied into public errors. Admission is never reopened here.
        from git_intent import GitIntentError
        code = str(error).split(';')[0] if type(error) is ValueError or isinstance(error, GitIntentError) else 'input-or-io'
        if not re.fullmatch(r'[A-Za-z][A-Za-z-]{0,79}|WORKFLOW_REVIEW_REQUIRED|MANAGED_POOL_[A-Z_]{1,100}|GIT_INTENT_[A-Z_]{1,100}', code):
            code = 'input-or-io'
        print(f'RELAY_OWNER_LIFECYCLE_BLOCKED={code};inspect-state-and-protected-deployment-log', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
