"""Current native evidence for an operation-scoped source-only upgrade.

This module never changes installed state. Expected managed bytes are supplied
by the source-owned catalogue; private evidence remains inside the operation.
"""
import copy
import grp
import hashlib
import importlib.util
import ipaddress
import io
import json
import marshal
import os
from pathlib import Path
import re
import stat
import subprocess
import struct
import sys
import types
from concurrent.futures import ThreadPoolExecutor


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def refuse(code):
    from installed_state import NotEligible
    raise NotEligible(code)


def require(value, code='SOURCE_UPGRADE_PROOF_UNPROVEN'):
    if not value:
        refuse(code)


def unchanged(value, code):
    """A moving admitted binding is a boundary, never an optimization miss."""
    if not value:
        raise RuntimeError(code)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'SOURCE_UPGRADE_JSON_INVALID')
        result[key] = value
    return result


def resolve_values(values, source_root):
    """Resolve nonsecret owning defaults with the existing controller Templar.

    Optional register facts and environment lookups are never manufactured.
    Missing required values subsequently refuse the optimization.
    """
    import yaml
    from ansible.parsing.dataloader import DataLoader
    from ansible.template import Templar
    root = Path(source_root)
    defaults = yaml.safe_load((root / 'deploy/ansible/group_vars/all.yml').read_text())
    variables = {**defaults, **values, 'playbook_dir': str(root / 'deploy/ansible')}
    templar = Templar(loader=DataLoader(), variables=variables)
    result = dict(values)
    for key, value in defaults.items():
        if key in result or 'lookup(' in str(value) or 'lookup (' in str(value):
            continue
        try:
            result[key] = templar.template(value, fail_on_undefined=True)
        except Exception:
            pass  # An unused register fact is not an installed-state observation.
    require(result.get('relay_deployment_profile') == 'production', 'SOURCE_UPGRADE_PROFILE_UNSUPPORTED')
    return result


def normalized_config(config):
    result = copy.deepcopy(config)
    source = result.get('source')
    require(isinstance(source, dict) and isinstance(source.get('repository'), str),
            'SOURCE_UPGRADE_CONFIG_UNPROVEN')
    selector = source.get('revision', 'main')
    require(isinstance(selector, str), 'SOURCE_UPGRADE_CONFIG_UNPROVEN')
    source.pop('revision', None)
    return result


def recipe_rows(source_root):
    root = Path(source_root)
    paths = []
    for path in sorted((root / 'deploy/ansible').rglob('*')):
        relative = path.relative_to(root / 'deploy/ansible').as_posix()
        if path.is_file() and 'tests' not in path.parts and '__pycache__' not in path.parts:
            paths.append(path)
    paths += [root / name for name in ['deploy/config.py', 'deploy/host_preflight.py',
        'deploy/managed_pool.py', 'deploy/pool_authorization.py', 'deploy/pool_eligibility.py',
        'deploy/serial_pool_installation.py', 'deploy/serial_pool_host.py']]
    return [[path.relative_to(root).as_posix(), hashlib.sha256(
        protected_read(path, limit=64 * 1024 * 1024, boundary=root)[0]).hexdigest()]
        for path in paths]


def protected_read(path, *, limit=1024 * 1024, owner_uid=0, boundary=Path('/')):
    path = Path(path)
    for parent in path.parents:
        info = parent.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == owner_uid and not info.st_mode & 0o022,
                'SOURCE_UPGRADE_PARENT_UNSAFE')
        if parent == boundary:
            break
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_uid == owner_uid
                and not before.st_mode & 0o022 and before.st_nlink == 1 and before.st_size <= limit,
                'SOURCE_UPGRADE_FILE_UNSAFE')
        raw = stream.read(limit + 1)
        require(len(raw) == before.st_size and file_stamp(os.fstat(stream.fileno())) == file_stamp(before),
                'SOURCE_UPGRADE_FILE_MOVED')
    require(file_stamp(path.lstat()) == file_stamp(before), 'SOURCE_UPGRADE_FILE_MOVED')
    return raw, file_stamp(before)


def file_stamp(info):
    return [info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns]


