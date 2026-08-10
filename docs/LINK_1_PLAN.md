# LINK-1 PR Plan — Types, Protocols, Identity Behaviour, Tests

**Status:** **v2 — APPROVED FOR IMPLEMENTATION** (PI approval of Option A with R2 shape, 2026-08-10; Echo review R1–R5 incorporated; v1 draft superseded)
**Date:** 2026-08-10
**Governing ADR:** ADR-0003 (RATIFIED 2026-07-17), acceptance criteria §7.1
**Review record:** Echo review 2026-08-10 (disposition: approve after targeted revision) — all five required revisions (R1–R5), bridge guards, validation contracts, and acceptance-test amendments incorporated below. R4's factual claims verified against baseline (`run_metadata` strictly key-validated: `generator`/`pipeline`/`physics_mode` [+ `max_secure_distance_definition` fibre-side]; no controls field).
**Baseline:** commit `03736da` (main), certified 2026-08-10 — suite green (142+1 base / 163 w/ qiskit), emissions deterministic (`docs/notes/NOTE-sequencing-2026-08-10.md` §1.2)

**Disposition (binding summary).** LINK-1 introduces the typed link-effect contracts, an exact table-backed geometry wrapper, a deterministic and collision-checked evaluation context, composition with fail-loud deferred boundaries, control validation plus a canonical audit record, and an opt-in mission bridge for the two already-representable multiplicative factors. It introduces **no** real stochastic physics, detector dynamics, estimator changes, or default-output changes. Emitted control-audit integration remains a hard prerequisite for the first production controlled effect (declared optional schema extension at that stage — not now).

---

## 1. Deferred-rule discharge (formal adoption at LINK-1, per ADR status log)

ADR-0003 ratified with two §3.3.1 rules deliberately deferred to LINK-1, evidence recorded in `docs/references/quantum-qkd-aero-adr0003-evidence-memo-timebin-review.md`. LINK-1 adopts them, with the R3 fail-loud boundary:

1. **`timing_jitter_s`: independent scalar contributions compose in quadrature** (√Σσ²). Evidence anchor: Singh et al. 2507.08102 Eq. 28. A contribution declared *correlated* is *not* silently composed and does *not* "route around" quadrature — it raises `UnsupportedCorrelatedCompositionError` until a typed correlated-state representation is introduced at the stage that earns it (LINK-4+). Same rule for a declared-correlated `background_rate_hz` contribution.
2. **`misalignment_error`: zero or one nonzero contributor** in LINK-1; a second nonzero contributor raises. **sin²(Δϕ)** is documented as the DV time-bin *mapping used by a future effect/estimator* — not as a stack combiner over already-resolved probabilities (multiple probability contributions cannot be combined by reconstructing phase offsets). Estimator-owned combination is deferred with the same fail-loud boundary.

## 2. Module layout

```
src/qkd/link.py          # contracts + runtime implementation only (~400 LOC)
tests/test_link.py       # acceptance + unit tests, incl. all mock effects (~550 LOC)
```

Test-only effects (`IdentityEffect`, `MultiplicativeMockEffect`, `ControlledMockEffect`, `StochasticMockEffect`) live in `tests/` — the production module ships contracts and runtime only. No `schema.py` changes (§7). One bounded opt-in seam in `mission.py` (§5).

## 3. Types and Protocols (ADR §3 shapes + R1 evaluation context)

```python
@dataclass(frozen=True)
class PassGeometry:
    t_s: float
    elevation_deg: float | None       # None for non-satellite media (decision 4)
    slant_range_km: float | None
    radial_velocity_mps: float | None = None

class GeometryProvider(Protocol):
    def at(self, t: float) -> PassGeometry: ...

@dataclass(frozen=True)
class ChannelObservables:    # → ChannelState territory
    transmittance_factor: float = 1.0
    background_rate_hz: float = 0.0
    misalignment_error: float = 0.0
    frequency_offset_hz: float = 0.0
    timing_jitter_s: float = 0.0

@dataclass(frozen=True)
class DetectorObservables:   # → DetectorParams territory
    efficiency_factor: float = 1.0
    dark_count_rate_hz: float = 0.0
    afterpulse_prob: float = 0.0
    dead_time_s: float = 0.0

@dataclass(frozen=True)
class LinkObservables:
    channel: ChannelObservables = ChannelObservables()
    detector: DetectorObservables = DetectorObservables()

@dataclass(frozen=True)
class EffectEvaluationContext:            # R1: the explicit path for controls + RNG
    controls: Mapping[str, float]         # values in force for THIS evaluation
    sample_index: int | None              # explicit index; stable replay identity
    rng_for: Callable[[str, int | None], np.random.Generator]
                                          # (purpose, index) → stack-derived stream

class ChannelEffect(Protocol):
    effect_id: str                        # nonempty, stable, unique in a stack (R5)
    def evaluate(self, t: float, geom: PassGeometry, *,
                 context: EffectEvaluationContext) -> LinkObservables: ...

@dataclass(frozen=True)
class ControlSpec:
    name: str                             # nonempty; doubles as the constraint id
    unit: str
    bounds: tuple[float, float]           # finite, lower <= upper
    description: str = ""                 # stable human-readable constraint text (R-detail)
    feasible: Callable[["EffectiveLinkState"], tuple[float, float]] | None = None

class Controllable(Protocol):
    def controls(self) -> tuple[ControlSpec, ...]: ...

@dataclass(frozen=True)
class EffectiveLinkState:
    """Composed physical state at t — construction bridge (decision 2), not a sibling API."""
    channel: ChannelObservables
    detector: DetectorObservables
```

