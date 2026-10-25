"""Target operations through the deployment backend's configured Ansible connection.

This is an internal adapter, not an alternative public deployment interface.
Only the qualified Debian SSH and local connections are admitted. Command results
use private no-log tasks; Ansible never prints helper input or diagnostics.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import uuid


BACKEND = Path(__file__).resolve().parent / 'ansible'
STRICT_SSH = '-o BatchMode=yes -o StrictHostKeyChecking=yes -o IdentitiesOnly=yes'
RESULT_LIMIT = 1048576


def connection_vars(target, key=None, *, local=False):
    connection = 'local' if local else target.get('connection', 'ssh')
    if connection not in ['ssh', 'local']:
        raise ValueError('unsupported-ansible-connection')
    values = {'ansible_connection': connection, 'ansible_user': target['user'],
              'ansible_python_interpreter': '/usr/bin/python3'}
    # Protected installed-local callers already run as root. Inherit the play's
    # privilege decisions: a host-level False suppresses become_user as well,
    # making runner probes and runner-owned archive extraction execute as root.
    if not local:
        values['ansible_become'] = True
    if connection == 'ssh':
        values.update(ansible_ssh_private_key_file=str(key), ansible_ssh_common_args=STRICT_SSH)
    return values


def backend_environment():
    env = {k: os.environ[k] for k in ['HOME', 'PATH', 'USER', 'LANG', 'LC_ALL', 'SSH_AUTH_SOCK'] if k in os.environ}
    env.update(ANSIBLE_CONFIG=str(BACKEND / 'ansible.cfg'),
               ANSIBLE_ROLES_PATH=str(BACKEND / 'roles'), PYTHONDONTWRITEBYTECODE='1')
    return env


class TargetProcess:
    """Popen-shaped adapter so existing guard/failure loops retain their semantics."""
    def __init__(self, target, key, argv, *, local=False):
        if local and target is None:
            target = {'user': 'root', 'host': 'localhost', 'connection': 'local'}
        self.target, self.key, self.argv, self.local = target, key, argv, local
        self.process = None
        self.temporary = None
        self.result = None

    def start(self, value=None):
        if self.process is not None:
            return
        self.temporary = tempfile.TemporaryDirectory(prefix='relay-ansible-operation-')
        work = Path(self.temporary.name)
        self.result_path = work / 'result.json'
        controller = 'relay_controller_' + uuid.uuid4().hex
        inventory = {'all': {'children': {'relay': {'hosts': {
            self.target['host']: connection_vars(self.target, self.key, local=self.local)}}},
            'hosts': {controller: {'ansible_connection': 'local', 'ansible_become': False,
                                  'ansible_python_interpreter': '/usr/bin/python3'}}}}
        request = "lookup('ansible.builtin.file', '" + str(work / 'request.json') + "', rstrip=False) | from_json"
        playbook = [{'hosts': 'relay', 'gather_facts': False, 'tasks': [{
            'name': 'relay-target-command', 'ansible.builtin.command': {
                'argv': '{{ (' + request + ').argv }}', 'stdin': '{{ (' + request + ').input | string }}',
                'stdin_add_newline': False, 'strip_empty_ends': False},
            'register': 'relay_target_receipt', 'failed_when': False,
            'no_log': True, 'changed_when': False}, {
            'name': 'Return the bounded helper receipt privately', 'delegate_to': controller, 'become': False,
            'ansible.builtin.copy': {'dest': str(self.result_path), 'mode': '0600',
                'content': "{{ {'rc': relay_target_receipt.rc | default(255), 'stdout': relay_target_receipt.stdout | default(''), 'stderr': relay_target_receipt.stderr | default('')} | to_json }}"},
            'no_log': True, 'diff': False}]}]
        for name, content in [('inventory.json', inventory), ('operation.json', playbook),
                              ('request.json', {'argv': self.argv, 'input': value or ''})]:
            path = work / name
            path.write_text(json.dumps(content), encoding='utf-8')
            path.chmod(0o600)
        env = backend_environment()
        self.process = subprocess.Popen(['ansible-playbook', '-i', str(work / 'inventory.json'),
            str(work / 'operation.json'), '--limit', self.target['host']], cwd=BACKEND, env=env,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True)

    @property
    def returncode(self):
        return self.result['rc'] if self.result is not None else self.process.returncode if self.process else None

    def poll(self):
        return self.process.poll() if self.process else None

    def communicate(self, input=None, timeout=None):
        if self.result is not None:
            return self.result['stdout'], self.result['stderr']
        self.start(input)
        self.process.wait(timeout=timeout)
        try:
            if self.result_path.stat().st_size > RESULT_LIMIT * 3:
                raise ValueError()
            result = json.loads(self.result_path.read_text())
            if (set(result) != {'rc', 'stdout', 'stderr'} or type(result['rc']) is not int
                    or any(not isinstance(result[k], str) or len(result[k].encode()) > RESULT_LIMIT
                           for k in ['stdout', 'stderr'])
                    or self.process.returncode != 0 and result['rc'] == 0):
                raise ValueError()
            self.result = result
        except (OSError, ValueError, TypeError):
            self.result = {'rc': 255, 'stdout': '', 'stderr': 'ANSIBLE_TARGET_OPERATION_UNPROVEN\n'}
        finally:
            self.temporary.cleanup()
        return self.result['stdout'], self.result['stderr']

    def terminate(self):
        if self.process:
            os.killpg(self.process.pid, signal.SIGTERM)
        elif self.temporary is not None:
            self.temporary.cleanup()

    def kill(self):
        if self.process:
            os.killpg(self.process.pid, signal.SIGKILL)

    def wait(self, timeout=None):
        if self.process is None:
            return 255  # a failed launch is never an instruction to launch again
        self.communicate(timeout=timeout)
        return self.returncode


def run_target(target, key, argv, *, input=None, timeout=None, local=False):
    process = TargetProcess(target, key, argv, local=local)
    try:
        output, errors = process.communicate(input=input, timeout=timeout)
        return subprocess.CompletedProcess(argv, process.returncode, output, errors)
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


TARGET_PROOF = '''import glob, os, pathlib, stat, subprocess, sys
try:
    release = dict(line.split('=', 1) for line in pathlib.Path('/etc/os-release').read_text().splitlines() if '=' in line)
    if sys.platform != 'linux' or release.get('ID', '').strip('"') != 'debian' or release.get('VERSION_ID', '').strip('"') != '12' or os.geteuid() != 0:
        raise ValueError()
    if sys.argv[1] == 'local':
        fingerprints = []
        for name in glob.glob('/etc/ssh/ssh_host_*_key.pub'):
            path = pathlib.Path(name)
            info = path.lstat()
            if stat.S_ISREG(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022:
                value = subprocess.run(['/usr/bin/ssh-keygen', '-lf', name], capture_output=True, text=True)
                if value.returncode == 0: fingerprints.append(value.stdout.split()[1])
        if sys.argv[2] not in fingerprints: raise ValueError()
    print('RELAY_TARGET_IDENTITY=PASS')
except Exception:
    print('RELAY_TARGET_IDENTITY_UNPROVEN', file=sys.stderr)
    sys.exit(1)
'''


def qualify_target(target, key):
    result = run_target(target, key, ['/usr/bin/python3', '-I', '-c', TARGET_PROOF,
        target.get('connection', 'ssh'), target['hostFingerprint']], timeout=60)
    if result.returncode or result.stdout != 'RELAY_TARGET_IDENTITY=PASS\n':
        raise RuntimeError('target-identity-or-debian-capability-unproven')


# A blocking Ansible command owns the original helper's stdin and kernel lock.
# Only ephemeral rendezvous files are added; the existing lock inode, reservation
# and recovery records remain authoritative. There is no lease or lock stealing.
GUARD_SCRIPT = '''import json, os, pathlib, selectors, stat, subprocess, sys, time
directory = pathlib.Path(sys.argv[1])
process = None
owned = False
try:
    if os.geteuid() != 0 or directory.parent != pathlib.Path('/run'):
        raise ValueError()
    os.mkdir(directory, 0o700)
    owned = True
    parent = os.getppid()
    def ancestry(pid):
        result = {}
        while pid > 1:
            fields = pathlib.Path('/proc/' + str(pid) + '/stat').read_text().rsplit(')', 1)[1].split()
            if fields[0] == 'Z': raise ValueError()
            result[pid] = fields[19]
            pid = int(fields[1])
        return result
    parent_start = ancestry(parent)
    value = json.load(sys.stdin)
    process = subprocess.Popen(value['argv'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, text=True)
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        if not selector.select(30) or process.stdout.readline().strip() != value['ready']:
            raise ValueError()
    (directory / 'ready').touch(mode=0o600)
    while not (directory / 'release').exists():
        if process.poll() is not None or os.getppid() != parent:
            raise ValueError()
        if ancestry(parent) != parent_start:
            raise ValueError()
        time.sleep(0.1)
    process.stdin.close()
    if process.wait(timeout=30) != 0:
        raise ValueError()
    print('ANSIBLE_GUARD_RELEASED')
except Exception:
    print('ANSIBLE_GUARD_UNPROVEN', file=sys.stderr)
    sys.exit(1)
finally:
    if process is not None and process.poll() is None:
        process.stdin.close()
        try: process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    if owned:
        for name in ['ready', 'release']:
            (directory / name).unlink(missing_ok=True)
        directory.rmdir()
'''

GUARD_CONTROL = '''import os, pathlib, stat, sys
directory = pathlib.Path(sys.argv[1])
if directory.parent != pathlib.Path('/run'):
    raise SystemExit(1)
try:
    info = directory.lstat()
except FileNotFoundError:
    print('WAIT')
    raise SystemExit(0)
if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o700:
    raise SystemExit(1)
if sys.argv[2] == 'release':
    fd = os.open(directory / 'release', os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    os.close(fd)
print('READY' if (directory / 'ready').is_file() else 'WAIT')
'''


class GuardProcess:
    def __init__(self, target, key, argv, ready):
        self.target, self.key = target, key
        self.directory = '/run/relay-ansible-guard-' + str(uuid.uuid4())
        self.process = TargetProcess(target, key, ['/usr/bin/python3', '-I', '-c', GUARD_SCRIPT, self.directory])
        self.process.start(json.dumps({'argv': argv, 'ready': ready}))
        self.stdin = self  # retain the existing close/wait guard interface

    def control(self, action):
        result = run_target(self.target, self.key,
            ['/usr/bin/python3', '-I', '-c', GUARD_CONTROL, self.directory, action], timeout=30)
        if result.returncode:
            raise RuntimeError('host-operation-guard-unproven;inspect-before-retry')
        return result.stdout.strip()

    def poll(self):
        return self.process.poll()

    def close(self):
        self.control('release')

    def wait(self, timeout=None):
        result = self.process.wait(timeout=timeout)
        if result == 0 and self.process.result['stdout'] != 'ANSIBLE_GUARD_RELEASED\n':
            return 255
        return result


def hold_target(target, key, argv, ready):
    guard = GuardProcess(target, key, argv, ready)
    try:
        deadline = time.monotonic() + 60
        while guard.poll() is None and time.monotonic() < deadline:
            if guard.control('status') == 'READY':
                return guard
        raise RuntimeError('host-operation-guard-unavailable')
    except BaseException:
        try:
            guard.close()
            guard.wait(timeout=30)
        finally:
            if guard.poll() is None:
                guard.process.terminate()
        raise
