"""Version 1 deployment input. No playbooks, templates or backend variables in it."""
from pathlib import Path, PurePosixPath
import json
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
    raw = Path(path).read_text()
    require(len(raw) <= 65536, 'size')
    require(not re.search(r'{{|{%|PRIVATE KEY|(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]{20,}', raw), 'literal-data-only')
    config = json.loads(raw, object_pairs_hook=unique_object)
    validate(config, product_root)
    return config


def validate(c, product_root):
    require(object_keys(c, ['schemaVersion', 'source', 'target', 'consumer', 'environment']), 'keys')
    require(c['schemaVersion'] == 1, 'schemaVersion')
    source = c['source']
    require(object_keys(source, ['repository'], ['revision']), 'source')
    require(text(source['repository'], r'(?:git@github\.com:|https://github\.com/)[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?'), 'source.repository')
    require(selector(source.get('revision', 'main')), 'source.revision')
    target = c['target']
    require(object_keys(target, ['host', 'user', 'identityFile', 'identityFingerprint', 'hostFingerprint']), 'target')
    require(text(target['host'], r'[A-Za-z0-9][A-Za-z0-9.-]{0,252}'), 'target.host')
    require(target['user'] == 'root', 'target.user')
    require(absolute(target['identityFile'].replace('~/', '/home/operator/', 1)), 'target.identityFile')
    for key in ['identityFingerprint', 'hostFingerprint']:
        require(text(target[key], r'SHA256:[A-Za-z0-9+/]{43}'), 'target.' + key)
    # The runtime remains the authority for its existing schema; do not create
    # a second subtly different validator in the deployment implementation.
    validation = subprocess.run(['node', '--input-type=module', '-e',
        'import {validateConsumer} from "./consumer/consumer-config.mjs";'
        'let s="";for await(const b of process.stdin)s+=b;'
        'try{validateConsumer(JSON.parse(s))}catch{process.exit(1)}'],
        input=json.dumps(c['consumer']), text=True, cwd=product_root, capture_output=True)
    require(validation.returncode == 0, 'consumer')
    e = c['environment']
    require(object_keys(e, ['namespace', 'serviceUser', 'reviewerUser', 'codexWorkGroup', 'runner',
        'generalRunner', 'reviewerBind', 'ingress', 'localApply', 'codexTokenRequired', 'compatibilityLinks'],
        ['reviewCheckName', 'instance']), 'environment')
    for key in ['namespace', 'serviceUser', 'reviewerUser', 'codexWorkGroup']:
        require(text(e[key], r'[a-z][a-z0-9-]{0,30}') and e[key] != 'root', key)
    r, g = e['runner'], e['generalRunner']
    require(object_keys(r, ['user', 'name', 'scope', 'group', 'labels']), 'runner')
    require(object_keys(g, ['user', 'name']), 'generalRunner')
    for instance in [r, g]:
        require(text(instance['user'], r'[a-z][a-z0-9-]{0,30}') and instance['user'] != 'root', 'runner.user')
        require(text(instance['name'], r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}'), 'runner.name')
    require(r['scope'] == 'organization', 'runner.scope')
    require(text(r['group'], r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}'), 'runner.group')
    require(isinstance(r['labels'], list) and len(r['labels']) == 1
            and all(text(v, r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}') for v in r['labels']), 'runner.labels')
    users = [e['serviceUser'], e['reviewerUser'], r['user'], g['user'], c['consumer']['runtimeUser']]
    require(len(set(users)) == len(users), 'isolated-users')
    require(e['codexWorkGroup'] not in users, 'isolated-work-group')
    require(r['name'] != g['name'], 'isolated-runner-names')
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
                                 'protectedPaths', 'protectedServices']), 'ingress')
    for key in ['serverName', 'foreignServerName']:
        require(text(ingress[key], r'[A-Za-z0-9][A-Za-z0-9.-]{0,252}'), 'ingress.' + key)
    require(absolute(ingress['ownershipRoot']), 'ingress.ownershipRoot')
    require(isinstance(ingress['protectedPaths'], list) and all(absolute(p) for p in ingress['protectedPaths']), 'protectedPaths')
    require(isinstance(ingress['protectedServices'], list), 'protectedServices')
    for unit in [ingress['service'], *ingress['protectedServices']]:
        require(text(unit, r'[A-Za-z0-9_.-]+\.service'), 'service')
    for prefix in ['/opt/', '/etc/', '/var/lib/', '/var/log/', '/run/']:
        owned = prefix + e['namespace']
        for protected in [ingress['ownershipRoot'], *ingress['protectedPaths']]:
            require(not (owned == protected or owned.startswith(protected + '/') or protected.startswith(owned + '/')), 'path-overlap')
    require(object_keys(e['localApply'], ['configPath']) and relative(e['localApply']['configPath']), 'localApply')
    require(type(e['codexTokenRequired']) is bool, 'codexTokenRequired')
    require(text(e.get('reviewCheckName', 'chatgpt-review'), r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}'), 'reviewCheckName')
    links = e['compatibilityLinks']
    require(isinstance(links, dict) and len(links) <= 8, 'compatibilityLinks')
    for alias, destination in links.items():
        require(relative(alias) and '/' in alias and alias.split('/')[0] not in
                ['controller', 'consumer', 'contracts', 'runtime', 'reviewer', 'deploy'], 'compatibilityLinks.alias')
        require(destination in ['controller', 'consumer', 'contracts', 'runtime', 'reviewer'], 'compatibilityLinks.destination')


def compile_inputs(c):
    """Private adapter. All backend paths and lifecycle mechanics are Relay-owned."""
    e, consumer, target = c['environment'], c['consumer'], c['target']
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
        'relay_general_runner_name': g['name'], 'relay_general_runner_user': g['user'],
        'relay_runner_name': r['name'], 'relay_runner_user': r['user'], 'relay_runner_group': r['user'],
        'relay_runner_registration_scope': r['scope'], 'relay_runner_registration_group': r['group'],
        'relay_runner_labels': r['labels'], 'relay_runner_repository': consumer['repository'],
        'relay_runner_package_cache_root': '/var/cache/' + ns,
        'relay_dispatch_user': g['user'], 'relay_dispatch_group': g['user'],
        'relay_codex_user': consumer['runtimeUser'], 'relay_codex_group': consumer['runtimeUser'],
        'relay_codex_work_group': e['codexWorkGroup'], 'relay_codex_token_required': e['codexTokenRequired'],
        'relay_production_local_apply_checkout_root': state + '/runner/work/' + '/'.join([consumer['repository'].split('/')[1]] * 2),
        'relay_consumer_deployment_config_relative': e['localApply']['configPath'],
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
        'relay_tls_acme_hostname': ingress['serverName'], 'relay_tls_acme_admitted_ip': target['host'],
        'relay_nginx_manage': False, 'relay_docker_nginx_manage': False, 'relay_docker_nginx_service_enabled': False,
        'relay_review_check_name': e.get('reviewCheckName', 'chatgpt-review'),
        'relay_compatibility_links': [{'alias': k, 'target': v} for k, v in e['compatibilityLinks'].items()],
    }
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
                         ('production-apply', 'production_local_apply')]:
        result['relay_' + kind + '_sudoers_file'] = '/etc/sudoers.d/' + ns + '-' + suffix
    fields = {'repository':'github_repository', 'owner':'owner_actor', 'baseBranch':'github_base_branch',
              'taskBranchPrefix':'task_branch_prefix', 'routingWorkflow':'routing_workflow',
              'recoveryWorkflow':'recovery_workflow', 'validationWorkflow':'validation_workflow'}
    for field, variable in fields.items():
        result['relay_' + variable] = consumer[field]
    for role in ['writer', 'reviewer']:
        app = consumer[role + 'App']
        for key, suffix in [('slug','app_slug'),('appId','app_id'),('installationId','app_installation_id'),('expectedActor','expected_actor')]:
            result['relay_' + role + '_' + suffix] = app[key]
    for role in ['writer', 'remediation']:
        for key in ['name', 'email']:
            result['relay_' + role + '_commit_' + key] = consumer[role + 'Identity'][key]
    result['relay_default_model'] = consumer['defaultProfile']['cliModelId']
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
    return result
