"""Read-only target prerequisites for the frozen intent-install candidate.

Only compiled nonsecret values enter this module. Credentials remain host-local;
the existing App/TLS qualifiers own material and remote-access validation.
"""
import argparse
import ast
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import socket
import stat
import subprocess
import sys


MAX_INPUT = 256 * 1024
MAX_OUTPUT = 64 * 1024


class HostPreflightError(ValueError):
    def __init__(self, code, resource, remedy='repair-prerequisite-on-existing-installation'):
        super().__init__(code)
        self.resource, self.remedy = resource, remedy


def require(value, code, resource, remedy='repair-prerequisite-on-existing-installation'):
    if not value:
        raise HostPreflightError(code, resource, remedy)


def resolved(values):
    """Namespace aliases from group_vars/all.yml, not desired installed data."""
    v = dict(values)
    install, config, state = (v['relay_' + key + '_root'] for key in ('install', 'config', 'state'))
    ns = v['relay_namespace']
    defaults = {
        'relay_release_root': install + '/releases', 'relay_log_root': '/var/log/' + ns,
        'relay_runtime_root': '/run/' + ns, 'relay_evidence_root': state + '/evidence',
        'relay_reviewer_group': v['relay_reviewer_user'], 'relay_runner_group': v['relay_runner_user'],
        'relay_codex_group': v['relay_codex_user'], 'relay_dispatch_user': v['relay_general_runner_user'],
        'relay_dispatch_group': v['relay_general_runner_user'],
        'relay_reviewer_service_name': 'reviewer-mcp.service',
        'relay_reviewer_recovery_service_name': 'reviewer-mcp-recovery.service',
        'relay_reviewer_recovery_timer_name': 'reviewer-mcp-recovery.timer',
        'relay_production_runner_service_name': 'relay-runner.service',
        'relay_runner_service_name': 'relay-runner.service',
        'relay_general_runner_service_name': 'relay-general-runner.service',
        'relay_controller_service_name': 'relay-controller.service',
        'relay_superseded_proxy_service_name': 'relay-openai-mtls-proxy.service',
        'relay_runner_root': install + '/runner', 'relay_runner_work_root': state + '/runner/work',
        'relay_runner_home': state + '/runner/home', 'relay_codex_home': state + '/codex-home',
        'relay_dispatch_state_root': state + '/dispatch', 'relay_dispatch_home': state + '/dispatch-home',
        'relay_dispatch_evidence_root': state + '/dispatch/evidence',
        'relay_codex_access_token_file': config + '/codex-credentials/access-token',
        'relay_reviewer_credential_key_file': config + '/reviewer-credentials/github-app-private-key.pem',
        'relay_writer_credential_key_file': config + '/writer-credentials/github-app-private-key.pem',
        'relay_tls_client_ca_file': config + '/certs/openai-client-ca.pem',
        'relay_runner_package_cache_root': '/var/cache/' + ns,
        'relay_codex_package_home': install + '/codex-runtime/package-home',
        'relay_codex_package_install_dir': install + '/codex-runtime/package-bin',
        'relay_codex_binary_path': install + '/codex-runtime/bin/codex',
    }
    for key, value in defaults.items():
        v.setdefault(key, value)
    return v


def runner_targets(v):
    install, state = v['relay_install_root'], v['relay_state_root']
    rows = [{'label': 'production', 'root': v['relay_runner_root'], 'work': v['relay_runner_work_root'],
             'home': v['relay_runner_home'], 'user': v['relay_runner_user'],
             'service': v['relay_production_runner_service_name']}]
    pool = v.get('relay_general_runner_pool')
    if pool:
        for member in pool['members']:
            rows.append({'label': 'member-' + member['id'], 'root': member['root'],
                         'work': member['state'] + '/work', 'home': member['state'] + '/home',
                         'user': pool['runnerUser'], 'service': member['service']})
    else:
        rows.append({'label': 'general', 'root': install + '/general-runner',
                     'work': state + '/general-runner/work', 'home': state + '/general-runner/home',
                     'user': v['relay_general_runner_user'], 'service': v['relay_general_runner_service_name']})
        for slot in v.get('relay_additional_execution_slots', []):
            rows.append({'label': 'slot-' + slot['relay_execution_slot'], 'root': slot['relay_runner_root'],
                         'work': slot['relay_runner_work_root'], 'home': slot['relay_runner_home'],
                         'user': slot['relay_runner_user'], 'service': slot['relay_runner_service_name']})
    return rows


def runtime_targets(v):
    rows = [{'label': 'primary', 'user': v['relay_codex_user'], 'group': v['relay_codex_group'],
             'home': v['relay_codex_home'], 'token': v['relay_codex_access_token_file'],
             'workGroup': v['relay_codex_work_group']}]
    for slot in v.get('relay_additional_execution_slots', []):
        rows.append({'label': 'slot-' + slot['relay_execution_slot'], 'user': slot['relay_codex_user'],
                     'group': slot['relay_codex_group'], 'home': slot['relay_codex_home'],
                     'token': slot['relay_codex_access_token_file'], 'workGroup': slot['relay_codex_work_group']})
    for user in v.get('relay_additional_runtime_users', []):
        rows.append({'label': 'repository-runtime-' + str(len(rows)), 'user': user, 'group': user,
                     'home': v['relay_state_root'] + '/runtime-users/' + user,
                     'token': v['relay_config_root'] + '/runtime-users/' + user + '/codex-credentials/access-token',
                     'workGroup': v['relay_codex_work_group']})
    return rows


