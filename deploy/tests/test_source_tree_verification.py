"""Whole installed-source verification must accept the complete candidate tree."""
import hashlib
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
import serial_pool_transition as transition
from managed_pool import PoolError

FIXTURE = 'controller/test/fixtures/historical-runtime/3f4d4348cfb05866b2108eadcc35b7a17153ff14.json'
pytestmark = pytest.mark.skipif(sys.platform != 'linux', reason='Linux descriptor and ownership boundary')


@pytest.fixture
def protected(tmp_path):
    tmp_path.chmod(0o700)
    return transition.ProtectedFiles(tmp_path, os.getuid())


def write(root, relative, raw):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    path.chmod(0o644)
    return path


def test_actual_oversized_fixture_is_hashed_but_control_reads_remain_bounded(tmp_path, protected):
    raw = (ROOT / FIXTURE).read_bytes()
    assert len(raw) == 1065228 and len(raw) > transition.MAX_BYTES
    path = write(tmp_path, 'source/' + FIXTURE, raw)
    expected = transition.sha((FIXTURE + '\0' + '644\0' + transition.sha(raw) + '\n').encode())
    assert protected.tree_sha256('/source') == expected
    with pytest.raises(PoolError, match='FILE_UNSAFE'):
        protected.read('/source/' + FIXTURE)
    path.write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
    assert protected.tree_sha256('/source') != expected


def test_complete_candidate_git_tree_is_verified_without_exclusions(tmp_path, protected):
    entries = subprocess.check_output(['git', 'ls-files', '--stage', '-z'], cwd=ROOT).split(b'\0')
    rows = []
    paths = set()
    for entry in filter(None, entries):
        metadata, name = entry.split(b'\t', 1)
        mode, _, stage = metadata.split()
        assert stage == b'0' and mode in (b'100644', b'100755')
        relative = name.decode()
        raw = (ROOT / relative).read_bytes()
        path = write(tmp_path, 'source/' + relative, raw)
        permissions = int(mode[-3:], 8)
        path.chmod(permissions)
        rows.append((name, name + b'\0' + mode[-3:] + b'\0' + hashlib.sha256(raw).hexdigest().encode() + b'\n'))
        paths.add(relative)
    assert FIXTURE in paths
    expected = transition.sha(b''.join(row for _, row in sorted(rows)))
    assert protected.tree_sha256('/source') == expected


@pytest.mark.parametrize('fault', ['symlink', 'hardlink', 'writable', 'owner', 'parent-writable'])
def test_large_source_file_protections_are_retained(tmp_path, protected, monkeypatch, fault):
    path = write(tmp_path, 'source/blob', b'x' * (transition.MAX_BYTES + 1))
    if fault == 'symlink':
        target = tmp_path / 'outside'
        path.rename(target)
        path.symlink_to(target)
    elif fault == 'hardlink':
        os.link(path, tmp_path / 'outside')
    elif fault == 'writable':
        path.chmod(0o666)
    elif fault == 'owner':
        fstat = os.fstat

        def foreign_file(descriptor):
            info = fstat(descriptor)
            if stat.S_ISREG(info.st_mode):
                values = list(info)
                values[4] = os.getuid() + 1
                return os.stat_result(values)
            return info

        monkeypatch.setattr(transition.os, 'fstat', foreign_file)
    else:
        path.parent.chmod(0o777)
    with pytest.raises(PoolError, match='SOURCE_LINK_UNPROVEN|FILE_UNSAFE|PARENT_UNSAFE'):
        protected.tree_sha256('/source')


def test_large_source_change_during_verification_is_rejected(tmp_path, protected, monkeypatch):
    path = write(tmp_path, 'source/blob', b'x' * (transition.MAX_BYTES + 1))
    read = protected.read

    def changed(*args, **kwargs):
        raw = read(*args, **kwargs)
        path.write_bytes(b'y' * len(raw))
        return raw

    monkeypatch.setattr(protected, 'read', changed)
    with pytest.raises(PoolError, match='SOURCE_CHANGED'):
        protected.tree_sha256('/source')


@pytest.mark.parametrize('sizes', [(17,), (8, 9)])
def test_source_total_budget_is_preserved(tmp_path, protected, monkeypatch, sizes):
    monkeypatch.setattr(transition, 'MAX_SOURCE_BYTES', 16)
    for index, size in enumerate(sizes):
        write(tmp_path, 'source/' + str(index), b'x' * size)
    with pytest.raises(PoolError, match='SOURCE_LIMIT'):
        protected.tree_sha256('/source')


def test_source_file_count_budget_is_preserved(tmp_path, protected, monkeypatch):
    monkeypatch.setattr(transition, 'MAX_SOURCE_FILES', 1)
    write(tmp_path, 'source/a', b'')
    write(tmp_path, 'source/b', b'')
    with pytest.raises(PoolError, match='SOURCE_LIMIT'):
        protected.tree_sha256('/source')
