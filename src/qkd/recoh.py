"""RECOH-1 derived stored-state witnesses and recovery classification.

Configuration names in this module are PROVISIONAL pending the memory SPEC
amendment (RECOH-0 v0.2 §4); reconciliation is a RECOH-2 obligation.

RecoveryClass is a derived output, not a configured capability. RECOH-1 is
an instrument: every supplied free-evolution model returns NONE. Synthetic
curve self-checks do not establish a physical recovery model or rung-2 claim.
"""

from __future__ import annotations

import math
from enum import Enum
from numbers import Real

import numpy as np

from qkd.mem_state import StoredQubit

__all__ = [
    "coherence_l1", "pure_target_fidelity", "trace_distance",
    "trace_distance_backflow", "recovery_fraction", "RecoveryClass",
    "classify_recovery",
]


def coherence_l1(state: StoredQubit) -> float:
    """Return 2*abs(rho[0, 1]) = hypot(rx, ry)."""
    return math.hypot(state.rx, state.ry)


def pure_target_fidelity(state: StoredQubit, target: StoredQubit) -> float:
    """Return squared-overlap fidelity (1+r.r_target)/2 for a pure target only."""
    if not math.isclose(math.hypot(target.rx, target.ry, target.rz),
                        1.0, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("target must be pure")
    return (1.0 + state.rx * target.rx + state.ry * target.ry + state.rz * target.rz) / 2.0


def trace_distance(a: StoredQubit, b: StoredQubit) -> float:
    """Return half the Euclidean distance between the Bloch vectors."""
    return 0.5 * math.dist((a.rx, a.ry, a.rz), (b.rx, b.ry, b.rz))


def _finite_scalar(value: float, name: str) -> float:
    if (isinstance(value, (bool, np.bool_)) or not isinstance(value, Real)
            or not math.isfinite(value)):
        raise ValueError(f"{name} must be a finite real scalar.")
    return float(value)


def _tolerance(tol: float) -> float:
    tol = _finite_scalar(tol, "tol")
    if tol < 0.0:
        raise ValueError("tol must be >= 0.")
    return tol


def _series(values, name: str) -> np.ndarray:
    if np.iscomplexobj(values):
        raise ValueError(f"{name} must be a finite real 1-D array.")
    try:
        result = np.asarray(values, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite real 1-D array.") from exc
    if result.ndim != 1 or result.size == 0 or not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must be a non-empty finite 1-D array.")
    return result


def _time_grid(t) -> np.ndarray:
    times = _series(t, "t")
    if not np.all(times[1:] > times[:-1]):
        raise ValueError("t must be strictly increasing.")
    return times


def _on_grid(values, name: str, times: np.ndarray) -> np.ndarray:
    result = _series(values, name)
    if len(result) != len(times):
        raise ValueError(f"{name} and t must have equal lengths.")
    return result


def trace_distance_backflow(D, t) -> float:
    """Discrete BLP-type backflow for a PRESELECTED reference state pair; this function does NOT
    perform the BLP maximization over initial states, and the result is
    grid-resolved (a revival between samples is not detected).

    Sum positive increments, not a rate or a time-weighted sum. For the
    pure-dephasing reference pair |+>, |->, the Bloch-vector difference is
    (2*kappa, 0, 0), so their trace distance is abs(kappa).
    """
    distances = _on_grid(D, "D", _time_grid(t))
    if np.any(distances < -1e-12) or np.any(distances > 1.0 + 1e-12):
        raise ValueError("D must lie in [0, 1] within absolute tolerance 1e-12.")
    return float(np.maximum(np.diff(distances), 0.0).sum())


def recovery_fraction(C0: float, C_free_tr: float, C_ctrl_tr: float, *, tol: float = 1e-12) -> float:
    """Return recovered/free-lost coherence without clamping or a zero-loss surrogate."""
    C0 = _finite_scalar(C0, "C0")
    C_free_tr = _finite_scalar(C_free_tr, "C_free_tr")
    C_ctrl_tr = _finite_scalar(C_ctrl_tr, "C_ctrl_tr")
    tol = _tolerance(tol)
    loss = C0 - C_free_tr
    if abs(loss) <= tol:
        raise ValueError("recovery fraction undefined: no recoverable coherence loss occurred")
    return (C_ctrl_tr - C_free_tr) / loss


class RecoveryClass(str, Enum):
    """Derived recovery categories; none of the RECOH-1 models establishes recovery."""

    NONE = "none"
    PROTECTION_ONLY = "protection_only"
    ACTIVE_REPHASING = "active_rephasing"
    ENVIRONMENTAL_BACKFLOW = "environmental_backflow"


def _has_qualifying_revival(values: np.ndarray, tol: float) -> bool:
    if len(values) < 3:
        return False
    # At each interior j, require distinct earlier i and later k; plateaus are allowed.
    earlier_max = np.maximum.accumulate(values)[:-2]
    later_max = np.maximum.accumulate(values[::-1])[::-1][2:]
    middle = values[1:-1]
    return bool(np.any((middle < earlier_max - tol) & (later_max > middle + tol)))


def classify_recovery(t, C_free, C_ctrl=None, *, backflow=None, tol: float = 1e-9) -> RecoveryClass:
    """Classify loss then revival on the supplied grid, not endpoint improvement alone.

    A revival requires i<j<k, C[j]<C[i]-tol and C[k]>C[j]+tol. Protection
    compares the final supplied samples; this API has no separate read time.
    """
    times = _time_grid(t)
    free = _on_grid(C_free, "C_free", times)
    controlled = None if C_ctrl is None else _on_grid(C_ctrl, "C_ctrl", times)
    tol = _tolerance(tol)
    if backflow is not None:
        backflow = _finite_scalar(backflow, "backflow")
    free_revival = _has_qualifying_revival(free, tol)
    ctrl_revival = controlled is not None and _has_qualifying_revival(controlled, tol)
    if free_revival and backflow is not None and backflow > tol:
        return RecoveryClass.ENVIRONMENTAL_BACKFLOW
    if ctrl_revival and not free_revival:
        return RecoveryClass.ACTIVE_REPHASING
    if controlled is not None and not free_revival and not ctrl_revival:
        if controlled[-1] > free[-1] + tol:
            return RecoveryClass.PROTECTION_ONLY
    return RecoveryClass.NONE
