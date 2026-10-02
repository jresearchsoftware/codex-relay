"""Read the fixed protected deployment snapshot; never accept a target or path."""
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import ssl
import stat
import sys

from config import loads


def require(condition, code):
    if not condition:
        raise ValueError(code)


def stamp(info):
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def protected_parents(path):
    for parent in path.parents:
        info = parent.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0
                and not info.st_mode & 0o022, 'unsafe-installed-parent')


def read_protected(path, modes, group=None):
    protected_parents(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1
                and stat.S_IMODE(info.st_mode) in modes
                and (group is None or info.st_gid == group), 'unsafe-installed-file')
        raw = stream.read(262145)
        require(0 < len(raw) <= 262144, 'installed-file-size')
        require(stamp(os.fstat(stream.fileno())) == stamp(info), 'installed-file-changed')
    protected_parents(path)
    require(stamp(path.lstat()) == stamp(info), 'installed-file-changed')
    return raw, stamp(info)


def check_public_main(repository, expected_head):
    """Fresh anonymous HTTPS read: no redirects, credentials, cache or fallback."""
    require(re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository), 'installed-repository')
    connection = http.client.HTTPSConnection('api.github.com', timeout=15,
                                              context=ssl.create_default_context())
    try:
        connection.request('GET', '/repos/' + repository + '/git/ref/heads/main', headers={
            'Accept': 'application/vnd.github+json', 'User-Agent': 'codex-relay-installed-apply',
            'Cache-Control': 'no-cache'})
        response = connection.getresponse()
        require(response.status == 200, 'main-head-unavailable')
        raw = response.read(8193)
        require(len(raw) <= 8192, 'main-head-unavailable')
        value = json.loads(raw)
        require(isinstance(value, dict) and value.get('ref') == 'refs/heads/main'
                and isinstance(value.get('object'), dict)
                and value['object'].get('type') == 'commit', 'main-head-unavailable')
        require(value['object'].get('sha') == expected_head, 'main-head-mismatch')
    except (OSError, http.client.HTTPException, UnicodeError, json.JSONDecodeError):
        raise ValueError('main-head-unavailable') from None
    finally:
        connection.close()


def verify(product_root, expected_head, expected_digest=None,
           expected_consumer_revision=None, check_main=False, workflow_consumer_revision=None):
    require(os.geteuid() == 0, 'root-required')
    require(isinstance(expected_head, str) and re.fullmatch('[0-9a-f]{40}', expected_head), 'installed-head')
    if check_main:
        require(isinstance(workflow_consumer_revision, str)
                and re.fullmatch('[0-9a-f]{40}', workflow_consumer_revision), 'workflow-consumer-revision')
    product_root = Path(product_root)
    release = product_root.parent
    require(product_root.name == 'reviewed-source' and release.name == expected_head
            and release.parent.name == 'releases', 'installed-release-path')
    install = release.parent.parent
    current = install / 'current'
    protected_parents(current)
    binding = current.lstat()
    require(stat.S_ISLNK(binding.st_mode) and binding.st_uid == 0
            and os.readlink(current) == str(release), 'installed-current-binding')
    paths = [product_root / '.relay-source.json', release / 'artifact-manifest.json',
             release / 'deployment-config.json']
    source_raw, source_stamp = read_protected(paths[0], {0o644, 0o640, 0o600})
    manifest_raw, manifest_stamp = read_protected(paths[1], {0o640, 0o600})
    config_raw, config_stamp = read_protected(paths[2], {0o600}, group=0)
    try:
        source, manifest = json.loads(source_raw), json.loads(manifest_raw)
        require(isinstance(source, dict) and source.get('revision') == expected_head, 'installed-source-head')
        require(isinstance(manifest, dict) and all(manifest.get(key) == expected_head
                for key in ['commit', 'resolvedRevision', 'installedRevision']), 'installed-manifest-head')
        consumer_revision = manifest.get('consumerRevision')
        require(isinstance(consumer_revision, str) and re.fullmatch('[0-9a-f]{40}', consumer_revision),
                'installed-consumer-revision')
        digest = hashlib.sha256(config_raw).hexdigest()
        require(manifest.get('deploymentConfigSha256') == digest
                and (expected_digest is None or expected_digest == digest), 'installed-config-digest')
        require(expected_consumer_revision is None or consumer_revision == expected_consumer_revision,
                'installed-consumer-revision')
        config = loads(config_raw.decode('utf-8'), product_root)
        require(config['environment']['localApply'] == {'source': 'installed'}
                and config['environment']['namespace'] == install.name, 'installed-config-binding')
    except (UnicodeError, json.JSONDecodeError, KeyError, TypeError):
        raise ValueError('invalid-installed-config') from None
    except ValueError as error:
        # Schema failures disclose only a fixed code, never config/parser input.
        if re.fullmatch('[a-z-]+', str(error)):
            raise
        raise ValueError('invalid-installed-config') from None
    if check_main:
        # The dispatch commit is consumer authority, independent of both the
        # pinned product and the configuration's original consumer provenance.
        check_public_main(config['consumer']['repository'], workflow_consumer_revision)
    protected_parents(current)
    require(stamp(current.lstat()) == stamp(binding), 'installed-current-changed')
    for path, expected in zip(paths, [source_stamp, manifest_stamp, config_stamp]):
        protected_parents(path)
        require(stamp(path.lstat()) == expected, 'installed-file-changed')
    return config, digest, consumer_revision


if __name__ == '__main__':
    try:
        # Only the existing begin task calls this internal checker while holding
        # its transition lock. The runner sudo interface accepts one typed product:consumer binding.
        require(len(sys.argv) == 5, 'argument-contract')
        verify(Path(__file__).resolve().parents[1], sys.argv[1], sys.argv[2], sys.argv[3],
               check_main=True, workflow_consumer_revision=sys.argv[4])
    except (ValueError, OSError) as error:
        code = str(error) if type(error) is ValueError and re.fullmatch('[a-z-]+', str(error)) else 'invalid-input-or-io'
        print('INSTALLED_CONFIG_BLOCKED=' + code, file=sys.stderr)
        raise SystemExit(1)
