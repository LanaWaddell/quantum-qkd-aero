# Schema Validator Hardening — Phase 2B Work-Package

**Status:** specification, queued. **Do NOT implement during Phase 2A.**
**Phase tag:** `[2B]` — lands *with* the `outputs/results.json` v1→v2.0 emission switchover.
**Relationship to `INTERFACES.md`:** subordinate. `INTERFACES.md` §5 remains the
canonical contract for the schema **shape**. This document specifies validation
**behaviour** only — it adds nothing to the shape and must not redefine it. If a
field name or section here ever disagrees with `INTERFACES.md` §5, `INTERFACES.md`
wins and this doc is the bug.

---

## 0. Why this exists

The Phase 2A validator (`src/qkd/schema.py`) is a **recognizer, not a guard.**
`_require_sections` checks that required key *names* are present and that sections
are mappings. It never inspects values. Under the 2A validator, every one of these
**passes**:

```
werner_p: 5.0          (impossible — p ∈ [0,1])
qber: -3               (impossible — a probability)
transmittance: "banana" (wrong type)
fidelity: NaN          (computation failed upstream)
gains: 0.0             (should be a {signal,decoy,vacuum} mapping)
margin: 0.0  while fidelity: 0.95, classical_bound: 0.6667   (internally inconsistent)
```

For 2A that is correct and in-scope: the job there is *"which schema is this?"*
But the moment 2B flips emission to v2.0, the v2.0 promise is **honest physics**,
and a physically-impossible or internally-inconsistent payload must be a **hard
error**, not silently accepted. This work-package closes that gap.

It also closes the test gap flagged in review: 2A proves *"accepts good v2.0"* and
*"rejects total garbage"*, but never *"rejects almost-good v2.0"* — the near-miss
case (a real run that dropped a field) that will actually occur in 2B.

---

## 1. Validation layers (v2.0 only)

v1 is the deprecated toy schema and is **not** hardened — it is going away at the
switchover, so spending validation effort on it is wasted. v2.0 gets five layers,
applied in order; the first failure raises `SchemaValidationError`.

| Layer | What it checks | Status |
|-------|----------------|--------|
| **L1 Structural** | required sections + keys present (mappings) | exists in 2A — keep |
| **L2 Types** | each field is the right type; reject `NaN`/`inf` | **new** |
| **L3 Ranges** | each numeric field within physical bounds | **new** |
| **L4 Constants** | stored constant fields ≈ their true values | **new** |
| **L5 Consistency** | derived/duplicated fields agree with their sources | **new** |

L5 is the highest-value layer — it catches the "wired up wrong" class of bug
(e.g. `mission.py` populating `physics_signals` inconsistently with the section it
was derived from). That is exactly the integration failure 2C could introduce, and
it is invisible to L1–L4.

---

## 2. API — backward-compatible additions

Keep the 2A public surface. Add a `deep` switch.

```python
class SchemaValidationError(ValueError): ...        # unchanged

def detect_results_schema(results) -> str: ...      # unchanged — recognition only (L1)

def validate_results_schema(results, *, deep: bool = True) -> bool:
    """
    L1 always. For schema "2.0" with deep=True, ALSO run L2–L5.
    For schema "1", deep is ignored (toy schema, structural only).
    deep defaults True so the v2.0 switchover gets hardening automatically;
    deep=False preserves pure-recognition behaviour for callers that only
    need to route by version.
    """

def load_results(path, *, deep: bool = True) -> dict: ...   # add deep, default True
```

Private helpers (one per layer), each raising `SchemaValidationError` on the first
violation with a message naming the field and the rule:
`_validate_types`, `_validate_ranges`, `_validate_constants`, `_validate_consistency`.

---

## 3. L2 — Types

- floats where float (all physics quantities); `int` for `sifted_key_length`;
  `bool` for `beats_classical`, `violates`, `eve_enabled`; `str | None` for
  `eve_type`; `Mapping` for `gains`.
- **Reject `NaN` and `inf` explicitly** (`math.isnan` / `math.isinf`). A NaN
  fidelity from a failed upstream computation must hard-fail here, not slip into a
  dashboard as a blank. This is the single most important type check, because numpy
  produces NaN/inf silently.

## 4. L3 — Ranges

Hard physical bounds. Use the **general** bound (not the Werner-model-specific
sub-range) so the validator stays correct even if 2B later uses a non-Werner
channel model.

