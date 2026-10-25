"""Derive locator bytes from desired input and already verified Git evidence.

This module performs no reads or source selection. Callers supply a protected
resolution receipt, or an original manifest receipt after installed verification.
"""
import hashlib
import re


def _require(condition):
    if not condition:
        raise ValueError('git-source-locator-receipt-binding')


def _sha(value, length=40):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{' + str(length) + '}', value) is not None


def _locator(config):
    policy = config['environment']['localApply']
    if policy.get('source') != 'git':
        return {}
    _require(set(policy) == {'source', 'repository', 'configPath'})
    return {'repository': policy['repository'], 'configPath': policy['configPath'],
            'owner': config['consumer']['owner'],
            'productRepository': config['source']['repository'].removeprefix('https://github.com/').removeprefix(
                'git@github.com:').removesuffix('.git')}


def _bound_pair(config, revision, receipt, config_raw):
    locator = _locator(config)
    _require(bool(locator) and _sha(revision) and isinstance(receipt, dict)
             and isinstance(config_raw, bytes)
             and receipt.get('product_sha') == revision
             and receipt.get('product_repository') == locator['productRepository']
             and receipt.get('config_repository') == locator['repository']
             and receipt.get('config_path') == locator['configPath']
             and receipt.get('config_sha256') == hashlib.sha256(config_raw).hexdigest()
             and _sha(receipt.get('config_sha')) and _sha(receipt.get('config_blob_sha'))
             and receipt.get('source_policy') in ['accepted-main', 'accepted-ancestor', 'test-qualified-exact'])
    if receipt['source_policy'] == 'test-qualified-exact':
        _require(config['source'].get('revision') == revision)
    return locator


def expected_locator(config, revision, receipt=None, config_raw=None):
    """Retain an exact TEST grant only from its bound, trusted resolution.

    Git configuration cannot introduce the qualification field. Accepted source
    receipts and ordinary owner-file input always produce the ordinary locator.
    """
    locator = _locator(config)
    _require(receipt is None or isinstance(receipt, dict))
    if receipt is not None and receipt.get('source_policy') == 'test-qualified-exact':
        locator = _bound_pair(config, revision, receipt, config_raw)
        return {**locator, 'qualificationProductSha': revision}
    return locator


def resume_receipt(config, revision, manifest, verified_snapshot_digest, config_raw):
    """Recover original evidence after the caller verifies installed state.

    The canonical installed snapshot has its own hash; the receipt binds the
    original Git bytes separately. Neither value selects new desired input.
    """
    _require(isinstance(manifest, dict) and _sha(verified_snapshot_digest, 64)
             and all(manifest.get(key) == revision for key in ['commit', 'resolvedRevision', 'installedRevision'])
             and manifest.get('deploymentConfigSha256') == verified_snapshot_digest)
    receipt = manifest.get('gitConfigReceipt')
    _bound_pair(config, revision, receipt, config_raw)
    return dict(receipt)
