"""Ephemeral input transport to the exact installed runner registration helper."""
import re
import shlex
import subprocess


def register_runner(target, key, values, revision, token, guard):
    """Return a bounded proof; never serialize the bootstrap token or raw output.

    The caller holds the installed bootstrap guard, which binds the installed
    manifest to ``revision`` and refuses unfinished production operations.
    Existing registration is validated before the helper consumes stdin.
    """
    if not re.fullmatch('[0-9a-f]{40}', revision):
        raise RuntimeError('runner-registration-exact-head-required')
    if token is not None and (not isinstance(token, str) or len(token) > 4096
                              or any(ord(char) < 33 or ord(char) > 126 for char in token)):
        raise RuntimeError('runner-registration-token-invalid-input;fresh registration token required')
    if guard is None or guard.poll() is not None:
        raise RuntimeError('host-operation-guard-lost;inspect-before-retry')
    general = values['relay_runner_name'] in (
        values['relay_general_runner_name'], '{{ relay_general_runner_name }}')
    name = values['relay_general_runner_name'] if general else values['relay_production_runner_name']
    scope = values['relay_general_runner_registration_scope'] if general else 'organization'
    group = (values['relay_general_runner_registration_group'] if general
             else values['relay_production_runner_registration_group']) if scope == 'organization' else '-'
    work = values['relay_state_root'] + ('/general-runner/work' if general else '/runner/work')
    repository = values['relay_github_repository']
    url = 'https://github.com/' + (repository.split('/')[0] if scope == 'organization' else repository)
    helper = values['relay_install_root'] + ('/relay-general-runner-registration' if general
                                           else '/relay-runner-registration')
    binding = f'url={url} name={name} label={",".join(values["relay_runner_labels"])} group={group} work={work}'
    argv = ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
            '-o', 'IdentitiesOnly=yes', '-i', str(key),
            target['user'] + '@' + target['host'], shlex.join([helper, '--expect-binding', binding])]
    process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True)
    try:
        pending = (token or '') + '\n'
        while True:
            if guard.poll() is not None:
                raise RuntimeError('host-operation-guard-lost;inspect-before-retry')
            try:
                output, errors = process.communicate(input=pending, timeout=1)
                break
            except subprocess.TimeoutExpired:
                pending = None
        if guard.poll() is not None:
            raise RuntimeError('host-operation-guard-lost;inspect-before-retry')
        if process.returncode:
            codes = re.findall(r'^RUNNER_REGISTRATION_FAIL code=([A-Z_]+)$', errors, re.MULTILINE)
            allowed = {'FRESH_REGISTRATION_TOKEN_REQUIRED', 'REGISTRATION_STATE_AMBIGUOUS',
                       'REGISTRATION_COMMAND_FAILED_INSPECT_BEFORE_RETRY', 'ROOT_REQUIRED',
                       'REPOSITORY_CONTRACT', 'RUNNER_ROOT_INVALID', 'RUNNER_ROOT_OWNERSHIP',
                       'RUNNER_PACKAGE_NOT_READY', 'RUNNER_VERSION_MISMATCH',
                       'REGISTRATION_CONFIGURATION_MISMATCH', 'CLEAN_REINSTALL_RECOVERY_REQUIRED'}
            code = codes[-1] if codes and codes[-1] in allowed else 'REGISTRATION_TRANSPORT_UNPROVEN'
            next_action = ('fresh registration token required' if code == 'FRESH_REGISTRATION_TOKEN_REQUIRED'
                           else 'inspect-before-retry')
            raise RuntimeError(f'RUNNER_REGISTRATION_FAIL code={code};next={next_action}')
        proof = re.fullmatch(r'RUNNER_REGISTRATION_PASS url=(\S+) name=(\S+) label=([A-Za-z0-9_.-]+) '
                             r'version=2\.336\.0 state=(registered|reused) group=(\S+) work=(\S+)\n?', output)
        if (proof is None or proof[1] != url or proof[2] != name
                or proof[3] != ','.join(values['relay_runner_labels'])
                or proof[5] != group or proof[6] != work):
            raise RuntimeError('runner-registration-proof-unproven;inspect-before-retry')
        return output.strip()
    finally:
        token = None
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
