"""Loaded proof is transient and absence/uncertainty never suppresses restart."""
import importlib.util
import copy
import io
import json
import os
from types import SimpleNamespace
from pathlib import Path
import sys
import subprocess
from unittest.mock import patch, MagicMock

import pytest


spec = importlib.util.spec_from_file_location('process_adoption', Path(__file__).parents[1] / 'process_adoption.py')
adoption = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adoption)


def test_service_dependency_sets_ignore_iteration_order_but_keep_configuration_order():
    values = {'LoadState': 'loaded', 'ActiveState': 'active', 'SubState': 'running',
              'NeedDaemonReload': 'no', 'MainPID': '42', 'ControlGroup': '/system.slice/example.service',
              'Requires': 'z.mount a.service z.mount', 'BindsTo': 'x.device y.socket',
              'PartOf': 'parent.target other.service', 'ExecStart': 'first second',
              'DropInPaths': '/one.conf /two.conf', 'EnvironmentFiles': '/first /second'}
    def observed(selected):
        response = SimpleNamespace(stdout='\n'.join(f'{key}={value}' for key, value in selected.items()).encode())
        with patch.object(adoption.subprocess, 'run', return_value=response):
            return adoption.service('example.service')
    before = observed(values)
    permuted = {**values, 'Requires': 'a.service z.mount', 'BindsTo': 'y.socket x.device',
                'PartOf': 'other.service parent.target'}
    assert observed(permuted) == before
    for field in ['Requires', 'BindsTo', 'PartOf']:
        assert observed({**permuted, field: permuted[field] + ' changed.service'}) != before
        with pytest.raises(ValueError):
            observed({**values, field: '../invalid.service'})
    for field in ['ExecStart', 'DropInPaths', 'EnvironmentFiles']:
        assert observed({**permuted, field: ' '.join(reversed(values[field].split()))}) != before


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


def test_complete_proof_survives_actual_json_roundtrip_of_native_stat_tuples():
    native = {'trust': {'/synthetic/certs': {'identity': (1, 2, 3)}}}
    wire = json.loads(json.dumps(native))
    assert run({'before': wire}, observed=native) == {'eligible': True, 'proof': wire}


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


def test_openssl_explicit_store_selection_and_default_dotnet_fallback():
    defaults = SimpleNamespace(openssl_cafile_env='SSL_CERT_FILE', openssl_cafile='/default/bundle.pem',
                               openssl_capath_env='SSL_CERT_DIR', openssl_capath='/default/certs')
    assert adoption.trust_locations({}, defaults) == ['/default/bundle.pem', '/default/certs', '/etc/ssl/certs']
    assert adoption.trust_locations({'SSL_CERT_FILE': '/custom/root.pem',
                                     'SSL_CERT_DIR': '/custom/one:/custom/two'}, defaults) == [
                                         '/custom/root.pem', '/custom/one', '/custom/two']
    with pytest.raises(ValueError):
        adoption.trust_locations({'SSL_CERT_FILE': 'relative.pem'}, defaults)


def trust_epoch(path):
    return max(item.lstat().st_ctime for item in [path, *path.parents, *path.rglob('*')]) + 5


@pytest.mark.parametrize('change', ['add', 'remove', 'content', 'link', 'directory'])
def test_trust_store_detects_roots_and_topology_changes_since_loaded_start(tmp_path, change):
    store = tmp_path / 'certs'; store.mkdir()
    first = store / 'root.pem'; first.write_bytes(b'synthetic-root-one')
    second = store / 'other.pem'; second.write_bytes(b'synthetic-root-two')
    alias = store / 'hash.0'; alias.symlink_to('root.pem')
    earliest = trust_epoch(tmp_path)
    before = adoption.trust_store(store, earliest, os.getuid(), boundary=tmp_path)
    if change == 'add':
        (store / 'new.pem').write_bytes(b'new-root')
    elif change == 'remove':
        first.unlink(); alias.unlink()
    elif change == 'content':
        first.write_bytes(b'changed-root')
    elif change == 'link':
        alias.unlink(); alias.symlink_to('other.pem')
    else:
        store.chmod(0o700)
    assert adoption.trust_store(store, trust_epoch(tmp_path), os.getuid(), boundary=tmp_path) != before
    # Real retained processes predate the mutation. Even reverted bytes cannot
    # prove that the loaded runtime has adopted a changed system trust store.
    changed_epoch = max(item.lstat().st_ctime for item in [store, *store.rglob('*')])
    with pytest.raises(ValueError):
        adoption.trust_store(store, changed_epoch + 1, os.getuid(), boundary=tmp_path)


