import math
from dataclasses import dataclass

import numpy as np


@dataclass
class TeleportationResult:
    fidelity: float
    singlet_fraction: float
    classical_bound: float
    beats_classical: bool
    margin: float
    method: str


def teleportation_fidelity(werner_p: float, *, method: str = "analytic") -> TeleportationResult:
    if not 0.0 <= werner_p <= 1.0:
        raise ValueError("werner_p must be in [0, 1].")

    classical_bound = 2 / 3

    if method == "analytic":
        fidelity = (1 + werner_p) / 2
        singlet_fraction = (1 + 3 * werner_p) / 4
    elif method == "numeric":
        rho = _werner_state(werner_p)
        bell_projector = _phi_plus_projector()
        singlet_fraction = float(np.real(np.trace(rho @ bell_projector)))
        fidelity = float((2 * singlet_fraction + 1) / 3)
    elif method == "qiskit":
        fidelity, singlet_fraction = _qiskit_teleportation_metrics(werner_p)
    else:
        raise ValueError(f"Unknown teleportation fidelity method: {method}")

    return TeleportationResult(
        fidelity=fidelity,
        singlet_fraction=singlet_fraction,
        classical_bound=classical_bound,
        beats_classical=_strictly_above(fidelity, classical_bound),
        margin=fidelity - classical_bound,
        method=method,
    )


def _werner_state(werner_p: float) -> np.ndarray:
    bell_projector = _phi_plus_projector()
    maximally_mixed = np.eye(4, dtype=complex) / 4
    return (werner_p * bell_projector) + ((1 - werner_p) * maximally_mixed)


def _phi_plus_projector() -> np.ndarray:
    phi_plus = np.array([1, 0, 0, 1], dtype=complex) / math.sqrt(2)
    return np.outer(phi_plus, np.conjugate(phi_plus))


def _strictly_above(value: float, bound: float) -> bool:
    return value > bound and not math.isclose(value, bound, abs_tol=1e-12)


def _qiskit_teleportation_metrics(werner_p: float) -> tuple[float, float]:
    from qiskit import QuantumCircuit
    from qiskit.quantum_info import DensityMatrix, Kraus, Statevector, partial_trace

    lam = 1.0 - werner_p
    kraus = _depolarizing_kraus(lam)

    circuit = QuantumCircuit(4)
    circuit.h(0)
    circuit.cx(0, 1)
    circuit.h(2)
    circuit.cx(2, 3)

    rho = DensityMatrix(Statevector.from_instruction(circuit))
    rho = rho.evolve(Kraus(kraus), qargs=[3])

    resource_state = partial_trace(rho, [0, 1])
    singlet_fraction = _density_matrix_singlet_fraction(resource_state.data)

    teleport = QuantumCircuit(4)
    teleport.cx(1, 2)
    teleport.h(1)
    teleport.cx(2, 3)
    teleport.cz(1, 3)
    rho = rho.evolve(teleport)

    choi_state = partial_trace(rho, [1, 2])
    entanglement_fidelity = _density_matrix_singlet_fraction(choi_state.data)
    average_fidelity = (2 * entanglement_fidelity + 1) / 3

    return average_fidelity, singlet_fraction


def _depolarizing_kraus(lam: float) -> list[np.ndarray]:
    sigma_x = np.array([[0, 1], [1, 0]], dtype=complex)
    sigma_y = np.array([[0, -1j], [1j, 0]], dtype=complex)
    sigma_z = np.array([[1, 0], [0, -1]], dtype=complex)
    identity = np.eye(2, dtype=complex)

    return [
        math.sqrt(1.0 - (3.0 * lam / 4.0)) * identity,
        math.sqrt(lam / 4.0) * sigma_x,
        math.sqrt(lam / 4.0) * sigma_y,
        math.sqrt(lam / 4.0) * sigma_z,
    ]


def _density_matrix_singlet_fraction(density_matrix: np.ndarray) -> float:
    phi_plus = np.array([1.0, 0.0, 0.0, 1.0], dtype=complex) / math.sqrt(2.0)
    return float(np.real(np.conjugate(phi_plus) @ np.asarray(density_matrix) @ phi_plus))
