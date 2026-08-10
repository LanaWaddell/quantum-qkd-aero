"""LINK-1: composable link-effect contracts, geometry wrapper, and runtime.

Implements ADR-0003 (RATIFIED 2026-07-17), §7.1 acceptance criteria, per
``docs/LINK_1_PLAN.md`` (v2, approved 2026-08-10). This module ships
**contracts and runtime only** -- it introduces no real stochastic physics,
detector dynamics, estimator changes, or default-output changes. Test-only
mock effects live in ``tests/test_link.py``, not here.

Deferred-rule discharge (plan §1, binding at LINK-1)
-----------------------------------------------------
ADR-0003 §3.3.1 deliberately deferred two composition rules to LINK-1;
``docs/references/quantum-qkd-aero-adr0003-evidence-memo-timebin-review.md``
records the literature evidence for their adoption:

1. ``timing_jitter_s`` -- independent scalar contributions compose **in
   quadrature** (``sqrt(sum(sigma_i**2))``). Evidence anchor: Singh et al.
   2507.08102 Eq. 28 (``dtau_M = sqrt(dtau**2 + dtau_CD**2 + dtau_JD**2 +
   dtau_JT**2)``), independent Gaussian-like broadening sources adding in
   variance. A contribution an effect *declares* correlated (e.g. a shared
   clock) is not silently folded into the quadrature sum -- it raises
   :class:`UnsupportedCorrelatedCompositionError` until a typed correlated-
   state representation is introduced (LINK-4+). ``background_rate_hz``
   carries the same declared-correlated escape hatch and the same fail-loud
   boundary.
2. ``misalignment_error`` -- LINK-1 permits zero or one nonzero contributor;
   a second nonzero contributor raises. The evidence memo's
   ``sin**2(delta_phi)`` DV time-bin phase-error model (X-basis QBER from
   accumulated interferometer phase noise) is recorded here only as the
   *future* estimator-owned mapping from a single composed misalignment
   value to a protocol quantity -- it is explicitly **not** implemented as a
   stack combiner that reconstructs and recombines phase offsets from
   multiple probability contributions. That combination remains estimator-
   owned and deferred with the same fail-loud boundary (LINK-6+).

Correlated-contribution declaration (implementation note -- not fully
pinned by the plan's Protocol code blocks; see the LINK-1 implementation
report for this as a flagged, resolved ambiguity). ``ChannelEffect`` as
specified carries only ``effect_id`` and ``evaluate``; there is no field in
that Protocol for declaring that a nonzero ``background_rate_hz`` or
``timing_jitter_s`` contribution is *correlated* rather than independent.
This module resolves that gap the same way :class:`Controllable` is already
optional and duck-typed: an effect may additionally expose a
``correlated_fields`` attribute -- an iterable of field names drawn from
``{"background_rate_hz", "timing_jitter_s"}`` -- naming which of its
possibly-nonzero observables represent correlated (not independently
composable) structure. Effects that never set it behave exactly as if it
were empty.
"""

from __future__ import annotations

import bisect
import hashlib
import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Protocol

import numpy as np

from qkd.orbit import SatellitePass
from qkd.signals import ChannelState, DetectorParams


# ---------------------------------------------------------------------------
# Exceptions (LINK-1 fail-loud boundaries; plan §4, §5, §6, §7)
# ---------------------------------------------------------------------------


class LinkError(ValueError):
    """Base class for LINK-1 binding-rule violations (ADR-0003 §3, §7)."""


class GeometryTableError(LinkError):
    """Raised for :class:`TableGeometryProvider` contract violations (plan §8)."""


class DuplicateEffectIdError(LinkError):
    """Raised when a stack is constructed with a repeated ``effect_id`` (R5)."""


class DuplicateControlNameError(LinkError):
    """Raised when two declared :class:`ControlSpec` share a name (R5, decision 5)."""


class InvalidObservableError(LinkError):
    """Raised when an effect's observables fail pre-composition validation (§4)."""


