#!/usr/bin/env python3
"""Stage one selected App key without printing or replacing secrets.

Only the public deployment compiler supplies these paths and identities. The
owner-provided source stays untouched. Reviewer remains the default interface;
the separate Writer phase selects its fixed root-only ownership policy. Codex
and runner credentials are outside this helper's interface.
"""
import argparse
import grp
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys


from bootstrap_guard import ProtectedPath, mutation_guard, publish_no_replace, require


def validate_env(raw, destination, app_id, installation_id):
    require(re.fullmatch('[1-9][0-9]*', app_id) and
            re.fullmatch('[1-9][0-9]*', installation_id), 'app-identity')
    entries = {}
    for line in raw.decode('utf-8').splitlines():
        if not line or line.startswith('#'):
            continue
        require('=' in line, 'app-env')
        key, value = line.split('=', 1)
        require(key not in entries, 'app-env')
        entries[key] = value
    require(entries == {
        'GITHUB_APP_PRIVATE_KEY_FILE': destination,
        'GITHUB_APP_ID': app_id,
        'GITHUB_APP_INSTALLATION_ID': installation_id,
    }, 'app-env')


def validate_key(raw):
    # Never let OpenSSL prompt for encrypted material, inherit operator options,
    # write an output key, or echo private parser diagnostics into Ansible logs.
    require(re.fullmatch(rb'-{5}BEGIN (?:RSA )?PRIVATE KEY-{5}', raw.splitlines()[0])
            and b'ENCRYPTED' not in raw,
            'private-key')
    result = subprocess.run(
        ['/usr/bin/openssl', 'rsa', '-check', '-noout', '-passin', 'pass:'],
        input=raw, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=15, check=False,
        env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'})
    require(result.returncode == 0, 'private-key')


def stage(args):
    require(os.geteuid() == 0, 'root-required')
    role = getattr(args, 'role', 'reviewer')
    require(role in ['reviewer', 'writer'], 'credential-role')
    group = grp.getgrnam(args.group).gr_gid
    require(role != 'writer' or (args.group == 'root' and group == 0), 'writer-group')
    mode = 0o600 if role == 'writer' else 0o640
    prefix = role.upper() + '_CREDENTIAL'
    require(args.source != args.destination and args.env_file != args.destination
            and Path(args.env_file).parent == Path(args.destination).parent,
            'credential-layout')
    with mutation_guard(args.lock_file, args.operation_record, args.manifest, args.exact_head):
        with ProtectedPath(args.source) as source, ProtectedPath(args.destination) as target, \
                ProtectedPath(args.env_file) as env:
            env_raw, env_stamp = env.read({mode}, group=group, limit=8192)
            validate_env(env_raw, args.destination, args.app_id, args.installation_id)
            raw, source_stamp = source.read({0o600, 0o640})
            validate_key(raw)
            present, _ = target.read({mode}, group=group, absent=True)
            source.recheck(source_stamp)
            env.recheck(env_stamp)
            if present is not None:
                require(hmac.compare_digest(present, raw), 'existing-credential-differs')
                return {'changed': False, 'status': prefix + '_UNCHANGED',
                        'proof': prefix + '_STAGE=PASS;head=' + args.exact_head}
            target.recheck_parents()
            if args.check:
                return {'changed': True, 'status': prefix + '_STAGE_PLANNED',
                        'proof': prefix + '_STAGE=PLANNED;head=' + args.exact_head}
            temporary = '.' + role + '-key-' + secrets.token_hex(16)
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=target.fd)
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fchown(stream.fileno(), 0, group)
                    os.fchmod(stream.fileno(), mode)
                    os.fsync(stream.fileno())
                source.recheck(source_stamp)
                env.recheck(env_stamp)
                target.recheck_parents()
                # No replacement race and no second name left on the inode if
                # execution stops after the destination becomes durable.
                publish_no_replace(target.fd, temporary, target.path.name)
                os.fsync(target.fd)
            finally:
                try:
                    os.unlink(temporary, dir_fd=target.fd)
                except FileNotFoundError:
                    pass  # Successful publication already consumed this name.
                else:
                    os.fsync(target.fd)
            saved, _ = target.read({mode}, group=group)
            require(hmac.compare_digest(saved, raw), 'staged-credential-unproven')
            return {'changed': True, 'status': prefix + '_STAGED',
                    'proof': prefix + '_STAGE=PASS;head=' + args.exact_head}


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['source', 'destination', 'group', 'env-file', 'app-id', 'installation-id',
                 'lock-file', 'operation-record', 'manifest', 'exact-head']:
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--role', choices=['reviewer', 'writer'], default='reviewer')
    return parser.parse_args()


if __name__ == '__main__':
    args = arguments()
    try:
        print(json.dumps(stage(args), sort_keys=True))
    except (ValueError, OSError, KeyError, UnicodeError, subprocess.SubprocessError) as error:
        # Do not print exception messages: they may include secret parser input.
        code = str(error) if type(error) is ValueError and re.fullmatch('[a-z-]+', str(error)) else 'invalid-input-or-io'
        print(args.role.upper() + '_CREDENTIAL_STAGE_BLOCKED=' + code, file=sys.stderr)
        raise SystemExit(1)
