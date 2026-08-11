"""qkd.twin -- Reference Kalman digital twin and innovation whiteness diagnostic.

TWIN-1 (``docs/TWIN_1_PLAN.md``, v2 approved). Lane: TWIN-* (Phase 2D
diagnostic/research machinery). The ADR-0002 wall holds from both sides: the
physics stack (``qkd.channel``, ``qkd.effects``, ``qkd.link``) and mission
orchestration (``qkd.mission``, ``qkd.run``) never read a trust/cognitive
field, and this module returns the favor -- it consumes and produces plain
``numpy`` arrays describing a linear-Gaussian observation model and imports
**none** of ``qkd.link``, ``qkd.mission``, or ``qkd.effects``. It has no
access to ``EffectiveLinkState``, mission emission, or estimator internals,
and none of its telemetry generators are wired into any production pass.

Claim scope (binding, plan Sec1 -- carried here verbatim in substance)
-----------------------------------------------------------------------
What the diagnostic is: a **temporal second-order diagnostic** -- scalar
innovation whiteness (Ljung-Box on standardized innovations) plus two-sided
NIS covariance consistency. Failure of either calibrated check rejects the
corresponding second-order consistency condition. **Passing both is
necessary but not sufficient** for full second-order matching, Gaussian-law
matching, source authenticity, or QKD security. (See ``NOTE-diffusion-kalman.md``
v2.1 Sec6 for why a fully matched adversary is a genuine statistical-
indistinguishability result under the stated observation model, not an
implementation gap this module closes.)

Calibrated blindness is an **ensemble statement**: for data drawn from the
nominal observable law, each diagnostic component rejects at its declared
null rate within a predeclared binomial tolerance, across many independent
seeded runs -- no detector using only these observations can reject a
same-law source more often than it rejects honest data at the same
threshold. Individual seeded runs are *permitted* to fail at rate ~= alpha;
demanding otherwise would reward a miscalibrated diagnostic, not a correct
one.

Terminology: an independently generated sequence from the nominal law is
**same-law synthesis**, never "replay" -- replay is reserved for reuse of a
recorded trajectory (a load-bearing distinction for later replace/replay/
synthesis/relay attack-class work; see ``NOTE-diffusion-kalman.md`` Sec6.2).

Evidence claim: TWIN-1 is **qDISH-relevant integrity-method evidence** / an
**anti-spoofing methodological primitive** -- not a navigation-integrity
prototype or a GPS-spoofing performance result (those require a PNT
observation model, attack model, and operating scenario, none of which this
module supplies).

Multiplicity: whiteness and NIS each run at their own declared alpha,
reported separately -- **no aggregate false-positive-rate claim is made and
no aggregate verdict exists.** :class:`InnovationDiagnosticResult` carries
only per-test statistics, thresholds, and pass/fail fields; it has no
``secure``/``authentic``/``matched`` field and no field that combines the two
tests into one verdict.

Scope boundary: this is **classical telemetry** authentication only --
whether the twin can tell that classical link observables are being forged.
It places no limit on, and says nothing about, the quantum layer's own
security properties (QBER-based eavesdropping bounds, entanglement
verification, the cryptographic security of the key); a Kalman
observability limit is not a QKD security limit
(``NOTE-diffusion-kalman.md`` v2.1 Sec1).
"""

from __future__ import annotations

import math
import types
from dataclasses import dataclass, field
from typing import Mapping

import numpy as np

# ---------------------------------------------------------------------------
# Validation helpers (shared by construction and per-step Joseph-form checks)
# ---------------------------------------------------------------------------

_PSD_TOL = 1e-8


def _check_finite(array: np.ndarray, name: str) -> None:
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must be finite; found non-finite values.")


def _check_square(array: np.ndarray, name: str) -> None:
    if array.ndim != 2 or array.shape[0] != array.shape[1]:
        raise ValueError(f"{name} must be a square 2-D matrix; got shape {array.shape}.")


def _check_symmetric(array: np.ndarray, name: str, *, atol: float = 1e-9) -> None:
    if not np.allclose(array, array.T, atol=atol, rtol=1e-9):
        raise ValueError(f"{name} must be symmetric within tolerance {atol}.")


