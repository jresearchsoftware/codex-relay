"""Actual tracked large source blobs retain the separate installed graph bound."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
import bounded_recovery as recovery

REVISION = 'a' * 40


@pytest.fixture
def graph(tmp_path):
    release = tmp_path / 'opt/relay-source-fixture/releases' / REVISION
    source = release / 'reviewed-source'
    fixtures = Path('controller/test/fixtures/historical-runtime')
    (source / fixtures).mkdir(parents=True)
    blobs = []
    for original in sorted((ROOT / fixtures).glob('*.json')):
        target = source / fixtures / original.name
        shutil.copyfile(original, target)
        target.chmod(0o644)
        assert target.stat().st_size > recovery.LIMIT
        blobs.append(target)
    assert len(blobs) == 3, 'the actual tracked historical runtime source fixtures are required'
    snapshot = b'{"source":{"revision":"' + REVISION.encode() + b'"}}\n'
    (release / 'deployment-config.json').write_bytes(snapshot)
    (release / 'deployment-config.json').chmod(0o600)
    manifest = {'commit': REVISION, 'installedRevision': REVISION, 'resolvedRevision': REVISION,
        'gitTree': 'b' * 40, 'deploymentConfigSha256': hashlib.sha256(snapshot).hexdigest(),
        'deploymentContract': {'schemaVersion': 1, 'epoch': 1,
            'capabilities': ['lifecycle-v1', 'git-desired-v1', 'integration-artifact-v1']},
        'gitConfigReceipt': {'product_sha': REVISION, 'config_sha': 'c' * 40,
            'config_blob_sha': 'd' * 40, 'config_sha256': 'e' * 64}}
    (release / 'artifact-manifest.json').write_text(json.dumps(manifest))
    (source / '.relay-source.json').write_text(json.dumps({'revision': REVISION, 'tree': 'b' * 40}))
    return tmp_path, release, source, blobs


def capture(graph):
    root, release, _, _ = graph
    return recovery.installed(release, REVISION, root, os.geteuid())


def test_complete_actual_large_source_blobs_are_read_and_bound(graph):
    before = capture(graph)
    assert len(before[2]['sourceGraphSha256']) == 64
    # A changed byte in EACH previously refused public fixture changes the full
    # graph witness: no exclusion or metadata-only treatment hides these blobs.
    for path in graph[3]:
        original = path.read_bytes()
        path.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
        assert capture(graph)[2]['sourceGraphSha256'] != before[2]['sourceGraphSha256']
        path.write_bytes(original)
    assert capture(graph) == before
    with pytest.raises(ValueError, match='EVIDENCE_UNSAFE'):
        recovery.read(graph[3][0], graph[0], os.geteuid())


def test_source_file_and_aggregate_overflow_are_bounded_before_read(graph, monkeypatch):
    path = graph[2] / 'oversized-source-blob'
    with path.open('wb') as stream:
        stream.truncate(recovery.SOURCE_LIMIT + 1)
    with pytest.raises(ValueError, match='SOURCE_LIMIT'):
        capture(graph)
    with pytest.raises(ValueError, match='EVIDENCE_UNSAFE'):
        recovery.read(path, graph[0], os.geteuid(), limit=recovery.SOURCE_LIMIT)
    path.unlink()
    # Individually valid actual blobs collectively exceed this test-only graph
    # budget. No large allocation is needed to exercise aggregate enforcement.
    maximum = max(path.stat().st_size for path in graph[3])
    monkeypatch.setattr(recovery, 'SOURCE_LIMIT', maximum + 65536)
    with pytest.raises(ValueError, match='SOURCE_LIMIT'):
        capture(graph)


@pytest.mark.parametrize('name', ['artifact-manifest.json', 'deployment-config.json'])
def test_metadata_receipt_limit_remains_512k(graph, name):
    path = graph[1] / name
    with path.open('ab') as stream:
        stream.write(b' ' * (recovery.LIMIT + 1))
    with pytest.raises(ValueError, match='EVIDENCE_UNSAFE'):
        capture(graph)


@pytest.mark.parametrize('damage', ['unsafe-mode', 'hardlink', 'symlink'])
def test_large_source_blob_retains_protected_file_contract(graph, damage):
    path = graph[3][0]
    if damage == 'unsafe-mode':
        path.chmod(0o666)
    elif damage == 'hardlink':
        os.link(path, graph[0] / 'aliased-source')
    else:
        saved = graph[0] / 'foreign-source'
        path.rename(saved)
        path.symlink_to(saved)
    with pytest.raises(ValueError, match='(?:PATH_UNSAFE|SOURCE_ALIAS_UNPROVEN)'):
        capture(graph)


def test_large_source_read_still_rejects_mutation_after_read(graph, monkeypatch):
    path = graph[3][0]
    original_fdopen = recovery.os.fdopen
    class MovingReader:
        def __init__(self, stream): self.stream = stream
        def __enter__(self): return self
        def __exit__(self, *args): return self.stream.__exit__(*args)
        def fileno(self): return self.stream.fileno()
        def read(self, size):
            raw = self.stream.read(size)
            with path.open('ab') as writer: writer.write(b'changed')
            return raw
    monkeypatch.setattr(recovery.os, 'fdopen', lambda *args, **kwargs: MovingReader(original_fdopen(*args, **kwargs)))
    with pytest.raises(ValueError, match='EVIDENCE_CHANGED'):
        recovery.read(path, graph[0], os.geteuid(), limit=recovery.SOURCE_LIMIT)
