"""Target operations over the qualified deployment SSH or local connection.

This internal adapter preserves helper argv, root authority and guard semantics.
An already-root Debian local caller with the configured host identity proved for
this command uses native execution with private, bounded input/output channels.
SSH, privilege escalation and other contexts retain the Ansible no-log adapter.
"""
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import uuid


BACKEND = Path(__file__).resolve().parent / 'ansible'
STRICT_SSH = '-o BatchMode=yes -o StrictHostKeyChecking=yes -o IdentitiesOnly=yes'
RESULT_LIMIT = 1048576
CHANNEL_CLEANUP_TIMEOUT = 10


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


def native_local_eligible(target, *, local=False):
    if (sys.platform != 'linux' or not hasattr(os, 'geteuid') or os.geteuid() != 0
            or target.get('user') != 'root'
            or ('local' if local else target.get('connection', 'ssh')) != 'local'
            or not isinstance(target.get('hostFingerprint'), str) or not target['hostFingerprint']):
        return False
    try:
        release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
        return release.get('ID', '').strip('"') == 'debian' and release.get('VERSION_ID', '').strip('"') == '12'
    except (OSError, ValueError):
        return False


def prove_native_local(target):
    result = subprocess.run(['/usr/bin/python3', '-I', '-c', TARGET_PROOF,
        'local', target['hostFingerprint']], stdin=subprocess.DEVNULL, capture_output=True,
        cwd=BACKEND, env=backend_environment(), timeout=60, check=False)
    if result.returncode != 0 or result.stdout != b'RELAY_TARGET_IDENTITY=PASS\n' or result.stderr:
        raise RuntimeError('target-identity-or-debian-capability-unproven')