def _check_psd(array: np.ndarray, name: str, *, tol: float = _PSD_TOL) -> None:
    """Raise if symmetric ``array`` is not PSD within a declared tolerance.

    ``numpy.linalg.eigvalsh`` is used only to *detect* a numerically
    significant negative eigenvalue -- a validation gate, never a repair:
    PSD failure raises here rather than silently clipping negative
    eigenvalues to zero and continuing (plan Sec2.1).
    """
    eigenvalues = np.linalg.eigvalsh(array)
    scale = max(1.0, float(np.max(np.abs(eigenvalues))))
    min_eig = float(np.min(eigenvalues))
    if min_eig < -tol * scale:
        raise ValueError(
            f"{name} is not positive semi-definite within tolerance "
            f"(min eigenvalue {min_eig:.6e}, scale {scale:.6e})."
        )


def _cholesky_or_raise(array: np.ndarray, name: str) -> np.ndarray:
    try:
        return np.linalg.cholesky(array)
    except np.linalg.LinAlgError as exc:
        raise ValueError(f"{name} is not numerically positive definite: {exc}") from exc


# ---------------------------------------------------------------------------
# Filter
# ---------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class TwinTrace:
    """Batch filter trace (plan Sec2.1) -- kept for external/hand-calc verification.

    ``eq=False``: fields are ``numpy`` arrays, for which the dataclass-
    generated elementwise ``__eq__`` would return an array rather than a
    bool. Callers compare individual fields with ``numpy.array_equal`` (as
    the determinism obligation in the test file does), not trace equality.
    """

    innovations: np.ndarray
    innovation_covariances: np.ndarray
    filtered_state: np.ndarray
    filtered_covariance: np.ndarray


