"""Execute the deployed hostname gates with real OpenSSL and synthetic keys."""
import copy
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
HOST = 'reviewer.example.invalid'
AVAILABLE = os.name != 'nt' and all(shutil.which(name) for name in ('openssl', 'ansible-playbook'))


@unittest.skipUnless(AVAILABLE, 'native Linux OpenSSL and Ansible required')
class CertificateHostnameExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='relay-hostname-test-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.fixture = Path(cls.temporary.name)
        cls.certificates = {}
        for name, san in [('exact', HOST), ('wildcard', '*.example.invalid'),
                          ('foreign', 'other.example.invalid')]:
            directory = cls.fixture / name
            directory.mkdir()
            cert, key = directory / 'fullchain.pem', directory / 'privkey.pem'
            subprocess.run([
                'openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                '-keyout', str(key), '-out', str(cert), '-days', '1',
                '-subj', '/CN=unrelated-cn.example.invalid',
                '-addext', 'subjectAltName=DNS:' + san,
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            cert.chmod(0o644)
            key.chmod(0o600)
            cls.certificates[name] = (cert, key)
        malformed = cls.fixture / 'malformed'
        malformed.mkdir()
        (malformed / 'fullchain.pem').write_text('not a certificate\n')
        cls.certificates['malformed'] = (malformed / 'fullchain.pem', cls.certificates['exact'][1])
        cls.certificates['missing'] = (cls.fixture / 'missing' / 'fullchain.pem', cls.certificates['exact'][1])
        expired = cls.fixture / 'expired'
        expired.mkdir()
        expired_cert = expired / 'fullchain.pem'
        subprocess.run([
            'openssl', 'x509', '-in', str(cls.certificates['exact'][0]),
            '-signkey', str(cls.certificates['exact'][1]), '-days', '-1',
            '-out', str(expired_cert),
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        expired_cert.chmod(0o644)
        cls.certificates['expired'] = (expired_cert, cls.certificates['exact'][1])

    def gate(self, role, name):
        tasks = yaml.safe_load((ROOT / 'roles' / role / 'tasks' / 'main.yml').read_text())
        return copy.deepcopy(next(task for task in tasks if task.get('name') == name))

    def execute(self, task, cert, key, hostname=HOST):
        with tempfile.TemporaryDirectory(prefix='run-', dir=self.fixture) as directory:
            run = Path(directory)
            projected, reloaded = run / 'projection', run / 'reload'
            # These later tasks represent the side effects that admission must
            # prevent. Only the actual source-controlled validation task runs.
            playbook = [{
                'hosts': 'localhost', 'connection': 'local', 'gather_facts': False,
                'vars': {
                    'ansible_python_interpreter': shutil.which('python3'),
                    'relay_docker_nginx_manage': True,
                    'relay_nginx_server_certificate_file': str(cert),
                    'relay_nginx_server_private_key_file': str(key),
                    'relay_nginx_server_name': hostname,
                    'relay_docker_nginx_projection_temp': {'path': str(cert.parent)},
                    'relay_tls_phase': 'issue', 'relay_tls_acme_hostname': hostname,
                },
                # Trust only the synthetic certificate for the issued gate's
                # existing chain check; never modify the machine trust store.
                'environment': {'SSL_CERT_FILE': str(cert)},
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
            result = subprocess.run(
                ['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(path)],
                capture_output=True, text=True, env=environment, cwd=ROOT,
            )
            return result, projected.exists(), reloaded.exists()

    def assert_admission(self, task, fixture, expected, hostname=HOST, key_fixture=None):
        cert, key = self.certificates[fixture]
        if key_fixture:
            key = self.certificates[key_fixture][1]
        result, projected, reloaded = self.execute(task, cert, key, hostname)
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode == 0, expected, output)
        self.assertEqual(projected, expected, output)
        self.assertEqual(reloaded, expected, output)

    def hostname_cases(self, task):
        for fixture, expected, hostname in [
            ('exact', True, HOST), ('wildcard', True, HOST),
            ('foreign', False, HOST), ('wildcard', False, 'nested.' + HOST),
            ('malformed', False, HOST), ('missing', False, HOST),
        ]:
            with self.subTest(fixture=fixture, hostname=hostname):
                self.assert_admission(task, fixture, expected, hostname)

    def test_source_certificate_gate_before_projection_and_reload(self):
        task = self.gate('relay_docker_nginx',
                         'Validate configured relay certificate hostname and key pair without printing private material')
        self.hostname_cases(task)
        with self.subTest(keypair='mismatch'):
            self.assert_admission(task, 'exact', False, key_fixture='foreign')

    def test_staged_certificate_gate_before_installation_and_reload(self):
        task = self.gate('relay_docker_nginx', 'Validate staged certificate projection before installation')
        self.hostname_cases(task)

    @unittest.skipUnless(os.name != 'nt' and os.geteuid() == 0,
                         'issued gate requires real root-owned synthetic certificate/key metadata')
    def test_issued_certificate_gate_before_readiness(self):
        task = self.gate('relay_tls', 'Validate the issued ACME certificate and host-local private key')
        self.hostname_cases(task)
        with self.subTest(keypair='mismatch'):
            self.assert_admission(task, 'exact', False, key_fixture='foreign')
        with self.subTest(validity='expired'):
            self.assert_admission(task, 'expired', False)

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
