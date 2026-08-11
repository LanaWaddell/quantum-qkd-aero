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


def _require_half_open_unit(name: str, value: float, *, hi: float) -> None:
    """Construction-time ``(0, hi]`` domain check (LINK-4, plan §2.1).

    Neither ``_require`` (closed ``[lo, hi]``) nor ``_require_positive``
    (strict ``> 0``, unbounded above) can express the strict-lower/closed-
    upper ``(0, hi]`` shape ``aperture_averaging`` needs; this third sibling
    helper keeps the same shared-helper discipline ("not four ad-hoc rule
    sets") rather than inlining a bespoke check.
    """

    if not math.isfinite(value) or not (0.0 < value <= hi):
        raise ValueError(f"{name} must be finite and in (0, {hi}]; got {value!r}.")


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


# ---------------------------------------------------------------------------
# LINK-4 -- seeded stochastic exogenous effects (docs/LINK_4_PLAN.md, v2
# approved). Neither effect joins the production stack (plan §2.2). Both are
# i.i.d.-per-sample-index effects: see the binding model declaration on
# ``ScintillationFadingEffect`` below (plan §1). Fixed canonical IDs:
# ``scintillation_fading``, ``pointing_jitter`` (plan §2.2).
# ---------------------------------------------------------------------------


RYTOV_WEAK_GUARD = 1.0
"""Reference guard on the elevation-coupled Rytov variance sigma_R^2 (plan §2.1).

A model-validity policy, not a physical discontinuity: the declared v1
log-normal law is restricted to the weak-scintillation regime it was derived
for. ``ScintillationFadingEffect`` raises when ``sigma_R^2(E)`` exceeds this
guard unless the caller explicitly opts in via ``allow_out_of_regime=True``.
There is no numeric threshold *parameter* -- changing a number must not
silently redefine what "weak" means.
"""


@dataclass(frozen=True)
class LogNormalLaw:
    """The one-time stationary log-normal law of a relative fading factor (plan §5).

    ``mu_log`` is the mean of the log-factor; ``sigma_log`` is its
    **standard deviation** (not variance) -- stated explicitly because it is
    passed directly as ``scale`` to ``numpy.random.Generator.normal``, which
    takes a standard deviation, not a variance.
    """

    mu_log: float
    sigma_log: float


