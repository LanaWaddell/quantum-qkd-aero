# ADR-0004: Adaptive-Coupling Tier and the Hybrid Cryptography Boundary

- Status: **Accepted** (ratified by Lana, PI, 2026-08-23)
- Date: 2026-08-23 (r3; r2 incorporated Echo/Codex fresh-eyes review `71bc2fd8722e2832b04e9ec08f51c356bd3629dbfaba1dd765fed13e4b4dbe63`; r3 applies the PI ratification-read round trip `f3a9f22289fce19bc88f84e138d5ac7d80ed459c4195ae944e5632356c57b6fc`, editorial only)
- Relates to: ADR-0002 (three-axis medium/topology/protocol model), ADR-0003 (composable link-effect pipeline)

## Context

ADR-0003 organizes channel effects into three tiers by causal origin: deterministic exogenous, stochastic exogenous, and protocol-endogenous. Two pressures now require structure that none of the three tiers can host without category error:

1. **Adaptive protocol behavior.** FSO/atmospheric operation (turbulence with millisecond-scale correlated fading) makes adaptation attractive: fade-gated post-selection, block sizing to the turbulence coherence time, contact-window-aware scheduling. Every such mechanism creates a feedback path — exogenous channel state → monitored observable → endogenous protocol or policy decision — that is not exogenous (the protocol created the dependence), not endogenous (it is driven by external state), and not deterministic. Placing it in any existing tier would blur the trust boundary those tiers implicitly encode: exogenous effects are Eve-attributable; endogenous effects are trusted-device territory.
2. **Hybrid QKD+PQC key establishment.** PQC never touches the quantum channel and therefore has no home in the channel taxonomy; forcing it in would repeat the same category error at a higher layer.

## Decision

### D1 — Fourth tier: adaptive coupling

A fourth architectural tier is added above the three ADR-0003 channel tiers. It owns every feedback path in which channel-state observables drive protocol or policy adaptation. Its defining contract:

- It enumerates the channel-state observables that adaptation is permitted to consume, with latency and trust annotations.
- All such observables are treated as adversarially shapeable (untrusted-side inputs). Any consumer of tier-4 outputs inherits this threat model.
- It hosts the monitoring/attribution function that classifies observed degradation (`environment_consistent` / `unexplained` / `adversarial_suspected` / `insufficient_evidence`) against committed environmental references, emitting single-authority, immutable attribution-evidence objects. Attribution verdicts are operational classifications, not proofs of cause or absence of attack: an `environment_consistent` verdict means only that the observation is compatible with the committed reference model; all channel-derived evidence remains adversarially shapeable unless an independently justified source is identified, and `insufficient_evidence`, stale, or missing attribution fails closed for high-assurance fallback.
- It is separately simulable: coupling logic must be testable against synthetic channel-state traces independent of the physics engine.

Turbulence itself remains a stochastic-exogenous process (enriched with correlation-time and fading-distribution parameters). Tier 4 owns only the coupling, never the process.

### D2 — Hybrid cryptography boundary

PQC and hybrid key establishment sit strictly above the QKD physics/post-processing pipeline, behind a `HybridKeyAndAssurance` boundary. Physical link evidence and cryptographic assurance evidence are separate streams that may be combined only at an explicit policy layer, never inside the physics model. The policy layer is a tier-4 client: its channel-state inputs (physical status, degradation attribution, key-buffer state) are untrusted-side observables, and fallback decisions driven by them are subject to tier-4's induced-degradation threat model — in particular, the physical-layer downgrade attack in which adversary-induced apparent degradation forces PQC-only operation.

## Consequences

- ADR-0003 is unmodified. Tier 4 is an extension; the §3.3.1 composition rules apply only within the three channel tiers.
- The physical-layer downgrade attack becomes a named, first-class scenario for policy-engine testing.
- The companion design note (`docs/architecture/pqc_hybrid_architecture.md`, v3.1) specifies the hybrid boundary's states, policy actions, schemas, and staged test program. It is companion material committed separately and is not part of this ratification.
- Entrainment/capture experimentation gains a formally specified venue: tier-4 coupling under a specified adversary. This connects to the Phase 2D trust layer at the ratified pattern level only; no substrate-level transfer is asserted, consistent with the second-member rule.

## Verification

This ADR is independently verifiable from its own text plus ADR-0003: D1's contract makes no claim requiring external evidence, and D2 asserts a boundary, not an implementation. Implementation claims live in the companion note and are staged there.
