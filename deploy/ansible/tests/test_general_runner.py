"""Two-instance provisioning and scheduling/authority regressions for Task 263."""

from pathlib import Path
import subprocess
import re
import unittest

from jinja2 import Environment, StrictUndefined, UndefinedError
import yaml


def linux_bash_available():
    import os,shutil
    return os.name != "nt" and shutil.which("bash") is not None

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
ROLE = ROOT / 'roles/relay_runner'
ENV = Environment(undefined=StrictUndefined)
ENV.tests['match'] = lambda value, pattern: re.match(pattern, value) is not None
ENV.filters['bool'] = lambda value: value is True or str(value).lower() in ('true', '1', 'yes')


def instance(general=False, scope='repository'):
    values = yaml.safe_load((ROOT / 'group_vars/all.yml').read_text(encoding='utf-8'))
    values.update(relay_deployment_profile='production', relay_runner_name='relay-production-relay')
    if general:
        values.update(relay_general_runner_registration_scope=scope,
                      relay_general_runner_registration_group='relay-general-restricted' if scope == 'organization' else '')
        values.update(yaml.safe_load((ROOT / 'vars/general-runner.yml').read_text(encoding='utf-8')))
    # Resolve only defined defaults, as Ansible does when a template uses them.
    # Unrelated release/build vars need not be supplied to test runner templates.
    for _ in range(12):
        for key, value in values.items():
            if isinstance(value, str) and '{{' in value:
                try:
                    values[key] = ENV.from_string(value).render(values)
                except UndefinedError:
                    pass
    return values


def named_task(name):
    tasks = yaml.safe_load((ROLE / 'tasks/main.yml').read_text(encoding='utf-8'))
    return next(task for task in tasks if task['name'] == name)


def assertions_pass(task, values):
    return all(ENV.compile_expression(expression)(**values)
               for expression in task['ansible.builtin.assert']['that'])


