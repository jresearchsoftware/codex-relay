"""Transient, fail-closed loaded-process proof for one managed Apply.

No receipt/cache is written. The caller retains the ordinary admission and
operation locks. A missing or older Reviewer capability selects normal restart.
"""
import hashlib
import fcntl
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import pwd
import re
import socket
import stat
import struct
import subprocess
import sys
import time


def require(value):
    if not value:
        raise ValueError('PROCESS_ADOPTION_UNPROVEN')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def identity(meta):
    return (meta.st_dev, meta.st_ino, meta.st_size, meta.st_mtime_ns, meta.st_ctime_ns,
            meta.st_mode, meta.st_uid, meta.st_gid, meta.st_nlink)


def configuration(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result)
            result[key] = value
        return result
    value = json.loads(data, object_pairs_hook=unique)
    require(isinstance(value, dict) and isinstance(value.get('artifact'), dict))
    artifact = value['artifact']
    require(set(artifact) == {'commit', 'sha256'}
            and re.fullmatch('[0-9a-f]{40}', artifact['commit'])
            and re.fullmatch('[0-9a-f]{64}', artifact['sha256']))
    del value['artifact']
    return digest(canonical(value))


def protected(path, *, uid=0):
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
        meta = os.fstat(stream.fileno())
        require(stat.S_ISREG(meta.st_mode) and meta.st_uid == uid and not meta.st_mode & 0o022
                and meta.st_nlink == 1 and meta.st_size <= 1048576)
        data = stream.read(1048577)
        require(len(data) <= 1048576 and identity(os.fstat(stream.fileno())) == identity(meta))
        return data


def service_exec_start(unit):
    """Retain the complete typed launch definition, excluding execution history."""
    def read(arguments):
        result = subprocess.run(['/bin/busctl', '--system', '--json=short', '--timeout=5s', *arguments],
                                capture_output=True, check=True, timeout=8)
        require(len(result.stdout) <= 1048576)
        return json.loads(result.stdout)

    location = read(['call', 'org.freedesktop.systemd1', '/org/freedesktop/systemd1',
                     'org.freedesktop.systemd1.Manager', 'GetUnit', 's', unit])
    require(isinstance(location, dict) and location.get('type') == 'o'
            and isinstance(location.get('data'), list) and len(location['data']) == 1)
    path = location['data'][0]
    require(isinstance(path, str) and re.fullmatch(r'/org/freedesktop/systemd1/unit/[A-Za-z0-9_]+', path))
    definition = read(['get-property', 'org.freedesktop.systemd1', path,
                       'org.freedesktop.systemd1.Service', 'ExecStartEx'])
    require(isinstance(definition, dict) and definition.get('type') == 'a(sasasttttuii)'
            and isinstance(definition.get('data'), list) and definition['data'])
    commands = []
    # get-property unwraps its D-Bus variant; unlike call, data is the value
    # itself, not an array containing all method return arguments.
    for command in definition['data']:
        require(isinstance(command, list) and len(command) == 10)
        executable, arguments, flags = command[:3]
        require(isinstance(executable, str) and executable.startswith('/') and '\0' not in executable
                and isinstance(arguments, list) and arguments
                and all(isinstance(value, str) and '\0' not in value for value in arguments)
                and isinstance(flags, list)
                and all(isinstance(value, str) and value and '\0' not in value for value in flags))
        require(all(type(value) is int and 0 <= value < 2**64 for value in command[3:7])
                and type(command[7]) is int and 0 <= command[7] < 2**32
                and all(type(value) is int and -2**31 <= value < 2**31 for value in command[8:]))
        commands.append([executable, arguments, flags])
    return commands


