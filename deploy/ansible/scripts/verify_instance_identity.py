"""Read-only guard: never adopt another consumer's installed Reviewer or units."""
import json
from pathlib import Path
import re
import sys


def repository_set(config):
    if not isinstance(config, dict) or ('repository' in config) == ('repositories' in config):
        raise ValueError('RELAY_INSTANCE_REPOSITORIES_INVALID')
    values = [config['repository']] if 'repository' in config else config['repositories']
    if not isinstance(values, list) or not values or not all(
        isinstance(value, str)
        and re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9_.-]{1,100}', value)
        and '--' not in value.split('/')[0] and value.split('/')[1] not in ['.', '..']
        for value in values
    ):
        raise ValueError('RELAY_INSTANCE_REPOSITORIES_INVALID')
    return set(values)


def general_pool_identity(pool):
    if pool is None:
        return None
    if (not isinstance(pool, dict) or set(pool) != {'name', 'runnerUser', 'root', 'service'}
            or not all(isinstance(value, str) for value in pool.values())
            or not re.fullmatch(r'[a-z][a-z0-9-]{0,54}', pool['name'])
            or not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', pool['runnerUser'])
            or pool['runnerUser'] == 'root'
            or pool['root'] != '/opt/codex-relay-pools/' + pool['name'] + '/runners/primary'
            or pool['service'] != pool['name'] + '-pool-1.service'):
        raise ValueError('RELAY_INSTANCE_POOL_BINDING_INVALID')
    return pool


def pool_unit_owned(content, pool):
    expected = {'User': pool['runnerUser'], 'Group': pool['runnerUser'],
                'WorkingDirectory': pool['root'], 'ExecStart': pool['root'] + '/run.sh'}
    section, observed = None, {}
    for row in content.splitlines():
        row = row.strip()
        if row.startswith('[') and row.endswith(']'):
            section = row[1:-1]
        elif section == 'Service' and '=' in row:
            key, value = (part.strip() for part in row.split('=', 1))
            if key in expected:
                if key in observed:
                    return False
                observed[key] = value
    return observed == expected


def parse_pool_argument(units):
    if '--general-pool' not in units:
        return units, None
    if len(units) < 2 or units[-2] != '--general-pool' or units.count('--general-pool') != 1:
        raise ValueError('RELAY_INSTANCE_POOL_BINDING_INVALID')
    return units[:-2], json.loads(units[-1])


def verify(install_root, config_root, repositories, units, systemd_root=Path('/etc/systemd/system'),
           reviewer_user=None, general_pool=None):
    pool = general_pool_identity(general_pool)
    if pool is not None and pool['service'] not in units:
        raise ValueError('RELAY_INSTANCE_POOL_BINDING_INVALID')
    expected = repository_set({'repository': repositories} if isinstance(repositories, str)
                              else {'repositories': repositories})
    config_path = Path(config_root) / 'reviewer-mcp.json'
    if config_path.is_symlink():
        raise ValueError('RELAY_INSTANCE_CONFIG_UNSAFE')
    if config_path.exists():
        config = json.loads(config_path.read_text())
        # Preserve the existing binding while permitting additional Reviewer
        # targets on the same instance, including legacy singleton upgrades.
        if not repository_set(config) <= expected:
            raise ValueError('RELAY_INSTANCE_REPOSITORY_COLLISION')
    for name in units:
        path = systemd_root / name
        if path.is_symlink():
            raise ValueError('RELAY_INSTANCE_UNIT_UNSAFE')
        if not path.exists():
            continue
        content = path.read_text()
        # Shared pool ownership is proved independently of a consumer namespace.
        if pool is not None and name == pool['service']:
            owned = pool_unit_owned(content, pool)
        elif name.endswith('.timer'):
            owned = 'Unit=' + name.removesuffix('.timer') + '.service' in content.splitlines()
        elif name.endswith('-relay-manual-outcome.socket'):
            namespace = Path(install_root).name
            owned = ('ListenStream=/run/' + namespace + '-manual-outcome.sock' in content.splitlines()
                     and 'Accept=yes' in content.splitlines())
        elif name.endswith('-relay-manual-outcome@.service'):
            owned = ('ExecStart=' + install_root + '/relay-manual-outcome-writer' in content.splitlines()
                     and 'User=root' in content.splitlines())
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
    for path in systemd_root.glob('*.socket'):
        if path.name in units or path.is_symlink() or not path.is_file():
            continue
        if 'ListenStream=/run/' + Path(install_root).name + '-manual-outcome.sock' in path.read_text().splitlines():
            raise ValueError('RELAY_INSTANCE_UNIT_COLLISION')


if __name__ == '__main__':
    try:
        repositories = json.loads(sys.argv[3]) if sys.argv[3].startswith('[') else sys.argv[3]
        units, general_pool = parse_pool_argument(sys.argv[5:])
        verify(*sys.argv[1:3], repositories, units, reviewer_user=sys.argv[4], general_pool=general_pool)
    except (OSError, ValueError, TypeError):
        # Config/unit contents can contain private data; never print them.
        print('RELAY_INSTANCE_IDENTITY_REJECTED', file=sys.stderr)
        sys.exit(1)
    print('RELAY_INSTANCE_IDENTITY_VALID')
