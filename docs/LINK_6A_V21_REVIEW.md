# LINK-6a v2.1 Confirmation Review — Targeted v2.2 Required

- **Disposition:** Hold dispatch for a targeted v2.2 revision; the receiver core remains approved
- **Review date:** 2026-08-17
- **Plan reviewed:** `docs/LINK_6A_PLAN.md`, status v2.1 dated 2026-08-17
- **Plan SHA-256:** `13fe35700066b96e960c0db6b22dae8a2313bacdda1035e5d1c0ab418ab703e7`
- **Prior review:** `docs/LINK_6A_V2_REVIEW.md`, SHA-256 `cdb3e926decc0396458c7033091958641e49a51e8d858cb16ad897ff8262b612`
- **Chat Claude feedback reviewed:** attachment SHA-256 `a38a34a4618ef2efde612cb72356dbe67e34573759cd11f8d15c7666e611dd2d`
- **Repository baseline:** `5b530ca`
- **Scope:** review/documentation only; no plan or source file was modified

## 1. Executive outcome

V2.1 is a strong revision. It closes the central v2 review findings around the
canonical rate field, common dead-time availability, control partitioning,
physical PDT support, result ownership, and per-run replayability. The shared
detector-history receiver equations remain approved and do not need another
redesign.

Chat Claude found a real numerical error: the precomputed availability anchor
does not follow from the plan's own equations. That must be corrected before
dispatch. Its suggested documentation improvements are also mostly sound.

The independent re-review found two additional dispatch blockers:

1. the selected PDT block duration is not yet tied to the duration over which
   the configured pulses are actually acquired; and
2. the plan still lacks executable definitions for parts of the activation,
   schema/provenance, and stochastic-effect contracts that it calls complete.

These are targeted contract corrections, not a rejection of the receiver
physics. After the items in section 2 are resolved on paper, implementation can
proceed through Gates A–D without another broad architecture review.

## 2. Required v2.2 corrections

### D1 — Correct and strengthen the numerical anchor

**Severity: Dispatch blocker. Chat Claude finding confirmed.**

Plan line 173 gives `A ≈ 0.9181237`. Direct high-precision evaluation of the
frozen equations gives:

```text
Q_bar          = 0.08755
denominator    = 0.9817510
Q_bar_reg      = 0.08917739834234953669514978849015687277...
a              = 0.00178354796684699073390299576980313746...
Q'_signal      = 0.10160519317016229166051269619282282371...
T'_signal      = 0.00280259658508114583025634809641141185...
R_click        = 89177.39834234953669514978849015687277... s^-1
A              = 0.91812408292894142996219025325890464892...
```

The plan's `A` is therefore wrong, not merely displayed at low precision. It
also promises verification to at least ten digits while printing most expected
values to only six or seven.

Required correction:

- replace the incorrect availability;
- publish every asserted anchor to at least 12 significant digits;
- hard-code those independently calculated values in the test rather than
  recomputing expected values with the production formulas; and
- retain the independent identity
  `sum(pi_x * Q'_x) == Q_bar_reg`, hence
  `R_click == f_rep * Q_bar_reg`.

### D2 — Resolve PDT acquisition duration, pulse scheduling, and memory scale

**Severity: Dispatch blocker. Chat Claude's claim that this is resolved is not
accepted.**

Plan line 117 defines the PDT block as the profile-bin width and requires only:

```text
n_pulses <= f_rep * block_duration_s
```

On the current defaults:

```text
profile sample spacing        = 0.476955506437172 s
n_pulses / f_rep              = 0.010000000000000 s
profile-bin intervals at 3 ms = 158.985...
pulse-train intervals at 3 ms = 3.333...
```

The inequality proves only that the pulses could fit inside the bin. It does
not prove that the configured 1,000,000 pulses sample the whole 0.477-second
bin. A contiguous 100 MHz pulse train lasts 0.01 seconds, so the stated
`block >= 50 * tau_c` guard would pass using the bin width while the actual
pulse acquisition samples only about three coherence intervals.

V2.2 must choose one physical contract:

- **Continuous-bin acquisition:** pulses span the complete profile bin. Then
  the modeled pulse count is approximately `f_rep * block_duration_s`
  (47,695,550.6 pulses on the default bin), and the role of the legacy
  `n_pulses = 1,000,000` must be removed from or relabeled within receiver/PDT
  count semantics.
- **Contiguous configured block:** acquisition duration is
  `n_pulses / f_rep`. Then the default 0.01-second block fails the 50-coherence-
  interval guard at `tau_c = 3 ms`, and an opt-in PDT caller must provide a
  larger block/pulse count.