def service(unit):
    require(unit.endswith('.service') and '/' not in unit)
    fields = 'LoadState,ActiveState,SubState,MainPID,ExecMainStartTimestamp,ExecMainStartTimestampMonotonic,NeedDaemonReload,User,ControlGroup,FragmentPath,DropInPaths,EnvironmentFiles,ExecStart,PartOf,Requires,BindsTo'
    result = subprocess.run(['/bin/systemctl', '--timestamp=us', 'show', unit, '--property=' + fields],
                            capture_output=True, check=True, timeout=15,
                            env={**os.environ, 'TZ': 'UTC', 'LC_ALL': 'C'})
    values = dict(line.split('=', 1) for line in result.stdout.decode().splitlines())
    require(values['LoadState'] == 'loaded' and values['ActiveState'] == 'active'
            and values['SubState'] == 'running' and values['NeedDaemonReload'] == 'no'
            and values['MainPID'].isdigit() and int(values['MainPID']) > 0
            and values['ControlGroup'] == '/system.slice/' + unit)
    for field in ['Requires', 'BindsTo', 'PartOf']:
        members = values[field].split()
        # systemd exports these dependency sets in iteration order, which may
        # change after daemon-reload. No ordering semantics apply to members.
        require(all(re.fullmatch(r'(?:[A-Za-z0-9:_.@-]|\\x[0-9a-fA-F]{2})+\.(?:service|socket|target|device|mount|automount|swap|timer|path|slice|scope)',
                                 member) for member in members))
        values[field] = ' '.join(sorted(set(members)))
    values['ExecStart'] = service_exec_start(unit)
    return values


def environment(pid):
    parts = Path('/proc', str(pid), 'environ').read_bytes().split(b'\0')
    pairs = [part.decode().split('=', 1) for part in parts if part]
    require(len({key for key, _ in pairs}) == len(pairs))
    return dict(pairs)


def service_started(state):
    return service_started_ns(state) / 1000000000


def service_started_ns(state):
    value = state['ExecMainStartTimestamp']
    for pattern in ['%a %Y-%m-%d %H:%M:%S UTC', '%a %Y-%m-%d %H:%M:%S.%f UTC']:
        try:
            parsed = datetime.strptime(value, pattern).replace(tzinfo=timezone.utc)
            elapsed = parsed - datetime(1970, 1, 1, tzinfo=timezone.utc)
            return ((elapsed.days * 86400 + elapsed.seconds) * 1000000 + elapsed.microseconds) * 1000
        except ValueError:
            continue
    raise ValueError('PROCESS_ADOPTION_UNPROVEN')


def process(pid, service_start, *, mutable_database=None):
    root = Path('/proc', str(pid))
    start = root.joinpath('stat').read_text().rsplit(') ', 1)[1].split()[19]
    boot = next(int(row.split()[1]) for row in Path('/proc/stat').read_text().splitlines() if row.startswith('btime '))
    # Bound by both original systemd realtime and current boot conversion;
    # a wall-clock correction cannot make a later input appear pre-start.
    started = min(service_start, boot + int(start) / os.sysconf('SC_CLK_TCK'))
    # Pin the exact kernel-mapped inode/device, then prove no mutation since
    # process startup. This also works when map_files requires CAP_SYS_ADMIN;
    # a matching pathname by itself is never loaded artifact evidence.
    maps = {}
    mapped_ids = {}
    for row in root.joinpath('maps').read_text().splitlines():
        columns = row.split(None, 5)
        if len(columns) == 6 and columns[5].startswith('/'):
            if columns[5].startswith('/memfd:doublemapper '):
                continue  # .NET anonymous JIT allocation, not a disk dependency.
            require(not columns[5].endswith(' (deleted)'))
            if mutable_database is not None and columns[5] in [mutable_database + suffix for suffix in ['', '-wal', '-shm']]:
                mutable_sqlite_mapping(columns[5], columns[1], columns[3], columns[4], root.stat().st_uid)
                continue
            identity = (columns[3], columns[4])
            require(columns[5] not in mapped_ids or mapped_ids[columns[5]] == identity)
            if columns[5] in maps:
                continue
            maps[columns[5]] = mapped_digest(columns[5], columns[3], columns[4], started)
            mapped_ids[columns[5]] = identity
    require(maps)
    return {'pid': str(pid), 'uid': root.stat().st_uid, 'start': start, 'executable': digest(root.joinpath('exe').read_bytes()),
            'environment': digest(canonical(environment(pid))),
            'command': digest(root.joinpath('cmdline').read_bytes()), 'maps': maps}


def mutable_sqlite_mapping(path, permissions, device, inode, uid):
    """The exact configured SQLite data family is live application state."""
    require(Path(path).is_absolute() and '..' not in Path(path).parts and 'x' not in permissions)
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
        meta = os.fstat(stream.fileno())
        major, minor = (int(value, 16) for value in device.split(':'))
        require(stat.S_ISREG(meta.st_mode) and meta.st_uid == uid and meta.st_nlink == 1
                and not meta.st_mode & 0o022 and meta.st_ino == int(inode)
                and os.major(meta.st_dev) == major and os.minor(meta.st_dev) == minor)


