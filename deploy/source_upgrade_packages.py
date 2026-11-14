"""Independent ephemeral official Codex reference for one source-only Apply.

Acquisition is explicit and separated from verification. A verifier never
downloads, normalizes, repairs or creates a missing reference or live payload.
"""
import hashlib
import grp
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import urllib.request

VERSION = '0.167.2'
INSTALLER_URL = 'https://chatgpt.com/codex/install.sh'
REFERENCE = 'codex-proof-reference'


def require(value, code='SOURCE_UPGRADE_CODEX_UNPROVEN'):
    if not value:
        raise ValueError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def _module(source_root, relative, name):
    spec = importlib.util.spec_from_file_location(name, Path(source_root) / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _owners(source_root):
    stage = _module(source_root, 'deploy/ansible/roles/relay_artifacts/files/relay-intent-stage.py', 'codex_reference_stage')
    package = _module(source_root, 'deploy/ansible/roles/relay_runner/files/relay-intent-package.py', 'codex_reference_package')
    codex = _module(source_root, 'deploy/ansible/roles/relay_codex_runtime/files/relay-codex-package-guard.py', 'codex_reference_guard')
    return stage, package, codex


def _context(stage, operation, values, source_root):
    require(values['relay_codex_cli_version'] == VERSION and values['relay_codex_installer_url'] == INSTALLER_URL,
            'SOURCE_UPGRADE_CODEX_RECIPE_CHANGED')
    stage_owner, package, codex = _owners(source_root)
    root = stage_owner.stage_root(stage, operation)
    return root / REFERENCE, package, codex


def _run(argv, *, env, cwd):
    return subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                          env=env, cwd=cwd, timeout=120, check=False)


def _download(url):
    with urllib.request.urlopen(url, timeout=30) as response:
        require(response.url.startswith('https://'), 'SOURCE_UPGRADE_CODEX_INSTALLER_UNPROVEN')
        raw = response.read(1048577)
    require(0 < len(raw) <= 1048576, 'SOURCE_UPGRADE_CODEX_INSTALLER_UNPROVEN')
    return raw


def _tree(packages):
    """All distribution entries/bytes, with internal links made root-relative."""
    packages = Path(packages)
    rows, observed = [], []
    for path in [packages, *sorted(packages.rglob('*'))]:
        info = path.lstat()
        before = (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
                  info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        require(info.st_uid == info.st_gid == 0 and (stat.S_ISLNK(info.st_mode) or not info.st_mode & 0o022))
        if stat.S_ISLNK(info.st_mode):
            target = path.resolve(strict=True)
            require(target.is_relative_to(packages))
            content = ['link', target.relative_to(packages).as_posix()]
        elif stat.S_ISDIR(info.st_mode):
            content = ['directory']
        else:
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1)
            with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
                require((os.fstat(stream.fileno()).st_dev, os.fstat(stream.fileno()).st_ino) == before[:2])
                content = ['file', hashlib.file_digest(stream, 'sha256').hexdigest()]
        rows.append([path.relative_to(packages).as_posix(), stat.S_IMODE(info.st_mode), *content])
        observed.append((path, before))
        require(len(rows) <= 20000, 'SOURCE_UPGRADE_CODEX_ENTRIES_EXCEEDED')
    for path, before in observed:
        info = path.lstat()
        require((info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
                 info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns) == before,
                'SOURCE_UPGRADE_CODEX_MOVED')
    return hashlib.sha256(canonical(rows)).hexdigest()


