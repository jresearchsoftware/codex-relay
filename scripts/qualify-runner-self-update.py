#!/usr/bin/env python3
"""Exercise pinned upstream update/wrapper shells in an unprivileged sandbox.

Listeners, downloaded payloads and job acceptance are synthetic. This proof
does not contact a GitHub runner service, register a runner, verify a server
version offer, download a signed distribution, or operate an installed service.
Listener policy and acquisition are excluded; legacy disableUpdate settings
remain untouched here and are covered by the separate migration qualification.
Recovery below is an explicit stopped-fixture repair, not a PROD recovery path.
"""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import urllib.request


OLD_VERSION = '2.336.0'
NEW_VERSION = '2.338.2'
UPSTREAM = f'https://raw.githubusercontent.com/actions/runner/v{NEW_VERSION}/src/Misc/'
SOURCES = {
    'update.sh.template': ('layoutbin/update.sh.template',
        '4be30dfd406af32339b03ba73a3c0b562743594a75aab10cb7c67ccf391f3078'),
    'safe_sleep.sh': ('layoutroot/safe_sleep.sh',
        '3e6f7c2108ab22d7c0dca7f3c923dd1a9450f61b9f940455fe73ad6c5baf1b3c'),
    'run.sh': ('layoutroot/run.sh',
        'b39d7e0ca921a3189f7fe4e0a2f686b46719d4ccc2647f156f14407ec4517e8f'),
    'run-helper.sh.template': ('layoutroot/run-helper.sh.template',
        '6e75e623cfe41831aae5dc4b059d0869a93355eff995fcbb23e38eda424d82f1'),
}
ENVIRONMENT = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'}
PRESERVED = ('.runner', '.credentials', '.credentials_rsaparams', '.env', '.path', '_work/existing-job')


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def fetch_sources():
    sources = {}
    for name, (relative, digest) in SOURCES.items():
        url = UPSTREAM + relative
        request = urllib.request.Request(url, headers={'User-Agent': 'codex-relay-runner-qualification'})
        with urllib.request.urlopen(request, timeout=30) as response:
            require(response.geturl() == url, 'UPSTREAM_UNEXPECTED_REDIRECT')
            content = response.read(131073)
        require(len(content) <= 131072 and sha256(content) == digest, f'UPSTREAM_HASH_MISMATCH:{name}')
        sources[name] = content.decode('utf-8')
    return sources


def executable(path, content):
    path.write_text(content, encoding='utf-8')
    path.chmod(0o750)


def run(argv, root, environment=None, timeout=15):
    process = subprocess.Popen(argv, cwd=root, env=environment or ENVIRONMENT,
                               text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=True)
    try:
        output, errors = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate(timeout=5)
        raise
    result = subprocess.CompletedProcess(argv, process.returncode, output, errors)
    require(len((result.stdout + result.stderr).encode('utf-8')) <= 16384, 'UNBOUNDED_FIXTURE_OUTPUT')
    return result


def snapshot(root):
    return {name: sha256((root / name).read_bytes()) for name in PRESERVED}


def snapshot_digest(value):
    return sha256(json.dumps(value, sort_keys=True).encode('utf-8'))


def render_update(root, pid):
    replacements = {
        '_PROCESS_ID_': str(pid), '_RUNNER_PROCESS_NAME_': 'Runner.Listener',
        '_ROOT_FOLDER_': str(root), '_EXIST_RUNNER_VERSION_': OLD_VERSION,
        '_DOWNLOAD_RUNNER_VERSION_': NEW_VERSION,
        '_UPDATE_LOG_': str(root / '_diag/update.log'), '_RESTART_INTERACTIVE_RUNNER_': '0',
    }
    source = (root / 'update.sh.template').read_text(encoding='utf-8')
    for name, value in replacements.items():
        require(name in source, f'UPSTREAM_PLACEHOLDER_MISSING:{name}')
        source = source.replace(name, value)
    executable(root / 'update.sh', source)


