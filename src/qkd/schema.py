"""Version-aware results schema recognition for Phase 2A.

The simulator continues to emit the current v1 schema for now. This module
recognizes that v1 shape and the future v2.0 contract from docs/INTERFACES.md.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


class SchemaValidationError(ValueError):
    """Raised when a results payload does not match a known schema."""


V1_REQUIRED_KEYS = {
    "teleportation": {"frames", "average_fidelity", "classical_limit", "remaining_entangled_resource_kb", "plot"},
    "summary": {"headline_key_yield", "headline_fidelity"},
}

V2_REQUIRED_KEYS = {
    "run_metadata": {"timestamp", "config_hash", "eve_enabled", "eve_type"},
    "channel": {"transmittance", "werner_p", "intrinsic_qber", "slant_range_km", "elevation_deg"},
    "bb84": {
        "sifted_key_length",
        "qber",
        "gains",
        "y1_lower_bound",
        "e1_upper_bound",
        "secure_key_rate",
        "decoy_anomaly_score",
    },
    "teleportation": {"fidelity", "singlet_fraction", "classical_bound", "beats_classical", "margin"},
    "chsh": {"S", "classical_bound", "tsirelson_bound", "violates", "margin"},
    "physics_signals": {
        "qber",
        "decoy_anomaly_score",
        "chsh_margin",
        "teleportation_margin",
        "loss_rate",
        "secure_key_rate",
    },
}


def detect_results_schema(results: Mapping[str, Any]) -> str:
    """Return ``"1"`` or ``"2.0"`` when a known results schema is recognized."""

    if not isinstance(results, Mapping):
        raise SchemaValidationError("Results payload must be a mapping.")

    if results.get("schema_version") == "2.0":
        _require_sections(results, V2_REQUIRED_KEYS)
        return "2.0"

    _require_sections(results, V1_REQUIRED_KEYS)
    return "1"


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