def mapped_digest(path, device, inode, started):
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
        meta = os.fstat(stream.fileno())
        major, minor = (int(value, 16) for value in device.split(':'))
        require(stat.S_ISREG(meta.st_mode) and meta.st_ino == int(inode)
                and os.major(meta.st_dev) == major and os.minor(meta.st_dev) == minor
                and meta.st_nlink == 1 and not meta.st_mode & 0o022
                and meta.st_ctime < started - 2)
        result = hashlib.file_digest(stream, 'sha256').hexdigest()
        require(identity(os.fstat(stream.fileno())) == identity(meta))
        return result


def loaded_reviewer(payload, state):
    uid = pwd.getpwnam(payload['reviewerUser']).pw_uid
    require(uid != 0)
    pid = int(state['MainPID'])
    require(Path('/proc', str(pid)).stat().st_uid == uid and state['User'] == payload['reviewerUser'])
    path = Path(payload['socket'])
    directory = path.parent.lstat()
    meta = path.lstat()
    require(stat.S_ISDIR(directory.st_mode) and directory.st_uid == uid
            and stat.S_IMODE(directory.st_mode) == 0o700
            and stat.S_ISSOCK(meta.st_mode) and meta.st_uid == uid
            and stat.S_IMODE(meta.st_mode) == 0o600)
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(5)
        connection.connect(str(path))
        peer_pid, peer_uid, _ = struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        require(peer_pid == pid and peer_uid == uid)
        data = bytearray()
        while True:
            chunk = connection.recv(4096)
            if not chunk:
                break
            data.extend(chunk)
            require(len(data) <= 16384)
    proof = json.loads(data)
    env = environment(pid)
    paths = env['REVIEWER_ADOPTION_ENV_FILES'].split(':')
    require(paths == payload['environmentFiles'] and env['REVIEWER_ADOPTION_SOCKET'] == payload['socket']
            and env['REVIEWER_ADOPTION_UNIT_FILE'] == state['FragmentPath'])
    expected = {'schemaVersion': 1, 'pid': pid,
                'config': configuration(protected(payload['config'])),
                'environment': digest(canonical(env)),
                'ca': digest(protected(env['REVIEWER_CLIENT_CA_FILE'])),
                'key': digest(protected(env['GITHUB_APP_PRIVATE_KEY_FILE'])),
                'unit': digest(protected(state['FragmentPath'])),
                'environmentFiles': {path: digest(protected(path)) for path in paths}}
    require(proof == expected)
    live = process(pid, service_started(state), mutable_database=env.get('REVIEWER_RELAY_DB'))
    for path, expected_digest in live['maps'].items():
        require(digest(Path(path).read_bytes()) == expected_digest)
    manifest = json.loads(protected(Path(payload['release']) / 'artifact-manifest.json'))
    require(live['executable'] == manifest['reviewerBinarySha256'])
    return {'loaded': proof, 'process': live, 'service': state,
            'units': service_configuration(state, service_started(state))}


def unchanged_since_start(path, earliest, uid):
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
        meta = os.fstat(stream.fileno())
        require(stat.S_ISREG(meta.st_mode) and meta.st_uid in [0, uid] and meta.st_nlink == 1
                and not meta.st_mode & 0o022 and meta.st_ctime < earliest - 2)
        result = hashlib.file_digest(stream, 'sha256').hexdigest()
        require(identity(os.fstat(stream.fileno())) == identity(meta))
        return result


def trust_locations(env, defaults):
    """The Linux .NET/OpenSSL machine store, including its default fallback."""
    file = env.get(defaults.openssl_cafile_env, defaults.openssl_cafile)
    directories = env.get(defaults.openssl_capath_env, defaults.openssl_capath)
    require(isinstance(file, str) and isinstance(directories, str))
    selected = ([file] if file else []) + [path for path in directories.split(':') if path]
    # .NET uses this fallback when the OpenSSL default directory has no roots.
    # Explicit SSL_CERT_DIR suppresses that fallback in the runtime contract.
    if defaults.openssl_capath_env not in env:
        selected.append('/etc/ssl/certs')
    require(selected and all(Path(path).is_absolute() and '..' not in Path(path).parts for path in selected))
    return list(dict.fromkeys(selected))