class Probe:
    def __init__(self, root, owner_uid):
        self.root, self.owner_uid, self.observed = Path(root), owner_uid, []

    def physical(self, path):
        logical = Path(path)
        require(logical.is_absolute() and logical == Path(os.path.normpath(logical)), 'HOST_PATH_INVALID', 'destination')
        return self.root / str(logical).lstrip('/')

    def inspect(self, label, path, *, directory=False, protected=False, required=False, modes=None,
                uid=None, gid=None, limit=None, content=False, symlink=False, retained_runtime=False,
                volatile_consumer=False):
        target = self.physical(path)
        for parent in reversed(target.parents):
            if not parent.is_relative_to(self.root):
                continue
            if not os.path.lexists(parent):
                require(not required, 'HOST_REQUIRED_INPUT_MISSING', label, 'provide-configured-protected-input-and-repeat-install')
                self.observed.append([label, 'absent']); return None
            info = parent.lstat()
            require(stat.S_ISDIR(info.st_mode), 'HOST_DESTINATION_PARENT_UNSAFE', label)
            if protected:
                require(info.st_uid == self.owner_uid and not info.st_mode & 0o022,
                        'HOST_DESTINATION_PARENT_UNSAFE', label)
        if not os.path.lexists(target):
            require(not required, 'HOST_REQUIRED_INPUT_MISSING', label, 'provide-configured-protected-input-and-repeat-install')
            self.observed.append([label, 'absent']); return None
        info = target.lstat()
        if symlink and stat.S_ISLNK(info.st_mode):
            require(info.st_uid == self.owner_uid, 'HOST_DESTINATION_ALIAS_UNSAFE', label)
        else:
            require(stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
                    'HOST_DESTINATION_COLLISION', label)
            require(not protected or info.st_uid == self.owner_uid and (not info.st_mode & 0o022
                    or retained_runtime and stat.S_IMODE(info.st_mode) == 0o770),
                    'HOST_DESTINATION_METADATA_UNSAFE', label)
        require(uid is None or info.st_uid == uid, 'HOST_CREDENTIAL_OWNER_INVALID', label)
        require(gid is None or info.st_gid == gid, 'HOST_CREDENTIAL_GROUP_INVALID', label)
        require(modes is None or stat.S_IMODE(info.st_mode) in modes, 'HOST_CREDENTIAL_MODE_INVALID', label)
        require(limit is None or 0 < info.st_size <= limit, 'HOST_CREDENTIAL_SIZE_INVALID', label)
        row = ([label, info.st_mode, info.st_uid, info.st_gid] if volatile_consumer else
               [label, info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid])
        if not directory and not volatile_consumer:
            row += [info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns]
            if content:
                with target.open('rb') as source:
                    row.append(hashlib.file_digest(source, 'sha256').hexdigest())
        self.observed.append(row)
        return info

    def inspect_loaded_unit(self, label, path):
        """Read distro units through only Debian's fixed usrmerge alias.

        Managed destinations and credentials always use the strict inspector.
        The alias itself and the canonical protected unit both enter the same
        initial/final observation, so replacing either changes the receipt.
        """
        self.physical(path)  # Keep the ordinary normalized-path validation.
        logical = Path(path)
        alias = self.physical('/lib')
        if logical.is_relative_to('/lib/systemd/system') and alias.is_symlink():
            before = alias.lstat()
            target = os.readlink(alias)
            require(before.st_uid == self.owner_uid and target in ('usr/lib', '/usr/lib'),
                    'HOST_LOADED_UNIT_ALIAS_UNSAFE', label)
            fields = ['st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mtime_ns', 'st_ctime_ns']
            self.observed.append([label + '-distro-lib-alias', *[getattr(before, key) for key in fields], target])
            canonical = str(Path('/usr/lib') / logical.relative_to('/lib'))
            result = self.inspect(label, canonical, protected=True, required=True, content=True)
            after = alias.lstat()
            require(all(getattr(before, key) == getattr(after, key) for key in fields)
                    and os.readlink(alias) == target, 'HOST_LOADED_UNIT_ALIAS_CHANGED', label)
            return result
        return self.inspect(label, path, protected=True, required=True, content=True)

    def inspect_runner_listener(self, label, runner_root, runner_uid, source_root):
        """Read only the native updater's same-instance bin.<semver> alias."""
        logical = Path(runner_root)
        alias = self.physical(logical / 'bin')
        if not alias.is_symlink():
            return self.inspect(label, str(logical / 'bin/Runner.Listener'))
        before = alias.lstat()
        target = os.readlink(alias)
        require(runner_uid is not None and before.st_uid == runner_uid,
                'HOST_RUNNER_NATIVE_LAYOUT_UNSAFE', label)
        selected = Path(target)
        if selected.is_absolute():
            require(selected.parent == logical, 'HOST_RUNNER_NATIVE_LAYOUT_UNSAFE', label)
            selected = Path(selected.name)
        require(re.fullmatch(r'bin[.](?:0|[1-9][0-9]*)[.](?:0|[1-9][0-9]*)[.](?:0|[1-9][0-9]*)', str(selected)),
                'HOST_RUNNER_NATIVE_LAYOUT_UNSAFE', label)
        canonical = logical / selected
        # Reuse package qualification's real-directory/file boundary. Resolve the
        # logical alias here because Probe also supports rooted Linux fixtures.
        if not hasattr(self, '_runner_layout'):
            helper = str(Path(source_root) / 'deploy/ansible/roles/relay_runner/files/relay-intent-package.py')
            self.inspect('runner-layout-source', helper, protected=True, required=True, content=True)
            namespace = {'__name__': 'relay_runner_layout', '__file__': str(self.physical(helper))}
            exec(compile(self.physical(helper).read_bytes(), namespace['__file__'], 'exec'), namespace)
            self._runner_layout = namespace
        try:
            qualified = (self._runner_layout['real'](self.physical(canonical), True, owner=False)
                         and self._runner_layout['real'](self.physical(canonical / 'Runner.Listener'), False, owner=False))
        except (OSError, ValueError):
            qualified = False
        require(qualified, 'HOST_RUNNER_NATIVE_LAYOUT_UNSAFE', label)
        directory = self.inspect(label + '-native-bin', str(canonical), directory=True, required=True, uid=runner_uid)
        listener = self.inspect(label, str(canonical / 'Runner.Listener'), required=True, uid=runner_uid)
        require(not (directory.st_mode | listener.st_mode) & 0o022
                and directory.st_mode & stat.S_IXUSR and listener.st_mode & stat.S_IXUSR,
                'HOST_RUNNER_NATIVE_LAYOUT_UNSAFE', label)
        fields = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_mtime_ns', 'st_ctime_ns')
        after = alias.lstat()
        require(all(getattr(before, name) == getattr(after, name) for name in fields)
                and os.readlink(alias) == target, 'HOST_RUNNER_NATIVE_LAYOUT_CHANGED', label)
        self.observed.append([label + '-native-bin-alias', *[getattr(before, name) for name in fields], target])
        return listener


