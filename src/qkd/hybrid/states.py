"""HYBRID-1 Stage 1: boundary state model (ADR-0004 D2; companion v3.1).

Enums and frozen dataclasses for the hybrid QKD+PQC boundary's evidence and
decision objects -- the Stage 1 contract set (companion "Suggested Schema and
Dataclasses", packet Deliverable 1, C2 exhaustive list). **State model only**:
no policy engine (Stage 2), no KDF/cryptographic derivation (Stage 3), no
authentication integration (Stage 4), no physics coupling (Stage 5). No field
ever carries key bytes -- secret references are opaque ``str`` handles; the
future key-store module owns their lifecycle and zeroization.

``AttributionVerdict`` and ``DegradationAttributionEvidence`` are owned by the
tier-4 adaptive-coupling package (:mod:`qkd.adaptive.contracts`, D-H1-2) and
imported here read-only, re-exported for API convenience. This module imports
nothing else project-internal, and nothing under ``qkd.hybrid`` imports any
physics module.

**Clock basis.** Every ``*_utc`` field is UTC, formatted exactly
``YYYY-MM-DDTHH:MM:SS.ffffffZ`` (D-H1-3 C5: fixed six fractional digits, ``Z``
suffix, no offset or shorter/longer-fraction spelling accepted, on both
construction and load).

**Deep immutability (D-H1-3 C4).** Frozen dataclasses do not freeze nested
mappings, so no field here stores a ``dict``: every mapping-valued field is a
key-sorted ``tuple[tuple[str, str], ...]`` (``MissionPolicy.metadata``,
``AssuranceDecision.freshness_results``), converted and sorted at
construction from either a ``Mapping`` or an already-sorted tuple of pairs.

**Companion deviation (C3, Echo blocker 1).** ``AssuranceDecision`` gains a
``policy_profile: MissionPolicyProfile`` field not present in companion v3.1's
schema listing, so the decision is self-validating and audit-complete without
dereferencing the policy. Recorded in the Development Record; the companion
gains a v3.2 editorial reconciliation in this same commit (schema-listing
addition + revision-log entry, nothing else).
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from qkd.adaptive.contracts import AttributionVerdict, DegradationAttributionEvidence

__all__ = [
    "AttributionVerdict",
    "DegradationAttributionEvidence",
    "PhysicalLinkStatus",
    "PnsSuspicionLevel",
    "AuthenticationScope",
    "CryptoPostureStatus",
    "AuthenticationStatus",
    "KeyIssuanceMode",
    "AssuranceDisposition",
    "RequiredAction",
    "MissionPolicyProfile",
    "PhysicalLinkState",
    "KeyBufferState",
    "QkdKeyCandidate",
    "CryptoAssuranceState",
    "AlgorithmPosture",
    "PqcHandshakeEvidence",
    "AuthenticationEvidence",
    "MissionPolicy",
    "AssuranceDecision",
    "KeyProvenanceRecord",
    "AssumptionUpdateEvent",
    "HybridKeyMaterial",
]


# ---------------------------------------------------------------------------
# Construction-time validation helpers
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


def _require_optional_timestamp(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_timestamp(value, field_name)


def _require_nonempty_str(value: object, field_name: str) -> str:
    if not isinstance(value, str) or value == "":
        raise ValueError(f"{field_name} must be a non-empty string; got {value!r}.")
    return value


def _require_optional_nonempty_str(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_nonempty_str(value, field_name)


def _require_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a str; got {value!r}.")
    return value


def _require_hex64(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not _HEX64_RE.fullmatch(value):
        raise ValueError(
            f"{field_name} must be a lowercase 64-character hex SHA-256 digest; got {value!r}."
        )
    return value


def _require_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a bool; got {value!r}.")
    return value


def _require_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an int; got {value!r}.")
    return value


def _require_nonnegative_int(value: object, field_name: str) -> int:
    value = _require_int(value, field_name)
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0; got {value!r}.")
    return value


def _require_finite_float(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be a real number; got {value!r}.")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{field_name} must be finite; got {value!r}.")
    return numeric


def _require_nonnegative_float(value: object, field_name: str) -> float:
    numeric = _require_finite_float(value, field_name)
    if numeric < 0.0:
        raise ValueError(f"{field_name} must be >= 0; got {numeric!r}.")
    return numeric


def _require_unit_interval(value: object, field_name: str) -> float:
    numeric = _require_finite_float(value, field_name)
    if not (0.0 <= numeric <= 1.0):
        raise ValueError(f"{field_name} must be within [0, 1]; got {numeric!r}.")
    return numeric


def _require_enum(value: object, enum_cls: type[Enum], field_name: str):
    if not isinstance(value, enum_cls):
        raise TypeError(f"{field_name} must be a {enum_cls.__name__}; got {value!r}.")
    return value


def _require_tuple_of_nonempty_str(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple) or any(not isinstance(item, str) for item in value):
        raise TypeError(f"{field_name} must be a tuple[str, ...]; got {value!r}.")
    for item in value:
        if item == "":
            raise ValueError(f"{field_name} entries must be non-empty strings.")
    return value


def _require_tuple_of_enum(value: object, enum_cls: type[Enum], field_name: str) -> tuple:
    if not isinstance(value, tuple) or any(not isinstance(item, enum_cls) for item in value):
        raise TypeError(f"{field_name} must be a tuple[{enum_cls.__name__}, ...]; got {value!r}.")
    return value


def _freeze_str_map(value: object, field_name: str) -> tuple[tuple[str, str], ...]:
    """D-H1-3 C4: convert a Mapping[str, str] or an already-sorted tuple of
    (str, str) pairs into a key-sorted ``tuple[tuple[str, str], ...]``,
    rejecting any residual mutable container or wrong-typed entry."""

    if isinstance(value, Mapping):
        items = list(value.items())
    elif isinstance(value, tuple):
        items = list(value)
    else:
        raise TypeError(
            f"{field_name} must be a Mapping[str, str] or tuple[tuple[str, str], ...]; "
            f"got {type(value)!r}."
        )
    pairs: list[tuple[str, str]] = []
    for item in items:
        if not (isinstance(item, tuple) and len(item) == 2):
            raise TypeError(f"{field_name} entries must be (str, str) pairs; got {item!r}.")
        key, val = item
        if not isinstance(key, str) or not isinstance(val, str):
            raise TypeError(f"{field_name} entries must be (str, str) pairs; got {item!r}.")
        if key == "":
            raise ValueError(f"{field_name} keys must be non-empty strings.")
        pairs.append((key, val))
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise ValueError(f"{field_name} has duplicate keys.")
    pairs.sort(key=lambda kv: kv[0])
    return tuple(pairs)


# ---------------------------------------------------------------------------
# Enums (companion "Suggested Schema and Dataclasses"; values verbatim)
# ---------------------------------------------------------------------------


class PhysicalLinkStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    SUSPECT = "suspect"
    FAILED = "failed"
    UNKNOWN = "unknown"


class PnsSuspicionLevel(str, Enum):
    NONE = "none"
    ELEVATED = "elevated"
    HIGH = "high"
    UNKNOWN = "unknown"


class AuthenticationScope(str, Enum):
    QKD_CLASSICAL_CHANNEL = "qkd_classical_channel"
    SESSION_CONTROL = "session_control"


class CryptoPostureStatus(str, Enum):
    APPROVED = "approved"
    WATCHED = "watched"
    CONTESTED = "contested"
    DEPRECATED = "deprecated"
    DISALLOWED = "disallowed"
    UNKNOWN = "unknown"


class AuthenticationStatus(str, Enum):
    VALID = "valid"
    VALID_WITH_WARNING = "valid_with_warning"
    EXPIRED = "expired"
    INVALID = "invalid"
    UNKNOWN = "unknown"


class KeyIssuanceMode(str, Enum):
    HYBRID = "hybrid"
    QKD_ONLY = "qkd_only"
    PQC_ONLY = "pqc_only"
    NONE = "none"


class AssuranceDisposition(str, Enum):
    ASSURED = "assured"
    DEGRADED = "degraded"
    HELD = "held"
    BLOCKED = "blocked"
    RESEARCH_ONLY = "research_only"


class RequiredAction(str, Enum):
    REKEY = "rekey"
    ROTATE_ALGORITHM = "rotate_algorithm"
    QUARANTINE_LINK = "quarantine_link"
    REQUIRE_HUMAN_REVIEW = "require_human_review"


class MissionPolicyProfile(str, Enum):
    HYBRID_REQUIRED = "hybrid_required"
    QKD_PREFERRED = "qkd_preferred"
    PQC_FALLBACK_ALLOWED = "pqc_fallback_allowed"
    RESEARCH_MODE = "research_mode"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PhysicalLinkState:
    """Derived from the QKD pipeline only (companion "Physical link state")."""

    link_id: str
    epoch_id: str
    observed_at_utc: str
    qber: float
    sifted_key_rate_bps: float
    secure_key_rate_bps: float
    decoy_pns_suspicion: PnsSuspicionLevel
    finite_key_epsilon: float
    error_correction_leakage_bits: int
    privacy_amplification_id: str
    session_id: str
    peer_id: str
    status: PhysicalLinkStatus
    attribution_evidence_ref: str | None
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_nonempty_str(self.link_id, "link_id")
        _require_nonempty_str(self.epoch_id, "epoch_id")
        _require_timestamp(self.observed_at_utc, "observed_at_utc")
        object.__setattr__(self, "qber", _require_unit_interval(self.qber, "qber"))
        object.__setattr__(
            self,
            "sifted_key_rate_bps",
            _require_nonnegative_float(self.sifted_key_rate_bps, "sifted_key_rate_bps"),
        )
        object.__setattr__(
            self,
            "secure_key_rate_bps",
            _require_nonnegative_float(self.secure_key_rate_bps, "secure_key_rate_bps"),
        )
        _require_enum(self.decoy_pns_suspicion, PnsSuspicionLevel, "decoy_pns_suspicion")
        object.__setattr__(
            self,
            "finite_key_epsilon",
            _require_unit_interval(self.finite_key_epsilon, "finite_key_epsilon"),
        )
        object.__setattr__(
            self,
            "error_correction_leakage_bits",
            _require_nonnegative_int(self.error_correction_leakage_bits, "error_correction_leakage_bits"),
        )
        _require_nonempty_str(self.privacy_amplification_id, "privacy_amplification_id")
        _require_nonempty_str(self.session_id, "session_id")
        _require_nonempty_str(self.peer_id, "peer_id")
        _require_enum(self.status, PhysicalLinkStatus, "status")
        object.__setattr__(
            self,
            "attribution_evidence_ref",
            _require_optional_nonempty_str(self.attribution_evidence_ref, "attribution_evidence_ref"),
        )
        object.__setattr__(
            self, "evidence_refs", _require_tuple_of_nonempty_str(self.evidence_refs, "evidence_refs")
        )


@dataclass(frozen=True)
class KeyBufferState:
    """QKD key-buffer fill/consumption/depletion evidence."""

    link_id: str
    observed_at_utc: str
    buffer_fill_bits: int
    consumption_rate_bps: float
    projected_depletion_utc: str | None
    next_contact_window_utc: str | None
    depletion_rate_anomaly: bool
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_nonempty_str(self.link_id, "link_id")
        _require_timestamp(self.observed_at_utc, "observed_at_utc")
        object.__setattr__(
            self, "buffer_fill_bits", _require_nonnegative_int(self.buffer_fill_bits, "buffer_fill_bits")
        )
        object.__setattr__(
            self,
            "consumption_rate_bps",
            _require_nonnegative_float(self.consumption_rate_bps, "consumption_rate_bps"),
        )
        object.__setattr__(
            self,
            "projected_depletion_utc",
            _require_optional_timestamp(self.projected_depletion_utc, "projected_depletion_utc"),
        )
        object.__setattr__(
            self,
            "next_contact_window_utc",
            _require_optional_timestamp(self.next_contact_window_utc, "next_contact_window_utc"),
        )
        object.__setattr__(
            self, "depletion_rate_anomaly", _require_bool(self.depletion_rate_anomaly, "depletion_rate_anomaly")
        )
        object.__setattr__(
            self, "evidence_refs", _require_tuple_of_nonempty_str(self.evidence_refs, "evidence_refs")
        )


@dataclass(frozen=True)
class QkdKeyCandidate:
    """QKD-derived key material handle and provenance, provided by privacy amplification."""

    key_id: str
    link_id: str
    epoch_id: str
    session_id: str
    secret_ref: str
    secure_key_bits: int
    produced_at_utc: str
    physical_state_ref: str
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_nonempty_str(self.key_id, "key_id")
        _require_nonempty_str(self.link_id, "link_id")
        _require_nonempty_str(self.epoch_id, "epoch_id")
        _require_nonempty_str(self.session_id, "session_id")
        _require_nonempty_str(self.secret_ref, "secret_ref")
        object.__setattr__(
            self, "secure_key_bits", _require_nonnegative_int(self.secure_key_bits, "secure_key_bits")
        )
        _require_timestamp(self.produced_at_utc, "produced_at_utc")
        _require_nonempty_str(self.physical_state_ref, "physical_state_ref")
        object.__setattr__(
            self, "evidence_refs", _require_tuple_of_nonempty_str(self.evidence_refs, "evidence_refs")
        )


@dataclass(frozen=True)
class CryptoAssuranceState:
    """Derived from protocol, algorithm, implementation, and authentication evidence."""

    session_id: str
    peer_id: str
    observed_at_utc: str
    kem_posture_ref: str
    signature_posture_ref: str | None
    implementation_status: CryptoPostureStatus
    authentication_refs: tuple[str, ...]
    status: CryptoPostureStatus
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_nonempty_str(self.session_id, "session_id")
        _require_nonempty_str(self.peer_id, "peer_id")
        _require_timestamp(self.observed_at_utc, "observed_at_utc")
        _require_nonempty_str(self.kem_posture_ref, "kem_posture_ref")
        object.__setattr__(
            self,
            "signature_posture_ref",
            _require_optional_nonempty_str(self.signature_posture_ref, "signature_posture_ref"),
        )
        _require_enum(self.implementation_status, CryptoPostureStatus, "implementation_status")
        object.__setattr__(
            self,
            "authentication_refs",
            _require_tuple_of_nonempty_str(self.authentication_refs, "authentication_refs"),
        )
        _require_enum(self.status, CryptoPostureStatus, "status")
        object.__setattr__(
            self, "evidence_refs", _require_tuple_of_nonempty_str(self.evidence_refs, "evidence_refs")
        )


@dataclass(frozen=True)
class AlgorithmPosture:
    """One algorithm suite's posture record (assumption-agility registry entry)."""

    suite_id: str
    primitive: str
    parameter_set: str
    status: CryptoPostureStatus
    source_refs: tuple[str, ...]
    reviewed_at_utc: str
    effective_until_utc: str | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        _require_nonempty_str(self.suite_id, "suite_id")
        _require_nonempty_str(self.primitive, "primitive")
        _require_nonempty_str(self.parameter_set, "parameter_set")
        _require_enum(self.status, CryptoPostureStatus, "status")
        object.__setattr__(
            self, "source_refs", _require_tuple_of_nonempty_str(self.source_refs, "source_refs")
        )
        _require_timestamp(self.reviewed_at_utc, "reviewed_at_utc")
        object.__setattr__(
            self,
            "effective_until_utc",
            _require_optional_timestamp(self.effective_until_utc, "effective_until_utc"),
        )
        _require_str(self.notes, "notes")


