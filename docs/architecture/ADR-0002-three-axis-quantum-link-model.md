# ADR-0002 — The Three-Axis Quantum Link Model

- Status: Accepted (design frame for the v2 schema and channel expansion)
- Date: 2026-06-27
- Supersedes: the pre-fibre `V2_REQUIRED_KEYS` stub in `schema.py` (see §6)

## Context

Through Phase 2B the simulator modelled exactly one kind of link: a **satellite
free-space, point-to-point, decoy-BB84** channel. The fibre front-end (PR-Fibre-1)
proved that a second *medium* flows through the existing physics stack unchanged — the
`ChannelState.transmittance` representation contract held under substitution. That
success raises the real design question: not "satellite vs fibre," but **what is the
general shape of a quantum link such that the third, fourth, and fifth kinds also fit
without another schema migration?**

A schema that spans exactly the two links we have today would be a two-member version of
the decorative problem — correct now, re-migrated the moment a third link arrives. This
ADR defines the durable frame so that expansion is a declared extension point, not a
surprise.

## Decision — three orthogonal axes

A quantum link is described by **three independent dimensions**. They vary separately and
must not be flattened into a single hardcoded channel description.

### Axis 1 — Medium (how a photon gets from A to B)
The propagation substrate. Varies by loss model and noise model; reduces (today) to a
transmittance plus equipment/noise constants.
- **Members today:** `atmospheric` (free-space, orbital or terrestrial), `fibre`.
- **Plausible future members:** terrestrial free-space (line-of-sight, static geometry),
  underwater optical, integrated/on-chip waveguide.
- **Status: FULLY GENERALIZED.** Two real members exist; the abstraction is earned. The
  transmittance representation contract (`docs/INTERFACES.md`) is the medium interface:
  each medium computes transmittance differently, emits the same `ChannelState`, and
  reuses `DetectorParams` unchanged.

### Axis 2 — Topology (the shape of the link)
The structural arrangement of the channel. This is the axis a flat schema cannot
represent, because not every link is a single point-to-point hop.
- **Member today:** `point_to_point` (one channel between two endpoints).
- **Plausible future members:** `mdi` / `twin_field` (two channels meeting at a central
  measurement node — beats the rate-distance limit), `repeater_chain` (multi-segment link
  with entanglement swapping — beats the single-fibre loss wall), `entanglement_distribution`
  (a source in the middle distributing pairs to endpoints).
- **Status: NAMED, NOT GENERALIZED.** Exactly one member exists. Per the project's
  anti-speculative-generality discipline (cf. the deferred `BaseChannel`/`HardwareProfile`),
  topology is declared as an explicit single-valued field but its polymorphism is
  **deferred until a second topology is actually built**. A repeater chain is not a sweep
  along an axis — it is a composition over segments — so generalizing topology is a real
  future design step, flagged here, not pre-built.

### Axis 3 — Protocol (what is run over the link)
The key-generation / teleportation scheme and its rate math.
- **Member today:** `decoy_bb84` (with the QND/PNS Eve model and teleportation-fidelity
  path already built).
- **Plausible future members:** `mdi_qkd`, `twin_field_qkd`, `cv_qkd` (continuous-variable
  — different physics: homodyne detection, Gaussian modulation, not photon counting),
  `entanglement_swapping`.
- **Status: NAMED, NOT GENERALIZED.** One member exists; polymorphism deferred until a
  second protocol is built, same discipline as topology.

## A concrete link is a point in this space

Every emitted result declares which point it occupies:

| Link | medium | topology | protocol |
|------|--------|----------|----------|
| Satellite pass (today) | `atmospheric` | `point_to_point` | `decoy_bb84` |
| Fibre link (today) | `fibre` | `point_to_point` | `decoy_bb84` |
| *Future: metro repeater* | `fibre` | `repeater_chain` | `entanglement_swapping` |
| *Future: CV over fibre* | `fibre` | `point_to_point` | `cv_qkd` |

The schema **names all three axes explicitly** so a physicist reading a result sees
exactly which design point it occupies, and so a future contributor knows where a new
link plugs in.

## What v2 builds vs. what v2 defers

This is the honest line between physics-forward and speculative:

- **v2 GENERALIZES medium fully** — the channel representation is medium-neutral; a result
  declares `medium` and carries an independent profile axis (time for an orbital pass,
  length for a fibre sweep, etc.). Two members exist; the generality is earned.
- **v2 DECLARES topology and protocol explicitly but single-valued** — every result
  carries `topology` and `protocol` fields, but the schema assumes `point_to_point` /
  `decoy_bb84` shapes. The polymorphic machinery (segment graphs for repeaters, alternate
  rate math for CV/MDI) is **not built** until a second member of that axis exists.
- **The cost of naming is ~zero; the cost of building is deferred.** Naming an axis
  prevents the flat-schema trap (a future topology becomes "make `topology` polymorphic,"
  a scoped change, not a migration). Building an axis out with one member would be the
  speculative-generality trap this project has avoided throughout.

## §6 — Why the pre-fibre `V2_REQUIRED_KEYS` is superseded

`schema.py` carries a `V2_REQUIRED_KEYS` stub designed before fibre existed. It is
superseded by this ADR because it **flattens all three axes**: it hardcodes a single
`channel` section with `slant_range_km`/`elevation_deg` (medium- *and* topology-specific —
orbital point-to-point), a single `bb84` section, and a single `chsh` section (protocol-
specific). It cannot represent a fibre link honestly (orbital geometry is required), let
alone a repeater chain or an MDI midpoint (no topology axis at all). Adopting it would do
a large migration and still violate "span both," so the v2 schema is designed fresh
against this three-axis frame. The pre-existing stub's *good ideas* — exposing
`bb84`/`chsh`/`physics_signals` surface, and the eventual L2–L5 validation hardening
(`docs/SCHEMA_HARDENING_2B.md`) — are retained as a *separable depth dimension* added
later, not as the *shape* adopted now.

## Consequences

- The v2 schema (PR-B in the channel-generalization sequence) is designed against this
  frame: medium-general profile, explicit single-valued `topology`/`protocol` declarations.
- The composition layer (PR-A) generalizes to a medium-neutral profile core; the satellite
  pass and fibre sweep are two callers.
- Future frontier work (repeaters, MDI/twin-field, CV-QKD) has a declared home: a new
  medium is trivial; a new topology or protocol is a known, scoped "make this axis
  polymorphic" extension, documented here, rather than a schema migration.
- The wall still holds: no trust/cognitive field in physics (Phase 2D reads
  `PhysicsSignals`); this ADR is about the physics-channel design space only.
