# LINK-4 PR Plan — Stochastic Exogenous Effects: Scintillation Fading and Pointing Jitter (Seeded; PDT Surface)

**Status:** **v2 — APPROVED FOR IMPLEMENTATION** (Echo review 2026-08-11, disposition "approve after targeted revision"; R1–R7 + test amendments incorporated)
**Date:** 2026-08-11
**Governing ADR:** ADR-0003 (RATIFIED 2026-07-17), LINK queue §8; honesty taxonomy §4.
**Depends on:** LINK-3 (merged, `main` @ `223d25c`; 294-test suite green). Discharges the LINK-1 §12 forward flag (`transmittance_factor ∈ [0,1]`) as an explicit design item.
**Module shape (fixed):** `src/qkd/effects.py`, `src/qkd/link.py`, `tests/test_link4_effects.py`. No change to `mission.py`, `orbit.py`, `channel.py`, `schema.py`, `run.py`, or the production stack. No cloud process, correlated OU path, gamma-gamma model, total-PDT estimator integration, or schema extension.

---

## 1. The central model declaration (R1 — revised semantics)

**Binding docstring language:** "`ScintillationFadingEffect` samples the stationary one-time marginal of the declared weak-turbulence log-normal model. Samples at different `sample_index` values are **independent by model definition**. For the current default mission grid (Δt ≈ 0.477 s) and the dynamics-spec reference τ_c = 3 ms, the omitted OU correlation is ρ = e^(−Δt/τ_c) ≈ 9×10⁻⁷⁰ and is negligible at simulator precision. This effect does not represent an OU path or preserve temporal correlation. A caller requiring correlation, or using a cadence not demonstrably separated from the relevant coherence time, must use the Exp-1 path generator."

The effect is described throughout as an **i.i.d. stationary-marginal effect** — never as "the exact finite-Δt OU joint law" (the marginal is exact under the declared model; the independence is a declared, quantified-negligible approximation of the joint law). Correlated processes remain architecturally possible later (indexed innovations + deterministic reconstruction, or a block/path generator); they do not belong in this stateless mission-cadence effect. Class name stays `ScintillationFadingEffect` (PI choice) with the binding docstring carrying the boundary.

The jitter effect is likewise an **i.i.d. per-index component-jitter model by definition** (R2) — no decorrelation-rate claim is made for platform jitter; temporally correlated jitter requires a measured/declared spectrum and is deferred to the fine-timescale generator.

## 2. The physics

### 2.1 `ScintillationFadingEffect`

Per sample, elevation-coupled (channel-dynamics spec, Generator B), with **log-irradiance** (not log-amplitude) variance (R3.1):

```
σ_R²(E)      = rytov_variance_zenith · (sin E)^(−11/6)
log_variance = ln(1 + aperture_averaging · σ_R²(E))          [log-irradiance / log-fading variance]
sigma_log    = sqrt(log_variance)                            [standard deviation of log-factor]
mu_log       = −log_variance / 2                             [pure-fading normalization: E[factor] = 1]
X            = rng.normal(loc=mu_log, scale=sigma_log)       [NumPy scale = std dev, NOT variance]
transmittance_factor = exp(X)                                [relative irradiance; E = 1; values > 1 by construction]
```

One **private parameter resolver** `_law_parameters(geom) -> (mu_log, sigma_log)` is the single code path used by both `evaluate()` and `stationary_law()` (R6) — elevation validation, Rytov policy, and the two law parameters cannot drift between sampling and declaration.

**Elevation validation (R4):** `geom.elevation_deg` must be non-None, finite, and in (0, 90] — zero/negative/NaN/above-zenith raise naming the effect and constraint, through *both* entry points.