def read_binding(values, *, root=Path('/'), owner_uid=0):
    install = Path(values['relay_install_root'])
    require(install.is_absolute() and '..' not in install.parts, 'SOURCE_UPGRADE_BINDING_INVALID')
    current = root / install.relative_to('/') / 'current'
    for parent in current.parents:
        info = parent.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == owner_uid and not info.st_mode & 0o022,
                'SOURCE_UPGRADE_PARENT_UNSAFE')
        if parent == root:
            break
    before = current.lstat()
    require(stat.S_ISLNK(before.st_mode) and before.st_uid == owner_uid, 'SOURCE_UPGRADE_CURRENT_UNSAFE')
    logical = Path(os.readlink(current))
    require(logical.is_absolute() and logical.parent == Path(values['relay_release_root'])
            and re.fullmatch('[0-9a-f]{40}', logical.name), 'SOURCE_UPGRADE_CURRENT_UNSAFE')
    release = root / logical.relative_to('/')
    require(release.is_dir(), 'SOURCE_UPGRADE_CURRENT_UNSAFE')
    paths = [release / 'artifact-manifest.json', release / 'deployment-config.json',
             release / 'reviewed-source/.relay-source.json']
    records, stamps, hashes = [], [], []
    for path in paths:
        raw, stamp = protected_read(path, owner_uid=owner_uid, boundary=root)
        records.append(json.loads(raw, object_pairs_hook=unique_object))
        stamps.append(stamp)
        hashes.append(hashlib.sha256(raw).hexdigest())
    manifest, snapshot, identity = records
    require(manifest.get('schemaVersion') == '1.0'
            and all(manifest.get(key) == logical.name for key in ['commit', 'resolvedRevision', 'installedRevision'])
            and identity.get('revision') == logical.name and identity.get('tree') == manifest.get('gitTree')
            and manifest.get('deploymentConfigSha256') == hashes[1]
            and snapshot.get('environment', {}).get('namespace') == values['relay_namespace'],
            'SOURCE_UPGRADE_INSTALLED_BINDING_UNPROVEN')
    receipt = manifest.get('gitConfigReceipt')
    repository = snapshot['source']['repository'].removeprefix('https://github.com/').removeprefix(
        'git@github.com:').removesuffix('.git')
    require(isinstance(receipt, dict) and receipt.get('product_sha') == logical.name
            and receipt.get('product_repository') == repository
            and isinstance(receipt.get('config_sha256'), str)
            and re.fullmatch('[0-9a-f]{64}', receipt['config_sha256']),
            'SOURCE_UPGRADE_RECEIPT_UNPROVEN')
    policy = snapshot['environment']['localApply']
    if receipt.get('source') == 'owner-file':
        require(policy.get('source') != 'git', 'SOURCE_UPGRADE_RECEIPT_UNPROVEN')
    else:
        require(receipt.get('source_policy') in ['accepted-main', 'accepted-ancestor', 'test-qualified-exact']
                and all(isinstance(receipt.get(key), str) and re.fullmatch('[0-9a-f]{40}', receipt[key])
                        for key in ['config_sha', 'config_blob_sha'])
                and (policy.get('source') != 'git' or receipt.get('config_repository') == policy['repository']
                     and receipt.get('config_path') == policy['configPath'])
                and all(key not in receipt or type(receipt[key]) is int and receipt[key] > 0
                        for key in ['product_repository_id', 'config_repository_id'])
                and ('workflow_run_id' not in receipt or receipt['workflow_run_id'] is None
                     or type(receipt['workflow_run_id']) is int and receipt['workflow_run_id'] > 0),
                'SOURCE_UPGRADE_RECEIPT_UNPROVEN')
    if 'installationState' in manifest:
        from intent_install import pair_digest
        require(manifest['installationState'] == {'schemaVersion': 1, 'stage': 'ready',
                                                 'pairSha256': pair_digest(receipt)}
                and type(manifest['installationState'].get('schemaVersion')) is int,
                'SOURCE_UPGRADE_PENDING_INSTALLATION')
    unchanged(file_stamp(current.lstat()) == file_stamp(before)
            and all(file_stamp(path.lstat()) == stamp for path, stamp in zip(paths, stamps)),
            'SOURCE_UPGRADE_BINDING_CHANGED')
    binding = {'revision': logical.name, 'release': str(logical), 'current': file_stamp(before),
               'manifestSha256': hashes[0], 'snapshotSha256': hashes[1], 'sourceSha256': hashes[2],
               'files': stamps}
    return binding, manifest, identity, snapshot


def run(argv, *, timeout=30, **kwargs):
    result = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, timeout=timeout, check=False,
        env={'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C', 'LC_ALL': 'C'}, **kwargs)
    require(result.returncode == 0 and len(result.stdout) <= 2 * 1024 * 1024,
            'SOURCE_UPGRADE_NATIVE_CHECK_UNPROVEN')
    return result