@dataclass(frozen=True, eq=False)
class LinearGaussianTwin:
    """Stateless linear-Gaussian Kalman twin (plan Sec2.1, R6).

    ``LinearGaussianTwin(F, H, Q, R).run(observations, x0, P0) -> TwinTrace``.
    No RNG anywhere in this class -- randomness lives only in the telemetry
    generators below, each taking an explicit ``numpy.random.Generator``.
    ``run`` is a pure batch function over its arguments: it retains no state
    between calls, and repeated calls with identical arguments are
    bit-identical.
    """

    F: np.ndarray
    H: np.ndarray
    Q: np.ndarray
    R: np.ndarray

    def __post_init__(self) -> None:
        F = np.asarray(self.F, dtype=float)
        H = np.asarray(self.H, dtype=float)
        Q = np.asarray(self.Q, dtype=float)
        R = np.asarray(self.R, dtype=float)

        _check_square(F, "F")
        _check_finite(F, "F")
        n = F.shape[0]

        if H.ndim != 2 or H.shape[1] != n:
            raise ValueError(f"H must have shape (m, {n}); got {H.shape}.")
        _check_finite(H, "H")
        m = H.shape[0]
        if m < 1:
            raise ValueError("H must declare at least one measurement row.")

        _check_square(Q, "Q")
        if Q.shape[0] != n:
            raise ValueError(f"Q must have shape ({n}, {n}); got {Q.shape}.")
        _check_finite(Q, "Q")
        _check_symmetric(Q, "Q")
        _check_psd(Q, "Q")

        _check_square(R, "R")
        if R.shape[0] != m:
            raise ValueError(f"R must have shape ({m}, {m}); got {R.shape}.")
        _check_finite(R, "R")
        _check_symmetric(R, "R")
        _check_psd(R, "R")

        object.__setattr__(self, "F", F)
        object.__setattr__(self, "H", H)
        object.__setattr__(self, "Q", Q)
        object.__setattr__(self, "R", R)

    @property
    def state_dim(self) -> int:
        return self.F.shape[0]

    @property
    def measurement_dim(self) -> int:
        return self.H.shape[0]

    def run(self, observations, x0, P0) -> TwinTrace:
        """Run the filter once over ``observations``, returning a fresh ``TwinTrace``.

        Joseph form exactly: ``P+ = (I-KH) P- (I-KH)^T + K R K^T``, followed
        by numerical re-symmetrization; the Kalman gain, and every
        symmetric-system solve below, use ``numpy.linalg.solve``/Cholesky --
        never an explicit matrix inverse. A PSD failure on ``P+`` raises
        (plan Sec2.1); it is never hidden by eigenvalue clipping.
        """
        n = self.state_dim
        m = self.measurement_dim

        observations = np.asarray(observations, dtype=float)
        if observations.ndim != 2 or observations.shape[1] != m:
            raise ValueError(f"observations must have shape (N, {m}); got {observations.shape}.")
        n_steps = observations.shape[0]
        if n_steps == 0:
            raise ValueError("observations must be non-empty.")
        _check_finite(observations, "observations")

        x0 = np.asarray(x0, dtype=float)
        if x0.shape != (n,):
            raise ValueError(f"x0 must have shape ({n},); got {x0.shape}.")
        _check_finite(x0, "x0")

        P0 = np.asarray(P0, dtype=float)
        _check_square(P0, "P0")
        if P0.shape[0] != n:
            raise ValueError(f"P0 must have shape ({n}, {n}); got {P0.shape}.")
        _check_finite(P0, "P0")
        _check_symmetric(P0, "P0")
        _check_psd(P0, "P0")

        if n == 1 and m == 1:
            # Scalar fast path (performance note, plan Sec6): mathematically
            # identical to the general branch below, specialized so ensemble
            # runs (200x N=2000 scalar filters) stay fast. For a 1x1 system
            # the Cholesky factor of S is exactly sqrt(S) and "solving"
            # S @ K^T = H @ P_pred is exactly division by S -- these are not
            # approximations of solve/Cholesky, they *are* solve/Cholesky's
            # closed form at dimension 1, evaluated directly instead of via
            # the general numpy linear-algebra entry points to avoid their
            # per-call dispatch overhead at this scale. The Joseph-form
            # arithmetic, PSD gate, and re-symmetrization (a no-op for a
            # 1x1 matrix) are otherwise untouched.
            return self._run_scalar(observations, float(x0[0]), float(P0[0, 0]))

        return self._run_general(observations, x0, P0)

    def _run_general(self, observations: np.ndarray, x0: np.ndarray, P0: np.ndarray) -> TwinTrace:
        n = self.state_dim
        m = self.measurement_dim
        n_steps = observations.shape[0]
        identity_n = np.eye(n)

        x = x0.copy()
        P = P0.copy()

        innovations = np.empty((n_steps, m))
        innovation_covariances = np.empty((n_steps, m, m))
        filtered_state = np.empty((n_steps, n))
        filtered_covariance = np.empty((n_steps, n, n))

        for k in range(n_steps):
            # Predict.
            x_pred = self.F @ x
            P_pred = self.F @ P @ self.F.T + self.Q

            # Innovation.
            nu = observations[k] - self.H @ x_pred
            S = self.H @ P_pred @ self.H.T + self.R
            _cholesky_or_raise(S, f"innovation covariance S at step k={k}")

            # Gain via solve, never an explicit inverse: K^T solves
            # S @ K^T = (H @ P_pred) (S is symmetric, so S^T == S), i.e.
            # K = (P_pred @ H^T) @ S^{-1} without ever forming S^{-1}.
            gain_rhs = self.H @ P_pred  # shape (m, n)
            K = np.linalg.solve(S, gain_rhs).T  # shape (n, m)

            # Update (Joseph form).
            x_post = x_pred + K @ nu
            i_minus_kh = identity_n - K @ self.H
            P_post = i_minus_kh @ P_pred @ i_minus_kh.T + K @ self.R @ K.T
            P_post = 0.5 * (P_post + P_post.T)  # numerical re-symmetrization
            _check_psd(P_post, f"P+ at step k={k}")

            innovations[k] = nu
            innovation_covariances[k] = S
            filtered_state[k] = x_post
            filtered_covariance[k] = P_post

            x, P = x_post, P_post

        return TwinTrace(
            innovations=innovations,
            innovation_covariances=innovation_covariances,
            filtered_state=filtered_state,
            filtered_covariance=filtered_covariance,
        )

    def _run_scalar(self, observations: np.ndarray, x0: float, p0: float) -> TwinTrace:
        f = float(self.F[0, 0])
        h = float(self.H[0, 0])
        q = float(self.Q[0, 0])
        r = float(self.R[0, 0])
        n_steps = observations.shape[0]

        x, p = x0, p0
        innovations = np.empty((n_steps, 1))
        innovation_covariances = np.empty((n_steps, 1, 1))
        filtered_state = np.empty((n_steps, 1))
        filtered_covariance = np.empty((n_steps, 1, 1))

        for k in range(n_steps):
            # Predict.
            x_pred = f * x
            p_pred = f * f * p + q

            # Innovation. s == (Cholesky factor)**2 of the 1x1 S; the PD
            # gate below is exactly _cholesky_or_raise's condition at n=1.
            nu = float(observations[k, 0]) - h * x_pred
            s = h * h * p_pred + r
            if not (s > 0.0 and math.isfinite(s)):
                raise ValueError(
                    f"innovation covariance S at step k={k} is not numerically "
                    f"positive definite: S={s!r}."
                )

            # Gain: K = p_pred * h / s -- the 1x1 closed form of solving
            # s @ K^T = h @ p_pred, never treated as a matrix inverse.
            gain = (p_pred * h) / s

            # Update (Joseph form, 1x1 closed form).
            x_post = x_pred + gain * nu
            i_minus_kh = 1.0 - gain * h
            p_post = i_minus_kh * i_minus_kh * p_pred + gain * gain * r
            # Re-symmetrization is a no-op at n=1. The PSD gate is still
            # run -- this is _check_psd's own scale-relative tolerance
            # condition at n=1 (a single eigenvalue equal to the entry
            # itself), evaluated directly to avoid eigvalsh's per-step
            # array-construction overhead at this scale.
            scale = max(1.0, abs(p_post))
            if p_post < -_PSD_TOL * scale:
                raise ValueError(
                    f"P+ at step k={k} is not positive semi-definite within "
                    f"tolerance (min eigenvalue {p_post:.6e}, scale {scale:.6e})."
                )

            innovations[k, 0] = nu
            innovation_covariances[k, 0, 0] = s
            filtered_state[k, 0] = x_post
            filtered_covariance[k, 0, 0] = p_post

            x, p = x_post, p_post

        return TwinTrace(
            innovations=innovations,
            innovation_covariances=innovation_covariances,
            filtered_state=filtered_state,
            filtered_covariance=filtered_covariance,
        )


