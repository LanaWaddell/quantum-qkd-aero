# LINK-3 PR Plan — Geometry-Coupled Deterministic Effects: Doppler and Pointing-Bias Hooks

**Status:** **v2 — APPROVED FOR IMPLEMENTATION** (Echo review 2026-08-10, disposition "approve after targeted revision"; revisions R1–R5 + amended test list incorporated)
**Date:** 2026-08-10
**Governing ADR:** ADR-0003 (RATIFIED 2026-07-17), LINK queue §8
**Depends on:** LINK-2 (merged, `main` @ `803f854`; 255-test suite green)

**Disposition (binding summary, per review).** LINK-3 adds the exact range-rate derivative of the project's declared orbit model, an opt-in first-order kinematic Doppler effect, and an opt-in deterministic pointing-bias approximation. Neither effect enters the production stack. Doppler remains bridge-rejected until LINK-6; stochastic pointing remains deferred to LINK-4; existing frozen emission and schema contracts remain unchanged.

---

## 1. Scope in one paragraph

(a) **Radial velocity** derived in `orbit.py` — the exact derivative of the **declared circular-orbit, stationary-Earth geometry**, completing the `PassGeometry` field LINK-1 declared and left `None`; (b) **`DopplerShiftEffect`** emitting `frequency_offset_hz`; (c) **`PointingLossEffect`**, a deterministic boresight-bias approximation emitting `transmittance_factor`. No estimator changes, no schema changes, no controls, no stochastics, no production-stack membership, no bridge extension.

## 2. The physics (decided here; approximation boundaries named)

### 2.1 Radial velocity — exact within the declared geometry model

With cos γ = cos γ_min·cos ψ, ψ = ωt, d² = R² + r² − 2Rr·cos γ:

```
ḋ(ψ) = R·r·ω·cos γ_min·sin ψ / d(ψ)          [km/s]
```

The sin γ cancellation is valid and avoids the removable singularity a separate γ̇ computation would hit at zenith closest approach. **This is the exact derivative of the declared model — not an exact real-orbit radial velocity.** Excluded (outside the ratified geometry model): Earth rotation, station motion, non-circular ephemerides, and relativistic frequency contributions. **Sign convention (binding): ḋ > 0 = receding, ḋ < 0 = approaching.** Anchors: ḋ = 0 at closest approach; antisymmetric over the symmetric pass; |ḋ| maximal at the horizon-mask edges; km/s scale for LEO.

Implementation: a **private helper** `_radial_velocity_km_s(psi, d_km, r_km, gamma_min)` (unit-test surface for the physics identity; documents its valid-domain assumptions rather than adding redundant validation for internally generated inputs). `satellite_pass()` populates the new column. Units stay km/s inside `orbit.py`; SI conversion happens exactly once at the provider boundary (§3).

### 2.2 Doppler — first-order kinematic, not a complete frequency-transfer model

```
frequency_offset_hz = −(v_r / C_M_S) · carrier_frequency_hz        C_M_S = 299_792_458.0 (single named constant)
```

**Docstring boundary (binding):** "This effect computes the first-order line-of-sight kinematic Doppler shift produced by the circular-orbit, stationary-Earth geometry used by `qkd.orbit`. It is not a complete frequency-transfer model." Also excluded, named in the docstring: Earth rotation/station motion, eccentric-orbit ephemerides, gravitational shift, hardware oscillator offsets, atmospheric propagation effects. The omitted longitudinal second-order relativistic term is ≈ 100 kHz at optical carriers — **approximately five orders below the first-order shift and below the GHz-scale filter widths contemplated for the initial LINK-6 consumer.** Scale anchor: 785 nm (f₀ ≈ 3.819×10¹⁴ Hz), 6 km/s ⇒ ≈ 7.64 GHz. `carrier_frequency_hz` is an explicit required parameter (finite, > 0); no hidden wavelength default.

### 2.3 Pointing bias — receiver-centre / small-aperture approximation (R1)

```
transmittance_factor = exp(−2·(θ_off / θ_div)²)        numerical output domain [0, 1]
```

**What this is (binding docstring language, per review):** "`PointingLossEffect` models the attenuation of Gaussian irradiance at the receiver centre under a fixed angular boresight offset. Used multiplicatively with the centred finite-aperture `GeometricLossEffect`, it is a small-aperture approximation, valid when the receiver aperture is small relative to the beam spot. Exact displaced-beam aperture integration and stochastic beam wander are deferred." The **centre-irradiance ratio is range-independent under the constant-angle far-field approximation** — it is *not* an exact factorization of the displaced-Gaussian finite-aperture capture, which depends jointly on aperture, beam radius, and displacement and retains range dependence through a/w (cf. Safi et al., arXiv:2005.11786). Output domain is [0, 1], not (0, 1]: large finite offset/divergence ratios may underflow to exactly 0.0. Parameters: `boresight_offset_urad` finite ≥ 0; `beam_divergence_urad` finite > 0; independent of `GeometricLossEffect`'s divergence parameter (caller keeps them physically consistent; no hidden coupling — LINK-2 explicit-construction pattern).

