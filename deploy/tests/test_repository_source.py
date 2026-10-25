"""Configured private consumer credentials are read-only, narrow and transient."""
import base64
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
import repository_source as source
import owner_lifecycle as owner

REPOSITORY = 'example/private-consumer'
HEAD = 'a' * 40
TOKEN = 'synthetic_consumer_read_token'
JWT = 'synthetic.app.jwt'


def fixture(public=False):
    config = {'consumer': {'repositories': [REPOSITORY], 'writerApp': {'appId': '101',
        'installationId': '202', 'slug': 'configured-writer', 'expectedActor': 'configured-writer[bot]'},
        'paths': {'credentialKeyFile': '/etc/example/writer.pem'}}, 'environment': {'namespace': 'example'}}
    repository = {'full_name': REPOSITORY, 'id': 311, 'private': not public, 'default_branch': 'main',
                  'owner': {'login': 'example', 'id': 77, 'type': 'Organization'}}
    grant = {'id': 202, 'app_id': 101, 'account': {'login': 'example', 'id': 77, 'type': 'Organization'},
             'target_type': 'Organization',
             'permissions': {'contents': 'write', 'metadata': 'read'}, 'suspended_at': None}
    values = {
        ('GET', '/app'): {'id': 101, 'slug': 'configured-writer', 'permissions': {'contents': 'write'}},
        ('GET', '/app/installations/202'): copy.deepcopy(grant),
        ('GET', '/repos/' + REPOSITORY + '/installation'): copy.deepcopy(grant),
        ('POST', '/app/installations/202/access_tokens'): {'token': TOKEN,
            'permissions': {'contents': 'read', 'metadata': 'read'}, 'repositories': [copy.deepcopy(repository)]},
        ('GET', '/repos/' + REPOSITORY): repository,
        ('GET', '/repos/' + REPOSITORY + '/git/ref/heads/main'): {'ref': 'refs/heads/main',
            'object': {'type': 'commit', 'sha': HEAD}},
        ('DELETE', '/installation/token'): None}
    calls = []

    def api(method, path, token=None, body=None):
        calls.append((method, path, token, copy.deepcopy(body)))
        if method == 'GET' and path == '/repos/' + REPOSITORY and token is None and not public:
            raise source.APIError(404)
        return copy.deepcopy(values[method, path])

    return config, values, calls, api


