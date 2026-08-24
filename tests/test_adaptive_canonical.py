"""ADAPT-1 canonical extraction, records, and digest invariants."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

from qkd.adaptive.references import (
    ADAPTIVE_SCHEMA_VERSION,
    CalibrationSpec,
    CommittedReference,
    DecisionRules,
    ReferenceContractError,
    ScalarReferenceModel,
)
from qkd.adaptive.traces import ChannelStateTrace, TraceContractError
from qkd.canonical import SerializationError, from_canonical_json, stable_hash, to_canonical_json

_ROOT = Path(__file__).resolve().parents[1]
_FIXTURE = _ROOT / "tests" / "fixtures" / "adaptive_canonical_trace.json"
_HYBRID_FIXTURE = _ROOT / "tests" / "fixtures" / "hybrid_canonical_fixtures.json"


def _reference() -> CommittedReference:
    return CommittedReference(
        reference_id="reference-1",
        committed_at_utc="2026-08-23T23:59:59.000000Z",
        observable_name="qber",
        model=ScalarReferenceModel(
            f=0.9,
            h=1.0,
            q=1.0,
            r=0.5,
            x0=0.0,
            p0=1.0 / (1.0 - 0.9**2),
        ),
        calibration=CalibrationSpec(alpha=0.05, lags=20, effective_n=2000, measurement_dim=1),
        decision_rules=DecisionRules(max_freshness_age_s=60.0),
    )


def _trace() -> ChannelStateTrace:
    return ChannelStateTrace(
        trace_id="trace-fixture",
        link_id="link-fixture",
        observable_name="qber",
        window_start_utc="2026-08-24T00:00:00.000000Z",
        window_end_utc="2026-08-24T00:00:02.000000Z",
        sample_interval_us=1_000_000,
        values=(0.125, -2.5, 3.0),
    )


def test_adaptive_envelope_matches_committed_byte_and_digest_fixture():
    fixture = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    encoded = to_canonical_json(_trace(), schema_version=ADAPTIVE_SCHEMA_VERSION)
    assert encoded == fixture["canonical"].encode("utf-8")
    assert stable_hash(encoded) == fixture["digest"]


def test_adaptive_float_tuple_round_trip_is_exact():
    encoded = to_canonical_json(_trace(), schema_version=ADAPTIVE_SCHEMA_VERSION)
    decoded = from_canonical_json(
        encoded,
        ChannelStateTrace,
        schema_version=ADAPTIVE_SCHEMA_VERSION,
    )
    assert decoded == _trace()
    assert decoded.values == (0.125, -2.5, 3.0)


def test_adaptive_loader_rejects_noncanonical_whitespace():
    canonical = to_canonical_json(_trace(), schema_version=ADAPTIVE_SCHEMA_VERSION)
    noncanonical = json.dumps(json.loads(canonical), indent=2).encode("utf-8")
    with pytest.raises(SerializationError, match="canonical reserialization"):
        from_canonical_json(
            noncanonical,
            ChannelStateTrace,
            schema_version=ADAPTIVE_SCHEMA_VERSION,
        )


def test_adaptive_loader_rejects_wrong_schema_identity():
    encoded = to_canonical_json(_trace(), schema_version=ADAPTIVE_SCHEMA_VERSION)
    with pytest.raises(SerializationError, match="schema_version"):
        from_canonical_json(encoded, ChannelStateTrace, schema_version="hybrid-1.0")


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_float_tuple_encoding_rejects_nonfinite_values(value):
    trace = object.__new__(ChannelStateTrace)
    for field, item in dataclasses.asdict(_trace()).items():
        object.__setattr__(trace, field, item)
    object.__setattr__(trace, "values", (value,))
    with pytest.raises(SerializationError, match="finite"):
        to_canonical_json(trace, schema_version=ADAPTIVE_SCHEMA_VERSION)


def test_float_tuple_decoding_rejects_nonfinite_values():
    encoded = to_canonical_json(_trace(), schema_version=ADAPTIVE_SCHEMA_VERSION)
    malformed = encoded.replace(b"3.0]", b"1e999]")
    with pytest.raises(SerializationError, match="finite"):
        from_canonical_json(
            malformed,
            ChannelStateTrace,
            schema_version=ADAPTIVE_SCHEMA_VERSION,
        )


def test_trace_constructor_normalizes_finite_numeric_values_to_float_tuple():
    trace = dataclasses.replace(
        _trace(),
        values=(1, 2.5),
        window_end_utc="2026-08-24T00:00:01.000000Z",
    )
    assert trace.values == (1.0, 2.5)
    assert all(type(value) is float for value in trace.values)


def test_trace_inclusive_end_relation_is_rechecked_on_canonical_load():
    encoded = to_canonical_json(_trace(), schema_version=ADAPTIVE_SCHEMA_VERSION)
    malformed = encoded.replace(b"00:00:02.000000Z", b"00:00:03.000000Z")
    with pytest.raises(SerializationError, match="inclusive final-sample"):
        from_canonical_json(
            malformed,
            ChannelStateTrace,
            schema_version=ADAPTIVE_SCHEMA_VERSION,
        )


def test_trace_constructor_rejects_nonfinite_and_bad_time_relation():
    with pytest.raises(TraceContractError, match="finite"):
        dataclasses.replace(_trace(), values=(float("nan"),))
    with pytest.raises(TraceContractError, match="must match"):
        dataclasses.replace(_trace(), window_start_utc="2026-08-24T00:00:00Z")
    with pytest.raises(TraceContractError, match="inclusive final-sample"):
        dataclasses.replace(_trace(), window_end_utc="2026-08-24T00:00:03.000000Z")


def test_reference_digest_is_computed_and_never_a_stored_field():
    reference = _reference()
    assert "digest" not in {field.name for field in dataclasses.fields(reference)}
    assert reference.digest == stable_hash(
        to_canonical_json(reference, schema_version=ADAPTIVE_SCHEMA_VERSION)
    )


@pytest.mark.parametrize(
    "mutated",
    [
        lambda reference: dataclasses.replace(
            reference, model=dataclasses.replace(reference.model, f=0.8)
        ),
        lambda reference: dataclasses.replace(
            reference, model=dataclasses.replace(reference.model, x0=0.25)
        ),
        lambda reference: dataclasses.replace(
            reference,
            decision_rules=dataclasses.replace(
                reference.decision_rules, max_freshness_age_s=61.0
            ),
        ),
        lambda reference: dataclasses.replace(
            reference, committed_at_utc="2026-08-23T23:59:58.000000Z"
        ),
        lambda reference: dataclasses.replace(reference, observable_name="availability"),
    ],
)
def test_reference_digest_changes_for_every_valid_model_rule_or_identity_edit(mutated):
    reference = _reference()
    assert mutated(reference).digest != reference.digest


@pytest.mark.parametrize(
    "kwargs",
    [
        {"alpha": 0.01, "lags": 20, "effective_n": 2000, "measurement_dim": 1},
        {"alpha": 0.05, "lags": 10, "effective_n": 2000, "measurement_dim": 1},
        {"alpha": 0.05, "lags": 20, "effective_n": 1000, "measurement_dim": 1},
        {"alpha": 0.05, "lags": 20, "effective_n": 2000, "measurement_dim": 2},
    ],
)
def test_reference_refuses_unsupported_calibration_edits(kwargs):
    with pytest.raises(ReferenceContractError, match="unsupported calibration"):
        CalibrationSpec(**kwargs)


def test_reference_wire_form_contains_only_four_calibration_lookup_keys():
    envelope = json.loads(
        to_canonical_json(_reference(), schema_version=ADAPTIVE_SCHEMA_VERSION)
    )
    assert set(envelope["payload"]["calibration"]) == {
        "alpha",
        "lags",
        "effective_n",
        "measurement_dim",
    }


def test_hybrid_fixture_bytes_remain_frozen_after_mechanism_extraction():
    assert hashlib.sha256(_HYBRID_FIXTURE.read_bytes()).hexdigest() == (
        "628b6998ce4b77546c48073df9da0763836c4716d25c8305c58006a470e6847d"
    )


def test_canonical_mechanism_has_no_default_schema_identity():
    with pytest.raises(TypeError):
        to_canonical_json(_trace())
    with pytest.raises(TypeError):
        from_canonical_json(b"{}", ChannelStateTrace)