@dataclass(frozen=True)
class PqcHandshakeEvidence:
    """Stage 1 representability only -- pure state; handshake production is Stage 4 (C2)."""

    session_id: str
    peer_id: str
    kem_suite_id: str
    signature_suite_id: str | None
    transcript_hash: str
    shared_secret_ref: str
    implementation_id: str
    implementation_status: CryptoPostureStatus
    algorithm_posture: AlgorithmPosture
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_nonempty_str(self.session_id, "session_id")
        _require_nonempty_str(self.peer_id, "peer_id")
        _require_nonempty_str(self.kem_suite_id, "kem_suite_id")
        object.__setattr__(
            self,
            "signature_suite_id",
            _require_optional_nonempty_str(self.signature_suite_id, "signature_suite_id"),
        )
        _require_hex64(self.transcript_hash, "transcript_hash")
        _require_nonempty_str(self.shared_secret_ref, "shared_secret_ref")
        _require_nonempty_str(self.implementation_id, "implementation_id")
        _require_enum(self.implementation_status, CryptoPostureStatus, "implementation_status")
        if not isinstance(self.algorithm_posture, AlgorithmPosture):
            raise TypeError(
                f"algorithm_posture must be an AlgorithmPosture; got {self.algorithm_posture!r}."
            )
        object.__setattr__(
            self, "evidence_refs", _require_tuple_of_nonempty_str(self.evidence_refs, "evidence_refs")
        )


