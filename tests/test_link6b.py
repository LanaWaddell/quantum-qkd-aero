"""LINK-6b acceptance tests.

``docs/LINK_6B_PLAN.md`` §1-§9 -- the three channel-side consumption mappings
(gate acceptance, filter acceptance, intrinsic-error mapping), the three new
built-in owners, the two new controls, the v1/v2 manifest compatibility
matrix, and the Pre-Gate 0 historical-oracle safeguards. Mission-level
integration (``simulate_pass``) and pure ``qkd.detection`` unit tests share
this one new file per plan §10 (create: ``tests/test_link6b.py``).
"""

from __future__ import annotations

import dataclasses
import json
import math
from pathlib import Path

import pytest

from qkd.detection import (
    FilterControlRequiredError,
    GateLeakageGuardError,
    GateWindowRequiredError,
    JITTER_LEAK_TOLERANCE,
    MAX_FILTER_SIGMA_HZ,
    MIN_FILTER_SIGMA_HZ,
    PDT_ADMISSIBLE_EFFECTS,
    ReceiverConfigError,
    ReceiverInputs,
    ReceiverModel,
    apply_link6b_channel_fold,
    compute_filter_acceptance,
    compute_gate_acceptance,
    compute_intrinsic_error_mapping,
    compute_receiver_block,
    compute_receiver_block_pdt,
    shared_history_afterpulse,
)
from qkd.effects import (
    BackgroundLightEffect,
    DetectorAfterpulsingEffect,
    DetectorDarkRateEffect,
    DetectorDeadTimeEffect,
    DopplerShiftEffect,
    PhaseMisalignmentEffect,
    PolarizationMisalignmentEffect,
    ScintillationFadingEffect,
    TimingJitterEffect,
)
from qkd.channel import channel_state
from qkd.link import (
    ChannelObservables,
    ChannelStack,
    LinkObservables,
    SingleContributorConflictError,
    TableGeometryProvider,
    apply_link_state,
)
from qkd.mission import INTENSITIES, MissionConfig, PULSE_REPETITION_RATE_HZ, simulate_pass
from qkd.orbit import satellite_pass
from qkd.replay import (
    LINK_PIPELINE_VERSION,
    LINK_PIPELINE_VERSION_V1,
    ManifestValidationError,
    replay_from_provenance,
    validate_manifest_object,
)
from qkd.run import _build_results
from qkd.signals import ChannelState, DetectorParams
from tests.test_replay import _valid_manifest_dict, _valid_manifest_v1_dict


FIXTURES_DIR = Path(__file__).parent / "fixtures"
V1_MANIFEST_PATH = FIXTURES_DIR / "link6a_manifest_v1.json"
V1_EXPECTED_PATH = FIXTURES_DIR / "link6a_manifest_v1_expected.json"

