# LINK-6a Plan Review — Second Independent Pass

- **Disposition:** Major revision required before implementation
- **Review date:** 2026-08-17
- **Review pass:** Fresh re-review requested after the initial review
- **Draft reviewed:** `/Users/lana/Downloads/LINK_6A_PLAN.md`, dated 2026-08-14
- **Draft SHA-256:** `e8ef06f35e6756ed9dc7546fd500ca9a69b98a7d65e8647ab7bd1f41561eab51`
- **Repository baseline:** local `Quantum-QKD-Aero` at `5b530ca`; 439 tests passed with the Qiskit extra and 418 passed with the Qiskit-specific file excluded
- **Change scope:** documentation only; no plan, physics, source, schema, or tests modified

## 1. Verdict

The plan has a strong overall direction, but it should not be implemented in
its current form. It combines four difficult contracts — detector memory,
decoy-estimator integration, turbulent-PDT integration, and replay-grade
provenance — and several of their interactions are not yet defined.

The most consequential problem is deeper than the first review stated. The
proposed afterpulse formulas model each signal intensity as if it had its own
detector history. In the actual protocol, randomly interleaved signal, decoy,
and vacuum pulses share one receiver. A click caused by a signal pulse can
produce an afterpulse during a later decoy or vacuum gate. Therefore the
afterpulse contribution is driven by the aggregate registered-click process,
not by the current intensity's gain alone.

The plan also treats dead time as a per-intensity final throughput correction.
That is only defensible under a declared common-availability mean-field model.
Under that model, multiplying the final asymptotic key rate by one common
availability is algebraically equivalent to scaling every observed gain,
including the vacuum gain, by the same availability. The draft instead defines
a different availability from each `Q'_x`, which loses that equivalence and can
distort the decoy bounds.

Recommended disposition: **revise, then re-review the mathematics and data
flow before authorizing implementation**. The architecture is salvageable
without changing the verified `bb84.py` estimator, but the wrapper contract
must be made considerably more precise.

## 2. Corrections to the first review

This pass preserves the first review's five main findings and strengthens
three of them:

1. **Gate-window deferral is now a blocker, not an acceptable convenience.**
   Ratified ADR-0003 explicitly classifies coincidence window `Delta t` as a
   control and requires estimators that own controls to expose that ownership.
   LINK-6a is already landing control/provenance machinery. Introducing the
   same quantity first as fixed configuration creates an avoidable ownership
   migration and conflicts with the ratified contract.
2. **The detector-memory problem is not solved by one shared dead-time rate
   alone.** Afterpulse probability itself must be driven by the shared prior
   click process; `Q_x/(1-p_ap)` for each intensity is not the interleaved
   protocol model.
3. **PDT bounding is not the only missing PDT rule.** The plan must also define
   which stochastic-effect stacks PDT mode supports and whether receiver memory
   is applied before or after averaging over fast fading.

## 3. Blocking findings

### B1 — The afterpulse model uses the wrong conditioning process

Draft lines 66–71 define:

```text
Q'_x = Q_x / (1 - p_ap)
```

separately for each intensity. This makes the afterpulse burden of a decoy gate
depend on the decoy gain and leaves the vacuum gain almost unchanged. In an
interleaved protocol, an afterpulse in the current gate is caused by a previous
registered avalanche, which may have originated from any intensity.

The revised plan needs explicit intensity-selection probabilities `pi_x` and
one shared detector-history approximation. One bounded candidate mean-field
model, offered for review rather than mandated here, is:

```text
Q_bar      = sum_x(pi_x * Q_x)
Q_reg_bar  = Q_bar / (1 - p_ap * (1 - Q_bar))
a          = p_ap * Q_reg_bar
Q'_x       = 1 - (1 - Q_x) * (1 - a)
T'_x       = T_x + 0.5 * (1 - Q_x) * a
E'_x       = T'_x / Q'_x
```

where `T_x = E_x Q_x` is the base error gain. This declares one-step,
next-live-gate afterpulsing, permits cascades through `Q_reg_bar`, treats the
afterpulse-only event as random, handles event collisions by probability union,
and remains bounded. It also recovers the familiar `1/(1-p_ap)` aggregate
factor only in the low-occupancy limit.

