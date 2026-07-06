# PR-D Schema Hardening — Active v2 Contract

**Status:** implemented in PR-D.

This document supersedes the field-level content of
`docs/SCHEMA_HARDENING_2B.md` for the current axis-agnostic v2 artifact. The
older document remains historical context for the five-layer validator design
and public API shape.

## API

```python
def detect_results_schema(results) -> str
def validate_results_schema(results, *, deep: bool = True) -> bool
def load_results(path, *, deep: bool = True) -> dict
```

`detect_results_schema(...)` is L1 recognition only. `validate_results_schema`
with `deep=True` runs L1 structural recognition, L2 types, L3 ranges, L4
constants, L5 cross-field consistency, and then `validate_provenance(...)`.
`deep=False` preserves pure recognition for tests or routing code.

There is no v1 branch. v1 emission was retired at the PR-B cutover.

## L2 Types

- Strings: `schema_version`, `link.*`, `profile.axis.name`,
  `mission.sky_condition`, `summary.*`, `run_metadata.*`, and
  `teleportation.plot`.
- `teleportation.frames`: integer, later range-checked as `>= 1`.
- Numeric scalars and array elements must be finite real numbers. `NaN` and
  `inf` are hard failures.
- All `profile` arrays and `profile.axis.values` must have equal, nonzero
  length. When `geometry` is present, its arrays must have the same length.
- Mapping sections must remain mappings: `profile.aggregates`,
  `mission.intensities`, `mission.detector`, optional `mission.fibre`,
  optional `geometry.min_loss`, and `provenance`.

## L3 Ranges And Vocabulary

Named vocabulary constants:

- `link.medium`: `atmospheric`, `fibre`
- `link.topology`: `point_to_point`
- `link.protocol`: `decoy_bb84`
- `profile.axis.name`: `time_s`, `length_km`

Range checks:

- `profile.transmittance[i]`: `[0, 1]`
- `profile.loss_db[i]`: `>= 0`
- `profile.secure_key_rate_per_pulse[i]`: `[0, 1]`
- `profile.effective_werner_p[i]`: `[0, 1]`
- `profile.fidelity[i]`: `[0, 1]`
- `teleportation.average_fidelity`: `[0, 1]`
- `profile.aggregates.min_loss_db`: `>= 0`
- `profile.aggregates.mean_fidelity`: `[0, 1]`
- `geometry.elevation_deg[i]`: `[0, 90]`
- `geometry.slant_range_km[i]`: `> 0`
- `mission.intensities`: `signal > decoy >= vacuum >= 0`
- `mission.detector.detection_efficiency`: `[0, 1]`
- `mission.detector.dark_count_prob`: `[0, 1]`
- `mission.detector.error_correction_efficiency`: `>= 1`
- `mission.pulse_repetition_rate_hz`: `> 0`

Dimensional rule:

- `profile.axis.name == "time_s"` requires
  `profile.aggregates.secure_key_yield_bits`.
- `profile.axis.name == "length_km"` forbids
  `profile.aggregates.secure_key_yield_bits`.

Fibre length sweeps use `max_secure_distance_km`, the
`secure_distance_bracket`, and the rate-distance curve as figures of merit.

## L4 Constants

`teleportation.classical_limit` is checked against the true value `2/3` with
`CONST_ATOL = 1e-3`, preserving the historical rounded-constant tolerance from
the older hardening spec.

## L5 Consistency

The validator checks algebra already encoded in the emitted artifact:

- `loss_db[i] ~= -10 * log10(transmittance[i])`
- `aggregates.min_loss_db ~= min(loss_db)`
- `aggregates.min_loss_axis_value ~= axis.values[argmin(loss_db)]`
- `aggregates.mean_fidelity ~= mean(fidelity)`
- `teleportation.average_fidelity` matches `aggregates.mean_fidelity` within
  `5e-4`, because the emitted duplicate is rounded to three decimals.
- For `time_s` axes only,
  `secure_key_yield_bits ~= sum(rate_i * f_rep * dt)`.
- For satellite payloads, `geometry.min_loss.*` matches the geometry arrays at
  `argmin(loss_db)`.
- For fibre payloads, `max_secure_distance_km` is the last axis value with
  positive `secure_key_rate_per_pulse`, and `secure_distance_bracket` records
  that sample plus the immediately following non-positive sample.
- For `run_metadata.physics_mode == "computed"`,
  `fidelity[i] ~= (1 + effective_werner_p[i]) / 2` under the current
  Werner-model emission.
- `teleportation.frames == len(profile.axis.values)`.

The validator deliberately does not recompute orbital mechanics, parse
headline presentation strings, or rerun protocol physics.

## Declared Extensions

`DECLARED_SCHEMA_EXTENSIONS: dict[str, set[str]]` allows future schema work to
declare extension keys by containing section path. Unknown top-level sections
and unknown keys inside known sections fail unless explicitly declared.

Declared extension leaves are still subject to provenance coverage when they
live under a provenance-covered data section.

## Test Coverage

PR-D adds golden satellite and fibre payloads, deep validation of both active
emission pipelines, `deep=False` recognition checks, declared-extension checks,
and mutation negatives for range, type, shape, constant, consistency,
dimensional, vocabulary, provenance, and near-miss missing-key failures.