def trust_parents(path, boundary):
    require(Path(path).is_relative_to(boundary))
    return [parent for parent in reversed(Path(path).parents) if parent.is_relative_to(boundary)]


def security_identity(meta):
    return (meta.st_dev, meta.st_ino, meta.st_mode, meta.st_uid, meta.st_gid)


def trust_store(path, earliest, uid=0, *, boundary=Path('/'), history_root=None):
    """Prove loaded trust cannot predate disk changes, including removed roots.

    Follow only bounded protected symlink topology. Every file, link and parent
    directory must have remained unchanged since retained service startup.
    """
    observed, visiting, expanded = {}, set(), set()
    def visit(current, descend):
        current = Path(current)
        require(current.is_absolute() and '..' not in current.parts)
        key = str(current)
        require(len(observed) < 8192)
        meta = current.lstat()
        require(meta.st_uid in [0, uid])
        if not stat.S_ISLNK(meta.st_mode):
            require(not meta.st_mode & 0o022)
        if key in visiting:
            require(not descend and stat.S_ISDIR(meta.st_mode))
            return  # A symlink target shares the currently enumerated parent.
        historical = (descend or stat.S_ISLNK(meta.st_mode) or (uid != 0 and meta.st_uid == uid)
                      or history_root is not None and current.is_relative_to(history_root))
        if historical:
            require(meta.st_ctime < earliest - 2)
        value = {'identity': identity(meta) if historical else security_identity(meta)}
        if key in observed:
            require(observed[key]['identity'] in [identity(meta), security_identity(meta)])
            if not descend or key in expanded:
                return
        visiting.add(key)
        if stat.S_ISLNK(meta.st_mode):
            value['link'] = os.readlink(current)
            resolved = current.resolve(strict=True)
            for parent in trust_parents(resolved, boundary):
                visit(parent, False)
            visit(resolved, descend)
        elif stat.S_ISREG(meta.st_mode):
            value['sha256'] = unchanged_since_start(current, earliest, uid)
        else:
            require(stat.S_ISDIR(meta.st_mode))
            if descend:
                for child in sorted(current.iterdir()):
                    visit(child, True)
        require(identity(current.lstat()) == identity(meta))
        observed[key] = value
        if descend:
            expanded.add(key)
        visiting.remove(key)
    path = Path(path)
    for parent in trust_parents(path, boundary):
        visit(parent, False)
    visit(path, True)
    return observed


def runner_trust(processes, earliest, uid):
    import ssl
    # Python's default-path query must use the same libcrypto the running .NET
    # process uses. A different or not-yet-loaded provider cannot attest its
    # compile-time defaults, so that case takes the ordinary restart path.
    own = {row.split(None, 5)[5] for row in Path('/proc/self/maps').read_text().splitlines()
           if len(row.split(None, 5)) == 6 and '/libcrypto.so' in row.split(None, 5)[5]}
    require(len(own) == 1)
    crypto = next(iter(own))
    crypto_digest = digest(Path(crypto).read_bytes())
    defaults = ssl.get_default_verify_paths()
    providers = {pid: [path for path in value['maps'] if '/libcrypto.so' in path]
                 for pid, value in processes.items()}
    selected = {pid: paths for pid, paths in providers.items() if paths}
    require(selected and all(paths == [crypto] and processes[pid]['maps'][crypto] == crypto_digest
                             for pid, paths in selected.items()))
    # The Listener's effective environment may differ from runsvc.sh/Node's.
    # Prove trust for each retained process actually using the crypto provider.
    return {pid: process_trust(environment(pid), defaults, earliest, uid) for pid in selected}


def process_trust(env, defaults, earliest, uid):
    selected = trust_locations(env, defaults)
    machine = {path: trust_store(path, earliest) for path in selected}
    # .NET's user X509 stores also contribute roots/intermediates. Absence is
    # proved through the nearest existing parent, never guessed from no files.
    home = Path(env['HOME'])
    require(home.is_absolute() and '..' not in home.parts)
    user = home / '.dotnet/corefx/cryptography/x509stores'
    absent = []
    while not os.path.lexists(user):
        absent.append(str(user))
        user = user.parent
        require(user != Path('/'))
    user_proof = (trust_store(user, earliest, uid, history_root=home) if not absent else
                  trust_store_parent(user, earliest, uid, history_root=home))
    return {'machine': machine, 'user': user_proof, 'absentUserPaths': absent}


