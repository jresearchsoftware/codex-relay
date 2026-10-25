"""Offline boundary checks for authenticated Git deployment intent."""
import base64
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location('git_intent', Path(__file__).parents[1] / 'git_intent.py')
intent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(intent)
CONFIG_SHA = 'a' * 40
PRODUCT_SHA = 'b' * 40
TOKEN = 'synthetic_workflow_credential'
PRIVATE = 'example/private-config'
PUBLIC = 'example/product'
PATH = 'deploy/production.json'
DEFAULT_CONFIG = b'{"source":{"repository":"https://github.com/example/product"}}'


def fixture(raw=DEFAULT_CONFIG):
    blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    private = {'full_name': PRIVATE, 'id': 17, 'private': True, 'default_branch': 'main'}
    prefix = '/repos/' + PRIVATE
    values = {
        prefix: private,
        prefix + '/git/ref/heads/main': {'ref': 'refs/heads/main', 'object': {'type': 'commit', 'sha': CONFIG_SHA}},
        prefix + '/actions/runs/31': {'id': 31, 'run_attempt': 1, 'event': 'workflow_dispatch',
            'path': intent.WORKFLOW, 'head_branch': 'main', 'head_sha': CONFIG_SHA,
            'actor': {'login': 'owner', 'id': 11}, 'triggering_actor': {'login': 'owner', 'id': 11},
            'repository': copy.deepcopy(private), 'head_repository': copy.deepcopy(private)},
        prefix + '/git/trees/' + CONFIG_SHA: {'truncated': False, 'tree': [
            {'path': 'deploy', 'type': 'tree', 'mode': '040000', 'sha': 'c' * 40}]},
        prefix + '/git/trees/' + 'c' * 40: {'truncated': False, 'tree': [
            {'path': 'production.json', 'type': 'blob', 'mode': '100644', 'sha': blob}]},
        prefix + '/contents/' + PATH + '?ref=' + CONFIG_SHA: {'type': 'file', 'path': PATH,
            'sha': blob, 'encoding': 'base64', 'size': len(raw), 'content': base64.b64encode(raw).decode()},
        '/repos/' + PUBLIC: {'full_name': PUBLIC, 'id': 18, 'private': False, 'default_branch': 'main'},
        '/repos/' + PUBLIC + '/git/ref/heads/main': {'ref': 'refs/heads/main',
            'object': {'type': 'commit', 'sha': PRODUCT_SHA}}}
    binding = {'repository': PRIVATE, 'configPath': PATH, 'owner': 'owner',
               'productRepository': PUBLIC, 'workflow': intent.WORKFLOW}
    dispatch = {'configSha': CONFIG_SHA, 'runId': 31, 'action': 'apply'}
    calls = []

    def api(path, token):
        calls.append((path, token))
        return copy.deepcopy(values[path])

    return binding, dispatch, values, calls, api


