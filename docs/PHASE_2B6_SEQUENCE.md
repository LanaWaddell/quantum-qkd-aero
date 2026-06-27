# Phase 2B-6 — Single Authoritative Pipeline → Honest Composition → Provenance

**Codex prompt / architecture spec (CORRECTED SEQUENCE). Draft for Echo review.**

> **Supersedes** the earlier single-PR `PHASE_2B6_HONEST_PASS_AND_PROVENANCE.md`.
> That draft was written against a stale mental model and was wrong on two
> load-bearing points (its `fidelity_noise`-is-unused claim and its root-`results.json`
> handling). Both are corrected here against repo HEAD. Do not implement the prior draft.

Two-phase Codex gate per PR: Codex returns a **plan**, waits for approval, then
implements and returns **diffs + test output**. Reconcile every claim below against
the *actual* files before editing.

**Standing review protocol (adopted after this episode).** Before proposing any
architectural change, enumerate (a) every executable entry point, (b) every writer of
every generated artifact, and (c) every external consumer. The stale-model error that
reordered this work was an *execution-graph* blind spot, not a physics one — it would
have been caught at step (b). This enumeration is now a required first step of every
architectural review.

---

## 0. The finding that reordered this work (verified at repo HEAD)

There are **two simulator entry points**, and one is a complete live decorative
simulator the dev record implies no longer exists:

- `qkd_model.py` (repo root) imports `TeleportationMission` and
  `build_teleportation_results` from `teleportation.py`, runs the original
  decorative fidelity curve `0.85 + sin(f/50)*0.05` (`teleportation.py:153`) and the
  linear entangled-resource countdown `current_resource -= 0.01` from `15.0`
  (`teleportation.py:125,159`), calls `fidelity_noise`, and writes
  `outputs/results.json` — the **same file** `run.py` writes. Whichever ran last
  wins the dashboard.
- These symbols are **not** orphaned: `TeleportationMission`,
  `build_teleportation_results`, and `fidelity_noise` are imported/called by
  `qkd_model.py` and covered by `tests/test_teleportation.py` and
  `tests/test_channel.py`.

The dev record's claim that the decorative fidelity curve and the resource countdown
are "now gone or grounded" is therefore **true only for the `run.py` path** and
false for the codebase as a whole. The decorative engine was orphaned from `run.py`
and never removed.

**The deeper diagnosis (not "decorative code exists" — "two producers, one artifact").**
The sharper framing is that `outputs/results.json` had **two competing producers**
(`run.py` and `qkd_model.py`) racing for the same file. Until exactly one authoritative
pipeline writes each artifact, the project cannot honestly claim "computed, not
decorative," because two different programs can generate the same output and the
dashboard cannot tell which one it is showing. The failure was in the **execution
graph**, not the physics — which is why it was invisible to physics-level reasoning and
only surfaced by enumerating who actually writes the file. PR0 therefore establishes a
durable repository invariant (§4.0), not just a deletion.

**Consequence:** removing this path is not cleanup riding alongside the real work —
it *is* the real "remove the last decorative physics" deliverable, and it must come
first (PR0). It also simplifies two downstream problems: deleting
`build_teleportation_results` removes the sole honest emitter of the misleadingly
named `remaining_entangled_resource_kb` key, which dissolves the
right-number-wrong-name dilemma (the key's only remaining references become the
schema validator and its test, so it can be dropped cleanly in PR1).

The **dev record must be corrected** (see §9): "orphaned-but-present in `qkd_model.py`,
retired in PR0," not "gone."

---

## 1. Sequence

- **PR0 (2B-6a) — Restore Single Authoritative Pipeline.** Retire the legacy decorative
  simulator; the deletion is the *mechanism* by which the one-producer-per-artifact
  invariant is restored. No schema change, no `run.py` rewrite. Self-contained; suite
  stays green.
- **PR1 (2B-6b)** — Honest pass composition (`mission.py`, yield integral, fidelity
  arch, `run.py`→I/O-only, drop the dead key), with provenance **co-designed from
  birth** (no retrofit).
- **PR2 (2B-6c)** — Provenance *hardening* as focused infrastructure (reserved-tag
  non-use, DERIVED-input transitive consistency, the formal SIMULATED/DERIVED
  boundary, INTERFACES provenance contract).

---

## 2. OPEN DECISIONS — Lana + Echo, before the relevant PR

