import json
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

from qkd.mission import simulate_pass
from qkd.provenance import validate_provenance


def main():
    os.makedirs(OUTPUTS_DIR, exist_ok=True)

    result = simulate_pass()

    plot_path = os.path.join(OUTPUTS_DIR, "qkd_teleportation.png")
    results_path = os.path.join(OUTPUTS_DIR, "results.json")

    fig, ax1 = plt.subplots(figsize=(10, 6))

    ax1.set_xlabel("Satellite pass time (s)")
    ax1.set_ylabel("Channel loss (dB)", color="blue")
    ax1.plot(result.time_s, result.loss_db, color="blue", alpha=0.75, label="Channel loss")
    ax1.scatter(
        [result.time_s[result.min_loss_index]],
        [result.min_loss_db],
        color="blue",
        s=30,
        zorder=3,
    )
    ax1.tick_params(axis="y", labelcolor="blue")
    ax1.legend(loc="upper left")

    ax2 = ax1.twinx()
    ax2.set_ylabel("Teleportation fidelity", color="green")
    ax2.plot(
        result.time_s,
        result.fidelity,
        color="green",
        linewidth=2,
        label="Computed fidelity",
    )
    ax2.axhline(
        y=result.classical_bound,
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

    results = _build_results(result, plot_path="outputs/qkd_teleportation.png")
    validate_provenance(results, results["provenance"])

    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results, f)

    print(
        "Dashboard Updated: "
        f"Min loss {result.min_loss_db:.1f} dB | "
        f"Fidelity {result.mean_fidelity:.3f}"
    )


def _build_results(result, *, plot_path):
    headline_key_yield = f"{result.secure_key_yield_bits / 1_000.0:.2f} Kb"

    return {
        "teleportation": {
            "frames": len(result.time_s),
            "average_fidelity": round(result.mean_fidelity, 3),
            "classical_limit": result.classical_bound,
            "plot": plot_path,
        },
        "summary": {
            "headline_key_yield": headline_key_yield,
            "headline_fidelity": f"{result.mean_fidelity:.3f}",
        },
        "pass_profile": {
            "time_s": result.time_s,
            "elevation_deg": result.elevation_deg,
            "slant_range_km": result.slant_range_km,
            "transmittance": result.transmittance,
            "loss_db": result.loss_db,
            "secure_key_rate_per_pulse": result.secure_key_rate_per_pulse,
            "effective_werner_p": result.effective_werner_p,
            "fidelity": result.fidelity,
            "min_loss_db": result.min_loss_db,
            "min_loss_time_s": result.time_s[result.min_loss_index],
            "min_loss_elevation_deg": result.elevation_deg[result.min_loss_index],
            "min_loss_slant_range_km": result.slant_range_km[result.min_loss_index],
            "secure_key_yield_bits": result.secure_key_yield_bits,
            "mean_fidelity": result.mean_fidelity,
        },
        "mission": result.mission,
        "provenance": result.provenance,
        "run_metadata": {
            "generator": "run.py",
            "pipeline": "mission.simulate_pass",
            "physics_mode": "computed",
        },
    }


if __name__ == "__main__":
    main()
