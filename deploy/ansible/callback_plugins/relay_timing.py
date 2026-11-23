"""Aggregate callback: bounded wall observations, never Ansible data or names.

Default stdout stays installed. Item/retry callbacks are intentionally untouched;
runner results cover a whole host task, including retries and loops. Intervals
can overlap across hosts and dynamic includes, and are not exclusive CPU costs.
"""
from hashlib import sha256
import os
from pathlib import Path
import re
import time

from ansible.plugins.callback import CallbackBase


DOCUMENTATION = r'''
name: relay_timing
type: aggregate
short_description: Privacy-safe Relay wall-clock task observations
version_added: "1.0"
description:
  - Reports opaque source identifiers and wall intervals without task data.
requirements:
  - Enabled by the Relay deployment backend with an operation UUID.
'''


class CallbackModule(CallbackBase):
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = 'aggregate'
    CALLBACK_NAME = 'relay_timing'
    CALLBACK_NEEDS_ENABLED = True

    def __init__(self):
        super().__init__()
        self.operation = os.environ.get('RELAY_TIMING_OPERATION', '')
        self.invocation = os.environ.get('RELAY_TIMING_INVOCATION', '')
        self.enabled = bool(re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', self.operation) and re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', self.invocation))
        self.root = Path(__file__).resolve().parents[1]
        self.started = time.monotonic()
        self.pending = {}
        self.intervals = []
        self.roles = {}

    def now(self):
        return int((time.monotonic() - self.started) * 1000)

    def emit(self, fields):
        if self.enabled:
            self._display.display('RELAY_ANSIBLE_TIMING=operation=' + self.operation + ';invocation=' + self.invocation + ';' + fields)

    def identity(self, task, hidden):
        if hidden:
            return 'redacted', 'redacted'
        try:
            path, line = task.get_path().rsplit(':', 1)
            relative = Path(path).resolve().relative_to(self.root)
            if not line.isdigit() or not (self.root / relative).is_file():
                raise ValueError()
            parts = relative.parts
            role = parts[1] if len(parts) > 2 and parts[0] == 'roles' else 'playbook'
            # Only checked-in role directory identifiers, never rendered names.
            if not re.fullmatch(r'relay_[a-z_]{1,60}|playbook', role):
                role = 'other'
            key = sha256((relative.as_posix() + ':' + line).encode()).hexdigest()[:12]
            return key, role
        except (ValueError, OSError, AttributeError):
            return 'unavailable', 'other'

    def v2_runner_on_start(self, host, task):
        if self.enabled:
            self.pending[(host.get_name(), task._uuid)] = (self.now(), task)

    def finish(self, result, status):
        if not self.enabled:
            return
        item = self.pending.pop((result._host.get_name(), result._task._uuid), None)
        if item is None:
            return
        start, task = item
        end = self.now()
        hidden = bool(task.no_log or result._result.get('_ansible_no_log'))
        key, role = self.identity(task, hidden)
        self.intervals.append((start, end))
        span = self.roles.setdefault(role, [start, end, 0])
        span[0], span[1], span[2] = min(span[0], start), max(span[1], end), span[2] + 1
        self.emit(f'kind=task;task={key};role={role};state={status};start_ms={start};end_ms={end};wall_ms={end-start}')

    def v2_runner_on_ok(self, result):
        self.finish(result, 'ok')

    def v2_runner_on_failed(self, result, ignore_errors=False):
        self.finish(result, 'failed')

    def v2_runner_on_skipped(self, result):
        self.finish(result, 'skipped')

    def v2_runner_on_unreachable(self, result):
        self.finish(result, 'unreachable')

    def v2_playbook_on_stats(self, stats):
        if not self.enabled:
            return
        end = self.now()
        # Unfinished work is an observation gap, never fabricated task success.
        for role, (start, stop, count) in sorted(self.roles.items()):
            self.emit(f'kind=role;role={role};tasks={count};start_ms={start};end_ms={stop};wall_ms={stop-start}')
        active = 0
        stop = 0
        for start, finish in sorted(self.intervals):
            active += max(0, finish - max(stop, start))
            stop = max(stop, finish)
        self.emit(f'kind=summary;wall_ms={end};observed_union_ms={active};gap_ms={end-active};unfinished={len(self.pending)};overlap=possible')
