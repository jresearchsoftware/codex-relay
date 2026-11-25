"""Deterministic evidence checks for the native managed-pool maintenance jobs."""

import copy
import os
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import runner_reservation as reservation


TOKEN = 'synthetic-credential'
DISPATCH = {'config_repository': 'example/deployment', 'config_sha': 'a' * 40,
            'workflow_run_id': 101, 'workflow_run_attempt': 2}


def holder(slot, runner_id):
    return {'runnerId': runner_id, 'runnerGroupId': 14, 'runnerName': 'runner-' + slot,
            'runnerLabel': 'slot-label-' + slot, 'service': 'runner-' + slot + '.service',
            'runnerRoot': '/opt/codex-relay-pools/example/runners/' + slot, 'runnerUid': 1400}


def job(slot, job_id, binding):
    return {'id': job_id, 'name': reservation.holder_job_name(slot), 'run_id': 101,
            'head_sha': 'a' * 40, 'status': 'in_progress', 'conclusion': None,
            'runner_id': binding['runnerId'], 'runner_group_id': binding['runnerGroupId'],
            'runner_name': binding['runnerName'], 'labels': ['self-hosted', binding['runnerLabel']]}


@pytest.fixture
def native():
    holders = {'primary': holder('primary', 5), 'pool-2': holder('pool-2', 9)}
    holders['primary']['ownerTransport'] = {'pid': 900, 'started': '340',
                                            'cgroup': reservation.service_cgroup(holders['primary'])}
    rows = [job('primary', 901, holders['primary']), job('pool-2', 902, holders['pool-2'])]
    return holders, rows


def local_proof(slot, binding, environment, *, min_hold_seconds):
    assert slot == 'pool-2' and min_hold_seconds == 0
    assert environment == {b'GITHUB_RUN_ID': b'101', b'GITHUB_RUN_ATTEMPT': b'2',
                           b'GITHUB_REPOSITORY': b'example/deployment', b'GITHUB_SHA': b'a' * 40,
                           b'GITHUB_WORKFLOW_REF': b'example/deployment/' + reservation.WORKFLOW.encode()
                           + b'@refs/heads/main', b'GITHUB_JOB': b'reserve', b'RELAY_HOLDER_SLOT': b'pool-2'}
    return {'pid': 910, 'started': '480', 'cgroup': reservation.service_cgroup(binding),
            'workerPid': 909, 'workerStarted': '420'}


def verify(native, *, local_holder=local_proof, extra_count=0):
    holders, rows = native

    def api(path, token):
        assert path == '/repos/example/deployment/actions/runs/101/attempts/2/jobs?per_page=100'
        assert token == TOKEN
        return {'total_count': len(rows) + extra_count, 'jobs': copy.deepcopy(rows)}

    return reservation.verify_runner_reservation(token=TOKEN, workflow_run=DISPATCH, holders=holders,
                                                 api=api, local_holder=local_holder)


def test_exact_attempt_and_configured_jobs_with_local_evidence(native):
    result = verify(native)
    assert result == {'primary': {'jobId': 901, 'runnerId': 5, 'pid': 900,
                                   'started': '340', 'cgroup': '/system.slice/runner-primary.service'},
                      'pool-2': {'jobId': 902, 'runnerId': 9, 'pid': 910,
                                 'started': '480', 'cgroup': '/system.slice/runner-pool-2.service',
                                 'workerPid': 909, 'workerStarted': '420'}}


def test_waits_for_native_and_local_evidence(native):
    _, rows = native
    rows[1].update(status='queued', runner_id=None, runner_name=None)
    assert verify(native) is None
    rows[1].update(status='in_progress', runner_id=9, runner_name='runner-pool-2')
    assert verify(native, local_holder=lambda *args, **kwargs: None) is None
    rows.pop()
    assert verify(native) is None


@pytest.mark.parametrize(('field', 'value', 'error'), [
    ('run_id', 99, 'JOB_IDENTITY_CHANGED'),
    ('run_attempt', 1, 'JOB_IDENTITY_CHANGED'),
    ('head_sha', 'b' * 40, 'JOB_IDENTITY_CHANGED'),
    ('runner_id', 6, 'JOB_RUNNER_CHANGED'),
    ('runner_group_id', 19, 'JOB_RUNNER_CHANGED'),
    ('runner_name', 'another-runner', 'JOB_RUNNER_CHANGED'),
    ('labels', ['self-hosted', 'another-slot'], 'JOB_RUNNER_CHANGED'),
    ('name', 'unrelated job', 'JOB_NAME_CHANGED'),
    ('status', 'completed', 'JOB_NOT_RUNNING'),
    ('conclusion', 'cancelled', 'JOB_NOT_RUNNING'),
])
def test_foreign_or_terminal_jobs_fail_closed(native, field, value, error):
    native[1][1][field] = value
    with pytest.raises(reservation.RunnerReservationError, match=error):
        verify(native)


def test_incomplete_or_ambiguous_native_jobs_fail_closed(native):
    holders, rows = native
    with pytest.raises(reservation.RunnerReservationError, match='JOBS_INCOMPLETE'):
        verify(native, extra_count=1)
    duplicate = job('pool-2', 903, holders['pool-2'])
    rows.append(duplicate)
    with pytest.raises(reservation.RunnerReservationError, match='JOB_NAME_AMBIGUOUS'):
        verify(native)
    duplicate['name'] = 'unrelated job'
    with pytest.raises(reservation.RunnerReservationError, match='RUNNER_JOB_AMBIGUOUS'):
        verify(native)