The final model may differ, but it must satisfy all of these structural rules:

- one history is shared across signal, decoy, and vacuum settings;
- intensity selection is explicit and independently random under the declared
  asymptotic approximation;
- afterpulse events may cross intensity classes;
- gains remain in `[0, 1]` without silent clipping; and
- error gains, not just QBER ratios, are propagated through the model.

The phrase "exact for the memoryless kernel" should be removed unless an exact
discrete gated process is actually derived. The geometric cascade is the
expected total progeny of an unsaturated branching approximation; it is not an
exact Bernoulli-gate detector law once collisions and dead time are present.

### B2 — Afterpulsing and dead time are not independent post-processors

Draft lines 72–74 apply an unlimited afterpulse cascade and then a
non-paralyzable availability. In a gated APD, dead time suppresses gates in
which afterpulses could occur, and the measured conditional afterpulse
probability depends on hold-off/dead-time convention. The current LINK-5
parameter contract already warned that `afterpulse_prob` is calibrated under a
declared operating convention.

The revised plan must choose one of two honest contracts:

1. **Effective post-holdoff parameter:** `p_ap` is the calibrated probability
   of an afterpulse in the next *live* gate after the configured holdoff. The
   model may then operate in live-gate time, but `p_ap` and `dead_time_s` form a
   calibrated pair and may not be swept independently without a calibration
   law.
2. **Joint time-kernel model:** afterpulse probability is a function of elapsed
   time after an avalanche, and dead time explicitly removes the affected
   gates. This is more physical but materially larger than the proposed v1.

If option 1 is selected, provenance and benchmark configuration must identify
the operating convention. The model must not imply that changing dead time
leaves `p_ap` physically unchanged.

The dead-time law itself also needs accurate labeling. `m = n/(1+n tau_d)` is
the classical non-paralyzable stationary-rate relation for an assumed arrival
process. For a periodic gated detector, it is a continuous mean-field
approximation unless the plan derives an equivalent skipped-gate renewal
model. The draft should not present it as an exact gated law.

### B3 — One common availability is required for the decoy-bound equivalence

The draft defines `R_click = Q'_x f_rep`, producing a different availability
for each intensity. That changes signal, decoy, and vacuum gains by different
factors and therefore changes the inferred `Y1` and `e1` in a way that does not
follow from one shared detector.

The first-order alternative is one shared candidate click rate:

```text
R_click = f_rep * sum_x(pi_x * Q'_x)
A       = 1 / (1 + R_click * tau_d)
```

The revised plan must then state whether it:

- supplies `A Q'_x` and unchanged `E'_x` to the existing decoy estimator; or
- computes the estimator from pre-dead-time statistics and multiplies all
  delivered quantities by `A`.

For the current asymptotic estimator, these routes are algebraically equivalent
only when the same `A` applies to every intensity and to the vacuum yield:

```text
Y1_L(A Q) = A Y1_L(Q)
e1_U(A Q, A Y0) = e1_U(Q, Y0)
R(A Q) = A R(Q)
```

That equivalence should be an explicit test. It does not hold for the draft's
per-intensity `A_x` values.

The plan must also say how availability affects `sifted_key_length`,
`secure_key_rate`, and integrated key yield. A throughput effect cannot update
only one of those representations.

### B4 — Intensity-selection probabilities expose a pre-existing rate-unit gap

The shared detector rate cannot be calculated without probabilities for
choosing signal, decoy, and vacuum pulses. The repository currently stores only
their mean photon numbers. It has no `pi_signal`, `pi_decoy`, or `pi_vacuum`.

This matters beyond detector occupancy. The current asymptotic formula is
naturally interpreted per signal pulse, while `profile.secure_key_rate_per_pulse`
is integrated against the total pulse repetition rate. Once selection
probabilities exist, the plan must decide whether the emitted rate is:

- bits per emitted **signal** pulse; or
- bits per emitted **total protocol** pulse, which includes a factor such as
  `pi_signal`.

