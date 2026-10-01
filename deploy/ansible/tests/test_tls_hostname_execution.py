"""Execute TLS admission and real Ansible projection gates with synthetic keys."""
import copy
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
HOST = 'reviewer.example.invalid'
HELPER = ROOT / 'tools' / 'tls-source-validate.py'
spec = importlib.util.spec_from_file_location('relay_tls_validation', HELPER)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)
AVAILABLE = (os.name != 'nt' and os.geteuid() == 0
             and all(shutil.which(name) for name in ('openssl', 'ansible-playbook')))


@unittest.skipUnless(AVAILABLE, 'native Linux root, OpenSSL and Ansible required for protected-path admission')
class CertificateHostnameExecutionTests(unittest.TestCase):
    @classmethod
    def openssl(cls, *args):
        subprocess.run(['openssl', *map(str, args)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    @classmethod
    def setUpClass(cls):
        # A writable /tmp parent must fail production admission, even for a
        # root-owned child. Synthetic source files therefore live under /root.
        cls.temporary = tempfile.TemporaryDirectory(prefix='relay-tls-test-', dir='/root')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.fixture = Path(cls.temporary.name)
        cls.ca, cls.ca_key = cls.fixture / 'root.pem', cls.fixture / 'root.key'
        cls.openssl('req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '2',
                    '-subj', '/CN=Relay synthetic root', '-keyout', cls.ca_key, '-out', cls.ca,
                    '-addext', 'basicConstraints=critical,CA:TRUE',
                    '-addext', 'keyUsage=critical,keyCertSign,cRLSign')
        cls.intermediate, cls.intermediate_key = cls.fixture / 'intermediate.pem', cls.fixture / 'intermediate.key'
        csr = cls.fixture / 'intermediate.csr'
        ext = cls.fixture / 'intermediate.ext'
        ext.write_text('basicConstraints=critical,CA:TRUE,pathlen:0\nkeyUsage=critical,keyCertSign,cRLSign\n')
        cls.openssl('req', '-new', '-newkey', 'rsa:2048', '-nodes', '-subj', '/CN=Relay synthetic intermediate',
                    '-keyout', cls.intermediate_key, '-out', csr)
        cls.openssl('x509', '-req', '-in', csr, '-CA', cls.ca, '-CAkey', cls.ca_key,
                    '-CAcreateserial', '-days', '2', '-extfile', ext, '-out', cls.intermediate)
        cls.certificates = {}
        for name, san in [('exact', HOST), ('wildcard', '*.example.invalid'),
                          ('foreign', 'other.example.invalid'), ('no_san', None), ('uri_san', None),
                          ('expired', HOST), ('future', HOST)]:
            directory = cls.fixture / name
            directory.mkdir()
            cert, key, csr = directory / 'fullchain.pem', directory / 'privkey.pem', directory / 'leaf.csr'
            cls.openssl('req', '-new', '-newkey', 'rsa:2048', '-nodes',
                        '-keyout', key, '-out', csr, '-subj', '/CN=' + HOST)
            ext = directory / 'extensions'
            ext.write_text('basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n'
                           + ('subjectAltName=URI:https://DNS:example.invalid\n' if name == 'uri_san' else
                              'subjectAltName=DNS:' + san + '\n' if san else ''))
            if name == 'future':
                (directory / 'index').touch()
                (directory / 'serial').write_text('01\n')
                cfg = directory / 'ca.cnf'
                cfg.write_text('[ca]\ndefault_ca=signer\n[signer]\n'
                               f'database={directory}/index\nserial={directory}/serial\nnew_certs_dir={directory}\n'
                               f'certificate={cls.intermediate}\nprivate_key={cls.intermediate_key}\n'
                               'default_md=sha256\npolicy=policy\n[policy]\ncommonName=supplied\n')
                cls.openssl('ca', '-batch', '-notext', '-config', cfg, '-in', csr, '-out', cert,
                            '-extfile', ext, '-startdate', '20400101000000Z', '-enddate', '20410101000000Z')
            else:
                cls.openssl('x509', '-req', '-in', csr, '-CA', cls.intermediate,
                            '-CAkey', cls.intermediate_key, '-CAcreateserial',
                            '-days', '-1' if name == 'expired' else '1', '-extfile', ext, '-out', cert)
            cert.write_bytes(cert.read_bytes() + cls.intermediate.read_bytes())
            cert.chmod(0o644)
            key.chmod(0o600)
            cls.certificates[name] = (cert, key)
        malformed = cls.fixture / 'malformed.pem'
        malformed.write_text('not a certificate\n')
        cls.certificates['malformed'] = (malformed, cls.certificates['exact'][1])
        cls.certificates['missing'] = (cls.fixture / 'absent.pem', cls.certificates['exact'][1])
        # Only this local wrapper supplies a synthetic trust anchor to the
        # callable API. Neither production CLI nor configuration has that knob.
        cls.wrapper = cls.fixture / 'fixture-validator.py'
        cls.wrapper.write_text('import importlib.util\n'
                               f'spec=importlib.util.spec_from_file_location("validator", {str(HELPER)!r})\n'
                               'module=importlib.util.module_from_spec(spec)\nspec.loader.exec_module(module)\n'
                               f'raise SystemExit(module.main(trust_store={str(cls.ca)!r}))\n')

    def validate(self, fixture='exact', *, key_fixture=None, hostname=HOST, trust=True):
        cert, key = self.certificates[fixture]
        if key_fixture:
            key = self.certificates[key_fixture][1]
        return validator.validate_sources(cert, key, hostname, trust_store=self.ca if trust else None)

    def test_matching_san_and_wildcard_with_trusted_intermediate(self):
        for fixture in ('exact', 'wildcard'):
            with self.subTest(fixture=fixture):
                self.assertEqual(self.validate(fixture)['status'], 'TLS_CERTIFICATE_KEY_VALIDATED')

    def test_invalid_identity_dates_material_and_keypair_fail_closed(self):
        for fixture in ('foreign', 'no_san', 'uri_san', 'expired', 'future', 'malformed', 'missing'):
            with self.subTest(fixture=fixture), self.assertRaises(validator.ValidationError):
                self.validate(fixture)
        with self.assertRaisesRegex(validator.ValidationError, 'KEYPAIR_MISMATCH'):
            self.validate(key_fixture='foreign')
        with self.assertRaisesRegex(validator.ValidationError, 'HOSTNAME_MISMATCH'):
            self.validate('wildcard', hostname='nested.' + HOST)

    def test_system_trust_rejects_untrusted_chain_and_ignores_environment_override(self):
        with patch.dict(os.environ, {'SSL_CERT_FILE': str(self.ca), 'SSL_CERT_DIR': str(self.fixture)}):
            with self.assertRaises(validator.ValidationError):
                self.validate(trust=False)

    def test_precise_file_modes_owner_and_all_parents_are_enforced(self):
        with tempfile.TemporaryDirectory(dir=self.fixture) as name:
            directory = Path(name)
            cert, key = directory / 'fullchain.pem', directory / 'privkey.pem'
            shutil.copyfile(self.certificates['exact'][0], cert)
            shutil.copyfile(self.certificates['exact'][1], key)
            cert.chmod(0o644)
            key.chmod(0o600)
            def check():
                return validator.validate_sources(cert, key, HOST, trust_store=self.ca)
            self.assertEqual(check()['status'], 'TLS_CERTIFICATE_KEY_VALIDATED')
            for path, unsafe, restored in ((key, 0o644, 0o600), (cert, 0o664, 0o644),
                                            (directory, 0o770, 0o700), (directory, 0o777, 0o700)):
                with self.subTest(path=path.name, mode=unsafe):
                    path.chmod(unsafe)
                    with self.assertRaises(validator.ValidationError):
                        check()
                    path.chmod(restored)
            os.chown(key, 65534, 65534)
            with self.assertRaises(validator.ValidationError):
                check()
            os.chown(key, 0, 0)
            os.chown(directory, 65534, 65534)
            with self.assertRaises(validator.ValidationError):
                check()
            os.chown(directory, 0, 0)
            for path, modes in ((cert, (0o600, 0o640, 0o644)), (key, (0o600, 0o640))):
                for mode in modes:
                    path.chmod(mode)
                    self.assertEqual(check()['status'], 'TLS_CERTIFICATE_KEY_VALIDATED')

    def test_explicit_symlinks_and_writable_ancestor_are_rejected(self):
        cert, key = self.certificates['exact']
        symlink = self.fixture / 'linked.pem'
        symlink.symlink_to(cert)
        with self.assertRaisesRegex(validator.ValidationError, 'SYMLINK_FORBIDDEN'):
            validator.validate_sources(symlink, key, HOST, trust_store=self.ca)
        parent = self.fixture / 'linked-parent'
        parent.symlink_to(cert.parent, target_is_directory=True)
        with self.assertRaisesRegex(validator.ValidationError, 'PARENT_UNSAFE'):
            validator.validate_sources(parent / cert.name, key, HOST, trust_store=self.ca)
        with tempfile.TemporaryDirectory() as unsafe:
            outside = Path(unsafe) / 'cert.pem'
            shutil.copyfile(cert, outside)
            with self.assertRaisesRegex(validator.ValidationError, 'PARENT_UNSAFE'):
                validator.validate_sources(outside, key, HOST, trust_store=self.ca)

    def test_only_controlled_legacy_live_archive_lineage_is_compatible(self):
        lineage = self.fixture / 'letsencrypt'
        live, archive = lineage / 'live' / HOST, lineage / 'archive' / HOST
        live.mkdir(parents=True)
        archive.mkdir(parents=True)
        cert, key = self.certificates['exact']
        for source, kind in ((cert, 'fullchain'), (key, 'privkey')):
            target = archive / (kind + '1.pem')
            shutil.copyfile(source, target)
            target.chmod(0o600 if kind == 'privkey' else 0o644)
            (live / (kind + '.pem')).symlink_to('../../archive/' + HOST + '/' + kind + '1.pem')
        with patch.object(validator, 'LEGACY_ROOT', lineage):
            args = (live / 'fullchain.pem', live / 'privkey.pem', HOST)
            with self.assertRaises(validator.ValidationError):
                validator.validate_sources(*args, trust_store=self.ca)
            self.assertEqual(validator.validate_sources(*args, allow_letsencrypt_lineage=True,
                                                        trust_store=self.ca)['status'], 'TLS_CERTIFICATE_KEY_VALIDATED')
            shutil.copyfile(archive / 'privkey1.pem', archive / 'privkey2.pem')
            (archive / 'privkey2.pem').chmod(0o600)
            (live / 'privkey.pem').unlink()
            (live / 'privkey.pem').symlink_to('../../archive/' + HOST + '/privkey2.pem')
            with self.assertRaisesRegex(validator.ValidationError, 'LINEAGE_PAIR_MISMATCH'):
                validator.validate_sources(*args, allow_letsencrypt_lineage=True, trust_store=self.ca)
            (live / 'privkey.pem').unlink()
            (live / 'privkey.pem').symlink_to(key)
            with self.assertRaisesRegex(validator.ValidationError, 'LINEAGE_UNSAFE'):
                validator.validate_sources(*args, allow_letsencrypt_lineage=True, trust_store=self.ca)

    def gate(self, name, role='relay_docker_nginx'):
        tasks = yaml.safe_load((ROOT / 'roles' / role / 'tasks/main.yml').read_text())
        task = copy.deepcopy(next(task for task in tasks if task.get('name') == name))
        if 'ansible.builtin.script' in task:
            task['ansible.builtin.script']['cmd'] = task['ansible.builtin.script']['cmd'].replace(
                "{{ (role_path ~ '/../../tools/tls-source-validate.py') | quote }}", str(self.wrapper))
        return task

    def execute(self, task, cert, key, hostname=HOST):
        with tempfile.TemporaryDirectory(prefix='run-', dir=self.fixture) as directory:
            run = Path(directory)
            projected, reloaded = run / 'projection', run / 'reload'
            playbook = [{
                'hosts': 'localhost', 'connection': 'local', 'gather_facts': False,
                'vars': {
                    'ansible_python_interpreter': shutil.which('python3'),
                    'relay_docker_nginx_manage': True, 'relay_tls_allow_legacy_lineage': False,
                    'relay_nginx_server_certificate_file': str(cert),
                    'relay_nginx_server_private_key_file': str(key),
                    'relay_nginx_server_name': hostname,
                    'relay_docker_nginx_projection_temp': {'path': str(cert.parent)},
                    'relay_tls_phase': 'issue', 'relay_tls_acme_hostname': hostname,
                },
                # Legacy issued-certificate gate still uses OpenSSL's default
                # trust-file mechanism. The new helper deliberately ignores it.
                'environment': {'SSL_CERT_FILE': str(self.ca)},
                'tasks': [task,
                          {'name': 'Projection sentinel', 'ansible.builtin.copy':
                           {'content': 'projected', 'dest': str(projected)}},
                          {'name': 'Reload sentinel', 'ansible.builtin.copy':
                           {'content': 'reloaded', 'dest': str(reloaded)}}],
            }]
            path = run / 'playbook.yml'
            path.write_text(yaml.safe_dump(playbook))
            environment = os.environ.copy()
            environment.update({'ANSIBLE_NOCOLOR': '1', 'ANSIBLE_LOCALHOST_WARNING': 'False'})
            result = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(path)],
                                    capture_output=True, text=True, env=environment, cwd=ROOT)
            return result, projected.exists(), reloaded.exists()

    def test_source_and_staged_gates_prevent_projection_and_reload(self):
        for gate in ('Validate configured relay certificate hostname and key pair without printing private material',
                     'Validate staged certificate projection before installation'):
            for fixture, expected, hostname in [('exact', True, HOST), ('wildcard', True, HOST),
                                                 ('foreign', False, HOST), ('wildcard', False, 'nested.' + HOST),
                                                 ('expired', False, HOST), ('future', False, HOST),
                                                 ('malformed', False, HOST), ('missing', False, HOST)]:
                with self.subTest(gate=gate, fixture=fixture, hostname=hostname):
                    cert, key = self.certificates[fixture]
                    result, projected, reloaded = self.execute(self.gate(gate), cert, key, hostname)
                    self.assertEqual(result.returncode == 0, expected, result.stdout + result.stderr)
                    self.assertEqual((projected, reloaded), (expected, expected))

    def test_legacy_issued_gate_before_readiness(self):
        gate = self.gate('Validate the issued ACME certificate and host-local private key', role='relay_tls')
        for fixture, expected in [('exact', True), ('wildcard', True), ('foreign', False),
                                  ('expired', False), ('future', False), ('malformed', False), ('missing', False)]:
            with self.subTest(fixture=fixture):
                result, projected, reloaded = self.execute(gate, *self.certificates[fixture])
                self.assertEqual(result.returncode == 0, expected, result.stdout + result.stderr)
                self.assertEqual((projected, reloaded), (expected, expected))
        result, projected, reloaded = self.execute(gate, self.certificates['exact'][0], self.certificates['foreign'][1])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((projected, reloaded), (False, False))

    def test_cli_failure_is_sanitized_and_has_no_trust_override(self):
        cert, key = self.certificates['exact']
        result = subprocess.run(['python3', str(HELPER), '--certificate', str(cert), '--private-key', str(key),
                                 '--hostname', HOST], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.strip(), 'TLS_SOURCE_CERTIFICATE_INVALID')
        self.assertEqual(result.stderr, '')
        result = subprocess.run(['python3', str(HELPER), '--trust-store', str(self.ca)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)

    def test_source_validation_precedes_projection_mutations(self):
        tasks = yaml.safe_load((ROOT / 'roles/relay_docker_nginx/tasks/main.yml').read_text())
        names = [task.get('name') for task in tasks]
        source = names.index('Validate configured relay certificate hostname and key pair without printing private material')
        staged = names.index('Validate staged certificate projection before installation')
        self.assertLess(source, names.index('Create relay-owned Docker-nginx certificate projection namespace'))
        self.assertLess(staged, names.index('Install relay certificate projection atomically with controlled modes'))
        self.assertLess(staged, names.index('Install the isolated relay Docker-nginx mTLS fragment'))


if __name__ == '__main__':
    unittest.main()
