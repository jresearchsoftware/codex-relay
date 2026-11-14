"""Independent reference acquisition and read-only complete payload proof."""
import os
import hashlib
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
import source_upgrade_packages as packages

SOURCE = Path(__file__).parents[2]
OPERATION = '12345678-1234-1234-1234-123456789abc'
pytestmark = pytest.mark.skipif(sys.platform != 'linux' or os.geteuid() != 0, reason='root Linux package ownership proof')


def distribution(home, install):
    release = home / 'packages/standalone/releases/0.167.2-test-linux'
    (release / 'bin').mkdir(parents=True)
    binary = release / 'bin/codex'
    binary.write_text('#!/bin/sh\nprintf "codex-cli 0.167.2\\n"\n'); binary.chmod(0o755)
    (release / 'resource').write_bytes(b'official independent resource bytes')
    (release / 'resource-link').symlink_to(release / 'resource')
    install.mkdir(exist_ok=True)
    (install / 'codex').symlink_to(binary)


@pytest.fixture
def prepared():
    # Private execution resource under root-owned /run: the actual stage helper
    # checks every ancestor. No test replaces that protected-path predicate.
    with tempfile.TemporaryDirectory(prefix='relay-task253-package-test-', dir='/run') as temporary:
        root = Path(temporary); root.chmod(0o700)
        stage = root / ('.stage-' + OPERATION); stage.mkdir(mode=0o700)
        live = root / 'live'; live.mkdir()
        home = live / 'package-home'; home.mkdir(mode=0o700)
        install = live / 'package-bin'; distribution(home, install)
        owners = packages._owners(SOURCE)
        owners[2].qualify(home, install / 'codex', packages.VERSION, normalize=True)
        owners[1].relocate_codex(live)
        binary = live / 'bin/codex'; binary.parent.mkdir(); binary.symlink_to((install / 'codex').resolve())
        runtime_home = root / 'runtime-home'; runtime_home.mkdir()
        rust = root / 'rust'; rust.mkdir(); rust.chmod(0o755)
        (rust / 'bin').mkdir(); (rust / 'bin').chmod(0o755)
        for tool in ['cargo', 'rustc', 'rustfmt']:
            (rust / 'bin' / tool).write_bytes(b'synthetic immutable Rust tool fixture')
            (rust / 'bin' / tool).chmod(0o755)
        (rust / 'support-library').write_bytes(b'root-owned Rust dependency')
        (rust / 'support-library').chmod(0o644)
        values = {'relay_codex_cli_version': packages.VERSION, 'relay_codex_installer_url': packages.INSTALLER_URL,
                  'relay_codex_package_home': str(home), 'relay_codex_package_install_dir': str(install),
                  'relay_codex_binary_path': str(binary), 'relay_codex_user': 'synthetic-runtime-user',
                  'relay_codex_home': str(runtime_home), 'relay_rust_toolchain_root': str(root / 'rust'),
                  'relay_group': 'root', 'relay_rust_toolchain_version': '1.90.0'}
        calls = []
        def installer(argv, *, env, cwd):
            calls.append((argv, env, cwd))
            distribution(Path(env['CODEX_HOME']), Path(env['CODEX_INSTALL_DIR']))
            return SimpleNamespace(returncode=0, stdout=b'')
        receipt = packages.prepare_reference(stage, OPERATION, values, SOURCE, execute=installer,
                                             download=lambda url: b'canonical official installer fixture')
        yield root, stage, values, receipt, calls


def runtime(argv, *, env, cwd):
    assert argv[:3] == ['/usr/sbin/runuser', '-u', 'synthetic-runtime-user']
    assert argv[-4:] == [str(Path(cwd).parent / 'live/bin/codex'),
                        str(Path(cwd).parent / 'rust/bin/cargo'), str(Path(cwd).parent / 'rust/bin/rustc'),
                        str(Path(cwd).parent / 'rust/bin/rustfmt')]
    assert set(env) == {'PATH', 'LANG', 'LC_ALL', 'HOME', 'CODEX_HOME'}
    return SimpleNamespace(returncode=0, stdout=b'codex-cli 0.167.2\ncargo 1.90.0 (fixture)\nrustc 1.90.0 (fixture)\nrustfmt 1.8.0\n')


