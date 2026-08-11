"""Tests for TWIN-1 (docs/TWIN_1_PLAN.md, v2 approved, Sec4 obligations 1-10).

Covers the reference linear-Gaussian Kalman twin (``LinearGaussianTwin``,
``TwinTrace``) and the innovation whiteness/NIS diagnostic
(``innovation_diagnostic``, ``DiagnosticCalibration``,
``InnovationDiagnosticResult``) plus the four telemetry generators, all in
``qkd.twin``. Obligation 10 (full existing suite green) is not a separate
pytest function -- it is exercised, and reported, by the same ``pytest``
invocation that runs the whole suite alongside this file.

Statistical tolerance bands (obligations 2, 4, 5) are exact-binomial /
exact-convolution constructions, computed here from ``math.comb`` with no
SciPy, derived analytically *before* any ensemble is drawn -- see
``_exact_binomial_two_sided_band`` and ``_exact_two_sample_diff_band``
below, and the module-level constants that call them. The plan's own
predeclared [3, 19] band (Sec3, n_runs=200, alpha=0.05) is reproduced by
this same construction and pinned by a regression assertion at import time
(``NULL_BAND_N200 == (3, 19)``), rather than trusted blindly.

Every ensemble in this file is fixed-seed deterministic: one recorded
master seed (``MASTER_SEED``, plan Sec3) is expanded into disjoint
``numpy.random.SeedSequence`` spawn subtrees, one per named "purpose"
(honest ensemble, same-law-synthesis ensemble, wrong-dynamics power,
memoryless-mismatch power x2, determinism), so no two runs in this file --
across obligations or within one ensemble -- ever share a draw stream, and
every assertion below is an exact rerun rather than flaky sampling.
"""

from __future__ import annotations

import dataclasses
import math

import numpy as np
import pytest

import qkd.twin as twin_module
from qkd.twin import (
    DiagnosticCalibration,
    InnovationDiagnosticResult,
    LinearGaussianTwin,
    TwinTrace,
    generate_honest_telemetry,
    generate_memoryless_covariance_mismatch_telemetry,
    generate_same_law_synthesis_telemetry,
    generate_wrong_dynamics_marginal_matched_telemetry,
    innovation_diagnostic,
    stationary_prior,
    stationary_variance,
)

# ---------------------------------------------------------------------------
# Sec3 predeclared statistical parameters
# ---------------------------------------------------------------------------

ALPHA = 0.05
LAGS = 20
N_STEPS = 2000

NULL_ENSEMBLE_RUNS = 200
POWER_ENSEMBLE_RUNS = 50
POWER_LOWER_BOUND = 0.9

MASTER_SEED = 20260811


def _exact_binomial_two_sided_band(
    n_trials: int, p: float, *, tail_prob: float = 0.005
) -> tuple[int, int]:
    """Smallest ``[lo, hi]`` with ``P(K<lo) <= tail_prob`` and ``P(K>hi) <= tail_prob``
    for ``K ~ Binomial(n_trials, p)`` -- an exact (``math.comb``-based, no SciPy)
    two-one-sided-0.5%-tails construction, i.e. a 99% two-sided acceptance
    band. This is a pure function of ``(n_trials, p)``, evaluated once at
    import time, before any ensemble is drawn -- never fit to a realized
    sample.
    """
    pmf = [math.comb(n_trials, k) * p**k * (1.0 - p) ** (n_trials - k) for k in range(n_trials + 1)]
    cdf = 0.0
    lo = None
    for k, pk in enumerate(pmf):
        prev_cdf = cdf
        cdf += pk
        if prev_cdf <= tail_prob < cdf:
            lo = k
            break
    tail = 0.0
    hi = None
    for k in range(n_trials, -1, -1):
        prev_tail = tail
        tail += pmf[k]
        if prev_tail <= tail_prob < tail:
            hi = k
            break
    return lo, hi


