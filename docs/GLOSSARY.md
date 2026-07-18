# Quantum-QKD-Aero — Glossary

**Authority:** ADR-0003 §6 (binding vocabulary) and ADR-0002 (three-axis
model). This file restates the binding terms for lookup and defines the
community-translation boundary for public-facing artifacts. Where this file
and a ratified ADR disagree, the ADR wins; fix this file.

---

## 1. Binding internal vocabulary (ADR-0003 §6)

**The precise claim.** The substrate does **not** increase the coherence of
an already-accepted quantum state. It increases the coherence of the
**retained ensemble** by changing the acceptance rule and the physical
filtering conditions.

**The coherence ladder** — three distinct things loose language conflates:

1. **Coherence recovery by post-selection** (improving the accepted
   ensemble via selection/filtering). *In scope now (LINK).*
2. **Recoherence** (restoring the individual physical state on a single
   carrier). *Not expressible in this substrate, and not claimed.*
3. **Entanglement concentration** (purification/distillation across
   multiple resources). *Topology-axis future (repeater members).*

**The rule:** documentation, papers, and proposals must not describe rung 1
as "recoherence" (rung 2) or as entanglement concentration (rung 3). The
honest vocabulary is *coherence recovery by post-selection* / *changing the
retained ensemble* (now) vs. *recoherence operations* (topology-axis
future).

**Related binding terms.**
- **`p_eff`** — effective Werner parameter of the retained ensemble after
  background dilution and filtering.
- **Background dilution** — S/(S+B) reduction of ensemble coherence from
  accidental/background coincidences.
- **`EffectiveLinkState`** — composed, effect-pipeline-derived link state;
  the construction bridge between channel effects and estimators
  (ADR-0003 §3.4).
- **Controls** — explicit declared inputs (e.g. coincidence window Δt,
  filter bandwidth, FOV) with mandatory auditability and feasibility
  coupling to `EffectiveLinkState` (ADR-0003 §3.6).
- **Estimator-stage observables** — quantities (e.g. QBER, SKR) that exist
  only after composition; never per-effect fields.

---

## 2. Community translation (public-facing artifacts)

This section is an architectural boundary, not a communication convenience.
The internal vocabulary optimizes conceptual consistency across
Quantum-QKD-Aero, Phase 2D, and future research directions; the community
vocabulary optimizes interoperability with the broader quantum
communication field. Each is authoritative in its own scope — internal
vocabulary is binding inside the repo, ADRs, and the Development Record
(ADR-0003 §6); community vocabulary leads on public surfaces — and the
explicit mappings below are the declared crossing between them, so that
neither vocabulary needs to displace the other in its own domain. This is
the same wall pattern as ADR-0002, applied at the terminology layer.

Papers, proposals, and talks report through the mappings below. Reference
for community usage: Singh et al., arXiv:2507.08102 (consulted at ADR-0003
ratification; see
`docs/references/quantum-qkd-aero-ref-timebin-review-2507-08102.md`).

**The bridge identity.** Under the Werner model the translation is exact,
not approximate: interference visibility **V = p** (hence V_eff = p_eff),
fidelity **F = (1+V)/2**, CHSH **S = 2√2·V**, and X-basis
**QBER = (1−V)/2**. Public artifacts report p_eff as visibility via this
identity — one methods-section sentence, no conceptual translation.

| Internal (binding) | Community term | Mapping |
|---|---|---|
| Retained-ensemble coherence, `p_eff` | Interference visibility V, fringe contrast | Identity: V = p_eff |
| Coherence recovery by post-selection (ladder rung 1) | Temporal/spectral filtering; gated detection; background rejection; SNR improvement | Same operation; community frames as noise rejection, never as coherence recovery |
| Recoherence (ladder rung 2 — **not claimed**) | *(no standard community term)* | Reserved for future work; forbidden for rung-1 operations per ADR-0003 §6 |
| Entanglement concentration (ladder rung 3 — topology-axis future) | Purification / distillation | Direct match |
| Background dilution S/(S+B) | Signal-to-noise ratio; coincidence-to-accidental ratio (CAR) for pair sources | Same physics; CAR is the pair-source convention |
| `misalignment_error` | Optical QBER contribution | QBER_X = (1−V)/2 ≡ sin²(∆ϕ) low-order model |
| Effect pipeline / `EffectiveLinkState` | Channel impairments / link budget | Formalized version of the informal community concept |
| `frequency_offset_hz` | Spectral detuning; Doppler shift | Direct |
| Coincidence window Δt; transmittance η; timing jitter | Same terms | No translation needed |

**Usage rule.** Internal artifacts use internal vocabulary for cohesion
with the coherence ladder and the Phase 2D bridge; public artifacts lead
with community terms and may introduce internal terms only alongside their
mapping. Because the two surfaces meet only through the bridge identity and
this table, future vocabulary changes on either side stay cheap: update the
mapping, not the other domain.
