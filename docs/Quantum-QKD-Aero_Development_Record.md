# Quantum-QKD-Aero — Technical Development Record (Phase 2B)

> **REVISION 19 — updated 2026-09-03 (RECOH-1 reference instrument).**
> The stored-state and analytic dephasing instrument is complete. This revision
> records its scope, calibration evidence, and remaining capability gates below.
> Historical revision summaries and superseded validation counts are retained
> in the dated Correction Log.

**Scope of this document:** a phase-by-phase record of the Phase 2B physics build —
what was implemented, how it was verified, the honesty guards in place, the file
and test inventory, current repo state, and the precise next steps. This is the
handoff artifact: a fresh session (a new Claude instance, or Codex) should be able
to read this plus `docs/INTERFACES.md` and `docs/PHASE_2B6_SEQUENCE.md` and pick up
exactly where the work stands.

Repo: `github.com/LanaWaddell/quantum-qkd-aero` · local: `Quantum-QKD-Aero/`
Working method (trial since 2026-08-10, **not yet standing practice**): top-tier Claude =
plan author, physics/architecture critic, independent verifier (cloud sandbox clone);
Sonnet subagent = implementation engineer against the approved plan *on trial* — Codex
(the implementer through Rev 12) remains the fallback, and the PI will choose after a
longer run with weekly usage limits as an explicit criterion; Echo = adversarial
pre-dispatch reviewer (Chat Claude consulted once, LINK-6a v2.1); Lana = PI (normative
decisions, local certification, commit/push). **All agent outputs are verified, not
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
coherence, teleportation fidelity, and provenance-enforced v2 emission without a second
writer. PR-Fibre-1 extended that discipline sideways: a fibre front-end computes the same
`ChannelState.transmittance` representation by a different physical model, and the
existing downstream physics stack consumes it unchanged. PR-A then factored that
downstream physics stack into a medium-neutral `simulate_profile(...)` core, so satellite
passes are one caller of the profile composition rather than the only place it exists.
PR-B then cut the emitted artifact over to the axis-agnostic v2 frame without changing
the physics values behind that artifact. PR-C adds the second caller: a dedicated-fibre
length sweep that feeds fibre `ChannelState` values through the same core and emits a
native v2 rate-distance artifact. PR-D hardens that artifact boundary: emitted v2 payloads
now fail fast on impossible values, mismatched array dimensions, undeclared schema keys,
dimensionally invalid aggregates, algebraic inconsistencies, or provenance drift.
ADR-0003 records the composable channel-physics layer downstream of ADR-0002's
medium/topology/protocol frame. LINK-1 through LINK-7 implement that lane: every
existing loss/detector constant became a fixed-ID production effect on a
stack that is evaluated on every call, new physics enters only as declared, typed,
bridge-rejected observables until an estimator explicitly consumes them, and the first
consumer (LINK-6a's QKD receiver model) does so through a declared control surface, a
canonical replay manifest, and an unchanged `bb84.py`; LINK-6b then consumes timing
jitter, Doppler offset, and misalignment. LINK-7 subsequently adds source-intensity
consumption through that receiver path and factors the base statistics with parity
checks. In parallel the TWIN lane built
the digital-twin diagnostic substrate (reference Kalman twin, calibrated whiteness/NIS,
private-probe watermark) whose central theorem — passive observation of an
exactly-law-matched replacement is blind, and the blindness is gain-independent — is
demonstrated as ensemble behaviour, not asserted. ADR-0004 now establishes the next
higher-layer boundary without modifying either substrate: adaptive decisions consume
adversarially shapeable channel evidence, while physical and cryptographic assurance
remain separate streams until an explicit policy layer combines them. FIXTURE-1 adds a
strictly non-production quasiperiodic stress surface; ADAPT-1 then implements the passive
D1 monitor over committed scalar references without coupling it to the live physics path.

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
| **2B-6c** | **Provenance hardening (enforcement, consistency, boundaries)** | ✅ committed |
| **PR-Fibre-1** | **Dedicated-fibre front-end contract validation** | ✅ committed in Rev 5 (d004c25) |
| **PR-A** | **Medium-neutral composition core (`simulate_profile`)** | ✅ committed; robust byte-identity guard corrected |
| **PR-B** | **v2 output schema cutover (`link` / `profile` / `geometry`)** | ✅ committed in Rev 8 (cadab78) |
| **PR-C** | **Fibre length sweep as second caller of `simulate_profile`** | ✅ committed in Rev 9 (6f0527d) |
| **PR-D** | **Deep schema validation and dimensional correction** | ✅ committed |
| **ADR-0003 / LINK-0** | **Composable link-effect pipeline architecture contract** | Ratified (2026-07-17) |
| **LINK-1** | Composable link-effect contracts, geometry wrapper, identity behaviour | ✅ `8b7ef46` (2026-08-10) |
| **LINK-2** | Loss/detector constants → fixed-ID production effects, byte-parity certified | ✅ `803f854` (2026-08-10) |
| **LINK-3** | Exact range-rate of the declared orbit; opt-in Doppler + pointing-bias hooks | ✅ `223d25c` (2026-08-10) |
| **LINK-4** | Seeded scintillation fading + pointing jitter; unit-mean declaration; stationary-law PDT surface | ✅ `4df5b7f` (2026-08-10) |
| **LINK-5** | Source partition + μ fluctuation, afterpulsing, dead time as typed bridge-rejected effects | ✅ `bdd73de` (2026-08-10) |
| **TWIN-1** | Reference Kalman twin + calibrated innovation diagnostic (whiteness + two-sided NIS) | ✅ `eeea12e` (2026-08-11) |
| **TWIN-2** | Private-probe watermark primitive; passive blindness gain-independent; relay blind by identity | ✅ `60ff5a1` (2026-08-11) |
| **LINK-6a** | QKD receiver model, gated detection, `gate_window_s` control, PDT consumption, replay manifest, benchmark contract | ✅ `2763c24` (2026-08-17) |
| **LINK-6b** | Timing-jitter gate acceptance, Doppler spectral-filter acceptance, misalignment consumption; manifest v2 + strict v1 replay; ADR-0003 §3.6 clarification | ✅ `e3815c0` (2026-08-18) |
| **LINK-7** | Source-intensity consumption, robust certified decoy inversion, manifest v3 | ✅ `f8c82f2` (2026-08-24) |
| **ADR-0004 / HYBRID-0** | Adaptive-coupling tier + hybrid QKD/PQC boundary; informative companion and staged implementation contract | ✅ ADR Accepted in `d7c9c33`; Stage 0 complete (2026-08-23) |
| **HYBRID-1** | Boundary state model: tier-4 attribution contracts, hybrid enums/dataclasses/validation, canonical serialization/digests, posture-registry snapshot | ✅ Stage 1 complete (2026-08-24) |
| **FIXTURE-1** | Non-production quasiperiodic misalignment stress fixture and bounded finite-range discrepancy note | ✅ `4c8d817` (2026-08-24) |
| **ADAPT-1** | Passive tier-4 attribution monitor over committed scalar references and synthetic traces | ✅ `8993d6c` (2026-08-24) |
| **MEM-0** | Standalone finite-key benchmark reconstruction | Implemented; benchmark acceptance unresolved |
| **RECOH-1** | Stored-state and analytic dephasing reference instrument | Complete (2026-09-03); not a rung-2 capability claim |

**Test suite (current Rev 19 local `qkd_env` validation, 2026-09-03):**
**991 passed** (`qkd_env/bin/python -m pytest -q`, 30.09 s);
**970 passed** with the Qiskit-specific file excluded
(`qkd_env/bin/python -m pytest -q --ignore=tests/test_teleportation_qiskit.py`,
29.72 s). Both configurations gained **25** tests over the verified
`215a876` baseline of **966/945**; the delta matches the plan. All additions
are in `tests/test_recoh1.py`; no existing test was edited. The environment
was Python 3.13.12, NumPy 2.4.6, pytest 9.0.3, and Qiskit 2.4.1.
The default artifact matches its same-environment pre-edit bytes; existing
in-process parity tests remain the portable oracle, not a cross-environment hash.

`python src/qkd/run.py` still prints `Min loss 27.7 dB | Fidelity 0.990` (verified).
`python src/qkd/run_fibre.py` prints
`Fibre Sweep Updated: Max secure distance 190.0 km | SKR@0 km 1.227e-02 bits/pulse`.

---

## 2. Phase-by-phase detail

*(Verified accurate at Rev 9 against the repo; earlier historical notes are retained
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
- At PR1, the v1 schema recognizer remained active while
  `remaining_entangled_resource_kb` was no longer required or emitted. That was a
  contained v1 evolution, not a v2.0 switchover. PR-B later retired v1 emission.
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
- Validation scope is intentionally v2 data-only: `link`, `teleportation`, `summary`,
  `profile`, `geometry`, and `mission`. Metadata blocks (`schema_version`,
  `provenance`, and `run_metadata`) are excluded.
- Taggable leaf rule: mappings recurse; any non-mapping value is a leaf. Arrays/lists/
  tuples are treated as single leaves, so whole pass arrays such as
  `profile.loss_db` keep one provenance tag rather than per-index tags.
- The validator rejects missing tags, extra/phantom tags, unknown tags, and reserved
  tags (`MEASURED`, `ESTIMATED`, `VALIDATED`). It does **not** implement a full
  dependency graph or `depends_on_illustrative`; those remain deferred.
- `run.py` calls `validate_provenance(results, results["provenance"])` after composing
  the payload and before writing `outputs/results.json`.
- The emitted payload includes a `mission` section carrying the illustrative
  inputs used by the composition layer:
  `pulse_repetition_rate_hz`, `intensities`, `detector`, and `sky_condition`.
- Mission provenance is leaf-level, not parent-container-level. Current mission leaves:
  `mission.pulse_repetition_rate_hz`, `mission.intensities.signal`,
  `mission.intensities.decoy`, `mission.intensities.vacuum`,
  `mission.detector.detection_efficiency`, `mission.detector.dark_count_prob`,
  `mission.detector.error_correction_efficiency`, and `mission.sky_condition`.
- Current emitted provenance has 32 data leaves: 3 `link`, 4 `teleportation`,
  2 `summary`, 11 `profile`, 4 `geometry`, and 8 `mission`. Bidirectional coverage
  now holds: every emitted data leaf has a tag, and every tag points to an emitted
  data leaf.
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

### PR-A — Medium-neutral composition core
**Files:** `src/qkd/mission.py`, `tests/test_profile.py`,
`tests/fixtures/pr_a_pre_refactor_satellite_output.json`.

- `mission.simulate_profile(axis_values, channel_states, ...) -> ProfileResult` is now
  the downstream composition core for already-resolved `ChannelState` sequences. It
  computes transmittance arrays, positive loss dB, decoy BB84 secure-key-rate arrays,
  background-light effective Werner p, teleportation fidelity, mean fidelity, and the
  secure-key-yield integral. It introduces no new physics and performs no I/O.
- `mission.simulate_pass()` remains the zero-argument satellite workflow. It still owns
  orbit geometry and atmospheric `channel_state(...)` construction, then delegates all
  downstream physics composition to `simulate_profile(...)`.
- The `ProfileResult -> PassResult` mapping is total: every profile-computed field in
  `PassResult` is copied from `ProfileResult`; geometry, mission inputs, and provenance
  are added only by the satellite wrapper. No profile quantity is recomputed in both
  places.
- The byte-identity reference fixture was captured from the actual pre-refactor git
  version (`git archive HEAD` at `ea50802`), not from a hand-reproduced parallel
  implementation. The robust guard now checks the production emission path by running
  `run.main()` into a temporary output directory and hashing the stable serialized
  emitted JSON contract. Raw pass arrays are compared separately with `1e-12` relative
  and absolute tolerance so genuine drift is still caught while last-ULP environment
  noise is absorbed.
- The verified production plot path remains `outputs/qkd_teleportation.png`; neither
  the pre-refactor `ea50802` run path nor the PR-A refactor emitted
  `outputs/qkd_pass.png`.
- `run.py`, `schema.py`, `channel.py`, `fibre.py`, `bb84.py`, `coherence.py`,
  `teleportation.py`, `orbit.py`, and `signals.py` are unchanged by PR-A. Output shape,
  provenance policy, dashboard behavior, and physics values remain unchanged.

### PR-B — v2 output schema cutover
**Files:** `src/qkd/run.py`, `src/qkd/schema.py`, `src/qkd/provenance.py`,
`src/qkd/mission.py`, `dashboard.js`, `docs/INTERFACES.md`,
`tests/test_schema.py`, `tests/test_profile.py`, `tests/test_provenance.py`,
`tests/test_mission.py`.

- `outputs/results.json` now emits `schema_version: "2.0"` and top-level
  `link`, `teleportation`, `summary`, `profile`, `geometry`, `mission`,
  `provenance`, and `run_metadata` sections.
- The link descriptor is explicit and medium-neutral:
  `{medium: "atmospheric", topology: "point_to_point", protocol: "decoy_bb84"}`.
- `pass_profile` is retired. Medium-neutral per-point arrays live under `profile`;
  satellite-only arrays live under `geometry`; aggregates live under
  `profile.aggregates`.
- The old pre-fibre `V2_REQUIRED_KEYS` stub in `schema.py` is retired. PR-B initially
  landed v2-only L1 shape recognition; PR-D later hardened the same current v2 artifact
  with L2-L5 checks and provenance wiring.
- The dashboard now reads `outputs/results.json` as v2 only. The stale root
  `results.json` fallback remains retired under the single-authoritative-pipeline
  invariant. The plot-image fallback remains only for the historical root PNG.
- Output parity is guarded by a map from every captured v1 leaf to exactly one v2
  location. New v2 leaves are explicitly enumerated. The production emission path
  hash changed because the schema shape changed; the underlying physics and headline
  values did not.

### PR-C — Fibre length sweep, second caller of the composition core
**Files:** `src/qkd/mission.py`, `src/qkd/run_fibre.py`,
`tests/test_fibre_sweep.py`, `docs/INTERFACES.md`, and this Development Record.

- `mission.simulate_fibre_sweep(...)` now builds
  `[fibre_channel_state(length_km) for length_km in lengths]` and feeds those
  geometry-free `ChannelState` objects into the unmodified `simulate_profile(...)`
  core with `axis_values = lengths_km`.
- The default grid is `0..220 km` in `5 km` steps. Under the current illustrative
  parameters, SKR is monotone decreasing, positive at `190 km`
  (`2.3793151827905804e-07` bits/pulse), and floored to `0.0` at `195 km`.
- `max_secure_distance_km` is intentionally the last positive-SKR sample (`190.0 km`),
  not the first zero sample. The emitted `secure_distance_bracket` records the
  last-positive and first-non-positive samples so the grid-resolution caveat is visible.
- Fibre uses `DEFAULT_SKY_CONDITION = "night"` because the model is a dark/dedicated
  fibre path with no sky background. `effective_werner_p` remains exactly the source
  `werner_p` (`0.98`) across the sweep.
- `src/qkd/run_fibre.py` is a separate artifact path. It writes
  `outputs/fibre_results.json` and `outputs/qkd_fibre_sweep.png`; it does not add modes
  to the satellite `run.py` path.
- Satellite emission remains pinned by the PR-B stable hash
  `bcac8a7024ccd114a0ef5288466ef8ab43f08964d61dada8d1cc7bdef28c8962`.

### PR-D — Deep schema validation and dimensional correction
**Files:** `src/qkd/schema.py`, `src/qkd/mission.py`, `src/qkd/run_fibre.py`,
`tests/test_schema.py`, `tests/test_fibre_sweep.py`, `docs/INTERFACES.md`,
`docs/PR_D_SCHEMA_HARDENING.md`, `docs/SCHEMA_HARDENING_2B.md`, and this
Development Record.

- `schema.py` is now a v2 L1 recognizer plus deep validator. By default,
  `validate_results_schema(...)` runs L1 structure, L2 finite type checks, L3 physical
  ranges and vocabulary, L4 stored constants, L5 artifact algebra, then
  `validate_provenance(...)`.
- `detect_results_schema(...)` remains recognition-only, and
  `validate_results_schema(..., deep=False)` / `load_results(..., deep=False)` preserve
  L1-only behavior for routing and recognition tests.
- `DECLARED_SCHEMA_EXTENSIONS: dict[str, set[str]]` is the extension mechanism:
  undeclared top-level sections and undeclared keys inside known sections fail. Declared
  extension leaves under provenance-covered data sections still require provenance tags.
- D1 dimensional correction is implemented: `secure_key_yield_bits` is required and
  L5-checked only for `time_s` artifacts. It is forbidden for `length_km` fibre sweeps.
  `simulate_fibre_sweep(...)` disables yield integration, `run_fibre.py` omits the field,
  and fibre provenance no longer carries a phantom yield tag.
- L5 validates the artifact relationships encoded by v2 emission: loss from
  transmittance, min-loss aggregates, mean fidelity, rounded average fidelity, temporal
  yield integral, satellite min-loss geometry, fibre secure-distance bracket, Werner
  fidelity under `physics_mode = "computed"`, and frame count.
- `docs/PR_D_SCHEMA_HARDENING.md` is the active schema-hardening spec for the current
  axis-agnostic v2 artifact. `docs/SCHEMA_HARDENING_2B.md` is preserved with a dated
  supersession note because its field-level details were for the older pre-fibre stub.


### LINK-1 → LINK-5 — the ADR-0003 queue implemented (2026-08-10)
**Plans:** `docs/LINK_1_PLAN.md` … `docs/LINK_5_PLAN.md` (each carries its Echo review
reconciliation and an implementation record). **Files:** `src/qkd/link.py` (contracts:
`ChannelEffect`/`GeometryProvider` Protocols, `LinkObservables` partition
channel/detector/source, `ChannelStack`, `EffectEvaluationContext`, `ControlSpec`/
`Controllable`, seeded child-RNG derivation, `apply_link_state` bridge, audit record),
`src/qkd/effects.py` (all built-in effects), `mission.py` (stack-always composition),
`tests/test_link.py`, `tests/test_effects.py`, `tests/test_link3_effects.py`,
`tests/test_link4_effects.py`, `tests/test_link5_effects.py`, `tests/test_orbit_velocity.py`.

- **LINK-1** — identity-only interfaces; `link_effects=None`/`[]` byte-identical; the
  bridge raises on any non-identity field it has no consumer for (the *estimator
  boundary*): new physics cannot silently leak into results.
- **LINK-2** — the four existing factors (`system_efficiency`, `atmospheric_absorption`,
  `geometric_loss`, `detector_qe`) migrated into fixed-ID production effects assembled
  on **every** call (no second code path); parity certified by an in-process oracle
  against an independent inline reference, plus a "no opt-in LINK features" language rule.
- **LINK-3** — exact analytic range-rate of the declared circular orbit (closed form with
  the sin γ cancellation, verified against central differences with a convergence check);
  first-order Doppler (`frequency_offset_hz`) and pointing-bias hooks emitted as
  bridge-rejected observables.
- **LINK-4** — seeded stochastic effects with order-independent per-effect child RNG streams
  (`SeedRequiredError` when a stochastic effect runs on an unseeded stack); scintillation
  fading (log-normal, weak-turbulence Rytov guard, unit-mean declaration partition-aware);
  pointing jitter; `stationary_law(geom)` exposed for the future PDT consumer.
- **LINK-5** — source partition (`intensity_factor` via `MuFluctuationEffect`),
  `DetectorAfterpulsingEffect(afterpulse_prob)`, `DetectorDeadTimeEffect(dead_time_s)` as
  typed, bridge-rejected observables; the epistemic boundary (physics/trust wall) made
  binding at the emission layer. Sonnet-subagent-caught detail: CPython `**`/`math.exp`
  raise `OverflowError` rather than returning `inf`, so overflow guards are explicit.

### TWIN-1 / TWIN-2 — digital-twin diagnostic substrate (2026-08-11)
**Plans:** `docs/TWIN_1_PLAN.md`, `docs/TWIN_2_PLAN.md`; normative sequencing in
`docs/notes/NOTE-sequencing-2026-08-10.md` (amended 2026-08-12: the Exp-1 gate split so a
*synthetic* Route-2 primitive is authorized while link instantiation stays Exp-1-gated;
TWIN-3 = finite-window power study registered). **Files:** `src/qkd/twin.py`,
`src/qkd/twin_watermark.py`, `tests/test_twin_whiteness.py`, `tests/test_twin_watermark.py`.

- **TWIN-1** — stateless batch Kalman filter (Joseph form) as the reference twin;
  scalar Ljung–Box on standardized innovations + two-sided NIS; frozen
  `DiagnosticCalibration` objects with precomputed χ² values (no SciPy); calibration
  proven as **ensemble behaviour** — the α-test rejects at ≈ α, with exact-binomial bands
  ([3, 19]/200 at α = 0.05) predeclared before seed pinning and fresh held-out review
  seeds. Echo's R1 replaced single-run "must not flag" assertions with this calibration.
- **TWIN-2** — private-probe (dynamic watermarking) primitive: probe/innovation
  cross-correlation detects *synthesis* and *replay* attacks; passive observation stays
  blind under exact law matching (`q_synth = q + g²σ_u²`), and the blindness is
  **gain-independent** — discovered during review, not planned; relay is blind by
  identity. Frozen-parameter honesty episode: the plan froze `g_modest = 0.1` with a
  ≥ 0.9 power floor that was unattainable (~0.80 with the 5-lag χ²₅ detector); the
  subagent refused to tune a frozen value and shipped a documented 0.6 floor; review
  corrected `g_modest → 0.15` (power 0.997) and restored the 0.9 floor.

### LINK-6a — Estimator integration I: QKD receiver model (2026-08-17)
**Plan:** `docs/LINK_6A_PLAN.md` v2.3.1 with §14 implementation record; reviews
`docs/LINK_6A_REVIEW.md`, `_V2_`, `_V21_`, `_V22_`, `_V23_`, `_V231_REVIEW.md` (Echo, six
cycles; Chat Claude reviewed v2.1). **Created:** `src/qkd/detection.py`, `src/qkd/replay.py`,
`src/qkd/benchmark.py`, `tests/test_detection.py`, `tests/test_link6a.py`,
`tests/test_replay.py`. **Modified:** `effects.py` (+`BackgroundLightEffect`,
`DetectorDarkRateEffect`), `mission.py`, `run.py`, `schema.py`, and — flagged, PI-accepted —
`tests/fixtures/pr_a_pre_refactor_satellite_output.json` (two `null` keys, because an
existing test compares `asdict(PassResult)` key sets and the approved trailing optional
fields extend it; values `None`; no emitted default-path field changed; no `.py` test edited).
`bb84.py`, `link.py` untouched.

- **Receiver physics (frozen after review):** shared-history mean-field afterpulse model
  across interleaved intensities (`Q̄ = Σπ_x Q_x`, `Q̄_reg = Q̄/(1−p_ap(1−Q̄))`,
  `a = p_ap Q̄_reg`, `Q'_x = 1−(1−Q_x)(1−a)`, `T'_x = T_x + ½(1−Q_x)a`), calibrated
  `(p_ap, τ_d)` operating pair, **one common** non-paralyzable availability
  `A = 1/(1+R_click τ_d)` with `R_click = f_rep·Q̄_reg` exactly (decoy homogeneity:
  `Y1_L(AQ) = A·Y1_L(Q)`, `e1_U` invariant — tested to 1e-16); gated noise
  `p_noise = 1−(1−y0)(1−p_bg)(1−p_dk)` entering the unchanged estimator through the
  `y0` slot by calling the public `run_decoy_bb84` on a detector copy (both certified base
  laws inherited); post-afterpulse `Q'_vacuum` — never raw `p_noise` — is the estimator's
  vacuum yield. Precomputed anchor `A = 0.918124082928941429…` (a v2.1 transcription
  error was caught by both reviewers) asserted to ≥ 12 digits.
- **Contract layer:** `simulate_pass(..., receiver=None, link_mode="sampled", pdt_config=None)`
  — explicit activation only; `gate_window_s` is the first *production* declared control
  (union registry built at mission level, owner-partitioned, required-when-consumed, no silent
  default); canonical `profile.secure_key_rate_per_pulse` stays the delivered per-protocol-
  pulse rate so the L5 yield law holds unmodified; `profile.link_receiver` diagnostic subtree
  and `run_metadata.link_provenance` canonical-JSON replay manifest as the only two new
  `DECLARED_SCHEMA_EXTENSIONS`, both absent on the default path; closed-world
  `replay_from_provenance` through the real simulation path (byte-identical round-trip
  in-process, sampled and PDT); `audit_spec()` protocol for unregistered custom effects.
- **PDT mode:** closed-world `PDT_ADMISSIBLE_EFFECTS` allowlist by `effect_id`; exactly one
  law effect (`scintillation_fading`) which must be **last** and is never `evaluate()`d —
  the deterministic prefix is built with `seed=None` so `SeedRequiredError` traps any RNG
  request; 21-node Gauss–Hermite with 41-node convergence; unbounded log-normal with tail/
  node validity guards (never clip); `PdtConfig` with `τ_mem = τ_d + 1/f_rep` memory guard,
  stationarity guard, and `block_duration_s` bound to the actual uniform profile grid;
  observed-statistics ratios `Q̂ = E[A·Q']/E[A]` (conditional-then-average, convex-mixture
  justification recorded). PDT vs a sampled ensemble agrees to 3e-4 in the small-σ regime and
  diverges by design under strong nonlinearity (`R(E_w[Q'])` vs `E_f[R]`).
- **Decisions of record:** receiver and Eve are mutually exclusive in 6a (a later PR must
  promote one canonical public anomaly helper or reuse the public Eve pipeline — never a
  third formula); `benchmark.py` is contract-complete (artifact schema, validator,
  calibrated-pair sweep refusal, model-derived crossing) with no sweep driver until the
  first advantage claim is made.
- **Verification-driven fixes before merge:** the subagent's "exact" identity clauses were
  softened (`1−(1−y0)` rounding at the live `y0 = 1e-6`; `approx(abs=1e-12)` tests) — now
  exact short-circuits with strict `==`; missing `SeedRequiredError` trap and PDT-vs-sampled
  ensemble tests added; per-sample dead-time/afterpulse invariance guard; boundary and A.5
  validator-matrix tests completed. Final: 562/541, emission hash unchanged.

---

### MEM-0 / RECOH-1 — separate reference instruments

MEM-0 remains a standalone finite-key benchmark reconstruction, not a passed
replication. Its source-backed inherited error-correction factor is `f_e = 1.16`;
the 2-QM cutoff/threshold anchors agree within predeclared tolerances, but absolute
magnitudes remain low by approximately 3.5× and the 1-QM count path remains
unresolved. The author query and factor ledger are preserved in
`docs/benchmarks/BENCH-mem0-gundogan.md`. RECOH-1 neither imports this module
nor claims to resolve those benchmark discrepancies.

RECOH-1 calibrates an explicit stored qubit against ideal, Lindblad, and Gaussian
white/OU pure-dephasing reference maps. The white kernel calls Lindblad directly.
For OU, `D_phi = sigma² * tau_c` is held fixed in the white-noise limit;
`kappa = exp[-D_phi * tau_c * g(t/tau_c)]`, with the approved stable
`expm1`/short-time-series evaluation of `g`. Negative physical coherence
factors are allowed in `dephase`, while the diagnostic, unnormalized Choi
constructor also accepts finite nonphysical factors so CPTP checks can reject
them. Choi trace is 2 and the output partial trace is the identity.

`RecoveryClass` is a **derived output**, not a configured capability. A recovery
label requires loss followed by a qualifying revival; endpoint improvement alone
is protection. Backflow is discrete positive variation for a **preselected**
state pair, not the maximized BLP measure, and cannot detect unsampled revivals.
All supplied free-evolution models yield `NONE`; positive classifier self-checks
use explicitly synthetic curves. The calibration suite covers density-matrix/Choi
validity, white/short/long-time limits, stable OU evaluation, monotonicity,
witnesses, classifier priority, invalid inputs, import/RNG isolation, emission
parity, and negative-factor composition.

Configuration vocabulary is **provisional** pending the memory SPEC amendment;
reconciliation is a RECOH-2 obligation. No control sequence, nonmonotone physical
model, stochastic trajectory, retrieval efficiency, production coupling, or
schema extension is introduced.

---

## 3. Module & contract inventory

`src/qkd/`: `teleportation.py`, `chsh.py`, `channel.py`, `orbit.py`, `bb84.py`,
`eve.py`, `coherence.py`, `fibre.py`, `signals.py` (dataclasses: `ChannelState`,
`DetectorParams`, `PhysicsSignals` — no trust field, by design), `mission.py`
(medium-neutral profile-composition core plus satellite pass wrapper and fibre sweep
wrapper), `provenance.py`
(observational field-origin tags plus the v2 data/provenance structural validator),
`run.py` (satellite I/O and plotting only, with pre-write schema/provenance validation),
`run_fibre.py` (fibre-sweep I/O and plotting only, with pre-write schema/provenance
validation), and `schema.py` (v2-only L1 recognizer plus L2-L5 deep validator; the old
orbital `V2_REQUIRED_KEYS` stub is retired). `canonical.py` is the schema-neutral canonical
dataclass-envelope mechanism; semantic schema identity remains at each caller. **LINK/TWIN
additions (Revs 13–16):** `link.py` (ADR-0003
contracts, `ChannelStack`, seeded child RNG, `apply_link_state` bridge, control registry,
audit record — untouched since LINK-5), `effects.py` (seventeen built-in production and
opt-in effects through LINK-7), `detection.py` (QKD receiver model, gated detection,
timing/filter/misalignment/source folds, PDT admission/quadrature/guards), `replay.py`
(`replay_from_provenance`, `LINK_PIPELINE_VERSION = "link-7.1"`, strict manifest v1/v2/v3
support, seventeen effect codecs), `benchmark.py` (artifact
contract + validator), `twin.py` (reference Kalman twin + calibrated diagnostics),
`twin_watermark.py` (private-probe primitive). `mission.py` composes the stack on every
call and owns the union control registry. `DECLARED_SCHEMA_EXTENSIONS` now holds exactly
`profile → link_receiver` and `run_metadata → link_provenance`.

**Adaptive/HYBRID additions (Revs 15–17):** `adaptive/contracts.py` remains the stdlib-only
tier-4 evidence vocabulary. `adaptive/observables.py`, `references.py`, `traces.py`, and
`monitor.py` implement ADAPT-1's closed observable registry, digest-bound scalar reference,
exact-cadence synthetic trace contract/generators, and passive TWIN-backed monitor.
`hybrid/serialization.py` is now a thin `hybrid-1.0` wrapper over `canonical.py`; all
pre-extraction HYBRID bytes and digests remain fixture-pinned. `fixtures/quasiperiodic.py`
is FIXTURE-1's non-production stress fixture and is neither production-wired nor PDT-admitted.

**Standalone reference instruments (Revs 18–19):** `mem0_gundogan.py` is the finite-key
benchmark reconstruction. `mem_state.py` adds frozen `StoredQubit`, `PLUS`/`MINUS`,
density/Choi/CPTP helpers, `dephase`, and the three `kappa_*` functions.
`recoh.py` adds L1 coherence, pure-target fidelity, trace distance, preselected-pair
backflow, recovery fraction, and derived classification. Its sole local dependency is
`qkd.mem_state`; both new modules otherwise use only stdlib and NumPy.
`tests/test_recoh1.py` is the associated calibration suite. None is wired into
production composition or an artifact writer.

**Legacy decorative path — retired in PR0/2B-6a:**
- `qkd_model.py` (repo root) — second entry point; deleted in PR0.
- `teleportation.py::TeleportationMission`, `teleportation.py::build_teleportation_results`,
  `channel.py::fidelity_noise` — the decorative curve, countdown, and noise; removed in PR0.
- Legacy tests removed in PR0: `test_teleportation_mission_current_output_lengths`,
  `test_build_teleportation_results_current_schema`, `test_fidelity_noise_clamps_to_unit_interval`.
- Stale root `./results.json` (pre-nesting flat shape, no current writer) — `git rm` in PR0.
- The retirement is documented in `docs/architecture/ADR-0001-single-authoritative-pipeline.md`.

Docs (Revs 13–17 additions): `docs/LINK_1_PLAN.md`…`LINK_5_PLAN.md`,
`docs/LINK_6A_PLAN.md` (+ six `LINK_6A_*REVIEW.md`), `docs/LINK_6B_PLAN.md`
(+ its review records), `docs/TWIN_1_PLAN.md`, `docs/TWIN_2_PLAN.md`,
`docs/notes/NOTE-sequencing-2026-08-10.md` (normative lane sequencing),
the Kalman note (v2.1, project KB — not in repo). Some working notes are held in a
gitignored private directory and are never pushed; the ignore rule itself is public
(`5b530ca`). Their contents do not bear on the physics substrate, the emission path, or
any ratified architecture decision in this record.
Docs: `docs/INTERFACES.md` (canonical v2 contract),
`docs/architecture/ADR-0002-three-axis-quantum-link-model.md` (three-axis link frame),
`docs/architecture/ADR-0003-composable-link-effect-pipeline.md` (ratified LINK contract),
`docs/architecture/ADR-0004-adaptive-coupling-and-hybrid-crypto-boundary.md` (Accepted
adaptive-coupling and hybrid-boundary decision),
`docs/architecture/pqc_hybrid_architecture.md` (informative ADR-0004 companion),
`docs/HYBRID_0_PLAN.md` (provenance-preserving Stage 0 execution record),
`docs/ADAPT_1_PLAN.md` (v1.4.1 authorized execution packet),
`docs/RECOH_1_PLAN.md` (v1.1 approved instrument contract and review provenance),
`docs/benchmarks/BENCH-mem0-gundogan.md` (unresolved reconstruction claims register),
`docs/notes/DN-quasiperiodic-misalignment.md` (FIXTURE-1 design note),
`docs/architecture/quantum-qkd-aero-architecture-map.md` (architecture/status map),
`docs/PR_D_SCHEMA_HARDENING.md` (active deep-validator contract),
`docs/SCHEMA_HARDENING_2B.md` (historical pre-fibre hardening spec),
`docs/PHASE_2B4_DECOY_EVE.md`, `docs/PHASE_2B5_BACKGROUND_LIGHT.md`,
`docs/PHASE_2B6_SEQUENCE.md` (PR0/PR1/PR2 sequence/spec history), and
`docs/architecture/ADR-0001-single-authoritative-pipeline.md`.
Archive: `01-Gate-Noise-Archive/` (preserved Qiskit/QEC research — do not delete).

**Parameter honesty:** every illustrative parameter is documented as representative,
NOT calibrated. The simulator models correct *relationships and behaviours*, not the
absolute performance of any real link.

**Current output shape:** `outputs/results.json` is v2 and currently has top-level
`schema_version`, `link`, `teleportation`, `summary`, `profile`, `geometry`,
`mission`, `provenance`, and `run_metadata` sections. `teleportation` contains
`frames`, `average_fidelity`, `classical_limit`, and `plot`; it does not contain
`remaining_entangled_resource_kb`. `profile.axis` names the independent axis
(`time_s` for satellite passes), profile arrays hold medium-neutral quantities,
`profile.aggregates` holds derived summary values including the temporal
`secure_key_yield_bits` integral, and `geometry` holds satellite-only
elevation/slant-range data. The `mission` section contains illustrative inputs
(`pulse_repetition_rate_hz`, `intensities`, `detector`, `sky_condition`) and is covered
by leaf-level `ILLUSTRATIVE` provenance.

**Current fibre output shape:** `outputs/fibre_results.json` is also v2. It has
`schema_version`, `link`, `teleportation`, `summary`, `profile`, `mission`,
`provenance`, and `run_metadata`, but intentionally omits `geometry`. Its profile axis
is `length_km`, and its fibre-specific aggregate
`profile.aggregates.max_secure_distance_km` is accompanied by
`profile.aggregates.secure_distance_bracket`. It intentionally omits
`profile.aggregates.secure_key_yield_bits`; a length-axis integral is not a bit yield.

---

## 4. What's next (precise) — corrected sequence

Active sequence history/spec: `docs/PHASE_2B6_SEQUENCE.md`. Two-phase Codex gate per PR
(plan+approval, then implement+diffs+tests). Current state:

1. **PR0 / 2B-6a — Restore Single Authoritative Pipeline: complete.** The legacy
   decorative pipeline and stale root artifact are gone. ADR-0001 records the decision.
2. **PR1 / 2B-6b — Honest composition: complete.** `mission.simulate_pass` composes
   geometry→channel→decoy SKR→coherence p_eff→fidelity; yield is the pass integral;
   `run.py` is I/O only; the dead `remaining_entangled_resource_kb` key is dropped; and
   deterministic `run_metadata` plus provenance tags are emitted. At PR1 this remained
   a v1-compatible output evolution; PR-B supersedes it with v2 emission.
3. **PR2 / 2B-6c — Provenance hardening: complete in the current repo.** The enum and
   emitted tags from PR1 are enforced by `validate_provenance`. The validator rejects
   missing/extra/unknown/reserved tags and is called by `run.py` before JSON emission.
   It originally covered v1 data leaves; PR-B migrated the same enforcement to the v2
   `link` / `profile` / `geometry` shape. PR2 deliberately deferred dependency-graph
   metadata such as `depends_on_illustrative` and did not change physics values.
4. **PR-Fibre-1 — Fibre channel front-end contract validation: complete.** A static
   dedicated-fibre channel function now emits the same `ChannelState` contract as the
   atmospheric/orbital front-end. Existing BB84, coherence, and teleportation modules
   consume it unchanged. No length sweep, `simulate_link`, schema change, Raman model, or
   dashboard path is included.
5. **PR-A — Medium-neutral composition core: complete.** The downstream composition
   stack is now factored into `mission.simulate_profile(...)`, while
   `mission.simulate_pass()` remains the satellite caller. Satellite output is
   guarded against the captured pre-refactor fixture through a production-path emitted
   JSON hash plus tolerant raw-array comparison; no schema, dashboard, run.py, or physics
   behavior changed.
6. **PR-B — v2 output schema cutover: complete.** `outputs/results.json` now emits the
   ADR-0002-aligned v2 frame with `link`, axis-agnostic `profile`, satellite
   `geometry`, and v2 provenance coverage. v1 and the old orbital v2 stub are retired.
7. **PR-C — Fibre length sweep: complete.** `simulate_fibre_sweep` is the second caller
   of `simulate_profile`; `run_fibre.py` emits the v2 fibre artifact; the secure
   rate-distance curve and max-secure-distance bracket are tested.
8. **PR-D — Deep schema validation and dimensional correction: complete.** The active
   v2 schema validator now enforces L2-L5, declared-extension vocabulary, provenance
   coverage, and the axis-conditional `secure_key_yield_bits` rule.
9. **ADR-0003 / LINK-0 — ratified (2026-07-17)**, and **LINK-1 → LINK-7 implemented
   (2026-08-10 → 08-24)** — see §2 and the Correction Log. The receiver consumes
   detector-side observables plus timing jitter, Doppler offset, misalignment, and source
   `intensity_factor`; the residual bridge rejects nothing non-identity.
10. **TWIN-1 / TWIN-2 complete (2026-08-11)** — synthetic Route-2 primitive authorized by the
   amended sequencing note; link instantiation of Route 2 stays **Exp-1-gated**.
11. **ADR-0004 / HYBRID-0 Stage 0 — complete (2026-08-23).** ADR-0004 r3 is Accepted;
   its v3.1 companion is informative. This stage adds architecture and implementation
   contracts only: no schemas, policy engine, registry, KDF adapter, or PQC integration.
12. **HYBRID-1 Stage 1 — complete (2026-08-24).** The boundary state model: tier-4-owned
   `AttributionVerdict` / `DegradationAttributionEvidence` at
   `src/qkd/adaptive/contracts.py` (D-H1-2, stdlib-only); the companion's exhaustive Stage 1
   contract set (twelve dataclasses plus nine enums) at `src/qkd/hybrid/states.py`;
   canonical envelope serialization and SHA-256 digests at `src/qkd/hybrid/serialization.py`
   (D-H1-3: `{"record_type", "schema_version", "payload"}` envelope, sorted-key/
   `ensure_ascii`/no-whitespace-variance encoding, exact `YYYY-MM-DDTHH:MM:SS.ffffffZ`
   timestamp grammar, byte-exact loader round-trip guard); and the D3-pattern
   `AlgorithmPostureRegistry` / digest-free `RegistrySnapshot` (digest is a computed
   property, never a stored field, per C8) at `src/qkd/hybrid/registry.py`. No policy
   engine, no KDF/cryptographic derivation, no authentication integration, no physics
   coupling. `AssuranceDecision.policy_profile` is a recorded deviation from the companion
   v3.1 schema listing (Echo blocker 1); HYBRID-1 reconciled the companion to v3.2
   (schema-listing addition + revision-log entry, nothing else). 199 new tests
   across `tests/test_hybrid_states.py`, `tests/test_hybrid_registry.py`, and
   `tests/test_hybrid_serialization.py`; zero regressions.
13. **FIXTURE-1 — complete (2026-08-24).** A non-production quasiperiodic misalignment
   fixture and 24-test stress program are preserved under `qkd.fixtures`; the fixture is
   absent from production composition and the PDT allowlist. Its design note limits
   discrepancy claims to the declared finite range and bounded-type structure.
14. **ADAPT-1 — complete (2026-08-24); independently certified in Rev 17.1.** The passive
   tier-4 monitor evaluates exact-length synthetic scalar traces against digest-bound
   committed references using TWIN-1 whiteness/NIS components. It records both component
   outcomes, applies the declared conservative operational OR mapping, and never emits
   `ADVERSARIAL_SUSPECTED`. Canonical serialization was extracted to `qkd.canonical`; the
   HYBRID wrapper and all frozen HYBRID fixture bytes/digests remain unchanged.

**Memory/recoherence gate state:** ADR-0003 §6 rung-2 remains **planned**.
Gate A (Echo MEM-basis review) remains **open**; Gate B0 is **YES**
(PI, 2026-09-03). RECOH-2 requires reconciliation of the provisional vocabulary
to the memory SPEC and separate authorization for control sequences; RECOH-3
nonmonotone physical models remain future work. MEM-0's unresolved benchmark
anchors remain a separate follow-up, not satisfied by instrument calibration.

**Open lanes (not yet sequenced; a sequencing decision is the next PI call):**
- **Receiver-aware Eve** — through the LINK-6a R6 path; one canonical anomaly helper.
- **LINK-6c candidate** — couple filter bandwidth honestly to background spectral
  radiance/rate density and FOV signal cost before any advantage benchmark.
- **Benchmark sweep driver** — `outputs/benchmark_*.json` producer, tied to the first real
  advantage claim (the QCC mapping memo / chosen advantage parameter).
- **HYBRID Stage 2** — the policy engine: deterministic evaluation from evidence bundles
  consuming Stage 1's boundary state model and registry snapshot interface; exhaustive
  policy matrix tests; audit-event generation. No cryptographic derivation yet.
- **ADAPT-2** — active private-probe/watermark attribution; the passive ADAPT-1 monitor's
  `ADVERSARIAL_SUSPECTED` prohibition remains until that evidence basis is implemented.
- **TWIN-3** — finite-window power study (registered in the sequencing note).
- **QCC proposal skeleton** — Project Overview / Scientific & Technical Approach /
  Performance Analysis & Benchmarking / Supporting Documentation, per the technical package;
  route-to-demonstration required; strategy note is private.
- **Exp 3B / Route-2 link instantiation** — Exp-1-gated.

**Further out (unchanged in physics scope):** Phase 2C orchestration grows from
`simulate_pass`; Phase 2D trust/cognitive work reads `PhysicsSignals`/emitted outputs
(the wall holds — no trust field in physics; ADR-0002/ADR-0003 boundary remains enforced
at emission); coherence-enhancement optimization over Δt/bandwidth/FOV; HYBRID Stages
2–6 proceed only through the explicit policy/assurance boundary in ADR-0004.

**Schema decision (standing):** v2.0 emission and L2-L5 validator hardening are now
complete for the current axis-agnostic artifact. Future schema expansion should use
`DECLARED_SCHEMA_EXTENSIONS` deliberately and update `docs/PR_D_SCHEMA_HARDENING.md`
with the new contract rather than silently accepting extras.

**If picking up fresh:** read this + `docs/INTERFACES.md` + ADR-0003 + ADR-0004 and its
informative companion + `docs/notes/NOTE-sequencing-2026-08-10.md` + the latest
`LINK_*`/`TWIN_*`/HYBRID plan record; run the validation commands listed in §1 and name
the environment; reconcile any module against the actual repo file (not a remembered
version) before editing; enumerate entry points / artifact writers / consumers first.

---

## Correction Log

- **2026-09-03 (Rev 19.2, SPEC ratification companion, Claude).** The memory-arm
  degradation SPEC (`docs/architecture/SPEC-memory-lifetime-adr0003.md`) is
  **ratified** (PI, two-commit protocol: ratification commit carries the SPEC
  only; this entry is the companion). Gate A — Echo's adversarial review of the
  DN/SPEC/RN MEM basis, the outstanding gate registered since 2026-08-26 — is
  **closed** (review SHA-256 `ab1f7ba16b8775d2080c7a71ee3be3a38fcec96aa7359fe2742b618d58aca5c4`;
  v0.3 reconciliation + v0.3.1 fix; Echo confirmation). Surface of record: three
  independent degradation axes (`dephasing_model: identity_state_evolution |
  lindblad_phase_damping | gaussian_frequency_noise`; `memory_error_model:
  constant | derived_from_state`; `retrieval_decay_model`), two immutable
  source-backed benchmark profiles (`gundogan-2024-2QM`, `paterson-2026-fidelity`),
  parameters separated from event realizations, deterministic-ensemble-map vs
  seeded-trajectory rule stated. `ideal` renamed `identity_state_evolution` at
  ratification (PI); RECOH-1's `kappa_ideal` function name is unchanged and the
  mapping is recorded in the RECOH-2 docstring pass, which also discharges the
  "provisional" marking on `dephasing_model`, `noise_kernel`, `D_phi`, `tau_c`.
  Corrected on the way in: v0.1/v0.2's statement that fidelity is bounded above
  by coherence (false: `F = (1+C)/2 > C`). Scheduling-policy exclusion recorded
  in SPEC §4. **Process decision (PI):** the separate-session fresh-eyes rule is
  tiered — required for ADRs and ADR amendments; for SPECs and plans a genuine
  break between review and ratification suffices. ADR-0003 Amendment A1
  (rung-2 placement) remains a provisional draft and now enters its dedicated
  two-round review under the ADR tier. Rung-2 capability status unchanged
  (**planned**). Suite unchanged (docs only): 970 / 991.

- **2026-09-03 (Rev 19.1, post-push certification, Claude).** Verified on a fresh
  public clone at `48ed81feaec92dfc72a6ca622610b3e740ee0768` (RECOH-1, packet
  rev 2, base `215a876`): **970 passed** with
  `--ignore=tests/test_teleportation_qiskit.py`; **991 passed** with the Qiskit
  extra (qiskit 2.5.2 / qiskit-aer 0.17.2); **+25 / +25** from Rev 18's
  945 / 966, matching the packet. `python src/qkd/run.py` →
  `Min loss 27.7 dB | Fidelity 0.990`. Default emission SHA-256 in the
  certifying environment `8c7cef94c756ce054ef120fdb18854788c9d040825fb66422d29e1a6ace9a6d5`,
  **identical** to the same environment's Rev 18.1 measurement (byte identity
  is environment-local; the implementer's local hash `1047ed1d…1bc4` was
  likewise unchanged before/after). Exactly five files changed; import hygiene
  holds; `choi_dephasing`/`dephase` validation split, R1 white-kernel identity,
  OU monotonicity, zero backflow on free evolution, `NONE` classification, and
  `recovery_fraction` failure behaviour exercised directly. Record deletions
  audited: superseded Rev 15–18 headers and the Rev 17 suite paragraph moved
  verbatim to the archived-snapshots block; no correction entry removed.
  **RECOH-1 = `48ed81f`.** Rung-2 capability status unchanged (planned);
  configuration names provisional; Gate A open; Gate B0 YES (PI, 2026-09-03).
  Correction to the packet's explanatory text, credited to the implementer:
  the truncated-series relative error at `x = 1e-3` is `x³/60 ≈ 1.7e-11`, not
  `x/120`; the prescribed series and switch were unchanged.

- **2026-09-03 (Rev 18.1, post-push certification, Claude — recorded with
  Rev 19.1).** `e7cd918` (MEM-0) and `215a876` (docs: remove private note
  filenames), with `4e3c1a1` between them, verified on a fresh public clone at
  `215a876f12b3775998893fcdc6d4ed1475155e2f`: **945 passed** no-Qiskit,
  **966 passed, 0 skipped** with the Qiskit extra, matching the Rev 18 body
  (+18 from Rev 17.1's 927 / 948). Smoke test
  `Min loss 27.7 dB | Fidelity 0.990`; emission SHA-256 in the certifying
  environment `8c7cef94…9a6d5`. Discharges the Rev 18 header's "commit hash
  omitted": **MEM-0 = `e7cd918`.** Registered follow-up (low priority, separate
  bounded change with default-emission regression check): `pip install -e .`
  modifies tracked `src/quantum_qkd_aero.egg-info/`; untrack generated
  egg-info.

- **2026-09-03 (Rev 19, RECOH-1 implementation and local validation).**
  Implemented the authorized five-file instrument change against clean main
  `215a876`: two isolated source modules, one 25-test calibration file, the
  v1.1 plan of record, and this record. Baseline reruns produced **966 full /
  945 no-Qiskit-file**; final runs produced **991 / 970**, **+25/+25**, matching
  the approved delta. These are implementer-run local validations, not an
  independent certification. No dependency installation, existing source/test
  edit, README change, SPEC/ADR change, or output/schema addition was required.
  The current local `outputs/results.json` SHA-256 before and after was
  `1047ed1d722d04b856dc25056e0017c1584431a74f03c488611fdce3dcca1bc4`;
  it is an environment-local comparison, not a replacement for historical
  hashes or the portable in-process parity oracle. The console remained
  `Dashboard Updated: Min loss 27.7 dB | Fidelity 0.990`.

  Plan provenance: `claude_RECOH-1-plan.md` v1 (SHA-256
  `c654ba43abed1e6d708980068e15cdf8add1b2dbbc12e753f7108bc1d78b835b`)
  plus the PI-approved execution packet rev 2 (SHA-256
  `eab6c4b7f7284821242d7710072d3c473ca221032b058e98c5419a79e9ec89cc`)
  were folded into `docs/RECOH_1_PLAN.md` v1.1. C1-C4, R-a/R-b, the
  composition test, and the Choi normalization/validation split are explicit.
  The packet's explanatory series-error typo was corrected with PI approval:
  the leading relative truncation error is `x³/60 ≈ 1.67e-11` at
  `x = 1e-3`, not the earlier `x/120 ≈ 1e-5`; the prescribed series and
  switch were not changed. High-precision Decimal checks now exercise the
  stable helper independently. Gate B0 was recorded YES by the PI on this
  date; Gate A remained open and rung-2 remained planned. This instrument
  authorization does not imply that any memory capability gate was passed.

  Record reconciliation: prior revision headers are preserved verbatim below
  as historical snapshots, rather than presenting their counts as current.
  The body had still described Rev 17's 948/927 tests despite the later
  MEM-0 baseline; that superseded paragraph is archived below. MEM-0 is now
  represented in the phase/module inventory without upgrading its benchmark
  status. Source-intensity consumption is attributed to LINK-7, correcting
  the through-line's previous attribution to LINK-6b. ADAPT-1's stale
  “hash pending post-push certification” wording is removed from the current
  next-steps body because the existing Rev 17.1 entry already certifies
  `8993d6c`. HYBRID-1's “in this same commit” companion wording is now
  explicitly historical to that phase. No prior correction entry is removed.

### Historical revision-header snapshots (archived 2026-09-03)

The following headers are retained as written at their revisions. Their
counts, status wording, and emission-streak claims are historical statements,
not the Rev 19 current-state summary.

> **REVISION 18 — updated 2026-08-27 (MEM-0 external benchmark reconstruction; commit hash omitted pending post-push certification; see Correction Log).**
> MEM-0 adds a standalone analytic reconstruction of the finite-key calculation published in
> Gündoğan, Sidhu, Krutzik & Oi, *Optica Quantum* **2**(3), 140–147 (2024), together with its
> benchmark artifact at `docs/benchmarks/BENCH-mem0-gundogan.md` — the project's first
> claims-register entry. The module `src/qkd/mem0_gundogan.py` is deliberately outside the
> authoritative emission pipeline: standard library plus NumPy only, pure functions, no RNG,
> no seeds, no event simulation, no memory state machine, and no LINK/adaptive/hybrid/fixture
> imports (enforced by an import-hygiene test). It implements no age-dependent memory model;
> the published benchmark collapses storage time into the constants η_mem = 0.6 and a
> storage-time-independent e_m, so MEM-0 is decoupled from the pending memory SPEC.
>
> **The benchmark is reported as an independent reconstruction, not a replication, and it is
> not a passed benchmark.** The 2-QM cutoff and threshold behaviour reproduces within
> predeclared tolerances under a source-backed inherited error-correction inefficiency
> f_e = 1.16 (adopted from Luong et al., *Appl. Phys. B* **122**, 96 (2016), which the
> benchmark paper cites and whose ε_m construction matches its Table 1; the benchmark paper
> itself does not state f_e). Absolute key-length magnitudes and block counts remain low by
> ≈3.5× against two mutually consistent source routes, and the 1-QM comparison remains
> unreproduced because the published source-to-(n_Z, n_X) count path is not printed. A factor
> ledger of eight physically interpretable counting conventions found none that is
> source-defensible and reproduces both the 1-QM cutoff and the rate crossover. Acceptance
> anchors were predeclared and are recorded as tested, never as selecting an interpretation;
> the paper-anchor test family is withheld pending resolution rather than weakened. An author
> query was sent 2026-08-27. Suite **966 with the Qiskit extra, 945 with the Qiskit-specific
> file ignored** (+18 from Revision 17.1); default emission SHA-256 unchanged — **fourteenth**
> consecutive change. Details in `docs/benchmarks/BENCH-mem0-gundogan.md`.

> **REVISION 17 — updated 2026-08-24 (FIXTURE-1 + ADAPT-1; commit hash omitted pending post-push certification; see Correction Log).**
> FIXTURE-1 adds a non-production quasiperiodic misalignment stress fixture and its
> bounded finite-range discrepancy design note. ADAPT-1 implements ADR-0004 D1's passive
> tier-4 attribution monitor: committed scalar references, exact-cadence synthetic traces,
> separately calibrated TWIN-1 whiteness/NIS outcomes, a conservative operational OR
> mapping, canonical adaptive records, and closed observable provenance metadata. Passive
> monitoring never emits `ADVERSARIAL_SUSPECTED`; active attribution remains ADAPT-2.
> Suite **948 full / 927 no-qiskit-file**, **+50/+50** from the tracked FIXTURE-1 baseline
> of 898/877. No production physics, artifact writer, output schema, or default emission
> path changed.
>
> **REVISION 16 — updated 2026-08-24 (LINK-7 source consumption, `f8c82f2`; see Correction Log).**
> LINK-7 consumes `source.intensity_factor` — the last deferred observable — completing the
> ADR-0003 estimator boundary: every partition field now has an authorized consumer or an
> explicit identity default. Robust decoy inversion under a hard certified common-mode bound
> (complete-rate minimization with a single witness, certified 1-D minimizer, conservative
> emission `R_certified = max(0, R_hat − ε)`); code-derived source-support gate (manifest echo
> audit-only); manifest v3 with strict v1/v2/v3 matrix and Pre-Gate 0 v2 oracle; first-ever
> `bb84.py` edit (pure statistics factoring, parity-certified). Suite **874 full / 853
> no-qiskit-file** (853 + 1 skipped without qiskit); default emission SHA-256 unchanged —
> **tenth** consecutive change. Details in `docs/LINK_7_PLAN.md` §15 and the Correction Log.
>
> **REVISION 15 — updated 2026-08-24 (HYBRID-1 Stage 1 — boundary state model;
> see Correction Log).** HYBRID-1 implements the ADR-0004 D2 hybrid QKD+PQC
> boundary's **state model only**: tier-4-owned attribution contracts at
> `src/qkd/adaptive/contracts.py` (`AttributionVerdict`,
> `DegradationAttributionEvidence`, per D-H1-2) and the boundary's enums, frozen
> dataclasses, validation, canonical serialization/digests, and the
> algorithm-posture registry snapshot interface under `src/qkd/hybrid/`, per the
> companion's Stage 1 contract checklist. No policy engine, KDF/cryptographic
> derivation, authentication integration, or physics coupling — those remain
> Stages 2–5. `AssuranceDecision` gains a `policy_profile` field beyond the
> companion v3.1 schema listing (Echo blocker 1); the companion is reconciled to
> v3.2 in this same commit (schema-listing addition + revision-log entry only).
> The LINK architectural lane remains active with LINK-1 through LINK-6b
> complete. Historical corrections and superseded counts/statuses remain in the
> Correction Log.

**Superseded Rev 17 current-suite paragraph (archived verbatim):**

**Test suite (current Rev 17 local `qkd_env` validation):** **948 passed**
(`qkd_env/bin/python -m pytest -q`); excluding the Qiskit-specific file, **927 passed**
(`qkd_env/bin/python -m pytest -q --ignore=tests/test_teleportation_qiskit.py`). Delta from
the tracked FIXTURE-1 baseline (**898/877**) is **+50/+50**, all in
`tests/test_adaptive_monitor.py` and `tests/test_adaptive_canonical.py`; the v1.4.1 C5
check was folded into the existing adaptive import-graph test, so the approved total
remains 948. Earlier per-revision counts remain in the Correction Log. The default artifact
is byte-identical to a clean `4c8d817` export in the same environment; cross-environment
literal hashes are not portable, so in-process parity remains the portable oracle.

### Earlier correction entries


- **2026-08-24 (Rev 17.1, post-push certification, Claude).** Both commits verified on a
  fresh clone of the public remote at HEAD `8993d6c` (`4c8d817` FIXTURE-1 → `8993d6c`
  ADAPT-1). Process note, recorded for honesty: the PI pushed before independent
  verification this once (the usual order is verify-then-push); certification was
  therefore performed entirely post-push and found nothing requiring remediation.
  Findings: FIXTURE-1's four files hash-identical to the Echo-reviewed rev 4/5 set;
  the transient APPLY note correctly absent; committed `docs/ADAPT_1_PLAN.md`
  hash-identical to the issued v1.4.1 packet (`67b10ac4…c1ac7d`); frozen
  `adaptive/contracts.py` byte-unchanged from `6f292d4`; `docs/private/` untracked;
  both commits' file lists exactly match their staging inventories with nothing else.
  The two superseded-test edits are precisely the permitted changes (scan narrowed to
  `contracts.py`; allowlist gained exactly `module == "qkd.canonical"`), each with its
  citing comment, physics-prefix assertions verbatim; HYBRID canonical fixtures
  byte-untouched (the refactor oracle held); C5 verified — the adaptive import-graph
  test asserts `{"serialization.py"}` is the only hybrid importer of `qkd.canonical`.
  §6.1 anchors literal in the committed tests: master seed `20260825`, component band
  `(3, 19)/200` re-derived and asserted, one-sided combined bound `32/200`, power floor
  `45/50`, arm-equivalence `≤ 7/50`, and the three step-angle literals. Suite on the
  fresh no-qiskit clone: **927 passed + 1 skipped** (948 full-env by PI under
  `qkd_env`); default emission `3d1544…f1417` unchanged — the eleventh and twelfth
  consecutive changes under the frozen default artifact. ADAPT-1 is the first
  Codex-implemented lane: two stop-and-surface events (preflight inventory conflict;
  unenumerated hybrid import guard), both correct, both resolved by PI-approved packet
  amendment before any test was touched.

- **2026-08-24 (Rev 17, FIXTURE-1 + ADAPT-1).** The PI resolved the sequencing conflict by
  landing FIXTURE-1 first as isolated commit `4c8d817`; its transient APPLY note was deleted
  rather than committed. ADAPT-1 was then redispatched from that tracked baseline under
  `docs/ADAPT_1_PLAN.md` v1.4.1. The first full ADAPT run stopped at one unenumerated legacy
  test: canonical-mechanism extraction correctly made `hybrid/serialization.py` import
  `qkd.canonical`, while the HYBRID import guard still prohibited that module. Per the
  superseded-test policy, implementation paused; the PI approved §6 superseded test 2 and
  C5 before the allowlist gained exactly that one clause. Physics-prefix assertions were
  left untouched, only `serialization.py` exercises the allowance, and HYBRID byte/digest
  fixtures remain the oracle. Final real local runs: **948 passed** with the Qiskit extra
  and **927 passed** with `tests/test_teleportation_qiskit.py` ignored, **+50/+50** from the
  FIXTURE-1 baseline of 898/877. A clean `4c8d817` export and the working tree emitted
  byte-identical default `outputs/results.json` in the same environment; no production
  writer or physics path changed. ADAPT-1's implementation commit hash is intentionally
  omitted for post-push certification.

- **2026-08-24 (Rev 16, LINK-7 + post-push certification, Claude).** LINK-7 (`f8c82f2`)
  reconciled and certified: fresh public clone — all thirteen code/test/fixture files
  hash-identical to the independently verified copies; `docs/private/` untracked; suite
  853 passed + 1 skipped (no-qiskit clone), 874 by PI under `qkd_env`; default emission
  `3d1544…f1417` unchanged (tenth consecutive change; an implementer report initially
  cited a wrong hash from hashing the wrong artifact — corrected against
  `outputs/results.json` during verification). Highlights of record: the §13 addendum
  process worked as designed — the implementer left three unenumerated failing tests
  failing rather than silently patching them, the PI approved the addendum, and only
  then were they edited; `bb84.py`'s first-ever modification is the D3 statistics
  factoring (+33/−9, laws moved verbatim, certified by the frozen-hash set, a pinned-grid
  parity test, and the byte-identical default path); a genuine robustness finding
  (minimizer non-convergence on wide clamped-zero plateaus) is fail-loud as
  `RobustRateCertificationError`, with fix-vs-accept and the closed-form Lipschitz
  derivation registered as follow-ups for Echo's post-review. Consumption state after
  LINK-7: the residual bridge rejects nothing non-identity; the anti-smuggling machinery
  is retained by completion, not deletion, for future partition additions.

- **2026-08-24 (Rev 15 post-push certification, Claude).** Implementation commit
  `c69e461` verified on a fresh clone of the public remote: all fifteen delivered
  files hash-identical to the independently verified copies; `docs/private/`
  untracked; `docs/LINK_7_PLAN.md` correctly absent from tracking (C10/C11);
  suite 800 passed + 1 skipped (no-qiskit clone) with zero regressions from
  601+1; PI full-environment certification 821 passed, 0 skipped under
  `qkd_env` (qiskit extra present since the HYBRID-0 certification round).
  Independent pre-push verification had additionally reproduced both sample
  canonical digests byte-for-byte, the timestamp-grammar rejection matrix on
  construction and load paths, the loader's canonical-reserialization refusal,
  all five `AssuranceDecision` invariants, the computed (non-stored)
  `RegistrySnapshot.digest()`, the physics-import isolation of the
  `adaptive`/`hybrid` namespaces, and the exact 7-line companion v3.2 diff.
  Implementer performed by the Sonnet subagent per PI instruction (recorded in
  packet rev 6); four implementer-flagged minimal resolutions accepted and
  listed in the packet's §(f) report.

- **2026-08-24 (Rev 15, HYBRID-1 Stage 1).** Implemented against
  `docs/HYBRID_1_PLAN.md` rev 6 (D-H1-1/2/3 confirmed by Echo, 2026-08-24), on
  fresh-clone HEAD `d48cb2c`. Files created: `src/qkd/adaptive/__init__.py`,
  `src/qkd/adaptive/contracts.py` (tier-4-owned, stdlib-only:
  `AttributionVerdict`, `DegradationAttributionEvidence`);
  `src/qkd/hybrid/__init__.py`, `src/qkd/hybrid/states.py` (nine enums, twelve
  frozen dataclasses per the companion's C2 exhaustive Stage 1 contract set),
  `src/qkd/hybrid/registry.py` (`AlgorithmPostureRegistry`, digest-free
  `RegistrySnapshot`, D3 CI consistency check), `src/qkd/hybrid/serialization.py`
  (generic canonical-envelope encoder/decoder driven by each dataclass's own
  type hints, D-H1-3); `tests/test_hybrid_states.py`,
  `tests/test_hybrid_registry.py`, `tests/test_hybrid_serialization.py`;
  `tests/fixtures/hybrid_canonical_fixtures.json` and
  `tests/fixtures/hybrid_non_canonical_physical_link_state.json`. Modified:
  `README.md` (HYBRID lane status lines), this record (Revision 15), and
  `docs/architecture/pqc_hybrid_architecture.md` (v3.2: `policy_profile` added
  to the `AssuranceDecision` schema listing, plus the v3.2 revision-log entry —
  nothing else; `git diff --stat` shows a five-line delta). Import-graph tests
  confirm D-H1-1/2 by AST inspection: `adaptive/contracts.py` has zero
  project-internal imports; `qkd.hybrid` imports only `qkd.adaptive.contracts`
  and its own siblings, never a physics module; no module outside `qkd.hybrid`
  imports it. Local validation (this sandbox, no qiskit extra):
  `PYTHONPATH=src python3 -m pytest -q` → **800 passed, 1 skipped**; with
  `--ignore=tests/test_teleportation_qiskit.py` → **800 passed**. Delta from
  the Rev 14 baseline (601 passed + 1 skipped / 601 passed) is **+199 / +199**,
  matching the three new test files' collected count exactly, zero regressions
  elsewhere. The qiskit-extra full-environment count is not re-run in this
  sandbox and is left unstated rather than computed by arithmetic (companion
  review-driven validation item 10: expected/derived counts are stop-condition
  thresholds, never evidence). `AssuranceDecision.policy_profile` is recorded
  as a deliberate deviation from the companion v3.1 schema section (Echo
  blocker 1), reconciled to v3.2 in this same commit per C7/C9 — no deferral.
  `git status --short` after staging shows only the allowlisted HYBRID-1 paths
  as new/modified; `docs/HYBRID_1_PLAN.md` itself is staged and committed per
  C11 (this packet's own allowlist addition); `docs/LINK_7_PLAN.md` is not
  present in this working tree and remains untouched either way.

- **2026-08-23 (Rev 14 certification correction).** Commit C (`89f3952`) described its
  verification as "post-push certification." That verification was performed by Codex
  in the local Mac `qkd_env` as the preparation/validation actor (Lana created the Git
  commits) and is therefore recharacterized as **local validation**, not independent
  certification. Independent post-push certification was performed by Claude on
  2026-08-23 from a fresh GitHub sandbox clone of HEAD
  `89f3952010b7cab3c4f2276e85aae02393e64c05`: commit boundaries A/B/C, ADR Accepted
  status, the companion's single-line delta and SHA-256 anchor
  (`d6c4a01b…fee898`), README lane declaration, Rev 14 provenance chain, and independent
  sandbox test runs of **622 passed** with Qiskit / **601 passed** with the Qiskit file
  ignored, delta **+0/+0**, were all confirmed. Certification record: this entry plus
  the certification document retained in project context.

- **2026-08-23 (Rev 14, HYBRID-0 Stage 0).** ADR-0004 r3 was ratified by Lana and
  added as Accepted in the minimal Commit A recorded in §1. It adds the adaptive-coupling
  tier above ADR-0003's three channel tiers and places hybrid QKD+PQC orchestration above
  the physics pipeline, with physical and cryptographic assurance retained as separate
  evidence streams. The ADR packet source hash was
  `6ab23fd2ba5ef8a3ce51b03c22c1934e2c32d2c001c67e38baccb8186d627c17`; the Accepted
  file hash is `67d55bf3dc76ec87b38aed6c403199c7e16c3f75c1a70fec3c39d7b7c929d27d`.
  Companion v3.1 was added as informative; byte comparison confirms its only delta from
  the supplied file is the approved status line. Supplied/as-committed companion hashes:
  `70a292854f8acd7a20fe015fa92866ddefe6901a9ca2b7bac5155cb3444bbe4b` /
  `d6c4a01b4c4d4c0d8aeecd9652725c3769cd9b6de488409efb7bfa5ce9fee898`.
  Provenance chain: Echo v1 `68662884…8f7bdb` → Claude v2 `9dff3b3d…64fe69` →
  Echo/Codex review input `71bc2fd8…4b4dbe63` → v3 `7d66a654…d4d6e38` → PI
  ratification-read round trip `f3a9f222…57b6fc` → supplied v3.1 → informative
  as-committed file. The source execution packet (`a835e7df…623e56`) is preserved as
  `docs/HYBRID_0_PLAN.md` (`8cf2c3a9…963ed4`) with an explicit dispatch correction:
  stale Scope labels r2/v3 became r3/v3.1, Revision 13 became live Revision 14, and its
  old LINK/test baseline was reconciled to `11dd75e`; no prior revision history was
  erased. Real local validation remained **622/601**, delta **+0/+0** from Rev 13.1.
  No source, tests, schema, output, or physics behavior changed. Post-push certification
  from a fresh GitHub clone of Commit B `4e8b066` confirmed the A/B commit boundaries,
  Accepted/informative status markers, lane declaration, Development Record state, and
  companion SHA-256 against the Commit B message. The Mac `qkd_env` dependency runtime
  executed the clone's source: **622 passed** with Qiskit and **601 passed** with
  `tests/test_teleportation_qiskit.py` ignored. Commit C records this evidence.

- **2026-08-18 (Rev 13.1, `e3815c0`).** LINK-6b reconciled: the three remaining channel-side
  observables (`timing_jitter_s` → gate acceptance `erf(Δt/(2√2σ_t))` on the existing
  `gate_window_s` control with an adjacent-gate leakage guard; `frequency_offset_hz` → Gaussian
  spectral-filter acceptance with declared residual fraction, two new controls
  `filter_sigma_hz`/`doppler_residual_fraction`, receiver-assumed source linewidth;
  `misalignment_error` → `e_d' = e_d + m − 2e_d m`) consumed through the LINK-6a receiver
  path as channel-copy folds before the base call — both certified base laws inherited;
  the residual bridge now rejects only `intensity_factor`. Three constant owners
  (`timing_jitter`, `polarization_misalignment`, `phase_misalignment` with parameter domain
  `0 ≤ Δφ ≤ π/4`); manifest v2 with a strict v1/v2 compatibility matrix and a **Pre-Gate 0**
  historical v1 oracle (fixtures regenerated by the reviewer from a pristine `2763c24` clone,
  identical); ADR-0003 status log gained one PI-signed clarification line (§3.6 item 1
  illustrative; response-law + validity-guard binding; `feasible` reserved) — body unchanged.
  Policy adopted (LINK-6b plan §12): a reviewed plan may enumerate superseded tests by name;
  all others remain oracles; one out-of-list edit was flagged by the subagent and accepted.
  Reviewer-caught defects in the plan before dispatch: a false `Q'_vacuum` invariance under
  gate/filter loss (shared history — Claude's error), a periodic-sine domain guard, and a
  circular oracle ordering. Certified 622/601 on a fresh clone; default emission `3d1544…`
  unchanged (ninth PR). LINK-6c (filter/background coupling; radiance vs rate-density and FOV
  signal-cost questions open) registered as the next candidate.

- **2026-08-18 (Rev 13).** Reconciled the record for LINK-1 → LINK-6a and TWIN-1/2 (eight
  code PRs, `8b7ef46` → `2763c24`, plus `03736da` licence/citation housekeeping and
  `5b530ca` gitignore). Superseded body facts from Rev 12 preserved here: "LINK-1 and later
  remain future work; no `ChannelEffect`, `GeometryProvider`, `ControlSpec`, `ChannelStack`,
  source module, test, or schema field exists yet" (true 2026-07-17; all now exist);
  "Test suite (current Rev-10 count) 163/142" (now 562/541); the working-method line naming
  Codex as sole implementer (Sonnet subagent on trial since 2026-08-10; Codex remains the
  fallback pending the PI's decision); §4 "Further out: LINK-1 may add
  identity-only interfaces". Per-commit certification recomputed on a fresh clone
  2026-08-18 (full / no-qiskit-file): 163/142, 219/198, 255/234, 294/273, 347/326, 389/368,
  414/393, 439/418, 562/541; default emission SHA-256 `3d1544027517…f1417` at every commit.
  Post-push verification of `2763c24` (Claude, 2026-08-18): fresh public clone; nothing under
  `docs/private/` tracked; all twelve delivered files hash-identical to the verified copies;
  Echo's four dispatch-gate reviews byte-identical to their published SHA-256s; 562 passed;
  emission hash unchanged. Recorded honestly: LINK-6a's implementation touched one existing
  test *fixture* (two null keys) — see §2 LINK-6a; and its plan went through v1 → v2 → v2.1
  → v2.2 → v2.3 → v2.3.1, with real defects caught at each stage (including a wrong numerical
  anchor authored by Claude and softened "exact" tests authored by the subagent).

- **2026-07-17 (Rev 12).** Reconciled the record for LINK-0 / ADR-0003
  ratification (documentation-only revision; no numerical facts superseded;
  test counts unchanged at 163/142, delta 0). Superseded statuses preserved
  here: the Revision 11 header summary read — ADR-0003 and the in-repo
  architecture map added; ADR-0003 defines the future LINK workstream as a
  ratification-ready architecture contract; no LINK code, composition-core,
  v2-schema, or trust-boundary change. The phase-overview row and §4 item 9
  previously read "Ratification-ready"; `docs/INTERFACES.md`'s document
  authority index previously named ADR-0003 as ratification-ready (updated
  to ratified in this revision's push). All of that state was true as of
  2026-07-05 and is superseded only in status, not in substance. This entry
  also records a Rev-11-era edit omitted from the Rev 11 log: ADR-0002
  gained a four-line non-normative cross-reference noting that ADR-0003
  extends its physical-simulation interface downstream without altering the
  composition core, v2 schema, or trust boundary — no ADR-0002 decision
  changed; the edit shipped in this revision's push. Post-push verification
  (Claude, 2026-07-17): ratification commit `d62a52e` (ADR-0003 only,
  single-hunk header diff vs. the frozen 2026-07-05 text — body
  byte-identical); companion commit `8801f64` (eight files as planned);
  tests 163/142 on a fresh clone, delta 0 confirmed.

- **2026-07-05 (Rev 11).** Added ADR-0003 /
  `docs/architecture/ADR-0003-composable-link-effect-pipeline.md` as the
  ratification-ready contract for the future LINK workstream and added
  `docs/architecture/quantum-qkd-aero-architecture-map.md` to the repo. The map
  records LINK as a new lane, distinct from PR-A/B/C/D and from ADR-0002's
  medium/topology/protocol axes. `docs/INTERFACES.md` now includes a document
  authority index and names ADR-0003 as ratification-ready. This is a
  documentation-only architecture update: no LINK source, tests, schema fields,
  or `DECLARED_SCHEMA_EXTENSIONS` changes were added.

- **2026-07-05 (Rev 10).** Reconciled the record for PR-D / Deep Schema Validation
  and Dimensional Correction. The queued `docs/SCHEMA_HARDENING_2B.md` concept was
  retained but its pre-fibre field-level content is superseded by
  `docs/PR_D_SCHEMA_HARDENING.md`. The active validator now performs L1 recognition,
  L2 finite type checks, L3 ranges/vocabulary, L4 constants, L5 cross-field consistency,
  and provenance validation by default. This revision also corrects the PR-C fibre
  artifact defect: `profile.aggregates.secure_key_yield_bits` was emitted on a
  `length_km` axis even though the computed quantity had units of bit-km/s, not bits.
  Fibre artifacts now omit that field, and the validator forbids it for `length_km`
  while requiring and checking it for `time_s`. Current suite count from real
  validation: 142 passed with `--ignore=tests/test_teleportation_qiskit.py`; 163
  passed with the qiskit extra available. Delta from Rev 9 is +22 collected tests,
  slightly above the planned +13-17 range because the mutation suite is parametrized
  across 17 negative cases and additional API/extension checks were added.

- **2026-06-30 (Rev 9, 6f0527d).** Reconciled the record for PR-C / Fibre Length-Sweep.
  Fibre is now the second real caller of `mission.simulate_profile(...)`, using
  `fibre_channel_state(...)` over a `0..220 km` / `5 km` grid and emitting a native v2
  artifact with `link.medium = "fibre"`, `profile.axis.name = "length_km"`, and no
  `geometry` section. The max-secure-distance headline is the last positive-SKR sample
  (`190.0 km`), not the first zero sample (`195.0 km`); the emitted bracket preserves
  both samples so the grid resolution is auditable. Current suite count from real
  validation: 120 passed with `--ignore=tests/test_teleportation_qiskit.py`; 141
  passed with the qiskit extra available. Delta from Rev 8 is +7 collected tests.
  Satellite output remains pinned to the PR-B stable hash and
  `python src/qkd/run.py` still prints `Dashboard Updated: Min loss 27.7 dB |
  Fidelity 0.990`.

- **2026-06-30 (Rev 8, cadab78).** Reconciled the record for PR-B / v2 output schema
  cutover. The current emitted artifact is schema `2.0` with top-level
  `schema_version`, `link`, `teleportation`, `summary`, `profile`, `geometry`,
  `mission`, `provenance`, and `run_metadata`. The old v1 `pass_profile` shape and
  the pre-fibre orbital `V2_REQUIRED_KEYS` stub are retired. Dashboard reading,
  schema recognition, provenance validation, and regression tests now target v2.
  Output parity is verified by mapping every captured v1 leaf to exactly one v2
  location while enumerating the new v2 leaves. Current suite count from real
  validation: 113 passed with `--ignore=tests/test_teleportation_qiskit.py`; 134
  passed with the qiskit extra available. Delta from Rev 7 is +4 collected tests.
  `python src/qkd/run.py` still prints `Dashboard Updated: Min loss 27.7 dB |
  Fidelity 0.990`; physics composition and numerical values are unchanged.

- **2026-06-30 (Rev 7, 42096c9).** Corrected the PR-A regression tests after clean-clone
  verification exposed two brittle guards: exact equality over raw floating-point arrays
  could fail on environment-level last-ULP differences, and a plot-path comparison needed
  to be pinned to the real production emission path rather than a separately constructed
  payload. The refactor itself remains correct: `ea50802` and the PR-A production path
  both emit `outputs/qkd_teleportation.png`, not `outputs/qkd_pass.png`, and no emitted
  values or physics behavior changed. The test suite count is unchanged from Rev 6:
  109 passed with `--ignore=tests/test_teleportation_qiskit.py`; 130 passed with the
  qiskit extra available. Delta from Rev 6 is +0 collected tests.

- **2026-06-30 (Rev 6).** Reconciled the record for PR-A / Medium-Neutral
  Composition Core, committed in Rev 6. `mission.py` now
  contains `ProfileResult` and `simulate_profile(...)`, and `simulate_pass()` delegates
  downstream profile composition to that core while retaining satellite geometry and
  atmospheric channel-state construction. The byte-identity fixture was captured from the
  actual pre-refactor git version (`git archive HEAD` at `ea50802`), not from a
  hand-reproduced algorithm. Current suite count from real validation: 109 passed with
  `--ignore=tests/test_teleportation_qiskit.py`; 130 passed with the qiskit extra
  available. Delta from Rev 5 is +5 collected tests, all in `tests/test_profile.py`.
  Output shape, `run.py`, schema recognition, provenance policy, dashboard behavior, and
  physics values remain unchanged.

- **2026-06-27 (Rev 5).** Reconciled the record for PR-Fibre-1, committed with this
  change (d004c25). This revision adds the dedicated-fibre front-end as the first
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