# ---------------------------------------------------------------------------
# Diagnostic calibration (plan Sec2.2, R4)
# ---------------------------------------------------------------------------

# Precomputed chi-square critical values for the single predeclared TWIN-1
# demonstration calibration configuration (plan Sec3): alpha=0.05,
# Ljung-Box lags K=20, N_eff=2000, scalar (measurement_dim=1) observations.
#
# Provenance: computed offline (never at runtime -- this module has no
# SciPy dependency) via bisection search on a self-contained regularized
# lower incomplete gamma function P(a, x) (Numerical-Recipes-style series
# expansion for x < a+1, continued fraction for x >= a+1, built only on
# ``math.lgamma``; chi2.cdf(x, df) == P(df/2, x/2)). Independently
# cross-checked against ``scipy.stats.chi2.ppf`` in an offline development
# sandbox (not a runtime import of this module); both methods agree to
# >= 10 significant figures:
#
#   ljung_box_upper = chi2.ppf(0.95,   df=20)   -> 31.410432844230918 (scipy)
#                                                   31.410432844230932 (bisection)
#   nis_lower       = chi2.ppf(0.025,  df=2000) -> 1877.9460368153905 (scipy)
#                                                   1877.9460368153777 (bisection)
#   nis_upper       = chi2.ppf(0.975,  df=2000) -> 2125.8423024497756 (scipy)
#                                                   2125.842302449785  (bisection)
#
# The higher-precision (scipy) values are the ones shipped below.
_CALIBRATION_TABLE: Mapping[tuple, Mapping[str, object]] = {
    (0.05, 20, 2000, 1): {
        "critical_values": {
            "ljung_box_upper": 31.410432844230918,
            "nis_lower": 1877.9460368153905,
            "nis_upper": 2125.8423024497756,
        },
        "provenance": (
            "ljung_box_upper = chi2.ppf(0.95, df=20); nis_lower/nis_upper = "
            "chi2.ppf(0.025, df=2000)/chi2.ppf(0.975, df=2000). Computed "
            "offline via bisection on a self-contained regularized "
            "incomplete-gamma implementation, cross-checked against "
            "scipy.stats.chi2.ppf -- see the module comment above "
            "_CALIBRATION_TABLE. SciPy is not imported by this module."
        ),
    },
}


