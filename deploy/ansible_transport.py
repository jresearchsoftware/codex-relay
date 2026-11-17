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
import shutil
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
PROGRESS_ROOT = Path('/run')

# The ordinary no-log Ansible command keeps its private stdout/stderr receipt.
# A root-private, operation-local rendezvous supplies only the latest validated
# drain observation while that same command runs. This follows the guard
# transport's ephemeral channel pattern; it is never lifecycle authority.
DRAIN_PROGRESS_WRAPPER = r'''import json, os, pathlib, re, subprocess, sys, threading
directory = pathlib.Path(sys.argv[1])
process = None
owned = False
pattern = sys.argv[2]
try:
    if directory.parent != pathlib.Path('/run') or not re.fullmatch('relay-ansible-progress-[a-f0-9]{32}', directory.name):
        raise ValueError()
    raw = sys.stdin.buffer.read(65537)
    if len(raw) > 65536: raise ValueError()
    request = json.loads(raw)
    if set(request) != {'argv', 'input'} or not isinstance(request['argv'], list) or not 1 <= len(request['argv']) <= 32 or not all(isinstance(v, str) and len(v) <= 4096 for v in request['argv']) or not isinstance(request['input'], str):
        raise ValueError()
    os.mkdir(directory, 0o700)
    owned = True
    process = subprocess.Popen(request['argv'], stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    def send_input():
        try:
            process.stdin.write(request['input'].encode('utf-8'))
            process.stdin.close()
        except BrokenPipeError:
            pass  # Child exit/output is decisive; never retry the command.
        except Exception:
            import traceback
            traceback.print_exc(limit=8)
    writer = threading.Thread(target=send_input, daemon=True)
    writer.start()
    pending = b''
    observations = []
    progress_truncated = False
    while True:
        chunk = process.stderr.read1(65536)
        if not chunk: break
        sys.stderr.buffer.write(chunk)
        sys.stderr.buffer.flush()
        pending += chunk
        while b'\n' in pending:
            line, pending = pending.split(b'\n', 1)
            if len(line) <= 4096 and re.fullmatch(pattern, line.decode('ascii', errors='replace')):
                try:
                    temporary = directory / 'next'
                    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
                    observations.append(line + b'\n')
                    while sum(map(len, observations)) > 65000:
                        observations.pop(0)
                        if not progress_truncated:
                            print('ANSIBLE_PROGRESS_CHANNEL_TRUNCATED', file=sys.stderr, flush=True)
                        progress_truncated = True
                    with os.fdopen(fd, 'wb') as stream:
                        if progress_truncated: stream.write(b'ANSIBLE_PROGRESS_CHANNEL_TRUNCATED\n')
                        stream.write(b''.join(observations))
                    os.replace(temporary, directory / 'progress')
                except OSError:
                    print('ANSIBLE_PROGRESS_CHANNEL_UNPROVEN', file=sys.stderr, flush=True)
        if len(pending) > 4096: pending = b'oversized:'
    sys.exit(process.wait())
finally:
    if process is not None:
        process.stderr.close()
        if process.poll() is None:
            process.terminate()
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    if owned:
        try:
            for name in ['next', 'progress']: (directory / name).unlink(missing_ok=True)
            directory.rmdir()
        except OSError:
            print('ANSIBLE_PROGRESS_CHANNEL_CLEANUP_UNPROVEN', file=sys.stderr, flush=True)
'''

DRAIN_PROGRESS_READ = r'''import os, pathlib, re, stat, sys
directory = pathlib.Path(sys.argv[1])
try:
    if directory.parent != pathlib.Path('/run') or not re.fullmatch('relay-ansible-progress-[a-f0-9]{32}', directory.name): raise ValueError()
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700: raise ValueError()
    fd = os.open(directory / 'progress', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 65536: raise ValueError()
        raw = stream.read(65537)
        if len(raw) > 65536: raise ValueError()
    sys.stdout.buffer.write(raw)
except FileNotFoundError:
    pass
except Exception:
    print('ANSIBLE_PROGRESS_CHANNEL_UNPROVEN', file=sys.stderr)
    sys.exit(1)
'''


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
        raise RuntimeError('target-identity-or-debian-capability-unproven') from subprocess.CalledProcessError(
            result.returncode, 'target-identity-proof', output=result.stdout, stderr=result.stderr)


