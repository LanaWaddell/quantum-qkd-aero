"""HYBRID-1 Deliverable 3/5: ``qkd.hybrid.registry`` (D3 registry pattern).

Covers the mandatory D3 CI consistency test (registry contents, enum
vocabularies, and serialized vocabulary constants must not silently drift
apart -- made real by proving the check actually fails on a corrupted
registry, not merely asserting a tautology) and the ``RegistrySnapshot``
digest contract (C8): computed property, absent from the serialized payload,
and process-stable.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qkd.hybrid.registry import (
    KNOWN_POSTURE_STATUSES,
    AlgorithmPostureRegistry,
    RegistryError,
    RegistrySnapshot,
)
from qkd.hybrid.serialization import from_canonical_json, stable_hash, to_canonical_json
from qkd.hybrid.states import AlgorithmPosture, CryptoPostureStatus

T = "2026-08-24T12:00:00.000000Z"

_FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "hybrid_canonical_fixtures.json").read_text(encoding="utf-8")
)


def _posture(suite_id: str, status: CryptoPostureStatus = CryptoPostureStatus.APPROVED) -> AlgorithmPosture:
    return AlgorithmPosture(
        suite_id=suite_id,
        primitive="kem",
        parameter_set="768",
        status=status,
        source_refs=("nist-fips-203",),
        reviewed_at_utc=T,
    )


# ---------------------------------------------------------------------------
# AlgorithmPostureRegistry -- independent registry, declared-or-fail
# ---------------------------------------------------------------------------


def test_registry_registers_and_lists_suite_ids_sorted():
    registry = AlgorithmPostureRegistry()
    registry.register(_posture("ML-KEM-768"))
    registry.register(_posture("ML-DSA-65"))
    assert registry.suite_ids() == ("ML-DSA-65", "ML-KEM-768")


def test_registry_get_returns_registered_posture():
    posture = _posture("ML-KEM-768")
    registry = AlgorithmPostureRegistry(postures=[posture])
    assert registry.get("ML-KEM-768") is posture


def test_registry_get_unknown_suite_raises():
    registry = AlgorithmPostureRegistry()
    with pytest.raises(RegistryError):
        registry.get("does-not-exist")


def test_registry_duplicate_suite_id_registration_rejected():
    registry = AlgorithmPostureRegistry(postures=[_posture("ML-KEM-768")])
    with pytest.raises(RegistryError):
        registry.register(_posture("ML-KEM-768"))


def test_registry_register_rejects_non_algorithm_posture():
    registry = AlgorithmPostureRegistry()
    with pytest.raises(TypeError):
        registry.register("not-a-posture")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# RegistrySnapshot -- construction, sorting, digest
# ---------------------------------------------------------------------------


def test_registry_snapshot_from_registry_is_suite_id_sorted():
    registry = AlgorithmPostureRegistry(postures=[_posture("ML-KEM-768"), _posture("ML-DSA-65")])
    snapshot = registry.snapshot(registry_version="v1", produced_at_utc=T)
    assert [suite_id for suite_id, _ in snapshot.postures] == ["ML-DSA-65", "ML-KEM-768"]


def test_registry_snapshot_direct_construction_from_dict_sorts_and_freezes():
    snapshot = RegistrySnapshot(
        registry_version="v1",
        produced_at_utc=T,
        postures={"z-suite": _posture("z-suite"), "a-suite": _posture("a-suite")},
    )
    assert isinstance(snapshot.postures, tuple)
    assert [suite_id for suite_id, _ in snapshot.postures] == ["a-suite", "z-suite"]


def test_registry_snapshot_rejects_suite_id_key_mismatch():
    with pytest.raises(ValueError):
        RegistrySnapshot(
            registry_version="v1",
            produced_at_utc=T,
            postures={"wrong-key": _posture("ML-KEM-768")},
        )


def test_registry_snapshot_rejects_non_algorithm_posture_value():
    with pytest.raises(TypeError):
        RegistrySnapshot(
            registry_version="v1",
            produced_at_utc=T,
            postures={"suite-1": "not-a-posture"},  # type: ignore[dict-item]
        )


def test_registry_snapshot_rejects_bad_timestamp():
    with pytest.raises(ValueError):
        RegistrySnapshot(registry_version="v1", produced_at_utc="2026-08-24", postures={})


def test_registry_snapshot_digest_matches_fixture():
    posture = _posture("ML-KEM-768")
    posture = AlgorithmPosture(
        suite_id="ML-KEM-768",
        primitive="kem",
        parameter_set="768",
        status=CryptoPostureStatus.APPROVED,
        source_refs=("nist-fips-203",),
        reviewed_at_utc="2026-08-24T12:00:00.000000Z",
        effective_until_utc="2026-08-24T12:05:00.000000Z",
        notes="baseline approved suite",
    )
    snapshot = RegistrySnapshot(
        registry_version="registry-v1",
        produced_at_utc="2026-08-24T12:00:00.000000Z",
        postures={"ML-KEM-768": posture},
    )
    fixture = _FIXTURES["RegistrySnapshot"]
    canonical = to_canonical_json(snapshot)
    assert canonical.decode("utf-8") == fixture["canonical"]
    assert stable_hash(canonical) == fixture["digest"]
    assert snapshot.digest() == fixture["digest"]


def test_registry_snapshot_digest_is_process_stable_and_deterministic():
    snapshot = RegistrySnapshot(registry_version="v1", produced_at_utc=T, postures={})
    first = snapshot.digest()
    second = snapshot.digest()
    assert first == second
    # Re-derive an equal snapshot independently and confirm the same digest --
    # the digest is a pure function of canonical content, not of identity or
    # construction order.
    rebuilt = RegistrySnapshot(registry_version="v1", produced_at_utc=T, postures={})
    assert rebuilt.digest() == first


def test_registry_snapshot_digest_absent_from_serialized_payload():
    snapshot = RegistrySnapshot(
        registry_version="v1", produced_at_utc=T, postures={"ML-KEM-768": _posture("ML-KEM-768")}
    )
    envelope = json.loads(to_canonical_json(snapshot).decode("utf-8"))
    assert set(envelope["payload"]) == {"registry_version", "produced_at_utc", "postures"}
    assert "digest" not in envelope["payload"]
    assert "digest" not in envelope


def test_registry_snapshot_round_trip():
    snapshot = RegistrySnapshot(
        registry_version="v1", produced_at_utc=T, postures={"ML-KEM-768": _posture("ML-KEM-768")}
    )
    encoded = to_canonical_json(snapshot)
    decoded = from_canonical_json(encoded, RegistrySnapshot)
    assert decoded == snapshot
    assert decoded.digest() == snapshot.digest()


# ---------------------------------------------------------------------------
# D3 mandatory CI consistency test -- proven real against a corrupted registry
# ---------------------------------------------------------------------------


def test_known_posture_statuses_matches_crypto_posture_status_enum():
    assert set(KNOWN_POSTURE_STATUSES) == {status.value for status in CryptoPostureStatus}


def test_registry_check_consistency_passes_for_a_valid_registry():
    registry = AlgorithmPostureRegistry(postures=[_posture("ML-KEM-768"), _posture("ML-DSA-65")])
    registry.check_consistency()  # must not raise


def test_registry_check_consistency_catches_key_suite_id_mismatch():
    """Corrupt the registry's internal dict directly (bypassing ``register()``,
    which itself forbids this) to prove ``check_consistency`` performs a real
    structural check, not a tautological one."""

    registry = AlgorithmPostureRegistry(postures=[_posture("ML-KEM-768")])
    registry._postures["renamed-key"] = registry._postures.pop("ML-KEM-768")
    with pytest.raises(RegistryError):
        registry.check_consistency()


def test_registry_check_consistency_catches_vocabulary_drift(monkeypatch):
    """Corrupt the module-level serialized vocabulary constant to prove the
    drift check actually compares against the live enum, not a copy of
    itself."""

    import qkd.hybrid.registry as registry_module

    monkeypatch.setattr(
        registry_module, "KNOWN_POSTURE_STATUSES", ("approved", "watched")  # missing several real values
    )
    registry = AlgorithmPostureRegistry(postures=[_posture("ML-KEM-768")])
    with pytest.raises(RegistryError):
        registry.check_consistency()
