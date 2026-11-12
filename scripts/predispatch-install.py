#!/usr/bin/env python3
"""Run the public crash-safe install/continuation with an existing gh credential.

The credential travels only on SSH stdin. The root host creates one private
temporary request, invokes the ordinary public installer once, and removes the
request after completion, failure or a handled disconnect/termination signal.
"""
import argparse
import json
import posixpath
import re
import shlex
import subprocess
import sys


REMOTE_PROGRAM = r'''
import json,os,re,signal,stat,subprocess,sys,tempfile
from pathlib import Path
def require(ok):
    if not ok: raise ValueError('PREDISPATCH_INSTALL_TRANSPORT_INVALID')
def protected(path,directory=False):
    path=Path(path)
    require(path.is_absolute() and str(path)==os.path.normpath(path))
    for entry in [path,*path.parents]:
        info=entry.lstat()
        require(info.st_uid==0 and not stat.S_ISLNK(info.st_mode) and not info.st_mode&0o022)
        require(stat.S_ISDIR(info.st_mode) if entry!=path or directory else stat.S_ISREG(info.st_mode) and info.st_nlink==1)
    return path
def protected_tree(root):
    count=0
    for directory,dirs,files in os.walk(root,followlinks=False):
        for name in dirs+files:
            count+=1;require(count<=20000)
            path=Path(directory)/name;protected(path,path.is_dir())
def interrupted(*_): raise InterruptedError()
for name in ('SIGINT','SIGTERM','SIGHUP'):
    signal.signal(getattr(signal,name),interrupted)
try:
    require(os.geteuid()==0 and len(sys.argv)==6)
    source,config,consumer,revision,mode=sys.argv[1:]
    require(re.fullmatch('[a-f0-9]{40}',revision) and mode in ('install','continue'))
    source=protected(source,True);config=protected(config);consumer=protected(consumer,True)
    cli=protected(source/'deploy/relay-deploy.py')
    # Only a fresh protected owner checkout may supply trusted Git metadata.
    protected(source/'.git',True);protected_tree(source);protected_tree(consumer)
    env={'PATH':'/usr/bin:/bin','HOME':'/root','LANG':'C.UTF-8','LC_ALL':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1',
         'GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null','GIT_OPTIONAL_LOCKS':'0'}
    head=subprocess.run(['/usr/bin/git','--no-replace-objects','-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false',
        '-C',str(source),'rev-parse','--verify','HEAD^{commit}'],env=env,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=False)
    require(head.returncode==0 and head.stdout.decode().strip()==revision)
    clean=subprocess.run(['/usr/bin/git','--no-replace-objects','-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false',
        '-C',str(source),'status','--porcelain','--untracked-files=all'],env=env,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=False)
    require(clean.returncode==0 and not clean.stdout.strip())
    raw=sys.stdin.buffer.read(4097);require(0<len(raw)<=4096)
    request=json.loads(raw)
    require(set(request)=={'operation','repository','runId','attemptId','authorizationId','workflowReadToken'}
        and request['operation']=='finalize-predispatch'
        and type(request['runId']) is int and request['runId']>0
        and request['attemptId']=='run-'+str(request['runId'])
        and type(request['authorizationId']) is int and request['authorizationId']>0
        and re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',request['repository'])
        and isinstance(request['workflowReadToken'],str) and re.fullmatch(r'[!-~]{1,2048}',request['workflowReadToken']))
    if mode=='continue':
        sys.dont_write_bytecode=True;sys.path.insert(0,str(source/'deploy'))
        from config import load,compile_inputs
        values=compile_inputs(load(config,source))
        claim=protected(values['relay_writer_claim_root'],True)
        gate_name='admission-pool-v1.json' if (Path(values['relay_config_root'])/'serial-pool-compat-v1.json').exists() else 'admission-v1.json'
        gate=json.loads(protected(claim/gate_name).read_bytes());operation=gate['operationId']
        require(re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}',operation)
            and gate['phase'] in ('quiesced','applying','recovery-required') and gate['target']==revision)
        snapshot=Path(values['relay_release_root'])/('.stage-'+operation)/'old-installation.json'
        binding=json.loads(protected(snapshot).read_bytes())['predispatchBridge']
        require(binding['operationId']==operation and binding['target']==revision
            and all(binding[key]==request[key] for key in ('runId','attemptId','authorizationId')))
    child=None
    with tempfile.TemporaryDirectory(prefix='relay-predispatch-request-',dir='/run') as temporary:
        path=Path(temporary)/'request.json'
        descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        try:
            os.fchmod(descriptor,0o600);os.fchown(descriptor,0,0)
            require(os.write(descriptor,raw)==len(raw));os.fsync(descriptor)
        finally: os.close(descriptor)
        try:
            child=subprocess.Popen(['/usr/bin/python3',str(cli),'--phase','install','--config',str(config),
                '--consumer-root',str(consumer),'--resolved-revision',revision,'--connection','local',
                '--predispatch-recovery-request',str(path)],env=env,stdin=subprocess.DEVNULL)
            code=child.wait()
        finally:
            if child is not None and child.poll() is None:
                child.terminate()
                try: child.wait(timeout=30)
                except subprocess.TimeoutExpired: child.kill();child.wait(timeout=30)
    raise SystemExit(code)
except (ValueError,KeyError,TypeError,ImportError,OSError,InterruptedError,subprocess.SubprocessError):
    print('PREDISPATCH_INSTALL_TRANSPORT_FAILED;inspect-same-operation-before-continuation',file=sys.stderr)
    raise SystemExit(1)
'''


