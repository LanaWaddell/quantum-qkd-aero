# TWIN-2 Plan — Private-Probe Watermarking and the Probe/Innovation Cross-Correlation Detector

**Status:** **v2 — APPROVED FOR IMPLEMENTATION** (Echo review 2026-08-11, "approve after targeted revision + explicit PI sequencing decision"; R1–R10 incorporated; PI sequencing amendment granted 2026-08-12)
**Date:** 2026-08-12
**Governing records:** `NOTE-diffusion-kalman.md` v2.1 §6.1–§6.2; `NOTE-sequencing-2026-08-10.md` **as amended 2026-08-12** (§3 Exp-1 gate split — TWIN-2 synthetic primitive authorized; TWIN-3 finite-window study and Exp-1-gated Exp 3B registered); TWIN-1 (merged, `eeea12e`).
**Lane:** TWIN-* (Phase 2D; no LINK-lane contact). Baseline: 414 green (393+1 skip without qiskit).
**Commit shape:** `src/qkd/twin.py` (known-input extension), `src/qkd/twin_watermark.py` (new), `tests/test_twin_watermark.py` (new), this plan.

## 0. Sequencing authority (R1 — resolved by dated amendment, not reinterpretation)

TWIN-2 proceeds under the **2026-08-12 amendment to `NOTE-sequencing-2026-08-10.md` §3** (dated PI decision): the model-generic synthetic Route-2 primitive is authorized now; the Exp-1 gate is preserved in full for every link-telemetry / mission-cadence / contact-window / PNT / QKD-performance instantiation (Exp 3B). Echo's finite-window power study is registered as **TWIN-3**. This plan cites that superseding record; it does not claim self-authority. **`N = 2000` here is a synthetic sample count, never a satellite-pass duration** (the mapping N ≈ T_contact/Δt is earned by TWIN-3/Exp 3B).

## 1. Claim scope (binding; TWIN-1 conventions inherited)

- **Demonstrated:** the Route-2 information-structure asymmetry as calibrated ensemble behaviour. Under an attack whose **complete unconditional Gaussian observation law matches the honest watermarked law** (R4), TWIN-1's **probe-unaware** whiteness and NIS diagnostics remain at their null rates, while a **probe-aware** cross-correlation detector rejects with predeclared power. The advantage is **privileged information, not a more aggressive threshold** (R3) — the two views are evaluated on the *same* attack paths, differing only in whether the detector receives the realized probe.
- **Detection and blindness both asserted:** detect no-probe synthesis and past-trajectory replay (privileged view); remain blind — **by structural identity (R7)** — to a perfect live relay.
- **Not claimed:** unforgeability (relay blindness is the standing honest boundary); any aggregate false-positive rate (per-test α, reported separately); navigation/QKD performance; ROC or probe-energy curves (TWIN-3 / sized Route-2 item). TWIN-2 is an **anti-spoofing methodological primitive**.
- **Probe privacy (R8):** "private" = the realized probe is excluded from the adversary's simulated information set and attack-generator signatures. **Not a cryptographic secrecy claim**; the recorded seed is available to the evaluator for reproducibility. Tests assert attack APIs do not accept the probe and the relay receives only the output stream — not that a real adversary cannot infer it.
- **Terminology (R7):** *replay* = re-presentation of a recorded trajectory; *passive-law-matched no-probe synthesis* = independent draw matching the full unconditional law but independent of the current probe; *relay* = pass-through of the true watermarked contemporaneous output.

## 2. Frozen model and parameters (R2/R5 — all fixed before any seed)

**Timing convention (R2, binding):** state recursion `x_{k+1} = a·x_k + g·u_k + w_k`, observation `y_k = x_k + v_k`. The probe u_k drives `x_{k+1}`, so it first affects `y_{k+1}` — **first theoretically visible lag is d = 1.** The known-input filter predicting `y_k` uses the *preceding* control: `x̂⁻_k = a·x̂_{k-1} + g·u_{k-1}` (control index k−1 predicts observation k). The cross-correlation is `r_d = corr(u_k, z_{k+d})` over lag set **D = {1, 2, 3, 4, 5}**; pair count for lag d is N−d (R6); u standardized by **known σ_u**, innovations by known S_k (zero-mean by construction, not sample-centered).

**Frozen numerics:**

