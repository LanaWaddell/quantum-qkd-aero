# Codex Execution Packet: HYBRID-0 rev 3 (Stage 0 — Design Ratification, Docs Only)

- Date: 2026-08-23
- Prepared by: Claude. Rev 3 supersedes rev 2 (`da41c95bcdae449dd6b9a348be6f596674f4c71dd11c63cc62855839070c60d9`), applying the PI ratification-read round trip (`f3a9f22289fce19bc88f84e138d5ac7d80ed459c4195ae944e5632356c57b6fc`): two editorial corrections and refreshed exact-byte references. Rev 2 had superseded rev 1 (`89e4afd958674f18cad06defa30e1c9098ef5e207f32ac6d5d1a69658393e5d0`) applying the Echo/Codex fresh-eyes review (`71bc2fd8722e2832b04e9ec08f51c356bd3629dbfaba1dd765fed13e4b4dbe63`).
- Dispatch correction (Codex, 2026-08-23): the Scope version labels below are corrected from ADR r2 / companion v3 to ADR r3 / companion v3.1; Development Record references are advanced from the packet's stale Revision 13 baseline to live Revision 14; the stale LINK/test baseline is reconciled to live `11dd75e`. No execution-model or architectural change; source packet SHA-256 `a835e7dfe141067b2f557f5101eb29aeddbe7568931b28473397be209a623e56`.
- Lane status: HYBRID-0 is a new lane. **The LINK architectural lane remains active; LINK-1 through LINK-6b are complete.** HYBRID-0 Stage 0 is docs-only and creates no sequencing conflict; no code paths are touched.

## Scope

Commit the ratified ADR-0004 (r3) and the companion design note (v3.1), together with the README lane declaration and Development Record Revision 14, under the commit model below. No source code changes. Schema content in the companion is illustrative only at this stage; Stage 1 implements it.

## Precondition — PI ratification gate

**Do not push until the ADR-0004 r3 status line has been flipped from Proposed to Accepted by Lana.** PI architecture acceptance is recorded in the ratification-read round trip (`f3a9f22289fce19bc88f84e138d5ac7d80ed459c4195ae944e5632356c57b6fc`), subject to the two editorial corrections that rev 3 applies; the flip itself still occurs only in Commit A, at the PI's hand. If the status line still reads Proposed, stop and surface.

Lana's ratification of ADR-0004 also resolves the companion's status: on ratification, the companion is approved as the **informative companion** to ADR-0004 (it is companion material, not itself ratified content).

## Commit model — two-commit ratification structure plus certification commit (three commits total)

Rev 1 claimed a two-commit sequence while also requiring README and Development Record edits it assigned to no commit, and a post-push hash addition that necessarily creates another commit. Rev 2 states the executable model honestly. It remains the project's standard shape: minimal ratification commit, companion commit, and the existing convention that Claude's post-push certification adds commit hashes.

### Commit A — ratification commit (minimal, independently verifiable)

- File: ADR-0004 under the repository's actual ADR directory convention (verify against the repo tree; this packet's path guesses are not authority; note any adjustment in the Development Record).
- Content: exactly the ADR-0004 r3 file in this packet, with the status line flipped to Accepted by Lana.
- Nothing else in this commit.

### Commit B — companion and records commit

- `docs/architecture/pqc_hybrid_architecture.md`: the companion v3.1 from this packet, with **exactly one permitted Codex edit**: the frontmatter status line changes to `status: "informative companion to ADR-0004 (Accepted)"`. Any other byte delta from v3.1-as-corrected is a stop-and-surface condition.
- README: declare the HYBRID-0 lane (Stage 0 complete on push) without altering the LINK lane's active status or the completed status of LINK-1 through LINK-6b.
- Development Record Revision 14, forward-written per the standing instruction below. Revision 14 **includes Commit A's commit hash** (known at this point). Commit B's own hash is omitted — no commit promises its own hash.
- Commit B's commit message body records the SHA-256 of the as-committed companion file (a file digest, computable before committing), continuing the provenance chain: Echo v1 → v2 → v3-as-reviewed → round trip → v3.1-as-corrected → as-committed.

