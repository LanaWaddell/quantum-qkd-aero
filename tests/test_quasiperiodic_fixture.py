"""Acceptance tests for the quasiperiodic misalignment fixture.

``docs/notes/DN-quasiperiodic-misalignment.md`` -- contract conformance,
the null results that bound what a golden-angle step can be claimed to
show, and the aliasing evidence for the proposed ADR-0003 §4 row-1 clarification.

The null tests are the load-bearing ones. Three of them exist specifically
to make an over-claim fail loudly:
``test_ergodic_limit_is_step_independent`` (no steady-state difference
between irrational steps), ``test_golden_is_not_pointwise_optimal`` (golden
does not win at every N), and ``test_fixture_is_not_pdt_admissible``
(a fixture may not be tabulated).
"""

from __future__ import annotations

import math

import pytest

from qkd.detection import PDT_ADMISSIBLE_EFFECTS
from qkd.effects import PolarizationMisalignmentEffect
from qkd.fixtures.quasiperiodic import (
    GOLDEN_ANGLE_DEG,
    SILVER_STEP_DEG,
    QuasiperiodicMisalignmentFixture,
    aliasing_bias,
    gap_lengths,
    orbit,
    orbit_period,
    star_discrepancy,
)
from qkd.link import ChannelStack, PassGeometry, SingleContributorConflictError

E_STEP_DEG = 360.0 * (math.e - 2.0)
PI_STEP_DEG = 360.0 * (math.pi - 3.0)
RATIONAL_STEP_DEG = 137.5

GEOM = PassGeometry(
    t_s=0.0, elevation_deg=45.0, slant_range_km=1000.0
)


class _FixedGeometry:
    """Medium-neutral constant geometry -- the fixture ignores it entirely."""

    def at(self, t: float) -> PassGeometry:
        return PassGeometry(
            t_s=t, elevation_deg=45.0, slant_range_km=1000.0
        )


def _ctx():
    """Minimal evaluation context: no controls, no sample index, no RNG use."""

    def _rng(purpose: str, index: int | None):  # pragma: no cover - never called
        raise AssertionError("fixture must not consume RNG")

    from qkd.link import EffectEvaluationContext

    return EffectEvaluationContext(controls={}, sample_index=None, rng_for=_rng)


def _error_at(fixture: QuasiperiodicMisalignmentFixture, t: float) -> float:
    return fixture.evaluate(t, GEOM, context=_ctx()).channel.misalignment_error


def _mean_error(step_deg: float, amplitude: float, n: int) -> float:
    return sum(
        math.sin(amplitude * math.sin(2.0 * math.pi * u)) ** 2
        for u in orbit(n, step_deg)
    ) / n


# ---------------------------------------------------------------------------
# Contract conformance
# ---------------------------------------------------------------------------


def test_zero_amplitude_is_exact_identity():
    """The inert case is bit-exact, not merely close -- the fixture is opt-in."""

    fixture = QuasiperiodicMisalignmentFixture(
        amplitude_rad=0.0, step_period_s=1.0
    )
    for t in (0.0, 1.0, 7.5, 1234.75):
        assert _error_at(fixture, t) == 0.0


def test_evaluation_is_deterministic_and_order_independent():
    """Repeated and out-of-order evaluation of the same t agree exactly."""

    fixture = QuasiperiodicMisalignmentFixture(
        amplitude_rad=0.2, step_period_s=0.5
    )
    forward = [_error_at(fixture, t / 4.0) for t in range(200)]
    backward = [_error_at(fixture, t / 4.0) for t in reversed(range(200))]
    assert forward == list(reversed(backward))


def test_emitted_error_stays_in_small_angle_model():
    """Bounded excursion keeps sin**2 on its monotone branch (no wrap)."""

    fixture = QuasiperiodicMisalignmentFixture(
        amplitude_rad=math.pi / 4.0, step_period_s=1.0
    )
    values = [_error_at(fixture, float(n)) for n in range(5000)]
    assert min(values) >= 0.0
    assert max(values) <= math.sin(math.pi / 4.0) ** 2 + 1e-12


