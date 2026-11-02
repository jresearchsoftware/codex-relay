"""Real root/Linux stage boundaries and locked Cargo fixture build, without hosts."""
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest

import yaml


ANSIBLE = Path(__file__).resolve().parents[1]
ROLE = ANSIBLE / 'roles/relay_artifacts'
spec = importlib.util.spec_from_file_location('intent_artifact_stage', ROLE / 'files/relay-intent-stage.py')
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)
OP = '12345678-1234-1234-1234-123456789abc'
TASKS = yaml.safe_load((ROLE / 'tasks/main.yml').read_text())
NATIVE = sys.platform == 'linux' and os.geteuid() == 0 and shutil.which('git')


@unittest.skipUnless(NATIVE, 'root Linux disposable filesystem and Git required')
class IntentArtifactStageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='relay-artifact-stage-', dir='/run')
        self.addCleanup(self.temporary.cleanup)
        self.parent = Path(self.temporary.name)
        self.root = self.parent / ('.stage-' + OP)
        self.root.mkdir(mode=0o700)
        self.repository = self.parent / 'git'
        self.repository.mkdir()
        files = {
            'reviewer/Cargo.toml': '[package]\nname="reviewer-mcp-http"\nversion="0.1.0"\nedition="2021"\n',
            'reviewer/Cargo.lock': 'version = 4\n\n[[package]]\nname = "reviewer-mcp-http"\nversion = "0.1.0"\n',
            'reviewer/src/main.rs': 'fn main(){let _=include_str!("../../contracts/src/github-authority-v1.json");'
                                    'let _=include_str!("../../contracts/src/github-authority-v4.json");'
                                    'println!("Usage: isolated-reviewer [OPTIONS]");}\n',
            'contracts/src/github-authority-v1.json': '{"schema_version":"3.0"}\n',
            'contracts/src/github-authority-v4.json': '{"schema_version":"4.0"}\n',
            'controller/src/codex-dispatch-entrypoint.mjs': 'export const status="ready";\n',
            'controller/src/diagnostic-store-entrypoint.mjs': 'export const status="ready";\n',
            'source-proof.txt': 'Exact frozen fixture bytes.\n',
            'executable.sh': '#!/bin/sh\nexit 0\n',
        }
        for name, text in files.items():
            path = self.repository / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        (self.repository / 'executable.sh').chmod(0o755)
        self.git('init', '-q')
        self.git('add', '.')
        tree = self.git('write-tree')
        self.revision = self.git('-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid',
                                 'commit-tree', tree, '-m', 'isolated archive fixture')
        self.archive = self.root / 'source.tar'
        self.git('archive', '--format=tar', '--output=' + str(self.archive), self.revision)
        self.archive.chmod(0o600)
        self.identity = {key: 'a' * 64 for key in stage.IDENTITY_KEYS}
        self.identity.update(revision=self.revision, tree=tree)
        self.expected = {'operationId': OP, 'sourceIdentity': self.identity}
        self.old = self.parent / 'old-release'
        self.old.mkdir()
        (self.old / 'available').write_text('unchanged old installation')
        (self.parent / 'current').symlink_to(self.old)

    def git(self, *arguments):
        result = subprocess.run(['git', *arguments], cwd=self.repository,
            env={**os.environ, 'GIT_CONFIG_NOSYSTEM': '1'}, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def prepare(self, private_toolchain=False):
        acquisition = stage.run('extract', self.root, self.expected, self.archive)
        release = self.root / 'release'
        binary = release / 'bin/reviewer-mcp-http'
        binary.parent.mkdir(mode=0o751)
        shutil.copyfile('/usr/bin/true', binary)
        binary.chmod(0o750)
        for name, target in stage.BIN_LINKS.items():
            (release / name).symlink_to(target)
        toolchain = {'livePrefix': str(self.parent / 'toolchains/rust'), 'stagedPrefix': '',
                     'version': '1.90.0', 'archiveSha256': 'b' * 64}
        if not private_toolchain:
            Path(toolchain['livePrefix']).mkdir(parents=True)
        if private_toolchain:
            prefix = self.root / 'rust-toolchain'
            (prefix / 'bin').mkdir(parents=True)
            shutil.copyfile('/usr/bin/true', prefix / 'bin/cargo')
            (prefix / 'bin/cargo').chmod(0o755)
            toolchain['stagedPrefix'] = str(prefix)
        metadata = {**self.expected, 'sourceAcquisition': acquisition,
            'reviewer': {'binarySha256': stage.hash_bytes(binary.read_bytes()), 'cargoVersion': 'cargo 1.90.0 fixture',
                         'artifactProvenance': 'verified-reuse', 'reuseSourceRelease': str(self.old),
                         'reuseSourceBinarySha256': stage.hash_bytes(binary.read_bytes()),
                         'buildContractSha256': 'c' * 64, 'previousRevision': 'none'},
            'toolchain': toolchain, 'packages': {'runner': {'treeSha256': 'd' * 64}, 'codex': {'treeSha256': 'e' * 64}}}
        receipt = stage.run('seal', self.root, metadata)
        return receipt

    def assert_old_available(self):
        self.assertEqual((self.parent / 'current').resolve(), self.old)
        self.assertEqual((self.old / 'available').read_text(), 'unchanged old installation')
        self.assertFalse((self.parent / 'admission-v1.json').exists())
        self.assertFalse((self.parent / 'operation.json').exists())

    def test_exact_git_archive_and_modes_are_proved_before_private_materialization(self):
        previous = os.umask(0o077)
        try:
            report = stage.run('extract', self.root, self.expected, self.archive)
        finally:
            os.umask(previous)
        source = self.root / 'release/reviewed-source'
        self.assertEqual(report['sourceGitTree'], self.identity['tree'])
        self.assertEqual(report['sourceArchiveSha256'], hashlib.sha256(self.archive.read_bytes()).hexdigest())
        self.assertEqual((source / 'source-proof.txt').read_bytes(), (self.repository / 'source-proof.txt').read_bytes())
        self.assertEqual(stat.S_IMODE((source / 'executable.sh').stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE((source / 'reviewer/src').stat().st_mode), 0o755)
        self.assert_old_available()

    def test_wrong_full_tree_and_revision_stop_before_source_publication(self):
        for field in ('tree', 'revision'):
            bad = deepcopy(self.expected)
            bad['sourceIdentity'][field] = 'f' * 40
            with self.assertRaisesRegex(ValueError, 'INTENT_STAGE_(SOURCE_TREE|ARCHIVE_REVISION)_CHANGED'):
                stage.run('extract', self.root, bad, self.archive)
            self.assertFalse((self.root / 'release').exists())
            self.assert_old_available()

    def test_source_only_materialization_can_be_reverified_without_rewriting_frozen_bytes(self):
        first = stage.run('extract', self.root, self.expected, self.archive)
        source = self.root / 'release/reviewed-source/source-proof.txt'
        inode = source.stat().st_ino
        self.assertEqual(stage.run('extract', self.root, self.expected, self.archive), first)
        self.assertEqual(source.stat().st_ino, inode)
        source.write_text('drift')
        with self.assertRaisesRegex(ValueError, 'INTENT_STAGE_EXISTING_SOURCE_CHANGED'):
            stage.run('extract', self.root, self.expected, self.archive)
        self.assert_old_available()

    def test_alias_traversal_and_special_archive_members_are_rejected_without_active_effects(self):
        for name, kind in [('../outside', tarfile.REGTYPE), ('/absolute', tarfile.REGTYPE),
                           ('alias', tarfile.SYMTYPE), ('device', tarfile.CHRTYPE)]:
            with self.subTest(name=name):
                raw = io.BytesIO()
                with tarfile.open(fileobj=raw, mode='w', format=tarfile.PAX_FORMAT,
                                  pax_headers={'comment': self.revision}) as archive:
                    member = tarfile.TarInfo(name)
                    member.type = kind
                    archive.addfile(member)
                self.archive.write_bytes(raw.getvalue())
                with self.assertRaisesRegex(ValueError, 'INTENT_STAGE_ARCHIVE_(PATH|TYPE)_INVALID'):
                    stage.run('extract', self.root, self.expected, self.archive)
                self.assertFalse((self.root / 'release').exists())
                self.assert_old_available()

    def test_seal_verify_and_live_consume_preserve_old_pointer_and_relocate_internal_links(self):
        receipt = self.prepare()
        self.assertEqual(stage.run('verify', self.root, self.expected), receipt)
        self.assertEqual(stat.S_IMODE((self.root / 'receipt.json').stat().st_mode), 0o600)
        self.assert_old_available()
        destination = self.parent / self.revision
        stage.run('consume', self.root, self.expected, destination)
        self.assertEqual((destination / 'reviewed-source/source-proof.txt').read_text(), 'Exact frozen fixture bytes.\n')
        self.assertEqual((destination / 'bin/relay-codex-dispatch.mjs').resolve(),
                         destination / 'reviewed-source/controller/src/codex-dispatch-entrypoint.mjs')
        self.assertEqual((destination / 'bin/reviewer-mcp-http').read_bytes(), Path('/usr/bin/true').read_bytes())
        self.assert_old_available()

    def test_changed_bytes_modes_unknown_aliases_and_hardlinks_fail_before_consume(self):
        self.prepare()
        source = self.root / 'release/reviewed-source/source-proof.txt'
        original = source.read_bytes()
        source.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'INTENT_STAGE_PAYLOAD_CHANGED'):
            stage.run('consume', self.root, self.expected, self.parent / self.revision)
        source.write_bytes(original)
        source.chmod(0o666)
        with self.assertRaisesRegex(ValueError, 'INTENT_STAGE_(PAYLOAD|PARENT)_UNSAFE'):
            stage.run('verify', self.root, self.expected)
        source.chmod(0o644)
        alias = source.with_name('new-alias')
        alias.symlink_to('source-proof.txt')
        with self.assertRaisesRegex(ValueError, 'INTENT_STAGE_LINK_INVALID'):
            stage.run('verify', self.root, self.expected)
        alias.unlink()
        os.link(source, alias)
        with self.assertRaisesRegex(ValueError, 'INTENT_STAGE_FILE_UNSAFE'):
            stage.run('verify', self.root, self.expected)
        self.assertFalse((self.parent / self.revision).exists())
        self.assert_old_available()

    def test_complete_destination_plan_rejects_late_collisions_before_copying_any_file(self):
        self.prepare()
        destination = self.parent / self.revision
        stage.run('consume', self.root, self.expected, destination)
        existing = destination / 'reviewed-source/source-proof.txt'
        existing.write_text('retain until the whole plan is proved')
        original = existing.read_bytes()
        late = destination / 'zz-retained'
        late.mkdir()
        foreign = late / 'late-alias'
        foreign.symlink_to('/etc/passwd')
        with self.assertRaisesRegex(ValueError, 'INTENT_STAGE_DESTINATION_LINK_INVALID'):
            stage.run('check-destination', self.root, self.expected, destination)
        with self.assertRaisesRegex(ValueError, 'INTENT_STAGE_DESTINATION_LINK_INVALID'):
            stage.run('consume', self.root, self.expected, destination)
        self.assertEqual(existing.read_bytes(), original)
        foreign.unlink()
        unsafe = late / 'writable'
        unsafe.write_text('retained')
        unsafe.chmod(0o666)
        with self.assertRaisesRegex(ValueError, 'INTENT_STAGE_DESTINATION_UNSAFE'):
            stage.run('check-destination', self.root, self.expected, destination)
        unsafe.chmod(0o644)
        unsafe.unlink()
        os.link(existing, unsafe)
        with self.assertRaisesRegex(ValueError, 'INTENT_STAGE_DESTINATION_UNSAFE'):
            stage.run('consume', self.root, self.expected, destination)
        self.assertEqual(existing.read_bytes(), original)
        unsafe.unlink()
        existing.unlink()
        existing.mkdir()
        with self.assertRaisesRegex(ValueError, 'INTENT_STAGE_DESTINATION_TYPE_CHANGED'):
            stage.run('check-destination', self.root, self.expected, destination)
        self.assert_old_available()

    def test_same_revision_destination_preserves_safe_extras_and_historical_absolute_product_alias(self):
        self.prepare()
        destination = self.parent / self.revision
        stage.run('consume', self.root, self.expected, destination)
        alias = destination / 'bin/relay-codex-dispatch.mjs'
        alias.unlink()
        alias.symlink_to(destination / 'reviewed-source/controller/src/codex-dispatch-entrypoint.mjs')
        extra = destination / 'reviewer-target/retained-output'
        extra.parent.mkdir()
        extra.write_text('ordinary safe prior build output')
        os.link(extra, extra.with_name('retained-cargo-dependency'))
        before = extra.stat().st_ino
        plan = stage.run('check-destination', self.root, self.expected, destination)
        self.assertEqual(plan['status'], 'DESTINATION_READY')
        self.assertGreater(plan['existingEntries'], 0)
        stage.run('consume', self.root, self.expected, destination)
        self.assertEqual(extra.read_text(), 'ordinary safe prior build output')
        self.assertEqual(extra.stat().st_ino, before)
        self.assertFalse(os.path.isabs(os.readlink(alias)))
        self.assert_old_available()

    def test_private_toolchain_copies_only_to_the_frozen_missing_destination(self):
        receipt = self.prepare(private_toolchain=True)
        target = Path(receipt['toolchain']['livePrefix'])
        expected = {**self.expected, 'expectedToolchainPrefix': str(target)}
        self.assertEqual(stage.run('check-destination', self.root, self.expected, self.parent / self.revision)['status'],
                         'DESTINATION_READY')
        target.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, 'INTENT_STAGE_TOOLCHAIN_DESTINATION_CHANGED'):
            stage.run('check-destination', self.root, self.expected, self.parent / self.revision)
        target.rmdir()
        stage.run('consume-toolchain', self.root, expected)
        self.assertEqual((target / 'bin/cargo').read_bytes(), Path('/usr/bin/true').read_bytes())
        before = (target / 'bin/cargo').stat().st_ino
        with self.assertRaisesRegex(ValueError, 'INTENT_STAGE_TOOLCHAIN_DESTINATION_CHANGED'):
            stage.run('consume-toolchain', self.root, expected)
        self.assertEqual((target / 'bin/cargo').stat().st_ino, before)
        self.assert_old_available()

    def test_existing_toolchain_parents_are_read_only_and_reject_writable_substitution(self):
        prefix = self.parent / 'compiler-parent/rust'
        (prefix / 'bin').mkdir(parents=True)
        expected = {**self.expected, 'prefix': str(prefix)}
        self.assertEqual(stage.run('check-toolchain', self.root, expected)['status'],
                         'READ_ONLY_TOOLCHAIN_BOUNDARY_READY')
        prefix.parent.chmod(0o777)
        with self.assertRaisesRegex(ValueError, 'INTENT_STAGE_PARENT_UNSAFE'):
            stage.run('check-toolchain', self.root, expected)
        prefix.parent.chmod(0o755)
        self.assert_old_available()

    def test_same_revision_stage_is_separate_and_does_not_overwrite_live_bytes(self):
        destination = self.parent / self.revision
        destination.mkdir()
        (destination / 'original').write_bytes(b'old current release')
        self.prepare()
        self.assertEqual((destination / 'original').read_bytes(), b'old current release')
        self.assertFalse((destination / 'bin').exists())
        self.assert_old_available()

    def test_real_locked_cargo_uses_the_exact_staged_schema_closure(self):
        cargo = os.environ.get('RELAY_TEST_CARGO') or shutil.which('cargo')
        if not cargo or not shutil.which('ansible-playbook'):
            self.skipTest('native Cargo and Ansible required for the real locked-build fixture')
        stage.run('extract', self.root, self.expected, self.archive)
        release = self.root / 'release'
        (release / 'reviewer-source/src').mkdir(parents=True)
        names = ['Stage reviewed Rust Reviewer source and lockfile', 'Stage reviewed Rust Reviewer implementation',
                 'Create protected shared Reviewer schema build inputs',
                 'Stage the exact shared GitHub authority schemas for the Reviewer build',
                 'Build the locked reviewed Rust Reviewer release artifact']
        tasks = [deepcopy(next(task for task in TASKS if task['name'] == name)) for name in names]
        tasks[-1]['ansible.builtin.command']['argv'][0] = str(cargo)
        variables = {'relay_release_path': str(release), 'relay_group': 'root',
            'relay_rust_toolchain_cargo_home': str(self.root / 'cargo-home'),
            'relay_rust_toolchain_root': str(Path(cargo).parent.parent),
            'relay_artifact_stage_only': True, 'relay_intent_stage_root': str(self.root),
            'relay_artifact_consume_staged': False, 'relay_reviewer_reuse_verified': False,
            'ansible_env': {'PATH': str(Path(cargo).parent) + ':/usr/bin:/bin', 'HOME': str(self.root)}}
        play = self.root / 'compile.yml'
        play.write_text(yaml.safe_dump([{'hosts': 'all', 'gather_facts': False, 'vars': variables, 'tasks': tasks}]))
        result = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(play)],
            env={**os.environ, 'ANSIBLE_CONFIG': str(ANSIBLE / 'ansible.cfg'), 'ANSIBLE_NOCOLOR': '1'},
            capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        binary = release / 'reviewer-target/release/reviewer-mcp-http'
        checked = subprocess.run([str(binary), '--help'], capture_output=True, text=True, timeout=10)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertIn('Usage:', checked.stdout)
        # A failed builder remains a private pre-cutover failure, including
        # when an earlier binary exists. Stage mode must invoke Cargo again.
        (release / 'reviewer-source/src/main.rs').write_text('this is not Rust;\n')
        play.write_text(yaml.safe_dump([{'hosts': 'all', 'gather_facts': False,
            'vars': variables, 'tasks': [tasks[-1]]}]))
        failed = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(play)],
            env={**os.environ, 'ANSIBLE_CONFIG': str(ANSIBLE / 'ansible.cfg'), 'ANSIBLE_NOCOLOR': '1'},
            capture_output=True, text=True, timeout=120)
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn('error:', failed.stdout + failed.stderr)
        self.assertFalse((self.root / 'receipt.json').exists())
        self.assert_old_available()

    def test_actual_candidate_import_probe_has_no_entrypoint_execution_or_credentials(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node required for actual candidate import closure')
        source = self.root / 'release/reviewed-source'
        for component in ('consumer', 'controller', 'runtime', 'contracts', 'reviewer'):
            shutil.copytree(ANSIBLE.parents[1] / component, source / component,
                ignore=shutil.ignore_patterns('target', 'node_modules', '__pycache__'))
        consumer = json.loads((ANSIBLE.parents[1] / 'deploy/example.json').read_text())['consumer']
        for name in consumer['paths']:
            consumer['paths'][name] = str(self.root / 'unused' / name)
        config = self.root / 'consumer.json'
        config.write_text(json.dumps(consumer))
        config.chmod(0o600)
        tasks = yaml.safe_load((ROLE / 'tasks/intent-stage.yml').read_text())
        probe = next(task for task in tasks if task['name'].startswith('Execute actual candidate controller'))
        argv = [value.replace('{{ relay_intent_stage_root }}', str(self.root))
                for value in probe['ansible.builtin.command']['argv']]
        argv[0] = node
        result = subprocess.run(argv, env={'PATH': '/usr/bin:/bin', 'HOME': str(self.root),
            'RELAY_CONSUMER_CONFIG': str(config), 'RELAY_REPOSITORY': consumer['repository']},
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'INTENT_STAGE_IMPORTS_READY')
        self.assertEqual(list((self.root / 'unused').glob('*')) if (self.root / 'unused').exists() else [], [])
        self.assert_old_available()

    def test_actual_ansible_consume_uses_sealed_payload_without_cargo_download_or_activation(self):
        if not shutil.which('ansible-playbook'):
            self.skipTest('Ansible required for actual sealed-consumption fixture')
        self.prepare()
        receipt = (self.root / 'receipt.json').read_bytes()
        variables = {'relay_intent_stage_root': str(self.root), 'relay_intent_stage_operation': OP,
            'relay_intent_staged_release': str(self.root / 'release'), 'relay_release_root': str(self.parent),
            'relay_release_path': str(self.parent / self.revision), 'relay_source_identity': self.identity,
            'relay_group': 'root', 'relay_reviewer_group': 'root',
            'relay_rust_toolchain_root': str(self.parent / 'toolchains/rust')}
        play = self.root / 'consume.yml'
        play.write_text(yaml.safe_dump([{'hosts': 'all', 'gather_facts': False, 'vars': variables,
            'tasks': [{'name': 'Consume qualified bytes', 'ansible.builtin.include_role': {
                'name': str(ROLE), 'tasks_from': 'intent-consume.yml'}}]}]))
        result = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(play)],
            env={**os.environ, 'ANSIBLE_CONFIG': str(ANSIBLE / 'ansible.cfg'), 'ANSIBLE_NOCOLOR': '1'},
            capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.root / 'receipt.json').read_bytes(), receipt)
        self.assertEqual((self.parent / self.revision / 'bin/reviewer-mcp-http').read_bytes(),
                         Path('/usr/bin/true').read_bytes())
        self.assert_old_available()

    def test_actual_complete_artifact_role_consumes_without_facts_from_skipped_build_tasks(self):
        if not shutil.which('ansible-playbook'):
            self.skipTest('Ansible required for complete artifact role consumption')
        self.prepare()
        isolated_role = self.root / 'roles/relay_artifacts'
        shutil.copytree(ROLE, isolated_role)
        # The role's real tasks and templates run unchanged. Only the final
        # service handler is a fixture no-op; no host unit is in this sandbox.
        (isolated_role / 'handlers/main.yml').write_text(yaml.safe_dump([{
            'name': 'Try-restart Reviewer after release transition',
            'ansible.builtin.debug': {'msg': 'isolated artifact fixture notification'}}]))
        variables = yaml.safe_load((ANSIBLE / 'group_vars/all.yml').read_text())
        variables.update(relay_intent_stage_root=str(self.root), relay_intent_stage_operation=OP,
            relay_intent_staged_release=str(self.root / 'release'), relay_release_root=str(self.parent),
            relay_install_root=str(self.parent), relay_source_identity=self.identity,
            relay_group='root', relay_reviewer_group='root', relay_runner_group='root',
            relay_rust_toolchain_root=str(self.parent / 'toolchains/rust'),
            relay_requested_revision=self.revision, relay_consumer_revision='d' * 40)
        self.assertNotIn('relay_reviewer_reuse_verified', variables)
        play = self.root / 'complete-consume.yml'
        play.write_text(yaml.safe_dump([{'hosts': 'all', 'gather_facts': False, 'vars': variables,
            'tasks': [{'name': 'Consume through the entire actual artifact role', 'ansible.builtin.include_role': {
                'name': str(isolated_role)}}]}]))
        result = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(play)],
            env={**os.environ, 'ANSIBLE_CONFIG': str(ANSIBLE / 'ansible.cfg'), 'ANSIBLE_NOCOLOR': '1'},
            capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        destination = self.parent / self.revision
        manifest = json.loads((destination / 'artifact-manifest.json').read_text())
        self.assertEqual(manifest['commit'], self.revision)
        self.assertEqual((self.parent / 'current').resolve(), destination)
        self.assertEqual((destination / 'bin/reviewer-mcp-http').read_bytes(), Path('/usr/bin/true').read_bytes())
        self.assertEqual((self.old / 'available').read_text(), 'unchanged old installation')

    def test_reinstall_sibling_stage_survives_runtime_archival_and_actual_ansible_consume(self):
        if not shutil.which('ansible-playbook'):
            self.skipTest('Ansible required for actual reinstall sealed-consumption fixture')
        install = self.parent / 'replacement'
        old = install / 'releases' / ('f' * 40)
        old.mkdir(parents=True)
        (old / 'available').write_text('retained installation bytes')
        (install / 'current').symlink_to('releases/' + old.name)
        sibling = self.parent / '.replacement-staging'
        sibling.mkdir(mode=0o700)
        replacement = sibling / self.root.name
        self.root.rename(replacement)
        self.root, self.archive = replacement, replacement / 'source.tar'
        self.prepare()
        receipt = (self.root / 'receipt.json').read_bytes()
        source = self.root / 'release/reviewed-source/source-proof.txt'
        source_inode = source.stat().st_ino
        expected = {**self.expected, 'reinstall': True, 'releaseRoot': str(install / 'releases')}
        with self.assertRaisesRegex(ValueError, 'INTENT_STAGE_DESTINATION_INVALID'):
            stage.run('consume', self.root, expected, self.parent / 'other/releases' / self.revision)
        archive = self.parent / 'retirement-archive'
        archive.mkdir(mode=0o700)
        install.rename(archive / 'runtime')
        (install / 'releases').mkdir(parents=True)
        variables = {'relay_intent_stage_root': str(self.root), 'relay_intent_stage_operation': OP,
            'relay_intent_stage_reinstall': True, 'relay_intent_staged_release': str(self.root / 'release'),
            'relay_install_root': str(install), 'relay_release_root': str(install / 'releases'),
            'relay_release_path': str(install / 'releases' / self.revision), 'relay_source_identity': self.identity,
            'relay_group': 'root', 'relay_reviewer_group': 'root',
            'relay_rust_toolchain_root': str(self.parent / 'toolchains/rust')}
        play = self.root / 'consume-reinstall.yml'
        play.write_text(yaml.safe_dump([{'hosts': 'all', 'gather_facts': False, 'vars': variables,
            'tasks': [{'name': 'Consume surviving qualified bytes', 'ansible.builtin.include_role': {
                'name': str(ROLE), 'tasks_from': 'intent-consume.yml'}}]}]))
        result = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(play)],
            env={**os.environ, 'ANSIBLE_CONFIG': str(ANSIBLE / 'ansible.cfg'), 'ANSIBLE_NOCOLOR': '1'},
            capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.root / 'receipt.json').read_bytes(), receipt)
        self.assertEqual(source.stat().st_ino, source_inode)
        self.assertEqual((install / 'releases' / self.revision / 'bin/reviewer-mcp-http').read_bytes(),
                         Path('/usr/bin/true').read_bytes())
        self.assertEqual((archive / 'runtime/current/available').read_text(), 'retained installation bytes')
        self.assertFalse((install / 'current').exists())
        self.assert_old_available()

    def test_complete_artifact_stage_runs_the_real_builder_and_imports_without_live_writes(self):
        cargo = os.environ.get('RELAY_TEST_CARGO') or shutil.which('cargo')
        if not cargo or not shutil.which('ansible-playbook'):
            self.skipTest('native Cargo and Ansible required for complete artifact stage')
        product = ANSIBLE.parents[1]
        for component in ('consumer', 'controller', 'runtime', 'contracts'):
            shutil.copytree(product / component, self.repository / component, dirs_exist_ok=True,
                ignore=shutil.ignore_patterns('target', 'node_modules', '__pycache__'))
        shutil.copyfile(product / 'reviewer/src/executable-cr-v2.json',
                        self.repository / 'reviewer/src/executable-cr-v2.json')
        self.git('add', '.')
        tree = self.git('write-tree')
        revision = self.git('-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid',
                            'commit-tree', tree, '-m', 'complete isolated source fixture')
        self.git('archive', '--format=tar', '--output=' + str(self.archive), revision)
        self.identity.update(revision=revision, tree=tree)
        install = self.parent / 'prepared-reinstall'
        (install / 'releases').mkdir(parents=True)
        sibling = self.parent / '.prepared-reinstall-staging'
        sibling.mkdir(mode=0o700)
        replacement = sibling / self.root.name
        self.root.rename(replacement)
        self.root, self.archive = replacement, replacement / 'source.tar'
        prefix = self.parent / 'existing-rust'
        (prefix / 'bin').mkdir(parents=True)
        for name in ('cargo', 'rustc', 'rustfmt'):
            wrapper = prefix / 'bin' / name
            wrapper.write_text('#!/bin/sh\nexec ' + str(Path(cargo).with_name(name)) + ' "$@"\n')
            wrapper.chmod(0o755)
        version = subprocess.check_output([cargo, '--version'], text=True).split()[1]
        config_spec = importlib.util.spec_from_file_location('stage_compiled_config', product / 'deploy/config.py')
        config_module = importlib.util.module_from_spec(config_spec)
        config_spec.loader.exec_module(config_module)
        config = config_module.load(product / 'deploy/example.json', product)
        variables = config_module.compile_inputs(config)
        variables.update(relay_install_root=str(install), relay_release_root=str(install / 'releases'),
            relay_state_root=str(self.parent / 'state'), relay_config_root=str(self.parent / 'active-config'),
            relay_intent_stage_root=str(self.root), relay_intent_stage_operation=OP,
            relay_intent_stage_reinstall=True,
            relay_source_archive=str(self.archive), relay_source_identity=self.identity,
            relay_rust_toolchain_root=str(prefix), relay_rust_toolchain_version=version,
            relay_requested_revision=revision, relay_consumer_revision='d' * 40,
            relay_installed_deployment_config=json.dumps(config),
            relay_installed_deployment_config_sha256=hashlib.sha256(json.dumps(config).encode()).hexdigest())
        variables = {**yaml.safe_load((ANSIBLE / 'group_vars/all.yml').read_text()), **variables}
        play = self.root / 'complete-stage.yml'
        # Resolve playbook-relative owning sources without substituting tasks.
        (self.root / 'roles').symlink_to(ANSIBLE / 'roles')
        for source_only in (True, False):
            variables['relay_intent_stage_source_only'] = source_only
            play.write_text(yaml.safe_dump([{'hosts': 'all', 'gather_facts': True, 'vars': variables,
                'tasks': [{'name': 'Run the private artifact stage', 'ansible.builtin.include_tasks':
                           str(ROLE / 'tasks/intent-stage.yml')}]}]))
            result = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(play)],
                env={**os.environ, 'ANSIBLE_CONFIG': str(ANSIBLE / 'ansible.cfg'), 'ANSIBLE_NOCOLOR': '1'},
                capture_output=True, text=True, timeout=180)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            if source_only:
                self.assertTrue((self.root / 'consumer.json').is_file())
                self.assertFalse((self.root / 'release/bin').exists())
                self.assertFalse((self.root / 'receipt.json').exists())
                self.assert_old_available()
        binary = self.root / 'release/bin/reviewer-mcp-http'
        self.assertTrue(binary.is_file())
        self.assertFalse((self.root / 'release/reviewer-target').exists())
        self.assertEqual(json.loads((self.root / 'release/artifact-manifest.json').read_text())['commit'], revision)
        self.assertFalse((self.parent / 'active-config').exists())
        self.assertFalse((install / 'releases' / revision).exists())
        self.assert_old_available()