def _exact_two_sample_diff_band(
    n_trials: int, p: float, *, tail_prob: float = 0.005
) -> tuple[int, int]:
    """Exact 99% two-sided band on the *difference* of two independent
    ``Binomial(n_trials, p)`` counts (obligation 4's two-sample tolerance,
    plan Sec3: "case-4-vs-honest comparison by two-sample tolerance
    (difference in rejection counts within the predeclared band)"). Built
    the same way as :func:`_exact_binomial_two_sided_band` -- two 0.5%
    tails -- on the convolved difference distribution of two independent
    draws from the same binomial law.
    """
    pmf = [math.comb(n_trials, k) * p**k * (1.0 - p) ** (n_trials - k) for k in range(n_trials + 1)]
    diff_pmf: dict[int, float] = {}
    for i, pi in enumerate(pmf):
        if pi <= 0.0:
            continue
        for j, pj in enumerate(pmf):
            diff_pmf[i - j] = diff_pmf.get(i - j, 0.0) + pi * pj
    diffs = sorted(diff_pmf)
    cdf = 0.0
    lo = None
    for d in diffs:
        prev_cdf = cdf
        cdf += diff_pmf[d]
        if prev_cdf <= tail_prob < cdf:
            lo = d
            break
    tail = 0.0
    hi = None
    for d in reversed(diffs):
        prev_tail = tail
        tail += diff_pmf[d]
        if prev_tail <= tail_prob < tail:
            hi = d
            break
    return lo, hi


# Plan Sec3's own predeclared band, reproduced by the construction above and
# pinned by a regression check (not merely trusted from the plan text).
NULL_BAND_N200 = _exact_binomial_two_sided_band(NULL_ENSEMBLE_RUNS, ALPHA)
assert NULL_BAND_N200 == (3, 19), (
    "NULL_BAND_N200 must reproduce the plan Sec3 predeclared band exactly."
)

# Obligation 5's n_runs=50 null-rate check (whiteness must stay at the null
# rate under the memoryless-mismatch construction -- only NIS should have
# power there): same exact-binomial-tail method, recomputed at n_trials=50.
NULL_BAND_N50 = _exact_binomial_two_sided_band(POWER_ENSEMBLE_RUNS, ALPHA)

# Obligation 4's two-sample tolerance on (same-law-synthesis count - honest
# count), both ~ Binomial(200, 0.05) independently.
TWO_SAMPLE_DIFF_BAND = _exact_two_sample_diff_band(NULL_ENSEMBLE_RUNS, ALPHA)


# ---------------------------------------------------------------------------
# Nominal model parameters (fixed before any seed is chosen)
# ---------------------------------------------------------------------------

# Honest / same-law-synthesis / wrong-dynamics nominal AR(1)+noise model.
NOMINAL_A = 0.9
NOMINAL_Q = 1.0
NOMINAL_R = 0.5
WRONG_B = 0.2  # plan Sec3: "a = 0.9 vs b = 0.2 at N = 2000"

# Memoryless (a=0) model for the covariance-mismatch construction.
MEMORYLESS_Q = 1.0
MEMORYLESS_R = 0.5
MEMORYLESS_RATIO = 2.0  # plan Sec3: "R'/r = 2 both directions"


def _nominal_twin() -> LinearGaussianTwin:
    return LinearGaussianTwin(F=[[NOMINAL_A]], H=[[1.0]], Q=[[NOMINAL_Q]], R=[[NOMINAL_R]])


def _nominal_prior():
    return stationary_prior(stationary_variance(NOMINAL_A, NOMINAL_Q))


def _memoryless_twin() -> LinearGaussianTwin:
    return LinearGaussianTwin(F=[[0.0]], H=[[1.0]], Q=[[MEMORYLESS_Q]], R=[[MEMORYLESS_R]])


def _memoryless_prior():
    return stationary_prior(MEMORYLESS_Q)  # a=0 => P_x = q / (1 - 0**2) = q


def _default_calibration() -> DiagnosticCalibration:
    return DiagnosticCalibration(alpha=ALPHA, lags=LAGS, effective_n=N_STEPS, measurement_dim=1)


# ---------------------------------------------------------------------------
# One recorded master seed deriving every ensemble's seeds (plan Sec3)
# ---------------------------------------------------------------------------

