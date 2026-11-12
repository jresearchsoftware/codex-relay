"""No credential in arguments/environment; private request cleanup on every exit."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('predispatch_install_transport', ROOT / 'scripts/predispatch-install.py')
transport = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)
TOKEN = 'synthetic-existing-gh-secret'


@pytest.mark.parametrize('continuation', [False, True])
def test_existing_credential_is_only_on_ssh_stdin(continuation):
    calls = []
    def run(argv, **options):
        calls.append((argv, options))
        return SimpleNamespace(returncode=0, stdout=TOKEN.encode()) if argv[0] == 'gh' else SimpleNamespace(returncode=7)
    argv = ['tool', '--host', 'root@qualified', '--source', '/root/accepted source', '--config', '/root/private/config.json',
        '--consumer-root', '/root/consumer', '--revision', 'a' * 40, '--repository', 'example/repo',
        '--run-id', '99', '--authorization-id', '123'] + (['--continue'] if continuation else [])
    with patch.object(sys, 'argv', argv), patch.object(transport.subprocess, 'run', side_effect=run):
        assert transport.main() == 7
    assert calls[0][0] == ['gh', 'auth', 'token']
    assert calls[0][1]['stderr'] is subprocess.DEVNULL
    ssh, options = calls[1]
    assert TOKEN not in str(ssh) and TOKEN not in str({k: v for k, v in options.items() if k != 'input'})
    assert 'StrictHostKeyChecking=yes' in ssh and 'BatchMode=yes' in ssh
    assert json.loads(options['input']) == {'operation': 'finalize-predispatch', 'repository': 'example/repo',
        'runId': 99, 'attemptId': 'run-99', 'authorizationId': 123, 'workflowReadToken': TOKEN}
    assert ssh[-1].endswith(' continue' if continuation else ' install')
    compile(transport.REMOTE_PROGRAM, '<fixed-root-transport>', 'exec')


NATIVE = sys.platform == 'linux' and os.geteuid() == 0


@pytest.fixture
def root_transport():
    if not NATIVE:
        pytest.skip('disposable root Linux transport fixture required')
    with tempfile.TemporaryDirectory(prefix='relay-transport-', dir='/run') as temporary:
        root = Path(temporary)
        source, consumer = root / 'source', root / 'consumer'
        (source / 'deploy').mkdir(parents=True)
        shutil.copy2(ROOT / 'deploy/ansible_transport.py', source / 'deploy/ansible_transport.py')
        shutil.copytree(ROOT / 'deploy/ansible', source / 'deploy/ansible')
        consumer.mkdir()
        config, capture = root / 'deployment.json', root / 'capture.json'
        config.write_text(json.dumps({'capture': str(capture)})); config.chmod(0o600)
        cli = source / 'deploy/relay-deploy.py'
        cli.write_text('''import json,os,stat,sys,time
from pathlib import Path
args=sys.argv[1:];config=Path(args[args.index('--config')+1]);value=json.loads(config.read_bytes())
request=Path(args[args.index('--predispatch-recovery-request')+1]);raw=request.read_text();token=json.loads(raw)['workflowReadToken']
assert stat.S_IMODE(request.stat().st_mode)==0o600 and request.stat().st_uid==0
assert stat.S_IMODE(request.parent.stat().st_mode)==0o700
assert all(token not in item for item in sys.argv) and all(token not in item for item in os.environ.values())
captured={'path':str(request),'operation':json.loads(raw)['operation']}
if value.get('ansible'):
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    import ansible_transport
    answer=value['ansible'];expected=answer['input']
    code=('import json,locale,os,sys; value=sys.stdin.read(); assert value == '+repr(expected)+'; '
        'encoding=locale.getpreferredencoding(False); assert encoding.upper().replace("-","")=="UTF8",encoding; '
        'assert os.environ.get("LANG")=="C.UTF-8"; assert os.environ.get("LC_ALL")=="C.UTF-8"; '
        'print(json.dumps({"encoding":encoding,"lang":os.environ["LANG"],"lc_all":os.environ["LC_ALL"],'
        '"input":value,"receipt":"PUBLIC_RECEIPT=PASS"},ensure_ascii=False))')
    result=ansible_transport.run_target(None,None,['/usr/bin/python3','-I','-c',code],
        input=expected,timeout=45,local=True)
    captured.update({'ansible_returncode':result.returncode,'ansible_stdout':result.stdout,'ansible_stderr':result.stderr})
Path(value['capture']).write_text(json.dumps(captured,ensure_ascii=False))
if value.get('sleep'):time.sleep(60)
sys.exit(value.get('exit',captured.get('ansible_returncode',0)))
''')
        def git(*args):
            return subprocess.check_output(['/usr/bin/git', '-c', 'core.hooksPath=/dev/null', '-C', str(source), *args], text=True).strip()
        git('init', '--quiet', '--template='); git('add', '.')
        git('-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '--quiet', '-m', 'transport fixture')
        revision = git('rev-parse', 'HEAD')
        request = {'operation': 'finalize-predispatch', 'repository': 'example/repo', 'runId': 99,
            'attemptId': 'run-99', 'authorizationId': 123, 'workflowReadToken': TOKEN}
        yield SimpleNamespace(root=root, source=source, consumer=consumer, config=config, capture=capture,
            revision=revision, payload=json.dumps(request).encode(), argv=[sys.executable, '-I', '-c', transport.REMOTE_PROGRAM,
                str(source), str(config), str(consumer), revision, 'install'])


@pytest.mark.parametrize('exit_code', [0, 4])
def test_root_private_request_is_removed_after_success_or_failure(root_transport, exit_code):
    f = root_transport
    f.config.write_text(json.dumps({'capture': str(f.capture), 'exit': exit_code}))
    result = subprocess.run(f.argv, input=f.payload, capture_output=True)
    assert result.returncode == exit_code, result.stderr.decode()
    assert TOKEN.encode() not in result.stdout + result.stderr
    captured = json.loads(f.capture.read_bytes())
    assert captured['operation'] == 'finalize-predispatch'
    assert not Path(captured['path']).exists() and not Path(captured['path']).parent.exists()


def test_exact_root_bridge_runs_real_ansible_local_target_with_utf8_locale(root_transport):
    f = root_transport
    literal = 'synthetic privé input — UTF-8: café'
    f.config.write_text(json.dumps({'capture': str(f.capture), 'ansible': {'input': literal}}))
    result = subprocess.run(f.argv, input=f.payload, capture_output=True, timeout=90)
    assert result.returncode == 0, result.stderr.decode()
    assert TOKEN.encode() not in result.stdout + result.stderr
    captured = json.loads(f.capture.read_bytes())
    assert captured['ansible_returncode'] == 0 and captured['ansible_stderr'] == ''
    assert json.loads(captured['ansible_stdout']) == {
        'encoding': 'UTF-8', 'lang': 'C.UTF-8', 'lc_all': 'C.UTF-8',
        'input': literal, 'receipt': 'PUBLIC_RECEIPT=PASS'}
    assert not Path(captured['path']).exists() and not Path(captured['path']).parent.exists()


@pytest.mark.skipif(not NATIVE, reason='disposable root Linux Ansible locale proof required')
def test_actual_ansible_refuses_non_utf8_locale_before_target_execution(tmp_path):
    marker = tmp_path / 'must-not-run'
    playbook = tmp_path / 'negative-locale.yml'
    playbook.write_text(f'''- hosts: all
  gather_facts: false
  tasks:
    - ansible.builtin.command: ['/usr/bin/touch', '{marker}']
''')
    env = {'PATH': '/usr/bin:/bin', 'HOME': '/root', 'LANG': 'C', 'LC_ALL': 'C',
        'PYTHONCOERCECLOCALE': '0', 'PYTHONUTF8': '0', 'PYTHONDONTWRITEBYTECODE': '1',
        'ANSIBLE_CONFIG': str(ROOT / 'deploy/ansible/ansible.cfg'),
        'ANSIBLE_ROLES_PATH': str(ROOT / 'deploy/ansible/roles')}
    result = subprocess.run(['/usr/bin/ansible-playbook', '-i', 'localhost,', '-c', 'local', str(playbook)],
        cwd=ROOT / 'deploy/ansible', env=env, capture_output=True, text=True, timeout=45)
    assert result.returncode != 0
    assert 'Ansible requires the locale encoding to be UTF-8' in result.stdout + result.stderr
    assert not marker.exists()


def test_root_private_request_is_removed_after_termination(root_transport):
    f = root_transport
    f.config.write_text(json.dumps({'capture': str(f.capture), 'sleep': True}))
    process = subprocess.Popen(f.argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    process.stdin.write(f.payload); process.stdin.close()
    try:
        deadline = time.monotonic() + 5
        while not f.capture.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert f.capture.exists(), 'public fixture never received its private input'
        path = Path(json.loads(f.capture.read_bytes())['path'])
        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=5) == 1
        assert TOKEN.encode() not in process.stdout.read() + process.stderr.read()
        assert not path.exists() and not path.parent.exists()
    finally:
        if process.poll() is None:
            process.kill(); process.wait(timeout=5)
        process.stdout.close(); process.stderr.close()


def test_continuation_refuses_absent_native_binding_before_public_install(root_transport):
    f = root_transport
    f.argv[-1] = 'continue'
    result = subprocess.run(f.argv, input=f.payload, capture_output=True)
    assert result.returncode == 1 and not f.capture.exists()
    assert TOKEN.encode() not in result.stdout + result.stderr


def test_continuation_uses_selected_compiler_paths_and_the_exact_original_request(root_transport):
    f = root_transport
    (f.source / 'deploy/config.py').write_text('import json\n'
        'def load(path,source):return json.loads(path.read_bytes())\n'
        'def compile_inputs(value):return value["compiled"]\n')
    subprocess.run(['/usr/bin/git', '-C', str(f.source), 'add', '.'], check=True)
    subprocess.run(['/usr/bin/git', '-C', str(f.source), '-c', 'user.name=fixture',
        '-c', 'user.email=fixture@example.invalid', 'commit', '--quiet', '-m', 'selected compiler fixture'], check=True)
    revision = subprocess.check_output(['/usr/bin/git', '-C', str(f.source), 'rev-parse', 'HEAD'], text=True).strip()
    claim, config_root, releases = f.root / 'claims', f.root / 'configuration', f.root / 'releases'
    for path in (claim, config_root, releases):
        path.mkdir()
    operation = '12345678-1234-4234-8234-123456789abc'
    gate = claim / 'admission-v1.json'
    gate.write_text(json.dumps({'operationId': operation, 'phase': 'applying', 'target': revision})); gate.chmod(0o600)
    stage = releases / ('.stage-' + operation); stage.mkdir()
    snapshot = stage / 'old-installation.json'
    snapshot.write_text(json.dumps({'predispatchBridge': {'operationId': operation, 'target': revision,
        'runId': 99, 'attemptId': 'run-99', 'authorizationId': 123}})); snapshot.chmod(0o600)
    f.config.write_text(json.dumps({'capture': str(f.capture), 'compiled': {
        'relay_writer_claim_root': str(claim), 'relay_config_root': str(config_root), 'relay_release_root': str(releases)}}))
    f.argv[-2:] = [revision, 'continue']
    result = subprocess.run(f.argv, input=f.payload, capture_output=True)
    assert result.returncode == 0, result.stderr.decode()
    assert TOKEN.encode() not in result.stdout + result.stderr
    request = Path(json.loads(f.capture.read_bytes())['path'])
    assert not request.exists() and not request.parent.exists()


@pytest.mark.parametrize('change', ['tracked', 'untracked', 'unsafe-source-file', 'unsafe-source-directory'])
def test_source_cannot_impersonate_its_accepted_head_after_local_changes(root_transport, change):
    f = root_transport
    if change == 'tracked':
        with (f.source / 'deploy/relay-deploy.py').open('a') as stream:
            stream.write('\n# changed after the selected commit\n')
    elif change == 'untracked':
        (f.source / 'extra.py').write_text('raise RuntimeError("unreviewed")\n')
    elif change == 'unsafe-source-file':
        (f.source / 'deploy/relay-deploy.py').chmod(0o666)
    else:
        (f.source / 'deploy').chmod(0o777)
    result = subprocess.run(f.argv, input=f.payload, capture_output=True)
    assert result.returncode == 1 and not f.capture.exists()
    assert TOKEN.encode() not in result.stdout + result.stderr


@pytest.mark.parametrize('change', ['file', 'directory', 'symlink'])
def test_consumer_tree_must_also_remain_root_protected(root_transport, change):
    f = root_transport
    nested = f.consumer / 'project'
    nested.mkdir()
    if change == 'file':
        (nested / 'metadata').write_text('synthetic metadata')
        (nested / 'metadata').chmod(0o666)
    elif change == 'directory':
        nested.chmod(0o777)
    else:
        (nested / 'alias').symlink_to(f.config)
    result = subprocess.run(f.argv, input=f.payload, capture_output=True)
    assert result.returncode == 1 and not f.capture.exists()
    assert TOKEN.encode() not in result.stdout + result.stderr
