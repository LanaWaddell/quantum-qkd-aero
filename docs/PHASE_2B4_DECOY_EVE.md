# Phase 2B-4 — Decoy-State Statistics & QND/PNS Eve (SPEC)

**Status:** specification, queued. Self-contained so a fresh session (Claude or
Codex) can implement it without the originating conversation.
**Relationship to other docs:** `INTERFACES.md` defines the module contracts and
the `PhysicsSignals` schema; this document specifies the decoy/Eve *physics and
behaviour*. Where they disagree, `INTERFACES.md` wins.
**Depends on:** 2B-1 (teleportation/CHSH), 2B-2 (channel_state → eta, werner_p),
2B-3 (run.py pass loop). Grounds the decorative `headline_key_yield` /
`remaining_entangled_resource_kb` placeholder left labelled in 2B-3.

---

## 0. Why this phase exists (the thesis it makes computable)

The current `bb84.py` is a *classicalised* bit simulation: it transmits bits via
`transmit_bit(p_loss, p_flip)` and computes QBER from mismatches. It has NO
photon-number structure, so it cannot represent the attack that matters most:
a photon-number-splitting (PNS) attack. PNS is the canonical "hidden breach" —
an eavesdropper who learns key bits while introducing **no QBER**. A QBER-only
monitor sees a clean channel; the attack is invisible to it.

The decoy-state method is precisely the countermeasure: by sending pulses of
different intensities and comparing their *gains*, one can bound the
single-photon yield and detect the statistical signature PNS leaves even when
QBER is undisturbed. This phase implements that, which simultaneously:

1. delivers the **QND/PNS Eve** model (the hidden breach),
2. makes the **decoy-state machinery** real (not decorative),
3. computes a genuine **secure key rate** — grounding the last decorative number
   from 2B-3 (`headline_key_yield`).

This is the QKD-physics realisation of the Echorym "breach invisible to ordinary
noise" theme. It belongs here as PHYSICS FIRST; any Echorym/trust mapping is 2D.

---

## 1. The non-negotiable honesty rule for this phase

Everything must be **computed from simulated pulse statistics**, never assumed.
The failure mode (the analogue of the `0.85 + sin(frame/50)` curve):

- DO NOT hardcode `Y_1`, `e_1`, the anomaly score, or the key rate.
- DO simulate Poisson photon-number statistics per intensity, simulate honest (or
  Eve-tampered) detection, measure the per-intensity **gains** and **QBERs**, and
  then *derive* the single-photon bounds from those measured gains via the decoy
  inequalities.

The `decoy_anomaly_score` must be a **difference between two computed quantities**:
the single-photon yield an honest channel would produce vs. the yield the decoy
estimator infers from the (Eve-tampered) gains. If those are ever stipulated
rather than computed, the phase has failed its own standard.

A second guard: under an **honest channel (no Eve)**, the decoy estimate of `Y_1`
must agree with the honest single-photon yield to within statistical/numerical
tolerance, so `decoy_anomaly_score ≈ 0`. The score only departs from 0 under PNS.

---

## 2. Physics reference (the equations to implement, with their meaning)

### 2.1 Weak coherent pulse photon statistics
A laser pulse of mean photon number (intensity) `mu` has Poisson photon-number
distribution:

    P(n | mu) = exp(-mu) * mu**n / n!

Decoy-state BB84 uses (at least) three intensities:
    signal  mu     (e.g. 0.5)
    decoy   nu     (e.g. 0.1),   with nu < mu
    vacuum  ~0.0   (background/dark-count probe)

### 2.2 Honest channel: yields and gains
Let `eta` be the *total* single-photon transmission-and-detection probability
(channel transmittance from channel_state × detector efficiency). The yield of an
`n`-photon pulse (probability Bob registers a detection) on an honest channel:

    Y_n = 1 - (1 - Y_0) * (1 - eta)**n          (n >= 0)

where `Y_0` is the dark-count / background probability per window (the vacuum
yield). The **gain** at intensity `mu` (overall detection probability) is:

    Q_mu = sum_n P(n|mu) * Y_n
         = Y_0 + 1 - exp(-eta * mu)              (closed form for the honest model)

