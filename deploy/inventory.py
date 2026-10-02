"""Read-only, bounded target inventory for the public bootstrap interface.

This probe uses only configured paths and product-owned layout. It does not
execute installed code, inspect secret contents, query GitHub with credentials,
create a lock or grant permission to change anything. The same accepted source
can inspect a fresh target or a pre-current installation.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import pwd
import re
import shlex
import stat
import subprocess
import sys


LIMIT = 65536


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('duplicate-key')
        value[key] = item
    return value


def _json(raw):
    if len(raw) > LIMIT:
        raise ValueError('oversize')
    return json.loads(raw, object_pairs_hook=_object)


def _stamp(info):
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _consumer(value):
    value = json.loads(json.dumps(value))
    value['defaultProfile'].setdefault('effort', 'ultra')
    return value


def _intent(value):
    value = json.loads(json.dumps(value))
    value['source'].pop('revision', None)
    value['consumer'] = _consumer(value['consumer'])
    return value


class Probe:
    """Directory-descriptor reads reject links, hardlinks and unsafe ancestors."""

    def __init__(self, root, owner_uid, boundary, user_ids):
        self.root = Path(root)
        self.boundary = Path(boundary) if boundary is not None else self.root
        self.owner_uid = owner_uid
        self.user_ids = user_ids

    def path(self, value):
        if (not isinstance(value, str) or not re.fullmatch(r'/[A-Za-z0-9_./-]+', value)
                or any(part in ('', '.', '..') for part in value.split('/')[1:])):
            raise ValueError('path')
        result = self.root / value.lstrip('/')
        if not result.is_relative_to(self.boundary):
            raise ValueError('boundary')
        return result

    def identity(self, name):
        if self.user_ids is not None:
            return self.user_ids[name]
        entry = pwd.getpwnam(name)
        return entry.pw_uid, entry.pw_gid

    @contextmanager
    def parent(self, value, *, leaf_parent_uid=None):
        path = self.path(value)
        relative = path.relative_to(self.boundary)
        descriptor = os.open(self.boundary, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            info = os.fstat(descriptor)
            if info.st_uid != self.owner_uid or info.st_mode & 0o022:
                raise ValueError('unsafe-boundary')
            parts = relative.parts[:-1]
            for index, part in enumerate(parts):
                following = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                    dir_fd=descriptor)
                os.close(descriptor)
                descriptor = following
                info = os.fstat(descriptor)
                owner = (leaf_parent_uid if leaf_parent_uid is not None and index == len(parts) - 1
                         else self.owner_uid)
                if info.st_uid != owner or info.st_mode & 0o022:
                    raise ValueError('unsafe-parent')
            yield descriptor, relative.name
        finally:
            os.close(descriptor)

    def metadata(self, value, *, uid=None, gid=None, modes=None, leaf_parent_uid=None):
        with self.parent(value, leaf_parent_uid=leaf_parent_uid) as (parent, name):
            info = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or info.st_uid != (self.owner_uid if uid is None else uid)
                    or gid is not None and info.st_gid != gid
                    or modes is not None and stat.S_IMODE(info.st_mode) not in modes
                    or info.st_mode & 0o022):
                raise ValueError('unsafe-file')
            return info

    def read(self, value, *, uid=None, gid=None, modes=None, leaf_parent_uid=None):
        with self.parent(value, leaf_parent_uid=leaf_parent_uid) as (parent, name):
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            with os.fdopen(descriptor, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                        or info.st_uid != (self.owner_uid if uid is None else uid)
                        or gid is not None and info.st_gid != gid
                        or modes is not None and stat.S_IMODE(info.st_mode) not in modes
                        or info.st_mode & 0o022 or info.st_size > LIMIT):
                    raise ValueError('unsafe-file')
                raw = stream.read(LIMIT + 1)
                if (_stamp(info) != _stamp(os.fstat(stream.fileno()))
                        or _stamp(info) != _stamp(os.stat(name, dir_fd=parent, follow_symlinks=False))):
                    raise ValueError('changed-file')
        return raw

    def present(self, value):
        try:
            with self.parent(value) as (parent, name):
                os.stat(name, dir_fd=parent, follow_symlinks=False)
            return True
        except FileNotFoundError:
            return False


def _installation(probe, install):
    try:
        with probe.parent(install + '/current') as (parent, name):
            info = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if not stat.S_ISLNK(info.st_mode) or info.st_uid != probe.owner_uid:
                raise ValueError('current')
            link = os.readlink(name, dir_fd=parent)
        release = str(PurePosixPath(install) / link)
        revision = PurePosixPath(release).name
        if release != install + '/releases/' + revision or not re.fullmatch('[0-9a-f]{40}', revision):
            raise ValueError('release')
        manifest = _json(probe.read(release + '/artifact-manifest.json'))
        identity = _json(probe.read(release + '/reviewed-source/.relay-source.json'))
        if (manifest.get('commit') != revision or identity.get('revision') != revision
                or any(manifest.get(key, revision) != revision for key in ['installedRevision', 'resolvedRevision'])
                or not re.fullmatch('[0-9a-f]{40}', manifest.get('gitTree', ''))
                or manifest.get('gitTree') != identity.get('tree')):
            raise ValueError('identity')
        return {'status': 'present', 'revision': revision}, release, manifest
    except FileNotFoundError:
        # A current pointer with missing release/identity is damaged, not fresh.
        try:
            if probe.present(install + '/current'):
                return {'status': 'invalid'}, None, None
            with probe.parent(install + '/current') as (parent, _):
                with os.scandir(parent) as entries:
                    if any(entry.name not in ['runner', 'general-runner'] for entry in entries):
                        return {'status': 'invalid'}, None, None
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            return {'status': 'invalid'}, None, None
        return {'status': 'missing'}, None, None
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return {'status': 'invalid'}, None, None


def _configuration(probe, config, release, manifest):
    result = {'status': 'unavailable', 'consumer': 'missing', 'deployment': 'unavailable'}
    try:
        current = _json(probe.read('/etc/' + config['environment']['namespace'] + '/consumer.json'))
        result['consumer'] = 'equivalent' if _consumer(current) == _consumer(config['consumer']) else 'different'
    except FileNotFoundError:
        pass
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        result['consumer'] = 'invalid'
    if release:
        try:
            raw = probe.read(release + '/deployment-config.json', modes={0o600})
            if manifest.get('deploymentConfigSha256') != hashlib.sha256(raw).hexdigest():
                raise ValueError('snapshot-binding')
            result['deployment'] = 'equivalent' if _intent(_json(raw)) == _intent(config) else 'different'
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            result['deployment'] = 'invalid'
    if 'invalid' in [result['consumer'], result['deployment']]:
        result['status'] = 'invalid'
    elif 'different' in [result['consumer'], result['deployment']]:
        result['status'] = 'different'
    elif result['consumer'] == result['deployment'] == 'equivalent':
        result['status'] = 'equivalent'
    elif result['consumer'] == 'equivalent':
        result['status'] = 'consumer-equivalent'
    elif result['consumer'] == 'missing' and release is None:
        result['status'] = 'missing'
    return result


def _runner(probe, config, general):
    env = config['environment']
    runner = env['generalRunner' if general else 'runner']
    suffix = 'general-runner' if general else 'runner'
    install, state = '/opt/' + env['namespace'], '/var/lib/' + env['namespace']
    runner_root = install + '/' + suffix
    scope = runner.get('scope', 'repository')
    result = {'status': 'invalid', 'freshTokenRequired': False}
    try:
        pending = state + '/runner-registration-' + runner['name'] + '.pending'
        if probe.present(pending):
            return {**result, 'reason': 'registration-pending',
                    'next': 'reconcile proven registration with runner-register or inspect unknown attempt'}
        # Missing runner package/Unix identity on a fresh target is normal.
        if not probe.present(runner_root):
            return {'status': 'missing', 'freshTokenRequired': True,
                    'next': 'install runner package; fresh registration token required'}
        uid, gid = probe.identity(runner['user'])
        try:
            raw = probe.read(runner_root + '/.runner', uid=uid, gid=gid, modes={0o600}, leaf_parent_uid=uid)
        except FileNotFoundError:
            try:
                probe.metadata(runner_root + '/.credentials', uid=uid, gid=gid, modes={0o600}, leaf_parent_uid=uid)
            except FileNotFoundError:
                # The runner writes its RSA key before AddRunner/AddAgent but
                # saves the other markers afterwards. RSA-only residue cannot
                # distinguish a pre-registration failure from a remote success.
                try:
                    probe.metadata(runner_root + '/.credentials_rsaparams', uid=uid, gid=gid,
                                   modes={0o600}, leaf_parent_uid=uid)
                except FileNotFoundError:
                    return {'status': 'missing', 'freshTokenRequired': True,
                            'next': 'fresh registration token required'}
            raise ValueError('partial-registration')
        probe.metadata(runner_root + '/.credentials', uid=uid, gid=gid, modes={0o600}, leaf_parent_uid=uid)
        marker = _json(raw.decode('utf-8-sig'))
        repository = config['consumer']['repository']
        url = 'https://github.com/' + (repository.split('/')[0] if scope == 'organization' else repository)
        if (marker.get('gitHubUrl') != url or marker.get('agentName') != runner['name']
                or marker.get('workFolder') != state + '/' + suffix + '/work'
                or type(marker.get('agentId')) is not int or marker['agentId'] < 1
                or scope == 'organization' and marker.get('poolName') != runner['group']):
            raise ValueError('runner-binding')
        return {'status': 'reusable', 'freshTokenRequired': False,
                'proof': 'local-registration-identity-and-protected-credential-metadata',
                'next': 'owner verifies live GitHub registration and runner-group policy before enablement'}
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return {**result, 'reason': 'registration-state-ambiguous', 'next': 'inspect intended runner before registration'}


def _protected_state(probe, config):
    env = config['environment']
    config_root = '/etc/' + env['namespace']
    specifications = []
    for role in ['reviewer', 'writer', 'codex']:
        field = 'sourceTokenFile' if role == 'codex' else 'sourceKeyFile'
        source = env.get(role + 'Credential', {}).get(field)
        if source:
            specifications.append((role + '-source', source, {0o600, 0o640} if role == 'reviewer' else {0o600},
                                   probe.owner_uid, None, 'external', role + '-credentials'))
    specifications.extend([
        ('writer-installed-key', config['consumer']['paths']['credentialKeyFile'], {0o600},
         probe.owner_uid, None, 'protected-retained', 'writer-credentials'),
        ('reviewer-installed-key', config_root + '/reviewer-credentials/github-app-private-key.pem', {0o640},
         probe.owner_uid, None, 'protected-retained', 'reviewer-credentials'),
        ('openai-client-ca', config_root + '/certs/openai-client-ca.pem', {0o644, 0o640, 0o600},
         probe.owner_uid, None, 'product-bootstrap', 'tls-check / tls-prepare'),
    ])
    try:
        uid, _ = probe.identity(config['consumer']['runtimeUser'])
    except (KeyError, OSError):
        uid = -1
    specifications.append(('codex-installed-token', config_root + '/codex-credentials/access-token', {0o600},
                           uid, uid, 'protected-retained', 'codex-credentials'))
    tls = env.get('tls')
    pair = ((tls or {}).get('source') or
            ({'certificateFile': config_root + '/certs/server-fullchain.pem',
              'privateKeyFile': config_root + '/certs/server-private-key.pem'} if tls is not None else
             {'certificateFile': '/etc/letsencrypt/live/' + env['ingress']['serverName'] + '/fullchain.pem',
              'privateKeyFile': '/etc/letsencrypt/live/' + env['ingress']['serverName'] + '/privkey.pem'}))
    for field, path in pair.items():
        specifications.append(('tls-' + field, path, {0o600, 0o640} if field == 'privateKeyFile' else {0o644, 0o640, 0o600},
                               probe.owner_uid, None, 'external' if tls is None or 'source' in tls else 'product-bootstrap',
                               'tls-check'))
    result = []
    for label, path, modes, uid, parent_uid, ownership, action in specifications:
        item = {'name': label, 'ownership': ownership, 'validation': 'metadata-only', 'next': action}
        try:
            # Let's Encrypt maintains a fixed root-owned live-to-archive link.
            # TLS qualification validates the certificate/key contents later.
            with probe.parent(path, leaf_parent_uid=parent_uid) as (parent, name):
                info = os.stat(name, dir_fd=parent, follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode) and path.startswith('/etc/letsencrypt/live/'):
                    if info.st_uid != probe.owner_uid:
                        raise ValueError('tls-link-owner')
                    link = os.readlink(name, dir_fd=parent)
                    host = env['ingress']['serverName']
                    match = re.fullmatch(r'../../archive/' + re.escape(host) + r'/(fullchain|privkey)[1-9][0-9]*\.pem', link)
                    if not match or match[1] != ('privkey' if label.endswith('privateKeyFile') else 'fullchain'):
                        raise ValueError('tls-link-target')
                    path = '/etc/letsencrypt/archive/' + host + '/' + PurePosixPath(link).name
            group = None
            if label in ['writer-source', 'writer-installed-key', 'codex-source']:
                group = 0 if probe.owner_uid == 0 else os.getgid()
            elif label == 'reviewer-installed-key':
                _, group = probe.identity(env['reviewerUser'])
            elif label == 'codex-installed-token':
                _, group = probe.identity(config['consumer']['runtimeUser'])
            probe.metadata(path, uid=uid, gid=group, modes=modes, leaf_parent_uid=parent_uid)
            item['status'] = 'reusable-metadata'
        except FileNotFoundError:
            item['status'] = 'missing'
        except (OSError, ValueError, TypeError, KeyError):
            item['status'] = 'invalid'
        result.append(item)
    return result


def inspect(config, *, root=Path('/'), owner_uid=0, boundary=None, user_ids=None):
    """Inventory is observation only, never decommission/installation authority.

    ``root``, ``boundary`` and identities are fixture seams, not public CLI
    inputs. The public transport always probes the real configured target.
    """
    probe = Probe(root, owner_uid, boundary, user_ids)
    namespace = config['environment']['namespace']
    if not re.fullmatch('[a-z][a-z0-9-]{0,30}', namespace):
        raise ValueError('inventory-namespace')
    installed, release, manifest = _installation(probe, '/opt/' + namespace)
    configuration = _configuration(probe, config, release, manifest)
    runners = {'production': _runner(probe, config, False), 'general': _runner(probe, config, True)}
    protected = _protected_state(probe, config)
    blockers = []
    for label, path in [('clean-reinstall-recovery', '/var/lib/' + namespace + '-clean-reinstall.json'),
                        ('production-operation-recovery', '/var/lib/' + namespace + '-production-operation.json')]:
        try:
            if probe.present(path):
                blockers.append(label + '-present;inspect-before-retry')
        except (OSError, ValueError):
            blockers.append(label + '-invalid;inspect-before-retry')
    if installed['status'] == 'invalid':
        blockers.append('installed-identity-invalid')
    if configuration['status'] in ['invalid', 'different']:
        blockers.append('configuration-' + configuration['status'])
    if installed['status'] == 'present' and configuration['consumer'] == 'missing':
        blockers.append('installed-consumer-configuration-missing')
    blockers.extend('runner-' + name + '-ambiguous' for name, row in runners.items() if row['status'] == 'invalid')
    blockers.extend('protected-state-' + row['name'] + '-invalid' for row in protected if row['status'] == 'invalid')
    consumer = config['consumer']
    repository, organization = consumer['repository'], consumer['repository'].split('/')[0]
    workflow_ref = '@refs/heads/' + consumer['baseBranch']
    production_workflow = repository + '/.github/workflows/manual-main-production-deploy.yml' + workflow_ref
    general_workflows = [repository + '/' + consumer[field] + workflow_ref
                         for field in ['routingWorkflow', 'recoveryWorkflow']]
    return {'schemaVersion': 1, 'readOnly': True, 'mutationAuthorized': False,
            'status': 'blocked' if blockers else 'observed', 'installed': installed,
            'configuration': configuration, 'runners': runners, 'protectedState': protected,
            'blockers': blockers,
            'ownerAdmin': [
                {'name': 'github-app-installations-and-permissions', 'status': 'unavailable',
                 'settings': 'https://github.com/' + repository + '/settings/installations',
                 'next': 'owner-admin verifies configured distinct Writer and Reviewer App installation IDs, '
                         'permissions and repository access against consumer.writerApp and consumer.reviewerApp'},
                {'name': 'github-runner-registration-and-policy', 'status': 'unavailable',
                 'registrationSettings': 'https://github.com/' + repository + '/settings/actions/runners',
                 'groupSettings': 'https://github.com/organizations/' + organization + '/settings/actions/runner-groups',
                 'production': {'group': config['environment']['runner']['group'],
                                'onlyRepository': repository, 'onlyWorkflowRefs': [production_workflow]},
                 'general': {'scope': config['environment']['generalRunner'].get('scope', 'repository'),
                             'group': config['environment']['generalRunner'].get('group'),
                             'onlyRepository': repository, 'onlyWorkflowRefs': general_workflows},
                 'next': 'owner-admin verifies registrations and saved isolated group restrictions; '
                         'repository-scoped general runners need equivalent external scheduling isolation; '
                         'labels and workflow conditions are insufficient; keep inactive until independently qualified'},
                {'name': 'dns-and-ingress', 'status': 'unavailable',
                 'next': 'owner verifies configured public DNS/ingress; run tls-check for protected TLS validation'},
            ] + ([{'name': 'installed-environment-intent', 'status': 'unavailable',
                    'next': 'no protected deployment snapshot; review durable environment intent before authorized clean reinstall'}]
                  if installed['status'] == 'present' and configuration['deployment'] == 'unavailable' else [])}


def _validate_report(report):
    """Reject partial transport evidence before callers use its status fields."""
    expected = {'schemaVersion', 'readOnly', 'mutationAuthorized', 'status', 'installed',
                'configuration', 'runners', 'protectedState', 'blockers', 'ownerAdmin'}
    if (not isinstance(report, dict) or report.keys() != expected or report['schemaVersion'] != 1
            or report['readOnly'] is not True or report['mutationAuthorized'] is not False
            or report['status'] not in ['observed', 'blocked']):
        raise ValueError('inventory-proof')
    installed = report['installed']
    if (not isinstance(installed, dict) or installed.get('status') not in ['present', 'missing', 'invalid']
            or installed['status'] == 'present' and not re.fullmatch('[0-9a-f]{40}', installed.get('revision', ''))):
        raise ValueError('inventory-installed-proof')
    configuration = report['configuration']
    if (not isinstance(configuration, dict) or configuration.keys() != {'status', 'consumer', 'deployment'}
            or configuration['status'] not in ['equivalent', 'consumer-equivalent', 'missing', 'different', 'invalid', 'unavailable']
            or configuration['consumer'] not in ['equivalent', 'different', 'missing', 'invalid']
            or configuration['deployment'] not in ['equivalent', 'different', 'unavailable', 'invalid']):
        raise ValueError('inventory-config-proof')
    runners = report['runners']
    if not isinstance(runners, dict) or runners.keys() != {'production', 'general'}:
        raise ValueError('inventory-runners-proof')
    for runner in runners.values():
        if (not isinstance(runner, dict) or runner.get('status') not in ['reusable', 'missing', 'invalid']
                or runner.get('freshTokenRequired') is not (runner['status'] == 'missing')):
            raise ValueError('inventory-runner-proof')
    protected = report['protectedState']
    if (not isinstance(protected, list) or len(protected) > 16
            or any(not isinstance(row, dict) or not isinstance(row.get('name'), str)
                   or row.get('status') not in ['reusable-metadata', 'missing', 'invalid']
                   or row.get('validation') != 'metadata-only' for row in protected)):
        raise ValueError('inventory-protected-proof')
    blockers = report['blockers']
    if (not isinstance(blockers, list) or len(blockers) > 32
            or any(not isinstance(code, str) or not re.fullmatch('[a-zA-Z;-]{1,160}', code) for code in blockers)
            or bool(blockers) != (report['status'] == 'blocked')):
        raise ValueError('inventory-blockers-proof')
    admin = report['ownerAdmin']
    if (not isinstance(admin, list) or not 3 <= len(admin) <= 4
            or any(not isinstance(row, dict) or not isinstance(row.get('name'), str)
                   or row.get('status') != 'unavailable' or not isinstance(row.get('next'), str) for row in admin)):
        raise ValueError('inventory-admin-proof')
    return report


def remote_inventory(target, key, config):
    """The entrypoint validates config and SSH identity before this call."""
    source = Path(__file__).read_text()
    argv = ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'IdentitiesOnly=yes',
            '-i', str(key), target['user'] + '@' + target['host'],
            shlex.join(['/usr/bin/python3', '-I', '-c', source])]
    try:
        result = subprocess.run(argv, input=json.dumps(config), text=True, capture_output=True, timeout=45)
        if result.returncode or len(result.stdout) > LIMIT:
            raise ValueError('inventory-transport')
        return _validate_report(_json(result.stdout))
    except (OSError, ValueError, TypeError, AttributeError, subprocess.TimeoutExpired):
        raise RuntimeError('RELAY_INVENTORY_UNAVAILABLE;inspect-target-access-and-protected-prerequisites') from None


if __name__ == '__main__':
    try:
        report = inspect(_json(sys.stdin.buffer.read(LIMIT + 1)))
        print(json.dumps(report, sort_keys=True, separators=(',', ':')))
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        print('RELAY_INVENTORY_UNAVAILABLE;inspect-configured-target', file=sys.stderr)
        sys.exit(1)
