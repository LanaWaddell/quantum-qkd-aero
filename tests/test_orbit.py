import pytest

from qkd.orbit import satellite_pass


def test_satellite_pass_returns_requested_sample_count():
    pass_profile = satellite_pass(samples=11, duration_s=100.0)

    assert len(pass_profile.time_s) == 11
    assert len(pass_profile.elevation_deg) == 11
    assert len(pass_profile.slant_range_km) == 11
    assert pass_profile.time_s[0] == 0.0
    assert pass_profile.time_s[-1] == 100.0


def test_satellite_pass_has_strongest_geometry_near_midpass():
    pass_profile = satellite_pass(samples=101)
    mid_index = len(pass_profile.time_s) // 2

    assert pass_profile.elevation_deg[mid_index] == max(pass_profile.elevation_deg)
    assert pass_profile.slant_range_km[mid_index] == min(pass_profile.slant_range_km)
    assert pass_profile.elevation_deg[0] == pass_profile.elevation_deg[-1]
    assert pass_profile.slant_range_km[0] == pass_profile.slant_range_km[-1]


def test_satellite_pass_rejects_invalid_configuration():
    with pytest.raises(ValueError):
        satellite_pass(samples=1)

    with pytest.raises(ValueError):
        satellite_pass(duration_s=0.0)

    with pytest.raises(ValueError):
        satellite_pass(horizon_elevation_deg=10.0, peak_elevation_deg=10.0)

    with pytest.raises(ValueError):
        satellite_pass(closest_slant_range_km=2000.0, horizon_slant_range_km=1000.0)
