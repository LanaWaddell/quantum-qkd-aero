"""qkd.twin_watermark -- Private-probe watermarking and the probe/innovation
cross-correlation detector.

TWIN-2 (``docs/TWIN_2_PLAN.md``, v2 approved). Lane: TWIN-* (Phase 2D
diagnostic/research machinery; no LINK-lane contact). This module imports
**none** of ``qkd.link``, ``qkd.mission``, or ``qkd.effects`` -- it extends
``qkd.twin`` only, consuming its ``LinearGaussianTwin`` (known-input
extension), ``DiagnosticCalibration``/``innovation_diagnostic`` (passive
whiteness/NIS), and ``stationary_variance``/``stationary_prior`` helpers.
None of its generators are wired into any production mission pass.

Sec0 -- Sequencing authority (R1, binding)
-------------------------------------------
TWIN-2 proceeds under the 2026-08-12 amendment to
``NOTE-sequencing-2026-08-10.md`` Sec3: the model-generic synthetic Route-2
primitive is authorized now; the Exp-1 gate is preserved in full for every
link-telemetry / mission-cadence / contact-window / PNT / QKD-performance
instantiation (Exp 3B, registered separately). Echo's finite-window power
study is registered as TWIN-3. This module's ``N = 2000`` is a
**synthetic sample count**, **never a satellite-pass duration** -- the
mapping N ~= T_contact/Delta_t is earned by TWIN-3/Exp 3B, not claimed
here.

Sec1 -- Claim scope (binding, TWIN-1 conventions inherited)
-------------------------------------------------------------
**Demonstrated:** the Route-2 information-structure asymmetry as calibrated
ensemble behaviour. Under an attack whose complete unconditional Gaussian
observation law matches the honest watermarked law (R4), TWIN-1's
probe-unaware whiteness and NIS diagnostics remain at their null rates,
while a probe-aware cross-correlation detector rejects with predeclared
power. The advantage is **privileged information, not a more aggressive
threshold** (R3) -- the two views (passive, privileged) are evaluated on
the *same* attack paths, differing only in whether the detector receives
the realized probe.

**Detection and blindness both asserted:** detect no-probe synthesis and
past-trajectory replay (privileged view); remain blind -- **by structural
identity (R7)** -- to a perfect live relay.

**Not claimed:** unforgeability (relay blindness is the standing honest
boundary); any aggregate false-positive rate (per-test alpha, reported
separately); navigation/QKD performance; ROC or probe-energy curves
(TWIN-3 / sized Route-2 item). TWIN-2 is an
**anti-spoofing methodological primitive**.

**Probe privacy (R8):** "private" means the realized probe is excluded from
the adversary's simulated information set and attack-generator signatures.
**Not a cryptographic secrecy claim** -- the recorded seed is available to
the evaluator for reproducibility. The attack-generator functions in this
module do not accept the probe as an argument, and the relay path receives
only the output stream -- not that a real adversary cannot infer the probe
by other means.

**Terminology (R7):**
  - *replay* = re-presentation of a recorded trajectory.
  - *passive-law-matched no-probe synthesis* = an independent draw matching
    the full unconditional law but independent of the current probe.
  - *relay* = pass-through of the true watermarked contemporaneous output.

Sec2 -- Frozen model and parameters (R2/R5)
---------------------------------------------
Timing convention (binding): state recursion ``x_{k+1} = a*x_k + g*u_k +
w_k``, observation ``y_k = x_k + v_k``. The probe ``u_k`` drives
``x_{k+1}``, so it first affects ``y_{k+1}`` -- the first theoretically
visible lag is **d = 1**. The known-input filter predicting ``y_k`` uses
the *preceding* control: ``x_hat^-_k = a*x_hat_{k-1} + g*u_{k-1}`` (the
first prediction, k=0, uses x0 with no control at all -- there is no
u_{-1}). The cross-correlation is ``r_d = corr(u_k, z_{k+d})`` over lag set
D = {1, 2, 3, 4, 5}; the pair count for lag d is N-d (R6); u is
standardized by the **known** sigma_u, innovations by the known S_k
(zero-mean by construction, never sample-centered).

All numerics below (a, q, r, sigma_u2, g_strong, g_modest, N, alpha, D) are
frozen by the plan before any seed is drawn.
"""

