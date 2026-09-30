#!/usr/bin/env python3
"""Bounded HTTP-01 bootstrap through an existing admitted Docker nginx.

Called only by the explicit public TLS phases under the deployment operation
lock. All subprocess output is captured; failures expose fixed diagnostics, not
Certbot account, contact or key data. Never stops an existing service.
"""
import argparse
import fnmatch
import grp
import hashlib
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import socket
import stat
import subprocess
import tempfile
import urllib.request

from bootstrap_guard import ProtectedPath, mutation_guard

CERTBOT_GLOBAL_CONFIG = '/etc/letsencrypt/cli.ini'
# Debian bookworm certbot 2.1.0-4 ships only max-log-backups=0 and
# preconfigured-renewal=True here. Package SHA256:
# c39721449ddbd5c2252e92df92cf4dfcbecc97b0b8a5df0ccf6df2d48265eddc.
# Admit those exact public package bytes, never arbitrary global hooks/options.
DEBIAN_CERTBOT_CONFIG_SHA256 = 'c0d5962eea9582f552fd2a235e0c0c3869c6c84c20359c8926eee8809d4d6872'

OPENAI_CAS = (
    ('openai-root-ca.pem', 'https://developers.openai.com/plugins/mtls/openai-root-ca.pem',
     '493D9A1EDC48D558F5A28764B20605205A50E1DF4840231E342F2E0E8CDD5BE9'),
    ('openai-connectors-mtls-ca.pem',
     'https://developers.openai.com/plugins/mtls/openai-connectors-mtls-ca.pem',
     'DA3D8E2E32EE4981EA1152C1456F866C863DBDE2FBF4F8EBA8850DF74B656816'),
)


class BootstrapError(Exception):
    pass


def require(condition, code):
    if not condition:
        raise BootstrapError(code)


def safe_path(path, *, directory=False, absent=False):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts, 'TLS_PATH_INVALID')
    for parent in reversed(path.parents):
        try:
            metadata = parent.lstat()
        except FileNotFoundError:
            require(absent, 'TLS_PARENT_MISSING')
            return
        require(stat.S_ISDIR(metadata.st_mode) and metadata.st_uid == 0 and
                metadata.st_mode & 0o022 == 0, 'TLS_PARENT_UNSAFE')
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        require(absent, 'TLS_PATH_MISSING')
        return
    require((stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode))
            and metadata.st_uid == 0 and metadata.st_mode & 0o022 == 0,
            'TLS_PATH_UNSAFE')


def execute(argv):
    environment = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C', 'HOME': '/root'}
    if argv[0] == '/usr/bin/certbot' and '--config-dir' in argv:
        state = Path(argv[argv.index('--config-dir') + 1]).parent
        environment.update(HOME=str(state / 'home'), XDG_CONFIG_HOME=str(state / 'home' / '.config'))
    try:
        result = subprocess.run(argv, text=True, capture_output=True, check=False,
                                timeout=600, env=environment)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise BootstrapError('TLS_SUBPROCESS_FAILED') from error
    require(result.returncode == 0, 'TLS_SUBPROCESS_FAILED')
    if 'nginx' in argv and ('-t' in argv or '-T' in argv):
        require(re.search(r'\[warn\]|conflicting server name', result.stdout + result.stderr,
                          re.IGNORECASE) is None,
                'TLS_INGRESS_VALIDATION_WARNING')
    return result.stdout


def write_atomic(path, data, mode=0o640, *, exclusive=False):
    path = Path(path)
    safe_path(path, absent=True)
    fd, temporary = tempfile.mkstemp(prefix='.relay-tls-', dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, 'wb') as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        if exclusive:
            os.link(temporary, path, follow_symlinks=False)
        else:
            os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_record(path, data):
    write_atomic(path, (json.dumps(data, sort_keys=True) + '\n').encode())