def fixture(parent, name, sources, identity):
    root = parent / name
    root.mkdir(mode=0o750)
    for directory in ('bin', 'externals', 'bin.' + NEW_VERSION, 'externals.' + NEW_VERSION, '_diag', '_work'):
        (root / directory).mkdir(mode=0o750)
    for filename, content in sources.items():
        executable(root / filename, content)
    state = {'agentId': identity, 'agentName': name, 'gitHubUrl': 'https://github.com/example',
             'poolName': 'synthetic-production' if name == 'production' else 'synthetic-general',
             'workFolder': str(root / '_work'), 'disableUpdate': True}
    for filename, content in {
        '.runner': json.dumps(state, sort_keys=True) + '\n',
        '.credentials': '{"fixture":"synthetic-no-credential"}\n',
        '.credentials_rsaparams': 'synthetic-no-private-key\n',
        '.env': 'SYNTHETIC_ENV=preserved\n', '.path': '/usr/bin:/bin\n',
        '_work/existing-job': 'preserve existing work\n',
        'externals/payload': 'old synthetic payload\n',
        'externals.' + NEW_VERSION + '/payload': 'new synthetic payload\n',
    }.items():
        (root / filename).write_text(content, encoding='utf-8')
        (root / filename).chmod(0o600)
    # The old stub supplies only the native update exit and detached shell
    # launch. The actual upstream scripts perform all link changes/restarts.
    old = '''#!/usr/bin/python3
import json, os, subprocess, sys
from pathlib import Path
root = Path(__file__).resolve().parent.parent
if sys.argv[1:] == ['--version']:
    print(OLD_VERSION)
    raise SystemExit(0)
assert sys.argv[1:] == ['run']
with (root / 'listener-events').open('a') as stream:
    stream.write(OLD_VERSION + '\\n')
source = (root / 'update.sh.template').read_text()
replacements = {'_PROCESS_ID_': str(os.getpid()), '_RUNNER_PROCESS_NAME_': 'Runner.Listener',
    '_ROOT_FOLDER_': str(root), '_EXIST_RUNNER_VERSION_': OLD_VERSION,
    '_DOWNLOAD_RUNNER_VERSION_': NEW_VERSION, '_UPDATE_LOG_': str(root / '_diag/update.log'),
    '_RESTART_INTERACTIVE_RUNNER_': '0'}
for name, value in replacements.items():
    assert name in source
    source = source.replace(name, value)
(root / 'update.sh').write_text(source)
with (root / '_diag/update-process.log').open('w') as output:
    process = subprocess.Popen(['/bin/bash', str(root / 'update.sh')], cwd=root,
                               stdout=output, stderr=subprocess.STDOUT)
(root / 'update-pid').write_text(str(process.pid))
raise SystemExit(3)
'''.replace('OLD_VERSION', repr(OLD_VERSION)).replace('NEW_VERSION', repr(NEW_VERSION))
    new = '''#!/usr/bin/python3
import sys
from pathlib import Path
root = Path(__file__).resolve().parent.parent
if sys.argv[1:] == ['--version']:
    print(NEW_VERSION)
    raise SystemExit(0)
assert sys.argv[1:] == ['run']
with (root / 'listener-events').open('a') as stream:
    stream.write(NEW_VERSION + '\\n')
(root / '_work/accepted-synthetic-job').write_text('synthetic job accepted after update\\n')
raise SystemExit(0)
'''.replace('NEW_VERSION', repr(NEW_VERSION))
    executable(root / 'bin/Runner.Listener', old)
    executable(root / ('bin.' + NEW_VERSION) / 'Runner.Listener', new)
    return root


def verify_links(root):
    for name in ('bin', 'externals'):
        path = root / name
        target = root / (name + '.' + NEW_VERSION)
        require(path.is_symlink() and os.readlink(path) == str(target), f'ABSOLUTE_VERSIONED_LINK_UNPROVEN:{name}')
        require(path.resolve(strict=True) == target, f'VERSIONED_TARGET_UNPROVEN:{name}')
    version = run([str(root / 'bin/Runner.Listener'), '--version'], root)
    require(version.returncode == 0 and version.stdout.strip() == NEW_VERSION, 'NEW_VERSION_UNPROVEN')


def verify_wrapper(root, expected_events):
    result = run(['/bin/bash', str(root / 'run.sh')], root)
    require(result.returncode == 0, 'OFFICIAL_WRAPPER_FAILED')
    require((root / 'listener-events').read_text().splitlines() == expected_events, 'WRAPPER_LISTENER_SEQUENCE_UNPROVEN')
    require((root / '_work/accepted-synthetic-job').is_file(), 'SYNTHETIC_JOB_NOT_ACCEPTED')
    if len(expected_events) == 2:
        require('Restarting runner...' in result.stdout, 'OFFICIAL_WRAPPER_RESTART_UNPROVEN')
        require((root / '_diag/update.log.succeed').is_file(), 'OFFICIAL_UPDATE_SUCCESS_LOG_MISSING')
    return result


def stopped_repair(root):
    # The updater has returned or was killed, and this fixture has no service.
    # Repair only the two proven local targets; preserve all old/new payloads.
    for name in ('bin', 'externals'):
        path, target = root / name, root / (name + '.' + NEW_VERSION)
        require(target.is_dir() and target.parent == root, 'RECOVERY_TARGET_UNPROVEN')
        if path.is_symlink():
            require(os.readlink(path) == str(target), 'RECOVERY_FOREIGN_LINK')
        else:
            require(not path.exists(), 'RECOVERY_UNEXPECTED_PATH')
            temporary = root / ('.' + name + '-qualification-repair')
            temporary.symlink_to(target, target_is_directory=True)
            os.replace(temporary, path)


