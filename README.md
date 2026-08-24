# Quantum-QKD-Aero — a verified quantum-link simulator

Quantum-QKD-Aero is a Python R&D sandbox for quantum key distribution and quantum
teleportation over real-world links. It models two channel media —
**satellite free-space** and **optical fibre** — sharing one verified physics core and one
medium-neutral composition layer, under a medium/topology/protocol channel model so further
link types slot in without re-architecture.

What distinguishes the project is **how** it is built, not just what it computes.

## What makes this different: verified, not decorative

Every quantity that drives the simulation is **computed from first principles and checked
against an analytic truth or a structural physical invariant** — never drawn, tuned, or
hardcoded to look right. This discipline is enforced, not aspirational, by a small set of
architectural invariants that the codebase holds:

- **Single Authoritative Pipeline** — exactly one production writer per generated
  artifact. No second program can silently produce the same output.
  (`docs/architecture/ADR-0001`.)
- **Ownership Invariant** — every physical quantity has one owner, is composed exactly
  once, at a real physical boundary; no layer silently absorbs another's responsibility.
  (E.g. channel transmittance means "photon launched → photon arrives at the detector
  face"; detector efficiency is owned separately and composed at point of use.)
- **Provenance Invariant** — every emitted quantity carries an enforced origin tag
  (`ANALYTIC` / `SIMULATED` / `DERIVED` / `ILLUSTRATIVE`); a validator rejects any output
  whose tags don't match what was actually emitted. Provenance **observes, never causes** —
  tagging a value cannot change it.

Parameters (link budget, source quality, sky background, fibre loss) are **illustrative,
not calibrated to a specific instrument** — the physical *relationships and behaviours*
are the point, not numbers tuned to one real system. Each output declares which of its
inputs are illustrative.

The development process mirrors this: implementations are **verified, not trusted** —
results are reproduced against the actual repository before being relied upon, and the
development record carries dated corrections rather than silently rewriting history.

## Implemented & verified now

**Quantum-information physics:**

- **Teleportation fidelity** from the Werner-state resource, `F = (1+p)/2`, benchmarked
  against the classical bound `2/3`. Validated three independent ways — analytic, numpy
  density-matrix, and an optional Qiskit circuit — agreeing to ~1e-9.
- **CHSH / Bell value** `S = 2√2·p`, driven by the *same* Werner parameter as
  teleportation (physically coupled, asserted as a structural fingerprint).
- **Decoy-state BB84** — Poisson pulse statistics, Lo–Ma–Chen single-photon bounds
  (verified conservative, with a tightening-limit check), GLLP asymptotic secure-key rate.
- **QND / photon-number-splitting eavesdropper** — a hidden-breach attack whose
  QBER-invisibility and decoy-anomaly signature *emerge* from per-photon-number behaviour:
  it holds QBER at the intrinsic level while raising a decoy anomaly and collapsing the
  key rate — the canonical attack a QBER-only monitor cannot see but decoy statistics can.
- **Background-light coherence** — effective Werner parameter `p_eff = p_source·S/(S+B)`;
  in daylight, teleportation fidelity arches over a pass and sags near the horizon, for a
  real reason (B=0 dark conditions stay flat).

**Channel media (the representation contract, proven under substitution):**

- **Satellite free-space** — transmittance from a free-space link budget (Beer–Lambert
  airmass extinction, Gaussian-beam diffraction capture), with satellite-pass geometry
  from a circular orbit and great-circle track (elevation and slant range derived and
  coupled, guarded by a coupling-proof test).
- **Optical fibre** — transmittance `eta = 10^(-(a*L + fixed)/10)` (standard SMF,
  illustrative attenuation and coupling loss). Fibre flows through the **unmodified** BB84 /
  coherence / teleportation stack, and as the **second caller of the composition core** it
  emits v2 natively with no schema change — validating the channel-representation contract
  and the medium generalization with zero downstream physics change.
- **Fibre rate–distance sweep** — secure-key-rate vs. length over the fibre, the canonical
  QKD rate–distance curve; secure key decays monotonically and the **maximum secure
  distance** (~190 km, default illustrative params) is reported with its grid-resolution
  bracket so the figure of merit is auditable.

**Honesty & verification infrastructure:**

- One authoritative composition layer (`mission.py`) -> one I/O layer (`run.py`); physics
  is computed in the composition, not the I/O.
- Enforced provenance on every emitted quantity, validated before each write.
- **Deep schema validation** — the v2 validator enforces L1 recognition plus L2 types,
  L3 ranges/vocabulary, L4 constants, and L5 cross-field consistency by default before
  every write, including the axis-conditional yield rule that keeps aggregates
  dimensionally honest (`docs/PR_D_SCHEMA_HARDENING.md`).
- **Passive adaptive attribution (ADAPT-1)** — committed scalar references and synthetic
  channel-state traces feed TWIN-1's separately calibrated whiteness/NIS diagnostics. The
  monitor records both component outcomes and applies a conservative operational OR mapping;
  it can report environmental consistency, unexplained degradation, or insufficient evidence,
  but never claims passive proof of an adversary.
- **Quasiperiodic stress fixture (FIXTURE-1)** — a non-production, nonphysical deterministic
  misalignment fixture for bounded finite-range sampling diagnostics; it is not admitted to the
  production stack or PDT allowlist.
- A pytest suite (**948 with the Qiskit extra, 927 with the Qiskit-specific file ignored**) covering the physics and the
  honesty guards (turbulence-independence, geometry coupling, decoy bounds,
  PNS-invisible-to-QBER, fidelity arch, fibre-contract flow, provenance enforcement,
  deep-schema goldens and mutation negatives, determinism).

## Architecture: the three-axis quantum-link model

The simulator describes a quantum link by three independent dimensions
(`docs/architecture/ADR-0002`):

- **Medium** — how a photon propagates (atmospheric, fibre, and future: terrestrial
  free-space, underwater, on-chip). **Two members exist today; fully generalized.**
- **Topology** — the shape of the link (point-to-point today; future: MDI / twin-field
  midpoint nodes, repeater chains, entanglement distribution). **Named explicitly,
  polymorphism deferred** until a second topology is built.
- **Protocol** — what is run over the link (decoy-BB84 today; future: MDI-QKD, twin-field,
  CV-QKD). **Named explicitly, polymorphism deferred.**

A concrete result declares its point in this space (`medium` / `topology` / `protocol`),
so a reader sees exactly which design point it occupies and a contributor knows where a
new link plugs in. The axes are *named* now (cheap, and it prevents a flat-schema dead
end); each is *built out* only when a second member earns it — the same
anti-speculative-generality discipline applied throughout the project.

Above this frame sits the **composable link-effect pipeline contract**
(`docs/architecture/ADR-0003`, ratified 2026-07-17): source, channel, and detector
effects compose into an `EffectiveLinkState` under explicit per-field rules,
stochastic effects draw from hash-derived order-independent RNG streams for exact
replay, operational controls are declared explicit inputs with feasibility coupling
to the composed link state, and estimator-stage observables (QBER, secure-key rate)
exist only after composition — never as per-effect fields. The **LINK architectural
lane remains active**, with LINK-1 through LINK-7 implemented; receiver-aware Eve
integration, filter/background coupling, and the benchmark sweep
driver remain open. ADR-0003 was ratified with its body unchanged after assessment
against the field's consolidated time-bin review (see `docs/references/`), which
independently validated the composition rules it defines.

Above the physics pipeline, **ADR-0004** (ratified 2026-08-23) defines a fourth,
adaptive-coupling tier and a strict hybrid QKD+PQC boundary with separate physical and
cryptographic evidence streams. **HYBRID-0 Stage 0 is complete as documentation only**;
**HYBRID-1 Stage 1 is complete**: `src/qkd/adaptive/contracts.py` and `src/qkd/hybrid/`
implement the boundary's state model (enums, frozen dataclasses, validation, canonical
serialization/digests, and the algorithm-posture registry snapshot interface) per
`docs/architecture/pqc_hybrid_architecture.md`, the informative companion. The policy
engine, KDF/cryptographic derivation, authentication integration, and physics coupling
(Stages 2-5) remain planned rather than implemented. **ADAPT-1 is complete** as a passive,
separately simulable tier-4 monitor over synthetic scalar traces and committed references;
active watermark attribution and live-pipeline coupling remain deferred.