def trust_store_parent(path, earliest, uid, *, boundary=Path('/'), history_root=None):
    # Fingerprint only the ancestor chain when the X509 store is absent. This
    # avoids scanning unrelated Runner home contents while detecting creation
    # or removal of a cached user trust store after startup.
    result = {}
    for parent in [*trust_parents(path, boundary), Path(path)]:
        meta = parent.lstat()
        require(stat.S_ISDIR(meta.st_mode) and meta.st_uid in [0, uid]
                and not meta.st_mode & 0o022)
        historical = (parent == Path(path) or (uid != 0 and meta.st_uid == uid)
                      or history_root is not None and parent.is_relative_to(history_root))
        if historical:
            require(meta.st_ctime < earliest - 2)
        result[str(parent)] = {'identity': identity(meta) if historical else security_identity(meta)}
    return result


def service_configuration(state, earliest):
    """Loaded unit/drop-in evidence, including the managed local-Apply drop-in."""
    files = {state['FragmentPath']: unchanged_since_start(state['FragmentPath'], earliest, 0)}
    directories = {}
    for path in state['DropInPaths'].split():
        value = Path(path)
        require(value.is_absolute() and value.name.endswith('.conf') and value.parent.name.endswith('.d'))
        files[path] = unchanged_since_start(value, earliest, 0)
        directories[str(value.parent)] = trust_store(value.parent, earliest)
    return {'files': files, 'dropinDirectories': directories}


def service_environment_files(state):
    """Read systemd's loaded EnvironmentFiles list, never another component's."""
    remaining = state['EnvironmentFiles']
    paths = []
    while remaining:
        selected = re.match(r'(/[-A-Za-z0-9_./]+) \(ignore_errors=(?:yes|no)\)(?: |$)', remaining)
        require(selected is not None)
        path = selected.group(1)
        require('..' not in Path(path).parts and str(Path(path)) == path)
        paths.append(path)
        remaining = remaining[selected.end():]
    return list(dict.fromkeys(paths))


def netlink_attributes(raw):
    result = {}
    while raw:
        require(len(raw) >= 4)
        length, kind = struct.unpack_from('=HH', raw)
        require(4 <= length <= len(raw) and (kind & 0x3fff) not in result)
        result[kind & 0x3fff] = raw[4:length]
        padded = (length + 3) & ~3
        require(padded <= len(raw))
        raw = raw[padded:]
    return result


def taskstats_elapsed(pid, uid):
    """Optional live PID GET, never a listener or persisted accounting record."""
    def attribute(kind, value):
        raw = struct.pack('=HH', len(value) + 4, kind) + value
        return raw + b'\0' * (-len(raw) % 4)

    with socket.socket(socket.AF_NETLINK, socket.SOCK_RAW, 16) as channel:
        channel.settimeout(1)
        channel.bind((0, 0))

        def query(family, command, attrs, sequence, reply_command, reply_version):
            body = struct.pack('=BBH', command, 1, 0) + attrs
            request = struct.pack('=IHHII', len(body) + 16, family, 1, sequence, 0) + body
            before = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
            channel.sendto(request, (0, 0))
            raw, source = channel.recvfrom(65536)
            require(source == (0, 0) and len(raw) >= 20)
            length, kind, flags, returned_sequence, recipient = struct.unpack_from('=IHHII', raw)
            require(length == len(raw) and returned_sequence == sequence and not flags & 2
                    and recipient == channel.getsockname()[0])
            if kind == 2:
                raise ValueError('PROCESS_ADOPTION_UNPROVEN')
            require(kind == family and raw[16] == reply_command and raw[17] == reply_version
                    and raw[18:20] == b'\0\0')
            return netlink_attributes(raw[20:]), before

        control, _ = query(16, 3, attribute(2, b'TASKSTATS\0'), 1, 1, 2)
        require(len(control.get(1, b'')) == 2)
        family = struct.unpack('=H', control[1])[0]
        require(family >= 16)
        response, before = query(family, 1, attribute(1, struct.pack('=I', int(pid))), 2, 2, 1)
        aggregate = netlink_attributes(response.get(4, b''))
        require(aggregate.get(1) == struct.pack('=I', int(pid)))
        stats = aggregate.get(3, b'')
        require(len(stats) >= 152 and struct.unpack_from('=H', stats)[0] >= 1)
        require(struct.unpack_from('=I', stats, 120)[0] == uid
                and struct.unpack_from('=I', stats, 128)[0] == int(pid))
        elapsed = struct.unpack_from('=Q', stats, 144)[0]
        # Linux bacct_add_tsk floors (ktime_get_ns - task.start_time) to us.
        # The request begins before that sample: subtract a full us, never add
        # a tick-sized acceptance margin. Transport delay only lowers this bound.
        return before - (elapsed + 1) * 1000