_PURPOSE_ORDER = (
    "honest",
    "same_law_synthesis",
    "wrong_dynamics_power",
    "memoryless_high",
    "memoryless_low",
    "determinism",
)
_PURPOSE_SEED_SEQUENCES = dict(
    zip(_PURPOSE_ORDER, np.random.SeedSequence(MASTER_SEED).spawn(len(_PURPOSE_ORDER)))
)


def _ensemble_rngs(purpose: str, n_runs: int) -> list[np.random.Generator]:
    """``n_runs`` independent Generators, deterministically derived from the
    one recorded ``MASTER_SEED`` via ``numpy``'s recommended
    ``SeedSequence.spawn`` tree -- every purpose gets its own disjoint
    spawn subtree, and within a purpose every run gets its own child seed.
    """
    return [np.random.default_rng(s) for s in _PURPOSE_SEED_SEQUENCES[purpose].spawn(n_runs)]


# ---------------------------------------------------------------------------
# 1. Scalar hand calculation (predict/innovation/S/gain/state/Joseph P+);
#    separate ill-conditioned case for symmetry/PSD handling
# ---------------------------------------------------------------------------


def test_1_scalar_hand_calculation_matches_general_and_fast_paths():
    f, h, q, r = 0.6, 1.0, 0.4, 0.3
    x0_value, p0_value = 0.2, 0.5
    z1 = 0.9

    # Independent hand calculation (plan Sec4 obligation 1), computed with
    # plain ``math`` rather than by calling ``qkd.twin`` at all.
    x_pred = f * x0_value
    p_pred = f * f * p0_value + q
    nu_expected = z1 - h * x_pred
    s_expected = h * h * p_pred + r
    gain_expected = (p_pred * h) / s_expected
    x_post_expected = x_pred + gain_expected * nu_expected
    i_minus_kh = 1.0 - gain_expected * h
    p_post_expected = i_minus_kh * i_minus_kh * p_pred + gain_expected * gain_expected * r

    twin = LinearGaussianTwin(F=[[f]], H=[[h]], Q=[[q]], R=[[r]])
    observations = np.array([[z1]])
    x0 = np.array([x0_value])
    p0 = np.array([[p0_value]])

    # Public dispatch (hits the scalar fast path at n=m=1)...
    trace_fast = twin.run(observations, x0, p0)
    # ...and the dimension-generic branch directly, so the hand calculation
    # verifies *both* code paths, not only the fast one.
    trace_general = twin._run_general(observations, x0.astype(float), p0.astype(float))

    for trace in (trace_fast, trace_general):
        assert trace.innovations[0, 0] == pytest.approx(nu_expected, abs=1e-12)
        assert trace.innovation_covariances[0, 0, 0] == pytest.approx(s_expected, abs=1e-12)
        assert trace.filtered_state[0, 0] == pytest.approx(x_post_expected, abs=1e-12)
        assert trace.filtered_covariance[0, 0, 0] == pytest.approx(p_post_expected, abs=1e-12)


def test_1_ill_conditioned_inputs_raise_without_pretending_joseph_form_fixes_them():
    # Non-symmetric Q: Joseph form is not asked to "average out" an invalid
    # input -- construction raises before any filtering happens.
    with pytest.raises(ValueError, match="symmetric"):
        LinearGaussianTwin(F=np.eye(2), H=[[1.0, 0.0]], Q=[[1.0, 0.5], [0.0, 1.0]], R=[[1.0]])

    # An indefinite (not merely singular) prior covariance fed directly to
    # run(): the Joseph-form update does not guarantee a PSD result from an
    # invalid prior, and does not attempt to -- validation raises at run()
    # entry, before any predict/update arithmetic runs.
    twin = LinearGaussianTwin(F=np.eye(2) * 0.5, H=np.eye(2), Q=np.eye(2), R=np.eye(2))
    indefinite_p0 = [[1.0, 2.0], [2.0, 1.0]]  # eigenvalues {3, -1}: indefinite
    with pytest.raises(ValueError, match="positive semi-definite"):
        twin.run(np.zeros((3, 2)), np.zeros(2), indefinite_p0)