@pytest.mark.parametrize('kind', ['missing', 'writable', 'dangling', 'cycle'])
def test_unknown_or_unsafe_trust_store_refuses_fast_path(tmp_path, kind):
    store = tmp_path / 'certs'; store.mkdir()
    root = store / 'root.pem'; root.write_bytes(b'synthetic-root')
    if kind == 'missing':
        root.unlink(); store.rmdir()
    elif kind == 'writable':
        root.chmod(0o666)
    elif kind == 'dangling':
        (store / 'hash.0').symlink_to('absent.pem')
    else:
        (store / 'hash.0').symlink_to('hash.0')
    with pytest.raises((OSError, ValueError, RuntimeError)):
        adoption.trust_store(store, trust_epoch(tmp_path), os.getuid(), boundary=tmp_path)


def test_absent_user_x509_store_requires_unchanged_nearest_parent(tmp_path):
    before = adoption.trust_store_parent(tmp_path, trust_epoch(tmp_path), os.getuid(), boundary=tmp_path)
    (tmp_path / '.dotnet').mkdir()
    assert adoption.trust_store_parent(tmp_path, trust_epoch(tmp_path), os.getuid(), boundary=tmp_path) != before
    with pytest.raises(ValueError):
        adoption.trust_store_parent(tmp_path, tmp_path.stat().st_ctime + 1, os.getuid(), boundary=tmp_path)


def test_unrelated_outer_directory_entries_are_not_loaded_ca_inputs(tmp_path):
    if os.getuid() != 0:
        pytest.skip('root-owned outer traversal fixture required')
    store = tmp_path / 'certs'; store.mkdir()
    (store / 'root.pem').write_bytes(b'synthetic-root')
    before = adoption.trust_store(store, trust_epoch(tmp_path), boundary=tmp_path)
    (tmp_path / 'unrelated-operation-record').write_bytes(b'not-a-CA-input')
    assert adoption.trust_store(store, trust_epoch(tmp_path), boundary=tmp_path) == before

def test_sqlite_data_mapping_changes_do_not_become_startup_dependency_drift(tmp_path):
    data = tmp_path / 'reviewer.sqlite3-shm'; data.write_bytes(b'first-live-state'); data.chmod(0o600)
    meta = data.stat()
    device = format(os.major(meta.st_dev), 'x') + ':' + format(os.minor(meta.st_dev), 'x')
    adoption.mutable_sqlite_mapping(data, 'rw-s', device, str(meta.st_ino), os.getuid())
    data.write_bytes(b'changed-live-state')
    adoption.mutable_sqlite_mapping(data, 'rw-s', device, str(meta.st_ino), os.getuid())
    for permissions, inode, uid in [('r-xs', str(meta.st_ino), os.getuid()),
                                    ('rw-s', str(meta.st_ino + 1), os.getuid()),
                                    ('rw-s', str(meta.st_ino), os.getuid() + 1)]:
        with pytest.raises(ValueError):
            adoption.mutable_sqlite_mapping(data, permissions, device, inode, uid)
    alias = tmp_path / 'aliased.sqlite3-shm'; alias.symlink_to(data)
    with pytest.raises(OSError):
        adoption.mutable_sqlite_mapping(alias, 'rw-s', device, str(meta.st_ino), os.getuid())


def test_actual_managed_dropin_is_proved_instead_of_blanket_rejected(tmp_path):
    if os.getuid() != 0:
        pytest.skip('root-owned systemd configuration fixture required')
    unit = tmp_path / 'runner.service'; unit.write_text('[Service]\nExecStart=/synthetic/runner\n')
    directory = tmp_path / 'runner.service.d'; directory.mkdir()
    dropin = directory / 'production-local-apply.conf'; dropin.write_text('[Service]\nReadWritePaths=/synthetic\n')
    state = {'FragmentPath': str(unit), 'DropInPaths': str(dropin)}
    # Bound only the root filesystem traversal for this isolated fixture.
    native = adoption.trust_store
    with patch.object(adoption, 'trust_store', side_effect=lambda path, earliest: native(path, earliest, boundary=tmp_path)):
        before = adoption.service_configuration(state, trust_epoch(tmp_path))
        assert str(dropin) in before['files']
        dropin.write_text('[Service]\nReadWritePaths=/changed\n')
        with pytest.raises(ValueError):
            adoption.service_configuration(state, dropin.stat().st_ctime + 1)


