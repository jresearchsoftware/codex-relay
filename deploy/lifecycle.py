"""Small admission lifecycle composition over the existing upgrade primitive.

The root admission gate owns durable state. This module adds no journal or
deployment backend; a missing/uncertain proof leaves the gate closed.
"""
import re
import sys
import uuid


def public_log_reference(path):
    """Expose a minted log identity without publishing its host location."""
    from pathlib import Path
    name = Path(path).name
    if re.fullmatch(r'relay-[0-9a-f]{12}-[a-z-]{1,40}-[A-Za-z0-9_-]{6,32}\.log', name):
        return 'protected-log/' + name
    return 'protected-deployment-log'


def report_failure(error, phase, *, private_log=None):
    """Retain bounded causal detail in an existing protected log or host journal.

    This function is also embedded in the private, frozen target helper source.
    Public output contains a safe reference and recorder failures independently;
    messages, paths, stacks and subprocess evidence stay in the host channel.
    """
    import errno
    import json
    import os
    import re
    import stat
    import subprocess
    import traceback
    if hasattr(error, '_deployment_failure_evidence'):
        return error._deployment_failure_evidence
    def redact(value):
        value = str(value)
        for key, secret in os.environ.items():
            if re.search(r'TOKEN|SECRET|PASSWORD|PRIVATE_KEY|CREDENTIAL', key, re.I) and len(secret) >= 4:
                value = value.replace(secret, '[REDACTED]')
        value = re.sub(r'(?s)-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)', '[REDACTED PRIVATE KEY]', value)
        value = re.sub(r'\b(?:github_pat_[A-Za-z0-9_]{8,}|gh[pousr]_[A-Za-z0-9]{8,}|sk-[A-Za-z0-9_-]{8,})', '[REDACTED]', value)
        value = re.sub(r'(?i)("(?:authorization|access[_-]?token|refresh[_-]?token|token|password|secret|api[_-]?key)"\s*:\s*)"(?:\\.|[^"\\])*(?:"|\\?$)', r'\1"[REDACTED]"', value)
        value = re.sub(r"(?i)((?:authorization|access[_-]?token|refresh[_-]?token|token|password|secret|api[_-]?key)[\"']?\s*[:=]\s*)'[^']*(?:'|$)", r"\1'[REDACTED]'", value)
        value = re.sub(r'(?i)((?:authorization|access[_-]?token|refresh[_-]?token|token|password|secret|api[_-]?key)[\"\x27]?\s*[:=]\s*[\"\x27]?)(?:(?:bearer|basic)\s+)?[^\s,\"\x27}]+', r'\1[REDACTED]', value)
        return value[:65536]
    phase = phase if re.fullmatch(r'[A-Za-z0-9_-]{1,80}', phase) else 'deployment'
    causes, seen, current = [], set(), error
    while isinstance(current, BaseException) and id(current) not in seen and len(causes) < 4:
        seen.add(id(current))
        message = redact(current)
        row = {'type': type(current).__name__, 'message': message[:4096], 'messageTruncated': len(message) > 4096}
        if isinstance(current, OSError) and current.errno in errno.errorcode:
            row['errno'] = errno.errorcode[current.errno]
        if isinstance(current, subprocess.CalledProcessError):
            row['exit'] = current.returncode
        if isinstance(current, (subprocess.CalledProcessError, subprocess.TimeoutExpired)):
            for channel in ['stdout', 'stderr']:
                captured = getattr(current, channel, None)
                row[channel + 'Availability'] = 'available' if captured is not None else 'unavailable'
                if captured is not None:
                    row[channel + 'Bytes'] = len(captured if isinstance(captured, bytes) else str(captured).encode('utf-8'))
            if current.stderr:
                stderr = redact(current.stderr.decode('utf-8', errors='replace') if isinstance(current.stderr, bytes) else current.stderr)
                row['stderr'], row['stderrTruncated'] = stderr[:8192], len(stderr) > 8192
                if '[REDACTED' in stderr:
                    row['stderrAvailability'] = 'redacted'
            if current.stdout:
                stdout = redact(current.stdout.decode('utf-8', errors='replace') if isinstance(current.stdout, bytes) else current.stdout)
                row['stdout'], row['stdoutTruncated'] = stdout[:8192], len(stdout) > 8192
                if '[REDACTED' in stdout:
                    row['stdoutAvailability'] = 'redacted'
        if isinstance(current, subprocess.TimeoutExpired):
            row['timeoutSeconds'] = current.timeout
        if hasattr(current, 'observation'):
            try:
                observation = redact(json.dumps(current.observation, ensure_ascii=True, sort_keys=True))
                row['observation'] = json.loads(observation) if len(observation) <= 8192 else {'status': 'bounded-omitted'}
            except (TypeError, ValueError, RecursionError):
                row['observation'] = {'status': 'unavailable'}
        causes.append(row)
        current = current.__cause__ or current.__context__
    stack = redact(''.join(traceback.format_exception(error)))
    record = {'version': 1, 'phase': phase, 'causes': causes,
              'stack': stack[:32768], 'stackTruncated': len(stack) > 32768}
    if private_log is not None:
        record['protectedLog'] = str(private_log)
    payload = json.dumps(record, ensure_ascii=True, separators=(',', ':'))
    result = {'phase': phase, 'status': 'unavailable', 'reason': 'NO_CONFIGURED_HOST_STORE'}
    recorder = None
    root = os.geteuid() == 0 and os.getuid() == 0
    if root and private_log is not None:
        try:
            fd = os.open(private_log, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, 'w') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_gid != 0 or stat.S_IMODE(info.st_mode) not in {0o600, 0o640} or info.st_nlink != 1:
                    raise ValueError('protected-log-unproven')
                stream.write('RELAY_DEPLOYMENT_CAUSAL_EVIDENCE=' + payload + '\n')
                stream.flush()
                os.fsync(stream.fileno())
            result = {'phase': phase, 'status': 'stored', 'destination': 'existing-protected-deployment-log'}
        except Exception as failure:
            recorder = {'type': type(failure).__name__}
            if isinstance(failure, OSError) and failure.errno in errno.errorcode:
                recorder['errno'] = errno.errorcode[failure.errno]
            record['recorderFailure'] = {**recorder, 'message': redact(failure)[:4096]}
            payload = json.dumps(record, ensure_ascii=True, separators=(',', ':'))
    if result['status'] != 'stored' and root:
        try:
            journal = os.stat('/run/systemd/journal/socket', follow_symlinks=False)
            if not stat.S_ISSOCK(journal.st_mode) or journal.st_uid != 0:
                raise ValueError('host-journal-unproven')
            written = subprocess.run(['/usr/bin/logger', '--journald'],
                input='SYSLOG_IDENTIFIER=codex-relay-deployment\nPRIORITY=3\nMESSAGE=' + payload + '\n',
                text=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=5, check=False)
            if written.returncode:
                raise subprocess.CalledProcessError(written.returncode, '/usr/bin/logger --journald', stderr=written.stderr)
            result = {'phase': phase, 'status': 'submitted', 'destination': 'existing-host-journal',
                      'identifier': 'codex-relay-deployment', 'readback': 'not-performed'}
        except Exception as failure:
            result['reason'] = 'HOST_JOURNAL_UNAVAILABLE'
            recorder = {'type': type(failure).__name__, **({'previous': recorder} if recorder else {})}
            if isinstance(failure, OSError) and failure.errno in errno.errorcode:
                recorder['errno'] = errno.errorcode[failure.errno]
            if isinstance(failure, subprocess.CalledProcessError):
                recorder['exit'] = failure.returncode
                recorder['messageAvailability'] = 'redacted'
    if recorder:
        result['recorderFailure'] = recorder
    print('RELAY_DEPLOYMENT_FAILURE_EVIDENCE=' + json.dumps(result, sort_keys=True), file=__import__('sys').stderr, flush=True)
    try:
        error._deployment_failure_evidence = result
    except (AttributeError, TypeError):
        pass  # Optional duplicate-report suppression owns no operation evidence.
    return result