# ---------------------------------------------------------------------------
# 2 & 4. Honest / same-law-synthesis ensembles: null rejection rates within
#    the predeclared binomial band; case-4-vs-honest two-sample tolerance
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def honest_ensemble_results() -> list[InnovationDiagnosticResult]:
    twin = _nominal_twin()
    x0, p0 = _nominal_prior()
    calibration = _default_calibration()
    results = []
    for rng in _ensemble_rngs("honest", NULL_ENSEMBLE_RUNS):
        obs = generate_honest_telemetry(rng, a=NOMINAL_A, q=NOMINAL_Q, r=NOMINAL_R, n_steps=N_STEPS)
        results.append(innovation_diagnostic(twin.run(obs, x0, p0), calibration))
    return results


@pytest.fixture(scope="module")
def same_law_synthesis_results() -> list[InnovationDiagnosticResult]:
    twin = _nominal_twin()
    x0, p0 = _nominal_prior()
    calibration = _default_calibration()
    results = []
    for rng in _ensemble_rngs("same_law_synthesis", NULL_ENSEMBLE_RUNS):
        obs = generate_same_law_synthesis_telemetry(
            rng, a=NOMINAL_A, q=NOMINAL_Q, r=NOMINAL_R, n_steps=N_STEPS
        )
        results.append(innovation_diagnostic(twin.run(obs, x0, p0), calibration))
    return results


def test_2_honest_stationary_ensemble_null_rejection_rates_within_binomial_band(
    honest_ensemble_results,
):
    whiteness_rejections = sum(not r.whiteness_pass for r in honest_ensemble_results)
    nis_rejections = sum(not r.nis_pass for r in honest_ensemble_results)

    lo, hi = NULL_BAND_N200
    assert lo <= whiteness_rejections <= hi, (
        f"whiteness rejected {whiteness_rejections}/{NULL_ENSEMBLE_RUNS} honest runs, "
        f"outside the predeclared exact-binomial 99% band [{lo}, {hi}]."
    )
    assert lo <= nis_rejections <= hi, (
        f"NIS rejected {nis_rejections}/{NULL_ENSEMBLE_RUNS} honest runs, "
        f"outside the predeclared exact-binomial 99% band [{lo}, {hi}]."
    )
    # A "detector" that never rejects at the null would also pass a naive
    # all-runs-succeed check -- assert the honest ensemble contains at
    # least one individually-rejected run (plan Sec1: individual seeded
    # runs are *permitted*, and expected, to fail at rate ~= alpha).
    assert whiteness_rejections > 0 or nis_rejections > 0


def test_4_same_law_synthesis_matches_honest_ensemble_within_two_sample_tolerance(
    honest_ensemble_results, same_law_synthesis_results
):
    honest_whiteness = sum(not r.whiteness_pass for r in honest_ensemble_results)
    honest_nis = sum(not r.nis_pass for r in honest_ensemble_results)
    synthesis_whiteness = sum(not r.whiteness_pass for r in same_law_synthesis_results)
    synthesis_nis = sum(not r.nis_pass for r in same_law_synthesis_results)

    lo, hi = TWO_SAMPLE_DIFF_BAND
    whiteness_diff = synthesis_whiteness - honest_whiteness
    nis_diff = synthesis_nis - honest_nis
    assert lo <= whiteness_diff <= hi, (
        f"same-law-synthesis whiteness rejections ({synthesis_whiteness}) vs honest "
        f"({honest_whiteness}): diff {whiteness_diff} outside the predeclared "
        f"two-sample band [{lo}, {hi}]."
    )
    assert lo <= nis_diff <= hi, (
        f"same-law-synthesis NIS rejections ({synthesis_nis}) vs honest "
        f"({honest_nis}): diff {nis_diff} outside the predeclared two-sample band [{lo}, {hi}]."
    )
    # Plan Sec4 obligation 4, verbatim: a single run is *not* required to
    # pass. This test makes no per-run pairing or per-run assertion
    # anywhere -- only the two ensemble-level rejection counts above.


