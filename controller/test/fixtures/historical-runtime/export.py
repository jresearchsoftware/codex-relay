#!/usr/bin/env python3
"""Retain exact test source plus Git proofs from an already acquired repository.

No network access, checkout, ref/config changes or product installation.
Usage: python3 export.py /path/to/repository-or-bare.git
"""
import base64
import json
from pathlib import Path
import subprocess
import sys

REVISIONS = (
    '3f4d4348cfb05866b2108eadcc35b7a17153ff14',
    'f6431d612d464c511fdda97e7dea64ace7f03ac7',
    '0aff32a6873262185f60364463f4e97ef330de89',
)
PATHS = ('consumer', 'controller/src', 'runtime/src', 'contracts/src',
         'reviewer/src/executable-cr-v2.json')


def export(repository, revision):
    def git(*args):
        return subprocess.check_output(['git', '-C', repository, *args])

    commit = git('cat-file', 'commit', revision).decode('utf-8')
    trees, files = {}, {}

    def visit(oid, path=''):
        raw = git('cat-file', 'tree', oid)
        trees[path] = base64.b64encode(raw).decode('ascii')
        for entry in git('ls-tree', '-z', oid).split(b'\0'):
            if not entry:
                continue
            metadata, name = entry.split(b'\t', 1)
            mode, kind, child = metadata.decode('ascii').split()
            name = name.decode('utf-8')
            target = f'{path}/{name}' if path else name
            if not any(target == p or target.startswith(p + '/') or p.startswith(target + '/') for p in PATHS):
                continue
            if kind == 'tree':
                visit(child, target)
            else:
                if mode not in ('100644', '100755') or kind != 'blob':
                    raise ValueError(f'Unsupported fixture object: {target}')
                files[target] = git('cat-file', 'blob', child).decode('utf-8')

    visit(commit.splitlines()[0].removeprefix('tree '))
    return json.dumps({'revision': revision, 'commit': commit, 'trees': trees, 'files': files},
                      indent=2, ensure_ascii=False) + '\n'


if __name__ == '__main__':
    for revision in REVISIONS:
        destination = Path(__file__).parent / f'{revision}.json'
        destination.write_text(export(sys.argv[1], revision), encoding='utf-8')
        print(destination.name)