def _rust_metadata(root, expected_gid):
    """Current recursive owner/mode contract; no old build receipt is trusted.

    Stat identities/timestamps are retained in the proof, so a package update
    between proof phases cannot pass on unchanged version output alone.
    """
    root = Path(root)
    require(stat.S_ISDIR(root.lstat().st_mode), 'SOURCE_UPGRADE_RUST_PREFIX_UNSAFE')
    rows, observed = [], []
    for path in [root, *sorted(root.rglob('*'))]:
        info = path.lstat()
        identity = [info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
                    info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns]
        require(info.st_uid == 0 and info.st_gid == expected_gid, 'SOURCE_UPGRADE_RUST_METADATA_UNSAFE')
        if stat.S_ISLNK(info.st_mode):
            target = path.resolve(strict=True)
            require(target.is_relative_to(root), 'SOURCE_UPGRADE_RUST_LINK_UNSAFE')
            content = ['link', target.relative_to(root).as_posix()]
        elif stat.S_ISDIR(info.st_mode):
            require(stat.S_IMODE(info.st_mode) == 0o755, 'SOURCE_UPGRADE_RUST_METADATA_UNSAFE')
            content = ['directory']
        else:
            require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) in [0o644, 0o755],
                    'SOURCE_UPGRADE_RUST_METADATA_UNSAFE')
            content = ['file']
        rows.append([path.relative_to(root).as_posix(), identity, *content])
        observed.append((path, identity))
        require(len(rows) <= 100000, 'SOURCE_UPGRADE_RUST_ENTRIES_EXCEEDED')
    for path, before in observed:
        info = path.lstat()
        require([info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
                 info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns] == before,
                'SOURCE_UPGRADE_RUST_MOVED')
    for name in ['cargo', 'rustc', 'rustfmt']:
        info = (root / 'bin' / name).lstat()
        require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o755,
                'SOURCE_UPGRADE_RUST_BINARY_UNSAFE')
    return hashlib.sha256(canonical(rows)).hexdigest()


def prepare_reference(stage, operation, values, source_root, *, execute=None, download=None):
    """Create one official pinned reference inside the already locked stage."""
    root, package, codex = _context(stage, operation, values, source_root)
    require(not os.path.lexists(root), 'SOURCE_UPGRADE_CODEX_REFERENCE_EXISTS')
    root.mkdir(mode=0o700)
    home, install = root / 'package-home', root / 'package-bin'
    home.mkdir(mode=0o700); install.mkdir(mode=0o700)
    installer = root / 'installer.sh'
    raw = (download or _download)(INSTALLER_URL)
    require(isinstance(raw, bytes) and 0 < len(raw) <= 1048576, 'SOURCE_UPGRADE_CODEX_INSTALLER_UNPROVEN')
    descriptor = os.open(installer, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o700)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(raw)
    environment = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'HOME': str(home),
                   'CODEX_HOME': str(home), 'CODEX_INSTALL_DIR': str(install), 'CODEX_NON_INTERACTIVE': '1'}
    result = (execute or _run)(['/bin/sh', str(installer), '--release', VERSION], env=environment, cwd=root)
    require(result.returncode == 0, 'SOURCE_UPGRADE_CODEX_INSTALLER_FAILED')
    codex.qualify(home, install / 'codex', VERSION, normalize=True)
    package.relocate_codex(root)
    codex.qualify(home, install / 'codex', VERSION)
    # Same pinned version probe as the ordinary package stage, without auth.
    package.version(install / 'codex', 'codex-cli ' + VERSION, home)
    return {'schemaVersion': 1, 'operation': operation, 'version': VERSION,
            'payloadTreeSha256': _tree(home / 'packages'), 'installerSha256': hashlib.sha256(raw).hexdigest()}