1. **`qkd_model.py` fate (PR0) — RESOLVED: delete.** Decision made (Lana + Echo):
   delete the file, do **not** archive the code; preserve the *decision* via the ADR
   (§4 task) plus git history. Rationale below stands as the recorded reasoning.
   "Retire" ≠ "delete"; the value-questions were answered: it has **no unique
   non-decorative capability** (its plot renders the decorative curve/countdown; `run.py`
   already plots richer computed values); it is **not** a regression reference (it is the
   thing being removed *because* it is wrong); its only value is historical (the original
   "Mission Lana" prototype, initial commit `2924673`). A moved-but-unmodified copy would
   be a *broken* file (PR0 removes the symbols it imports), and a faithful archive would
   mean freezing self-contained decorative code — strictly more foot-gun, opposite to the
   single-producer goal. Git history + the ADR preserve everything of value.

2. **`ChannelState.transmittance` contract (BLOCKS PR1 — correctness).**
   `run_decoy_bb84` and `coherence.signal_coincidence_rate` both compute
   `eta = transmittance * detector_efficiency` (verified). This is only correct if
   `transmittance` **excludes** receiver detector QE. Recommendation: ratify in
   `docs/INTERFACES.md` that `ChannelState.transmittance` is link transmittance *up to
   but not including* receiver detector QE (`channel.system_efficiency` = transmit/
   optics/coupling only); detector QE is owned solely by
   `DetectorParams.detection_efficiency`. No defaults change. Guarded by PR1 test A3.

3. **Pulse repetition rate (BLOCKS the PR1 yield number).** The yield (kilobits) is a
   per-pulse rate integrated over time, so it needs `f_rep`. No calibrated value
   exists. Recommendation: declare `PULSE_REPETITION_RATE_HZ` as a documented
   **ILLUSTRATIVE** constant (proposed `1.0e8` Hz), explicitly distinct from
   `coherence.DEFAULT_SOURCE["pair_rate_hz"]` (`1.0e7`), which models the entangled
   pair source. Confirm value or override.

4. **Provenance PR1/PR2 boundary (Echo ratifies).** Recommendation: PR1 ships the
   composition *born provenance-tagged* (the in-use enum applied, results.json emits a
   `provenance` block, completeness/honesty tests for what PR1 emits). PR2 hardens the
   *mechanism* (reserved-tag non-use enforcement, DERIVED-input transitive-consistency,
   formal boundary, INTERFACES contract). This honors Echo's "provenance first-class,
   not a retrofit" while keeping the new enforcement infrastructure in its own focused
   review. Echo: ratify this split, or fold all provenance into PR1.

5. **Run-metadata stamp (PR1, low-risk).** Add a minimal `run_metadata` block to
   `outputs/results.json` identifying the producer — `{generator: "run.py", pipeline:
   "mission.simulate_pass", physics_mode: "computed"}` — so the artifact is
   self-describing and a future second producer is visible immediately. This aligns with
   the `run_metadata` section `schema.py` already reserves for v2. **Deferred:** `commit`
   and `timestamp` — they make `results.json` non-deterministic, and this suite's
   determinism is load-bearing. If added, tests must assert presence-and-type, never
   value. Confirm minimal-now vs include-commit/timestamp.

6. **Uncertainty seed (PR2, optional).** Confidence is orthogonal to origin and will
   matter for the optimization/inverse work. A hand-set `uncertainty: HIGH` label would
   itself be decorative; the honest form is *derived* — a value's confidence falls out of
   its inputs' provenance. Since PR2 already walks the input graph (B5), the cheap on-ethos
   seed is one **computed** boolean per emitted quantity, `depends_on_illustrative`
   (true if any transitive input is `ILLUSTRATIVE`), which flags exactly the numbers
   sensitive to `f_rep`/intensities/sky-rate. **Recommendation: ship the boolean seed;
   defer the full LOW/MED/HIGH propagation** to the phase that consumes it (building the
   whole scale now is speculative generality). Echo/Lana: approve the seed, or defer
   entirely.

7. **Layer naming (non-blocking).** No trust/cognitive layer or field is introduced in
   any of these PRs. Defer the name; do not introduce "trust" terminology here.

---

## 3. Architectural boundaries (the wall — reviewer-rejection criteria)

- No new field on any `signals.py` dataclass. `PhysicsSignals` is populated, never
  extended.
- `mission.py` **composes**; it introduces no new closed-form or emergent physics.
- After PR1, `run.py` does **I/O only** — no physics arithmetic.
- Provenance is metadata: tagging a quantity must not change the quantity.
- No attacker on the honest pass. `mission.simulate_pass` accepts an optional `eve`
  (defaulting to `None`) for 2D-readiness but PR1/PR2 exercise and test only
  `eve=None`. `QND_PNS`'s low-loss `ValueError` is out of scope by construction.

