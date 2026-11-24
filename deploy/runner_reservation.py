"""Read exact GitHub and kernel evidence for an owner Apply's runner reservations."""

import os
from pathlib import Path
import re
import time

from git_intent import WORKFLOW, github_api


HOLDER_TIMEOUT_SECONDS = 4 * 60 * 60
MAX_JOBS = 64
MAX_UNIT_PROCESSES = 128
HOLDER_COMMAND = b'/usr/bin/node\0--input-type=module\0'


class RunnerReservationError(ValueError):
    """Only fixed codes and configured slots are exposed to failure reporting."""


def require(condition, code, slot=None):
    if not condition:
        error = RunnerReservationError('RUNNER_RESERVATION_' + code)
        if slot is not None:
            error.observation = {'slot': slot}
        raise error


def positive(value):
    return type(value) is int and 0 < value <= 9007199254740991


def valid_text(value, pattern):
    return isinstance(value, str) and re.fullmatch(pattern, value) is not None


def holder_job_name(slot):
    return 'lifecycle' if slot == 'primary' else 'Reserve General runner ' + slot


def service_cgroup(holder):
    return '/system.slice/' + holder['service']


def read_bounded(path, limit):
    with path.open('rb') as stream:
        value = stream.read(limit + 1)
    require(len(value) <= limit, 'PROCESS_EVIDENCE_LIMIT')
    return value


def process_identity(root):
    # comm is parenthesized and may itself contain spaces or parentheses.
    fields = read_bounded(root / 'stat', 4096).rpartition(b') ')[2].split()
    require(len(fields) >= 20 and fields[1].isdigit() and fields[19].isdigit(),
            'PROCESS_STAT_INVALID')
    if fields[0] in (b'Z', b'X'):
        return None
    return int(fields[1]), fields[19].decode('ascii')


def verify_process_binding(root, holder, group, slot):
    groups = read_bounded(root / 'cgroup', 4096).splitlines()
    require(root.stat().st_uid == holder['runnerUid'] and b'0::' + group.encode('ascii') in groups,
            'PROCESS_BINDING_CHANGED', slot)


def runner_binary(path, holder, name):
    # GitHub's native updater can change `bin` into a versioned directory link.
    binary = Path(path)
    return (binary.parent.parent == Path(holder['runnerRoot']) and binary.name == name
            and re.fullmatch(r'bin(?:\.[0-9]+\.[0-9]+\.[0-9]+)?', binary.parent.name) is not None)


def observe_holder(slot, holder, expected_environment, *, proc_root=Path('/proc'),
                   cgroup_root=Path('/sys/fs/cgroup'), min_hold_seconds=0):
    """Corroborate a native job with one exact live Worker and its fixed child."""
    group = service_cgroup(holder)
    unit = cgroup_root / group.lstrip('/')
    try:
        pids = read_bounded(unit / 'cgroup.procs', 4096).split()
        require(len(pids) <= MAX_UNIT_PROCESSES and all(pid.isdigit() for pid in pids),
                'UNIT_PROCESSES_INVALID', slot)
        processes = {}
        node = str(Path('/usr/bin/node').resolve())
        for pid in {int(value) for value in pids}:
            root = proc_root / str(pid)
            identity = process_identity(root)
            if identity is None:
                continue
            executable = os.readlink(root / 'exe')
            if Path(executable).name.startswith(('Runner.Worker', 'Runner.Listener')) or executable == node:
                processes[pid] = identity, executable

        workers = [pid for pid, (_, executable) in processes.items() if Path(executable).name.startswith('Runner.Worker')]
        require(len(workers) <= 1, 'WORKER_AMBIGUOUS', slot)
        if not workers:
            return None
        worker = workers[0]
        worker_identity, worker_executable = processes[worker]
        listener = worker_identity[0]
        require(runner_binary(worker_executable, holder, 'Runner.Worker') and listener in processes
                and runner_binary(processes[listener][1], holder, 'Runner.Listener'),
                'WORKER_BINDING_CHANGED', slot)
        for pid in (worker, listener):
            verify_process_binding(proc_root / str(pid), holder, group, slot)

        claimants = []
        for pid, (identity, executable) in processes.items():
            if executable != node or identity[0] != worker:
                continue
            root = proc_root / str(pid)
            if read_bounded(root / 'cmdline', 4096) != HOLDER_COMMAND:
                continue
            verify_process_binding(root, holder, group, slot)
            entries = read_bounded(root / 'environ', 256 * 1024).split(b'\0')
            observed = {}
            for entry in entries:
                key, _, value = entry.partition(b'=')
                if key in expected_environment:
                    require(key not in observed, 'HOLDER_ENVIRONMENT_AMBIGUOUS', slot)
                    observed[key] = value
            require(observed == expected_environment, 'HOLDER_ENVIRONMENT_CHANGED', slot)
            claimants.append(pid)
        require(len(claimants) <= 1, 'HOLDER_AMBIGUOUS', slot)
        if not claimants:
            return None

        claimant = claimants[0]
        for pid in (listener, worker, claimant):
            root = proc_root / str(pid)
            if process_identity(root) != processes[pid][0]:
                return None
            verify_process_binding(root, holder, group, slot)
        started = processes[claimant][0][1]
        age = time.clock_gettime(time.CLOCK_BOOTTIME) - int(started) / os.sysconf('SC_CLK_TCK')
        require(0 <= age and age + min_hold_seconds < HOLDER_TIMEOUT_SECONDS, 'HOLDER_EXPIRING', slot)
        return {'pid': claimant, 'started': started, 'cgroup': group,
                'workerPid': worker, 'workerStarted': worker_identity[1]}
    except FileNotFoundError:
        return None  # A kernel process or unit can disappear during observation.
    except OSError:
        raise RunnerReservationError('RUNNER_RESERVATION_PROCESS_READ_FAILED') from None