class UnsupportedCorrelatedCompositionError(LinkError):
    """Raised when a declared-correlated background/jitter contribution is composed (§1, §4)."""


class SingleContributorConflictError(LinkError):
    """Raised when a second nonzero single-contributor field is composed (§4)."""


class UndeclaredControlError(LinkError):
    """Raised when a control value is supplied for a name no effect declared (§7)."""


class ControlBoundsError(LinkError):
    """Raised when a control value violates its :class:`ControlSpec` static bounds (§7)."""


class InfeasibleControlError(LinkError):
    """Raised when a control value/feasibility intersection is violated (§7, ADR §7.6). Never clamped."""


class SeedRequiredError(LinkError):
    """Raised when an effect requests an RNG stream from a stack constructed with ``seed=None`` (§6)."""


class UnsupportedLinkObservableError(LinkError):
    """Raised by :func:`apply_link_state` for any non-identity observable outside the two folded fields (§5)."""


# ---------------------------------------------------------------------------
# §3 -- Types and Protocols
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PassGeometry:
    """Deterministic exogenous pass state at a single instant (ADR-0003 §3.1).

    ``elevation_deg``/``slant_range_km``/``radial_velocity_mps`` are optional
    so non-satellite media (fibre, decision 4) can conform without inventing
    satellite-specific values. :class:`TableGeometryProvider` (the LINK-1
    satellite provider) never populates ``radial_velocity_mps``: the wrapped
    ``orbit.SatellitePass`` carries no velocity column -- Doppler derivation
    is LINK-3 scope.
    """

    t_s: float
    elevation_deg: float | None
    slant_range_km: float | None
    radial_velocity_mps: float | None = None


class GeometryProvider(Protocol):
    """Deterministic exogenous geometry, tabulated or ephemeris-backed (ADR-0003 §3.1)."""

    def at(self, t: float) -> PassGeometry: ...


@dataclass(frozen=True)
class ChannelObservables:
    """Physical observables composing into ``ChannelState`` territory (ADR-0003 §3.3)."""

    transmittance_factor: float = 1.0
    background_rate_hz: float = 0.0
    misalignment_error: float = 0.0
    frequency_offset_hz: float = 0.0
    timing_jitter_s: float = 0.0


@dataclass(frozen=True)
class DetectorObservables:
    """Physical observables composing into ``DetectorParams`` territory (ADR-0003 §3.3)."""

    efficiency_factor: float = 1.0
    dark_count_rate_hz: float = 0.0
    afterpulse_prob: float = 0.0
    dead_time_s: float = 0.0


@dataclass(frozen=True)
class LinkObservables:
    """A single effect's evaluated output at ``(t, geom)`` (ADR-0003 §3.2, §3.3)."""

    channel: ChannelObservables = ChannelObservables()
    detector: DetectorObservables = DetectorObservables()


@dataclass(frozen=True)
class EffectEvaluationContext:
    """The explicit per-evaluation path for controls and RNG (plan §3, R1).

    R1 invariants (binding): control values are explicit per evaluation; the
    *stack* derives RNG streams, never the effect; stream purpose and
    sample/block index are explicit; repeated or out-of-order evaluation of
    the same indexed sample yields the same result; no effect holds mutable
    RNG state between calls.
    """

    controls: Mapping[str, float]
    sample_index: int | None
    rng_for: Callable[[str, int | None], np.random.Generator]


class ChannelEffect(Protocol):
    """A source/channel/detector effect: one ``evaluate()``, physical observables only.

    ``effect_id`` must be nonempty, stable, and unique within a stack (R5).
    """

    effect_id: str

    def evaluate(
        self,
        t: float,
        geom: PassGeometry,
        *,
        context: EffectEvaluationContext,
    ) -> LinkObservables: ...


@dataclass(frozen=True)
class ControlSpec:
    """A declared tunable parameter -- the intervention surface (ADR-0003 §3.6)."""

    name: str
    unit: str
    bounds: tuple[float, float]
    description: str = ""
    feasible: Callable[["EffectiveLinkState"], tuple[float, float]] | None = None