### Commit C — certification commit (post-push)

- After push, Claude performs fresh-clone certification: verifies the actual commit structure, recomputes the committed companion hash against the Commit B message anchor, confirms lane declaration and Development Record state, and reruns the test suite recording actual counts.
- Commit C then adds Commit B's commit hash and the certification note to the Development Record. This is the existing project convention (Claude adds hashes post-push) stated as an explicit commit rather than left implicit.

## Verification steps (before push)

1. Confirm ADR directory and companion path against the actual repo tree; repo is the authority.
2. Confirm README lane declarations: HYBRID-0 added; the LINK lane remains active and LINK-1 through LINK-6b remain complete.
3. Confirm the companion's only delta from v3.1-as-corrected is the single status line; record both hashes (v3.1-as-corrected and as-committed) in Revision 14's provenance chain.
4. Run the full test suite twice and record **actual** counts as the evidence of record:
   - `pytest` (with qiskit extra)
   - `pytest --ignore=tests/test_teleportation_qiskit.py` (no-qiskit proxy)
   - Stop condition: any delta from Revision 13.1's 622 / 601 is stop-and-surface. Expected counts are stop-condition thresholds only, never evidence; the Development Record states the actuals.

## Development Record reconciliation (standing instruction — verbatim compliance)

Write the Development Record forward, describing post-push state directly: completed phases marked complete, no hedging. Omit the current commit's hash — Claude adds it during post-push certification (Commit C). State test counts from the real pytest runs both with and without the qiskit extra (`--ignore=tests/test_teleportation_qiskit.py` as the no-qiskit proxy), stating the delta from the previous revision. Superseded numbers are preserved in dated Correction Log entries only; current-state facts appear once in the body.

Revision 14 content guidance (Codex drafts; forward-written):

- ADR-0004 r3 ratified: adaptive-coupling tier (tier 4) defined above the ADR-0003 channel tiers, with attribution as consistency-not-cause evidence; hybrid QKD+PQC boundary above the physics pipeline with evidence-stream separation. Commit A hash stated.
- Companion note v3.1 committed as informative companion: hybrid states; orthogonal policy result model (issuance mode / disposition / required actions); induced-degradation threat model (physical-layer downgrade attack, key-buffer depletion) with fail-closed attribution rules; boundary-schema contracts and Stage 1 checklist; staged roadmap (Stages 0–6). Stage 0 complete.
- Provenance chain stated: Echo v1 `6866…7bdb` → v2 `9dff…fe69` → Echo/Codex review `71bc…4b63` (review input, not authority) → v3 `7d66…6e38` → ratification-read round trip `f3a9…b6fc` (PI acceptance recorded) → v3.1-as-corrected → as-committed (hash in Commit B message).
- HYBRID-0 lane declared; the LINK lane remains active and LINK-1 through LINK-6b remain complete.

## Items explicitly out of scope for HYBRID-0 Stage 0

- Any implementation of schemas, policy engine, KDF adapter, or registries (Stages 1+); selection of the exact hybrid combiner construction (Stage 3, including verification of the precise SP 800-227 section reference).
- Any modification to ADR-0003, §3.3.1 composition rules, or the LINK-1 execution packet.
- Any IP disclosure filing. Note for PI's separate disclosure sweep (not a Codex task): the tier-4 attribution-gated fallback mechanism — channel-state feedback treated as adversarially shapeable input to crypto orchestration, with consistency-not-cause attribution evidence, fail-closed insufficient-evidence handling, fallback hysteresis, and recovery asymmetry — remains the strongest novelty candidate. Conception date 2026-08-23 is anchored by this packet lineage; the review-driven refinement (evidence-object model, non-causal semantics) is part of the same conception record.
