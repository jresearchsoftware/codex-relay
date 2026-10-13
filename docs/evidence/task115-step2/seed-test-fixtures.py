import fcntl, hashlib, json, os, pathlib, shutil
ROOT = pathlib.Path('/var/lib/codex-relay-test')
WORK = ROOT / 'qualification-step2-01a12efc'
SOURCE = WORK / 'relay-task115-step2-fixture-final'
assert os.getuid() == 0 and ROOT.resolve() == ROOT and SOURCE.resolve() == SOURCE
assert str(pathlib.Path('/opt/codex-relay-test/current').resolve()) == '/opt/codex-relay-test/qualification-step2-3fff414'
receipt = []
with (ROOT / 'writer-claims/publication-v2.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    specs = []
    for run in range(9007115000401, 9007115000405):
        source = SOURCE / f'{run}.claim.json'
        record = json.loads(source.read_text())
        assert record['envelope']['runId'] == run and record['envelope']['repository'] == 'jresearchsoftware/codex-relay-testbed'
        assert record['envelope']['consumerDigest'] == '18fdd7fa538be3aef3ee6000181018230c5120f7371d524707b362e8bff30a5c'
        assert record['qualificationFixture']['synthetic'] and not record['qualificationFixture']['realExecution']
        specs.append((source, ROOT / f'writer-claims/publication-v2/{run}.json'))
        if run >= 9007115000403:
            specs.append((SOURCE / f'{run}.journal.json', ROOT / f'dispatch/attempts-v2/{run}.json'))
    for source, dest in specs:
        assert not dest.is_symlink()
        if dest.exists():
            assert dest.is_file() and dest.stat().st_uid == 0 and not dest.stat().st_mode & 0o077
            assert dest.read_bytes() == source.read_bytes()
    for source, dest in specs:
        assert dest.parent.resolve().is_relative_to(ROOT)
        dest.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        existed = dest.exists()
        if not existed:
            shutil.copyfile(source, dest)
        os.chown(dest, 0, 0)
        dest.chmod(0o600)
        receipt.append({'path': str(dest), 'sha256': hashlib.sha256(dest.read_bytes()).hexdigest(), 'run': json.loads(dest.read_text())['envelope']['runId'], 'existing_verified_own_partial_seed': existed})
(WORK / 'seed-receipt.json').write_text(json.dumps({'synthetic': True, 'real_admission': False, 'real_execution': False, 'records': receipt}, indent=2) + '\n')
print(json.dumps({'synthetic': True, 'real_admission': False, 'real_execution': False, 'records': receipt}))