def test_runner_environment_file_selection_uses_loaded_component_configuration():
    state = {'EnvironmentFiles': '/etc/synthetic/relay.env (ignore_errors=yes)'}
    assert adoption.service_environment_files(state) == ['/etc/synthetic/relay.env']
    assert '/etc/synthetic/reviewer-credentials/github-app.env' not in adoption.service_environment_files(state)
    assert adoption.service_environment_files({'EnvironmentFiles': ''}) == []
    with pytest.raises(ValueError):
        adoption.service_environment_files({'EnvironmentFiles': '/etc/synthetic/../foreign.env (ignore_errors=no)'})


def test_generated_helper_consumer_bound_keeps_original_and_current_clock_guards():
    state = {'ExecMainStartTimestamp': 'Sat 2026-11-14 09:00:00.123456 UTC',
             'ExecMainStartTimestampMonotonic': '5000000'}
    base = 1794646800000000000
    hz = os.sysconf('SC_CLK_TCK')
    with patch.object(adoption.time, 'time_ns', return_value=base + 100000000000), \
            patch.object(adoption.time, 'clock_gettime_ns', return_value=10000000000):
        # The original monotonic anchor is truncated to microseconds: subtract
        # its full quantum before taking max with any finer independent bound.
        assert adoption.consumer_start_lower_bound(state, str(6 * hz)) == base + 1123455000
    with patch.object(adoption.time, 'time_ns', return_value=base - 100000000000), \
            patch.object(adoption.time, 'clock_gettime_ns', return_value=10000000000):
        assert adoption.consumer_start_lower_bound(state, str(6 * hz)) == base - 104000000000
    with pytest.raises(ValueError):
        adoption.consumer_start_lower_bound({**state, 'ExecMainStartTimestamp': 'Sat 2026-11-14 09:00:00 UTC'}, str(6 * hz))


@pytest.mark.parametrize('fault', [None, 'peer', 'sequence', 'family', 'version', 'uid', 'pid',
                                  'truncated', 'attribute', 'recipient', 'command', 'denied', 'short-stats'])
def test_live_taskstats_reply_is_kernel_bound_and_elapsed_rounding_is_conservative(fault):
    pack = adoption.struct.pack
    def attr(kind, value):
        raw = pack('=HH', len(value) + 4, kind) + value
        return raw + b'\0' * (-len(raw) % 4)
    def reply(family, command, version, sequence, attrs):
        body = pack('=BBH', command, version, 0) + attrs
        return pack('=IHHII', len(body) + 16, family, 0, sequence, 123) + body
    stats = bytearray(152)
    adoption.struct.pack_into('=H', stats, 0, 13)
    adoption.struct.pack_into('=I', stats, 120, 99 if fault == 'uid' else 12)
    adoption.struct.pack_into('=I', stats, 128, 99 if fault == 'pid' else 42)
    adoption.struct.pack_into('=Q', stats, 144, 123456)
    aggregate = attr(1, pack('=I', 42)) + attr(3, stats[:120] if fault == 'short-stats' else stats)
    attrs = attr(4, aggregate)
    if fault == 'attribute':
        attrs = pack('=HH', 65535, 4)
    raw = reply(99 if fault == 'family' else 35, 2, 99 if fault == 'version' else 1,
                99 if fault == 'sequence' else 2, attrs)
    if fault == 'recipient':
        raw = raw[:12] + pack('=I', 99) + raw[16:]
    elif fault == 'command':
        raw = raw[:16] + b'\x01' + raw[17:]
    elif fault == 'denied':
        raw = reply(2, 2, 1, 2, pack('=i', -1))
    if fault == 'truncated':
        raw = raw[:-1]
    channel = MagicMock()
    channel.__enter__.return_value = channel
    channel.getsockname.return_value = (123, 0)
    channel.recvfrom.side_effect = [(reply(16, 1, 2, 1, attr(1, pack('=H', 35))), (0, 0)),
                                    (raw, (7, 0) if fault == 'peer' else (0, 0))]
    with patch.object(adoption.socket, 'socket', return_value=channel), \
            patch.object(adoption.time, 'clock_gettime_ns', return_value=1000000000):
        if fault is None:
            assert adoption.taskstats_elapsed('42', 12) == 1000000000 - 123457000
        else:
            with pytest.raises(ValueError):
                adoption.taskstats_elapsed('42', 12)


