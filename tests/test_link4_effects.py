"""Tests for LINK-4 (docs/LINK_4_PLAN.md, v2 approved, §7 tests 1-18).

Covers ``ScintillationFadingEffect``/``PointingJitterEffect``/``LogNormalLaw``
(``qkd.effects``) and the ``unit_mean_fading_fields`` declaration contract
(``qkd.link.ChannelStack``). Tests 17 and 18 are not separate pytest
functions: test 17's "frozen-hash/captured-fixture/LINK-1/2/3 tests pass
unmodified" half is exercised by the same ``pytest`` invocation that
collects this file (``tests/test_link.py``, ``tests/test_link3_effects.py``,
``tests/test_effects.py``, ``tests/test_profile.py``, and every other
existing test file are untouched by this PR); its other half -- pre-LINK-4
effects construct a ``ChannelStack`` exactly as before -- is the dedicated
regression test near the bottom of this file. Test 18 (full suite green) is
reported outside pytest by the invocation that runs the whole suite.

Statistical oracle tolerance bands (tests 1 and 3) are derived analytically
from normal/log-normal sample-mean and sample-variance theory *before* the
seed is pinned -- see the comments at each assertion for the derivation --
so the bands cannot be chosen against the realized draw.
"""

from __future__ import annotations

import json
import math
import statistics
from dataclasses import dataclass, replace
from unittest import mock

import pytest

import qkd.effects as effects_module
from qkd.effects import (
    LogNormalLaw,
    PointingJitterEffect,
    PointingLossEffect,
    RYTOV_WEAK_GUARD,
    ScintillationFadingEffect,
    SystemEfficiencyEffect,
)
from qkd.link import (
    ChannelObservables,
    ChannelStack,
    DetectorObservables,
    EffectEvaluationContext,
    EffectiveLinkState,
    InvalidObservableError,
    LinkObservables,
    PassGeometry,
    SeedRequiredError,
    apply_link_state,
)
from qkd.mission import MissionConfig, simulate_pass
from qkd.run import _build_results
from qkd.schema import validate_results_schema
from qkd.signals import ChannelState, DetectorParams


# ---------------------------------------------------------------------------
# Test-only fixtures / helpers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ConstantGeometryProvider:
    """Ignores ``t``; always returns the same geometry (only ``t_s`` varies).

    Statistical-test fixture: lets the tests draw many independent samples
    at a fixed elevation via distinct ``sample_index`` values, exactly the
    way ``ChannelStack``/``simulate_pass`` drive a real pass, without
    needing a real ``SatellitePass``.
    """

    geometry: PassGeometry

    def at(self, t: float) -> PassGeometry:
        return replace(self.geometry, t_s=t)


@dataclass(frozen=True)
class _MockUnitMeanEffect:
    """Minimal user effect exposing an arbitrary ``unit_mean_fading_fields`` value."""

    effect_id: str
    transmittance_factor: float = 1.0
    unit_mean_fading_fields: object = None

    def evaluate(self, t, geom, *, context) -> LinkObservables:
        return LinkObservables(
            channel=ChannelObservables(transmittance_factor=self.transmittance_factor)
        )


def _channel_state(**overrides) -> ChannelState:
    base = dict(
        transmittance=0.8,
        werner_p=0.9,
        intrinsic_qber=0.01,
        dark_count_prob=1e-6,
        slant_range_km=550.0,
        elevation_deg=90.0,
    )
    base.update(overrides)
    return ChannelState(**base)


def _detector_params(**overrides) -> DetectorParams:
    base = dict(detection_efficiency=0.5, dark_count_prob=1e-6)
    base.update(overrides)
    return DetectorParams(**base)