def verify_runner_reservation(*, token, workflow_run, holders, min_hold_seconds=0, api=None,
                              local_holder=None):
    """Return exact per-slot receipt, or None while the native jobs start.

    The caller supplies the protected owner dispatch and registered pool
    bindings under its pool lock. This read makes no scheduling mutation.
    """
    api = github_api if api is None else api
    local_holder = observe_holder if local_holder is None else local_holder
    require(isinstance(workflow_run, dict) and isinstance(token, str) and bool(token), 'DISPATCH_INVALID')
    repository = workflow_run.get('config_repository')
    run_id = workflow_run.get('workflow_run_id')
    attempt = workflow_run.get('workflow_run_attempt')
    head = workflow_run.get('config_sha')
    require(valid_text(repository, r'[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}')
            and positive(run_id) and positive(attempt) and valid_text(head, r'[0-9a-f]{40}'), 'DISPATCH_INVALID')
    require(type(min_hold_seconds) in (int, float) and 0 <= min_hold_seconds < HOLDER_TIMEOUT_SECONDS,
            'HOLD_BUDGET_INVALID')
    require(isinstance(holders, dict) and 'primary' in holders and 0 < len(holders) <= 32, 'POOL_BINDING_INVALID')
    for slot, holder in holders.items():
        require(valid_text(slot, r'[a-z][a-z0-9-]{0,31}') and isinstance(holder, dict), 'POOL_BINDING_INVALID')
        require(positive(holder.get('runnerId')) and positive(holder.get('runnerGroupId'))
                and valid_text(holder.get('runnerName'), r'[A-Za-z0-9_.-]{1,128}')
                and valid_text(holder.get('runnerLabel'), r'[A-Za-z0-9_.-]{1,256}')
                and valid_text(holder.get('service'), r'[A-Za-z0-9_.-]{1,192}\.service')
                and valid_text(holder.get('runnerRoot'), r'/opt/codex-relay-pools/[A-Za-z0-9_-]+/runners/' + slot)
                and positive(holder.get('runnerUid')), 'POOL_BINDING_INVALID', slot)
    require(len({holder['runnerId'] for holder in holders.values()}) == len(holders), 'POOL_BINDING_INVALID')

    response = api(f'/repos/{repository}/actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100', token)
    rows = response.get('jobs') if isinstance(response, dict) else None
    require(isinstance(rows, list) and len(rows) <= MAX_JOBS and type(response.get('total_count')) is int
            and response['total_count'] == len(rows), 'JOBS_INCOMPLETE')
    require(all(isinstance(job, dict) and positive(job.get('id')) and positive(job.get('run_id'))
                and job['run_id'] == run_id and job.get('head_sha') == head
                and ('run_attempt' not in job or positive(job['run_attempt']) and job['run_attempt'] == attempt)
                and isinstance(job.get('name'), str) for job in rows), 'JOB_IDENTITY_CHANGED')
    require(len({job['id'] for job in rows}) == len(rows), 'JOB_IDENTITY_CHANGED')

    evidence = {}
    for slot, holder in holders.items():
        matching = [job for job in rows if job['name'] == holder_job_name(slot)]
        require(len(matching) <= 1, 'JOB_NAME_AMBIGUOUS', slot)
        assigned = [job for job in rows if job.get('status') == 'in_progress'
                    and job.get('runner_id') == holder['runnerId']]
        require(len(assigned) <= 1, 'RUNNER_JOB_AMBIGUOUS', slot)
        require(not assigned or assigned == matching, 'JOB_NAME_CHANGED', slot)
        if not matching:
            continue
        job = matching[0]
        status = job.get('status')
        require(status in ('requested', 'waiting', 'pending', 'queued', 'in_progress')
                and job.get('conclusion') is None, 'JOB_NOT_RUNNING', slot)
        if status != 'in_progress':
            continue
        require(positive(job.get('runner_id')) and job['runner_id'] == holder['runnerId']
                and job.get('runner_name') == holder['runnerName']
                and positive(job.get('runner_group_id')) and job['runner_group_id'] == holder['runnerGroupId']
                and isinstance(job.get('labels'), list) and holder['runnerLabel'] in job['labels'],
                'JOB_RUNNER_CHANGED', slot)

        if slot == 'primary':
            process = holder.get('ownerTransport')
            require(isinstance(process, dict) and positive(process.get('pid'))
                    and valid_text(process.get('started'), r'[0-9]{1,20}')
                    and process.get('cgroup') == service_cgroup(holder), 'OWNER_TRANSPORT_UNPROVEN', slot)
        else:
            workflow_ref = f'{repository}/{WORKFLOW}@refs/heads/main'
            expected_environment = dict(GITHUB_RUN_ID=str(run_id), GITHUB_RUN_ATTEMPT=str(attempt),
                                        GITHUB_REPOSITORY=repository, GITHUB_WORKFLOW_REF=workflow_ref,
                                        GITHUB_SHA=head, GITHUB_JOB='reserve', RELAY_HOLDER_SLOT=slot)
            process = local_holder(slot, holder, {key.encode('ascii'): value.encode('ascii')
                                                   for key, value in expected_environment.items()},
                                   min_hold_seconds=min_hold_seconds)
            if process is None:
                continue
        evidence[slot] = {**process, 'jobId': job['id'], 'runnerId': holder['runnerId']}

    return evidence if set(evidence) == set(holders) else None