def absolute_path(value):
    if not value.startswith('/') or posixpath.normpath(value) != value or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise argparse.ArgumentTypeError('expected a normalized absolute path')
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--source', required=True, type=absolute_path, help='fresh verified accepted root-owned product checkout')
    parser.add_argument('--config', required=True, type=absolute_path, help='existing qualified owner Git deployment configuration')
    parser.add_argument('--consumer-root', required=True, type=absolute_path, help='root-owned consumer checkout with the accepted target workflows')
    parser.add_argument('--revision', required=True)
    parser.add_argument('--repository', required=True)
    parser.add_argument('--run-id', required=True, type=int)
    parser.add_argument('--authorization-id', required=True, type=int)
    parser.add_argument('--continue', dest='continuation', action='store_true', help='require the exact retained bridge UUID and request before retrying')
    args = parser.parse_args()
    if (not re.fullmatch(r'[A-Za-z0-9_.@-]+', args.host) or args.host.startswith('-')
        or not re.fullmatch('[a-f0-9]{40}', args.revision) or args.run_id < 1 or args.authorization_id < 1
        or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', args.repository)):
        parser.error('invalid host, revision, repository or native identifier')
    auth = subprocess.run(['gh', 'auth', 'token'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    token = auth.stdout.strip()
    if auth.returncode or not re.fullmatch(rb'[!-~]{1,2048}', token):
        sys.exit('Unable to obtain the existing gh credential.')
    request = {'operation': 'finalize-predispatch', 'repository': args.repository, 'runId': args.run_id,
               'attemptId': f'run-{args.run_id}', 'authorizationId': args.authorization_id,
               'workflowReadToken': token.decode('ascii')}
    payload = json.dumps(request, separators=(',', ':')).encode()
    if len(payload) > 4096:
        sys.exit('Recovery request exceeds the entrypoint limit.')
    remote = ' '.join(map(shlex.quote, ['/usr/bin/python3', '-I', '-c', REMOTE_PROGRAM,
        args.source, args.config, args.consumer_root, args.revision, 'continue' if args.continuation else 'install']))
    result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', args.host, remote],
                            input=payload, check=False)
    return result.returncode


if __name__ == '__main__':
    sys.exit(main())
