"""Version 1 deployment input. No playbooks, templates or backend variables in it."""
from pathlib import Path, PurePosixPath
import json
import ipaddress
import re
import subprocess


class InvalidConfig(ValueError):
    pass


def require(condition, field):
    if not condition:
        raise InvalidConfig(f'INVALID_DEPLOYMENT_CONFIG:{field}')


def object_keys(value, required, optional=()):
    return isinstance(value, dict) and set(required) <= value.keys() <= set(required) | set(optional)


def text(value, pattern):
    return isinstance(value, str) and re.fullmatch(pattern, value) is not None


def absolute(value):
    return text(value, r'/[A-Za-z0-9_./-]+') and all(p not in ('', '.', '..') for p in value.split('/')[1:])


def relative(value):
    return text(value, r'[A-Za-z0-9_./-]+') and all(p not in ('', '.', '..') for p in value.split('/'))


def selector(value):
    return (text(value, r'[A-Za-z0-9][A-Za-z0-9._/-]{0,239}') and '..' not in value
            and all(p and not p.startswith('.') and not p.endswith('.lock') for p in value.split('/')))


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate-key')
        result[key] = value
    return result


def load(path, product_root):
    return loads(Path(path).read_text(), product_root)


def loads(raw, product_root):
    require(len(raw) <= 65536, 'size')
    require(not re.search(r'{{|{%|PRIVATE KEY|(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]{20,}', raw), 'literal-data-only')
    config = json.loads(raw, object_pairs_hook=unique_object)
    derive_managed_pool_slots(config)
    validate(config, product_root)
    return config


def configured_repositories(config):
    """Return the installation allowlist without selecting an execution target."""
    consumer = config['consumer']
    return consumer.get('repositories', [consumer.get('repository')])


def deployment_repository(config, repository=None):
    """Resolve the protected lifecycle anchor or an explicit projection target."""
    repositories = configured_repositories(config)
    selected = repository if repository is not None else config['environment'].get(
        'repository', config['consumer'].get('repository'))
    require(isinstance(selected, str) and selected in repositories, 'environment.repository')
    return selected


def derive_managed_pool_slots(config):
    """Stable internal routes; desired capacity never allocates per-repo runners."""
    consumer, environment = config.get('consumer', {}), config.get('environment', {})
    if 'generalRunnerPool' not in consumer:
        return
    supplied = consumer.get('executionSlots')
    general = environment.get('generalRunner', {})
    require(all(key in general for key in ['name', 'user']), 'generalRunnerPool.generalRunner')
    require('namespace' in environment and 'codexWorkGroup' in environment,
            'generalRunnerPool.environment')
    require('runtimeUser' in consumer and 'paths' in consumer, 'generalRunnerPool.consumer')
    fields = ['workRoot', 'attemptRoot', 'dispatch', 'launcher', 'diagnosticsConfig',
              'diagnosticsStore', 'diagnosticsRoot']
    require(all(key in consumer['paths'] for key in fields), 'generalRunnerPool.paths')
    consumer['executionSlots'] = []
    for number in range(1, 33):
        slot_id = 'primary' if number == 1 else f'pool-{number}'
        consumer['executionSlots'].append({
            'id': slot_id, 'runnerName': general['name'] + ('' if number == 1 else f'-{number}'),
            'runnerUser': general['user'], 'runtimeUser': consumer['runtimeUser'],
            'workGroup': environment['codexWorkGroup'],
            'paths': ({key: consumer['paths'][key] for key in fields} if number == 1
                      else execution_slot_paths(environment['namespace'], slot_id))})
    require(supplied is None or supplied == consumer['executionSlots'],
            'generalRunnerPool.derived-executionSlots')


