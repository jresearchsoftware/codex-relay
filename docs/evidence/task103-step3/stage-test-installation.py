#!/usr/bin/env python3
"""Prepare, never execute, a scoped Task 103 TEST installation bundle.

This is qualification glue, not another production deployment interface. It
exports one exact Git object and reuses its roles, assertions and templates.
The generated play requires stopped TEST services and independently checked
idle admission. It does not register runners, create Task admissions, activate
services, alter ingress, install global packages or call GitHub.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import yaml

TARGETS = {'codex-relay-test': 'jresearchsoftware/codex-relay-testbed',
           'codex-relay-test-two': 'jresearchsoftware/codex-relay-testbed-2'}
TOOLS = '/opt/codex-relay-test'


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_module(path, name):
    specification = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def task(name, module, values, **extra):
    return {'name': name, 'ansible.builtin.' + module: values, **extra}


def prepare(args):
    source = args.source_root.resolve()
    sys.path.insert(0, str(source / 'deploy'))
    config_module = load_module(source / 'deploy/config.py', 'task103_deployment_config')
    deployment = load_module(source / 'deploy/relay-deploy.py', 'task103_deployment_entrypoint')
    identity = deployment.source_identity(source)
    require(identity['revision'] == args.revision, 'candidate-head-mismatch')
    require(re.fullmatch('[0-9a-f]{40}', args.consumer_revision or ''), 'exact-consumer-main-required')
    require(args.cargo_version.startswith('cargo 1.90.0 '), 'actual-cargo-1.90-build-evidence-required')
    configuration = config_module.load(args.config, source)
    namespace = configuration['environment']['namespace']
    require(namespace in TARGETS and configuration['consumer']['repository'] == TARGETS[namespace], 'TEST-target-only')
    require(configuration['target']['host'] == '195.201.83.241', 'TEST-host-binding')
    prefix = 'relay-test' if namespace == 'codex-relay-test' else 'relay-test-two'
    slots = configuration['consumer'].get('executionSlots', [])
    require([slot['id'] for slot in slots] == ['primary', 'second'], 'exact-primary-second-topology')
    names = [configuration['environment'][key] for key in ['serviceUser', 'reviewerUser']]
    names.append(configuration['environment']['runner']['user'])
    names += [slot[key] for slot in slots for key in ['runnerUser', 'runtimeUser', 'workGroup']]
    require(all(name.startswith(prefix) for name in names), 'TEST-identities-only')
    partial = None
    if args.resume_partial_proof:
        partial = json.loads(args.resume_partial_proof.read_text())
        require(set(partial) == {'namespace', 'revision', 'originalArchiveRevision', 'originalConsumerSha256',
                'originalConsumerDigest', 'manifestSha256', 'retainedStatusSha256', 'deploymentConfigSha256'},
                'exact-own-partial-proof-required')
        require(partial['namespace'] == namespace and re.fullmatch('[0-9a-f]{40}', partial['revision']),
                'own-partial-namespace-revision')
        require(re.fullmatch('[0-9a-f]{40}', partial['originalArchiveRevision']), 'original-own-archive-revision')
        require(all(re.fullmatch('[0-9a-f]{64}', partial[key]) for key in partial
                    if key not in ['namespace', 'revision', 'originalArchiveRevision']), 'own-partial-proof-digests')
    require(args.reviewer_binary.is_file() and not args.reviewer_binary.is_symlink(), 'regular-Reviewer-build-required')
    output = args.output.absolute()
    require(not output.exists(), 'new-bundle-directory-required')
    output.mkdir(parents=True, mode=0o700)
    backend = output / 'ansible'
    shutil.copytree(source / 'deploy/ansible', backend,
                    ignore=shutil.ignore_patterns('tests', '__pycache__', '.pytest_cache'))
    shutil.copyfile(source / 'deploy/execution_topology.py', output / 'execution_topology.py')
    assets = output / 'assets'
    assets.mkdir(mode=0o700)
    subprocess.run(['git', '-C', str(source), 'archive', '--format=tar',
                    '--output=' + str(assets / 'source.tar'), args.revision], check=True)
    shutil.copyfile(args.reviewer_binary, assets / 'reviewer-mcp-http')
    (assets / 'reviewer-mcp-http').chmod(0o750)
    values = config_module.compile_inputs(configuration)
    snapshot = json.dumps(configuration, sort_keys=True, separators=(',', ':'), ensure_ascii=False) + '\n'
    values.update(relay_source_identity=identity, relay_requested_revision=args.revision,
                  relay_consumer_revision=args.consumer_revision, relay_deployment_profile='production',
                  relay_production_exact_head=args.revision, relay_production_operation_target_head=args.revision,
                  relay_production_operation_phase='apply', relay_manage_base_packages=False,
                  relay_service_state_management='preserve', relay_service_enabled=False,
                  relay_service_activation_authorized=False, relay_runner_service_state_management='preserve',
                  relay_runner_service_enabled=False, relay_runner_registration_enabled=False,
                  relay_runner_registration_authorized=False, relay_runner_registration_completed=False,
                  relay_production_defer_lifecycle=True, relay_upgrade_lifecycle_managed=True,
                  relay_upgrade_lifecycle_previous_active={'manualOutcome': {'active': False}},
                  relay_codex_credential_source_file='/root/codex-relay-test-input/codex-access-token',
                  relay_writer_credential_source_file='/root/codex-relay-test-input/writer-app.pem',
                  relay_reviewer_credential_source_file='/root/codex-relay-test-input/reviewer-app.pem',
                  relay_installed_deployment_config=snapshot,
                  relay_installed_deployment_config_sha256=hashlib.sha256(snapshot.encode()).hexdigest(),
                  relay_source_archive='{{ playbook_dir }}/../assets/source.tar')
    (output / 'configuration.json').write_text(snapshot)
    (backend / 'stage-vars.json').write_text(json.dumps(values, indent=2) + '\n')
    adaptations = []
    # Root helpers must use the private TEST Node even when they leave a service
    # mount namespace. The JS source and every sandbox/security gate stay exact.
    for path in sorted(backend.glob('roles/**/templates/*')):
        if not path.is_file():
            continue
        raw = path.read_text()
        if '/usr/bin/node' in raw:
            before = digest(path)
            path.write_text(raw.replace('/usr/bin/node', '{{ relay_install_root }}/node22/bin/node'))
            adaptations.append({'path': str(path.relative_to(backend)), 'change': 'TEST-private-Node22-path',
                                'sourceSha256': before, 'stagedSha256': digest(path)})
    # Preserve the static fixed-interpreter assertion in the installation
    # binding check, matching the same documented private TEST path exactly.
    binding_check = backend / 'roles/relay_codex_runtime/tasks/production-launcher-validation.yml'
    binding_check.write_text(binding_check.read_text().replace(
        "search('exec /usr/bin/node --experimental-default-type=module')",
        "search('exec ' ~ relay_install_root ~ '/node22/bin/node --experimental-default-type=module')"))
    adaptations.append({'path': str(binding_check.relative_to(backend)),
                        'change': 'same-fixed-interpreter-assertion-for-TEST-Node22'})
    # This timer can start Reviewer later. Keep the unit and every surrounding
    # readiness/activation assertion, and defer solely its automatic activation.
    runtime_main = backend / 'roles/relay_runtime/tasks/main.yml'
    tasks = yaml.safe_load(runtime_main.read_text())
    for item in tasks:
        if item['name'] == 'Keep the Reviewer recovery timer available without activating Reviewer':
            item['when'].append(False)
            adaptations.append({'path': str(runtime_main.relative_to(backend)),
                                'change': 'defer-automatic-recovery-timer-start'})
    runtime_main.write_text(yaml.safe_dump(tasks, sort_keys=False))
    # Ordinary public apply creates this lock before the roles. The scoped
    # TEST play creates only the same idle mutex inode, with no operation record.
    tasks = yaml.safe_load(runtime_main.read_text())
    position = next(i for i, item in enumerate(tasks) if item['name'] ==
                    'Record the preserved Reviewer lifecycle state') + 1
    tasks.insert(position, task('Create or verify only the dedicated idle TEST operation mutex', 'command', {
        'argv': ['/usr/bin/python3', '-I', '-c',
                 "import os,stat,sys; p=sys.argv[1]; parent=os.stat(os.path.dirname(p),follow_symlinks=False); assert stat.S_ISDIR(parent.st_mode) and parent.st_uid==0 and not parent.st_mode&0o022; exists=os.path.lexists(p); flags=os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK; fd=os.open(p,flags) if exists else os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644); os.fchmod(fd,0o644) if not exists else None; s=os.fstat(fd); assert stat.S_ISREG(s.st_mode) and s.st_uid==s.st_gid==0 and s.st_nlink==1 and stat.S_IMODE(s.st_mode)==0o644; os.close(fd)",
                 '{{ relay_production_operation_lock_path }}']}, changed_when=False))
    runtime_main.write_text(yaml.safe_dump(tasks, sort_keys=False))
    # Initialize only lifecycle gate state after a reviewed idle TEST reset.
    # This source operation does not allocate Step or create execution admission.
    writer_tasks = backend / 'roles/relay_controller/tasks/writer-entrypoint.yml'
    tasks = yaml.safe_load(writer_tasks.read_text())
    for item in tasks:
        if item['name'] == 'Initialize missing lifecycle admission state without reopening retained state':
            item['when'] = ['not ansible_check_mode | bool']
            adaptations.append({'path': str(writer_tasks.relative_to(backend)),
                                'change': 'initialize-missing-TEST-lifecycle-gate-before-status'})
    writer_tasks.write_text(yaml.safe_dump(tasks, sort_keys=False))
    # Keep source/reuse/protected-snapshot assertions; replace only the local
    # Reviewer build action with the parent's exact already-built artifact.
    artifact_main = backend / 'roles/relay_artifacts/tasks/main.yml'
    original = yaml.safe_load(artifact_main.read_text())
    filtered = []
    omitted = {'Build the locked reviewed Rust Reviewer release artifact',
               'Record the built Reviewer toolchain identity',
               'Install the built Reviewer executable into the release contract',
               'Reuse the verified Reviewer executable without rebuilding it',
               'Record the verified reused Reviewer toolchain identity'}
    for item in original:
        if item['name'] in omitted:
            continue
        if item['name'] == 'Read the deployed Reviewer executable digest':
            filtered.extend([
                task('Stage the exact parent-built TEST Reviewer artifact', 'copy', {
                    'src': '{{ playbook_dir }}/../assets/reviewer-mcp-http',
                    'dest': '{{ relay_release_path }}/bin/reviewer-mcp-http', 'owner': 'root',
                    'group': '{{ relay_reviewer_group }}', 'mode': '0750'}),
                task('Record honest local locked-build provenance', 'set_fact', {
                    'relay_reviewer_cargo_version': args.cargo_version,
                    'relay_reviewer_artifact_provenance': 'task103-local-locked-build',
                    'relay_reviewer_reuse_source_release': 'none', 'relay_reviewer_reuse_source_digest': 'none'})])
        if item['name'] == 'Record the deployed artifact manifest':
            # set_fact from source identity has higher precedence than task
            # vars. Replace only the artifact's build provenance explicitly;
            # keep the actual source-pinned runtime toolchain tasks untouched.
            filtered.append(task('Bind manifest only to the observed local Reviewer build provenance', 'set_fact', {
                'relay_rust_toolchain_archive_sha256': 'UNAVAILABLE',
                'relay_reviewer_build_contract_sha256': hashlib.sha256(
                    b'cargo-build=--release,--locked;toolchain=local-1.90.0;archive=UNAVAILABLE').hexdigest()}))
        filtered.append(item)
    artifact_main.write_text(yaml.safe_dump(filtered, sort_keys=False))
    adaptations.append({'path': str(artifact_main.relative_to(backend)),
                        'change': 'exact-parent-locked-build-artifact;unobserved-archive-provenance-UNAVAILABLE'})
    # The normal role creates the exact runtime UID and private token target
    # first. Stage the established token with the unchanged protected helper
    # before its original authenticated-runtime assertions, without env bytes.
    codex_main = backend / 'roles/relay_codex_runtime/tasks/main.yml'
    codex_tasks = yaml.safe_load(codex_main.read_text())
    provision = next(i for i, item in enumerate(codex_tasks)
                     if item['name'] == 'Provision a supplied Codex access token into the protected destination')
    codex_tasks.insert(provision, task('Stage the existing TEST token with the exact source protected helper', 'command', {
        'argv': ['/usr/bin/python3', '{{ playbook_dir }}/tools/codex-credential-stage.py',
                 '--source', '{{ relay_codex_credential_source_file }}',
                 '--destination', '{{ relay_codex_access_token_file }}',
                 '--config-root', '{{ relay_config_root }}', '--user', '{{ relay_codex_user }}',
                 '--group', '{{ relay_codex_group }}', '--lock-file', '{{ relay_production_operation_lock_path }}',
                 '--operation-record', '{{ relay_production_operation_record_path }}',
                 '--manifest', '{{ relay_install_root }}/current/artifact-manifest.json',
                 '--exact-head', '{{ relay_production_exact_head }}']},
        no_log=True, when='not ansible_check_mode | bool'))
    codex_main.write_text(yaml.safe_dump(codex_tasks, sort_keys=False))
    adaptations.append({'path': str(codex_main.relative_to(backend)),
                        'change': 'insert-unchanged-protected-token-helper-before-original-token-assertions'})
    # Safety preflight/archival is separate from source gates, never a substitute.
    guard = output / 'guard-idle-test.py'
    guard.write_text(IDLE_GUARD)
    fixed = {'namespace': namespace, 'revision': args.revision,
             'consumer': configuration['consumer'], 'claimRoot': configuration['consumer']['paths']['claimRoot'],
             'deploymentConfigSha256': hashlib.sha256(snapshot.encode()).hexdigest(), 'resumePartial': partial}
    (output / 'guard-binding.json').write_text(json.dumps(fixed) + '\n')
    pre_tasks = [task('Require idle stopped isolated TEST resources and preserve previous local state', 'command', {
        'argv': ['/usr/bin/python3', '-I', '{{ playbook_dir }}/../guard-idle-test.py',
                 '{{ playbook_dir }}/../guard-binding.json']}),
        {'name': 'Prove numeric isolation before account reconciliation',
         'ansible.builtin.include_tasks': 'tasks/execution-slot-topology.yml',
         'vars': {'relay_slot_topology_preflight': True}},
        {'name': 'Resolve the immutable source identity before rendering runtime contracts',
         'ansible.builtin.include_tasks': 'roles/relay_artifacts/tasks/resolve-identities.yml'},
        {'name': 'Discover the admitted shared Docker gateway through the unchanged read-only source role',
         'ansible.builtin.include_role': {'name': 'relay_docker_network_gateway'},
         'when': "relay_reviewer_bind_mode == 'nexus_gateway'"},
        {'name': 'Install the fixed TEST local-apply and owner-lifecycle boundaries',
         'ansible.builtin.include_role': {'name': 'relay_runner', 'tasks_from': 'production-local-apply.yml'}}]
    post_tasks = [
        {'name': 'Install the additional fixed slot without activation or registration',
         'ansible.builtin.include_tasks': 'tasks/execution-slot.yml',
         'loop': '{{ relay_additional_execution_slots }}', 'loop_control': {'loop_var': 'relay_slot_inputs'}},
        {'name': 'Reconcile the primary general instance without activation',
         'ansible.builtin.include_tasks': 'tasks/production-general-runner.yml'},
        {'name': 'Preserve the separate production TEST runner registration', 'ansible.builtin.include_role': {'name': 'relay_runner'}},
        {'name': 'Verify complete fixed slot topology', 'ansible.builtin.include_tasks': 'tasks/execution-slot-topology.yml'}]
    # Reuse the actual secret-safe credential tasks and their helper guards.
    # Public lifecycle preflight is optional in disposable TEST; exact installed
    # binding, namespace lock, atomic no-replace and metadata assertions remain
    # enforced by each unchanged source helper.
    for role in ['reviewer', 'writer']:
        credential_play = yaml.safe_load((backend / ('relay-' + role + '-credentials.yml')).read_text())[0]
        post_tasks.extend(credential_play['tasks'])
    post_tasks.extend([
        task('Read the exact installed non-secret candidate manifest for source binding assertions', 'slurp', {
            'src': '{{ relay_install_root }}/current/artifact-manifest.json'}, register='task103_final_manifest'),
        task('Bind original final launcher assertions to the installed candidate manifest', 'set_fact', {
            'relay_production_final_manifest': '{{ task103_final_manifest.content | b64decode | from_json }}'}),
        {'name': 'Run every original final launcher binding assertion with its fixed TEST interpreter',
         'ansible.builtin.include_role': {'name': 'relay_codex_runtime', 'tasks_from': 'production-launcher-validation.yml'}}])
    unit_names = [namespace + suffix for suffix in ['-reviewer.service', '-reviewer-recovery.service',
        '-runner.service', '-general-runner.service', '-slot-second-runner.service', '-relay-manual-outcome@.service']]
    post_tasks.extend([
        task('Create only dedicated TEST service tool overlay directories', 'file', {
            'path': '/etc/systemd/system/{{ item }}.d', 'state': 'directory',
            'owner': 'root', 'group': 'root', 'mode': '0755'}, loop=unit_names),
        task('Expose qualified private TEST tools inside only TEST service namespaces', 'copy', {
            'content': '[Service]\nBindReadOnlyPaths={{ relay_install_root }}/node22/bin/node:/usr/bin/node\nBindReadOnlyPaths={{ relay_install_root }}/tools/bwrap:/usr/bin/bwrap\n',
            'dest': '/etc/systemd/system/{{ item }}.d/task103-qualification-tools.conf',
            'owner': 'root', 'group': 'root', 'mode': '0644'}, loop=unit_names),
        task('Reload installed dedicated TEST units without activating services', 'systemd', {'daemon_reload': True})])
    play = [{'name': 'Task103 scoped TEST installation; activation is separate', 'hosts': '195.201.83.241',
             'connection': 'local', 'become': False, 'gather_facts': True,
             'vars_files': ['group_vars/all.yml', 'stage-vars.json'], 'pre_tasks': pre_tasks,
             'roles': ['relay_base', 'relay_runtime', 'relay_artifacts', 'relay_reviewer_bind', 'relay_codex_runtime', 'relay_controller'],
             'post_tasks': post_tasks}]
    (backend / 'stage.yml').write_text(yaml.safe_dump(play, sort_keys=False))
    plan = {'sourceRevision': args.revision, 'consumerRevision': args.consumer_revision,
            'namespace': namespace, 'repository': TARGETS[namespace],
            'reviewerBinarySha256': digest(args.reviewer_binary), 'cargoVersion': args.cargo_version,
            'reviewerBuildFlags': ['--release', '--locked'], 'localBuildArchiveSha256': 'UNAVAILABLE',
            'resumePartial': partial,
            'adaptations': adaptations, 'authority': 'Task103 admitted isolated TEST; preparation only',
            'prerequisites': ['Stop only this TEST Reviewer, recovery timer, manual Outcome socket and runner services.',
                'Stage the two qualified private tools under /opt/' + namespace + '/node22 and /opt/' + namespace + '/tools/bwrap.',
                'Run the play in the proved private systemd Node22/bwrap mount namespace.',
                'Existing /root/codex-relay-test-input secret files must retain root-only source metadata; helpers stage without logging bytes.'],
            'execution': ['ansible-playbook', '-i', '195.201.83.241,', 'ansible/stage.yml'],
            'limitations': ['TEST adaptation does not qualify ordinary public bootstrap/upgrade/rollback.',
                'Local Reviewer build does not prove checksum-pinned Ansible archive use; automatic reusable-build admission remains fail-closed.',
                'No native registration labels, runner ACLs, model overlap, terminal Outcomes or independent acceptance are proved.']}
    # Record complete source/template adaptations, including YAML reformatting.
    # The exact Git archive is unchanged; installed-template deltas stay explicit.
    reasons = {item['path']: item['change'] for item in adaptations}
    plan['adaptations'] = []
    for path in sorted(backend.rglob('*')):
        original = source / 'deploy/ansible' / path.relative_to(backend)
        if path.is_file() and original.is_file() and digest(path) != digest(original):
            plan['adaptations'].append({'path': str(path.relative_to(backend)),
                'change': reasons.get(str(path.relative_to(backend)), 'TEST-template-adaptation'),
                'sourceSha256': digest(original), 'stagedSha256': digest(path)})
    plan['sourceArchiveSha256'] = digest(assets / 'source.tar')
    (output / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    for path in [output / 'configuration.json', output / 'guard-binding.json', backend / 'stage-vars.json']:
        path.chmod(0o600)
    print(json.dumps({'prepared': str(output), 'sourceRevision': args.revision, 'namespace': namespace}))


IDLE_GUARD = r'''import fcntl,hashlib,json,os,re,shutil,stat,subprocess,sys
from pathlib import Path
def protected(path, kind, *, root_group=True, mode=None):
    for parent in path.parents:
        info=parent.lstat(); assert stat.S_ISDIR(info.st_mode) and info.st_uid==0 and not info.st_mode&0o022
    info=path.lstat(); assert kind(info.st_mode) and info.st_uid==0 and (stat.S_ISLNK(info.st_mode) or not info.st_mode&0o022)
    assert not root_group or info.st_gid==0
    assert mode is None or stat.S_IMODE(info.st_mode)==mode
    if stat.S_ISREG(info.st_mode): assert info.st_nlink==1
    return (info.st_dev,info.st_ino,info.st_mode,info.st_uid,info.st_gid)

def own_partial(binding, install, config, state, claim):
    # Only this explicit TEST stage's artifact-staged/consumer-not-reconciled
    # interruption is recoverable here. No status is fabricated or initialized;
    # the original archive and native bodies remain untouched.
    proof=binding['resumePartial']; old=proof['revision']
    assert proof['namespace']==binding['namespace'] and re.fullmatch('[0-9a-f]{40}',old)
    assert set(proof)=={'namespace','revision','originalArchiveRevision','originalConsumerSha256','originalConsumerDigest','manifestSha256','retainedStatusSha256','deploymentConfigSha256'}
    assert re.fullmatch('[0-9a-f]{40}',proof['originalArchiveRevision'])
    assert all(re.fullmatch('[0-9a-f]{64}',proof[k]) for k in proof if k not in ['namespace','revision','originalArchiveRevision'])
    # The first idle archive survives later bounded install corrections. It is
    # independent from the most recently staged manifest/revision above.
    archive=state/'task103-step3-retained-local-state'/('before-'+proof['originalArchiveRevision'])
    protected(archive,stat.S_ISDIR,mode=0o700)
    protected(archive/'claims',stat.S_ISDIR,mode=0o700)
    for filename,key in [('consumer.json','originalConsumerSha256'),('idle-status.json','retainedStatusSha256')]:
        path=archive/filename; protected(path,stat.S_ISREG,mode=0o600)
        assert hashlib.sha256(path.read_bytes()).hexdigest()==proof[key]
    protected(config,stat.S_ISREG)
    assert hashlib.sha256(config.read_bytes()).hexdigest()==proof['originalConsumerSha256']
    previous=json.loads(config.read_text()); assert previous['paths']['claimRoot']==str(claim)
    status=json.loads((archive/'idle-status.json').read_text())
    assert status['active']==[] and status['unknown']==[] and status['consumerDigest']==proof['originalConsumerDigest']
    assert status['phase']=='open' and status['operationId'] is None and status['target'] is None
    binding_stamp=protected(install/'current',stat.S_ISLNK)
    release=install/'releases'/old
    assert os.readlink(install/'current')==str(release)
    protected(release,stat.S_ISDIR,root_group=False)
    manifest=release/'artifact-manifest.json'; protected(manifest,stat.S_ISREG,root_group=False)
    assert hashlib.sha256(manifest.read_bytes()).hexdigest()==proof['manifestSha256']
    data=json.loads(manifest.read_text())
    assert data['schemaVersion']=='1.0' and data['commit']==data['installedRevision']==data['resolvedRevision']==old
    snapshot=release/'deployment-config.json'; protected(snapshot,stat.S_ISREG,mode=0o600)
    assert hashlib.sha256(snapshot.read_bytes()).hexdigest()==proof['deploymentConfigSha256']==data['deploymentConfigSha256']
    previous_deployment=json.loads(snapshot.read_text())
    assert previous_deployment['source']['revision']==old and previous_deployment['environment']['namespace']==binding['namespace']
    # A corrective commit changes the source revision. Every other frozen
    # deployment input must remain the same for this narrowly bound recovery.
    previous_deployment['source']['revision']=binding['revision']
    updated=json.dumps(previous_deployment,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n'
    assert hashlib.sha256(updated.encode()).hexdigest()==binding['deploymentConfigSha256']
    assert data['reviewerArtifactProvenance']=='task103-local-locked-build'
    binary=release/'bin/reviewer-mcp-http'; protected(binary,stat.S_ISREG,root_group=False)
    assert hashlib.sha256(binary.read_bytes()).hexdigest()==data['reviewerBinarySha256']
    claim_stamp=protected(claim,stat.S_ISDIR,mode=0o700)
    names={p.name for p in claim.iterdir()}; assert names in [set(),{'publication-v2.lock'}]
    lock=None
    try:
        if names:
            protected(claim/'publication-v2.lock',stat.S_ISREG)
            lock=os.open(claim/'publication-v2.lock',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert protected(claim,stat.S_ISDIR,mode=0o700)==claim_stamp and {p.name for p in claim.iterdir()}==names
        assert protected(install/'current',stat.S_ISLNK)==binding_stamp
    finally:
        if lock is not None: os.close(lock)
    print('TEST_OWN_PARTIAL_STAGE_VERIFIED='+old+';original-archive=preserved;execution-state=empty')

assert os.geteuid()==0
binding=json.loads(Path(sys.argv[1]).read_text()); ns=binding['namespace']
assert ns in ['codex-relay-test','codex-relay-test-two']
install=Path('/opt')/ns; config=Path('/etc')/ns/'consumer.json'; state=Path('/var/lib')/ns
units=[ns+x for x in ['.service','-reviewer.service','-reviewer-recovery.timer','-runner.service','-general-runner.service','-slot-second-runner.service','-relay-manual-outcome.socket']]
for unit in units:
    result=subprocess.run(['/bin/systemctl','show',unit,'--property=ActiveState','--value'],text=True,capture_output=True)
    assert result.stdout.strip() in ['inactive','failed',''], 'TEST service must be stopped: '+unit
if not config.exists():
    assert not config.is_symlink() and not (install/'current').exists(), 'unexpected partial TEST state'
    sys.exit(0)
meta=config.lstat(); assert stat.S_ISREG(meta.st_mode) and meta.st_uid==0 and meta.st_nlink==1 and not meta.st_mode&0o022
previous=json.loads(config.read_text()); claim=Path(binding['claimRoot'])
assert previous['paths']['claimRoot']==str(claim) and claim.is_relative_to(state)
assert claim.is_dir() and not claim.is_symlink() and claim.lstat().st_uid==0
if binding.get('resumePartial') is not None:
    own_partial(binding,install,config,state,claim)
    sys.exit(0)
lock=os.open(claim/'publication-v2.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
info=os.fstat(lock); assert stat.S_ISREG(info.st_mode) and info.st_uid==info.st_gid==0 and info.st_nlink==1 and not info.st_mode&0o022
fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
current=(install/'current').resolve(strict=True); assert current.parent==install/'releases' and re.fullmatch('[0-9a-f]{40}',current.name)
node=install/'node22/bin/node'; assert node.is_file() and not node.is_symlink()
env={'RELAY_CONSUMER_CONFIG':str(config),'PATH':'/usr/bin:/bin','HOME':'/root','LANG':'C','LC_ALL':'C'}
read=subprocess.run([str(node),str(current/'reviewed-source/controller/src/admission-cli.mjs'),'status'],env=env,text=True,capture_output=True,timeout=30)
assert read.returncode==0, 'original admission status unavailable; retain state'
status=json.loads(read.stdout); assert status['active']==[] and status['unknown']==[], 'original attempt is not idle'
if previous==binding['consumer']: os.close(lock); sys.exit(0)
archive_parent=state/'task103-step3-retained-local-state'
archive_parent.mkdir(mode=0o700,exist_ok=True)
info=archive_parent.lstat(); assert stat.S_ISDIR(info.st_mode) and info.st_uid==info.st_gid==0 and stat.S_IMODE(info.st_mode)==0o700
archive=archive_parent/('before-'+binding['revision']); archive.mkdir(mode=0o700,exist_ok=False)
shutil.copyfile(config,archive/'consumer.json'); (archive/'consumer.json').chmod(0o600)
for filename in ['artifact-manifest.json','deployment-config.json']:
    origin=current/filename
    if origin.is_file(): shutil.copyfile(origin,archive/filename); (archive/filename).chmod(0o600)
(archive/'idle-status.json').write_text(json.dumps(status)); (archive/'idle-status.json').chmod(0o600)
os.rename(claim,archive/'claims'); claim.mkdir(mode=0o700)
os.close(lock)
print('TEST_IDLE_LOCAL_STATE_PRESERVED='+str(archive))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--consumer-revision', required=True)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--reviewer-binary', required=True, type=Path)
    parser.add_argument('--cargo-version', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--resume-partial-proof', type=Path,
                        help='Explicit root-read-back hashes for this own artifact-staged TEST interruption only')
    args = parser.parse_args()
    require(re.fullmatch('[0-9a-f]{40}', args.revision or ''), 'exact-candidate-required')
    prepare(args)


if __name__ == '__main__':
    main()
