# Quantum-QKD-Aero — Module Interfaces (Phase 2)

**Status:** contract specification. Defines *interfaces*, not implementations.
**Audience:** Codex (implementation), Lana (PI), Claude/Echo (architecture).
**Rule for this document:** signatures, dataclasses, and behavioural contracts only.
No algorithm bodies. Physics is specified by its inputs, outputs, and the
constants its tests must satisfy — not by code here.

---

## 0. Phase legend

Every item below is tagged so implementation order stays clean:

| Tag | Phase | Meaning |
|-----|-------|---------|
| `[2A]` | Prepare the lab | Packaging, docs, test scaffolding, schema **definition** |
| `[2B]` | Calibrate the instruments | Real physics: fidelity, CHSH, decoy stats, Eve |
| `[2C]` | Orchestrate the mission | `mission.py` chains the calibrated modules |
| `[2D]` | Derive trust/coherence | Aggregate physics signals into trust — **not before 2B** |

**Codex implements `[2A]` only** in the current pass. `[2B]`/`[2C]`/`[2D]`
files may be *created as stubs with reserved names*, but their physics is
not written yet.

---

## 1. Core principle — two channel parameters, never one

The single most important design decision: the channel exposes **two
physically distinct quantities that must not be collapsed into one "channel
quality" number.**

| Symbol | Field | Governs | Feeds |
|--------|-------|---------|-------|
| **η** (transmittance) | `transmittance` | photon survival / loss | BB84, decoy, yields, gains |
| **p** (Werner parameter) | `werner_p` | entanglement quality | teleportation, CHSH |

Loss and decoherence are different effects. A channel can be lossy but
preserve entanglement, or low-loss but decohering. Keeping η and p separate is
what lets the photon-counting layer (BB84/decoy) and the entanglement layer
(teleportation/CHSH) report independent, honest signals.

The elegant consequence: **one `werner_p` analytically drives both
teleportation fidelity and CHSH**, so those two outputs stay physically coupled
through a single parameter instead of being independent decorative curves.

### 1.1 Ownership invariant

Every physical quantity has exactly one owner, is composed exactly once, and no
layer may silently absorb the responsibility of another. PR0 established the
artifact form of this rule: one authoritative production writer per generated
artifact. PR1 extends it to quantities: channel loss, detector efficiency,
mission opportunity, and control/policy choices must remain in their owning
layers and meet only at explicit composition points.

Layer glossary:

- **Physics** produces probabilities.
- **Hardware** converts arriving photons into measurements.
- **Mission** determines opportunity: orbit, pass geometry, weather, and run
  context.
- **Control/Policy** determines decisions such as filtering, optimization, and
  scheduling.

`ChannelState.transmittance` is a representation contract: it is the probability
that a photon launched at the transmitter aperture arrives at the receiver's
detection stage. It includes propagation/channel/optical losses up to the
detector face: geometric capture, atmospheric transmission, pointing, optical
path, and coupling. It excludes detector quantum efficiency, dead time, dark
counts, and timing; those belong to `DetectorParams`. End-to-end detection
efficiency is composed only at the point of use as
`transmittance * detector.detection_efficiency`.

The pulse repetition rate `f_rep` is a hardware-layer parameter, not a physical
constant. Phase 2B-6b uses the illustrative fixed value
`PULSE_REPETITION_RATE_HZ = 1.0e8` in `mission.py`. It is representative but not
calibrated, and it is intentionally held fixed during future optimization so an
optimizer cannot trivially improve yield by increasing the transmitter clock.

### 1.2 Provenance invariant

Provenance observes; it never causes. Provenance tags describe how emitted
quantities were produced, but they must not select algorithms, alter numerical
values, influence simulation state, or become physics inputs.

Operational tags:

- `ANALYTIC`: exact closed-form value.
- `SIMULATED`: direct output of a physics-model call.
- `DERIVED`: pure function of already-emitted values.
- `ILLUSTRATIVE`: named, uncalibrated constant or scenario input.
- `MEASURED`, `ESTIMATED`, and `VALIDATED`: reserved for later phases and not
  applied by the current simulator.

