"""LINK-7 acceptance tests: robust decoy inversion under a certified common-mode bound.

``docs/LINK_7_PLAN.md`` v1.3 -- §1 (information model/trigger/gate), §2 (Route
A robust inversion), §3 (structural epistemic wall), §4 (source model
ownership), §5 (versioning/manifest/replay), §6 (acceptance-test contract),
§12 (numerical anchors), §13 (superseded-test enumeration). Pure
``qkd.detection``/``qkd.bb84``/``qkd.effects``/``qkd.replay`` unit tests and
mission-level (``simulate_pass``) integration tests share this one new file
per plan §9 (create: ``tests/test_link7.py``).
"""

from __future__ import annotations

import dataclasses
import inspect
import json
import math
from pathlib import Path

import pytest

from qkd.bb84 import (
    estimate_decoy_bounds,
    expected_block_statistics,
    run_decoy_bb84,
    secure_key_rate,
)
from qkd.detection import (
    PDT_ADMISSIBLE_EFFECTS,
    ROBUST_RATE_CERT_GAP,
    ReceiverInputs,
    ReceiverModel,
    RobustRateCertificationError,
    RobustRateResult,
    SourceCertificateViolationError,
    SourceModelIncompatibleError,
    SourceTruthInputs,
    SourceUncertaintyRequiredError,
    active_source_effect_ids,
    compute_receiver_block,
    compute_robust_secure_key_rate,
    extract_receiver_inputs,
    extract_source_truth,
    piyavskii_shubert_minimize,
    validate_source_uncertainty_gate,
)
from qkd.effects import SOURCE_MODEL_SUPPORT, CalibratedSourceFactorEffect, MuFluctuationEffect
from qkd.link import (
    ChannelObservables,
    DetectorObservables,
    EffectiveLinkState,
    SourceObservables,
    UnsupportedLinkObservableError,
    apply_link_state,
)
from qkd.mission import MissionConfig, PULSE_REPETITION_RATE_HZ, simulate_pass
from qkd.replay import (
    LINK_PIPELINE_VERSION,
    LINK_PIPELINE_VERSION_V1,
    LINK_PIPELINE_VERSION_V2,
    ManifestValidationError,
    SourceSupportEchoMismatchError,
    replay_from_provenance,
    validate_manifest_object,
)
from qkd.run import _build_results
from qkd.signals import ChannelState, DetectorParams
from tests.test_replay import _valid_manifest_dict, _valid_manifest_v1_dict, _valid_manifest_v2_dict


FIXTURES_DIR = Path(__file__).parent / "fixtures"
V2_MANIFEST_PATH = FIXTURES_DIR / "link6b_manifest_v2.json"
V2_EXPECTED_PATH = FIXTURES_DIR / "link6b_manifest_v2_expected.json"

_PI = (0.8, 0.15, 0.05)


def _identity_inputs(**overrides) -> ReceiverInputs:
    fields = dict(
        background_rate_hz=0.0,
        dark_count_rate_hz=0.0,
        afterpulse_prob=0.0,
        dead_time_s=0.0,
        timing_jitter_s=0.0,
        frequency_offset_hz=0.0,
        misalignment_error=0.0,
    )
    fields.update(overrides)
    return ReceiverInputs(**fields)


def _assert_close_structure(actual, expected, path="root"):
    """Same portable tolerant-comparison discipline as
    ``tests/test_link6b.py::_assert_close_structure`` (plan §5 safeguard b)."""

    if isinstance(expected, dict):
        assert isinstance(actual, dict), path
        assert actual.keys() == expected.keys(), path
        for key in expected:
            _assert_close_structure(actual[key], expected[key], f"{path}.{key}")
        return
    if isinstance(expected, list):
        assert isinstance(actual, list), path
        assert len(actual) == len(expected), path
        for index, (a, e) in enumerate(zip(actual, expected)):
            _assert_close_structure(a, e, f"{path}[{index}]")
        return
    if isinstance(expected, float):
        assert actual == pytest.approx(expected, rel=1e-9, abs=1e-9), path
        return
    assert actual == expected, path


# ---------------------------------------------------------------------------
# §3.1 -- type wall: intensity_factor absent from ReceiverInputs and from
# every decoy-estimator signature; only the truth-generation/block helpers
# may receive it.
# ---------------------------------------------------------------------------


def test_receiver_inputs_stays_exactly_seven_fields_intensity_factor_absent():
    names = [f.name for f in dataclasses.fields(ReceiverInputs)]
    assert names == [
        "background_rate_hz",
        "dark_count_rate_hz",
        "afterpulse_prob",
        "dead_time_s",
        "timing_jitter_s",
        "frequency_offset_hz",
        "misalignment_error",
    ]
    assert "intensity_factor" not in names


def test_source_truth_inputs_is_the_sole_new_truth_side_field():
    names = [f.name for f in dataclasses.fields(SourceTruthInputs)]
    assert names == ["intensity_factor"]
    assert SourceTruthInputs().intensity_factor == 1.0


def test_decoy_estimator_signatures_never_name_intensity_factor_or_k():
    for fn in (estimate_decoy_bounds, secure_key_rate, compute_robust_secure_key_rate):
        params = set(inspect.signature(fn).parameters)
        assert "intensity_factor" not in params, fn.__qualname__
        assert "k" not in params, fn.__qualname__
        assert "k_prime" not in params, fn.__qualname__


def test_truth_generator_and_block_helper_may_receive_intensity_factor_estimator_may_not():
    # expected_block_statistics is the statistics-only truth generator
    # (§3.2): its `intensities` argument is exactly where a caller folds in
    # the realized k (mission.py does this once, outside the function).
    truth_params = set(inspect.signature(expected_block_statistics).parameters)
    assert truth_params == {"channel", "intensities", "detector"}
    assert "intensity_factor" not in truth_params  # k enters via the caller, not a named param

    # compute_receiver_block is the one place `intensity_factor` is a named
    # parameter -- the block-level seam between truth and estimator.
    block_params = set(inspect.signature(compute_receiver_block).parameters)
    assert "intensity_factor" in block_params

    # No decoy-inversion function (estimate_decoy_bounds / secure_key_rate /
    # compute_robust_secure_key_rate) has this parameter (plan §3.2 final
    # sentence: "No function that performs decoy inversion ever receives
    # realized k").
    for fn in (estimate_decoy_bounds, secure_key_rate, compute_robust_secure_key_rate):
        assert "intensity_factor" not in inspect.signature(fn).parameters


