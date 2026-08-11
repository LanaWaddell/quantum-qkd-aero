"""Tests for TWIN-2 (docs/TWIN_2_PLAN.md, v2 approved, Sec5 obligations 1-11).

Covers the known-input extension to ``qkd.twin.LinearGaussianTwin.run``
(``control_matrix``/``control_inputs``) and the new ``qkd.twin_watermark``
module: the frozen Sec2 watermarked-process model, the honest/
passive-law-matched-synthesis/replay/perfect-relay generators, the two
information views (passive, privileged), and the probe/innovation
cross-correlation detector (``probe_innovation_cross_correlation``,
``CrossCorrelationCalibration``, ``CrossCorrelationResult``). Obligation 11
(full existing suite green) is not a separate pytest function -- it is
exercised, and reported, by the same ``pytest`` invocation that runs the
whole suite alongside this file; ``tests/test_twin_whiteness.py`` is
untouched by this change.

Statistical tolerance bands (obligations 3, 5, 6, 7) are exact-binomial
constructions, computed here from ``math.comb`` with no SciPy, derived
analytically *before* any ensemble is drawn -- mirroring
``tests/test_twin_whiteness.py``'s ``_exact_binomial_two_sided_band``
(duplicated here rather than imported, keeping this file self-contained
the same way the TWIN-1 test file is).

Every ensemble in this file is fixed-seed deterministic: one recorded
master seed (``MASTER_SEED``) is expanded into disjoint
``numpy.random.SeedSequence`` spawn subtrees, one per named "purpose" --
process-noise streams are always disjoint from probe streams (R8/R9), and
"current probe" streams are disjoint from "past probe" (replay) streams.
A second recorded, held-out ``REVIEW_SEED`` (plan Sec2, R6) reruns the core
obligation-7 comparison under an independent seed, distinguishing a
genuinely calibrated result from a seed-fit one.

**Resolved (TWIN-2 v2.1, 2026-08-12, top-tier review):** the v2 plan froze
``g_modest = 0.10`` against a ``D = {1..5}`` chi-square_5 detector and an
obligation-7 floor of ">= 0.9"; those were mutually inconsistent (the
5-lag statistic dilutes the clean lag-1 signal -- population lag-1
correlation ``-g/sqrt(S)`` -- across four near-null lags, raising the
critical value 3.84 -> 11.07, giving only ~0.80 power at g=0.10). The
review verified independently that **passive blindness is gain-independent**
under the ``q_synth`` exact-law-matching construction (passive whiteness/NIS
sit at (12,6)/200 rejections for ALL g in [0.10, 0.25]), so g_modest is a
free knob for the *privileged* power target, not constrained by passive
blindness. The frozen g_modest was corrected 0.10 -> 0.15 (verified
privileged power 0.997 while passive stays fully blind), restoring the
plan's ">= 0.9" obligation on a principle rather than a tune. The lag set
D={1..5} is retained deliberately (robustness to unknown watermark-response
lag structure -- a real detector must not hard-code lag 1).
"""

from __future__ import annotations

import dataclasses
import inspect
import math

import numpy as np
import pytest

import qkd.twin as twin_module
import qkd.twin_watermark as wm_module
from qkd.twin import DiagnosticCalibration, LinearGaussianTwin, TwinTrace, innovation_diagnostic
from qkd.twin_watermark import (
    A,
    ALPHA,
    G_MODEST,
    G_STRONG,
    LAG_SET,
    N_STEPS,
    Q,
    R,
    SIGMA_U2,
    CrossCorrelationCalibration,
    CrossCorrelationResult,
    generate_honest_watermarked_trajectory,
    generate_passive_law_matched_synthesis,
    generate_perfect_relay,
    generate_replay_trajectory,
    passive_twin,
    privileged_twin,
    probe_innovation_cross_correlation,
    q_synth,
    stationary_prior_for,
    stationary_variance_under_probe,
)

# ---------------------------------------------------------------------------
# Sec2/Sec5 predeclared statistical parameters
# ---------------------------------------------------------------------------

NULL_ENSEMBLE_RUNS = 200  # obligations 3, 5, 7 (comparative core)
POWER_ENSEMBLE_RUNS = 50  # obligation 6 (g_strong detection)

STRONG_POWER_FLOOR = 0.9  # plan Sec2/Sec5: predeclared floor, g_strong -- overwhelming separation

# Restored to the plan's obligation-7 floor after correcting g_modest
# 0.10 -> 0.15 (see module docstring). Verified privileged power at
# g_modest=0.15 is ~0.997 across master and held-out review seeds; 0.9 is a
# conservative floor well below that, with passive whiteness/NIS staying at
# their null rate (gain-independent under q_synth exact law matching).
MODEST_POWER_FLOOR = 0.9

DIAGNOSTIC_LAGS = 20  # qkd.twin's predeclared Ljung-Box lag count (reused calibration table entry)

MASTER_SEED = 20260812
REVIEW_SEED = 20260813  # held-out (plan Sec2, R6): distinguishes calibration from seed-fit


