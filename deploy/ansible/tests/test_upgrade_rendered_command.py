"""Execute the actual Ansible-rendered preflight Python against protected fixtures."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import pytest

pytest.importorskip('ansible', reason='actual Ansible template qualification')
from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar

ROOT = Path(__file__).resolve().parents[3]
ANSIBLE = ROOT / 'deploy/ansible'
pytestmark = pytest.mark.skipif(sys.platform != 'linux' or os.geteuid() != 0,
    reason='native protected /run fixture requires root')
REVISION = 'a' * 40


@pytest.fixture
def command_fixture():
    with tempfile.TemporaryDirectory(prefix='relay-upgrade-rendered-', dir='/run') as temporary:
        root = Path(temporary)
        (root / 'opt').mkdir(mode=0o700)
        (root / 'etc').mkdir(mode=0o700)
        yield root


def rendered(root, *, git_desired=True, expected='none'):
    loader = DataLoader()
    loader.set_basedir(str(ANSIBLE))
    task = loader.load_from_file(str(ANSIBLE / 'tasks/upgrade-preflight.yml'))[0]
    variables = {'playbook_dir': str(ANSIBLE), 'relay_git_desired_state': git_desired,
        'relay_install_root': str(root / 'opt/relay-fixture'),
        'relay_config_root': str(root / 'etc/relay-fixture'),
        'relay_production_operation_target_head': REVISION,
        'relay_intent_expected_installed_revision': expected,
        'relay_owner_apply_requested': True, 'relay_serial_pool_transition': False,
        'relay_installed_deployment_config': json.dumps({'environment': {'namespace': 'relay-fixture'}})}
    template = Templar(loader=loader, variables=variables)
    return (template.template(task['ansible.builtin.command']['argv']),
            template.template(task['ansible.builtin.command']['stdin']))


@pytest.mark.parametrize('git_desired', [True, False])
def test_rendered_preflight_executes_actual_validator_for_an_absent_installation(command_fixture, git_desired):
    argv, stdin = rendered(command_fixture, git_desired=git_desired)
    result = subprocess.run(argv, input=stdin, text=True, capture_output=True, timeout=30,
                            env={'PATH': '/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1'})
    assert result.returncode == 0, result.stderr
    assert result.stdout == 'RELAY_UPGRADE_SOURCE_VALIDATED=none\n'
    assert not (command_fixture / 'opt/relay-fixture').exists()
    assert not (command_fixture / 'etc/relay-fixture').exists()


def test_rendered_git_preflight_refuses_a_planned_identity_mismatch(command_fixture):
    argv, stdin = rendered(command_fixture, expected='b' * 40)
    result = subprocess.run(argv, input=stdin, text=True, capture_output=True, timeout=30,
                            env={'PATH': '/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1'})
    assert result.returncode == 1
    assert result.stdout == ''
    assert result.stderr == 'RELAY_UPGRADE_PREFLIGHT_BLOCKED;inspect-installed-identity-and-owner-intent\n'
