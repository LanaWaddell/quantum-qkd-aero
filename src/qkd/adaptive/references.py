"""Committed scalar references for the passive ADAPT-1 monitor."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime

from qkd.canonical import stable_hash, to_canonical_json
from qkd.twin import DiagnosticCalibration

from .observables import observable_spec

ADAPTIVE_SCHEMA_VERSION = "adaptive-1.0"
OPERATIONAL_MAPPING = "component_or_separately_calibrated"
REASON_CODE_VOCABULARY_VERSION = "adaptive-1.0"

_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")


class ReferenceContractError(ValueError):
    """Raised when a committed reference violates its frozen contract."""


def require_nonempty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ReferenceContractError(f"{field_name} must be a non-empty string.")
    return value


def parse_canonical_utc(value: object, field_name: str) -> datetime:
    if not isinstance(value, str) or not _TIMESTAMP_RE.fullmatch(value):
        raise ReferenceContractError(
            f"{field_name} must match YYYY-MM-DDTHH:MM:SS.ffffffZ exactly."
        )
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError as exc:
        raise ReferenceContractError(f"{field_name} is not a valid UTC timestamp.") from exc


def _finite(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReferenceContractError(f"{field_name} must be a real number.")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ReferenceContractError(f"{field_name} must be finite.")
    return numeric


@dataclass(frozen=True)
class ScalarReferenceModel:
    """Complete one-state/one-measurement linear-Gaussian model."""

    f: float
    h: float
    q: float
    r: float
    x0: float
    p0: float

    def __post_init__(self) -> None:
        for name in ("f", "h", "q", "r", "x0", "p0"):
            object.__setattr__(self, name, _finite(getattr(self, name), name))
        if self.q < 0.0:
            raise ReferenceContractError("q must be non-negative.")
        if self.r <= 0.0:
            raise ReferenceContractError("r must be strictly positive.")
        if self.p0 < 0.0:
            raise ReferenceContractError("p0 must be non-negative.")


@dataclass(frozen=True)
class CalibrationSpec:
    """The four lookup keys accepted by TWIN-1's closed calibration table."""

    alpha: float
    lags: int
    effective_n: int
    measurement_dim: int

    def __post_init__(self) -> None:
        alpha = _finite(self.alpha, "alpha")
        object.__setattr__(self, "alpha", alpha)
        for name in ("lags", "effective_n", "measurement_dim"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ReferenceContractError(f"{name} must be an integer.")
        try:
            DiagnosticCalibration(
                alpha=self.alpha,
                lags=self.lags,
                effective_n=self.effective_n,
                measurement_dim=self.measurement_dim,
            )
        except ValueError as exc:
            raise ReferenceContractError(f"unsupported calibration keys: {exc}") from exc

    def build(self) -> DiagnosticCalibration:
        """Reconstruct thresholds from TWIN-1; thresholds never enter the wire form."""

        return DiagnosticCalibration(
            alpha=self.alpha,
            lags=self.lags,
            effective_n=self.effective_n,
            measurement_dim=self.measurement_dim,
        )


@dataclass(frozen=True)
class DecisionRules:
    """Digest-bound operational rules for ADAPT-1 evidence production."""

    max_freshness_age_s: float
    operational_mapping: str = OPERATIONAL_MAPPING
    reason_code_vocabulary_version: str = REASON_CODE_VOCABULARY_VERSION

    def __post_init__(self) -> None:
        value = _finite(self.max_freshness_age_s, "max_freshness_age_s")
        if value < 0.0:
            raise ReferenceContractError("max_freshness_age_s must be non-negative.")
        object.__setattr__(self, "max_freshness_age_s", value)
        if self.operational_mapping != OPERATIONAL_MAPPING:
            raise ReferenceContractError(
                f"operational_mapping must be {OPERATIONAL_MAPPING!r}."
            )
        if self.reason_code_vocabulary_version != REASON_CODE_VOCABULARY_VERSION:
            raise ReferenceContractError(
                f"reason_code_vocabulary_version must be {REASON_CODE_VOCABULARY_VERSION!r}."
            )


@dataclass(frozen=True)
class CommittedReference:
    """Immutable, commit-before-observe reference with a computed digest."""

    reference_id: str
    committed_at_utc: str
    observable_name: str
    model: ScalarReferenceModel
    calibration: CalibrationSpec
    decision_rules: DecisionRules

    def __post_init__(self) -> None:
        require_nonempty_string(self.reference_id, "reference_id")
        parse_canonical_utc(self.committed_at_utc, "committed_at_utc")
        observable_spec(self.observable_name, require_monitorable=True)
        if not isinstance(self.model, ScalarReferenceModel):
            raise TypeError("model must be a ScalarReferenceModel.")
        if not isinstance(self.calibration, CalibrationSpec):
            raise TypeError("calibration must be a CalibrationSpec.")
        if not isinstance(self.decision_rules, DecisionRules):
            raise TypeError("decision_rules must be DecisionRules.")

    @property
    def digest(self) -> str:
        """Digest the canonical reference envelope; no digest is stored."""

        return stable_hash(to_canonical_json(self, schema_version=ADAPTIVE_SCHEMA_VERSION))


__all__ = [
    "ADAPTIVE_SCHEMA_VERSION",
    "CalibrationSpec",
    "CommittedReference",
    "DecisionRules",
    "OPERATIONAL_MAPPING",
    "REASON_CODE_VOCABULARY_VERSION",
    "ReferenceContractError",
    "ScalarReferenceModel",
]
