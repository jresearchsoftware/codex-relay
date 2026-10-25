"""Read-only stop for an unqualified SERIAL-to-pool configuration transition.

Changing the consumer digest also changes admission and original-attempt
recovery bindings. Registration-name changes or stopping the old service cannot
establish that compatibility. Preserve all original state before owner design.
"""
from contextlib import ExitStack, contextmanager
import os
from pathlib import Path
import stat

from managed_pool import PoolError, require
from pool_eligibility import _directory, _open_directory, _read, _json, _peer, NAMESPACE


@contextmanager
def _legacy_boundary(contract, root, owner_uid):
    namespace = contract['namespace']
    require(isinstance(namespace, str) and NAMESPACE.fullmatch(namespace), 'SERIAL_STATE_UNPROVEN')
    with ExitStack() as stack:
        descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        stack.callback(os.close, descriptor)
        _directory(os.fstat(descriptor), owner_uid)

        def present(parts):
            parent = descriptor
            for name in parts[:-1]:
                try:
                    parent = _open_directory(parent, name, owner_uid, stack, [])
                except FileNotFoundError:
                    return False
            try:
                os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
                return True
            except FileNotFoundError:
                return False

        # Presence is enough to stop; credentials and original journals are
        # never opened, repaired, moved or reinterpreted as pool ownership.
        legacy = present(['opt', namespace, 'general-runner'])
        legacy |= present(['etc', 'systemd', 'system', namespace + '-general-runner.service'])
        require(not legacy, 'SERIAL_TRANSITION_REQUIRED')
        yield namespace, descriptor, stack


def reject_legacy_registration(contract, *, root=Path('/'), owner_uid=0):
    """Reject legacy artifacts after the caller authenticates managed current.

    This guard grants no source, resource or pool eligibility proof. It does not
    read a mutable deployment snapshot or any legacy credentials/journals.
    """
    with _legacy_boundary(contract, root, owner_uid):
        pass


def reject_serial_transition(contract, *, root=Path('/'), owner_uid=0):
    with _legacy_boundary(contract, root, owner_uid) as (namespace, descriptor, stack):
        try:
            opt = _open_directory(descriptor, 'opt', owner_uid, stack, [])
            install = _open_directory(opt, namespace, owner_uid, stack, [])
            current = os.stat('current', dir_fd=install, follow_symlinks=False)
        except FileNotFoundError:
            return  # genuinely fresh or an unregistered partial pool install
        require(stat.S_ISLNK(current.st_mode) and current.st_uid == owner_uid, 'SERIAL_STATE_UNPROVEN')
        link = os.readlink('current', dir_fd=install)
        import re
        prefix = '(?:/opt/' + re.escape(namespace) + '/)?releases/'
        match = re.fullmatch(prefix + '([0-9a-f]{40})', link)
        require(match is not None, 'SERIAL_STATE_UNPROVEN')
        releases = _open_directory(install, 'releases', owner_uid, stack, [])
        release = _open_directory(releases, match[1], owner_uid, stack, [])
        raw, _ = _read(release, 'deployment-config.json', {0o600}, owner_uid, private=True)
        config = _json(raw)
        require(isinstance(config.get('consumer'), dict), 'SERIAL_STATE_UNPROVEN')
        require('generalRunnerPool' in config['consumer'], 'SERIAL_TRANSITION_REQUIRED')
        require(_peer(opt, namespace, contract, owner_uid) is not None, 'SERIAL_STATE_UNPROVEN')