@dataclass(frozen=True)
class DiagnosticCalibration:
    """Frozen calibration contract for :func:`innovation_diagnostic` (plan Sec2.2, R4).

    Only the predeclared demonstration configuration(s) in
    ``_CALIBRATION_TABLE`` are supported: ``critical_values`` and
    ``provenance`` are derived automatically from that table and are never
    accepted as caller-supplied arguments, foreclosing silent reuse of a
    mismatched table entry. An unsupported ``(alpha, lags, effective_n,
    measurement_dim)`` combination raises rather than interpolating.
    """

    alpha: float
    lags: int
    effective_n: int
    measurement_dim: int
    critical_values: Mapping[str, float] = field(init=False)
    provenance: str = field(init=False)

    def __post_init__(self) -> None:
        key = (self.alpha, self.lags, self.effective_n, self.measurement_dim)
        entry = _CALIBRATION_TABLE.get(key)
        if entry is None:
            supported = sorted(_CALIBRATION_TABLE)
            raise ValueError(
                "Unsupported diagnostic calibration configuration "
                f"(alpha={self.alpha!r}, lags={self.lags!r}, "
                f"effective_n={self.effective_n!r}, "
                f"measurement_dim={self.measurement_dim!r}); only the "
                f"predeclared demonstration configuration(s) {supported} "
                "are supported (plan Sec2.2, R4) -- interpolation or "
                "silent reuse of a mismatched table entry is not permitted."
            )
        object.__setattr__(
            self, "critical_values", types.MappingProxyType(dict(entry["critical_values"]))
        )
        object.__setattr__(self, "provenance", entry["provenance"])


@dataclass(frozen=True)
class InnovationDiagnosticResult:
    """Per-test whiteness/NIS result (plan Sec2.2). No aggregate verdict field.

    Carries only per-test statistics, thresholds, and pass/fail booleans --
    deliberately no ``secure``/``authentic``/``matched`` field and no field
    that combines ``whiteness_pass``/``nis_pass`` into one aggregate verdict
    (plan Sec1, R4: whiteness and NIS are reported separately; no aggregate
    false-positive-rate claim is made).
    """

    alpha: float
    lags: int
    effective_n: int
    calibration: DiagnosticCalibration
    whiteness_statistic: float
    whiteness_threshold: float
    whiteness_pass: bool
    nis_statistic: float
    nis_lower_threshold: float
    nis_upper_threshold: float
    nis_pass: bool


def _ljung_box_statistic(z: np.ndarray, lags: int) -> float:
    """Ljung-Box Q statistic on standardized innovations ``z`` (plan Sec2.2).

    Standard definition (matching e.g. statsmodels' ``acorr_ljungbox``):
    autocorrelations are computed about ``z``'s own sample mean rather than
    an assumed-known zero mean, so the statistic stays well-defined even if
    a finite-sample filter bias leaves the sample mean not exactly zero.
    """
    n = z.shape[0]
    if lags < 1 or lags >= n:
        raise ValueError(f"lags must be in [1, {n - 1}]; got {lags}.")
    z_centered = z - z.mean()
    c0 = float(np.sum(z_centered**2))
    if c0 <= 0.0:
        raise ValueError(
            "innovation_diagnostic requires nonzero standardized-innovation variance."
        )
    stat = 0.0
    for lag in range(1, lags + 1):
        autocovariance = float(np.sum(z_centered[lag:] * z_centered[:-lag]))
        r_lag = autocovariance / c0
        stat += (r_lag**2) / (n - lag)
    return n * (n + 2.0) * stat