@dataclass(frozen=True)
class AuthenticationEvidence:
    """One authenticated-channel record for one :class:`AuthenticationScope`."""

    session_id: str
    peer_id: str
    channel_id: str
    scope: AuthenticationScope
    mechanism: str
    status: AuthenticationStatus
    credential_ref: str | None
    transcript_hash: str
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_nonempty_str(self.session_id, "session_id")
        _require_nonempty_str(self.peer_id, "peer_id")
        _require_nonempty_str(self.channel_id, "channel_id")
        _require_enum(self.scope, AuthenticationScope, "scope")
        _require_nonempty_str(self.mechanism, "mechanism")
        _require_enum(self.status, AuthenticationStatus, "status")
        object.__setattr__(
            self, "credential_ref", _require_optional_nonempty_str(self.credential_ref, "credential_ref")
        )
        _require_hex64(self.transcript_hash, "transcript_hash")
        object.__setattr__(
            self, "evidence_refs", _require_tuple_of_nonempty_str(self.evidence_refs, "evidence_refs")
        )


@dataclass(frozen=True)
class MissionPolicy:
    """Valid-by-construction mission/session policy (companion schema rules).

    Stage 1 scope: the ``profile`` enum replaces free boolean combinations and
    every field is validated at construction. The substantive cross-object
    contradiction the packet names -- ``HYBRID_REQUIRED`` incompatible with
    single-source issuance -- is enforced where it is actually decided, on
    :class:`AssuranceDecision` (Stage 1 records carry the profile they were
    evaluated under; a validated factory consuming a full ``MissionPolicy`` is
    Stage 2's policy-engine responsibility).
    """

    policy_id: str
    policy_version: str
    profile: MissionPolicyProfile
    allow_watched_pqc: bool
    emergency_exception_ref: str | None = None
    require_human_review_for_contested: bool = True
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _require_nonempty_str(self.policy_id, "policy_id")
        _require_nonempty_str(self.policy_version, "policy_version")
        _require_enum(self.profile, MissionPolicyProfile, "profile")
        object.__setattr__(
            self, "allow_watched_pqc", _require_bool(self.allow_watched_pqc, "allow_watched_pqc")
        )
        object.__setattr__(
            self,
            "emergency_exception_ref",
            _require_optional_nonempty_str(self.emergency_exception_ref, "emergency_exception_ref"),
        )
        object.__setattr__(
            self,
            "require_human_review_for_contested",
            _require_bool(self.require_human_review_for_contested, "require_human_review_for_contested"),
        )
        object.__setattr__(self, "metadata", _freeze_str_map(self.metadata, "metadata"))


