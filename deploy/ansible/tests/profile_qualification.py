#!/usr/bin/env python3
"""Bounded qualification evidence from existing logs and temporary local state.

No production invocation. Timing is an explicitly local clear-boundary sample,
not an extrapolation to SSH/production wall time. Run as root for real metadata.
"""
import argparse
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import tempfile
import time

import yaml

ROOT = Path(__file__).resolve().parents[1]


def profile(baseline, log_root, head):
    for phase in ['check', 'apply', 'post-check', 'diagnose']:
        path = log_root / f'production-{head}-{phase}.log'
        if not path.exists():
            print(json.dumps({'phase': phase, 'log': 'UNAVAILABLE'}))
            continue
        text = path.read_text()
        tasks = re.findall(r'^TASK \[(.+?)\]', text, re.M)
        print(json.dumps({'phase': phase, 'log': path.name, 'task_boundaries': len(tasks),
            'fact_gathers': tasks.count('Gathering Facts'),
            'identity_resolutions': sum('Resolve the reviewed release commit on the Ansible controller' in t for t in tasks),
            'final_validation': any('Require the final production reconciliation contract' in t for t in tasks),
            'passed': bool(re.search(r'unreachable=0\s+failed=0', text)),
            'wall_seconds': 'UNAVAILABLE: log has no task timestamps'}))
    repo = ROOT.parents[1]
    old = subprocess.check_output(['git', '-c', f'safe.directory={repo}', '-C', str(repo), 'show', f'{baseline}:deploy/ansible/tasks/production-operation-state-clear.yml'], text=True)
    new = (ROOT / 'tasks/production-operation-state-clear.yml').read_text()
    samples = {'old': [], 'new': []}
    with tempfile.TemporaryDirectory(prefix='relay-clear-profile-') as directory:
        root = Path(directory)
        for iteration in range(3):
            for label, text in [('old', old), ('new', new)]:
                record = root / 'operation.json'
                record.write_text(json.dumps({'schemaVersion': '1', 'state': 'RECOVERY_REQUIRED', 'phase': 'apply', 'target_head': baseline}))
                record.chmod(0o600)
                variables = {'relay_production_operation_record_path': str(record),
                    'relay_production_operation_lock_path': str(root / 'operation.lock'),
                    'relay_production_operation_schema_version': '1',
                    'relay_production_operation_clear_phase': 'apply', 'relay_production_operation_clear_head': baseline}
                play = root / 'profile.yml'
                play.write_text(yaml.safe_dump([{'hosts': 'localhost', 'gather_facts': False, 'vars': variables, 'tasks': yaml.safe_load(text)}]))
                start = time.monotonic()
                result = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(play)], capture_output=True, text=True)
                elapsed = time.monotonic() - start
                assert result.returncode == 0, result.stdout + result.stderr
                assert not record.exists()
                samples[label].append(round(elapsed, 3))
        medians = {k: statistics.median(v) for k, v in samples.items()}
        print(json.dumps({'sample': 'real localhost locked clear; three alternating runs', 'seconds': samples,
            'median_seconds': medians, 'reduction_percent': round(100 * (1 - medians['new'] / medians['old']), 1),
            'old_tasks': len(yaml.safe_load(old)), 'new_tasks': len(yaml.safe_load(new))}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', required=True)
    parser.add_argument('--log-root', type=Path, required=True)
    parser.add_argument('--head', required=True)
    args = parser.parse_args()
    if os.geteuid() != 0 or not re.fullmatch('[a-f0-9]{40}', args.baseline) or not re.fullmatch('[a-f0-9]{12}', args.head):
        parser.error('root and exact baseline SHA / 12-character log head are required')
    profile(args.baseline, args.log_root, args.head)
