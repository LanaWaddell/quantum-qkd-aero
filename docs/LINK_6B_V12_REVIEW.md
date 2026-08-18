# LINK-6b Plan v1.2 Re-review

**Date:** 2026-08-18

**Plan reviewed:** `docs/LINK_6B_PLAN.md`

**Plan SHA-256:** `cf0c443e24b22a294a914c53c4d5f27b736e85b6ba3a05a61a9cd9406d9188a2`

**Prior review:** `docs/LINK_6B_REVIEW.md` (`41ed6376856d2774c0c240c4fe58b8127c0cd7d98fb151ec9c7c6e5f62ed10d1`)

## Disposition

**Approve after four narrow v1.2.1 contract corrections. No further physics redesign is required.**

All seven findings from the v1.1 review were substantively adopted. The shared-history correction, filter activation rules, versioned replay matrix, test-edit policy, phase domain, benchmark deferral, and ADR reconciliation are now architecturally sound. The remaining corrections are ordering or wording matters that should be frozen before dispatch so the implementer does not have to interpret them.

## Required corrections

### R1 - Scope the post-afterpulse invariant to the mappings that change gains

Section 8 now correctly tests the gate/filter shared-history coupling, but the phrase “post-afterpulse `Q'_vacuum` unchanged only when `p_ap = 0`” is too broad when read across all three LINK-6b inputs.

- Under **gate/filter acceptance**, `Q'_vacuum` is invariant at `p_ap = 0` and generally changes at `p_ap > 0` because signal/decoy gains change aggregate occupancy.
- Under **misalignment-only** input, gains and aggregate occupancy do not change, so `Q'_vacuum` remains unchanged even when `p_ap > 0`.

State those two cases separately in §8. The §1 introduction already scopes the corrected mechanism properly.

### R2 - Capture the historical v1 oracle before Gate A, not at Gate C

Section 5 and the file inventory call `tests/fixtures/link6a_manifest_v1.json` a real pre-6b artifact, but §10 says it is generated as “Gate C's first step.” Gates A and B have already changed production code by then, so Gate C cannot independently capture the pre-refactor behavior.

Add a **Pre-Gate 0** before any source edit:

1. Generate and commit the canonical v1 manifest through the live LINK-6a production path.
2. Capture its historical expected semantic output independently before any LINK-6b change.
3. After implementation, retain both safeguards:
   - exact in-process parity between `replay_from_provenance(v1_fixture)` and the real current production path reconstructed from that manifest;
   - comparison with the captured historical output using the project's established portable pattern: structure/stable serialization plus tolerant raw numeric-array comparisons, not a raw cross-environment byte hash alone.

The project has already established that byte identity is environment-local. A hash captured on one machine is not by itself the portable compatibility oracle, and an expected hash computed only after the refactor would be circular.

### R3 - Remove the deferred benchmark rule from Gate D

The benchmark enforcement is correctly deferred in §§6 and 8, and `benchmark.py` is correctly outside the modify set. Section 10 still defines Gate D as including the “benchmark coupled-cost rule.” Remove that phrase; Gate D should cover PDT integration, ensemble consistency, and final default-path/full-suite certification.

Also remove “and in `benchmark.py`'s docstring-level contract” from §6 unless a docstring-only `benchmark.py` edit is explicitly added to the inventory. The current plan says that file is untouched; the prohibition can live in LINK-6b and become executable with the first driver/LINK-6c.

### R4 - Record the PI decision and freeze the ADR status-log text

Lana has now approved decision §11-5: the clarification belongs in ADR-0003's status log so future work does not rely on superseded illustrative wording. Replace “PI to confirm” with **confirmed** and include the exact entry the implementer must add.

Recommended status-log entry:

> 2026-08-18 — **PI clarification for LINK-6b (Lana):** §3.6 item 1's statement that composed `timing_jitter_s` “bounds how tight Delta t can go” is illustrative motivation, not a mandate to manufacture an arbitrary hard lower bound. Under LINK-6b's centered-Gaussian timing model, timing coupling is implemented by the declared gate-acceptance response/cost law and adjacent-gate model-validity guard. `ControlSpec.feasible` remains reserved for genuine hardware-feasibility intervals. Control declaration, bounds, auditability, and replay requirements remain binding; the ADR decision body is otherwise unchanged.

Use the repository's existing Unicode `Delta t` notation if desired; the semantic text should remain fixed. This is a clarification of the ratified decision, not a new LINK feature or a relaxation of control auditability.

## Findings confirmed closed

### B1 - Shared detector history

Closed. The plan now distinguishes invariant direct/base noise from the emergent post-afterpulse vacuum gain and requires the correct cross-intensity test.

### B2 - Filter activation

Closed. The five-branch rule is complete, prevents silent neglect of nonzero source linewidth, and preserves exact identity behavior.

### B3 - Replay versions

Closed subject to R2's historical-oracle ordering. The v1/v2 matrix prevents hybrid receiver schemas, pipeline versions, effects, and controls while preserving schema version `2.0`.

### B4 - Existing-test exceptions

Closed. The exact affected tests and helpers are enumerated, the already-existing intensity rejection remains untouched, and trailing `0.0` fields preserve legacy `ReceiverInputs` constructions honestly.

### B5 - Phase domain

Closed. Enforcing `0 <= delta_phi_rad <= pi/4` on the parameter removes the periodicity loophole.

### B6 - Benchmark scope

Closed subject to R3's stale Gate-D wording. Deferring machine enforcement until a real driver/LINK-6c is the lower-risk choice.

### B7 - ADR reconciliation

Closed in design; R4 records Lana's approval and makes the exact status-log edit executable.

## LINK-6c note

The candidate is now labeled provisionally and correctly records the unresolved radiance/rate-density ownership, FOV signal cost, measured-rate override, and flat-spectrum assumption. It is suitable as a sequencing note, not yet an implementation contract.

## Final gate

After R1-R4 are incorporated textually, LINK-6b is approved for dispatch through its Pre-Gate 0 and Gates A-D. Re-review can be a brief hash-and-text confirmation; the equations and architecture do not need another full cycle unless those sections change.

No implementation files or tests were modified during this re-review, and the suite was not rerun because the implementation baseline is unchanged.
