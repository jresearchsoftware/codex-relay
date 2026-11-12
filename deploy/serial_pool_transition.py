"""Read-only evidence for already completed SERIAL-to-pool cutovers.

No new transition, receipt, gate, source copy or runner mutation is supported.
The retained source/configuration seals still bind exact historical readers.
"""
from contextlib import contextmanager
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat

from managed_pool import require


MAX_BYTES = 1024 * 1024
MAX_SOURCE_FILES = 10000
MAX_SOURCE_BYTES = 64 * 1024 * 1024


def encoded(value):
    """Match JSON.stringify for the contract's JSON objects and integer IDs."""
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _stamp(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


class ProtectedFiles:
    """Descriptor-relative no-follow reads of retained protected evidence."""
    def __init__(self, root=Path('/'), owner_uid=0):
        self.root, self.owner_uid = Path(root), owner_uid

    def _directory(self, info):
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == self.owner_uid
                and not info.st_mode & 0o022, 'SERIAL_TRANSITION_PARENT_UNSAFE')

    @contextmanager
    def parent(self, logical):
        path = PurePosixPath(logical)
        require(path.is_absolute() and str(path) == str(logical)
                and all(part not in ['', '.', '..'] for part in path.parts[1:]),
                'SERIAL_TRANSITION_PATH_UNSAFE')
        descriptors = []
        try:
            current = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            descriptors.append(current)
            self._directory(os.fstat(current))
            for part in path.parts[1:-1]:
                current = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                  dir_fd=current)
                descriptors.append(current)
                self._directory(os.fstat(current))
            yield current, path.name
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)

    def read(self, logical, *, modes=None, optional=False, allow_empty=False, max_bytes=MAX_BYTES):
        try:
            with self.parent(logical) as (parent, name):
                descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                     dir_fd=parent)
                with os.fdopen(descriptor, 'rb') as stream:
                    info = os.fstat(stream.fileno())
                    require(stat.S_ISREG(info.st_mode) and info.st_uid == self.owner_uid
                            and info.st_nlink == 1 and not info.st_mode & 0o022
                            and (modes is None or stat.S_IMODE(info.st_mode) in modes)
                            and (allow_empty or info.st_size > 0) and info.st_size <= max_bytes,
                            'SERIAL_TRANSITION_FILE_UNSAFE')
                    raw = stream.read(max_bytes + 1)
                    require(len(raw) <= max_bytes and _stamp(info) == _stamp(os.fstat(stream.fileno()))
                            and _stamp(info) == _stamp(os.stat(name, dir_fd=parent, follow_symlinks=False)),
                            'SERIAL_TRANSITION_FILE_CHANGED')
                    return raw
        except FileNotFoundError:
            if optional:
                return None
            raise


    def tree_sha256(self, logical, *, source_links=None, original_source_root=None):
        rows = []
        total_bytes = 0
        links = {} if source_links is None else source_links
        components = {'controller', 'consumer', 'contracts', 'runtime', 'reviewer'}
        require(isinstance(links, dict) and len(links) <= 8 and all(
            isinstance(alias, str) and re.fullmatch(r'[A-Za-z0-9_./-]+', alias)
            and '/' in alias and all(part and part not in ['.', '..'] for part in alias.split('/'))
            and alias.split('/')[0] not in components | {'deploy'}
            and isinstance(component, str) and component in components
            for alias, component in links.items()), 'SERIAL_TRANSITION_SOURCE_LINKS_INVALID')
        if links:
            require(isinstance(original_source_root, str) and re.fullmatch(
                r'/opt/[a-z][a-z0-9-]{0,30}/releases/[0-9a-f]{40}/reviewed-source', original_source_root),
                'SERIAL_TRANSITION_SOURCE_LINKS_INVALID')
        observed_links = set()
        with self.parent(logical + '/.tree-boundary') as (root, _):
            def visit(directory, prefix):
                nonlocal total_bytes
                before = _stamp(os.fstat(directory))
                for name in os.listdir(directory):
                    relative = prefix + name
                    info = os.stat(name, dir_fd=directory, follow_symlinks=False)
                    if stat.S_ISLNK(info.st_mode):
                        require(relative in links and info.st_uid == self.owner_uid and info.st_nlink == 1,
                                'SERIAL_TRANSITION_SOURCE_LINK_UNPROVEN')
                        target = os.readlink(name, dir_fd=directory)
                        require(target == original_source_root + '/' + links[relative],
                                'SERIAL_TRANSITION_SOURCE_LINK_CHANGED')
                        with self.parent(target + '/.link-target-boundary'):
                            pass  # The fixed canonical component directory is protected.
                        require(_stamp(info) == _stamp(os.stat(name, dir_fd=directory, follow_symlinks=False))
                                and os.readlink(name, dir_fd=directory) == target,
                                'SERIAL_TRANSITION_SOURCE_LINK_CHANGED')
                        total_bytes += len(target.encode('utf-8'))
                        require(len(rows) < MAX_SOURCE_FILES and total_bytes <= MAX_SOURCE_BYTES,
                                'SERIAL_TRANSITION_SOURCE_LIMIT')
                        rows.append((relative.encode(), f'{relative}\0symlink\0{sha(target.encode())}\n'.encode()))
                        observed_links.add(relative)
                    elif stat.S_ISDIR(info.st_mode):
                        child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                        dir_fd=directory)
                        try:
                            self._directory(os.fstat(child))
                            visit(child, relative + '/')
                            require(_stamp(info) == _stamp(os.fstat(child)),
                                    'SERIAL_TRANSITION_SOURCE_CHANGED')
                        finally:
                            os.close(child)
                    else:
                        # Source blobs share the bounded tree budget. The small
                        # default read limit remains for protected control files.
                        require(info.st_size <= MAX_SOURCE_BYTES - total_bytes,
                                'SERIAL_TRANSITION_SOURCE_LIMIT')
                        raw = self.read(logical + '/' + relative, allow_empty=True,
                                        max_bytes=MAX_SOURCE_BYTES - total_bytes)
                        total_bytes += len(raw)
                        require(len(rows) < MAX_SOURCE_FILES and total_bytes <= MAX_SOURCE_BYTES,
                                'SERIAL_TRANSITION_SOURCE_LIMIT')
                        require(_stamp(info) == _stamp(os.stat(name, dir_fd=directory, follow_symlinks=False)),
                                'SERIAL_TRANSITION_SOURCE_CHANGED')
                        rows.append((relative.encode(), f'{relative}\0{info.st_mode & 0o777:o}\0{sha(raw)}\n'.encode()))
                require(before == _stamp(os.fstat(directory)), 'SERIAL_TRANSITION_SOURCE_CHANGED')
            visit(root, '')
        require(observed_links == set(links), 'SERIAL_TRANSITION_SOURCE_LINK_MISSING')
        require(rows, 'SERIAL_TRANSITION_SOURCE_EMPTY')
        return sha(b''.join(row for _, row in sorted(rows)))


