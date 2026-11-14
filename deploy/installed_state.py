"""Ephemeral desired-state catalogue for bounded source-only upgrades.

This is a verifier, not an Ansible executor. Explicit task owners below supply
the file recipes; unknown source/profile/recipes refuse the optimization.
"""
import base64
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess


class NotEligible(ValueError):
    def __init__(self, code='INSTALLED_STATE_UNPROVEN'):
        super().__init__(code)


def require(value, code='INSTALLED_STATE_UNPROVEN'):
    if not value:
        raise NotEligible(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def recipe_digest(source_root):
    root = Path(source_root) / 'deploy/ansible'
    rows = []
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root)
        if path.is_file() and 'tests' not in relative.parts and '__pycache__' not in relative.parts:
            rows.append([str(relative).replace('\\', '/'), hashlib.sha256(path.read_bytes()).hexdigest()])
    return hashlib.sha256(canonical(rows)).hexdigest()


# Frozen against the reviewed recipe surface, not an observed installation.
RECIPE_SHA256 = '072327500c8d3eb022ddb545592ad3ac7450ca0b4827de87e2d8fec080f93544'
OWNERS = {
    "roles/relay_codex_runtime/tasks/runtime-namespace.yml": [
        "Reconcile the Codex temporary roots for the runtime identity",
        "Reconcile the Codex arg0 root after its temporary parent"
    ],
    "roles/relay_codex_runtime/tasks/repository-work-root.yml": [
        "Reconcile only fixed repository work ancestor metadata"
    ],
    "roles/relay_runtime/tasks/main.yml": [
        "Create namespaced relay directories",
        "Install Reviewer credential readiness verifier",
        "Install the production operation-state verifier",
        "Install the production Reviewer service start guard",
        "Install the explicit Reviewer activation transition helper",
        "Install the explicit runner-enable transition helper",
        "Install the operation-locked Reviewer restart helper",
        "Install bounded read-only GitHub App qualification implementation",
        "Install Reviewer read-only GitHub App qualification wrapper",
        "Install source-controlled non-secret GitHub App identity contracts",
        "Install owner-local credential provisioning helper",
        "Install the previously authorized Reviewer recovery helper",
        "Install the Reviewer failure runner-stop helper",
        "Install the read-only Reviewer readiness gate for the production runner",
        "Install the Reviewer recovery service unit",
        "Install the Reviewer recovery timer unit",
        "Install secret-free relay environment contract",
        "Install reviewer configuration contract",
        "Install Reviewer MCP service unit",
        "Remove superseded dedicated mTLS proxy unit after it is stopped",
        "Record retention and health contract"
    ],
    "roles/relay_runtime/tasks/production-operation-stale-disposition.yml": [
        "Install the source-controlled stale-disposition helper"
    ],
    "roles/relay_controller/tasks/main.yml": [
        "Create generic-runner-owned on-demand dispatch state namespaces",
        "Preserve the shared Codex work namespace without resetting its mode",
        "Create the root-protected diagnostics namespace",
        "Install the fixed root-owned diagnostics mode control path",
        "Install the grouped read-only qualification diagnostic snapshot helper",
        "Install the narrowly scoped runner sudoers rule for diagnostics storage",
        "Install root-only Writer credential readiness verifier",
        "Install the shared App qualification implementation required by Writer",
        "Install the bounded non-routing Codex qualification probe",
        "Install root-only Writer read-only GitHub App qualification wrapper",
        "Remove the historical Controller daemon unit",
        "Install the root-readable on-demand Controller contract"
    ],
    "roles/relay_controller/tasks/runtime-entrypoints.yml": [
        "Install the root-owned explicit consumer snapshot",
        "Install the fixed root-owned diagnostics store wrapper",
        "Install the fixed root-owned on-demand Codex dispatch wrapper",
        "Install the explicit owner-only non-routing general runner smoke",
        "Install the consumer-owned smoke against the external product ABI"
    ],
    "roles/relay_controller/tasks/writer-entrypoint.yml": [
        "Create root-owned Writer publication record namespace",
        "Install the fixed root-owned on-demand Writer/Controller helper wrapper",
        "Install the fixed Reviewer-accessible manual Outcome client",
        "Install the root-only bounded manual Outcome Writer wrapper",
        "Install the separated bounded manual Outcome socket units",
        "Install the root-only credential-free lifecycle admission helper",
        "Install the narrowly scoped runner sudoers rule for the Writer helper"
    ],
    "roles/relay_codex_runtime/tasks/launcher.yml": [
        "Install the fixed Codex diagnostic helper with every launcher reconciliation",
        "Install the fixed Codex execution module",
        "Install the fixed isolated-slot namespace builder",
        "Install the bounded sandbox cleanup helper for the runtime identity",
        "Install the fixed Codex execution wrapper"
    ],
    "roles/relay_codex_runtime/tasks/main.yml": [
        "Create the fixed Codex runtime and credential namespaces",
        "Install the dedicated Codex sudoers boundary"
    ],
    "roles/relay_runner/tasks/main.yml": [
        "Reconcile root-owned shared runner state parent",
        "Create runner package cache and mutable namespaces",
        "Install runner archive safety validator",
        "Create runner diagnostic namespace with runner ownership",
        "Converge runner root metadata after package reconciliation",
        "Install owner-mediated runner registration helper",
        "Create runner directories",
        "Install runner service structure"
    ],
    "roles/relay_runner/tasks/production-local-apply.yml": [
        "Create the protected installation parent before its local-apply helper",
        "Create root-owned disposable local-apply staging namespace",
        "Create the root-owned production runner drop-in directory",
        "Reconcile the production runner sandbox for local apply",
        "Install the fixed root-owned local production apply helper",
        "Install and validate the narrow production runner sudoers rule",
        "Install the fixed protected owner lifecycle entrypoint",
        "Install the narrow general runner owner lifecycle sudoers rule"
    ],
    "roles/relay_runner/tasks/general-runtime.yml": [
        "Preserve the private routing and shared Codex work boundaries",
        "Install only the existing automatic relay sudo capabilities for the general identity"
    ],
    "tasks/execution-slot.yml": [
        "Create root-owned slot namespace parents",
        "Create private runtime credential and diagnostic destinations",
        "Install fixed credential-free slot dispatcher and diagnostic wrappers",
        "Preserve the same fixed owner lifecycle capability for this automatic slot"
    ],
    "tasks/execution-slot-shared.yml": [
        "Create common root-owned slot namespace parents"
    ],
    "tasks/managed-pool.yml": [
        "Install the fixed root-only owner pool entrypoint"
    ]
}


