"""HYBRID-1 Deliverable 5: ``qkd.hybrid.states`` and ``qkd.adaptive.contracts``.

Covers ``docs/HYBRID_1_PLAN.md`` Deliverable 5's state/validation bullets:
exhaustive invalid-``MissionPolicy``/``AssuranceDecision`` construction
rejection, degraded-without-issuance unrepresentability, both authentication
scopes, the ``AssuranceDecision`` profile cross-check and ``RESEARCH_ONLY``
rules, the enum-vocabulary freeze, and the import-graph boundary (D-H1-1/2).
Serialization/digest/fixture tests live in ``test_hybrid_serialization.py``;
registry tests live in ``test_hybrid_registry.py``.
"""

from __future__ import annotations

import ast
import dataclasses
import typing
from pathlib import Path

import pytest

from qkd.adaptive.contracts import AttributionVerdict, DegradationAttributionEvidence
from qkd.hybrid.states import (
    AlgorithmPosture,
    AssumptionUpdateEvent,
    AssuranceDecision,
    AssuranceDisposition,
    AuthenticationEvidence,
    AuthenticationScope,
    AuthenticationStatus,
    CryptoAssuranceState,
    CryptoPostureStatus,
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

T = "2026-08-24T12:00:00.000000Z"
HEX64 = "a" * 64

_REPO_SRC = Path(__file__).resolve().parents[1] / "src"


def _valid_decision_kwargs(**overrides: object) -> dict[str, object]:
    kwargs: dict[str, object] = dict(
        session_id="sess-001",
        decision_id="decision-001",
        policy_id="policy-001",
        policy_version="1.0.0",
        policy_profile=MissionPolicyProfile.QKD_PREFERRED,
        physical_status=PhysicalLinkStatus.HEALTHY,
        crypto_status=CryptoPostureStatus.APPROVED,
        authentication_status=AuthenticationStatus.VALID,
        issuance_mode=KeyIssuanceMode.HYBRID,
        disposition=AssuranceDisposition.ASSURED,
        required_actions=(),
        selected_input_refs=("qkey-001",),
        attribution_evidence_ref=None,
        key_buffer_evidence_ref=None,
        freshness_results=(),
        reasons=("nominal",),
        transcript_hash=HEX64,
        evidence_refs=(),
    )
    kwargs.update(overrides)
    return kwargs


def _valid_policy_kwargs(**overrides: object) -> dict[str, object]:
    kwargs: dict[str, object] = dict(
        policy_id="policy-001",
        policy_version="1.0.0",
        profile=MissionPolicyProfile.QKD_PREFERRED,
        allow_watched_pqc=False,
    )
    kwargs.update(overrides)
    return kwargs


# ---------------------------------------------------------------------------
# Enum vocabulary freeze (serialized values match companion verbatim)
# ---------------------------------------------------------------------------

_EXPECTED_ENUM_VALUES = {
    PhysicalLinkStatus: {"healthy", "degraded", "suspect", "failed", "unknown"},
    PnsSuspicionLevel: {"none", "elevated", "high", "unknown"},
    AttributionVerdict: {
        "environment_consistent",
        "unexplained",
        "adversarial_suspected",
        "insufficient_evidence",
        "not_applicable",
    },
    AuthenticationScope: {"qkd_classical_channel", "session_control"},
    CryptoPostureStatus: {"approved", "watched", "contested", "deprecated", "disallowed", "unknown"},
    AuthenticationStatus: {"valid", "valid_with_warning", "expired", "invalid", "unknown"},
    KeyIssuanceMode: {"hybrid", "qkd_only", "pqc_only", "none"},
    AssuranceDisposition: {"assured", "degraded", "held", "blocked", "research_only"},
    RequiredAction: {"rekey", "rotate_algorithm", "quarantine_link", "require_human_review"},
    MissionPolicyProfile: {"hybrid_required", "qkd_preferred", "pqc_fallback_allowed", "research_mode"},
}


@pytest.mark.parametrize("enum_cls,expected", list(_EXPECTED_ENUM_VALUES.items()))
def test_enum_vocabulary_freeze(enum_cls, expected):
    assert {member.value for member in enum_cls} == expected


# ---------------------------------------------------------------------------
# MissionPolicy -- exhaustive invalid-construction rejection
# ---------------------------------------------------------------------------


def test_mission_policy_valid_construction():
    policy = MissionPolicy(**_valid_policy_kwargs(metadata={"mission": "demo"}))
    assert policy.metadata == (("mission", "demo"),)


@pytest.mark.parametrize(
    "overrides,error",
    [
        ({"policy_id": ""}, ValueError),
        ({"policy_version": ""}, ValueError),
        ({"profile": "hybrid_required"}, TypeError),  # raw str, not the enum
        ({"allow_watched_pqc": "yes"}, TypeError),
        ({"require_human_review_for_contested": 1}, TypeError),
        ({"emergency_exception_ref": ""}, ValueError),
        ({"metadata": ["not", "a", "mapping"]}, TypeError),
        ({"metadata": {"": "empty-key"}}, ValueError),
        ({"metadata": {"k": 1}}, TypeError),
    ],
)
def test_mission_policy_invalid_construction_rejected(overrides, error):
    with pytest.raises(error):
        MissionPolicy(**_valid_policy_kwargs(**overrides))


# ---------------------------------------------------------------------------
# AssuranceDecision -- exhaustive invalid-construction rejection
# ---------------------------------------------------------------------------


def test_assurance_decision_valid_construction():
    decision = AssuranceDecision(**_valid_decision_kwargs())
    assert decision.issuance_mode is KeyIssuanceMode.HYBRID


@pytest.mark.parametrize(
    "overrides",
    [
        # disposition in {BLOCKED, HELD} => issuance_mode == NONE
        {"disposition": AssuranceDisposition.BLOCKED, "issuance_mode": KeyIssuanceMode.HYBRID},
        {"disposition": AssuranceDisposition.HELD, "issuance_mode": KeyIssuanceMode.QKD_ONLY},
        # disposition == RESEARCH_ONLY => issuance_mode == NONE
        {"disposition": AssuranceDisposition.RESEARCH_ONLY, "issuance_mode": KeyIssuanceMode.PQC_ONLY},
        # policy_profile == HYBRID_REQUIRED => issuance_mode in {HYBRID, NONE}
        {
            "policy_profile": MissionPolicyProfile.HYBRID_REQUIRED,
            "issuance_mode": KeyIssuanceMode.QKD_ONLY,
        },
        {
            "policy_profile": MissionPolicyProfile.HYBRID_REQUIRED,
            "issuance_mode": KeyIssuanceMode.PQC_ONLY,
        },
        # issuance_mode != NONE <=> selected_input_refs non-empty
        {"issuance_mode": KeyIssuanceMode.NONE, "selected_input_refs": ("qkey-001",)},
        {"issuance_mode": KeyIssuanceMode.HYBRID, "selected_input_refs": ()},
    ],
)
def test_assurance_decision_structural_invariant_rejected(overrides):
    with pytest.raises(ValueError):
        AssuranceDecision(**_valid_decision_kwargs(**overrides))


@pytest.mark.parametrize(
    "overrides,error",
    [
        ({"session_id": ""}, ValueError),
        ({"decision_id": ""}, ValueError),
        ({"policy_id": ""}, ValueError),
        ({"policy_version": ""}, ValueError),
        ({"policy_profile": "hybrid_required"}, TypeError),
        ({"physical_status": "healthy"}, TypeError),
        ({"crypto_status": "approved"}, TypeError),
        ({"authentication_status": "valid"}, TypeError),
        ({"issuance_mode": "hybrid"}, TypeError),
        ({"disposition": "assured"}, TypeError),
        ({"required_actions": [RequiredAction.REKEY]}, TypeError),  # list, not tuple
        ({"required_actions": ("rekey",)}, TypeError),  # raw str, not enum
        ({"selected_input_refs": ["qkey-001"]}, TypeError),
        ({"attribution_evidence_ref": ""}, ValueError),
        ({"key_buffer_evidence_ref": ""}, ValueError),
        ({"freshness_results": [("physical", "fresh")]}, TypeError),
        ({"freshness_results": {"physical": 1}}, TypeError),
        ({"reasons": ("",)}, ValueError),
        ({"transcript_hash": "not-hex"}, ValueError),
        ({"transcript_hash": "a" * 63}, ValueError),
        ({"transcript_hash": "A" * 64}, ValueError),  # uppercase rejected
        ({"evidence_refs": ["ev-1"]}, TypeError),
    ],
)
def test_assurance_decision_field_validation_rejected(overrides, error):
    with pytest.raises(error):
        AssuranceDecision(**_valid_decision_kwargs(**overrides))


def test_assurance_decision_degraded_without_issuance_mode_unrepresentable():
    """``disposition=degraded`` without an explicit ``issuance_mode`` is
    structurally unrepresentable: ``issuance_mode`` has no default, so the
    dataclass constructor itself refuses the call (TypeError), before any
    ``__post_init__`` invariant even runs."""

    kwargs = _valid_decision_kwargs(disposition=AssuranceDisposition.DEGRADED)
    del kwargs["issuance_mode"]
    with pytest.raises(TypeError):
        AssuranceDecision(**kwargs)


def test_assurance_decision_degraded_with_explicit_issuance_mode_representable():
    decision = AssuranceDecision(
        **_valid_decision_kwargs(
            disposition=AssuranceDisposition.DEGRADED,
            issuance_mode=KeyIssuanceMode.PQC_ONLY,
            selected_input_refs=("pqc-secret-001",),
        )
    )
    assert decision.disposition is AssuranceDisposition.DEGRADED
    assert decision.issuance_mode is KeyIssuanceMode.PQC_ONLY


def test_assurance_decision_degraded_held_with_none_issuance_representable():
    decision = AssuranceDecision(
        **_valid_decision_kwargs(
            disposition=AssuranceDisposition.HELD,
            issuance_mode=KeyIssuanceMode.NONE,
            selected_input_refs=(),
        )
    )
    assert decision.disposition is AssuranceDisposition.HELD
    assert decision.issuance_mode is KeyIssuanceMode.NONE


# ---------------------------------------------------------------------------
# AssuranceDecision.policy_profile cross-check and RESEARCH_ONLY tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("issuance_mode", [KeyIssuanceMode.HYBRID, KeyIssuanceMode.NONE])
def test_hybrid_required_profile_permits_hybrid_or_none(issuance_mode):
    selected = ("qkey-001",) if issuance_mode != KeyIssuanceMode.NONE else ()
    disposition = AssuranceDisposition.ASSURED if issuance_mode != KeyIssuanceMode.NONE else AssuranceDisposition.HELD
    decision = AssuranceDecision(
        **_valid_decision_kwargs(
            policy_profile=MissionPolicyProfile.HYBRID_REQUIRED,
            issuance_mode=issuance_mode,
            selected_input_refs=selected,
            disposition=disposition,
        )
    )
    assert decision.policy_profile is MissionPolicyProfile.HYBRID_REQUIRED


@pytest.mark.parametrize("issuance_mode", [KeyIssuanceMode.QKD_ONLY, KeyIssuanceMode.PQC_ONLY])
def test_hybrid_required_profile_rejects_single_source_issuance(issuance_mode):
    with pytest.raises(ValueError):
        AssuranceDecision(
            **_valid_decision_kwargs(
                policy_profile=MissionPolicyProfile.HYBRID_REQUIRED,
                issuance_mode=issuance_mode,
                selected_input_refs=("some-ref",),
            )
        )


def test_research_only_disposition_permits_none_issuance():
    decision = AssuranceDecision(
        **_valid_decision_kwargs(
            disposition=AssuranceDisposition.RESEARCH_ONLY,
            issuance_mode=KeyIssuanceMode.NONE,
            selected_input_refs=(),
        )
    )
    assert decision.disposition is AssuranceDisposition.RESEARCH_ONLY
    assert decision.issuance_mode is KeyIssuanceMode.NONE


@pytest.mark.parametrize(
    "issuance_mode", [KeyIssuanceMode.HYBRID, KeyIssuanceMode.QKD_ONLY, KeyIssuanceMode.PQC_ONLY]
)
def test_research_only_disposition_rejects_any_issuance(issuance_mode):
    with pytest.raises(ValueError):
        AssuranceDecision(
            **_valid_decision_kwargs(
                disposition=AssuranceDisposition.RESEARCH_ONLY,
                issuance_mode=issuance_mode,
                selected_input_refs=("some-ref",),
            )
        )


# ---------------------------------------------------------------------------
# Both authentication scopes representable and distinguishable
# ---------------------------------------------------------------------------


def _auth_evidence(scope: AuthenticationScope) -> AuthenticationEvidence:
    return AuthenticationEvidence(
        session_id="sess-001",
        peer_id="peer-001",
        channel_id="chan-001",
        scope=scope,
        mechanism="ml-dsa-65-signed",
        status=AuthenticationStatus.VALID,
        credential_ref="cred-001",
        transcript_hash=HEX64,
        evidence_refs=(),
    )


def test_both_authentication_scopes_representable_and_distinguishable():
    classical = _auth_evidence(AuthenticationScope.QKD_CLASSICAL_CHANNEL)
    session = _auth_evidence(AuthenticationScope.SESSION_CONTROL)
    assert classical.scope is AuthenticationScope.QKD_CLASSICAL_CHANNEL
    assert session.scope is AuthenticationScope.SESSION_CONTROL
    assert classical.scope != session.scope
    assert classical != session


def test_authentication_evidence_rejects_unknown_scope_type():
    with pytest.raises(TypeError):
        AuthenticationEvidence(
            session_id="sess-001",
            peer_id="peer-001",
            channel_id="chan-001",
            scope="qkd_classical_channel",  # raw str, not the enum
            mechanism="ml-dsa-65-signed",
            status=AuthenticationStatus.VALID,
            credential_ref=None,
            transcript_hash=HEX64,
        )


# ---------------------------------------------------------------------------
# Deep immutability: per-field-type tuple/mapping conversion and rejection
# ---------------------------------------------------------------------------


def test_mission_policy_metadata_accepts_dict_and_freezes_sorted():
    policy = MissionPolicy(**_valid_policy_kwargs(metadata={"z": "1", "a": "2"}))
    assert isinstance(policy.metadata, tuple)
    assert policy.metadata == (("a", "2"), ("z", "1"))
    with pytest.raises(dataclasses.FrozenInstanceError):
        policy.metadata = ()  # type: ignore[misc]


def test_mission_policy_metadata_accepts_presorted_tuple():
    policy = MissionPolicy(**_valid_policy_kwargs(metadata=(("a", "2"), ("z", "1"))))
    assert policy.metadata == (("a", "2"), ("z", "1"))


def test_mission_policy_metadata_rejects_duplicate_keys():
    with pytest.raises(ValueError):
        MissionPolicy(**_valid_policy_kwargs(metadata=(("a", "1"), ("a", "2"))))


def test_evidence_refs_tuple_field_rejects_list():
    with pytest.raises(TypeError):
        PhysicalLinkState(
            link_id="link-1",
            epoch_id="epoch-1",
            observed_at_utc=T,
            qber=0.01,
            sifted_key_rate_bps=1.0,
            secure_key_rate_bps=1.0,
            decoy_pns_suspicion=PnsSuspicionLevel.NONE,
            finite_key_epsilon=1e-9,
            error_correction_leakage_bits=1,
            privacy_amplification_id="pa-1",
            session_id="sess-1",
            peer_id="peer-1",
            status=PhysicalLinkStatus.HEALTHY,
            attribution_evidence_ref=None,
            evidence_refs=["not", "a", "tuple"],  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Timestamp grammar (construction path; load-path coverage lives in
# test_hybrid_serialization.py)
# ---------------------------------------------------------------------------

_BAD_TIMESTAMPS = [
    "2026-08-24T12:00:00.000000+00:00",  # offset spelling
    "2026-08-24T12:00:00.0Z",  # one fractional digit
    "2026-08-24T12:00:00.000Z",  # three fractional digits
    "2026-08-24T12:00:00Z",  # no fraction
    "2026-08-24t12:00:00.000000Z",  # lowercase 't'
    "2026-08-24T12:00:00.000000z",  # lowercase 'z'
    "2026-13-01T00:00:00.000000Z",  # invalid month
]


@pytest.mark.parametrize("bad_ts", _BAD_TIMESTAMPS)
def test_timestamp_grammar_rejected_at_construction(bad_ts):
    with pytest.raises(ValueError):
        AssumptionUpdateEvent(
            event_id="ev-1",
            suite_id="ML-KEM-768",
            previous_status=CryptoPostureStatus.WATCHED,
            new_status=CryptoPostureStatus.APPROVED,
            source_refs=(),
            reviewed_by="board",
            effective_at_utc=bad_ts,
        )


def test_timestamp_grammar_accepts_exact_form():
    event = AssumptionUpdateEvent(
        event_id="ev-1",
        suite_id="ML-KEM-768",
        previous_status=CryptoPostureStatus.WATCHED,
        new_status=CryptoPostureStatus.APPROVED,
        source_refs=(),
        reviewed_by="board",
        effective_at_utc="2026-08-24T12:00:00.000000Z",
    )
    assert event.effective_at_utc == "2026-08-24T12:00:00.000000Z"


# ---------------------------------------------------------------------------
# Representative-object smoke construction for every remaining contract type
# (guards against a field being silently dropped from the C2 exhaustive set)
# ---------------------------------------------------------------------------


def test_key_buffer_state_construction():
    KeyBufferState(
        link_id="link-1",
        observed_at_utc=T,
        buffer_fill_bits=1024,
        consumption_rate_bps=10.0,
        projected_depletion_utc=None,
        next_contact_window_utc=None,
        depletion_rate_anomaly=False,
    )


def test_qkd_key_candidate_construction():
    QkdKeyCandidate(
        key_id="k-1",
        link_id="link-1",
        epoch_id="epoch-1",
        session_id="sess-1",
        secret_ref="secret-1",
        secure_key_bits=1024,
        produced_at_utc=T,
        physical_state_ref="pls-1",
    )


def test_crypto_assurance_state_construction():
    CryptoAssuranceState(
        session_id="sess-1",
        peer_id="peer-1",
        observed_at_utc=T,
        kem_posture_ref="posture-1",
        signature_posture_ref=None,
        implementation_status=CryptoPostureStatus.APPROVED,
        authentication_refs=(),
        status=CryptoPostureStatus.APPROVED,
    )


def test_pqc_handshake_evidence_construction():
    posture = AlgorithmPosture(
        suite_id="ML-KEM-768",
        primitive="kem",
        parameter_set="768",
        status=CryptoPostureStatus.APPROVED,
        source_refs=(),
        reviewed_at_utc=T,
    )
    PqcHandshakeEvidence(
        session_id="sess-1",
        peer_id="peer-1",
        kem_suite_id="ML-KEM-768",
        signature_suite_id=None,
        transcript_hash=HEX64,
        shared_secret_ref="secret-1",
        implementation_id="impl-1",
        implementation_status=CryptoPostureStatus.APPROVED,
        algorithm_posture=posture,
    )


def test_pqc_handshake_evidence_rejects_wrong_posture_type():
    with pytest.raises(TypeError):
        PqcHandshakeEvidence(
            session_id="sess-1",
            peer_id="peer-1",
            kem_suite_id="ML-KEM-768",
            signature_suite_id=None,
            transcript_hash=HEX64,
            shared_secret_ref="secret-1",
            implementation_id="impl-1",
            implementation_status=CryptoPostureStatus.APPROVED,
            algorithm_posture="not-a-posture",  # type: ignore[arg-type]
        )


def test_key_provenance_record_requires_nonempty_selected_input_refs():
    with pytest.raises(ValueError):
        KeyProvenanceRecord(
            key_id="k-1",
            decision_ref="d-1",
            selected_input_refs=(),
            rejected_input_refs=(),
            derivation_suite="suite-1",
            policy_version="1.0",
            transcript_hash=HEX64,
            created_at_utc=T,
            schema_version="hybrid-1.0",
        )


def test_key_provenance_record_allows_empty_rejected_input_refs():
    record = KeyProvenanceRecord(
        key_id="k-1",
        decision_ref="d-1",
        selected_input_refs=("in-1",),
        rejected_input_refs=(),
        derivation_suite="suite-1",
        policy_version="1.0",
        transcript_hash=HEX64,
        created_at_utc=T,
        schema_version="hybrid-1.0",
    )
    assert record.rejected_input_refs == ()


def test_hybrid_key_material_construction():
    HybridKeyMaterial(
        key_id="k-1",
        session_id="sess-1",
        purpose="traffic",
        derivation_suite="hkdf-1",
        qkd_epoch_id="epoch-1",
        pqc_suite_id="ML-KEM-768",
        policy_version="1.0",
        key_ref="key-handle-1",
        provenance_refs=(),
    )


def test_degradation_attribution_evidence_window_ordering_enforced():
    with pytest.raises(ValueError):
        DegradationAttributionEvidence(
            evidence_id="e-1",
            link_id="link-1",
            verdict=AttributionVerdict.ENVIRONMENT_CONSISTENT,
            confidence=0.5,
            window_start_utc="2026-08-24T12:05:00.000000Z",
            window_end_utc="2026-08-24T12:00:00.000000Z",  # before start
            produced_at_utc=T,
            monitor_id="mon-1",
            monitor_version="v1",
            reference_id="ref-1",
            reference_digest=HEX64,
            source_integrity="signed",
            source_independence="independent",
            freshness="fresh",
            reason_codes=(),
        )


def test_degradation_attribution_evidence_confidence_out_of_range_rejected():
    with pytest.raises(ValueError):
        DegradationAttributionEvidence(
            evidence_id="e-1",
            link_id="link-1",
            verdict=AttributionVerdict.INSUFFICIENT_EVIDENCE,
            confidence=1.5,
            window_start_utc=T,
            window_end_utc=T,
            produced_at_utc=T,
            monitor_id="mon-1",
            monitor_version="v1",
            reference_id="ref-1",
            reference_digest=HEX64,
            source_integrity="signed",
            source_independence="independent",
            freshness="fresh",
            reason_codes=(),
        )


# ---------------------------------------------------------------------------
# No-bytes-fields type-level test (checklist: secret-handle lifecycle -- no
# field ever carries raw key bytes)
# ---------------------------------------------------------------------------

_ALL_CONTRACT_TYPES = (
    PhysicalLinkState,
    KeyBufferState,
    QkdKeyCandidate,
    CryptoAssuranceState,
    AlgorithmPosture,
    PqcHandshakeEvidence,
    AuthenticationEvidence,
    MissionPolicy,
    AssuranceDecision,
    KeyProvenanceRecord,
    AssumptionUpdateEvent,
    HybridKeyMaterial,
    DegradationAttributionEvidence,
)


def _hints_mention_bytes(tp: object) -> bool:
    if tp is bytes or tp is bytearray:
        return True
    args = typing.get_args(tp)
    return any(_hints_mention_bytes(arg) for arg in args)


@pytest.mark.parametrize("cls", _ALL_CONTRACT_TYPES)
def test_no_field_is_typed_bytes(cls):
    hints = typing.get_type_hints(cls)
    for f in dataclasses.fields(cls):
        assert not _hints_mention_bytes(hints[f.name]), (
            f"{cls.__name__}.{f.name} must never be typed bytes -- Stage 1 carries no raw key material."
        )


# ---------------------------------------------------------------------------
# Import-graph tests (D-H1-1/2)
# ---------------------------------------------------------------------------


def _imported_module_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                # Relative import within the package -- not a project-internal
                # import of a *different* top-level module; record it distinctly.
                modules.add("." * node.level + (node.module or ""))
            elif node.module:
                modules.add(node.module)
    return modules


def _py_files(root: Path) -> list[Path]:
    return sorted(root.rglob("*.py"))


def test_adaptive_contracts_imports_nothing_project_internal():
    # ADAPT-1 plan Sec6: this invariant belongs specifically to the frozen contract module.
    path = _REPO_SRC / "qkd" / "adaptive" / "contracts.py"
    modules = _imported_module_names(path)
    qkd_imports = {m for m in modules if m == "qkd" or m.startswith("qkd.") or m.startswith(".")}
    assert not qkd_imports, f"{path} imports project-internal module(s): {qkd_imports}"


_PHYSICS_MODULE_PREFIXES = (
    "qkd.link",
    "qkd.mission",
    "qkd.channel",
    "qkd.bb84",
    "qkd.detection",
    "qkd.effects",
    "qkd.eve",
    "qkd.decoy",
    "qkd.coherence",
    "qkd.teleportation",
    "qkd.fibre",
    "qkd.orbit",
    "qkd.chsh",
    "qkd.replay",
    "qkd.schema",
    "qkd.provenance",
    "qkd.signals",
    "qkd.twin",
    "qkd.benchmark",
    "qkd.run",
)


def test_hybrid_imports_only_adaptive_contracts_and_itself():
    for path in _py_files(_REPO_SRC / "qkd" / "hybrid"):
        modules = _imported_module_names(path)
        for module in modules:
            if not (module == "qkd" or module.startswith("qkd.") or module.startswith(".")):
                continue  # stdlib / third-party import, unrestricted
            # ADAPT-1 plan Sec6 permits only the schema-neutral canonical extraction.
            allowed = module == "qkd.adaptive.contracts" or module == "qkd.canonical" or module.startswith("qkd.hybrid") or module.startswith(".")
            assert allowed, f"{path} has a disallowed project-internal import: {module!r}"
            for physics_prefix in _PHYSICS_MODULE_PREFIXES:
                assert not module.startswith(physics_prefix), (
                    f"{path} imports physics module {module!r} via prefix {physics_prefix!r}"
                )


def test_no_module_outside_hybrid_imports_hybrid():
    hybrid_dir = (_REPO_SRC / "qkd" / "hybrid").resolve()
    for path in _py_files(_REPO_SRC):
        if hybrid_dir in path.resolve().parents or path.resolve().parent == hybrid_dir:
            continue
        modules = _imported_module_names(path)
        offending = {m for m in modules if m == "qkd.hybrid" or m.startswith("qkd.hybrid.")}
        assert not offending, f"{path} imports qkd.hybrid, which only the hybrid package (and the future tier-4 monitor) may do: {offending}"
