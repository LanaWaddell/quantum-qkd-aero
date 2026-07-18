# Quantum-QKD-Aero: Architecture Map

*The standing top-level view of the architecture and the projects it will simulate. Reconciles the **foundational contract** (ADR-0002's three-axis model, ADR-0003's LINK lane, and the completed PR-A/B/C/D queue) with the **research layer** (the experiment ladder). Update status fields here as work moves roadmap → specced → built.*

> Reconciled against **ADR-0002** and **ADR-0003**. The repo ADRs and `docs/INTERFACES.md` are authoritative for the contract; this map tracks status against them. Project discipline term: **physics-forward / anti-speculative-generality** — generalize an axis only when a second real member earns it.

---

## Two layers of "architecture" (orient first)

- **Foundational layer — the contract.** ADR-0002's three axes (**medium / topology / protocol**), ADR-0003's LINK workstream (**composable source-channel-detector effects**), and the v2 output schema built on them. The completed PRs generalize the composition core and schema across the *existing* members.
- **Research layer — the thesis.** "Communication is the adaptive capability" — trust/operational coherence as measurable quantities, realized as the experiment ladder. This is **Phase 2D**, and it **reads `PhysicsSignals`** behind a hard wall (see below); it never writes into the physics channel.

The contact window is not a third organizing idea — it's the **topology axis's** expansion mechanism, and topology is deferred until a second member earns it.

---

## The wall (non-negotiable)

The physics channel carries **no trust/cognitive field**. Phase 2D (the research/trust layer) reads `PhysicsSignals` — a defined, read-only output surface — and nothing in the cognitive layer flows back into physics emission. ADR-0002 is about the physics-channel design space *only*. Every "standing invariant" in the research layer is downstream of this wall.

---

## Architectural foundation — ADR-0002 three-axis model

A concrete link is a **point** in this space; every emitted result declares which point it occupies. Each axis generalizes one member at a time.

