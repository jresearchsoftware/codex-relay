"""Real Ansible privilege semantics for runner probes and package extraction."""
import grp
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from unittest.mock import patch

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / 'deploy/ansible'
sys.path.insert(0, str(ROOT / 'deploy'))
import ansible_transport

pytestmark = pytest.mark.skipif(sys.platform != 'linux' or os.geteuid() != 0,
                               reason='native root Ansible identity qualification')


@pytest.fixture
def runner(request):
    # Use an existing ordinary identity without editing accounts or permissions
    # outside this disposable fixture. No real runner, service or credential runs.
    user = pwd.getpwnam('nobody')
    assert user.pw_uid != 0 and user.pw_gid != 0
    group = grp.getgrgid(user.pw_gid).gr_name
    temporary = tempfile.TemporaryDirectory(prefix='relay-runner-identity-', dir='/run')
    request.addfinalizer(temporary.cleanup)
    tmp_path = Path(temporary.name)
    tmp_path.chmod(0o755)
    root = tmp_path / 'runner'
    for path in [root, root / 'bin', root / '_diag']:
        path.mkdir(mode=0o750)
        os.chown(path, user.pw_uid, user.pw_gid)
    for name in ['config.sh', 'run.sh']:
        path = root / name
        path.write_text('#!/bin/sh\nexit 0\n')
        path.chmod(0o755)
        os.chown(path, user.pw_uid, user.pw_gid)
    listener = root / 'bin/Runner.Listener'
    listener.write_text('#!/usr/bin/python3\nimport json,os,pathlib,sys,time\n'
        'assert sys.argv[1:]==["--version"]\n'
        'path=pathlib.Path(__file__).parent.parent/"_diag"/("Runner_"+str(time.time_ns())+".log")\n'
        'fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o666)\n'
        'with os.fdopen(fd,"w") as stream: json.dump({"uid":os.geteuid(),"gid":os.getegid()},stream)\n'
        'print("2.336.0")\n')
    listener.chmod(0o755)
    os.chown(listener, user.pw_uid, user.pw_gid)
    records = tmp_path / 'tar-records'
    records.mkdir(mode=0o750)
    os.chown(records, user.pw_uid, user.pw_gid)
    tools = tmp_path / 'tools'
    tools.mkdir(mode=0o755)
    tar = shutil.which('tar')
    assert tar
    # Observe the real extractor's effective identity, then execute actual GNU
    # tar. Output ownership alone could hide root extraction followed by chown.
    for name in ['tar', 'gtar']:
        wrapper = tools / name
        wrapper.write_text('#!/usr/bin/python3\nimport json,os,pathlib,sys,time\n'
            'path=pathlib.Path(' + repr(str(records)) + ')/(str(time.time_ns())+".json")\n'
            'fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)\n'
            'with os.fdopen(fd,"w") as stream: json.dump({"uid":os.geteuid(),"gid":os.getegid(),"args":sys.argv[1:]},stream)\n'
            'os.execv(' + repr(tar) + ',[' + repr(tar) + ',*sys.argv[1:]])\n')
        wrapper.chmod(0o755)
    payload = tmp_path / 'package-payload'
    payload.write_text('Real unarchive payload, no executable or credential.\n')
    archive = tmp_path / 'runner.tar.gz'
    with tarfile.open(archive, 'w:gz') as stream:
        stream.add(payload, arcname='package-payload')
    archive.chmod(0o644)
    selected = {
        'Inspect runner root and registration markers before package reconciliation',
        'Inspect the installed runner version before software reconciliation',
        'Extract the verified runner package into the dedicated runner namespace',
        'Inspect installed runner entrypoints and version binary',
        'Create runner diagnostic namespace with runner ownership',
        'Inspect existing runner diagnostic files',
        'Normalize runner diagnostic file ownership before package probes',
        'Verify installed runner reports the pinned version',
        'Refuse installed runner version drift',
        'Reconcile runner diagnostic ownership after all package probes',
        'Enforce runner ownership of all diagnostic files after probes',
    }
    tasks = [task for task in yaml.safe_load((BACKEND / 'roles/relay_runner/tasks/main.yml').read_text())
             if task['name'] in selected]
    assert len(tasks) == len(selected)
    return {'work': tmp_path, 'root': root, 'uid': user.pw_uid, 'gid': user.pw_gid, 'user': user.pw_name,
            'group': group, 'records': records, 'tools': tools, 'tasks': tasks,
            'variables': {'relay_runner_root': str(root), 'relay_runner_user': user.pw_name,
                'relay_runner_group': group, 'relay_runner_package_archive': str(archive),
                'relay_runner_package_install_needed': True,
                'relay_runner_registration_marker': str(root / '.runner'),
                'relay_runner_credentials_marker': str(root / '.credentials')}}


def channel(tmp_path, mode):
    local = mode == 'installed-local'
    target = {'host': 'fixture.invalid', 'user': 'root',
              'connection': 'local' if mode == 'ordinary-local' else 'ssh'}
    variables = ansible_transport.connection_vars(target, '/synthetic/key', local=local)
    if mode == 'ssh':
        executable = tmp_path / 'synthetic-ssh'
        executable.write_text('#!/usr/bin/python3\nimport subprocess,sys\n'
            'raise SystemExit(subprocess.call(["/bin/sh","-c",sys.argv[-1]],stdin=sys.stdin.buffer))\n')
        executable.chmod(0o755)
        variables.update(ansible_ssh_executable=str(executable), ansible_ssh_transfer_method='piped',
                         ansible_pipelining=True, ansible_ssh_use_tty=False)
        assert variables['ansible_become'] is True
        assert 'StrictHostKeyChecking=yes' in variables['ansible_ssh_common_args']
    # Do not override ansible_become: this exact variable's precedence caused the
    # actual installed-local failure. SSH substitutes I/O only, not privilege.
    return target, variables