and the intensity QBER (with intrinsic optical error `e_d` and the random
dark-count error of 1/2):

    E_mu * Q_mu = e_0 * Y_0 + e_d * (1 - exp(-eta*mu)),   e_0 = 1/2

These closed forms are for the HONEST channel and may be used to (a) drive the
simulation and (b) provide the "honest expected" reference for the anomaly score.
They must NOT be used as the *measured* values under Eve — those come from the
Eve-tampered simulation (§2.4).

### 2.3 Decoy-state single-photon bounds (the estimator)
From measured gains/QBERs at signal, decoy, vacuum, the standard Lo–Ma–Chen decoy
bounds give a lower bound on the single-photon yield `Y_1` and an upper bound on
the single-photon error `e_1`. Implement the standard two-decoy (or vacuum+weak)
estimator, e.g.:

    Y_1_lower >= (mu / (mu*nu - nu**2)) *
                 ( Q_nu*exp(nu) - Q_mu*exp(mu)*(nu**2/mu**2) - (mu**2 - nu**2)/mu**2 * Y_0 )

    e_1_upper <= (E_nu*Q_nu*exp(nu) - e_0*Y_0) / (Y_1_lower * nu)

(Use the precise forms from Lo, Ma & Chen 2005 / Ma et al. 2005; the exact
algebra is an implementation detail — the CONTRACT is "Y_1 lower bound and e_1
upper bound, computed from the measured per-intensity gains.")

The **single-photon gain**:  Q_1 = Y_1 * mu * exp(-mu).

### 2.4 The QND / PNS Eve (the hidden breach)
Eve performs a quantum non-demolition photon-number measurement (no polarisation
disturbance), then acts conditionally on photon number `n`:

  - `n = 0`: nothing to forward.
  - `n = 1`: with some probability, BLOCK (she cannot split a single photon without
    disturbance); optionally forward a fraction through a lossless line she controls.
  - `n >= 2`: SPLIT — keep one photon (store for later measurement in the revealed
    basis → learns the bit with zero error), forward the rest, often through a
    **lossless** channel so Bob's overall rate looks normal.

Key properties the implementation must reproduce:
  - PNS introduces **no extra QBER** on the photons Bob receives (Eve does not
    measure polarisation in transit) → `E_mu` ≈ intrinsic, unchanged.
  - PNS **distorts the gain-vs-intensity relationship**: multi-photon pulses are
    favoured (forwarded losslessly), single-photon pulses suppressed. So the
    *ratio* of signal gain to decoy gain departs from the honest Poisson
    prediction. The decoy estimator then returns an anomalous (often impossibly
    low or inconsistent) `Y_1_lower`.
  - Eve can be tuned to match the honest TOTAL gain `Q_mu` and QBER, which is why
    a QBER-only / single-intensity monitor is fooled. The decoy comparison is not.

Provide at least these strategies (subclasses of an `EveStrategy` base, per
INTERFACES §4):
    `Null`            — no attack (honest channel).
    `InterceptResend` — measures & resends; drives QBER toward ~0.25 (the LOUD
                        attack, for contrast; not the focus of this phase).
    `QND_PNS`         — the hidden breach above.

### 2.5 Secure key rate (grounds the 2B-3 placeholder)
The GLLP / decoy asymptotic secure-key rate per pulse:

    R >= q * { -Q_mu * f_EC * H2(E_mu) + Q_1 * (1 - H2(e_1)) }

with `H2` the binary entropy, `f_EC` the error-correction inefficiency
(`DetectorParams.error_correction_efficiency`, default 1.16), `q` the
sifting/basis factor (1/2 for standard BB84, or ~1 for efficient BB84 — state
which). Clamp `R` at 0 (a negative formula value means "no secure key"). This
`secure_key_rate` REPLACES the decorative `headline_key_yield` placeholder from
2B-3 — wire it into run.py / results.json in this phase or a 2B-4b follow-on.

---

## 3. Module / interface targets (per INTERFACES.md)

- **`src/qkd/bb84.py`** — add decoy-state estimation. Keep the existing
  classicalised `run_bb84`/`compute_qber` (tests depend on them) OR introduce a
  new `run_decoy_bb84(channel: ChannelState, intensities, n_pulses, detector,
  eve=None) -> BB84Result` that does the photon-number-aware simulation. Prefer a
  NEW function so 2A baseline tests for the old path stay green; the old path can
  be retired in a later cleanup.
- **`src/qkd/eve.py`** — currently a skip-only placeholder. Replace with the
  `EveStrategy` base + `Null`, `InterceptResend`, `QND_PNS`. Eve TAMPERS with the
  per-pulse forwarding/gains; the legitimate decoy estimator (in bb84.py) does the
  inference. Keep that separation clean.
- **`BB84Result`** (dataclass; co-locate in bb84.py like Teleportation/CHSH did):
  `sifted_key_length, qber, gains{signal,decoy,vacuum}, qber_per_intensity,
  y1_lower_bound, e1_upper_bound, q1, secure_key_rate, decoy_anomaly_score`.
- **`PhysicsSignals`** (already defined in signals.py): populate `qber`,
  `decoy_anomaly_score`, `secure_key_rate`, `loss_rate` from the result. NO trust
  field — that wall stays.

---

## 4. Test targets (the regression locks)

Replace the skip-only `tests/test_decoy.py` and `tests/test_eve.py` with real tests:

1. **Poisson sanity:** `sum_n P(n|mu)` ≈ 1; mean ≈ mu.
2. **Honest gain matches closed form:** simulated `Q_mu` ≈ `Y_0 + 1 - exp(-eta*mu)`
   to statistical tolerance (use enough pulses, or compute analytically).
3. **Honest channel anomaly ≈ 0:** with `Null` Eve, `decoy_anomaly_score` ≈ 0 and
   the decoy `Y_1_lower` ≈ honest `Y_1`.
4. **PNS is invisible to QBER:** with `QND_PNS`, `E_mu` ≈ intrinsic (does NOT rise),
   yet `decoy_anomaly_score` > 0. THIS is the thesis test — the most important one.
5. **Intercept-resend is loud:** with `InterceptResend`, `qber` rises toward ~0.25.
6. **Secure key rate is non-negative and sane:** `R >= 0`; on a clean low-loss
   channel `R > 0`; under strong PNS the decoy bound drives `R` toward 0.
7. **Key rate monotonicity (honest):** `R` decreases as loss increases (lower eta).
8. **Determinism:** seeded RNG → reproducible gains (so tests are stable).

Test #4 is to this phase what the coupling test was to 2B-1: the structural
signature a decorative model cannot fake.

---

## 5. Scope discipline

**In scope:** decoy-state estimation, the three Eve strategies, secure key rate,
populating PhysicsSignals, grounding the 2B-3 key-yield placeholder, the tests above.

**Out of scope (do NOT pull in):**
- trust / coherence scoring (that is 2D and reads PhysicsSignals; no trust field
  enters bb84/eve);
- finite-key corrections (asymptotic key rate only; flag finite-key as a known
  simplification in the docstring, as 2B-2 flagged its illustrative parameters);
- multi-node / network (Phase 3);
- the v2.0 schema *emission* switch — if the new key-rate output needs new JSON
  fields, add them as EXTRA keys under the still-v1 results (as 2B-3 did with
  `pass_profile`) OR make this the deliberate moment to flip to v2.0 *with* the
  schema-hardening from `SCHEMA_HARDENING_2B.md` landed in the SAME PR (preferred
  if the key-rate work naturally wants the v2.0 `bb84`/`physics_signals` blocks).
  Decide explicitly; do not half-switch.

**Two-phase Codex gate (as established all through 2B):** before editing, Codex
inspects current `bb84.py`/`eve.py`, states exactly how decoy estimation and Eve
integrate without breaking existing tests, lists files, and waits for approval.
After: full diffs, `pytest -v`, run.py still works, `git diff --check`,
`git status --short`. Decoy/Eve math is non-trivial — the plan review matters.
