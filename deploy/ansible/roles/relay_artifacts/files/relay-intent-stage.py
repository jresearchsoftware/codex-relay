"""Bounded artifact preparation/verification behind the private installer stage.

No operation changes the active release pointer, consumer, units or admission.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tarfile
import uuid

MAX_ENTRIES = 20000
MAX_BYTES = 2 * 1024 * 1024 * 1024
IDENTITY_KEYS = {'revision', 'tree', 'sourceTreeSha256', 'controllerSourceTreeSha256',
                 'codexLauncherSourceTreeSha256', 'reviewerSourceTreeSha256', 'reviewerBuildInputsTreeSha256'}
BIN_LINKS = {'bin/relay-codex-dispatch.mjs': '../reviewed-source/controller/src/codex-dispatch-entrypoint.mjs',
             'bin/relay-diagnostics-store.mjs': '../reviewed-source/controller/src/diagnostic-store-entrypoint.mjs'}


def require(value, code):
    if not value:
        raise ValueError(code)


def hash_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def stamp(info):
    return tuple(getattr(info, 'st_' + key) for key in
                 ('dev', 'ino', 'mode', 'nlink', 'uid', 'gid', 'size', 'mtime_ns', 'ctime_ns'))


def protected(path, *, directory=False, owner_uid=0):
    path = Path(path)
    require(path.is_absolute() and str(path) == os.path.normpath(path), 'INTENT_STAGE_PATH_INVALID')
    for current in [path, *path.parents]:
        info = current.lstat()
        require(info.st_uid == owner_uid and not stat.S_ISLNK(info.st_mode)
                and not info.st_mode & 0o022, 'INTENT_STAGE_PARENT_UNSAFE')
        if current == path and not directory:
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, 'INTENT_STAGE_FILE_UNSAFE')
        else:
            require(stat.S_ISDIR(info.st_mode), 'INTENT_STAGE_PARENT_UNSAFE')
    return path.stat()


def read_regular(path, *, owner_uid=0, limit=MAX_BYTES):
    before = protected(path, owner_uid=owner_uid)
    require(before.st_size <= limit, 'INTENT_STAGE_BYTES_EXCEEDED')
    with open(path, 'rb') as stream:
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    require(len(raw) == before.st_size and stamp(before) == stamp(after) == stamp(Path(path).stat()),
            'INTENT_STAGE_INPUT_CHANGED')
    return raw


def atomic(path, raw, mode):
    path = Path(path)
    protected(path.parent, directory=True)
    temporary = path.with_name('.' + path.name + '.stage-' + str(uuid.uuid4()))
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fchmod(stream.fileno(), mode)
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary.exists():
            temporary.unlink()


def identity(value):
    require(isinstance(value, dict) and set(value) == IDENTITY_KEYS, 'INTENT_STAGE_IDENTITY_INVALID')
    require(all(re.fullmatch('[a-f0-9]{40}' if key in ('revision', 'tree') else '[a-f0-9]{64}', item or '')
                for key, item in value.items()), 'INTENT_STAGE_IDENTITY_INVALID')
    return value


def stage_root(root, operation):
    require(re.fullmatch('[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', operation or ''),
            'INTENT_STAGE_OPERATION_INVALID')
    root = Path(root)
    protected(root, directory=True)
    require(root.name == '.stage-' + operation and stat.S_IMODE(root.stat().st_mode) == 0o700,
            'INTENT_STAGE_ROOT_INVALID')
    return root


def git_object(kind, raw):
    return hashlib.sha1(kind.encode() + b' ' + str(len(raw)).encode() + b'\0' + raw).digest()


def git_tree(entries):
    tree = {}
    for name, mode, raw in entries:
        current = tree
        parts = name.split('/')
        for part in parts[:-1]:
            require(part not in current or isinstance(current[part], dict), 'INTENT_STAGE_ARCHIVE_COLLISION')
            current = current.setdefault(part, {})
        require(parts[-1] not in current, 'INTENT_STAGE_ARCHIVE_COLLISION')
        current[parts[-1]] = (mode, git_object('blob', raw))

    def digest(current):
        rows = []
        for name, value in current.items():
            directory = isinstance(value, dict)
            mode, object_id = ('40000', digest(value)) if directory else value
            rows.append(((name + ('/' if directory else '')).encode(),
                         mode.encode() + b' ' + name.encode() + b'\0' + object_id))
        return git_object('tree', b''.join(raw for _, raw in sorted(rows)))
    return digest(tree).hex()


def extract(root, archive_path, expected, links):
    raw_archive = read_regular(archive_path)
    entries, names, total = [], set(), 0
    with tarfile.open(fileobj=__import__('io').BytesIO(raw_archive)) as archive:
        require(archive.pax_headers.get('comment') == expected['revision'], 'INTENT_STAGE_ARCHIVE_REVISION_CHANGED')
        for member in archive:
            name = member.name.rstrip('/')
            path = PurePosixPath(name)
            require(name and not path.is_absolute() and str(path) == name
                    and all(part not in ('.', '..', '') for part in path.parts)
                    and '\\' not in name and not any(ord(c) < 32 for c in name), 'INTENT_STAGE_ARCHIVE_PATH_INVALID')
            require(name not in names and len(names) < MAX_ENTRIES, 'INTENT_STAGE_ARCHIVE_COLLISION')
            names.add(name)
            require(member.isdir() or member.isfile(), 'INTENT_STAGE_ARCHIVE_TYPE_INVALID')
            if member.isdir():
                continue
            total += member.size
            require(total <= MAX_BYTES, 'INTENT_STAGE_BYTES_EXCEEDED')
            with archive.extractfile(member) as stream:
                raw = stream.read(member.size + 1)
            require(len(raw) == member.size, 'INTENT_STAGE_ARCHIVE_INCOMPLETE')
            entries.append((name, '100755' if member.mode & 0o111 else '100644', raw))
    require(entries and git_tree(entries) == expected['tree'], 'INTENT_STAGE_SOURCE_TREE_CHANGED')
    source = root / 'release/reviewed-source'
    if source.exists():
        protected(source, directory=True)
        aliases = {'reviewed-source/' + link['alias'] for link in links}
        expected_names = {name for name, _, _ in entries} | {'.relay-source.json'}
        observed = {path.relative_to(source).as_posix() for path in source.rglob('*')
                    if path.is_symlink() or not path.is_dir()}
        require(observed == expected_names | {name.removeprefix('reviewed-source/') for name in aliases},
                'INTENT_STAGE_EXISTING_SOURCE_CHANGED')
        for name, mode, raw in entries:
            path = source / name
            require(read_regular(path) == raw and stat.S_IMODE(path.stat().st_mode) ==
                    (0o755 if mode == '100755' else 0o644), 'INTENT_STAGE_EXISTING_SOURCE_CHANGED')
        require(json.loads(read_regular(source / '.relay-source.json')) == expected, 'INTENT_STAGE_IDENTITY_CHANGED')
        known = allowed_links({'compatibilityLinks': links})
        for alias in aliases:
            path = root / 'release' / alias
            require(path.is_symlink() and os.readlink(path) == known[alias], 'INTENT_STAGE_EXISTING_SOURCE_CHANGED')
        return {'sourceArchiveSha256': hash_bytes(raw_archive), 'sourceGitTree': expected['tree'],
                'compatibilityLinks': links, 'sourceFiles': len(entries), 'sourceBytes': total}
    source.mkdir(parents=True, mode=0o755)
    for name, mode, raw in entries:
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        atomic(target, raw, 0o755 if mode == '100755' else 0o644)
    for directory, _, _ in os.walk(source):
        Path(directory).chmod(0o755)
    atomic(source / '.relay-source.json', (json.dumps(expected, sort_keys=True) + '\n').encode(), 0o644)
    for link in links:
        require(isinstance(link, dict) and set(link) == {'alias', 'target'}, 'INTENT_STAGE_LINK_INVALID')
        alias, target = (PurePosixPath(link[key]) for key in ('alias', 'target'))
        require(not alias.is_absolute() and not target.is_absolute()
                and '..' not in alias.parts and '..' not in target.parts
                and str(alias) != '.' and str(target) != '.', 'INTENT_STAGE_LINK_INVALID')
        destination, original = source / str(alias), source / str(target)
        require(not destination.exists() and not destination.is_symlink() and original.is_file(), 'INTENT_STAGE_LINK_INVALID')
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        destination.symlink_to(os.path.relpath(original, destination.parent))
    return {'sourceArchiveSha256': hash_bytes(raw_archive), 'sourceGitTree': expected['tree'], 'compatibilityLinks': links,
            'sourceFiles': len(entries), 'sourceBytes': total}


def allowed_links(acquisition):
    result = dict(BIN_LINKS)
    for link in acquisition.get('compatibilityLinks', []):
        alias = 'reviewed-source/' + link['alias']
        result[alias] = os.path.relpath('reviewed-source/' + link['target'], str(PurePosixPath(alias).parent))
    return result


def tree_digest(root, links=None, toolchain=False):
    root = Path(root)
    protected(root, directory=True)
    rows, total = [], 0
    for directory, subdirectories, files in os.walk(root, followlinks=False):
        for name in sorted(subdirectories + files):
            path = Path(directory) / name
            info = path.lstat()
            require(info.st_uid == 0 and (stat.S_ISLNK(info.st_mode) or not info.st_mode & 0o022),
                    'INTENT_STAGE_PAYLOAD_UNSAFE')
            relative = path.relative_to(root).as_posix()
            require(len(rows) < MAX_ENTRIES, 'INTENT_STAGE_ENTRIES_EXCEEDED')
            if stat.S_ISLNK(info.st_mode):
                target = os.readlink(path)
                require(not os.path.isabs(target) and path.resolve(strict=True).is_relative_to(root),
                        'INTENT_STAGE_LINK_ESCAPE')
                require(toolchain or (links or {}).get(relative) == target, 'INTENT_STAGE_LINK_INVALID')
                content = ['link', target]
            elif stat.S_ISDIR(info.st_mode):
                content = ['directory']
            else:
                raw = read_regular(path)
                total += len(raw)
                require(total <= MAX_BYTES, 'INTENT_STAGE_BYTES_EXCEEDED')
                content = ['file', hash_bytes(raw)]
            rows.append([relative, stat.S_IMODE(info.st_mode), *content])
    return hash_bytes(json.dumps(sorted(rows), separators=(',', ':')).encode())


def verify(root, expected):
    receipt = json.loads(read_regular(root / 'receipt.json', limit=2 * 1024 * 1024))
    require(stat.S_IMODE((root / 'receipt.json').stat().st_mode) == 0o600
            and receipt['version'] == 1 and receipt['operationId'] == expected['operationId']
            and receipt['sourceIdentity'] == identity(expected['sourceIdentity']), 'INTENT_STAGE_RECEIPT_CHANGED')
    require(receipt['releaseTreeSha256'] == tree_digest(root / 'release', allowed_links(receipt['sourceAcquisition'])),
            'INTENT_STAGE_PAYLOAD_CHANGED')
    binary = root / 'release/bin/reviewer-mcp-http'
    require(hash_bytes(read_regular(binary)) == receipt['reviewer']['binarySha256'], 'INTENT_STAGE_REVIEWER_CHANGED')
    require(json.loads(read_regular(root / 'release/reviewed-source/.relay-source.json')) == expected['sourceIdentity'],
            'INTENT_STAGE_IDENTITY_CHANGED')
    if receipt['toolchain']['stagedPrefix']:
        require(receipt['toolchain']['stagedPrefix'] == str(root / 'rust-toolchain')
                and receipt['toolchain']['treeSha256'] == tree_digest(root / 'rust-toolchain', toolchain=True),
                'INTENT_STAGE_TOOLCHAIN_CHANGED')
    return receipt


def copy_tree(source, destination):
    if destination.exists() or destination.is_symlink():
        protected(destination, directory=True)
    else:
        protected(destination.parent, directory=True)
        destination.mkdir(mode=stat.S_IMODE(source.stat().st_mode))
        destination.chmod(stat.S_IMODE(source.stat().st_mode))
    for path in source.iterdir():
        target = destination / path.name
        if path.is_symlink():
            require(not target.exists() or target.is_symlink(), 'INTENT_STAGE_DESTINATION_CHANGED')
            temporary = target.with_name('.' + target.name + '.stage-' + str(uuid.uuid4()))
            temporary.symlink_to(os.readlink(path))
            os.replace(temporary, target)
        elif path.is_dir():
            copy_tree(path, target)
        else:
            if target.exists() or target.is_symlink():
                protected(target)
            atomic(target, read_regular(path), stat.S_IMODE(path.stat().st_mode))


def consume_destination(root, data, argument):
    destination = Path(argument)
    if data.get('reinstall', False):
        release_root = Path(data.get('releaseRoot', ''))
        install_root = release_root.parent
        require(data['reinstall'] is True and release_root.is_absolute() and release_root.name == 'releases'
                and root.parent == install_root.parent / ('.' + install_root.name + '-staging')
                and destination.parent == release_root, 'INTENT_STAGE_DESTINATION_INVALID')
    else:
        require(destination.parent == root.parent, 'INTENT_STAGE_DESTINATION_INVALID')
    require(destination.name == data['sourceIdentity']['revision'], 'INTENT_STAGE_DESTINATION_INVALID')
    return destination


def check_destination(source, destination, links):
    """Validate the entire existing copy plan before changing its first byte.

    Safe unreferenced regular files (including wholly internal Cargo output
    hardlinks) remain untouched. Only fixed product aliases may be symlinks, including the
    historical absolute spelling that names this exact same release payload.
    """
    existing = destination.exists() or destination.is_symlink()
    parent = destination if existing else destination.parent
    while not parent.exists() and not parent.is_symlink():
        parent = parent.parent
    protected(parent, directory=True)
    if not existing:
        return {'status': 'DESTINATION_READY', 'existingEntries': 0}
    planned = {}
    for directory, subdirectories, files in os.walk(source, followlinks=False):
        for name in subdirectories + files:
            path = Path(directory) / name
            planned[path.relative_to(source).as_posix()] = (
                'link' if path.is_symlink() else 'directory' if path.is_dir() else 'file')
    entries, hardlinks, total = {}, {}, 0
    for directory, subdirectories, files in os.walk(destination, followlinks=False):
        for name in sorted(subdirectories + files):
            path = Path(directory) / name
            info = path.lstat()
            relative = path.relative_to(destination).as_posix()
            require(len(entries) < MAX_ENTRIES, 'INTENT_STAGE_ENTRIES_EXCEEDED')
            require(info.st_uid == 0 and (stat.S_ISLNK(info.st_mode) or not info.st_mode & 0o022),
                    'INTENT_STAGE_DESTINATION_UNSAFE')
            if stat.S_ISLNK(info.st_mode):
                expected = links.get(relative)
                require(expected is not None and os.path.normpath(str(path.parent / os.readlink(path)))
                        == os.path.normpath(str(path.parent / expected)), 'INTENT_STAGE_DESTINATION_LINK_INVALID')
                entries[relative] = 'link'
            elif stat.S_ISDIR(info.st_mode):
                entries[relative] = 'directory'
            else:
                require(stat.S_ISREG(info.st_mode), 'INTENT_STAGE_DESTINATION_UNSAFE')
                if info.st_nlink != 1:
                    hardlinks.setdefault((info.st_dev, info.st_ino), []).append((relative, info.st_nlink))
                total += info.st_size
                require(total <= MAX_BYTES, 'INTENT_STAGE_BYTES_EXCEEDED')
                entries[relative] = 'file'
    for aliases in hardlinks.values():
        require(all(relative not in planned and count == len(aliases) for relative, count in aliases),
                'INTENT_STAGE_DESTINATION_UNSAFE')
    for relative, kind in planned.items():
        require(relative not in entries or entries[relative] == kind, 'INTENT_STAGE_DESTINATION_TYPE_CHANGED')
    return {'status': 'DESTINATION_READY', 'existingEntries': len(entries)}


def run(action, root, data, argument=None):
    root = stage_root(root, data['operationId'])
    expected = identity(data['sourceIdentity'])
    if action == 'extract':
        return extract(root, argument, expected, data.get('compatibilityLinks', []))
    if action == 'check-toolchain':
        protected(Path(data['prefix']), directory=True)
        protected(Path(data['prefix']) / 'bin', directory=True)
        return {'status': 'READ_ONLY_TOOLCHAIN_BOUNDARY_READY'}
    if action == 'normalize-links':
        for name, target in BIN_LINKS.items():
            path = root / 'release' / name
            require(path.is_symlink() and path.resolve(strict=True) == (path.parent / target).resolve(strict=True),
                    'INTENT_STAGE_LINK_INVALID')
            path.unlink()
            path.symlink_to(target)
        return {'status': 'NORMALIZED'}
    if action == 'seal':
        require(not (root / 'receipt.json').exists(), 'INTENT_STAGE_RECEIPT_ALREADY_EXISTS')
        if data['toolchain']['stagedPrefix']:
            require(data['toolchain']['stagedPrefix'] == str(root / 'rust-toolchain'), 'INTENT_STAGE_TOOLCHAIN_INVALID')
            data['toolchain']['treeSha256'] = tree_digest(root / 'rust-toolchain', toolchain=True)
        receipt = {**data, 'version': 1,
                   'releaseTreeSha256': tree_digest(root / 'release', allowed_links(data['sourceAcquisition']))}
        require(hash_bytes(read_regular(root / 'release/bin/reviewer-mcp-http')) == data['reviewer']['binarySha256'],
                'INTENT_STAGE_REVIEWER_CHANGED')
        atomic(root / 'receipt.json', (json.dumps(receipt, sort_keys=True) + '\n').encode(), 0o600)
        return verify(root, data)
    receipt = verify(root, data)
    if action == 'verify':
        return receipt
    if action == 'consume-toolchain':
        toolchain = receipt['toolchain']
        require(toolchain['livePrefix'] == data['expectedToolchainPrefix'], 'INTENT_STAGE_TOOLCHAIN_DESTINATION_CHANGED')
        if toolchain['stagedPrefix']:
            destination = Path(toolchain['livePrefix'])
            require(destination.is_absolute() and not destination.exists() and not destination.is_symlink(),
                    'INTENT_STAGE_TOOLCHAIN_DESTINATION_CHANGED')
            missing, parent = [], destination.parent
            while not parent.exists() and not parent.is_symlink():
                missing.append(parent)
                parent = parent.parent
            protected(parent, directory=True)
            for directory in reversed(missing):
                directory.mkdir(mode=0o751)
                directory.chmod(0o751)
            copy_tree(root / 'rust-toolchain', destination)
        else:
            protected(Path(toolchain['livePrefix']), directory=True)
        return receipt
    require(action in ('consume', 'check-destination'), 'INTENT_STAGE_ACTION_INVALID')
    destination = consume_destination(root, data, argument)
    compiler = Path(receipt['toolchain']['livePrefix'])
    if receipt['toolchain']['stagedPrefix']:
        require(not compiler.exists() and not compiler.is_symlink(), 'INTENT_STAGE_TOOLCHAIN_DESTINATION_CHANGED')
        parent = compiler.parent
        while not parent.exists() and not parent.is_symlink():
            parent = parent.parent
        protected(parent, directory=True)
    else:
        protected(compiler, directory=True)
    plan = check_destination(root / 'release', destination, allowed_links(receipt['sourceAcquisition']))
    if action == 'check-destination':
        return plan
    copy_tree(root / 'release', destination)
    return receipt


if __name__ == '__main__':
    try:
        require(os.geteuid() == 0, 'INTENT_STAGE_ROOT_REQUIRED')
        action, root, *arguments = sys.argv[1:]
        require(action in ('extract', 'seal', 'verify', 'consume', 'normalize-links', 'consume-toolchain', 'check-toolchain', 'check-destination')
                and len(arguments) == (action in ('extract', 'consume', 'check-destination')),
                'INTENT_STAGE_ARGUMENT_INVALID')
        data = json.loads(sys.stdin.buffer.read(2 * 1024 * 1024 + 1))
        print(json.dumps(run(action, root, data, arguments[0] if arguments else None)))
    except (OSError, ValueError, KeyError, TypeError, UnicodeError, tarfile.TarError) as error:
        code = str(error)
        print(code if re.fullmatch('INTENT_[A-Z_]{1,70}', code) else 'INTENT_ARTIFACT_STAGE_UNPROVEN', file=sys.stderr)
        raise SystemExit(1) from None
