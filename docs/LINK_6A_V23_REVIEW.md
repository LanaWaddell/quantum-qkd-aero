# LINK-6a v2.3 Confirmation Review — Narrow Contract Correction

- **Disposition:** Approve after one narrow v2.3.1 contract correction; implementation remains unauthorized until applied
- **Review date:** 2026-08-17
- **Plan reviewed:** `docs/LINK_6A_PLAN.md`, v2.3
- **Plan SHA-256:** `f9d81c9884cab29d492b2f5218a37a4fb090c57a705a002a9e19aa23c3ea019f`
- **Prior gate:** `docs/LINK_6A_V22_REVIEW.md`, SHA-256 `a21ac0ff9eb3343346d7fe823c400c11918a9fbd31d7e028670ce88cd79bf2c1`
- **Repository baseline:** `5b530ca`
- **Scope:** confirmation review only; no source or plan changes

## 1. Outcome

V2.3 closes the six substantive questions from the v2.2 confirmation review.
The detector-copy route now reuses both certified BB84 base laws, the PDT law
effect is excluded from deterministic evaluation, the allowlist is explicit,
the pulse/block model uses the live defaults without a false independence
claim, the memory and grid guards are executable, and the receiver/Eve boundary
is honest.

The two discretionary decisions are approved:

- **Law effect must be last:** approved. It converts node substitution from a
  commutation assumption into exact replacement of the sampled last factor.
- **Receiver and Eve mutually exclusive in LINK-6a:** approved. Honest receiver
  integration earns its behavior first; receiver-aware Eve composition remains
  a later, separately reviewed capability.

The plan is very close to dispatch-ready. Two contract defects remain:

1. the selection probabilities are assigned the wrong provenance class; and
2. the manifest claims closed-world validation at every depth without defining
   the nested vocabularies needed to perform it.

These do not reopen the physics. Correct them, plus the small semantic cleanups
in section 3, and the plan is approved for Gates A–D without another broad
review.

## 2. Required pre-dispatch corrections

### F1 — Correct `pi` provenance from `SIMULATED` to `ILLUSTRATIVE`

**Plan location:** Appendix A.4.

`pi.signal`, `pi.decoy`, and `pi.vacuum` are caller/model configuration. They
are not produced by the simulation. The live mission provenance map classifies
analogous configured inputs — intensities and detector settings — as
`ILLUSTRATIVE`.

Appendix A.4 currently assigns `SIMULATED` to both output arrays **and**
`pi.*`. That is incorrect provenance.

Use:

```text
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

Add a positive exact-map assertion and one negative test that deliberately tags
a `pi` leaf as `SIMULATED` and fails the expected provenance contract test.
The generic live validator checks tag validity/coverage, not semantic tag
choice, so this project-specific assertion is necessary.

### F2 — Enumerate the replay manifest's nested closed-world schema

**Plan location:** §4, Appendix A.2, and Appendix A.5.

A.2 now defines the manifest's top-level keys, but A.5 promises unknown-key
rejection “at any depth.” Several nested objects still have no exact vocabulary:

- `mission_config` is described as “complete, typed per existing config
  schema,” but no replay-manifest configuration schema currently exists.
- `receiver` names concepts but not exact keys/types.
- `model_ids` has no member vocabulary.
- `serialization` has no exact keys or identifier values.
- registered effect `params` depend on codecs, but the codec-specific allowed
  keys are not explicitly tied into deep validation.

The implementation cannot reject unknown nested keys without first inventing
those vocabularies. Freeze them before dispatch.

At minimum, enumerate:

```text
mission_config:
  samples
  altitude_km
  peak_elevation_deg
  horizon_elevation_deg
  atmosphere
  detector
  intensities
  n_pulses
  pulse_repetition_rate_hz
  sky_condition

receiver:
  exact pi object
  operating-convention identifier
  any receiver constants that are not already effect/control-owned

model_ids:
  exact key names and accepted identifier values

serialization:
  exact key names and canonical-JSON identifier values
