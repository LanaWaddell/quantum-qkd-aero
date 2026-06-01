"""Phase 2B-5 tests for background-light degradation of werner_p."""

import math

import pytest

from qkd.channel import channel_state
from qkd.coherence import (
    SKY_BACKGROUND_RATE_HZ,
    effective_werner_p,
    effective_werner_p_for_sky,
)
from qkd.orbit import satellite_pass
from qkd.teleportation import teleportation_fidelity


DET_EFF = 0.5
P_SRC = 0.98


def test_zero_background_recovers_source_p_for_any_transmittance():
    for eta in (0.001, 0.01, 0.1, 0.5, 1.0):
        p_eff = effective_werner_p(eta, P_SRC, DET_EFF, background_rate_hz=0.0)
        assert math.isclose(p_eff, P_SRC, abs_tol=1e-15), eta


def test_more_loss_lowers_p_eff_only_through_signal_rate():
    etas = (0.5, 0.1, 0.01, 0.003, 0.001)
    p_effs = [
        effective_werner_p_for_sky(e, P_SRC, DET_EFF, sky_condition="day")
        for e in etas
    ]
    assert all(b <= a for a, b in zip(p_effs, p_effs[1:])), p_effs
    assert p_effs[0] > p_effs[-1]


def test_brighter_sky_degrades_p_eff():
    eta = 0.05
    night = effective_werner_p_for_sky(eta, P_SRC, DET_EFF, sky_condition="night")
    twilight = effective_werner_p_for_sky(eta, P_SRC, DET_EFF, sky_condition="twilight")
    day = effective_werner_p_for_sky(eta, P_SRC, DET_EFF, sky_condition="day")
    assert night > twilight > day
    assert math.isclose(night, P_SRC, abs_tol=1e-12)


def test_tighter_coincidence_window_restores_p_eff():
    windows = (10e-9, 5e-9, 2e-9, 1e-9, 0.5e-9, 0.1e-9)
    p_effs = [
        effective_werner_p(
            0.05, P_SRC, DET_EFF,
            background_rate_hz=SKY_BACKGROUND_RATE_HZ["day"],
            coincidence_window_s=window,
        )
        for window in windows
    ]
    assert all(b >= a for a, b in zip(p_effs, p_effs[1:])), p_effs
    assert p_effs[-1] > p_effs[0]


def test_fidelity_arches_over_pass_in_daylight_but_is_flat_at_night():
    p = satellite_pass(samples=101, peak_elevation_deg=90.0, horizon_elevation_deg=10.0)
    fids_night = []
    fids_day = []
    for elevation_deg, slant_range_km in zip(p.elevation_deg, p.slant_range_km):
        eta = channel_state(elevation_deg, slant_range_km).transmittance
        pe_night = effective_werner_p_for_sky(eta, P_SRC, DET_EFF, sky_condition="night")
        pe_day = effective_werner_p_for_sky(eta, P_SRC, DET_EFF, sky_condition="day")
        fids_night.append(teleportation_fidelity(pe_night).fidelity)
        fids_day.append(teleportation_fidelity(pe_day).fidelity)
    peak = len(p.time_s) // 2
    assert len({round(f, 9) for f in fids_night}) == 1
    assert math.isclose(fids_day[peak], max(fids_day), abs_tol=1e-12)
    assert fids_day[0] < fids_day[peak]
    assert fids_day[-1] < fids_day[peak]
    assert (fids_day[peak] - fids_day[0]) > 0.05


def test_p_eff_bounds():
    for eta in (0.001, 0.05, 0.5, 1.0):
        for sky in ("night", "twilight", "day"):
            p_eff = effective_werner_p_for_sky(eta, P_SRC, DET_EFF, sky_condition=sky)
            assert 0.0 <= p_eff <= P_SRC


def test_background_independent_of_transmittance():
    from qkd.coherence import background_coincidence_rate, signal_coincidence_rate
    b1 = background_coincidence_rate(SKY_BACKGROUND_RATE_HZ["day"], 1e-9, local_singles_rate_hz=6e6)
    b2 = background_coincidence_rate(SKY_BACKGROUND_RATE_HZ["day"], 1e-9, local_singles_rate_hz=6e6)
    assert b1 == b2
    s_hi = signal_coincidence_rate(0.5, DET_EFF, pair_rate_hz=1e7, alice_efficiency=0.6)
    s_lo = signal_coincidence_rate(0.05, DET_EFF, pair_rate_hz=1e7, alice_efficiency=0.6)
    assert s_hi > s_lo


def test_invalid_inputs_rejected():
    with pytest.raises(ValueError):
        effective_werner_p(0.5, 1.5, DET_EFF)
    with pytest.raises(ValueError):
        effective_werner_p(0.5, P_SRC, DET_EFF, coincidence_window_s=0.0)
    with pytest.raises(ValueError):
        effective_werner_p_for_sky(0.5, P_SRC, DET_EFF, sky_condition="eclipse")
