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

LINK-6 source/detector-consumption gate (LINK-5, ``docs/LINK_5_PLAN.md``
§3 -- consolidated, binding)
------------------------------------------------------------------------
LINK-5 adds three source/detector parameter owners below --
:class:`MuFluctuationEffect`, :class:`DetectorAfterpulsingEffect`,
:class:`DetectorDeadTimeEffect` -- none of which are folded into gains,
QBER, or key rate by this module; ``qkd.link.apply_link_state`` bridge-
rejects all three (``source.intensity_factor``, ``detector.afterpulse_prob``,
``detector.dead_time_s``) as non-identity observables. The consumption gate
those three parameters must clear before any future LINK-6 work folds them
into an estimator (plan §3, verbatim):

    "Before any LINK-5 observable is folded into gains, errors, or key
    rate, LINK-6 must declare: (1) the realized-versus-observed
    source-intensity information model; (2) a decoy-state proof valid for
    the selected intensity uncertainty and correlation assumptions; (3)
    the detector dead-time response convention; (4) the afterpulse
    conditioning/window or kernel model; and (5) the interaction order or
    joint model for dead time and afterpulsing. Until all applicable items
    are present, non-identity LINK-5 observables remain bridge-rejected."

See also :class:`qkd.link.SourceObservables`'s epistemic contract (plan
§1.2) for the source side of this same boundary.
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
    SourceObservables,
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


