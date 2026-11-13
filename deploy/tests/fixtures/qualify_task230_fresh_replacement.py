#!/usr/bin/env python3
"""Probe supported expert replacement of an actual incomplete TEST installation.

Uses the existing offline backend fixture, real public CLI, Ansible and systemd.
External GitHub responses and Runner/Codex distributions remain synthetic. A
failed reinstall is retained for diagnosis; no recovery state is cleared and no
activation is attempted after a failed operation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def files(root):
    return {str(path.relative_to(root)): ('link:' + os.readlink(path) if path.is_symlink() else digest(path))
            for path in sorted(root.rglob('*')) if path.is_file() or path.is_symlink()}


def command(argv, *, cwd, check=True):
    result = subprocess.run(list(map(str, argv)), cwd=cwd, capture_output=True,
        text=True, timeout=3600, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
    if check and result.returncode:
        raise AssertionError('Qualification command failed; inspect retained phase logs')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--isolated-disposable-container', action='store_true', required=True)
    parser.add_argument('--fixture-root', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--expected-revision', required=True)
    args = parser.parse_args()
    assert os.geteuid() == 0 and Path('/.dockerenv').exists()
    assert {path.name for path in Path('/sys/class/net').iterdir()} == {'lo'}
    root, source = args.fixture_root.resolve(strict=True), args.source_root.resolve(strict=True)
    assert root.parent == Path('/qualification') and root.name.startswith('task230-public-cli-')
    assert source.is_relative_to(Path('/qualification')) and (source / '.git').is_dir()
    revision = command(['git', 'rev-parse', 'HEAD'], cwd=source).stdout.strip()
    assert revision == args.expected_revision and re.fullmatch('[0-9a-f]{40}', revision)
    assert not command(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=source).stdout
    config_path = root / 'consumer/relay.json'
    config = json.loads(config_path.read_text())
    namespace = config['environment']['namespace']
    assert re.fullmatch(r'(?:task230|t230)-[a-z0-9-]{1,14}', namespace)
    assert config['consumer']['generalRunnerPool']['desiredCapacity'] == 6
    install = Path('/opt') / namespace
    release = (install / 'current').resolve(strict=True)
    assert release.parent == install / 'releases'
    old = release.name
    manifest_path = release / 'artifact-manifest.json'
    original_manifest = manifest_path.read_bytes()
    manifest = json.loads(original_manifest)
    assert manifest['installationState']['stage'] == 'fresh-incomplete'
    assert old != revision and manifest['commit'] == old
    old_source = release / 'reviewed-source'
    fixture = old_source / 'controller/test/fixtures/historical-runtime/3f4d4348cfb05866b2108eadcc35b7a17153ff14.json'
    assert fixture.stat().st_size == 1065228
    gate = json.loads(command([install / 'relay-admission', 'status'], cwd=source).stdout)
    assert gate['phase'] == 'open' and not gate.get('active') and not gate.get('unknown')
    assert not list(install.rglob('.runner')), 'Replacement scenario requires no namespace registration'
    pool = Path('/opt/codex-relay-pools') / config['environment']['generalRunner']['name']
    assert not list(pool.rglob('.runner')), 'Replacement scenario requires no shared pool registration'
    reviewer = namespace + '-reviewer.service'
    assert command(['systemctl', 'is-active', reviewer], cwd=source, check=False).stdout.strip() == 'inactive'
    protected = Path('/etc') / namespace
    # Hash credential bytes only; never write secret contents to evidence.
    credentials = {str(path): digest(path) for path in protected.rglob('*')
        if path.is_file() and not path.is_symlink()
        and any(part in {'reviewer-credentials', 'writer-credentials', 'codex-credentials', 'credentials', 'certs'}
                for part in path.parts)}
    claim = Path(config['consumer']['paths']['claimRoot'])
    history = {str(path): digest(path) for path in claim.rglob('*.json')
        if path.is_file() and not path.name.startswith('admission-')}
    source_before = files(release)
    foreign = config['environment']['ingress']['service']
    assert foreign == namespace + '-test-ingress.service'
    stamp_args = ['systemctl', 'show', foreign, '-p', 'MainPID', '-p', 'ExecMainStartTimestampMonotonic']
    foreign_before = command(stamp_args, cwd=source).stdout
    assert 'MainPID=0\n' not in foreign_before
    evidence = Path(tempfile.mkdtemp(prefix='replacement-evidence-', dir=root))
    report = {'status': 'RUNNING', 'originalProduct': old, 'replacementProduct': revision,
        'originalManifestSha256': hashlib.sha256(original_manifest).hexdigest(),
        'externalRegistration': 'synthetic-offline', 'phases': {},
        'originalInstallationState': manifest['installationState']}
    (evidence / 'original-manifest.json').write_bytes(original_manifest)
    fixture_report = json.loads((root / 'report.json').read_text())
    fixture_report.update(sourceRoot=str(source), sourceFixtureRevision=revision,
                          replacementOriginalSourceRoot=str(old_source))
    (root / 'report.json').write_text(json.dumps(fixture_report, indent=2) + '\n')
    backend = source / 'deploy/tests/fixtures/qualify_task230_backend.py'
    common = [sys.executable, backend, '--isolated-disposable-container', '--fixture-root', root,
        '--config', config_path, '--consumer-root', root / 'consumer', '--resolved-revision', revision,
        '--connection', 'local', '--log-root', evidence / 'logs']

    def phase(name, *options):
        result = command([*common, '--phase', name, *options], cwd=source, check=False)
        (evidence / (name + '.stdout')).write_text(result.stdout)
        (evidence / (name + '.stderr')).write_text(result.stderr)
        report['phases'][name] = {'exit': result.returncode}
        assert result.returncode == 0, 'Public phase failed: ' + name
        return result

    try:
        phase('workflow-project', '--authorize-workflow-projection')
        command(['git', 'add', '--', '.'], cwd=root / 'consumer')
        changed = command(['git', 'diff', '--cached', '--quiet'], cwd=root / 'consumer', check=False)
        assert changed.returncode in [0, 1]
        if changed.returncode == 1:
            command(['git', '-c', 'user.name=isolated-test', '-c', 'user.email=test@example.invalid',
                     'commit', '-qm', 'Review exact TEST replacement workflow projection'], cwd=root / 'consumer')
        phase('workflow-verify')
        phase('reinstall', '--authorize-reinstall')
        archive = install.parent / ('.' + namespace + '-retired-' + old + '-' + revision)
        archived_release = archive / 'runtime/releases' / old
        assert files(archived_release) == source_before, 'Replacement altered retired release bytes'
        assert (archived_release / 'artifact-manifest.json').read_bytes() == original_manifest
        assert all(Path(path).is_file() and digest(Path(path)) == value for path, value in credentials.items())
        assert all(Path(path).is_file() and digest(Path(path)) == value for path, value in history.items())
        assert command(stamp_args, cwd=source).stdout == foreign_before
        phase('activate', '--authorize-reviewer-activation')
        phase('runner-register', '--authorize-runner-register',
              '--runner-registration-token', 'synthetic-offline-production-registration')
        phase('runner-enable', '--authorize-runner-enable')
        phase('apply')
        phase('post-check')
        result = phase('install')
        report['ordinaryInstallResult'] = json.loads(result.stdout.split('RELAY_INSTALL_RESULT=')[-1].splitlines()[0])
        report['finalInstallationState'] = json.loads((install / 'current/artifact-manifest.json').read_text()).get('installationState')
        assert files(archived_release) == source_before, 'Completion altered retired release bytes'
        assert all(Path(path).is_file() and digest(Path(path)) == value for path, value in credentials.items())
        assert all(Path(path).is_file() and digest(Path(path)) == value for path, value in history.items())
        assert command(stamp_args, cwd=source).stdout == foreign_before
        report.update(status='PASS', archive=str(archive), operationalPostCheck=True,
            incompleteOriginalPairPreserved=True,
            limitation='Expert replacement operational proof does not establish a fresh ready marker')
    except Exception as error:
        report.update(status='FAIL', failure=str(error),
            limitation='Retained failed operation requires diagnosis; no continuation or state clearing attempted')
        raise
    finally:
        (evidence / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