def gateway_values(values, *, execute=run):
    """The existing Docker gateway role's read-only predicates, without mutation."""
    result = dict(values)
    mode = values['relay_reviewer_bind_mode']
    if mode == 'a_only_loopback':
        require(ipaddress.ip_address(values['relay_reviewer_bind_address']).is_loopback,
                'SOURCE_UPGRADE_BIND_UNPROVEN')
        result.update(relay_reviewer_bind_network='', relay_reviewer_gateway_validated=False)
        return result
    require(mode == 'nexus_gateway', 'SOURCE_UPGRADE_BIND_UNSUPPORTED')
    name = values['relay_docker_network_name']
    networks = json.loads(execute(['/usr/bin/docker', 'network', 'inspect', name]).stdout)
    require(isinstance(networks, list) and len(networks) == 1, 'SOURCE_UPGRADE_GATEWAY_UNPROVEN')
    network = networks[0]
    configs = network.get('IPAM', {}).get('Config')
    require(network.get('Name') == name and network.get('Driver') == 'bridge'
            and isinstance(configs, list) and len(configs) == 1, 'SOURCE_UPGRADE_GATEWAY_UNPROVEN')
    address = configs[0].get('Gateway')
    require(isinstance(address, str) and isinstance(ipaddress.ip_address(address), ipaddress.IPv4Address)
            and address not in ['0.0.0.0', '127.0.0.1', '255.255.255.255'],
            'SOURCE_UPGRADE_GATEWAY_UNPROVEN')
    host = execute(['/usr/sbin/ip', '-o', '-4', 'addr', 'show']).stdout.decode()
    require(len(re.findall(r'\s' + re.escape(address) + '/', host)) == 1,
            'SOURCE_UPGRADE_GATEWAY_UNPROVEN')
    route = execute(['/usr/sbin/ip', '-4', 'route', 'get', address]).stdout.decode()
    require(re.search(r'dev\s+', route), 'SOURCE_UPGRADE_GATEWAY_UNPROVEN')
    containers = json.loads(execute(['/usr/bin/docker', 'inspect', values['relay_docker_nginx_container_name']]).stdout)
    require(isinstance(containers, list) and len(containers) == 1, 'SOURCE_UPGRADE_GATEWAY_UNPROVEN')
    container = containers[0]
    attached = container.get('NetworkSettings', {}).get('Networks', {}).get(name, {})
    require(container.get('Name') == '/' + values['relay_docker_nginx_container_name']
            and attached.get('NetworkID') == network.get('Id')
            and (values['relay_docker_nginx_validation_mode'] != 'active' or attached.get('Gateway') == address),
            'SOURCE_UPGRADE_GATEWAY_UNPROVEN')
    result.update(relay_reviewer_bind_address=address, relay_reviewer_bind_network=name,
                  relay_reviewer_gateway_validated=True,
                  relay_docker_nginx_reviewer_upstream=address + ':' + str(values['relay_reviewer_bind_port']))
    return result


def describe(values, config, identity, source_root):
    from host_preflight import resolved
    v = resolved(values)
    binding, manifest, old_identity, snapshot = read_binding(v)
    require(normalized_config(snapshot) == normalized_config(config), 'SOURCE_UPGRADE_CONFIG_CHANGED')
    require(recipe_rows(Path(binding['release']) / 'reviewed-source') == recipe_rows(source_root),
            'SOURCE_UPGRADE_RECIPE_CHANGED')
    for name in ['reviewerSourceTreeSha256', 'reviewerBuildInputsTreeSha256']:
        require(identity.get(name) == manifest.get(name), 'SOURCE_UPGRADE_REVIEWER_INPUT_CHANGED')
    version, host, archive = [v['relay_rust_toolchain_' + key] for key in ['version', 'host', 'archive_sha256']]
    contract = ('cargo-build=--locked,--release;target-dir=reviewer-target;rust-version=' + version
                + ';rust-host=' + host + ';rust-archive-sha256=' + archive)
    require(manifest.get('reviewerBuildContractSha256') == hashlib.sha256(contract.encode()).hexdigest()
            and manifest.get('reviewerBuildToolchain', {}).get('archiveSha256') == archive
            and manifest.get('reviewerBuildToolchain', {}).get('cargoVersion', '').startswith('cargo ' + version)
            and manifest.get('reviewerArtifactProvenance') in ['built', 'verified-reuse'],
            'SOURCE_UPGRADE_REVIEWER_BUILD_UNPROVEN')
    raw, _ = protected_read(Path(binding['release']) / 'bin/reviewer-mcp-http', limit=256 * 1024 * 1024)
    require(hashlib.sha256(raw).hexdigest() == manifest.get('reviewerBinarySha256'),
            'SOURCE_UPGRADE_REVIEWER_BINARY_CHANGED')
    old_values = gateway_values(v)
    old_values.update(relay_release_commit=binding['revision'], relay_release_sha256=manifest['releaseSourceTreeSha256'],
        relay_release_path=binding['release'], relay_consumer_revision=manifest['consumerRevision'],
        relay_production_operation_target_head=binding['revision'],
        relay_controller_source_tree_sha256=manifest['controllerSourceTreeSha256'],
        relay_codex_launcher_source_tree_sha256=manifest['codexLauncherSourceTreeSha256'],
        relay_intent_preflight_installed_revision=binding['revision'])
    unchanged(read_binding(v)[0] == binding, 'SOURCE_UPGRADE_BINDING_CHANGED')
    return {'eligible': True, 'binding': binding, 'manifest': manifest,
            'sourceIdentity': old_identity, 'oldValues': old_values}