class RepositorySourceTests(unittest.TestCase):
    def setUp(self):
        signer = patch.object(source, '_jwt', return_value=JWT)
        self.signer = signer.start(); self.addCleanup(signer.stop)
        root = patch.object(source.os, 'geteuid', return_value=0)
        root.start(); self.addCleanup(root.stop)

    def test_private_grant_mints_only_named_repository_read_permissions_and_revokes(self):
        config, _, calls, api = fixture()
        with source.consumer_access(config, REPOSITORY, api=api) as access:
            self.assertEqual((access.head, access.repository_id, access.private), (HEAD, 311, True))
            self.assertEqual(access.token, TOKEN)
            self.assertNotIn(TOKEN, repr(access))
        self.assertIsNone(access.token)
        request = next(row for row in calls if row[0] == 'POST')
        self.assertEqual(request[3], {'repositories': ['private-consumer'],
            'permissions': {'contents': 'read', 'metadata': 'read'}})
        self.assertEqual(calls[-1], ('DELETE', '/installation/token', TOKEN, None))
        self.signer.assert_called_once_with('/etc/example/writer.pem', 101)

    def test_public_consumer_uses_anonymous_main_without_key_or_token(self):
        config, _, calls, api = fixture(public=True)
        with source.consumer_access(config, REPOSITORY, api=api) as access:
            self.assertEqual(access.head, HEAD)
            self.assertFalse(access.private)
            self.assertIsNone(access.token)
        self.signer.assert_not_called()
        self.assertTrue(all(row[0] == 'GET' and row[2] is None for row in calls))

    def test_anonymous_403_never_substitutes_credentials(self):
        config, _, calls, _ = fixture()
        with self.assertRaisesRegex(source.ConsumerSourceError, '^CONSUMER_SOURCE_HTTP_403$'):
            with source.consumer_access(config, REPOSITORY, api=lambda *args: (_ for _ in ()).throw(source.APIError(403))):
                self.fail('403 entered credential context')
        self.signer.assert_not_called()

    def test_wrong_app_installation_or_repo_grant_stops_before_token_mint(self):
        cases = [('GET', '/app', 'id', 999), ('GET', '/app', 'slug', 'another-writer'),
            ('GET', '/app', 'permissions', {'contents': 'none'}),
            ('GET', '/app/installations/202', 'account', {'login': 'foreign', 'id': 77}),
            ('GET', '/repos/' + REPOSITORY + '/installation', 'id', 999),
            ('GET', '/repos/' + REPOSITORY + '/installation', 'app_id', 999)]
        for method, path, field, value in cases:
            config, values, calls, api = fixture(); values[method, path][field] = value
            with self.assertRaises(source.ConsumerSourceError):
                with source.consumer_access(config, REPOSITORY, api=api):
                    self.fail('bad grant entered credential context')
            self.assertFalse(any(row[0] == 'POST' for row in calls))
        config, _, calls, api = fixture()
        with self.assertRaisesRegex(source.ConsumerSourceError, '^CONSUMER_SOURCE_REPOSITORY_NOT_CONFIGURED$'):
            with source.consumer_access(config, 'example/foreign', api=api):
                self.fail('foreign repository entered context')
        self.assertEqual(calls, [])

    def test_namespace_key_boundary_prevents_cross_installation_signing(self):
        config, _, calls, api = fixture()
        config['consumer']['paths']['credentialKeyFile'] = '/etc/production/writer.pem'
        with self.assertRaisesRegex(source.ConsumerSourceError, '^CONSUMER_SOURCE_KEY_NAMESPACE_MISMATCH$'):
            with source.consumer_access(config, REPOSITORY, api=api):
                self.fail('cross-namespace key entered source context')
        self.assertFalse(any(row[1] == '/app' or row[0] == 'POST' for row in calls))
        self.signer.assert_not_called()

    def test_owner_reviewed_key_reference_is_not_gated_by_old_consumer_values(self):
        config, _, _, api = fixture()
        config['consumer']['paths']['credentialKeyFile'] = '/etc/example/rotated-writer.pem'
        with source.consumer_access(config, REPOSITORY, api=api):
            pass
        self.signer.assert_called_once_with('/etc/example/rotated-writer.pem', 101)

    def test_owner_reviewed_app_selection_uses_only_that_exact_existing_grant(self):
        config, values, calls, api = fixture()
        config['consumer']['writerApp'] = {'appId': '303', 'installationId': '404',
            'slug': 'selected-writer', 'expectedActor': 'selected-writer[bot]'}
        values['GET', '/app'].update(id=303, slug='selected-writer')
        installation = values.pop(('GET', '/app/installations/202'))
        installation.update(id=404, app_id=303)
        values['GET', '/app/installations/404'] = installation
        values['GET', '/repos/' + REPOSITORY + '/installation'].update(id=404, app_id=303)
        values['POST', '/app/installations/404/access_tokens'] = values.pop(('POST', '/app/installations/202/access_tokens'))
        with source.consumer_access(config, REPOSITORY, api=api):
            pass
        self.signer.assert_called_once_with('/etc/example/writer.pem', 303)
        self.assertFalse(any('/installations/202' in row[1] for row in calls))

    def test_scope_private_repo_and_main_mismatches_revoke_issued_token(self):
        cases = [('POST', '/app/installations/202/access_tokens', 'permissions', {'contents': 'write', 'metadata': 'read'}),
            ('POST', '/app/installations/202/access_tokens', 'repositories', []),
            ('GET', '/repos/' + REPOSITORY, 'id', 999),
            ('GET', '/repos/' + REPOSITORY, 'private', False),
            ('GET', '/repos/' + REPOSITORY, 'default_branch', 'other'),
            ('GET', '/repos/' + REPOSITORY + '/git/ref/heads/main', 'object', {'type': 'commit', 'sha': 'refs/pull/1/head'})]
        for method, path, field, value in cases:
            config, values, calls, api = fixture(); values[method, path][field] = value
            with self.assertRaises(source.ConsumerSourceError):
                with source.consumer_access(config, REPOSITORY, api=api):
                    self.fail('bad token scope entered context')
            self.assertEqual(calls[-1][:3], ('DELETE', '/installation/token', TOKEN))

    def test_consumer_fetch_failure_revokes_and_unknown_revocation_is_explicit(self):
        config, _, calls, api = fixture()
        with self.assertRaisesRegex(ValueError, '^fixture-fetch-failed$'):
            with source.consumer_access(config, REPOSITORY, api=api) as access:
                raise ValueError('fixture-fetch-failed')
        self.assertIsNone(access.token)
        self.assertEqual(calls[-1][0], 'DELETE')

        def fail_revoke(method, path, token=None, body=None):
            if method == 'DELETE':
                raise source.APIError(500)
            return api(method, path, token, body)

        with self.assertRaisesRegex(source.ConsumerSourceError, '^CONSUMER_SOURCE_TOKEN_REVOCATION_UNPROVEN$'):
            with source.consumer_access(config, REPOSITORY, api=fail_revoke):
                pass

    def test_http_unknown_403_is_fixed_and_does_not_expose_response_or_credential(self):
        with patch.object(source.http.client, 'HTTPSConnection') as connection:
            connection.return_value.getresponse.return_value.status = 403
            connection.return_value.getresponse.return_value.read.return_value = TOKEN.encode()
            with self.assertRaisesRegex(source.ConsumerSourceError, '^CONSUMER_SOURCE_HTTP_403$') as caught:
                source.github_api('GET', '/repos/' + REPOSITORY, TOKEN)
            self.assertNotIn(TOKEN, str(caught.exception))
            connection.return_value.getresponse.return_value.read.assert_not_called()
            connection.return_value.close.assert_called_once()


