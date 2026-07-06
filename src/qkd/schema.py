"""Results schema recognition and deep validation for the v2 emitted artifact."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from numbers import Real
from pathlib import Path
from typing import Any

from qkd.provenance import ProvenanceValidationError, validate_provenance


class SchemaValidationError(ValueError):
    """Raised when a results payload does not match a known schema."""


VALID_LINK_MEDIA = frozenset({"atmospheric", "fibre"})
VALID_LINK_TOPOLOGIES = frozenset({"point_to_point"})
VALID_LINK_PROTOCOLS = frozenset({"decoy_bb84"})
VALID_PROFILE_AXES = frozenset({"time_s", "length_km"})

DECLARED_SCHEMA_EXTENSIONS: dict[str, set[str]] = {}
"""Explicitly allowed extension keys by containing section path.

Unknown top-level sections and unknown keys inside known sections fail unless
they are declared here. A declared key is treated as an extension-owned subtree.
"""

ATOL = 1e-6
CONST_ATOL = 1e-3
ROUNDED_FIDELITY_ATOL = 5e-4
CLASSICAL_TELEPORTATION_LIMIT = 2.0 / 3.0

_ALLOWED_KEYS_BY_PATH = {
    "": {
        "schema_version",
        "link",
        "teleportation",
        "summary",
        "profile",
        "geometry",
        "mission",
        "provenance",
        "run_metadata",
    },
    "link": {"medium", "topology", "protocol"},
    "teleportation": {"frames", "average_fidelity", "classical_limit", "plot"},
    "summary": {
        "headline_key_yield",
        "headline_fidelity",
        "headline_max_secure_distance",
    },
    "profile": {
        "axis",
        "transmittance",
        "loss_db",
        "secure_key_rate_per_pulse",
        "effective_werner_p",
        "fidelity",
        "aggregates",
    },
    "profile.axis": {"name", "values"},
    "profile.aggregates": {
        "min_loss_db",
        "min_loss_axis_value",
        "secure_key_yield_bits",
        "mean_fidelity",
        "max_secure_distance_km",
        "secure_distance_bracket",
    },
    "profile.aggregates.secure_distance_bracket": {
        "last_positive_length_km",
        "last_positive_secure_key_rate_per_pulse",
        "first_non_positive_length_km",
        "first_non_positive_secure_key_rate_per_pulse",
    },
    "geometry": {"elevation_deg", "slant_range_km", "min_loss"},
    "geometry.min_loss": {"elevation_deg", "slant_range_km"},
    "mission": {
        "pulse_repetition_rate_hz",
        "intensities",
        "detector",
        "sky_condition",
        "fibre",
    },
    "mission.intensities": {"signal", "decoy", "vacuum"},
    "mission.detector": {
        "detection_efficiency",
        "dark_count_prob",
        "error_correction_efficiency",
    },
    "mission.fibre": {
        "attenuation_db_km",
        "fixed_loss_db",
        "intrinsic_qber",
        "dark_count_prob",
        "werner_p",
    },
    "run_metadata": {
        "generator",
        "pipeline",
        "physics_mode",
        "max_secure_distance_definition",
    },
}


def detect_results_schema(results: Mapping[str, Any]) -> str:
    """Return ``"2.0"`` when the emitted results schema is recognized."""

    if not isinstance(results, Mapping):
        raise SchemaValidationError("Results payload must be a mapping.")

    if results.get("schema_version") != "2.0":
        raise SchemaValidationError("Unsupported or missing schema_version.")

    _require_v2_shape(results)
    return "2.0"


def validate_results_schema(results: Mapping[str, Any], *, deep: bool = True) -> bool:
    """Return True when the payload matches the supported results schema."""

    detect_results_schema(results)
    if deep:
        _validate_declared_vocabulary(results)
        _validate_types(results)
        _validate_ranges(results)
        _validate_constants(results)
        _validate_consistency(results)
        try:
            validate_provenance(results, results["provenance"])
        except ProvenanceValidationError as exc:
            raise SchemaValidationError(str(exc)) from exc
    return True


def load_results(path: str | Path, *, deep: bool = True) -> dict[str, Any]:
    """Load a JSON results file and validate its schema."""

    with open(path, "r", encoding="utf-8") as f:
        results = json.load(f)
    validate_results_schema(results, deep=deep)
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


def _validate_declared_vocabulary(results: Mapping[str, Any]) -> None:
    _validate_known_keys(results, "")


def _validate_known_keys(value: Any, path: str) -> None:
    if not isinstance(value, Mapping):
        return
    if path == "provenance":
        return

    allowed = _ALLOWED_KEYS_BY_PATH.get(path)
    if allowed is None:
        raise SchemaValidationError(f"No schema vocabulary declared for {path}.")

    declared_extensions = DECLARED_SCHEMA_EXTENSIONS.get(path, set())
    for key, child in value.items():
        child_path = _join_path(path, key)
        if key in declared_extensions:
            continue
        if key not in allowed:
            raise SchemaValidationError(f"Undeclared schema key: {child_path}")
        _validate_known_keys(child, child_path)


def _validate_types(results: Mapping[str, Any]) -> None:
    _require_string(results["schema_version"], "schema_version")

    for key in ("medium", "topology", "protocol"):
        _require_string(results["link"][key], f"link.{key}")

    teleportation = results["teleportation"]
    _require_int(teleportation["frames"], "teleportation.frames")
    _require_finite_number(
        teleportation["average_fidelity"],
        "teleportation.average_fidelity",
    )
    _require_finite_number(
        teleportation["classical_limit"],
        "teleportation.classical_limit",
    )
    _require_string(teleportation["plot"], "teleportation.plot")

    for key, value in results["summary"].items():
        _require_string(value, f"summary.{key}")

    profile = results["profile"]
    axis = profile["axis"]
    _require_string(axis["name"], "profile.axis.name")
    axis_values = _require_numeric_array(axis["values"], "profile.axis.values")

    profile_array_names = (
        "transmittance",
        "loss_db",
        "secure_key_rate_per_pulse",
        "effective_werner_p",
        "fidelity",
    )
    for name in profile_array_names:
        values = _require_numeric_array(profile[name], f"profile.{name}")
        _require_same_length(values, axis_values, f"profile.{name}", "profile.axis.values")

    if not axis_values:
        raise SchemaValidationError("profile.axis.values must be non-empty.")

    aggregates = profile["aggregates"]
    for key in ("min_loss_db", "min_loss_axis_value", "mean_fidelity"):
        _require_finite_number(aggregates[key], f"profile.aggregates.{key}")
    if "secure_key_yield_bits" in aggregates:
        _require_finite_number(
            aggregates["secure_key_yield_bits"],
            "profile.aggregates.secure_key_yield_bits",
        )
    if "max_secure_distance_km" in aggregates:
        _require_optional_finite_number(
            aggregates["max_secure_distance_km"],
            "profile.aggregates.max_secure_distance_km",
        )
    if "secure_distance_bracket" in aggregates:
        bracket = _require_mapping(
            aggregates["secure_distance_bracket"],
            "profile.aggregates.secure_distance_bracket",
        )
        for key in (
            "last_positive_length_km",
            "last_positive_secure_key_rate_per_pulse",
            "first_non_positive_length_km",
            "first_non_positive_secure_key_rate_per_pulse",
        ):
            _require_optional_finite_number(
                bracket[key],
                f"profile.aggregates.secure_distance_bracket.{key}",
            )

    if "geometry" in results:
        geometry = results["geometry"]
        for name in ("elevation_deg", "slant_range_km"):
            values = _require_numeric_array(geometry[name], f"geometry.{name}")
            _require_same_length(values, axis_values, f"geometry.{name}", "profile.axis.values")
        min_loss = _require_mapping(geometry["min_loss"], "geometry.min_loss")
        for key in ("elevation_deg", "slant_range_km"):
            _require_finite_number(min_loss[key], f"geometry.min_loss.{key}")

    mission = results["mission"]
    _require_finite_number(
        mission["pulse_repetition_rate_hz"],
        "mission.pulse_repetition_rate_hz",
    )
    _require_string(mission["sky_condition"], "mission.sky_condition")
    intensities = _require_mapping(mission["intensities"], "mission.intensities")
    for key in ("signal", "decoy", "vacuum"):
        _require_finite_number(intensities[key], f"mission.intensities.{key}")
    detector = _require_mapping(mission["detector"], "mission.detector")
    for key in (
        "detection_efficiency",
        "dark_count_prob",
        "error_correction_efficiency",
    ):
        _require_finite_number(detector[key], f"mission.detector.{key}")
    if "fibre" in mission:
        fibre = _require_mapping(mission["fibre"], "mission.fibre")
        for key in (
            "attenuation_db_km",
            "fixed_loss_db",
            "intrinsic_qber",
            "dark_count_prob",
            "werner_p",
        ):
            _require_finite_number(fibre[key], f"mission.fibre.{key}")

    provenance = _require_mapping(results["provenance"], "provenance")
    for key, value in provenance.items():
        _require_string(value, f"provenance.{key}")

    for key, value in results["run_metadata"].items():
        _require_string(value, f"run_metadata.{key}")


def _validate_ranges(results: Mapping[str, Any]) -> None:
    link = results["link"]
    _require_member(link["medium"], VALID_LINK_MEDIA, "link.medium")
    _require_member(link["topology"], VALID_LINK_TOPOLOGIES, "link.topology")
    _require_member(link["protocol"], VALID_LINK_PROTOCOLS, "link.protocol")

    teleportation = results["teleportation"]
    _require_minimum(teleportation["frames"], 1, "teleportation.frames")
    _require_range(
        teleportation["average_fidelity"],
        0.0,
        1.0,
        "teleportation.average_fidelity",
    )
    _require_range(
        teleportation["classical_limit"],
        0.0,
        1.0,
        "teleportation.classical_limit",
    )

    profile = results["profile"]
    axis_name = profile["axis"]["name"]
    _require_member(axis_name, VALID_PROFILE_AXES, "profile.axis.name")

    for index, value in enumerate(profile["transmittance"]):
        _require_range(value, 0.0, 1.0, f"profile.transmittance[{index}]")
    for index, value in enumerate(profile["loss_db"]):
        _require_minimum(value, 0.0, f"profile.loss_db[{index}]")
    for index, value in enumerate(profile["secure_key_rate_per_pulse"]):
        _require_range(
            value,
            0.0,
            1.0,
            f"profile.secure_key_rate_per_pulse[{index}]",
        )
    for index, value in enumerate(profile["effective_werner_p"]):
        _require_range(value, 0.0, 1.0, f"profile.effective_werner_p[{index}]")
    for index, value in enumerate(profile["fidelity"]):
        _require_range(value, 0.0, 1.0, f"profile.fidelity[{index}]")

    aggregates = profile["aggregates"]
    _require_minimum(aggregates["min_loss_db"], 0.0, "profile.aggregates.min_loss_db")
    _require_range(
        aggregates["mean_fidelity"],
        0.0,
        1.0,
        "profile.aggregates.mean_fidelity",
    )

    if axis_name == "time_s":
        if "secure_key_yield_bits" not in aggregates:
            raise SchemaValidationError(
                "profile.aggregates.secure_key_yield_bits is required for time_s axes."
            )
        _require_minimum(
            aggregates["secure_key_yield_bits"],
            0.0,
            "profile.aggregates.secure_key_yield_bits",
        )
        if "max_secure_distance_km" in aggregates:
            raise SchemaValidationError(
                "profile.aggregates.max_secure_distance_km is fibre-only."
            )
        if "secure_distance_bracket" in aggregates:
            raise SchemaValidationError(
                "profile.aggregates.secure_distance_bracket is fibre-only."
            )
    else:
        if "secure_key_yield_bits" in aggregates:
            raise SchemaValidationError(
                "profile.aggregates.secure_key_yield_bits is forbidden for length_km axes."
            )
        if "max_secure_distance_km" not in aggregates:
            raise SchemaValidationError(
                "profile.aggregates.max_secure_distance_km is required for length_km axes."
            )
        if "secure_distance_bracket" not in aggregates:
            raise SchemaValidationError(
                "profile.aggregates.secure_distance_bracket is required for length_km axes."
            )
        if aggregates["max_secure_distance_km"] is not None:
            _require_minimum(
                aggregates["max_secure_distance_km"],
                0.0,
                "profile.aggregates.max_secure_distance_km",
            )

    if "geometry" in results:
        for index, value in enumerate(results["geometry"]["elevation_deg"]):
            _require_range(value, 0.0, 90.0, f"geometry.elevation_deg[{index}]")
        for index, value in enumerate(results["geometry"]["slant_range_km"]):
            _require_strict_minimum(value, 0.0, f"geometry.slant_range_km[{index}]")

    mission = results["mission"]
    _require_strict_minimum(
        mission["pulse_repetition_rate_hz"],
        0.0,
        "mission.pulse_repetition_rate_hz",
    )
    intensities = mission["intensities"]
    for key in ("signal", "decoy", "vacuum"):
        _require_minimum(intensities[key], 0.0, f"mission.intensities.{key}")
    if not (intensities["signal"] > intensities["decoy"] >= intensities["vacuum"]):
        raise SchemaValidationError(
            "mission.intensities must satisfy signal > decoy >= vacuum."
        )
    detector = mission["detector"]
    _require_range(
        detector["detection_efficiency"],
        0.0,
        1.0,
        "mission.detector.detection_efficiency",
    )
    _require_range(
        detector["dark_count_prob"],
        0.0,
        1.0,
        "mission.detector.dark_count_prob",
    )
    _require_minimum(
        detector["error_correction_efficiency"],
        1.0,
        "mission.detector.error_correction_efficiency",
    )
    if "fibre" in mission:
        fibre = mission["fibre"]
        _require_minimum(
            fibre["attenuation_db_km"],
            0.0,
            "mission.fibre.attenuation_db_km",
        )
        _require_minimum(fibre["fixed_loss_db"], 0.0, "mission.fibre.fixed_loss_db")
        _require_range(
            fibre["intrinsic_qber"],
            0.0,
            0.5,
            "mission.fibre.intrinsic_qber",
        )
        _require_range(
            fibre["dark_count_prob"],
            0.0,
            1.0,
            "mission.fibre.dark_count_prob",
        )
        _require_range(fibre["werner_p"], 0.0, 1.0, "mission.fibre.werner_p")


def _validate_constants(results: Mapping[str, Any]) -> None:
    _assert_close(
        results["teleportation"]["classical_limit"],
        CLASSICAL_TELEPORTATION_LIMIT,
        "teleportation.classical_limit",
        atol=CONST_ATOL,
    )


def _validate_consistency(results: Mapping[str, Any]) -> None:
    profile = results["profile"]
    axis = profile["axis"]["values"]
    loss_db = profile["loss_db"]
    fidelity = profile["fidelity"]
    aggregates = profile["aggregates"]
    min_loss_index = min(range(len(loss_db)), key=loss_db.__getitem__)

    for index, (eta, observed_loss) in enumerate(zip(profile["transmittance"], loss_db)):
        if eta <= 0.0:
            raise SchemaValidationError(
                f"profile.transmittance[{index}] must be positive for finite loss_db."
            )
        expected_loss = -10.0 * math.log10(eta)
        _assert_close(observed_loss, expected_loss, f"profile.loss_db[{index}]")

    _assert_close(
        aggregates["min_loss_db"],
        min(loss_db),
        "profile.aggregates.min_loss_db",
    )
    _assert_close(
        aggregates["min_loss_axis_value"],
        axis[min_loss_index],
        "profile.aggregates.min_loss_axis_value",
    )
    expected_mean_fidelity = sum(fidelity) / len(fidelity)
    _assert_close(
        aggregates["mean_fidelity"],
        expected_mean_fidelity,
        "profile.aggregates.mean_fidelity",
    )

    # The emitted teleportation duplicate is rounded with round(..., 3), so the
    # guard uses half of the 3-decimal rounding unit rather than the L5 ATOL.
    if (
        abs(results["teleportation"]["average_fidelity"] - aggregates["mean_fidelity"])
        > ROUNDED_FIDELITY_ATOL
    ):
        raise SchemaValidationError(
            "teleportation.average_fidelity must match "
            "profile.aggregates.mean_fidelity within 5e-4."
        )

    axis_name = profile["axis"]["name"]
    if axis_name == "time_s":
        expected_yield = _integrated_temporal_yield_bits(
            axis,
            profile["secure_key_rate_per_pulse"],
            results["mission"]["pulse_repetition_rate_hz"],
        )
        _assert_close(
            aggregates["secure_key_yield_bits"],
            expected_yield,
            "profile.aggregates.secure_key_yield_bits",
        )
    else:
        _validate_fibre_secure_distance(results, min_loss_index)

    if "geometry" in results:
        geometry = results["geometry"]
        _assert_close(
            geometry["min_loss"]["elevation_deg"],
            geometry["elevation_deg"][min_loss_index],
            "geometry.min_loss.elevation_deg",
        )
        _assert_close(
            geometry["min_loss"]["slant_range_km"],
            geometry["slant_range_km"][min_loss_index],
            "geometry.min_loss.slant_range_km",
        )

    # This rule is valid for the current Werner-model v2 emission. Replacing the channel model requires either changing the model marker or revising this L5 rule.
    if results["run_metadata"]["physics_mode"] == "computed":
        for index, (p_eff, observed_fidelity) in enumerate(
            zip(profile["effective_werner_p"], fidelity)
        ):
            expected_fidelity = (1.0 + p_eff) / 2.0
            _assert_close(observed_fidelity, expected_fidelity, f"profile.fidelity[{index}]")

    if results["teleportation"]["frames"] != len(axis):
        raise SchemaValidationError(
            "teleportation.frames must equal len(profile.axis.values)."
        )


def _validate_fibre_secure_distance(
    results: Mapping[str, Any],
    min_loss_index: int,
) -> None:
    del min_loss_index
    profile = results["profile"]
    axis_values = profile["axis"]["values"]
    rates = profile["secure_key_rate_per_pulse"]
    aggregates = profile["aggregates"]
    bracket = aggregates["secure_distance_bracket"]

    positive_indices = [index for index, rate in enumerate(rates) if rate > 0.0]
    if positive_indices:
        last_positive_index = positive_indices[-1]
        first_non_positive_index = (
            last_positive_index + 1
            if last_positive_index + 1 < len(rates)
            else None
        )
    else:
        last_positive_index = None
        first_non_positive_index = 0

    expected_max_distance = (
        None if last_positive_index is None else axis_values[last_positive_index]
    )
    if aggregates["max_secure_distance_km"] != expected_max_distance:
        raise SchemaValidationError(
            "profile.aggregates.max_secure_distance_km must be the last "
            "axis value with positive secure_key_rate_per_pulse."
        )

    expected_last_positive_rate = (
        None if last_positive_index is None else rates[last_positive_index]
    )
    expected_first_non_positive_length = (
        None if first_non_positive_index is None else axis_values[first_non_positive_index]
    )
    expected_first_non_positive_rate = (
        None if first_non_positive_index is None else rates[first_non_positive_index]
    )
    expected_bracket = {
        "last_positive_length_km": expected_max_distance,
        "last_positive_secure_key_rate_per_pulse": expected_last_positive_rate,
        "first_non_positive_length_km": expected_first_non_positive_length,
        "first_non_positive_secure_key_rate_per_pulse": expected_first_non_positive_rate,
    }
    if bracket != expected_bracket:
        raise SchemaValidationError(
            "profile.aggregates.secure_distance_bracket must match the "
            "last-positive and immediately following non-positive samples."
        )

    definition = results["run_metadata"].get("max_secure_distance_definition")
    if not definition:
        raise SchemaValidationError(
            "run_metadata.max_secure_distance_definition is required for length_km axes."
        )


def _integrated_temporal_yield_bits(
    time_s: Sequence[float],
    secure_key_rate_per_pulse: Sequence[float],
    pulse_repetition_rate_hz: float,
) -> float:
    if len(time_s) < 2:
        return 0.0
    sample_width_s = (time_s[-1] - time_s[0]) / (len(time_s) - 1)
    return sum(rate * pulse_repetition_rate_hz * sample_width_s for rate in secure_key_rate_per_pulse)


def _require_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SchemaValidationError(f"{path} must be a mapping.")
    return value


def _require_string(value: Any, path: str) -> None:
    if not isinstance(value, str):
        raise SchemaValidationError(f"{path} must be a string.")


def _require_int(value: Any, path: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SchemaValidationError(f"{path} must be an integer.")


def _require_finite_number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise SchemaValidationError(f"{path} must be a finite number.")
    numeric_value = float(value)
    if math.isnan(numeric_value) or math.isinf(numeric_value):
        raise SchemaValidationError(f"{path} must be finite.")
    return numeric_value


def _require_optional_finite_number(value: Any, path: str) -> float | None:
    if value is None:
        return None
    return _require_finite_number(value, path)


def _require_numeric_array(value: Any, path: str) -> list[float]:
    if (
        isinstance(value, (str, bytes))
        or not isinstance(value, Sequence)
    ):
        raise SchemaValidationError(f"{path} must be an array of finite numbers.")
    return [
        _require_finite_number(item, f"{path}[{index}]")
        for index, item in enumerate(value)
    ]


def _require_same_length(
    values: Sequence[Any],
    expected: Sequence[Any],
    path: str,
    expected_path: str,
) -> None:
    if len(values) != len(expected):
        raise SchemaValidationError(
            f"{path} must have the same length as {expected_path}."
        )


def _require_member(value: str, allowed: frozenset[str], path: str) -> None:
    if value not in allowed:
        expected = ", ".join(sorted(allowed))
        raise SchemaValidationError(f"{path} must be one of: {expected}.")


def _require_range(value: float, low: float, high: float, path: str) -> None:
    if value < low or value > high:
        raise SchemaValidationError(f"{path} must be in [{low}, {high}].")


def _require_minimum(value: float, low: float, path: str) -> None:
    if value < low:
        raise SchemaValidationError(f"{path} must be >= {low}.")


def _require_strict_minimum(value: float, low: float, path: str) -> None:
    if value <= low:
        raise SchemaValidationError(f"{path} must be > {low}.")


def _assert_close(
    actual: float,
    expected: float,
    path: str,
    *,
    atol: float = ATOL,
) -> None:
    if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=atol):
        raise SchemaValidationError(
            f"{path} must be close to {expected}; got {actual}."
        )


def _join_path(prefix: str, key: str) -> str:
    if not prefix:
        return key
    return f"{prefix}.{key}"