**Weak-regime policy (R4):** fixed reference guard `RYTOV_WEAK_GUARD = 1.0` (a model-validity policy, not a physical discontinuity). Parameter `allow_out_of_regime: bool = False`. When σ_R²(E) exceeds the guard: default → raise naming the model, elevation, computed σ_R², and guard; with `allow_out_of_regime=True` → continue with the same log-normal approximation, documented as **an explicit out-of-regime approximation, not a validated strong-turbulence model**. No numeric threshold parameter — changing a number must not silently redefine validity. Regime statement (binding): "The v1 log-normal law is restricted to the declared weak-scintillation regime. Moderate or strong scintillation requires a separately selected and validated model; gamma-gamma is the planned v2 candidate." Note the concrete trap this guards: `rytov_variance_zenith = 0.1` at a 10° horizon gives σ_R² ≈ 2.5 — the defaults leave the regime near the horizon; at a 25° mask, σ_R² ≈ 0.49 is comfortably inside.

Domains: `rytov_variance_zenith` finite ≥ 0; `aperture_averaging` finite ∈ (0, 1]. Construction-time via the `_require` pattern.

### 2.2 `PointingJitterEffect`

```
θ_x, θ_y ~ N(0, σ_j²) with component standard deviation σ_j = jitter_sigma_urad
           (two draws, fixed order, one stream)
transmittance_factor = exp(−2·(θ_x² + θ_y²) / beam_divergence_urad²)          domain [0, 1]
```

Output domain is **[0, 1]** — large finite σ_j/θ_div underflows to exactly 0.0 (R3.2), matching LINK-3's corrected pointing contract. Analytic mean: E[factor] = 1/(1 + 4σ_j²/θ_div²). Same receiver-centre/small-aperture approximation language as LINK-3, binding. **Bias + jitter (R3.3):** "Exact joint treatment of deterministic bias and isotropic Gaussian jitter gives a Rician/noncentral-χ² radial model; Beckmann is the broader anisotropic extension. Both the cross term and finite-aperture overlap are deferred." Multiplying LINK-3's deterministic bias factor with this jitter factor is approximate and documented as such. Domains: `jitter_sigma_urad` finite ≥ 0; `beam_divergence_urad` finite > 0. No geometry requirement.

Fixed canonical IDs: `scintillation_fading`, `pointing_jitter`. Neither joins the production stack.

## 3. Indexing contract (R2 — binding)

Both stochastic effects **require an explicit sample index**: if `context.sample_index is None`, evaluation raises naming `sample_index` (with `index=None`, the LINK-1 runtime would resolve the same purpose stream every call and silently repeat one draw across all geometries — the failure this rule prevents). Effects call `context.rng_for("fade")` / `context.rng_for("jitter")` with no index argument, letting the stack-owned context supply the already-validated index. Same `(seed, effect_id, purpose, sample_index)` ⇒ bit-identical draw across repetition, call order, and fresh stack instances; different indices select different child streams. **Independent-index semantics is the model contract — empirical whiteness in one finite sample is a tripwire, not the proof.**

## 4. The [0,1] bound revisit (LINK-1 §12 flag — discharged; R5 contract)

Duck-typed declaration `unit_mean_fading_fields`, tightened:

1. Validated and normalized at **`ChannelStack` construction**: bare strings and malformed iterables rejected (never iterated as characters); only `"transmittance_factor"` recognized in LINK-4; unrecognized names raise at construction; the recognized declaration is cached per effect ID.
2. The cached declaration is passed into raw-observable validation so **only the declaring effect** receives the relaxed rule (finite and ≥ 0) for that field; undeclared effects keep the strict [0, 1] bound.
3. The bridge's folded-total-transmittance validation (η ∈ [0, 1], raise — never clamp) is unchanged and remains the no-gain law.
4. **Timing note (binding honesty):** the existing `correlated_fields` guard validates at evaluation in the pushed code; LINK-4 validates only its *new* declaration at construction and does not claim identical failure timing, nor change the older guard.
5. The attribute is a **semantic declaration, not proof**: the stack validates the allowed domain; the effect's analytic/statistical tests validate the unit-mean claim.