The decision must be reflected consistently in naming, key-yield integration,
benchmark curves, and replay provenance. Default-path byte identity may require
keeping the legacy metric unchanged while introducing an opt-in receiver metric
with explicit units. The plan may not quietly hardcode equal selection or use
`pi_signal = 1`, because either choice changes the physical detector load or
misrepresents a decoy protocol.

### B5 — The noise mapping needs an ownership and detector-cardinality contract

Draft lines 50–56 combine `DetectorParams.dark_count_prob`,
`background_rate_hz`, and `dark_count_rate_hz` as independent noise sources.
The repository currently declares `DetectorParams.dark_count_prob` authoritative
for the BB84 detection window. A nonzero `dark_count_rate_hz` may represent the
same detector dark noise in rate form, in which case the proposed equation
double counts it.

The revised plan must define:

- whether rate observables are absolute physical rates or increments relative
  to the legacy `dark_count_prob`;
- whether each rate is incident at the receiver, incident at a detector,
  registered after detector efficiency, or already aggregated across the
  receiver;
- whether `dark_count_prob` is per detector or the aggregate vacuum yield
  `Y0` used by the estimator;
- the modeled detector cardinality and double-click policy; and
- exactly where detector efficiency is applied, once.

The equation

```text
p_noise = 1 - (1-y0) exp(-(R_bg + R_dark) Delta t)
```

is exact only for the declared aggregate Poisson/independence model. If rates
are per detector, the no-click probabilities must be combined across detectors.

The claimed reuse of `coherence.py`'s accidentals convention should be removed.
`B = R_bg R_local Delta t` is a coincidence-rate model; `1-exp(-R Delta t)` is
a probability of at least one event in a gate. They share a time window but are
not the same physical mapping.

### B6 — The gate window must enter through the ratified control surface

ADR-0003 §3.6 explicitly names coincidence window `Delta t` as a control and
states that estimators owning tunable parameters implement `Controllable`.
Draft §3.3 instead temporarily classifies it as fixed physical configuration.

The revised plan should introduce `gate_window_s` as a declared, run-level
control now. It can remain constant during a run and need not be optimized in
LINK-6a. That preserves the ratified ownership model without expanding into
adaptive control policy.

At minimum, its control contract needs:

- SI units and strict finite positive bounds;
- a non-overlap or operating-mode rule relative to `f_rep`;
- future feasibility coupling to `timing_jitter_s` without changing the field's
  identity or meaning;
- inclusion in the existing audit/replay record; and
- rejection when supplied through an undeclared path.

If the project deliberately wants to defer control ownership, that requires an
ADR-level exception or amendment, not only a sentence in a PR plan.

### B7 — The estimator-consumption seam and result plumbing are incomplete

The live `apply_link_state(...)` rejects non-identity background, dark-count,
afterpulse, and dead-time observables before `simulate_profile(...)` calls the
estimator. The plan says a wrapper transforms estimator inputs and outputs but
does not specify how the per-sample `EffectiveLinkState` reaches that wrapper.

The approved flow should be total and single-owned:

```text
ChannelStack.evaluate(t)
        |
        v
EffectiveLinkState
        |
        +-- approved LINK-6a consumer extracts exactly:
        |     background_rate_hz
        |     dark_count_rate_hz
        |     afterpulse_prob
        |     dead_time_s
        |
        +-- residual state goes through apply_link_state(...)
        |     and still rejects every unconsumed non-identity field
        |
        v
receiver wrapper -> existing estimate_decoy_bounds / secure_key_rate
```

The mission path currently collapses detector output to one `DetectorParams`
for the whole pass. LINK-6a needs a per-sample receiver-input record or an
equivalent list of consumed states. The plan should name its type and owner.

The plan also says `run.py` emits provenance but does not define how `run.py`
receives it. The production result must carry an optional replay/provenance
record from the same simulation that generated the profile. `run.py` must not
reconstruct or re-evaluate stack state separately.

No field may be considered consumed merely because the bridge skipped its
rejection. The consumer should return or declare the exact consumed-field set,
and the residual bridge should fail on everything else, including
`intensity_factor`, frequency offset, jitter, and misalignment.

