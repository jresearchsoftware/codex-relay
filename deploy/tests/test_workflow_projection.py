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
        self.assertEqual(first['workflowContract'], 'relay-workflows-v2')
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
            self.assertEqual(step['env']['EXPECTED_WORKFLOW_CONTRACT'], 'relay-workflows-v2')
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

    def test_owner_lifecycle_uses_configured_general_runner_and_fixed_namespace_helper(self):
        self.config = self_config()
        self.config['environment']['generalRunner'].update(scope='organization', group='general-only')
        validate(self.config, ROOT)
        rendered = projection.render(self.config, HEAD, ROOT)
        lifecycle = yaml.safe_load(rendered[projection.PRODUCTION])
        job, = lifecycle['jobs'].values()
        step, = job['steps']
        self.assertEqual(job['runs-on'], {
            'group': 'general-only', 'labels': ['self-hosted', 'Linux', 'X64', 'codex-relay']})
        self.assertIn('/usr/local/sbin/codex-relay-owner-lifecycle', step['run'])
        self.assertIn('test "$RUNNER_NAME" = codex-relay-general-runner', step['run'])
        self.assertEqual(lifecycle[True]['workflow_dispatch']['inputs']['action']['options'],
                         ['apply', 'stop', 'resume'])

    def test_lifecycle_projection_change_requires_consumer_review_before_target_verification(self):
        self.config = self_config()
        with tempfile.TemporaryDirectory(prefix='relay-prior-source-') as source:
            templates = Path(source) / 'deploy/workflows'
            shutil.copytree(ROOT / 'deploy/workflows', templates)
            production = templates / 'production.yml.in'
            production.write_text(production.read_text().replace(
                '/usr/local/sbin/@@NAMESPACE@@-owner-lifecycle',
                '/opt/@@NAMESPACE@@/relay-production-local-apply'))
            previous = projection.project(self.config, HEAD, source, self.root)
            before = {path: (self.root / path).read_bytes() for path in [*previous['files'], projection.MANIFEST]}
            with tempfile.TemporaryDirectory(prefix='relay-lifecycle-proposal-') as output:
                target = 'b' * 40
                proposal = projection.prepare(self.config, target, ROOT, self.root, output)
                self.assertEqual(proposal['state'], 'workflow-review-required')
                self.assertEqual(proposal['revision'], target)
                self.assertEqual(before, {path: (self.root / path).read_bytes() for path in before})
                with self.assertRaisesRegex(InvalidConfig, 'workflow-projection-target-mismatch'):
                    projection.verify(self.config, target, ROOT, self.root)
                projection.verify(self.config, target, ROOT, output)
                # Consumer review/merge supplies the target bytes; projection
                # preparation itself never commits or publishes the proposal.
                shutil.copytree(output, self.root, dirs_exist_ok=True)
                projection.verify(self.config, target, ROOT, self.root)

    def test_product_revision_alone_never_requires_reprojection(self):
        before = self.project()
        contents = {path: (self.root / path).read_bytes() for path in [*before['files'], projection.MANIFEST]}
        next_head = 'b' * 40
        self.assertEqual(self.verify(next_head), before)
        self.assertEqual(self.project(next_head), before)
        self.assertEqual(contents, {path: (self.root / path).read_bytes() for path in contents})
        with tempfile.TemporaryDirectory(prefix='relay-proposal-') as output:
            self.assertEqual(projection.prepare(self.config, next_head, ROOT, self.root, output)['state'], 'ready')
            self.assertEqual(list(Path(output).iterdir()), [])

    def test_content_and_contract_changes_require_review_without_mutating_consumer(self):
        self.project()
        before = {path: (self.root / path).read_bytes() for path in self.rendered}
        for mode in ['content', 'contract']:
            with tempfile.TemporaryDirectory(prefix='relay-source-') as source, tempfile.TemporaryDirectory(prefix='relay-proposal-') as output:
                templates = Path(source) / 'deploy/workflows'
                shutil.copytree(ROOT / 'deploy/workflows', templates)
                if mode == 'content':
                    with (templates / 'routing.yml.in').open('a') as stream:
                        stream.write('# actual workflow content change\n')
                else:
                    (templates / 'contract.json').write_text('{"workflowContract":"relay-workflows-v3"}')
                result = projection.prepare(self.config, 'b' * 40, source, self.root, output)
                self.assertEqual(result['state'], 'workflow-review-required')
                projection.verify(self.config, 'b' * 40, source, output)
                self.assertEqual(before, {path: (self.root / path).read_bytes() for path in before})

    def test_sha_bound_manifest_migrates_once_after_drift_verification(self):
        legacy = {path: raw.replace(b'relay-workflows-v2', HEAD.encode()) for path, raw in self.rendered.items()}
        for path, raw in legacy.items():
            destination = self.root / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
        manifest = {'schemaVersion': 1, 'relayRevision': HEAD,
                    'sourceRepository': self.config['source']['repository'],
                    'consumerRepository': self.config['consumer']['repository'],
                    'files': {path: projection.sha256(raw) for path, raw in legacy.items()}}
        (self.root / projection.MANIFEST).write_text(json.dumps(manifest))
        with tempfile.TemporaryDirectory(prefix='relay-migration-') as output:
            self.assertEqual(projection.prepare(self.config, HEAD, ROOT, self.root, output)['state'], 'workflow-review-required')
            self.assertEqual(json.loads((self.root / projection.MANIFEST).read_text()), manifest)
            shutil.copytree(output, self.root, dirs_exist_ok=True)
            self.assertEqual(projection.prepare(self.config, 'b' * 40, ROOT, self.root, output)['state'], 'ready')

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
        manifest.write_text(expected.replace('"schemaVersion": 2', '"schemaVersion": 2, "schemaVersion": 2'))
        with self.assertRaisesRegex(InvalidConfig, 'duplicate-key'):
            self.project()
        manifest.write_text(expected.replace('"schemaVersion": 2', '"schemaVersion": true'))
        with self.assertRaisesRegex(InvalidConfig, 'workflow-manifest-version'):
            self.project()
        manifest.write_text(expected)
        for revision in ['main', '../../candidate', '', 'a' * 39]:
            with self.assertRaisesRegex(InvalidConfig, 'workflow-exact-revision'):
                self.project(revision)

    def test_partial_mutation_is_visible_and_cannot_be_blindly_retried(self):
        self.project()
        self.config['environment']['generalRunner']['name'] = 'changed-runner'
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
        self.config['environment']['generalRunner']['name'] = 'changed-runner'
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

    def test_bootstrap_derives_missing_projection_and_preserves_old_consumer_workflows(self):
        path = self.root / next(iter(self.rendered))
        path.parent.mkdir(parents=True)
        path.write_text('old consumer-owned workflow\n')
        with tempfile.TemporaryDirectory(prefix='relay-bootstrap-artifacts-') as output:
            result = projection.prepare(self.config, HEAD, ROOT, self.root, output)
            self.assertEqual(result['state'], 'workflow-review-required')
            self.assertEqual(path.read_text(), 'old consumer-owned workflow\n')
            self.assertFalse((self.root / projection.MANIFEST).exists())
            projection.verify(self.config, HEAD, ROOT, output)
            self.assertEqual(projection.prepare(self.config, HEAD, ROOT, self.root, output), result)
            # Simulate the separately owner-reviewed consumer publication.
            shutil.copytree(output, self.root, dirs_exist_ok=True)
            self.assertEqual(projection.prepare(self.config, HEAD, ROOT, self.root, output)['state'], 'ready')

    def test_bootstrap_refuses_managed_drift_and_does_not_rewrite_a_reviewed_proposal(self):
        self.project()
        self.config['environment']['generalRunner']['name'] = 'changed-runner'
        with tempfile.TemporaryDirectory(prefix='relay-bootstrap-artifacts-') as output:
            next_head = 'b' * 40
            projection.prepare(self.config, next_head, ROOT, self.root, output)
            proposal_path = Path(output) / next(iter(self.rendered))
            proposal_path.write_text('owner edit in proposal\n')
            with self.assertRaisesRegex(InvalidConfig, 'workflow-drift'):
                projection.prepare(self.config, next_head, ROOT, self.root, output)
            self.assertEqual(proposal_path.read_text(), 'owner edit in proposal\n')
            source_path = self.root / next(iter(self.rendered))
            source_path.write_text('consumer drift\n')
            with self.assertRaisesRegex(InvalidConfig, 'workflow-drift'):
                projection.prepare(self.config, next_head, ROOT, self.root, output)

    def test_bootstrap_cannot_write_proposals_inside_either_checkout(self):
        with self.assertRaisesRegex(InvalidConfig, 'projection-output-outside-checkouts'):
            projection.prepare(self.config, HEAD, ROOT, self.root, self.root / 'output')
        self.assertFalse((self.root / 'output').exists())

    def test_projection_lock_blocks_overlapping_local_mutation(self):
        self.project()
        original_name = self.config['environment']['generalRunner']['name']
        self.config['environment']['generalRunner']['name'] = 'changed-runner'
        (self.root / '.github/.relay-workflows.lock').mkdir()
        with self.assertRaisesRegex(InvalidConfig, 'workflow-projection-in-progress'):
            self.project('b' * 40)
        self.config['environment']['generalRunner']['name'] = original_name
        self.verify()


if __name__ == '__main__':
    unittest.main()
