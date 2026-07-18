# Evidence Memo — arXiv:2507.08102 vs. ADR-0003 Ratification Review

**Purpose:** Map evidence from the time-bin review (Singh et al., arXiv:
2507.08102v2, Oblak group / UCalgary IQST — see companion digest
`quantum-qkd-aero-ref-timebin-review-2507-08102.md`) onto the five sections
flagged for careful review before PI sign-off of ADR-0003, plus the
revisit / expansion / novel-concept findings from the 2026-07-17 review
session.
**Prepared by:** Claude (physics/architecture reviewer), from independent
full-text extraction of the paper. Alert-list scan: clean.
**Standing disposition:** Evidence input to the fresh-eyes read. Nothing here
requires amending ADR-0003 text before ratification; items are classified
as **confirms**, **resolves-deferred**, or **parked**.

---

## A. The five flagged ratification sections

### A1. §3.3.1 Composition rules table

**Verdict: strengthened; one deferred rule is now resolvable.**

- **`timing_jitter_s` (deferred: "estimator-owned or quadrature-composed;
  LINK-1 must choose").** Paper Eq. 28 gives the community's operational
  answer: independent temporal broadening sources compose **in quadrature**
  (∆τ_M = √(∆τ² + ∆τ_CD² + ∆τ_JD² + ∆τ_JT²)). This is variance addition for
  independent Gaussian-like broadening — physically principled, and now
  citable. **Recommendation:** LINK-1 adopts quadrature composition for
  independent jitter/broadening contributions, with the caveat that
  correlated contributions (e.g. shared clock) need declared structure —
  the same escape hatch `background_rate_hz` already has. This does not
  change ADR-0003 text; it discharges the deferred choice with evidence.
- **`misalignment_error` (deferred: documented low-order default allowed,
  no universal rule).** The paper supplies the DV time-bin physical model:
  X-basis error from DLI phase noise with QBER ∝ sin²(∆ϕ), and a complete
  phase-error budget (source drift Eq. 9; DLI path/wavelength Eq. 20;
  lock-laser transfer Eq. 23; all τ_el-scaled). **Recommendation:** the
  documented low-order default for the time-bin implementation is
  sin²(∆ϕ_total) with ∆ϕ contributions quadrature-combined — while keeping
  the ADR's refusal to bake a universal rule, since the model is
  encoding-specific (see A5/C3).
- **`afterpulse_prob` / `dead_time_s` (detector-model owned, non-additive).**
  Confirmed. The paper's detector treatment (gated InGaAs afterpulsing,
  µs dead times, SNSPD saturation >100 MHz) shows exactly the nonlinear,
  history/rate-dependent character the table quarantines. No change.
- **`background_rate_hz` (sum, unless declared correlated).** Holds. SRS
  coexistence noise (Eq. 16) enters as a background-rate contributor and the
  sum rule is correct — but the effect carries a **propagation-direction
  parameter** (co- vs. counter-propagating classical traffic changes the
  functional form). This is effect-internal structure, not a table change;
  note it as precedent that effect parameters may encode directionality
  without the composition algebra needing to.
- **Prospective stressors (parked, not ratification blockers):**
  (i) CV excess noise ε — position-dependent, already flagged as the
  prospective seventh row; the paper doesn't bear on it directly.
  (ii) **Non-local dispersion compensation** (paper §10): an effect applied
  to one arm of an entangled pair acts on the joint two-photon state —
  composition spanning two channels. Out of scope for point-to-point
  ADR-0003; becomes real when entanglement-based protocols (BBM92/E91) join
  the protocol axis. Park with the repeater items.

### A2. The wall: discipline vs. mechanical enforcement

**Verdict: indirectly supportive; no new risk identified.**

The paper's error-budget structure factors cleanly into source effects
(laser drift), channel effects (dispersion, SRS, turbulence), and
measurement effects (DLI phase, detector jitter) — mirroring the ADR's
source/channel/detector effect classes. More specifically, it confirms the
ADR's key estimator-stage claim: QBER contributions **do not exist at the
per-effect level**. The sin²(∆ϕ) term only becomes a QBER when composed
with basis choice and gain at the estimator; dark-count QBER depends on
composed gain. The physics literature and the ADR draw the same line.
Nothing in the paper suggests a case the wall's type-signature enforcement
would mishandle.