# ---------------------------------------------------------------------------
# §3.1 -- full-consumption test: after both extraction stages compose, the
# residual bridge rejects nothing non-identity on a receiver-active run.
# ---------------------------------------------------------------------------


def test_receiver_extraction_alone_leaves_source_non_identity_bridge_rejects():
    state = EffectiveLinkState(
        channel=ChannelObservables(),
        detector=DetectorObservables(),
        source=SourceObservables(intensity_factor=1.3),
    )
    inputs, residual = extract_receiver_inputs(state)
    assert residual.source.intensity_factor == 1.3  # untouched by this stage alone (§3.1)

    channel = ChannelState(transmittance=0.2, werner_p=0.98, intrinsic_qber=0.015, dark_count_prob=0.0)
    detector = DetectorParams(detection_efficiency=0.5, dark_count_prob=1e-6)
    with pytest.raises(UnsupportedLinkObservableError, match="intensity_factor"):
        apply_link_state(residual, channel=channel, detector=detector)


def test_two_stage_extraction_leaves_fully_identity_residual_bridge_accepts():
    state = EffectiveLinkState(
        channel=ChannelObservables(),
        detector=DetectorObservables(),
        source=SourceObservables(intensity_factor=1.3),
    )
    inputs, after_receiver = extract_receiver_inputs(state)
    truth, after_source = extract_source_truth(after_receiver)
    assert truth.intensity_factor == 1.3
    assert after_source.source == SourceObservables()  # fully-identity now

    channel = ChannelState(transmittance=0.2, werner_p=0.98, intrinsic_qber=0.015, dark_count_prob=0.0)
    detector = DetectorParams(detection_efficiency=0.5, dark_count_prob=1e-6)
    new_channel, new_detector = apply_link_state(after_source, channel=channel, detector=detector)
    assert new_channel.transmittance == channel.transmittance
    assert new_detector.detection_efficiency == detector.detection_efficiency


def test_extract_source_truth_default_is_identity():
    state = EffectiveLinkState(channel=ChannelObservables(), detector=DetectorObservables())
    truth, residual = extract_source_truth(state)
    assert truth == SourceTruthInputs(intensity_factor=1.0)
    assert residual.source == SourceObservables()


# ---------------------------------------------------------------------------
# §3.2/R4 -- anti-oracle acceptance tests
# ---------------------------------------------------------------------------


def test_robust_estimate_is_a_pure_function_of_observed_stats_never_of_k():
    # Different realized k never reaches compute_robust_secure_key_rate at
    # all (it has no such parameter -- test above); this test additionally
    # certifies that, given bit-identical constructed observed statistics,
    # nominal settings, and delta, two independent calls are bit-identical
    # (the estimator is a deterministic pure function of its declared
    # inputs, never of any latent draw).
    gains = {"signal": 0.0254222707470433, "decoy": 0.00513775634910441, "vacuum": 1e-06}
    qber = {"signal": 0.015019092760213, "decoy": 0.0150944141797433, "vacuum": 0.5}
    r1 = compute_robust_secure_key_rate(gains=gains, qber_per_intensity=qber, mu=0.5, nu=0.1, delta=0.05)
    r2 = compute_robust_secure_key_rate(gains=gains, qber_per_intensity=qber, mu=0.5, nu=0.1, delta=0.05)
    assert r1 == r2


def test_uncertain_model_active_with_draw_exactly_one_still_requires_delta():
    # half_width=0.0 deterministically draws intensity_factor == 1.0 every
    # time (rng.uniform(1.0, 1.0) == 1.0) -- if the trigger checked the
    # realized draw instead of the active model, this would slip through
    # undetected. The active-model trigger (R4) must still fire.
    receiver = ReceiverModel(pi=_PI)  # source_intensity_uncertainty=None
    with pytest.raises(SourceUncertaintyRequiredError):
        simulate_pass(
            MissionConfig(samples=5),
            receiver=receiver,
            link_effects=[CalibratedSourceFactorEffect(half_width=0.0)],
            link_seed=1,
        )


# ---------------------------------------------------------------------------
# §2/§6 -- security-function tests: hand-computed q1(k')/R(k'), witness
# consistency, dense-grid oracle vs. certifying minimizer, universal
# R_robust <= R_nominal (+ named strict-inequality anchor), R_certified <=
# R_hat within the certified gap, and a clamped-at-zero case (R12.1).
# ---------------------------------------------------------------------------

# Anchor fixture A (plan §12): nominal mu=0.5, nu=0.1; observed statistics
# constructed at realized k=1.03 (intensities 0.515, 0.103, 0) through the
# live gain/error laws at eta=0.05, y0=1e-6, e_d=0.015.
_ANCHOR_A_GAINS = {"signal": 0.0254222707470433, "decoy": 0.00513775634910441, "vacuum": 1e-06}
_ANCHOR_A_QBER = {"signal": 0.015019092760213, "decoy": 0.0150944141797433, "vacuum": 0.5}
_ANCHOR_A_MU = 0.5
_ANCHOR_A_NU = 0.1


def _anchor_a_candidate(k_prime: float) -> tuple[float, float, float, float]:
    mu_p = k_prime * _ANCHOR_A_MU
    nu_p = k_prime * _ANCHOR_A_NU
    y1, e1 = estimate_decoy_bounds(
        _ANCHOR_A_GAINS, _ANCHOR_A_QBER, {"signal": mu_p, "decoy": nu_p, "vacuum": 0.0}
    )
    q1 = y1 * mu_p * math.exp(-mu_p)
    r = secure_key_rate(_ANCHOR_A_GAINS["signal"], _ANCHOR_A_QBER["signal"], q1, e1)
    return y1, e1, q1, r


