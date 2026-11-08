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
    if isinstance(values['relay_runner_labels'], str):
        values['relay_runner_labels'] = yaml.safe_load(values['relay_runner_labels'])
    return values


def named_task(name):
    tasks = yaml.safe_load((ROLE / 'tasks/main.yml').read_text(encoding='utf-8'))
    return next(task for task in tasks if task['name'] == name)


def assertions_pass(task, values):
    # Ansible evaluates each assertion as an if-block, whose grammar differs
    # from compile_expression for an unparenthesized conditional expression.
    return all(ENV.from_string('{% if ' + expression + ' %}true{% else %}false{% endif %}').render(values) == 'true'
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
            self.assertEqual('PartOf=reviewer-mcp.service' in unit, values is production)
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
            self.assertIn('state=reused', helper)
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









if __name__ == '__main__':
    unittest.main()
