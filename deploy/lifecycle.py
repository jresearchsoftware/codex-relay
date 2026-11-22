"""Small admission lifecycle composition over the existing upgrade primitive.

The root admission gate owns durable state. This module adds no journal or
deployment backend; a missing/uncertain proof leaves the gate closed.
"""
from contextvars import ContextVar
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
    previous = getattr(error, '_deployment_failure_evidence', None)
    if isinstance(previous, dict) and previous.get('status') in ['stored', 'submitted']:
        return previous
    def redact(value, partial=False):
        try:
            value = str(value)
        except Exception as failure:
            return '[message unavailable: ' + type(failure).__name__ + ']'
        for key, secret in os.environ.items():
            if re.search(r'TOKEN|SECRET|PASSWORD|PRIVATE_KEY|CREDENTIAL', key, re.I) and len(secret) >= 4:
                value = value.replace(secret, '[REDACTED]')
                if partial:
                    # A timeout or bounded capture may stop mid-credential.
                    # Linear overlap matching avoids quadratic scans for long
                    # environment credentials; never publish a surviving prefix.
                    def trim_suffix(text, word):
                        table = [0] * len(word)
                        matched = 0
                        for index in range(1, len(word)):
                            while matched and word[index] != word[matched]:
                                matched = table[matched - 1]
                            if word[index] == word[matched]:
                                matched += 1
                            table[index] = matched
                        matched = 0
                        for character in text[-len(word):]:
                            while matched and character != word[matched]:
                                matched = table[matched - 1]
                            if character == word[matched]:
                                matched += 1
                            if matched == len(word):
                                matched = table[matched - 1]
                        return text[:-matched] + '[REDACTED PARTIAL]' if matched >= 4 else text
                    separator = '\n[bounded child capture: middle omitted]\n'
                    pieces = value.split(separator)
                    for index, piece in enumerate(pieces):
                        piece = trim_suffix(piece, secret)
                        # A tail capture can also begin inside a credential.
                        reverse = trim_suffix(piece[::-1], secret[::-1])
                        pieces[index] = reverse[::-1].replace(']LAITRAP DETCADER[', '[REDACTED PARTIAL]')
                    value = separator.join(pieces)
        value = re.sub(r'(?s)-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)', '[REDACTED PRIVATE KEY]', value)
        value = re.sub(r'\b(?:github_pat_[A-Za-z0-9_]{8,}|gh[pousr]_[A-Za-z0-9]{8,}|sk-[A-Za-z0-9_-]{8,})', '[REDACTED]', value)
        value = re.sub(r'(?i)("(?:authorization|access[_-]?token|refresh[_-]?token|token|password|secret|api[_-]?key)"\s*:\s*)"(?:\\.|[^"\\])*(?:"|\\?$)', r'\1"[REDACTED]"', value)
        value = re.sub(r"(?i)((?:authorization|access[_-]?token|refresh[_-]?token|token|password|secret|api[_-]?key)[\"']?\s*[:=]\s*)'[^']*(?:'|$)", r"\1'[REDACTED]'", value)
        value = re.sub(r'(?i)((?:authorization|access[_-]?token|refresh[_-]?token|token|password|secret|api[_-]?key)[\"\x27]?\s*[:=]\s*[\"\x27]?)(?:(?:bearer|basic)\s+)?[^\s,\"\x27}]+', r'\1[REDACTED]', value)
        return value
    def bounded(value, limit):
        if len(value) <= limit:
            return value
        marker = '\n[diagnostic text: middle omitted]\n'
        head = (limit - len(marker)) // 2
        return value[:head] + marker + value[-(limit - len(marker) - head):]
    phase = phase if re.fullmatch(r'[A-Za-z0-9_-]{1,80}', phase) else 'deployment'
    causes, seen, current = [], set(), error
    while isinstance(current, BaseException) and id(current) not in seen and len(causes) < 4:
        seen.add(id(current))
        message = redact(current)
        row = {'type': type(current).__name__, 'message': bounded(message, 4096), 'messageTruncated': len(message) > 4096}
        if isinstance(current, OSError) and current.errno in errno.errorcode:
            row['errno'] = errno.errorcode[current.errno]
        if isinstance(current, subprocess.CalledProcessError):
            row['exit'] = current.returncode
            if isinstance(current.returncode, int) and current.returncode < 0:
                row['signal'] = -current.returncode
        if (isinstance(current, (subprocess.CalledProcessError, subprocess.TimeoutExpired))
                or isinstance(getattr(current, 'capture_bytes', None), dict)):
            for channel in ['stdout', 'stderr']:
                captured = getattr(current, channel, None)
                row[channel + 'Availability'] = 'available' if captured is not None else 'unavailable'
                if captured is not None:
                    captured_bytes = len(captured if isinstance(captured, bytes) else str(captured).encode('utf-8'))
                    row[channel + 'Bytes'] = getattr(current, 'capture_bytes', {}).get(channel, captured_bytes)
                    row[channel + 'Truncated'] = (row[channel + 'Bytes'] > captured_bytes
                        or (b'[bounded child capture: middle omitted]' in captured if isinstance(captured, bytes)
                            else '[bounded child capture: middle omitted]' in str(captured)))
            if getattr(current, 'stderr', None):
                stderr = redact(current.stderr.decode('utf-8', errors='replace') if isinstance(current.stderr, bytes) else current.stderr, partial=isinstance(current, subprocess.TimeoutExpired) or row.get('stderrTruncated', False))
                row['stderr'], row['stderrTruncated'] = bounded(stderr, 8192), len(stderr) > 8192 or row.get('stderrTruncated', False)
                if '[REDACTED' in stderr:
                    row['stderrAvailability'] = 'redacted'
            if getattr(current, 'stdout', None):
                stdout = redact(current.stdout.decode('utf-8', errors='replace') if isinstance(current.stdout, bytes) else current.stdout, partial=isinstance(current, subprocess.TimeoutExpired) or row.get('stdoutTruncated', False))
                row['stdout'], row['stdoutTruncated'] = bounded(stdout, 8192), len(stdout) > 8192 or row.get('stdoutTruncated', False)
                if '[REDACTED' in stdout:
                    row['stdoutAvailability'] = 'redacted'
        if isinstance(current, subprocess.TimeoutExpired):
            row['timeoutSeconds'] = current.timeout
        if hasattr(current, 'observation'):
            try:
                observation = redact(json.dumps(current.observation, ensure_ascii=True, sort_keys=True))
                row['observation'] = json.loads(observation) if len(observation) <= 8192 else {'status': 'bounded-omitted'}
            except Exception:
                row['observation'] = {'status': 'unavailable'}
        causes.append(row)
        current = current.__cause__ or current.__context__
    try:
        stack = redact(''.join(traceback.format_exception(error)))
    except Exception as failure:
        stack = '[stack unavailable: ' + type(failure).__name__ + ']'
    record = {'version': 1, 'phase': phase, 'causes': causes,
              'stack': bounded(stack, 32768), 'stackTruncated': len(stack) > 32768}
    correlation = {key: os.environ[name] for key, name in [('runId', 'GITHUB_RUN_ID'),
                   ('runAttempt', 'GITHUB_RUN_ATTEMPT')]
                   if re.fullmatch(r'[1-9][0-9]{0,19}', os.environ.get(name, ''))}
    if correlation:
        record['correlation'] = correlation
    if private_log is not None:
        record['protectedLog'] = str(private_log)
    payload = json.dumps(record, ensure_ascii=True, separators=(',', ':'))
    result = {'phase': phase, 'status': 'unavailable', 'reason': 'NO_CONFIGURED_HOST_STORE'}
    recorder = None
    root = os.geteuid() == 0 and os.getuid() == 0
    if private_log is not None:
        try:
            fd = os.open(private_log, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, 'w') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or (root and info.st_gid != 0) or stat.S_IMODE(info.st_mode) not in ({0o600, 0o640} if root else {0o600}) or info.st_nlink != 1:
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
    if result['status'] not in ['stored', 'submitted']:
        # Pre-install/owner controllers may have no root journal. Reuse the
        # deployment's private temporary-log mechanism, with no service/config
        # prerequisite and no public host path. Keep the original record bounded.
        try:
            import tempfile
            prefix = 'relay-' + os.urandom(6).hex() + '-causal-'
            descriptor, fallback_path = tempfile.mkstemp(prefix=prefix, suffix='.log')
            with os.fdopen(descriptor, 'w') as stream:
                os.fchmod(stream.fileno(), 0o600)
                if recorder:
                    record['recorderFailure'] = recorder
                stream.write('RELAY_DEPLOYMENT_CAUSAL_EVIDENCE=' + json.dumps(record, ensure_ascii=True, separators=(',', ':')) + '\n')
                stream.flush()
                os.fsync(stream.fileno())
            result = {'phase': phase, 'status': 'stored', 'destination': 'existing-private-deployment-log',
                      'reference': 'protected-log/' + os.path.basename(fallback_path)}
        except Exception as failure:
            result['reason'] = 'PRIVATE_LOG_FALLBACK_UNAVAILABLE'
            recorder = {'type': type(failure).__name__, **({'previous': recorder} if recorder else {})}
            if isinstance(failure, OSError) and failure.errno in errno.errorcode:
                recorder['errno'] = errno.errorcode[failure.errno]
    if recorder:
        result['recorderFailure'] = recorder
    summary = 'RELAY_DEPLOYMENT_FAILURE_EVIDENCE=' + json.dumps(result, sort_keys=True) + '\n'
    try:
        __import__('sys').stderr.write(summary)
        __import__('sys').stderr.flush()
    except Exception:
        # Independent descriptor fallback: a failed stream must not replace the
        # original operation error. Host/descriptor failure can defeat both.
        try:
            os.write(2, summary.encode('ascii'))
        except OSError:
            pass
    try:
        error._deployment_failure_evidence = result
    except (AttributeError, TypeError):
        pass  # Optional duplicate-report suppression owns no operation evidence.
    return result


