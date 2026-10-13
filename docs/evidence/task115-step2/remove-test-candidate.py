"""Remove only this restored, archived disposable TEST candidate and work area."""
import json
import os
import shutil
import subprocess
from pathlib import Path

WORK = Path('/var/lib/codex-relay-test/qualification-step2-01a12efc')
SLOT = Path('/opt/codex-relay-test/qualification-step2-3fff414')
CURRENT = Path('/opt/codex-relay-test/current')
assert os.getuid() == 0 and WORK.resolve() == WORK and SLOT.resolve() == SLOT
restore = json.loads((WORK / 'restore-receipt.json').read_text())
cleanup = json.loads((WORK / 'cleanup-receipt.json').read_text())
assert restore['stage'] == 'original_pointer_and_service_activity_restored'
assert str(CURRENT.resolve()) == restore['old_pointer']
assert len(cleanup['records']) == 6
assert all(not Path(item['path']).exists() for item in cleanup['records'])
assert all((subprocess.run(['systemctl', 'is-active', '--quiet', u]).returncode == 0) == active for u, active in restore['original_active'].items())
for target, parent in [(SLOT, Path('/opt/codex-relay-test')), (WORK, Path('/var/lib/codex-relay-test'))]:
    assert target.parent == parent and target.resolve().is_relative_to(parent)
    assert target != CURRENT.resolve()
    shutil.rmtree(target)
print(json.dumps({'scope': 'isolated TEST', 'temporary_candidate_removed': str(SLOT), 'temporary_work_area_removed': str(WORK), 'restored_pointer': str(CURRENT.resolve()), 'original_service_activity_preserved': True, 'native_history_preserved': True}))