def precise_consumer_lower_bound(state, pid, proof, uid):
    lower_monotonic = taskstats_elapsed(pid, uid)
    # Bind the queried live PID to the already captured process generation.
    require(Path('/proc', pid, 'stat').read_text().rsplit(')', 1)[1].split()[19] == proof['start'])
    wall_before = time.time_ns()
    monotonic_after = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    current = wall_before - monotonic_after + lower_monotonic
    original = (service_started_ns(state) + lower_monotonic
                - (int(state['ExecMainStartTimestampMonotonic']) + 1) * 1000)
    return min(current, original)


def consumer_start_lower_bound(state, start_ticks, pid=None, proof=None, uid=None):
    # The public Runner generates its helper after the main wrapper starts.
    # Bind it to the consuming shell, using both present and original clocks;
    # a later forward wall-clock adjustment must not approve stale script code.
    require(re.search(r'\.[0-9]{1,6} UTC$', state['ExecMainStartTimestamp']) is not None)
    ticks = int(start_ticks) * 1000000000 // os.sysconf('SC_CLK_TCK')
    wall_before = time.time_ns()
    boot_after = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
    current = wall_before - boot_after + ticks
    monotonic_before = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    boot_after = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
    original = (service_started_ns(state) + ticks - (boot_after - monotonic_before)
                - (int(state['ExecMainStartTimestampMonotonic']) + 1) * 1000)
    lower = min(current, original)
    if pid is not None:
        try:
            lower = max(lower, precise_consumer_lower_bound(state, pid, proof, uid))
        except (OSError, ValueError, KeyError, struct.error):
            pass  # Unsupported kernel/capability/uncertain reply keeps strict tick proof.
    return lower


def runner_arguments(pid, proof):
    raw = Path('/proc', pid, 'cmdline').read_bytes()
    require(digest(raw) == proof['command'])
    return [part.decode() for part in raw.split(b'\0') if part]


def generated_runner_helper(root, state, processes, earliest, uid):
    """Narrow proof for the pinned Runner run.sh -> run-helper.sh copy."""
    helper, template, generator = (root / name for name in ['run-helper.sh', 'run-helper.sh.template', 'run.sh'])
    generator_hash = unchanged_since_start(generator, earliest, uid)
    template_hash = unchanged_since_start(template, earliest, uid)
    recipe = b'cp -f "$DIR"/run-helper.sh.template "$DIR"/run-helper.sh'
    require(recipe in protected(generator, uid=uid))
    wrapper = processes[state['MainPID']]
    arguments = runner_arguments(state['MainPID'], wrapper)
    require(len(arguments) >= 2 and arguments[1] == str(generator))
    consumers = []
    for pid, proof in processes.items():
        arguments = runner_arguments(pid, proof)
        if len(arguments) >= 2 and arguments[1] == str(helper):
            require(proof['executable'] == wrapper['executable'])
            consumers.append(pid)
    require(len(consumers) == 1)
    consumer = consumers[0]
    lower = consumer_start_lower_bound(state, processes[consumer]['start'], consumer, processes[consumer], uid)
    meta = helper.lstat()
    require(meta.st_ctime_ns < lower)
    helper_hash = digest(protected(helper, uid=uid))
    require(helper_hash == template_hash and identity(helper.lstat()) == identity(meta))
    return {'sha256': helper_hash, 'generatorSha256': generator_hash, 'templateSha256': template_hash,
            'consumer': consumer, 'consumerStartTicks': processes[consumer]['start']}


