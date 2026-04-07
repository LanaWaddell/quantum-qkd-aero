import json
import os
import sys

import matplotlib.pyplot as plt


CURRENT_DIR = os.path.dirname(__file__)
SRC_DIR = os.path.dirname(CURRENT_DIR)
PROJECT_ROOT = os.path.dirname(SRC_DIR)
OUTPUTS_DIR = os.path.join(PROJECT_ROOT, "outputs")

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from qkd.teleportation import TeleportationMission, build_teleportation_results


def main():
    os.makedirs(OUTPUTS_DIR, exist_ok=True)

    teleport = TeleportationMission()
    frames, fidelities, resources = teleport.run_teleportation()

    plot_path = os.path.join(OUTPUTS_DIR, "qkd_teleportation.png")
    results_path = os.path.join(OUTPUTS_DIR, "results.json")

    fig, ax1 = plt.subplots(figsize=(10, 6))

    ax1.set_xlabel("Teleported Quantum Frames")
    ax1.set_ylabel("Teleportation Fidelity", color="blue")
    ax1.plot(frames, fidelities, color="blue", alpha=0.7)
    ax1.axhline(y=0.67, color="red", linestyle="--", label="Classical Limit")
    ax1.set_ylim(0.5, 1.0)
    ax1.legend(loc="upper left")

    ax2 = ax1.twinx()
    ax2.set_ylabel("Remaining Entangled Resource (Kb)", color="green")
    ax2.plot(frames, resources, color="green", linewidth=2)

    plt.title("Mission Lana: Quantum Teleportation Link")
    plt.savefig(plot_path)
    plt.close(fig)

    results = build_teleportation_results(
        frames,
        fidelities,
        resources,
        plot_path="outputs/qkd_teleportation.png",
    )

    with open(results_path, "w") as f:
        json.dump(results, f)

    print(
        "Dashboard Updated: "
        f"Yield {results['summary']['headline_key_yield']} | "
        f"Fidelity {results['summary']['headline_fidelity']}"
    )


if __name__ == "__main__":
    main()
