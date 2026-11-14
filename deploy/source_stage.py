"""Native batch for the existing source-only private preparation play.

Unsupported frontend rendering/transport sizes retain the owning Ansible path.
Once submitted, an unproved operation stops; it never retries another writer.
"""
import base64
import gzip
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import zlib

MAX_ARCHIVE = 24 * 1024 * 1024
MAX_CONSUMER = 512 * 1024
MAX_HELPER = 256 * 1024
MAX_INPUT = 36 * 1024 * 1024
ENTRYPOINTS = ('entrypoint.mjs', 'recover-attempt-publication.mjs', 'admission-cli.mjs',
              'privileged-writer-entrypoint.mjs', 'codex-dispatch-entrypoint.mjs', 'diagnostic-store-entrypoint.mjs')


def require(value, code='INTENT_STAGE_NATIVE_INPUT_INVALID'):
    if not value:
        raise ValueError(code)


def render_consumer(source_root, values):
    from ansible.parsing.dataloader import DataLoader
    from ansible.template import Templar
    import yaml
    source_root = Path(source_root)
    defaults = yaml.safe_load((source_root / 'deploy/ansible/group_vars/all.yml').read_text())
    variables = {**defaults, **values, 'playbook_dir': str(source_root / 'deploy/ansible')}
    template = source_root / 'deploy/ansible/roles/relay_controller/templates/consumer.json.j2'
    templar = Templar(loader=DataLoader(), variables=variables)
    raw = templar.do_template(template.read_text(), preserve_trailing_newlines=True,
                              escape_backslashes=False).encode()
    require(0 < len(raw) <= MAX_CONSUMER)
    require(isinstance(json.loads(raw), dict))
    return raw


def guard_alive(guard, code):
    require(guard is not None and guard.poll() is None, code)


def prepare(preparation, guard, pool_guard):
    # A missing legacy guard/profile is an unsupported optimization, preserving
    # its original play. A guard lost during an admitted operation is a boundary.
    if guard is None or pool_guard is None:
        return False
    guard_alive(guard, 'INTENT_STAGE_HOST_LOCK_LOST')
    guard_alive(pool_guard, 'INTENT_STAGE_POOL_LOCK_LOST')
    root = Path(__file__).resolve().parents[1]
    try:
        helper_source = (root / 'deploy/ansible/roles/relay_artifacts/files/relay-intent-stage.py').read_text()
        require(len(helper_source.encode()) <= MAX_HELPER)
        scope = {'__name__': 'relay_source_stage_identity'}
        exec(compile(helper_source, '<frozen-stage-helper>', 'exec'), scope)
        scope['identity'](preparation.identity)
        archive_path = Path(preparation.values['relay_source_archive'])
        before = archive_path.stat()
        require(0 < before.st_size <= MAX_ARCHIVE)
        archive = archive_path.read_bytes()
        after = archive_path.stat()
        require(len(archive) == before.st_size and all(getattr(before, key) == getattr(after, key)
                for key in ['st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns']))
        consumer = render_consumer(root, preparation.values)
        compressed = gzip.compress(archive, compresslevel=1, mtime=0)
        require(len(compressed) <= MAX_ARCHIVE)
        payload = {'operationId': preparation.operation, 'sourceIdentity': preparation.identity,
            'stage': preparation.stage, 'installRoot': preparation.values['relay_install_root'],
            'releaseRoot': preparation.values['relay_release_root'], 'reinstall': preparation.reinstall,
            'compatibilityLinks': preparation.values.get('relay_compatibility_links', []),
            'helperSource': helper_source, 'archiveGzipBase64': base64.b64encode(compressed).decode(),
            'consumerBase64': base64.b64encode(consumer).decode()}
        require(len(json.dumps(payload).encode()) <= MAX_INPUT)
    except (ImportError, OSError, KeyError, ValueError, TypeError):
        return False
    except Exception:
        # Templar filter/register availability is frontend capability, not
        # permission to issue an alternative root operation after submission.
        return False
    result = preparation.execute(['/usr/bin/python3', '-I', '-c', Path(__file__).read_text()], payload=payload)
    guard_alive(guard, 'INTENT_STAGE_HOST_LOCK_LOST')
    guard_alive(pool_guard, 'INTENT_STAGE_POOL_LOCK_LOST')
    require(result == {'status': 'SOURCE_STAGE_READY', 'operationId': preparation.operation,
                       'sourceIdentity': preparation.identity}, 'INTENT_STAGE_NATIVE_RESULT_UNPROVEN')
    return True