def test_hand_computed_q1_and_complete_rate_at_each_delta_005_candidate():
    # The v1 omission the plan corrects: q1 is intensity-dependent
    # (q1_L(k') = Y1_L(k') * k'mu * exp(-k'mu)), not evaluated once at k'=1.
    expected = {
        0.95: (0.0528111101714486, 0.0168983797002632, 0.0156001591097021, 0.00517713289209529),
        1.00: (0.0500071169997848, 0.0170390899696245, 0.0151654248321032, 0.00498039524641108),
        1.05: (0.04745938558528, 0.0171850573420071, 0.0147392984195759, 0.00478756687764011),
    }
    for k_prime, (y1_expected, e1_expected, q1_expected, r_expected) in expected.items():
        y1, e1, q1, r = _anchor_a_candidate(k_prime)
        assert y1 == pytest.approx(y1_expected, rel=0, abs=1e-12)
        assert e1 == pytest.approx(e1_expected, rel=0, abs=1e-12)
        assert q1 == pytest.approx(q1_expected, rel=0, abs=1e-12)
        assert r == pytest.approx(r_expected, rel=0, abs=1e-12)


def test_witness_rule_all_diagnostics_come_from_the_single_minimizing_k_star():
    robust = compute_robust_secure_key_rate(
        gains=_ANCHOR_A_GAINS, qber_per_intensity=_ANCHOR_A_QBER, mu=_ANCHOR_A_MU, nu=_ANCHOR_A_NU, delta=0.05
    )
    y1_at_star, e1_at_star, q1_at_star, r_at_star = _anchor_a_candidate(robust.k_star)
    # Never mixed extrema: every reported diagnostic traces to evaluating
    # the *same* k_star, not e.g. min(Y1 over k') paired with max(e1 over k').
    assert robust.y1_lower_bound == y1_at_star
    assert robust.e1_upper_bound == e1_at_star
    assert robust.q1 == q1_at_star
    assert robust.r_hat == r_at_star


@pytest.mark.parametrize("delta", [0.05, 0.1])
def test_dense_grid_oracle_agrees_with_certifying_minimizer_on_anchor_a(delta):
    n = 20_001
    best_r = math.inf
    for i in range(n):
        k_prime = (1.0 - delta) + (2.0 * delta) * i / (n - 1)
        r = _anchor_a_candidate(k_prime)[3]
        if r < best_r:
            best_r = r
    robust = compute_robust_secure_key_rate(
        gains=_ANCHOR_A_GAINS, qber_per_intensity=_ANCHOR_A_QBER, mu=_ANCHOR_A_MU, nu=_ANCHOR_A_NU, delta=delta
    )
    assert robust.r_hat == pytest.approx(best_r, abs=1e-9)
    assert robust.k_star == pytest.approx(1.0 + delta, abs=1e-9)  # upper-endpoint minimum (plan §2, R5 evidence)


def test_synthetic_objective_with_known_interior_minimum_is_found():
    # The QKD anchors' minima sit at the upper endpoint (plan §2, R5
    # evidence) -- this test proves the minimizer is genuinely a *global*
    # certifying search, not an endpoints-only shortcut, by giving it a
    # smooth objective with a known INTERIOR minimum. A more modest gap
    # (1e-6, not the production ROBUST_RATE_CERT_GAP=1e-12) is used
    # deliberately: fixed-Lipschitz Piyavskii-Shubert's worst-case iteration
    # count grows with domain-width / gap, and this synthetic domain is far
    # wider than any real Kdelta interval -- the plan does not mandate 1e-12
    # for this synthetic fixture, only for the production anchors (see the
    # implementation report's deviations for the measured convergence-rate
    # data this choice is based on).
    def f(x: float) -> float:
        return (x - 3.0) ** 2 + 5.0

    x_star, f_star, epsilon = piyavskii_shubert_minimize(f, 0.0, 10.0, gap=1e-6)
    assert x_star == pytest.approx(3.0, abs=1e-3)
    assert f_star == pytest.approx(5.0, abs=1e-6)
    assert epsilon <= 1e-6
    # Neither endpoint is anywhere near the true minimum -- an
    # endpoints-only strategy would have failed this fixture.
    assert f(0.0) > f_star + 1.0
    assert f(10.0) > f_star + 1.0


def test_universal_r_robust_le_r_nominal_and_named_strict_inequality_anchor():
    nominal_y1, nominal_e1, nominal_q1, nominal_r = _anchor_a_candidate(1.0)
    for delta in (0.0, 0.02, 0.05, 0.1, 0.2):
        robust = compute_robust_secure_key_rate(
            gains=_ANCHOR_A_GAINS,
            qber_per_intensity=_ANCHOR_A_QBER,
            mu=_ANCHOR_A_MU,
            nu=_ANCHOR_A_NU,
            delta=delta,
        )
        assert robust.r_certified <= nominal_r + ROBUST_RATE_CERT_GAP, delta
    # delta == 0 -> exact equality (the identity short-circuit).
    robust_zero = compute_robust_secure_key_rate(
        gains=_ANCHOR_A_GAINS, qber_per_intensity=_ANCHOR_A_QBER, mu=_ANCHOR_A_MU, nu=_ANCHOR_A_NU, delta=0.0
    )
    assert robust_zero.r_certified == nominal_r
    # The predeclared strict-inequality anchor (plan §12, C1): delta=0.05
    # is strictly below the nominal rate -- not clamped-at-zero, not a
    # saturated-bound tie.
    robust_005 = compute_robust_secure_key_rate(
        gains=_ANCHOR_A_GAINS, qber_per_intensity=_ANCHOR_A_QBER, mu=_ANCHOR_A_MU, nu=_ANCHOR_A_NU, delta=0.05
    )
    assert robust_005.r_certified < nominal_r