class GitSourceTransportTests(unittest.TestCase):
    def test_git_fetch_has_plain_url_and_environment_only_auth_without_persistent_config(self):
        with tempfile.TemporaryDirectory(prefix='relay-consumer-fetch-', dir='/tmp') as name:
            root = Path(name) / 'checkout'; calls = []

            def git(directory, *args, **kwargs):
                calls.append((args, kwargs))
                if args[0] == 'rev-parse': return HEAD
                if args[:3] == ('ls-tree', '-r', '--name-only'): return 'README.md'
                if args[0] == 'ls-tree': return '100644 blob ' + HEAD + '\tREADME.md'
                return ''

            with patch.object(owner, 'git', side_effect=git):
                self.assertEqual(owner.acquire_source(root, REPOSITORY, HEAD, read_token=TOKEN), root)
            args, keywords = next(row for row in calls if row[0][0] == 'fetch')
            self.assertEqual(args[-2:], ('https://github.com/' + REPOSITORY + '.git', HEAD))
            self.assertNotIn(TOKEN, str(args))
            env = keywords['environment']
            self.assertEqual(env['HOME'], str(root))
            settings = {env['GIT_CONFIG_KEY_' + str(i)]: env['GIT_CONFIG_VALUE_' + str(i)]
                        for i in range(int(env['GIT_CONFIG_COUNT']))}
            self.assertEqual(settings['credential.helper'], '')
            self.assertEqual(settings['http.followRedirects'], 'false')
            header = settings['http.https://github.com/' + REPOSITORY + '.git.extraHeader']
            self.assertEqual(base64.b64decode(header.removeprefix('AUTHORIZATION: basic ')).decode(), 'x-access-token:' + TOKEN)
            self.assertFalse((root / '.git/config').exists())
            self.assertTrue(all('environment' not in kw for a, kw in calls if a[0] != 'fetch'))

    def test_anonymous_git_env_clears_headers_helpers_traces_and_global_configs(self):
        env = source.git_read_environment({'PATH': '/usr/bin:/bin', 'GIT_TRACE': '1',
            'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_99': 'credential.helper',
            'GIT_CONFIG_VALUE_99': TOKEN, 'GIT_ASKPASS': '/untrusted'}, REPOSITORY)
        self.assertNotIn(TOKEN, str(env)); self.assertNotIn('GIT_TRACE', env)
        self.assertNotIn('GIT_ASKPASS', env); self.assertNotIn('GIT_CONFIG_VALUE_99', env)
        self.assertEqual(env['GIT_CONFIG_GLOBAL'], '/dev/null')
        self.assertFalse(any(key.endswith('extraHeader') and value for key, value in
            [(env['GIT_CONFIG_KEY_' + str(i)], env['GIT_CONFIG_VALUE_' + str(i)])
             for i in range(int(env['GIT_CONFIG_COUNT']))]))

    def test_signer_uses_validated_fd_and_never_key_bytes_in_argv(self):
        with tempfile.TemporaryDirectory(prefix='relay-consumer-key-', dir='/tmp') as name:
            root = Path(name); key = root / 'key.pem'; key.write_bytes(b'synthetic-local-key'); key.chmod(0o600)
            captured = []

            def sign(argv, **kwargs):
                fd = kwargs['pass_fds'][0]; captured.append(fd)
                self.assertEqual(argv[-1], '/proc/self/fd/' + str(fd))
                self.assertEqual(os.read(fd, 100), b'synthetic-local-key')
                self.assertNotIn('synthetic-local-key', str(argv))
                self.assertNotIn(str(key), str(argv))
                self.assertNotIn(b'synthetic-local-key', kwargs['input'])
                return SimpleNamespace(returncode=0, stdout=b'signature')

            with patch.object(source.subprocess, 'run', side_effect=sign):
                jwt = source._jwt(key, 101, owner_uid=os.getuid(), boundary=root)
            self.assertEqual(len(jwt.split('.')), 3)
            with self.assertRaises(OSError): os.fstat(captured[0])
            alias = root / 'alias'; os.link(key, alias)
            with self.assertRaisesRegex(source.ConsumerSourceError, '^CONSUMER_SOURCE_KEY_UNSAFE$'):
                source._jwt(key, 101, owner_uid=os.getuid(), boundary=root)


if __name__ == '__main__':
    unittest.main()