class GitIntentTests(unittest.TestCase):
    def test_freezes_pair_and_keeps_product_anonymous(self):
        binding, dispatch, values, calls, api = fixture()
        result = intent.resolve_pair(binding, dispatch, TOKEN, api=api)
        self.assertEqual(result['config_bytes'], DEFAULT_CONFIG)
        receipt = result['receipt']
        self.assertEqual(receipt['config_sha'], CONFIG_SHA)
        self.assertEqual(receipt['config_path'], PATH)
        self.assertEqual(receipt['product_sha'], PRODUCT_SHA)
        self.assertEqual(receipt['source_policy'], 'accepted-main')
        self.assertEqual(receipt['config_sha256'], hashlib.sha256(result['config_bytes']).hexdigest())
        self.assertNotIn(TOKEN, json.dumps(receipt))
        self.assertNotIn('synthetic', json.dumps(receipt))
        for path, token in calls:
            self.assertEqual(token, None if path.startswith('/repos/' + PUBLIC) else TOKEN)
        self.assertTrue(any('?ref=' + CONFIG_SHA in path for path, _ in calls))

    def test_all_actions_and_invalid_dispatch(self):
        for action in ('apply', 'stop', 'resume'):
            binding, dispatch, _, _, api = fixture()
            dispatch['action'] = action
            self.assertEqual(intent.resolve_pair(binding, dispatch, TOKEN, api=api)['receipt']['action'], action)
        for field, value in [('configSha', 'main'), ('configSha', 'refs/pull/1/head'),
                             ('runId', True), ('runId', 0), ('action', 'restart')]:
            binding, dispatch, _, calls, api = fixture()
            dispatch[field] = value
            with self.assertRaisesRegex(intent.GitIntentError, '^GIT_INTENT_DISPATCH_INVALID$'):
                intent.resolve_pair(binding, dispatch, TOKEN, api=api)
            self.assertEqual(calls, [])

    def test_path_and_repository_cannot_select_endpoint_or_ref(self):
        for key, value in [('configPath', '../secret'), ('configPath', '/absolute'),
                           ('configPath', 'x?ref=main'), ('configPath', 'a%2fb'),
                           ('configPath', 'a\\b'), ('repository', 'https://evil.test/repo'),
                           ('workflow', '.github/workflows/other.yml')]:
            binding, dispatch, _, calls, api = fixture()
            binding[key] = value
            with self.assertRaises(intent.GitIntentError):
                intent.resolve_pair(binding, dispatch, TOKEN, api=api)
            self.assertEqual(calls, [])

    def test_repository_main_and_native_workflow_bindings(self):
        prefix = '/repos/' + PRIVATE
        cases = [(prefix, 'full_name', 'other/repo'), (prefix, 'id', False),
                 (prefix, 'private', False), (prefix, 'default_branch', 'other'),
                 (prefix + '/git/ref/heads/main', 'object', {'type': 'commit', 'sha': 'd' * 40}),
                 ('/repos/' + PUBLIC, 'private', True), ('/repos/' + PUBLIC, 'default_branch', 'master')]
        run_path = prefix + '/actions/runs/31'
        cases += [(run_path, key, value) for key, value in [
            ('event', 'pull_request'), ('actor', {'login': 'attacker'}),
            ('triggering_actor', {'login': 'attacker'}), ('run_attempt', 0),
            ('path', intent.WORKFLOW + '@feature'), ('head_sha', 'e' * 40), ('head_branch', 'feature'),
            ('triggering_actor', {'login': 'owner', 'id': 12}),
            ('repository', {'id': 99, 'full_name': PRIVATE}),
            ('head_repository', {'id': 17, 'full_name': 'fork/private-config'})]]
        for path, key, value in cases:
            with self.subTest(path=path, key=key):
                binding, dispatch, values, _, api = fixture()
                values[path][key] = value
                with self.assertRaises(intent.GitIntentError):
                    intent.resolve_pair(binding, dispatch, TOKEN, api=api)

    def test_symlink_submodule_and_blob_integrity(self):
        for mode in ('120000', '160000', '040000', '100755'):
            binding, dispatch, values, _, api = fixture()
            values['/repos/' + PRIVATE + '/git/trees/' + 'c' * 40]['tree'][0]['mode'] = mode
            with self.assertRaisesRegex(intent.GitIntentError, '^GIT_INTENT_FILE_INVALID$'):
                intent.resolve_pair(binding, dispatch, TOKEN, api=api)

    def test_documented_workflow_path_refs_and_owner_case(self):
        for suffix in ('', '@main', '@refs/heads/main'):
            binding, dispatch, values, _, api = fixture()
            run = values['/repos/' + PRIVATE + '/actions/runs/31']
            run['path'] = intent.WORKFLOW + suffix
            run['actor']['login'] = 'OWNER'
            intent.resolve_pair(binding, dispatch, TOKEN, api=api)

    def test_contents_hash_size_and_encoding(self):
        content_path = '/repos/' + PRIVATE + '/contents/' + PATH + '?ref=' + CONFIG_SHA
        for field, value in [('content', '!!notbase64'), ('content', base64.b64encode(b'x' * 27).decode()),
                             ('size', intent.MAX_CONFIG_BYTES + 1), ('type', 'symlink'), ('sha', 'f' * 40)]:
            binding, dispatch, values, _, api = fixture()
            values[content_path][field] = value
            with self.assertRaises(intent.GitIntentError):
                intent.resolve_pair(binding, dispatch, TOKEN, api=api)

    def test_obvious_secrets_never_return(self):
        for raw in (b'-----BEGIN PRIVATE KEY-----', b'ghp_' + b'a' * 30, TOKEN.encode()):
            binding, dispatch, _, _, api = fixture(raw)
            with self.assertRaisesRegex(intent.GitIntentError, '^GIT_INTENT_SECRET_CONTENT$') as caught:
                intent.resolve_pair(binding, dispatch, TOKEN, api=api)
            self.assertNotIn(raw.decode(), str(caught.exception))

    def test_frozen_source_ancestor_uses_anonymous_frozen_compare_without_file_patches(self):
        selected = 'd' * 40
        raw = json.dumps({'source': {'repository': 'git@github.com:example/product.git', 'revision': selected}}).encode()
        binding, dispatch, values, calls, api = fixture(raw)
        path = '/repos/' + PUBLIC + '/compare/' + selected + '...' + PRODUCT_SHA + '?per_page=1&page=2'
        values[path] = {'status': 'ahead', 'base_commit': {'sha': selected},
                        'merge_base_commit': {'sha': selected}, 'behind_by': 0}
        result = intent.resolve_pair(binding, dispatch, TOKEN, api=api)
        self.assertEqual(result['receipt']['product_sha'], selected)
        self.assertEqual(result['receipt']['source_policy'], 'accepted-ancestor')
        self.assertIn((path, None), calls)
        for key, value in [('status', 'diverged'), ('behind_by', 1),
                           ('merge_base_commit', {'sha': PRODUCT_SHA}), ('base_commit', {'sha': PRODUCT_SHA})]:
            original = copy.deepcopy(values[path]); values[path][key] = value
            with self.assertRaisesRegex(intent.GitIntentError, '^GIT_INTENT_PRODUCT_NOT_ACCEPTED$'):
                intent.resolve_pair(binding, dispatch, TOKEN, api=api)
            values[path] = original

    def test_test_qualification_pin_is_protected_exact_and_never_a_source_ref_escape(self):
        selected = 'e' * 40
        raw = json.dumps({'source': {'repository': 'https://github.com/' + PUBLIC, 'revision': selected}}).encode()
        binding, dispatch, values, calls, api = fixture(raw)
        binding['qualificationProductSha'] = selected
        path = '/repos/' + PUBLIC + '/git/commits/' + selected
        values[path] = {'sha': selected}
        result = intent.resolve_pair(binding, dispatch, TOKEN, api=api)
        self.assertEqual(result['receipt']['source_policy'], 'test-qualified-exact')
        self.assertEqual(result['receipt']['product_sha'], selected)
        self.assertIn((path, None), calls)
        self.assertFalse(any('/compare/' in path for path, _ in calls))
        values[path]['sha'] = PRODUCT_SHA
        with self.assertRaisesRegex(intent.GitIntentError, '^GIT_INTENT_QUALIFICATION_COMMIT_INVALID$'):
            intent.resolve_pair(binding, dispatch, TOKEN, api=api)

    def test_source_is_literal_json_and_only_bound_main_or_accepted_full_sha(self):
        invalid = [b'{"source":{},"source":{}}', b'{"source":NaN}', b'x' * 65537,
                   json.dumps({'source': {'repository': 'https://github.com/other/product'}}).encode()]
        invalid += [json.dumps({'source': {'repository': 'https://github.com/' + PUBLIC, 'revision': revision}}).encode()
                    for revision in ('refs/pull/1/head', 'feature', '../main', 'main?ref=branch')]
        for raw in invalid:
            binding, dispatch, _, _, api = fixture(raw)
            with self.assertRaises(intent.GitIntentError):
                intent.resolve_pair(binding, dispatch, TOKEN, api=api)

    def test_token_stdin_is_bounded_and_strict(self):
        for suffix in (b'', b'\n', b'\r\n'):
            self.assertEqual(intent.read_token(io.BytesIO(TOKEN.encode() + suffix)), TOKEN)
        for value in (b'', b'a b', b'a\nb', b'a\n\n', b'a\r', b'a' * 4097, b'\xff'):
            with self.assertRaisesRegex(intent.GitIntentError, '^GIT_INTENT_TOKEN_INVALID$'):
                intent.read_token(io.BytesIO(value))

    def test_http_redirect_errors_and_oversize_are_not_followed_or_exposed(self):
        for status, data, code in [(302, b'private response', 'GIT_INTENT_HTTP_STATUS'),
                                    (403, TOKEN.encode(), 'GIT_INTENT_HTTP_STATUS'),
                                    (200, b'x' * (intent.MAX_RESPONSE_BYTES + 1), 'GIT_INTENT_RESPONSE_TOO_LARGE'),
                                    (200, b'{bad json', 'GIT_INTENT_HTTP_FAILED'),
                                    (200, b'{"a":1,"a":2}', 'GIT_INTENT_RESPONSE_INVALID')]:
            with patch.object(intent.http.client, 'HTTPSConnection') as connection:
                connection.return_value.getresponse.return_value.status = status
                connection.return_value.getresponse.return_value.read.return_value = data
                with self.assertRaisesRegex(intent.GitIntentError, '^' + code + '$'):
                    intent.github_api('/repos/' + PRIVATE, TOKEN)
                self.assertEqual(connection.call_args.args[0], 'api.github.com')
                self.assertEqual(connection.return_value.request.call_count, 1)
                connection.return_value.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