class Controllable(Protocol):
    """Optional, duck-typed: effects/estimators that declare tunable controls."""

    def controls(self) -> tuple[ControlSpec, ...]: ...


@dataclass(frozen=True)
class EffectiveLinkState:
    """Composed physical state at ``t`` -- construction bridge (ADR ratification decision 2).

    Feeds the existing ``ChannelState`` + ``DetectorParams`` construction via
    :func:`apply_link_state`; it is not a sibling API and computes no gains,
    QBER, or key rate.
    """

    channel: ChannelObservables
    detector: DetectorObservables


# ---------------------------------------------------------------------------
# §8 -- TableGeometryProvider
# ---------------------------------------------------------------------------


class TableGeometryProvider:
    """Wraps ``orbit.SatellitePass`` behind :class:`GeometryProvider` (plan §8, ratification decision 1).

    Binding contract: equal nonzero column lengths; strictly increasing,
    finite ``time_s``; finite stored geometry; columns are snapshotted to
    tuples at construction (immune to later mutation of the source
    ``SatellitePass`` lists); linear interpolation between samples with
    exact stored-value return at exact sample times (byte-identity depends
    on this); an out-of-domain query raises, never silently extrapolates;
    interpolated (and exact) results carry ``PassGeometry.t_s ==
    requested_t``.
    """

    def __init__(self, satellite_pass: SatellitePass) -> None:
        time_s = tuple(float(v) for v in satellite_pass.time_s)
        elevation_deg = tuple(float(v) for v in satellite_pass.elevation_deg)
        slant_range_km = tuple(float(v) for v in satellite_pass.slant_range_km)

        n = len(time_s)
        if n == 0:
            raise GeometryTableError("SatellitePass columns must be nonempty.")
        if len(elevation_deg) != n or len(slant_range_km) != n:
            raise GeometryTableError(
                "SatellitePass time_s/elevation_deg/slant_range_km must have "
                "equal lengths."
            )
        for value in time_s:
            if not math.isfinite(value):
                raise GeometryTableError("SatellitePass.time_s must be finite.")
        for previous, current in zip(time_s, time_s[1:]):
            if not current > previous:
                raise GeometryTableError("SatellitePass.time_s must be strictly increasing.")
        for value in elevation_deg:
            if not math.isfinite(value):
                raise GeometryTableError("SatellitePass.elevation_deg must be finite.")
        for value in slant_range_km:
            if not math.isfinite(value):
                raise GeometryTableError("SatellitePass.slant_range_km must be finite.")

        self._time_s = time_s
        self._elevation_deg = elevation_deg
        self._slant_range_km = slant_range_km

    def at(self, t: float) -> PassGeometry:
        time_s = self._time_s
        n = len(time_s)
        if t < time_s[0] or t > time_s[-1]:
            raise GeometryTableError(
                f"t={t} is outside the pass domain [{time_s[0]}, {time_s[-1]}]."
            )

        idx = bisect.bisect_left(time_s, t)
        if idx < n and time_s[idx] == t:
            return PassGeometry(
                t_s=t,
                elevation_deg=self._elevation_deg[idx],
                slant_range_km=self._slant_range_km[idx],
            )

        lo, hi = idx - 1, idx
        t0, t1 = time_s[lo], time_s[hi]
        frac = (t - t0) / (t1 - t0)
        elevation_deg = self._elevation_deg[lo] + frac * (
            self._elevation_deg[hi] - self._elevation_deg[lo]
        )
        slant_range_km = self._slant_range_km[lo] + frac * (
            self._slant_range_km[hi] - self._slant_range_km[lo]
        )
        return PassGeometry(t_s=t, elevation_deg=elevation_deg, slant_range_km=slant_range_km)


# ---------------------------------------------------------------------------
# §6 -- stochastic reproducibility
# ---------------------------------------------------------------------------