def _module(source_root, relative, name):
    path = Path(source_root) / relative
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_derived_cache(path, source, tracked):
    """Accept only a current interpreter's exact compilation of tracked bytes.

    Cache bytes never supply Git identity. No cached code is executed, removed
    or repaired; an unsupported/stale/changed cache refuses the optimization.
    """
    raw, stamp = protected_read(path, limit=64 * 1024 * 1024, boundary=source)
    require(len(raw) > 16 and raw[:4] == importlib.util.MAGIC_NUMBER,
            'SOURCE_UPGRADE_BYTECODE_UNPROVEN')
    flags = struct.unpack('<I', raw[4:8])[0]
    require(flags in [0, 1, 3], 'SOURCE_UPGRADE_BYTECODE_UNPROVEN')
    original = Path(importlib.util.source_from_cache(str(path)))
    relative = original.relative_to(source).as_posix()
    require(relative in tracked and original.suffix == '.py', 'SOURCE_UPGRADE_BYTECODE_UNPROVEN')
    optimization = re.search(r'\.opt-([12])\.pyc$', path.name)
    level = int(optimization[1]) if optimization else 0
    # Native proof bootstrap deliberately redirects cache reads to /dev/null.
    # Validate historical source-local caches independently of that active
    # prefix, without temporarily re-enabling cached imports.
    cache_name = original.stem + '.' + sys.implementation.cache_tag + ('.opt-' + str(level) if level else '') + '.pyc'
    require(original.parent / '__pycache__' / cache_name == path,
            'SOURCE_UPGRADE_BYTECODE_UNPROVEN')
    source_raw = tracked[relative]
    info = original.lstat()
    if flags & 1:
        require(raw[8:16] == importlib.util.source_hash(source_raw), 'SOURCE_UPGRADE_BYTECODE_UNPROVEN')
    else:
        require(struct.unpack('<II', raw[8:16]) == (int(info.st_mtime) & 0xffffffff, len(source_raw) & 0xffffffff),
                'SOURCE_UPGRADE_BYTECODE_UNPROVEN')
    stream = io.BytesIO(raw[16:])
    try:
        code = marshal.load(stream)
    except (EOFError, ValueError, TypeError):
        refuse('SOURCE_UPGRADE_BYTECODE_UNPROVEN')
    require(isinstance(code, types.CodeType) and not stream.read(), 'SOURCE_UPGRADE_BYTECODE_UNPROVEN')
    # Both owning installed entrypoint spellings resolve to the already bound
    # release. Arbitrary staging/foreign co_filename values are not accepted.
    current = source.parents[2] / 'current/reviewed-source' / relative
    require(code.co_filename in [str(original), str(current)], 'SOURCE_UPGRADE_BYTECODE_UNPROVEN')
    expected = compile(source_raw, code.co_filename, 'exec', dont_inherit=True, optimize=level)
    require(exact_code(code, expected), 'SOURCE_UPGRADE_BYTECODE_UNPROVEN')
    return [path.relative_to(source).as_posix(), hashlib.sha256(raw).hexdigest(), stamp]


def exact_code(actual, expected):
    # CPython code equality compares typed semantic constants (including signed
    # zero); marshal serialization additionally depends on object-reference and
    # interning flags. Compare every code definition field explicitly, including
    # filenames/debug tables omitted by semantic equality, recursively.
    fields = ['co_argcount', 'co_posonlyargcount', 'co_kwonlyargcount', 'co_nlocals',
              'co_stacksize', 'co_flags', 'co_code', 'co_names', 'co_varnames',
              'co_filename', 'co_name', 'co_qualname', 'co_firstlineno',
              'co_linetable', 'co_exceptiontable', 'co_freevars', 'co_cellvars']
    return (type(actual) is types.CodeType and type(expected) is types.CodeType
            and actual == expected and all(getattr(actual, field) == getattr(expected, field) for field in fields)
            and all(exact_code(left, right) for left, right in zip(actual.co_consts, expected.co_consts)
                    if isinstance(left, types.CodeType) or isinstance(right, types.CodeType)))