### A3. Recoherence vocabulary as a public-facing commitment

**Verdict: neutral, with one translation obligation.**

The paper never uses recoherence language; the community's observables are
**visibility / interference contrast**, QBER, and HOM visibility. The
retained-ensemble coherence vocabulary is internally coherent, but any
public-facing artifact (paper, proposal) will need an explicit translation
layer mapping the ADR's vocabulary onto these standard observables —
e.g. turbulence-induced DLI contrast loss (paper §4.2) is the community's
name for a phenomenon the recoherence framing would describe differently.
Ratify the vocabulary as-is; add the translation obligation to the LINK-6
validation-artifact scope rather than the ADR.

### A4. LINK-1 byte-identical and RNG acceptance criteria

**Verdict: unchanged in structure; enriched with concrete future targets.**

The byte-parity and hash-derived RNG stream criteria are orthogonal to
anything in the paper. What the paper adds is a set of **numerical
validation anchors** for later LINK stages (see digest §12): the 100 km
dispersion worked example (433 ps bin separation), the 6.45° and 3.6°
phase-error examples, the 50% WCP HOM cap, PMD negligibility thresholds,
and SRS directional asymptotics. Recommendation: record these as candidate
LINK-6 validation-curve targets now, so acceptance criteria for the physics
(as opposed to the plumbing) are pinned to independent literature values
rather than self-referential regression baselines.

### A5. Implications of the deferred fibre / PathProvider decision

**Verdict: the deferral was correct; the paper previews what LINK-1
evidence will show.**

The paper makes fibre a *richer* medium than the current attenuation-only
model: chromatic dispersion (length-proportional, feeds ∆τ_CD into Eq. 28)
and SRS coexistence noise (length- and direction-dependent) are first-order
and fibre-specific, with no free-space analogue. Two implications:

1. The fibre medium will need its own effect family, not just a different
   transmittance formula — supporting the ADR's instinct that PathProvider
   placement should wait for LINK-1 evidence rather than be guessed now.
2. The `GeometryProvider`-free-of-satellite-assumptions cost note in §9 of
   the ADR gains force: fibre effects are indexed by length and direction,
   not elevation/slant-range. Whatever LINK-1 chooses must let a
   length-indexed provider supply dispersion and SRS parameters without
   satellite vocabulary leaking in.

Additionally, the paper flags satellite-specific TBQ effects (platform
Doppler, motion-induced phase) that map to the already-planned LINK-3
hooks and the existing `frequency_offset_hz` sum rule — confirming that
row's adequacy for the deterministic part of Doppler.

---

## B. Session findings beyond the five flagged sections

### B1. Revisit-worthy (previous areas)

- **Fibre channel honesty:** at realistic bin widths and lengths, an
  attenuation-only fibre model omits the two effects the community treats
  as first-order (dispersion, SRS-under-coexistence). No current result is
  wrong — the ~190 km max-secure-distance stands as an attenuation-limited
  figure on the default illustrative fibre — but the LINK backlog should
  treat dispersion + coexistence noise as the fibre medium's LINK-3/LINK-4
  analogue of the satellite's Doppler/scintillation family.
- **Δt feasibility coupling validated:** the paper's gated-detection SRS
  mitigation and the τ_el > ∆τ_M constraint are precisely the
  physics-coupled feasibility the `ControlSpec.feasible(EffectiveLinkState)`
  design anticipates (composed jitter bounds the coincidence window).
  The design choice is independently confirmed by how experimentalists
  actually reason.

### B2. Expansion areas

- **MDI before repeaters (sequencing argument).** The paper states the
  MDI topology is architecturally the repeater topology minus quantum
  memory. MDI is therefore the *minimal* topology-axis second member:
  two channels converging on an untrusted partial-BSM node, exercising
  multi-channel composition and HOM/BSM machinery while staying memoryless
  and point-to-multipoint-free. It de-risks the parked repeater domain in
  the smallest earned step. Consistent with the second-member rule: not to
  be pre-built, but recorded as the preferred topology-axis candidate when
  that axis earns its second member.
