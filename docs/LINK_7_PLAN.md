# LINK-7 Plan v1.3: Source Consumption (Robust Decoy Inversion Under a Certified Common-Mode Bound)

- Date: 2026-08-24
- Prepared by: Claude (Chat Claude v1, `757e121a…50ad5c891`; revised to v1.1 by Cowork Claude applying Echo's review `LINK_7_REVIEW.md`, `0652e831…2efbf551f51`, in full — R1–R6 adopted, C1–C5 adopted, §3 structural refinements adopted; all review claims independently verified against fresh-clone HEAD `d48cb2c`)
- Status: **v1.3 — DISPATCH VERSION (Echo re-review `LINK_7_V12_REVIEW.md`, `0b7d6b73…23a9c35`: "green for Sonnet dispatch after two small plan-text corrections" — R12.1/R12.2 applied, both editorial nits fixed; literature mapping confirmed by Echo: Wang PRA 75 052301 (2007) and PRA 77 042311 (2008), with Sixto/Zapatero/Curty and Trefilov as boundary references; PI dispatch authorization given).**
- **v1.2 → v1.3 changelog:** (R12.1) certified-rate **emission rule** stated — the emitted secure-rate claim is `R_certified = max(0, R_hat − ε)` where `R_hat` is the minimizer's best candidate minimum and `ε ≤ ROBUST_RATE_CERT_GAP` its certified absolute overstatement gap (equivalently, the certified lower envelope); diagnostics may record `R_hat`, `ε`, `R_certified`; the claim can never exceed the true interval minimum, even by 1e-12; (R12.2) `SOURCE_MODEL_SUPPORT` is **code/registry-derived only** — the hard-containment gate derives support from registered effect semantics and parameters; the v3 manifest records support as an **audit echo, never trusted**: `replay_from_provenance` recomputes the gate from the reconstructed effects and rejects a manifest whose echoed support disagrees with the recomputation; exact v3 receiver keys pinned at implementation; (nits) §9 "extraction triple" → `extract_source_truth` + mission-level composition; §6 heading corrected. The four §10 decisions are **PI-confirmed (2026-08-24)**. This revision adds the numerical anchors (§12), the superseded-test enumeration (§13, per the 6b §12 policy), the two-stage extraction design that shrinks that enumeration (§3.1), the monotonicity evidence and its honest status (§2), and the literature note (§7).
- Baseline: `d48cb2c` (622 full / 601 no-qiskit-file; reverified). HYBRID-1 may land first — disjoint files, no coordination needed; v1.2 re-pins the baseline hash.
- Lane: LINK, following LINK-6b. Working method: 6a/6b pattern (PI + Echo gate → Sonnet dispatch → independent verification → PI certification).

## 0. Scope statement

After LINK-6b the residual bridge rejects exactly one non-identity field: `source.intensity_factor`. LINK-7 consumes it — the last deferred observable — discharging the source-side items of the consolidated consumption gate: **gate item (1)**, the realized-versus-observed information model (§1), and **gate item (2)**, a decoy-state treatment valid for exactly the declared uncertainty structure (§2). Out of scope: Route B source monitoring (§8); per-setting/pulse-resolved/correlated intensity errors (the cited literature — Sixto/Zapatero/Curty 2206.06700, Trefilov et al. 2411.00709 — motivates the *boundary*, not this model); receiver-aware Eve; finite-key; source-active PDT (deferred per §10-D2); any benchmark claim. All emitted rates remain asymptotic, model-conditional. Default path byte-identical; frozen-hash tests unmodified.

## 1. Information model (gate item 1, binding — Echo R4 placement and trigger)

The realized factor `k` is **latent simulation truth**: it scales the true mean photon numbers that generate counts, and no estimator path may read it — structurally (§3), not documentarily. The estimator's declared knowledge is: nominal settings (μ, ν, 0), observed block statistics, and a **hard calibration certificate** `source_intensity_uncertainty = δ ∈ [0, 1)` asserting certified containment `k ∈ Kδ = [1−δ, 1+δ]` for the block.

- **Placement (R4):** δ is an **estimator/source-characterization assumption**, not a control. It lives as `ReceiverModel.source_intensity_uncertainty: float | None = None` — the LINK-6b `source_linewidth_sigma_hz` precedent — and is recorded in the manifest. `ControlSpec` remains the intervention surface; no ADR change.
- **Required-when-consumed trigger (R4, binding):** validity depends on the **active source model/configuration, never on the sampled realization** — checking `k ≠ 1` to decide whether δ is required would itself consume latent truth. Rules: an uncertain source model active (any registered stochastic source owner in the stack) ⇒ δ required, even if the realized draw happens to be exactly 1.0 (`SourceUncertaintyRequiredError`); no source model active ⇒ δ may be absent; δ supplied on an identity run ⇒ accepted-but-unused, recorded.
- **Model-compatibility gate (R2, Route R2-A — hard containment; R12.2 trust rule):** a run may emit a LINK-7 secure-rate claim only if **every active source contributor declares bounded support contained in Kδ**. The declaration is a consumer-side model-class check (`SOURCE_MODEL_SUPPORT` registry mapping source `effect_id` → declared support form), not a stack-algebra change — and it is **code/registry-derived only**: the gate reads registered effect semantics and constructor parameters, never a manifest. The manifest records support as an audit echo; replay recomputes the gate from the reconstructed effects and rejects any manifest whose echo disagrees. The existing unbounded log-normal `MuFluctuationEffect` is **not security-consumable** under a hard δ — it remains a stress/noise model for sampled-mode studies with **no secure-rate claim** (`SourceModelIncompatibleError` on any attempt); a sample-level "the draw happened to land inside" check is explicitly rejected as insufficient. Probabilistic-δ (ε_source accounting) is Route R2-B, recorded as a follow-up, not smuggled into the scalar.
- **Miscalibration (R4 / Echo answer 3):** `δ = 0` with a non-identity-capable source model active is an inconsistent configuration and **fails loudly** outside the estimator (`SourceCertificateViolationError` at composition). Assumption-failure study is representable only via an explicitly named stress mode that emits **no secure claim**; LINK-7 does not implement that mode, it records it.

## 2. Route A robust inversion (gate item 2 — Echo R1: the complete rate, one witness)

**Structure (C5 wording):** a low-dimensional common-mode special case — one epoch-fixed unknown scalar `k` shared by all nonzero settings, exact zero preserved (`k·0 = 0`), one draw per estimation block (§C4).

- **Truth side:** physical statistics are generated at realized intensities (kμ, kν, 0) through a **statistics-only path** (§3.2); the unchanged 6a/6b chain (noise mapping, acceptance folds, shared afterpulse, availability) applies on top.
- **Estimator side (R1, complete-rate robustification):** observed gains and error statistics held fixed; for every candidate `k′ ∈ Kδ` evaluate the **complete candidate rate** with candidate intensities everywhere the proof uses intensities:

```
μ′ = k′μ, ν′ = k′ν
Y1_L(k′), e1_U(k′) = estimate_decoy_bounds(observed gains, observed errors, {signal: μ′, decoy: ν′, vacuum: 0})
q1_L(k′)           = Y1_L(k′) · μ′ · e^(−μ′)          ← the v1 omission: q1 is intensity-dependent
R(k′)              = secure_key_rate(Q_signal_obs, E_signal_obs, q1_L(k′), e1_U(k′), q, f_EC)
R_robust           = min over k′ ∈ Kδ of R(k′)
R_certified        = max(0, R_hat − ε)     ← the emitted claim (R12.1): R_hat = minimizer's best
                                              candidate, ε ≤ ROBUST_RATE_CERT_GAP its certified gap;
                                              never above the true interval minimum
```

  Availability/π factors apply after, exactly where they apply today. **Witness rule (R1):** every reported security diagnostic (`Y1`, `e1`, `q1`) is taken from the single minimizing witness `k*` — never mixed extrema of intermediate fields, which can correspond to no admissible source.
- **Certified minimization (R5 / Echo answer 2; v1.2 evidence recorded):** endpoints-only is **not** assumed. A 432-configuration dense-sweep exploration (μ ∈ {0.4…0.8}, ν ∈ {0.05…0.2}, η ∈ {0.005…0.15}, e_d ∈ {0.01…0.05}, δ ∈ {0.1…0.3}; 4001-point grids, live estimator) found **zero interior minima** — every observed worst case sits at the **upper** endpoint `1+δ` (larger assumed intensity ⇒ larger assumed multi-photon fraction ⇒ lower `Y1_L` and lower `q1`). This is **evidence, not proof** (Echo's distinction stands), so the production mechanism remains the **deterministic, globally certifying 1-D minimizer**: Piyavskii–Shubert with a documented over-estimate of the Lipschitz constant derived from closed-form derivative bounds of the rate expression on the pinned operating domain (no SciPy), terminating at declared certified gap `ROBUST_RATE_CERT_GAP = 1e-12` (absolute, on the per-pulse rate; PI D4 confirmed mechanism). Tests: dense-grid oracle agreement on the §12 anchors; the minimizer's global-certification property demonstrated on a **synthetic objective with a known interior minimum** (the tool is proven able to find interior minima even though the QKD anchors' minima are endpoint); upper-endpoint agreement asserted on every anchor. If a v1.3+ analytic note ever proves complete-rate monotonicity on the supported domain, endpoints become certified and the minimizer becomes the cross-check — a recorded upgrade path, not this lane's requirement.
- **Reduction identities (strict `==`):** δ = 0 (with a compatible or absent source model) reproduces the current nominal inversion and full pipeline bit-identically — the identity short-circuit. **Sanity invariant (C1):** universal `R_robust ≤ R_nominal`; exact equality required at δ = 0; strict inequality asserted only on a predeclared nondegenerate anchor — no false global "iff" (equality can also occur clamped-at-zero or on saturated bounds).

## 3. Structural epistemic wall (Echo §3, adopted)

- **3.1 Type wall (v1.2 refinement — two-stage extraction):** `ReceiverInputs` stays **seven** fields (estimator-consumable observables only). New truth-side type `SourceTruthInputs(intensity_factor: float = 1.0)`. The existing `extract_receiver_inputs(state) -> (ReceiverInputs, residual)` keeps its signature **unchanged**; a new `extract_source_truth(state) -> (SourceTruthInputs, residual)` is composed after it at mission level. This keeps every existing extraction test intact (the 6a exact-consumed-set test needs no edit) while the composed pair consumes eight observables and the residual bridge then rejects nothing non-identity — asserted by a named full-consumption test. Named tests: `intensity_factor` absent from `ReceiverInputs` and from every decoy-estimator signature; the truth-generation helper may receive `k`, the robust estimator cannot.
- **3.2 Statistics-only truth path:** `run_decoy_bb84` both generates statistics **and** inverts; calling it at (kμ, kν) would pass realized `k` through an estimator function. LINK-7 therefore uses a statistics-only generator — §10-D3 decides between the two honest routes (minimal `bb84.py` refactor vs. detection-side reuse of the certified primitives). No function that performs decoy inversion ever receives realized `k`.
- **Anti-oracle acceptance test (retained from v1, strengthened per R4):** different realized `k`, bit-identical constructed observed statistics, same nominal settings and δ ⇒ bit-identical robust estimate; plus: uncertain model active with realized draw exactly 1.0 still requires δ.

## 4. Source model and ownership (R2-A, C2)

- **New bounded owner (the R2-A vehicle):** `CalibratedSourceFactorEffect(half_width)` (id `calibrated_source_factor`), drawing `k ~ Uniform[1−w, 1+w]`, `0 ≤ w < 1`, seeded per the LINK-4 discipline, declared support `[1−w, 1+w]` in `SOURCE_MODEL_SUPPORT`. Security-consumable iff `w ≤ δ`. This is a **new effect id ⇒ codec count 16 → 17** (consistent with Echo R3's conditional). `MuFluctuationEffect` unchanged, registered with **unbounded** support ⇒ never hard-δ-consumable.
- **Ownership wording (C2, corrected):** `MuFluctuationEffect` and `CalibratedSourceFactorEffect` are the registered built-in owners; `source.intensity_factor` **composes as a product** across distinct effects (LINK-5 §1.4) — what rejects is a duplicate `effect_id`, not a second contributor. LINK-7 introduces no new combination rule; instead the **consumer** restricts the accepted model class: a security-consumable run requires every active source contributor to be support-declared with the **composed** support contained in Kδ (product of interval supports, computed conservatively).
- **Block boundary (C4, binding):** the realized factor is constant over exactly the estimation block whose signal/decoy/vacuum statistics feed one inversion; one draw per block, asserted by test; aggregation across blocks with different `k` into one inversion is structurally absent and named as out-of-model.
- **Vacuum invariant (C3):** exact-zero vacuum preserved exactly under any `k`; scoped to the current `vacuum = 0.0` setting.

## 5. Versioning, manifest, replay (R3 / Echo answer 4)

- **Manifest v3**, `pipeline_version = "link-7.1"`; strict three-row matrix (v1 ↔ `link-6a.1`, v2 ↔ `link-6b.1`, v3 ↔ `link-7.1`), every hybrid rejected; the v2 receiver object stays frozen exactly as 6b defined it; v3's receiver object adds `source_intensity_uncertainty` (nullable) and an **audit-echo** of the active owners' support (recorded, never trusted — the gate recomputes from code, R12.2).
- **Pre-Gate 0 (6b discipline):** before any source edit, capture a real **manifest-v2** fixture plus its expected semantic output through the unmodified baseline production path; after implementation, both safeguards (in-process parity; portable tolerant semantic parity). v1 and v2 historical replays unchanged.
- Codec count 17 (the one new owner). Effect codecs, controls, and 6b tests otherwise untouched except the v1.2-enumerated superseded set (version-pinned tests, matrix tests, `_valid_manifest_dict` → v3 with retained v1/v2 helpers — final enumeration in v1.2 after the 6b §7/§12 policy).

## 6. Acceptance-test contract (anchors §12; counts pinned at dispatch)

Echo §6 adopted **in full**, plus (R12.1) `R_certified ≤ R_hat`, `R_hat − R_certified ≤ ROBUST_RATE_CERT_GAP`, `R_certified` is the emitted field, and a clamped-at-zero case; (R12.2) manifest support-echo disagreement ⇒ named replay rejection; the full contract (epistemic/type-wall; security-function incl. hand-computed `q1(k′)` and complete `R(k′)`, witness-consistency, interior-minimum fixture, dense-grid oracle vs certifying minimizer, `R_robust ≤ R_nominal` universal with named strict case; calibration-model incl. incompatible-model rejection, certificate-violation rejection, δ domain tests; physics incl. realized-k-through-truth-chain, shared-history occupancy consistency, exact-zero vacuum, one-draw-per-block, no-mixture; replay/version incl. Pre-Gate 0, three-row matrix, hybrid rejections, v3 round-trip). PDT rows are **omitted** per §10-D2 (deferral); the sampled-mode ensemble tests do not reference PDT.

## 7. Literature gate (Echo §8, pre-dispatch)

v1.2 carries a short literature note establishing exactly one claim: *for one block-fixed common multiplicative source parameter shared across the nonzero settings and independent of the setting choice, applying the standard fixed-intensity asymptotic decoy bound per candidate value and taking the worst complete key rate over the certified set is sound (covered by, or strictly weaker than, a published analysis).* Anchors: X.-B. Wang's inexact-intensity decoy analyses; Sixto/Zapatero/Curty 2206.06700 (why correlated/setting-dependent errors need more); Trefilov 2411.00709 (source-memory boundary). No claim of generality beyond this case.

## 8. Recorded follow-ups (not this lane)

Route B source monitoring (declared monitor observable with its own noise model); Route R2-B probabilistic δ with ε_source accounting; source-active PDT (Echo Option A: epoch-sampled source prefix admission — one draw per block shared across all quadrature nodes, explicit allowlist category, never relabelled deterministic); per-setting/correlated intensity errors; receiver-aware Eve; geometry-coupled polarization frame.

## 9. File inventory (final, v1.3)

**Create:** `tests/test_link7.py`, Pre-Gate 0 fixtures (`link6b_manifest_v2.json` + expected). **Modify:** `src/qkd/detection.py` (SourceTruthInputs, robust inversion, certifying minimizer + emission rule, model-compatibility gate), `src/qkd/effects.py` (`CalibratedSourceFactorEffect`, `SOURCE_MODEL_SUPPORT`), `src/qkd/mission.py` (`extract_source_truth` + mission-level composition — the §3.1 two-stage design, not a triple return; trigger rules), `src/qkd/replay.py` (manifest v3, codec 17, support-echo recomputation), `src/qkd/bb84.py` (§10-D3: extract public `expected_block_statistics`, pure factoring, parity-pinned), plus the §13-enumerated superseded tests. **Untouched:** `link.py`, `schema.py`, `benchmark.py`, `run.py`, twin/orbit/channel/signals/coherence, all other tests and fixtures.

## 10. PI decisions — **confirmed (PI, 2026-08-24)**

| # | Question | Decision |
|---|---|---|
| D1 | R2 route | **Confirmed: R2-A hard containment** with `CalibratedSourceFactorEffect` (codec 17); R2-B recorded |
| D2 | Source-active PDT | **Confirmed: defer (Option B)** — sampled-only; Option A recorded with Echo's five conditions |
| D3 | Statistics-only truth path | **Confirmed: the bb84 factoring** — extract public `expected_block_statistics(channel, intensities, detector) -> (gains, qber_per_intensity)` from `run_decoy_bb84`'s honest branch, which then calls it. First-ever `bb84.py` edit: pure factoring, no law change, certified by (i) the frozen-hash set, (ii) a new parity test asserting `run_decoy_bb84`'s outputs are bit-identical pre/post-factoring on a pinned grid, (iii) the byte-identity default path. No decoy-inversion function ever receives realized `k` |
| D4 | Certifying minimizer | **Confirmed: mechanism approved**; `ROBUST_RATE_CERT_GAP = 1e-12` pinned with the §12 anchors |

## 11. Answers to Echo's review (disposition table)

| Finding | Disposition (adopted v1.1, carried) |
|---|---|
| R1 — robustify the complete rate incl. `q1(k′)`; single witness `k*`; observed statistics held fixed | **Adopted** — §2, verified against live `bb84.py` (`q1 = Y1·μ·e^(−μ)`) |
| R2 — hard δ incompatible with unbounded `MuFluctuationEffect` | **Adopted (R2-A)** — §1 model-compatibility gate, §4 bounded owner; sample-level containment explicitly rejected |
| R3 — manifest v2 frozen; bump to v3 + Pre-Gate 0 v2 oracle | **Adopted** — §5; v1's "extend v2" withdrawn |
| R4 — δ is an estimator assumption; trigger on active model, not sampled truth; reject δ=0∧k≠1 | **Adopted** — §1; `ReceiverModel` placement; `SourceCertificateViolationError` |
| R5 — no endpoints-only, no uncertified grid | **Adopted** — §2 certifying Piyavskii minimizer with grid as test oracle |
| R6 — PDT admission forbids `mu_fluctuation` | **Adopted (Option B)** — source-active PDT deferred, §8; v1's PDT ensemble test withdrawn |
| §3.1 SourceTruthInputs / §3.2 statistics-only path | **Adopted** — §3; route choice = PI D3 |
| C1 ≤-invariant; C2 product composition; C3 exact-zero scope; C4 block boundary; C5 wording | **All adopted** — §2, §4 |

## 12. Numerical anchors (independent transcription guard; printed values truncated; tests assert the independent derivation to ≥ 12 significant digits)

**Anchor fixture A (constructed observed statistics — estimator-level, no receiver chain):** nominal `μ = 0.5`, `ν = 0.1`; truth generated by the live gain/error laws at `η = 0.05`, `y0 = 1e-6`, `e_d = 0.015`, realized `k = 1.03` (so observed statistics correspond to intensities (0.515, 0.103, 0)):

```
observed  Q_s = 0.0254222707470433   Q_d = 0.00513775634910441   Q_v = 1e-06
observed  E_s = 0.015019092760213    E_d = 0.0150944141797433    E_v = 0.5
δ = 0.05 candidates (complete rate, live estimator):
k' = 0.95: R = 0.00517713289209529  Y1_L = 0.0528111101714486  e1_U = 0.0168983797002632  q1 = 0.0156001591097021
k' = 1.00: R = 0.00498039524641108  Y1_L = 0.0500071169997848  e1_U = 0.0170390899696245  q1 = 0.0151654248321032
k' = 1.05: R = 0.00478756687764011  Y1_L = 0.04745938558528    e1_U = 0.0171850573420071  q1 = 0.0147392984195759
R_robust = R(1.05) = 0.00478756687764011  (witness k* = 1+δ; all reported diagnostics from k* — R1 witness rule)
R_robust < R_nominal ✓  (universal ≤ invariant; this is the predeclared strict-inequality anchor, C1)
```

The dense-grid oracle (200k points) confirms the upper-endpoint minimum on this fixture; the certifying minimizer must agree within `ROBUST_RATE_CERT_GAP`. δ = 0 on this fixture must reproduce `R(1.00)` bit-identically (strict `==`). A second anchor with `δ = 0.1` (same observed statistics) is pinned in the test file from the same derivation (`R_robust = R(1.1) = 0.00459857086776621…`).

## 13. Superseded-test enumeration (6b §12 policy — exact names, exact permitted change; everything else is an oracle)

| Test / helper | Permitted change |
|---|---|
| `test_replay.py::test_link_pipeline_version_constant_has_the_plan_frozen_value` | `LINK_PIPELINE_VERSION == "link-7.1"`; retained `…_V1 == "link-6a.1"`, new retained `…_V2 == "link-6b.1"` |
| `test_replay.py::test_effect_codecs_cover_exactly_the_sixteen_registered_effect_ids` | → seventeen (adds `calibrated_source_factor`); renamed accordingly |
| `test_replay.py::test_manifest_version_unsupported_rejected` | unsupported probe 3 → 4 |
| `test_replay.py::test_canonical_json_reserialization_mismatch_rejected` | tamper string `"manifest_version":2` → `:3` |
| `test_replay.py::_valid_manifest_dict` (helper) | → v3 form; new helper `_valid_manifest_v2_dict` retains the exact v2 form (alongside existing `_valid_manifest_v1_dict`) |
| `test_link6a.py::test_intensity_factor_still_rejected_in_receiver_active_mode` | **deleted** — the field is now consumed; its protective role passes to the new certificate-requirement and full-consumption tests in `tests/test_link7.py` |

**§13 addendum (PI-approved 2026-08-24, post-implementation — three tests the original enumeration missed, discovered by the implementer and left failing rather than silently patched, exactly per policy):** `test_link5_effects.py::test_intensity_factor_not_reachable_through_detector_params_channel_state_or_estimator` — its premise ("the field is unreachable everywhere but `link.py`/`effects.py`") is what LINK-7 lawfully ends; permitted change: extend its allowed-module list by exactly `detection.py`, `mission.py`, `replay.py` (the authorized consumption path), retaining the reachability rule for every other module; `test_link6b.py::test_pregate0_v1_fixture_satisfies_both_replay_safeguards` and `test_link6b.py::test_manifest_v2_round_trip_byte_identical_sampled` — both assert the live path emits `manifest_version == 2`; permitted change: expect v3 from the live path (the same pattern LINK-6b applied to the LINK-6a-era assertions), with the historical v1/v2 fixtures continuing to guard their frozen versions.

Notably **not** superseded (the §3.1 two-stage extraction preserves them): `test_detection.py::test_extract_receiver_inputs_returns_exact_consumed_field_set` (still seven), every `ReceiverInputs` construction, all 6b activation/matrix tests for v1/v2 rows. Byte-identity and parity tests are never eligible.

## 14. Literature note (Echo §8 gate — scoped claim)

The exact claim LINK-7 relies on: *for one block-fixed common multiplicative source parameter shared by the nonzero signal/decoy settings, independent of setting choice and of the channel, evaluating the standard fixed-intensity asymptotic decoy bound at each candidate parameter value in a certified interval and taking the worst complete key rate is sound.* This is the interval-uncertainty ("intensity fluctuation") special case treated by X.-B. Wang's decoy-state analyses with inexact/unstable source intensities (worst-case-over-declared-bounds structure; Wang's PRA intensity-fluctuation series), of which the epoch-common single-parameter form here is a strict sub-case — the candidate sweep is exactly the worst-case-over-bounds evaluation with one shared parameter instead of per-setting ones. Sixto/Zapatero/Curty (arXiv:2206.06700) and Trefilov et al. (arXiv:2411.00709) are cited as the *boundary* references: setting-correlated and memory-bearing errors are outside this model, and LINK-7 claims nothing about them. **Verification status:** the structural containment argument is stated here; Echo's re-review is asked to confirm the Wang-series mapping or name a preferred canonical citation — the plan cites what is verified, and dispatch does not proceed on an unverified citation (the fallback, if the mapping is disputed, is to label the robust bound "model-defined worst-case over the certified interval" without a literature-coverage claim, which weakens the framing but not the mathematics).

## 15. Implementation record (2026-08-24)

**Dispatch:** Sonnet subagent (trial), plan v1.3 + PI-approved §13 addendum, baseline `c69e461` @ 800+1-skipped local / 821 full env. Three passes: Pre-Gate 0 + implementation; verification-driven named-error fix; §13-addendum test reconciliation. Top-tier verification (Fable 5) independent throughout.

**Pre-Gate 0:** `tests/fixtures/link6b_manifest_v2.json` (`820d3412…77f54c38`) and `link6b_manifest_v2_expected.json` (`f9d06ad2…156a84b4`) captured from the unmodified `c69e461` tree before any source edit.

**Files.** Created: `tests/test_link7.py` (54 tests), the two fixtures. Modified: `bb84.py` (+33/−9 — **first-ever edit**: D3 factoring only, `expected_block_statistics` extracted verbatim, `run_decoy_bb84` calls it; certified by frozen-hash set + pinned-grid parity + byte-identical default emission), `detection.py` (SourceTruthInputs, code-derived `SOURCE_MODEL_SUPPORT` gate, complete-rate robust inversion with single-witness diagnostics, certified Piyavskii–Shubert minimizer + R12.1 emission rule `R_certified = max(0, R_hat − ε)`, `RobustRateCertificationError` fail-loud non-convergence), `effects.py` (`CalibratedSourceFactorEffect`, support registry), `mission.py` (two-stage extraction composition, model-based triggers), `replay.py` (manifest v3 matrix, codec 17, audit-echo recomputation + `SourceSupportEchoMismatchError`); §13 + addendum test edits exactly as enumerated.

**Certification (cloud, no-qiskit clone):** **853 passed, 1 skipped** (full-env projection 874); default emission `outputs/results.json` SHA-256 unchanged at `3d1544027517…f1417` — the **tenth** consecutive change with the frozen default emission intact (the subagent's first report cited a wrong hash from hashing the wrong artifact; independently corrected against `outputs/results.json`).

**Independently verified:** §12 anchors bit-exact (`R_hat = 0.00478756687764011`, ε = 8.9e-13, `R_certified` within gap; δ=0.1 anchor likewise); δ=0 strict `==` identity; no estimator signature carries realized k; `ReceiverInputs` still seven; factoring parity (`expected_block_statistics` ≡ `run_decoy_bb84` internals); v3 manifest round-trip byte-identical; v1 AND v2 historical fixtures replay with semantic parity; support-echo tamper rejected; `SourceUncertaintyRequiredError` / `SourceModelIncompatibleError` (unbounded model, and w > δ) / composition triggers all fire; codecs 17.

**Recorded deviations (accepted, flagged for Echo's post-review):** (1) the Piyavskii Lipschitz over-estimate is derived from a dense probe + safety factor with online verify-and-double, not the plan's closed-form derivative bounds — self-checking but weaker as a certificate; **closed-form derivation registered as a follow-up**; (2) `PIYAVSKII_MAX_ITERATIONS = 2e6` set empirically; (3) a real robustness finding: wide clamped-zero plateau configurations can exhaust the iteration budget — now a **named** `RobustRateCertificationError` (fail-loud, tested on the discovered configuration), never a silent fallback; fix-vs-accept is a recorded follow-up; (4) the synthetic interior-minimum minimizer test certifies at gap 1e-6 (production anchors at 1e-12); (5) product-composition of two distinct bounded source owners is registry-tested only — a second bounded owner does not yet exist.

**Local certification (PI, qkd_env with qiskit):** expected **874 passed** (853 + 21 qiskit). Stage exactly: the five modified `src/qkd` files, the four modified test files, `tests/test_link7.py`, the two fixtures, `docs/LINK_7_PLAN.md`, and Echo's LINK-7 review files if desired in-repo. `docs/HYBRID_*` paths are already committed; nothing else.
