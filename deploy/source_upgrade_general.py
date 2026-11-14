"""Preserve an unchanged General component; never attest its startup cache.

General software/settings/units are not rewritten by a source-only promotion.
Its current protected inputs and complete process identity must stay unchanged
through that operation. Production's separate loaded-input history is untouched.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import ssl
import stat
import subprocess

import process_adoption as adoption


def require(value):
    if not value:
        raise ValueError('SOURCE_UPGRADE_GENERAL_CHANGED')


def _service(unit):
    state = adoption.service(unit)
    # systemctl may omit empty arrays even with --all. Read the actual typed
    # D-Bus property; only a successful empty a(sb) establishes no env files.
    def read(arguments):
        result = subprocess.run(['/bin/busctl', '--system', '--json=short', '--timeout=5s', *arguments],
                                capture_output=True, check=True, timeout=8)
        require(len(result.stdout) <= 16384)
        return json.loads(result.stdout)
    location = read(['call', 'org.freedesktop.systemd1', '/org/freedesktop/systemd1',
                     'org.freedesktop.systemd1.Manager', 'GetUnit', 's', unit])
    require(isinstance(location, dict) and location.get('type') == 'o'
            and isinstance(location.get('data'), list) and len(location['data']) == 1
            and isinstance(location['data'][0], str)
            and re.fullmatch('/org/freedesktop/systemd1/unit/[A-Za-z0-9_]+', location['data'][0]))
    result = read(['get-property', 'org.freedesktop.systemd1', location['data'][0],
                   'org.freedesktop.systemd1.Service', 'EnvironmentFiles'])
    require(isinstance(result, dict) and result.get('type') == 'a(sb)' and isinstance(result.get('data'), list))
    files = []
    for row in result['data']:
        require(isinstance(row, list) and len(row) == 2 and isinstance(row[0], str)
                and re.fullmatch('/[-A-Za-z0-9_./]+', row[0]) and '..' not in Path(row[0]).parts
                and type(row[1]) is bool)
        files.append(row[0] + ' (ignore_errors=' + ('yes' if row[1] else 'no') + ')')
    value = ' '.join(files)
    require('EnvironmentFiles' not in state or state['EnvironmentFiles'] == value)
    state['EnvironmentFiles'] = value
    adoption.service_environment_files(state)  # Exact same loaded-file grammar.
    return state


def _identity(info):
    return adoption.identity(info)


def _file(path, uid, *, device=None, inode=None, verified=None):
    """Current inode-bound bytes, without a Production startup-time assertion."""
    path = Path(path)
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_uid in [0, uid]
                and not before.st_mode & 0o022 and before.st_nlink == 1)
        if device is not None:
            major, minor = (int(part, 16) for part in device.split(':'))
            require(before.st_ino == int(inode) and os.major(before.st_dev) == major
                    and os.minor(before.st_dev) == minor)
        identity = _identity(before)
        previous = verified.get(str(path)) if verified is not None else None
        if previous is not None:
            # Reuse only bytes actually hashed earlier in THIS capture. Every
            # read still opens O_NOFOLLOW and checks the complete fresh FD/path
            # identity. A changed input refuses instead of refreshing the memo.
            require(previous['identity'] == identity)
            digest = previous['sha256']
        else:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        require(_identity(os.fstat(stream.fileno())) == _identity(before)
                and _identity(path.lstat()) == _identity(before))
    result = {'identity': identity, 'sha256': digest}
    if verified is not None and previous is None:
        verified[str(path)] = result
    return result


def _directory(path, uid, *, mutable_root=False):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(descriptor)
        require(stat.S_ISDIR(before.st_mode) and before.st_uid in [0, uid] and not before.st_mode & 0o022)
        names = sorted(os.listdir(descriptor))
        require(len(names) <= 20000 and _identity(os.fstat(descriptor)) == _identity(before)
                and _identity(Path(path).lstat()) == _identity(before))
        # General creates mutable diagnostics/work entries during normal use.
        # Only these two owner-defined classes are outside startup inputs.
        if mutable_root:
            names = [name for name in names if name not in ['_diag', '_work']]
        return {'identity': _identity(before), 'entries': names}
    finally:
        os.close(descriptor)


def _process(pid, uid, *, verified=None):
    root = Path('/proc', str(pid))
    before = root.joinpath('stat').read_text().rsplit(') ', 1)[1].split()[19]
    require(root.stat().st_uid == uid)
    maps, objects = {}, {}
    for row in root.joinpath('maps').read_text().splitlines():
        fields = row.split(None, 5)
        if len(fields) != 6 or not fields[5].startswith('/'):
            continue
        path = fields[5]
        if path.startswith('/memfd:doublemapper '):
            continue  # Existing .NET anonymous JIT class, not a disk dependency.
        require(not path.endswith(' (deleted)'))
        key = (fields[3], fields[4])
        require(path not in objects or objects[path] == key)
        if path not in maps:
            maps[path] = _file(path, uid, device=fields[3], inode=fields[4], verified=verified)
            objects[path] = key
    require(maps)
    result = {'pid': str(pid), 'uid': uid, 'start': before,
              'executable': adoption.digest(root.joinpath('exe').read_bytes()),
              'command': adoption.digest(root.joinpath('cmdline').read_bytes()),
              'environment': adoption.digest(adoption.canonical(adoption.environment(pid))), 'maps': maps}
    require(root.stat().st_uid == uid
            and root.joinpath('stat').read_text().rsplit(') ', 1)[1].split()[19] == before)
    return result


def _tree(path, uid, *, scope=None, verified=None):
    """Current complete tree, bounded links/topology and final movement check."""
    path = Path(path)
    scope = Path(scope) if scope is not None else path
    observed, visiting = {}, set()
    def visit(current):
        current = Path(current)
        require(current.is_relative_to(scope) and str(current) not in visiting and len(observed) < 20000)
        before = current.lstat()
        require(before.st_uid in [0, uid])
        visiting.add(str(current))
        if stat.S_ISLNK(before.st_mode):
            raw = os.readlink(current)
            target = Path(raw) if Path(raw).is_absolute() else current.parent / raw
            target = Path(os.path.normpath(target))
            require(target.is_relative_to(scope))
            value = {'identity': _identity(before), 'link': raw}
            # Validate every intervening target directory, never follow an
            # unchecked hidden directory redirect to some other namespace.
            for parent in [scope, *reversed(target.relative_to(scope).parents)]:
                actual = parent if parent == scope else scope / parent
                require(stat.S_ISDIR(actual.lstat().st_mode) and not actual.is_symlink()
                        and actual.lstat().st_uid in [0, uid] and not actual.lstat().st_mode & 0o022)
            if str(target) not in observed:
                visit(target)
        elif stat.S_ISDIR(before.st_mode):
            value = _directory(current, uid)
            for name in value['entries']:
                if str(current / name) not in observed:
                    visit(current / name)
        else:
            value = _file(current, uid, verified=verified)
        require(_identity(current.lstat()) == _identity(before))
        observed[str(current)] = value
        visiting.remove(str(current))
    visit(path)
    for name, value in observed.items():
        require(_identity(Path(name).lstat()) == value['identity'])
    return observed


def _trust_tree(path, uid, *, boundary=Path('/'), verified=None):
    """Current trust inputs, including absence; no loaded-cache-age claim."""
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts and path.is_relative_to(boundary))
    parents = {}
    for parent in adoption.trust_parents(path, boundary):
        if not os.path.lexists(parent):
            break
        meta = parent.lstat()
        require(stat.S_ISDIR(meta.st_mode) and meta.st_uid in [0, uid] and not meta.st_mode & 0o022)
        parents[str(parent)] = adoption.security_identity(meta)
    if not os.path.lexists(path):
        parent = path.parent
        while not os.path.lexists(parent): parent = parent.parent
        before = parent.lstat()
        require(stat.S_ISDIR(before.st_mode) and before.st_uid in [0, uid] and not before.st_mode & 0o022)
        return {'absent': True, 'parent': _identity(before), 'parents': parents}
    # Trust-store aliases legitimately cross /usr/lib/ssl -> /etc/ssl and
    # /etc/ssl/certs -> /usr/share. Their current protected targets are inputs.
    return {'parents': parents, 'tree': _tree(path, uid, scope=boundary, verified=verified)}


def _trust(processes, uid, *, verified=None):
    own = {row.split(None, 5)[5] for row in Path('/proc/self/maps').read_text().splitlines()
           if len(row.split(None, 5)) == 6 and '/libcrypto.so' in row.split(None, 5)[5]}
    require(len(own) == 1)
    crypto = next(iter(own))
    providers = {pid: [path for path in value['maps'] if '/libcrypto.so' in path]
                 for pid, value in processes.items()}
    selected = {pid: value for pid, value in processes.items() if providers[pid]}
    require(selected)
    defaults = ssl.get_default_verify_paths()
    output = {}
    for pid, value in selected.items():
        require(providers[pid] == [crypto]
                and value['maps'][crypto]['sha256'] == _file(crypto, 0, verified=verified)['sha256'])
        env = adoption.environment(pid)
        locations = adoption.trust_locations(env, defaults)
        home = env.get('HOME')
        require(isinstance(home, str) and home.startswith('/') and '..' not in Path(home).parts)
        locations.append(str(Path(home) / '.dotnet/corefx/cryptography/x509stores'))
        output[pid] = {path: _trust_tree(path, uid if path.startswith(home + '/') else 0, verified=verified)
                       for path in locations}
    return output


def capture_general(runner, source_root):
    """Current General component, to compare before/final/after source cutover."""
    require(runner.get('label', '').startswith('member-'))
    verified = {}  # Per invocation only; never retained, shared or persisted.
    uid = pwd.getpwnam(runner['user']).pw_uid
    require(uid != 0)
    state = _service(runner['service'])
    require(state['User'] == runner['user'])
    cgroup = Path('/sys/fs/cgroup') / state['ControlGroup'].lstrip('/') / 'cgroup.procs'
    members = adoption.cgroup_members(cgroup)
    require(state['MainPID'] in members)
    processes = {pid: _process(pid, uid, verified=verified) for pid in members}
    root = Path(runner['root'])
    topology = _directory(root, uid, mutable_root=True)
    require(all(name in topology['entries'] for name in ['.runner', '.credentials']))
    files = {}
    for name in topology['entries']:
        path = root / name
        if path.is_dir() and not path.is_symlink():
            require(name in ['bin', 'externals'] or re.fullmatch(r'(?:bin|externals)\.[0-9]+\.[0-9]+\.[0-9]+', name))
            continue
        if name in ['bin', 'externals']:
            continue  # Native version aliases are checked by runner_directory.
        require(not path.is_symlink())  # Fixed root interpreted files/settings.
        files[str(path)] = _file(path, uid, verified=verified)
    spec = importlib.util.spec_from_file_location('general_package_layout',
        Path(source_root) / 'deploy/ansible/roles/relay_runner/files/relay-intent-package.py')
    package = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(package)
    distribution = {}
    for name in ['bin', 'externals']:
        selected = package.runner_directory(root, name)
        require(selected is not None)
        if (root / name).is_symlink():
            files[str(root / name)] = {'identity': _identity((root / name).lstat()), 'link': os.readlink(root / name)}
        distribution[name] = _tree(selected, uid, verified=verified)
    units = {state['FragmentPath']: _file(state['FragmentPath'], 0, verified=verified)}
    for path in state['DropInPaths'].split():
        units[path] = _file(path, 0, verified=verified)
        units[str(Path(path).parent)] = _directory(Path(path).parent, 0)
    environment = {path: _file(path, 0, verified=verified) for path in adoption.service_environment_files(state)}
    trust = _trust(processes, uid, verified=verified)
    require(_directory(root, uid, mutable_root=True) == topology)
    require(adoption.cgroup_members(cgroup) == members)
    require({pid: _process(pid, uid, verified=verified) for pid in members} == processes)
    require(adoption.cgroup_members(cgroup) == members and _service(runner['service']) == state)
    # Repeat all selected inputs after the potentially long process/trust reads.
    for path, before in files.items():
        if 'link' in before:
            require(_identity(Path(path).lstat()) == before['identity'] and os.readlink(path) == before['link'])
        else:
            require(_file(path, uid, verified=verified) == before)
    require(all(_tree(package.runner_directory(root, name), uid, verified=verified) == before
                for name, before in distribution.items()))
    for path, before in units.items():
        require((_directory(path, 0) if 'entries' in before else _file(path, 0, verified=verified)) == before)
    require(all(_file(path, 0, verified=verified) == before for path, before in environment.items()))
    require(_trust(processes, uid, verified=verified) == trust)
    return {'service': state, 'processes': processes, 'root': topology, 'files': files,
            'distribution': distribution, 'units': units, 'environment': environment, 'trust': trust}