# ---------------------------------------------------------------------------
# 3. Wrong-dynamics marginal-matched construction: analytic marginal
#    equality; whiteness empirical power >= predeclared floor
# ---------------------------------------------------------------------------


def test_3_wrong_dynamics_marginal_matched_analytic_equality_and_whiteness_power():
    p_x = stationary_variance(NOMINAL_A, NOMINAL_Q)
    q_prime = p_x * (1.0 - WRONG_B**2)
    # Analytic stationary marginal equality (plan Sec2.3 item 2, R5): the
    # b-process's own stationary variance q'/(1-b^2) collapses algebraically
    # to p_x by construction -- asserted directly, not tuned numerically.
    assert q_prime / (1.0 - WRONG_B**2) == pytest.approx(p_x, rel=0.0, abs=1e-12)

    twin = _nominal_twin()
    x0, p0 = _nominal_prior()
    calibration = _default_calibration()

    rejections = 0
    for rng in _ensemble_rngs("wrong_dynamics_power", POWER_ENSEMBLE_RUNS):
        obs = generate_wrong_dynamics_marginal_matched_telemetry(
            rng, a=NOMINAL_A, q=NOMINAL_Q, b=WRONG_B, r=NOMINAL_R, n_steps=N_STEPS
        )
        result = innovation_diagnostic(twin.run(obs, x0, p0), calibration)
        if not result.whiteness_pass:
            rejections += 1

    empirical_power = rejections / POWER_ENSEMBLE_RUNS
    # Predeclared conservative floor (plan Sec3): a=0.9 vs b=0.2 at N=2000 is
    # an overwhelming analytic separation -- expected power ~= 1; >= 0.9 is
    # a floor, not an estimate.
    assert empirical_power >= POWER_LOWER_BOUND, (
        f"wrong-dynamics whiteness power {empirical_power} "
        f"({rejections}/{POWER_ENSEMBLE_RUNS}) below the predeclared floor {POWER_LOWER_BOUND}."
    )


# ---------------------------------------------------------------------------
# 5. Memoryless covariance mismatch: standardized innovations white at the
#    null rate; two-sided NIS rejects with power >= floor (both directions)
# ---------------------------------------------------------------------------


def test_5_memoryless_covariance_mismatch_white_but_nis_rejects_both_directions():
    twin = _memoryless_twin()
    x0, p0 = _memoryless_prior()
    calibration = _default_calibration()

    for direction, r_prime, purpose in (
        ("R' > r", MEMORYLESS_R * MEMORYLESS_RATIO, "memoryless_high"),
        ("R' < r", MEMORYLESS_R / MEMORYLESS_RATIO, "memoryless_low"),
    ):
        whiteness_rejections = 0
        nis_rejections = 0
        for rng in _ensemble_rngs(purpose, POWER_ENSEMBLE_RUNS):
            obs = generate_memoryless_covariance_mismatch_telemetry(
                rng, q=MEMORYLESS_Q, r_prime=r_prime, n_steps=N_STEPS
            )
            result = innovation_diagnostic(twin.run(obs, x0, p0), calibration)
            if not result.whiteness_pass:
                whiteness_rejections += 1
            if not result.nis_pass:
                nis_rejections += 1

        lo, hi = NULL_BAND_N50
        assert lo <= whiteness_rejections <= hi, (
            f"[{direction}] whiteness rejected {whiteness_rejections}/{POWER_ENSEMBLE_RUNS} "
            f"memoryless-mismatch runs -- dynamics are correct (a=0 both sides), so this "
            f"should stay at the null rate; outside band [{lo}, {hi}]."
        )
        empirical_power = nis_rejections / POWER_ENSEMBLE_RUNS
        assert empirical_power >= POWER_LOWER_BOUND, (
            f"[{direction}] NIS power {empirical_power} ({nis_rejections}/{POWER_ENSEMBLE_RUNS}) "
            f"below the predeclared floor {POWER_LOWER_BOUND}."
        )


# ---------------------------------------------------------------------------
# 6. Calibration contract: unsupported configurations fail loudly; recorded
#    df and critical values match an independent oracle
# ---------------------------------------------------------------------------