def distribution_alias(path, roots, earliest, uid):
    """Bounded native distribution leaf links, never credential/settings links."""
    current = Path(path)
    links, directories = {}, {}
    for _ in range(16):
        scopes = [root for root in roots if current.is_relative_to(root)]
        require(len(scopes) == 1)
        scope = scopes[0]
        # No hidden intermediate redirect is followed. Top-level native
        # bin/externals version aliases were separately resolved and proved.
        parent = scope
        parents = [scope]
        for component in current.parent.relative_to(scope).parts:
            parent = parent / component
            parents.append(parent)
        for parent in parents:
            meta = parent.lstat()
            require(stat.S_ISDIR(meta.st_mode) and meta.st_uid in [0, uid]
                    and not meta.st_mode & 0o022 and meta.st_ctime < earliest - 2)
            directories[str(parent)] = identity(meta)
        meta = current.lstat()
        if not stat.S_ISLNK(meta.st_mode):
            result = unchanged_since_start(current, earliest, uid)
            require(all(identity(Path(name).lstat()) == info for name, info in directories.items()))
            require(all(identity(Path(name).lstat()) == value['identity']
                        and os.readlink(name) == value['target'] for name, value in links.items()))
            return {'links': links, 'directories': directories, 'target': str(current), 'sha256': result}
        require(str(current) not in links and meta.st_uid in [0, uid] and meta.st_nlink == 1
                and meta.st_ctime < earliest - 2)
        target = os.readlink(current)
        links[str(current)] = {'identity': identity(meta), 'target': target}
        candidate = Path(target) if Path(target).is_absolute() else current.parent / target
        current = Path(os.path.normpath(candidate))
    raise ValueError('PROCESS_ADOPTION_UNPROVEN')


def distribution_directory(path, earliest, uid):
    """Deletion-aware history for optional settings and interpreted files."""
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        meta = os.fstat(descriptor)
        require(stat.S_ISDIR(meta.st_mode) and meta.st_uid in [0, uid]
                and not meta.st_mode & 0o022 and meta.st_ctime < earliest - 2)
        entries = sorted(os.listdir(descriptor))
        require(len(entries) <= 20000 and identity(os.fstat(descriptor)) == identity(meta)
                and identity(Path(path).lstat()) == identity(meta))
        return {'identity': identity(meta), 'entries': entries}
    finally:
        os.close(descriptor)


def cgroup_members(path):
    values = Path(path).read_text().splitlines()
    require(values and all(re.fullmatch('[1-9][0-9]*', value) for value in values)
            and len(values) == len(set(values)))
    return sorted(values, key=int)


def revalidate_runner_processes(cgroup, expected, state):
    # MainPID alone cannot detect a replaced Listener/child during file scans.
    # Require the complete same cgroup and each loaded identity at the end.
    require(cgroup_members(cgroup) == sorted(expected, key=int))
    for pid, original in expected.items():
        require(process(pid, service_started(state)) == original)
    require(cgroup_members(cgroup) == sorted(expected, key=int))