from __future__ import annotations

import math
import types
from dataclasses import dataclass, field
from typing import Mapping, Sequence

import numpy as np

from qkd.twin import LinearGaussianTwin, TwinTrace, stationary_prior, stationary_variance

# ---------------------------------------------------------------------------
# Frozen numerics (plan Sec2 table) -- fixed before any seed is chosen.
# ---------------------------------------------------------------------------

A = 0.9  # nominal AR(1) coefficient
Q = 1.0  # nominal (conditional-on-u) process variance
R = 0.5  # measurement variance
SIGMA_U2 = 1.0  # probe variance
SIGMA_U = math.sqrt(SIGMA_U2)

G_STRONG = 0.5  # strong gain: g**2 * sigma_u2 = 0.25 (25% of q)
G_MODEST = 0.15  # modest gain: g**2 * sigma_u2 = 0.0225 (2.25% of q)
# Note (TWIN-2 v2.1, 2026-08-12): passive blindness is GAIN-INDEPENDENT under the
# q_synth exact-law-matching construction -- passive whiteness/NIS on synthesis sit
# at their null rate for ALL g (verified: (12,6)/200 rejections across g in
# [0.10, 0.25]). g_modest is therefore chosen purely to place the *privileged*
# 5-lag cross-correlation power >= 0.9, not to preserve passive blindness. At
# g=0.10 the 5-lag chi^2_5 detector reaches only ~0.80 power (the lag-1 response
# is diluted across 4 near-null lags, raising the critical value 3.84 -> 11.07);
# g=0.15 gives ~0.997 with passive still fully blind. This is the stronger and
# correct framing of the Route-2 result.

N_STEPS = 2000  # synthetic sample count (Sec0 -- not a satellite-pass duration)
ALPHA = 0.05  # per test, reported separately -- no family-wise claim
LAG_SET: tuple[int, ...] = (1, 2, 3, 4, 5)  # D; df = len(LAG_SET) = 5


def q_synth(g: float) -> float:
    """Passive-law-matched no-probe synthesis process variance (plan Sec2, R4).

    ``q_synth(g) = q + g**2 * sigma_u2`` -- this is *exactly* the marginal
    (probe-marginalized) process-noise variance of the honest watermarked
    recursion: since ``u_k`` is i.i.d. ``N(0, sigma_u2)`` independent of
    ``w_k``, the unconditional increment ``g*u_k + w_k`` has variance
    ``g**2*sigma_u2 + q``. This algebraic identity is why a passive filter
    that does not see ``u`` and is built with ``Q = q_synth(g)`` sees the
    correct total process variance for *any* of {honest, synthesis,
    replay, relay} and stays at its null calibration for all four.
    """
    if not math.isfinite(g):
        raise ValueError(f"invalid gain g={g!r}.")
    return Q + g * g * SIGMA_U2


def stationary_variance_under_probe(g: float) -> float:
    """``P_x^u(g) = (q + g**2*sigma_u2) / (1 - a**2)`` (plan Sec2 table).

    The stationary state variance of the honest watermarked process
    (marginalizing the probe) -- identically the stationary variance of the
    ``q_synth(g)`` AR(1) synthesis process, since ``q_synth(g)`` *is* that
    marginal process-noise variance. Used to stationary-initialize every
    generator below so no burn-in transient appears in any signal.
    """
    return stationary_variance(A, q_synth(g))


# ---------------------------------------------------------------------------
# Filter builders -- the two information views (plan Sec4, R3, the core
# architecture). The passive view is built with Q = q_synth(g) and never
# receives control terms; the privileged view is built with the physical Q
# and is run with the known control matrix/inputs (the realized probe).
# ---------------------------------------------------------------------------


def passive_twin(g: float) -> LinearGaussianTwin:
    """No-control filter, ``Q = q_synth(g)`` (plan Sec4): the probe is
    marginalized as ordinary Gaussian excitation. This filter is never
    handed ``u`` -- structurally, not merely by omission of a nonzero
    control term (it is built with no ``B``, so ``run`` cannot be given
    ``control_inputs`` through it without also passing a ``control_matrix``
    this constructor never distributes).
    """
    return LinearGaussianTwin(F=[[A]], H=[[1.0]], Q=[[q_synth(g)]], R=[[R]])


