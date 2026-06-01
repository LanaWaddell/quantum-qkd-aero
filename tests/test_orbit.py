"""Tests for derived-geometry satellite-pass (orbit.py)."""
import math

import pytest

from qkd.orbit import EARTH_RADIUS_KM, satellite_pass


def test_satellite_pass_returns_requested_sample_count():
    p = satellite_pass(samples=51, altitude_km=550, peak_elevation_deg=90,
                       horizon_elevation_deg=10)
    assert len(p.time_s) == 51
    assert len(p.elevation_deg) == 51
    assert len(p.slant_range_km) == 51


def test_zenith_pass_reaches_ninety_at_midpass():
    p = satellite_pass(samples=11, altitude_km=550, peak_elevation_deg=90,
                       horizon_elevation_deg=10)
    mid = len(p.elevation_deg) // 2
    assert math.isclose(p.elevation_deg[mid], 90.0, abs_tol=1e-6)


def test_zenith_slant_range_equals_altitude():
    # Physical-coupling check: a true overhead pass is exactly 'altitude' away.
    alt = 550.0
    p = satellite_pass(samples=11, altitude_km=alt, peak_elevation_deg=90,
                       horizon_elevation_deg=10)
    mid = len(p.slant_range_km) // 2
    assert math.isclose(p.slant_range_km[mid], alt, abs_tol=1e-3)
    assert math.isclose(p.slant_range_km[mid], min(p.slant_range_km), abs_tol=1e-6)


def test_slant_range_is_coupled_to_elevation_by_geometry():
    # The defining honesty check: slant range must follow from elevation via the
    # orbital relation, NOT be independently interpolated. A stand-in fails this.
    alt = 550.0
    r = EARTH_RADIUS_KM + alt
    p = satellite_pass(samples=21, altitude_km=alt, peak_elevation_deg=90,
                       horizon_elevation_deg=10)
    for e_deg, d_km in zip(p.elevation_deg, p.slant_range_km):
        e = math.radians(e_deg)
        d_expected = math.sqrt(r**2 - EARTH_RADIUS_KM**2 * math.cos(e)**2) \
            - EARTH_RADIUS_KM * math.sin(e)
        assert math.isclose(d_expected, d_km, abs_tol=1e-6), e_deg


def test_pass_is_time_symmetric():
    p = satellite_pass(samples=11, altitude_km=550, peak_elevation_deg=90,
                       horizon_elevation_deg=10)
    assert math.isclose(p.time_s[0], -p.time_s[-1], abs_tol=1e-6)


def test_endpoints_at_horizon_mask():
    mask = 10.0
    p = satellite_pass(samples=11, altitude_km=550, peak_elevation_deg=90,
                       horizon_elevation_deg=mask)
    assert math.isclose(p.elevation_deg[0], mask, abs_tol=1e-6)
    assert math.isclose(p.elevation_deg[-1], mask, abs_tol=1e-6)


def test_elevation_rises_then_falls():
    p = satellite_pass(samples=21, altitude_km=550, peak_elevation_deg=90,
                       horizon_elevation_deg=10)
    elevs = p.elevation_deg
    peak_i = elevs.index(max(elevs))
    assert all(elevs[i] <= elevs[i + 1] for i in range(peak_i))
    assert all(elevs[i] >= elevs[i + 1] for i in range(peak_i, len(elevs) - 1))


def test_off_zenith_pass_peaks_at_requested_elevation():
    p = satellite_pass(samples=15, altitude_km=550, peak_elevation_deg=40,
                       horizon_elevation_deg=10)
    assert math.isclose(max(p.elevation_deg), 40.0, abs_tol=1e-6)
    # off-zenith closest approach is farther than the altitude
    mid = len(p.slant_range_km) // 2
    assert p.slant_range_km[mid] > 550.0


def test_leo_pass_duration_is_physical():
    p = satellite_pass(samples=3, altitude_km=550, peak_elevation_deg=90,
                       horizon_elevation_deg=0.01)
    duration_min = (p.time_s[-1] - p.time_s[0]) / 60.0
    assert 3.0 < duration_min < 20.0


def test_satellite_pass_rejects_invalid_configuration():
    with pytest.raises(ValueError):
        satellite_pass(samples=1)  # too few samples
    with pytest.raises(ValueError):
        satellite_pass(altitude_km=-1)
    with pytest.raises(ValueError):
        satellite_pass(peak_elevation_deg=95)  # > 90
    with pytest.raises(ValueError):
        satellite_pass(peak_elevation_deg=30, horizon_elevation_deg=30)  # horizon !< peak
