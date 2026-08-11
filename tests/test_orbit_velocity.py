"""Tests for LINK-3 radial velocity (docs/LINK_3_PLAN.md §6, tests 1-6; `orbit.py`).

Test 7 (the ``TableGeometryProvider`` fourth-column contract) lives in
``tests/test_link3_effects.py`` alongside the other LINK-3 seam/effect tests,
per the plan's "Provider (enumerated separately)" note.
"""
from __future__ import annotations

import math

import pytest

from qkd.orbit import EARTH_MU_KM3_S2, EARTH_RADIUS_KM, SatellitePass, satellite_pass


# ---------------------------------------------------------------------------
# 1. Odd-sampled pass: modeled radial velocity exactly 0 at closest approach
# ---------------------------------------------------------------------------


def test_radial_velocity_exactly_zero_at_closest_approach_odd_samples():
    # Off-zenith on purpose: closest approach is exact zero regardless of
    # gamma_min because sin(psi) == 0 at the (odd-count) midpoint sample.
    p = satellite_pass(samples=21, altitude_km=550.0, peak_elevation_deg=60.0,
                       horizon_elevation_deg=10.0)
    mid = len(p.radial_velocity_km_s) // 2
    assert p.time_s[mid] == 0.0
    assert p.radial_velocity_km_s[mid] == 0.0


# ---------------------------------------------------------------------------
# 2. Antisymmetry: v(-t) == -v(t) within a tight absolute tolerance
# ---------------------------------------------------------------------------


def test_radial_velocity_antisymmetric_about_closest_approach():
    p = satellite_pass(samples=25, altitude_km=550.0, peak_elevation_deg=45.0,
                       horizon_elevation_deg=10.0)
    n = len(p.radial_velocity_km_s)
    for i in range(n):
        j = n - 1 - i
        assert math.isclose(p.time_s[i], -p.time_s[j], abs_tol=1e-9)
        assert math.isclose(
            p.radial_velocity_km_s[i], -p.radial_velocity_km_s[j], abs_tol=1e-9
        )


# ---------------------------------------------------------------------------
# 3. Sign convention: < 0 approaching (first half), > 0 receding (second half)
# ---------------------------------------------------------------------------


def test_radial_velocity_sign_convention_approach_then_recede():
    p = satellite_pass(samples=41, altitude_km=550.0, peak_elevation_deg=75.0,
                       horizon_elevation_deg=10.0)
    mid = len(p.radial_velocity_km_s) // 2
    for v in p.radial_velocity_km_s[:mid]:
        assert v < 0.0
    assert p.radial_velocity_km_s[mid] == 0.0
    for v in p.radial_velocity_km_s[mid + 1:]:
        assert v > 0.0


# ---------------------------------------------------------------------------
# 4. Analytic helper vs independent central difference, interior samples,
#    two-step-size convergence check
# ---------------------------------------------------------------------------


def _central_difference_error_at_interior_sample(samples: int) -> tuple[float, float]:
    """Central difference of slant_range_km vs the analytic column, one interior sample.

    Returns ``(step_h, abs_error)``. The interior index (samples // 3) is well
    away from both endpoints for every ``samples`` value used here.
    """
    p = satellite_pass(samples=samples, altitude_km=550.0, peak_elevation_deg=60.0,
                       horizon_elevation_deg=10.0)
    i = samples // 3
    assert 0 < i < samples - 1  # genuinely interior
    dt = p.time_s[i + 1] - p.time_s[i - 1]
    central_diff = (p.slant_range_km[i + 1] - p.slant_range_km[i - 1]) / dt
    analytic = p.radial_velocity_km_s[i]
    step_h = p.time_s[i + 1] - p.time_s[i]
    return step_h, abs(central_diff - analytic)


def test_analytic_radial_velocity_matches_central_difference_with_convergence():
    # Central-difference truncation error is O(h**2); a generous coefficient
    # (empirically ~1e-4 for this geometry) keeps the per-step-size bound
    # concrete without being a bitwise/exact-order claim (plan §6 test 4).
    coarse_h, coarse_error = _central_difference_error_at_interior_sample(501)
    fine_h, fine_error = _central_difference_error_at_interior_sample(1001)

    tolerance_coefficient = 1.0e-3
    assert coarse_error < tolerance_coefficient * coarse_h**2
    assert fine_error < tolerance_coefficient * fine_h**2

    # Two-step-size convergence: halving h should shrink the error by
    # roughly 4x (quadratic); require at least 3x to leave float/geometry
    # slack while still being a genuine convergence assertion.
    assert fine_h == pytest.approx(coarse_h / 2.0, rel=1e-6)
    assert fine_error < coarse_error / 3.0


# ---------------------------------------------------------------------------
# 5. Default-geometry max |v| in a justified km/s band; max at horizon edges
# ---------------------------------------------------------------------------


def test_default_geometry_max_radial_velocity_is_physically_bounded_at_horizon():
    p = satellite_pass()  # default altitude/elevation/horizon geometry

    r_km = EARTH_RADIUS_KM + 550.0
    orbital_speed_km_s = math.sqrt(EARTH_MU_KM3_S2 / r_km)  # omega * r, upper bound

    abs_values = [abs(v) for v in p.radial_velocity_km_s]
    max_abs = max(abs_values)
    max_index = abs_values.index(max_abs)

    # justified band: strictly positive (a real LEO pass has nonzero range
    # rate away from closest approach), strictly below the full orbital
    # speed (radial velocity is a projection of the orbital velocity vector,
    # never the whole vector for a horizon-limited pass).
    assert 5.0 < max_abs < orbital_speed_km_s

    # maximum occurs at the horizon-mask edges (both ends, by antisymmetry).
    assert max_index in (0, len(p.radial_velocity_km_s) - 1)
    assert math.isclose(
        abs(p.radial_velocity_km_s[0]), abs(p.radial_velocity_km_s[-1]), rel_tol=1e-12
    )
    assert math.isclose(abs(p.radial_velocity_km_s[0]), max_abs, rel_tol=1e-12)


# ---------------------------------------------------------------------------
# 6. Legacy three-column construction => radial_velocity_km_s is None
# ---------------------------------------------------------------------------


def test_legacy_three_column_construction_leaves_radial_velocity_none():
    p = SatellitePass(
        time_s=[0.0, 1.0, 2.0],
        elevation_deg=[10.0, 20.0, 10.0],
        slant_range_km=[900.0, 800.0, 900.0],
    )
    assert p.radial_velocity_km_s is None
