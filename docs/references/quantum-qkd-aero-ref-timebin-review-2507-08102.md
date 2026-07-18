# Reference Digest — Time-Bin Photonic QI Review (arXiv:2507.08102v2)

**Status:** Reference digest (paper proxy). The source PDF (~112 MB) exceeds the
project-upload limit; this digest stands in for it in project knowledge.
**Source:** Singh, Sethia, Esmaeilifar, Valivarthi, Sinclair, Spiropulu, Oblak,
"Photonic quantum information with time-bins: Principles and applications,"
arXiv:2507.08102v2 [quant-ph], v2 dated 2 Jul 2026. 114 pages, review article.
**Provenance note:** Lead group is **Oblak / UCalgary IQST** (with Caltech and
Harvard co-authors) — the local Calgary experimental community. Reproducing this
review's worked examples is a natural validation bridge to that group.
**Verification note:** Digest prepared from independent full-text extraction of
the uploaded PDF (2026-07-17). All numbers below were read from the extracted
text, not recalled from memory. Alert-list scan of the full text: clean (no
AI-directed content, no injection patterns).
**Scope of this digest:** condensed technical claims and equation forms in our
own words, organized for QKD-Aero use. For verbatim context, consult the arXiv
source directly.

---

## 1. Why this paper matters to QKD-Aero

It is the community's consolidated statement of time-bin (DV) link physics:
which channel/detector effects are first-order, how they compose, and how they
bound design parameters. Several of its results bear directly on ADR-0003
§3.3.1 composition rules (notably the quadrature composition of temporal
broadening) and on the LINK-3/LINK-5 effect families. See companion memo
`quantum-qkd-aero-adr0003-evidence-memo-timebin-review.md`.

---

## 2. Sources and state preparation (paper §3)

- Coherent state |α⟩ in Fock basis; photon-number statistics Poissonian:
  p(n|µ) = µⁿe^(−µ)/n!, with µ = |α|² the mean photon number and ∆n = √µ.
  Weak-coherent pulses (WCP) approximate qubits only for µ ≪ 1; multi-photon
  fraction is the PNS exposure (this is the physics already under the repo's
  decoy machinery).
- TBQ generation: pulsed laser (fixed pulse width) vs. CW laser + intensity/
  phase modulators (adjustable width; needs RF chain bandwidth — e.g. 100 ps
  pulses need > 20 GHz Nyquist-limited modulator chain). Single-photon sources:
  quantum dots (two-Raman scheme), SPDC/SFWM probabilistic pairs.
- Source coherence: TBQ phase error from source frequency inaccuracy
  (**Eq. 9**): ∆ϕ_s = 2π·τ_el·√(∆ν_d² + ∆ν_l²) — linewidth ∆ν_l plus drift
  ∆ν_d, scaling **linearly with time-bin separation τ_el**.

## 3. Fibre transmission (paper §4.1)

Four first-order fibre effects for time-bins:

**Attenuation (§4.1.1).** µ_out = µ_in·e^(−αL); α_dB = 4.343α; minimum
≈ 0.2 dB/km near 1550 nm (SMF-28). Matches the repo's 10^(−αL/10) transmittance.
Repeater-less links limited to a few hundred km by dark-count SNR floor.

**Chromatic dispersion (§4.1.2).** Temporal broadening ∆T = L·β₂·∆ω = L·D·∆λ;
D ≈ 17 ps/(nm·km) at 1550 nm, ≈ 1 ps/(nm·km) near 1310 nm for SMF-28.
Broadening degrades bin orthogonality → QBER. Compensation options: DCF,
chirped fiber Bragg gratings (6–10 dB insertion loss), pre-compensation at
Alice before attenuation, dispersion-shifted fibre, and **non-local dispersion
compensation** for entangled pairs (negative dispersion applied to one photon
compensates the pair — see §10 below; architecturally significant).

