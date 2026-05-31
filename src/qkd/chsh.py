"""Computed CHSH values for Werner-state entanglement checks."""

import math
from dataclasses import dataclass

import numpy as np


@dataclass
class CHSHResult:
    S: float
    classical_bound: float
    tsirelson_bound: float
    violates: bool
    margin: float
    method: str


def chsh_value(werner_p: float, *, method: str = "analytic") -> CHSHResult:
    if not 0.0 <= werner_p <= 1.0:
        raise ValueError("werner_p must be in [0, 1].")

    classical_bound = 2.0
    tsirelson_bound = 2 * math.sqrt(2)

    if method == "analytic":
        s_value = tsirelson_bound * werner_p
    elif method == "numeric":
        rho = _werner_state(werner_p)
        chsh_operator = _chsh_operator()
        s_value = float(np.real(np.trace(rho @ chsh_operator)))
    else:
        raise ValueError(f"Unknown CHSH method: {method}")

    return CHSHResult(
        S=s_value,
        classical_bound=classical_bound,
        tsirelson_bound=tsirelson_bound,
        violates=_strictly_above(s_value, classical_bound),
        margin=s_value - classical_bound,
        method=method,
    )


def _werner_state(werner_p: float) -> np.ndarray:
    bell_projector = _phi_plus_projector()
    maximally_mixed = np.eye(4, dtype=complex) / 4
    return (werner_p * bell_projector) + ((1 - werner_p) * maximally_mixed)


def _phi_plus_projector() -> np.ndarray:
    phi_plus = np.array([1, 0, 0, 1], dtype=complex) / math.sqrt(2)
    return np.outer(phi_plus, np.conjugate(phi_plus))


def _chsh_operator() -> np.ndarray:
    sigma_x = np.array([[0, 1], [1, 0]], dtype=complex)
    sigma_z = np.array([[1, 0], [0, -1]], dtype=complex)

    a0 = sigma_z
    a1 = sigma_x
    b0 = (sigma_z + sigma_x) / math.sqrt(2)
    b1 = (sigma_z - sigma_x) / math.sqrt(2)

    return (
        np.kron(a0, b0)
        + np.kron(a0, b1)
        + np.kron(a1, b0)
        - np.kron(a1, b1)
    )


def _strictly_above(value: float, bound: float) -> bool:
    return value > bound and not math.isclose(value, bound, abs_tol=1e-12)