class GeneralRunnerTests(unittest.TestCase):
    def test_both_instances_render_without_local_or_registration_collision(self):
        production, general = instance(), instance(True)
        for key in ('relay_runner_user', 'relay_runner_group', 'relay_runner_root',
                    'relay_runner_work_root', 'relay_runner_home', 'relay_runner_service_name',
                    'relay_runner_service_unit_path', 'relay_runner_registration_helper_path',
                    'relay_runner_registration_marker', 'relay_runner_credentials_marker'):
            with self.subTest(key=key):
                self.assertNotEqual(production[key], general[key])
                self.assertNotIn('{{', general[key])
        self.assertEqual(production['relay_runner_user'], 'relay-runner')
        self.assertEqual(production['relay_runner_root'], '/opt/codex-relay/runner')
        self.assertEqual(production['relay_runner_work_root'], '/var/lib/codex-relay/runner/work')
        self.assertEqual(production['relay_runner_service_name'], 'relay-runner.service')
        targets = []
        for values in (production, general):
            for name in ('Install owner-mediated runner registration helper', 'Install runner service structure'):
                spec = named_task(name)['ansible.builtin.template']
                targets.append(ENV.from_string(spec['dest']).render(values))
            unit = ENV.from_string((ROLE / 'templates/relay-runner.service.j2').read_text()).render(values)
            self.assertIn(f"User={values['relay_runner_user']}\n", unit)
            self.assertIn('ProtectSystem=strict', unit)
            self.assertIn('ProtectHome=true', unit)
            self.assertIn('PrivateTmp=true', unit)
            self.assertIn('NoNewPrivileges=false', unit)
            self.assertIn('ExecStartPre=+/opt/codex-relay/relay-reviewer-readiness', unit)
            self.assertNotIn('/production-apply', unit)
            self.assertNotIn('{{', unit)
        self.assertEqual(len(set(targets)), 4)

    def test_scope_depends_on_the_instance_even_on_the_same_production_host(self):
        contract = named_task('Require the pinned runner package and identity contract')
        for general, scope in [(False, 'organization'), (True, 'repository'), (True, 'organization')]:
            values = instance(general, scope)
            self.assertTrue(assertions_pass(contract, values))
            helper = ENV.from_string((ROLE / 'templates/relay-runner-registration.j2').read_text()).render(values)
            if scope == 'repository':
                self.assertIn("--url 'https://github.com/example/relay-consumer'", helper)
                self.assertNotIn('--runnergroup', helper)
            else:
                self.assertIn("--url 'https://github.com/example'", helper)
                expected_group = 'relay-general-restricted' if general else 'relay-production'
                self.assertIn("--runnergroup '" + expected_group + "'", helper)
            self.assertNotIn('--token', helper)
            self.assertIn('read -r -s registration_value', helper)
            self.assertIn('REGISTRATION_ALREADY_PRESENT', helper)
            self.assertNotIn('{{', helper)
            unit = ENV.from_string((ROLE / 'templates/relay-runner.service.j2').read_text()).render(values)
            self.assertIn('RUNNER_REGISTRATION=owner-mediated-' + scope + '-token', unit)
            if linux_bash_available():
                syntax = subprocess.run(['bash', '-n'], input=helper, text=True, capture_output=True)
                self.assertEqual(syntax.returncode, 0, syntax.stderr)
            wrong = {**values, 'relay_runner_registration_scope': 'repository' if scope == 'organization' else 'organization'}
            self.assertFalse(assertions_pass(contract, wrong))

    def test_general_registration_cannot_reuse_any_production_namespace(self):
        contract = named_task('Require isolated namespaces for the general instance on a production host')
        production = instance()
        for scope in ['repository', 'organization']:
            general = instance(True, scope)
            self.assertTrue(all(ENV.compile_expression(value)(**general) for value in contract['when']))
            self.assertTrue(assertions_pass(contract, general))
            for key in ('relay_runner_user', 'relay_runner_group', 'relay_runner_root', 'relay_runner_work_root',
                        'relay_runner_home', 'relay_runner_service_name', 'relay_runner_registration_helper_path'):
                with self.subTest(scope=scope, key=key):
                    self.assertFalse(assertions_pass(contract, {**general, key: production[key]}))

    def test_general_org_registration_requires_its_own_configured_group_at_install_and_enable(self):
        install = named_task('Require the pinned runner package and identity contract')
        enable = yaml.safe_load((ROOT / 'relay-general-runner.yml').read_text())[0]['tasks'][0]
        values = instance(True, 'organization')
        values.update(relay_general_runner_authorized=True,
                      inventory_hostname=values['relay_production_host'],
                      ansible_facts={'distribution': 'Debian', 'distribution_major_version': '12'},
                      relay_production_operation_phase='general-runner-enable',
                      relay_production_exact_head='a' * 40)
        for contract in [install, enable]:
            self.assertTrue(assertions_pass(contract, values))
            for changes in [
                {'relay_runner_registration_scope': 'repository'},
                {'relay_runner_registration_group': 'unconfigured-group'},
                {'relay_runner_registration_group': '', 'relay_general_runner_registration_group': ''},
                {'relay_runner_registration_group': 'relay-production',
                 'relay_general_runner_registration_group': 'relay-production'},
                {'relay_runner_registration_group': 'RELAY-PRODUCTION',
                 'relay_general_runner_registration_group': 'RELAY-PRODUCTION'},
            ]:
                with self.subTest(contract=contract['name'], changes=changes):
                    self.assertFalse(assertions_pass(contract, {**values, **changes}))


    def test_registration_binding_rejects_wrong_scope_name_and_work(self):
        contract = named_task('Detect and validate factual runner registration completion')
        for general, scope in [(False, 'organization'), (True, 'repository'), (True, 'organization')]:
            values = instance(general, scope)
            marker = {'gitHubUrl': 'https://github.com/example' + ('/relay-consumer' if scope == 'repository' else ''),
                      'agentName': values['relay_runner_name'], 'workFolder': values['relay_runner_work_root']}
            self.assertTrue(assertions_pass(contract, {**values, 'relay_runner_registration_state': marker}))
            for key in marker:
                self.assertFalse(assertions_pass(contract, {**values, 'relay_runner_registration_state': {**marker, key: 'wrong'}}))
            old_scope = 'https://github.com/example' + ('/relay-consumer' if scope == 'organization' else '')
            self.assertFalse(assertions_pass(contract, {
                **values, 'relay_runner_registration_state': {**marker, 'gitHubUrl': old_scope},
            }))

    def test_general_enable_rejects_registration_from_another_scope(self):
        play = yaml.safe_load((ROOT / 'relay-general-runner.yml').read_text())[0]
        contract = next(task for task in play['tasks']
                        if task['name'] == 'Require the configured registration scope for the exact general runner')
        for scope in ['repository', 'organization']:
            values = instance(True, scope)
            marker = {'gitHubUrl': 'https://github.com/example' + ('/relay-consumer' if scope == 'repository' else ''),
                      'agentName': values['relay_runner_name'], 'workFolder': values['relay_runner_work_root']}
            self.assertTrue(assertions_pass(contract, {**values, 'general_marker': marker}))
            for mismatch in [
                {'gitHubUrl': 'https://github.com/example' + ('/relay-consumer' if scope == 'organization' else '')},
                {'agentName': values['relay_production_runner_name']},
                {'workFolder': instance()['relay_runner_work_root']},
            ]:
                with self.subTest(scope=scope, mismatch=mismatch):
                    self.assertFalse(assertions_pass(contract, {**values, 'general_marker': {**marker, **mismatch}}))

    def test_owner_enable_cannot_install_software_or_reconcile_another_runner(self):
        play = yaml.safe_load((ROOT / 'relay-general-runner.yml').read_text())[0]
        includes = [task['ansible.builtin.include_role'] for task in play['tasks'] if 'ansible.builtin.include_role' in task]
        self.assertEqual(includes, [
            {'name': 'relay_runner', 'tasks_from': 'general-validation.yml'},
        ])
        mutations = [task for task in play['tasks'] if 'ansible.builtin.systemd' in task]
        self.assertEqual(len(mutations), 1)
        self.assertEqual(mutations[0]['when'], "relay_production_operation_phase == 'general-runner-enable'")
        self.assertEqual(ENV.from_string(mutations[0]['ansible.builtin.systemd']['name']).render(instance(True)), 'relay-general-runner.service')
        for path in (ROOT / 'relay-general-runner.yml', ROOT / 'vars/general-runner.yml',
                     ROLE / 'tasks/general-runtime.yml', ROLE / 'tasks/general-validation.yml'):
            text = path.read_text()
            self.assertNotIn('debian-codexexp-01', text)
            self.assertNotIn('Stage-A', text)

    def test_general_enable_binds_the_configured_production_registration(self):
        play = yaml.safe_load((ROOT / 'relay-general-runner.yml').read_text())[0]
        contract = next(task for task in play['tasks']
                        if task['name'] == 'Require unchanged organization production registration')
        for production_name in ('relay-production-relay', 'example-production-runner'):
            with self.subTest(production_name=production_name):
                values = {
                    'relay_github_repository': 'another-owner/consumer',
                    'relay_production_runner_name': production_name,
                    'relay_runner_name': 'example-general-runner',
                    'relay_state_root': '/var/lib/another-relay',
                }
                marker = {
                    'gitHubUrl': 'https://github.com/another-owner',
                    'agentName': production_name,
                    'workFolder': '/var/lib/another-relay/runner/work',
                }
                self.assertTrue(assertions_pass(contract, {**values, 'production_marker': marker}))
                mismatches = (
                    {'agentName': 'wrong-production-runner'},
                    {'agentName': values['relay_runner_name']},
                    {'gitHubUrl': 'https://github.com/another-owner/consumer'},
                    {'gitHubUrl': 'https://github.com/other-owner'},
                    {'workFolder': '/var/lib/another-relay/general-runner/work'},
                    {'workFolder': '/var/lib/other-relay/runner/work'},
                )
                if production_name != 'relay-production-relay':
                    mismatches += ({'agentName': 'relay-production-relay'},)
                for mismatch in mismatches:
                    with self.subTest(mismatch=mismatch):
                        self.assertFalse(assertions_pass(contract, {
                            **values, 'production_marker': {**marker, **mismatch},
                        }))

    def test_general_enable_requires_local_codex_credentials_even_when_install_allows_missing(self):
        tasks = yaml.safe_load((ROOT / 'relay-general-runner.yml').read_text())[0]['tasks']
        by_name = {task['name']: task for task in tasks}
        token_gate = by_name['Require a provisioned Codex token before enabling automatic execution']
        directory_gate = by_name['Require the isolated Codex credential directory']
        values = {**instance(True), 'relay_codex_token_required': False}
        directory = {'exists': True, 'isdir': True, 'islnk': False,
                     'pw_name': values['relay_codex_user'], 'gr_name': values['relay_codex_group'],
                     'mode': '0700'}
        token = {'exists': True, 'isreg': True, 'islnk': False,
                 'pw_name': values['relay_codex_user'], 'gr_name': values['relay_codex_group'],
                 'mode': '0600', 'nlink': 1, 'size': 128}
        self.assertTrue(assertions_pass(token_gate, {**values, 'general_runner_codex_token': {'stat': token}}))
        self.assertTrue(assertions_pass(directory_gate, {
            **values, 'general_runner_codex_credential_directory': {'stat': directory},
        }))
        for mismatch in ({'exists': False}, {'isreg': False}, {'islnk': True}, {'pw_name': 'root'},
                         {'gr_name': 'root'}, {'mode': '0640'}, {'nlink': 2}, {'size': 0}, {'size': 16385}):
            with self.subTest(token=mismatch):
                self.assertFalse(assertions_pass(token_gate, {
                    **values, 'general_runner_codex_token': {'stat': {**token, **mismatch}},
                }))
        for mismatch in ({'exists': False}, {'isdir': False}, {'islnk': True},
                         {'pw_name': 'root'}, {'gr_name': 'root'}, {'mode': '0750'}):
            with self.subTest(directory=mismatch):
                self.assertFalse(assertions_pass(directory_gate, {
                    **values, 'general_runner_codex_credential_directory': {'stat': {**directory, **mismatch}},
                }))
        for name in ['Inspect Codex credential directory without reading credentials',
                     'Inspect Codex token metadata without reading credentials']:
            inspection = by_name[name]['ansible.builtin.stat']
            self.assertFalse(inspection['follow'])
            self.assertFalse(inspection['get_checksum'])
            self.assertFalse(inspection['get_mime'])
        readability = by_name['Require the Codex runtime identity to read its fixed token']
        self.assertEqual(readability['ansible.builtin.command']['argv'], [
            '/usr/sbin/runuser', '-u', '{{ relay_codex_user }}', '--', '/usr/bin/test', '-r',
            '{{ relay_codex_access_token_file }}',
        ])
        enable_index = tasks.index(by_name['Enable and start only the owner-registered general service'])
        self.assertLess(tasks.index(token_gate), enable_index)
        self.assertLess(tasks.index(directory_gate), enable_index)
        self.assertLess(tasks.index(readability), enable_index)
        for task in [token_gate, directory_gate, readability]:
            self.assertNotIn('when', task)




if __name__ == '__main__':
    unittest.main()