_SINGLE_SOURCE_ISSUANCE_MODES = frozenset({KeyIssuanceMode.QKD_ONLY, KeyIssuanceMode.PQC_ONLY})
_NO_ISSUANCE_DISPOSITIONS = frozenset({AssuranceDisposition.BLOCKED, AssuranceDisposition.HELD})


@dataclass(frozen=True)
class AssuranceDecision:
    """Orthogonal decision result (companion "Policy Result Model").

    Gains ``policy_profile`` over the companion v3.1 schema listing (C3, Echo
    blocker 1) -- see module docstring.
    """

    session_id: str
    decision_id: str
    policy_id: str
    policy_version: str
    policy_profile: MissionPolicyProfile
    physical_status: PhysicalLinkStatus
    crypto_status: CryptoPostureStatus
    authentication_status: AuthenticationStatus
    issuance_mode: KeyIssuanceMode
    disposition: AssuranceDisposition
    required_actions: tuple[RequiredAction, ...]
    selected_input_refs: tuple[str, ...]
    attribution_evidence_ref: str | None
    key_buffer_evidence_ref: str | None
    freshness_results: tuple[tuple[str, str], ...]
    reasons: tuple[str, ...]
    transcript_hash: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_nonempty_str(self.session_id, "session_id")
        _require_nonempty_str(self.decision_id, "decision_id")
        _require_nonempty_str(self.policy_id, "policy_id")
        _require_nonempty_str(self.policy_version, "policy_version")
        _require_enum(self.policy_profile, MissionPolicyProfile, "policy_profile")
        _require_enum(self.physical_status, PhysicalLinkStatus, "physical_status")
        _require_enum(self.crypto_status, CryptoPostureStatus, "crypto_status")
        _require_enum(self.authentication_status, AuthenticationStatus, "authentication_status")
        _require_enum(self.issuance_mode, KeyIssuanceMode, "issuance_mode")
        _require_enum(self.disposition, AssuranceDisposition, "disposition")
        object.__setattr__(
            self,
            "required_actions",
            _require_tuple_of_enum(self.required_actions, RequiredAction, "required_actions"),
        )
        object.__setattr__(
            self,
            "selected_input_refs",
            _require_tuple_of_nonempty_str(self.selected_input_refs, "selected_input_refs"),
        )
        object.__setattr__(
            self,
            "attribution_evidence_ref",
            _require_optional_nonempty_str(self.attribution_evidence_ref, "attribution_evidence_ref"),
        )
        object.__setattr__(
            self,
            "key_buffer_evidence_ref",
            _require_optional_nonempty_str(self.key_buffer_evidence_ref, "key_buffer_evidence_ref"),
        )
        object.__setattr__(
            self, "freshness_results", _freeze_str_map(self.freshness_results, "freshness_results")
        )
        object.__setattr__(self, "reasons", _require_tuple_of_nonempty_str(self.reasons, "reasons"))
        _require_hex64(self.transcript_hash, "transcript_hash")
        object.__setattr__(
            self, "evidence_refs", _require_tuple_of_nonempty_str(self.evidence_refs, "evidence_refs")
        )

        # Deliverable 1 structural invariants -- schema errors, not runtime fallbacks.
        if self.disposition in _NO_ISSUANCE_DISPOSITIONS and self.issuance_mode != KeyIssuanceMode.NONE:
            raise ValueError(
                f"disposition={self.disposition.value!r} requires issuance_mode=NONE; "
                f"got {self.issuance_mode.value!r}."
            )
        if self.disposition == AssuranceDisposition.RESEARCH_ONLY and self.issuance_mode != KeyIssuanceMode.NONE:
            raise ValueError(
                f"disposition=RESEARCH_ONLY requires issuance_mode=NONE; got {self.issuance_mode.value!r}."
            )
        if (
            self.policy_profile == MissionPolicyProfile.HYBRID_REQUIRED
            and self.issuance_mode in _SINGLE_SOURCE_ISSUANCE_MODES
        ):
            raise ValueError(
                "policy_profile=HYBRID_REQUIRED is incompatible with a single-source "
                f"issuance_mode; got {self.issuance_mode.value!r}."
            )
        if self.issuance_mode == KeyIssuanceMode.NONE and self.selected_input_refs:
            raise ValueError("issuance_mode=NONE requires selected_input_refs to be empty.")
        if self.issuance_mode != KeyIssuanceMode.NONE and not self.selected_input_refs:
            raise ValueError(
                f"issuance_mode={self.issuance_mode.value!r} requires a non-empty selected_input_refs."
            )


