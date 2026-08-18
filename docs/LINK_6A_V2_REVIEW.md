# LINK-6a v2 Re-review — Targeted Revision Gate

- **Disposition:** Approve after targeted v2.1 revision; implementation remains unauthorized
- **Review date:** 2026-08-17
- **Plan reviewed:** `docs/LINK_6A_PLAN.md`, v2 dated 2026-08-17
- **Plan SHA-256:** `9fb6d1a8c89e5b7360a7af516802a8bd987891c957ce47ef84382038a4240388`
- **Compared against:** v1 SHA-256 `e8ef06f35e6756ed9dc7546fd500ca9a69b98a7d65e8647ab7bd1f41561eab51`
- **Repository baseline:** `5b530ca`; unchanged source baseline previously verified at 439 passed / 418 with the Qiskit-specific file excluded
- **Scope of this review:** documentation only; the v2 plan was not modified

## 1. Outcome

The v2 plan is a substantial and technically serious correction. The two
material receiver-physics errors in v1 are closed:

- the afterpulse process is now driven by one aggregate detector history and
  crosses signal/decoy/vacuum intensity classes; and
- dead-time availability is now one common factor, preserving the homogeneity
  property of the existing asymptotic decoy estimator.

The shared-history equations are internally consistent as a declared
next-live-gate mean-field approximation. The common-availability identity was
also checked against the live estimator over a broad grid of physically
generated gains; no counterexample was found. The revised operating-pair,
noise-ownership, control-ownership, bridge-consumption, and replay directions
are all materially better than v1.

The plan is not quite dispatch-ready. The remaining findings are narrower than
the first review, but three affect public contracts and should be fixed on paper
before code exists:

1. the opt-in emitted rate/result schema is not defined and conflicts with the
   current key-yield consistency rule if implemented literally;
2. the PDT "bounded law" is still mathematically incomplete; and
3. the selected slow-fading order depends on timescales that are not carried by
   the current stationary-law interface or a proposed configuration.

Recommended disposition: **targeted v2.1 revision followed by a short
confirmation review**. No further redesign of the B1/B3 receiver core is
requested.

## 2. Blocker disposition from the first review

| First-review item | v2 disposition | Re-review finding |
|---|---|---|
| B1 shared detector history | **Closed** | Aggregate occupancy, cross-intensity afterpulsing, bounded probability union, and error-gain propagation are now explicit. Edge domains need one small amendment (§3.5). |
| B2 afterpulse/dead-time convention | **Closed** | The calibrated next-live-gate operating pair is an honest first-order choice; independent sweeps are forbidden. |
| B3 common availability | **Closed** | One shared `A` is used and estimator homogeneity is an acceptance test. Result-field semantics still need to be enumerated (§3.1/§3.6). |
| B4 intensity probabilities/rate units | **Partially closed** | `pi` and both rate units now exist conceptually, but their emitted paths and canonical profile meaning are unresolved (§3.1/§3.5). |
| B5 noise ownership/cardinality | **Closed** | Incident background, registered additional dark rate, aggregate `y0`, detector efficiency placement, and the withdrawn coincidence analogy are clear. |
| B6 gate window as control | **Partially closed** | Ownership is corrected; exact registry partitioning and the strict-positive bound mechanism remain unspecified (§3.4). |
| B7 consumption seam | **Mostly closed** | `ReceiverInputs`, residual bridge, per-sample flow, and result-carried provenance are sound. The complete result mapping is still absent (§3.1/§3.6). |
| B8 PDT contract | **Partially closed** | Stack admissibility and order are chosen, but support/tail handling and timescale enforcement remain incomplete (§3.2/§3.3). |
| B9 replay protocol | **Mostly closed** | Canonical string encoding, effect registry, and production replay entry point are credible. Runtime policy for unregistered custom effects remains open (§3.7). |

All S1–S5 findings are directionally closed. The built-in rate owners,
QKD-specific response label, stack-always wording, physically comparable
benchmarks, and artifact contract should be retained.

## 3. Required v2.1 corrections

### R1 — Freeze the opt-in profile/result/schema contract

Plan §1.1 introduces:

```text
secure_key_rate_per_signal_pulse
secure_key_rate_per_protocol_pulse
```

but it does not say where those arrays live in the v2 artifact, what
`profile.secure_key_rate_per_pulse` contains when the receiver is active, or
which profile rate drives `secure_key_yield_bits`.

That omission is immediately observable in the current validator. L5 computes:

```text
secure_key_yield_bits
    = sum(profile.secure_key_rate_per_pulse[i] * f_rep * dt)
```

If the legacy profile array remains per signal pulse while the new yield uses
an additional `pi_signal`, the emitted payload fails its own consistency check.
New profile fields also fail strict vocabulary validation unless declared and
typed.

Recommended contract:

