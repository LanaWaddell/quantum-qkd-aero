# LINK-6b Plan v1.1 Review

**Date:** 2026-08-18

**Plan reviewed:** `docs/LINK_6B_PLAN.md`

**Plan SHA-256:** `aed9834947341c274b4dd8f333cfff6b409ed695d2fcca27bfba0a86cd6c2d79`

**Repository reviewed:** `main` at `ffbe136`; the only change after the plan's implementation baseline `2763c24` is the post-LINK-6a Development Record reconciliation.

## Disposition

**Major revision required before dispatch.**

The three estimator-owned mappings are well chosen, their equations and numerical anchors are correct, and reusing the LINK-6a detector-copy path remains the right architecture. The review found one shared-history physics error, several incomplete boundary contracts, and two implementation-scope inconsistencies. None requires changing `bb84.py` or `link.py`.

## Blocking findings

### B1 - Post-afterpulse vacuum gain is not invariant under gate/filter loss

Plan §8 says `p_bg`, `p_dk`, `p_noise`, and `Q'_vacuum` remain unchanged by every LINK-6b input. The first three are valid direct-input invariants; `Q'_vacuum` is not.

LINK-6a deliberately models one shared detector history. Gate/filter acceptance lowers signal and decoy gains, which lowers aggregate `Q_bar`, the afterpulse arrival probability `a`, and therefore the post-afterpulse vacuum gain:

```text
Q'_vacuum = 1 - (1 - Q_vacuum)(1 - a)
a = p_ap * Q_bar_reg
```

An independent live-code calculation with unchanged `Q_vacuum = 1e-6` and `p_ap = 0.02` produced:

```text
eta = 0.10 -> Q'_vacuum = 0.0005426416717643212
eta = 0.05 -> Q'_vacuum = 0.00027404025969057777
```

Required correction:

- assert `p_bg`, `p_dk`, `p_noise`, and the **base** `Q_vacuum` are unchanged by signal-only acceptance;
- assert post-afterpulse `Q'_vacuum` is unchanged only when `p_ap = 0`;
- add a `p_ap > 0` test proving the expected cross-intensity history coupling remains active;
- replace “`Q'_signal` scales” with an exact assertion against the base gain law at folded transmittance, followed by the existing shared-history transformation. Gains are nonlinear and must not be tested as a simple multiplicative scaling.

This is the only physics error found in the plan.

### B2 - Nonzero source linewidth has no complete activation rule

Sections 1.2 and 2 require `filter_sigma_hz` only when `frequency_offset_hz` is nonzero. But the approved formula also produces finite-linewidth loss at zero Doppler whenever `source_linewidth_sigma_hz > 0`, and that calculation is undefined without `filter_sigma_hz`.

Freeze one rule explicitly. Recommended:

- `filter_sigma_hz` is required when either `frequency_offset_hz != 0` **or** `source_linewidth_sigma_hz > 0`;
- `doppler_residual_fraction` is required only when `frequency_offset_hz != 0`;
- if both are identity and no filter is supplied, `eta_filter = 1.0` exactly;
- if a filter is supplied at zero Doppler, finite source-linewidth acceptance is still computed;
- validate `source_linewidth_sigma_hz` as finite and nonnegative in `ReceiverModel`, manifest v2, and negative/NaN/infinity tests.

This prevents a nonzero recorded receiver parameter from being silently ignored.

### B3 - Replay v1/v2 compatibility needs a version matrix

Section 5 distinguishes the v1 and v2 receiver objects, but does not bind the rest of the manifest vocabulary to the selected version. A closed-world replay contract should not accept impossible hybrids such as a v1 manifest carrying `link-6b.1`, a LINK-6b-only effect, or a LINK-6b-only control.

Add an explicit compatibility matrix and negative tests:

| Manifest | Pipeline | Receiver keys | LINK-6b effects/controls |
|---|---|---|---|
| v1 | `link-6a.1` | `pi`, `operating_convention` | rejected |
| v2 | `link-6b.1` | plus `source_linewidth_sigma_hz` | accepted under current registries |

`schema_version` should remain exactly `2.0` for both. The stored v1 replay test should use a real canonical v1 manifest and prove that replay supplies `source_linewidth_sigma_hz = 0.0` without changing its result. Add cross-version rejection tests for receiver keys, pipeline version, new effect IDs, and new control names.

### B4 - The §7 exception list is incomplete as written

The policy is approved in principle: only a reviewed plan may enumerate superseded tests, and all other tests remain oracles. The live suite shows four corrections needed before that policy is executable:

1. Add `test_replay.py::test_manifest_version_unsupported_rejected`; it currently asserts that version 2 is unsupported and must move to a genuinely unsupported version.
2. Add `test_replay.py::test_canonical_json_reserialization_mismatch_rejected`; its byte replacement is hardcoded to `"manifest_version":1` and becomes a no-op when the default fixture moves to v2.
3. Name the helper `_valid_manifest_dict` explicitly instead of allowing “any A.2 valid-manifest fixture literal.” Give the retained v1 fixture/helper an exact name as well.
4. Specify that the three new `ReceiverInputs` fields are trailing identity defaults (`0.0`). The existing suite constructs `ReceiverInputs` with four positional values many times; defaults preserve those tests honestly. Without defaults, numerous unlisted tests must be edited.

Also do not add a duplicate residual-bridge test: `test_link6a.py::test_intensity_factor_still_rejected_in_receiver_active_mode` already proves the remaining source field is rejected. The superseded frequency-offset test may be removed as enumerated, while the existing intensity test remains untouched.

