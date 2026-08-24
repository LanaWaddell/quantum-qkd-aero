"""HYBRID-1 Stage 1: hybrid QKD+PQC boundary state model (ADR-0004 D2).

State model only: enums, frozen dataclasses, validation, canonical
serialization/digests, and the algorithm-posture registry snapshot interface.
No policy engine (Stage 2), no KDF/cryptographic derivation (Stage 3), no
authentication integration (Stage 4), no physics coupling (Stage 5). This
package imports :mod:`qkd.adaptive.contracts` read-only (re-exporting
``AttributionVerdict`` and ``DegradationAttributionEvidence``) and nothing
else project-internal; nothing here imports any physics module.
"""

from __future__ import annotations

from qkd.hybrid.registry import AlgorithmPostureRegistry, RegistryError, RegistrySnapshot
from qkd.hybrid.serialization import (
    SCHEMA_VERSION,
    SerializationError,
    from_canonical_json,
    stable_hash,
    to_canonical_json,
)
from qkd.hybrid.states import (
    AlgorithmPosture,
    AssumptionUpdateEvent,
    AssuranceDecision,
    AssuranceDisposition,
    AttributionVerdict,
    AuthenticationEvidence,
    AuthenticationScope,
    AuthenticationStatus,
    CryptoAssuranceState,
    CryptoPostureStatus,
    DegradationAttributionEvidence,
    HybridKeyMaterial,
    KeyBufferState,
    KeyIssuanceMode,
    KeyProvenanceRecord,
    MissionPolicy,
    MissionPolicyProfile,
    PhysicalLinkState,
    PhysicalLinkStatus,
    PnsSuspicionLevel,
    PqcHandshakeEvidence,
    QkdKeyCandidate,
    RequiredAction,
)

__all__ = [
    "AlgorithmPosture",
    "AlgorithmPostureRegistry",
    "AssumptionUpdateEvent",
    "AssuranceDecision",
    "AssuranceDisposition",
    "AttributionVerdict",
    "AuthenticationEvidence",
    "AuthenticationScope",
    "AuthenticationStatus",
    "CryptoAssuranceState",
    "CryptoPostureStatus",
    "DegradationAttributionEvidence",
    "HybridKeyMaterial",
    "KeyBufferState",
    "KeyIssuanceMode",
    "KeyProvenanceRecord",
    "MissionPolicy",
    "MissionPolicyProfile",
    "PhysicalLinkState",
    "PhysicalLinkStatus",
    "PnsSuspicionLevel",
    "PqcHandshakeEvidence",
    "QkdKeyCandidate",
    "RegistryError",
    "RegistrySnapshot",
    "RequiredAction",
    "SCHEMA_VERSION",
    "SerializationError",
    "from_canonical_json",
    "stable_hash",
    "to_canonical_json",
]