### B8 — PDT needs support, stack-admissibility, and timescale rules

The current scintillation law is an unbounded log-normal relative factor, while
a physical total-transmittance PDT has support in `[0,1]`. Multiplying a base
transmittance by a quadrature factor can exceed one. The plan must select one
declared physical treatment shared by sampled and PDT modes; silent clipping is
not acceptable.

The plan must also define which stacks PDT mode supports. The repository can
contain more than one stochastic effect. `PointingJitterEffect` is stochastic
but does not expose `stationary_law(...)`; a stack can also contain a
scintillation law plus other random effects. Consequently, the statement that
PDT mode is deterministic and seed-independent is true only for an explicitly
restricted stack.

The revised contract should do one of the following:

- accept exactly one distribution-capable stochastic effect and reject every
  other stochastic effect in PDT mode;
- define and integrate a joint distribution for all active stochastic effects;
  or
- declare a mixed sampled/quadrature mode, including its seed semantics.

Finally, the interaction between PDT and detector memory needs a timescale
decision. Dead-time availability is nonlinear in click rate, so in general:

```text
E[A(Q(f)) Q(f)] != A(E[Q(f)]) E[Q(f)]
```

If fading is fast relative to the detector-memory scale, average gain and error
gain over the PDT first, then apply the shared detector-memory approximation.
If fading is slow, apply receiver response conditionally and average afterward.
The plan must select and justify one order. The current separate §4 and §5
descriptions leave this expensive interaction undefined.

### B9 — `link_provenance` needs a typed schema and a real replay protocol

Adding `link_provenance` to
`DECLARED_SCHEMA_EXTENSIONS["run_metadata"]` does not make a mapping valid. The
deep validator currently requires every `run_metadata` value to be a string.
The extension registry controls vocabulary, not nested type semantics.

The plan should define a structured, versioned replay manifest and a dedicated
validator. At minimum it needs:

- manifest format/version;
- complete mission/profile configuration;
- ordered effect specifications with stable type identifiers;
- explicit allowlisted constructor parameters;
- link seed and declared controls;
- intensity-selection probabilities and receiver/detection configuration;
- sampled/PDT mode and model identifiers;
- schema/emitter or pipeline version;
- canonical serialization rules; and
- a production replay entry point that rejects unknown effect types and fields.

`dataclasses.asdict(...)` is not a sufficient serialization protocol. The
`ChannelEffect` protocol does not require dataclasses, and current dataclasses
contain `init=False` and derived fields that cannot be passed back into their
constructors. Replay should use a built-in effect registry plus explicit
`to_spec`/`from_spec` behavior, or an equivalently narrow allowlist.

The byte-identity test must run through the real production simulation and
emission path. If complete replay is intentionally deferred, rename the 6a
promise to **configuration-auditable** and do not claim self-replayability yet.

## 4. Significant scope and labeling findings

### S1 — No built-in effect currently produces either rate observable

The live effect library has owners for detector efficiency, afterpulsing, and
dead time, but no built-in `ChannelEffect` for `background_rate_hz` or
`dark_count_rate_hz`. LINK-6a can prove consumption with test effects, but a
user cannot activate the feature through the project library as currently
planned.

The plan should state whether custom effects are intentionally the only 6a rate
producers. If built-in parameter-owner effects are required, `effects.py` must
be added to scope and reviewed explicitly rather than discovered during
implementation.

### S2 — The benchmark comparison must be physically meaningful

An ideal receiver will normally dominate the same receiver with afterpulsing,
dead time, and added noise, so "ideal versus full receiver" is not an advantage
demonstration. Benchmark pairs should be named realizable or clearly declared
counterfactual configurations, with metric direction and equality tolerance
defined.

If the advantage is expected from a tighter gate, reduced afterpulsing, or a
different detector, the changed configuration and all coupled costs —
efficiency, jitter acceptance, or calibration — must be included. Otherwise the
harness can manufacture an advantage by varying only the favorable parameter.

### S3 — Benchmark artifacts need a contract, not only light validation

