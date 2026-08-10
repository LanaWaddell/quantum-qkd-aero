# LINK-2 PR Plan — Migrate Existing Loss/Detector Constants into the Effect Framework

**Status:** **v2 — APPROVED FOR IMPLEMENTATION** (Echo review 2026-08-10, disposition "approve after targeted revision"; R1–R5 + test amendments incorporated; PI disposition on R1: **bounded input-domain hardening in this PR**, 2026-08-10)
**Date:** 2026-08-10
**Governing ADR:** ADR-0003 (RATIFIED 2026-07-17), LINK queue §8
**Depends on:** LINK-1 (merged, `main` @ `8b7ef46`; 219-test suite green)

**Disposition (binding summary).** LINK-2 migrates the existing satellite system, atmospheric, geometric, and detector-efficiency factors into fixed-ID production effects, evaluated in a parity-pinned order through the LINK-1 bridge. It adds no new physics or estimator behaviour. Byte parity is certified in-process against the retained inline reference **over the explicitly declared accepted input domain**; normalization of previously unvalidated out-of-domain inputs is a separately declared and tested behaviour change — this PR is **migration plus input-domain hardening**, not an unconditional pure refactor.

---

## 1. What migrates, and what deliberately does not

**Migrates:**

| Existing computation | Becomes | Observable |
|---|---|---|
| `cfg["system_efficiency"]` (constant) | `SystemEfficiencyEffect` | `transmittance_factor` |
| `atmospheric_transmittance(elevation, zenith_optical_depth)` | `AtmosphericAbsorptionEffect` | `transmittance_factor` (from `geom.elevation_deg`) |
| `geometric_transmittance(slant_range, divergence, aperture)` | `GeometricLossEffect` | `transmittance_factor` (from `geom.slant_range_km`) |
| `DetectorParams.detection_efficiency` (constant) | `DetectorQuantumEfficiencyEffect` | `efficiency_factor` |

**Does not migrate (scope boundary):**

- `werner_p`, `intrinsic_qber` — source/channel/protocol parameters; `channel_state()` keeps owning them unchanged (Werner quality intentionally independent of atmospheric loss, per `channel.py`).
- **Dark counts (corrected rationale, R3):** `ChannelState.dark_count_prob` remains unchanged as channel-model provenance. `DetectorParams.dark_count_prob` is the authoritative detector-window probability consumed by `run_decoy_bb84()`, but LINK-1 represents physical dark counts as `dark_count_rate_hz`; conversion requires a defined gate/coincidence window and is deferred to LINK-6. LINK-2 therefore migrates detector **quantum efficiency only**.
- `sky_condition` / background-light path — background is a rate observable with no estimator integration until LINK-6; the LINK-1 bridge correctly rejects it until then.
- The **fibre** path — its migration is the evidence-gathering step for ratification decision 4 and is its own later PR.
- `error_correction_efficiency` — protocol-side constant, not a physical link observable.

## 2. Byte parity over the declared domain (the heart of this PR)

### 2.1 Declared accepted input domain (R1 — PI disposition: bounded hardening)

The pre-LINK-2 inline path validates nothing: `channel_state()` accepts any `system_efficiency`, multiplies, and clamps only the aggregate (e.g. `system_efficiency=10.0` is silently accepted today and yields finite η). The LINK pipeline validates each factor. These domains differ, so parity is claimed **only over the declared domain**:

| Input | Accepted domain |
|---|---|
| `system_efficiency` | finite, ∈ [0, 1] |
| `detection_efficiency` (QE) | finite, ∈ [0, 1] |
| `zenith_optical_depth` | finite, ≥ 0 |
| `beam_divergence_urad` | finite, ≥ 0 |
| `rx_aperture_m` | finite, ≥ 0 |

**Behaviour change, declared and tested:** configurations outside this domain — previously accepted silently by the inline path — now **fail loudly at effect construction** (§4). No silent fallback to the inline path for invalid factors (stack ownership must not be configuration-dependent). Tests lock this behaviour explicitly (§6 test 12).

### 2.2 The float argument (within the declared domain)

1. **Left-associated product.** Baseline: `eta = (s * a) * g`. Stack with pinned order `[system, atmospheric, geometric]`: `((1.0 * s) * a) * g`. `1.0 * x == x` exactly in IEEE-754, so the sequences are bitwise identical. **Registration order is part of the parity contract**; reordering is parity-breaking by definition.
2. **Exact folds.** Base `ChannelState` built with `eta_override=1.0`: fold `1.0 * P == P`. Base detector `detection_efficiency=1.0`: fold `1.0 * QE == QE`.
3. **Clamp no-op within the domain.** Every factor ∈ [0, 1] ⇒ product ∈ [0, 1] ⇒ the retained aggregate clamp never fires; on the migrated path it runs against `eta_override=1.0` (also no-op). Outside the domain, §2.1 applies instead — parity is not claimed there.
4. **User effects preserve order.** Appended after production effects: `((P * u1) * u2)…` — the same left-association a pre-LINK-2 user multiplication would have produced.

**No formula duplication:** effects call the existing verified `atmospheric_transmittance()` / `geometric_transmittance()` with identical arguments — same code, same bits, same raises for their own argument validation.

