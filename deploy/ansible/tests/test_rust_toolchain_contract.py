"""Shared Rust pin, reconciliation and development access regressions.

These unprivileged tests cover source/task decisions. Real ownership and
executable behavior are qualified by installed_runtime_proof.py in native CI.
"""
from pathlib import Path
import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar
import yaml


ROOT = Path(__file__).resolve().parents[1]
TASKS = yaml.safe_load((ROOT / 'roles/relay_artifacts/tasks/rust-toolchain.yml').read_text())


def task(name):
    return next(item for item in TASKS if item['name'] == name)


class RustToolchainContractTests(unittest.TestCase):
    @unittest.skipUnless(os.name != 'nt' and shutil.which('ansible-playbook'), 'Unix Ansible required for unprivileged check-mode execution')
    def test_check_mode_plans_missing_and_existing_toolchains_without_mutation(self):
        import grp
        with tempfile.TemporaryDirectory(prefix='rust-check-mode-') as directory:
            temporary = Path(directory)
            state = temporary / 'state'
            prefix = state / 'toolchains/rust-fixture'
            values = {**yaml.safe_load((ROOT / 'group_vars/all.yml').read_text()),
                      'ansible_architecture': 'x86_64', 'relay_state_root': str(state),
                      'relay_rust_toolchain_root': str(prefix), 'relay_group': grp.getgrgid(os.getgid()).gr_name,
                      'ansible_remote_tmp': str(temporary / 'remote-tmp')}
            playbook = temporary / 'check.yml'
            playbook.write_text(yaml.safe_dump([{'hosts': 'localhost', 'gather_facts': False, 'vars': values,
                'tasks': [{'ansible.builtin.include_role': {'name': 'relay_artifacts', 'tasks_from': 'rust-toolchain.yml'}}]}]))
            def snapshot():
                return {str(path): (path.stat().st_mode, path.stat().st_uid, path.stat().st_mtime_ns)
                        for path in state.rglob('*')} if state.exists() else None
            for present in [False, True]:
                if present:
                    (prefix / 'bin').mkdir(parents=True)
                    for name in ['cargo', 'rustc', 'rustfmt']:
                        (prefix / 'bin' / name).write_text('must not execute in check mode')
                before = snapshot()
                result = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', '--check', str(playbook)],
                    env={'PATH': '/usr/bin:/bin', 'HOME': str(temporary), 'ANSIBLE_CONFIG': str(ROOT / 'ansible.cfg'),
                         'ANSIBLE_ROLES_PATH': str(ROOT / 'roles'), 'ANSIBLE_NOCOLOR': '1'}, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('RUST_TOOLCHAIN_CHECK_MODE_PLAN', result.stdout)
                self.assertIn(f'install={not present}', result.stdout)
                self.assertEqual(snapshot(), before)

    def test_native_rust_acquisition_verifies_source_checksum_without_inheriting_credentials(self):
        import installed_runtime_proof as proof
        values = yaml.safe_load((ROOT / 'group_vars/all.yml').read_text())
        fixture = b'deterministic archive fixture'
        values['relay_rust_toolchain_archive_sha256'] = hashlib.sha256(fixture).hexdigest()
        with tempfile.TemporaryDirectory(prefix='rust-acquisition-test-') as directory:
            def download(argv, **options):
                self.assertEqual(options['env'], {'PATH': '/usr/bin:/bin', 'HOME': directory})
                self.assertIn('--fail', argv)
                self.assertIn(f'https://static.rust-lang.org/dist/rust-{values["relay_rust_toolchain_version"]}-{values["relay_rust_toolchain_host"]}.tar.xz', argv)
                Path(argv[-1]).write_bytes(fixture)
            with mock.patch.object(proof.yaml, 'safe_load', return_value=values), mock.patch.object(proof, 'run', side_effect=download):
                archive = proof.download_rust_archive(Path(directory))
                self.assertEqual(archive.read_bytes(), fixture)
                values['relay_rust_toolchain_archive_sha256'] = '0' * 64
                with self.assertRaisesRegex(RuntimeError, 'RUST_PROOF_ARCHIVE_CHECKSUM_MISMATCH'):
                    proof.download_rust_archive(Path(directory))

    def test_reviewer_reuse_does_not_skip_toolchain_reconciliation(self):
        artifacts = yaml.safe_load((ROOT / 'roles/relay_artifacts/tasks/main.yml').read_text())
        shared = next(item for item in artifacts if item.get('ansible.builtin.include_tasks') == 'rust-toolchain.yml')
        self.assertNotIn('when', shared)
        for item in TASKS:
            self.assertNotIn('relay_reviewer_reuse_verified', str(item))
        build = next(item for item in artifacts if item['name'] == 'Build the locked reviewed Rust Reviewer release artifact')
        self.assertEqual(build['ansible.builtin.command']['argv'][0], '{{ relay_rust_toolchain_root }}/bin/cargo')
        self.assertEqual(build['environment']['CARGO_HOME'], '{{ relay_rust_toolchain_cargo_home }}')
        self.assertIn('not relay_reviewer_reuse_verified | bool', build['when'])
        reuse = (ROOT / 'roles/relay_artifacts/tasks/verify-reviewer-reuse.yml').read_text()
        self.assertIn('relay_rust_toolchain_archive_sha256', reuse)
        self.assertIn('relay_rust_toolchain_version', reuse)

    def test_only_missing_binaries_trigger_the_existing_pinned_installer(self):
        expression = task('Determine whether the managed Rust toolchain needs installation')['ansible.builtin.set_fact']['relay_rust_toolchain_install_needed']
        for present in [(False, False, False), (True, True, True), (True, True, False), (False, True, True)]:
            variables = {'relay_rust_toolchain_binaries': {'results': [{'stat': {'exists': exists}} for exists in present]}}
            result = Templar(loader=DataLoader(), variables=variables).template(expression)
            self.assertEqual(result, not all(present))
        for name in ['Download the checksum-pinned Rust build toolchain', 'Unpack the checksum-pinned Rust build toolchain',
                     'Install the pinned Rust build toolchain in the relay namespace']:
            self.assertEqual(task(name)['when'], ['not ansible_check_mode | bool', 'relay_rust_toolchain_install_needed | bool'])
        download = task('Download the checksum-pinned Rust build toolchain')['ansible.builtin.get_url']
        self.assertEqual(download['checksum'], 'sha256:{{ relay_rust_toolchain_archive_sha256 }}')
        install = task('Install the pinned Rust build toolchain in the relay namespace')['ansible.builtin.command']
        self.assertIn('--prefix={{ relay_rust_toolchain_root }}', install['argv'])
        # A surviving cargo binary must not suppress repair of a missing rustfmt.
        self.assertNotIn('creates', install)

    def test_access_is_limited_to_the_managed_payload_and_traversal(self):
        namespaces = task('Create relay-owned Rust toolchain namespaces')
        self.assertEqual(namespaces['ansible.builtin.file']['owner'], 'root')
        self.assertEqual(namespaces['loop'], [
            {'path': '{{ relay_state_root }}/toolchains', 'mode': '0751'},
            {'path': '{{ relay_rust_toolchain_unpack_root }}', 'mode': '0750'},
            {'path': '{{ relay_rust_toolchain_cargo_home }}', 'mode': '0750'},
        ])
        access = task('Reconcile read-only development access to the managed Rust payload')['ansible.builtin.file']
        self.assertEqual(access, {'path': '{{ relay_rust_toolchain_root }}', 'state': 'directory', 'owner': 'root',
                                 'group': '{{ relay_group }}', 'mode': 'u=rwX,go=rX', 'recurse': True, 'follow': False})
        runtime = yaml.safe_load((ROOT / 'roles/relay_codex_runtime/tasks/main.yml').read_text())
        probe = next(item for item in runtime if item['name'] == 'Verify managed Rust tools through the Codex Unix identity without credentials')
        self.assertEqual(probe['loop'], ['cargo', 'rustc', 'rustfmt'])
        self.assertEqual(probe['ansible.builtin.command']['argv'],
                         ['/usr/sbin/runuser', '-u', '{{ relay_codex_user }}', '--', '{{ relay_rust_toolchain_root }}/bin/{{ item }}', '--version'])
        for item in runtime:
            if 'ansible.builtin.user' in item:
                self.assertNotIn('relay_group', str(item['ansible.builtin.user'].get('groups', [])))



if __name__ == '__main__':
    unittest.main()