**Polarization mode dispersion (§4.1.3).** σ_T ≈ D_p·√L with
D_p ≈ 0.1 ps/√km (modern fibre) → ~1 ps per 100 km. Negligible vs. chromatic
dispersion for pulses > 10 ps. **Time-bin encoding is inherently insensitive to
PMD** — this is a core encoding-conditional claim (an effect that exists for
polarization qubits and not for TBQs).

**Spontaneous Raman scattering, SRS (§4.1.4).** Coexistence noise from
classical channels sharing the fibre. **Eq. 16 (direction-dependent):**
- Co-propagating: P_SRS,co = P₀·β_f·L·e^(−αL)
- Counter-propagating: P_SRS,counter = (P₀·β_b/2α)·[1 − e^(−2αL)]
Backward scattering dominates in long spans. Mitigations catalogued: launch-
power minimization, propagation-direction choice, wavelength planning
(anti-Stokes side favoured; O-band quantum + C-band classical common; shifting
the quantum channel by tens of nm can change noise by an order of magnitude —
e.g. 1290 nm markedly quieter than 1310 nm against a 1550 nm classical
channel), narrow-band spectral filtering, **temporal filtering via gated
detection windows** (maps to the repo's coincidence-window control Δt),
coherent filtering, fibre cooling (impractical), orthogonal-polarization
launch. Zischler et al. semi-analytical model adds four-wave mixing, spatial
crosstalk, Rayleigh backscatter for SDM fibres.

## 4. Free-space and satellite transmission (paper §4.2)

- Vacuum free-space loss scales ~1/r² (beam divergence) vs. exponential in
  fibre — the familiar satellite motivation.
- Atmospheric effects: turbulence (beam wander/spread/distortion), absorption,
  weather, background light. Spatial-mode distortion forces multimode coupling.
- **Encoding-specific:** spatial-mode distortion degrades the interference
  contrast of DLI-based superposition measurement — a time-bin-specific
  penalty beyond raw transmittance. Multimode time-bin analyzers are the
  countermeasure (Jin et al.: BB84 over 1.2 km turbulent channel, 138 bit/s).
- Reference demos: 144 km max horizontal atmospheric link; RFI-QKD over 2 km
  at ~1% QBER; 40 kbps over 500 m day/night horizontal links; single-photon
  interference of TBQs retro-reflected from a satellite at up to ~5000 km with
  **67% visibility**; satellite QKD to 12,900 km (polarization).
- **Satellite-specific for TBQs:** platform-motion phase shifts and Doppler
  are called out as particularly impactful for time-bin encoding (temporal
  jitter + phase sensitivity). Directly relevant to LINK-3 Doppler hooks and
  the existing `frequency_offset_hz` field.

## 5. Detection and measurement (paper §5)

**Detector parameter envelopes (§5.1, §12.2):**

| Detector | Efficiency | Jitter | Dead time | Dark counts | Notes |
|---|---|---|---|---|---|
| Si-SPAD | ~90% | ~40–50 ps | ~40 ns | <10 cps | 300–1100 nm only (no C-band) |
| InGaAs-SPAD | ~30% | ~100 ps | ~µs | higher | 900–1700 nm; gated; afterpulse-prone |
| SNSPD | >90% | <20 ps (few-ps best) | — | <1 cps | 0.8–2 K; saturation >100 MHz |

The Outlook frames **SNSPDs as the enabling technology** that made time-bins
the leading terrestrial encoding (C-band + 0.2 dB/km + high-efficiency
low-jitter detection). LINK-5 realism defaults can cite these envelopes.

**Z-basis measurement:** arrival-time histogram against a reference clock
(TDC). **X/Y-basis:** delay-line interferometer (DLI) imposes delay τ_el so
early/late interfere; alternatives are quantum-memory-assisted delay (§5.3),
conversion to polarization (§5.4), reference-state interference (§5.5).

**DLI phase stability (§5.2.4) — the X-basis error budget:**
- Phase through a DLI: ϕ = 2πnL̃/λ_Q (**Eq. 18**); displacement from δn, δL̃,
  δλ_Q (**Eq. 19**); practical combined form
  ∆ϕ = (2π/λ_Q)·√((∆L)² + (L/λ_Q·∆λ_Q)²) (**Eq. 20**).
- **QBER contribution follows sin²(∆ϕ)** — quadratic for small ∆ϕ. This is the
  physical model behind the DV time-bin misalignment term.
- Reference-laser locking transfers the lock laser's wavelength drift into
  quantum-signal phase error (**Eq. 23**, quadrature of the two drift terms).
  Worked example: L = 30 cm (τ_el = 1 ns), 0.1 pm drift on both lasers →
  ∆ϕ_Q ≈ 6.45° projection error. Mitigation: share one lock laser across the
  preparation and measurement DLIs (common-mode cancellation).
- Locking schemes: single-colour PID (phase-dependent sensitivity, fringe
  ambiguity), two-colour I/Q locking (uniform sensitivity, full [0, 2π]),
  frequency-shifted locking, single-photon-detection locking, passive
  temperature-stabilized commercial DLIs, thermally-insensitive hybrid
  hollow-core/SMF designs.

**Characterization (§5.6):** QST, fidelity, visibility measurements.

## 6. Parameter selection — the design trade-space (paper §6)

The section is effectively a hand-derived feasibility analysis for (∆τ, τ_el):

- **Time-bandwidth product (Eq. 27):** ∆τ·∆ν_τ = c₀ (0.441 Gaussian, 0.886
  rectangular). Couples temporal width to spectral width, hence to filter
  bandwidths, memory bandwidth, and HOM spectral indistinguishability.
- **Lower bound on τ_el — orthogonality (Eq. 28):** measured bin width
  composes **in quadrature**:
  ∆τ_M = √(∆τ² + ∆τ_CD² + ∆τ_JD² + ∆τ_JT²)
  (intrinsic width, chromatic-dispersion broadening, detector jitter,
  time-tagger jitter). Requirement τ_el > ∆τ_M.
  **Worked example (validation target):** 100 ps Gaussian at 1550 nm over
  100 km SMF (17 ps/nm·km) → 160 ps after dispersion; with 50 ps detector +
  30 ps tagger jitter → ∆τ_M = 170 ps; for 0.01% bin overlap take
  τ_el = 6σ = 2.55·∆τ_M = **433 ps**.
- **Upper bound on τ_el — phase stability:** Eq. 9 source phase error and DLI
  path stability both scale with τ_el (numeric anchor: 1 ns bins with 10 MHz
  source drift → ≥ 3.6° phase error). Spin-photon entanglement adds a π-pulse
  floor: τ_π < τ_el.
- Table 2 (paper) summarizes: bin width bounded below by preparation
  bandwidth / emitter lifetime / memory bandwidth, above by τ_el and filter
  bandwidth; separation bounded below by ∆τ_M and τ_π, above by source
  coherence and phase stability.

**QKD-Aero significance:** this constraint chain is exactly what the
`ControlSpec.feasible(EffectiveLinkState)` mechanism is designed to encode —
an automated version of this section is a novel simulator capability.

## 7. Entanglement, HOM, BSM (paper §7–8)

- **SPDC time-bin entanglement (Eq. 29):** pump superposition
  (|e⟩+e^{iϕ}|l⟩)/√2 down-converts to (|ee⟩+e^{iϕ}|ll⟩)/√2 (signal/idler);
  pair efficiency ≲ 10⁻⁶ per pump photon. Also SFWM, quantum dots, optical
  switches; GHZ states by interference + post-selection.
- **HOM (§8.1):** two-photon interference on a 50:50 BS; visibility
  V = (C_max − C_min)/C_max quantifies indistinguishability.
  **HOM visibility ceiling is set by photon statistics (Eq. 51 context):
  V_max = 1 (true single photons), 0.5 (coherent/WCP), 0.33 (thermal).**
- **Eq. 51 — first-principles HOM coincidence probability for TBQ
  superposition inputs:** Pc = 1 − V_max·[three Gaussian temporal-overlap
  terms at t = −τ_el, 0, +τ_el (central full-overlap dip full-weight, the
  two early–late/late–early side dips half-weight)]·e^{−∆τ²(ω₁−ω₂)²}, as a
  function of relative delay t, bin separation τ_el, bin width ∆τ, and
  spectral detuning. HOM-dip width = √2 × input pulse width and is
  **independent of detector jitter** (cross-correlation, not single-event
  timing). *Prefactor caution: verify exact coefficients against the arXiv
  source before implementation — this digest's extraction had minor layout
  garbling on Eq. 51's fractions; the structural form and V_max values are
  confirmed.* This is the designated photonic-layer model for any future
  MDI/BSM lane, with V_max keyed to source statistics.
- **BSM (§8.2):** linear-optics partial BSM discriminates |ψ±⟩ only — the
  machinery MDI-QKD, swapping, and repeaters all share.

## 8. Qudits and time-energy entanglement (paper §9–10)

- **Qudit scaling law (§9.2–9.3):** measuring d-dimensional phase states needs
  **2d − 1 DLIs** and detection efficiency falls as **1/d** — the concrete
  cost model if dimension ever becomes a protocol parameter. HD states are
  more noise-tolerant (higher QBER thresholds) at implementation-complexity
  cost.
- **Time-energy entanglement (§10):** Franson-type; CW pump coherence time
  bounds pair emission-time uncertainty while energy sum is sharp. Continuous
  time/energy variables that **discretize into time-bin or frequency-bin
  entanglement** — the conceptual bridge object between the DV branch and
  continuous-variable structure. Characterized via Franson interferometry.
- **Non-local dispersion compensation:** dispersion applied to one arm of an
  entangled pair compensates the joint two-photon wavepacket — a channel
  effect whose composition spans two channels (breaks per-channel locality;
  parked architectural question for entanglement-based protocols).

## 9. QKD protocols with TBQs (paper §11.1)

- **BB84 (time-bin):** mature across integrated, field-deployed, and long-haul
  fibre; demos include 2.5 GHz clocked systems, three-state BB84 field trial
  (21 dB channel, 3.4 kbit/s), 7 km free-space link, on-chip LiNbO₃ over
  deployed fibre, 120 km with telecom quantum-dot source.
- **COW:** WCP sequence in {|e⟩, |l⟩, |+⟩}; Z-basis keys, X-basis
  inter-pulse coherence monitoring defeats PNS; simple transmitter,
  interferometric X-monitor is the hard part. Demos beyond 300 km / >50 dB /
  multi-GHz clocks; modulator-free variants; finite-key and zero-error attack
  analyses exist. (Candidate cheap third DV protocol-family member; shares the
  WCP substrate; needs inter-pulse phase-coherence modelling.)
- **E91 / BBM92 (entanglement-based):** fibre TBQ demos exist, including
  four-user BBM92 from a single SPDC source via spectral multiplexing.
  Inherently repeater-compatible.
- **MDI-QKD (§11.1.4):** both parties send BB84 states to an untrusted
  central node performing a partial BSM; kills all detector side channels.
  Record 404 km (ultra-low-loss fibre); metropolitan star-topology field
  demos; 303 km with source-uncertainty hardening; 19.2 km free-space with
  adaptive optics. **Most MDI implementations use time-bins** (fibre
  depolarization rules out polarization).
- **HD time-phase QKD:** BB84-like with qudits; urban-fibre 2D/4D demos;
  limited by the 2d − 1 DLI cost above.

## 10. Networks, repeaters, outlook (paper §11.4, §12)

- Repeater protocol structure: segment the link, entangle adjacent nodes via
  probabilistic BSM, swap outward, memories synchronize; converts exponential
  loss scaling to polynomial. Full-scale repeaters remain unrealized;
  elementary demos exist on NV/SiV centers and trapped ions with TBQs.
- **MDI topology ≅ repeater topology** (stated explicitly in the Outlook):
  an untrusted BSM node between users is the repeater node minus the memory.
  Sequencing implication for QKD-Aero: MDI is the minimal topology-axis
  extension exercising two-channel composition + BSM, memoryless.
- Multiplexed time-energy entanglement serving **simultaneous** time-sync +
  QKD over 120 km (Xiang et al.) — one entangled substrate, parallel network
  functions (Phase 2D resonance: one physical layer, multiple higher-layer
  services).
- Carrier-grade quantum-communication infrastructure spanning >10,000 km
  reported; integrated photonics as the transceiver path; standardization
  still immature.
- Outlook emphases: SNSPDs as the enabling technology; integrated photonics
  (large birefringence/dispersion platforms favour time-bins over
  polarization/frequency encoding); light-matter interfaces mostly prefer
  time-bins (polarization-dependent atomic interactions); HD encoding as the
  capacity path; MDI as the near-term testbed protocol.

---

## 11. Quick map — paper section → QKD-Aero artifact

| Paper | QKD-Aero touchpoint |
|---|---|
| Eq. 28 quadrature broadening | ADR-0003 §3.3.1 `timing_jitter_s` deferred rule → quadrature branch now literature-backed |
| §5.2.4 sin²(∆ϕ) QBER, Eqs. 9/19/20/23 | `misalignment_error` documented low-order default (DV time-bin case) |
| §4.1.2 dispersion | Fibre-medium effect family (currently attenuation-only); feeds ∆τ_CD into Eq. 28 |
| §4.1.4 SRS Eq. 16 | Coexistence-noise effect → `background_rate_hz` (sum rule holds); direction-dependent internal parameter |
| §5.1 detector envelopes | LINK-5 realism defaults (afterpulse/dead-time non-additivity confirmed) |
| §4.2 satellite Doppler/phase | LINK-3 Doppler hooks; `frequency_offset_hz`; encoding-conditional visibility loss |
| §6 / Table 2 constraint chain | `ControlSpec.feasible` automation target (novel capability) |
| §8 HOM 50% WCP cap + Eq. 51 | Verifiable invariant + photonic BSM model for future MDI/BSM lane; also the declared conditioning gap on the current teleportation lane (see memo addendum) |
| Eq. 9 (∆ϕ = 2π·τ_el·∆ν) as estimator map | Composed `frequency_offset_hz` (incl. Doppler) → phase error → X-basis QBER at estimator stage (LINK-3/LINK-6) |
| §11.1.4 + §12.2 MDI ≅ repeater | Topology-axis sequencing: MDI before repeaters |
| §10 non-local dispersion comp. | Parked: two-channel effect composition (entanglement-based protocols) |
| §9.3 qudit cost (2d−1, 1/d) | Parked: dimension as protocol parameter |
| §11.1.2 COW | Parked: cheap DV protocol-family member on WCP substrate |

## 12. Validation targets extracted (for future LINK acceptance tests)

1. 100 ps @ 1550 nm, 100 km SMF, D = 17 ps/nm·km → 160 ps broadened;
   + 50 ps/30 ps jitters → ∆τ_M = 170 ps; τ_el(0.01% overlap) = 433 ps.
2. τ_el = 1 ns, ∆ν_d = 10 MHz source drift → ∆ϕ_s ≥ 3.6° (Eq. 9).
3. L = 30 cm DLI, dual 0.1 pm lock/source drift → ∆ϕ_Q ≈ 6.45° (Eq. 23).
4. WCP HOM visibility ≤ 50%; single-photon source → up to 100%.
5. PMD: σ_T ≈ 1 ps over 100 km (D_p = 0.1 ps/√km) — confirm negligibility
   threshold vs. chromatic dispersion for pulses > 10 ps.
6. SRS Eq. 16 asymptotics: counter-propagating noise saturates at
   P₀β_b/2α for αL ≫ 1; co-propagating peaks then decays with L.