def failure_reporting_source():
    """Freeze the same stdlib-only reporter into existing private target calls."""
    import inspect
    return inspect.getsource(report_failure) + '\n'


class LifecycleCheckError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise LifecycleCheckError(code)


def progress(phase, target):
    if phase in _LIFECYCLE_OPERATIONS:
        observe_failure_state(attempted=_LIFECYCLE_OPERATIONS[phase])
    print(f'RELAY_LIFECYCLE_PROGRESS={phase};target={target}', flush=True)


_DRAIN_PENDING_IDENTITY = (
    r'Task-[1-9][0-9]{0,15}/Step-[1-9][0-9]{0,15}/run-[1-9][0-9]{0,19}'
    r'(?:\[repository=[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}'
    r'(?:;slot=[a-z][a-z0-9-]{0,31})?\])?')
DRAIN_PROGRESS_PATTERN = (
    r'ADMISSION_DRAIN_PROGRESS phase=drain active=(?:[0-9]{1,10}|UNAVAILABLE) unknown=(?:[0-9]{1,10}|UNAVAILABLE)'
    r' elapsedSeconds=[0-9]{1,10}'
    r'(?: pending=(?:' + _DRAIN_PENDING_IDENTITY + r'(?:,' + _DRAIN_PENDING_IDENTITY + r'){0,19}|none))?'
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
    observe_failure_state(requested=target, operation_id=operation)
    if not already_quiesced:
        progress('QUIESCE', target)
        observe_admission_call('quiesce')
        gate('quiesce', '--operation', operation, '--target', target)
        observe_admission_result('quiesce')
    progress('DRAIN', target)
    if recovery:
        state = gate('status', '--operation', operation)
        require(state['phase'] == 'recovery-required'
                and not state['active'] and not state['unknown'], 'recovery-drain-unproven')
        observe_failure_state(admission='closed', boundary='drained')
        gate('recovery-target', '--operation', operation, '--target', target)
    else:
        drained = gate('drain', '--operation', operation, '--timeout', str(timeout))
        if isinstance(drained, dict) and drained.get('drained') is True:
            observe_admission_result('drain')
    if stop:
        progress('QUIESCED', target)
        return operation
    try:
        gate('phase', '--operation', operation, '--phase', 'applying')
        progress('APPLY', target)
        if _operation.get() is not None and _operation.get().get('phase') != 'resume':
            observe_target_mutation()
        result = apply()
        progress('ACTIVATE/VERIFY', target)
        require(verify(result, target), 'lifecycle-verification-unproven')
        observe_failure_state(boundary='activation', installed=target, activation='verified')
        gate('phase', '--operation', operation, '--phase', 'verified', '--revision', target)
        observe_admission_result('phase', 'verified')
        progress('RESUME', target)
        observe_admission_call('resume')
        gate('resume', '--operation', operation)
        observe_admission_result('resume')
    except Exception:
        # A failed state write must not obscure the original failure. The gate
        # was closed before apply; absence of a successful resume stays closed.
        try:
            gate('phase', '--operation', operation, '--phase', 'recovery-required')
            observe_admission_result('phase', 'recovery-required')
            progress('RECOVERY_REQUIRED', target)
        except Exception as recovery_error:
            report_failure(recovery_error, 'recovery-state-write')
            print('RELAY_LIFECYCLE_WARNING=recovery-state-write-unproven;admission-remains-closed;inspect-retained-operation',
                  file=sys.stderr, flush=True)
        raise
    progress('OPEN', target)
    return operation


# In-memory observations from the existing lifecycle and backend. The protected
# gate, manifest, installation receipts and deployment log remain authoritative.
_operation = ContextVar('deployment_operation', default=None)
_DEPLOYMENT_PHASES = frozenset({
    'install', 'check', 'apply', 'upgrade', 'post-check', 'inventory', 'bootstrap', 'reinstall',
    'reinstall-recover', 'workflow-project', 'workflow-verify', 'workflow-deployment-project',
    'runner-register', 'diagnose', 'activate', 'runner-enable', 'stale-dispose', 'tls-check',
    'tls-prepare', 'tls-dry-run', 'tls-issue', 'reviewer-credentials', 'writer-credentials',
    'codex-credentials', 'ingress', 'validate', 'owner-lifecycle-bootstrap', 'stop', 'resume', 'recover'
})
_LIFECYCLE_OPERATIONS = {
    'PREFLIGHT': 'target preflight', 'STAGING': 'source staging', 'LOCK': 'host lock acquisition',
    'QUIESCE': 'admission quiesce', 'DRAIN': 'admission drain', 'APPLY': 'target Apply',
    'ACTIVATE/VERIFY': 'activation and verification', 'VERIFY_INSTALLED': 'installed identity readback',
    'RESUME': 'admission resume'
}
_DEPLOYMENT_PROOFS = {
    'backend-recap': 'The backend did not supply its required zero-failure recap.',
    'installed-identity-proof': 'The required exact installed product and configuration receipt is missing.',
    'final-runtime-proof': 'The backend did not supply the required runtime validation for the selected product.',
    'upgrade-same-operation-activation-proof': 'The upgrade did not prove activation of the selected product in this operation.',
    'lifecycle-same-operation-activation-proof': 'The deployment did not prove activation of the selected product in this operation.',
    'post-check-drift': 'The read-only post-check observed configuration drift.'
}
_DEPLOYMENT_BOUNDARIES = {
    'inputs': 'input selection', 'configuration': 'consumer configuration validation',
    'host-preflight': 'target preflight', 'locked': 'invocation lock', 'installed-anchor': 'original installed identity',
    'quiesced': 'closed admission', 'drained': 'admission drain', 'backend-started': 'backend launch',
    'backend-returned': 'backend exit', 'installed': 'installed identity verification',
    'activation': 'runtime activation verification', 'open': 'admission reopening',
    'original-open': 'restoration of the original admission and availability'
}
_BACKEND_DEPENDENCIES = frozenset({
    'ansible-playbook', 'apt-package-metadata', 'release-artifacts', 'codex-package-and-runtime',
    'reviewer-build-and-runtime', 'production-runner-package', 'general-runner-package',
    'controller-entrypoints', 'reviewer-activation', 'reviewer-listener', 'service-health', 'runtime-verification',
    'public-deployment-primitive', 'admission-gate', 'source-git', 'workflow-projection', 'managed-pool'
})
_CONFIG_ACTIONS = {
    'clean-source': 'Use an accepted product checkout with a clean worktree.',
    'source-root': 'Select the root of the accepted Relay product checkout.',
    'ssh-identity-required': 'Supply the selected target’s configured SSH identity and fingerprint.',
    'operator-key': 'Verify the selected operator identity file is a regular local file.',
    'operator-key-identity': 'Verify the configured operator fingerprint against the selected SSH key.',
    'host-identity': 'Verify the selected host fingerprint through the trusted host identity record.',
    'consumer-projection': 'Verify the committed Relay integration directory against the selected consumer and product.',
    'explicit-installed-apply-recovery': 'Use the installed-configuration recovery command only for a matching installed Apply operation.',
    'explicit-local-owner-lifecycle-bootstrap-required': 'Use the owner lifecycle bootstrap command locally with its explicit authorization.'
}
_CHECK_ACTIONS = {
    'accepted-main-unavailable': 'Verify the selected repository’s trusted main commit through GitHub.',
    'GIT_INTENT_REPOSITORY_MISMATCH': 'Verify the source and consumer repository bindings for the selected owner run.',
    'GIT_INTENT_RUN_MISMATCH': 'Compare the original Actions run with the selected workflow, owner and configuration commit.',
    'consumer-dispatch-stale': 'Compare the run configuration commit with the current trusted consumer branch before selecting the owner operation.',
    'WORKFLOW_REVIEW_REQUIRED': 'Verify and integrate the generated workflow projection for the selected product and consumer configuration.',
    'resume-recovery-requires-diagnosis': 'Read the retained admission gate and verify the installed pair before using Resume.',
    'host-operation-guard-lost': 'Have the host operator read the retained operation and confirm the original host lock state.',
    'host-operation-guard-final-check': 'Have the host operator reconcile the original host operation guard before proceeding.',
    'lifecycle-verification-unproven': 'Run the supported read-only deployment diagnostic for this target and reconcile the retained operation.',
    'argument-contract': 'Correct the action and exact revision arguments for the selected owner lifecycle command.',
    'git-argument-contract': 'Correct the action, accepted revision, configuration commit and original run ID for the Git-backed lifecycle command.',
    'git-selected-config-invalid': 'Correct the selected consumer configuration commit against the selected product schema.',
    'git-consumer-readback-mismatch': 'Verify the selected consumer configuration commit and receipt through target inventory.',
    'lifecycle-public-primitive-failed': 'Run the supported read-only deployment diagnostic for the same target before repeating this operation.',
    'root-required': 'Use the installed owner lifecycle entrypoint with its configured host authorization.',
}
_READ_ONLY_PHASES = frozenset({'check', 'post-check', 'inventory', 'workflow-project', 'workflow-verify',
                              'workflow-deployment-project', 'diagnose', 'tls-check', 'validate'})


def start_failure_observation(operation, phase=None, run=None):
    return _operation.set({'operation': operation, 'phase': phase, 'run': run, 'boundary': 'inputs',
                           'admission': 'unknown', 'effect': 'not-entered', 'backend_attempts': 0})


def stop_failure_observation(token):
    _operation.reset(token)


def observe_failure_state(**observed):
    state = _operation.get()
    if state is not None:
        # Last proved installation/activation are independent of a subsequent
        # narrower backend check, journal write or gate acknowledgement.
        state.update(observed)


def observe_admission_call(action):
    if action in {'quiesce', 'resume', 'recovery-target'}:
        observe_failure_state(admission='unknown-write')


def observe_admission_result(action, phase=None):
    if action in {'quiesce', 'drain', 'resume', 'phase'}:
        observe_failure_state(admission='open' if action == 'resume' else 'closed')
    if action in {'quiesce', 'drain', 'resume'}:
        observe_failure_state(boundary={'quiesce': 'quiesced', 'drain': 'drained', 'resume': 'open'}[action])
    if action == 'phase' and phase == 'verified':
        # This is only called after the existing, successful guarded runtime
        # and installation checks. It is not inferred from an Ansible exit.
        state = _operation.get()
        if state is not None:
            observe_failure_state(boundary='activation', installed=state.get('requested'), activation='verified')


def observe_backend_start():
    state = _operation.get()
    if state is not None:
        observe_failure_state(boundary='backend-started', backend_attempts=state['backend_attempts'] + 1,
                              attempted='deployment backend', backend='ansible-playbook', backend_exit=None)


def observe_target_mutation():
    state = _operation.get()
    if state is not None and state.get('phase') not in _READ_ONLY_PHASES:
        observe_failure_state(effect='possible', installed=None, activation=None)


def deployment_failure(error, evidence=None):
    """Compose ordinary command output from safe observations, with an existing protected reference."""
    import errno
    import os
    import subprocess
    from git_intent import GitHubRequestError
    state = _operation.get() or {}
    details = {}
    current = error
    for _ in range(5):
        if current is None:
            break
        if isinstance(current, GitHubRequestError):
            details.setdefault('github', current.observation)
        elif isinstance(current, subprocess.TimeoutExpired):
            details.setdefault('cause', 'A deployment dependency exceeded its deadline.')
        elif isinstance(current, subprocess.CalledProcessError):
            dependency = getattr(current, 'deployment_dependency', None)
            if dependency == 'public-deployment-primitive':
                # Only the fixed child protocol is read. Extract numeric exit
                # and fixed dependencies from its existing progress, never text.
                stream = current.output or ''
                if isinstance(stream, str):
                    for match in re.finditer(r'(?m)^RELAY_DEPLOYMENT_PROGRESS=backend;dependency=([a-z-]+);state=failed;exit=(-?[0-9]{1,3});elapsed_seconds=[0-9]{1,10}$', stream):
                        if match[1] in _BACKEND_DEPENDENCIES:
                            details['child_backend'] = (match[1], int(match[2]))
            if current.returncode:
                details.setdefault('cause', f'A deployment dependency {"ended on signal " + str(-current.returncode) if current.returncode < 0 else "exited with code " + str(current.returncode)}.')
        elif isinstance(current, InterruptedError) or isinstance(current, KeyboardInterrupt):
            details.setdefault('cause', 'The operation was interrupted.')
        elif isinstance(current, OSError) and current.errno in errno.errorcode:
            details.setdefault('cause', f'The operating system reported {errno.errorcode[current.errno]}.')
        elif isinstance(current, (ValueError, RuntimeError)):
            code = str(current).split(';', 1)[0]
            # Config validation uses named fields. Exclude input values, arbitrary
            # exception messages, and every suffix after the source-owned field.
            field = re.match(r'^INVALID_DEPLOYMENT_CONFIG:([A-Za-z][A-Za-z0-9_.-]{0,159})(?=[:;]|$)', code)
            if field:
                details.setdefault('check', field[1])
                action = _CONFIG_ACTIONS.get(field[1], f'Correct the {field[1]} check in the selected deployment input.')
                details.setdefault('action', action)
            elif code in _CHECK_ACTIONS:
                details.setdefault('check', code)
                details.setdefault('action', _CHECK_ACTIONS[code])
            elif isinstance(current, LifecycleCheckError) and re.fullmatch('[a-z][a-z0-9-]{0,100}', code):
                details.setdefault('check', code)
            elif type(current).__name__ == 'PoolError' and re.fullmatch(r'MANAGED_POOL_[A-Z_]{1,100}', code):
                details.setdefault('check', code)
                details.setdefault('action', 'Verify the selected managed runner group and its trusted workflow access in pool preflight.')
        current = current.__cause__
    phase = state.get('phase') if state.get('phase') in _DEPLOYMENT_PHASES else 'operation'
    operation = 'Owner Relay lifecycle' if state.get('operation') == 'owner' else 'Relay deployment'
    boundary = _DEPLOYMENT_BOUNDARIES.get(state.get('boundary'), 'input selection')
    requested = state.get('requested')
    installed = state.get('installed')
    run = state.get('run') or os.environ.get('GITHUB_RUN_ID')
    correlation = f' (Actions run {run})' if re.fullmatch(r'[1-9][0-9]{0,19}', str(run)) else ''
    sentences = [f'{operation} {phase} failed{correlation}. Last verified boundary was {boundary}.']
    attempted = state.get('attempted')
    if attempted in _LIFECYCLE_OPERATIONS.values() or attempted == 'deployment backend':
        sentences.append(f'Relay was performing {attempted}.')
    if isinstance(requested, str) and re.fullmatch('[0-9a-f]{40}', requested):
        sentences.append(f'Selected product {requested}.')
    config = state.get('config')
    if isinstance(config, str) and re.fullmatch('[0-9a-f]{40}', config):
        sentences.append(f'Selected configuration commit {config}.')
    operation_id = state.get('operation_id')
    if isinstance(operation_id, str) and re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', operation_id):
        sentences.append(f'Admission operation {operation_id}.')
    if details.get('check'):
        check = details['check']
        sentences.append(_DEPLOYMENT_PROOFS.get(check, f'The {check} check failed.'))
    backend = state.get('backend')
    exit_code = state.get('backend_exit')
    github = details.get('github')
    if github:
        status = github['status']
        detail = {'timeout': 'timed out', 'network': 'failed at the network boundary',
                  'rate-limit': 'was rate-limited', 'invalid-response': 'returned a response that did not decode',
                  'transport-unknown': 'failed without a recognized transport cause'}.get(github['reason'], 'failed')
        http = f' (HTTP {status})' if type(status) is int and 100 <= status <= 599 else ''
        os_code = f' ({github["osCode"]})' if github['osCode'] else ''
        stopped = {'attempt-limit': 'the read attempt limit was reached', 'deadline': 'the deadline left no time to retry',
                   'provider-delay': 'the provider-directed wait exceeded the read budget',
                   'non-transient': 'the failure did not qualify for retry',
                   'mutation': 'the request can have an effect and must not be repeated blindly'}[github['stopped']]
        attempts = github['attempts']
        sentences.append(f'GitHub {github["method"]} ({github["endpoint"]}) {detail}{http}{os_code}. '
                         f'{attempts} request attempt{"s" if attempts != 1 else ""} ({max(0, attempts - 1)} retries). '
                         f'Recovery stopped because {stopped}.')
    if 'child_backend' in details:
        backend, exit_code = details['child_backend']
    if backend in _BACKEND_DEPENDENCIES and isinstance(exit_code, int) and exit_code != 0:
        action = f'ended on signal {-exit_code}' if exit_code < 0 else f'exited with code {exit_code}'
        sentences.append(f'Ansible {action} while reporting {backend}.')
    elif not github and 'cause' in details:
        sentences.append(details['cause'])
    elif not github and not details.get('check'):
        sentences.append('The cause at the failed boundary is unconfirmed.')
    attempts = state.get('backend_attempts', 0)
    if attempts:
        sentences.append(f'{attempts} backend invocation{"s" if attempts != 1 else ""} started in this command.')
    sentences.append('Relay did not automatically repeat this operation.')
    effect = state.get('effect')
    if effect == 'not-entered':
        sentences.append('This invocation did not enter a target installation or activation mutation.')
    if isinstance(installed, str) and re.fullmatch('[0-9a-f]{40}', installed):
        sentences.append(f'Last verified installed product was {installed}.')
    else:
        sentences.append('The installed product is unverified.')
    sentences.append('Runtime activation was verified.' if state.get('activation') == 'verified' else 'Runtime activation is unverified.')
    admission = state.get('admission')
    sentences.append({'closed': 'The last acknowledged gate state was closed.',
                      'open': 'The last acknowledged gate state was open.'}.get(admission, 'Admission state is unverified.'))
    reference = state.get('log') or (evidence or {}).get('reference')
    if re.fullmatch(r'protected-log/relay-[0-9a-f]{12}-[a-z-]{1,40}-[A-Za-z0-9_-]{6,32}\.log', reference or ''):
        sentences.append(f'Protected evidence reference {reference}.')
    elif (evidence or {}).get('status') == 'submitted':
        sentences.append('Protected evidence was submitted to the codex-relay-deployment host journal.')
    elif (evidence or {}).get('status') == 'unavailable':
        sentences.append('Protected evidence retention could not be verified.')
    action = details.get('action') if effect == 'not-entered' and admission not in {'closed', 'unknown-write'} else None
    if not action and github and effect == 'not-entered' and admission not in {'closed', 'unknown-write'}:
        if github['reason'] == 'rate-limit':
            action = 'Check the GitHub rate-limit reset for the configured reader before selecting another owner operation.'
        elif github['method'] == 'GET' and github['status'] in {401, 403, 404}:
            action = 'Verify the configured read credential and selected repository binding.'
        elif github['method'] == 'GET':
            action = 'Verify that the host can read the selected GitHub repository before selecting another owner operation.'
    if not action:
        action = 'Run the supported read-only deployment diagnostic for the same target before repeating this operation.'
    sentences.append('Next action: ' + action)
    return ' '.join(sentences)


def print_terminal_failure(error, phase, recorder):
    try:
        evidence = recorder(error, phase)
    except Exception:
        evidence = {'status': 'unavailable'}
    print(deployment_failure(error, evidence), file=sys.stderr, flush=True)
