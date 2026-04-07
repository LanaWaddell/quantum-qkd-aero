import math
import statistics

from qkd.channel import fidelity_noise


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
