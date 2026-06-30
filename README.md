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
- A pytest suite (**125 with the Qiskit extra, 104 without**) covering the physics and the
  honesty guards (turbulence-independence, geometry coupling, decoy bounds,
  PNS-invisible-to-QBER, fidelity arch, fibre-contract flow, provenance enforcement,
  determinism).

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

**Next / deferred:** schema hardening (L2–L5 type/range/constant/consistency validators, a
separable robustness layer — `docs/SCHEMA_HARDENING_2B.md`); a **Phase 2D trust/coherence
layer** reading the computed `PhysicsSignals` (QBER, decoy anomaly, CHSH/teleportation
margins, loss, secure-key rate) from behind the physics wall — no trust field inside the
physics modules; and **coherence-enhancement optimization** over the filtering levers
(window, bandwidth, field of view) against signal loss.

## Horizon

The three-axis model is built to absorb frontier link types without re-architecture:
quantum repeaters (beating the single-fibre loss wall via entanglement swapping),
MDI / twin-field QKD (beating the rate-distance limit via a central node), and
continuous-variable QKD (homodyne detection rather than photon counting). These are
**design targets the architecture accommodates, not implemented work.**

## Workflow

Run the simulator (writes `outputs/results.json` and the pass plot):

```
python src/qkd/run.py
```

Launch the dashboard, then open `http://localhost:8080`:

```
npm start
```

Recreate the Python environment:

```
python3 -m venv qkd_env
qkd_env/bin/python -m pip install -r requirements.txt
qkd_env/bin/python src/qkd/run.py
```

Package-style development with the dev extra, and the optional Qiskit validation path:

```
python -m pip install -e ".[dev]"   # then: pytest
python -m pip install -e ".[qiskit]"
```

## Code layout

Active code is in `src/qkd/`: `channel.py` (atmospheric/free-space medium), `fibre.py`
(fibre medium), `orbit.py`, `teleportation.py`, `chsh.py`, `bb84.py`, `eve.py`,
`coherence.py`, `mission.py` (composition), `provenance.py` (enforced origin tags),
`signals.py` (interface dataclasses), `run.py` (I/O), `schema.py`. The dashboard is in
`dashboard.js`; tests in `tests/`. `docs/INTERFACES.md` is the canonical contract;
`docs/architecture/` holds the ADRs; the development record
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
the code.

## Research & challenge alignment

This is a public research sandbox for quantum networking and secure communication. Its
themes align with a submission to the Quantum City Challenge (Securing Critical
Infrastructure), which proposed a Cognitive Quantum Network layer for adaptive,
trust-aware QKD. This repository develops the verified physics-layer foundation — computed
channel, decoy-state, and coherence models with monitored signals — on which such an
adaptive trust layer (Phase 2D) would be built.
