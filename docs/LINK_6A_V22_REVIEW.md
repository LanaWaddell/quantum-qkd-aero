# LINK-6a v2.2 Confirmation Review — Dispatch Hold

- **Disposition:** Not yet approved for dispatch; targeted v2.3 correction required
- **Review date:** 2026-08-17
- **Plan reviewed:** `docs/LINK_6A_PLAN.md`, v2.2
- **Plan SHA-256:** `6146328318735c9e577e0e9f54faf87374c6feefefdec8979b2e4dd8efc1b4d4`
- **Prior gate:** `docs/LINK_6A_V21_REVIEW.md`, SHA-256 `232109ba0bf55ecb6a077d23abfffd3058f66048744da899c75af6215d2b5c4b`
- **Repository baseline:** `5b530ca`
- **Scope:** confirmation review only; the v2.2 plan and source tree were not modified

## 1. Outcome

V2.2 correctly fixes the numerical anchor, the exact click-rate identity, the
post-afterpulse vacuum-yield concept, the public activation surface, the named
selection-probability tolerance, the gate-window refusal rule, the afterpulse
limitation, and the availability-weighted convex-mixture argument.

The shared receiver model remains approved. No physics redesign is requested.

Dispatch cannot yet be approved because several v2.2 statements conflict with
the live repository or with other parts of the same plan. The most immediate
ones are factual: §5 substitutes the numerical-anchor fixture's `10^4` pulses
at `10^6 s^-1` for the live mission defaults of `10^6` pulses at `10^8 s^-1`,
and it names an existing `EffectRngError` that does not exist. More
substantively, the PDT law effect is not explicitly removed from the
`seed=None` deterministic stack, the base error-gain route remains undefined,
and Appendix A still omits fields/provenance it calls total.

These are bounded corrections. Once the findings below are resolved, the plan
can be approved without reopening B1/B3 or repeating the broad review cycle.

## 2. Dispatch blockers

### C1 — Correct the PDT pulse defaults and remove the false independence claim

**Plan location:** §5, line 162.

The live mission constants are:

```text
DEFAULT_N_PULSES                 = 1,000,000
PULSE_REPETITION_RATE_HZ         = 100,000,000 s^-1
default sample spacing           = 0.476955506437172 s
physical pulses in that interval = 47,695,550.6437172
n_pulses / f_rep                 = 0.01 s
```

The plan instead states `10^4` pulses, `10^6 s^-1`, and approximately
`4.8 * 10^5` physical pulses. Those are scaled anchor-fixture values, not the
repository defaults. The 0.01-second ratio happens to remain the same, which
can hide the substitution.

The sentence claiming each uniformly placed counted pulse has an
**independent** fading draw is also physically false for a process with a
3-ms coherence time. Uniform selection across a block can be exchangeable and
can sample the stationary marginal, but pulses falling in the same coherence
interval remain correlated. Fifty coherence intervals do not make individual
pulses independent.

Required correction:

1. Use the live `10^6 / 10^8` defaults and the corresponding approximately
   47.7-million-pulse physical train.
2. Define `n_pulses` as a uniformly distributed expected-count subsample of
   total protocol pulses for PDT diagnostics; do not call the fading samples
   independent.
3. State that LINK-6a computes deterministic asymptotic expectations and does
   not claim finite-key independence. Temporal correlations inside the block
   remain outside the finite-key model.
4. Require `PdtConfig.block_duration_s` to equal the profile bin width within a
   named tolerance, or define a separate explicit binning contract. Merely
   accepting a caller-provided duration allows a false 10-second duration to
   be attached to a 0.477-second profile sample.
5. Define the final sample's bin width. The current profile uses one uniform
   sample width, so reusing that width for every sample is the conservative
   minimal rule.

The memory guard from the v2.1 review also remains unresolved. A next-live-gate
afterpulse has at least one gate period of memory even when `dead_time_s = 0`.
Replace the vacuous `tau_c >= 20 * dead_time_s` zero-dead-time boundary with a
declared effective memory scale that includes `1 / f_rep` (choose and document
the exact hold-off convention).

### C2 — Make the PDT deterministic-stack path executable

**Plan location:** §5 line 149 and §8 line 178.

The plan says a PDT stack is built with `seed=None`, but the accepted
`ScintillationFadingEffect` requests an RNG from `evaluate(...)`. If that law
effect remains in the evaluated stack, PDT always raises before quadrature.
The plan never states the required exclusion path.

Freeze this sequence:

1. Identify exactly one registered law effect.
2. Obtain its `stationary_law(...)` at the current geometry.
3. Build/evaluate a deterministic stack from **all other** admitted effects,
   preserving their order and controls.
