"""Original controller causes survive missing receipts and diagnostic failures."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ansible_transport as transport
import lifecycle


def backend(monkeypatch, tmp_path, body):
    stub = tmp_path / 'controller.py'
    stub.write_text('import json,pathlib,sys,time,os\n' + body)
    original = transport.subprocess.Popen
    calls = []
    def popen(argv, **kwargs):
        if argv[0] == 'ansible-playbook':
            calls.append(argv)
            return original([sys.executable, str(stub), argv[2]], **kwargs)
        return original(argv, **kwargs)
    monkeypatch.setattr(transport.subprocess, 'Popen', popen)
    return calls


def retained_record(process):
    directory = Path(process.temporary.name)
    assert directory.stat().st_mode & 0o777 == 0o700
    log = directory / 'failure.log'
    assert log.stat().st_mode & 0o777 == 0o600
    return json.loads(log.read_text().split('=', 1)[1])


@pytest.mark.parametrize('receipt', ['missing', 'invalid', 'invalid-json', 'success-with-controller-failure'])
def test_original_controller_cause_has_private_durability_before_cleanup(monkeypatch, tmp_path, capfd, receipt):
    write = {
        'missing': '', 'invalid': '(work/"result.json").write_text("{}")\n',
        'invalid-json': '(work/"result.json").write_text("broken json")\n',
        'success-with-controller-failure': '(work/"result.json").write_text(json.dumps({"rc":0,"stdout":"","stderr":""}))\n'
    }[receipt]
    calls = backend(monkeypatch, tmp_path, 'work=pathlib.Path(sys.argv[1]).parent\n'
        'print("controller loader: missing locale",file=sys.stderr)\n'
        'print("password=private-controller-value",file=sys.stderr)\n'
        'print("startup output")\n' + write + 'sys.exit(7)\n')
    process = transport.TargetProcess(None, None, ['/usr/bin/true'], local=True)
    try:
        assert process.communicate(timeout=5) == ('', 'ANSIBLE_TARGET_OPERATION_UNPROVEN\n')
        assert process.returncode == 255 and len(calls) == 1
        record = retained_record(process)
        text = json.dumps(record)
        assert 'missing locale' in text and 'startup output' in text
        assert 'private-controller-value' not in text
        assert record['causes'][1]['exit'] == 7
        assert record['causes'][0]['observation']['effect'] == 'unknown-inspect-original-operation'
        public = ''.join(capfd.readouterr())
        assert 'protected-transport/' in public and 'before-retry' in public
        assert 'missing locale' not in public and 'private-controller-value' not in public
    finally:
        process.temporary.cleanup()


@pytest.mark.parametrize('rc', [0, 9, -15])
def test_receipt_native_classification_and_effect_remain_intact(monkeypatch, tmp_path, rc):
    calls = backend(monkeypatch, tmp_path, 'work=pathlib.Path(sys.argv[1]).parent\n'
        '(work/"result.json").write_text(json.dumps({"rc":' + str(rc) + ',"stdout":"target output","stderr":"target original cause"}))\n')
    process = transport.TargetProcess(None, None, ['/usr/bin/true'], local=True)
    try:
        assert process.communicate(timeout=5) == ('target output', 'target original cause')
        assert process.returncode == rc and len(calls) == 1
        if rc:
            record = retained_record(process)
            assert record['causes'][0]['exit'] == rc
            assert record['causes'][0]['stderr'] == 'target original cause'
            if rc < 0:
                assert record['causes'][0]['signal'] == 15
        else:
            assert not Path(process.temporary.name).exists()
    finally:
        if Path(process.temporary.name).exists():
            process.temporary.cleanup()


def test_recorder_failure_retains_original_bounded_channels_independently(monkeypatch, tmp_path, capfd):
    backend(monkeypatch, tmp_path, 'sys.stderr.write("first actionable error\\n"+"x"*2000000)\nsys.exit(7)\n')
    def fail(*args, **kwargs):
        raise OSError('private-recorder-location')
    monkeypatch.setattr(lifecycle, 'report_failure', fail)
    process = transport.TargetProcess(None, None, ['/usr/bin/true'], local=True)
    try:
        process.communicate(timeout=5)
        directory = Path(process.temporary.name)
        raw = (directory / 'controller-stderr').read_bytes()
        assert raw.startswith(b'first actionable error\n') and len(raw) == transport.RESULT_LIMIT + 1
        assert process.capture_counts[1] == 2000023
        public = ''.join(capfd.readouterr())
        assert 'RELAY_ANSIBLE_DIAGNOSTIC_UNAVAILABLE=OSError' in public
        assert 'original-private-channels-retained' in public
        assert 'private-recorder-location' not in public and 'first actionable' not in public
    finally:
        process.temporary.cleanup()


def test_actual_ansible_locale_failure_has_readable_original_cause(monkeypatch):
    monkeypatch.setenv('LC_ALL', 'C')
    process = transport.TargetProcess(None, None, ['/usr/bin/true'], local=True)
    try:
        process.communicate(timeout=15)
        assert process.returncode == 255
        record = retained_record(process)
        assert 'Ansible requires the locale encoding to be UTF-8' in json.dumps(record)
    finally:
        process.temporary.cleanup()


def test_timeout_preserves_first_output_alongside_cleanup_receipt_failure(monkeypatch, tmp_path, capfd):
    calls = backend(monkeypatch, tmp_path, 'print("first controller failure",file=sys.stderr,flush=True)\ntime.sleep(60)\n')
    instances = []
    original = transport.TargetProcess
    class Observed(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            instances.append(self)
    monkeypatch.setattr(transport, 'TargetProcess', Observed)
    try:
        with pytest.raises(subprocess.TimeoutExpired) as caught:
            transport.run_target(None, None, ['/usr/bin/true'], local=True, timeout=.1)
        assert len(calls) == 1
        assert b'first controller failure' in caught.value.stderr
        process = instances[0]
        lines = (Path(process.temporary.name) / 'failure.log').read_text().splitlines()
        records = [json.loads(line.split('=', 1)[1]) for line in lines]
        assert any(record['phase'] == 'target-operation-interrupted' and
            record['causes'][0]['type'] == 'TimeoutExpired' and
            'first controller failure' in record['causes'][0]['stderr'] for record in records)
        assert 'first controller failure' not in ''.join(capfd.readouterr())
    finally:
        for process in instances:
            process.temporary.cleanup()


def test_output_store_failure_keeps_draining_original_child(monkeypatch, tmp_path):
    import io
    process = transport.TargetProcess(None, None, [], local=True)
    class BrokenStore:
        def write(self, raw):
            raise OSError('disk unavailable')
    process.read_channel(io.BytesIO(b'first cause\n' + b'x' * 2000000), BrokenStore(), index=1)
    assert process.capture_counts[1] == 2000012
    assert bytes(process.capture_prefix[1]).startswith(b'first cause\n')
    assert len(process.capture_prefix[1]) == transport.RESULT_LIMIT + 1
    assert len(process.reader_errors) == 1


def test_drain_wrapper_small_pipe_drains_stderr_while_submitting_stdin(tmp_path):
    # A supported Linux pipe capacity under resource pressure, not a production
    # capacity override. Exercise the exact wrapper with only fixture paths.
    script = transport.DRAIN_PROGRESS_WRAPPER.replace("pathlib.Path('/run')", 'pathlib.Path(' + repr(str(tmp_path)) + ')')
    script = script.replace('stdin=subprocess.PIPE, stderr=subprocess.PIPE)',
                            'stdin=subprocess.PIPE, stderr=subprocess.PIPE, pipesize=4096)')
    directory = tmp_path / ('relay-ansible-progress-' + 'a' * 32)
    code = 'import sys;sys.stderr.write("first actionable error\\n"+"x"*8192);sys.stderr.flush();assert len(sys.stdin.read())==50000;sys.exit(7)'
    from lifecycle import DRAIN_PROGRESS_PATTERN
    result = subprocess.run([sys.executable, '-c', script, str(directory), DRAIN_PROGRESS_PATTERN],
        input=json.dumps({'argv': [sys.executable, '-c', code], 'input': 'y' * 50000}),
        capture_output=True, text=True, timeout=5)
    assert result.returncode == 7 and result.stderr.startswith('first actionable error\n')
    assert not directory.exists()


def test_late_controller_error_survives_bounded_capture_and_durable_projection(monkeypatch, tmp_path):
    backend(monkeypatch, tmp_path, 'sys.stderr.write("FIRST_ERROR\\n"+"x"*2000000+"\\nLATE_ERROR_E999");sys.exit(7)\n')
    process = transport.TargetProcess(None, None, ['/usr/bin/true'], local=True)
    try:
        process.communicate(timeout=5)
        record = retained_record(process)
        text = json.dumps(record)
        assert 'FIRST_ERROR' in text and 'LATE_ERROR_E999' in text
        tail = Path(process.temporary.name) / 'stderr-tail'
        assert tail.read_bytes().endswith(b'LATE_ERROR_E999') and tail.stat().st_size == 8192
    finally:
        process.temporary.cleanup()