## 3. Module layout

```
src/qkd/effects.py       # NEW — production effect library (four effects; ~170 LOC)
src/qkd/mission.py       # production assembly helper + seam semantics update (~50 LOC delta)
src/qkd/channel.py       # MECHANICAL CHANGE ONLY (R2): resolved_atmosphere_config() helper
                         #   extracted; channel_state() consumes it; formula and direct-call
                         #   behaviour unchanged
tests/test_effects.py    # NEW — parity oracle + per-effect anchors (~400 LOC)
```

`link.py` untouched. `MissionConfig` untouched (no stack-bearing field — settled by LINK-1).

## 4. The four effects (spec — R4 shapes)

Fixed, non-overridable production IDs via `field(init=False)`; required numeric parameters; **construction-time validation** in `__post_init__` against the §2.1 domain (a shared private `_require(name, value, *, lo, hi)` helper — not four ad-hoc rule sets):

```python
@dataclass(frozen=True)
class SystemEfficiencyEffect:
    system_efficiency: float
    effect_id: str = field(default="system_efficiency", init=False)
    def __post_init__(self): ...            # finite, in [0, 1] — raises ValueError at construction

@dataclass(frozen=True)
class AtmosphericAbsorptionEffect:
    zenith_optical_depth: float
    effect_id: str = field(default="atmospheric_absorption", init=False)
    def __post_init__(self): ...            # finite, >= 0

@dataclass(frozen=True)
class GeometricLossEffect:
    beam_divergence_urad: float
    rx_aperture_m: float
    effect_id: str = field(default="geometric_loss", init=False)
    def __post_init__(self): ...            # both finite, >= 0

@dataclass(frozen=True)
class DetectorQuantumEfficiencyEffect:
    detection_efficiency: float
    effect_id: str = field(default="detector_qe", init=False)
    def __post_init__(self): ...            # finite, in [0, 1]
```

**Failure timing (binding, R4):** invalid *numeric parameters* fail at **effect construction** (`__post_init__`). Missing *geometry* (`elevation_deg is None` / `slant_range_km is None` from a non-satellite provider) fails at **evaluation** with a clear error naming the effect and field (these two are satellite-medium members; the contract stays neutral). Per-evaluation *factor* validation by `ChannelStack` (LINK-1) is unchanged and remains the composition-time backstop. All four effects ignore `context` (no controls, no RNG — "a constant is a function that ignores t").

## 5. Mission seam (R2 + implementation shape)

Flow (binding):

1. `simulate_pass` builds its one `SatellitePass` exactly as today.
2. Wraps that exact pass in `TableGeometryProvider` (no second geometry object).
3. Resolves atmosphere configuration through the **single shared resolver** `channel.resolved_atmosphere_config(cfg.atmosphere)` — the same helper `channel_state()` now consumes internally (R2; one implementation, two consumers).
4. Assembles production effects via a private helper `_production_link_effects(resolved_cfg, detector)` returning the pinned order `[SystemEfficiencyEffect, AtmosphericAbsorptionEffect, GeometricLossEffect, DetectorQuantumEfficiencyEffect]`; user `link_effects` appended after. The helper is the *only* place the four reserved IDs and the parity order live; its return order is tested directly.
5. Base channel states: `channel_state(..., atmosphere=cfg.atmosphere, eta_override=1.0)` — all non-η behaviour identical.
6. Base detector: `dataclasses.replace(cfg.detector, detection_efficiency=1.0)` — all other fields pass through untouched.
7. Evaluate the stack once per existing sample (explicit `sample_index`) and fold via the unchanged `apply_link_state`.
8. Continue through the unchanged profile/result/emission pipeline.

**Post-migration seam semantics (documented in the docstring):** `link_effects=None` and `link_effects=[]` both mean "production effects only" and are byte-identical to the pre-LINK-2 default. User effects colliding with the four reserved production IDs fail via LINK-1's existing `DuplicateEffectIdError`. All four production effects are time-constant on the detector side, so LINK-1's sample-varying-efficiency guard never fires (tested).

**`channel_state()` retains its inline η formula** as the independent parity oracle during the soak period; removal is a post-soak follow-up PR, not part of LINK-2.

## 6. Tests (Echo amendments incorporated)

