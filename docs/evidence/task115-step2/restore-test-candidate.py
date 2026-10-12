import json, os, pathlib, subprocess
WORK = pathlib.Path('/var/lib/codex-relay-test/qualification-step2-01a12efc')
CURRENT = pathlib.Path('/opt/codex-relay-test/current')
receipt = json.loads((WORK / 'stage-receipt.json').read_text())
assert os.getuid() == 0 and str(CURRENT.resolve()) == receipt['candidate_pointer']
units = list(receipt['original_active'])
subprocess.run(['systemctl', 'stop', *units], check=True)
new = CURRENT.with_name('current-task115-step2-restore')
assert not new.exists() and not new.is_symlink()
new.symlink_to(receipt['old_pointer'])
new.replace(CURRENT)
subprocess.run(['systemctl', 'start', *[u for u, active in receipt['original_active'].items() if active]], check=True)
assert str(CURRENT.resolve()) == receipt['old_pointer']
assert all((subprocess.run(['systemctl', 'is-active', '--quiet', u]).returncode == 0) == active for u, active in receipt['original_active'].items())
receipt['stage'] = 'original_pointer_and_service_activity_restored'
(WORK / 'restore-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt))