def _independent_chi2_ppf(target_p: float, df: int) -> float:
    """Independent regularized-incomplete-gamma bisection oracle.

    Deliberately *not* derived by importing anything from ``qkd.twin`` --
    a fresh implementation (Numerical-Recipes-style series/continued
    fraction on ``math.lgamma``), matching the LINK-4/5 "independent
    hand-computed oracle" pattern, used only to cross-check the shipped
    calibration table's critical values.
    """

    def regularized_lower_gamma(a: float, x: float) -> float:
        if x == 0.0:
            return 0.0
        gln = math.lgamma(a)
        if x < a + 1.0:
            ap = a
            summ = 1.0 / a
            delta = summ
            for _ in range(1000):
                ap += 1.0
                delta *= x / ap
                summ += delta
                if abs(delta) < abs(summ) * 1e-16:
                    break
            return summ * math.exp(-x + a * math.log(x) - gln)
        tiny = 1e-300
        b = x + 1.0 - a
        c = 1.0 / tiny
        d = 1.0 / b
        h = d
        for i in range(1, 1000):
            an = -i * (i - a)
            b += 2.0
            d = an * d + b
            if abs(d) < tiny:
                d = tiny
            c = b + an / c
            if abs(c) < tiny:
                c = tiny
            d = 1.0 / d
            delta = d * c
            h *= delta
            if abs(delta - 1.0) < 1e-16:
                break
        q = math.exp(-x + a * math.log(x) - gln) * h
        return 1.0 - q

    def chi2_cdf(x: float, df_: int) -> float:
        return regularized_lower_gamma(df_ / 2.0, x / 2.0)

    lo, hi = 0.0, df * 10.0 + 1000.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if chi2_cdf(mid, df) < target_p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def test_6_calibration_contract_supported_configuration_matches_independent_oracle():
    calibration = _default_calibration()
    assert calibration.alpha == ALPHA
    assert calibration.lags == LAGS
    assert calibration.effective_n == N_STEPS
    assert calibration.measurement_dim == 1

    expected_ljung_box_upper = _independent_chi2_ppf(0.95, LAGS)
    expected_nis_lower = _independent_chi2_ppf(0.025, N_STEPS)
    expected_nis_upper = _independent_chi2_ppf(0.975, N_STEPS)

    assert calibration.critical_values["ljung_box_upper"] == pytest.approx(
        expected_ljung_box_upper, abs=1e-6
    )
    assert calibration.critical_values["nis_lower"] == pytest.approx(expected_nis_lower, abs=1e-6)
    assert calibration.critical_values["nis_upper"] == pytest.approx(expected_nis_upper, abs=1e-6)


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(alpha=0.01, lags=LAGS, effective_n=N_STEPS, measurement_dim=1),
        dict(alpha=ALPHA, lags=10, effective_n=N_STEPS, measurement_dim=1),
        dict(alpha=ALPHA, lags=LAGS, effective_n=1000, measurement_dim=1),
        dict(alpha=ALPHA, lags=LAGS, effective_n=N_STEPS, measurement_dim=2),
    ],
)
def test_6_unsupported_calibration_configurations_raise(kwargs):
    with pytest.raises(ValueError, match="Unsupported diagnostic calibration"):
        DiagnosticCalibration(**kwargs)


def test_6_recorded_df_and_critical_values_match_the_calibration_object(honest_ensemble_results):
    result = honest_ensemble_results[0]
    assert result.lags == LAGS
    assert result.effective_n == N_STEPS
    assert result.whiteness_threshold == result.calibration.critical_values["ljung_box_upper"]
    assert result.nis_lower_threshold == result.calibration.critical_values["nis_lower"]
    assert result.nis_upper_threshold == result.calibration.critical_values["nis_upper"]


# ---------------------------------------------------------------------------
# 7. Determinism: bit-identical result fields; no state retained between
#    batch calls
# ---------------------------------------------------------------------------


