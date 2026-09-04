# SPEC-memory-lifetime-adr0003 — Memory-arm degradation surface

**Status:** RATIFIED — 2026-09-03 (PI: Lana). v0.3.1 body unchanged from the
Gate A-closed text except the enum rename `ideal` → `identity_state_evolution`. Governing document; extends ADR-0003; alters no ADR.
**Status log:**
- 2026-08-26 — v0.1 drafted (Chat Claude) as part of the DN/SPEC/RN MEM basis.
- 2026-08-26 — Review finding (Claude): incompatible degradation models in the
  Gündoğan and Paterson papers; amendment required.
- 2026-09-03 — v0.2 amendment drafted (Claude) as the Gate A review target.
- 2026-09-03 — Gate A: Echo adversarial review of DN + SPEC v0.2 + RN
  (SHA-256 `ab1f7ba1…aca5c4`); eight required revisions, three non-blocking.
- 2026-09-03 — v0.3 reconciled (Claude); v0.3.1 single consistency fix;
  Echo confirmation pass: **Gate A CLOSED**.
- 2026-09-03 — **RATIFIED** (PI). `ideal` renamed `identity_state_evolution`
  at ratification. Fresh-eyes read taken after a break rather than a separate
  session; see the Rev 19.2 companion entry on the tiered fresh-eyes rule.
**Disclosure:** publish-freely category (architecture/design decision;
simulation of published models). The memory scheduling policy is a held item
and is excluded from this document by §4. Log this commit as a disclosure
event.

---

## Original v0.3.1 header (retained)

**Status:** **Gate A CLOSED** (Echo confirmation pass 2026-09-03, after the
single v0.3.1 correction below). Ready for PI ratification (two-commit).
Gate A review SHA-256 `ab1f7ba16b8775d2080c7a71ee3be3a38fcec96aa7359fe2742b618d58aca5c4`.
**v0.3.1 change:** §3.2 `write_success` tier corrected from "exogenous event
realization" to protocol-endogenous, resolving the contradiction with §2
(Echo confirmation finding). Non-blocking note added at §3.1 on the reading of
`ideal`.
**Supersedes:** v0.3, v0.2 (2026-09-03), v0.1 (2026-08-26, Chat Claude).
**Scope:** QKD-Aero memory arm, degradation parameterization.
**Depends on:** ADR-0003 (three-tier taxonomy, §3.6 controls, §6 vocabulary).
**Companion references (private, local working folder, not tracked):**
`DN-time-delayed-two-memory.md` and `RN-strathclyde-oi-group-2026.md`, each
with a dated 2026-09-03 correction appendix.

## 0. Reconciliation record (Gate A dispositions → v0.3)

| # | Echo disposition | v0.3 action |
|---|---|---|
| 1 | §1.3 "bounded above by coherence" is false (`F = (1+C)/2 > C`) | Rewritten: fidelity is derived from the state/channel and target; no scalar bound stated. Error originated in v0.1 and was carried by Claude into v0.2. |
| 2 | `constant_error` is not a dephasing-map member | **Split into three axes:** `dephasing_model` (state evolution), `memory_error_model` (estimator mapping), `retrieval_decay_model` (efficiency). |
| 3 | `(1−C)/2` must not be universal | Scoped to the declared single-qubit pure-dephasing reference mapping; protocol/state-channel mappings declared per estimator (two-memory composition recorded). |
| 4 | "never coupled" too absolute | "Independently represented; not coupled by default; platform-specific correlation admitted only with evidence." |
| 5 | Remove `control_sequence` | Removed; lives in RECOH-2 until a common memory-control surface is earned. |
| 6 | No `platform → defaults` | `platform` is a descriptive tag; named source-backed **benchmark profiles** replace defaults (§3.4). |
| 7 | Deterministic ensemble map vs seeded trajectory | General taxonomy rule stated in §2. |
| 8 | DN/RN stale verification language | Dated correction appendices issued alongside (separate files). |
| 9 | Parameter vs realization tier labels | §3.2 split (`write_efficiency`/`write_success`; `swap_success_prob`/`swap_success`); v0.3.1: `write_success` is protocol-endogenous, consistent with §2. |
| 10 | Paterson local channel vs composed pair fidelity | Stated in §5.2. |
| 11 | ADR A1 `recovery_class` name → typed published result | Applied in ADR A1 v0.2 (separate file). |

