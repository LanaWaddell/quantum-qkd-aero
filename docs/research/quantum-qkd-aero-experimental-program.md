# Quantum-QKD-Aero: Experimental Program (Lab-Mode Design)

*Five experiments treating the simulator as an instrument for studying adaptation, coherence, and trust — not just key-rate calculation. Each experiment is the question the previous one raises, so the order is the program.*

---

## Design principles (read first)

- **Every experiment reports a curve, not a number.** The science is in how a quantity scales with a control parameter (volatility, observation quality, attack strength, distribution shift, cost-of-error), not in a single headline result.
- **Always include an oracle/genie upper bound.** The simulator knows the true channel state and true attack labels even when the agent does not. Report the *fraction of the oracle gap closed*, so gains are interpretable rather than absolute.
- **The agent never sees what it must not be able to game.** Attack labels (Exp 3), the committed reference (Exp 4), and security ground truth (Exp 5) are available to the *evaluator* and the *reward*, never to the *observation*. This separation is the whole point of those experiments.
- **Reward hacking is the default failure mode.** Any time the learned policy "wins," check whether it won by exploiting an estimator shortcut rather than real physics. The matched baselines and oracle bounds exist partly to catch this.
- **This whole program is the Phase 2D research layer, behind the wall.** Per ADR-0002, the physics channel carries no cognitive/trust field. The agent reads `PhysicsSignals` — the physics output surface — and nothing here writes back into physics emission. The "agent never sees what it can't game" principle above is the operational form of that wall: the read surface is `PhysicsSignals`, and the evaluator's privileged knowledge (labels, committed reference, ground truth) lives outside it.

### Shared notation

| Symbol | Meaning |
|---|---|
| η, η̂ | true / estimated channel transmittance |
| μ, ν₁, ν₂ | signal and decoy intensities (ν₂ ≈ 0 vacuum) |
| p_Z | basis-choice bias (asymmetric BB84) |
| Q_x, E_x | gain and QBER at intensity x |
| Y₁, e₁ | single-photon yield and error rate (decoy-estimated) |
| ε_sec | composable security parameter |
| N | block length (rounds) |
| SKR | secure key rate (bits/block or bits/s) |

### Shared infrastructure (build once, used by all five)

1. **Decision-epoch RL wrapper** — a Gym-style `step(action) → (obs, reward, done, info)` around the existing first-principles physics. One epoch = one block of N rounds (or a sub-block for fast control).
2. **Channel-dynamics generators** — temporally correlated transmittance (Ornstein–Uhlenbeck process in log-η, with tunable correlation time τ_c and variance σ²), discrete obscuration events (cloud on/off), and an orbital-pass generator (elevation angle → slant range → atmospheric path length → η_geo over time for a LEO downlink).
3. **Baseline-policy library** — static-optimal-for-mean, static-worst-case, a QBER-threshold heuristic, and the per-epoch oracle.
4. **Per-epoch secure-key module** — decoy-state estimation of Y₁, e₁ and SKR from epoch statistics, with a finite-key option (composable bound with statistical-fluctuation correction) toggleable for Exp 5.
5. **Metrics/repro harness** — fixed seeds, logged trajectories, and per-run config capture.

**Modeling note on algorithm choice.** Experiments 1 and 2a are close to *contextual bandits* (per-epoch parameter choice, weak long-horizon coupling) — start there; it's a cheaper, more debuggable baseline than full RL. Experiments 2b, 4, and 5 have genuine temporal credit assignment (spending now to know later; drift accumulating; optimal stopping) and want a sequential method (PPO/SAC for continuous actions, DQN or a learned stopping rule for discrete ones). Don't reach for deep RL where a bandit suffices.

---

## Experiment 1 — Does adaptation pay, and where?

**Conceptual anchor:** the value-of-adaptation curve. The spine of the ML4QT contribution.

**Question.** Static QKD parameterizations are chosen for the average or worst-case channel. How much secure key does that leave on the table, and how does the value of adapting scale with channel non-stationarity? Hypothesis: value of adaptation ≈ 0 in a stable channel and grows with volatility; the science is locating that crossover and its scaling.