def innovation_diagnostic(
    trace: TwinTrace, calibration: DiagnosticCalibration
) -> InnovationDiagnosticResult:
    """Ljung-Box whiteness + two-sided NIS diagnostic on standardized innovations.

    **Scalar-observation-only** (plan Sec2.2): raises clearly when the
    trace's measurement dimension is not 1. A per-component univariate
    Ljung-Box test does not test *vector* whiteness -- cross-component/
    cross-lag dependence escapes it; a multivariate portmanteau statistic
    is deferred (plan Sec5, out of scope for TWIN-1) until a real
    multi-observable telemetry model earns it.

    This is a **temporal second-order diagnostic**: passing both the
    whiteness and NIS checks is necessary but not sufficient for full
    second-order matching, Gaussian-law matching, source authenticity, or
    QKD security (module docstring, plan Sec1). The two checks are reported
    at their own declared alpha, separately -- no aggregate verdict is
    computed or returned.
    """
    m = trace.innovations.shape[1]
    if m != 1:
        raise ValueError(
            "innovation_diagnostic supports scalar (measurement_dim=1) "
            f"observations only; got measurement_dim={m}."
        )
    if calibration.measurement_dim != 1:
        raise ValueError(
            "calibration.measurement_dim must be 1 for this scalar-only "
            f"diagnostic; got {calibration.measurement_dim}."
        )

    n_eff = trace.innovations.shape[0]
    if n_eff != calibration.effective_n:
        raise ValueError(
            f"trace has {n_eff} retained innovations but calibration "
            f"declares effective_n={calibration.effective_n}; TWIN-1 ships "
            "no burn-in/partial-window support, so the count must match "
            "exactly (plan Sec2.2, R4)."
        )

    nu = trace.innovations[:, 0]
    S = trace.innovation_covariances[:, 0, 0]
    if np.any(S <= 0.0):
        raise ValueError("innovation_diagnostic requires strictly positive S_k throughout.")

    z = nu / np.sqrt(S)

    whiteness_statistic = _ljung_box_statistic(z, calibration.lags)
    whiteness_threshold = calibration.critical_values["ljung_box_upper"]
    whiteness_pass = whiteness_statistic <= whiteness_threshold  # one-sided upper tail

    nis_statistic = float(np.sum(z**2))
    nis_lower_threshold = calibration.critical_values["nis_lower"]
    nis_upper_threshold = calibration.critical_values["nis_upper"]
    nis_pass = nis_lower_threshold <= nis_statistic <= nis_upper_threshold

    return InnovationDiagnosticResult(
        alpha=calibration.alpha,
        lags=calibration.lags,
        effective_n=calibration.effective_n,
        calibration=calibration,
        whiteness_statistic=whiteness_statistic,
        whiteness_threshold=whiteness_threshold,
        whiteness_pass=whiteness_pass,
        nis_statistic=nis_statistic,
        nis_lower_threshold=nis_lower_threshold,
        nis_upper_threshold=nis_upper_threshold,
        nis_pass=nis_pass,
    )


# ---------------------------------------------------------------------------
# Telemetry generators (plan Sec2.3) -- the theorem's cast.
#
# All scalar-stationary, all take an explicit ``numpy.random.Generator``,
# all initialized from the stationary distribution so no transient appears
# in any detection signal (R5). None of these are wired into any production
# mission pass -- they exist only to drive this module's own tests.
# ---------------------------------------------------------------------------


def stationary_variance(a: float, q: float) -> float:
    """Return ``P_x = q / (1 - a**2)``, the scalar AR(1) stationary state variance.

    Raises for ``|a| >= 1`` (the recursion ``x_k = a*x_{k-1} + w_k`` is not
    stationary at or beyond the unit root) or invalid/negative ``q``.
    """
    if not math.isfinite(a) or not math.isfinite(q) or q < 0.0:
        raise ValueError(f"invalid AR(1) parameters a={a!r}, q={q!r}.")
    if abs(a) >= 1.0:
        raise ValueError(f"a={a!r} is not stationary (|a| must be < 1).")
    return q / (1.0 - a * a)