- **Explicit duty-cycle schedule:** record and validate a pulse schedule or
  duty factor, use its actual acquisition span in the guard, and use the
  corresponding average/live gate rate in detector loading.

Do not retain the current inequality as evidence of stationary-PDT admission.
Also define the last profile sample's block width and the behavior for
non-temporal profiles.

The detector-memory guard needs one more boundary correction. Because `p_ap`
is the probability in the **next live gate**, the memory timescale does not
vanish when `dead_time_s = 0`; it still includes at least one gate period.
Define and guard an effective memory scale that includes `1 / f_rep` (the plan
should choose the exact `max`/hold-off convention) rather than using
`dead_time_s` alone.

### D3 — Freeze the actual noise-to-estimator plumbing

**Severity: Dispatch blocker. Chat Claude's direction is correct but
incomplete.**

The live `bb84.py` establishes two distinct stages:

1. `_honest_gain(mu, eta, y0)` uses
   `Q_mu = 1 - (1 - y0) * exp(-eta * mu)`, with
   `DetectorParams.dark_count_prob` as the base `y0`;
2. `estimate_decoy_bounds(...)` has no independent `y0` parameter. It reads
   its estimator vacuum yield from `gains["vacuum"]`.

Accordingly, the complete untouched-`bb84.py` route must be:

```text
base detector copy: dark_count_prob = p_noise
base statistics:    Q_x, T_x from the existing honest gain/error law
receiver transform: Q'_x, T'_x from the shared afterpulse equations
decoy estimator:    gains = Q'_x, qber = T'_x / Q'_x
estimator y0:       Q'_vacuum = 1 - (1 - p_noise)(1 - a)
```

The estimator must not receive untransformed `p_noise` as a separate vacuum
yield after the afterpulse transform; no such argument exists, and doing so
would break the single-code-path and common-scaling claims. Amend sections
1.2/1.5 and Appendix A to state this two-stage substitution explicitly.

Add a hand-calculated test proving both:

- zero rate effects give base `p_noise == detector.dark_count_prob`; and
- afterpulsing gives `gains["vacuum"] == Q'_vacuum`, which is the exact value
  consumed as `y0` by the unchanged estimator.

### D4 — Define the opt-in public API and pulse-count semantics

**Severity: Dispatch blocker.**

The plan defines `ReceiverModel`, `PdtConfig`, explicit `pi`, and
`gate_window_s`, but it does not define how a caller activates them through
`simulate_pass(...)` or `simulate_profile(...)`. The current mission API has
only `link_effects`, `link_seed`, and `link_controls` as LINK inputs.

Before dispatch, freeze:

- the exact new optional arguments or `MissionConfig` fields;
- the sampled-vs-PDT mode selector;
- where `ReceiverModel` and `PdtConfig` are supplied;
- whether receiver activation requires all of `pi`, `gate_window_s`, and the
  calibrated detector pair;
- what happens when `gate_window_s` is absent on a receiver-active run; and
- whether `n_pulses` means total protocol pulses, signal pulses, or a legacy
  expected-count block.

The safest gate-window rule is explicit-required-on-activation: receiver-active
runs without `link_controls["gate_window_s"]` raise a named error. A silent
default would make rate effects depend on an unstated acquisition setting.

For total protocol pulses, delivered sifted count must be rounded only after
applying the protocol-selection and availability factors:

```text
round(n_protocol_pulses * pi_signal * q * A * Q'_signal)
```

If the project intentionally retains signal-block count semantics instead,
that choice and its separation from profile/yield pulse semantics must be
explicit in `ReceiverBlockResult`.

### D5 — Make Appendix A genuinely total for schema and provenance

**Severity: Dispatch blocker. Prior R1/R6 only partially closed.**

Plan lines 25–26 call Appendix A a complete type/range/provenance mapping, but
the appendix does not provide types, ranges, exact dataclass fields, or
provenance tags. It also lists `gains`, `qber`, `Y1_L`, and `q1` without saying
whether they exist only in `ReceiverBlockResult` or are carried into
`ProfileResult`/`PassResult`.

Freeze the exact shape of `profile.link_receiver`, including exact unit
strings. For every leaf, specify:

- JSON type and Python owner;
- array length relationship to `profile.axis.values`;
- finite/range rules (`availability` in `[0,1]`, positive normalized `pi`,
  nonnegative rates);
- whether it is emitted, internal-only, or diagnostic; and
- the exact provenance tag/path.

This is required by the live provenance validator: nested mappings recurse,
while arrays are single leaves. A likely subtree therefore needs separate tags
for paths such as:

