import math

import pytest

from qkd.bb84 import run_decoy_bb84
from qkd.channel import channel_state
from qkd.coherence import effective_werner_p_for_sky
from qkd.fibre import DEFAULT_FIBRE, fibre_channel_state, fibre_transmittance
from qkd.signals import DetectorParams
from qkd.teleportation import teleportation_fidelity


INTENSITIES = {"signal": 0.5, "decoy": 0.1, "vacuum": 0.0}
DETECTOR = DetectorParams(detection_efficiency=0.5, dark_count_prob=1.0e-6)


def test_fibre_transmittance_matches_standard_loss_law():
    for length_km in (0.0, 10.0, 50.0):
        expected = 10.0 ** (
            -(
                (DEFAULT_FIBRE["attenuation_db_km"] * length_km)
                + DEFAULT_FIBRE["fixed_loss_db"]
            )
            / 10.0
        )

        assert fibre_transmittance(length_km) == pytest.approx(expected, rel=0.0, abs=1e-12)


def test_fibre_transmittance_is_monotonic_and_bounded():
    short = fibre_transmittance(0.0)
    medium = fibre_transmittance(10.0)
    long = fibre_transmittance(50.0)

    assert 0.0 <= long < medium < short <= 1.0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"length_km": -1.0},
        {"length_km": 1.0, "attenuation_db_km": -0.1},
        {"length_km": 1.0, "fixed_loss_db": -0.1},
    ],
)
def test_fibre_transmittance_rejects_negative_inputs(kwargs):
    with pytest.raises(ValueError):
        fibre_transmittance(**kwargs)


def test_fibre_channel_state_is_geometry_free_and_uses_fibre_defaults():
    state = fibre_channel_state(25.0)

    assert state.slant_range_km is None
    assert state.elevation_deg is None
    assert state.transmittance == fibre_transmittance(25.0)
    assert state.werner_p == DEFAULT_FIBRE["werner_p"]
    assert state.intrinsic_qber == DEFAULT_FIBRE["intrinsic_qber"]
    assert state.dark_count_prob == DEFAULT_FIBRE["dark_count_prob"]


def test_fibre_channel_state_overrides_match_channel_interface():
    state = fibre_channel_state(25.0, eta_override=0.25, p_override=0.75)

    assert state.transmittance == 0.25
    assert state.werner_p == 0.75


def test_fibre_channel_state_runs_through_bb84_with_positive_skr_ordering():
    short = run_decoy_bb84(fibre_channel_state(10.0), INTENSITIES, 1_000_000, DETECTOR)
    longer = run_decoy_bb84(fibre_channel_state(20.0), INTENSITIES, 1_000_000, DETECTOR)
    very_long = run_decoy_bb84(fibre_channel_state(500.0), INTENSITIES, 1_000_000, DETECTOR)

    assert math.isfinite(short.secure_key_rate)
    assert math.isfinite(longer.secure_key_rate)
    assert short.secure_key_rate > 0.0
    assert longer.secure_key_rate > 0.0
    assert short.secure_key_rate > longer.secure_key_rate
    assert very_long.secure_key_rate >= 0.0


def test_dark_fibre_coherence_preserves_source_werner_p_and_fidelity():
    state = fibre_channel_state(25.0)

    p_eff = effective_werner_p_for_sky(
        state.transmittance,
        state.werner_p,
        DETECTOR.detection_efficiency,
        sky_condition="night",
    )
    source_fidelity = teleportation_fidelity(state.werner_p)
    fibre_fidelity = teleportation_fidelity(p_eff)

    assert p_eff == pytest.approx(state.werner_p, rel=0.0, abs=1e-9)
    assert fibre_fidelity.fidelity == pytest.approx(source_fidelity.fidelity, rel=0.0, abs=1e-9)


def test_same_bb84_protocol_accepts_atmospheric_and_fibre_channels():
    atmospheric = channel_state(elevation_deg=80.0, slant_range_km=550.0)
    fibre = fibre_channel_state(10.0)

    atmospheric_result = run_decoy_bb84(atmospheric, INTENSITIES, 1_000_000, DETECTOR)
    fibre_result = run_decoy_bb84(fibre, INTENSITIES, 1_000_000, DETECTOR)

    assert atmospheric_result.secure_key_rate >= 0.0
    assert fibre_result.secure_key_rate >= 0.0
    assert atmospheric_result.gains.keys() == fibre_result.gains.keys()
