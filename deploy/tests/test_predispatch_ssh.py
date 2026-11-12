import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


spec = importlib.util.spec_from_file_location('predispatch_ssh', Path(__file__).resolve().parents[2] / 'scripts/predispatch-ssh.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_token_is_only_transported_on_ssh_stdin():
    token = b'synthetic-secret'
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout=token) if args[0] == 'gh' else SimpleNamespace(returncode=0)

    argv = ['tool', '--host', 'root@operator', '--source', '/root/accepted source', '--consumer', '/etc/relay.json',
            '--repository', 'example/repo', '--run-id', '99', '--operation', 'predispatch-state']
    with patch('sys.argv', argv), patch.object(module.subprocess, 'run', side_effect=run):
        assert module.main() == 0
    ssh_args, ssh_kwargs = calls[1]
    assert token not in str(ssh_args).encode()
    assert token in ssh_kwargs['input']
    assert 'StrictHostKeyChecking=yes' in ssh_args
    assert "'/root/accepted source/controller/src/predispatch-recovery-entrypoint.mjs'" in ssh_args[-1]
    assert calls[0][1]['stderr'] == module.subprocess.DEVNULL


def test_finalize_requires_authorization_id():
    argv = ['tool', '--host', 'root@operator', '--source', '/root/source', '--consumer', '/etc/relay.json',
            '--repository', 'example/repo', '--run-id', '99', '--operation', 'finalize-predispatch']
    with patch('sys.argv', argv), patch.object(module.subprocess, 'run') as run:
        try:
            module.main()
        except SystemExit as exc:
            assert exc.code == 2
        else:
            assert False, 'missing authorization was accepted'
        run.assert_not_called()
