"""HYBRID-1 Deliverable 4/5: ``qkd.hybrid.serialization`` (D-H1-3).

Canonical-JSON envelope/encoding, round-trip and digest-stability tests for
every Stage 1 record type, exact byte fixtures (``tests/fixtures/
hybrid_canonical_fixtures.json``), timestamp-grammar accept/reject on both
the construction and load paths, the loader's canonical-reserialization
rejection guard, unknown/missing-key rejection, and non-ASCII round-tripping
under ``ensure_ascii=True``.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from qkd.adaptive.contracts import AttributionVerdict, DegradationAttributionEvidence
from qkd.hybrid.registry import RegistrySnapshot
from qkd.hybrid.serialization import SCHEMA_VERSION, SerializationError, from_canonical_json, stable_hash, to_canonical_json
from qkd.hybrid.states import (
    AlgorithmPosture,
    AssumptionUpdateEvent,
    AssuranceDecision,
    AssuranceDisposition,
    AuthenticationEvidence,
    AuthenticationScope,
    AuthenticationStatus,
    CryptoAssuranceState,
    CryptoPostureStatus,
    HybridKeyMaterial,
    KeyBufferState,
    KeyIssuanceMode,
    KeyProvenanceRecord,
    MissionPolicy,
    MissionPolicyProfile,
    PhysicalLinkState,
    PhysicalLinkStatus,
    PnsSuspicionLevel,
    PqcHandshakeEvidence,
    QkdKeyCandidate,
)

_FIXTURES_DIR = Path(__file__).parent / "fixtures"
_FIXTURES = json.loads((_FIXTURES_DIR / "hybrid_canonical_fixtures.json").read_text(encoding="utf-8"))

T = "2026-08-24T12:00:00.000000Z"
T2 = "2026-08-24T12:05:00.000000Z"
DIGEST_A = "a" * 64
DIGEST_B = "b" * 64


def _build_samples() -> dict[str, object]:
    """The exact set of sample records used to generate the byte fixtures.

    Field values here must match ``tests/fixtures/hybrid_canonical_fixtures.json``
    byte-for-byte -- any change to either must change both together.
    """

    samples: dict[str, object] = {}

    samples["PhysicalLinkState"] = PhysicalLinkState(
        link_id="link-001",
        epoch_id="epoch-001",
        observed_at_utc=T,
        qber=0.021,
        sifted_key_rate_bps=12000.5,
        secure_key_rate_bps=4300.25,
        decoy_pns_suspicion=PnsSuspicionLevel.NONE,
        finite_key_epsilon=1e-9,
        error_correction_leakage_bits=256,
        privacy_amplification_id="pa-001",
        session_id="sess-001",
        peer_id="peer-ground-01",
        status=PhysicalLinkStatus.HEALTHY,
        attribution_evidence_ref="attr-evidence-001",
        evidence_refs=("ev-link-001", "ev-link-002"),
    )

    samples["KeyBufferState"] = KeyBufferState(
        link_id="link-001",
        observed_at_utc=T,
        buffer_fill_bits=1048576,
        consumption_rate_bps=2048.0,
        projected_depletion_utc=T2,
        next_contact_window_utc=T2,
        depletion_rate_anomaly=False,
        evidence_refs=("ev-buffer-001",),
    )

    samples["QkdKeyCandidate"] = QkdKeyCandidate(
        key_id="qkey-001",
        link_id="link-001",
        epoch_id="epoch-001",
        session_id="sess-001",
        secret_ref="secret-handle-001",
        secure_key_bits=8192,
        produced_at_utc=T,
        physical_state_ref="physlink-001",
        evidence_refs=(),
    )

    samples["CryptoAssuranceState"] = CryptoAssuranceState(
        session_id="sess-001",
        peer_id="peer-ground-01",
        observed_at_utc=T,
        kem_posture_ref="posture-mlkem768",
        signature_posture_ref="posture-mldsa65",
        implementation_status=CryptoPostureStatus.APPROVED,
        authentication_refs=("auth-ref-001", "auth-ref-002"),
        status=CryptoPostureStatus.APPROVED,
        evidence_refs=(),
    )

    algorithm_posture = AlgorithmPosture(
        suite_id="ML-KEM-768",
        primitive="kem",
        parameter_set="768",
        status=CryptoPostureStatus.APPROVED,
        source_refs=("nist-fips-203",),
        reviewed_at_utc=T,
        effective_until_utc=T2,
        notes="baseline approved suite",
    )
    samples["AlgorithmPosture"] = algorithm_posture

    samples["PqcHandshakeEvidence"] = PqcHandshakeEvidence(
        session_id="sess-001",
        peer_id="peer-ground-01",
        kem_suite_id="ML-KEM-768",
        signature_suite_id="ML-DSA-65",
        transcript_hash=DIGEST_A,
        shared_secret_ref="pqc-secret-handle-001",
        implementation_id="liboqs-0.10",
        implementation_status=CryptoPostureStatus.APPROVED,
        algorithm_posture=algorithm_posture,
        evidence_refs=("ev-pqc-001",),
    )

    samples["AuthenticationEvidence"] = AuthenticationEvidence(
        session_id="sess-001",
        peer_id="peer-ground-01",
        channel_id="classical-ch-001",
        scope=AuthenticationScope.QKD_CLASSICAL_CHANNEL,
        mechanism="ml-dsa-65-signed",
        status=AuthenticationStatus.VALID,
        credential_ref="cred-001",
        transcript_hash=DIGEST_B,
        evidence_refs=(),
    )

    samples["MissionPolicy"] = MissionPolicy(
        policy_id="policy-001",
        policy_version="1.0.0",
        profile=MissionPolicyProfile.HYBRID_REQUIRED,
        allow_watched_pqc=False,
        emergency_exception_ref=None,
        require_human_review_for_contested=True,
        metadata={"mission": "aero-demo-1", "owner": "ops"},
    )

    samples["AssuranceDecision"] = AssuranceDecision(
        session_id="sess-001",
        decision_id="decision-001",
        policy_id="policy-001",
        policy_version="1.0.0",
        policy_profile=MissionPolicyProfile.HYBRID_REQUIRED,
        physical_status=PhysicalLinkStatus.HEALTHY,
        crypto_status=CryptoPostureStatus.APPROVED,
        authentication_status=AuthenticationStatus.VALID,
        issuance_mode=KeyIssuanceMode.HYBRID,
        disposition=AssuranceDisposition.ASSURED,
        required_actions=(),
        selected_input_refs=("qkey-001", "pqc-secret-handle-001"),
        attribution_evidence_ref="attr-evidence-001",
        key_buffer_evidence_ref="ev-buffer-001",
        freshness_results={"physical": "fresh", "crypto": "fresh"},
        reasons=("all gates passed",),
        transcript_hash=DIGEST_A,
        evidence_refs=("ev-decision-001",),
    )

    samples["KeyProvenanceRecord"] = KeyProvenanceRecord(
        key_id="hybridkey-001",
        decision_ref="decision-001",
        selected_input_refs=("qkey-001", "pqc-secret-handle-001"),
        rejected_input_refs=(),
        derivation_suite="hkdf-sha384-hybrid-v1",
        policy_version="1.0.0",
        transcript_hash=DIGEST_A,
        created_at_utc=T,
        schema_version="hybrid-1.0",
    )

    samples["AssumptionUpdateEvent"] = AssumptionUpdateEvent(
        event_id="assumption-001",
        suite_id="ML-KEM-768",
        previous_status=CryptoPostureStatus.WATCHED,
        new_status=CryptoPostureStatus.APPROVED,
        source_refs=("nist-fips-203",),
        reviewed_by="posture-board",
        effective_at_utc=T,
    )

    samples["HybridKeyMaterial"] = HybridKeyMaterial(
        key_id="hybridkey-001",
        session_id="sess-001",
        purpose="traffic",
        derivation_suite="hkdf-sha384-hybrid-v1",
        qkd_epoch_id="epoch-001",
        pqc_suite_id="ML-KEM-768",
        policy_version="1.0.0",
        key_ref="derived-key-handle-001",
        provenance_refs=("hybridkey-001-provenance",),
    )

    samples["DegradationAttributionEvidence"] = DegradationAttributionEvidence(
        evidence_id="attr-evidence-001",
        link_id="link-001",
        verdict=AttributionVerdict.ENVIRONMENT_CONSISTENT,
        confidence=0.87,
        window_start_utc=T,
        window_end_utc=T2,
        produced_at_utc=T2,
        monitor_id="tier4-monitor-01",
        monitor_version="0.1.0",
        reference_id="ref-model-001",
        reference_digest=DIGEST_A,
        source_integrity="signed",
        source_independence="independent-sensor",
        freshness="fresh",
        reason_codes=("nominal_turbulence",),
        evidence_refs=(),
    )

    samples["RegistrySnapshot"] = RegistrySnapshot(
        registry_version="registry-v1",
        produced_at_utc=T,
        postures={"ML-KEM-768": algorithm_posture},
    )

    return samples


_SAMPLES = _build_samples()


# ---------------------------------------------------------------------------
# Exact byte fixtures (per record type)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(_SAMPLES))
def test_canonical_envelope_matches_byte_fixture(name):
    record = _SAMPLES[name]
    canonical = to_canonical_json(record)
    fixture = _FIXTURES[name]
    assert canonical.decode("utf-8") == fixture["canonical"]
    assert stable_hash(canonical) == fixture["digest"]


@pytest.mark.parametrize("name", sorted(_SAMPLES))
def test_envelope_shape_and_schema_version(name):
    record = _SAMPLES[name]
    envelope = json.loads(to_canonical_json(record).decode("utf-8"))
    assert set(envelope) == {"record_type", "schema_version", "payload"}
    assert envelope["record_type"] == type(record).__name__
    assert envelope["schema_version"] == SCHEMA_VERSION == "hybrid-1.0"


# ---------------------------------------------------------------------------
# Round-trip: from(to(x)) == x, and digest stability
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(_SAMPLES))
def test_round_trip_equals_original(name):
    record = _SAMPLES[name]
    encoded = to_canonical_json(record)
    decoded = from_canonical_json(encoded, type(record))
    assert decoded == record


@pytest.mark.parametrize("name", sorted(_SAMPLES))
def test_digest_is_process_stable(name):
    record = _SAMPLES[name]
    encoded_first = to_canonical_json(record)
    encoded_second = to_canonical_json(record)
    assert encoded_first == encoded_second
    assert stable_hash(encoded_first) == stable_hash(encoded_second)


def test_stable_hash_is_lowercase_hex_sha256_length():
    digest = stable_hash(to_canonical_json(_SAMPLES["PhysicalLinkState"]))
    assert len(digest) == 64
    assert digest == digest.lower()
    int(digest, 16)  # raises ValueError if not valid hex


# ---------------------------------------------------------------------------
# Canonical encoding shape: sorted keys, no whitespace, ensure_ascii
# ---------------------------------------------------------------------------


def test_canonical_json_has_no_whitespace_variance():
    encoded = to_canonical_json(_SAMPLES["PhysicalLinkState"])
    assert b", " not in encoded
    assert b": " not in encoded
    assert b"\n" not in encoded


def test_canonical_json_keys_sorted_at_every_level():
    envelope = json.loads(to_canonical_json(_SAMPLES["AssuranceDecision"]).decode("utf-8"))
    assert list(envelope) == sorted(envelope)
    assert list(envelope["payload"]) == sorted(envelope["payload"])
    assert list(envelope["payload"]["freshness_results"]) == sorted(envelope["payload"]["freshness_results"])


def test_canonical_float_uses_python_repr_shortest_form():
    record = _SAMPLES["PhysicalLinkState"]
    envelope = json.loads(to_canonical_json(record).decode("utf-8"))
    assert envelope["payload"]["qber"] == 0.021
    # The raw bytes must contain the shortest round-trip decimal, matching
    # repr(0.021) -- not a fixed-precision or alternate spelling.
    assert b'"qber":0.021' in to_canonical_json(record)


# ---------------------------------------------------------------------------
# NaN/Inf rejected at construction and at encoding
# ---------------------------------------------------------------------------


def test_nan_rejected_at_construction():
    with pytest.raises(ValueError):
        PhysicalLinkState(
            link_id="link-1",
            epoch_id="epoch-1",
            observed_at_utc=T,
            qber=float("nan"),
            sifted_key_rate_bps=1.0,
            secure_key_rate_bps=1.0,
            decoy_pns_suspicion=PnsSuspicionLevel.NONE,
            finite_key_epsilon=1e-9,
            error_correction_leakage_bits=1,
            privacy_amplification_id="pa-1",
            session_id="sess-1",
            peer_id="peer-1",
            status=PhysicalLinkStatus.HEALTHY,
            attribution_evidence_ref=None,
        )


def test_inf_rejected_at_encoding_layer_defense_in_depth():
    """Bypass the frozen dataclass's own construction-time guard via
    ``object.__setattr__`` (the only way to reach a non-finite float in a
    live instance) to prove the encoder independently rejects it too."""

    record = _SAMPLES["KeyBufferState"]
    object.__setattr__(record, "consumption_rate_bps", math.inf)
    try:
        with pytest.raises(SerializationError):
            to_canonical_json(record)
    finally:
        object.__setattr__(record, "consumption_rate_bps", 2048.0)


# ---------------------------------------------------------------------------
# Timestamp grammar -- both construction and load paths (C5)
# ---------------------------------------------------------------------------

_BAD_TIMESTAMPS = [
    "2026-08-24T12:00:00.000000+00:00",
    "2026-08-24T12:00:00.0Z",
    "2026-08-24T12:00:00.000Z",
    "2026-08-24T12:00:00Z",
    "2026-08-24t12:00:00.000000Z",
    "2026-08-24T12:00:00.000000z",
]


def _envelope_bytes_with_observed_at(bad_timestamp: str) -> bytes:
    envelope = json.loads(to_canonical_json(_SAMPLES["KeyBufferState"]).decode("utf-8"))
    envelope["payload"]["observed_at_utc"] = bad_timestamp
    return json.dumps(envelope, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")


@pytest.mark.parametrize("bad_ts", _BAD_TIMESTAMPS)
def test_timestamp_grammar_rejected_on_load_path(bad_ts):
    data = _envelope_bytes_with_observed_at(bad_ts)
    with pytest.raises(SerializationError):
        from_canonical_json(data, KeyBufferState)


def test_timestamp_grammar_accepted_on_load_path():
    data = to_canonical_json(_SAMPLES["KeyBufferState"])
    decoded = from_canonical_json(data, KeyBufferState)
    assert decoded == _SAMPLES["KeyBufferState"]


# ---------------------------------------------------------------------------
# Loader canonical-reserialization rejection (C6)
# ---------------------------------------------------------------------------


def test_loader_rejects_non_canonical_but_semantically_equal_json():
    non_canonical = (_FIXTURES_DIR / "hybrid_non_canonical_physical_link_state.json").read_bytes()
    canonical = _FIXTURES["PhysicalLinkState"]["canonical"].encode("utf-8")
    parsed_non_canonical = json.loads(non_canonical)
    parsed_canonical = json.loads(canonical)
    assert parsed_non_canonical == parsed_canonical  # semantically equal ...
    assert non_canonical != canonical  # ... but not byte-identical
    with pytest.raises(SerializationError):
        from_canonical_json(non_canonical, PhysicalLinkState)
    # The canonical form itself must still load cleanly.
    assert from_canonical_json(canonical, PhysicalLinkState) == _SAMPLES["PhysicalLinkState"]


def test_loader_rejects_reordered_top_level_keys():
    envelope = json.loads(to_canonical_json(_SAMPLES["QkdKeyCandidate"]).decode("utf-8"))
    reordered = {
        "schema_version": envelope["schema_version"],
        "payload": envelope["payload"],
        "record_type": envelope["record_type"],
    }
    data = (json.dumps(reordered) + " ").encode("utf-8")  # trailing space also breaks byte-equality
    with pytest.raises(SerializationError):
        from_canonical_json(data, QkdKeyCandidate)


# ---------------------------------------------------------------------------
# Unknown-key / missing-key rejection, record_type / schema_version mismatch
# ---------------------------------------------------------------------------


def test_loader_rejects_unknown_envelope_key():
    envelope = json.loads(to_canonical_json(_SAMPLES["QkdKeyCandidate"]).decode("utf-8"))
    envelope["extra_top_level_key"] = "unexpected"
    data = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")
    with pytest.raises(SerializationError):
        from_canonical_json(data, QkdKeyCandidate)


def test_loader_rejects_unknown_payload_key():
    envelope = json.loads(to_canonical_json(_SAMPLES["QkdKeyCandidate"]).decode("utf-8"))
    envelope["payload"]["unexpected_field"] = "surprise"
    data = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")
    with pytest.raises(SerializationError):
        from_canonical_json(data, QkdKeyCandidate)


def test_loader_rejects_missing_payload_key():
    envelope = json.loads(to_canonical_json(_SAMPLES["QkdKeyCandidate"]).decode("utf-8"))
    del envelope["payload"]["key_id"]
    data = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")
    with pytest.raises(SerializationError):
        from_canonical_json(data, QkdKeyCandidate)


def test_loader_rejects_record_type_mismatch():
    data = to_canonical_json(_SAMPLES["QkdKeyCandidate"])
    with pytest.raises(SerializationError):
        from_canonical_json(data, KeyBufferState)


def test_loader_rejects_schema_version_mismatch():
    envelope = json.loads(to_canonical_json(_SAMPLES["QkdKeyCandidate"]).decode("utf-8"))
    envelope["schema_version"] = "hybrid-0.9"
    data = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")
    with pytest.raises(SerializationError):
        from_canonical_json(data, QkdKeyCandidate)


def test_loader_rejects_invalid_utf8():
    with pytest.raises(SerializationError):
        from_canonical_json(b"\xff\xfe not utf-8", QkdKeyCandidate)


def test_loader_rejects_invalid_json():
    with pytest.raises(SerializationError):
        from_canonical_json(b"{not valid json", QkdKeyCandidate)


def test_loader_rejects_non_object_envelope():
    with pytest.raises(SerializationError):
        from_canonical_json(b"[1,2,3]", QkdKeyCandidate)


# ---------------------------------------------------------------------------
# Non-ASCII content round-trips under ensure_ascii=True
# ---------------------------------------------------------------------------


def test_non_ascii_round_trips_under_ensure_ascii():
    policy = MissionPolicy(
        policy_id="policy-unicode",
        policy_version="1.0.0",
        profile=MissionPolicyProfile.RESEARCH_MODE,
        allow_watched_pqc=True,
        metadata={"mission_name": "misión-任务-\U0001f680"},
    )
    encoded = to_canonical_json(policy)
    # ensure_ascii=True: no raw multi-byte UTF-8 sequence appears; only
    # 7-bit-clean ASCII bytes (the non-ASCII codepoints are \u-escaped).
    assert all(byte < 0x80 for byte in encoded)
    assert b"\\u00f3" in encoded or b"\\u00F3" in encoded
    decoded = from_canonical_json(encoded, MissionPolicy)
    assert decoded == policy
    assert dict(decoded.metadata)["mission_name"] == "misión-任务-\U0001f680"
