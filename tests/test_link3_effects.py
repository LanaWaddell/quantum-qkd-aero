"""Tests for LINK-3 (docs/LINK_3_PLAN.md §6, tests 7-17).

Covers the ``TableGeometryProvider`` optional fourth column (``qkd.link``),
``DopplerShiftEffect``/``PointingLossEffect`` (``qkd.effects``), the
``simulate_pass`` bridge-rejection boundary, and mission-level pointing
integration. Tests 2 and 15 of ``docs/LINK_1_PLAN.md``/``docs/LINK_2_PLAN.md``
style apply here too: test 16 (frozen-hash/parity tests pass unmodified) and
test 17 (full suite green) are not separate pytest functions -- they are
exercised by the same ``pytest`` invocation that collects this file
(``tests/test_profile.py``, ``tests/test_fibre_sweep.py``, ``tests/test_link.py``,
``tests/test_effects.py`` are all untouched by this PR), plus the focused
"no velocity field in the emitted payload" assertion below (test 16's other
half). The full-suite count is reported outside pytest.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, replace

import pytest

from qkd.channel import channel_state, resolved_atmosphere_config
from qkd.effects import C_M_S, DopplerShiftEffect, PointingLossEffect
from qkd.link import (
    ChannelObservables,
    ChannelStack,
    DuplicateEffectIdError,
    EffectEvaluationContext,
    GeometryTableError,
    LinkObservables,
    PassGeometry,
    TableGeometryProvider,
    UnsupportedLinkObservableError,
)
from qkd.mission import MissionConfig, _pass_result_from_profile, simulate_pass, simulate_profile
from qkd.orbit import SatellitePass, satellite_pass
from qkd.run import _build_results
from qkd.schema import validate_results_schema


# ---------------------------------------------------------------------------
# Test-only fixtures / helpers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _MockFrequencyContributor:
    """Minimal user-supplied frequency_offset_hz contributor, distinct effect_id."""

    effect_id: str
    frequency_offset_hz: float

    def evaluate(self, t, geom, *, context) -> LinkObservables:
        return LinkObservables(
            channel=ChannelObservables(frequency_offset_hz=self.frequency_offset_hz)
        )


def _velocity_pass(samples: int = 21, peak_elevation_deg: float = 60.0):
    return satellite_pass(
        samples=samples, altitude_km=550.0, peak_elevation_deg=peak_elevation_deg,
        horizon_elevation_deg=10.0,
    )


def _velocity_provider(**kwargs) -> TableGeometryProvider:
    return TableGeometryProvider(_velocity_pass(**kwargs))


def _noop_context() -> EffectEvaluationContext:
    def _rng_for(purpose, index=None):
        raise AssertionError("LINK-3 effects must not request RNG streams.")

    return EffectEvaluationContext(controls={}, sample_index=None, rng_for=_rng_for)


def _canonical_bytes(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _contains_velocity_key(obj) -> bool:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if "velocity" in key.lower() or "doppler" in key.lower():
                return True
            if _contains_velocity_key(value):
                return True
    elif isinstance(obj, list):
        return any(_contains_velocity_key(item) for item in obj)
    return False


# ---------------------------------------------------------------------------
# 7. TableGeometryProvider optional fourth column
# ---------------------------------------------------------------------------


def test_provider_radial_velocity_absent_is_none():
    legacy = SatellitePass(
        time_s=[0.0, 1.0, 2.0],
        elevation_deg=[10.0, 45.0, 10.0],
        slant_range_km=[900.0, 600.0, 900.0],
    )
    provider = TableGeometryProvider(legacy)

    assert provider.at(0.0).radial_velocity_mps is None
    assert provider.at(0.5).radial_velocity_mps is None
    assert provider.at(2.0).radial_velocity_mps is None


def test_provider_radial_velocity_length_mismatch_rejected():
    bad = SatellitePass(
        time_s=[0.0, 1.0, 2.0],
        elevation_deg=[10.0, 45.0, 10.0],
        slant_range_km=[900.0, 600.0, 900.0],
        radial_velocity_km_s=[1.0, 2.0],
    )
    with pytest.raises(GeometryTableError):
        TableGeometryProvider(bad)


def test_provider_radial_velocity_non_finite_rejected():
    bad = SatellitePass(
        time_s=[0.0, 1.0, 2.0],
        elevation_deg=[10.0, 45.0, 10.0],
        slant_range_km=[900.0, 600.0, 900.0],
        radial_velocity_km_s=[1.0, float("nan"), 3.0],
    )
    with pytest.raises(GeometryTableError):
        TableGeometryProvider(bad)


def test_provider_radial_velocity_snapshot_immune_to_mutation():
    good = SatellitePass(
        time_s=[0.0, 1.0, 2.0],
        elevation_deg=[10.0, 45.0, 10.0],
        slant_range_km=[900.0, 600.0, 900.0],
        radial_velocity_km_s=[1.0, 2.0, 3.0],
    )
    provider = TableGeometryProvider(good)

    good.radial_velocity_km_s.append(999.0)
    good.radial_velocity_km_s[0] = -999.0

    assert provider.at(0.0).radial_velocity_mps == 1000.0


def test_provider_radial_velocity_exact_sample_conversion_exactly_once():
    good = SatellitePass(
        time_s=[0.0, 1.0, 2.0],
        elevation_deg=[10.0, 45.0, 10.0],
        slant_range_km=[900.0, 600.0, 900.0],
        radial_velocity_km_s=[1.0, -2.0, 3.0],
    )
    provider = TableGeometryProvider(good)

    assert provider.at(0.0).radial_velocity_mps == 1.0 * 1000.0
    assert provider.at(1.0).radial_velocity_mps == -2.0 * 1000.0
    assert provider.at(2.0).radial_velocity_mps == 3.0 * 1000.0


def test_provider_radial_velocity_linear_interpolation():
    good = SatellitePass(
        time_s=[0.0, 1.0, 2.0],
        elevation_deg=[10.0, 45.0, 10.0],
        slant_range_km=[900.0, 600.0, 900.0],
        radial_velocity_km_s=[1.0, -2.0, 3.0],
    )
    provider = TableGeometryProvider(good)

    geom = provider.at(0.5)
    assert geom.t_s == 0.5
    expected = 1000.0 + 0.5 * (-2000.0 - 1000.0)
    assert geom.radial_velocity_mps == expected

    geom2 = provider.at(1.5)
    expected2 = -2000.0 + 0.5 * (3000.0 - (-2000.0))
    assert geom2.radial_velocity_mps == expected2


def test_provider_radial_velocity_real_pass_matches_scaled_column():
    pass_geometry = _velocity_pass(samples=15)
    provider = TableGeometryProvider(pass_geometry)

    for index, t in enumerate(pass_geometry.time_s):
        geom = provider.at(t)
        assert geom.radial_velocity_mps == pass_geometry.radial_velocity_km_s[index] * 1000.0


# ---------------------------------------------------------------------------
# 8. Doppler: 0 at closest approach; positive approaching, negative receding
# ---------------------------------------------------------------------------


def test_doppler_zero_at_closest_approach_sign_by_approach_recede():
    provider = _velocity_provider(samples=21)
    effect = DopplerShiftEffect(carrier_frequency_hz=3.819e14)
    context = _noop_context()

    geom_mid = provider.at(0.0)
    assert geom_mid.radial_velocity_mps == 0.0
    observed_mid = effect.evaluate(0.0, geom_mid, context=context)
    assert observed_mid.channel.frequency_offset_hz == 0.0

    approaching_t = _velocity_pass(samples=21).time_s[0]  # first half: approaching
    geom_approach = provider.at(approaching_t)
    assert geom_approach.radial_velocity_mps < 0.0
    observed_approach = effect.evaluate(approaching_t, geom_approach, context=context)
    assert observed_approach.channel.frequency_offset_hz > 0.0

    receding_t = _velocity_pass(samples=21).time_s[-1]  # second half: receding
    geom_recede = provider.at(receding_t)
    assert geom_recede.radial_velocity_mps > 0.0
    observed_recede = effect.evaluate(receding_t, geom_recede, context=context)
    assert observed_recede.channel.frequency_offset_hz < 0.0


# ---------------------------------------------------------------------------
# 9. 785 nm anchor vs an independent first-order calculation
# ---------------------------------------------------------------------------


def test_doppler_785nm_anchor_matches_first_order_calculation():
    wavelength_m = 785e-9
    carrier_frequency_hz = C_M_S / wavelength_m
    assert carrier_frequency_hz == pytest.approx(3.819e14, rel=1e-3)

    v_r_mps = 6_000.0  # 6 km/s, receding
    geom = PassGeometry(t_s=0.0, elevation_deg=None, slant_range_km=None,
                        radial_velocity_mps=v_r_mps)
    effect = DopplerShiftEffect(carrier_frequency_hz=carrier_frequency_hz)

    observed = effect.evaluate(0.0, geom, context=_noop_context())

    # Independent calculation, same operation order deliberately used so the
    # comparison can be bitwise (plan §6 test 9).
    expected = -(v_r_mps / C_M_S) * carrier_frequency_hz
    assert observed.channel.frequency_offset_hz == expected
    assert abs(observed.channel.frequency_offset_hz) == pytest.approx(7.64e9, rel=1e-2)


# ---------------------------------------------------------------------------
# 10. Missing radial_velocity_mps => evaluation raises naming effect + field
# ---------------------------------------------------------------------------


def test_doppler_raises_naming_effect_and_field_when_velocity_missing():
    geom = PassGeometry(t_s=0.0, elevation_deg=90.0, slant_range_km=550.0)
    effect = DopplerShiftEffect(carrier_frequency_hz=1.0e14)

    with pytest.raises(ValueError, match="DopplerShiftEffect") as excinfo:
        effect.evaluate(0.0, geom, context=_noop_context())
    assert "radial_velocity_mps" in str(excinfo.value)


# ---------------------------------------------------------------------------
# 11. Real Doppler + distinct-ID mock sums per ratified rule; duplicate
#     DopplerShiftEffect instances rejected by fixed-ID collision
# ---------------------------------------------------------------------------


def test_doppler_sums_with_distinct_id_mock_contributor():
    provider = _velocity_provider(samples=21)
    t = _velocity_pass(samples=21).time_s[0]

    doppler = DopplerShiftEffect(carrier_frequency_hz=2.0e14)
    mock = _MockFrequencyContributor("mock-frequency", frequency_offset_hz=1_234.5)

    geom = provider.at(t)
    doppler_component = doppler.evaluate(t, geom, context=_noop_context()).channel.frequency_offset_hz

    stack = ChannelStack([doppler, mock], provider)
    state = stack.evaluate(t, sample_index=0)

    assert state.channel.frequency_offset_hz == pytest.approx(
        doppler_component + 1_234.5, rel=0.0, abs=1e-9
    )


def test_duplicate_doppler_effect_instances_rejected():
    provider = _velocity_provider(samples=9)
    with pytest.raises(DuplicateEffectIdError):
        ChannelStack(
            [
                DopplerShiftEffect(carrier_frequency_hz=1.0e14),
                DopplerShiftEffect(carrier_frequency_hz=2.0e14),
            ],
            provider,
        )


# ---------------------------------------------------------------------------
# 12. simulate_pass bridge rejection: UnsupportedLinkObservableError naming
#     channel.frequency_offset_hz
# ---------------------------------------------------------------------------


def test_simulate_pass_rejects_doppler_via_bridge():
    cfg = MissionConfig(samples=21)
    doppler = DopplerShiftEffect(carrier_frequency_hz=2.0e14)

    with pytest.raises(UnsupportedLinkObservableError, match="channel.frequency_offset_hz"):
        simulate_pass(cfg, link_effects=[doppler])


# ---------------------------------------------------------------------------
# 13. Pointing values: 1.0 at zero offset; exp(-2) at offset==divergence;
#     monotone decreasing; documented [0, 1] domain
# ---------------------------------------------------------------------------


def test_pointing_loss_value_at_zero_offset_is_one():
    effect = PointingLossEffect(boresight_offset_urad=0.0, beam_divergence_urad=10.0)
    geom = PassGeometry(t_s=0.0, elevation_deg=None, slant_range_km=None)
    observed = effect.evaluate(0.0, geom, context=_noop_context())
    assert observed.channel.transmittance_factor == 1.0


def test_pointing_loss_value_at_offset_equal_divergence_matches_exp_minus_two():
    divergence = 25.0
    effect = PointingLossEffect(boresight_offset_urad=divergence, beam_divergence_urad=divergence)
    geom = PassGeometry(t_s=0.0, elevation_deg=None, slant_range_km=None)
    observed = effect.evaluate(0.0, geom, context=_noop_context())

    # Same operation order as the implementation, deliberately, for a
    # bitwise comparison (plan §6 test 13).
    expected = math.exp(-2.0 * (divergence / divergence) ** 2)
    assert observed.channel.transmittance_factor == expected
    assert observed.channel.transmittance_factor == math.exp(-2.0)


def test_pointing_loss_monotone_decreasing_in_offset():
    divergence = 30.0
    offsets = [0.0, 5.0, 10.0, 20.0, 40.0, 80.0]
    geom = PassGeometry(t_s=0.0, elevation_deg=None, slant_range_km=None)
    values = [
        PointingLossEffect(boresight_offset_urad=offset, beam_divergence_urad=divergence)
        .evaluate(0.0, geom, context=_noop_context())
        .channel.transmittance_factor
        for offset in offsets
    ]
    assert all(values[i] > values[i + 1] for i in range(len(values) - 1))
    assert all(0.0 <= v <= 1.0 for v in values)


def test_pointing_loss_domain_is_closed_zero_one_not_half_open():
    # Large finite offset/divergence ratio underflows to exactly 0.0 (plan
    # §2.3): the documented domain is [0, 1], not (0, 1].
    effect = PointingLossEffect(boresight_offset_urad=1.0e6, beam_divergence_urad=1.0)
    geom = PassGeometry(t_s=0.0, elevation_deg=None, slant_range_km=None)
    observed = effect.evaluate(0.0, geom, context=_noop_context())
    assert observed.channel.transmittance_factor == 0.0


# ---------------------------------------------------------------------------
# 14. Mission integration: per-sample multiplication contract + optional
#     independently constructed byte-equality oracle
# ---------------------------------------------------------------------------


def test_pointing_loss_mission_per_sample_multiplication_contract():
    cfg = MissionConfig(samples=21)
    offset, divergence = 12.0, 30.0
    factor = math.exp(-2.0 * (offset / divergence) ** 2)

    baseline = simulate_pass(cfg)
    with_pointing = simulate_pass(
        cfg, link_effects=[PointingLossEffect(boresight_offset_urad=offset,
                                              beam_divergence_urad=divergence)]
    )

    for base_t, pointed_t in zip(baseline.transmittance, with_pointing.transmittance):
        assert pointed_t == base_t * factor

    payload = _build_results(with_pointing, plot_path="outputs/qkd_teleportation.png")
    assert validate_results_schema(payload, deep=True) is True


def test_pointing_loss_mission_matches_independent_oracle_byte_identical():
    """Independent oracle: baseline channel states (via ``channel_state()``
    directly -- the pre-LINK-2 primitive, not the ``link_effects`` stack)
    times a hand-computed factor, through the existing
    ``simulate_profile``/``_pass_result_from_profile``/``_build_results``
    path -- never re-running the tested ``link_effects`` branch itself.
    """

    cfg = MissionConfig(samples=17)
    offset, divergence = 8.0, 40.0
    factor = math.exp(-2.0 * (offset / divergence) ** 2)

    pass_geometry = satellite_pass(
        samples=cfg.samples, altitude_km=cfg.altitude_km,
        peak_elevation_deg=cfg.peak_elevation_deg,
        horizon_elevation_deg=cfg.horizon_elevation_deg,
    )
    baseline_channel_states = [
        channel_state(
            elevation_deg=elevation_deg, slant_range_km=slant_range_km,
            atmosphere=cfg.atmosphere,
        )
        for elevation_deg, slant_range_km in zip(
            pass_geometry.elevation_deg, pass_geometry.slant_range_km
        )
    ]
    expected_channel_states = [
        replace(state, transmittance=state.transmittance * factor)
        for state in baseline_channel_states
    ]
    expected_profile = simulate_profile(
        pass_geometry.time_s,
        expected_channel_states,
        intensities=cfg.intensities,
        n_pulses=cfg.n_pulses,
        detector=cfg.detector,
        pulse_repetition_rate_hz=cfg.pulse_repetition_rate_hz,
        sky_condition=cfg.sky_condition,
    )
    expected_result = _pass_result_from_profile(pass_geometry, expected_profile, cfg)
    expected_payload = _build_results(expected_result, plot_path="outputs/qkd_teleportation.png")

    migrated_result = simulate_pass(
        cfg, link_effects=[PointingLossEffect(boresight_offset_urad=offset,
                                              beam_divergence_urad=divergence)]
    )
    migrated_payload = _build_results(migrated_result, plot_path="outputs/qkd_teleportation.png")

    assert _canonical_bytes(expected_payload) == _canonical_bytes(migrated_payload)
    assert validate_results_schema(expected_payload, deep=True) is True
    assert validate_results_schema(migrated_payload, deep=True) is True


# ---------------------------------------------------------------------------
# 15. Construction rejects invalid carrier/offset/divergence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "carrier_frequency_hz",
    [float("nan"), float("inf"), 0.0, -1.0e14],
)
def test_doppler_construction_rejects_invalid_carrier(carrier_frequency_hz):
    with pytest.raises(ValueError):
        DopplerShiftEffect(carrier_frequency_hz=carrier_frequency_hz)


@pytest.mark.parametrize(
    "boresight_offset_urad",
    [float("nan"), float("inf"), -1.0, -0.001],
)
def test_pointing_construction_rejects_invalid_offset(boresight_offset_urad):
    with pytest.raises(ValueError):
        PointingLossEffect(boresight_offset_urad=boresight_offset_urad, beam_divergence_urad=10.0)


@pytest.mark.parametrize(
    "beam_divergence_urad",
    [float("nan"), float("inf"), 0.0, -1.0],
)
def test_pointing_construction_rejects_invalid_divergence(beam_divergence_urad):
    with pytest.raises(ValueError):
        PointingLossEffect(boresight_offset_urad=0.0, beam_divergence_urad=beam_divergence_urad)


def test_pointing_construction_accepts_zero_offset():
    # boresight_offset_urad >= 0 is the valid boundary -- 0.0 is accepted.
    PointingLossEffect(boresight_offset_urad=0.0, beam_divergence_urad=10.0)


# ---------------------------------------------------------------------------
# 16. Emitted payload contains no velocity field (frozen-hash/parity tests
#     themselves are exercised unmodified by the same pytest invocation --
#     tests/test_profile.py, tests/test_fibre_sweep.py, tests/test_link.py,
#     tests/test_effects.py)
# ---------------------------------------------------------------------------


def test_default_emission_contains_no_velocity_field():
    cfg = MissionConfig(samples=11)
    result = simulate_pass(cfg)
    payload = _build_results(result, plot_path="outputs/qkd_teleportation.png")

    assert validate_results_schema(payload, deep=True) is True
    assert not _contains_velocity_key(payload)
    assert "velocity" not in json.dumps(payload)
    assert "doppler" not in json.dumps(payload).lower()
