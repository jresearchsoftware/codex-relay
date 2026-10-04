"""Small admission lifecycle composition over the existing upgrade primitive.

The root admission gate owns durable state. This module adds no journal or
deployment backend; a missing/uncertain proof leaves the gate closed.
"""
import uuid


def require(condition, code):
    if not condition:
        raise ValueError(code)


def progress(phase, target):
    print(f'RELAY_LIFECYCLE_PROGRESS={phase};target={target}', flush=True)


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
        progress('APPLY', target)
        gate('phase', '--operation', operation, '--phase', 'applying')
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
        except Exception:
            pass
        raise
    progress('OPEN', target)
    return operation
