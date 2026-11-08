#!/usr/bin/env python3
"""One persistent, host-local TEST ownership marker; no lease or age takeover."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone


DEFAULT = '/var/lib/codex-relay-test/test-environment.lock'


class Refusal(Exception):
    pass


@contextmanager
def marker(path):
    # Never unlink this inode: separate invocations must flock the same file.
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o660)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise Refusal('UNSAFE_TEST_LOCK')
        fcntl.flock(fd, fcntl.LOCK_EX)
        current = os.stat(path, follow_symlinks=False)
        if (info.st_dev, info.st_ino) != (current.st_dev, current.st_ino):
            raise Refusal('TEST_LOCK_REPLACED')
        with os.fdopen(os.dup(fd), 'r+', encoding='utf-8') as stream:
            raw = stream.read(16385)
            try:
                holder = json.loads(raw) if raw else None
                if holder is not None and (not isinstance(holder, dict) or
                        not all(holder.get(key) for key in ('task', 'execution', 'token'))):
                    raise ValueError()
            except (ValueError, TypeError):
                raise Refusal('TEST_LOCK_DAMAGED: inspect marker; do not assume free')
            yield stream, holder
    finally:
        os.close(fd)


def save(stream, holder):
    stream.seek(0)
    stream.write(json.dumps(holder, sort_keys=True) + '\n')
    stream.truncate()
    stream.flush()
    os.fsync(stream.fileno())


def operate(path, action, *, task=None, execution=None, token=None,
            usable=False, stopped=False):
    with marker(path) as (stream, holder):
        if action == 'status':
            return {'status': 'BUSY' if holder else 'FREE', 'holder': holder}
        if action == 'claim':
            if holder:
                return {'status': 'BLOCKED', 'holder': holder}
            holder = {'task': task, 'execution': execution, 'token': str(uuid.uuid4()),
                      'host': socket.gethostname(), 'pid': os.getpid(),
                      'claimed_at': datetime.now(timezone.utc).isoformat()}
            save(stream, holder)
            return {'status': 'CLAIMED', 'holder': holder}
        if not holder or holder['token'] != token:
            raise Refusal('TEST_LOCK_NOT_OWNED')
        if not usable:
            raise Refusal('TEST_USABLE_CONFIRMATION_REQUIRED: retain ownership until cleanup succeeds')
        if action == 'recover':
            if not stopped:
                raise Refusal('TEST_HOLDER_STOP_CONFIRMATION_REQUIRED')
        elif holder['task'] != task or holder['execution'] != execution:
            raise Refusal('TEST_LOCK_NOT_OWNED')
        save(stream, None)
        return {'status': 'RELEASED', 'holder': holder}


def run_owned(args):
    claim = operate(args.path, 'claim', task=args.task, execution=args.execution)
    print(json.dumps(claim), flush=True)
    if claim['status'] == 'BLOCKED':
        return 2
    # A crash/kill, or failed cleanup, deliberately leaves diagnosable ownership.
    try:
        result = subprocess.run(args.command, check=False).returncode
    except OSError:
        result = 127  # Failed launch is handled; interruption keeps ownership.
    cleanup = subprocess.run([args.cleanup_script], check=False).returncode
    if cleanup == 0:
        print(json.dumps(operate(args.path, 'release', task=args.task,
            execution=args.execution, token=claim['holder']['token'], usable=True)), flush=True)
    else:
        raise Refusal('TEST_CLEANUP_FAILED: ownership retained')
    return result if result >= 0 else 128 - result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--path', default=DEFAULT, help='same absolute host-local path for every TEST user')
    commands = parser.add_subparsers(dest='action', required=True)
    commands.add_parser('status')
    for action in ('claim', 'release', 'recover', 'run'):
        command = commands.add_parser(action)
        if action != 'recover':
            command.add_argument('--task', required=True, help='repository#issue')
            command.add_argument('--execution', required=True, help='unique run/session identity')
        if action in ('release', 'recover'):
            command.add_argument('--token', required=True, help='exact observed ownership token')
            command.add_argument('--test-usable', action='store_true')
        if action == 'recover':
            command.add_argument('--confirm-holder-stopped', action='store_true')
        if action == 'run':
            command.add_argument('--cleanup-script', required=True,
                                 help='executable restoring/verifying usable TEST; zero means safe handback')
            command.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not Path(args.path).is_absolute():
        parser.error('--path must be absolute')
    try:
        if args.action == 'run':
            if args.command[:1] == ['--']:
                args.command = args.command[1:]
            if not args.command:
                parser.error('run needs a command after --')
            return run_owned(args)
        result = operate(args.path, args.action, task=getattr(args, 'task', None),
            execution=getattr(args, 'execution', None), token=getattr(args, 'token', None),
            usable=getattr(args, 'test_usable', False),
            stopped=getattr(args, 'confirm_holder_stopped', False))
        print(json.dumps(result))
        return 2 if result['status'] == 'BLOCKED' else 0
    except (Refusal, OSError) as error:
        print(json.dumps({'status': 'BLOCKED', 'reason': str(error)}))
        return 2


if __name__ == '__main__':
    sys.exit(main())