def run_role(tmp_path, runner, mode, phase):
    target, connection = channel(tmp_path, mode)
    inventory = tmp_path / (phase + '-inventory.json')
    inventory.write_text(json.dumps({'all': {'hosts': {target['host']: {
        **connection, **runner['variables'], 'ansible_remote_tmp': str(tmp_path / 'remote')}}}}))
    playbook = tmp_path / (phase + '-play.yml')
    playbook.write_text(yaml.safe_dump([{'hosts': 'all', 'gather_facts': False, 'become': True,
        'environment': {'PATH': str(runner['tools']) + ':/usr/bin:/bin'}, 'tasks': runner['tasks']}]))
    argv = ['ansible-playbook', '-i', str(inventory), str(playbook)]
    if phase != 'apply':
        argv.append('--check')
    result = subprocess.run(argv, env={**ansible_transport.backend_environment(), 'ANSIBLE_NOCOLOR': '1',
        'ANSIBLE_LOCAL_TEMP': str(tmp_path / 'local')}, cwd=BACKEND,
        capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    recap = re.search(r'fixture.invalid\s*:\s*ok=\d+\s+changed=(\d+)\s+unreachable=0\s+failed=0', result.stdout)
    assert recap, result.stdout + result.stderr
    return result, int(recap[1])


@pytest.mark.parametrize('mode', ['installed-local', 'ordinary-local', 'ssh'])
def test_effective_runner_identity_preserves_private_diagnostics_and_clean_checks(tmp_path, runner, mode):
    tmp_path = runner['work']
    before, pre_changes = run_role(tmp_path, runner, mode, 'before-check')
    apply, _ = run_role(tmp_path, runner, mode, 'apply')
    after, post_changes = run_role(tmp_path, runner, mode, 'after-check')
    diagnostics = list((runner['root'] / '_diag').glob('Runner_*.log'))
    assert len(diagnostics) == 6
    observed = [json.loads(path.read_bytes()) for path in diagnostics]
    extracts = [json.loads(path.read_bytes()) for path in runner['records'].glob('*.json')]
    expected = {'uid': runner['uid'], 'gid': runner['gid']}
    assert observed == [expected] * 6 and all(
        row['uid'] == runner['uid'] and row['gid'] == runner['gid'] for row in extracts), {
            'mode': mode, 'actualProbeIdentities': observed,
            'actualExtractorIdentities': [{key: row[key] for key in ['uid', 'gid']} for row in extracts]}
    assert all((path.stat().st_uid, path.stat().st_gid, path.stat().st_mode & 0o777)
               == (runner['uid'], runner['gid'], 0o600) for path in diagnostics)
    assert extracts and any('--extract' in row['args'] for row in extracts), extracts
    assert all(row['uid'] == runner['uid'] and row['gid'] == runner['gid'] for row in extracts), extracts
    extracted = runner['root'] / 'package-payload'
    assert extracted.read_text().startswith('Real unarchive payload')
    assert (extracted.stat().st_uid, extracted.stat().st_gid) == (runner['uid'], runner['gid'])
    assert pre_changes == post_changes == 0, before.stdout + apply.stdout + after.stdout


def test_real_wrong_owner_drift_remains_changed_and_strict_postcheck_rejects_it(tmp_path, runner):
    tmp_path = runner['work']
    wrong = runner['root'] / '_diag' / 'preexisting-wrong-owner.log'
    wrong.write_text('Synthetic preexisting ownership drift.\n')
    wrong.chmod(0o600)
    original = (wrong.read_bytes(), wrong.stat().st_uid, wrong.stat().st_gid, wrong.stat().st_ino)
    result, changes = run_role(tmp_path, runner, 'installed-local', 'drift-check')
    assert changes > 0
    assert (wrong.read_bytes(), wrong.stat().st_uid, wrong.stat().st_gid, wrong.stat().st_ino) == original
    # Feed the actual Ansible check output through the existing public primitive's
    # strict drift check. Its unrelated target/provenance seams are synthetic;
    # no success marker or relaxed check is supplied.
    spec = importlib.util.spec_from_file_location('runner_identity_cli', ROOT / 'deploy/relay-deploy.py')
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    desired = json.loads((ROOT / 'deploy/example.json').read_text())
    desired['target']['connection'] = 'local'
    config_path = tmp_path / 'desired.json'
    config_path.write_text(json.dumps(desired))
    argv = ['relay-deploy', '--config', str(config_path), '--phase', 'post-check',
            '--connection', 'local', '--consumer-root', str(tmp_path), '--log-root', str(tmp_path / 'logs')]
    def actual_output(_argv, _cwd, _env, log, *_guards):
        log.write(result.stdout + result.stderr)
        return result.returncode
    previous_umask = os.umask(0o022)
    try:
        with patch.object(sys, 'argv', argv), \
             patch.object(cli, 'source_identity', return_value={'revision': 'a' * 40, 'tree': 'b' * 40}), \
             patch.object(cli, 'clean_git', return_value='c' * 40), \
             patch.object(cli.tempfile, 'gettempdir', return_value=str(tmp_path)), \
             patch.object(cli, 'run_backend', side_effect=actual_output), \
             patch.object(ansible_transport, 'qualify_target'):
            with pytest.raises(ValueError, match='post-check-drift'):
                cli.run(cli.arguments())
    finally:
        os.umask(previous_umask)