@dataclass(frozen=True)
class KeyProvenanceRecord:
    """Records source inputs, algorithms, policy version, and evidence digests."""

    key_id: str
    decision_ref: str
    selected_input_refs: tuple[str, ...]
    rejected_input_refs: tuple[str, ...]
    derivation_suite: str
    policy_version: str
    transcript_hash: str
    created_at_utc: str
    schema_version: str

    def __post_init__(self) -> None:
        _require_nonempty_str(self.key_id, "key_id")
        _require_nonempty_str(self.decision_ref, "decision_ref")
        object.__setattr__(
            self,
            "selected_input_refs",
            _require_tuple_of_nonempty_str(self.selected_input_refs, "selected_input_refs"),
        )
        if not self.selected_input_refs:
            raise ValueError("selected_input_refs must be non-empty (checklist: provenance for selected contributors).")
        object.__setattr__(
            self,
            "rejected_input_refs",
            _require_tuple_of_nonempty_str(self.rejected_input_refs, "rejected_input_refs"),
        )
        _require_nonempty_str(self.derivation_suite, "derivation_suite")
        _require_nonempty_str(self.policy_version, "policy_version")
        _require_hex64(self.transcript_hash, "transcript_hash")
        _require_timestamp(self.created_at_utc, "created_at_utc")
        _require_nonempty_str(self.schema_version, "schema_version")