```text
profile.link_receiver.secure_key_rate_per_signal_pulse
profile.link_receiver.availability
profile.link_receiver.pi.signal
profile.link_receiver.pi.decoy
profile.link_receiver.pi.vacuum
profile.link_receiver.units.<each-unit-leaf>
```

`run_metadata.link_provenance` correctly needs no provenance leaf because
`run_metadata` is outside the validator's data sections. State that explicitly
to prevent an implementer from weakening `validate_provenance`.

The dedicated extension validator must be called by the production deep-schema
path and must reject missing, unknown, wrong-length, nonfinite, and out-of-range
receiver fields. Merely registering the subtree name is insufficient.

### D6 — Make PDT stochastic admissibility executable

**Severity: Dispatch blocker.**

Plan line 115 requires PDT to reject every additional stochastic effect. The
live `ChannelEffect` protocol has no stochastic/deterministic marker, and a
custom effect may request `context.rng_for(...)` without exposing
`stationary_law`. The mission therefore cannot reliably enforce the stated
rule by introspection.

The lowest-risk initial contract is allowlist-based:

- PDT accepts one registered built-in law-capable effect (initially the
  scintillation effect);
- every other active effect must be registered and declared deterministic;
- unregistered custom effects are rejected in PDT mode, even though they may
  remain configuration-auditable in sampled mode; and
- PDT constructs/evaluates the deterministic stack without drawing the law
  effect, then applies its relative factor at each quadrature node.

Record this classification in the effect registry and replay manifest. Add a
test with a custom RNG-using effect lacking `stationary_law`; it must not pass
PDT admission merely because the runtime cannot see its RNG call in advance.

### D7 — Define the configuration-auditable custom-effect payload

**Severity: Medium contract correction.**

Plan line 111 says an unregistered custom effect's type name and “declared
parameters” are recorded descriptively. The current `ChannelEffect` protocol
has no declared-parameters method, and the plan correctly forbids generic
`dataclasses.asdict` serialization.

Choose one honest rule:

- require an explicit audit-spec protocol for configuration-auditable custom
  effects; or
- record only stable type/effect IDs plus an explicit
  `parameters_complete: false` marker when no audit spec exists.

Do not claim complete configuration auditability for parameters that the
runtime has no contract for reading.

## 3. Required low-cost corrections

These should be folded into the same v2.2 edit:

1. **Name the `pi` normalization tolerance.** Plan line 19 still says “within
   tolerance” without a constant or comparison rule.
2. **Declare the afterpulse-error limitation.** `e0 = 1/2` is coherent for the
   aggregate single-detector-equivalent model, but real detector afterpulses
   can carry temporal/detector correlations. State that per-detector memory,
   detector assignment, double-click policy, and security treatment of those
   correlations are outside LINK-6a.
3. **Add the exact click-rate identity.** State and test
   `R_click = f_rep * Q_bar_reg`; it is a useful independent invariant.
4. **Add the convex-mixture justification with its assumptions.** Under fixed
   intensity-selection probabilities and one intensity-independent common
   availability `A(f)`, the normalized weights
   `A(f)p(f) / E[A]` form one shared probability measure. The decoy
   mixture-channel structure is therefore preserved. State that the argument
   fails if availability or fading selection is intensity-dependent.
5. **Remove stale “bounded law” wording.** Lines 113, 124, and 138 still call
   the treatment a bounded/shared-bounded law, contradicting line 116's
   accurate “unbounded log-normal with validity guard” description.
6. **Fix section references.** The v2.1 changelog mentions clarifications in
   “§12–§13”, but the document has no §13 and the numerical anchor is under
   §11.

## 4. Adjudication of Chat Claude's feedback

| Feedback item | Disposition | Independent finding |
|---|---|---|
| Availability anchor is wrong | **Confirmed** | Correct value is `0.918124082928941...`; all anchor values need enough printed precision for the promised test. |
| `p_noise` enters through `DetectorParams.dark_count_prob` | **Confirmed with refinement** | Correct for base statistics; after afterpulsing, the unchanged estimator reads `Q'_vacuum`, not raw `p_noise`, from `gains["vacuum"]`. |
| `e0 = 1/2` needs a correlation caveat | **Confirmed** | Keep the aggregate approximation but declare the excluded per-detector temporal correlation/security model. |
| Add `R_click = f_rep * Q_bar_reg` | **Confirmed** | Follows exactly from the union identity and should be an acceptance invariant. |
| Decide missing `gate_window_s` behavior | **Confirmed** | Explicit-required-on-receiver-activation is recommended. |
| Name the `pi` sum tolerance | **Confirmed** | Needed for reproducible validation. |
| Add convex-mixture justification | **Confirmed with assumptions** | Valid only with one intensity-independent common weighting measure and intensity choices independent of fading. |
| PDT timescale question is resolved | **Not confirmed** | Profile-bin duration and actual pulse-acquisition duration still diverge by about 47.7x on defaults. |
| Baseline “418 passed, 1 skipped without qiskit” | **Not reproduced** | The explicit no-Qiskit-file run produced `418 passed`, with no skip. The plan's `439/418` statement is correct. |
| Approve for dispatch after anchor-only correction | **Not accepted** | D2–D6 must also be frozen before implementation to avoid invented contracts and false PDT admission. |