- **COW-QKD** parked as a cheap DV protocol-family member (WCP substrate
  shared; new requirement: inter-pulse phase-coherence modelling).
- **LINK-5 detector realism** gains literature-grounded parameter envelopes
  (digest §5 table).
- **Qudit dimension** parked with a concrete cost law (2d−1 DLIs, 1/d
  detection efficiency).

### B3. Novel / theoretical openings

1. **Automated parameter-feasibility trade-space.** Paper §6 derives the
   feasible (∆τ, τ_el) region by hand; nothing in the review literature
   computes it. Exposing that region as a function of `EffectiveLinkState`
   via `ControlSpec.feasible` — validated against the paper's worked
   examples — is a novel simulator capability and a publishable artifact.
2. **Two-channel effect composition** (non-local dispersion compensation)
   as a future extension of the composition algebra — sibling of the CV
   position-dependence question. Parked.
3. **Encoding-conditional effects.** The paper's central physics argument
   is that channel effects are conditional on encoding (PMD irrelevant to
   time-bins; turbulence contrast loss and satellite Doppler specifically
   punitive for time-bins). The model is currently encoding-agnostic.
   **Do not add an encoding axis** (second-member rule); record the
   evidence question — "which implemented effects are encoding-conditional,
   and where would encoding-conditionality live if earned?" — in the
   parking lot alongside the expansion domains.

### B4. Local-relevance note

The review is authored by the Calgary experimental group (Oblak / IQST).
Reproducing its worked examples as validation targets creates a concrete,
citable bridge to local experimental capability for future proposals —
a low-cost continuation of the fibre-proposal direction that builds blocks
(per the standing post-proposal posture) without committing new scope.

---

## C. Disposition summary

| Item | Class | Action |
|---|---|---|
| Eq. 28 quadrature → `timing_jitter_s` | Resolves-deferred | LINK-1 adopts quadrature w/ correlated-structure escape |
| sin²(∆ϕ) → `misalignment_error` | Resolves-deferred | Documented low-order default, DV time-bin scope only |
| Afterpulse / dead-time quarantine | Confirms | None |
| SRS direction parameter | Confirms (+precedent) | Note effect-internal directionality; sum rule holds |
| Estimator-owned QBER | Confirms | None |
| Recoherence vocabulary | Neutral | Translation layer → LINK-6 scope |
| Byte/RNG criteria | Unchanged | Add digest §12 anchors as LINK-6 targets |
| Fibre deferral | Confirms | LINK-1 evidence = dispersion + SRS effect family |
| MDI ≅ repeater | Expansion | Preferred topology-axis second member (parked) |
| Non-local dispersion comp. | Novel (parked) | Parking lot, with repeaters |
| Encoding-conditionality | Novel (parked) | Parking lot as evidence question, not axis |
| Feasibility trade-space | Novel (active-adjacent) | Candidate LINK-6+ capability + validation bridge |

**Bottom line for sign-off:** the paper independently validates the shape of
every §3.3.1 decision it touches, discharges two deliberately deferred rules
with citable physics, and identifies no conflict with the ADR as written.
No amendment needed before ratification.

---

## D. Addendum (2026-07-17) — cross-review reconciliation

A parallel review of the same paper by a second AI reviewer (without ADR-0002/
0003 context) raised five items. Reconciled here after independent
verification against the paper text and the repo at commit `ab2de8e`
(fresh clone). Original memo body above is unchanged.

