# TWIN-1 Plan — Reference Kalman Twin and Innovation Diagnostic

**Status:** **v2 — APPROVED FOR IMPLEMENTATION** (Echo review 2026-08-11, "approve after targeted revision"; R1–R7 + amended proof obligations incorporated)
**Date:** 2026-08-12 (plan v1 2026-08-12 per session clock; Echo review stamped 2026-08-11 — recorded, immaterial)
**Governing records:** `NOTE-diffusion-kalman.md` v2.1 §6–§7; `NOTE-sequencing-2026-08-10.md` §2; and a private alignment note (gitignored, not in repo) §1.
**Lane:** TWIN-* (Phase 2D diagnostic/research machinery; consumes no `EffectiveLinkState`, mission emission, or estimator internals). Baseline: LINK-5 @ `bdd73de`, 389 green (368+1 skip without qiskit).
**Commit shape:** three files — `src/qkd/twin.py`, `tests/test_twin_whiteness.py`, `docs/TWIN_1_PLAN.md`.

---

## 1. Claim scope (binding, R1/R7 language)

TWIN-1 turns the v2.1 note's first build item into executable evidence, scoped exactly:

- **What the diagnostic is:** a *temporal second-order diagnostic* — scalar innovation whiteness (Ljung–Box on standardized innovations) plus two-sided NIS covariance consistency. **Failure of either calibrated check rejects the corresponding second-order consistency condition. Passing both is necessary but not sufficient for full second-order matching, Gaussian-law matching, source authenticity, or QKD security.**
- **Calibrated blindness is an ensemble statement (R1):** for data drawn from the nominal observable law, each diagnostic component rejects at its declared null rate within a predeclared binomial tolerance; no detector using only these observations can reject a same-law source more often than it rejects honest data at the same threshold. Individual seeded runs are *permitted* to fail at rate ≈ α — demanding otherwise would reward a miscalibrated diagnostic.
- **Terminology (R7):** an independently generated sequence from the nominal law is **same-law synthesis**, never "replay" — *replay* is reserved for reuse of a recorded trajectory (load-bearing distinction for TWIN-2's replace/replay/synthesis/relay classes).
- **Evidence claim (R7):** TWIN-1 is **qDISH-relevant integrity-method evidence** / an **anti-spoofing methodological primitive** — not a navigation-integrity prototype or GPS-spoofing performance result (those require a PNT observation model, attack model, and operating scenario).
- **Multiplicity (R4):** whiteness and NIS each run at their own declared α, reported separately; **no aggregate false-positive-rate claim is made** and no aggregate verdict exists.

## 2. `src/qkd/twin.py` (~200 LOC)

### 2.1 Filter: `LinearGaussianTwin` (R6 — stateless batch contract)

```python
LinearGaussianTwin(F, H, Q, R).run(observations, x0, P0) -> TwinTrace
```

- Dimension-generic filter; **no RNG anywhere in the filter** (randomness lives only in telemetry-generation helpers, each taking an explicit `numpy.random.Generator`). No state retained between `run` calls.
- `TwinTrace` (frozen): innovations ν_k, innovation covariances S_k, filtered state/covariance traces (for verification).
- Joseph form exactly: `P⁺ = (I−KH) P⁻ (I−KH)ᵀ + K R Kᵀ`; symmetry may be numerically re-symmetrized after update; **PSD failure raises — never hidden by eigenvalue clipping**.
- Linear algebra by `numpy.linalg.solve`/Cholesky — **no explicit matrix inversion** (gain, standardization, NIS quadratic forms).
- Construction/run validation: dimension compatibility for (F, H, Q, R, x0, P0); finiteness; symmetry; Q, R, P0 PSD within declared tolerance; every S_k numerically positive definite or clear diagnostic error; empty/too-short observation sequences (vs requested lags) and non-finite observations rejected.

### 2.2 Diagnostic: `innovation_diagnostic` (R2/R3/R4)

- **Scalar-observation-only in TWIN-1**: raises clearly when measurement dimension ≠ 1. (Per-component univariate Ljung–Box does not test vector whiteness — cross-component/cross-lag dependence escapes it; a multivariate portmanteau statistic is deferred until a real multi-observable telemetry model earns it.)
- **Whiteness:** Ljung–Box on **standardized innovations** z_k = ν_k/√S_k (one declared null; raw-innovation autocorrelations may be reported descriptively but are not a decision test). Lag budget K declared; df = K.
- **NIS (two-sided, R3):** ε_k = ν_k²/S_k ~ χ²₁ under the model; Σε_k over the N_eff retained samples ~ χ²_{N_eff}; two-sided bounds at declared α so inflated *and* deflated covariance are detectable; burn-in exclusion explicit and reflected in N_eff.
- **Calibration contract (R4):** a frozen `DiagnosticCalibration` object records `(alpha, lags, effective_n, measurement_dim, critical_values, provenance)`. Only the predeclared demonstration configurations ship (their χ² critical values precomputed, provenance commented — no SciPy); **unsupported (α, K, N, m) combinations raise** rather than interpolate or silently reuse a wrong table entry.
- Result object (frozen): per-test statistics, thresholds, per-test pass/fail, α, lags, N_eff, calibration reference. **No `secure`/`authentic`/`matched`/aggregate-verdict field.**

### 2.3 Telemetry generators (the theorem's cast)

All scalar–stationary, all taking an explicit `Generator`, all initialized **from the stationary distribution** (no transient in any detection signal, R5):

1. **Honest:** nominal model (F = a, |a| < 1; Q = q; H = 1; R = r); stationary state variance P_x = q/(1−a²).
2. **Wrong-dynamics, marginal-matched (R5, analytic):** F = b ≠ a with Q′ = P_x(1−b²) — same stationary state and observation marginal variance *by construction* (asserted analytically in the test, not tuned numerically). Nominal-filter innovations are colored.
3. **Same-law synthesis:** independent draw from the nominal law (case-3 blindness ensemble).
4. **Memoryless covariance mismatch (R3 test-5 construction):** nominal model with a = 0 (memoryless filter — the recursion cannot color innovations), data generated with wrong measurement variance R′ ≠ r. Standardized innovations stay temporally white at the expected rate; two-sided NIS rejects with high power — demonstrating that NIS adds information beyond whiteness *without* the confound of filter-recursion coloring.

## 3. Predeclared statistical parameters (fixed before any seed is chosen; rationale in test comments)

- α = 0.05 per test, reported separately (no family-wise claim, §1).
- Ljung–Box lags K = 20; run length N = 2000 with burn-in 0 (stationary initialization makes burn-in unnecessary — stated).
- Null-calibration ensembles (obligations 2 and 4): n_runs = 200 per ensemble; expected rejections 10 at α = 0.05; acceptance band = exact binomial 99% interval [3, 19] per component; case-4-vs-honest comparison by two-sample tolerance (difference in rejection counts within the predeclared band).
- Power assertions (obligations 3 and 5): adversary parameters chosen for overwhelming analytic separation (e.g. a = 0.9 vs b = 0.2 at N = 2000; R′/r = 2), n_runs = 50, empirical-power lower bound ≥ 0.9 asserted conservatively (rationale: expected power ≈ 1 at these distances; the bound is a floor, not an estimate).
- Every ensemble is fixed-seed deterministic (seeds derived from one recorded master seed); all assertions are exact reruns, not flaky sampling.

## 4. Proof obligations (Echo's amended list — the test file implements exactly these)

| # | Obligation |
|---|---|
| 1 | Scalar hand calculation verifies predict, innovation, S, gain, state update, and Joseph covariance update; separate ill-conditioned case verifies symmetry/PSD handling (without claiming Joseph form guarantees PSD under invalid inputs) |
| 2 | Honest stationary ensemble: whiteness and NIS rejection frequencies individually consistent with declared null sizes within the §3 binomial bands |
| 3 | Wrong-dynamics construction: analytic stationary marginal equality asserted; whiteness empirical power ≥ predeclared conservative bound |
| 4 | Same-law-synthesis ensemble: rejection frequencies match the honest ensemble within the predeclared two-sample tolerance; a single run is **not** required to pass |
| 5 | Memoryless covariance mismatch: standardized innovations white at expected rate; two-sided NIS rejects with power ≥ bound (both directions: R′ > r and R′ < r) |
| 6 | Calibration contract: unsupported (α, lags, N, m) combinations fail loudly; recorded df and critical values match the calibration object |
| 7 | Determinism: identical model, observations, prior, and calibration ⇒ bit-identical result fields; filter retains no state between batch calls; differing nominal seeds handled statistically (obligation 2), never individually required to pass |
| 8 | Validation: dimension, symmetry, PSD, finite-value, lag-length, empty-input, and singular-S failures explicit |
| 9 | Result object has no verdict field; docstrings carry the §1 necessary-not-sufficient and classical-telemetry-only boundaries (asserted) |
| 10 | Existing suite green: 389 with qiskit (368+1 skip without — count recorded per environment) |

## 5. Out of scope (unchanged + review additions)

Telemetry instantiation of the twin; probe/watermark cross-correlation (TWIN-2); multivariate portmanteau whiteness; Gaussianity/higher-cumulant tests; attack-class enums, ROC artifacts, navigation models, qDISH-specific parameters; any security verdict; any LINK-lane file, emission, schema, or control; SciPy.

## 6. Implementation record (2026-08-12)

Implemented by a Sonnet subagent; reviewed top-tier. **Result: 414 passed** (389 baseline + 25 new; zero skips/xfails; suite ~5s — a bit-identity-verified scalar fast path avoids per-step numpy overhead). Realized statistics all inside predeclared bands: honest ensemble rejections 14 (whiteness) / 9 (NIS) of 200 vs band [3, 19]; same-law synthesis 10/8 with two-sample differences −4/−1 vs exact-convolution band [−11, 11]; wrong-dynamics whiteness power 50/50; memoryless-mismatch NIS power 50/50 both directions with whiteness staying null (2/50, band [0, 7]). **Independent review verification with fresh master seeds never used by the tests:** honest 7/10, same-law synthesis 12/11 (calibrated blindness confirmed — indistinguishable from honest, as the theorem predicts), wrong-dynamics power 50/50 — the calibration is correct, not seed-tuned. Files: `src/qkd/twin.py` +697, `tests/test_twin_whiteness.py` +694.

Three recorded ambiguity resolutions, reviewed and accepted: the two-sample band derived by exact convolution of two Binomial(200, 0.05) via the same two-tail method as the plan's own [3, 19]; the n=50 null band recomputed with the identical construction → [0, 7]; (q, r) = (1.0, 0.5) fixed uniformly before any seed. χ² critical values computed by a self-contained regularized-incomplete-gamma bisection, cross-checked offline against SciPy (which the module does not import).

**Standing-claim upgrade discharged:** the covariance-gating result is now temporal-second-order-diagnostic-checked (whiteness + NIS), per the v2.1 note's narrowed language — the sequencing note's oldest open item is closed, and the qDISH evidence trail has its first artifact.

## 7. Execution note

Implementation against the 389-green baseline. Independent review verifies: the ensemble-calibration statistics (obligations 2/4 — the R1 correction, this PR's scientific core), the memoryless construction's white-but-NIS-rejected behaviour (obligation 5), and the §1 claim-scope language before merge. A genuine ambiguity is recorded for review, not resolved by invention.