## The medium-general channel layer (built & certified)

The composition layer and output schema are now generalized onto the three-axis model —
satellite and fibre both flow through **one medium-neutral composition core** and **one
axis-agnostic v2 schema**, with the satellite output preserved byte-identically through the
migration. The generalization was built and verified in sequence:

- **Medium-neutral composition core** — `simulate_profile` composes an ordered sequence of
  channel states along an *independent axis* (time for a satellite pass, length for a fibre
  sweep). The satellite pass delegates to it, proven byte-identical before/after.
- **Axis-agnostic v2 schema** — every result declares its `link` (medium / topology /
  protocol) and a generic `profile.axis`; a non-orbital medium omits satellite geometry
  entirely. A hard cutover from the satellite-only v1 format, with full output-parity
  asserted and provenance enforcement carried through intact.
- **Fibre length-sweep** — fibre as the *second caller* of the same core, length-indexed,
  emitting v2 natively with **no change to the core or schema** — the concrete proof the
  medium axis is genuinely generalized. Produces the canonical **secure-key-rate vs.
  distance curve** with **maximum secure distance** (~190 km on the default illustrative
  fibre) as the figure of merit.

**Next / active:** the **LINK lane** continues after LINK-7 with receiver-aware Eve
integration and honest filter/background coupling before any benchmark advantage claim.
**ADAPT-2** is the future active-probe/watermark attribution lane. **HYBRID Stage 2** (the
policy engine) consumes Stage 1's boundary state model only when sequenced; no
cryptographic derivation exists yet.
Phase 2D remains a downstream reader of computed `PhysicsSignals`; no trust field
enters the physics modules.

