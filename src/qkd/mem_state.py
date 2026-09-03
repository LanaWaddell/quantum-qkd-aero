"""RECOH-1 stored-qubit and analytic pure-dephasing reference instrument.

Configuration names in this module are PROVISIONAL pending the memory SPEC
amendment (RECOH-0 v0.2 §4); reconciliation is a RECOH-2 obligation.

The local dephasing_model/noise_kernel vocabulary distinguishes ideal,
lindblad_phase_damping, and gaussian_frequency_noise (white or OU). For OU,
<xi(t)xi(0)> = sigma**2 * exp(-abs(t)/tau_c), kappa = exp(-<phi**2>/2),
and D_phi = sigma**2 * tau_c. sigma**2 is derived, never configured;
T2 = 1/D_phi is only a reporting alias (infinite when D_phi = 0).
This instrument has no retrieval-efficiency model or production coupling
and makes no rung-2 claim. No control sequences or stochastic trajectories.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real

import numpy as np

__all__ = [
    "StoredQubit", "PLUS", "MINUS", "density_matrix", "dephase",
    "choi_dephasing", "is_cptp_dephasing", "kappa_ideal", "kappa_lindblad",
    "kappa_gaussian",
]

_STATE_TOL = 1e-12
_CHOI_TOL = 1e-12
_OU_X_SWITCH = 1e-3


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
