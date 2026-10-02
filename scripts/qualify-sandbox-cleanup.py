#!/usr/bin/env python3
"""Qualify the fixed cleanup helper with two synthetic Unix identities.

Requires uid 0 only to drop child credentials to numeric fixture UIDs/GIDs.
Creates no users, changes no system configuration, and touches only its owned
temporary directory. No deployed Relay, credential, service or network access.
"""
import errno
import grp
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
RUNNER_UID = 62039
RUNTIME_UID = 62040
WORK_GID = 62041
CHILD_ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'}


def child_identity(uid):
    def drop():
        os.setgroups([WORK_GID])
        os.setgid(uid)
        os.setuid(uid)
        os.umask(0o007)
    return drop


def run_as(uid, args):
    result = subprocess.run([sys.executable, '-I', '-S', *args],
        env=CHILD_ENV, preexec_fn=child_identity(uid), text=True,
        capture_output=True, timeout=40, check=False)
    if result.stderr or len(result.stdout.encode('utf8')) > 2048:
        raise AssertionError('UNBOUNDED_OR_UNEXPECTED_FIXTURE_OUTPUT')
    return result.returncode, json.loads(result.stdout)


def directory(path, uid, mode=0o2770):
    path.mkdir()
    os.chown(path, uid, WORK_GID)
    path.chmod(mode)


def main():
    if sys.platform != 'linux' or os.geteuid() != 0:
        print('SANDBOX_CLEANUP_UNIX_PROOF_UNAVAILABLE requires native Linux uid 0 for synthetic child identities')
        return 2
    for uid in [RUNNER_UID, RUNTIME_UID]:
        try:
            pwd.getpwuid(uid)
        except KeyError:
            continue
        raise AssertionError('SYNTHETIC_FIXTURE_UID_ALREADY_ALLOCATED')
    for gid in [RUNNER_UID, RUNTIME_UID, WORK_GID]:
        try:
            grp.getgrgid(gid)
        except KeyError:
            continue
        raise AssertionError('SYNTHETIC_FIXTURE_GID_ALREADY_ALLOCATED')
    with tempfile.TemporaryDirectory(prefix='relay-sandbox-identity-proof-') as temporary:
        base = Path(temporary).resolve(strict=True)
        assert base.parent == Path(tempfile.gettempdir()).resolve(strict=True)
        assert base.name.startswith('relay-sandbox-identity-proof-') and not base.is_symlink()
        base.chmod(0o755)
        work = base / 'work'
        directory(work, RUNNER_UID)
        cwd = work / 'run-39'
        directory(cwd, RUNNER_UID)
        sandbox = cwd / '.codex-sandbox'
        directory(sandbox, RUNNER_UID)
        directory(sandbox / 'home', RUNNER_UID)
        directory(sandbox / 'home/tmp', RUNNER_UID)
        template = ROOT / 'deploy/ansible/roles/relay_codex_runtime/templates/relay-codex-cleanup.py.j2'
        source = template.read_text(encoding='utf8')
        assert source.count('{{ relay_dispatch_work_root | to_json }}') == 1
        helper = base / 'cleanup.py'
        helper.write_text(source.replace('{{ relay_dispatch_work_root | to_json }}', json.dumps(str(work))), encoding='utf8')
        helper.chmod(0o644)
        metadata = sandbox.stat()
        identity = f'{metadata.st_dev}:{metadata.st_ino}'

        # The actual runtime UID creates the private descendant. Shared group
        # membership must never cause the private mode to be relaxed.
        arg0 = sandbox / 'home/tmp/arg0'
        create = """import json,os,sys
root=sys.argv[1]
os.mkdir(root, 0o700)
with open(root+'/private-state','w') as f: f.write('synthetic protected state')
s=os.stat(root)
print(json.dumps({'uid':os.getuid(),'mode':s.st_mode & 0o777}))
"""
        code, created = run_as(RUNTIME_UID, ['-c', create, str(arg0)])
        assert code == 0 and created == {'uid': RUNTIME_UID, 'mode': 0o700}, created
        assert sandbox.stat().st_uid == RUNNER_UID
        wrong = run_as(RUNTIME_UID, [str(helper), '--cwd', str(cwd), '--sandbox-identity', f'{metadata.st_dev}:{metadata.st_ino + 1}'])
        assert wrong[0] == 1 and wrong[1]['code'] == 'SANDBOX_CLEANUP_IDENTITY_MISMATCH', wrong

        raw_cleanup = """import json,shutil,sys
try:
 shutil.rmtree(sys.argv[1])
except OSError as e:
 print(json.dumps({'errno':e.errno}));sys.exit(1)
print(json.dumps({'removed':True}))
"""
        code, denied = run_as(RUNNER_UID, ['-c', raw_cleanup, str(sandbox)])
        assert code == 1 and denied == {'errno': errno.EACCES}, denied
        assert stat.S_IMODE(arg0.stat().st_mode) == 0o700
        assert (arg0 / 'private-state').read_text() == 'synthetic protected state'

        outside = base / 'outside'
        outside.mkdir()
        sentinel = outside / 'must-survive'
        sentinel.write_text('outside the admitted sandbox')
        (sandbox / 'redirect').symlink_to(outside, target_is_directory=True)
        code, receipt = run_as(RUNTIME_UID, [str(helper), '--cwd', str(cwd), '--sandbox-identity', identity])
        assert code == 0 and receipt == {'schemaVersion': 1, 'status': 'removed'}, receipt
        assert not sandbox.exists() and cwd.is_dir()
        assert sentinel.read_text() == 'outside the admitted sandbox'
        code, receipt = run_as(RUNTIME_UID, [str(helper), '--cwd', str(cwd), '--sandbox-identity', identity])
        assert code == 1 and receipt['code'] == 'ENOENT' and receipt['syscall'] == 'open', receipt

        # Verify a real permission failure produces a bounded operation/syscall
        # capsule while retaining the inaccessible artifact and its exact mode.
        directory(sandbox, RUNNER_UID)
        directory(sandbox / 'home', RUNNER_UID)
        directory(sandbox / 'home/tmp', RUNNER_UID)
        directory(arg0, RUNNER_UID, 0o700)
        marker = arg0 / 'keep-private'
        marker.write_text('retained evidence')
        metadata = sandbox.stat()
        code, receipt = run_as(RUNTIME_UID, [str(helper), '--cwd', str(cwd), '--sandbox-identity', f'{metadata.st_dev}:{metadata.st_ino}'])
        assert code == 1 and receipt == {'schemaVersion': 1, 'status': 'retained', 'code': 'EACCES',
            'operation': 'open-directory', 'syscall': 'open', 'path': '.codex-sandbox/home/tmp/arg0'}, receipt
        assert marker.read_text() == 'retained evidence' and stat.S_IMODE(arg0.stat().st_mode) == 0o700
        assert str(base) not in json.dumps(receipt)
    print('SANDBOX_CLEANUP_UNIX_PROOF_PASS distinct-numeric-uids;runtime-private-0700;runner-eacces;'
          'fixed-helper-removes;outside-symlink-preserved;inode-and-replay-gates;bounded-os-evidence')
    return 0


if __name__ == '__main__':
    sys.exit(main())