## 3. Module changes

```
src/qkd/orbit.py         # SatellitePass gains radial_velocity_km_s: list[float] | None = None
                         #   (constructor-compatible AND emission-inert — representation/
                         #   equality/asdict shape does change; emitted payload does not);
                         #   satellite_pass() always populates; _radial_velocity_km_s helper.
                         #   DISCIPLINE: the arithmetic expressions and evaluation order
                         #   producing time_s / elevation_deg / slant_range_km are untouched.
src/qkd/link.py          # TableGeometryProvider: optional 4th column — present ⇒ same nonzero
                         #   length, every value finite, snapshotted to tuple, exact stored
                         #   sample (converted) at exact times, linear interpolation between,
                         #   km/s × 1000.0 conversion exactly once; absent ⇒
                         #   radial_velocity_mps=None (LINK-1 behaviour). Docstring's
                         #   "Doppler is LINK-3 scope" note discharged.
src/qkd/effects.py       # + C_M_S constant; DopplerShiftEffect, PointingLossEffect
                         #   (construction-time validation via existing _require pattern;
                         #   NOT added to _production_link_effects)
tests/test_orbit_velocity.py   # NEW
tests/test_link3_effects.py    # NEW
```

Untouched: `mission.py` (production four unchanged — no new parity argument needed or made), `schema.py`, `run.py`, `signals.py`, `channel.py`, all existing tests including the frozen-hash tripwires.

## 4. Effect specs

```python
@dataclass(frozen=True)
class DopplerShiftEffect:
    carrier_frequency_hz: float                          # __post_init__: finite, > 0
    effect_id: str = field(default="doppler_shift", init=False)
    # evaluate: geom.radial_velocity_mps is None -> raise naming effect + field
    #           else frequency_offset_hz = -(v_r / C_M_S) * carrier_frequency_hz

@dataclass(frozen=True)
class PointingLossEffect:
    boresight_offset_urad: float                         # __post_init__: finite, >= 0
    beam_divergence_urad: float                          # __post_init__: finite, > 0
    effect_id: str = field(default="pointing_loss", init=False)
    # evaluate: transmittance_factor = math.exp(-2.0 * (offset/divergence)**2)
```

Both ignore `context`. `doppler_shift` and `pointing_loss` are **fixed canonical effect IDs, collision-checked within every assembled stack** (R5 — there is no global reserved-ID registry; "production-reserved" applies only to the four LINK-2 members that `_production_link_effects()` assembles).

## 5. Seam and boundary behaviour

- **Doppler via `simulate_pass(link_effects=…)`** raises `UnsupportedLinkObservableError` naming `channel.frequency_offset_hz` — a successful boundary test of the LINK-1 guard, not missing functionality. No bridge extension in LINK-3.
- **Doppler at stack level:** `ChannelStack.evaluate()` composes `frequency_offset_hz` by the ratified sum rule — computable for research use and ready for LINK-6. Duplicate `DopplerShiftEffect` instances are *impossible* in one stack (fixed-ID collision, by design); sum composition is tested with one real Doppler effect plus a **distinct-ID mock** frequency contributor (R5).
- **Pointing via `simulate_pass`:** usable today as an appended user effect; per-sample contract `with_pointing.transmittance[i] == baseline.transmittance[i] * factor` (exact single application — the LINK-2 `P * u` association). Downstream emitted fields (key rate, loss dB, aggregates) are *nonlinear* consequences and are not claimed to scale.
- **Default emission unchanged:** neither effect is in the production stack; the orbit column is emission-inert. Proof (R3): the existing frozen-hash and captured-fixture tests pass **unmodified** — `tests/test_profile.py::test_run_main_emitted_results_match_captured_pre_refactor_contract`, `tests/test_fibre_sweep.py::test_satellite_emission_remains_pr_b_stable_hash`, the captured pass fixture, and the LINK-1/LINK-2 parity tests — plus a focused assertion that the emitted payload contains no velocity field. Any new in-process comparison is a *current-path parity check*, not a before/after proof.

## 6. Acceptance tests (Echo-amended list)