1. On a receiver-active run,
   `profile.secure_key_rate_per_pulse` is the **delivered per-protocol-pulse**
   rate. This is the literal meaning of the existing field and keeps the L5
   yield equation valid without a hidden multiplier.
2. Add an explicitly named receiver subtree or declared profile field for the
   delivered per-signal-pulse diagnostic. Do not make two arrays silently
   compete as the canonical yield source.
3. The default path remains byte-identical because its documented implicit
   convention is `pi_signal = 1`, so signal-pulse and protocol-pulse rates
   coincide there.
4. Enumerate the exact `ProfileResult`, `PassResult`, and emitted JSON fields,
   including types, ranges, provenance leaves, and L5 relationships.
5. State which array the dashboard reads on receiver-active output. The
   canonical `profile.secure_key_rate_per_pulse` should remain sufficient for
   the current dashboard.

Plan §1.5 refers to a "plan appendix table" enumerating every touched result
field, but the v2 document has no appendix. Add that table; it should include
at least gains, error gains/QBER, `Y1_L`, `e1_U`, `q1`, sifted length, both rate
units, canonical profile rate, and integrated yield.

### R2 — Complete the PDT support/tail rule

Plan §5 calls the selected treatment a "bounded law," but the underlying
log-normal remains unbounded. A tail-probability guard does not itself define a
bounded distribution. If the mass above `eta_total = 1` is below the chosen
tolerance, the plan still does not say what happens when a 21- or 41-node
quadrature point evaluates above one.

The v2.1 plan should select one complete rule. The least disruptive option is:

- label the model accurately as an **unbounded log-normal approximation with
  a negligible-unphysical-tail validity guard**, not a bounded law;
- define the exact tail tolerance and how it contributes to the numerical
  error budget;
- require every quadrature node used by both the 21- and 41-node rules to
  satisfy `eta_base * f_i <= 1`, otherwise raise;
- retain the sampled-mode bridge raise for an actually drawn unphysical total
  transmittance; and
- run the sampled/PDT consistency test only in a declared regime where the tail
  bound and node-domain checks pass.

An explicitly truncated and renormalized log-normal would also be coherent,
but it is a larger model change and would require the sampled generator to use
the same truncated law. Silent clipping remains unacceptable.

### R3 — Represent and enforce the slow-fading applicability condition

The conditional-receiver-then-average order is physically reasonable for the
project's reference hierarchy:

```text
detector memory (microseconds) << turbulence coherence (about 3 ms)
                              << profile block (about 0.1–1 s)
```

However, the current `LogNormalLaw` carries only `mu_log` and `sigma_log`.
Neither it nor the v2 plan supplies a coherence time, a block duration, or a
guard relating those values to `dead_time_s`. A custom law-capable effect can
therefore enter PDT mode even when the selected ordering is false. The existing
dead-time owner also accepts any finite nonnegative duration.

The v2.1 plan must define an enforceable applicability contract. For example:

- PDT configuration records `fading_coherence_time_s` and `block_duration_s`,
  or the stationary-law interface exposes them;
- provenance records both values and the selected
  `conditional_then_average` order;
- an exact declared ratio guard checks detector-memory scale against fading
  coherence time;
- another guard checks the block contains enough coherence intervals for the
  stationary-PDT approximation; and
- effects that cannot provide the required timing declaration are rejected in
  this PDT mode.

The plan should state whether block duration is the mission-axis sample width,
`n_pulses / f_rep`, or a new explicit value. Those differ today: the default
`n_pulses / f_rep` is 0.01 s, while a 1000-sample pass profile has a much larger
sample interval. The choice affects whether a block actually samples the
stationary fading distribution.

### R4 — Specify estimator-control registry partitioning and positive bounds

Moving `gate_window_s` onto the ratified control surface is correct. The live
`ChannelStack`, however, validates every control it receives against its own
effect-owned registry and rejects unknown names. Passing the combined control
mapping directly to the stack would therefore reject the estimator-owned gate
window.

The plan should state that mission composition:

1. builds one collision-checked registry from stack and estimator controls;
2. validates the complete caller mapping once;
3. partitions values by owner;
4. passes only effect-owned controls into `ChannelStack.evaluate(...)`; and
5. passes only receiver-owned controls into the receiver.

Alternatively, authorize a deliberate `link.py` registry extension. Do not
leave this as an implementation inference.

`ControlSpec.bounds` is currently a closed interval. The phrase "strictly
positive finite lower bound" therefore needs an exact representable lower
bound or an approved open-bound extension. Name the constant/mechanism and add
zero, NaN, infinity, and just-inside-bound tests.

### R5 — Close the receiver equation edge domains

Three small domain clauses prevent implementation-dependent behavior:

- Require `pi_signal`, `pi_decoy`, and `pi_vacuum` to be strictly positive for
  this three-intensity estimator. Allowing zero means the corresponding
  asymptotic gain cannot be observed and `pi_signal = 0` cannot produce key.