class IntentArtifactCompositionTests(unittest.TestCase):
    def test_private_stage_builds_without_current_config_or_activation_tasks(self):
        play = yaml.safe_load((ANSIBLE / 'relay-intent-stage.yml').read_text())[0]
        paths = [task.get('ansible.builtin.include_tasks') or
                 'roles/' + task['ansible.builtin.include_role']['name'] + '/tasks/' +
                 task['ansible.builtin.include_role']['tasks_from'] for task in play['tasks']]
        self.assertEqual(paths[-1], 'roles/relay_artifacts/tasks/intent-stage-seal.yml')
        self.assertIn('roles/relay_runner/tasks/intent-stage-package.yml', paths)
        self.assertIn('roles/relay_codex_runtime/tasks/intent-stage-package.yml', paths)
        for name in ['Activate only the reviewed release binding',
                     'Reconcile the protected deployment snapshot before its manifest']:
            task = next(task for task in TASKS if task['name'] == name)
            self.assertIn('relay_artifact_stage_only', str(task['when']))
        source = next(task for task in TASKS if task['name'] == 'Stage Relay source through its internal Git transport')
        self.assertIn('relay_artifact_stage_only', source['when'])
        build = next(task for task in TASKS if task['name'] == 'Build the locked reviewed Rust Reviewer release artifact')
        self.assertIn('--locked', build['ansible.builtin.command']['argv'])
        self.assertIn('not (relay_artifact_consume_staged | default(false) | bool)', build['when'])