For current v1 emission, provenance is enforced over the data sections
`teleportation`, `summary`, `pass_profile`, and `mission`. Metadata blocks such
as `provenance` and `run_metadata` are not taggable data.

---

## 2. Dependency graph

```
ChannelModel ──► η  ──► BB84 + Decoy ──►(Eve injected here)──► QBER, gains, Y1, anomaly, key rate
             └──► p  ──┬► Teleportation ──► fidelity, singlet fraction, margin
                       └► CHSH          ──► S, violation, margin
                                  all outputs ──► PhysicsSignals  (collected, NOT scored)
                                                        │
                                                        ▼
                                                  [2D] trust/coherence  (later)
```

The wall between `[2B]` and `[2D]` is enforced at the type level:
`PhysicsSignals` contains **no trust or coherence field.** 2B produces it; 2D
consumes it. If a trust number ever appears inside a 2B module, that's the bug.

---

## 3. Shared data contracts

These dataclasses are the types that flow between modules. They are stable
contracts; module internals may change without touching them.

```python
# src/qkd/signals.py   [2A define dataclasses] [2B/2D populate]

from dataclasses import dataclass

@dataclass
class ChannelState:
    """Physical channel conditions, resolved to the two governing parameters."""
    transmittance: float          # η ∈ [0, 1]   arrival probability at detector stage
    werner_p: float               # p ∈ [0, 1]   1 = perfect Bell pair, 0 = maximally mixed
    intrinsic_qber: float         # e_d ∈ [0, 0.5]  optical misalignment — NOT caused by Eve
    dark_count_prob: float        # Y_0, per detection window
    # provenance (optional; for dashboard/report only, not physics inputs)
    slant_range_km: float | None = None
    elevation_deg: float | None = None


@dataclass
class DetectorParams:
    """Receiver-side parameters."""
    detection_efficiency: float   # η_d ∈ [0, 1]  (kept separate from channel η)
    dark_count_prob: float        # Y_0
    error_correction_efficiency: float = 1.16   # f(E) factor for key-rate formula


@dataclass
class PhysicsSignals:
    """
    The 2D-trust INPUT contract. Defined in 2A, populated in 2B, consumed in 2D.
    Deliberately contains NO trust/coherence field — that is the 2B/2D wall.
    """
    qber: float                   # visible disturbance (intercept-resend shows here)
    decoy_anomaly_score: float    # hidden-breach indicator (PNS shows HERE, not in qber); ≥ 0
    chsh_margin: float            # S - 2.0   (>0 ⇒ Bell violation)
    teleportation_margin: float   # F - 2/3   (>0 ⇒ beats classical)
    loss_rate: float              # 1 - η
    secure_key_rate: float        # bits per pulse
```

### Per-module result objects

```python
@dataclass
class BB84Result:                 # returned by bb84.run_bb84   [2B]
    sifted_key_length: int
    qber: float                                   # overall signal QBER, E_μ
    gains: dict[str, float]                       # {'signal','decoy','vacuum'} → gain Q
    qber_per_intensity: dict[str, float]
    y1_lower_bound: float                         # decoy estimate of single-photon yield Y1
    e1_upper_bound: float                         # decoy estimate of single-photon error e1
    q1: float                                     # single-photon gain contribution
    secure_key_rate: float                        # bits/pulse (asymptotic decoy bound)
    decoy_anomaly_score: float                    # ≥0; ~0 honest, grows under PNS

@dataclass
class TeleportationResult:         # returned by teleportation.teleportation_fidelity   [2B]
    fidelity: float               # = (1 + p) / 2
    singlet_fraction: float       # = (1 + 3p) / 4
    classical_bound: float        # = 2/3  (best measure-and-prepare strategy)
    beats_classical: bool         # fidelity > 2/3
    margin: float                 # fidelity - 2/3
    method: str                   # 'analytic' | 'qiskit'

@dataclass
class CHSHResult:                  # returned by chsh.chsh_value   [2B]
    S: float                      # = 2√2 · p
    classical_bound: float        # = 2.0
    tsirelson_bound: float        # = 2√2 ≈ 2.8284
    violates: bool                # S > 2.0
    margin: float                 # S - 2.0
    method: str                   # 'analytic' | 'qiskit'
```

