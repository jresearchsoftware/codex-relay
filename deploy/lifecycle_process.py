"""Observe one lifecycle child without turning its exit into convergence proof."""
import os
import re
import signal
import subprocess
import sys
import threading
import time


CAPTURE_LIMIT = 256 * 1024
OMITTED = b'\n[bounded child capture: middle omitted]\n'


def retain_failure(error, result):
    """Keep a zero-exit malformed proof's streams behind its existing safe code."""
    for channel in ['stdout', 'stderr']:
        setattr(error, channel, getattr(result, channel, None))
    error.capture_bytes = getattr(result, 'capture_bytes', {
        channel: len(value if isinstance(value, bytes) else str(value).encode('utf-8'))
        for channel in ['stdout', 'stderr'] if (value := getattr(result, channel, None)) is not None})
    error.observation = {'childExit': result.returncode}
    return error


def run(argv, *, phase, dependency, timeout=None, interval=30, forward=None,
        input=None, stdout_proofs=(), **options):
    """Keep private bounded child evidence and report elapsed waits while quiet.

    Only an explicit caller validator forwards child lines. Capture keeps the
    first and last bytes and original sizes. Requested exact stdout proof lines
    are recognized over the full stream, independently of diagnostic clipping;
    only matches to caller-supplied lines are retained, never arbitrary output.
    Cleanup never replaces the primary exception, including cancellation.
    """
    if not all(re.fullmatch(r'[a-z][a-z0-9-]{0,79}', value) for value in [phase, dependency]):
        raise ValueError('lifecycle-child-progress-identity-invalid')
    expected = {line.encode('utf-8'): line for line in stdout_proofs}
    if any(not line or len(line) > 8192 or b'\n' in line or b'\r' in line for line in expected):
        raise ValueError('lifecycle-child-proof-line-invalid')
    matched = set()
    started = time.monotonic()
    captures = {channel: [bytearray(), bytearray()] for channel in ['stdout', 'stderr']}
    sizes = {'stdout': 0, 'stderr': 0}
    failures = []
    def secondary(error):
        if len(failures) < 8:
            failures.append(error)
    options['start_new_session'] = True
    process = None
    forwarding = threading.Event()
    forwarding.set()

    def captured(channel):
        first, last = captures[channel]
        separator = OMITTED if sizes[channel] > CAPTURE_LIMIT else b''
        return (bytes(first) + separator + bytes(last)).decode('utf-8', errors='replace')

    def observe(stream, channel):
        pending = bytearray()
        oversized = False
        def observe_line(line):
            if channel == 'stdout' and line in expected:
                matched.add(expected[line])
            if forward is not None and forwarding.is_set():
                try:
                    forward(line.decode('utf-8', errors='replace'))
                except Exception as error:
                    secondary(error)
        try:
            try:
                descriptor = stream.fileno()
            except (AttributeError, OSError, ValueError):
                descriptor = None  # In-memory adapters used by bounded callers.
            while True:
                chunk = os.read(descriptor, 4096) if descriptor is not None else stream.read(4096)
                if not chunk:
                    break
                if isinstance(chunk, str):
                    chunk = chunk.encode('utf-8')
                sizes[channel] += len(chunk)
                first, last = captures[channel]
                room = max(0, CAPTURE_LIMIT // 2 - len(first))
                first.extend(chunk[:room])
                last.extend(chunk[room:])
                del last[:-CAPTURE_LIMIT // 2]
                if (forward is None or not forwarding.is_set()) and (channel != 'stdout' or not expected):
                    continue
                pending.extend(chunk)
                while b'\n' in pending:
                    end = pending.index(b'\n')
                    line = bytes(pending[:end]); del pending[:end + 1]
                    if not oversized and len(line) <= 8192:
                        observe_line(line)
                    oversized = False
                if len(pending) > 8192:
                    pending.clear(); oversized = True
            # An EOF-terminated stdout line is still a complete proof line.
            # Preserve the existing newline-only public forwarding behavior.
            if channel == 'stdout' and not oversized and bytes(pending) in expected:
                matched.add(expected[bytes(pending)])
        except Exception as error:
            secondary(error)

    readers = []
    writer = None
    if input is not None:
        def write():
            try:
                process.stdin.write(input)
            except Exception as error:
                secondary(error)
            finally:
                try:
                    process.stdin.close()
                except Exception as error:
                    secondary(error)
        writer = threading.Thread(target=write, daemon=True)
    def evidence(error):
        error.stdout = captured('stdout')
        error.stderr = captured('stderr')
        error.capture_bytes = dict(sizes)
        if failures:
            error.observation = {'childChannelFailures': [
                {'type': type(failure).__name__, 'errno': getattr(failure, 'errno', None)}
                for failure in failures]}
        return error
    primary = None
    try:
        process = subprocess.Popen(argv, stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, **options)
        readers = [threading.Thread(target=observe, args=(getattr(process, channel), channel), daemon=True)
                   for channel in captures]
        for reader in readers:
            reader.start()
        if writer is not None:
            writer.start()
        print(f'RELAY_DEPLOYMENT_PROGRESS={phase};dependency={dependency};state=started', flush=True)
        next_progress = started + interval
        while process.poll() is None:
            now = time.monotonic()
            if timeout is not None and now - started >= timeout:
                raise subprocess.TimeoutExpired(argv, timeout)
            if now >= next_progress:
                print(f'RELAY_DEPLOYMENT_PROGRESS={phase};dependency={dependency};state=waiting;elapsed_seconds={int(now-started)}', flush=True)
                next_progress = now + interval
            time.sleep(min(0.05, interval))
        for reader in readers:
            reader.join(timeout=5)
        if process.returncode:
            print(f'RELAY_DEPLOYMENT_PROGRESS={phase};dependency={dependency};state=failed;exit={process.returncode}', flush=True)
            raise evidence(subprocess.CalledProcessError(process.returncode, argv))
        if failures or any(reader.is_alive() for reader in readers):
            raise RuntimeError('lifecycle-child-channel-unproven') from (failures[0] if failures else None)
        result = subprocess.CompletedProcess(argv, process.returncode,
            captured('stdout'), captured('stderr'))
        result.capture_bytes = dict(sizes)
        result.stdout_proofs = frozenset(matched)
        print(f'RELAY_DEPLOYMENT_PROGRESS={phase};dependency={dependency};state=child-completed', flush=True)
        return result
    except BaseException as error:
        primary = error
        raise
    finally:
        forwarding.clear()
        try:
            if process is not None:
                # The new session binds cleanup to this invocation's own group,
                # including children retaining a pipe after their parent exited.
                if process.poll() is None or any(reader.is_alive() for reader in readers):
                    def stop_group(signum):
                        try:
                            os.killpg(process.pid, signum)
                        except ProcessLookupError:
                            pass
                    stop_group(signal.SIGTERM)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        stop_group(signal.SIGKILL)
                        process.wait(timeout=5)
                    for reader in readers:
                        if reader.ident is not None:
                            reader.join(timeout=.25)
                    if any(reader.is_alive() for reader in readers):
                        stop_group(signal.SIGKILL)
                for reader in readers:
                    if reader.ident is not None:
                        reader.join(timeout=5)
                if writer is not None and writer.ident is not None:
                    writer.join(timeout=5)
                if any(reader.is_alive() for reader in readers) or writer is not None and writer.is_alive():
                    raise RuntimeError('lifecycle-child-cleanup-unproven')
                for channel in captures:
                    if not any(reader.is_alive() for reader in readers):
                        getattr(process, channel).close()
        except BaseException as cleanup:
            from lifecycle import report_failure
            report_failure(cleanup, 'lifecycle-child-cleanup')
            print('RELAY_LIFECYCLE_WARNING=child-cleanup-unproven;inspect-before-retry', file=sys.stderr, flush=True)
            if primary is None:
                raise
        finally:
            if primary is not None:
                evidence(primary)
