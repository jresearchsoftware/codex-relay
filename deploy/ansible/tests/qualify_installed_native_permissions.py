#!/usr/bin/env python3
"""Opt-in installed-launcher proof, confined to a private mount/PID namespace.

Run as root on an explicitly authorized qualification host. No installed files,
services, credentials or GitHub records are changed. A deterministic loopback
provider drives the real pinned CLI; no model or Relay attempt is launched.
The installed launcher receives only the candidate's single native argv delta.
"""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import pwd
import grp
import re
import shutil
import subprocess
import sys
import tempfile
import threading

REPO = Path(__file__).resolve().parents[3]
TEMPLATE = REPO / 'deploy/ansible/roles/relay_codex_runtime/templates/relay-codex-launcher.mjs.j2'
RESULT = {'status': 'success', 'summary': 'native permissions qualification',
          'validation': ['native command completed'], 'blockedReason': ''}
PROBE = r'''
import errno,json,os,pathlib,subprocess
p=pathlib.Path.cwd()
for name in ['.agents/skills/native-proof/SKILL.md','ordinary-native-proof.txt']:
 q=p/name;q.parent.mkdir(parents=True,exist_ok=True);q.write_text('synthetic native proof\n')
for args in [['git','add','ordinary-native-proof.txt','.agents'],
             ['git','commit','-qm','Native permission qualification']]:
 subprocess.run(args,check=True,capture_output=True)
negative={}
for name,path in __NEGATIVE_PATHS__.items():
 try:
  fd=os.open(path,os.O_RDONLY);os.close(fd)
 except OSError as e: negative[name]=errno.errorcode.get(e.errno,'UNKNOWN')
 else: negative[name]='EXPOSED'
try: pathlib.Path('/etc/passwd').open('a').close()
except OSError as e: negative['protected_write']=errno.errorcode.get(e.errno,'UNKNOWN')
else: negative['protected_write']='WRITABLE'
r=subprocess.run(['sudo','-n','-u','root','/usr/bin/true'],capture_output=True)
negative['sudo_root']='denied' if r.returncode else 'ALLOWED'
print(json.dumps({'uid':os.getuid(),'gid':os.getgid(),'groups':os.getgroups(),
 'namespaces':{n:os.readlink('/proc/self/ns/'+n) for n in ['mnt','pid','user']},
 'agents_written':(p/'.agents/skills/native-proof/SKILL.md').is_file(),
 'head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
 'github_credentials_present':any(k in os.environ for k in ['GITHUB_TOKEN','GH_TOKEN','SSH_AUTH_SOCK']),
 'negative':negative},sort_keys=True))
'''


