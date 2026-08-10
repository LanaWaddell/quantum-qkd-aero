# NOTE: Diffusion, Fokker–Planck, and the Kalman Digital Twin

**Status:** Reference note (non-normative)
**Related:** ADR-0002 (physics/cognitive wall), ADR-0003 (composable channel interface)
**Scope:** Establishes the formal chain linking classical diffusion (Einstein 1905) to the covariance propagation used in the Kalman digital twin, and states the resulting limit on covariance-based adversary detection as a theorem rather than an implementation shortfall.

---

## 1. Purpose

This note records *why* covariance gating cannot detect a covariance-matched adversary — not as an artifact of the current gating design, but as a consequence of Gaussian sufficiency. It then identifies the three assumptions whose relaxation reopens detection, and locates privileged perturbation among them.

The chain is: **Langevin SDE → Fokker–Planck density evolution → linear-Gaussian moment closure → discrete Kalman prediction.** Each arrow is an identity or a limit, not an analogy.

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

**Boundary note (ADR-0002):** the fluctuation–dissipation relation lives entirely in the physics channel. It sets noise magnitudes (detector thermal noise, dark counts, scintillation); it must not be read as a statement about the trust layer. This note derives layer-crossing structure only at the level of shared mathematics, not shared state.

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

These are the Kalman–Bucy prediction equations. For linear-Gaussian systems, **Fokker–Planck propagation *is* Kalman covariance propagation**, rewritten.

---

## 5. Discretization

Over step Δt:

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

Predict inflates covariance (diffusion, entropy up); update contracts it (measurement). Steady state balances the two — structurally the Ornstein–Uhlenbeck equilibrium σ²/2θ between restoring drift and noise injection. This is the natural formalism for the committed-reference / mast pattern: commitment = restoring force, drift pressure = noise, tolerated excursion = stationary variance.

---

## 6. The covariance-matched adversary as a theorem

A linear-Gaussian process is **completely determined** by (m, P). An adversary that matches both is not hard to detect — it induces *the same distribution*. No residual statistic exists to test against.

> **Claim.** Covariance gating cannot detect a covariance-matched adversary. This follows from Gaussian sufficiency, not from any deficiency of the gating implementation.

Consequence: the current simulation result (twin raises forgery cost but cannot prove unforgeability) is the *expected* result. Detection requires breaking one of three assumptions:

1. **Non-Gaussianity** — higher cumulants (skew, kurtosis) carry information the covariance does not. The adversary must then match an unbounded moment hierarchy, not one matrix.
2. **Nonlinearity** — nonlinear f breaks moment closure; the adversary must replicate the full density.
3. **Intervention** — an intervention perturbs the **drift f**, not the noise covariance. Matching a covariance is an *estimation* problem solvable from passive observation; matching the response to a private probe is not, because the adversary cannot observe the probe.

Assumption (3) is where **privileged perturbation** does load-bearing work. It inverts the fluctuation–dissipation structure: instead of inferring noise from dissipation, it tests whether the system responds to a private stimulus as the true dynamics require. This yields a cost asymmetry scaling with probe privacy — **not** unforgeability. The honest boundary stands: raised forgery cost, no proof of unforgeability.

---

## 7. Takeaways for the build queue

- Covariance-only gating is provably insufficient against a matched adversary; do not treat improved gating as a path to detection.
- Detection budget should be spent on (a) higher-moment / non-Gaussian residual tests, (b) nonlinear-response tests, and (c) private-intervention tests — with (c) tied to the privileged-perturbation threat model.
- Any unforgeability claim in documentation must be scoped to a probe-privacy assumption and stated as a cost bound, never as a guarantee.

---

## Appendix R1 — Review commentary (Claude, 2026-07-22)

*Status: commentary only; body above unchanged. Cross-review by Echo pending.*

**Overall.** The derivation chain checks out at every arrow: the fluctuation–dissipation normalization (§2), the FP → Kalman–Bucy identity for linear dynamics (§4), the Van Loan discretization and the A = 0 sanity anchor (§5). Framing the detection limit as a consequence of Gaussian sufficiency rather than a gating deficiency is the right move for the build queue. Points below are ordered by importance.

**R1.1 — The theorem needs a sharper definition of "covariance-matched."**
§6 states a linear-Gaussian process is "completely determined by (m, P)," but the per-time *marginals* (m_k, P_k) do not determine the process law. A Gaussian process is determined by its mean function and its full **two-time covariance kernel**. An adversary matching only the steady-state marginal P while running the wrong dynamics (wrong F, wrong Q_d split) produces *colored* innovations and is caught by a standard whiteness test. Suggested restatement: an adversary matching the full second-order statistics — equivalently, one whose output renders the Kalman innovation sequence white Gaussian with covariance HP⁻Hᵀ + R — induces zero KL divergence from the true law, so every detector's ROC collapses to the chance line (Neyman–Pearson framing). The conclusion survives, since full second-order matching is still a passive system-identification problem, but the adversary's job is matching (A, LQLᵀ), not one matrix; the note as written understates that cost.

**R1.2 — §6 sentence says the opposite of what it means.**
"An adversary that matches both is not hard to detect — it induces the same distribution." Read literally, "not hard to detect" = easy. Intended: "not merely hard to detect — undetectable in principle."

**R1.3 — Privileged perturbation has a named literature to anchor to.**
Assumption (3) is essentially **physical/dynamic watermarking** from control-systems security: Mo & Sinopoli's replay-attack detection via a private Gaussian excitation on the control input, and Satchidanandan & Kumar's dynamic watermarking. That literature quantifies exactly the trade gestured at here — detection power vs. probe/control cost — with chi-squared innovation detectors, and would let this note cite a cost bound rather than assert one.

**R1.4 — The probe-privacy caveat needs a channel-position condition.**
"The adversary cannot observe the probe" holds only if the attack severs the probe→observation path. A man-in-the-middle that *relays* the true system's response to the probe inherits the correct response for free — this is precisely why watermarking defeats replay attacks but not all loop-preserving attacks. Suggested scoping (for §6 and the takeaways): the cost asymmetry holds against adversaries who **replace** the dynamics, not those who **relay** them. This scopes the privileged-perturbation claim the same way the note already scopes unforgeability.

**R1.5 — Detection power is pass-limited; connect to contact-window work.**
Route (a) (non-Gaussianity) is theoretically clean but statistically expensive: higher-cumulant estimators have rapidly growing variance, and samples arrive in finite contact windows. A per-pass detection-power budget — how many samples before, e.g., a kurtosis test has power against a given deviation — would turn takeaway (a) from a direction into a sized work item, and ties directly into the contact-window-extension analysis.

**R1.6 — Minor.**
(i) The OU steady-state paragraph in §5 is an analogy (the Kalman steady state is the DARE balance of Q_d inflation against measurement contraction, not a drift), which sits slightly at odds with §1's "each arrow is an identity, not an analogy" — worth flagging as the one deliberate analogy. (ii) Since this lives in a QKD project, one scoping sentence distinguishing this classical-telemetry argument from the quantum layer's own authentication guarantees would preempt a predictable reader confusion. (iii) ADR-0002/0003 wall discipline is well kept: the probe enters as a typed physical input through the declared control surface; verdicts stay above `PhysicsSignals`.
