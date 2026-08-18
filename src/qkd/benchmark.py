"""LINK-6a: benchmark comparability + artifact contract (plan §6, S2/S3, Gate D).

Paired configurations must be named realizable or explicitly declared
counterfactual setups with *all* coupled parameters listed (S2); the harness
refuses single-parameter favorable sweeps that violate the declared §1.4
``(afterpulse_prob, dead_time_s)`` calibrated pair. Each artifact carries the
complete S3 contract, enforced closed-world by :func:`validate_benchmark_artifact`.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ARTIFACT_VERSION = 1
_METRIC_DIRECTIONS = frozenset({"higher_is_better", "lower_is_better"})
_CALIBRATED_PAIR_FIELDS = ("afterpulse_prob", "dead_time_s")


class BenchmarkError(ValueError):
    """Base class for LINK-6a benchmark contract violations."""


class CalibratedPairSweepError(BenchmarkError):
    """Raised when a sweep varies ``afterpulse_prob``/``dead_time_s`` independently
    of its calibrated-pair partner without a declared calibration law (plan §1.4, §6)."""


class BenchmarkArtifactValidationError(BenchmarkError):
    """Raised by :func:`validate_benchmark_artifact` for a malformed artifact (§6 S3)."""


@dataclass(frozen=True)
class BenchmarkConfiguration:
    """One named, fully-specified configuration point (plan §6 S2/S3).

    ``parameters`` must be the *full* coupled parameter block (S2 -- "a
    tighter gate window carries its jitter-acceptance/efficiency costs; a
    lower-afterpulse detector carries its calibrated pair"), not just the
    swept axis value. ``is_counterfactual`` names a setup that is not
    claimed realizable (S2, "explicitly declared counterfactual").
    """

    name: str
    parameters: Mapping[str, float | int | str | bool]
    axis_value: float
    metric_value: float
    provenance_link: str | None = None
    is_counterfactual: bool = False


@dataclass(frozen=True)
class CrossingBracket:
    """An interpolated advantage-crossing plus both retained bracketing samples
    (plan §12 advantage-crossing rule, §6 S3)."""

    lower_axis_value: float
    lower_metric_value: float
    upper_axis_value: float
    upper_metric_value: float
    crossing_axis_value: float
    crossing_label: str = "model-derived"


def linear_crossing(
    lower_axis_value: float,
    lower_metric_value: float,
    upper_axis_value: float,
    upper_metric_value: float,
    *,
    threshold: float = 0.0,
) -> CrossingBracket:
    """Linear interpolation between two bracketing samples (plan §12).

    The interpolated crossing is labeled ``"model-derived"``; both
    neighboring samples are retained on the returned :class:`CrossingBracket`
    (never collapsed to the crossing point alone).
    """

    if upper_axis_value == lower_axis_value:
        raise BenchmarkError("Bracketing axis values must differ.")
    if (lower_metric_value - threshold) * (upper_metric_value - threshold) > 0.0:
        raise BenchmarkError(
            "The bracketing samples do not straddle threshold; no crossing "
            "exists strictly between them."
        )
    if upper_metric_value == lower_metric_value:
        crossing_axis_value = lower_axis_value
    else:
        frac = (threshold - lower_metric_value) / (upper_metric_value - lower_metric_value)
        crossing_axis_value = lower_axis_value + frac * (upper_axis_value - lower_axis_value)
    return CrossingBracket(
        lower_axis_value=lower_axis_value,
        lower_metric_value=lower_metric_value,
        upper_axis_value=upper_axis_value,
        upper_metric_value=upper_metric_value,
        crossing_axis_value=crossing_axis_value,
    )


def validate_calibration_pair_sweep(
    configurations: Sequence[BenchmarkConfiguration],
    *,
    calibration_law: Callable[[float], float] | None = None,
) -> None:
    """Refuse a sweep that varies exactly one of ``(afterpulse_prob, dead_time_s)``
    (plan §1.4, §6 S2) unless ``calibration_law`` is supplied."""

    if calibration_law is not None:
        return
    distinct_values: dict[str, set] = {field: set() for field in _CALIBRATED_PAIR_FIELDS}
    for config in configurations:
        for field in _CALIBRATED_PAIR_FIELDS:
            if field in config.parameters:
                distinct_values[field].add(config.parameters[field])
    varying = {field for field, values in distinct_values.items() if len(values) > 1}
    if len(varying) == 1:
        (only,) = varying
        other = next(f for f in _CALIBRATED_PAIR_FIELDS if f != only)
        raise CalibratedPairSweepError(
            f"Sweep varies {only!r} independently of its calibrated-pair partner "
            f"{other!r} (plan §1.4); supply calibration_law= or vary both/neither."
        )


def build_benchmark_artifact(
    *,
    axis_name: str,
    axis_units: str,
    metric_name: str,
    metric_units: str,
    metric_direction: str,
    configurations: Sequence[BenchmarkConfiguration],
    assumptions: Sequence[str],
    crossing: CrossingBracket | None = None,
    equality_tolerance: float = 0.0,
    calibration_law: Callable[[float], float] | None = None,
) -> dict[str, Any]:
    """Assemble one ``outputs/benchmark_*.json``-shaped artifact (plan §6 S3)."""

    if metric_direction not in _METRIC_DIRECTIONS:
        raise BenchmarkArtifactValidationError(
            f"metric_direction must be one of {sorted(_METRIC_DIRECTIONS)}."
        )
    if not assumptions:
        raise BenchmarkArtifactValidationError("assumptions must be non-empty.")
    if not configurations:
        raise BenchmarkArtifactValidationError("configurations must be non-empty.")

    validate_calibration_pair_sweep(configurations, calibration_law=calibration_law)

    artifact: dict[str, Any] = {
        "artifact_version": ARTIFACT_VERSION,
        "axis": {"name": axis_name, "units": axis_units},
        "metric": {
            "name": metric_name,
            "units": metric_units,
            "direction": metric_direction,
        },
        "equality_tolerance": equality_tolerance,
        "configurations": [
            {
                "name": config.name,
                "parameters": dict(config.parameters),
                "axis_value": config.axis_value,
                "metric_value": config.metric_value,
                "provenance_link": config.provenance_link,
                "is_counterfactual": config.is_counterfactual,
            }
            for config in configurations
        ],
        "assumptions": list(assumptions),
    }
    if crossing is not None:
        artifact["crossing"] = {
            "lower": {
                "axis_value": crossing.lower_axis_value,
                "metric_value": crossing.lower_metric_value,
            },
            "upper": {
                "axis_value": crossing.upper_axis_value,
                "metric_value": crossing.upper_metric_value,
            },
            "crossing_axis_value": crossing.crossing_axis_value,
            "label": crossing.crossing_label,
        }

    validate_benchmark_artifact(artifact)
    return artifact


_ARTIFACT_REQUIRED_KEYS = frozenset(
    {
        "artifact_version",
        "axis",
        "metric",
        "equality_tolerance",
        "configurations",
        "assumptions",
    }
)
_ARTIFACT_ALLOWED_KEYS = _ARTIFACT_REQUIRED_KEYS | {"crossing"}
_AXIS_KEYS = frozenset({"name", "units"})
_METRIC_KEYS = frozenset({"name", "units", "direction"})
_CONFIG_KEYS = frozenset(
    {"name", "parameters", "axis_value", "metric_value", "provenance_link", "is_counterfactual"}
)
_CROSSING_KEYS = frozenset({"lower", "upper", "crossing_axis_value", "label"})
_CROSSING_POINT_KEYS = frozenset({"axis_value", "metric_value"})


def validate_benchmark_artifact(artifact: Mapping[str, Any]) -> None:
    """The dedicated light validator (plan §6 S3) -- missing units, ambiguous
    brackets, and incomplete assumptions are all named rejections."""

    if not isinstance(artifact, Mapping):
        raise BenchmarkArtifactValidationError("Artifact must be a mapping.")
    extra = set(artifact) - _ARTIFACT_ALLOWED_KEYS
    if extra:
        raise BenchmarkArtifactValidationError(f"Unknown artifact key(s): {sorted(extra)}.")
    missing = _ARTIFACT_REQUIRED_KEYS - set(artifact)
    if missing:
        raise BenchmarkArtifactValidationError(f"Artifact is missing key(s): {sorted(missing)}.")
    if artifact["artifact_version"] != ARTIFACT_VERSION:
        raise BenchmarkArtifactValidationError(
            f"artifact_version must equal {ARTIFACT_VERSION}."
        )

    axis = artifact["axis"]
    if not isinstance(axis, Mapping) or set(axis) != _AXIS_KEYS:
        raise BenchmarkArtifactValidationError("axis must have exactly the keys {name, units}.")
    if not axis["name"] or not axis["units"]:
        raise BenchmarkArtifactValidationError("axis.name and axis.units must be non-empty.")

    metric = artifact["metric"]
    if not isinstance(metric, Mapping) or set(metric) != _METRIC_KEYS:
        raise BenchmarkArtifactValidationError(
            "metric must have exactly the keys {name, units, direction}."
        )
    if not metric["name"] or not metric["units"]:
        raise BenchmarkArtifactValidationError("metric.name and metric.units must be non-empty.")
    if metric["direction"] not in _METRIC_DIRECTIONS:
        raise BenchmarkArtifactValidationError(
            f"metric.direction must be one of {sorted(_METRIC_DIRECTIONS)}."
        )

    configurations = artifact["configurations"]
    if not isinstance(configurations, list) or not configurations:
        raise BenchmarkArtifactValidationError("configurations must be a non-empty array.")
    for index, config in enumerate(configurations):
        path = f"configurations[{index}]"
        if not isinstance(config, Mapping) or set(config) != _CONFIG_KEYS:
            raise BenchmarkArtifactValidationError(
                f"{path} must have exactly the keys {sorted(_CONFIG_KEYS)}."
            )
        if not config["name"]:
            raise BenchmarkArtifactValidationError(f"{path}.name must be non-empty.")
        parameters = config["parameters"]
        if not isinstance(parameters, Mapping) or not parameters:
            raise BenchmarkArtifactValidationError(
                f"{path}.parameters must be a non-empty mapping (the full coupled "
                "parameter block, plan §6 S2 -- not just the swept axis value)."
            )

    assumptions = artifact["assumptions"]
    if (
        not isinstance(assumptions, list)
        or not assumptions
        or any(not isinstance(a, str) or not a for a in assumptions)
    ):
        raise BenchmarkArtifactValidationError(
            "assumptions must be a non-empty array of non-empty strings."
        )

    if "crossing" in artifact:
        crossing = artifact["crossing"]
        if not isinstance(crossing, Mapping) or set(crossing) != _CROSSING_KEYS:
            raise BenchmarkArtifactValidationError(
                f"crossing must have exactly the keys {sorted(_CROSSING_KEYS)}."
            )
        for side in ("lower", "upper"):
            point = crossing[side]
            if not isinstance(point, Mapping) or set(point) != _CROSSING_POINT_KEYS:
                raise BenchmarkArtifactValidationError(
                    f"crossing.{side} must have exactly the keys "
                    f"{sorted(_CROSSING_POINT_KEYS)} (both neighboring samples "
                    "retained, plan §6/§12)."
                )
        if crossing["label"] != "model-derived":
            raise BenchmarkArtifactValidationError(
                "crossing.label must be 'model-derived' (plan §12 advantage-"
                "crossing rule)."
            )


def write_benchmark_artifact(artifact: Mapping[str, Any], path: str | Path) -> Path:
    """Validate then write ``artifact`` as canonical-ish pretty JSON to ``path``.

    Callers (tests, in particular) must pass a ``tmp_path``-rooted path --
    this module performs no directory discovery of its own and never writes
    into the repository's ``outputs/`` directory on its own initiative.
    """

    validate_benchmark_artifact(artifact)
    target = Path(path)
    target.write_text(json.dumps(dict(artifact), indent=2, sort_keys=True), encoding="utf-8")
    return target