**Observation space.** Windowed transmittance estimate η̂ (mean + recent variance), current QBER estimate, orbital geometry / elevation angle (for satellite regime), recent SKR history, time-in-epoch. Optionally a short channel forecast feature.

**Action space (continuous).** Decoy intensities (μ, ν₁), basis bias p_Z, signal fraction. One action per decision epoch.

**Reward.** R_t = secure bits generated in epoch t, computed by the secure-key module from that epoch's statistics. Hard floor: if decoy estimation cannot certify security (e₁ above threshold), R_t = 0 — no credit for unsafe key.

**Baselines.** (a) static-optimal-for-mean channel; (b) static-worst-case/conservative; (c) QBER-threshold heuristic; (d) **per-epoch oracle** with true η (upper bound).

**Metrics & deliverables.** Value of adaptation V = (SKR_RL − SKR_best-static) plotted against a non-stationarity parameter (OU correlation time τ_c, fading variance σ², or cloud-event rate). Crossover point where V becomes significant. Fraction of oracle gap closed.

**Platform requirements (new build).** Non-stationarity generator (#2 above) — this is the main new piece; the rest reuses existing physics. Decision-epoch loop. Bandit/RL training harness.

**Dependencies.** None — runnable almost entirely on existing instruments. This experiment validates the shared infrastructure for everything after it.

---

## Experiment 2 — What is the shadow price of the system's own situational awareness?

**Conceptual anchor:** "operational coherence" stops being a slogan and becomes an elasticity. Two sub-experiments.

### 2a — Observation-quality elasticity

**Question.** How fast does secure key rate fall as the agent's *picture of the channel* degrades? The slope dSKR/d(observation quality) is operational coherence with a number attached.

**Observation space.** As Exp 1, but passed through a controllable corruption stage: latency τ (agent sees state from τ epochs ago), additive noise σ_obs on η̂ and QBER, and feature masking (partial observability).

**Action space.** As Exp 1.

**Reward.** As Exp 1 (secure bits per epoch).

**Baselines.** Perfect-observation agent (upper bound); progressively corrupted variants.

**Metrics.** Elasticity curve dSKR/d(obs quality) — slope *and* curvature — across each corruption axis (latency, noise, masking) independently and jointly. Regret vs. the perfect-info oracle as a function of corruption.

**Platform requirements.** Observation-corruption harness: latency buffer, calibrated noise injection, feature-mask switch.

### 2b — The sensing-vs-using tradeoff

**Question.** Monitoring photons aren't key photons. If estimating the channel competes with using it, how much should the system spend on *knowing* versus *doing*, and how does that optimum move with volatility?

**Observation space.** As 2a, plus current estimator uncertainty.

**Action space.** Exp 1 actions **plus** a probing fraction f — the share of pulses/time allocated to channel estimation, which does not contribute to key but sharpens η̂.

**Reward.** Secure bits from the (1 − f) fraction, *net* of the probing cost. Better η̂ improves downstream decisions, so the agent must trade information acquisition against immediate yield — a genuine sequential problem.

**Baselines.** Fixed-probing-budget agent; zero-probing agent; perfect-info oracle (f → 0 with free knowledge).

**Metrics.** Optimal probing fraction f*(volatility) — the headline curve. Regret vs. oracle. Whether f* tracks the value-of-adaptation crossover from Exp 1 (it should: adaptation is only worth informing when adaptation itself pays).

**Platform requirements.** A resource model coupling probing and key generation to a shared photon/time budget; instrumentation to log f and estimator uncertainty.

**Dependencies.** Builds directly on Exp 1's environment and oracle.

---

## Experiment 3 — Can the loop tell sabotage from weather?

**Conceptual anchor:** privileged perturbation in communication clothing — an adversary can forge the *symptom* (QBER) but not the *physics that generated it*.

**Question.** Under attacks calibrated to produce the *same QBER* as natural degradation, can the system separate sabotage from weather and respond appropriately, without a crippling false-abort rate?

**Attack library (QBER-matched).** Intercept-resend; photon-number-splitting; beamsplitter tap / partial collection; detector blinding (bright-light); time-shift. **Intercept-resend and PNS extend the existing QND/PNS Eve model that `decoy_bb84` already ships** — this experiment is not a from-scratch attack library; it adds QBER-matching, the remaining attacks, and the response layer on top of an Eve path that already exists. Each attack is calibrated by the matching routine to hit a target QBER equal to a chosen natural-degradation scenario, so QBER alone is uninformative. The discriminating signal lives in the *full* statistics: decoy-yield structure (PNS distorts Y₁ characteristically — already computable from the existing decoy-state machinery), photon-number statistics, detector temporal correlations, and mismatch between observed multi-intensity gains and the channel model's prediction.

**Observation space.** Full decoy statistics — gains and error rates per intensity (Q_μ, Q_ν, E_μ, E_ν), not just aggregate QBER — plus temporal-correlation features. **No attack label.**

**Action space (discrete/decision).** continue · abort block · switch link · re-key · raise monitoring.

**Reward.** R = (secure key preserved) − λ_fa·(false-abort cost) − λ_leak·(bits emitted while under an *undetected* attack). The leak term uses simulator-side ground-truth labels that the agent never observes; λ_leak ≫ λ_fa encodes "a compromised key is worse than a lost one." This pushes the ROC tradeoff into the objective rather than fixing a threshold by hand.

**Baselines.** QBER-threshold abort (standard practice); decoy-bound monitoring (standard security check); a *supervised* classifier on full statistics (non-adaptive ceiling for detection); the RL agent (which both detects and acts).

**Metrics.** Per-attack detection ROC (TPR vs FPR) at matched QBER — the existence of separation above chance *is* the privileged-perturbation claim. Secure-key-preserved-under-attack. False-abort rate on pure weather. Compromise leakage (bits emitted under undetected attack).

**Platform requirements (extends an existing Eve, not greenfield).** The QND/PNS Eve model and the decoy-yield discriminating signal **already exist** in the `decoy_bb84` protocol. What this experiment builds *on top of* that: the QBER-matching calibration routine, the remaining attacks not yet modelled (beamsplitter tap, detector blinding, time-shift), richer per-intensity statistics exposure, and the decision/response action space. Smaller than the original framing implied — the hardest pieces (a working Eve, the decoy statistics that expose it) are in place.

**Dependencies.** Needs Exp 1's environment and the full-statistics secure-key module. Independent of Exp 2.

---

## Experiment 4 — Does the agent know when it's lost?

**Conceptual anchor:** capture / unhealthy synchrony (Echorym) and the committed reference (Ulysses-and-the-mast). The real failure mode isn't error — it's confidence staying high while competence collapses.

**Question.** Under distribution shift, does the agent's internal confidence decouple from true secure-key margin (the capture signature)? And does a committed reference fire *before* margin collapses — with how much lead time?

**Setup.** Train in regime A (one atmospheric profile / detector-aging state / orbit). Deploy in shifted regime B (different profile, aged detectors, different pass geometry). Measure, don't retrain.

**Observation space.** Agent observation as in Exp 1. Separately logged (not part of the experiment's training signal): the agent's confidence proxies — value estimate, predicted SKR, policy entropy — and the committed-reference residual.

**Committed reference.** A small set of canary rounds with fixed, known parameters whose expected statistics under the *trusted* channel model are pinned outside the optimization loop. Drift is flagged when observed canary statistics deviate from the committed reference beyond a calibrated band. Because the agent is trained without canary reward, it cannot optimize the reference away — that precommitment is the mechanism.

**Action / supervisory layer.** The agent acts normally; a supervisor raises a drift alarm on canary residual. (Optionally, a later meta-policy responds to alarms — but first characterize the bare detector.)

**Reward.** Standard key-rate reward in regime A (this experiment evaluates the response to shift rather than training it).

**Metrics.** Confidence–competence correlation under shift — it *should* decouple, and that decoupling is the hazard being demonstrated. **Detection lead time** = (epoch when true margin crosses the unsafe threshold) − (epoch when the canary alarm fires); want > 0, and characterize its distribution. False-alarm rate of the canary under benign drift. The lead-time distribution is the entire value of the mechanism.

**Platform requirements.** Distribution-shift harness (parameter-shift schedules: detector aging curve, atmospheric-profile swap, orbit change). Confidence-signal logging. The canary / committed-reference subsystem with pinned reference statistics and a residual test, kept strictly outside the training loop.

**Dependencies.** Needs a trained agent from Exp 1 (or 2). Independent of Exp 3, though the two compose naturally later (a drifted agent is also more attackable).

---

## Experiment 5 — When should it commit the key?

**Conceptual anchor:** superposition discipline made literal — withholding commitment until alignment is confirmed. The capstone, and the most distinctly novel.

**Question.** In the finite-key regime a block is only ε-secure after enough rounds, and under a fluctuating channel the choice to keep-accumulating / commit-now / abort is a real optimal-stopping problem. Can a learned commitment policy trade key rate against security margin better than fixed-block rules, and how does the optimal discipline shift with volatility and with the cost of being wrong?

**Observation space.** Accumulated block statistics so far (counts, running QBER, current ε-secure key-length lower bound given data to date), channel state/forecast, rounds/resources remaining.

**Action space (discrete).** continue accumulating · commit block · abort block. (Optional extension: choose the ε allocation.)

**Reward.** Secure bits committed if commit *and* the block certifies ε-secure; −c_abort·N_wasted if abort (sunk rounds); −C_violation (large) if a committed block fails to certify (security violation must be driven to ~0); holding carries an implicit opportunity cost because the channel may worsen. The c_abort / C_violation ratio is the tunable "cost of being wrong."

**Baselines.** Fixed-block-size (standard QKD); fixed-time; QBER-threshold commit; oracle with future channel knowledge (upper bound on achievable stopping).

**Metrics.** Secure key rate; **security-violation rate (must be ≈ 0)** — report this first, since a policy that wins on rate by occasionally committing insecure blocks is disqualified, not impressive; average commitment latency; how the learned stopping threshold moves with volatility and with the cost-of-error parameter. Framing: finite-key QKD as a learned commitment / optimal-stopping problem.

**Platform requirements.** Composable finite-key accounting folded into the per-epoch reward (secure-key-length estimator with ε budget and finite-statistics correction — e.g., a Hoeffding-style or tighter bound), block-management action space, cost-of-error parameterization.

**Dependencies.** Needs the finite-key toggle in the secure-key module. Conceptually closes the arc opened by Exp 1.

---

## The arc, and what comes after

The five experiments form a ladder, each the honest question raised by the last:

1. Adaptation pays — and its value scales with volatility.
2. …so it depends on the quality of the shared picture — which has a measurable shadow price.
3. …and that picture can be *attacked* while looking like weather.
4. …and even unattacked, the agent can silently drift while staying confident.
5. …so the system must learn the discipline of *when to commit*.

**Experiments 6–7 (network frontier), once the single link is understood:**

- **Heterogeneous link arbitration** — a learned policy for *when to route over fibre vs. free-space vs. a satellite pass*. This is the CSA adaptive-communication-architecture abstract realized at the network layer rather than the link layer.
- **Multi-node coordination** — learned scheduling of entanglement swapping and purification across a short repeater chain. The entanglement-swapping path leans on the **teleportation-fidelity machinery that `decoy_bb84` already ships**, so the protocol primitive is partly in place; what's new is the topology (composition over segments — a real design step per ADR-0002, not a sweep) and the memory/decoherence model. This is where the quantum-internet thread (swapping + memories + purification) actually begins, and it's the reason the first five are worth doing in this order: each one builds an instrument the network experiments will reuse.