def decode_archive(encoded):
    # One gzip member, full CRC/trailer verification, and an output bound before
    # allocating the complete archive. Concatenated members/trailing bytes refuse.
    require(isinstance(encoded, str) and 0 < len(encoded) <= ((MAX_ARCHIVE + 2) // 3) * 4)
    compressed = base64.b64decode(encoded, validate=True)
    require(0 < len(compressed) <= MAX_ARCHIVE)
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    archive = decoder.decompress(compressed, MAX_ARCHIVE + 1)
    require(0 < len(archive) <= MAX_ARCHIVE and decoder.eof
            and not decoder.unused_data and not decoder.unconsumed_tail,
            'INTENT_STAGE_NATIVE_ARCHIVE_INVALID')
    return archive


def native(payload):
    require(os.geteuid() == 0, 'INTENT_STAGE_ROOT_REQUIRED')
    require(isinstance(payload, dict) and set(payload) == {'operationId', 'sourceIdentity', 'stage',
        'installRoot', 'releaseRoot', 'reinstall', 'compatibilityLinks', 'helperSource',
        'archiveGzipBase64', 'consumerBase64'})
    require(type(payload['reinstall']) is bool and isinstance(payload['helperSource'], str)
            and len(payload['helperSource'].encode()) <= MAX_HELPER)
    scope = {'__name__': 'relay_frozen_stage_helper'}
    exec(compile(payload['helperSource'], '<frozen-stage-helper>', 'exec'), scope)
    identity = scope['identity'](payload['sourceIdentity'])
    stage = scope['stage_root'](payload['stage'], payload['operationId'])
    parent = (Path(payload['installRoot']).parent / ('.' + Path(payload['installRoot']).name + '-staging')
              if payload['reinstall'] else Path(payload['releaseRoot']))
    require(parent.is_absolute() and stage.parent == parent, 'INTENT_STAGE_NATIVE_BINDING_INVALID')
    archive = decode_archive(payload['archiveGzipBase64'])
    consumer = base64.b64decode(payload['consumerBase64'], validate=True)
    require(0 < len(archive) <= MAX_ARCHIVE and 0 < len(consumer) <= MAX_CONSUMER)
    require(isinstance(json.loads(consumer), dict))
    scope['atomic'](stage / 'source.tar', archive, 0o600)
    scope['run']('extract', stage, {'operationId': payload['operationId'], 'sourceIdentity': identity,
        'compatibilityLinks': payload['compatibilityLinks']}, stage / 'source.tar')
    scope['atomic'](stage / 'consumer.json', consumer, 0o600)
    source = stage / 'release/reviewed-source/controller/src'
    for name in ENTRYPOINTS:
        result = subprocess.run(['/usr/bin/node', '--check', str(source / name)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'}, timeout=30, check=False)
        require(result.returncode == 0, 'INTENT_STAGE_SOURCE_SYNTAX_INVALID')
    return {'status': 'SOURCE_STAGE_READY', 'operationId': payload['operationId'], 'sourceIdentity': identity}


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT + 1)
        require(len(raw) <= MAX_INPUT)
        print(json.dumps(native(json.loads(raw))))
    except Exception as error:
        code = str(error)
        print(code if re.fullmatch('INTENT_STAGE_[A-Z_]{1,100}', code) else 'INTENT_STAGE_NATIVE_UNPROVEN', file=sys.stderr)
        raise SystemExit(40)