def validate_config(config):
    require(config['phase'] in ('check', 'prerequisites', 'dry_run', 'issue'), 'TLS_PHASE_INVALID')
    require(re.fullmatch('[0-9a-f]{40}', config['head']) is not None,
            'TLS_ACME_EXACT_HEAD_REQUIRED')
    require(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+',
                         config['hostname']) is not None, 'TLS_HOSTNAME_INVALID')
    require(re.fullmatch('[a-z][a-z0-9-]{0,47}', config['namespace']) is not None,
            'TLS_NAMESPACE_INVALID')
    issuance = config['phase'] in ('dry_run', 'issue')
    if issuance:
        require(re.fullmatch(r'[^\s@]+@[^\s@]+', config['email']) is not None,
                'TLS_ACME_OWNER_EMAIL_REQUIRED')
        require(config.get('method') == 'webroot', 'TLS_ACME_SUPPORTED_METHOD_REQUIRED')
        require(isinstance(config['addresses'], list) and config['addresses'],
                'TLS_PUBLIC_ADDRESSES_REQUIRED')
    try:
        addresses = sorted({str(ipaddress.ip_address(value)) for value in config['addresses']})
    except ValueError as error:
        raise BootstrapError('TLS_PUBLIC_ADDRESSES_INVALID') from error
    require(len(addresses) == len(config['addresses']), 'TLS_PUBLIC_ADDRESSES_AMBIGUOUS')
    config['addresses'] = addresses
    # Paths appear in nginx syntax; prohibit shell/nginx metacharacters even
    # though subprocess execution itself uses argv without a shell.
    paths = ['conf_root', 'state_root', 'marker', 'client_ca', 'preparation_root',
             'certificate', 'private_key', 'manifest', 'lock_file', 'operation_record']
    if issuance:
        paths.append('webroot')
    for name in paths:
        require(re.fullmatch('/[A-Za-z0-9_./-]+', config[name]) is not None,
                'TLS_PATH_INVALID')
    require(config['certbot'] == '/usr/bin/certbot', 'TLS_CERTBOT_PROVENANCE_INVALID')
    require(re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]*', config['container']) is not None,
            'TLS_CONTAINER_INVALID')
    require(re.fullmatch('[a-z][a-z0-9-]{0,63}', config['reviewer_group']) is not None,
            'TLS_REVIEWER_GROUP_INVALID')
    preparation = Path(config['preparation_root'])
    require(Path(config['state_root']) == preparation / 'certbot' and
            Path(config['marker']) == preparation / 'acme-http01-dry-run-passed',
            'TLS_NAMESPACE_PATH_MISMATCH')


def ensure_directory(path, mode=0o700, group=0):
    path = Path(path)
    safe_path(path, directory=True, absent=True)
    if not path.exists():
        path.mkdir(mode=mode)
        path.chmod(mode)
        os.chown(path, 0, group)


def validate_ca(path, fingerprint):
    safe_path(path)
    actual = execute(['openssl', 'x509', '-in', str(path), '-noout', '-fingerprint', '-sha256'])
    require(actual.strip().split('=', 1)[-1].replace(':', '').upper() == fingerprint,
            'TLS_OPENAI_CA_IDENTITY_MISMATCH')
    execute(['openssl', 'x509', '-in', str(path), '-noout', '-checkend', '0'])
    constraints = execute(['openssl', 'x509', '-in', str(path), '-noout', '-text'])
    require('CA:TRUE' in constraints and 'Certificate Sign' in constraints,
            'TLS_OPENAI_CA_CONSTRAINTS_INVALID')


def download_ca(url):
    # Exact official HTTPS URLs only; redirects cannot silently select another
    # host, and pinned certificate identity is independently verified below.
    with urllib.request.urlopen(url, timeout=30) as response:
        require(response.geturl() == url, 'TLS_OPENAI_CA_REDIRECT_REJECTED')
        data = response.read(128 * 1024 + 1)
    require(0 < len(data) <= 128 * 1024, 'TLS_OPENAI_CA_DOWNLOAD_INVALID')
    return data


