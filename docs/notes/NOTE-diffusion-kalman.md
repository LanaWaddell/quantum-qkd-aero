# NOTE: Diffusion, Fokker–Planck, and the Kalman Digital Twin

**Status:** Reference note (non-normative) — **v2.1**. Lineage: v1 → v2 (2026-07-22, two-reviewer reconciliation, Appendix A) → v2.1 (2026-08-10, Echo full-packet review corrections, Appendix A addendum). v1 archived at `docs/notes/archive/NOTE-diffusion-kalman-v1.md`.
**Related:** ADR-0002 (physics/cognitive wall), ADR-0003 (composable channel interface)
**Scope:** Establishes the formal chain linking classical diffusion (Einstein 1905) to the covariance propagation used in the Kalman digital twin, and states the resulting limit on covariance-based adversary detection as a theorem rather than an implementation shortfall.

---

## 1. Purpose

This note records *why* covariance gating cannot detect a distribution-matched adversary — not as an artifact of the current gating design, but as a consequence of the observation model containing no distinguishing information. It then identifies the two routes by which detection reopens, and locates privileged perturbation among them.

The chain is: **Langevin SDE → Fokker–Planck density evolution → linear-Gaussian moment closure → discrete Kalman prediction.** Each arrow is an identity or a limit, not an analogy — with one deliberate exception flagged in §5.

**Scope boundary (classical vs. quantum).** Everything in this note concerns *classical telemetry authentication* — whether the twin can tell that classical link observables are being forged. It says nothing about, and places no limit on, the quantum layer's own security properties (QBER-based eavesdropping bounds, entanglement verification, the cryptographic security of the key). A Kalman observability limit is not a QKD security limit.

---

## 2. Langevin (physics layer)

Force balance with fluctuation–dissipation coupling:

```
m dv/dt = -γ v + F(t)
⟨F(t)⟩ = 0,   ⟨F(t) F(t')⟩ = 2 γ k_B T · δ(t - t')
```

The noise amplitude is pinned to the dissipation γ by temperature — it is not a free parameter. In the overdamped limit:

```
dx = √(2D) dW,    D = k_B T / γ = k_B T / (6π η r)   [Stokes–Einstein]
```

**Scope of fluctuation–dissipation:** the relation constrains *equilibrium thermal-noise contributions* associated with dissipation. Other channel effects — atmospheric scintillation (turbulent refractive-index fluctuations) and nonthermal dark-count mechanisms (tunneling, afterpulsing) — require their own physical models and are not set by FDT.

**Boundary note (ADR-0002):** the fluctuation–dissipation relation lives entirely in the physics channel; it must not be read as a statement about the trust layer. This note derives layer-crossing structure only at the level of shared mathematics, not shared state.

---

## 3. Fokker–Planck (paths → densities)

General Itô SDE `dx = f(x,t) dt + L dW`, dW of spectral density Q:

```
∂p/∂t = -∇·(f p) + ½ ∇∇ : (L Q Lᵀ p)
```

Free case (f = 0, LQLᵀ = 2D) reduces to the heat equation; delta initial condition gives a Gaussian of variance 2Dt, i.e. **⟨x²⟩ = 2Dt**.

Key property: the path is random, the density is deterministic. This is the precondition for filtering.

---

## 4. Moment closure (the bridge)

For linear dynamics `dx = A x dt + L dW`, Fokker–Planck preserves Gaussianity, so the density is fully specified by (m, P):

```
dm/dt = A m
dP/dt = A P + P Aᵀ + L Q Lᵀ
```

These are the Kalman–Bucy prediction equations. For linear-Gaussian systems, **Fokker–Planck propagation *is* the Kalman predict step**, rewritten. The update step is not Fokker–Planck: it is Bayesian conditioning of the predicted density on a measurement.

---

## 5. Discretization

Over step Δt (exact for time-invariant A; time-varying dynamics require the corresponding state-transition operator and integral):

```
F   = exp(A Δt)
Q_d = ∫₀^Δt exp(Aτ) L Q Lᵀ exp(Aτ)ᵀ dτ    [Van Loan matrix-exponential]

Predict:
m⁻_k = F m_{k-1}
P⁻_k = F P_{k-1} Fᵀ + Q_d
```

**Sanity anchor:** A = 0 (pure diffusion) ⇒ F = I, Q_d = 2D·Δt ⇒ P_k = P₀ + 2Dt. Einstein's 1905 result is the free-particle special case of the predict step.

Update step (no diffusion analog):

```
K   = P⁻ Hᵀ (H P⁻ Hᵀ + R)⁻¹
P⁺  = (I - K H) P⁻
```

Process noise adds uncertainty during prediction; measurement conditioning removes uncertainty during update. At steady state these contributions balance through the Riccati equation. (Note: prediction is not monotone inflation — stable dynamics can contract FPFᵀ faster than Q_d replenishes it, and per-step entropy need not increase. Strict inflation holds only in the A = 0 anchor case.)

