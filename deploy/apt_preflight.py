"""Verify APT metadata and package acquisition before closing live admission.

Only this invocation's disposable lists/cache change. APT owns signature and
hash verification; raw repository URLs and diagnostics never leave the target.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def verify(packages, *, runner=subprocess.run, parent='/run'):
    if (not isinstance(packages, list) or not packages or len(packages) > 64
            or not all(isinstance(p, str) and re.fullmatch('[a-z0-9][a-z0-9+.-]{0,100}', p) for p in packages)):
        raise ValueError('INTENT_APT_PACKAGE_CONTRACT_INVALID')
    with tempfile.TemporaryDirectory(prefix='relay-apt-preflight-', dir=parent) as directory:
        warnings = 0
        root = Path(directory)
        # Match ordinary public APT metadata accessibility while retaining root
        # ownership. This lets _apt acquire files without disabling its sandbox.
        root.chmod(0o755)
        (root / 'lists/partial').mkdir(parents=True)
        (root / 'cache/archives/partial').mkdir(parents=True)
        base = ['/usr/bin/apt-get', '-o', 'Dir::State::lists=' + str(root / 'lists'),
            '-o', 'Dir::Cache=' + str(root / 'cache'), '-o', 'APT::Update::Error-Mode=any',
            '-o', 'Acquire::AllowInsecureRepositories=false',
            '-o', 'Acquire::AllowDowngradeToInsecureRepositories=false',
            '-o', 'APT::Get::AllowUnauthenticated=false']
        for action, timeout in [(['update'], 240),
                (['--download-only', '--no-upgrade', '--assume-yes', 'install', *packages], 300)]:
            result = runner([*base, *action], capture_output=True, timeout=timeout,
                env={**os.environ, 'LANG': 'C', 'LC_ALL': 'C', 'DEBIAN_FRONTEND': 'noninteractive'})
            if result.returncode != 0:
                raise ValueError('INTENT_APT_INTEGRITY_OR_ACQUISITION_UNPROVEN')
            diagnostics = getattr(result, 'stderr', b'') or b''
            warnings += sum(line.startswith(b'W:') for line in diagnostics.splitlines())
    return {'status': 'PASS', 'scope': 'isolated-signed-metadata-and-download-only',
            'packages': packages, 'warningCount': warnings}


def main():
    try:
        if os.geteuid() != 0:
            raise ValueError('INTENT_APT_ROOT_REQUIRED')
        payload = json.loads(sys.stdin.buffer.read(16385))
        print(json.dumps(verify(payload['packages']), sort_keys=True))
    except Exception as error:
        code = str(error)
        print(code if re.fullmatch('INTENT_APT_[A-Z_]{1,80}', code)
              else 'INTENT_APT_PREFLIGHT_UNAVAILABLE', file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