def prepare_ca(config):
    preparation = Path(config['preparation_root'])
    group = grp.getgrnam(config['reviewer_group']).gr_gid
    ensure_directory(preparation)
    ensure_directory(Path(config['client_ca']).parent, 0o750, group)
    cert_directory = Path(config['client_ca']).parent.stat()
    require(cert_directory.st_gid == group and stat.S_IMODE(cert_directory.st_mode) == 0o750,
            'TLS_OPENAI_CA_DIRECTORY_UNREADABLE_OR_UNSAFE')
    paths = []
    for name, url, fingerprint in OPENAI_CAS:
        destination = preparation / name
        safe_path(destination, absent=True)
        if destination.exists():
            validate_ca(destination, fingerprint)
        else:
            with tempfile.TemporaryDirectory(prefix='.ca-', dir=preparation) as temporary:
                staged = Path(temporary) / name
                write_atomic(staged, download_ca(url), 0o644)
                validate_ca(staged, fingerprint)
                write_atomic(destination, staged.read_bytes(), 0o644)
        paths.append(destination)
    execute(['openssl', 'verify', '-CAfile', str(paths[0]), str(paths[0]), str(paths[1])])
    bundle = b''.join(path.read_bytes().rstrip() + b'\n' for path in paths)
    destination = Path(config['client_ca'])
    safe_path(destination, absent=True)
    if destination.exists():
        require(destination.read_bytes() == bundle, 'TLS_OPENAI_CA_EXISTING_BUNDLE_MISMATCH')
        metadata = destination.stat()
        require(metadata.st_gid == group and stat.S_IMODE(metadata.st_mode) == 0o640,
                'TLS_OPENAI_CA_BUNDLE_UNSAFE_PERMISSIONS')
    else:
        write_atomic(destination, bundle)
        os.chown(destination, 0, group)


def certbot_configuration_identity():
    # Certbot/ConfigArgParse merge global defaults even with --config supplied.
    # Never execute unknown global hooks/options or erase a foreign cli.ini.
    safe_path(CERTBOT_GLOBAL_CONFIG, absent=True)
    if not os.path.lexists(CERTBOT_GLOBAL_CONFIG):
        return 'absent'
    try:
        with ProtectedPath(CERTBOT_GLOBAL_CONFIG) as protected:
            contents, _ = protected.read({0o600, 0o640, 0o644}, group=0)
    except (OSError, ValueError) as error:
        raise BootstrapError('TLS_CERTBOT_GLOBAL_CONFIGURATION_AMBIGUOUS') from error
    digest = hashlib.sha256(contents).hexdigest()
    require(digest == DEBIAN_CERTBOT_CONFIG_SHA256, 'TLS_CERTBOT_GLOBAL_CONFIGURATION_AMBIGUOUS')
    return digest


def certbot_provenance(config):
    certbot_configuration_identity()
    executable = Path(config['certbot'])
    if not executable.exists():
        execute(['apt-get', '-y', '--no-install-recommends', 'install', 'certbot'])
    certbot_configuration_identity()
    safe_path(executable)
    require(executable.resolve() == executable, 'TLS_CERTBOT_PROVENANCE_INVALID')
    require(execute(['dpkg-query', '-S', str(executable)]).startswith('certbot:'),
            'TLS_CERTBOT_PROVENANCE_INVALID')
    require(execute(['dpkg-query', '-W', '-f=${Status}', 'certbot']) == 'install ok installed',
            'TLS_CERTBOT_PROVENANCE_INVALID')


def validator_module():
    spec = importlib.util.spec_from_file_location('tls_source_validate',
                                                Path(__file__).with_name('tls-source-validate.py'))
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    return validator


def check_dns(config):
    try:
        actual = {str(ipaddress.ip_address(entry[4][0])) for entry in
                  socket.getaddrinfo(config['hostname'], 80, socket.AF_UNSPEC, socket.SOCK_STREAM)}
    except (OSError, ValueError) as error:
        raise BootstrapError('TLS_PUBLIC_DNS_UNAVAILABLE') from error
    require(actual == set(config['addresses']), 'TLS_PUBLIC_DNS_MISMATCH')