**Structural analogy (the one deliberate analogy in this note):** the Riccati steady state is *structurally like* the Ornstein–Uhlenbeck equilibrium σ²/2θ between restoring drift and noise injection — but it is a balance of Q_d inflation against measurement contraction, not literally a restoring drift. Read in this spirit, it remains the natural formalism for the committed-reference / mast pattern: commitment = restoring force, drift pressure = noise, tolerated excursion = stationary variance.

---

## 6. The distribution-matched adversary as a theorem

**What "matched" must mean.** A Gaussian *random variable* at one time is determined by (m, P). A Gaussian *process* is determined by its mean function and its complete **two-time covariance kernel**. Matching the per-time marginals (m_k, P_k) is therefore *not* sufficient: an adversary running the wrong dynamics (wrong F, wrong Q_d split) with the right steady-state marginal produces *colored* innovations and is caught by a standard whiteness test.

> **Theorem (observation-law form).** If the adversarial and nominal hypotheses induce the same joint probability law over the complete observation history available to the detector, then no detector based on that history can distinguish them with power exceeding its false-positive rate. Equivalently: zero KL divergence between the two observation laws collapses every detector's ROC to the chance line (Neyman–Pearson).

In the linear-Gaussian case, equality of the observation laws is expressible through the full first- and second-order statistics — operationally, the adversary's output must render the Kalman **innovation sequence** indistinguishable from nominal:

- correct innovation mean;
- correct innovation covariance HP⁻Hᵀ + R;
- **white** temporal structure;
- Gaussian distribution;
- correct cross-correlations with all known inputs.

An adversary achieving all of this is not merely difficult to detect — it is **statistically indistinguishable under the stated observation model**. No residual statistic exists to test against. This follows from the structure of the observation law, not from any deficiency of the gating implementation.

Consequence: the current simulation result (twin raises forgery cost but cannot prove unforgeability) is the *expected* result. Note also that full matching is a harder adversarial task than matching one covariance matrix — the adversary must identify or emulate the nominal **observable input–output law** (equivalently, the innovation representation / full second-order statistics up to realization equivalence); it need **not** reproduce the honest system's internal state-space realization, since distinct realizations generate the same observable process. This remains a passive system-identification problem in principle, subject to observability, identifiability, sufficient excitation, sample length, and model-class assumptions.

### 6.1 The two routes to detection

Detection reopens by one of two structurally different moves:

**Route 1 — Enrich the passive observation model.** Higher-order / non-Gaussian residual statistics; nonlinear dynamics (breaking moment closure); temporal statistics beyond marginal covariance; additional modalities or trusted side information. These raise the adversary's identification burden *quantitatively* — they must match distributional structure beyond the first two moments (not "all moments": moment-matching determines the law only under moment-determinacy conditions; the lognormal is the classic counterexample) — but the task remains passive estimation, defeatable in principle by a sufficiently capable passive adversary.

**Route 2 — Change the information structure through intervention.** Private probes; dynamic watermarking; challenge–response measurements; randomized control inputs known only to the verifier. Crucially, intervention need not break linearity or Gaussianity: a private Gaussian watermark injected into a linear-Gaussian system leaves the augmented process exactly linear-Gaussian. What changes is *who knows what*. The detector's question shifts from "does this output resemble the expected passive distribution?" to "does this output contain the response causally associated with a particular private input?" — and the relevant statistic is a private probe/innovation **cross-correlation**, not a changed drift estimate. Matching that response is not solvable from passive observation, because the adversary cannot observe the probe.

This is where **privileged perturbation** does load-bearing work. It inverts the fluctuation–dissipation structure: instead of inferring noise from dissipation, it tests whether the system responds to a private stimulus as the true dynamics require. Because the augmented system stays linear-Gaussian, this route needs *no new estimator machinery* — the twin's existing innovation sequence plus one cross-correlation statistic is the whole detector. It is the cheapest route to implement, not the most exotic.

### 6.2 Attack-class scoping