4. Apply the law effect's relative transmittance factor at each quadrature
   node without calling its stochastic `evaluate(...)` method.
5. Feed each physical node state through the receiver.

The claimed existing exception is also misnamed. The live runtime defines
`SeedRequiredError`, not `EffectRngError`. Correct the plan and acceptance test.

`PDT_ADMISSIBLE_EFFECTS` must enumerate stable registry type IDs and their
classification (`deterministic` or `law`) rather than saying “the built-in
deterministic production/LINK effects.” That phrase leaves the implementer to
decide whether built-ins such as `PointingJitterEffect` and
`MuFluctuationEffect` qualify. The exact allowlist is the contract.

The `seed=None` trap can then test a deliberately misclassified admitted test
effect requesting RNG and must produce the existing `SeedRequiredError`.
Unregistered custom effects should continue to fail at allowlist admission
before evaluation.

### C3 — Reuse or completely freeze the base BB84 statistics path

**Plan location:** §1.2 line 38, §1.5 line 76, and Appendix A line 259.

V2.2 correctly states that the final estimator consumes post-afterpulse
`Q'_vacuum` through `gains["vacuum"]`. However, the route remains internally
contradictory:

- §1.2 says the wrapper independently reproduces the base gain law;
- it never defines the corresponding base error-gain law `T_x`;
- §1.5 still says the estimator consumes `(Q'_x, E'_x, p_noise)`; and
- Appendix A repeats `estimate_decoy_bounds` on `(Q'_x, E'_x, p_noise)`, even
  though the live estimator has no `p_noise` argument.

The current certified base error gain is not implied by the gain equation:

```text
T_x = 0.5 * y0 + e_d * (1 - exp(-eta * mu_x))
```

The lowest-risk route is to construct a detector copy with
`dark_count_prob=p_noise` and call the existing public `run_decoy_bb84(...)`
for base `Q_x/E_x`, then apply the receiver transformation and call the same
unchanged `estimate_decoy_bounds(...)`/`secure_key_rate(...)` functions on
`Q'_x/E'_x`. This preserves the certified gain and error laws without copying
private formulas.

If the plan deliberately chooses an independent receiver-side reproduction,
it must freeze **both** base gain and base error-gain equations and require a
full parity test against `run_decoy_bb84` over boundaries and representative
grids. Gain-only parity is insufficient.

In either case, replace every stale `(Q'_x, E'_x, p_noise)` phrase with:

```text
estimate_decoy_bounds(gains=Q'_x, qber_per_intensity=E'_x, intensities=...)
where its internal y0 is Q'_vacuum == gains["vacuum"]
```

The acceptance assertion `Q'_vacuum > p_noise` also needs its actual domain:
`p_ap > 0`, `Q_bar_reg > 0`, and `p_noise < 1`. At the all-zero or saturated
boundaries, strict inequality does not hold.

### C4 — Finish Appendix A's claimed totality

**Plan location:** Appendix A.

Appendix A is improved but is not yet a total executable contract:

- `ReceiverBlockResult`, `ProfileResult`, and `PassResult` exact field/type
  additions are not enumerated.
- `sifted_key_length` still says “base sifted * A” and “per signal-block” even
  though §5 now defines `n_pulses` as a total-protocol-pulse subsample. Under
  that definition the expected delivered count is
  `round(n_pulses * pi_signal * q * A * Q'_signal)`.
- `units` is called fixed-vocabulary without naming its exact keys and string
  values.
- No provenance leaf map is provided for the nested `profile.link_receiver`
  subtree, although the live validator recursively requires those tags.
- The acceptance list tests only an unknown key, not missing keys, wrong
  lengths, nonfinite values, range violations, normalization failure, or unit
  vocabulary.

Add the exact optional dataclass fields and define every emitted leaf. At
minimum, freeze provenance paths for:

```text
profile.link_receiver.secure_key_rate_per_signal_pulse
profile.link_receiver.availability
profile.link_receiver.pi.signal
profile.link_receiver.pi.decoy
profile.link_receiver.pi.vacuum
profile.link_receiver.units.<exact-key>
```

Arrays remain one provenance leaf, consistent with the live validator. As
correctly stated earlier, `run_metadata.link_provenance` needs no provenance
tag because `run_metadata` is outside the tagged data sections.

### C5 — Close the custom-effect audit contract

**Plan location:** §4 line 145 and Appendix A.2.

