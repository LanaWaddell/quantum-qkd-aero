"""Simple satellite-pass geometry for Phase 2B integration."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class SatellitePass:
    """Sampled pass geometry over a single visible satellite pass."""

    time_s: list[float]
    elevation_deg: list[float]
    slant_range_km: list[float]


def satellite_pass(
    *,
    samples: int = 1000,
    duration_s: float = 600.0,
    horizon_elevation_deg: float = 5.0,
    peak_elevation_deg: float = 82.0,
    horizon_slant_range_km: float = 1800.0,
    closest_slant_range_km: float = 275.0,
) -> SatellitePass:
    """Return a smooth, symmetric LEO pass profile for simulator integration."""

    if samples < 2:
        raise ValueError("samples must be at least 2")
    if duration_s <= 0.0:
        raise ValueError("duration_s must be positive")
    if not 0.0 < horizon_elevation_deg < peak_elevation_deg <= 90.0:
        raise ValueError("elevation bounds must satisfy 0 < horizon < peak <= 90")
    if not 0.0 < closest_slant_range_km < horizon_slant_range_km:
        raise ValueError("range bounds must satisfy 0 < closest < horizon")

    time_s = []
    elevation_deg = []
    slant_range_km = []

    for index in range(samples):
        phase = index / (samples - 1)
        visibility = 0.0 if index in (0, samples - 1) else math.sin(math.pi * phase)

        time_s.append(duration_s * phase)
        elevation_deg.append(
            horizon_elevation_deg
            + (peak_elevation_deg - horizon_elevation_deg) * visibility
        )
        slant_range_km.append(
            closest_slant_range_km
            + (horizon_slant_range_km - closest_slant_range_km) * (1.0 - visibility)
        )

    return SatellitePass(
        time_s=time_s,
        elevation_deg=elevation_deg,
        slant_range_km=slant_range_km,
    )