def check_container(config):
    inspected = json.loads(execute(['docker', 'inspect', config['container']]))
    require(len(inspected) == 1, 'TLS_INGRESS_IDENTITY_AMBIGUOUS')
    container = inspected[0]
    require(container['Name'] == '/' + config['container'] and
            container['Config']['Image'] == config['image'] and
            container['State']['Running'], 'TLS_INGRESS_IDENTITY_MISMATCH')
    for source, destination in ((config['conf_root'], '/etc/nginx/conf.d'),
                                (config['webroot'], '/var/www/html')):
        mounts = [mount for mount in container['Mounts'] if mount['Destination'] == destination]
        require(len(mounts) == 1 and mounts[0]['Type'] == 'bind' and
                mounts[0]['Source'] == source, 'TLS_INGRESS_MOUNT_MISMATCH')
    ports = container['NetworkSettings']['Ports']
    for port in ('80', '443'):
        require(any(binding['HostPort'] == port for binding in (ports.get(port + '/tcp') or [])),
                'TLS_INGRESS_PUBLIC_PORT_MISMATCH')
    return container['Id']


def fragment_text(config):
    return ('# Relay temporary ACME challenge; do not edit\nserver {\n'
            '    listen 80;\n    listen [::]:80;\n'
            f"    server_name {config['hostname']};\n"
            '    location ^~ /.well-known/acme-challenge/ {\n'
            '        root /var/www/html;\n        try_files $uri =404;\n    }\n'
            '    location / { return 404; }\n}\n').encode()


def check_conflicts(config, fragment, container_id):
    # Inspect only the explicitly admitted conf.d directory, never arbitrary
    # protected paths. A pre-existing hostname is ambiguous; no foreign server
    # block is rewritten or disabled to make the challenge work.
    contents = []
    for path in Path(config['conf_root']).glob('*.conf'):
        safe_path(path)
        require(path.stat().st_size <= 1024 * 1024, 'TLS_INGRESS_CONFIG_TOO_LARGE')
        contents.append(path.read_text())
        require(path != fragment, 'TLS_ACME_FRAGMENT_ALREADY_EXISTS')
    # nginx -T expands runtime includes, which may otherwise hide a wildcard or
    # regex hostname in a non-.conf snippet. This is the pinned control plane's
    # effective configuration; its contents are never printed or logged.
    effective = execute(['docker', 'exec', container_id, 'nginx', '-T'])
    require(len(effective.encode()) <= 8 * 1024 * 1024, 'TLS_INGRESS_CONFIG_TOO_LARGE')
    contents.append(effective)
    for content in contents:
        for names in re.findall(r'\bserver_name\s+([^;]+);', re.sub(r'#.*', '', content)):
            for name in names.split():
                name = name.strip('\"\'')
                require(not name.startswith('~') and '$' not in name,
                        'TLS_ACME_HOSTNAME_ROUTING_AMBIGUOUS')
                matches = (fnmatch.fnmatchcase(config['hostname'], name) or
                           (name.startswith('.') and (config['hostname'] == name[1:] or
                                                       config['hostname'].endswith(name))))
                require(not matches, 'TLS_ACME_HOSTNAME_ALREADY_ROUTED')


def reload_nginx(config, container_id):
    require(check_container(config) == container_id, 'TLS_INGRESS_CONTAINER_CHANGED')
    execute(['docker', 'exec', container_id, 'nginx', '-t'])
    execute(['docker', 'exec', container_id, 'nginx', '-s', 'reload'])


