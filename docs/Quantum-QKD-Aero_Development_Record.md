# Quantum-QKD-Aero — Technical Development Record (Phase 2B)

> **REVISION 5 — updated 2026-06-27.** This revision records completion of
> PR-Fibre-1, committed with this change (hash: pending). The dedicated-fibre
> front-end is now the first substitution test of the `ChannelState.transmittance`
> representation contract. Historical corrections and superseded counts/statuses
> are preserved in the Correction Log rather than repeated as current body facts.

**Scope of this document:** a phase-by-phase record of the Phase 2B physics build —
what was implemented, how it was verified, the honesty guards in place, the file
and test inventory, current repo state, and the precise next steps. This is the
handoff artifact: a fresh session (a new Claude instance, or Codex) should be able
to read this plus `docs/INTERFACES.md` and `docs/PHASE_2B6_SEQUENCE.md` and pick up
exactly where the work stands.

Repo: `github.com/LanaWaddell/quantum-qkd-aero` · local: `Quantum-QKD-Aero/`
Working method: Claude = physics/architecture critic + reference-code author
(verifies in a sandbox); Codex = repo-access implementation engineer; Echo =
systems-level integrator/reviewer; Lana = PI. **All agent outputs are verified, not
trusted.** Standing review rule (adopted 2026-06-27): before proposing architectural
change, enumerate every executable entry point, every artifact writer, and every
external consumer — the error above was an execution-graph blind spot, not a physics one.

---

## 0. The through-line: "computed, not decorative"

The entire 2B arc replaced placeholder quantities with values derived from first
principles and checked against an analytic truth or a structural physical property.
The original decorative quantity was the teleportation fidelity curve
`0.85 + sin(frame/50)*0.05`. A second decorative quantity was later found — a
linear "entangled resource" countdown (`15.0 → 5.0 Kb` by subtracting 0.01/frame).
A semi-decorative third (an interpolated orbit) was also found and replaced.

The durable invariant is now twofold: exactly one authoritative production pipeline
writes each generated artifact, and each physical quantity has one owning layer. The
current pipeline composes geometry/orbit, channel transmittance, decoy BB84, background
coherence, teleportation fidelity, and provenance-enforced v1 emission without a second
writer. PR-Fibre-1 extends that discipline sideways: a fibre front-end computes the same
`ChannelState.transmittance` representation by a different physical model, and the
existing downstream physics stack consumes it unchanged.