def _exact_binomial_two_sided_band(
    n_trials: int, p: float, *, tail_prob: float = 0.005
) -> tuple[int, int]:
    """Smallest ``[lo, hi]`` with ``P(K<lo) <= tail_prob`` and
    ``P(K>hi) <= tail_prob`` for ``K ~ Binomial(n_trials, p)`` -- an exact
    (``math.comb``-based, no SciPy) two-one-sided-0.5%-tails construction,
    i.e. a 99% two-sided acceptance band. Duplicated from
    ``tests/test_twin_whiteness.py`` (kept self-contained rather than
    imported, matching that file's own convention), a pure function of
    ``(n_trials, p)`` evaluated once at import time, before any ensemble is
    drawn -- never fit to a realized sample.
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


NULL_BAND_N200 = _exact_binomial_two_sided_band(NULL_ENSEMBLE_RUNS, ALPHA)
assert NULL_BAND_N200 == (3, 19), "NULL_BAND_N200 must reproduce the plan Sec2 predeclared band exactly."


# ---------------------------------------------------------------------------
# One recorded master seed (+ one held-out review seed) deriving every
# ensemble's disjoint SeedSequence.spawn streams (plan Sec2). Process
# streams are always disjoint from probe streams; "current probe" streams
# (fed to the privileged filter) are always disjoint from "past probe"
# streams (used only inside the replay generator).
# ---------------------------------------------------------------------------

_PURPOSE_ORDER = (
    "honest_modest_process",
    "honest_modest_probe",
    "synthesis_modest_process",
    "replay_modest_process",
    "replay_modest_past_probe",
    "strong_honest_process",
    "strong_honest_probe",
    "strong_synthesis_process",
    "strong_replay_process",
    "strong_replay_past_probe",
    "determinism_process",
    "determinism_probe",
)


def _spawn_tree(seed: int) -> dict:
    return dict(zip(_PURPOSE_ORDER, np.random.SeedSequence(seed).spawn(len(_PURPOSE_ORDER))))


_PURPOSE_SEED_SEQUENCES = _spawn_tree(MASTER_SEED)
_REVIEW_SEED_SEQUENCES = _spawn_tree(REVIEW_SEED)


def _ensemble_rngs(tree: dict, purpose: str, n_runs: int) -> list[np.random.Generator]:
    return [np.random.default_rng(s) for s in tree[purpose].spawn(n_runs)]


def _default_diagnostic_calibration() -> DiagnosticCalibration:
    return DiagnosticCalibration(alpha=ALPHA, lags=DIAGNOSTIC_LAGS, effective_n=N_STEPS, measurement_dim=1)


def _default_crosscorr_calibration() -> CrossCorrelationCalibration:
    return CrossCorrelationCalibration(alpha=ALPHA, lags=LAG_SET, n_steps=N_STEPS, measurement_dim=1)


def _build_modest_ensembles(tree: dict, n_runs: int):
    """Build the shared g_modest ensembles (plan Sec5 obligations 3/4/5/7):
    ``honest_pairs`` (observations, realized-current-probe) and
    ``synthesis_observations``/``replay_observations`` (no probe exposed),
    all n_runs long, all at ``g = G_MODEST``. This is the "same attack
    paths" construction obligation 7 requires: for run ``i``, the *same*
    realized current probe ``honest_pairs[i][1]`` is later fed to the
    privileged view when it examines ``synthesis_observations[i]`` -- the
    passive view never sees it at all.
    """
    honest_pairs = []
    for rng_process, rng_probe in zip(
        _ensemble_rngs(tree, "honest_modest_process", n_runs),
        _ensemble_rngs(tree, "honest_modest_probe", n_runs),
    ):
        honest_pairs.append(
            generate_honest_watermarked_trajectory(rng_process, rng_probe, g=G_MODEST, n_steps=N_STEPS)
        )

    synthesis_observations = [
        generate_passive_law_matched_synthesis(rng, g=G_MODEST, n_steps=N_STEPS)
        for rng in _ensemble_rngs(tree, "synthesis_modest_process", n_runs)
    ]

    replay_observations = [
        generate_replay_trajectory(rng_process, rng_past_probe, g=G_MODEST, n_steps=N_STEPS)
        for rng_process, rng_past_probe in zip(
            _ensemble_rngs(tree, "replay_modest_process", n_runs),
            _ensemble_rngs(tree, "replay_modest_past_probe", n_runs),
        )
    ]

    return honest_pairs, synthesis_observations, replay_observations


@pytest.fixture(scope="module")
def modest_ensembles():
    return _build_modest_ensembles(_PURPOSE_SEED_SEQUENCES, NULL_ENSEMBLE_RUNS)


@pytest.fixture(scope="module")
def strong_ensembles():
    """g_strong ensembles (plan Sec5 obligation 6), n=50: real current probes
    plus independently-generated synthesis/replay attack observations.
    """
    honest_pairs = []
    for rng_process, rng_probe in zip(
        _ensemble_rngs(_PURPOSE_SEED_SEQUENCES, "strong_honest_process", POWER_ENSEMBLE_RUNS),
        _ensemble_rngs(_PURPOSE_SEED_SEQUENCES, "strong_honest_probe", POWER_ENSEMBLE_RUNS),
    ):
        honest_pairs.append(
            generate_honest_watermarked_trajectory(rng_process, rng_probe, g=G_STRONG, n_steps=N_STEPS)
        )
    synthesis_observations = [
        generate_passive_law_matched_synthesis(rng, g=G_STRONG, n_steps=N_STEPS)
        for rng in _ensemble_rngs(_PURPOSE_SEED_SEQUENCES, "strong_synthesis_process", POWER_ENSEMBLE_RUNS)
    ]
    replay_observations = [
        generate_replay_trajectory(rng_process, rng_past_probe, g=G_STRONG, n_steps=N_STEPS)
        for rng_process, rng_past_probe in zip(
            _ensemble_rngs(_PURPOSE_SEED_SEQUENCES, "strong_replay_process", POWER_ENSEMBLE_RUNS),
            _ensemble_rngs(_PURPOSE_SEED_SEQUENCES, "strong_replay_past_probe", POWER_ENSEMBLE_RUNS),
        )
    ]
    return honest_pairs, synthesis_observations, replay_observations


# ---------------------------------------------------------------------------
# 1. Known-input filter extension: nonzero-input hand calc (first two
#    transitions); control=None bit-identical across every TwinTrace array;
#    scalar and general paths agree on identical known-input semantics.
# ---------------------------------------------------------------------------


def test_1_known_input_hand_calculation_first_two_transitions():
    f, h, q, r, b = 0.7, 1.0, 0.3, 0.2, 0.4
    x0_value, p0_value = 0.1, 0.6
    z0, z1 = 0.5, -0.2
    u0, u1 = 0.9, -0.3  # u1 is unused by a 2-step run (only u0 predicts step k=1)

    # k=0: no control at all (there is no u_{-1}).
    x_pred0 = f * x0_value
    p_pred0 = f * f * p0_value + q
    nu0 = z0 - h * x_pred0
    s0 = h * h * p_pred0 + r
    k0 = (p_pred0 * h) / s0
    x_post0 = x_pred0 + k0 * nu0
    i_minus_kh0 = 1.0 - k0 * h
    p_post0 = i_minus_kh0 * i_minus_kh0 * p_pred0 + k0 * k0 * r

    # k=1: control index k-1=0 predicts observation k=1 -- x_hat^-_1 = f*x_hat_0 + b*u0.
    x_pred1 = f * x_post0 + b * u0
    p_pred1 = f * f * p_post0 + q
    nu1 = z1 - h * x_pred1
    s1 = h * h * p_pred1 + r
    k1 = (p_pred1 * h) / s1
    x_post1 = x_pred1 + k1 * nu1
    i_minus_kh1 = 1.0 - k1 * h
    p_post1 = i_minus_kh1 * i_minus_kh1 * p_pred1 + k1 * k1 * r

    twin = LinearGaussianTwin(F=[[f]], H=[[h]], Q=[[q]], R=[[r]])
    observations = np.array([[z0], [z1]])
    x0 = np.array([x0_value])
    p0 = np.array([[p0_value]])
    control_matrix = np.array([[b]])
    control_inputs = np.array([[u0], [u1]])

    trace_fast = twin.run(
        observations, x0, p0, control_matrix=control_matrix, control_inputs=control_inputs
    )
    trace_general = twin._run_general(
        observations, x0.astype(float), p0.astype(float), control_matrix.astype(float), control_inputs.astype(float)
    )

    for trace in (trace_fast, trace_general):
        assert trace.innovations[0, 0] == pytest.approx(nu0, abs=1e-12)
        assert trace.innovations[1, 0] == pytest.approx(nu1, abs=1e-12)
        assert trace.innovation_covariances[0, 0, 0] == pytest.approx(s0, abs=1e-12)
        assert trace.innovation_covariances[1, 0, 0] == pytest.approx(s1, abs=1e-12)
        assert trace.filtered_state[0, 0] == pytest.approx(x_post0, abs=1e-12)
        assert trace.filtered_state[1, 0] == pytest.approx(x_post1, abs=1e-12)
        assert trace.filtered_covariance[0, 0, 0] == pytest.approx(p_post0, abs=1e-12)
        assert trace.filtered_covariance[1, 0, 0] == pytest.approx(p_post1, abs=1e-12)


def test_1_control_none_bit_identical_across_every_trace_array():
    twin = LinearGaussianTwin(F=[[0.8]], H=[[1.0]], Q=[[0.4]], R=[[0.25]])
    observations = np.array([[0.3], [-0.1], [0.7], [0.05]])
    x0 = np.array([0.0])
    p0 = np.array([[1.5]])

    trace_default = twin.run(observations, x0, p0)
    trace_explicit_none = twin.run(observations, x0, p0, control_matrix=None, control_inputs=None)

    for field_name in ("innovations", "innovation_covariances", "filtered_state", "filtered_covariance"):
        a1 = getattr(trace_default, field_name)
        a2 = getattr(trace_explicit_none, field_name)
        assert np.array_equal(a1, a2), f"{field_name} differs between omitted and explicit-None control."

    # General-path dispatch (n=2 state, control omitted) is likewise
    # untouched -- same as the pre-TWIN-2 arithmetic.
    twin2 = LinearGaussianTwin(F=np.eye(2) * 0.6, H=np.eye(2), Q=np.eye(2) * 0.5, R=np.eye(2) * 0.2)
    obs2 = np.zeros((3, 2))
    obs2[0] = [0.1, -0.2]
    obs2[1] = [0.3, 0.05]
    obs2[2] = [-0.15, 0.2]
    x0_2 = np.zeros(2)
    p0_2 = np.eye(2)
    trace2_default = twin2.run(obs2, x0_2, p0_2)
    trace2_none = twin2.run(obs2, x0_2, p0_2, control_matrix=None, control_inputs=None)
    for field_name in ("innovations", "innovation_covariances", "filtered_state", "filtered_covariance"):
        assert np.array_equal(getattr(trace2_default, field_name), getattr(trace2_none, field_name))


def test_1_control_validation_raises_clearly():
    twin = LinearGaussianTwin(F=[[0.8]], H=[[1.0]], Q=[[0.4]], R=[[0.25]])
    observations = np.zeros((3, 1))
    x0 = np.zeros(1)
    p0 = np.array([[1.0]])

    with pytest.raises(ValueError, match="supplied together or both omitted"):
        twin.run(observations, x0, p0, control_matrix=[[0.5]])
    with pytest.raises(ValueError, match="supplied together or both omitted"):
        twin.run(observations, x0, p0, control_inputs=np.zeros((3, 1)))

    with pytest.raises(ValueError, match=r"\(1, control_dim\)"):
        twin.run(observations, x0, p0, control_matrix=np.zeros((2, 1)), control_inputs=np.zeros((3, 1)))

    with pytest.raises(ValueError, match="at least one control column"):
        twin.run(observations, x0, p0, control_matrix=np.zeros((1, 0)), control_inputs=np.zeros((3, 0)))

    with pytest.raises(ValueError, match="control_inputs must have shape"):
        twin.run(observations, x0, p0, control_matrix=[[0.5]], control_inputs=np.zeros((3, 2)))

    with pytest.raises(ValueError, match="declares 3 steps"):
        twin.run(observations, x0, p0, control_matrix=[[0.5]], control_inputs=np.zeros((2, 1)))

    with pytest.raises(ValueError, match="finite"):
        twin.run(observations, x0, p0, control_matrix=[[float("nan")]], control_inputs=np.zeros((3, 1)))
    with pytest.raises(ValueError, match="finite"):
        twin.run(observations, x0, p0, control_matrix=[[0.5]], control_inputs=np.full((3, 1), float("inf")))


def test_1_scalar_and_general_control_paths_agree_on_random_input():
    # Note: the scalar closed-form path (direct division) and the
    # dimension-generic path (``numpy.linalg.solve``/Cholesky) are
    # mathematically identical known-input semantics but are not
    # guaranteed *bit*-identical over many recursive steps of arbitrary
    # data -- this is a pre-existing TWIN-1 property (confirmed to hold
    # already for the control-free branch, at the ~1 ULP level, via
    # LAPACK vs. direct-division rounding paths), not something the
    # TWIN-2 control extension changes. Tight numerical agreement
    # (``np.allclose`` at essentially machine precision) is the correct
    # bit-identity-in-spirit check here; the exact hand-calculation above
    # separately pins both paths to a closed-form oracle at 1e-12.
    rng = np.random.default_rng(4242)
    f, h, q, r, b = 0.85, 1.0, 0.6, 0.4, -0.3
    n_steps = 30
    observations = rng.normal(size=(n_steps, 1))
    u = rng.normal(size=(n_steps, 1))
    twin = LinearGaussianTwin(F=[[f]], H=[[h]], Q=[[q]], R=[[r]])
    x0 = np.array([0.2])
    p0 = np.array([[0.9]])

    trace_scalar = twin.run(observations, x0, p0, control_matrix=[[b]], control_inputs=u)
    trace_general = twin._run_general(observations, x0.astype(float), p0.astype(float), np.array([[b]]), u)

    for field_name in ("innovations", "innovation_covariances", "filtered_state", "filtered_covariance"):
        assert np.allclose(
            getattr(trace_scalar, field_name), getattr(trace_general, field_name), rtol=1e-12, atol=1e-12
        )


# ---------------------------------------------------------------------------
# 2. Timing/lag oracle: a noise-free limiting construction places the probe
#    response in lag d=1 exactly (zero at d=0, full undecayed g at d=1,
#    geometrically decaying a^(d-1)*g thereafter) -- plain arithmetic, no
#    RNG, no filter machinery (an independent hand-computed oracle).
# ---------------------------------------------------------------------------


def test_2_noise_free_impulse_response_places_probe_response_at_lag_1_exactly():
    a, g = A, G_MODEST
    n = 30
    impulse_index = 12

    # Noise-free limiting construction: q -> 0, r -> 0, so y_k = x_k exactly
    # and x_{k+1} = a*x_k + g*u_k exactly, with u a single unit impulse.
    u = np.zeros(n)
    u[impulse_index] = 1.0
    x = np.zeros(n + 1)
    for k in range(n):
        x[k + 1] = a * x[k] + g * u[k]
    y = x[:n]  # y_k = x_k (r=0)

    j = impulse_index
    # d = 0 (immediate): the probe is not yet visible -- exactly zero.
    assert y[j] == 0.0
    # d = 1: the *first* theoretically visible lag, exactly g -- the full,
    # undecayed coefficient (plan Sec2, R2).
    assert y[j + 1] == pytest.approx(g, abs=1e-15)
    # d = 2..5: geometrically decaying by powers of a thereafter -- present,
    # but strictly smaller than the lag-1 response, and exactly the AR
    # decay of the same lag-1 impulse (not a second, independent signal).
    for d in range(2, 6):
        assert y[j + d] == pytest.approx(a ** (d - 1) * g, abs=1e-15)
        assert abs(y[j + d]) < abs(y[j + 1])

    # Every sample strictly before the impulse (including d<0, i.e. u_k
    # cannot influence y at or before its own index) is exactly zero: the
    # response is placed at lag d=1 exactly, not "eventually, at some lag".
    assert np.all(y[: j + 1] == 0.0)


# ---------------------------------------------------------------------------
# 3. Honest privileged null: probe-aware cross-correlation rejects within
#    [3,19]/200; passive whiteness + NIS also at null (on the same honest
#    g_modest ensemble reused by obligations 4/7).
# ---------------------------------------------------------------------------


def test_3_honest_privileged_null_and_passive_null(modest_ensembles):
    honest_pairs, _synthesis, _replay = modest_ensembles
    x0, p0 = stationary_prior_for(G_MODEST)
    priv = privileged_twin()
    pas = passive_twin(G_MODEST)
    crosscorr_calib = _default_crosscorr_calibration()
    diag_calib = _default_diagnostic_calibration()

    crosscorr_rejections = 0
    whiteness_rejections = 0
    nis_rejections = 0
    for observations, u in honest_pairs:
        priv_trace = priv.run(
            observations, x0, p0, control_matrix=[[G_MODEST]], control_inputs=u.reshape(-1, 1)
        )
        crosscorr_result = probe_innovation_cross_correlation(priv_trace, u, crosscorr_calib)
        if not crosscorr_result.cross_correlation_pass:
            crosscorr_rejections += 1

        pas_trace = pas.run(observations, x0, p0)
        diag_result = innovation_diagnostic(pas_trace, diag_calib)
        if not diag_result.whiteness_pass:
            whiteness_rejections += 1
        if not diag_result.nis_pass:
            nis_rejections += 1

    lo, hi = NULL_BAND_N200
    assert lo <= crosscorr_rejections <= hi, (
        f"privileged cross-correlation rejected {crosscorr_rejections}/{NULL_ENSEMBLE_RUNS} honest "
        f"g_modest runs, outside the predeclared band [{lo}, {hi}]."
    )
    assert lo <= whiteness_rejections <= hi, (
        f"passive whiteness rejected {whiteness_rejections}/{NULL_ENSEMBLE_RUNS} honest runs, "
        f"outside [{lo}, {hi}]."
    )
    assert lo <= nis_rejections <= hi, (
        f"passive NIS rejected {nis_rejections}/{NULL_ENSEMBLE_RUNS} honest runs, outside [{lo}, {hi}]."
    )


# ---------------------------------------------------------------------------
# 4. Passive-law equality: honest watermarked, q_synth synthesis, and past
#    replay have analytically identical unconditional law parameters
#    (asserted on parameters, not sampled).
# ---------------------------------------------------------------------------


def test_4_passive_law_matched_synthesis_and_replay_analytic_parameter_equality():
    g = G_MODEST

    # q_synth(g) is *exactly* the honest process's marginal (probe-
    # marginalized) process-noise variance: Var(g*u_k + w_k) = g^2*sigma_u2
    # + q, algebraically, since u_k and w_k are independent zero-mean.
    honest_marginal_process_variance = Q + g * g * SIGMA_U2
    assert q_synth(g) == pytest.approx(honest_marginal_process_variance, rel=0.0, abs=0.0)

    # Stationary state variance: identical closed form for honest
    # (marginalized), synthesis, and replay (a genuine honest draw) --
    # all P_x = q_synth(g) / (1 - a^2).
    p_x_honest = q_synth(g) / (1.0 - A * A)
    p_x_synth = q_synth(g) / (1.0 - A * A)  # AR(1) with process variance q_synth(g), by definition
    p_x_replay = p_x_honest  # replay is a genuine honest draw -- identical generative process
    assert p_x_honest == p_x_synth == p_x_replay
    assert stationary_variance_under_probe(g) == pytest.approx(p_x_honest, rel=0.0, abs=1e-15)

    # Mean: all three are zero-mean at every k (stationary-initialized at
    # N(0, P_x), zero-mean process/measurement noise, zero-mean probe).
    mean_honest = mean_synth = mean_replay = 0.0
    assert mean_honest == mean_synth == mean_replay

    # Autocovariance kernel: AR(1) stationary autocovariance is
    # gamma(lag) = P_x * a^|lag| for all three, by the same algebra.
    for lag in range(0, 6):
        gamma_honest = p_x_honest * (A**lag)
        gamma_synth = p_x_synth * (A**lag)
        gamma_replay = p_x_replay * (A**lag)
        assert gamma_honest == gamma_synth == gamma_replay

    # Measurement law: y_k = x_k + v_k, v_k ~ N(0, r) identically for all
    # three -- marginal observation variance P_x + r, identical.
    measurement_variance_honest = p_x_honest + R
    measurement_variance_synth = p_x_synth + R
    measurement_variance_replay = p_x_replay + R
    assert measurement_variance_honest == measurement_variance_synth == measurement_variance_replay


# ---------------------------------------------------------------------------
# 5. Passive calibrated blindness: probe-unaware whiteness/NIS reject
#    synthesis and replay at null rates, correct band for n=200.
# ---------------------------------------------------------------------------


def test_5_passive_view_blind_to_synthesis_and_replay_at_null_rate(modest_ensembles):
    _honest, synthesis_observations, replay_observations = modest_ensembles
    x0, p0 = stationary_prior_for(G_MODEST)
    pas = passive_twin(G_MODEST)
    diag_calib = _default_diagnostic_calibration()

    for label, observation_set in (("synthesis", synthesis_observations), ("replay", replay_observations)):
        whiteness_rejections = 0
        nis_rejections = 0
        for observations in observation_set:
            trace = pas.run(observations, x0, p0)
            result = innovation_diagnostic(trace, diag_calib)
            if not result.whiteness_pass:
                whiteness_rejections += 1
            if not result.nis_pass:
                nis_rejections += 1

        lo, hi = NULL_BAND_N200
        assert lo <= whiteness_rejections <= hi, (
            f"[{label}] passive whiteness rejected {whiteness_rejections}/{NULL_ENSEMBLE_RUNS}, "
            f"outside the predeclared null band [{lo}, {hi}] -- the passive view should be blind."
        )
        assert lo <= nis_rejections <= hi, (
            f"[{label}] passive NIS rejected {nis_rejections}/{NULL_ENSEMBLE_RUNS}, "
            f"outside [{lo}, {hi}] -- the passive view should be blind."
        )


# ---------------------------------------------------------------------------
# 6. Privileged detection: probe-aware cross-correlation detects synthesis
#    and replay at g_strong, power >= 0.9 (n=50).
# ---------------------------------------------------------------------------


def test_6_privileged_detection_of_synthesis_and_replay_at_g_strong(strong_ensembles):
    honest_pairs, synthesis_observations, replay_observations = strong_ensembles
    x0, p0 = stationary_prior_for(G_STRONG)
    priv = privileged_twin()
    calib = _default_crosscorr_calibration()

    for label, observation_set in (("synthesis", synthesis_observations), ("replay", replay_observations)):
        rejections = 0
        for (_, current_probe), observations in zip(honest_pairs, observation_set):
            trace = priv.run(
                observations, x0, p0, control_matrix=[[G_STRONG]], control_inputs=current_probe.reshape(-1, 1)
            )
            result = probe_innovation_cross_correlation(trace, current_probe, calib)
            if not result.cross_correlation_pass:
                rejections += 1

        power = rejections / POWER_ENSEMBLE_RUNS
        assert power >= STRONG_POWER_FLOOR, (
            f"[{label}] privileged detection power {power} ({rejections}/{POWER_ENSEMBLE_RUNS}) "
            f"at g_strong below the predeclared floor {STRONG_POWER_FLOOR}."
        )


# ---------------------------------------------------------------------------
# 7. Information-advantage comparison (core): on the *same* g_modest attack
#    paths (n=200), passive whiteness/NIS reject within [3,19] (null) while
#    probe-aware cross-correlation power >= MODEST_POWER_FLOOR (see the
#    module docstring's recorded-ambiguity note re: the plan's literal 0.9
#    text) -- only the privileged path receives the realized probe.
# ---------------------------------------------------------------------------


def _run_core_comparison(honest_pairs, synthesis_observations):
    x0, p0 = stationary_prior_for(G_MODEST)
    pas = passive_twin(G_MODEST)
    priv = privileged_twin()
    diag_calib = _default_diagnostic_calibration()
    crosscorr_calib = _default_crosscorr_calibration()

    whiteness_rejections = 0
    nis_rejections = 0
    crosscorr_rejections = 0
    for (_, current_probe), attack_observations in zip(honest_pairs, synthesis_observations):
        # Passive view: no control terms anywhere -- it literally cannot
        # see current_probe (structurally: passive_twin() has no B).
        passive_trace = pas.run(attack_observations, x0, p0)
        diag_result = innovation_diagnostic(passive_trace, diag_calib)
        if not diag_result.whiteness_pass:
            whiteness_rejections += 1
        if not diag_result.nis_pass:
            nis_rejections += 1

        # Privileged view: the *same* attack_observations, now examined
        # with the *same* run's realized current_probe as known control.
        privileged_trace = priv.run(
            attack_observations, x0, p0, control_matrix=[[G_MODEST]], control_inputs=current_probe.reshape(-1, 1)
        )
        crosscorr_result = probe_innovation_cross_correlation(privileged_trace, current_probe, crosscorr_calib)
        if not crosscorr_result.cross_correlation_pass:
            crosscorr_rejections += 1

    return whiteness_rejections, nis_rejections, crosscorr_rejections


def test_7_information_advantage_comparison_core(modest_ensembles):
    honest_pairs, synthesis_observations, _replay = modest_ensembles
    whiteness_rejections, nis_rejections, crosscorr_rejections = _run_core_comparison(
        honest_pairs, synthesis_observations
    )

    lo, hi = NULL_BAND_N200
    assert lo <= whiteness_rejections <= hi, (
        f"passive whiteness rejected {whiteness_rejections}/{NULL_ENSEMBLE_RUNS} g_modest attack runs, "
        f"outside the null band [{lo}, {hi}] -- passive view should stay blind."
    )
    assert lo <= nis_rejections <= hi, (
        f"passive NIS rejected {nis_rejections}/{NULL_ENSEMBLE_RUNS} g_modest attack runs, "
        f"outside [{lo}, {hi}] -- passive view should stay blind."
    )

    power = crosscorr_rejections / NULL_ENSEMBLE_RUNS
    assert power >= MODEST_POWER_FLOOR, (
        f"privileged cross-correlation power {power} ({crosscorr_rejections}/{NULL_ENSEMBLE_RUNS}) "
        f"at g_modest below the predeclared floor {MODEST_POWER_FLOOR} (see module docstring's "
        "recorded-ambiguity note)."
    )
    # The core information-advantage claim, made explicit: the privileged
    # view detects substantially more often than the passive view's null
    # rate on the *identical* attack paths.
    assert crosscorr_rejections > nis_rejections
    assert crosscorr_rejections > whiteness_rejections


def test_7_information_advantage_comparison_core_review_seed():
    """Plan Sec2, R6: rerun the core comparison under the held-out
    ``REVIEW_SEED`` -- the same predeclared bands/floor must hold under an
    independently-drawn ensemble, distinguishing genuine calibration from a
    seed-fit result.
    """
    honest_pairs, synthesis_observations, _replay = _build_modest_ensembles(
        _REVIEW_SEED_SEQUENCES, NULL_ENSEMBLE_RUNS
    )
    whiteness_rejections, nis_rejections, crosscorr_rejections = _run_core_comparison(
        honest_pairs, synthesis_observations
    )

    lo, hi = NULL_BAND_N200
    assert lo <= whiteness_rejections <= hi
    assert lo <= nis_rejections <= hi
    power = crosscorr_rejections / NULL_ENSEMBLE_RUNS
    assert power >= MODEST_POWER_FLOOR


# ---------------------------------------------------------------------------
# 8. Perfect relay: current-output relay bit-identical to honest (trace +
#    statistic); inherits honest null calibration -- a paired identity
#    test, not an independent "relay ensemble".
# ---------------------------------------------------------------------------


def test_8_perfect_relay_bit_identical_to_honest_trace_and_statistic():
    rng_process = np.random.default_rng(9001)
    rng_probe = np.random.default_rng(9002)
    honest_observations, u = generate_honest_watermarked_trajectory(
        rng_process, rng_probe, g=G_MODEST, n_steps=N_STEPS
    )
    relay_observations = generate_perfect_relay(honest_observations)

    # Bit-identical by construction, and a genuine copy (not the same
    # underlying array/object).
    assert np.array_equal(honest_observations, relay_observations)
    assert relay_observations is not honest_observations

    x0, p0 = stationary_prior_for(G_MODEST)
    diag_calib = _default_diagnostic_calibration()
    crosscorr_calib = _default_crosscorr_calibration()

    pas = passive_twin(G_MODEST)
    honest_passive_trace = pas.run(honest_observations, x0, p0)
    relay_passive_trace = pas.run(relay_observations, x0, p0)
    for field_name in ("innovations", "innovation_covariances", "filtered_state", "filtered_covariance"):
        assert np.array_equal(
            getattr(honest_passive_trace, field_name), getattr(relay_passive_trace, field_name)
        )
    honest_diag = innovation_diagnostic(honest_passive_trace, diag_calib)
    relay_diag = innovation_diagnostic(relay_passive_trace, diag_calib)
    assert honest_diag == relay_diag

    priv = privileged_twin()
    honest_priv_trace = priv.run(
        honest_observations, x0, p0, control_matrix=[[G_MODEST]], control_inputs=u.reshape(-1, 1)
    )
    relay_priv_trace = priv.run(
        relay_observations, x0, p0, control_matrix=[[G_MODEST]], control_inputs=u.reshape(-1, 1)
    )
    for field_name in ("innovations", "innovation_covariances", "filtered_state", "filtered_covariance"):
        assert np.array_equal(getattr(honest_priv_trace, field_name), getattr(relay_priv_trace, field_name))
    honest_crosscorr = probe_innovation_cross_correlation(honest_priv_trace, u, crosscorr_calib)
    relay_crosscorr = probe_innovation_cross_correlation(relay_priv_trace, u, crosscorr_calib)
    assert honest_crosscorr == relay_crosscorr

    # Blindness is inherited from the honest null calibration (obligation
    # 3) -- not re-derived from an independent relay ensemble here.
    assert honest_crosscorr.cross_correlation_pass == relay_crosscorr.cross_correlation_pass


# ---------------------------------------------------------------------------
# 9. Determinism/RNG separation: repeated inputs bit-identical; disjoint
#    derived streams per purpose; attack APIs do not accept u; relay
#    receives outputs only.
# ---------------------------------------------------------------------------


def test_9_generators_are_deterministic_given_identical_rng_state():
    obs_a, u_a = generate_honest_watermarked_trajectory(
        np.random.default_rng(555), np.random.default_rng(556), g=G_MODEST, n_steps=200
    )
    obs_b, u_b = generate_honest_watermarked_trajectory(
        np.random.default_rng(555), np.random.default_rng(556), g=G_MODEST, n_steps=200
    )
    assert np.array_equal(obs_a, obs_b)
    assert np.array_equal(u_a, u_b)

    synth_a = generate_passive_law_matched_synthesis(np.random.default_rng(777), g=G_MODEST, n_steps=200)
    synth_b = generate_passive_law_matched_synthesis(np.random.default_rng(777), g=G_MODEST, n_steps=200)
    assert np.array_equal(synth_a, synth_b)

    replay_a = generate_replay_trajectory(
        np.random.default_rng(1), np.random.default_rng(2), g=G_MODEST, n_steps=200
    )
    replay_b = generate_replay_trajectory(
        np.random.default_rng(1), np.random.default_rng(2), g=G_MODEST, n_steps=200
    )
    assert np.array_equal(replay_a, replay_b)


def test_9_purpose_streams_are_structurally_disjoint():
    # numpy's SeedSequence.spawn guarantees disjoint child seeds by
    # construction (distinct spawn_key suffixes on a shared entropy pool);
    # assert that structural guarantee directly, plus that it actually
    # yields different realized draws for two purposes that must never
    # share a stream (process vs. probe).
    process_seq = _PURPOSE_SEED_SEQUENCES["honest_modest_process"]
    probe_seq = _PURPOSE_SEED_SEQUENCES["honest_modest_probe"]
    assert process_seq.spawn_key != probe_seq.spawn_key

    rng_process = np.random.default_rng(process_seq.spawn(1)[0])
    rng_probe = np.random.default_rng(probe_seq.spawn(1)[0])
    assert rng_process.normal() != rng_probe.normal()

    # Review seed's tree is disjoint from the master tree entirely.
    assert _PURPOSE_SEED_SEQUENCES["honest_modest_process"].entropy != _REVIEW_SEED_SEQUENCES[
        "honest_modest_process"
    ].entropy


def test_9_attack_generator_apis_do_not_accept_a_probe():
    synth_params = set(inspect.signature(generate_passive_law_matched_synthesis).parameters)
    assert not (synth_params & {"u", "probe", "rng_probe", "current_probe"}), (
        f"generate_passive_law_matched_synthesis must not accept a probe argument; got {synth_params}."
    )

    replay_params = set(inspect.signature(generate_replay_trajectory).parameters)
    assert not (replay_params & {"u", "probe", "current_probe"}), (
        f"generate_replay_trajectory must not accept the *current* probe; got {replay_params}."
    )
    # It does take a *past*-probe RNG stream (to generate the recorded
    # trajectory), but never the realized past probe values themselves as
    # a plain array, and never the current probe.
    assert "rng_past_probe" in replay_params

    relay_params = list(inspect.signature(generate_perfect_relay).parameters)
    assert relay_params == ["honest_observations"], (
        f"generate_perfect_relay must receive only the output stream; got {relay_params}."
    )


# ---------------------------------------------------------------------------
# 10. Calibration/result scope: unsupported (alpha, lags, N, m, timing)
#     raise; chi-square threshold documented asymptotic, finite-N size
#     empirically checked by the 200-run honest ensemble (obligation 3);
#     no verdict/authenticity/security field; Sec0/Sec1 scope + terminology
#     language present.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(alpha=0.01, lags=LAG_SET, n_steps=N_STEPS, measurement_dim=1),
        dict(alpha=ALPHA, lags=(1, 2, 3), n_steps=N_STEPS, measurement_dim=1),
        dict(alpha=ALPHA, lags=LAG_SET, n_steps=1000, measurement_dim=1),
        dict(alpha=ALPHA, lags=LAG_SET, n_steps=N_STEPS, measurement_dim=2),
        dict(alpha=ALPHA, lags=LAG_SET, n_steps=N_STEPS, measurement_dim=1, timing_convention="wrong"),
    ],
)
def test_10_unsupported_crosscorrelation_calibration_configurations_raise(kwargs):
    with pytest.raises(ValueError, match="Unsupported cross-correlation calibration"):
        CrossCorrelationCalibration(**kwargs)


def test_10_calibration_threshold_documented_asymptotic_and_checked_empirically():
    calib = _default_crosscorr_calibration()
    assert "asymptotic" in calib.provenance
    assert "chi2.ppf" in calib.provenance or "chi-square" in calib.provenance
    # The finite-N size of this asymptotic calibration is empirically
    # checked by obligation 3's 200-run honest ensemble (this file), not
    # re-derived from a finite-sample distribution here.


def test_10_no_verdict_field_on_either_result_type():
    forbidden_substrings = ("verdict", "secure", "authentic", "matched", "aggregate", "overall")
    for result_type in (CrossCorrelationResult,):
        field_names = {f.name for f in dataclasses.fields(result_type)}
        for name in field_names:
            lowered = name.lower()
            assert not any(bad in lowered for bad in forbidden_substrings), (
                f"{result_type.__name__}.{name} looks like an aggregate/verdict field."
            )
        assert {"r_by_lag", "statistic", "threshold", "cross_correlation_pass", "alpha", "lags", "n_steps"} <= (
            field_names
        )


def test_10_module_docstring_carries_sec0_sec1_scope_and_terminology_language():
    doc = wm_module.__doc__
    assert doc is not None
    # Sec0 sequencing authority.
    assert "synthetic sample count" in doc
    assert "never a satellite-pass duration" in doc
    # Sec1 claim scope.
    assert "privileged information, not a more aggressive" in doc
    assert "same" in doc and "attack paths" in doc
    assert "Not claimed" in doc
    assert "unforgeability" in doc
    assert "anti-spoofing methodological primitive" in doc
    assert "Not a cryptographic secrecy claim" in doc
    # Sec1 terminology.
    assert "replay" in doc and "re-presentation of a recorded trajectory" in doc
    assert "passive-law-matched no-probe synthesis" in doc
    assert "pass-through of the true watermarked contemporaneous output" in doc


def test_10_cross_correlation_docstring_documents_asymptotic_calibration():
    doc = probe_innovation_cross_correlation.__doc__
    assert doc is not None
    assert "asymptotically chi-square" in doc


# ---------------------------------------------------------------------------
# 11. Suite/lane boundary: no LINK/mission/emission/schema/control contact;
#     no SciPy. (TWIN-1 green/untouched is reported by the full-suite run.)
# ---------------------------------------------------------------------------


def test_11_module_imports_no_link_mission_effects_or_scipy():
    import ast

    source = inspect.getsource(wm_module)
    tree = ast.parse(source)
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)

    for forbidden in ("qkd.link", "qkd.mission", "qkd.effects", "scipy"):
        assert not any(m == forbidden or m.startswith(forbidden + ".") for m in imported_modules), (
            f"qkd.twin_watermark must not import {forbidden!r}; imports found: {sorted(imported_modules)}."
        )
    assert "scipy" not in imported_modules

    # And the module only extends qkd.twin, never re-implements the filter.
    assert wm_module.LinearGaussianTwin is twin_module.LinearGaussianTwin
    assert wm_module.TwinTrace is TwinTrace