| # | Test |
|---|---|
| 1 | Odd-sampled pass: modeled radial velocity exactly 0 at closest approach |
| 2 | Antisymmetry ḋ(−t) = −ḋ(t) within a stated tight absolute tolerance |
| 3 | Sign convention: < 0 approaching (first half), > 0 receding (second half) |
| 4 | Analytic helper vs independently computed central difference of `slant_range_km` at **interior** samples; concrete tolerance tied to step size, with a two-step-size convergence check |
| 5 | Default-geometry max \|ḋ\| in a justified km/s band; maximum occurs at horizon-mask edges |
| 6 | Legacy three-column `SatellitePass` construction ⇒ `radial_velocity_km_s is None` |
| 7 | Provider (enumerated separately): absent ⇒ `None`; present ⇒ length match enforced, non-finite rejected, tuple snapshot immune to source-list mutation, exact converted sample at exact times, linear interpolation, × 1000.0 exactly once |
| 8 | Doppler: 0 at closest approach; positive approaching, negative receding |
| 9 | 785 nm anchor vs an independent first-order calculation (tight numerical tolerance; bitwise only if identical operation order is deliberately used) |
| 10 | Missing `radial_velocity_mps` ⇒ evaluation raises naming effect + field |
| 11 | Real Doppler + distinct-ID mock contributor sums per the ratified rule; duplicate `DopplerShiftEffect` instances rejected by fixed-ID collision |
| 12 | `simulate_pass` bridge rejection: `UnsupportedLinkObservableError` naming `channel.frequency_offset_hz` |
| 13 | Pointing values: 1.0 at zero offset; `exp(-2)` at θ_off = θ_div (vs `math.exp`, same operation order); monotone decreasing; documented [0, 1] domain |
| 14 | Mission integration: per-sample `transmittance[i] == baseline[i] * factor` exactly, single application; deep-schema-valid payload; optional byte-equality only against an **independently constructed** expected pass (baseline channel states × hand-computed factor → existing profile/result/builder path; never re-running the tested `link_effects` branch as its own oracle) |
| 15 | Construction rejects invalid carrier/offset/divergence: NaN, **+inf**, ≤ 0 where required, negatives |
| 16 | Frozen-hash, captured-fixture, LINK-1, and LINK-2 parity tests pass **unmodified**; emitted payload contains no velocity field |
| 17 | Full suite green from the certified 255-test parent baseline plus the new tests |

(Performance: the added per-sample arithmetic is negligible; no formal duration assertion — an undefined performance claim is not reproducible, per review.)

## 7. Risks

- **Existing-column drift in `orbit.py`**: the §3 discipline line is binding — velocity computation must not alter the expressions or evaluation order for the three existing columns; test 16's frozen hashes are the tripwire.
- **Approximation misuse**: §2.3's docstring language ships verbatim so the small-aperture boundary travels with the effect, not just the plan.
- **Interpolated velocity vs derivative-of-interpolated-range**: not identical between samples; exact at samples; acceptable and documented under the table-provider contract.
- **Fixed-ID misconception**: §4's canonical-vs-reserved distinction prevents the plan from implying a registry that does not exist.

## 8. Out of scope (explicit)

Stochastic pointing jitter, beam wander, scintillation (LINK-4); exact displaced-beam aperture-overlap integration (deferred with LINK-4's pointing upgrade or later, whichever earns it); estimator consumption of `frequency_offset_hz` and any bridge extension (LINK-6); production-stack membership for either effect (future PR with its own parity/impact argument); μ fluctuation, afterpulsing, dead time (LINK-5); Earth rotation / non-circular orbits / full frequency-transfer modeling; schema changes; controls.

## 9. Implementation record (2026-08-10)

Implemented by a Sonnet subagent; reviewed top-tier against this plan. **Result: 294 passed** (255 baseline + 39 new; zero skips/xfails). Frozen-hash tripwires (`test_profile` pre-refactor contract, `test_fibre_sweep` PR-B stable hash) and the LINK-1/LINK-2 parity tests pass **unmodified**; end-to-end `qkd.run` emission hash equals the frozen baseline `3d154402…1417` — the velocity column is emission-inert as designed. Independent review spot-check: analytic ḋ vs fine central difference agrees to ~3×10⁻¹⁰ relative error; sign chain (approach ⇒ v_r < 0 ⇒ Δf > 0) verified. Default-geometry max |ḋ| = 6.88 km/s at the horizon-mask edges (< orbital speed 7.59 km/s — sane). Files: `orbit.py` +44, `link.py` +47, `effects.py` +122, `tests/test_orbit_velocity.py` +145, `tests/test_link3_effects.py` +489.

Two recorded ambiguity resolutions, reviewed and accepted: (1) the ×1000.0 SI conversion is applied once per stored sample at provider construction, with interpolation over already-converted values — makes "exact converted stored sample" trivially true and double-conversion impossible; (2) `_radial_velocity_km_s` computes ω from `r_km` internally and takes R from the module constant, keeping the plan's stated four-argument signature.

## 10. Execution note

Implementation proceeds against the certified LINK-2 baseline (255 green), followed by independent review of the physics anchors (tests 1–5, 8–9, 13), the boundary tests (11, 12, 16), and the §3 discipline line before merge. All design decisions are made in this plan; a genuine ambiguity is recorded for review, not resolved by invention.