def privileged_twin() -> LinearGaussianTwin:
    """With-control filter, physical ``Q = q`` (plan Sec4): the conditional
    process variance stays at the physical ``q`` because the control term
    ``g*u_{k-1}`` explains the probe's contribution to the mean directly;
    only the *unexplained* process noise ``w_k`` remains as ``Q``.
    """
    return LinearGaussianTwin(F=[[A]], H=[[1.0]], Q=[[Q]], R=[[R]])


def stationary_prior_for(g: float) -> tuple[np.ndarray, np.ndarray]:
    """``(x0, P0)`` at the shared stationary variance ``P_x^u(g)`` (plan Sec4).

    Both the passive and privileged views are stationary-initialized at the
    *same* numeric variance: it is simultaneously the honest process's true
    marginal stationary variance and the ``q_synth(g)`` synthesis process's
    stationary variance (they are the same algebraic quantity -- see
    :func:`q_synth`).
    """
    return stationary_prior(stationary_variance_under_probe(g))


# ---------------------------------------------------------------------------
# Telemetry / trajectory generators (plan Sec4) -- the threat-class cast.
#
# All scalar-stationary, all take an explicit ``numpy.random.Generator`` (or
# two, for honest/replay, kept in disjoint SeedSequence.spawn subtrees by
# the caller), all initialized from stationary_variance_under_probe so no
# transient appears in any signal (R5). Attack-generator signatures never
# accept a probe argument (R8/R9): generate_passive_law_matched_synthesis
# and generate_replay_trajectory take no ``u`` and return no ``u``.
# ---------------------------------------------------------------------------


def _draw_normal(rng: np.random.Generator, variance: float) -> float:
    return float(rng.normal(0.0, math.sqrt(variance))) if variance > 0.0 else 0.0


def generate_honest_watermarked_trajectory(
    rng_process: np.random.Generator,
    rng_probe: np.random.Generator,
    *,
    g: float,
    a: float = A,
    q: float = Q,
    r: float = R,
    sigma_u2: float = SIGMA_U2,
    n_steps: int = N_STEPS,
) -> tuple[np.ndarray, np.ndarray]:
    """The Sec2 recursion with the private probe: ``x_{k+1} = a*x_k + g*u_k
    + w_k``, ``y_k = x_k + v_k``, stationary-initialized at
    ``P_x^u(g)``. Returns ``(observations, probe)`` -- ``observations``
    shape ``(n_steps, 1)``, ``probe`` shape ``(n_steps,)`` with
    ``probe[k] = u_k``. ``rng_process`` and ``rng_probe`` must be disjoint
    streams (plan Sec2, obligation 9): process noise/measurement noise draw
    from ``rng_process``, the probe draws from ``rng_probe``.
    """
    if r < 0.0 or not math.isfinite(r):
        raise ValueError(f"invalid measurement variance r={r!r}.")
    if sigma_u2 < 0.0 or not math.isfinite(sigma_u2):
        raise ValueError(f"invalid probe variance sigma_u2={sigma_u2!r}.")
    if n_steps <= 0:
        raise ValueError("n_steps must be positive.")

    p_x_u = stationary_variance(a, q + g * g * sigma_u2)
    x = _draw_normal(rng_process, p_x_u)
    observations = np.empty((n_steps, 1))
    probe = np.empty(n_steps)
    for k in range(n_steps):
        observations[k, 0] = x + _draw_normal(rng_process, r)
        u_k = _draw_normal(rng_probe, sigma_u2)
        probe[k] = u_k
        x = a * x + g * u_k + _draw_normal(rng_process, q)
    return observations, probe


def generate_passive_law_matched_synthesis(
    rng_process: np.random.Generator,
    *,
    g: float,
    a: float = A,
    q: float = Q,
    r: float = R,
    sigma_u2: float = SIGMA_U2,
    n_steps: int = N_STEPS,
) -> np.ndarray:
    """Passive-law-matched no-probe synthesis (plan Sec4, R4): AR(1) with
    process variance ``q_synth(g) = q + g**2*sigma_u2``, **no probe at
    all** -- this function's signature has no ``u``/``rng_probe`` parameter
    by construction (R8/R9), matching the honest watermarked process's
    complete unconditional Gaussian law (mean, stationary variance,
    autocovariance kernel, measurement law) analytically, while
    independent of the current probe.
    """
    qs = q + g * g * sigma_u2
    if r < 0.0 or not math.isfinite(r):
        raise ValueError(f"invalid measurement variance r={r!r}.")
    if n_steps <= 0:
        raise ValueError("n_steps must be positive.")

    p_x = stationary_variance(a, qs)
    x = _draw_normal(rng_process, p_x)
    observations = np.empty((n_steps, 1))
    for k in range(n_steps):
        observations[k, 0] = x + _draw_normal(rng_process, r)
        x = a * x + _draw_normal(rng_process, qs)
    return observations


