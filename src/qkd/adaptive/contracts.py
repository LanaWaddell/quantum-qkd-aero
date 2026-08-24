"""Tier-4-owned attribution contracts (ADR-0004 D1; HYBRID-1 D-H1-2).

**Ownership.** This module is the adaptive-coupling tier's (tier 4's) contract
surface. ``AttributionVerdict`` and ``DegradationAttributionEvidence`` have
**one** definition, here. Tier 4 owns their semantics and production. Verbatim
from the HYBRID-1 execution packet (D-H1-2, Echo's wording, adopted verbatim):

    AttributionVerdict and DegradationAttributionEvidence have one definition
    in an import-light adaptive-coupling contract module. Tier 4 owns their
    semantics and production. Hybrid policy imports them read-only and may
    re-export them for API convenience. Neither contract module imports
    physics or policy implementations.

HYBRID-1 *creates* this module because it is the first consumer to land, but
creation is not ownership: the future tier-4 monitoring lane extends this
package rather than importing from ``qkd.hybrid``. This module has **stdlib
imports only** -- no project-internal import, ever, in either direction.

**Scope.** Stage 1 only: representability and structural validation
(construction-time invariants, canonical timestamp grammar, digest-shape
checks). No monitoring logic, no attribution computation, no policy. Those
are the tier-4 monitoring lane's own packet.

**Clock basis.** Every ``*_utc`` field is UTC, formatted exactly
``YYYY-MM-DDTHH:MM:SS.ffffffZ`` (fixed six fractional digits, ``Z`` suffix,
no alternative spelling accepted).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

__all__ = ["AttributionVerdict", "DegradationAttributionEvidence"]


# ---------------------------------------------------------------------------
# Construction-time validation helpers (stdlib only; not shared with
# qkd.hybrid -- this module imports nothing project-internal, so its
# validators are self-contained even though qkd.hybrid.states duplicates the
# same shapes).
# ---------------------------------------------------------------------------

_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


def _require_timestamp(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not _TIMESTAMP_RE.fullmatch(value):
        raise ValueError(
            f"{field_name} must match YYYY-MM-DDTHH:MM:SS.ffffffZ exactly "
            f"(six fractional digits, 'Z' suffix, no offset spelling); got {value!r}."
        )
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError as exc:
        raise ValueError(f"{field_name} is not a valid calendar timestamp: {value!r}.") from exc
    return value


def _require_nonempty_str(value: object, field_name: str) -> str:
    if not isinstance(value, str) or value == "":
        raise ValueError(f"{field_name} must be a non-empty string; got {value!r}.")
    return value


def _require_hex64(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not _HEX64_RE.fullmatch(value):
        raise ValueError(
            f"{field_name} must be a lowercase 64-character hex SHA-256 digest; got {value!r}."
        )
    return value


def _require_unit_interval(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a real number; got {value!r}.")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{field_name} must be finite; got {value!r}.")
    if not (0.0 <= numeric <= 1.0):
        raise ValueError(f"{field_name} must be within [0, 1]; got {numeric!r}.")
    return numeric


def _require_tuple_of_nonempty_str(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple) or any(not isinstance(item, str) for item in value):
        raise TypeError(f"{field_name} must be a tuple[str, ...]; got {value!r}.")
    for item in value:
        if item == "":
            raise ValueError(f"{field_name} entries must be non-empty strings.")
    return value


class AttributionVerdict(str, Enum):
    """Tier-4 monitoring's consistency-not-cause classification (ADR-0004 D1)."""

    ENVIRONMENT_CONSISTENT = "environment_consistent"
    UNEXPLAINED = "unexplained"
    ADVERSARIAL_SUSPECTED = "adversarial_suspected"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class DegradationAttributionEvidence:
    """Single-authority, immutable tier-4 attribution evidence object.

    Stage 1: pure state/representability. Referenced -- never embedded -- by
    ``PhysicalLinkState.attribution_evidence_ref``; tier 4 is the single
    attribution authority.
    """

    evidence_id: str
    link_id: str
    verdict: AttributionVerdict
    confidence: float
    window_start_utc: str
    window_end_utc: str
    produced_at_utc: str
    monitor_id: str
    monitor_version: str
    reference_id: str
    reference_digest: str
    source_integrity: str
    source_independence: str
    freshness: str
    reason_codes: tuple[str, ...]
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_nonempty_str(self.evidence_id, "evidence_id")
        _require_nonempty_str(self.link_id, "link_id")
        if not isinstance(self.verdict, AttributionVerdict):
            raise TypeError(f"verdict must be an AttributionVerdict; got {self.verdict!r}.")
        object.__setattr__(self, "confidence", _require_unit_interval(self.confidence, "confidence"))
        _require_timestamp(self.window_start_utc, "window_start_utc")
        _require_timestamp(self.window_end_utc, "window_end_utc")
        if self.window_end_utc < self.window_start_utc:
            raise ValueError("window_end_utc must not precede window_start_utc.")
        _require_timestamp(self.produced_at_utc, "produced_at_utc")
        _require_nonempty_str(self.monitor_id, "monitor_id")
        _require_nonempty_str(self.monitor_version, "monitor_version")
        _require_nonempty_str(self.reference_id, "reference_id")
        _require_hex64(self.reference_digest, "reference_digest")
        _require_nonempty_str(self.source_integrity, "source_integrity")
        _require_nonempty_str(self.source_independence, "source_independence")
        _require_nonempty_str(self.freshness, "freshness")
        object.__setattr__(
            self, "reason_codes", _require_tuple_of_nonempty_str(self.reason_codes, "reason_codes")
        )
        object.__setattr__(
            self, "evidence_refs", _require_tuple_of_nonempty_str(self.evidence_refs, "evidence_refs")
        )