@pytest.mark.parametrize(
    "kwargs",
    [
        {"amplitude_rad": -1e-9, "step_period_s": 1.0},
        {"amplitude_rad": math.pi / 4.0 + 1e-9, "step_period_s": 1.0},
        {"amplitude_rad": math.nan, "step_period_s": 1.0},
        {"amplitude_rad": 0.1, "step_period_s": 0.0},
        {"amplitude_rad": 0.1, "step_period_s": -1.0},
        {"amplitude_rad": 0.1, "step_period_s": 1.0, "step_deg": 360.1},
        {"amplitude_rad": 0.1, "step_period_s": 1.0, "phase0": 1.5},
    ],
)
def test_invalid_parameters_fail_at_construction(kwargs):
    """Domain violations fail loudly at construction, never at evaluation."""

    with pytest.raises(ValueError):
        QuasiperiodicMisalignmentFixture(**kwargs)


def test_single_contributor_rule_applies():
    """A second nonzero misalignment owner in the same stack raises."""

    stack = ChannelStack(
        effects=(
            QuasiperiodicMisalignmentFixture(
                amplitude_rad=0.2, step_period_s=1.0
            ),
            PolarizationMisalignmentEffect(error_prob=0.01),
        ),
        geometry=_FixedGeometry(),
    )
    with pytest.raises(SingleContributorConflictError):
        stack.evaluate(0.25)


def test_fixture_is_not_pdt_admissible():
    """No fixture effect_id may enter the tabulation allowlist.

    Load-bearing. PDT admission asserts a signal is safe to precompute on
    the evaluation grid; this fixture is chosen for spectral content that
    breaks that assertion (see the aliasing tests below).
    """

    fixture = QuasiperiodicMisalignmentFixture(
        amplitude_rad=0.1, step_period_s=1.0
    )
    assert fixture.effect_id.startswith("fixture_")
    assert fixture.effect_id not in PDT_ADMISSIBLE_EFFECTS


# ---------------------------------------------------------------------------
# Null results -- what a golden step cannot be claimed to show
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "step_deg", [GOLDEN_ANGLE_DEG, SILVER_STEP_DEG, E_STEP_DEG]
)
def test_ergodic_limit_is_step_independent(step_deg):
    """Steady-state mean error is identical across irrational steps.

    Load-bearing null result. Weyl equidistribution fixes the invariant
    measure, so any observable depending only on it -- long-run QBER
    contribution, asymptotic key rate -- cannot distinguish rotation
    numbers. A run reporting a steady-state golden-angle advantage has a
    bug, not a finding.
    """

    amplitude = 0.3
    reference = 0.0439974
    assert _mean_error(step_deg, amplitude, 200_000) == pytest.approx(
        reference, abs=1e-5
    )


def test_golden_is_not_pointwise_optimal():
    """Golden does not have the smallest D*_N at every N.

    Load-bearing null result. Golden's bounded-type property is a
    worst-case-over-N boundedness statement, not pointwise dominance:
    at N = 5000 the sqrt(2) step is more uniform. This test pins that so a
    later run cannot quietly reinterpret a single favourable N as a
    general win.
    """

    golden = star_discrepancy(orbit(5000, GOLDEN_ANGLE_DEG))
    silver = star_discrepancy(orbit(5000, SILVER_STEP_DEG))
    assert silver < golden


# ---------------------------------------------------------------------------
# Discriminating results -- what a golden step can show
# ---------------------------------------------------------------------------


