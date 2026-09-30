"""Exercise bootstrap state transitions without any live ingress/ACME calls."""
from contextlib import ExitStack
import copy
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


TOOLS = Path(__file__).resolve().parents[1] / 'tools'
# Exact /etc/letsencrypt/cli.ini from Debian bookworm certbot_2.1.0-4_all.deb;
# distribution package SHA256 is recorded beside the implementation allowlist.
DEBIAN_STOCK_CONFIG = (
    b'# Because we are using logrotate for greater flexibility, disable the\n'
    b'# internal certbot logrotation.\n'
    b'max-log-backups = 0\n'
    b'# Adjust interactive output regarding automated renewal\n'
    b'preconfigured-renewal = True\n'
)
sys.path.insert(0, str(TOOLS))
SPEC = importlib.util.spec_from_file_location('tls_bootstrap', TOOLS / 'tls-webroot-bootstrap.py')
TLS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TLS)


@unittest.skipUnless(os.name != 'nt' and os.geteuid() == 0, 'root native Linux protected filesystem required')
class BootstrapExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='relay-tls-test-', dir='/root')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.head = 'a' * 40
        for directory in ('webroot', 'conf', 'state', 'certs', 'runtime', 'install'):
            (self.root / directory).mkdir(mode=0o755)
        (self.root / 'certs').chmod(0o750)
        release = self.root / 'install' / 'releases' / self.head
        release.mkdir(parents=True)
        (release / 'artifact-manifest.json').write_text(json.dumps({
            'schemaVersion': '1.0', 'commit': self.head, 'installedRevision': self.head}))
        (self.root / 'install' / 'current').symlink_to(release)
        lock = self.root / 'runtime' / 'production-operation.lock'
        lock.write_text('')
        lock.chmod(0o644)
        (self.root / 'certs' / 'client-ca.pem').write_text('synthetic pinned bundle')
        self.config = {
            'phase': 'dry_run', 'head': self.head, 'namespace': 'relay-test',
            'hostname': 'relay.example.invalid', 'email': 'owner@example.invalid',
            'method': 'webroot', 'addresses': ['192.0.2.10', '2001:db8::10'],
            'webroot': str(self.root / 'webroot'), 'conf_root': str(self.root / 'conf'),
            'preparation_root': str(self.root / 'state' / 'tls-preparation'),
            'state_root': str(self.root / 'state' / 'tls-preparation' / 'certbot'),
            'marker': str(self.root / 'state' / 'tls-preparation' / 'acme-http01-dry-run-passed'),
            'client_ca': str(self.root / 'certs' / 'client-ca.pem'),
            'certificate': str(self.root / 'certs' / 'server-fullchain.pem'),
            'private_key': str(self.root / 'certs' / 'server-private-key.pem'),
            'reviewer_group': 'root', 'container': 'nginx', 'image': 'nginx:fixture',
            'manifest': str(self.root / 'install' / 'current' / 'artifact-manifest.json'),
            'lock_file': str(lock), 'operation_record': str(self.root / 'state' / 'operation.json'),
            'certbot': '/usr/bin/certbot',
        }
        self.foreign = self.root / 'conf' / 'docreview.conf'
        self.foreign.write_text('server { listen 443 ssl; server_name docreview.example.invalid; }\n')
        self.foreign_original = self.foreign.read_bytes()
        self.commands = []
        self.container = {
            'Id': 'fixture-container', 'Name': '/nginx', 'Config': {'Image': 'nginx:fixture'},
            'State': {'Running': True},
            'Mounts': [{'Type': 'bind', 'Source': self.config['conf_root'], 'Destination': '/etc/nginx/conf.d'},
                       {'Type': 'bind', 'Source': self.config['webroot'], 'Destination': '/var/www/html'}],
            'NetworkSettings': {'Ports': {'80/tcp': [{'HostPort': '80'}], '443/tcp': [{'HostPort': '443'}]}},
        }

    @property
    def fragment(self):
        return self.root / 'conf' / 'relay-test-acme.conf'

    def dns(self, *args):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('192.0.2.10', 80)),
                (socket.AF_INET6, socket.SOCK_STREAM, 6, '', ('2001:db8::10', 80, 0, 0))]

    def execute(self, argv):
        self.commands.append(argv)
        if 'certonly' in argv:
            hooks = Path(self.config['state_root']) / 'config' / 'renewal-hooks'
            for name in ('pre', 'deploy', 'post'):
                (hooks / name).mkdir(parents=True, exist_ok=True)
        if argv[:2] == ['docker', 'inspect']:
            return json.dumps([self.container])
        if argv[0] == 'curl':
            token = argv[-1].rsplit('/', 1)[-1]
            return (self.root / 'webroot' / '.well-known' / 'acme-challenge' / token).read_text()
        if argv[-1] == '--version':
            return 'certbot 2.1.0\n'
        return ''

    def simulate(self, config=None, execute=None):
        with ExitStack() as stack:
            stack.enter_context(patch.object(TLS, 'prepare_ca'))
            stack.enter_context(patch.object(TLS, 'certbot_provenance'))
            stack.enter_context(patch.object(TLS, 'execute', side_effect=execute or self.execute))
            stack.enter_context(patch.object(TLS.socket, 'getaddrinfo', side_effect=self.dns))
            return TLS.run(copy.deepcopy(config or self.config))

    def marker(self):
        return json.loads(Path(self.config['marker']).read_text())

    def assert_preserved(self):
        self.assertFalse(self.fragment.exists())
        self.assertEqual(self.foreign.read_bytes(), self.foreign_original)
        self.assertFalse(any('stop' in command or 'restart' in command for command in self.commands))

    def test_clean_shared_ingress_dry_run_is_scoped_and_restored(self):
        self.assertEqual(self.simulate()['status'], 'TLS_ACME_DRY_RUN_PASSED')
        self.assertEqual(self.marker()['status'], 'TLS_ACME_DRY_RUN_PASSED')
        invocation = next(command for command in self.commands if 'certonly' in command)
        self.assertIn('--webroot', invocation)
        self.assertIn('--dry-run', invocation)
        self.assertIn('--no-directory-hooks', invocation)
        self.assertEqual(invocation[invocation.index('--config') + 1], '/dev/null')
        self.assertEqual(invocation[invocation.index('--server') + 1],
                         'https://acme-staging-v02.api.letsencrypt.org/directory')
        self.assertNotIn('--standalone', invocation)
        for kind in ('config', 'work', 'logs'):
            self.assertEqual(invocation[invocation.index('--' + kind + '-dir') + 1],
                             str(Path(self.config['state_root']) / kind))
        self.assertEqual(len([command for command in self.commands if command[0] == 'curl']), 2)
        self.assert_preserved()

    def test_first_challenge_directories_are_nginx_readable_under_restrictive_umask(self):
        previous = os.umask(0o077)
        try:
            self.simulate()
        finally:
            os.umask(previous)
        for relative in ('.well-known', '.well-known/acme-challenge'):
            self.assertEqual((Path(self.config['webroot']) / relative).stat().st_mode & 0o777, 0o755)
        self.assert_preserved()

    def test_successful_staging_authorizes_one_exact_live_request(self):
        self.simulate()
        config = dict(self.config, phase='issue')
        with patch.object(TLS, 'publish_certificate') as publish:
            self.assertEqual(self.simulate(config)['status'], 'TLS_CERTIFICATE_KEY_VALIDATED')
            publish.assert_called_once()
        self.assertEqual(self.marker()['status'], 'TLS_ACME_DRY_RUN_INVALIDATED')
        self.assert_preserved()

    def test_changed_contact_address_webroot_or_ca_cannot_reuse_staging(self):
        for field, value in [('email', 'other@example.invalid'), ('addresses', ['192.0.2.10']),
                             ('image', 'nginx:other')]:
            with self.subTest(field=field):
                self.simulate()
                config = dict(self.config, phase='issue')
                config[field] = value
                with self.assertRaises(TLS.BootstrapError):
                    self.simulate(config)
                self.assertEqual(self.marker()['status'], 'TLS_ACME_DRY_RUN_INVALIDATED')
                self.assert_preserved()

    def test_missing_staging_cannot_issue(self):
        with self.assertRaisesRegex(TLS.BootstrapError, 'DRY_RUN_REQUIRED'):
            self.simulate(dict(self.config, phase='issue'))
        self.assertFalse(any('certonly' in command for command in self.commands))

    def test_certbot_failure_restores_foreign_ingress_and_invalidates_marker(self):
        self.simulate()
        def execute(argv):
            if 'certonly' in argv:
                raise TLS.BootstrapError('TLS_SUBPROCESS_FAILED')
            return self.execute(argv)
        with self.assertRaises(TLS.BootstrapError):
            self.simulate(execute=execute)
        self.assertEqual(self.marker()['status'], 'TLS_ACME_DRY_RUN_INVALIDATED')
        self.assert_preserved()

    def test_failed_nginx_validation_removes_fragment_before_restoring(self):
        def execute(argv):
            if argv[-1] == '-t' and self.fragment.exists():
                raise TLS.BootstrapError('TLS_SUBPROCESS_FAILED')
            return self.execute(argv)
        with self.assertRaises(TLS.BootstrapError):
            self.simulate(execute=execute)
        self.assert_preserved()

    def test_challenge_wrong_response_prevents_certbot(self):
        def execute(argv):
            return 'wrong challenge' if argv[0] == 'curl' else self.execute(argv)
        with self.assertRaisesRegex(TLS.BootstrapError, 'CHALLENGE_UNREACHABLE'):
            self.simulate(execute=execute)
        self.assertFalse(any('certonly' in command for command in self.commands))
        self.assert_preserved()

    def test_foreign_hostname_and_unpinned_mount_fail_before_fragment(self):
        self.foreign.write_text('server { server_name relay.example.invalid; }')
        with self.assertRaisesRegex(TLS.BootstrapError, 'HOSTNAME_ALREADY_ROUTED'):
            self.simulate()
        self.foreign.write_bytes(self.foreign_original)
        self.container['Mounts'][1]['Source'] = '/foreign/webroot'
        with self.assertRaisesRegex(TLS.BootstrapError, 'MOUNT_MISMATCH'):
            self.simulate()
        self.assert_preserved()

    def test_foreign_wildcard_and_regex_routes_are_not_overridden(self):
        for name in ('*.example.invalid', '.example.invalid', '~^relay[.]example[.]invalid$'):
            with self.subTest(name=name):
                self.foreign.write_text('server { server_name ' + name + '; }')
                with self.assertRaisesRegex(TLS.BootstrapError, 'HOSTNAME_'):
                    self.simulate()
                self.assertFalse(self.fragment.exists())
        self.foreign.write_bytes(self.foreign_original)

    def test_nginx_conflicting_name_warning_with_zero_exit_is_rejected(self):
        completed = subprocess.CompletedProcess(['docker'], 0, '',
                                                'nginx: [warn] conflicting server name ignored')
        with patch.object(TLS.subprocess, 'run', return_value=completed):
            with self.assertRaisesRegex(TLS.BootstrapError, 'VALIDATION_WARNING'):
                TLS.execute(['docker', 'exec', 'fixture', 'nginx', '-t'])

    def test_effective_included_non_conf_wildcard_is_not_overridden(self):
        self.foreign.write_text('include /etc/nginx/foreign-vhost.snippet;\n')
        def execute(argv):
            if argv[-1] == '-T':
                return '# configuration file /etc/nginx/foreign-vhost.snippet:\nserver_name *.example.invalid;\n'
            return self.execute(argv)
        with self.assertRaisesRegex(TLS.BootstrapError, 'HOSTNAME_ALREADY_ROUTED'):
            self.simulate(execute=execute)
        self.assertFalse(self.fragment.exists())

    def test_hostile_global_certbot_configuration_is_refused_before_any_subprocess(self):
        config = self.root / 'hostile-cli.ini'
        config.write_bytes(DEBIAN_STOCK_CONFIG + b'pre-hook = /bin/false\n')
        with patch.object(TLS, 'CERTBOT_GLOBAL_CONFIG', str(config)), patch.object(TLS, 'execute') as execute:
            with self.assertRaisesRegex(TLS.BootstrapError, 'GLOBAL_CONFIGURATION_AMBIGUOUS'):
                TLS.certbot_provenance(self.config)
            execute.assert_not_called()

    def test_exact_debian_stock_config_is_admitted_and_bound_to_staging(self):
        config = self.root / 'stock-cli.ini'
        config.write_bytes(DEBIAN_STOCK_CONFIG)
        with patch.object(TLS, 'CERTBOT_GLOBAL_CONFIG', str(config)):
            self.assertEqual(TLS.certbot_configuration_identity(), TLS.DEBIAN_CERTBOT_CONFIG_SHA256)
            self.simulate()
            self.assertEqual(self.marker()['binding']['certbot_global_configuration'],
                             TLS.DEBIAN_CERTBOT_CONFIG_SHA256)
            config.unlink()
            with self.assertRaisesRegex(TLS.BootstrapError, 'BINDING_INVALID_OR_STALE'):
                self.simulate(dict(self.config, phase='issue'))
        self.assert_preserved()

    def test_absent_certbot_install_can_introduce_verified_stock_configuration(self):
        config = self.root / 'installed-cli.ini'
        commands = []
        def execute(argv):
            commands.append(argv)
            if argv[0] == 'apt-get':
                config.write_bytes(DEBIAN_STOCK_CONFIG)
                return ''
            if argv[:2] == ['dpkg-query', '-S']:
                return 'certbot: /usr/bin/certbot\n'
            return 'install ok installed'
        original_exists = Path.exists
        def exists(path):
            return False if str(path) == '/usr/bin/certbot' else original_exists(path)
        with patch.object(TLS, 'CERTBOT_GLOBAL_CONFIG', str(config)), \
                patch.object(TLS, 'execute', side_effect=execute), \
                patch.object(TLS, 'safe_path'), patch.object(Path, 'exists', exists):
            TLS.certbot_provenance(self.config)
        self.assertEqual(sum(command[0] == 'apt-get' for command in commands), 1)
        self.assertTrue(config.read_bytes() == DEBIAN_STOCK_CONFIG)

    def test_certbot_subprocess_uses_isolated_home_not_owner_configuration(self):
        completed = subprocess.CompletedProcess(['certbot'], 0, 'certbot fixture', '')
        with patch.object(TLS.subprocess, 'run', return_value=completed) as run:
            TLS.execute(['/usr/bin/certbot', '--config-dir', self.config['state_root'] + '/config', '--version'])
            environment = run.call_args.kwargs['env']
            self.assertEqual(environment['HOME'], self.config['state_root'] + '/home')
            self.assertEqual(environment['XDG_CONFIG_HOME'], self.config['state_root'] + '/home/.config')

    def test_namespace_renewal_hooks_refused_before_ingress_or_certbot(self):
        hooks = Path(self.config['state_root']) / 'config' / 'renewal-hooks'
        hooks.mkdir(parents=True)
        (hooks / 'foreign-hook').write_text('do not execute')
        with self.assertRaisesRegex(TLS.BootstrapError, 'RENEWAL_STATE_AMBIGUOUS'):
            self.simulate()
        self.assertFalse(self.commands)
        self.assert_preserved()

    def test_ipv6_dns_drift_fails_closed(self):
        config = dict(self.config, addresses=['192.0.2.10'])
        with self.assertRaisesRegex(TLS.BootstrapError, 'PUBLIC_DNS_MISMATCH'):
            self.simulate(config)
        self.assertFalse(self.commands)
        self.assert_preserved()

    def test_ca_only_does_not_require_contact_dns_ports_certbot_or_webroot(self):
        config = dict(self.config, phase='prerequisites', email='', addresses=[], webroot='', method='')
        self.assertEqual(self.simulate(config)['status'], 'TLS_PREPARATION_PREREQUISITES_READY')
        self.assertFalse(self.commands)
        self.assertFalse(Path(config['marker']).exists())

    def test_check_is_nonmutating_on_missing_bootstrap_state(self):
        config = dict(self.config, phase='check', email='', addresses=[], webroot='', method='')
        before = sorted(str(path.relative_to(self.root)) for path in self.root.rglob('*'))
        self.assertEqual(TLS.run(config)['status'], 'TLS_PREPARATION_CHECK_MODE_PASS')
        self.assertEqual(before, sorted(str(path.relative_to(self.root)) for path in self.root.rglob('*')))

    def test_guard_rejects_wrong_head_active_operation_and_busy_lock(self):
        for kind in ('head', 'operation', 'lock'):
            with self.subTest(kind=kind), ExitStack() as stack:
                config = copy.deepcopy(self.config)
                if kind == 'head':
                    config['head'] = 'b' * 40
                if kind == 'operation':
                    Path(config['operation_record']).write_text('{}')
                    stack.callback(Path(config['operation_record']).unlink)
                if kind == 'lock':
                    lock = stack.enter_context(open(config['lock_file']))
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaises((TLS.BootstrapError, ValueError, BlockingIOError)):
                    self.simulate(config)
                self.assertFalse(Path(config['marker']).exists())

    def test_symlinked_or_writable_webroot_is_rejected(self):
        Path(self.config['webroot']).chmod(0o777)
        with self.assertRaisesRegex(TLS.BootstrapError, 'PATH_UNSAFE'):
            self.simulate()
        self.assert_preserved()

    def make_ca_fixture(self):
        directory = self.root / 'ca-fixture'
        directory.mkdir()
        root, intermediate = directory / 'root.pem', directory / 'intermediate.pem'
        def command(arguments):
            subprocess.run(['openssl'] + arguments, check=True, capture_output=True)
        command(['req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                 '-subj', '/CN=Synthetic test root', '-addext', 'basicConstraints=critical,CA:TRUE',
                 '-addext', 'keyUsage=critical,keyCertSign,cRLSign',
                 '-keyout', str(directory / 'root.key'), '-out', str(root)])
        command(['req', '-new', '-newkey', 'rsa:2048', '-nodes', '-subj', '/CN=Synthetic test intermediate',
                 '-keyout', str(directory / 'intermediate.key'), '-out', str(directory / 'intermediate.csr')])
        extension = directory / 'extensions'
        extension.write_text('basicConstraints=critical,CA:TRUE\nkeyUsage=critical,keyCertSign,cRLSign\n')
        command(['x509', '-req', '-in', str(directory / 'intermediate.csr'), '-CA', str(root),
                 '-CAkey', str(directory / 'root.key'), '-CAcreateserial', '-days', '1',
                 '-extfile', str(extension), '-out', str(intermediate)])
        ca_data = [root.read_bytes(), intermediate.read_bytes()]
        identities = []
        for index, path in enumerate((root, intermediate)):
            fingerprint = TLS.execute(['openssl', 'x509', '-in', str(path), '-noout', '-sha256', '-fingerprint'])
            identities.append((('root.pem', 'intermediate.pem')[index], 'https://fixture.invalid/' + str(index),
                               fingerprint.strip().split('=')[-1].replace(':', '')))
        return ca_data, identities

    def test_ca_clean_bootstrap_then_reuse_validates_real_chain_and_permissions(self):
        ca_data, identities = self.make_ca_fixture()
        Path(self.config['client_ca']).unlink()
        config = dict(self.config, phase='prerequisites', email='', addresses=[], webroot='', method='')
        with patch.object(TLS, 'OPENAI_CAS', identities), patch.object(TLS, 'download_ca', side_effect=ca_data) as download:
            self.assertEqual(TLS.run(config)['status'], 'TLS_PREPARATION_PREREQUISITES_READY')
            self.assertEqual(download.call_count, 2)
        self.assertEqual(Path(config['client_ca']).stat().st_mode & 0o777, 0o640)
        with patch.object(TLS, 'OPENAI_CAS', identities), patch.object(TLS, 'download_ca') as download:
            TLS.run(config)
            download.assert_not_called()
        self.assertFalse(Path(config['state_root']).exists())

    def test_pinned_ca_identity_mismatch_does_not_install_bundle(self):
        ca_data, identities = self.make_ca_fixture()
        identities[0] = (identities[0][0], identities[0][1], '00' * 32)
        Path(self.config['client_ca']).unlink()
        config = dict(self.config, phase='prerequisites', email='', addresses=[], webroot='', method='')
        with patch.object(TLS, 'OPENAI_CAS', identities), patch.object(TLS, 'download_ca', side_effect=ca_data):
            with self.assertRaisesRegex(TLS.BootstrapError, 'IDENTITY_MISMATCH'):
                TLS.run(config)
        self.assertFalse(Path(config['client_ca']).exists())

    def test_existing_unrelated_ca_bundle_is_preserved(self):
        ca_data, identities = self.make_ca_fixture()
        original = Path(self.config['client_ca']).read_bytes()
        config = dict(self.config, phase='prerequisites', email='', addresses=[], webroot='', method='')
        with patch.object(TLS, 'OPENAI_CAS', identities), patch.object(TLS, 'download_ca', side_effect=ca_data):
            with self.assertRaisesRegex(TLS.BootstrapError, 'EXISTING_BUNDLE_MISMATCH'):
                TLS.run(config)
        self.assertEqual(Path(config['client_ca']).read_bytes(), original)

    def test_existing_ca_directory_that_reviewer_cannot_traverse_is_not_reported_ready(self):
        Path(self.config['client_ca']).parent.chmod(0o700)
        with patch.object(TLS, 'download_ca') as download:
            with self.assertRaisesRegex(TLS.BootstrapError, 'DIRECTORY_UNREADABLE_OR_UNSAFE'):
                TLS.prepare_ca(self.config)
            download.assert_not_called()

    def test_public_playbook_check_executes_helpers_on_clean_fixture_without_bootstrap_mutation(self):
        ansible = Path(sys.executable).with_name('ansible-playbook')
        if not ansible.exists():
            self.skipTest('Ansible executable required for public playbook execution')
        variables = {
            'ansible_python_interpreter': sys.executable,
            'relay_tls_exact_head': self.head, 'relay_tls_phase': 'prerequisites',
            'relay_namespace': self.config['namespace'],
            'relay_tls_acme_hostname': self.config['hostname'],
            'relay_tls_acme_email': '', 'relay_tls_acme_method': '', 'relay_tls_public_addresses': [],
            'relay_tls_acme_webroot': '',
            'relay_docker_nginx_conf_root': self.config['conf_root'],
            'relay_docker_nginx_container_name': self.config['container'],
            'relay_docker_nginx_expected_image': self.config['image'],
            'relay_tls_preparation_root': self.config['preparation_root'],
            'relay_tls_acme_state_root': self.config['state_root'],
            'relay_tls_acme_dry_run_marker': self.config['marker'],
            'relay_tls_client_ca_file': self.config['client_ca'],
            'relay_nginx_server_certificate_file': self.config['certificate'],
            'relay_nginx_server_private_key_file': self.config['private_key'],
            'relay_reviewer_group': 'root', 'relay_tls_qualified_manifest_file': self.config['manifest'],
            'relay_tls_certbot_executable': '/usr/bin/certbot',
            'relay_production_operation_lock_path': self.config['lock_file'],
            'relay_production_operation_record_path': self.config['operation_record'],
        }
        extra = self.root / 'vars.json'
        extra.write_text(json.dumps(variables))
        inventory = self.root / 'inventory'
        inventory.write_text('[relay]\nlocalhost ansible_connection=local\n')
        environment = os.environ.copy()
        environment['ANSIBLE_NOCOLOR'] = '1'
        result = subprocess.run([str(ansible), '-i', str(inventory),
                                 str(TOOLS.parent / 'relay-tls-preparation.yml'),
                                 '--check', '-e', '@' + str(extra)],
                                text=True, capture_output=True, env=environment)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('TLS_BOOTSTRAP_CHECK=PASS;head=' + self.head, result.stdout)
        self.assertFalse(Path(self.config['preparation_root']).exists())
        self.assertFalse(Path(self.config['certificate']).exists())

    def make_server_lineage(self):
        self.make_ca_fixture()
        fixture = self.root / 'ca-fixture'
        state = Path(self.config['state_root'])
        archive = state / 'config' / 'archive' / self.config['hostname']
        lineage = state / 'config' / 'live' / self.config['hostname']
        archive.mkdir(parents=True)
        lineage.mkdir(parents=True)
        def command(arguments):
            subprocess.run(['openssl'] + arguments, check=True, capture_output=True)
        key = archive / 'privkey1.pem'
        command(['req', '-new', '-newkey', 'rsa:2048', '-nodes', '-subj', '/CN=Synthetic server',
                 '-keyout', str(key), '-out', str(fixture / 'server.csr')])
        extension = fixture / 'server.ext'
        extension.write_text('basicConstraints=CA:FALSE\nextendedKeyUsage=serverAuth\n'
                             'keyUsage=digitalSignature,keyEncipherment\n'
                             'subjectAltName=DNS:' + self.config['hostname'] + '\n')
        command(['x509', '-req', '-in', str(fixture / 'server.csr'), '-CA', str(fixture / 'intermediate.pem'),
                 '-CAkey', str(fixture / 'intermediate.key'), '-CAcreateserial', '-days', '1',
                 '-extfile', str(extension), '-out', str(fixture / 'server.pem')])
        certificate = archive / 'fullchain1.pem'
        certificate.write_bytes((fixture / 'server.pem').read_bytes() + (fixture / 'intermediate.pem').read_bytes())
        certificate.chmod(0o644)
        key.chmod(0o600)
        (lineage / 'fullchain.pem').symlink_to(certificate)
        (lineage / 'privkey.pem').symlink_to(key)
        validator = TLS.validator_module()
        wrapped = SimpleNamespace(ValidationError=validator.ValidationError,
                                  validate_sources=lambda *args, **kwargs:
                                  validator.validate_sources(*args, **kwargs, trust_store=fixture / 'root.pem'))
        return archive, lineage, wrapped

    def test_issued_pair_is_chain_validated_then_published_as_protected_regular_files(self):
        archive, _, validator = self.make_server_lineage()
        with patch.object(TLS, 'validator_module', return_value=validator):
            TLS.publish_certificate(self.config)
        certificate, key = Path(self.config['certificate']), Path(self.config['private_key'])
        self.assertFalse(certificate.is_symlink())
        self.assertFalse(key.is_symlink())
        self.assertEqual(certificate.stat().st_mode & 0o777, 0o644)
        self.assertEqual(key.stat().st_mode & 0o777, 0o600)
        self.assertTrue(key.read_bytes() == (archive / 'privkey1.pem').read_bytes())
        with patch.object(TLS, 'validator_module', return_value=validator):
            self.assertEqual(self.simulate(dict(self.config, phase='issue'))['status'],
                             'TLS_EXISTING_CERTIFICATE_REUSED')
        self.assertFalse(any('certonly' in command for command in self.commands))

    def test_issue_recovers_after_process_exit_at_first_durable_key_publication(self):
        archive, lineage, validator = self.make_server_lineage()
        # Certbot exposes the synthetic lineage only when the admitted issue
        # operation reaches certonly, after a successful staging operation.
        pending = lineage.with_name('fixture-pending-lineage')
        lineage.rename(pending)
        self.simulate()
        config = dict(self.config, phase='issue')
        certificate, key = Path(config['certificate']), Path(config['private_key'])
        original_fsync = os.fsync

        def interrupt_after_durable_key(fd):
            original_fsync(fd)
            if stat.S_ISDIR(os.fstat(fd).st_mode) and key.exists() and not certificate.exists():
                os._exit(74)

        def issue(argv):
            result = self.execute(argv)
            if 'certonly' in argv:
                pending.rename(lineage)
            return result

        child = os.fork()
        if child == 0:
            try:
                with patch.object(TLS, 'validator_module', return_value=validator), \
                        patch.object(TLS.os, 'fsync', side_effect=interrupt_after_durable_key):
                    self.simulate(config, execute=issue)
            except BaseException:
                os._exit(75)
            os._exit(76)
        _, status = os.waitpid(child, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 74)
        self.assertTrue(key.exists())
        self.assertFalse(certificate.exists())
        self.assertEqual(key.stat().st_nlink, 1)
        self.assertEqual(key.read_bytes(), (archive / 'privkey1.pem').read_bytes())
        # os._exit bypasses every finally, including temporary snapshot cleanup.
        # The public issue retry must converge without removing any residue.
        self.assertTrue(list(Path(config['state_root']).glob('.certificate-*')))
        self.assertFalse(list(key.parent.glob('.relay-tls-*')))
        self.assert_preserved()
        identity = (key.stat().st_dev, key.stat().st_ino)
        self.commands.clear()
        with patch.object(TLS, 'validator_module', return_value=validator):
            self.assertEqual(self.simulate(config)['status'], 'TLS_EXISTING_CERTIFICATE_REUSED')
            self.assertEqual(self.simulate(config)['status'], 'TLS_EXISTING_CERTIFICATE_REUSED')
        self.assertEqual((key.stat().st_dev, key.stat().st_ino), identity)
        self.assertEqual(certificate.read_bytes(), (archive / 'fullchain1.pem').read_bytes())
        self.assertEqual(certificate.stat().st_mode & 0o777, 0o644)
        self.assertEqual(key.stat().st_mode & 0o777, 0o600)
        validator.validate_sources(certificate, key, config['hostname'])
        self.assertFalse(self.commands)
        self.assert_preserved()

    def test_foreign_or_ambiguous_partial_key_is_preserved_and_rejected(self):
        archive, _, validator = self.make_server_lineage()
        key = Path(self.config['private_key'])
        material = (archive / 'privkey1.pem').read_bytes()
        for kind in ('mismatched', 'hardlink', 'symlink', 'dangling', 'owner', 'group', 'mode'):
            with self.subTest(kind=kind), patch.object(TLS, 'validator_module', return_value=validator):
                if kind == 'hardlink':
                    os.link(archive / 'privkey1.pem', key)
                elif kind in ('symlink', 'dangling'):
                    key.symlink_to(archive / ('privkey1.pem' if kind == 'symlink' else 'absent.pem'))
                else:
                    key.write_bytes((self.root / 'ca-fixture' / 'root.key').read_bytes()
                                    if kind == 'mismatched' else material)
                    key.chmod(0o640 if kind == 'mode' else 0o600)
                    os.chown(key, 1 if kind == 'owner' else 0, 1 if kind == 'group' else 0)
                before = key.lstat()
                with self.assertRaisesRegex(TLS.BootstrapError, 'TLS_MANAGED_PARTIAL_KEY_'):
                    self.simulate(dict(self.config, phase='issue'))
                after = key.lstat()
                for attribute in ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
                                  'st_size', 'st_mtime_ns', 'st_ctime_ns'):
                    self.assertEqual(getattr(after, attribute), getattr(before, attribute))
                self.assertFalse(Path(self.config['certificate']).exists())
                self.assertFalse(self.commands)
                key.unlink()

    def test_partial_key_requires_explicit_issue_and_matching_namespace_lineage(self):
        archive, lineage, validator = self.make_server_lineage()
        key = Path(self.config['private_key'])
        key.write_bytes((archive / 'privkey1.pem').read_bytes())
        key.chmod(0o600)
        before = key.read_bytes()
        with patch.object(TLS, 'validator_module', return_value=validator):
            with self.assertRaisesRegex(TLS.BootstrapError, 'PARTIAL_REQUIRES_ISSUE_REUSE'):
                self.simulate()
            (lineage / 'privkey.pem').unlink()
            (archive / 'privkey2.pem').write_bytes(before)
            (archive / 'privkey2.pem').chmod(0o600)
            (lineage / 'privkey.pem').symlink_to(archive / 'privkey2.pem')
            with self.assertRaisesRegex(TLS.BootstrapError, 'GENERATION_MISMATCH'):
                self.simulate(dict(self.config, phase='issue'))
            (lineage / 'fullchain.pem').unlink()
            (lineage / 'privkey.pem').unlink()
            lineage.rmdir()
            with self.assertRaisesRegex(TLS.BootstrapError, 'PATH_MISSING'):
                self.simulate(dict(self.config, phase='issue'))
        self.assertEqual(key.read_bytes(), before)
        self.assertFalse(Path(self.config['certificate']).exists())
        self.assertFalse(self.commands)

    def test_certificate_only_partial_state_is_never_adopted(self):
        archive, _, validator = self.make_server_lineage()
        certificate = Path(self.config['certificate'])
        certificate.write_bytes((archive / 'fullchain1.pem').read_bytes())
        certificate.chmod(0o644)
        before = certificate.read_bytes()
        with patch.object(TLS, 'validator_module', return_value=validator):
            with self.assertRaisesRegex(validator.ValidationError, 'TLS_SOURCE_UNAVAILABLE_OR_UNSAFE'):
                self.simulate(dict(self.config, phase='issue'))
        self.assertEqual(certificate.read_bytes(), before)
        self.assertFalse(Path(self.config['private_key']).exists())
        self.assertFalse(self.commands)

    def test_unsafe_lineage_and_mixed_generations_cannot_publish(self):
        archive, lineage, validator = self.make_server_lineage()
        with patch.object(TLS, 'validator_module', return_value=validator):
            archive.chmod(0o777)
            with self.assertRaisesRegex(TLS.BootstrapError, 'UNSAFE'):
                TLS.publish_certificate(self.config)
            archive.chmod(0o755)
            (lineage / 'privkey.pem').unlink()
            (archive / 'privkey2.pem').write_bytes((archive / 'privkey1.pem').read_bytes())
            (archive / 'privkey2.pem').chmod(0o600)
            (lineage / 'privkey.pem').symlink_to(archive / 'privkey2.pem')
            with self.assertRaisesRegex(TLS.BootstrapError, 'GENERATION_MISMATCH'):
                TLS.publish_certificate(self.config)
            self.assertFalse(Path(self.config['private_key']).exists())


if __name__ == '__main__':
    unittest.main()