def snapshot(root):
    return {str(path.relative_to(root)): (path.lstat().st_mode, path.lstat().st_ctime_ns,
            os.readlink(path) if path.is_symlink() else path.read_bytes() if path.is_file() else None)
            for path in root.rglob('*')}


def test_explicit_acquisition_uses_existing_pinned_installer_environment(prepared):
    root, stage, values, receipt, calls = prepared
    assert not (stage / 'codex-package').exists()
    assert len(calls) == 1
    argv, env, cwd = calls[0]
    assert argv == ['/bin/sh', str(stage / packages.REFERENCE / 'installer.sh'), '--release', packages.VERSION]
    assert set(env) == {'PATH', 'LANG', 'LC_ALL', 'HOME', 'CODEX_HOME', 'CODEX_INSTALL_DIR', 'CODEX_NON_INTERACTIVE'}
    assert env['HOME'] == env['CODEX_HOME'] == str(stage / packages.REFERENCE / 'package-home')
    assert env['CODEX_NON_INTERACTIVE'] == '1'
    before = snapshot(root)
    proof = packages.verify_packages(stage, OPERATION, values, SOURCE, receipt, execute=runtime)
    assert proof['treeSha256'] == proof['referenceTreeSha256'] == receipt['payloadTreeSha256']
    assert proof['comparison'] == 'exact-payload' and proof['equivalenceSha256'] == proof['treeSha256']
    assert snapshot(root) == before


def history_distribution(prepared, monkeypatch):
    """Simulate the qualified writer; the actual public SHA is checked on host."""
    root, stage, values, receipt, calls = prepared
    monkeypatch.setattr(packages, 'SELECTION_HISTORY_INSTALLER_SHA256', receipt['installerSha256'])
    reference = stage / packages.REFERENCE / 'package-home'
    live = Path(values['relay_codex_package_home'])
    for home, identity in [(reference, b'1 11 1790000000.123456789'), (live, b'2 22 1790000001.987654321')]:
        standalone = home / 'packages/standalone'
        (standalone / 'current').symlink_to('releases/0.167.2-test-linux')
        history = standalone / 'selection-history'
        history.write_bytes(b'0.167.2-test-linux\n\n' + identity + b'\n')
        history.chmod(0o644)
    receipt = {**receipt, 'payloadTreeSha256': packages._tree(reference / 'packages')}
    return root, stage, values, receipt, reference, live


def test_only_qualified_history_kernel_identity_is_equivalent_and_never_rewritten(prepared, monkeypatch):
    root, stage, values, receipt, reference, live = history_distribution(prepared, monkeypatch)
    before = snapshot(root)
    proof = packages.verify_packages(stage, OPERATION, values, SOURCE, receipt, execute=runtime)
    assert proof['comparison'] == 'selection-history-kernel-identity-v1'
    assert proof['treeSha256'] != proof['referenceTreeSha256'] == receipt['payloadTreeSha256']
    assert proof['equivalenceSha256'] not in [proof['treeSha256'], proof['referenceTreeSha256']]
    actual = live / 'packages/standalone/selection-history'
    assert proof['selectionHistory']['live']['historyRow'][3] == hashlib.sha256(actual.read_bytes()).hexdigest()
    assert proof['selectionHistory']['live']['currentIdentity'] == packages._stamp(
        (live / 'packages/standalone/current').lstat())
    assert snapshot(root) == before