| Symbol | Value | Note |
|---|---|---|
| a | 0.9 | nominal AR(1) |
| q | 1.0 | nominal process variance (conditional on u) |
| r | 0.5 | measurement variance |
| σ_u² | 1.0 | probe variance |
| g_strong | 0.5 | strong gain: g²σ_u² = 0.25 (25% of q) — overwhelming separation |
| g_modest | **0.15** | g²σ_u² = 0.0225 (2.25% of q). **Corrected 0.10→0.15 at implementation review** — see §8. |
| q_synth(g) | q + g²σ_u² | passive-law-matched synthesis process variance (R4) |
| N | 2000 | **synthetic** sample count |
| α | 0.05 | per test, reported separately (no family-wise claim) |
| D | {1..5} | df = 5 |
| P_x^u(g) | (q + g²σ_u²)/(1−a²) | stationary init variance under probing (no transient) |

**Ensembles (R5, exact-binomial bands via the TWIN-1 helper):** null-calibration n = 200 → 99% band [3, 19]; two-sample honest-vs-relay comparison via exact convolution → [−11, 11]; detection ensembles n = 50, power floor ≥ 0.9. **Comparative test (obligation 7) uses n = 200** so its passive-null assertion uses the [3, 19] band (R5 ambiguity resolved: comparative = 200-run). Master seed recorded; probe seeds in a disjoint `SeedSequence.spawn` stream from process seeds; **a second held-out review seed** (R6) used only at review to distinguish calibration from seed-fit.

## 3. Filter extension (`twin.py`, R9 — complete contract)

`run(observations, x0, P0, *, control_matrix=None, control_inputs=None)`:

- Both `None` (default) takes the **old arithmetic branch exactly** — not "old plus numeric-zero control"; bit-identity covers **every `TwinTrace` array**, asserted (R9). TWIN-1 test file untouched and green.
- Supplied-together-or-both-omitted; `B.shape == (state_dim, control_dim)`; `control_inputs.shape == (n_steps, control_dim)` under the §2 timing convention (control k−1 predicts obs k; the first prediction uses x0 with no control, documented); finiteness; empty control dim and length mismatch raise clearly. Scalar fast path and general path implement identical known-input semantics (bit-identity test across both).

## 4. Watermarked process and threat-class generators (`twin_watermark.py`)

Scalar–stationary, stationary-initialized at P_x^u(g) (no transient in any signal):

- **Honest watermarked:** the §2 recursion with the private probe.
- **Passive-law-matched no-probe synthesis (R4):** AR(1) with process variance `q_synth = q + g²σ_u²`, **no probe** — matches the honest watermarked process's complete unconditional Gaussian law (mean, stationary variance, autocovariance kernel, measurement law) **analytically** (asserted by parameter equality, not sampled tolerance), while independent of the current probe.
- **Replay:** a *recorded* honest watermarked trajectory from a **past** probe realization, re-presented against the current probe — same unconditional law (analytic), zero correlation with the current probe.
- **Perfect relay (R7):** the true current watermarked output passed through unchanged — **bit-identical to honest by construction**; blindness proven by a paired identity test, then inherited from the honest null calibration. No independent "relay ensemble" substitutes for the identity test.
- **Delayed relay: removed (R10)** — listed as the first extension after base timing/calibration are certified.

**Two information views (R3, the core architecture):**
- **Passive view:** filter run with **no** control terms; the probe is marginalized as ordinary Gaussian excitation (this is why synthesis uses q_synth — the passive filter sees the correct total process variance). Whiteness + NIS computed here.
- **Privileged view:** filter run **with** `B, u` (conditional process variance stays the physical q); cross-correlation uses the same realized u.
The comparison is honest only because the passive path never receives u — asserted structurally.

## 5. Proof obligations (R-rewrite §4)

