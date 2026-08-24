"""Quasiperiodic misalignment fixture and irrational-rotation diagnostics.

**This module models no physics.** Free-space propagation imposes no
golden-angle rotation on a polarization or time-bin reference frame, and
nothing here should be read as claiming otherwise. The numerical proximity
of the golden angle (137.5077...deg) to the inverse fine-structure constant
(137.036) is a coincidence of units and carries no physical content.

What this module *is*: a deterministic, non-repeating misalignment schedule
used as a stress fixture. Physical misalignment drift over a pass is smooth
and slow; a seeded random walk is unstructured. A quasiperiodic schedule is
neither -- it is fully reproducible from one scalar, never repeats within
any practical horizon, and -- its rotation number being badly approximable
(continued fraction all ones, so its partial quotients are bounded) --
equidistributes with bounded-type discrepancy: ``N * D*_N / log N`` stays
bounded in ``N``. That combination makes it a useful
adversarial input for three questions the physical library cannot pose:

1. Does an estimator's running QBER converge at the rate its finite-key
   analysis assumes, when the error contribution is deterministic but
   non-periodic?
2. Does coarse-grid evaluation alias a bounded, smooth, deterministic
   signal into a biased mean? (It does; see :func:`aliasing_bias`. In this
   repository PDT is the per-block probability-distribution-of-transmittance
   mode, ADR-0003 section 4 -- the bandwidth question here is about any
   evaluation grid, including PDT's block grid.)
3. Does a drift monitor tuned on periodic or stochastic misalignment
   register a quasiperiodic excursion of the same amplitude?

Scope of what a golden-angle step can and cannot show
-----------------------------------------------------
The orbit ``{n * alpha}`` for irrational ``alpha`` is Weyl-equidistributed.
Any observable that depends only on the invariant measure -- the long-run
mean misalignment error, the asymptotic key rate -- has the **same** limit
for every irrational step angle. Golden is not special there, and a result
reporting a steady-state difference between two irrational steps is
reporting a bug, not a discovery. See
:func:`tests/test_quasiperiodic_fixture.py::test_ergodic_limit_is_step_independent`.

Where the golden angle genuinely differs is finite-``N`` structure. Its
continued fraction is all ones, so it is badly approximable with the
smallest possible partial quotients, and its orbit is of bounded type:
``N * D*_N / log N`` stays bounded in ``N``. That is a boundedness claim,
not a minimality claim -- it does not give the smallest ``D*_N`` at every
N (see the pointwise-optimality null test). Discriminating
observables are therefore convergence rate at fixed ``N``, worst-case
deviation, and gap statistics -- not steady-state anything.

Rationality caveat (binding for any run using this fixture). In IEEE-754
double precision every ``step_deg`` is a dyadic rational, so every orbit is
eventually periodic; ``step_deg=137.5`` exactly is ``275/2`` degrees --
``55/144`` of a turn -- and closes after 144 steps, which is short enough
to see. :func:`orbit_period` reports
the exact closure period of the represented value, and the fixture's own
acceptance test asserts that any run stays well below it.

Composition
-----------
:class:`QuasiperiodicMisalignmentFixture` is a third ``misalignment_error``
owner alongside :class:`~qkd.effects.PolarizationMisalignmentEffect` and
:class:`~qkd.effects.PhaseMisalignmentEffect`. The LINK-1 single-contributor
rule applies unchanged: a second nonzero misalignment contributor anywhere
in the same stack raises
:class:`~qkd.link.SingleContributorConflictError`. It declares no controls,
consumes no RNG, and reads nothing outside ``(t, geom)`` -- the ADR-0002
wall is untouched, as it must be for a fixture that will be pointed at
estimators.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from fractions import Fraction

from qkd.link import (
    ChannelObservables,
    EffectEvaluationContext,
    LinkObservables,
    PassGeometry,
)

GOLDEN_ANGLE_DEG = 137.50776405003785
"""``360 * (2 - phi)``, the golden angle in degrees, at double precision."""

SILVER_STEP_DEG = 360.0 * (math.sqrt(2.0) - 1.0)
"""A second irrational step (from ``sqrt(2)``) used as the null-comparison arm."""

_MAX_AMPLITUDE_RAD = math.pi / 4.0
"""Small-angle ceiling, matching :class:`~qkd.effects.PhaseMisalignmentEffect`.