---

## 4. PR0 (2B-6a) — Restore Single Authoritative Pipeline (retire legacy decorative simulator)

**Framing:** this is not "delete old code" — it is *restoring the architectural invariant
that each generated artifact has exactly one authoritative producer* (§4.0). The deletion
is the mechanism, not the point.

**Why first:** the central thesis of Phase 2B ("computed, not decorative") is false in
practice while a decorative simulator writes the shared output file. This PR makes the
thesis true.

**§4.0 Repository invariant established by this PR (durable, mechanically checkable):**
> *There shall be exactly one authoritative production pipeline per generated artifact.
> Any historical or experimental pipeline must write to a separate, clearly-labelled
> output and must never overwrite a production artifact.*

This is the durable rule the two-producer bug violated; it outlives this PR and is a
standing reviewer-rejection criterion. For `outputs/results.json` the sole authoritative
producer is `run.py` (via `mission.simulate_pass`). Codex verifies mechanically:
`grep -rn "results.json" --include=*.py` must show exactly one writer of the production
path.

**Deletions (verified consumers at HEAD):**
- `qkd_model.py` — delete the file (Open Decision 1).
- `src/qkd/teleportation.py` — remove class `TeleportationMission` (≈L116–162) and
  `build_teleportation_results` (≈L165–181); remove the now-dead
  `from qkd.channel import fidelity_noise` (L7) and `import statistics` if unused after
  removal. **Keep** `teleportation_fidelity`, `TeleportationResult`, and all
  computed/numeric/qiskit machinery untouched.
- `src/qkd/channel.py` — remove `fidelity_noise` (≈L39–50).
- `tests/test_teleportation.py` — remove `test_teleportation_mission_current_output_lengths`
  and `test_build_teleportation_results_current_schema`; drop `TeleportationMission,
  build_teleportation_results` from the import. Keep the 7 `teleportation_fidelity` tests.
- `tests/test_channel.py` — remove `test_fidelity_noise_clamps_to_unit_interval`; drop
  `fidelity_noise` from the import.
- `./results.json` (repo root) — `git rm`. It is a pre-nesting committed artifact
  (flat `{key_yield, fidelity}` shape) that no current entry point writes.
- Grep for any runner references to `qkd_model.py` (README, `package.json`, CI,
  Makefile) and update/remove them.
- **Archive the decision, not the code (new ADR).** Create
  `docs/architecture/ADR-0001-single-authoritative-pipeline.md` capturing: why
  `qkd_model.py` originally existed (the original "Mission Lana" prototype), what it
  demonstrated, why it was retired (it violated the §4.0 single-producer invariant by
  writing the same production artifact as `run.py`), the introduced commit
  (`2924673`, 2026-04-06 — initial commit; predates the 2B refactor), and the removing
  commit (this PR0). This preserves the reasoning and the provenance pointers without
  keeping obsolete executable code on disk — git history plus the ADR is the archive.
  Establishes a light ADR convention for future structural decisions.

