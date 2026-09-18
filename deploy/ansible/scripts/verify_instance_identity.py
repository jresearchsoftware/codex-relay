"""Read-only guard: never adopt another consumer's installed Reviewer or units."""
import json
from pathlib import Path
import sys


def verify(install_root, config_root, repository, units, systemd_root=Path('/etc/systemd/system'),
           reviewer_user=None):
    config_path = Path(config_root) / 'reviewer-mcp.json'
    if config_path.is_symlink():
        raise ValueError('RELAY_INSTANCE_CONFIG_UNSAFE')
    if config_path.exists():
        config = json.loads(config_path.read_text())
        if config.get('repository') != repository:
            raise ValueError('RELAY_INSTANCE_REPOSITORY_COLLISION')
    for name in units:
        path = systemd_root / name
        if path.is_symlink():
            raise ValueError('RELAY_INSTANCE_UNIT_UNSAFE')
        if not path.exists():
            continue
        content = path.read_text()
        if name.endswith('.timer'):
            owned = 'Unit=' + name.removesuffix('.timer') + '.service' in content.splitlines()
        else:
            owned = any(line.startswith('ExecStart=' + install_root + '/')
                        for line in content.splitlines())
        if not owned:
            raise ValueError('RELAY_INSTANCE_UNIT_COLLISION')
    for path in systemd_root.glob('*.service'):
        if path.name in units or path.is_symlink() or not path.is_file():
            continue
        lines = path.read_text().splitlines()
        starts = [line for line in lines if line.startswith('ExecStart=')]
        if not any('/reviewer-mcp-http ' in line for line in starts):
            continue
        if (any(line.startswith('ExecStart=' + install_root + '/') for line in starts)
                or reviewer_user and 'User=' + reviewer_user in lines):
            raise ValueError('RELAY_INSTANCE_REVIEWER_IDENTITY_COLLISION')


if __name__ == '__main__':
    try:
        verify(*sys.argv[1:4], sys.argv[5:], reviewer_user=sys.argv[4])
    except (OSError, ValueError, TypeError):
        # Config/unit contents can contain private data; never print them.
        print('RELAY_INSTANCE_IDENTITY_REJECTED', file=sys.stderr)
        sys.exit(1)
    print('RELAY_INSTANCE_IDENTITY_VALID')