def test_7_determinism_bit_identical_and_no_state_between_batch_calls():
    twin = _nominal_twin()
    x0, p0 = _nominal_prior()
    calibration = _default_calibration()
    rng_a, rng_b = _ensemble_rngs("determinism", 2)

    obs_a = generate_honest_telemetry(rng_a, a=NOMINAL_A, q=NOMINAL_Q, r=NOMINAL_R, n_steps=N_STEPS)

    trace_1 = twin.run(obs_a, x0, p0)
    trace_2 = twin.run(obs_a, x0, p0)
    assert np.array_equal(trace_1.innovations, trace_2.innovations)
    assert np.array_equal(trace_1.innovation_covariances, trace_2.innovation_covariances)
    assert np.array_equal(trace_1.filtered_state, trace_2.filtered_state)
    assert np.array_equal(trace_1.filtered_covariance, trace_2.filtered_covariance)

    result_1 = innovation_diagnostic(trace_1, calibration)
    result_2 = innovation_diagnostic(trace_2, calibration)
    assert result_1 == result_2

    # No state retained between batch calls: running the same twin instance
    # on a second, unrelated observation sequence produces exactly what a
    # *fresh* instance produces on that sequence alone.
    obs_b = generate_honest_telemetry(rng_b, a=NOMINAL_A, q=NOMINAL_Q, r=NOMINAL_R, n_steps=200)
    trace_b_after_a = twin.run(obs_b, x0, p0)
    trace_b_fresh = _nominal_twin().run(obs_b, x0, p0)
    assert np.array_equal(trace_b_after_a.innovations, trace_b_fresh.innovations)
    assert np.array_equal(trace_b_after_a.filtered_covariance, trace_b_fresh.filtered_covariance)

    # Differing nominal seeds are handled statistically (obligation 2's
    # ensemble band), never required to individually pass -- nothing here
    # re-asserts single-run success beyond the specific fixed inputs above.


# ---------------------------------------------------------------------------
# 8. Validation: dimension, symmetry, PSD, finite-value, lag-length,
#    empty-input, and singular-S failures explicit
# ---------------------------------------------------------------------------


def test_8_dimension_mismatch_raises():
    with pytest.raises(ValueError):
        LinearGaussianTwin(F=np.eye(2), H=[[1.0, 0.0, 0.0]], Q=np.eye(2), R=[[1.0]])
    with pytest.raises(ValueError):
        LinearGaussianTwin(F=np.eye(2), H=[[1.0, 0.0]], Q=np.eye(3), R=[[1.0]])
    with pytest.raises(ValueError):
        LinearGaussianTwin(F=np.eye(2), H=[[1.0, 0.0]], Q=np.eye(2), R=np.eye(2))
    twin = _nominal_twin()
    x0, p0 = _nominal_prior()
    with pytest.raises(ValueError):
        twin.run(np.zeros((5, 2)), x0, p0)  # observations column count wrong
    with pytest.raises(ValueError):
        twin.run(np.zeros((5, 1)), np.zeros(2), p0)  # x0 length wrong


def test_8_symmetry_validation_raises():
    with pytest.raises(ValueError, match="symmetric"):
        LinearGaussianTwin(F=np.eye(2), H=[[1.0, 0.0]], Q=[[1.0, 0.5], [0.0, 1.0]], R=[[1.0]])
    with pytest.raises(ValueError, match="symmetric"):
        LinearGaussianTwin(F=np.eye(2), H=np.eye(2), Q=np.eye(2), R=[[1.0, 0.5], [0.0, 1.0]])
    twin = LinearGaussianTwin(F=np.eye(2) * 0.5, H=np.eye(2), Q=np.eye(2), R=np.eye(2))
    with pytest.raises(ValueError, match="symmetric"):
        twin.run(np.zeros((3, 2)), np.zeros(2), [[1.0, 0.5], [0.0, 1.0]])


