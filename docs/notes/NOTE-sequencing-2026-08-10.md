# NOTE: Cross-lane sequencing decision (2026-08-10)

**Status:** Sequencing record (normative until superseded) — revised 2026-08-10 after Echo's pre-LINK-1 full-packet review (whiteness claim narrowed; canary reclassified Route 1; Exp 3 staged as 3A/3B/3C; §6 revision gates added)
**Context:** Follows the two-reviewer reconciliation of `NOTE-diffusion-kalman.md` (v2.1, Appendix A) and the ADR-0003 evidence memo. Supersedes the architecture map's "PR-A is NEXT" queue status, which is stale: per ADR-0003 §8, PR-A through PR-D have landed (`DECLARED_SCHEMA_EXTENSIONS` implemented). The stabilization lane is complete.
**Canonicalization note:** the canonical `NOTE-diffusion-kalman.md` (project knowledge base and `docs/notes/`) carries the v2.1 body; v1 is archived at `docs/notes/archive/NOTE-diffusion-kalman-v1.md`. The v1/v2 filename ambiguity flagged in Echo's review existed only in the review packet's copies.

---

## 1. Next repo build: LINK-1

LINK-1 (observables dataclasses + Protocols + ControlSpec/Controllable + table-backed GeometryProvider; zero behaviour change) is the next repo work. Pre-flight, in order:

1. **Ratify ADR-0003 (LINK-0).** Status flip + date stamp; the timebin evidence memo cleared it ("no amendment needed before ratification"). Ratification formally adopts the two review-discharged rules LINK-1 implements:
   - `timing_jitter_s` composes in **quadrature**, with the correlated-structure escape (memo item, Eq. 28);
   - `misalignment_error` low-order default = **sin²(Δϕ)**, documented, DV time-bin scope only.
2. **Freeze the byte-identity baseline.** ✅ **DONE 2026-08-10.** Certified at HEAD `03736da` (main): suite green (**142 passed / 1 skipped** base; **163 passed** with qiskit); both emissions (`qkd.run`, `qkd.run_fibre`) run-to-run deterministic; artifacts frozen with SHA-256 manifest (`link1-baseline-03736da.zip`, delivered to PI; write-back to `tests/fixtures/` on request).
   **Finding — byte-identity is environment-local:** Mac working copy (Py 3.13.12 arm64, numpy 2.4.6) and cloud (Py 3.11.15 x86_64, numpy 2.4.4) emissions differ at ULP level (~100 last-digit float64 fields; no structural differences). Consequence: LINK-1's criterion #1 test must compute the pre-stack path and the empty-stack path **in the same test run** and assert byte-identical serialization in-process — never diff against a fixture generated on another machine. Frozen artifacts serve as per-environment regression tripwires. If CI is added, CI freezes its own fixture at this commit and pins numpy.
3. **Decide ratification-decision-5 residual in the LINK-1 plan:** does the runtime controls registry literally share the `DECLARED_SCHEMA_EXTENSIONS` declaration pattern, or mirror it? Decide explicitly at PR-plan time, not implicitly in code.

Standing constraints (not tasks): `GeometryProvider` stays satellite-neutral where practical (decision 4 fibre deferral, resolved by interface pressure + byte-identity evidence, not taste); §3.3.1 composition rules are binding — the non-additive fields are the trap.

## 2. Twin lane (parallel; does not block LINK-1)

Per `NOTE-diffusion-kalman.md` v2 §7 and the reconciliation:

- **Immediate small item: innovation-whiteness testing** on the existing Kalman twin. Estimator-side statistic only; no new interfaces; no contact with the composition core. May proceed independently of LINK-1. **Claim scope (per Echo review):** whiteness testing strengthens the existing result by checking *temporal second-order structure*; only together with innovation-covariance and known-input cross-correlation tests does it support a full second-order matching claim. Report it as a temporal second-order diagnostic — not by itself as proof of complete second-order matching. Under the v2.1 theorem, nothing may be called "matched" until at least whiteness is checked — this is a validation obligation on the existing result, not new scope.
- **Foreclosed:** any further covariance-gating refinement as a detection path (provably spent money, v2 §6).

## 3. Watermark / privileged-perturbation simulation: folded into Exp 3, not standalone

The Route 2 probe/innovation cross-correlation test (dynamic-watermarking form) is a classical-telemetry instantiation of Exp 3's anchor ("forge the symptom, not the physics that generated it"). Sequencing:

- **Do not run standalone now.** It needs realistic channel dynamics; the OU transmittance generator it wants is experimental-program shared-infrastructure item #2, built by Exp 1 anyway.
- **Exp 3 is staged (per Echo review), separating three distinct questions the original design conflated:**
  - **Exp 3A — passive separation** using full decoy and temporal statistics (Route 1);
  - **Exp 3B (= Exp 3-lite) — private probe/innovation cross-correlation** (Route 2): linear-Gaussian twin + one cross-correlation statistic, no RL, no attack library. Runs after Exp 1's generators exist. If the classical version shows no separation under realistic contact windows, that is decision-relevant before further Exp 3 investment;
  - **Exp 3C — response policy** after a detector fires.