@pytest.mark.parametrize('body', [
    b'0.167.2-test-linux\n\n1 2 3.000000000\nextra\n',
    b'0.167.2-test-linux\n\n1 2 3.000000000',
    b'0.167.2-test-linux\r\n\r\n1 2 3.000000000\r\n',
    b'other-release\n\n1 2 3.000000000\n',
    b'0.167.2-test-linux\nprevious-release\n1 2 3.000000000\n',
    b'0.167.2-test-linux\n../escape\n1 2 3.000000000\n',
    b'0.167.2-test-linux\n\ntrue 2 3.000000000\n',
    b'0.167.2-test-linux\n\n-1 2 3.000000000\n',
    b'0.167.2-test-linux\n\n1 0 3.000000000\n',
    b'0.167.2-test-linux\n\n1 2 3.00\n',
    b'0.167.2-test-linux\n\n1 2 3.000000000 extra\n',
    b'0.167.2-test-linux\n\n1 2 3.000000000\xff\n',
])
def test_history_schema_and_first_two_lines_are_not_ignored(prepared, monkeypatch, body):
    _, stage, values, receipt, _reference, live = history_distribution(prepared, monkeypatch)
    (live / 'packages/standalone/selection-history').write_bytes(body)
    with pytest.raises(ValueError):
        packages.verify_packages(stage, OPERATION, values, SOURCE, receipt, execute=runtime)


@pytest.mark.parametrize('change', ['mode', 'owner', 'symlink', 'hardlink', 'extra-payload',
                                  'current-target', 'unknown-installer'])
def test_history_exception_preserves_all_other_owner_and_payload_checks(prepared, monkeypatch, change):
    _, stage, values, receipt, _reference, live = history_distribution(prepared, monkeypatch)
    history = live / 'packages/standalone/selection-history'
    if change == 'mode': history.chmod(0o755)
    elif change == 'owner': os.chown(history, 9999, 9999)
    elif change == 'symlink':
        history.unlink(); history.symlink_to('releases/0.167.2-test-linux/resource')
    elif change == 'hardlink': os.link(history, history.with_name('another-history'))
    elif change == 'extra-payload':
        (live / 'packages/standalone/releases/0.167.2-test-linux/resource').write_bytes(b'different official resource')
    elif change == 'current-target':
        current = live / 'packages/standalone/current'
        current.unlink(); current.symlink_to('releases/0.167.2-test-linux/resource')
    else: monkeypatch.setattr(packages, 'SELECTION_HISTORY_INSTALLER_SHA256', '0' * 64)
    with pytest.raises(ValueError):
        packages.verify_packages(stage, OPERATION, values, SOURCE, receipt, execute=runtime)


def test_history_and_current_identity_remain_bound_across_operation_proofs(prepared, monkeypatch):
    _, stage, values, receipt, _reference, live = history_distribution(prepared, monkeypatch)
    before = packages.verify_packages(stage, OPERATION, values, SOURCE, receipt, execute=runtime)
    current = live / 'packages/standalone/current'
    target = os.readlink(current)
    current.unlink(); current.symlink_to(target)
    after = packages.verify_packages(stage, OPERATION, values, SOURCE, receipt, execute=runtime)
    assert before['treeSha256'] == after['treeSha256']
    assert before['equivalenceSha256'] == after['equivalenceSha256']
    assert before['selectionHistory']['live']['currentIdentity'] != after['selectionHistory']['live']['currentIdentity']
    history = live / 'packages/standalone/selection-history'
    history.write_bytes(b'0.167.2-test-linux\n\n3 33 1790000002.000000000\n')
    changed = packages.verify_packages(stage, OPERATION, values, SOURCE, receipt, execute=runtime)
    assert changed['treeSha256'] != after['treeSha256']
    assert changed['equivalenceSha256'] == after['equivalenceSha256']
    assert changed['selectionHistory']['live']['historyRow'] != after['selectionHistory']['live']['historyRow']


@pytest.mark.parametrize('change', ['history', 'current'])
def test_history_or_same_target_alias_change_during_probes_is_refused(prepared, monkeypatch, change):
    _, stage, values, receipt, _reference, live = history_distribution(prepared, monkeypatch)
    def mutate(argv, *, env, cwd):
        if change == 'history':
            (live / 'packages/standalone/selection-history').write_bytes(b'0.167.2-test-linux\n\n4 44 1790000003.000000000\n')
        else:
            current = live / 'packages/standalone/current'
            target = os.readlink(current)
            current.unlink(); current.symlink_to(target)
        return runtime(argv, env=env, cwd=cwd)
    with pytest.raises(ValueError, match='SOURCE_UPGRADE_CODEX_MOVED'):
        packages.verify_packages(stage, OPERATION, values, SOURCE, receipt, execute=mutate)