The discipline throughout otherwise holds: if a quantity isn't checked against a
known-true value or a structural invariant, it isn't trusted — and verification
repeatedly caught real errors (including several of Claude's own, and this one).

---

## 1. Phase status overview

| Phase | What | Status |
|-------|------|--------|
| 2B-1a | Computed teleportation fidelity + CHSH (analytic + numpy) | ✅ committed |
| 2B-1b | Qiskit density-matrix validation of teleportation | ✅ committed |
| 2B-2  | Honest channel: η computed, source werner_p constant | ✅ committed |
| 2B-3  | Real satellite pass → loss arc; sine curve removed *from run.py* | ✅ committed |
| 2B-3 (orbit hardening) | Replace interpolated orbit with derived geometry | ✅ committed |
| 2B-4a | Honest decoy-state BB84 foundation | ✅ committed |
| 2B-4b | QND/PNS Eve (hidden breach) + secure key rate | ✅ committed |
| 2B-5  | Background light → effective werner_p (fidelity arch) | ✅ committed |
| **2B-6a** | **Restore Single Authoritative Pipeline (retire legacy decorative path)** | ✅ committed |
| **2B-6b** | **Honest pass composition (mission.py, yield integral, fidelity arch, run.py→I/O)** | ✅ committed |
| **2B-6c** | **Provenance hardening (enforcement, consistency, boundaries)** | ✅ implemented in current repo |
| **PR-Fibre-1** | **Dedicated-fibre front-end contract validation** | ✅ committed with this change (hash: pending) |

**Test suite (current Rev-5 count):** with the qiskit extra available, the suite is
**125 passed** (`qkd_env/bin/python -m pytest -v`). The base suite excluding
Qiskit-specific tests is **104 passed**
(`qkd_env/bin/python -m pytest -q --ignore=tests/test_teleportation_qiskit.py`).
Delta from Rev 4: **+10 collected tests** from `tests/test_fibre.py`. The Phase A plan
described seven logical fibre tests; the collected delta is +10 because the invalid-input
case is parametrized across three inputs. This is expected and recorded here rather than
hidden.

`python src/qkd/run.py` still prints `Min loss 27.7 dB | Fidelity 0.990` (verified).

---

## 2. Phase-by-phase detail

*(Verified accurate at Rev 5 against the repo; earlier historical notes are retained
where they explain how the system evolved.)*

### 2B-1a — Computed teleportation fidelity & CHSH
**Files:** `src/qkd/teleportation.py`, `src/qkd/chsh.py`, `tests/test_teleportation.py`,
`tests/test_chsh.py`, `tests/test_coupling.py`.

- **Teleportation:** `teleportation_fidelity(werner_p)` → `F = (1+p)/2` via the
  Werner singlet fraction `f = (1+3p)/4` and the Horodecki relation
  `F = (2f+1)/3`. Benchmarked against the classical bound `2/3`. `beats_classical`
  uses strict `>`.
- **CHSH:** `chsh_value(werner_p)` → `S = 2√2·p`, vs. classical bound `2.0` and
  Tsirelson `2√2`. Driven by the SAME `werner_p` as teleportation — physically coupled.
- **Methods:** `analytic` and `numeric` (explicit Werner density matrix in numpy);
  must agree to 1e-9. Constant thresholds asserted (F=1 at p=1; F=2/3 at p=1/3;
  S=2√2 at p=1; S=2 at p=1/√2).
- **Coupling fingerprint:** `test_coupling.py` asserts that in `1/3 < p < 1/√2` the
  state beats the classical teleportation bound but does NOT violate CHSH — the two
  thresholds differ (1/3 vs 0.7071). A single drawn curve cannot reproduce this.

### 2B-1b — Qiskit density-matrix validation (optional)
**Files:** `src/qkd/teleportation.py` (`method="qiskit"`), `tests/test_teleportation_qiskit.py`,
optional `[qiskit]` extra in `pyproject.toml`.

- Third validation path: coherent teleportation circuit using Qiskit's deterministic
  `quantum_info` density-matrix/Kraus APIs, Werner resource via a depolarizing channel
  with **λ = 1−p**, averaged fidelity via the Choi/entanglement-fidelity route
  (`F_avg = (2·F_e + 1)/3`). Deterministic; tests to 1e-9.
- The recipe was verified independently in numpy first; an intermediate test asserts the
  resource singlet fraction `(1+3p)/4`, guarding the λ=1−p mapping.
- Result: analytic = numeric = qiskit. Current verified local version: qiskit 2.4.1.
  `qiskit-aer` 0.17.2 may remain installed in the local environment from earlier
  validation, but it is not imported by the repo and is no longer declared in the
  optional `[qiskit]` extra.

### 2B-2 — Honest channel
**Files:** `src/qkd/channel.py` (extended), `tests/test_channel.py` (extended).

- `channel_state(...) → ChannelState`. **Transmittance η is COMPUTED:**
  `η = system_efficiency × T_atm × T_geo`, `T_atm = exp(−τ_zenith / sin(elevation))`,
  `T_geo = 1 − exp(−2a²/w²)` (`rx_aperture_m` is the **diameter**).
- **werner_p is SPECIFIED, not weather-derived.** Honesty guard: turbulence changes η
  but NOT werner_p.
- Parameters illustrative, not calibrated. η is realistically tiny (~1e-3 to 1e-4).
- **Contract note:** `ChannelState.transmittance` excludes receiver detector QE
  (owned by `DetectorParams.detection_efficiency`); both `run_decoy_bb84` and
  `coherence.signal_coincidence_rate` multiply the two. PR1 ratified this in
  `docs/INTERFACES.md`, documented `system_efficiency` as transmit/optics/coupling up to
  the detector face, and added a single-fold detector-efficiency scaling guard in
  `tests/test_mission.py`.

### 2B-3 — Real satellite pass; sine curve dies (in run.py)
**Files:** `src/qkd/run.py` (rewritten), `src/qkd/orbit.py` (new), `tests/test_orbit.py` (new).

- Historical 2B-3 state: `run.py` drove a satellite pass → per-sample `channel_state()` →
  η → loss in dB, with computed `teleportation_fidelity(werner_p)` as a flat reference.
  `fidelity_noise` stopped being called by `run.py` here; the later discovery of a
  second legacy writer is recorded in the Correction Log.
- Loss reported as positive-magnitude dB; "min loss" = closest approach.
- `results.json` keeps v1 schema keys valid and adds a `pass_profile` block.
- PR1 moved this pass composition out of `run.py` and into `mission.py`. The
  `remaining_entangled_resource_kb` / `5.00 Kb` placeholder has been retired; honest
  yield is now an integral of per-pulse SKR over the pass.

### 2B-3 orbit hardening — derived geometry
**Files:** `src/qkd/orbit.py` (replaced), `tests/test_orbit.py` (10 tests).

- Circular orbit + great-circle track. `d(γ)=√(R_E²+r²−2R_E·r·cos γ)`,
  `E(γ)=atan2(cos γ − R_E/r, sin γ)`, `γ_min=arccos((R_E/r)cos E_max)−E_max`,
  `ω=√(μ/r³)`. `EARTH_RADIUS_KM=6371`, `EARTH_MU_KM3_S2=398600.4418`.
- **Coupling-proof test:** slant range recomputed from elevation matches to 1e-6. Zenith
  slant range = altitude. Consequence: `Min loss` shifted 21.7 → 27.7 dB (closest
  approach 550 km, ~+6 dB ≈ 10·log10(4)).

### 2B-4a — Honest decoy-state BB84
**Files:** `src/qkd/bb84.py` (extended), `tests/test_decoy.py`.

- `run_decoy_bb84(...) → BB84Result`, deterministic expectation-value statistics.
- Implements honest gain `Q_μ = Y0 + 1 − e^(−η·μ)`, per-intensity QBER, Lo–Ma–Chen decoy
  bounds (`estimate_decoy_bounds`), `binary_entropy`, `secure_key_rate` (GLLP asymptotic,
  q=0.5, `f_EC` from DetectorParams). **`secure_key_rate` is per-pulse** (secure bits per
  emitted signal pulse), clamped to `max(0,·)`.
- **Verification:** decoy `Y1_L`/`e1_U` are conservative bounds — checked via inequality,
  not equality. Tightening-limit anchor: `Y1_L → Y1_true` as ν → vacuum.

### 2B-4b — QND/PNS Eve (the hidden breach) + real key rate
**Files:** `src/qkd/eve.py`, `src/qkd/bb84.py`, `tests/test_eve.py`.

- `EveStrategy` base + `NullEve`, `InterceptResend`, `QND_PNS`. Eve acts on photon
  number; n=1 forwarded by a fraction solved from the target gain (raises ValueError if
  PNS can't match on a low-loss channel).
- **Signatures EMERGE:** QBER-invisibility from forwarded photons carrying only intrinsic
  error; the decoy anomaly from multi-photon favoritism distorting the gain ratio.
- **Verified thesis result:**
  `honest qber=0.0150 anomaly=0.000 skr=0.0197` ·
  `null qber=0.0150 anomaly≈0 skr=0.0197` ·
  `pns qber=0.0150 anomaly=0.966 skr=0.000` ·
  `ir qber=0.250 anomaly≈0 skr=0.000`.

### 2B-5 — Background light → effective werner_p
**Files:** `src/qkd/coherence.py` (new), `tests/test_coherence.py` (new).

- `effective_werner_p(...)`: `p_eff = p_source · S/(S+B)`, `S ∝ η_link`,
  `B = R_bg · R_local · Δt` (product of rates × window). B independent of link
  transmittance. Separate module — the 2B-2 guard holds untouched.
- **Honesty guard:** B=0 (night) → `p_eff = p_source` exactly, including the
  `S=0, B=0` edge. Daytime fidelity ARCHES under the current illustrative defaults
  (~0.571 peak → ~0.503 horizon, below 2/3 near horizon); night is flat at 0.99.
  PR1 wires this per-sample fidelity path through `mission.py` and into `run.py`; the
  default displayed pass uses `DEFAULT_SKY_CONDITION = "night"`, so it stays flat for a
  physical reason rather than as a drawn line.

### 2B-6a — Restore Single Authoritative Pipeline
**Files:** deleted `qkd_model.py` and root `results.json`; edited
`src/qkd/teleportation.py`, `src/qkd/channel.py`, `tests/test_teleportation.py`,
`tests/test_channel.py`; added `docs/architecture/ADR-0001-single-authoritative-pipeline.md`.

- Removed the original decorative simulator path: `qkd_model.py`,
  `TeleportationMission`, `build_teleportation_results`, and `fidelity_noise`.
- Removed the three tests that existed only to preserve those retired symbols.
- Removed the stale root `results.json` fallback artifact; **did not remove**
  `outputs/results.json`.
- Established the §4.0 invariant: exactly one authoritative production pipeline per
  generated artifact. For `outputs/results.json`, the sole writer is `src/qkd/run.py`.
- Preserved the decision and provenance in ADR-0001 rather than archiving executable
  decorative code.

### 2B-6b — Honest pass composition, born provenance-tagged
**Files:** `src/qkd/mission.py`, `src/qkd/provenance.py`, `src/qkd/run.py`,
`src/qkd/schema.py`, `src/qkd/coherence.py`, `src/qkd/channel.py`,
`docs/INTERFACES.md`, `tests/test_mission.py`, `tests/test_provenance.py`,
`tests/test_coherence.py`, `tests/test_schema.py`.

- `mission.py` is now the composition layer. It introduces no new physics and performs
  no I/O. `simulate_pass()` still works with zero arguments; `MissionConfig` is a small
  defaults bundle, not a configuration framework.
- Default illustrative constants live in `mission.py`: `PULSE_REPETITION_RATE_HZ =
  1.0e8`, `INTENSITIES = {"signal": 0.5, "decoy": 0.1, "vacuum": 0.0}`,
  `DEFAULT_N_PULSES = 1_000_000`, `DEFAULT_SKY_CONDITION = "night"`, and
  `DetectorParams(detection_efficiency=0.5, dark_count_prob=1.0e-6)`.
- Honest yield is now
  `secure_key_yield_bits = Σ secure_key_rate_per_pulse_i · f_rep · Δt_sample`. Under
  the current defaults, the dashboard headline is `1282.24 Kb`; this is an illustrative
  hardware-scaled yield, not a calibrated mission-performance claim.
- `werner_p_source` is treated as a single scalar channel/source constant across the
  pass; `mission._single_werner_source()` guards against accidental per-sample drift.
- `run.py` now only calls `simulate_pass()`, renders the plot, writes
  `outputs/results.json`, and prints the headline. Physics arithmetic moved into
  `mission.py`.
- The v1 schema recognizer remains active, but `remaining_entangled_resource_kb` is no
  longer required or emitted. This is a contained v1 evolution, not a v2.0 switchover.
- `run_metadata` is emitted deterministically:
  `{generator: "run.py", pipeline: "mission.simulate_pass", physics_mode: "computed"}`.
- `src/qkd/provenance.py` declares in-use tags (`ANALYTIC`, `SIMULATED`, `DERIVED`,
  `ILLUSTRATIVE`) and reserved tags (`MEASURED`, `ESTIMATED`, `VALIDATED`). At PR1 it
  emitted field-level tags for `summary`, `teleportation`, and pass-profile quantities,
  but did not enforce bidirectional coverage. PR2 now enforces structural coverage and
  tag validity; see 2B-6c below.
- Tests added: 10 mission/composition tests and 2 provenance tests. Guards include the
  yield integral, honest-zero yield, detector QE composed exactly once, day arch,
  night-flat B=0 control, v1 schema/dead-key removal, provenance completeness,
  `run.py` delegation, and unchanged `signals.py` dataclasses.

### 2B-6c — Provenance hardening
**Files:** `src/qkd/provenance.py`, `src/qkd/mission.py`, `src/qkd/run.py`,
`docs/INTERFACES.md`, `tests/test_provenance.py`, `tests/test_mission.py`,
`tests/test_schema.py`.

- `docs/INTERFACES.md` now states the Provenance Invariant: provenance observes; it
  never causes. Tags describe emitted values and must not select algorithms, alter
  numerical values, influence simulation state, or become physics inputs.
- `src/qkd/provenance.py` now provides `validate_provenance(emitted, provenance_map)`.
  It is a pure structural validator: no I/O, no mutation, no physics decisions.
- Validation scope is intentionally v1 data-only: `teleportation`, `summary`,
  `pass_profile`, and `mission`. Metadata blocks (`provenance`, `run_metadata`) are
  excluded.
- Taggable leaf rule: mappings recurse; any non-mapping value is a leaf. Arrays/lists/
  tuples are treated as single leaves, so whole pass arrays such as
  `pass_profile.loss_db` keep one provenance tag rather than per-index tags.
- The validator rejects missing tags, extra/phantom tags, unknown tags, and reserved
  tags (`MEASURED`, `ESTIMATED`, `VALIDATED`). It does **not** implement a full
  dependency graph or `depends_on_illustrative`; those remain deferred.
- `run.py` calls `validate_provenance(results, results["provenance"])` after composing
  the payload and before writing `outputs/results.json`.
- The emitted v1 payload now includes a `mission` section carrying the illustrative
  inputs that were already used by the composition layer:
  `pulse_repetition_rate_hz`, `intensities`, `detector`, and `sky_condition`.
- Mission provenance is leaf-level, not parent-container-level. Current mission leaves:
  `mission.pulse_repetition_rate_hz`, `mission.intensities.signal`,
  `mission.intensities.decoy`, `mission.intensities.vacuum`,
  `mission.detector.detection_efficiency`, `mission.detector.dark_count_prob`,
  `mission.detector.error_correction_efficiency`, and `mission.sky_condition`.
- Current emitted provenance has 28 data leaves: 4 `teleportation`, 2 `summary`,
  14 `pass_profile`, and 8 `mission`. Bidirectional coverage now holds: every emitted
  data leaf has a tag, and every tag points to an emitted data leaf.
- Tests added: 11 non-qiskit tests covering validator acceptance/non-mutation, the
  array-as-single-leaf rule, missing/extra/unknown/reserved failures, illustrative
  mission constants, exact `2/3` analytic classical bound, simulated arrays changing
  with pass geometry, derived-value recomputation, and provenance determinism.

### PR-Fibre-1 — Dedicated-fibre front-end contract validation
**Files:** `src/qkd/fibre.py`, `tests/test_fibre.py`, `docs/INTERFACES.md`.

- `src/qkd/fibre.py` is a second channel front-end, parallel to atmospheric
  `channel.py`, created to validate the `ChannelState.transmittance` representation
  contract. It introduces no downstream protocol changes.
- `DEFAULT_FIBRE` contains illustrative, representative parameters:
  `attenuation_db_km = 0.2`, `fixed_loss_db = 6.0`, `intrinsic_qber = 0.015`,
  `dark_count_prob = 1.0e-6`, and `werner_p = 0.98`. These are not calibrated
  deployment data.
- `fibre_transmittance(length_km, attenuation_db_km, fixed_loss_db)` computes
  `η = 10^(-(attenuation_db_km * length_km + fixed_loss_db) / 10)` and rejects
  negative lengths or losses before applying a defensive `[0, 1]` numerical clamp.
- `fibre_channel_state(length_km, fibre=None, *, eta_override=None, p_override=None)`
  emits a `ChannelState` with the computed fibre transmittance, source/resource
  `werner_p`, intrinsic QBER, and dark-count probability. The override paths set
  `transmittance` and `werner_p` exactly for valid values.
- Fibre `ChannelState` leaves `slant_range_km` and `elevation_deg` as `None`. Fibre
  length is not stuffed into orbital geometry fields.
- The existing `run_decoy_bb84`, coherence, and teleportation functions consume the
  fibre `ChannelState` unchanged. `bb84.py`, `coherence.py`, `teleportation.py`,
  `signals.py`, `mission.py`, `run.py`, and `schema.py` are untouched by this change.
- The model assumes dark/dedicated fibre. Raman scattering from classical DWDM
  co-propagation, PMD/birefringence depolarization, fibre length sweeps,
  `simulate_link`, schema changes, and emitted fibre artifacts are explicitly deferred.
- Tests added: 10 collected tests covering the standard fibre loss law at `0`, `10`,
  and `50 km`; monotonic bounded transmittance; invalid input rejection; geometry-free
  `ChannelState`; override parity; BB84 secure-key-rate ordering in a positive-SKR
  regime with a separate zero-floor assertion; exact dark-fibre
  `p_eff == p_source` to `1e-9`; and the same BB84 protocol accepting both atmospheric
  and fibre `ChannelState` inputs.

---

## 3. Module & contract inventory

`src/qkd/`: `teleportation.py`, `chsh.py`, `channel.py`, `orbit.py`, `bb84.py`,
`eve.py`, `coherence.py`, `fibre.py`, `signals.py` (dataclasses: `ChannelState`,
`DetectorParams`, `PhysicsSignals` — no trust field, by design), `mission.py`
(single pass-composition layer), `provenance.py` (observational field-origin tags plus
the v1 data/provenance structural validator), `run.py` (I/O and plotting only, with a
pre-write provenance validation call), and `schema.py` (v1/v2 recognizer; v1 no longer
requires `remaining_entangled_resource_kb`).

**Legacy decorative path — retired in PR0/2B-6a:**
- `qkd_model.py` (repo root) — second entry point; deleted in PR0.
- `teleportation.py::TeleportationMission`, `teleportation.py::build_teleportation_results`,
  `channel.py::fidelity_noise` — the decorative curve, countdown, and noise; removed in PR0.
- Legacy tests removed in PR0: `test_teleportation_mission_current_output_lengths`,
  `test_build_teleportation_results_current_schema`, `test_fidelity_noise_clamps_to_unit_interval`.
- Stale root `./results.json` (pre-nesting flat shape, no current writer) — `git rm` in PR0.
- The retirement is documented in `docs/architecture/ADR-0001-single-authoritative-pipeline.md`.

Docs: `docs/INTERFACES.md` (canonical contract), `docs/SCHEMA_HARDENING_2B.md`,
`docs/PHASE_2B4_DECOY_EVE.md`, `docs/PHASE_2B5_BACKGROUND_LIGHT.md`,
`docs/PHASE_2B6_SEQUENCE.md` (PR0/PR1/PR2 sequence/spec history), and
`docs/architecture/ADR-0001-single-authoritative-pipeline.md`.
Archive: `01-Gate-Noise-Archive/` (preserved Qiskit/QEC research — do not delete).

**Parameter honesty:** every illustrative parameter is documented as representative,
NOT calibrated. The simulator models correct *relationships and behaviours*, not the
absolute performance of any real link.

**Current output shape:** `outputs/results.json` remains v1-recognized and currently has
top-level `teleportation`, `summary`, `pass_profile`, `mission`, `provenance`, and
`run_metadata` sections. `teleportation` contains `frames`, `average_fidelity`,
`classical_limit`, and `plot`; it no longer contains `remaining_entangled_resource_kb`.
The `mission` section contains illustrative inputs (`pulse_repetition_rate_hz`,
`intensities`, `detector`, `sky_condition`) and is covered by leaf-level
`ILLUSTRATIVE` provenance. PR-Fibre-1 does not change `outputs/results.json`, `run.py`,
schema recognition, or dashboard-visible artifacts.

---

## 4. What's next (precise) — corrected sequence

Active sequence history/spec: `docs/PHASE_2B6_SEQUENCE.md`. Two-phase Codex gate per PR
(plan+approval, then implement+diffs+tests). Current state:

1. **PR0 / 2B-6a — Restore Single Authoritative Pipeline: complete.** The legacy
   decorative pipeline and stale root artifact are gone. ADR-0001 records the decision.
2. **PR1 / 2B-6b — Honest composition: complete.** `mission.simulate_pass` composes
   geometry→channel→decoy SKR→coherence p_eff→fidelity; yield is the pass integral;
   `run.py` is I/O only; the dead `remaining_entangled_resource_kb` key is dropped; v1
   output remains recognized; and deterministic `run_metadata` plus provenance tags are
   emitted.
3. **PR2 / 2B-6c — Provenance hardening: complete in the current repo.** The enum and
   emitted tags from PR1 are now enforced by `validate_provenance`. The validator covers
   v1 data leaves, rejects missing/extra/unknown/reserved tags, and is called by `run.py`
   before JSON emission. PR2 deliberately deferred dependency-graph metadata such as
   `depends_on_illustrative` and did not change physics values.
4. **PR-Fibre-1 — Fibre channel front-end contract validation: complete.** A static
   dedicated-fibre channel function now emits the same `ChannelState` contract as the
   atmospheric/orbital front-end. Existing BB84, coherence, and teleportation modules
   consume it unchanged. No length sweep, `simulate_link`, schema change, Raman model, or
   dashboard path is included.
5. **Next active technical milestone — schema hardening / v2 emission, if continuing the
   hardening track.** `docs/SCHEMA_HARDENING_2B.md` remains the guide for L2 types,
   L3 ranges, L4 constants, L5 consistency, and the eventual v2.0 output flip. Do this
   as its own PR; do not half-switch v1 and v2.
6. **Next fibre-track milestone — link composition / length sweep, if continuing the
   fibre path.** That later packet should introduce any `simulate_link` or emitted fibre
   artifact deliberately rather than expanding PR-Fibre-1 retroactively.

**Further out (updated):** Phase 2C broader mission orchestration grows from the
`simulate_pass` composition layer rather than inventing a second composition point.
Phase 2D trust/cognitive work reads `PhysicsSignals` and/or emitted physics outputs (the
wall holds — no trust field in physics). Coherence-enhancement optimization can operate
over filtering levers Δt/bandwidth/FOV vs. signal loss, with `f_rep` held fixed as
hardware. The applied target (Quantum City municipal-fibre proposal) reuses this verified
substrate by swapping the channel front-end; the CQN layer in that proposal maps onto
Phase 2D.

**Schema decision (standing):** v2.0 emission + L2–L5 validator hardening
(`SCHEMA_HARDENING_2B.md`) remains its own PR. PR1's drop of the single dead v1 key and
addition of `provenance`/`run_metadata`, plus PR2's additive `mission` section and
provenance validator, were v1-compatible, additive/contained changes, not the v2.0 flip.
Do not half-switch.

**If picking up fresh:** read this + `docs/INTERFACES.md` + `docs/PHASE_2B6_SEQUENCE.md`;
run the validation commands listed in §1; reconcile any module against the actual repo
file (not a remembered version) before editing; enumerate entry points / artifact writers
/ consumers first.

---

## Correction Log

- **2026-06-27 (Rev 5).** Reconciled the record for PR-Fibre-1, committed with this
  change (hash: pending). This revision adds the dedicated-fibre front-end as the first
  substitution test of the `ChannelState.transmittance` representation contract:
  `src/qkd/fibre.py` computes fibre loss, emits geometry-free `ChannelState` objects,
  and leaves downstream BB84/coherence/teleportation/signals/mission/run/schema modules
  unchanged. Current suite count from real validation: 104 passed with
  `--ignore=tests/test_teleportation_qiskit.py`; 125 passed with the qiskit extra
  available. Delta from Rev 4 is +10 collected tests. The Phase A plan described seven
  logical fibre tests; the actual delta is +10 because the negative-input test is
  parametrized across three inputs. Output shape remains v1 and unchanged by fibre.

- **2026-06-27 (Rev 4).** Reconciled the record after PR2 / 2B-6c provenance
  hardening. The previous Rev 3 statements that PR2 was "planned" or "next" are now
  superseded: `validate_provenance` exists, `run.py` calls it before writing JSON, the
  output includes the v1-compatible `mission` data section, and the former phantom
  `mission.*` provenance parents have been replaced with leaf-level tags. All three
  detector parameters (`detection_efficiency`, `dark_count_prob`,
  `error_correction_efficiency`) are emitted under `mission.detector` and tagged
  individually. The record now distinguishes PR2's implemented structural enforcement
  from still-deferred work: dependency-graph metadata such as
  `depends_on_illustrative`, v2.0 emission, and L2–L5 schema hardening. Current suite
  count: 94 base tests; 94 passed / 1 skipped without qiskit; 115 passed with qiskit.

- **2026-06-27 (Rev 3).** Updated the record after PR0 / 2B-6a and PR1 / 2B-6b
  completion. PR0 retired `qkd_model.py`, `TeleportationMission`,
  `build_teleportation_results`, `fidelity_noise`, the stale root `results.json`, and
  the three legacy tests, establishing the single-authoritative-pipeline invariant.
  PR1 added the honest pass composition layer in `mission.py`, reduced `run.py` to
  I/O/plotting, replaced the `5.00 Kb` placeholder with the secure-key-yield integral,
  dropped `remaining_entangled_resource_kb` from v1 required keys and emission, added
  deterministic `run_metadata`, introduced observational provenance tags, ratified the
  transmittance/f_rep ownership contracts in `INTERFACES.md`, and added 12 non-qiskit
  tests. Current suite count: 83 passed / 1 skipped without qiskit; 104 passed with
  qiskit. This revision also corrects the older shorthand that paired the Qiskit
  validation path with `qiskit-aer`: Aer may be locally installed from earlier
  experiments, but the implemented validation imports only `qiskit.quantum_info` APIs
  and the project declares only `qiskit` in the optional extra. At Rev 3, PR2 / 2B-6c
  remained planned for provenance hardening; that status is superseded by Rev 4.

- **2026-06-27 (Rev 2).** Corrected the §0 claim that the decorative fidelity curve and
  the resource countdown were "now gone or grounded." They were gone from `run.py` but
  live in `qkd_model.py` / `TeleportationMission` / `fidelity_noise`, which wrote the same
  `outputs/results.json` — a two-producer violation of the (now explicit) single-authoritative-
  pipeline invariant. Found by reconciling the planned 2B-6 work against repo HEAD.
  Corrected the test-count framing (74 base / 95 with qiskit; 71 / 92 post-PR0). Added the
  2B-6a/b/c sequence, the legacy-path inventory (§3), and the corrected next-steps (§4).
  No physics result was wrong; the error was in the execution-graph description.
