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

from qkd.mission import simulate_fibre_sweep
from qkd.provenance import validate_provenance
from qkd.schema import validate_results_schema


def main():
    os.makedirs(OUTPUTS_DIR, exist_ok=True)

    result = simulate_fibre_sweep()

    plot_path = os.path.join(OUTPUTS_DIR, "qkd_fibre_sweep.png")
    results_path = os.path.join(OUTPUTS_DIR, "fibre_results.json")

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.set_xlabel("Fibre length (km)")
    ax.set_ylabel("Secure key rate (bits/pulse)")
    ax.plot(
        result.length_km,
        result.secure_key_rate_per_pulse,
        color="purple",
        linewidth=2,
        label="Secure key rate",
    )
    if result.max_secure_distance_km is not None:
        ax.axvline(
            result.max_secure_distance_km,
            color="black",
            linestyle="--",
            linewidth=1,
            label="Max secure distance",
        )
    ax.set_ylim(bottom=0.0)
    ax.legend(loc="upper right")
    plt.title("Dedicated-Fibre Decoy-BB84 Length Sweep")
    plt.tight_layout()
    plt.savefig(plot_path)
    plt.close(fig)

    results = _build_results(result, plot_path="outputs/qkd_fibre_sweep.png")
    validate_results_schema(results)
    validate_provenance(results, results["provenance"])

    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results, f)

    print(
        "Fibre Sweep Updated: "
        f"Max secure distance {_format_distance(result.max_secure_distance_km)} | "
        f"SKR@0 km {result.secure_key_rate_per_pulse[0]:.3e} bits/pulse"
    )


def _build_results(result, *, plot_path):
    bracket = result.secure_distance_bracket
    headline_key_rate = (
        f"{result.secure_key_rate_per_pulse[0]:.3e} bits/pulse @ "
        f"{result.length_km[0]:.1f} km"
    )

    return {
        "schema_version": "2.0",
        "link": {
            "medium": "fibre",
            "topology": "point_to_point",
            "protocol": "decoy_bb84",
        },
        "teleportation": {
            "frames": len(result.length_km),
            "average_fidelity": round(result.mean_fidelity, 3),
            "classical_limit": result.classical_bound,
            "plot": plot_path,
        },
        "summary": {
            "headline_key_yield": headline_key_rate,
            "headline_fidelity": f"{result.mean_fidelity:.3f}",
            "headline_max_secure_distance": _format_distance(result.max_secure_distance_km),
        },
        "profile": {
            "axis": {
                "name": "length_km",
                "values": result.length_km,
            },
            "transmittance": result.transmittance,
            "loss_db": result.loss_db,
            "secure_key_rate_per_pulse": result.secure_key_rate_per_pulse,
            "effective_werner_p": result.effective_werner_p,
            "fidelity": result.fidelity,
            "aggregates": {
                "min_loss_db": result.min_loss_db,
                "min_loss_axis_value": result.length_km[result.min_loss_index],
                "secure_key_yield_bits": result.secure_key_yield_bits,
                "mean_fidelity": result.mean_fidelity,
                "max_secure_distance_km": result.max_secure_distance_km,
                "secure_distance_bracket": {
                    "last_positive_length_km": bracket.last_positive_length_km,
                    "last_positive_secure_key_rate_per_pulse": (
                        bracket.last_positive_secure_key_rate_per_pulse
                    ),
                    "first_non_positive_length_km": bracket.first_non_positive_length_km,
                    "first_non_positive_secure_key_rate_per_pulse": (
                        bracket.first_non_positive_secure_key_rate_per_pulse
                    ),
                },
            },
        },
        "mission": result.mission,
        "provenance": result.provenance,
        "run_metadata": {
            "generator": "run_fibre.py",
            "pipeline": "mission.simulate_fibre_sweep",
            "physics_mode": "computed",
            "max_secure_distance_definition": (
                "last length sample with positive secure_key_rate_per_pulse; "
                "secure_distance_bracket records the first non-positive sample, "
                "so the grid-resolution caveat is auditable"
            ),
        },
    }


def _format_distance(distance_km):
    if distance_km is None:
        return "none"
    return f"{distance_km:.1f} km"


if __name__ == "__main__":
    main()
