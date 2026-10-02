"""Real local projection and drift checks; no GitHub or installed host access."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
from config import InvalidConfig, validate
import workflow_projection as projection
from test_consumer_workflows import HEAD, self_config


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='relay-projection-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.config = json.loads((ROOT / 'deploy/example.json').read_text())
        self.rendered = projection.render(self.config, HEAD, ROOT)

    def project(self, revision=HEAD, **kwargs):
        return projection.project(self.config, revision, ROOT, self.root, **kwargs)

    def verify(self, revision=HEAD):
        return projection.verify(self.config, revision, ROOT, self.root)

    def test_external_projection_is_deterministic_and_preserves_consumer_files(self):
        workflows = self.root / '.github/workflows'
        workflows.mkdir(parents=True)
        checks = workflows / 'relay-exact-head-validation.yml'
        checks.write_text('consumer-owned checks\n')
        validate(self.config, ROOT)
        first = self.project()
        self.assertEqual(self.verify(), first)
        contents = {str(path.relative_to(self.root)): path.read_bytes()
                    for path in self.root.rglob('*') if path.is_file()}
        self.assertEqual(len(first['files']), 2)
        self.assertEqual(first['relayRevision'], HEAD)
        self.assertEqual(first['consumerRepository'], 'example-org/sample-project')
        self.assertEqual(self.project(), first)
        self.assertEqual(contents, {str(path.relative_to(self.root)): path.read_bytes()
                                   for path in self.root.rglob('*') if path.is_file()})
        self.assertEqual(checks.read_text(), 'consumer-owned checks\n')
        for path, raw in self.rendered.items():
            self.assertEqual((self.root / path).read_bytes(), raw)
            value = yaml.safe_load(raw)
            job, = value['jobs'].values()
            step, = job['steps']
            self.assertIn("github.repository == 'example-org/sample-project'", job['if'])
            self.assertIn("github.actor == 'example-owner'", job['if'])
            self.assertEqual(job['runs-on'], ['self-hosted', 'Linux', 'X64', 'relay'])
            self.assertEqual(step['env']['EXPECTED_RELAY_HEAD'], HEAD)
            self.assertEqual(os.stat(self.root / path).st_mode & 0o777, 0o644)

    def test_general_runner_group_and_non_main_base_are_projected(self):
        self.config['consumer']['baseBranch'] = 'stable/release'
        self.config['environment']['generalRunner'].update(scope='organization', group='general-only')
        validate(self.config, ROOT)
        rendered = projection.render(self.config, HEAD, ROOT)
        routing = yaml.safe_load(rendered[self.config['consumer']['routingWorkflow']])
        self.assertEqual(routing[True]['pull_request_target']['branches'], ['stable/release'])
        self.assertEqual(routing['jobs']['route']['runs-on'], {
            'group': 'general-only', 'labels': ['self-hosted', 'Linux', 'X64', 'relay']})
        self.assertIn("github.ref == 'refs/heads/stable/release'", routing['jobs']['route']['if'])

    def test_changed_exact_target_requires_reprojection_but_retains_old_bytes_until_owner_projects(self):
        before = self.project()
        next_head = 'b' * 40
        with self.assertRaisesRegex(InvalidConfig, 'workflow-projection-target-mismatch'):
            self.verify(next_head)
        self.assertEqual(self.verify(), before)
        after = self.project(next_head)
        self.assertEqual(self.verify(next_head), after)
        self.assertNotEqual(before, after)

    def test_target_source_is_recomputed_instead_of_trusting_manifest(self):
        self.project()
        changed = dict(self.rendered)
        path = next(iter(changed))
        changed[path] += b'# unexpected target source change\n'
        with patch.object(projection, 'render', return_value=changed):
            with self.assertRaisesRegex(InvalidConfig, 'workflow-projection-target-mismatch'):
                self.verify()

    def test_unmanaged_or_drifted_workflows_are_never_overwritten(self):
        path = self.root / next(iter(self.rendered))
        path.parent.mkdir(parents=True)
        path.write_text('owner workflow\n')
        with self.assertRaisesRegex(InvalidConfig, 'workflow-unmanaged'):
            self.project()
        self.assertEqual(path.read_text(), 'owner workflow\n')
        path.unlink()
        self.project()
        other = self.root / [value for value in self.rendered if value != str(path.relative_to(self.root))][0]
        previous = other.read_bytes()
        path.write_text('direct edit\n')
        for operation in [self.project, self.verify]:
            with self.assertRaisesRegex(InvalidConfig, 'workflow-drift'):
                operation('b' * 40)
        self.assertEqual(path.read_text(), 'direct edit\n')
        self.assertEqual(other.read_bytes(), previous)

    def test_paths_cannot_be_silently_reassigned_to_another_consumer_or_role(self):
        self.project()
        self.config['consumer']['repository'] = 'other/project'
        with self.assertRaisesRegex(InvalidConfig, 'workflow-consumer-binding'):
            self.project()
        self.config['consumer']['repository'] = 'example-org/sample-project'
        self.config['consumer']['routingWorkflow'] = '.github/workflows/renamed.yml'
        with self.assertRaisesRegex(InvalidConfig, 'workflow-path-migration-required'):
            self.project()

    def test_symlink_and_hardlink_paths_fail_without_modifying_the_target(self):
        outside = self.root / 'outside'
        outside.mkdir()
        (self.root / '.github').symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(InvalidConfig, 'workflow-directory'):
            self.project()
        self.assertEqual(list(outside.iterdir()), [])
        (self.root / '.github').unlink()
        self.project()
        path = self.root / next(iter(self.rendered))
        original = path.read_bytes()
        os.link(path, outside / 'linked.yml')
        with self.assertRaisesRegex(InvalidConfig, 'workflow-regular-file'):
            self.project('b' * 40)
        self.assertEqual(path.read_bytes(), original)
        (outside / 'linked.yml').unlink()
        path.unlink()
        path.symlink_to(outside / 'absent')
        with self.assertRaisesRegex(InvalidConfig, 'workflow-drift'):
            self.project('b' * 40)
        self.assertFalse((outside / 'absent').exists())

    def test_malformed_manifest_and_nonexact_target_fail_closed(self):
        self.project()
        manifest = self.root / projection.MANIFEST
        expected = manifest.read_text()
        manifest.write_text(expected.replace('"schemaVersion": 1', '"schemaVersion": 1, "schemaVersion": 1'))
        with self.assertRaisesRegex(InvalidConfig, 'duplicate-key'):
            self.project()
        manifest.write_text(expected.replace('"schemaVersion": 1', '"schemaVersion": true'))
        with self.assertRaisesRegex(InvalidConfig, 'workflow-manifest-version'):
            self.project()
        manifest.write_text(expected)
        for revision in ['main', '../../candidate', '', 'a' * 39]:
            with self.assertRaisesRegex(InvalidConfig, 'workflow-exact-revision'):
                self.project(revision)

    def test_partial_mutation_is_visible_and_cannot_be_blindly_retried(self):
        self.project()
        write = projection._write
        count = 0

        def fail_second(path, content):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError('synthetic storage interruption')
            return write(path, content)

        with patch.object(projection, '_write', side_effect=fail_second):
            with self.assertRaisesRegex(ValueError, 'WORKFLOW_PROJECTION_INCOMPLETE;written=.github/workflows/'):
                self.project('b' * 40)
        with self.assertRaisesRegex(InvalidConfig, 'workflow-drift'):
            self.project('b' * 40)
        self.assertFalse((self.root / '.github/.relay-workflows.lock').exists())

    def test_edit_between_individual_writes_is_retained_and_reported(self):
        self.project()
        write = projection._write
        paths = list(self.rendered)
        edited = self.root / paths[1]

        def concurrent_edit(path, content):
            write(path, content)
            if path == self.root / paths[0]:
                edited.write_text('concurrent owner edit\n')

        with patch.object(projection, '_write', side_effect=concurrent_edit):
            with self.assertRaisesRegex(ValueError, 'WORKFLOW_PROJECTION_INCOMPLETE'):
                self.project('b' * 40)
        self.assertEqual(edited.read_text(), 'concurrent owner edit\n')

    def test_legacy_adoption_is_explicit_exact_and_scoped(self):
        self.config = self_config()
        legacy = json.loads((ROOT / 'deploy/workflows/legacy.json').read_text())
        for name, digest in legacy['files'].items():
            source = ROOT / 'deploy/tests/fixtures/workflows-48946e7' / Path(name).name
            self.assertEqual(projection.sha256(source.read_bytes()), digest,
                             'Migration fixture must match the supported immutable predecessor')
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        with self.assertRaisesRegex(InvalidConfig, 'workflow-unmanaged'):
            self.project()
        changed = self.root / next(iter(legacy['files']))
        original = changed.read_bytes()
        changed.write_bytes(original + b'# direct edit\n')
        with self.assertRaisesRegex(InvalidConfig, 'workflow-legacy-drift'):
            self.project(adopt_legacy=True)
        changed.write_bytes(original)
        self.config['consumer']['owner'] = 'other-owner'
        with self.assertRaisesRegex(InvalidConfig, 'workflow-legacy-consumer'):
            self.project(adopt_legacy=True)
        self.config['consumer']['owner'] = 'foal'
        projected = self.project(adopt_legacy=True)
        self.assertEqual(self.verify(), projected)
        self.assertEqual(len(projected['files']), 3)
        with self.assertRaisesRegex(InvalidConfig, 'workflow-legacy-already-managed'):
            self.project(adopt_legacy=True)

    def test_projection_lock_blocks_overlapping_local_mutation(self):
        self.project()
        (self.root / '.github/.relay-workflows.lock').mkdir()
        with self.assertRaisesRegex(InvalidConfig, 'workflow-projection-in-progress'):
            self.project('b' * 40)
        self.verify()


if __name__ == '__main__':
    unittest.main()