# ---------------------------------------------------------------------------
# LINK-5 -- source-partition and detector-parameter effects
# (docs/LINK_5_PLAN.md, v2 approved). None join the production stack; all
# three are bridge-rejected by ``qkd.link.apply_link_state`` until the
# "LINK-6 source/detector-consumption gate" above is satisfied. Fixed
# canonical IDs: ``mu_fluctuation``, ``detector_afterpulsing``,
# ``detector_dead_time`` (plan §2).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MuFluctuationEffect:
    """Epoch-common multiplicative source-intensity fluctuation (LINK-5, plan §1, §2.1).

    **Epoch-common semantics (LINK-5 plan §1.3, R2 -- binding, verbatim):**
    "Each indexed evaluation draws one common multiplicative source factor
    for the complete modeled mission epoch. The factor scales every nonzero
    nominal intensity setting in that epoch. Multiplication preserves exact
    zero (a true vacuum setting stays zero; a nonzero nominal 'vacuum' is
    scaled like the other settings). It does not model pulse-resolved
    fluctuations, setting-conditioned error distributions, or correlations
    with previous intensity choices. Those require a pulse/block generator
    and a compatible security analysis."

    ``sample_index`` indexes a pass/profile epoch, not an optical pulse --
    this is block/epoch-common calibration fluctuation by declaration.

    ::

        sigma_log_sq = ln(1 + relative_sigma^2)   [relative_sigma = RMS relative fluctuation, std/mean]
        sigma_log    = sqrt(sigma_log_sq)          [standard deviation of log-factor]
        mu_log       = -sigma_log_sq / 2           [unit-mean normalization]
        X ~ N(mu_log, sigma_log)  from context.rng_for("mu")   [scale = std dev]
        intensity_factor = exp(X)

    **Numerical contract (LINK-5 plan §2.1, R4 -- overflow-safe disposition):**
    construction computes and validates that the derived ``sigma_log_sq``,
    ``sigma_log``, and ``mu_log`` are all finite -- a huge-but-finite
    ``relative_sigma`` whose square overflows fails loudly at
    **construction**, not silently at first draw. Evaluation validates the
    sampled factor is finite before emitting it (never leaks
    ``inf``/``NaN``/``OverflowError`` as an accepted observable);
    ``qkd.link.ChannelStack``'s composed-source validation (plan §1.4) is
    the backstop layer beyond this effect's own.

    **Zero-variance case (pinned):** the class is stochastic *by contract*
    -- ``relative_sigma=0`` still draws (a scale-0 normal), still requires a
    resolved seed and an explicit ``sample_index``, and yields
    ``intensity_factor`` exactly ``1.0``; consistent with LINK-4's
    zero-jitter behaviour (:class:`PointingJitterEffect`).

    Declares ``unit_mean_fading_fields = {"intensity_factor"}`` (LINK-5
    plan §1.4): at :class:`~qkd.link.ChannelStack` construction this relaxes
    that field's validation, for this effect only, from ``[0, 1]`` to finite
    and ``>= 0`` (the factor is > 1 for roughly half of all draws).

    Domain: ``relative_sigma`` finite ``>= 0``, validated at construction
    via :func:`_require`. Typical magnitudes are percent-level (calibration
    drift, not pulse-resolved noise). No geometry requirement.

    **Indexing contract (plan §3, binding):** identical in shape to
    :class:`ScintillationFadingEffect`/:class:`PointingJitterEffect` --
    :meth:`evaluate` requires an explicit ``context.sample_index`` (raises,
    naming ``sample_index``, *before* drawing) and calls
    ``context.rng_for("mu")`` with no index argument, letting the
    stack-owned context supply the already-validated index.

    **Consumption gate:** see the module docstring's "LINK-6 source/
    detector-consumption gate" section and ``qkd.link.SourceObservables``'s
    epistemic contract -- ``intensity_factor`` remains bridge-rejected until
    that gate is satisfied.
    """

    relative_sigma: float
    effect_id: str = field(default="mu_fluctuation", init=False)
    unit_mean_fading_fields: frozenset[str] = field(
        default=frozenset({"intensity_factor"}), init=False
    )
    sigma_log_sq: float = field(init=False, repr=False, compare=False)
    sigma_log: float = field(init=False, repr=False, compare=False)
    mu_log: float = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        _require("relative_sigma", self.relative_sigma, lo=0.0, hi=math.inf)

        # Multiplication (not ``**``), deliberately: CPython's float ``**``
        # raises OverflowError on an overflowing result instead of returning
        # inf, which would surface as an uncaught OverflowError rather than
        # the controlled, contract-named ValueError below (R4 numerical
        # contract, LINK-5 plan §2.1).
        relative_sigma_sq = self.relative_sigma * self.relative_sigma
        sigma_log_sq = math.log1p(relative_sigma_sq)
        if not math.isfinite(sigma_log_sq):
            raise ValueError(
                "MuFluctuationEffect: derived sigma_log_sq="
                f"{sigma_log_sq!r} is not finite for relative_sigma="
                f"{self.relative_sigma!r} (construction-time R4 numerical "
                "contract, LINK-5 plan §2.1)."
            )
        sigma_log = math.sqrt(sigma_log_sq)
        mu_log = -sigma_log_sq / 2.0
        if not math.isfinite(sigma_log) or not math.isfinite(mu_log):
            raise ValueError(
                "MuFluctuationEffect: derived sigma_log/mu_log are not both "
                f"finite (sigma_log={sigma_log!r}, mu_log={mu_log!r}) for "
                f"relative_sigma={self.relative_sigma!r} (construction-time "
                "R4 numerical contract, LINK-5 plan §2.1)."
            )

        object.__setattr__(self, "sigma_log_sq", sigma_log_sq)
        object.__setattr__(self, "sigma_log", sigma_log)
        object.__setattr__(self, "mu_log", mu_log)

    def evaluate(
        self, t: float, geom: PassGeometry, *, context: EffectEvaluationContext
    ) -> LinkObservables:
        if context.sample_index is None:
            raise ValueError(
                "MuFluctuationEffect.evaluate: context.sample_index is "
                "None; this effect requires an explicit sample_index (LINK-5 "
                "indexing contract, plan §3) -- without it, the runtime "
                "would resolve the same RNG stream every call and silently "
                "repeat one draw across all geometries."
            )
        rng = context.rng_for("mu")
        x = rng.normal(loc=self.mu_log, scale=self.sigma_log)
        try:
            # CPython's math.exp raises OverflowError on an overflowing
            # result instead of returning inf; caught and normalized to inf
            # so the finiteness check below is the one controlled,
            # contract-named raise (R4 numerical contract, LINK-5 plan §2.1)
            # -- never an uncaught OverflowError escaping evaluate().
            intensity_factor = math.exp(x)
        except OverflowError:
            intensity_factor = math.inf
        if not math.isfinite(intensity_factor):
            raise ValueError(
                "MuFluctuationEffect.evaluate: sampled intensity_factor="
                f"{intensity_factor!r} is not finite; refusing to emit a "
                "non-finite observable (R4 numerical contract, LINK-5 plan "
                "§2.1) -- qkd.link.ChannelStack's composed-source validation "
                "is a further backstop, not a substitute for this check."
            )
        return LinkObservables(source=SourceObservables(intensity_factor=intensity_factor))


