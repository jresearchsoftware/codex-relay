#!/usr/bin/env python3
"""Read-only admission of a protected server certificate/private-key pair.

Only fixed status codes cross the process boundary. OpenSSL output, key bytes,
and public-key comparisons are never emitted. The callable trust_store override
exists for local synthetic regression fixtures; the CLI always uses system trust.
"""
import argparse
import os
from pathlib import Path
import re
import stat
import subprocess


LEGACY_ROOT = Path('/etc/letsencrypt')


class ValidationError(Exception):
    """A sanitized, fixed certificate-admission failure code."""


def protected_path(path, *, directory=False, key=False):
    """Require an absolute, non-symlink path protected from non-root writes."""
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ValidationError('TLS_SOURCE_PATH_UNSAFE')
    for parent in reversed(path.parents):
        metadata = parent.lstat()
        if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != 0
                or stat.S_IMODE(metadata.st_mode) & 0o022):
            raise ValidationError('TLS_SOURCE_PARENT_UNSAFE')
    metadata = path.lstat()
    if directory:
        if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != 0
                or stat.S_IMODE(metadata.st_mode) & 0o022):
            raise ValidationError('TLS_SOURCE_PARENT_UNSAFE')
    elif (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != 0
          or stat.S_IMODE(metadata.st_mode) not in ({0o600, 0o640} if key else {0o600, 0o640, 0o644})
          or not 0 < metadata.st_size <= (65536 if key else 1048576)):
        raise ValidationError('TLS_SOURCE_FILE_UNSAFE')
    return path


def _source(path, hostname, kind, allow_lineage):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ValidationError('TLS_SOURCE_PATH_UNSAFE')
    if not path.is_symlink():
        return protected_path(path, key=kind == 'privkey'), None
    # The sole compatibility exception is Certbot's canonical live/archive
    # topology. An explicit configured source must never enable this exception.
    canonical = LEGACY_ROOT / 'live' / hostname / (kind + '.pem')
    if not allow_lineage or path != canonical:
        raise ValidationError('TLS_SOURCE_SYMLINK_FORBIDDEN')
    protected_path(path.parent, directory=True)
    link = path.lstat()
    if link.st_uid != 0:
        raise ValidationError('TLS_SOURCE_SYMLINK_UNSAFE')
    target = os.readlink(path)
    match = re.fullmatch(re.escape('../../archive/' + hostname + '/' + kind) + r'([1-9][0-9]*)\.pem', target)
    if not match:
        raise ValidationError('TLS_SOURCE_LINEAGE_UNSAFE')
    resolved = LEGACY_ROOT / 'archive' / hostname / (kind + match[1] + '.pem')
    return protected_path(resolved, key=kind == 'privkey'), match[1]


def _openssl(arguments, *, input_bytes=None):
    # Do not inherit SSL_CERT_FILE, SSL_CERT_DIR, OPENSSL_CONF, provider loading,
    # or any other controller/remote environment trust override.
    result = subprocess.run(
        ['/usr/bin/openssl', *map(str, arguments)], input=input_bytes,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'OPENSSL_CONF': '/dev/null'},
        timeout=30, check=False,
    )
    if result.returncode:
        raise ValidationError('TLS_SOURCE_CERTIFICATE_INVALID')
    return result.stdout


def validate_sources(certificate, private_key, hostname, *, allow_letsencrypt_lineage=False, trust_store=None):
    """Validate metadata, DNS SAN, keypair, current dates and trusted TLS chain."""
    if (not isinstance(hostname, str) or len(hostname) > 253 or '.' not in hostname
            or not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+', hostname)):
        raise ValidationError('TLS_SOURCE_HOSTNAME_INVALID')
    try:
        cert, cert_number = _source(certificate, hostname, 'fullchain', allow_letsencrypt_lineage)
        key, key_number = _source(private_key, hostname, 'privkey', allow_letsencrypt_lineage)
        if cert_number != key_number:
            raise ValidationError('TLS_SOURCE_LINEAGE_PAIR_MISMATCH')
        san = _openssl(['x509', '-in', cert, '-noout', '-ext', 'subjectAltName'])
        if not re.search(rb'(?:^|[,\n])\s*DNS:[^,\s]+', san):
            raise ValidationError('TLS_SOURCE_DNS_SAN_REQUIRED')
        checked = _openssl(['x509', '-in', cert, '-noout', '-checkhost', hostname]).strip()
        if checked != ('Hostname ' + hostname + ' does match certificate').encode('ascii'):
            raise ValidationError('TLS_SOURCE_HOSTNAME_MISMATCH')
        _openssl(['x509', '-in', cert, '-noout', '-checkend', '0'])
        public = _openssl(['x509', '-in', cert, '-pubkey', '-noout'])
        cert_public = _openssl(['pkey', '-pubin', '-outform', 'DER'], input_bytes=public)
        key_public = _openssl(['pkey', '-in', key, '-passin', 'pass:', '-pubout', '-outform', 'DER'])
        if cert_public != key_public:
            raise ValidationError('TLS_SOURCE_KEYPAIR_MISMATCH')
        # Explicit Debian trust suppresses environmental defaults. verify checks
        # leaf + intermediate notBefore/notAfter and server-purpose constraints.
        trust = (['-CAfile', trust_store, '-no-CApath', '-no-CAstore'] if trust_store is not None
                 else ['-CAfile', '/etc/ssl/certs/ca-certificates.crt', '-CApath', '/etc/ssl/certs', '-no-CAstore'])
        _openssl(['verify', *trust, '-purpose', 'sslserver', '-verify_hostname', hostname,
                  '-untrusted', cert, cert])
    except (OSError, subprocess.TimeoutExpired, ValueError):
        raise ValidationError('TLS_SOURCE_UNAVAILABLE_OR_UNSAFE') from None
    return {'status': 'TLS_CERTIFICATE_KEY_VALIDATED'}


def main(argv=None, *, trust_store=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--certificate', required=True)
    parser.add_argument('--private-key', required=True)
    parser.add_argument('--hostname', required=True)
    parser.add_argument('--allow-letsencrypt-lineage', action='store_true')
    args = parser.parse_args(argv)
    try:
        result = validate_sources(args.certificate, args.private_key, args.hostname,
                                  allow_letsencrypt_lineage=args.allow_letsencrypt_lineage,
                                  trust_store=trust_store)
    except ValidationError as error:
        print(str(error))
        return 1
    print(result['status'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