def test_golden_worst_case_discrepancy_is_bounded_over_declared_range():
    """Golden's normalised discrepancy stays below the declared bound over the
    tested N set, while the well-approximable pi-derived comparison is much
    larger.

    This is the real discriminator: not the value at any single N, but the
    supremum of ``N D*_N / log N`` over the declared range. Golden is the
    badly-approximable arm; the pi-derived step admits the strong rational
    approximation 22/7, so its orbit clusters and the ratio grows. A finite
    check over {50, 200, 1000, 5000} evidences the bounded-type contrast on
    that range -- it is not, and cannot be, a proof of global boundedness.
    """

    def worst(step_deg: float) -> float:
        return max(
            n * star_discrepancy(orbit(n, step_deg)) / math.log(n)
            for n in (50, 200, 1000, 5000)
        )

    assert worst(GOLDEN_ANGLE_DEG) < 0.6
    assert worst(PI_STEP_DEG) > 3.0


@pytest.mark.parametrize(
    "step_deg", [GOLDEN_ANGLE_DEG, SILVER_STEP_DEG, RATIONAL_STEP_DEG]
)
def test_three_distance_theorem_holds(step_deg):
    """At most three distinct gap lengths -- structural proof it is a rotation."""

    assert len(gap_lengths(orbit(1000, step_deg))) <= 3


def test_rational_step_recurs_and_irrational_step_does_not():
    """A decimal-rational step is short-period; the golden step is not.

    ``137.5`` deg is 55/144 of a turn, so the orbit closes after 144 steps
    and the float orbit tracks that to rounding. The golden step never
    returns near its start at the same lag. This is the confound guard: a
    rounded "golden angle" literal can be a 144-periodic signal.
    """

    assert orbit_period(RATIONAL_STEP_DEG) == 144
    rational = QuasiperiodicMisalignmentFixture(
        amplitude_rad=0.3, step_period_s=1.0, step_deg=RATIONAL_STEP_DEG
    )
    golden = QuasiperiodicMisalignmentFixture(
        amplitude_rad=0.3, step_period_s=1.0
    )
    rational_drift = max(
        abs(rational.orbit_position(n) - rational.orbit_position(n + 144))
        for n in range(500)
    )
    golden_drift = min(
        abs(golden.orbit_position(n) - golden.orbit_position(n + 144))
        for n in range(500)
    )
    assert rational_drift < 1e-12
    assert golden_drift > 1e-3


def test_run_length_stays_below_float_closure():
    """Any run this fixture is used for must be far short of exact closure."""

    assert orbit_period(GOLDEN_ANGLE_DEG) > 10**12


# ---------------------------------------------------------------------------
# Aliasing -- evidence for the ADR-0003 amendment
# ---------------------------------------------------------------------------


def test_coarse_grid_biases_a_fully_deterministic_signal():
    """Determinism does not confer tabulation safety.

    ADR-0003 §4 row 1 currently licenses tabulation for the
    deterministic-exogenous tier ("Tabulate freely"), with smoothness only
    in the rationale. This signal is deterministic, bounded, smooth, and
    RNG-free, and a coarse grid still biases its mean by double-digit
    percent, because the misalignment mapping is nonlinear and a
    Fibonacci-denominator stride resonates with the rotation number. The
    correct criterion is bandwidth relative to the evaluation grid.
    """

    amplitude = 0.3
    fine_mean = _mean_error(GOLDEN_ANGLE_DEG, amplitude, 4000)
    bias = aliasing_bias(
        amplitude, GOLDEN_ANGLE_DEG, coarse_stride=55, n_samples=4000
    )
    assert abs(bias / fine_mean) > 0.10
    assert bias < 0.0


def test_aliasing_bias_grows_with_resonant_stride():
    """Bias is monotone in stride resonance, not noise."""

    amplitude = 0.3
    magnitudes = [
        abs(
            aliasing_bias(
                amplitude, GOLDEN_ANGLE_DEG, coarse_stride=s, n_samples=4000
            )
        )
        for s in (13, 21, 55)
    ]
    assert magnitudes == sorted(magnitudes)