@dataclass(frozen=True)
class DetectorAfterpulsingEffect:
    """Nominal/calibrated conditional afterpulse-probability parameter owner (LINK-5, plan §2.2).

    **Binding contract (LINK-5 plan §2.2, R3.1 -- verbatim):** "``afterpulse_prob``
    is a nominal/calibrated *conditional* afterpulse-probability parameter
    under a declared detector operating convention. It is not an
    independent additive count probability or a context-free material
    constant. LINK-6 must define its conditioning event, counting
    window/gate model, and interaction with dead time before use." (Afterpulse
    estimation is calibration- and rate-dependent; cf. Wiechers et al.,
    gated-APD afterpulsing.)

    Domain: finite, in ``[0, 1]``, validated at construction via
    :func:`_require`. Ignores ``context`` -- no controls, no RNG ("a
    constant is a function that ignores t", plan §4).

    This is a **single-contributor field owner**
    (``qkd.link.ChannelStack``, LINK-1): a second nonzero
    ``afterpulse_prob`` contributor anywhere in the same stack raises
    :class:`~qkd.link.SingleContributorConflictError`; a distinct nonzero
    :class:`DetectorDeadTimeEffect` contributor coexists in the same stack
    without conflict (different field; LINK-5 plan §2.3).

    Not in the production stack; bridge-rejected by
    ``qkd.link.apply_link_state`` until LINK-6 -- see the module
    docstring's "LINK-6 source/detector-consumption gate".
    """

    afterpulse_prob: float
    effect_id: str = field(default="detector_afterpulsing", init=False)

    def __post_init__(self) -> None:
        _require("afterpulse_prob", self.afterpulse_prob, lo=0.0, hi=1.0)

    def evaluate(
        self, t: float, geom: PassGeometry, *, context: EffectEvaluationContext
    ) -> LinkObservables:
        return LinkObservables(
            detector=DetectorObservables(afterpulse_prob=self.afterpulse_prob)
        )


@dataclass(frozen=True)
class DetectorDeadTimeEffect:
    """Detector recovery/hold-off duration parameter owner (LINK-5, plan §2.3).

    **Binding contract (LINK-5 plan §2.3, R3.2 -- verbatim):** "``dead_time_s``
    is the detector recovery/hold-off duration parameter. LINK-5 assigns no
    throughput law. LINK-6 must declare the detector timing model
    (non-paralyzable, paralyzable, or gated/hold-off) and the rate variable
    to which the parameter applies."

    Domain: finite, ``>= 0``, validated at construction via :func:`_require`.
    Ignores ``context`` -- no controls, no RNG ("a constant is a function
    that ignores t", plan §4).

    This is a **single-contributor field owner**
    (``qkd.link.ChannelStack``, LINK-1): a second nonzero ``dead_time_s``
    contributor anywhere in the same stack raises
    :class:`~qkd.link.SingleContributorConflictError`; a distinct nonzero
    :class:`DetectorAfterpulsingEffect` contributor coexists in the same
    stack without conflict (different field; LINK-5 plan §2.2).

    Not in the production stack; bridge-rejected by
    ``qkd.link.apply_link_state`` until LINK-6 -- see the module
    docstring's "LINK-6 source/detector-consumption gate".
    """

    dead_time_s: float
    effect_id: str = field(default="detector_dead_time", init=False)

    def __post_init__(self) -> None:
        _require("dead_time_s", self.dead_time_s, lo=0.0, hi=math.inf)

    def evaluate(
        self, t: float, geom: PassGeometry, *, context: EffectEvaluationContext
    ) -> LinkObservables:
        return LinkObservables(detector=DetectorObservables(dead_time_s=self.dead_time_s))