def destination_specs(v):
    """Existing role namespaces and fixed entrypoints; no recursive journal scan."""
    install, config, state = v['relay_install_root'], v['relay_config_root'], v['relay_state_root']
    rows = []
    def add(label, path, directory=False, protected=True, symlink=False):
        rows.append((label, path, directory, protected, symlink))
    for key in ('install', 'release', 'config', 'state', 'runtime'):
        add(key + '-root', v['relay_' + key + '_root'], True)
    add('log-root', v['relay_log_root'], True, False)
    for suffix in ('certs', 'reviewer-credentials', 'writer-credentials', 'codex-credentials'):
        add(suffix + '-root', config + '/' + suffix, True, suffix != 'codex-credentials')
    for suffix in ('reviewer', 'evidence', 'evidence/reviewer', 'production-apply', 'toolchains', 'cargo-home'):
        add('state-' + suffix.replace('/', '-'), state + '/' + suffix, True, suffix not in ('reviewer', 'evidence', 'evidence/reviewer'))
    add('package-cache', v['relay_runner_package_cache_root'], True)
    for suffix in ('bin', 'package-home', 'package-bin'):
        add('codex-package-' + suffix, install + '/codex-runtime/' + suffix, True)
    add('codex-diagnostic-module', install + '/codex-runtime/relay-codex-diagnostic.mjs')
    for suffix in ('relay.env', 'reviewer-mcp.json', 'controller.json', 'consumer.json', 'diagnostics.json',
                   'retention-policy.yaml', 'deployment-source.json'):
        add('config-' + suffix, config + '/' + suffix)
    for role in ('writer', 'reviewer'):
        add(role + '-environment', config + '/' + role + '-credentials/github-app.env')
    helpers = ('relay-reviewer-credential-check', 'relay-production-operation-state', 'relay-reviewer-start-guard',
        'relay-reviewer-activation-start', 'relay-runner-enable-start', 'relay-reviewer-operation-restart',
        'relay-app-qualification.py', 'relay-reviewer-app-qualification', 'relay-credential-provision',
        'relay-reviewer-recovery', 'relay-reviewer-stop-runner', 'relay-reviewer-readiness',
        'relay-diagnostics-control', 'relay-qualification-diagnostic-snapshot', 'relay-writer-credential-check',
        'relay-qualification-codex-probe', 'relay-writer-app-qualification', 'relay-writer-controller',
        'relay-manual-outcome', 'relay-manual-outcome-writer', 'relay-admission', 'relay-production-local-apply',
        'relay-runner-registration', 'relay-general-runner-registration', 'relay-runner-archive-check.py',
        'relay-general-runner-smoke', 'relay-managed-pool')
    for name in helpers:
        add('helper-' + name, install + '/' + name)
    for key in ('relay_writer_helper_path', 'relay_diagnostics_store_path', 'relay_codex_dispatch_path',
                'relay_codex_launcher_path', 'relay_diagnostics_config_path', 'relay_owner_lifecycle_helper_path'):
        if v.get(key): add('compiled-' + key.removeprefix('relay_'), v[key])
    add('codex-command', v['relay_codex_binary_path'], symlink=True)
    add('package-install-command', v['relay_codex_package_install_dir'] + '/codex', symlink=True)
    for suffix in ('relay-codex.mjs', 'relay-codex', 'relay-codex-isolation.mjs', 'relay-codex-cleanup.py'):
        add('primary-' + suffix, install + '/' + suffix)
    for key in ('relay_dispatch_state_root', 'relay_dispatch_home', 'relay_dispatch_evidence_root',
                'relay_dispatch_work_root', 'relay_writer_claim_root', 'relay_diagnostics_root'):
        if v.get(key): add('compiled-' + key.removeprefix('relay_'), v[key], True, key in ('relay_writer_claim_root', 'relay_diagnostics_root'))
    for runtime in runtime_targets(v):
        label = runtime['label']
        for suffix in ('', '/tmp', '/tmp/arg0'):
            add(label + '-runtime' + suffix.replace('/', '-'), runtime['home'] + suffix, True, False)
        add(label + '-token-parent', str(Path(runtime['token']).parent), True, False)
    for runner in runner_targets(v):
        label = runner['label']
        for key in ('root', 'work', 'home'):
            add(label + '-runner-' + key, runner[key], True, False)
        for name in ('config.sh', 'run.sh', 'bin/Runner.Listener', '.runner', '.credentials', '.credentials_rsaparams'):
            add(label + '-runner-' + name.replace('/', '-'), runner['root'] + '/' + name, False, False)
    for slot in v.get('relay_additional_execution_slots', []):
        label = 'slot-' + slot['relay_execution_slot']
        for key in ('relay_execution_slot_install_root', 'relay_dispatch_state_root', 'relay_dispatch_home',
                    'relay_dispatch_evidence_root', 'relay_dispatch_work_root', 'relay_diagnostics_root'):
            add(label + '-' + key.removeprefix('relay_'), slot[key], True, key == 'relay_execution_slot_install_root')
        for key in ('relay_codex_launcher_path', 'relay_codex_dispatch_path', 'relay_diagnostics_config_path', 'relay_diagnostics_store_path'):
            add(label + '-' + key.removeprefix('relay_'), slot[key])
        for name in ('relay-codex.mjs', 'relay-codex-isolation.mjs', 'relay-codex-cleanup.py', 'relay-runner-registration'):
            add(label + '-helper-' + name, slot['relay_execution_slot_install_root'] + '/' + name)
        for kind in ('codex', 'writer', 'diagnostics'):
            add(label + '-sudoers-' + kind, '/etc/sudoers.d/' + v['relay_namespace'] + '-' + label + '-' + kind)
    work_roots = [v.get('relay_dispatch_work_root')]
    work_roots += [slot.get('relay_dispatch_work_root') for slot in v.get('relay_additional_execution_slots', [])]
    for index, work in enumerate(path for path in work_roots if path):
        for repository_index, repository in enumerate(v.get('relay_github_repositories', [])):
            for depth, suffix in enumerate(('repositories', 'repositories/' + repository.split('/')[0], 'repositories/' + repository)):
                add(f'repository-work-{index}-{repository_index}-{depth}', work + '/' + suffix, True, False)
    for key, path in v.items():
        if key.endswith('_sudoers_file') and isinstance(path, str):
            add('sudoers-' + key.removeprefix('relay_'), path)
    ns = v['relay_namespace']
    for suffix in ('codex', 'writer', 'diagnostics', 'production-apply', 'owner-lifecycle',
                   'general-writer', 'general-diagnostics', 'general-codex'):
        add('sudoers-' + suffix, '/etc/sudoers.d/' + ns + '-' + suffix)
    for runner in runner_targets(v):
        unit = '/etc/systemd/system/' + runner['service']
        add(runner['label'] + '-unit', unit)
        add(runner['label'] + '-dropins', unit + '.d', True)
    add('production-apply-dropin', '/etc/systemd/system/' + v['relay_production_runner_service_name'] + '.d/production-local-apply.conf')
    add('manual-outcome-service-template', '/etc/systemd/system/' + ns + '-relay-manual-outcome@.service')
    return rows