def test_precise_consumer_clock_bound_does_not_relax_history_when_provider_unavailable():
    state = {'ExecMainStartTimestamp': 'Sat 2026-11-14 09:00:00.123456 UTC',
             'ExecMainStartTimestampMonotonic': '5000000'}
    with patch.object(adoption.time, 'time_ns', return_value=1794646900000000000), \
            patch.object(adoption.time, 'clock_gettime_ns', return_value=10000000000):
        strict = adoption.consumer_start_lower_bound(state, '600')
        with patch.object(adoption, 'precise_consumer_lower_bound', side_effect=OSError('unsupported')):
            assert adoption.consumer_start_lower_bound(state, '600', '42', {'start': '600'}, 12) == strict
        with patch.object(adoption, 'precise_consumer_lower_bound', return_value=strict - 1000):
            assert adoption.consumer_start_lower_bound(state, '600', '42', {'start': '600'}, 12) == strict
        with patch.object(adoption, 'precise_consumer_lower_bound', return_value=strict + 5000000):
            assert adoption.consumer_start_lower_bound(state, '600', '42', {'start': '600'}, 12) == strict + 5000000


@pytest.mark.parametrize('moved', [False, True])
def test_precise_consumer_original_clock_truncation_and_pid_generation(moved):
    state = {'ExecMainStartTimestamp': 'Sat 2026-11-14 09:00:00.123456 UTC',
             'ExecMainStartTimestampMonotonic': '5000000'}
    original = adoption.service_started_ns(state)
    proc_stat = '42 (shell)' + ' x' * 19 + (' 601' if moved else ' 600')
    with patch.object(adoption, 'taskstats_elapsed', return_value=6000123456), \
            patch.object(Path, 'read_text', return_value=proc_stat), \
            patch.object(adoption.time, 'time_ns', return_value=original + 100000000000), \
            patch.object(adoption.time, 'clock_gettime_ns', return_value=10000000000):
        if moved:
            with pytest.raises(ValueError):
                adoption.precise_consumer_lower_bound(state, '42', {'start': '600'}, 12)
        else:
            assert adoption.precise_consumer_lower_bound(state, '42', {'start': '600'}, 12) == original + 1000122456


@pytest.mark.parametrize('change', [None, 'bytes', 'consumer-time', 'template', 'generator', 'no-consumer'])
def test_generated_runner_helper_requires_template_generator_and_consuming_time(tmp_path, change):
    generator = tmp_path / 'run.sh'
    generator.write_bytes(b'cp -f "$DIR"/run-helper.sh.template "$DIR"/run-helper.sh\n')
    template = tmp_path / 'run-helper.sh.template'; template.write_bytes(b'#!/bin/bash\n/synthetic/Runner.Listener run\n')
    helper = tmp_path / 'run-helper.sh'; helper.write_bytes(template.read_bytes())
    state = {'MainPID': 'wrapper'}
    processes = {'wrapper': {'executable': 'bash'}, 'consumer': {'executable': 'bash', 'start': '600'}}
    arguments = {'wrapper': ['bash', str(generator)], 'consumer': ['bash', str(helper)]}
    epoch = trust_epoch(tmp_path)
    lower = helper.stat().st_ctime_ns + 1000000000
    if change == 'bytes':
        helper.write_bytes(b'changed executable script')
    elif change == 'consumer-time':
        lower = helper.stat().st_ctime_ns
    elif change == 'template':
        template.write_bytes(b'changed template')
    elif change == 'generator':
        generator.write_bytes(b'unqualified copy recipe')
    elif change == 'no-consumer':
        arguments['consumer'] = ['bash', '/unrelated/script']
    with patch.object(adoption, 'runner_arguments', side_effect=lambda pid, _proof: arguments[pid]), \
            patch.object(adoption, 'consumer_start_lower_bound', return_value=lower):
        if change is None:
            result = adoption.generated_runner_helper(tmp_path, state, processes, epoch, os.getuid())
            assert result['sha256'] == adoption.digest(template.read_bytes()) and result['consumer'] == 'consumer'
        else:
            with pytest.raises(ValueError):
                adoption.generated_runner_helper(tmp_path, state, processes, epoch, os.getuid())