def failure_reporting_source():
    """Freeze the same stdlib-only reporter into existing private target calls."""
    import inspect
    return inspect.getsource(report_failure) + '\n'


def require(condition, code):
    if not condition:
        raise ValueError(code)


def progress(phase, target):
    print(f'RELAY_LIFECYCLE_PROGRESS={phase};target={target}', flush=True)


DRAIN_PROGRESS_PATTERN = (
    r'ADMISSION_DRAIN_PROGRESS phase=drain active=(?:[0-9]{1,10}|UNAVAILABLE) unknown=(?:[0-9]{1,10}|UNAVAILABLE)'
    r' elapsedSeconds=[0-9]{1,10}'
    r'(?: pending=(?:Task-[1-9][0-9]{0,15}/Step-[1-9][0-9]{0,15}/run-[1-9][0-9]{0,19}'
    r'(?:,Task-[1-9][0-9]{0,15}/Step-[1-9][0-9]{0,15}/run-[1-9][0-9]{0,19}){0,19}|none))?'
    r' reason=(?:waiting-for-controllers|drained|inventory-unknown|lock-or-inventory-unavailable)')


def drain_progress(line):
    """Forward only the admission CLI's bounded, nonsecret progress grammar.

    stdout remains the single JSON capability result. Arbitrary stderr, task
    descriptions, configuration and backend output stay in their private channel.
    """
    if len(line) <= 4096 and re.fullmatch(DRAIN_PROGRESS_PATTERN, line):
        print(line, flush=True)
        return True
    return False