Each standalone artifact should define a version, axis name and units, metric
name and units, ordered configurations, assumptions, provenance/replay link,
and bracket semantics. The bracket must distinguish sampled endpoints from an
interpolated crossing and retain both neighboring samples.

### S4 — “General DFOS receiver” is too broad for this v1 model

The proposed receiver assumes BB84-specific sufficient statistics, random
afterpulse errors, and one aggregate detector-memory process. That is useful,
but it is not yet a detector-technology-neutral DFOS receiver. Keep the
low-level rate-to-window utility general; describe the response wrapper as the
declared QKD receiver model until a second caller proves the abstraction.

### S5 — Default-path language must match stack-always architecture

Replace "no link effects" and "no effects active" with **"no opt-in LINK
features"**. Production effects are assembled on every `simulate_pass()` call.
The default-path byte-identity requirement itself remains correct.

## 5. Decisions worth preserving

- Keep `bb84.py` unchanged. The receiver wrapper should reuse the existing
  `estimate_decoy_bounds(...)`, `secure_key_rate(...)`, and result semantics;
  it must not fork the decoy estimator.
- Propagate error gains `E_x Q_x` and aggregate QBER as `E[EQ]/E[Q]`.
- Integrate a physically valid PDT before nonlinear estimator calculations.
- Keep source-intensity realization, Doppler, jitter, and misalignment
  bridge-rejected in LINK-6a.
- Keep benchmark artifacts separate from the core v2 results artifact.
- Preserve default-path emitted bytes and all frozen-hash tests.
- Keep finite-key analysis out of 6a, but label all resulting key rates
  asymptotic and model-conditional.

## 6. Recommended implementation sequence

Even if LINK-6a remains one plan and one branch, it should have internal gates:

### Gate A — Receiver contract and bridge seam

- Declare intensity-selection probabilities and output-rate units.
- Declare detector cardinality, noise ownership, gate control, and operating
  convention.
- Select the shared afterpulse/dead-time model.
- Add the per-sample receiver-input type and exact consumed-field bridge.
- Prove identity and shared-availability equivalence before mission emission.

### Gate B — Mission integration and replay manifest

- Route the receiver model through `simulate_pass(...)` without a second
  physical pipeline.
- Carry optional provenance from `PassResult` to the production emitter.
- Add the typed, versioned replay schema and production replay entry point.
- Preserve default-path bytes.

### Gate C — PDT consumption

- Select the bounded total-transmittance law or explicit validity guard.
- Restrict or define supported stochastic stacks.
- Declare detector-memory/fading timescale order.
- Prove quadrature convergence and sampled/PDT consistency under the same law.

### Gate D — Benchmark artifacts

- Add the small benchmark schema.
- Use physically comparable named configurations.
- Emit auditable bracket endpoints and assumptions.

This sequence allows a failed detector-model review to stop before schema and
benchmark surfaces depend on it.

## 7. Minimum acceptance-test additions

In addition to the draft's tests, the revised plan should require:

1. A signal click can increase the later shared afterpulse burden seen by decoy
   and vacuum settings; no per-intensity detector histories.
2. Changing intensity-selection probabilities changes shared detector load but
   does not change the base optical gains.
3. Shared common availability scales `Y1_L` and key rate while preserving
   `e1_U`, as shown algebraically above.
4. Per-intensity availability is rejected or demonstrably absent.
5. Gains and error gains remain physical at high base gain and near the
   afterpulse model boundary; no clipping.
6. The selected afterpulse/dead-time operating convention is present in
   provenance, and invalid independent parameter sweeps fail if disallowed.
7. Legacy `dark_count_prob` plus a rate contribution follows the declared
   absolute/incremental ownership rule and cannot double count one source.
8. Detector cardinality is tested with hand-computed no-click probabilities.
9. `gate_window_s` is accepted only through its declared control and respects
   pulse-period/model bounds.
10. The consumer lifts bridge rejection for exactly the four approved fields;
    all LINK-6b and source fields still fail.
11. A time-varying rate effect reaches the matching mission sample rather than
    being collapsed to one pass-wide detector object.