def probe_challenge(config):
    directory = Path(config['webroot']) / '.well-known' / 'acme-challenge'
    for parent in (directory.parent, directory):
        safe_path(parent, directory=True, absent=True)
        if not parent.exists():
            parent.mkdir(mode=0o755)
            parent.chmod(0o755)
        require(stat.S_IMODE(parent.stat().st_mode) == 0o755,
                'TLS_ACME_CHALLENGE_DIRECTORY_UNREADABLE_OR_UNSAFE')
    token = 'relay-' + secrets.token_hex(24)
    path = directory / token
    contents = secrets.token_hex(32)
    write_atomic(path, contents.encode(), 0o644)
    try:
        for address in config['addresses']:
            formatted = '[' + address + ']' if ':' in address else address
            result = execute(['curl', '--fail', '--silent', '--show-error', '--noproxy', '*',
                              '--max-time', '15', '--max-redirs', '0', '--resolve',
                              f"{config['hostname']}:80:{formatted}",
                              f"http://{config['hostname']}/.well-known/acme-challenge/{token}"])
            require(result == contents, 'TLS_ACME_CHALLENGE_UNREACHABLE')
    finally:
        path.unlink()


def binding(config):
    global_configuration = certbot_configuration_identity()
    return {'schema': 2, 'head': config['head'], 'hostname': config['hostname'],
            'contact_sha256': hashlib.sha256(config['email'].encode()).hexdigest(),
            'method': config['method'], 'webroot': config['webroot'],
            'addresses': config['addresses'], 'container': config['container'],
            'image': config['image'], 'conf_root': config['conf_root'],
            'state_root': config['state_root'], 'certbot': config['certbot'],
            'certbot_global_configuration': global_configuration,
            'certbot_version': execute([config['certbot'], '--config', '/dev/null', '--config-dir',
                                       str(Path(config['state_root']) / 'config'), '--version']).strip(),
            'client_ca_sha256': hashlib.sha256(Path(config['client_ca']).read_bytes()).hexdigest(),
            'provenance': 'debian-package'}


def publish_certificate(config):
    root = Path(config['state_root']) / 'config'
    lineage = root / 'live' / config['hostname']
    archive = root / 'archive' / config['hostname']
    safe_path(lineage, directory=True)
    safe_path(archive, directory=True)
    sources = []
    for name in ('fullchain.pem', 'privkey.pem'):
        source = lineage / name
        require(source.is_symlink() and source.lstat().st_uid == 0,
                'TLS_CERTBOT_LINEAGE_INVALID')
        resolved = source.resolve(strict=True)
        require(resolved.parent == archive, 'TLS_CERTBOT_LINEAGE_ESCAPES_NAMESPACE')
        safe_path(resolved)
        require(resolved.stat().st_size <= 1024 * 1024, 'TLS_CERTBOT_SOURCE_TOO_LARGE')
        sources.append(resolved)
    validator = validator_module()
    certificate_generation = re.fullmatch(r'fullchain([1-9][0-9]*)\.pem', sources[0].name)
    key_generation = re.fullmatch(r'privkey([1-9][0-9]*)\.pem', sources[1].name)
    require(certificate_generation and key_generation and
            certificate_generation[1] == key_generation[1], 'TLS_CERTBOT_GENERATION_MISMATCH')
    validator.validate_sources(sources[0], sources[1], config['hostname'])
    with tempfile.TemporaryDirectory(prefix='.certificate-', dir=config['state_root']) as temporary:
        cert, key = Path(temporary) / 'fullchain.pem', Path(temporary) / 'privkey.pem'
        write_atomic(cert, sources[0].read_bytes(), 0o644)
        write_atomic(key, sources[1].read_bytes(), 0o600)
        validator.validate_sources(cert, key, config['hostname'])
        # Product-managed destinations are immutable inputs to a later explicit
        # ingress phase. Publishing never activates/reloads TLS or Reviewer.
        require(not os.path.lexists(config['private_key']) and not os.path.lexists(config['certificate']),
                'TLS_MANAGED_DESTINATION_ALREADY_EXISTS')
        write_atomic(config['private_key'], key.read_bytes(), 0o600, exclusive=True)
        published_key = Path(config['private_key']).stat()
        try:
            write_atomic(config['certificate'], cert.read_bytes(), 0o644, exclusive=True)
        except BaseException:
            current = Path(config['private_key']).lstat()
            if (current.st_dev, current.st_ino) == (published_key.st_dev, published_key.st_ino):
                Path(config['private_key']).unlink()
            raise