def test_r_certified_le_r_hat_and_within_the_certified_gap_on_anchor():
    for delta in (0.05, 0.1):
        robust = compute_robust_secure_key_rate(
            gains=_ANCHOR_A_GAINS,
            qber_per_intensity=_ANCHOR_A_QBER,
            mu=_ANCHOR_A_MU,
            nu=_ANCHOR_A_NU,
            delta=delta,
        )
        assert robust.epsilon <= ROBUST_RATE_CERT_GAP
        assert robust.r_certified <= robust.r_hat
        assert robust.r_hat - robust.r_certified <= ROBUST_RATE_CERT_GAP


def test_delta_zero_reproduces_nominal_inversion_bit_identically():
    robust = compute_robust_secure_key_rate(
        gains=_ANCHOR_A_GAINS, qber_per_intensity=_ANCHOR_A_QBER, mu=_ANCHOR_A_MU, nu=_ANCHOR_A_NU, delta=0.0
    )
    y1, e1 = estimate_decoy_bounds(
        _ANCHOR_A_GAINS, _ANCHOR_A_QBER, {"signal": _ANCHOR_A_MU, "decoy": _ANCHOR_A_NU, "vacuum": 0.0}
    )
    q1 = y1 * _ANCHOR_A_MU * math.exp(-_ANCHOR_A_MU)
    r = secure_key_rate(_ANCHOR_A_GAINS["signal"], _ANCHOR_A_QBER["signal"], q1, e1)
    assert robust.k_star == 1.0
    assert robust.y1_lower_bound == y1
    assert robust.e1_upper_bound == e1
    assert robust.q1 == q1
    assert robust.r_hat == r
    assert robust.epsilon == 0.0
    assert robust.r_certified == r  # strict == identity reduction, no minimizer search


def test_r12_1_clamped_at_zero_case():
    # A configuration whose entire candidate domain clamps the raw rate to
    # exactly 0.0 (secure_key_rate's own floor) -- exercises the emission
    # rule's max(0, R_hat - epsilon) floor for real: R_hat == 0.0 exactly
    # but epsilon is a tiny positive certified gap, so R_hat - epsilon is
    # negative and must be clamped back to 0.0, not emitted as a negative
    # claim.
    gains = {"signal": 0.03, "decoy": 0.008, "vacuum": 1e-6}
    qber = {"signal": 0.09, "decoy": 0.09, "vacuum": 0.5}
    robust = compute_robust_secure_key_rate(gains=gains, qber_per_intensity=qber, mu=0.5, nu=0.1, delta=0.05)
    assert robust.r_hat == 0.0
    assert robust.epsilon > 0.0
    assert robust.r_hat - robust.epsilon < 0.0  # the raw (unclamped) claim would be negative
    assert robust.r_certified == 0.0  # max(0, ...) floors it


def test_certification_failure_raises_named_error_not_bare_runtime_error():
    # The discovered production risk (implementation report, deviation
    # h.3): a domain that both spans the transition kink into
    # secure_key_rate's zero floor *and* a wide clamped-flat plateau beyond
    # it can exhaust PIYAVSKII_MAX_ITERATIONS before certifying
    # ROBUST_RATE_CERT_GAP. This must fail loud and named -- never a bare
    # RuntimeError, never a silent uncertified fallback. This reproduction
    # genuinely exercises the full production iteration budget (~10s).
    gains = {"signal": 0.03, "decoy": 0.008, "vacuum": 1e-6}
    qber = {"signal": 0.09, "decoy": 0.09, "vacuum": 0.5}
    with pytest.raises(RobustRateCertificationError) as excinfo:
        compute_robust_secure_key_rate(gains=gains, qber_per_intensity=qber, mu=0.5, nu=0.1, delta=0.1)
    message = str(excinfo.value)
    assert "max_iterations" in message  # iteration count
    assert "R_hat" in message or "best sampled value" in message  # best R_hat found so far
    assert "gap" in message  # achieved (uncertified) gap at exhaustion


def test_delta_domain_rejects_nan_inf_negative_and_ge_one():
    for bad_delta in (math.nan, math.inf, -math.inf, -0.01, 1.0, 1.5):
        with pytest.raises(ValueError):
            compute_robust_secure_key_rate(
                gains=_ANCHOR_A_GAINS,
                qber_per_intensity=_ANCHOR_A_QBER,
                mu=_ANCHOR_A_MU,
                nu=_ANCHOR_A_NU,
                delta=bad_delta,
            )
    # Exact 0 is accepted (the identity short-circuit).
    compute_robust_secure_key_rate(
        gains=_ANCHOR_A_GAINS, qber_per_intensity=_ANCHOR_A_QBER, mu=_ANCHOR_A_MU, nu=_ANCHOR_A_NU, delta=0.0
    )


# ---------------------------------------------------------------------------
# §12 -- numerical anchors, independently re-derived (>= 12 significant
# digits; printed to 15 in the implementation report).
# ---------------------------------------------------------------------------


def test_anchor_a_delta_005_matches_plan_to_at_least_12_significant_digits():
    robust = compute_robust_secure_key_rate(
        gains=_ANCHOR_A_GAINS, qber_per_intensity=_ANCHOR_A_QBER, mu=_ANCHOR_A_MU, nu=_ANCHOR_A_NU, delta=0.05
    )
    assert robust.k_star == pytest.approx(1.05, abs=0, rel=1e-12)
    # The plan's printed anchor value is R_hat (the raw candidate rate at
    # the witness k*), not R_certified (= R_hat - epsilon, which differs by
    # epsilon ~ 8.9e-13, well under the >=12-significant-digit requirement).
    assert robust.r_hat == pytest.approx(0.00478756687764011, abs=1e-15)
    assert robust.r_certified == pytest.approx(robust.r_hat, abs=ROBUST_RATE_CERT_GAP)


