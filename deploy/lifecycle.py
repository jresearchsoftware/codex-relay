"""Small admission lifecycle composition over the existing upgrade primitive.

The root admission gate owns durable state. This module adds no journal or
deployment backend; a missing/uncertain proof leaves the gate closed.
"""
import re
import sys
import uuid


def require(condition, code):
    if not condition:
        raise ValueError(code)


def progress(phase, target):
    print(f'RELAY_LIFECYCLE_PROGRESS={phase};target={target}', flush=True)


DRAIN_PROGRESS_PATTERN = (
    r'ADMISSION_DRAIN_PROGRESS phase=drain active=[0-9]{1,10} unknown=[0-9]{1,10}'
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