**D1. Teleportation-lane conditioning (their item 1) — accepted with
reduced severity and a different fix.** Verified against
`src/qkd/teleportation.py` and `mission.py`: the module maps Werner-p →
fidelity at the density-matrix level ((1+p)/2, singlet fraction (1+3p)/4,
classical bound 2/3; analytic/numeric/Qiskit cross-checked). It models no
photonic BSM at all — the fidelity is implicitly **conditioned on an ideal,
complete BSM over perfectly indistinguishable photons**, and that
conditioning is undeclared. Their "inconsistent with the WCP statistics"
framing overstates it: the teleportation lane (channel → background
coherence → effective Werner p → fidelity) and the decoy-BB84 WCP lane are
parallel estimators that exchange no numbers, so nothing is computationally
wrong today. But both emit into the same per-sample artifact and
`teleportation_margin` is a Phase 2D read signal, so an undeclared
conditioning is a real honesty gap: a reader could take the fidelity as
photonically achievable in the same WCP experiment. It is not — WCP caps
HOM visibility at 50% (paper Eq. 51, V_max = 0.5 for coherent light) and
linear-optics BSM resolves 2 of 4 Bell states.
**Fix: declaration, not replacement.** Add the conditioning statement to the
module docstring and (candidate) `run_metadata`; do *not* drop Eq. 51 into
the current lane — it is a state-quality diagnostic, and Eq. 51 is the
photonic-implementation model that belongs to a future MDI/BSM lane
(V_max keyed to source statistics, 2-of-4 success accounting). Eq. 51's
existence and content verified directly against the paper.

**D2. Doppler → phase → X-basis QBER (their item 3) — accepted; sharper
than this memo's original mapping.** The original memo mapped Doppler to
`frequency_offset_hz` (sum rule, LINK-3 hooks) and stopped. The missing
piece is the **estimator-stage map**: composed frequency offset ∆ν →
superposition phase error ∆ϕ = 2π·τ_el·∆ν (paper Eq. 9) → X-basis QBER via
the sin²(∆ϕ) model of A1. Scales linearly with bin separation (1 ns +
10 MHz drift → 3.6°). This is consistent with §3.3.1 as written (the field
composes by sum; the QBER mapping lives at the estimator, where the ADR
puts it) — record it as a LINK-3/LINK-6 estimator requirement.

**D3. Turbulence basis-dependence (their item 2) — equivalent content,
placement differs.** Same physics as this memo's encoding-conditionality
finding (B3.3). Their actionable framing: an X-basis QBER coupling from
spatial-mode distortion degrading interferometer contrast, distinct from
scalar transmittance. ADR-informed placement: a channel-effect contribution
into `misalignment_error` with a declared model — meaningful only once the
implementation's encoding assumption is pinned (see D4).

**D4. Encoding as an explicit axis (their item 5) — declined as stated,
middle path adopted.** Building encoding as a modeled axis now would
pre-build generalization ahead of evidence (second-member rule); their
recommendation is reasonable absent that context, and their RL-selects-
encoding-per-segment idea parks cleanly in the Phase 2D-era lot. But their
underlying observation earns a cheap honesty fix this memo had not
articulated: the paper shows satellite free-space records run on
polarization while time-bin owns fibre, and several paper effects
(DLI contrast loss, Doppler-phase) apply only to a time-bin implementation.
**Action: declare the current implementation's implicit encoding assumption**
(docs/record, candidate `run_metadata` field) so encoding-conditional
effects have a defined home when earned — a declaration, not an axis.

**D5. Section 6 consistency assertions (their item 4) — already covered**
(digest §12 anchors → LINK-6 targets); adding the time-bandwidth product
(∆τ·∆ν = 0.441 Gaussian) explicitly to the anchor list.

**Items they did not surface** (for calibration, not criticism — they
lacked project context): the §3.3.1 deferred-rule resolutions (A1), the
fibre-deferral implications (A5), the MDI ≅ repeater topology-axis
sequencing argument, non-local dispersion compensation, and the
feasibility-trade-space capability. Their extensions list (COW / MDI / HD)
otherwise matches §B2.

### Updated disposition rows

| Item | Class | Action |
|---|---|---|
| Teleportation-lane conditioning | Honesty gap (verified @ `ab2de8e`) | Declare ideal-BSM conditioning in docstring + record; Eq. 51 reserved for future MDI/BSM lane |
| Doppler → phase → QBER map | Resolves-gap (estimator stage) | LINK-3/LINK-6 estimator requirement (Eq. 9 + sin² model) |
| Implicit encoding assumption | Honesty gap | Declare in docs/record; axis question stays parked |
| Time-bandwidth product | Confirms | Added to LINK-6 anchor list |