def _canonical_bytes(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _raising_rng_for(purpose, index=None):
    raise AssertionError(
        "sample_index validation must raise before any RNG stream is requested"
    )


# ---------------------------------------------------------------------------
# 1. mu_log/sigma_log hand-computed oracle; sample mean/variance/factor mean
#    within predeclared analytic bands
# ---------------------------------------------------------------------------


def test_scintillation_law_parameters_and_sample_moments_within_analytic_bands():
    elevation_deg = 30.0
    rytov_variance_zenith = 0.05
    aperture_averaging = 0.6
    n = 5000
    seed = 20260811

    # Independent hand-computed oracle (plan §2.1 formula), fixed before any
    # sample is drawn.
    sigma_r_sq = rytov_variance_zenith * math.sin(math.radians(elevation_deg)) ** (-11.0 / 6.0)
    log_variance = math.log(1.0 + aperture_averaging * sigma_r_sq)
    expected_sigma_log = math.sqrt(log_variance)
    expected_mu_log = -log_variance / 2.0

    effect = ScintillationFadingEffect(
        rytov_variance_zenith=rytov_variance_zenith, aperture_averaging=aperture_averaging
    )
    geom = PassGeometry(t_s=0.0, elevation_deg=elevation_deg, slant_range_km=None)

    mu_log, sigma_log = effect._law_parameters(geom)
    assert mu_log == pytest.approx(expected_mu_log, abs=1e-12)
    assert sigma_log == pytest.approx(expected_sigma_log, abs=1e-12)

    # Analytic tolerance bands, derived from normal-sample statistics
    # *before* drawing (never chosen against the realized sample): for N
    # i.i.d. draws of X ~ N(mu_log, sigma_log^2), the sample mean has
    # standard error sigma_log/sqrt(N); the (N-1)-denominator sample
    # variance has standard error sigma_log^2 * sqrt(2/(N-1)) (large-N
    # normal approximation to the scaled chi-square(N-1) distribution). A
    # 5-standard-error band keeps false-failure probability negligible
    # while still catching a materially wrong implementation.
    tol_mean_log = 5.0 * expected_sigma_log / math.sqrt(n)
    tol_var_log = 5.0 * expected_sigma_log**2 * math.sqrt(2.0 / (n - 1))
    # factor = exp(X) is log-normal with mu=mu_log, sigma=sigma_log; since
    # mu_log = -sigma_log^2/2 by the pure-fading normalization,
    # E[factor] = 1 and Var[factor] = exp(sigma_log^2) - 1 (standard
    # log-normal moment identities).
    var_factor = math.exp(expected_sigma_log**2) - 1.0
    tol_mean_factor = 5.0 * math.sqrt(var_factor / n)

    provider = _ConstantGeometryProvider(geom)
    stack = ChannelStack([effect], provider, seed=seed)
    factors = [
        stack.evaluate(float(idx), sample_index=idx).channel.transmittance_factor
        for idx in range(n)
    ]
    log_samples = [math.log(f) for f in factors]

    sample_mean_log = statistics.fmean(log_samples)
    sample_var_log = statistics.variance(log_samples)
    sample_mean_factor = statistics.fmean(factors)

    # Realized seed=20260811, n=5000: sample_mean_log ~= -0.051948 (band
    # +/-0.022536 around expected -0.050785); sample_var_log ~= 0.103561
    # (band +/-0.010158 around expected 0.101570); sample_mean_factor ~=
    # 0.999594 (band +/-0.023120 around expected 1.0) -- all comfortably
    # inside their predeclared bands.
    assert sample_mean_log == pytest.approx(expected_mu_log, abs=tol_mean_log)
    assert sample_var_log == pytest.approx(expected_sigma_log**2, abs=tol_var_log)
    assert sample_mean_factor == pytest.approx(1.0, abs=tol_mean_factor)


# ---------------------------------------------------------------------------
# 2. Elevation coupling: sigma_log strictly increasing as E decreases
# ---------------------------------------------------------------------------


def test_scintillation_sigma_log_strictly_increasing_as_elevation_decreases():
    effect = ScintillationFadingEffect(rytov_variance_zenith=0.01, aperture_averaging=0.7)
    elevations = [70.0, 50.0, 30.0, 15.0, 8.0]  # strictly decreasing
    sigma_logs = [
        effect.stationary_law(
            PassGeometry(t_s=0.0, elevation_deg=e, slant_range_km=None)
        ).sigma_log
        for e in elevations
    ]
    assert all(sigma_logs[i] < sigma_logs[i + 1] for i in range(len(sigma_logs) - 1))


# ---------------------------------------------------------------------------
# 3. Jitter: domain [0, 1] incl. underflow-to-exactly-0.0; seeded mean within
#    predeclared band; zero-jitter => factor == 1.0
# ---------------------------------------------------------------------------


def test_pointing_jitter_zero_jitter_gives_identity_factor():
    geom = PassGeometry(t_s=0.0, elevation_deg=None, slant_range_km=None)
    provider = _ConstantGeometryProvider(geom)
    effect = PointingJitterEffect(jitter_sigma_urad=0.0, beam_divergence_urad=20.0)
    stack = ChannelStack([effect], provider, seed=1)
    for idx in range(5):
        state = stack.evaluate(float(idx), sample_index=idx)
        assert state.channel.transmittance_factor == 1.0


def test_pointing_jitter_underflows_to_exactly_zero_for_extreme_parameters():
    geom = PassGeometry(t_s=0.0, elevation_deg=None, slant_range_km=None)
    provider = _ConstantGeometryProvider(geom)
    effect = PointingJitterEffect(jitter_sigma_urad=1.0e6, beam_divergence_urad=1.0)
    stack = ChannelStack([effect], provider, seed=7)
    state = stack.evaluate(0.0, sample_index=0)
    assert state.channel.transmittance_factor == 0.0


def test_pointing_jitter_seeded_mean_within_analytic_band_of_closed_form_mean():
    sigma_j = 5.0
    divergence = 30.0
    n = 5000
    seed = 314159

    # Closed form (plan §2.2): factor = exp(-c * Q) with c = 2*sigma_j^2 /
    # divergence^2 and Q = theta_x^2 + theta_y^2 ~ sigma_j^2 * chi2(2), i.e.
    # Q/sigma_j^2 is Exponential(mean=2). Integrating the Exponential
    # moment-generating function gives E[factor] = 1/(1 + 2c) ==
    # 1/(1 + 4*sigma_j^2/divergence^2) (plan's stated closed form) and
    # Var[factor] = 1/(1 + 4c) - E[factor]^2. Both fixed before drawing.
    c = 2.0 * sigma_j**2 / divergence**2
    expected_mean = 1.0 / (1.0 + 2.0 * c)
    assert expected_mean == pytest.approx(1.0 / (1.0 + 4.0 * sigma_j**2 / divergence**2))
    expected_var = 1.0 / (1.0 + 4.0 * c) - expected_mean**2
    tol_mean = 5.0 * math.sqrt(expected_var / n)  # 5-standard-error band, as in test 1

    effect = PointingJitterEffect(jitter_sigma_urad=sigma_j, beam_divergence_urad=divergence)
    geom = PassGeometry(t_s=0.0, elevation_deg=None, slant_range_km=None)
    provider = _ConstantGeometryProvider(geom)
    stack = ChannelStack([effect], provider, seed=seed)

    factors = [
        stack.evaluate(float(idx), sample_index=idx).channel.transmittance_factor
        for idx in range(n)
    ]
    assert all(0.0 <= f <= 1.0 for f in factors)

    sample_mean = statistics.fmean(factors)
    # Realized seed=314159, n=5000: sample_mean ~= 0.898728 (band
    # +/-0.006396 around expected 0.9) -- comfortably inside.
    assert sample_mean == pytest.approx(expected_mean, abs=tol_mean)


# ---------------------------------------------------------------------------
# 4. stationary_law vs independent oracle; exp(mu+sigma^2/2)==1; shares the
#    private resolver with evaluate (structural, via a spy)
# ---------------------------------------------------------------------------


def test_stationary_law_matches_independent_oracle_and_unit_mean_identity():
    rytov = 0.03
    aperture = 0.4
    elevation_deg = 45.0
    effect = ScintillationFadingEffect(rytov_variance_zenith=rytov, aperture_averaging=aperture)
    geom = PassGeometry(t_s=0.0, elevation_deg=elevation_deg, slant_range_km=None)

    sigma_r_sq = rytov * math.sin(math.radians(elevation_deg)) ** (-11.0 / 6.0)
    log_variance = math.log(1.0 + aperture * sigma_r_sq)
    expected = LogNormalLaw(mu_log=-log_variance / 2.0, sigma_log=math.sqrt(log_variance))

    law = effect.stationary_law(geom)
    assert isinstance(law, LogNormalLaw)
    assert law.mu_log == pytest.approx(expected.mu_log, abs=1e-12)
    assert law.sigma_log == pytest.approx(expected.sigma_log, abs=1e-12)
    assert math.exp(law.mu_log + law.sigma_log**2 / 2.0) == pytest.approx(1.0, abs=1e-12)


def test_stationary_law_shares_private_resolver_with_evaluate():
    effect = ScintillationFadingEffect(rytov_variance_zenith=0.05, aperture_averaging=0.5)
    geom = PassGeometry(t_s=0.0, elevation_deg=40.0, slant_range_km=None)
    provider = _ConstantGeometryProvider(geom)
    stack = ChannelStack([effect], provider, seed=99)

    original = effects_module.ScintillationFadingEffect._law_parameters
    calls: list = []

    def spy(self, g):
        calls.append(g)
        return original(self, g)

    with mock.patch.object(effects_module.ScintillationFadingEffect, "_law_parameters", spy):
        law = effect.stationary_law(geom)
        stack.evaluate(0.0, sample_index=0)

    # Code-path identity (both calls hit the same resolver), not merely
    # moment agreement -- exactly one call from stationary_law, one from
    # evaluate (via ChannelStack), both with the (value-)equal geometry.
    assert len(calls) == 2
    assert calls[0] == geom
    assert calls[1] == geom

    mu_log, sigma_log = effect._law_parameters(geom)
    assert law.mu_log == mu_log
    assert law.sigma_log == sigma_log


# ---------------------------------------------------------------------------
# 5. sample_index=None => both effects raise naming sample_index, before
#    requesting an RNG stream
# ---------------------------------------------------------------------------


def test_both_effects_raise_when_sample_index_is_none():
    context = EffectEvaluationContext(controls={}, sample_index=None, rng_for=_raising_rng_for)

    scint = ScintillationFadingEffect(rytov_variance_zenith=0.05, aperture_averaging=0.5)
    geom_scint = PassGeometry(t_s=0.0, elevation_deg=45.0, slant_range_km=None)
    with pytest.raises(ValueError, match="sample_index"):
        scint.evaluate(0.0, geom_scint, context=context)

    jitter = PointingJitterEffect(jitter_sigma_urad=5.0, beam_divergence_urad=20.0)
    geom_jitter = PassGeometry(t_s=0.0, elevation_deg=None, slant_range_km=None)
    with pytest.raises(ValueError, match="sample_index"):
        jitter.evaluate(0.0, geom_jitter, context=context)


# ---------------------------------------------------------------------------
# 6. Same (seed, index) bit-identical across repetition, out-of-order
#    evaluation, and fresh stacks; different indices differ (tripwire)
# ---------------------------------------------------------------------------


def test_replay_bit_identical_across_repetition_order_and_fresh_stacks():
    geom = PassGeometry(t_s=0.0, elevation_deg=35.0, slant_range_km=None)
    provider = _ConstantGeometryProvider(geom)
    seed = 4242

    def make_effects():
        return [
            ScintillationFadingEffect(rytov_variance_zenith=0.05, aperture_averaging=0.5),
            PointingJitterEffect(jitter_sigma_urad=4.0, beam_divergence_urad=25.0),
        ]

    stack_a = ChannelStack(make_effects(), provider, seed=seed)
    state_repeat_1 = stack_a.evaluate(1.0, sample_index=3)
    state_repeat_2 = stack_a.evaluate(1.0, sample_index=3)
    assert state_repeat_1 == state_repeat_2

    stack_b = ChannelStack(make_effects(), provider, seed=seed)  # fresh instance
    state_fresh = stack_b.evaluate(1.0, sample_index=3)
    assert state_fresh == state_repeat_1

    stack_c = ChannelStack(make_effects(), provider, seed=seed)  # out-of-order
    stack_c.evaluate(1.0, sample_index=5)
    state_out_of_order = stack_c.evaluate(1.0, sample_index=3)
    assert state_out_of_order == state_repeat_1

    # Different index differs -- an empirical tripwire, documented as such
    # (plan §3), never proof of the independence model.
    state_other_index = stack_a.evaluate(1.0, sample_index=4)
    assert state_other_index != state_repeat_1


# ---------------------------------------------------------------------------
# 7. Mission replay on a demonstrably in-regime configuration: same
#    link_seed => byte-identical emission, deep-schema-valid; different seed
#    => different bytes
# ---------------------------------------------------------------------------


def test_mission_replay_in_regime_byte_identical_same_seed_differs_other_seed():
    horizon_elevation_deg = 25.0
    rytov_variance_zenith = 0.1  # spec-default zenith Rytov variance

    # Verify in-regime across the whole pass *before* relying on it (plan §7
    # test 7): sigma_R^2(E) = rytov_variance_zenith * sin(E)^(-11/6) is a
    # strictly decreasing function of E on (0, 90] (test 2), so it is
    # maximized at the pass's lowest elevation -- the horizon mask itself.
    sigma_r_sq_at_mask = rytov_variance_zenith * math.sin(
        math.radians(horizon_elevation_deg)
    ) ** (-11.0 / 6.0)
    assert sigma_r_sq_at_mask < RYTOV_WEAK_GUARD  # ~= 0.485 < 1.0

    cfg = MissionConfig(samples=41, horizon_elevation_deg=horizon_elevation_deg)
    effects = [
        ScintillationFadingEffect(
            rytov_variance_zenith=rytov_variance_zenith, aperture_averaging=0.3
        ),
        PointingJitterEffect(jitter_sigma_urad=3.0, beam_divergence_urad=25.0),
    ]

    result_a = simulate_pass(cfg, link_effects=effects, link_seed=123)
    result_b = simulate_pass(cfg, link_effects=effects, link_seed=123)
    payload_a = _build_results(result_a, plot_path="outputs/qkd_teleportation.png")
    payload_b = _build_results(result_b, plot_path="outputs/qkd_teleportation.png")

    assert validate_results_schema(payload_a, deep=True) is True
    assert _canonical_bytes(payload_a) == _canonical_bytes(payload_b)

    result_c = simulate_pass(cfg, link_effects=effects, link_seed=456)
    payload_c = _build_results(result_c, plot_path="outputs/qkd_teleportation.png")
    assert _canonical_bytes(payload_a) != _canonical_bytes(payload_c)


# ---------------------------------------------------------------------------
# 8. SeedRequiredError from simulate_pass with stochastic effects and no
#    link_seed
# ---------------------------------------------------------------------------


def test_simulate_pass_requires_seed_for_stochastic_effects():
    cfg = MissionConfig(samples=21, horizon_elevation_deg=25.0)
    effects = [ScintillationFadingEffect(rytov_variance_zenith=0.05, aperture_averaging=0.5)]
    with pytest.raises(SeedRequiredError):
        simulate_pass(cfg, link_effects=effects)


# ---------------------------------------------------------------------------
# 9. Horizon-inclusive opt-in run with spec-default scintillation parameters
#    raises the model-validity error naming model/elevation/sigma_R^2/guard
# ---------------------------------------------------------------------------


def test_default_horizon_pass_with_spec_default_rytov_raises_model_validity():
    cfg = MissionConfig(samples=21)  # default horizon_elevation_deg=10.0
    effects = [
        ScintillationFadingEffect(rytov_variance_zenith=0.1, aperture_averaging=0.3)
    ]  # spec-default zenith Rytov variance / aperture-averaging factor

    with pytest.raises(ValueError) as excinfo:
        simulate_pass(cfg, link_effects=effects, link_seed=1)

    message = str(excinfo.value)
    assert "ScintillationFadingEffect" in message
    assert "elevation_deg" in message
    assert "sigma_R^2" in message
    assert "RYTOV_WEAK_GUARD" in message


# ---------------------------------------------------------------------------
# 10. allow_out_of_regime=True permits the horizon-inclusive run
# ---------------------------------------------------------------------------


def test_allow_out_of_regime_permits_horizon_inclusive_run():
    cfg = MissionConfig(samples=21)  # default horizon_elevation_deg=10.0
    effects = [
        ScintillationFadingEffect(
            rytov_variance_zenith=0.1, aperture_averaging=0.3, allow_out_of_regime=True
        )
    ]
    # allow_out_of_regime=True names an explicit, caller-chosen out-of-regime
    # log-normal approximation (plan §2.1) -- not a validated
    # strong-turbulence model. The call must simply not raise.
    result = simulate_pass(cfg, link_effects=effects, link_seed=7)
    assert len(result.transmittance) == cfg.samples


# ---------------------------------------------------------------------------
# 11. Guard boundary tested directly on sigma_R^2 values; elevation domain
#     (None, NaN, +-inf, 0, negative, >90) raises through both entry points
# ---------------------------------------------------------------------------


def test_rytov_guard_boundary_tested_directly_on_sigma_r_sq_values():
    elevation_deg = 15.0
    base = math.sin(math.radians(elevation_deg)) ** (-11.0 / 6.0)

    # Solve directly for rytov_variance_zenith values that place sigma_R^2
    # just below and just above the guard -- targeting sigma_R^2 itself
    # rather than relying on float equality through sin(E) landing exactly
    # on the guard.
    rytov_below = 0.999 / base
    rytov_above = 1.001 / base
    sigma_r_sq_below = rytov_below * base
    sigma_r_sq_above = rytov_above * base
    assert sigma_r_sq_below < RYTOV_WEAK_GUARD < sigma_r_sq_above

    geom = PassGeometry(t_s=0.0, elevation_deg=elevation_deg, slant_range_km=None)

    effect_below = ScintillationFadingEffect(
        rytov_variance_zenith=rytov_below, aperture_averaging=0.5
    )
    effect_below.stationary_law(geom)  # no raise: just inside the guard

    effect_above = ScintillationFadingEffect(
        rytov_variance_zenith=rytov_above, aperture_averaging=0.5
    )
    with pytest.raises(ValueError, match="sigma_R"):
        effect_above.stationary_law(geom)

    effect_above_allowed = ScintillationFadingEffect(
        rytov_variance_zenith=rytov_above, aperture_averaging=0.5, allow_out_of_regime=True
    )
    effect_above_allowed.stationary_law(geom)  # no raise: explicit opt-in


@pytest.mark.parametrize(
    "elevation_deg",
    [None, float("nan"), float("inf"), float("-inf"), 0.0, -5.0, 90.001, 180.0],
)
def test_scintillation_elevation_domain_rejected_through_both_entry_points(elevation_deg):
    effect = ScintillationFadingEffect(rytov_variance_zenith=0.05, aperture_averaging=0.5)
    geom = PassGeometry(t_s=0.0, elevation_deg=elevation_deg, slant_range_km=None)

    with pytest.raises(ValueError, match="elevation_deg"):
        effect.stationary_law(geom)

    context = EffectEvaluationContext(controls={}, sample_index=0, rng_for=_raising_rng_for)
    with pytest.raises(ValueError, match="elevation_deg"):
        effect.evaluate(0.0, geom, context=context)


def test_scintillation_elevation_boundary_ninety_is_accepted():
    effect = ScintillationFadingEffect(rytov_variance_zenith=0.01, aperture_averaging=0.5)
    geom = PassGeometry(t_s=0.0, elevation_deg=90.0, slant_range_km=None)
    effect.stationary_law(geom)  # no raise: 90 is the closed upper boundary


# ---------------------------------------------------------------------------
# 12. Construction-time rejection of unknown and malformed (incl.
#     bare-string) unit_mean_fading_fields; recognized declaration accepted
# ---------------------------------------------------------------------------


def test_construction_rejects_bare_string_unit_mean_fading_fields():
    provider = _ConstantGeometryProvider(
        PassGeometry(t_s=0.0, elevation_deg=45.0, slant_range_km=None)
    )
    effect = _MockUnitMeanEffect(effect_id="mock", unit_mean_fading_fields="transmittance_factor")
    with pytest.raises(ValueError, match="bare string"):
        ChannelStack([effect], provider)


def test_construction_rejects_unrecognized_unit_mean_fading_field():
    provider = _ConstantGeometryProvider(
        PassGeometry(t_s=0.0, elevation_deg=45.0, slant_range_km=None)
    )
    effect = _MockUnitMeanEffect(
        effect_id="mock", unit_mean_fading_fields=["not_a_real_field"]
    )
    with pytest.raises(ValueError, match="unrecognized"):
        ChannelStack([effect], provider)


def test_construction_rejects_non_iterable_unit_mean_fading_fields():
    provider = _ConstantGeometryProvider(
        PassGeometry(t_s=0.0, elevation_deg=45.0, slant_range_km=None)
    )
    effect = _MockUnitMeanEffect(effect_id="mock", unit_mean_fading_fields=42)
    with pytest.raises(ValueError):
        ChannelStack([effect], provider)


def test_construction_accepts_recognized_unit_mean_fading_declaration():
    provider = _ConstantGeometryProvider(
        PassGeometry(t_s=0.0, elevation_deg=45.0, slant_range_km=None)
    )
    effect = _MockUnitMeanEffect(
        effect_id="mock",
        transmittance_factor=1.5,
        unit_mean_fading_fields=("transmittance_factor",),
    )
    stack = ChannelStack([effect], provider)
    state = stack.evaluate(0.0, sample_index=0)
    assert state.channel.transmittance_factor == 1.5


def test_construction_accepts_real_scintillation_effect_declaration():
    provider = _ConstantGeometryProvider(
        PassGeometry(t_s=0.0, elevation_deg=45.0, slant_range_km=None)
    )
    effect = ScintillationFadingEffect(rytov_variance_zenith=0.05, aperture_averaging=0.5)
    ChannelStack([effect], provider, seed=1)  # no raise


# ---------------------------------------------------------------------------
# 13. Real scintillation effect at an index with factor > 1 accepted;
#     undeclared effect emitting 1.5 rejected; mixed-stack effect-specificity
# ---------------------------------------------------------------------------


def test_declared_effect_factor_above_one_accepted_undeclared_rejected_mixed_stack():
    geom = PassGeometry(t_s=0.0, elevation_deg=45.0, slant_range_km=None)
    provider = _ConstantGeometryProvider(geom)

    scint = ScintillationFadingEffect(rytov_variance_zenith=0.3, aperture_averaging=1.0)
    stack = ChannelStack([scint], provider, seed=999)
    found_above_one = None
    for idx in range(200):
        state = stack.evaluate(float(idx), sample_index=idx)
        if state.channel.transmittance_factor > 1.0:
            found_above_one = state.channel.transmittance_factor
            break
    assert found_above_one is not None and found_above_one > 1.0

    undeclared = _MockUnitMeanEffect(effect_id="undeclared_mock", transmittance_factor=1.5)
    stack_undeclared = ChannelStack([undeclared], provider)
    with pytest.raises(InvalidObservableError):
        stack_undeclared.evaluate(0.0, sample_index=0)

    # Mixed stack, same evaluation: the declaring effect's factor is
    # relaxed while the undeclared effect's fixed 1.5 still raises -- the
    # relaxation is effect-specific, not stack-global.
    mixed_stack = ChannelStack([scint, undeclared], provider, seed=999)
    with pytest.raises(InvalidObservableError) as excinfo:
        mixed_stack.evaluate(0.0, sample_index=0)
    assert "undeclared_mock" in str(excinfo.value)


# ---------------------------------------------------------------------------
# 14. Synthetic bridge test: fade-up onto high base transmittance raises
#     (never clamps); full in-regime seeded pass stays within the bridge
#     domain (pinned-seed regression, not a universal guarantee)
# ---------------------------------------------------------------------------


def test_bridge_fade_up_onto_high_base_transmittance_raises_never_clamps():
    state = EffectiveLinkState(
        channel=ChannelObservables(transmittance_factor=1.2),
        detector=DetectorObservables(),
    )
    base_channel = _channel_state(transmittance=0.95)
    with pytest.raises(ValueError, match=r"outside \[0, 1\]"):
        apply_link_state(state, channel=base_channel, detector=_detector_params())


def test_full_in_regime_seeded_pass_stays_within_bridge_domain_pinned_seed_regression():
    # A pinned-seed regression case, not a universal probabilistic
    # guarantee (plan §7 test 14): the bridge could in principle still
    # raise for a different seed/parameter combination even in-regime,
    # since the deterministic base transmittance times an occasional >1
    # fade draw can exceed 1.0. This test certifies only the specific
    # configuration below.
    cfg = MissionConfig(samples=41, horizon_elevation_deg=25.0)
    effects = [
        ScintillationFadingEffect(rytov_variance_zenith=0.1, aperture_averaging=0.3),
        PointingJitterEffect(jitter_sigma_urad=3.0, beam_divergence_urad=25.0),
    ]
    result = simulate_pass(cfg, link_effects=effects, link_seed=2026)
    assert all(0.0 <= t <= 1.0 for t in result.transmittance)


# ---------------------------------------------------------------------------
# 15. Construction domains for all parameters
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rytov_variance_zenith", [float("nan"), float("inf"), -1.0, -0.001])
def test_scintillation_construction_rejects_invalid_rytov(rytov_variance_zenith):
    with pytest.raises(ValueError):
        ScintillationFadingEffect(
            rytov_variance_zenith=rytov_variance_zenith, aperture_averaging=0.5
        )


@pytest.mark.parametrize("aperture_averaging", [float("nan"), float("inf"), 0.0, -0.1, 1.5])
def test_scintillation_construction_rejects_invalid_aperture_averaging(aperture_averaging):
    with pytest.raises(ValueError):
        ScintillationFadingEffect(rytov_variance_zenith=0.05, aperture_averaging=aperture_averaging)


def test_scintillation_construction_accepts_boundaries():
    ScintillationFadingEffect(rytov_variance_zenith=0.0, aperture_averaging=1.0)


@pytest.mark.parametrize("jitter_sigma_urad", [float("nan"), float("inf"), -1.0, -0.001])
def test_jitter_construction_rejects_invalid_sigma(jitter_sigma_urad):
    with pytest.raises(ValueError):
        PointingJitterEffect(jitter_sigma_urad=jitter_sigma_urad, beam_divergence_urad=10.0)


@pytest.mark.parametrize("beam_divergence_urad", [float("nan"), float("inf"), 0.0, -1.0])
def test_jitter_construction_rejects_invalid_divergence(beam_divergence_urad):
    with pytest.raises(ValueError):
        PointingJitterEffect(jitter_sigma_urad=5.0, beam_divergence_urad=beam_divergence_urad)


def test_jitter_construction_accepts_zero_sigma():
    PointingJitterEffect(jitter_sigma_urad=0.0, beam_divergence_urad=10.0)


# ---------------------------------------------------------------------------
# 16. Composition with LINK-3 deterministic pointing bias: product relation
#     (same-order arithmetic), documented approximate
# ---------------------------------------------------------------------------


def test_composition_with_deterministic_pointing_bias_is_product_same_order():
    geom = PassGeometry(t_s=0.0, elevation_deg=None, slant_range_km=None)
    provider = _ConstantGeometryProvider(geom)

    bias = PointingLossEffect(boresight_offset_urad=8.0, beam_divergence_urad=25.0)
    jitter = PointingJitterEffect(jitter_sigma_urad=4.0, beam_divergence_urad=25.0)

    bias_only_stack = ChannelStack([bias], provider)
    jitter_only_stack = ChannelStack([jitter], provider, seed=55)
    combined_stack = ChannelStack([bias, jitter], provider, seed=55)

    bias_factor = bias_only_stack.evaluate(0.0, sample_index=0).channel.transmittance_factor
    jitter_factor = jitter_only_stack.evaluate(0.0, sample_index=0).channel.transmittance_factor
    combined_factor = combined_stack.evaluate(0.0, sample_index=0).channel.transmittance_factor

    # Same-order left-associated product -- ChannelStack's own composition
    # rule -- documented as approximate (plan §2.2, R3.3): the exact joint
    # treatment of a deterministic bias and isotropic Gaussian jitter is a
    # Rician/noncentral-chi-square radial model, not a bare product; the
    # cross term and finite-aperture overlap are deferred.
    assert combined_factor == pytest.approx(bias_factor * jitter_factor, rel=0.0, abs=1e-12)


# ---------------------------------------------------------------------------
# 17. Frozen-hash / captured-fixture / LINK-1/2/3 regression: effects that
#     never declare unit_mean_fading_fields construct exactly as before.
#     (The rest of test 17 -- unmodified existing test files passing -- is
#     exercised by the same pytest invocation that collects this file.)
# ---------------------------------------------------------------------------


def test_stack_construction_unaffected_for_effects_without_declaration():
    provider = _ConstantGeometryProvider(
        PassGeometry(t_s=0.0, elevation_deg=45.0, slant_range_km=550.0)
    )
    stack = ChannelStack([SystemEfficiencyEffect(system_efficiency=0.9)], provider)
    state = stack.evaluate(0.0, sample_index=0)
    assert state.channel.transmittance_factor == 0.9


def test_default_mission_emission_unaffected_by_link4():
    cfg = MissionConfig(samples=11)
    result = simulate_pass(cfg)
    payload = _build_results(result, plot_path="outputs/qkd_teleportation.png")
    assert validate_results_schema(payload, deep=True) is True
