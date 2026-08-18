"""LINK-6a Gate A/C tests: receiver contract, gated-detection physics, PDT quadrature.

``docs/LINK_6A_PLAN.md`` v2.3.1 -- §1 (receiver model), §1.2 (noise mapping),
§1.3/§1.5 (shared-history afterpulse + availability), §2 (gate window
control), §5 (PDT admissibility/quadrature/guards), §8/§12 (acceptance tests
and the numerical anchor). Pure ``qkd.detection`` unit tests; mission-level
integration lives in ``tests/test_link6a.py``.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from qkd.detection import (
    AfterpulseCascadeDomainError,
    GateWindowRequiredError,
    MIN_GATE_WINDOW_S,
    PDT_BLOCK_BINDING_REL_TOL,
    PDT_BLOCK_RATIO,
    PDT_GRID_UNIFORMITY_REL_TOL,
    PDT_MEMORY_RATIO,
    PDT_TAIL_TOLERANCE,
    PI_SUM_TOLERANCE,
    PdtBlockDurationMismatchError,
    PdtConfig,
    PdtGridNonUniformError,
    PdtGuardError,
    PdtNPulsesExceedsTrainError,
    PdtNodeUnphysicalError,
    PdtSampleVaryingMemoryError,
    PdtTailToleranceExceededError,
    ReceiverConfigError,
    ReceiverInputs,
    ReceiverModel,
    _assert_pdt_memory_invariant,
    click_availability,
    compute_noise_probabilities,
    compute_receiver_block,
    compute_receiver_block_pdt,
    extract_receiver_inputs,
    gauss_hermite_lognormal_nodes,
    shared_history_afterpulse,
    validate_grid_and_block_duration,
    validate_pdt_guards,
    validate_tail_and_nodes,
)
from qkd.effects import LogNormalLaw
from qkd.link import ChannelObservables, DetectorObservables, EffectiveLinkState, SourceObservables
from qkd.signals import ChannelState, DetectorParams


# ---------------------------------------------------------------------------
# §1.1 -- ReceiverModel construction
# ---------------------------------------------------------------------------


def test_receiver_model_requires_strictly_positive_pi():
    with pytest.raises(ReceiverConfigError):
        ReceiverModel(pi=(0.0, 0.5, 0.5))
    with pytest.raises(ReceiverConfigError):
        ReceiverModel(pi=(0.5, -0.1, 0.6))


def test_receiver_model_requires_pi_sum_to_one_within_tolerance():
    ReceiverModel(pi=(0.8, 0.15, 0.05))  # sums exactly, ok
    with pytest.raises(ReceiverConfigError):
        ReceiverModel(pi=(0.8, 0.15, 0.06))
    # Just inside PI_SUM_TOLERANCE is accepted.
    epsilon = PI_SUM_TOLERANCE / 2.0
    ReceiverModel(pi=(0.8, 0.15, 0.05 + epsilon))


def test_receiver_model_rejects_unknown_operating_convention():
    with pytest.raises(ReceiverConfigError):
        ReceiverModel(pi=(0.8, 0.15, 0.05), operating_convention="other")


def test_receiver_model_controls_declares_gate_window_with_period_coupled_bounds():
    receiver = ReceiverModel(pi=(0.8, 0.15, 0.05))
    (spec,) = receiver.controls(pulse_repetition_rate_hz=1.0e8)
    assert spec.name == "gate_window_s"
    assert spec.unit == "s"
    assert spec.bounds == (MIN_GATE_WINDOW_S, 1.0 / 1.0e8)


# ---------------------------------------------------------------------------
# §3 -- extract_receiver_inputs / residual bridge seam
# ---------------------------------------------------------------------------


def test_extract_receiver_inputs_returns_exact_consumed_field_set():
    state = EffectiveLinkState(
        channel=ChannelObservables(background_rate_hz=123.0, misalignment_error=0.1),
        detector=DetectorObservables(
            dark_count_rate_hz=45.0, afterpulse_prob=0.02, dead_time_s=1e-7
        ),
        source=SourceObservables(intensity_factor=1.0),
    )
    inputs, residual = extract_receiver_inputs(state)

    assert inputs == ReceiverInputs(
        background_rate_hz=123.0,
        dark_count_rate_hz=45.0,
        afterpulse_prob=0.02,
        dead_time_s=1e-7,
    )
    # The residual zeroes only the four consumed fields; every other field
    # (including 6b/source fields) passes through unchanged for the
    # existing apply_link_state bridge to reject.
    assert residual.channel.background_rate_hz == 0.0
    assert residual.channel.misalignment_error == 0.1
    assert residual.detector.dark_count_rate_hz == 0.0
    assert residual.detector.afterpulse_prob == 0.0
    assert residual.detector.dead_time_s == 0.0
    assert residual.source.intensity_factor == 1.0


def test_extract_receiver_inputs_identity_state_round_trips_to_zero_inputs():
    state = EffectiveLinkState(channel=ChannelObservables(), detector=DetectorObservables())
    inputs, residual = extract_receiver_inputs(state)
    assert inputs == ReceiverInputs(0.0, 0.0, 0.0, 0.0)
    assert residual == state


# ---------------------------------------------------------------------------
# §1.2 -- noise mapping
# ---------------------------------------------------------------------------


def test_gate_window_required_when_a_rate_observable_is_active():
    inputs = ReceiverInputs(
        background_rate_hz=1.0e6, dark_count_rate_hz=0.0, afterpulse_prob=0.0, dead_time_s=0.0
    )
    with pytest.raises(GateWindowRequiredError):
        compute_noise_probabilities(
            detection_efficiency=0.5, y0=1e-6, receiver_inputs=inputs, gate_window_s=None
        )


def test_gate_window_not_required_when_both_rates_are_identity():
    inputs = ReceiverInputs(0.0, 0.0, 0.0, 0.0)
    p_bg, p_dk, p_noise = compute_noise_probabilities(
        detection_efficiency=0.5, y0=1e-6, receiver_inputs=inputs, gate_window_s=None
    )
    assert (p_bg, p_dk) == (0.0, 0.0)
    assert p_noise == pytest.approx(1e-6)


def test_noise_mapping_hand_calculation():
    inputs = ReceiverInputs(
        background_rate_hz=1.0e6, dark_count_rate_hz=2.0e5, afterpulse_prob=0.0, dead_time_s=0.0
    )
    eta_det = 0.5
    gate_window_s = 1.0e-9
    p_bg, p_dk, p_noise = compute_noise_probabilities(
        detection_efficiency=eta_det, y0=1e-6, receiver_inputs=inputs, gate_window_s=gate_window_s
    )
    expected_p_bg = 1.0 - math.exp(-eta_det * 1.0e6 * gate_window_s)
    expected_p_dk = 1.0 - math.exp(-2.0e5 * gate_window_s)
    expected_p_noise = 1.0 - (1.0 - 1e-6) * (1.0 - expected_p_bg) * (1.0 - expected_p_dk)
    assert p_bg == pytest.approx(expected_p_bg, rel=0.0, abs=1e-15)
    assert p_dk == pytest.approx(expected_p_dk, rel=0.0, abs=1e-15)
    assert p_noise == pytest.approx(expected_p_noise, rel=0.0, abs=1e-15)


def test_dark_count_rate_is_an_additional_source_not_a_double_count():
    # y0 = 0 and only the rate-form dark count active -> p_noise from the
    # rate alone (no double counting, plan §1.2).
    inputs = ReceiverInputs(
        background_rate_hz=0.0, dark_count_rate_hz=1.0e5, afterpulse_prob=0.0, dead_time_s=0.0
    )
    gate_window_s = 1.0e-8
    p_bg, p_dk, p_noise = compute_noise_probabilities(
        detection_efficiency=0.5, y0=0.0, receiver_inputs=inputs, gate_window_s=gate_window_s
    )
    assert p_bg == 0.0
    assert p_noise == pytest.approx(p_dk, rel=0.0, abs=1e-15)
    assert p_noise == pytest.approx(1.0 - math.exp(-1.0e5 * gate_window_s), rel=0.0, abs=1e-15)


def test_p_noise_equals_y0_exactly_when_both_rates_zero():
    inputs = ReceiverInputs(0.0, 0.0, 0.0, 0.0)
    _, _, p_noise = compute_noise_probabilities(
        detection_efficiency=0.5, y0=0.0037, receiver_inputs=inputs, gate_window_s=1e-9
    )
    assert p_noise == 0.0037  # strict bit-exact parity anchor (plan §1.2)

    # The live default y0 = 1e-6: 1-(1-y0) != y0 in float64 without the
    # short-circuit (measured 1.0000000000287557e-06) -- this is the case
    # that actually exercises the fix, unlike 0.0037 above.
    _, _, p_noise_default = compute_noise_probabilities(
        detection_efficiency=0.5, y0=1e-6, receiver_inputs=inputs, gate_window_s=1e-9
    )
    assert p_noise_default == 1e-6


# ---------------------------------------------------------------------------
# §1.3/§1.5 -- shared-history afterpulse + availability + §12 numerical anchor
# ---------------------------------------------------------------------------

_ANCHOR_PI = (0.8, 0.15, 0.05)
_ANCHOR_GAINS = {"signal": 0.1, "decoy": 0.05, "vacuum": 0.001}
_ANCHOR_QBER = {"signal": 0.02, "decoy": 0.0, "vacuum": 0.0}
_ANCHOR_P_AP = 0.02
_ANCHOR_F_REP = 1.0e6
_ANCHOR_TAU_D = 1.0e-6


def test_numerical_anchor_matches_plan_12_to_12_significant_digits():
    q_prime, e_prime, t_prime, a, q_bar, q_bar_reg = shared_history_afterpulse(
        _ANCHOR_GAINS, _ANCHOR_QBER, _ANCHOR_PI, _ANCHOR_P_AP
    )

    assert q_bar == pytest.approx(0.08755, rel=0.0, abs=1e-15)
    assert q_bar_reg == pytest.approx(0.089177398342349536, rel=1e-12)
    assert a == pytest.approx(0.001783547966846990, rel=1e-11)
    assert q_prime["signal"] == pytest.approx(0.101605193170162291, rel=1e-12)
    assert q_prime["decoy"] == pytest.approx(0.051694370568504641, rel=1e-12)
    assert q_prime["vacuum"] == pytest.approx(0.002781764418880143, rel=1e-11)
    assert t_prime["signal"] == pytest.approx(0.002802596585081145, rel=1e-12)
    assert e_prime["signal"] == pytest.approx(0.027583202173411795, rel=1e-11)

    r_click, availability = click_availability(_ANCHOR_F_REP, q_bar_reg, _ANCHOR_TAU_D)
    assert r_click == pytest.approx(89177.398342349536, rel=1e-12)
    assert availability == pytest.approx(0.918124082928941429, rel=1e-12)

    # Two-form R_click identity (§1.5): f_rep * Q_bar_reg == f_rep * sum(pi_x Q'_x).
    r_click_alt = _ANCHOR_F_REP * sum(
        pi_x * q_prime[name] for pi_x, name in zip(_ANCHOR_PI, ("signal", "decoy", "vacuum"))
    )
    assert r_click == pytest.approx(r_click_alt, rel=0.0, abs=1e-9)

    # §1.3 sanity identity: the mean-field union equals Q_bar_reg exactly.
    union = 1.0 - (1.0 - a) * (1.0 - q_bar)
    assert union == pytest.approx(q_bar_reg, rel=0.0, abs=1e-15)


def test_afterpulse_domain_raises_at_p_ap_equal_to_one():
    with pytest.raises(AfterpulseCascadeDomainError):
        shared_history_afterpulse(_ANCHOR_GAINS, _ANCHOR_QBER, _ANCHOR_PI, 1.0)


def test_afterpulse_cascade_denominator_stays_positive_within_the_consumer_domain():
    # Within the enforced consumer domain 0 <= p_ap < 1 and Q_bar in [0, 1],
    # 1 - p_ap*(1 - Q_bar) > 1 - p_ap >= 0 always -- the cascade cannot
    # diverge once p_ap < 1 is already enforced (defensive check only).
    gains = {"signal": 0.99, "decoy": 0.99, "vacuum": 0.99}
    qber = {"signal": 0.0, "decoy": 0.0, "vacuum": 0.0}
    q_prime, *_rest = shared_history_afterpulse(gains, qber, (0.8, 0.15, 0.05), 0.999999)
    assert all(0.0 <= value <= 1.0 for value in q_prime.values())


def test_e_prime_is_defined_zero_when_q_prime_is_zero_all_zero_channel():
    gains = {"signal": 0.0, "decoy": 0.0, "vacuum": 0.0}
    qber = {"signal": 0.0, "decoy": 0.0, "vacuum": 0.0}
    q_prime, e_prime, _t_prime, a, q_bar, q_bar_reg = shared_history_afterpulse(
        gains, qber, _ANCHOR_PI, 0.02
    )
    assert q_bar == 0.0
    assert a == 0.0
    assert q_prime == {"signal": 0.0, "decoy": 0.0, "vacuum": 0.0}
    assert e_prime == {"signal": 0.0, "decoy": 0.0, "vacuum": 0.0}


def test_pi_changes_detector_load_but_not_base_optical_gains():
    # Q_bar (detector load) depends on pi; the raw per-intensity gains
    # (base bb84 statistics) passed in are untouched by pi.
    q1, *_rest1 = shared_history_afterpulse(_ANCHOR_GAINS, _ANCHOR_QBER, (0.8, 0.15, 0.05), 0.02)
    q2, *_rest2 = shared_history_afterpulse(_ANCHOR_GAINS, _ANCHOR_QBER, (0.5, 0.3, 0.2), 0.02)
    # Base gains dict passed in is identical (pi never mutates its input).
    assert _ANCHOR_GAINS == {"signal": 0.1, "decoy": 0.05, "vacuum": 0.001}
    # But the shared afterpulse arrival "a" (detector load) differs with pi.
    assert q1 != q2


def test_common_availability_equivalent_to_supply_a_times_q_route():
    # R6/§1.5: Y1_L(A*Q) == A*Y1_L(Q), e1_U(A*Q, A*Y0) == e1_U(Q, Y0),
    # R(A*Q) == A*R(Q) when A is common across intensities.
    from qkd.bb84 import estimate_decoy_bounds, secure_key_rate

    intensities = {"signal": 0.5, "decoy": 0.1, "vacuum": 0.0}
    gains = {"signal": 0.1, "decoy": 0.05, "vacuum": 0.001}
    qber = {"signal": 0.02, "decoy": 0.01, "vacuum": 0.0}
    availability = 0.7345

    y1_l, e1_u = estimate_decoy_bounds(gains=gains, qber_per_intensity=qber, intensities=intensities)
    scaled_gains = {name: availability * value for name, value in gains.items()}
    y1_l_scaled, e1_u_scaled = estimate_decoy_bounds(
        gains=scaled_gains, qber_per_intensity=qber, intensities=intensities
    )

    assert y1_l_scaled == pytest.approx(availability * y1_l, rel=1e-9)
    assert e1_u_scaled == pytest.approx(e1_u, rel=1e-9)  # e1_U invariant under common A

    mu = intensities["signal"]
    q1 = y1_l * mu * math.exp(-mu)
    q1_scaled = y1_l_scaled * mu * math.exp(-mu)
    rate = secure_key_rate(gains["signal"], qber["signal"], q1, e1_u, q=0.5)
    rate_scaled = secure_key_rate(
        scaled_gains["signal"], qber["signal"], q1_scaled, e1_u_scaled, q=0.5
    )
    assert rate_scaled == pytest.approx(availability * rate, rel=1e-9)


def test_per_intensity_availability_is_demonstrably_absent():
    # A single scalar A multiplies every intensity's gain identically; there
    # is no per-intensity A_x anywhere in the chain.
    q_prime, _e_prime, _t_prime, _a, _q_bar, q_bar_reg = shared_history_afterpulse(
        _ANCHOR_GAINS, _ANCHOR_QBER, _ANCHOR_PI, _ANCHOR_P_AP
    )
    r_click, availability = click_availability(_ANCHOR_F_REP, q_bar_reg, _ANCHOR_TAU_D)
    # click_availability returns one scalar, not a per-intensity mapping --
    # structurally, no per-intensity A can be extracted from this API.
    assert isinstance(availability, float)


# ---------------------------------------------------------------------------
# §1.2 -- Q'_vacuum > p_noise acceptance test and boundary cases
# ---------------------------------------------------------------------------


def test_vacuum_gain_exceeds_p_noise_when_afterpulsing_active():
    channel = ChannelState(transmittance=0.2, werner_p=0.98, intrinsic_qber=0.015, dark_count_prob=0.0)
    detector = DetectorParams(detection_efficiency=0.5, dark_count_prob=1e-6)
    inputs = ReceiverInputs(
        background_rate_hz=0.0, dark_count_rate_hz=0.0, afterpulse_prob=0.02, dead_time_s=1e-6
    )
    intensities = {"signal": 0.5, "decoy": 0.1, "vacuum": 0.0}
    block = compute_receiver_block(
        channel=channel,
        detector=detector,
        intensities=intensities,
        n_pulses=1_000_000,
        pi=(0.8, 0.15, 0.05),
        receiver_inputs=inputs,
        gate_window_s=None,
        pulse_repetition_rate_hz=1.0e8,
    )
    assert block.gains["vacuum"] > block.p_noise


def test_vacuum_gain_equals_p_noise_at_zero_afterpulsing_boundary():
    channel = ChannelState(transmittance=0.2, werner_p=0.98, intrinsic_qber=0.015, dark_count_prob=0.0)
    detector = DetectorParams(detection_efficiency=0.5, dark_count_prob=1e-6)
    inputs = ReceiverInputs(0.0, 0.0, 0.0, 0.0)
    intensities = {"signal": 0.5, "decoy": 0.1, "vacuum": 0.0}
    block = compute_receiver_block(
        channel=channel,
        detector=detector,
        intensities=intensities,
        n_pulses=1_000_000,
        pi=(0.8, 0.15, 0.05),
        receiver_inputs=inputs,
        gate_window_s=None,
        pulse_repetition_rate_hz=1.0e8,
    )
    assert block.gains["vacuum"] == block.p_noise  # a == 0 -> exact pass-through


def test_vacuum_gain_equals_p_noise_at_saturated_p_noise_boundary():
    # p_noise = 1 (y0 = 1.0): Q_vacuum = y0 = 1 exactly (honest gain at
    # mean_photon_number == 0), so Q'_vacuum = 1-(1-1)*(1-a) = 1 = p_noise,
    # the saturated-boundary equality (plan §1.2 acceptance test).
    channel = ChannelState(transmittance=0.2, werner_p=0.98, intrinsic_qber=0.015, dark_count_prob=0.0)
    detector = DetectorParams(detection_efficiency=0.5, dark_count_prob=1.0)
    inputs = ReceiverInputs(
        background_rate_hz=0.0, dark_count_rate_hz=0.0, afterpulse_prob=0.02, dead_time_s=1e-6
    )
    intensities = {"signal": 0.5, "decoy": 0.1, "vacuum": 0.0}
    block = compute_receiver_block(
        channel=channel,
        detector=detector,
        intensities=intensities,
        n_pulses=1_000_000,
        pi=(0.8, 0.15, 0.05),
        receiver_inputs=inputs,
        gate_window_s=None,
        pulse_repetition_rate_hz=1.0e8,
    )
    assert block.p_noise == 1.0
    assert block.gains["vacuum"] == 1.0
    assert block.gains["vacuum"] == block.p_noise


def test_all_zero_channel_boundary_q_bar_reg_zero_vacuum_and_error_defined_zero():
    # Q_bar_reg = 0 (all-zero channel: eta = 0 and y0 = 0) -> a = 0 ->
    # Q'_vacuum == p_noise == 0 exactly, and E' is the defined-zero case
    # (Q'_x = 0 -> E'_x ≡ 0, plan §1.3 R5 edge domain), not 0/0.
    channel = ChannelState(transmittance=0.0, werner_p=0.98, intrinsic_qber=0.015, dark_count_prob=0.0)
    detector = DetectorParams(detection_efficiency=0.5, dark_count_prob=0.0)
    inputs = ReceiverInputs(
        background_rate_hz=0.0, dark_count_rate_hz=0.0, afterpulse_prob=0.02, dead_time_s=1e-6
    )
    intensities = {"signal": 0.5, "decoy": 0.1, "vacuum": 0.0}
    block = compute_receiver_block(
        channel=channel,
        detector=detector,
        intensities=intensities,
        n_pulses=1_000_000,
        pi=(0.8, 0.15, 0.05),
        receiver_inputs=inputs,
        gate_window_s=None,
        pulse_repetition_rate_hz=1.0e8,
    )
    assert block.q_bar_reg == 0.0
    assert block.a == 0.0
    assert block.p_noise == 0.0
    assert block.gains["vacuum"] == 0.0
    assert block.gains["vacuum"] == block.p_noise
    assert block.qber_per_intensity["vacuum"] == 0.0
    assert block.qber_per_intensity["signal"] == 0.0
    assert block.qber_per_intensity["decoy"] == 0.0


def test_afterpulse_prob_just_below_one_with_small_q_bar_stays_finite():
    # Consumer-domain edge: p_ap just below 1 (not equal), Q_bar small but
    # nonzero -> the cascade denominator 1 - p_ap*(1-Q_bar) stays strictly
    # positive and finite, no divergence (plan §1.3 R5 edge domain).
    gains = {"signal": 0.001, "decoy": 0.0005, "vacuum": 0.0001}
    qber = {"signal": 0.02, "decoy": 0.01, "vacuum": 0.0}
    p_ap = 1.0 - 1e-9
    q_prime, e_prime, t_prime, a, q_bar, q_bar_reg = shared_history_afterpulse(
        gains, qber, (0.8, 0.15, 0.05), p_ap
    )
    assert math.isfinite(q_bar_reg)
    assert math.isfinite(a)
    assert all(math.isfinite(v) and 0.0 <= v <= 1.0 for v in q_prime.values())
    assert all(math.isfinite(v) and 0.0 <= v <= 1.0 for v in e_prime.values())


def test_decoy_anomaly_score_is_zero_receiver_active_honest_run():
    channel = ChannelState(transmittance=0.2, werner_p=0.98, intrinsic_qber=0.015, dark_count_prob=0.0)
    detector = DetectorParams(detection_efficiency=0.5, dark_count_prob=1e-6)
    inputs = ReceiverInputs(0.0, 0.0, 0.02, 1e-6)
    intensities = {"signal": 0.5, "decoy": 0.1, "vacuum": 0.0}
    block = compute_receiver_block(
        channel=channel,
        detector=detector,
        intensities=intensities,
        n_pulses=1_000_000,
        pi=(0.8, 0.15, 0.05),
        receiver_inputs=inputs,
        gate_window_s=None,
        pulse_repetition_rate_hz=1.0e8,
    )
    assert block.decoy_anomaly_score == 0.0


def test_receiver_active_run_with_identity_inputs_reproduces_run_decoy_bb84():
    # Gate-A parity: p_ap = 0, identity ReceiverInputs -> the wrapper's base
    # call reproduces run_decoy_bb84's own gains/QBERs/anomaly score exactly.
    from qkd.bb84 import run_decoy_bb84

    channel = ChannelState(transmittance=0.2, werner_p=0.98, intrinsic_qber=0.015, dark_count_prob=0.0)
    detector = DetectorParams(detection_efficiency=0.5, dark_count_prob=1e-6)
    inputs = ReceiverInputs(0.0, 0.0, 0.0, 0.0)
    intensities = {"signal": 0.5, "decoy": 0.1, "vacuum": 0.0}

    reference = run_decoy_bb84(channel, intensities, 1_000_000, detector, eve=None)
    block = compute_receiver_block(
        channel=channel,
        detector=detector,
        intensities=intensities,
        n_pulses=1_000_000,
        pi=(1.0, 0.0, 0.0) if False else (0.8, 0.15, 0.05),
        receiver_inputs=inputs,
        gate_window_s=None,
        pulse_repetition_rate_hz=1.0e8,
    )
    # Identity inputs -> p_noise == y0, a == 0 -> the exact short-circuits in
    # compute_noise_probabilities/shared_history_afterpulse/click_availability
    # make this bit-exact, not merely close (plan §8 Gate-A parity).
    assert block.gains == reference.gains
    assert block.qber_per_intensity == reference.qber_per_intensity
    assert block.decoy_anomaly_score == reference.decoy_anomaly_score
    assert block.secure_key_rate_per_signal_pulse == reference.secure_key_rate
    # Availability == 1 (dead_time_s == 0) so the delivered signal rate is
    # exactly pi_signal * the base rate.
    assert block.availability == 1.0


# ---------------------------------------------------------------------------
# §2 -- gate window bound edge cases
# ---------------------------------------------------------------------------


def test_gate_window_bound_constant_is_named_and_tiny():
    assert MIN_GATE_WINDOW_S == 1e-12


def test_named_constants_have_the_plan_frozen_values():
    assert PI_SUM_TOLERANCE == 1e-9
    assert MIN_GATE_WINDOW_S == 1e-12
    assert PDT_TAIL_TOLERANCE == 1e-9
    assert PDT_MEMORY_RATIO == 20
    assert PDT_BLOCK_RATIO == 50
    assert PDT_GRID_UNIFORMITY_REL_TOL == 1e-9
    assert PDT_BLOCK_BINDING_REL_TOL == 1e-6


# ---------------------------------------------------------------------------
# §5 -- PDT: guards, grid binding, quadrature, tail/node checks
# ---------------------------------------------------------------------------


def test_pdt_config_requires_positive_finite_timing():
    with pytest.raises(PdtGuardError):
        PdtConfig(fading_coherence_time_s=0.0, block_duration_s=1.0)
    with pytest.raises(PdtGuardError):
        PdtConfig(fading_coherence_time_s=1.0, block_duration_s=math.inf)


def test_grid_uniformity_and_block_binding_hand_calculation():
    time_s = [0.0, 0.5, 1.0, 1.5, 2.0]
    width = validate_grid_and_block_duration(time_s, 0.5)
    assert width == pytest.approx(0.5)

    with pytest.raises(PdtBlockDurationMismatchError):
        validate_grid_and_block_duration(time_s, 10.0)

    # Just inside PDT_BLOCK_BINDING_REL_TOL is accepted.
    validate_grid_and_block_duration(time_s, 0.5 * (1.0 + PDT_BLOCK_BINDING_REL_TOL / 2.0))


def test_grid_non_uniformity_raises():
    with pytest.raises(PdtGridNonUniformError):
        validate_grid_and_block_duration([0.0, 0.5, 1.3], 0.5)


def test_memory_guard_non_vacuous_at_zero_dead_time():
    # tau_mem = 0 + 1/f_rep is nonzero even at dead_time_s = 0 -- the guard
    # must still be able to fail.
    pdt_config = PdtConfig(fading_coherence_time_s=1e-9, block_duration_s=1.0)
    with pytest.raises(PdtGuardError):
        validate_pdt_guards(
            pdt_config,
            dead_time_s=0.0,
            pulse_repetition_rate_hz=1.0e8,
            n_pulses=1,
            block_duration_s=1.0,
        )


def test_memory_guard_passes_at_live_defaults():
    pdt_config = PdtConfig(fading_coherence_time_s=3e-3, block_duration_s=0.476955506437)
    tau_mem = validate_pdt_guards(
        pdt_config,
        dead_time_s=1e-6,
        pulse_repetition_rate_hz=1.0e8,
        n_pulses=1_000_000,
        block_duration_s=0.476955506437,
    )
    assert tau_mem == pytest.approx(1e-6 + 1e-8)


def test_stationarity_guard_rejects_short_block():
    pdt_config = PdtConfig(fading_coherence_time_s=3e-3, block_duration_s=1e-3)
    with pytest.raises(PdtGuardError):
        validate_pdt_guards(
            pdt_config,
            dead_time_s=0.0,
            pulse_repetition_rate_hz=1.0e8,
            n_pulses=1,
            block_duration_s=1e-3,
        )


def test_n_pulses_exceeding_train_rejected_at_admission():
    pdt_config = PdtConfig(fading_coherence_time_s=1e-3, block_duration_s=0.1)
    with pytest.raises(PdtNPulsesExceedsTrainError):
        validate_pdt_guards(
            pdt_config,
            dead_time_s=0.0,
            pulse_repetition_rate_hz=1.0e6,
            n_pulses=200_000,  # exceeds f_rep * block_duration_s == 1e5
            block_duration_s=0.1,
        )


def test_pdt_memory_invariant_accepts_constant_samples():
    inputs = [ReceiverInputs(0.0, 0.0, 0.02, 1e-6) for _ in range(5)]
    _assert_pdt_memory_invariant(inputs)  # no raise
    _assert_pdt_memory_invariant([])  # no raise on empty


def test_pdt_memory_invariant_rejects_varying_dead_time():
    inputs = [
        ReceiverInputs(0.0, 0.0, 0.02, 1e-6),
        ReceiverInputs(0.0, 0.0, 0.02, 1e-6),
        ReceiverInputs(0.0, 0.0, 0.02, 2e-6),  # differs at index 2
    ]
    with pytest.raises(PdtSampleVaryingMemoryError):
        _assert_pdt_memory_invariant(inputs)


def test_pdt_memory_invariant_rejects_varying_afterpulse_prob():
    inputs = [
        ReceiverInputs(0.0, 0.0, 0.02, 1e-6),
        ReceiverInputs(0.0, 0.0, 0.03, 1e-6),  # differs at index 1
    ]
    with pytest.raises(PdtSampleVaryingMemoryError):
        _assert_pdt_memory_invariant(inputs)


def test_gauss_hermite_nodes_are_a_probability_measure():
    law = LogNormalLaw(mu_log=0.0, sigma_log=0.1)
    f_nodes, p_nodes = gauss_hermite_lognormal_nodes(law, 21)
    assert len(f_nodes) == 21
    assert np.all(p_nodes >= 0.0)
    assert p_nodes.sum() == pytest.approx(1.0, rel=0.0, abs=1e-12)
    # E[f] == 1 for a pure-fading unit-mean log-normal law (mu = -sigma^2/2
    # is not assumed here; instead directly check exp(mu+sigma^2/2)).
    expected_mean = math.exp(law.mu_log + 0.5 * law.sigma_log**2)
    assert float((f_nodes * p_nodes).sum()) == pytest.approx(expected_mean, rel=1e-9)


def test_quadrature_21_node_converges_to_41_node():
    law = LogNormalLaw(mu_log=-0.02, sigma_log=0.2)
    f21, p21 = gauss_hermite_lognormal_nodes(law, 21)
    f41, p41 = gauss_hermite_lognormal_nodes(law, 41)
    mean21 = float((f21 * p21).sum())
    mean41 = float((f41 * p41).sum())
    assert mean21 == pytest.approx(mean41, rel=1e-9)


def test_tail_tolerance_exceeded_raises():
    # A wide law with eta_base close to 1 puts non-negligible mass above 1.
    law = LogNormalLaw(mu_log=0.0, sigma_log=1.5)
    f_nodes, _p_nodes = gauss_hermite_lognormal_nodes(law, 21)
    with pytest.raises(PdtTailToleranceExceededError):
        validate_tail_and_nodes(law, eta_base=0.99, f_nodes=f_nodes)


def test_node_unphysical_raises_without_clipping():
    # Construct nodes directly to guarantee at least one exceeds eta_base
    # while keeping analytic tail mass within tolerance for isolation.
    law = LogNormalLaw(mu_log=0.0, sigma_log=1e-6)
    f_nodes = np.array([1.5])
    with pytest.raises(PdtNodeUnphysicalError):
        validate_tail_and_nodes(law, eta_base=0.9, f_nodes=f_nodes)


def test_tail_and_node_guards_pass_in_the_valid_regime():
    law = LogNormalLaw(mu_log=-0.0005, sigma_log=0.03)
    f_nodes, _p_nodes = gauss_hermite_lognormal_nodes(law, 21)
    tail_mass = validate_tail_and_nodes(law, eta_base=0.2, f_nodes=f_nodes)
    assert tail_mass <= PDT_TAIL_TOLERANCE


def test_availability_weighted_ratio_differs_from_naive_mean_collapse():
    # E[A*Q]/E[A] must differ, in general, from the naive A(E[Q])*E[Q] or an
    # unweighted mean of Q' across nodes (mean-collapse prohibition, §5).
    law = LogNormalLaw(mu_log=-0.00125, sigma_log=0.05)
    channel_base = ChannelState(
        transmittance=0.3, werner_p=0.98, intrinsic_qber=0.015, dark_count_prob=0.0
    )
    detector = DetectorParams(detection_efficiency=0.5, dark_count_prob=1e-6)
    inputs = ReceiverInputs(0.0, 0.0, 0.05, 5e-7)
    intensities = {"signal": 0.5, "decoy": 0.1, "vacuum": 0.0}

    result = compute_receiver_block_pdt(
        law=law,
        channel_base=channel_base,
        detector=detector,
        intensities=intensities,
        n_pulses=1_000_000,
        pi=(0.8, 0.15, 0.05),
        receiver_inputs=inputs,
        gate_window_s=None,
        pulse_repetition_rate_hz=1.0e8,
        n_nodes=21,
    )

    # Unweighted-mean-of-Q' comparison (mean collapse, no availability weight).
    f_nodes, p_nodes = gauss_hermite_lognormal_nodes(law, 21)
    from qkd.bb84 import run_decoy_bb84
    from dataclasses import replace as dc_replace

    unweighted_q_signal = 0.0
    for f_i, p_i in zip(f_nodes, p_nodes):
        node_channel = dc_replace(channel_base, transmittance=channel_base.transmittance * float(f_i))
        base = run_decoy_bb84(node_channel, intensities, 1_000_000, detector, eve=None)
        q_prime, _e, _t, _a, _qb, _qbr = shared_history_afterpulse(
            base.gains, base.qber_per_intensity, (0.8, 0.15, 0.05), 0.05
        )
        unweighted_q_signal += float(p_i) * q_prime["signal"]

    assert result.gains["signal"] != pytest.approx(unweighted_q_signal, rel=1e-9)
