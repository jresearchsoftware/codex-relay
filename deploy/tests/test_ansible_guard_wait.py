"""Bounded readiness uses the original private guard and qualified transport."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ansible_transport as transport

pytestmark = pytest.mark.skipif(sys.platform != 'linux' or os.geteuid() != 0,
                                reason='isolated protected /run root fixtures')


def controller(path, action='wait-ready', prefix=''):
    return subprocess.Popen(['/usr/bin/python3', '-I', '-c', prefix + transport.GUARD_CONTROL,
                             str(path), action], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def await_active(process):
    # The controller must have observed the empty directory before replacement.
    time.sleep(0.15)
    assert process.poll() is None


def test_real_wait_ready_before_directory_creation_then_original_holder_eof_cleanup():
    path = Path('/run/task253-guard-wait-' + str(uuid.uuid4()))
    query = controller(path)
    holder = None
    try:
        await_active(query)
        helper = 'import sys,time;time.sleep(.2);print("FIXTURE_READY",flush=True);sys.stdin.read()'
        holder = subprocess.Popen(['/usr/bin/python3', '-I', '-c', transport.GUARD_SCRIPT, str(path)],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        holder.stdin.write(json.dumps({'argv': ['/usr/bin/python3', '-I', '-c', helper],
                                       'ready': 'FIXTURE_READY'}))
        holder.stdin.close()
        assert query.communicate(timeout=5) == ('READY\n', '')
        assert query.returncode == 0 and holder.poll() is None
        release = controller(path, 'release')
        assert release.communicate(timeout=5) == ('READY\n', '')
        assert release.returncode == 0
        assert holder.wait(timeout=5) == 0
        assert holder.stdout.read() == 'ANSIBLE_GUARD_RELEASED\n'
        assert not path.exists()
    finally:
        if query.poll() is None:
            query.kill(); query.wait()
        if holder is not None and holder.poll() is None:
            (path / 'release').touch(mode=0o600)
            holder.wait(timeout=5)


@pytest.mark.parametrize('change', ['replace', 'symlink', 'unsafe-mode', 'disappear', 'unsafe-ready'])
def test_wait_refuses_changed_or_unsafe_namespace_each_iteration(change):
    with tempfile.TemporaryDirectory(prefix='task253-guard-wait-', dir='/run') as temporary:
        path = Path(temporary)
        path.chmod(0o700)
        query = controller(path)
        previous = path.with_name(path.name + '-previous')
        try:
            await_active(query)
            if change in ['replace', 'symlink']:
                path.rename(previous)
                if change == 'replace':
                    path.mkdir(mode=0o700)
                else:
                    path.symlink_to(previous, target_is_directory=True)
            elif change == 'unsafe-mode':
                path.chmod(0o750)
            elif change == 'disappear':
                path.rmdir()
            else:
                (path / 'ready').symlink_to('/dev/null')
            query.communicate(timeout=5)
            assert query.returncode == 1
        finally:
            if query.poll() is None:
                query.kill(); query.wait()
            if path.is_symlink():
                path.unlink()
            if previous.exists():
                previous.rmdir()


def test_missing_directory_timeout_is_bounded_without_creating_state():
    path = Path('/run/task253-guard-wait-' + str(uuid.uuid4()))
    # An advancing test clock exercises the actual target timeout branch without
    # spending twenty seconds on a deliberately unavailable fixture.
    clock = 'import time\nvalues=iter([0,21]);time.monotonic=lambda:next(values)\n'
    query = controller(path, prefix=clock)
    assert query.communicate(timeout=5) == ('WAIT\n', '')
    assert query.returncode == 0 and not path.exists()


def test_failed_holder_is_not_relaunched_by_wait_or_cleanup(monkeypatch):
    created = []
    original = transport.GuardProcess
    class Observed(original):
        def __init__(self, *args):
            super().__init__(*args)
            created.append(self)
    monkeypatch.setattr(transport, 'GuardProcess', Observed)
    # Shorten only the target's waiting clock; real Ansible, the guard process,
    # failed helper and cleanup transport still execute unchanged.
    monkeypatch.setattr(transport, 'GUARD_CONTROL',
                        transport.GUARD_CONTROL.replace('+ 20', '+ 0.5'))
    with pytest.raises(RuntimeError, match='guard-unavailable'):
        transport.hold_target({'host': 'localhost', 'user': 'root', 'connection': 'local'}, None,
                              ['/usr/bin/false'], 'FIXTURE_READY')
    assert len(created) == 1
    assert created[0].poll() is not None
    assert not Path(created[0].directory).exists()
