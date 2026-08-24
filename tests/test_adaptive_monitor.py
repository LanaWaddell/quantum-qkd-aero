"""ADAPT-1 passive attribution monitor and predeclared ensemble program."""

from __future__ import annotations

import ast
import dataclasses
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from qkd.adaptive.contracts import AttributionVerdict, DegradationAttributionEvidence
from qkd.adaptive.monitor import (
    ADAPT_COMPONENT_ALPHA,
    ADAPT_FAMILY_ALPHA_BOUND,
    ADAPT_MONITOR_ID,
    ADAPT_MONITOR_VERSION,
    AttributionMonitor,
    MonitorContractError,
    TraceLengthContractError,
)
from qkd.adaptive.observables import OBSERVABLES, ObservableContractError, observable_spec
from qkd.adaptive.references import (
    ADAPTIVE_SCHEMA_VERSION,
    CalibrationSpec,
    CommittedReference,
    DecisionRules,
    ReferenceContractError,
    ScalarReferenceModel,
)
from qkd.adaptive.traces import (
    ChannelStateTrace,
    TraceContractError,
    generate_law_shifted_trace,
    generate_matched_law_trace,
    generate_quasiperiodic_drift_trace,
    generate_reference_consistent_trace,
    generate_variance_inflated_trace,
)
from qkd.canonical import from_canonical_json, to_canonical_json
from qkd.twin import LinearGaussianTwin, innovation_diagnostic

ADAPT_MASTER_SEED = 20260825
PURPOSE_ORDER = (
    "null_consistent",
    "variance_inflated_high",
    "variance_inflated_low",
    "law_shifted",
    "matched_law",
    "quasiperiodic_golden",
    "quasiperiodic_sqrt2",
    "quasiperiodic_rational",
    "determinism",
)
ALPHA = 0.05
LAGS = 20
EFFECTIVE_N = 2000
MEASUREMENT_DIM = 1
SAMPLE_INTERVAL_US = 1_000_000
NULL_RUNS = 200
POWER_RUNS = 50
NULL_COMPONENT_BAND = (3, 19)
COMBINED_UPPER_COUNT = 32
POWER_MINIMUM_COUNT = 45
QUASIPERIODIC_EQUIVALENCE_COUNT = 7
F = 0.9
H = 1.0
Q = 1.0
R = 0.5
X0 = 0.0
P0 = Q / (1.0 - F**2)
TRACE_START = "2026-08-24T00:00:00.000000Z"

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src" / "qkd"


def _reference(
    *, observable_name: str = "qber", max_freshness_age_s: float = 60.0
) -> CommittedReference:
    return CommittedReference(
        reference_id="reference-1",
        committed_at_utc="2026-08-23T23:59:59.000000Z",
        observable_name=observable_name,
        model=ScalarReferenceModel(f=F, h=H, q=Q, r=R, x0=X0, p0=P0),
        calibration=CalibrationSpec(ALPHA, LAGS, EFFECTIVE_N, MEASUREMENT_DIM),
        decision_rules=DecisionRules(max_freshness_age_s=max_freshness_age_s),
    )


def _seed_map() -> dict[str, list[int]]:
    roots = np.random.SeedSequence(ADAPT_MASTER_SEED).spawn(len(PURPOSE_ORDER))
    result = {}
    for purpose, root in zip(PURPOSE_ORDER, roots, strict=True):
        children = root.spawn(NULL_RUNS if purpose in {"null_consistent", "matched_law"} else POWER_RUNS)
        result[purpose] = [int(child.generate_state(1, dtype=np.uint64)[0]) for child in children]
    return result