- Define `E'_x = 0` when `Q'_x = 0`; otherwise the all-zero channel/noise case
  produces `0/0`.
- Prefer consumer-domain `0 <= p_ap < 1`. The LINK-5 parameter owner may retain
  its broad `[0,1]` storage domain, but the critical branching boundary
  `p_ap = 1` makes the zero-base-click fixed point singular and is outside the
  intended first-order receiver model.

Also call `Q_reg_bar` an aggregate registered-click **probability/occupancy**;
`R_click` is the first rate-valued quantity.

### R6 — Make the wrapper/result mapping total, including anomaly semantics

The plan keeps `bb84.py` unchanged, which remains the right boundary, but does
not define what type the wrapper returns or how every `BB84Result` field maps
through afterpulsing and dead time.

This matters especially for:

- `gains`, `y1_lower_bound`, and `q1`: are they pre-dead-time/live-gate values
  or delivered per-emitted-pulse values?
- `sifted_key_length`: it must include `pi_signal` and common availability when
  interpreted over total protocol pulses.
- `decoy_anomaly_score`: a calibrated honest receiver must not look like QND/PNS
  Eve merely because detector memory changed the gain relationship.

Define a receiver-specific result type or a complete mapping table. For the
honest LINK-6a path, the anomaly reference must pass through the same calibrated
receiver model, so the honest receiver remains approximately zero-anomaly.
Future Eve integration can then compare receiver-aware honest and observed
statistics through the same estimator path.

### R7 — Define replay policy for unregistered effects and manifest presence

The built-in effect registry and canonical JSON string are a practical solution
to the current schema type constraint. One runtime question remains: the public
mission API accepts custom `ChannelEffect` implementations that may not have a
registered replay codec.

Choose one explicit policy:

- replay-grade production emission rejects an unregistered active effect; or
- the manifest carries a required replayability status and the run is emitted
  as configuration-auditable but non-replayable.

The plan's project-level downgrade clause is not yet a per-run rule. Also
restate that `run_metadata.link_provenance` is absent when no opt-in LINK
feature is active; that absence is part of the frozen default-path contract.

## 4. Recommended clarifications

These are not approval blockers but will reduce implementation interpretation:

- List every file to create or modify. V2 adds `effects.py` to scope and may
  require `link.py`, schema, provenance, result dataclasses, and emitter tests;
  the file boundary should be explicit before dispatch.
- Define the advantage-crossing interpolation algorithm and tolerance. Preserve
  both neighboring samples and label the interpolated point as model-derived,
  not grid-independent truth.
- Give each Gate A–D a concrete expected test delta. The final counts must still
  come from real runs, but a planned delta catches accidental missing coverage.
- Add one independent numerical receiver anchor with precomputed `Q_bar`,
  `Q_reg_bar`, `a`, `Q'_x`, `T'_x`, `A`, and both rate units. Structural tests
  alone should not be the only transcription guard.

## 5. Findings accepted without further redesign

The following v2 decisions are approved as written, subject to the targeted
corrections above:

- the aggregate shared-history mean-field afterpulse model;
- random afterpulse-only errors with optical-click precedence on collisions;
- the calibrated next-live-gate `(p_ap, dead_time_s)` operating pair;
- one common non-paralyzable mean-field availability;
- pre-dead-time/live-gate decoy statistics plus one common delivered-rate
  multiplier, with the homogeneity identity tested;
- aggregate single-detector-equivalent noise ownership and one-time detector
  efficiency application;
- `ReceiverInputs` extraction plus unchanged residual bridge rejection;
- estimator-side ownership of `gate_window_s` as a run-level control;
- exactly one law-capable stochastic effect in the initial PDT mode;
- canonical JSON as a string-valued `run_metadata` extension;
- explicit built-in effect replay registry rather than `dataclasses.asdict`;
- built-in background and additional-dark-rate parameter owners;
- QKD-specific receiver labeling; and
- sequential Gates A–D.

## 6. Re-review gate

V2.1 is ready for implementation authorization when it answers these seven
questions directly in the plan:

1. Which emitted array is the canonical per-protocol-pulse rate, and how does
   L5 recompute yield from it?
2. What exact schema/result/provenance fields exist on receiver-active runs?
3. What happens to every quadrature node and tail contribution above physical
   total transmittance one?
4. Where do fading coherence time and PDT block duration come from, and what
   enforceable ratio validates the selected memory/fading order?
5. How are stack-owned and estimator-owned controls collision-checked,
   partitioned, and bounded?
6. What are the complete edge domains and output-field mappings of the
   receiver wrapper, including honest anomaly behavior?
7. What happens when an active custom effect has no replay codec?

Once those are written down, the plan can move to **approved for implementation
through Gates A–D**. The core receiver model does not need another redesign.
