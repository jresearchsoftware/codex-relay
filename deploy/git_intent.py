"""Bind private deployment bytes and public product main to one owner dispatch.

The workflow token is transient input only. Nothing in this module logs, writes
credentials, follows redirects, or accepts a caller-selected network endpoint.
"""
import base64
import binascii
import hashlib
import http.client
import json
import re
import ssl


MAX_CONFIG_BYTES = 256 * 1024
MAX_RESPONSE_BYTES = 512 * 1024
MAX_TOKEN_BYTES = 4096
WORKFLOW = '.github/workflows/manual-main-production-deploy.yml'


class GitIntentError(ValueError):
    """A public fixed-code error; never includes response or credential bytes."""


def require(condition, code):
    if not condition:
        raise GitIntentError(code)


def _sha(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{40}', value) is not None


def _positive(value):
    return type(value) is int and 0 < value <= 9007199254740991


def _token(value):
    require(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_]{1,4096}', value) is not None,
            'GIT_INTENT_TOKEN_INVALID')
    return value


def read_token(stream):
    """Read one bounded token from stdin through EOF, with optional final newline."""
    try:
        value = stream.read(MAX_TOKEN_BYTES + 3)
        if isinstance(value, bytes):
            value = value.decode('ascii')
        require(isinstance(value, str), 'GIT_INTENT_TOKEN_INVALID')
        if value.endswith('\r\n'):
            value = value[:-2]
        elif value.endswith('\n'):
            value = value[:-1]
        return _token(value)
    except (OSError, UnicodeError):
        raise GitIntentError('GIT_INTENT_TOKEN_INVALID') from None


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, 'GIT_INTENT_RESPONSE_INVALID')
        value[key] = item
    return value


def github_api(path, token=None):
    """One bounded HTTPS GET to GitHub; http.client never follows redirects."""
    require(isinstance(path, str) and path.startswith('/repos/')
            and re.fullmatch(r'/[A-Za-z0-9_./?=&-]+', path) is not None,
            'GIT_INTENT_PATH_INVALID')
    headers = {'Accept': 'application/vnd.github+json',
               'X-GitHub-Api-Version': '2022-11-28',
               'User-Agent': 'codex-relay-git-intent'}
    if token is not None:
        headers['Authorization'] = 'Bearer ' + _token(token)
    connection = http.client.HTTPSConnection('api.github.com', timeout=30,
                                             context=ssl.create_default_context())
    try:
        connection.request('GET', path, headers=headers)
        response = connection.getresponse()
        require(response.status == 200, 'GIT_INTENT_HTTP_STATUS')
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        require(len(raw) <= MAX_RESPONSE_BYTES, 'GIT_INTENT_RESPONSE_TOO_LARGE')
        result = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object)
        require(isinstance(result, dict), 'GIT_INTENT_RESPONSE_INVALID')
        return result
    except GitIntentError:
        raise
    except (OSError, http.client.HTTPException, UnicodeError, ValueError):
        raise GitIntentError('GIT_INTENT_HTTP_FAILED') from None
    finally:
        connection.close()


def _repository(api, repository, token, private):
    data = api('/repos/' + repository, token)
    require(isinstance(data, dict) and data.get('full_name') == repository
            and _positive(data.get('id')) and data.get('private') is private
            and data.get('default_branch') == 'main', 'GIT_INTENT_REPOSITORY_MISMATCH')
    return data


def _main(api, repository, token):
    data = api('/repos/' + repository + '/git/ref/heads/main', token)
    obj = data.get('object', {}) if isinstance(data, dict) else {}
    require(isinstance(data, dict) and isinstance(obj, dict)
            and data.get('ref') == 'refs/heads/main' and obj.get('type') == 'commit'
            and _sha(obj.get('sha')), 'GIT_INTENT_MAIN_INVALID')
    return obj['sha']