def test_8_psd_validation_raises_at_construction_and_at_run():
    with pytest.raises(ValueError, match="positive semi-definite"):
        LinearGaussianTwin(F=[[1.0]], H=[[1.0]], Q=[[-1.0]], R=[[1.0]])
    with pytest.raises(ValueError, match="positive semi-definite"):
        LinearGaussianTwin(F=[[1.0]], H=[[1.0]], Q=[[1.0]], R=[[-1.0]])
    twin = LinearGaussianTwin(F=np.eye(2) * 0.5, H=np.eye(2), Q=np.eye(2), R=np.eye(2))
    indefinite_p0 = [[1.0, 2.0], [2.0, 1.0]]  # eigenvalues {3, -1}: indefinite
    with pytest.raises(ValueError, match="positive semi-definite"):
        twin.run(np.zeros((3, 2)), np.zeros(2), indefinite_p0)


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
def test_8_finite_value_validation_raises(bad_value):
    with pytest.raises(ValueError, match="finite"):
        LinearGaussianTwin(F=[[bad_value]], H=[[1.0]], Q=[[1.0]], R=[[1.0]])
    twin = _nominal_twin()
    x0, p0 = _nominal_prior()
    with pytest.raises(ValueError, match="finite"):
        twin.run([[bad_value]], x0, p0)
    with pytest.raises(ValueError, match="finite"):
        twin.run([[0.0]], [bad_value], p0)
    with pytest.raises(ValueError, match="finite"):
        twin.run([[0.0]], x0, [[bad_value]])


def test_8_empty_observations_raises():
    twin = _nominal_twin()
    x0, p0 = _nominal_prior()
    with pytest.raises(ValueError, match="non-empty"):
        twin.run(np.empty((0, 1)), x0, p0)


def test_8_singular_innovation_covariance_raises_scalar_and_general_paths():
    scalar_twin = LinearGaussianTwin(F=[[0.5]], H=[[0.0]], Q=[[1.0]], R=[[0.0]])
    with pytest.raises(ValueError, match="not numerically positive definite"):
        scalar_twin.run([[0.0]], [0.0], [[1.0]])

    general_twin = LinearGaussianTwin(F=np.eye(2) * 0.5, H=[[0.0, 0.0]], Q=np.eye(2), R=[[0.0]])
    with pytest.raises(ValueError, match="not numerically positive definite"):
        general_twin.run(np.zeros((1, 1)), np.zeros(2), np.eye(2))


def test_8_lag_length_validation_raises():
    z = np.zeros(5)
    with pytest.raises(ValueError, match="lags"):
        twin_module._ljung_box_statistic(z, 5)  # lags must be < n
    with pytest.raises(ValueError, match="lags"):
        twin_module._ljung_box_statistic(z, 0)


# ---------------------------------------------------------------------------
# 9. No verdict field; docstrings carry the Sec1 claim-scope language
# ---------------------------------------------------------------------------


def test_9_result_object_has_no_verdict_field():
    field_names = {f.name for f in dataclasses.fields(InnovationDiagnosticResult)}
    forbidden_substrings = ("verdict", "secure", "authentic", "matched", "aggregate", "overall")
    for name in field_names:
        lowered = name.lower()
        assert not any(bad in lowered for bad in forbidden_substrings), (
            f"InnovationDiagnosticResult.{name} looks like an aggregate/verdict field."
        )
    # Per-test fields present and reported separately, never combined.
    assert {"whiteness_pass", "nis_pass", "alpha", "lags", "effective_n", "calibration"} <= field_names


def test_9_module_docstring_carries_claim_scope_language():
    doc = twin_module.__doc__
    assert doc is not None
    assert "necessary but not sufficient" in doc
    assert "same-law synthesis" in doc
    assert 'never "replay"' in doc
    assert "ensemble statement" in doc
    assert "no aggregate false-positive-rate claim" in doc
    assert "no aggregate verdict exists" in doc
    assert "QKD security" in doc
    assert "classical telemetry" in doc


def test_9_innovation_diagnostic_docstring_reiterates_necessary_not_sufficient():
    doc = innovation_diagnostic.__doc__
    assert doc is not None
    assert "necessary but not sufficient" in doc
    assert "no aggregate verdict is" in doc and "computed or returned" in doc


# ---------------------------------------------------------------------------
# 10. Existing suite green: reported outside pytest by the invocation that
#     runs the whole suite (this file adds obligations 1-9 above; it does
#     not modify or duplicate any existing test file).
# ---------------------------------------------------------------------------
