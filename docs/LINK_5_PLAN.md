# LINK-5 PR Plan — Source/Detector Realism: μ Fluctuation, Afterpulsing, Dead Time

**Status:** **v2 — APPROVED FOR IMPLEMENTATION** (Echo review 2026-08-11, disposition "approve after targeted revision"; R1–R6 + test amendments incorporated)
**Date:** 2026-08-11
**Governing ADR:** ADR-0003 (RATIFIED 2026-07-17), LINK queue §8. Source partition per ADR §2 ("source, channel, and detector effects").
**Depends on:** LINK-4 (merged; 347-test suite green).
**Module shape (fixed):** `src/qkd/link.py`, `src/qkd/effects.py`, `tests/test_link5_effects.py`. No changes to `mission.py`, `channel.py`, `schema.py`, `run.py`, `signals.py`, the estimator, or the default production stack.

**The architectural sentence (per review):** add the typed source and detector parameters now, but make the **epistemic boundary as explicit as the physical partition** — `EffectiveLinkState` may know the simulated truth; the future QKD estimator may use only what the modeled system can legitimately observe or certify.

---

## 1. The source partition

### 1.1 Types (backward-compatible defaulted additions)

```python
@dataclass(frozen=True)
class SourceObservables:
    intensity_factor: float = 1.0

@dataclass(frozen=True)
class LinkObservables:
    channel: ChannelObservables = ChannelObservables()
    detector: DetectorObservables = DetectorObservables()
    source: SourceObservables = SourceObservables()          # NEW

@dataclass(frozen=True)
class EffectiveLinkState:
    channel: ChannelObservables
    detector: DetectorObservables
    source: SourceObservables = SourceObservables()          # NEW
```

Internal type-shape change recorded explicitly: `repr`/equality/`asdict` shapes of both classes change; constructor calls do not; the byte-identity claim applies to the emitted artifact (frozen hashes), not internal representations.

### 1.2 Epistemic contract (R1 — binding docstring)

> "`intensity_factor` is the **realized physical** common-mode multiplier on the nominal mean photon numbers for the modeled epoch. It is **latent simulation truth** unless a separate monitoring/characterization interface declares what information is available to the protocol. Presence in `EffectiveLinkState` does not authorize an estimator to observe the exact value."

This is the ADR-0002 wall applied at the estimator's information surface: folding realized latent factors into the estimator would grant oracle knowledge a real system obtains only through source monitoring or calibration. Decoy-state security can be invalidated by source-intensity correlations and unmodeled source errors (Sixto, Zapatero & Curty, arXiv:2206.06700; Trefilov et al., arXiv:2411.00709) — the boundary is load-bearing, not defensive wording.

### 1.3 Epoch-common semantics (R2 — binding docstring)

> "Each indexed evaluation draws one common multiplicative source factor for the complete modeled mission epoch. The factor scales every nonzero nominal intensity setting in that epoch. Multiplication preserves exact zero (a true vacuum setting stays zero; a nonzero nominal 'vacuum' is scaled like the other settings). It does not model pulse-resolved fluctuations, setting-conditioned error distributions, or correlations with previous intensity choices. Those require a pulse/block generator and a compatible security analysis."

`sample_index` indexes a pass/profile epoch, not an optical pulse — this is **block/epoch-common calibration fluctuation** by declaration.

### 1.4 Composition, validation, bridge

- `intensity_factor` composes as a **product**; the composed result is validated finite and ≥ 0 (multiplication overflow rejected).
- Strict default validation finite ∈ [0, 1]; values > 1 only via the `unit_mean_fading_fields` declaration, whose recognized set becomes `{"transmittance_factor", "intensity_factor"}` with **partition-aware resolution** (R5): each recognized name maps to its typed path (`channel.transmittance_factor` / `source.intensity_factor`); a declaration for one field does not relax the other field on the same effect. All LINK-4 declaration mechanics (construction-time normalization, malformed/bare-string rejection, per-effect caching, effect-specificity) unchanged and re-asserted; LINK-4 transmittance behaviour and the bridge η ≤ 1 law unchanged; `audit_record()` unchanged.
- `apply_link_state` extends its non-identity rejection set with `source.intensity_factor` (identity 1.0), raising `UnsupportedLinkObservableError` naming the field. All three LINK-5 observables are therefore bridge-rejected — the essential anti-smuggling boundary.

## 2. The effects

### 2.1 `MuFluctuationEffect(relative_sigma)` — stochastic, epoch-common, i.i.d. (LINK-4 pattern)