---

## 1. Decomposing "memory lifetime"

The phrase collapses distinguishable quantities. For simulation they must stay
separate, because they degrade on different timescales, enter the key rate
through different terms, and — per the second-member evidence (§5.3) — are
placed differently by different published models.

**1.1 Coherence.** The stored superposition's off-diagonal magnitude,
`C(t) = 2|ρ₀₁(t)|` for a stored qubit. Governed by the state-evolution axis
(`dephasing_model`, §3.1).

**1.2 Retrieval efficiency.** The fraction of stored excitation recovered on
read-out, `η_mem(t)`; distinct from write efficiency. Governed by the
efficiency axis (`retrieval_decay_model`, §3.2). Coherence and retrieval
efficiency are **independently represented and not coupled by default**; a
platform-specific model may correlate them only where evidence warrants it,
and such coupling must be declared, never implicit. (For AFC/REID memories,
decoherence manifests as reduced efficiency at high fidelity — Gündoğan et
al. 2024 — which is the case that forces the independence.)

**1.3 Retrieved-state fidelity.** `F_state(t) = F(ρ(t), ρ_target)`, derived
from the stored-state channel and the declared target. It is **not** bounded
by the scalar coherence measure: for `|+⟩` under pure dephasing
`F = (1+C)/2 > C` on `0 < C < 1`. Fidelity is a derived output, never a knob.

**1.4 Memory error `e_m`.** The error the protocol estimator consumes.
Governed by the estimator-mapping axis (`memory_error_model`, §3.1): either a
declared constant or a declared mapping from the stored-state channel.

A model that exposes only one lifetime parameter will misattribute loss to
error, or the reverse, and the resulting QBER will not be trustworthy.

## 2. Taxonomy assignment

**Storage duration — deterministic exogenous (tabulate).** From overpass
geometry; transit time for the time-delayed scheme, plus the classical
signalling term for a swap. Computed by the orbital module.

**Classical communication latency — deterministic exogenous (tabulate).**
Slant range over c.

**Memory degradation — exogenous.** General rule (Gate A disposition 7): an
exogenous physical degradation model may be represented **either** as a
deterministic ensemble map (closed-form `C(t)`, `η_mem(t)` as functions of
storage duration — no RNG required) **or** as a seeded stochastic trajectory
(ADR-0003 §3.4 stream discipline applies). The tier is "exogenous, generated
at evaluation time from storage duration"; whether generation is analytic or
sampled is a property of the model, not of the tier. RECOH-1's analytic maps
are the first case; trajectory models (RECOH-3 candidates) are the second.

**Heralding and swap outcomes — protocol-endogenous (live).** Whether a
write succeeded, whether a Bell-state measurement produced a usable outcome,
and the branching that follows. These are **event realizations**; the
probabilities that parameterize them are configuration (§3.2).

Nothing here requires a fourth tier or a special case.

## 3. Parameter surface

### 3.1 Three degradation axes (replaces v0.2's single enum)

**State-evolution axis**

| Parameter | Tier | Values / meaning |
|---|---|---|
| `dephasing_model` | config | `identity_state_evolution` \| `lindblad_phase_damping` \| `gaussian_frequency_noise` |
| `D_phi` | config [1/s] | dephasing intensity, white-limit-safe (`D_phi ≡ σ²·τc` for Gaussian noise); `T2 ≡ 1/D_phi` is a reporting alias; zero valid; not used by `identity_state_evolution` |
| `noise_kernel` | config | `white` \| `ornstein_uhlenbeck`; `gaussian_frequency_noise` only |
| `tau_c` | config [s] | noise correlation time; `ornstein_uhlenbeck` only; `> 0` |

