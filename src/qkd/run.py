import json
import math
import os
import sys

CURRENT_DIR = os.path.dirname(__file__)
SRC_DIR = os.path.dirname(CURRENT_DIR)
PROJECT_ROOT = os.path.dirname(SRC_DIR)
OUTPUTS_DIR = os.path.join(PROJECT_ROOT, "outputs")
MATPLOTLIB_CACHE_DIR = os.path.join(PROJECT_ROOT, ".cache", "matplotlib")

os.makedirs(MATPLOTLIB_CACHE_DIR, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", MATPLOTLIB_CACHE_DIR)

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from qkd.channel import channel_state
from qkd.orbit import satellite_pass
from qkd.teleportation import teleportation_fidelity


def main():
    os.makedirs(OUTPUTS_DIR, exist_ok=True)

    pass_geometry = satellite_pass()
    channel_states = [
        channel_state(
            elevation_deg=elevation_deg,
            slant_range_km=slant_range_km,
        )
        for elevation_deg, slant_range_km in zip(
            pass_geometry.elevation_deg,
            pass_geometry.slant_range_km,
        )
    ]

    transmittance = [state.transmittance for state in channel_states]
    loss_db = [_channel_loss_db(eta) for eta in transmittance]
    min_loss_index = min(range(len(loss_db)), key=loss_db.__getitem__)
    min_loss_db = loss_db[min_loss_index]
    strongest_link_state = channel_states[min_loss_index]

    teleportation = teleportation_fidelity(strongest_link_state.werner_p)
    fidelities = [teleportation.fidelity for _ in pass_geometry.time_s]

    plot_path = os.path.join(OUTPUTS_DIR, "qkd_teleportation.png")
    results_path = os.path.join(OUTPUTS_DIR, "results.json")

    fig, ax1 = plt.subplots(figsize=(10, 6))

    ax1.set_xlabel("Satellite pass time (s)")
    ax1.set_ylabel("Channel loss (dB)", color="blue")
    ax1.plot(pass_geometry.time_s, loss_db, color="blue", alpha=0.75, label="Channel loss")
    ax1.scatter(
        [pass_geometry.time_s[min_loss_index]],
        [min_loss_db],
        color="blue",
        s=30,
        zorder=3,
    )
    ax1.tick_params(axis="y", labelcolor="blue")
    ax1.legend(loc="upper left")

    ax2 = ax1.twinx()
    ax2.set_ylabel("Teleportation fidelity", color="green")
    ax2.plot(
        pass_geometry.time_s,
        fidelities,
        color="green",
        linewidth=2,
        label="Computed fidelity",
    )
    ax2.axhline(
        y=teleportation.classical_bound,
        color="red",
        linestyle="--",
        label="Classical limit",
    )
    ax2.set_ylim(0.5, 1.0)
    ax2.tick_params(axis="y", labelcolor="green")
    ax2.legend(loc="lower right")

    plt.title("Mission Lana: Satellite QKD Link")
    plt.tight_layout()
    plt.savefig(plot_path)
    plt.close(fig)

    results = _build_results(
        pass_geometry=pass_geometry,
        transmittance=transmittance,
        loss_db=loss_db,
        min_loss_index=min_loss_index,
        teleportation_fidelity_value=teleportation.fidelity,
        plot_path="outputs/qkd_teleportation.png",
    )

    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results, f)

    print(
        "Dashboard Updated: "
        f"Min loss {min_loss_db:.1f} dB | "
        f"Fidelity {teleportation.fidelity:.3f}"
    )


def _channel_loss_db(eta):
    if eta <= 0.0:
        return math.inf
    return -10.0 * math.log10(eta)


def _build_results(
    *,
    pass_geometry,
    transmittance,
    loss_db,
    min_loss_index,
    teleportation_fidelity_value,
    plot_path,
):
    min_loss_db = loss_db[min_loss_index]
    remaining_entangled_resource_kb = 5.0  # TODO(2B-decoy): replace with key/resource accounting.
    headline_key_yield = f"{remaining_entangled_resource_kb:.2f} Kb"  # TODO(2B-decoy): replace with SKR.

    return {
        "teleportation": {
            "frames": len(pass_geometry.time_s),
            "average_fidelity": round(teleportation_fidelity_value, 3),
            "classical_limit": 0.67,
            "remaining_entangled_resource_kb": remaining_entangled_resource_kb,
            "plot": plot_path,
        },
        "summary": {
            "headline_key_yield": headline_key_yield,
            "headline_fidelity": f"{teleportation_fidelity_value:.3f}",
        },
        "pass_profile": {
            "time_s": pass_geometry.time_s,
            "elevation_deg": pass_geometry.elevation_deg,
            "slant_range_km": pass_geometry.slant_range_km,
            "transmittance": transmittance,
            "loss_db": loss_db,
            "min_loss_db": min_loss_db,
            "min_loss_time_s": pass_geometry.time_s[min_loss_index],
            "min_loss_elevation_deg": pass_geometry.elevation_deg[min_loss_index],
            "min_loss_slant_range_km": pass_geometry.slant_range_km[min_loss_index],
        },
    }


if __name__ == "__main__":
    main()