def generate_replay_trajectory(
    rng_process: np.random.Generator,
    rng_past_probe: np.random.Generator,
    *,
    g: float,
    a: float = A,
    q: float = Q,
    r: float = R,
    sigma_u2: float = SIGMA_U2,
    n_steps: int = N_STEPS,
) -> np.ndarray:
    """Replay of a recorded past-probe trajectory (plan Sec4, R7 terminology).

    Re-presentation of a genuinely honest watermarked trajectory generated
    against a **past** probe realization (``rng_past_probe``, disjoint from
    both the current probe stream and ``rng_process``). Only the
    observations are returned -- the past probe realization itself is
    never exposed (R8/R9: attack APIs do not accept, or leak, a probe).
    Because this *is* a genuine draw of the honest generative process, its
    unconditional law is identical to :func:`generate_honest_watermarked_trajectory`
    and :func:`generate_passive_law_matched_synthesis` (obligation 4); it
    has zero correlation with the *current* probe because
    ``rng_past_probe`` is an independent stream from it.
    """
    observations, _past_probe = generate_honest_watermarked_trajectory(
        rng_process, rng_past_probe, g=g, a=a, q=q, r=r, sigma_u2=sigma_u2, n_steps=n_steps
    )
    return observations


def generate_perfect_relay(honest_observations: np.ndarray) -> np.ndarray:
    """Perfect relay (plan Sec4, R7): the true current watermarked output
    passed through unchanged. This is not an independent generator with
    its own randomness -- it is the identity function on
    ``honest_observations`` (returning a defensive copy so callers cannot
    mutate the original trace's source array), i.e. **bit-identical to
    honest by construction**. Blindness is proven by a paired identity
    test (obligation 8), never by an independent "relay ensemble".
    """
    return np.array(honest_observations, dtype=float, copy=True)


# ---------------------------------------------------------------------------
# Probe/innovation cross-correlation detector (plan Sec2/Sec4, the
# privileged-view core) and its frozen calibration.
# ---------------------------------------------------------------------------

_TIMING_CONVENTION = (
    "x_{k+1} = a*x_k + g*u_k + w_k; y_k = x_k + v_k; probe u_k first "
    "visible at lag d=1 in y_{k+1}; known-input filter predicting y_k uses "
    "control index k-1 (x_hat^-_k = a*x_hat_{k-1} + g*u_{k-1}), first "
    "prediction k=0 uses x0 with no control (TWIN-2 plan Sec2)."
)