@pytest.mark.parametrize('change', ['live-byte', 'aux-resource', 'extra', 'removed', 'mode', 'owner',
                                  'hardlink', 'escape', 'reference-byte', 'installer', 'operation', 'receipt'])
def test_payload_drift_never_passes_on_version_alone(prepared, change):
    root, stage, values, receipt, _ = prepared
    release = Path(values['relay_codex_package_home']) / 'packages/standalone/releases/0.167.2-test-linux'
    if change == 'live-byte': (release / 'bin/codex').write_text('#!/bin/sh\nprintf "codex-cli 0.167.2\\n"\n# tampered\n')
    elif change == 'aux-resource': (release / 'resource').write_bytes(b'changed auxiliary bytes')
    elif change == 'extra': (release / 'extra').write_bytes(b'unexpected bytes')
    elif change == 'removed': (release / 'resource-link').unlink()
    elif change == 'mode': (release / 'resource').chmod(0o666)
    elif change == 'owner': os.chown(release / 'resource', 9999, 9999)
    elif change == 'hardlink': os.link(release / 'resource', release / 'alias')
    elif change == 'escape':
        (release / 'resource-link').unlink(); (release / 'resource-link').symlink_to('/etc/passwd')
    elif change == 'reference-byte': (stage / packages.REFERENCE / 'package-home/packages/standalone/releases/0.167.2-test-linux/resource').write_bytes(b'changed reference')
    elif change == 'installer': (stage / packages.REFERENCE / 'installer.sh').write_bytes(b'changed installer')
    elif change == 'operation': receipt = {**receipt, 'operation': 'other operation'}
    else: receipt = {**receipt, 'payloadTreeSha256': '0' * 64}
    with pytest.raises(ValueError):
        packages.verify_packages(stage, OPERATION, values, SOURCE, receipt, execute=runtime)


def test_verifier_does_not_create_missing_reference(prepared):
    root, stage, values, receipt, _ = prepared
    shutil.rmtree(stage / packages.REFERENCE)
    before = snapshot(root)
    with pytest.raises((ValueError, OSError)):
        packages.verify_packages(stage, OPERATION, values, SOURCE, receipt, execute=runtime)
    assert snapshot(root) == before and not (stage / packages.REFERENCE).exists()


@pytest.mark.parametrize('failed', range(4))
def test_each_real_tool_version_probe_is_required(prepared, failed):
    _, stage, values, receipt, _ = prepared
    def bad(argv, *, env, cwd):
        lines = runtime(argv, env=env, cwd=cwd).stdout.splitlines()
        lines[failed] = b'incorrect-tool-version-output'
        return SimpleNamespace(returncode=int(failed == 3), stdout=b'\n'.join(lines))
    with pytest.raises(ValueError, match='SOURCE_UPGRADE_TOOLCHAIN_RUNTIME_UNPROVEN'):
        packages.verify_packages(stage, OPERATION, values, SOURCE, receipt, execute=bad)


@pytest.mark.parametrize('tool,index', [('cargo', 1), ('rustc', 2)])
def test_rust_tool_name_with_wrong_pinned_version_is_refused(prepared, tool, index):
    _, stage, values, receipt, _ = prepared
    def wrong_version(argv, *, env, cwd):
        lines = runtime(argv, env=env, cwd=cwd).stdout.splitlines()
        lines[index] = (tool + ' 1.89.0 (same-tool-name-wrong-version)').encode()
        return SimpleNamespace(returncode=0, stdout=b'\n'.join(lines))
    with pytest.raises(ValueError, match='SOURCE_UPGRADE_TOOLCHAIN_RUNTIME_UNPROVEN'):
        packages.verify_packages(stage, OPERATION, values, SOURCE, receipt, execute=wrong_version)


