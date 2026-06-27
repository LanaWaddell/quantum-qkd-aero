# Quantum-QKD-Aero — Technical Development Record (Phase 2B)

> **REVISION 2 — corrected 2026-06-27.** This supersedes Revision 1. Revision 1
> contained a load-bearing error: it stated the original decorative quantities were
> "now gone or grounded." They were gone from the `run.py` pipeline but **still present
> and live in a second execution path** (`qkd_model.py` → `TeleportationMission` →
> `fidelity_noise`) that wrote the *same* `outputs/results.json`. This was found by
> reconciling the planned 2B-6 work against the actual repo files. The correction and
> its consequences are recorded in §0, §3, §4, and the Correction Log at the end. Treat
> this document as an architectural source: if it is wrong, downstream work inherits the
> error — which is exactly what nearly happened here.

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

**Correction (Rev 2):** these decorative quantities were removed *from the `run.py`
pipeline* during 2B-3, but were **not removed from the codebase.** They remained live
in the original prototype path — `qkd_model.py` (repo root) driving
`TeleportationMission.run_teleportation()` (the `0.85 + sin(f/50)*0.05` curve and the
`-= 0.01` countdown) via `build_teleportation_results`, calling `fidelity_noise` — and
that path **wrote the same `outputs/results.json` that `run.py` writes.** So there were
**two competing producers of one production artifact**, and "whichever ran last wins the
dashboard." This is the deeper issue: until exactly one authoritative pipeline writes
each artifact, the project cannot honestly claim "computed, not decorative," because two
different programs can generate the same output. These symbols date to the **initial
commit `2924673` (2026-04-06)** and predate the 2B refactor. They are retired in
**PR0 / Phase 2B-6a** ("Restore Single Authoritative Pipeline"), which establishes the
durable invariant: *exactly one authoritative production pipeline per artifact; any
historical/experimental pipeline must write separate outputs and never overwrite a
production artifact.*

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
| **2B-6a** | **Restore Single Authoritative Pipeline (retire legacy decorative path)** | **planned (PR0)** |
| **2B-6b** | **Honest pass composition (mission.py, yield integral, fidelity arch, run.py→I/O)** | **planned (PR1)** |
| **2B-6c** | **Provenance system (epistemic tagging, enforced)** | **planned (PR2)** |

**Test suite (corrected count):** at Rev-2 verification, **74 passed, 1 skipped**
without the qiskit extra; **95 passed** with it (74 base + 21 qiskit tests). Rev 1's
bare "95 passed" was the with-qiskit total, not a no-qiskit baseline. After PR0 removes
three legacy tests, the baseline becomes **71 / 92**.

`python src/qkd/run.py` prints `Min loss 27.7 dB | Fidelity 0.990` (verified). NOTE:
`qkd_model.py` prints a *different* decorative headline and overwrites the same JSON;
this is the two-producer condition PR0 resolves.

---

## 2. Phase-by-phase detail

*(Verified accurate at Rev-2 against the repo; retained from Rev 1.)*

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

- Third validation path: coherent teleportation circuit on a density-matrix simulator,
  Werner resource via a depolarizing channel with **λ = 1−p**, averaged fidelity via the
  Choi/entanglement-fidelity route (`F_avg = (2·F_e + 1)/3`). Deterministic; tests to 1e-9.
- The recipe was verified independently in numpy first; an intermediate test asserts the
  resource singlet fraction `(1+3p)/4`, guarding the λ=1−p mapping.
- Result: analytic = numeric = qiskit. (qiskit 2.4.x / qiskit-aer 0.17.x.)

### 2B-2 — Honest channel
**Files:** `src/qkd/channel.py` (extended), `tests/test_channel.py` (extended).

- `channel_state(...) → ChannelState`. **Transmittance η is COMPUTED:**
  `η = system_efficiency × T_atm × T_geo`, `T_atm = exp(−τ_zenith / sin(elevation))`,
  `T_geo = 1 − exp(−2a²/w²)` (`rx_aperture_m` is the **diameter**).
