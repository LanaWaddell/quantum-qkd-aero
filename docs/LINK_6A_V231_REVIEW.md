# LINK-6a v2.3.1 Brief Confirmation Review

**Date:** 2026-08-17

**Plan reviewed:** `docs/LINK_6A_PLAN.md`

**Plan SHA-256:** `8997158932336649caec83bf16a7236d8e022bde4c30ff9ecb692f707335eebd`

**Prior review:** `docs/LINK_6A_V23_REVIEW.md` (`a308c9cf23b45bc5b343482e981dec9cba8fa1143f6331a4c82e0639f6a52708`)

## Disposition

**Approved for implementation through Gates A-D, subject to Lana's explicit dispatch authorization.**

The two required v2.3.1 corrections are complete. I found no remaining physics, architecture, replay-contract, provenance, or test-contract blocker in this review. This approval does not itself authorize implementation.

## Confirmation

### F1 - provenance semantics

Confirmed. Appendix A.4 now tags only the two computed receiver arrays as `SIMULATED`; `pi.*` and `units.*` are `ILLUSTRATIVE`. This matches the live mission provenance convention, where configured intensities are illustrative. The plan also requires both an exact project-specific map assertion and a negative `pi`-as-`SIMULATED` test, closing the gap left by the generic validator's coverage-only behavior.

### F2 - closed-world replay manifest

Confirmed. Appendix A.2 now enumerates the manifest at every nested level and assigns each calibrated value one owner. In particular, `receiver` contains only `pi` and `operating_convention`; afterpulse probability and dead time remain solely in their ordered effect specifications.

The enumerated live-tree bindings were checked directly:

- all ten `MissionConfig` constructor fields match A.2.1;
- all seven resolved `DEFAULT_ATMOSPHERE` keys match A.2.1;
- all three `DetectorParams` fields are represented;
- `sky_condition` matches the live `night`, `twilight`, and `day` vocabulary;
- every existing registered effect's listed `param_keys` matches its `init=True` dataclass fields.

The two new rate-owner effects have equally explicit one-key codec contracts, and the required codec/dataclass anti-drift test will keep the registry synchronized as implementation evolves. Introducing `LINK_PIPELINE_VERSION = "link-6a.1"` gives the manifest an explicit pipeline-semantic version without conflating it with results schema version `2.0`.

### Review cleanups

Confirmed:

- availability is `A` in sampled mode and `E_f[A(f)]` in PDT mode;
- required `ReceiverBlockResult` fields are separated from optional trailing result additions;
- the future receiver-aware Eve work must promote one canonical helper or use the public Eve pipeline, never add a third anomaly formula;
- Appendix A is labeled for v2.3.1.

## Gate conditions retained

Implementation should proceed in the plan's Gate A-D order. The approved detector-copy reuse route, law-effect-last PDT rule, receiver/Eve exclusion for LINK-6a, closed-world replay validation, default-path byte identity, and full environment-split test certification remain binding.

No source files or tests were changed during this confirmation review, and the full suite was not rerun because the repository baseline is unchanged; implementation must produce the real certification counts required by the plan.