| # | Test | Purpose |
|---|---|---|
| 1 | `test_migrated_emission_byte_identical_to_independent_inline_reference` — **two independently constructed results in one process** (R5): (a) inline reference reproducing the pre-migration pass body via direct `channel_state()` (no override), the same `SatellitePass`, `simulate_profile()`, and the existing result-construction helper; (b) the migrated stack-always `simulate_pass()`. Both through the real `run._build_results()`, canonicalized exactly as LINK-1 does; assert byte equality; `validate_results_schema(deep=True)` on **both** payloads | **The parity certificate** |
| 2 | LINK-1's `test_none_empty_identity_paths_byte_identical` passes **unmodified** | Regression guard on new None/empty semantics (supplements, does not replace, test 1) |
| 3 | `test_production_assembly_order_and_fixed_ids` — helper returns exactly the four pinned IDs in the pinned order; IDs are `init=False` (callers cannot override; attempted rename around collision checks impossible) | §2.2 contract + R4 |
| 4 | `test_atmospheric_effect_matches_function_bitwise` (parameterized: 90°, mid, near-horizon elevations) | Adapter honesty |
| 5 | `test_geometric_effect_matches_function_bitwise` (incl. range 0 → 1.0, zero divergence) | Adapter honesty + boundary |
| 6 | `test_detector_qe_fold_restores_original_exactly_once`; custom detector's `dark_count_prob` and `error_correction_efficiency` survive the identity-base + fold **unchanged** | §2.2 fact 2 + amendment 4 |
| 7 | `test_full_custom_atmosphere_parity` — vary **every** migrated atmosphere key simultaneously and individually; inline vs migrated bytes equal | Amendment 5 / single-resolver guard |
| 8 | `test_resolver_single_source` — `resolved_atmosphere_config()` used by both consumers; direct `channel_state()` calls (existing tests) unmodified and passing | R2 + amendment 6 |
| 9 | `test_user_effects_compose_after_production` — two user multiplicative effects; output bitwise equals `inline_baseline * u1 * u2` in that association | Amendment 8 |
| 10 | `test_user_effect_colliding_with_production_id_rejected` | Seam guard |
| 11 | `test_effects_raise_at_evaluation_on_missing_geometry_fields` | §4 failure timing |
| 12 | `test_out_of_domain_inputs_fail_at_construction` — parameterized: negative and >1 `system_efficiency`, invalid QE, negative τ₀/divergence/aperture, NaN/inf — **locks the R1 disposition** (previously-silent configs now raise, at construction) | R1 + amendment 3/9 |
| 13 | `test_domain_boundaries_accepted` — efficiencies at exactly 0.0 and 1.0, τ₀ = 0.0; parity holds at boundaries | Amendment 2 |
| 14 | `test_production_qe_constant_across_pass` — varying-efficiency guard never fires on the production stack | Amendment 10 |
| 15 | Full suite green (219 existing + new); no measurable pytest-duration regression | Regression |

The frozen pre-LINK-2 emission hash remains a separate per-environment regression tripwire; the binding parity proof is the in-process comparison (test 1), per the sequencing note's environment-locality finding.

## 7. Risks

- **Domain mismatch** (the real R1 risk — not float associativity): resolved by the declared domain + construction-time hardening + test 12. No silent inline fallback.
- **Float associativity**: §2.2 pinned order; any future production-stack insertion (LINK-3 Doppler) lands after `geometric_loss` and before user effects **unless a new parity argument is written** — stated in the assembly helper's docstring.
- **Config-resolution drift**: eliminated structurally by the shared resolver (R2), not tested-around.
- **Semantic change to `link_effects=[]`**: observable behaviour unchanged (still byte-identical to default); meaning documented.
- **Performance**: four trivial evaluations × ~1000 samples — negligible; confirmed in test 15.

## 8. Out of scope (explicit)

Fibre-path migration (decision-4 evidence PR); background/`sky_condition` and any rate→window-probability mapping (LINK-6); removal of `channel_state()`'s inline formula (post-soak); Doppler (LINK-3), stochastic effects (LINK-4), detector dynamics (LINK-5); controls on production effects (fixed physical configuration per ADR §3.6; the first controlled production effect remains gated on the LINK-1 R4 audit-emission prerequisite); any schema change.

## 9. Implementation record (2026-08-10)

Implemented by a Sonnet subagent; reviewed top-tier against this plan. **Result: 255 passed** (219 baseline + 36 new; `tests/test_link.py` unmodified and green — §6 test 2 satisfied). Parity certificate: independent inline-reference vs migrated payloads through `run._build_results()` byte-identical at both 31 samples (sha256 `03a1ad06…`) and the default 1000 samples (sha256 `af8eabbd…`), both deep-schema-valid. End-to-end check (independent review): `python -m qkd.run` emission hash equals the frozen pre-LINK-1 baseline `3d154402…1417` — the stack-always production path changes nothing observable. Files: `src/qkd/effects.py` (+182), `tests/test_effects.py` (+517), `mission.py` (+64), `channel.py` (+14, resolver extraction only).

**One judgment call flagged by implementation, reviewed and accepted:** §6 test 13's `system_efficiency=0.0` boundary drives loss_db to +inf, tripping `schema.py`'s *pre-existing* finiteness constraint on `profile.aggregates.min_loss_db` — a constraint that applies to the inline and migrated paths equally and predates LINK-2. That boundary is therefore parity-tested at `ChannelStack.evaluate()` level; the remaining boundaries (efficiencies at 1.0, QE at 0.0/1.0, τ₀ = 0.0) run through the full schema-validated pipeline. Correct isolation: the orthogonal schema constraint is not this PR's to change.

## 10. Execution note

Implementation proceeds against the certified LINK-1 baseline (`8b7ef46`, 219 green), followed by independent review of the parity evidence — test 1's byte equality and test 2's unmodified survival — before merge. All design decisions are made in this plan; an implementation encountering a genuine ambiguity records it for review rather than resolving it by invention.