The prior D7 finding is unchanged. The plan says an unregistered custom effect
emits its “declared parameters descriptively,” but `ChannelEffect` has no
declared-parameter interface and generic dataclass serialization is explicitly
forbidden.

Choose one rule before dispatch:

- require an explicit `audit_spec()` protocol for a
  `configuration_auditable` custom effect; or
- emit stable type/effect IDs only and mark parameter completeness false.

Do not describe a run as configuration-auditable if relevant constructor
parameters are silently unavailable.

## 3. Required consistency edits

These are mechanical but should be completed in the same revision:

1. Replace the stale “bounded law” wording in the §5 heading, line 158, and
   §8 line 176 with “unbounded log-normal with validity guard.”
2. In Appendix A, replace the stale estimator-source tuple containing
   `p_noise` as described in C3.
3. Correct every `EffectRngError` occurrence to `SeedRequiredError`.
4. Correct the §11 claim that the PDT timing finding is fully adopted; it is
   only closed once C1's live constants, correlation language, duration
   validation, and memory scale are fixed.
5. Remove “all existing tests” from the untouched list if implementation
   legitimately needs to extend an existing test file; otherwise explicitly
   bind the implementation to new test files only.

## 4. Confirmed v2.2 improvements

The following changes are accepted:

- corrected 12-plus-digit numerical anchor, including
  `A = 0.918124082928941429...`;
- exact `R_click = f_rep * Q_bar_reg` identity;
- strict positive `pi` entries with `PI_SUM_TOLERANCE = 1e-9`;
- post-afterpulse `Q'_vacuum` as the estimator's vacuum gain;
- declared aggregate-model limitation for random afterpulse-only errors;
- explicit `simulate_pass(..., receiver, link_mode, pdt_config)` activation
  surface and invalid-combination errors;
- receiver activation never inferred from the presence of effects;
- no silent `gate_window_s` default when a rate observable is consumed;
- canonical per-protocol-pulse rate and unchanged L5 yield relationship;
- receiver-aware honest anomaly reference;
- closed-world PDT direction rather than behavioral stochastic inference;
- availability-weighted convex-mixture justification, provided one common
  intensity-independent weighting measure is preserved;
- unbounded-log-normal tail/node validity policy; and
- environment-qualified baseline test counts.

## 5. Prior-gate closure

| V2.1 finding | V2.2 status |
|---|---|
| D1 numerical anchor | **Closed.** |
| D2 PDT acquisition and memory | **Partially closed.** A subsample model was chosen, but defaults, correlation, duration binding, and zero-dead-time memory remain wrong or incomplete (C1). |
| D3 noise-to-estimator plumbing | **Partially closed.** `Q'_vacuum` is correct; base error statistics and stale three-argument descriptions remain (C3). |
| D4 activation API/pulse-count semantics | **Partially closed.** API is frozen; sifted-count and PDT pulse semantics remain inconsistent (C1/C4). |
| D5 total schema/provenance | **Partially closed.** Closed-world subtrees were introduced, but dataclass fields, units, provenance, and validator matrix remain incomplete (C4). |
| D6 PDT stochastic admission | **Partially closed.** Allowlist direction is correct; exact members, law exclusion, and exception path remain incomplete (C2). |
| D7 custom-effect audit | **Open.** No parameter-introspection contract was added (C5). |

## 6. Final confirmation gate

Dispatch is approved when one targeted revision answers these six questions:

1. Are all PDT examples and guards expressed using the live mission defaults,
   without claiming independent fading draws?
2. Is `block_duration_s` bound to the actual profile bin, and does the memory
   scale include at least one live-gate period?
3. Is the law effect excluded from the deterministic stack, with an exact
   allowlist and the real `SeedRequiredError` path?
4. Are base gain **and error-gain** statistics reused or fully parity-pinned,
   with `Q'_vacuum` as the unchanged estimator's sole vacuum input?
5. Does Appendix A enumerate exact dataclass fields, sifted-count semantics,
   unit strings, provenance leaves, and the full validator rejection matrix?
6. What exact information makes an unregistered custom effect genuinely
   configuration-auditable?

Once these are answered, the appropriate disposition is **approved for
dispatch through Gates A–D**. The receiver equations and anchor do not require
another review.

## 7. Verification evidence

- The plan hash matches the supplied v2.2 hash exactly.
- The corrected anchor values and exact click-rate identity were independently
  recalculated and agree.
- Live mission defaults were read from `src/qkd/mission.py`.
- Live RNG failure behavior was read from `src/qkd/link.py`; the exception is
  `SeedRequiredError`.
- The repository remains at source baseline `5b530ca`; this review introduced
  no source or plan changes.
