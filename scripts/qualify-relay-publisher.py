#!/usr/bin/env python3
"""Opt-in Linux actual-export fixture; synthetic READY, local writes only.

Reuse the pinned Shared Publisher implementation, never a local release engine.
Source CI/acceptance, real publication and credential access remain unqualified.
"""
from pathlib import Path
import argparse, hashlib, sys, json, subprocess, os, tempfile
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--publisher", type=Path, required=True)
parser.add_argument("--vibe", type=Path, required=True)
parser.add_argument("--source-ref", required=True)
args = parser.parse_args()
SOURCE = Path(__file__).resolve().parents[1]
PIN = "5a1e5de66388501235fc9ffd23d45efb34df2b85"
assert sys.platform.startswith("linux"), "Native Linux filesystem required"
assert subprocess.check_output(["git", "-C", str(args.publisher), "rev-parse", "HEAD"], text=True).strip() == PIN
VIBE = args.vibe.resolve()
pin = json.loads((SOURCE / "toolchain/vibevm.json").read_text())
assert hashlib.sha256(VIBE.read_bytes()).hexdigest() == pin["linux_x86_64_musl_binary"]["sha256"]
sys.path.insert(0, str(args.publisher.resolve() / "tooling/vibe-publisher"))
import publisher as P
SHA = P.git(SOURCE, "rev-parse", args.source_ref).decode().strip()
WORK = Path(tempfile.mkdtemp(prefix="relay-publisher-", dir="/tmp"))
for key in ("PUBLISH_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
    os.environ.pop(key, None)
os.environ.update(GIT_AUTHOR_NAME='Fixture',GIT_AUTHOR_EMAIL='fixture@example.invalid',GIT_COMMITTER_NAME='Fixture',GIT_COMMITTER_EMAIL='fixture@example.invalid',GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=os.devnull,GIT_TERMINAL_PROMPT='0')
binding=json.loads(P.git(SOURCE,'show',SHA+':vibe-publisher.json'))
package=dict(binding['packages'][0])
files,receipt=P.snapshot(SOURCE,SHA,package)
metadata=json.loads(P.git(SOURCE,'show',SHA+':guidance/source.json'))
assert receipt['version'] == metadata['version']
tag='v'+receipt['version']
remote=WORK/'distribution.git'
P.git(None,'init','--bare','--initial-branch=main',str(remote))
package['destination']=remote.as_uri()
decision={'status':'READY','package':package['coordinate'],'source_sha':SHA,'version':receipt['version'],'payload_sha256':receipt['payload_sha256'],'destination':package['destination']}
staged=P.stage(SOURCE,package,decision,VIBE,WORK/'stage')
assert staged['status']=='STAGED'
for path,data in files.items():
    assert P.git(Path(staged['staging']),'show',tag+':'+path)==data,path
published=P.finalize(staged)
assert published['status']=='PUBLISHED'
refs_before=P.remote_refs(package['destination'],tag)
retry=P.stage(SOURCE,package,decision,WORK/'absent-binary',WORK/'retry')
assert retry['status']=='ALREADY_PUBLISHED'
assert P.remote_refs(package['destination'],tag)==refs_before
P.git(remote,'config','uploadArchive.allowUnreachable','true')
release_commit=P.git(remote,'rev-parse',tag+'^{}').decode().strip()
consumer=WORK/'consumer'
consumer.mkdir()
(consumer/'vibe.toml').write_text(f'''[project]
name="actual-two-git-roots"
version="0.0.0"
spec_format="mixed"
[requires.packages]
"org.jresearch.ai/codex-relay"={{version="={metadata['version']}",git="{remote.as_uri()}",rev="{release_commit}",auth="none"}}
"org.jresearch.ai/development-governance"={{version="={metadata['shared_version']}",git="https://github.com/jrs-vibevm/org.jresearch.ai.development-governance.git",rev="{metadata['shared_distribution_revision']}",auth="none"}}
''')
(consumer/'AGENTS.md').write_text('Owner local sentinel remains.\n')
env=P.native_environment(WORK/'consumer-env')
result=subprocess.run([str(VIBE),'--json','install','--path',str(consumer),'--no-default-registry','--assume-yes'],env=env,capture_output=True,text=True,timeout=180)
(WORK/'install.stdout').write_text(result.stdout)
(WORK/'install.stderr').write_text(result.stderr)
assert result.returncode==0,(result.returncode,result.stdout,result.stderr)
slot=consumer/'vibevm/vibedeps/org.jresearch.ai.codex-relay'/metadata['version']
for path,data in files.items():
    assert (slot/path).read_bytes()==data,path
assert 'Owner local sentinel remains.' in (consumer/'AGENTS.md').read_text()
assert (consumer/'vibevm/vibedeps/org.jresearch.ai.development-governance'/metadata['shared_version']/'vibe.toml').is_file()
print(json.dumps({'qualification':'LOCAL_SYNTHETIC_READY_ONLY_NO_SOURCE_CI_AUTHORITY','source_sha':SHA,'payload_sha256':receipt['payload_sha256'],'exported_files_including_receipt':len(files),'stage':staged['status'],'local_finalize':published['status'],'same_source_retry':retry['status'],'consumer_install_returncode':result.returncode,'consumer_exact_bytes':True,'owner_agents_sentinel_retained':True,'native_environment_no_credentials':True,'explicit_shared_git_revision':metadata['shared_distribution_revision'],'remote_refs':refs_before,'evidence_directory':str(WORK)},indent=2))