`identity_state_evolution` (renamed from `ideal` at ratification, PI
decision on Echo's non-blocking note): identity evolution of the stored state
over storage time — no time-resolved dephasing — **not** "perfect memory";
the error and efficiency axes are independent of it. RECOH-1's `kappa_ideal`
keeps its function name; the RECOH-2 docstring pass records the mapping
`kappa_ideal ↔ identity_state_evolution`.

Binding conventions (RECOH-1, certified `48ed81f`): `gaussian_frequency_noise`
+ `white` **is** `lindblad_phase_damping` (`C(t) = C₀ e^{−D_phi t}`) — one
member, two spellings, identity enforced by construction and test.
`ornstein_uhlenbeck`: `C(t) = C₀ exp[−D_phi·τc·g(t/τc)]`, `g(x) = x − 1 + e^{−x}`
(stable helper), monotone, BLP-Markovian on free evolution. Markovianity is
**never** configured; it is derived by the predeclared witnesses (§3.3).

**Estimator-mapping axis**

| Parameter | Tier | Values / meaning |
|---|---|---|
| `memory_error_model` | config | `constant` \| `derived_from_state` |
| `e_m_constant` | config | `constant` only (Gündoğan ε_m = 2%) |
| `state_error_mapping` | config | `derived_from_state` only; declares how the stored-state channel maps to the estimator's error term |

Declared mappings: **reference** (single stored qubit, pure dephasing,
coherence-sensitive basis): `e_m(t) = (1 − C(t))/2`. **Two-memory
composition** (independent phase-flip channels, Gündoğan two-QM estimator):
`e_dp = e_{m1}(1 − e_{m2}) + (1 − e_{m1}) e_{m2}` — equivalently the
complement of Paterson's pair-fidelity law
`F = λ_A λ_B + (1−λ_A)(1−λ_B)`. Neither mapping is universal; each estimator
declares the one it uses.

**Efficiency axis**

| Parameter | Tier | Values / meaning |
|---|---|---|
| `retrieval_efficiency_0` | config | at t = 0 |
| `retrieval_decay_model` | config | `none` \| `exponential` \| `benchmark_pinned` (functional form for `η_mem(t)`); independent of the other two axes by default |

### 3.2 Remaining surface (parameters vs realizations separated)

| Parameter | Tier | Notes |
|---|---|---|
| `platform` | config, **descriptive tag** | `rare_earth_crystal` \| `cold_atom`; carries **no defaults** (§3.4) |
| `write_efficiency` | config (probability parameter) | at t = 0, independent of storage duration |
| `write_success` | protocol-endogenous event | realized live from the declared write/link/herald model, parameterized by `write_efficiency`; affects subsequent branching |
| `storage_duration` | deterministic | supplied by the orbital layer, never set by hand |
| `mode_capacity` | config | multiplexed modes available for buffering |
| `swap_success_prob` | config / computed probability | parameter |
| `swap_success` | protocol-endogenous event | realized live |

Two memory instances per satellite for the time-delayed scheme. **Do not share
any degradation parameter between them** — `D_phi`, `tau_c`, `e_m_constant`,
`state_error_mapping`, `retrieval_decay_model`, or `retrieval_efficiency_0`.

### 3.3 Derived outputs (never configuration)

`C(t)`, `F_state(t)`, `e_m(t)` (when derived), `η_mem(t)`; on the RECOH
witness path additionally `trace_distance_backflow` (grid-resolved,
preselected pair), `recovery_fraction`, and the **typed recovery result**
(`none | protection_only | active_rephasing | environmental_backflow`) — a
classification of results, never an input. Retrieval efficiency is reported
alongside, never folded in.

### 3.4 Benchmark profiles (replace platform defaults)

Named, source-backed, immutable once recorded. Two are defined by §5:

```
profile: gundogan-2024-2QM
  platform: rare_earth_crystal (tag)
  dephasing_model: identity_state_evolution   # not time-resolved in the source
  memory_error_model: constant, e_m_constant = 0.02
  retrieval_decay_model: benchmark_pinned (η_mem ≈ 0.6 at 90 min)

profile: paterson-2026-fidelity
  platform: rare_earth_crystal (tag)
  dephasing_model: lindblad_phase_damping, D_phi = 1/τ_mem, τ_mem = 100 ms
  memory_error_model: derived_from_state, state_error_mapping = two_memory_phase_flip
  retrieval_decay_model: none (η_mem = 1)
```

A profile may be cited; it may not be edited. New profiles require a source.

## 4. Boundary check against ADR-0002 and disclosure boundary

Everything in this SPEC sits on the physics side of the wall. Nothing in the
trust layer reads these parameters directly; a later trust-layer feature
consumes published observables, including the typed recovery result, and may
not redefine them.

**Scheduling-policy exclusion (binding).** This SPEC parameterizes memory
*degradation* and records swap and write outcomes as event realizations. It
does **not** contain, and must never be extended to contain, the rule that
decides when a stored mode is retained, flushed, swapped, deferred, or
rerouted. That policy is a separately governed item; any proposal to add
decision rules to this document is out of scope here and goes through the
disclosure review first.

## 5. Validation targets

**5.1 Gündoğan et al. (Optica Quantum 2024) — profile `gundogan-2024-2QM`.**
Reproduce: asymptotic key rate approached under high channel loss with
few-minute contacts; improved dark-count resilience of the two-memory scheme
over one memory. MEM-0 (`e7cd918`) reconstructs the finite-key calculation
with storage time collapsed into constants; this arm must reproduce MEM-0's
numbers under the pinned profile. This is a benchmark profile, not a platform
default.

**5.2 Paterson et al. (arXiv:2604.16165) — profile `paterson-2026-fidelity`.**
Local memory channel: pure dephasing with `λ(t) = (1 − e^{−t/τ_mem})/2`,
i.e. `κ = 1 − 2λ = e^{−t/τ_mem}`, so `D_phi = 1/τ_mem`; unit memory
efficiency in that analysis; `τ_mem = 100 ms` representative. **Scope
note:** the paper's quoted quantity is the **distributed Bell-pair fidelity
after two independent memory channels**, not a single memory's `F_state(t)`.
RECOH's local dephasing map reproduces each memory's phase-flip channel; the
Paterson benchmark then composes the two channels
(`state_error_mapping = two_memory_phase_flip`) to reproduce the paper's
pair-fidelity law. Reproduce that law before any ν_c work.

**5.3 Second-member finding (revised per Gate A).** The two papers justify
**independent placement of age dependence** across memory state
error/coherence and retrieval efficiency, and therefore justify the three
separate surfaces of §3.1. Paterson supplies the `lindblad_phase_damping`
state-evolution member; the dynamical-decoupling literature on both platform
families (Zhong 2015, Heinze 2013, Dudin 2013; Echo-verified) supplies the
correlated Gaussian/OU member **as a control primitive for RECOH-2**, not as
evidence of intrinsic non-Markovianity; Gündoğan supplies the constant-error
plus age-dependent-efficiency benchmark arm.

**5.4 RECOH-1 reconciliation.** `src/qkd/mem_state.py` / `src/qkd/recoh.py`
provisional names (`dephasing_model`, `noise_kernel`, `D_phi`, `tau_c`) are
adopted unchanged; RECOH-1's `kappa_ideal` corresponds to this SPEC's
`identity_state_evolution`.
Ratification discharges the "provisional" marking; docstrings are updated in
the RECOH-2 packet, which is also where `control_sequence` first appears.

Extend the existing suite (970 / 991 at `48ed81f`); no parallel suite.

## 6. Claim boundary (mirrors ADR-0003 A1, provisional)

This SPEC provides state variables and models on which a rung-2 recovery
claim could be made. It makes none. Recovery is decided by predeclared
witnesses on certified implementations, mechanism typed, and recorded in the
Development Record. The existence of a state model, a dephasing model, or a
benchmark profile implies nothing about capability status.
