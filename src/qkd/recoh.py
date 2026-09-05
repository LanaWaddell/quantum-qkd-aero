"""RECOH-1/RECOH-2 derived stored-state witnesses, recovery classification, and
the rung-2 recovery report.

Configuration names in this module (`dephasing_model`, `noise_kernel`, `D_phi`,
`tau_c`) follow SPEC-memory-lifetime-adr0003 (ratified 2026-09-03, `81c97ed`);
`kappa_ideal` corresponds to `identity_state_evolution`.

RecoveryClass is a derived output, not a configured capability. RECOH-1 is
an instrument: every supplied free-evolution model returns NONE. Synthetic
curve self-checks do not establish a physical recovery model or rung-2 claim.

RECOH-2 adds `recovery_report`, which constructs both the free and
pi-pulse-controlled trajectories from an `EchoModel` (matching by
construction), evaluates the purity-identity guard, and reports the recovered
fraction at the predeclared read times. It attempts rung 2 (mechanism
ACTIVE_REPHASING) only on the single-qubit reference model declared in
docs/RECOH_2_PLAN.md; recovery is unconditioned by construction.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from numbers import Real

import numpy as np

from qkd.mem_state import (
    EchoModel, StoredQubit, echo_peak_time, evolve, purity, stored_state_at,
    var_free,
)

__all__ = [
    "coherence_l1", "pure_target_fidelity", "trace_distance",
    "trace_distance_backflow", "recovery_fraction", "RecoveryClass",
    "classify_recovery", "RecoveryStatus", "GuardStatus", "GuardResult",
    "RecoveryReport", "echo_grid", "purity_guard", "recovery_report",
]

_UNRESOLVED_LOSS_TOL = 1e-12


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


# --------------------------------------------------------------------------
# RECOH-2: rung-2 report contract.
# --------------------------------------------------------------------------


class RecoveryStatus(str, Enum):
    """Top-level outcome of a rung-2 recovery attempt; see recovery_report."""

    AVAILABLE = "available"
    NO_LOSS = "no_loss"
    NO_PEAK = "no_peak"
    UNRESOLVED_LOSS = "unresolved_loss"


class GuardStatus(str, Enum):
    """Outcome of the model-consistency purity-identity guard."""

    PASSED = "passed"
    FAILED = "failed"
    NOT_EVALUATED = "not_evaluated"


@dataclass(frozen=True)
class GuardResult:
    """Purity-identity guard outcome; not an independent mechanism witness."""

    status: GuardStatus
    max_abs_dev: float | None


@dataclass(frozen=True)
class RecoveryReport:
    """Rung-2 recovery report; see docs/RECOH_2_PLAN.md for the full contract."""

    recovery_status: RecoveryStatus
    reason: str
    recovery_class: RecoveryClass
    valid: bool
    t_peak: float | None
    R_peak: float | None
    R_2tau: float | None
    C_free_peak: float | None
    C_ctrl_peak: float | None
    backflow_free: float
    purity_guard: GuardResult
    fidelity: dict


def echo_grid(model: EchoModel, n: int) -> np.ndarray:
    """Return a strictly increasing, deduplicated grid on [0, 2*tau] with n>=8
    uniform interior points plus the exact insertion of tau and (when defined)
    t_peak.
    """
    if isinstance(n, bool) or not isinstance(n, (int, np.integer)):
        raise ValueError("n must be an integer >= 8.")
    if n < 8:
        raise ValueError("n must be >= 8.")
    two_tau = 2.0 * model.tau
    base = np.linspace(0.0, two_tau, int(n))
    extra = [model.tau]
    t_peak = echo_peak_time(model)
    if t_peak is not None:
        extra.append(t_peak)
    return np.unique(np.concatenate([base, np.asarray(extra, dtype=float)]))


def purity_guard(states_free, states_ctrl, rz0) -> GuardResult:
    """Check P(t) == (1 + rz0**2 + C_l1(t)**2)/2 on every supplied state, to 1e-12.

    Both None -> not_evaluated; exactly one None -> ValueError.
    """
    if states_free is None and states_ctrl is None:
        return GuardResult(GuardStatus.NOT_EVALUATED, None)
    if states_free is None or states_ctrl is None:
        raise ValueError("states_free and states_ctrl must both be provided or both be None.")
    rz0 = _finite_scalar(rz0, "rz0")
    deviations = []
    for state in (*states_free, *states_ctrl):
        expected = (1.0 + rz0**2 + coherence_l1(state) ** 2) / 2.0
        deviations.append(abs(purity(state) - expected))
    max_dev = max(deviations) if deviations else 0.0
    status = GuardStatus.PASSED if max_dev <= 1e-12 else GuardStatus.FAILED
    return GuardResult(status, max_dev)


def _fidelity_at(model: EchoModel, t: float, r0_is_pure: bool) -> float | str:
    ctrl_state = stored_state_at(model, t, controlled=True)
    if r0_is_pure:
        return pure_target_fidelity(ctrl_state, model.r0)
    return "not_available"


def recovery_report(model: EchoModel, n_grid: int) -> RecoveryReport:
    """Construct both trajectories from `model` and report the rung-2 recovery
    outcome. See docs/RECOH_2_PLAN.md for the full precedence and field
    contract. Unconditioned by construction: no branch on outcomes.
    """
    C0 = coherence_l1(model.r0)
    grid = echo_grid(model, n_grid)
    free_states = evolve(model, grid, controlled=False)
    ctrl_states = evolve(model, grid, controlled=True)
    C_free = np.array([coherence_l1(s) for s in free_states])
    C_ctrl = np.array([coherence_l1(s) for s in ctrl_states])

    guard = purity_guard(free_states, ctrl_states, model.r0.rz)
    valid = guard.status is GuardStatus.PASSED

    w_free_grid = np.exp(-np.asarray(var_free(model, grid), dtype=float) / 2.0)
    backflow_free = trace_distance_backflow(w_free_grid, grid)

    r0_norm = math.hypot(model.r0.rx, model.r0.ry, model.r0.rz)
    r0_is_pure = math.isclose(r0_norm, 1.0, rel_tol=0.0, abs_tol=1e-9)
    two_tau = 2.0 * model.tau
    t_peak = echo_peak_time(model)
    fidelity = {"2tau": _fidelity_at(model, two_tau, r0_is_pure)}
    if t_peak is not None:
        fidelity["t_peak"] = _fidelity_at(model, t_peak, r0_is_pure)

    def _report(status: RecoveryStatus, reason: str, *, recovery_class=RecoveryClass.NONE,
                t_peak_field=None, R_peak=None, R_2tau=None,
                C_free_peak=None, C_ctrl_peak=None) -> RecoveryReport:
        return RecoveryReport(
            recovery_status=status, reason=reason, recovery_class=recovery_class,
            valid=valid, t_peak=t_peak_field, R_peak=R_peak, R_2tau=R_2tau,
            C_free_peak=C_free_peak, C_ctrl_peak=C_ctrl_peak,
            backflow_free=backflow_free, purity_guard=guard, fidelity=fidelity,
        )

    if C0 == 0.0:
        return _report(RecoveryStatus.NO_LOSS, "zero initial transverse coherence")
    if model.D_phi == 0.0:
        return _report(RecoveryStatus.NO_LOSS, "zero noise intensity")
    if model.tau_c is None:
        return _report(RecoveryStatus.NO_PEAK, "white kernel: no post-pulse revival", R_2tau=0.0)

    C_free_2tau = coherence_l1(stored_state_at(model, two_tau, controlled=False))
    for label, t_r in (("t_peak", t_peak), ("2tau", two_tau)):
        C_free_tr = C_free_2tau if label == "2tau" else coherence_l1(
            stored_state_at(model, t_r, controlled=False)
        )
        if abs(C0 - C_free_tr) <= _UNRESOLVED_LOSS_TOL:
            return _report(RecoveryStatus.UNRESOLVED_LOSS, f"unresolved loss at {label}")

    C_free_peak = coherence_l1(stored_state_at(model, t_peak, controlled=False))
    C_ctrl_peak = coherence_l1(stored_state_at(model, t_peak, controlled=True))
    C_ctrl_2tau = coherence_l1(stored_state_at(model, two_tau, controlled=True))
    R_peak = recovery_fraction(C0, C_free_peak, C_ctrl_peak)
    R_2tau = recovery_fraction(C0, C_free_2tau, C_ctrl_2tau)
    recovery_class = classify_recovery(grid, C_free, C_ctrl, backflow=backflow_free)
    return _report(
        RecoveryStatus.AVAILABLE, "recovery evaluated", recovery_class=recovery_class,
        t_peak_field=t_peak, R_peak=R_peak, R_2tau=R_2tau,
        C_free_peak=C_free_peak, C_ctrl_peak=C_ctrl_peak,
    )
