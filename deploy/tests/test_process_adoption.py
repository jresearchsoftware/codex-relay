"""Loaded proof is transient and absence/uncertainty never suppresses restart."""
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

import pytest


spec = importlib.util.spec_from_file_location('process_adoption', Path(__file__).parents[1] / 'process_adoption.py')
adoption = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adoption)


def run(payload, observed=None, error=None):
    output = io.StringIO()
    with patch.object(sys, 'stdin', io.StringIO(json.dumps(payload))), patch.object(sys, 'stdout', output), \
            patch.object(adoption, 'capture', return_value=observed, side_effect=error):
        adoption.main()
    return json.loads(output.getvalue())


def test_loaded_configuration_excludes_only_artifact_provenance():
    config = {'artifact': {'commit': 'a' * 40, 'sha256': 'b' * 64}, 'owner': 'alice',
              'service': {'bind_port': 8787}, 'githubNativeAuthorityEnabled': True}
    before = adoption.configuration(json.dumps(config))
    config['artifact'] = {'commit': 'c' * 40, 'sha256': 'd' * 64}
    assert adoption.configuration(json.dumps(config)) == before
    for key, value in [('owner', 'bob'), ('service', {'bind_port': 8788}),
                       ('githubNativeAuthorityEnabled', False)]:
        changed = dict(config, **{key: value})
        assert adoption.configuration(json.dumps(changed)) != before


@pytest.mark.parametrize('config', ['{"artifact":{},"owner":"a","owner":"a"}',
                                  '{"artifact":{"commit":"unresolved","sha256":"b"}}'])
def test_corrupt_or_ambiguous_config_never_qualifies_by_matching_semantics(config):
    with pytest.raises((ValueError, TypeError)):
        adoption.configuration(config)


@pytest.mark.parametrize('error', [FileNotFoundError(), PermissionError(), ValueError(), KeyError('private')])
def test_unavailable_or_stale_proof_retains_existing_restart(error):
    assert run({}, error=error) == {'eligible': False}


@pytest.mark.parametrize('field', ['config', 'ca', 'key', 'unit', 'environment', 'pid', 'dependencies'])
def test_any_changed_loaded_input_or_process_refuses_preservation(field):
    before = {field: 'old'}
    assert run({'before': before}, observed={field: 'new'}) == {'eligible': False}


def test_only_complete_unchanged_proof_selects_preservation():
    proof = {'reviewer': {'pid': 123, 'config': 'a'}, 'production': {'pid': 456}}
    assert run({'before': proof}, observed=proof) == {'eligible': True, 'proof': proof}


def test_kernel_change_time_rejects_stale_cached_runner_settings(tmp_path):
    settings = tmp_path / '.runner'
    settings.write_text('{"agentName":"current"}')
    with pytest.raises(ValueError, match='PROCESS_ADOPTION_UNPROVEN'):
        adoption.unchanged_since_start(settings, settings.stat().st_ctime, settings.stat().st_uid)
    expected = adoption.digest(settings.read_bytes())
    assert adoption.unchanged_since_start(settings, settings.stat().st_ctime + 3, settings.stat().st_uid) == expected


def test_private_input_symlink_is_not_accepted(tmp_path):
    real = tmp_path / 'key'
    real.write_text('synthetic')
    link = tmp_path / 'alias'
    link.symlink_to(real)
    with pytest.raises((ValueError, OSError)):
        adoption.protected(link, uid=real.stat().st_uid)


def test_mapped_inode_and_change_time_prove_loaded_dependency(tmp_path):
    dependency = tmp_path / 'runtime.so'
    dependency.write_bytes(b'synthetic-runtime')
    meta = dependency.stat()
    device = format(os.major(meta.st_dev), 'x') + ':' + format(os.minor(meta.st_dev), 'x')
    expected = adoption.digest(dependency.read_bytes())
    assert adoption.mapped_digest(dependency, device, str(meta.st_ino), meta.st_ctime + 3) == expected
    with pytest.raises(ValueError):
        adoption.mapped_digest(dependency, device, str(meta.st_ino + 1), meta.st_ctime + 3)
    with pytest.raises(ValueError):
        adoption.mapped_digest(dependency, device, str(meta.st_ino), meta.st_ctime)


def test_original_systemd_start_time_must_be_explicit_and_utc():
    assert adoption.service_started({'ExecMainStartTimestamp': 'Sat 2026-11-14 09:00:00 UTC'}) == 1794646800
    with pytest.raises(ValueError):
        adoption.service_started({'ExecMainStartTimestamp': ''})


def test_lost_operation_or_drain_rejects_reuse():
    gate = {'operationId': 'current', 'target': 'a', 'phase': 'applying', 'active': [], 'unknown': [],
            'previousActive': {'reviewer': {'active': True}, 'production': {'active': True}}}
    payload = {'admission': ['/synthetic/admission'], 'operation': 'current', 'target': 'a',
               'productionActive': True}
    result = type('Result', (), {})()
    with patch.object(adoption.subprocess, 'run', return_value=result):
        result.stdout = json.dumps(gate).encode()
        assert adoption.admission(payload) == gate
        for key, bad in [('operationId', 'foreign'), ('phase', 'recovery-required'),
                         ('target', 'b'), ('active', [1]), ('unknown', [2])]:
            result.stdout = json.dumps(dict(gate, **{key: bad})).encode()
            with pytest.raises(ValueError):
                adoption.admission(payload)


def test_restart_and_final_loaded_proof_are_both_gated():
    tasks = Path(__file__).parents[1] / 'ansible/tasks'
    activation = (tasks / 'upgrade-lifecycle-activate.yml').read_text()
    validation = (tasks / 'upgrade-lifecycle-validation.yml').read_text()
    assert 'not relay_upgrade_loaded_process_preserved' in activation
    assert 'not relay_upgrade_loaded_process_preserved' in validation
    assert 'RELAY_UPGRADE_PRESERVED_LOADED_INPUTS_UNPROVEN' in validation