def execute(gate, target, apply, verify, *, operation=None, timeout=1800,
            already_quiesced=False, stop=False, recovery=False):
    """Call trusted capabilities, keeping failure evidence in the existing gate.

    `apply` is exactly one public apply/upgrade. `verify` consumes its same-call
    runtime proof and protected installed identity, never the install exit alone.
    Rollback/recovery can use the same composition with an explicitly selected
    previously accepted target and the retained operation, after diagnosis.
    """
    operation = operation or str(uuid.uuid4())
    if not already_quiesced:
        progress('QUIESCE', target)
        gate('quiesce', '--operation', operation, '--target', target)
    progress('DRAIN', target)
    if recovery:
        state = gate('status', '--operation', operation)
        require(state['phase'] == 'recovery-required'
                and not state['active'] and not state['unknown'], 'recovery-drain-unproven')
        gate('recovery-target', '--operation', operation, '--target', target)
    else:
        gate('drain', '--operation', operation, '--timeout', str(timeout))
    if stop:
        progress('QUIESCED', target)
        return operation
    try:
        gate('phase', '--operation', operation, '--phase', 'applying')
        progress('APPLY', target)
        result = apply()
        progress('ACTIVATE/VERIFY', target)
        require(verify(result, target), 'lifecycle-verification-unproven')
        gate('phase', '--operation', operation, '--phase', 'verified', '--revision', target)
        progress('RESUME', target)
        gate('resume', '--operation', operation)
    except Exception:
        # A failed state write must not obscure the original failure. The gate
        # was closed before apply; absence of a successful resume stays closed.
        try:
            gate('phase', '--operation', operation, '--phase', 'recovery-required')
            progress('RECOVERY_REQUIRED', target)
        except Exception:
            print('RELAY_LIFECYCLE_WARNING=recovery-state-write-unproven;admission-remains-closed;inspect-retained-operation',
                  file=sys.stderr, flush=True)
        raise
    progress('OPEN', target)
    return operation