def validate_delta(original, target):
    """Verify the policy boundary of an already retired cutover."""
    from config import derive_managed_pool_slots
    old, new = copy.deepcopy(original), copy.deepcopy(target)
    require('generalRunnerPool' not in old['consumer'] and 'executionSlots' not in old['consumer'],
            'SERIAL_TRANSITION_ORIGINAL_NOT_SERIAL')
    pool = new['consumer'].get('generalRunnerPool')
    require(isinstance(pool, dict) and set(pool) == {'desiredCapacity'}
            and type(pool['desiredCapacity']) is int and 1 <= pool['desiredCapacity'] <= 32,
            'SERIAL_TRANSITION_TARGET_NOT_POOL')
    # The original configuration is bound by its retained seals; the current
    # deployment validator validates the target. This is only a read boundary.
    derive_managed_pool_slots(new)
    require(original['environment']['generalRunner']['name'] not in {
        slot['runnerName'] for slot in new['consumer']['executionSlots']},
        'SERIAL_TRANSITION_REGISTRATION_NAME_COLLISION')
    new['consumer'].pop('generalRunnerPool')
    new['consumer'].pop('executionSlots')
    if 'repositories' in new['consumer']:
        anchor = old['consumer'].get('repository')
        repositories = new['consumer']['repositories']
        require(isinstance(anchor, str) and isinstance(repositories, list)
                and bool(repositories) and all(isinstance(repo, str) for repo in repositories)
                and len(set(repositories)) == len(repositories) and anchor in repositories
                and all(repo.split('/')[0] == anchor.split('/')[0] for repo in repositories)
                and 'repository' not in new['consumer']
                and new['environment'].get('repository') == anchor,
                'SERIAL_TRANSITION_REPOSITORY_SET_CHANGED')
        old_reviewers = old['environment'].get('reviewerRepositories', [anchor])
        new_reviewers = new['environment'].get('reviewerRepositories', repositories)
        require(isinstance(new_reviewers, list)
                and all(isinstance(repo, str) for repo in new_reviewers)
                and set(old_reviewers) <= set(new_reviewers) == set(repositories),
                'SERIAL_TRANSITION_REVIEWER_TARGETS_CHANGED')
        new['consumer'].pop('repositories')
        new['consumer']['repository'] = anchor
        for key in ['repository', 'reviewerRepositories']:
            if key in old['environment']:
                new['environment'][key] = copy.deepcopy(old['environment'][key])
            else:
                new['environment'].pop(key, None)
    for value in (old, new):
        value['source'].pop('revision', None)
        general = value['environment']['generalRunner']
        for key in ['name', 'scope', 'group', 'poolApp']:
            general.pop(key, None)
    require(old == new, 'SERIAL_TRANSITION_OWNER_INTENT_CHANGED')
    require(original['environment']['generalRunner']['user'] == target['environment']['generalRunner']['user'],
            'SERIAL_TRANSITION_RUNNER_IDENTITY_CHANGED')
    return True