## 5. PDT surface (R6 — a relative-fading law, not the total PDT)

`ScintillationFadingEffect.stationary_law(geom) -> LogNormalLaw` — frozen dataclass with fields `mu_log` (mean of log-factor) and `sigma_log` (**standard deviation** of log-factor, stated explicitly). **Binding scope language:** "`stationary_law(geom)` exposes the one-time log-normal law of the *relative* scintillation factor. Exp-1/LINK-6 may combine or scale this law with the deterministic channel state and any other stochastic layers to construct the block-level total-transmittance PDT before estimator nonlinearities." It is not the distribution of total channel transmittance. Analytic identity: exp(mu_log + sigma_log²/2) = 1 within floating precision (tested). Shares `_law_parameters` with `evaluate()`; tested against a hand-computed oracle, not merely sample moments (code-path identity ≠ moment agreement).

## 6. Replay and provenance boundary (R7)

**What LINK-4 proves:** given the same externally supplied effect configuration, seed, and mission inputs, emission bytes are identical (and deep-schema-valid). **What it does not claim:** that an emitted artifact is independently replayable from its own record — the emission contains no `link_seed`, effect IDs, or effect parameters, and `audit_record()` is not emitted and carries no parameter values. Emitted stochastic-run provenance is recorded as a **prerequisite for results intended to stand alone as reproducible research artifacts**, most naturally landing with LINK-6's estimator/run-metadata integration. No schema expansion in LINK-4.

## 7. Tests (Echo-amended)

**Statistical oracles (constant geometry, fixed law parameters; tolerances derived analytically from the normal/log-normal variance and the sample count *before* pinning the seed — bands are never chosen against the realized draw):**

| # | Test |
|---|---|
| 1 | `mu_log`/`sigma_log` vs hand-computed formula at chosen elevations (tight tolerance); log-sample mean ≈ mu_log, log-sample variance ≈ sigma_log², factor mean ≈ 1.0, each within predeclared analytic bands at stated sample count |
| 2 | Elevation coupling: sigma_log strictly increasing as E decreases |
| 3 | Jitter: domain [0, 1] incl. explicit finite-parameter underflow-to-exactly-0.0 case; seeded mean within predeclared band of 1/(1 + 4σ_j²/θ_div²); zero-jitter ⇒ factor ≡ 1.0 |
| 4 | `stationary_law` fields vs independent hand-computed oracle; `exp(mu_log + sigma_log²/2) == 1` within float precision; shares the private resolver with `evaluate` (asserted structurally, e.g. via a counting/spy resolver or code-path test) |

**Indexing and replay:**

| # | Test |
|---|---|
| 5 | `sample_index=None` ⇒ both effects raise naming `sample_index` |
| 6 | Same (seed, index) bit-identical across repetition, out-of-order evaluation, and fresh stacks; different indices differ (tripwire, documented as such) |
| 7 | Mission replay on a **demonstrably in-regime configuration** (e.g. 25° mask): same `link_seed` ⇒ byte-identical emission via `run._build_results()`, deep-schema-valid; different seed ⇒ different bytes |
| 8 | `SeedRequiredError` from `simulate_pass` with stochastic effects and no `link_seed` |

**Rytov policy (split per review — the default 10° pass with default zenith Rytov exceeds the guard):**

| # | Test |
|---|---|
| 9 | Horizon-inclusive opt-in run with spec-default scintillation parameters raises the model-validity error naming model/elevation/σ_R²/guard |
| 10 | `allow_out_of_regime=True` permits the horizon-inclusive run; test names it an approximation |
| 11 | Guard boundary tested directly on σ_R² values (not via fragile float equality through sin(E)); elevation domain: None, NaN, ±inf, 0, negative, > 90 all raise through both entry points |

**Declaration and bridge:**