@pytest.mark.parametrize('target_spelling', ['relative', 'absolute'])
def test_native_npm_leaf_alias_proves_only_unchanged_same_distribution_target(tmp_path, target_spelling):
    distribution = tmp_path / 'externals'
    cli = distribution / 'node/bin/npm'; cli.parent.mkdir(parents=True)
    target = distribution / 'node/lib/npm-cli.js'; target.parent.mkdir()
    target.write_bytes(b'public-native-npm-entrypoint')
    cli.symlink_to('../lib/npm-cli.js' if target_spelling == 'relative' else str(target))
    result = adoption.distribution_alias(cli, [distribution], trust_epoch(tmp_path), os.getuid())
    assert result['sha256'] == adoption.digest(target.read_bytes())
    assert result['target'] == str(target) and str(cli) in result['links']


@pytest.mark.parametrize('change', ['escape', 'credentials', 'hardlink', 'directory-link', 'writable', 'new-link', 'new-target', 'cycle'])
def test_distribution_alias_never_weakens_fixed_input_or_immutable_target_proof(tmp_path, change):
    distribution = tmp_path / 'externals'; distribution.mkdir()
    target = distribution / 'npm-cli.js'; target.write_bytes(b'public-script')
    link = distribution / 'npm'; link.symlink_to('npm-cli.js')
    if change == 'escape':
        link.unlink(); link.symlink_to('../../foreign-input')
    elif change == 'credentials':
        credentials = tmp_path / '.credentials'; credentials.write_bytes(b'synthetic-private-input')
        link.unlink(); link.symlink_to('../.credentials')
    elif change == 'hardlink':
        os.link(target, distribution / 'hardlink')
    elif change == 'directory-link':
        directory = distribution / 'alias'; directory.symlink_to('.', target_is_directory=True)
        link.unlink(); link.symlink_to('alias/npm-cli.js')
    elif change == 'writable':
        target.chmod(0o666)
    elif change == 'cycle':
        link.unlink(); link.symlink_to('npm')
    epoch = trust_epoch(tmp_path)
    if change == 'new-link':
        epoch = link.lstat().st_ctime + 1
    elif change == 'new-target':
        epoch = target.stat().st_ctime + 1
    with pytest.raises((ValueError, OSError)):
        adoption.distribution_alias(link, [distribution], epoch, os.getuid())


@pytest.mark.parametrize('name', ['.env', '.path', '.runner_migrated', '.credentials_rsaparams',
                                  'bin/removed.dll', 'externals/node/lib/removed.js'])
def test_deletion_before_first_capture_cannot_hide_loaded_optional_or_interpreted_input(tmp_path, name):
    root = tmp_path / 'runner'; root.mkdir()
    value = root / name; value.parent.mkdir(parents=True, exist_ok=True)
    value.write_bytes(b'previously-loaded-input')
    directory = value.parent
    before = adoption.distribution_directory(directory, trust_epoch(tmp_path), os.getuid())
    value.unlink()
    assert adoption.distribution_directory(directory, trust_epoch(tmp_path), os.getuid()) != before
    # A fresh capture after deletion still has to refuse: no previous in-memory
    # proof is needed to detect a post-start loss of cached settings/code.
    with pytest.raises(ValueError):
        adoption.distribution_directory(directory, directory.stat().st_ctime + 1, os.getuid())


def test_existing_generated_helper_write_keeps_directory_topology_but_not_file_history(tmp_path):
    helper = tmp_path / 'run-helper.sh'; helper.write_bytes(b'public-generated-template')
    before = adoption.distribution_directory(tmp_path, trust_epoch(tmp_path), os.getuid())
    helper.write_bytes(b'public-generated-template')
    assert adoption.distribution_directory(tmp_path, trust_epoch(tmp_path), os.getuid()) == before
    # The separate consuming-process proof remains necessary for this file.
    with pytest.raises(ValueError):
        adoption.unchanged_since_start(helper, helper.stat().st_ctime + 1, os.getuid())