## Horizon

The three-axis model is built to absorb frontier link types without re-architecture:
quantum repeaters (beating the single-fibre loss wall via entanglement swapping),
MDI / twin-field QKD (beating the rate-distance limit via a central node), and
continuous-variable QKD (homodyne detection rather than photon counting). These are
**design targets the architecture accommodates, not implemented work.**

## Workflow

Set up the environment and install the package (dependencies are declared in
`pyproject.toml`; requires Python ≥3.10):

```
python3 -m venv qkd_env
source qkd_env/bin/activate
python -m pip install -e .
```

Two optional extras — the dev extra adds pytest, the Qiskit extra enables the third
independent teleportation-validation path:

```
python -m pip install -e ".[dev]"
python -m pip install -e ".[qiskit]"
```

Run the simulator (writes `outputs/results.json` and the pass plot):

```
python src/qkd/run.py
```

Run the test suite — **927 tests with the Qiskit-specific file ignored, or 948 with the
Qiskit extra installed**:

```
pytest
```

Launch the dashboard, then open `http://localhost:8080`:

```
npm install
npm start
```

## Code layout

Active code is in `src/qkd/`: the medium/physics modules (`channel.py`, `fibre.py`,
`orbit.py`, `teleportation.py`, `chsh.py`, `bb84.py`, `eve.py`, `coherence.py`); the
LINK/TWIN modules (`link.py`, `effects.py`, `detection.py`, `replay.py`, `benchmark.py`,
`twin.py`, `twin_watermark.py`); the passive adaptive monitor in `adaptive/`, the hybrid
boundary model in `hybrid/`, schema-neutral canonical serialization in `canonical.py`, and
the non-production stress fixtures in `fixtures/`; and `mission.py` (composition), `provenance.py`
(enforced origin tags), `signals.py` (interface dataclasses), `run.py` / `run_fibre.py`
(I/O), and `schema.py`. The dashboard is in `dashboard.js`; tests in `tests/`.
`docs/INTERFACES.md` is the canonical physics/output contract and
carries the document authority index; `docs/architecture/` holds the ADRs and the
architecture/status map; `docs/GLOSSARY.md` holds the binding vocabulary and the
community-translation boundary for public-facing artifacts; `docs/references/` holds
literature reference digests and evidence memos; the development record
(`docs/Quantum-QKD-Aero_Development_Record.md`) is the phase-by-phase handoff artifact.

`01-Gate-Noise-Archive/` is preserved archival research (Bell-state preparation,
noise-model, measurement routines) — not part of the active workflow.

## Scope & honesty

Parameters throughout (zenith optical depth, beam divergence, receiver aperture, source
pair-rate, sky-background rates, detector efficiency, fibre attenuation and coupling loss)
are representative illustrative values, **not calibrated to a specific site or
instrument**. The simulator models correct physical *relationships and behaviours* — how
loss varies over a pass, how a PNS attack hides from QBER, how daylight degrades coherence,
how fibre rate decays with distance — not the absolute performance of any particular real
link. Per-module simplifications (circular orbit, plane-parallel airmass, asymptotic key
rate, simplified accidentals model, dark-fibre / no-Raman assumption) are documented in
the code. Where independent literature values exist, physics validation targets are pinned
to them rather than to self-referential baselines: `docs/references/` records the digests
and evidence memos, most recently the consolidated time-bin review (Singh et al.,
arXiv:2507.08102), assessed at ADR-0003 ratification with no amendment required.

## Research & challenge alignment

This is a public research sandbox for quantum networking and secure communication. Its
themes align with a submission to the Quantum City Challenge (Securing Critical
Infrastructure), which proposed a Cognitive Quantum Network layer for adaptive,
trust-aware QKD. This repository develops the verified physics-layer foundation — computed
channel, decoy-state, and coherence models with monitored signals — on which such an
adaptive trust layer (Phase 2D) would be built.

## Licence & citation

Released under the **MIT Licence** — see [LICENSE](LICENSE). The code is free to use,
modify, and redistribute, including commercially, with attribution and without warranty.

If you use Quantum-QKD-Aero in published work, please cite it. Citation metadata is in
[CITATION.cff](CITATION.cff); GitHub renders it under "Cite this repository" in the
sidebar.