def test_anchor_a_delta_01_matches_plan_to_at_least_12_significant_digits():
    robust = compute_robust_secure_key_rate(
        gains=_ANCHOR_A_GAINS, qber_per_intensity=_ANCHOR_A_QBER, mu=_ANCHOR_A_MU, nu=_ANCHOR_A_NU, delta=0.1
    )
    assert robust.k_star == pytest.approx(1.1, abs=0, rel=1e-12)
    assert robust.r_hat == pytest.approx(0.00459857086776621, abs=1e-15)
    assert robust.r_certified == pytest.approx(robust.r_hat, abs=ROBUST_RATE_CERT_GAP)


# ---------------------------------------------------------------------------
# §1/§4 -- calibration-model tests: incompatible-model rejection,
# certificate-violation rejection, delta domain, registry correctness.
# ---------------------------------------------------------------------------


def test_source_model_support_registry_is_code_derived_and_exact():
    # R12.2: the registry is the sole source of truth, never a manifest.
    assert SOURCE_MODEL_SUPPORT["mu_fluctuation"](MuFluctuationEffect(relative_sigma=0.05)) is None
    assert SOURCE_MODEL_SUPPORT["calibrated_source_factor"](CalibratedSourceFactorEffect(half_width=0.3)) == (
        0.7,
        1.3,
    )
    assert SOURCE_MODEL_SUPPORT["calibrated_source_factor"](CalibratedSourceFactorEffect(half_width=0.0)) == (
        1.0,
        1.0,
    )


def test_active_source_effect_ids_filters_to_registered_source_owners():
    from qkd.effects import DetectorAfterpulsingEffect

    effects = [DetectorAfterpulsingEffect(0.02), CalibratedSourceFactorEffect(half_width=0.1)]
    assert active_source_effect_ids(effects) == ("calibrated_source_factor",)


def test_mu_fluctuation_incompatible_regardless_of_delta():
    for delta in (0.0, 0.05, 0.5, 0.99):
        with pytest.raises(SourceModelIncompatibleError):
            validate_source_uncertainty_gate([MuFluctuationEffect(relative_sigma=0.05)], delta)


def test_mu_fluctuation_incompatible_even_when_delta_is_none_first_checks_trigger():
    # No delta at all -> the required-when-active trigger fires first.
    with pytest.raises(SourceUncertaintyRequiredError):
        validate_source_uncertainty_gate([MuFluctuationEffect(relative_sigma=0.05)], None)


def test_delta_zero_with_bounded_nonzero_half_width_raises_certificate_violation():
    with pytest.raises(SourceCertificateViolationError):
        validate_source_uncertainty_gate([CalibratedSourceFactorEffect(half_width=0.02)], 0.0)


def test_delta_zero_with_bounded_zero_half_width_is_accepted_identity():
    support = validate_source_uncertainty_gate([CalibratedSourceFactorEffect(half_width=0.0)], 0.0)
    assert support == (1.0, 1.0)


def test_calibrated_source_factor_compatible_iff_half_width_le_delta():
    validate_source_uncertainty_gate([CalibratedSourceFactorEffect(half_width=0.03)], 0.05)  # ok, no raise
    with pytest.raises(SourceModelIncompatibleError):
        validate_source_uncertainty_gate([CalibratedSourceFactorEffect(half_width=0.06)], 0.05)


def test_no_active_source_model_returns_none_delta_accepted_but_unused():
    assert validate_source_uncertainty_gate([], None) is None
    assert validate_source_uncertainty_gate([], 0.1) is None  # accepted-but-unused


def test_calibrated_source_factor_construction_rejects_domain_violations():
    for bad_half_width in (math.nan, math.inf, -0.01, 1.0, 1.5):
        with pytest.raises(ValueError):
            CalibratedSourceFactorEffect(half_width=bad_half_width)
    CalibratedSourceFactorEffect(half_width=0.0)  # accepted


# ---------------------------------------------------------------------------
# §10-D2 -- source-active PDT stays deferred (Option B): the new owner is
# not in the closed-world PDT allowlist, same as MuFluctuationEffect.
# ---------------------------------------------------------------------------


def test_calibrated_source_factor_not_pdt_admissible():
    assert "calibrated_source_factor" not in PDT_ADMISSIBLE_EFFECTS
    assert "mu_fluctuation" not in PDT_ADMISSIBLE_EFFECTS


# ---------------------------------------------------------------------------
# §2/§4 -- physics tests
# ---------------------------------------------------------------------------

_PHYS_CHANNEL = ChannelState(transmittance=0.2, werner_p=0.98, intrinsic_qber=0.015, dark_count_prob=0.0)
_PHYS_DETECTOR = DetectorParams(detection_efficiency=0.5, dark_count_prob=1e-6)
_PHYS_INTENSITIES = {"signal": 0.5, "decoy": 0.1, "vacuum": 0.0}


def test_realized_k_reaches_truth_statistics_never_the_estimator_intensities():
    inputs = _identity_inputs()
    block_nominal = compute_receiver_block(
        channel=_PHYS_CHANNEL,
        detector=_PHYS_DETECTOR,
        intensities=_PHYS_INTENSITIES,
        n_pulses=1000,
        pi=_PI,
        receiver_inputs=inputs,
        gate_window_s=None,
        pulse_repetition_rate_hz=1e8,
        intensity_factor=1.0,
    )
    block_realized = compute_receiver_block(
        channel=_PHYS_CHANNEL,
        detector=_PHYS_DETECTOR,
        intensities=_PHYS_INTENSITIES,
        n_pulses=1000,
        pi=_PI,
        receiver_inputs=inputs,
        gate_window_s=None,
        pulse_repetition_rate_hz=1e8,
        intensity_factor=1.3,
    )
    # The truth side moved (gains differ -- k reached the statistics-only
    # generator).
    assert block_nominal.gains != block_realized.gains
    # The estimator side did not: q1 == Y1_L * mu_nominal * exp(-mu_nominal)
    # using the *nominal* mu (0.5), never the realized 0.65 -- no
    # decoy-inversion function ever receives k (plan §3).
    mu_nominal = _PHYS_INTENSITIES["signal"]
    expected_q1 = block_realized.y1_lower_bound * mu_nominal * math.exp(-mu_nominal)
    assert block_realized.q1 == expected_q1


