"""Satellite-pass geometry from real orbital mechanics (Phase 2B-3, hardened).

Replaces the earlier smooth-interpolation stand-in with derived geometry: a
circular orbit and a great-circle ground track. Elevation and slant range are
PHYSICALLY COUPLED through the orbit (not independently interpolated) -- at peak
elevation the slant range is exactly determined by the geometry, and the whole
pass shape follows from the orbit altitude and peak elevation.

Geometry (circular orbit, great-circle ground track, Earth rotation neglected)
------------------------------------------------------------------------------
Earth radius R_E, orbit radius r = R_E + altitude. With geocentric angle gamma
between ground station and satellite:

    slant range:  d(gamma) = sqrt(R_E^2 + r^2 - 2 R_E r cos gamma)
    elevation:    E(gamma) = atan2(cos gamma - R_E/r, sin gamma)

For a pass of peak elevation E_max, the closest-approach geocentric angle is

    gamma_min = arccos((R_E/r) cos E_max) - E_max          (= 0 for a zenith pass)

and along a great-circle track parameterised by along-track angle psi = omega*t:

    cos gamma(psi) = cos(gamma_min) cos(psi)

Orbital angular rate omega = sqrt(mu / r^3), mu = G*M_earth. The pass is sampled
over the psi range for which elevation exceeds the horizon mask.

Scope/honesty: circular orbit, great-circle track, Earth rotation neglected -- the
standard simplifications -- but elevation and slant range are GENUINELY derived
and genuinely coupled, unlike the previous interpolated profile. Slant range at a
zenith pass equals the orbit altitude because the geometry demands it (a check the
tests assert).

API: returns a columnar SatellitePass (time_s / elevation_deg / slant_range_km /
radial_velocity_km_s) for compatibility with run.py and the coherence pass loop.

Radial velocity (LINK-3, ``docs/LINK_3_PLAN.md`` §2.1)
--------------------------------------------------------
With cos(gamma) = cos(gamma_min) cos(psi), psi = omega*t, the range-rate is the
exact derivative of the declared model above:

    d(gamma(psi))/dt = R_E * r * omega * cos(gamma_min) * sin(psi) / d(gamma(psi))

This is the exact derivative of the declared circular-orbit, stationary-Earth
model -- not an exact real-orbit radial velocity. Earth rotation, station
motion, non-circular ephemerides, and relativistic frequency contributions are
excluded, consistent with the geometry model above. Sign convention: positive
is receding, negative is approaching.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

EARTH_RADIUS_KM: float = 6371.0
EARTH_MU_KM3_S2: float = 398_600.4418  # G * M_earth


@dataclass(frozen=True)
class SatellitePass:
    """Sampled pass geometry over a single visible satellite pass."""

    time_s: list[float]
    elevation_deg: list[float]
    slant_range_km: list[float]
    radial_velocity_km_s: list[float] | None = None


def _elevation_from_gamma(gamma_rad: float, r_km: float) -> float:
    k = EARTH_RADIUS_KM / r_km
    return math.degrees(math.atan2(math.cos(gamma_rad) - k, math.sin(gamma_rad)))


def _slant_range_from_gamma(gamma_rad: float, r_km: float) -> float:
    return math.sqrt(
        EARTH_RADIUS_KM**2 + r_km**2 - 2.0 * EARTH_RADIUS_KM * r_km * math.cos(gamma_rad)
    )


def _gamma_for_elevation(elevation_deg: float, r_km: float) -> float:
    """Inverse: geocentric angle at which the satellite sits at this elevation."""
    k = EARTH_RADIUS_KM / r_km
    e = math.radians(elevation_deg)
    return math.acos(k * math.cos(e)) - e


def _radial_velocity_km_s(psi: float, d_km: float, r_km: float, gamma_min: float) -> float:
    """Exact derivative of the declared slant-range model (LINK-3, plan §2.1).

    ``d(d)/dt = R_E * r_km * omega * cos(gamma_min) * sin(psi) / d_km``, where
    ``omega = sqrt(EARTH_MU_KM3_S2 / r_km**3)`` is the orbital angular rate for
    the circular orbit of radius ``r_km``. The ``sin(gamma)`` factor common to
    both ``d(gamma)`` and ``gamma_dot`` cancels analytically, which is what
    avoids the removable singularity a separate ``gamma_dot`` computation
    would hit at zenith closest approach (``sin(gamma) == 0``).

    Private, internal helper: ``psi``/``d_km``/``r_km``/``gamma_min`` are
    always supplied by :func:`satellite_pass` from its own already-validated
    geometry (``d_km`` is the positive slant range implied by ``psi`` and
    ``gamma_min`` via :func:`_slant_range_from_gamma`, which is strictly
    positive because ``r_km != EARTH_RADIUS_KM`` for any physical altitude).
    No redundant validation is performed here for that reason; this function
    documents its valid-domain assumptions rather than re-checking inputs
    ``satellite_pass`` already guarantees.

    Sign convention (binding): positive = receding, negative = approaching.
    """
    omega = math.sqrt(EARTH_MU_KM3_S2 / r_km**3)  # rad/s
    return EARTH_RADIUS_KM * r_km * omega * math.cos(gamma_min) * math.sin(psi) / d_km


def satellite_pass(
    *,
    samples: int = 1000,
    altitude_km: float = 550.0,
    peak_elevation_deg: float = 90.0,
    horizon_elevation_deg: float = 10.0,
) -> SatellitePass:
    """Return a derived-geometry LEO pass profile (columnar SatellitePass).

    Parameters
    ----------
    samples : number of time samples across the visible pass (>= 2; odd includes peak).
    altitude_km : circular-orbit altitude above Earth's surface.
    peak_elevation_deg : peak elevation of the pass (90 = directly overhead).
    horizon_elevation_deg : minimum usable elevation; pass sampled where E >= this.
    """
    if samples < 2:
        raise ValueError("samples must be at least 2")
    if altitude_km <= 0.0:
        raise ValueError("altitude_km must be positive")
    if not 0.0 < horizon_elevation_deg < peak_elevation_deg <= 90.0:
        raise ValueError(
            "elevation bounds must satisfy 0 < horizon < peak <= 90"
        )

    r = EARTH_RADIUS_KM + altitude_km
    omega = math.sqrt(EARTH_MU_KM3_S2 / r**3)  # rad/s

    gamma_min = _gamma_for_elevation(peak_elevation_deg, r)     # closest approach
    gamma_mask = _gamma_for_elevation(horizon_elevation_deg, r)  # at horizon mask

    # along-track angle where elevation == horizon mask:
    # cos(gamma_mask) = cos(gamma_min) cos(psi_mask)
    ratio = math.cos(gamma_mask) / math.cos(gamma_min)
    ratio = max(-1.0, min(1.0, ratio))
    psi_mask = math.acos(ratio)

    time_s: list[float] = []
    elevation_deg: list[float] = []
    slant_range_km: list[float] = []
    radial_velocity_km_s: list[float] = []

    for index in range(samples):
        frac = index / (samples - 1)             # 0..1
        psi = -psi_mask + frac * (2.0 * psi_mask)
        cos_gamma = math.cos(gamma_min) * math.cos(psi)
        cos_gamma = max(-1.0, min(1.0, cos_gamma))
        gamma = math.acos(cos_gamma)

        time_s.append(psi / omega)               # 0 at peak; symmetric +/-
        elevation_deg.append(_elevation_from_gamma(gamma, r))
        slant_range_km.append(_slant_range_from_gamma(gamma, r))
        radial_velocity_km_s.append(
            _radial_velocity_km_s(psi, slant_range_km[-1], r, gamma_min)
        )

    return SatellitePass(
        time_s=time_s,
        elevation_deg=elevation_deg,
        slant_range_km=slant_range_km,
        radial_velocity_km_s=radial_velocity_km_s,
    )