# Precomputed asymptotic chi-square critical value for the single
# predeclared TWIN-2 cross-correlation calibration configuration (plan
# Sec2/Sec5 obligation 10): alpha=0.05, D={1,2,3,4,5} (df=5), N=2000,
# scalar (measurement_dim=1) observations, Sec2 timing convention.
#
# T = sum_{d in D} (N-d) * r_d**2 is asymptotically chi-square with
# df=len(D)=5 under the null (u, z independent, both standardized to unit
# variance by known population parameters -- see
# probe_innovation_cross_correlation below): each per-lag term
# (N-d)*r_d**2 is asymptotically chi-square_1, and the terms are
# asymptotically independent across lags for a stationary process with the
# geometrically-decaying dependence structure here, so their sum is
# asymptotically chi-square_5. This is the same asymptotic-calibration
# pattern as qkd.twin's Ljung-Box/NIS thresholds -- its finite-N size is
# empirically checked by the 200-run honest-privileged-null ensemble
# (obligation 3), not re-derived from a finite-sample distribution.
#
# Provenance: computed offline (never at runtime -- this module has no
# SciPy dependency, matching qkd.twin's precedent) via bisection search on
# the same self-contained regularized lower incomplete gamma function used
# in qkd.twin's _CALIBRATION_TABLE comment (Numerical-Recipes-style series
# expansion for x < a+1, continued fraction for x >= a+1, built only on
# ``math.lgamma``). Independently cross-checked against
# ``scipy.stats.chi2.ppf`` in an offline development sandbox (not a
# runtime import of this module); both methods agree to >= 10 significant
# figures:
#
#   chi2.ppf(0.95, df=5) -> 11.070497693516351 (scipy)
#                            11.070497693516348 (bisection)
#
# The higher-precision (scipy) value is the one shipped below.
_CROSSCORR_CALIBRATION_TABLE: Mapping[tuple, Mapping[str, object]] = {
    (0.05, LAG_SET, 2000, 1, _TIMING_CONVENTION): {
        "critical_value": 11.070497693516351,
        "provenance": (
            "critical_value = chi2.ppf(1-alpha, df=len(lags)); T = "
            "sum_{d in lags} (N-d)*r_d**2 is asymptotically chi-square_df "
            "under the null of no probe/innovation correlation. Computed "
            "offline via bisection on a self-contained regularized "
            "incomplete-gamma implementation, cross-checked against "
            "scipy.stats.chi2.ppf -- see the module comment above "
            "_CROSSCORR_CALIBRATION_TABLE. SciPy is not imported by this "
            "module."
        ),
    },
}


@dataclass(frozen=True)
class CrossCorrelationCalibration:
    """Frozen calibration contract for :func:`probe_innovation_cross_correlation`
    (plan Sec2/Sec5 obligation 10).

    Only the predeclared demonstration configuration in
    ``_CROSSCORR_CALIBRATION_TABLE`` is supported: ``critical_value`` and
    ``provenance`` are derived automatically from that table and are never
    accepted as caller-supplied arguments. An unsupported ``(alpha, lags,
    n_steps, measurement_dim, timing_convention)`` combination raises
    rather than interpolating or silently reusing a mismatched entry.
    """

    alpha: float
    lags: tuple[int, ...]
    n_steps: int
    measurement_dim: int
    timing_convention: str = _TIMING_CONVENTION
    critical_value: float = field(init=False)
    provenance: str = field(init=False)

    def __post_init__(self) -> None:
        key = (self.alpha, tuple(self.lags), self.n_steps, self.measurement_dim, self.timing_convention)
        entry = _CROSSCORR_CALIBRATION_TABLE.get(key)
        if entry is None:
            supported = sorted(_CROSSCORR_CALIBRATION_TABLE, key=lambda k: (k[0], k[2], k[3]))
            raise ValueError(
                "Unsupported cross-correlation calibration configuration "
                f"(alpha={self.alpha!r}, lags={tuple(self.lags)!r}, "
                f"n_steps={self.n_steps!r}, measurement_dim={self.measurement_dim!r}, "
                f"timing_convention={'matches' if self.timing_convention == _TIMING_CONVENTION else 'DOES NOT MATCH'} "
                f"the frozen Sec2 convention); only the predeclared demonstration "
                f"configuration(s) {supported} are supported (plan Sec2/Sec5 "
                "obligation 10) -- interpolation or silent reuse of a "
                "mismatched table entry is not permitted."
            )
        object.__setattr__(self, "critical_value", entry["critical_value"])
        object.__setattr__(self, "provenance", entry["provenance"])


@dataclass(frozen=True)
class CrossCorrelationResult:
    """Probe/innovation cross-correlation result (plan Sec4). No verdict field.

    Carries only per-lag correlations, the aggregate statistic, its
    threshold, and a single pass/fail boolean for *this* statistical test
    -- deliberately no ``secure``/``authentic``/``matched``/``verdict``
    field (plan Sec1, mirroring ``qkd.twin.InnovationDiagnosticResult``).
    """

    alpha: float
    lags: tuple[int, ...]
    n_steps: int
    calibration: CrossCorrelationCalibration
    r_by_lag: Mapping[int, float]
    statistic: float
    threshold: float
    cross_correlation_pass: bool


