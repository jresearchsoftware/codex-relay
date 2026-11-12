#!/usr/bin/env python3
"""Send an existing gh credential to the root recovery entrypoint via SSH stdin."""
import argparse
import json
import posixpath
import re
import shlex
import subprocess
import sys


def absolute_path(value):
    if not value.startswith('/') or posixpath.normpath(value) != value or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise argparse.ArgumentTypeError('expected a normalized absolute path')
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True, help='SSH host or user@host configured with a trusted host key')
    parser.add_argument('--source', required=True, type=absolute_path, help='verified accepted root-owned source directory')
    parser.add_argument('--consumer', required=True, type=absolute_path, help='existing protected consumer config')
    parser.add_argument('--repository', required=True)
    parser.add_argument('--run-id', required=True, type=int)
    parser.add_argument('--operation', required=True, choices=['predispatch-state', 'finalize-predispatch'])
    parser.add_argument('--authorization-id', type=int)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_.@-]+', args.host) or args.host.startswith('-'):
        parser.error('invalid SSH host')
    if args.run_id < 1 or ((args.operation == 'finalize-predispatch') != (args.authorization_id is not None)) or (args.authorization_id is not None and args.authorization_id < 1):
        parser.error('invalid run or authorization ID')
    auth = subprocess.run(['gh', 'auth', 'token'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    token = auth.stdout.strip()
    if auth.returncode or not re.fullmatch(rb'[\x21-\x7e]{1,2048}', token):
        sys.exit('Unable to obtain the existing gh credential.')
    request = {'repository': args.repository, 'operation': args.operation, 'runId': args.run_id,
               'attemptId': f'run-{args.run_id}', 'workflowReadToken': token.decode('ascii')}
    if args.authorization_id is not None:
        request['authorizationId'] = args.authorization_id
    payload = json.dumps(request, separators=(',', ':')).encode()
    if len(payload) > 4096:
        sys.exit('Recovery request exceeds the entrypoint limit.')
    remote = ' '.join(map(shlex.quote, ['/usr/bin/env', '-i', 'PATH=/usr/bin:/bin', 'HOME=/root',
        'LANG=C', 'LC_ALL=C', f'RELAY_CONSUMER_CONFIG={args.consumer}', '/usr/bin/node',
        f'{args.source}/controller/src/predispatch-recovery-entrypoint.mjs']))
    result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
        args.host, remote], input=payload, check=False)
    return result.returncode


if __name__ == '__main__':
    sys.exit(main())
