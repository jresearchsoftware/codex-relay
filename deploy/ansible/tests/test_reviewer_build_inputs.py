"""Actual Reviewer staging and compile-time inputs in an unprivileged fixture.

The fixture substitutes only ownership identities with its current Unix user;
source paths, destinations, modes and copy loops come from the product tasks.
It neither runs the installation role nor contacts a configured environment.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

import yaml


REPO = Path(__file__).resolve().parents[3]
ANSIBLE = REPO / 'deploy/ansible'
TASKS = yaml.safe_load((ANSIBLE / 'roles/relay_artifacts/tasks/main.yml').read_text())
STAGING_NAMES = [
    'Stage reviewed Rust Reviewer source and lockfile',
    'Stage reviewed Rust Reviewer implementation',
    'Create protected shared Reviewer schema build inputs',
    'Stage the exact shared GitHub authority schemas for the Reviewer build',
]
STAGING = [next(task for task in TASKS if task.get('name') == name) for name in STAGING_NAMES]
NATIVE = os.name != 'nt' and shutil.which('ansible-playbook') and shutil.which('rustc')


class ReviewerBuildInputTests(unittest.TestCase):
    def test_shared_schema_staging_preserves_protected_copy_contract(self):
        task = STAGING[-1]
        self.assertEqual(task['loop'], ['github-authority-v1.json', 'github-authority-v4.json'])
        self.assertEqual(task['ansible.builtin.copy'], {
            'src': '{{ relay_release_path }}/reviewed-source/contracts/src/{{ item }}',
            'dest': '{{ relay_release_path }}/contracts/src/{{ item }}',
            'remote_src': True, 'owner': 'root', 'group': '{{ relay_group }}', 'mode': '0640',
        })
        self.assertEqual(task['when'], 'not ansible_check_mode | bool')

    @unittest.skipUnless(NATIVE, 'Native Ansible and Rust required for staged compile-input qualification')
    def test_actual_staging_supplies_compile_inputs_and_missing_v4_fails_compilation(self):
        with tempfile.TemporaryDirectory(prefix='reviewer-staged-inputs-') as directory:
            temporary = Path(directory)
            release = temporary / 'release'
            reviewed = release / 'reviewed-source'
            shutil.copytree(REPO / 'reviewer/src', reviewed / 'reviewer/src')
            for name in ['Cargo.toml', 'Cargo.lock']:
                shutil.copyfile(REPO / 'reviewer' / name, reviewed / 'reviewer' / name)
            schemas = reviewed / 'contracts/src'
            schemas.mkdir(parents=True)
            for path in (REPO / 'contracts/src').glob('github-authority-*.json'):
                shutil.copyfile(path, schemas / path.name)
            staged = release / 'reviewer-source'
            staged.mkdir(mode=0o750)
            tasks = deepcopy(STAGING)
            for task in tasks:
                module = task.get('ansible.builtin.copy', task.get('ansible.builtin.file'))
                module['owner'] = str(os.getuid())
                module['group'] = str(os.getgid())
            playbook = temporary / 'stage.yml'
            playbook.write_text(yaml.safe_dump([{
                'hosts': 'localhost', 'gather_facts': False,
                'vars': {'relay_release_path': str(release), 'relay_group': str(os.getgid()),
                         'ansible_remote_tmp': str(temporary / 'remote-tmp')},
                'tasks': tasks,
            }]))
            result = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(playbook)],
                env={**os.environ, 'ANSIBLE_CONFIG': str(ANSIBLE / 'ansible.cfg'), 'ANSIBLE_NOCOLOR': '1'},
                text=True, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for name in ['github-authority-v1.json', 'github-authority-v4.json']:
                path = release / 'contracts/src' / name
                self.assertEqual(path.read_bytes(), (schemas / name).read_bytes())
                self.assertEqual(path.stat().st_mode & 0o777, 0o640)
                self.assertEqual(json.loads(path.read_text())['schema_version'], '3.0' if '-v1.' in name else '4.0')
            for name in ['Cargo.toml', 'Cargo.lock']:
                self.assertEqual((staged / name).read_bytes(), (REPO / 'reviewer' / name).read_bytes())

            # The compiler resolves the real production include_str! arguments
            # from the same staged src directory used by the Reviewer crate.
            # This catches missing relocated inputs independently of their names
            # in Ansible YAML and also covers the local executable-CR definition.
            includes = []
            for name in ['task_authority.rs', 'executable_cr.rs']:
                source = (staged / 'src' / name).read_text()
                includes.extend(re.findall(r'include_str!\(\s*"([^\"]+)"\s*\)', source))
            self.assertGreaterEqual(len(includes), 3)
            probe = staged / 'src/staged-input-probe.rs'
            probe.write_text('\n'.join(
                f'pub const INPUT_{index}: &str = include_str!({json.dumps(path)});'
                for index, path in enumerate(includes)) + '\n')
            argv = [shutil.which('rustc'), '--edition=2021', '--crate-type=lib',
                    '--crate-name=staged_input_probe', str(probe), '-o', str(temporary / 'probe.rlib')]
            compiled = subprocess.run(argv, text=True, capture_output=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            v4 = release / 'contracts/src/github-authority-v4.json'
            retained = v4.read_bytes()
            v4.unlink()
            missing = subprocess.run(argv, text=True, capture_output=True, timeout=30)
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn('github-authority-v4.json', missing.stderr)
            self.assertIn('No such file or directory', missing.stderr)
            v4.write_bytes(retained)
            v4.chmod(0o640)

            # Optional full staged crate check uses only already cached packages.
            # Explicit opt-in avoids imposing another Cargo build on normal
            # deployment unit suites; no network or runtime service is involved.
            if os.environ.get('RELAY_STAGED_REVIEWER_CARGO_CHECK') == '1':
                cargo = shutil.which('cargo')
                self.assertIsNotNone(cargo)
                checked = subprocess.run([cargo, 'check', '--locked', '--offline',
                    '--manifest-path', str(staged / 'Cargo.toml')],
                    text=True, capture_output=True, timeout=300)
                self.assertEqual(checked.returncode, 0, checked.stderr)


if __name__ == '__main__':
    unittest.main()