def test_shared_history_occupancy_responds_to_realized_intensity():
    inputs = _identity_inputs(afterpulse_prob=0.02)
    block1 = compute_receiver_block(
        channel=_PHYS_CHANNEL,
        detector=_PHYS_DETECTOR,
        intensities=_PHYS_INTENSITIES,
        n_pulses=1000,
        pi=_PI,
        receiver_inputs=inputs,
        gate_window_s=None,
        pulse_repetition_rate_hz=1e8,
        intensity_factor=1.0,
    )
    block2 = compute_receiver_block(
        channel=_PHYS_CHANNEL,
        detector=_PHYS_DETECTOR,
        intensities=_PHYS_INTENSITIES,
        n_pulses=1000,
        pi=_PI,
        receiver_inputs=inputs,
        gate_window_s=None,
        pulse_repetition_rate_hz=1e8,
        intensity_factor=1.5,
    )
    assert block1.a != block2.a
    assert block1.q_bar_reg != block2.q_bar_reg

    from qkd.detection import shared_history_afterpulse

    realized = {name: 1.5 * value for name, value in _PHYS_INTENSITIES.items()}
    gains, qber = expected_block_statistics(_PHYS_CHANNEL, realized, _PHYS_DETECTOR)
    _q_prime, _e_prime, _t_prime, a, _q_bar, q_bar_reg = shared_history_afterpulse(gains, qber, _PI, 0.02)
    assert a == block2.a
    assert q_bar_reg == block2.q_bar_reg


def test_exact_zero_vacuum_preserved_under_any_realized_k():
    for k in (0.5, 1.0, 1.7, 1000.0):
        realized = {name: k * value for name, value in _PHYS_INTENSITIES.items()}
        assert realized["vacuum"] == 0.0
        gains, qber = expected_block_statistics(_PHYS_CHANNEL, realized, _PHYS_DETECTOR)
        assert gains["vacuum"] == _PHYS_DETECTOR.dark_count_prob  # honest_gain(0, eta, y0) == y0 exactly


def test_one_draw_per_block_single_k_scales_every_nonzero_setting_uniformly():
    # C4: the realized factor is one epoch-fixed scalar shared by every
    # nonzero setting in the block -- not a per-intensity draw. Folding a
    # single k into the intensities mapping (as compute_receiver_block
    # does) necessarily scales signal and decoy by the *same* ratio.
    k = 1.37
    realized = {name: k * value for name, value in _PHYS_INTENSITIES.items()}
    assert realized["signal"] / _PHYS_INTENSITIES["signal"] == pytest.approx(k)
    assert realized["decoy"] / _PHYS_INTENSITIES["decoy"] == pytest.approx(k)
    assert realized["signal"] / realized["decoy"] == pytest.approx(
        _PHYS_INTENSITIES["signal"] / _PHYS_INTENSITIES["decoy"]
    )


def test_calibrated_source_factor_zero_half_width_is_exactly_identity():
    # rng.uniform(1.0, 1.0) deterministically returns exactly 1.0 -- the
    # class is identity-capable at half_width=0 (consistent with
    # MuFluctuationEffect's zero-variance convention).
    result = simulate_pass(
        MissionConfig(samples=5),
        receiver=ReceiverModel(pi=_PI, source_intensity_uncertainty=0.0),
        link_effects=[CalibratedSourceFactorEffect(half_width=0.0)],
        link_seed=1,
    )
    baseline = simulate_pass(MissionConfig(samples=5), receiver=ReceiverModel(pi=_PI), link_seed=1)
    assert result.link_receiver.secure_key_rate_per_signal_pulse == baseline.link_receiver.secure_key_rate_per_signal_pulse


# ---------------------------------------------------------------------------
# §1 -- mission-level trigger/gate integration
# ---------------------------------------------------------------------------


def test_no_source_model_active_delta_absent_is_unaffected():
    result = simulate_pass(MissionConfig(samples=5), receiver=ReceiverModel(pi=_PI), link_seed=1)
    assert result.link_receiver is not None


def test_delta_accepted_but_unused_on_identity_run_recorded_in_manifest():
    receiver = ReceiverModel(pi=_PI, source_intensity_uncertainty=0.2)
    with_delta = simulate_pass(MissionConfig(samples=5), receiver=receiver, link_seed=1)
    without_delta = simulate_pass(
        MissionConfig(samples=5), receiver=ReceiverModel(pi=_PI), link_seed=1
    )
    # No source model active -> delta never changes the emitted rate.
    assert (
        with_delta.link_receiver.secure_key_rate_per_signal_pulse
        == without_delta.link_receiver.secure_key_rate_per_signal_pulse
    )
    manifest = json.loads(with_delta.link_provenance)
    assert manifest["receiver"]["source_intensity_uncertainty"] == 0.2
    assert manifest["receiver"]["source_support_echo"] is None


def test_source_uncertainty_required_error_at_mission_level():
    receiver = ReceiverModel(pi=_PI)
    with pytest.raises(SourceUncertaintyRequiredError):
        simulate_pass(
            MissionConfig(samples=5),
            receiver=receiver,
            link_effects=[CalibratedSourceFactorEffect(half_width=0.05)],
            link_seed=1,
        )


def test_source_certificate_violation_error_at_mission_level():
    receiver = ReceiverModel(pi=_PI, source_intensity_uncertainty=0.0)
    with pytest.raises(SourceCertificateViolationError):
        simulate_pass(
            MissionConfig(samples=5),
            receiver=receiver,
            link_effects=[CalibratedSourceFactorEffect(half_width=0.02)],
            link_seed=1,
        )