**R1 invariants (binding):** control values are explicit per evaluation; the *stack* derives RNG streams, never the effect; stream purpose and sample/block index are explicit; repeated or out-of-order evaluation of the same indexed sample yields the same result; no effect holds mutable RNG state between calls. Evaluation is fully determined by `(t, geom, fixed_config, control_values, rng_stream)` per ADR §3.6.

## 4. Composition rules implemented (§3.3.1, binding, with R3 boundaries)

| Field | LINK-1 behaviour |
|---|---|
| `transmittance_factor` | product |
| `background_rate_hz` | sum of independent scalars; declared-correlated contribution → `UnsupportedCorrelatedCompositionError` |
| `frequency_offset_hz` | sum |
| `timing_jitter_s` | quadrature over independent scalars; declared-correlated → `UnsupportedCorrelatedCompositionError` |
| `misalignment_error` | ≤ 1 nonzero contributor; second nonzero contributor raises. sin²(Δϕ) documented as future DV time-bin mapping, not a combiner |
| `efficiency_factor` | product, folded exactly once (single-fold guard extended) |
| `dark_count_rate_hz` | sum |
| `afterpulse_prob` | single-contributor policy: second nonzero contributor raises |
| `dead_time_s` | single-contributor policy: second nonzero contributor raises |

**Observable validation (pre-composition, fail-loud):** every effect output is checked before composing — `transmittance_factor`, `efficiency_factor`, `misalignment_error`, `afterpulse_prob` finite and in [0, 1]; `background_rate_hz`, `dark_count_rate_hz`, `timing_jitter_s`, `dead_time_s` finite and ≥ 0; `frequency_offset_hz` finite. A malformed effect must not create negative rates or a channel-improving factor > 1.

## 5. Integration seam — Option A, R2 shape (PI-approved)

`simulate_pass` owns geometry; the stack wraps **the exact pass the mission generated**:

1. `simulate_pass` constructs its `SatellitePass` exactly as today.
2. If link effects were requested, it wraps *that same object* in `TableGeometryProvider` and constructs the stack from it.
3. The stack is evaluated at the existing pass sample times (explicit `sample_index` per sample).
4. `MissionConfig` is **not** touched — it stays serializable mission input translated by `_mission_inputs()`. The seam is opt-in keyword arguments on `simulate_pass`:

```python
def simulate_pass(config=None, *, eve=None,
                  link_effects: Sequence[ChannelEffect] | None = None,
                  link_seed: int | None = None,
                  link_controls: Mapping[str, float] | None = None) -> PassResult:
```

`link_effects=None` (default) takes the *untouched* baseline code path — no provider, no stack, no bridge. **Invariant test:** the provider used by the stack wraps the same `SatellitePass` instance/values used to populate the result geometry.

**Bridge (`apply_link_state`) guards (binding):**

- Folds exactly two fields: `transmittance_factor` into `ChannelState.transmittance` (base state built first, then only transmittance replaced) and `efficiency_factor` into the supplied detector's `detection_efficiency` (only that field replaced). Resulting values validated physical (∈ [0, 1]).
- **Any other non-identity observable raises** `UnsupportedLinkObservableError` naming the field — nothing is silently dropped. `background_rate_hz`, `dark_count_rate_hz` (no defined gate window yet), `misalignment_error`, `frequency_offset_hz`, `timing_jitter_s`, `afterpulse_prob`, `dead_time_s` are all unrepresentable in the current estimator path and therefore rejected at the bridge until their integration stage.

Zero-behaviour-change holds because: `None` → untouched path; empty/identity stacks wrap the mission's own pass; only the two representable factors reach the bridge; everything else fails loudly; and the three real emitted payloads are byte-identical and schema-valid (§8).

## 6. Stochastic reproducibility (§3.4 + R5)