| Axis | Member(s) today | Frontier members | Status |
|---|---|---|---|
| **Medium** (how a photon gets A→B) | `atmospheric` (free-space, orbital *or* terrestrial), `fibre` | terrestrial free-space LOS, underwater optical, on-chip waveguide | **FULLY GENERALIZED — earned.** Interface = the transmittance contract (`INTERFACES.md`): each medium computes transmittance differently, emits the same `ChannelState`, reuses `DetectorParams`. New media are trivial. |
| **Topology** (shape of the link) | `point_to_point` | `mdi`/`twin_field` (central measurement node), `repeater_chain` (multi-segment + swapping), `entanglement_distribution` (mid-source) | **NAMED, NOT GENERALIZED.** One member. Polymorphism deferred until a 2nd topology is built — and a repeater chain is *composition over segments*, not a sweep, so it's a real future design step, not pre-built. |
| **Protocol** (what's run over the link) | `decoy_bb84` (ships with QND/PNS Eve model + teleportation-fidelity path) | `mdi_qkd`, `twin_field_qkd`, `cv_qkd` (homodyne, Gaussian mod — different physics), `entanglement_swapping` | **NAMED, NOT GENERALIZED.** One member; same deferral discipline. |

Note the cross-axis subtlety: **MDI / twin-field is both a topology** (two channels meeting at a central node) **and a protocol** (its own rate math). CV-QKD is protocol-only. Repeaters are topology + `entanglement_swapping` protocol.

**v2 generalizes medium fully; declares topology/protocol explicitly but single-valued.** Naming an axis costs ~zero and prevents the flat-schema trap (a future topology becomes a scoped "make `topology` polymorphic," not a migration). Building an axis out with one member would be the speculative-generality trap.

---

## Completed build queue (PR-A → PR-D)

Completed stabilization work, **below** the experiment ladder. Certified at each step: satellite stayed working through A (byte-identical), B migrated it with parity asserted, C added fibre on the proven core, and D hardened the emitted artifact boundary.

| PR | Scope | Status |
|---|---|---|
| **PR-A — Composition core** | Generalize the composition layer to a medium-neutral `simulate_profile` over an independent profile axis (time for an orbital pass, length for a fibre sweep); refactor `simulate_pass` to delegate; prove satellite output **byte-identical**. No new physics, no schema change, no fibre. | **Complete** |
| **PR-B — v2 schema** | v2 schema against the three-axis frame: medium-general profile, explicit single-valued `topology`/`protocol`. Migrate satellite emission + dashboard + tests; assert **full output parity**. Hard cutover: v1 retired; pre-fibre `V2_REQUIRED_KEYS` stub retired as superseded (per ADR §6). | **Complete** |
| **PR-C — Fibre length-sweep** | Fibre (already a proven medium via `PR-Fibre-1`) as the second caller of the core, length-indexed, emitting v2 natively. Headline: **secure-key-rate vs. fibre length** and **maximum secure distance**. | **Complete** |
| **PR-D — Schema hardening** | L2-L5 validators and axis-conditional aggregate validation as a *separable depth dimension*. Robustness at the emitted-artifact boundary. | **Complete** |

Fibre computes its transmittance length-indexed ($\eta = 10^{-\alpha L/10}$, $\alpha \sim 0.2$ dB/km) and emits the same `ChannelState` — the medium abstraction is already earned; PR-C is the *v2-native length-sweep artifact*, not new medium machinery.

---

## LINK workstream — composable channel-physics layer

ADR-0003 defines a new `LINK-*` lane for composable source-channel-detector
effects. LINK is **not** a fourth ADR-0002 axis and does not reuse the PR-A/B/C/D
queue: it is a downstream physical-effects layer that enriches the existing
medium/topology/protocol design point while preserving the composition core, v2
schema, and trust boundary.

| LINK | Scope | Status |
|---|---|---|
| **LINK-0 — ADR-0003** | Ratify the composable link-effect pipeline, controls surface, stochastic reproducibility rules, and coherence-recovery vocabulary. | **Ratification-ready** |
| **LINK-1 — Identity stack** | Observables dataclasses + Protocols + `ControlSpec`/`Controllable` + table-backed `GeometryProvider`; zero behavior change and byte-identical empty/identity stack. | Future work |
| **LINK-2+** | Migrate loss/detector constants, add deterministic and stochastic effects, source/detector realism, estimator integration, and validation artifacts. | Roadmap |

---

## The project space — capability → axis → where it lives → status

| Capability | Axis / layer | Where it lives | Status |
|---|---|---|---|
| **Atmospheric link** (orbital + terrestrial free-space) | Medium | channel-dynamics spec (satellite); medium contract earned | **Built** |
| **Fibre link** | Medium | `PR-Fibre-1` (front-end, proven) | **Built** |
| **Fibre rate–distance curve (v2)** | Medium | PR-C | **Built** |
| **Composable link effects** | LINK layer (downstream channel physics) | ADR-0003 / LINK-* | Ratification-ready |
| **MDI / twin-field** | Topology **and** Protocol | frontier — not documented | Roadmap *(deferred on both axes)* |
| **CV-QKD** | Protocol | frontier — not documented | Roadmap *(deferred axis)* |
| **Quantum repeaters** | Topology (+ `entanglement_swapping` protocol) | contact-window ext / Exp 7′ | Roadmap |
| **Entanglement distribution** | Topology | frontier | Roadmap |
| **Hybrid networks** | Topology | contact-window ext / Exp 6′ | Roadmap |
| **Autonomous routing** | Topology | contact-window ext / Exp 6′ | Roadmap |
| **Delay-tolerant** | Topology × Medium | contact-window ext / Exp 6′ | Roadmap |
| **Deep space** | Medium × Topology | contact-window ext / Exp 8 | Roadmap |
| **Human–AI decision layers** | Research layer (**Phase 2D**, reads `PhysicsSignals`) | experiment ladder 2–5 + CSA framing | Specced *(downstream of substrate, behind the wall)* |

Concrete core: the **Medium** axis (both members built). Topology and Protocol are honestly deferred; the Phase-2D research layer waits on the substrate and reads `PhysicsSignals`.

---

## The experiment ladder — status tracker (Phase 2D, downstream)

Runs on the medium-general substrate (post PR-A/B) + a decision-epoch RL wrapper + the non-stationarity generator, reading `PhysicsSignals`. Downstream of the PR queue.

| # | Experiment | One line | Status |
|---|---|---|---|
| 1 | Value of adaptation | Does adaptation pay, and how does its value scale with volatility? | Specced — *gated on substrate + RL wrapper* |
| 2 | Shadow price of awareness | Observation-quality elasticity + sensing-vs-using tradeoff | Specced |
| 3 | Sabotage vs. weather | Separate QBER-matched attacks from natural degradation — **extends the existing QND/PNS Eve**, not from scratch | Specced |
| 4 | Capture / silent drift | Confidence–competence decoupling + committed-reference lead time | Specced |
| 5 | When to commit | Finite-key accumulate/commit/abort as learned optimal stopping | Specced |
| 6′ | Contact-aware scheduling (DTN) | Store/forward/hold over intermittent windows (topology axis) | Roadmap |
| 7′ | Repeater memory | Swap/purify/wait under decohering memory; PLOB baseline (topology + `entanglement_swapping`) | Roadmap |
| 8 | Deep-space open-loop | What light-time costs adaptive QKD; predictive vs. reactive | Roadmap |

The non-stationarity generator (channel-dynamics spec) adds *new* atmospheric physics, so it is **not** PR-A (which is byte-identical, no new physics) — it lands as a later atmospheric-medium enrichment feeding the ladder.

---

## Build order / dependency spine (corrected)

```
ADR-0002 three-axis model  (the contract)  ──  the wall: physics has no cognitive field
   │
   ├─ PR-A composition core ─► PR-B v2 schema  (medium-neutral core + PhysicsSignals surface)
   │        │                      │
   │        │                      ├─► PR-C fibre length-sweep (rate–distance)   [parallel caller]
   │        │                      └─► PR-D schema hardening
   │        │
   │        └─► ADR-0003 LINK lane ─► LINK-1 identity stack  (future, no behavior change)
   │
   └─ Phase 2D research layer  (reads PhysicsSignals, never writes physics)
        │   depends on PR-A/B; enriched by the non-stationarity generator (later atmospheric physics)
        └─ Exp 1 ─► Exp 2 ─► Exp 3, Exp 4 ─► Exp 5
             │
             └─ contact-window layer = topology polymorphism (deferred; composition over segments)
                  └─ Exp 6′, Exp 7′, Exp 8
```

The PR-A/B/C/D stabilization queue is complete. The next LINK work begins only
after ADR-0003 sign-off; LINK-1 is deliberately identity/zero-behavior-change
work. The Phase-2D ladder sits above the medium-general substrate and reads
`PhysicsSignals`.

---

## Document index

| Doc | Holds | Authority |
|---|---|---|
| **ADR-0002** *(repo)* | The three-axis model — the contract | **Authoritative** |
| **ADR-0003** *(repo)* | Composable LINK effect pipeline; controls surface; coherence-recovery boundary | **Ratification-ready** |
| **`INTERFACES.md`** *(repo)* | Transmittance contract; `ChannelState` / `DetectorParams` / `PhysicsSignals` surfaces | **Authoritative** |
| **`PR_D_SCHEMA_HARDENING.md`** *(repo)* | Active L2-L5 validator contract for current v2 artifacts | **Authoritative** |
| `SCHEMA_HARDENING_2B.md` *(repo)* | Historical pre-fibre hardening spec; layers/API retained, field content superseded | Historical |
| `quantum-qkd-aero-architecture-map.md` *(this file)* | Top-level view, axis status, PR/LINK queue, ladder tracker, index | Status tracker |
| `experimental-program.md` | The five core experiments — obs/action/reward/baselines/metrics/platform | Research layer (Phase 2D) |
| `channel-dynamics-spec.md` | Satellite-medium $\eta(t)$ generator (orbital A, OU turbulence B, cloud C) | Medium (`atmospheric`) |
| `contact-window-extension.md` | `ContactTopology` — topology-axis polymorphism; deep space / DTN / repeaters as regimes; Exp 6′/7′/8 | Topology (roadmap) |

---

## Folder conventions

1. **The wall.** No cognitive/trust field in physics; Phase 2D reads `PhysicsSignals` only. Never breached.
2. **ADRs are the contract's source of truth.** This map tracks status; contract changes go to the repo ADR first.
3. **Physics-forward / anti-speculative-generality.** Generalize an axis only when a second real member earns it. Medium is earned (2 members); topology and protocol stay single-valued-but-named until a 2nd member arrives — which is what prevents v2 re-migration when repeaters / MDI / twin-field / CV-QKD land.
4. **Certified at each step.** Byte-identical delegation (PR-A); full output parity asserted (PR-B). Don't build the Phase-2D layer on a substrate mid-migration.
5. **Standing experiment invariants** (Phase 2D, downstream of the wall): never credit unsafe key in any reward; always include an oracle/genie upper bound and report the fraction of the gap closed; keep what the *agent* observes strictly separate from what the *evaluator* uses.
6. **Label vision vs. built;** roadmap is never written as though it's running.

---

## How to use this map

**Contract** change (an axis gaining a member, a schema change, or LINK lane
boundary) → repo ADR first, then the axis/LINK table here. **Capability or
experiment** → add to the project-space table (which axis or lane) and, if it
implies a new experiment, to the ladder with the prior result it follows from.
Move status here before updating the individual spec. This file should always
answer: *what's the contract, what's real yet, and what's the actual next
build*.