| Field | Bound | Note |
|-------|-------|------|
| `channel.transmittance` | `[0, 1]` | η |
| `channel.werner_p` | `[0, 1]` | p |
| `channel.intrinsic_qber` | `[0, 0.5]` | e_d |
| `bb84.qber` | `[0, 0.5]` | beyond 0.5 you relabel bases |
| `bb84.gains.{signal,decoy,vacuum}` | `[0, 1]` each | detection prob/pulse |
| `bb84.y1_lower_bound` | `[0, 1]` | single-photon yield |
| `bb84.e1_upper_bound` | `[0, 0.5]` | single-photon error |
| `bb84.secure_key_rate` | `[0, 1]` | bits/pulse; `>1` unphysical, `<0`→clamp to 0 upstream |
| `bb84.sifted_key_length` | integer `>= 0` | |
| `bb84.decoy_anomaly_score` | `>= 0` | no hard upper bound by construction |
| `teleportation.fidelity` | `[0, 1]` | Werner model emits `[0.5, 1]` |
| `teleportation.singlet_fraction` | `[0, 1]` | Werner model emits `[0.25, 1]` |
| `chsh.S` | `[0, 2√2]` | Tsirelson cap (+float tol) |

Margins (`teleportation.margin`, `chsh.margin`, `physics_signals.*_margin`) are
**not** range-checked directly — they are verified in L5 against their definitions,
which is stronger.

## 5. L4 — Constants

Some fields are fixed constants in the schema. Verify they ≈ the true value, so a
payload that fabricated a wrong bound is caught.

| Field | True value |
|-------|-----------|
| `teleportation.classical_bound` | `2/3` |
| `chsh.classical_bound` | `2.0` |
| `chsh.tsirelson_bound` | `2√2` |

**Rounding subtlety — read this, it will otherwise cost an afternoon.** The
`INTERFACES.md` §5 example shows these rounded (`0.6667`, `2.8284`). `0.6667`
differs from true `2/3` by `3.3e-5`. So the L4 tolerance must be **looser than
the rounding error**: use `CONST_ATOL = 1e-3`. Recommendation: **2B should emit
full precision** (`0.6666666666666666`, `2.8284271247461903`); the validator
tolerates either via `CONST_ATOL`. For all *inequality* and *derived* checks (L5),
the validator must use the **true** constants internally (`2/3`, `2.0`,
`2*math.sqrt(2)`), never the rounded stored values.

## 6. L5 — Consistency

Tolerance `ATOL = 1e-6` (these compare full-precision computed values, so they can
be tight). Use `math.isclose(a, b, abs_tol=ATOL)`.

```
C1   teleportation.margin        ≈ fidelity - (2/3)
C2   teleportation.beats_classical == (fidelity > 2/3)        # true constant, not stored
C3   chsh.margin                 ≈ S - 2.0
C4   chsh.violates               == (S > 2.0)
C5   physics_signals.qber                 ≈ bb84.qber
C6   physics_signals.decoy_anomaly_score  ≈ bb84.decoy_anomaly_score
C7   physics_signals.secure_key_rate      ≈ bb84.secure_key_rate
C8   physics_signals.teleportation_margin ≈ teleportation.margin
C9   physics_signals.chsh_margin          ≈ chsh.margin
C10  physics_signals.loss_rate            ≈ 1 - channel.transmittance
```

**Boundary caution on C2/C4:** when `fidelity` is *exactly* `2/3` or `S` is exactly
`2.0`, the strict `>` makes `beats_classical`/`violates` `False`. That is the
physically correct convention (you must *beat* the bound, not tie it), so emission
and validation must agree on strict `>`. Document it so it is not "fixed" later by
someone who assumes `>=`.

---

## 7. Golden valid sample

The hardened tests need a payload that passes **all five layers** — a real,
internally-consistent v2.0 example. Values below are computed from the analytic
contract at `p = 0.9`, `η = 0.5`, honest channel (`decoy_anomaly_score = 0`).
Float values are shown full-precision; tests should compare with `math.isclose`.

```python
GOLDEN_V2 = {
    "schema_version": "2.0",
    "run_metadata": {"timestamp": "2026-05-31T12:00:00Z", "config_hash": "golden",
                     "eve_enabled": False, "eve_type": None},
    "channel": {"transmittance": 0.5, "werner_p": 0.9, "intrinsic_qber": 0.02,
                "slant_range_km": 1200.0, "elevation_deg": 30.0},
    "bb84": {"sifted_key_length": 500, "qber": 0.02,
             "gains": {"signal": 0.02, "decoy": 0.01, "vacuum": 0.0001},
             "y1_lower_bound": 0.015, "e1_upper_bound": 0.025,
             "secure_key_rate": 0.005, "decoy_anomaly_score": 0.0},
    "teleportation": {"fidelity": 0.95, "singlet_fraction": 0.925,
                      "classical_bound": 0.6666666666666666,
                      "beats_classical": True, "margin": 0.2833333333333333},
    "chsh": {"S": 2.545584412271571, "classical_bound": 2.0,
             "tsirelson_bound": 2.8284271247461903,
             "violates": True, "margin": 0.5455844122715711},
    "physics_signals": {"qber": 0.02, "decoy_anomaly_score": 0.0,
                        "chsh_margin": 0.5455844122715711,
                        "teleportation_margin": 0.2833333333333333,
                        "loss_rate": 0.5, "secure_key_rate": 0.005},
}
# Derivations (so the numbers are auditable, not magic):
#   fidelity         = (1 + 0.9)/2                 = 0.95
#   singlet_fraction = (1 + 3*0.9)/4               = 0.925
#   tel margin       = 0.95 - 2/3                  = 0.2833333333333333
#   S                = 2*sqrt(2)*0.9               = 2.545584412271571
#   chsh margin      = 2.545584412271571 - 2.0     = 0.5455844122715711
#   loss_rate        = 1 - 0.5                     = 0.5
```