- **werner_p is SPECIFIED, not weather-derived.** Honesty guard: turbulence changes η
  but NOT werner_p.
- Parameters illustrative, not calibrated. η is realistically tiny (~1e-3 to 1e-4).
- **Contract note (Rev 2):** `ChannelState.transmittance` excludes receiver detector QE
  (owned by `DetectorParams.detection_efficiency`); both `run_decoy_bb84` and
  `coherence.signal_coincidence_rate` multiply the two. To be ratified explicitly in
  `INTERFACES.md` in PR1 (2B-6b) and guarded by a single-fold-scaling test.

### 2B-3 — Real satellite pass; sine curve dies (in run.py)
**Files:** `src/qkd/run.py` (rewritten), `src/qkd/orbit.py` (new), `tests/test_orbit.py` (new).

- `run.py` drives a satellite pass → per-sample `channel_state()` → η → loss in dB, with
  computed `teleportation_fidelity(werner_p)` as a flat reference. `fidelity_noise` is no
  longer called *by run.py*. **(Rev-2 correction: it is still called by `qkd_model.py`;
  see §0.)**
- Loss reported as positive-magnitude dB; "min loss" = closest approach.
- `results.json` keeps v1 schema keys valid and adds a `pass_profile` block.
- **Labeled placeholder retained:** `remaining_entangled_resource_kb` /
  `headline_key_yield` kept for v1-schema compatibility, marked `# TODO(2B-decoy)`. (Rev 2:
  retired in PR1 — the honest yield becomes an integral of per-pulse SKR over the pass.)

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
- **Verified thesis result (reproduced at Rev 2):**
  `honest qber=0.0150 anomaly=0.000 skr=0.0197` ·
  `null qber=0.0150 anomaly≈0 skr=0.0197` ·
  `pns qber=0.0150 anomaly=0.966 skr=0.000` ·
  `ir qber=0.250 anomaly≈0 skr=0.000`.

### 2B-5 — Background light → effective werner_p
**Files:** `src/qkd/coherence.py` (new), `tests/test_coherence.py` (new).

- `effective_werner_p(...)`: `p_eff = p_source · S/(S+B)`, `S ∝ η_link`,
  `B = R_bg · R_local · Δt` (product of rates × window). B independent of link
  transmittance. Separate module — the 2B-2 guard holds untouched.
- **Honesty guard:** B=0 (night) → `p_eff = p_source` exactly. Daytime fidelity ARCHES
  (~0.70 peak → ~0.51 horizon, below 2/3 near horizon); night flat at 0.99. (Rev 2:
  not yet wired into the displayed pass — that is PR1.)

---

## 3. Module & contract inventory

`src/qkd/`: `teleportation.py`, `chsh.py`, `channel.py`, `orbit.py`, `bb84.py`,
`eve.py`, `coherence.py`, `signals.py` (dataclasses: `ChannelState`,
`DetectorParams`, `PhysicsSignals` — no trust field, by design), `run.py`,
`schema.py`, `mission.py` (Phase-2A stub; becomes the composition layer in PR1).

**Legacy decorative path (Rev 2 — retired in PR0/2B-6a):**
- `qkd_model.py` (repo root) — second entry point; deleted in PR0.
- `teleportation.py::TeleportationMission`, `teleportation.py::build_teleportation_results`,
  `channel.py::fidelity_noise` — the decorative curve, countdown, and noise; removed in PR0.
- Legacy tests removed in PR0: `test_teleportation_mission_current_output_lengths`,
  `test_build_teleportation_results_current_schema`, `test_fidelity_noise_clamps_to_unit_interval`.
- Stale root `./results.json` (pre-nesting flat shape, no current writer) — `git rm` in PR0.
- The retirement is documented in `docs/architecture/ADR-0001-single-authoritative-pipeline.md`.