def retained_runners(v, probe):
    """Old installed input supplies observation scope only, never desired state."""
    install = v['relay_install_root']
    current = probe.physical(install + '/current')
    if not os.path.lexists(current):
        return [], [], []
    link = current.lstat()
    require(stat.S_ISLNK(link.st_mode) and link.st_uid == probe.owner_uid,
            'HOST_PREVIOUS_RELEASE_BINDING_INVALID', 'previous-installation')
    selected = current.resolve(strict=True)
    revision = selected.name
    require(re.fullmatch('[a-f0-9]{40}', revision)
            and selected == probe.physical(v['relay_release_root'] + '/' + revision),
            'HOST_PREVIOUS_RELEASE_BINDING_INVALID', 'previous-installation')
    expected = v.get('relay_intent_preflight_installed_revision', v.get('relay_intent_expected_installed_revision'))
    if isinstance(expected, str) and re.fullmatch('[a-f0-9]{40}', expected):
        require(revision == expected, 'HOST_PREVIOUS_RELEASE_CHANGED', 'previous-installation')
    release = v['relay_release_root'] + '/' + revision
    try:
        probe.inspect('previous-manifest', release + '/artifact-manifest.json', protected=True, required=True, limit=128 * 1024)
        probe.inspect('previous-config', release + '/deployment-config.json', protected=True, required=True, limit=64 * 1024)
    except HostPreflightError:
        raise HostPreflightError('HOST_PREVIOUS_SERVICE_SCOPE_UNPROVEN', 'previous-installation',
                                'qualify-old-service-inventory-through-supported-owner-diagnostics') from None
    raw = probe.physical(release + '/deployment-config.json').read_bytes()
    manifest = json.loads(probe.physical(release + '/artifact-manifest.json').read_bytes())
    require(manifest.get('commit') == revision
            and manifest.get('deploymentConfigSha256') == hashlib.sha256(raw).hexdigest(),
            'HOST_PREVIOUS_CONFIG_BINDING_INVALID', 'previous-installation')
    previous = json.loads(raw)
    environment, consumer = previous['environment'], previous['consumer']
    require(environment['namespace'] == v['relay_namespace'], 'HOST_PREVIOUS_NAMESPACE_MISMATCH', 'previous-installation')
    namespaced = 'instance' in environment
    ns = environment['namespace']
    reviewer = ns + '-reviewer.service' if namespaced else 'reviewer-mcp.service'
    general = environment['generalRunner']
    state = v['relay_state_root']
    rows = [{'label': 'previous-production', 'user': environment['runner']['user'],
             'root': install + '/runner', 'home': state + '/runner/home', 'work': state + '/runner/work',
             'service': ns + '-runner.service' if namespaced else 'relay-runner.service'}]
    if 'generalRunnerPool' in consumer:
        for index, slot in enumerate(consumer['executionSlots'], 1):
            member = '/codex-relay-pools/' + general['name'] + '/runners/' + slot['id']
            rows.append({'label': 'previous-member-' + slot['id'], 'user': general['user'],
                         'root': '/opt' + member, 'home': '/var/lib' + member + '/home',
                         'work': '/var/lib' + member + '/work', 'service': general['name'] + f'-pool-{index}.service'})
    else:
        rows.append({'label': 'previous-general', 'user': general['user'], 'root': install + '/general-runner',
                     'home': state + '/general-runner/home', 'work': state + '/general-runner/work',
                     'service': ns + '-general-runner.service' if namespaced else 'relay-general-runner.service'})
        for slot in consumer.get('executionSlots', [])[1:]:
            prefix = '/slots/' + slot['id']
            rows.append({'label': 'previous-slot-' + slot['id'], 'user': slot['runnerUser'],
                         'root': install + prefix + '/runner', 'home': state + prefix + '/runner/home',
                         'work': state + prefix + '/runner/work', 'service': ns + '-slot-' + slot['id'] + '-runner.service'})
    identities = {environment['serviceUser'], environment['reviewerUser'], environment['runner']['user'],
                  general['user'], consumer['runtimeUser'], *consumer.get('repositoryRuntimeUsers', {}).values()}
    identities.update(slot[key] for slot in consumer.get('executionSlots', []) for key in ('runnerUser', 'runtimeUser'))
    return rows, [('previous-reviewer', reviewer),
                 ('previous-recovery', ns + '-reviewer-recovery.service' if namespaced else 'reviewer-mcp-recovery.service'),
                 ('previous-recovery-timer', ns + '-reviewer-recovery.timer' if namespaced else 'reviewer-mcp-recovery.timer')], sorted(identities)


def _execute(argv, *, env=None, input=None):
    result = subprocess.run(argv, stdin=subprocess.DEVNULL if input is None else None, input=input,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=env or {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'OPENSSL_CONF': '/dev/null'},
        timeout=180, check=False)
    require(len(result.stdout) <= MAX_OUTPUT and len(result.stderr or b'') <= MAX_OUTPUT,
            'HOST_PROBE_OUTPUT_INVALID', 'host-probe')
    return result