def verify_packages(stage, operation, values, source_root, receipt, *, execute=None):
    """Verify only; absence/uncertainty never creates or reacquires anything."""
    root, package, codex = _context(stage, operation, values, source_root)
    require(isinstance(receipt, dict) and set(receipt) == {'schemaVersion', 'operation', 'version',
                                                         'payloadTreeSha256', 'installerSha256'}
            and type(receipt['schemaVersion']) is int and receipt['schemaVersion'] == 1
            and receipt['operation'] == operation and receipt['version'] == VERSION
            and all(isinstance(receipt[key], str) and re.fullmatch('[0-9a-f]{64}', receipt[key])
                    for key in ['payloadTreeSha256', 'installerSha256']),
            'SOURCE_UPGRADE_CODEX_REFERENCE_BINDING')
    require(package.real(root, True) and stat.S_IMODE(root.stat().st_mode) == 0o700,
            'SOURCE_UPGRADE_CODEX_REFERENCE_MISSING')
    installer = root / 'installer.sh'
    require(package.real(installer, False) and package.file_sha(installer) == receipt['installerSha256'],
            'SOURCE_UPGRADE_CODEX_REFERENCE_CHANGED')
    reference_home = root / 'package-home'
    reference = codex.qualify(reference_home, root / 'package-bin/codex', VERSION)
    live_home = Path(values['relay_codex_package_home'])
    live = codex.qualify(live_home, values['relay_codex_binary_path'], VERSION)
    require(Path(reference['binary']).relative_to(reference_home) == Path(live['binary']).relative_to(live_home),
            'SOURCE_UPGRADE_CODEX_ENTRYPOINT_CHANGED')
    reference_tree = _tree(reference_home / 'packages')
    live_tree = _tree(live_home / 'packages')
    require(reference_tree == live_tree == receipt['payloadTreeSha256'], 'SOURCE_UPGRADE_CODEX_PAYLOAD_CHANGED')
    rust_version = values['relay_rust_toolchain_version']
    require(isinstance(rust_version, str) and re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', rust_version),
            'SOURCE_UPGRADE_RUST_VERSION_UNPROVEN')
    rust_gid = grp.getgrnam(values['relay_group']).gr_gid
    rust_metadata = _rust_metadata(values['relay_rust_toolchain_root'], rust_gid)
    run = execute or _run
    user, home = values['relay_codex_user'], values['relay_codex_home']
    environment = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'HOME': home, 'CODEX_HOME': home}
    commands = [(values['relay_codex_binary_path'], 'codex-cli ' + VERSION),
                *[(values['relay_rust_toolchain_root'] + '/bin/' + name, name + ' ' + rust_version)
                  for name in ['cargo', 'rustc']], (values['relay_rust_toolchain_root'] + '/bin/rustfmt', None)]
    # The same primary runtime identity owns the ordinary Codex and managed
    # Rust probes. Batch transport, retaining each real tool invocation/result.
    result = run(['/usr/sbin/runuser', '-u', user, '--', '/bin/sh', '-c',
                  'for command do "$command" --version || exit 1; done', 'relay-toolchain-proof',
                  *[command for command, _ in commands]], env=environment, cwd=home)
    require(result.returncode == 0 and len(result.stdout) <= 4096, 'SOURCE_UPGRADE_TOOLCHAIN_RUNTIME_UNPROVEN')
    outputs = result.stdout.decode().splitlines()
    require(len(outputs) == len(commands), 'SOURCE_UPGRADE_TOOLCHAIN_RUNTIME_UNPROVEN')
    for output, (_, expected) in zip(outputs, commands):
        output = output.strip()
        if expected is not None:
            require(output == expected if expected.startswith('codex-cli ') else output.startswith(expected + ' '),
                    'SOURCE_UPGRADE_TOOLCHAIN_RUNTIME_UNPROVEN')
    require(_tree(reference_home / 'packages') == reference_tree and _tree(live_home / 'packages') == live_tree,
            'SOURCE_UPGRADE_CODEX_MOVED')
    require(_rust_metadata(values['relay_rust_toolchain_root'], rust_gid) == rust_metadata,
            'SOURCE_UPGRADE_RUST_MOVED')
    return {'version': VERSION, 'treeSha256': live_tree, 'referenceTreeSha256': reference_tree,
            'runtimeVersions': dict(zip(['codex', 'cargo', 'rustc', 'rustfmt'], [line.strip() for line in outputs])),
            'rustMetadataSha256': rust_metadata}
