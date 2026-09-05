"""RECOH-1/RECOH-2 stored-qubit and analytic dephasing + active-rephasing instrument.

Configuration names in this module (`dephasing_model`, `noise_kernel`, `D_phi`,
`tau_c`) follow SPEC-memory-lifetime-adr0003 (ratified 2026-09-03, `81c97ed`);
`kappa_ideal` corresponds to `identity_state_evolution`.

The local dephasing_model/noise_kernel vocabulary distinguishes ideal,
lindblad_phase_damping, and gaussian_frequency_noise (white or OU). For OU,
<xi(t)xi(0)> = sigma**2 * exp(-abs(t)/tau_c), kappa = exp(-<phi**2>/2),
and D_phi = sigma**2 * tau_c. sigma**2 is derived, never configured;
T2 = 1/D_phi is only a reporting alias (infinite when D_phi = 0).

RECOH-2 extends this instrument with an ideal, instantaneous pi-pulse about the
storage-basis X axis applied at a predeclared time tau, and the OU-noise
"echo" variance evaluator (`echo_h`, `echo_F`) used to compute the controlled
trajectory's attenuation. This module makes no rung-2 claim on its own; the
recovery classification and report contract live in qkd.recoh.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real

import numpy as np

__all__ = [
    "StoredQubit", "PLUS", "MINUS", "density_matrix", "dephase",
    "choi_dephasing", "is_cptp_dephasing", "kappa_ideal", "kappa_lindblad",
    "kappa_gaussian", "EchoModel", "pi_pulse_x", "purity", "echo_h", "echo_F",
    "var_free", "var_ctrl", "echo_peak_time", "stored_state_at", "evolve",
]

_STATE_TOL = 1e-12
_CHOI_TOL = 1e-12
_OU_X_SWITCH = 1e-3
_ECHO_H_SWITCH = 0.5
_ECHO_H_MAX_ITER = 60


def _finite_real(value: float, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite real scalar.")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite.")
    return value


def _times(t) -> np.ndarray:
    if np.iscomplexobj(t):
        raise ValueError("t must contain finite real values >= 0.")
    try:
        values = np.asarray(t, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("t must contain finite real values >= 0.") from exc
    if not np.all(np.isfinite(values)) or np.any(values < 0.0):
        raise ValueError("t must contain finite values >= 0.")
    return values


def _finite_nonneg_array(value, name: str) -> np.ndarray:
    """Validate a scalar or array as finite real and >= 0; ndim is preserved."""
    if np.iscomplexobj(value):
        raise ValueError(f"{name} must contain finite real values >= 0.")
    try:
        arr = np.asarray(value, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain finite real values >= 0.") from exc
    if not np.all(np.isfinite(arr)) or np.any(arr < 0.0):
        raise ValueError(f"{name} must contain finite real values >= 0.")
    return arr


def _scalar_or_array(values: np.ndarray) -> float | np.ndarray:
    return float(values) if values.ndim == 0 else values


@dataclass(frozen=True)
class StoredQubit:
    """Bloch-vector state with |r| <= 1 + 1e-12; never renormalized."""

    rx: float
    ry: float
    rz: float

    def __post_init__(self) -> None:
        for name in ("rx", "ry", "rz"):
            object.__setattr__(self, name, _finite_real(getattr(self, name), name))
        if math.hypot(self.rx, self.ry, self.rz) > 1.0 + _STATE_TOL:
            raise ValueError("Bloch-vector bound violated: |r| must be <= 1 + 1e-12.")


PLUS = StoredQubit(1.0, 0.0, 0.0)
MINUS = StoredQubit(-1.0, 0.0, 0.0)


def density_matrix(state: StoredQubit) -> np.ndarray:
    """Return the 2x2 complex matrix rho = (I + r.sigma)/2."""
    return 0.5 * np.array(
        [[1.0 + state.rz, state.rx - 1j * state.ry],
         [state.rx + 1j * state.ry, 1.0 - state.rz]],
        dtype=complex,
    )


def dephase(state: StoredQubit, kappa: float) -> StoredQubit:
    """Apply physical real dephasing; negative kappa is allowed, |kappa| > 1 is not."""
    if (isinstance(kappa, (bool, np.bool_)) or not isinstance(kappa, Real)
            or not math.isfinite(kappa)):
        raise ValueError("kappa must be a finite real scalar.")
    if abs(kappa) > 1.0:
        raise ValueError("kappa bound violated: |kappa| must be <= 1.")
    return StoredQubit(kappa * state.rx, kappa * state.ry, state.rz)


def choi_dephasing(kappa: float) -> np.ndarray:
    """Unnormalized J = sum_ij E(|i><j|) tensor |i><j|; trace(J) = 2.

    Basis: |00>, |01>, |10>, |11>, with output subsystem first. Any finite
    real kappa is admitted for diagnosis, even when the map is not physical.
    Eigenvalues are 1+kappa, 1-kappa, 0, 0; output partial trace is I.
    """
    if (isinstance(kappa, (bool, np.bool_)) or not isinstance(kappa, Real)
            or not math.isfinite(kappa)):
        raise ValueError("kappa must be a finite real scalar for Choi construction.")
    return np.array(
        [[1.0, 0.0, 0.0, kappa], [0.0, 0.0, 0.0, 0.0],
         [0.0, 0.0, 0.0, 0.0], [kappa, 0.0, 0.0, 1.0]],
        dtype=complex,
    )


def is_cptp_dephasing(kappa: float) -> bool:
    """Check Choi PSD and output partial trace, each within absolute 1e-12."""
    choi = choi_dephasing(kappa)
    output_trace = np.trace(choi.reshape(2, 2, 2, 2), axis1=0, axis2=2)
    return bool(
        np.linalg.eigvalsh(choi).min() >= -_CHOI_TOL
        and np.allclose(output_trace, np.eye(2), rtol=0.0, atol=_CHOI_TOL)
    )


def kappa_ideal(t) -> float | np.ndarray:
    """Identity coherence factor, shape-preserving for arrays of t >= 0."""
    return _scalar_or_array(np.ones_like(_times(t)))


def kappa_lindblad(t, D_phi: float) -> float | np.ndarray:
    """Return exp(-D_phi*t), with D_phi >= 0 and t >= 0."""
    times = _times(t)
    rate = _finite_real(D_phi, "D_phi")
    if rate < 0.0:
        raise ValueError("D_phi must be >= 0.")
    with np.errstate(over="ignore", under="ignore"):
        result = np.exp(-rate * times)
    return _scalar_or_array(result)


def _g_ou(x) -> float | np.ndarray:
    """Stable x-1+exp(-x); series leading relative error is x**3/60."""
    values = np.asarray(x, dtype=float)
    result = np.empty_like(values)
    small = values < _OU_X_SWITCH
    xs = values[small]
    result[small] = xs**2 * (0.5 - xs / 6.0 + xs**2 / 24.0)
    result[~small] = values[~small] + np.expm1(-values[~small])
    return _scalar_or_array(result)


def kappa_gaussian(t, D_phi: float, tau_c: float | None = None) -> float | np.ndarray:
    """White noise reuses Lindblad exactly; OU gives exp(-D_phi*tau_c*g(t/tau_c)).

    The white limit holds D_phi = sigma**2*tau_c fixed, not sigma**2.
    tau_c=None denotes white noise; a finite OU tau_c must be > 0.
    """
    if tau_c is None:
        return kappa_lindblad(t, D_phi)
    times = _times(t)
    rate = _finite_real(D_phi, "D_phi")
    correlation_time = _finite_real(tau_c, "tau_c")
    if rate < 0.0:
        raise ValueError("D_phi must be >= 0.")
    if correlation_time <= 0.0:
        raise ValueError("tau_c must be > 0; use None for the white kernel.")
    if rate == 0.0:
        return _scalar_or_array(np.ones_like(times))
    result = np.exp(-rate * correlation_time * _g_ou(times / correlation_time))
    return _scalar_or_array(result)


# --------------------------------------------------------------------------
# RECOH-2: active rephasing (ideal pi-pulse) on the stored-qubit reference.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class EchoModel:
    """RECOH-2 single-qubit echo model: OU (or white, tau_c=None) noise plus
    an ideal instantaneous pi-pulse about the storage-basis X axis at tau.
    """

    r0: StoredQubit
    D_phi: float
    tau_c: float | None
    tau: float

    def __post_init__(self) -> None:
        if not isinstance(self.r0, StoredQubit):
            raise ValueError("r0 must be a StoredQubit.")
        object.__setattr__(self, "D_phi", _finite_real(self.D_phi, "D_phi"))
        if self.D_phi < 0.0:
            raise ValueError("D_phi must be >= 0.")
        if self.tau_c is not None:
            object.__setattr__(self, "tau_c", _finite_real(self.tau_c, "tau_c"))
            if self.tau_c <= 0.0:
                raise ValueError("tau_c must be > 0; use None for the white kernel.")
        object.__setattr__(self, "tau", _finite_real(self.tau, "tau"))
        if self.tau <= 0.0:
            raise ValueError("tau must be > 0.")


def pi_pulse_x(state: StoredQubit) -> StoredQubit:
    """Ideal instantaneous pi-pulse about the storage-basis X axis: (rx,ry,rz) -> (rx,-ry,-rz).

    An involution: applying it twice returns the original state. Preserves
    |rho_01| (coherence_l1), purity, and trace exactly.
    """
    return StoredQubit(state.rx, -state.ry, -state.rz)


def purity(state: StoredQubit) -> float:
    """Return P = (1 + |r|**2)/2."""
    return (1.0 + state.rx**2 + state.ry**2 + state.rz**2) / 2.0


def _echo_h_coeff(n: int) -> float:
    return ((-1) ** n) * (2.0 ** (2 - n) - 1.0) / math.factorial(n)


def _echo_h_series_scalar(x: float) -> float:
    """Series h(x) = sum_{n>=3} c_n x**n for 0 < x < 0.5; binding underflow policy."""
    n = 3
    x_pow = x**3
    term = _echo_h_coeff(n) * x_pow
    if term == 0.0:
        return 0.0
    total = term
    iterations = 1
    while True:
        if iterations >= _ECHO_H_MAX_ITER:
            raise RuntimeError("echo_h: convergence failure")
        n += 1
        x_pow *= x
        term = _echo_h_coeff(n) * x_pow
        iterations += 1
        if term == 0.0:
            return total
        if abs(term) < 1e-17 * abs(total):
            return total
        total += term


def echo_h(x) -> float | np.ndarray:
    """h(x) = x - 3 + 4*exp(-x/2) - exp(-x), evaluated by series for 0<x<0.5
    (declared underflow policy) and directly for x >= 0.5. x < 0 raises;
    x == 0.0 returns 0.0 exactly.
    """
    arr = _finite_nonneg_array(x, "x")
    out = np.empty_like(arr, dtype=float)

    zero_mask = arr == 0.0
    out[zero_mask] = 0.0

    direct_mask = arr >= _ECHO_H_SWITCH
    xd = arr[direct_mask]
    out[direct_mask] = xd - 3.0 + 4.0 * np.exp(-xd / 2.0) - np.exp(-xd)

    series_mask = (~zero_mask) & (~direct_mask)
    if np.any(series_mask):
        xs = arr[series_mask]
        vals = np.array([_echo_h_series_scalar(float(v)) for v in xs], dtype=float)
        out[series_mask] = vals

    return _scalar_or_array(out)


def echo_F(a, b) -> float | np.ndarray:
    """F(a,b) = [h(2a) + h(2b) + Delta**2] / 2, Delta = exp(-min(a,b))*E(|a-b|),
    E(x) = -expm1(-x). F(a,a) == h(2a) and F(0,0) == 0.0 follow from this
    identity without special-casing. a, b must be finite and >= 0.
    """
    a_arr = _finite_nonneg_array(a, "a")
    b_arr = _finite_nonneg_array(b, "b")
    delta = np.exp(-np.minimum(a_arr, b_arr)) * (-np.expm1(-np.abs(a_arr - b_arr)))
    total = (echo_h(2.0 * a_arr) + echo_h(2.0 * b_arr) + delta**2) / 2.0
    return _scalar_or_array(np.asarray(total, dtype=float))


def var_free(model: EchoModel, t) -> float | np.ndarray:
    """Var_free(t) = 2*D_phi*t (white kernel) or 2*D_phi*tau_c*g(t/tau_c) (OU)."""
    times = _times(t)
    if model.tau_c is None:
        result = 2.0 * model.D_phi * times
    else:
        result = 2.0 * model.D_phi * model.tau_c * _g_ou(times / model.tau_c)
    return _scalar_or_array(np.asarray(result, dtype=float))


def var_ctrl(model: EchoModel, t) -> float | np.ndarray:
    """Var_ctrl(t): equals Var_free(t) for t < tau (and everywhere in the white
    kernel, which has no post-pulse peak); for t >= tau under OU noise, uses
    2*D_phi*tau_c*F(tau/tau_c, (t-tau)/tau_c) (never called with negative b).
    """
    times = _times(t)
    if model.tau_c is None:
        result = 2.0 * model.D_phi * times
        return _scalar_or_array(np.asarray(result, dtype=float))
    result = np.empty_like(times, dtype=float)
    before = times < model.tau
    after = ~before
    if np.any(before):
        result[before] = 2.0 * model.D_phi * model.tau_c * _g_ou(times[before] / model.tau_c)
    if np.any(after):
        a = model.tau / model.tau_c
        b = (times[after] - model.tau) / model.tau_c
        result[after] = 2.0 * model.D_phi * model.tau_c * echo_F(a, b)
    return _scalar_or_array(result)


def echo_peak_time(model: EchoModel) -> float | None:
    """t_peak = tau + tau_c*log1p(E(tau/tau_c)); None for the white kernel or D_phi=0."""
    if model.tau_c is None or model.D_phi == 0.0:
        return None
    x = model.tau / model.tau_c
    e_x = -math.expm1(-x)
    return model.tau + model.tau_c * math.log1p(e_x)


def stored_state_at(model: EchoModel, t, controlled: bool):
    """Return the noise-averaged state at time(s) t (scalar or 1-D array, t>=0).

    controlled=False: free evolution at every t, no sign flips.
    controlled=True: r(t) = (W(t)*rx0, W(t)*ry0, rz0) for t < tau and
    r(t) = (W(t)*rx0, -W(t)*ry0, -rz0) for t >= tau (r(tau) = r(tau+)), where
    W(t) = exp(-Var(t)/2) uses var_ctrl (which already equals var_free before
    tau). Returns a single StoredQubit for scalar t, else a tuple of
    StoredQubit matching t elementwise.
    """
    times = _times(t)
    scalar = times.ndim == 0
    arr = np.atleast_1d(times).astype(float)
    var = np.atleast_1d(np.asarray(var_ctrl(model, arr) if controlled else var_free(model, arr), dtype=float))
    with np.errstate(over="ignore", under="ignore"):
        w = np.exp(-var / 2.0)
    r0 = model.r0
    rx = w * r0.rx
    if controlled:
        after = arr >= model.tau
        ry = np.where(after, -w * r0.ry, w * r0.ry)
        rz = np.where(after, -r0.rz, r0.rz)
    else:
        ry = w * r0.ry
        rz = np.full(arr.shape, r0.rz)
    states = tuple(
        StoredQubit(float(rx[i]), float(ry[i]), float(rz[i])) for i in range(arr.shape[0])
    )
    return states[0] if scalar else states


def evolve(model: EchoModel, t_grid, controlled: bool):
    """Validate t_grid (finite, strictly increasing, no duplicates, 1-D,
    non-empty) and return stored_state_at(model, t_grid, controlled).
    """
    arr = _times(t_grid)
    arr = np.atleast_1d(arr)
    if arr.ndim != 1:
        raise ValueError("t_grid must be a 1-D array of times.")
    if arr.size == 0:
        raise ValueError("t_grid must be a non-empty array of times.")
    if not np.all(np.diff(arr) > 0):
        raise ValueError("t_grid must be strictly increasing with no duplicates.")
    return stored_state_at(model, arr, controlled)
