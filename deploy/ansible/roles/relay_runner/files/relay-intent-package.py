"""Operation-bound package staging; never reads credentials or active config."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys


def require(value, code='INTENT_PACKAGE_UNPROVEN'):
    if not value:
        raise ValueError(code)


def file_sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def real(path, directory=None, *, owner=True):
    path = Path(path)
    require(path.is_absolute() and path == Path(os.path.normpath(path)))
    for parent in reversed(path.parents):
        if not os.path.lexists(parent):
            return False
        info = parent.lstat()
        require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode))
        require(not owner or info.st_uid == 0 and not info.st_mode & 0o022, 'INTENT_PACKAGE_PATH_UNSAFE')
    if not os.path.lexists(path):
        return False
    info = path.lstat()
    require(not stat.S_ISLNK(info.st_mode))
    require(not owner or info.st_uid == 0 and not info.st_mode & 0o022, 'INTENT_PACKAGE_PATH_UNSAFE')
    require(stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode) and info.st_nlink == 1)
    return True


def _runner_directory(root, name):
    path = root / name
    if path.is_symlink():
        # The native updater separately points bin/externals at a retained
        # versioned directory inside the same instance (using absolute links).
        target = os.readlink(path)
        if os.path.isabs(target):
            require(Path(target).parent == root, 'INTENT_RUNNER_NATIVE_LAYOUT_UNSAFE')
            target = Path(target).name
        require(re.fullmatch(re.escape(name) + r'[.](?:0|[1-9][0-9]*)[.](?:0|[1-9][0-9]*)[.](?:0|[1-9][0-9]*)', target),
                'INTENT_RUNNER_NATIVE_LAYOUT_UNSAFE')
        path = root / target
        require(real(path, True, owner=False), 'INTENT_RUNNER_NATIVE_LAYOUT_UNSAFE')
    return path if real(path, True, owner=False) else None


def runner_directory(root, name):
    try:
        return _runner_directory(root, name)
    except (OSError, ValueError):
        raise ValueError('INTENT_RUNNER_NATIVE_LAYOUT_UNSAFE_STOPPED_REPAIR_REQUIRED') from None


def runner_entrypoint(root, name):
    path = root / name
    if name == 'bin/Runner.Listener':
        directory = runner_directory(root, 'bin')
        if directory is None:
            return None
        path = directory / 'Runner.Listener'
    return path if real(path, False, owner=False) else None


def inspect_live(kind, values):
    if kind == 'runner':
        root = Path(values['root'])
        real(root, True, owner=False)
        real(Path(values['archive']).parent, True)
        real(values['archive'], False)
        if root.exists():
            markers = [root / name for name in ('.runner', '.credentials')]
            require(all(os.path.lexists(path) for path in markers) or not any(os.path.lexists(path) for path in markers),
                    'INTENT_RUNNER_REGISTRATION_AMBIGUOUS')
            for path in markers:
                real(path, False, owner=False)
            for name in ('bin', 'externals'):
                runner_directory(root, name)
            for name in ('config.sh', 'run.sh', 'bin/Runner.Listener'):
                runner_entrypoint(root, name)
    else:
        for key in ('home', 'installDir'):
            real(values[key], True)
        real(values['installer'], False)
        install_command = Path(values['installDir']) / 'codex'
        if os.path.lexists(install_command):
            require(install_command.is_symlink() and install_command.lstat().st_uid == 0)
        command = Path(values['binary'])
        real(command.parent, True)
        if os.path.lexists(command):
            require(stat.S_ISLNK(command.lstat().st_mode) and command.lstat().st_uid == 0)
        packages = Path(values['home']) / 'packages'
        if packages.exists():
            tree(packages)


def runner_transition(stage, values):
    # Native self-update may change every distribution byte, so staged bootstrap
    # bytes do not establish drift. Probe live software only as its unprivileged
    # runner identity; Runner.Listener may write its private diagnostics.
    live = Path(values['root'])
    entrypoints = [runner_entrypoint(live, name) for name in ('config.sh', 'run.sh', 'bin/Runner.Listener')]
    directories = [runner_directory(live, name) for name in ('bin', 'externals')]
    access_paths = [path for path in directories if path is not None]
    complete = all(path is not None and path.stat().st_mode & 0o500 == 0o500 for path in directories)
    external = directories[1]
    if external is not None:
        runtimes = [child for child in external.iterdir() if re.fullmatch(r'node[0-9]+', child.name)]
        complete = complete and bool(runtimes)
        for runtime in runtimes:
            for path in (runtime, runtime / 'bin', runtime / 'bin/node'):
                access_paths.append(path)
                try:
                    usable = real(path, path.name != 'node', owner=False) and path.stat().st_mode & 0o500 == 0o500
                except (OSError, ValueError):
                    usable = False
                if not usable:
                    complete = False
    complete = complete and all(path is not None and path.stat().st_mode & 0o111 for path in entrypoints)
    if complete:
        probe = subprocess.run(['/usr/sbin/runuser', '--user', values['user'], '--', '/bin/sh', '-c',
            'umask 077; listener=$1; shift; for path do test -r "$path" && test -x "$path" || exit 1; done; exec "$listener" --version',
            'relay-runner-version', str(live / 'bin/Runner.Listener'), *map(str, access_paths)],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=60, check=False, cwd=live, env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'})
        complete = (probe.returncode == 0 and len(probe.stdout) <= 128 and
                    re.fullmatch(rb'(?:0|[1-9][0-9]*)[.](?:0|[1-9][0-9]*)[.](?:0|[1-9][0-9]*)', probe.stdout.strip()))
    if complete:
        return
    require(not os.path.lexists(live / '.runner'), 'RUNNER_REGISTERED_PACKAGE_REPAIR_REQUIRED_STOPPED_ONLY')
    state = subprocess.run(['systemctl', 'is-active', values['service']], stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=30, check=False,
        env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'})
    require(state.returncode in (3, 4) and state.stdout.strip() in (b'inactive', b'failed', b'unknown'),
            'RUNNER_ACTIVE_PACKAGE_TRANSITION_REQUIRED')


def tree(root, *, skip_manifest=False):
    root = Path(root)
    rows = []
    for path in [root, *sorted(root.rglob('*'))]:
        if skip_manifest and path == root / 'manifest.json':
            continue
        info = path.lstat()
        require(info.st_uid == info.st_gid == 0 and (stat.S_ISLNK(info.st_mode) or not info.st_mode & 0o022))
        if stat.S_ISLNK(info.st_mode):
            require(path.resolve(strict=True).is_relative_to(root))
            content = ['link', os.readlink(path)]
        elif stat.S_ISDIR(info.st_mode):
            content = ['directory']
        else:
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1)
            content = ['file', file_sha(path)]
        rows.append([str(path.relative_to(root)), stat.S_IMODE(info.st_mode), *content])
    return hashlib.sha256(json.dumps(rows, separators=(',', ':')).encode()).hexdigest()


def version(command, expected, home):
    result = subprocess.run([str(command), '--version'], stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60, check=False,
        cwd=home, env={'PATH': '/usr/bin:/bin', 'HOME': str(home), 'CODEX_HOME': str(home),
                       'LANG': 'C', 'LC_ALL': 'C'})
    require(result.returncode == 0 and len(result.stdout) <= 128 and result.stdout.decode().strip() == expected,
            'INTENT_PACKAGE_VERSION_MISMATCH')


def binding(kind, operation, package_version, archive_sha):
    return {'version': 1, 'kind': kind, 'operationId': operation,
            'packageVersion': package_version, 'archiveSha256': archive_sha}


def verify(root, expected):
    require(real(root, True))
    manifest = root / 'manifest.json'
    require(real(manifest, False) and manifest.stat().st_size <= 4096)
    value = json.loads(manifest.read_bytes())
    require(isinstance(value, dict) and set(value) == set(expected) | {'treeSha256'}
            and all(value.get(key) == item for key, item in expected.items())
            and value['treeSha256'] == tree(root, skip_manifest=True), 'INTENT_PACKAGE_STAGE_CHANGED')
    if expected['kind'] == 'runner':
        require(file_sha(root / 'archive.tar.gz') == expected['archiveSha256'], 'INTENT_RUNNER_ARCHIVE_CHECKSUM_MISMATCH')
    return value


def relocate_codex(root):
    packages = root / 'package-home/packages'
    for path in packages.rglob('*'):
        if path.is_symlink():
            target = path.resolve(strict=True)
            require(target.is_relative_to(packages))
            if os.path.isabs(os.readlink(path)):
                path.unlink()
                path.symlink_to(os.path.relpath(target, path.parent))


def consume_codex(root, values, expected):
    value = verify(root, expected)
    inspect_live('codex', values)
    source = root / 'package-home/packages'
    destination = Path(values['home']) / 'packages'
    # Validate every prospective collision before changing any active bytes.
    for path in [source, *source.rglob('*')]:
        target = destination / path.relative_to(source)
        if os.path.lexists(target):
            info = target.lstat()
            require(info.st_uid == info.st_gid == 0 and (stat.S_ISLNK(info.st_mode) or not info.st_mode & 0o022))
            require(stat.S_ISDIR(info.st_mode) if path.is_dir() and not path.is_symlink() else
                    stat.S_ISLNK(info.st_mode) if path.is_symlink() else stat.S_ISREG(info.st_mode) and info.st_nlink == 1)
    home = Path(values['home'])
    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    home.chmod(0o700)
    destination.mkdir(mode=0o755, exist_ok=True)
    for path in sorted(source.rglob('*')):
        target = destination / path.relative_to(source)
        if path.is_symlink():
            if target.is_symlink() and os.readlink(target) == os.readlink(path):
                continue
            if os.path.lexists(target):
                target.unlink()
            target.symlink_to(os.readlink(path))
        elif path.is_dir():
            target.mkdir(mode=stat.S_IMODE(path.stat().st_mode), exist_ok=True)
        else:
            # Both trees were checked in this call, under the same protected
            # stage/destination boundary. Compare actual bytes and mode, never
            # a version name or an earlier process's cached digest.
            if (target.exists() and stat.S_IMODE(target.stat().st_mode) == stat.S_IMODE(path.stat().st_mode)
                    and file_sha(target) == file_sha(path)):
                continue
            shutil.copyfile(path, target, follow_symlinks=False)
            target.chmod(stat.S_IMODE(path.stat().st_mode))
    command = root / 'package-bin/codex'
    binary = command.resolve(strict=True)
    require(binary.is_relative_to(root / 'package-home/packages'))
    install = Path(values['installDir'])
    install.mkdir(mode=0o700, parents=True, exist_ok=True)
    link = install / 'codex'
    target = home / binary.relative_to(root / 'package-home')
    if os.path.lexists(link):
        require(link.is_symlink() and link.lstat().st_uid == 0)
        if os.readlink(link) == str(target):
            return value
        link.unlink()
    link.symlink_to(target)
    return value


def main():
    action, kind, stage, operation, package_version, archive_sha = sys.argv[1:]
    require(os.geteuid() == 0 and kind in ('runner', 'codex') and action in ('initialize', 'seal', 'verify', 'consume', 'relocate'))
    require(re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', operation)
            and re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', package_version))
    require(re.fullmatch('[a-f0-9]{64}', archive_sha) if kind == 'runner' else archive_sha == '-')
    stage = Path(stage)
    require(real(stage, True) and stat.S_IMODE(stage.stat().st_mode) == 0o700)
    for parent in stage.parents:
        info = parent.lstat()
        require(info.st_uid == 0 and not info.st_mode & 0o022)
    root = stage / (kind + '-package')
    expected = binding(kind, operation, package_version, archive_sha)
    raw = sys.stdin.buffer.read(16385)
    require(len(raw) <= 16384)
    values = json.loads(raw)
    require(isinstance(values, dict))
    if action == 'initialize':
        inspect_live(kind, values)
        require(not os.path.lexists(root))
        root.mkdir(mode=0o700)
    elif action == 'seal':
        require(real(root, True) and not os.path.lexists(root / 'manifest.json'))
        if kind == 'runner':
            require(file_sha(root / 'archive.tar.gz') == archive_sha)
            version(root / 'payload/bin/Runner.Listener', package_version, root / 'payload')
            inspect_live(kind, values)
            runner_transition(root, values)
        else:
            version(root / 'package-bin/codex', 'codex-cli ' + package_version, root / 'package-home')
        value = {**expected, 'treeSha256': tree(root, skip_manifest=True)}
        fd = os.open(root / 'manifest.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as output:
            json.dump(value, output, sort_keys=True)
        print(json.dumps(value, sort_keys=True))
    elif action == 'relocate':
        require(kind == 'codex')
        relocate_codex(root)
    elif action == 'consume':
        require(kind == 'codex')
        # consume_codex owns the same-call complete stage and live-path proof.
        # Repeating it here would traverse every distribution byte twice with
        # no intervening mutation or trust boundary.
        value = consume_codex(root, values, expected)
        print(json.dumps(value, sort_keys=True))
    else:
        inspect_live(kind, values)
        value = verify(root, expected)
        if kind == 'runner':
            runner_transition(root, values)
        print(json.dumps(value, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, UnicodeError, subprocess.SubprocessError) as error:
        code = str(error)
        print(code if re.fullmatch('[A-Z][A-Z0-9_]{0,79}', code) else 'INTENT_PACKAGE_UNPROVEN', file=sys.stderr)
        raise SystemExit(1) from None