```

For `atmosphere`, detector, intensities, controls, PDT configuration, and every
registered effect codec, either enumerate each nested vocabulary in A.2 or
name the exact validator/codec-owned schema that performs the closed-world
check. Do not use “existing config schema” unless a concrete schema function or
mapping exists in the live tree.

Also resolve the phrase “`p_ap`/`dead_time_s` calibrated pair as consumed” in
the receiver object. Those values originate from effects and may be
sample-varying; they should not be duplicated as one receiver constant unless
the manifest defines the exact scalar/array rule. Prefer single ownership in
the ordered effect specs, with the receiver recording only its operating-model
identifier and input-selection configuration.

## 3. Required semantic cleanups

These are small but should be folded into the same edit:

1. **PDT availability:** Appendix A.1/A.3 should say `availability` is `A` in
   sampled mode and `E_f[A(f)]` in PDT mode. PDT has no single node-independent
   `A`.
2. **A.3 heading:** “all optional, all defaulting to the legacy value” is true
   for the trailing `ProfileResult`/`PassResult` additions, but not for the new
   required fields of `ReceiverBlockResult`. Narrow the heading or split the
   table.
3. **Private anomaly helper:** `_relative_y1_shortfall` is a private
   `bb84.py` helper. In-package reuse is acceptable for honest 6a and is not a
   dispatch blocker, but record that the later receiver-aware Eve PR must
   either promote one canonical public anomaly helper or continue through the
   existing public Eve pipeline — it must not create a third formula.
4. **Historical labels:** Appendix A's heading still says “v2.2.” Relabel it
   v2.3. Historical changelog references can remain historical.

## 4. Six-question gate result

| V2.2 confirmation question | V2.3 result |
|---|---|
| Live PDT defaults, no independent-draw claim | **Closed.** Correct `10^6 / 10^8` defaults; exchangeable/correlated marginal treatment; asymptotic scope explicit. |
| Block bound to grid; memory includes a gate period | **Closed.** Named grid tolerances, final-bin rule, `tau_mem = dead_time + 1/f_rep`. |
| Law excluded; exact allowlist; real exception | **Closed.** Law-last deterministic-prefix path, stable effect IDs, `SeedRequiredError`. |
| Base gain/error statistics reused; post-afterpulse vacuum input | **Closed.** Detector-copy `run_decoy_bb84` route; both certified laws inherited; real estimator signature used. |
| Exact dataclasses, count semantics, units, provenance, validator matrix | **Mostly closed.** Dataclasses/counts/units/matrix are complete; correct `pi` provenance per F1. |
| Honest custom-effect configuration audit | **Closed.** Optional scalar `audit_spec()` with author-asserted completeness; explicit incomplete fallback. |

## 5. Accepted implementation contract

The following should now be treated as frozen for dispatch:

- aggregate shared-history afterpulse model and exact click-rate identity;
- calibrated `(p_ap, dead_time_s)` pair and common availability;
- detector-copy reuse of `run_decoy_bb84` for honest base statistics;
- post-afterpulse `Q'_vacuum` as the unchanged estimator's vacuum yield;
- explicit receiver activation and no implicit activation from effects;
- receiver/Eve mutual exclusion in LINK-6a;
- canonical delivered per-protocol-pulse profile rate;
- exact sifted expected-count law including `pi_signal` and availability;
- required-when-consumed gate window with no silent default;
- law-last, one-law, closed-world PDT stack;
- deterministic prefix evaluated with `seed=None` and the existing
  `SeedRequiredError` defense;
- grid-bound block duration, effective memory scale, and asymptotic
  exchangeable-but-correlated PDT interpretation;
- unbounded log-normal validity guard with no clipping;
- receiver-aware honest anomaly exactly zero in 6a;
- canonical replay/refusal distinction; and
- default-path byte identity.

## 6. Dispatch disposition

After F1, F2, and the four cleanups are incorporated, LINK-6a is **approved for
implementation through sequential Gates A–D**. The next review should be a
brief textual confirmation of those edits, not another mathematical or
architectural cycle.

The implementation review must still verify actual behavior, real test counts,
the frozen default-output hash, and replay from the production path. That is an
implementation gate, not a reason to hold the plan once the two remaining
contracts are explicit.

## 7. Verification evidence

- The v2.3 plan hash matches the supplied hash exactly.
- Live mission defaults and grid width agree with the v2.3 corrections.
- The live RNG exception is `SeedRequiredError`.
- `ScintillationFadingEffect.evaluate(...)` requests `rng_for("fade")`, so
  excluding the law effect from the deterministic prefix is necessary.
- The live estimator takes only `gains`, `qber_per_intensity`, and
  `intensities`; the v2.3 detector-copy route matches that API.
- No source or plan file was modified by this review.