| # | Test |
|---|---|
| 12 | Construction-time rejection of unknown and malformed (incl. bare-string) `unit_mean_fading_fields`; recognized declaration accepted |
| 13 | Real scintillation effect at an index with factor > 1 accepted; undeclared effect emitting 1.5 rejected; relaxation applies **only** to the declaring effect (mixed-stack test) |
| 14 | Synthetic bridge test: fade-up onto high base transmittance ⇒ `apply_link_state` raises (never clamps); full in-regime seeded pass stays within the bridge domain — described as a pinned-seed regression case, not a universal probabilistic guarantee |

**Boundaries and regression:**

| # | Test |
|---|---|
| 15 | Construction domains for all parameters (NaN, ±inf, negatives; `aperture_averaging` ∈ (0,1] strictness) |
| 16 | Composition with LINK-3 deterministic pointing bias: product relation (same-order arithmetic), documented approximate |
| 17 | Frozen-hash, captured-fixture, LINK-1/2/3 tests pass unmodified; default emission byte-identical |
| 18 | Full suite green from the certified 294-test parent baseline plus the new tests |

## 8. Risks

- **Statistical flake**: impossible at test time — fixed seeds make assertions deterministic; tolerance rationale predeclared (R-amendment) so the tests can't bless an accidental implementation.
- **Model misuse**: §1/§2 binding docstrings ship verbatim; `allow_out_of_regime` makes out-of-regime use a visible, named choice.
- **Declaration abuse**: construction-time validation + effect-specific caching + undeclared backstop + unchanged bridge law (R5).
- **Provenance overclaim**: §6 boundary keeps replay claims inside what the artifact actually contains.

## 9. Out of scope (explicit)

Cloud/obscuration Markov layer (Exp-1 generator — correct omission per review; no placeholder effect); correlated OU path stepping and any sub-block temporal structure (Exp-1); total-channel PDT construction and estimator integration incl. E̅ₓ aggregation (LINK-6/Exp-1 gates); gamma-gamma or any moderate/strong-scintillation model (v2 candidate, separately validated); Rician/Beckmann biased-jitter and displaced-aperture overlap; emitted stochastic provenance/schema extension (LINK-6 prerequisite, recorded in §6); afterpulsing, dead time, μ fluctuation (LINK-5); production-stack membership; controls.

## 10. Implementation record (2026-08-11)

Implemented by a Sonnet subagent; reviewed top-tier against this plan. **Result: 347 passed** (294 baseline + 53 new; zero skips/xfails); frozen-hash and all prior-lane tests unmodified; end-to-end `qkd.run` emission hash still equals the original frozen baseline `3d154402…1417` (five PRs, default output unmoved). Statistical oracles landed 1–3 standard errors inside their predeclared 5-SE analytic bands. Independent review checks (fresh seed, never used by tests): law identity `exp(mu_log + sigma_log²/2) = 1.0` exact; factor mean 0.9995 over 2001 draws (fade range 0.29×–2.64×); mission replay byte-identical per seed, divergent across seeds. Files: `effects.py` +281, `link.py` +99, `tests/test_link4_effects.py` +748. Implementation niceties noted at review: `log1p` for the log-variance (accurate at small A·σ_R²); index-required raise placed before any drawing.

Two recorded ambiguity resolutions, reviewed and accepted: (1) "spec-default scintillation parameters" resolved from the channel-dynamics spec's defaults table (σ_R,zen² = 0.10, A_ap = 0.3), which reproduce this plan's own worked examples; (2) the shared-resolver structural assertion implemented via a test-only spy (`mock.patch.object`), no production change.

## 11. Execution note

Implementation proceeds against the certified LINK-3 baseline (294 green), followed by independent review of the statistical oracles (tests 1–4), the indexing contract (5–6), the Rytov policy split (9–11), and the §4 `link.py` validation dispatch before merge. All design decisions are made in this plan; a genuine ambiguity is recorded for review, not resolved by invention.
