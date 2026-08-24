# Execution Packet: HYBRID-1 rev 6 (Stage 1 — Boundary State Model Only)

- Date: 2026-08-24
- Prepared by: Claude (Chat Claude rev 2, revised by Cowork Claude review pass 2026-08-24), against fresh-clone HEAD `d48cb2c` (Rev 14 + certification correction; 622/601 passing — reverified 2026-08-24 on a fresh clone: 601 passed + 1 skipped without qiskit; docs-only commits since `e3815c0`). Rev 3 supersedes rev 2, applying three narrow review corrections (changelog below); rev 2 superseded rev 1 (`409ae6047d13ed9ac803bfadfcb587c17b8b7d1eb4db8ab2ff6c92fe04fab072`), applying Echo's dispatch review in full: D-H1-2 rejected as written and replaced (ownership inversion), two validation blockers resolved, D-H1-3 specification completed. Namespace check reverified 2026-08-24 against fresh-clone HEAD: `src/qkd/` contains no `adaptive`, `contracts`, or `hybrid` entries; no collision.
- **Rev 5 → rev 6 changelog (Echo confirmation, 2026-08-24; D-H1-1/2/3 all confirmed; PI dispatch authorization given):** (C11, mechanical) `docs/HYBRID_1_PLAN.md` added to the verification-step allowlist and explicit staging paths — C10 made the allowlist the binding staging list, and rev 5's list would have left the execution plan itself untracked, unlike the committed `HYBRID_0_PLAN.md`; `docs/LINK_7_PLAN.md` remains excluded. Implementer note: dispatched to the Sonnet subagent per the PI's instruction (this packet's earlier "Codex drafts" phrasing reads as "the implementer drafts").
- **Rev 4 → rev 5 changelog (Echo re-review, 2026-08-24; C4–C7 confirmed, D-H1-1/2 remain confirmed):** (C8) the `RegistrySnapshot` self-referential digest removed — a digest stored inside the snapshot cannot be computed over the full envelope that contains it; the digest is now a **computed property over the serialized snapshot envelope** (`RegistrySnapshot.digest()` → SHA-256 of the canonical envelope bytes of the digest-free record), never a stored field, matching the packet's hash-actual-emitted-bytes rule; (C9) the stale Development-Record line saying the companion v3.2 reconciliation is "registered for the companion's next touch" corrected to match C7 — v3.2 ships in HYBRID-1's records commit; (C10) staging hygiene: `docs/LINK_7_PLAN.md` (untracked LINK-lane draft) and any other untracked non-HYBRID file are **excluded from HYBRID-1 staging** — the verification-step file allowlist is the staging list, `git add` by explicit path only, never `git add -A`/`.`.
- **Rev 3 → rev 4 changelog (Echo confirmation review, 2026-08-24; D-H1-1/2 and C2/C3 confirmed):** (C4) deep-immutability conversion typed **per field** — string mappings become `tuple[tuple[str, str], ...]`; `RegistrySnapshot.postures` becomes `tuple[tuple[str, AlgorithmPosture], ...]` (suite-id-sorted; each posture serialized as its own canonical payload object) — the rev 3 blanket `str,str` rule did not fit the postures field; (C5) canonical timestamp **grammar pinned exactly**: `YYYY-MM-DDTHH:MM:SS.ffffffZ` — fixed six fractional digits always present (constructors format explicitly; `datetime.isoformat` output with omitted or shorter fractions is rejected), so one instant has exactly one byte form — Z-only alone admitted `.0Z` vs `.000000Z` variance; (C6) canonical encoding gains `ensure_ascii=True` (matching the repository's `replay.py` serialization contract) and the loader **rejects any input that differs byte-for-byte from its canonical reserialization**, as `replay.py` already does; (C7, adopted Echo recommendation) the companion v3.2 `policy_profile` reconciliation ships **in HYBRID-1's records commit** rather than deferring known implementation/schema drift — one schema-listing addition plus a revision-log entry in `docs/architecture/pqc_hybrid_architecture.md`, nothing else.
- **Rev 2 → rev 3 changelog (review corrections, no architectural change):** (C1) the Deliverable-1 timestamp-validation bullet contradicted D-H1-3's canonical form (it accepted `Z` **or** `+00:00` while D-H1-3 rejects every non-`Z` spelling) — resolved in favour of D-H1-3: **`Z`-only everywhere**, one instant one byte form; (C2) `PqcHandshakeEvidence` membership made explicit — it **is** in the Stage 1 contract set (the companion's Stage 1 checklist gates "all boundary objects", and it is a listed boundary object; Stage 1 implements it as pure state/representability only, its Stage 4 handshake semantics untouched) — the rev 2 phrasing ("exactly the contract set" + a list omitting it + an auxiliary-types catch-all) left the implementer to decide; (C3) the `AssuranceDecision.policy_profile` field (Echo blocker 1) is a deliberate **deviation from the companion v3.1 schema** and is now instructed to be recorded as such in the Development Record, with a companion v3.2 editorial reconciliation — *rev 4's C7 pulls that reconciliation into HYBRID-1's own records commit; the rev 3 "next touch" deferral is superseded (C9)* — the schema section must not silently drift from the implemented contract.
- Governing documents: ADR-0004 r3 (Accepted, `d7c9c33` — status line verified Accepted/ratified-by-Lana on the live file); companion `docs/architecture/pqc_hybrid_architecture.md` (informative, as-committed SHA-256 `d6c4a01b4c4d4c0d8aeecd9652725c3769cd9b6de488409efb7bfa5ce9fee898` — verified byte-exact 2026-08-24), specifically its "Stage 1: State model only" roadmap entry and "Stage 1 contract checklist"
- Lane status: HYBRID lane, Stage 1. **The LINK architectural lane remains active** (LINK-7 drafting in parallel). No sequencing conflict: HYBRID-1 touches no physics module and no existing schema path.

## Scope

Implement the ADR-0004 boundary **state model only**: enums, frozen dataclasses, validation, serialization, digests, and the algorithm-posture registry snapshot interface, with tests. Explicitly excluded (later stages): the policy engine (Stage 2), any KDF or cryptographic derivation (Stage 3), authentication integration (Stage 4), simulation coupling (Stage 5), operational registry workflow (Stage 6). Nothing in this stage produces, consumes, or represents actual key material — secret references are opaque handles only.

## Blocking decisions for PI before dispatch

- **D-H1-1 (package location, as modified by Echo review).** Two namespaces, ownership-aligned: `src/qkd/adaptive/contracts.py` — an import-light adaptive-coupling contract module holding exactly `AttributionVerdict` and `DegradationAttributionEvidence` — and `src/qkd/hybrid/` (modules `states.py`, `registry.py`, `serialization.py`, `__init__.py`) for everything hybrid-specific. Neither namespace is imported by any physics module, and the reverse imports are prohibited: `adaptive/contracts.py` imports nothing project-internal (stdlib only); `hybrid/` may import `adaptive.contracts` read-only and nothing else project-internal. Confirm or redirect.
- **D-H1-2 (contract ownership, rev 1 proposal rejected and replaced per Echo review).** Rev 1 made the hybrid package the definition point for the attribution contracts with tier 4 importing from its own consumer — an ownership inversion against ADR-0004 D1, which makes tier 4 the emitter and single authority for attribution evidence. Replaced with Echo's wording, adopted verbatim: `AttributionVerdict` and `DegradationAttributionEvidence` have one definition in an import-light adaptive-coupling contract module. Tier 4 owns their semantics and production. Hybrid policy imports them read-only and may re-export them for API convenience. Neither contract module imports physics or policy implementations. HYBRID-1 *creates* `src/qkd/adaptive/contracts.py` because it is the first consumer to land, but the module docstring declares tier-4 ownership, and the future tier-4 monitoring lane extends that package rather than importing from `hybrid`. Creation is not ownership. This still freezes the interface that gates the tier-4 packet — the freeze just lives in the owner's namespace now.
- **D-H1-3 (serialization + digest, direction accepted, specification completed per Echo review).** JSON serialization, digests over the system's real emitted bytes, never over hand-reconstructed payloads. Canonical form pinned exactly:
  - **Envelope:** every serialized record is `{"record_type": <str>, "schema_version": "hybrid-1.0", "payload": {...}}`; `record_type` is the dataclass name; digest is computed over the full envelope bytes.
  - **Canonical encoding:** UTF-8, `ensure_ascii=True` (C6 — matching `replay.py`), sorted keys at every level, no whitespace variance (`separators=(",", ":")`), NaN/Inf rejected at construction and by the encoder. **Loader round-trip guard (C6):** `from_canonical_json` re-serializes the parsed object under these rules and rejects any input whose bytes differ — non-canonical spellings never load.
  - **Canonical floats:** shortest round-trip decimal representation (CPython `repr(float)` semantics); no alternative spellings.
  - **Canonical timestamps (C5, exact grammar):** `YYYY-MM-DDTHH:MM:SS.ffffffZ` — fixed six fractional digits, always present, `Z` suffix required. Everything else is rejected, not normalized: offset spellings (`+00:00`), missing or shorter/longer fractional fields (`.0Z`, `.000Z`, no fraction), lowercase `z`. Constructors format explicitly (never bare `datetime.isoformat`, which drops zero microseconds). One instant, one byte form.
  - **Deep immutability (C4, typed per field):** frozen dataclasses do not freeze nested mappings, so no field stores a `dict`; every mapping-valued field is converted at construction to a key-sorted tuple of pairs with the **field's declared value type** — string mappings (e.g. `MissionPolicy.metadata`, `AssuranceDecision.freshness_results`) to `tuple[tuple[str, str], ...]`; `RegistrySnapshot.postures` to `tuple[tuple[str, AlgorithmPosture], ...]`, suite-id-sorted, each posture serialized as its own canonical payload object. All serialize back to JSON objects. Constructors reject any residual mutable container and any value not of the field's declared type.
  - **Hash algorithm:** SHA-256 over the canonical envelope bytes, hex-lowercase.
  - **Test discipline:** serialization and digest tests assert against **exact byte fixtures** checked into `tests/fixtures/`; `pytest.approx` is confined to numerical-behavior tests and never touches canonical bytes or digests. Confirm.

## Deliverables

### 0. `src/qkd/adaptive/contracts.py` — tier-4-owned attribution contracts (import-light)

Exactly `AttributionVerdict` and `DegradationAttributionEvidence`, stdlib imports only, module docstring declaring tier-4 ownership and the D-H1-2 rule verbatim. Everything else about their fields and validation follows the companion and the D-H1-3 canonical rules.

### 1. `src/qkd/hybrid/states.py` — enums and frozen dataclasses (attribution types imported read-only from `adaptive.contracts`, re-exported for API convenience)

Exactly the contract set from companion v3.1, implemented as `@dataclass(frozen=True)` with `__post_init__` validation:

- Enums defined here: `PhysicalLinkStatus`, `PnsSuspicionLevel`, `AuthenticationScope`, `CryptoPostureStatus`, `AuthenticationStatus`, `KeyIssuanceMode`, `AssuranceDisposition`, `RequiredAction`, `MissionPolicyProfile`. (`AttributionVerdict` lives in `adaptive.contracts`, imported read-only.)
- Dataclasses defined here — **the complete companion schema-section set, explicitly enumerated (C2):** `PhysicalLinkState`, `KeyBufferState`, `QkdKeyCandidate`, `CryptoAssuranceState`, `AlgorithmPosture`, `PqcHandshakeEvidence` (Stage 1 representability only — pure state; its handshake production semantics are Stage 4), `AuthenticationEvidence`, `MissionPolicy`, `AssuranceDecision`, `KeyProvenanceRecord`, `AssumptionUpdateEvent`, `HybridKeyMaterial` (handle-only). This list is exhaustive; there is no auxiliary-types catch-all — a companion type not on this list is a stop-and-surface condition, not an implementer judgment call.
- Field names, types, and enum values must match the companion **exactly**; where the companion's illustrative code is underspecified (e.g., exact `Mapping` types) or where this packet records a deliberate deviation (the D-H1-3 mapping→sorted-tuple conversion; the C3 `policy_profile` field), resolve as specified here and record the resolution in the Development Record. Any *other* conflict between companion text and implementability is stop-and-surface, not silent adjustment.

Validation encoded in construction (schema errors, not runtime fallbacks):

- `disposition` in `{BLOCKED, HELD}` ⇒ `issuance_mode == NONE`.
- **(Echo blocker 1; recorded companion deviation, C3)** `AssuranceDecision` gains a `policy_profile: MissionPolicyProfile` field so the record is self-validating and audit-complete without dereferencing the policy: `__post_init__` enforces `policy_profile == HYBRID_REQUIRED` ⇒ `issuance_mode ∈ {HYBRID, NONE}`. A validated factory consuming a full `MissionPolicy` is Stage 2's policy-engine responsibility; Stage 1 records carry the profile they were evaluated under. (Chosen over factory-only because decisions are audit records — the enforcement basis must travel with the record.) The Development Record entry for HYBRID-1 must name this field as a deviation from the companion v3.1 schema section, and the **companion v3.2 editorial reconciliation** (adding the field to the schema listing, plus a revision-log entry) **ships in HYBRID-1's records commit** (C7/C9 — no deferral).
- **(Echo blocker 2)** `disposition == RESEARCH_ONLY` ⇒ `issuance_mode == NONE`, enforced at construction — the conservative rule. No `KeyUsageScope` concept is introduced in Stage 1; if research-scoped issuance is ever actually needed, adding a usage-scope axis is a recorded Stage 2 decision, not a Stage 1 invention. Fail-closed until then.
- Timestamp grammar per C5 enforced in every `*_utc` validator (supersedes the rev 3 bullet's `Z`-only phrasing — grammar, not just suffix).
- `MissionPolicy` valid by construction: profile enum only; `HYBRID_REQUIRED` incompatible with single-source issuance expectations is enforced at decision construction; contradictory configurations raise.
- `issuance_mode != NONE` ⇒ `selected_input_refs` non-empty; `issuance_mode == NONE` ⇒ empty.
- **(C1/C5)** Every `*_utc` field validated against the exact D-H1-3 grammar `YYYY-MM-DDTHH:MM:SS.ffffffZ` (rejection, not normalization, of every other spelling). The declared clock basis is UTC and is documented in the module docstring.
- `confidence` in [0, 1]; digests hex-lowercase of declared length; identifier fields non-empty.

### 2. Stage 1 contract checklist discharge

Each checklist item from the companion maps to a concrete mechanism, asserted by tests:

| Checklist item | Mechanism |
| --- | --- |
| Session/peer/link/epoch/transcript identifiers | required non-empty fields on every decision-participating object |
| Timestamps, expiry, freshness rules, clock basis | `*_utc` exact-grammar validation (C1/C5); freshness *rules* documented as Stage 2 evaluation inputs (fields present, evaluation deferred) |
| Per-scope `AuthenticationEvidence` | `scope: AuthenticationScope`; both-scopes-present is a Stage 2 policy check, representability tested now |
| Immutable digests + schema versions | frozen dataclasses with deep-immutability conversion; envelope `record_type`/`schema_version`; SHA-256 over canonical envelope bytes via `serialization.py` |
| Secret-handle lifecycle / zeroization ownership | handles are opaque `str` refs; module docstring declares the future key-store module as zeroization owner; tests assert no field ever carries raw key bytes (type-level: no `bytes` fields in Stage 1 objects) |
| Provenance for selected and rejected contributors | `KeyProvenanceRecord.selected_input_refs` / `rejected_input_refs` both required (empty tuple allowed for rejected) |

### 3. `src/qkd/hybrid/registry.py` — posture registry snapshot interface (D3 pattern)

- `AlgorithmPostureRegistry` as an **independent registry** per the LINK-1 D3 registry pattern: its own module, its own declared contents, no coupling to `schema.DECLARED_SCHEMA_EXTENSIONS`.
- Read-only snapshot semantics: `RegistrySnapshot` (frozen) with `registry_version`, `produced_at_utc`, and postures by suite id — **no stored digest field (C8)**: the canonical digest is a computed property, `RegistrySnapshot.digest()` = SHA-256 over the snapshot's own canonical envelope bytes (which therefore contain no digest — no self-reference), via `serialization.stable_hash`. Consumers that persist or compare snapshots use the computed digest; a test asserts `digest()` is stable across processes and absent from the serialized payload. Policy evaluation (Stage 2) will consume snapshots, never the live registry.
- Freshness semantics defined on the snapshot (`produced_at_utc` + documented staleness rule as data, evaluated in Stage 2).
- **Mandatory CI consistency test** per D3: a test that fails if registry contents, enum vocabularies, and serialized vocabulary constants drift apart.

### 4. `src/qkd/hybrid/serialization.py`

- Canonical JSON encoder (sorted keys, explicit float handling, no NaN/Inf), `to_canonical_json` / `from_canonical_json` per contract, and `stable_hash` over the emitted bytes.
- Round-trip property: `from(to(x)) == x` for every contract type; digest stability across process runs.
- `schema_version = "hybrid-1.0"` embedded in every serialized record; unknown-key rejection on load (declared-or-fail, mirroring the project's existing schema discipline without touching `schema.py`).

### 5. Tests — `tests/test_hybrid_states.py`, `tests/test_hybrid_registry.py`, `tests/test_hybrid_serialization.py`

Required coverage (companion "Review-driven validation additions" items 4, 5, 6, 9 in their Stage 1 representability form, plus Stage 1 basics):

- Exhaustive invalid-`MissionPolicy` and invalid-`AssuranceDecision` construction rejection (every structural-invariant violation raises).
- `disposition=degraded` without explicit `issuance_mode` unrepresentable.
- Both-authentication-scopes representable and distinguishable.
- Serialization round-trip + digest stability for every type; digest computed from emitted bytes only.
- Registry CI consistency test (D3).
- Enum vocabulary freeze test (serialized values match companion vocabulary verbatim).
- Import-graph tests: `adaptive/contracts.py` imports nothing project-internal; nothing under `src/qkd/hybrid/` imports any physics module; `hybrid` imports from `adaptive.contracts` only; no module outside `hybrid` and (later) the tier-4 monitor imports `hybrid`.
- Byte-fixture tests for every record type's canonical envelope and digest (exact equality, fixtures in `tests/fixtures/`); timestamp grammar tests — the exact form accepted; `+00:00`, `.0Z`, `.000Z`, missing fraction, lowercase `z` each rejected, on **both** construction and load paths (C5); loader canonical-reserialization rejection test (non-canonical but semantically equal JSON refused, C6); deep-immutability tests per field type incl. `postures` pair-typing (C4); non-ASCII content round-trips under `ensure_ascii=True`.
- `AssuranceDecision` profile cross-check tests (HYBRID_REQUIRED ⇒ issuance ∈ {HYBRID, NONE}; violation raises) and RESEARCH_ONLY ⇒ NONE construction tests.

## Verification steps (before push)

1. Confirm no existing module or test path collides; repo is the authority over this packet's path guesses.
2. `pytest` and `pytest --ignore=tests/test_teleportation_qiskit.py`: record **actual** counts as evidence. Stop conditions: any existing-test regression from 622/601, or new-test count differing from the count the Development Record states.
3. Byte-level check that no file outside `src/qkd/adaptive/`, `src/qkd/hybrid/`, `tests/test_hybrid_*.py`, `tests/fixtures/` (new hybrid fixtures only), `README.md`, the Development Record, `docs/HYBRID_1_PLAN.md` (C11 — this packet itself, committed like `HYBRID_0_PLAN.md`), and `docs/architecture/pqc_hybrid_architecture.md` (C7 — exactly the v3.2 schema-listing addition + revision-log entry, nothing else; any other companion byte delta is stop-and-surface) changed.
4. **Staging hygiene (C10):** this allowlist is also the staging list — `git add` by explicit path only, never `git add -A` or `git add .`. Untracked non-HYBRID working files in `docs/` (currently `docs/LINK_7_PLAN.md`, a LINK-lane draft awaiting its own dispatch) must not enter any HYBRID-1 commit; `git status` after staging must show them still untracked.

## Development Record reconciliation (standing instruction — verbatim compliance)

Write the Development Record forward, describing post-push state directly: completed phases marked complete, no hedging. Omit the current commit's hash — Claude adds it during post-push certification. State test counts from the real pytest runs both with and without the qiskit extra (`--ignore=tests/test_teleportation_qiskit.py` as the no-qiskit proxy), stating the delta from the previous revision. Superseded numbers are preserved in dated Correction Log entries only; current-state facts appear once in the body.

Revision 15 content guidance (implementer drafts; forward-written):

- HYBRID-1 complete: tier-4-owned attribution contracts created at `src/qkd/adaptive/contracts.py` (created by HYBRID-1, owned by tier 4, per the D-H1-2 rule); boundary state model implemented under `src/qkd/hybrid/` per ADR-0004 and companion v3.1 Stage 1; contract checklist discharged item-by-item; D3-pattern posture-registry snapshot interface with CI consistency test; canonical serialization with stable digests; N new tests, actual counts stated with delta from 622/601.
- Blocking decisions D-H1-1/2/3 resolutions recorded as ratified.
- **(C3/C7/C9)** The `AssuranceDecision.policy_profile` field recorded as a deliberate deviation from the companion v3.1 schema section (Echo blocker 1 resolution), **and reconciled in the same push**: companion v3.2 ships in HYBRID-1's records commit (schema-listing addition + revision-log entry) — no knowingly-shipped implementation/schema drift, no deferral to a later touch.
- Explicitly restate: no policy engine, no cryptographic derivation, no authentication integration, no physics coupling; tier-4 monitoring spec now unblocked by the frozen contract interface (D-H1-2).

## Out of scope

- Stages 2–6 in their entirety; any change to `src/qkd/schema.py`, physics modules, or existing tests; any ADR edit (the C7 companion v3.2 edit is a companion edit, not an ADR edit).
- Tier-4 monitoring implementation (separate packet; gated on this stage's freeze of `adaptive.contracts`, which the monitor lane will extend in its own namespace rather than import from `hybrid`).
