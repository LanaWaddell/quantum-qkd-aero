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


C_M_S = 299_792_458.0
"""Speed of light in vacuum, m/s (LINK-3, plan §2.2) -- the single named constant."""


def _require(name: str, value: float, *, lo: float, hi: float) -> None:
    """Shared construction-time domain check (plan §4 -- "not four ad-hoc rule sets").

    Raises ``ValueError`` naming ``name`` unless ``value`` is finite and lies
    in the closed interval ``[lo, hi]``.
    """

    if not math.isfinite(value) or not (lo <= value <= hi):
        raise ValueError(
            f"{name} must be finite and in [{lo}, {hi}]; got {value!r}."
        )


def _require_positive(name: str, value: float) -> None:
    """Construction-time strict-positivity check (LINK-3, plan §4).

    ``_require`` above is a closed-interval ``[lo, hi]`` check and so cannot
    express ``> 0``; this sibling helper covers the strict-positivity
    parameters LINK-3 introduces (``carrier_frequency_hz``,
    ``beam_divergence_urad``) with the same finite-and-named-failure shape.
    """

    if not math.isfinite(value) or not value > 0.0:
        raise ValueError(f"{name} must be finite and > 0; got {value!r}.")


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


# ---------------------------------------------------------------------------
# LINK-3 -- opt-in geometry-coupled deterministic effects (docs/LINK_3_PLAN.md
# §4). Neither effect is added to _production_link_effects (mission.py):
# Doppler remains bridge-rejected until LINK-6, and pointing bias remains an
# opt-in appended user effect until a production-stack membership PR argues
# its own parity case.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DopplerShiftEffect:
    """First-order line-of-sight kinematic Doppler shift (LINK-3, plan §2.2, §4).

    This effect computes the first-order line-of-sight kinematic Doppler
    shift produced by the circular-orbit, stationary-Earth geometry used by
    ``qkd.orbit``. It is not a complete frequency-transfer model. Excluded:
    Earth rotation/station motion, eccentric-orbit ephemerides, gravitational
    shift, hardware oscillator offsets, atmospheric propagation effects. The
    omitted longitudinal second-order relativistic term is ~100 kHz at
    optical carriers -- approximately five orders below the first-order
    shift and below the GHz-scale filter widths contemplated for the initial
    LINK-6 consumer. Scale anchor: 785 nm (f0 ~= 3.819e14 Hz), 6 km/s => ~=
    7.64 GHz.

    ``frequency_offset_hz = -(v_r / C_M_S) * carrier_frequency_hz``, where
    ``v_r`` is ``geom.radial_velocity_mps`` (positive = receding, negative =
    approaching -- ``qkd.orbit``'s sign convention). ``carrier_frequency_hz``
    is an explicit required parameter (finite, > 0); no hidden wavelength
    default.

    Not in the production stack (plan §1, §8): Doppler stays bridge-rejected
    by ``qkd.link.apply_link_state`` until LINK-6 wires
    ``frequency_offset_hz`` into an estimator-owned consumer. Usable today
    directly at the ``qkd.link.ChannelStack`` level for research use.
    """

    carrier_frequency_hz: float
    effect_id: str = field(default="doppler_shift", init=False)

    def __post_init__(self) -> None:
        _require_positive("carrier_frequency_hz", self.carrier_frequency_hz)

    def evaluate(
        self, t: float, geom: PassGeometry, *, context: EffectEvaluationContext
    ) -> LinkObservables:
        if geom.radial_velocity_mps is None:
            raise ValueError(
                "DopplerShiftEffect.evaluate: geom.radial_velocity_mps is "
                "None (geometry provider does not populate radial velocity); "
                "this effect requires a radial-velocity-populated geometry "
                "provider (LINK-3 SatellitePass.radial_velocity_km_s)."
            )
        frequency_offset_hz = -(geom.radial_velocity_mps / C_M_S) * self.carrier_frequency_hz
        return LinkObservables(
            channel=ChannelObservables(frequency_offset_hz=frequency_offset_hz)
        )


@dataclass(frozen=True)
class PointingLossEffect:
    """Receiver-centre / small-aperture pointing-bias attenuation (LINK-3, plan §2.3, §4).

    ``PointingLossEffect`` models the attenuation of Gaussian irradiance at
    the receiver centre under a fixed angular boresight offset. Used
    multiplicatively with the centred finite-aperture ``GeometricLossEffect``,
    it is a small-aperture approximation, valid when the receiver aperture is
    small relative to the beam spot. Exact displaced-beam aperture
    integration and stochastic beam wander are deferred.

    The centre-irradiance ratio computed here is range-independent under the
    constant-angle far-field approximation -- it is *not* an exact
    factorization of the displaced-Gaussian finite-aperture capture, which
    depends jointly on aperture, beam radius, and displacement and retains
    range dependence through a/w (cf. Safi et al., arXiv:2005.11786).

    ``transmittance_factor = exp(-2 * (boresight_offset_urad /
    beam_divergence_urad) ** 2)``. Output domain is ``[0, 1]``, not
    ``(0, 1]``: large finite offset/divergence ratios may underflow to
    exactly ``0.0``.

    ``beam_divergence_urad`` is independent of ``GeometricLossEffect``'s
    divergence parameter (caller keeps them physically consistent; no hidden
    coupling -- LINK-2 explicit-construction pattern).

    Not in the production stack (plan §1, §8); usable today as an appended
    user effect via ``simulate_pass(link_effects=...)``.
    """

    boresight_offset_urad: float
    beam_divergence_urad: float
    effect_id: str = field(default="pointing_loss", init=False)

    def __post_init__(self) -> None:
        _require("boresight_offset_urad", self.boresight_offset_urad, lo=0.0, hi=math.inf)
        _require_positive("beam_divergence_urad", self.beam_divergence_urad)

    def evaluate(
        self, t: float, geom: PassGeometry, *, context: EffectEvaluationContext
    ) -> LinkObservables:
        ratio = self.boresight_offset_urad / self.beam_divergence_urad
        transmittance_factor = math.exp(-2.0 * ratio**2)
        return LinkObservables(
            channel=ChannelObservables(transmittance_factor=transmittance_factor)
        )