def _file_blob(api, prefix, config_sha, path, token):
    tree_sha = config_sha
    parts = path.split('/')
    for index, part in enumerate(parts):
        tree = api(prefix + '/git/trees/' + tree_sha, token)
        require(isinstance(tree, dict) and tree.get('truncated') is False
                and isinstance(tree.get('tree'), list), 'GIT_INTENT_TREE_INVALID')
        entries = [entry for entry in tree['tree'] if isinstance(entry, dict) and entry.get('path') == part]
        require(len(entries) == 1 and _sha(entries[0].get('sha')), 'GIT_INTENT_FILE_INVALID')
        entry = entries[0]
        if index == len(parts) - 1:
            require(entry.get('type') == 'blob' and entry.get('mode') == '100644',
                    'GIT_INTENT_FILE_INVALID')
            return entry['sha']
        require(entry.get('type') == 'tree' and entry.get('mode') == '040000',
                'GIT_INTENT_FILE_INVALID')
        tree_sha = entry['sha']


def _product_selection(raw, product, binding, api):
    require(len(raw) <= 64 * 1024, 'GIT_INTENT_CONFIG_TOO_LARGE')
    try:
        config = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object,
                            parse_constant=lambda _: require(False, 'GIT_INTENT_CONFIG_INVALID'))
    except (UnicodeError, ValueError):
        raise GitIntentError('GIT_INTENT_CONFIG_INVALID') from None
    source = config.get('source') if isinstance(config, dict) else None
    repository = source.get('repository') if isinstance(source, dict) else None
    require(isinstance(repository, str) and re.fullmatch(
        r'(?:https://github\.com/|git@github\.com:)[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?', repository) is not None,
        'GIT_INTENT_PRODUCT_SOURCE_INVALID')
    repository = repository.removeprefix('https://github.com/').removeprefix('git@github.com:').removesuffix('.git')
    require(repository == product, 'GIT_INTENT_PRODUCT_SOURCE_MISMATCH')
    selected = source.get('revision', 'main')
    require(selected == 'main' or _sha(selected), 'GIT_INTENT_PRODUCT_REVISION_INVALID')
    main_sha = _main(api, product, None)
    qualification = binding.get('qualificationProductSha')
    if qualification is not None and selected == qualification:
        commit = api('/repos/' + product + '/git/commits/' + selected, None)
        require(isinstance(commit, dict) and commit.get('sha') == selected,
                'GIT_INTENT_QUALIFICATION_COMMIT_INVALID')
        return selected, 'test-qualified-exact'
    if selected == 'main' or selected == main_sha:
        return main_sha, 'accepted-main'
    # Page two omits GitHub's potentially large first-page changed-file patches.
    # Both endpoints are frozen SHAs; a subsequent main move cannot change proof.
    comparison = api('/repos/' + product + '/compare/' + selected + '...' + main_sha
                     + '?per_page=1&page=2', None)
    require(isinstance(comparison, dict) and comparison.get('status') in ('ahead', 'identical')
            and isinstance(comparison.get('base_commit'), dict) and comparison['base_commit'].get('sha') == selected
            and isinstance(comparison.get('merge_base_commit'), dict)
            and comparison['merge_base_commit'].get('sha') == selected and comparison.get('behind_by') == 0,
            'GIT_INTENT_PRODUCT_NOT_ACCEPTED')
    return selected, 'accepted-ancestor'