def _child_rng(
    run_seed: int,
    effect_id: str,
    purpose: str,
    index: int | None = None,
) -> np.random.Generator:
    """Derive a stack-owned, order-independent child RNG stream (plan §6).

    Canonical JSON list encoding makes delimiter-based collisions between
    distinct ``(effect_id, purpose)`` tuples impossible (colons inside
    either string cannot be mistaken for a separator). Never Python
    ``hash()`` -- it is process-salted and not reproducible across runs.
    """

    payload = json.dumps(
        [run_seed, effect_id, purpose, index],
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.blake2b(payload, digest_size=16).digest()
    return np.random.default_rng(int.from_bytes(digest, "big"))


# ---------------------------------------------------------------------------
# §4 + §6 + §7 -- ChannelStack
# ---------------------------------------------------------------------------


_CHANNEL_UNIT_INTERVAL_FIELDS = ("transmittance_factor", "misalignment_error")
_CHANNEL_NONNEGATIVE_FIELDS = ("background_rate_hz", "timing_jitter_s")
_CHANNEL_FINITE_ONLY_FIELDS = ("frequency_offset_hz",)

_DETECTOR_UNIT_INTERVAL_FIELDS = ("efficiency_factor", "afterpulse_prob")
_DETECTOR_NONNEGATIVE_FIELDS = ("dark_count_rate_hz", "dead_time_s")

_CORRELATION_AWARE_CHANNEL_FIELDS = frozenset({"background_rate_hz", "timing_jitter_s"})


def _validate_channel_observables(obs: ChannelObservables, effect_id: str) -> None:
    for field_name in _CHANNEL_UNIT_INTERVAL_FIELDS:
        value = getattr(obs, field_name)
        if not math.isfinite(value) or not (0.0 <= value <= 1.0):
            raise InvalidObservableError(
                f"Effect {effect_id!r} produced channel.{field_name}={value!r}, "
                "which must be finite and in [0, 1]."
            )
    for field_name in _CHANNEL_NONNEGATIVE_FIELDS:
        value = getattr(obs, field_name)
        if not math.isfinite(value) or value < 0.0:
            raise InvalidObservableError(
                f"Effect {effect_id!r} produced channel.{field_name}={value!r}, "
                "which must be finite and >= 0."
            )
    for field_name in _CHANNEL_FINITE_ONLY_FIELDS:
        value = getattr(obs, field_name)
        if not math.isfinite(value):
            raise InvalidObservableError(
                f"Effect {effect_id!r} produced channel.{field_name}={value!r}, "
                "which must be finite."
            )


def _validate_detector_observables(obs: DetectorObservables, effect_id: str) -> None:
    for field_name in _DETECTOR_UNIT_INTERVAL_FIELDS:
        value = getattr(obs, field_name)
        if not math.isfinite(value) or not (0.0 <= value <= 1.0):
            raise InvalidObservableError(
                f"Effect {effect_id!r} produced detector.{field_name}={value!r}, "
                "which must be finite and in [0, 1]."
            )
    for field_name in _DETECTOR_NONNEGATIVE_FIELDS:
        value = getattr(obs, field_name)
        if not math.isfinite(value) or value < 0.0:
            raise InvalidObservableError(
                f"Effect {effect_id!r} produced detector.{field_name}={value!r}, "
                "which must be finite and >= 0."
            )


class ChannelStack:
    """Composes ``LinkObservables`` across effects -- nothing more (ADR-0003 §3.4).

    Construction assembles the controls registry (decision 5: per-effect
    declaration mirrored into a central, live runtime registry -- correspondence
    with ``schema.DECLARED_SCHEMA_EXTENSIONS``: same declared-or-fail
    discipline, deliberately not the same object) and rejects duplicate
    ``effect_id``/control names (R5). Evaluation composes per the §3.3.1/§4
    table, validates every effect's raw observables before composing, and
    derives each effect's RNG stream via :func:`_child_rng` -- order-
    independent by construction, never referencing registration order.
    """

    def __init__(
        self,
        effects: Sequence[ChannelEffect],
        geometry: GeometryProvider,
        *,
        seed: int | None = None,
    ) -> None:
        self._effects: tuple[ChannelEffect, ...] = tuple(effects)
        self._geometry = geometry
        self._seed = seed

        seen_effect_ids: set[str] = set()
        for effect in self._effects:
            effect_id = effect.effect_id
            if not effect_id:
                raise ValueError("ChannelEffect.effect_id must be a nonempty string.")
            if effect_id in seen_effect_ids:
                raise DuplicateEffectIdError(f"Duplicate effect_id: {effect_id!r}.")
            seen_effect_ids.add(effect_id)

        registry: dict[str, ControlSpec] = {}
        for effect in self._effects:
            declare = getattr(effect, "controls", None)
            if not callable(declare):
                continue
            for spec in declare():
                if not spec.name:
                    raise ValueError("ControlSpec.name must be a nonempty string.")
                if spec.name in registry:
                    raise DuplicateControlNameError(f"Duplicate control name: {spec.name!r}.")
                lower, upper = spec.bounds
                if not (math.isfinite(lower) and math.isfinite(upper)) or lower > upper:
                    raise ValueError(
                        f"ControlSpec {spec.name!r} bounds must be finite with lower <= upper."
                    )
                registry[spec.name] = spec
        self._controls: dict[str, ControlSpec] = registry

    @property
    def control_specs(self) -> Mapping[str, ControlSpec]:
        """Read-only view of the assembled controls registry (decision 5)."""

        return MappingProxyType(self._controls)

    @property
    def effect_ids(self) -> tuple[str, ...]:
        return tuple(effect.effect_id for effect in self._effects)

    def evaluate(
        self,
        t: float,
        *,
        controls: Mapping[str, float] | None = None,
        sample_index: int | None = None,
    ) -> EffectiveLinkState:
        """Evaluate the composed :class:`EffectiveLinkState` at ``t`` (ADR-0003 §3.4)."""

        resolved_controls: dict[str, float] = dict(controls) if controls else {}
        self._validate_control_static_bounds(resolved_controls)

        geom = self._geometry.at(t)

        transmittance_product = 1.0
        background_sum = 0.0
        frequency_offset_sum = 0.0
        jitter_sum_sq = 0.0
        misalignment_value = 0.0
        misalignment_contributors = 0
        efficiency_product = 1.0
        dark_count_sum = 0.0
        afterpulse_value = 0.0
        afterpulse_contributors = 0
        dead_time_value = 0.0
        dead_time_contributors = 0

        for effect in self._effects:
            context = EffectEvaluationContext(
                controls=MappingProxyType(dict(resolved_controls)),
                sample_index=sample_index,
                rng_for=self._rng_for_factory(effect.effect_id, sample_index),
            )
            observables = effect.evaluate(t, geom, context=context)
            _validate_channel_observables(observables.channel, effect.effect_id)
            _validate_detector_observables(observables.detector, effect.effect_id)

            correlated_fields = frozenset(getattr(effect, "correlated_fields", ()))
            if correlated_fields - _CORRELATION_AWARE_CHANNEL_FIELDS:
                raise ValueError(
                    f"Effect {effect.effect_id!r} declared correlated_fields "
                    f"{sorted(correlated_fields)}; only "
                    f"{sorted(_CORRELATION_AWARE_CHANNEL_FIELDS)} are recognized in LINK-1."
                )

            ch = observables.channel
            transmittance_product *= ch.transmittance_factor

            if ch.background_rate_hz != 0.0:
                if "background_rate_hz" in correlated_fields:
                    raise UnsupportedCorrelatedCompositionError(
                        f"Effect {effect.effect_id!r} declares a correlated "
                        "background_rate_hz contribution; correlated background "
                        "composition has no typed representation before LINK-4+."
                    )
                background_sum += ch.background_rate_hz

            frequency_offset_sum += ch.frequency_offset_hz

            if ch.timing_jitter_s != 0.0:
                if "timing_jitter_s" in correlated_fields:
                    raise UnsupportedCorrelatedCompositionError(
                        f"Effect {effect.effect_id!r} declares a correlated "
                        "timing_jitter_s contribution; correlated jitter "
                        "composition has no typed representation before LINK-4+."
                    )
                jitter_sum_sq += ch.timing_jitter_s ** 2

            if ch.misalignment_error != 0.0:
                misalignment_contributors += 1
                if misalignment_contributors > 1:
                    raise SingleContributorConflictError(
                        f"Effect {effect.effect_id!r} is a second nonzero "
                        "misalignment_error contributor; LINK-1 permits at most one."
                    )
                misalignment_value = ch.misalignment_error

            det = observables.detector
            efficiency_product *= det.efficiency_factor
            dark_count_sum += det.dark_count_rate_hz

            if det.afterpulse_prob != 0.0:
                afterpulse_contributors += 1
                if afterpulse_contributors > 1:
                    raise SingleContributorConflictError(
                        f"Effect {effect.effect_id!r} is a second nonzero "
                        "afterpulse_prob contributor; LINK-1 permits at most one."
                    )
                afterpulse_value = det.afterpulse_prob

            if det.dead_time_s != 0.0:
                dead_time_contributors += 1
                if dead_time_contributors > 1:
                    raise SingleContributorConflictError(
                        f"Effect {effect.effect_id!r} is a second nonzero "
                        "dead_time_s contributor; LINK-1 permits at most one."
                    )
                dead_time_value = det.dead_time_s

        state = EffectiveLinkState(
            channel=ChannelObservables(
                transmittance_factor=transmittance_product,
                background_rate_hz=background_sum,
                misalignment_error=misalignment_value,
                frequency_offset_hz=frequency_offset_sum,
                timing_jitter_s=math.sqrt(jitter_sum_sq),
            ),
            detector=DetectorObservables(
                efficiency_factor=efficiency_product,
                dark_count_rate_hz=dark_count_sum,
                afterpulse_prob=afterpulse_value,
                dead_time_s=dead_time_value,
            ),
        )

        self._validate_control_feasibility(resolved_controls, state)
        return state

    def audit_record(self, controls: Mapping[str, float] | None = None) -> bytes:
        """Canonical, byte-stable audit record: sorted-key JSON of controls,
        ``link_seed``, and effect ids (plan §7, R4 -- bounded LINK-1 disposition).

        LINK-1 emits no controlled production effect and writes nothing into
        ``run_metadata``; this record is available to callers directly and is
        the hard prerequisite the first production controlled effect must
        wire into a declared ``DECLARED_SCHEMA_EXTENSIONS`` entry.
        """

        payload = {
            "controls": dict(controls) if controls else {},
            "link_seed": self._seed,
            "effect_ids": sorted(effect.effect_id for effect in self._effects),
        }
        return json.dumps(
            payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")
        ).encode("utf-8")

    def _rng_for_factory(
        self, effect_id: str, sample_index: int | None
    ) -> Callable[[str, int | None], np.random.Generator]:
        seed = self._seed

        def rng_for(purpose: str, index: int | None = None) -> np.random.Generator:
            if seed is None:
                raise SeedRequiredError(
                    f"Effect {effect_id!r} requested an RNG stream (purpose="
                    f"{purpose!r}) but the stack was constructed with "
                    "link_seed=None; stochastic evaluation requires a resolved "
                    "integer seed."
                )
            resolved_index = sample_index if index is None else index
            return _child_rng(seed, effect_id, purpose, resolved_index)

        return rng_for

    def _validate_control_static_bounds(self, controls: Mapping[str, float]) -> None:
        for name, value in controls.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"Control {name!r} value must be a finite number.")
            numeric_value = float(value)
            if not math.isfinite(numeric_value):
                raise ValueError(f"Control {name!r} value must be finite.")
            if name not in self._controls:
                raise UndeclaredControlError(f"Undeclared control: {name!r}.")
            spec = self._controls[name]
            lower, upper = spec.bounds
            if numeric_value < lower or numeric_value > upper:
                raise ControlBoundsError(
                    f"Control {name!r} ({spec.description or spec.unit}) value "
                    f"{numeric_value} is outside static bounds [{lower}, {upper}]."
                )

    def _validate_control_feasibility(
        self, controls: Mapping[str, float], state: EffectiveLinkState
    ) -> None:
        for name, value in controls.items():
            spec = self._controls[name]
            if spec.feasible is None:
                continue
            feasible_lower, feasible_upper = spec.feasible(state)
            static_lower, static_upper = spec.bounds
            lower = max(static_lower, feasible_lower)
            upper = min(static_upper, feasible_upper)
            if lower > upper:
                raise InfeasibleControlError(
                    f"Control {name!r} ({spec.description or spec.unit}) has an "
                    f"empty feasible intersection: static=[{static_lower}, "
                    f"{static_upper}], feasible=[{feasible_lower}, {feasible_upper}]."
                )
            if value < lower or value > upper:
                raise InfeasibleControlError(
                    f"Control {name!r} ({spec.description or spec.unit}) value "
                    f"{value} is outside the feasible intersection [{lower}, "
                    f"{upper}] (static=[{static_lower}, {static_upper}], "
                    f"feasible=[{feasible_lower}, {feasible_upper}]); values "
                    "outside feasibility are rejected, never clamped."
                )