---

## 4. Module interfaces

### `src/qkd/channel.py`  `[2B refine; 2A may stub]`
Maps physical conditions → the two governing parameters.

```python
def channel_state(
    elevation_deg: float,
    slant_range_km: float,
    atmosphere: dict,             # turbulence / loss configuration
    *,
    eta_override: float | None = None,
    p_override: float | None = None,
) -> ChannelState: ...
```
- Geometry/atmosphere → (η, p). Keep the model **deliberately simple** in 2B
  (a clean parameterised loss term + a turbulence→p map). Refinement later does
  not change this signature.
- Overrides let tests and parameter sweeps inject η/p directly. **Required** —
  the test suite depends on them.

### `src/qkd/bb84.py`  `[2B]`
BB84 **and** decoy estimation live together — they are too coupled to split.

```python
def run_bb84(
    channel: ChannelState,
    intensities: dict,            # {'signal': μ, 'decoy': ν, 'vacuum': ~0.0}
    n_pulses: int,
    detector: DetectorParams,
    eve: "EveStrategy | None" = None,
) -> BB84Result: ...
```
Behavioural contract:
- Honest channel (`eve=None`): `qber ≈ intrinsic_qber`; `decoy_anomaly_score ≈ 0`.
- `decoy_anomaly_score` is computed from how poorly the observed signal/decoy/
  vacuum **gains** are explained by a single honest η. Exact estimator is a 2B
  detail; the *contract* is "≥0, zero when honest, derived from decoy gains."
- `secure_key_rate` uses the asymptotic decoy bound (Lo-Ma-Chen / GLLP-style);
  formula is an implementation detail, the output field is fixed here.

### `src/qkd/eve.py`  `[2B]`
Eve **acts on physics**; the legitimate decoy estimator (in `bb84.py`) does the
**inference**. Clean separation: Eve tampers, Alice/Bob infer, anomaly is the
inference result.

```python
class EveStrategy:                # base; subclasses below
    def transform(self, channel: ChannelState, intensity: float, n_pulses: int
    ) -> tuple[float, float]:     # -> (effective_gain, induced_qber)
        ...

class Null(EveStrategy): ...          # no-op (equivalent to eve=None)
class InterceptResend(EveStrategy): ...
class QND_PNS(EveStrategy): ...       # photon-number-splitting via QND photon-number measurement
```
The physical contract that makes this worth building — **the project thesis,
made computable:**
- `InterceptResend` → pushes QBER toward **~0.25** (loudly visible).
- `QND_PNS` → leaves QBER **≈ intrinsic** (invisible to QBER) but distorts the
  signal-vs-decoy gain relationship → **`decoy_anomaly_score` rises.**

A QBER-only observer never sees the PNS attack. The decoy anomaly does. That
single fact is the bridge to the Echorym "hidden breach" concept (§ noted in
the research packet) — but it lives here as physics first.

### `src/qkd/teleportation.py`  `[2B]`
```python
def teleportation_fidelity(werner_p: float, *, method: str = "analytic"
) -> TeleportationResult: ...
```
- `method="analytic"` (default): closed form, exact, no heavy dependency.
- `method="qiskit"` (optional extra): build the Bell pair, apply a depolarising
  channel calibrated to `werner_p`, run the real teleportation circuit, and
  **assert it matches the analytic value.** Validation path, not the default.

### `src/qkd/chsh.py`  `[2B]`
```python
def chsh_value(werner_p: float, *, method: str = "analytic") -> CHSHResult: ...
```
Same analytic/qiskit policy as teleportation.

### `src/qkd/mission.py`  `[2C — reserve name in 2A]`
Chains the calibrated modules into one experiment. Phase 2B-6b makes this the
single pass-composition layer: it performs no I/O and introduces no new physics.
The zero-argument default pass remains available through `simulate_pass()`.

