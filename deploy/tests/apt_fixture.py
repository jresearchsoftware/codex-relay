"""Disposable signed Debian repository for real acquisition-failure proofs."""
from datetime import datetime, timezone
import functools
import gzip
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import subprocess
import threading


def signed_repository(tmp_path):
    root = tmp_path / 'repo'
    index = root / 'dists/stable/main/binary-amd64'
    index.mkdir(parents=True)
    package = tmp_path / 'package'
    (package / 'DEBIAN').mkdir(parents=True)
    name = 'relay-recovery-acquisition-fixture'
    (package / 'DEBIAN/control').write_text('Package: ' + name + '\nVersion: 1.0\nArchitecture: all\n'
        'Maintainer: Fixture <test@example.invalid>\nDescription: disposable recovery proof\n')
    (root / 'pool').mkdir()
    deb = root / 'pool/fixture.deb'
    subprocess.run(['dpkg-deb', '--build', str(package), str(deb)], capture_output=True, check=True)
    raw = deb.read_bytes()
    packages = ('Package: ' + name + '\nVersion: 1.0\nArchitecture: all\nFilename: pool/fixture.deb\n'
        'Size: ' + str(len(raw)) + '\nSHA256: ' + hashlib.sha256(raw).hexdigest() + '\n'
        'Description: disposable recovery proof\n\n').encode()
    compressed = gzip.compress(packages, mtime=0)
    (index / 'Packages').write_bytes(packages)
    (index / 'Packages.gz').write_bytes(compressed)
    release = root / 'dists/stable/Release'
    release.write_text('Suite: stable\nCodename: stable\nDate: '
        + datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S +0000')
        + '\nArchitectures: amd64 all\nComponents: main\nSHA256:\n'
        + ''.join(' ' + hashlib.sha256(data).hexdigest() + ' ' + str(len(data)) + ' main/binary-amd64/'
                  + name + '\n' for name, data in [('Packages', packages), ('Packages.gz', compressed)]))
    home = tmp_path / 'gpg'; home.mkdir(mode=0o700)
    gpg = ['gpg', '--batch', '--homedir', str(home), '--pinentry-mode', 'loopback', '--passphrase', '']
    subprocess.run([*gpg, '--quick-generate-key', 'Recovery Fixture <test@example.invalid>',
                    'rsa2048', 'sign', '0'], capture_output=True, check=True)
    key = tmp_path / 'fixture.gpg'
    key.write_bytes(subprocess.check_output([*gpg, '--export'], stderr=subprocess.DEVNULL))
    subprocess.run([*gpg, '--yes', '--clearsign', '--output', str(release.with_name('InRelease')),
                    str(release)], capture_output=True, check=True)
    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *_args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=str(root)))
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    source = tmp_path / 'sources.list'
    source.write_text('deb [signed-by=' + str(key) + '] http://127.0.0.1:'
                     + str(server.server_address[1]) + ' stable main\n')
    def runner(argv, **options):
        # Only repository selection changes at this fixture boundary. Actual APT
        # signature/hash checks and download-only semantics remain unchanged.
        result = subprocess.run([*argv[:1], '-o', 'Dir::Etc::sourcelist=' + str(source),
            '-o', 'Dir::Etc::sourceparts=-', *argv[1:]], **options)
        runner.diagnostics.append((result.stdout + result.stderr).decode(errors='replace'))
        return result
    runner.diagnostics = []
    try:
        yield name, index / 'Packages.gz', compressed, runner
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
        subprocess.run(['gpgconf', '--homedir', str(home), '--kill', 'gpg-agent'], capture_output=True)
