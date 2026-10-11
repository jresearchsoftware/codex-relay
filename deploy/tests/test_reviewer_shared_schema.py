"""Shared compile-time inputs bind the staged Reviewer and reuse identity."""
import importlib.util
from pathlib import Path
import re
import shutil
import subprocess
import sys

from jinja2 import Environment, StrictUndefined
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
spec = importlib.util.spec_from_file_location('relay_deploy_shared_schema', ROOT / 'deploy/relay-deploy.py')
deployment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deployment)


def test_staged_reviewer_resolves_shared_compile_time_schema_from_exact_source(tmp_path):
    release = tmp_path / 'release'; reviewed = release / 'reviewed-source'
    (reviewed / 'contracts/src').mkdir(parents=True)
    (release / 'reviewer-source/src').mkdir(parents=True)
    shutil.copyfile(ROOT / 'reviewer/src/task_authority.rs', release / 'reviewer-source/src/task_authority.rs')
    environment = Environment(undefined=StrictUndefined)
    tasks = yaml.safe_load((ROOT / 'deploy/ansible/roles/relay_artifacts/tasks/main.yml').read_text())
    task = next(task for task in tasks if task['name'] == 'Stage the exact shared GitHub authority schemas for the Reviewer build')
    copy = task['ansible.builtin.copy']
    values = {'relay_release_path': str(release), 'relay_group': 'synthetic-group'}
    assert copy['remote_src'] is True and copy['owner'] == 'root' and copy['mode'] == '0640'
    assert set(task['loop']) == {'github-authority-v1.json', 'github-authority-v4.json'}
    staged = {}
    for item in task['loop']:
        source = ROOT / 'contracts/src' / item
        shutil.copyfile(source, reviewed / 'contracts/src' / item)
        src, dest = [Path(environment.from_string(copy[key]).render({**values, 'item': item})) for key in ['src', 'dest']]
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        staged[dest.resolve()] = source
    rust = release / 'reviewer-source/src/task_authority.rs'
    includes = re.findall(r'include_str!\(\s*"([^"]+)"\s*\)', rust.read_text())
    assert {(rust.parent / include).resolve() for include in includes} == set(staged)
    for include in includes:
        resolved = (rust.parent / include).resolve()
        assert resolved.read_bytes() == staged[resolved].read_bytes()
    directory = next(task for task in tasks if task['name'] == 'Create protected shared Reviewer schema build inputs')
    assert directory['ansible.builtin.file']['mode'] == '0750'
    assert directory['ansible.builtin.file']['owner'] == 'root'
    assert tasks.index(task) < next(index for index, row in enumerate(tasks) if row['name'] == 'Build the locked reviewed Rust Reviewer release artifact')


@pytest.mark.parametrize('schema', ['github-authority-v1.json', 'github-authority-v4.json'])
def test_schema_only_source_change_invalidates_reviewer_reuse_identity(tmp_path, schema):
    git = lambda *args: subprocess.check_output(['git', '-C', str(tmp_path), *args], text=True).strip()
    for path in ['reviewer/src/main.rs', 'contracts/src/github-authority-v1.json', 'contracts/src/github-authority-v4.json',
                 'controller/src/main.mjs', 'runtime/src/main.mjs', 'consumer/consumer.mjs',
                 'deploy/ansible/roles/relay_artifacts/main.yml',
                 'deploy/ansible/roles/relay_codex_runtime/templates/relay-codex-launcher.mjs.j2']:
        destination = tmp_path / path; destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text('synthetic source\n')
    git('init', '--quiet', '--template=', '--initial-branch=main')
    def commit(message):
        git('add', '.'); git('-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid',
                            'commit', '--quiet', '-m', message)
    commit('baseline')
    initial = deployment.source_identity(tmp_path)
    (tmp_path / 'contracts/src' / schema).write_text('changed shared schema\n')
    commit('schema only')
    changed = deployment.source_identity(tmp_path)
    assert changed['reviewerSourceTreeSha256'] != initial['reviewerSourceTreeSha256']
    assert changed['reviewerBuildInputsTreeSha256'] == initial['reviewerBuildInputsTreeSha256']
    assert changed['controllerSourceTreeSha256'] != initial['controllerSourceTreeSha256']