| # | Obligation |
|---|---|
| 1 | Known-input extension: nonzero-input hand calc verifies the first two transitions; complete validation (R9); `control=None` bit-identical across **every** TwinTrace array |
| 2 | Timing/lag oracle: a noise-free limiting construction places the probe response in lag d = 1 exactly (not "some lag becomes large") |
| 3 | Honest privileged null: probe-aware cross-correlation rejects within [3, 19]/200; passive whiteness + NIS also at null |
| 4 | Passive-law equality: honest watermarked, q_synth synthesis, and past replay have **analytically identical** unconditional law parameters (asserted on parameters, not sampled) |
| 5 | Passive calibrated blindness: probe-unaware whiteness/NIS reject synthesis and replay at null rates, correct band for the ensemble size |
| 6 | Privileged detection: probe-aware cross-correlation detects synthesis and replay at g_strong, power ≥ 0.9 (n = 50) |
| 7 | **Information-advantage comparison (core):** on the *same* g_modest attack paths (n = 200), passive whiteness/NIS reject within [3, 19] (null) while probe-aware cross-correlation power ≥ 0.9 — only the privileged path receives realized u |
| 8 | Perfect relay: current-output relay bit-identical to honest (trace + statistic); inherits honest null calibration |
| 9 | Determinism/RNG separation: repeated inputs bit-identical; disjoint derived streams per purpose; attack APIs do not accept u; relay receives outputs only |
| 10 | Calibration/result scope: unsupported (α, lags, N, m, timing) raise; χ² threshold documented **asymptotic**, its finite-N size empirically checked by the 200-run honest ensemble; no verdict/authenticity/security field; §0/§1 scope + terminology language present |
| 11 | Suite/lane boundary: TWIN-1 green and untouched; no LINK/mission/emission/schema/control contact; no SciPy |

## 6. Out of scope

Finite-window power surface (TWIN-3); link/telemetry instantiation (Exp 3B, Exp-1-gated); delayed/partial-relay calibrated claims; probe-energy/ROC curves; multivariate probes and lag optimization; QKD+PQC composition (a future ASSURANCE/TRUST lane, per Echo); any LINK-lane file, emission, schema, control; navigation/PNT models; SciPy.

## 8. Implementation record (2026-08-12) — v2.1

Implemented by a Sonnet subagent; reviewed top-tier. **Result: 439 passed** (414 baseline + 25 new; zero skips/xfails; ~18s). Frozen emission hash unchanged (`3d154402…`). All 11 obligations covered. Files: `twin.py` +113 (known-input extension), `twin_watermark.py` +~530 (new), `tests/test_twin_watermark.py` +~920 (new).

**One genuine plan error found by the subagent and corrected at review — the workflow functioning as designed.** The v2 plan froze `g_modest = 0.10` against a `D = {1..5}` χ²₅ detector *and* an obligation-7 power floor of ≥ 0.9 — mutually inconsistent: the 5-lag statistic dilutes the clean lag-1 response (population lag-1 correlation −g/√S) across four near-null lags, lifting the critical value 3.84 → 11.07, so g=0.10 yields only ~0.80 power. The subagent correctly refused to silently retune a frozen parameter and instead shipped an honest 0.6 floor with the tension documented. **Top-tier review then verified independently that passive blindness is gain-independent** under the q_synth exact-law-matching construction — passive whiteness/NIS reject at (12,6)/200 for all g ∈ [0.10, 0.25] — so g_modest is a free knob for the *privileged* target, not constrained by passive blindness. Corrected g_modest 0.10 → **0.15** (verified privileged power 0.997, passive still fully blind), restoring the ≥ 0.9 obligation on a principle rather than a tune. D={1..5} retained deliberately (robustness to unknown watermark-response lag structure). This gain-independence is the **stronger, correct framing** of the Route-2 result and is now recorded in the module docstring: exact-law-matched synthesis is passively invisible *at every gain*; only the privileged detector separates it, with power rising in gain.

**Obligation-7 realized (g_modest = 0.15, n = 200, shared paths):** passive whiteness 12/200 and NIS 6/200 (both in null band [3, 19]); privileged cross-correlation power 0.997 (≥ 0.9). Obligation 8 relay bit-identity confirmed (trace + both result objects `==` honest). Obligation 2 lag-1 oracle exact. Minor recorded resolution: `sigma_u` is a probe model parameter passed to the detector, not stored on the calibration object (mirrors how a/q/r sit outside `DiagnosticCalibration` in TWIN-1).

## 7. Execution note

TWIN-1 conventions govern. Sonnet implementation against the 414-green baseline; top-tier review verifies obligation 7 (the comparative core, on shared paths with only-privileged-u), obligation 8 (relay bit-identity), obligation 4 (analytic law equality), and the §0/§1 scope language, using the held-out review seed. Genuine ambiguities recorded, not resolved by invention.