def verify_source_tree(binding, identity, snapshot, catalogue, source_root):
    """Reconstruct Git object bytes, never run Git against installed metadata."""
    source = Path(binding['release']) / 'reviewed-source'
    aliases = snapshot['environment'].get('compatibilityLinks', {})
    require(isinstance(aliases, dict), 'SOURCE_UPGRADE_SOURCE_LINKS_UNPROVEN')
    generated = {str(Path(row['path']).relative_to(source)) for row in catalogue['entries']
                 if Path(row['path']).is_relative_to(source)}
    entries, caches, seen_links, total, observed = [], [], set(), 0, [(source, file_stamp(source.lstat()))]
    for directory, directories, files in os.walk(source, followlinks=False):
        for name in [*directories, *files]:
            path = Path(directory) / name
            relative = path.relative_to(source).as_posix()
            info = path.lstat()
            require(info.st_uid == 0 and (stat.S_ISLNK(info.st_mode) or not info.st_mode & 0o022),
                    'SOURCE_UPGRADE_SOURCE_UNSAFE')
            observed.append((path, file_stamp(info)))
            if stat.S_ISLNK(info.st_mode):
                require(relative in aliases and path.resolve(strict=True) == source / aliases[relative],
                        'SOURCE_UPGRADE_SOURCE_LINKS_UNPROVEN')
                seen_links.add(relative)
                if name in directories:
                    directories.remove(name)
            elif stat.S_ISDIR(info.st_mode):
                continue
            else:
                require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
                        'SOURCE_UPGRADE_SOURCE_UNSAFE')
                if path.parent.name == '__pycache__' and path.suffix == '.pyc':
                    caches.append(path)
                    continue
                if relative == '.relay-source.json' or relative in generated:
                    continue  # Metadata/generation is separately bound and audited.
                require(relative.isascii() and not any(c in relative for c in ['"', '\\', '\t', '\n']),
                        'SOURCE_UPGRADE_SOURCE_NAMES_UNSUPPORTED')
                raw, _ = protected_read(path, limit=64 * 1024 * 1024, boundary=source)
                total += len(raw)
                require(total <= 256 * 1024 * 1024 and len(entries) < 20000,
                        'SOURCE_UPGRADE_SOURCE_LIMIT')
                entries.append((relative, '100755' if info.st_mode & 0o111 else '100644', raw))
    require(seen_links == set(aliases), 'SOURCE_UPGRADE_SOURCE_LINKS_UNPROVEN')
    stage = _module(source_root, 'deploy/ansible/roles/relay_artifacts/files/relay-intent-stage.py',
                    'source_upgrade_source_tree')
    require(stage.git_tree(entries) == identity['tree'], 'SOURCE_UPGRADE_SOURCE_DRIFT')
    tracked = {name: raw for name, _, raw in entries}
    derived = [verify_derived_cache(path, source, tracked) for path in sorted(caches)]
    groups = {
        'sourceTreeSha256': ['controller', 'runtime', 'consumer', 'contracts', 'reviewer', 'deploy'],
        'controllerSourceTreeSha256': ['consumer/consumer.mjs', 'consumer/consumer-config.mjs', 'controller/src',
            'runtime/src', 'runtime/config', 'contracts/src', 'reviewer/src/executable-cr-v2.json'],
        'codexLauncherSourceTreeSha256': ['deploy/ansible/roles/relay_codex_runtime/templates/relay-codex-launcher.mjs.j2',
            'deploy/ansible/roles/relay_codex_runtime/templates/relay-codex-cleanup.py.j2'],
        'reviewerSourceTreeSha256': ['reviewer', 'contracts/src/github-authority-v1.json', 'contracts/src/github-authority-v4.json'],
        'reviewerBuildInputsTreeSha256': ['deploy/ansible/group_vars/all.yml', 'deploy/ansible/site.yml',
            *['deploy/ansible/roles/' + name for name in ['relay_base', 'relay_preflight', 'relay_artifacts',
                'relay_runtime', 'relay_nginx', 'relay_docker_nginx']]],
    }
    for key, prefixes in groups.items():
        rows = [mode + ' blob ' + stage.git_object('blob', raw).hex() + '\t' + name
                for name, mode, raw in sorted(entries)
                if any(name == prefix or name.startswith(prefix + '/') for prefix in prefixes)]
        require(rows and hashlib.sha256('\n'.join(rows).encode()).hexdigest() == identity[key],
                'SOURCE_UPGRADE_SOURCE_DRIFT')
    require(all(file_stamp(path.lstat()) == stamp for path, stamp in observed),
            'SOURCE_UPGRADE_SOURCE_MOVED')
    return {'gitTree': identity['tree'], 'derivedCachesSha256': hashlib.sha256(canonical(derived)).hexdigest()}


def loaded_proof(values):
    import process_adoption as adoption
    payload = {'reviewerUnit': values['relay_reviewer_service_name'],
        'productionUnit': values['relay_production_runner_service_name'],
        'reviewerUser': values['relay_reviewer_user'], 'productionUser': values['relay_production_runner_user'],
        'productionRoot': values['relay_runner_root'], 'productionActive': True,
        'socket': values['relay_runtime_root'] + '/reviewer-proof/loaded.sock',
        'environmentFiles': [values['relay_config_root'] + '/relay.env',
                             values['relay_config_root'] + '/reviewer-credentials/github-app.env'],
        'config': values['relay_config_root'] + '/reviewer-mcp.json',
        'release': values['relay_install_root'] + '/current'}
    return adoption.capture_inputs(payload)


def _future_outcomes(futures):
    """Collect every result after executor shutdown has joined its readers."""
    results, errors = {}, []
    for name, future in futures.items():
        try:
            results[name] = future.result(timeout=0)
        except Exception as error:
            errors.append(error)
    return results, errors


def _raise_read_failures(errors):
    # Moving bindings/guards must never become an ordinary optimization miss
    # merely because another reader discovered unsupported inputs first.
    if errors:
        hard = next((error for error in errors if isinstance(error, RuntimeError)), None)
        unexpected = next((error for error in errors if not isinstance(
            error, (ValueError, OSError, subprocess.SubprocessError))), None)
        raise hard or unexpected or errors[0]


def package_proof(values, source_root, loaded, *, stage, operation, package_reference):
    import host_preflight
    package = _module(source_root, 'deploy/ansible/roles/relay_runner/files/relay-intent-package.py',
                      'source_upgrade_package')
    from source_upgrade_packages import verify_packages
    from source_upgrade_general import capture_general
    runners = host_preflight.runner_targets(values)
    if values.get('relay_general_runner_pool'):
        capacity = values['relay_general_runner_pool']['desiredCapacity']
        require(type(capacity) is int and 1 <= capacity <= 32, 'SOURCE_UPGRADE_POOL_CAPACITY_UNPROVEN')
        runners = runners[:1 + capacity]
    for runner in runners:
        package.inspect_live('runner', {'root': runner['root'], 'archive': values['relay_runner_package_archive']})
        package.runner_transition(None, {'root': runner['root'], 'user': runner['user'], 'service': runner['service']})
    # Listener --version may write ordinary _diag files. Complete every native
    # probe before any General capture, then overlap only independent readers.
    # The context joins every submitted task even when one result refuses.
    with ThreadPoolExecutor(max_workers=3, thread_name_prefix='relay-package-proof') as executor:
        codex_future = executor.submit(verify_packages, stage, operation, values, source_root, package_reference)
        general = {runner['label']: executor.submit(capture_general, runner, source_root)
                   for runner in runners if runner['label'] != 'production'}
    results, errors = _future_outcomes({'codex': codex_future, **general})
    _raise_read_failures(errors)
    codex_proof = results['codex']
    runner_rows = [{'label': runner['label'], 'proof': loaded['production']
                    if runner['label'] == 'production' else results[runner['label']]}
                   for runner in runners]
    recipe = hashlib.sha256(canonical(recipe_rows(source_root))).hexdigest()
    return {'runner': {'recipeSha256': recipe, 'treeSha256': hashlib.sha256(canonical(runner_rows)).hexdigest()},
            'codex': {'recipeSha256': recipe,
                      'treeSha256': hashlib.sha256(canonical(codex_proof)).hexdigest()},
            'activeRunnerUnits': [runner['service'] for runner in runners]}