```
sigma_log² = ln(1 + relative_sigma²)      [relative_sigma = RMS relative fluctuation, std/mean]
mu_log     = −sigma_log²/2                [unit mean]
X ~ N(mu_log, sigma_log)  from context.rng_for("mu")      [scale = std dev]
intensity_factor = exp(X)
```

Declares `unit_mean_fading_fields = {"intensity_factor"}`. Fixed ID `mu_fluctuation`. Full indexing contract (raise on `sample_index is None`, before drawing). **Numerical contract (R4, overflow-safe disposition):** construction computes and validates that derived `sigma_log_sq`, `sigma_log`, `mu_log` are all finite (a huge-but-finite `relative_sigma` whose square overflows fails loudly at construction, not silently at first draw); evaluation validates the sampled factor is finite before emitting (never leaks `inf`/`NaN`/`OverflowError` as an accepted observable); the stack's composed-source validation is the backstop. **Zero-variance case (pinned):** the class is stochastic by contract — `relative_sigma = 0` still draws (a scale-0 normal), still requires seed and index, and yields factor ≡ 1.0 exactly; consistent with LINK-4's zero-jitter behaviour. Typical magnitudes percent-level. No geometry requirement.

### 2.2 `DetectorAfterpulsingEffect(afterpulse_prob)` — static parameter owner

Domain finite ∈ [0, 1]; fixed ID `detector_afterpulsing`. **Binding contract (R3.1):** "`afterpulse_prob` is a nominal/calibrated *conditional* afterpulse-probability parameter under a declared detector operating convention. It is not an independent additive count probability or a context-free material constant. LINK-6 must define its conditioning event, counting window/gate model, and interaction with dead time before use." (Afterpulse estimation is calibration- and rate-dependent; cf. Wiechers et al., gated-APD afterpulsing.) Ignores `context`.

### 2.3 `DetectorDeadTimeEffect(dead_time_s)` — static parameter owner

Domain finite ≥ 0; fixed ID `detector_dead_time`. **Binding contract (R3.2):** "`dead_time_s` is the detector recovery/hold-off duration parameter. LINK-5 assigns no throughput law. LINK-6 must declare the detector timing model (non-paralyzable, paralyzable, or gated/hold-off) and the rate variable to which the parameter applies." Ignores `context`.

Both single-contributor fields are **passed unchanged when exactly one nonzero contributor exists** (not "composed" — LINK-1 deliberately rejects a second nonzero contributor). One afterpulse contributor and one dead-time contributor may coexist; only two contributors to the *same* field conflict.

## 3. LINK-6 source/detector-consumption gate (consolidated, per review — binding)

> Before any LINK-5 observable is folded into gains, errors, or key rate, LINK-6 must declare: (1) the realized-versus-observed source-intensity information model; (2) a decoy-state proof valid for the selected intensity uncertainty and correlation assumptions; (3) the detector dead-time response convention; (4) the afterpulse conditioning/window or kernel model; and (5) the interaction order or joint model for dead time and afterpulsing. Until all applicable items are present, non-identity LINK-5 observables remain bridge-rejected.

## 4. Tests (Echo-amended)

**Source law and semantics:**

| # | Test |
|---|---|
| 1 | Backward compatibility: existing-style `LinkObservables(channel=…, detector=…)` and `EffectiveLinkState(channel, detector)` carry identity source; all prior-lane tests pass unmodified |
| 2 | `sigma_log_sq`/`sigma_log`/`mu_log` vs **independently hand-computed** expected values (the `exp(mu+σ²/2)==1` identity is retained but noted as near-tautological alone); seeded moments (log-mean, log-variance, factor mean) within predeclared analytic bands at stated sample count |
| 3 | Epoch-common contract (pure unit test, pre-LINK-6): one draw per epoch; a hypothetical fold scales all nonzero settings identically; exact zero preserved |
| 4 | Not-exposed check: `intensity_factor` reachable through no `DetectorParams`, `ChannelState`, or current estimator path |
| 5 | R4 numerics: huge-but-finite `relative_sigma` fails loudly at construction (derived-parameter finiteness); non-finite sampled factor cannot be emitted; composed-product overflow rejected; `relative_sigma=0` draws, requires seed+index, factor ≡ 1.0 exactly |
| 6 | `intensity_factor` product composition (hand-computed, same-order) with composed result validated finite/≥ 0 |

**Declarations:**