def test_primary_requires_the_cgroup_proven_owner_transport(native):
    native[0]['primary']['ownerTransport']['cgroup'] = '/system.slice/another.service'
    with pytest.raises(reservation.RunnerReservationError, match='OWNER_TRANSPORT_UNPROVEN'):
        verify(native)


@pytest.fixture
def local(tmp_path, monkeypatch):
    slot = 'pool-2'
    binding = holder(slot, 9)
    binding['runnerUid'] = os.getuid()
    proc, cgroup = tmp_path / 'proc', tmp_path / 'cgroup'
    unit = cgroup / reservation.service_cgroup(binding).lstrip('/')
    unit.mkdir(parents=True)
    (unit / 'cgroup.procs').write_text('1\n20\n21\n')
    environment = {b'GITHUB_JOB': b'reserve', b'RELAY_HOLDER_SLOT': b'pool-2'}

    def process(pid, parent, executable):
        root = proc / str(pid)
        root.mkdir(parents=True)
        ticks = os.sysconf('SC_CLK_TCK') * pid
        stat_fields = ' '.join(['S', str(parent)] + ['0'] * 17 + [str(ticks)])
        (root / 'stat').write_text(f'{pid} (name with ) spaces) {stat_fields}\n')
        (root / 'cgroup').write_text(f'0::{reservation.service_cgroup(binding)}\n')
        (root / 'exe').symlink_to(executable)
        return root

    binary = Path(binding['runnerRoot']) / 'bin.2.338.2'
    process(1, 2, binary / 'Runner.Listener')
    process(20, 1, binary / 'Runner.Worker')
    node = process(21, 20, Path('/usr/bin/node').resolve())
    (node / 'cmdline').write_bytes(reservation.HOLDER_COMMAND)
    (node / 'environ').write_bytes(b'GITHUB_JOB=reserve\0RELAY_HOLDER_SLOT=pool-2\0TOKEN=ignored\0')
    monkeypatch.setattr(reservation.time, 'clock_gettime', lambda _: 25.0)

    def read(**kwargs):
        return reservation.observe_holder(slot, binding, environment, proc_root=proc, cgroup_root=cgroup, **kwargs)

    return read, proc, unit, binding


def test_expired_reservation_requires_both_exact_local_processes_to_release(local):
    read, proc, _, binding = local
    members = {'primary': {'service': 'primary.service'}, 'pool-2': binding}
    snapshots = {'primary': {'runnerId': 11}, 'pool-2': {'runnerId': 12}}
    receipt = {
        'primary': {'pid': 2, 'started': '1', 'cgroup': '/system.slice/primary.service',
                    'jobId': 101, 'runnerId': 11},
        'pool-2': {**read(), 'jobId': 102, 'runnerId': 12},
    }

    with pytest.raises(reservation.RunnerReservationError, match='RECOVERY_HOLDER_STILL_LIVE'):
        reservation.verify_released_reservation(members, snapshots, receipt, proc_root=proc)
    (proc / '21/stat').unlink()
    with pytest.raises(reservation.RunnerReservationError, match='RECOVERY_HOLDER_STILL_LIVE'):
        reservation.verify_released_reservation(members, snapshots, receipt, proc_root=proc)
    # Reuse of a PID with a different start time is a different process.
    receipt['pool-2']['workerStarted'] = '1'
    reservation.verify_released_reservation(members, snapshots, receipt, proc_root=proc)
    receipt['pool-2']['runnerId'] = 13
    with pytest.raises(reservation.RunnerReservationError, match='RECOVERY_RECEIPT_INVALID'):
        reservation.verify_released_reservation(members, snapshots, receipt, proc_root=proc)


def test_kernel_proves_exact_holder_beneath_stock_worker(local):
    read, _, _, _ = local
    result = read()
    assert result == {'pid': 21, 'workerPid': 20, 'started': str(21 * os.sysconf('SC_CLK_TCK')),
                      'workerStarted': str(20 * os.sysconf('SC_CLK_TCK')),
                      'cgroup': '/system.slice/runner-pool-2.service'}
    with pytest.raises(reservation.RunnerReservationError, match='HOLDER_EXPIRING'):
        read(min_hold_seconds=reservation.HOLDER_TIMEOUT_SECONDS - 4)


def test_disappearing_holder_is_not_positive_evidence(local):
    read, proc, unit, _ = local
    (proc / '21' / 'stat').unlink()
    assert read() is None
    (unit / 'cgroup.procs').write_text('1\n20\n')
    assert read() is None


@pytest.mark.parametrize(('field', 'value', 'error'), [
    ('cgroup', b'0::/system.slice/another.service\n', 'PROCESS_BINDING_CHANGED'),
    ('environ', b'GITHUB_JOB=reserve\0RELAY_HOLDER_SLOT=pool-3\0', 'HOLDER_ENVIRONMENT_CHANGED'),
    ('environ', b'GITHUB_JOB=reserve\0RELAY_HOLDER_SLOT=pool-2\0RELAY_HOLDER_SLOT=pool-3\0',
     'HOLDER_ENVIRONMENT_AMBIGUOUS'),
])
def test_live_process_identity_must_match_native_holder(local, field, value, error):
    read, proc, _, _ = local
    (proc / '21' / field).write_bytes(value)
    with pytest.raises(reservation.RunnerReservationError, match=error):
        read()