Reserved contract:
```python
def run_mission(channel: ChannelState, detector: DetectorParams,
                intensities: dict, n_pulses: int,
                eve: EveStrategy | None = None) -> PhysicsSignals: ...
```
Flow: BB84/decoy → QBER + gains + anomaly → teleportation fidelity (from p) →
CHSH (from p) → collect into `PhysicsSignals`. No scoring. No trust.

Phase 2B-6b pass composition:

```python
PULSE_REPETITION_RATE_HZ = 1.0e8  # illustrative fixed hardware clock

def simulate_pass(config=None, *, eve=None) -> PassResult: ...
```

The secure-key yield is an integral over the pass:
`sum(secure_key_rate_per_pulse_i * PULSE_REPETITION_RATE_HZ * dt)`. The clock
rate is hardware-owned and fixed; BB84 owns per-pulse secure-key rate; mission
owns only the composition and integration over opportunity.

---

## 5. Output schema — `outputs/results.json`

This schema **kills the original audit bug** (run.py wrote values nested under
`summary`; dashboard.js read flat root-level keys → silent mismatch). Defined
once here; both writer and dashboard conform.

```jsonc
{
  "schema_version": "2.0",
  "run_metadata":  { "timestamp": "", "config_hash": "", "eve_enabled": false, "eve_type": null },
  "channel":       { "transmittance": 0, "werner_p": 0, "intrinsic_qber": 0,
                     "slant_range_km": null, "elevation_deg": null },
  "bb84":          { "sifted_key_length": 0, "qber": 0,
                     "gains": { "signal": 0, "decoy": 0, "vacuum": 0 },
                     "y1_lower_bound": 0, "e1_upper_bound": 0,
                     "secure_key_rate": 0, "decoy_anomaly_score": 0 },
  "teleportation": { "fidelity": 0, "singlet_fraction": 0, "classical_bound": 0.6667,
                     "beats_classical": false, "margin": 0 },
  "chsh":          { "S": 0, "classical_bound": 2.0, "tsirelson_bound": 2.8284,
                     "violates": false, "margin": 0 },
  "physics_signals": { "qber": 0, "decoy_anomaly_score": 0, "chsh_margin": 0,
                       "teleportation_margin": 0, "loss_rate": 0, "secure_key_rate": 0 }
}
```

### Schema versioning — the 2A / 2B resolution (read carefully)

There is an apparent contradiction to resolve: 2A should set up schema
versioning, but Codex must **not** emit real v2.0 physics yet. Resolution:

- **`[2A]` DEFINES and REGISTERS v2.0** — this document + a **version-aware
  validator** that recognises *both* the current v1 toy output and v2.0.
- **`[2A]` the simulator keeps EMITTING v1.** No physics fields are populated.
- **`[2B]` flips the switchover** to emitting v2.0, once the modules exist to
  fill the fields honestly.

So the validator and the schema exist now; the *emission* changes later. The
2A test is written against v2.0 (version-aware) so it is **not thrown away**
when 2B lands. Codex does not write physics to satisfy it — the test simply
tolerates v1 today and is ready for v2.0 tomorrow.

---

## 6. Test targets

Test **files** are scaffolded in `[2A]` (mirroring module names so they are not
later rewritten). Physics **assertions** activate in `[2B]`.

| File | Phase | Asserts |
|------|-------|---------|
| `test_channel.py` | 2A stub / 2B | η, p stay in [0,1]; overrides honoured |
| `test_bb84.py` | 2A stub / 2B | honest channel: `qber ≈ intrinsic_qber`; gains physically sane |
| `test_decoy.py` | 2B | anomaly ≈ 0 honest; **anomaly > 0 under `QND_PNS`**; QBER unchanged by PNS |
| `test_eve.py` | 2B | `InterceptResend` drives QBER → ~0.25 |
| `test_teleportation.py` | 2A stub / 2B | **constants below** |
| `test_chsh.py` | 2A stub / 2B | **constants below** |
| `test_schema.py` | 2A | validates `results.json` against v2.0 (accepts v1 today) |

### Constant assertions — free, permanent regression locks

These closed-form values can be asserted **the moment** the analytic functions
exist, and they lock the physics forever:

