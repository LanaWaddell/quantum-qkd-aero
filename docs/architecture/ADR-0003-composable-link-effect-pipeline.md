# ADR-0003 — Composable Link-Effect Pipeline and Geometry-Aware Channel Modeling

**Status:** RATIFIED — 2026-07-17 (PI: Lana). Body unchanged from the
2026-07-05 RATIFICATION-READY text; ratified as-is following independent
literature contact (see status log).
**Status log** (dates evidence-backed: review-thread timestamps via Echo;
git history confirms this file's first commit is the ratification commit):
- 2026-07-05 — Initial draft (Lana, PI).
- 2026-07-05 — Echo systems review, round 1; revisions incorporated.
- 2026-07-05 — Echo review round 2 incorporated (explicit composition rules
  §3.3.1, hash-derived order-independent RNG §3.4, `EffectiveLinkState` as
  construction bridge §3.4, controls-as-explicit-input + mandatory
  auditability §3.6, refined retained-ensemble language §6, LINK-1
  acceptance criteria §7.1, ratification decisions resolved with fibre
  deferred). Frozen RATIFICATION-READY; PI sign-off deliberately deferred
  for a fresh-eyes review.
- 2026-07-17 — Evidence contact at ratification: Singh et al.,
  arXiv:2507.08102 (time-bin review) assessed against every flagged
  section; the evidence memo
  (`docs/references/quantum-qkd-aero-adr0003-evidence-memo-timebin-review.md`)
  concluded **no amendment required**. Deliberately deferred §3.3.1 rules
  remain deferred to LINK-1 by design, now with literature evidence
  recorded for their discharge.
- 2026-07-17 — **RATIFIED** by Lana (PI). Body text unchanged.
**Date:** 2026-07-05 (frozen) / 2026-07-17 (ratified)
**Deciders:** Lana (PI); reviewed by Echo (systems, two rounds), Claude (physics/architecture)
**Extends:** ADR-0002 (three-axis medium/topology/protocol model). Does **not** alter
the composition core, the v2 schema, or the trust-layer boundary.
**Workstream label:** `LINK-*` (composable source–channel–detector effects).
This is a new lane; it does not reuse or extend the PR-A/B/C/D identifiers.
**Research role:** beyond software design, this ADR is the first formal bridge
between *modeling decoherence* and *designing coherence-preserving
interventions* — via the intervention surface (§3.6) and the coherence-recovery
boundary (§6). It defines what "recoherence" may honestly mean on this substrate.

---

## 1. Context

The verified physics substrate models the link as a per-sample computed
transmittance plus specified equipment constants. Extending realism (Doppler,
pointing jitter, daylight background, μ fluctuation, afterpulsing, scintillation)
raises three architectural risks this ADR exists to close *before* the first such
module is written:

1. **Special-casing** — the composition loop branching on whether an effect is
   static or time-varying, accumulating per-module knowledge at the composition site.
2. **Protocol smuggling** — channel effects emitting protocol-level quantities
   (QBER "contributions", security conclusions) that no single effect can honestly
   own, because those quantities are nonlinear functions of the *composed* state.
3. **Optimistic smoothing** — stochastic fast dynamics baked into precomputed
   tables, which averages transmittance *before* the nonlinear gain/QBER map and
   systematically overestimates key rate.
4. **Untyped intervention** — coherence-affecting levers (coincidence window,
   spectral bandwidth, FOV, μ) living as undeclared config values, so the later
   optimization research (Phase 2D) has no principled surface to act on and no
   feasibility coupling to the channel state.

The substrate already contains the two ingredients an intervention framework
needs: a *mechanism* by which coherence degrades (`p_eff = p_source · S/(S+B)`,
Phase 2B-5) and a *lever with a genuine cost* (tighter `coincidence_window_s`
suppresses B but also cuts S). This ADR gives that pairing a typed home, which
is what turns a decoherence *model* into an intervention *platform* — the
research bridge named in the preamble.

## 2. Decision (one paragraph — the whole architecture)

Adopt a composable link-effect pipeline in which source, channel, and detector
effects emit **physical observables** evaluated at time `t` and pass geometry
`geom`. Deterministic geometry may be tabulated behind a provider interface;
stochastic exogenous effects must be generated at evaluation time with seeded
RNGs and explicit correlation times/spectra; protocol-endogenous choices remain
live and are never precomputed. QBER, gains, and key-rate quantities are computed
by **estimator layers** from the composed physical state — never by individual
channel effects. Effects and estimators **declare their tunable controls**
(§3.6), giving interventions a typed surface; parameter values arrive through
the same front door whether chosen by a human, a static config, or a learned
policy, and the physics never knows which. The pipeline receives only
`(t, geom)` plus typed physical parameters and returns only physical
observables: the ADR-0002 wall, enforced by type signature. Within this frame
the substrate expresses **selection-based coherence recovery** (§6);
operation-based recoherence is a declared expansion on the topology axis, not
pre-built.

## 3. Interfaces

### 3.1 GeometryProvider — deterministic exogenous state

```python
class GeometryProvider(Protocol):
    def at(self, t: float) -> PassGeometry: ...
```

`PassGeometry` carries only deterministic orbital/pass state: elevation, slant
range, radial velocity (Doppler input), and later optional descriptors
(day/night flag, atmospheric profile id). Two conforming implementations are
anticipated: **table-backed** (interpolated precomputed pass; frozen, versionable
fixtures for regression tests — the LINK-1 default) and **ephemeris-backed**
(lazy propagation; added later behind the same interface, nothing downstream
changes).

> Resolved (ratification decision 1): the table-backed provider **wraps** the
> existing `orbit.py` columnar `SatellitePass` rather than replacing it.
> `SatellitePass` stays the representation; `GeometryProvider` is the interface.

### 3.2 ChannelEffect — physical observables, single evaluate()

```python
class ChannelEffect(Protocol):
    def evaluate(self, t: float, geom: PassGeometry) -> LinkObservables: ...
```

A single `evaluate()` returning a typed object, per Echo's review, rather than a
method forest in which every effect stubs out most observables. Effects declare
neither "static" nor "dynamic"; a constant is a function that ignores `t`.

### 3.3 LinkObservables — partitioned to respect the existing contract

**Design constraint (differs from the review sketch):** the observables object
must not duplicate the ratified seam between `ChannelState` and
`DetectorParams`. `ChannelState.transmittance` excludes detector QE by design,
and a single-fold-scaling guard ensures detection efficiency is multiplied
exactly once. A flat dataclass carrying both `transmittance` and
`detector_efficiency` would create a second location where efficiency could be
folded — a double-count hazard. The observables are therefore partitioned:

```python
@dataclass(frozen=True)
class ChannelObservables:      # composes INTO ChannelState territory
    transmittance_factor: float = 1.0        # multiplicative
    background_rate_hz: float = 0.0          # additive
    misalignment_error: float = 0.0          # combined per estimator rule
    frequency_offset_hz: float = 0.0         # additive (Doppler etc.)
    timing_jitter_s: float = 0.0

@dataclass(frozen=True)
class DetectorObservables:     # composes INTO DetectorParams territory
    efficiency_factor: float = 1.0
    dark_count_rate_hz: float = 0.0
    afterpulse_prob: float = 0.0
    dead_time_s: float = 0.0

@dataclass(frozen=True)
class LinkObservables:
    channel: ChannelObservables = ChannelObservables()
    detector: DetectorObservables = DetectorObservables()
```

Composition rules are per-field and stated explicitly — not left implicit —
because rates and multiplicative factors compose trivially but timing, dead
time, afterpulsing, and misalignment do **not** all compose additively, and an
unstated "just add them" default would be a physics error.

#### 3.3.1 Composition rules (binding)

| Field | Composition rule |
|---|---|
| `transmittance_factor` | **Product** over effects |
| `background_rate_hz` | **Sum** over effects, unless an effect declares correlated structure for estimator/PDT handling |
| `frequency_offset_hz` | **Sum** over effects |
| `timing_jitter_s` | **Not naively additive** — estimator-owned or quadrature-composed; LINK-1 must choose the rule before implementation |
| `misalignment_error` | **Estimator-owned**; LINK-1 may define a documented low-order default but must not bake a universal physical rule early |
| `efficiency_factor` | **Product** over detector effects, folded into `DetectorParams` **exactly once** (the existing single-fold guard extends to the stack) |
| `dark_count_rate_hz` | **Sum** over detector effects |
| `afterpulse_prob` | **Not blindly additive** — detector-model owned; additive only under an explicitly declared low-probability approximation |
| `dead_time_s` | **Detector-model owned**; competing dead-time effects require an explicit rule, not summation |

The rule of thumb the table encodes: independent multiplicative losses
multiply, independent event rates add, and everything with a nonlinear or
saturating physical character (timing, dead time, afterpulsing, misalignment)
is owned by the estimator/detector model with an explicitly declared
combination rule — never summed by default.

### 3.4 ChannelStack — composes observables, nothing more

```python
class ChannelStack:
    def __init__(self, effects: list[ChannelEffect],
                 geometry: GeometryProvider, *, seed: int | None): ...
    def state(self, t: float) -> EffectiveLinkState: ...
```

`EffectiveLinkState` is the composed physical state at `t` — the **construction
bridge**, not a sibling API: it feeds the existing `ChannelState` +
`DetectorParams` (and `PhysicsSignals`) construction, preserving the ratified
public seam and keeping byte-stability easy. It computes **no** gains, QBER, or
key rate.

**Stochastic reproducibility (binding).** The stack owns stochastic
reproducibility. Each stochastic effect receives a deterministic child RNG
stream derived **by stable hash** from `(run_seed, effect_id, stream_purpose,
optional sample/block_index)`. Child streams must be **order-independent**:
inserting, removing, or reordering *unrelated* effects must not change another
effect's stochastic sequence. This is the specific bug the rule exists to
prevent — RNG streams assigned by registration order mean adding effect X to
`A → B → C` silently changes B's and C's randomness, making stochastic
comparisons and regression tests fragile. Effects own their stochastic process
model and correlation structure; the stack owns seeding, stream identity, and
replay stability.

### 3.5 Estimator stage — protocol quantities from composed state

The existing `run_decoy_bb84` / `secure_key_rate` path *is* the estimator stage;
this ADR names the boundary rather than inventing a new one. Gains, per-intensity
QBER, decoy bounds, SKR, and finite-key corrections are computed from
`EffectiveLinkState` (+ protocol parameters). No `ChannelEffect` ever emits a
QBER contribution: dark-count QBER depends on the composed gain, so the quantity
does not exist at the per-effect level.

### 3.6 Controls — the intervention surface

Every parameter in the pipeline is one of exactly two kinds, and the
distinction is **declared, not implicit**:

- **Fixed physical configuration** — τ_zenith, orbital altitude, detector QE,
  dark-count rate: properties of the world and the equipment. Not tunable
  in-run.
- **Controls** — coincidence window Δt, spectral filter bandwidth, field of
  view, source intensity μ, decoy intensities, basis bias p_Z: parameters an
  operator or policy may legitimately adjust. These are the intervention
  surface.

```python
@dataclass(frozen=True)
class ControlSpec:
    name: str                      # e.g. "coincidence_window_s"
    unit: str                      # SI unit string
    bounds: tuple[float, float]    # static physical bounds
    # feasibility coupling: bounds that depend on the current link state,
    # e.g. Δt cannot be tighter than the composed timing jitter
    feasible: Callable[[EffectiveLinkState], tuple[float, float]] | None = None

class Controllable(Protocol):
    def controls(self) -> tuple[ControlSpec, ...]: ...
```

Effects and estimators that own tunable parameters implement `Controllable`.
Two properties this buys:

1. **Interventions have physics-coupled feasibility.** The composed
   `timing_jitter_s` bounds how tight Δt can go; FOV bounds couple to pointing
   variance. An intervention's viability depends on the channel state rather
   than floating free — which is precisely what makes "optimal coherence under
   noise" a well-posed optimization rather than parameter fishing.
2. **The Phase 2D read/act surface is closed.** The research layer *reads*
   `PhysicsSignals` and *acts* only through declared `ControlSpec`s. Everything
   it can touch is enumerated; everything else is fixed configuration it
   cannot reach. This is the action-space half of "the agent never sees what
   it can't game."

Controls are protocol-endogenous by definition (taxonomy §4, third tier): live
only, never precomputed.

**Controls are explicit inputs, not mutable effect state (binding).** A control
is evaluated as an explicit input value for a given sample/block/run — never as
an in-place mutation of an effect object. A controlled effect must be fully
reproducible from `(t, geom, fixed_config, control_values, rng_stream)`. This
forbids hidden temporal coupling (an effect quietly carrying state from one
call to the next) and is what makes replay and audit sound.

**Control auditability is mandatory (binding).** Control values in force must be
recoverable from the emitted record. LINK implementations record run-level
static controls always; where controls vary over time/block/sample, they record
the corresponding control trace **or** a reproducible policy reference plus seed.
Per-sample metadata is not required for every run if it would bloat output, but
a declared audit mode or reproducible compact representation is. This is the
same auditability discipline as the max-secure-distance bracket: an intervention
that changed a result must be visible as having done so.

## 4. The honesty taxonomy (tabulate / generate / live)

| Tier | Examples | Rule | Why |
|---|---|---|---|
| Deterministic exogenous | elevation, range, radial velocity | **Tabulate freely** | Smooth ephemeris; interpolation error controllable and quantifiable |
| Stochastic exogenous | scintillation, beam wander, pointing jitter (ms-scale) | **Generate at eval time**, seeded RNG, explicit τ_c/spectra | Smoothing into tables averages η *before* the nonlinear gain/QBER map → systematic key-rate overestimate |
| Protocol-endogenous | adaptive μ/decoy choices, probing fraction, commit decisions | **Live only** — never precomputed | Closed-loop by definition; depends on statistics observed up to `t` |

**Relation to the PDT machinery (channel-dynamics spec):** fine-grained seeded
generation and the per-block probability-distribution-of-transmittance summary
are the two sanctioned modes of the *same* constraint — both deliver the
distribution (or samples from it) to the estimator *before* the nonlinearity.
What is forbidden is the third, unsanctioned mode: collapsing the distribution
to its mean upstream of the estimator. PDT mode is an approved optimization,
not an exception to this rule.

## 5. The wall (restated for this layer)

Channel/effect/estimator layers may receive: time, pass geometry, source
parameters, detector parameters, seeded stochastic configuration. They may
return: physical observables and protocol-consumable link state.

**The wall is about information type, not provenance.** Physics layers accept
typed physical parameter values through the declared control surface (§3.6)
regardless of *who* chose them — a human operator, a static config file, or a
learned policy — and never know or care which. Setting μ or Δt is a legal
physical input whatever chose it. What is forbidden is trust-layer *state*
entering as input or physics *emitting* trust-layer conclusions:

- **May not receive:** agent internal state, attack-likelihood estimates,
  confidence/value signals, secure/insecure verdicts, any meta-evaluation
  state.
- **May not emit:** verdicts, policy recommendations, trust scores — anything
  above the `PhysicsSignals` surface.

This is the ADR-0002 principle running in both directions: the agent never
sees what it can't game, and the physics never sees what chose it. Breaching
requires changing a Protocol signature — which is an ADR conversation, not a
commit.

## 6. Coherence recovery — the vocabulary boundary

This section is the research-bridge core, and it draws one line precisely so
the bridge stays rigorous rather than metaphorical.

**In scope now — selection-based coherence recovery.** What this substrate can
express is coherence recovery *by selection*: filtering in time (Δt), spectrum
(bandwidth), and space (FOV) excludes accidental-background events, so the
**post-selected ensemble** has higher effective Werner parameter
(`p_eff = p_source · S/(S+B)`, with B falling faster than S under tighter
filters — up to the jitter/acceptance floor). No decohered state is restored;
noise events are excluded from the ensemble. The recovery is real, measurable,
and paid for in signal rate. The first well-posed Phase 2D research question
falls directly out of this framing:

> *How much coherence can selection alone recover, and at what signal cost?* —
> maximize `p_eff` (or SKR) over the declared controls, subject to
> feasibility coupling, across channel regimes.

**Declared expansion — operation-based recoherence.** Physically restoring or
concentrating entanglement — purification, distillation, memory-based
protocols — operates on multiple pairs and requires multi-segment composition:
the **topology axis**, which ADR-0002 correctly defers until a second member
earns it (anti-speculative-generality). Nothing in this ADR pre-builds it; the
LINK frame is designed so that when repeater members arrive, purification
enters as operations *between* estimator stages, not as a rewrite of the
effect pipeline.

**The precise claim (binding vocabulary).** The substrate does **not** increase
the coherence of an already-accepted quantum state. It increases the coherence
of the *retained ensemble* by changing the acceptance rule and the physical
filtering conditions. That phrasing separates three distinct things that loose
language conflates, and they form a clean ladder:

1. **Improving the accepted ensemble** — selection/post-selection. *In scope
   now* (LINK).
2. **Restoring the individual physical state** — true recoherence on a single
   carrier. *Not expressible here, and not claimed.*
3. **Concentrating entanglement across multiple resources** — purification /
   distillation. *Topology-axis future* (repeater members).

**The rule:** documentation, papers, and proposals must not describe rung 1 as
"recoherence" (rung 2) or as entanglement concentration (rung 3). The honest
vocabulary is *coherence recovery by post-selection* / *changing the retained
ensemble* (now) vs. *recoherence operations* (topology-axis future). This
ladder is what makes the Echorym ↔ physics bridge (Phase 2D) defensible in
front of a physics referee — and in Echorym terms it is the first formal world
rule where "recovery" is not magic reversal but disciplined selection,
constrained action, and auditably changed interaction with the environment.

## 7. Validation requirements (per module, uniform)

1. **Limiting case:** `ChannelStack([effect])` at zero-noise parameters
   reproduces the ideal channel exactly.
2. **Known-regime anchor:** each effect reproduces a published or analytic
   QBER/gain/key-rate behaviour in at least one regime (e.g. `E_x → 1/2` as
   η → 0; `E_x → e_d` at high η).
3. **Single-fold guard (extended):** detector efficiency and transmittance are
   each folded exactly once across the composed stack.
4. **Stochastic honesty:** `E[η_turb] = 1` normalization where applicable;
   seeded reproducibility; distribution (not mean) reaches the estimator.
5. **Byte-stability:** with the stack empty or all-identity, existing v2
   emission is unchanged.
6. **Control legality:** every in-run parameter change goes through a declared
   `ControlSpec`; values outside static bounds raise; values outside the
   feasibility coupling are rejected with the violated constraint named (not
   silently clamped — clamping would hide infeasible interventions from the
   optimizer).
7. **Replay stability under composition change:** with a fixed seed and a
   stochastic identity/mock effect, replay is deterministic *and* inserting,
   removing, or reordering unrelated effects does not alter another effect's
   stream (the §3.4 order-independence guarantee, tested directly).

### 7.1 LINK-1 acceptance criteria (ratified — LINK-1 is deliberately boring)

LINK-1 adds **only** types, interfaces, identity behaviour, and tests. **No**
Doppler, jitter, afterpulsing, optimization, or estimator changes beyond
proving the empty/identity stack is byte-identical. The acceptance shape:

1. Empty `ChannelStack` or all-identity effects → existing v2 output
   **byte-identical**.
2. One multiplicative transmittance effect → `ChannelState` transmittance
   changes **exactly once**.
3. One detector-efficiency effect → `DetectorParams` efficiency changes
   **exactly once**.
4. An undeclared runtime control → the stack **rejects** it.
5. An out-of-bounds declared control → the stack **rejects** it with the
   violated `ControlSpec` named.
6. Fixed seed + stochastic identity/mock effect → replay is deterministic and
   effect order does **not** silently alter unrelated streams.

Criteria 4–6 are the ones that most directly encode the binding rules above
(controls registry enforcement at the stack; order-independent RNG); they are
the acceptance-criterion form of §3.4 and §3.6.

## 8. Scope and roadmap placement

**In scope (this ADR):** the interfaces (§3, including the control surface
§3.6), the taxonomy (§4), the wall restatement (§5), the coherence-recovery
boundary (§6), the validation pattern (§7), the LINK-* lane definition.

**Out of scope:** any implementation; any change to the composition core, v2
schema, or current PR queue; the non-stationarity generator itself (a later
atmospheric-medium enrichment that will *conform to* this ADR); topology or
protocol axis expansion.

**Placement:** downstream enrichment after the current stabilization lane —
**not** gated on PR-D. Coordination note for PR-D: since LINK (and the control
surface) will extend the emitted field set, PR-D's L2–L5 validators should be
written **extensible** — validate what exists, tolerate *declared* extensions,
fail on undeclared ones — so hardening doesn't have to be reworked when LINK
lands, and strict validators are never loosened ad hoc under time pressure.
**Status (PR-D landed, remote `ab2de8e`):** this mechanism is now implemented as
the `DECLARED_SCHEMA_EXTENSIONS` registry in `schema.py` — unknown top-level
sections and unknown keys inside known sections fail unless declared there. A
future LINK field set lands as a registry entry, not a validator change; that
is the concrete extension point this ADR builds on.

Proposed LINK queue (identifiers reserved; scoping deferred):

| ID | Scope |
|---|---|
| LINK-0 | This ADR, ratified |
| LINK-1 | Observables dataclasses + Protocols + `ControlSpec`/`Controllable` + table-backed GeometryProvider; zero behaviour change |
| LINK-2 | Migrate existing loss/detector constants into the effect framework; byte-parity asserted |
| LINK-3 | Geometry-coupled deterministic effects: Doppler, pointing-loss hooks |
| LINK-4 | Stochastic exogenous effects: jitter, scintillation (seeded; PDT bridge) |
| LINK-5 | Source/detector realism: μ fluctuation, afterpulsing, dead time |
| LINK-6 | Estimator integration + validation-curve artifacts |
| LINK-7 | Finite-key / correlated-noise hardening notes (with PR-D if it lands) |

## 9. Consequences

**Positive:** wall enforceable by type signature; uniform test pattern extends
the suite mechanically; static-vs-dynamic ceases to be an architectural fork;
the Phase 2D action space is enumerated and physics-bounded from birth; the
selection-vs-recoherence vocabulary is fixed before any paper or proposal can
blur it; Codex-facing slice is this document alone (physics rationale in,
trust narrative out — context compartmentalization mirrors code
compartmentalization).

**Costs/risks:** the provider wraps `SatellitePass` (decision 1), so the risk
is interface leakage — LINK-1 must keep `GeometryProvider` free of
satellite-specific assumptions where practical (bearing on the deferred fibre
decision 4); the §3.3.1 composition rules must be honoured or the stack
silently drops or mis-combines observables (the non-additive fields are the
trap); LINK-2's migration of working code is pure-refactor risk and must carry
byte-parity certification like PR-A did; feasibility coupling introduces a
state-dependent bound (a `ControlSpec` that reads `EffectiveLinkState`), which
must remain read-only or it becomes a backdoor from state into configuration.

**Rejected alternatives:** per-observable method forest (encourages stub
pollution); `qber_contribution` on effects (protocol smuggling — the quantity
doesn't exist per-effect); flat observables dataclass mixing channel and
detector fields (double-fold hazard against the ratified transmittance
contract); baking stochastic dynamics into geometry tables (optimistic-smoothing
physics error).

---

## Ratification decisions (resolved)

These six were the open questions; the review resolved five and deliberately
defers one.

1. **`PassGeometry` vs `SatellitePass` → WRAP.** `GeometryProvider` becomes the
   interface; `SatellitePass` remains the existing representation, wrapped by a
   table-backed provider. Do not replace it.
2. **`EffectiveLinkState` → construction bridge**, not a sibling API. It is the
   richer internal object from which `ChannelState` + `DetectorParams` (+
   `PhysicsSignals`) are constructed, preserving the ratified public seam and
   minimizing schema churn. (Now stated in §3.4.)
3. **Misalignment combination → estimator-owned.** LINK-1 may define a
   documented low-order default rule only; do not bake a universal physical
   rule early. (Now in the §3.3.1 table.)
4. **Fibre placement → DEFERRED to LINK-1 evidence (the one deliberate
   non-decision).** Fibre may be expressible through the existing medium-neutral
   `simulate_profile` profile axis plus a conforming effect, or it may reveal
   that `GeometryProvider` should generalize. LINK-1 must avoid satellite-specific
   assumptions in the provider interface where practical, but must **not**
   introduce a generalized `PathProvider` unless byte-parity migration or fibre
   integration demonstrates the need. This is decided by interface pressure and
   the byte-identity test, not by architectural taste — consistent with the
   project's anti-speculative-generality discipline.
5. **Controls registry → both, enforced at the stack.** Per-effect declaration
   *plus* a central runtime registry the stack assembles; feasibility coupling
   is enforced at the stack, because only the stack sees the composed state the
   coupling depends on. This mirrors PR-D's schema-side `DECLARED_SCHEMA_EXTENSIONS`
   (a central declared registry that fails on the undeclared); the runtime
   controls registry is its live analogue, and LINK-1 should decide whether the
   two literally share a declaration pattern.
6. **`run_metadata` control auditability → YES, mandatory.** Record run-level
   static controls always; record time/block/sample-varying controls by trace,
   block summary, or reproducible policy reference plus seed. (Now binding in
   §3.6.) A declared audit mode / compact reproducible representation satisfies
   this without forcing per-sample bloat on every run.
