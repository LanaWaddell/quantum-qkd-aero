"""Tier-4 adaptive-coupling package (ADR-0004 D1).

Owns every feedback path in which channel-state observables drive protocol or
policy adaptation. HYBRID-1 creates :mod:`qkd.adaptive.contracts` as the first
consumer to land; see that module's docstring for the ownership rule.
"""

from __future__ import annotations

from .contracts import AttributionVerdict, DegradationAttributionEvidence
from .monitor import AttributionMonitor, MonitorContractError, TraceLengthContractError
from .observables import OBSERVABLES, ObservableContractError, ObservableSpec, observable_spec
from .references import CalibrationSpec, CommittedReference, DecisionRules, ScalarReferenceModel
from .traces import (
    ChannelStateTrace,
    TraceContractError,
    generate_law_shifted_trace,
    generate_matched_law_trace,
    generate_quasiperiodic_drift_trace,
    generate_reference_consistent_trace,
    generate_variance_inflated_trace,
)

__all__ = [
    "AttributionMonitor",
    "AttributionVerdict",
    "CalibrationSpec",
    "ChannelStateTrace",
    "CommittedReference",
    "DecisionRules",
    "DegradationAttributionEvidence",
    "MonitorContractError",
    "OBSERVABLES",
    "ObservableContractError",
    "ObservableSpec",
    "ScalarReferenceModel",
    "TraceContractError",
    "TraceLengthContractError",
    "generate_law_shifted_trace",
    "generate_matched_law_trace",
    "generate_quasiperiodic_drift_trace",
    "generate_reference_consistent_trace",
    "generate_variance_inflated_trace",
    "observable_spec",
]
