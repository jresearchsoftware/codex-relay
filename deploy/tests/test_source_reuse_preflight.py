"""Source-only preparation retains the ordinary lock and recovery boundaries."""
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from install_preflight import PreparedInstall


@pytest.fixture
def preparation(monkeypatch):
    prepared = PreparedInstall(None, None, {
        'relay_install_root': '/opt/relay', 'relay_release_root': '/opt/relay/releases',
        'relay_namespace': 'relay',
        'relay_consumer_revision': 'c' * 40, 'relay_intent_expected_installed_revision': 'a' * 40,
    }, {'revision': 'b' * 40}, '12345678-1234-4234-8234-123456789abc')
    calls = []
    module = SimpleNamespace(
        prepare=lambda *_args: True,
        verify=lambda _prepared, **options: calls.append(('verify', options)) or {'sealed': True},
        promote=lambda *_args: {'status': 'SOURCE_UPGRADE_READY', 'revision': 'b' * 40},
    )
    monkeypatch.setitem(sys.modules, 'source_upgrade', module)
    return prepared, module, calls


def test_missing_evidence_does_not_nominate_and_malformed_response_refuses(preparation):
    prepared, module, _calls = preparation
    module.prepare = lambda *_args: False
    assert prepared.prepare_source_reuse({}, None, None) is False
    assert prepared.source_reuse is False
    module.prepare = lambda *_args: {'eligible': True}
    with pytest.raises(RuntimeError, match='RESULT_UNPROVEN'):
        prepared.prepare_source_reuse({}, None, None)
    assert prepared.source_reuse is False


def test_final_reuses_one_batch_only_under_writer_lock(preparation):
    prepared, _module, calls = preparation
    assert prepared.prepare_source_reuse({}, None, None)
    prepared.initial = {}
    prepared.captured = True
    prepared.consumer = lambda **options: calls.append(('consumer', options))
    prepared.host = lambda **_options: pytest.fail('batch owns host proof')
    prepared.action = lambda *_args: pytest.fail('batch owns captured snapshot revalidation')
    with pytest.raises(RuntimeError, match='WRITER_LOCK_MISSING'):
        prepared.final()
    prepared.holder = SimpleNamespace(poll=lambda: None)
    prepared.final()
    assert calls == [('consumer', {'final': True}), ('verify', {'final': True})]


def test_promotion_requires_cutover_capture_and_live_lease_and_exact_target(preparation):
    prepared, module, _calls = preparation
    prepared.prepare_source_reuse({}, None, None)
    for captured, cutover, holder in [(False, True, SimpleNamespace(poll=lambda: None)),
                                     (True, False, SimpleNamespace(poll=lambda: None)),
                                     (True, True, SimpleNamespace(poll=lambda: 1))]:
        prepared.captured, prepared.cutover_started, prepared.holder = captured, cutover, holder
        with pytest.raises(RuntimeError, match='SEQUENCE_INVALID'):
            prepared.promote_source_reuse({}, None, None)
    prepared.captured = prepared.cutover_started = True
    prepared.holder = SimpleNamespace(poll=lambda: None)
    module.promote = lambda *_args: {'status': 'SOURCE_UPGRADE_READY', 'revision': 'a' * 40}
    with pytest.raises(RuntimeError, match='PROMOTION_UNPROVEN'):
        prepared.promote_source_reuse({}, None, None)