def run(config):
    validate_config(config)
    safe_path(Path(config['manifest']).resolve(strict=True))
    require(json.loads(Path(config['manifest']).read_text())['commit'] == config['head'],
            'TLS_ACME_QUALIFIED_HEAD_MISMATCH')
    if config['phase'] == 'check':
        for name in ('preparation_root', 'state_root'):
            safe_path(config[name], directory=True, absent=True)
        for name in ('marker', 'client_ca'):
            safe_path(config[name], absent=True)
        if not config.get('allow_legacy_lineage', False):
            for name in ('certificate', 'private_key'):
                safe_path(config[name], absent=True)
        if Path(config['certificate']).exists() or Path(config['private_key']).exists():
            validator_module().validate_sources(config['certificate'], config['private_key'], config['hostname'],
                                                allow_letsencrypt_lineage=config.get('allow_legacy_lineage', False))
        return {'status': 'TLS_PREPARATION_CHECK_MODE_PASS', 'ca_preparation': 'explicit',
                'issuance': 'explicit', 'ingress': 'unchanged'}
    with mutation_guard(config['lock_file'], config['operation_record'], config['manifest'], config['head']):
        return run_mutating(config)


def run_mutating(config):
    previous = None
    if config['phase'] in ('dry_run', 'issue'):
        ensure_directory(config['preparation_root'])
        safe_path(config['marker'], absent=True)
        if config['phase'] == 'issue' and Path(config['marker']).exists():
            previous = json.loads(Path(config['marker']).read_text())
        # Invalidate before any bootstrap, including failed CA or DNS checks.
        write_record(config['marker'], {'status': 'TLS_ACME_DRY_RUN_INVALIDATED'})
    prepare_ca(config)
    if config['phase'] == 'prerequisites':
        return {'status': 'TLS_PREPARATION_PREREQUISITES_READY'}
    # Reuse already-valid managed material without any ACME/account/ingress
    # work. An invalid existing pair is never silently replaced or rotated.
    if Path(config['certificate']).exists() or Path(config['private_key']).exists():
        validator_module().validate_sources(config['certificate'], config['private_key'], config['hostname'])
        return {'status': 'TLS_EXISTING_CERTIFICATE_REUSED'}
    for name in ('webroot', 'conf_root'):
        safe_path(config[name], directory=True)
    ensure_directory(config['state_root'])
    ensure_directory(Path(config['state_root']) / 'home')
    ensure_directory(Path(config['state_root']) / 'home' / '.config')
    require(not os.path.lexists(Path(config['state_root']) / 'home' / '.config' / 'letsencrypt' / 'cli.ini'),
            'TLS_CERTBOT_USER_CONFIGURATION_AMBIGUOUS')
    # Certbot may have completed a prior issuance before interrupted publishing.
    # Reuse only fully validated material through the explicit issue phase.
    lineage = Path(config['state_root']) / 'config' / 'live' / config['hostname']
    if os.path.lexists(lineage):
        require(config['phase'] == 'issue', 'TLS_EXISTING_LINEAGE_REQUIRES_ISSUE_REUSE')
        publish_certificate(config)
        return {'status': 'TLS_EXISTING_CERTIFICATE_REUSED'}
    for name in ('marker', 'certificate', 'private_key'):
        safe_path(config[name], absent=True)
    certbot_provenance(config)
    renewal = Path(config['state_root']) / 'config' / 'renewal'
    hooks = Path(config['state_root']) / 'config' / 'renewal-hooks'
    for directory in (renewal, hooks):
        safe_path(directory, directory=True, absent=True)
    require(not renewal.exists() or not any(renewal.iterdir()),
            'TLS_CERTBOT_EXISTING_RENEWAL_STATE_AMBIGUOUS')
    if hooks.exists():
        # Certbot creates these empty directories even with hooks disabled.
        for directory in hooks.iterdir():
            require(directory.name in ('pre', 'deploy', 'post'),
                    'TLS_CERTBOT_EXISTING_RENEWAL_STATE_AMBIGUOUS')
            safe_path(directory, directory=True)
            require(not any(directory.iterdir()), 'TLS_CERTBOT_EXISTING_RENEWAL_STATE_AMBIGUOUS')
    if config['phase'] == 'issue':
        require(previous is not None, 'TLS_ACME_DRY_RUN_REQUIRED')
    check_dns(config)
    current_binding = binding(config)
    if previous is not None:
        require(previous == {'status': 'TLS_ACME_DRY_RUN_PASSED', 'binding': current_binding},
                'TLS_ACME_DRY_RUN_BINDING_INVALID_OR_STALE')
    container_id = check_container(config)
    fragment = Path(config['conf_root']) / (config['namespace'] + '-acme.conf')
    check_conflicts(config, fragment, container_id)
    execute(['docker', 'exec', container_id, 'nginx', '-t'])
    fragment_created = False
    try:
        write_atomic(fragment, fragment_text(config), 0o644)
        fragment_created = True
        reload_nginx(config, container_id)
        probe_challenge(config)
        check_dns(config)
        require(check_container(config) == container_id, 'TLS_INGRESS_CONTAINER_CHANGED')
        server = ('https://acme-staging-v02.api.letsencrypt.org/directory' if config['phase'] == 'dry_run'
                  else 'https://acme-v02.api.letsencrypt.org/directory')
        argv = [config['certbot'], '--config', '/dev/null', 'certonly', '--webroot',
                '--no-directory-hooks', '--max-log-backups', '3', '--server', server,
                '--webroot-path', config['webroot'],
                '--preferred-challenges', 'http', '--non-interactive', '--agree-tos',
                '--email', config['email'], '--keep-until-expiring', '--cert-name', config['hostname'],
                '-d', config['hostname']]
        for kind in ('config', 'work', 'logs'):
            directory = Path(config['state_root']) / kind
            safe_path(directory, directory=True, absent=True)
            directory.mkdir(mode=0o700, exist_ok=True)
            argv += ['--' + kind + '-dir', str(directory)]
        if config['phase'] == 'dry_run':
            argv.append('--dry-run')
        require(certbot_configuration_identity() == current_binding['certbot_global_configuration'],
                'TLS_CERTBOT_GLOBAL_CONFIGURATION_CHANGED')
        execute(argv)
        if config['phase'] == 'issue':
            publish_certificate(config)
    finally:
        if fragment_created:
            # Do not overwrite/delete a concurrent edit or reload an unpinned
            # replacement container; fail closed for explicit reconciliation.
            safe_path(fragment)
            require(fragment.read_bytes() == fragment_text(config), 'TLS_ACME_FRAGMENT_CHANGED')
            fragment.unlink()
            reload_nginx(config, container_id)
    if config['phase'] == 'dry_run':
        write_record(config['marker'], {'status': 'TLS_ACME_DRY_RUN_PASSED', 'binding': current_binding})
    return {'status': 'TLS_ACME_DRY_RUN_PASSED' if config['phase'] == 'dry_run' else
            'TLS_CERTIFICATE_KEY_VALIDATED'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    arguments = parser.parse_args()
    try:
        require(os.geteuid() == 0, 'TLS_ROOT_REQUIRED')
        safe_path(arguments.config)
        result = run(json.loads(Path(arguments.config).read_text()))
    except Exception as error:
        print(json.dumps({'status': 'BLOCKED', 'reason': str(error) if isinstance(error, BootstrapError)
                          else 'TLS_BOOTSTRAP_VALIDATION_FAILED'}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