def _end_timestamp(n_steps: int = EFFECTIVE_N) -> str:
    start = datetime.strptime(TRACE_START, "%Y-%m-%dT%H:%M:%S.%fZ")
    end = start + timedelta(microseconds=(n_steps - 1) * SAMPLE_INTERVAL_US)
    return end.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _produced_at(n_steps: int = EFFECTIVE_N, *, offset_s: float = 0.0) -> str:
    end = datetime.strptime(_end_timestamp(n_steps), "%Y-%m-%dT%H:%M:%S.%fZ")
    return (end + timedelta(seconds=offset_s)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _evaluate(trace: ChannelStateTrace, reference: CommittedReference | None = None):
    return AttributionMonitor().evaluate(
        trace,
        _reference() if reference is None else reference,
        evidence_id=f"evidence-{trace.trace_id}",
        produced_at_utc=trace.window_end_utc,
    )


def _consistent(seed: int, *, n_steps: int = EFFECTIVE_N) -> ChannelStateTrace:
    return generate_reference_consistent_trace(
        _reference(),
        trace_id=f"trace-{seed}",
        link_id="link-1",
        window_start_utc=TRACE_START,
        sample_interval_us=SAMPLE_INTERVAL_US,
        seed=seed,
        n_steps=n_steps,
    )


def _binomial_cdf(k: int, n: int, p: float) -> float:
    return sum(math.comb(n, i) * p**i * (1.0 - p) ** (n - i) for i in range(k + 1))


def _exact_binomial_two_sided_band(n: int, p: float, *, tail_prob: float = 0.005):
    lo = max(k for k in range(n + 1) if _binomial_cdf(k - 1, n, p) <= tail_prob)
    hi = min(k for k in range(n + 1) if 1.0 - _binomial_cdf(k, n, p) <= tail_prob)
    return lo, hi


def _one_sided_upper(n: int, p: float, *, tail_prob: float = 0.005) -> int:
    return min(k for k in range(n + 1) if 1.0 - _binomial_cdf(k, n, p) <= tail_prob)


def test_anchor_table_constants_and_derived_integer_bounds_are_literal():
    assert ADAPT_MASTER_SEED == 20260825
    assert PURPOSE_ORDER == (
        "null_consistent",
        "variance_inflated_high",
        "variance_inflated_low",
        "law_shifted",
        "matched_law",
        "quasiperiodic_golden",
        "quasiperiodic_sqrt2",
        "quasiperiodic_rational",
        "determinism",
    )
    assert (F, H, Q, R, X0) == (0.9, 1.0, 1.0, 0.5, 0.0)
    assert P0 == Q / (1.0 - F**2)
    assert (ALPHA, LAGS, EFFECTIVE_N, MEASUREMENT_DIM) == (0.05, 20, 2000, 1)
    assert (SAMPLE_INTERVAL_US, NULL_RUNS, POWER_RUNS) == (1_000_000, 200, 50)
    assert _exact_binomial_two_sided_band(200, 0.05) == NULL_COMPONENT_BAND == (3, 19)
    assert _one_sided_upper(200, 0.10) == COMBINED_UPPER_COUNT == 32
    assert POWER_MINIMUM_COUNT == 45
    assert QUASIPERIODIC_EQUIVALENCE_COUNT == 7
    assert ADAPT_COMPONENT_ALPHA == 0.05
    assert ADAPT_FAMILY_ALPHA_BOUND == 0.10
    forbidden_dev_seed = "".join(("2026", "0824"))
    assert forbidden_dev_seed not in Path(__file__).read_text(encoding="utf-8")


def test_observable_registry_is_closed_world_and_fully_annotated():
    assert tuple(OBSERVABLES) == (
        "qber",
        "sifted_key_rate_bps",
        "secure_key_rate_bps",
        "decoy_anomaly_score",
        "availability",
        "buffer_fill_bits",
    )
    for spec in OBSERVABLES.values():
        assert spec.trust == "adversarially_shapeable"
        assert spec.latency_class in {"per_sample", "per_block", "per_pass"}
        assert spec.source_module
    assert observable_spec("qber", require_monitorable=True).unit == "fraction"


def test_unknown_and_policy_context_observables_reject_before_monitoring():
    with pytest.raises(ObservableContractError, match="unknown"):
        observable_spec("not_registered", require_monitorable=True)
    with pytest.raises(ObservableContractError, match="policy_context_only"):
        observable_spec("buffer_fill_bits", require_monitorable=True)
    with pytest.raises(TraceContractError, match="policy_context_only"):
        dataclasses.replace(_consistent(1, n_steps=1), observable_name="buffer_fill_bits")


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.add("." * node.level + (node.module or ""))
    return modules


def test_adaptive_import_graph_uses_only_declared_dependencies():
    denied = (
        "qkd.hybrid",
        "qkd.fixtures",
        "qkd.link",
        "qkd.mission",
        "qkd.detection",
        "qkd.effects",
        "qkd.replay",
        "qkd.bb84",
        "qkd.channel",
        "qkd.orbit",
        "qkd.eve",
        "qkd.coherence",
        "qkd.schema",
        "qkd.run",
    )
    for path in sorted((_SRC / "adaptive").glob("*.py")):
        for module in _imports(path):
            if module.startswith("."):
                continue
            assert not module.startswith(denied), f"{path} imports denied module {module!r}"
            root = module.split(".", 1)[0]
            assert (
                root in sys.stdlib_module_names
                or module == "numpy"
                or module == "qkd.twin"
                or module == "qkd.canonical"
                or module.startswith("qkd.adaptive")
            ), f"{path} imports undeclared dependency {module!r}"
    importers = {
        path.name
        for path in sorted((_SRC / "hybrid").glob("*.py"))
        if "qkd.canonical" in _imports(path)
    }
    assert importers == {"serialization.py"}


def test_reference_rejects_multivariate_or_incomplete_calibration():
    with pytest.raises(ReferenceContractError, match="unsupported calibration"):
        CalibrationSpec(ALPHA, LAGS, EFFECTIVE_N, 2)
    with pytest.raises(TypeError):
        CommittedReference(
            "reference",
            "2026-08-23T00:00:00.000000Z",
            "qber",
            object(),
            CalibrationSpec(ALPHA, LAGS, EFFECTIVE_N, 1),
            DecisionRules(60.0),
        )


def test_reference_reconstruction_is_bit_identical_to_direct_twin():
    reference = _reference()
    restored = from_canonical_json(
        to_canonical_json(reference, schema_version=ADAPTIVE_SCHEMA_VERSION),
        CommittedReference,
        schema_version=ADAPTIVE_SCHEMA_VERSION,
    )
    trace = _consistent(_seed_map()["determinism"][0])
    observations = np.asarray(trace.values).reshape((-1, 1))

    def run(candidate):
        model = candidate.model
        twin = LinearGaussianTwin(
            np.array([[model.f]]),
            np.array([[model.h]]),
            np.array([[model.q]]),
            np.array([[model.r]]),
        )
        return twin.run(observations, np.array([model.x0]), np.array([[model.p0]]))

    direct = run(reference)
    reconstructed = run(restored)
    for field in dataclasses.fields(direct):
        assert np.array_equal(getattr(direct, field.name), getattr(reconstructed, field.name))
    assert innovation_diagnostic(direct, reference.calibration.build()) == innovation_diagnostic(
        reconstructed, restored.calibration.build()
    )


@pytest.mark.parametrize(
    ("committed_at", "match"),
    [
        (TRACE_START, "strictly precede"),
        ("2026-08-24T00:00:01.000000Z", "strictly precede"),
    ],
)
def test_commit_then_observe_is_strict_and_produces_no_evidence(committed_at, match):
    reference = dataclasses.replace(_reference(), committed_at_utc=committed_at)
    with pytest.raises(MonitorContractError, match=match):
        _evaluate(_consistent(2), reference)


def test_monitor_rejects_observable_mismatch_and_early_production_time():
    trace = _consistent(3)
    with pytest.raises(MonitorContractError, match="observable_name"):
        _evaluate(trace, _reference(observable_name="availability"))
    with pytest.raises(MonitorContractError, match="must not precede"):
        AttributionMonitor().evaluate(
            trace,
            _reference(),
            evidence_id="evidence",
            produced_at_utc="2026-08-24T00:00:01.000000Z",
        )
    with pytest.raises(MonitorContractError, match="non-empty"):
        AttributionMonitor().evaluate(
            trace,
            _reference(),
            evidence_id="",
            produced_at_utc=trace.window_end_utc,
        )
    with pytest.raises(MonitorContractError, match="must match"):
        AttributionMonitor().evaluate(
            trace,
            _reference(),
            evidence_id="evidence",
            produced_at_utc="2026-08-24T00:33:19Z",
        )


def test_exact_length_trichotomy_short_equal_and_long():
    short = _consistent(4, n_steps=EFFECTIVE_N - 1)
    evidence = AttributionMonitor().evaluate(
        short,
        _reference(),
        evidence_id="short",
        produced_at_utc=short.window_end_utc,
    )
    assert evidence.verdict is AttributionVerdict.INSUFFICIENT_EVIDENCE
    assert evidence.confidence == 0.0
    assert evidence.reason_codes == ("window_below_effective_n",)

    exact = _consistent(5)
    assert _evaluate(exact).verdict in {
        AttributionVerdict.ENVIRONMENT_CONSISTENT,
        AttributionVerdict.UNEXPLAINED,
    }

    long = _consistent(6, n_steps=EFFECTIVE_N + 1)
    with pytest.raises(TraceLengthContractError, match="never truncates"):
        _evaluate(long)


def test_trace_time_relation_is_inclusive_and_exact_at_microsecond_precision():
    trace = _consistent(7, n_steps=3)
    assert trace.window_start_utc == TRACE_START
    assert trace.window_end_utc == "2026-08-24T00:00:02.000000Z"
    with pytest.raises(TraceContractError, match="inclusive final-sample"):
        dataclasses.replace(trace, window_end_utc="2026-08-24T00:00:02.000001Z")


def test_freshness_boundary_equality_is_fresh_and_above_is_stale():
    reference = _reference(max_freshness_age_s=60.0)
    trace = _consistent(8)
    monitor = AttributionMonitor()
    at_boundary = monitor.evaluate(
        trace,
        reference,
        evidence_id="at-boundary",
        produced_at_utc=_produced_at(offset_s=60.0),
    )
    above_boundary = monitor.evaluate(
        trace,
        reference,
        evidence_id="above-boundary",
        produced_at_utc=_produced_at(offset_s=60.000001),
    )
    assert at_boundary.freshness == "fresh"
    assert above_boundary.freshness == "stale"


@pytest.mark.parametrize(
    ("whiteness_pass", "nis_pass", "nis_position", "verdict", "reason_codes"),
    [
        (True, True, "inside", AttributionVerdict.ENVIRONMENT_CONSISTENT, ("whiteness_pass", "nis_pass")),
        (False, True, "inside", AttributionVerdict.UNEXPLAINED, ("whiteness_reject", "nis_pass")),
        (True, False, "high", AttributionVerdict.UNEXPLAINED, ("whiteness_pass", "nis_reject_high")),
        (False, False, "low", AttributionVerdict.UNEXPLAINED, ("whiteness_reject", "nis_reject_low")),
    ],
)
def test_operational_or_mapping_records_both_component_outcomes_in_frozen_order(
    monkeypatch, whiteness_pass, nis_pass, nis_position, verdict, reason_codes
):
    statistic = {"inside": 2000.0, "high": 2200.0, "low": 1800.0}[nis_position]
    result = SimpleNamespace(
        whiteness_pass=whiteness_pass,
        nis_pass=nis_pass,
        nis_statistic=statistic,
        nis_lower_threshold=1877.0,
        nis_upper_threshold=2126.0,
    )
    monkeypatch.setattr("qkd.adaptive.monitor.innovation_diagnostic", lambda *_: result)
    evidence = _evaluate(_consistent(9))
    assert evidence.verdict is verdict
    assert evidence.reason_codes == reason_codes
    assert evidence.confidence == 1.0 - ADAPT_FAMILY_ALPHA_BOUND == 0.9


def test_evidence_fields_preserve_identity_integrity_independence_and_no_statistics():
    trace = _consistent(10)
    evidence = _evaluate(trace)
    assert evidence.evidence_refs == (trace.trace_id, "reference-1")
    assert evidence.reference_digest == _reference().digest
    assert evidence.monitor_id == ADAPT_MONITOR_ID
    assert evidence.monitor_version == ADAPT_MONITOR_VERSION
    assert evidence.source_integrity == "not_cryptographically_verified"
    assert evidence.source_independence == "channel_derived_not_independent"
    assert not ({"statistic", "threshold"} & {field.name for field in dataclasses.fields(evidence)})


def test_passive_monitor_emitted_verdict_set_excludes_adversarial_and_not_applicable(monkeypatch):
    emitted = set()
    for whiteness_pass, nis_pass in ((True, True), (False, True), (True, False), (False, False)):
        result = SimpleNamespace(
            whiteness_pass=whiteness_pass,
            nis_pass=nis_pass,
            nis_statistic=2200.0,
            nis_lower_threshold=1877.0,
            nis_upper_threshold=2126.0,
        )
        monkeypatch.setattr("qkd.adaptive.monitor.innovation_diagnostic", lambda *_, r=result: r)
        emitted.add(_evaluate(_consistent(11)).verdict)
    emitted.add(_evaluate(_consistent(12, n_steps=EFFECTIVE_N - 1)).verdict)
    assert emitted == {
        AttributionVerdict.ENVIRONMENT_CONSISTENT,
        AttributionVerdict.UNEXPLAINED,
        AttributionVerdict.INSUFFICIENT_EVIDENCE,
    }


def _counts(generator, seeds):
    whiteness = 0
    nis = 0
    unexplained = 0
    for index, seed in enumerate(seeds):
        trace = generator(seed, index)
        evidence = _evaluate(trace)
        whiteness += evidence.reason_codes[0] == "whiteness_reject"
        nis += evidence.reason_codes[1] in {"nis_reject_high", "nis_reject_low"}
        unexplained += evidence.verdict is AttributionVerdict.UNEXPLAINED
    return whiteness, nis, unexplained


def test_reference_consistent_component_null_rates_and_familywise_upper_bound():
    seeds = _seed_map()["null_consistent"]
    whiteness, nis, combined = _counts(lambda seed, _: _consistent(seed), seeds)
    lo, hi = NULL_COMPONENT_BAND
    assert lo <= whiteness <= hi
    assert lo <= nis <= hi
    assert combined <= COMBINED_UPPER_COUNT


def test_matched_law_replacement_remains_environment_consistent_at_null_rates():
    reference = _reference()

    def generator(seed, index):
        return generate_matched_law_trace(
            reference=reference,
            trace_id=f"matched-{index}",
            link_id="link-1",
            window_start_utc=TRACE_START,
            sample_interval_us=SAMPLE_INTERVAL_US,
            seed=seed,
        )

    whiteness, nis, combined = _counts(generator, _seed_map()["matched_law"])
    lo, hi = NULL_COMPONENT_BAND
    assert lo <= whiteness <= hi
    assert lo <= nis <= hi
    assert combined <= COMBINED_UPPER_COUNT
    assert NULL_RUNS - combined >= 168


@pytest.mark.parametrize(
    ("purpose", "generator", "required_code"),
    [
        (
            "variance_inflated_high",
            lambda reference, seed, index: generate_variance_inflated_trace(
                reference,
                r_factor=2.0,
                trace_id=f"high-{index}",
                link_id="link-1",
                window_start_utc=TRACE_START,
                sample_interval_us=SAMPLE_INTERVAL_US,
                seed=seed,
            ),
            "nis_reject_high",
        ),
        (
            "variance_inflated_low",
            lambda reference, seed, index: generate_variance_inflated_trace(
                reference,
                r_factor=0.5,
                trace_id=f"low-{index}",
                link_id="link-1",
                window_start_utc=TRACE_START,
                sample_interval_us=SAMPLE_INTERVAL_US,
                seed=seed,
            ),
            "nis_reject_low",
        ),
        (
            "law_shifted",
            lambda reference, seed, index: generate_law_shifted_trace(
                reference,
                f_true=0.2,
                trace_id=f"law-{index}",
                link_id="link-1",
                window_start_utc=TRACE_START,
                sample_interval_us=SAMPLE_INTERVAL_US,
                seed=seed,
            ),
            "whiteness_reject",
        ),
    ],
)
def test_predeclared_variance_and_law_shift_effects_meet_power_floor(
    purpose, generator, required_code
):
    reference = _reference()
    detections = 0
    for index, seed in enumerate(_seed_map()[purpose]):
        evidence = _evaluate(generator(reference, seed, index))
        detections += required_code in evidence.reason_codes
    assert detections >= POWER_MINIMUM_COUNT


def test_quasiperiodic_arms_meet_power_floor_and_no_golden_advantage_is_asserted():
    reference = _reference()
    steps = {
        "quasiperiodic_golden": 137.50776405003785,
        "quasiperiodic_sqrt2": 360.0 * (math.sqrt(2.0) - 1.0),
        "quasiperiodic_rational": 137.5,
    }
    counts = {}
    for purpose, step in steps.items():
        count = 0
        for index, seed in enumerate(_seed_map()[purpose]):
            trace = generate_quasiperiodic_drift_trace(
                reference,
                amplitude=1.0,
                step_deg=step,
                trace_id=f"{purpose}-{index}",
                link_id="link-1",
                window_start_utc=TRACE_START,
                sample_interval_us=SAMPLE_INTERVAL_US,
                seed=seed,
            )
            count += _evaluate(trace).verdict is AttributionVerdict.UNEXPLAINED
        counts[purpose] = count
        assert count >= POWER_MINIMUM_COUNT
    assert abs(counts["quasiperiodic_golden"] - counts["quasiperiodic_sqrt2"]) <= 7


def test_synthetic_generators_and_evidence_are_seed_deterministic():
    seed = _seed_map()["determinism"][0]
    first = _consistent(seed)
    second = _consistent(seed)
    assert first == second
    first_bytes = to_canonical_json(_evaluate(first), schema_version=ADAPTIVE_SCHEMA_VERSION)
    second_bytes = to_canonical_json(_evaluate(second), schema_version=ADAPTIVE_SCHEMA_VERSION)
    assert first_bytes == second_bytes


def test_fixture_lane_contains_no_uncited_global_discrepancy_optimality_claim():
    source = (_SRC / "fixtures" / "quasiperiodic.py").read_text(encoding="utf-8").lower()
    design_note = (
        _ROOT / "docs" / "notes" / "DN-quasiperiodic-misalignment.md"
    ).read_text(encoding="utf-8").lower()
    forbidden = (
        "globally optimal discrepancy",
        "globally minimizes discrepancy",
        "best discrepancy of every irrational",
        "pointwise optimal discrepancy",
    )
    assert all(phrase not in source for phrase in forbidden)
    assert "bounded-type discrepancy" in source
    assert "bounded_over_declared_range" in design_note