def require_unchanged_pool_plan(plan):
    require(plan.get('status') == 'PASS' and not plan['createParents'] and bool(plan['members']) and all(
        not row['createDirectories'] and not row['installPackage']
        and not row['installUnit'] and not row['retiring'] for row in plan['members'].values()),
        'SOURCE_UPGRADE_POOL_RECONCILIATION_REQUIRED')


def pool_proof(config, digest, source_root):
    import managed_pool as pool
    import pool_authorization
    import serial_pool_installation
    contract = pool.pool_contract(config)
    template_path = Path(source_root) / 'deploy/ansible/roles/relay_runner/templates/relay-managed-pool.service.j2'
    template = protected_read(template_path, boundary=Path(source_root))[0].decode()
    plan = pool.installation_plan(contract, template)
    require_unchanged_pool_plan(plan)
    auth = pool_authorization.installation_authorization(config)
    require(all(auth.get(key) == contract[key] for key in ['organization', 'appId', 'installationId']),
            'SOURCE_UPGRADE_POOL_AUTH_UNPROVEN')
    github = pool.GitHub(auth['installationToken'], contract['organization'])
    group = github.qualify(contract)
    transition = serial_pool_installation.preflight(config, github, digest)
    require(transition is None or transition.get('phase') == 'retired'
            and not transition.get('completionRequired'), 'SOURCE_UPGRADE_POOL_TRANSITION_PENDING')
    members = contract['members'][:contract['desiredCapacity']]
    state = pool.State('/var/lib/codex-relay-pools/' + contract['name']).read()
    require(isinstance(state, dict) and state.get('binding') == pool.binding(contract)
            and set(state.get('members', {})) == {member['id'] for member in members}
            and all(row.get('phase') == 'ready' for row in state['members'].values()),
            'SOURCE_UPGRADE_POOL_RECONCILIATION_REQUIRED')
    host = pool.Host(contract)
    remote = github.runners()
    group_ids = {row['id'] for row in github.pages('/orgs/' + contract['organization']
                 + '/actions/runner-groups/' + str(group) + '/runners', 'runners')}
    rows = []
    for member in members:
        identifier = host.registration(member)
        found = [row for row in remote if row.get('id') == identifier]
        require(identifier is not None and identifier in group_ids and len(found) == 1
                and state['members'][member['id']].get('runnerId') == identifier
                and found[0].get('status') == 'online' and found[0].get('busy') is False
                and host.ready(member), 'SOURCE_UPGRADE_POOL_NOT_READY')
        labels = {label.get('name') for label in found[0].get('labels', [])}
        require(contract['label'] in labels and member['label'] in labels, 'SOURCE_UPGRADE_POOL_LABEL_CHANGED')
        rows.append({'member': member['id'], 'runnerId': identifier})
    return {'bindingSha256': hashlib.sha256(canonical(pool.binding(contract))).hexdigest(),
            'capacity': len(rows), 'members': rows}


def readiness_proof(values, *, execute=run):
    """The existing readiness predicates, without acquiring a competing Apply lock."""
    marker = Path(values['relay_reviewer_activation_marker'])
    raw, stamp = protected_read(marker)
    require(stat.S_IMODE(stamp[2]) == 0o600 and raw.rstrip(b'\n') == b'authorized',
            'SOURCE_UPGRADE_ACTIVATION_UNPROVEN')
    require(not os.path.lexists(values['relay_reviewer_recovery_off_marker']),
            'SOURCE_UPGRADE_RECOVERY_PENDING')
    unit = values['relay_reviewer_service_name']
    require(execute(['/bin/systemctl', 'is-enabled', unit]).stdout.strip() in [b'enabled', b'enabled-runtime'],
            'SOURCE_UPGRADE_REVIEWER_NOT_ENABLED')
    expected = values['relay_reviewer_bind_address'] + ':' + str(values['relay_reviewer_bind_port'])
    listeners = execute(['/bin/ss', '-H', '-ltnp']).stdout.decode().splitlines()
    matches = [line for line in listeners if len(line.split()) >= 4 and line.split()[3] == expected]
    require(len(matches) == 1, 'SOURCE_UPGRADE_LISTENER_UNPROVEN')
    pid = execute(['/bin/systemctl', 'show', unit, '--property=MainPID', '--value']).stdout.strip()
    require(pid.isdigit() and int(pid) > 0 and re.search(
        r'\bpid=' + re.escape(pid.decode()) + r',', matches[0]), 'SOURCE_UPGRADE_LISTENER_UNPROVEN')
    unchanged(protected_read(marker)[1] == stamp, 'SOURCE_UPGRADE_ACTIVATION_CHANGED')
    return {'activation': stamp, 'listener': expected, 'pid': int(pid)}