@dataclass(frozen=True)
class ScintillationFadingEffect:
    """Stationary-marginal weak-turbulence log-normal scintillation fading (LINK-4, plan §1, §2.1).

    **Binding model declaration (plan §1, R1 -- verbatim):** "``ScintillationFadingEffect``
    samples the stationary one-time marginal of the declared weak-turbulence
    log-normal model. Samples at different ``sample_index`` values are
    **independent by model definition**. For the current default mission
    grid (Δt ≈ 0.477 s) and the dynamics-spec reference τ_c = 3 ms, the
    omitted OU correlation is ρ = e^(−Δt/τ_c) ≈ 9×10⁻⁷⁰ and is negligible at
    simulator precision. This effect does not represent an OU path or
    preserve temporal correlation. A caller requiring correlation, or using
    a cadence not demonstrably separated from the relevant coherence time,
    must use the Exp-1 path generator."

    The effect is an **i.i.d. stationary-marginal effect** -- never "the
    exact finite-Δt OU joint law" (the marginal is exact under the declared
    model; the independence is a declared, quantified-negligible
    approximation of the joint law).

    Per sample, elevation-coupled (channel-dynamics spec, Generator B), with
    log-irradiance (not log-amplitude) variance (plan §2.1, R3.1)::

        sigma_R^2(E)  = rytov_variance_zenith * (sin E)^(-11/6)
        log_variance  = ln(1 + aperture_averaging * sigma_R^2(E))
        sigma_log     = sqrt(log_variance)          [standard deviation of log-factor]
        mu_log        = -log_variance / 2           [pure-fading normalization: E[factor] = 1]
        X             = rng.normal(loc=mu_log, scale=sigma_log)
        transmittance_factor = exp(X)               [E = 1; values > 1 by construction]

    A single private parameter resolver, :meth:`_law_parameters`, is the one
    code path used by both :meth:`evaluate` and :meth:`stationary_law`
    (plan §2.1, R6) -- elevation validation, the Rytov policy below, and the
    two law parameters cannot drift between sampling and declaration.

    **Elevation validation (plan §2.1, R4):** ``geom.elevation_deg`` must be
    non-None, finite, and in ``(0, 90]``; zero/negative/NaN/above-zenith
    raise naming the effect and the constraint, through both entry points.

    **Weak-regime policy (plan §2.1, R4):** ``RYTOV_WEAK_GUARD`` (module
    level, above) is a fixed reference guard, not a physical discontinuity.
    When ``sigma_R^2(E)`` exceeds the guard: by default this raises, naming
    the model, the elevation, the computed ``sigma_R^2``, and the guard;
    with ``allow_out_of_regime=True`` it continues with the same log-normal
    approximation, documented as an explicit out-of-regime approximation,
    not a validated strong-turbulence model. **Binding regime statement
    (plan §2.1, verbatim):** "The v1 log-normal law is restricted to the
    declared weak-scintillation regime. Moderate or strong scintillation
    requires a separately selected and validated model; gamma-gamma is the
    planned v2 candidate." Concrete trap this guards: ``rytov_variance_zenith
    = 0.1`` at a 10-degree horizon gives ``sigma_R^2 ~= 2.5`` -- the defaults
    leave the regime near the horizon; at a 25-degree mask, ``sigma_R^2 ~=
    0.49`` is comfortably inside.

    Domains (construction-time, via :func:`_require` /
    :func:`_require_half_open_unit`): ``rytov_variance_zenith`` finite >= 0;
    ``aperture_averaging`` finite in ``(0, 1]``.

    **Indexing contract (plan §3, binding):** :meth:`evaluate` requires an
    explicit ``context.sample_index``; if ``None``, it raises naming
    ``sample_index`` *before* drawing (with ``index=None``, the LINK-1
    runtime would resolve the same purpose stream every call and silently
    repeat one draw across all geometries -- the failure this rule
    prevents). :meth:`evaluate` calls ``context.rng_for("fade")`` with no
    index argument, letting the stack-owned context supply the
    already-validated index.

    ``unit_mean_fading_fields`` (plan §4, R5) declares ``transmittance_factor``
    as a unit-mean fading field: at :class:`~qkd.link.ChannelStack`
    construction this relaxes that field's validation, for this effect only,
    from ``[0, 1]`` to finite and ``>= 0`` (the factor is > 1 by
    construction). The declaration is a semantic statement, not proof -- the
    unit-mean claim itself is validated by this class's own analytic/
    statistical tests.
    """

    rytov_variance_zenith: float
    aperture_averaging: float
    allow_out_of_regime: bool = False
    effect_id: str = field(default="scintillation_fading", init=False)
    unit_mean_fading_fields: frozenset[str] = field(
        default=frozenset({"transmittance_factor"}), init=False
    )

    def __post_init__(self) -> None:
        _require(
            "rytov_variance_zenith", self.rytov_variance_zenith, lo=0.0, hi=math.inf
        )
        _require_half_open_unit("aperture_averaging", self.aperture_averaging, hi=1.0)

    def _law_parameters(self, geom: PassGeometry) -> tuple[float, float]:
        """Shared resolver for :meth:`evaluate` and :meth:`stationary_law` (plan §2.1, R6).

        Validates ``geom.elevation_deg`` and the Rytov weak-regime policy,
        then returns ``(mu_log, sigma_log)``.
        """

        elevation_deg = geom.elevation_deg
        if (
            elevation_deg is None
            or not math.isfinite(elevation_deg)
            or not (0.0 < elevation_deg <= 90.0)
        ):
            raise ValueError(
                "ScintillationFadingEffect requires geom.elevation_deg to be "
                f"non-None, finite, and in (0, 90]; got {elevation_deg!r}."
            )

        sigma_r_sq = self.rytov_variance_zenith * math.sin(
            math.radians(elevation_deg)
        ) ** (-11.0 / 6.0)

        if sigma_r_sq > RYTOV_WEAK_GUARD and not self.allow_out_of_regime:
            raise ValueError(
                "ScintillationFadingEffect: the declared weak-turbulence "
                f"log-normal model is invalid at elevation_deg={elevation_deg!r} "
                f"-- computed Rytov variance sigma_R^2={sigma_r_sq!r} exceeds "
                f"the weak-regime guard RYTOV_WEAK_GUARD={RYTOV_WEAK_GUARD!r}. "
                "Pass allow_out_of_regime=True to proceed as an explicit "
                "out-of-regime approximation, not a validated strong-"
                "turbulence model."
            )

        log_variance = math.log1p(self.aperture_averaging * sigma_r_sq)
        sigma_log = math.sqrt(log_variance)
        mu_log = -log_variance / 2.0
        return mu_log, sigma_log

    def evaluate(
        self, t: float, geom: PassGeometry, *, context: EffectEvaluationContext
    ) -> LinkObservables:
        if context.sample_index is None:
            raise ValueError(
                "ScintillationFadingEffect.evaluate: context.sample_index is "
                "None; this effect requires an explicit sample_index (LINK-4 "
                "indexing contract, plan §3) -- without it, the runtime "
                "would resolve the same RNG stream every call and silently "
                "repeat one draw across all geometries."
            )
        mu_log, sigma_log = self._law_parameters(geom)
        rng = context.rng_for("fade")
        x = rng.normal(loc=mu_log, scale=sigma_log)
        transmittance_factor = math.exp(x)
        return LinkObservables(
            channel=ChannelObservables(transmittance_factor=transmittance_factor)
        )

    def stationary_law(self, geom: PassGeometry) -> LogNormalLaw:
        """The one-time log-normal law of the *relative* scintillation factor (plan §5, R6).

        **Binding scope language (plan §5, verbatim):** "``stationary_law(geom)``
        exposes the one-time log-normal law of the *relative* scintillation
        factor. Exp-1/LINK-6 may combine or scale this law with the
        deterministic channel state and any other stochastic layers to
        construct the block-level total-transmittance PDT before estimator
        nonlinearities." It is not the distribution of total channel
        transmittance. Shares :meth:`_law_parameters` with :meth:`evaluate`.
        """

        mu_log, sigma_log = self._law_parameters(geom)
        return LogNormalLaw(mu_log=mu_log, sigma_log=sigma_log)