### B5 - The phase-misalignment validity guard is periodic and does not enforce the stated domain

Section 4 says phase errors beyond `pi/4` are out of model, but proposes checking only `sin^2(delta_phi) <= 0.5`. That admits large phases whenever the periodic sine returns below the threshold; for example, `delta_phi = pi` passes with an emitted error near zero.

If the declared model domain is the principal low-order interval, validate the parameter itself:

```text
0 <= delta_phi_rad <= pi/4
```

Then compute `sin^2(delta_phi_rad)`. Test both boundaries and reject values just above `pi/4`, including `pi` as the periodicity regression case. If arbitrary wrapped phase is intended instead, the plan must define canonical phase reduction and withdraw the “beyond pi/4” limitation. The bounded principal interval is the lower-risk choice.

### B6 - The benchmark acceptance rule is outside the stated implementation inventory

Section 8 requires the benchmark harness to reject a filter sweep that omits its Doppler-acceptance cost, but §10 leaves `src/qkd/benchmark.py` untouched. The live harness knows only the calibrated `(afterpulse_prob, dead_time_s)` pair; it cannot enforce the proposed filter rule.

Choose one:

- add `src/qkd/benchmark.py` to scope and specify the exact machine-checkable declaration/API, including which parameters are required and whether `eta_filter` is recomputed and tolerance-checked; or
- defer this new enforcement until the first benchmark driver/LINK-6c and keep LINK-6b's rule as a documented prohibition only.

The second option is lower risk because LINK-6b ships no benchmark sweep driver. In either case, `src/qkd/schema.py` does not need behavioral modification for manifest v2: its link-provenance validator already delegates to `qkd.replay._validate_manifest_json`. Update §10 so the file inventory matches the actual ownership boundary.

### B7 - Reconcile the plan's cost-surface decision with ratified ADR-0003

The plan correctly observes that narrowing a centered gate/filter is physically feasible and incurs acceptance loss rather than crossing a natural hard lower bound. However, ADR-0003 §3.6 currently says `timing_jitter_s` bounds how tight the gate can go and presents this as `ControlSpec.feasible` coupling, while plan §2 explicitly declines to use `ControlSpec.feasible`.

Do not manufacture an arbitrary minimum-acceptance threshold. Instead, add a brief authoritative reconciliation: LINK-6b implements timing coupling as a response/cost law, while the adjacent-gate condition is a model-validity guard; `ControlSpec.feasible` remains reserved for a genuine feasibility interval. Because ADR-0003 is ratified, make this an ADR clarification or explicitly identify the existing ADR language as illustrative rather than binding before dispatch.

## Confirmed design choices

- `eta_gate = erf(Delta t / (2 sqrt(2) sigma_t))` is correct for a centered Gaussian arrival-time distribution and rectangular gate.
- The two-sided adjacent-gate tail expression is a conservative validity guard; the stated default anchor underflows to zero as reported.
- The Gaussian-line/Gaussian-filter overlap formula and all three spectral anchors were independently reproduced.
- `e_d' = e_d + m - 2 e_d m` is the correct independent-flip XOR composition under the declared model.
- Gate/filter acceptance belongs before `run_decoy_bb84`; misalignment belongs in the channel copy's `intrinsic_qber`. This preserves both certified base laws.
- Applying the two acceptance factors to `eta_base` before each PDT node is correct because they are deterministic per sample and independent of the fading node.
- `doppler_residual_fraction` should be a control.
- `source_linewidth_sigma_hz` may remain receiver-assumed for LINK-6b, with the ownership debt recorded and replayed.
- Bumping the manifest to v2 while retaining strict v1 replay is preferable to an optional-key schema.
- `JITTER_LEAK_TOLERANCE = 1e-9` is reasonable and consistent with the PDT tail convention.
- `bb84.py` and `link.py` can remain untouched.

## LINK-6c candidate

The follow-up is directionally right but should remain a candidate, not a frozen formula, until its own plan resolves two ownership questions:

1. Decide whether the new observable is already-collected **background rate spectral density** or upstream **spectral radiance**. If aperture and FOV are still to be applied, radiance-like units (`photons s^-1 m^-2 sr^-1 Hz^-1`) are the honest upstream quantity; calling it an incident rate density while also multiplying by aperture/FOV risks double ownership.
2. Model the FOV's signal-acceptance cost against pointing/spot statistics as well as its background benefit. Otherwise LINK-6c would repeat the same half-trade it is meant to repair: a narrower FOV would reduce background for free.

Retaining `background_rate_hz` as a mutually exclusive measured, post-filter override is sound. The Gaussian spectral integral is sound only under a locally flat spectral-density assumption, which the LINK-6c plan should state and test. Sequencing LINK-6c before any filter/background advantage benchmark remains the right recommendation.

## Required v1.2 gate

Return the revised plan for re-review before dispatch. The next version should:

1. correct the shared-afterpulse invariants and tests;
2. close filter/source-linewidth activation and validation;
3. define strict v1/v2 replay compatibility;
4. complete the exact §7 test/helper enumeration and preserve old constructors with identity defaults;
5. correct the phase-effect domain;
6. resolve or defer the benchmark-harness change in the file inventory;
7. reconcile the ADR feasibility wording;
8. keep LINK-6c explicitly provisional with the radiance/FOV signal-cost questions recorded.

No implementation files or tests were modified during this review. The current suite was not rerun because the implementation baseline is unchanged; certification counts belong to the eventual implementation gates.
