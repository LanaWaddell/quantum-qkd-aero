"""Results schema recognition for the v2 emitted artifact."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


class SchemaValidationError(ValueError):
    """Raised when a results payload does not match a known schema."""


# TODO(PR-D): This validator is still a RECOGNIZER, not a deep GUARD. PR-B
#   retires v1 and the pre-fibre orbital v2 stub, then keeps L1 key-shape
#   validation only. Implement L2 types (+reject NaN/inf), L3 ranges,
#   L4 constants, and L5 cross-field consistency later per
#   docs/SCHEMA_HARDENING_2B.md.
def detect_results_schema(results: Mapping[str, Any]) -> str:
    """Return ``"2.0"`` when the emitted results schema is recognized."""

    if not isinstance(results, Mapping):
        raise SchemaValidationError("Results payload must be a mapping.")

    if results.get("schema_version") != "2.0":
        raise SchemaValidationError("Unsupported or missing schema_version.")

    _require_v2_shape(results)
    return "2.0"


def validate_results_schema(results: Mapping[str, Any]) -> bool:
    """Return True when the payload matches a supported results schema."""

    detect_results_schema(results)
    return True


def load_results(path: str | Path) -> dict[str, Any]:
    """Load a JSON results file and validate that its schema is recognized."""

    with open(path, "r", encoding="utf-8") as f:
        results = json.load(f)
    detect_results_schema(results)
    return results


def _require_sections(results: Mapping[str, Any], required: Mapping[str, set[str]]) -> None:
    for section, keys in required.items():
        if section not in results or not isinstance(results[section], Mapping):
            raise SchemaValidationError(f"Missing or invalid section: {section}")
        missing = keys - set(results[section])
        if missing:
            missing_keys = ", ".join(sorted(missing))
            raise SchemaValidationError(f"Missing keys in {section}: {missing_keys}")


def _require_v2_shape(results: Mapping[str, Any]) -> None:
    _require_sections(
        results,
        {
            "link": {"medium", "topology", "protocol"},
            "teleportation": {"frames", "average_fidelity", "classical_limit", "plot"},
            "summary": {"headline_key_yield", "headline_fidelity"},
            "profile": {
                "axis",
                "transmittance",
                "loss_db",
                "secure_key_rate_per_pulse",
                "effective_werner_p",
                "fidelity",
                "aggregates",
            },
            "mission": {
                "pulse_repetition_rate_hz",
                "intensities",
                "detector",
                "sky_condition",
            },
            "run_metadata": {"generator", "pipeline", "physics_mode"},
            "provenance": set(),
        },
    )
    _require_sections(results["profile"], {"axis": {"name", "values"}})
    _require_sections(
        results["profile"],
        {
            "aggregates": {
                "min_loss_db",
                "min_loss_axis_value",
                "secure_key_yield_bits",
                "mean_fidelity",
            },
        },
    )
    _require_sections(
        results["mission"],
        {
            "intensities": {"signal", "decoy", "vacuum"},
            "detector": {
                "detection_efficiency",
                "dark_count_prob",
                "error_correction_efficiency",
            },
        },
    )
    if "geometry" in results:
        _require_sections(
            results,
            {"geometry": {"elevation_deg", "slant_range_km", "min_loss"}},
        )
        _require_sections(
            results["geometry"],
            {"min_loss": {"elevation_deg", "slant_range_km"}},
        )