class TargetProcess:
    """Popen-shaped adapter so existing guard/failure loops retain their semantics."""
    def __init__(self, target, key, argv, *, local=False):
        if local and target is None:
            target = {'user': 'root', 'host': 'localhost', 'connection': 'local'}
        self.target, self.key, self.argv, self.local = target, key, argv, local
        self.process = None
        self.temporary = None
        self.result = None
        self.started = False
        self.native = False
        self.cancelled = False

    def start(self, value=None):
        if self.process is not None:
            return
        if self.started:
            raise RuntimeError('target-operation-launch-unproven')
        self.started = True
        self.native = native_local_eligible(self.target, local=self.local)
        if self.native:
            prove_native_local(self.target)
        self.temporary = tempfile.TemporaryDirectory(prefix='relay-ansible-operation-')
        work = Path(self.temporary.name)
        work.chmod(0o700)
        self.result_path = work / 'result.json'
        if self.native:
            self.start_native(work, value)
            return
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


    def start_native(self, work, value):
        paths = [work / name for name in ['input', 'stdout', 'stderr']]
        streams = []
        try:
            for path in paths:
                descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
                os.fchmod(descriptor, 0o600)
                streams.append(os.fdopen(descriptor, 'w+b'))
            data = value if isinstance(value, bytes) else (value or '').encode('utf-8')
            streams[0].write(data)
            streams[0].flush()
            streams[0].seek(0)
            self.process = subprocess.Popen(self.argv, cwd=BACKEND, env=backend_environment(),
                stdin=streams[0], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                close_fds=True, start_new_session=True)
            self.output_paths = paths[1:]
            self.output_streams = streams[1:]
            self.output_identities = [(os.fstat(stream.fileno()).st_dev, os.fstat(stream.fileno()).st_ino)
                                      for stream in self.output_streams]
            self.reader_errors = []
            self.readers = []
            for pipe, stream in zip([self.process.stdout, self.process.stderr], self.output_streams):
                reader = threading.Thread(target=self.read_channel, args=(pipe, stream), daemon=True)
                self.readers.append(reader)
                reader.start()
        except BaseException:
            if self.process is not None:
                self.kill()
                self.process.wait()
            for stream in streams:
                stream.close()
            self.temporary.cleanup()
            raise
        finally:
            if streams:
                streams[0].close()

    def read_channel(self, pipe, stream):
        stored = 0
        try:
            while True:
                chunk = pipe.read(65536)
                if not chunk:
                    break
                if stored <= RESULT_LIMIT:
                    bounded = chunk[:RESULT_LIMIT + 1 - stored]
                    stream.write(bounded)
                    stored += len(bounded)
            stream.flush()
        except Exception:
            self.reader_errors.append(True)
        finally:
            pipe.close()

    def pending_output(self):
        return self.native and any(reader.is_alive() for reader in getattr(self, 'readers', []))

    def collect_native(self):
        try:
            output = []
            if self.reader_errors:
                raise ValueError()
            for path, stream, identity in zip(self.output_paths, self.output_streams, self.output_identities):
                before = os.fstat(stream.fileno())
                current = path.lstat()
                def stamp(meta):
                    return (meta.st_dev, meta.st_ino, meta.st_size, meta.st_mtime_ns, meta.st_ctime_ns,
                            meta.st_mode, meta.st_uid, meta.st_gid, meta.st_nlink)
                if (not stat.S_ISREG(before.st_mode) or stat.S_IMODE(before.st_mode) != 0o600
                        or before.st_uid != 0 or before.st_nlink != 1
                        or (before.st_dev, before.st_ino) != identity
                        or stamp(current) != stamp(before)):
                    raise ValueError()
                stream.seek(0)
                raw = stream.read(RESULT_LIMIT + 1)
                if (len(raw) > RESULT_LIMIT or stamp(os.fstat(stream.fileno())) != stamp(before)
                        or stamp(path.lstat()) != stamp(before)):
                    raise ValueError()
                output.append(raw.decode('utf-8'))
            self.result = {'rc': self.process.returncode, 'stdout': output[0], 'stderr': output[1]}
        except (OSError, ValueError, UnicodeError):
            self.result = {'rc': 255, 'stdout': '', 'stderr': 'ANSIBLE_TARGET_OPERATION_UNPROVEN\n'}
        finally:
            for stream in self.output_streams:
                stream.close()
            self.temporary.cleanup()
        return self.result['stdout'], self.result['stderr']

    @property
    def returncode(self):
        return self.result['rc'] if self.result is not None else self.process.returncode if self.process else None

    def poll(self):
        status = self.process.poll() if self.process else None
        # The old Ansible wrapper stayed alive until helper channels closed.
        # Preserve that completion frontier for every existing guard loop.
        return None if self.native and self.pending_output() else status

    def communicate(self, input=None, timeout=None):
        if self.result is not None:
            return self.result['stdout'], self.result['stderr']
        self.start(input)
        deadline = time.monotonic() + timeout if timeout is not None else None
        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            if self.native:
                raise subprocess.TimeoutExpired('relay-target-operation', timeout) from None
            raise
        if self.native:
            for reader in self.readers:
                reader.join(timeout=max(0, deadline - time.monotonic()) if deadline is not None else None)
                if reader.is_alive():
                    raise subprocess.TimeoutExpired('relay-target-operation', timeout)
            return self.collect_native()
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
        self.cancelled = self.native
        if self.process:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        elif self.temporary is not None:
            self.temporary.cleanup()

    def kill(self):
        self.cancelled = self.native
        if self.process:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def wait(self, timeout=None):
        if self.process is None:
            return 255  # a failed launch is never an instruction to launch again
        bounded_cancel = self.native and self.cancelled
        effective = timeout
        if bounded_cancel:
            effective = min(timeout, CHANNEL_CLEANUP_TIMEOUT) if timeout is not None else CHANNEL_CLEANUP_TIMEOUT
        try:
            self.communicate(timeout=effective)
        except subprocess.TimeoutExpired:
            if bounded_cancel and timeout is None:
                raise RuntimeError('target-operation-channel-unproven;inspect-before-retry') from None
            raise
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
                process.wait(timeout=CHANNEL_CLEANUP_TIMEOUT)
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=CHANNEL_CLEANUP_TIMEOUT)
                except subprocess.TimeoutExpired:
                    raise RuntimeError('target-operation-channel-unproven;inspect-before-retry') from None


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

GUARD_CONTROL = '''import os, pathlib, stat, sys, time
directory = pathlib.Path(sys.argv[1])
action = sys.argv[2]
if directory.parent != pathlib.Path('/run') or action not in ['status', 'wait-ready', 'release']:
    raise SystemExit(1)
deadline = time.monotonic() + 20
identity = None
while True:
    try:
        info = directory.lstat()
    except FileNotFoundError:
        if identity is not None:
            raise SystemExit(1)
        info = None
    if info is not None:
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o700:
            raise SystemExit(1)
        observed = (info.st_dev, info.st_ino)
        if identity is not None and identity != observed:
            raise SystemExit(1)
        identity = observed
        if action == 'release':
            fd = os.open(directory / 'release', os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            os.close(fd)
        ready = directory / 'ready'
        try:
            ready_info = ready.lstat()
        except FileNotFoundError:
            ready_info = None
        if ready_info is not None:
            if (not stat.S_ISREG(ready_info.st_mode) or ready_info.st_uid != 0
                    or ready_info.st_nlink != 1 or stat.S_IMODE(ready_info.st_mode) != 0o600):
                raise SystemExit(1)
            print('READY')
            break
    if action != 'wait-ready' or time.monotonic() >= deadline:
        print('WAIT')
        break
    time.sleep(0.05)
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
            # Wait inside the same qualified target request rather than
            # launching a full Ansible play for every pre-readiness poll.
            if guard.control('wait-ready') == 'READY' and guard.poll() is None:
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
