"""One-shot Task115 disposable TEST cleanup, never a production interface."""
import fcntl
import hashlib
import json
import os
from pathlib import Path

ROOT = Path('/var/lib/codex-relay-test')
WORK = ROOT / 'qualification-step2-01a12efc'
CURRENT = Path('/opt/codex-relay-test/current')
OLD = '/opt/codex-relay-test/releases/5699432e95440307fa799b0a3b8ac3150ffd574a'
assert os.getuid() == 0 and ROOT.resolve() == ROOT and WORK.resolve() == WORK
assert str(CURRENT.resolve()) == OLD
restoration = json.loads((WORK / 'restore-receipt.json').read_text())
assert restoration['stage'] == 'original_pointer_and_service_activity_restored'
archived = WORK / 'completed-synthetic-records'
archived.mkdir(mode=0o700, exist_ok=False)
records = []
with (ROOT / 'writer-claims/publication-v2.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    for run in range(9007115000401, 9007115000405):
        paths = [(ROOT / f'writer-claims/publication-v2/{run}.json', 'claim')]
        if run >= 9007115000403:
            paths.append((ROOT / f'dispatch/attempts-v2/{run}.json', 'journal'))
        for path, kind in paths:
            assert path.resolve() == path and path.is_file()
            raw = path.read_bytes()
            record = json.loads(raw)
            seed = json.loads((WORK / f'relay-task115-step2-fixture-final/{run}.{kind}.json').read_text())
            assert record['envelope'] == seed['envelope']
            assert record['qualificationFixture']['synthetic']
            assert not record['qualificationFixture']['realExecution']
            assert record['envelope']['repository'] == 'jresearchsoftware/codex-relay-testbed'
            assert record['envelope']['runId'] == run
            (archived / f'{run}.{kind}.json').write_bytes(raw)
            records.append({'run': run, 'kind': kind, 'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(), 'immutable_envelope_unchanged': True})
    for record in records:
        Path(record['path']).unlink()
    attempts = ROOT / 'dispatch/attempts-v2'
    attempts_directory_removed = False
    if not any(attempts.iterdir()):
        attempts.rmdir()
        attempts_directory_removed = True
receipt = {'scope': 'isolated TEST synthetic records only', 'records': records, 'attempts_directory_removed_if_empty': attempts_directory_removed, 'native_history_preserved': True}
(WORK / 'cleanup-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt))