def loaded_runner(payload, state):
    uid = pwd.getpwnam(payload['productionUser']).pw_uid
    require(state['User'] == payload['productionUser'])
    cgroup = Path('/sys/fs/cgroup') / state['ControlGroup'].lstrip('/') / 'cgroup.procs'
    pids = cgroup_members(cgroup)
    require(state['MainPID'] in pids and pids)
    processes = {pid: process(pid, service_started(state)) for pid in pids}
    require(all(Path('/proc', pid).stat().st_uid == uid for pid in pids))
    boot = next(int(row.split()[1]) for row in Path('/proc/stat').read_text().splitlines() if row.startswith('btime '))
    earliest = min(service_started(state), boot + min(int(value['start']) for value in processes.values()) / os.sysconf('SC_CLK_TCK'))
    root = Path(payload['productionRoot'])
    topology = {str(root): distribution_directory(root, earliest, uid)}
    # Runner's own settings/credentials are cached on Listener startup. Kernel
    # ctime proves they have not changed since any retained service process
    # started; byte equality alone would not establish loaded settings.
    names = ['.runner', '.runner_migrated', '.credentials', '.credentials_rsaparams', '.env', '.path']
    files = {str(root / name): unchanged_since_start(root / name, earliest, uid)
             for name in names if os.path.lexists(root / name)}
    require(str(root / '.runner') in files and str(root / '.credentials') in files)
    # runsvc.sh/RunnerService.js and managed DLLs can be interpreted/read into
    # memory rather than represented by a distinct executable mapping. Prove
    # unchanged complete startup distribution, not only Runner.Listener's name.
    inputs = [path for path in root.iterdir() if path.is_file()]
    distribution_roots = []
    def unreadable_distribution(error):
        raise error
    for directory in ['bin', 'externals']:
        entry = root / directory
        if entry.is_symlink():
            meta = entry.lstat()
            resolved = entry.resolve(strict=True)
            require(meta.st_uid == uid and meta.st_ctime < earliest - 2
                    and resolved.parent == root and resolved.name.startswith(directory + '.'))
            files[str(entry)] = digest(os.readlink(entry).encode())
            entry = resolved
        require(entry.is_dir())
        distribution_roots.append(entry)
        for parent, directories, names in os.walk(entry, onerror=unreadable_distribution):
            topology[str(parent)] = distribution_directory(parent, earliest, uid)
            require(len(topology) <= 20000)
            require(all(not (Path(parent) / name).is_symlink() for name in directories))
            inputs.extend(Path(parent) / name for name in names)
            require(len(inputs) <= 20000)
    for path in inputs:
        if path == root / 'run-helper.sh':
            files[str(path)] = generated_runner_helper(root, state, processes, earliest, uid)
            continue
        if path.is_symlink():
            files[str(path)] = distribution_alias(path, distribution_roots, earliest, uid)
            continue
        files[str(path)] = unchanged_since_start(path, earliest, uid)
    for path in service_environment_files(state):
        files[path] = unchanged_since_start(path, earliest, 0)
    for process_value in processes.values():
        for path, expected in process_value['maps'].items():
            # Same mapped object and same intended disk object, never a renamed
            # old DLL or runtime accepted against a new installation.
            require(digest(Path(path).read_bytes()) == expected)
    trust = runner_trust(processes, earliest, uid)
    units = service_configuration(state, earliest)
    require(all(distribution_directory(path, earliest, uid) == original for path, original in topology.items()))
    revalidate_runner_processes(cgroup, processes, state)
    return {'service': state, 'processes': processes, 'files': files, 'trust': trust,
            'units': units, 'distributionDirectories': topology}


def capture_inputs(payload):
    reviewer_state = service(payload['reviewerUnit'])
    reviewer = loaded_reviewer(payload, reviewer_state)
    runner = None
    if payload['productionActive']:
        runner = loaded_runner(payload, service(payload['productionUnit']))
    # Recheck after bounded reads; service movement during proof is uncertain.
    require(service(payload['reviewerUnit']) == reviewer_state)
    if runner:
        require(service(payload['productionUnit']) == runner['service'])
    return {'reviewer': reviewer, 'production': runner}


def admission(payload):
    result = subprocess.run([*payload['admission'], 'status', '--operation', payload['operation']],
                            capture_output=True, check=True, timeout=60)
    gate = json.loads(result.stdout)
    require(gate['operationId'] == payload['operation'] and gate['target'] == payload['target']
            and gate['phase'] == 'applying' and gate['active'] == [] and gate['unknown'] == [])
    require(gate['previousActive']['reviewer']['active'] is True
            and gate['previousActive']['production']['active'] == payload['productionActive'])
    return gate


def capture(payload):
    with os.fdopen(os.open(payload['operationLock'], os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as lock:
        opened = os.fstat(lock.fileno())
        require(stat.S_ISREG(opened.st_mode) and opened.st_uid == 0 and not opened.st_mode & 0o022
                and opened.st_nlink == 1)
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        gate = admission(payload)
        if payload.get('before') is not None:
            record = json.loads(protected(payload['operationRecord']))
            require(record['state'] == 'RECOVERY_REQUIRED' and record['phase'] == 'apply'
                    and record['target_head'] == payload['target'])
        proof = capture_inputs(payload)
        require(admission(payload) == gate)
        current = os.lstat(payload['operationLock'])
        require((current.st_dev, current.st_ino) == (opened.st_dev, opened.st_ino))
        require(identity(os.fstat(lock.fileno())) == identity(opened))
        return proof


def main():
    payload = json.load(sys.stdin)
    try:
        # The initial proof crosses Ansible's JSON boundary. Normalize native
        # stat tuples before comparing its later JSON-decoded representation.
        current = json.loads(canonical(capture(payload)))
        previous = payload.get('before')
        require(previous is None or current == previous)
        print(json.dumps({'eligible': True, 'proof': current}))
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, ImportError, StopIteration, subprocess.SubprocessError):
        # Normal fall back, with no exception/credential/path disclosure.
        print(json.dumps({'eligible': False}))


if __name__ == '__main__':
    main()