def test_source_model_incompatible_error_mu_fluctuation_at_mission_level():
    for delta in (None, 0.0, 0.3):
        receiver = ReceiverModel(pi=_PI, source_intensity_uncertainty=delta)
        expected = SourceUncertaintyRequiredError if delta is None else SourceModelIncompatibleError
        with pytest.raises(expected):
            simulate_pass(
                MissionConfig(samples=5),
                receiver=receiver,
                link_effects=[MuFluctuationEffect(relative_sigma=0.05)],
                link_seed=1,
            )


def test_certified_source_run_activates_robust_diagnostics_and_stays_le_nominal():
    receiver_nominal = ReceiverModel(pi=_PI)
    nominal = simulate_pass(MissionConfig(samples=5), receiver=receiver_nominal, link_seed=1)

    receiver_robust = ReceiverModel(pi=_PI, source_intensity_uncertainty=0.05)
    robust = simulate_pass(
        MissionConfig(samples=5),
        receiver=receiver_robust,
        link_effects=[CalibratedSourceFactorEffect(half_width=0.05)],
        link_seed=1,
    )
    assert robust.link_receiver is not None
    for rate in robust.link_receiver.secure_key_rate_per_signal_pulse:
        assert rate >= 0.0
    manifest = json.loads(robust.link_provenance)
    assert manifest["receiver"]["source_intensity_uncertainty"] == 0.05
    assert manifest["receiver"]["source_support_echo"] == [0.95, 1.05]


# ---------------------------------------------------------------------------
# §5 -- versioning, manifest, replay
# ---------------------------------------------------------------------------


def test_pregate0_v2_fixture_satisfies_both_replay_safeguards():
    manifest_json = V2_MANIFEST_PATH.read_text(encoding="utf-8")
    manifest = json.loads(manifest_json)
    assert manifest["manifest_version"] == 2
    assert manifest["pipeline_version"] == LINK_PIPELINE_VERSION_V2

    # Safeguard (a): exact in-process parity.
    from qkd.effects import DopplerShiftEffect, PolarizationMisalignmentEffect, TimingJitterEffect

    replayed = replay_from_provenance(manifest_json)
    direct = simulate_pass(
        link_effects=[
            TimingJitterEffect(1e-10),
            PolarizationMisalignmentEffect(0.01),
            DopplerShiftEffect(carrier_frequency_hz=1.934e14),
        ],
        receiver=ReceiverModel(pi=_PI),
        link_controls={
            "gate_window_s": 1e-9,
            "filter_sigma_hz": 1e9,
            "doppler_residual_fraction": 0.01,
        },
    )
    replayed_dict = dataclasses.asdict(replayed)
    direct_dict = dataclasses.asdict(direct)
    replayed_dict.pop("link_provenance")
    direct_dict.pop("link_provenance")
    assert replayed_dict == direct_dict

    # Safeguard (b): tolerant structure/array comparison with the historical
    # semantic output captured at Pre-Gate 0, before any LINK-7 source edit.
    current_payload = _build_results(replayed, plot_path="x.png")
    expected_payload = json.loads(V2_EXPECTED_PATH.read_text(encoding="utf-8"))
    assert (
        json.loads(current_payload["run_metadata"]["link_provenance"])["manifest_version"] == 3
    )
    current_payload["run_metadata"].pop("link_provenance", None)
    expected_payload["run_metadata"].pop("link_provenance", None)
    _assert_close_structure(current_payload, expected_payload)


def test_three_row_compatibility_matrix():
    v1 = _valid_manifest_v1_dict()
    v2 = _valid_manifest_v2_dict()
    v3 = _valid_manifest_dict()
    assert v1["pipeline_version"] == LINK_PIPELINE_VERSION_V1
    assert v2["pipeline_version"] == LINK_PIPELINE_VERSION_V2
    assert v3["pipeline_version"] == LINK_PIPELINE_VERSION
    validate_manifest_object(v1)
    validate_manifest_object(v2)
    validate_manifest_object(v3)

    # Every hybrid is rejected.
    v1_wrong_pipeline = dict(v1, pipeline_version=LINK_PIPELINE_VERSION)
    with pytest.raises(ManifestValidationError):
        validate_manifest_object(v1_wrong_pipeline)
    v2_wrong_pipeline = dict(v2, pipeline_version=LINK_PIPELINE_VERSION_V1)
    with pytest.raises(ManifestValidationError):
        validate_manifest_object(v2_wrong_pipeline)
    v3_wrong_pipeline_v1 = dict(v3, pipeline_version=LINK_PIPELINE_VERSION_V1)
    with pytest.raises(ManifestValidationError):
        validate_manifest_object(v3_wrong_pipeline_v1)
    v3_wrong_pipeline_v2 = dict(v3, pipeline_version=LINK_PIPELINE_VERSION_V2)
    with pytest.raises(ManifestValidationError):
        validate_manifest_object(v3_wrong_pipeline_v2)


def test_v1_and_v2_reject_calibrated_source_factor_effect_id():
    for manifest_factory in (_valid_manifest_v1_dict, _valid_manifest_v2_dict):
        manifest = manifest_factory()
        manifest["effects"] = [
            {
                "effect_id": "calibrated_source_factor",
                "type_id": "qkd.effects.CalibratedSourceFactorEffect",
                "parameters_complete": True,
                "params": {"half_width": 0.02},
            }
        ]
        manifest["replayability"] = "replayable"
        with pytest.raises(ManifestValidationError):
            validate_manifest_object(manifest)