def runtime_support_proof(values, *, execute=run):
    # This file action is metadata-only: its secret/external bytes are qualified
    # by host_preflight and bound to the running Reviewer by loaded_proof.
    _, ca = protected_read(values['relay_tls_client_ca_file'], limit=256 * 1024)
    require(stat.S_IMODE(ca[2]) == 0o640
            and ca[4] == grp.getgrnam(values['relay_reviewer_group']).gr_gid,
            'SOURCE_UPGRADE_CLIENT_CA_METADATA_DRIFT')
    timer = values['relay_reviewer_recovery_timer_name']
    result = execute(['/bin/systemctl', 'show', timer,
                      '--property=LoadState,ActiveState,UnitFileState,NeedDaemonReload'])
    state = dict(line.split('=', 1) for line in result.stdout.decode().splitlines())
    require(state == {'LoadState': 'loaded', 'ActiveState': 'active', 'UnitFileState': 'enabled',
                      'NeedDaemonReload': 'no'}, 'SOURCE_UPGRADE_RECOVERY_TIMER_DRIFT')
    return {'clientCa': ca, 'recoveryTimer': state}


def prerequisite_proof(values, *, execute=run):
    if not values['relay_manage_base_packages']:
        return {'managed': False}
    packages = values['relay_base_packages']
    require(isinstance(packages, list) and packages and all(isinstance(name, str)
            and re.fullmatch('[a-z0-9][a-z0-9+.-]*', name) for name in packages),
            'SOURCE_UPGRADE_PREREQUISITE_RECIPE_UNPROVEN')
    expected = set(packages) | {'bubblewrap'}
    result = execute(['/usr/bin/dpkg-query', '--show', '--showformat=${Package}\t${Status}\n', *sorted(expected)])
    rows = [line.split('\t') for line in result.stdout.decode().splitlines()]
    require(len(rows) == len(expected) and {row[0] for row in rows} == expected
            and all(len(row) == 2 and row[1] == 'install ok installed' for row in rows),
            'SOURCE_UPGRADE_PREREQUISITE_MISSING')
    return {'managed': True, 'installed': sorted(expected)}


