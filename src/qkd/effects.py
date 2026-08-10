"""LINK-2: production link-effect library (fixed-ID migration of existing constants).

Implements ADR-0003 (RATIFIED 2026-07-17), LINK queue §8, per
``docs/LINK_2_PLAN.md`` (v2, approved 2026-08-10) §4. This module migrates
the four existing satellite system/atmospheric/geometric/detector-efficiency
factors into fixed-ID :class:`qkd.link.ChannelEffect` implementations,
evaluated in a parity-pinned order through the LINK-1 bridge
(``qkd.link.apply_link_state``). It adds no new physics: the atmospheric and
geometric effects call the existing, independently verified
``qkd.channel.atmospheric_transmittance`` / ``qkd.channel.geometric_transmittance``
functions with identical arguments -- same code, same bits, same raises for
their own argument validation -- rather than reimplementing the formulas.

Declared accepted input domain (plan §2.1, R1 -- bounded input-domain
hardening disposition). The pre-LINK-2 inline path validated nothing at the
factor level (only the aggregate transmittance was clamped); the migrated
effects validate each factor **at construction**, via one shared private
helper, :func:`_require`:

=====================  =========================
Parameter               Accepted domain
=====================  =========================
``system_efficiency``    finite, in [0, 1]
``detection_efficiency`` finite, in [0, 1]
``zenith_optical_depth`` finite, >= 0
``beam_divergence_urad`` finite, >= 0
``rx_aperture_m``        finite, >= 0
=====================  =========================

This is a declared, tested **behaviour change**: configurations outside this
domain -- previously accepted silently by the inline path -- now fail loudly
at effect construction, never falling back to the inline path (stack
ownership must not be configuration-dependent).

Failure timing (plan §4, binding, R4): invalid *numeric parameters* fail at
**construction** (``__post_init__``, below). Missing *geometry*
(``elevation_deg is None`` / ``slant_range_km is None``, from a non-satellite
geometry provider) fails at **evaluation**, with an error naming the effect
and the missing field -- these two effects are satellite-medium members, but
the :class:`~qkd.link.PassGeometry` contract stays medium-neutral. All four
effects ignore ``context`` -- no controls, no RNG ("a constant is a function
that ignores t").
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from qkd.channel import atmospheric_transmittance, geometric_transmittance
from qkd.link import (
    ChannelObservables,
    DetectorObservables,
    EffectEvaluationContext,
    LinkObservables,
    PassGeometry,
)


def _require(name: str, value: float, *, lo: float, hi: float) -> None:
    """Shared construction-time domain check (plan §4 -- "not four ad-hoc rule sets").

    Raises ``ValueError`` naming ``name`` unless ``value`` is finite and lies
    in the closed interval ``[lo, hi]``.
    """

    if not math.isfinite(value) or not (lo <= value <= hi):
        raise ValueError(
            f"{name} must be finite and in [{lo}, {hi}]; got {value!r}."
        )


@dataclass(frozen=True)
class SystemEfficiencyEffect:
    """Migrates the constant ``cfg["system_efficiency"]`` factor (plan §1, §4).

    Transmit/optics/coupling efficiency up to the detector face (see
    ``qkd.channel.DEFAULT_ATMOSPHERE``'s comment); detector quantum
    efficiency is a separate effect, :class:`DetectorQuantumEfficiencyEffect`.
    """

    system_efficiency: float
    effect_id: str = field(default="system_efficiency", init=False)

    def __post_init__(self) -> None:
        _require("system_efficiency", self.system_efficiency, lo=0.0, hi=1.0)

    def evaluate(
        self, t: float, geom: PassGeometry, *, context: EffectEvaluationContext
    ) -> LinkObservables:
        return LinkObservables(
            channel=ChannelObservables(transmittance_factor=self.system_efficiency)
        )


@dataclass(frozen=True)
class AtmosphericAbsorptionEffect:
    """Migrates ``atmospheric_transmittance(elevation_deg, zenith_optical_depth)`` (plan §1, §4).

    Calls the existing verified ``qkd.channel.atmospheric_transmittance``
    with ``geom.elevation_deg`` -- no formula reimplementation (plan §2.2).
    """

    zenith_optical_depth: float
    effect_id: str = field(default="atmospheric_absorption", init=False)

    def __post_init__(self) -> None:
        _require(
            "zenith_optical_depth", self.zenith_optical_depth, lo=0.0, hi=math.inf
        )

    def evaluate(
        self, t: float, geom: PassGeometry, *, context: EffectEvaluationContext
    ) -> LinkObservables:
        if geom.elevation_deg is None:
            raise ValueError(
                "AtmosphericAbsorptionEffect.evaluate: geom.elevation_deg is "
                "None (non-satellite geometry provider); this effect requires "
                "satellite-medium geometry."
            )
        factor = atmospheric_transmittance(geom.elevation_deg, self.zenith_optical_depth)
        return LinkObservables(channel=ChannelObservables(transmittance_factor=factor))


@dataclass(frozen=True)
class GeometricLossEffect:
    """Migrates ``geometric_transmittance(slant_range_km, divergence, aperture)`` (plan §1, §4).

    Calls the existing verified ``qkd.channel.geometric_transmittance`` with
    ``geom.slant_range_km`` -- no formula reimplementation (plan §2.2).
    """

    beam_divergence_urad: float
    rx_aperture_m: float
    effect_id: str = field(default="geometric_loss", init=False)

    def __post_init__(self) -> None:
        _require(
            "beam_divergence_urad", self.beam_divergence_urad, lo=0.0, hi=math.inf
        )
        _require("rx_aperture_m", self.rx_aperture_m, lo=0.0, hi=math.inf)

    def evaluate(
        self, t: float, geom: PassGeometry, *, context: EffectEvaluationContext
    ) -> LinkObservables:
        if geom.slant_range_km is None:
            raise ValueError(
                "GeometricLossEffect.evaluate: geom.slant_range_km is None "
                "(non-satellite geometry provider); this effect requires "
                "satellite-medium geometry."
            )
        factor = geometric_transmittance(
            geom.slant_range_km, self.beam_divergence_urad, self.rx_aperture_m
        )
        return LinkObservables(channel=ChannelObservables(transmittance_factor=factor))


@dataclass(frozen=True)
class DetectorQuantumEfficiencyEffect:
    """Migrates the constant ``DetectorParams.detection_efficiency`` factor (plan §1, §4).

    Detector quantum efficiency only (plan §1, R3): dark counts are not
    migrated in LINK-2 -- ``DetectorParams.dark_count_prob`` remains the
    authoritative detector-window probability, and converting LINK-1's
    ``dark_count_rate_hz`` representation requires a defined gate/coincidence
    window, deferred to LINK-6.
    """

    detection_efficiency: float
    effect_id: str = field(default="detector_qe", init=False)

    def __post_init__(self) -> None:
        _require(
            "detection_efficiency", self.detection_efficiency, lo=0.0, hi=1.0
        )

    def evaluate(
        self, t: float, geom: PassGeometry, *, context: EffectEvaluationContext
    ) -> LinkObservables:
        return LinkObservables(
            detector=DetectorObservables(efficiency_factor=self.detection_efficiency)
        )