@dataclass(frozen=True)
class PointingJitterEffect:
    """I.i.d. per-index isotropic Gaussian pointing-jitter attenuation (LINK-4, plan §1, §2.2).

    The jitter effect is an **i.i.d. per-index component-jitter model by
    definition** (plan §1, R2) -- no decorrelation-rate claim is made for
    platform jitter; temporally correlated jitter requires a measured/
    declared spectrum and is deferred to the fine-timescale generator.

    ::

        theta_x, theta_y ~ N(0, sigma_j^2), sigma_j = jitter_sigma_urad
            (two draws, fixed order, one stream)
        transmittance_factor = exp(-2 * (theta_x^2 + theta_y^2) / beam_divergence_urad^2)

    Output domain is **[0, 1]** -- large finite ``jitter_sigma_urad`` /
    ``beam_divergence_urad`` ratios underflow to exactly ``0.0`` (plan
    §2.2, R3.2), matching LINK-3's corrected pointing contract. Analytic
    mean: ``E[factor] = 1 / (1 + 4 * sigma_j^2 / theta_div^2)``. Same
    receiver-centre/small-aperture approximation language as LINK-3,
    binding.

    **Bias + jitter (plan §2.2, R3.3 -- verbatim):** "Exact joint treatment
    of deterministic bias and isotropic Gaussian jitter gives a
    Rician/noncentral-χ² radial model; Beckmann is the broader anisotropic
    extension. Both the cross term and finite-aperture overlap are
    deferred." Multiplying LINK-3's deterministic bias factor
    (:class:`PointingLossEffect`) with this jitter factor is approximate and
    documented as such.

    Domains: ``jitter_sigma_urad`` finite >= 0; ``beam_divergence_urad``
    finite > 0. No geometry requirement.

    **Indexing contract (plan §3, binding):** identical to
    :class:`ScintillationFadingEffect` above -- :meth:`evaluate` requires an
    explicit ``context.sample_index`` (raises, naming ``sample_index``,
    *before* drawing) and calls ``context.rng_for("jitter")`` with no index
    argument.
    """

    jitter_sigma_urad: float
    beam_divergence_urad: float
    effect_id: str = field(default="pointing_jitter", init=False)

    def __post_init__(self) -> None:
        _require("jitter_sigma_urad", self.jitter_sigma_urad, lo=0.0, hi=math.inf)
        _require_positive("beam_divergence_urad", self.beam_divergence_urad)

    def evaluate(
        self, t: float, geom: PassGeometry, *, context: EffectEvaluationContext
    ) -> LinkObservables:
        if context.sample_index is None:
            raise ValueError(
                "PointingJitterEffect.evaluate: context.sample_index is "
                "None; this effect requires an explicit sample_index (LINK-4 "
                "indexing contract, plan §3) -- without it, the runtime "
                "would resolve the same RNG stream every call and silently "
                "repeat one draw across all geometries."
            )
        rng = context.rng_for("jitter")
        theta_x = rng.normal(loc=0.0, scale=self.jitter_sigma_urad)
        theta_y = rng.normal(loc=0.0, scale=self.jitter_sigma_urad)
        transmittance_factor = math.exp(
            -2.0 * (theta_x**2 + theta_y**2) / self.beam_divergence_urad**2
        )
        return LinkObservables(
            channel=ChannelObservables(transmittance_factor=transmittance_factor)
        )