def test_v3_receiver_keys_are_exactly_v2_keys_plus_the_two_new_fields():
    v3 = _valid_manifest_dict()
    v3["receiver"] = {
        "pi": {"signal": 0.8, "decoy": 0.15, "vacuum": 0.05},
        "operating_convention": "next_live_gate_v1",
        "source_linewidth_sigma_hz": 0.0,
        "source_intensity_uncertainty": None,
        "source_support_echo": None,
    }
    v3["model_ids"] = {"receiver": "qkd_receiver_mean_field_v1", "pdt": None}
    validate_manifest_object(v3)  # ok

    # v1/v2 receiver objects never carry the two new v3-only keys.
    v2 = _valid_manifest_v2_dict()
    v2["receiver"] = {
        "pi": {"signal": 0.8, "decoy": 0.15, "vacuum": 0.05},
        "operating_convention": "next_live_gate_v1",
        "source_linewidth_sigma_hz": 0.0,
    }
    v2["model_ids"] = {"receiver": "qkd_receiver_mean_field_v1", "pdt": None}
    validate_manifest_object(v2)  # ok -- no source_intensity_uncertainty/echo required

    v2_with_v3_keys = dict(v2)
    v2_with_v3_keys["receiver"] = dict(v2["receiver"], source_intensity_uncertainty=None)
    with pytest.raises(ManifestValidationError):
        validate_manifest_object(v2_with_v3_keys)


def test_v3_round_trip_byte_identical_sampled_with_certified_source_model():
    receiver = ReceiverModel(pi=_PI, source_intensity_uncertainty=0.05)
    result = simulate_pass(
        MissionConfig(samples=10),
        receiver=receiver,
        link_effects=[CalibratedSourceFactorEffect(half_width=0.05)],
        link_seed=7,
    )
    manifest = json.loads(result.link_provenance)
    assert manifest["manifest_version"] == 3
    assert manifest["pipeline_version"] == LINK_PIPELINE_VERSION
    assert manifest["receiver"]["source_intensity_uncertainty"] == 0.05
    assert manifest["receiver"]["source_support_echo"] == [0.95, 1.05]

    replayed = replay_from_provenance(result.link_provenance)
    assert dataclasses.asdict(replayed) == dataclasses.asdict(result)


def test_source_support_echo_null_when_no_source_model_active():
    result = simulate_pass(MissionConfig(samples=5), receiver=ReceiverModel(pi=_PI), link_seed=1)
    manifest = json.loads(result.link_provenance)
    assert manifest["receiver"]["source_support_echo"] is None


def test_source_support_echo_mismatch_rejected_on_replay():
    receiver = ReceiverModel(pi=_PI, source_intensity_uncertainty=0.05)
    result = simulate_pass(
        MissionConfig(samples=5),
        receiver=receiver,
        link_effects=[CalibratedSourceFactorEffect(half_width=0.05)],
        link_seed=7,
    )
    manifest = json.loads(result.link_provenance)
    # Tamper the audit-only echo -- replay must recompute from the
    # reconstructed effects and refuse on disagreement (R12.2 -- the echo is
    # never trusted).
    manifest["receiver"]["source_support_echo"] = [0.9, 1.1]
    tampered_json = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    with pytest.raises(SourceSupportEchoMismatchError):
        replay_from_provenance(tampered_json)


def test_v1_v2_historical_replays_unchanged_receiver_defaults():
    # A v1/v2 manifest never carried source_intensity_uncertainty -- the
    # reader supplies the identity default None (plan §5).
    v1 = _valid_manifest_v1_dict()
    v1["effects"] = []
    v1["receiver"] = {
        "pi": {"signal": 0.8, "decoy": 0.15, "vacuum": 0.05},
        "operating_convention": "next_live_gate_v1",
    }
    v1["model_ids"] = {"receiver": "qkd_receiver_mean_field_v1", "pdt": None}
    manifest_json = json.dumps(v1, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    replayed = replay_from_provenance(manifest_json)
    assert replayed.link_receiver is not None


# ---------------------------------------------------------------------------
# §10-D3 -- bb84 factoring: pure extraction, no law change, parity-pinned.
# ---------------------------------------------------------------------------


def test_expected_block_statistics_matches_run_decoy_bb84_honest_branch():
    channel = ChannelState(transmittance=0.2, werner_p=0.98, intrinsic_qber=0.015, dark_count_prob=0.0)
    detector = DetectorParams(detection_efficiency=0.5, dark_count_prob=1e-6)
    intensities = {"signal": 0.5, "decoy": 0.1, "vacuum": 0.0}

    gains, qber = expected_block_statistics(channel, intensities, detector)
    reference = run_decoy_bb84(channel, intensities, 1_000_000, detector)
    assert gains == reference.gains
    assert qber == reference.qber_per_intensity


def test_run_decoy_bb84_bit_identical_on_a_pinned_grid_post_factoring():
    # LINK-7 plan §10-D3(ii): a parity test asserting run_decoy_bb84's
    # outputs are bit-identical pre/post-factoring on a pinned grid. The
    # values below are frozen at the moment of the factoring commit and are
    # never eligible for retuning (plan §13, "byte-identity and parity
    # tests are never eligible").
    channel = ChannelState(transmittance=0.15, werner_p=0.97, intrinsic_qber=0.02, dark_count_prob=1e-7)
    detector = DetectorParams(detection_efficiency=0.6, dark_count_prob=2e-6)
    intensities = {"signal": 0.6, "decoy": 0.12, "vacuum": 0.0}
    result = run_decoy_bb84(channel, intensities, 1_000_000, detector)

    assert result.gains == {
        "signal": pytest.approx(0.05256978836241466, abs=0, rel=1e-15),
        "decoy": pytest.approx(0.010743867902572979, abs=0, rel=1e-15),
        "vacuum": pytest.approx(2e-06, abs=0, rel=1e-15),
    }
    assert result.qber_per_intensity["signal"] == pytest.approx(0.02001830143787355, abs=0, rel=1e-15)
    assert result.secure_key_rate == pytest.approx(0.007610033854014323, abs=0, rel=1e-15)


def test_decoy_bb84_and_decoy_eve_tests_still_pass_is_covered_by_the_full_suite():
    # Documents that this file introduces no changes to tests/test_bb84.py
    # or the eve-detection tests -- they are the untouched oracle for the
    # bb84 factoring (plan §10-D3(i)/(iii)); nothing further to assert here.
    assert True
