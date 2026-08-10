"""Tests for LINK-2 (docs/LINK_2_PLAN.md §6; ADR-0003 LINK queue §8).

Covers the production effect library (:mod:`qkd.effects`), the shared
atmosphere resolver (:func:`qkd.channel.resolved_atmosphere_config`), and the
stack-always mission seam (:func:`qkd.mission._production_link_effects`,
``simulate_pass``). Test 1 is the parity certificate: an inline reference
result, constructed independently from the primitives the pre-migration code
path used (direct ``channel_state()`` with no ``eta_override``, the same
``SatellitePass`` construction, ``simulate_profile()``, and the existing
``_pass_result_from_profile`` helper), compared byte-for-byte against the
migrated, stack-always ``simulate_pass()`` result -- both through the real
``run._build_results()`` emission builder, both schema-validated with
``deep=True``.

Plan §6 test 2 (LINK-1's ``test_none_empty_identity_paths_byte_identical``
passing unmodified) and test 15 (full-suite green) are not separate pytest
functions here: ``tests/test_link.py`` is untouched and is exercised by the
same ``pytest`` invocation that collects this file, and the full-suite
count is reported outside pytest.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace

import pytest

from qkd.channel import (
    DEFAULT_ATMOSPHERE,
    atmospheric_transmittance,
    channel_state,
    geometric_transmittance,
    resolved_atmosphere_config,
)
from qkd.effects import (
    AtmosphericAbsorptionEffect,
    DetectorQuantumEfficiencyEffect,
    GeometricLossEffect,
    SystemEfficiencyEffect,
)
from qkd.link import (
    ChannelObservables,
    ChannelStack,
    DuplicateEffectIdError,
    EffectEvaluationContext,
    LinkObservables,
    PassGeometry,
    TableGeometryProvider,
    apply_link_state,
)
from qkd.mission import (
    MissionConfig,
    _pass_result_from_profile,
    _production_link_effects,
    simulate_pass,
    simulate_profile,
)
from qkd.orbit import satellite_pass
from qkd.run import _build_results
from qkd.schema import validate_results_schema
from qkd.signals import ChannelState, DetectorParams


# ---------------------------------------------------------------------------
# Test-only fixtures / helpers (independent of tests/test_link.py by design)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _UserMultiplicativeEffect:
    """Minimal user-supplied multiplicative transmittance effect for §6 test 9/10."""

    effect_id: str
    transmittance_factor: float = 1.0

    def evaluate(self, t, geom, *, context) -> LinkObservables:
        return LinkObservables(
            channel=ChannelObservables(transmittance_factor=self.transmittance_factor)
        )


def _tiny_pass():
    return satellite_pass(
        samples=9, altitude_km=550.0, peak_elevation_deg=90.0, horizon_elevation_deg=10.0
    )


def _tiny_provider() -> TableGeometryProvider:
    return TableGeometryProvider(_tiny_pass())


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


def _noop_context() -> EffectEvaluationContext:
    """A context production effects never touch -- rng_for asserts if called."""

    def _rng_for(purpose, index=None):
        raise AssertionError("production effects must not request RNG streams.")

    return EffectEvaluationContext(controls={}, sample_index=None, rng_for=_rng_for)


def _canonical_bytes(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _inline_reference_result(cfg: MissionConfig):
    """Reconstruct the pre-LINK-2 pass body directly from its own primitives.

    Independent of ``simulate_pass`` -- no shared code path with the
    migrated implementation beyond the primitives that were already true
    before LINK-2 (``satellite_pass``, ``channel_state`` with no override,
    ``simulate_profile``, ``_pass_result_from_profile``).
    """

    pass_geometry = satellite_pass(
        samples=cfg.samples,
        altitude_km=cfg.altitude_km,
        peak_elevation_deg=cfg.peak_elevation_deg,
        horizon_elevation_deg=cfg.horizon_elevation_deg,
    )
    channel_states = [
        channel_state(
            elevation_deg=elevation_deg,
            slant_range_km=slant_range_km,
            atmosphere=cfg.atmosphere,
        )
        for elevation_deg, slant_range_km in zip(
            pass_geometry.elevation_deg, pass_geometry.slant_range_km
        )
    ]
    profile = simulate_profile(
        pass_geometry.time_s,
        channel_states,
        intensities=cfg.intensities,
        n_pulses=cfg.n_pulses,
        detector=cfg.detector,
        pulse_repetition_rate_hz=cfg.pulse_repetition_rate_hz,
        sky_condition=cfg.sky_condition,
    )
    return _pass_result_from_profile(pass_geometry, profile, cfg)


def _parity_bytes(cfg: MissionConfig):
    """Inline-reference vs migrated ``simulate_pass`` canonical bytes + payloads."""

    payload_inline = _build_results(
        _inline_reference_result(cfg), plot_path="outputs/qkd_teleportation.png"
    )
    payload_migrated = _build_results(
        simulate_pass(cfg), plot_path="outputs/qkd_teleportation.png"
    )
    return (
        _canonical_bytes(payload_inline),
        _canonical_bytes(payload_migrated),
        payload_inline,
        payload_migrated,
    )


# ---------------------------------------------------------------------------
# 1. The parity certificate (plan §6 test 1)
# ---------------------------------------------------------------------------


def test_migrated_emission_byte_identical_to_independent_inline_reference():
    cfg = MissionConfig(samples=31)

    bytes_inline, bytes_migrated, payload_inline, payload_migrated = _parity_bytes(cfg)

    assert bytes_inline == bytes_migrated
    assert validate_results_schema(payload_inline, deep=True) is True
    assert validate_results_schema(payload_migrated, deep=True) is True


# ---------------------------------------------------------------------------
# 3. Assembly order and fixed ids (plan §6 test 3)
# ---------------------------------------------------------------------------


def test_production_assembly_order_and_fixed_ids():
    resolved = resolved_atmosphere_config(None)
    detector = DetectorParams(detection_efficiency=0.42, dark_count_prob=1e-6)

    effects = _production_link_effects(resolved, detector)

    assert [effect.effect_id for effect in effects] == [
        "system_efficiency",
        "atmospheric_absorption",
        "geometric_loss",
        "detector_qe",
    ]
    assert [type(effect) for effect in effects] == [
        SystemEfficiencyEffect,
        AtmosphericAbsorptionEffect,
        GeometricLossEffect,
        DetectorQuantumEfficiencyEffect,
    ]

    # effect_id is init=False: callers cannot override it via the constructor.
    with pytest.raises(TypeError):
        SystemEfficiencyEffect(system_efficiency=0.5, effect_id="hacked")
    with pytest.raises(TypeError):
        AtmosphericAbsorptionEffect(zenith_optical_depth=0.1, effect_id="hacked")
    with pytest.raises(TypeError):
        GeometricLossEffect(beam_divergence_urad=1.0, rx_aperture_m=0.5, effect_id="hacked")
    with pytest.raises(TypeError):
        DetectorQuantumEfficiencyEffect(detection_efficiency=0.5, effect_id="hacked")


# ---------------------------------------------------------------------------
# 4. Atmospheric adapter honesty (plan §6 test 4)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("elevation_deg", [90.0, 45.0, 10.5])
def test_atmospheric_effect_matches_function_bitwise(elevation_deg):
    zenith_optical_depth = 0.2
    effect = AtmosphericAbsorptionEffect(zenith_optical_depth=zenith_optical_depth)
    geom = PassGeometry(t_s=0.0, elevation_deg=elevation_deg, slant_range_km=1_000.0)

    observed = effect.evaluate(0.0, geom, context=_noop_context())
    expected = atmospheric_transmittance(elevation_deg, zenith_optical_depth)

    assert observed.channel.transmittance_factor == expected


# ---------------------------------------------------------------------------
# 5. Geometric adapter honesty + boundaries (plan §6 test 5)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "slant_range_km,beam_divergence_urad,rx_aperture_m",
    [
        (0.0, 10.0, 0.5),  # range 0 -> 1.0
        (1_000.0, 0.0, 0.5),  # zero divergence -> 1.0
        (1_000.0, 10.0, 0.5),  # ordinary case
        (2_500.0, 25.0, 0.3),
    ],
)
def test_geometric_effect_matches_function_bitwise(
    slant_range_km, beam_divergence_urad, rx_aperture_m
):
    effect = GeometricLossEffect(
        beam_divergence_urad=beam_divergence_urad, rx_aperture_m=rx_aperture_m
    )
    geom = PassGeometry(t_s=0.0, elevation_deg=45.0, slant_range_km=slant_range_km)

    observed = effect.evaluate(0.0, geom, context=_noop_context())
    expected = geometric_transmittance(slant_range_km, beam_divergence_urad, rx_aperture_m)

    assert observed.channel.transmittance_factor == expected


# ---------------------------------------------------------------------------
# 6. Detector QE fold exactly-once + other fields survive (plan §6 test 6)
# ---------------------------------------------------------------------------


def test_detector_qe_fold_restores_original_exactly_once():
    original_detector = DetectorParams(
        detection_efficiency=0.63, dark_count_prob=2.5e-6, error_correction_efficiency=1.22
    )
    base_detector = replace(original_detector, detection_efficiency=1.0)
    base_channel = _channel_state(transmittance=0.7)

    provider = _tiny_provider()
    stack = ChannelStack(
        [DetectorQuantumEfficiencyEffect(detection_efficiency=original_detector.detection_efficiency)],
        provider,
    )
    t = _tiny_pass().time_s[0]
    state = stack.evaluate(t, sample_index=0)

    new_channel, new_detector = apply_link_state(
        state, channel=base_channel, detector=base_detector
    )

    assert new_detector.detection_efficiency == original_detector.detection_efficiency
    assert new_detector.dark_count_prob == original_detector.dark_count_prob
    assert new_detector.error_correction_efficiency == original_detector.error_correction_efficiency
    # channel side is the identity fold (no channel-side effect in this stack)
    assert new_channel.transmittance == base_channel.transmittance


# ---------------------------------------------------------------------------
# 7. Full custom atmosphere parity (plan §6 test 7)
# ---------------------------------------------------------------------------


_ATMOSPHERE_VARIANTS = [
    {"zenith_optical_depth": 0.05},
    {"system_efficiency": 0.35},
    {"beam_divergence_urad": 25.0},
    {"rx_aperture_m": 0.8},
    {
        "zenith_optical_depth": 0.05,
        "system_efficiency": 0.35,
        "beam_divergence_urad": 25.0,
        "rx_aperture_m": 0.8,
    },
]


@pytest.mark.parametrize("overrides", _ATMOSPHERE_VARIANTS)
def test_full_custom_atmosphere_parity(overrides):
    cfg = MissionConfig(samples=15, atmosphere=overrides)

    bytes_inline, bytes_migrated, payload_inline, payload_migrated = _parity_bytes(cfg)

    assert bytes_inline == bytes_migrated
    assert validate_results_schema(payload_inline, deep=True) is True
    assert validate_results_schema(payload_migrated, deep=True) is True


# ---------------------------------------------------------------------------
# 8. Single-resolver guard (plan §6 test 8)
# ---------------------------------------------------------------------------


def test_resolver_single_source():
    custom = {"zenith_optical_depth": 0.33, "rx_aperture_m": 0.9}

    resolved = resolved_atmosphere_config(custom)
    expected = dict(DEFAULT_ATMOSPHERE)
    expected.update(custom)
    assert resolved == expected

    assert resolved_atmosphere_config(None) == dict(DEFAULT_ATMOSPHERE)
    assert resolved_atmosphere_config({}) == dict(DEFAULT_ATMOSPHERE)

    # direct channel_state() calls (pre-existing usage, unmodified) still pass.
    state = channel_state(elevation_deg=45.0, slant_range_km=800.0, atmosphere=custom)
    assert 0.0 <= state.transmittance <= 1.0


# ---------------------------------------------------------------------------
# 9. User effects compose after production, left-associated (plan §6 test 9)
# ---------------------------------------------------------------------------


def test_user_effects_compose_after_production():
    cfg = MissionConfig(samples=17)
    u1, u2 = 0.9, 0.7

    baseline_result = simulate_pass(cfg)
    with_user_result = simulate_pass(
        cfg,
        link_effects=[
            _UserMultiplicativeEffect("user-1", transmittance_factor=u1),
            _UserMultiplicativeEffect("user-2", transmittance_factor=u2),
        ],
    )

    for base_t, user_t in zip(baseline_result.transmittance, with_user_result.transmittance):
        expected = (base_t * u1) * u2
        assert user_t == expected


# ---------------------------------------------------------------------------
# 10. User/production id collision rejected (plan §6 test 10)
# ---------------------------------------------------------------------------


def test_user_effect_colliding_with_production_id_rejected():
    cfg = MissionConfig(samples=9)
    colliding = _UserMultiplicativeEffect("system_efficiency", transmittance_factor=0.9)

    with pytest.raises(DuplicateEffectIdError):
        simulate_pass(cfg, link_effects=[colliding])


# ---------------------------------------------------------------------------
# 11. Missing geometry raises at evaluation (plan §6 test 11)
# ---------------------------------------------------------------------------


def test_effects_raise_at_evaluation_on_missing_geometry_fields():
    geom = PassGeometry(t_s=0.0, elevation_deg=None, slant_range_km=None)
    context = _noop_context()

    atmospheric = AtmosphericAbsorptionEffect(zenith_optical_depth=0.2)
    with pytest.raises(ValueError, match="elevation_deg"):
        atmospheric.evaluate(0.0, geom, context=context)

    geometric = GeometricLossEffect(beam_divergence_urad=10.0, rx_aperture_m=0.5)
    with pytest.raises(ValueError, match="slant_range_km"):
        geometric.evaluate(0.0, geom, context=context)


# ---------------------------------------------------------------------------
# 12. Out-of-domain inputs fail at construction (plan §6 test 12, R1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "factory",
    [
        lambda: SystemEfficiencyEffect(system_efficiency=-0.1),
        lambda: SystemEfficiencyEffect(system_efficiency=1.1),
        lambda: SystemEfficiencyEffect(system_efficiency=float("nan")),
        lambda: SystemEfficiencyEffect(system_efficiency=float("inf")),
        lambda: DetectorQuantumEfficiencyEffect(detection_efficiency=-0.1),
        lambda: DetectorQuantumEfficiencyEffect(detection_efficiency=1.5),
        lambda: DetectorQuantumEfficiencyEffect(detection_efficiency=float("nan")),
        lambda: DetectorQuantumEfficiencyEffect(detection_efficiency=float("-inf")),
        lambda: AtmosphericAbsorptionEffect(zenith_optical_depth=-0.01),
        lambda: AtmosphericAbsorptionEffect(zenith_optical_depth=float("-inf")),
        lambda: AtmosphericAbsorptionEffect(zenith_optical_depth=float("nan")),
        lambda: GeometricLossEffect(beam_divergence_urad=-1.0, rx_aperture_m=0.5),
        lambda: GeometricLossEffect(beam_divergence_urad=10.0, rx_aperture_m=-0.5),
        lambda: GeometricLossEffect(beam_divergence_urad=float("nan"), rx_aperture_m=0.5),
        lambda: GeometricLossEffect(beam_divergence_urad=10.0, rx_aperture_m=float("inf")),
    ],
)
def test_out_of_domain_inputs_fail_at_construction(factory):
    with pytest.raises(ValueError):
        factory()


# ---------------------------------------------------------------------------
# 13. Domain boundaries accepted, parity holds (plan §6 test 13)
# ---------------------------------------------------------------------------


def test_domain_boundaries_accepted():
    # Construction accepts the exact 0.0 / 1.0 boundaries without raising.
    SystemEfficiencyEffect(system_efficiency=0.0)
    SystemEfficiencyEffect(system_efficiency=1.0)
    DetectorQuantumEfficiencyEffect(detection_efficiency=0.0)
    DetectorQuantumEfficiencyEffect(detection_efficiency=1.0)
    AtmosphericAbsorptionEffect(zenith_optical_depth=0.0)
    GeometricLossEffect(beam_divergence_urad=0.0, rx_aperture_m=0.0)

    # Full-pass parity at boundaries that leave transmittance/loss_db finite:
    # system_efficiency=0.0 would drive eta (and therefore loss_db) to 0/+inf,
    # tripping schema.py's pre-existing, LINK-2-independent
    # profile.aggregates.min_loss_db finiteness constraint for *any*
    # zero-transmittance pass (inline or migrated alike) -- see this test's
    # last block for that boundary checked at the stack-evaluation level
    # instead of through the full schema-validated pipeline.
    cfg_upper = MissionConfig(
        samples=13,
        atmosphere={"zenith_optical_depth": 0.0, "system_efficiency": 1.0},
        detector=DetectorParams(detection_efficiency=1.0, dark_count_prob=1e-6),
    )
    bytes_inline, bytes_migrated, payload_inline, payload_migrated = _parity_bytes(cfg_upper)
    assert bytes_inline == bytes_migrated
    assert validate_results_schema(payload_inline, deep=True) is True
    assert validate_results_schema(payload_migrated, deep=True) is True

    cfg_zero_qe = MissionConfig(
        samples=13,
        atmosphere={"zenith_optical_depth": 0.0, "system_efficiency": 1.0},
        detector=DetectorParams(detection_efficiency=0.0, dark_count_prob=1e-6),
    )
    bytes_inline, bytes_migrated, payload_inline, payload_migrated = _parity_bytes(cfg_zero_qe)
    assert bytes_inline == bytes_migrated
    assert validate_results_schema(payload_inline, deep=True) is True
    assert validate_results_schema(payload_migrated, deep=True) is True

    # system_efficiency=0.0 boundary, checked at the stack-evaluation level.
    provider = _tiny_provider()
    resolved = resolved_atmosphere_config(
        {"system_efficiency": 0.0, "zenith_optical_depth": 0.0}
    )
    detector = DetectorParams(detection_efficiency=0.5, dark_count_prob=1e-6)
    stack = ChannelStack(_production_link_effects(resolved, detector), provider)
    t = _tiny_pass().time_s[0]
    state = stack.evaluate(t, sample_index=0)
    assert state.channel.transmittance_factor == 0.0


# ---------------------------------------------------------------------------
# 14. Production QE is time-constant; varying-efficiency guard never fires
#     (plan §6 test 14)
# ---------------------------------------------------------------------------


def test_production_qe_constant_across_pass():
    cfg = MissionConfig(samples=41)
    pass_geometry = satellite_pass(
        samples=cfg.samples,
        altitude_km=cfg.altitude_km,
        peak_elevation_deg=cfg.peak_elevation_deg,
        horizon_elevation_deg=cfg.horizon_elevation_deg,
    )
    resolved = resolved_atmosphere_config(cfg.atmosphere)
    provider = TableGeometryProvider(pass_geometry)
    stack = ChannelStack(_production_link_effects(resolved, cfg.detector), provider)

    efficiencies = {
        stack.evaluate(t, sample_index=sample_index).detector.efficiency_factor
        for sample_index, t in enumerate(pass_geometry.time_s)
    }

    assert efficiencies == {cfg.detector.detection_efficiency}

    # End-to-end: the sample-varying-efficiency guard in simulate_pass never
    # fires for the (all time-constant) production effects.
    result = simulate_pass(cfg)
    assert len(result.transmittance) == cfg.samples