# ---------------------------------------------------------------------------
# §5 -- apply_link_state bridge
# ---------------------------------------------------------------------------


_IDENTITY_CHANNEL_FIELDS: dict[str, float] = {
    "background_rate_hz": 0.0,
    "misalignment_error": 0.0,
    "frequency_offset_hz": 0.0,
    "timing_jitter_s": 0.0,
}
_IDENTITY_DETECTOR_FIELDS: dict[str, float] = {
    "dark_count_rate_hz": 0.0,
    "afterpulse_prob": 0.0,
    "dead_time_s": 0.0,
}


def apply_link_state(
    state: EffectiveLinkState,
    *,
    channel: ChannelState,
    detector: DetectorParams,
) -> tuple[ChannelState, DetectorParams]:
    """Fold the two currently-representable link observables into the existing seam (plan §5).

    Folds exactly two fields: ``transmittance_factor`` into a copy of
    ``channel`` (only ``transmittance`` replaced) and ``efficiency_factor``
    into a copy of ``detector`` (only ``detection_efficiency`` replaced).
    Both folded results are validated to lie in ``[0, 1]``. Any other
    non-identity observable -- ``background_rate_hz``, ``dark_count_rate_hz``
    (no defined gate window yet), ``misalignment_error``,
    ``frequency_offset_hz``, ``timing_jitter_s``, ``afterpulse_prob``,
    ``dead_time_s`` -- is unrepresentable by the current estimator path and
    raises :class:`UnsupportedLinkObservableError` naming the field; nothing
    is silently dropped.
    """

    for field_name, identity_value in _IDENTITY_CHANNEL_FIELDS.items():
        value = getattr(state.channel, field_name)
        if value != identity_value:
            raise UnsupportedLinkObservableError(
                f"channel.{field_name}={value!r} is not representable by the "
                f"current estimator path (identity={identity_value})."
            )
    for field_name, identity_value in _IDENTITY_DETECTOR_FIELDS.items():
        value = getattr(state.detector, field_name)
        if value != identity_value:
            raise UnsupportedLinkObservableError(
                f"detector.{field_name}={value!r} is not representable by the "
                f"current estimator path (identity={identity_value})."
            )

    new_transmittance = channel.transmittance * state.channel.transmittance_factor
    if not math.isfinite(new_transmittance) or not (0.0 <= new_transmittance <= 1.0):
        raise ValueError(
            f"Folded transmittance {new_transmittance!r} is outside [0, 1]."
        )
    new_channel = replace(channel, transmittance=new_transmittance)

    new_efficiency = detector.detection_efficiency * state.detector.efficiency_factor
    if not math.isfinite(new_efficiency) or not (0.0 <= new_efficiency <= 1.0):
        raise ValueError(
            f"Folded detection_efficiency {new_efficiency!r} is outside [0, 1]."
        )
    new_detector = replace(detector, detection_efficiency=new_efficiency)

    return new_channel, new_detector