```
Teleportation:   F(p=1)   = 1.0
                 F(p=1/3) = 2/3        ← the classical bound, exactly
                 F(p=0)   = 1/2
                 singlet_fraction(p=1/3) = 1/2

CHSH:            S(p=1)      = 2√2 ≈ 2.8284   (Tsirelson)
                 S(p=1/√2)   = 2.0            ← violation threshold, exactly
                 S(p=0)      = 0.0

Coupling check:  teleportation beats classical at p > 1/3
                 CHSH violates at            p > 1/√2 ≈ 0.7071
                 ⇒ regime 1/3 < p < 0.7071 : useful for transfer, NO Bell violation
```

That last coupling regime is the structural fingerprint a decorative model
**cannot** reproduce. A test that confirms "fidelity beats 2/3 while S ≤ 2" in
that band is the strongest single proof that the curves are computed, not drawn.

---

## 7. Phase 2A work items — what Codex implements NOW

**Approved for this pass:**
1. `pyproject.toml` — core deps + optional extras (see §9). Core = `numpy`,
   `matplotlib`. No required `qiskit`.
2. `npm start` — one-command dashboard launch.
3. `docs/INTERFACES.md` — this file (add if not present).
4. `README` — document the **current** workflow (Run simulator → `outputs/` →
   dashboard) **and** the planned Phase 2B architecture + active-vs-archive map.
5. Test scaffolding — create the §6 files with placeholders / simple
   existing-behaviour tests + the version-aware `test_schema.py`.
6. Reserve module filenames: `src/qkd/{channel,bb84,eve,teleportation,chsh,signals,mission}.py`
   (empty or docstring-only stubs) so packaging/docs do not churn in 2B.

**NOT approved this pass (explicitly held for 2B+):**
- changing BB84 logic;
- changing teleportation physics (the sine-wave curve stays until 2B replaces it);
- implementing Eve, CHSH, or decoy estimation;
- **switching emitted output to v2.0** (define + validate only; keep emitting v1);
- deleting or moving any archive files.

---

## 8. File preservation & archive porting candidates

**Preserve — do not delete or casually move:**
- `01-Gate-Noise-Archive/` — flagged in the research packet as possibly holding
  the **genuinely grounded** Bell-state / QEC / noise-model circuits. This is
  the one physically-real asset that already exists.

**Porting candidates (for 2B, not now):** the README's active-vs-archive
section should explicitly tag which archive files are candidates to feed the
`method="qiskit"` validation paths — specifically any working Bell-state
preparation, depolarising-noise model, or measurement-count routines. Tag them;
do not move them yet. The cleanup must not bury the real physics.

---

## 9. Analytic / Qiskit hybrid — packaging policy

Default path is analytic (fast, exact, lightweight). Qiskit is an **optional
validation extra**, never a hard dependency.

```
# pyproject.toml structure (Codex to finalise exact syntax)
dependencies            = ["numpy", "matplotlib"]
optional.qiskit         = ["qiskit"]      # enables method="qiskit" validation
optional.dev            = ["pytest"]

# install profiles:  qkd-aero            (analytic only)
#                    qkd-aero[qiskit]    (+ circuit validation)
#                    qkd-aero[dev]       (+ tests)
```

Rationale: analytic formulas are the ground truth and what dashboards/sweeps
run on; the Qiskit path exists to *prove* the analytic values to a physics
reviewer (`assert circuit_result ≈ analytic_result`) and to reuse the archive
circuits — without imposing Qiskit on every install or slowing the default test
run.

---

## 10. Decisions still held open (out of scope for 2A)

Recorded so they are not silently resolved by implementation:
- `[2D]` exact trust/coherence formula and its weights;
- `[2D]` whether coherence is a distinct computed variable or a function of trust;
- breach-classification taxonomy (malicious / noise / environmental);
- the **0.376 coherence threshold** — remains symbolic; if ever real, it must be
  *derived* from dynamics, not imposed (no relevant physical constant sits near
  0.376; the meaningful bounds here are 1/3, 1/√2, 2/3, 2√2, ~11% QBER);
- `[3]` multi-node graph representation;
- whether digital twins become agents, state mirrors, or predictive models.

These belong to 2D and beyond. 2A/2B must not encode answers to them.