def run(*args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installation', required=True, type=Path)
    parser.add_argument('--consumer', required=True, type=Path)
    parser.add_argument('--inside', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    assert os.geteuid() == 0 and sys.platform == 'linux'
    if not args.inside:
        # All subsequent mounts are private, including /proc. No host account,
        # permission, launcher, credential or installed setting is rewritten.
        result = subprocess.run(['unshare', '--mount', '--pid', '--fork', '--mount-proc',
                     sys.executable, str(Path(__file__).resolve()), '--inside',
                     '--installation', str(args.installation), '--consumer', str(args.consumer)],
                     capture_output=True, text=True, timeout=240)
        if result.returncode:
            raise RuntimeError(result.stderr[-8000:])
        print(result.stdout, end='')
        return
    assert os.getpid() == 1, 'inside mode requires a fresh PID namespace'
    run('mount', '--make-rprivate', '/')
    run('mount', '-t', 'tmpfs', '-o', 'mode=0755', 'native-permissions-run', '/run')
    consumer = json.loads(args.consumer.read_text())
    slot = consumer['executionSlots'][0]
    assert slot['id'] == 'primary'
    user, group = slot['runtimeUser'], slot['workGroup']
    uid, gid = pwd.getpwnam(user).pw_uid, grp.getgrnam(group).gr_gid
    assert uid != 0 and gid != 0
    install = args.installation.resolve()
    wrapper = Path(slot['paths']['launcher'])
    assert wrapper.parent == install
    assert "RELAY_ISOLATED_SLOT='1'" in wrapper.read_text(), 'qualified outer isolation required'
    launcher = install / 'relay-codex.mjs'
    original = launcher.read_text()
    old_line = next(line for line in original.splitlines() if 'const args = [' in line)
    new_line = next(line for line in TEMPLATE.read_text().splitlines() if 'const args = [' in line)
    expected = old_line.replace('"--sandbox", "workspace-write", "--add-dir", gitRoot,',
                                '"--sandbox", "danger-full-access",').replace(
                                    ', "-c", "sandbox_workspace_write.network_access=true"', '')
    assert new_line == expected, 'qualification only permits the exact native argv delta'
    binary = install / 'codex-runtime/bin/codex'
    assert run(str(binary), '--version').stdout.strip() == 'codex-cli 0.160.0'
    token = Path(re.search(r'^const TOKEN_FILE = "([^"]+)";', original, re.M)[1])
    work_root = Path(slot['paths']['workRoot'])
    run('mount', '-t', 'tmpfs', '-o', 'mode=0755', 'native-permissions-proof', str(work_root))
    report = {'cli_version': '0.160.0', 'installed_revision': (install / 'current').resolve().name,
              'source_base': run('git', '-C', str(REPO), 'rev-parse', 'HEAD').stdout.strip(),
              'candidate_argv_sha256': hashlib.sha256(new_line.encode()).hexdigest(),
              'candidate_isolation_sha256': hashlib.sha256((REPO / 'deploy/ansible/roles/relay_codex_runtime/files/relay-codex-isolation.mjs').read_bytes()).hexdigest(),
              'installed_launcher_sha256': hashlib.sha256(original.encode()).hexdigest(),
              'runtime_uid': uid, 'work_gid': gid, 'outer_isolation': 'bubblewrap',
              'scope': 'private namespace; installed launcher plus exact native argv delta; no model/GitHub',
              'cases': []}
    with tempfile.TemporaryDirectory(prefix='native-permissions-', dir='/var/tmp') as temp:
        temp = Path(temp)
        # A private overlay permits a synthetic administrator requirement even
        # when /etc/codex is absent, without creating that directory on the host.
        upper, overlay_work = temp / 'etc-upper', temp / 'etc-work'
        upper.mkdir(); overlay_work.mkdir()
        run('mount', '-t', 'overlay', 'overlay', '-o',
            f'lowerdir=/etc,upperdir={upper},workdir={overlay_work}', '/etc')
        candidate = temp / 'launcher.mjs'; candidate.write_text(original.replace(old_line, new_line)); candidate.chmod(0o755)
        credential = temp / 'token'; credential.write_text('synthetic-native-proof'); credential.chmod(0o600)
        os.chown(credential, uid, -1)
        run('mount', '--bind', str(candidate), str(launcher))
        run('mount', '--bind', str(credential), str(token))
        isolation = REPO / 'deploy/ansible/roles/relay_codex_runtime/files/relay-codex-isolation.mjs'
        run('mount', '--bind', str(isolation), str(install / 'relay-codex-isolation.mjs'))
        # Open/close only: even an isolation failure must not read secret bytes.
        foreign = temp / 'foreign-private'; foreign.write_text('synthetic private data'); foreign.chmod(0o600)
        negative_paths = {'foreign_file': str(foreign),
                          'writer_key': consumer['paths']['credentialKeyFile'],
                          'reviewer_key': str(args.consumer.parent / 'reviewer-credentials/github-app-private-key.pem')}
        assert all(Path(p).is_file() for p in negative_paths.values())
        requests, command_outputs = [], []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                assert self.path == '/v1/responses'
                assert self.headers.get('Authorization') is None
                request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                requests.append(request)
                outputs = [v for v in request['input'] if v.get('type') == 'function_call_output']
                if not outputs:
                    item = {'type': 'function_call', 'id': 'fc-native', 'call_id': 'call-native',
                            'name': 'exec_command', 'arguments': json.dumps({
                                'cmd': '/usr/bin/python3 .codex-sandbox/native-probe.py',
                                'yield_time_ms': 1000, 'max_output_tokens': 2000})}
                else:
                    command_outputs.append(outputs[-1]['output'])
                    item = {'type': 'message', 'role': 'assistant', 'id': 'msg-native',
                            'content': [{'type': 'output_text', 'text': json.dumps(RESULT)}]}
                events = [{'type': 'response.created', 'response': {'id': 'resp-native'}},
                          {'type': 'response.output_item.done', 'item': item},
                          {'type': 'response.completed', 'response': {'id': 'resp-native'}}]
                body = ''.join(f'event: {e["type"]}\ndata: {json.dumps(e)}\n\n' for e in events).encode()
                self.send_response(200); self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            for present, restricted in [(True, False), (False, False), (True, True)]:
                requests.clear(); command_outputs.clear()
                if restricted:
                    policy = Path('/etc/codex/requirements.toml')
                    policy.parent.mkdir(exist_ok=True)
                    policy.write_text('allowed_sandbox_modes = ["read-only", "workspace-write"]\n')
                    policy.chmod(0o644)
                cwd = work_root / 'repositories' / consumer['repositories'][0] / (
                    'event-9603' if restricted else 'event-9601' if present else 'event-9602')
                cwd.mkdir(parents=True)
                # Real Task source checkout, rather than a nested projection fixture.
                archive = subprocess.run(['git', '-C', str(REPO), 'archive', 'HEAD'], check=True, capture_output=True)
                subprocess.run(['tar', '-x', '-C', str(cwd)], input=archive.stdout, check=True)
                if not present: shutil.rmtree(cwd / '.agents')
                run('git', '-C', str(cwd), 'init', '-q')
                run('git', '-C', str(cwd), '-c', 'user.name=Qualification', '-c', 'user.email=qualification@example.invalid', 'add', '.')
                run('git', '-C', str(cwd), '-c', 'user.name=Qualification', '-c', 'user.email=qualification@example.invalid', 'commit', '-qm', 'Qualification baseline')
                baseline = run('git', '-C', str(cwd), 'rev-parse', 'HEAD').stdout.strip()
                sandbox = cwd / '.codex-sandbox'
                for directory in ['home', 'config', 'cache', 'data', 'state', 'tmp']: (sandbox / directory).mkdir(parents=True, exist_ok=True)
                (sandbox / 'native-probe.py').write_text(PROBE.replace('__NEGATIVE_PATHS__', repr(negative_paths)))
                (sandbox / 'task-input.md').write_text('Synthetic installed native permission qualification. No external operations.')
                schema = {
                    'type': 'object', 'properties': {k: {'type': 'array', 'items': {'type': 'string'}} if k == 'validation' else {'type': 'string'} for k in RESULT},
                    'required': list(RESULT), 'additionalProperties': False}
                (sandbox / 'codex-result-schema.json').write_text(json.dumps(schema))
                (sandbox / 'home/config.toml').write_text(
                    'model_provider="qualification"\n[features]\nenable_request_compression=false\n'
                    '[model_providers.qualification]\nname="qualification"\nwire_api="responses"\n'
                    f'base_url="http://127.0.0.1:{server.server_port}/v1"\nrequires_openai_auth=false\nsupports_websockets=false\n')
                for path in [cwd, *cwd.rglob('*')]: os.chown(path, uid, gid, follow_symlinks=False)
                child = subprocess.Popen(['sudo', '-n', '-u', user, '-g', group, str(wrapper),
                    'exec', '--json', '--model', 'gpt-6.1-sol', '--effort', 'medium',
                    '--input-file', str(sandbox / 'task-input.md'), '--cwd', str(cwd), '--issue', '96'],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                # Stdin is the launcher's lifetime pipe; keep it open until exit.
                child.wait(timeout=90)
                stdout, stderr = child.stdout.read(), child.stderr.read(); child.stdin.close()
                if restricted:
                    assert child.returncode != 0 and not requests, 'managed denial must precede provider access'
                    assert 'requirements do not allow' in stderr and 'danger-full-access' in stderr
                    assert not (cwd / '.agents/skills/native-proof/SKILL.md').exists()
                    assert '"containment":"reaped"' in stderr
                    report['cases'].append({'managed_requirement': 'read-only/workspace-write only',
                        'native_result': 'denied before provider; noninteractive policy unchanged',
                        'root_agents_write': 'not executed', 'launcher_exit': child.returncode,
                        'containment': 'reaped'})
                    continue
                assert child.returncode == 0, stderr[-2000:]
                assert len(requests) == 2 and len(command_outputs) == 1, command_outputs
                records = [json.loads(line) for rollout in (sandbox / 'home/sessions').rglob('*.jsonl') for line in rollout.read_text().splitlines()]
                context = next(r['payload'] for r in records if r['type'] == 'turn_context')
                assert context['approval_policy'] == 'never'
                output = command_outputs[0]
                match = re.search(r'\{"agents_written".*\}', output)
                assert match, output
                observation = json.loads(match[0])
                assert observation['uid'] == uid and observation['gid'] == gid and observation['agents_written']
                assert observation['head'] != baseline and not observation['github_credentials_present']
                assert all(v in ['ENOENT', 'EACCES', 'EROFS', 'denied'] for v in observation['negative'].values()), observation
                assert all(observation['namespaces'][n] != os.readlink('/proc/self/ns/' + n) for n in ['mnt', 'pid', 'user'])
                assert context['sandbox_policy'] == {'type': 'danger-full-access'}
                assert '"containment":"reaped"' in stderr
                report['cases'].append({'agents_initially': 'present' if present else 'absent',
                    'native_policy': context['sandbox_policy'], 'approval_policy': context['approval_policy'],
                    'observed': observation, 'containment': 'reaped'})
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=5)
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