def qualify_failure(parent, name, sources, interrupt):
    root = fixture(parent, name, sources, 100)
    before = snapshot(root)
    # A completed child supplies a real, already-exited PID for the update's
    # /proc wait; no process belonging to another user is inspected or signaled.
    exited = subprocess.Popen(['/bin/true'])
    exited.wait(timeout=5)
    render_update(root, exited.pid)
    commands = root / 'fault-commands'
    commands.mkdir(mode=0o750)
    # Fault the second link so the first valid absolute link survives. No
    # upstream shell bytes are changed, including safe_sleep and update loops.
    fault = '''#!/usr/bin/python3
import os, signal, sys
if sys.argv[-1].endswith('/externals'):
    if INTERRUPT:
        os.kill(os.getppid(), signal.SIGKILL)
    raise SystemExit(73)
os.execv('/usr/bin/ln', ['ln', *sys.argv[1:]])
'''.replace('INTERRUPT', repr(interrupt))
    executable(commands / 'ln', fault)
    environment = {**ENVIRONMENT, 'PATH': str(commands) + ':' + ENVIRONMENT['PATH']}
    failed = run(['/bin/bash', str(root / 'update.sh')], root, environment)
    require(failed.returncode == (-signal.SIGKILL if interrupt else 1), 'INJECTED_LINK_FAILURE_UNPROVEN')
    require(not (root / 'externals').exists() and not (root / 'update.finished').exists(), 'INTERRUPTED_FRONTIER_UNPROVEN')
    require(not (root / '_work/accepted-synthetic-job').exists(), 'FAILED_UPDATE_ACCEPTED_JOB')
    require(snapshot(root) == before, 'FAILED_UPDATE_CHANGED_PERSISTED_STATE')
    if not interrupt:
        require((root / '_diag/update.log.failed').is_file(), 'UPSTREAM_FAILURE_LOG_MISSING')
    stopped_repair(root)
    verify_links(root)
    verify_wrapper(root, [NEW_VERSION])
    require(snapshot(root) == before, 'RECOVERY_CHANGED_PERSISTED_STATE')
    return {'scenario': name, 'updater_exit': failed.returncode, 'recovery': 'explicit-stopped-sandbox-links',
            'healthy_synthetic_job': True, 'preserved_manifest_sha256': snapshot_digest(before)}


def main():
    if sys.platform != 'linux' or os.geteuid() == 0:
        print(json.dumps({'status': 'UNAVAILABLE', 'requires': 'unprivileged native Linux temporary filesystem'}))
        return 2
    sources = fetch_sources()
    results = []
    with tempfile.TemporaryDirectory(prefix='relay-native-update-proof-') as temporary:
        parent = Path(temporary).resolve(strict=True)
        require(parent.parent == Path(tempfile.gettempdir()).resolve(strict=True), 'SANDBOX_PARENT_UNPROVEN')
        require(not str(parent).startswith('/mnt/'), 'NATIVE_LINUX_FILESYSTEM_REQUIRED')
        for index, name in enumerate([f'general-{value}' for value in range(1, 7)] + ['production'], 1):
            root = fixture(parent, name, sources, index)
            before = snapshot(root)
            verify_wrapper(root, [OLD_VERSION, NEW_VERSION])
            verify_links(root)
            require(snapshot(root) == before, 'NATIVE_UPDATE_CHANGED_PERSISTED_STATE')
            results.append({'runner': name, 'wrapper_restart': True, 'synthetic_job': True,
                            'preserved_manifest_sha256': snapshot_digest(before)})
        failures = [qualify_failure(parent, 'failed-link', sources, False),
                    qualify_failure(parent, 'interrupted-link', sources, True)]
    print(json.dumps({'status': 'PASS', 'proof': 'official-upstream-shells-with-synthetic-listeners-and-payloads',
        'upstream_version': NEW_VERSION, 'from_version': OLD_VERSION,
        'sources': {name: {'url': UPSTREAM + relative, 'sha256': digest}
                    for name, (relative, digest) in SOURCES.items()},
        'runners': results, 'failure_recovery': failures,
        'preserved_files': list(PRESERVED), 'persisted_disable_update_untouched': True,
        'live_registration': False, 'server_offer_or_signed_distribution': False,
        'native_listener_policy_or_acquisition': False,
        'installed_service_or_prod_mutation': False}, sort_keys=True))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (AssertionError, OSError, subprocess.SubprocessError, ValueError) as error:
        print(json.dumps({'status': 'FAIL', 'error': str(error)}, sort_keys=True))
        raise SystemExit(1)
