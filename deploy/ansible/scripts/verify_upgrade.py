"""Read-only upgrade gate: retain one proven installation and its owner intent."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys


def protected(path, *, directory=False, owner_uid=0, boundary=Path('/')):
    if not path.is_relative_to(boundary):
        raise ValueError('RELAY_UPGRADE_UNSAFE_PATH')
    current = path
    first = True
    while True:
        metadata = current.lstat()
        kind = stat.S_ISDIR if not first or directory else stat.S_ISREG
        if (metadata.st_uid != owner_uid or metadata.st_mode & 0o022
                or not kind(metadata.st_mode) or first and not directory and metadata.st_nlink != 1):
            raise ValueError('RELAY_UPGRADE_UNSAFE_PATH')
        if current == boundary:
            break
        first = False
        current = current.parent


def installed_identity(install, *, owner_uid=0, boundary=Path('/')):
    protection = {'owner_uid': owner_uid, 'boundary': boundary}
    protected(install, directory=True, **protection)
    current = install / 'current'
    metadata = current.lstat()
    if not stat.S_ISLNK(metadata.st_mode) or metadata.st_uid != owner_uid:
        raise ValueError('RELAY_UPGRADE_INSTALLED_IDENTITY_UNPROVEN')
    release = current.resolve(strict=True)
    revision = release.name
    if release.parent != install / 'releases' or not re.fullmatch('[0-9a-f]{40}', revision):
        raise ValueError('RELAY_UPGRADE_INSTALLED_IDENTITY_UNPROVEN')
    protected(release, directory=True, **protection)
    manifest_path = release / 'artifact-manifest.json'
    identity_path = release / 'reviewed-source/.relay-source.json'
    for path in [manifest_path, identity_path]:
        protected(path, **protection)
    manifest = json.loads(manifest_path.read_text())
    identity = json.loads(identity_path.read_text())
    if (not isinstance(manifest, dict) or not isinstance(identity, dict)
            or any(manifest.get(key) != revision for key in ['commit', 'installedRevision', 'resolvedRevision'])
            or identity.get('revision') != revision or manifest.get('gitTree') != identity.get('tree')
            or not re.fullmatch('[0-9a-f]{40}', identity.get('tree', ''))):
        raise ValueError('RELAY_UPGRADE_INSTALLED_IDENTITY_UNPROVEN')
    return release, manifest


def verify_apply(install_root, target_revision, *, owner_uid=0, boundary=Path('/')):
    if not re.fullmatch('[0-9a-f]{40}', target_revision):
        raise ValueError('RELAY_APPLY_TARGET_INVALID')
    install = Path(install_root)
    if not install.exists() and not install.is_symlink():
        protected(install.parent, directory=True, owner_uid=owner_uid, boundary=boundary)
        return 'none'
    protected(install, directory=True, owner_uid=owner_uid, boundary=boundary)
    current = install / 'current'
    if not current.exists() and not current.is_symlink():
        return 'none'
    release, _ = installed_identity(install, owner_uid=owner_uid, boundary=boundary)
    if release.name != target_revision:
        raise ValueError('RELAY_APPLY_REVISION_CHANGE_REQUIRES_EXPLICIT_UPGRADE')
    return release.name


def authenticated_consumer_baseline(install, config_root, target_revision, context, *, owner_uid=0, boundary=Path('/')):
    """Reprove only the private clone authenticated by the actual history gate.

    The caller's root orchestration obtained this context from the native Node
    preflight. No ordinary loader, live config or retained record is replaced.
    """
    protection = {'owner_uid': owner_uid, 'boundary': boundary}
    stage, baseline = Path(context['stageRoot']), Path(context['consumerPath'])
    if (stage.parent not in (install / 'releases', install.parent / ('.' + install.name + '-staging'))
            or not re.fullmatch(r'[.]stage-[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', stage.name)
            or baseline.parent.parent != stage or baseline.name != 'consumer.json'
            or not re.fullmatch('consumer-context-[A-Za-z0-9]{6}', baseline.parent.name)
            or not re.fullmatch('[a-f0-9]{64}', context.get('baselineDigest', ''))):
        raise ValueError('RELAY_INSTALL_BASELINE_BINDING_UNPROVEN')
    for directory in (stage, baseline.parent):
        protected(directory, directory=True, **protection)
        if stat.S_IMODE(directory.stat().st_mode) != 0o700:
            raise ValueError('RELAY_INSTALL_BASELINE_BINDING_UNPROVEN')
    protected(baseline, **protection)
    if baseline.stat().st_size > 128 * 1024:
        raise ValueError('RELAY_INSTALL_BASELINE_BINDING_UNPROVEN')
    raw = baseline.read_bytes()
    actual = json.loads(raw)
    claim = Path(context['claimRoot'])
    if (not isinstance(actual, dict) or not claim.is_absolute() or str(claim) != os.path.normpath(claim)
            or actual.get('paths', {}).get('claimRoot') != str(claim)):
        raise ValueError('RELAY_INSTALL_BASELINE_BINDING_UNPROVEN')
    source = stage / 'release/reviewed-source'
    for path in (source / '.relay-source.json', source / 'consumer/consumer-config.mjs'):
        protected(path, **protection)
    if json.loads((source / '.relay-source.json').read_bytes()).get('revision') != target_revision:
        raise ValueError('RELAY_INSTALL_BASELINE_BINDING_UNPROVEN')
    program = ('import{readFileSync}from"node:fs";import{pathToFileURL}from"node:url";'
               'const m=await import(pathToFileURL(process.argv[1]));'
               'const c=m.validateConsumer(m.parseConsumerJson(readFileSync(process.argv[2],"utf8")));'
               'console.log(JSON.stringify({digest:m.consumerDigest(c),claimRoot:c.paths.claimRoot}));')
    result = subprocess.run(['/usr/bin/node', '--input-type=module', '-e', program,
        str(source / 'consumer/consumer-config.mjs'), str(baseline)], stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=30,
        env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'})
    if (result.returncode or len(result.stdout) > 4096
            or json.loads(result.stdout) != {'digest': context['baselineDigest'], 'claimRoot': str(claim)}
            or baseline.read_bytes() != raw):
        raise ValueError('RELAY_INSTALL_BASELINE_BINDING_UNPROVEN')
    receipt = Path(config_root) / 'serial-pool-compat-v1.json'
    paired = receipt.exists() or receipt.is_symlink()
    if paired:
        protected(receipt, **protection)
    gate_path = boundary / claim.relative_to('/') / ('admission-pool-v1.json' if paired else 'admission-v1.json')
    protected(gate_path, **protection)
    if gate_path.stat().st_size > 4096 or stat.S_IMODE(gate_path.stat().st_mode) != 0o600:
        raise ValueError('RELAY_INSTALL_BASELINE_GATE_UNPROVEN')
    gate = json.loads(gate_path.read_bytes())
    if (not isinstance(gate, dict) or set(gate) != {'version', 'consumerDigest', 'phase', 'operationId', 'target',
                                                  'previousActive', 'verifiedRevision'}
            or gate.get('version') != 1 or gate.get('consumerDigest') != context['baselineDigest']
            or gate.get('phase') not in ('open', 'quiesced', 'drained', 'applying', 'verified', 'recovery-required')):
        raise ValueError('RELAY_INSTALL_BASELINE_GATE_UNPROVEN')
    return actual


def verify_desired(install_root, config_root, target_revision, expected_installed, *,
                   owner_uid=0, boundary=Path('/'), expected_config=None, resource_probe=None,
                   consumer_baseline=None, consumer_resource_probe=None):
    """Bind the planner's observed installation without comparing desired intent.

    A reviewed Git change may replace an old profile, target set or snapshot.
    Current/source/manifest identity and actual filesystem protection still
    establish which installation this operation may reconcile or replace.
    """
    if (not re.fullmatch('[0-9a-f]{40}', target_revision or '')
            or expected_installed != 'none' and not re.fullmatch('[0-9a-f]{40}', expected_installed or '')):
        raise ValueError('RELAY_INSTALL_PLAN_INVALID')
    protection = {'owner_uid': owner_uid, 'boundary': boundary}
    install = Path(install_root)
    if not install.exists() and not install.is_symlink():
        protected(install.parent, directory=True, **protection)
        actual = 'none'
    else:
        protected(install, directory=True, **protection)
        current = install / 'current'
        if not current.exists() and not current.is_symlink():
            actual = 'none'
        else:
            release, _ = installed_identity(install, **protection)
            actual = release.name
    if actual != expected_installed:
        raise ValueError('RELAY_INSTALL_PLANNED_IDENTITY_CHANGED')
    if consumer_baseline is not None and actual == 'none':
        raise ValueError('RELAY_INSTALL_BASELINE_BINDING_UNPROVEN')
    baseline = (authenticated_consumer_baseline(install, config_root, target_revision, consumer_baseline,
                owner_uid=owner_uid, boundary=boundary) if consumer_baseline is not None else None)
    if actual != 'none' and expected_config is not None:
        namespace = expected_config['environment']['namespace']
        if (install != boundary / 'opt' / namespace
                or Path(config_root) != boundary / 'etc' / namespace):
            raise ValueError('REINSTALL_RESOURCE_MIGRATION_UNSUPPORTED')
        proof = (consumer_resource_probe or globals().get('prove_selected_resources') if baseline is not None
                 else resource_probe or globals().get('prove_git_resources'))
        if not callable(proof):
            raise ValueError('RELAY_INSTALL_RESOURCE_PROOF_UNAVAILABLE')
        if baseline is None:
            proof(expected_config, root=boundary, owner_uid=owner_uid)
        else:
            proof(expected_config, baseline, root=boundary, owner_uid=owner_uid)
    config_root = Path(config_root)
    if config_root.exists() or config_root.is_symlink():
        protected(config_root, directory=True, **protection)
        consumer = config_root / 'consumer.json'
        if consumer.exists() or consumer.is_symlink():
            protected(consumer, **protection)
            if baseline is None and not isinstance(json.loads(consumer.read_text()), dict):
                raise ValueError('RELAY_INSTALL_ACTUAL_CONSUMER_INVALID')
        elif baseline is not None:
            raise ValueError('RELAY_INSTALL_ACTUAL_CONSUMER_INVALID')
    return actual


def verify(install_root, config_root, expected_config, *, owner_uid=0, boundary=Path('/')):
    protection = {'owner_uid': owner_uid, 'boundary': boundary}
    config_root = Path(config_root)
    protected(config_root, directory=True, **protection)
    release, manifest = installed_identity(Path(install_root), **protection)
    snapshot_path = release / 'deployment-config.json'
    consumer_path = config_root / 'consumer.json'
    for path in [snapshot_path, consumer_path]:
        protected(path, **protection)
    if stat.S_IMODE(snapshot_path.stat().st_mode) != 0o600:
        raise ValueError('RELAY_UPGRADE_CONFIG_UNPROVEN')
    snapshot = snapshot_path.read_bytes()
    if manifest.get('deploymentConfigSha256') != hashlib.sha256(snapshot).hexdigest():
        raise ValueError('RELAY_UPGRADE_CONFIG_UNPROVEN')
    installed_config = json.loads(snapshot)

    def intent(config):
        value = json.loads(json.dumps(config))
        value['source'].pop('revision', None)
        return value

    if (intent(installed_config) != intent(expected_config)
            or json.loads(consumer_path.read_text()) != expected_config['consumer']):
        raise ValueError('RELAY_UPGRADE_OWNER_INTENT_CHANGED')
    return release.name


if __name__ == '__main__':
    try:
        if len(sys.argv) >= 6 and sys.argv[1] == '--git-desired':
            import argparse
            parser = argparse.ArgumentParser(add_help=False)
            for name in ('install_root', 'config_root', 'target_revision', 'expected_installed'):
                parser.add_argument(name)
            for name in ('consumer-baseline', 'baseline-digest', 'claim-root', 'stage-root'):
                parser.add_argument('--' + name)
            arguments = vars(parser.parse_args(sys.argv[2:]))
            selected = [arguments.pop(key) for key in ('consumer_baseline', 'baseline_digest', 'claim_root', 'stage_root')]
            if any(value is not None for value in selected) and not all(value is not None for value in selected):
                raise ValueError('RELAY_INSTALL_BASELINE_BINDING_UNPROVEN')
            context = dict(zip(('consumerPath', 'baselineDigest', 'claimRoot', 'stageRoot'), selected)) if selected[0] else None
            revision = verify_desired(**arguments, expected_config=json.load(sys.stdin), consumer_baseline=context)
        elif len(sys.argv) in [3, 4]:
            revision = (verify_apply(sys.argv[1], sys.argv[3]) if len(sys.argv) == 4 else
                        verify(sys.argv[1], sys.argv[2], json.load(sys.stdin)))
        else:
            raise ValueError('RELAY_UPGRADE_INPUT_INVALID')
    except (ValueError, OSError, TypeError, KeyError, AttributeError, subprocess.SubprocessError):
        # Never include private configuration, credentials or remote content.
        print('RELAY_UPGRADE_PREFLIGHT_BLOCKED;inspect-installed-identity-and-owner-intent', file=sys.stderr)
        sys.exit(1)
    print('RELAY_UPGRADE_SOURCE_VALIDATED=' + revision)