## 5. Prior-gate status

| Prior v2.1 target | Status after confirmation review |
|---|---|
| R1 canonical output/yield contract | **Mostly closed**; canonical rate is correct, but exact extension schema/provenance remains incomplete (D5). |
| R2 PDT support/tail rule | **Closed**, apart from stale “bounded law” wording. |
| R3 slow-fading applicability | **Partially closed**; ratio guards exist, but acquisition duration and zero-dead-time memory semantics are not physical yet (D2). |
| R4 control partitioning/bounds | **Mostly closed**; missing receiver-active gate-window behavior remains (D4). |
| R5 edge domains | **Closed**; add a named `pi` normalization tolerance. |
| R6 total result mapping/anomaly | **Partially closed**; anomaly path is sound, but pulse-count and total dataclass/schema mapping remain incomplete (D4/D5). |
| R7 replay policy | **Mostly closed**; custom parameter auditability still lacks an interface (D7). |

## 6. Accepted core decisions

The following decisions remain approved and should not be reopened in v2.2:

- one aggregate detector history across interleaved intensities;
- the shared next-live-gate mean-field afterpulse equations;
- explicit strictly positive intensity-selection probabilities;
- one calibrated `(p_ap, dead_time_s)` operating pair;
- one common non-paralyzable availability factor;
- pre-dead-time/live-gate decoy estimation and one common delivered-rate
  multiplier;
- `profile.secure_key_rate_per_pulse` as the canonical delivered
  per-protocol-pulse rate;
- unchanged `bb84.py` estimator and secure-key-rate functions;
- aggregate gate-occupancy noise mapping, with detector efficiency applied
  once;
- receiver-aware honest anomaly reference;
- estimator-owned declared gate-window control;
- canonical string-valued replay manifest and built-in codec registry;
- no clipping of unphysical PDT transmittance;
- conditional receiver evaluation followed by availability-weighted averaging,
  once D2's acquisition contract is satisfied; and
- sequential implementation Gates A–D with the frozen default output retained.

## 7. Dispatch confirmation gate

V2.2 is ready for implementation authorization when the plan answers these
questions without leaving choices to the implementer:

1. Are all numerical anchor values corrected and printed to testable precision?
2. What time interval do the modeled pulses actually occupy, and what pulse
   schedule makes the PDT stationarity guard true?
3. Does the post-afterpulse estimator consume `Q'_vacuum` as its unchanged
   `gains["vacuum"]` yield?
4. What exact public API activates receiver and PDT modes, and what does
   `n_pulses` count?
5. What is the exact `profile.link_receiver` schema, validator, dataclass, and
   provenance-leaf map?
6. How does PDT prove every non-law effect is deterministic, and how is the law
   effect excluded from sampled stack evaluation?
7. What can a configuration-auditable custom effect honestly serialize?

Once those seven answers are incorporated, the appropriate disposition is
**approved for dispatch through Gates A–D**. No new broad review of the shared
receiver equations is required.

## 8. Validation evidence

The unchanged baseline was rerun during this review:

```text
qkd_env/bin/python -m pytest -q
439 passed in 62.48s

qkd_env/bin/python -m pytest -q --ignore=tests/test_teleportation_qiskit.py
418 passed in 48.66s
```

The arithmetic anchor was evaluated independently at 50-digit decimal
precision. No implementation files or plan text were changed.

## 9. Physics references checked

- Carlos Wiechers et al., “Dead-time optimization to increase secure distance
  range in prepare and measure quantum key distribution protocols,”
  [arXiv:2303.13742](https://arxiv.org/abs/2303.13742) — supports treating
  afterpulse probability and dead time as a coupled operating choice.
- Shuang Wang et al., “Realistic detector model for a time-bin-encoding quantum
  key distribution system,” *Physical Review Applied* 23, 054071 (2025),
  [doi:10.1103/PhysRevApplied.23.054071](https://doi.org/10.1103/PhysRevApplied.23.054071)
  — supports explicitly limiting the aggregate model where detector
  dead-time/afterpulse memory creates temporal correlations.