---

## 8. Required test changes — **this breaks a green 2A test, by design**

> **The sharp edge.** The existing 2A test
> `test_schema_validator_accepts_future_v2_contract_shape` feeds an **all-zero**
> v2.0 sample and asserts `validate_results_schema(...) is True`. With L5 on and
> `deep=True` default, that sample now **fails** — its margins are zero while its
> fidelity/S/transmittance are zero (C1 wants `margin ≈ 0 - 2/3 = -0.6667`, C10
> wants `loss_rate ≈ 1 - 0 = 1`, etc.), so it is internally inconsistent. That
> failure is **correct**: the all-zero placeholder was valid for *recognition*
> (2A) but cannot survive *correctness* (2B). It must be migrated in the **same
> PR** that lands this hardening, or the suite goes red.

Migration — split the one 2A test into two:

```python
# (a) recognition only — keep the cheap all-zero shape, but assert via deep=False
def test_schema_recognizes_minimal_v2_shape():
    assert detect_results_schema(ALL_ZERO_V2) == "2.0"
    assert validate_results_schema(ALL_ZERO_V2, deep=False) is True   # L1 only

# (b) correctness — the golden sample, full deep validation
def test_schema_deep_validates_golden_v2():
    assert validate_results_schema(GOLDEN_V2, deep=True) is True      # L1–L5
```

New negative tests (each asserts `pytest.raises(SchemaValidationError)`), built by
mutating a copy of `GOLDEN_V2`:

```
test_rejects_out_of_range_werner_p        werner_p = 1.4
test_rejects_out_of_range_qber            bb84.qber = -0.01
test_rejects_nan_fidelity                 teleportation.fidelity = float("nan")
test_rejects_inf_value                    chsh.S = float("inf")
test_rejects_wrong_type_gains             bb84.gains = 0.0          # not a mapping
test_rejects_wrong_constant               teleportation.classical_bound = 0.5
test_rejects_inconsistent_margin          teleportation.margin = 0.0   # C1 fails
test_rejects_inconsistent_loss_rate       physics_signals.loss_rate = 0.9  # C10 fails
test_rejects_near_miss_missing_section    del payload["chsh"]       # THE flagged gap
test_rejects_near_miss_missing_key        del payload["bb84"]["decoy_anomaly_score"]
test_deep_false_skips_value_checks        GOLDEN with werner_p=1.4, deep=False → True
test_v1_path_unaffected_by_deep_flag      v1 sample, deep=True → True (L1 only)
```

`test_rejects_near_miss_missing_section` and `_missing_key` are the specific cases
2A could not cover; they exercise the rejection path L1 already has but never tested.

---

## 9. `schema.py` TODO markers (drop in NOW, during 2A is fine)

Documentation-only — no behaviour change, so safe to add even though implementation
is 2B. Put these in `src/qkd/schema.py` so whoever flips emission sees the gap where
it lives, not only in this doc:

```python
# TODO(2B): This validator is a RECOGNIZER, not a GUARD. It checks key presence
#   only (L1). Before flipping outputs/results.json emission to v2.0, implement
#   L2 types (+reject NaN/inf), L3 ranges, L4 constants, L5 cross-field
#   consistency, per docs/SCHEMA_HARDENING_2B.md. Landing that hardening will
#   intentionally break test_schema_validator_accepts_future_v2_contract_shape
#   (all-zero sample is inconsistent under L5) — migrate it per §8 in the same PR.
```

---

## 10. Out of scope

- v1 hardening (deprecated; removed at switchover).
- JSON Schema / pydantic migration — possible later refactor; this spec is plain
  Python to match the existing module. If you adopt pydantic in 2B, the L2–L5
  *rules* above transfer directly to validators/field constraints.
- Trust/coherence field validation — those fields do not exist until `[2D]`; when
  they do, extend L3/L5 here rather than starting a new doc.