def resolve_pair(binding, dispatch, token, *, api=None):
    """Return private config_bytes and a nonsecret frozen-pair receipt.

    ``api(path, token)`` is an optional test transport. Production requests always
    use the fixed HTTPS GitHub API; public product requests receive no token.
    """
    api = github_api if api is None else api
    token = _token(token)
    require(isinstance(binding, dict) and isinstance(dispatch, dict), 'GIT_INTENT_INPUT_INVALID')
    require(binding.get('qualificationProductSha') is None or _sha(binding['qualificationProductSha']),
            'GIT_INTENT_QUALIFICATION_BINDING_INVALID')
    repository, product = binding.get('repository'), binding.get('productRepository')
    for name in (repository, product):
        require(isinstance(name, str) and re.fullmatch(
            r'[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}', name) is not None
            and not name.endswith('.git'), 'GIT_INTENT_BINDING_INVALID')
    owner, path = binding.get('owner'), binding.get('configPath')
    require(isinstance(owner, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}', owner) is not None
            and binding.get('workflow', WORKFLOW) == WORKFLOW, 'GIT_INTENT_BINDING_INVALID')
    require(isinstance(path, str) and re.fullmatch(r'[A-Za-z0-9_./-]{1,240}', path) is not None
            and 1 <= len(path.split('/')) <= 16
            and all(part not in ('', '.', '..') for part in path.split('/')),
            'GIT_INTENT_CONFIG_PATH_INVALID')
    config_sha, run_id, action = dispatch.get('configSha'), dispatch.get('runId'), dispatch.get('action')
    require(_sha(config_sha) and _positive(run_id) and action in ('apply', 'stop', 'resume'),
            'GIT_INTENT_DISPATCH_INVALID')
    config_repo = _repository(api, repository, token, True)
    require(_main(api, repository, token) == config_sha, 'GIT_INTENT_CONFIG_MAIN_CHANGED')
    prefix = '/repos/' + repository
    run = api(prefix + '/actions/runs/' + str(run_id), token)
    require(isinstance(run, dict) and _positive(run.get('id')) and run.get('id') == run_id
            and _positive(run.get('run_attempt')) and run.get('event') == 'workflow_dispatch'
            and run.get('path') in (WORKFLOW, WORKFLOW + '@main', WORKFLOW + '@refs/heads/main')
            and run.get('head_branch') == 'main' and run.get('head_sha') == config_sha
            and all(isinstance(run.get(field), dict) and isinstance(run[field].get('login'), str)
                    and run[field]['login'].casefold() == owner.casefold() and _positive(run[field].get('id'))
                    for field in ('actor', 'triggering_actor'))
            and run['actor']['id'] == run['triggering_actor']['id']
            and all(isinstance(run.get(field), dict) and run[field].get('id') == config_repo['id']
                    and run[field].get('full_name') == repository for field in ('repository', 'head_repository')),
            'GIT_INTENT_WORKFLOW_MISMATCH')
    blob = _file_blob(api, prefix, config_sha, path, token)
    file = api(prefix + '/contents/' + path + '?ref=' + config_sha, token)
    require(isinstance(file, dict) and file.get('type') == 'file' and file.get('path') == path
            and file.get('sha') == blob and file.get('encoding') == 'base64'
            and type(file.get('size')) is int and 0 < file['size'] <= MAX_CONFIG_BYTES
            and isinstance(file.get('content'), str) and 'target' not in file
            and not file.get('submodule_git_url'), 'GIT_INTENT_FILE_INVALID')
    encoded = file['content']
    require(len(encoded) <= (MAX_CONFIG_BYTES * 4 // 3 + 4) * 2
            and re.fullmatch(r'[A-Za-z0-9+/=\r\n]*', encoded) is not None,
            'GIT_INTENT_CONTENT_INVALID')
    try:
        raw = base64.b64decode(encoded.replace('\r', '').replace('\n', ''), validate=True)
    except (ValueError, binascii.Error):
        raise GitIntentError('GIT_INTENT_CONTENT_INVALID') from None
    require(len(raw) == file['size'] and hashlib.sha1(
        b'blob ' + str(len(raw)).encode('ascii') + b'\0' + raw).hexdigest() == blob,
        'GIT_INTENT_BLOB_MISMATCH')
    require(token.encode('ascii') not in raw and not re.search(
        rb'PRIVATE KEY|(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]{20,}', raw),
        'GIT_INTENT_SECRET_CONTENT')
    product_repo = _repository(api, product, None, False)
    product_sha, source_policy = _product_selection(raw, product, binding, api)
    return {'config_bytes': raw, 'receipt': {
        'config_repository': repository, 'config_repository_id': config_repo['id'],
        'config_path': path, 'config_sha': config_sha, 'config_blob_sha': blob,
        'config_sha256': hashlib.sha256(raw).hexdigest(),
        'product_repository': product, 'product_repository_id': product_repo['id'],
        'product_sha': product_sha, 'source_policy': source_policy, 'workflow_run_id': run_id, 'action': action}}