| # | Test |
|---|---|
| 7 | Recognition set extended: `intensity_factor` declarable; unrecognized names raise at construction; malformed/bare-string rejected; **partition-aware**: declaring `intensity_factor` does not relax `transmittance_factor` on the same effect and vice versa (same-effect cross-check); mixed-stack effect-specificity; LINK-4 transmittance declaration behaviour byte-for-byte unchanged; `audit_record()` unchanged |
| 8 | Strict default [0, 1] for undeclared `intensity_factor`; declared unit-mean factor > 1 accepted (finite ≥ 0) |

**Indexing/replay:**

| # | Test |
|---|---|
| 9 | `sample_index=None` raises naming `sample_index`; same (seed, effect_id, purpose, index) bit-identical across repetition/order/fresh stacks; different indices differ (worded as a stream-separation tripwire, not independence proof) |
| 10 | `SeedRequiredError` without `link_seed`, including the zero-variance effect (stochastic by contract) |

**Detector:**

| # | Test |
|---|---|
| 11 | Static domains: `afterpulse_prob` boundaries 0 and 1 accepted, `dead_time_s = 0` accepted (documented: parameter acceptance ≠ every later detector law well-defined at every boundary); NaN/±inf/negatives rejected at construction |
| 12 | Real afterpulsing + distinct-ID nonzero mock ⇒ single-contributor conflict; same for dead time; **afterpulse + dead-time contributors coexist** (different fields); values pass through the stack unchanged; duplicate fixed IDs collide |

**Bridge and regression:**

| # | Test |
|---|---|
| 13 | Direct `apply_link_state` source-rejection test (bridge contract pinned without mission plumbing) **and** the three `simulate_pass` rejections naming `source.intensity_factor`, `detector.afterpulse_prob`, `detector.dead_time_s` |
| 14 | Frozen-hash, captured-fixture, and all LINK-1/2/3/4 tests pass unmodified; default emission byte-identical |
| 15 | Full suite green from the certified 347-test parent baseline plus the new tests |

## 5. Risks

- **Epistemic leak**: prevented structurally (bridge rejection) and contractually (§1.2 + §3 gate); test 4 pins the current-path non-exposure.
- **Type-shape ripple**: defaulted fields, constructor-compatible; recorded openly; frozen hashes are the emission tripwire.
- **Numerical leak**: R4 disposition closes the overflow path at construction, evaluation, and composition — three layers.
- **Declaration cross-partition confusion**: partition-aware resolution + same-effect cross-check (test 7).

## 6. Out of scope (explicit)

All §3 gate items (LINK-6); per-setting-independent or correlated/pulse-resolved source noise and source memory; joint afterpulse/dead-time detector model; production-stack membership; controls; schema changes; emitted stochastic provenance (LINK-6 prerequisite per LINK-4 §6).

## 7. Implementation record (2026-08-11)

Implemented by a Sonnet subagent; reviewed top-tier against this plan. **Result: 389 passed** (347 baseline + 42 new; zero skips/xfails); all prior-lane tests and frozen hashes unmodified; end-to-end `qkd.run` emission hash still equals the original frozen baseline `3d154402…1417` — six PRs, default output unmoved. Statistical oracles inside predeclared bands. Independent review checks (fresh seed): all three bridge rejections fire naming their fields; unit mean 1.00064 over 1501 draws; huge-finite `relative_sigma` raises at construction; zero-variance effect still requires seed. Files: `link.py` +176 (incl. the `_UNIT_MEAN_FADING_FIELD_PARTITION` typed-path mapping), `effects.py` +252, `tests/test_link5_effects.py` +821.

**One implementation-level catch by the subagent, reviewed and endorsed:** CPython's `**` and `math.exp` raise `OverflowError` rather than returning `inf` (unlike `*`), which would have let an uncaught arithmetic exception escape instead of the plan's controlled, named failure. Resolved with `relative_sigma * relative_sigma` at construction and a guarded `math.exp` at evaluation, so both overflow paths surface as the intended contract-naming `ValueError`. No plan ambiguities were recorded — the LINK-4 patterns fully determined the remaining choices.

## 8. Execution note

Implementation proceeds against the certified LINK-4 baseline (347 green), followed by independent review of the epistemic/epoch-common contracts (§1.2–§1.3 verbatim), the R4 numerical layers (test 5), and the partition-aware declaration change in `link.py` (test 7) before merge. All design decisions are made in this plan; a genuine ambiguity is recorded for review, not resolved by invention.