def lifecycle_unit_proof(values, *, execute=None, active_runners=()):
    logical = [values['relay_general_runner_service_name'],
               *[slot['relay_runner_service_name'] for slot in values['relay_additional_execution_slots']]]
    socket = values['relay_namespace'] + '-relay-manual-outcome.socket'
    units = [values['relay_reviewer_service_name'], values['relay_production_runner_service_name'], socket, *logical]
    require(len(set(units)) == len(units) and all(re.fullmatch('[A-Za-z0-9@_.-]+', unit) for unit in units),
            'SOURCE_UPGRADE_SERVICE_RECIPE_UNPROVEN')
    argv = ['/bin/systemctl', 'show', *units,
            '--property=Id,LoadState,ActiveState,SubState,UnitFileState,NeedDaemonReload']
    result = (execute(argv) if execute else subprocess.run(argv, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=30, check=False,
        env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'}))
    # systemctl show returns 1 for the explicitly permitted not-found logical
    # units. Every requested unit must still supply its complete typed state.
    require(result.returncode in [0, 1] and len(result.stdout) <= 65536,
            'SOURCE_UPGRADE_SERVICE_STATE_UNPROVEN')
    observed = {}
    for block in result.stdout.decode().strip().split('\n\n'):
        pairs = [line.split('=', 1) for line in block.splitlines()]
        require(all(len(pair) == 2 for pair in pairs), 'SOURCE_UPGRADE_SERVICE_STATE_UNPROVEN')
        row = dict(pairs)
        unit = row.pop('Id', None)
        require(unit in units and unit not in observed and len(pairs) == len(row) + 1,
                'SOURCE_UPGRADE_SERVICE_STATE_UNPROVEN')
        require(row.get('NeedDaemonReload') == 'no', 'SOURCE_UPGRADE_DAEMON_RELOAD_REQUIRED')
        require(row.get('LoadState') == 'loaded' or unit in logical and row.get('LoadState') == 'not-found',
                'SOURCE_UPGRADE_SERVICE_STATE_UNPROVEN')
        if unit in logical:
            # Pool projection uses these same fixed logical names for its
            # first physical members. Their complete loaded/distribution proof
            # must already have succeeded; other active logical units refuse.
            require(row.get('ActiveState') in ['inactive', 'failed'] or unit in active_runners
                    and row.get('ActiveState') == 'active' and row.get('SubState') == 'running'
                    and row.get('LoadState') == 'loaded'
                    and row.get('UnitFileState') in ['enabled', 'enabled-runtime'],
                    'SOURCE_UPGRADE_LOGICAL_RUNNER_ACTIVE')
        elif unit == socket:
            require((row.get('ActiveState') == 'active' and row.get('SubState') == 'listening')
                    or row.get('ActiveState') in ['inactive', 'failed'],
                    'SOURCE_UPGRADE_MANUAL_SOCKET_UNHEALTHY')
        else:
            require(row.get('ActiveState') == 'active' and row.get('SubState') == 'running',
                    'SOURCE_UPGRADE_SERVICE_STATE_UNPROVEN')
        observed[unit] = row
    require(set(observed) == set(units), 'SOURCE_UPGRADE_SERVICE_STATE_UNPROVEN')
    return observed


def runtime_imports(values, *, execute=run):
    release = values['relay_install_root'] + '/current'
    result = execute(['/usr/sbin/runuser', '-u', values['relay_dispatch_user'], '--',
        '/usr/bin/env', '-i', 'PATH=/usr/bin:/bin',
        'RELAY_CONSUMER_CONFIG=' + values['relay_consumer_config_path'],
        'RELAY_REPOSITORY=' + values['relay_github_repository'], '/usr/bin/node', '--input-type=module', '-e',
        'import {pathToFileURL} from "node:url"; for(const path of process.argv.slice(2)) await import(pathToFileURL(path)); console.log("INSTALLED_RELAY_IMPORTS_READY");',
        'installed-import', release + '/bin/relay-routing.mjs', release + '/bin/relay-publication-recovery.mjs'],
        cwd='/')
    require(result.stdout.strip() == b'INSTALLED_RELAY_IMPORTS_READY',
            'SOURCE_UPGRADE_RUNTIME_IMPORTS_UNPROVEN')


def prove(values, config, source_root, catalogue, expected_binding=None, *,
          stage, operation, package_reference):
    from host_preflight import resolved, inspect_inputs
    from installed_state import audit_catalogue
    v = gateway_values(resolved(values))
    binding, manifest, identity, snapshot = read_binding(v)
    if expected_binding is not None:
        unchanged(binding == expected_binding, 'SOURCE_UPGRADE_BINDING_CHANGED')
    require(normalized_config(snapshot) == normalized_config(config), 'SOURCE_UPGRADE_CONFIG_CHANGED')
    source_proof = verify_source_tree(binding, identity, snapshot, catalogue, source_root)
    v.update(relay_intent_preflight_installed_revision=binding['revision'])
    digest = v.get('relay_source_reuse_consumer_digest')
    require(isinstance(digest, str) and re.fullmatch('[0-9a-f]{64}', digest),
            'SOURCE_UPGRADE_CONSUMER_DIGEST_UNPROVEN')
    with ThreadPoolExecutor(max_workers=3, thread_name_prefix='relay-live-proof') as executor:
        host_future = executor.submit(inspect_inputs, v, source_root)
        pool_future = executor.submit(pool_proof, config, digest, source_root)
        loaded_future = executor.submit(loaded_proof, v)
        dependency_errors = []
        try:
            loaded = loaded_future.result(timeout=180)
            # Production capture must precede packages. Host/App/TLS and pool
            # continue while the independent packages are checked.
            packages = package_proof(v, source_root, loaded, stage=stage, operation=operation,
                                     package_reference=package_reference)
        except Exception as error:
            dependency_errors.append(error)
    results, errors = _future_outcomes({'host': host_future, 'pool': pool_future, 'loaded': loaded_future})
    _raise_read_failures([*errors, *dependency_errors])
    host, pool, loaded = results['host'], results['pool'], results['loaded']
    require(host.get('status') == 'PASS' and not host.get('pendingProductMaterial')
            and all(value == 0 for value in host.get('identityPlan', {}).values()),
            'SOURCE_UPGRADE_HOST_RECONCILIATION_REQUIRED')
    readiness = readiness_proof(v)
    support = runtime_support_proof(v)
    prerequisites = prerequisite_proof(v)
    runtime_imports(v)
    units = lifecycle_unit_proof(v, active_runners=packages['activeRunnerUnits'])
    # Each predicate above owns these checks; no caller-provided success flags.
    flags = {name: True for name in ['identities', 'mutableState', 'packages', 'pool',
                                   'ingress', 'loadedProcesses', 'sealedRelease']}
    state = audit_catalogue(catalogue, live_checks=flags)
    unchanged(read_binding(v)[0] == binding, 'SOURCE_UPGRADE_BINDING_CHANGED')
    unchanged(loaded_proof(v) == loaded, 'SOURCE_UPGRADE_PROCESS_MOVED')
    unchanged(readiness_proof(v) == readiness, 'SOURCE_UPGRADE_READINESS_CHANGED')
    unchanged(runtime_support_proof(v) == support, 'SOURCE_UPGRADE_RUNTIME_SUPPORT_CHANGED')
    unchanged(lifecycle_unit_proof(v, active_runners=packages['activeRunnerUnits']) == units,
              'SOURCE_UPGRADE_SERVICE_STATE_CHANGED')
    unchanged(prerequisite_proof(v) == prerequisites, 'SOURCE_UPGRADE_PREREQUISITES_CHANGED')
    return {'binding': binding, 'loaded': loaded, 'host': host,
            'packages': packages, 'pool': pool, 'catalogue': state, 'readiness': readiness,
            'runtimeSupport': support, 'prerequisites': prerequisites, 'lifecycleUnits': units,
            'source': source_proof}