@pytest.mark.parametrize('movement', [None, 'membership', 'start', 'executable', 'command', 'maps', 'environment', 'uid'])
def test_end_scan_detects_child_movement_even_with_same_main_pid(tmp_path, movement):
    group = tmp_path / 'cgroup.procs'; group.write_text('101\n102\n')
    original = {'101': {'start': '1', 'executable': 'wrapper', 'command': 'wrapper-command',
                        'maps': {'/public/bash': 'a'}, 'environment': 'first', 'uid': 1000},
                '102': {'start': '2', 'executable': 'listener', 'command': 'listener-command',
                        'maps': {'/public/runtime': 'b'}, 'environment': 'second', 'uid': 1000}}
    observed = copy.deepcopy(original)
    if movement == 'membership':
        group.write_text('101\n103\n')
    elif movement is not None:
        observed['102'][movement] = {'/changed/runtime': 'c'} if movement == 'maps' else 'changed'
    state = {'MainPID': '101', 'ExecMainStartTimestamp': 'Sat 2026-11-14 09:00:00 UTC'}
    with patch.object(adoption, 'process', side_effect=lambda pid, _start: observed[pid]):
        if movement is None:
            adoption.revalidate_runner_processes(group, original, state)
        else:
            with pytest.raises(ValueError):
                adoption.revalidate_runner_processes(group, original, state)


def test_child_movement_during_end_scan_is_also_refused(tmp_path):
    group = tmp_path / 'cgroup.procs'; group.write_text('101\n102\n')
    original = {'101': {'start': '1'}, '102': {'start': '2'}}
    def observe(pid, _start):
        if pid == '102':
            group.write_text('101\n103\n')
        return original[pid]
    with patch.object(adoption, 'process', side_effect=observe), pytest.raises(ValueError):
        adoption.revalidate_runner_processes(group, original, {'ExecMainStartTimestamp': 'Sat 2026-11-14 09:00:00 UTC'})


def test_runner_trust_uses_actual_crypto_child_environment_not_service_wrapper():
    import ssl
    paths = {row.split(None, 5)[5] for row in Path('/proc/self/maps').read_text().splitlines()
             if len(row.split(None, 5)) == 6 and '/libcrypto.so' in row.split(None, 5)[5]}
    assert len(paths) == 1
    crypto = next(iter(paths))
    child = {'HOME': '/synthetic/listener-home', 'SSL_CERT_FILE': '/synthetic/listener-roots.pem'}
    processes = {'wrapper': {'maps': {}}, 'listener': {'maps': {crypto: adoption.digest(Path(crypto).read_bytes())}}}
    with patch.object(adoption, 'environment', return_value=child) as environment, \
            patch.object(adoption, 'process_trust', return_value={'verified': True}) as trust:
        assert adoption.runner_trust(processes, 100, 1000) == {'listener': {'verified': True}}
        environment.assert_called_once_with('listener')
        assert trust.call_args.args[0] == child


def test_real_sqlite_wal_mapping_is_mutable_state_not_an_executable_dependency(tmp_path):
    # Other native suites can legitimately leave unrelated deleted mappings in
    # pytest. Keep the production refusal intact and inspect a fresh process.
    import mmap
    script = r'''
import importlib.util,json,os,sqlite3,sys,time
from pathlib import Path
spec=importlib.util.spec_from_file_location('isolated_process_adoption',sys.argv[1])
adoption=importlib.util.module_from_spec(spec);spec.loader.exec_module(adoption)
database=Path(sys.argv[2])/'reviewer.sqlite3'
with sqlite3.connect(database) as connection:
    assert connection.execute('PRAGMA journal_mode=WAL').fetchone()==('wal',)
    connection.execute('CREATE TABLE evidence (value TEXT)');connection.commit()
    assert str(database)+'-shm' in Path('/proc/self/maps').read_text()
    proof=adoption.process(os.getpid(),time.time()+5,mutable_database=str(database))
    assert not any(path.startswith(str(database)) for path in proof['maps'])
    try:
        adoption.process(os.getpid(),time.time()+5,mutable_database=str(database)+'-other')
    except ValueError:
        pass
    else:
        raise AssertionError('wrong configured database bypassed loaded-map refusal')
    connection.execute('INSERT INTO evidence VALUES (?)',('new-live-state',));connection.commit()
    assert adoption.process(os.getpid(),time.time()+5,mutable_database=str(database))==proof
print(json.dumps({'real_wal_mapping':True,'mutation_preserved':True,'wrong_database_refused':True}))
'''
    prior = tmp_path / 'unrelated-prior-suite-mapping'
    prior.write_bytes(b'x' * 4096)
    with prior.open('r+b') as stream, mmap.mmap(stream.fileno(), 0) as held:
        prior.unlink()
        assert str(prior) + ' (deleted)' in Path('/proc/self/maps').read_text()
        result = subprocess.run([sys.executable, '-I', '-B', '-c', script,
                                 str(spec.origin), str(tmp_path)],
                                text=True, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {'real_wal_mapping': True, 'mutation_preserved': True,
                                       'wrong_database_refused': True}


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