The excursion is bounded so the emitted ``sin**2`` value stays inside the
monotone branch of the same time-bin phase-error model the physical owner
discharges. Without this ceiling a quasiperiodic phase would wrap and the
fixture would silently emit out-of-model errors that happen to land in
``[0, 1]``.
"""


def _require(name: str, value: float, *, lo: float, hi: float) -> None:
    """Construction-time closed-interval domain check, named failure."""

    if not math.isfinite(value) or not (lo <= value <= hi):
        raise ValueError(
            f"{name} must be finite and in [{lo}, {hi}]; got {value!r}."
        )


def _require_positive(name: str, value: float) -> None:
    """Construction-time strict-positivity check, named failure."""

    if not math.isfinite(value) or not value > 0.0:
        raise ValueError(f"{name} must be finite and > 0; got {value!r}.")


# ---------------------------------------------------------------------------
# Orbit diagnostics (pure functions -- no observables, no stack coupling)
# ---------------------------------------------------------------------------


def orbit(n_samples: int, step_deg: float, *, phase0: float = 0.0) -> list[float]:
    """The rotation orbit ``{phase0 + n * step_deg / 360}`` on ``[0, 1)``."""

    if n_samples < 1:
        raise ValueError(f"n_samples must be >= 1; got {n_samples!r}.")
    alpha = step_deg / 360.0
    return [math.fmod(phase0 + i * alpha, 1.0) % 1.0 for i in range(n_samples)]


def star_discrepancy(points: list[float]) -> float:
    """Exact star discrepancy ``D*_N`` of a point set in ``[0, 1)``.

    For a one-dimensional set the supremum is attained at the sorted points,
    so the exact value is computable in ``O(N log N)`` -- no estimation.
    Lower is more uniform; the golden step's badly approximable rotation
    number keeps ``N * D*_N / log N`` bounded (bounded-type discrepancy).
    """

    if not points:
        raise ValueError("points must be nonempty.")
    ordered = sorted(points)
    n = len(ordered)
    worst = 0.0
    for i, x in enumerate(ordered):
        worst = max(worst, abs((i + 1) / n - x), abs(i / n - x))
    return worst


def gap_lengths(points: list[float]) -> list[float]:
    """Sorted distinct circular gap lengths between successive orbit points.

    The three-distance theorem guarantees at most three distinct values for
    any rotation orbit, irrational or not. Used as a structural assertion
    that the fixture really is a rotation orbit and not an ad-hoc waveform.
    """

    if len(points) < 2:
        raise ValueError("points must contain at least two entries.")
    ordered = sorted(points)
    gaps = [b - a for a, b in zip(ordered, ordered[1:])]
    gaps.append(1.0 - ordered[-1] + ordered[0])
    distinct: list[float] = []
    for g in sorted(gaps):
        if not distinct or abs(g - distinct[-1]) > 1e-9:
            distinct.append(g)
    return distinct


def orbit_period(step_deg: float) -> int:
    """Closure period in steps of ``step_deg`` read as an exact decimal.

    Returns the denominator of ``Fraction(str(step_deg)) / 360`` in lowest
    terms -- the step count after which a step angle that is rational *as
    written* repeats. ``137.5`` gives 144, not some astronomical number:
    a decimal literal a human would call "the golden angle, rounded" is a
    short-period signal wearing quasiperiodic clothing, and that is exactly
    the confound this fixture has to be able to expose.

    Two caveats, both binding on interpretation:

    * This is decimal semantics, not IEEE-754 semantics. In double
      precision every step is a dyadic rational and every orbit closes
      eventually, but at a denominator near ``2**52`` -- so the float orbit
      of a rational step tracks the exact rational orbit only up to
      accumulated rounding (empirically ``~1e-14`` over ``n <= 500``), and
      the float orbit of an irrational step never closes in practice.
    * A large return value is not evidence of irrationality. It means the
      literal has no short exact period, which is necessary but not
      sufficient. Use :func:`star_discrepancy` growth for the substantive
      question.
    """

    return (Fraction(str(step_deg)) / 360).denominator


def aliasing_bias(
    amplitude_rad: float,
    step_deg: float,
    *,
    coarse_stride: int,
    n_samples: int,
    phase0: float = 0.0,
) -> float:
    """Mean misalignment error on a coarse grid minus the fine-grid mean.

    Evidence for the ADR-0003 amendment argued in ``docs/notes/
    DN-quasiperiodic-misalignment.md``: tabulation safety is a claim about
    bandwidth relative to the evaluation grid, **not** about determinism.
    A fully deterministic, bounded, smooth signal sampled on a stride that
    beats against its rotation number produces a biased mean, because
    ``sin**2`` is nonlinear -- the same failure mode ADR-0003 already
    forbids for stochastic fading, arriving by a different route.

    A nonzero return is the whole point; the sign and size depend on the
    stride/step resonance.
    """

    if coarse_stride < 1:
        raise ValueError(f"coarse_stride must be >= 1; got {coarse_stride!r}.")
    fine = orbit(n_samples, step_deg, phase0=phase0)
    coarse = fine[::coarse_stride]
    fine_mean = sum(_error_from_fraction(amplitude_rad, u) for u in fine) / len(fine)
    coarse_mean = sum(
        _error_from_fraction(amplitude_rad, u) for u in coarse
    ) / len(coarse)
    return coarse_mean - fine_mean


def _error_from_fraction(amplitude_rad: float, u: float) -> float:
    """Map an orbit position ``u`` in ``[0, 1)`` to a misalignment error."""

    delta_phi = amplitude_rad * math.sin(2.0 * math.pi * u)
    return math.sin(delta_phi) ** 2


# ---------------------------------------------------------------------------
# The fixture effect
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QuasiperiodicMisalignmentFixture:
    """Deterministic quasiperiodic ``misalignment_error`` owner (fixture).

    The emitted value is ``sin**2(A * sin(2 * pi * {phase0 + n * alpha}))``
    with ``n = t / step_period_s`` and ``alpha = step_deg / 360``. The outer
    ``sin**2`` is the same time-bin phase-error mapping
    :class:`~qkd.effects.PhaseMisalignmentEffect` discharges; the inner
    bounded sine is what makes the excursion quasiperiodic while keeping
    ``delta_phi`` inside the small-angle model.

    ``amplitude_rad == 0`` emits exact identity, so the fixture is inert
    unless deliberately armed.

    ``step_deg`` stays a free parameter. That is deliberate: the fixture is
    a discriminator between rotation numbers, not an argument for one, and
    the acceptance tests use ``SILVER_STEP_DEG`` and a rational step as
    comparison arms.
    """

    amplitude_rad: float
    step_period_s: float
    step_deg: float = GOLDEN_ANGLE_DEG
    phase0: float = 0.0
    effect_id: str = field(default="fixture_quasiperiodic_misalignment", init=False)

    def __post_init__(self) -> None:
        _require("amplitude_rad", self.amplitude_rad, lo=0.0, hi=_MAX_AMPLITUDE_RAD)
        _require_positive("step_period_s", self.step_period_s)
        _require("step_deg", self.step_deg, lo=0.0, hi=360.0)
        _require("phase0", self.phase0, lo=0.0, hi=1.0)

    def orbit_position(self, t: float) -> float:
        """Orbit position in ``[0, 1)`` at time ``t`` -- pure, no observables."""

        n = t / self.step_period_s
        return math.fmod(self.phase0 + n * (self.step_deg / 360.0), 1.0) % 1.0

    def delta_phi_rad(self, t: float) -> float:
        """Instantaneous phase excursion, bounded by ``amplitude_rad``."""

        return self.amplitude_rad * math.sin(2.0 * math.pi * self.orbit_position(t))

    def evaluate(
        self, t: float, geom: PassGeometry, *, context: EffectEvaluationContext
    ) -> LinkObservables:
        misalignment_error = math.sin(self.delta_phi_rad(t)) ** 2
        return LinkObservables(
            channel=ChannelObservables(misalignment_error=misalignment_error)
        )
