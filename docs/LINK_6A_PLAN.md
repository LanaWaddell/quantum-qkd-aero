# LINK-6a Plan — Estimator Integration I: QKD Receiver Model, Gated Detection, PDT Consumption, Benchmark/Provenance Layer

**Status:** **v2.3.1 — APPROVED (Echo `docs/LINK_6A_V231_REVIEW.md`, SHA-256 `21cbed66…9b16421a`; PI dispatch authorization 2026-08-17) — IMPLEMENTED 2026-08-18, see §14 implementation record; awaiting PI local certification + commit** (Echo v2.3 confirmation review 2026-08-17, `docs/LINK_6A_V23_REVIEW.md`, SHA-256 `a308c9cf…6a52708`: "approve after one narrow v2.3.1 contract correction; the physics, detector-copy route, law-last rule, and Eve deferral are approved"; F1, F2 and cleanups 1–4 applied below; implementation **not authorized** until PI + Echo confirm these edits)
**Date:** 2026-08-17
**v2.3 → v2.3.1 changelog:** (F1) `profile.link_receiver.pi.*` provenance corrected to **`ILLUSTRATIVE`** (caller configuration, matching the live `mission.intensities.*` tags), with a positive exact-map assertion and a negative test (A.4); (F2) replay manifest nested vocabularies **enumerated closed-world** — `mission_config` (ten keys, resolved seven-key `atmosphere`, three-key `detector`, three-key `intensities`, `sky_condition` enum), `receiver` (`pi` + `operating_convention` only — the calibrated pair is **not** duplicated there; single ownership stays with the ordered effect specs), `production_effects`/`effects` with **codec-owned `param_keys`** per `effect_id` (table), `model_ids`, `serialization`, `link_controls`, `pdt_config` (A.2.1); cleanups: `availability` = `A` in sampled mode and `E_f[A(f)]` in PDT mode (A.1/A.3); A.3 split into required `ReceiverBlockResult` fields vs optional trailing additions; private-helper rule for the future Eve PR recorded (§1.2); Appendix A heading relabelled v2.3.1.
**v2.2 → v2.3 changelog:** (C1) §5 rewritten on the **live** mission defaults (`DEFAULT_N_PULSES = 10⁶`, `f_rep = 10⁸ s⁻¹`, uniform sample width 0.476955506437 s ⇒ ≈ 4.77×10⁷ physical pulses per sample; the v2.2 text had substituted the anchor fixture's 10⁴/10⁶); the false "independent fading draws" sentence withdrawn — `n_pulses` is a uniformly distributed **expected-count subsample** whose fading values are exchangeable but *correlated within a coherence interval*; LINK-6a computes deterministic asymptotic expectations, no finite-key independence claim; `block_duration_s` **bound to the actual profile bin width** within a named tolerance (final sample reuses the uniform width); memory guard rebased on a declared **effective memory scale** `τ_mem = dead_time_s + 1/f_rep` (non-vacuous at zero dead time). (C2) PDT deterministic-stack path frozen as a five-step sequence with the law effect **excluded** from evaluation and required to be **last** in the composed stack; `PDT_ADMISSIBLE_EFFECTS` enumerated by stable `effect_id` with `deterministic`/`law` classification; exception name corrected to the live **`SeedRequiredError`**. (C3) Base statistics route decided: **reuse** `run_decoy_bb84` on a detector copy with `dark_count_prob = p_noise` (both certified base gain **and** error-gain laws inherited, no private-formula copying); every stale `(Q'_x, E'_x, p_noise)` phrase replaced by the real call `estimate_decoy_bounds(gains=Q', qber_per_intensity=E', intensities)`; `Q'_vacuum > p_noise` assertion given its exact domain. (C4) Appendix A completed: exact optional dataclass additions to `ReceiverBlockResult`/`ProfileResult`/`PassResult`, sifted-count law `round(n_pulses·pi_signal·q·A·Q'_signal)`, exact `units` keys/strings, provenance leaf map for `profile.link_receiver`, full validator rejection matrix. (C5) Custom-effect audit contract closed: optional **`audit_spec()` protocol**; absent ⇒ type/effect IDs only with `parameters_complete: false`. Consistency edits: "bounded law" wording removed everywhere; `EffectRngError` → `SeedRequiredError`; §11 PDT row corrected to "partially adopted in v2.2, closed in v2.3"; untouched list binds implementation to **new test files only**.
**v2.1 → v2.2 changelog:** §12 numerical anchor corrected (`A = 0.918124082928941…` — the v2.1 value 0.9181237 came from a rounded intermediate; all anchors now stated to 12+ digits with a truncation clause) and the exact identity `R_click = f_rep · Q_bar_reg` added as an implementation simplification, second anchor, and test (§1.5, §12); estimator entry mechanism made explicit — `estimate_decoy_bounds` consumes post-afterpulse `Q'_vacuum` as `gains["vacuum"]`, never raw `p_noise`, with the full `y0`-slot mechanism stated (§1.2); PDT pulse-train semantics defined — `n_pulses` is a declared uniform-across-block exchangeable subsample of the physical pulse train, never a contiguous 0.01 s burst (§5); receiver/PDT **activation API** frozen as exact `simulate_pass` signature additions (§3.1); Appendix A upgraded to a **total** schema contract (totality clause + extension-subtree field schemas); PDT stochastic-effect classification made a closed-world **allowlist** contract with a `seed=None` deterministic-evaluation trap (§5); `e0 = ½` declared-limitation caveat (§1.3); `gate_window_s` required-when-consumed rule — no silent default (§2); named `PI_SUM_TOLERANCE` constant (§1.1); convex-mixture security justification for availability-weighted decoy bounds (§5); test-count environments named (header); v2.1 dispatch-gate answers table added (§11).
**v2 → v2.1 changelog:** emitted rate/result/schema contract frozen with the L5 yield identity preserved (R1, + Appendix A); PDT relabeled *unbounded log-normal with negligible-unphysical-tail validity guard*, node-domain rule added (R2); enforceable slow-fading applicability contract via `PdtConfig` timing + ratio guards (R3); control-registry partitioning and representable bounds (R4); receiver edge domains closed (R5); total wrapper/result mapping incl. honest-anomaly semantics (R6, + Appendix A); per-run replayability policy for unregistered effects (R7); file inventory, crossing-interpolation rule, per-gate test deltas, and a precomputed numerical anchor added (§12–§13).
**Depends on:** LINK-5 + TWIN-2 (merged). Baseline counts are **environment-conditional and must be named in any certification**: full environment with qiskit installed = **439 passed**; same environment with `--ignore=tests/test_teleportation_qiskit.py` = **418 passed**; environment without qiskit installed = **418 passed, 1 skipped**. All three are the same suite — the apparent reviewer discrepancy (Chat Claude's "418 passed, 1 skipped" vs Echo's non-reproduction) dissolves once the environment is stated.
**v1 → v2 changelog:** shared-history afterpulse model replacing the per-intensity cascade (B1); calibrated (p_ap, τ_d) operating-pair convention (B2); common dead-time availability with the decoy-equivalence property as a test (B3); explicit intensity-selection probabilities and rate-units contract (B4); noise ownership/cardinality contract, `coherence.py` reuse claim withdrawn (B5); `gate_window_s` enters as a declared control (B6); total consumption dataflow with `ReceiverInputs` and result plumbing (B7); PDT admissibility, bounded-law guard, and declared memory/fading order (B8); typed versioned replay manifest + production replay entry point (B9); built-in rate-owner effects added to scope (S1); benchmark comparability + artifact contract (S2/S3); "QKD receiver model" labeling (S4); "no opt-in LINK features" language (S5); Gate A–D internal sequence adopted.

---

## 0. Scope statement

LINK-6a consumes the four detector-side deferred observables (`background_rate_hz`, `dark_count_rate_hz`, `afterpulse_prob`, `dead_time_s`) through a **declared QKD receiver model** (S4 — the low-level gated-detection utility is general; the response wrapper is QKD-specific until a second caller earns the abstraction), integrates the PDT mode, and lands the control/audit/replay and benchmark layers. `bb84.py` is untouched; the wrapper reuses `estimate_decoy_bounds`/`secure_key_rate` and their semantics. Out of scope: LINK-6b fields (frequency offset, jitter, misalignment), source consumption (LINK-5 gate items 1–2), finite-key analysis (all emitted rates labeled **asymptotic, model-conditional**), adaptive control policy, sensing physics. The default path — **no opt-in LINK features** (S5; production effects are assembled on every call) — remains byte-identical; all frozen-hash tests unmodified.

## 1. The receiver model (B1/B2/B3/B4 — equations frozen for re-review)

### 1.1 Intensity selection (B4)

`ReceiverModel` requires explicit selection probabilities `pi = (pi_signal, pi_decoy, pi_vacuum)`: each **strictly positive** (R5 — this three-intensity estimator needs all three gains observable, and `pi_signal = 0` cannot produce key), summing to 1 within the **named constant `PI_SUM_TOLERANCE = 1e-9`** (v2.2 — a named module-level constant referenced by the validator and its tests, not an inline literal), validated at construction. No implicit equal split, no implicit `pi_signal = 1`.

**Units and emission contract (B4 + R1, binding — the L5 identity is preserved, not patched):**

1. **Canonical field:** `profile.secure_key_rate_per_pulse` is, on every run, the **delivered per-protocol-pulse rate** — its literal name. The existing L5 consistency law `secure_key_yield_bits = Σ_i rate_i · f_rep · dt_i` therefore remains valid **with no hidden multiplier** on receiver-active runs (the receiver path computes `rate = pi_signal · A · per_signal_pulse_rate` *before* writing the canonical field). The dashboard continues to read this field unchanged.
2. **Default path:** byte-identical, because the documented implicit legacy convention is `pi_signal = 1` and `A = 1` — signal-pulse and protocol-pulse rates coincide exactly.
3. **Per-signal diagnostic:** receiver-active runs additionally emit a **declared extension subtree** `profile.link_receiver` (one `DECLARED_SCHEMA_EXTENSIONS["profile"]` entry; extension-owned, validated by a dedicated light validator, not by ad-hoc loosening of L2–L5): `{secure_key_rate_per_signal_pulse: [...], pi: {signal, decoy, vacuum}, availability: [...], units: {...}}`. Exactly one array — the canonical field — is ever the yield source; the subtree is diagnostic by contract.
4. The complete `ProfileResult`/`PassResult`/emitted-JSON field mapping, with types, semantics (pre-dead-time live-gate vs delivered), and L5 relationships, is **Appendix A** (the table v2 referenced but omitted).

### 1.2 Noise mapping (B5 — ownership and cardinality contract)

Declared **aggregate single-detector-equivalent** receiver (matching the existing estimator's implicit model; `y0 = DetectorParams.dark_count_prob` remains the authoritative aggregate per-window vacuum yield; double-click policy remains out of scope, stated). Ownership rules:

- `background_rate_hz` — **absolute incident** background photon rate at the detector face; registered via the already-folded `detection_efficiency` (applied here **exactly once** for this observable; the single-fold discipline extends): `p_bg = 1 − exp(−η_det · R_bg · Δt_gate)`.
- `dark_count_rate_hz` — **absolute registered** dark rate of an *additional modeled source*, not a rate-form restatement of `y0` (no double counting by contract): `p_dk = 1 − exp(−R_dk · Δt_gate)`. A user modeling dark counts entirely in rate form sets `dark_count_prob = 0` and supplies the rate effect — supported and tested.
- Combination under declared independence: `p_noise = 1 − (1 − y0)(1 − p_bg)(1 − p_dk)`; exact for the declared aggregate Poisson/independent model; `p_noise ≡ y0` exactly when both rates are zero (parity anchor).
- The v1 claim of reusing `coherence.py`'s accidentals convention is **withdrawn** (B5): `B = R·R·Δt` is a coincidence-rate model; `1 − exp(−RΔt)` is a gate-occupancy probability. Same window, different mappings.

**Base-statistics route (C3, v2.3 — decided: reuse, not reproduce):** the wrapper obtains the base per-intensity statistics by calling the **existing public** `run_decoy_bb84(channel_state, intensities, n_pulses, detector_eff, eve=None)` on a **detector copy** `detector_eff = replace(detector, dark_count_prob=p_noise)` — `p_noise` thereby occupies the `y0` slot that `bb84.py` reads (`y0 = detector.dark_count_prob`), so **both** certified base laws are inherited unmodified: the gain law `Q_x = 1 − (1 − y0)e^(−ημ_x)` **and** the error-gain law `T_x = ½·y0 + e_d·(1 − e^(−ημ_x))` (the latter is *not* implied by the gain law — a receiver-side reproduction would have had to freeze and parity-pin it separately; reuse makes that unnecessary). The wrapper reads `Q_x = result.gains[x]`, `E_x = result.qber_per_intensity[x]`, `T_x = E_x·Q_x`. `bb84.py` is **never modified**. The base results pass through the §1.3 chain, and the **unchanged** estimator is then called exactly as:

```
estimate_decoy_bounds(gains=Q', qber_per_intensity=E', intensities=intensities)
    where the estimator's internal vacuum yield is Q'_vacuum == gains["vacuum"]
```

— the vacuum slot receives **post-afterpulse `Q'_vacuum`, never raw `p_noise`** (Echo, dispatch-gate review): afterpulses register in vacuum gates too, and a vacuum yield that excludes them would double-count that noise as single-photon signal. Then `q1' = Y1_L'·μ_s·e^(−μ_s)` and `secure_key_rate(Q'_s, E'_s, q1', e1_U', q=q, error_correction_efficiency=detector.error_correction_efficiency)` — the same two public functions `run_decoy_bb84` itself calls. The base call's own `sifted_key_length`, `secure_key_rate`, `y1_lower_bound`, `e1_upper_bound`, `q1`, `decoy_anomaly_score` are **discarded** (pre-receiver quantities); Appendix A defines every emitted replacement. **Honest anomaly reference (R6, made concrete):** in LINK-6a `receiver` and `eve` are mutually exclusive (`receiver` with `eve is not None` ⇒ named error, `ReceiverEveNotSupportedError` — receiver-aware Eve integration is a later PR whose path is structurally this one), so observed = honest and the receiver-aware reference score is `_relative_y1_shortfall(Y1_L', Y1_L') = 0.0` exactly (in-package reuse of the tiny private helper; the Gate-A default-path test asserts equality with `run_decoy_bb84`'s own score, which certifies the reuse). **Recorded for the later receiver-aware Eve PR (cleanup 3):** that PR must either promote **one canonical public anomaly helper** in `bb84.py` (a bb84 change, reviewed there) or route through the existing public Eve pipeline — it must **not** introduce a third anomaly formula; the private import here is an honest-6a-only convenience, not a precedent. Acceptance test: a receiver-active run with `p_ap > 0`, `Q_bar_reg > 0`, `p_noise < 1` asserts `gains["vacuum"] == Q'_vacuum > p_noise` at the estimator call boundary; at the all-zero (`Q_bar_reg = 0`) and saturated (`p_noise = 1`) boundaries the assertion is equality, tested separately.

### 1.3 Shared-history afterpulse model (B1 — Echo's candidate mean-field model, adopted after verification)

One detector history across interleaved intensities; explicit `pi_x`; base gains `Q_x` computed with `p_noise` per §1.2; error gains `T_x = E_x·Q_x`:

```
Q_bar     = Σ_x pi_x · Q_x                       (aggregate optical-gate occupancy)
Q_reg_bar = Q_bar / (1 − p_ap·(1 − Q_bar))        (registered-click rate with cascade;
                                                   validity: p_ap·(1 − Q_bar) < 1, enforced)
a         = p_ap · Q_reg_bar                      (afterpulse arrival probability per gate)
Q'_x      = 1 − (1 − Q_x)(1 − a)                  (union; gains stay in [0,1] structurally — no clipping)
T'_x      = T_x + ½·(1 − Q_x)·a                   (afterpulse-only events are random, e0 = ½;
                                                   collisions attribute error to the optical click)
E'_x      = T'_x / Q'_x
```

**Declared limitation (v2.2 — `e0 = ½` for afterpulse-only events):** assigning error ½ to afterpulse-only clicks assumes afterpulses carry no basis/bit correlation with the prior detection. In a real two-detector receiver, an afterpulse fires in the *same* detector that previously registered, biasing toward the previous outcome; modeling that requires per-detector cardinality, which this aggregate single-detector-equivalent receiver defers **together with the double-click policy** (§1.2) as one coupled future upgrade. Until then `e0 = ½` is the declared convention, recorded here as a limitation rather than a physical claim.

Satisfies all five structural rules of the review (shared history; explicit independent selection; cross-intensity afterpulses; bounded gains without clipping; error *gains* propagated). Recovers the aggregate `1/(1−p_ap)` factor only in the low-occupancy limit — and the v1 phrase "exact for the memoryless kernel" is **withdrawn**: this is a declared one-step next-live-gate **mean-field approximation** (branching-process expected progeny), not an exact gated-Bernoulli law.

**Edge domains (R5, binding):** `Q_bar_reg` is an aggregate registered-click **probability/occupancy per gate** (the first rate-valued quantity is `R_click`, §1.5). Consumer domain `0 ≤ p_ap < 1` — the receiver raises at `p_ap = 1` (singular branching fixed point, outside the first-order model), while the LINK-5 parameter owner retains its broad `[0, 1]` storage domain unchanged. `E'_x ≡ 0` when `Q'_x = 0` (the all-zero channel/noise case is defined, not `0/0`). Sanity identity (tested): the aggregate union `1 − (1 − Q_bar)(1 − a)` equals `Q_bar_reg` — the mean-field construction is internally consistent.

### 1.4 Operating convention (B2 — option 1 adopted)

`p_ap` is defined as the **calibrated probability of an afterpulse in the next live gate after the configured hold-off**: `(p_ap, dead_time_s)` form a **calibrated pair** under a named operating convention, recorded in provenance and benchmark configuration. Sweeping one member independently is disallowed by contract (the benchmark harness refuses such sweeps unless a calibration law is supplied); the model never implies dead-time changes leave `p_ap` physically unchanged. (Wiechers et al.; Losev et al.) The joint time-kernel model (option 2) is the declared future upgrade, not v1.

### 1.5 Common dead-time availability (B3)

```
R_click = f_rep · Σ_x pi_x · Q'_x                 (one shared candidate registered-click rate)
A       = 1 / (1 + R_click · τ_d)                 (non-paralyzable; labeled a continuous
                                                   mean-field approximation for a periodic
                                                   gated detector — not an exact gated law)
```

**Exact identity (v2.2 — implementation simplification and second anchor):** `Σ_x pi_x · Q'_x = 1 − (1 − a)(1 − Q_bar) = Q_bar_reg` (the same union collapse as the §1.3 sanity identity), hence **`R_click = f_rep · Q_bar_reg` exactly** — not approximately. The implementation may compute `R_click` either way; a test asserts the two forms agree to machine precision, and the §12 anchor states both.

**One common A for all intensities and the vacuum yield.** Route (chosen): the decoy estimator consumes **pre-dead-time** statistics via `estimate_decoy_bounds(gains=Q', qber_per_intensity=E', intensities)` with `gains["vacuum"] = Q'_vacuum` (§1.2, C3); every **delivered** quantity — sifted key length, canonical per-protocol-pulse rate, per-signal diagnostic rate, integrated key yield — is multiplied by the same `A`, consistently across all result representations (**Appendix A** enumerates every touched field). The algebraic equivalence with the supply-`A·Q'_x` route — `Y1_L(A·Q) = A·Y1_L(Q)`, `e1_U(A·Q, A·Y0) = e1_U(Q, Y0)`, `R(A·Q) = A·R(Q)` — holds precisely because A is common, and is an **explicit acceptance test**; per-intensity availability is demonstrably absent (tested).

**Honest-anomaly semantics (R6, binding):** the `decoy_anomaly_score` reference passes through the **same calibrated receiver model** as the observed statistics — a calibrated honest receiver must not read as QND/PNS Eve merely because detector memory changed the gain relationships. Acceptance: honest receiver-active runs score ≈ 0 anomaly within a declared tolerance; future Eve integration compares receiver-aware honest vs observed statistics through this same path. Wrapper return type: `ReceiverBlockResult` (frozen), whose complete field-by-field mapping from `BB84Result` (which fields are pre-dead-time live-gate diagnostics — gains, `Y1_L`, `q1` — vs delivered quantities, and where `pi_signal` and `A` each apply) is Appendix A.

## 2. The gate window is a declared control (B6 — v1 deferral withdrawn)

`gate_window_s` enters through the **ratified control surface**: the receiver wrapper implements `Controllable`, declaring `ControlSpec("gate_window_s", unit="s", bounds=(MIN_GATE_WINDOW_S, 1/pulse_repetition_rate_hz))` — run-level constant in 6a (no adaptive policy); future feasibility coupling to composed `timing_jitter_s` attaches to this same field without changing its identity.

**Registry partitioning (R4, binding — no `link.py` change):** the live `ChannelStack` validates controls against its own effect-owned registry and would reject estimator-owned names if handed the combined mapping. Mission composition therefore: (1) builds **one collision-checked union registry** from stack-effect controls plus estimator `Controllable`s; (2) validates the complete caller `link_controls` mapping **once** against the union (undeclared names rejected there); (3) **partitions values by owner**; (4) passes only effect-owned controls into `ChannelStack.evaluate(...)`; (5) passes only receiver-owned controls into the receiver.

**Required-when-consumed rule (v2.2 — no silent default):** `gate_window_s` has **no default value**. Whenever the receiver path would consume it — i.e. `extract_receiver_inputs` returns a non-identity `background_rate_hz` or `dark_count_rate_hz` (the two observables whose mapping `1 − exp(−R·Δt_gate)` depends on the window) — the caller must supply it in `link_controls`, else the mission raises a **named error** at composition time (a silent default window would silently set the scale of `p_bg`/`p_dk`, exactly the class of implicit convention B4/B6 exist to forbid). When neither rate observable is active the control is unused: supplying it is still accepted, validated against bounds, and recorded (audit + manifest) — never silently dropped.

**Bounds representation (R4):** `ControlSpec.bounds` is a closed interval; "strictly positive" is realized by the named constant `MIN_GATE_WINDOW_S = 1e-12` (1 ps, far below any physical gate) as the closed lower bound, with the model-coupled upper bound `1/f_rep` evaluated at registry assembly (the non-overlap rule). Tests cover zero, NaN, ±inf, and just-inside-bound values. The control value appears in the audit record and the replay manifest. This is the first *production* declared control, which is precisely why the R4 audit-emission prerequisite lands in the same PR (§4).

## 3. Consumption dataflow (B7 — total and single-owned)

```
ChannelStack.evaluate(t_k)  →  EffectiveLinkState_k
      │
      ├─ extract_receiver_inputs(state_k) →  (ReceiverInputs_k, residual_k)
      │     ReceiverInputs (frozen): background_rate_hz, dark_count_rate_hz,
      │     afterpulse_prob, dead_time_s          [exactly these four; returned
      │     as the declared consumed-field set]
      │
      ├─ residual_k → apply_link_state(...)  [unchanged bridge: still raises on ANY
      │     other non-identity field — intensity_factor, frequency_offset_hz,
      │     timing_jitter_s, misalignment_error]
      │
      ▼
per-sample ReceiverInputs list  →  mission profile loop  →  receiver wrapper around
estimate_decoy_bounds/secure_key_rate (per sample, time-varying rates reach their
matching sample — never collapsed to one pass-wide object)  →  PassResult
      │
      └─ PassResult.link_provenance (optional frozen record, produced by the SAME
         simulation)  →  run._build_results emits it — run.py never re-evaluates
         or reconstructs stack state
```

No field is "consumed" merely because rejection was skipped: `extract_receiver_inputs` returns the exact consumed set, and the residual bridge fails on everything else (tested field-by-field).

### 3.1 Activation API (v2.2, frozen — the exact `simulate_pass` surface)

The current signature is `simulate_pass(config=None, *, eve=None, link_effects=None, link_seed=None, link_controls=None) -> PassResult`. LINK-6a adds **exactly three keyword-only parameters**, all defaulting to inactive:

```python
def simulate_pass(
    config: MissionConfig | None = None,
    *,
    eve=None,
    link_effects: Sequence[ChannelEffect] | None = None,
    link_seed: int | None = None,
    link_controls: Mapping[str, float] | None = None,
    receiver: ReceiverModel | None = None,            # NEW — the receiver activation switch
    link_mode: str = "sampled",                       # NEW — "sampled" | "pdt" (named error otherwise)
    pdt_config: PdtConfig | None = None,              # NEW — required iff link_mode == "pdt"
) -> PassResult
```

Activation rules (binding):

1. **`receiver=None` (default) is the legacy path, byte-identical** — the residual bridge continues to reject any non-identity detector-side field, with the rejection message extended to name `receiver=` as the activation route. Activation is **explicit-only**: the presence of detector-side effects never implicitly constructs a receiver.
2. **`receiver=ReceiverModel(...)` activates the §1 path.** `ReceiverModel` carries `pi`, the §1.4 operating-convention label, and the estimator glue; the four physical observables still arrive per-sample via `ReceiverInputs` from the stack. A receiver supplied with an all-identity stack is **allowed** (it runs on baseline `y0`, `p_ap = 0`, `τ_d = 0` — useful for π-only studies) and is receiver-active for every emission/provenance purpose, including `profile.link_receiver` and the canonical `pi_signal · A` field semantics.
3. **`link_mode="pdt"` requires `receiver` and `pdt_config`** (each absence is its own named error); `pdt_config` supplied in `"sampled"` mode is a named error (configuration is rejected, never silently ignored). `link_mode` and the `PdtConfig` values are recorded in the §4 manifest (`mode` field).
4. **`n_pulses` keeps its existing home** (`MissionConfig` / estimator block size); its PDT-mode semantics are defined in §5 (uniform-across-block subsample), with the `n_pulses ≤ f_rep · block_duration_s` consistency check enforced at PDT admission.

## 4. Provenance and replay (B9 — typed manifest, real protocol)

**Schema reality respected:** the deep validator requires `run_metadata` values to be strings, and the extension registry governs vocabulary, not nested types. Therefore `run_metadata.link_provenance` is a **canonical-JSON string** (sorted keys, declared separators) containing a **versioned replay manifest**: `manifest_version`; complete mission/profile configuration; ordered effect specs with stable type identifiers via a **built-in effect registry** with explicit `to_spec`/`from_spec` per effect (allowlisted constructor parameters — `dataclasses.asdict` is *not* the protocol; `init=False`/derived fields excluded by construction); `link_seed`; declared controls incl. `gate_window_s`; `pi` probabilities and receiver/detection configuration incl. the §1.4 operating convention; mode (`sampled`/`pdt`) and model identifiers; pipeline/schema version; canonical serialization rules. A **production replay entry point** `replay_from_provenance(manifest_json) -> PassResult` rejects unknown effect types and unknown fields; the acceptance test replays through the **real** simulation and emission path to byte-identical output.

**Per-run replayability policy (R7 — the downgrade clause made a run-level rule):** the manifest carries a required `replayability` status. If every active effect has a registered codec, status = `"replayable"` and the round-trip guarantee applies. If a custom `ChannelEffect` without a registered codec is active, emission proceeds with status = `"configuration_auditable"` and `replay_from_provenance` **refuses that manifest with a named reason** (it never half-replays). **What makes it auditable (C5, decided — `ChannelEffect` has no declared-parameter interface and generic dataclass serialization is forbidden):** the manifest's entry for such an effect always carries `{effect_id, type_id: "<module>.<qualname>", parameters_complete: bool, params}`, filled by exactly one of two rules. (a) If the effect implements the **optional protocol `audit_spec(self) -> Mapping[str, float | int | str | bool | None]`** (JSON-scalar values only; validated at emission — non-scalar or non-finite ⇒ named error), `params = audit_spec()` and `parameters_complete = true` — the *effect author* asserts completeness and is the accountable party. (b) Otherwise `params = {}` and `parameters_complete = false` — the run is auditable **as to identity and position only**, and the manifest says so; no run is described as parameter-auditable when constructor parameters are silently unavailable. The status word `"configuration_auditable"` is retained for both cases because the `parameters_complete` flag carries the distinction explicitly and is itself replay-refused either way. Registered built-ins always yield `"replayable"`. And restated as part of the frozen contract: `run_metadata.link_provenance` is **absent** when no opt-in LINK feature is active — its absence *is* the default-path byte-identity.

## 5. PDT consumption (B8 — admissibility, unbounded log-normal with validity guard, declared order)

- **Stack admissibility (v2.2/v2.3 — closed-world allowlist, exact members, C2):** classification is by **stable `effect_id`** membership in `PDT_ADMISSIBLE_EFFECTS`, a frozen mapping `effect_id → {"deterministic", "law"}` — the exact contract, no implementer discretion:

  | classification | `effect_id` members |
  |---|---|
  | `deterministic` | `system_efficiency`, `atmospheric_absorption`, `geometric_loss`, `detector_qe` (production four); `doppler_shift`, `pointing_loss` (LINK-3); `detector_afterpulsing`, `detector_dead_time` (LINK-5); `background_light`, `detector_dark_rate` (§6, this PR) |
  | `law` | `scintillation_fading` (the only law-capable type: exposes `stationary_law`) |
  | **not admissible** (sampled-mode only) | `pointing_jitter`, `mu_fluctuation` (stochastic without a stationary-law interface), and **every** custom/unregistered `effect_id` |

  PDT mode requires **exactly one** `law` member and rejects any non-member **by `effect_id` at admission, before any evaluation** (named `PdtInadmissibleEffectError`; the same closed-world rule as §4 replay; sampled mode remains the open extension path). No attempt is made to infer whether an arbitrary effect is stochastic — an undecidable classification is replaced by a decidable membership test. (`doppler_shift` is admissible by classification but its non-identity `frequency_offset_hz` is still rejected downstream by the residual bridge — LINK-6b territory — so it cannot in practice appear in a receiver-active stack; listed for completeness of the contract.)

- **Deterministic-stack evaluation path (C2, frozen five-step sequence):** the accepted law effect's `evaluate(...)` calls `context.rng_for("fade")` and would trip the seed trap if evaluated, so it is **excluded from evaluation**, not merely allowlisted. Binding sequence per profile sample: (1) identify the single `law` member; **it must be the last effect in the composed stack** (production four + user effects, in order) — otherwise named error `PdtLawEffectNotLastError` (this makes "all other effects" literally the stack prefix, so applying the fading factor afterward is *exactly* the sampled composition with the drawn `f` replaced by the node `f_i`; no commutation assumption is needed); (2) obtain `law = law_effect.stationary_law(pass_geometry)` once per sample geometry; (3) build a `ChannelStack(prefix_effects, provider, seed=None)` from all other admitted effects, preserving order, and evaluate it with the effect-owned control subset → `η_base(t_k)` and the full deterministic state; (4) for each Gauss–Hermite node `f_i` of the law, form the physical node state with transmittance `η_base·f_i` (never calling the law effect's `evaluate`); (5) feed each node state through §3 extraction and the §1 receiver chain, then average per the ratios below. **Defense in depth (executable, name corrected):** because the prefix stack is constructed with `seed=None`, any admitted effect that nevertheless requests randomness raises LINK-1's existing **`SeedRequiredError`** (`link.py`; the v2.2 name `EffectRngError` was wrong — no such class exists). Tests: a deliberately misclassified admitted *test* effect requesting RNG must raise `SeedRequiredError`; unregistered custom effects and `pointing_jitter` must fail earlier, at allowlist admission. Joint distributions and mixed sampled/quadrature modes are declared future work. Determinism/seed-independence claims are thereby scoped to the admissible stack only.
- **Tail/support rule (R2 — accurate labeling, complete rule):** the model is an **unbounded log-normal approximation with a negligible-unphysical-tail validity guard** — *not* a bounded law (a tail guard does not bound a distribution; the truncated-and-renormalized alternative is declared future work and would have to change the sampled generator identically). The complete rule: (i) declared tail tolerance `PDT_TAIL_TOLERANCE = 1e-9` on the mass with `η_base(t)·f > 1`, exceeded ⇒ raise; the admitted tail mass enters the stated numerical error budget alongside the quadrature-convergence tolerance; (ii) **every quadrature node of both the 21- and 41-node rules** must satisfy `η_base·f_i ≤ 1`, otherwise raise — no node is ever evaluated above physical transmittance; (iii) the sampled-mode bridge raise for an actually-drawn unphysical total is retained unchanged; (iv) the sampled/PDT consistency test runs only in a declared regime where (i) and (ii) pass. Never clip, never silently renormalize.
- **Memory/fading order with an enforceable applicability contract (R3):** the declared order is `conditional_then_average`, valid under the timescale hierarchy detector memory (µs) ≪ fading coherence (ms) ≪ estimation block (~0.1–1 s). Because `LogNormalLaw` carries no timing, the timing is supplied by a **`PdtConfig`** (frozen): `fading_coherence_time_s` and `block_duration_s`, both required and explicit. Enforced guards (declared constants, C1-revised): **memory guard** `fading_coherence_time_s ≥ PDT_MEMORY_RATIO · τ_mem` with `PDT_MEMORY_RATIO = 20` and the declared **effective memory scale `τ_mem = dead_time_s + 1/f_rep`** — the next-live-gate afterpulse convention (§1.4) carries at least one gate period of memory even at `dead_time_s = 0`, so the v2.2 guard `τ_c ≥ 20·τ_d` was vacuous there; under live defaults `1/f_rep = 10 ns`, so the guard is non-vacuous yet trivially satisfied by any physical τ_c (default τ_c = 3 ms vs τ_mem = 1.01 µs at τ_d = 1 µs); and **stationarity guard** `block_duration_s ≥ PDT_BLOCK_RATIO · fading_coherence_time_s` with `PDT_BLOCK_RATIO = 50`. **Block-duration binding (C1, decided):** `block_duration_s` is the wall-clock width of the profile bin, and the mission **validates the caller's value against the actual grid**: the default pass grid is uniform (`time_s[k+1] − time_s[k] = 0.476955506437 s` for all k, verified to relative tolerance `PDT_GRID_UNIFORMITY_REL_TOL = 1e-9` — a non-uniform grid is a named error, binning contracts for non-uniform axes are future work), the **final sample reuses that same uniform width** (conservative minimal rule), and `|block_duration_s − grid_width| ≤ PDT_BLOCK_BINDING_REL_TOL · grid_width` with `PDT_BLOCK_BINDING_REL_TOL = 1e-6`, else named error `PdtBlockDurationMismatchError` naming both values — a caller can no longer attach a fictitious 10 s block to a 0.477 s sample. It is **not** `n_pulses/f_rep` (0.01 s under live defaults 10⁶/10⁸ — only ~3 coherence intervals at τ_c = 3 ms); consistency check `n_pulses ≤ f_rep × block_duration_s` (10⁶ ≤ 4.77×10⁷ under defaults). Both timing values, the derived `τ_mem`, and the order label are recorded in provenance. A law-capable effect plus caller-supplied `PdtConfig` timing is the admission contract; configurations that cannot supply timing are rejected. Per Gauss–Hermite node f: optical gains `Q_x(η·f)` → §1 receiver chain (shared afterpulse, common `A(f)`) → then average. The estimator consumes **observed-statistics ratios**, matching what a real block measurement yields under slow fading:

```
Q̂_x = E_f[ A(f) · Q'_x(f) ] / E_f[ A(f) ]          T̂_x = E_f[ A(f) · T'_x(f) ] / E_f[ A(f) ]
Ê_x = T̂_x / Q̂_x                                     delivered rates scale by E_f[ A(f) ]
```

(the E̅ = E[EQ]/E[Q] rule, generalized to availability-weighted observed statistics; the naive orders `A(E[Q])·E[Q]` and unweighted averages are demonstrated inequivalent in a test — the mean-collapse prohibition made executable). Quadrature: fixed 21 Gauss–Hermite nodes, convergence vs 41 asserted; PDT-vs-sampled-ensemble consistency asserted under the same unbounded log-normal law with validity guard and the same declared order.

**Security justification for the availability-weighted ratios (v2.2):** the weights `w(f) = A(f)·p(f) / E_f[A]` are non-negative and integrate to 1 — a legitimate probability measure. Under it, each observed gain remains a **convex mixture over photon number**, `Q̂_μ = Σ_n P(n|μ) · Ŷ_n` with `Ŷ_n = E_w[Y_n(f)]` shared across intensities (the Poisson photon-number statistics are set at the source and do not depend on `f`), so the decoy-state linear-programming bounds retain their validity for the availability-weighted effective channel: `Y1_L`/`e1_U` computed from `(Q̂_x, Ê_x)` bound the availability-weighted single-photon parameters. The estimate is model-conditional on the declared slow-fading order, consistent with the plan-wide **asymptotic, model-conditional** labeling (§0).

**`n_pulses` semantics on PDT runs (v2.3 — restated on the live defaults; independence claim withdrawn, C1):** the live mission constants are `DEFAULT_N_PULSES = 10⁶` and `PULSE_REPETITION_RATE_HZ = 10⁸ s⁻¹` (`mission.py`; the v2.2 text wrongly used the anchor fixture's 10⁴/10⁶ — the ratio `n_pulses/f_rep = 0.01 s` is the same, which is how the substitution hid). The physical pulse train per default profile sample is `f_rep · block_duration_s = 10⁸ × 0.476955506437 s ≈ 4.77×10⁷` pulses. `n_pulses` is the estimator's per-sample statistical block size and on PDT runs is declared a **uniformly distributed expected-count subsample of the total protocol pulses in the block** (used for PDT diagnostics and the sifted-count normalization, Appendix A). Its fading values are **exchangeable — not independent**: uniform placement over ≥ 50 coherence intervals samples the stationary *marginal*, which is exactly the average the quadrature computes, but pulses falling within the same ≈ 3 ms coherence interval remain correlated, and fifty intervals do not make individual pulses independent. **LINK-6a computes deterministic asymptotic expectations only; it makes no finite-key independence claim, and temporal correlations inside the block are outside the (out-of-scope, §0) finite-key model.** The **contiguous-burst reading is explicitly not the model**: 10⁶ consecutive pulses at 10⁸ s⁻¹ span 0.01 s ≈ 3 coherence intervals, would *not* sample the stationary distribution, and would require per-coherence-interval conditioning — declared out of scope. The admission checks are the executable form of this declaration: `n_pulses ≤ f_rep · block_duration_s` (a subsample cannot exceed the train it samples) together with the stationarity and memory guards; the `PdtConfig` docstring carries this paragraph's declaration verbatim.

## 6. Scope additions (S1) and benchmark contract (S2/S3)

- **Built-in rate owners (S1, in scope and reviewed here):** `BackgroundLightEffect(background_rate_hz)` and `DetectorDarkRateEffect(dark_count_rate_hz)` — constant-parameter owners in `effects.py`, LINK-2 pattern (fixed IDs `background_light`, `detector_dark_rate`; construction-time domains finite ≥ 0; docstrings carrying the §1.2 ownership contract). Custom effects are thereby not the only activation path.
- **Benchmark comparability (S2):** paired configurations must be **named realizable or explicitly declared counterfactual** setups with *all* coupled parameters listed (a tighter gate window carries its jitter-acceptance/efficiency costs; a lower-afterpulse detector carries its calibrated pair). "Ideal vs degraded" is not an advantage claim and the harness refuses single-parameter favorable sweeps that violate a declared calibration pair (§1.4). Metric direction and equality tolerance declared per artifact.
- **Artifact contract (S3):** each `outputs/benchmark_*.json` carries: `artifact_version`; axis name + units; metric name + units + direction; ordered named configurations with full parameter blocks; assumptions; a provenance/replay link; bracket semantics distinguishing **sampled endpoints** from the **interpolated crossing**, retaining both neighboring samples. A dedicated light validator enforces all of it (missing units / ambiguous brackets / incomplete assumptions rejected).

## 7. Implementation gates (per review §6 — internal, sequential)

**Gate A** — receiver contract & bridge seam: §1 declarations + §3 extractor + identity anchors + the B3 equivalence proof, before any mission emission. **Gate B** — mission integration & replay manifest: §3 plumbing + §4 manifest/entry point, default-path bytes preserved. **Gate C** — PDT (§5). **Gate D** — benchmark artifacts (§6). Each gate's tests pass before the next becomes dependent; a failed Gate-A re-review stops the PR before schema/benchmark surfaces exist.

## 8. Acceptance tests

The v1 obligations (byte-identity set; window-mapping hand calculations; receiver hand calculations; PDT convergence/consistency; provenance round-trip; boundary reassertions; suite green from 439) **plus Echo's fifteen additions verbatim** (review §7): shared afterpulse burden crossing intensity classes; `pi` changes detector load but not base optical gains; common-A scaling of `Y1_L`/R with `e1_U` invariance; per-intensity A demonstrably absent; boundedness without clipping near model boundaries; operating convention in provenance + disallowed independent sweeps failing; dark-count ownership no-double-count rule; detector-cardinality hand computations; `gate_window_s` only via its declared control with period bounds; exact consumed-field set with all 6b/source fields still rejected; time-varying rates reaching matching samples; PDT stack-admissibility rejections; shared unbounded-log-normal-with-validity-guard law + declared order across modes; production replay from manifest with unknown-type/field rejection; benchmark validator rejections.

**v2.2 additions:** `gains["vacuum"] == Q'_vacuum > p_noise` asserted at the estimator call boundary on a `p_ap > 0` run (§1.2); two-form `R_click` identity to machine precision (§1.5); anchors asserted to ≥ 12 significant digits against the independent derivation (§12); allowlist rejection of a non-registered effect type in PDT mode **and** the `seed=None` trap raising the live `SeedRequiredError` on a deliberately misclassified admitted test effect that requests RNG (§5); `gate_window_s` required-when-consumed named error, and accepted-but-unused recording (§2); §3.1 activation-rule errors (`pdt` without receiver, `pdt` without `pdt_config`, `pdt_config` in sampled mode, unknown `link_mode`); `n_pulses > f_rep·block_duration_s` rejected at PDT admission (§5); A.1/A.2 closed-world validators rejecting an unknown key.

**v2.3 additions:** `PdtLawEffectNotLastError` when the law effect is not last; `PdtInadmissibleEffectError` for `pointing_jitter`, `mu_fluctuation`, and a custom effect, raised **before** any evaluation; the deterministic-prefix path reproduces sampled-mode composition exactly when the drawn `f` is replaced by a node `f_i` (a test effect stack with a fixed-`f` stand-in); `PdtBlockDurationMismatchError` on a 10 s claim against the 0.477 s grid, and acceptance within tolerance; grid non-uniformity named error; memory guard non-vacuous at `dead_time_s = 0` (fails for `τ_c < 20/f_rep`); Gate-A parity: `receiver=None` remains byte-identical, and on a receiver-active run with identity `ReceiverInputs` and `p_ap = 0` the wrapper's base call reproduces `run_decoy_bb84`'s gains/QBERs exactly (reuse certification), with `decoy_anomaly_score` equal to the estimator's own; `ReceiverEveNotSupportedError`; `audit_spec()` scalar validation and `parameters_complete` flag both ways; A.4 tag set exact (missing/extra tag negative tests); the full A.5 matrix; every constant (`PI_SUM_TOLERANCE`, `MIN_GATE_WINDOW_S`, `PDT_TAIL_TOLERANCE`, `PDT_MEMORY_RATIO`, `PDT_BLOCK_RATIO`, `PDT_GRID_UNIFORMITY_REL_TOL`, `PDT_BLOCK_BINDING_REL_TOL`, `LINK_PIPELINE_VERSION`) referenced by name in its test.

**v2.3.1 additions:** A.4 exact provenance-map assertion and the negative `pi`-tagged-`SIMULATED` test (F1); nested closed-world rejections for each A.2 object — an unknown key inside `mission_config`, `mission_config.atmosphere`, `mission_config.detector`, `receiver`, `pdt_config`, `model_ids`, `serialization`, and a registered `effects[i].params` (F2); `receiver` object containing `p_ap`/`dead_time_s` rejected (single ownership); codec `param_keys` anti-drift test over all thirteen registered `effect_id`s; `production_effects` order pinned; `sky_condition` outside the enum rejected.

## 9. Answers to the first review's §9 gate questions (v2, retained for the record)

| Q | Answer |
|---|---|
| 1 | §1.3 — shared mean-field history: aggregate `Q_bar` → cascade `Q_reg_bar` → per-gate arrival `a`, union into every intensity class |
| 2 | §1.4 — `p_ap` = calibrated next-live-gate probability under the configured hold-off; `(p_ap, τ_d)` a calibrated pair, convention in provenance |
| 3 | §1.1 — explicit validated `pi`; units contract: legacy field frozen, receiver metrics per-signal-pulse and per-protocol-pulse with `pi_signal` explicit |
| 4 | §1.5 — one common A from the shared candidate click rate; estimator consumes pre-dead-time statistics; delivered quantities scale by A; equivalence tested |
| 5 | §1.2 — background: absolute incident, × η_det once; dark rate: absolute registered, additional-source ownership; y0 authoritative aggregate; single-detector-equivalent; double-click out of scope, stated |
| 6 | §2 — `Controllable` on the receiver wrapper, `ControlSpec` with period-coupled bounds, registry + audit + manifest, run-level constant |
| 7 | §3 — `ReceiverInputs` per sample, extractor returning the exact consumed set, residual bridge unchanged, `PassResult.link_provenance` carried to the emitter |
| 8 | §5 — exactly one law-capable effect; [0,1] guard by mass tolerance, shared across modes; slow-fading conditional-then-average order with observed-statistics ratios |
| 9 | §4 — versioned canonical-JSON manifest (string-valued, validator-compatible), effect registry with `to_spec`/`from_spec`, production `replay_from_provenance`, downgrade-by-decision rule |
| 10 | §6 — named realizable/declared-counterfactual pairs with coupled costs; calibration-pair sweeps refused; artifact contract enforced by validator |

## 10. Answers to the v2 re-review gate (the seven confirmation questions)

| Q | Answer |
|---|---|
| 1 | §1.1 — `profile.secure_key_rate_per_pulse` **is** the canonical delivered per-protocol-pulse rate on every run; L5 recomputes yield as `Σ rate·f_rep·dt` with no hidden multiplier (the receiver applies `pi_signal·A` *before* writing the field); default path coincides via legacy `pi_signal = 1, A = 1` |
| 2 | Appendix A — complete `ProfileResult`/`PassResult`/emitted-field enumeration; the one new emitted subtree is `profile.link_receiver` (declared extension, dedicated validator) plus the string-valued `run_metadata.link_provenance` |
| 3 | §5 — unbounded-log-normal-with-guard labeling; tail mass > 1e-9 raises and admitted mass enters the error budget; **every** 21- and 41-rule node must satisfy `η_base·f_i ≤ 1` or raise; sampled-mode bridge raise retained; consistency test scoped to the valid regime |
| 4 | §5 — `PdtConfig(fading_coherence_time_s, block_duration_s)` supplies timing; guards `τ_c ≥ 20·τ_d` and `block ≥ 50·τ_c`; block = profile sample spacing (≈0.48 s default, ~160 coherence intervals), explicitly not `n_pulses/f_rep`; `n_pulses ≤ f_rep·block` consistency check; values + order label in provenance *(v2.3 supersedes the memory guard with `τ_mem = τ_d + 1/f_rep` and binds `block_duration_s` to the grid — §5, §11.1)* |
| 5 | §2 — union registry collision-checked at mission composition; caller mapping validated once; owner-partitioned; effect-owned subset → stack, receiver-owned → receiver; `MIN_GATE_WINDOW_S = 1e-12` closed lower bound, `1/f_rep` model-coupled upper bound; zero/NaN/inf/just-inside tested |
| 6 | §1.3/§1.5 + Appendix A — strict-positive `pi`; `E'_x ≡ 0` at `Q'_x = 0`; consumer domain `p_ap < 1`; `Q_bar_reg` labeled an occupancy; full `BB84Result → ReceiverBlockResult` mapping with pre-dead-time vs delivered semantics; honest receiver ≈ 0 anomaly through the receiver-aware reference |
| 7 | §4 — per-run `replayability` status: unregistered active effect ⇒ `"configuration_auditable"` emission and a named replay refusal; all-registered ⇒ `"replayable"` with the byte-identical round-trip guarantee |

## 11. Answers to the v2.1 dispatch-gate reviews (Chat Claude + Echo, 2026-08-17)

| Finding | Source | Disposition in v2.2 |
|---|---|---|
| Anchor `A ≈ 0.9181237` wrong; correct `0.918124082928941` | both (must-fix) | **Adopted** — §12 anchor corrected, 12+ digits, truncation clause; the v2.1 value came from recomputing A off a rounded `R_click ≈ 89177.85` instead of the exact `f_rep·Q_bar_reg = 89177.3983…` |
| `R_click = f_rep·Q_bar_reg` exact identity | Chat Claude | **Adopted** — §1.5 implementation note, second anchor, machine-precision test |
| Estimator must consume post-afterpulse `Q'_vacuum` as `gains["vacuum"]`, not raw `p_noise`; state the `y0`-slot entry mechanism | Chat Claude, sharpened by Echo | **Adopted** — §1.2 binding mechanism + acceptance test at the estimator call boundary |
| PDT still conflates the ≈ 0.48 s profile bin with the 0.01 s pulse train; `n_pulses` meaning undefined | Echo | **Partially adopted in v2.2** (subsample model chosen, but on the wrong defaults, with a false independence claim, unbound duration, and a vacuous zero-dead-time memory guard — v2.2 review C1); **closed in v2.3** — §5 restated on live 10⁶/10⁸ defaults, exchangeable-not-independent, `block_duration_s` bound to the grid, `τ_mem = τ_d + 1/f_rep` |
| Receiver/PDT activation API and `simulate_pass` surface undefined | Echo | **Adopted** — §3.1 frozen signature (three new keyword-only parameters) + activation rules 1–4 |
| Appendix A not yet a total schema contract | Echo | **Adopted** — totality clause + typed extension-subtree schemas + not-listed-means-frozen rule |
| PDT needs an allowlisted stochastic-effect classification | Echo | **Adopted** — §5 closed-world `PDT_ADMISSIBLE_EFFECTS` registry + `seed=None` `SeedRequiredError` trap (name corrected in v2.3, C2) |
| `e0 = ½` caveat for afterpulse-only events | Chat Claude | **Adopted** — §1.3 declared limitation, coupled to the deferred double-click/per-detector upgrade |
| Default `gate_window_s` behavior when the control is absent | Chat Claude | **Adopted as refuse-not-default** — §2 required-when-consumed rule, named composition-time error |
| Named π-sum tolerance | Chat Claude | **Adopted** — `PI_SUM_TOLERANCE = 1e-9` (§1.1) |
| Convex-mixture security sentence for availability-weighted decoy bounds | Chat Claude | **Adopted** — §5, with the model-conditional scope stated |
| "418 passed, 1 skipped" did not reproduce on the full environment | Echo (on Chat Claude's run) | **Reconciled, no defect** — environment-conditional counts named in the header; certification must name the environment |

### 11.1 Answers to the v2.2 confirmation review (Echo, `docs/LINK_6A_V22_REVIEW.md`) — the six final-gate questions

| Gate Q | Finding | Disposition in v2.3 |
|---|---|---|
| 1 | C1 — anchor-fixture 10⁴/10⁶ substituted for live 10⁶/10⁸; "independent fading draws" false | **Adopted** — §5 rewritten on `DEFAULT_N_PULSES = 10⁶`, `f_rep = 10⁸`, ≈ 4.77×10⁷ physical pulses/sample; exchangeable-not-independent; deterministic asymptotic expectations only; contiguous-burst reading excluded |
| 2 | C1 — `block_duration_s` unbound; zero-dead-time memory guard vacuous | **Adopted** — grid-uniformity check + `PDT_BLOCK_BINDING_REL_TOL = 1e-6` binding with named mismatch error, final sample reuses uniform width; `τ_mem = dead_time_s + 1/f_rep`, guard `τ_c ≥ 20·τ_mem` |
| 3 | C2 — law effect not excluded from `seed=None` stack; allowlist members unnamed; `EffectRngError` does not exist | **Adopted** — five-step deterministic-prefix sequence with law effect required last and never evaluated; `PDT_ADMISSIBLE_EFFECTS` enumerated by `effect_id` with classification; live `SeedRequiredError` named in plan and tests |
| 4 | C3 — base error-gain route undefined; stale three-argument `(Q', E', p_noise)` phrases | **Adopted (reuse route)** — `run_decoy_bb84` on `replace(detector, dark_count_prob=p_noise)` inherits both certified base laws; real `estimate_decoy_bounds(gains=Q', qber_per_intensity=E', intensities)` call everywhere; `Q'_vacuum > p_noise` domain stated; receiver+Eve mutually exclusive in 6a (named error) |
| 5 | C4 — Appendix A not total: dataclass fields, sifted-count law, unit strings, provenance leaves, validator matrix | **Adopted** — A.3 (exact optional fields), sifted `round(n_pulses·pi_signal·q·A·Q'_signal)`, A.1 exact `units`, A.4 seven tagged leaves with pinned tags, A.5 rejection matrix (one named negative test per row) |
| 6 | C5 — no parameter interface for custom-effect auditability | **Adopted** — optional `audit_spec()` protocol (JSON scalars, author-asserted completeness) else `parameters_complete: false`; manifest entry `{effect_id, type_id, parameters_complete, params}` |
| — | Consistency edits 1–5 | **All applied** — "bounded law" wording removed (§5 heading, ratios line, §8); stale estimator tuple replaced; `EffectRngError` → `SeedRequiredError` everywhere; §11 PDT row corrected; untouched list binds implementation to new test files only |

### 11.2 Answers to the v2.3 confirmation review (Echo, `docs/LINK_6A_V23_REVIEW.md`)

| Finding | Disposition in v2.3.1 |
|---|---|
| F1 — `pi.*` provenance must be `ILLUSTRATIVE` | **Adopted** — A.4 map split SIMULATED (two arrays) / ILLUSTRATIVE (`pi.*`, `units.*`); positive exact-map assertion + negative `pi`-as-SIMULATED test |
| F2 — nested manifest vocabularies unenumerated; calibrated pair duplicated in `receiver` | **Adopted** — A.2 table + A.2.1 `mission_config` (ten keys, resolved atmosphere, detector, intensities, sky enum) + A.2.2 codec `param_keys` per `effect_id` with an anti-drift test; `receiver` reduced to `pi` + `operating_convention`; `production_effects` ids-only; `model_ids`/`serialization` exact; `pipeline_version` introduced as a named constant |
| Cleanup 1 — `availability` is `A` sampled / `E_f[A]` PDT | **Adopted** — A.1, A.3.1 |
| Cleanup 2 — A.3 heading over-claims optionality | **Adopted** — split into A.3.1 (required `ReceiverBlockResult`) and A.3.2 (optional trailing additions) |
| Cleanup 3 — private anomaly helper | **Adopted** — §1.2 records the future-Eve-PR rule: promote one public helper or reuse the public Eve pipeline; never a third formula |
| Cleanup 4 — Appendix A label | **Adopted** — relabelled v2.3.1 |

## 12. File inventory and implementation clarifications (R-clarifications)

**Create:** `src/qkd/detection.py` (gated-detection utility + `ReceiverModel`/`ReceiverInputs`/`ReceiverBlockResult` + `PdtConfig`), `src/qkd/replay.py` (manifest, effect registry, `replay_from_provenance`), `src/qkd/benchmark.py`, `tests/test_detection.py`, `tests/test_link6a.py`, `tests/test_replay.py`. **Modify:** `src/qkd/effects.py` (two rate owners, S1), `src/qkd/mission.py` (extractor, union-registry partitioning, per-sample receiver flow, `PassResult.link_provenance`), `src/qkd/run.py` (emit provenance + `profile.link_receiver` when present), `src/qkd/schema.py` (exactly two registry entries: `run_metadata → link_provenance`, `profile → link_receiver`). **Untouched:** `bb84.py`, `link.py`, `orbit.py`, `channel.py`, `signals.py`, `twin*.py`, **and every existing test file** — the implementation is bound to the three **new** test files only (consistency edit 5: an implementer who believes an existing test file must change stops and records the ambiguity rather than editing it).

- **Advantage-crossing rule:** linear interpolation between the two bracketing samples; the interpolated crossing is labeled **model-derived**, both neighboring samples retained in the artifact; equality tolerance declared per metric.
- **Planned per-gate test deltas** (planning aid; real counts from runs): Gate A ≈ +15, Gate B ≈ +9, Gate C ≈ +8, Gate D ≈ +6.
- **Precomputed numerical anchor (independent transcription guard; corrected in v2.2):** with `pi = (0.8, 0.15, 0.05)`, `Q_s = 0.1`, `Q_d = 0.05`, `Q_v = 0.001`, `E_s = 0.02`, `p_ap = 0.02`, `f_rep = 1×10⁶`, `τ_d = 1×10⁻⁶` (base gains given directly; the §1.2 gain law is anchored separately):

  ```
  Q_bar     = 0.08755                       (exact)
  Q_bar_reg = 0.08755/0.9817510             = 0.089177398342349536…   (denominator exact)
  a         = 0.02 · Q_bar_reg              = 0.001783547966846990…
  Q'_s      = 0.101605193170162291…         Q'_d = 0.051694370568504641…
  Q'_v      = 0.002781764418880143…         (this value, not p_noise, feeds gains["vacuum"], §1.2)
  T'_s      = 0.002 + 0.5·0.9·a             = 0.002802596585081145…
  E'_s      = 0.027583202173411795…
  R_click   = f_rep · Q_bar_reg             = 89177.398342349536…  s⁻¹   (exact identity, §1.5;
                                              equals f_rep·Σ pi_x·Q'_x to machine precision — tested)
  A         = 1/(1 + R_click·τ_d)           = 0.918124082928941429…
  ```

  The v2.1 value `A ≈ 0.9181237` was **wrong** — computed from a rounded intermediate (`R_click ≈ 89177.85`) rather than the exact chain; both dispatch-gate reviews caught it. Printed values are **truncated, not rounded**; the test target is the independent hand derivation itself, asserted to **≥ 12 significant digits**, plus the union-equals-`Q_bar_reg` identity and the two-form `R_click` identity.

## 13. Execution note

Per the v2.3 confirmation disposition ("approve after one narrow v2.3.1 contract correction"): **this v2.3.1 goes to PI review and Echo's brief textual confirmation of F1/F2 + cleanups; implementation remains unauthorized until both.** On confirmation the plan is approved for sequential Gates A–D per Echo §6; the implementation review then verifies actual behavior, real environment-named test counts, the frozen default-output hash, and replay from the production path. After confirmation: Sonnet implementation through Gates A–D against the 439-green baseline; top-tier review verifies the B1/B3 model tests, the L5 yield identity on a receiver-active run, the replay round-trip, and the byte-identity set before merge. Genuine ambiguities recorded, not resolved by invention.

## Appendix A — Receiver-active result and emission mapping (R1/R6; **total** schema contract, v2.3.1)

**Totality clause (binding):** this appendix is exhaustive in the following precise sense. (i) The table below lists **every** result/emission quantity whose value or semantics differs on a receiver-active run. (ii) Every emitted field **not** listed is byte-identical to the LINK-5 emission and remains governed unchanged by the existing frozen schema and its validators — "not listed" is a frozen-behavior claim, tested by the byte-identity set, not an omission. (iii) The only new emission surfaces are the **exactly two** registry entries of §12 (`run_metadata → link_provenance`, `profile → link_receiver`), whose complete field-level schemas are given below; the dedicated light validators enforce these schemas closed-world (unknown keys rejected). An implementation that touches any field outside this appendix is out of contract.

| Quantity | Source | Semantics on receiver-active runs | Default path |
|---|---|---|---|
| `gains` (Q'_x) | wrapper, §1.3 | **pre-dead-time live-gate** probabilities (diagnostic) | unchanged (= Q_x) |
| error gains T'_x / `qber` E'_x | wrapper, §1.3 | pre-dead-time live-gate; `E'_x ≡ 0` at `Q'_x = 0` | unchanged |
| `y1_lower_bound` (Y1_L'), `q1'` | `estimate_decoy_bounds(gains=Q', qber_per_intensity=E', intensities)`, vacuum slot = `Q'_vacuum` | pre-dead-time live-gate (homogeneity makes delivered variant = A·value; not separately emitted) | unchanged |
| `e1_upper_bound` | same | **invariant under A** (tested identity) | unchanged |
| `sifted_key_length` | wrapper | **delivered expected count** `round(n_pulses · pi_signal · q · A · Q'_signal)` — under the §5 declaration that `n_pulses` counts total protocol pulses (C4; the legacy law `round(n_pulses·q·Q_signal)` is its `pi_signal = 1, A = 1, Q' = Q` special case) | identical value |
| `secure_key_rate` (per BB84Result) | wrapper | delivered per-**signal**-pulse: `A × secure_key_rate(Q'_s, E'_s, q1', e1_U', q, ecc)` | unchanged |
| `profile.secure_key_rate_per_pulse` | mission/profile | **canonical delivered per-protocol-pulse** = pi_signal × A × per-signal rate; **the only yield source (L5)** | identical value (pi=1, A=1) |
| `profile.link_receiver.*` | run emitter | declared extension: per-signal array, pi, availability, units | **absent** |
| `profile.aggregates.secure_key_yield_bits` | existing L5 law | Σ canonical rate × f_rep × dt — valid unmodified | unchanged |
| `decoy_anomaly_score` | wrapper reference path | receiver-aware reference ⇒ honest ≈ 0 (tested tolerance) | unchanged |
| `run_metadata.link_provenance` | run emitter | canonical-JSON string manifest incl. `replayability`, pi, operating pair, controls, PdtConfig timing + order | **absent** |

### A.1 `profile.link_receiver` — field schema (closed-world; validator rejects unknown keys)

| Field | Type | Units / range | Semantics |
|---|---|---|---|
| `secure_key_rate_per_signal_pulse` | array[float], length = profile length | bits/signal-pulse, ≥ 0 | pre-`pi_signal` delivered per-**signal**-pulse rate, `A` applied (diagnostic — never a yield source) |
| `availability` | array[float], length = profile length | dimensionless, (0, 1] | per-sample **`A` in sampled mode; `E_f[A(f)]` in PDT mode** (§1.5/§5 — PDT has no single node-independent `A`; the emitted value is the availability weight the delivered rates were scaled by) |
| `pi.signal`, `pi.decoy`, `pi.vacuum` | float ×3 | dimensionless, each > 0, Σ = 1 ± `PI_SUM_TOLERANCE` | the declared selection probabilities |
| `units` | object of exactly two strings | — | **exact keys and values (C4):** `{"secure_key_rate_per_signal_pulse": "bits/signal-pulse", "availability": "dimensionless"}` — any other key or value rejected |

### A.2 `run_metadata.link_provenance` — manifest key schema (canonical-JSON **string**; §4)

Top-level keys (F2 — every nested object below is closed-world; the validator rejects unknown keys **at every depth** because every depth now has an enumerated vocabulary):

| Key | Type | Required | Value contract |
|---|---|---|---|
| `manifest_version` | int | always | `1` |
| `replayability` | str enum | always | `"replayable"` \| `"configuration_auditable"` |
| `mission_config` | object | always | exactly the ten keys of A.2.1 |
| `production_effects` | array[str] | always | the four production `effect_id`s in parity-pinned order: `["system_efficiency", "atmospheric_absorption", "geometric_loss", "detector_qe"]` — ids only; their params are *derived from `mission_config`* by `simulate_pass` and are not repeated (single ownership) |
| `effects` | array[object] | always (may be empty) | the caller's `link_effects` in order; each entry `{effect_id: str, type_id: str, parameters_complete: bool, params: object}`; registered entries have `params` keys **exactly** the codec's `param_keys` (A.2.2) and `parameters_complete: true`; unregistered entries follow §4 C5 and are permitted only when `replayability == "configuration_auditable"` |
| `link_seed` | int \| null | always | as passed |
| `link_controls` | object str→float | always (may be empty) | keys must be members of the union control registry at replay (§2); values finite |
| `receiver` | object | iff receiver-active | exactly `{pi: {signal, decoy, vacuum}, operating_convention: str}` — `pi` floats > 0 summing to 1 ± `PI_SUM_TOLERANCE`; `operating_convention` enum `["next_live_gate_v1"]`. **The calibrated `(p_ap, dead_time_s)` pair is not recorded here** (F2): those values are effect-owned, may be sample-varying, and live once in the ordered effect specs |
| `mode` | str enum | always | `"sampled"` \| `"pdt"` |
| `pdt_config` | object | iff `mode == "pdt"` | exactly `{fading_coherence_time_s: float, block_duration_s: float, tau_mem_s: float, order: "conditional_then_average"}` |
| `model_ids` | object | always | exactly `{receiver: str \| null, pdt: str \| null}` with vocabularies `receiver ∈ {"qkd_receiver_mean_field_v1"}` (null iff not receiver-active) and `pdt ∈ {"pdt_gauss_hermite_21_v1"}` (null iff `mode == "sampled"`) |
| `pipeline_version` | str | always | new named constant `LINK_PIPELINE_VERSION = "link-6a.1"` in `replay.py` (no such constant exists in the live tree — it is introduced here and bumped by future LINK PRs) |
| `schema_version` | str | always | the live results schema version, currently `"2.0"` (`run.py`; validator-enforced) |
| `serialization` | object | always | exactly `{format: "canonical-json-v1", sort_keys: true, separators: [",", ":"], ensure_ascii: true, float_repr: "python-repr"}` — the rule set under which the manifest string was produced; replay re-serializes under it and requires byte equality |

**A.2.1 `mission_config` vocabulary (mirrors the live `MissionConfig` fields exactly):** `samples` (int > 0); `altitude_km`, `peak_elevation_deg`, `horizon_elevation_deg` (finite floats); `atmosphere` — the **resolved** seven-key object produced by `resolved_atmosphere_config` (`zenith_optical_depth`, `system_efficiency`, `beam_divergence_urad`, `rx_aperture_m`, `intrinsic_qber`, `dark_count_prob`, `werner_p`; all present, all finite — recording the resolved form makes the manifest total and replay idempotent, since re-merging a complete dict onto the defaults is the identity); `detector` — exactly `{detection_efficiency, dark_count_prob, error_correction_efficiency}` (the three `DetectorParams` fields); `intensities` — exactly `{signal, decoy, vacuum}` floats ≥ 0; `n_pulses` (int ≥ 0); `pulse_repetition_rate_hz` (float > 0); `sky_condition` — enum over the live `SKY_BACKGROUND_RATE_HZ` keys `["night", "twilight", "day"]`. Replay reconstructs `MissionConfig(**mission_config)` with `DetectorParams(**detector)`; no "existing config schema" is invoked — this table **is** the schema, and its validator lives in `replay.py`.

**A.2.2 Codec-owned `param_keys` (the closed-world set for each registered `effect_id`'s `params`; `init=True` constructor fields only — `init=False`/derived fields excluded by construction):**

| `effect_id` | `param_keys` |
|---|---|
| `system_efficiency` | `system_efficiency` |
| `atmospheric_absorption` | `zenith_optical_depth` |
| `geometric_loss` | `beam_divergence_urad`, `rx_aperture_m` |
| `detector_qe` | `detection_efficiency` |
| `doppler_shift` | `carrier_frequency_hz` |
| `pointing_loss` | `boresight_offset_urad`, `beam_divergence_urad` |
| `scintillation_fading` | `rytov_variance_zenith`, `aperture_averaging`, `allow_out_of_regime` (bool) |
| `pointing_jitter` | `jitter_sigma_urad`, `beam_divergence_urad` |
| `mu_fluctuation` | `relative_sigma` |
| `detector_afterpulsing` | `afterpulse_prob` |
| `detector_dead_time` | `dead_time_s` |
| `background_light` (new, §6) | `background_rate_hz` |
| `detector_dark_rate` (new, §6) | `dark_count_rate_hz` |

The deep validator consults `EFFECT_CODECS[effect_id].param_keys` for every registered `effects[i].params` — missing or extra keys are named rejections; a test asserts each codec's `param_keys` equals the set of `init=True` fields of its dataclass minus `effect_id`, so the table cannot drift from the code silently. `replay_from_provenance` validates this whole schema closed-world before any reconstruction (unknown keys/types at any depth → named rejection, §4).

### A.3 Exact dataclass additions (C4; cleanup 2 — split into a new required-field type and optional trailing additions)

**A.3.1 — `ReceiverBlockResult` (new, frozen, `detection.py`): all fields required.**

| Dataclass | Field | Type | Semantics |
|---|---|---|---|
| `ReceiverBlockResult` | `gains`, `qber_per_intensity` | `dict[str, float]` | post-afterpulse pre-dead-time `Q'_x`, `E'_x` |
| | `y1_lower_bound`, `e1_upper_bound`, `q1` | `float` | from `estimate_decoy_bounds`/`q1'` on `(Q', E')` — pre-dead-time |
| | `availability` | `float` in (0, 1] | common `A` (sampled) or `E_f[A(f)]` (PDT) — the factor applied to every delivered quantity of this block |
| | `secure_key_rate_per_signal_pulse` | `float ≥ 0` | `A ×` asymptotic per-signal rate |
| | `secure_key_rate_per_pulse` | `float ≥ 0` | `pi_signal ×` the above — the value written to the canonical profile field |
| | `sifted_key_length` | `int ≥ 0` | `round(n_pulses·pi_signal·q·A·Q'_signal)` |
| | `decoy_anomaly_score` | `float` | receiver-aware reference (`0.0` exactly in 6a, §1.2) |
| | `p_noise`, `p_bg`, `p_dk`, `a`, `q_bar_reg`, `r_click_hz` | `float` | diagnostics for the anchor tests (not emitted) |

**A.3.2 — trailing optional additions to existing frozen dataclasses: all default to the legacy value.**

| Dataclass | New field | Type / default | Semantics |
|---|---|---|---|
| `ProfileResult` | `link_receiver` | `LinkReceiverProfile \| None = None` (frozen: `secure_key_rate_per_signal_pulse: list[float]`, `availability: list[float]`, `pi: tuple[float, float, float]`) | `None` on the legacy path |
| `PassResult` | `link_receiver` | same type, `= None` | copied from the profile |
| `PassResult` | `link_provenance` | `str \| None = None` | the canonical-JSON manifest string (§4); `None` ⇒ `run_metadata.link_provenance` absent |

Adding trailing defaulted fields to the frozen dataclasses does not change any existing positional construction; every existing constructor call and emitted default-path field is unchanged (byte-identity set certifies).

### A.4 Provenance leaf map for `profile.link_receiver` (C4 — the live validator recurses into `profile`)

`validate_provenance` treats arrays as single leaves and recurses through nested mappings under the data sections, so a receiver-active emission **must** tag exactly these paths (F1-corrected; tags follow `mission.py`'s live provenance map, where simulation outputs such as `profile.secure_key_rate_per_pulse` are `SIMULATED` and configured inputs such as `mission.intensities.*` and `profile.axis.name` are `ILLUSTRATIVE` — `pi.*` is caller configuration, not a simulation product), and no others:

```
SIMULATED:
  profile.link_receiver.secure_key_rate_per_signal_pulse
  profile.link_receiver.availability
ILLUSTRATIVE:
  profile.link_receiver.pi.signal
  profile.link_receiver.pi.decoy
  profile.link_receiver.pi.vacuum
  profile.link_receiver.units.secure_key_rate_per_signal_pulse
  profile.link_receiver.units.availability
```

Because the generic live validator checks tag validity and coverage but not semantic tag *choice*, this map is enforced by a **project-specific positive assertion** (the receiver-active emission's provenance restricted to `profile.link_receiver.*` equals this exact seven-entry map) plus a **negative test** that deliberately tags a `pi` leaf `SIMULATED` and must fail that assertion.

`run_metadata.link_provenance` needs no tag (`run_metadata` is outside the tagged data sections — confirmed against `provenance.py`'s `DATA_SECTIONS`). The default path emits none of these paths and none of these tags — the "extra tag references non-emitted field" branch of the validator is exercised as a negative test.

### A.5 Validator rejection matrix (C4 — the A.1/A.2 light validators, executable)

| Rejection class | A.1 `profile.link_receiver` | A.2 `run_metadata.link_provenance` |
|---|---|---|
| unknown key (any depth) | ✓ | ✓ |
| missing required key | ✓ (all seven leaves) | ✓ (all required top-level keys; `receiver` iff receiver-active; `pdt_config` iff `mode == "pdt"`) |
| wrong type | ✓ (arrays of float, `pi` floats, `units` strings) | ✓ (per key type above; the top-level value itself must be a `str` per the deep validator) |
| wrong array length | ✓ (≠ profile length) | n/a |
| non-finite value | ✓ (NaN/±inf anywhere) | ✓ (any numeric leaf) |
| range violation | ✓ (`availability` ∉ (0, 1]; rate < 0; `pi_x ≤ 0`) | ✓ (`link_seed` non-int; `manifest_version` ≠ supported) |
| normalization failure | ✓ (`Σ pi ≠ 1 ± PI_SUM_TOLERANCE`) | n/a |
| unit vocabulary | ✓ (exact two keys/values, A.1) | ✓ (`serialization` rule identifiers exact) |
| enum vocabulary | n/a | ✓ (`replayability`, `mode`, `order`) |
| canonical-JSON form | n/a | ✓ (re-serialization of the parsed object must reproduce the string byte-for-byte) |
| unknown `type_id`/`effect_id` on replay | n/a | ✓ (`replay_from_provenance`, §4) |

Every row is one named negative test in `tests/test_link6a.py` (A.1) or `tests/test_replay.py` (A.2).


## 14. Implementation record (2026-08-18)

**Dispatch:** Sonnet subagent, plan v2.3.1 (`8997158…35eebd`), baseline `5b530ca` @ 439 green. Two passes: initial Gates A–D (543 passed), then six top-tier-verification fixes (562 passed). Top-tier verification (Fable 5) ran independently of the subagent's own tests.

**Files.** Created: `src/qkd/detection.py` (812), `src/qkd/replay.py` (644), `src/qkd/benchmark.py` (311), `tests/test_detection.py` (691, 43 tests), `tests/test_link6a.py` (860, 46), `tests/test_replay.py` (484, 34). Modified: `src/qkd/effects.py` (+`BackgroundLightEffect`, `DetectorDarkRateEffect`), `src/qkd/mission.py` (§3.1 signature, union registry, receiver-active + PDT composition, manifest wiring, trailing dataclass fields), `src/qkd/run.py` (conditional emission), `src/qkd/schema.py` (two registry entries + A.1/A.2 validators). **Also modified — flagged for PI:** `tests/fixtures/pr_a_pre_refactor_satellite_output.json` gained two `null`-valued keys (`link_receiver`, `link_provenance`) under `pass_result`, because `tests/test_profile.py::test_simulate_pass_physics_matches_captured_pre_refactor_pass_result` compares `asdict(simulate_pass())` key sets and A.3.2's approved trailing `PassResult` fields necessarily extend that set (values `None`; every emitted default-path field unchanged). No `.py` test file was edited. Untouched: `bb84.py`, `link.py`, `orbit.py`, `channel.py`, `signals.py`, `coherence.py`, `twin*.py`, all existing test modules.

**Certification (cloud, x86_64, numpy 2.4.4, qiskit installed):** `pytest -q` → **562 passed** (439 + 123); `--ignore=tests/test_teleportation_qiskit.py` → **541 passed**. Default emission `python -m qkd.run` → `outputs/results.json` SHA-256 **`3d1544027517197062097234d272ecbfbc03cd1864bbd0ee46169cf1250f1417`** — the eighth consecutive PR with the frozen default emission unchanged (environment-local identity; the in-process parity tests are the portable certificate).

**Independently verified by the top-tier review (outside the subagent's tests):** §12 anchor to 15 digits (`A = 0.918124082928941`, `Q̄_reg = 0.089177398342350`, `R_click = 89177.3983423496`); two-form `R_click` identity (rel 5e-16); default-path emission has no `link_receiver`/`link_provenance` and `run_metadata` keys unchanged; `GateWindowRequiredError` when a rate owner is active without the control; L5 yield identity on a receiver-active run (rel 4.7e-14); canonical rate = `pi_signal × per-signal (A-applied)`; A.4 provenance map exactly the seven entries with the F1 tags; schema validation of a receiver-active payload; sampled and PDT replay round-trips byte-identical in-process; manifest top-level/`mission_config`/`atmosphere` vocabularies match A.2/A.2.1; `receiver` object = `pi` + `operating_convention` only; `ReceiverEveNotSupportedError`; `Q'_vacuum > p_noise` at the estimator boundary with `p_ap > 0`; B3 homogeneity (`Y1_L` scaling rel 3e-16, `e1_U` diff 7e-18); law-last, `pointing_jitter` inadmissible, block-duration mismatch; **exact** identity-receiver parity (`gains ==`, `qber ==`, `rate_per_signal == base rate`, `A == 1.0`) after fix 1; PDT vs sampled ensemble in the small-σ in-regime case: rel diff 3.1e-4 over 60 seeds (SE ≈ 7e-4) — and, as expected from the declared conditional-then-average order, ~1.4% divergence at rytov 0.05 out-of-regime (`R(E_w[Q'])` vs `E_f[R(Q'(f))]`), which is the order, not a defect.

**Verification-driven fixes (subagent pass 2):** (1) exact identity short-circuits — `p_noise = y0` when both rates are zero, `Q'/T'/E'` pass-through when `a == 0`, `A = 1.0` when `dead_time_s == 0` — the subagent's first pass had `1−(1−y0)` rounding (`1.0000000000287557e-06` for `y0 = 1e-6`) and its "exact" tests were softened to `approx(abs=1e-12)`; both tests are now strict `==`; (2) missing `SeedRequiredError` trap test added (misclassified admitted effect with `effect_id="pointing_loss"` requesting RNG in a PDT prefix); (3) missing PDT-vs-sampled ensemble consistency test added (40 seeds, rel 6.9e-4 < 2e-3, docstring carries the order caveat); (4) `PdtSampleVaryingMemoryError` — dead-time/afterpulse invariance across samples asserted before the once-evaluated memory guard (closes the subagent's ambiguity about reading `dead_time_s` from sample 0); (5) boundary tests: saturated `p_noise = 1` equality, all-zero channel `E' ≡ 0`, `p_ap → 1⁻`; (6) A.5 matrix completed (missing key / wrong type / non-finite / normalization for A.1; non-int seed, unsupported `manifest_version`, non-finite leaf, three enum vocabularies for A.2).

**Recorded ambiguities (subagent, accepted by the review):** `ReceiverModel.controls(pulse_repetition_rate_hz)` takes the period explicitly (the `link.py` `Controllable` protocol is zero-argument; the receiver bound is model-coupled to `f_rep`, so mission assembles the union registry by direct call — `link.py` untouched, as required); PDT-mode `ReceiverBlockResult` diagnostics (`p_noise, p_bg, p_dk, a, q_bar_reg, r_click_hz`, not emitted) are node-probability-weighted averages; `benchmark.py` is contract-complete (artifact schema, validator, calibrated-pair sweep refusal, model-derived crossing with both neighbours) but ships no sweep driver writing to `outputs/` — a driver is a follow-up when the first advantage claim is actually made (QCC mapping memo).

**Local certification (PI, Mac arm64 / numpy 2.4.6):** expected `python -m pytest -q` → **562 passed** with qiskit installed, or **541 passed, 1 skipped** without qiskit (the skip is `tests/test_teleportation_qiskit.py`); `git status` must show exactly the twelve files listed above (4 modified src, 3 new src, 3 new tests, 1 fixture, this plan) plus the four Echo review files if not yet committed. Do not compare `outputs/results.json` bytes across machines (ULP drift) — the frozen-hash test is the in-process oracle.
