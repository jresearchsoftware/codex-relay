import hashlib, json, os, pathlib, shutil, subprocess, tarfile, grp

WORK = pathlib.Path('/var/lib/codex-relay-test/qualification-step2-01a12efc')
SLOT = pathlib.Path('/opt/codex-relay-test/qualification-step2-3fff414')
CURRENT = pathlib.Path('/opt/codex-relay-test/current')
OLD = '/opt/codex-relay-test/releases/5699432e95440307fa799b0a3b8ac3150ffd574a'
REV = '3fff4140c57b993b9f006159529d9459ec9ace13'
ARCHIVE = 'a68cee8f2bae7aefedf33f2627415e5209c25ec0e114c6699f7b11482fe059af'
BINARY = '0eb7a7bc6ad040de273bfe92a86914696357677a99c16a7fbd296117f1925145'
UNITS = ['codex-relay-test-reviewer.service', 'codex-relay-test-runner.service', 'codex-relay-test-general-runner.service', 'codex-relay-test-relay-manual-outcome.socket']

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

assert os.getuid() == 0 and str(CURRENT.resolve()) == OLD and not SLOT.exists()
assert str(WORK.resolve()) == str(WORK) and WORK.is_dir()
assert digest(WORK / 'task115-step2-source.tar') == ARCHIVE
assert digest(WORK / 'reviewer-mcp-http') == BINARY
env = {'RELAY_CONSUMER_CONFIG': '/etc/codex-relay-test/consumer.json', 'PATH': '/usr/bin:/bin', 'HOME': '/root', 'LANG': 'C', 'LC_ALL': 'C'}
status = json.loads(subprocess.check_output(['/opt/codex-relay-test/node22/bin/node', OLD + '/reviewed-source/controller/src/admission-cli.mjs', 'status'], env=env, text=True))
assert not status['active'] and not status['unknown'] and status['phase'] == 'open'
states = {u: subprocess.run(['systemctl', 'is-active', '--quiet', u]).returncode == 0 for u in UNITS}
assert states[UNITS[0]] and states[UNITS[3]]
receipt = {'scope': 'temporary isolated TEST candidate installation; not a product lifecycle receipt', 'source_revision': REV, 'old_pointer': OLD, 'candidate_pointer': str(SLOT), 'archive_sha256': ARCHIVE, 'reviewer_binary_sha256': BINARY, 'original_active': states, 'admission_status_before': status, 'stage': 'prepared'}
(WORK / 'stage-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
SLOT.mkdir(mode=0o751)
source = SLOT / 'reviewed-source'
source.mkdir(mode=0o751)
with tarfile.open(WORK / 'task115-step2-source.tar') as archive:
    for member in archive.getmembers():
        p = pathlib.PurePosixPath(member.name)
        assert not p.is_absolute() and '..' not in p.parts and (member.isfile() or member.isdir())
        assert (source / member.name).resolve().is_relative_to(source)
    archive.extractall(source)
for path in source.rglob('*'):
    assert not path.is_symlink()
    os.chown(path, 0, 0)
    path.chmod(0o755 if path.is_dir() or path.stat().st_mode & 0o111 else 0o644)
(SLOT / 'bin').mkdir(mode=0o751)
shutil.copyfile(WORK / 'reviewer-mcp-http', SLOT / 'bin/reviewer-mcp-http')
os.chown(SLOT / 'bin/reviewer-mcp-http', 0, grp.getgrnam('relay-test-reviewer').gr_gid)
(SLOT / 'bin/reviewer-mcp-http').chmod(0o750)
assert digest(SLOT / 'bin/reviewer-mcp-http') == BINARY
files = {str(p.relative_to(source)): digest(p) for p in source.rglob('*') if p.is_file()}
(WORK / 'installed-source-hashes.json').write_text(json.dumps(files, indent=2, sort_keys=True) + '\n')
(SLOT / 'qualification-source.json').write_text(json.dumps(receipt, indent=2) + '\n')
subprocess.run(['systemctl', 'stop', *UNITS], check=True)
new = CURRENT.with_name('current-task115-step2-new')
assert not new.exists() and not new.is_symlink()
new.symlink_to(SLOT)
new.replace(CURRENT)
receipt['stage'] = 'candidate_pointer_installed'
(WORK / 'stage-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
subprocess.run(['systemctl', 'start', UNITS[3], UNITS[0]], check=True)
assert subprocess.run(['systemctl', 'is-active', '--quiet', UNITS[0], UNITS[3]]).returncode == 0
receipt['stage'] = 'candidate_services_active'
(WORK / 'stage-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt))