Docs: `docs/INTERFACES.md` (canonical contract), `docs/SCHEMA_HARDENING_2B.md`,
`docs/PHASE_2B4_DECOY_EVE.md`, `docs/PHASE_2B5_BACKGROUND_LIGHT.md`,
`docs/PHASE_2B6_SEQUENCE.md` (the active PR0→PR1→PR2 spec).
Archive: `01-Gate-Noise-Archive/` (preserved Qiskit/QEC research — do not delete).

**Parameter honesty:** every illustrative parameter is documented as representative,
NOT calibrated. The simulator models correct *relationships and behaviours*, not the
absolute performance of any real link.

---

## 4. What's next (precise) — corrected sequence

Active spec: `docs/PHASE_2B6_SEQUENCE.md`. Two-phase Codex gate per PR (plan+approval,
then implement+diffs+tests). Order:

1. **PR0 / 2B-6a — Restore Single Authoritative Pipeline.** Delete `qkd_model.py`,
   `TeleportationMission`, `build_teleportation_results`, `fidelity_noise`, the three
   legacy tests, and the stale root `results.json`; write ADR-0001. Establishes the
   one-producer-per-artifact invariant. No schema or `run.py` change. Expected suite:
   71 / 92.
2. **PR1 / 2B-6b — Honest composition.** `mission.simulate_pass` composes
   geometry→channel→decoy SKR→coherence p_eff→fidelity. Retire the `5.00 Kb` placeholder:
   honest yield = `Σ SKR_i · f_rep · Δt` (per-pulse rate integrated over the pass). Wire
   the daytime fidelity arch. Reduce `run.py` to I/O only. Drop the dead
   `remaining_entangled_resource_kb` key (contained v1 evolution, NOT the v2.0 flip). Add
   a minimal `run_metadata` producer stamp. Provenance co-designed from birth.
   **Blocking decisions:** transmittance contract (§2B-2 note) and `f_rep` value.
3. **PR2 / 2B-6c — Provenance system.** `Provenance` enum (ANALYTIC / SIMULATED / DERIVED
   / ILLUSTRATIVE in use; MEASURED / ESTIMATED / VALIDATED reserved), enforced:
   completeness, illustrative-honesty, reserved-non-use, and DERIVED-input transitive
   consistency. Optional seed: a computed `depends_on_illustrative` boolean (the honest
   seed of a future uncertainty dimension; full scale deferred to the optimization phase).

**Further out (unchanged):** Phase 2C mission orchestration (the composition seed grows
here); Phase 2D trust/cognitive layer reading `PhysicsSignals` (the wall holds — no trust
field in physics); coherence-enhancement optimization (maximize p_eff / key rate over
filtering levers Δt/bandwidth/FOV vs. signal loss). The applied target (Quantum City
municipal-fibre proposal) reuses this verified substrate by swapping the channel
front-end; the CQN layer in that proposal maps onto Phase 2D.

**Schema decision (standing):** v2.0 emission + L2–L5 validator hardening
(`SCHEMA_HARDENING_2B.md`) is its own PR. Dropping a single dead v1 key (PR1) is a
contained evolution, not the v2.0 flip. Do not half-switch.

**If picking up fresh:** read this + `docs/INTERFACES.md` + `docs/PHASE_2B6_SEQUENCE.md`;
run `pytest -v` to confirm the baseline; reconcile any module against the actual repo
file (not a remembered version) before editing; enumerate entry points / artifact
writers / consumers first.

---

## Correction Log

- **2026-06-27 (Rev 2).** Corrected the §0 claim that the decorative fidelity curve and
  the resource countdown were "now gone or grounded." They were gone from `run.py` but
  live in `qkd_model.py` / `TeleportationMission` / `fidelity_noise`, which wrote the same
  `outputs/results.json` — a two-producer violation of the (now explicit) single-authoritative-
  pipeline invariant. Found by reconciling the planned 2B-6 work against repo HEAD.
  Corrected the test-count framing (74 base / 95 with qiskit; 71 / 92 post-PR0). Added the
  2B-6a/b/c sequence, the legacy-path inventory (§3), and the corrected next-steps (§4).
  No physics result was wrong; the error was in the execution-graph description.