_BASE_CHANNEL = ChannelState(
    transmittance=0.1, werner_p=0.98, intrinsic_qber=0.015, dark_count_prob=1e-6
)
_BASE_DETECTOR = DetectorParams(detection_efficiency=0.5, dark_count_prob=1e-6)
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
    ``tests/test_profile.py::_assert_close_structure`` (plan §5 safeguard b)."""

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
# Pre-Gate 0 -- the real, historical v1 manifest satisfies both §5 safeguards
# ---------------------------------------------------------------------------


def test_pregate0_v1_fixture_satisfies_both_replay_safeguards():
    manifest_json = V1_MANIFEST_PATH.read_text(encoding="utf-8")
    manifest = json.loads(manifest_json)
    assert manifest["manifest_version"] == 1
    assert manifest["pipeline_version"] == LINK_PIPELINE_VERSION_V1

    # Safeguard (a): exact in-process parity -- replay_from_provenance(v1)
    # byte-identical to the current production path reconstructed directly
    # from the same parameters that produced the fixture (Pre-Gate 0).
    replayed = replay_from_provenance(manifest_json)

    direct = simulate_pass(
        link_effects=[
            BackgroundLightEffect(1e4),
            DetectorDarkRateEffect(500.0),
            DetectorAfterpulsingEffect(0.02),
            DetectorDeadTimeEffect(1e-6),
        ],
        receiver=ReceiverModel(pi=(0.8, 0.15, 0.05)),
        link_controls={"gate_window_s": 1e-9},
    )
    replayed_dict = dataclasses.asdict(replayed)
    direct_dict = dataclasses.asdict(direct)
    # link_provenance strings legitimately differ (fresh v2 manifest vs the
    # stored historical v1 string) -- excluded from the byte-identity check,
    # same as the historical-oracle comparison below.
    replayed_dict.pop("link_provenance")
    direct_dict.pop("link_provenance")
    assert replayed_dict == direct_dict

    # Safeguard (b): tolerant structure/array comparison with the *historical*
    # semantic output captured at Pre-Gate 0, before any 6b source edit.
    # ``provenance`` is intentionally NOT popped -- the provenance maps are
    # identical v1-vs-replayed and popping would only weaken the oracle.
    current_payload = _build_results(replayed, plot_path="x.png")
    expected_payload = json.loads(V1_EXPECTED_PATH.read_text(encoding="utf-8"))
    # run_metadata.link_provenance legitimately changes on replay -- the
    # reader re-emits a fresh v2 manifest string (not the stored historical
    # v1 string), so this one field is popped after asserting the intended
    # re-emission semantics (manifest_version bumped to 2).
    assert (
        json.loads(current_payload["run_metadata"]["link_provenance"])["manifest_version"] == 2
    )
    current_payload["run_metadata"].pop("link_provenance", None)
    expected_payload["run_metadata"].pop("link_provenance", None)
    _assert_close_structure(current_payload, expected_payload)


# ---------------------------------------------------------------------------
# §1.1 -- gate acceptance (eta_gate)
# ---------------------------------------------------------------------------


def test_eta_gate_identity_short_circuit_when_sigma_t_zero():
    assert (
        compute_gate_acceptance(
            timing_jitter_s=0.0, gate_window_s=None, pulse_repetition_rate_hz=1e8
        )
        == 1.0
    )


def test_eta_gate_hand_anchor_to_12_digits():
    eta_gate = compute_gate_acceptance(
        timing_jitter_s=1e-10, gate_window_s=1e-9, pulse_repetition_rate_hz=1e8
    )
    assert eta_gate == pytest.approx(0.999999426696856, rel=1e-12)


def test_gate_window_required_for_nonzero_timing_jitter():
    with pytest.raises(GateWindowRequiredError):
        compute_gate_acceptance(
            timing_jitter_s=1e-10, gate_window_s=None, pulse_repetition_rate_hz=1e8
        )


def test_leakage_guard_passes_at_live_defaults():
    # Leaked mass underflows to 0.0 at plan §9 live defaults.
    eta_gate = compute_gate_acceptance(
        timing_jitter_s=1e-10, gate_window_s=1e-9, pulse_repetition_rate_hz=1e8
    )
    assert eta_gate > 0.0


def test_leakage_guard_fires_for_large_jitter():
    with pytest.raises(GateLeakageGuardError):
        compute_gate_acceptance(
            timing_jitter_s=5e-9, gate_window_s=1e-9, pulse_repetition_rate_hz=1e8
        )


def test_jitter_leak_tolerance_constant_is_named():
    assert JITTER_LEAK_TOLERANCE == 1e-9


# ---------------------------------------------------------------------------
# §1.2 -- filter acceptance (eta_filter): the five activation branches
# ---------------------------------------------------------------------------


def test_eta_filter_branch_iii_exact_identity_when_all_absent():
    assert (
        compute_filter_acceptance(
            frequency_offset_hz=0.0,
            filter_sigma_hz=None,
            doppler_residual_fraction=None,
            source_linewidth_sigma_hz=0.0,
        )
        == 1.0
    )


def test_eta_filter_branch_i_filter_required_for_nonzero_offset():
    with pytest.raises(FilterControlRequiredError):
        compute_filter_acceptance(
            frequency_offset_hz=8e9,
            filter_sigma_hz=None,
            doppler_residual_fraction=0.01,
            source_linewidth_sigma_hz=0.0,
        )


def test_eta_filter_branch_i_filter_required_for_nonzero_linewidth():
    with pytest.raises(FilterControlRequiredError):
        compute_filter_acceptance(
            frequency_offset_hz=0.0,
            filter_sigma_hz=None,
            doppler_residual_fraction=None,
            source_linewidth_sigma_hz=2e8,
        )


def test_eta_filter_branch_ii_residual_fraction_required_for_nonzero_offset():
    with pytest.raises(FilterControlRequiredError):
        compute_filter_acceptance(
            frequency_offset_hz=8e9,
            filter_sigma_hz=1e9,
            doppler_residual_fraction=None,
            source_linewidth_sigma_hz=0.0,
        )


def test_eta_filter_branch_iv_supplied_filter_with_zero_offset_computes_linewidth_prefactor():
    eta_filter = compute_filter_acceptance(
        frequency_offset_hz=0.0,
        filter_sigma_hz=1e9,
        doppler_residual_fraction=None,
        source_linewidth_sigma_hz=2e8,
    )
    sigma_f, sigma_s = 1e9, 2e8
    expected = sigma_f / math.sqrt(sigma_f**2 + sigma_s**2)
    assert eta_filter == pytest.approx(expected, rel=1e-12)
    assert eta_filter < 1.0


def test_eta_filter_branch_iv_supplied_filter_zero_linewidth_zero_offset_is_one():
    eta_filter = compute_filter_acceptance(
        frequency_offset_hz=0.0,
        filter_sigma_hz=1e9,
        doppler_residual_fraction=None,
        source_linewidth_sigma_hz=0.0,
    )
    assert eta_filter == pytest.approx(1.0, rel=1e-12)


def test_eta_filter_branch_v_unused_residual_fraction_accepted_and_has_no_effect():
    eta_filter_with = compute_filter_acceptance(
        frequency_offset_hz=0.0,
        filter_sigma_hz=1e9,
        doppler_residual_fraction=0.5,
        source_linewidth_sigma_hz=2e8,
    )
    eta_filter_without = compute_filter_acceptance(
        frequency_offset_hz=0.0,
        filter_sigma_hz=1e9,
        doppler_residual_fraction=None,
        source_linewidth_sigma_hz=2e8,
    )
    assert eta_filter_with == eta_filter_without


def test_eta_filter_hand_anchor_sigma_s_zero_to_12_digits():
    eta_filter = compute_filter_acceptance(
        frequency_offset_hz=8e9,
        filter_sigma_hz=1e9,
        doppler_residual_fraction=0.01,
        source_linewidth_sigma_hz=0.0,
    )
    assert eta_filter == pytest.approx(0.996805114543032, rel=1e-12)


def test_eta_filter_hand_anchor_finite_linewidth_to_12_digits():
    eta_filter = compute_filter_acceptance(
        frequency_offset_hz=8e9,
        filter_sigma_hz=1e9,
        doppler_residual_fraction=0.01,
        source_linewidth_sigma_hz=2e8,
    )
    assert eta_filter == pytest.approx(0.977568141425954, rel=1e-12)


def test_eta_filter_hand_anchor_uncompensated_doppler_to_12_digits():
    eta_filter = compute_filter_acceptance(
        frequency_offset_hz=8e9,
        filter_sigma_hz=1e9,
        doppler_residual_fraction=1.0,
        source_linewidth_sigma_hz=0.0,
    )
    assert eta_filter == pytest.approx(1.2664165549094e-14, rel=1e-9)


def test_filter_sigma_hz_bounds_named_constants():
    assert MIN_FILTER_SIGMA_HZ == 1e3
    assert MAX_FILTER_SIGMA_HZ == 1e15


# ---------------------------------------------------------------------------
# §1.3 -- intrinsic-error mapping (e_d')
# ---------------------------------------------------------------------------


def test_e_d_prime_identity_short_circuit_when_m_zero():
    assert compute_intrinsic_error_mapping(0.015, 0.0) == 0.015


def test_e_d_prime_hand_anchor_exact_literal():
    e_d_prime = compute_intrinsic_error_mapping(0.015, 0.01)
    assert e_d_prime == 0.0247


def test_e_d_prime_domain_reaches_bb84_own_check_not_preempted():
    # e_d=0.015 (small), m=0.9 (only reachable via a raw ChannelObservables
    # test effect -- the two owner effects both cap their emitted
    # misalignment_error <= 0.5): e_d' = 0.015+0.9-2*0.015*0.9 = 0.888 > 0.5.
    # detection.py performs no domain pre-check (plan §1.3) -- bb84.py's own
    # channel.intrinsic_qber in [0, 0.5] check is reached and raises.
    inputs = _identity_inputs(misalignment_error=0.9)
    with pytest.raises(ValueError, match="intrinsic_qber"):
        compute_receiver_block(
            channel=_BASE_CHANNEL,
            detector=_BASE_DETECTOR,
            intensities=INTENSITIES,
            n_pulses=1000,
            pi=_PI,
            receiver_inputs=inputs,
            gate_window_s=None,
            pulse_repetition_rate_hz=1e8,
        )


def test_e_d_prime_bounded_by_half_for_valid_owner_domains():
    # Both e_d and m in [0, 0.5] (bb84's own domain, PolarizationMisalignment/
    # PhaseMisalignment's declared domain) -> e_d' <= 0.5 always (monotone in
    # each argument at the opposing corner, max exactly 0.5 at (0.5, 0.5)).
    for e_d in (0.0, 0.1, 0.3, 0.5):
        for m in (0.0, 0.1, 0.3, 0.5):
            assert compute_intrinsic_error_mapping(e_d, m) <= 0.5 + 1e-15


# ---------------------------------------------------------------------------
# §1 -- apply_link6b_channel_fold: identity pass-through + folded transmittance
# ---------------------------------------------------------------------------


def test_channel_fold_identity_pass_through_exact():
    channel_eff, eta_gate, eta_filter, e_d_eff = apply_link6b_channel_fold(
        _BASE_CHANNEL,
        receiver_inputs=_identity_inputs(),
        gate_window_s=None,
        pulse_repetition_rate_hz=1e8,
        filter_sigma_hz=None,
        doppler_residual_fraction=None,
        source_linewidth_sigma_hz=0.0,
    )
    assert eta_gate == 1.0
    assert eta_filter == 1.0
    assert e_d_eff == _BASE_CHANNEL.intrinsic_qber
    assert channel_eff.transmittance == _BASE_CHANNEL.transmittance
    assert channel_eff.intrinsic_qber == _BASE_CHANNEL.intrinsic_qber


def test_channel_fold_multiplies_transmittance_by_both_acceptances():
    inputs = _identity_inputs(timing_jitter_s=1e-10, frequency_offset_hz=8e9)
    channel_eff, eta_gate, eta_filter, e_d_eff = apply_link6b_channel_fold(
        _BASE_CHANNEL,
        receiver_inputs=inputs,
        gate_window_s=1e-9,
        pulse_repetition_rate_hz=1e8,
        filter_sigma_hz=1e9,
        doppler_residual_fraction=0.01,
        source_linewidth_sigma_hz=0.0,
    )
    assert channel_eff.transmittance == pytest.approx(
        _BASE_CHANNEL.transmittance * eta_gate * eta_filter, rel=0.0, abs=1e-15
    )
    assert e_d_eff == _BASE_CHANNEL.intrinsic_qber


# ---------------------------------------------------------------------------
# §8 -- signal-only property + Q'_vacuum invariance scoping (B1/R1)
# ---------------------------------------------------------------------------


def test_gate_filter_fold_leaves_noise_probabilities_and_base_q_vacuum_unchanged():
    inputs_identity = _identity_inputs(background_rate_hz=1e4, dark_count_rate_hz=500.0)
    inputs_with_6b = _identity_inputs(
        background_rate_hz=1e4,
        dark_count_rate_hz=500.0,
        timing_jitter_s=1e-10,
        frequency_offset_hz=8e9,
    )
    block_a = compute_receiver_block(
        channel=_BASE_CHANNEL,
        detector=_BASE_DETECTOR,
        intensities=INTENSITIES,
        n_pulses=1_000_000,
        pi=_PI,
        receiver_inputs=inputs_identity,
        gate_window_s=1e-9,
        pulse_repetition_rate_hz=1e8,
    )
    block_b = compute_receiver_block(
        channel=_BASE_CHANNEL,
        detector=_BASE_DETECTOR,
        intensities=INTENSITIES,
        n_pulses=1_000_000,
        pi=_PI,
        receiver_inputs=inputs_with_6b,
        gate_window_s=1e-9,
        pulse_repetition_rate_hz=1e8,
        filter_sigma_hz=1e9,
        doppler_residual_fraction=0.01,
    )
    assert block_a.p_bg == block_b.p_bg
    assert block_a.p_dk == block_b.p_dk
    assert block_a.p_noise == block_b.p_noise
    # base Q_vacuum == p_noise identically (bb84's honest-gain law at mu=0).
    assert block_a.p_noise == block_b.p_noise


def test_q_vacuum_prime_unchanged_at_p_ap_zero_under_gate_filter_loss():
    inputs_no_6b = _identity_inputs(afterpulse_prob=0.0)
    inputs_with_6b = _identity_inputs(
        afterpulse_prob=0.0, timing_jitter_s=1e-10, frequency_offset_hz=8e9
    )
    kwargs = dict(
        channel=_BASE_CHANNEL,
        detector=_BASE_DETECTOR,
        intensities=INTENSITIES,
        n_pulses=1_000_000,
        pi=_PI,
        gate_window_s=1e-9,
        pulse_repetition_rate_hz=1e8,
        filter_sigma_hz=1e9,
        doppler_residual_fraction=0.01,
    )
    block_no_6b = compute_receiver_block(receiver_inputs=inputs_no_6b, **kwargs)
    block_with_6b = compute_receiver_block(receiver_inputs=inputs_with_6b, **kwargs)
    assert block_no_6b.gains["vacuum"] == pytest.approx(block_no_6b.p_noise, rel=0.0, abs=1e-15)
    assert block_with_6b.gains["vacuum"] == pytest.approx(
        block_with_6b.p_noise, rel=0.0, abs=1e-15
    )


def test_q_vacuum_prime_decreases_under_gate_filter_loss_when_p_ap_positive():
    kwargs = dict(
        channel=_BASE_CHANNEL,
        detector=_BASE_DETECTOR,
        intensities=INTENSITIES,
        n_pulses=1_000_000,
        pi=_PI,
        gate_window_s=1e-9,
        pulse_repetition_rate_hz=1e8,
    )
    inputs_no_loss = _identity_inputs(afterpulse_prob=0.02)
    inputs_with_loss = _identity_inputs(
        afterpulse_prob=0.02, timing_jitter_s=1e-10, frequency_offset_hz=8e9
    )
    block_no_loss = compute_receiver_block(receiver_inputs=inputs_no_loss, **kwargs)
    block_with_loss = compute_receiver_block(
        receiver_inputs=inputs_with_loss,
        filter_sigma_hz=1e9,
        doppler_residual_fraction=0.01,
        **kwargs,
    )
    assert block_with_loss.gains["vacuum"] < block_no_loss.gains["vacuum"]

    # Exact base-law assertion at the folded transmittance, followed by the
    # LINK-6a shared-history transform -- reconstructed independently here,
    # never asserted as a multiplicative "scaling" of Q'_vacuum (B1/R1).
    channel_eff, eta_gate, eta_filter, _ = apply_link6b_channel_fold(
        _BASE_CHANNEL,
        receiver_inputs=inputs_with_loss,
        gate_window_s=1e-9,
        pulse_repetition_rate_hz=1e8,
        filter_sigma_hz=1e9,
        doppler_residual_fraction=0.01,
        source_linewidth_sigma_hz=0.0,
    )
    from qkd.bb84 import run_decoy_bb84
    from dataclasses import replace

    detector_eff = replace(_BASE_DETECTOR, dark_count_prob=block_with_loss.p_noise)
    base = run_decoy_bb84(channel_eff, INTENSITIES, 1_000_000, detector_eff, eve=None)
    q_prime, e_prime, t_prime, a, q_bar, q_bar_reg = shared_history_afterpulse(
        base.gains, base.qber_per_intensity, _PI, 0.02
    )
    assert block_with_loss.gains["vacuum"] == pytest.approx(q_prime["vacuum"], rel=0.0, abs=1e-15)
    expected_q_vacuum_prime = 1.0 - (1.0 - base.gains["vacuum"]) * (1.0 - a)
    assert block_with_loss.gains["vacuum"] == pytest.approx(
        expected_q_vacuum_prime, rel=0.0, abs=1e-12
    )


def test_q_vacuum_prime_invariant_under_misalignment_only_at_any_p_ap():
    kwargs = dict(
        channel=_BASE_CHANNEL,
        detector=_BASE_DETECTOR,
        intensities=INTENSITIES,
        n_pulses=1_000_000,
        pi=_PI,
        gate_window_s=None,
        pulse_repetition_rate_hz=1e8,
    )
    inputs_no_misalignment = _identity_inputs(afterpulse_prob=0.02)
    inputs_misalignment = _identity_inputs(afterpulse_prob=0.02, misalignment_error=0.1)
    block_no = compute_receiver_block(receiver_inputs=inputs_no_misalignment, **kwargs)
    block_with = compute_receiver_block(receiver_inputs=inputs_misalignment, **kwargs)

    assert block_with.gains == block_no.gains
    assert block_with.q_bar_reg == block_no.q_bar_reg
    assert block_with.a == block_no.a
    assert block_with.gains["vacuum"] == block_no.gains["vacuum"]
    # T'_x / E'_x DO change under misalignment.
    assert block_with.qber_per_intensity["signal"] != block_no.qber_per_intensity["signal"]


def test_q_signal_prime_exact_against_base_law_at_folded_transmittance():
    inputs = _identity_inputs(
        afterpulse_prob=0.02, timing_jitter_s=1e-10, frequency_offset_hz=8e9
    )
    block = compute_receiver_block(
        channel=_BASE_CHANNEL,
        detector=_BASE_DETECTOR,
        intensities=INTENSITIES,
        n_pulses=1_000_000,
        pi=_PI,
        receiver_inputs=inputs,
        gate_window_s=1e-9,
        pulse_repetition_rate_hz=1e8,
        filter_sigma_hz=1e9,
        doppler_residual_fraction=0.01,
    )
    channel_eff, eta_gate, eta_filter, e_d_eff = apply_link6b_channel_fold(
        _BASE_CHANNEL,
        receiver_inputs=inputs,
        gate_window_s=1e-9,
        pulse_repetition_rate_hz=1e8,
        filter_sigma_hz=1e9,
        doppler_residual_fraction=0.01,
        source_linewidth_sigma_hz=0.0,
    )
    eta = channel_eff.transmittance * _BASE_DETECTOR.detection_efficiency
    mu = INTENSITIES["signal"]
    y0 = block.p_noise
    expected_base_q_signal = 1.0 - (1.0 - y0) * math.exp(-eta * mu)
    from qkd.bb84 import run_decoy_bb84
    from dataclasses import replace

    detector_eff = replace(_BASE_DETECTOR, dark_count_prob=y0)
    base = run_decoy_bb84(channel_eff, INTENSITIES, 1_000_000, detector_eff, eve=None)
    assert base.gains["signal"] == pytest.approx(expected_base_q_signal, rel=0.0, abs=1e-15)
    q_prime, *_rest = shared_history_afterpulse(
        base.gains, base.qber_per_intensity, _PI, inputs.afterpulse_prob
    )
    assert block.gains["signal"] == pytest.approx(q_prime["signal"], rel=0.0, abs=1e-15)


# ---------------------------------------------------------------------------
# §4 -- built-in owners: construction domains
# ---------------------------------------------------------------------------


def test_timing_jitter_effect_domain():
    TimingJitterEffect(jitter_sigma_s=0.0)
    TimingJitterEffect(jitter_sigma_s=1e-10)
    with pytest.raises(ValueError):
        TimingJitterEffect(jitter_sigma_s=-1e-10)
    with pytest.raises(ValueError):
        TimingJitterEffect(jitter_sigma_s=float("nan"))
    with pytest.raises(ValueError):
        TimingJitterEffect(jitter_sigma_s=float("inf"))


def test_polarization_misalignment_effect_domain():
    PolarizationMisalignmentEffect(error_prob=0.0)
    PolarizationMisalignmentEffect(error_prob=0.5)
    with pytest.raises(ValueError):
        PolarizationMisalignmentEffect(error_prob=0.5 + 1e-12)
    with pytest.raises(ValueError):
        PolarizationMisalignmentEffect(error_prob=-1e-12)


def test_phase_misalignment_effect_parameter_domain():
    PhaseMisalignmentEffect(delta_phi_rad=0.0)
    PhaseMisalignmentEffect(delta_phi_rad=math.pi / 4.0)
    with pytest.raises(ValueError):
        PhaseMisalignmentEffect(delta_phi_rad=math.pi / 4.0 + 1e-12)
    with pytest.raises(ValueError):
        PhaseMisalignmentEffect(delta_phi_rad=math.pi)


def test_phase_misalignment_effect_emits_sin_squared_hand_anchor():
    effect = PhaseMisalignmentEffect(delta_phi_rad=0.1)
    observables = effect.evaluate(0.0, geom=None, context=None)
    assert observables.channel.misalignment_error == pytest.approx(
        0.009966711079379185, rel=1e-12
    )


def test_phase_misalignment_periodicity_regression_pi_rejected_not_zero_output():
    # sin**2(pi) == 0 (in-range output) -- the domain must be enforced on
    # the *parameter*, not the periodic output (B5).
    assert math.sin(math.pi) ** 2 == pytest.approx(0.0, abs=1e-30)
    with pytest.raises(ValueError):
        PhaseMisalignmentEffect(delta_phi_rad=math.pi)


def test_polarization_and_phase_misalignment_are_single_contributor_fields():
    stack = ChannelStack(
        [
            PolarizationMisalignmentEffect(error_prob=0.05),
            PhaseMisalignmentEffect(delta_phi_rad=0.1),
        ],
        _StubGeometryProvider(),
        seed=None,
    )
    with pytest.raises(SingleContributorConflictError):
        stack.evaluate(0.0, sample_index=0)


class _StubGeometryProvider:
    def at(self, t):
        from qkd.link import PassGeometry

        return PassGeometry(t_s=t, elevation_deg=45.0, slant_range_km=1000.0)


# ---------------------------------------------------------------------------
# §4 -- PDT allowlist membership + codec anti-drift (sixteen)
# ---------------------------------------------------------------------------


def test_new_owners_are_deterministic_pdt_admissible_members():
    for effect_id in ("timing_jitter", "polarization_misalignment", "phase_misalignment"):
        assert PDT_ADMISSIBLE_EFFECTS[effect_id] == "deterministic"


def test_pdt_admissible_effects_has_fourteen_members():
    assert len(PDT_ADMISSIBLE_EFFECTS) == 14
    deterministic = [k for k, v in PDT_ADMISSIBLE_EFFECTS.items() if v == "deterministic"]
    law = [k for k, v in PDT_ADMISSIBLE_EFFECTS.items() if v == "law"]
    assert len(deterministic) == 13
    assert law == ["scintillation_fading"]


# ---------------------------------------------------------------------------
# §3 -- required-when-consumed + accepted-but-unused recording (mission level)
# ---------------------------------------------------------------------------


def test_timing_jitter_requires_gate_window_s_at_mission_level():
    receiver = ReceiverModel(pi=_PI)
    with pytest.raises(GateWindowRequiredError):
        simulate_pass(
            MissionConfig(samples=5),
            receiver=receiver,
            link_effects=[TimingJitterEffect(jitter_sigma_s=1e-10)],
        )


def test_frequency_offset_requires_filter_sigma_hz_at_mission_level():
    receiver = ReceiverModel(pi=_PI)
    with pytest.raises(FilterControlRequiredError):
        simulate_pass(
            MissionConfig(samples=5),
            receiver=receiver,
            link_effects=[DopplerShiftEffect(carrier_frequency_hz=3.8e14)],
        )


def test_frequency_offset_requires_doppler_residual_fraction_at_mission_level():
    receiver = ReceiverModel(pi=_PI)
    with pytest.raises(FilterControlRequiredError):
        simulate_pass(
            MissionConfig(samples=5),
            receiver=receiver,
            link_effects=[DopplerShiftEffect(carrier_frequency_hz=3.8e14)],
            link_controls={"filter_sigma_hz": 1e9},
        )


def test_source_linewidth_without_filter_raises_at_mission_level():
    receiver = ReceiverModel(pi=_PI, source_linewidth_sigma_hz=2e8)
    with pytest.raises(FilterControlRequiredError):
        simulate_pass(MissionConfig(samples=5), receiver=receiver)


def test_filter_controls_accepted_but_unused_when_no_frequency_offset_active():
    receiver = ReceiverModel(pi=_PI)
    result = simulate_pass(
        MissionConfig(samples=5),
        receiver=receiver,
        link_controls={"filter_sigma_hz": 1e9, "doppler_residual_fraction": 0.5},
    )
    assert result.link_provenance is not None
    manifest = json.loads(result.link_provenance)
    assert manifest["link_controls"]["filter_sigma_hz"] == 1e9
    assert manifest["link_controls"]["doppler_residual_fraction"] == 0.5


# ---------------------------------------------------------------------------
# §2 -- control bounds: zero/NaN/+-inf/just-inside for the two new controls
# ---------------------------------------------------------------------------


def test_filter_sigma_hz_bounds_enforced_at_mission_level():
    receiver = ReceiverModel(pi=_PI)
    from qkd.link import ControlBoundsError

    with pytest.raises(ControlBoundsError):
        simulate_pass(
            MissionConfig(samples=5),
            receiver=receiver,
            link_effects=[DopplerShiftEffect(carrier_frequency_hz=3.8e14)],
            link_controls={
                "filter_sigma_hz": MIN_FILTER_SIGMA_HZ - 1.0,
                "doppler_residual_fraction": 0.1,
            },
        )
    # Just inside the bounds is accepted.
    simulate_pass(
        MissionConfig(samples=5),
        receiver=receiver,
        link_effects=[DopplerShiftEffect(carrier_frequency_hz=3.8e14)],
        link_controls={
            "filter_sigma_hz": MIN_FILTER_SIGMA_HZ,
            "doppler_residual_fraction": 0.1,
        },
    )


def test_doppler_residual_fraction_bounds_enforced_at_mission_level():
    receiver = ReceiverModel(pi=_PI)
    from qkd.link import ControlBoundsError

    with pytest.raises(ControlBoundsError):
        simulate_pass(
            MissionConfig(samples=5),
            receiver=receiver,
            link_effects=[DopplerShiftEffect(carrier_frequency_hz=3.8e14)],
            link_controls={"filter_sigma_hz": 1e9, "doppler_residual_fraction": 1.0 + 1e-9},
        )
    for value in (0.0, 1.0):
        simulate_pass(
            MissionConfig(samples=5),
            receiver=receiver,
            link_effects=[DopplerShiftEffect(carrier_frequency_hz=3.8e14)],
            link_controls={"filter_sigma_hz": 1e9, "doppler_residual_fraction": value},
        )


def test_control_value_nan_and_inf_rejected():
    receiver = ReceiverModel(pi=_PI)
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError):
            simulate_pass(
                MissionConfig(samples=5),
                receiver=receiver,
                link_effects=[DopplerShiftEffect(carrier_frequency_hz=3.8e14)],
                link_controls={"filter_sigma_hz": bad, "doppler_residual_fraction": 0.1},
            )


# ---------------------------------------------------------------------------
# §1.2 -- ReceiverModel.source_linewidth_sigma_hz validation
# ---------------------------------------------------------------------------


def test_receiver_model_source_linewidth_finite_nonnegative():
    ReceiverModel(pi=_PI, source_linewidth_sigma_hz=0.0)
    ReceiverModel(pi=_PI, source_linewidth_sigma_hz=1e8)
    for bad in (float("nan"), float("inf"), float("-inf"), -1.0):
        with pytest.raises(ReceiverConfigError):
            ReceiverModel(pi=_PI, source_linewidth_sigma_hz=bad)


# ---------------------------------------------------------------------------
# §3 -- time-varying Doppler reaches its matching sample, both modes
# ---------------------------------------------------------------------------


def _hand_frequency_offset_hz(radial_velocity_km_s: float, carrier_frequency_hz: float) -> float:
    c_m_s = 299_792_458.0
    return -((radial_velocity_km_s * 1000.0) / c_m_s) * carrier_frequency_hz


def test_time_varying_doppler_reaches_matching_sample_sampled_mode():
    carrier_frequency_hz = 3.8e14
    filter_sigma_hz = 2e9
    doppler_residual_fraction = 0.02
    cfg = MissionConfig(samples=5)
    pass_geometry = satellite_pass(
        samples=cfg.samples,
        altitude_km=cfg.altitude_km,
        peak_elevation_deg=cfg.peak_elevation_deg,
        horizon_elevation_deg=cfg.horizon_elevation_deg,
    )
    provider = TableGeometryProvider(pass_geometry)
    stack = ChannelStack(
        [DopplerShiftEffect(carrier_frequency_hz=carrier_frequency_hz)], provider, seed=None
    )

    for sample_index, t in enumerate(pass_geometry.time_s):
        state = stack.evaluate(t, sample_index=sample_index)
        base_channel = channel_state(
            elevation_deg=pass_geometry.elevation_deg[sample_index],
            slant_range_km=pass_geometry.slant_range_km[sample_index],
            eta_override=1.0,
        )
        residual_channel = dataclasses.replace(
            base_channel, transmittance=base_channel.transmittance
        )
        inputs = ReceiverInputs(
            background_rate_hz=0.0,
            dark_count_rate_hz=0.0,
            afterpulse_prob=0.0,
            dead_time_s=0.0,
            timing_jitter_s=0.0,
            frequency_offset_hz=state.channel.frequency_offset_hz,
            misalignment_error=0.0,
        )
        block = compute_receiver_block(
            channel=residual_channel,
            detector=_BASE_DETECTOR,
            intensities=INTENSITIES,
            n_pulses=1000,
            pi=_PI,
            receiver_inputs=inputs,
            gate_window_s=None,
            pulse_repetition_rate_hz=1e8,
            filter_sigma_hz=filter_sigma_hz,
            doppler_residual_fraction=doppler_residual_fraction,
        )
        expected_offset = _hand_frequency_offset_hz(
            pass_geometry.radial_velocity_km_s[sample_index], carrier_frequency_hz
        )
        assert state.channel.frequency_offset_hz == pytest.approx(
            expected_offset, rel=0.0, abs=1e-6
        )
        expected_eta_filter = compute_filter_acceptance(
            frequency_offset_hz=expected_offset,
            filter_sigma_hz=filter_sigma_hz,
            doppler_residual_fraction=doppler_residual_fraction,
            source_linewidth_sigma_hz=0.0,
        )
        assert block.eta_filter == pytest.approx(expected_eta_filter, rel=1e-12)


def test_time_varying_doppler_reaches_matching_sample_pdt_mode():
    carrier_frequency_hz = 3.8e14
    filter_sigma_hz = 2e9
    doppler_residual_fraction = 0.02
    cfg = MissionConfig(samples=200)
    pass_geometry = satellite_pass(
        samples=cfg.samples,
        altitude_km=cfg.altitude_km,
        peak_elevation_deg=cfg.peak_elevation_deg,
        horizon_elevation_deg=cfg.horizon_elevation_deg,
    )
    provider = TableGeometryProvider(pass_geometry)
    law_owner = ScintillationFadingEffect(rytov_variance_zenith=0.001, aperture_averaging=0.5)
    stack = ChannelStack(
        [DopplerShiftEffect(carrier_frequency_hz=carrier_frequency_hz)], provider, seed=None
    )

    sample_index = 3
    t = pass_geometry.time_s[sample_index]
    state = stack.evaluate(t, sample_index=sample_index)
    base_channel = channel_state(
        elevation_deg=pass_geometry.elevation_deg[sample_index],
        slant_range_km=pass_geometry.slant_range_km[sample_index],
    )
    inputs = ReceiverInputs(
        background_rate_hz=0.0,
        dark_count_rate_hz=0.0,
        afterpulse_prob=0.0,
        dead_time_s=0.0,
        timing_jitter_s=0.0,
        frequency_offset_hz=state.channel.frequency_offset_hz,
        misalignment_error=0.0,
    )
    geom = provider.at(t)
    law = law_owner.stationary_law(geom)
    block = compute_receiver_block_pdt(
        law=law,
        channel_base=base_channel,
        detector=_BASE_DETECTOR,
        intensities=INTENSITIES,
        n_pulses=1000,
        pi=_PI,
        receiver_inputs=inputs,
        gate_window_s=None,
        pulse_repetition_rate_hz=1e8,
        filter_sigma_hz=filter_sigma_hz,
        doppler_residual_fraction=doppler_residual_fraction,
    )
    expected_offset = _hand_frequency_offset_hz(
        pass_geometry.radial_velocity_km_s[sample_index], carrier_frequency_hz
    )
    expected_eta_filter = compute_filter_acceptance(
        frequency_offset_hz=expected_offset,
        filter_sigma_hz=filter_sigma_hz,
        doppler_residual_fraction=doppler_residual_fraction,
        source_linewidth_sigma_hz=0.0,
    )
    assert block.eta_filter == pytest.approx(expected_eta_filter, rel=1e-12)


# ---------------------------------------------------------------------------
# §5 -- PDT-vs-sampled ensemble consistency with 6b inputs active
# ---------------------------------------------------------------------------


def test_pdt_vs_sampled_ensemble_consistency_with_6b_inputs_active():
    from qkd.detection import PdtConfig

    pdt_config = PdtConfig(fading_coherence_time_s=3e-3, block_duration_s=0.476955506437)
    receiver = ReceiverModel(pi=_PI)
    link_effects = [
        ScintillationFadingEffect(rytov_variance_zenith=0.001, aperture_averaging=0.5),
    ]
    controls = {"gate_window_s": 1e-9}

    pdt_result = simulate_pass(
        MissionConfig(),
        receiver=receiver,
        link_effects=[TimingJitterEffect(jitter_sigma_s=1e-10)] + link_effects,
        link_controls=controls,
        link_mode="pdt",
        pdt_config=pdt_config,
    )

    seeds = range(60)
    sampled_rates = []
    for seed in seeds:
        sampled_result = simulate_pass(
            MissionConfig(),
            receiver=receiver,
            link_effects=[TimingJitterEffect(jitter_sigma_s=1e-10)] + link_effects,
            link_controls=controls,
            link_seed=seed,
        )
        sampled_rates.append(sampled_result.secure_key_rate_per_pulse[2])

    mean_sampled = sum(sampled_rates) / len(sampled_rates)
    pdt_rate = pdt_result.secure_key_rate_per_pulse[2]
    if mean_sampled > 0.0:
        rel_diff = abs(pdt_rate - mean_sampled) / mean_sampled
        assert rel_diff < 5e-2


# ---------------------------------------------------------------------------
# §5 -- manifest v2 round-trip byte-identical (sampled + PDT)
# ---------------------------------------------------------------------------


def test_manifest_v2_round_trip_byte_identical_sampled():
    receiver = ReceiverModel(pi=_PI, source_linewidth_sigma_hz=1e8)
    result = simulate_pass(
        MissionConfig(samples=10),
        receiver=receiver,
        link_effects=[
            TimingJitterEffect(jitter_sigma_s=1e-10),
            PolarizationMisalignmentEffect(error_prob=0.01),
            DopplerShiftEffect(carrier_frequency_hz=3.8e14),
        ],
        link_controls={
            "gate_window_s": 1e-9,
            "filter_sigma_hz": 1e9,
            "doppler_residual_fraction": 0.01,
        },
    )
    manifest = json.loads(result.link_provenance)
    assert manifest["manifest_version"] == 2
    assert manifest["pipeline_version"] == LINK_PIPELINE_VERSION
    assert manifest["receiver"]["source_linewidth_sigma_hz"] == 1e8

    replayed = replay_from_provenance(result.link_provenance)
    assert dataclasses.asdict(replayed) == dataclasses.asdict(result)


def test_manifest_v2_round_trip_byte_identical_pdt():
    from qkd.detection import PdtConfig

    receiver = ReceiverModel(pi=_PI)
    pdt_config = PdtConfig(fading_coherence_time_s=3e-3, block_duration_s=0.476955506437)
    result = simulate_pass(
        MissionConfig(),
        receiver=receiver,
        link_effects=[
            PhaseMisalignmentEffect(delta_phi_rad=0.1),
            ScintillationFadingEffect(rytov_variance_zenith=0.02, aperture_averaging=0.5),
        ],
        link_mode="pdt",
        pdt_config=pdt_config,
    )
    replayed = replay_from_provenance(result.link_provenance)
    assert dataclasses.asdict(replayed) == dataclasses.asdict(result)


# ---------------------------------------------------------------------------
# §5, B3 -- the six cross-version compatibility rejections
# ---------------------------------------------------------------------------


def _v1_with_receiver(**receiver_extra):
    manifest = _valid_manifest_v1_dict()
    manifest["receiver"] = {
        "pi": {"signal": 0.8, "decoy": 0.15, "vacuum": 0.05},
        "operating_convention": "next_live_gate_v1",
        **receiver_extra,
    }
    manifest["model_ids"]["receiver"] = "qkd_receiver_mean_field_v1"
    return manifest


def test_b3_v1_with_link_6b1_pipeline_version_rejected():
    manifest = _valid_manifest_v1_dict()
    manifest["pipeline_version"] = LINK_PIPELINE_VERSION
    with pytest.raises(ManifestValidationError):
        validate_manifest_object(manifest)


def test_b3_v1_with_6b_effect_id_rejected():
    manifest = _valid_manifest_v1_dict()
    manifest["effects"] = [
        {
            "effect_id": "timing_jitter",
            "type_id": "qkd.effects.TimingJitterEffect",
            "parameters_complete": True,
            "params": {"jitter_sigma_s": 1e-10},
        }
    ]
    with pytest.raises(ManifestValidationError):
        validate_manifest_object(manifest)


def test_b3_v1_with_6b_control_name_rejected():
    manifest = _valid_manifest_v1_dict()
    manifest["link_controls"] = {"filter_sigma_hz": 1e9}
    with pytest.raises(ManifestValidationError):
        validate_manifest_object(manifest)


def test_b3_v1_with_source_linewidth_sigma_hz_rejected():
    manifest = _v1_with_receiver(source_linewidth_sigma_hz=0.0)
    with pytest.raises(ManifestValidationError):
        validate_manifest_object(manifest)


def test_b3_v2_with_link_6a1_pipeline_version_rejected():
    manifest = _valid_manifest_dict()
    manifest["pipeline_version"] = LINK_PIPELINE_VERSION_V1
    with pytest.raises(ManifestValidationError):
        validate_manifest_object(manifest)


def test_b3_v2_receiver_missing_third_key_rejected():
    manifest = _valid_manifest_dict()
    manifest["receiver"] = {
        "pi": {"signal": 0.8, "decoy": 0.15, "vacuum": 0.05},
        "operating_convention": "next_live_gate_v1",
    }
    manifest["model_ids"]["receiver"] = "qkd_receiver_mean_field_v1"
    with pytest.raises(ManifestValidationError):
        validate_manifest_object(manifest)


def test_v1_manifest_valid_form_round_trips():
    manifest = _valid_manifest_v1_dict()
    validate_manifest_object(manifest)


def test_source_linewidth_sigma_hz_nan_inf_negative_rejected_in_v2_manifest():
    for bad in (float("nan"), float("inf"), float("-inf"), -1.0):
        manifest = _valid_manifest_dict()
        manifest["receiver"] = {
            "pi": {"signal": 0.8, "decoy": 0.15, "vacuum": 0.05},
            "operating_convention": "next_live_gate_v1",
            "source_linewidth_sigma_hz": bad,
        }
        manifest["model_ids"]["receiver"] = "qkd_receiver_mean_field_v1"
        with pytest.raises(ManifestValidationError):
            validate_manifest_object(manifest)