def render(source, variables):
    from ansible.parsing.dataloader import DataLoader
    from ansible.template import Templar
    try:
        return Templar(loader=DataLoader(), variables=variables).template(source, fail_on_undefined=True)
    except Exception:
        raise NotEligible('INSTALLED_RECIPE_INPUT_UNAVAILABLE') from None


def _tasks(value):
    for task in value:
        yield task
        for key in ['block', 'rescue', 'always']:
            if key in task:
                yield from _tasks(task[key])


def build_catalogue(source_root, values):
    """Use exact owned task nodes/templates and compiled variables, no facts.

    Additional live checks are an explicit mandatory part of the result. The
    caller owns admission, loaded-input and sealed-release verification.
    """
    import yaml
    from ansible.parsing.dataloader import DataLoader
    from ansible.template import Templar
    root = Path(source_root).resolve()
    require(recipe_digest(root) == RECIPE_SHA256, 'INSTALLED_RECIPE_NOT_SUPPORTED')
    raw = yaml.safe_load((root / 'deploy/ansible/group_vars/all.yml').read_text())
    v = {**raw, **values, 'ansible_check_mode': False, 'playbook_dir': str(root / 'deploy/ansible')}
    require(v.get('relay_deployment_profile') == 'production'
            and isinstance(v.get('relay_general_runner_pool'), dict)
            and len(v.get('relay_additional_execution_slots', [])) == 31,
            'INSTALLED_PROFILE_NOT_SUPPORTED')
    require(not render('{{ relay_nginx_manage | bool }}', v)
            and not render('{{ relay_docker_nginx_manage | bool }}', v)
            and not v.get('relay_additional_runtime_users')
            and all(not slot.get('relay_additional_runtime_users') for slot in v['relay_additional_execution_slots']),
            'INSTALLED_PROFILE_NOT_SUPPORTED')
    # Variables remain lazy, as in Ansible: unused optional defaults must not
    # demand runtime register facts or unrelated profile inputs.
    require(not any(key in v for key in ['CODEX_ACCESS_TOKEN', 'GITHUB_TOKEN']), 'INSTALLED_SECRET_INPUT_REFUSED')
    entries, owners, probes, identities, entry_owners = {}, [], [], {}, {}
    templar = Templar(loader=DataLoader(), variables=v)
    active_owner = None

    def expand(value, variables):
        templar.available_variables = variables
        try:
            return templar.template(value, fail_on_undefined=True)
        except Exception:
            error = NotEligible('INSTALLED_RECIPE_INPUT_UNAVAILABLE')
            error.owner = active_owner  # Public source task identity, never an input value.
            raise error from None

    def add(entry, owner):
        path = entry['path']
        require(isinstance(path, str) and path.startswith('/') and '..' not in Path(path).parts)
        if path in entries:
            require(entries[path] == entry, 'INSTALLED_RECIPE_CONFLICT')
        entries[path] = entry
        owners.append(owner)
        entry_owners.setdefault(path, set()).add(owner)

    def selected(relative, context, names=None):
        nonlocal active_owner
        path = root / 'deploy/ansible' / relative
        role = next((part for part in path.parts if part.startswith('relay_')), '')
        variables = {**context, 'role_path': str(root / 'deploy/ansible/roles' / role)}
        rows = {task.get('name'): task for task in _tasks(yaml.safe_load(path.read_text()))}
        expected = OWNERS[relative] if names is None else names
        for name in expected:
            active_owner = relative + ':' + name
            require(name in rows, 'INSTALLED_OWNER_MISSING')
            task = rows[name]
            module = next((key for key in task if key in ['ansible.builtin.template', 'ansible.builtin.copy', 'ansible.builtin.file']), None)
            require(module is not None, 'INSTALLED_OWNER_UNSUPPORTED')
            items = expand(task.get('loop', [None]), variables)
            require(isinstance(items, list) and len(items) <= 2048)
            for item in items:
                local = {**variables, 'item': item}
                local.update(expand(task.get('vars', {}), local))
                args = expand(task[module], local)
                target = args.get('dest', args.get('path'))
                existing = entries.get(target, {})
                entry = {'path': target, 'owner': args.get('owner', existing.get('owner', 'root')),
                         'group': args.get('group', existing.get('group', 'root')), 'mode': args.get('mode')}
                if module == 'ansible.builtin.file':
                    kind = args.get('state', 'file')
                    require(kind in ['directory', 'absent', 'link', 'file'] and not args.get('recurse'),
                            'INSTALLED_OWNER_UNSUPPORTED')
                    entry['kind'] = kind
                    if kind == 'link': entry['target'] = args['src']
                else:
                    entry['kind'] = 'file'
                    if 'content' in args:
                        content = args['content'].encode()
                    else:
                        source = Path(args['src'])
                        if not source.is_absolute():
                            source = root / 'deploy/ansible/roles' / role / ('templates' if module.endswith('template') else 'files') / source
                        source = source.resolve()
                        require(source.is_relative_to(root) and not args.get('remote_src'), 'INSTALLED_SOURCE_NOT_OWNED')
                        text = source.read_text()
                        require("lookup('env'" not in text and 'lookup("env"' not in text,
                                'INSTALLED_SECRET_INPUT_REFUSED')
                        if module.endswith('template'):
                            # Match the template action itself. template() would
                            # auto-convert JSON text to native dict/list values.
                            templar.available_variables = local
                            try:
                                content = templar.do_template(text, preserve_trailing_newlines=True,
                                                              escape_backslashes=False).encode()
                            except Exception:
                                error = NotEligible('INSTALLED_RECIPE_INPUT_UNAVAILABLE')
                                error.owner = active_owner
                                raise error from None
                        else:
                            content = source.read_bytes()
                    entry['contentBase64'] = base64.b64encode(content).decode()
                    entry['sha256'] = hashlib.sha256(content).hexdigest()
                if entry['kind'] != 'absent':
                    require(re.fullmatch('[0-7]{3,4}', str(entry['mode'])) is not None,
                            'INSTALLED_METADATA_NOT_EXPLICIT')
                    entry['mode'] = int(str(entry['mode']), 8)
                if (relative == 'roles/relay_controller/tasks/runtime-entrypoints.yml'
                        and name == 'Install the root-owned explicit consumer snapshot'):
                    # Git-owned publication retains an existing serialization
                    # when the native validated consumer digest is unchanged.
                    # The complete desired JSON object remains source-derived.
                    entry['contentKind'] = 'consumer-json'
                add(entry, relative + ':' + name)

    # Explicit context expansion is owned by execution-slot.yml, never inferred
    # from currently present files or currently registered physical pool members.
    primary = {**v, 'relay_execution_slot': 'primary'}
    for user_key, group_key in [('relay_user', 'relay_group'), ('relay_reviewer_user', 'relay_reviewer_group'),
                                ('relay_runner_user', 'relay_runner_group')]:
        name, group = expand(v[user_key], v), expand(v[group_key], v)
        identities[name] = {'name': name, 'primaryGroup': group, 'shell': '/usr/sbin/nologin',
                            'requiredGroups': [], 'forbiddenGroups': [expand(v['relay_codex_work_group'], v)]
                            if user_key == 'relay_runner_user' else []}
    for relative in OWNERS:
        if relative not in ['tasks/execution-slot.yml', 'roles/relay_runner/tasks/general-runtime.yml',
                            'roles/relay_codex_runtime/tasks/repository-work-root.yml']:
            selected(relative, primary)
    general = yaml.safe_load((root / 'deploy/ansible/vars/general-runner.yml').read_text())
    for index, slot in enumerate([None, *v['relay_additional_execution_slots']]):
        context = {**primary, **general} if slot is None else {**v, **slot, 'relay_execution_slot_isolation': True,
                                                'relay_execution_slot_shared_prerequisites': True}
        if slot is not None:
            selected('roles/relay_codex_runtime/tasks/launcher.yml', context)
            selected('tasks/execution-slot.yml', context)
        selected('roles/relay_runner/tasks/general-runtime.yml', context)
        launcher_tasks = yaml.safe_load((root / 'deploy/ansible/roles/relay_codex_runtime/tasks/launcher.yml').read_text())
        work_owner = next(task for task in launcher_tasks
                          if task['name'] == 'Reconcile shared repository work ancestors before installing the launcher')
        if expand(context.get('relay_github_repositories', []), context):
            paths = expand(work_owner['vars']['relay_repository_work_paths'], context)
            require(isinstance(paths, list))
            selected('roles/relay_codex_runtime/tasks/repository-work-root.yml',
                     {**context, 'relay_repository_work_ancestors': {'results': [{'item': path} for path in paths]}})
        # The pool contract preserves existing account home/shell/primary group;
        # it requires shared work membership without removing foreign groups.
        for key in ['relay_codex_user', 'relay_runner_user']:
            name = expand(context[key], context)
            account = {'name': name, 'requiredGroups': [expand(context['relay_codex_work_group'], context)],
                       'forbiddenGroups': []}
            require(name not in identities or identities[name] == account, 'INSTALLED_IDENTITY_COLLISION')
            identities[name] = account
        argv = ['/usr/sbin/runuser', '-u', expand(context['relay_codex_user'], context), '--', '/usr/bin/bwrap',
                '--unshare-user', '--unshare-pid', '--unshare-ipc', '--unshare-uts', '--die-with-parent',
                '--new-session', '--ro-bind', '/usr', '/usr', '--ro-bind', '/bin', '/bin',
                '--ro-bind', '/lib', '/lib', '--ro-bind', '/lib64', '/lib64', '--proc', '/proc',
                '--dev', '/dev', '/usr/bin/true']
        probes.append({'label': 'runtime-' + str(index), 'argv': argv, 'stdout': ''})
    return {'schemaVersion': 1, 'recipeSha256': RECIPE_SHA256,
            'entries': sorted(entries.values(), key=lambda row: row['path']), 'probes': probes,
            'entryOwners': [sorted(entry_owners[path]) for path in sorted(entries)],
            'identities': list(identities.values()),
            'coverage': {'owners': sorted(set(owners)), 'routeCount': len(probes)},
            'requiredLiveChecks': ['identities', 'mutableState', 'packages', 'pool', 'ingress',
                                   'loadedProcesses', 'sealedRelease']}


