"""Native Linux ownership, concurrency and handback checks for shared TEST."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import signal
from concurrent.futures import ThreadPoolExecutor

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/test-environment-lock.py'
pytestmark = pytest.mark.skipif(sys.platform != 'linux', reason='Linux flock boundary')


@pytest.fixture
def lock(tmp_path):
    spec = importlib.util.spec_from_file_location('test_environment_lock', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, tmp_path / 'ownership.lock'


def invoke(path, *args):
    return subprocess.run([sys.executable, str(SCRIPT), '--path', str(path), *args],
                          capture_output=True, text=True, timeout=15)


def claim(module, path, task='example/repo#217', execution='run-1'):
    return module.operate(path, 'claim', task=task, execution=execution)


def test_exact_execution_unlock_and_reuse(lock):
    module, path = lock
    holder = claim(module, path)['holder']
    assert claim(module, path, 'example/repo#215')['holder'] == holder
    assert claim(module, path)['status'] == 'BLOCKED'
    for task, execution, token in [('other#1', 'run-1', holder['token']),
                                    (holder['task'], 'run-2', holder['token']),
                                    (holder['task'], 'run-1', 'wrong')]:
        with pytest.raises(module.Refusal, match='NOT_OWNED'):
            module.operate(path, 'release', task=task, execution=execution,
                           token=token, usable=True)
    assert module.operate(path, 'status')['holder'] == holder
    with pytest.raises(module.Refusal, match='USABLE'):
        module.operate(path, 'release', token=holder['token'])
    inode = path.stat().st_ino
    module.operate(path, 'release', task=holder['task'], execution=holder['execution'],
                   token=holder['token'], usable=True)
    assert path.stat().st_ino == inode
    assert claim(module, path, 'example/repo#215')['status'] == 'CLAIMED'


def test_simultaneous_processes_have_one_winner(lock):
    _, path = lock
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda i: invoke(path, 'claim', '--task', f'example/repo#{i}',
                                '--execution', f'run-{i}'), range(1, 13)))
    winners = [json.loads(r.stdout) for r in results if r.returncode == 0]
    assert len(winners) == 1
    assert all(json.loads(r.stdout)['holder'] == winners[0]['holder'] for r in results)


def test_interrupted_claim_and_stale_recovery(lock):
    module, path = lock
    result = invoke(path, 'claim', '--task', 'example/repo#217', '--execution', 'dead-run')
    holder = json.loads(result.stdout)['holder']
    assert module.operate(path, 'status')['holder'] == holder
    with pytest.raises(module.Refusal, match='STOP_CONFIRMATION'):
        module.operate(path, 'recover', token=holder['token'], usable=True)
    module.operate(path, 'recover', token=holder['token'], usable=True, stopped=True)
    next_holder = claim(module, path)['holder']
    with pytest.raises(module.Refusal, match='NOT_OWNED'):
        module.operate(path, 'recover', token=holder['token'], usable=True, stopped=True)
    assert module.operate(path, 'status')['holder'] == next_holder


@pytest.mark.parametrize('exit_code', [0, 7])
def test_handled_work_cleans_before_release(lock, tmp_path, exit_code):
    module, path = lock
    cleanup = tmp_path / 'cleanup'
    cleanup.write_text('#!/bin/sh\nprintf cleaned > "' + str(tmp_path / 'cleaned') + '"\n')
    cleanup.chmod(0o700)
    result = invoke(path, 'run', '--task', 'example/repo#217', '--execution', 'run-1',
                    '--cleanup-script', str(cleanup), '--', sys.executable,
                    '-c', f'raise SystemExit({exit_code})')
    assert result.returncode == exit_code
    assert (tmp_path / 'cleaned').read_text() == 'cleaned'
    assert module.operate(path, 'status')['status'] == 'FREE'


def test_failed_cleanup_retains_holder_and_busy_never_runs_work(lock, tmp_path):
    module, path = lock
    result = invoke(path, 'run', '--task', 'example/repo#217', '--execution', 'run-1',
                    '--cleanup-script', '/bin/false', '--', '/bin/true')
    assert result.returncode == 2
    assert 'TEST_CLEANUP_FAILED' in result.stdout
    result = invoke(path, 'run', '--task', 'example/repo#215', '--execution', 'run-2',
                    '--cleanup-script', '/bin/false', '--', '/usr/bin/touch', str(tmp_path / 'bad'))
    assert result.returncode == 2
    assert not (tmp_path / 'bad').exists()
    assert module.operate(path, 'status')['holder']['execution'] == 'run-1'


def test_killed_wrapper_retains_claim_even_after_child_stops(lock):
    module, path = lock
    process = subprocess.Popen([sys.executable, str(SCRIPT), '--path', str(path),
        'run', '--task', 'example/repo#217', '--execution', 'killed-run',
        '--cleanup-script', '/bin/true', '--', '/bin/sleep', '60'],
        stdout=subprocess.PIPE, text=True, start_new_session=True)
    try:
        holder = json.loads(process.stdout.readline())['holder']
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
        assert module.operate(path, 'status')['holder'] == holder
        assert claim(module, path, 'example/repo#215')['status'] == 'BLOCKED'
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
        process.stdout.close()


def test_age_never_breaks_a_claim(lock):
    module, path = lock
    holder = claim(module, path)['holder']
    holder['claimed_at'] = '1970-01-01T00:00:00+00:00'
    path.write_text(json.dumps(holder))
    assert claim(module, path, 'example/repo#215') == {'status': 'BLOCKED', 'holder': holder}


def test_failed_launch_is_handled_and_missing_cleanup_retains_claim(lock):
    module, path = lock
    result = invoke(path, 'run', '--task', 'example/repo#217', '--execution', 'run-1',
                    '--cleanup-script', '/bin/true', '--', '/no-such-work-command')
    assert result.returncode == 127
    assert module.operate(path, 'status')['status'] == 'FREE'
    result = invoke(path, 'run', '--task', 'example/repo#217', '--execution', 'run-2',
                    '--cleanup-script', '/no-such-cleanup', '--', '/bin/true')
    assert result.returncode == 2
    assert module.operate(path, 'status')['holder']['execution'] == 'run-2'


@pytest.mark.parametrize('kind', ['symlink', 'hardlink', 'fifo', 'damaged'])
def test_unsafe_marker_is_never_free(lock, tmp_path, kind):
    module, path = lock
    target = tmp_path / 'target'
    target.write_text('preserve')
    if kind == 'symlink':
        path.symlink_to(target)
    elif kind == 'hardlink':
        os.link(target, path)
    elif kind == 'fifo':
        os.mkfifo(path)
    else:
        path.write_text('{broken')
    with pytest.raises((module.Refusal, OSError)):
        claim(module, path)
    assert target.read_text() == 'preserve'