def validate(c, product_root):
    require(object_keys(c, ['schemaVersion', 'source', 'target', 'consumer', 'environment']), 'keys')
    require(c['schemaVersion'] == 1, 'schemaVersion')
    source = c['source']
    require(object_keys(source, ['repository'], ['revision']), 'source')
    require(text(source['repository'], r'(?:git@github\.com:|https://github\.com/)[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?'), 'source.repository')
    require(selector(source.get('revision', 'main')), 'source.revision')
    target = c['target']
    require(object_keys(target, ['host', 'user', 'hostFingerprint'],
                        ['connection', 'identityFile', 'identityFingerprint']), 'target')
    require(target.get('connection', 'ssh') in ['ssh', 'local'], 'target.connection')
    require(text(target['host'], r'[A-Za-z0-9][A-Za-z0-9.-]{0,252}'), 'target.host')
    require(target['user'] == 'root', 'target.user')
    if target.get('connection', 'ssh') == 'ssh' or 'identityFile' in target:
        require(isinstance(target.get('identityFile'), str)
                and absolute(target['identityFile'].replace('~/', '/home/operator/', 1)), 'target.identityFile')
    for key in ['identityFingerprint', 'hostFingerprint']:
        if key == 'hostFingerprint' or target.get('connection', 'ssh') == 'ssh' or key in target:
            require(text(target.get(key), r'SHA256:[A-Za-z0-9+/]{43}'), 'target.' + key)
    # The runtime remains the authority for its existing schema; do not create
    # a second subtly different validator in the deployment implementation.
    validation = subprocess.run(['node', '--input-type=module', '-e',
        'import {validateConsumer} from "./consumer/consumer-config.mjs";'
        'let s="";for await(const b of process.stdin)s+=b;'
        'try{validateConsumer(JSON.parse(s))}catch{process.exit(1)}'],
        input=json.dumps(c['consumer']), text=True, cwd=product_root, capture_output=True)
    require(validation.returncode == 0, 'consumer')
    e = c['environment']
    require('workGroup' not in c['consumer'] or c['consumer']['workGroup'] == e.get('codexWorkGroup'),
            'consumer.workGroup')
    require(object_keys(e, ['namespace', 'serviceUser', 'reviewerUser', 'codexWorkGroup', 'runner',
        'generalRunner', 'reviewerBind', 'ingress', 'localApply', 'codexTokenRequired', 'compatibilityLinks'],
        ['repository', 'reviewCheckName', 'reviewerRepositories', 'instance', 'tls', 'reviewerCredential', 'writerCredential', 'codexCredential']), 'environment')
    repository = deployment_repository(c)
    writer_repositories = configured_repositories(c)
    if 'reviewerRepositories' in e:
        repositories = e['reviewerRepositories']
        require(isinstance(repositories, list) and bool(repositories)
                and all(text(v, r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9_.-]{1,100}')
                        and '--' not in v.split('/')[0] and v.split('/')[1] not in ['.', '..']
                        for v in repositories), 'reviewerRepositories')
    for key in ['namespace', 'serviceUser', 'reviewerUser', 'codexWorkGroup']:
        require(text(e[key], r'[a-z][a-z0-9-]{0,30}') and e[key] != 'root', key)
    r, g = e['runner'], e['generalRunner']
    require(object_keys(r, ['user', 'name', 'scope', 'group', 'labels']), 'runner')
    require(object_keys(g, ['user', 'name'], ['scope', 'group', 'poolApp']), 'generalRunner')
    for instance in [r, g]:
        require(text(instance['user'], r'[a-z][a-z0-9-]{0,30}') and instance['user'] != 'root', 'runner.user')
        require(text(instance['name'], r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}'), 'runner.name')
    require(r['scope'] == 'organization', 'runner.scope')
    require(text(r['group'], r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}'), 'runner.group')
    general_scope = g.get('scope', 'repository')
    require(general_scope in ['repository', 'organization'], 'generalRunner.scope')
    if general_scope == 'organization':
        require(text(g.get('group'), r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}'), 'generalRunner.group')
        require(g['group'].lower() != r['group'].lower(), 'isolated-runner-groups')
    else:
        require('group' not in g, 'generalRunner.group')
    pool = c['consumer'].get('generalRunnerPool')
    if pool is not None:
        require(all(value.split('/')[0] == repository.split('/')[0] for value in writer_repositories),
                'generalRunnerPool.organization')
        require(general_scope == 'organization', 'generalRunnerPool.organization-scope')
        require(text(g['name'], r'[a-z][a-z0-9-]{0,54}'), 'generalRunnerPool.name')
        require('instance' in e, 'generalRunnerPool.namespaced-instance')
        app = g.get('poolApp')
        require(object_keys(app, ['appId', 'installationId', 'privateKeyFile']), 'generalRunner.poolApp')
        require(all(text(app[key], r'[1-9][0-9]{0,19}') for key in ['appId', 'installationId']),
                'generalRunner.poolApp.identity')
        require(absolute(app['privateKeyFile']), 'generalRunner.poolApp.privateKeyFile')
    else:
        require('poolApp' not in g, 'generalRunner.poolApp.requires-pool')
    require(isinstance(r['labels'], list) and len(r['labels']) == 1
            and all(text(v, r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}') for v in r['labels']), 'runner.labels')
    users = [e['serviceUser'], e['reviewerUser'], r['user'], g['user'], c['consumer']['runtimeUser']]
    require(len(set(users)) == len(users), 'isolated-users')
    require(e['codexWorkGroup'] not in users, 'isolated-work-group')
    runtime_users = c['consumer'].get('repositoryRuntimeUsers', {})
    require(not set(runtime_users.values()) & set(users[:-1] + [e['codexWorkGroup']]),
            'repositoryRuntimeUsers.isolated-users')
    require(r['name'] != g['name'], 'isolated-runner-names')
    slots = c['consumer'].get('executionSlots')
    if slots is not None:
        primary = slots[0]
        require(primary['id'] == 'primary' and primary['runnerName'] == g['name']
                and primary['runnerUser'] == g['user']
                and primary['workGroup'] == e['codexWorkGroup'], 'executionSlots.primary')
        require('instance' in e, 'executionSlots.namespaced-instance')
        slot_users = [slot[key] for slot in slots for key in ['runnerUser', 'runtimeUser']]
        protected_users = [e['serviceUser'], e['reviewerUser'], r['user']]
        require(not set(slot_users) & set(protected_users), 'executionSlots.isolated-users')
        if pool is None:
            require(len(set(slot_users)) == len(slot_users), 'executionSlots.isolated-users')
        groups = [slot['workGroup'] for slot in slots]
        require((pool is not None or len(set(groups)) == len(groups))
                and not set(groups) & set(slot_users + protected_users + list(runtime_users.values())),
                'executionSlots.isolated-work-groups')
        require(r['name'] not in [slot['runnerName'] for slot in slots], 'executionSlots.production-runner')
        for slot in slots[1:]:
            require(slot['paths'] == execution_slot_paths(e['namespace'], slot['id']),
                    'executionSlots.fixed-paths')
    if 'instance' in e:
        instance = e['instance']
        require(object_keys(instance, ['reviewerPort', 'publicationEnabled']), 'instance')
        require(type(instance['reviewerPort']) is int
                and 1024 <= instance['reviewerPort'] <= 65535, 'instance.reviewerPort')
        require(type(instance['publicationEnabled']) is bool, 'instance.publicationEnabled')
        # A second consumer must not reach another consumer's privileged paths.
        roots = tuple(prefix + e['namespace'] + '/' for prefix in ['/opt/', '/etc/', '/var/lib/'])
        require(all(path.startswith(roots) for path in c['consumer']['paths'].values()),
                'instance.paths')
    bind = e['reviewerBind']
    require(object_keys(bind, ['mode', 'network', 'container']), 'reviewerBind')
    require(bind['mode'] in ['loopback', 'docker_gateway'], 'reviewerBind.mode')
    for key in ['network', 'container']:
        require(text(bind[key], r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}'), 'reviewerBind.' + key)
    ingress = e['ingress']
    require(object_keys(ingress, ['serverName', 'ownershipRoot', 'foreignServerName', 'service',
                                 'protectedPaths', 'protectedServices'], ['publicAddresses']), 'ingress')
    for key in ['serverName', 'foreignServerName']:
        require(text(ingress[key], r'[A-Za-z0-9][A-Za-z0-9.-]{0,252}'), 'ingress.' + key)
    if 'publicAddresses' in ingress:
        addresses = ingress['publicAddresses']
        require(isinstance(addresses, list) and 1 <= len(addresses) <= 16
                and all(isinstance(v, str) for v in addresses), 'ingress.publicAddresses')
        try:
            canonical = [str(ipaddress.ip_address(v)) for v in addresses]
        except ValueError:
            require(False, 'ingress.publicAddresses')
        require(canonical == addresses and len(set(canonical)) == len(canonical), 'ingress.publicAddresses')
    require(absolute(ingress['ownershipRoot']), 'ingress.ownershipRoot')
    require(isinstance(ingress['protectedPaths'], list) and all(absolute(p) for p in ingress['protectedPaths']), 'protectedPaths')
    require(isinstance(ingress['protectedServices'], list), 'protectedServices')
    for unit in [ingress['service'], *ingress['protectedServices']]:
        require(text(unit, r'[A-Za-z0-9_.-]+\.service'), 'service')
    owned_paths = [prefix + e['namespace'] for prefix in ['/opt/', '/etc/', '/var/lib/', '/var/log/', '/run/']]
    owned_paths.append('/var/lib/' + e['namespace'] + '-deployment.lock')
    if pool is not None:
        require(e['namespace'] != 'codex-relay-pools', 'generalRunnerPool.namespace-collision')
        owned_paths.extend(['/opt/codex-relay-pools/' + g['name'],
                            '/var/lib/codex-relay-pools/' + g['name'],
                            '/var/lib/codex-relay-pool-' + g['name'] + '-deployment.lock'])
    for owned in owned_paths:
        for protected in [ingress['ownershipRoot'], *ingress['protectedPaths']]:
            require(not (owned == protected or owned.startswith(protected + '/') or protected.startswith(owned + '/')), 'path-overlap')
    local_apply = e['localApply']
    if object_keys(local_apply, ['source']) and local_apply['source'] == 'installed':
        repository = c['source']['repository'].removeprefix('https://github.com/').removeprefix('git@github.com:').removesuffix('.git')
        require(repository == deployment_repository(c) and c['consumer']['baseBranch'] == 'main'
                and c['source'].get('revision', 'main') == 'main', 'localApply.installed-self-consumer')
    else:
        require(object_keys(local_apply, ['configPath']) and relative(local_apply['configPath']), 'localApply')
    require(type(e['codexTokenRequired']) is bool, 'codexTokenRequired')
    if 'tls' in e:
        tls = e['tls']
        require(object_keys(tls, [], ['source', 'acme']), 'tls')
        if 'source' in tls:
            source = tls['source']
            require(object_keys(source, ['certificateFile', 'privateKeyFile']), 'tls.source')
            require(all(absolute(v) for v in source.values()), 'tls.source.paths')
            require(source['certificateFile'] != source['privateKeyFile'], 'tls.source.distinct')
        if 'acme' in tls:
            acme = tls['acme']
            require(object_keys(acme, ['email', 'challenge', 'webroot']), 'tls.acme')
            require(text(acme['email'], r'[A-Za-z0-9._+%-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}'), 'tls.acme.email')
            require(acme['challenge'] == 'webroot', 'tls.acme.challenge')
            require(absolute(acme['webroot']) and acme['webroot'].startswith(ingress['ownershipRoot'] + '/'),
                    'tls.acme.webroot')
            require(bind['mode'] == 'docker_gateway', 'tls.acme.topology')
            require('publicAddresses' in ingress, 'tls.acme.publicAddresses')
            require(text(ingress['serverName'], r'(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}'),
                    'tls.acme.hostname')
            require(ingress['serverName'] != ingress['foreignServerName'], 'tls.acme.distinct-hostname')
            # Issuance owns its output. It must never overwrite an external reuse source.
            require('source' not in tls, 'tls.source-or-acme')
    for name, field in [('reviewerCredential', 'sourceKeyFile'), ('writerCredential', 'sourceKeyFile'),
                        ('codexCredential', 'sourceTokenFile')]:
        if name in e:
            credential = e[name]
            require(object_keys(credential, [field]) and absolute(credential[field]), name)
    require(text(e.get('reviewCheckName', 'chatgpt-review'), r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}'), 'reviewCheckName')
    links = e['compatibilityLinks']
    require(isinstance(links, dict) and len(links) <= 8, 'compatibilityLinks')
    for alias, destination in links.items():
        require(relative(alias) and '/' in alias and alias.split('/')[0] not in
                ['controller', 'consumer', 'contracts', 'runtime', 'reviewer', 'deploy'], 'compatibilityLinks.alias')
        require(destination in ['controller', 'consumer', 'contracts', 'runtime', 'reviewer'], 'compatibilityLinks.destination')


def execution_slot_paths(namespace, slot_id):
    install = '/opt/' + namespace + '/slots/' + slot_id
    config = '/etc/' + namespace + '/slots/' + slot_id
    state = '/var/lib/' + namespace + '/slots/' + slot_id
    return {'workRoot': state + '/work', 'attemptRoot': state + '/dispatch/attempts-v2',
            'dispatch': install + '/relay-codex-dispatch', 'launcher': install + '/relay-codex',
            'diagnosticsConfig': config + '/runtime-diagnostics.json',
            'diagnosticsStore': install + '/relay-diagnostics-store', 'diagnosticsRoot': state + '/debug'}


def execution_slot_inputs(c, slot):
    """Fixed namespaced overrides; no executable, credential or repository selector."""
    e = c['environment']
    ns, slot_id = e['namespace'], slot['id']
    install, config, state = '/opt/' + ns + '/slots/' + slot_id, '/etc/' + ns + '/slots/' + slot_id, '/var/lib/' + ns + '/slots/' + slot_id
    # Repository overrides follow the installation default runtime identity.
    # An explicitly independent slot retains its own account and credential.
    runtime_users = (c['consumer'].get('repositoryRuntimeUsers', {})
                     if slot['runtimeUser'] == c['consumer']['runtimeUser'] else {})
    result = {
        'relay_execution_slot': slot_id, 'relay_execution_slot_install_root': install,
        'relay_execution_slot_isolation': True,
        'relay_runner_name': slot['runnerName'], 'relay_runner_user': slot['runnerUser'],
        'relay_runner_group': slot['runnerUser'], 'relay_runner_root': install + '/runner',
        'relay_runner_work_root': state + '/runner/work', 'relay_runner_home': state + '/runner/home',
        'relay_runner_service_name': ns + '-slot-' + slot_id + '-runner.service',
        'relay_runner_service_unit_path': '/etc/systemd/system/' + ns + '-slot-' + slot_id + '-runner.service',
        'relay_runner_labels': e['runner']['labels'] + [execution_slot_label(c, slot)],
        'relay_runner_registration_helper_path': install + '/relay-runner-registration',
        'relay_runner_registration_scope': e['generalRunner'].get('scope', 'repository'),
        'relay_runner_registration_group': e['generalRunner'].get('group', ''),
        'relay_dispatch_user': slot['runnerUser'], 'relay_dispatch_group': slot['runnerUser'],
        'relay_codex_user': slot['runtimeUser'], 'relay_codex_group': slot['runtimeUser'],
        'relay_repository_runtime_users': runtime_users,
        'relay_additional_runtime_users': sorted(set(runtime_users.values()) - {slot['runtimeUser']}),
        'relay_codex_work_group': slot['workGroup'], 'relay_codex_home': state + '/codex-home',
        'relay_codex_access_token_root': config + '/codex-credentials',
        'relay_codex_access_token_file': config + '/codex-credentials/access-token',
        'relay_dispatch_state_root': state + '/dispatch', 'relay_dispatch_home': state + '/dispatch-home',
        'relay_dispatch_evidence_root': state + '/dispatch/evidence',
        'relay_dispatch_remediation_root': state + '/dispatch/remediation',
        'relay_dispatch_work_root': slot['paths']['workRoot'],
        'relay_codex_dispatch_path': slot['paths']['dispatch'], 'relay_codex_launcher_path': slot['paths']['launcher'],
        'relay_diagnostics_config_path': slot['paths']['diagnosticsConfig'],
        'relay_diagnostics_store_path': slot['paths']['diagnosticsStore'], 'relay_diagnostics_root': slot['paths']['diagnosticsRoot'],
        'relay_codex_sudoers_file': '/etc/sudoers.d/' + ns + '-slot-' + slot_id + '-codex',
    }
    if 'generalRunnerPool' in c['consumer']:
        number = 1 if slot_id == 'primary' else int(slot_id.removeprefix('pool-'))
        result['relay_runner_service_name'] = e['generalRunner']['name'] + f'-pool-{number}.service'
        result['relay_runner_service_unit_path'] = '/etc/systemd/system/' + result['relay_runner_service_name']
    return result


def execution_slot_label(c, slot):
    """A fixed native runner label, unique to repository, installation and slot."""
    import hashlib
    identity = (c['environment']['generalRunner']['name'] + ':' + slot['id']
                if 'generalRunnerPool' in c['consumer'] else
                deployment_repository(c) + ':' + c['environment']['namespace'] + ':' + slot['id'])
    return 'relay-slot-' + hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]


def general_pool_label(c):
    import hashlib
    return 'relay-pool-' + hashlib.sha256(c['environment']['generalRunner']['name'].encode()).hexdigest()[:24]


def select_execution_slot(c, slot_id='primary'):
    """Resolve only an automatic runner from validated durable configuration."""
    slots = c['consumer'].get('executionSlots', [])
    require(slot_id == 'primary' or any(slot['id'] == slot_id for slot in slots), 'execution-slot')
    if slot_id != 'primary':
        return execution_slot_inputs(c, next(slot for slot in slots if slot['id'] == slot_id))
    values = compile_inputs(c)
    ns = c['environment']['namespace']
    return {'relay_execution_slot': 'primary',
            'relay_runner_name': values['relay_general_runner_name'],
            'relay_runner_user': values['relay_general_runner_user'],
            'relay_runner_group': values['relay_general_runner_user'],
            'relay_runner_registration_scope': values['relay_general_runner_registration_scope'],
            'relay_runner_registration_group': values['relay_general_runner_registration_group'],
            'relay_runner_root': '/opt/' + ns + '/general-runner',
            'relay_runner_work_root': '/var/lib/' + ns + '/general-runner/work',
            'relay_runner_home': '/var/lib/' + ns + '/general-runner/home',
            'relay_runner_service_name': values.get('relay_general_runner_service_name', 'relay-general-runner.service'),
            'relay_runner_service_unit_path': '/etc/systemd/system/' + values.get('relay_general_runner_service_name', 'relay-general-runner.service'),
            'relay_runner_registration_helper_path': '/opt/' + ns + '/relay-general-runner-registration',
            'relay_runner_labels': values['relay_runner_labels'] + ([execution_slot_label(c, slots[0])] if slots else []),
            'relay_runner_service_state_management': 'preserve', 'relay_runner_service_enabled': False,
            'relay_runner_registration_enabled': False, 'relay_runner_registration_authorized': False,
            'relay_runner_registration_completed': False}


def compile_inputs(c):
    """Private adapter. All backend paths and lifecycle mechanics are Relay-owned."""
    e, consumer, target = c['environment'], c['consumer'], c['target']
    repository = deployment_repository(c)
    ns = e['namespace']
    install, config, state = '/opt/' + ns, '/etc/' + ns, '/var/lib/' + ns
    r, g, ingress, bind = e['runner'], e['generalRunner'], e['ingress'], e['reviewerBind']
    result = {
        'relay_namespace': ns, 'relay_user': e['serviceUser'], 'relay_group': e['serviceUser'],
        'relay_reviewer_user': e['reviewerUser'], 'relay_reviewer_group': e['reviewerUser'],
        'relay_install_root': install, 'relay_config_root': config, 'relay_state_root': state,
        'relay_log_root': '/var/log/' + ns, 'relay_runtime_root': '/run/' + ns,
        'relay_release_root': install + '/releases', 'relay_evidence_root': state + '/evidence',
        'relay_production_operation_record_path': '/var/lib/' + ns + '-production-operation.json',
        'relay_production_host': target['host'], 'relay_production_reviewer_server_name': ingress['serverName'],
        'relay_production_runner_name': r['name'], 'relay_production_runner_user': r['user'],
        'relay_production_runner_registration_group': r['group'],
        'relay_general_runner_name': g['name'], 'relay_general_runner_user': g['user'],
        'relay_general_runner_registration_scope': g.get('scope', 'repository'),
        'relay_general_runner_registration_group': g.get('group', ''),
        'relay_runner_name': r['name'], 'relay_runner_user': r['user'], 'relay_runner_group': r['user'],
        'relay_runner_registration_scope': r['scope'], 'relay_runner_registration_group': r['group'],
        'relay_runner_labels': r['labels'], 'relay_general_runner_labels': r['labels'],
        'relay_runner_repository': repository,
        'relay_github_repository': repository,
        'relay_writer_repositories': configured_repositories(c),
        'relay_runner_package_cache_root': '/var/cache/' + ns,
        'relay_dispatch_user': g['user'], 'relay_dispatch_group': g['user'],
        'relay_codex_user': consumer['runtimeUser'], 'relay_codex_group': consumer['runtimeUser'],
        'relay_codex_work_group': e['codexWorkGroup'], 'relay_codex_token_required': e['codexTokenRequired'],
        'relay_production_local_apply_checkout_root': state + '/runner/work/' + '/'.join([repository.split('/')[1]] * 2),
        'relay_production_local_apply_stage_root': state + '/production-apply',
        'relay_owner_lifecycle_helper_path': '/usr/local/sbin/' + ns + '-owner-lifecycle',
        'relay_local_apply_source': e['localApply'].get('source', 'checkout'),
        'relay_consumer_deployment_config_relative': e['localApply'].get('configPath', ''),
        'relay_reviewer_bind_mode': 'nexus_gateway' if bind['mode'] == 'docker_gateway' else 'a_only_loopback',
        'relay_docker_network_name': bind['network'], 'relay_docker_nginx_container_name': bind['container'],
        'relay_docker_nginx_service_name': ingress['service'],
        'relay_nexus_ownership_root': ingress['ownershipRoot'], 'relay_production_nexus_ownership_root': ingress['ownershipRoot'],
        'relay_nexus_b_server_name': ingress['foreignServerName'],
        'relay_nexus_protected_paths': ingress['protectedPaths'], 'relay_nexus_protected_services': ingress['protectedServices'],
        'relay_nginx_server_name': ingress['serverName'],
        'relay_nginx_server_certificate_file': '/etc/letsencrypt/live/' + ingress['serverName'] + '/fullchain.pem',
        'relay_nginx_server_private_key_file': '/etc/letsencrypt/live/' + ingress['serverName'] + '/privkey.pem',
        'relay_docker_nginx_fragment': ingress['ownershipRoot'] + '/nginx-conf/' + ns + '.conf',
        'relay_docker_nginx_projection_root': ingress['ownershipRoot'] + '/letsencrypt/' + ns + '/' + ingress['serverName'],
        'relay_tls_acme_hostname': ingress['serverName'],
        # SSH transport is never a DNS/ACME assertion. Old install-only inputs
        # remain valid; new issuance requires explicit public addresses.
        'relay_tls_public_addresses': ingress.get('publicAddresses', []),
        'relay_tls_acme_admitted_ip': '',
        'relay_nginx_manage': False, 'relay_docker_nginx_manage': False, 'relay_docker_nginx_service_enabled': False,
        'relay_review_check_name': e.get('reviewCheckName', 'chatgpt-review'),
        'relay_reviewer_repositories': sorted(set(e.get('reviewerRepositories', configured_repositories(c)))),
        'relay_compatibility_links': [{'alias': k, 'target': v} for k, v in e['compatibilityLinks'].items()],
    }
    tls = e.get('tls')
    result['relay_tls_allow_legacy_lineage'] = tls is None
    if tls is not None:
        pair = tls.get('source', {'certificateFile': config + '/certs/server-fullchain.pem',
                                 'privateKeyFile': config + '/certs/server-private-key.pem'})
        result['relay_nginx_server_certificate_file'] = pair['certificateFile']
        result['relay_nginx_server_private_key_file'] = pair['privateKeyFile']
    acme = (tls or {}).get('acme', {})
    result.update({
        'relay_tls_acme_method': acme.get('challenge', 'webroot'),
        'relay_tls_acme_email': acme.get('email', ''),
        'relay_tls_acme_webroot': acme.get('webroot', ''),
        'relay_tls_acme_configured': bool(acme),
        'relay_reviewer_credential_source_file': e.get('reviewerCredential', {}).get('sourceKeyFile', ''),
        'relay_writer_credential_source_file': e.get('writerCredential', {}).get('sourceKeyFile', ''),
        'relay_codex_credential_source_file': e.get('codexCredential', {}).get('sourceTokenFile', ''),
    })
    instance = e.get('instance')
    result['relay_reviewer_bind_port'] = instance['reviewerPort'] if instance else 8787
    result['relay_reviewer_relay_enabled'] = instance['publicationEnabled'] if instance else True
    if instance:
        # Legacy consumers retain their installed unit identities. Opting in
        # scopes every lifecycle participant, including disabled runner units.
        result.update({
            'relay_reviewer_service_name': ns + '-reviewer.service',
            'relay_reviewer_recovery_service_name': ns + '-reviewer-recovery.service',
            'relay_reviewer_recovery_timer_name': ns + '-reviewer-recovery.timer',
            'relay_runner_service_name': ns + '-runner.service',
            'relay_production_runner_service_name': ns + '-runner.service',
            'relay_general_runner_service_name': ns + '-general-runner.service',
            'relay_controller_service_name': ns + '-controller.service',
            'relay_superseded_proxy_service_name': ns + '-openai-mtls-proxy.service',
        })
    for suffix, kind in [('codex', 'codex'), ('writer', 'writer'), ('diagnostics', 'diagnostics'),
                         ('production-apply', 'production_local_apply'), ('owner-lifecycle', 'owner_lifecycle')]:
        result['relay_' + kind + '_sudoers_file'] = '/etc/sudoers.d/' + ns + '-' + suffix
    fields = {'owner':'owner_actor', 'baseBranch':'github_base_branch',
              'taskBranchPrefix':'task_branch_prefix', 'routingWorkflow':'routing_workflow',
              'recoveryWorkflow':'recovery_workflow', 'validationWorkflow':'validation_workflow'}
    for field, variable in fields.items():
        result['relay_' + variable] = consumer[field]
    if 'repositories' in consumer:
        result['relay_github_repositories'] = consumer['repositories']
    if 'workGroup' in consumer:
        result['relay_codex_launch_work_group'] = consumer['workGroup']
    if 'repositoryRuntimeUsers' in consumer:
        result['relay_repository_runtime_users'] = consumer['repositoryRuntimeUsers']
        result['relay_additional_runtime_users'] = sorted(set(consumer['repositoryRuntimeUsers'].values())
                                                        - {consumer['runtimeUser']})
    for role in ['writer', 'reviewer']:
        app = consumer[role + 'App']
        for key, suffix in [('slug','app_slug'),('appId','app_id'),('installationId','app_installation_id'),('expectedActor','expected_actor')]:
            result['relay_' + role + '_' + suffix] = app[key]
    for role in ['writer', 'remediation']:
        for key in ['name', 'email']:
            result['relay_' + role + '_commit_' + key] = consumer[role + 'Identity'][key]
    result['relay_default_model'] = consumer['defaultProfile']['cliModelId']
    if 'effort' in consumer['defaultProfile']:
        result['relay_default_effort'] = consumer['defaultProfile']['effort']
    mapping = {'workRoot':'dispatch_work_root', 'dispatch':'codex_dispatch_path', 'writerHelper':'writer_helper_path',
               'launcher':'codex_launcher_path', 'diagnosticsConfig':'diagnostics_config_path',
               'diagnosticsStore':'diagnostics_store_path', 'diagnosticsRoot':'diagnostics_root',
               'credentialEnv':'writer_credential_env_file', 'credentialKeyFile':'writer_credential_key_file', 'claimRoot':'writer_claim_root'}
    for field, variable in mapping.items():
        result['relay_' + variable] = consumer['paths'][field]
    result['relay_dispatch_state_root'] = str(PurePosixPath(consumer['paths']['attemptRoot']).parent)
    require(consumer['paths']['attemptRoot'].endswith('/attempts-v2'), 'paths.attemptRoot')
    if 'validationNames' in consumer:
        result['relay_validation_names'] = consumer['validationNames']
    if 'executionSlots' in consumer:
        result['relay_execution_slots'] = consumer['executionSlots']
        result['relay_execution_slot'] = 'primary'
        result['relay_execution_slot_isolation'] = True
        result['relay_general_runner_labels'] = e['runner']['labels'] + [execution_slot_label(c, consumer['executionSlots'][0])]
        result['relay_additional_execution_slots'] = [execution_slot_inputs(c, slot) for slot in consumer['executionSlots'][1:]]
    if 'generalRunnerPool' in consumer:
        from managed_pool import pool_contract
        result['relay_general_runner_pool'] = pool_contract(c)
        result['relay_general_runner_service_name'] = result['relay_general_runner_pool']['members'][0]['service']
    return result