Stack-owned child streams, canonical encoding, collision-checked identities:

```python
def _child_rng(run_seed: int, effect_id: str, purpose: str,
               index: int | None = None) -> np.random.Generator:
    payload = json.dumps([run_seed, effect_id, purpose, index],
                         ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.blake2b(payload, digest_size=16).digest()   # 128-bit
    return np.random.default_rng(int.from_bytes(digest, "big"))
```

- Canonical JSON list encoding — delimiter-ambiguity impossible (colons in `effect_id`/`purpose` cannot collide distinct tuples). Never Python `hash()` (process-salted).
- **Construction-time identity rules (R5):** every `effect_id` nonempty and stable; duplicate `effect_id`s rejected (including two instances of the same effect type); every declared control name nonempty and unique across the assembled registry; duplicate control declarations fail loudly.
- **Seed rule:** stochastic evaluation requires a resolved integer `link_seed`; `seed=None` is accepted only for a wholly deterministic stack (any effect requesting `rng_for` with `seed=None` raises).
- Order-independence holds by construction: derivation never references registration order. Exposed to effects only via `context.rng_for(purpose, index)`.

## 7. Controls: registry, validation, and audit (decision 5 + R4)

**Registry (decision 5 — mirror, don't share).** The stack assembles a central registry from each effect's `controls()` declarations at construction — same declared-or-fail semantics as `schema.py`'s `DECLARED_SCHEMA_EXTENSIONS`, deliberately *not* the same object (schema registry validates emitted artifacts, import-light; controls registry is live runtime state carrying feasibility callables reading `EffectiveLinkState`). Correspondence documented in both docstrings.

**Validation (binding):** control values finite; undeclared name → `UndeclaredControlError`; outside static bounds → error naming the `ControlSpec` (name + description); feasibility bound = intersection of static bounds and `feasible(state)` result; **empty intersection → error naming the control and both intervals** (never silently clamped, ADR §7.6); violations of the state-dependent bound name the control and its description.

**Audit (R4 — bounded LINK-1 disposition, verified against baseline).** The baseline `run_metadata` carries only `generator`/`pipeline`/`physics_mode` (strictly key-validated); there is no existing controls path to emission, and LINK-1 claims none. Instead: the stack produces a **canonical serializable audit record** (sorted-key JSON of controls in force + `link_seed` + effect ids) available to callers, byte-stable for identical inputs. No controlled production effect exists in LINK-1 and no controlled run is emitted. **Hard prerequisite recorded:** the first production controlled effect must land the declared optional schema extension (a `DECLARED_SCHEMA_EXTENSIONS` entry) consuming this record — emission auditability is a guarded future integration seam, not complete now.

## 8. `TableGeometryProvider` contract

Wraps the existing `orbit.SatellitePass` (ratification decision 1: WRAP). Binding contract: equal nonzero column lengths; strictly increasing, finite `time_s`; finite stored geometry; **columns snapshotted to tuples at construction** (the dataclass is frozen but its lists are mutable); linear interpolation between samples with **exact stored-value return at exact sample times** (byte-identity depends on this); out-of-domain query → exception, never silent extrapolation; interpolated results carry `PassGeometry.t_s == requested_t`.

## 9. Acceptance tests (§7.1 + Echo amendments)

Core (mapping §7.1):

| # | Test | Criterion |
|---|---|---|
| 1 | `test_none_empty_identity_paths_byte_identical` — three paths through the **real `run._build_results()` emission builder**; compare canonical serialized bytes; **every compared payload also passes `validate_results_schema(deep=True)`** | §7.1-1 |
| 2 | `test_multiplicative_effect_scales_transmittance_exactly_once` (hand-computed) | §7.1-2 |
| 3 | `test_detector_efficiency_folds_exactly_once` | §7.1-3 |
| 4 | `test_undeclared_runtime_control_rejected` | §7.1-4 |
| 5 | `test_out_of_bounds_control_rejected_names_spec` (name + description) | §7.1-5 |
| 6 | `test_infeasible_control_rejected_named_not_clamped` + empty-intersection case | §7.1-5/§7.6 |
| 7 | `test_fixed_seed_replay_deterministic` | §7.1-6 |
| 8 | `test_effect_reorder_insert_remove_leaves_unrelated_streams_unchanged` | §7.1-6 |

Amendments (Echo review):

| # | Test |
|---|---|
| 9 | `test_fresh_stack_instances_same_seed_identical` (independent constructions) |
| 10 | `test_indexed_samples_replay_under_different_call_orders` |
| 11 | `test_duplicate_effect_id_rejected` (incl. two instances of one type) |
| 12 | `test_duplicate_control_name_rejected` |
| 13 | `test_canonical_key_no_collision_with_separator_characters` (ids/purposes containing `:` etc.) |
| 14 | `test_bridge_rejects_unsupported_nonidentity_observable` (nothing silently dropped) |
| 15 | `test_correlated_contribution_raises_unsupported_error` (jitter + background) |
| 16 | `test_misalignment_second_contributor_rejected`; `test_afterpulse_deadtime_second_contributor_rejected` |
| 17 | `test_invalid_observables_rejected` (parameterized: NaN, ±inf, negative rates/times, factors/probabilities outside [0,1]) |
| 18 | `test_geometry_table_validation_and_out_of_domain_query` |
| 19 | `test_geometry_provider_exact_at_sample_times` + snapshot immunity to post-construction list mutation |
| 20 | `test_stack_provider_wraps_mission_pass` (R2 invariant) |
| 21 | `test_jitter_quadrature_composition` |
| 22 | `test_control_audit_record_byte_stable` |
| 23 | `test_seed_none_rejected_for_stochastic_stack` |

Plus: full existing suite green (regression). The frozen `link1-baseline-03736da` artifacts remain a separate per-environment regression tripwire; the acceptance proof is the in-process three-path comparison.

## 10. Risks and guards

- **Dual-geometry hazard**: eliminated by R2 (stack provider constructed inside `simulate_pass` from the mission's own pass; invariant test 20).
- **Silent observable loss**: eliminated by the bridge rejection guard (test 14) and pre-composition validation (test 17).
- **Interface leakage** (decision 4): `PassGeometry` fields optional; provider makes no satellite assumption; fibre decided later by interface pressure.
- **Hash/identity collisions**: canonical JSON encoding, 128-bit digest, construction-time duplicate rejection (tests 11–13).
- **Byte-identity environment-locality**: in-process three-path comparison through the real builder; no cross-machine fixture diffs.
- **Scope creep**: any physics beyond identity/mock effects is a review-blocking finding on this PR by definition.

## 11. Out of scope (explicit)

Doppler, pointing loss, scintillation, μ fluctuation, afterpulsing/dead-time physics (LINK-3/4/5); estimator integration of background, misalignment, frequency offset, jitter (LINK-6 — all bridge-rejected until then); correlated-state representations (stage that earns them); migrating existing constants into effects (LINK-2, byte-parity certified); fibre provider generalization (decision 4); any schema change including the controls extension (prerequisite of the first production controlled effect, not LINK-1); any Exp-1+ infrastructure.

## 12. Implementation record (2026-08-10)

Implemented by a Sonnet subagent per §12's hand-off design; reviewed top-tier against this plan. **Result: 219 passed** (163 baseline + 56 new from the 23 acceptance tests with parametrization); three-path byte-identity holds through the real `run._build_results()` builder with `deep=True` schema validation on every payload; default-path emission hash equals the frozen `link1-baseline-03736da` value (independently re-verified). Files: `src/qkd/link.py` (+728), `tests/test_link.py` (+827), `mission.py` (+79; `MissionConfig` untouched).

Two plan gaps surfaced and resolved during implementation (reviewed and accepted):

1. **Correlated-contribution declaration mechanism.** §3's `ChannelEffect` Protocol had no field for declaring a contribution correlated, though §4 requires the fail-loud boundary to trigger on such a declaration. Resolution: optional duck-typed `correlated_fields` attribute (iterable over `{"background_rate_hz", "timing_jitter_s"}`), mirroring how `Controllable` is already optional. Absent attribute ≡ empty. This is a §3 amendment by implementation, documented in `link.py`'s module docstring.
2. **Sample-varying detector efficiency.** `simulate_profile` takes one shared `DetectorParams` per pass, so a per-sample-varying `efficiency_factor` is unrepresentable without modifying `simulate_profile` (out of scope). Resolution: the seam folds per sample and **raises** if the folded efficiencies disagree across samples — fail-loud, never silently collapsed. Constant-factor effects (all of LINK-1's) never trigger it.

**Forward flag for LINK-4 (recorded, no action now):** the §4 validation bound `transmittance_factor ∈ [0, 1]` is correct for LINK-1–3, but a scintillation effect implementing the channel-dynamics spec's η_turb (lognormal, E[η_turb] = 1) has instantaneous values > 1 by construction. LINK-4 must revisit this bound (likely: factor finite ≥ 0 at the stack, with composed total η ≤ 1 enforced at the bridge/state construction) — an explicit design item for that PR, not a silent relaxation.

## 13. Execution note

Implementable by a mid-tier model session: all design decisions are made here (R1–R5 resolved; no architecture left to invent at the keyboard). Work the sections in order §3 → §4 → §6 → §7 → §8 → §5 → §9. Certify with full suite + test 1 in the implementing environment before merge.
