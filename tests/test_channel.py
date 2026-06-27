import math

import pytest

from qkd.channel import (
    apply_bit_flip,
    apply_loss,
    atmospheric_transmittance,
    channel_state,
    geometric_transmittance,
    transmit_bit,
)


def test_apply_loss_extremes():
    assert apply_loss(1, p_loss=0.0) == 1
    assert apply_loss(1, p_loss=1.0) is None


def test_apply_bit_flip_extremes():
    assert apply_bit_flip(0, p_flip=0.0) == 0
    assert apply_bit_flip(0, p_flip=1.0) == 1


def test_transmit_bit_applies_loss_before_flip():
    assert transmit_bit(1, p_loss=1.0, p_flip=1.0) is None
    assert transmit_bit(1, p_loss=0.0, p_flip=1.0) == 0


def test_channel_state_transmittance_in_unit_interval():
    for elevation_deg in (5.0, 30.0, 90.0):
        for slant_range_km in (100.0, 1_000.0, 2_000.0):
            state = channel_state(
                elevation_deg=elevation_deg,
                slant_range_km=slant_range_km,
            )
            assert 0.0 <= state.transmittance <= 1.0


def test_channel_state_transmittance_increases_with_elevation():
    low_elevation = channel_state(elevation_deg=10.0, slant_range_km=1_000.0)
    high_elevation = channel_state(elevation_deg=80.0, slant_range_km=1_000.0)

    assert high_elevation.transmittance > low_elevation.transmittance


def test_channel_state_transmittance_decreases_with_range():
    near = channel_state(elevation_deg=45.0, slant_range_km=500.0)
    far = channel_state(elevation_deg=45.0, slant_range_km=2_000.0)

    assert near.transmittance > far.transmittance


def test_atmospheric_conditions_change_eta_but_not_werner_p():
    clear = channel_state(
        elevation_deg=45.0,
        slant_range_km=1_000.0,
        atmosphere={"zenith_optical_depth": 0.05},
    )
    hazy = channel_state(
        elevation_deg=45.0,
        slant_range_km=1_000.0,
        atmosphere={"zenith_optical_depth": 0.50},
    )

    assert clear.transmittance > hazy.transmittance
    assert clear.werner_p == hazy.werner_p


def test_channel_state_overrides_are_honored():
    state = channel_state(
        elevation_deg=45.0,
        slant_range_km=1_000.0,
        eta_override=0.25,
        p_override=0.70,
    )

    assert state.transmittance == 0.25
    assert state.werner_p == 0.70


def test_channel_state_equipment_properties_are_passthrough():
    state = channel_state(
        elevation_deg=45.0,
        slant_range_km=1_000.0,
        atmosphere={
            "intrinsic_qber": 0.02,
            "dark_count_prob": 2.0e-6,
        },
    )

    assert state.intrinsic_qber == 0.02
    assert state.dark_count_prob == 2.0e-6


def test_channel_state_records_geometry():
    state = channel_state(elevation_deg=37.0, slant_range_km=750.0)

    assert state.elevation_deg == 37.0
    assert state.slant_range_km == 750.0


def test_invalid_elevation_rejected():
    with pytest.raises(ValueError):
        channel_state(elevation_deg=0.0, slant_range_km=1_000.0)

    with pytest.raises(ValueError):
        channel_state(elevation_deg=91.0, slant_range_km=1_000.0)


def test_atmospheric_transmittance_monotonic_and_bounded():
    low_elevation = atmospheric_transmittance(
        elevation_deg=10.0,
        zenith_optical_depth=0.2,
    )
    high_elevation = atmospheric_transmittance(
        elevation_deg=80.0,
        zenith_optical_depth=0.2,
    )

    assert 0.0 <= low_elevation <= 1.0
    assert 0.0 <= high_elevation <= 1.0
    assert high_elevation > low_elevation


def test_geometric_transmittance_decreases_with_range():
    near = geometric_transmittance(
        slant_range_km=500.0,
        beam_divergence_urad=10.0,
        rx_aperture_m=0.5,
    )
    far = geometric_transmittance(
        slant_range_km=2_000.0,
        beam_divergence_urad=10.0,
        rx_aperture_m=0.5,
    )

    assert math.isfinite(near)
    assert math.isfinite(far)
    assert 0.0 <= far < near <= 1.0