class OperationDirectory:
    """Existing private transport spools, retained explicitly on failed evidence.

    Unlike TemporaryDirectory, process shutdown cannot remove the only original
    cause after a recorder failure. Successful operations still clean eagerly.
    """
    def __init__(self):
        self.name = tempfile.mkdtemp(prefix='relay-ansible-operation-')

    def cleanup(self):
        shutil.rmtree(self.name)


class TargetProcess:
    """Popen-shaped adapter so existing guard/failure loops retain their semantics."""
    def __init__(self, target, key, argv, *, local=False, progress=False):
        if local and target is None:
            target = {'user': 'root', 'host': 'localhost', 'connection': 'local'}
        self.target, self.key, self.argv, self.local = target, key, argv, local
        self.process = None
        self.temporary = None
        self.result = None
        self.started = False
        self.native = False
        self.cancelled = False
        self.progress = progress
        self.remote_progress = None
        self.last_progress = None
        self.forwarded_progress = {}
        self.progress_warning = False
        self.retained = False
        self.capture_counts = [0, 0]
        self.capture_prefix = [bytearray(), bytearray()]
        self.capture_tail = [bytearray(), bytearray()]
        self.reader_errors = []
        self.readers = []

    def start(self, value=None):
        try:
            return self._start(value)
        except BaseException as error:
            self.record_transport_failure(error, 'target-operation-start')
            if self.process is not None and self.process.poll() is None:
                try:
                    self.kill()
                    self.process.wait(timeout=CHANNEL_CLEANUP_TIMEOUT)
                except BaseException as secondary:
                    self.record_transport_failure(secondary, 'target-operation-start-cleanup')
            raise

    def _start(self, value=None):
        if self.process is not None:
            return
        if self.started:
            raise RuntimeError('target-operation-launch-unproven')
        self.started = True
        self.native = native_local_eligible(self.target, local=self.local)
        if self.native:
            prove_native_local(self.target)
        self.temporary = OperationDirectory()
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
        payload = {'argv': self.argv, 'input': value or ''}
        if self.progress is True:
            from lifecycle import DRAIN_PROGRESS_PATTERN
            self.remote_progress = PROGRESS_ROOT / ('relay-ansible-progress-' + uuid.uuid4().hex)
            payload = {'argv': ['/usr/bin/python3', '-I', '-c', DRAIN_PROGRESS_WRAPPER,
                               str(self.remote_progress), DRAIN_PROGRESS_PATTERN], 'input': json.dumps(payload)}
        for name, content in [('inventory.json', inventory), ('operation.json', playbook),
                              ('request.json', payload)]:
            path = work / name
            path.write_text(json.dumps(content), encoding='utf-8')
            path.chmod(0o600)
        env = backend_environment()
        self.output_paths = [work / 'controller-stdout', work / 'controller-stderr']
        self.output_streams = []
        try:
            for path in self.output_paths:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
                os.fchmod(fd, 0o600)
                self.output_streams.append(os.fdopen(fd, 'w+b'))
            self.process = subprocess.Popen(['ansible-playbook', '-i', str(work / 'inventory.json'),
            str(work / 'operation.json'), '--limit', self.target['host']], cwd=BACKEND, env=env,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                start_new_session=True)
            self.start_readers()
        except BaseException as error:
            self.record_transport_failure(error, 'ansible-controller-start')
            for stream in self.output_streams:
                stream.close()
            raise


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
            self.start_readers()
        except BaseException as error:
            if self.process is not None:
                self.kill()
                self.process.wait()
            for stream in streams:
                stream.close()
            self.record_transport_failure(error, 'native-target-start')
            raise
        finally:
            if streams:
                streams[0].close()

    def start_readers(self):
        for index, (pipe, stream) in enumerate(zip([self.process.stdout, self.process.stderr], self.output_streams)):
            reader = threading.Thread(target=self.read_channel,
                args=(pipe, stream, self.native and self.progress and index == 1, index), daemon=True)
            self.readers.append(reader)
            reader.start()

    def captured_evidence(self, index):
        prefix = bytes(self.capture_prefix[index])
        if self.capture_counts[index] > len(prefix):
            return prefix + b'\n[bounded child capture: middle omitted]\n' + bytes(self.capture_tail[index])
        return prefix

    def record_transport_failure(self, error, phase):
        """Durable bounded original evidence before receipt/spool cleanup.

        The existing private operation directory is the independent fallback if
        the protected host journal is unavailable. It contains no retry authority.
        """
        if getattr(error, '_transport_failure_recorded', False):
            return
        error._transport_failure_recorded = True
        if self.temporary is None or not Path(self.temporary.name).is_dir():
            from lifecycle import report_failure
            return report_failure(error, phase)
        self.retained = True
        observation = getattr(error, 'observation', {})
        if not isinstance(observation, dict):
            observation = {'observationAvailability': 'unavailable-invalid-type'}
        def safe_message(item):
            try:
                return str(item)[:4096]
            except Exception as formatting:
                return '[message unavailable: ' + type(formatting).__name__ + ']'
        error.observation = {**observation,
            'operationId': Path(self.temporary.name).name,
            'controllerExit': self.process.returncode if self.process else None,
            'effect': 'unknown-inspect-original-operation',
            'channels': [{'bytes': count, 'retainedBytes': len(prefix),
                          'truncated': count > len(prefix)}
                         for count, prefix in zip(self.capture_counts, self.capture_prefix)],
            'readerFailures': [{'type': type(item).__name__, 'message': safe_message(item)}
                               for item in self.reader_errors[:4]]}
        if not isinstance(error, (subprocess.CalledProcessError, subprocess.TimeoutExpired)):
            error.stdout, error.stderr = self.captured_evidence(0), self.captured_evidence(1)
            error.capture_bytes = dict(zip(['stdout', 'stderr'], self.capture_counts))
        if (not isinstance(error, (subprocess.CalledProcessError, subprocess.TimeoutExpired))
                and error.__cause__ is None and self.process is not None
                and self.process.returncode is not None and self.process.returncode != 0):
            child = subprocess.CalledProcessError(self.process.returncode if self.process else 255,
                'ansible-controller' if not self.native else 'native-target',
                output=self.captured_evidence(0), stderr=self.captured_evidence(1))
            error.__cause__ = child
        try:
            from lifecycle import report_failure
            for index, name in enumerate(['stdout-tail', 'stderr-tail']):
                if self.capture_counts[index] > len(self.capture_prefix[index]):
                    fd = os.open(Path(self.temporary.name) / name,
                                 os.O_CREAT | os.O_TRUNC | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
                    with os.fdopen(fd, 'wb') as tail:
                        tail.write(self.capture_tail[index])
                        tail.flush()
                        os.fsync(tail.fileno())
            path = Path(self.temporary.name) / 'failure.log'
            fd = os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            os.fchmod(fd, 0o600)
            os.close(fd)
            report_failure(error, phase, private_log=path)
            directory_fd = os.open(self.temporary.name, os.O_DIRECTORY | os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except Exception as recorder_error:
            # This fixed fallback does not invoke the failed formatter/recorder.
            print('RELAY_ANSIBLE_DIAGNOSTIC_UNAVAILABLE=' + type(recorder_error).__name__ +
                  ';original-private-channels-retained', file=sys.stderr, flush=True)
        print('RELAY_ANSIBLE_FAILURE=phase=' + phase + ';evidence=protected-transport/' +
              Path(self.temporary.name).name +
              ';effect=unknown;next=inspect-original-operation-and-private-transport-evidence-before-retry',
              file=sys.stderr, flush=True)

    def cleanup_output(self):
        for stream in getattr(self, 'output_streams', []):
            try:
                stream.close()
            except Exception as secondary:
                self.record_transport_failure(secondary, 'transport-channel-cleanup')
        if not self.retained and self.temporary is not None:
            try:
                self.temporary.cleanup()
            except Exception as secondary:
                self.record_transport_failure(secondary, 'transport-directory-cleanup')
                print('RELAY_ANSIBLE_WARNING=cleanup-unproven;original-result-preserved;inspect-before-retry',
                      file=sys.stderr, flush=True)

    def read_channel(self, pipe, stream, emit_progress=False, index=0):
        stored = 0
        writable = True
        pending = b''
        try:
            while True:
                chunk = pipe.read1(65536)
                if not chunk:
                    break
                self.capture_counts[index] += len(chunk)
                self.capture_tail[index].extend(chunk)
                del self.capture_tail[index][:-8192]
                self.capture_prefix[index].extend(chunk[:max(0, RESULT_LIMIT + 1 - len(self.capture_prefix[index]))])
                if emit_progress:
                    # A partial/oversized line never becomes public evidence.
                    from lifecycle import drain_progress
                    pending += chunk
                    while b'\n' in pending:
                        line, pending = pending.split(b'\n', 1)
                        if len(line) <= 4096:
                            drain_progress(line.decode('ascii', errors='replace'))
                    if len(pending) > 4096:
                        pending = b'oversized:'
                if writable and stored <= RESULT_LIMIT:
                    bounded = chunk[:RESULT_LIMIT + 1 - stored]
                    try:
                        stream.write(bounded)
                        stored += len(bounded)
                    except Exception as error:
                        # Continue draining the child even if durable capture
                        # fails; the independent bounded memory prefix survives.
                        self.reader_errors.append(error)
                        writable = False
            if writable:
                stream.flush()
                if hasattr(stream, 'fileno'):
                    try:
                        os.fsync(stream.fileno())
                    except __import__('io').UnsupportedOperation:
                        pass
        except Exception as error:
            self.reader_errors.append(error)
        finally:
            pipe.close()

    def pending_output(self):
        return any(reader.is_alive() for reader in self.readers)

    def warn_progress(self):
        if not self.progress_warning:
            print('RELAY_LIFECYCLE_WARNING=remote-drain-progress-unproven;inspect-protected-transport-evidence', flush=True)
            self.progress_warning = True

    def forward_progress(self, line):
        from lifecycle import drain_progress
        if line in self.forwarded_progress:
            return True
        if drain_progress(line):
            self.last_progress = line
            self.forwarded_progress[line] = None
            if len(self.forwarded_progress) > 2048:
                self.forwarded_progress.pop(next(iter(self.forwarded_progress)))
            return True
        return False

    def observe_remote_progress(self, timeout):
        result = run_target(self.target, self.key, ['/usr/bin/python3', '-I', '-c', DRAIN_PROGRESS_READ,
                            str(self.remote_progress)], timeout=timeout, local=self.local)
        if result.returncode:
            self.warn_progress()
        elif result.stdout:
            for line in result.stdout.splitlines():
                if not self.forward_progress(line):
                    self.warn_progress()

    def collect_native(self):
        try:
            output = []
            if self.reader_errors:
                raise ValueError('native-target-output-capture-failed')
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
                    raise ValueError('native-target-output-identity-unproven')
                stream.seek(0)
                raw = stream.read(RESULT_LIMIT + 1)
                if (len(raw) > RESULT_LIMIT or stamp(os.fstat(stream.fileno())) != stamp(before)
                        or stamp(path.lstat()) != stamp(before)):
                    raise ValueError('native-target-output-oversized-or-changed')
                output.append(raw.decode('utf-8'))
            self.result = {'rc': self.process.returncode, 'stdout': output[0], 'stderr': output[1]}
            if self.process.returncode:
                self.record_transport_failure(subprocess.CalledProcessError(self.process.returncode,
                    'native-target', output=output[0], stderr=output[1]), 'native-target')
        except (OSError, ValueError, UnicodeError) as error:
            self.record_transport_failure(error, 'native-target-receipt')
            self.result = {'rc': 255, 'stdout': '', 'stderr': 'ANSIBLE_TARGET_OPERATION_UNPROVEN\n'}
        finally:
            self.cleanup_output()
        return self.result['stdout'], self.result['stderr']

    @property
    def returncode(self):
        return self.result['rc'] if self.result is not None else self.process.returncode if self.process else None

    def poll(self):
        status = self.process.poll() if self.process else None
        # The old Ansible wrapper stayed alive until helper channels closed.
        # Preserve that completion frontier for every existing guard loop.
        return None if self.pending_output() else status

    def communicate(self, input=None, timeout=None):
        if self.result is not None:
            return self.result['stdout'], self.result['stderr']
        self.start(input)
        deadline = time.monotonic() + timeout if timeout is not None else None
        try:
            if self.remote_progress is not None:
                next_progress = time.monotonic() + 1
                while self.process.poll() is None:
                    remaining = max(0, deadline - time.monotonic()) if deadline is not None else 15
                    if remaining <= 0:
                        raise subprocess.TimeoutExpired('relay-target-operation', timeout)
                    if time.monotonic() >= next_progress:
                        try:
                            self.observe_remote_progress(min(15, remaining))
                        except (OSError, subprocess.SubprocessError, RuntimeError):
                            self.warn_progress()
                        next_progress = time.monotonic() + 5
                    remaining = max(0, deadline - time.monotonic()) if deadline is not None else 1
                    if remaining <= 0:
                        raise subprocess.TimeoutExpired('relay-target-operation', timeout)
                    try:
                        self.process.wait(timeout=min(1, remaining))
                    except subprocess.TimeoutExpired:
                        pass
            else:
                self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            if self.native:
                raise subprocess.TimeoutExpired('relay-target-operation', timeout) from None
            raise
        if self.readers:
            for reader in self.readers:
                reader.join(timeout=max(0, deadline - time.monotonic()) if deadline is not None else None)
                if reader.is_alive():
                    raise subprocess.TimeoutExpired('relay-target-operation', timeout)
        if self.native:
            return self.collect_native()
        try:
            if self.reader_errors:
                raise RuntimeError('ansible-controller-output-capture-failed')
            if self.result_path.stat().st_size > RESULT_LIMIT * 3:
                raise ValueError('ansible-target-receipt-oversized')
            result = json.loads(self.result_path.read_text())
            if (set(result) != {'rc', 'stdout', 'stderr'} or type(result['rc']) is not int
                    or any(not isinstance(result[k], str) or len(result[k].encode()) > RESULT_LIMIT
                           for k in ['stdout', 'stderr'])
                    or self.process.returncode != 0 and result['rc'] == 0):
                raise ValueError('ansible-target-receipt-invalid-or-controller-failed')
            self.result = result
            if self.remote_progress is not None:
                from lifecycle import DRAIN_PROGRESS_PATTERN
                import re
                lines = re.findall('(?m)^' + DRAIN_PROGRESS_PATTERN + '$', result['stderr'])
                if self.last_progress in lines:
                    # Final private stderr is chronological. Resume after the
                    # latest live observation so bounded dedup eviction cannot
                    # make old activity appear again after a later drain.
                    lines = lines[len(lines) - lines[::-1].index(self.last_progress):]
                for line in lines:
                    self.forward_progress(line)
                if re.search(r'(?m)^ANSIBLE_PROGRESS_CHANNEL_(?:UNPROVEN|CLEANUP_UNPROVEN|TRUNCATED)$', result['stderr']):
                    self.warn_progress()
            if result['rc'] != 0:
                failure = subprocess.CalledProcessError(result['rc'], 'target-operation',
                    output=result['stdout'], stderr=result['stderr'])
                self.record_transport_failure(failure, 'target-operation')
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            self.record_transport_failure(error, 'ansible-target-receipt')
            self.result = {'rc': 255, 'stdout': '', 'stderr': 'ANSIBLE_TARGET_OPERATION_UNPROVEN\n'}
        finally:
            self.cleanup_output()
        return self.result['stdout'], self.result['stderr']

    def terminate(self):
        self.cancelled = True
        if self.process:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        elif self.temporary is not None and not self.retained:
            self.temporary.cleanup()

    def kill(self):
        self.cancelled = True
        if self.process:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def wait(self, timeout=None):
        if self.process is None:
            return 255  # a failed launch is never an instruction to launch again
        bounded_cancel = self.cancelled
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


def run_target(target, key, argv, *, input=None, timeout=None, local=False, progress=False):
    process = TargetProcess(target, key, argv, local=local, progress=progress)
    dependency = progress if progress in ['source-preparation', 'source-verification', 'host-prerequisites'] else None
    started = time.monotonic()
    try:
        if dependency:
            print(f'RELAY_DEPLOYMENT_PROGRESS=target-operation;dependency={dependency};state=started', flush=True)
            deadline = started + timeout if timeout is not None else None
            while True:
                remaining = max(0, deadline - time.monotonic()) if deadline is not None else 30
                try:
                    output, errors = process.communicate(input=input, timeout=min(30, remaining))
                    break
                except subprocess.TimeoutExpired:
                    if deadline is not None and time.monotonic() >= deadline:
                        raise
                    # This is an observation of the same child, never another
                    # launch or an inference that elapsed work has succeeded.
                    print(f'RELAY_DEPLOYMENT_PROGRESS=target-operation;dependency={dependency};state=waiting;elapsed_seconds={int(time.monotonic()-started)}', flush=True)
            print(f'RELAY_DEPLOYMENT_PROGRESS=target-operation;dependency={dependency};state=child-completed;exit={process.returncode}', flush=True)
        else:
            output, errors = process.communicate(input=input, timeout=timeout)
        return subprocess.CompletedProcess(argv, process.returncode, output, errors)
    except BaseException as error:
        primary = error
        raise
    finally:
        primary = locals().get('primary')
        try:
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
        except BaseException as cleanup_error:
            process.record_transport_failure(cleanup_error, 'target-operation-cleanup')
            if primary is None:
                raise
            print('RELAY_ANSIBLE_WARNING=cleanup-unproven;primary-failure-preserved;inspect-before-retry',
                  file=sys.stderr, flush=True)
        if primary is not None:
            if isinstance(primary, subprocess.TimeoutExpired):
                primary.output = process.captured_evidence(0)
                primary.stderr = process.captured_evidence(1)
                primary.capture_bytes = dict(zip(['stdout', 'stderr'], process.capture_counts))
            # collect may have cleaned a successful child after a deadline; do
            # not fabricate a spool path that no longer exists.
            if process.temporary is not None and Path(process.temporary.name).is_dir():
                process.record_transport_failure(primary, 'target-operation-interrupted')
            else:
                from lifecycle import report_failure
                report_failure(primary, 'target-operation-interrupted')


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
    import traceback
    traceback.print_exc(limit=8)
    print('RELAY_TARGET_IDENTITY_UNPROVEN', file=sys.stderr)
    sys.exit(1)
'''


def qualify_target(target, key):
    result = run_target(target, key, ['/usr/bin/python3', '-I', '-c', TARGET_PROOF,
        target.get('connection', 'ssh'), target['hostFingerprint']], timeout=60)
    if result.returncode or result.stdout != 'RELAY_TARGET_IDENTITY=PASS\n':
        raise RuntimeError('target-identity-or-debian-capability-unproven') from subprocess.CalledProcessError(
            result.returncode, 'target-identity-proof', output=result.stdout, stderr=result.stderr)


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
                               stderr=sys.stderr, text=True)
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        if not selector.select(30):
            raise TimeoutError('guard-readiness-timeout')
        observed = process.stdout.readline().strip()
        if observed != value['ready']:
            raise ValueError('guard-readiness-mismatch;expected=' + value['ready'] + ';observed=' + observed[:4096])
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
    import traceback
    traceback.print_exc(limit=8)
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
    except BaseException as error:
        from lifecycle import report_failure
        report_failure(error, 'host-operation-guard')
        try:
            guard.close()
            guard.wait(timeout=30)
        except BaseException as secondary:
            report_failure(secondary, 'host-operation-guard-cleanup')
            print('RELAY_ANSIBLE_WARNING=guard-cleanup-unproven;primary-failure-preserved;inspect-before-retry',
                  file=sys.stderr, flush=True)
        finally:
            if guard.poll() is None:
                try:
                    guard.process.terminate()
                except BaseException as secondary:
                    report_failure(secondary, 'host-operation-guard-termination')
        raise