The Route 2 guarantee is conditional on **attack class**, not universal. "The adversary cannot observe the probe" holds only if the attack severs the probe→observation path. Relevant classes: **replacement** (adversary substitutes its own dynamics — probe response absent; detected), **replay** (recorded past output — probe response absent; detected; this is the original watermarking result), **synthesis** (model-generated output — probe response absent unless the model includes the probe; detected), **relay / man-in-the-middle** (adversary passes through the true system's response — probe response *inherited for free*; not detected by this mechanism), and **partial-path compromise** (intermediate). The cost asymmetry holds against adversaries who *replace* the dynamics, not those who *relay* them.

This is the established territory of **physical / dynamic watermarking** in control-systems security: Mo & Sinopoli (replay-attack detection via private Gaussian excitation, chi-squared innovation detectors), Satchidanandan & Kumar (dynamic watermarking, arXiv:1606.08741), with later work (e.g. Hespanhol et al., arXiv:1703.07760) making explicit that detectability holds under specified attack and observability conditions. That literature quantifies the detection-power vs. probe-cost trade this note gestures at, and should be the citation anchor for any cost bound.

The honest boundary stands: raised forgery cost scaling with probe privacy — **not** unforgeability.

---

## 7. Takeaways for the build queue

- Covariance-only gating is provably insufficient against a matched adversary; do not treat improved gating as a path to detection.
- **First build item: innovation-whiteness testing.** Buildable now against the existing twin with no new interfaces. Scope of the claim it supports: whiteness testing strengthens the existing result by checking *temporal second-order structure*; only together with innovation-covariance and known-input cross-correlation tests (and distributional checks, if the claim is specifically Gaussian-law matching) does it support a full second-order matching claim. Report it as a temporal second-order diagnostic, not by itself as proof of complete second-order matching.
- Detection budget divides by route: Route 1 (higher-moment / non-Gaussian / nonlinear-response residual tests) and Route 2 (private-intervention tests tied to the privileged-perturbation threat model and the attack classes of §6.2).
- Route 1 power is **pass-limited**: higher-cumulant estimators have rapidly growing variance and samples arrive in finite contact windows. A per-pass detection-power budget (samples needed before, e.g., a kurtosis test has power against a given deviation) turns this into a sized work item, tied to the contact-window-extension analysis. For Route 2, the probe/innovation cross-correlation is the concrete statistic to size against probe energy, contact-window duration, operational disturbance, and probe secrecy.
- Any unforgeability claim in documentation must be scoped to (a) a probe-privacy assumption *and* (b) an attack class per §6.2, and stated as a cost bound, never as a guarantee.

---

## Appendix A — Reconciliation record (2026-07-22)

v1 was reviewed by two AI reviewers: Claude (Appendix R1 of v1, points R1.1–R1.6) and Echo (cross-review, full agreement with R1 plus additions). Both verdicts: retain and revise, not rethink — the derivational spine (§2–§5 chain) is sound. v2 folds in all agreed corrections. Disposition:

| Item | Found by | v2 disposition |
|---|---|---|
| Theorem overstated: marginals (m,P) ≠ process law; needs two-time kernel / innovation formulation | Claude (R1.1) | §6 restated; whiteness test noted |
| Observation-law / ROC-collapse form as the final theorem statement | Echo (refining R1.1) | Adopted as the theorem box in §6 |
| "not hard to detect" sentence inverted | Claude (R1.2) | Fixed in §6 |
| "Three assumptions" taxonomy wrong: intervention changes information structure, not the model class | Echo | Replaced by two-route taxonomy (§6.1) |
| Watermarked system stays linear-Gaussian ⇒ Route 2 needs no new estimator machinery | Claude (reconciliation) | Noted in §6.1 |
| Dynamic-watermarking literature anchor (Mo & Sinopoli; Satchidanandan & Kumar; Hespanhol et al.) | Claude (R1.3) + Echo (citations) | §6.2 |
| Probe-privacy claim conditional on attack class (replace vs. relay) | Claude (R1.4); attack-class enumeration per Echo | §6.2 |
| Predict step is not monotone inflation; entropy claim wrong in general | Echo | §5 rephrased (Riccati balance); anchor case retained |
| FDT scope over-extended (scintillation, dark counts) | Echo | §2 narrowed |
| FP ≡ Kalman applies to predict only; update = Bayesian conditioning | Echo | §4 scoped |
| Discretization exact only for time-invariant A | Echo | §5 caveat |
| OU comparison is an analogy, in tension with §1's "no analogies" | Claude (R1.6i) + Echo | §5 marked as the deliberate exception; §1 flags it |
| "Unbounded moment hierarchy" loose (moment determinacy) | Echo | §6.1 Route 1 caveat |
| Classical-telemetry vs. quantum-layer security scoping | Claude (R1.6ii) + Echo | §1 scope boundary |
| Detection power is pass-limited; tie to contact-window work | Claude (R1.5) | §7 |
| Innovation-whiteness testing as first build item | Echo (sequence step 2), prioritized in reconciliation | §7 |
| ADR-0002/0003 wall discipline verified intact | Claude (R1.6iii) + Echo | No change needed |

Echo's proposed research sequence (formalize observation laws → whiteness testing → define attack classes → typed private probe via ADR-0003 control surface → probe-response correlation per attack class → detection power vs. probe energy / window / disturbance / secrecy) is recorded here as the candidate work program for the privileged-perturbation direction; sequencing decisions belong to the build queue, not this note.

### v2.1 addendum (2026-08-10) — Echo full-packet review corrections

Two corrections from Echo's pre-LINK-1 full-packet review, verified and applied:

| Item | Found by | v2.1 disposition |
|---|---|---|
| "(A, LQLᵀ) identification" overstated: realization equivalence means only the observable input–output law must be matched; passive solvability conditional on observability/identifiability/excitation/sample length | Echo | §6 sentence replaced |
| Whiteness alone ≠ full second-order matching; needs innovation covariance + known-input cross-correlations (+ distributional checks for a Gaussian-law claim) | Echo | §7 first build item narrowed to "temporal second-order diagnostic" |

Preserved boundaries restated by the review (already present in v2, no change): replace/replay vs. live relay asymmetry (§6.2); classical-telemetry vs. QKD-security scope (§1). Optional implementation note recorded for later coding stages: prefer the Joseph-form covariance update for numerical robustness when the update step becomes code.