def qualify_app(source_root, settings, *, execute=_execute):
    script = Path(source_root) / 'deploy/ansible/roles/relay_runtime/files/relay-app-qualification.py'
    environment = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'OPENSSL_CONF': '/dev/null',
        'RELAY_APP_ROLE': settings['role'], 'GITHUB_APP_ID': str(settings['appId']),
        'GITHUB_APP_INSTALLATION_ID': str(settings['installationId']), 'RELAY_EXPECTED_APP_SLUG': settings['slug'],
        'RELAY_EXPECTED_ACTOR': settings['actor'], 'RELAY_EXPECTED_REPOSITORY': settings['repository'],
        'GITHUB_APP_PRIVATE_KEY_FILE': settings['key'], 'RELAY_EXPECTED_KEY_MODE': settings['mode'],
        'RELAY_EXPECTED_WRITE_PERMISSION_NAMES': ('contents,issues,pull_requests,workflows' if settings['role'] == 'writer'
                                                else 'pull_requests,checks,issues'),
        'RELAY_TOKEN_PERMISSIONS': 'metadata:read'}
    if settings.get('pool'):
        environment['RELAY_MANAGED_POOL_BINDING'] = json.dumps(settings['pool'], separators=(',', ':'))
    result = execute(['/usr/bin/python3', '-I', '-B', str(script)], env=environment)
    code = re.fullmatch(rb'APP_QUALIFICATION_FAIL code=([A-Z][A-Z0-9_]{0,79})\n?', result.stdout)
    require(result.returncode == 0 and result.stdout.startswith(b'APP_QUALIFICATION_PASS '),
            'HOST_APP_' + code[1].decode() if code else 'HOST_APP_QUALIFICATION_FAILED',
            settings['role'] + '-app', 'repair-selected-app-installation-or-repository-grant-and-repeat-install')


def qualify_tls(source_root, certificate, private_key, hostname, legacy, *, execute=_execute):
    script = Path(source_root) / 'deploy/ansible/tools/tls-source-validate.py'
    argv = ['/usr/bin/python3', '-I', '-B', str(script), '--certificate', str(certificate), '--private-key', str(private_key),
            '--hostname', hostname]
    if legacy: argv.append('--allow-letsencrypt-lineage')
    result = execute(argv)
    require(result.returncode == 0, 'HOST_TLS_MATERIAL_INVALID', 'tls-material',
            'repair-configured-certificate-key-chain-or-validity-and-repeat-install')


def qualify_ca(source_root, ca_path, *, execute=_execute):
    source = Path(source_root) / 'deploy/ansible/tools/tls-webroot-bootstrap.py'
    assignments = ast.parse(source.read_text()).body
    constants = [ast.literal_eval(node.value) for node in assignments if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id == 'OPENAI_CAS' for target in node.targets)]
    require(len(constants) == 1, 'HOST_CLIENT_CA_CONTRACT_INVALID', 'client-ca')
    expected = {item[2] for item in constants[0]}
    bundle = Path(ca_path).read_bytes()
    certificates = re.findall(rb'-----BEGIN CERTIFICATE-----\s.*?-----END CERTIFICATE-----', bundle, re.DOTALL)
    residue = re.sub(rb'-----BEGIN CERTIFICATE-----\s.*?-----END CERTIFICATE-----', b'', bundle, flags=re.DOTALL)
    require(len(certificates) == len(expected) and not residue.strip(), 'HOST_CLIENT_CA_INVALID', 'client-ca')
    actual = set()
    for certificate in certificates:
        result = execute(['/usr/bin/openssl', 'x509', '-noout', '-checkend', '0', '-fingerprint', '-sha256'], input=certificate)
        match = re.search(rb'(?:SHA256|sha256) Fingerprint=([A-Fa-f0-9:]+)', result.stdout)
        require(result.returncode == 0 and match is not None, 'HOST_CLIENT_CA_INVALID', 'client-ca')
        actual.add(match[1].decode().replace(':', '').upper())
    require(actual == expected, 'HOST_CLIENT_CA_IDENTITY_MISMATCH', 'client-ca')


def qualify_acme(source_root, settings, *, execute=_execute):
    # Reuse only existing observation functions. Do not invoke run(), challenge
    # publication, Certbot installation/issuance, nginx reload or any writer.
    program = '''import importlib.util,json,sys
sys.dont_write_bytecode=True
from pathlib import Path
directory=Path(sys.argv[1])/"deploy/ansible/tools"
sys.path.insert(0,str(directory))
spec=importlib.util.spec_from_file_location("tls_bootstrap",directory/"tls-webroot-bootstrap.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
c=json.loads(sys.stdin.buffer.read(16385))
try:
 global_config=m.certbot_configuration_identity()
 container=m.check_container(c)
 m.check_conflicts(c,Path(c["conf_root"])/(c["namespace"]+"-acme.conf"),container)
 print(json.dumps({"container":container,"certbotGlobalConfig":global_config},sort_keys=True))
except Exception as e:
 import re
 code=str(e)
 print(code if re.fullmatch("[A-Z][A-Z0-9_]{0,79}",code) else "TLS_ACME_PREREQUISITE_UNAVAILABLE")
 sys.exit(1)
'''
    result = execute(['/usr/bin/python3', '-I', '-B', '-c', program, str(source_root)],
                     input=json.dumps(settings, separators=(',', ':')).encode())
    code = re.fullmatch(rb'([A-Z][A-Z0-9_]{0,79})\n?', result.stdout)
    require(result.returncode == 0, 'HOST_' + code[1].decode() if code else 'HOST_TLS_ACME_PREREQUISITE_UNAVAILABLE',
            'tls-acme', 'repair-known-acme-dns-container-mount-routing-or-certbot-prerequisite-and-repeat-install')
    value = json.loads(result.stdout)
    require(isinstance(value, dict) and set(value) == {'container', 'certbotGlobalConfig'},
            'HOST_TLS_ACME_PROOF_INVALID', 'tls-acme')
    return value


def qualify_pool(source_root, contract, *, execute=_execute):
    source = Path(source_root)
    template = source / 'deploy/ansible/roles/relay_runner/templates/relay-managed-pool.service.j2'
    payload = {'contract': contract, 'unitTemplate': template.read_text()}
    result = execute(['/usr/bin/python3', '-I', '-B', str(source / 'deploy/managed_pool.py'), '--preflight'],
                     input=json.dumps(payload, separators=(',', ':')).encode())
    code = re.fullmatch(rb'(MANAGED_POOL_[A-Z0-9_]{1,80})\n?', result.stderr or b'')
    require(result.returncode == 0, 'HOST_' + code[1].decode() if code else 'HOST_POOL_INSTALLATION_UNPROVEN',
            'managed-pool-installation', 'repair-owning-pool-installation-prerequisite-on-existing-version-before-repeat-install')
    value = json.loads(result.stdout)
    require(isinstance(value, dict) and set(value) == {'status', 'createParents', 'members'} and value['status'] == 'PASS'
            and isinstance(value['members'], dict), 'HOST_POOL_INSTALLATION_PROOF_INVALID', 'managed-pool-installation')
    return value