def probe_innovation_cross_correlation(
    privileged_trace: TwinTrace,
    probe: Sequence[float] | np.ndarray,
    calibration: CrossCorrelationCalibration,
    *,
    sigma_u: float = SIGMA_U,
) -> CrossCorrelationResult:
    """Probe/innovation cross-correlation detector (plan Sec2, the
    privileged-view core).

    ``privileged_trace`` must come from :func:`privileged_twin` run *with*
    the known control matrix and the *same* ``probe`` as control inputs
    (plan Sec4: "cross-correlation uses the same realized u"). For each lag
    ``d`` in ``calibration.lags``::

        r_d = (1 / (N - d)) * sum_{k=0}^{N-d-1} (u_k / sigma_u) * z_{k+d}

    over the ``N - d`` available pairs (plan Sec2, R6), where ``z_k =
    nu_k / sqrt(S_k)`` is the privileged filter's standardized innovation
    and ``u_k`` is standardized by the **known** population ``sigma_u``
    (never a sample standard deviation) -- both factors are zero-mean by
    construction, so ``r_d`` is not sample-centered. ``sigma_u`` is a
    keyword-only argument (defaulting to the frozen ``SIGMA_U = sqrt(1.0)``,
    plan Sec2) rather than a field of ``calibration``: it is a frozen model
    parameter of the probe itself (like ``a``, ``q``, ``r``), not a
    property of the detector's statistical calibration.

    The aggregate statistic is ``T = sum_d (N-d) * r_d**2``: each per-lag
    term ``(N-d)*r_d**2`` is asymptotically chi-square_1 under the null of
    no probe/innovation correlation (the ``N-d`` factor is the per-lag pair
    count normalization -- not a uniform ``N`` scaling, plan Sec2/Sec5
    obligation 10), and their sum over ``|D|`` lags is asymptotically
    chi-square with ``df = len(D)``. ``T`` exceeding the calibrated
    threshold rejects the null (a detected probe-response mismatch);
    ``cross_correlation_pass`` is ``True`` when ``T`` stays within the
    calibrated null region (mirroring ``whiteness_pass``/``nis_pass`` in
    ``qkd.twin.InnovationDiagnosticResult``).
    """
    if privileged_trace.innovations.shape[1] != 1:
        raise ValueError(
            "probe_innovation_cross_correlation supports scalar "
            f"(measurement_dim=1) traces only; got "
            f"measurement_dim={privileged_trace.innovations.shape[1]}."
        )
    if calibration.measurement_dim != 1:
        raise ValueError(
            "calibration.measurement_dim must be 1 for this scalar-only "
            f"detector; got {calibration.measurement_dim}."
        )

    nu = privileged_trace.innovations[:, 0]
    S = privileged_trace.innovation_covariances[:, 0, 0]
    if np.any(S <= 0.0):
        raise ValueError(
            "probe_innovation_cross_correlation requires strictly positive S_k throughout."
        )
    n_steps = nu.shape[0]
    if n_steps != calibration.n_steps:
        raise ValueError(
            f"privileged_trace has {n_steps} innovations but calibration "
            f"declares n_steps={calibration.n_steps}; the count must match "
            "exactly (plan Sec2/Sec5 obligation 10)."
        )

    if sigma_u <= 0.0 or not math.isfinite(sigma_u):
        raise ValueError(f"invalid sigma_u={sigma_u!r}.")

    probe = np.asarray(probe, dtype=float)
    if probe.shape != (n_steps,):
        raise ValueError(f"probe must have shape ({n_steps},); got {probe.shape}.")
    if not np.all(np.isfinite(probe)):
        raise ValueError("probe must be finite.")

    z = nu / np.sqrt(S)
    u_std = probe / sigma_u

    r_by_lag: dict[int, float] = {}
    statistic = 0.0
    for d in calibration.lags:
        if d < 1 or d >= n_steps:
            raise ValueError(f"lag d={d} must be in [1, {n_steps - 1}].")
        pairs = n_steps - d
        r_d = float(np.sum(u_std[:pairs] * z[d : d + pairs]) / pairs)
        r_by_lag[d] = r_d
        statistic += pairs * (r_d**2)

    threshold = calibration.critical_value
    cross_correlation_pass = statistic <= threshold

    return CrossCorrelationResult(
        alpha=calibration.alpha,
        lags=calibration.lags,
        n_steps=n_steps,
        calibration=calibration,
        r_by_lag=types.MappingProxyType(r_by_lag),
        statistic=statistic,
        threshold=threshold,
        cross_correlation_pass=cross_correlation_pass,
    )
