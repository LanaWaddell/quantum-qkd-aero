"""Closed observable registry for the passive ADAPT-1 monitor."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Mapping

LatencyClass = Literal["per_sample", "per_block", "per_pass"]
MonitorApplicability = Literal["monitorable", "policy_context_only"]


class ObservableContractError(ValueError):
    """Raised when an observable is absent or not monitorable."""


@dataclass(frozen=True)
class ObservableSpec:
    """Registry metadata for one adversarially shapeable observable."""

    name: str
    unit: str
    description: str
    latency_class: LatencyClass
    trust: str
    source_module: str
    monitor_applicability: MonitorApplicability

    def __post_init__(self) -> None:
        for field_name in ("name", "unit", "description", "source_module"):
            if not isinstance(getattr(self, field_name), str) or not getattr(self, field_name):
                raise ValueError(f"{field_name} must be a non-empty string.")
        if self.latency_class not in {"per_sample", "per_block", "per_pass"}:
            raise ValueError(f"unsupported latency_class {self.latency_class!r}.")
        if self.trust != "adversarially_shapeable":
            raise ValueError("ADAPT-1 observable trust must be 'adversarially_shapeable'.")
        if self.monitor_applicability not in {"monitorable", "policy_context_only"}:
            raise ValueError(
                f"unsupported monitor_applicability {self.monitor_applicability!r}."
            )


_SPECS = (
    ObservableSpec(
        "qber",
        "fraction",
        "Observed quantum bit error rate.",
        "per_block",
        "adversarially_shapeable",
        "qkd.bb84",
        "monitorable",
    ),
    ObservableSpec(
        "sifted_key_rate_bps",
        "bit/s",
        "Sifted key production rate.",
        "per_block",
        "adversarially_shapeable",
        "qkd.receiver",
        "monitorable",
    ),
    ObservableSpec(
        "secure_key_rate_bps",
        "bit/s",
        "Asymptotic secure key production rate.",
        "per_block",
        "adversarially_shapeable",
        "qkd.bb84",
        "monitorable",
    ),
    ObservableSpec(
        "decoy_anomaly_score",
        "fraction",
        "Relative single-photon-yield anomaly indicator.",
        "per_block",
        "adversarially_shapeable",
        "qkd.eve",
        "monitorable",
    ),
    ObservableSpec(
        "availability",
        "fraction",
        "Receiver dead-time availability.",
        "per_block",
        "adversarially_shapeable",
        "qkd.receiver",
        "monitorable",
    ),
    ObservableSpec(
        "buffer_fill_bits",
        "bit",
        "Hybrid-policy key-buffer occupancy context.",
        "per_pass",
        "adversarially_shapeable",
        "qkd.hybrid.states",
        "policy_context_only",
    ),
)

OBSERVABLES: Mapping[str, ObservableSpec] = MappingProxyType({spec.name: spec for spec in _SPECS})


def observable_spec(name: str, *, require_monitorable: bool = False) -> ObservableSpec:
    """Return the closed-world spec for ``name`` or raise a contract error."""

    try:
        spec = OBSERVABLES[name]
    except (KeyError, TypeError) as exc:
        raise ObservableContractError(f"unknown adaptive observable {name!r}.") from exc
    if require_monitorable and spec.monitor_applicability != "monitorable":
        raise ObservableContractError(
            f"observable {name!r} is policy_context_only and cannot be monitored."
        )
    return spec


__all__ = [
    "OBSERVABLES",
    "ObservableContractError",
    "ObservableSpec",
    "observable_spec",
]