def inspect_inputs(values, source_root, *, root=Path('/'), owner_uid=0, users=None, groups=None,
                   execute=_execute, app_qualifier=qualify_app, tls_qualifier=qualify_tls,
                   ca_qualifier=qualify_ca, acme_qualifier=qualify_acme, pool_qualifier=qualify_pool,
                   resolve_dns=socket.getaddrinfo):
    v = resolved(values); probe = Probe(root, owner_uid)
    user_cache, group_cache = {}, {}
    def user(name):
        if name not in user_cache:
            if users is not None: row = users.get(name)
            else:
                try:
                    item = pwd.getpwnam(name)
                    row = {'uid': item.pw_uid, 'gid': item.pw_gid, 'home': item.pw_dir, 'shell': item.pw_shell,
                           'groups': sorted(os.getgrouplist(name, item.pw_gid))}
                except KeyError: row = None
            require(row is None or row['uid'] > 0, 'HOST_PRIVILEGED_IDENTITY_COLLISION', 'unix-identity')
            user_cache[name] = row
        return user_cache[name]
    def group(name):
        if name not in group_cache:
            if groups is not None: row = groups.get(name)
            else:
                try: row = grp.getgrnam(name).gr_gid
                except KeyError: row = None
            require(row is None or row > 0, 'HOST_PRIVILEGED_IDENTITY_COLLISION', 'unix-group')
            group_cache[name] = row
        return group_cache[name]
    runtimes, runners = runtime_targets(v), runner_targets(v)
    old_runners, old_services, old_identities = retained_runners(v, probe)
    for name in old_identities:
        user(name)
    identity_specs = [(v['relay_user'], v['relay_group'], None, False),
                      (v['relay_reviewer_user'], v['relay_reviewer_group'], None, False)]
    identity_specs += [(r['user'], r['user'], None if r['label'] == 'production' else r['home'],
                       r['label'] != 'production' and bool(v.get('relay_general_runner_pool')))
                      for r in runners]
    identity_specs += [(r['user'], r['group'], r['home'], bool(v.get('relay_general_runner_pool'))
                      or r['label'].startswith('repository-runtime-')) for r in runtimes]
    plans = {'createUsers': 0, 'primaryGroupChanges': 0, 'homeShellChanges': 0, 'workMembershipChanges': 0}
    created = set()
    for name, primary, home, preserve in dict.fromkeys(identity_specs):
        account, primary_gid = user(name), group(primary)
        if account is None:
            plans['createUsers'] += int(name not in created); created.add(name); continue
        if not preserve:
            plans['primaryGroupChanges'] += int(primary_gid is None or account['gid'] != primary_gid)
            plans['homeShellChanges'] += int(account['shell'] != '/usr/sbin/nologin' or home is not None and account['home'] != home)
    for runtime in runtimes:
        work_gid = group(runtime['workGroup']); account = user(runtime['user'])
        plans['workMembershipChanges'] += int(account is not None and (work_gid is None or work_gid not in account['groups']))
    listeners = {runner['root'] + '/bin/Runner.Listener': runner for runner in runners}
    for label, path, directory, protected, symlink in destination_specs(v):
        if path in listeners:
            runner = listeners[path]
            account = user(runner['user'])
            info = probe.inspect_runner_listener(label, runner['root'], account['uid'] if account else None, source_root)
        else:
            info = probe.inspect(label, path, directory=directory, protected=protected, symlink=symlink,
                                 retained_runtime=label == 'runtime-root',
                                 volatile_consumer=path == v['relay_config_root'] + '/consumer.json')
        if label == 'runtime-root' and info is not None and info.st_mode & 0o022:
            require(info.st_gid == group(v['relay_reviewer_group']), 'HOST_DESTINATION_METADATA_UNSAFE', label)
    for runner in runners:
        present = [os.path.lexists(probe.physical(runner['root'] + '/' + name)) for name in ('.runner', '.credentials')]
        require(present[0] == present[1], 'HOST_RUNNER_REGISTRATION_AMBIGUOUS', runner['label'],
                'reconcile-or-diagnose-original-runner-registration-before-repeat-install')
    for runner in old_runners:
        user(runner['user'])
        for key in ('root', 'work', 'home'):
            probe.inspect(runner['label'] + '-' + key, runner[key], directory=True)
    if v.get('relay_general_runner_pool'):
        for relative in ('deploy/managed_pool.py', 'deploy/ansible/roles/relay_runner/templates/relay-managed-pool.service.j2'):
            probe.inspect('pool-installation-qualifier-source', str(Path(source_root) / relative), protected=True, required=True)
        plan = pool_qualifier(probe.physical(source_root), v['relay_general_runner_pool'], execute=execute)
        probe.observed.append(['managed-pool-installation-plan', plan])
    uids = [row['uid'] for row in user_cache.values() if row is not None]
    require(len(uids) == len(set(uids)), 'HOST_IDENTITY_ALIAS_COLLISION', 'unix-identity')
    # The candidate installs the Reviewer App key as root:<reviewer> 0640.
    # Preserve unrelated account settings, but do not knowingly grant a runner
    # or runtime direct access to that specific protected credential group.
    reviewer_gid = group(v['relay_reviewer_group'])
    for name in {r['user'] for r in runners + runtimes}:
        account = user(name)
        membership = set(account['groups']) if account else set()
        membership.add(group(name))
        require(reviewer_gid is None or reviewer_gid not in membership,
                'HOST_PROTECTED_CREDENTIAL_GROUP_COLLISION', 'reviewer-credential-group',
                'repair-concrete-reviewer-key-access-boundary-before-repeat-install')
    services = [('reviewer', v['relay_reviewer_service_name']), ('recovery', v['relay_reviewer_recovery_service_name']),
                ('recovery-timer', v['relay_reviewer_recovery_timer_name']), ('controller', v['relay_controller_service_name']),
                ('manual-outcome', v['relay_namespace'] + '-relay-manual-outcome.socket')]
    services += [(r['label'], r['service']) for r in runners]
    services += old_services + [(r['label'], r['service']) for r in old_runners]
    services += [('ingress', v['relay_docker_nginx_service_name'])]
    if v['relay_reviewer_bind_mode'] == 'nexus_gateway': services.append(('docker', 'docker.service'))
    observed_services = []
    for label, unit in dict.fromkeys(services):
        require(re.fullmatch(r'[A-Za-z0-9_.@-]{1,160}', unit), 'HOST_SERVICE_INPUT_INVALID', label)
        result = execute(['systemctl', 'show', '--no-pager', '--property=LoadState,ActiveState,SubState,UnitFileState,MainPID,User,Group,FragmentPath,DropInPaths', unit])
        require(result.returncode == 0, 'HOST_SERVICE_OBSERVATION_UNAVAILABLE', label)
        state = dict(line.split('=', 1) for line in result.stdout.decode().splitlines() if '=' in line)
        require(state.get('LoadState') in ('loaded', 'not-found') and state.get('ActiveState') in ('active', 'inactive', 'failed'),
                'HOST_SERVICE_STATE_AMBIGUOUS', label)
        require(state.get('UnitFileState', '') in ('', 'enabled', 'enabled-runtime', 'disabled', 'static', 'indirect', 'generated'),
                'HOST_SERVICE_ENABLEMENT_UNSAFE', label)
        pid = state.get('MainPID', '0')
        require(re.fullmatch('[0-9]+', pid), 'HOST_SERVICE_PROCESS_UNPROVEN', label)
        start = None
        if int(pid):
            try:
                process = probe.physical('/proc/' + pid + '/stat').read_text()
                start = process[process.rfind(')') + 2:].split()[19]
            except (OSError, IndexError):
                raise HostPreflightError('HOST_SERVICE_PROCESS_UNPROVEN', label) from None
        if label in ('ingress', 'docker'):
            require(state['LoadState'] == 'loaded' and state['ActiveState'] == 'active',
                    'HOST_EXTERNAL_SERVICE_UNAVAILABLE', label, 'restore-required-existing-ingress-or-docker-service-before-repeat-install')
        elif state['ActiveState'] == 'active' and unit.endswith('.service'):
            require(int(pid) > 0, 'HOST_SERVICE_PROCESS_UNPROVEN', label)
        for path in [state.get('FragmentPath', ''), *state.get('DropInPaths', '').split()]:
            if path: probe.inspect_loaded_unit(label + '-loaded-unit', path)
        probe.inspect(label + '-unit-destination', '/etc/systemd/system/' + unit, protected=True)
        observed_services.append([label, state, start])
        runner = next((r for r in runners + old_runners if r['label'] == label), None)
        desired_runner = next((r for r in runners if runner and r['user'] == runner['user']), None)
        if desired_runner and desired_runner['label'] != 'production' and state['ActiveState'] == 'active':
            runner = desired_runner; account = user(runner['user'])
            work_groups = ({r['workGroup'] for r in runtimes} if v.get('relay_general_runner_pool') else
                           {next((r['workGroup'] for r in runtimes if r['label'] == runner['label']), runtimes[0]['workGroup'])})
            require(account is not None, 'HOST_ACTIVE_TRANSPORT_IDENTITY_CHANGED', label)
            preserve = bool(v.get('relay_general_runner_pool'))
            changed = (not preserve and (account['gid'] != group(runner['user'])
                       or account['home'] != runner['home'] or account['shell'] != '/usr/sbin/nologin'))
            changed = changed or any(group(name) is None or group(name) not in account['groups'] for name in work_groups)
            if not preserve:
                changed = changed or set(account['groups']) != {group(runner['user']), *(group(name) for name in work_groups)}
            require(not changed, 'HOST_ACTIVE_TRANSPORT_IDENTITY_CHANGED', label,
                    'qualify-supported-general-transport-transition-before-repeat-install')
    credentials = []
    publication = v.get('relay_reviewer_relay_enabled', True)
    for role, required in [('reviewer', True), ('writer', publication)]:
        source = v.get('relay_' + role + '_credential_source_file')
        path = source or v['relay_' + role + '_credential_key_file']
        label = role + '-key'
        info = probe.inspect(label, path, protected=True, required=required or bool(source), uid=owner_uid,
                             modes={0o600, 0o640} if role == 'reviewer' else {0o600}, limit=65536)
        if info is None or not required and not source: continue
        material = execute(['/usr/bin/openssl', 'pkey', '-in', str(probe.physical(path)), '-passin', 'pass:', '-check', '-noout'])
        require(material.returncode == 0, 'HOST_APP_PRIVATE_KEY_INVALID', label, 'provide-valid-selected-app-key-and-repeat-install')
        script = str(Path(source_root) / 'deploy/ansible/roles/relay_runtime/files/relay-app-qualification.py')
        probe.inspect('app-qualifier-source', script, protected=True, required=True)
        repositories = v['relay_reviewer_repositories'] if role == 'reviewer' else v.get('relay_writer_repositories', [v['relay_github_repository']])
        for repository in repositories:
            settings = {'role': role, 'repository': repository, 'key': str(probe.physical(path)),
                'mode': format(stat.S_IMODE(info.st_mode), '04o'), 'appId': v['relay_' + role + '_app_id'],
                'installationId': v['relay_' + role + '_app_installation_id'], 'slug': v['relay_' + role + '_app_slug'],
                'actor': v['relay_' + role + '_expected_actor']}
            if role == 'writer' and v.get('relay_general_runner_pool'):
                pool = v['relay_general_runner_pool']
                settings['pool'] = {key: pool[key] for key in ('appId', 'installationId', 'organization', 'repositories')}
            app_qualifier(probe.physical(source_root), settings, execute=execute)
            credentials.append(role)
    token_source = v.get('relay_codex_credential_source_file')
    primary_token = token_source or runtimes[0]['token']
    token_user = user(runtimes[0]['user'])
    probe.inspect('primary-runtime-token', primary_token, required=bool(token_source) or v.get('relay_codex_token_required', True),
        protected=bool(token_source), uid=owner_uid if token_source else token_user['uid'] if token_user else -1,
        gid=0 if token_source else group(runtimes[0]['group']) if token_user else -1, modes={0o600}, limit=16384)
    # Additional slot/repository credentials are populated from the established
    # primary credential by their existing owning roles, not independently minted.
    for runtime in runtimes[1:]:
        account = user(runtime['user'])
        probe.inspect(runtime['label'] + '-token', runtime['token'], uid=account['uid'] if account else None,
                      modes={0o600}, limit=16384)
    certificate, key = v['relay_nginx_server_certificate_file'], v['relay_nginx_server_private_key_file']
    pending = []
    pair = [os.path.lexists(probe.physical(path)) for path in (certificate, key)]
    require(pair[0] == pair[1], 'HOST_TLS_MATERIAL_PARTIAL', 'tls-material',
            'diagnose-retained-tls-publication-through-existing-supported-recovery')
    certificate_pending = not all(pair)
    if certificate_pending:
        fresh = v.get('relay_intent_preflight_installed_revision', v.get('relay_intent_expected_installed_revision')) == 'none'
        require(fresh and v.get('relay_tls_acme_configured'),
                'HOST_TLS_ISSUANCE_STAGE_REQUIRED' if v.get('relay_tls_acme_configured') else 'HOST_TLS_MATERIAL_MISSING',
                'tls-material', 'prepare-selected-certificate-through-supported-automatic-stage-before-cutover')
        # A fresh inactive bootstrap has no old availability to disrupt. Preserve
        # its existing product-owned issuance schedule; verify its known external
        # inputs now, without claiming that a certificate has already been issued.
        addresses = v.get('relay_tls_public_addresses', [])
        require(addresses and v.get('relay_tls_acme_method') == 'webroot' and v.get('relay_tls_acme_webroot')
                and v.get('relay_tls_acme_email'), 'HOST_TLS_ACME_PREREQUISITE_MISSING', 'tls-material')
        try:
            actual = {entry[4][0] for entry in resolve_dns(v['relay_nginx_server_name'], 80, socket.AF_UNSPEC, socket.SOCK_STREAM)}
        except OSError:
            raise HostPreflightError('HOST_TLS_PUBLIC_DNS_UNAVAILABLE', 'tls-material') from None
        require(actual == set(addresses), 'HOST_TLS_PUBLIC_DNS_MISMATCH', 'tls-material')
        for relative in ('deploy/ansible/tools/tls-webroot-bootstrap.py', 'deploy/ansible/tools/bootstrap_guard.py'):
            probe.inspect('tls-bootstrap-source', str(Path(source_root) / relative), protected=True, required=True)
        probe.inspect('tls-webroot', v['relay_tls_acme_webroot'], directory=True, protected=True)
        acme = acme_qualifier(probe.physical(source_root), {
            'namespace': v['relay_namespace'], 'hostname': v['relay_nginx_server_name'],
            'container': v['relay_docker_nginx_container_name'],
            'image': v.get('relay_docker_nginx_image', 'nginx:latest'),
            'conf_root': v.get('relay_docker_nginx_conf_root', v['relay_nexus_ownership_root'] + '/nginx-conf'),
            'webroot': v['relay_tls_acme_webroot']}, execute=execute)
        probe.observed.append(['acme-external-inputs', acme])
        pending.append('tls-acme-issuance')
    ca = probe.inspect('client-ca', v['relay_tls_client_ca_file'], protected=True, modes={0o600, 0o640, 0o644}, limit=256 * 1024)
    if ca is None:
        require(v.get('relay_intent_preflight_installed_revision', v.get('relay_intent_expected_installed_revision')) == 'none',
                'HOST_CLIENT_CA_MISSING', 'client-ca',
                'prepare-qualified-client-ca-through-supported-tls-preparation-before-repeat-install')
        pending.append('client-ca-preparation')
    else:
        probe.inspect('client-ca-qualifier-source', str(Path(source_root) / 'deploy/ansible/tools/tls-webroot-bootstrap.py'),
                      protected=True, required=True)
        ca_qualifier(probe.physical(source_root), probe.physical(v['relay_tls_client_ca_file']), execute=execute)
    for relative in ('deploy/ansible/tools/tls-source-validate.py',):
        probe.inspect('tls-qualifier-source', str(Path(source_root) / relative), protected=True, required=True)
    if not certificate_pending:
        tls_qualifier(probe.physical(source_root), probe.physical(certificate), probe.physical(key),
                      v['relay_nginx_server_name'], v.get('relay_tls_allow_legacy_lineage', False), execute=execute)
    # Content remains private. Metadata binds rotations and replacements between
    # observations without treating credential bytes as a public receipt.
    for label, path in [('tls-certificate', certificate), ('tls-private-key', key)]:
        if certificate_pending:
            probe.inspect(label, path, protected=True)
            continue
        target = probe.physical(path)
        if target.is_symlink():
            info = target.lstat(); probe.observed.append([label, info.st_ino, info.st_uid, os.readlink(target)])
            info = target.resolve(strict=True).stat(); probe.observed.append([label + '-resolved', info.st_ino, info.st_mtime_ns, info.st_ctime_ns])
        else: probe.inspect(label, path, protected=True, required=True)
    snapshot = {'metadata': sorted(probe.observed, key=lambda row: row[0]), 'services': observed_services,
                'users': user_cache, 'groups': group_cache}
    observed = hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'version': 1, 'status': 'PASS', 'observedSha256': observed, 'pendingProductMaterial': pending,
            'checks': {'destinations': len(probe.observed), 'identities': len(user_cache),
                       'appRepositories': len(credentials), 'services': len(observed_services)}, 'identityPlan': plans}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', action='store_true', required=True)
    parser.parse_args()
    try:
        require(os.geteuid() == 0 and sys.platform == 'linux', 'HOST_ROOT_LINUX_REQUIRED', 'execution')
        raw = sys.stdin.buffer.read(MAX_INPUT + 1)
        require(len(raw) <= MAX_INPUT, 'HOST_INPUT_TOO_LARGE', 'input')
        payload = json.loads(raw)
        require(isinstance(payload, dict) and set(payload) == {'values', 'sourceRoot'}
                and isinstance(payload['values'], dict), 'HOST_INPUT_INVALID', 'input')
        result = inspect_inputs(payload['values'], payload['sourceRoot'])
        output = json.dumps(result, sort_keys=True)
        require(len(output) <= MAX_OUTPUT, 'HOST_OUTPUT_TOO_LARGE', 'output')
        print(output)
    except HostPreflightError as error:
        print(json.dumps({'version': 1, 'status': 'FAIL', 'error_code': str(error),
                          'resource': error.resource, 'next_action': error.remedy}, sort_keys=True))
        return 1
    except Exception:
        print(json.dumps({'version': 1, 'status': 'FAIL', 'error_code': 'HOST_PREFLIGHT_UNAVAILABLE',
                          'resource': 'host-prerequisites', 'next_action': 'inspect-protected-prerequisite-through-existing-owner-diagnostics'}))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