12. PDT mode rejects unsupported stochastic-stack combinations.
13. PDT and sampled mode use the same bounded law and declared receiver-memory
    order.
14. Replay reconstructs a result through the real production entry point from
    the emitted manifest; unknown effect types and extra fields fail.
15. The benchmark validator rejects mismatched axes, missing units, ambiguous
    brackets, and incomplete assumptions.

## 8. Evidence reviewed

### Repository evidence

- `src/qkd/bb84.py`: gains and decoy bounds; `DetectorParams.dark_count_prob`
  is authoritative; no intensity-selection probabilities exist.
- `src/qkd/mission.py`: stack-always production path; one pass-wide
  `DetectorParams`; `simulate_profile(...)` calls the honest estimator per
  channel sample.
- `src/qkd/link.py`: rate observables compose, but the bridge rejects all four
  detector-side LINK-6a fields; `audit_record()` currently records only
  controls, seed, and effect IDs.
- `src/qkd/effects.py`: afterpulse/dead-time parameters are calibrated owners;
  no built-in background-rate or detector-dark-rate effect exists.
- `src/qkd/schema.py`: declared extensions affect vocabulary, while deep
  validation still requires every `run_metadata` value to be a string.
- ADR-0003: coincidence window is a control; distribution must reach the
  estimator before nonlinear maps; controls must be auditable.

Validation runs performed for this review:

- `qkd_env/bin/python -m pytest -q` — **439 passed**.
- `qkd_env/bin/python -m pytest -q --ignore=tests/test_teleportation_qiskit.py`
  — **418 passed**.

### Primary technical references

- Papapanos et al., [Afterpulsing Effect on the Baseline System Error Rate and
  on the Decoy-State Quantum Key Distribution
  Protocols](https://arxiv.org/abs/2010.03358). Supports treating afterpulse
  detections as receiver-generated correlated noise and propagating their
  effects through decoy gains, error gains, and secure-key calculations.
- Wiechers et al., [Systematic afterpulsing-estimation algorithms for gated
  avalanche photodiodes](https://doi.org/10.1364/AO.55.007252). Models gated
  afterpulse and dead-time behavior through gate-history probabilities rather
  than independent scalar post-processing.
- Losev et al., [Dead time duration and active reset influence on the
  afterpulse probability of InGaAs/InP single-photon avalanche
  diodes](https://arxiv.org/abs/2104.03919). Supports the requirement that
  afterpulse probability be interpreted under a declared dead-time/holdoff
  operating convention.
- Ma et al., [Practical decoy state for quantum key
  distribution](https://doi.org/10.1103/PhysRevA.72.012326). Governs the
  asymptotic weak+vacuum decoy quantities reused by the current estimator.
- Vasylyev, Semenov, and Vogel, [Characterization of free-space quantum
  channels](https://arxiv.org/abs/1810.05700). Defines a physical atmospheric
  channel PDT on total transmittance `eta in [0,1]`, supporting the objection to
  an unbounded total-transmittance quadrature without a declared treatment.

## 9. Final re-review gate

Do not authorize implementation until the next draft answers, with equations
and type/data flow rather than prose alone:

1. What process generates shared afterpulses across interleaved intensities?
2. What exactly does `p_ap` mean relative to dead time and live gates?
3. What are the intensity-selection probabilities and key-rate units?
4. Is dead-time availability common, and where does it enter the decoy
   sufficient statistics?
5. Are noise rates absolute or incremental, before or after efficiency, and per
   detector or aggregate?
6. How does `gate_window_s` conform to ADR-0003's control contract?
7. What exact per-sample object crosses from `EffectiveLinkState` into the
   receiver wrapper?
8. Which stochastic stacks are legal in PDT mode, what is their bounded law,
   and what is the fading-versus-memory order?
9. What complete, typed record is sufficient for production replay?
10. What physically meaningful configurations does the benchmark compare?

Once those are pinned, the implementation can remain additive and keep the
verified estimator core untouched. Without them, LINK-6a would likely require
later changes to its public configuration, schema, detector mathematics, and
benchmark semantics — exactly the expensive retrofit this review is intended
to prevent.
