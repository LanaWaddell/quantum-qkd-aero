import math
import statistics
from dataclasses import dataclass

import numpy as np

from qkd.channel import fidelity_noise


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


class TeleportationMission:
    def __init__(
        self,
        entangled_kb=15.0,
        use_channel_model=False,
        p_loss=0.0,
        p_flip=0.0,
        noise_strength=0.05,
    ):
        self.resource = entangled_kb  # Based on your last graph
        self.use_channel_model = use_channel_model
        self.p_loss = p_loss
        self.p_flip = p_flip
        self.noise_strength = noise_strength

    def run_teleportation(self):
        # We'll try to teleport 1000 'Quantum Frames'
        frames = list(range(1000))
        fidelities = []
        consumed_resource = []

        current_resource = self.resource

        for f in frames:
            # Teleportation fidelity is affected by the 'purity' of our entanglement
            # We'll simulate a high-quality link (0.85 average fidelity)
            base_fidelity = 0.85

            if self.use_channel_model:
                fidelity = fidelity_noise(
                    frame_index=f,
                    base_fidelity=base_fidelity,
                    noise_strength=self.noise_strength,
                    p_loss=self.p_loss,
                    p_flip=self.p_flip,
                )
            else:
                noise = math.sin(f / 50) * 0.05  # Simulated environmental jitter
                fidelity = base_fidelity + noise

            fidelities.append(fidelity)

            # Each teleportation 'consumes' one entangled pair
            current_resource -= 0.01  # 10 bits per frame
            consumed_resource.append(current_resource)

        return frames, fidelities, consumed_resource


def build_teleportation_results(frames, fidelities, resources, plot_path):
    average_fid = statistics.mean(fidelities)
    current_yield = resources[-1]

    return {
        "teleportation": {
            "frames": len(frames),
            "average_fidelity": round(average_fid, 3),
            "classical_limit": 0.67,
            "remaining_entangled_resource_kb": round(current_yield, 2),
            "plot": plot_path,
        },
        "summary": {
            "headline_key_yield": f"{current_yield:.2f} Kb",
            "headline_fidelity": f"{average_fid:.3f}",
        },
    }