**Not touched by PR0:** `schema.py`, `run.py` (still emits its own `5.0` placeholder —
that is PR1's job). The decorative *simulator* dies here; `run.py`'s placeholder dies
in PR1.

**PR0 acceptance:**
- `grep -rn "TeleportationMission\|build_teleportation_results\|fidelity_noise"
  --include=*.py` returns nothing.
- No remaining importer of the deleted symbols; no unused imports left behind.
- **§4.0 invariant holds:** exactly one writer of `outputs/results.json` (`run.py`);
  `grep -rn "results.json" --include=*.py` confirms a single production writer.
- Suite: **71 passed, 1 skipped** (without qiskit) / **92 passed** (with the qiskit
  extra). (Down 3 from 74/95: the three legacy tests above.)

---

## 5. PR1 (2B-6b) — Honest composition, born provenance-tagged

### 5.1 Physics rationale
- **Yield is an integral, not a piped rate.** `bb84.secure_key_rate` returns secure
  bits **per emitted signal pulse** (GLLP, basis-sift `q` applied, clamped to
  `max(0,·)`). The placeholder it replaces (`5.00 Kb`) is a **yield**. Honest yield:
  `secure_key_yield_bits = Σ_samples SKR_i · f_rep · Δt_sample`. Horizon samples
  (`SKR_i→0`) contribute zero via the existing clamp; a full collapse yields `0.0`
  honestly (a computed zero, not a placeholder).
- **Fidelity arches for a real reason.** Per-sample
  `coherence.effective_werner_p_for_sky(transmittance_i, werner_p_source,
  detector_efficiency, sky_condition=...)` → `teleportation_fidelity(p_eff_i)`. Day:
  arches over the pass, dips below 2/3 near the horizon (background `B` independent of
  link `η`; signal `S ∝ η`). Night (`B=0`): flat at the source value (~0.99). The
  displayed fidelity stops being flat because the physics says it shouldn't be.

### 5.2 Tasks
- **`src/qkd/mission.py`** (replace stub): `simulate_pass(config=None, *, eve=None) ->
  PassResult`. `PassResult` (new dataclass) holds geometry passthrough; per-sample
  `transmittance`, `loss_db`, `secure_key_rate_per_pulse`, `effective_werner_p`,
  `fidelity`; aggregates `min_loss_db`, `min_loss_index`, `secure_key_yield_bits`,
  `mean_fidelity`; **and a `provenance` map (the co-design seam — see §6).** Calls
  `satellite_pass`, `channel_state`, `run_decoy_bb84` (eve=None),
  `coherence.effective_werner_p_for_sky`, `teleportation_fidelity`. Illustrative
  constants (`PULSE_REPETITION_RATE_HZ`, pass `INTENSITIES`, pass `DetectorParams`,
  default `sky_condition`) live here as documented module constants. **No I/O.**
- **Yield + arch:** implement §5.1 inside `simulate_pass`. `Δt_sample` from uniform
  `time_s` spacing; rectangular sum; yield in bits → Kb for display only.
- **`src/qkd/run.py`** → I/O only: `result = simulate_pass()`; render plot from
  `result` (now plotting the **per-sample arched fidelity**, not a flat line); write
  `outputs/results.json` (additive v1 shape + `provenance` block); print headline.
  Remove the `5.0` placeholder and all physics arithmetic.
- **Drop the dead key (schema):** stop emitting `remaining_entangled_resource_kb`;
  remove it from `schema.py:V1_REQUIRED_KEYS["teleportation"]`; update the v1 fixture in
  `test_schema.py`. This is a contained v1 evolution (drop one dead required key), **not**
  the v2.0 validator-hardening flip (§7). The honest yield goes to
  `summary.headline_key_yield` (a correctly named field — the dashboard already reads it).
- **`docs/INTERFACES.md`:** ratify the transmittance pre-detector contract (Open
  Decision 2) and the `f_rep` illustrative constant.
- **Run-metadata stamp (Open Decision 5):** emit a `run_metadata` block in
  `outputs/results.json` — minimal deterministic fields `{generator: "run.py",
  pipeline: "mission.simulate_pass", physics_mode: "computed"}` — so the artifact
  self-identifies its producer (operationalizing the §4.0 invariant). Additive v1 key;
  aligns with the `run_metadata` section reserved in `schema.py` for v2. Omit
  `commit`/`timestamp` unless Open Decision 5 elects to include them, in which case
  tests assert presence-and-type only (never value), to preserve suite determinism.

### 5.3 PR1 acceptance tests (verification anchors)
- **A1 — yield is the integral, not a constant.** Independently recompute
  `Σ SKR_i·f_rep·Δt` from `simulate_pass()` internals; assert equals emitted yield.
- **A2 — yield honest-zero control.** Force `SKR_i=0` ∀ samples (extreme loss); assert
  emitted yield `== 0.0`, provenance tag `DERIVED`.
- **A3 — detector QE applied once (guards Open Decision 2).** Halving
  `DetectorParams.detection_efficiency` halves the single-photon contribution to the
  signal gain (and so is reflected once in SKR); assert the single-fold scaling — no
  double-count against `transmittance`.
- **A4 — arch shape, daytime.** Per-sample fidelity peaks at/near `min_loss_index`,
  decreases toward both horizons, dips below 2/3 at the horizon samples.
- **A5 — arch night-flat control.** `sky_condition="night"` ⇒ every per-sample fidelity
  equals `teleportation_fidelity(werner_p_source).fidelity` to 1e-9 (B=0 honesty guard).
- **A6 — headline preserved.** Min-loss still ≈ 27.7 dB (geometry untouched); printed/
  JSON fidelity now equals `mean_fidelity` (night default ⇒ still ~0.990).
- **A7 — schema.** `detect_results_schema(results)` returns `"1"`; updated
  `test_schema.py` passes; the dropped key is gone from required-keys and emission; the
  `provenance` block does not break v1 recognition.
- **A8 — boundary guard.** `signals.py` dataclasses unchanged; `run.py` contains no
  physics arithmetic.
- **A9 — producer self-identification.** `run_metadata.generator` / `.pipeline` in the
  emitted JSON name `run.py` / `mission.simulate_pass`; assert presence and these
  values. (Any `commit`/`timestamp` fields, if included, are asserted by type only.)

---

## 6. PR2 (2B-6c) — Provenance hardening

### 6.1 `src/qkd/provenance.py` (introduced co-designed in PR1, hardened here)
`Provenance` enum. **In use** (each has a checkable instance): `ANALYTIC` (exact closed
form, e.g. the 2/3 bound), `SIMULATED` (output of a physics-model call, e.g. per-pulse
SKR via `run_decoy_bb84`, `p_eff` via `coherence`), `DERIVED` (pure function of
already-tagged values, e.g. the yield integral, mean fidelity, min-loss),
`ILLUSTRATIVE` (representative non-calibrated parameter, e.g. `f_rep`, intensities, sky
rates). **Reserved** (declared, must not appear in output until a checkable instance
exists): `MEASURED`, `ESTIMATED` (reserved for the future inverse-problem work),
`VALIDATED` (could later apply to the qiskit-confirmed teleportation path).

**Operational boundary (the line Codex applies on every field):**
> `SIMULATED` = the value is the direct output of a physics-model function call.
> `DERIVED` = the value is a pure function of values that are themselves already tagged.

### 6.2 PR2 acceptance tests
- **B1 — completeness** (may land in PR1): every field under `summary` and
  `teleportation` in results.json has a `provenance` entry.
- **B2 — illustrative honesty:** every `ILLUSTRATIVE` value equals a named module
  constant (not an inline literal).
- **B3 — analytic anchor:** the `ANALYTIC` classical bound equals 2/3.
- **B4 — reserved non-use:** no emitted field carries a reserved tag.
- **B5 — DERIVED transitive consistency:** every `DERIVED` field's inputs are
  themselves tagged (computed), per the operational boundary. (This is the
  Chat-Claude/Echo strengthening: labels are checked for *consistency*, not just
  presence.)
- **B6 — uncertainty seed (OPTIONAL, Open Decision 6).** If approved: emit a *computed*
  boolean `depends_on_illustrative` per quantity (true iff any transitive input is
  `ILLUSTRATIVE`), derived from the same input-graph walk as B5. Test: the yield (depends
  on `f_rep`/intensities) is flagged true; a pure-`ANALYTIC` quantity (the 2/3 bound) is
  flagged false. The full LOW/MED/HIGH scale is **deferred** to the optimization/inverse
  phase that consumes it — do not build it here.

---

## 7. Schema decision (confirmed)

- PR0: no schema change.
- PR1: **v1 + drop one dead required key** (`remaining_entangled_resource_kb`) and add
  the honest values + `provenance` block as additive keys. `schema_version` stays
  absent. Dropping a single dead key is a contained v1 evolution — explicitly **not**
  the v2.0 flip, which `schema.py`'s own TODO says requires the L2–L5 validator
  hardening (`SCHEMA_HARDENING_2B.md`) as a separate PR. Bundling that hardening here
  would be the half-switch the project warned against. **Deferred.**

---

## 8. Out of scope (do not start here)

- v2.0 schema emission + L2–L5 validator hardening (separate PR).
- Any trust / cognitive / adaptive layer or field (Phase 2D).
- Attacker injection on the displayed pass; the `QND_PNS` low-loss `ValueError` path.
- `BaseChannel` ABC / a second channel implementation — introduce **with** the fibre
  front-end when two channels genuinely exist to generalize over, not speculatively.
- The inverse problem / Bayesian state estimation (`ESTIMATED` tag reserved for it).

---

## 9. Dev-record correction (required, do promptly — it's the handoff artifact)

Correct `Quantum-QKD-Aero_Development_Record.md`: the decorative fidelity curve
`0.85 + sin(frame/50)*0.05` and the linear resource countdown were **orphaned-but-present
in `qkd_model.py` / `TeleportationMission`**, not gone; they are **retired in PR0
(2B-6a)**. A future session that reads "now gone or grounded" and builds on it inherits a
false premise. The fix is small but load-bearing. (Can be produced as a separate edit;
flagged here so it isn't lost.)

---

## 10. How Claude verifies in sandbox before sign-off

Re-derive the yield integral from raw per-sample SKR and compare to emission; reproduce
night-flat and daytime-arch shapes from `coherence` directly; confirm detector-QE
single-fold scaling by hand against `_honest_gain`; confirm zero remaining importers of
the deleted symbols after PR0; run the full suite with and without the qiskit extra.
Findings reported pass/fail against §4/§5/§6, not taken on trust from the diff.