@dataclass(frozen=True)
class AssumptionUpdateEvent:
    """Captures a change in PQC confidence, implementation status, or deprecation state."""

    event_id: str
    suite_id: str
    previous_status: CryptoPostureStatus
    new_status: CryptoPostureStatus
    source_refs: tuple[str, ...]
    reviewed_by: str
    effective_at_utc: str

    def __post_init__(self) -> None:
        _require_nonempty_str(self.event_id, "event_id")
        _require_nonempty_str(self.suite_id, "suite_id")
        _require_enum(self.previous_status, CryptoPostureStatus, "previous_status")
        _require_enum(self.new_status, CryptoPostureStatus, "new_status")
        object.__setattr__(
            self, "source_refs", _require_tuple_of_nonempty_str(self.source_refs, "source_refs")
        )
        _require_nonempty_str(self.reviewed_by, "reviewed_by")
        _require_timestamp(self.effective_at_utc, "effective_at_utc")


@dataclass(frozen=True)
class HybridKeyMaterial:
    """Labeled derived-key handle -- never raw QKD or raw PQC secrets."""

    key_id: str
    session_id: str
    purpose: str
    derivation_suite: str
    qkd_epoch_id: str | None
    pqc_suite_id: str | None
    policy_version: str
    key_ref: str
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_nonempty_str(self.key_id, "key_id")
        _require_nonempty_str(self.session_id, "session_id")
        _require_nonempty_str(self.purpose, "purpose")
        _require_nonempty_str(self.derivation_suite, "derivation_suite")
        object.__setattr__(
            self, "qkd_epoch_id", _require_optional_nonempty_str(self.qkd_epoch_id, "qkd_epoch_id")
        )
        object.__setattr__(
            self, "pqc_suite_id", _require_optional_nonempty_str(self.pqc_suite_id, "pqc_suite_id")
        )
        _require_nonempty_str(self.policy_version, "policy_version")
        _require_nonempty_str(self.key_ref, "key_ref")
        object.__setattr__(
            self,
            "provenance_refs",
            _require_tuple_of_nonempty_str(self.provenance_refs, "provenance_refs"),
        )