def _audit_catalogue(catalogue, *, root=Path('/'), execute=None, users=None, groups=None, live_checks=None, diagnostic=None):
    """Read-only bounded audit. Exceptions expose fixed codes, never file bytes."""
    require(catalogue.get('schemaVersion') == 1 and catalogue.get('recipeSha256') == RECIPE_SHA256)
    require(catalogue.get('coverage', {}).get('routeCount') == 32 and len(catalogue.get('probes', [])) == 32)
    root = Path(root).resolve()
    require(live_checks is not None and set(live_checks) == set(catalogue['requiredLiveChecks'])
            and all(value is True for value in live_checks.values()), 'INSTALLED_LIVE_CHECK_UNPROVEN')
    run = execute or (lambda argv: subprocess.run(argv, capture_output=True, timeout=20))
    stamps = []
    managed_directories = {entry['path'] for entry in catalogue['entries'] if entry['kind'] == 'directory'}

    def identifier(name, group=False):
        source = groups if group else users
        if source is not None:
            require(name in source, 'INSTALLED_IDENTITY_UNPROVEN')
            item = source[name]
            return item['gid' if group else 'uid'] if isinstance(item, dict) else item
        try:
            return grp.getgrnam(name).gr_gid if group else pwd.getpwnam(name).pw_uid
        except KeyError:
            raise NotEligible('INSTALLED_IDENTITY_UNPROVEN') from None

    for index, account in enumerate(catalogue.get('identities', [])):
        diagnostic.update(owner='roles/relay_base/tasks/main.yml:Unix identity boundaries', field='identity', index=index)
        name = account['name']
        if users is not None:
            require(name in users and isinstance(users[name], dict), 'INSTALLED_IDENTITY_UNPROVEN')
            actual = users[name]
        else:
            try:
                row = pwd.getpwnam(name)
            except KeyError:
                raise NotEligible('INSTALLED_IDENTITY_UNPROVEN') from None
            actual = {'uid': row.pw_uid, 'gid': row.pw_gid, 'shell': row.pw_shell,
                      'groups': os.getgrouplist(name, row.pw_gid)}
        require(actual['uid'] > 0 and actual['gid'] > 0, 'INSTALLED_PRIVILEGED_IDENTITY')
        if 'primaryGroup' in account:
            require(actual['gid'] == identifier(account['primaryGroup'], True), 'INSTALLED_PRIMARY_GROUP_DRIFT')
        if 'shell' in account:
            require(actual['shell'] == account['shell'], 'INSTALLED_ACCOUNT_DRIFT')
        require(all(identifier(group, True) in actual['groups'] for group in account['requiredGroups'])
                and all(identifier(group, True) not in actual['groups'] for group in account['forbiddenGroups']),
                'INSTALLED_MEMBERSHIP_DRIFT')

    def stamp(info):
        return [info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
                info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns]

    for index, entry in enumerate(catalogue['entries']):
        diagnostic.update(owner=catalogue['entryOwners'][index], field='ancestors', index=index)
        relative = Path(entry['path'])
        require(relative.is_absolute() and '..' not in relative.parts)
        path = root / str(relative).lstrip('/')
        # All fixed path ancestors must remain real directories; no hidden
        # redirect can substitute a different protected namespace.
        for parent in path.parents:
            if parent == root: break
            parent_info = parent.lstat()
            require(parent.is_relative_to(root) and stat.S_ISDIR(parent_info.st_mode),
                    'INSTALLED_PATH_REDIRECTED')
            logical = '/' + str(parent.relative_to(root))
            require(logical in managed_directories or entry['kind'] == 'directory' and entry['owner'] != 'root' or
                    parent_info.st_uid == 0 and not parent_info.st_mode & 0o022,
                    'INSTALLED_PATH_PARENT_UNSAFE')
        if entry['kind'] == 'absent':
            diagnostic['field'] = 'absence'
            require(not os.path.lexists(path), 'INSTALLED_ABSENCE_DRIFT')
            stamps.append([path, None, index])
            continue
        diagnostic['field'] = 'type'
        meta = path.lstat()
        diagnostic['field'] = 'owner'
        require(meta.st_uid == identifier(entry['owner']), 'INSTALLED_METADATA_DRIFT')
        diagnostic['field'] = 'group'
        require(meta.st_gid == identifier(entry['group'], True), 'INSTALLED_METADATA_DRIFT')
        diagnostic['field'] = 'mode'
        require(stat.S_IMODE(meta.st_mode) == entry['mode'], 'INSTALLED_METADATA_DRIFT')
        diagnostic['field'] = 'type'
        kind = entry['kind']
        if kind == 'directory':
            require(stat.S_ISDIR(meta.st_mode), 'INSTALLED_TYPE_DRIFT')
        elif kind == 'link':
            diagnostic['field'] = 'link'
            require(stat.S_ISLNK(meta.st_mode) and os.readlink(path) == entry['target'], 'INSTALLED_LINK_DRIFT')
        else:
            require(stat.S_ISREG(meta.st_mode) and meta.st_nlink == 1, 'INSTALLED_TYPE_DRIFT')
            diagnostic['field'] = 'content'
            expected = base64.b64decode(entry['contentBase64'], validate=True)
            semantic_json = entry.get('contentKind') == 'consumer-json'
            require(meta.st_size <= 2 * 1024 * 1024 if semantic_json else meta.st_size == len(expected),
                    'INSTALLED_CONTENT_DRIFT')
            with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
                require(stamp(os.fstat(stream.fileno())) == stamp(meta))
                if semantic_json:
                    def unique(pairs):
                        result = {}
                        for key, value in pairs:
                            require(key not in result, 'INSTALLED_CONTENT_DRIFT')
                            result[key] = value
                        return result
                    actual = json.loads(stream.read(2 * 1024 * 1024 + 1).decode('utf-8'), object_pairs_hook=unique)
                    require(canonical(actual) == canonical(json.loads(expected.decode('utf-8'), object_pairs_hook=unique)),
                            'INSTALLED_CONTENT_DRIFT')
                else:
                    require(hashlib.file_digest(stream, 'sha256').hexdigest() == entry['sha256'], 'INSTALLED_CONTENT_DRIFT')
                require(stamp(os.fstat(stream.fileno())) == stamp(meta))
        stamps.append([path, stamp(meta), index])
    for index, probe in enumerate(catalogue['probes']):
        diagnostic.update(owner='tasks/execution-slot.yml:Private process namespace probe', field='nativeProbe', index=index)
        result = run(probe['argv'])
        output = result.stdout.decode() if isinstance(result.stdout, bytes) else result.stdout
        require(result.returncode == 0 and output == probe['stdout'], 'INSTALLED_NATIVE_PROBE_FAILED')
    for path, before, index in stamps:
        diagnostic.update(owner=catalogue['entryOwners'][index], field='movement', index=index)
        require((not os.path.lexists(path)) if before is None else stamp(path.lstat()) == before,
                'INSTALLED_STATE_MOVED')
    return {'eligible': True, 'catalogueSha256': hashlib.sha256(canonical(catalogue)).hexdigest(),
            'entryCount': len(stamps), 'routeCount': 32}


def audit_catalogue(catalogue, *, root=Path('/'), execute=None, users=None, groups=None, live_checks=None):
    """Return bounded evidence or one fixed eligibility failure; never inputs."""
    diagnostic = {'owner': None, 'field': 'catalogue', 'index': None}
    try:
        return _audit_catalogue(catalogue, root=root, execute=execute, users=users,
                                groups=groups, live_checks=live_checks, diagnostic=diagnostic)
    except NotEligible as error:
        error.owner, error.field, error.index = diagnostic['owner'], diagnostic['field'], diagnostic['index']
        raise
    except (OSError, KeyError, TypeError, ValueError, subprocess.SubprocessError):
        error = NotEligible('INSTALLED_STATE_UNAVAILABLE')
        error.owner, error.field, error.index = diagnostic['owner'], diagnostic['field'], diagnostic['index']
        raise error from None