def stationary_prior(p_x: float) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(x0, P0) = (zeros(1), [[p_x]])`` -- the stationary scalar filter prior (R5)."""
    if p_x < 0.0 or not math.isfinite(p_x):
        raise ValueError(f"invalid stationary variance p_x={p_x!r}.")
    return np.zeros(1), np.array([[p_x]])


def _draw_normal(rng: np.random.Generator, variance: float) -> float:
    return float(rng.normal(0.0, math.sqrt(variance))) if variance > 0.0 else 0.0


def generate_honest_telemetry(
    rng: np.random.Generator, *, a: float, q: float, r: float, n_steps: int
) -> np.ndarray:
    """Nominal scalar AR(1)+noise telemetry (plan Sec2.3 item 1), stationary-initialized.

    ``x_k = a*x_{k-1} + w_k``, ``w_k ~ N(0, q)``; ``z_k = x_k + v_k``,
    ``v_k ~ N(0, r)``; ``x_0`` is drawn from the model's own stationary
    distribution ``N(0, P_x)`` so no burn-in transient appears in any
    detection signal (R5).
    """
    if r < 0.0 or not math.isfinite(r):
        raise ValueError(f"invalid measurement variance r={r!r}.")
    if n_steps <= 0:
        raise ValueError("n_steps must be positive.")

    p_x = stationary_variance(a, q)
    x = _draw_normal(rng, p_x)
    observations = np.empty((n_steps, 1))
    for k in range(n_steps):
        x = a * x + _draw_normal(rng, q)
        observations[k, 0] = x + _draw_normal(rng, r)
    return observations


def generate_same_law_synthesis_telemetry(
    rng: np.random.Generator, *, a: float, q: float, r: float, n_steps: int
) -> np.ndarray:
    """Independent draw from the *same* nominal law as :func:`generate_honest_telemetry`.

    **Same-law synthesis** (plan Sec1, R7 terminology) -- never "replay":
    this is a fresh independent draw from the nominal observable law, not
    reuse of a recorded trajectory. Implemented as literally the identical
    generative process so the case-3 blindness ensemble (plan Sec2.3 item 3)
    is exactly the honest ensemble's null distribution, driven by an
    independent RNG stream/seed.
    """
    return generate_honest_telemetry(rng, a=a, q=q, r=r, n_steps=n_steps)


def generate_wrong_dynamics_marginal_matched_telemetry(
    rng: np.random.Generator, *, a: float, q: float, b: float, r: float, n_steps: int
) -> np.ndarray:
    """Wrong-dynamics adversary with the honest model's marginal variance (plan Sec2.3 item 2, R5).

    ``F=b != a``, ``Q' = P_x*(1 - b**2)`` where ``P_x = q/(1 - a**2)`` is the
    *honest* model's stationary state variance -- by construction this
    process has exactly the same stationary state variance (and, since
    observation noise is unchanged, the same marginal observation variance)
    as the honest model; only its second-order *temporal* structure
    differs, colouring the nominal filter's innovations. The marginal
    equality is asserted analytically in the test file, never tuned
    numerically.
    """
    p_x = stationary_variance(a, q)
    if abs(b) >= 1.0:
        raise ValueError(f"b={b!r} is not stationary (|b| must be < 1).")
    q_prime = p_x * (1.0 - b * b)
    if q_prime < 0.0 or not math.isfinite(q_prime):
        raise ValueError(f"invalid marginal-matched process noise q'={q_prime!r} for b={b!r}.")
    if r < 0.0 or not math.isfinite(r):
        raise ValueError(f"invalid measurement variance r={r!r}.")
    if n_steps <= 0:
        raise ValueError("n_steps must be positive.")

    x = _draw_normal(rng, p_x)
    observations = np.empty((n_steps, 1))
    for k in range(n_steps):
        x = b * x + _draw_normal(rng, q_prime)
        observations[k, 0] = x + _draw_normal(rng, r)
    return observations


def generate_memoryless_covariance_mismatch_telemetry(
    rng: np.random.Generator, *, q: float, r_prime: float, n_steps: int
) -> np.ndarray:
    """Memoryless (``a=0``) filter, data with wrong measurement variance ``R' != r``.

    Plan Sec2.3 item 4 / R3 test-5 construction. ``a=0`` makes the recursion
    memoryless -- ``x_k = w_k`` i.i.d. ``N(0, q)`` -- so the filter's own
    recursion cannot colour its innovations (and no explicit stationary
    initialization is needed: every ``x_k`` is already an independent draw
    from the ``a=0`` stationary law). Any statistical signal in the
    standardized innovations must therefore come from the mismatch between
    the filter's nominal ``R`` and the true ``R'`` used to generate the
    data -- isolating NIS's information content from the filter-recursion
    coloring exercised by the wrong-dynamics construction above.
    """
    if q < 0.0 or not math.isfinite(q):
        raise ValueError(f"invalid process variance q={q!r}.")
    if r_prime < 0.0 or not math.isfinite(r_prime):
        raise ValueError(f"invalid true measurement variance r_prime={r_prime!r}.")
    if n_steps <= 0:
        raise ValueError("n_steps must be positive.")

    observations = np.empty((n_steps, 1))
    for k in range(n_steps):
        x_k = _draw_normal(rng, q)
        observations[k, 0] = x_k + _draw_normal(rng, r_prime)
    return observations