- **Claim discipline:** passive separation above chance is a *Route 1* result; only separation *caused by the private probe* is the Route 2 / privileged-perturbation claim. The design must define exactly which nuisance observables are matched (QBER alone is too weak — gain and intensity-conditioned statistics can trivially distinguish some attacks) and which held-out statistics are allowed to discriminate.

## 4. Supplement effects on planned experiments

- **Exp 3 attack library absorbs the §6.2 attack-class taxonomy** — it currently lacks a *relay / man-in-the-middle* class, which is precisely the class the privileged-perturbation mechanism cannot catch. Exp 3 ROC claims must be scoped by attack class to be honest.
- **Exp 4's committed-reference canary is a Route 1 mechanism** (held-out trusted reference), **corrected from the earlier Route 2 classification** per Echo's review: the precommitment defeats the *trained agent* optimizing the reference away (internal capture-detection), but a fixed, known canary can in principle be modelled or forged by an *external* adversary. It becomes Route 2 only if it includes a private or unpredictable challenge whose causal response must appear in the observation (dynamic-watermarking style). Exp 4's purpose — drift detection and confidence/competence decoupling — is unaffected; the correction separates *model-drift detection* from *adversary authentication*, and the canary must be made private/randomized if it is ever intended as a watermark.
- **Route 1 power budget** (per-pass higher-cumulant detection power vs. contact-window duration) is an analysis item tied to the contact-window-extension work; sized, not scheduled.

## 6. Pre-implementation revision gates (from Echo's full-packet review, 2026-08-10)

The research specs are roadmap-grade, not implementation-ready. Each item below is a **gate**: revise before building the stage it belongs to. None blocks LINK-1.

**Before Exp 1 (channel-dynamics spec):**

- Convert all internal geometry to SI (metres/seconds); R_E is currently in km against SI GM.
- Resolve the **PDT vs. τ_c** design tension: the stationary per-block PDT summary erases the temporal correlation τ_c provides, so under PDT mode τ_c affects finite-sample uncertainty, not the distribution itself. Either use geometry / slowly-varying turbulence strength / cloud dynamics as the primary adaptation axes, or retain a block-state process preserving inter-block correlation.
- OU exact transition is exact only for constant (m, σ_X, τ_c) over the step; specify piecewise-constant stepping (elevation drives σ_X).
- PDT aggregation: average gain and error-gain separately, then divide — E̅ₓ = E[EₓQₓ]/E[Qₓ]. Never average QBER values directly.
- Document η_turb as a relative irradiance factor (E[η_turb]=1 implies instantaneous values above 1) and verify composed η ≤ 1.

**Before full Exp 3 (experimental program):**

- Replace the label-based "bits emitted under attack" reward term with a security-grounded quantity: certified secret-key length under the applicable proof; zero key when model/security assumptions are violated; attack-detection accuracy reported as a separate operational metric. "Attack present" ≠ "key compromised" — decoy-state analysis already bounds the single-photon contribution against PNS-type behaviour (Lo–Ma–Chen); blinding and time-shift attacks exploit implementation assumptions and need explicit detector/device models.

**Before Exp 5:**

- `commit` must be structurally admissible only when the composable finite-key procedure certifies positive key length — rejection, not penalty. Security failure cannot be merely an expensive RL outcome.
- Adaptive stopping requires proofs compatible with data-dependent stopping (time-uniform bounds, allocated error budget across looks, or a variable-length QKD proof — cf. Tupkary et al., PRResearch 6, 023002; Wiesemann et al., arXiv:2405.16578). Fixed-sample bounds may not be checked repeatedly until one passes.

**Before any Exp 6+/contact-window build:**

- Soften "same constraint in two media" to "shared scheduling pattern": no-cloning, heralding, swapping, and purification mean transition laws and feasible actions are not parameterized only by "what is stored and how it decays."
- Fix the memory-fidelity floor: full two-qubit depolarization gives Bell fidelity 1/4; F > 1/2 is the Werner distillability *boundary*. Either use a depolarizing model approaching 1/4 or label the 1/2-floor model as dephasing-specific.
- Scope the PLOB claim: it is the repeaterless point-to-point pure-loss benchmark; trusted-node and alternative-assumption architectures change the trust model rather than "beating" it.
- Deep-space delay needs an event timeline (one-way L vs. round-trip 2L vs. asynchronous); "pre-commit the whole window" follows only when the relevant feedback delay is large relative to both the control interval and remaining contact time.
- Distinguish a classical *key store* from a generic DTN bundle — forwarding key material through intermediate nodes changes the trust/composability model.

## 5. Order summary

```
now:        ADR-0003 sign-off → LINK-1 (baseline frozen ✅; LINK-1 stays clean and bounded)
parallel:   innovation-whiteness test on existing twin (temporal second-order diagnostic)
later:      LINK-2+ per ADR-0003 queue · Exp 1 (builds shared infra; §6 gates first)
then:       Exp 3A (passive) → Exp 3B/-lite (probe correlation) → Exp 3C (response) → Exp 4
never:      covariance-gating refinement as a detection path
```