def test_actual_runtime_version_outputs_are_retained_in_proof(prepared):
    _, stage, values, receipt, _ = prepared
    before = packages.verify_packages(stage, OPERATION, values, SOURCE, receipt, execute=runtime)
    def changed_build(argv, *, env, cwd):
        result = runtime(argv, env=env, cwd=cwd)
        return SimpleNamespace(returncode=0, stdout=result.stdout.replace(b'rustfmt 1.8.0', b'rustfmt 1.8.1'))
    after = packages.verify_packages(stage, OPERATION, values, SOURCE, receipt, execute=changed_build)
    assert before['runtimeVersions'] != after['runtimeVersions']


def test_payload_changes_during_runtime_probe_are_refused(prepared):
    _, stage, values, receipt, _ = prepared
    def mutate(argv, *, env, cwd):
        (Path(values['relay_codex_package_home']) / 'packages/changed-during-probe').write_bytes(b'drift')
        return runtime(argv, env=env, cwd=cwd)
    with pytest.raises(ValueError, match='SOURCE_UPGRADE_CODEX_MOVED'):
        packages.verify_packages(stage, OPERATION, values, SOURCE, receipt, execute=mutate)


@pytest.mark.parametrize('change', ['mode', 'group', 'link', 'binary-link'])
def test_entire_rust_prefix_metadata_is_checked_before_executing(prepared, change):
    _, stage, values, receipt, _ = prepared
    root = Path(values['relay_rust_toolchain_root'])
    if change == 'mode': (root / 'support-library').chmod(0o666)
    elif change == 'group': os.chown(root / 'support-library', 0, 9999)
    elif change == 'link': (root / 'escape').symlink_to('/etc/passwd')
    else:
        (root / 'bin/cargo').unlink(); (root / 'bin/cargo').symlink_to('../support-library')
    def forbidden(*args, **kwargs):
        raise AssertionError('runtime execution preceded the complete metadata check')
    with pytest.raises(ValueError):
        packages.verify_packages(stage, OPERATION, values, SOURCE, receipt, execute=forbidden)


def test_rust_changes_between_proof_phases_are_visible(prepared):
    _, stage, values, receipt, _ = prepared
    before = packages.verify_packages(stage, OPERATION, values, SOURCE, receipt, execute=runtime)
    (Path(values['relay_rust_toolchain_root']) / 'support-library').write_bytes(b'updated protected root library')
    after = packages.verify_packages(stage, OPERATION, values, SOURCE, receipt, execute=runtime)
    assert before['rustMetadataSha256'] != after['rustMetadataSha256']


@pytest.mark.parametrize('field,value', [('schemaVersion', True), ('payloadTreeSha256', None), ('installerSha256', 7)])
def test_reference_receipt_types_are_strict(prepared, field, value):
    _, stage, values, receipt, _ = prepared
    with pytest.raises(ValueError, match='SOURCE_UPGRADE_CODEX_REFERENCE_BINDING'):
        packages.verify_packages(stage, OPERATION, values, SOURCE, {**receipt, field: value}, execute=runtime)
def test_official_download_matches_ordinary_get_url_agent_without_changing_tls(monkeypatch):
    from ansible.module_utils.urls import url_argument_spec
    class Response:
        url = packages.INSTALLER_URL
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self, limit):
            assert limit == 1048577
            return b'#!/bin/sh\n'
    calls = []
    def urlopen(request, **kwargs):
        assert request.full_url == packages.INSTALLER_URL
        assert request.get_header('User-agent') == url_argument_spec()['http_agent']['default']
        assert kwargs == {'timeout': 30}  # No unverified TLS context or auth.
        calls.append(request)
        return Response()
    monkeypatch.setattr(packages.urllib.request, 'urlopen', urlopen)
    assert packages._download(packages.INSTALLER_URL) == b'#!/bin/sh\n'
    assert len(calls) == 1
