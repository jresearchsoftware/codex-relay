"""Read-only upgrade gate: retain one proven installation and its owner intent."""
import hashlib
import json
from pathlib import Path
import re
import stat
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


def verify_desired(install_root, config_root, target_revision, expected_installed, *,
                   owner_uid=0, boundary=Path('/'), expected_config=None, resource_probe=None):
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
    if actual != 'none' and expected_config is not None:
        namespace = expected_config['environment']['namespace']
        if (install != boundary / 'opt' / namespace
                or Path(config_root) != boundary / 'etc' / namespace):
            raise ValueError('REINSTALL_RESOURCE_MIGRATION_UNSUPPORTED')
        proof = resource_probe or globals().get('prove_git_resources')
        if not callable(proof):
            raise ValueError('RELAY_INSTALL_RESOURCE_PROOF_UNAVAILABLE')
        proof(expected_config, root=boundary, owner_uid=owner_uid)
    config_root = Path(config_root)
    if config_root.exists() or config_root.is_symlink():
        protected(config_root, directory=True, **protection)
        consumer = config_root / 'consumer.json'
        if consumer.exists() or consumer.is_symlink():
            protected(consumer, **protection)
            if not isinstance(json.loads(consumer.read_text()), dict):
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
        # A separately reserved SERIAL transition may change only the selected
        # pool topology. Ordinary upgrades retain their original exact gate.
        receipt_path = config_root / 'serial-pool-compat-v1.json'
        state_path = Path(installed_config['consumer']['paths']['claimRoot']) / 'serial-pool-transition-v1.json'
        if not receipt_path.exists() or not state_path.exists():
            raise ValueError('RELAY_UPGRADE_OWNER_INTENT_CHANGED')
        for path in [receipt_path, state_path]:
            protected(path, **protection)
        receipt_raw = receipt_path.read_bytes()
        receipt = json.loads(receipt_raw)
        state = json.loads(state_path.read_bytes())
        prospective = json.dumps(expected_config, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
        if (state.get('phase') not in ['stopped', 'target-ready', 'remove-intent', 'retired']
                or state.get('targetRevision') != expected_config['source']['revision']
                and expected_config['source']['revision'] != 'main'
                or state.get('receiptSha256') != hashlib.sha256(receipt_raw).hexdigest()
                or state.get('plan', {}).get('targetConfigSha256') != hashlib.sha256(prospective).hexdigest()
                or receipt.get('original', {}).get('revision') != release.name
                or receipt.get('original', {}).get('configSha256') != hashlib.sha256(snapshot).hexdigest()
                or receipt.get('original', {}).get('consumerSha256') != hashlib.sha256(consumer_path.read_bytes()).hexdigest()
                or receipt.get('operationId') != state.get('operationId')
                or receipt.get('namespace') != installed_config['environment']['namespace']
                or receipt.get('repository') != expected_config['environment'].get('repository', expected_config['consumer'].get('repository'))):
            raise ValueError('RELAY_UPGRADE_OWNER_INTENT_CHANGED')
    return release.name


if __name__ == '__main__':
    try:
        if len(sys.argv) == 6 and sys.argv[1] == '--git-desired':
            revision = verify_desired(*sys.argv[2:], expected_config=json.load(sys.stdin))
        elif len(sys.argv) in [3, 4]:
            revision = (verify_apply(sys.argv[1], sys.argv[3]) if len(sys.argv) == 4 else
                        verify(sys.argv[1], sys.argv[2], json.load(sys.stdin)))
        else:
            raise ValueError('RELAY_UPGRADE_INPUT_INVALID')
    except (ValueError, OSError, TypeError, KeyError, AttributeError):
        # Never include private configuration, credentials or remote content.
        print('RELAY_UPGRADE_PREFLIGHT_BLOCKED;inspect-installed-identity-and-owner-intent', file=sys.stderr)
        sys.exit(1)
    print('RELAY_UPGRADE_SOURCE_VALIDATED=' + revision)
