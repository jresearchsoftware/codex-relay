#!/usr/bin/env python3
"""Stage one owner-provided Codex token without replacement or secret output.

The runtime owns only the final credential directory and file. Root never writes
or changes ownership through a name inside that mutable directory: it prepares
the token in a private root directory, then atomically publishes without replace.
"""
import argparse
import ctypes
import grp
import hmac
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import stat
import sys

from bootstrap_guard import ProtectedPath, mutation_guard, require, stamp


MAX_TOKEN_BYTES = 16 * 1024  # Same bound as the installed Codex launcher.


def validate_token(raw):
    # An opaque bearer token is one printable ASCII line; preserve its bytes,
    # including an optional terminal newline, exactly as the owner supplied it.
    require(0 < len(raw) <= MAX_TOKEN_BYTES
            and re.fullmatch(rb'[!-~]+(?:\r?\n)?', raw), 'token-format')


class CodexTokenTarget:
    """One explicitly typed runtime-owned leaf below root-protected parents."""

    def __init__(self, config_root, destination, uid, gid):
        self.path = Path(destination)
        require(self.path == Path(config_root) / 'codex-credentials' / 'access-token'
                and str(self.path) == destination and uid > 0 and gid > 0,
                'credential-layout')
        self.uid, self.gid = uid, gid
        self.parent = ProtectedPath(str(self.path.parent))
        self.fd = None

    def __enter__(self):
        self.parent.__enter__()
        try:
            self.fd = os.open(self.parent.path.name,
                              os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                              dir_fd=self.parent.fd)
            self.identity = self.directory_identity(os.fstat(self.fd))
            self.recheck_parents()
            return self
        except BaseException:
            self.__exit__()
            raise

    def __exit__(self, *_):
        if self.fd is not None:
            os.close(self.fd)
        self.parent.__exit__()

    def directory_identity(self, info):
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == self.uid
                and info.st_gid == self.gid and stat.S_IMODE(info.st_mode) == 0o700,
                'credential-directory')
        return info.st_dev, info.st_ino

    def recheck_parents(self):
        self.parent.recheck_parents()
        require(self.directory_identity(self.parent.metadata()) == self.identity
                and self.directory_identity(os.fstat(self.fd)) == self.identity,
                'credential-directory-changed')

    def read(self, *, absent=False):
        self.recheck_parents()
        try:
            fd = os.open(self.path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=self.fd)
        except FileNotFoundError:
            require(absent, 'missing-file')
            return None
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_uid == self.uid
                    and info.st_gid == self.gid and info.st_nlink == 1
                    and stat.S_IMODE(info.st_mode) == 0o600, 'file-metadata')
            raw = stream.read(MAX_TOKEN_BYTES + 1)
            validate_token(raw)
            require(stamp(os.fstat(stream.fileno())) == stamp(info), 'file-changed')
        self.recheck_parents()
        require(stamp(os.stat(self.path.name, dir_fd=self.fd, follow_symlinks=False))
                == stamp(info), 'file-changed')
        return raw


def publish_token(source_fd, target_fd):
    """Cross-directory no-replace rename; never follow a runtime-owned name."""
    rename = getattr(ctypes.CDLL(None, use_errno=True), 'renameat2', None)
    require(rename is not None, 'atomic-publication-unavailable')
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                       ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(source_fd, b'access-token', target_fd, b'access-token', 1) != 0:
        raise OSError(ctypes.get_errno(), 'atomic-publication-failed')


def stage(args):
    require(os.geteuid() == 0, 'root-required')
    user, group = pwd.getpwnam(args.user), grp.getgrnam(args.group)
    require(user.pw_gid == group.gr_gid, 'credential-identity')
    require(args.source != args.destination, 'credential-layout')
    with mutation_guard(args.lock_file, args.operation_record, args.manifest, args.exact_head):
        with ProtectedPath(args.source) as source, CodexTokenTarget(
                args.config_root, args.destination, user.pw_uid, group.gr_gid) as target:
            raw, source_stamp = source.read({0o600}, group=0, limit=MAX_TOKEN_BYTES)
            validate_token(raw)
            present = target.read(absent=True)
            source.recheck(source_stamp)
            if present is not None:
                require(hmac.compare_digest(present, raw), 'existing-credential-differs')
                return result(False, 'UNCHANGED', args.exact_head)
            if args.check:
                return result(True, 'STAGE_PLANNED', args.exact_head, planned=True)
            # The config root stays root-owned and non-writable by the runtime.
            # A private root-owned directory keeps the prepared inode inaccessible
            # even after fchown, until the final atomic publication.
            temporary = '.codex-token-' + secrets.token_hex(16)
            os.mkdir(temporary, 0o700, dir_fd=target.parent.fd)
            staging_fd = os.open(temporary, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                 dir_fd=target.parent.fd)
            try:
                fd = os.open('access-token', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=staging_fd)
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fchown(stream.fileno(), user.pw_uid, group.gr_gid)
                    os.fchmod(stream.fileno(), 0o600)
                    os.fsync(stream.fileno())
                source.recheck(source_stamp)
                target.recheck_parents()
                publish_token(staging_fd, target.fd)
                os.fsync(target.fd)
                os.fsync(staging_fd)
            finally:
                try:
                    os.unlink('access-token', dir_fd=staging_fd)
                except FileNotFoundError:
                    pass  # Atomic publication consumed the private name.
                os.close(staging_fd)
                os.rmdir(temporary, dir_fd=target.parent.fd)
                os.fsync(target.parent.fd)
            require(hmac.compare_digest(target.read(), raw), 'staged-credential-unproven')
            source.recheck(source_stamp)
            return result(True, 'STAGED', args.exact_head)


def result(changed, status, head, *, planned=False):
    return {'changed': changed, 'status': 'CODEX_CREDENTIAL_' + status,
            'proof': 'CODEX_CREDENTIAL_STAGE=' + ('PLANNED' if planned else 'PASS') + ';head=' + head}


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['source', 'destination', 'config-root', 'user', 'group',
                 'lock-file', 'operation-record', 'manifest', 'exact-head']:
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--check', action='store_true')
    return parser.parse_args()


if __name__ == '__main__':
    try:
        print(json.dumps(stage(arguments()), sort_keys=True))
    except (ValueError, OSError, KeyError, UnicodeError) as error:
        # Credential parser/OS messages are never copied into Ansible output.
        code = str(error) if type(error) is ValueError and re.fullmatch('[a-z-]+', str(error)) else 'invalid-input-or-io'
        print('CODEX_CREDENTIAL_STAGE_BLOCKED=' + code, file=sys.stderr)
        raise SystemExit(1)
